# -*- coding: utf-8 -*-
"""Try ChatGPT (OpenAI vision) on the apple photo test set. Settings come from FarmTrack/.env (key and model name).

  python run_llm_vision.py --dry-run     check .env, photos, schema and the request; sends NOTHING
  python run_llm_vision.py --limit 2     try 2 photos first (a few requests)
  python run_llm_vision.py               all photos x 3 variants (about 84 requests, about 17 cents with gpt-4o-mini)
  python run_llm_vision.py --selftest    exercise the scoring/report code with FAKE answers (no key, no internet)

Variants (the true label is never sent):
  closed  photo + the project's own symptom descriptions; choose from a fixed list
  open    photo only; free-text answer (does it know Marssonina without being told?)
  hybrid  photo + the vision model B's top-3 as a hint; tests the idea "LLM on top of the vision model"

PRIVACY: the photos in this test set are web images, not client photos. Do NOT run this on client photos without their permission,
because the photos are uploaded to OpenAI. Requests use store=false so OpenAI does not keep the responses for later retrieval.
"""
import argparse, base64, collections, csv, datetime, json, os, pathlib, platform, random, re, sys, time, urllib.error, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent
ROOT = DATA.parent
IMG = DATA / "images"
API_URL = "https://api.openai.com/v1/responses"
PRICES_PER_M = {"gpt-4o-mini": (0.15, 0.60), "gpt-6-luna": (0.10, 0.50)}   # input, output USD per 1M tokens (OpenAI model pages, 19 Oct 2026)


def load_env(path):
    vals = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            else:
                v = v.split(" #")[0].strip()
            vals[k.strip()] = v
    return vals


ENV_FILE = ROOT / ".env"
for _k, _v in load_env(ENV_FILE).items():
    os.environ.setdefault(_k, _v)
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DETAIL = os.environ.get("OPENAI_IMAGE_DETAIL", "high")
TEMPERATURE = os.environ.get("OPENAI_TEMPERATURE", "0")
MAX_OUT = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "1200") or 1200)


def key_status():
    k = os.environ.get("OPENAI_API_KEY", "")
    if not k or k.startswith("your-") or "here" in k:
        return None, "NOT SET: open FarmTrack\\.env and replace the placeholder after OPENAI_API_KEY="
    return k, f"found (length {len(k)}, not shown)"


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


CATALOGUE = {r["disease_id"]: r for r in read_csv(DATA / "reference" / "disease_catalogue.csv")}
OPTIONS = [("scab", "Apple___Apple_scab"), ("alternaria_leaf_spot", "Apple___Alternaria_leaf_spot"), ("marssonina_blotch", "Apple___Marssonina_blotch"),
           ("powdery_mildew", "Apple___Powdery_mildew"), ("rust", "Apple___Cedar_apple_rust"), ("frogeye_black_rot", "Apple___Black_rot"),
           ("healthy", "Apple___healthy"), ("other_or_unclear", None)]
OPT2CANON = dict(OPTIONS)
OPT_NAMES = [o for o, _ in OPTIONS]
SHORT = lambda c: (c or "OTHER").replace("Apple___", "")


def option_text():
    lines = []
    for name, cid in OPTIONS:
        if cid and cid in CATALOGUE and CATALOGUE[cid]["symptoms"]:
            desc = re.sub(r"\s*\([^)]*\)", "", CATALOGUE[cid]["symptoms"])   # drop notes like "(North American disease)" so the test is neutral
        elif name == "healthy":
            desc = "no spots or lesions; evenly green leaf"
        else:
            desc = "anything else, or you cannot tell"
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- prompts and schemas
CHOICE = {"type": "object", "additionalProperties": False, "required": ["disease", "probability", "reason"],
          "properties": {"disease": {"type": "string", "enum": OPT_NAMES}, "probability": {"type": "number"}, "reason": {"type": "string"}}}
SUBJECT = {"type": "string", "enum": ["single_leaf", "leaves_on_branch", "fruit", "several_panels_or_collage", "other"]}
CLOSED_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["subject", "usable_photo", "symptoms", "first_choice", "second_choice", "third_choice", "should_ask_expert"],
                 "properties": {"subject": SUBJECT, "usable_photo": {"type": "boolean"}, "symptoms": {"type": "string"},
                                "first_choice": CHOICE, "second_choice": CHOICE, "third_choice": CHOICE, "should_ask_expert": {"type": "boolean"}}}
