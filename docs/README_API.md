# yt-dlp API and Channel Downloader

Complete solution for YouTube channel downloading with parallel processing, audio conversion, and transcript extraction.

## Files Structure

- **`yt_dlp_api.py`** - Memory-based API server (core backend)
- **`yt_dlp_channel_downloader.py`** - Complete channel downloader (main client)
- **`requirements.txt`** - All dependencies
- **`README_API.md`** - This documentation

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the API server:**
```bash
python yt_dlp_api.py
```

3. **Download a channel (interactive mode):**
```bash
python yt_dlp_channel_downloader.py
```

4. **Or use programmatically:**
```python
from yt_dlp_channel_downloader import download_channel_simple

# Audio only (MP3) - fastest
result = download_channel_simple('https://www.youtube.com/@channel/videos')

# With custom options
from yt_dlp_channel_downloader import ChannelDownloader, create_audio_config

config = create_audio_config(max_videos=100, workers=6)
downloader = ChannelDownloader(config)
result = downloader.download_channel('https://www.youtube.com/@channel/videos')
```

## Features

### ✅ Audio Conversion (MP4 to MP3)
- **Formats:** MP3, AAC, WAV, OGG, FLAC, M4A, OPUS
- **Quality:** VBR (0-10) or specific bitrate (128K, 192K, 320K)
- **Smart format selection** for best audio quality

### ✅ Transcript Extraction  
- **Manual subtitles** in multiple languages
- **Auto-generated captions** when available
- **Multiple formats:** SRT, VTT, ASS, TTML, JSON3
- **Concurrent download** with videos

### ✅ Channel Downloads
- **Complete channel support** (@channelname, /channel/, /c/, /user/)
- **Playlist processing** with range selection
- **Batch processing** for efficiency
- **Smart folder organization** by channel name

### ✅ Performance Features
- **Parallel downloads** (4-8x faster than sequential)
- **Memory management** with automatic cleanup
- **Rate limiting** to avoid API blocks
- **Retry logic** with exponential backoff
- **Progress tracking** and detailed logging

## Configuration Options

### Pre-configured Setups

```python
# Audio downloads - optimized for speed
config = create_audio_config(max_videos=50, workers=6)

# Video downloads - balanced quality/speed  
config = create_video_config(max_videos=30, workers=3)

# Audio + Transcripts - comprehensive
config = create_transcript_config(max_videos=100, workers=4)
```

### Custom Configuration

```python
from yt_dlp_channel_downloader import DownloadConfig

config = DownloadConfig(
    # Performance
    max_workers=6,              # Parallel downloads
    batch_size=15,              # Videos per batch
    max_videos=100,             # Channel limit
    max_memory_percent=70.0,    # Memory usage limit
    
    # Download Settings  
    audio_only=True,            # MP3 conversion
    audio_format='mp3',         # Output format
    audio_quality='192K',       # Bitrate or VBR 0-10
    format_selector='ba/b',     # Quality selector
    
    # Subtitles
    download_subtitles=True,    # Enable transcripts
    auto_subtitles=True,        # Auto-generated captions
    subtitle_languages=['en'],  # Language preferences
    
    # Output
    output_dir='./downloads',   # Base directory
    create_channel_folder=True, # Organize by channel
    skip_existing=True,         # Resume downloads
    
    # Advanced
    use_async=False,           # Async vs threaded
    retry_attempts=3,          # Error resilience
    rate_limit_delay=1.0       # API throttling
)
```

## API Endpoints

The memory-based API server provides:

### 1. Download Endpoint
```http
POST /download
Content-Type: application/json

{
    "url": "https://youtube.com/watch?v=...",
    "options": {
        "extractaudio": true,
        "audioformat": "mp3", 
        "audioquality": "192K"
  }
}
```

### 2. Channel Listing
```http  
POST /channel
Content-Type: application/json

{
    "url": "https://www.youtube.com/@channel/videos",
  "options": {
        "extract_flat": true,
        "playlist_items": "1-50"
  }
}
```

### 3. Transcript Extraction
```http
POST /subtitles
Content-Type: application/json

{
    "url": "https://youtube.com/watch?v=...",
    "options": {
        "writeautomaticsub": true,
        "allsubtitles": true,
        "subtitleslangs": ["en"]
  }
}
```

## Complete Parameter Reference

### Audio Conversion
```python
{
    'extractaudio': True,           # Enable audio extraction
    'audioformat': 'mp3',           # mp3, aac, wav, ogg, flac, m4a
    'audioquality': '192K',         # Bitrate (128K, 192K, 320K) or VBR (0-10)
    'format': 'ba[acodec^=mp3]/ba/b'  # Best audio format
}
```

### Video Quality
```python
{
    'format': 'best[height<=720][filesize<200M]',  # Quality limits
    'height': 720,                  # Max resolution
    'fps': 30,                      # Frame rate limit
    'filesize_max': '200M',         # Size limit
    'vcodec': 'h264',              # Video codec preference
}
```

### Subtitles/Transcripts
```python
{
    'writesubtitles': True,         # Manual subtitles
    'writeautomaticsub': True,      # Auto-generated captions
    'allsubtitles': True,           # All available languages
    'subtitleslangs': ['en', 'es'], # Specific languages
    'subtitlesformat': 'srt',       # srt, vtt, ass, ttml, json3
}
```

### Playlists/Channels
```python
{
    'extract_flat': True,           # List videos only
    'playlist_items': '1-50',       # Range selection
    'playliststart': 1,             # Start position
    'playlistend': 50,              # End position
    'playlistreverse': False,       # Reverse order
    'playlistrandom': False,        # Random order
}
```

