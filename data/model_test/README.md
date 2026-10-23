# Model test: step by step

Goal: run the two pretrained models on the photo test set (`data/images/testset_v1`) and see how well they do. **No training happens in these steps.** Photos never leave your machine; only the model files are downloaded from huggingface.co (once).

| Model | What it is | Why we test it |
|---|---|---|
| **A** `neghani/plantvillage-mobilenetv2` | Small phone-sized model, 38 PlantVillage classes (Apple scab but **no** Alternaria or Marssonina) | Candidate for the offline, on-device check |
| **B** `ixrbhii/apple-disease-convnext` | Larger server model, 8 apple classes (includes Marssonina and Alternaria) | Candidate for the online check |

## 1. Install (once, about 10 minutes)

Open **PowerShell** and run these one at a time. Python 3.13 is already on this machine.

```powershell
cd C:\siva\Research\FarmTrack\data\model_test
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

- If `Activate.ps1` is blocked, run `Set-ExecutionPolicy -Scope Process Bypass` first, then activate again.
- Roughly 1 to 2 GB of disk (estimate). No GPU needed.
- If `pip install torch` fails on Python 3.13, install Python 3.12 and create the venv with it (`py -3.12 -m venv .venv`).

## 2. Check everything is ready

```powershell
python run_models.py --dry-run
```

It lists the photos and then every package and your connection to huggingface.co. You want to see **READY to run.** If anything says MISSING or PROBLEM, fix that and run it again (or send me the output).

## 3. Quick smoke test (3 photos)

```powershell
python run_models.py --limit 3
```

The first run downloads the models (about 110 MB) and may print warnings; warnings are fine. **If you see `MODEL A FAILED` or `MODEL B FAILED` with a long error, copy all of it and send it to me.** I wrote and syntax-checked this script and tested the scoring code with fake numbers, but I could not run the real models on this machine, so the first real run is the real test of the loading code.

## 4. Full run

```powershell
python run_models.py
```

It takes about a minute or two on a normal CPU (estimate). It writes a new folder `results\run_<date_time>\` containing:

- `report.md`: the review report (open this)
- `predictions.csv`: every answer for every photo
- `run_info.json`: versions used

## 5. What to send me

1. `report.md` and `predictions.csv` from the run folder.
2. Anything odd you noticed.

## 6. What I will check in the report

1. **Does model B name Marssonina and Alternaria?** It is the only model that has these classes.
2. **Is model A confidently wrong?** It has no class for two of the three diseases. If it answers "scab" or "healthy" with high confidence on an Alternaria leaf, that is the strongest argument for our design: crop picker first, a "not sure" cut-off, and a server or expert check.
3. **Do the confidence numbers mean anything?** I compare coverage and precision at each cut-off with the cut-offs in our rules (0.45 show, 0.65 auto-advice) and with model A's own published 0.50.
4. **Does preprocessing matter?** The report scores both the models' default centre-crop and a whole-photo resize. Model B's card says it was trained on resized, uncropped photos, and these are mostly rectangular photos.
5. **Which wrong answers come from doubtful labels?** The report shows the "reliable labels only" score next to the all-photos score.

## 7. Training: my review and recommendation

**Do not train anything now.** Reasons:

1. **There is almost nothing to train on:** 23 leaf photos, and only 1 clearly reliable scab leaf.
2. **The photos are web images with unknown licence.** We should not train on them or ship a model built from them.
3. **The labels are not confirmed by an agronomist.** Training on unconfirmed labels teaches the model the mistakes.
4. **We could not tell improvement from luck.** With 3 to 11 photos per disease, one photo moves a score by 9 to 25 points.

What these photos *are* good for: a first look at how the pretrained models behave (this test).

**When training makes sense (phase 2):**

- **Data:** a few hundred agronomist-confirmed photos per disease taken in the client's own orchards, plus healthy leaves. Apple leaf diseases are seasonal, so realistically this is **March to August 2027**.
- **Split:** by tree or leaf, never by photo, so the test photos are never near-copies of training photos.
- **Extra data to start from:** public field sets with clean licences (PlantDoc, the J&K Indigenous Apple Leaf set, Plant Pathology 2021, AppleLeaf9). No public Marssonina set exists, so only the client's photos can cover it.

**Training options, cheapest first:**

| Option | Needs | Effort |
|---|---|---|
| 1. No training: crop picker, quality check, "not sure" cut-off, expert queue | nothing | **This is the MVP plan** |
| 2. Few-shot matching: compare a new photo with confirmed examples | about 10+ confirmed photos per disease | seconds to run, no real training |
| 3. Light fine-tune of the last layers | a few hundred photos per disease | minutes on a free Colab T4 or RTX 3060 |
| 4. Full fine-tune with augmentation, then compress for the phone | the same, plus time to evaluate | hours; a day or two of work |

**How I will judge the results:** I will not set a numeric pass mark, because with this few photos any pass mark is meaningless. I will look at the pattern: is the right disease usually in the top 3, are the confidence numbers believable, and how often is the model confidently wrong.

| If the report shows... | Then I would... |
|---|---|
| B usually right on the reliable photos, sensible confidence | Keep the pretrained models for the MVP; plan photo collection for phase 2 |
| B right on Marssonina but weak on Alternaria or scab | Rely on the expert queue for those; collect confirmed photos first |
| B often confidently wrong | Test the paid Kindwise API on the same photos; raise phase 2 to the top of the list |
| A confidently wrong on Alternaria and Marssonina | Expected; keep the server check and the crop picker, and never advise from model A alone for those diseases |

---

## 8. ChatGPT photo analysis test (added 19 Oct 2026)

Goal: see whether ChatGPT's vision (GPT-4o-mini by default) can analyse the same photos, alone and "on top of" the vision model. **Nothing needs installing**: the script uses only Python's standard library, so your existing `.venv` is fine.

**Privacy:** the photos in this test set are web images, not client photos, and they are **uploaded to OpenAI** for this test. Do not run it on client photos without the client's permission. Requests use `store=false`.

### Steps

1. Open `C:\siva\Research\FarmTrack\.env` and replace `your-openai-api-key-here` with your key (get one at https://platform.openai.com/api-keys). Save. **Never paste the key into a chat or share this file.**
2. The model name is also in `.env` (`OPENAI_MODEL=gpt-4o-mini`). Change it there to try another model. Note: `gpt-4o-mini-2024-07-18` shuts down on 14 Jan 2027; OpenAI recommends `gpt-6-luna`.
3. In PowerShell:

```powershell
cd C:\siva\Research\FarmTrack\data\model_test
.venv\Scripts\Activate.ps1
python run_llm_vision.py --dry-run        # checks .env and shows the request; sends nothing; should end "READY"
python run_llm_vision.py --limit 2        # tries 2 photos first
python run_llm_vision.py                  # all 28 photos x 3 variants (about 84 requests)
```

If the first request fails, the script stops and prints the error (it never prints your key). Copy that message to me.

### The three variants (the true label is never sent)

| Variant | What ChatGPT gets | What it tests |
|---|---|---|
| `closed` | Photo + the project's own symptom descriptions, choose from a fixed list | "LLM + RAG-style knowledge" as a second opinion |
| `open` | Photo only, free-text answer | Does it know Marssonina without being told? |
| `hybrid` | Photo + the vision model B's top 3 as a hint | Your idea: an LLM on top of the vision model |

### Output and cost

`results\llm_<model>_<date_time>\` with `report.md` (open this), `predictions.csv` and `responses.jsonl`. The report compares ChatGPT with vision model B on the same photos, shows whether its stated probability separates right from wrong, how often it asks for an expert, and (for `hybrid`) how many wrong vision answers it fixed and how many right ones it broke. Cost with gpt-4o-mini: about 17 cents for the full 84-request run (actual, 19 Oct 2026; about $0.002 per photo, because gpt-4o-mini counts about 12,900 input tokens per photo). An earlier estimate of 3 to 5 cents was wrong. The report prints the real token count.

**Caveats:** the same tiny, unconfirmed web-image test set; answers from a language model vary from run to run, so one run is one sample. If you want to check stability, run it twice and send me both reports.
