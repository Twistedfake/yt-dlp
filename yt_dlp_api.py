#!/usr/bin/env python3
"""
yt-dlp HTTP API Server
Provides an HTTP API that returns video content as binary data instead of saving to disk.
"""

import io
import json
import logging
import os
import traceback
from urllib.parse import parse_qs, urlparse

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import BadRequest

from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_filename
from yt_dlp_memory_downloader import MemoryHttpFD


class YtDlpAPI:
    """HTTP API wrapper for yt-dlp that returns binary content"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
    
    def _get_ffmpeg_location(self):
        """Auto-detect ffmpeg location on the system"""
        import os
        import subprocess
        from pathlib import Path
        
        # Try WinGet installation first (has both ffmpeg and ffprobe)
        winget_path = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe')
        if os.path.isfile(winget_path):
            # Also check if ffprobe exists in the same directory
            winget_dir = os.path.dirname(winget_path)
            ffprobe_path = os.path.join(winget_dir, 'ffprobe.exe')
            if os.path.isfile(ffprobe_path):
                return winget_path
        
        # Try imageio-ffmpeg as fallback (only has ffmpeg)
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            if ffmpeg_exe and os.path.isfile(ffmpeg_exe):
                return ffmpeg_exe
        except ImportError:
            pass
        
        # Try common locations for ffmpeg
        possible_locations = [
            # Standard installation paths
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            # Check if it's in PATH
            'ffmpeg',  # This will be checked with 'where' command
        ]
        
        # Check each possible location
        for location in possible_locations:
            if location == 'ffmpeg':
                # Check if ffmpeg is in PATH
                try:
                    subprocess.run(['ffmpeg', '-version'], 
                                 capture_output=True, check=True, timeout=5)
                    return 'ffmpeg'  # Available in PATH
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            else:
                if os.path.isfile(location):
                    return location
        
        return None
        
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/', methods=['GET'])
        def index():
            return jsonify({
                'service': 'yt-dlp HTTP API',
                'version': '1.0.0',
                'endpoints': {
                    '/download': 'POST - Download video and return as binary',
                    '/info': 'POST - Get video info without downloading',
                    '/subtitles': 'POST - Extract subtitles/transcripts',
                    '/channel': 'POST - Get channel/playlist video list'
                }
            })
        
        @self.app.route('/info', methods=['POST'])
        def get_info():
            """Get video information without downloading"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')
                
                url = data['url']
                opts = data.get('options', {})
                
                # Configure yt-dlp for info extraction only
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'simulate': True,  # Don't download
                    
                    # ── ANTI-BOT MEASURES FOR YOUTUBE ──
                    # Use browser cookies to avoid bot detection
                    'cookiesfrombrowser': opts.get('cookiesfrombrowser', ('chrome', None, None, None)),
                    # Browser-like headers
                    'user_agent': opts.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
                    'referer': opts.get('referer', 'https://www.youtube.com/'),
                    # Additional headers to appear more browser-like
                    'http_headers': {
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                    },
                    # Rate limiting to avoid detection
                    'sleep_interval': opts.get('sleep_interval', 1),
                    'max_sleep_interval': opts.get('max_sleep_interval', 3),
                    # Cookie file support as fallback
                    'cookiefile': opts.get('cookiefile', None),
                    
                    **opts
                }
                
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                return jsonify({
                    'success': True,
                    'info': {
                        'title': info.get('title'),
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader'),
                        'view_count': info.get('view_count'),
                        'formats': [
                            {
                                'format_id': f.get('format_id'),
                                'ext': f.get('ext'),
                                'resolution': f.get('resolution'),
                                'filesize': f.get('filesize'),
                                'tbr': f.get('tbr'),
                            }
                            for f in info.get('formats', [])
                        ]
                    }
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500
        
        @self.app.route('/download', methods=['POST'])
        def download_video():
            """Download video and return as binary stream"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')
                
                url = data['url']
                opts = data.get('options', {})
                format_selector = data.get('format', None)
                
                # Check if audio extraction is requested
                extract_audio = opts.get('extractaudio', False)
                audio_format = opts.get('audioformat', 'mp3')
                
                # Check if subtitles are requested
                write_subs = opts.get('writesubtitles', False)
                write_auto_subs = opts.get('writeautomaticsub', False)
                
                # Auto-detect ffmpeg location
                ffmpeg_location = self._get_ffmpeg_location()
                
                # Configure yt-dlp to use our memory downloader
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    
                    # ── ANTI-BOT MEASURES FOR YOUTUBE ──
                    # Use browser cookies to avoid bot detection
                    'cookiesfrombrowser': opts.get('cookiesfrombrowser', ('chrome', None, None, None)),
                    # Browser-like headers
                    'user_agent': opts.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
                    'referer': opts.get('referer', 'https://www.youtube.com/'),
                    # Additional headers to appear more browser-like
                    'http_headers': {
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                    },
                    # Rate limiting to avoid detection
                    'sleep_interval': opts.get('sleep_interval', 1),
                    'max_sleep_interval': opts.get('max_sleep_interval', 3),
                    # Cookie file support as fallback
                    'cookiefile': opts.get('cookiefile', None),
                    
                    # Disable all file writing to disk - we only want in-memory downloads
                    'writesubtitles': False,  # write_subs,
                    'writeautomaticsub': False,  # write_auto_subs,
                    # All other file writing options disabled for memory-only operation
                    'writethumbnail': False,  # opts.get('writethumbnail', False),
                    'write_all_thumbnails': False,  # opts.get('write_all_thumbnails', False),
                    'writeinfojson': False,  # opts.get('writeinfojson', False),
                    'writedescription': False,  # opts.get('writedescription', False),
                    'writeannotations': False,  # opts.get('writeannotations', False),
                    'writelink': False,  # opts.get('writelink', False),
                    'writeurllink': False,  # opts.get('writeurllink', False),
                    'writewebloclink': False,  # opts.get('writewebloclink', False),
                    'writedesktoplink': False,  # opts.get('writedesktoplink', False),
                    # Don't use post-processors for memory downloads - they require disk files
                    'postprocessors': [],
                    **opts
                }
                
                # Handle format selection for audio extraction (without post-processing)
                if format_selector:
                    # If user specified a format, use it
                    ydl_opts['format'] = format_selector
                elif extract_audio:
                    # For audio extraction, select best audio format directly (no post-processing)
                    # This gets the best audio stream without needing FFmpeg conversion
                    ydl_opts['format'] = 'bestaudio/best'
                else:
                    # Default format selection - let yt-dlp handle it automatically
                    ydl_opts['format'] = 'best'
                
                # Set ffmpeg location if found (even though we won't use post-processors)
                if ffmpeg_location:
                    if ffmpeg_location != 'ffmpeg':  # If it's a specific path
                        # Also set ffprobe location (usually in same directory)
                        ffmpeg_dir = os.path.dirname(ffmpeg_location)
                        ffprobe_location = os.path.join(ffmpeg_dir, 'ffprobe.exe')
                        if os.path.isfile(ffprobe_location):
                            ydl_opts['ffmpeg_location'] = ffmpeg_dir
                        else:
                            ydl_opts['ffmpeg_location'] = ffmpeg_location
                    else:
                        ydl_opts['ffmpeg_location'] = ffmpeg_location
                
                # Note: We deliberately don't add FFmpegExtractAudioPP post-processor
                # because it requires files on disk, but we're downloading to memory
                
                # Custom YDL class that uses our memory downloader
                class MemoryYDL(YoutubeDL):
                    def __init__(self, params=None):
                        super().__init__(params)
                        self.memory_downloader = None
                        
                    def dl(self, name, info, subtitle=False, test=False):
                        """Override dl method to use memory downloader"""
                        if not info.get('url'):
                            self.raise_no_formats(info, True)

                        # Create our memory downloader
                        self.memory_downloader = MemoryHttpFD(self, self.params)
                        
                        # Add progress hooks
                        for ph in self._progress_hooks:
                            self.memory_downloader.add_progress_hook(ph)
                        
                        # Download to memory
                        success, real_download = self.memory_downloader.download(name, info, subtitle)
                        return success, real_download
                
                # Extract info and download
                with MemoryYDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    if not ydl.memory_downloader:
                        raise Exception("No data downloaded")
                    
                    # Get the downloaded data
                    video_data = ydl.memory_downloader.get_downloaded_data()
                    
                    if not video_data:
                        raise Exception("No video data received")
                    
                    # Determine content type and extension based on the actual format downloaded
                    ext = info.get('ext', 'mp4')
                    
                    # For audio extraction, we rely on yt-dlp's format selection to give us audio
                    # The extension should reflect what we actually got
                    if extract_audio:
                        # Map common audio formats to proper extensions and MIME types
                        audio_ext_map = {
                            'm4a': 'audio/mp4',
                            'mp3': 'audio/mpeg', 
                            'webm': 'audio/webm',
                            'ogg': 'audio/ogg',
                            'opus': 'audio/ogg',
                            'aac': 'audio/aac',
                            'wav': 'audio/wav',
                            'flac': 'audio/flac'
                        }
                        content_type = audio_ext_map.get(ext, 'audio/mpeg')
                    else:
                        # Standard video content types
                        content_type = {
                            'mp4': 'video/mp4',
                            'webm': 'video/webm',
                            'flv': 'video/x-flv',
                            'avi': 'video/x-msvideo',
                            'mov': 'video/quicktime',
                            'mkv': 'video/x-matroska',
                            'm4a': 'audio/mp4',
                            'mp3': 'audio/mpeg',
                            'ogg': 'audio/ogg',
                            'wav': 'audio/wav',
                        }.get(ext, 'application/octet-stream')
                    
                    # Generate filename
                    title = sanitize_filename(info.get('title', 'video'))
                    filename = f"{title}.{ext}"
                    
                    # Return binary data as streaming response
                    def generate():
                        chunk_size = 8192
                        for i in range(0, len(video_data), chunk_size):
                            yield video_data[i:i + chunk_size]
                    
                    # Sanitize headers to avoid Unicode encoding issues
                    safe_title = info.get('title', '').encode('ascii', 'ignore').decode('ascii')
                    safe_filename = filename.encode('ascii', 'ignore').decode('ascii')
                    
                    return Response(
                        generate(),
                        mimetype=content_type,
                        headers={
                            'Content-Disposition': f'attachment; filename="{safe_filename}"',
                            'Content-Length': str(len(video_data)),
                            'X-Video-Title': safe_title,
                            'X-Video-Duration': str(info.get('duration', '')),
                            'X-Video-Format': ext,
                        }
                    )
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500
        
        @self.app.route('/subtitles', methods=['POST'])
        def get_subtitles():
            """Extract subtitles/transcripts from video"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')
                
                url = data['url']
                opts = data.get('options', {})
                
                # Configure yt-dlp for subtitle extraction
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    
                    # ── ANTI-BOT MEASURES FOR YOUTUBE ──
                    # Use browser cookies to avoid bot detection
                    'cookiesfrombrowser': opts.get('cookiesfrombrowser', ('chrome', None, None, None)),
                    # Browser-like headers
                    'user_agent': opts.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
                    'referer': opts.get('referer', 'https://www.youtube.com/'),
                    # Additional headers to appear more browser-like
                    'http_headers': {
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                    },
                    # Rate limiting to avoid detection
                    'sleep_interval': opts.get('sleep_interval', 1),
                    'max_sleep_interval': opts.get('max_sleep_interval', 3),
                    # Cookie file support as fallback
                    'cookiefile': opts.get('cookiefile', None),
                    
                    # Disable subtitle writing to disk - we only extract subtitle info
                    'writesubtitles': False,  # True,
                    'writeautomaticsub': False,  # True,
                    'allsubtitles': True,
                    'skip_download': True,  # Don't download video
                    **opts
                }
                
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    return jsonify({
                        'success': True,
                        'subtitles': info.get('subtitles', {}),
                        'automatic_captions': info.get('automatic_captions', {}),
                        'info': {
                            'title': info.get('title'),
                            'duration': info.get('duration'),
                            'uploader': info.get('uploader'),
                        }
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500
        
        @self.app.route('/channel', methods=['POST'])
        def get_channel():
            """Get list of videos from channel or playlist"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')
                
                url = data['url']
                opts = data.get('options', {})
                
                # Configure yt-dlp for playlist/channel extraction
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    
                    # ── ANTI-BOT MEASURES FOR YOUTUBE ──
                    # Use browser cookies to avoid bot detection
                    'cookiesfrombrowser': opts.get('cookiesfrombrowser', ('chrome', None, None, None)),
                    # Browser-like headers
                    'user_agent': opts.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
                    'referer': opts.get('referer', 'https://www.youtube.com/'),
                    # Additional headers to appear more browser-like
                    'http_headers': {
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                    },
                    # Rate limiting to avoid detection
                    'sleep_interval': opts.get('sleep_interval', 1),
                    'max_sleep_interval': opts.get('max_sleep_interval', 3),
                    # Cookie file support as fallback
                    'cookiefile': opts.get('cookiefile', None),
                    
                    'extract_flat': True,  # Only get URLs, don't download
                    **opts
                }
                
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    return jsonify({
                        'success': True,
                        'channel_info': {
                            'title': info.get('title'),
                            'uploader': info.get('uploader'),
                            'description': info.get('description'),
                            'video_count': len(info.get('entries', [])),
                        },
                        'videos': [
                            {
                                'url': entry.get('url'),
                                'title': entry.get('title'),
                                'id': entry.get('id'),
                                'duration': entry.get('duration'),
                                'view_count': entry.get('view_count'),
                            }
                            for entry in info.get('entries', [])
                        ]
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask server"""
        self.app.run(host=host, port=port, debug=debug)


def check_environment():
    """Check if the environment is properly set up"""
    import sys
    import importlib.util
    
    print("🔍 yt-dlp HTTP API Setup Check")
    print("=" * 35)
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Error: Python 3.7 or higher is required")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Check required packages
    required_packages = [
        ('flask', 'Flask'),
        ('werkzeug', 'Werkzeug'), 
        ('requests', 'requests'),
        ('yt_dlp', 'yt-dlp'),
    ]
    
    missing_packages = []
    for package, display_name in required_packages:
        if importlib.util.find_spec(package) is None:
            missing_packages.append(display_name)
        else:
            print(f"✅ {display_name}")
    
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)
    
    # Check required files
    required_files = ['yt_dlp_memory_downloader.py']
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
        else:
            print(f"✅ {file}")
    
    if missing_files:
        print(f"\n❌ Missing files: {', '.join(missing_files)}")
        sys.exit(1)
    
    print("✅ All checks passed!\n")


if __name__ == '__main__':
    import argparse
    import sys
    
    # Check environment first
    check_environment()
    
    parser = argparse.ArgumentParser(description='yt-dlp HTTP API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Create and run API
        api = YtDlpAPI()
        print(f"🚀 Starting yt-dlp HTTP API server on http://{args.host}:{args.port}")
        print("Press Ctrl+C to stop the server")
        print("-" * 50)
        api.run(host=args.host, port=args.port, debug=args.debug)
        
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1) 