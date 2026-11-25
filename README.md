# Read-It-For-Me

A web app for blind, low-vision and low-literacy users in Khyber Pakhtunkhwa, Pakistan.
Photograph a **medicine label**, a **utility bill**, or an **official notice** — the app
reads the document, explains it in simple words, and **reads the result aloud** in
**Urdu (default), Pashto, or English**. Audio plays automatically after processing.

Built for a one-day buildathon: working end-to-end demo first, polish second.

## How it works

```
photo (camera / gallery)
  -> client-side compression (canvas, max 1600 px, JPEG 0.8)
  -> POST /api/analyze  (FastAPI: EXIF fix + resize + vision model)
  -> validated JSON result (Pydantic contract, safety rules enforced in code)
  -> page renders the result + POST /api/speak (edge-tts) -> audio auto-plays
  -> if server TTS fails, the browser's speechSynthesis takes over
```

- **Vision + language model:** a Qwen vision-language model (Qwen2.5-VL / Qwen3-VL)
  behind any OpenAI-compatible chat-completions endpoint — DashScope, a Hugging Face
  endpoint, or a local vLLM/Ollama server. The hosted demo routes the same call through
  a small Gemini bridge (see "Hosted demo" below) because the Gemini key lives in a
  secure vault that the hosting platform cannot read.
- **TTS:** `edge-tts` server-side (ur-PK-UzmaNeural, ur-PK-AsadNeural,
  ps-AF-LatifaNeural, ps-AF-GulNawazNeural, en-US-JennyNeural — confirmed at startup,
  graceful fallback). Audio is cached in memory by hash of (text, voice).
- **Privacy:** images and extracted text are processed in memory and discarded.
  Logs contain only request id, doc_type, latency and status code.

## Setup

```bash
cd read-it-for-me
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your endpoint + key
```

`.env`:

```
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
API_KEY=your-api-key-here
MODEL=qwen2.5-vl-72b-instruct
DEFAULT_LANG=ur
```

### Switching the Qwen endpoint

Only the three env vars change — no code edits:

| Target | BASE_URL | MODEL |
|---|---|---|
| DashScope (Qwen cloud) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen2.5-vl-72b-instruct` |
| Local vLLM | `http://localhost:8000/v1` | your served model name |
| Local Ollama | `http://localhost:11434/v1` | `qwen2.5vl` |
| Gemini (OpenAI-compatible) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.5-flash` |

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — on a phone on the same network, use the machine's LAN IP
so the camera and audio work in a real browser.

## Tests

```bash
pytest            # schema validation, JSON parsing/repair, safety-line
                  # injection, needs_retake logic (mocked model responses)

