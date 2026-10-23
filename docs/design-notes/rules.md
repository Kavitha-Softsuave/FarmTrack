# Rules engine (agent RULES): doubts, judgement calls, contract requests

Entry point: `app.rules.engine.build_rules_engine(settings, disabled_products=None)`. Tests: `cd backend && .venv/Scripts/python -m pytest tests/rules -q` (593 pass, 1 skipped = S11, about 13 s). Lint and mypy clean.

## Contract requests
- **Settings: add `rules_auto_advice_diseases: str | None = None`** (env `RULES_AUTO_ADVICE_DISEASES`). The policy reads `os.environ` on every call, but pydantic-settings does not export `.env` values to `os.environ`, so a value written only in the repo `.env` is invisible. The engine already does `getattr(settings, "rules_auto_advice_diseases", None)`, so adding the field is enough; no other change needed.
- None other. `rules_config.json` wins over `Settings.min_confidence_*` (read from the file, 0.65).

## Policy and routing
- Auto-advice only for `Apple___Apple_scab` (`app/rules/policy.py: AUTO_ADVICE`). `RULES_AUTO_ADVICE_DISEASES`: comma list or `*` (every catalogue disease with chemical_control yes). `requires_expert_review`, `expert_referral`, `no` (no cure), low confidence, unknown/None disease and wrong-crop disease ALWAYS win, even with `*`.
- Reason codes in `RuleOutput.reasons`: `disease_unknown, disease_not_in_catalogue, disease_crop_mismatch, requires_expert_review, no_chemical_cure, expert_referral, low_confidence, not_in_auto_advice_policy, out_of_season_for_disease, phenology_band_unknown, no_product_for_disease_and_stage, no_product_after_exclusions, no_approved_data_for_crop, healthy_class, auto_advice_policy`.
- `RuleInput.disease_confidence` defaults to 0.0, which means expert queue: callers must pass the real confidence.
- A **healthy class below 0.65 confidence is not declared healthy**: it goes to the expert queue (`low_confidence`). Brief said healthy -> `not_a_disease` without a threshold; I added it because telling a farmer "your plant is healthy" on a 0.4 guess is unsafe.
- Apple farmer with no `phenology_band` and no `elevation_m`: status `needs_more_info`, route `expert_queue` (stage cannot be derived). `evaluate_risks` then uses the widest scab window over all bands (warn rather than miss).
- Expert route: no products, no `excluded`, no `timing`; `non_chemical` = catalogue text (Hindi draft from `messages.NON_CHEMICAL_HI`), `See scab/Marssonina` aliases resolved to the target's text, a no-cure message when chemical_control is `no` (unless the catalogue text already starts "No cure"), a generic hygiene sentence when the catalogue has nothing. The one catalogue measure that names an oil spray (San Jose scale) is dropped: a medicine must never appear in the expert route.
- "General HP rules in notes_query": `notes_query` keeps exactly the four frozen keys (`crop, disease_id, stage, product_ids`) because a caller may splat it into `KnowledgeBase.notes_for`. On the expert route `product_ids` is `[]`, which makes RAG return the disease and rule notes. No extra key added.
- History warnings (stale, off-label, tank-mix, rotation limit) are attached on every route except `no_approved_data` and `not_a_disease`.
- `severity`: yellow for advice and expert routes; red when a risk concerning that disease (scab for scab, leaf-spot for Marssonina/Alternaria, late blight) or a rain wash-off is red; green only for `not_a_disease`.

## Stage and season
- Stage = latest calendar stage whose `typical_doy` has been reached (same day-of-year in any year); before the first stage `dormant`; after `walnut_plus_40d` the cultivar's `pre_harvest/harvest/post_harvest`. Unknown cultivar -> Royal Delicious. Non-apple crops: `stage=None`, `stage_source=None` (rows are stage `any`).
- Fallback: no row for the exact stage -> latest EARLIER stage that has rows (trace line says so); never a later stage; apple rows with stage `any` always match. Example: S3 clock 30 Mar for band B2 is `tight_cluster` (day 89 < pink bud day 92) although the data says pink bud, so scab advice comes from the `green_tip` rows.
- Scab primary season = `green_tip - 7 d` .. `petal_fall + 21 d + 7 d` for the farmer's band (slack at BOTH ends because the calendar is an estimate). Marssonina/Alternaria (only reachable when the policy is widened): out of season before 1 June (`marssonina_alternaria_weather.active_from_date_mmdd`).
- `days_to_harvest`: RuleInput override, else calendar `harvest` row of the cultivar for the band; after this year's harvest, days to next year's. Non-apple without override: unknown -> `HARVEST_DATE_UNKNOWN` warning (no exclusion possible).

