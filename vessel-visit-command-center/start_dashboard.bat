@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_RUN="

rem Prefer the self-contained project environment created for this dashboard.
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_RUN="%~dp0.venv\Scripts\python.exe""
)

rem Prefer the Windows Python launcher when it is installed.
if not defined PYTHON_RUN where py >nul 2>nul
if not defined PYTHON_RUN if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_RUN=py -3.12"
)

rem Try a real python.exe from PATH. This rejects the Microsoft Store alias.
if not defined PYTHON_RUN (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_RUN=python"
)

rem Search common per-user Python installation folders.
if not defined PYTHON_RUN (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
        if exist "%%~fD\python.exe" set "PYTHON_RUN="%%~fD\python.exe""
    )
)

rem Search common system-wide installation folders.
if not defined PYTHON_RUN (
    for /d %%D in ("%ProgramFiles%\Python3*") do (
        if exist "%%~fD\python.exe" set "PYTHON_RUN="%%~fD\python.exe""
    )
)

if not defined PYTHON_RUN goto :python_missing

echo Using Python: %PYTHON_RUN%
%PYTHON_RUN% --version

%PYTHON_RUN% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo Installing pip...
    %PYTHON_RUN% -m ensurepip --upgrade
    if errorlevel 1 goto :setup_failed
)

%PYTHON_RUN% -c "import streamlit, pandas, plotly, openpyxl, requests" >nul 2>nul
if errorlevel 1 (
    echo Installing dashboard requirements. This is required only once...
    %PYTHON_RUN% -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_failed
)

echo.
echo Starting Nevis Vessel Command Center...
echo Open http://localhost:8501 if the browser does not open automatically.
echo Keep this window open while using the dashboard.
echo.
%PYTHON_RUN% -m streamlit run dashboard.py
goto :end

:python_missing
echo.
echo ERROR: A real Python installation was not found.
echo Install Python 3.12 64-bit from:
echo https://www.python.org/downloads/windows/
echo.
echo IMPORTANT: Select "Add python.exe to PATH" during installation.
echo Close this window after installation, then double-click start_dashboard.bat again.
pause
exit /b 1

:setup_failed
echo.
echo ERROR: The Python packages could not be installed.
echo Review the error displayed above.
pause
exit /b 1

:end
endlocal