OPEN_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["subject", "symptoms", "most_likely_disease", "other_possibilities", "confidence", "should_ask_expert"],
               "properties": {"subject": SUBJECT, "symptoms": {"type": "string"}, "most_likely_disease": {"type": "string"},
                              "other_possibilities": {"type": "array", "items": {"type": "string"}}, "confidence": {"type": "number"}, "should_ask_expert": {"type": "boolean"}}}

INTRO = ("This photo comes from an apple orchard in Himachal Pradesh, India. You are helping an agronomist. "
         "Use only what you can see in the photo; no other information is available. ")
CLOSED_TEXT = (INTRO + "First say what the photo shows. Then describe the visible symptoms precisely: colour of the spots, their shape and border, any halo, "
               "the yellowing pattern (for example green islands inside yellow areas), velvety texture, concentric rings, tiny black dots. "
               "Then rank your three most likely diagnoses from this closed list, each with a probability between 0 and 1 (the three probabilities must not add up to more than 1):\n"
               "{options}\n"
               "Choose healthy only if no symptoms are visible. If the photo is not a clear single apple leaf (for example fruit, several panels, or too blurry), say so, and still give your best ranking. "
               "If you cannot tell, choose other_or_unclear with a high probability and set should_ask_expert to true.")
OPEN_TEXT = (INTRO + "First say what the photo shows. Then describe the visible symptoms precisely. Then name, in plain words, the single most likely disease or problem "
             "(or write 'unclear'), list other possibilities, and give your confidence between 0 and 1. Set should_ask_expert to true if an expert should look.")
HYBRID_TEXT = CLOSED_TEXT + ("\n\nA computer-vision model also looked at this same photo and ranked: {hint}. "
                             "You may agree or disagree; decide from what you see in the photo.")


def build_payload(model, text, schema_name, schema, image_path, extras):
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    payload = {"model": model,
               "input": [{"role": "user", "content": [{"type": "input_text", "text": text},
                                                      {"type": "input_image", "image_url": f"data:{mime};base64,{b64}", "detail": DETAIL}]}],
               "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
               "max_output_tokens": MAX_OUT, "store": False}
    if TEMPERATURE not in ("", "none"):
        payload["temperature"] = float(TEMPERATURE)
    payload.update(extras or {})
    return payload


def call_api(payload, key, retries=5):
    dropped = []
    for attempt in range(retries + 1):
        req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8")), dropped
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(body).get("error", {})
            except Exception:
                err = {}
            param = err.get("param")
            if e.code == 400 and err.get("code") in ("unsupported_parameter", "unknown_parameter", "unsupported_value") and param in payload and param not in ("model", "input", "text"):
                dropped.append(param)
                payload.pop(param)          # e.g. temperature on a model that does not accept it
                continue
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            raise RuntimeError(f"OpenAI API error {e.code}: {body[:800]}")
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error: {e}")
    raise RuntimeError("Too many retries")


def extract(resp):
    if resp.get("status") not in (None, "completed"):
        raise RuntimeError(f"response status {resp.get('status')}: {resp.get('incomplete_details')}")
    text = "".join(c.get("text", "") for it in resp.get("output", []) if it.get("type") == "message" for c in it.get("content", []) if c.get("type") == "output_text")
    refusal = [c.get("refusal") for it in resp.get("output", []) if it.get("type") == "message" for c in it.get("content", []) if c.get("type") == "refusal"]
    if not text:
        raise RuntimeError(f"no text in response (refusal={refusal})")
    u = resp.get("usage", {}) or {}
    return json.loads(text), int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0), int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)


# --------------------------------------------------------------------------------------------- data
def load_rows(limit=None):
    rows = [r for r in read_csv(IMG / "labels.csv") if r["set"] in ("leaf_test", "fruit_info")]
    return rows[:limit] if limit else rows


def latest_cv_run():
    best, n = None, 0
    for p in (HERE / "results").glob("run_*/predictions.csv"):
        c = sum(1 for _ in open(p, encoding="utf-8-sig"))
        if c > n:
            best, n = p, c
    return best


