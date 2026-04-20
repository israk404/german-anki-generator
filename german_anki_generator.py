#!/usr/bin/env python3
"""
German Anki Card Generator — v1
One master prompt · auto word-type detection · universal note type · 26 fields.
"""

import json
import os
import sys
import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import threading

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

GENDER_COLORS = {
    "der": "#2563EB",
    "die": "#DC2626",
    "das": "#16A34A",
    "":    "#94A3B8",
}

UMLAUT_MAP = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    'ß': 'ss',
}

TYPE_COLORS = {
    "noun":      "#DBEAFE",
    "verb":      "#FEF3C7",
    "adjective": "#DCFCE7",
    "phrase":    "#F3E8FF",
}
TYPE_TEXT = {
    "noun":      "#1D4ED8",
    "verb":      "#92400E",
    "adjective": "#15803D",
    "phrase":    "#7E22CE",
}

# ── Native language options for pronunciation field ───────────────────────────
NATIVE_LANGUAGES = [
    "Bangla",
    "Hindi",
    "Arabic",
    "Turkish",
    "Spanish",
    "Portuguese",
    "French",
    "Italian",
    "Russian",
    "Urdu",
    "Persian (Farsi)",
    "Chinese (Pinyin)",
    "Japanese (Hiragana)",
    "Korean",
    "Vietnamese",
    "Indonesian",
    "Swahili",
    "Polish",
    "Dutch",
    "Greek",
]

# ── Universal field order — 26 fields ────────────────────────────────────────
# Anki note type must have fields in exactly this order.
UNIVERSAL_FIELDS = [
    "word_type",           #  1
    "target_word",         #  2
    "article",             #  3
    "plural",              #  4
    "genitive",            #  5
    "auxiliary",           #  6
    "past_participle",     #  7
    "conjugation",         #  8
    "separable",           #  9
    "reflexive",           # 10
    "comparative",         # 11
    "superlative",         # 12
    "antonym",             # 13
    "register",            # 14
    "english_translation", # 15
    "pronunciation",       # 16
    "german_sentence",     # 17
    "english_sentence",    # 18
    "cloze_sentence",      # 19
    "collocations",        # 20
    "word_family",         # 21
    "image_url",           # 22
    "audio_word",          # 23  auto-injected
    "audio_sentence",      # 24  auto-injected
    "notes",               # 25
    "tags",                # 26
]

# ─────────────────────────────────────────────────────────────────────────────
#  MASTER PROMPT
# ─────────────────────────────────────────────────────────────────────────────