## Exclusions and limits
- "Last spray" = latest fungicide-family spray (fungicide, bactericide) of this calendar year on this crop; a spray whose product row belongs to another crop is ignored (history rows carry no crop). Insecticide/acaricide candidates compare with the last pest-family spray; oil is separate.
- Same active ingredient: shares ANY active with the last spray (so `mancozeb + pyraclostrobin` follows `mancozeb`). Always excluded.
- Same FRAC component as the last spray: excluded only when an alternative remains; if every remaining candidate shares a group they are kept with a yellow `ROTATION_LIMIT` (`params.kind = same_frac_no_alternative`).
- DMI = component `3`, counted inside mixtures; QoI = `11` (limit 3, 4 once 12 or more fungicide sprays this season); SDHI = `7` (2 consecutive fungicide sprays). IRAC `3A` is NOT DMI (letter suffix keeps it apart). Counts use history since 1 Jan of `now.year`. Duplicate Zoho rows (self + advisor, same actives and codes within 5 minutes) count once.
- QoI only in a mixture is applied to every crop (`P071` azoxystrobin alone is excluded when the policy is widened to tomato).
- Unknown waiting period: excluded when `days_to_harvest <= 30` (number parsed from `unknown_waiting_period_policy`), otherwise kept with `NO_WAITING_PERIOD`. `waiting_period_days > days_to_harvest` is excluded (equal is allowed).
- `stop_sprays_before_harvest_days` (21) is NOT an exclusion (the legal rule is the waiting period; 21 days is a SKUAST second opinion): it only produces a yellow `NEAR_HARVEST` warning.
- Dodine excluded when the highest of current temp, next 12 h forecast and today's forecast maximum is above 30 C (exactly 30 is allowed; no weather -> no exclusion, the product warning still says "not above 30 degrees"). Captan and oil: 15 days either way, looking back only.
- Banned = master `ban_status == banned` or an active in `banned_restricted.csv` (any crop, conservative). Off-label: an active that is not an approved apple active (`pydiflumetofen`, `fenpropathrin`, `thiamethoxam` only as FS) or a trade-name alias; applied defensively to master rows and used for history (apple growers only).
- Disabled products (admin) are listed in `excluded` with `disabled_by_admin`, count as not approved (a crop with every row disabled -> `no_approved_data`; `supported_crops()` drops it). The callable is read on every call.
- Not implemented (not in the brief): config `min_days_between_insecticide_and_fungicide` (3), HP point 9 (12-14 day interval), timing `not_needed`.

## Ranking
- Score: infection active (scab risk red, scab only) systemic +30, mixed +15; otherwise contact +30, mixed +15. HP-evaluated brand +10, confidence V +5 / V-s +2, known waiting period +3, each yellow warning -3, proposed-ban extra -17 (so -20 in total, still allowed). Ties by product_id. One row per active ingredient, top 3. Brand examples: product `hp_evaluated_brands`, then `brand_master` group, then `brand_example`; max 4.
- `ProductChoice.use_note` carries the master's `use_note` column (a code such as `curative_or_protectant`), not the free-text `note` column (developer comments).
- `rank_reason` is a plain string in `RuleInput.language`.

## Timing
- `repeat_within_days` (7): the most recent FUNGICIDE spray is within the last 7 days and >= 10 mm of OBSERVED rain fell in the 12 h after it (forecast alone only makes the `rain_washoff` risk yellow). Brief did not limit it to 7 days; a spray older than that cannot be "repeated within 7 days".
- `wait` when `rain_next_12h_mm >= 2.0`; the text names the dry hours the top product needs. Rainfast hours follow `rules_config` (contact 8, **mixed 4**, systemic 2); the brief said "contact/mixed 8", the config value was used.
- Rain sums use `[t0, t0+12h)` like the data scripts.

