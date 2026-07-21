@echo off
chcp 65001 >nul
echo 🚀 스마트 체어 백엔드 서버를 가동합니다...
start "Backend Server" cmd /k "python app.py"

echo ⏳ 서버 안정화를 위해 2초 대기합니다...
timeout /t 2 /nobreak >nul

echo 🔌 아두이노 중계기를 가동합니다...
start "Arduino Bridge" cmd /k "python arduino_bridge.py"