python scripts/smoke_test.py --image path/to/photo.jpg --lang ur
python scripts/smoke_test.py --image path/to/bill.jpg --lang ps --base-url https://your-deployment.example
```

## Hosted demo (Vercel + Gemini bridge)

The live deployment is the same FastAPI app on Vercel. Because the Gemini API key is
held in a secure vault (and a vault placeholder stored in Vercel's env is *not* the
key), the deployed app is configured with:

```
VISION_BRIDGE_URL=https://<existing ngrok domain>/webhook/readit-analyze
VISION_BRIDGE_TOKEN=<shared secret>
```

An n8n webhook workflow ("ReadIt Bridge") forwards that path to
`scripts/bridge_proxy.py` running next to the vault (port 5682), which calls
Gemini `gemini-3.5-flash` and returns the raw model text. The app then runs the
identical parsing, validation and safety pipeline as the Qwen path. If you have
your own key, skip the bridge entirely and set `BASE_URL` / `API_KEY` / `MODEL`.

## Manual test checklist

For each item: take the photo in the app, listen to the full spoken result, and
check the key facts on screen against the paper.

- [ ] **Medicine strip** (e.g. paracetamol): name + strength read correctly, expiry
      spoken, fixed line "confirm with a pharmacist or doctor" appended, no dose
      invented that is not printed.
- [ ] **Electricity bill** (PESCO): amount due and due date first, consumer number
      correct, late-fee warning only if printed.
- [ ] **Government notice**: sender, what is asked, and the deadline read correctly.
- [ ] **Blurry photo**: app refuses to guess, speaks the retake hint, offers a retake.
- [ ] **Dark photo**: same retake behaviour with a "more light" hint.
- [ ] **Non-document photo** (e.g. a face / a wall): doc_type "unreadable", retake hint.
- [ ] **Each language**: repeat the medicine test in اردو, پښتو and English — the
      explanation, the spoken script and the safety line are all in the chosen language.
- [ ] **No-sight pass**: with a screen reader (TalkBack/VoiceOver), complete the whole
      flow by touch/keyboard alone: language -> photo -> result -> repeat -> key facts only.

## Demo script (2 minutes, for judges)

1. **(0:00) The problem.** "In Khyber Pakhtunkhwa, a blind grandmother gets a medicine
   strip and an electricity bill she cannot read. This app reads both for her — in her
   own language." Open the app; the welcome is already speaking in Urdu.
2. **(0:20) Medicine.** Hold a paracetamol strip under the phone, tap the one huge
   button (it fills a third of the screen — no aiming at small targets). The app says
   "Reading your document, please wait", then reads: the name, the strength, the expiry —
   and ends with "Please confirm with a pharmacist or doctor." Point out: it did **not**
   invent a dose, because the pack does not print one.
3. **(0:50) Bill in Pashto.** Tap پښتو — the app speaks its own name in Pashto.
   Photograph a PESCO bill. It reads the amount and the last date first, in simple
   everyday Pashto.
4. **(1:15) Bad photo.** Deliberately shake a blurry photo. The app refuses to guess:
   it speaks "Hold the phone about 20 cm above the paper and keep it steady" and waits
   for a retake. "It never makes up a number."
5. **(1:35) Controls.** Show Repeat, Slower, and "Key facts only" — all large, all
   labelled, all working without sight. Close: "One photo, three languages, zero reading
   required — and nothing is stored."

## Safety rules (prompt *and* code)

- Read only what is printed; never invent a dose, schedule, price, date or instruction.
  Unclear items are reported as "not clearly visible" in the user's language.
- Medicine: the fixed pharmacist/doctor line is appended **in code** to every spoken
  medicine result, in the user's language.
- Confidence < 0.6 or image quality ≠ good ⇒ `needs_retake = true` and the app speaks
  the retake hint instead of guessing.
- Bills/notices: facts and deadlines only — no legal or financial advice.
- Per-IP in-memory rate limit; CORS locked to same origin; 8 MB image cap;
  JPEG/PNG/WebP only; 30 s model timeout, 15 s TTS timeout, one retry with backoff.

## Known limitations (honest)

- **Pashto OCR accuracy** is the weakest link. Qwen/Gemini-class VLMs read printed
  Urdu and English well, but printed Pashto — especially Nastaliq-style fonts,
  low-quality photocopies and mixed Pashto/English forms — produces more errors,
  and there is little Pashto document data in any public benchmark. Numbers and
  dates should be double-checked against the paper by a sighted person when money
  or medicine depends on them.
- **Pashto TTS voice quality:** the edge-tts Pashto voices (ps-AF-*) are Afghan
  Pashto voices; pronunciation and accent differ from KP Pashto, and quality is
  noticeably below the Urdu and English voices. If a device has no Pashto voice
  at all, the app says so in spoken English and shows the text.
- **Handwritten text** is largely unsupported: neat printed handwriting sometimes
  reads, cursive Urdu/Pashto handwriting usually does not. The app is designed to
  ask for a retake rather than guess.
- The vision model can still misread a clear photo occasionally; the confidence /
  quality gates reduce, but do not eliminate, wrong readings. The verbatim
  "original text" section is shown so a sighted helper can verify.
- Server TTS needs internet access to Microsoft's speech service; offline, the
  browser fallback is the only voice.
- The hosted demo's vision bridge depends on the bridge machine + tunnel being up;
  self-hosting with your own `BASE_URL`/`API_KEY` removes that dependency.

## Project layout

```
read-it-for-me/
  app/        FastAPI app: main, config, vision, tts, schemas, prompts
  static/     single-page app (plain HTML/CSS/JS, no build step)
  tests/      pytest unit tests
  scripts/    smoke_test.py, bridge_proxy.py
  .env.example, requirements.txt, README.md
```
