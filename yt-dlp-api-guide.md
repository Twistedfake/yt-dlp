# yt-dlp API Format Guide

## Quick Reference Table

| **Request Type** | **Endpoint** | **Description** |
|------------------|--------------|-----------------|
| **Video Only** | `/download` with `"bestvideo[height=720][ext=mp4]"` | 720p MP4 video without audio |
| **Audio Only** | `/download` with `"bestaudio[ext=m4a]/bestaudio"` | Best audio in M4A format |
| **Video + Audio** | `/download` with `"bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]/best"` | 720p video with audio combined |
| **Channel Info** | `/channel` with defaults | Get channel info and video metadata (no download) |
| **Channel Download** | `/channel` with `"download": true` | Download multiple videos from channel in single response |
| **URL Transcription** | `/transcribe` with `"model": "base"` | Audio-to-text from URL using OpenAI Whisper |
| **File Upload Transcription** | `/transcribe-file` with file upload | Transcribe uploaded MP4/MP3/audio files |
| **Download + Transcribe** | `/download` with `"transcribe": true` | Download video and get transcription in one request |

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

## Transcription with OpenAI Whisper

The API includes audio transcription capabilities using OpenAI Whisper in multiple ways:

### 📁 Upload File for Transcription

Upload MP4, MP3, or any audio/video file directly:

```bash
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@/path/to/video.mp4" \
  -F "model=base" \
  -F "format=json"
```

### 🎬 Download + Transcribe in One Request

Download a video and get its transcription:

```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "transcribe": true,
    "transcribe_model": "base",
    "transcribe_format": "json"
  }'
```

### 🔗 URL-Only Transcription

Transcribe from URL without downloading:

### 🎤 Basic Transcription (JSON)
```bash
curl -X POST http://localhost:5002/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "model": "base",
    "language": "en"
  }'
```

### 📝 Transcription as Text File
```bash
curl -X POST http://localhost:5002/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "text",
    "model": "base"
  }' \
  -o transcript.txt
```

### 🎬 Transcription as SRT Subtitles
```bash
curl -X POST http://localhost:5002/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "srt",
    "model": "small"
  }' \
  -o subtitles.srt
```

### Whisper Model Options

| **Model** | **Size** | **Speed** | **Accuracy** | **Use Case** |
|-----------|----------|-----------|--------------|--------------|
| `tiny` | ~39 MB | Fastest | Basic | Quick transcripts |
| `base` | ~74 MB | Fast | Good | General use |
| `small` | ~244 MB | Medium | Better | Balanced quality |
| `medium` | ~769 MB | Slow | High | High accuracy |
| `large` | ~1550 MB | Slowest | Highest | Best quality |

### Transcription Formats

| **Format** | **Output** | **Description** |
|------------|------------|-----------------|
| `json` | JSON response | Full transcript with segments and timing |
| `text` | Plain text | Simple text file |
| `srt` | SRT subtitles | Standard subtitle format |
| `vtt` | WebVTT | Web video text tracks |
| `both` | JSON with video + transcript | Video data (base64) + transcription |

### 📤 File Upload Examples

**Upload MP4 file:**
```bash
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@video.mp4" \
  -F "model=small" \
  -F "format=srt" \
  -o subtitles.srt
```

**Upload MP3 audio:**
```bash
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@audio.mp3" \
  -F "model=base" \
  -F "language=en" \
  -F "format=text" \
  -o transcript.txt
```

### 🎯 Download + Transcribe Examples

**Get video file + transcript JSON:**
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestvideo[height=720]+bestaudio",
    "transcribe": true,
    "transcribe_format": "both"
  }'
```

**Download audio and get SRT subtitles:**
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestaudio",
    "transcribe": true,
    "transcribe_model": "small",
    "transcribe_format": "srt"
  }' \
  -o video_subtitles.srt
```

## Channel Info & Downloads

### **Updated `/channel` Endpoint:**
- ✅ **Default Behavior**: Returns channel info and video metadata (no download)
- ✅ **Native yt-dlp Integration**: Uses built-in tab handling (no manual URL parsing)
- ✅ **Single HTTP Response**: All videos returned in one request when `download=true`
- ✅ **Video Type Filtering**: Choose regular videos, shorts, streams, or all

