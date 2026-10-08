#!/usr/bin/env python3
"""
German Anki Card Generator — v9
3 card types: Recognition (DE→EN) · Production (EN→DE) · Gender Drill
Unique audio filenames per sentence · Modern UI · 3 verified edge-tts voices
No AnkiConnect · Both prompts viewable · Full field editing · Checkbox entry picker
"""

import json, os, sys, re, time, threading, asyncio, hashlib
import urllib.request, urllib.error, urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

try:
    from google import genai as _genai_sdk
    from google.genai import types as _genai_types
    GENAI_SDK_AVAILABLE = True
except ImportError:
    GENAI_SDK_AVAILABLE = False

try:
    from groq import Groq as _GroqClient
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE  = Path("anki_config.json")
SESSION_FILE = Path("anki_session_draft.json")
HISTORY_FILE = Path("anki_word_history.txt")

PROVIDERS = ["Gemini", "Groq", "Custom (OpenAI-compatible)"]

DE_VOICES = [
    "de-DE-ConradNeural",
    "de-DE-KatjaNeural",
    "de-DE-AmalaNeural",
]

GEMINI_MODELS = ["gemini-3.6-flash","gemini-3.5-flash-lite","gemini-3.1-pro-preview"]
GROQ_MODELS   = ["openai/gpt-oss-120b","qwen/qwen3.8-27b","openai/gpt-oss-20b"]

# Per-call timeout enforced by _call_with_timeout (seconds).
# If the model holds the socket open past this, we abandon it and move on.
# 90s is long enough for a slow-but-working Gemini call and short enough
# to fail fast when the free-tier quota is silently exhausted.
API_CALL_TIMEOUT_S = 90

GENDER_COLORS = {"der":"#2563EB","die":"#DC2626","das":"#16A34A","":"#94A3B8"}
TYPE_COLORS   = {"noun":"#DBEAFE","verb":"#FEF3C7","adjective":"#DCFCE7","phrase":"#F3E8FF"}
TYPE_TEXT     = {"noun":"#1D4ED8","verb":"#92400E","adjective":"#15803D","phrase":"#7E22CE"}
UMLAUT_MAP    = {'ä':'ae','ö':'oe','ü':'ue','Ä':'Ae','Ö':'Oe','Ü':'Ue','ß':'ss'}

NATIVE_LANGUAGES = [
    "Bangla","Hindi","Arabic","Turkish","Spanish","Portuguese",
    "French","Italian","Russian","Urdu","Persian (Farsi)",
    "Chinese (Pinyin)","Japanese (Hiragana)","Korean","Vietnamese",
    "Indonesian","Swahili","Polish","Dutch","Greek",
]

UNIVERSAL_FIELDS = [
    "word_type","target_word","full_answer","english_translation","sense_hint",
    "german_sentence","english_sentence","article","plural","genitive","plural_only",
    "present_3sg","preterite","past_participle","auxiliary","separable","reflexive",
    "valency","comparative","superlative","pronunciation_ipa","pronunciation_native",
    "memory_tip","confusable","collocations","word_family","register","image_url",
    "notes","audio_word","audio_sentence",
]

VERIFIER_APPLY_FIELDS = {
    "article","plural","genitive","plural_only",
    "present_3sg","preterite","past_participle","auxiliary","separable","reflexive","valency",
    "comparative","superlative",
    "pronunciation_ipa","full_answer","english_translation",
    "german_sentence","english_sentence",
}

# ─────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

MASTER_PROMPT = '''You are generating data for a German language Anki deck.
Process ONE German word and return a single valid JSON object.
No markdown, no code fences, no explanation. JSON only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIELDS — every key present, use "" for non-applicable
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

word_type          → "noun" | "verb" | "adjective" | "phrase"
target_word        → exact German word, nouns capitalised
full_answer        → typed-answer string: "der Tisch" (article + noun) for nouns; bare infinitive e.g. "brauchen" for verbs; bare adjective for adjectives; the phrase itself for phrases
english_translation → natural English meaning, all types
sense_hint         → ONLY if the word is ambiguous or easily confused with another meaning — one short bracketed disambiguator e.g. "bank (river)" vs "bank (money)". Leave "" if not needed.

━━ EXAMPLE SENTENCE (one, simple) ━━━━━━━━━━━━━━━━━━
german_sentence    → Simple A1/A2 sentence. Max 10 words. Basic usage of the word.
english_sentence   → Exact English translation of german_sentence.

━━ NOUN FIELDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
article            → "der"|"die"|"das" — nouns only, "" otherwise
plural             → full plural e.g. "die Häuser" — nouns only
genitive           → genitive singular e.g. "des Hauses" — nouns only
plural_only        → "yes" if noun exists only in plural (die Leute, die Ferien), "" otherwise

━━ VERB FIELDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
present_3sg        → er/sie/es present form e.g. "er ruft ... an" — verbs only
preterite          → 1sg preterite e.g. "ich rief ... an" — verbs only
past_participle    → e.g. "angerufen" — verbs only
auxiliary          → "haben"|"sein" — verbs only
separable          → separable prefix e.g. "an-" if separable, "" otherwise
reflexive          → "yes"|"no" — verbs only
valency            → case government e.g. "+ Akkusativ", "+ Dativ", "+ Akkusativ + Dativ" — verbs only

━━ ADJECTIVE FIELDS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
comparative        → e.g. "größer" — adjectives only
superlative        → e.g. "am größten" — adjectives only

━━ PRONUNCIATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
pronunciation_ipa      → IPA only. e.g. "/ˈvoːnən/"
pronunciation_native   → phonetic approximation in <<LANG>> script only. e.g. "ভো·নেন"
memory_tip             → ONE memorable sound comparison to English. e.g. "'W' sounds like English 'V' — wohnen ≈ 'VON-en'"

━━ VOCABULARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
confusable         → a word learners often mix this up with, plus a one-line distinction. e.g. "brauchen (need) ≠ gebrauchen (to make use of, more formal)". Leave "" if none.
collocations       → 3–4 fixed phrases each with English in brackets.
                     Format: "German phrase (English meaning), ..."
                     Example: "nach Hause gehen (to go home), zu Hause (at home)"
word_family        → 2–3 related words from same root with English.
register           → "formal"|"informal"|"neutral" — phrases only, "" otherwise
image_url          → "" (auto-filled by app)
notes              → One key grammar rule OR the single most common mistake learners make.
audio_word         → "" (auto-generated)
audio_sentence     → "" (auto-generated)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORD TO PROCESS: <<WORD>>'''

VERIFIER_PROMPT = '''You are a German language expert verifying an Anki vocabulary card.
Your job is to CORRECT factual errors only. Do not rewrite for style.
Do not change a field unless it is factually wrong.
NEVER return an empty string for a field that had content — omit the field instead.

Word: <<WORD>>
Card JSON:
<<CARD_JSON>>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIELDS TO VERIFY — check each one listed below
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NOUNS
- article, plural, genitive, plural_only
  (correct gender, correct plural form, correct genitive ending)
- full_answer  (must be "article + noun" for nouns)

VERBS
- present_3sg, preterite, past_participle, auxiliary
  (correct forms; auxiliary is "haben" or "sein" — sein for motion/state change)
- separable  (prefix with trailing hyphen, e.g. "an-", or "" if not separable)
- reflexive  ("yes" | "no")
- valency    (correct case government, e.g. "+ Akkusativ", "+ Dativ")

ADJECTIVES
- comparative, superlative  (correct forms; superlative as "am größten")

ALL WORD TYPES
- english_translation  (natural, accurate; must match the sense shown in the sentence)
- german_sentence      (grammatically correct, uses the word correctly, A1/A2 level, ≤10 words)
- english_sentence     (exact translation of german_sentence)

PRONUNCIATION
- pronunciation_ipa     (valid IPA for Standard German only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIELDS TO SKIP — never touch these
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
word_type, target_word, sense_hint, memory_tip, register,
image_url, audio_word, audio_sentence,
pronunciation_native, word_family, collocations, notes, confusable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Return a JSON object containing ONLY the fields you actually corrected.
- Preserve the exact key name and value type (string vs. empty string).
- If a field is already correct, do NOT include it — do not echo it back.
- NEVER return an empty string for a field that had content. Omit it instead.
- If nothing needs correcting, return exactly: {}
- No markdown. No code fences. No explanation. JSON only.'''

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

class ConfigManager:
    DEFAULTS = {
        "provider":"Gemini","gemini_keys":[],"groq_keys":[],"custom_keys":[],
        "gemini_model":"gemini-3.6-flash","groq_model":"openai/gpt-oss-120b",
        "custom_base_url":"","custom_model":"",
        "verifier_enabled":False,"verifier_provider":"Gemini",
        "verifier_gemini_model":"gemini-3.6-flash",
        "verifier_groq_model":"openai/gpt-oss-120b","verifier_custom_model":"",
        "voice_word":"de-DE-ConradNeural","voice_sentence":"de-DE-KatjaNeural",
        "audio_speed":"+0%","sentence_audio":True,
        "overnight_mode":False,"max_retries":5,"backoff_base":10.0,
        "max_overnight_passes":1,"notify_on_complete":True,
        "pixabay_key":"","delay_seconds":1.5,"native_language":"Bangla",
        "deck_name":"German::Vocabulary","notetype_name":"GermanAnki_v8",
        "use_pixabay":True,"dark_mode":False,
    }
    def __init__(self):
        self._data = dict(self.DEFAULTS); self.load()
    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    self._data.update(json.load(f))
            except Exception: pass
    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception: pass
    def get(self, k, d=None): return self._data.get(k, self.DEFAULTS.get(k, d))
    def set(self, k, v): self._data[k] = v; self.save()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION / HISTORY / STATS
# ─────────────────────────────────────────────────────────────────────────────

def save_session(data):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "data": data},
                      f, indent=2, ensure_ascii=False)
    except Exception: pass
def load_session():
    if not SESSION_FILE.exists(): return []
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            return json.load(f).get("data", [])
    except Exception: return []
def clear_session():
    try: SESSION_FILE.unlink(missing_ok=True)
    except Exception: pass

def load_word_history():
    """Return lowercase set of all words ever processed.
    Robust to encoding differences (UTF-8, UTF-8-BOM, UTF-16, ANSI/cp1252)."""
    if not HISTORY_FILE.exists(): return set()
    try:
        raw = HISTORY_FILE.read_bytes()
    except Exception:
        return set()
    if not raw:
        return set()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        enc = "utf-16"
    elif raw.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    else:
        try:
            raw.decode("utf-8"); enc = "utf-8"
        except UnicodeDecodeError:
            enc = "cp1252"
    try:
        text = raw.decode(enc, errors="replace")
    except Exception:
        return set()
    text = text.replace("\x00", "")
    return {line.strip().lower() for line in text.splitlines() if line.strip()}

def append_word_history(words):
    """Store lowercase. Rewrites the whole file in UTF-8 to normalize encoding."""
    try:
        existing = load_word_history()
        for w in words:
            wl = str(w).strip().lower()
            if wl:
                existing.add(wl)
        if not existing:
            return
        tmp = HISTORY_FILE.with_suffix(".tmp")
        tmp.write_text("\n".join(sorted(existing)) + "\n", encoding="utf-8")
        tmp.replace(HISTORY_FILE)
    except Exception: pass

def load_stats():
    stats = {"total":0,"noun":0,"verb":0,"adjective":0,"phrase":0,"sessions":0}
    bd = Path("anki_output/backups")
    if not bd.exists(): return stats
    for fp in bd.glob("*.json"):
        stats["sessions"] += 1
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for e in data:
                    stats["total"] += 1
                    wt = e.get("word_type","")
                    if wt in stats: stats[wt] += 1
        except Exception: pass
    return stats

# ─────────────────────────────────────────────────────────────────────────────
# PIXABAY
# ─────────────────────────────────────────────────────────────────────────────

class PixabayClient:
    BASE = ("https://pixabay.com/api/?key={key}&q={q}"
            "&image_type=photo&per_page=5&safesearch=true"
            "&orientation=horizontal&order=popular&lang={lang}")

    @staticmethod
    def fetch(target_word, english_translation, sense_hint, word_type, api_key):
        if word_type != "noun" or not api_key:
            return ""

        de = (target_word or "").strip()
        en = (english_translation or "").split(",")[0].split("/")[0].strip()
        sh = (sense_hint or "").strip()
        sh_clean = re.sub(r'\([^)]*\)', '', sh).strip()

        queries = []
        if sh_clean:
            queries.append((sh_clean, "de"))
        if de:
            queries.append((de, "de"))
        if en:
            queries.append((en, "en"))

        for query, lang in queries:
            if not query:
                continue
            try:
                url = PixabayClient.BASE.format(
                    key=urllib.parse.quote(api_key),
                    q=urllib.parse.quote(query[:50]),
                    lang=lang)
                req = urllib.request.Request(
                    url, headers={"User-Agent":"AnkiGenerator/9.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                hits = data.get("hits", [])
                if hits:
                    img = (hits[0].get("largeImageURL","")
                           or hits[0].get("webformatURL",""))
                    if img:
                        return img
            except Exception:
                continue
        return ""

    @staticmethod
    def fetch_thumbnail(url, size=80):
        if not PIL_AVAILABLE or not url: return None
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent":"AnkiGenerator/9.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data))
            img.thumbnail((size, size))
            return ImageTk.PhotoImage(img)
        except Exception: return None