### Advanced Options
```python
{
    'geo_bypass': True,             # Bypass geo-restrictions
    'proxy': 'http://proxy:8080',   # Proxy server
    'cookiefile': 'cookies.txt',    # Authentication cookies
    'user_agent': 'Custom UA',      # Custom user agent
    'sleep_interval': 1,            # Rate limiting
    'max_sleep_interval': 5,        # Random delay range
}
```

## Performance Comparison

| Method | Speed | Memory | Best For |
|--------|-------|---------|----------|
| Sequential | 1x | Low | Small downloads |
| Threaded (4 workers) | 4-6x | Medium | Balanced performance |
| Async (8 concurrent) | 6-10x | Low | Large batches |
| Hybrid approach | 8-12x | Medium | Production use |

## Error Handling

The downloader includes comprehensive error handling:

- **Network issues:** Automatic retry with exponential backoff
- **Memory limits:** Automatic cleanup and batch pausing
- **Rate limiting:** Smart delays between requests
- **File conflicts:** Skip existing files or overwrite
- **API errors:** Detailed logging and graceful degradation

## Output Organization

```
downloads/
├── ChannelName1/
│   ├── channel_info.json
│   ├── Video1.mp3
│   ├── Video1_transcripts.json
│   ├── Video2.mp3
│   └── Video2_transcripts.json
└── ChannelName2/
    └── ...
```

## Limitations & Solutions

### Memory Usage
- **Issue:** Videos stored in RAM during processing
- **Solution:** Batch processing with memory monitoring
- **Mitigation:** Configure `max_memory_percent` and `batch_size`

### Rate Limiting  
- **Issue:** YouTube API limits
- **Solution:** Built-in delays and retry logic
- **Mitigation:** Adjust `rate_limit_delay` and `batch_pause`

### Large Channels
- **Issue:** Thousands of videos
- **Solution:** Process in batches with progress tracking
- **Mitigation:** Set `max_videos` limit and use resume functionality

## Examples

### Basic Usage
```python
# Simple audio download
result = download_channel_simple('https://www.youtube.com/@channel/videos', as_audio=True)

# Video download  
result = download_channel_simple('https://www.youtube.com/@channel/videos', as_audio=False)
```

### Advanced Usage
```python
from yt_dlp_channel_downloader import ChannelDownloader, DownloadConfig

# Custom configuration
config = DownloadConfig(
    max_workers=8,
    batch_size=20,
    max_videos=200,
    audio_only=True,
    audio_format='mp3',
    audio_quality='320K',
    download_subtitles=True,
    rate_limit_delay=0.5
)

downloader = ChannelDownloader(config)

# Progress callback
def show_progress(current, total, result):
    print(f"[{current}/{total}] {'✅' if result.success else '❌'} {result.title}")

# Download with progress tracking
result = downloader.download_channel(
    'https://www.youtube.com/@channel/videos',
    progress_callback=show_progress
)

print(f"Downloaded {result['downloaded']}/{result['total_videos']} videos")
print(f"Total size: {result['total_size_mb']:.1f} MB")
print(f"Saved to: {result['output_directory']}")
```

### Batch Processing Multiple Channels
```python
channels = [
    'https://www.youtube.com/@python/videos',
    'https://www.youtube.com/@django/videos', 
    'https://www.youtube.com/@flask/videos'
]

config = create_audio_config(max_videos=50, workers=4)
downloader = ChannelDownloader(config)

for channel_url in channels:
    print(f"\n🎯 Processing: {channel_url}")
    result = downloader.download_channel(channel_url)
    print(f"✅ Completed: {result['downloaded']} videos")
```

## Troubleshooting

### Common Issues

1. **API Connection Error:**
   ```bash
   # Start the API server first
   python yt_dlp_api.py
   ```

2. **Memory Usage Too High:**
   ```python
   config.max_memory_percent = 50.0  # Lower limit
   config.batch_size = 5            # Smaller batches
   ```

3. **Rate Limited:**
   ```python
   config.rate_limit_delay = 2.0    # Slower requests
   config.max_workers = 2           # Less parallel
   ```

4. **Failed Downloads:**
   ```python
   config.retry_attempts = 5        # More retries
   config.retry_delay = 3.0         # Longer delays
   ```

### Logging

Check `downloader.log` for detailed execution logs:
```bash
tail -f downloader.log
```

## Integration Examples

The channel downloader can be integrated into larger applications:

```python
# Web service integration
from flask import Flask, jsonify, request
from yt_dlp_channel_downloader import ChannelDownloader, create_audio_config

app = Flask(__name__)

@app.route('/download_channel', methods=['POST'])
def download_channel():
    channel_url = request.json['url']
    
    config = create_audio_config(max_videos=50, workers=4)
    downloader = ChannelDownloader(config)
    
    result = downloader.download_channel(channel_url)
    return jsonify(result)

# Scheduled downloads
import schedule
import time

def daily_download():
    channels = ['https://www.youtube.com/@news/videos']
    config = create_audio_config(max_videos=10, workers=2)
    downloader = ChannelDownloader(config)
    
    for channel in channels:
        downloader.download_channel(channel)

schedule.every().day.at("02:00").do(daily_download)

while True:
    schedule.run_pending()
    time.sleep(60)
```

This comprehensive solution provides everything needed for efficient YouTube channel downloading with professional-grade features and error handling. 