### **Parameters:**
- `url` (required): Channel URL
- `max_videos` (optional): Number of videos (default: 10)
- `video_types` (optional): Array of `["regular", "shorts", "streams", "all"]` (default: `["regular"]`)
- `download` (optional): Boolean to download videos as base64 data (default: false)
- `transcribe` (optional): Boolean to transcribe videos (default: false)
- `transcribe_model` (optional): Whisper model (tiny, base, small, medium, large)
- `transcribe_format` (optional): Format (json, text, srt, vtt)
- `options` (optional): yt-dlp options

### **Get Channel Info Only (Default):**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name"
  }'
```

**Response:**
```json
{
  "success": true,
  "channel_title": "Channel Name",
  "total_videos_found": 100,
  "returned_videos": 10,
  "video_types_filter": ["regular"],
  "videos": [
    {
      "id": "VIDEO_ID",
      "title": "Video Title",
      "url": "https://youtube.com/watch?v=VIDEO_ID",
      "duration": 180,
      "view_count": 1000
    }
  ]
}
```

### **Download 5 Videos with Transcription:**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name",
    "max_videos": 5,
    "video_types": ["regular", "shorts"],
    "download": true,
    "transcribe": true,
    "transcribe_model": "base",
    "transcribe_format": "json"
  }'
```

**Response:**
```json
{
  "success": true,
  "channel_title": "Channel Name",
  "videos": [
    {
      "id": "VIDEO_ID",
      "title": "Video Title",
      "file_size": 1024000,
      "video_data": "base64_encoded_video_data",
      "transcription": {
        "text": "Transcribed text here...",
        "language": "en",
        "segments": [...]
      }
    }
  ],
  "transcriptions": [
    {
      "video_title": "Video Title",
      "transcription": {...}
    }
  ]
}
```

### **Get Only Shorts Info:**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name",
    "max_videos": 20,
    "video_types": ["shorts"]
  }'
