@echo off
setlocal
CLS
ECHO.
ECHO This script will run the Python tray application with the necessary privileges.

:init
setlocal DisableDelayedExpansion
set "batchPath=%~0"
for %%k in (%0) do set batchName=%%~nk
set "vbsGetPrivileges=%temp%\OEgetPriv_%batchName%.vbs"
setlocal EnableDelayedExpansion
:checkPrivileges
NET FILE 1>NUL 2>NUL
if '%errorlevel%' == '0' ( goto gotPrivileges ) else ( goto getPrivileges )

:getPrivileges
if '%1'=='ELEV' (echo ELEV & shift /1 & goto gotPrivileges)
ECHO.
ECHO Invoking UAC for Privilege Escalation
ECHO Set UAC = CreateObject^("Shell.Application"^) > "%vbsGetPrivileges%"
ECHO args = "ELEV " >> "%vbsGetPrivileges%"
ECHO For Each strArg in WScript.Arguments >> "%vbsGetPrivileges%"
ECHO args = args ^& strArg ^& " "  >> "%vbsGetPrivileges%"
ECHO Next >> "%vbsGetPrivileges%"
ECHO UAC.ShellExecute "!batchPath!", args, "", "runas", 1 >> "%vbsGetPrivileges%"
"%SystemRoot%\System32\WScript.exe" "%vbsGetPrivileges%" %*
exit /B

:gotPrivileges
setlocal & pushd .
cd /d %~dp0
if '%1'=='ELEV' (del "%vbsGetPrivileges%" 1>nul 2>nul & shift /1)

:Variables
cls
ECHO Initializing script variables...
set "SCRIPT_DIR=%~dp0"
set "PYTHON_MAIN_SCRIPT=tray_app.py"
set "VENV_PRIMARY_NAME=.venv"
set "VENV_FALLBACK_NAME=venv"
set "PYTHON_CMD="
set "VENV_DIR_TO_USE="

REM Add current directory and bin folder to PATH
set "Path=%Path%;%CD%;%CD%\bin;"

REM Ensure bin directory exists
if not exist "bin" md bin

REM Check for Python installation
echo Searching for Python installation...
where python >nul 2>nul
if errorlevel 1 (
    where python3 >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python is not installed or not found in your system's PATH.
        exit /B
    ) else (
        set "PYTHON_CMD=python3"
    )
) else (
    set "PYTHON_CMD=python"
)

REM Verify Python command works
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not functional or not properly configured in PATH.
    exit /B
) else (
    echo Python detected: %PYTHON_CMD%
)

REM Detect or create virtual environment
if exist "%VENV_PRIMARY_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
) else if exist "%VENV_FALLBACK_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_FALLBACK_NAME%"
) else (
    echo No virtual environment found. Creating one in "%VENV_PRIMARY_NAME%"...
    %PYTHON_CMD% -m venv "%VENV_PRIMARY_NAME%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /B
    )
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
)

REM Create virtual environment if it doesn't exist
if not exist "%VENV_PRIMARY_NAME%" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv "%VENV_PRIMARY_NAME%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /B
    )
    echo Virtual environment created successfully.

    REM Activate the virtual environment
    call "%VENV_PRIMARY_NAME%\Scripts\activate.bat"

    REM Install required packages
    echo Installing required Python packages...
    pip install PyQt6 pystray pillow keyring PyQt6-WebEngine pyinstaller cryptography WMI pywin32
    if errorlevel 1 (
        echo ERROR: Failed to install required packages.
        exit /B
    )
    echo Python packages installed successfully.

    REM Run pywin32 post-install script
    echo Running pywin32 post-install script...
    python .venv\Lib\site-packages\win32\scripts\pywin32_postinstall.py -install
    if errorlevel 1 (
        echo ERROR: Failed to run pywin32 post-install script.
        exit /B
    )
    echo pywin32 post-install script completed successfully.
)

REM Activate virtual environment
call "%VENV_DIR_TO_USE%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    exit /B
)

REM Run the Python script
echo Running the Python script: %PYTHON_MAIN_SCRIPT%...
%PYTHON_CMD% "%SCRIPT_DIR%%PYTHON_MAIN_SCRIPT%"
if errorlevel 1 (
    echo ERROR: Python script execution failed.
    exit /B
)

echo Script completed successfully.
exit /B
