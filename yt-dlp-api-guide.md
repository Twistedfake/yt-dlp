# yt-dlp API Format Guide

## Quick Reference Table

| **Request Type** | **Endpoint** | **Description** |
|------------------|--------------|-----------------|
| **Video Only** | `/download` with `"bestvideo[height=720][ext=mp4]"` | 720p MP4 video without audio |
| **Audio Only** | `/download` with `"bestaudio[ext=m4a]/bestaudio"` | Best audio in M4A format |
| **Video + Audio** | `/download` with `"bestvideo[height=720][ext=mp4]+bestaudio[ext=m4a]/best"` | 720p video with audio combined |
| **Channel Download** | `/channel` → `/job/{job_id}` | Job-based channel downloads with progress tracking |
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

## Job-Based Channel Downloads

### **Problem Solved:**
- ❌ **Old System**: HTTP timeouts on large channels, no progress tracking
- ✅ **New System**: Instant job creation, real-time progress, no timeouts

### **How It Works:**
1. **Start Job**: POST to `/channel` → Get `job_id` immediately
2. **Track Progress**: GET `/job/{job_id}` → See real-time status
3. **Get Results**: GET `/job/{job_id}/results` → All videos and transcriptions
4. **Download Videos**: GET `/job/{job_id}/download/{video_index}` → Individual files

### **Start Channel Download:**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/c/SomeChannel",
    "max_videos": 100,
    "transcribe": true,
    "transcribe_model": "tiny"
  }'
```

**Response (Immediate):**
```json
{
  "success": true,
  "job_id": "12345678-1234-1234-1234-123456789abc",
  "message": "Channel download started",
  "channel_title": "Tech Channel",
  "total_videos": 100,
  "status_url": "/job/12345678-1234-1234-1234-123456789abc",
  "estimated_time": "1000 seconds"
}
```

### **Track Progress:**
```bash
curl -H "X-API-Key: your_api_key" \
  http://localhost:5002/job/12345678-1234-1234-1234-123456789abc
```

**Response (Real-time):**
```json
{
  "id": "12345678-1234-1234-1234-123456789abc",
  "type": "channel",
  "status": "running",
  "total_items": 100,
  "completed_items": 25,
  "failed_items": 2,
  "progress_percent": 25.0,
  "current_item": "Downloading: Introduction to Python...",
  "channel_title": "Tech Channel",
  "transcriptions": [...]
}
```

### **Get All Results:**
```bash
curl -H "X-API-Key: your_api_key" \
  http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/results
```

**Response (When Complete):**
```json
{
  "job_id": "12345678-1234-1234-1234-123456789abc",
  "status": "completed",
  "channel_title": "Tech Channel",
  "total_videos": 100,
  "successful_downloads": 98,
  "failed_downloads": 2,
  "transcriptions_count": 98,
  "total_size_mb": 1250.5,
  "results": [
    {
      "url": "https://youtube.com/watch?v=xyz",
      "title": "Video 1",
      "success": true,
      "file_size": 12345678,
      "download_time": 4.2,
      "format": "m4a",
      "transcription": {...}
    }
  ],
  "transcriptions": [
    {
      "video_title": "Video 1",
      "video_url": "https://youtube.com/watch?v=xyz",
      "transcription": {
        "text": "Full transcript...",
        "language": "en",
        "segments": [...]
      }
    }
  ]
}
```

### **Download Individual Videos:**
```bash
# Download video #0 (first video)
curl -H "X-API-Key: your_api_key" \
  http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/download/0 \
  -o "video_1.m4a"

# Download video #5 (sixth video)
curl -H "X-API-Key: your_api_key" \
  http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/download/5 \
  -o "video_6.m4a"
```

### **Get All Transcriptions:**
```bash
# As JSON
curl -H "X-API-Key: your_api_key" \
  "http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/transcriptions?format=json"

# As combined text file
curl -H "X-API-Key: your_api_key" \
  "http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/transcriptions?format=text" \
  -o "all_transcriptions.txt"

# As SRT subtitles
curl -H "X-API-Key: your_api_key" \
  "http://localhost:5002/job/12345678-1234-1234-1234-123456789abc/transcriptions?format=srt" \
  -o "all_subtitles.srt"