def cv_hints(path):
    """model B, default preprocessing, apple-only -> {photo: [(name, prob)...]} and exact/lenient flags."""
    hints, ref = {}, {}
    if not path:
        return hints, ref
    for r in read_csv(path):
        if r["model"] == "B" and r["preprocessing"] == "default" and r["classes"] == "apple_only":
            hints[r["photo"]] = [(r["top1"], float(r["p1"])), (r["top2"], float(r["p2"])), (r["top3"], float(r["p3"]))]
            ref[r["photo"]] = (r["exact"] == "1", r["lenient"] == "1", r["top1"])
    return hints, ref


NICE = {"Apple___Apple_scab": "apple scab", "Apple___Apple_scab_rust": "apple scab & rust", "Apple___Gray_spot": "gray spot", "Apple___Brown_spot": "brown spot",
        "Apple___Alternaria_leaf_spot": "Alternaria leaf spot", "Apple___healthy": "healthy", "Apple___Marssonina_blotch": "Marssonina blotch", "Apple___Root_rot_collar_rot": "root rot / collar rot"}


def hint_text(h):
    return "; ".join(f"{i + 1}) {NICE.get(l, l)} ({p:.2f})" for i, (l, p) in enumerate(h))


KEYWORDS = {"Apple___Apple_scab": ["scab", "venturia"], "Apple___Alternaria_leaf_spot": ["alternaria"], "Apple___Marssonina_blotch": ["marssonina", "diplocarpon", "apple blotch"],
            "Apple___Powdery_mildew": ["powdery"], "Apple___Cedar_apple_rust": ["rust"], "Apple___Black_rot": ["frogeye", "frog-eye", "black rot", "botryosphaeria"],
            "Apple___healthy": ["healthy"]}
def open_match(text):
    t = (text or "").lower()
    return {c for c, ks in KEYWORDS.items() if any(k in t for k in ks)}


# --------------------------------------------------------------------------------------------- analysis
def pct(a, b):
    return "n/a" if b == 0 else f"{a}/{b} = {100 * a / b:.0f}%"


def md(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def auc(good, bad):
    if not good or not bad:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in good for b in bad) / (len(good) * len(bad))


def score_closed(rows, res):
    out = []
    for r in rows:
        o = res.get(r["filename"])
        if not o:
            continue
        ch = [o["first_choice"], o["second_choice"], o["third_choice"]]
        canon = [OPT2CANON[c["disease"]] for c in ch]
        t = r["label"]
        out.append(dict(row=r, o=o, pred=canon[0], p1=float(ch[0]["probability"]), exact=canon[0] == t, in3=t in canon, canon=canon, ch=ch))
    return out


