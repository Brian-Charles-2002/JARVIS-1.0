# J.A.R.V.I.S

A voice-enabled AI desktop assistant for Windows, powered by the Google Gemini API.

`Python 3.10–3.12` · `Windows 10 / 11` · `Gemini API` · `58 tools` · `Text / Voice / GUI modes`

---

You speak to it naturally. It understands intent, decides when it needs to *do*
something on your computer, calls a structured tool to act, verifies the result,
answers aloud, and keeps listening.

This is an **agent loop**, not a pile of hard-coded voice commands. Gemini only
proposes actions; the local safety layer decides what actually runs.

---

## Contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Running JARVIS](#running-jarvis)
- [The desktop overlay](#the-desktop-overlay)
- [Voice configuration](#voice-configuration)
- [Tool reference](#tool-reference)
- [Browser automation](#browser-automation)
- [Screen vision](#screen-vision)
- [Safety and permissions](#safety-and-permissions)
- [Adding a new tool](#adding-a-new-tool)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

---

## Highlights

| Capability | Details |
|---|---|
| Conversation memory | Resolves references such as "open it", "that folder", "the browser", "continue". |
| Speech in and out | Local `faster-whisper` transcription, `edge-tts` neural voices with a `pyttsx3` offline fallback. |
| Continuous voice loop | hear → transcribe → reason → act → speak → listen. |
| Native function calling | Gemini drives a central tool registry of 58 typed tools. |
| Multi-step tasks | Gemini chains several tools until the goal is reached, then verifies. |
| Computer control | Apps, browser, web search, filesystem, keyboard/mouse, clipboard, windows, screenshots, terminal. |
| Safety layer | Risk classification, permission checks, pending-action confirmation, prompt-injection defense. |
| Secret-aware logging | API keys, tokens and passwords are never stored or written to logs. |
| Three modes | Terminal text chat, hands-free voice, and a floating on-screen window. |

---

## Architecture

```
USER SPEAKS
   │
   ▼
SPEECH-TO-TEXT ──► GEMINI (intent) ──► respond or use a tool
                                            │
                                            ▼
                                  validate → permissions → confirmation
                                            │
                                            ▼
                                        EXECUTE ──► structured result
                                            │
                              next step ◄───┘
                                            │
                                            ▼
                              FINAL RESPONSE ──► TEXT-TO-SPEECH ──► LISTEN
```

### Module map

| Area | Path | Responsibility |
|---|---|---|
| Config | `config/settings.py` | Environment-driven settings for model, voice, safety and logging. |
| Brain | `ai/gemini_client.py` | `google-genai` SDK wrapper: retries, backoff, function calling. |
| Prompt | `ai/prompts.py` | The JARVIS system instruction. |
| Adapter | `ai/tool_adapter.py` | Converts tools and conversation into Gemini SDK types. |
| Agent | `core/agent.py` | The iterative decide / act / observe loop. |
| Tools | `tools/` | Registry plus every computer capability as a `BaseTool`. |
| Safety | `safety/`, `core/permissions.py` | Risk classification, confirmation, command validation. |
| Memory | `memory/`, `core/context.py` | Session and persistent memory, context bounding. |
| Voice | `voice/` | Microphone capture, VAD, STT, TTS, wake word, listener. |
| Desktop UI | `ui/desktop.py` | Tkinter overlay window and state animation. |
| Entry | `main.py` | Startup, mode selection, graceful shutdown. |

---

## Quick start

### Prerequisites

- Windows 10 or 11
- Python 3.10 – 3.12 (3.12 recommended)
- A Gemini API key, free from <https://aistudio.google.com/apikey>

### Installation

```powershell
# 1) create a virtual environment
python -m venv .venv

# 2) activate it
.venv\Scripts\Activate.ps1

# 3) install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4) create your configuration file
copy .env.example .env
notepad .env        # set GEMINI_API_KEY
```

If PowerShell blocks activation, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.

### Minimal core install

Heavy and hardware-dependent packages are imported lazily, so text mode runs
before they are installed. For the fastest path to a working agent:

```powershell
pip install google-genai python-dotenv pydantic psutil pytest
pip install pyperclip send2trash duckduckgo-search edge-tts pygame PyGetWindow PyAutoGUI
```

Whisper, Playwright and PyAutoGUI activate only when their packages are present.

### Configuration

Only two values are required:

```dotenv
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-flash-lite-latest
```

The key is never hard-coded and never logged; it is read from `.env` or the
environment, and `.env` is git-ignored. The model is configurable without
touching code. Defaults live in `config/settings.py`.

---

## Running JARVIS

```powershell
python main.py             # voice mode (microphone required)
python main.py --text      # text mode, terminal chat, no microphone
python main.py --gui       # floating on-screen assistant window
python main.py --debug     # verbose logging
python main.py --no-speak  # silence text-to-speech
```

A normal start looks like this:

```text
==================================================
                     J.A.R.V.I.S
              Personal AI Assistant
==================================================
[OK] Configuration loaded
[OK] Gemini connected
[OK] Tool registry loaded
[OK] Text-to-speech ready

Jarvis: Good evening. JARVIS online. How can I help?
```

In text mode you type at the `You >` prompt and JARVIS replies aloud. Say
`exit jarvis` to quit, or `cancel` to drop a pending action.

---

## The desktop overlay

```powershell
python main.py --gui
```

A small, always-on-top window that lives on your screen while you talk to it.
It reuses the same brain, tools, safety gate and TTS as text and voice modes —
the window is only a view controller.

- **Animated core orb** whose color and motion reflect the live state: blue
  standby, green listening, amber thinking with orbiting nodes, cyan speaking
  with audio bars.
- **Live transcript** of every line from you and from Jarvis, including
  confirmations and errors, auto-scrolled.
- **Type or speak.** Use the text box with Enter or the Send button, or click
  Mic for hands-free voice. The microphone is lazy-loaded, so text-only use
  never needs Whisper or NumPy.
- **Clean shutdown** via the close button, `Esc`, or saying `exit jarvis`.
  Memory, TTS and the browser session are released.

Threading: Gemini calls and speech run on a worker thread, and every window
update is marshalled through a UI queue onto Tk's main loop. The window never
freezes and Tkinter's single-thread rule is respected.

---

## Voice configuration

All voice knobs live in `.env`.

| Setting | Meaning | Default |
|---|---|---|
| `STT_BACKEND` | `local` (faster-whisper) or `recognition` (Google Web Speech) | `local` |
| `STT_MODEL` | Whisper size: `tiny`, `base.en`, `small`, `medium`, `large-v3` | `base.en` |
| `STT_COMPUTE_TYPE` | Whisper compute mode, for example `int8` or `float16` | `int8` |
| `SILENCE_THRESHOLD` | Floor for speech detection; the VAD actually triggers at `max(this, 5 x measured noise floor)`. Raise it only if fan noise wakes the assistant. | `0.004` |
| `END_SILENCE_DURATION` | Seconds of silence that end an utterance | `0.8` |
| `MAX_RECORDING_DURATION` | Hard cap per utterance, in seconds | `20.0` |
| `MIN_RECORDING_DURATION` | Shortest utterance accepted as speech | `0.4` |
| `SAMPLE_RATE` | Capture sample rate in Hz | `16000` |
| `MICROPHONE_DEVICE` | Device-name substring; empty means system default | *(empty)* |
| `TTS_ENGINE` | `edge`, `pyttsx3`, or `none` | `edge` |
| `TTS_VOICE` | An `edge-tts` voice, for example `en-GB-RyanNeural` | `en-GB-RyanNeural` |
| `TTS_RATE` | Words per minute for `pyttsx3` | `175` |
| `TTS_VOLUME` | `0.0` to `1.0` for `pyttsx3` | `1.0` |
| `WAKE_WORD_ENABLED` | Require "Jarvis, …" before acting | `false` |
| `WAKE_WORD` | The wake word itself | `jarvis` |

JARVIS pauses recognition while it speaks, so it never hears itself. Full-duplex
barge-in is designed for but not in this build.

---

## Tool reference

Every capability is a typed tool with a JSON schema, so Gemini can only call
what you have registered. Count: 58.

| Category | Tools |
|---|---|
| Applications | `open_application`, `close_application`, `get_running_apps`, `list_processes`, `is_process_running` |
| Browser (basic) | `open_url`, `open_browser`, `read_page`, `web_search` |
| Browser (automation) | `browser_navigate`, `browser_search`, `browser_get_text`, `browser_get_links`, `browser_click`, `browser_type`, `browser_scroll`, `browser_state`, `browser_close` |
| Filesystem | `list_directory`, `read_file`, `write_file`, `append_file`, `create_file`, `create_folder`, `delete_file`, `delete_folder`, `move_file`, `copy_file`, `rename_file`, `open_file`, `file_exists`, `get_file_info` |
| Keyboard and mouse | `press_key`, `hotkey`, `type_text`, `move_mouse`, `click_mouse`, `right_click`, `double_click`, `scroll` |
| Windows | `get_active_window`, `list_windows`, `focus_window` |
| Clipboard | `get_clipboard`, `set_clipboard` |
| System info | `get_system_info`, `get_cpu_usage`, `get_memory_usage`, `get_disk_usage`, `get_battery_status`, `get_network_status` |
| Power and time | `get_current_time`, `lock_computer`, `restart_computer`, `shutdown_computer` |
| Terminal | `run_terminal_command` |
| Screen | `take_screenshot`, `analyze_screen` |

Application discovery searches PATH, the registry App Paths key, Start Menu
shortcuts and common install directories. Add an explicit mapping in
`config/app_aliases.json` when a tool reports `APPLICATION_NOT_FOUND`:

```json
{
  "obs": "C:\\Program Files\\obs\\obs64.exe"
}
```

---

## Browser automation

`tools/browser_manager.py` keeps one Playwright Chromium session for the whole
task, so multi-step browsing reuses the same page. `browser_click` matches
visible text first and falls back to a CSS selector.

```powershell
pip install playwright
playwright install
```

The browser is headed (visible) by default so you can watch it work. Set
`BROWSER_HEADLESS=true` in `.env` to run it invisibly. The basic `open_url`,
`open_browser` and `web_search` tools need no Playwright at all.

---

## Screen vision

The `analyze_screen` tool captures the desktop and asks a multimodal Gemini
model to interpret it: "what's on my screen?", "read this error", "find the
download button".

It runs only when you ask. JARVIS never uploads screenshots in the background.
Implementation: `pyautogui` for capture, `ai/gemini_client.analyze_image` for
reasoning.

---

## Safety and permissions

Every tool carries a risk level:

```
SAFE  →  CAUTION  →  SENSITIVE  →  DESTRUCTIVE
```

Before anything executes, the request passes through:

1. Schema validation
2. Safety classification
3. Permission check
4. Confirmation prompt, if the risk requires it
5. Execution

Additional guarantees:

- Deletions prefer the Recycle Bin over permanent removal.
- Shutdown, restart and force operations always require an explicit `yes`.
- Web, file and screen content is treated as **data**, never as instructions —
  the prompt-injection defense.
- Passwords, tokens and API keys are never stored or logged.
- `CONFIRMATION_LEVEL` in `.env` sets the minimum risk that triggers a prompt
  (default `DESTRUCTIVE`).

---

## Adding a new tool

Subclass `BaseTool` in any `tools/*.py` module:

```python
from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does, shown to Gemini."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def run(self, target: str) -> ToolResult:
        return ToolResult.ok(self.name, {"target": target})
```

Register it in the `_ALL_TOOLS` list in `tools/__init__.py`. Gemini sees it
automatically and the safety layer enforces its risk level.

---

## Testing

```powershell
pip install pytest
python -m compileall -q .
pytest
```

Coverage includes configuration, tool registry, schema validation, filesystem
tools, permission and command-risk classification, the confirmation flow,
session and persistent memory including secret refusal, and context management.

The agent is tested against a fake Gemini client, so no test consumes API quota.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Missing key error on startup | Create `.env` from `.env.example` and set `GEMINI_API_KEY`. JARVIS exits with a clear message, not a stack trace. |
| `Gemini request failed` or rate limit | The client backs off and retries briefly. Try a different `GEMINI_MODEL`, or wait. |
| Whisper slow or model download blocked | Use `STT_MODEL=tiny` or `STT_BACKEND=recognition`. The first run downloads the model. |
| No sound from speech | `edge-tts` needs internet. Try `TTS_ENGINE=pyttsx3` for offline, or `--no-speak`. |
| `Microphone not available` | Check Windows Sound settings → Input, and confirm no other app holds exclusive access. Text mode still works. |
| It never hears me | Run with `--debug`. The log prints the measured noise floor and speech threshold, and warns after 5 silent seconds. If the threshold is far above your loudest block, the problem is Windows input volume or mic privacy access, not JARVIS. The VAD adapts to your mic, so do not raise `SILENCE_THRESHOLD` to fix this. |
| `APPLICATION_NOT_FOUND` | The app is not discoverable. Add its path to `config/app_aliases.json`. |
| App opens the wrong thing or fails with a split path | Update to the current `tools/applications.py`; spaced install paths such as `C:\Program Files\...` are passed as their own argument, not into a shell string. |

---

## Roadmap

- Wake word and interruption / barge-in in the voice loop.
- Windows UI-Automation tools beyond keyboard and mouse.
- Long-term semantic memory backed by a vector store.
- Additional provider backends behind the `AIProvider` abstraction.

---

## A note on hardware

Voice features (microphone capture, Whisper, audio playback) cannot be exercised
from a headless or CI environment. They are import-guarded and degrade
gracefully. Test them on your own machine with `python main.py` and a working
microphone.