```

## Job Status Values

| **Status** | **Description** |
|------------|-----------------|
| `starting` | Job created, initializing |
| `running` | Actively downloading videos |
| `completed` | All videos processed successfully |
| `failed` | Job encountered fatal error |

## Data Storage & Cleanup

### **Where Everything Goes:**
- **Videos**: Stored in memory only, no disk files
- **Transcriptions**: Stored in job data structure
- **Job Data**: Kept in API memory until restart
- **Temporary Files**: Auto-deleted after transcription

### **Memory Management:**
- **Batch Processing**: 3-5 videos at a time
- **Auto Cleanup**: Garbage collection after each batch
- **Memory Monitoring**: Warnings at 90%+ RAM usage
- **No Disk Storage**: Everything stays in memory

### **100+ Video Example:**
```json
{
  "url": "https://www.youtube.com/c/LargeChannel",
  "max_videos": 100,
  "max_workers": 2,
  "batch_size": 3,
  "delay": 2.0,
  "transcribe": true,
  "transcribe_model": "tiny"
}
```

**Processing Flow:**
1. **Job Created**: Returns `job_id` instantly
2. **Batch 1**: Downloads videos 1-3 → transcribes → cleanup
3. **Batch 2**: Downloads videos 4-6 → transcribes → cleanup
4. **...continues**: Until all 100 videos done
5. **Results Available**: All videos + transcriptions accessible via job endpoints

**No Timeouts**: Job runs in background, check progress anytime!

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

## Channel Download Limitations & YouTube Rate Limits

### VPS Optimization (4GB RAM / 1vCPU)
- **Max Videos**: No hard limit - can download entire channels
- **Max Workers**: 3 parallel downloads (hard limit)
- **Batch Size**: 5 videos per batch (hard limit)
- **Memory Monitoring**: Warning at 90% RAM usage, garbage collection at 95%
- **File Storage**: No files saved to disk - all in memory only
- **Auto Cleanup**: Automatic garbage collection after each batch
- **Rate Limiting**: Minimum 1 second delay between downloads

### What Happens with 100+ Videos?
- **Single Request**: Download all 100 videos in one API call
- **Automatic Batching**: Videos processed in small batches (3-5 at a time)
- **Memory Management**: Garbage collection after each batch + at 95% RAM
- **No Disk Storage**: Videos stay in memory only, no files saved
- **Rate Limiting**: 2+ second delays prevent YouTube throttling
- **Progress Streaming**: Real-time updates show which videos succeed/fail
- **Resilient**: Individual video failures don't stop the entire channel download

### Example: 100 Video Channel Download
```json
{
  "url": "https://www.youtube.com/c/LargeChannel",
  "max_videos": 100,     // No limit - downloads all 100 videos
  "max_workers": 2,      // Conservative for VPS
  "batch_size": 3,       // Small batches for memory management
  "delay": 2.5,          // Avoid rate limits
  "transcribe": false,   // Disable for large batches
  "format": "bestaudio[filesize<30M]"
}
```

**Single Request Downloads Everything:**
- Downloads videos 1-3 (batch 1) → cleanup → pause 3s
- Downloads videos 4-6 (batch 2) → cleanup → pause 3s  
- Downloads videos 7-9 (batch 3) → cleanup → pause 3s
- ... continues until all 100 videos are done
- Final cleanup and summary

### YouTube Rate Limits
- **No Official API Limits**: YouTube doesn't publish specific rate limits for yt-dlp
- **Recommended Delays**: 2-3 seconds between requests to avoid throttling
- **IP-based Throttling**: YouTube may slow down or block aggressive downloading
- **Best Practices**:
  - Use `delay: 2.0` or higher for channels with many videos
  - Limit `max_videos` to 10-15 for large channels
  - Use `max_workers: 1` for sensitive channels
  - Avoid downloading from the same channel repeatedly

### Error Handling
- **429 Too Many Requests**: YouTube is rate limiting - increase delay
- **403 Forbidden**: Possible IP block - wait 30-60 minutes
- **Memory Errors**: Reduce `max_videos`, `max_workers`, or `batch_size`
- **Network Timeouts**: Increase delays, reduce parallel workers

### Performance Recommendations
| **VPS Specs** | **Max Videos** | **Max Workers** | **Batch Size** | **Delay** |
|---------------|----------------|-----------------|----------------|-----------|
| 2GB RAM / 1vCPU | 10 | 1 | 2 | 3.0s |
| 4GB RAM / 1vCPU | 15 | 2 | 3 | 2.0s |
| 8GB RAM / 2vCPU | 25 | 3 | 5 | 1.5s |
| 16GB RAM / 4vCPU | 50 | 5 | 8 | 1.0s |

### Whisper + Channel Downloads
- **Use "tiny" model**: Fastest processing for batch operations
- **Memory Impact**: Each transcription uses ~200MB additional RAM
- **Processing Time**: Add 30-60 seconds per video for transcription
- **Recommendation**: Disable transcription for channels with 15+ videos

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