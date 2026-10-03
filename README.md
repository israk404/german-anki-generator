# German Anki Generator

Generate high-quality Anki flashcards for German vocabulary using Google Gemini, Groq, or any OpenAI-compatible LLM. Produces three card types per word, generates native audio via edge-tts, fetches images from Pixabay, and validates every card with an optional verification pass.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Table of contents

- [What it does](#what-it-does)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Getting API keys](#getting-api-keys)
- [First run](#first-run)
- [Workflow](#workflow)
- [Anki setup](#anki-setup)
- [Card types explained](#card-types-explained)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [License](#license)

---

## What it does

Give it a list of German words. It returns a fully-prepared Anki deck: 31 fields per word, 3 card types, native pronunciation audio, example sentences with translations, images for nouns, and grammar metadata (gender, plural, conjugations, valency). All you do is import one `.txt` file into Anki.

**Input:**
```
Haus, gehen, groß, Guten Morgen
```

**Output:**
- `anki_output/<timestamp>_Haus_gehen_gross.txt` — import this into Anki
- `anki_output/media/*.mp3` — copy these to Anki's `collection.media/` folder
- `anki_output/backups/*.json` — raw data, editable and re-exportable

---

## Features

- **3 card types from one note** — Recognition (DE→EN), Production (EN→DE, typed), Gender Drill (der/die/das)
- **31 structured fields** — grammar, pronunciation, collocations, mnemonics, and more
- **AI generation** — Gemini 3.6 Flash / 3.5 Flash-Lite, Groq (GPT-OSS-120B), or any OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, Ollama, etc.)
- **Optional verification pass** — a second LLM call checks the first one's work with a strict fact-only correction list
- **Native audio** — Microsoft edge-tts, 3 verified German voices
- **Unique audio filenames** — sentence MP3s are hashed so the same word in two decks never collides
- **Pixabay images** — auto-fetched for concrete nouns
- **Multi-key rotation** — add multiple API keys per provider; the app round-robins through them
- **Retry with exponential backoff** — survives rate limits and transient failures
- **Session resume** — close the app, come back, pick up where you left off
- **Modern GUI** — light and dark mode, editable fields, checkbox word picker
- **No cloud dependency for state** — everything saves to local JSON files

---

## Requirements

- **Python 3.10 or newer**
- **Windows, macOS, or Linux**
- **Internet connection** (for AI APIs, edge-tts, and Pixabay)
- **Anki** (desktop) — free download at [apps.ankiweb.net](https://apps.ankiweb.net)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/israk404/german-anki-generator.git
cd german-anki-generator
```

### 2. (Recommended) Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install google-genai groq edge-tts pyperclip pillow
```

| Package | Purpose | Required? |
|---|---|---|
| `google-genai` | Gemini API client | Yes (for Gemini) |
| `groq` | Groq API client | Yes (for Groq) |
| `edge-tts` | Microsoft neural voices for German audio | Yes |
| `pyperclip` | Clipboard paste support | Optional but recommended |
| `pillow` | Image thumbnails in the preview tab | Optional |

The app runs even if some optional packages are missing — you just lose the related features. The startup log tells you what loaded and what didn't.

### 4. Verify the install

```bash
python -m py_compile german_anki_generator.py
```

Silent exit = good. Then launch:

```bash
python german_anki_generator.py
```

---

## Getting API keys

You need at least **one** provider configured. Gemini is the recommended default — it has a generous free tier and excellent German.

### Gemini (recommended, free tier available)

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with a Google account
3. Click **Create API key**
4. Copy the key

**Free tier limits for `gemini-3.6-flash`:**
- 5 requests per minute (RPM)
- 20 requests per day (RPD)
- Resets at midnight Pacific Time (1:00 PM Bangladesh Time)

> Because each word consumes **2 requests** (1 generation + 1 verification), 20 RPD = **10 words per day** per project. For a 500-word batch, either use multiple projects or enable billing.

**Recommended alternative:** `gemini-3.5-flash-lite` has a **500 RPD** free tier — 25× more. Perfect for verification. Use 3.6 Flash for generation and 3.5 Flash-Lite for verification.

### Groq (fast, free tier)

1. Go to [console.groq.com/keys](https://console.groq.com/keys)
2. Sign up or log in
3. Create an API key
4. Copy it

Groq's free tier offers **1,000 RPD** for `openai/gpt-oss-120b` — excellent for bulk generation.

### Custom (OpenAI-compatible)

Any endpoint that speaks `/v1/chat/completions` works:

- **OpenAI** — `https://api.openai.com`
- **DeepSeek** — `https://api.deepseek.com`
- **OpenRouter** — `https://openrouter.ai/api`
- **Together AI** — `https://api.together.xyz`
- **Mistral** — `https://api.mistral.ai`
- **Ollama** (local) — `http://localhost:11434`

You only need a base URL and a model name — the app handles the rest.

### Pixabay (optional, for noun images)

1. Go to [pixabay.com/api/docs](https://pixabay.com/api/docs/)
2. Sign in and copy your free API key
3. Paste it into **Settings → Export → Pixabay images**

---

## First run

When you launch the app for the first time:

1. **Settings tab → API keys** — paste your key(s) for the provider(s) you'll use
2. **Settings tab → Generator** — pick your provider (Gemini is a good default)
3. **Settings tab → Verifier** — check "Enable verification pass" and pick a model
   - **Do not** use a weaker verifier than your generator — it can damage good content
   - Recommended pairing: 3.6 Flash generates, 3.5 Flash-Lite verifies
4. **Settings tab → Audio** — pick a voice (Conrad, Katja, or Amala all work)
5. **Settings tab → Export** — set your deck name and note type name

---

## Workflow

### Step 1 — Enter words

Go to the **Input** tab. Paste or type German words:

```
Haus, gehen, groß, Guten Morgen, die Katze
```

Commas, newlines, or a mix — all work.

### Step 2 — Process

Click **Process words**. The app:
1. Calls your generator model once per word
2. Optionally calls the verifier
3. Fetches a Pixabay image if the word is a noun and images are enabled
4. Saves everything to the session draft

Watch the live log for progress and any corrections the verifier makes.

### Step 3 — Review and edit

Go to the **Preview** tab:
- The **word picker button** opens a checkbox popup — tick or untick words you want to include
- **Double-click any cell** in the field table to edit it inline
- Use the **Filter** dropdown to see only nouns, verbs, adjectives, or phrases
- Click **♪ Word** or **♪ Sentence** to preview audio

### Step 4 — Generate files

Click **Generate files + audio** in the bottom bar. This:
1. Creates `.mp3` files for every word and sentence
2. Writes the `.txt` file for Anki import
3. Writes a JSON backup of the session

Output goes to `anki_output/`.

### Step 5 — Import into Anki

See [Anki setup](#anki-setup) below.

---

## Anki setup

### 1. Create the note type

Open Anki → **Tools → Manage Note Types** → **Add** → **Clone: Basic** → name it `GermanAnki_v8` (or whatever you set in Settings).

Click **Fields…** and add these **31 fields in this exact order**:

```
1.  word_type
2.  target_word
3.  full_answer
4.  english_translation
5.  sense_hint
6.  german_sentence
7.  english_sentence
8.  article
9.  plural
10. genitive
11. plural_only
12. present_3sg
13. preterite
14. past_participle
15. auxiliary
16. separable
17. reflexive
18. valency
19. comparative
20. superlative
21. pronunciation_ipa
22. pronunciation_native
23. memory_tip
24. confusable
25. collocations
26. word_family
27. register
28. image_url
29. notes
30. audio_word
31. audio_sentence
```

Delete the default `Front` and `Back` fields. Save.

### 2. Install the card templates

This repo ships with three card templates and a CSS file in the `templates/` folder (if using them):

- `1-recognition-front.html` / `1-recognition-back.html`
- `2-production-front.html` / `2-production-back.html`
- `3-gender-drill-front.html` / `3-gender-drill-back.html`
- `styling.css`

To install:

1. In **Manage Note Types**, select `GermanAnki_v8`, click **Cards…**
2. Rename **Card 1** to `Recognition` → paste the two recognition `.html` files
3. Add a new card type via **Options → Add Card Type** → rename to `Production` → paste the two production files
4. Add another → rename to `Gender Drill` → paste the two gender drill files
5. Click the **Styling** tab → paste `styling.css`
6. Click **Save**

### 3. Set card generation rules

This step is **required** — without it, Gender Drill cards will be generated for verbs and adjectives (and appear blank).

- **Recognition** → generation rule: leave empty
- **Production** → generation rule: leave empty
- **Gender Drill** → generation rule: `article`

### 4. Copy the audio files

Copy every `.mp3` from `anki_output/media/` to Anki's media folder:

**Windows:**
```
C:\Users\<you>\AppData\Roaming\Anki2\<profile>\collection.media\
```

**macOS:**
```
~/Library/Application Support/Anki2/<profile>/collection.media/
```

**Linux:**
```
~/.local/share/Anki2/<profile>/collection.media/
```

You can open the media folder quickly with **Tools → Check Media → Open media folder**.

### 5. Import the .txt

In Anki:

1. **File → Import**
2. Select your `<timestamp>_xxx.txt` file
3. Set **Note Type** to `GermanAnki_v8`
4. Set **Deck** to the deck you want
5. Set **Fields separated by**: **Tab**
6. Set **Allow HTML in fields**: **On**
7. Click **Import**

Verify the field mapping matches — the `.txt` header row declares the columns in order, so Anki should map them automatically.

---

## Card types explained

### 1. Recognition (DE→EN)

- **Front:** the German word + audio
- **Back:** article, translation, example sentence, pronunciation, grammar, collocations
- **Purpose:** do you know what this word means?

### 2. Production (EN→DE)

- **Front:** English translation + typed-answer input
- **Back:** the full German answer (article + word for nouns)
- **Purpose:** can you produce the German word on demand? Wrong article = wrong answer.

### 3. Gender Drill (nouns only)

- **Front:** bare noun — "Der, die, oder das?"
- **Back:** the correct article + plural
- **Purpose:** drill the article as a reflex
- **Note:** only generated for singular-capable nouns (excludes *die Leute*, *die Ferien*)

---

## Configuration reference

All settings live in `anki_config.json` in the app folder. You can edit it by hand or via the GUI.

| Setting | Default | Notes |
|---|---|---|
| `provider` | `Gemini` | Which AI provider to use |
| `gemini_model` | `gemini-3.6-flash` | Model ID |
| `groq_model` | `openai/gpt-oss-120b` | Model ID |
| `verifier_enabled` | `False` | Run a second LLM pass to check facts |
| `verifier_gemini_model` | `gemini-3.6-flash` | Use a model **at least as strong** as the generator |
| `voice_word` | `de-DE-ConradNeural` | Word audio voice |
| `voice_sentence` | `de-DE-KatjaNeural` | Sentence audio voice |
| `audio_speed` | `+0%` | Range −50% to +20% |
| `sentence_audio` | `True` | Generate sentence MP3s |
| `overnight_mode` | `False` | Enable per-word retries on failure |
| `max_retries` | `5` | Attempts per word per stage |
| `backoff_base` | `10.0` | Exponential backoff base (seconds) |
| `max_overnight_passes` | `1` | Batch retry passes for failed words |
| `pixabay_key` | `""` | Pixabay API key |
| `use_pixabay` | `True` | Fetch images for nouns |
| `native_language` | `Bangla` | Language for `pronunciation_native` field |
| `deck_name` | `German::Vocabulary` | Deck name in the exported `.txt` |
| `notetype_name` | `GermanAnki_v8` | Note type name in the exported `.txt` |

---

## Troubleshooting

### "No module named 'google.genai'" (or similar)

Install the missing package:

```bash
pip install google-genai groq edge-tts pyperclip pillow
```

The startup log shows which dependencies loaded successfully.

### "429 RESOURCE_EXHAUSTED" errors

You've hit your daily quota. Check which provider/model you're using:

- **Gemini 3.6 Flash free tier:** 20 RPD — resets at midnight Pacific (1:00 PM Bangladesh Time)
- **Gemini 3.5 Flash-Lite free tier:** 500 RPD
- **Groq GPT-OSS-120B free tier:** 1,000 RPD

Options:
- Wait for the daily reset
- Switch to a higher-quota model (Flash-Lite, Groq)
- Add more API keys (each from a separate Google Cloud project — keys from the same project share quota)

### "Event loop is closed" errors after generating audio

Fixed in v9. If you see it, you're on an older version — upgrade.

### Audio doesn't play in Anki

1. Confirm the `.mp3` files are in Anki's `collection.media/` folder — not just in `anki_output/media/`
2. Run **Tools → Check Media** in Anki to reindex
3. Re-import the `.txt` file — the `[sound:...]` tags need to be present

### Wrong image for a word

Pixabay returns the most popular image for the English translation, which is often the wrong sense for polysemous words (*Bank*, *Maus*, *Ball*, *Schloss*). Double-click the `image_url` field in the Preview tab and paste your own URL, or clear it.

### Verifier deletes or corrupts fields

You're using a weaker verifier than your generator. Use the same model or a stronger one. v9 also has code-side guards that reject empty overwrites and protect sensitive fields — but the rule is: **the verifier should never be weaker than the generator**.

### Voice audio sounds wrong or fails

Only three edge-tts voices work reliably: Conrad, Katja, Amala. v9 restricts the dropdown to these. If you see failures, upgrade:

```bash
pip install -U edge-tts
```

### Same word in two decks plays the wrong sentence

Fixed in v9. Sentence MP3 filenames now include a hash of the sentence text, so two different sentences for the same word never share a file.

### Duplicate-word warning on process

The app tracks every word you've ever processed in `anki_word_history.txt`. If you re-add a word intentionally, click **Yes** to continue. To clear history, delete the file.

### App doesn't start, no window appears

Run from a terminal to see errors:

```bash
python german_anki_generator.py
```

Paste any traceback into a GitHub issue.

---

## FAQ

**How many words can I process at once?**
Technically unlimited. Practically, the daily API quota is the bottleneck. With free-tier Gemini 3.6 Flash, that's ~10 words/day per project. With Groq free tier, ~500–1,000 words/day.

**Does it work offline?**
No — generation requires an LLM API. Once cards are generated, you can edit them offline and export without internet, but audio generation requires internet (edge-tts).

**Can I use it for other languages?**
The prompts and card templates are German-specific. The infrastructure would work for any language with modified prompts.

**Can I edit the prompts?**
Yes — the **Prompts** tab shows both the generation and verification prompt. To modify them, edit `MASTER_PROMPT` and `VERIFIER_PROMPT` in the source file (around line 200).

**How do I add new fields?**
Add the field name to `UNIVERSAL_FIELDS` in the code, add it to the Anki note type, and update the card templates. Not trivial — plan the schema carefully.

**Does it support AnkiConnect?**
No — v9 removed AnkiConnect support. The file-import workflow is more reliable and doesn't require Anki to be running.

**Is my API key safe?**
Yes — keys are stored in `anki_config.json` locally and never transmitted anywhere except to the API provider you configured. Do not commit `anki_config.json` to GitHub.

**Where are my session files?**
- `anki_session_draft.json` — current session, auto-saved after each word
- `anki_word_history.txt` — lifetime word history, used for duplicate detection
- `anki_output/backups/*.json` — one backup per file generation

All are plain text and human-readable.

---

## Contributing

Issues and pull requests welcome. For significant changes, open an issue first to discuss the approach.

## License

MIT — see `LICENSE` file for details.

## Acknowledgments

- [Microsoft edge-tts](https://github.com/rany2/edge-tts) for German neural voices
- [Pixabay](https://pixabay.com) for free image search
- [Anki](https://apps.ankiweb.net) for the flashcard platform
