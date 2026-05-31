# FingerprintBridge — AS608 / JM101B Desktop App

All-in-one Tkinter GUI: continuous scan, enroll, delete, user list, Supabase logging — compiled to a single Windows `.exe`.

## Wiring (Critical — #1 Cause of "Sensor Not Found")

| AS608 / JM101B | USB-TTL Adapter      |
| -------------- | -------------------- |
| TX             | RX ← MUST be crossed |
| RX             | TX ← MUST be crossed |
| GND            | GND                  |
| VCC            | 3.3 V                |

> **Straight wiring (TX→TX) = sensor not found, every time.**

## Why the `.exe` Didn't Connect (and What Was Fixed)

Three bugs existed in the original build:

### 1. `serial.serialwin32` was missing from hiddenimports

PyInstaller auto-detects the pyserial package but not the Windows-specific backend.

The port appeared to open, but every read/write silently did nothing, so the sensor never responded.

**Fixed:** `serial.serialwin32` and `serial.win32` added.

### 2. `config.json` was written to the wrong folder

`resource_path()` was routing `config.json` into `_MEIPASS` — a read-only temp folder destroyed when the `.exe` exits.

The `.exe` was reading stale/empty config on every launch.

**Fixed:** `_app_dir()` now always uses:

```python
os.path.dirname(sys.executable)
```

so `config.json` sits permanently beside the `.exe`.

### 3. Import errors were silently swallowed

The original `try/except ImportError` hid the real Python error message (e.g. `"No module named serial.serialwin32"`).

**Fixed:** Errors are now stored in `_IMPORT_ERRORS` and shown in the connection error dialog so you know exactly what PyInstaller forgot to bundle.

## Build the `.exe`

### 1. Install dependencies

```bash
pip install pyinstaller pyfingerprint pyserial supabase
```

### 2. Build

Run from the project folder:

```bash
pyinstaller fingerprint_app.spec
```

Output:

```text
dist\FingerprintBridge.exe
```

A single portable executable.

`config.json` is created next to the `.exe` when you save Settings.

If you move the application to another machine, copy both the `.exe` and `config.json`.

## Diagnosing Build Issues

If the `.exe` still can't connect, run it from Command Prompt:

```bash
cd dist
FingerprintBridge.exe
```

The connection error dialog will now show the exact missing module name (for example, `"No module named 'serial.serialwin32'"`).

Add that module to `hiddenimports` in the `.spec` file and rebuild.

Alternatively, temporarily set:

```python
console=True
```

in the `.spec` file to see full Python tracebacks in a CMD window.

## Supabase Setup (One-Time)

1. Create a project at https://supabase.com
2. Open **SQL Editor**
3. Paste `supabase_schema.sql`
4. Click **Run**
5. Open **Settings → API**
6. Copy the Project URL and anon key
7. In the app, open **⚙ Settings**
8. Paste the URL and key
9. Click **Save**
10. Click **Connect**

## App Tabs

| Tab    | Description                                             |
| ------ | ------------------------------------------------------- |
| Scan   | Continuous scan loop, live match display, history table |
| Enroll | Guided 2-scan enrollment, saves to sensor and Supabase  |
| Users  | View and delete enrolled users                          |
| Log    | Timestamped event log with color coding                 |

## Auto-Start on Windows Boot

Using **Task Scheduler**:

1. Create Basic Task
2. **Trigger:** When I log on
3. **Action:** Start a program
4. Select `FingerprintBridge.exe`
