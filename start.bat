@ECHO OFF

:: Entry point for Pixeler. Runs __main__.py (the floating Input / Output panels).
:: The first run creates a virtual environment in .\.venv and installs requirements.txt into it.

IF NOT EXIST .venv (
    ECHO Setting up virtual environment and installing requirements...
    ECHO Creating virtual environment...
    python -m venv .venv

    ECHO Installing required packages...
    .\.venv\Scripts\pip.exe install -r .\requirements.txt

    ECHO Done! Virtual environment is set up.
)

IF EXIST .venv (
    ECHO Activating virtual environment...
    CALL .venv\Scripts\activate
)

ECHO Running Pixeler...
ECHO #################################
.\.venv\Scripts\python.exe .