MASTER_PROMPT = '''You are generating data for a German language learning Anki deck.
You will receive a list of German words or phrases of ANY type — nouns, verbs, adjectives, and phrases can all be mixed in one list.
For EACH item, automatically identify its type and fill all 26 fields correctly.

OUTPUT: A single valid JSON array only. No markdown, no code fences, no explanation whatsoever.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL 26 FIELDS — every object must contain all 26, use "" for non-applicable fields
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. word_type           → "noun" | "verb" | "adjective" | "phrase"
 2. target_word         → The German word exactly as given. Capitalize nouns.
 3. article             → "der" | "die" | "das" for nouns only. "" for all others.
 4. plural              → Full plural with article e.g. "die Häuser". "" if not noun.
 5. genitive            → Genitive singular e.g. "des Hauses". "" if not noun.
 6. auxiliary           → "haben" or "sein" for verbs only. "" for all others.
 7. past_participle     → e.g. "gegangen" for verbs only. "" for all others.
 8. conjugation         → "ich X | du X | er/sie/es X | wir X" for verbs. "" for all others.
 9. separable           → "yes" or "no" for verbs only. "" for all others.
10. reflexive           → "yes" or "no" for verbs only. "" for all others.
11. comparative         → e.g. "größer" for adjectives only. "" for all others.
12. superlative         → e.g. "am größten" for adjectives only. "" for all others.
13. antonym             → Opposite adjective e.g. "klein". "" for all others.
14. register            → "formal" | "informal" | "neutral" for phrases only. "" for all others.
15. english_translation → Clear English meaning. Required for ALL types.
16. pronunciation       → "<<LANG>> phonetic | English phonetic | memory tip"
                          Example: "<<NOUN_EX>> | hous | sounds like English house"
17. german_sentence     → One natural A1/A2 sentence using this word. Max 12 words.
18. english_sentence    → English translation of that sentence.
19. cloze_sentence      → Same sentence with the target word replaced by ___
20. collocations        → 3-4 common fixed phrases or compounds using this word.
21. word_family         → 2-3 related words from same root with English meaning.
22. image_url           → "" (always leave blank)
23. audio_word          → "" (auto-generated by the app, always leave blank)
24. audio_sentence      → "" (auto-generated by the app, always leave blank)
25. notes               → One memory trick, grammar rule, or common mistake warning.
26. tags                → Space-separated: level + type + topic. e.g. "A1 noun home"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO IDENTIFY WORD TYPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NOUN      → Has der/die/das. Always capitalized in German.
            Examples: Haus, Auto, Freund, Stadt, Wasser, Zeit
VERB      → Action or state word. Infinitive ends in -en.
            Examples: gehen, machen, haben, sein, kaufen, schlafen, anfangen
ADJECTIVE → Describes a quality. Can follow "sein" (Das Haus ist groß).
            Examples: groß, klein, schön, schnell, müde, wichtig, neu
PHRASE    → Two or more words functioning as a fixed unit.
            Examples: Guten Morgen, nach Hause, Das macht nichts, Wie geht es Ihnen?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLETE EXAMPLES (one of each type)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[
  {
    "word_type": "noun",
    "target_word": "Haus",
    "article": "das",
    "plural": "die Häuser",
    "genitive": "des Hauses",
    "auxiliary": "",
    "past_participle": "",
    "conjugation": "",
    "separable": "",
    "reflexive": "",
    "comparative": "",
    "superlative": "",
    "antonym": "",
    "register": "",
    "english_translation": "house",
    "pronunciation": "<<NOUN_EX>> | hous | sounds like English house",
    "german_sentence": "Das Haus ist sehr groß und alt.",
    "english_sentence": "The house is very big and old.",
    "cloze_sentence": "Das ___ ist sehr groß und alt.",
    "collocations": "nach Hause, zu Hause, das Elternhaus, der Hausmeister",
    "word_family": "das Häuschen (little house), häuslich (domestic), der Haushalt (household)",
    "image_url": "",
    "audio_word": "",
    "audio_sentence": "",
    "notes": "zu Hause = at home (location). nach Hause = going home (direction). These two are extremely commonly confused!",
    "tags": "A1 noun home"
  },
  {
    "word_type": "verb",
    "target_word": "gehen",
    "article": "",
    "plural": "",
    "genitive": "",
    "auxiliary": "sein",
    "past_participle": "gegangen",
    "conjugation": "ich gehe | du gehst | er/sie/es geht | wir gehen",
    "separable": "no",
    "reflexive": "no",
    "comparative": "",
    "superlative": "",
    "antonym": "",
    "register": "",
    "english_translation": "to go",
    "pronunciation": "<<VERB_EX>> | geh-en | geh rhymes with day",
    "german_sentence": "Ich gehe jeden Morgen in die Schule.",
    "english_sentence": "I go to school every morning.",
    "cloze_sentence": "Ich ___ jeden Morgen in die Schule.",
    "collocations": "spazieren gehen, einkaufen gehen, schlafen gehen, zur Arbeit gehen",
    "word_family": "der Gang (corridor/gait), der Ausgang (exit), der Eingang (entrance)",
    "image_url": "",
    "audio_word": "",
    "audio_sentence": "",
    "notes": "Uses sein in perfect tense: Ich bin gegangen. NOT habe gegangen — very common mistake for beginners!",
    "tags": "A1 verb movement"
  },
  {
    "word_type": "adjective",
    "target_word": "groß",
    "article": "",
    "plural": "",
    "genitive": "",
    "auxiliary": "",
    "past_participle": "",
    "conjugation": "",
    "separable": "",
    "reflexive": "",
    "comparative": "größer",
    "superlative": "am größten",
    "antonym": "klein",
    "register": "",
    "english_translation": "big / tall",
    "pronunciation": "<<ADJ_EX>> | gross | WARNING: means BIG not the English word gross",
    "german_sentence": "Mein Bruder ist sehr groß.",
    "english_sentence": "My brother is very tall.",
    "cloze_sentence": "Mein Bruder ist sehr ___.",
    "collocations": "ein großes Problem, groß werden, im Großen und Ganzen, großartig",
    "word_family": "die Größe (size/height), vergrößern (to enlarge), großartig (magnificent)",
    "image_url": "",
    "audio_word": "",
    "audio_sentence": "",
    "notes": "Means both big (objects) and tall (people). False friend: groß does NOT mean the English gross!",
    "tags": "A1 adjective size"
  },
  {
    "word_type": "phrase",
    "target_word": "Wie geht es Ihnen?",
    "article": "",
    "plural": "",
    "genitive": "",
    "auxiliary": "",
    "past_participle": "",
    "conjugation": "",
    "separable": "",
    "reflexive": "",
    "comparative": "",
    "superlative": "",
    "antonym": "",
    "register": "formal",
    "english_translation": "How are you? (formal)",
    "pronunciation": "<<PHRASE_EX>> | vee gayt es EE-nen | Ihnen is the formal you",
    "german_sentence": "Guten Tag! Wie geht es Ihnen heute?",
    "english_sentence": "Good day! How are you today?",
    "cloze_sentence": "Guten Tag! ___ heute?",
    "collocations": "Wie geht es dir? (informal), Wie geht es Ihnen? (formal), Es geht mir gut, Nicht so gut",
    "word_family": "gehen (to go), gut (good) — literally means How goes it to you?",
    "image_url": "",
    "audio_word": "",
    "audio_sentence": "",
    "notes": "Use Ihnen (capital I, formal) with strangers and authority figures. With friends use: Wie geht es dir? or just Wie geht es?",
    "tags": "A1 phrase greeting formal"
  }
]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORDS TO PROCESS  (replace everything below this line with your word list)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[INSERT YOUR WORDS HERE — one per line or comma-separated, mixed types are fine]'''