```

## Data Storage & Response Format

### **How It Works:**
- **Single HTTP Response**: All videos returned in one JSON response when `download=true`
- **Base64 Video Data**: Videos encoded as base64 strings for JSON compatibility
- **Memory Only**: No files saved to disk, everything processed in memory
- **Temporary Files**: Auto-deleted after transcription

### **Response Size Considerations:**
- **Small Videos** (≤50MB each): 5-10 videos per request recommended
- **Large Videos** (>50MB each): 2-3 videos per request recommended
- **Audio Only**: Can handle more videos due to smaller file sizes
- **With Transcription**: Adds minimal data (~1KB per video)

### **Example: 5 Videos with Transcription:**
```json
{
  "url": "https://youtube.com/@channel_name", 
  "max_videos": 5,
  "download": true,
  "transcribe": true,
  "transcribe_model": "tiny",
  "format": "bestaudio[filesize<30M]"
}
```

**Response Structure:**
```json
{
  "success": true,
  "channel_title": "Channel Name",
  "videos": [
    {
      "id": "abc123",
      "title": "Video 1",
      "file_size": 25600000,
      "video_data": "base64EncodedVideoData...",
      "transcription": {"text": "Full transcript...", "segments": [...]}
    }
  ],
  "transcriptions": [...]
}
```

## Technical Details

### File Format Support
- **Audio**: MP3, M4A, WAV, FLAC, OGG, AAC, OPUS
- **Video**: MP4, WEBM, AVI, MOV, MKV, FLV
- **Any format supported by FFmpeg** (Whisper uses FFmpeg internally)

### Memory Management
- Temporary files automatically cleaned up
- Efficient streaming for large files
- Memory-optimized downloading

### Error Handling
- Graceful fallbacks for missing Whisper installation
- Detailed error messages for debugging
- Timeout handling for large files

### Security
- Same authentication as existing API endpoints
- File upload size limits (configurable)
- Temporary file cleanup for security

## Channel Download Recommendations & Limits

### Response Size Limitations
- **JSON Response Size**: Larger responses take longer to process and transfer
- **Memory Usage**: All videos held in memory until response sent
- **Base64 Encoding**: Increases data size by ~33% over binary
- **Network Transfer**: Large responses may timeout on slow connections

### Recommended Limits by Video Type

| **Content Type** | **Max Videos** | **Reason** |
|------------------|----------------|------------|
| **Audio Only** | 10-15 videos | Smaller file sizes, manageable response |
| **Video (720p)** | 3-5 videos | Larger files, avoid response timeouts |
| **Video (1080p+)** | 2-3 videos | Very large files, memory constraints |
| **With Transcription** | +0 videos | Transcription data is minimal (~1KB each) |

### Example: Optimal Audio Downloads
```json
{
  "url": "https://youtube.com/@channel_name",
  "max_videos": 10,
  "video_types": ["regular"],
  "download": true,
  "format": "bestaudio[filesize<30M]"
}
```

### Example: Conservative Video Downloads
```json
{
  "url": "https://youtube.com/@channel_name", 
  "max_videos": 3,
  "video_types": ["regular"],
  "download": true,
  "transcribe": true,
  "format": "bestvideo[height<=720]+bestaudio"
}
```

### YouTube Rate Limits & Best Practices
- **No Official Limits**: YouTube doesn't publish specific rate limits for yt-dlp
- **Single Request Processing**: All videos downloaded sequentially in one request
- **IP-based Throttling**: YouTube may throttle or block aggressive downloading
- **Best Practices**:
  - Keep `max_videos` ≤ 10 for regular use
  - Use audio-only formats to reduce bandwidth
  - Avoid repeated requests to same channel
  - Use appropriate video type filters

### Error Handling
- **Response Timeouts**: Reduce `max_videos` or use audio-only formats
- **403 Forbidden**: Possible IP block - wait 30-60 minutes
- **Memory Errors**: Reduce `max_videos` or video quality
- **Large Response**: Use `/info` endpoint first to check video count

### Performance Recommendations by Server

| **Server Specs** | **Audio Max** | **Video Max** | **Transcribe** |
|------------------|---------------|---------------|----------------|
| 2GB RAM / 1vCPU | 8 videos | 2 videos | tiny model only |
| 4GB RAM / 1vCPU | 12 videos | 3 videos | base model |
| 8GB RAM / 2vCPU | 15 videos | 5 videos | small model |
| 16GB RAM / 4vCPU | 20 videos | 8 videos | medium model |

### Transcription Considerations
- **Model Selection**: Use `tiny` for speed, `base` for balance, `small`+ for accuracy
- **Memory Impact**: ~200MB RAM per transcription job
- **Processing Time**: 10-60 seconds per video depending on model and length
- **Combined Operations**: Transcription adds minimal response size but processing time

## Performance Notes

### Model Download Times (First Use)
- **tiny**: ~2 seconds
- **base**: ~5 seconds  
- **small**: ~15 seconds
- **medium**: ~45 seconds
- **large**: ~90 seconds

### Processing Speed (After Download)
- **tiny**: ~10x real-time
- **base**: ~5x real-time
- **small**: ~2x real-time
- **medium**: ~1x real-time
- **large**: ~0.5x real-time

*Times vary based on CPU/GPU availability*

## Testing

### Test Scripts
- `test_transcription.py` - Tests URL transcription functionality
- `test_file_upload.py` - Tests file upload transcription
- Both include comprehensive error handling and format testing

### Running Tests
```bash
# Set API key
export API_KEY="your_api_key"

# Test URL transcription
python test_transcription.py

# Test file upload (requires test file)
python test_file_upload.py
```

## Installation

### Local Development
```bash
pip install openai-whisper torch torchaudio
```

### Docker Build
```bash
docker compose build --no-cache
```

### VPS Deployment
- All dependencies included in Docker image
- No additional configuration needed
- Works with existing cookie management system

## API Response

**Download endpoints** return video/audio in the response as binary

**Transcription endpoint** returns JSON or text based on format parameter