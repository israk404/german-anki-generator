# 🇩🇪 German Anki Card Generator

A desktop app that turns a list of German words into a complete, import-ready Anki deck — with audio, example sentences, cloze exercises, collocations, word families, and pronunciation guides. Works with **any native language** — not just Bengali.

---

## Screenshots

<p align="center">
  <img src="screenshots/app_main.png" width="32%">
  <img src="screenshots/app_preview.png" width="32%">
  <img src="screenshots/app_prompt.png" width="32%">
</p>
<p align="center">
  <img src="screenshots/anki_card_front.png" width="32%">
  <img src="screenshots/anki_card_back.png" width="32%">
</p>

---

## What it does

You give it a list of German words — any mix of nouns, verbs, adjectives, and phrases.
It generates:

- A ready-to-import `.txt` file for Anki
- German audio for every word (with article for nouns)
- German audio for every example sentence
- All 26 card fields filled automatically by AI

The AI automatically identifies each word type and fills the right fields — conjugation for verbs, plural and genitive for nouns, comparative and antonym for adjectives, and register for phrases.

---

## Download

### ✅ Option 1 — Windows app (no Python needed)

👉 **[Download latest release](https://github.com/israk404/german-anki-generator/releases/latest)**

Download `GermanAnkiGenerator.exe` and run it. No installation needed.

> **Windows security warning:** Click **More info → Run anyway** when Windows shows a security prompt. This is normal for open-source software without a paid certificate. The full source code is in this repository for anyone to verify.

### Option 2 — Run from Python source

Requires Python 3.9 or higher and an internet connection.

```bash
git clone https://github.com/israk404/german-anki-generator.git
cd german-anki-generator
pip install gtts pyperclip
python german_anki_generator.py
```

Or click the green **Code** button → **Download ZIP** → extract → run `german_anki_generator.py`.

On Linux, install tkinter first:
```bash
sudo apt install python3-tk
```

---

## How it works

```
1. Open the app
2. Select your native language from the sidebar dropdown
3. Go to the "Master Prompt" tab → click "Copy master prompt"
4. Paste into ChatGPT / Claude / Gemini
5. Replace [INSERT YOUR WORDS HERE] with your word list
6. Copy the JSON response → paste into the "JSON Input" tab
7. Click "Preview cards" to verify
8. Click "Generate Files + Audio"
9. Copy the mp3 files to Anki's media folder
10. Import the .txt file into Anki
```

Mixed word types in one list are fine — the AI sorts them automatically.
**Recommended batch size:** 10–20 words per request.

---

## Native language support

The pronunciation field shows how a German word sounds in your native language script, not just English phonetics. Select your language once from the sidebar — the prompt updates automatically every time you copy it.

**Supported languages:**
Bangla · Hindi · Arabic · Turkish · Spanish · Portuguese · French · Italian · Russian · Urdu · Persian (Farsi) · Chinese (Pinyin) · Japanese (Hiragana) · Korean · Vietnamese · Indonesian · Swahili · Polish · Dutch · Greek

Example pronunciation field for the word **Haus**:

| Language | Pronunciation field |
|---|---|
| Bangla | হাউস \| hous \| sounds like English house |
| Hindi | हाउस \| hous \| sounds like English house |
| Arabic | هاوس \| hous \| sounds like English house |
| Spanish | jaus \| hous \| sounds like English house |
| Japanese | ハウス \| hous \| sounds like English house |

---

## Card fields (26 universal fields)

| # | Field | What it contains |
|---|---|---|
| 1 | word_type | noun · verb · adjective · phrase |
| 2 | target_word | The German word |
| 3 | article | der · die · das (nouns only) |
| 4 | plural | Full plural with article |
| 5 | genitive | Genitive singular form |
| 6 | auxiliary | haben or sein (verbs only) |
| 7 | past_participle | e.g. gegangen |
| 8 | conjugation | ich · du · er/sie/es · wir forms |
| 9 | separable | yes or no (verbs only) |
| 10 | reflexive | yes or no (verbs only) |
| 11 | comparative | e.g. größer (adjectives only) |
| 12 | superlative | e.g. am größten |
| 13 | antonym | Opposite word |
| 14 | register | formal · informal · neutral (phrases) |
| 15 | english_translation | English meaning |
| 16 | pronunciation | Native language · English phonetic · memory tip |
| 17 | german_sentence | A1/A2 example sentence |
| 18 | english_sentence | Translation of the sentence |
| 19 | cloze_sentence | Fill-in-the-blank version |
| 20 | collocations | Common fixed phrases |
| 21 | word_family | Related words from the same root |
| 22 | image_url | Optional image (leave blank) |
| 23 | audio_word | Auto-generated mp3 tag |
| 24 | audio_sentence | Auto-generated mp3 tag |
| 25 | notes | Memory trick or grammar warning |
| 26 | tags | Level + type + topic e.g. A1 noun home |

---

## Anki setup (one-time)

Do this once. All future imports work automatically after.

### Step 1 — Create the note type

In Anki: **Tools → Manage Note Types → Add → Clone: Basic → OK**

Name it exactly: `German Universal`

### Step 2 — Add all 26 fields

Click **Fields**. Delete the default fields. Add these in **exactly this order**:

```
1.  word_type
2.  target_word
3.  article
4.  plural
5.  genitive
6.  auxiliary
7.  past_participle
8.  conjugation
9.  separable
10. reflexive
11. comparative
12. superlative
13. antonym
14. register
15. english_translation
16. pronunciation
17. german_sentence
18. english_sentence
19. cloze_sentence
20. collocations
21. word_family
22. image_url
23. audio_word
24. audio_sentence
25. notes
26. tags
```

### Step 3 — Add the card template

Click **Cards** on the note type.

- Copy the contents of `anki_note_card_front.txt` → paste into **Front Template**
- Copy the contents of `anki_note_card_back.txt` → paste into **Back Template**
- Copy the contents of `anki_note_card_styling.css` → paste into **Styling**

Click **Close** → **Save**.

### Step 4 — Import your generated file

1. Copy all `.mp3` files from `anki_output/media/` to your Anki media folder:
   - **Windows:** `%APPDATA%\Anki2\User 1\collection.media`
   - **macOS:** `~/Library/Application Support/Anki2/User 1/collection.media`
   - **Linux:** `~/.local/share/Anki2/User 1/collection.media`

2. In Anki: **File → Import → select the `.txt` file**
3. Set **Note Type** to `German Universal`
4. Tick ✅ **Allow HTML in fields**
5. Confirm fields are mapped in order (field 1 → field 26)
6. Click **Import**

---

## App features

### Sidebar

| Option | What it does |
|---|---|
| Native Language | Sets the script/phonetics used in the pronunciation field |
| Generate reverse cards | Adds an English → German card for every German → English card |
| Sentence audio | Generates a second mp3 for the example sentence |
| Deck name | Which Anki deck to import into. Use `::` for subdecks e.g. `German::A1` |

### Tabs

| Tab | Purpose |
|---|---|
| JSON Input | Paste, load, or clear the AI's JSON response |
| Preview | Inspect each card — shows type badge and gender color |
| Master Prompt | View and copy the prompt for any AI |

### Gender color coding

| Color | Article | Gender |
|---|---|---|
| 🔵 Blue | der | masculine |
| 🔴 Red | die | feminine |
| 🟢 Green | das | neuter |

### Output folder structure

```
anki_output/
├── media/
│   ├── das_haus.mp3           ← word audio
│   ├── sent_das_haus.mp3      ← sentence audio
│   └── ...
├── backups/
│   └── 20250118_....json      ← original JSON saved automatically
└── 20250118_haus_gehen.txt    ← Anki import file
```

---

## Files in this repository

| File | What it is |
|---|---|
| `german_anki_generator.py` | Main application — run with Python |
| `anki_note_card_front.txt` | Front template — paste into Anki card editor |
| `anki_note_card_back.txt` | Back template — paste into Anki card editor |
| `anki_note_card_styling.css` | Card CSS — paste into Anki card editor |
| `README.md` | This file |
| `LICENSE` | MIT license |

---

## Frequently asked questions

**Q: Do I need an API key?**
No. You copy the prompt manually and paste it into any free AI chat. No account or key required.

**Q: My language is not in the list. Can I still use it?**
Yes. Select any language from the list as a fallback, then manually edit the pronunciation field in the JSON before generating. The format is always: `your phonetic | English phonetic | memory tip`.

**Q: What if the AI gives me extra text around the JSON?**
The app automatically strips markdown code fences and finds the JSON array inside any response.

**Q: Can I use this without internet?**
The `.txt` file always generates. You only need internet for audio generation (gTTS uses Google's servers).

**Q: The audio sounds robotic. Can I use better TTS?**
gTTS is free but basic. You can record words yourself or use a service like ElevenLabs and rename the files to match the pattern the app uses.

**Q: My import says "field count mismatch".**
Your note type doesn't have exactly 26 fields in the right order. Go to **Tools → Manage Note Types → German Universal → Fields** and verify against the list above.

**Q: The exe won't open.**
Click **More info → Run anyway** on the Windows security prompt. If it still fails, run from Python source instead.

**Q: Can I study cloze cards separately?**
The `cloze_sentence` field shows a fill-in-the-blank prompt on the back of each card. This is a Basic note type — for true interactive cloze testing you would need a separate Cloze note type in Anki.

---

## Troubleshooting (Python version)

**App won't open**
```bash
python --version        # must be 3.9 or higher
pip install gtts pyperclip
python german_anki_generator.py
```

**"No module named gtts" or "No module named pyperclip"**
```bash
pip install gtts pyperclip
```

**Audio not playing in Anki**
- Copy `.mp3` files to the media folder *before* importing the `.txt`
- In Anki: **Tools → Check Media** to verify files are detected

**JSON parse error**
- The app strips code fences automatically — but if errors persist, delete everything before `[` and after `]` in the JSON box manually

---

## Contributing

This tool is shared freely. Pull requests are welcome. Possible improvements:

- More native languages in the pronunciation dropdown
- Direct AI API integration (skip the copy-paste step)
- Image search integration for the `image_url` field
- Support for other target languages beyond German

---

## License

MIT — free to use, modify, and share. See `LICENSE` for details.

---

## Acknowledgements

Card design informed by the German learning community on Reddit (r/German) — particularly community discussions on effective Anki usage, what fields matter for long-term retention, and common beginner mistakes at A1–B2 level.

Built with Python · tkinter · gTTS
