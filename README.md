# FingerprintBridge — AS608 / JM101B Desktop App

All-in-one Tkinter GUI: continuous scan, enroll, delete, user list,
Supabase logging — compiled to a single Windows .exe.

────────────────────────────────────────────────────────────────
WIRING (CRITICAL — this is the #1 cause of "sensor not found")
────────────────────────────────────────────────────────────────
  AS608 / JM101B    USB-TTL Adapter
  TX            →   RX          ← MUST be crossed
  RX            →   TX          ← MUST be crossed
  GND           →   GND
  VCC           →   3.3 V

  Straight (TX→TX) = sensor not found, every time.

────────────────────────────────────────────────────────────────
WHY THE .EXE DIDN'T CONNECT (and what was fixed)
────────────────────────────────────────────────────────────────
Three bugs existed in the original build:

  1. serial.serialwin32 was missing from hiddenimports
     PyInstaller auto-detects the pyserial *package* but not the
     Windows-specific backend. The port appeared to open, but
     every read/write silently did nothing — so the sensor never
     responded. Fixed: serial.serialwin32 + serial.win32 added.

  2. config.json was written to the wrong folder
     resource_path() was routing config.json into _MEIPASS —
     a read-only temp folder destroyed when the .exe exits.
     The .exe was reading stale/empty config on every launch.
     Fixed: _app_dir() now always uses os.path.dirname(sys.executable)
     so config.json sits next to the .exe permanently.

  3. Import errors were silently swallowed
     The original try/except ImportError hid the real Python
     error message (e.g. "No module named serial.serialwin32").
     Fixed: errors are now stored in _IMPORT_ERRORS and shown
     in the connection error dialog so you know exactly what
     PyInstaller forgot to bundle.

────────────────────────────────────────────────────────────────
BUILD THE .EXE
────────────────────────────────────────────────────────────────
  # 1. Install everything
  pip install pyinstaller pyfingerprint pyserial supabase

  # 2. Build (run from this folder)
  pyinstaller fingerprint_app.spec

  Output: dist\FingerprintBridge.exe   ← single portable file

  config.json is created next to the .exe when you save Settings.
  Copy both files if you move the .exe to another machine.

────────────────────────────────────────────────────────────────
DIAGNOSING BUILD ISSUES
────────────────────────────────────────────────────────────────
  If the .exe still can't connect, run it from Command Prompt:

    cd dist
    FingerprintBridge.exe

  The connection error dialog will now show the exact missing
  module name (e.g. "No module named 'serial.serialwin32'").
  Add that module to hiddenimports in the .spec and rebuild.

  Alternatively, temporarily set console=True in the .spec to
  see all Python tracebacks in a CMD window.

────────────────────────────────────────────────────────────────
SUPABASE SETUP (one-time)
────────────────────────────────────────────────────────────────
  1. Create project at https://supabase.com
  2. SQL Editor → paste supabase_schema.sql → Run
  3. Settings → API → copy Project URL + anon key
  4. In app: ⚙ Settings → paste URL + key → Save → Connect

────────────────────────────────────────────────────────────────
APP TABS
────────────────────────────────────────────────────────────────
  Scan   — continuous scan loop, live match display, history table
  Enroll — guided 2-scan enrollment → saves to sensor + Supabase
  Users  — view / delete enrolled users
  Log    — timestamped event log with colour coding

────────────────────────────────────────────────────────────────
AUTO-START ON WINDOWS BOOT
────────────────────────────────────────────────────────────────
  Task Scheduler → Create Basic Task
    Trigger : When I log on
    Action  : Start a program → path to FingerprintBridge.exe
