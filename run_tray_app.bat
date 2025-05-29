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

REM Determine the Python script to run and its display name
if "%~1"=="" (
    set "PYTHON_SCRIPT_FULL_PATH=%SCRIPT_DIR%tray_app.py"
    set "PYTHON_SCRIPT_DISPLAY_NAME=tray_app.py"
) else (
    set "USER_SUPPLIED_SCRIPT_PATH=%~1"
    REM Check if USER_SUPPLIED_SCRIPT_PATH is absolute. A simple check for a colon.
    echo "%USER_SUPPLIED_SCRIPT_PATH%" | find ":" > nul
    if errorlevel 1 (
        REM No colon, assume relative to SCRIPT_DIR
        set "PYTHON_SCRIPT_FULL_PATH=%SCRIPT_DIR%%USER_SUPPLIED_SCRIPT_PATH%"
        set "PYTHON_SCRIPT_DISPLAY_NAME=%USER_SUPPLIED_SCRIPT_PATH%"
    ) else (
        REM Has a colon, assume absolute path
        set "PYTHON_SCRIPT_FULL_PATH=%USER_SUPPLIED_SCRIPT_PATH%"
        REM For display name, get just the filename part
        for %%f in ("%USER_SUPPLIED_SCRIPT_PATH%") do set "PYTHON_SCRIPT_DISPLAY_NAME=%%~nxf"
    )
)

set "VENV_PRIMARY_NAME=.venv"
set "VENV_FALLBACK_NAME=venv"
set "PYTHON_CMD="
set "VENV_DIR_TO_USE="
set "WMI_REQUIRED=1" REM Set to 0 to skip WMI service checks if not needed by the Python script

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
        exit /B
    )
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
    set "VENV_SETUP_NEEDED=1"
)

REM Perform setup if a new venv was created
if "%VENV_SETUP_NEEDED%"=="1" (
    echo Performing setup for new virtual environment: %VENV_DIR_TO_USE%

    REM Activate the virtual environment if not already active
    if defined VIRTUAL_ENV (
        echo Virtual environment %VIRTUAL_ENV% already active. Skipping activation for setup.
    ) else (
        echo Activating newly created virtual environment %VENV_DIR_TO_USE% for setup...
        call "%VENV_DIR_TO_USE%\Scripts\activate.bat"
        if errorlevel 1 (
            echo ERROR: Failed to activate newly created virtual environment %VENV_DIR_TO_USE%.
            exit /B
        )
    )

    REM Upgrade pip
    echo Upgrading pip...
    %PYTHON_CMD% -m pip install --upgrade pip
    if errorlevel 1 (
        echo ERROR: Failed to upgrade pip in %VENV_DIR_TO_USE%.
        exit /B
    )
    echo pip upgraded successfully.

    REM Install required packages
    if not exist "%SCRIPT_DIR%requirements.txt" (
        echo ERROR: requirements.txt not found in %SCRIPT_DIR%. Cannot install packages.
        exit /B
    )
    echo Installing required Python packages from requirements.txt into %VENV_DIR_TO_USE%...
    %PYTHON_CMD% -m pip install -r "%SCRIPT_DIR%requirements.txt"
    if errorlevel 1 (
        echo ERROR: Failed to install required packages into %VENV_DIR_TO_USE%.
        exit /B
    )
    echo Python packages installed successfully.

    REM Run pywin32 post-install script
    echo Running pywin32 post-install script for %VENV_DIR_TO_USE%...
    %PYTHON_CMD% "%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py" -install
    if errorlevel 1 (
        echo ERROR: Failed to run pywin32 post-install script for %VENV_DIR_TO_USE%.
        exit /B
    )
    echo pywin32 post-install script completed successfully.
)

REM Activate virtual environment
if defined VIRTUAL_ENV (
    echo Virtual environment %VIRTUAL_ENV% is already active.
) else (
    echo Activating virtual environment: %VENV_DIR_TO_USE%
    call "%VENV_DIR_TO_USE%\Scripts\activate.bat"
    if errorlevel 1 (
        echo ERROR: Failed to activate virtual environment %VENV_DIR_TO_USE%.
        exit /B
    )
)


REM Ensure pywin32 components are registered if pywin32 is installed in the active venv
set "PYWIN32_POSTINSTALL_SCRIPT=%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py"
if exist "%PYWIN32_POSTINSTALL_SCRIPT%" (
    echo Ensuring pywin32 components are registered for %VENV_DIR_TO_USE%...
    %PYTHON_CMD% "%PYWIN32_POSTINSTALL_SCRIPT%" -install
    if errorlevel 1 (
        echo ERROR: Failed to run pywin32 post-install script for %VENV_DIR_TO_USE%.
        echo This script is necessary for WMI functionality. Please check permissions or pywin32 installation.
        exit /B
    ) else (
        echo pywin32 post-install script checked/run successfully for %VENV_DIR_TO_USE%.
    )
)

if "%WMI_REQUIRED%"=="1" (
    REM Check and ensure WMI service (winmgmt) is running
    echo Checking WMI Service status...
    sc query winmgmt | find "RUNNING" > nul
    if errorlevel 1 (
        echo WMI Service (winmgmt) is not running. Attempting to start it...
        net start winmgmt 2>>"%SCRIPT_DIR%wmi_service_error.log"
        if errorlevel 1 (
            echo WARNING: Failed to start WMI Service. Features like system monitoring or hardware queries in %PYTHON_SCRIPT_DISPLAY_NAME% may not work. Check "%SCRIPT_DIR%wmi_service_error.log" for details.
        ) else (
            echo WMI Service started successfully.
            echo Waiting for WMI service to initialize...
            set /a "wmi_timeout_count=0"
            :wait_wmi_service
            sc query winmgmt | find "RUNNING" > nul
            if errorlevel 1 (
                if %wmi_timeout_count% GEQ 10 (
                    echo WARNING: WMI Service failed to confirm running state after 10 seconds. Features in %PYTHON_SCRIPT_DISPLAY_NAME% may be affected.
                    goto :continue_after_wmi_wait
                )
                timeout /t 1 /nobreak > nul
                set /a "wmi_timeout_count+=1"
                goto :wait_wmi_service
            )
            echo WMI Service is now running.
            :continue_after_wmi_wait
        )
    ) else (
        echo WMI Service (winmgmt) is running.
    )
) else (
    echo Skipping WMI service check as WMI_REQUIRED is not set to 1.
)

REM Run the Python script
echo Running the Python script: %PYTHON_SCRIPT_DISPLAY_NAME% ^(%PYTHON_SCRIPT_FULL_PATH%^)
REM Clear any previous error log for the Python script
if exist "%SCRIPT_DIR%python_error.log" del "%SCRIPT_DIR%python_error.log"
%PYTHON_CMD% "%PYTHON_SCRIPT_FULL_PATH%" 2>>"%SCRIPT_DIR%python_error.log"

if errorlevel 1 (
    echo ERROR: Python script %PYTHON_SCRIPT_DISPLAY_NAME% execution failed.
    if exist "%SCRIPT_DIR%python_error.log" (
        echo See "%SCRIPT_DIR%python_error.log" for details.
    )
    exit /B
)

echo Script completed successfully.
exit
