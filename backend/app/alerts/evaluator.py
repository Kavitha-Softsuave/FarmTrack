"""Alert evaluator: runs the rules engine for every farmer with a station, stores new alerts and pushes them.

Idempotent: one alert per (farmer, dedupe_key), where the key names the episode, e.g. 'scab:ST05:2026-05-04'. A risk that later
turns red gets its own alert ('...:red'); a yellow one is not raised once the red one exists.

The episode date comes from RiskItem.detail ('episode', 'episode_start', 'period_start' or 'spray_at': an ISO date or datetime;
the rules engine sets period_start for scab and spray_at for rain wash-off). Without one (leaf spot, late blight) an episode lasts
until EPISODE_GAP_DAYS have passed since the farmer's last alert of that kind, so a long spell of risky weather gives a reminder
every few days, not one alert per hour or per day.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import SpokenOut
from app.clock import IST
from app.db.models import AdviceRow, AlertRow, DeviceRow, FarmerRow, SprayLogRow, as_ist
from app.db.repo import farmer_profile
from app.domain.types import FarmerProfile, LocalizedText, RiskItem, Severity, SprayRecord, WeatherSnapshot
from app.integrations.history import merge_history, records_from_spray_logs
from app.integrations.reference import ProductRef, harvest_day_of_year, load_product_master

if TYPE_CHECKING:
    from app.services.container import Container

log = logging.getLogger(__name__)

# RiskItem.id -> short code used in dedupe keys
RISK_KINDS: dict[str, str] = {
    "scab_infection_risk": "scab",
    "marssonina_alternaria_risk": "marssonina",
    "late_blight_risk": "late_blight",
    "rain_washoff": "washoff",
}
ALERT_LEVELS = (Severity.yellow, Severity.red)
RECENT_SPRAY_DAYS = 90
IMMINENT_HARVEST_DAYS = 7
EPISODE_GAP_DAYS = 5
SPRAY_LOOKUP_LIMIT = 50                        # recent diary entries searched for the scan behind a spray reminder
SAME_SPRAY_WINDOW = timedelta(minutes=1)
_EPISODE_KEYS = ("episode", "episode_start", "period_start", "spray_at", "sprayed_at", "start")

STALE_NOTE = LocalizedText(
    en="The field sensor is not reporting, so this alert uses the weather forecast only.",
    hi="खेत का सेंसर बंद है, इसलिए यह सूचना केवल मौसम के अनुमान पर आधारित है।",
)
_HI_MONTHS = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्तूबर", "नवंबर", "दिसंबर")


@dataclass
class _Draft:
    kind: str
    level: Severity
    dedupe_key: str
    title: LocalizedText
    body: LocalizedText
    payload: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------- public API
def run_once(session: Session, container: Container, now: datetime | None = None) -> list[AlertRow]:
    """Evaluate every farmer once and return the NEW alerts (committed). Safe to call repeatedly: repeats create nothing."""
    when = now if now is not None else container.clock.now()
    when = when.replace(tzinfo=IST) if when.tzinfo is None else when
    products = load_product_master(container.settings.data_dir)
    weather_cache: dict[str, WeatherSnapshot | None] = {}
    stale_cache: dict[str, bool] = {}
    farmers = session.scalars(select(FarmerRow).where(FarmerRow.station_id.is_not(None)).order_by(FarmerRow.id)).all()
    created: list[AlertRow] = []
    for farmer in farmers:
        farmer_id = farmer.id
        try:
            new = _evaluate_farmer(session, container, farmer, when, products, weather_cache, stale_cache)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("alert evaluation failed for farmer %s", farmer_id)
            continue
        if new:
            _push(session, container, farmer, new, when)
            created.extend(new)
    return created


# ------------------------------------------------------------------------------------------------- per farmer
def _evaluate_farmer(session: Session, container: Container, farmer: FarmerRow, now: datetime,
                     products: Mapping[str, ProductRef], weather_cache: dict[str, WeatherSnapshot | None],
                     stale_cache: dict[str, bool]) -> list[AlertRow]:
    station = farmer.station_id or ""
    weather_on = container.settings.weather_enabled
    weather: WeatherSnapshot | None = None
    if weather_on:
        if station not in weather_cache:
            weather_cache[station] = _snapshot(container, farmer, now)
        weather = weather_cache[station]
        if weather is None:
            return []

    profile = farmer_profile(farmer)
    history = _history(session, container, farmer, now, products)
    drafts: list[_Draft] = []
    if weather is not None:                     # WEATHER_ENABLED=false: no weather risk alerts, the waiting-period alert still runs
        if station not in stale_cache:
            stale_cache[station] = _sensor_stale(container, station, now)
        sensor_stale = stale_cache[station] or weather.stale
        for risk in container.rules.evaluate_risks(profile, weather, now, history):
            short = RISK_KINDS.get(risk.id)
            if short is None or risk.level not in ALERT_LEVELS:
                continue
            episode = _episode_date(session, farmer.id, short, station, risk.detail, now)
            drafts.append(_risk_draft(risk, short, station, episode, sensor_stale))
    waiting = _waiting_period_draft(profile, history, now, products, container.settings.data_dir)
    if waiting is not None:
        drafts.append(waiting)

    created: list[AlertRow] = []
    for draft in drafts:
        if _already_alerted(session, farmer.id, draft):
            continue
        scan_id = _scan_for_draft(session, farmer.id, draft)
        row = AlertRow(
            farmer_id=farmer.id, kind=draft.kind, level=draft.level.value, dedupe_key=draft.dedupe_key,
            title=draft.title.model_dump(), body=draft.body.model_dump(),
            spoken=_spoken(container, _speech(draft.title.en, draft.body.en), _speech(draft.title.hi, draft.body.hi)),
            payload={**draft.payload, "scan_id": scan_id} if scan_id else draft.payload, created_at=now,
        )
        session.add(row)
        created.append(row)
    session.flush()
    return created


def _snapshot(container: Container, farmer: FarmerRow, now: datetime) -> WeatherSnapshot | None:
    try:
        return container.weather.snapshot(farmer.station_id, farmer.lat, farmer.lon, now)
    except Exception as exc:
        log.warning("no weather for station %s, its farmers are skipped: %s", farmer.station_id, type(exc).__name__)
        return None


def _sensor_stale(container: Container, station: str, now: datetime) -> bool:
    try:
        return bool(container.iot.is_stale(station, now))
    except Exception as exc:
        log.warning("sensor state unknown for station %s, treating as stale: %s", station, type(exc).__name__)
        return True


def _history(session: Session, container: Container, farmer: FarmerRow, now: datetime,
             products: Mapping[str, ProductRef]) -> list[SprayRecord]:
    try:
        zoho = container.zoho.get_history(farmer.id, now)
    except Exception as exc:
        log.warning("zoho history unavailable for farmer %s, using the app diary only: %s", farmer.id, type(exc).__name__)
        zoho = []
    rows = session.scalars(select(SprayLogRow).where(SprayLogRow.farmer_id == farmer.id)).all()
    return merge_history(zoho, records_from_spray_logs(rows, products, until=now))


# ------------------------------------------------------------------------------------------------- drafts
def _risk_draft(risk: RiskItem, short: str, station: str, episode: date, sensor_stale: bool) -> _Draft:
    key = f"{short}:{station}:{episode.isoformat()}"
    if risk.level == Severity.red:
        key += ":red"
    title = LocalizedText(en=risk.title.en, hi=risk.title.hi or risk.title.en)
    body = LocalizedText(en=risk.text.en, hi=risk.text.hi or risk.text.en)
    if sensor_stale:
        body = LocalizedText(en=f"{body.en} {STALE_NOTE.en}".strip(), hi=f"{body.hi} {STALE_NOTE.hi}".strip())
    payload = {"risk_id": risk.id, "station_id": station, "sensor_stale": sensor_stale, "detail": _jsonable(risk.detail)}
    return _Draft(risk.id, risk.level, key, title, body, payload)


def _waiting_period_draft(profile: FarmerProfile, history: list[SprayRecord], now: datetime,
                          products: Mapping[str, ProductRef], data_dir: Path) -> _Draft | None:
    """Alert when the latest safe-to-harvest date (spray + waiting period) falls after the expected harvest date.

    Only crops with harvest data (apple, from the stage calendar) can be checked; other crops return None.
    """
    if profile.primary_crop != "Apple":
        return None
    doy = harvest_day_of_year(data_dir, profile.phenology_band, profile.primary_variety)
    if doy is None:
        return None
    today = now.date()
    harvest = date(today.year, 1, 1) + timedelta(days=doy - 1)
    days_to_harvest = (harvest - today).days
    if days_to_harvest < 0:
        return None
    worst: tuple[date, SprayRecord, ProductRef] | None = None
    for record in history:
        product = products.get(record.product_id or "")
        if record.nutrient or product is None or not product.waiting_period_days:
            continue
        if record.sprayed_at < now - timedelta(days=RECENT_SPRAY_DAYS):
            continue
        safe = record.sprayed_at.date() + timedelta(days=product.waiting_period_days)
        if worst is None or safe > worst[0]:
            worst = (safe, record, product)
    if worst is None or worst[0] <= harvest:
        return None
    safe, record, product = worst
    sprayed = record.sprayed_at.date()
    wait = product.waiting_period_days
    name_en, name_hi = product.active_ingredient, product.active_ingredient_hi or product.active_ingredient
    title = LocalizedText(en="Wait before picking fruit", hi="फल तोड़ने से पहले रुकें")
    body = LocalizedText(
        en=f"{name_en} was sprayed on {_date_text(sprayed, 'en')}. It needs {wait} days. "
           f"Do not pick fruit before {_date_text(safe, 'en')}.",
        hi=f"{name_hi} का छिड़काव {_date_text(sprayed, 'hi')} को हुआ था। इसके बाद {wait} दिन रुकना है। "
           f"{_date_text(safe, 'hi')} से पहले फल न तोड़ें।",
    )
    level = Severity.red if days_to_harvest <= IMMINENT_HARVEST_DAYS else Severity.yellow
    payload = {"product_id": product.product_id, "sprayed_on": sprayed.isoformat(), "safe_from": safe.isoformat(),
               "expected_harvest": harvest.isoformat(), "days_to_harvest": days_to_harvest, "waiting_period_days": wait}
    return _Draft("waiting_period", level, f"waiting:{product.product_id}:{sprayed.isoformat()}", title, body, payload)


def _date_text(value: date, lang: str) -> str:
    month = _HI_MONTHS[value.month - 1] if lang == "hi" else value.strftime("%b")
    return f"{value.day} {month}"


def _explicit_episode(detail: dict[str, Any]) -> date | None:
    for key in _EPISODE_KEYS:
        value = detail.get(key)
        if isinstance(value, datetime):
            return value.astimezone(IST).date() if value.tzinfo else value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                continue
    return None


def _episode_date(session: Session, farmer_id: str, short: str, station: str, detail: dict[str, Any], now: datetime) -> date:
    explicit = _explicit_episode(detail)
    if explicit is not None:
        return explicit
    prefix = f"{short}:{station}:"
    cutoff = now - timedelta(days=EPISODE_GAP_DAYS)
    rows = session.execute(select(AlertRow.dedupe_key, AlertRow.created_at)
                           .where(AlertRow.farmer_id == farmer_id, AlertRow.dedupe_key.startswith(prefix, autoescape=True))).all()
    open_episodes = [key[len(prefix):][:10] for key, created in rows if (seen := as_ist(created)) is not None and seen >= cutoff]
    return date.fromisoformat(max(open_episodes)) if open_episodes else now.date()


def _scan_for_draft(session: Session, farmer_id: str, draft: _Draft) -> str | None:
    """The scan behind a reminder about a spray the farmer logged from that scan's advice ('I sprayed this'), so the app can open it.

    Only the rain wash-off reminder (found by the spray time) and the waiting-period alert (by spray day and product) are about one
    spray. Weather risks belong to the field, not to a scan: no scan id.
    """
    payload = draft.payload
    at: datetime | None = None
    day: date | None = None
    product_id: str | None = None
    try:
        if draft.kind == "rain_washoff":
            at = _parse_time((payload.get("detail") or {}).get("spray_at"))
        elif draft.kind == "waiting_period":
            day, product_id = date.fromisoformat(str(payload.get("sprayed_on"))), payload.get("product_id")
    except ValueError:
        return None
    if at is None and day is None:
        return None
    rows = session.scalars(select(SprayLogRow).where(SprayLogRow.farmer_id == farmer_id, SprayLogRow.advice_id.is_not(None))
                           .order_by(SprayLogRow.sprayed_at.desc()).limit(SPRAY_LOOKUP_LIMIT)).all()
    for row in rows:
        sprayed = as_ist(row.sprayed_at)
        if sprayed is None:
            continue
        same_time = at is not None and abs(sprayed - at) <= SAME_SPRAY_WINDOW
        same_day = day is not None and sprayed.date() == day and row.product_id == product_id
        if same_time or same_day:
            advice = session.get(AdviceRow, row.advice_id)
            return advice.scan_id if advice is not None and advice.farmer_id == farmer_id else None
    return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def _already_alerted(session: Session, farmer_id: str, draft: _Draft) -> bool:
    keys = [draft.dedupe_key]
    if draft.level == Severity.yellow and draft.kind in RISK_KINDS:
        keys.append(draft.dedupe_key + ":red")      # a red alert for the same episode already covers this one
    found = session.scalar(select(AlertRow.id).where(AlertRow.farmer_id == farmer_id, AlertRow.dedupe_key.in_(keys)).limit(1))
    return found is not None


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


# ------------------------------------------------------------------------------------------------- text, speech, push
def _speech(title: str, body: str) -> str:
    return f"{title.rstrip('.')}. {body}".strip()


def _spoken(container: Container, en: str, hi: str) -> dict[str, Any]:
    """SpokenOut as JSON. Falls back to text only when the voice service is missing or fails: an alert must never be lost to TTS."""
    try:
        from app.voice.spoken import spoken_out

        return spoken_out(container.audio, en, hi).model_dump(mode="json")
    except Exception as exc:
        log.info("spoken audio not attached to alert (%s)", type(exc).__name__)
        return SpokenOut(text=LocalizedText(en=en, hi=hi)).model_dump(mode="json")


def _push(session: Session, container: Container, farmer: FarmerRow, alerts: list[AlertRow], now: datetime) -> None:
    farmer_id, language = farmer.id, "en" if farmer.language == "en" else "hi"
    try:
        tokens = list(session.scalars(select(DeviceRow.push_token).where(DeviceRow.farmer_id == farmer_id)).all())
        if not tokens:
            return
        for alert in alerts:
            title, body = LocalizedText(**alert.title), LocalizedText(**alert.body)
            data = {"alert_id": alert.id, "kind": alert.kind, "level": alert.level}
            if isinstance((alert.payload or {}).get("scan_id"), str):
                data["scan_id"] = alert.payload["scan_id"]                  # the app opens that scan when the push is tapped
            sent = False
            for token in tokens:
                try:
                    sent = bool(container.push.send(token, title.get(language) or title.en, body.get(language) or body.en, data)) or sent
                except Exception as exc:
                    log.warning("push failed for farmer %s: %s", farmer_id, type(exc).__name__)
            if sent:
                alert.pushed_at = now
        session.commit()
    except Exception:
        session.rollback()
        log.exception("push step failed for farmer %s", farmer_id)
