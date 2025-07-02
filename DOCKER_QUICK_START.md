# 🚀 Docker Quick Start Guide

## Prerequisites
- Docker Desktop must be running on Windows

## Step 1: Start Docker Desktop
1. Press `Windows + R`
2. Type `Docker Desktop` and press Enter
3. Wait for Docker Desktop to start (you'll see the Docker icon in system tray)
4. When ready, the Docker Desktop icon will be solid (not spinning)

## Step 2: Verify Docker is Running
```bash
docker --version
docker info
```
Both commands should work without errors.

## Step 3: Build and Run (Choose One)

### Option A: Using Docker Compose (Recommended)
```bash
# Build and start
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Option B: Using Docker Commands
```bash
# Build
docker build -t yt-dlp-api .

# Run
docker run -d --name yt-dlp-api -p 5002:5002 --restart unless-stopped yt-dlp-api

# Check status
docker ps

# View logs
docker logs -f yt-dlp-api

# Stop
docker stop yt-dlp-api && docker rm yt-dlp-api
```

## Step 4: Test the API
```bash
# Health check
curl http://localhost:5002/

# Download test (small video)
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  --output test_video.mp4
```

## 🎯 That's it!
Your yt-dlp API is now running in a Docker container at `http://localhost:5002`

## 🚨 Troubleshooting
- **"Docker Desktop is not running"** → Start Docker Desktop from Windows Start menu
- **Port 5000 in use** → Change port: `docker run -p 5002:5002 yt-dlp-api`
- **Build fails** → Check Docker Desktop is running and try `docker-compose build --no-cache` 