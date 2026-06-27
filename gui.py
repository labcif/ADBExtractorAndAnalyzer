"""
gui.py — ADB Extractor & Analyser 2.0
Theme constants, reusable UI components (ChecklistPanel, StatusBar),
and the main ADBExtractorApp window class.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk


from core import (
    DEFAULT_PREFS,
    extract_apk_files,
    extract_private_data,
    extract_public_data,
    list_apk_packages,
    list_private_packages,
    list_public_packages,
    load_prefs,
    log,
    run_aleapp,
    run_jadx,
    run_mobsf,
    save_prefs,
    full_device_dump,
    get_last_log_line,
    set_current_device,
    get_current_device,
    list_adb_devices,
)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

COLORS = {
    "bg":           "#1a1a2e",
    "panel":        "#16213e",
    "accent":       "#0f3460",
    "highlight":    "#e94560",
    "text":         "#eaeaea",
    "text_dim":     "#8892a4",
    "entry_bg":     "#0d1b2a",
    "button":       "#0f3460",
    "button_hover": "#e94560",
    "success":      "#4caf50",
    "warning":      "#ff9800",
}

FONTS = {
    "title":   ("Consolas", 20, "bold"),
    "section": ("Consolas", 13, "bold"),
    "label":   ("Consolas", 10),
    "button":  ("Consolas", 9, "bold"),
    "status":  ("Consolas", 9),
    "log":     ("Consolas", 8),
}


# ---------------------------------------------------------------------------
# Widget styling helpers
# ---------------------------------------------------------------------------

def _style_button(btn: tk.Button) -> None:
    btn.config(
        bg=COLORS["button"],
        fg=COLORS["text"],
        activebackground=COLORS["highlight"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        font=FONTS["button"],
        cursor="hand2",
        padx=8,
        pady=4,
    )
    def on_enter(e):
        if btn.cget("state") != tk.DISABLED:
            btn.config(bg=COLORS["highlight"])
    def on_leave(e):
        if btn.cget("state") != tk.DISABLED:
            btn.config(bg=COLORS["button"])
            
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)


def _set_button_state(btn: tk.Button, enabled: bool) -> None:
    if enabled:
        btn.config(state=tk.NORMAL, bg=COLORS["button"], fg=COLORS["text"])
    else:
        btn.config(state=tk.DISABLED, bg=COLORS["accent"], fg=COLORS["text_dim"])


def _style_entry(entry: tk.Entry) -> None:
    entry.config(
        bg=COLORS["entry_bg"],
        fg=COLORS["text"],
        insertbackground=COLORS["highlight"],
        relief=tk.FLAT,
        font=FONTS["label"],
        highlightthickness=1,
        highlightbackground=COLORS["accent"],
        highlightcolor=COLORS["highlight"],
    )


# ---------------------------------------------------------------------------
# Reusable components
# ---------------------------------------------------------------------------

class ChecklistPanel(tk.Frame):
    """
    Scrollable checklist panel with a filter bar and Select All toggle.
    Accepts a `fetch_items` callable that returns list[str] | None.
    For the APK panel, the callable must also update an external apk_dir_map;
    that is handled by the app class via _fetch_apks().
    """

    def __init__(self, parent, title: str, fetch_items, **kwargs):
        super().__init__(parent, bg=COLORS["panel"], **kwargs)
        self._fetch_items = fetch_items
        self._vars: dict[str, tk.IntVar] = {}
        self._build(title)


    def _build(self, title: str) -> None:
        # Header row
        header = tk.Frame(self, bg=COLORS["panel"])
        header.pack(fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(header, text=title, bg=COLORS["panel"],
                fg=COLORS["highlight"], font=FONTS["section"]).pack(side=tk.LEFT)

        self._toggle_btn = tk.Button(header, text="☑ All", command=self.toggle_all)
        _style_button(self._toggle_btn)
        self._toggle_btn.pack(side=tk.RIGHT, padx=2)

        self._apply_btn = tk.Button(header, text="Filter ▶", command=self.populate)
        _style_button(self._apply_btn)
        self._apply_btn.pack(side=tk.RIGHT, padx=2)

        self._filter_var = tk.StringVar()
        self._filter_entry = tk.Entry(header, textvariable=self._filter_var, width=16)
        _style_entry(self._filter_entry)
        self._filter_entry.pack(side=tk.RIGHT, padx=4)
        self._filter_entry.bind("<Return>", lambda e: self.populate())

        tk.Label(header, text="Filter:", bg=COLORS["panel"],
                fg=COLORS["text_dim"], font=FONTS["label"]).pack(side=tk.RIGHT)

        # Scrollable canvas
        canvas_frame = tk.Frame(self, bg=COLORS["panel"])
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Scrollbar
        self._scrollbar = tk.Scrollbar(
            canvas_frame,
            orient="vertical",
            bg=COLORS["accent"],
            troughcolor=COLORS["bg"]
        )
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Canvas
        self._canvas = tk.Canvas(
            canvas_frame,
            yscrollcommand=self._scrollbar.set,
            bg=COLORS["entry_bg"],
            highlightthickness=0
        )
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._scrollbar.config(command=self._canvas.yview)

        # Inner frame
        self._inner_frame = tk.Frame(
            self._canvas,
            bg=COLORS["entry_bg"],
            padx=4,
            pady=2
        )

        self._canvas_window = self._canvas.create_window(
            (0, 0),
            window=self._inner_frame,
            anchor="nw"
        )

        # Resize + scroll region
        self._inner_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )

        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._canvas_window, width=e.width)
        )

        # FIX: proper mousewheel handling
        canvas_frame.bind("<Enter>", lambda e: self._bind_mousewheel())
        canvas_frame.bind("<Leave>", lambda e: self._unbind_mousewheel())

        # Item count badge
        self._count_label = tk.Label(self, text="0 items",
                                    bg=COLORS["panel"],
                                    fg=COLORS["text_dim"],
                                    font=FONTS["status"])
        self._count_label.pack(pady=(0, 4))


    def _bind_mousewheel(self):
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)


    def _unbind_mousewheel(self):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")


    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:  # Linux scroll up
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:  # Linux scroll down
            self._canvas.yview_scroll(1, "units")
        elif event.delta:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


    def populate(self) -> None:
        # Clear existing widgets
        for widget in self._inner_frame.winfo_children():
            widget.destroy()
        self._vars.clear()

        # Show loading indicator
        loading_label = tk.Label(
            self._inner_frame,
            text="Loading packages from device...",
            bg=COLORS["entry_bg"],
            fg=COLORS["text_dim"],
            font=FONTS["label"]
        )
        loading_label.pack(pady=10, fill=tk.X)
        self._count_label.config(text="Loading...")

        # Run fetch in background
        def worker():
            try:
                items = self._fetch_items()
            except Exception as e:
                log(f"Error fetching items: {e}")
                items = None
            
            # Update UI on main thread
            self.after(0, lambda: self._on_fetch_complete(items, loading_label))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_complete(self, items: list[str] | None, loading_label: tk.Label) -> None:
        # Destroy the loading label if it exists
        if loading_label.winfo_exists():
            loading_label.destroy()

        if items is None:
            self._count_label.config(text="Error loading items")
            return

        filt = self._filter_var.get().strip().lower()
        visible = [line for line in items if not filt or filt in line.lower()]
        self._count_label.config(text=f"{len(visible)} items")

        for item in visible:
            var = tk.IntVar()
            self._vars[item] = var

            cb = tk.Checkbutton(
                self._inner_frame,
                text=item,
                variable=var,
                bg=COLORS["entry_bg"],
                fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["accent"],
                activeforeground=COLORS["highlight"],
                font=FONTS["label"],
                anchor="w",
            )
            cb.pack(fill=tk.X, anchor="w", padx=4, pady=1)

    def get_selected(self) -> list[str]:
        return [name for name, var in self._vars.items() if var.get() == 1]

    def toggle_all(self) -> None:
        all_on = all(v.get() == 1 for v in self._vars.values())
        value = 0 if all_on else 1
        for var in self._vars.values():
            var.set(value)

    def set_enabled(self, enabled: bool) -> None:
        _set_button_state(self._toggle_btn, enabled)
        _set_button_state(self._apply_btn, enabled)
        state = tk.NORMAL if enabled else tk.DISABLED
        self._filter_entry.config(state=state)


class StatusBar(tk.Frame):
    """Bottom status bar with a text label, cancel button, and progress bar."""

    def __init__(self, parent, cancel_cmd=None, **kwargs):
        super().__init__(parent, bg=COLORS["accent"], height=28, **kwargs)
        self.pack_propagate(False)

        self._msg = tk.StringVar(value="Ready")
        self._log_preview = tk.StringVar(value="")

        left = tk.Frame(self, bg=COLORS["accent"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 6))

        self._msg_label = tk.Label(
            left,
            textvariable=self._msg,
            bg=COLORS["accent"],
            fg=COLORS["text"],
            font=FONTS["status"],
            anchor="w"
        )
        self._msg_label.pack(side=tk.LEFT)

        self._sep_label = tk.Label(
            left,
            text="  |  ",
            bg=COLORS["accent"],
            fg=COLORS["text_dim"],
            font=FONTS["status"],
            anchor="w"
        )
        self._sep_label.pack(side=tk.LEFT)

        self._log_label = tk.Label(
            left,
            textvariable=self._log_preview,
            bg=COLORS["accent"],
            fg=COLORS["text_dim"],
            font=FONTS["status"],
            anchor="w",
            justify="left"
        )
        self._log_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        right = tk.Frame(self, bg=COLORS["accent"])
        right.pack(side=tk.RIGHT, padx=10)

        self._progress = ttk.Progressbar(right, mode="indeterminate", length=120)
        self._progress.pack(side=tk.RIGHT, pady=4)

        self._cancel_btn = tk.Button(right, text="✖ Cancel", command=cancel_cmd)
        _style_button(self._cancel_btn)
        self._cancel_btn.pack(side=tk.RIGHT, padx=(0, 10), pady=2)
        _set_button_state(self._cancel_btn, False)

    def set(self, msg: str, busy: bool = False) -> None:
        self._msg.set(msg)
        if busy:
            self._progress.start(10)
            _set_button_state(self._cancel_btn, True)
        else:
            self._progress.stop()
            _set_button_state(self._cancel_btn, False)
    
    def _truncate(self, text: str, limit: int = 80) -> str:
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[:limit - 3] + "..."   

    def set_log_preview(self, msg: str) -> None:
        self._log_preview.set(self._truncate(msg, 90))


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class ADBExtractorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ADB Extractor & Analyser 2.0")
        self.geometry("1380x860")
        self.minsize(1000, 700)
        self.configure(bg=COLORS["bg"])

        self._app_icon = tk.PhotoImage(file="assets/icon.png")
        self.iconphoto(True, self._app_icon)

        self._prefs = load_prefs()
        self._apk_dir_map: dict[str, str] = {}
        self._disableable_buttons: list[tk.Button] = []
        self._task_running = False

        self._build_styles()
        self._build_ui()
        
        # Prompt device selection at startup
        self._prompt_device_selection_startup()
        self._start_device_monitor()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # ttk style setup
    # ------------------------------------------------------------------

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TProgressbar",
            troughcolor=COLORS["bg"],
            bordercolor=COLORS["bg"],
            background=COLORS["highlight"],
            lightcolor=COLORS["highlight"],
            darkcolor=COLORS["highlight"],
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_header()
        self._build_columns()
        self._build_status()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=COLORS["accent"], height=52)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        img = Image.open("assets/icon.png")
        img = img.resize((24, 24))
        self._icon_img = ImageTk.PhotoImage(img)

        tk.Label(
            hdr,
            image=self._icon_img,
            bg=COLORS["accent"]
        ).pack(side=tk.LEFT, padx=(16, 8))

        tk.Label(
            hdr,
            text="ADB Extractor & Analyser 2.0",
            bg=COLORS["accent"], fg=COLORS["text"],
            font=FONTS["title"]
        ).pack(side=tk.LEFT)

        out_frame = tk.Frame(hdr, bg=COLORS["accent"])
        out_frame.pack(side=tk.RIGHT, padx=10)

        tk.Label(out_frame, text="Output:", bg=COLORS["accent"],
                fg=COLORS["text_dim"], font=FONTS["label"]).pack(side=tk.LEFT, padx=4)

        self._output_var = tk.StringVar(value=self._prefs["output_path"])
        out_entry = tk.Entry(out_frame, textvariable=self._output_var, width=36)
        _style_entry(out_entry)
        out_entry.pack(side=tk.LEFT, padx=4)

        self._browse_btn = tk.Button(out_frame, text="Browse…", command=self._browse_output)
        _style_button(self._browse_btn)
        self._browse_btn.pack(side=tk.LEFT, padx=4)
        self._disableable_buttons.append(self._browse_btn)

        # Device selection section in header
        dev_frame = tk.Frame(hdr, bg=COLORS["accent"])
        dev_frame.pack(side=tk.RIGHT, padx=(10, 20))

        tk.Label(dev_frame, text="Device:", bg=COLORS["accent"],
                 fg=COLORS["text_dim"], font=FONTS["label"]).pack(side=tk.LEFT, padx=4)

        self._device_label_var = tk.StringVar(value="None")
        self._device_label = tk.Label(dev_frame, textvariable=self._device_label_var, bg=COLORS["accent"],
                                     fg=COLORS["text_dim"], font=FONTS["section"])
        self._device_label.pack(side=tk.LEFT, padx=4)

        self._change_btn = tk.Button(dev_frame, text="Change…", command=self._change_device_runtime)
        _style_button(self._change_btn)
        self._change_btn.pack(side=tk.LEFT, padx=4)
        self._disableable_buttons.append(self._change_btn)

        self._dump_btn = tk.Button(dev_frame, text="Full Dump", command=self._do_full_dump)
        _style_button(self._dump_btn)
        self._dump_btn.pack(side=tk.LEFT, padx=(12, 4))
        self._disableable_buttons.append(self._dump_btn)

    def _build_columns(self) -> None:
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Column 1 — Private Data
        col1 = tk.Frame(body, bg=COLORS["panel"])
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        self._private_panel = ChecklistPanel(
            col1, "Private Data  /data/data/", self._fetch_private
        )
        self._private_panel.pack(fill=tk.BOTH, expand=True)

        self._build_tool_row(col1, "ALEAPP", "aleapp_path",
                             self._browse_aleapp, label_suffix="path:*")
        self._build_col_buttons(col1, [
            ("Extract",           self._do_extract_private),
            ("Extract & Analyse", self._do_extract_and_analyse),
        ])

        # Column 2 — APK Files
        col2 = tk.Frame(body, bg=COLORS["panel"])
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        self._apk_panel = ChecklistPanel(
            col2, "APK Files  /data/app/", self._fetch_apks
        )
        self._apk_panel.pack(fill=tk.BOTH, expand=True)

        self._build_tool_row(col2, "JADX", "jadx_path",
                             self._browse_jadx, label_suffix="path:*")
        self._build_mobsf_row(col2)
        self._build_col_buttons(col2, [
            ("Extract",                    self._do_extract_apk),
            ("Extract & Scan (MobSF)",     self._do_extract_and_mobsf),
            ("Extract & Decompile (JADX)", self._do_extract_and_jadx),
        ])

        # Column 3 — Public Data
        col3 = tk.Frame(body, bg=COLORS["panel"])
        col3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        self._public_panel = ChecklistPanel(
            col3, "Public Data  /sdcard/Android/data/", self._fetch_public
        )
        self._public_panel.pack(fill=tk.BOTH, expand=True)

        self._build_col_buttons(col3, [
            ("Extract", self._do_extract_public),
        ])

    def _build_tool_row(self, parent, label: str, pref_key: str,
                        browse_cmd, label_suffix: str = "path:") -> None:
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill=tk.X, padx=8, pady=2)

        tk.Label(row, text=f"{label} {label_suffix}",
                 bg=COLORS["panel"], fg=COLORS["text_dim"],
                 font=FONTS["label"]).pack(side=tk.LEFT)

        var = tk.StringVar(value=self._prefs.get(pref_key, ""))
        setattr(self, f"_{pref_key}_var", var)
        entry = tk.Entry(row, textvariable=var)
        _style_entry(entry)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        btn = tk.Button(row, text="Browse…", command=browse_cmd)
        _style_button(btn)
        btn.pack(side=tk.LEFT)
        self._disableable_buttons.append(btn)

    def _build_mobsf_row(self, parent) -> None:
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill=tk.X, padx=8, pady=2)

        tk.Label(row, text="MobSF (ip:port):",
                 bg=COLORS["panel"], fg=COLORS["text_dim"],
                 font=FONTS["label"]).pack(side=tk.LEFT)

        self._mobsf_var = tk.StringVar(
            value=self._prefs.get("mobsf_endpoint", DEFAULT_PREFS["mobsf_endpoint"])
        )
        entry = tk.Entry(row, textvariable=self._mobsf_var)
        _style_entry(entry)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

    def _build_col_buttons(self, parent,
                           buttons: list[tuple[str, callable]]) -> None:
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill=tk.X, padx=8, pady=(4, 8))
        for label, cmd in buttons:
            btn = tk.Button(row, text=label, command=cmd)
            _style_button(btn)
            btn.pack(side=tk.LEFT, padx=3, pady=2)
            self._disableable_buttons.append(btn)

    def _build_status(self) -> None:
        self._status = StatusBar(self, cancel_cmd=self._cancel_current_task)
        self._status.pack(fill=tk.X, side=tk.BOTTOM)

    # ------------------------------------------------------------------
    # Checklist data fetchers
    # ------------------------------------------------------------------

    def _fetch_private(self) -> list[str]:
        return list_private_packages()

    def _fetch_apks(self) -> list[str]:
        """Fetch APK list and refresh the internal apk_dir_map."""
        labels, apk_dir_map = list_apk_packages()
        self._apk_dir_map = apk_dir_map
        return labels

    def _fetch_public(self) -> list[str]:
        return list_public_packages()

    def _populate_all(self) -> None:
        self._private_panel.populate()
        self._apk_panel.populate()
        self._public_panel.populate()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._output_var.set(path)

    def _browse_aleapp(self) -> None:
        path = filedialog.askopenfilename()
        if path:
            self._aleapp_path_var.set(path)

    def _browse_jadx(self) -> None:
        path = filedialog.askopenfilename()
        if path:
            self._jadx_path_var.set(path)

    # ------------------------------------------------------------------
    # Background task runner — keeps UI responsive
    # ------------------------------------------------------------------
    
    def _start_log_monitor(self) -> None:
        self._monitor_logs = True
        self._poll_log_file()

    def _stop_log_monitor(self) -> None:
        self._monitor_logs = False
        self._status.set_log_preview("")

    def _poll_log_file(self) -> None:
        if not getattr(self, "_monitor_logs", False):
            return

        last = get_last_log_line()
        if last:
            self._status.set_log_preview(last)

        self.after(500, self._poll_log_file)

    def _start_device_monitor(self) -> None:
        self._check_device_connectivity()

    def _check_device_connectivity(self) -> None:
        device = get_current_device()
        if not device or device == "None":
            self._device_label_var.set("None")
            self._device_label.config(fg=COLORS["text_dim"])
            self.after(3000, self._check_device_connectivity)
            return

        def worker():
            try:
                devices = list_adb_devices()
                connected = (device in devices)
            except Exception:
                connected = False

            # Update UI on main thread
            self.after(0, lambda: self._update_device_status_ui(device, connected))

        threading.Thread(target=worker, daemon=True).start()

    def _update_device_status_ui(self, device: str, connected: bool) -> None:
        if connected:
            self._device_label_var.set(device)
            self._device_label.config(fg=COLORS["success"])
        else:
            self._device_label_var.set(f"{device} (Offline)")
            self._device_label.config(fg=COLORS["warning"])
        
        self.after(3000, self._check_device_connectivity)

    def _cancel_current_task(self) -> None:
        from core import cancel_active_tasks
        log("User requested cancellation of the running task.")
        cancel_active_tasks()
        self._status.set("Cancelling task…", busy=True)

    def _update_ui_state(self) -> None:
        enabled = not self._task_running
        for btn in self._disableable_buttons:
            _set_button_state(btn, enabled)
        
        self._private_panel.set_enabled(enabled)
        self._apk_panel.set_enabled(enabled)
        self._public_panel.set_enabled(enabled)

    def _on_task_finish(self) -> None:
        self._task_running = False
        self._update_ui_state()

    def _run_async(self, fn, *args) -> None:
        from core import set_cancelled
        set_cancelled(False)
        self._task_running = True
        self._update_ui_state()
        self._start_log_monitor()

        def wrapper():
            try:
                fn(*args)
            except Exception as e:
                from core import is_cancelled
                if not is_cancelled():
                    log(f"Unhandled error in background task: {e}")
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))
                else:
                    log(f"Background task exception suppressed due to cancellation: {e}")
            finally:
                self.after(0, lambda: self._status.set("Ready", busy=False))
                self.after(0, self._stop_log_monitor)
                self.after(0, self._on_task_finish)

        threading.Thread(target=wrapper, daemon=True).start()

    # ------------------------------------------------------------------
    # Action handlers — Private Data
    # ------------------------------------------------------------------

    def _do_extract_private(self) -> None:
        selected = self._private_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one package.")
            return
        self._status.set(f"Extracting {len(selected)} private package(s)…", busy=True)
        log(f"Extracting private data: {selected}")
        self._run_async(extract_private_data, selected,
                        self._output_var.get() or None)

    def _do_extract_and_analyse(self) -> None:
        aleapp = self._aleapp_path_var.get().strip()
        if not aleapp:
            messagebox.showerror("ALEAPP not set",
                                 "Please select the ALEAPP script path.")
            return
        selected = self._private_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one package.")
            return
        self._status.set("Extracting & running ALEAPP…", busy=True)

        def task():
            folder = extract_private_data(selected, self._output_var.get() or None)
            if folder:
                run_aleapp(aleapp, folder)

        self._run_async(task)

    # ------------------------------------------------------------------
    # Action handlers — APK Files
    # ------------------------------------------------------------------

    def _do_extract_apk(self) -> None:
        selected = self._apk_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one APK.")
            return
        self._status.set(f"Extracting {len(selected)} APK(s)…", busy=True)
        self._run_async(extract_apk_files, selected, self._apk_dir_map,
                        self._output_var.get() or None)

    def _do_extract_and_mobsf(self) -> None:
        selected = self._apk_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one APK.")
            return
        endpoint = self._mobsf_var.get().strip() or DEFAULT_PREFS["mobsf_endpoint"]
        self._status.set("Extracting & scanning with MobSF…", busy=True)

        def task():
            base, pkgs = extract_apk_files(selected, self._apk_dir_map,
                                           self._output_var.get() or None)
            run_mobsf(endpoint, base, pkgs)

        self._run_async(task)

    def _do_extract_and_jadx(self) -> None:
        jadx = self._jadx_path_var.get().strip()
        if not jadx:
            messagebox.showerror("JADX not set",
                                 "Please select the JADX executable path.")
            return
        selected = self._apk_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one APK.")
            return
        self._status.set("Extracting & decompiling with JADX…", busy=True)

        def task():
            base, pkgs = extract_apk_files(selected, self._apk_dir_map,
                                           self._output_var.get() or None)
            run_jadx(jadx, base, pkgs)

        self._run_async(task)

    # ------------------------------------------------------------------
    # Action handlers — Public Data
    # ------------------------------------------------------------------

    def _do_extract_public(self) -> None:
        selected = self._public_panel.get_selected()
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Please select at least one package.")
            return
        self._status.set(f"Extracting {len(selected)} public package(s)…", busy=True)
        log(f"Extracting public data: {selected}")
        self._run_async(extract_public_data, selected,
                        self._output_var.get() or None)

    # ------------------------------------------------------------------
    # Action handlers — Full Dump
    # ------------------------------------------------------------------

    def _do_full_dump(self) -> None:
        if not get_current_device():
            messagebox.showwarning("No Device", "Please select a device before performing a full dump.")
            return

        self._status.set("Creating full device dump…", busy=True)

        def task():
            try:
                res = full_device_dump(self._output_var.get() or None)
                if res:
                    self.after(0, lambda: messagebox.showinfo("Success", f"Full dump completed successfully!\nSaved to: {res}"))
                else:
                    self.after(0, lambda: messagebox.showerror("Error", "Full dump failed. Check logs.txt for details."))
            except Exception as e:
                log(f"Full dump failed: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        self._run_async(task)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        save_prefs({
            "aleapp_path":    self._aleapp_path_var.get(),
            "output_path":    self._output_var.get(),
            "jadx_path":      self._jadx_path_var.get(),
            "mobsf_endpoint": self._mobsf_var.get(),
        })
        self.destroy()

    def _prompt_device_selection_startup(self) -> None:
        devices = list_adb_devices()
        if len(devices) == 1:
            device = devices[0]
            set_current_device(device)
            self._device_label_var.set(device)
            self._device_label.config(fg=COLORS["success"])
            log(f"Auto-selected sole device at startup: {device}")
            self._populate_all()
        else:
            dialog = DeviceSelectorDialog(self, is_startup=True)
            self.wait_window(dialog)
            
            if dialog.selected_device:
                set_current_device(dialog.selected_device)
                self._device_label_var.set(dialog.selected_device)
                self._device_label.config(fg=COLORS["success"])
                log(f"Device selected at startup: {dialog.selected_device}")
            else:
                set_current_device(None)
                self._device_label_var.set("None")
                self._device_label.config(fg=COLORS["text_dim"])
                log("No device selected at startup.")
                
            self._populate_all()

    def _change_device_runtime(self) -> None:
        dialog = DeviceSelectorDialog(self, is_startup=False)
        self.wait_window(dialog)
        
        if dialog.selected_device:
            if dialog.selected_device == "None":
                set_current_device(None)
                self._device_label_var.set("None")
                self._device_label.config(fg=COLORS["text_dim"])
                log("Device cleared / disconnected at runtime.")
            else:
                set_current_device(dialog.selected_device)
                self._device_label_var.set(dialog.selected_device)
                self._device_label.config(fg=COLORS["success"])
                log(f"Device changed at runtime to: {dialog.selected_device}")
            self._populate_all()


# ---------------------------------------------------------------------------
# Device Selector Dialog
# ---------------------------------------------------------------------------

class DeviceSelectorDialog(tk.Toplevel):
    def __init__(self, parent, is_startup=False):
        super().__init__(parent, bg=COLORS["bg"])
        self.title("Select Android Device")
        self.geometry("450x260")
        self.resizable(False, False)
        
        # Center the window relative to the parent
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        
        if parent_w < 100 or parent_h < 100:
            parent_w = parent.winfo_screenwidth()
            parent_h = parent.winfo_screenheight()
            parent_x = 0
            parent_y = 0
            
        x = parent_x + (parent_w - 450) // 2
        y = parent_y + (parent_h - 260) // 2
        self.geometry(f"+{x}+{y}")
        
        self.transient(parent)
        self.grab_set()
        
        self.parent = parent
        self.is_startup = is_startup
        self.selected_device = None
        
        self._build_ui()
        self._refresh_devices()
        
    def _build_ui(self):
        hdr = tk.Frame(self, bg=COLORS["panel"], height=50)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        
        lbl = tk.Label(
            hdr,
            text="DEVICE SELECTOR",
            bg=COLORS["panel"],
            fg=COLORS["highlight"],
            font=FONTS["section"]
        )
        lbl.pack(pady=12)
        
        body = tk.Frame(self, bg=COLORS["bg"], padx=20, pady=15)
        body.pack(fill=tk.BOTH, expand=True)
        
        desc = tk.Label(
            body,
            text="Select an available Android device (physical/emulator):",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=FONTS["label"],
            anchor="w"
        )
        desc.pack(fill=tk.X, pady=(0, 10))
        
        drop_frame = tk.Frame(body, bg=COLORS["bg"])
        drop_frame.pack(fill=tk.X, pady=10)
        
        self._dev_var = tk.StringVar()
        self._dev_menu = ttk.Combobox(
            drop_frame,
            textvariable=self._dev_var,
            state="readonly",
            font=FONTS["label"],
            width=25
        )
        self._dev_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        refresh_btn = tk.Button(drop_frame, text="↻ Refresh", command=self._refresh_devices)
        _style_button(refresh_btn)
        refresh_btn.pack(side=tk.RIGHT)
        
        footer = tk.Frame(self, bg=COLORS["bg"], pady=15, padx=20)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        select_btn = tk.Button(footer, text="Select Device", command=self._on_select)
        _style_button(select_btn)
        select_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        if self.is_startup:
            cancel_btn = tk.Button(footer, text="Run Without Device", command=self.destroy)
            _style_button(cancel_btn)
            cancel_btn.pack(side=tk.RIGHT)
        else:
            disconnect_btn = tk.Button(footer, text="Disconnect", command=self._on_disconnect)
            _style_button(disconnect_btn)
            disconnect_btn.pack(side=tk.RIGHT, padx=(0, 10))
            
            cancel_btn = tk.Button(footer, text="Cancel", command=self.destroy)
            _style_button(cancel_btn)
            cancel_btn.pack(side=tk.RIGHT)
        
    def _refresh_devices(self):
        self._dev_menu.config(values=[])
        self._dev_var.set("Refreshing...")

        def worker():
            try:
                devices = list_adb_devices()
            except Exception:
                devices = []

            self.after(0, lambda: self._on_refresh_complete(devices))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refresh_complete(self, devices: list[str]):
        if devices:
            self._dev_menu.config(values=devices)
            current = get_current_device()
            if current in devices:
                self._dev_menu.set(current)
            else:
                self._dev_menu.set(devices[0])
        else:
            self._dev_menu.config(values=[])
            self._dev_var.set("No devices found")
            
    def _on_select(self):
        val = self._dev_var.get()
        if val and val != "No devices found":
            self.selected_device = val
            self.destroy()
        else:
            messagebox.showwarning(
                "No Device Selected",
                "Please connect a device and click Refresh, or run without a device.",
                parent=self
            )

    def _on_disconnect(self):
        self.selected_device = "None"
        self.destroy()
