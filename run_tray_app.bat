```batch
@echo off
setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%SCRIPT_DIR%run_tray_app.log"
call :log LOG: Script execution started. Timestamp: %date% %time%

REM --- UAC Self-Elevation ---
REM Check if already elevated using 'openfiles' (requires admin rights)
openfiles > NUL 2>&1
if %errorlevel% NEQ 0 (
    call :log LOG: Insufficient privileges. Attempting UAC elevation.
    powershell -Command "Start-Process -FilePath '%COMSPEC%' -ArgumentList '/c \"%~f0\" %*' -Verb RunAs"
    call :log LOG: Exiting non-elevated instance.
    exit /b
)
call :log LOG: Administrative privileges confirmed.

REM --- Variables ---
cls
call :log LOG: Initializing script variables...
set "VENV_PRIMARY_NAME=.venv"
set "VENV_FALLBACK_NAME=venv"
set "PYTHON_CMD="
set "VENV_DIR_TO_USE="
set "WMI_REQUIRED=1"
set "REQUIREMENTS_FILE=requirements.txt"
set "WMI_TIMEOUT=10"
call :log LOG: VENV_PRIMARY_NAME=%VENV_PRIMARY_NAME%, VENV_FALLBACK_NAME=%VENV_FALLBACK_NAME%
call :log LOG: WMI_REQUIRED=%WMI_REQUIRED%, REQUIREMENTS_FILE=%REQUIREMENTS_FILE%, WMI_TIMEOUT=%WMI_TIMEOUT%

REM Helper function for logging (native batch, no tee dependency)
:log
echo %*
echo %*>>"%LOG_FILE%"
goto :eof

REM Determine the Python script to run and its display name
if "%~1"=="" (
    set "PYTHON_SCRIPT_FULL_PATH=%SCRIPT_DIR%tray_app.py"
    set "PYTHON_SCRIPT_DISPLAY_NAME=tray_app.py"
) else (
    call :log LOG: Python script argument provided: %~1
    set "USER_SUPPLIED_SCRIPT_PATH=%~1"
    REM Check if USER_SUPPLIED_SCRIPT_PATH is absolute (contains colon or starts with \\)
    echo "%USER_SUPPLIED_SCRIPT_PATH%" | findstr /B /C:"[A-Za-z]:" /C:"\\\\" >nul
    if errorlevel 1 (
        call :log LOG: Interpreting Python script path as relative.
        set "PYTHON_SCRIPT_FULL_PATH=%SCRIPT_DIR%%USER_SUPPLIED_SCRIPT_PATH%"
        set "PYTHON_SCRIPT_DISPLAY_NAME=%USER_SUPPLIED_SCRIPT_PATH%"
    ) else (
        call :log LOG: Interpreting Python script path as absolute.
        set "PYTHON_SCRIPT_FULL_PATH=%USER_SUPPLIED_SCRIPT_PATH%"
        for %%f in ("%USER_SUPPLIED_SCRIPT_PATH%") do set "PYTHON_SCRIPT_DISPLAY_NAME=%%~nxf"
    )
)
call :log LOG: PYTHON_SCRIPT_FULL_PATH set to: %PYTHON_SCRIPT_FULL_PATH%
call :log LOG: PYTHON_SCRIPT_DISPLAY_NAME set to: %PYTHON_SCRIPT_DISPLAY_NAME%

REM Verify Python script exists
if not exist "%PYTHON_SCRIPT_FULL_PATH%" (
    call :log ERROR: Python script %PYTHON_SCRIPT_FULL_PATH% does not exist.
    exit
)

REM Add current directory and bin folder to PATH
set "Path=%Path%;%CD%;%CD%\bin;"
if not exist "bin" (
    md bin
    call :log LOG: Created 'bin' directory.
) else (
    call :log LOG: 'bin' directory already exists.
)

REM Check for Python installation
call :log LOG: Searching for Python installation...
where python >nul 2>nul
if errorlevel 1 (
    call :log LOG: 'python' command not found. Checking for 'python3'.
    where python3 >nul 2>nul
    if errorlevel 1 (
        call :log ERROR: Python is not installed or not found in PATH.
        exit
    ) else (
        set "PYTHON_CMD=python3"
        call :log LOG: 'python3' command found.
    )
) else (
    set "PYTHON_CMD=python"
    call :log LOG: 'python' command found.
)
call :log LOG: PYTHON_CMD set to: %PYTHON_CMD%

REM Verify Python version (requires Python 3.6+ for PyQt6)
call :log LOG: Checking Python version...
for /f "tokens=2 delims= " %%v in ('%PYTHON_CMD% --version 2^>nul') do set "PYTHON_VERSION=%%v"
for /f "tokens=1,2 delims=." %%a in ("!PYTHON_VERSION!") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)
if !PY_MAJOR! LSS 3 (
    call :log ERROR: Python version !PYTHON_VERSION! is not supported. Requires Python 3.6 or higher.
    exit
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 6 (
    call :log ERROR: Python version !PYTHON_VERSION! is not supported. Requires Python 3.6 or higher.
    exit
)
call :log LOG: Python version !PYTHON_VERSION! is compatible.

REM Detect or create virtual environment
set "VENV_SETUP_NEEDED=0"
call :log LOG: Detecting or creating virtual environment...
if exist "%VENV_PRIMARY_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
    call :log LOG: Found existing virtual environment: %VENV_DIR_TO_USE%
) else if exist "%VENV_FALLBACK_NAME%\Scripts\activate.bat" (
    set "VENV_DIR_TO_USE=%VENV_FALLBACK_NAME%"
    call :log LOG: Found existing virtual environment: %VENV_DIR_TO_USE%
) else (
    call :log LOG: No virtual environment found. Creating one in "%VENV_PRIMARY_NAME%"...
    %PYTHON_CMD% -m venv "%VENV_PRIMARY_NAME%"
    if errorlevel 1 (
        call :log ERROR: Failed to create virtual environment in %VENV_PRIMARY_NAME%.
        exit
    )
    set "VENV_DIR_TO_USE=%VENV_PRIMARY_NAME%"
    set "VENV_SETUP_NEEDED=1"
    call :log LOG: Virtual environment created in %VENV_DIR_TO_USE%. VENV_SETUP_NEEDED=1.
)

REM Check if a virtual environment is already active
if defined VIRTUAL_ENV (
    call :log LOG: Virtual environment %VIRTUAL_ENV% already active. Skipping activation.
) else (
    call :log LOG: Activating virtual environment: %VENV_DIR_TO_USE%...
    call "%VENV_DIR_TO_USE%\Scripts\activate.bat"
    if errorlevel 1 (
        call :log ERROR: Failed to activate virtual environment %VENV_DIR_TO_USE%.
        exit
    )
    call :log LOG: Virtual environment %VENV_DIR_TO_USE% activated.
)

REM Perform setup for new virtual environment
if "%VENV_SETUP_NEEDED%"=="1" (
    call :log LOG: Performing setup for new virtual environment: %VENV_DIR_TO_USE%
    
    REM Upgrade pip
    call :log LOG: Upgrading pip...
    %PYTHON_CMD% -m pip install --upgrade pip
    if errorlevel 1 (
        call :log ERROR: Failed to upgrade pip in %VENV_DIR_TO_USE%.
        exit
    )
    call :log LOG: pip upgraded successfully.

    REM Install required packages
    if exist "%SCRIPT_DIR%%REQUIREMENTS_FILE%" (
        call :log LOG: Installing packages from %REQUIREMENTS_FILE%...
        %PYTHON_CMD% -m pip install -r "%SCRIPT_DIR%%REQUIREMENTS_FILE%"
        if errorlevel 1 (
            call :log ERROR: Failed to install packages from %REQUIREMENTS_FILE%.
            exit
        )
        call :log LOG: Packages from %REQUIREMENTS_FILE% installed successfully.
    ) else (
        call :log LOG: %REQUIREMENTS_FILE% not found. Installing default packages...
        %PYTHON_CMD% -m pip install PyQt6 pystray pillow keyring PyQt6-WebEngine pyinstaller cryptography WMI pywin32
        if errorlevel 1 (
            call :log ERROR: Failed to install default packages in %VENV_DIR_TO_USE%.
            exit
        )
        call :log LOG: Default packages installed successfully.
    )

    REM Run pywin32 post-install script
    call :log LOG: Running pywin32 post-install script for new virtual environment...
    %PYTHON_CMD% "%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py" -install
    if errorlevel 1 (
        call :log ERROR: Failed to run pywin32 post-install script for %VENV_DIR_TO_USE%.
        exit
    )
    call :log LOG: pywin32 post-install script completed successfully.
)

REM Ensure pywin32 components are registered
set "PYWIN32_POSTINSTALL_SCRIPT=%VENV_DIR_TO_USE%\Lib\site-packages\win32\scripts\pywin32_postinstall.py"
call :log LOG: Checking for pywin32 post-install script at %PYWIN32_POSTINSTALL_SCRIPT%
if exist "%PYWIN32_POSTINSTALL_SCRIPT%" (
    call :log LOG: Ensuring pywin32 components are registered...
    %PYTHON_CMD% "%PYWIN32_POSTINSTALL_SCRIPT%" -install
    if errorlevel 1 (
        call :log ERROR: Failed to run pywin32 post-install script. Required for WMI functionality.
        exit
    )
    call :log LOG: pywin32 components registered successfully.
) else (
    call :log LOG: pywin32 post-install script not found. Skipping registration.
)

REM Check and ensure WMI service (winmgmt) is running if required
if "%WMI_REQUIRED%"=="1" (
    call :log LOG: Checking WMI Service (winmgmt) status...
    sc query winmgmt | find "RUNNING" > nul
    if errorlevel 1 (
        call :log LOG: WMI Service not running. Attempting to start...
        net start winmgmt 2>>"%SCRIPT_DIR%wmi_error.log"
        if errorlevel 1 (
            call :log WARNING: Failed to start WMI Service. Features like system monitoring in %PYTHON_SCRIPT_DISPLAY_NAME% may not work. See wmi_error.log.
        ) else (
            call :log LOG: WMI Service started. Waiting for initialization...
            set /a "timeout_count=0"
            :wait_wmi
            sc query winmgmt | find "RUNNING" > nul
            if errorlevel 1 (
                if !timeout_count! GEQ %WMI_TIMEOUT% (
                    call :log WARNING: WMI Service failed to confirm running after %WMI_TIMEOUT% seconds. Features in %PYTHON_SCRIPT_DISPLAY_NAME% may be affected.
                    goto continue
                )
                timeout /t 1 /nobreak > nul
                set /a "timeout_count+=1"
                goto wait_wmi
            )
            call :log LOG: WMI Service confirmed running.
        )
    ) else (
        call :log LOG: WMI Service (winmgmt) is already running.
    )
) else (
    call :log LOG: Skipping WMI service check as WMI_REQUIRED is not 1.
)
:continue

REM Run the Python script
call :log LOG: Running Python script: %PYTHON_SCRIPT_DISPLAY_NAME% (%PYTHON_SCRIPT_FULL_PATH%)
%PYTHON_CMD% "%PYTHON_SCRIPT_FULL_PATH%" 2>>"%SCRIPT_DIR%python_error_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%.log"
if errorlevel 1 (
    call :log ERROR: Python script %PYTHON_SCRIPT_DISPLAY_NAME% execution failed. See python_error_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%.log for details.
    exit
)
call :log LOG: Python script executed successfully.
call :log LOG: Script completed successfully. Timestamp: %date% %time%
exit
```