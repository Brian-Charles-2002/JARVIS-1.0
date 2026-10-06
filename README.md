# J.A.R.V.I.S — Personal AI Desktop Assistant

A conversational, **voice-enabled AI assistant for Windows** powered by the
**Google Gemini API** as its reasoning brain. You speak to it naturally; it
understands intent, decides when it needs to *do* something on your computer,
calls structured tools to act, verifies the result, answers aloud, and keeps
listening. It is an **agent loop**, not a pile of hard-coded voice commands.

> Build a reliable conversational Gemini-powered agent first, then progressively
> give it controlled computer abilities.

---

## 1. What it can do (current milestone)

- Natural conversation with **conversation memory** and **reference resolution**
  ("open it", "that folder", "the browser", "continue").
- **Speech-to-text** (local `faster-whisper`) and **text-to-speech** (`edge-tts`
  with a `pyttsx3` fallback).
- A continuous **voice loop**: hear → transcribe → reason → act → speak → listen.
- **Gemini native function/tool calling** through a central **tool registry**.
- **Multi-step tasks**: Gemini chains several tools until the goal is done.
- Windows tools: open/close apps, browser & URLs, web search, full filesystem
  operations, keyboard/mouse, clipboard, windows, screenshots, system info,
  terminal commands.
- **Safety layer**: risk classification, permission checks, a real
  **pending-action confirmation** system, destructive-action protection,
  prompt-injection defenses, and secret-aware logging (never logs API keys).
- **Text/debug mode** for working without a microphone.

## 2. Architecture

```
USER SPEAKS → SPEECH-TO-TEXT → GEMINI (intent) → decides respond-or-use-tool
   → VALIDATE tool → PERMISSION/CONFIRMATION → EXECUTE → structured result
   → back to GEMINI → next step ... → FINAL RESPONSE → TEXT-TO-SPEECH → LISTEN
```

Key modules:

| Area    | Path                | Responsibility                                         |
|---------|---------------------|-------------------------------------------------------|
| Config  | `config/settings.py`| Env-driven settings (model, voice, safety, logging).   |
| Brain   | `ai/gemini_client.py`| `google-genai` SDK wrapper, retries, function calling.|
| Prompt  | `ai/prompts.py`      | The JARVIS system instruction.                         |
| Adapter | `ai/tool_adapter.py` | Tools/conversation → Gemini SDK types.                 |
| Agent   | `core/agent.py`      | The iterative decide/act/observe loop.                 |
| Tools   | `tools/`             | Registry + every computer capability as a `BaseTool`.  |
| Safety  | `safety/`, `core/permissions.py` | Risk, confirmation, command validation.   |
| Memory  | `memory/`, `core/context.py`     | Session + persistent memory, context bounds.   |
| Voice   | `voice/`             | Mic, VAD, STT, TTS, wake word, listener.               |
| Entry   | `main.py`            | Startup, modes, graceful shutdown.                     |

## 3. Prerequisites

- **Windows 10 / 11**
- **Python 3.10 – 3.12** (3.12 recommended; the code lazy-imports heavy deps so
  text mode works even before voice libraries are installed)
- A **Gemini API key** — free at <https://aistudio.google.com/apikey>

## 4. Installation (from zero)

```powershell
# 1) create the virtual environment (Python 3.12 recommended)
python -m venv .venv

# 2) activate it
.venv\Scripts\Activate.ps1
# (PowerShell blocked? run:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

# 3) install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4) create your config
copy .env.example .env
# then edit .env and set GEMINI_API_KEY (and GEMINI_MODEL)
```

<details>
<summary><b>Minimal core install</b> (fastest way to a working text-mode agent)</summary>

```powershell
pip install google-genai python-dotenv pydantic psutil pytest
# optional light extras used by tools:
pip install pyperclip send2trash duckduckgo-search edge-tts pygame PyGetWindow PyAutoGUI
```
Whisper/Playwright/pyautogui are **imported lazily**, so voice/browser features
activate only once their packages are present. Text mode runs without them.
</details>

## 5. Configuring Gemini

Only two values are required:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash
```

- The key is **never** hard-coded and never logged — it comes from `.env` /
  environment variables. `.env` is git-ignored.
- The **model is configurable without touching code**. Change `GEMINI_MODEL`
  to any Gemini model you have access to. Defaults live in `config/settings.py`.

## 6. Running JARVIS

```powershell
python main.py            # voice mode (microphone required)
python main.py --text     # text mode — chat in the terminal, no microphone
python main.py --gui      # floating on-screen assistant window (typing + optional voice)
python main.py --debug    # verbose logging
python main.py --no-speak # silence TTS
```

Startup looks like:

```
==================================================
                     J.A.R.V.I.S
              Personal AI Assistant
==================================================
[✓] Configuration loaded
[✓] Gemini connected
[✓] Tool registry loaded
[✓] Text-to-speech ready

