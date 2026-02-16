@echo off
SETLOCAL EnableDelayedExpansion

echo ===================================================
echo 🚀 Kemi AI Studio - Unified Launcher (RTX 5080)
echo ===================================================

:: 1. ComfyUI Path setup
set COMFYUI_PATH=D:\Projects\ComfyUI
set PROJECT_PATH=D:\Projects\AI_Generator

:: 2. Check ComfyUI exists
if not exist "%COMFYUI_PATH%\main.py" (
    echo [ERROR] ComfyUI not found at %COMFYUI_PATH%
    echo Please install ComfyUI first.
    pause
    exit /b
)

:: 3. Kill existing processes if any (optional, to avoid port conflicts)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq ComfyUI-Engine" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Kemi-Studio-UI" 2>nul

:: 4. Start ComfyUI Engine in Background
echo [*] Starting ComfyUI Engine in background...
start "ComfyUI-Engine" /min cmd /c "cd /d %COMFYUI_PATH% && python main.py --listen"

:: Wait for ComfyUI to initialize (usually 10-15 seconds)
echo [*] Waiting for AI Engine to warm up (15s)...
timeout /t 15 /nobreak >nul

:: 5. Start Kemi Studio UI
echo [*] Starting Kemi Studio UI...
echo [*] Opening Dashboard at http://localhost:8000
start http://localhost:8000

echo ===================================================
echo 🔥 System is ready! 
echo Keep this window open to manage the servers.
echo To stop everything, close this window and the 
echo ComfyUI-Engine window in the taskbar.
echo ===================================================

cd /d %PROJECT_PATH%
python app.py

pause
