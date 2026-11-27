"""
FingerprintBridge — AS608 / JM101B Desktop App
Single-file Tkinter GUI: enroll, continuous scan, delete, users, Supabase logging.
Build to .exe:  pyinstaller fingerprint_app.spec
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import sys
import queue
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
#  SOUND — bundled WAV files + SND_FILENAME | SND_ASYNC
#
#  Why WAV files instead of SND_ALIAS:
#    SND_ALIAS depends on the user's Windows sound scheme — if they have
#    "No Sounds" set, nothing plays. Bundled WAVs always play regardless.
#
#  Why SND_ASYNC instead of SND_NOWAIT:
#    SND_NOWAIT tells Windows "skip if the driver is busy" — that was the
#    root cause of inconsistent sounds when other audio was playing.
#    SND_ASYNC tells Windows "start playing and return immediately" —
#    Windows queues it properly through the audio mixer so it always plays.
#
#  The worker thread still exists so the scan loop never blocks waiting for
#  a previous sound to finish before the next one can be queued.
# ─────────────────────────────────────────────────────────────────────────────
import winsound as _winsound

def _sounds_dir() -> str:
    """
    When frozen (.exe): WAVs are extracted into _MEIPASS/sounds by PyInstaller.
    When running as .py: WAVs sit in sounds/ next to the script.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "sounds")   # inside the bundle
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

_SOUND_FILES = {
    "in":   "in.wav",
    "out":  "out.wav",
    "fail": "fail.wav",
}

_sound_q: queue.Queue = queue.Queue()

def _sound_worker():
    while True:
        event = _sound_q.get()
        if event is None:
            break
        fname = _SOUND_FILES.get(event)
        if not fname:
            continue
        path = os.path.join(_sounds_dir(), fname)
        try:
            if os.path.exists(path):
                # SND_FILENAME: play this exact file
                # SND_ASYNC: return immediately, let Windows mixer handle it
                # No SND_NOWAIT — that was dropping sounds when audio was busy
                _winsound.PlaySound(path,
                    _winsound.SND_FILENAME | _winsound.SND_ASYNC)
            else:
                # WAV missing — fall back to alias so something plays
                alias = {"in": "SystemAsterisk",
                         "out": "SystemExclamation",
                         "fail": "SystemHand"}.get(event)
                if alias:
                    _winsound.PlaySound(alias, _winsound.SND_ALIAS | _winsound.SND_ASYNC)
        except Exception:
            pass

_sound_thread = threading.Thread(target=_sound_worker,
                                  name="SoundWorker", daemon=False)
_sound_thread.start()

def play_sound(event: str) -> None:
    """Queue a sound. Returns instantly — never blocks the scan loop."""
    _sound_q.put(event)


# ─────────────────────────────────────────────────────────────────────────────
#  FIX 1 — capture real import errors so the GUI can show them
# ─────────────────────────────────────────────────────────────────────────────
_IMPORT_ERRORS: list[str] = []

try:
    from pyfingerprint.pyfingerprint import PyFingerprint
    SENSOR_AVAILABLE = True
except Exception as _e:
    SENSOR_AVAILABLE = False
    _IMPORT_ERRORS.append(f"pyfingerprint: {_e}")

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except Exception as _e:
    SUPABASE_AVAILABLE = False
    _IMPORT_ERRORS.append(f"supabase: {_e}")

# ─────────────────────────────────────────────────────────────────────────────
#  FIX 2 — correct config.json path for both .py and .exe
#
#  When PyInstaller bundles a one-file .exe:
#    sys.frozen = True
#    sys.executable = "C:\Users\you\FingerprintBridge.exe"   ← the real .exe
#    sys._MEIPASS   = "C:\Users\you\AppData\Local\Temp\_MEI…" ← read-only temp
#
#  config.json must live NEXT TO the .exe, not inside the temp folder.
#  Using sys.executable (not __file__, not sys._MEIPASS) is the correct fix.
# ─────────────────────────────────────────────────────────────────────────────
def _app_dir() -> str:
    if getattr(sys, "frozen", False):           # running as PyInstaller .exe
        return os.path.dirname(sys.executable)  # folder that contains .exe
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(_app_dir(), "config.json")

DEFAULT_CONFIG = {
    "port": "COM3",
    "baud": 57600,
    "supabase_url": "",
    "supabase_key": "",
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  THEMES  (dark + light)
# ─────────────────────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "BG":     "#0F1117",
        "BG2":    "#171B26",
        "BG3":    "#1E2435",
        "CARD":   "#1A1F2E",
        "BORDER": "#2A3050",
        "TEXT":   "#E8EAF0",
        "TEXT2":  "#8B91A8",
        "TEXT3":  "#4A5068",
    },
    "light": {
        "BG":     "#F0F2F7",
        "BG2":    "#E2E6EF",
        "BG3":    "#D4D9E6",
        "CARD":   "#FFFFFF",
        "BORDER": "#C5CBDB",
        "TEXT":   "#1A1F2E",
        "TEXT2":  "#4A5068",
        "TEXT3":  "#8B91A8",
    },
}

# Accent colours stay the same in both modes
GREEN  = "#1DB87A"
GREEND = "#0F6E56"
RED    = "#E24B4A"
BLUE   = "#378ADD"
AMBER  = "#EF9F27"
MONO   = "Consolas"
SANS   = "Segoe UI"

# Active theme variables — populated by _apply_theme()
BG = BG2 = BG3 = CARD = BORDER = TEXT = TEXT2 = TEXT3 = ""

def _apply_theme(name: str) -> None:
    """Write the chosen theme palette into the module-level colour globals."""
    global BG, BG2, BG3, CARD, BORDER, TEXT, TEXT2, TEXT3
    t = THEMES[name]
    BG     = t["BG"]
    BG2    = t["BG2"]
    BG3    = t["BG3"]
    CARD   = t["CARD"]
    BORDER = t["BORDER"]
    TEXT   = t["TEXT"]
    TEXT2  = t["TEXT2"]
    TEXT3  = t["TEXT3"]

_apply_theme("dark")   # default