# ── Per-language example pronunciations for the 4 example words ──────────────
# Format: (Haus, gehen, groß, Wie geht es Ihnen?)
LANG_EXAMPLES = {
    "Bangla":            ("হাউস",          "গেহেন",       "গ্রোস",    "ভি গেট এস ইনেন"),
    "Hindi":             ("हाउस",           "गेहेन",       "ग्रोस",    "वी गेट एस इनेन"),
    "Arabic":            ("هاوس",           "غيهن",        "غروس",     "في غيت إس إينن"),
    "Turkish":           ("haus",           "geyen",       "gros",     "vi geyt es inen"),
    "Spanish":           ("jaus",           "guejen",      "gros",     "vi gueit es inen"),
    "Portuguese":        ("raus",           "guéren",      "gros",     "vi gueit es inen"),
    "French":            ("haousse",        "guéen",       "grosse",   "vi guète esse ine-ne"),
    "Italian":           ("haus",           "gè-en",       "gros",     "vi ghet es inen"),
    "Russian":           ("хаус",           "гэ-эн",       "грос",     "ви гейт эс инэн"),
    "Urdu":              ("ہاؤس",           "گیہن",        "گروس",     "وی گیٹ ایس اینن"),
    "Persian (Farsi)":   ("هاوس",           "گه‌ئن",       "گروس",     "وی گیت اس اینن"),
    "Chinese (Pinyin)":  ("hāo sī",         "gé ēn",       "gé luō sī","wéi gài tè ài sī yī nén"),
    "Japanese (Hiragana)":("ハウス",        "ゲーエン",    "グロース",  "ヴィー ゲート エス イーネン"),
    "Korean":            ("하우스",         "게엔",        "그로스",    "비 게트 에스 이넨"),
    "Vietnamese":        ("ha-ut",          "gê-en",       "grốt",     "vi ghết ét i-nen"),
    "Indonesian":        ("haus",           "ge-en",       "gros",     "vi geit es inen"),
    "Swahili":           ("hausi",          "ge-en",       "grosu",    "vi geiti esi ineni"),
    "Polish":            ("haus",           "ge-en",       "gros",     "wi gejt es inen"),
    "Dutch":             ("haus",           "chee-en",     "chros",    "vee chayt es ee-nen"),
    "Greek":             ("χάους",          "γκε-εν",      "γκρος",    "βι γκεϊτ ες ίνεν"),
}