Jarvis: Good evening. JARVIS ONLINE. How can I help?
```

In text mode you type `You > ...`; JARVIS replies and speaks it. Say
`exit jarvis` to quit, `cancel` to drop a pending action.

### The desktop window (`--gui`)

`python main.py --gui` opens a small, always-on-top overlay that lives on your
screen while you talk to it. It reuses the same `Brain`, tools, safety gate and
TTS as text/voice mode — the window is only a view controller.

- **Animated core orb** — its color and motion reflect the live state:
  blue *Standby*, green *Listening…*, amber *Thinking…* (orbiting nodes),
  cyan *Speaking…* (audio bars).
- **Live transcript** — every "You" and "Jarvis" line, including confirmations
  and errors, scrolled automatically.
- **Type or speak** — use the text box (Enter or **Send**), or click **🎙 Mic**
  for hands-free voice. The mic is lazy-loaded, so text-only use never needs
  Whisper/numpy; if no microphone is present the button just reports that.
- **Close** — the ✕ button, `Esc`, or saying `exit jarvis` shuts JARVIS down
  cleanly (memory, TTS and the browser session are released).

Threading: Gemini calls and text-to-speech run on a worker thread, and all
window updates are marshalled through a UI queue onto Tk's main loop, so the
window never freezes and Tkinter's single-thread rule is respected.

## 7. Microphone / voice configuration

Voice knobs live in `.env`:

| Setting | Meaning |
|---------|---------|
| `STT_BACKEND` | `local` (faster-whisper) or `recognition` (Google Web Speech) |
| `STT_MODEL` | whisper size: `tiny`/`base.en`/`small`/`medium`/`large-v3` |
| `SILENCE_THRESHOLD` | RMS level that counts as speech (raise in noisy rooms) |
| `END_SILENCE_DURATION` | seconds of silence that ends an utterance |
| `MAX_RECORDING_DURATION` | hard cap per utterance |
| `MICROPHONE_DEVICE` | device-name substring; empty = system default |
| `TTS_ENGINE` | `edge` / `pyttsx3` / `none` |
| `TTS_VOICE` | an `edge-tts` voice (e.g. `en-GB-RyanNeural`) |
| `WAKE_WORD_ENABLED`, `WAKE_WORD` | optional "Jarvis, ..." gating |

JARVIS pauses recognition while it speaks, so it does not hear itself.
Full-duplex/barge-in is designed-for but not in this build.

## 8. Browser automation & vision

**Persistent browser session** — `tools/browser_manager.py` keeps one Playwright
Chromium session for the whole task, so multi-step browsing reuses the same
page: `browser_navigate`, `browser_search`, `browser_get_text`,
`browser_get_links` (to resolve "open the first result"), `browser_click`
(matches visible text first, then a CSS selector), `browser_type`,
`browser_scroll`, `browser_state`, `browser_close`. The browser is **headed
(visible)** by default so you can watch it; set `BROWSER_HEADLESS=true` in `.env`
to run it invisibly. Enable with:

```powershell
pip install playwright
playwright install
```

Basic `open_url` / `open_browser` / `web_search` need no Playwright.

**Screen vision** — the `analyze_screen` tool screenshots the desktop and asks a
multimodal Gemini model to interpret it ("what's on my screen?", "read this
error", "find the download button"). It runs **only** when you ask; JARVIS never
uploads screenshots in the background. It reuses `pyautogui` (capture) and
`ai/gemini_client.analyze_image` (reasoning).

## 9. Troubleshooting

- **Missing key error on startup** — create `.env` from `.env.example` and set
  `GEMINI_API_KEY`. JARVIS exits with a clear message, not a stack trace.
- **`Gemini request failed` / rate limit** — the client backs off and retries
  briefly; try a different `GEMINI_MODEL`, or wait.
- **Whisper slow / model download blocked** — use `STT_MODEL=tiny` or
  `STT_BACKEND=recognition`. First run downloads the model.
- **No sound from TTS** — `edge-tts` needs internet; try `TTS_ENGINE=pyttsx3`
  (offline) or `--no-speak`.
- **`Microphone not available`** — check Windows Sound settings → Input, and
  that no other app has exclusive access. Text mode still works.
- **`APPLICATION_NOT_FOUND`** — the app isn't discoverable; add its path to
  `config/app_aliases.json` (e.g. `{"chrome": "C:\\...\\chrome.exe"}`).

## 10. Adding a new tool

1. Subclass `BaseTool` in a `tools/*.py` module: set `name`, `description`,
   `risk` (from `safety.risk.RiskLevel`), a JSON-schema `parameters` block, and
   implement `run(...)` returning a `ToolResult`.
2. Register it in `tools/__init__.py`'s `_ALL_TOOLS`.
3. That's it — Gemini sees it automatically and the safety layer enforces its
   risk level.

## 11. Safety & permissions

Every tool carries a risk level: `SAFE → CAUTION → SENSITIVE → DESTRUCTIVE`.
Before execution: **schema validation → safety classification → permission
check → confirmation (if required) → execution**. Gemini only *proposes* actions;
the local app decides what runs. Deletions prefer the Recycle Bin; shutdown /
restart / force operations always require an explicit **yes**. Web/file/screen
content is treated as **data**, never as instructions (prompt-injection defense).
Passwords, tokens and keys are never stored or logged. `CONFIRMATION_LEVEL` in
`.env` sets the minimum risk that triggers a prompt (default `DESTRUCTIVE`).

## 12. Running tests

```powershell
pip install pytest
python -m compileall -q .
pytest
```

Tests cover configuration, tool registry/schemas/validation, filesystem tools,
permission & command-risk classification, confirmation flow, session +
persistent memory (including secret refusal), and context management. The agent
is tested with a **fake** Gemini client, so **no tests consume API quota**.

## 13. Roadmap (next phases)

Advanced Playwright browser sessions, Gemini **vision** ("what's on my screen?"),
wake-word + interruption/barge-in, Windows UI-Automation tools, long-term
semantic memory via a vector store, and more provider backends behind the
`AIProvider` abstraction.

## 14. Honest note on hardware

Voice features (microphone capture, Whisper, audio playback) cannot be exercised
from a headless/CI environment — they're import-guarded and degrade gracefully.
Test them on your own machine with `python main.py` and a working mic.
#   J A R V I S - 1 . 0  
 #   J A R V I S - 1 . 0  
 