@echo off
setlocal
cd /d "%~dp0"

REM Windows EXE build helper. Run this on a Windows PC where Python is available.
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
playwright install chromium
pyinstaller --noconfirm --onefile --name InvestingCalendarTelegramBot --hidden-import=zoneinfo investing_calendar_telegram_bot.py

echo.
echo Build complete: dist\InvestingCalendarTelegramBot.exe
echo Put .env in the same folder as the EXE before running.
pause