class GermanAnkiGenerator:

    def __init__(self, output_dir: str = "anki_output"):
        self.output_dir = Path(output_dir)
        self.audio_dir  = self.output_dir / "media"
        self.timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    def setup(self):
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "backups").mkdir(exist_ok=True)

    def clean_json(self, text: str) -> str:
        text = re.sub(r'^```json\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text)
        text = re.sub(r'^```\s*', '', text)
        m = re.search(r'\[[\s\S]*\]', text)
        return m.group(0).strip() if m else text.strip()

    def sanitize_filename(self, text: str) -> str:
        for u, r in UMLAUT_MAP.items():
            text = text.replace(u, r)
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '_', text)
        return text.lower().strip('_')[:50]

    def escape_field(self, value: str) -> str:
        if not value:
            return ""
        value = str(value)
        needs_quote = any(c in value for c in ('\t', '\n', '\r', '"'))
        if '"' in value:
            value = value.replace('"', '""')
        if needs_quote:
            value = f'"{value}"'
        return value

    def generate_audio(self, text: str, filename: str) -> Optional[Path]:
        if not GTTS_AVAILABLE or not text.strip():
            return None
        fp = self.audio_dir / f"{filename}.mp3"
        if fp.exists():
            return fp
        try:
            tts = gTTS(text=text, lang='de', tld='de', slow=False)
            tts.save(str(fp))
            return fp
        except Exception:
            return None

    def process(
        self,
        json_input: str,
        deck_name: str = "German::Vocabulary",
        generate_reverse: bool = False,
        sentence_audio: bool = True,
        progress_callback=None,
    ) -> Tuple[bool, str, dict]:

        self.setup()

        cleaned = self.clean_json(json_input)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}", {}

        if not isinstance(data, list) or not data:
            return False, "JSON must be a non-empty array", {}

        if progress_callback:
            progress_callback(f"Parsed {len(data)} entries")

        audio_word_count = 0
        audio_sent_count = 0

        for i, entry in enumerate(data):
            word    = entry.get("target_word", "")
            article = entry.get("article", "")

            word_text = f"{article} {word}".strip() if article else word
            word_fn   = self.sanitize_filename(f"{article}_{word}".strip("_"))

            if self.generate_audio(word_text, word_fn):
                audio_word_count += 1

            if sentence_audio:
                sentence = entry.get("german_sentence", "")
                sent_fn  = self.sanitize_filename(f"sent_{word_fn}")
                if self.generate_audio(sentence, sent_fn):
                    audio_sent_count += 1

            if progress_callback:
                progress_callback(f"Audio {i+1}/{len(data)}: {word}")

        if progress_callback:
            progress_callback("Writing import file…")

        sample_words = [e.get("target_word", "") for e in data[:3]]
        fn_base  = self.sanitize_filename("_".join(w for w in sample_words if w))
        filename = f"{self.timestamp}_{fn_base}"
        txt_path = self.output_dir / f"{filename}.txt"

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("#separator:Tab\n")
            f.write("#html:true\n")
            f.write(f"#deck:{deck_name}\n")
            f.write("\n")

            for entry in data:
                word    = entry.get("target_word", "")
                article = entry.get("article", "")
                word_fn = self.sanitize_filename(f"{article}_{word}".strip("_"))
                sent_fn = self.sanitize_filename(f"sent_{word_fn}")

                row = []
                for field in UNIVERSAL_FIELDS:
                    if field == "audio_word":
                        mp3   = self.audio_dir / f"{word_fn}.mp3"
                        value = f"[sound:{word_fn}.mp3]" if mp3.exists() else ""
                    elif field == "audio_sentence":
                        mp3   = self.audio_dir / f"{sent_fn}.mp3"
                        value = f"[sound:{sent_fn}.mp3]" if mp3.exists() else ""
                    elif field == "tags":
                        raw   = entry.get("tags", "")
                        value = (" ".join(str(t) for t in raw)
                                 if isinstance(raw, list)
                                 else str(raw).replace(",", " "))
                    else:
                        value = str(entry.get(field, ""))
                    row.append(self.escape_field(value))

                f.write("\t".join(row) + "\n")

                if generate_reverse:
                    rev = []
                    for field in UNIVERSAL_FIELDS:
                        if field == "target_word":
                            val = str(entry.get("english_translation", ""))
                        elif field == "english_translation":
                            val = str(entry.get("target_word", ""))
                        elif field == "audio_word":
                            mp3 = self.audio_dir / f"{word_fn}.mp3"
                            val = f"[sound:{word_fn}.mp3]" if mp3.exists() else ""
                        elif field == "audio_sentence":
                            mp3 = self.audio_dir / f"{sent_fn}.mp3"
                            val = f"[sound:{sent_fn}.mp3]" if mp3.exists() else ""
                        elif field == "tags":
                            raw = entry.get("tags", "")
                            base = (" ".join(str(t) for t in raw)
                                    if isinstance(raw, list)
                                    else str(raw).replace(",", " "))
                            val = base + " reverse"
                        else:
                            val = str(entry.get(field, ""))
                        rev.append(self.escape_field(val))
                    f.write("\t".join(rev) + "\n")

        backup = self.output_dir / "backups" / f"{filename}.json"
        with open(backup, 'w', encoding='utf-8') as f:
            f.write(json_input)

        return True, "Success!", {
            "entries":    len(data),
            "audio_word": audio_word_count,
            "audio_sent": audio_sent_count,
            "txt_path":   str(txt_path),
            "audio_dir":  str(self.audio_dir),
            "filename":   filename,
            "reverse":    generate_reverse,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────────────────────────────────────

class AnkiGeneratorGUI:

    BG          = "#F8FAFC"
    SURFACE     = "#FFFFFF"
    BORDER      = "#E2E8F0"
    ACCENT      = "#2563EB"
    ACCENT_DARK = "#1D4ED8"
    TEXT        = "#1E293B"
    TEXT_MUTED  = "#64748B"
    SUCCESS     = "#16A34A"
    ERROR       = "#DC2626"
    SIDEBAR_BG  = "#EEF2FF"

    def __init__(self, root):
        self.root = root
        self.root.title("German Anki Generator  ·  v1")
        self.root.geometry("1120x700")
        self.root.minsize(920, 580)
        self.root.configure(bg=self.BG)

        self.parsed_data: Optional[List[Dict]] = None
        self.deck_name_var   = tk.StringVar(value="German::Vocabulary")
        self.reverse_var     = tk.BooleanVar(value=False)
        self.sent_audio_var  = tk.BooleanVar(value=True)
        self.native_lang_var = tk.StringVar(value="Bangla")

        self._build_styles()
        self._build_ui()
        self._center()
        self._check_deps()

    # ── Styles ───────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=self.BG, foreground=self.TEXT,
                    font=("Segoe UI", 10))
        s.configure("Card.TFrame",   background=self.SURFACE)
        s.configure("Header.TFrame", background=self.BG)
        s.configure("Title.TLabel",  background=self.BG,
                    font=("Segoe UI", 13, "bold"), foreground=self.TEXT)
        s.configure("Sub.TLabel",    background=self.BG,
                    font=("Segoe UI", 9), foreground=self.TEXT_MUTED)
        s.configure("Section.TLabel", background=self.SURFACE,
                    font=("Segoe UI", 9, "bold"), foreground=self.TEXT_MUTED)
        s.configure("Accent.TButton",
                    background=self.ACCENT, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=(14, 8),
                    relief="flat", borderwidth=0)
        s.map("Accent.TButton",
              background=[("active", self.ACCENT_DARK),
                          ("disabled", self.BORDER)])
        s.configure("Ghost.TButton",
                    background=self.BG, foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 9), padding=(8, 5),
                    relief="flat", borderwidth=0)
        s.map("Ghost.TButton",
              foreground=[("active", self.TEXT)],
              background=[("active", self.BORDER)])
        s.configure("Treeview",
                    background=self.SURFACE, foreground=self.TEXT,
                    rowheight=26, fieldbackground=self.SURFACE,
                    font=("Segoe UI", 9), borderwidth=0)
        s.configure("Treeview.Heading",
                    background=self.BORDER, foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", "#DBEAFE")],
              foreground=[("selected", self.TEXT)])
        s.configure("TNotebook",    background=self.BG, borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=self.BORDER, foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 9), padding=(14, 7))
        s.map("TNotebook.Tab",
              background=[("selected", self.SURFACE)],
              foreground=[("selected", self.ACCENT)])

    # ── Layout ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 10))
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="German Anki Generator",
                  style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(hdr,
                  text="  ·  master prompt · auto type detection · 26 universal fields",
                  style="Sub.TLabel").pack(side=tk.LEFT)
        self.status_lbl = tk.Label(hdr, text="● Ready",
                                   bg=self.BG, fg=self.SUCCESS,
                                   font=("Segoe UI", 9))
        self.status_lbl.pack(side=tk.RIGHT)

        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill=tk.X)

        # Body
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        sidebar = tk.Frame(body, bg=self.SIDEBAR_BG, width=210)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        nb_frame = tk.Frame(body, bg=self.BG)
        nb_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_notebook(nb_frame)

        # Bottom bar
        bot = tk.Frame(self.root, bg=self.BG, pady=8)
        bot.pack(fill=tk.X, padx=12)
        self.progress = ttk.Progressbar(bot, mode="indeterminate", length=160)
        self.progress.pack(side=tk.LEFT)
        ttk.Button(bot, text="Open output folder",
                   style="Ghost.TButton",
                   command=self._open_folder).pack(side=tk.RIGHT, padx=(8, 0))
        self.gen_btn = ttk.Button(
            bot, text="⬇  Generate Files + Audio",
            style="Accent.TButton", command=self._generate,
        )
        self.gen_btn.pack(side=tk.RIGHT)

    # ── Sidebar ──────────────────────────────────────────────────────────────
    def _build_sidebar(self, parent):
        def sec(text):
            tk.Label(parent, text=text, bg=self.SIDEBAR_BG,
                     fg=self.ACCENT, font=("Segoe UI", 8, "bold")
                     ).pack(padx=14, pady=(14, 3), anchor="w")

        def sep():
            tk.Frame(parent, bg=self.BORDER, height=1
                     ).pack(fill=tk.X, padx=10, pady=6)

        sec("OPTIONS")

        tk.Checkbutton(
            parent, text="Generate reverse cards",
            variable=self.reverse_var,
            bg=self.SIDEBAR_BG, fg=self.TEXT,
            selectcolor="#C7D2FE", activebackground=self.SIDEBAR_BG,
            font=("Segoe UI", 9),
        ).pack(padx=14, pady=2, anchor="w")

        tk.Checkbutton(
            parent, text="Sentence audio",
            variable=self.sent_audio_var,
            bg=self.SIDEBAR_BG, fg=self.TEXT,
            selectcolor="#C7D2FE", activebackground=self.SIDEBAR_BG,
            font=("Segoe UI", 9),
        ).pack(padx=14, pady=2, anchor="w")
        self.sent_audio_var.set(True)

        sep()
        sec("DECK NAME")
        tk.Entry(
            parent, textvariable=self.deck_name_var,
            bg=self.SURFACE, fg=self.TEXT,
            relief="flat", bd=1, font=("Segoe UI", 9), width=22,
        ).pack(padx=14, pady=(0, 6), fill=tk.X)

        sep()
        sec("NATIVE LANGUAGE")
        tk.Label(
            parent,
            text="Pronunciation guide language:",
            bg=self.SIDEBAR_BG, fg=self.TEXT_MUTED,
            font=("Segoe UI", 8), wraplength=180, justify="left",
        ).pack(padx=14, pady=(0, 4), anchor="w")

        lang_combo = ttk.Combobox(
            parent,
            textvariable=self.native_lang_var,
            values=NATIVE_LANGUAGES,
            state="readonly",
            width=20,
            font=("Segoe UI", 9),
        )
        lang_combo.pack(padx=14, pady=(0, 6), fill=tk.X)
        lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        sep()
        sec("GENDER LEGEND")
        for article, color in GENDER_COLORS.items():
            label = article if article else "(no article)"
            row = tk.Frame(parent, bg=self.SIDEBAR_BG)
            row.pack(padx=14, pady=1, anchor="w")
            tk.Label(row, text="■", bg=self.SIDEBAR_BG, fg=color,
                     font=("Segoe UI", 11)).pack(side=tk.LEFT)
            tk.Label(row, text=f"  {label}", bg=self.SIDEBAR_BG,
                     fg=self.TEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT)

        sep()
        sec("TYPE LEGEND")
        for wt, color in TYPE_COLORS.items():
            row = tk.Frame(parent, bg=self.SIDEBAR_BG)
            row.pack(padx=14, pady=2, anchor="w")
            tk.Label(row, text=f"  {wt}  ",
                     bg=color, fg=TYPE_TEXT[wt],
                     font=("Segoe UI", 8, "bold"),
                     padx=4, pady=2).pack(side=tk.LEFT)

        sep()
        sec("FIELDS  (26 total)")

        field_canvas = tk.Canvas(parent, bg=self.SIDEBAR_BG,
                                 highlightthickness=0, height=220)
        field_scroll = ttk.Scrollbar(parent, orient="vertical",
                                     command=field_canvas.yview)
        field_canvas.configure(yscrollcommand=field_scroll.set)
        field_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4))
        field_canvas.pack(fill=tk.BOTH, expand=True, padx=(14, 0))

        inner = tk.Frame(field_canvas, bg=self.SIDEBAR_BG)
        field_canvas.create_window((0, 0), window=inner, anchor="nw")
        for i, f in enumerate(UNIVERSAL_FIELDS, 1):
            tk.Label(inner, text=f"{i:2d}. {f}",
                     bg=self.SIDEBAR_BG, fg=self.TEXT_MUTED,
                     font=("Consolas", 8), anchor="w",
                     ).pack(fill=tk.X, pady=1)
        inner.update_idletasks()
        field_canvas.config(scrollregion=field_canvas.bbox("all"))

    # ── Notebook ─────────────────────────────────────────────────────────────
    def _build_notebook(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)

        t1 = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(t1, text="  JSON Input  ")
        self._build_input_tab(t1)

        t2 = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(t2, text="  Preview  ")
        self._build_preview_tab(t2)

        t3 = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(t3, text="  Master Prompt  ")
        self._build_prompt_tab(t3)

    # ── Tab 1 ─────────────────────────────────────────────────────────────────
    def _build_input_tab(self, parent):
        bar = tk.Frame(parent, bg=self.SURFACE)
        bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(bar, text="🔍 Preview cards",
                   style="Ghost.TButton", command=self._preview
                   ).pack(side=tk.LEFT)
        ttk.Button(bar, text="📋 Paste",
                   style="Ghost.TButton", command=self._paste_json
                   ).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="🗑  Clear",
                   style="Ghost.TButton",
                   command=lambda: self.json_box.delete(1.0, tk.END)
                   ).pack(side=tk.LEFT)
        ttk.Button(bar, text="📁 Load file",
                   style="Ghost.TButton", command=self._load_file
                   ).pack(side=tk.LEFT, padx=4)
        tk.Label(bar, text="Paste JSON output from LLM here",
                 bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        box_frame = tk.Frame(parent, bg=self.BORDER, bd=1)
        box_frame.pack(fill=tk.BOTH, expand=True)
        self.json_box = scrolledtext.ScrolledText(
            box_frame, font=("Consolas", 9), wrap=tk.WORD,
            relief="flat", bd=0, bg=self.SURFACE, fg=self.TEXT,
            insertbackground=self.TEXT, padx=10, pady=8,
        )
        self.json_box.pack(fill=tk.BOTH, expand=True)
        self.json_box.insert(tk.END, (
            "// 1. Go to the 'Master Prompt' tab → Copy prompt\n"
            "// 2. Paste into ChatGPT / Claude / Gemini\n"
            "// 3. Replace [INSERT YOUR WORDS HERE] with your word list\n"
            "//    (mixed types are fine — Haus, gehen, groß, Guten Morgen)\n"
            "// 4. Paste the JSON response here\n"
            "// 5. Click 'Preview cards' to verify\n"
            "// 6. Click 'Generate Files + Audio'\n\n"
            "// Paste JSON below ↓\n"
        ))

    # ── Tab 2 ─────────────────────────────────────────────────────────────────
    def _build_preview_tab(self, parent):
        top = tk.Frame(parent, bg=self.SURFACE)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text="Entry:", style="Section.TLabel").pack(side=tk.LEFT)
        self.entry_var   = tk.StringVar()
        self.entry_combo = ttk.Combobox(
            top, textvariable=self.entry_var,
            state="readonly", width=35,
        )
        self.entry_combo.pack(side=tk.LEFT, padx=8)
        self.entry_combo.bind("<<ComboboxSelected>>", self._show_entry)
        self.count_lbl = tk.Label(top, text="0 entries",
                                  bg=self.SURFACE, fg=self.TEXT_MUTED,
                                  font=("Segoe UI", 9))
        self.count_lbl.pack(side=tk.RIGHT)

        badge_row = tk.Frame(parent, bg=self.SURFACE)
        badge_row.pack(fill=tk.X, pady=(0, 6))
        self.type_badge   = tk.Label(badge_row, text="",
                                     bg="#E2E8F0", fg=self.TEXT_MUTED,
                                     font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.type_badge.pack(side=tk.LEFT, padx=(0, 6))
        self.gender_badge = tk.Label(badge_row, text="",
                                     bg="#E2E8F0", fg=self.TEXT_MUTED,
                                     font=("Segoe UI", 8, "bold"), padx=8, pady=3)
        self.gender_badge.pack(side=tk.LEFT)

        tree_wrap = tk.Frame(parent, bg=self.BORDER, bd=1)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical")
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal")
        self.tree = ttk.Treeview(
            tree_wrap, columns=("#", "Field", "Value"),
            show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        self.tree.heading("#",     text="#")
        self.tree.heading("Field", text="Field")
        self.tree.heading("Value", text="Value")
        self.tree.column("#",     width=32,  minwidth=28,  stretch=False)
        self.tree.column("Field", width=160, minwidth=120, stretch=False)
        self.tree.column("Value", width=580, minwidth=300)
        self.tree.tag_configure("noun",   background="#EFF6FF")
        self.tree.tag_configure("verb",   background="#FFFBEB")
        self.tree.tag_configure("adj",    background="#F0FDF4")
        self.tree.tag_configure("phrase", background="#FDF4FF")
        self.tree.tag_configure("audio",  background="#F0FDF4",
                                foreground=self.SUCCESS)
        self.tree.tag_configure("empty",  foreground="#CBD5E1")
        self.tree.tag_configure("shared", background=self.SURFACE)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

    # ── Tab 3 ─────────────────────────────────────────────────────────────────
    def _build_prompt_tab(self, parent):
        bar = tk.Frame(parent, bg=self.SURFACE)
        bar.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            bar,
            text="Copy → paste into any AI → add words at the bottom → paste JSON back into Input tab",
            bg=self.SURFACE, fg=self.TEXT_MUTED,
            font=("Segoe UI", 9), wraplength=680, justify="left",
        ).pack(side=tk.LEFT)
        ttk.Button(bar, text="📋 Copy master prompt",
                   style="Accent.TButton",
                   command=self._copy_prompt).pack(side=tk.RIGHT)

        frame = tk.Frame(parent, bg=self.BORDER, bd=1)
        frame.pack(fill=tk.BOTH, expand=True)
        self.prompt_box = scrolledtext.ScrolledText(
            frame, font=("Consolas", 9), wrap=tk.WORD,
            relief="flat", bd=0, bg="#FAFAF9", fg=self.TEXT,
            padx=10, pady=8, state="disabled",
        )
        self.prompt_box.pack(fill=tk.BOTH, expand=True)
        self.prompt_box.config(state="normal")
        self.prompt_box.insert(tk.END, self._get_prompt_for_lang())
        self.prompt_box.config(state="disabled")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _get_prompt_for_lang(self) -> str:
        """Return the master prompt with the user's selected native language."""
        lang = self.native_lang_var.get()
        ex = LANG_EXAMPLES.get(lang, LANG_EXAMPLES["Bangla"])
        noun_ex, verb_ex, adj_ex, phrase_ex = ex

        prompt = MASTER_PROMPT
        # Field definition line
        prompt = prompt.replace("<<LANG>>",      lang)
        # Four example pronunciation values
        prompt = prompt.replace("<<NOUN_EX>>",   noun_ex)
        prompt = prompt.replace("<<VERB_EX>>",   verb_ex)
        prompt = prompt.replace("<<ADJ_EX>>",    adj_ex)
        prompt = prompt.replace("<<PHRASE_EX>>", phrase_ex)
        return prompt

    def _on_lang_change(self, event=None):
        """Refresh the prompt display when language changes."""
        self.prompt_box.config(state="normal")
        self.prompt_box.delete(1.0, tk.END)
        self.prompt_box.insert(tk.END, self._get_prompt_for_lang())
        self.prompt_box.config(state="disabled")

    def _copy_prompt(self):
        prompt = self._get_prompt_for_lang()
        if CLIPBOARD_AVAILABLE:
            pyperclip.copy(prompt)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
        lang = self.native_lang_var.get()
        self._set_status(f"✅ Prompt copied ({lang})!", self.SUCCESS)
        self.root.after(2500, lambda: self._set_status("● Ready", self.SUCCESS))

    def _preview(self):
        raw = self.json_box.get(1.0, tk.END).strip()
        if not raw or raw.startswith("//"):
            messagebox.showwarning("Empty", "Paste JSON from the LLM first.")
            return
        gen     = GermanAnkiGenerator()
        cleaned = gen.clean_json(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Error", str(e))
            return
        if not isinstance(data, list) or not data:
            messagebox.showerror("Format Error", "JSON must be a non-empty array.")
            return
        self.parsed_data = data
        labels = []
        for i, item in enumerate(data):
            art  = item.get("article", "")
            word = item.get("target_word", "?")
            wt   = item.get("word_type", "")
            labels.append(f"{i+1}. [{wt}]  {art} {word}".strip())
        self.entry_combo["values"] = labels
        self.count_lbl.config(text=f"{len(data)} entries")
        if labels:
            self.entry_combo.current(0)
            self._show_entry()
        self._set_status(f"✅ {len(data)} entries — click Preview tab to inspect",
                         self.SUCCESS)

    def _show_entry(self, event=None):
        if not self.parsed_data:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        idx = self.entry_combo.current()
        if idx < 0 or idx >= len(self.parsed_data):
            return
        entry     = self.parsed_data[idx]
        word_type = entry.get("word_type", "noun")
        article   = entry.get("article", "")

        tc = TYPE_COLORS.get(word_type, "#E2E8F0")
        tt = TYPE_TEXT.get(word_type, self.TEXT_MUTED)
        self.type_badge.config(text=f"  {word_type.upper()}  ", bg=tc, fg=tt)
        if article:
            gc = GENDER_COLORS.get(article, self.TEXT_MUTED)
            self.gender_badge.config(text=f"  {article}  ", bg=gc, fg="white")
        else:
            self.gender_badge.config(text="", bg="#E2E8F0", fg=self.TEXT_MUTED)

        type_specific = {
            "noun":      {"article", "plural", "genitive"},
            "verb":      {"auxiliary", "past_participle", "conjugation",
                          "separable", "reflexive"},
            "adjective": {"comparative", "superlative", "antonym"},
            "phrase":    {"register"},
        }.get(word_type, set())
        type_tag = {"noun": "noun", "verb": "verb",
                    "adjective": "adj", "phrase": "phrase"}.get(word_type, "shared")

        for i, field in enumerate(UNIVERSAL_FIELDS, 1):
            if field in ("audio_word", "audio_sentence"):
                value   = "[auto-generated mp3]"
                row_tag = "audio"
            else:
                raw_val = entry.get(field, "")
                value   = str(raw_val) if raw_val else ""
                if not value:
                    value   = "—"
                    row_tag = "empty"
                elif field in type_specific:
                    row_tag = type_tag
                else:
                    row_tag = "shared"
                if len(value) > 110:
                    value = value[:110] + "…"
            self.tree.insert("", tk.END, values=(i, field, value), tags=(row_tag,))

    def _paste_json(self):
        """Paste clipboard content into the JSON box."""
        try:
            if CLIPBOARD_AVAILABLE:
                content = pyperclip.paste()
            else:
                content = self.root.clipboard_get()
            if content:
                self.json_box.delete(1.0, tk.END)
                self.json_box.insert(tk.END, content)
                self._set_status("✅ Pasted from clipboard", self.SUCCESS)
                self.root.after(2000,
                    lambda: self._set_status("● Ready", self.SUCCESS))
            else:
                self._set_status("⚠ Clipboard is empty", self.TEXT_MUTED)
        except Exception:
            self._set_status("⚠ Could not read clipboard", self.TEXT_MUTED)

    def _load_file(self):
        fp = filedialog.askopenfilename(
            filetypes=[("JSON/Text", "*.json *.txt"), ("All", "*.*")]
        )
        if fp:
            try:
                with open(fp, encoding="utf-8") as f:
                    content = f.read()
                self.json_box.delete(1.0, tk.END)
                self.json_box.insert(tk.END, content)
                self._set_status(f"✅ Loaded {os.path.basename(fp)}", self.SUCCESS)
            except Exception as e:
                messagebox.showerror("Load Error", str(e))

    def _open_folder(self):
        d = Path("anki_output")
        if not d.exists():
            messagebox.showinfo("Not found", "No output folder yet. Generate first.")
            return
        if sys.platform == "win32":
            os.startfile(str(d))
        elif sys.platform == "darwin":
            os.system(f'open "{d}"')
        else:
            os.system(f'xdg-open "{d}"')

    def _generate(self):
        raw = self.json_box.get(1.0, tk.END).strip()
        if not raw or raw.startswith("//"):
            messagebox.showwarning("Empty", "Paste JSON from the LLM first.")
            return
        gen     = GermanAnkiGenerator()
        cleaned = gen.clean_json(raw)
        try:
            data = json.loads(cleaned)
            if not isinstance(data, list) or not data:
                raise ValueError
        except Exception:
            messagebox.showerror("JSON Error",
                                 "Cannot parse JSON. Check the Input tab.")
            return
        self.gen_btn.config(state="disabled")
        self.progress.start()
        self._set_status("⏳ Generating…", self.TEXT_MUTED)
        threading.Thread(target=self._gen_thread, args=(raw,), daemon=True).start()

    def _gen_thread(self, raw: str):
        gen = GermanAnkiGenerator()
        def cb(msg):
            self.root.after(0, lambda m=msg: self._set_status(m, self.TEXT_MUTED))
        ok, msg, stats = gen.process(
            raw,
            deck_name=self.deck_name_var.get(),
            generate_reverse=self.reverse_var.get(),
            sentence_audio=self.sent_audio_var.get(),
            progress_callback=cb,
        )
        self.root.after(0, self._gen_done, ok, msg, stats)

    def _gen_done(self, ok: bool, msg: str, stats: dict):
        self.progress.stop()
        self.gen_btn.config(state="normal")
        if ok:
            self._set_status("✅ Done!", self.SUCCESS)
            result = (
                f"✅  Generation complete!\n\n"
                f"📄  File:           {stats.get('filename')}.txt\n"
                f"📊  Card entries:   {stats.get('entries')}\n"
                f"🔊  Word audio:     {stats.get('audio_word')} files\n"
                f"🔊  Sentence audio: {stats.get('audio_sent')} files\n"
                f"📇  Reverse cards:  {'yes' if stats.get('reverse') else 'no'}\n\n"
                f"──────────────────────────────────────\n"
                f"Next steps:\n"
                f"1. Copy all .mp3 files from  anki_output/media/  to:\n"
                f"   {self._anki_media_path()}\n\n"
                f"2. Anki → File → Import → select the .txt file\n"
                f"3. Note type: German Universal  (26 fields, in order)\n"
                f"4. Tick ✅ 'Allow HTML in fields'\n"
                f"5. Map fields 1–26 in order\n\n"
                f"Open output folder now?"
            )
            if messagebox.askyesno("Done!", result):
                self._open_folder()
        else:
            self._set_status("❌ Failed", self.ERROR)
            messagebox.showerror("Error", msg)

    def _set_status(self, text: str, color: str):
        self.status_lbl.config(text=text, fg=color)

    def _anki_media_path(self) -> str:
        if sys.platform == "win32":
            return r"%APPDATA%\Anki2\User 1\collection.media"
        elif sys.platform == "darwin":
            return "~/Library/Application Support/Anki2/User 1/collection.media"
        return "~/.local/share/Anki2/User 1/collection.media"

    def _center(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _check_deps(self):
        missing = []
        if not GTTS_AVAILABLE:
            missing.append("gtts")
        if not CLIPBOARD_AVAILABLE:
            missing.append("pyperclip")
        if missing:
            messagebox.showwarning(
                "Missing packages",
                f"Run:  pip install {' '.join(missing)}\n\n"
                "Audio and clipboard features need these."
            )


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.configure(bg="#F8FAFC")
    AnkiGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
