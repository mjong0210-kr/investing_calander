# Playwright browser packaging fix

If the EXE fails with an error like:

`BrowserType.launch: Executable doesn't exist ... playwright ... .local-browsers ... headless_shell.exe`

that means the EXE bundled the Playwright Python package but did not bundle the Chromium browser binary.

This v5 build fixes that by:

1. Setting `PLAYWRIGHT_BROWSERS_PATH=0` in GitHub Actions.
2. Running `playwright install chromium` during the Windows build.
3. Building with `InvestingCalendarTelegramBot.spec`, which uses `collect_data_files("playwright")` to include the Playwright driver and bundled Chromium.

After rebuilding with this version, the user PC should not need Python or a separate `playwright install` command.
