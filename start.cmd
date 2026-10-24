@echo off
rem Запуск стенда на Windows двойным щелчком: http://localhost:8080
chcp 65001 >nul
setlocal
cd /d "%~dp0"

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
    pause
    exit /b 1
)

echo.
echo Готово: http://localhost:8080
echo Остановить: docker compose down
start "" http://localhost:8080
pause
