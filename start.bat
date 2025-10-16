@ECHO OFF

:: This is the main entry point for the application in the newest version.
:: Instead of using pixelCounter.py and pixeler.py separately, we now use __main__.py to handle both functionalities.
:: This simplifies the user experience, ensures that all dependencies are managed in one place, and reduces redundancy in the codebase.
:: Files under .\python\ folder will become obsolete when the main file is finished.

:: Check if .venv folder exists, if it doesn't, create it, if it does, installs requirements.
IF NOT EXIST .venv (
    :: Inform the user that the virtual environment is being set up
    ECHO Setting up virtual environment and installing requirements...
    
    :: We have to create a virtual environment to prevent cluttering the user's global Python installation
    :: This script creates a virtual environment in the .venv folder and installs the required packages from requirements.txt

    :: Check if .venv folder already exists
    IF EXIST .venv (
        ECHO Virtual environment already exists. Skipping creation.
        EXIT /B 0
    )

    :: Inform the user that the virtual environment is being created
    ECHO Creating virtual environment...
    python -m venv .venv

    :: Inform the user that packages are being installed
    ECHO Installing required packages...
    .\.venv\Scripts\pip.exe install -r .\requirements.txt

    ECHO Done! Virtual environment is set up.
)

:: Check if .venv exists, if it does, activate the virtual environment
IF EXIST .venv (
    :: Inform the user that the virtual environment is being activated
    ECHO Activating virtual environment...
    CALL .venv\Scripts\activate
)

ECHO Running Pixeler...
ECHO #################################
:: Run script using virtual environment's python file.
.\.venv\Scripts\python.exe .