# ─────────────────────────────────────────────────────────────────────────────
# AI CLIENTS
# ─────────────────────────────────────────────────────────────────────────────

def _call_with_timeout(fn, timeout_s, label="API call"):
    """Run fn() on a daemon thread, abandon it if it exceeds timeout_s.

    This is the *only* reliable way to time out google-genai and groq calls.
    Their SDK-level timeouts (HttpOptions, Groq timeout=) are silently ignored
    on some versions, and a silently-exhausted free-tier quota holds the
    socket open indefinitely with no HTTP response.

    On timeout we raise TimeoutError; the abandoned thread keeps running in
    the background (daemon → dies with the process) but the pipeline moves on."""
    result = [None]
    error  = [None]
    done   = threading.Event()

    def _worker():
        try:
            result[0] = fn()
        except Exception as e:
            error[0] = e
        finally:
            done.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    if not done.wait(timeout=timeout_s):
        raise TimeoutError(
            f"{label} exceeded {timeout_s}s. "
            f"If this happens on the FIRST word of a batch, your free-tier "
            f"quota is likely exhausted (Gemini silently holds the socket "
            f"instead of returning 429). Switch to gemini-3.5-flash-lite or "
            f"wait for the midnight-Pacific reset.")

    if error[0] is not None:
        raise error[0]
    return result[0]


class GeminiClient:
    def __init__(self, api_keys, model):
        if not GENAI_SDK_AVAILABLE:
            raise RuntimeError("Install: pip install google-genai")
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        self.model = model; self._key_index = 0; self._clients = {}

    def _get_client(self, key):
        if key not in self._clients:
            self._clients[key] = _genai_sdk.Client(api_key=key)
        return self._clients[key]

    def _do_call(self, key, prompt):
        """Blocking generate_content call, executed on a worker thread."""
        resp = self._get_client(key).models.generate_content(
            model=self.model, contents=prompt,
            config=_genai_types.GenerateContentConfig(
                temperature=0.3, max_output_tokens=2048))
        text = resp.text
        if not text or not text.strip():
            raise ValueError("Empty response")
        return text.strip()

    def generate(self, prompt):
        if not self.api_keys:
            raise ValueError("No Gemini keys configured.")
        last_error = None
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._key_index % len(self.api_keys)]
            kn  = self._key_index % len(self.api_keys) + 1
            self._key_index += 1
            try:
                return _call_with_timeout(
                    lambda: self._do_call(key, prompt),
                    timeout_s=API_CALL_TIMEOUT_S,
                    label=f"Gemini key #{kn}")
            except Exception as e:
                last_error = f"Key #{kn}: {e}"
        raise RuntimeError(f"All Gemini keys failed. Last: {last_error}")


class GroqClient:
    _DEAD = ("model_not_found","model_decommissioned","does not exist","no longer supported")
    def __init__(self, api_keys, model):
        if not GROQ_SDK_AVAILABLE:
            raise RuntimeError("Install: pip install groq")
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        self.model = model; self.model_used = model; self._key_index = 0

    def _try_model(self, model_id, prompt):
        self._model_dead = False; last_err = None
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._key_index % len(self.api_keys)]
            kn  = self._key_index % len(self.api_keys) + 1
            self._key_index += 1
            try:
                def _do():
                    resp = _GroqClient(api_key=key).chat.completions.create(
                        model=model_id,
                        messages=[{"role":"user","content":prompt}],
                        temperature=0.3, max_tokens=2048)
                    return resp.choices[0].message.content
                text = _call_with_timeout(
                    _do, timeout_s=API_CALL_TIMEOUT_S,
                    label=f"Groq key #{kn}/{model_id}")
                if text and text.strip(): return text.strip(), None
                last_err = f"Key #{kn}/{model_id}: empty"
            except Exception as e:
                last_err = f"Key #{kn}/{model_id}: {e}"
                if any(s in str(e) for s in self._DEAD):
                    self._model_dead = True; break
        return None, last_err

    def generate(self, prompt):
        if not self.api_keys: raise ValueError("No Groq keys configured.")
        chain = [self.model] + [m for m in GROQ_MODELS if m != self.model]
        errors = []
        for mid in chain:
            text, err = self._try_model(mid, prompt)
            if text is not None: self.model_used = mid; return text
            errors.append(err)
            if not self._model_dead: break
        raise RuntimeError("All Groq keys/models failed.\n" +
                           "\n".join(f"  {e}" for e in errors if e))

