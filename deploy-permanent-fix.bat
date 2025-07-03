@echo off
echo 🚀 Deploying Permanent Cookie Fix for yt-dlp API
echo ==================================================

echo [INFO] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running! Please start Docker Desktop.
    pause
    exit /b 1
)
echo [SUCCESS] Docker is running

echo [INFO] Checking cookie setup...
if not exist "yt_dlp\cookies" (
    echo [WARNING] Creating yt_dlp\cookies directory...
    mkdir yt_dlp\cookies
)

echo [INFO] Stopping existing container...
docker-compose down

echo [INFO] Building Docker image with permanent fixes...
docker-compose build --no-cache

echo [INFO] Starting container with permanent fixes...
docker-compose up -d

echo [INFO] Waiting for API to start...
timeout /t 10 /nobreak >nul

echo [INFO] Testing API health...
curl -s --connect-timeout 10 http://localhost:5002/health | findstr "healthy" >nul
if %errorlevel% equ 0 (
    echo [SUCCESS] API is healthy and running!
) else (
    echo [ERROR] API health check failed. Checking logs...
    docker-compose logs --tail=20 yt-dlp-api
    pause
    exit /b 1
)

echo [INFO] Testing cookie functionality...
curl -s http://localhost:5002/cookie-status

echo [INFO] Recent container logs:
docker-compose logs --tail=15 yt-dlp-api

echo.
echo ==================================================
echo [SUCCESS] PERMANENT FIX DEPLOYMENT COMPLETE!
echo ==================================================
echo.
echo 🎯 What's been fixed permanently:
echo ✅ ytc library installed in Docker image
echo ✅ Cookie directories created with proper permissions
echo ✅ Automatic cookie copying on container startup
echo ✅ Enhanced cookie detection and fallback
echo ✅ Initialization script runs on every container start
echo.
echo 🔧 Container startup now automatically:
echo • Sets up /app/YTC-DL and /app/cookies directories
echo • Copies any existing cookies to centralized location
echo • Tests ytc library for automated cookies
echo • Lists available cookie files
echo.
echo 📡 Your API endpoints:
echo • Health: curl http://localhost:5002/health
echo • Cookie Status: curl http://localhost:5002/cookie-status
echo • Download: curl -X POST http://localhost:5002/download -d "{\"url\":\"...\"}"
echo.
echo 🍪 Cookie priority (automatic):
echo 1. ytc automated cookies (refreshed every 6 hours)
echo 2. Manual cookies in /app/YTC-DL/cookies.txt
echo 3. Fallback to cookiesfrombrowser options
echo.
echo [SUCCESS] No more manual cookie setup needed! 🎉
echo [INFO] The fix is now permanent - cookies will work after rebuilds!
echo.
echo [INFO] Deployment complete! Check the logs above for any issues.
pause 