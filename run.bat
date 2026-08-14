@echo off
REM ============================================================
REM  Crypto Swing-Trader - launch backend (FastAPI) + frontend (Vite)
REM  Double-click this file, or run it from a terminal.
REM  Requirement: MySQL 8 must already be running (see backend\.env).
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === Crypto Swing-Trader ===
echo.

REM --- 1. Python virtual environment ------------------------------------
if not exist "backend\.venv\Scripts\python.exe" (
    echo [setup] Creating Python virtual environment...
    py -3 -m venv backend\.venv
    if errorlevel 1 (
        echo [ERROR] Could not create venv. Is Python 3.12+ installed and on PATH?
        pause
        exit /b 1
    )
    echo [setup] Installing backend dependencies ^(first run, may take a few minutes^)...
    call "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
    call "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
)

REM --- 2. Backend .env check --------------------------------------------
if not exist "backend\.env" (
    echo [WARN] backend\.env not found.
    echo        Copy backend\.env.example to backend\.env and set DATABASE_URL + API keys.
    echo        The app will still start but the database will be unavailable.
    echo.
)

REM --- 3. Frontend dependencies -----------------------------------------
if not exist "frontend\node_modules" (
    echo [setup] Installing frontend dependencies ^(first run, may take a few minutes^)...
    pushd frontend
    call npm install
    popd
)

REM --- 4. Launch both servers in their own windows ----------------------
echo [run] Starting backend on http://localhost:8000 ...
start "JSE backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo [run] Starting frontend on http://localhost:5173 ...
start "JSE frontend" /D "%~dp0frontend" cmd /k "npm run dev"

REM --- 5. Open the app in the default browser ---------------------------
echo [run] Waiting for servers to start...
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo ------------------------------------------------------------
echo  App:      http://localhost:5173
echo  API docs: http://localhost:8000/docs
echo.
echo  Two windows opened (backend + frontend). Close them to stop.
echo ------------------------------------------------------------
echo.
endlocal