class CustomClient:
    def __init__(self, api_keys, model, base_url):
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        self.model = model; self.base_url = base_url.rstrip("/"); self._key_index = 0
    def generate(self, prompt):
        if not self.api_keys: raise ValueError("No Custom keys configured.")
        if not self.base_url:  raise ValueError("Custom base URL not set.")
        if not self.model:     raise ValueError("Custom model not set.")
        url = f"{self.base_url}/v1/chat/completions"
        last_err = None
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._key_index % len(self.api_keys)]
            kn  = self._key_index % len(self.api_keys) + 1
            self._key_index += 1
            payload = json.dumps({
                "model": self.model,
                "messages": [{"role":"user","content":prompt}],
                "temperature": 0.3, "max_tokens": 2048,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST",
                headers={"Content-Type":"application/json",
                         "Authorization":f"Bearer {key}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                if text and text.strip(): return text.strip()
                last_err = f"Key #{kn}: empty"
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8","replace")[:300]
                last_err = f"Key #{kn}: HTTP {e.code} — {body}"
            except Exception as e:
                last_err = f"Key #{kn}: {e}"
        raise RuntimeError(f"All Custom keys failed. Last: {last_err}")

def make_client(provider, config):
    if provider == "Gemini":
        return GeminiClient(config.get("gemini_keys"), config.get("gemini_model"))
    elif provider == "Groq":
        return GroqClient(config.get("groq_keys"), config.get("groq_model"))
    elif provider == "Custom (OpenAI-compatible)":
        return CustomClient(config.get("custom_keys"),
                            config.get("custom_model"), config.get("custom_base_url"))
    raise ValueError(f"Unknown provider: {provider}")

def make_verifier(config):
    if not config.get("verifier_enabled"): return None
    vp = config.get("verifier_provider", "Gemini")
    if vp == "Gemini":
        return GeminiClient(config.get("gemini_keys"), config.get("verifier_gemini_model"))
    elif vp == "Groq":
        return GroqClient(config.get("groq_keys"), config.get("verifier_groq_model"))
    elif vp == "Custom (OpenAI-compatible)":
        return CustomClient(config.get("custom_keys"),
                            config.get("verifier_custom_model"), config.get("custom_base_url"))
    return None

# ─────────────────────────────────────────────────────────────────────────────
# CORE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class GermanAnkiGenerator:
    def __init__(self, output_dir="anki_output"):
        self.output_dir = Path(output_dir)
        self.audio_dir  = self.output_dir / "media"
        self.timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    def setup(self):
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "backups").mkdir(exist_ok=True)

    def clean_json(self, text):
        text = re.sub(r'^```json\s*','',text.strip())
        text = re.sub(r'\s*```$','',text)
        text = re.sub(r'^```\s*','',text)
        m = re.search(r'\{[\s\S]*\}', text)
        if m: return m.group(0).strip()
        m = re.search(r'\[[\s\S]*\]', text)
        return m.group(0).strip() if m else text.strip()

    def sanitize_filename(self, text):
        for u, r in UMLAUT_MAP.items(): text = text.replace(u, r)
        text = re.sub(r'[^\w\s-]','',text)
        text = re.sub(r'[-\s]+','_',text)
        return text.lower().strip('_')[:50]

    def escape_field(self, value):
        if not value: return ""
        value = str(value)
        if '"' in value: value = value.replace('"','""')
        if any(c in value for c in ('\t','\n','\r','"')):
            value = f'"{value}"'
        return value

    def _sentence_hash(self, sentence):
        if not sentence:
            return "nosent"
        return hashlib.md5(sentence.strip().encode("utf-8")).hexdigest()[:8]

    def generate_audio(self, text, filename, voice, speed="+0%"):
        if not EDGE_TTS_AVAILABLE or not text.strip(): return None
        fp = self.audio_dir / f"{filename}.mp3"
        if fp.exists() and fp.stat().st_size > 0: return fp
        try:
            async def _run():
                comm = edge_tts.Communicate(text, voice=voice, rate=speed)
                await comm.save(str(fp))
            asyncio.run(_run())
            return fp if fp.exists() and fp.stat().st_size > 0 else None
        except Exception: return None

    def play_audio(self, text, voice, speed="+0%"):
        if not EDGE_TTS_AVAILABLE or not text.strip(): return
        tmp = Path("anki_output/media"); tmp.mkdir(parents=True, exist_ok=True)
        fp = tmp / f"_preview_{self.sanitize_filename(text[:20])}.mp3"
        def _worker():
            try:
                async def _gen():
                    comm = edge_tts.Communicate(text, voice=voice, rate=speed)
                    await comm.save(str(fp))
                asyncio.run(_gen())
                if fp.exists():
                    if sys.platform == "win32": os.startfile(str(fp))
                    elif sys.platform == "darwin": os.system(f'afplay "{fp}"')
                    else: os.system(f'mpg123 "{fp}" 2>/dev/null || aplay "{fp}" 2>/dev/null')
            except Exception: pass
        threading.Thread(target=_worker, daemon=True).start()

    def process(self, data, deck_name="German::Vocabulary",
                sentence_audio=True, selected_indices=None,
                voice_word="de-DE-ConradNeural",
                voice_sentence="de-DE-KatjaNeural",
                audio_speed="+0%", progress_callback=None):
        self.setup()
        if selected_indices is not None:
            data = [data[i] for i in selected_indices if i < len(data)]

        aw_count = as_count = 0
        for i, entry in enumerate(data):
            word    = entry.get("target_word","")
            article = entry.get("article","")
            word_text = f"{article} {word}".strip() if article else word
            word_fn   = self.sanitize_filename(f"{article}_{word}".strip("_"))

            s1 = entry.get("german_sentence","")
            sent_fn = self.sanitize_filename(
                f"sent_{word_fn}_{self._sentence_hash(s1)}")

            if self.generate_audio(word_text, word_fn, voice_word, audio_speed):
                aw_count += 1
            if sentence_audio:
                if self.generate_audio(s1, sent_fn, voice_sentence, audio_speed):
                    as_count += 1
            if progress_callback:
                progress_callback(i+1, len(data), word)

        if progress_callback:
            progress_callback(len(data), len(data), "Writing…")

        sample   = [e.get("target_word","") for e in data[:3]]
        fn_base  = self.sanitize_filename("_".join(w for w in sample if w))
        filename = f"{self.timestamp}_{fn_base}"
        txt_path = self.output_dir / f"{filename}.txt"

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("#separator:tab\n#html:true\n")
            f.write("#columns:" + "\t".join(UNIVERSAL_FIELDS) + "\n")
            f.write(f"#deck:{deck_name}\n\n")
            for entry in data:
                word    = entry.get("target_word","")
                article = entry.get("article","")
                word_fn = self.sanitize_filename(f"{article}_{word}".strip("_"))
                s1 = entry.get("german_sentence","")
                sent_fn = self.sanitize_filename(
                    f"sent_{word_fn}_{self._sentence_hash(s1)}")

                mp3w = self.audio_dir / f"{word_fn}.mp3"
                mp3s = self.audio_dir / f"{sent_fn}.mp3"
                sound_word = f"[sound:{word_fn}.mp3]" if mp3w.exists() else ""
                sound_sent = f"[sound:{sent_fn}.mp3]" if mp3s.exists() else ""

                row = []
                for field in UNIVERSAL_FIELDS:
                    if field == "audio_word":       val = sound_word
                    elif field == "audio_sentence": val = sound_sent
                    else: val = str(entry.get(field,""))
                    row.append(self.escape_field(val))
                f.write("\t".join(row) + "\n")

        backup = self.output_dir / "backups" / f"{filename}.json"
        with open(backup,"w",encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True, "Success!", {
            "entries": len(data), "audio_word": aw_count, "audio_sent": as_count,
            "txt_path": str(txt_path), "audio_dir": str(self.audio_dir),
            "filename": filename,
        }

# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────

LIGHT = dict(
    BG="#F1F5F9", SURFACE="#FFFFFF", BORDER="#E2E8F0",
    ACCENT="#6366F1", ACCENT_HOVER="#4F46E5", ACCENT_SOFT="#EEF2FF",
    TEXT="#0F172A", TEXT_MUTED="#64748B",
    SUCCESS="#10B981", ERROR="#EF4444", WARN="#F59E0B",
    SIDEBAR_BG="#FFFFFF",
    LOG_BG="#0F172A", LOG_FG="#94A3B8",
    LOG_OK="#34D399", LOG_ERR="#F87171", LOG_INFO="#FBBF24",
    ENTRY_BG="#F8FAFC",
)
DARK = dict(
    BG="#0F172A", SURFACE="#1E293B", BORDER="#334155",
    ACCENT="#818CF8", ACCENT_HOVER="#6366F1", ACCENT_SOFT="#312E81",
    TEXT="#F1F5F9", TEXT_MUTED="#94A3B8",
    SUCCESS="#34D399", ERROR="#F87171", WARN="#FBBF24",
    SIDEBAR_BG="#1E293B",
    LOG_BG="#020617", LOG_FG="#64748B",
    LOG_OK="#34D399", LOG_ERR="#F87171", LOG_INFO="#FBBF24",
    ENTRY_BG="#0F172A",
)

# ─────────────────────────────────────────────────────────────────────────────
# CHECKBOX DROPDOWN WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class CheckboxDropdown(tk.Toplevel):
    def __init__(self, parent, anchor_widget, labels, checked, on_change):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg="#334155")
        self.attributes("-topmost", True)

        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
        self.geometry(f"460x320+{x}+{y}")

        self.labels  = labels
        self.checked = checked
        self.on_change = on_change

        outer = tk.Frame(self, bg="#FFFFFF")
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        bar = tk.Frame(outer, bg="#F8FAFC")
        bar.pack(fill=tk.X)
        tk.Button(bar, text="Select All", command=self._all,
                  relief="flat", bg="#EEF2FF", fg="#4338CA",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=4,
                  cursor="hand2").pack(side=tk.LEFT, padx=6, pady=6)
        tk.Button(bar, text="Deselect All", command=self._none,
                  relief="flat", bg="#F1F5F9", fg="#64748B",
                  font=("Segoe UI", 9), padx=10, pady=4,
                  cursor="hand2").pack(side=tk.LEFT, padx=(0,6), pady=6)
        tk.Button(bar, text="✕", command=self.destroy,
                  relief="flat", bg="#FEE2E2", fg="#B91C1C",
                  font=("Segoe UI", 10, "bold"), padx=8, pady=4,
                  cursor="hand2").pack(side=tk.RIGHT, padx=6, pady=6)

        body = tk.Frame(outer, bg="#FFFFFF")
        body.pack(fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(body, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.lb = tk.Listbox(body, font=("Segoe UI", 10),
                             bg="#FFFFFF", fg="#0F172A",
                             selectbackground="#EEF2FF", selectforeground="#4338CA",
                             relief="flat", bd=0, activestyle="none",
                             yscrollcommand=vsb.set, highlightthickness=0)
        self.lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self.lb.yview)
        self.lb.bind("<Button-1>", self._on_click)
        self.lb.bind("<space>",   self._on_click)

        self._refresh()
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(200, self._bind_outside)

    def _bind_outside(self):
        try: self.grab_set()
        except Exception: pass

    def _refresh(self):
        self.lb.delete(0, tk.END)
        for i, (label, on) in enumerate(zip(self.labels, self.checked)):
            mark = "☑" if on else "☐"
            self.lb.insert(tk.END, f"  {mark}  {label}")
            if on:
                self.lb.itemconfig(i, fg="#0F172A")
            else:
                self.lb.itemconfig(i, fg="#94A3B8")

    def _on_click(self, event):
        idx = self.lb.nearest(event.y) if hasattr(event, "y") else self.lb.curselection()[0]
        if 0 <= idx < len(self.checked):
            self.checked[idx] = not self.checked[idx]
            self._refresh()
            self.on_change(idx, self.checked[idx])

    def _all(self):
        for i in range(len(self.checked)): self.checked[i] = True
        self._refresh(); self.on_change(-1, True)

    def _none(self):
        for i in range(len(self.checked)): self.checked[i] = False
        self._refresh(); self.on_change(-1, False)

# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

class AnkiGeneratorGUI:
    def __init__(self, root):
        self.root = root
        self.config = ConfigManager()
        theme = DARK if self.config.get("dark_mode") else LIGHT
        for k, v in theme.items(): setattr(self, k, v)

        self.root.title("German Anki Generator")
        self.root.geometry("1360x820")
        self.root.minsize(1100, 680)
        self.root.configure(bg=self.BG)

        self.parsed_data: List[Dict] = []
        self._card_select_vars: List[tk.BooleanVar] = []
        self._filtered_indices: List[int] = []
        self._failed_words: List[str] = []
        self._thumb_refs: List = []
        self._stop_flag = False
        self._processing = False
        self._overnight_pass = 0
        self._prompt_mode = tk.StringVar(value="generation")

        self._hb_gen = 0
        self._hb_label = ""
        self._hb_start = 0.0

        self.provider_var         = tk.StringVar(value=self.config.get("provider"))
        self.gemini_model_var     = tk.StringVar(value=self.config.get("gemini_model"))
        self.groq_model_var       = tk.StringVar(value=self.config.get("groq_model"))
        self.custom_base_url_var  = tk.StringVar(value=self.config.get("custom_base_url"))
        self.custom_model_var     = tk.StringVar(value=self.config.get("custom_model"))
        self.verifier_enabled_var = tk.BooleanVar(value=self.config.get("verifier_enabled"))
        self.verifier_provider_var= tk.StringVar(value=self.config.get("verifier_provider"))
        self.verifier_gmodel_var  = tk.StringVar(value=self.config.get("verifier_gemini_model"))
        self.verifier_rmodel_var  = tk.StringVar(value=self.config.get("verifier_groq_model"))
        self.verifier_cmodel_var  = tk.StringVar(value=self.config.get("verifier_custom_model"))
        self.overnight_var        = tk.BooleanVar(value=self.config.get("overnight_mode"))
        self.max_retries_var      = tk.IntVar(value=self.config.get("max_retries"))
        self.backoff_base_var     = tk.DoubleVar(value=self.config.get("backoff_base"))
        self.max_passes_var       = tk.IntVar(value=self.config.get("max_overnight_passes"))
        self.notify_var           = tk.BooleanVar(value=self.config.get("notify_on_complete"))
        self.deck_name_var        = tk.StringVar(value=self.config.get("deck_name"))
        self.native_lang_var      = tk.StringVar(value=self.config.get("native_language"))
        self.delay_var            = tk.DoubleVar(value=self.config.get("delay_seconds"))
        self.pixabay_key_var      = tk.StringVar(value=self.config.get("pixabay_key"))
        self.use_pixabay_var      = tk.BooleanVar(value=self.config.get("use_pixabay"))
        self.sent_audio_var       = tk.BooleanVar(value=self.config.get("sentence_audio"))
        self.voice_word_var       = tk.StringVar(value=self.config.get("voice_word"))
        self.voice_sent_var       = tk.StringVar(value=self.config.get("voice_sentence"))
        self.audio_speed_var      = tk.StringVar(value=self.config.get("audio_speed"))
        self.notetype_var         = tk.StringVar(value=self.config.get("notetype_name"))
        self.filter_var           = tk.StringVar(value="All")
        self.card_select_var      = tk.BooleanVar(value=True)
        self.select_summary_var   = tk.StringVar(value="Select words ▾")

        self._build_styles()
        self._build_ui()
        self._center()
        self._check_deps()
        self._offer_resume_session()

    def _build_styles(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure(".", background=self.BG, foreground=self.TEXT,
                    font=("Segoe UI", 10))
        s.configure("Surface.TFrame", background=self.SURFACE)
        s.configure("Sidebar.TFrame", background=self.SIDEBAR_BG)
        s.configure("Primary.TButton",
                    background=self.ACCENT, foreground="#FFFFFF",
                    font=("Segoe UI", 10, "bold"),
                    padding=(18, 10), relief="flat", borderwidth=0)
        s.map("Primary.TButton",
              background=[("active", self.ACCENT_HOVER), ("disabled", self.BORDER)],
              foreground=[("disabled", self.TEXT_MUTED)])
        s.configure("Danger.TButton",
                    background="#DC2626", foreground="#FFFFFF",
                    font=("Segoe UI", 10, "bold"),
                    padding=(12, 8), relief="flat", borderwidth=0)
        s.map("Danger.TButton",
              background=[("active","#B91C1C"),("disabled",self.BORDER)])
        s.configure("Soft.TButton",
                    background=self.ACCENT_SOFT, foreground=self.ACCENT,
                    font=("Segoe UI", 9, "bold"),
                    padding=(10, 6), relief="flat", borderwidth=0)
        s.map("Soft.TButton",
              background=[("active","#E0E7FF"),("disabled",self.BORDER)],
              foreground=[("active",self.ACCENT_HOVER)])
        s.configure("Ghost.TButton",
                    background=self.BG, foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 9),
                    padding=(8, 5), relief="flat", borderwidth=0)
        s.map("Ghost.TButton", foreground=[("active",self.ACCENT)],
              background=[("active",self.BORDER)])
        s.configure("Treeview", background=self.SURFACE, foreground=self.TEXT,
                    rowheight=28, fieldbackground=self.SURFACE,
                    font=("Segoe UI", 9), borderwidth=0)
        s.configure("Treeview.Heading", background="#F1F5F9", foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 9, "bold"), relief="flat", padding=(6, 6))
        s.map("Treeview",
              background=[("selected",self.ACCENT_SOFT)],
              foreground=[("selected",self.ACCENT_HOVER)])
        s.configure("TNotebook", background=self.BG, borderwidth=0, tabmargins=(0,4,0,0))
        s.configure("TNotebook.Tab", background=self.BG, foreground=self.TEXT_MUTED,
                    font=("Segoe UI", 10, "bold"), padding=(18, 10), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected",self.SURFACE)],
              foreground=[("selected",self.ACCENT)])
        s.configure("TProgressbar", troughcolor=self.BORDER, background=self.ACCENT,
                    thickness=6, borderwidth=0)
        s.configure("TCombobox", fieldbackground=self.ENTRY_BG, background=self.SURFACE,
                    foreground=self.TEXT, arrowcolor=self.TEXT_MUTED, borderwidth=1,
                    relief="flat", padding=4)

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg=self.SURFACE)
        hdr.pack(fill=tk.X)
        tk.Frame(hdr, bg=self.ACCENT, width=4).pack(side=tk.LEFT, fill=tk.Y)
        ih = tk.Frame(hdr, bg=self.SURFACE)
        ih.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16,20), pady=12)
        tk.Label(ih, text="German Anki", bg=self.SURFACE, fg=self.TEXT,
                 font=("Segoe UI Semibold", 16)).pack(side=tk.LEFT)
        tk.Label(ih, text="  Generator", bg=self.SURFACE, fg=self.ACCENT,
                 font=("Segoe UI Semibold", 16)).pack(side=tk.LEFT)
        tk.Label(ih, text="  v9  ·  3 card types  ·  edge-tts  ·  unique audio",
                 bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(8,0))
        self.status_lbl = tk.Label(ih, text="● Ready", bg=self.SURFACE, fg=self.SUCCESS,
                                   font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(side=tk.RIGHT)
        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill=tk.X)

        bot = tk.Frame(self.root, bg=self.SURFACE, pady=12)
        bot.pack(fill=tk.X, padx=20, side=tk.BOTTOM)
        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)

        prog_frame = tk.Frame(bot, bg=self.SURFACE)
        prog_frame.pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate", length=220, maximum=100)
        self.progress.pack(side=tk.LEFT)
        self.progress_lbl = tk.Label(prog_frame, text="", bg=self.SURFACE,
                                     fg=self.TEXT_MUTED, font=("Segoe UI", 9), width=8)
        self.progress_lbl.pack(side=tk.LEFT, padx=(8,0))

        self.stop_btn = ttk.Button(bot, text="Stop", style="Danger.TButton",
                                   command=self._stop_processing, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=(12,0))
        self.retry_btn = ttk.Button(bot, text="Retry failed", style="Soft.TButton",
                                    command=self._retry_failed, state="disabled")
        self.retry_btn.pack(side=tk.LEFT, padx=(8,0))

        ttk.Button(bot, text="Open output folder", style="Ghost.TButton",
                   command=self._open_folder).pack(side=tk.RIGHT, padx=(8,0))
        self.gen_btn = ttk.Button(bot, text="Generate files + audio",
                                  style="Primary.TButton", command=self._generate)
        self.gen_btn.pack(side=tk.RIGHT)

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(16,0))

        sidebar = tk.Frame(body, bg=self.SIDEBAR_BG, width=240,
                           highlightbackground=self.BORDER, highlightthickness=1)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0,16))
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        nb_frame = tk.Frame(body, bg=self.BG)
        nb_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_notebook(nb_frame)

    def _build_sidebar(self, parent):
        sb_canvas = tk.Canvas(parent, bg=self.SIDEBAR_BG, highlightthickness=0)
        sb_scroll = ttk.Scrollbar(parent, orient="vertical", command=sb_canvas.yview)
        sb_canvas.configure(yscrollcommand=sb_scroll.set)
        sb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        sb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(sb_canvas, bg=self.SIDEBAR_BG)
        inner_id = sb_canvas.create_window((0,0), window=inner, anchor="nw")
        sb_canvas.bind("<Configure>", lambda e: sb_canvas.itemconfig(inner_id, width=e.width))
        inner.bind("<Configure>", lambda e: sb_canvas.configure(scrollregion=sb_canvas.bbox("all")))
        def _mw(e): sb_canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        sb_canvas.bind("<MouseWheel>",_mw); inner.bind("<MouseWheel>",_mw)

        def sec(t): tk.Label(inner, text=t, bg=self.SIDEBAR_BG, fg=self.TEXT_MUTED,
                              font=("Segoe UI", 8, "bold")).pack(padx=18, pady=(18,6), anchor="w")
        def line(): tk.Frame(inner, bg=self.BORDER, height=1).pack(fill=tk.X, padx=14, pady=8)

        sec("OPTIONS")
        for text, var, key in [
            ("Image via Pixabay",  self.use_pixabay_var, "use_pixabay"),
            ("Sentence audio",     self.sent_audio_var,  "sentence_audio"),
            ("Dark mode (restart)",tk.BooleanVar(value=self.config.get("dark_mode")), "dark_mode"),
        ]:
            tk.Checkbutton(inner, text=text, variable=var,
                           bg=self.SIDEBAR_BG, fg=self.TEXT,
                           selectcolor=self.ACCENT_SOFT,
                           activebackground=self.SIDEBAR_BG,
                           activeforeground=self.TEXT,
                           font=("Segoe UI", 9), cursor="hand2",
                           command=lambda k=key, v=var: self.config.set(k, v.get())
                           ).pack(padx=18, pady=3, anchor="w")

        line(); sec("DECK NAME")
        de = tk.Entry(inner, textvariable=self.deck_name_var,
                      bg=self.ENTRY_BG, fg=self.TEXT, relief="flat", bd=0,
                      font=("Segoe UI", 9), insertbackground=self.TEXT)
        de.pack(padx=18, pady=(0,6), fill=tk.X, ipady=6, ipadx=8)
        de.bind("<FocusOut>", lambda e: self.config.set("deck_name", self.deck_name_var.get()))

        line(); sec("NATIVE LANGUAGE")
        lc = ttk.Combobox(inner, textvariable=self.native_lang_var,
                          values=NATIVE_LANGUAGES, state="readonly",
                          font=("Segoe UI", 9))
        lc.pack(padx=18, pady=(0,6), fill=tk.X)
        lc.bind("<<ComboboxSelected>>", self._on_lang_change)

        line(); sec("GENDER COLOR KEY")
        for art, color in GENDER_COLORS.items():
            label = art if art else "(none)"
            row = tk.Frame(inner, bg=self.SIDEBAR_BG); row.pack(padx=18, pady=2, anchor="w")
            tk.Label(row, text="●", bg=self.SIDEBAR_BG, fg=color,
                     font=("Segoe UI", 13)).pack(side=tk.LEFT)
            tk.Label(row, text=f"  {label}", bg=self.SIDEBAR_BG, fg=self.TEXT,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)

        line(); sec("WORD TYPES")
        for wt, col in TYPE_COLORS.items():
            row = tk.Frame(inner, bg=self.SIDEBAR_BG); row.pack(padx=18, pady=2, anchor="w")
            tk.Label(row, text=f"  {wt.upper()}  ", bg=col, fg=TYPE_TEXT[wt],
                     font=("Segoe UI", 8, "bold"), padx=4, pady=2).pack(side=tk.LEFT)

        line(); sec(f"FIELDS ({len(UNIVERSAL_FIELDS)})")
        for i, f in enumerate(UNIVERSAL_FIELDS, 1):
            tk.Label(inner, text=f"{i:2d}.  {f}", bg=self.SIDEBAR_BG, fg=self.TEXT_MUTED,
                     font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, padx=18, pady=1)
        tk.Frame(inner, bg=self.SIDEBAR_BG, height=16).pack()

    def _build_notebook(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.pack(fill=tk.BOTH, expand=True)
        tabs = [
            ("  Input  ",    self._build_word_input_tab),
            ("  Preview  ",  self._build_preview_tab),
            ("  Stats  ",    self._build_stats_tab),
            ("  Prompts  ",  self._build_prompt_tab),
            ("  Settings  ", self._build_settings_tab),
        ]
        for label, builder in tabs:
            f = ttk.Frame(self.nb, style="Surface.TFrame", padding=18)
            self.nb.add(f, text=label)
            builder(f)

    def _build_word_input_tab(self, parent):
        tk.Label(parent, text="Words to process",
                 bg=self.SURFACE, fg=self.TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0,4))
        tk.Label(parent,
                 text="Separate by commas or new lines. Mixed types fine: "
                      "Haus, gehen, groß, Guten Morgen.",
                 bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0,14))

        entry_row = tk.Frame(parent, bg=self.SURFACE)
        entry_row.pack(fill=tk.X, pady=(0,12))
        wrap = tk.Frame(entry_row, bg=self.BORDER, bd=1)
        wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.word_box = tk.Text(wrap, height=5, font=("Segoe UI", 11),
                                bg=self.ENTRY_BG, fg=self.TEXT, relief="flat", bd=0,
                                insertbackground=self.TEXT, padx=12, pady=10,
                                wrap=tk.WORD, yscrollcommand=vsb.set,
                                highlightthickness=0)
        self.word_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self.word_box.yview)

        btn_col = tk.Frame(entry_row, bg=self.SURFACE)
        btn_col.pack(side=tk.LEFT, padx=(10,0), fill=tk.Y)
        ttk.Button(btn_col, text="Paste", style="Soft.TButton",
                   command=self._paste_words).pack(fill=tk.X, pady=2)
        ttk.Button(btn_col, text="Clear", style="Ghost.TButton",
                   command=lambda: self.word_box.delete(1.0, tk.END)).pack(fill=tk.X, pady=2)
        ttk.Button(btn_col, text="History", style="Ghost.TButton",
                   command=self._show_history).pack(fill=tk.X, pady=2)

        proc_row = tk.Frame(parent, bg=self.SURFACE)
        proc_row.pack(fill=tk.X, pady=(2,10))
        self.process_btn = ttk.Button(proc_row, text="Process words",
                                      style="Primary.TButton",
                                      command=self._start_api_processing)
        self.process_btn.pack(side=tk.LEFT)
        self.api_status_lbl = tk.Label(proc_row, text="", bg=self.SURFACE,
                                       fg=self.TEXT_MUTED, font=("Segoe UI", 9))
        self.api_status_lbl.pack(side=tk.LEFT, padx=14)

        queue_row = tk.Frame(parent, bg=self.SURFACE)
        queue_row.pack(fill=tk.X, pady=(0,14))
        tk.Label(queue_row, text="Queue", bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.queue_lbl = tk.Label(queue_row, text="—", bg=self.SURFACE,
                                  fg=self.TEXT, font=("Segoe UI", 9))
        self.queue_lbl.pack(side=tk.LEFT, padx=10)

        tk.Label(parent, text="Live log", bg=self.SURFACE, fg=self.TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(4,6))
        log_wrap = tk.Frame(parent, bg=self.BORDER, bd=1)
        log_wrap.pack(fill=tk.BOTH, expand=True)
        self.log_box = scrolledtext.ScrolledText(
            log_wrap, font=("Consolas", 9), bg=self.LOG_BG, fg=self.LOG_FG,
            relief="flat", bd=0, insertbackground=self.LOG_INFO,
            padx=14, pady=12, state="disabled", wrap=tk.WORD)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        for tag, fg in [("ok",self.LOG_OK),("err",self.LOG_ERR),
                        ("info",self.LOG_INFO),("warn",self.WARN)]:
            self.log_box.tag_configure(tag, foreground=fg)
        self._log("Ready. Enter words above and click Process words.", "info")

    def _build_preview_tab(self, parent):
        top = tk.Frame(parent, bg=self.SURFACE)
        top.pack(fill=tk.X, pady=(0,10))

        nav = tk.Frame(top, bg=self.SURFACE)
        nav.pack(side=tk.LEFT)
        ttk.Button(nav, text="◀", style="Ghost.TButton",
                   command=self._prev_entry).pack(side=tk.LEFT)
        self.entry_combo = tk.Button(nav, textvariable=self.select_summary_var,
                                     bg=self.ENTRY_BG, fg=self.TEXT,
                                     activebackground=self.ACCENT_SOFT,
                                     activeforeground=self.ACCENT_HOVER,
                                     relief="flat", bd=0, font=("Segoe UI", 10),
                                     padx=14, pady=6, cursor="hand2",
                                     command=self._open_entry_dropdown)
        self.entry_combo.pack(side=tk.LEFT, padx=6)
        ttk.Button(nav, text="▶", style="Ghost.TButton",
                   command=self._next_entry).pack(side=tk.LEFT)

        audio_row = tk.Frame(top, bg=self.SURFACE)
        audio_row.pack(side=tk.LEFT, padx=(16,0))
        ttk.Button(audio_row, text="♪ Word", style="Soft.TButton",
                   command=self._play_word_audio).pack(side=tk.LEFT)
        ttk.Button(audio_row, text="♪ Sentence", style="Soft.TButton",
                   command=self._play_sentence_audio).pack(side=tk.LEFT, padx=6)

        right = tk.Frame(top, bg=self.SURFACE)
        right.pack(side=tk.RIGHT)
        ttk.Button(right, text="Delete", style="Ghost.TButton",
                   command=self._delete_entry).pack(side=tk.RIGHT, padx=(6,0))
        ttk.Button(right, text="Select all", style="Ghost.TButton",
                   command=self._select_all).pack(side=tk.RIGHT, padx=(6,0))
        fc = ttk.Combobox(right, textvariable=self.filter_var,
                          values=["All","noun","verb","adjective","phrase"],
                          state="readonly", width=10, font=("Segoe UI", 9))
        fc.pack(side=tk.RIGHT, padx=(6,0))
        fc.bind("<<ComboboxSelected>>", lambda e: self._refresh_preview())
        tk.Label(right, text="Filter", bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT)
        self.count_lbl = tk.Label(right, text="0 entries", bg=self.SURFACE,
                                  fg=self.TEXT_MUTED, font=("Segoe UI", 9))
        self.count_lbl.pack(side=tk.RIGHT, padx=(0,10))

        badge_row = tk.Frame(parent, bg=self.SURFACE)
        badge_row.pack(fill=tk.X, pady=(0,8))
        self.type_badge   = tk.Label(badge_row, text="", bg="#E2E8F0",
                                     fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold"),
                                     padx=10, pady=3)
        self.type_badge.pack(side=tk.LEFT, padx=(0,6))
        self.gender_badge = tk.Label(badge_row, text="", bg="#E2E8F0",
                                     fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold"),
                                     padx=10, pady=3)
        self.gender_badge.pack(side=tk.LEFT, padx=(0,6))
        self.image_badge  = tk.Label(badge_row, text="", bg="#E2E8F0",
                                     fg=self.TEXT_MUTED, font=("Segoe UI", 8),
                                     padx=8, pady=3)
        self.image_badge.pack(side=tk.LEFT, padx=(0,6))
        self.thumb_label  = tk.Label(badge_row, bg=self.SURFACE, text="")
        self.thumb_label.pack(side=tk.LEFT, padx=(0,6))

        tk.Label(badge_row,
                 text="Double-click any cell to edit",
                 bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 8, "italic")).pack(side=tk.RIGHT)

        tree_wrap = tk.Frame(parent, bg=self.BORDER, bd=1)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical")
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal")
        self.tree = ttk.Treeview(tree_wrap, columns=("#","Field","Value"),
                                 show="headings",
                                 yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        self.tree.heading("#", text="#")
        self.tree.heading("Field", text="Field")
        self.tree.heading("Value", text="Value")
        self.tree.column("#",     width=40,  minwidth=32,  stretch=False)
        self.tree.column("Field", width=180, minwidth=140, stretch=False)
        self.tree.column("Value", width=720, minwidth=340)
        for tag, bg in [("noun","#EFF6FF"),("verb","#FFFBEB"),
                        ("adj","#F0FDF4"),("phrase","#FDF4FF"),
                        ("pron","#FEF9C3"),("sent","#ECFDF5"),
                        ("audio","#F0FDF4"),("empty","#FAFAFA"),("shared",self.SURFACE)]:
            self.tree.tag_configure(tag, background=bg)
        self.tree.tag_configure("highlight", background="#FFF7ED")
        self.tree.tag_configure("empty", foreground="#CBD5E1")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _build_stats_tab(self, parent):
        tk.Label(parent, text="Lifetime statistics",
                 bg=self.SURFACE, fg=self.TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0,4))
        tk.Label(parent, text="Counts from anki_output/backups/",
                 bg=self.SURFACE, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0,18))
        self.stats_frame = tk.Frame(parent, bg=self.SURFACE)
        self.stats_frame.pack(fill=tk.X)
        ttk.Button(parent, text="Refresh", style="Soft.TButton",
                   command=self._refresh_stats).pack(anchor="w", pady=(18,0))
        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=tk.X, pady=18)
        tk.Label(parent, text="Current session", bg=self.SURFACE,
                 fg=self.TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0,8))
        self.session_stats_lbl = tk.Label(parent, text="0 words this session",
                                          bg=self.SURFACE, fg=self.TEXT_MUTED,
                                          font=("Segoe UI", 10))
        self.session_stats_lbl.pack(anchor="w")
        self._refresh_stats()

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children(): w.destroy()
        s = load_stats()
        for i, (label, count, color) in enumerate([
            ("Total words",s["total"],self.ACCENT),
            ("Nouns",s["noun"],"#2563EB"),
            ("Verbs",s["verb"],"#92400E"),
            ("Adjectives",s["adjective"],"#15803D"),
            ("Phrases",s["phrase"],"#7E22CE"),
            ("Sessions",s["sessions"],self.TEXT_MUTED),
        ]):
            cell = tk.Frame(self.stats_frame, bg=self.SURFACE, padx=14, pady=12)
            cell.grid(row=i//3, column=i%3, padx=8, pady=6, sticky="w")
            tk.Label(cell, text=str(count), bg=self.SURFACE, fg=color,
                     font=("Segoe UI Semibold", 30)).pack(anchor="w")
            tk.Label(cell, text=label, bg=self.SURFACE, fg=self.TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(self.stats_frame,
                 text=f"→ {s['total']*2} Anki cards total (2 card types × {s['total']} words)",
                 bg=self.SURFACE, fg=self.TEXT_MUTED, font=("Segoe UI", 9)
                 ).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(8,0))
        nn = len(self.parsed_data)
        n  = sum(1 for e in self.parsed_data if e.get("word_type")=="noun")
        v  = sum(1 for e in self.parsed_data if e.get("word_type")=="verb")
        a  = sum(1 for e in self.parsed_data if e.get("word_type")=="adjective")
        p  = sum(1 for e in self.parsed_data if e.get("word_type")=="phrase")
        self.session_stats_lbl.config(
            text=f"{nn} words  ·  {n} nouns  ·  {v} verbs  ·  {a} adj  ·  {p} phrases")

    def _build_prompt_tab(self, parent):
        bar = tk.Frame(parent, bg=self.SURFACE)
        bar.pack(fill=tk.X, pady=(0,10))
        tk.Label(bar, text="Prompt viewer", bg=self.SURFACE, fg=self.TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side=tk.LEFT)

        toggle = tk.Frame(bar, bg=self.SURFACE)
        toggle.pack(side=tk.LEFT, padx=(20,0))
        for value, text in [("generation","Generation prompt"),
                            ("verification","Verification prompt")]:
            rb = tk.Radiobutton(toggle, text=text, variable=self._prompt_mode,
                                value=value, bg=self.SURFACE, fg=self.TEXT,
                                selectcolor=self.ACCENT_SOFT,
                                activebackground=self.SURFACE,
                                activeforeground=self.ACCENT,
                                font=("Segoe UI", 9, "bold"), cursor="hand2",
                                command=self._refresh_prompt_box)
            rb.pack(side=tk.LEFT, padx=(0,10))

        ttk.Button(bar, text="Copy", style="Soft.TButton",
                   command=self._copy_prompt).pack(side=tk.RIGHT)

        frame = tk.Frame(parent, bg=self.BORDER, bd=1)
        frame.pack(fill=tk.BOTH, expand=True)
        self.prompt_box = scrolledtext.ScrolledText(
            frame, font=("Consolas", 9), wrap=tk.WORD, relief="flat", bd=0,
            bg=self.ENTRY_BG, fg=self.TEXT, padx=14, pady=12, state="disabled")
        self.prompt_box.pack(fill=tk.BOTH, expand=True)
        self._refresh_prompt_box()

    def _build_settings_tab(self, parent):
        canvas = tk.Canvas(parent, bg=self.SURFACE, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg=self.SURFACE)
        win = canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        canvas.bind("<MouseWheel>",_mw); inner.bind("<MouseWheel>",_mw)

        cols = [tk.Frame(inner, bg=self.SURFACE) for _ in range(4)]
        for i, c in enumerate(cols):
            c.grid(row=0, column=i, sticky="nsew",
                   padx=(0 if i==0 else 20, 0), pady=6)
        for i in range(4):
            inner.grid_columnconfigure(i, weight=1, uniform="col")

        col_keys, col_pipeline, col_audio, col_export = cols

        def sec(p,t):
            tk.Label(p,text=t,bg=self.SURFACE,fg=self.ACCENT,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w",pady=(12,6))
        def sep(p): tk.Frame(p,bg=self.BORDER,height=1).pack(fill=tk.X,pady=10)
        def lbl(p,t):
            tk.Label(p,text=t,bg=self.SURFACE,fg=self.TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w",pady=(0,3))
        def ent(p,var,show=""):
            e = tk.Entry(p,textvariable=var,font=("Segoe UI", 9),
                         bg=self.ENTRY_BG,fg=self.TEXT,relief="flat",bd=0,show=show,
                         insertbackground=self.TEXT)
            e.pack(fill=tk.X,pady=(0,8),ipady=6,ipadx=8)
            return e

        sec(col_keys, "API keys")
        for title, hint, ck, la, ca, va in [
            ("Gemini", "aistudio.google.com · free",
             "gemini_keys","_gemini_lb","_gemini_cl","_gemini_nv"),
            ("Groq", "console.groq.com · free",
             "groq_keys","_groq_lb","_groq_cl","_groq_nv"),
            ("Custom", "Any OpenAI-compatible endpoint",
             "custom_keys","_custom_lb","_custom_cl","_custom_nv"),
        ]:
            tk.Label(col_keys,text=title,bg=self.SURFACE,fg=self.TEXT,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w",pady=(10,2))
            tk.Label(col_keys,text=hint,bg=self.SURFACE,fg=self.TEXT_MUTED,
                     font=("Segoe UI", 8)).pack(anchor="w",pady=(0,4))
            kf = tk.Frame(col_keys,bg=self.BORDER,bd=1); kf.pack(fill=tk.X)
            lb = tk.Listbox(kf,font=("Consolas", 8),bg=self.SURFACE,fg=self.TEXT,
                            selectbackground=self.ACCENT_SOFT,
                            selectforeground=self.ACCENT_HOVER,
                            relief="flat",bd=0,activestyle="none",height=3,
                            highlightthickness=0)
            lbsb = ttk.Scrollbar(kf,command=lb.yview)
            lb.configure(yscrollcommand=lbsb.set)
            lb.pack(side=tk.LEFT,fill=tk.X,expand=True)
            lbsb.pack(side=tk.RIGHT,fill=tk.Y)
            setattr(self,la,lb)
            nv = tk.StringVar(); setattr(self,va,nv)
            ar = tk.Frame(col_keys,bg=self.SURFACE); ar.pack(fill=tk.X,pady=(4,0))
            en = tk.Entry(ar,textvariable=nv,font=("Consolas", 8),
                          bg=self.ENTRY_BG,fg=self.TEXT,relief="flat",bd=0,show="●",
                          insertbackground=self.TEXT)
            en.pack(side=tk.LEFT,fill=tk.X,expand=True,padx=(0,6),ipady=5,ipadx=6)
            en.bind("<Return>", lambda e,_ck=ck,_la=la,_ca=ca,_va=va:
                    self._add_key(_ck,_la,_ca,_va))
            ttk.Button(ar,text="Add",style="Soft.TButton",
                       command=lambda _ck=ck,_la=la,_ca=ca,_va=va:
                       self._add_key(_ck,_la,_ca,_va)).pack(side=tk.LEFT)
            br = tk.Frame(col_keys,bg=self.SURFACE); br.pack(fill=tk.X,pady=(4,8))
            ttk.Button(br,text="Remove",style="Ghost.TButton",
                       command=lambda _ck=ck,_la=la,_ca=ca:
                       self._remove_key(_ck,_la,_ca)).pack(side=tk.LEFT)
            ttk.Button(br,text="Paste",style="Ghost.TButton",
                       command=lambda _va=va,_ck=ck,_la=la,_ca=ca:
                       self._paste_key(_va,_ck,_la,_ca)).pack(side=tk.LEFT,padx=4)
            cl = tk.Label(col_keys,text="0 keys",bg=self.SURFACE,
                          fg=self.TEXT_MUTED,font=("Segoe UI", 8))
            cl.pack(anchor="w",pady=(0,2)); setattr(self,ca,cl)
            self._refresh_key_list(ck,la,ca)

        ttk.Button(col_keys,text="Test active provider",style="Soft.TButton",
                   command=self._test_keys).pack(anchor="w",pady=(10,0))

        sec(col_pipeline, "Generator")
        lbl(col_pipeline,"Provider")
        pf = tk.Frame(col_pipeline,bg=self.SURFACE); pf.pack(anchor="w",pady=(0,8))
        for p in PROVIDERS:
            tk.Radiobutton(pf,text=p,variable=self.provider_var,value=p,
                           bg=self.SURFACE,fg=self.TEXT,selectcolor=self.ACCENT_SOFT,
                           activebackground=self.SURFACE,activeforeground=self.ACCENT,
                           font=("Segoe UI", 9),cursor="hand2",
                           command=lambda: self.config.set("provider",self.provider_var.get())
                           ).pack(anchor="w",pady=2)

        lbl(col_pipeline,"Gemini model")
        gm = ttk.Combobox(col_pipeline,textvariable=self.gemini_model_var,
                          values=GEMINI_MODELS,state="readonly",font=("Segoe UI", 9))
        gm.pack(fill=tk.X,pady=(0,6))
        gm.bind("<<ComboboxSelected>>",
                lambda e: self.config.set("gemini_model",self.gemini_model_var.get()))

        lbl(col_pipeline,"Groq model")
        grm = ttk.Combobox(col_pipeline,textvariable=self.groq_model_var,
                           values=GROQ_MODELS,state="readonly",font=("Segoe UI", 9))
        grm.pack(fill=tk.X,pady=(0,6))
        grm.bind("<<ComboboxSelected>>",
                 lambda e: self.config.set("groq_model",self.groq_model_var.get()))

        sep(col_pipeline)
        sec(col_pipeline,"Custom provider")
        lbl(col_pipeline,"Base URL")
        eu = ent(col_pipeline,self.custom_base_url_var)
        eu.bind("<FocusOut>",
                lambda e: self.config.set("custom_base_url",self.custom_base_url_var.get()))
        lbl(col_pipeline,"Model name")
        em = ent(col_pipeline,self.custom_model_var)
        em.bind("<FocusOut>",
                lambda e: self.config.set("custom_model",self.custom_model_var.get()))

        sep(col_pipeline)
        sec(col_pipeline,"Verifier")
        tk.Checkbutton(col_pipeline,text="Enable verification pass",
                       variable=self.verifier_enabled_var,
                       bg=self.SURFACE,fg=self.TEXT,selectcolor=self.ACCENT_SOFT,
                       activebackground=self.SURFACE,activeforeground=self.ACCENT,
                       font=("Segoe UI", 9),cursor="hand2",
                       command=lambda: self.config.set("verifier_enabled",
                                                       self.verifier_enabled_var.get())
                       ).pack(anchor="w",pady=(0,6))
        lbl(col_pipeline,"Verifier provider")
        vpf = tk.Frame(col_pipeline,bg=self.SURFACE); vpf.pack(anchor="w",pady=(0,6))
        for p in PROVIDERS:
            tk.Radiobutton(vpf,text=p,variable=self.verifier_provider_var,value=p,
                           bg=self.SURFACE,fg=self.TEXT,selectcolor=self.ACCENT_SOFT,
                           activebackground=self.SURFACE,activeforeground=self.ACCENT,
                           font=("Segoe UI", 9),cursor="hand2",
                           command=lambda: self.config.set("verifier_provider",
                                                           self.verifier_provider_var.get())
                           ).pack(anchor="w",pady=2)
        lbl(col_pipeline,"Verifier Gemini model")
        vgm = ttk.Combobox(col_pipeline,textvariable=self.verifier_gmodel_var,
                           values=GEMINI_MODELS,state="readonly",font=("Segoe UI", 9))
        vgm.pack(fill=tk.X,pady=(0,6))
        vgm.bind("<<ComboboxSelected>>",
                 lambda e: self.config.set("verifier_gemini_model",self.verifier_gmodel_var.get()))
        lbl(col_pipeline,"Verifier Groq model")
        vrm = ttk.Combobox(col_pipeline,textvariable=self.verifier_rmodel_var,
                           values=GROQ_MODELS,state="readonly",font=("Segoe UI", 9))
        vrm.pack(fill=tk.X,pady=(0,6))
        vrm.bind("<<ComboboxSelected>>",
                 lambda e: self.config.set("verifier_groq_model",self.verifier_rmodel_var.get()))
        lbl(col_pipeline,"Verifier Custom model")
        evc = ent(col_pipeline,self.verifier_cmodel_var)
        evc.bind("<FocusOut>",
                 lambda e: self.config.set("verifier_custom_model",self.verifier_cmodel_var.get()))

        sep(col_pipeline)
        sec(col_pipeline,"Retry")
        tk.Checkbutton(col_pipeline,text="Auto-retry on failures",
                       variable=self.overnight_var,
                       bg=self.SURFACE,fg=self.TEXT,selectcolor=self.ACCENT_SOFT,
                       activebackground=self.SURFACE,activeforeground=self.ACCENT,
                       font=("Segoe UI", 9),cursor="hand2",
                       command=lambda: self.config.set("overnight_mode",self.overnight_var.get())
                       ).pack(anchor="w",pady=(0,6))
        tk.Checkbutton(col_pipeline,text="Notify when finished",
                       variable=self.notify_var,
                       bg=self.SURFACE,fg=self.TEXT,selectcolor=self.ACCENT_SOFT,
                       activebackground=self.SURFACE,activeforeground=self.ACCENT,
                       font=("Segoe UI", 9),cursor="hand2",
                       command=lambda: self.config.set("notify_on_complete",self.notify_var.get())
                       ).pack(anchor="w",pady=(0,8))
        for label, var, key, lo, hi in [
            ("Max retries", self.max_retries_var,  "max_retries", 1, 20),
            ("Backoff (sec)", self.backoff_base_var, "backoff_base", 5, 120),
            ("Max passes", self.max_passes_var, "max_overnight_passes", 1, 20),
        ]:
            lbl(col_pipeline, label)
            row = tk.Frame(col_pipeline,bg=self.SURFACE); row.pack(fill=tk.X,pady=(0,8))
            sc = ttk.Scale(row,from_=lo,to=hi,variable=var,orient=tk.HORIZONTAL)
            sc.pack(side=tk.LEFT,fill=tk.X,expand=True)
            tk.Label(row,textvariable=var,bg=self.SURFACE,fg=self.TEXT,
                     font=("Segoe UI", 9),width=4).pack(side=tk.LEFT,padx=(6,0))
            sc.bind("<ButtonRelease-1>",
                    lambda e,_k=key,_v=var: self.config.set(_k, round(_v.get(),1)))

        sec(col_audio,"Audio · word")
        lbl(col_audio,"Word voice")
        vw = ttk.Combobox(col_audio,textvariable=self.voice_word_var,
                          values=DE_VOICES,state="readonly",font=("Segoe UI", 9))
        vw.pack(fill=tk.X,pady=(0,6))
        vw.bind("<<ComboboxSelected>>",
                lambda e: self.config.set("voice_word",self.voice_word_var.get()))
        ttk.Button(col_audio,text="Preview word voice",style="Soft.TButton",
                   command=lambda: GermanAnkiGenerator().play_audio(
                       "Guten Morgen", self.voice_word_var.get(),
                       self.audio_speed_var.get())).pack(anchor="w",pady=(0,10))

        sep(col_audio)
        sec(col_audio,"Audio · sentence")
        lbl(col_audio,"Sentence voice")
        vs = ttk.Combobox(col_audio,textvariable=self.voice_sent_var,
                          values=DE_VOICES,state="readonly",font=("Segoe UI", 9))
        vs.pack(fill=tk.X,pady=(0,6))
        vs.bind("<<ComboboxSelected>>",
                lambda e: self.config.set("voice_sentence",self.voice_sent_var.get()))
        ttk.Button(col_audio,text="Preview sentence voice",style="Soft.TButton",
                   command=lambda: GermanAnkiGenerator().play_audio(
                       "Ich lerne Deutsch jeden Tag.",
                       self.voice_sent_var.get(),
                       self.audio_speed_var.get())).pack(anchor="w",pady=(0,10))

        sep(col_audio)
        sec(col_audio,"Speed")
        SPEED_OPTIONS = ["-50%","-40%","-30%","-20%","-10%","+0%","+10%","+20%"]
        lbl(col_audio,"Speech rate")
        sp = ttk.Combobox(col_audio,textvariable=self.audio_speed_var,
                          values=SPEED_OPTIONS,state="readonly",font=("Segoe UI", 9))
        sp.pack(fill=tk.X,pady=(0,6))
        sp.bind("<<ComboboxSelected>>",
                lambda e: self.config.set("audio_speed",self.audio_speed_var.get()))
        ttk.Button(col_audio,text="Preview at this speed",style="Soft.TButton",
                   command=lambda: GermanAnkiGenerator().play_audio(
                       "Guten Tag! Wie geht es Ihnen?",
                       self.voice_word_var.get(),
                       self.audio_speed_var.get())).pack(anchor="w",pady=(0,10))

        tk.Label(col_audio,
                 text="Available voices:\n"
                      "Conrad · male · narrator\n"
                      "Katja · female · natural\n"
                      "Amala · female · younger",
                 bg=self.SURFACE,fg=self.TEXT_MUTED,font=("Segoe UI", 8),
                 justify="left").pack(anchor="w",pady=(12,0))

        sec(col_export,"Export")
        lbl(col_export,"Deck name")
        de2 = ent(col_export,self.deck_name_var)
        de2.bind("<FocusOut>",lambda e: self.config.set("deck_name",self.deck_name_var.get()))

        lbl(col_export,"Native language")
        lc2 = ttk.Combobox(col_export,textvariable=self.native_lang_var,
                           values=NATIVE_LANGUAGES,state="readonly",font=("Segoe UI", 9))
        lc2.pack(fill=tk.X,pady=(0,8))
        lc2.bind("<<ComboboxSelected>>",self._on_lang_change)

        lbl(col_export,"Note type name")
        nte = ent(col_export,self.notetype_var)
        nte.bind("<FocusOut>",
                 lambda e: self.config.set("notetype_name",self.notetype_var.get()))

        lbl(col_export,"Delay between AI calls (seconds)")
        dr = tk.Frame(col_export,bg=self.SURFACE); dr.pack(fill=tk.X,pady=(0,8))
        self.delay_scale = ttk.Scale(dr,from_=0.5,to=15.0,variable=self.delay_var,
                                     orient=tk.HORIZONTAL,command=self._update_delay_lbl)
        self.delay_scale.pack(side=tk.LEFT,fill=tk.X,expand=True)
        self.delay_lbl = tk.Label(dr,text=f"{self.delay_var.get():.1f}s",
                                  bg=self.SURFACE,fg=self.TEXT,font=("Segoe UI", 9),width=5)
        self.delay_lbl.pack(side=tk.LEFT,padx=(6,0))

        sep(col_export)
        sec(col_export,"Pixabay images")
        pix_e = tk.Entry(col_export,textvariable=self.pixabay_key_var,font=("Segoe UI", 9),
                         bg=self.ENTRY_BG,fg=self.TEXT,relief="flat",bd=0,show="●",
                         insertbackground=self.TEXT)
        pix_e.pack(fill=tk.X,pady=(0,6),ipady=6,ipadx=8)
        pix_e.bind("<FocusOut>",
                   lambda e: self.config.set("pixabay_key",self.pixabay_key_var.get()))
        ttk.Button(col_export,text="Save Pixabay key",style="Soft.TButton",
                   command=self._save_pixabay_key).pack(anchor="w",pady=(0,6))
        tk.Label(col_export,text="pixabay.com/api/docs — free key",
                 bg=self.SURFACE,fg=self.TEXT_MUTED,font=("Segoe UI", 8)).pack(anchor="w")

    def _add_key(self, ck, la, ca, va):
        raw = getattr(self, va).get().strip()
        if not raw: return
        new_keys = [k.strip() for k in re.split(r'[\n,]+', raw) if k.strip()]
        existing = self.config.get(ck)
        for k in new_keys:
            if k not in existing: existing.append(k)
        self.config.set(ck, existing)
        getattr(self, va).set("")
        self._refresh_key_list(ck, la, ca)

    def _remove_key(self, ck, la, ca):
        lb = getattr(self, la); sel = lb.curselection()
        if not sel: return
        keys = self.config.get(ck)
        for i in reversed(sel):
            if i < len(keys): keys.pop(i)
        self.config.set(ck, keys); self._refresh_key_list(ck, la, ca)

    def _paste_key(self, va, ck, la, ca):
        try:
            content = (pyperclip.paste() if CLIPBOARD_AVAILABLE
                       else self.root.clipboard_get())
            if content:
                getattr(self, va).set(content.strip())
                self._add_key(ck, la, ca, va)
        except Exception: pass

    def _refresh_key_list(self, ck, la, ca):
        lb = getattr(self, la); lb.delete(0, tk.END)
        keys = self.config.get(ck)
        for k in keys:
            masked = (k[:6] + "●" * max(0, len(k)-10) + k[-4:]) if len(k) > 10 else k
            lb.insert(tk.END, masked)
        cl = getattr(self, ca)
        n = len(keys)
        cl.config(text=f"{n} key{'s' if n!=1 else ''}",
                  fg=self.SUCCESS if n > 0 else self.ERROR)

    def _save_pixabay_key(self):
        self.config.set("pixabay_key", self.pixabay_key_var.get())
        self._set_status("Pixabay key saved ✓", self.SUCCESS)
        self.root.after(2000, lambda: self._set_status("● Ready", self.SUCCESS))

    def _update_delay_lbl(self, val=None):
        v = self.delay_var.get()
        self.delay_lbl.config(text=f"{v:.1f}s")
        self.config.set("delay_seconds", round(v,1))

    # ─────────────────────────────────────────────────────────────────────────
    # HEARTBEAT
    # ─────────────────────────────────────────────────────────────────────────

    def _start_heartbeat(self, label):
        self._hb_label = label
        self._hb_start = time.time()
        self._hb_gen  += 1
        my_gen = self._hb_gen
        def tick():
            if my_gen != self._hb_gen: return
            elapsed = time.time() - self._hb_start
            self._set_status(f"⏳ {self._hb_label} — {elapsed:.0f}s", self.WARN)
            self.root.after(1000, tick)
        self.root.after(1000, tick)

    def _stop_heartbeat(self):
        self._hb_gen += 1

    # ─────────────────────────────────────────────────────────────────────────
    # PROCESSING
    # ─────────────────────────────────────────────────────────────────────────

    def _start_api_processing(self):
        if self._processing: return
        raw = self.word_box.get(1.0, tk.END).strip()
        if not raw:
            messagebox.showwarning("No words", "Enter words first."); return
        provider = self.provider_var.get()
        keys_map = {"Gemini":"gemini_keys","Groq":"groq_keys","Custom (OpenAI-compatible)":"custom_keys"}
        if not self.config.get(keys_map.get(provider,"")):
            messagebox.showwarning("No API keys",
                f"Add {provider} keys in Settings tab."); return
        words = [w.strip() for w in re.split(r'[,\n]+', raw) if w.strip()]
        if not words:
            messagebox.showwarning("No words", "Could not parse any words."); return

        seen = set()
        deduped = []
        for w in words:
            wl = w.strip().lower()
            if wl and wl not in seen:
                seen.add(wl)
                deduped.append(w.strip())
        if len(deduped) < len(words):
            self._log(f"ℹ Removed {len(words) - len(deduped)} duplicate(s) from the input list.", "info")
        words = deduped

        history = load_word_history()
        in_session = {str(e.get("target_word","")).strip().lower()
                      for e in self.parsed_data if e.get("target_word")}
        dupes_history = [w for w in words if w.strip().lower() in history]
        dupes_session = [w for w in words if w.strip().lower() in in_session]

        if dupes_history or dupes_session:
            lines = []
            if dupes_session:
                preview = ", ".join(dupes_session[:8]) + ("…" if len(dupes_session) > 8 else "")
                lines.append(f"In this session ({len(dupes_session)}): {preview}")
            if dupes_history:
                preview = ", ".join(dupes_history[:8]) + ("…" if len(dupes_history) > 8 else "")
                lines.append(f"Previously processed ({len(dupes_history)}): {preview}")
            msg = ("Duplicate words found:\n\n" + "\n\n".join(lines) +
                   "\n\nYes = process all (re-generate)\nNo = skip duplicates\nCancel = abort")
            choice = messagebox.askyesnocancel("Duplicates found", msg)
            if choice is None:
                return
            if choice is False:
                skip = {w.strip().lower() for w in dupes_history + dupes_session}
                words = [w for w in words if w.strip().lower() not in skip]
                self._log(f"ℹ Skipped {len(skip)} known word(s). "
                          f"Processing {len(words)} new word(s).", "info")
                if not words:
                    messagebox.showinfo("Nothing to do",
                        "All entered words have already been processed.")
                    return
            else:
                self._log(f"⚠ Proceeding with {len(dupes_history)+len(dupes_session)} "
                          f"duplicate(s) — they will be re-generated.", "warn")

        self.queue_lbl.config(text=f"{len(words)} word(s): {', '.join(words[:5])}{'…' if len(words)>5 else ''}")
        self._stop_flag = False; self._processing = True; self._overnight_pass = 0
        self.process_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.retry_btn.config(state="disabled")
        self.progress.config(maximum=len(words), value=0)
        self.progress_lbl.config(text=f"0/{len(words)}")
        self._set_status("⏳ Processing…", self.WARN)
        threading.Thread(target=self._api_worker, args=(words,), daemon=True).start()

    def _verify_with_retry(self, entry, word, ver_client, gen, max_retries, backoff_base):
        overnight = self.config.get("overnight_mode")
        attempts  = max_retries if overnight else 1
        last_err  = None
        for attempt in range(1, attempts + 1):
            if self._stop_flag: return None, "Stopped"
            if attempt > 1:
                wait = min(backoff_base * (2 ** (attempt - 2)), 1800)
                self._log(f"  ↻ Verifier retry {attempt}/{attempts} — wait {wait:.0f}s…", "warn")
                for _ in range(int(wait)):
                    if self._stop_flag: return None, "Stopped"
                    time.sleep(1)
                if self._stop_flag: return None, "Stopped"
            try:
                self._start_heartbeat(f"Verifying '{word}'")
                vp = (VERIFIER_PROMPT
                      .replace("<<WORD>>", word)
                      .replace("<<CARD_JSON>>", json.dumps(entry, ensure_ascii=False, indent=2)))
                raw = ver_client.generate(vp)
                self._stop_heartbeat()
                corrections = json.loads(gen.clean_json(raw))
                if not isinstance(corrections, dict):
                    raise ValueError("Verifier did not return a JSON object")
                return corrections, None
            except Exception as e:
                self._stop_heartbeat()
                last_err = str(e)
                self._log(f"  ✗ Verifier attempt {attempt}/{attempts}: {e}", "err")
        return None, last_err

    def _process_one_word(self, word, gen_client, ver_client, lang, use_pixabay, pix_key, gen):
        prompt = self._build_prompt(word, lang)
        self._start_heartbeat(f"Generating '{word}'")
        try:
            raw_text = gen_client.generate(prompt)
        except Exception as e:
            self._stop_heartbeat()
            return None, f"Generator error: {e}"
        self._stop_heartbeat()

        cleaned = gen.clean_json(raw_text)
        try:
            entry = json.loads(cleaned)
            if isinstance(entry, list) and entry: entry = entry[0]
            if not isinstance(entry, dict): raise ValueError("Not a JSON object")
        except Exception as e:
            return None, f"JSON parse error: {e}"

        if ver_client is not None:
            self._log("  🔍 Verifying…", "info")
            v_max_retries = int(self.config.get("max_retries"))
            v_backoff     = float(self.config.get("backoff_base"))
            corrections, verr = self._verify_with_retry(
                entry, word, ver_client, gen, v_max_retries, v_backoff)
            if corrections is not None:
                if corrections:
                    changed = []; rejected = []
                    for k, v in corrections.items():
                        if k not in VERIFIER_APPLY_FIELDS: continue
                        old = entry.get(k, "")
                        new = "" if v is None else str(v).strip()
                        if old and not new:
                            rejected.append(f"{k} (empty overwrite rejected)"); continue
                        if k == "target_word" and old != new:
                            rejected.append(f"{k} (protected)"); continue
                        if str(old) == new: continue
                        entry[k] = new
                        changed.append(f"{k}: {str(old)[:40]} → {new[:40]}")
                    for c in changed:  self._log(f"  ✏ {c}", "warn")
                    for r in rejected: self._log(f"  ⛔ {r}", "warn")
                    if not changed and not rejected:
                        self._log("  ✓ Verified — no changes", "ok")
                else:
                    self._log("  ✓ Verified — no changes", "ok")
            else:
                entry["_unverified"] = "yes"
                self._log(f"  ⚠ Unverified — kept generator output ({verr})", "warn")

        if use_pixabay and pix_key:
            img = PixabayClient.fetch(entry.get("target_word",word),
                                      entry.get("english_translation",word),
                                      entry.get("sense_hint",""),
                                      entry.get("word_type",""), pix_key)
            if img:
                entry["image_url"] = img
                self._log(f"  🖼 {img[:55]}{'…' if len(img)>55 else ''}", "ok")
            elif entry.get("word_type") == "noun":
                self._log("  🖼 No image found", "warn")
        return entry, None

    def _api_worker(self, words):
        provider     = self.provider_var.get()
        delay        = float(self.config.get("delay_seconds"))
        use_pixabay  = self.config.get("use_pixabay")
        pix_key      = self.config.get("pixabay_key")
        lang         = self.config.get("native_language")
        overnight    = self.config.get("overnight_mode")
        max_retries  = int(self.config.get("max_retries"))
        backoff_base = float(self.config.get("backoff_base"))

        try:
            gen_client = make_client(provider, self.config)
        except Exception as e:
            self._log(f"✗ Cannot create generator: {e}", "err")
            self.root.after(0, lambda: self._on_api_done([], words, words)); return
        ver_client = None
        try:
            ver_client = make_verifier(self.config)
        except Exception as e:
            self._log(f"⚠ Verifier unavailable: {e}", "warn")

        gen = GermanAnkiGenerator()
        results: List[Dict] = []; failed: List[str] = []

        model = (self.config.get("gemini_model") if provider=="Gemini"
                 else self.config.get("groq_model") if provider=="Groq"
                 else self.config.get("custom_model"))
        ver_info = ""
        if ver_client:
            vp = self.config.get("verifier_provider","Gemini")
            vm = (self.config.get("verifier_gemini_model") if vp=="Gemini"
                  else self.config.get("verifier_groq_model") if vp=="Groq"
                  else self.config.get("verifier_custom_model"))
            ver_info = f" → Verifier: {vp}/{vm}"

        self._log(f"AI: {provider}/{model}{ver_info}", "info")
        self._log(f"Retry: {'on' if overnight else 'off'} · "
                  f"Retries: {max_retries} · Backoff: {backoff_base}s", "info")
        self._log("─"*60, "info")

        for i, word in enumerate(words):
            if self._stop_flag:
                self._log("⏹ Stopped.", "warn")
                failed.extend(words[i:]); break
            self._log(f"[{i+1}/{len(words)}] '{word}'", "info")
            self._api_status(f"{i+1}/{len(words)}: {word}")
            self.root.after(0, lambda i=i, n=len(words): (
                self.progress.configure(value=i),
                self.progress_lbl.configure(text=f"{i}/{n}")))

            entry = None; last_err = None
            attempts = max_retries if overnight else 1
            for attempt in range(1, attempts+1):
                if self._stop_flag: break
                if attempt > 1:
                    wait = min(backoff_base * (2**(attempt-2)), 1800)
                    self._log(f"  ↻ Retry {attempt}/{attempts} — wait {wait:.0f}s…", "warn")
                    for _ in range(int(wait)):
                        if self._stop_flag: break
                        time.sleep(1)
                    if self._stop_flag: break
                entry, err = self._process_one_word(
                    word, gen_client, ver_client, lang, use_pixabay, pix_key, gen)
                if entry is not None: last_err = None; break
                else: last_err = err; self._log(f"  ✗ {err}", "err")

            if entry is not None:
                results.append(entry)
                wt  = entry.get("word_type","?")
                art = entry.get("article","")
                tw  = entry.get("target_word", word)
                en  = entry.get("english_translation","")
                tail = "  ⚠ unverified" if entry.get("_unverified") == "yes" else ""
                self._log(f"  ✓ [{wt}] {(art+' ') if art else ''}{tw} → {en}{tail}", "ok")
            else:
                failed.append(word)
                self._log(f"  ✗ '{word}' exhausted all retries.", "err")

            if delay > 0 and i < len(words)-1 and not self._stop_flag:
                self._log(f"  ⏱ {delay}s…", "info")
                time.sleep(delay)

        self._log("─"*60, "info")
        unverified_n = sum(1 for e in results if e.get("_unverified") == "yes")
        self._log(f"Pass done — {len(results)} succeeded, {len(failed)} failed.",
                  "ok" if not failed else "warn")
        if unverified_n:
            self._log(f"  ⚠ {unverified_n} entr{'y' if unverified_n==1 else 'ies'} "
                      f"could not be verified.", "warn")
        if failed: self._log(f"Failed: {', '.join(failed)}", "err")
        self.root.after(0, lambda: self._on_api_done(results, failed, words))

    def _on_api_done(self, results, failed, all_words):
        self._processing = False; self._stop_flag = False
        self._failed_words = failed
        if results:
            self.parsed_data = list(self.parsed_data) + results
            self._card_select_vars += [tk.BooleanVar(value=True) for _ in results]
            save_session(self.parsed_data)
            append_word_history([e.get("target_word","") for e in results])
            self._refresh_preview()
            if hasattr(self, "session_stats_lbl"): self._refresh_stats()

        overnight  = self.config.get("overnight_mode")
        max_passes = int(self.config.get("max_overnight_passes"))
        if overnight and failed and not self._stop_flag and self._overnight_pass < max_passes:
            self._overnight_pass += 1
            self._log(f"🌙 Pass {self._overnight_pass}/{max_passes} — "
                      f"retrying {len(failed)} word(s)…", "warn")
            self._processing = True
            self.process_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            threading.Thread(target=self._api_worker, args=(failed,), daemon=True).start()
            return

        self._overnight_pass = 0
        self.process_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.retry_btn.config(state="normal" if failed else "disabled")
        n = len(all_words)
        self.progress.config(value=n, maximum=max(n,1))
        self.progress_lbl.config(text=f"{n}/{n}")
        self._api_status(""); self.queue_lbl.config(text="—")
        if results or self.parsed_data:
            self._set_status(f"✓ {len(self.parsed_data)} words ready", self.SUCCESS)
            self.nb.select(1)
        else:
            self._set_status("⚠ No results — check log", self.ERROR)
        if self.config.get("notify_on_complete") and not self._stop_flag:
            msg = f"German Anki: {len(self.parsed_data)} words done. {len(failed)} failed."
            try:
                if sys.platform == "win32":
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, msg, "German Anki — Done", 0x40)
                elif sys.platform == "darwin":
                    os.system(f'osascript -e "display notification \\"{msg}\\" with title \\"German Anki\\""')
                else:
                    os.system(f'notify-send "German Anki" "{msg}" 2>/dev/null || true')
            except Exception: pass

    def _retry_failed(self):
        if not self._failed_words: return
        self.word_box.delete(1.0, tk.END)
        self.word_box.insert(tk.END, ", ".join(self._failed_words))
        self._failed_words = []
        self.retry_btn.config(state="disabled")
        self._start_api_processing()

    def _stop_processing(self):
        self._stop_flag = True
        self._log("Stop requested…", "warn")

    def _build_prompt(self, word, lang):
        return MASTER_PROMPT.replace("<<LANG>>", lang).replace("<<WORD>>", word)

    def _refresh_prompt_box(self):
        mode = self._prompt_mode.get()
        if mode == "generation":
            prompt = self._build_prompt("<<YOUR WORD>>", self.native_lang_var.get())
        else:
            sample = self.parsed_data[0] if self.parsed_data else {
                "target_word":"Beispiel","word_type":"noun","article":"das",
                "plural":"die Beispiele","english_translation":"example"}
            prompt = (VERIFIER_PROMPT
                      .replace("<<WORD>>", sample.get("target_word","Beispiel"))
                      .replace("<<CARD_JSON>>",
                               json.dumps(sample, ensure_ascii=False, indent=2)))
        self.prompt_box.config(state="normal")
        self.prompt_box.delete(1.0, tk.END)
        self.prompt_box.insert(tk.END, prompt)
        self.prompt_box.config(state="disabled")

    def _on_lang_change(self, event=None):
        self.config.set("native_language", self.native_lang_var.get())
        self._refresh_prompt_box()

    def _copy_prompt(self):
        mode = self._prompt_mode.get()
        if mode == "generation":
            prompt = self._build_prompt("<<YOUR WORD>>", self.native_lang_var.get())
        else:
            prompt = VERIFIER_PROMPT
        if CLIPBOARD_AVAILABLE: pyperclip.copy(prompt)
        else: self.root.clipboard_clear(); self.root.clipboard_append(prompt)
        self._set_status("Copied ✓", self.SUCCESS)
        self.root.after(2000, lambda: self._set_status("● Ready", self.SUCCESS))

    def _refresh_preview(self):
        data = self.parsed_data
        flt  = self.filter_var.get()
        labels = []; self._filtered_indices = []
        for i, item in enumerate(data):
            wt = item.get("word_type","")
            if flt != "All" and wt != flt: continue
            art  = item.get("article","")
            word = item.get("target_word","?")
            unv  = "  ⚠" if item.get("_unverified") == "yes" else ""
            labels.append(f"[{wt}] {(art+' ') if art else ''}{word}{unv}")
            self._filtered_indices.append(i)
        self._preview_labels = labels

        total = len(data)
        checked = sum(1 for v in self._card_select_vars if v.get()) if self._card_select_vars else 0
        if labels:
            self.select_summary_var.set(f"{checked}/{total} selected  ▾")
        else:
            self.select_summary_var.set("No entries  ▾")

        self.count_lbl.config(text=f"{len(labels)}/{total} entries" if flt!="All" else f"{total} entries")
        if labels:
            self._current_preview_idx = len(labels)-1
            self._show_entry()

    def _open_entry_dropdown(self):
        if not self.parsed_data:
            messagebox.showinfo("No entries", "No entries yet.")
            return
        checked_state = []
        for idx in self._filtered_indices:
            if idx < len(self._card_select_vars):
                checked_state.append(self._card_select_vars[idx].get())
            else:
                checked_state.append(True)
        self._dropdown_state = checked_state

        def on_change(local_idx, value):
            if local_idx == -1:
                for j, i in enumerate(self._filtered_indices):
                    if i < len(self._card_select_vars):
                        self._card_select_vars[i].set(value)
            else:
                real = self._filtered_indices[local_idx]
                if real < len(self._card_select_vars):
                    self._card_select_vars[real].set(value)
            total = len(self.parsed_data)
            checked = sum(1 for v in self._card_select_vars if v.get())
            self.select_summary_var.set(f"{checked}/{total} selected  ▾")

        CheckboxDropdown(self.root, self.entry_combo,
                         self._preview_labels, checked_state, on_change)

    def _show_entry(self):
        if not self.parsed_data: return
        for item in self.tree.get_children(): self.tree.delete(item)
        raw_idx = getattr(self, "_current_preview_idx", 0)
        if raw_idx < 0 or raw_idx >= len(self._filtered_indices): return
        idx = self._filtered_indices[raw_idx]
        if idx < 0 or idx >= len(self.parsed_data): return
        entry     = self.parsed_data[idx]
        word_type = entry.get("word_type","noun")
        article   = entry.get("article","")
        image_url = entry.get("image_url","")

        tc = TYPE_COLORS.get(word_type,"#E2E8F0")
        tt = TYPE_TEXT.get(word_type, self.TEXT_MUTED)
        self.type_badge.config(text=f" {word_type.upper()} ", bg=tc, fg=tt)
        self.gender_badge.config(
            text=f" {article} " if article else "",
            bg=GENDER_COLORS.get(article,"#E2E8F0"),
            fg="white" if article else self.TEXT_MUTED)
        self.image_badge.config(
            text=" Image " if image_url else " No image ",
            bg="#DCFCE7" if image_url else "#FEE2E2",
            fg=self.SUCCESS if image_url else "#DC2626")
        self.thumb_label.config(image="", text="")
        self._thumb_refs.clear()
        if image_url and PIL_AVAILABLE:
            def _load():
                tk_img = PixabayClient.fetch_thumbnail(image_url)
                if tk_img:
                    self._thumb_refs.append(tk_img)
                    self.root.after(0, lambda: self.thumb_label.config(image=tk_img))
            threading.Thread(target=_load, daemon=True).start()

        PRON_FIELDS = {"pronunciation_ipa","pronunciation_native","memory_tip"}
        SENT_FIELDS = {"german_sentence","english_sentence"}
        KEY_FIELDS  = {"english_translation","full_answer","collocations","notes"}
        TYPE_SPECIFIC = {
            "noun":{"article","plural","genitive","plural_only"},
            "verb":{"auxiliary","past_participle","present_3sg","preterite",
                    "separable","reflexive","valency"},
            "adjective":{"comparative","superlative"},
            "phrase":{"register"},
        }.get(word_type,set())
        type_tag = {"noun":"noun","verb":"verb","adjective":"adj","phrase":"phrase"}.get(word_type,"shared")

        for i, field in enumerate(UNIVERSAL_FIELDS, 1):
            if field in ("audio_word","audio_sentence"):
                value, tag = "[auto-generated mp3]", "audio"
            else:
                raw_val = entry.get(field,"")
                value   = str(raw_val) if raw_val else "—"
                if not raw_val:          tag = "empty"
                elif field in PRON_FIELDS: tag = "pron"
                elif field in SENT_FIELDS: tag = "sent"
                elif field in KEY_FIELDS:  tag = "highlight"
                elif field in TYPE_SPECIFIC: tag = type_tag
                else:                      tag = "shared"
            if len(value) > 200: value = value[:200] + "…"
            self.tree.insert("", tk.END, values=(i, field, value), tags=(tag,))

    def _prev_entry(self):
        i = getattr(self, "_current_preview_idx", 0)
        if i > 0:
            self._current_preview_idx = i-1
            self._show_entry()

    def _next_entry(self):
        i = getattr(self, "_current_preview_idx", 0)
        if i < len(self._filtered_indices)-1:
            self._current_preview_idx = i+1
            self._show_entry()

    def _select_all(self):
        for v in self._card_select_vars: v.set(True)
        self._refresh_preview()

    def _delete_entry(self):
        i = getattr(self, "_current_preview_idx", 0)
        if i < 0 or i >= len(self._filtered_indices): return
        idx = self._filtered_indices[i]
        if 0 <= idx < len(self.parsed_data):
            self.parsed_data.pop(idx)
            if idx < len(self._card_select_vars): self._card_select_vars.pop(idx)
            save_session(self.parsed_data)
            self._refresh_preview()

    def _on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell": return
        item = self.tree.focus()
        if not item: return
        col = self.tree.identify_column(event.x)
        if col != "#3": return
        values = self.tree.item(item, "values")
        if not values: return
        field = values[1]
        i = getattr(self, "_current_preview_idx", 0)
        if i < 0 or i >= len(self._filtered_indices): return
        idx = self._filtered_indices[i]
        if idx >= len(self.parsed_data): return
        entry = self.parsed_data[idx]
        current = str(entry.get(field,""))

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit: {field}")
        dialog.geometry("640x260")
        dialog.configure(bg=self.SURFACE)
        tk.Label(dialog, text=field, bg=self.SURFACE, fg=self.ACCENT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=20, pady=(16,6))
        txt = tk.Text(dialog, height=6, font=("Segoe UI", 10),
                      bg=self.ENTRY_BG, fg=self.TEXT, relief="flat",
                      padx=12, pady=10, wrap=tk.WORD, insertbackground=self.TEXT)
        txt.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0,10))
        txt.insert(tk.END, current)
        txt.focus_set()
        def save():
            entry[field] = txt.get(1.0, tk.END).strip()
            save_session(self.parsed_data)
            self._show_entry()
            dialog.destroy()
        ttk.Button(dialog, text="Save", style="Primary.TButton",
                   command=save).pack(side=tk.RIGHT, padx=20, pady=(0,16))
        ttk.Button(dialog, text="Cancel", style="Ghost.TButton",
                   command=dialog.destroy).pack(side=tk.RIGHT, padx=(0,6), pady=(0,16))

    def _play_word_audio(self):
        i = getattr(self, "_current_preview_idx", 0)
        if i < 0 or i >= len(self._filtered_indices): return
        idx = self._filtered_indices[i]
        if idx >= len(self.parsed_data): return
        entry = self.parsed_data[idx]
        art = entry.get("article",""); word = entry.get("target_word","")
        text = f"{art} {word}".strip() if art else word
        if text:
            GermanAnkiGenerator().play_audio(
                text, self.voice_word_var.get(), self.audio_speed_var.get())

    def _play_sentence_audio(self):
        i = getattr(self, "_current_preview_idx", 0)
        if i < 0 or i >= len(self._filtered_indices): return
        idx = self._filtered_indices[i]
        if idx >= len(self.parsed_data): return
        s = self.parsed_data[idx].get("german_sentence","")
        if s:
            GermanAnkiGenerator().play_audio(
                s, self.voice_sent_var.get(), self.audio_speed_var.get())

    def _get_selected_indices(self):
        sel = [i for i, v in enumerate(self._card_select_vars) if v.get()]
        return sel if len(sel) < len(self.parsed_data) else None

    def _generate(self):
        if not self.parsed_data:
            messagebox.showwarning("No data","Process words first."); return
        self.gen_btn.config(state="disabled")
        self.progress.config(mode="indeterminate"); self.progress.start(10)
        self._set_status("⏳ Generating…", self.WARN)
        def worker():
            gen = GermanAnkiGenerator()
            ok, msg, info = gen.process(
                data=self.parsed_data,
                deck_name=self.deck_name_var.get(),
                sentence_audio=self.sent_audio_var.get(),
                selected_indices=self._get_selected_indices(),
                voice_word=self.voice_word_var.get(),
                voice_sentence=self.voice_sent_var.get(),
                audio_speed=self.audio_speed_var.get(),
                progress_callback=lambda i,n,w: self.root.after(0, lambda i=i,n=n,w=w:
                    self._set_status(f"Audio {i}/{n}: {w}", self.WARN)),
            )
            self.root.after(0, lambda: self._on_generate_done(ok, msg, info))
        threading.Thread(target=worker, daemon=True).start()

    def _on_generate_done(self, ok, msg, info):
        self.progress.stop()
        self.progress.config(mode="determinate", value=100)
        self.gen_btn.config(state="normal")
        if ok:
            summary = (f"Done!\n\n"
                       f"  Entries:  {info['entries']}\n"
                       f"  Word audio:     {info['audio_word']}\n"
                       f"  Sentence audio: {info['audio_sent']}\n\n"
                       f"  File: {info['txt_path']}\n\n"
                       f"  Copy .mp3 files from:\n  {info['audio_dir']}\n"
                       f"  → Anki collection.media folder\n\n"
                       f"  Then import the .txt into Anki (separator: Tab).")
            self._set_status("✓ Files generated", self.SUCCESS)
            messagebox.showinfo("Done", summary)
        else:
            self._set_status(f"✗ {msg}", self.ERROR)
            messagebox.showerror("Error", msg)

    def _test_keys(self):
        provider = self.provider_var.get()
        self._log(f"Testing {provider} keys…", "info")
        def run():
            try:
                client = make_client(provider, self.config)
                result = client.generate("Reply with one word: OK")
                self._log(f"  ✓ {provider} key works — response: {result[:40]}", "ok")
            except Exception as e:
                self._log(f"  ✗ {provider}: {e}", "err")
        threading.Thread(target=run, daemon=True).start()

    def _show_history(self):
        h = load_word_history()
        if not h:
            messagebox.showinfo("History","No words processed yet."); return
        top = tk.Toplevel(self.root); top.title("Word History")
        top.geometry("440x460"); top.configure(bg=self.SURFACE)
        st = scrolledtext.ScrolledText(top, font=("Consolas", 9),
                                       bg=self.SURFACE, fg=self.TEXT,
                                       relief="flat", bd=0, padx=14, pady=14)
        st.pack(fill=tk.BOTH, expand=True)
        st.insert(tk.END, f"{len(h)} words processed:\n\n" + "\n".join(sorted(h)))
        st.config(state="disabled")

    def _paste_words(self):
        try:
            content = (pyperclip.paste() if CLIPBOARD_AVAILABLE
                       else self.root.clipboard_get())
            if content:
                self.word_box.delete(1.0, tk.END)
                self.word_box.insert(tk.END, content)
        except Exception: pass

    def _open_folder(self):
        folder = Path("anki_output"); folder.mkdir(exist_ok=True)
        if sys.platform=="win32": os.startfile(str(folder))
        elif sys.platform=="darwin": os.system(f'open "{folder}"')
        else: os.system(f'xdg-open "{folder}"')

    def _set_status(self, msg, color=None):
        self.status_lbl.config(text=msg, fg=color or self.SUCCESS)

    def _log(self, msg, tag=""):
        def _do():
            self.log_box.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert(tk.END, f"[{ts}] {msg}\n", tag if tag else "")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")
        self.root.after(0, _do)

    def _api_status(self, msg):
        self.root.after(0, lambda: self.api_status_lbl.config(text=msg))

    def _center(self):
        self.root.update_idletasks()
        w=self.root.winfo_width(); h=self.root.winfo_height()
        x=(self.root.winfo_screenwidth()-w)//2; y=(self.root.winfo_screenheight()-h)//2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _check_deps(self):
        if GENAI_SDK_AVAILABLE:  self._log("AI: Gemini ✓", "ok")
        else:                    self._log("AI: Gemini ✗ — pip install google-genai", "err")
        if GROQ_SDK_AVAILABLE:   self._log("AI: Groq ✓", "ok")
        else:                    self._log("AI: Groq ✗ — pip install groq", "err")
        if EDGE_TTS_AVAILABLE:
            self._log("Audio: edge-tts ✓", "ok")
        else:
            self._log("Audio: edge-tts ✗ — pip install edge-tts", "err")
        if PIL_AVAILABLE:  self._log("Image thumbnails: Pillow ✓", "ok")
        pix = self.config.get("pixabay_key")
        if pix: self._log("Pixabay ✓  (nouns only)", "ok")
        else:   self._log("Pixabay key not set — add in Settings → Export", "warn")

    def _offer_resume_session(self):
        data = load_session()
        if not data: return
        if messagebox.askyesno("Resume session",
            f"Found {len(data)} word(s) from a previous session. Resume?"):
            self.parsed_data = data
            self._card_select_vars = [tk.BooleanVar(value=True) for _ in data]
            self._refresh_preview()
            self._set_status(f"Resumed {len(data)} words from last session", self.SUCCESS)
        else:
            clear_session()

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    try: root.iconbitmap(default="")
    except Exception: pass
    AnkiGeneratorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