# ─────────────────────────────────────────────────────────────────────────────
#  SENSOR CONTROLLER
# ─────────────────────────────────────────────────────────────────────────────
class SensorController:
    def __init__(self):
        self.sensor = None
        self.sb     = None
        self.connected = False
        self.cfg    = load_config()

    def connect(self):
        if not SENSOR_AVAILABLE:
            err = "\n".join(_IMPORT_ERRORS) or "pyfingerprint not available"
            raise RuntimeError(f"Library error:\n{err}\n\nRun: pip install pyfingerprint pyserial")

        port = self.cfg["port"]
        baud = int(self.cfg["baud"])

        self.sensor = PyFingerprint(port, baud, 0xFFFFFFFF, 0x00000000)
        if not self.sensor.verifyPassword():
            self.sensor = None
            raise RuntimeError(
                "Sensor password mismatch.\n\n"
                "Check TX↔RX wiring (must be CROSSED).\n"
                f"Port used: {port}  Baud: {baud}"
            )

        url = self.cfg.get("supabase_url", "").strip()
        key = self.cfg.get("supabase_key", "").strip()
        if url and key:
            if not SUPABASE_AVAILABLE:
                raise RuntimeError("supabase-py not installed.\nRun: pip install supabase")
            self.sb = create_client(url, key)
        else:
            self.sb = None

        self.connected = True

    def disconnect(self):
        self.sensor    = None
        self.sb        = None
        self.connected = False

    # ── sensor helpers ──────────────────────────────────────────────────────
    def template_count(self) -> int:
        return self.sensor.getTemplateCount() if self.sensor else 0

    def capacity(self) -> int:
        return self.sensor.getStorageCapacity() if self.sensor else 127

    def wait_for_finger(self):
        while not self.sensor.readImage():
            time.sleep(0.05)

    def wait_for_lift(self):
        while self.sensor.readImage():
            time.sleep(0.1)

    def scan_once(self) -> tuple[int, int]:
        self.wait_for_finger()
        self.sensor.convertImage(0x01)
        pos, acc = self.sensor.searchTemplate()
        return int(pos), int(acc)

    def enroll_step1(self):
        self.wait_for_finger()
        self.sensor.convertImage(0x01)

    def enroll_step2(self):
        self.wait_for_finger()
        self.sensor.convertImage(0x02)

    def enroll_finish(self) -> int:
        if self.sensor.compareCharacteristics() == 0:
            raise RuntimeError("Fingerprints did not match — try again.")
        self.sensor.createTemplate()
        return int(self.sensor.storeTemplate())

    def delete_template(self, slot: int):
        if self.sensor:
            self.sensor.deleteTemplate(slot)

    def list_templates(self) -> list[int]:
        if not self.sensor:
            return []
        occupied = []
        for i in range(self.capacity()):
            try:
                if self.sensor.loadTemplate(i, 0x01):
                    occupied.append(i)
            except Exception:
                pass
        return occupied

    # ── Supabase helpers ────────────────────────────────────────────────────
    # PostgREST rule for mixed-case columns created with double-quotes:
    #   - In .eq(), .update(), .order() → pass the plain name, supabase-py quotes it
    #   - In .select() → must wrap each column in double-quotes inside the string
    #     e.g. '"EmployeeId","FirstName"' so PostgREST receives "EmployeeId","FirstName"
    # Swallowed exceptions were hiding insert failures — all helpers now raise so
    # the scan loop can surface them in the Log tab.

    def get_employee_by_slot(self, slot: int) -> dict | None:
        """Look up a user row by FingerprintSlot. Raises on error, returns None if not found."""
        if not self.sb:
            return None
        res = (self.sb.table("user")
               .select('"EmployeeId","FirstName","LastName","Role","FingerprintSlot"')
               .eq("FingerprintSlot", slot)
               .limit(1)
               .execute())
        return res.data[0] if res.data else None

    def get_latest_status(self, employee_id: int) -> str | None:
        """Return most recent status ('IN'/'OUT') for this employee, or None. Raises on error."""
        if not self.sb:
            return None
        res = (self.sb.table("personnel_entry_logs")
               .select("status")
               .eq("employee_id", employee_id)
               .order("id", desc=True)
               .limit(1)
               .execute())
        return res.data[0]["status"] if res.data else None

    def log_entry(self, employee: dict, status: str) -> None:
        """Insert one row into personnel_entry_logs. Raises on error."""
        if not self.sb:
            raise RuntimeError("Supabase client not initialised — check URL and key in Settings.")
        now = datetime.now()
        full_name = f"{employee['FirstName']} {employee['LastName']}"
        row = {
            "employee_id": employee["EmployeeId"],
            "name":        full_name,
            "role":        employee.get("Role", ""),
            "date":        now.strftime("%Y-%m-%d"),
            "time":        now.strftime("%H:%M:%S"),
            "status":      status,
            "created_at":  now.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at":  now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.sb.table("personnel_entry_logs").insert(row).execute()

    def get_users(self) -> list[dict]:
        """Return all users that have a FingerprintSlot assigned."""
        if not self.sb:
            return []
        res = (self.sb.table("user")
               .select('"EmployeeId","FirstName","LastName","Role","FingerprintSlot"')
               .not_.is_("FingerprintSlot", "null")
               .order("FingerprintSlot")
               .execute())
        return res.data or []

    def search_employees(self, first_name: str) -> list[dict]:
        """Search user table by FirstName (case-insensitive). Raises on error."""
        if not self.sb:
            return []
        res = (self.sb.table("user")
               .select('"EmployeeId","FirstName","LastName","Role","FingerprintSlot"')
               .ilike("FirstName", f"%{first_name}%")
               .execute())
        return res.data or []

    def assign_slot(self, employee_id: int, slot: int) -> None:
        """Save the fingerprint slot number onto the user row. Raises on error."""
        if self.sb:
            (self.sb.table("user")
             .update({"FingerprintSlot": slot})
             .eq("EmployeeId", employee_id)
             .execute())

    def clear_slot(self, slot: int) -> None:
        """Remove fingerprint slot assignment from whoever had this slot. Raises on error."""
        if self.sb:
            (self.sb.table("user")
             .update({"FingerprintSlot": None})
             .eq("FingerprintSlot", slot)
             .execute())


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.ctrl        = SensorController()
        self.scan_active = False
        self._q          = queue.Queue()
        self._anim_step  = 0
        self._match_count = 0
        self._fail_count  = 0
        self._theme_name  = "dark"
        self._colour_registry: list[tuple] = []   # filled by _reg() during _build()

        self.title("FingerprintBridge")
        self.geometry("900x640")
        self.minsize(820, 580)
        self.configure(bg=BG)

        # Launch fullscreen
        self.after(0, lambda: self.state("zoomed"))

        self._styles()
        self._build()
        self._poll()

        # Show import errors immediately if any
        if _IMPORT_ERRORS:
            self.after(400, self._show_import_warning)

    # ── ttk styles ──────────────────────────────────────────────────────────
    def _styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=(SANS, 10))
        s.configure("TFrame", background=BG)
        s.configure("TNotebook", background=BG2, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG3, foreground=TEXT2,
                    font=(SANS, 10), padding=(14, 6))
        s.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", TEXT)])
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Card.TLabel",  background=CARD, foreground=TEXT)
        s.configure("Muted.TLabel", background=CARD, foreground=TEXT2, font=(SANS, 9))
        s.configure("Big.TLabel",   background=CARD, foreground=TEXT,  font=(SANS, 22, "bold"))
        s.configure("BigG.TLabel",  background=CARD, foreground=GREEN, font=(SANS, 22, "bold"))
        s.configure("BigR.TLabel",  background=CARD, foreground=RED,   font=(SANS, 22, "bold"))
        s.configure("Green.TButton", background=GREEN, foreground="#000",
                    font=(SANS, 10, "bold"), borderwidth=0, focusthickness=0)
        s.map("Green.TButton", background=[("active", GREEND), ("disabled", BG3)],
              foreground=[("disabled", TEXT3)])
        s.configure("Gray.TButton", background=BG3, foreground=TEXT,
                    font=(SANS, 10), borderwidth=0, focusthickness=0)
        s.map("Gray.TButton", background=[("active", BORDER)])
        s.configure("Red.TButton", background="#2A1515" if self._theme_name=="dark" else "#FDEAEA",
                    foreground=RED, font=(SANS, 10), borderwidth=0, focusthickness=0)
        s.map("Red.TButton", background=[("active", "#3A1515" if self._theme_name=="dark" else "#FBDADA")])
        s.configure("Treeview", background=BG2, foreground=TEXT,
                    fieldbackground=BG2, borderwidth=0, font=(SANS, 10), rowheight=24)
        s.configure("Treeview.Heading", background=BG3, foreground=TEXT2,
                    font=(SANS, 9), borderwidth=0)
        s.map("Treeview", background=[("selected", BG3)], foreground=[("selected", GREEN)])
        s.configure("TEntry", fieldbackground=BG3, foreground=TEXT,
                    insertcolor=TEXT, borderwidth=1, relief="flat", font=(SANS, 10))
        s.configure("Horizontal.TProgressbar",
                    troughcolor=BG3, background=GREEN, thickness=4, borderwidth=0)
        s.configure("TCombobox", fieldbackground=BG3, foreground=TEXT,
                    selectbackground=BG3, selectforeground=TEXT)
        s.map("TCombobox", fieldbackground=[("readonly", BG3)])
        s.configure("TScrollbar", background=BG3, troughcolor=BG2,
                    borderwidth=0, arrowcolor=TEXT3)

    def _toggle_theme(self):
        """Switch between dark and light mode — only updates colours, never touches layout."""
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        _apply_theme(self._theme_name)
        self._styles()
        self._apply_colours()
        icon = "☀" if self._theme_name == "light" else "🌙"
        self._theme_btn.configure(
            text=f"{icon} {'Light' if self._theme_name=='light' else 'Dark'}")

    def _reg(self, widget, role: str):
        """Register a widget so _apply_colours() can repaint it. Call once at build time.
        role is one of: bg bg2 bg3 card border text text2 text3
        Special compound roles: card+text  card+text2  card+text3
        bg2+text  bg2+text2  bg2+text3  bg3+text  canvas  logtext  listbox
        """
        self._colour_registry.append((widget, role))
        return widget   # returns widget so it can be used inline

    def _apply_colours(self):
        """Repaint every registered widget. Never touches layout or geometry."""
        role_map = {
            "bg":          lambda w: w.configure(bg=BG),
            "bg2":         lambda w: w.configure(bg=BG2),
            "bg3":         lambda w: w.configure(bg=BG3),
            "card":        lambda w: w.configure(bg=CARD),
            "card+text":   lambda w: w.configure(bg=CARD, fg=TEXT),
            "card+text2":  lambda w: w.configure(bg=CARD, fg=TEXT2),
            "card+text3":  lambda w: w.configure(bg=CARD, fg=TEXT3),
            "bg+text":     lambda w: w.configure(bg=BG,   fg=TEXT),
            "bg+text2":    lambda w: w.configure(bg=BG,   fg=TEXT2),
            "bg+text3":    lambda w: w.configure(bg=BG,   fg=TEXT3),
            "bg2+text":    lambda w: w.configure(bg=BG2,  fg=TEXT),
            "bg2+text2":   lambda w: w.configure(bg=BG2,  fg=TEXT2),
            "bg2+text3":   lambda w: w.configure(bg=BG2,  fg=TEXT3),
            "bg3+text":    lambda w: w.configure(bg=BG3,  fg=TEXT),
            # canvas: only bg colour — never triggers a redraw or pack recalc
            "canvas":      lambda w: w.configure(bg=CARD),
            "logtext":     lambda w: w.configure(bg=BG2, fg=TEXT2,
                                                 insertbackground=TEXT),
            "listbox":     lambda w: w.configure(bg=BG2, fg=TEXT,
                                                 selectbackground=BG3,
                                                 selectforeground=GREEN),
            "topbtn":      lambda w: w.configure(bg=BG2, fg=TEXT2,
                                                 activebackground=BG2,
                                                 activeforeground=TEXT),
            "topbtn+green":lambda w: w.configure(bg=BG2, fg=GREEN,
                                                 activebackground=BG2,
                                                 activeforeground=GREEND),
        }
        for widget, role in self._colour_registry:
            try:
                role_map[role](widget)
            except Exception:
                pass
        # Canvas bg only — redraw content separately after colours settle
        try:
            self._fp_cv.configure(bg=CARD)
        except Exception:
            pass
        # Schedule the canvas content redraw after Tk finishes geometry pass
        self.after(10, self._redraw_fp)

    def _redraw_fp(self):
        """Redraw fingerprint canvas content after colours have settled."""
        try:
            if self.scan_active:
                self._fp_scanning()
            else:
                self._fp_idle()
        except Exception:
            pass

    # ── layout ──────────────────────────────────────────────────────────────
    def _build(self):
        # top bar
        bar = tk.Frame(self, bg=BG2, height=50)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._reg(bar, "bg2")
        self._reg(tk.Label(bar, text="●", fg=GREEN, bg=BG2,
                           font=(MONO, 13)), "bg2").pack(side="left", padx=(14,5))
        self._reg(tk.Label(bar, text="FingerprintBridge", fg=TEXT, bg=BG2,
                           font=(SANS, 12, "bold")), "bg2+text").pack(side="left")
        self._reg(tk.Label(bar, text="AS608 · Supabase", fg=TEXT3, bg=BG2,
                           font=(MONO, 8)), "bg2+text3").pack(side="left", padx=(8,0), pady=(3,0))

        self._conn_btn = tk.Button(bar, text="Connect", fg=GREEN, bg=BG2,
                                   activebackground=BG2, activeforeground=GREEND,
                                   relief="flat", font=(SANS, 10, "bold"),
                                   cursor="hand2", command=self._toggle_connect,
                                   bd=0, padx=14)
        self._conn_btn.pack(side="right", pady=8, padx=6)

        tk.Button(bar, text="⚙ Settings", fg=TEXT2, bg=BG2,
                  activebackground=BG2, activeforeground=TEXT,
                  relief="flat", font=(SANS, 10), cursor="hand2",
                  command=self._settings, bd=0, padx=10).pack(side="right", pady=8)

        self._theme_btn = tk.Button(bar, text="☀ Light", fg=TEXT2, bg=BG2,
                                    activebackground=BG2, activeforeground=TEXT,
                                    relief="flat", font=(SANS, 10), cursor="hand2",
                                    command=self._toggle_theme, bd=0, padx=10)
        self._theme_btn.pack(side="right", pady=8)

        self._dot = tk.Label(bar, text="○", fg=RED, bg=BG2, font=(MONO, 11))
        self._dot.pack(side="right", pady=8)

        # notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self._t_scan   = ttk.Frame(nb)
        self._t_enroll = ttk.Frame(nb)
        self._t_users  = ttk.Frame(nb)
        self._t_log    = ttk.Frame(nb)
        self._t_diag   = ttk.Frame(nb)   # FIX 3 — diagnostics tab

        nb.add(self._t_scan,   text="  Scan  ")
        nb.add(self._t_enroll, text="  Enroll  ")
        nb.add(self._t_users,  text="  Users  ")
        nb.add(self._t_log,    text="  Log  ")
        nb.add(self._t_diag,   text="  Diagnostics  ")

        self._build_scan()
        self._build_enroll()
        self._build_users()
        self._build_log()
        self._build_diag()

        # status bar
        bot = tk.Frame(self, bg=BG2, height=24)
        bot.pack(fill="x")
        bot.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready  ·  Not connected")
        tk.Label(bot, textvariable=self._status_var, fg=TEXT3, bg=BG2,
                 font=(MONO, 8)).pack(side="left", padx=12)
        self._sb_lbl = tk.Label(bot, text="Supabase: off", fg=TEXT3, bg=BG2, font=(MONO, 8))
        self._sb_lbl.pack(side="right", padx=12)

    # ────────────────────────────── SCAN TAB ────────────────────────────────
    def _build_scan(self):
        f = self._t_scan
        f.columnconfigure((0,1), weight=1)
        f.rowconfigure(1, weight=1)
        self._reg(f, "bg")

        # metric row
        mrow = tk.Frame(f, bg=BG)
        mrow.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14,8))
        for i in range(4):
            mrow.columnconfigure(i, weight=1)
        self._reg(mrow, "bg")

        self._m_enrolled = tk.StringVar(value="0")
        self._m_matches  = tk.StringVar(value="0")
        self._m_fails    = tk.StringVar(value="0")
        self._m_conf     = tk.StringVar(value="—")

        for i, (lbl, var, sty) in enumerate([
            ("ENROLLED",      self._m_enrolled, "Big.TLabel"),
            ("MATCHES TODAY", self._m_matches,  "BigG.TLabel"),
            ("REJECTIONS",    self._m_fails,    "BigR.TLabel"),
            ("CONFIDENCE",    self._m_conf,     "Big.TLabel"),
        ]):
            c = self._card(mrow)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i==0 else 6, 0))
            self._reg(c, "card")
            self._reg(tk.Label(c, text=lbl, fg=TEXT3, bg=CARD,
                               font=(MONO,8)), "card+text3").pack(pady=(10,2))
            ttk.Label(c, textvariable=var, style=sty).pack(pady=(0,10))

        # left scanner panel
        left = self._card(f)
        left.grid(row=1, column=0, sticky="nsew", padx=(14,6), pady=(0,14))
        left.columnconfigure(0, weight=1)
        self._reg(left, "card")

        self._reg(tk.Label(left, text="SCANNER", fg=TEXT3, bg=CARD,
                           font=(MONO,8)), "card+text3").pack(pady=(14,0))

        # Canvas: wrapped in a fixed-size frame that pack_propagate=False locks
        # Using grid inside left panel so the canvas row has a fixed minsize
        left.rowconfigure(1, minsize=148)   # row 1 = canvas row, never shrinks

        cv_wrap = tk.Frame(left, bg=CARD, width=124, height=124)
        cv_wrap.pack(pady=14)
        cv_wrap.pack_propagate(False)   # ignore children's size requests
        self._reg(cv_wrap, "card")

        self._fp_cv = tk.Canvas(cv_wrap, width=120, height=120,
                                bg=CARD, highlightthickness=0)
        self._fp_cv.pack(expand=True)
        # Explicitly set canvas size attributes — these survive delete("all")
        self._fp_cv.configure(width=120, height=120)
        self._fp_idle()

        self._scan_lbl = tk.Label(left, text="Place finger on sensor",
                                  fg=TEXT, bg=CARD, font=(SANS,11,"bold"))
        self._scan_lbl.pack()
        self._reg(self._scan_lbl, "card+text")

        self._scan_sub = tk.Label(left, text="Not connected",
                                  fg=TEXT2, bg=CARD, font=(MONO,9))
        self._scan_sub.pack(pady=(3,14))
        self._reg(self._scan_sub, "card+text2")

        self._pbar = ttk.Progressbar(left, mode="indeterminate", length=150,
                                     style="Horizontal.TProgressbar")
        self._pbar.pack(pady=(0,12))

        btnf = tk.Frame(left, bg=CARD)
        btnf.pack(fill="x", padx=18, pady=(0,16))
        btnf.columnconfigure((0,1), weight=1)
        self._reg(btnf, "card")

        self._btn_scan = ttk.Button(btnf, text="▶  Start Scan",
                                    style="Green.TButton", command=self._start_scan)
        self._btn_scan.grid(row=0, column=0, sticky="ew", padx=(0,5), ipady=6)
        self._btn_stop = ttk.Button(btnf, text="■  Stop",
                                    style="Gray.TButton", command=self._stop_scan,
                                    state="disabled")
        self._btn_stop.grid(row=0, column=1, sticky="ew", ipady=6)

        # right recent scans
        right = self._card(f)
        right.grid(row=1, column=1, sticky="nsew", padx=(0,14), pady=(0,14))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self._reg(right, "card")

        self._reg(tk.Label(right, text="RECENT SCANS", fg=TEXT3, bg=CARD,
                           font=(MONO,8)), "card+text3").pack(pady=(14,6))

        cols = ("time","user","slot","conf","result")
        self._scan_tv = ttk.Treeview(right, columns=cols, show="headings",
                                     height=14, selectmode="browse")
        for c,t,w in [("time","Time",65),("user","User",110),
                      ("slot","Slot",55),("conf","Confidence",90),("result","Result",75)]:
            self._scan_tv.heading(c, text=t)
            self._scan_tv.column(c, width=w, anchor="center")
        sb = ttk.Scrollbar(right, orient="vertical", command=self._scan_tv.yview)
        self._scan_tv.configure(yscrollcommand=sb.set)
        self._scan_tv.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,12))
        sb.pack(side="right", fill="y", pady=(0,12), padx=(0,6))
        self._scan_tv.tag_configure("match", foreground=GREEN)
        self._scan_tv.tag_configure("fail",  foreground=RED)
        self._scan_tv.tag_configure("out",   foreground=AMBER)

    # ─────────────────────────── ENROLL TAB ─────────────────────────────────
    def _build_enroll(self):
        f = self._t_enroll
        f.columnconfigure(0, weight=1)

        wrap = tk.Frame(f, bg=BG)
        wrap.pack(expand=True, fill="both", padx=70, pady=28)
        wrap.columnconfigure(0, weight=1)

        tk.Label(wrap, text="Enroll New Fingerprint", fg=TEXT, bg=BG,
                 font=(SANS,15,"bold")).pack(pady=(0,4))
        tk.Label(wrap, text="Search for an employee by first name, then scan their finger.",
                 fg=TEXT2, bg=BG, font=(SANS,10)).pack(pady=(0,18))

        card = self._card(wrap)
        card.pack(fill="x", pady=(0,14))

        # ── Search row ──
        search_row = tk.Frame(card, bg=CARD)
        search_row.pack(fill="x", padx=22, pady=(18,8))
        search_row.columnconfigure(1, weight=1)

        tk.Label(search_row, text="Search by First Name", fg=TEXT2, bg=CARD,
                 font=(SANS,10)).grid(row=0, column=0, sticky="w", padx=(0,12))
        self._search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self._search_var,
                  width=28).grid(row=0, column=1, sticky="ew")
        ttk.Button(search_row, text="Search", style="Gray.TButton",
                   command=self._search_employee).grid(row=0, column=2, padx=(8,0), ipady=4, ipadx=8)

        # ── Search results listbox ──
        res_frame = tk.Frame(card, bg=CARD)
        res_frame.pack(fill="x", padx=22, pady=(0,10))
        res_frame.columnconfigure(0, weight=1)

        tk.Label(res_frame, text="Select employee:", fg=TEXT3, bg=CARD,
                 font=(MONO,8)).pack(anchor="w", pady=(0,4))

        lb_wrap = tk.Frame(res_frame, bg=CARD)
        lb_wrap.pack(fill="x")
        lb_wrap.columnconfigure(0, weight=1)

        self._employee_lb = tk.Listbox(lb_wrap, bg=BG2, fg=TEXT, font=(SANS,10),
                                        selectbackground=BG3, selectforeground=GREEN,
                                        relief="flat", bd=0, height=4,
                                        activestyle="none")
        lb_sb = ttk.Scrollbar(lb_wrap, orient="vertical", command=self._employee_lb.yview)
        self._employee_lb.configure(yscrollcommand=lb_sb.set)
        self._employee_lb.grid(row=0, column=0, sticky="ew")
        lb_sb.grid(row=0, column=1, sticky="ns")
        self._employee_lb.bind("<<ListboxSelect>>", self._on_employee_select)

        # selected employee display
        self._selected_emp_var = tk.StringVar(value="No employee selected")
        tk.Label(card, textvariable=self._selected_emp_var, fg=TEXT2, bg=CARD,
                 font=(MONO,9)).pack(padx=22, pady=(0,8), anchor="w")

        # ── Enrollment steps ──
        self._estep_lbls = []
        steps_frame = tk.Frame(card, bg=CARD)
        steps_frame.pack(fill="x", padx=22, pady=(0,6))
        for txt in ["1  Place finger on sensor (scan 1)",
                    "2  Remove finger",
                    "3  Place same finger (scan 2)",
                    "4  Save template & update Supabase"]:
            lbl = tk.Label(steps_frame, text=f"○  {txt}", fg=TEXT3, bg=CARD,
                           font=(MONO,9), anchor="w")
            lbl.pack(fill="x", pady=2)
            self._estep_lbls.append(lbl)

        self._estatus = tk.Label(card, text="", fg=GREEN, bg=CARD, font=(SANS,11,"bold"))
        self._estatus.pack(pady=(4,14))

        btnf = tk.Frame(card, bg=CARD)
        btnf.pack(padx=22, pady=(0,18))
        self._enroll_btn = ttk.Button(btnf, text="▶  Start Enrollment",
                                      style="Green.TButton", command=self._start_enroll)
        self._enroll_btn.pack(ipady=8, ipadx=20)

        # internal: holds the selected employee dict
        self._selected_employee: dict | None = None
        self._search_results: list[dict] = []

    # ─────────────────────────── USERS TAB ──────────────────────────────────
    def _build_users(self):
        f = self._t_users
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        top = tk.Frame(f, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14,8))
        tk.Label(top, text="Enrolled Users", fg=TEXT, bg=BG,
                 font=(SANS,13,"bold")).pack(side="left")
        ttk.Button(top, text="↻ Refresh", style="Gray.TButton",
                   command=self._refresh_users).pack(side="right", ipady=4)
        ttk.Button(top, text="✕ Delete Selected", style="Red.TButton",
                   command=self._delete_user).pack(side="right", padx=(0,8), ipady=4)

        card = self._card(f)
        card.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0,14))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        cols = ("slot","emp_id","name","role")
        self._users_tv = ttk.Treeview(card, columns=cols, show="headings", selectmode="browse")
        for c,t,w in [("slot","Slot #",70),("emp_id","Emp ID",70),
                      ("name","Name",200),("role","Role",120)]:
            self._users_tv.heading(c, text=t)
            self._users_tv.column(c, width=w)
        sb2 = ttk.Scrollbar(card, orient="vertical", command=self._users_tv.yview)
        self._users_tv.configure(yscrollcommand=sb2.set)
        self._users_tv.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        sb2.grid(row=0, column=1, sticky="ns", pady=8, padx=(0,6))
        tk.Label(card, text="If no Supabase keys are set, lists on-chip templates only.",
                 fg=TEXT3, bg=CARD, font=(MONO,8)).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0,8))

    # ────────────────────────────── LOG TAB ─────────────────────────────────
    def _build_log(self):
        f = self._t_log
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        top = tk.Frame(f, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14,8))
        tk.Label(top, text="Activity Log", fg=TEXT, bg=BG,
                 font=(SANS,13,"bold")).pack(side="left")
        ttk.Button(top, text="Clear", style="Gray.TButton",
                   command=self._clear_log).pack(side="right", ipady=4)

        card = self._card(f)
        card.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0,14))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        self._log_txt = tk.Text(card, bg=BG2, fg=TEXT2, font=(MONO,9),
                                relief="flat", bd=0, state="disabled", wrap="word")
        sb3 = ttk.Scrollbar(card, orient="vertical", command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=sb3.set)
        self._log_txt.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        sb3.grid(row=0, column=1, sticky="ns", pady=8, padx=(0,6))
        self._log_txt.tag_configure("g", foreground=GREEN)
        self._log_txt.tag_configure("r", foreground=RED)
        self._log_txt.tag_configure("b", foreground=BLUE)
        self._log_txt.tag_configure("a", foreground=AMBER)
        self._log_txt.tag_configure("d", foreground=TEXT3)

        self._log("FingerprintBridge started", "b")
        if _IMPORT_ERRORS:
            for e in _IMPORT_ERRORS:
                self._log(f"Import error: {e}", "r")
        self._log("Configure port in Settings then click Connect.", "d")

    # ─────────────────────── DIAGNOSTICS TAB  (FIX 3) ───────────────────────
    def _build_diag(self):
        f = self._t_diag
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        tk.Label(f, text="Diagnostics", fg=TEXT, bg=BG,
                 font=(SANS,13,"bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(14,8))

        card = self._card(f)
        card.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0,14))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        self._diag_txt = tk.Text(card, bg=BG2, fg=TEXT2, font=(MONO,9),
                                 relief="flat", bd=0, state="disabled", wrap="word")
        sb4 = ttk.Scrollbar(card, orient="vertical", command=self._diag_txt.yview)
        self._diag_txt.configure(yscrollcommand=sb4.set)
        self._diag_txt.grid(row=0, column=0, sticky="nsew", padx=(8,0), pady=8)
        sb4.grid(row=0, column=1, sticky="ns", pady=8, padx=(0,6))
        self._diag_txt.tag_configure("g", foreground=GREEN)
        self._diag_txt.tag_configure("r", foreground=RED)
        self._diag_txt.tag_configure("a", foreground=AMBER)
        self._diag_txt.tag_configure("d", foreground=TEXT3)

        btnf = tk.Frame(f, bg=BG)
        btnf.grid(row=2, column=0, sticky="ew", padx=14, pady=(0,14))
        ttk.Button(btnf, text="Run Diagnostics", style="Green.TButton",
                   command=self._run_diag).pack(side="left", ipady=6, ipadx=16)
        ttk.Button(btnf, text="List COM Ports", style="Gray.TButton",
                   command=self._list_ports).pack(side="left", padx=10, ipady=6, ipadx=12)

        self._diag("Run diagnostics to check library and sensor status.", "d")
        self._diag_check_imports()

    def _diag(self, msg: str, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._diag_txt.configure(state="normal")
        self._diag_txt.insert("end", f"[{ts}] ", "d")
        self._diag_txt.insert("end", msg + "\n", tag)
        self._diag_txt.see("end")
        self._diag_txt.configure(state="disabled")

    def _diag_check_imports(self):
        self._diag("─" * 50, "d")
        self._diag(f"Python: {sys.version}", "d")
        self._diag(f"Frozen (running as .exe): {getattr(sys,'frozen',False)}", "d")
        self._diag(f"App dir: {_app_dir()}", "d")
        self._diag(f"config.json path: {CONFIG_FILE}", "d")
        self._diag(f"config.json exists: {os.path.exists(CONFIG_FILE)}", "d")
        self._diag("─" * 50, "d")
        if SENSOR_AVAILABLE:
            self._diag("✓ pyfingerprint imported OK", "g")
        else:
            self._diag("✗ pyfingerprint FAILED to import", "r")
            for e in _IMPORT_ERRORS:
                if "pyfingerprint" in e:
                    self._diag(f"  → {e}", "r")
        if SUPABASE_AVAILABLE:
            self._diag("✓ supabase imported OK", "g")
        else:
            self._diag("✗ supabase FAILED to import", "r")

        # FIX 3 — explicitly check serial sub-modules that PyInstaller often misses
        for mod in ["serial", "serial.serialutil", "serial.serialwin32",
                    "serial.serialposix", "serial.tools", "serial.tools.list_ports"]:
            try:
                __import__(mod)
                self._diag(f"✓ {mod}", "g")
            except ImportError as e:
                self._diag(f"✗ {mod}  →  {e}", "r")

    def _run_diag(self):
        self._diag_txt.configure(state="normal")
        self._diag_txt.delete("1.0", "end")
        self._diag_txt.configure(state="disabled")
        self._diag_check_imports()
        cfg = load_config()
        self._diag("─" * 50, "d")
        self._diag(f"Configured port: {cfg['port']}  baud: {cfg['baud']}", "d")
        self._diag(f"Supabase URL set: {bool(cfg.get('supabase_url','').strip())}", "d")
        self._diag(f"Supabase key set: {bool(cfg.get('supabase_key','').strip())}", "d")
        # try opening the serial port directly
        try:
            import serial
            p = serial.Serial(cfg["port"], int(cfg["baud"]), timeout=1)
            p.close()
            self._diag(f"✓ Serial port {cfg['port']} opened OK", "g")
        except Exception as e:
            self._diag(f"✗ Serial port {cfg['port']} failed: {e}", "r")
            self._diag("  → Check port name, USB cable, and driver (CH340/CP2102)", "a")

    def _list_ports(self):
        try:
            from serial.tools import list_ports
            ports = list(list_ports.comports())
            self._diag("─" * 50, "d")
            if ports:
                self._diag("Available COM ports:", "a")
                for p in ports:
                    self._diag(f"  {p.device}  —  {p.description}", "g")
            else:
                self._diag("No COM ports found. Is the USB-TTL adapter plugged in?", "r")
        except Exception as e:
            self._diag(f"list_ports error: {e}", "r")

    def _show_import_warning(self):
        messagebox.showwarning(
            "Library import errors",
            "Some libraries failed to import:\n\n" +
            "\n".join(_IMPORT_ERRORS) +
            "\n\nCheck the Diagnostics tab for details."
        )

    # ─────────────────────────── SHARED HELPERS ─────────────────────────────
    def _card(self, parent):
        return tk.Frame(parent, bg=CARD, bd=0,
                        highlightthickness=1, highlightbackground=BORDER)

    def _fp_idle(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)   # re-assert after delete("all")
        c.create_oval(10,10,110,110, outline=BORDER, width=2)
        cx,cy = 60,60
        for off in range(-3,4):
            y = cy + off*7; r = 28 + abs(off)*4
            c.create_arc(cx-r, y-r, cx+r, y+r, start=30, extent=120,
                         style="arc", outline=TEXT3, width=1)

    def _fp_scanning(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline=GREEN, width=2)
        cx,cy = 60,60
        for i,off in enumerate(range(-3,4)):
            y = cy + off*7; r = 28 + abs(off)*4
            col = GREEN if abs(off) <= self._anim_step % 4 else TEXT3
            c.create_arc(cx-r, y-r, cx+r, y+r, start=30, extent=120,
                         style="arc", outline=col, width=1)

    def _fp_match(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline=GREEN, width=3)
        c.create_text(60,60, text="✓", fill=GREEN, font=(SANS,32,"bold"))

    def _fp_fail(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline=RED, width=3)
        c.create_text(60,60, text="✕", fill=RED, font=(SANS,32,"bold"))

    # ── Sound ────────────────────────────────────────────────────────────────
    def _beep(self, pattern: str):
        """Play a system sound in a detached subprocess."""
        play_sound(pattern)

    # ── Canvas blink animation ───────────────────────────────────────────────
    # Each blink sequence runs on the main thread via after() chains.
    # _blink_count tracks remaining flashes; _blink_state tracks on/off.

    def _blink_in(self, flashes=4, interval=120):
        """Green blink for IN — alternates between match icon and dark ring."""
        self._blink_sequence(
            on_fn=self._fp_match,
            off_fn=self._fp_match_dim,
            flashes=flashes,
            interval=interval,
            restore_fn=self._fp_match,
        )

    def _blink_out(self, flashes=4, interval=120):
        """Amber blink for OUT."""
        self._blink_sequence(
            on_fn=self._fp_out,
            off_fn=self._fp_out_dim,
            flashes=flashes,
            interval=interval,
            restore_fn=self._fp_out,
        )

    def _blink_fail(self, flashes=3, interval=100):
        """Red blink for no match / fail."""
        self._blink_sequence(
            on_fn=self._fp_fail,
            off_fn=self._fp_fail_dim,
            flashes=flashes,
            interval=interval,
            restore_fn=self._fp_fail,
        )

    def _blink_sequence(self, on_fn, off_fn, flashes, interval, restore_fn):
        """Generic blink: alternate on/off `flashes` times then settle on restore_fn."""
        total_steps = flashes * 2

        def _step(n):
            if n <= 0:
                restore_fn()
                return
            if n % 2 == 0:
                off_fn()
            else:
                on_fn()
            self.after(interval, lambda: _step(n - 1))

        _step(total_steps)

    # ── Dim variants for blink off-frames ────────────────────────────────────
    def _fp_match_dim(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline=GREEND, width=2)
        c.create_text(60,60, text="✓", fill=GREEND, font=(SANS,32,"bold"))

    def _fp_out(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline=AMBER, width=3)
        c.create_text(60,60, text="✓", fill=AMBER, font=(SANS,32,"bold"))

    def _fp_out_dim(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline="#7A5010", width=2)
        c.create_text(60,60, text="✓", fill="#7A5010", font=(SANS,32,"bold"))

    def _fp_fail_dim(self):
        c = self._fp_cv
        c.delete("all")
        c.configure(width=120, height=120)
        c.create_oval(10,10,110,110, outline="#7A1515", width=2)
        c.create_text(60,60, text="✕", fill="#7A1515", font=(SANS,32,"bold"))

    def _log(self, msg: str, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_txt.configure(state="normal")
        self._log_txt.insert("end", f"[{ts}] ", "d")
        self._log_txt.insert("end", msg + "\n", tag)
        self._log_txt.see("end")
        self._log_txt.configure(state="disabled")

    def _clear_log(self):
        self._log_txt.configure(state="normal")
        self._log_txt.delete("1.0","end")
        self._log_txt.configure(state="disabled")

    def _ui(self, fn):
        self._q.put(fn)

    def _poll(self):
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def _status(self, msg: str):
        self._status_var.set(msg)

    # ─────────────────────────── CONNECTION ─────────────────────────────────
    def _toggle_connect(self):
        if self.ctrl.connected:
            self.ctrl.disconnect()
            self._dot.configure(text="○", fg=RED)
            self._conn_btn.configure(text="Connect")
            self._status("Disconnected")
            self._scan_sub.configure(text="Not connected")
            self._sb_lbl.configure(text="Supabase: off")
            self._log("Disconnected.", "a")
        else:
            self._log("Connecting...", "d")
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            self.ctrl.cfg = load_config()
            self.ctrl.connect()
            cnt = self.ctrl.template_count()
            cap = self.ctrl.capacity()
            def ok():
                self._dot.configure(text="●", fg=GREEN)
                self._conn_btn.configure(text="Disconnect")
                self._status(f"Connected  ·  {self.ctrl.cfg['port']}  ·  {cnt}/{cap} templates")
                self._scan_lbl.configure(text="Place finger on sensor")
                self._scan_sub.configure(text=f"Ready on {self.ctrl.cfg['port']}")
                self._m_enrolled.set(str(cnt))
                self._sb_lbl.configure(
                    text="Supabase: on" if self.ctrl.sb else "Supabase: off (no keys)")
                self._log(f"Connected  →  {cnt}/{cap} templates on chip", "g")
            self._ui(ok)
        except Exception as e:
            def err(msg=str(e)):
                messagebox.showerror("Connection failed", msg)
                self._log(f"Connection error: {msg}", "r")
            self._ui(err)

    # ─────────────────────────── CONTINUOUS SCAN ────────────────────────────
    def _start_scan(self):
        if not self.ctrl.connected:
            messagebox.showwarning("Not connected", "Connect to the sensor first.")
            return
        self.scan_active = True
        self._btn_scan.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._pbar.start(12)
        self._anim_loop()
        self._log("Continuous scan started", "b")
        threading.Thread(target=self._scan_loop, daemon=True).start()

    def _stop_scan(self):
        self.scan_active = False

    def _anim_loop(self):
        if self.scan_active:
            self._anim_step += 1
            self._fp_scanning()
            self.after(200, self._anim_loop)

    def _scan_loop(self):
        while self.scan_active:
            try:
                slot, acc = self.ctrl.scan_once()
                ts = datetime.now().strftime("%H:%M:%S")

                if slot == -1:
                    self._fail_count += 1
                    f = self._fail_count
                    self._beep("fail")
                    def show_fail(fc=f):
                        self._blink_fail()
                        self._scan_lbl.configure(text="No match found")
                        self._scan_sub.configure(text="Unknown fingerprint — not in system")
                        self._m_fails.set(str(fc))
                        self._m_conf.set("—")
                        self._scan_tv.insert("","0",values=(ts,"Unknown","—","—","FAIL"),tags=("fail",))
                        self._log("No match — fingerprint not enrolled", "r")
                    self._ui(show_fail)
                else:
                    # Look up employee by fingerprint slot
                    try:
                        employee = self.ctrl.get_employee_by_slot(slot)
                    except Exception as e:
                        self._ui(lambda err=str(e): self._log(f"get_employee error: {err}", "r"))
                        self.ctrl.wait_for_lift()
                        time.sleep(0.5)
                        continue

                    if employee is None:
                        self._fail_count += 1
                        f = self._fail_count
                        self._beep("fail")
                        def show_no_user(fc=f, s=slot):
                            self._blink_fail()
                            self._scan_lbl.configure(text="Employee not found")
                            self._scan_sub.configure(text=f"Slot #{s} matched but no user record in database")
                            self._m_fails.set(str(fc))
                            self._scan_tv.insert("","0",values=(ts,"—",f"#{s}","—","NO USER"),tags=("fail",))
                            self._log(f"Slot #{s} matched but no employee record in Supabase — check FingerprintSlot value", "r")
                        self._ui(show_no_user)
                    else:
                        self._match_count += 1
                        emp_id   = employee["EmployeeId"]
                        fullname = f"{employee['FirstName']} {employee['LastName']}"
                        role     = employee.get("Role", "")
                        cpct     = f"{min(int(acc/2),100)}%"

                        # Determine IN / OUT
                        try:
                            latest = self.ctrl.get_latest_status(emp_id)
                        except Exception as e:
                            latest = None
                            self._ui(lambda err=str(e): self._log(f"get_latest_status error: {err}", "r"))

                        status = "OUT" if latest == "IN" else "IN"

                        # Queue sound — returns instantly
                        self._beep(status.lower())

                        # Write to personnel_entry_logs
                        try:
                            self.ctrl.log_entry(employee, status)
                            supabase_ok = True
                        except Exception as e:
                            supabase_ok = False
                            self._ui(lambda err=str(e): self._log(f"log_entry FAILED: {err}", "r"))

                        m = self._match_count
                        def show_match(n=fullname, r=role, s=slot, cp=cpct,
                                       st=status, mc=m, ok=supabase_ok):
                            # Blink green for IN, amber for OUT
                            if st == "IN":
                                self._blink_in()
                            else:
                                self._blink_out()
                            status_color = GREEN if st == "IN" else AMBER
                            self._scan_lbl.configure(text=f"{n}  —  {st}", fg=status_color)
                            sb_note = "logged to Supabase" if ok else "⚠ Supabase insert FAILED — check Log tab"
                            self._scan_sub.configure(
                                text=f"{r}  ·  slot #{s}  ·  {cp}  ·  {sb_note}")
                            self._m_matches.set(str(mc))
                            self._m_conf.set(cp)
                            tag = "match" if st == "IN" else "out"
                            self._scan_tv.insert("","0",
                                values=(ts, n, f"#{s}", cp, st), tags=(tag,))
                            log_tag = ("g" if st == "IN" else "a") if ok else "r"
                            self._log(
                                f"{st}  →  {n}  ({r})  slot={s}  acc={cp}"
                                + ("" if ok else "  [SUPABASE INSERT FAILED]"),
                                log_tag
                            )
                        self._ui(show_match)

                self.ctrl.wait_for_lift()
                time.sleep(0.5)

                # reset canvas after 2 s
                time.sleep(2)
                if self.scan_active:
                    self._ui(lambda: (
                        self._fp_scanning(),
                        self._scan_lbl.configure(text="Place finger on sensor", fg=TEXT),
                        self._scan_sub.configure(text="Scanning..."),
                    ))

            except Exception as e:
                if self.scan_active:
                    self._ui(lambda err=str(e): self._log(f"Scan error: {err}", "r"))
                time.sleep(1)

        def done():
            self._btn_scan.configure(state="normal")
            self._btn_stop.configure(state="disabled")
            self._pbar.stop()
            self._fp_idle()
            self._scan_lbl.configure(text="Place finger on sensor", fg=TEXT)
            self._scan_sub.configure(text="Scan stopped")
            self._log("Scan stopped", "a")
        self._ui(done)

    # ─────────────────────────── ENROLL ─────────────────────────────────────
    def _search_employee(self):
        if not self.ctrl.sb:
            messagebox.showwarning("Not connected", "Connect to Supabase first.")
            return
        term = self._search_var.get().strip()
        if not term:
            messagebox.showwarning("Enter a name", "Type a first name to search.")
            return
        threading.Thread(target=self._do_search, args=(term,), daemon=True).start()

    def _do_search(self, term: str):
        try:
            results = self.ctrl.search_employees(term)
            def populate(r=results):
                self._search_results = r
                self._employee_lb.delete(0, "end")
                if not r:
                    self._employee_lb.insert("end", "  No employees found")
                    self._selected_emp_var.set("No employee selected")
                    self._selected_employee = None
                else:
                    for emp in r:
                        slot_txt = f"slot #{emp['FingerprintSlot']}" if emp.get("FingerprintSlot") else "no slot"
                        self._employee_lb.insert(
                            "end",
                            f"  {emp['FirstName']} {emp['LastName']}  ·  {emp['Role']}  ·  {slot_txt}"
                        )
            self._ui(populate)
        except Exception as e:
            self._ui(lambda: self._log(f"Search error: {e}", "r"))

    def _on_employee_select(self, _event=None):
        sel = self._employee_lb.curselection()
        if not sel or not self._search_results:
            return
        idx = sel[0]
        if idx >= len(self._search_results):
            return
        emp = self._search_results[idx]
        self._selected_employee = emp
        slot_txt = f"slot #{emp['FingerprintSlot']}" if emp.get("FingerprintSlot") else "no fingerprint yet"
        self._selected_emp_var.set(
            f"Selected: {emp['FirstName']} {emp['LastName']}  ·  {emp['Role']}  ·  ID #{emp['EmployeeId']}  ·  {slot_txt}"
        )

    def _start_enroll(self):
        if not self.ctrl.connected:
            messagebox.showwarning("Not connected", "Connect to the sensor first.")
            return
        if self._selected_employee is None:
            messagebox.showwarning("No employee selected", "Search and select an employee first.")
            return
        emp = self._selected_employee
        if emp.get("FingerprintSlot") is not None:
            if not messagebox.askyesno(
                "Already enrolled",
                f"{emp['FirstName']} {emp['LastName']} already has slot #{emp['FingerprintSlot']}.\n"
                "Re-enrolling will overwrite it. Continue?"
            ):
                return
        self._enroll_btn.configure(state="disabled")
        for lbl in self._estep_lbls:
            lbl.configure(fg=TEXT3)
        self._estatus.configure(text="")
        threading.Thread(target=self._do_enroll, args=(emp,), daemon=True).start()

    def _estep(self, idx: int):
        def fn():
            for i, lbl in enumerate(self._estep_lbls):
                if   i < idx:  lbl.configure(fg=GREEN)
                elif i == idx: lbl.configure(fg=AMBER)
                else:          lbl.configure(fg=TEXT3)
        self._ui(fn)

    def _do_enroll(self, emp: dict):
        fullname = f"{emp['FirstName']} {emp['LastName']}"
        try:
            self._ui(lambda: self._estatus.configure(text="Waiting for finger (scan 1)…", fg=AMBER))
            self._estep(0)
            self.ctrl.enroll_step1()

            self._estep(1)
            self._ui(lambda: self._estatus.configure(text="Remove finger…", fg=AMBER))
            self.ctrl.wait_for_lift()
            time.sleep(1)

            self._estep(2)
            self._ui(lambda: self._estatus.configure(text="Place same finger (scan 2)…", fg=AMBER))
            self.ctrl.enroll_step2()

            self._estep(3)
            self._ui(lambda: self._estatus.configure(text="Saving template…", fg=AMBER))
            slot = self.ctrl.enroll_finish()

            # Save slot back to the user row in Supabase
            self.ctrl.assign_slot(emp["EmployeeId"], slot)
            cnt = self.ctrl.template_count()

            def ok(n=fullname, s=slot, c=cnt):
                for lbl in self._estep_lbls:
                    lbl.configure(fg=GREEN)
                self._estatus.configure(text=f"✓  {n} enrolled at slot #{s}", fg=GREEN)
                self._selected_employee = None
                self._selected_emp_var.set("No employee selected")
                self._employee_lb.delete(0, "end")
                self._search_var.set("")
                self._m_enrolled.set(str(c))
                self._log(f"Enrolled: {n}  slot=#{s}  EmployeeId={emp['EmployeeId']}", "g")
                self._enroll_btn.configure(state="normal")
                self._refresh_users()
            self._ui(ok)

        except Exception as e:
            def fail(err=str(e)):
                self._estatus.configure(text=f"✕  {err}", fg=RED)
                self._log(f"Enroll error: {err}", "r")
                self._enroll_btn.configure(state="normal")
            self._ui(fail)

    # ─────────────────────────── USERS ──────────────────────────────────────
    def _refresh_users(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            if self.ctrl.sb:
                rows = self.ctrl.get_users()
            elif self.ctrl.sensor:
                slots = self.ctrl.list_templates()
                rows  = [{"FingerprintSlot": s, "FirstName": f"Slot #{s}",
                           "LastName": "", "Role": "—"}
                          for s in slots]
            else:
                rows = []
            def populate(r=rows):
                for item in self._users_tv.get_children():
                    self._users_tv.delete(item)
                for u in r:
                    fullname = f"{u.get('FirstName','')} {u.get('LastName','')}".strip()
                    self._users_tv.insert("","end", values=(
                        u.get("FingerprintSlot","—"),
                        u.get("EmployeeId","—"),
                        fullname,
                        u.get("Role","—"),
                    ))
                self._m_enrolled.set(str(len(r)))
            self._ui(populate)
        except Exception as e:
            self._ui(lambda: self._log(f"Refresh error: {e}", "r"))

    def _delete_user(self):
        sel = self._users_tv.selection()
        if not sel:
            messagebox.showinfo("Select user", "Click a user first."); return
        vals = self._users_tv.item(sel[0], "values")
        slot, emp_id, name = vals[0], vals[1], vals[2]
        if slot == "—":
            messagebox.showinfo("No slot", "This user has no fingerprint slot to delete.")
            return
        if not messagebox.askyesno("Delete fingerprint",
                                    f"Remove fingerprint for {name}?\n"
                                    f"This deletes the template from the sensor and clears slot #{slot} in Supabase.\n"
                                    f"The employee record itself is NOT deleted."):
            return
        threading.Thread(target=self._do_delete, args=(int(slot), name), daemon=True).start()

    def _do_delete(self, slot: int, name: str):
        try:
            if self.ctrl.sensor:
                self.ctrl.delete_template(slot)
            self.ctrl.clear_slot(slot)
            cnt = self.ctrl.template_count()
            self._ui(lambda: (
                self._log(f"Fingerprint removed: {name}  slot=#{slot}", "a"),
                self._m_enrolled.set(str(cnt)),
                self._refresh_users(),
            ))
        except Exception as e:
            self._ui(lambda: self._log(f"Delete error: {e}", "r"))

    # ─────────────────────────── SETTINGS ───────────────────────────────────
    def _settings(self):
        cfg = load_config()
        win = tk.Toplevel(self)
        win.title("Settings"); win.geometry("440x310")
        win.configure(bg=BG); win.resizable(False,False); win.grab_set()

        tk.Label(win, text="Connection Settings", fg=TEXT, bg=BG,
                 font=(SANS,13,"bold")).pack(pady=(18,3))
        tk.Label(win, text="Changes apply on next Connect.", fg=TEXT2, bg=BG,
                 font=(SANS,9)).pack(pady=(0,12))

        card = self._card(win)
        card.pack(fill="x", padx=20)
        form = tk.Frame(card, bg=CARD)
        form.pack(fill="x", padx=20, pady=14)
        form.columnconfigure(1, weight=1)

        entries: dict[str, tk.StringVar] = {}
        for i,(lbl,key,val) in enumerate([
            ("COM Port",          "port",         cfg["port"]),
            ("Baud Rate",         "baud",         str(cfg["baud"])),
            ("Supabase URL",      "supabase_url", cfg["supabase_url"]),
            ("Supabase Anon Key", "supabase_key", cfg["supabase_key"]),
        ]):
            tk.Label(form, text=lbl, fg=TEXT2, bg=CARD,
                     font=(SANS,10)).grid(row=i, column=0, sticky="w", pady=5, padx=(0,14))
            var = tk.StringVar(value=val)
            ttk.Entry(form, textvariable=var,
                      show=("*" if "key" in key else ""),
                      width=30).grid(row=i, column=1, sticky="ew", pady=5)
            entries[key] = var

        def save():
            new = {k: v.get() for k,v in entries.items()}
            new["baud"] = int(new.get("baud", 57600) or 57600)
            save_config(new)
            self._log("Settings saved. Reconnect to apply.", "a")
            win.destroy()

        btnf = tk.Frame(win, bg=BG)
        btnf.pack(pady=14)
        ttk.Button(btnf, text="Save", style="Green.TButton",
                   command=save).pack(side="left", padx=8, ipady=6, ipadx=20)
        ttk.Button(btnf, text="Cancel", style="Gray.TButton",
                   command=win.destroy).pack(side="left", padx=8, ipady=6, ipadx=14)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
    _sound_q.put(None)       # tell worker to stop cleanly
    _sound_thread.join(timeout=2)
