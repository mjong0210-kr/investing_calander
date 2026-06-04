# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Important for Playwright:
# In GitHub Actions we install Chromium with PLAYWRIGHT_BROWSERS_PATH=0.
# That places the browser under the playwright package directory.
# collect_data_files("playwright") then bundles Playwright's driver + bundled Chromium
# into the one-file EXE extraction directory, so the user does NOT need Python or
# "playwright install" on their PC.
playwright_datas = collect_data_files("playwright")
playwright_hiddenimports = collect_submodules("playwright")


a = Analysis(
    ['investing_calendar_telegram_bot.py'],
    pathex=[],
    binaries=[],
    datas=playwright_datas,
    hiddenimports=playwright_hiddenimports + ['zoneinfo'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='InvestingCalendarTelegramBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
