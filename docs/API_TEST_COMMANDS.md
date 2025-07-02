# yt-dlp HTTP API - Test Commands

This document contains comprehensive curl test commands for the yt-dlp HTTP API server.

## 🚀 Getting Started

Make sure your API server is running:
```bash
python yt_dlp_api.py
```

The server will be available at: `http://localhost:5002` (updated port)

---

## 🍪 YouTube Bot Detection Bypass

The API now includes **Chrome cookies support** to bypass YouTube's bot detection. All endpoints automatically use Chrome cookies when available.

### Basic Chrome Cookies (Automatic)
The API automatically uses Chrome cookies by default. No special configuration needed!

### Custom Browser Cookies
```bash
# Use Firefox cookies instead
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "cookiesfrombrowser": ["firefox", null, null, null]
    }
  }' \
  --output rick_roll.mp4

# Use Edge cookies
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "cookiesfrombrowser": ["edge", null, null, null]
    }
  }' \
  --output test_edge.mp4
```

### Cookie File Support
```bash
# Use exported cookie file
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "cookiefile": "/path/to/cookies.txt"
    }
  }' \
  --output test_cookies.mp4
```

### Custom User Agent
```bash
# Override user agent
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
  }' \
  --output test_custom_ua.mp4
```

---

## 🌐 Test URL

All examples use this YouTube Shorts URL:
```
https://www.youtube.com/shorts/yFLFkdFvNh0
```

---

## 📋 API Test Commands

### 1. 🔍 **Health Check**
Test if the API server is running:
```bash
curl -X GET http://localhost:5002/
```

**Expected Response:**
```json
{
  "service": "yt-dlp HTTP API",
  "version": "1.0.0",
  "endpoints": {
    "/download": "POST - Download video and return as binary",
    "/info": "POST - Get video info without downloading",
    "/subtitles": "POST - Extract subtitles/transcripts",
    "/channel": "POST - Get channel/playlist video list"
  }
}
```

---

### 2. 📊 **Video Information Extraction**
Get video metadata without downloading:
```bash
curl -X POST http://localhost:5002/info \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0"
  }'
```

---

### 3. 🎵 **Audio Downloads**

#### Basic MP3 Audio Download
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "options": {
      "extractaudio": true,
      "audioformat": "mp3"
    }
  }' \
  --output "audio.mp3"
```

#### High-Quality Audio (192k MP3)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "options": {
      "extractaudio": true,
      "audioformat": "mp3",
      "audioquality": "192"
    }
  }' \
  --output "audio_192k.mp3"
```

#### Best Audio Quality (Original Format)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestaudio"
  }' \
  --output "best_audio.webm"
```

---

### 4. 🎬 **Video Downloads**

#### Best Quality Video
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best"
  }' \
  --output "video_best.mp4"
```

#### 720p Video
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best[height<=720]"
  }' \
  --output "video_720p.mp4"
```

#### 480p Video
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best[height<=480]"
  }' \
  --output "video_480p.mp4"
```

#### Worst Quality (Smallest File)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "worst"
  }' \
  --output "video_worst.mp4"
```

---

### 5. 📝 **Subtitle Downloads**

#### Get Subtitle Information
```bash
curl -X POST http://localhost:5002/subtitles \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0"
  }'
```

#### Download Video with Subtitles
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "options": {
      "writesubtitles": true,
      "writeautomaticsub": true
    }
  }' \
  --output "video_with_subs.mp4"
```

---

### 6. 🎯 **Advanced Format Selection**

#### MP4 Video Only
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best[ext=mp4]"
  }' \
  --output "video.mp4"
```

#### WebM Video Only
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best[ext=webm]"
  }' \
  --output "video.webm"
```

#### Best Video + Best Audio (Separate Streams)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestvideo+bestaudio"
  }' \
  --output "video_combined.mp4"
```

---

### 7. 📱 **Mobile-Optimized Downloads**

#### Low Bandwidth (Mobile-Friendly)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best[filesize<50M][height<=720]"
  }' \
  --output "mobile_video.mp4"
```

#### Audio for Mobile (Low Quality)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "options": {
      "extractaudio": true,
      "audioformat": "mp3",
      "audioquality": "128"
    }
  }' \
  --output "mobile_audio.mp3"
```

---

### 8. 🔧 **Debugging and Testing**

#### Verbose Output (for debugging)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best",
    "options": {
      "verbose": true
    }
  }' \
  --output "debug_video.mp4" \
  -v
```

#### Test with Headers Display
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "best"
  }' \
  --output "test_video.mp4" \
  --dump-header headers.txt
```

---

## 🛡️ Error Handling Tests

### Invalid URL Test
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://invalid-url.com/video"
  }'
```

### Missing URL Test
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## 📊 Response Headers

The API returns useful metadata in response headers:

- `Content-Disposition`: Suggested filename
- `Content-Length`: File size in bytes
- `X-Video-Title`: Video title (ASCII-safe)
- `X-Video-Duration`: Duration in seconds
- `X-Video-Format`: File format/extension

---

## 🎯 PowerShell Equivalents

For Windows PowerShell users:

### Basic Download
```powershell
$body = @{
    url = "https://www.youtube.com/shorts/yFLFkdFvNh0"
    format = "best"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5002/download" `
    -Method Post `
    -Body $body `
    -ContentType "application/json" `
    -OutFile "video.mp4"
```

### Audio Download
```powershell
$body = @{
    url = "https://www.youtube.com/shorts/yFLFkdFvNh0"
    options = @{
        extractaudio = $true
        audioformat = "mp3"
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5002/download" `
    -Method Post `
    -Body $body `
    -ContentType "application/json" `
    -OutFile "audio.mp3"
```

---

## 🚨 Notes

1. **File Formats**: The API returns the original format from yt-dlp without post-processing
2. **Audio Extraction**: Uses format selection (`bestaudio`) rather than FFmpeg conversion
3. **Memory Efficient**: All downloads happen in memory and stream to the client
4. **Headers**: Response includes metadata about the downloaded content
5. **Error Handling**: Failed requests return JSON with error details

---

## 🔗 API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Health check and API info |
| `/info` | POST | Get video metadata |
| `/download` | POST | Download video/audio as binary |
| `/subtitles` | POST | Extract subtitle information |
| `/channel` | POST | Get playlist/channel video list |

---

**Created for yt-dlp HTTP API v1.0.0** 🎉 
