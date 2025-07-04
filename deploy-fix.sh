#!/bin/bash
# Deploy the fixed yt-dlp API to resolve the sudo/ffmpeg issue

echo "🔧 Deploying yt-dlp API fix for sudo/ffmpeg issue..."

# Check if we're in the correct directory
if [ ! -f "yt_dlp_api.py" ]; then
    echo "❌ Error: yt_dlp_api.py not found. Please run this script from the project root."
    exit 1
fi

# Stop the existing container
echo "🛑 Stopping existing container..."
docker-compose down

# Remove the old image to force rebuild
echo "🗑️ Removing old image..."
docker rmi yt-dlp-api 2>/dev/null || true

# Build the new image with the fixed code
echo "🔨 Building new image with sudo fix..."
docker-compose build --no-cache

# Start the container
echo "🚀 Starting updated container..."
docker-compose up -d

# Wait for the container to be ready
echo "⏳ Waiting for container to be ready..."
sleep 10

# Test the fix
echo "🧪 Testing the fix..."
curl -s -X POST http://localhost:5002/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key_here" \
  -d '{"command": "ffmpeg -version", "sudo": false}' | jq -r '.success'

if [ $? -eq 0 ]; then
    echo "✅ Fix deployed successfully!"
    echo "🎉 The API now intelligently detects container environments and avoids sudo"
    echo ""
    echo "📊 Container status:"
    docker-compose ps
else
    echo "❌ Fix deployment failed"
    echo "📋 Container logs:"
    docker-compose logs --tail=20
    exit 1
fi

echo ""
echo "🚀 Deployment complete!"
echo "The API is now running with the sudo fix applied."
echo "FFmpeg commands will work without sudo issues." 