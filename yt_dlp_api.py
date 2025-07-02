#!/usr/bin/env python3
"""
yt-dlp HTTP API Server
Provides an HTTP API that returns video content as binary data instead of saving to disk.

COOKIE AUTHENTICATION FOR YOUTUBE:
YouTube increasingly requires authentication to avoid bot detection. Use one of these methods:

METHOD 1 - Browser Cookies (Recommended for local testing):
POST to /download with:
{
    "url": "https://youtube.com/watch?v=VIDEO_ID",
    "options": {
        "cookiesfrombrowser": "chrome"
    }
}

METHOD 2 - Cookie File (Recommended for VPS):
{
    "url": "https://youtube.com/watch?v=VIDEO_ID", 
    "options": {
        "cookiefile": "/path/to/youtube_cookies.txt"
    }
}

TESTING LOCALLY:
python yt_dlp_api_fixed.py --debug
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
        """Auto-detect ffmpeg location on the system (cross-platform)"""
        import os
        import subprocess
        import platform
        from pathlib import Path
        
        is_windows = platform.system() == 'Windows'
        ffmpeg_exe = 'ffmpeg.exe' if is_windows else 'ffmpeg'
        
        # First, try ffmpeg in PATH (works on all platforms)
        try:
            subprocess.run([ffmpeg_exe if is_windows else 'ffmpeg', '-version'], 
                         capture_output=True, check=True, timeout=5)
            return ffmpeg_exe if is_windows else 'ffmpeg'
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Try imageio-ffmpeg as fallback (cross-platform)
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            if ffmpeg_path and os.path.isfile(ffmpeg_path):
                return ffmpeg_path
        except ImportError:
            pass
        
        # Platform-specific locations
        if is_windows:
            possible_locations = [
                # WinGet installation
                os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe'),
                # Standard Windows paths
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            ]
        else:
            # Linux/Unix locations
            possible_locations = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/ffmpeg/bin/ffmpeg',
                '/snap/bin/ffmpeg',  # Snap package
                '/usr/bin/avconv',   # Alternative on some systems
            ]
        
        # Check each possible location
        for location in possible_locations:
            if os.path.isfile(location):
                return location
        
        return None

    def _get_enhanced_ydl_opts(self, opts=None):
        """Get enhanced yt-dlp options with robust anti-bot measures (cross-platform)"""
        import platform
        
        if opts is None:
            opts = {}
        
        # Detect platform for realistic headers
        system = platform.system()
        if system == 'Windows':
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            platform_header = '"Windows"'
        elif system == 'Darwin':  # macOS
            user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            platform_header = '"macOS"'
        else:  # Linux and others
            user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            platform_header = '"Linux"'
            
        # Enhanced anti-bot configuration
        enhanced_opts = {
            'quiet': True,
            'no_warnings': True,
            
            # ── ENHANCED ANTI-BOT MEASURES FOR YOUTUBE ──
            # Cookie authentication (primary defense)
            'cookiefile': opts.get('cookiefile', None),
            
            # More sophisticated browser simulation (platform-aware)
            'user_agent': opts.get('user_agent', user_agent),
            'referer': opts.get('referer', 'https://www.youtube.com/'),
            
            # Comprehensive browser-like headers (platform-aware)
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': platform_header,
                **opts.get('http_headers', {})
            },
            
            # Aggressive rate limiting to avoid detection
            'sleep_interval': opts.get('sleep_interval', 2),  # Increased from 1
            'max_sleep_interval': opts.get('max_sleep_interval', 5),  # Increased from 3
            'sleep_interval_requests': opts.get('sleep_interval_requests', 1),  # New
            
            # YouTube-specific client selection
            'youtube_client': opts.get('youtube_client', 'web'),  # Use web client
            
            # Network configuration
            'socket_timeout': opts.get('socket_timeout', 30),
            'retries': opts.get('retries', 3),
            
            **opts
        }
        
        # Handle cookiesfrombrowser properly - yt-dlp expects just the browser string
        cookiesfrombrowser = opts.get('cookiesfrombrowser')
        if cookiesfrombrowser:
            # Pass the browser name directly as yt-dlp expects
            enhanced_opts['cookiesfrombrowser'] = cookiesfrombrowser.lower()
        
        return enhanced_opts
        
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/', methods=['GET'])
        def index():
            return jsonify({
                'service': 'yt-dlp HTTP API',
                'version': '1.1.0',
                'endpoints': {
                    '/download': 'POST - Download video and return as binary',
                    '/info': 'POST - Get video info without downloading',
                    '/subtitles': 'POST - Extract subtitles/transcripts',
                    '/channel': 'POST - Get channel/playlist video list'
                },
                'cookie_help': {
                    'browser_cookies': 'Use "cookiesfrombrowser":"chrome" in options',
                    'cookie_file': 'Use "cookiefile":"/path/to/cookies.txt" in options',
                    'supported_browsers': ['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave']
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
                
                # Use enhanced options with better anti-bot measures
                ydl_opts = self._get_enhanced_ydl_opts(opts)
                ydl_opts.update({
                    'simulate': True,  # Don't download
                    **opts
                })
                
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                return jsonify({
                    'success': True,
                    'info': {
                        'title': info.get('title'),
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader'),
                        'view_count': info.get('view_count'),
                        'upload_date': info.get('upload_date'),
                        'webpage_url': info.get('webpage_url'),
                        'formats': [
                            {
                                'format_id': f.get('format_id'),
                                'ext': f.get('ext'),
                                'resolution': f.get('resolution'),
                                'filesize': f.get('filesize'),
                                'tbr': f.get('tbr'),
                                'format_note': f.get('format_note'),
                            }
                            for f in info.get('formats', [])
                        ]
                    }
                })
                
            except Exception as e:
                error_msg = str(e)
                
                # Enhanced error reporting for cookie-related issues
                if 'bot' in error_msg.lower() or 'sign in' in error_msg.lower():
                    return jsonify({
                        'success': False,
                        'error': error_msg,
                        'help': {
                            'issue': 'YouTube bot detection - authentication required',
                            'solutions': [
                                'Use browser cookies: {"options": {"cookiesfrombrowser": "chrome"}}',
                                'Export cookies to file and use: {"options": {"cookiefile": "/path/to/cookies.txt"}}',
                                'Install browser extension to export cookies.txt format',
                                'Make sure you are logged into YouTube in your browser'
                            ],
                            'cookie_extensions': {
                                'chrome': 'Get cookies.txt LOCALLY extension',
                                'firefox': 'cookies.txt extension'
                            }
                        },
                        'traceback': traceback.format_exc()
                    }), 403
                else:
                    return jsonify({
                        'success': False,
                        'error': error_msg,
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
                
                # Auto-detect ffmpeg location
                ffmpeg_location = self._get_ffmpeg_location()
                
                # Use enhanced options with better anti-bot measures
                ydl_opts = self._get_enhanced_ydl_opts(opts)
                ydl_opts.update({
                    # Disable all file writing to disk - we only want in-memory downloads
                    'writesubtitles': False,
                    'writeautomaticsub': False,
                    'writethumbnail': False,
                    'write_all_thumbnails': False,
                    'writeinfojson': False,
                    'writedescription': False,
                    'writeannotations': False,
                    'writelink': False,
                    'writeurllink': False,
                    'writewebloclink': False,
                    'writedesktoplink': False,
                    # Don't use post-processors for memory downloads
                    'postprocessors': [],
                    **opts
                })
                
                # Handle format selection for audio extraction
                if format_selector:
                    ydl_opts['format'] = format_selector
                elif extract_audio:
                    ydl_opts['format'] = 'bestaudio/best'
                else:
                    ydl_opts['format'] = 'best'
                
                # Set ffmpeg location if found (cross-platform)
                if ffmpeg_location:
                    if ffmpeg_location not in ['ffmpeg', 'ffmpeg.exe']:
                        import platform
                        ffmpeg_dir = os.path.dirname(ffmpeg_location)
                        ffprobe_name = 'ffprobe.exe' if platform.system() == 'Windows' else 'ffprobe'
                        ffprobe_location = os.path.join(ffmpeg_dir, ffprobe_name)
                        if os.path.isfile(ffprobe_location):
                            ydl_opts['ffmpeg_location'] = ffmpeg_dir
                        else:
                            ydl_opts['ffmpeg_location'] = ffmpeg_location
                    else:
                        ydl_opts['ffmpeg_location'] = ffmpeg_location
                
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
                    
                    # Determine content type and extension
                    ext = info.get('ext', 'mp4')
                    
                    if extract_audio:
                        # Map audio formats to MIME types
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
                    
                    # Sanitize headers
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
                error_msg = str(e)
                
                # Enhanced error reporting for cookie-related issues
                if 'bot' in error_msg.lower() or 'sign in' in error_msg.lower():
                    return jsonify({
                        'success': False,
                        'error': error_msg,
                        'help': {
                            'issue': 'YouTube bot detection - authentication required',
                            'solutions': [
                                'Use browser cookies: {"options": {"cookiesfrombrowser": "chrome"}}',
                                'Export cookies to file and use: {"options": {"cookiefile": "/path/to/cookies.txt"}}',
                                'Install browser extension to export cookies.txt format',
                                'Make sure you are logged into YouTube in your browser'
                            ]
                        },
                        'traceback': traceback.format_exc()
                    }), 403
                else:
                    return jsonify({
                        'success': False,
                        'error': error_msg,
                        'traceback': traceback.format_exc()
                    }), 500

        @self.app.route('/test-cookies', methods=['GET'])
        def test_cookies():
            """Test endpoint to verify cookie extraction is working"""
            try:
                # Test different browsers
                browsers = ['chrome', 'firefox', 'edge']
                cookie_status = {}
                
                for browser in browsers:
                    try:
                        # Try to load cookies from browser
                        ydl_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'cookiesfrombrowser': browser,  # Just the browser name
                            'simulate': True,
                        }
                        
                        with YoutubeDL(ydl_opts) as ydl:
                            # Just test cookie loading
                            cookie_status[browser] = 'Available'
                    except Exception as e:
                        cookie_status[browser] = f'Error: {str(e)}'
                
                return jsonify({
                    'success': True,
                    'cookie_test_results': cookie_status,
                    'recommendation': 'Use the browser marked as "Available" in your API requests'
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500
    
    def run(self, host='0.0.0.0', port=5002, debug=False):
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
    parser.add_argument('--port', type=int, default=5002, help='Port to bind to')
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
        print("\n📋 Cookie Authentication Help:")
        print("• Browser cookies: POST with {\"options\": {\"cookiesfrombrowser\": \"chrome\"}}")
        print("• Cookie file: POST with {\"options\": {\"cookiefile\": \"/path/to/cookies.txt\"}}")
        print("• Test cookies: GET http://localhost:5002/test-cookies")
        print("\nPress Ctrl+C to stop the server")
        print("-" * 50)
        api.run(host=args.host, port=args.port, debug=args.debug)
        
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1) 