@echo off
setlocal
CLS
ECHO.
ECHO This script will run the specified Python tray application with necessary privileges.

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
if "%~1"=="" (
    set "PYTHON_MAIN_SCRIPT=tray_app.py"
) else (
    set "PYTHON_MAIN_SCRIPT=%~1"
)
set "VENV_PRIMARY_NAME=.venv"
set "VENV_FALLBACK_NAME=venv"
set "PYTHON_CMD="
set "VENV_DIR_TO_USE="
set "WMI_REQUIRED=1"
set "REQUIREMENTS_FILE=requirements.txt"

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
        exit
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
    exit
) else (
    echo Python detected: %PYTHON_CMD%
)

set "VENV_SETUP_NEEDED=0"
REM Detect or create virtual environment
if exist "%VENV_PRIMARY_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
    echo Found existing virtual environment: %VENV_DIR_TO_USE%
) else if exist "%VENV_FALLBACK_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_FALLBACK_NAME%"
    echo Found existing virtual environment: %VENV_DIR_TO_USE%
) else (
    echo No virtual environment found. Creating one in "%VENV_PRIMARY_NAME%"...
    %PYTHON_CMD% -m venv "%VENV_PRIMARY_NAME%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment in %VENV_PRIMARY_NAME%.
        exit
    )
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
    set "VENV_SETUP_NEEDED=1"
)

REM Check if a virtual environment is already active
if defined VIRTUAL_ENV (
    echo Virtual environment already active: %VIRTUAL_ENV%
) else (
    REM Activate virtual environment
    echo Activating virtual environment: %VENV_DIR_TO_USE%
    call "%VENV_DIR_TO_USE%\Scripts\activate.bat"
    if errorlevel 1 (
        echo ERROR: Failed to activate virtual environment %VENV_DIR_TO_USE%.
        exit
    )
)

REM Perform setup if a new venv was created
if "%VENV_SETUP_NEEDED%"=="1" (
    echo Performing setup for new virtual environment: %VENV_DIR_TO_USE%

    REM Upgrade pip
    echo Upgrading pip...
    %PYTHON_CMD% -m pip install --upgrade pip
    if errorlevel 1 (
        echo ERROR: Failed to upgrade pip in %VENV_DIR_TO_USE%.
        exit
    )
    echo pip upgraded successfully.

    REM Install required packages from requirements.txt
    if exist "%SCRIPT_DIR%%REQUIREMENTS_FILE%" (
        echo Installing required Python packages from %REQUIREMENTS_FILE%...
        %PYTHON_CMD% -m pip install -r "%SCRIPT_DIR%%REQUIREMENTS_FILE%"
        if errorlevel 1 (
            echo ERROR: Failed to install packages from %REQUIREMENTS_FILE%.
            exit
        )
    ) else (
        echo Installing default Python packages into %VENV_DIR_TO_USE%...
        %PYTHON_CMD% -m pip install PyQt6 pystray pillow keyring PyQt6-WebEngine pyinstaller cryptography WMI pywin32
        if errorlevel 1 (
            echo ERROR: Failed to install default packages into %VENV_DIR_TO_USE%.
            exit
        )
    )
    echo Python packages installed successfully.

    REM Run pywin32 post-install script
    echo Running pywin32 post-install script for %VENV_DIR_TO_USE%...
    %PYTHON_CMD% "%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py" -install
    if errorlevel 1 (
        echo ERROR: Failed to run pywin32 post-install script for %VENV_DIR_TO_USE%.
        exit
    )
    echo pywin32 post-install script completed successfully.
)

REM Ensure pywin32 components are registered if pywin32 is installed
set "PYWIN32_POSTINSTALL_SCRIPT=%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py"
if exist "%PYWIN32_POSTINSTALL_SCRIPT%" (
    echo Ensuring pywin32 components are registered for %VENV_DIR_TO_USE%...
    %PYTHON_CMD% "%PYWIN32_POSTINSTALL_SCRIPT%" -install
    if errorlevel 1 (
        echo ERROR: Failed to run pywin32 post-install script for %VENV_DIR_TO_USE%.
        echo This script is necessary for WMI functionality. Please check permissions or pywin32 installation.
        exit
    ) else (
        echo pywin32 post-install script checked/run successfully for %VENV_DIR_TO_USE%.
    )
)

REM Check and ensure WMI service (winmgmt) is running if required
if "%WMI_REQUIRED%"=="1" (
    echo Checking WMI Service status...
    sc query winmgmt | find "RUNNING" > nul
    if errorlevel 1 (
        echo WMI Service (winmgmt) is not running. Attempting to start it...
        net start winmgmt 2>>wmi_error.log
        if errorlevel 1 (
            echo WARNING: Failed to start WMI Service. Features like system monitoring or hardware queries in %PYTHON_MAIN_SCRIPT% may not work. Check wmi_error.log for details.
        ) else (
            echo WMI Service started. Waiting for initialization...
            set /a "timeout_count=0"
            :wait_wmi
            sc query winmgmt | find "RUNNING" > nul
            if errorlevel 1 (
                if %timeout_count% GEQ 10 (
                    echo WARNING: WMI Service failed to start after 10 seconds. Features like system monitoring may not work.
                    goto continue
                )
                timeout /t 1 /nobreak > nul
                set /a "timeout_count+=1"
                goto wait_wmi
            )
            echo WMI Service is now running.
        )
    ) else (
        echo WMI Service (winmgmt) is running.
    )
) else (
    echo Skipping WMI service check as it is not required.
)
:continue

REM Run the Python script
echo Running the Python script: %PYTHON_MAIN_SCRIPT%...
%PYTHON_CMD% "%SCRIPT_DIR%%PYTHON_MAIN_SCRIPT%" 2>python_error.log
if errorlevel 1 (
    echo ERROR: Python script execution failed. See python_error.log for details.
    exit
)

echo Script completed successfully.
exit