def variant_section(vname, rows, res, cv_ref):
    leaf = [r for r in rows if r["set"] == "leaf_test"]
    fruit = [r for r in rows if r["set"] == "fruit_info"]
    L = [f"## Variant: {vname}", ""]
    errs = [r["filename"] for r in rows if r["filename"] not in res]
    if errs:
        L += [f"_{len(errs)} photos have no answer (see console errors)._", ""]
    if vname == "open":
        tab, details = [], []
        for c in sorted({r["label"] for r in leaf}):
            rs = [r for r in leaf if r["label"] == c and r["filename"] in res]
            top1 = sum(c in open_match(res[r["filename"]]["most_likely_disease"]) for r in rs)
            anyk = sum(c in open_match(res[r["filename"]]["most_likely_disease"] + " " + " ".join(res[r["filename"]]["other_possibilities"])) for r in rs)
            tab.append([SHORT(c), len(rs), pct(top1, len(rs)), pct(anyk, len(rs))])
        for r in leaf:
            o = res.get(r["filename"])
            if o:
                details.append([r["filename"].split("/")[-1], SHORT(r["label"]), r["label_doubt"], o["most_likely_disease"][:60], "; ".join(o["other_possibilities"])[:70],
                                f"{o['confidence']:.2f}", "yes" if r["label"] in open_match(o["most_likely_disease"]) else "NO"])
        L += ["Free-text answers matched to a disease by keyword (the table below shows the raw text so you can judge).", "",
              md(["True disease", "n", "Named as most likely", "Named anywhere in its list"], tab), "",
              md(["Photo", "True", "Doubt", "Most likely (its words)", "Others", "Conf.", "Right?"], details), ""]
        return "\n".join(L)
    sc = score_closed(leaf, res)
    rel = [s for s in sc if s["row"]["label_doubt"] in ("none", "low")]
    tab = []
    for c in sorted({r["label"] for r in leaf}):
        s = [x for x in sc if x["row"]["label"] == c]
        tab.append([SHORT(c), len(s), pct(sum(x["exact"] for x in s), len(s)), pct(sum(x["in3"] for x in s), len(s)), f"{sum(x['p1'] for x in s) / max(len(s), 1):.2f}"])
    for nm, s in (("**all leaf photos**", sc), ("**reliable labels only**", rel)):
        tab.append([nm, len(s), pct(sum(x["exact"] for x in s), len(s)), pct(sum(x["in3"] for x in s), len(s)), f"{sum(x['p1'] for x in s) / max(len(s), 1):.2f}"])
    L += [md(["True disease", "n", "Top-1 correct", "In its top 3", "Mean stated probability"], tab), ""]
    dist = [[SHORT(c), "; ".join(f"{SHORT(k)} x{v}" for k, v in collections.Counter(x["pred"] for x in sc if x["row"]["label"] == c).most_common())] for c in sorted({r["label"] for r in leaf})]
    L += ["**What it answers for each true disease:**\n", md(["True disease", "Answers"], dist), ""]
    good = [x["p1"] for x in sc if x["exact"]]
    bad = [x["p1"] for x in sc if not x["exact"]]
    a = auc(good, bad)
    L.append(f"**Does its stated probability separate right from wrong?** Mean when right {sum(good) / max(len(good), 1):.2f} (n={len(good)}), when wrong {sum(bad) / max(len(bad), 1):.2f} (n={len(bad)}); "
             f"chance that a right answer is more confident than a wrong one: {'n/a' if a is None else f'{a:.2f}'} (0.50 = tells nothing).\n")
    cw = [x for x in sc if (not x["exact"]) and x["p1"] >= 0.45]
    L.append(f"**Confidently wrong (stated probability >= 0.45 and wrong): {len(cw)} of {len(sc)}**\n")
    ask = [x for x in sc if x["o"]["should_ask_expert"] or x["ch"][0]["disease"] == "other_or_unclear"]
    L.append(f"**Asked for an expert / said unclear:** {len(ask)} of {len(sc)} photos; among those, it would have been wrong anyway on {sum(not x['exact'] for x in ask)}. "
             f"Among the {len(sc) - len(ask)} it answered without flagging, {sum(x['exact'] for x in sc if x not in ask)} were right.\n")
    if vname == "hybrid" and cv_ref:
        followed = [x for x in sc if x["row"]["filename"] in cv_ref and x["canon"][0] == {"Apple___Apple_scab_rust": "Apple___Apple_scab", "Apple___Brown_spot": "Apple___Marssonina_blotch"}.get(cv_ref[x["row"]["filename"]][2], cv_ref[x["row"]["filename"]][2])]
        rescued = [x for x in sc if x["row"]["filename"] in cv_ref and (not cv_ref[x["row"]["filename"]][1]) and x["exact"]]
        broken = [x for x in sc if x["row"]["filename"] in cv_ref and cv_ref[x["row"]["filename"]][1] and not x["exact"]]
        L += [f"**Effect of the vision model's hint:** it agreed with the vision model's first choice on {len(followed)} of {len(sc)} photos; "
              f"it fixed {len(rescued)} photos the vision model got wrong and broke {len(broken)} that the vision model got right (lenient scoring for the vision model).\n"]
    L += ["**Every leaf photo:**\n", md(["Photo", "True", "Doubt", "Subject it saw", "1st (p)", "2nd (p)", "3rd (p)", "Right?"],
          [[x["row"]["filename"].split("/")[-1], SHORT(x["row"]["label"]), x["row"]["label_doubt"], x["o"]["subject"],
            f"{x['ch'][0]['disease']} ({x['ch'][0]['probability']:.2f})", f"{x['ch'][1]['disease']} ({x['ch'][1]['probability']:.2f})", f"{x['ch'][2]['disease']} ({x['ch'][2]['probability']:.2f})",
            "yes" if x["exact"] else "NO"] for x in sc]), ""]
    if fruit:
        fs = score_closed(fruit, res)
        L.append(f"**Fruit photos (true disease: scab):** it called {sum(x['exact'] for x in fs)} of {len(fs)} scab; subject recognised as fruit in {sum(x['o']['subject'] == 'fruit' for x in fs)}.\n")
    return "\n".join(L)


