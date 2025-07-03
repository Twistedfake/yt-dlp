# yt-dlp API Transcription Features

## Overview

Added comprehensive OpenAI Whisper transcription capabilities to the yt-dlp API with three different ways to transcribe audio/video content.

## ✅ What's Been Added

### 1. **File Upload Transcription** - `/transcribe-file`
- Upload MP4, MP3, WAV, or any audio/video file directly
- Whisper supports all formats that FFmpeg supports (including MP4 videos)
- No conversion needed - Whisper handles video files natively
- Form-data upload with multipart/form-data

### 2. **URL Transcription** - `/transcribe` 
- Download and transcribe from any supported URL
- Works with YouTube, Twitter, TikTok, etc.
- Automatic audio extraction from videos

### 3. **Download + Transcribe** - `/download` with `transcribe=true`
- Download video/audio AND get transcription in one request
- Multiple output formats: JSON, text, SRT, VTT, or both video+transcript
- Efficient single-request workflow

## 🎯 Key Features

### Whisper Model Support
- **tiny** (~39 MB) - Fastest, basic accuracy
- **base** (~74 MB) - Good balance (default)
- **small** (~244 MB) - Better accuracy  
- **medium** (~769 MB) - High accuracy
- **large** (~1550 MB) - Best accuracy

### Output Formats
- **JSON** - Full transcript with timing segments
- **Text** - Plain text file
- **SRT** - Standard subtitle format
- **VTT** - Web video text tracks
- **Both** - Video data (base64) + transcription in JSON

### Language Support
- Auto-detection (default)
- Manual language specification (en, es, fr, etc.)
- 90+ languages supported by Whisper

## 🚀 Usage Examples

### File Upload
```bash
# Upload MP4 video file
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@video.mp4" \
  -F "model=base" \
  -F "format=srt" \
  -o subtitles.srt

# Upload MP3 audio file  
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@audio.mp3" \
  -F "model=small" \
  -F "language=en" \
  -F "format=text" \
  -o transcript.txt
```

### URL Transcription
```bash
# Transcribe from YouTube URL
curl -X POST http://localhost:5002/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "model": "base",
    "format": "json"
  }'
```

### Download + Transcribe
```bash
# Download video and get transcription
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "format": "bestaudio",
    "transcribe": true,
    "transcribe_model": "small",
    "transcribe_format": "srt"
  }' \
  -o video_subtitles.srt
```

## 🐳 Docker Compatibility

### Updated Dependencies
- Added `openai-whisper>=20231117`
- Added `torch>=2.0.0` and `torchaudio>=2.0.0`
- Added `git` and `build-essential` to Dockerfile

### VPS Ready
- All features work in Docker containers
- Optimized for VPS deployment
- Automatic model downloading and caching
- Efficient memory management with temporary file cleanup

## 🧪 Testing

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

## 📝 Technical Details

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

## 🔧 Installation

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

## 📊 Performance Notes

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

## 🎉 Summary

The yt-dlp API now provides comprehensive transcription capabilities with:
- ✅ 3 different transcription methods
- ✅ 5 output formats
- ✅ 5 Whisper model sizes
- ✅ 90+ language support
- ✅ Full Docker/VPS compatibility
- ✅ Direct MP4 video support (no conversion needed)
- ✅ Comprehensive error handling and testing 