@echo off
REM === frellmapi ngrok tunnel ===
REM 1. Download ngrok: https://ngrok.com/download
REM 2. Run: ngrok config add-authtoken YOUR_TOKEN
REM 3. Run this script to expose frellmapi

echo Starting ngrok tunnel for frellmapi (port 3001)...
echo.
echo After starting, copy the https:// URL to Render env vars:
echo   FRELLMAPI_URL=https://xxxx.ngrok-free.app/v1
echo   FRELLMAPI_KEY=frellmapi-a4fc69d7fa5ca8504930131b70d7b0cfdf6d0b09abe941ce
echo.
ngrok http 3001
