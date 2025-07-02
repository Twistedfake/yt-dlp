#!/bin/bash
set -e

echo "🚀 Deploying yt-dlp API with persistent cookies..."

# Check if cookies file exists
if [ ! -f "yt_dlp/cookies/youtube-cookies.txt" ]; then
    echo "⚠️  Warning: YouTube cookies file not found at yt_dlp/cookies/youtube-cookies.txt"
    echo "   Please export your YouTube cookies first!"
    echo ""
    echo "   How to export cookies:"
    echo "   1. Install browser extension: 'Get cookies.txt LOCALLY'"
    echo "   2. Visit youtube.com while logged in"
    echo "   3. Export cookies and save as yt_dlp/cookies/youtube-cookies.txt"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Stop current container
echo "📱 Stopping current container..."
docker-compose down

# Rebuild and start with new volume mounts
echo "🔧 Rebuilding with persistent cookies..."
docker-compose up -d --build

# Wait for container to be ready
echo "⏳ Waiting for API to start..."
sleep 5

# Check if API is responding
echo "🧪 Testing API..."
if curl -s http://localhost:5002/ | grep -q "yt-dlp HTTP API"; then
    echo "✅ API is running!"
    echo ""
    echo "📋 API Information:"
    curl -s http://localhost:5002/ | python3 -m json.tool | grep -E "(service|version)"
    echo ""
    echo "🍪 Cookies mounted from: yt_dlp/cookies/ → /app/cookies/"
    
    # Check if cookies file is accessible
    if docker exec yt-dlp-api test -f /app/cookies/youtube-cookies.txt; then
        echo "✅ YouTube cookies file found in container!"
        echo ""
        echo "🧪 Test YouTube authentication:"
        echo 'curl -X POST http://localhost:5002/info \'
        echo '  -H "Content-Type: application/json" \'
        echo '  -d '"'"'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "options": {"cookiefile": "/app/cookies/youtube-cookies.txt"}}'"'"''
    else
        echo "⚠️  YouTube cookies file not found in container"
        echo "   Make sure yt_dlp/cookies/youtube-cookies.txt exists on host"
    fi
else
    echo "❌ API failed to start. Check logs:"
    echo "docker-compose logs yt-dlp-api"
fi

echo ""
echo "🎯 Deployment complete!"
echo "📊 Monitor logs: docker-compose logs -f yt-dlp-api" 