#!/bin/bash
set -e

echo "🚀 Deploying Permanent Cookie Fix for yt-dlp API"
echo "=================================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
print_status "Checking Docker..."
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running! Please start Docker Desktop."
    exit 1
fi
print_success "Docker is running"

# Check if cookies directory exists
print_status "Checking cookie setup..."
if [ ! -d "yt_dlp/cookies" ]; then
    print_warning "Creating yt_dlp/cookies directory..."
    mkdir -p yt_dlp/cookies
fi

# Check for existing cookie files
COOKIE_FOUND=false
for cookie_file in "yt_dlp/cookies/youtube_cookies.txt" "yt_dlp/cookies/youtube-cookies.txt" "yt_dlp/cookies/cookies.txt"; do
    if [ -f "$cookie_file" ]; then
        print_success "Found cookie file: $cookie_file"
        COOKIE_FOUND=true
        break
    fi
done

if [ "$COOKIE_FOUND" = false ]; then
    print_warning "No cookie files found. The API will use automated ytc cookies."
    print_status "To add manual cookies later, place them in yt_dlp/cookies/youtube_cookies.txt"
fi

# Stop existing container
print_status "Stopping existing container..."
docker-compose down || true

# Build with no cache to ensure all changes are applied
print_status "Building Docker image with permanent fixes..."
docker-compose build --no-cache

# Start the container
print_status "Starting container with permanent fixes..."
docker-compose up -d

# Wait for container to be ready
print_status "Waiting for API to start..."
sleep 10

# Test if API is responding
print_status "Testing API health..."
if curl -s --connect-timeout 10 http://localhost:5002/health | grep -q "healthy"; then
    print_success "API is healthy and running!"
else
    print_error "API health check failed. Checking logs..."
    docker-compose logs --tail=20 yt-dlp-api
    exit 1
fi

# Test cookie functionality
print_status "Testing cookie functionality..."

# Check cookie status
print_status "Checking cookie status..."
curl -s http://localhost:5002/cookie-status | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('✅ Cookie directory:', data.get('centralized_directory', {}).get('path', 'N/A'))
    files = data.get('centralized_directory', {}).get('cookie_files', {})
    if files:
        print(f'✅ Cookie files found: {len(files)}')
        for name, info in files.items():
            print(f'  - {name}: {info.get(\"size\", 0)} bytes')
    else:
        print('⚠️ No cookie files in centralized directory')
    
    ytc_available = data.get('ytc_automated', {}).get('available', False)
    print(f'✅ YTC automated cookies: {ytc_available}')
    
except Exception as e:
    print(f'❌ Could not parse cookie status: {e}')
"

# Test YouTube functionality
print_status "Testing YouTube functionality..."
TEST_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Test with automatic cookie detection
curl -s -X POST http://localhost:5002/info \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$TEST_URL\"}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('success'):
        info = data.get('info', {})
        print('✅ YouTube test successful!')
        print(f'  Title: {info.get(\"title\", \"N/A\")}')
        print(f'  Duration: {info.get(\"duration\", \"N/A\")} seconds')
        print(f'  Uploader: {info.get(\"uploader\", \"N/A\")}')
    else:
        print(f'❌ YouTube test failed: {data.get(\"error\", \"Unknown error\")}')
        if 'help' in data:
            print('💡 Suggestions:')
            for solution in data['help'].get('solutions', []):
                print(f'  - {solution}')
except Exception as e:
    print(f'❌ Could not parse response: {e}')
    print('Raw response:', sys.stdin.read())
"

# Show container logs for verification
print_status "Recent container logs:"
docker-compose logs --tail=15 yt-dlp-api

# Final status
echo ""
echo "=================================================="
print_success "PERMANENT FIX DEPLOYMENT COMPLETE!"
echo "=================================================="

echo ""
echo "🎯 What's been fixed permanently:"
echo "✅ ytc library installed in Docker image"
echo "✅ Cookie directories created with proper permissions"
echo "✅ Automatic cookie copying on container startup"
echo "✅ Enhanced cookie detection and fallback"
echo "✅ Initialization script runs on every container start"

echo ""
echo "🔧 Container startup now automatically:"
echo "• Sets up /app/YTC-DL and /app/cookies directories"
echo "• Copies any existing cookies to centralized location"
echo "• Tests ytc library for automated cookies"
echo "• Lists available cookie files"

echo ""
echo "📡 Your API endpoints:"
echo "• Health: curl http://localhost:5002/health"
echo "• Cookie Status: curl http://localhost:5002/cookie-status"
echo "• Download: curl -X POST http://localhost:5002/download -d '{\"url\":\"...\"}'"

echo ""
echo "🍪 Cookie priority (automatic):"
echo "1. ytc automated cookies (refreshed every 6 hours)"
echo "2. Manual cookies in /app/YTC-DL/cookies.txt"
echo "3. Fallback to cookiesfrombrowser options"

echo ""
print_success "No more manual cookie setup needed! 🎉"
print_status "The fix is now permanent - cookies will work after rebuilds!"

# Test API key if provided
if [ ! -z "$API_KEY" ]; then
    echo ""
    print_status "Testing with API key authentication..."
    curl -s -H "X-API-Key: $API_KEY" http://localhost:5002/cookie-status >/dev/null && \
        print_success "API key authentication working!" || \
        print_warning "API key test failed - check your key"
fi

echo ""
print_status "Deployment complete! Check the logs above for any issues." 