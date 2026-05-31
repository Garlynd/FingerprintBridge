# fingerprint_app.spec
# Build command:  pyinstaller fingerprint_app.spec
#
# Prerequisites (run once in your terminal):
#   pip install pyinstaller pyfingerprint pyserial supabase Pillow

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ['fingerprint_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # ── pyserial ─────────────────────────────────────────────────────────
        'serial',
        'serial.serialutil',
        'serial.serialwin32',       # Windows UART — most commonly missed
        'serial.tools',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        # serial.serialposix / fcntl are Linux-only — safe to omit on Windows

        # ── pyfingerprint ─────────────────────────────────────────────────────
        'pyfingerprint',
        'pyfingerprint.pyfingerprint',

        # ── Pillow — pyfingerprint imports PIL internally ──────────────────────
        # Previously in `excludes` by mistake — that was actively blocking it.
        'PIL',
        'PIL.Image',
        'PIL.ImageOps',
        'PIL.ImageFilter',
        'PIL.ImageDraw',
        'PIL.ImageFile',
        'PIL.BmpImagePlugin',
        'PIL.PngImagePlugin',
        'PIL.JpegImagePlugin',
        'PIL.TiffImagePlugin',

        # ── supabase stack ────────────────────────────────────────────────────
        'supabase',
        'supabase._sync.client',
        'supabase._async.client',
        'gotrue',
        'gotrue._sync.gotrue_client',
        'gotrue._async.gotrue_client',
        'postgrest',
        'postgrest._sync.client',
        'postgrest._async.client',
        'storage3',
        'realtime',
        'httpx',
        'httpx._transports.default',
        'httpcore',
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
        'sniffio',
        'certifi',

        # ── tkinter ───────────────────────────────────────────────────────────
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # DO NOT put PIL/Pillow here — pyfingerprint needs it
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FingerprintBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no black console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',    # uncomment if you have icon.ico next to this file
)
