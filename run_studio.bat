@echo off
SETLOCAL EnableDelayedExpansion

echo ===================================================
echo  Kemi AI Studio - Unified Launcher (RTX 5080)
echo ===================================================

set COMFYUI_PATH=D:\Projects\ComfyUI
set PROJECT_PATH=D:\Projects\AI_Generator

if not exist "%COMFYUI_PATH%\main.py" (
    echo [ERROR] ComfyUI not found at %COMFYUI_PATH%
    pause
    exit /b
)

netstat -ano | findstr :8188 >nul
if %errorlevel% equ 0 (
    echo [!] ComfyUI is already running on port 8188.
) else (
    echo [*] Starting ComfyUI Engine in background...
    start "ComfyUI-Engine" /min cmd /c "cd /d %COMFYUI_PATH% && python main.py --listen --disable-xformers --lowvram --use-ck-attention"
    echo [*] Waiting for AI Engine to warm up (15s)...
    timeout /t 15 /nobreak >nul
)

netstat -ano | findstr :8000 >nul
if %errorlevel% equ 0 (
    echo [!] Studio UI already running on port 8000.
    start http://localhost:8000
    pause
    goto :eof
)

if exist "%PROJECT_PATH%\.venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment...
    call "%PROJECT_PATH%\.venv\Scripts\activate.bat"
)

echo [*] Starting Kemi Studio UI...
start http://localhost:8000

echo ===================================================
echo  System is ready!
echo  Keep this window open to manage the servers.
echo ===================================================

cd /d %PROJECT_PATH%
python app.py

pause
