"""EasyTranscribe: square, semi-transparent, draggable widget."""

import json
import os
import queue
import sys
import threading
import tkinter as tk

import customtkinter as ctk
from pynput import keyboard as pynput_keyboard
import pyperclip

from stt_engine import STTEngine

BACKGROUND = "#121212"
CARD = "#1E1E1E"
ACCENT = "#007AFF"
TEXT_COLOR = "#FFFFFF"
MUTED_TEXT = "#B0B0B0"
TITLE_BAR = "#181818"
TITLE_ACCENT = "#8FA8C9"

WINDOW_SIZE = 280
EDGE_MARGIN = 20
TITLE_BAR_HEIGHT = 25

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_NAME = "EasyTranscribe"


class EasyTranscribeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("Dark")

        self.title("EasyTranscribe")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.9)
        self.resizable(False, False)
        self.configure(fg_color=BACKGROUND)
        self.protocol("WM_DELETE_WINDOW", self._close_app)

        self._engine: STTEngine | None = None
        self._is_recording = False
        self._stop_event: threading.Event | None = None
        self._stream_thread: threading.Thread | None = None
        self._text_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._displayed_text = ""
        self._is_visible = True
        self._hotkey_listener: pynput_keyboard.GlobalHotKeys | None = None
        self._drag_offset: tuple[int, int] | None = None

        self._font = ("Segoe UI Variable", 12)
        self._font_bold = ("Segoe UI Variable", 13, "bold")

        self._settings = self._load_settings()
        self._is_locked = bool(self._settings.get("locked", False))
        self._saved_position = self._settings.get("position", {})
        self._start_with_windows = self._settings.get("start_with_windows")
        if self._start_with_windows is None:
            self._start_with_windows = self._get_startup_enabled()

        self._build_ui()
        self._position_window()
        self._apply_startup_setting()
        self._set_loading(True)
        self._load_engine_async()
        self._start_hotkey_listener()

    def _build_ui(self) -> None:
        self.title_bar = ctk.CTkFrame(
            self,
            width=WINDOW_SIZE,
            height=TITLE_BAR_HEIGHT,
            fg_color=TITLE_BAR,
            corner_radius=0,
        )
        self.title_bar.place(x=0, y=0)
        self.title_bar.bind("<ButtonPress-1>", self._on_drag_start)
        self.title_bar.bind("<B1-Motion>", self._on_drag_motion)
        self.title_bar.bind("<ButtonRelease-1>", self._on_drag_end)

        self.logo_label = ctk.CTkLabel(
            self.title_bar,
            width=40,
            height=TITLE_BAR_HEIGHT,
            text="ET",
            text_color=TITLE_ACCENT,
            font=self._font_bold,
        )
        self.logo_label.place(x=8, y=0)
        self.logo_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.logo_label.bind("<B1-Motion>", self._on_drag_motion)
        self.logo_label.bind("<ButtonRelease-1>", self._on_drag_end)

        self.lock_button = ctk.CTkButton(
            self.title_bar,
            width=46,
            height=18,
            text="Lock" if not self._is_locked else "Unlock",
            command=self._toggle_lock,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A",
            corner_radius=6,
            text_color=TEXT_COLOR,
            font=("Segoe UI Variable", 9, "bold"),
        )
        self.lock_button.place(x=WINDOW_SIZE - 92, y=3)

        self.close_button = ctk.CTkButton(
            self.title_bar,
            width=26,
            height=18,
            text="X",
            command=self._close_app,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A",
            corner_radius=6,
            text_color=TEXT_COLOR,
            font=self._font,
        )
        self.close_button.place(x=WINDOW_SIZE - 34, y=3)

        self.shortcut_label = ctk.CTkLabel(
            self.title_bar,
            width=90,
            height=14,
            text="Ctrl+Alt+S",
            text_color=MUTED_TEXT,
            font=("Segoe UI Variable", 8),
            anchor="e",
        )
        self.shortcut_label.place(x=WINDOW_SIZE - 190, y=5)

        self.header_label = ctk.CTkLabel(
            self,
            width=240,
            height=22,
            text="EasyTranscribe",
            text_color=TEXT_COLOR,
            font=self._font_bold,
        )
        self.header_label.place(x=20, y=32)

        self.status_var = tk.StringVar(value="Loading Model...")
        self.status_label = ctk.CTkLabel(
            self,
            width=240,
            height=18,
            textvariable=self.status_var,
            text_color=MUTED_TEXT,
            font=self._font,
        )
        self.status_label.place(x=20, y=54)

        self.record_button = ctk.CTkButton(
            self,
            width=120,
            height=34,
            text="Record",
            command=self._toggle_recording,
            fg_color=ACCENT,
            hover_color="#1E8CFF",
            corner_radius=12,
            text_color="white",
            font=self._font_bold,
        )
        self.record_button.place(relx=0.5, y=78, anchor="n")

        self.startup_var = tk.BooleanVar(value=bool(self._start_with_windows))
        self.startup_checkbox = ctk.CTkCheckBox(
            self,
            width=180,
            height=20,
            text="Start with Windows",
            variable=self.startup_var,
            command=self._on_startup_toggle,
            text_color=MUTED_TEXT,
            fg_color=ACCENT,
            hover_color="#1E8CFF",
            border_color="#2A2A2A",
            font=("Segoe UI Variable", 10),
        )
        self.startup_checkbox.place(x=20, y=112)

        self.text_area = ctk.CTkTextbox(
            self,
            width=240,
            height=92,
            wrap="word",
            fg_color=CARD,
            text_color=TEXT_COLOR,
            border_color="#2A2A2A",
            border_width=1,
            corner_radius=12,
            font=self._font,
        )
        self.text_area.place(x=20, y=134)

        footer_frame = ctk.CTkFrame(
            self,
            width=240,
            height=32,
            fg_color="transparent",
        )
        footer_frame.place(x=20, y=230)
        footer_frame.grid_columnconfigure(0, weight=1)
        footer_frame.grid_columnconfigure(1, weight=1)

        self.copy_button = ctk.CTkButton(
            footer_frame,
            width=110,
            height=32,
            text="Copy",
            command=self._copy_text,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A",
            corner_radius=12,
            text_color=TEXT_COLOR,
            font=self._font_bold,
        )
        self.copy_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.clear_button = ctk.CTkButton(
            footer_frame,
            width=110,
            height=32,
            text="Clear",
            command=self._clear_text,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A",
            corner_radius=12,
            text_color=TEXT_COLOR,
            font=self._font_bold,
        )
        self.clear_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _position_window(self) -> None:
        saved_x = self._saved_position.get("x")
        saved_y = self._saved_position.get("y")
        if isinstance(saved_x, int) and isinstance(saved_y, int):
            self.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{saved_x}+{saved_y}")
            return

        left, top, right, bottom = self._get_work_area()
        x = right - WINDOW_SIZE - EDGE_MARGIN
        y = bottom - WINDOW_SIZE - EDGE_MARGIN
        self.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{x}+{y}")

    def _get_work_area(self) -> tuple[int, int, int, int]:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 48
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        )
        return rect.left, rect.top, rect.right, rect.bottom

    def _on_drag_start(self, event: tk.Event) -> None:
        if self._is_locked:
            return
        self._drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self._is_locked or not self._drag_offset:
            return
        offset_x, offset_y = self._drag_offset
        x = event.x_root - offset_x
        y = event.y_root - offset_y
        self.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{x}+{y}")

    def _on_drag_end(self, _event: tk.Event) -> None:
        if not self._is_locked:
            self._save_settings()

    def _toggle_lock(self) -> None:
        self._is_locked = not self._is_locked
        self.lock_button.configure(text="Unlock" if self._is_locked else "Lock")
        self._save_settings()

    def _toggle_recording(self) -> None:
        if not self._engine:
            self.status_var.set("Loading Model...")
            return
        if not self._is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        self._is_recording = True
        self.status_var.set("Recording...")
        self.record_button.configure(text="Stop")

        self._stop_event = threading.Event()
        self._text_queue = queue.Queue()
        self._stream_thread = threading.Thread(
            target=self._stream_worker, daemon=True
        )
        self._stream_thread.start()
        self.after(50, self._poll_stream_queue)

    def _stop_recording(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self.status_var.set("Finalizing...")
        self.record_button.configure(state="disabled")

    def _stream_worker(self) -> None:
        if self._engine is None or self._stop_event is None:
            return

        def on_update(full_text: str) -> None:
            self._text_queue.put(("update", full_text))

        def on_final(text: str) -> None:
            self._text_queue.put(("final", text))

        def on_error(message: str) -> None:
            self._text_queue.put(("error", message))

        # The streaming loop runs in a background thread. UI updates are
        # marshaled onto the main thread via the queue and `after`.
        self._engine.stream_transcribe(
            self._stop_event, on_update, on_final, on_error
        )
        self._text_queue.put(("done", ""))

    def _poll_stream_queue(self) -> None:
        try:
            while True:
                kind, payload = self._text_queue.get_nowait()
                if kind == "update":
                    self._apply_stream_update(payload)
                elif kind == "final":
                    self._apply_final_text(payload)
                elif kind == "error":
                    self.status_var.set(payload)
                    self._finish_recording()
                    return
                elif kind == "done":
                    self._finish_recording()
                    return
        except queue.Empty:
            pass

        if self._is_recording:
            self.after(50, self._poll_stream_queue)

    def _finish_recording(self) -> None:
        self._is_recording = False
        self.status_var.set("Ready")
        self.record_button.configure(text="Record", state="normal")

    def _apply_stream_update(self, full_text: str) -> None:
        if not full_text:
            return

        common_length = self._common_prefix_length(
            self._displayed_text, full_text
        )
        if common_length < len(self._displayed_text):
            self.text_area.delete(f"1.0+{common_length}c", tk.END)

        delta = full_text[common_length:]
        if delta:
            self.text_area.insert(tk.END, delta)

        self._displayed_text = full_text

    def _apply_final_text(self, text: str) -> None:
        if not text:
            return
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, text)
        self._displayed_text = text

    def _common_prefix_length(self, a: str, b: str) -> int:
        limit = min(len(a), len(b))
        idx = 0
        while idx < limit and a[idx] == b[idx]:
            idx += 1
        return idx

    def _copy_text(self) -> None:
        text = self.text_area.get("1.0", tk.END).strip()
        if text:
            pyperclip.copy(text)
            self.status_var.set("Copied")
        else:
            self.status_var.set("Nothing to copy")

    def _clear_text(self) -> None:
        self.text_area.delete("1.0", tk.END)
        self._displayed_text = ""
        if self._engine:
            self._engine.reset()
        self.status_var.set("Ready")

    def _set_loading(self, is_loading: bool) -> None:
        if is_loading:
            self.record_button.configure(state="disabled")
            self.copy_button.configure(state="disabled")
            self.clear_button.configure(state="disabled")
            self.status_var.set("Loading Model...")
        else:
            self.record_button.configure(state="normal")
            self.copy_button.configure(state="normal")
            self.clear_button.configure(state="normal")
            self.status_var.set("Ready")

    def _load_engine_async(self) -> None:
        threading.Thread(target=self._load_engine, daemon=True).start()

    def _load_engine(self) -> None:
        try:
            engine = STTEngine()
            self.after(0, lambda: self._on_engine_loaded(engine))
        except Exception as exc:
            self.after(0, lambda: self._on_engine_error(str(exc)))

    def _on_engine_loaded(self, engine: STTEngine) -> None:
        self._engine = engine
        self._set_loading(False)

    def _on_engine_error(self, message: str) -> None:
        self.status_var.set(message)
        self.record_button.configure(state="disabled")

    def _start_hotkey_listener(self) -> None:
        def _listen() -> None:
            with pynput_keyboard.GlobalHotKeys(
                {"<ctrl>+<alt>+s": self._on_hotkey}
            ) as listener:
                self._hotkey_listener = listener
                listener.join()

        threading.Thread(target=_listen, daemon=True).start()

    def _on_hotkey(self) -> None:
        self.after(0, self._toggle_visibility)

    def _load_settings(self) -> dict:
        if not os.path.exists(CONFIG_PATH):
            return {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self) -> None:
        self.update_idletasks()
        data = {
            "position": {"x": int(self.winfo_x()), "y": int(self.winfo_y())},
            "locked": self._is_locked,
            "start_with_windows": bool(self.startup_var.get()),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError:
            pass

    def _toggle_visibility(self) -> None:
        if self._is_visible:
            self.withdraw()
            self._is_visible = False
        else:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self._is_visible = True

    def _get_startup_enabled(self) -> bool:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, STARTUP_NAME)
            return bool(value)
        except OSError:
            return False

    def _set_startup_enabled(self, enabled: bool) -> None:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    app_path = os.path.abspath(sys.argv[0])
                    value = f"\"{sys.executable}\" \"{app_path}\""
                    winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, value)
                else:
                    try:
                        winreg.DeleteValue(key, STARTUP_NAME)
                    except FileNotFoundError:
                        pass
        except OSError:
            pass

    def _on_startup_toggle(self) -> None:
        enabled = bool(self.startup_var.get())
        self._set_startup_enabled(enabled)
        self._save_settings()

    def _apply_startup_setting(self) -> None:
        if self._start_with_windows is None:
            return
        self.startup_var.set(bool(self._start_with_windows))
        self._set_startup_enabled(bool(self._start_with_windows))
        self._save_settings()

    def _close_app(self) -> None:
        self._save_settings()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.destroy()


def main() -> None:
    app = EasyTranscribeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
