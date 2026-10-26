@echo off
rem Запуск стенда на Windows двойным щелчком: http://localhost:8080
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Порт сайта: 8080 или HTTP_PORT из .env (если 8080 занят — README, «Если что-то не работает»)
set "PORT=8080"
if exist .env for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"HTTP_PORT=" .env') do set "PORT=%%b"

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker не запущен. Запустите Docker Desktop, дождитесь "Engine running" и снова откройте start.cmd.
    pause
    exit /b 1
)

echo Собираю и запускаю стенд. Первый раз это 5-15 минут, дальше меньше минуты.
docker compose up -d --build --wait --wait-timeout 600
if errorlevel 1 (
    echo.
    echo Стенд не поднялся. Состояние сервисов:
    docker compose ps
    echo Логи: docker compose logs --tail=100
    echo Частые причины и что делать: README, раздел "Если что-то не работает".
    pause
    exit /b 1
)

echo.
echo Готово: http://localhost:%PORT%
echo Остановить: docker compose down
start "" http://localhost:%PORT%
pause
