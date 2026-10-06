"""JARVIS desktop overlay: an always-on-top assistant that talks on screen.

A single Tkinter window shows an animated "core" orb whose look reflects the
current state (idle / listening / thinking / speaking), a live transcript, a
text box for typing, and an optional microphone toggle for hands-free voice.
All assistant logic stays in :class:`core.brain.Brain`; this file is only a
view controller. Network calls and text-to-speech run on a worker thread so the
window never freezes, and every UI change is marshalled back to Tk's main loop.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont

from core.logging_setup import get_logger

logger = get_logger("ui.desktop")

# --- palette ---------------------------------------------------------------
BG = "#0a0e14"
PANEL = "#0f1620"
INK = "#cfe8ff"
DIM = "#5c7793"
ACCENT = "#22d3ee"

STATE_COLORS = {
    "idle": ("#1e3a5f", "#2f6fb0", "#4aa3e0"),
    "listening": ("#123a34", "#1f9e7a", "#34d6a4"),
    "thinking": ("#4a3410", "#c8901f", "#ffc24a"),
    "speaking": ("#0d3a44", "#19a7c9", "#4fe3ff"),
}
STATE_LABELS = {
    "idle": "Standby",
    "listening": "Listening…",
    "thinking": "Thinking…",
    "speaking": "Speaking…",
}


def _color(state: str, idx: int) -> str:
    palette = STATE_COLORS.get(state, STATE_COLORS["idle"])
    value = palette[idx]
    return value if isinstance(value, str) and value.startswith("#") else palette[2]


class JarvisApp:
    def __init__(self, brain) -> None:
        self.brain = brain
        self.name = brain.settings.assistant_name

        self.state = "idle"
        self._phase = 0.0
        self._dyn: list[int] = []

        # Serialized actions keep the agent single-threaded.
        self._work: "queue.Queue[str]" = queue.Queue()
        # UI updates are pushed from any thread and applied only on the Tk loop.
        self._ui: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

        # Voice (built lazily so text-only use never needs numpy/whisper).
        self._listener = None
        self._listener_thread: threading.Thread | None = None
        self._listening = threading.Event()

        self.root = tk.Tk()
        self.root.title(f"{self.name.upper()}")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()
        self._position_window()
        self._bind_keys()

        # Brain fires events from the worker thread; they are queued and only
        # applied on the Tk main loop (tkinter is not thread-safe).
        self.brain.on_event = self._post

        self._start_worker()
        self.root.after(40, self._animate)
        self.root.after(20, self._drain_ui)
        self.root.after(150, self._on_greet)

    # --- layout -------------------------------------------------------------
    def _build_layout(self) -> None:
        self.ui_font = tkfont.Font(family="Segoe UI", size=11)
        self.title_font = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.small_font = tkfont.Font(family="Segoe UI", size=9)

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="J.A.R.V.I.S", font=self.title_font,
                 bg=BG, fg=ACCENT).pack(side="left")
        self.status_lbl = tk.Label(header, text="Standby", font=self.small_font,
                                   bg=BG, fg=DIM)
        self.status_lbl.pack(side="right", pady=(6, 0))

        self.canvas = tk.Canvas(outer, width=280, height=190, bg=PANEL,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", pady=(8, 8))

        self.transcript = tk.Text(
            outer, height=9, width=42, bg=PANEL, fg=INK, relief="flat",
            wrap="word", font=self.ui_font, insertbackground=INK,
            state="disabled", padx=10, pady=8, spacing1=4,
        )
        self.transcript.pack(fill="both", expand=True)
        self.transcript.tag_configure("user", foreground="#7fd1ff",
                                      justify="right")
        self.transcript.tag_configure("jarvis", foreground="#e6f4ff")
        self.transcript.tag_configure("sys", foreground=DIM,
                                      font=self.small_font)

        controls = tk.Frame(outer, bg=BG)
        controls.pack(fill="x", pady=(8, 0))
        self.entry = tk.Entry(controls, bg=PANEL, fg=INK, relief="flat",
                              insertbackground=INK, font=self.ui_font)
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self._send_from_entry())

        self._btn(controls, "Send", ACCENT, self._send_from_entry).pack(side="left")
        self.mic_btn = self._btn(controls, "🎙 Mic", DIM, self._toggle_mic)
        self.mic_btn.pack(side="left", padx=(6, 0))

    def _btn(self, parent, text, color, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=BG, fg=color,
                         activebackground=PANEL, activeforeground=INK,
                         relief="flat", bd=0, font=self.ui_font, cursor="hand2",
                         padx=12, pady=4, highlightthickness=0)

    def _position_window(self) -> None:
        w, h = 320, 560
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - w - 40
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(300, 460)

    def _bind_keys(self) -> None:
        self.root.bind("<Escape>", lambda e: self._on_close())

    # --- transcript & state (main-thread only) ------------------------------
    def _append(self, role: str, text: str) -> None:
        self.transcript.configure(state="normal")
        prefix = f"{self.name.title()}:  " if role == "jarvis" else ("You:  " if role == "user" else "")
        self.transcript.insert("end", prefix + text + "\n", role)
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def _set_state(self, state: str) -> None:
        self.state = state
        self.status_lbl.configure(text=STATE_LABELS.get(state, state))

    def _set_mic_button(self, on: bool) -> None:
        self.mic_btn.configure(fg="#34d6a4" if on else DIM)

    # --- cross-thread event plumbing ----------------------------------------
    def _post(self, event: dict) -> None:
        """Safe from any thread: enqueue a UI update for the Tk loop."""
        self._ui.put(event)

    def _drain_ui(self) -> None:
        if self._stop.is_set():
            return
        try:
            for _ in range(50):
                try:
                    event = self._ui.get_nowait()
                except queue.Empty:
                    break
                self._apply(event)
        except tk.TclError:
            return
        self.root.after(20, self._drain_ui)

    def _apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "user":
            self._append("user", event.get("text", ""))
        elif kind == "reply":
            self._append("jarvis", event.get("text", ""))
        elif kind == "sys":
            self._append("sys", event.get("text", ""))
        elif kind == "mic":
            self._set_mic_button(bool(event.get("on")))
        elif kind == "close":
            self._on_close()
        elif kind == "state":
            self._set_state(event.get("state", "idle"))

    # --- worker -------------------------------------------------------------
    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._work_loop, daemon=True)
        self._worker.start()

    def _work_loop(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._work.get(timeout=0.2)
            except queue.Empty:
                continue
            if text == "__greet__":
                try:
                    self.brain.announce(self.brain.greeting())
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Greeting failed: %s", exc)
                continue
            try:
                _, keep = self.brain.process(text)
                if not keep:
                    self._post({"type": "close"})
                    break
            except Exception as exc:  # noqa: BLE001 - one bad turn must not kill the loop
                logger.exception("Process failed")
                self._post({"type": "sys", "text": f"[error] {exc}"})
                self._post({"type": "state", "state": "idle"})

    def _submit(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self._work.put(text)

    def _send_from_entry(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._set_state("thinking")
        self._submit(text)

    def _on_greet(self) -> None:
        self._work.put("__greet__")

    # --- voice --------------------------------------------------------------
    def _toggle_mic(self) -> None:
        if self._listening.is_set():
            self._stop_mic()
        else:
            self._start_mic()

    def _start_mic(self) -> None:
        def setup() -> None:
            try:
                from voice.listener import VoiceListener
                from voice.microphone import Microphone
                from voice.speech_to_text import make_stt

                settings = self.brain.settings
                mic = Microphone(settings)
                if not mic.available():
                    raise RuntimeError("no microphone available")
                stt = make_stt(settings)
                stt.warmup()
                listener = VoiceListener(settings, stt, mic)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Voice unavailable: %s", exc)
                self._post({"type": "sys", "text": f"Voice not available: {exc}"})
                self._post({"type": "mic", "on": False})
                self._listening.clear()
                return

            self._listener = listener
            self._listening.set()
            self._post({"type": "sys", "text": "Microphone on — speak your command."})
            self._post({"type": "mic", "on": True})

            def heard(text: str) -> bool:
                if not self._listening.is_set():
                    return False
                self._post({"type": "state", "state": "thinking"})
                self._submit(text)
                return True

            try:
                listener.run(heard)
            finally:
                self._listening.clear()
                self._post({"type": "mic", "on": False})

        self._listener_thread = threading.Thread(target=setup, daemon=True)
        self._listener_thread.start()

    def _stop_mic(self) -> None:
        self._listening.clear()
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
        self._post({"type": "mic", "on": False})

    # --- animation ----------------------------------------------------------
    def _animate(self) -> None:
        if self._stop.is_set():
            return
        self._phase += 0.06
        try:
            self._draw()
        except tk.TclError:
            return
        self.root.after(33, self._animate)

    def _draw(self) -> None:
        c = self.canvas
        for item in self._dyn:
            c.delete(item)
        self._dyn.clear()

        cx = int(c["width"]) // 2
        cy = int(c["height"]) // 2
        pulse = (time.monotonic() * 1.6) % 1.0
        breath = 0.5 + 0.5 * pow(abs(sin_or(self._phase)), 1)

        base = 34
        rings = 4
        for i in range(rings, 0, -1):
            r = base + i * 12 + pulse * 10
            self._dyn.append(c.create_oval(cx - r, cy - r, cx + r, cy + r,
                                           outline=_color(self.state, 0), width=1))
        # core disc
        core_r = base + int(breath * 6)
        self._dyn.append(c.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r,
                                       fill=_color(self.state, 1), outline=_color(self.state, 2),
                                       width=2))
        self._dyn.append(c.create_oval(cx - core_r * 0.5, cy - core_r * 0.5,
                                       cx + core_r * 0.5, cy + core_r * 0.5,
                                       fill=_color(self.state, 2), outline=""))
        self._dyn.append(c.create_text(cx, cy, text=self.name.upper()[0],
                                       fill="#04121c", font=("Segoe UI", 20, "bold")))

        if self.state == "thinking":
            for k in range(3):
                ang = self._phase * 2 + k * (6.283 / 3)
                dx = cx + (core_r + 16) * cos_or(ang)
                dy = cy + (core_r + 16) * sin_or(ang)
                self._dyn.append(c.create_oval(dx - 4, dy - 4, dx + 4, dy + 4,
                                               fill=_color(self.state, 2), outline=""))
        elif self.state in ("speaking", "listening"):
            self._draw_wave(c, cx, cy, core_r)

    def _draw_wave(self, c, cx, cy, core_r) -> None:
        t = time.monotonic()
        bars = 9
        span = 150
        left = cx - span / 2
        for i in range(bars):
            x = left + i * (span / (bars - 1))
            amp = 6 + 10 * abs(sin_or(t * 4 + i * 0.9))
            self._dyn.append(c.create_line(x, cy - amp, x, cy + amp,
                                           fill=_color(self.state, 2), width=3))

    # --- lifecycle ----------------------------------------------------------
    def _on_close(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._stop_mic()
        try:
            self.brain.close()
        except Exception:  # noqa: BLE001
            logger.debug("brain.close error", exc_info=True)
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self.root.mainloop()


# small math shims so a bad import never breaks drawing
import math


def sin_or(x: float) -> float:
    try:
        return math.sin(x)
    except Exception:  # noqa: BLE001
        return 0.0


def cos_or(x: float) -> float:
    try:
        return math.cos(x)
    except Exception:  # noqa: BLE001
        return 0.0