def build_report(rows, allres, usage, model, selftest, cv_path, cv_ref):
    leaf = [r for r in rows if r["set"] == "leaf_test"]
    L = []
    if selftest:
        L += ["# SELFTEST: FAKE ANSWERS. THESE NUMBERS MEAN NOTHING.", ""]
    L += ["# ChatGPT photo analysis report", "", f"Run: {datetime.datetime.now():%Y-%m-%d %H:%M} | model: **{model}** | image detail: {DETAIL} | photos: {len(leaf)} leaf + {len(rows) - len(leaf)} fruit", "",
          "## Read this first", "",
          "- **Same caveats as the vision test:** web images, labels not agronomist-confirmed, tiny n (one photo moves a disease by 9 to 25 points), so this is directional only.",
          "- **Answers from a language model vary from run to run.** One run is one sample; repeat before drawing conclusions.",
          "- **The true label was never sent.** The `closed` variant gives it the project's own symptom descriptions (like RAG); `open` gives nothing; `hybrid` adds the vision model's top 3.",
          "- **The model's stated probability is its own claim, not a measured accuracy.**", ""]
    for v, res in allres.items():
        L += [variant_section(v, rows, res, cv_ref), ""]
    # comparison with the vision model
    if cv_path:
        L += ["## Side by side with the vision model B (same photos)", ""]
        comp = []
        for c in sorted({r["label"] for r in leaf}):
            rs = [r for r in leaf if r["label"] == c and r["filename"] in cv_ref]
            row = [SHORT(c), len(rs), pct(sum(cv_ref[r["filename"]][0] for r in rs), len(rs)), pct(sum(cv_ref[r["filename"]][1] for r in rs), len(rs))]
            for v in ("closed", "hybrid"):
                if v in allres:
                    s = [x for x in score_closed(leaf, allres[v]) if x["row"]["label"] == c]
                    row.append(pct(sum(x["exact"] for x in s), len(s)))
                else:
                    row.append("not run")
            comp.append(row)
        L += [md(["True disease", "n", "Vision B exact", "Vision B lenient*", "ChatGPT closed", "ChatGPT hybrid"], comp), "",
              "*lenient counts Brown spot as Marssonina and Scab & Rust as Scab (inferred aliases).", ""]
    tin = sum(u[0] for u in usage); tout = sum(u[1] for u in usage)
    pr = PRICES_PER_M.get(model)
    cost = f"about ${tin / 1e6 * pr[0] + tout / 1e6 * pr[1]:.3f}" if pr else "unknown for this model (set prices in the script)"
    L += ["## Cost of this run", "", f"{len(usage)} requests, {tin:,} input tokens, {tout:,} output tokens: {cost}.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------------------------- main
def fake_answer(variant, r, rnd):
    t = [c for c, k in OPTIONS if k == r["label"]][0]
    names = OPT_NAMES[:]
    rnd.shuffle(names)
    first = t if rnd.random() < 0.5 else names[0]
    ch = [dict(disease=first, probability=round(rnd.uniform(.4, .95), 2), reason="fake"), dict(disease=names[1], probability=.1, reason="fake"), dict(disease=names[2], probability=.05, reason="fake")]
    if variant == "open":
        nm = {"scab": "apple scab", "alternaria_leaf_spot": "Alternaria leaf spot", "marssonina_blotch": "Marssonina blotch"}.get(first, "unclear")
        return dict(subject="single_leaf", symptoms="fake", most_likely_disease=nm, other_possibilities=["apple scab"], confidence=round(rnd.uniform(.4, .9), 2), should_ask_expert=rnd.random() < .3)
    return dict(subject="fruit" if r["set"] == "fruit_info" else "single_leaf", usable_photo=True, symptoms="fake", first_choice=ch[0], second_choice=ch[1], third_choice=ch[2], should_ask_expert=rnd.random() < .3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--variants", nargs="+", default=["closed", "open", "hybrid"], choices=["closed", "open", "hybrid"])
    ap.add_argument("--cv-run", help="path to a model_test results/run_*/predictions.csv used for the hybrid hint")
    args = ap.parse_args()

    rows = load_rows(args.limit)
    cv_path = pathlib.Path(args.cv_run) if args.cv_run else latest_cv_run()
    hints, cv_ref = cv_hints(cv_path)
    key, kstat = key_status()
    print(f".env file : {ENV_FILE} ({'found' if ENV_FILE.exists() else 'MISSING'})")
    print(f"api key   : {kstat}")
    print(f"model     : {MODEL}   image detail: {DETAIL}   temperature: {TEMPERATURE}   max output tokens: {MAX_OUT}")
    print(f"photos    : {len(rows)} ({sum(r['set'] == 'leaf_test' for r in rows)} leaf, {sum(r['set'] == 'fruit_info' for r in rows)} fruit)")
    print(f"hybrid hint from vision run: {cv_path if cv_path else 'NONE (hybrid will be skipped)'}")
    if "hybrid" in args.variants and not hints:
        args.variants = [v for v in args.variants if v != "hybrid"]

    def make(variant, r):
        path = IMG / r["filename"]
        if variant == "closed":
            return build_payload(MODEL, CLOSED_TEXT.format(options=option_text()), "closed_diagnosis", CLOSED_SCHEMA, path, None)
        if variant == "open":
            return build_payload(MODEL, OPEN_TEXT, "open_diagnosis", OPEN_SCHEMA, path, None)
        return build_payload(MODEL, HYBRID_TEXT.format(options=option_text(), hint=hint_text(hints[r["filename"]])), "hybrid_diagnosis", CLOSED_SCHEMA, path, None)

    if args.dry_run:
        for v in args.variants:
            p = make(v, rows[0])
            shown = json.loads(json.dumps(p))
            shown["input"][0]["content"][1]["image_url"] = shown["input"][0]["content"][1]["image_url"][:40] + "...(image data hidden)"
            print(f"\n--- request preview, variant '{v}', photo {rows[0]['filename']} ({len(json.dumps(p)) / 1024:.0f} KB total) ---")
            print(json.dumps(shown, indent=1, ensure_ascii=False)[:3200])
        print("\nNothing was sent. READY." if key else "\nNothing was sent. NOT READY: set OPENAI_API_KEY in .env first.")
        sys.exit(0 if key else 1)

    if not key and not args.selftest:
        sys.exit("OPENAI_API_KEY is not set. Open FarmTrack\\.env, replace the placeholder, save, and run again.")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HERE / "results" / (("llm_selftest_" if args.selftest else f"llm_{MODEL}_") + stamp)
    out.mkdir(parents=True, exist_ok=True)
    allres, usage, raw = {}, [], open(out / "responses.jsonl", "w", encoding="utf-8")
    rnd = random.Random(7)
    for v in args.variants:
        allres[v] = {}
        print(f"\n=== variant {v} ===")
        for i, r in enumerate(rows, 1):
            try:
                if args.selftest:
                    ans, tin, tout = fake_answer(v, r, rnd), 1000, 300
                else:
                    resp, dropped = call_api(make(v, r), key)
                    ans, tin, tout = extract(resp)
                    if dropped and i == 1:
                        print(f"  note: this model did not accept {dropped}; the script dropped it")
                allres[v][r["filename"]] = ans
                usage.append((tin, tout))
                raw.write(json.dumps(dict(variant=v, photo=r["filename"], answer=ans, in_tokens=tin, out_tokens=tout), ensure_ascii=False) + "\n")
                print(f"  {i:2d}/{len(rows)} {r['filename'].split('/')[-1]:14s} ok")
            except Exception as e:
                print(f"  {i:2d}/{len(rows)} {r['filename'].split('/')[-1]:14s} FAILED: {e}")
                if i == 1 and not args.selftest:
                    print("\nThe first request failed. Copy this message (it contains no key) and send it to me; stopping to avoid wasting requests.")
                    sys.exit(1)
            if not args.selftest:
                time.sleep(0.3)
    raw.close()
    (out / "report.md").write_text(build_report(rows, allres, usage, MODEL, args.selftest, cv_path, cv_ref), encoding="utf-8")
    with open(out / "predictions.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "photo", "set", "true_label", "label_doubt", "answer_json"])
        for v, res in allres.items():
            for r in rows:
                if r["filename"] in res:
                    w.writerow([v, r["filename"], r["set"], r["label"], r["label_doubt"], json.dumps(res[r["filename"]], ensure_ascii=False)])
    print(f"\nWrote {out / 'report.md'}\n      {out / 'predictions.csv'}\n      {out / 'responses.jsonl'}")


if __name__ == "__main__":
    main()