## Risks
- Scab: wet runs joined when the gap is under 8 h; the Mills row comes from the mean temperature (tolerance 1e-6 against float noise); `reached_at` is the first hour where running wet hours meet the running-mean requirement. **Red** = reached in the last 24 h OR the run ended less than 8 h ago (still joinable); **yellow** = ongoing run with at least 70 % of the need; else green. Forecast hours are never counted as infection. Only inside the primary season; fewer than 24 observed hours -> green with `insufficient_data`.
- S4 note: the data builder computed `threshold_reached_at` (21:00) with the WHOLE run's mean temperature (hindsight); the engine uses the running mean, so it turns red at 18:00 and is red at 21:00 (asserted), green at 12:00.
- Marssonina/Alternaria: only complete 24-hour days, from 1 June, mean temp > 20 and mean RH >= 70, 5 consecutive days = red, 3-4 = yellow. The config text "with >= 6 h leaf wetness on rain days" is not applied (the data scripts do not either).
- Late blight: NIPHM 168-hour window ending now; red when both counts are met, yellow at 80 % of both; with less than 90 % of the 168 hours and the rule not met -> green with `insufficient_data`. Only for farmers who grow potato or tomato. At the S7 clock (08:00) the rule is already true (163 and 95 h).
- Rain wash-off: any non-nutrient spray in the last 24 h (any crop); red on observed rain >= 10 mm in the 12 h after it, yellow with forecast, green otherwise; no item when there was no recent spray.
- `RiskItem.detail` is JSON-safe (ISO strings) and carries `weather_stale`.

## Warnings: code catalogue
`PROPOSED_BAN, NO_WAITING_PERIOD, DOSE_PER_200L, DODINE_RESTRICTIONS, CAPTAN_OIL_INFO` (per product); `NO_TANK_MIX, STALE_HISTORY, OFF_LABEL_HISTORY, TANK_MIX_HISTORY, ROTATION_LIMIT (params.kind: dmi, qoi, sdhi, qoi_solo, same_active, same_frac, same_frac_no_alternative), HARVEST_DATE_UNKNOWN, NEAR_HARVEST` (output); `check_spray` adds `OFF_LABEL_PRODUCT, BANNED_PRODUCT, WAITING_PERIOD_EXCEEDS_HARVEST, CAPTAN_OIL_GAP`.
- STALE_HISTORY: no non-nutrient spray in 60 days while in season (apple: from silver tip to post-harvest + 30 days; other crops March-October); no record at all also warns (`STALE_HISTORY_NONE` wording).
- TANK_MIX_HISTORY looks back 30 days and needs a nutrient row on the same calendar day as a fungicide; the data cannot tell a tank mix from separate sprays, so the wording says "logged the same day".
- `check_spray`: limits are reported when the new entry REACHES the limit (yellow) or EXCEEDS it (red, `params.exceeded`).
- S5 expectation "never recommended": none of the three off-label actives exists in the master, and the sweep test also asserts it with the widest policy.

## Data inconsistencies met (scenarios vs rules)
- S6 expects Marssonina/Alternaria advice with non-DMI options; by policy that is expert_review unless `RULES_AUTO_ADVICE_DISEASES` is widened (both are tested).
- S7 expects mancozeb again; HP rule 3 (never repeat the same chemical) excludes it (mancozeb was used 13 days earlier) and the default policy sends potato to the expert anyway.
- S8 expects whitefly products; policy gives no products for a no-cure virus.
- S10 facts say 73 days stale (counted from a 5 Aug cut-off); the farmer's real last spray is 12 Jul (97 days).

## Hindi (all draft, native review needed)
Product-name placeholders render the Hindi active name when the master has one. Wording follows the VOICE agent (`खेती के जानकार` for expert, `छिड़काव`, `दवा`). Check: the DMI/QoI/SDHI sentences keep "FRAC 3 / 11 / 7" in Latin letters; "डीएमआई, क्यूओआई, एसडीएचआई" are transliterations of group names a farmer will not know; `मंज़ूर`, `अनुमति`, `रोक` for approved/allowed/banned; units spelled out ("मिलीमीटर", "लीटर").

## For integration
- Wire: `build_rules_engine(settings, disabled_products=lambda: set(...))`. Reference data is cached per `data_dir`; call `app.rules.data.clear_cache()` if the data files change at runtime (the admin switch needs no reload).
- Weather snapshot conventions the engine accepts: observed rows are `time <= now` (the row at `now` included), forecast rows `time > now`, hourly, naive times taken as IST. `rain_next_12h_mm` is read from the snapshot as given.
- History: pass every Zoho row up to now; self/advisor duplicates and unresolved product ids are handled. `SprayRecord.category` may be None.
