# yt-dlp API Format Guide

## Quick Reference Table

| **Download Type** | **Format String** | **Description** |
|------------------|-------------------|-----------------|
| **Video Only** | `"bestvideo[height=720][ext=mp4]"` | 720p MP4 video without audio |
| **Audio Only** | `"bestaudio[ext=m4a]/bestaudio"` | Best audio in M4A format |
| **Video + Audio** | `"bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]/best"` | 720p video with audio combined |

## Authentication

All API requests require authentication using the `X-API-Key` header:

```bash
-H "X-API-Key: your_api_key"
```

## Curl Examples

### 🎥 Video + Audio Download
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]/best"
  }'
```

### 🎵 Audio-Only Download
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestaudio[ext=m4a]/bestaudio"
  }'
```

### 📹 Video-Only Download (No Audio)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestvideo[height=720][ext=mp4]"
  }'
```

## Format String Syntax

| **Symbol** | **Meaning** | **Example** |
|------------|-------------|-------------|
| `+` | Combine streams | `bestvideo+bestaudio` (merge video and audio) |
| `/` | Fallback option | `format1/format2` (try format1, if fails use format2) |
| `[...]` | Filter criteria | `[height=720]` (only 720p), `[ext=mp4]` (only MP4) |

## Common Filter Options

| **Filter** | **Description** | **Example** |
|------------|-----------------|-------------|
| `height=720` | Exact resolution | `bestvideo[height=720]` |
| `height>=720` | Minimum resolution | `bestvideo[height>=720]` |
| `ext=mp4` | File format | `bestvideo[ext=mp4]` |
| `abr>=128` | Audio bitrate | `bestaudio[abr>=128]` |

## Audio Conversion to MP3

```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
    "format": "bestaudio",
    "postprocessors": [{
      "key": "FFmpegExtractAudio",
      "preferredcodec": "mp3",
      "preferredquality": "192"
    }]
  }'
```

## Quality Options

| **Quality Level** | **Video Format** | **Audio Format** |
|------------------|------------------|------------------|
| **High Quality** | `bestvideo[height>=1080]` | `bestaudio[abr>=192]` |
| **Medium Quality** | `bestvideo[height>=720]` | `bestaudio[abr>=128]` |
| **Low Quality** | `bestvideo[height>=480]` | `bestaudio[abr>=96]` |

## Advanced Examples

### Download Best Available Quality (Any Format)
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "best"
  }'
```

### Download 4K Video with High-Quality Audio
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestvideo[height>=2160]+bestaudio[abr>=192]/best"
  }'
```

### Download with Multiple Fallback Options
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestvideo[height=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height=720]+bestaudio/best"
  }'
```

## Common Use Cases

### 1. YouTube Shorts (Vertical Videos)
```json
{
  "url": "https://www.youtube.com/shorts/yFLFkdFvNh0",
  "format": "bestvideo[height>=720]+bestaudio/best"
}
```

### 2. Music Videos (Audio Focus)
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "format": "bestaudio[ext=m4a]/bestaudio",
  "postprocessors": [{
    "key": "FFmpegExtractAudio",
    "preferredcodec": "mp3",
    "preferredquality": "320"
  }]
}
```

### 3. Educational Content (Balanced Quality)
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"
}
```

## Error Handling

If a format isn't available, yt-dlp will try the next option after `/`. Always include a fallback:

```json
{
  "format": "preferred_format/fallback_format/best"
}
```

## API Response

The API will return video/audio in the response as binary