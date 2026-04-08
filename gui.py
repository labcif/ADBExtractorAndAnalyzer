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
    full_device_dump
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
    btn.bind("<Enter>", lambda e: btn.config(bg=COLORS["highlight"]))
    btn.bind("<Leave>", lambda e: btn.config(bg=COLORS["button"]))


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

        apply_btn = tk.Button(header, text="Filter ▶", command=self.populate)
        _style_button(apply_btn)
        apply_btn.pack(side=tk.RIGHT, padx=2)

        self._filter_var = tk.StringVar()
        filter_entry = tk.Entry(header, textvariable=self._filter_var, width=16)
        _style_entry(filter_entry)
        filter_entry.pack(side=tk.RIGHT, padx=4)
        filter_entry.bind("<Return>", lambda e: self.populate())

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
        for widget in self._inner_frame.winfo_children():
            widget.destroy()
        self._vars.clear()

        filt = self._filter_var.get().strip().lower()
        items = self._fetch_items()
        if not items:
            self._count_label.config(text="0 items")
            return

        visible = [line for line in items if not filt or filt in line.lower()]
        self._count_label.config(text=f"{len(visible)} items")

        for item in visible:
            var = tk.IntVar()
            self._vars[item] = var

            cb = tk.Checkbutton(
                self._inner_frame,   # 👈 changed from self._canvas
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


class StatusBar(tk.Frame):
    """Bottom status bar with a text label and an indeterminate progress bar."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["accent"], height=28, **kwargs)
        self.pack_propagate(False)

        self._msg = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._msg,
                 bg=COLORS["accent"], fg=COLORS["text"],
                 font=FONTS["status"], anchor="w").pack(side=tk.LEFT, padx=10, fill=tk.Y)

        self._progress = ttk.Progressbar(self, mode="indeterminate", length=120)
        self._progress.pack(side=tk.RIGHT, padx=10, pady=4)

    def set(self, msg: str, busy: bool = False) -> None:
        self._msg.set(msg)
        if busy:
            self._progress.start(10)
        else:
            self._progress.stop()


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

        self._build_styles()
        self._build_ui()
        self._populate_all()

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

        # dump_btn = tk.Button(hdr, text="Full Dump", command=self._do_full_dump)
        # _style_button(dump_btn)
        # dump_btn.pack(side=tk.RIGHT, padx=4, pady=6)

        out_frame = tk.Frame(hdr, bg=COLORS["accent"])
        out_frame.pack(side=tk.RIGHT, padx=10)

        tk.Label(out_frame, text="Output:", bg=COLORS["accent"],
                fg=COLORS["text_dim"], font=FONTS["label"]).pack(side=tk.LEFT, padx=4)

        self._output_var = tk.StringVar(value=self._prefs["output_path"])
        out_entry = tk.Entry(out_frame, textvariable=self._output_var, width=36)
        _style_entry(out_entry)
        out_entry.pack(side=tk.LEFT, padx=4)

        btn = tk.Button(out_frame, text="Browse…", command=self._browse_output)
        _style_button(btn)
        btn.pack(side=tk.LEFT, padx=4)

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

    def _build_status(self) -> None:
        self._status = StatusBar(self)
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

    def _run_async(self, fn, *args) -> None:
        def wrapper():
            try:
                fn(*args)
            except Exception as e:
                log(f"Unhandled error in background task: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self._status.set("Ready", busy=False))

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
        self._status.set("Creating full device dump…", busy=True)

        def task():
            try:
                full_device_dump(self._output_var.get() or None)
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
