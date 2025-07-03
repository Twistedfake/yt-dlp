#!/usr/bin/env python3
"""
yt-dlp HTTP API Server with Authentication
Provides an HTTP API that returns video content as binary data instead of saving to disk.

AUTHENTICATION:
Set environment variable for API access:
- API_KEY: API key authentication (required for production)
- If not set, API will run without authentication (development only)

USAGE WITH AUTH:
export API_KEY="your-secret-api-key"
curl -H "X-API-Key: your-secret-api-key" http://localhost:5002/download
# OR
curl -H "Authorization: Bearer your-secret-api-key" http://localhost:5002/download

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
python yt_dlp_api.py --debug
"""

import io
import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from functools import wraps
from urllib.parse import parse_qs, urlparse

# Ensure FFmpeg is in PATH
os.environ["PATH"] = "/usr/bin:" + os.environ.get("PATH", "")

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import BadRequest, Unauthorized
import requests

from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_filename
from yt_dlp_memory_downloader import MemoryHttpFD


class YtDlpAPI:
    """HTTP API wrapper for yt-dlp that returns binary content with authentication"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.cookie_dir = self._setup_cookie_directory()
        self._setup_auth()
        self._auto_setup_cookies()  # Automatically handle cookie setup
        self.setup_routes()
    
    def _setup_auth(self):
        """Setup authentication based on environment variables"""
        self.api_key = os.getenv('API_KEY')

        
        # Determine auth mode
        if self.api_key:
            self.auth_mode = 'api_key'
            print(f"🔐 Authentication: API Key (key: {self.api_key[:4]}***)")
        else:
            self.auth_mode = 'none'
            print("⚠️ WARNING: No authentication configured! Set API_KEY environment variable")
    
    def require_auth(self, f):
        """Decorator to require authentication for endpoints"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if self.auth_mode == 'none':
                # No auth configured, allow access
                return f(*args, **kwargs)
            
            if self.auth_mode == 'api_key':
                # Check for API key in headers
                provided_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
                if not provided_key or provided_key != self.api_key:
                    return jsonify({
                        'error': 'Invalid or missing API key',
                        'auth_method': 'api_key',
                        'hint': 'Include X-API-Key header or Authorization: Bearer <key>'
                    }), 401
            
            return f(*args, **kwargs)
        return decorated_function
    
    def _setup_cookie_directory(self):
        """Setup centralized cookie directory for both ytc and manual cookies"""
        import os
        
        # Use YTC-DL directory as the primary cookie location for consistency
        ytc_dl_dir = os.path.join(os.getcwd(), 'YTC-DL')
        
        # Determine the best cookie directory location with YTC-DL as priority
        possible_dirs = [
            ytc_dl_dir,               # YTC-DL directory (highest priority)
            '/app/cookies',           # Docker/VPS standard
            './cookies',              # Local development
            os.path.expanduser('~/.yt-dlp/cookies'),  # User home directory
            '/tmp/yt-dlp-cookies'     # Fallback temp directory
        ]
        
        cookie_dir = None
        for dir_path in possible_dirs:
            try:
                os.makedirs(dir_path, exist_ok=True)
                # Test write permissions
                test_file = os.path.join(dir_path, '.test_write')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                cookie_dir = dir_path
                print(f"🍪 Cookie directory: {cookie_dir}")
                break
            except (OSError, PermissionError):
                continue
        
        if not cookie_dir:
            raise RuntimeError("Could not create writable cookie directory")
        
        return cookie_dir

    def _auto_setup_cookies(self):
        """Automatically set up cookies on API startup"""
        print("🔧 Auto-setting up cookies on startup...")
        
        # Copy any existing cookies to centralized location
        cookie_sources = [
            '/app/cookies/youtube_cookies.txt',
            '/app/cookies/youtube-cookies.txt',
            './cookies/youtube_cookies.txt',
            './cookies/youtube-cookies.txt'
        ]
        
        target = os.path.join(self.cookie_dir, 'cookies.txt')
        
        for source in cookie_sources:
            if os.path.exists(source) and not os.path.exists(target):
                try:
                    import shutil
                    shutil.copy2(source, target)
                    print(f"✅ Auto-copied cookies from {source} to {target}")
                    break
                except Exception as e:
                    print(f"⚠️ Could not auto-copy {source}: {e}")
        
        # Try to get fresh ytc cookies
        try:
            cookie_result = self._get_automated_cookies()
            if cookie_result['success']:
                print(f"✅ Auto-setup: {cookie_result['source']}")
            else:
                print(f"⚠️ Auto-setup: {cookie_result['error']}")
        except Exception as e:
            print(f"⚠️ Auto-setup ytc failed: {e}")
        
        # List what we have
        try:
            available_files = self.get_available_cookie_files()
            if available_files:
                print(f"✅ Cookie files available: {', '.join(available_files)}")
            else:
                print("⚠️ No cookie files found - YouTube may require manual authentication")
        except Exception as e:
            print(f"⚠️ Could not check cookie files: {e}")

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
        """Get enhanced yt-dlp options with better anti-bot measures and automated cookies"""
        if opts is None:
            opts = {}
        
        enhanced_opts = {
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],
                    'player_skip': ['configs'],
                }
            },
            'http_chunk_size': 10485760,
            'retries': 3,
            'fragment_retries': 3,
            'extractor_retries': 3,
            'ignoreerrors': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'ffmpeg_location': 'ffmpeg',
            'prefer_ffmpeg': True,
            **opts
        }
        
        # Try automated cookies first with ytc
        cookie_source = self._get_automated_cookies()
        if cookie_source['success']:
            enhanced_opts.update(cookie_source['opts'])
            print(f"🍪 Using automated cookies: {cookie_source['source']}")
        else:
            print(f"⚠️ Automated cookies failed: {cookie_source['error']}")
            # Fall back to manual cookie file handling
            enhanced_opts = self._handle_manual_cookies(enhanced_opts, opts)
        
        return enhanced_opts
    
    def _get_automated_cookies(self):
        """Try to get automated cookies from ytc service and save to centralized directory"""
        ytc_cookie_file = os.path.join(self.cookie_dir, 'ytc_youtube_cookies.txt')
        ytc_dl_cookies = os.path.join(self.cookie_dir, 'cookies.txt')  # YTC-DL default file
        
        try:
            import ytc
            import time
            
            # Check if we have YTC-DL cookies.txt (this gets priority since it's the primary store)
            if os.path.exists(ytc_dl_cookies):
                file_age = time.time() - os.path.getmtime(ytc_dl_cookies)
                if file_age < 21600:  # 6 hours in seconds
                    print(f"🍪 Using YTC-DL cookies from {ytc_dl_cookies}")
                    return {
                        'success': True,
                        'source': 'YTC-DL cookies.txt',
                        'opts': {'cookiefile': ytc_dl_cookies}
                    }
            
            # Check if we have recent cached cookies (less than 6 hours old)
            if os.path.exists(ytc_cookie_file):
                file_age = time.time() - os.path.getmtime(ytc_cookie_file)
                if file_age < 21600:  # 6 hours in seconds
                    print(f"🍪 Using cached ytc cookies from {ytc_cookie_file}")
                    return {
                        'success': True,
                        'source': 'ytc cached file',
                        'opts': {'cookiefile': ytc_cookie_file}
                    }
            
            # Get fresh cookies from ytc service
            print("🔄 Fetching fresh cookies from ytc remote API...")
            cookie_header = ytc.youtube()
            
            if cookie_header and len(cookie_header.strip()) > 50:  # Basic validation
                # Convert cookie header to Netscape format and save to YTC-DL cookies.txt
                netscape_cookies = self._convert_header_to_netscape(cookie_header)
                
                # Save to YTC-DL cookies.txt (primary location)
                with open(ytc_dl_cookies, 'w') as f:
                    f.write(netscape_cookies)
                
                # Also save backup copy to ytc_youtube_cookies.txt
                with open(ytc_cookie_file, 'w') as f:
                    f.write(netscape_cookies)
                
                print(f"✅ Saved fresh ytc cookies to {ytc_dl_cookies} (primary) and {ytc_cookie_file} (backup)")
                
                return {
                    'success': True,
                    'source': 'ytc remote API (fresh)',
                    'opts': {'cookiefile': ytc_dl_cookies}
                }
            else:
                return {
                    'success': False,
                    'error': 'ytc returned empty or invalid cookies',
                    'opts': {}
                }
                
        except ImportError:
            return {
                'success': False,
                'error': 'ytc library not installed - run pip install ytc',
                'opts': {}
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'ytc service error: {str(e)}',
                'opts': {}
            }
    
    def _convert_header_to_netscape(self, cookie_header):
        """Convert cookie header string to Netscape cookie file format"""
        import time
        
        # Basic Netscape format header
        netscape_content = "# Netscape HTTP Cookie File\n# Generated by yt-dlp API with ytc\n"
        
        # Parse cookies from header (simple approach)
        cookies = cookie_header.split(';')
        for cookie in cookies:
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                # Netscape format: domain, domain_flag, path, secure, expiration, name, value
                expire_time = int(time.time()) + 86400 * 30  # 30 days from now
                netscape_content += f".youtube.com\tTRUE\t/\tFALSE\t{expire_time}\t{name}\t{value}\n"
        
        return netscape_content
    
    def _handle_manual_cookies(self, enhanced_opts, opts):
        """Handle manual cookie files as fallback using centralized directory"""
        print("🔄 Falling back to manual cookie file method")
        
        # Check for existing manual cookie files in centralized directory
        manual_cookie_files = [
            'cookies.txt',            # YTC-DL default cookies (highest priority)
            'youtube_cookies.txt',
            'manual_youtube_cookies.txt',
            'browser_youtube_cookies.txt'
        ]
        
        cookiefile = opts.get('cookiefile')
        if cookiefile:
            # Handle specified cookie file
            if not os.path.isabs(cookiefile):
                # Relative path - look in centralized directory first
                centralized_path = os.path.join(self.cookie_dir, cookiefile)
                if os.path.exists(centralized_path):
                    enhanced_opts['cookiefile'] = centralized_path
                    print(f"🍪 Using cookie file from centralized directory: {centralized_path}")
                    return enhanced_opts
                
                # Legacy path handling for backward compatibility
                if cookiefile.startswith('yt_dlp/cookies/'):
                    legacy_path = f'/app/{cookiefile}'
                elif '/' not in cookiefile:
                    legacy_path = f'/app/cookies/{cookiefile}'
                else:
                    legacy_path = f'/app/{cookiefile}'
                
                # If legacy file exists, copy to centralized directory
                if os.path.exists(legacy_path):
                    self._copy_to_centralized_dir(legacy_path, cookiefile)
                    enhanced_opts['cookiefile'] = os.path.join(self.cookie_dir, cookiefile)
                    return enhanced_opts
            else:
                # Absolute path - copy to centralized directory if it exists
                if os.path.exists(cookiefile):
                    filename = os.path.basename(cookiefile)
                    self._copy_to_centralized_dir(cookiefile, filename)
                    enhanced_opts['cookiefile'] = os.path.join(self.cookie_dir, filename)
                    return enhanced_opts
        else:
            # No cookie file specified - look for default files in centralized directory
            for filename in manual_cookie_files:
                filepath = os.path.join(self.cookie_dir, filename)
                if os.path.exists(filepath):
                    enhanced_opts['cookiefile'] = filepath
                    print(f"🍪 Found default cookie file: {filepath}")
                    return enhanced_opts
        
        print("⚠️ No manual cookie files found in centralized directory")
        return enhanced_opts
    
    def _copy_to_centralized_dir(self, source_path, filename):
        """Copy cookie file to centralized directory and make it writable"""
        dest_path = os.path.join(self.cookie_dir, filename)
        try:
            shutil.copy2(source_path, dest_path)
            os.chmod(dest_path, 0o666)  # Make it writable
            print(f"🔧 Copied cookie file to centralized directory: {dest_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not copy cookie file to centralized directory: {e}")
    
    def get_available_cookie_files(self):
        """Get list of all available cookie files in centralized directory"""
        try:
            files = os.listdir(self.cookie_dir)
            cookie_files = [f for f in files if f.endswith('.txt') and ('cookie' in f.lower() or f == 'cookies.txt')]
            return sorted(cookie_files)
        except Exception:
            return []
        
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/', methods=['GET'])
        def index():
            """Public endpoint - API information and health check"""
            auth_info = {
                'auth_required': self.auth_mode != 'none',
                'auth_method': self.auth_mode,
                'auth_help': {
                    'api_key': 'Include X-API-Key header or Authorization: Bearer <key>',
                    'none': 'No authentication required (development mode)'
                }
            }
            
            return jsonify({
                'service': 'yt-dlp HTTP API with Authentication',
                'version': '2.0.0',
                'authentication': auth_info,
                'endpoints': {
                    '/': 'GET - API information (public)',
                    '/health': 'GET - Health check (public)',
                    '/download': 'POST - Download video and return as binary (protected)',
                    '/info': 'POST - Get video info without downloading (protected)',
                    '/execute': 'POST - Execute system commands (protected)',
                    '/cookie-status': 'GET - Get comprehensive cookie status (protected)',
                    '/refresh-ytc-cookies': 'POST - Force refresh of ytc cookies (protected)',
                    '/list-cookies': 'GET - List all cookie files (protected)',
                    '/install-ytc': 'POST - Install ytc library (protected)'
                },
                'cookie_automation': {
                    'ytc_automated': 'Automatic fresh cookies from remote API (preferred)',
                    'manual_fallback': 'Manual cookie files as backup method',
                    'centralized_directory': self.cookie_dir,
                    'cache_duration': '6 hours for ytc cookies',
                    'test_endpoint': '/test-ytc',
                    'status_endpoint': '/cookie-status',
                    'refresh_endpoint': '/refresh-ytc-cookies'
                },
                'cookie_help': {
                    'automated': 'ytc library handles cookies automatically - no setup needed!',
                    'browser_cookies': 'Use "cookiesfrombrowser":"chrome" in options (fallback)',
                    'cookie_file': 'Use "cookiefile":"/path/to/cookies.txt" in options (fallback)',
                    'supported_browsers': ['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave']
                },
                'usage_examples': {
                    'download_with_api_key': {
                        'url': '/download',
                        'method': 'POST',
                        'headers': {'X-API-Key': 'your-api-key'},
                        'body': {
                            'url': 'https://youtube.com/watch?v=VIDEO_ID',
                            'options': {'cookiesfrombrowser': 'chrome'}
                        }
                    },
                    'download_with_bearer_token': {
                        'url': '/download',
                        'method': 'POST',
                        'headers': {'Authorization': 'Bearer your-api-key'},
                        'body': {
                            'url': 'https://youtube.com/watch?v=VIDEO_ID',
                            'options': {'cookiefile': '/path/to/cookies.txt'}
                        }
                    }
                }
            })
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Public endpoint - Health check"""
            return jsonify({
                'status': 'healthy',
                'service': 'yt-dlp API',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'cookie_directory': self.cookie_dir,
                'auth_configured': self.auth_mode != 'none'
            })
        
        @self.app.route('/info', methods=['POST'])
        @self.require_auth
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
        @self.require_auth
        def download_video():
            """Download video and return as binary stream, optionally with transcription"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')
                
                url = data['url']
                opts = data.get('options', {})
                format_selector = data.get('format', None)
                
                # Transcription parameters
                should_transcribe = data.get('transcribe', False)
                transcribe_model = data.get('transcribe_model', 'base')
                transcribe_language = data.get('transcribe_language', None)
                transcribe_format = data.get('transcribe_format', 'json')
                
                # Check if audio extraction is requested
                extract_audio = opts.get('extractaudio', False)
                audio_format = opts.get('audioformat', 'mp3')
                
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
                    # Force FFmpeg settings
                    'ffmpeg_location': 'ffmpeg',
                    'prefer_ffmpeg': True,
                    **opts
                })
                
                # Handle format selection for audio extraction
                if format_selector:
                    ydl_opts['format'] = format_selector
                elif extract_audio:
                    ydl_opts['format'] = 'bestaudio/best'
                else:
                    ydl_opts['format'] = 'best'
                
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
                    
                    # Handle transcription if requested
                    if should_transcribe:
                        try:
                            import whisper
                            import tempfile
                            
                            # Load Whisper model
                            model = whisper.load_model(transcribe_model)
                            
                            # Save video data to temporary file for transcription
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as temp_file:
                                temp_file.write(video_data)
                                temp_path = temp_file.name
                            
                            try:
                                # Transcribe the file
                                transcribe_options = {
                                    'language': transcribe_language,
                                    'task': 'transcribe'
                                }
                                result = model.transcribe(temp_path, **transcribe_options)
                                
                                # Return transcription based on format
                                if transcribe_format == 'text':
                                    return Response(
                                        result['text'],
                                        mimetype='text/plain',
                                        headers={'Content-Disposition': f'attachment; filename="{title}_transcript.txt"'}
                                    )
                                elif transcribe_format == 'srt':
                                    srt_content = self._whisper_to_srt(result['segments'])
                                    return Response(
                                        srt_content,
                                        mimetype='text/plain',
                                        headers={'Content-Disposition': f'attachment; filename="{title}_transcript.srt"'}
                                    )
                                elif transcribe_format == 'vtt':
                                    vtt_content = self._whisper_to_vtt(result['segments'])
                                    return Response(
                                        vtt_content,
                                        mimetype='text/vtt',
                                        headers={'Content-Disposition': f'attachment; filename="{title}_transcript.vtt"'}
                                    )
                                elif transcribe_format == 'both':
                                    # Return both video and transcript in JSON
                                    import base64
                                    return jsonify({
                                        'success': True,
                                        'title': title,
                                        'duration': info.get('duration', 0),
                                        'language': result.get('language', 'unknown'),
                                        'transcription': {
                                            'text': result['text'],
                                            'segments': result['segments'],
                                            'model_used': transcribe_model
                                        },
                                        'video': {
                                            'filename': filename,
                                            'format': ext,
                                            'size': len(video_data),
                                            'data': base64.b64encode(video_data).decode('utf-8')
                                        },
                                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                                    })
                                else:  # json format (default)
                                    return jsonify({
                                        'success': True,
                                        'title': title,
                                        'duration': info.get('duration', 0),
                                        'language': result.get('language', 'unknown'),
                                        'text': result['text'],
                                        'segments': result['segments'],
                                        'model_used': transcribe_model,
                                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                                    })
                                    
                            finally:
                                # Clean up temp file
                                try:
                                    if os.path.exists(temp_path):
                                        os.unlink(temp_path)
                                except:
                                    pass
                                    
                        except ImportError:
                            return jsonify({
                                'error': 'OpenAI Whisper not installed for transcription',
                                'install_hint': 'Run: pip install openai-whisper'
                            }), 500
                        except Exception as e:
                            return jsonify({
                                'error': f'Transcription failed: {str(e)}',
                                'video_downloaded': True,
                                'video_size': len(video_data)
                            }), 500
                    
                    # Return binary data as streaming response (when no transcription)
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

        @self.app.route('/execute', methods=['POST'])
        @self.require_auth
        def execute_command():
            """Execute system commands with root privileges for VPS management"""
            import subprocess
            import shlex
            import time
            
            try:
                data = request.get_json()
                if not data or 'command' not in data:
                    raise BadRequest('Missing command in request body')
                
                command = data['command']
                use_sudo = data.get('sudo', True)  # Default to using sudo
                timeout = data.get('timeout', 30)  # Default 30 seconds timeout
                working_dir = data.get('cwd', '/app')  # Default to /app directory
                
                # Security: Basic command validation (can be enhanced)
                dangerous_commands = ['rm -rf /', 'format', 'fdisk', 'mkfs']
                if any(dangerous in command.lower() for dangerous in dangerous_commands):
                    return jsonify({
                        'success': False,
                        'error': 'Command contains potentially dangerous operations',
                        'command': command
                    }), 400
                
                # Prepare command with sudo if requested
                if use_sudo and not command.startswith('sudo'):
                    command = f'sudo {command}'
                
                print(f"🚀 Executing command: {command}")
                print(f"📁 Working directory: {working_dir}")
                
                # Execute command
                start_time = time.time()
                
                try:
                    # Use shell=True for complex commands, capture both stdout and stderr
                    result = subprocess.run(
                        command,
                        shell=True,
                        cwd=working_dir,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=dict(os.environ, DEBIAN_FRONTEND='noninteractive')  # Non-interactive mode
                    )
                    
                    execution_time = time.time() - start_time
                    
                    return jsonify({
                        'success': True,
                        'command': command,
                        'exit_code': result.returncode,
                        'stdout': result.stdout,
                        'stderr': result.stderr,
                        'execution_time': round(execution_time, 2),
                        'working_directory': working_dir,
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except subprocess.TimeoutExpired:
                    return jsonify({
                        'success': False,
                        'error': f'Command timed out after {timeout} seconds',
                        'command': command,
                        'timeout': timeout
                    }), 408
                    
                except subprocess.CalledProcessError as e:
                    return jsonify({
                        'success': False,
                        'error': f'Command failed with exit code {e.returncode}',
                        'command': command,
                        'exit_code': e.returncode,
                        'stdout': e.stdout,
                        'stderr': e.stderr
                    }), 500
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500


        @self.app.route('/fix-youtube', methods=['POST'])
        @self.require_auth
        def fix_youtube_auth():
            """Auto-fix YouTube authentication issues"""
            try:
                print("🔧 Auto-fixing YouTube authentication...")
                
                # Commands to fix YouTube authentication
                fix_commands = [
                    # Update yt-dlp to latest version
                    'pip install --upgrade yt-dlp',
                    
                    # Install additional dependencies
                    'pip install --upgrade requests urllib3 certifi',
                    
                    # Fix the cookie handling in the API
                    '''python3 -c "
import os
api_file = '/app/yt_dlp_api.py'
if os.path.exists(api_file):
    with open(api_file, 'r') as f:
        content = f.read()
    
    # Fix cookie handling
    old_code = 'enhanced_opts[\"cookiesfrombrowser\"] = cookiesfrombrowser.lower()'
    new_code = 'enhanced_opts[\"cookiesfrombrowser\"] = (cookiesfrombrowser.lower(),) if isinstance(cookiesfrombrowser, str) else cookiesfrombrowser'
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        with open(api_file, 'w') as f:
            f.write(content)
        print('Cookie handling fixed')
    else:
        print('Cookie code not found or already fixed')
"''',
                ]
                
                results = []
                for cmd in fix_commands:
                    try:
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd='/app',
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        results.append({
                            'command': cmd[:50] + '...' if len(cmd) > 50 else cmd,
                            'success': result.returncode == 0,
                            'output': result.stdout,
                            'error': result.stderr
                        })
                    except Exception as e:
                        results.append({
                            'command': cmd[:50] + '...' if len(cmd) > 50 else cmd,
                            'success': False,
                            'error': str(e)
                        })
                
                return jsonify({
                    'success': True,
                    'message': 'YouTube authentication fix completed',
                    'results': results,
                    'next_steps': [
                        'Restart the Docker container: docker-compose restart',
                        'Test with: {"url": "https://youtube.com/watch?v=VIDEO_ID", "options": {"cookiesfrombrowser": "chrome"}}',
                        'Check logs for success'
                    ]
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/cookie-status', methods=['GET'])
        @self.require_auth
        def cookie_status():
            """Get comprehensive cookie status including centralized directory"""
            try:
                # Test ytc
                ytc_result = self._get_automated_cookies()
                
                # Get all cookie files from centralized directory
                centralized_files = {}
                try:
                    for filename in os.listdir(self.cookie_dir):
                        if filename.endswith('.txt') and 'cookie' in filename.lower():
                            filepath = os.path.join(self.cookie_dir, filename)
                            stat = os.stat(filepath)
                            centralized_files[filename] = {
                                'path': filepath,
                                'size': stat.st_size,
                                'modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                                'age_hours': (time.time() - stat.st_mtime) / 3600,
                                'readable': os.access(filepath, os.R_OK),
                                'writable': os.access(filepath, os.W_OK)
                            }
                except Exception as e:
                    centralized_files = {'error': str(e)}
                
                return jsonify({
                    'centralized_directory': {
                        'path': self.cookie_dir,
                        'cookie_files': centralized_files
                    },
                    'ytc_automated': {
                        'available': ytc_result['success'],
                        'source': ytc_result.get('source', 'none'),
                        'error': ytc_result.get('error') if not ytc_result['success'] else None,
                        'primary_file': os.path.join(self.cookie_dir, 'cookies.txt'),
                        'backup_file': os.path.join(self.cookie_dir, 'ytc_youtube_cookies.txt')
                    },
                    'recommendation': 'ytc automated' if ytc_result['success'] else 'manual cookie files',
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'cache_duration': '6 hours for ytc cookies'
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/refresh-ytc-cookies', methods=['POST'])
        @self.require_auth
        def refresh_ytc_cookies():
            """Force refresh of ytc cookies (ignore cache)"""
            try:
                ytc_cookie_file = os.path.join(self.cookie_dir, 'ytc_youtube_cookies.txt')
                ytc_dl_cookies = os.path.join(self.cookie_dir, 'cookies.txt')
                
                # Remove existing cached files to force refresh
                files_removed = []
                for cookie_file in [ytc_cookie_file, ytc_dl_cookies]:
                    if os.path.exists(cookie_file):
                        os.remove(cookie_file)
                        files_removed.append(cookie_file)
                        print(f"🗑️ Removed cached cookies: {cookie_file}")
                
                # Get fresh cookies
                cookie_result = self._get_automated_cookies()
                
                if cookie_result['success']:
                    return jsonify({
                        'success': True,
                        'message': 'ytc cookies refreshed successfully',
                        'source': cookie_result['source'],
                        'primary_cookie_file': ytc_dl_cookies,
                        'backup_cookie_file': ytc_cookie_file,
                        'files_removed': files_removed,
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Failed to refresh ytc cookies',
                        'error': cookie_result['error']
                    }), 500
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/list-cookies', methods=['GET'])
        @self.require_auth
        def list_cookies():
            """List all cookie files in centralized directory"""
            try:
                cookie_files = self.get_available_cookie_files()
                detailed_info = []
                
                for filename in cookie_files:
                    filepath = os.path.join(self.cookie_dir, filename)
                    stat = os.stat(filepath)
                    detailed_info.append({
                        'filename': filename,
                        'path': filepath,
                        'size': stat.st_size,
                        'modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                        'age_hours': round((time.time() - stat.st_mtime) / 3600, 1),
                        'type': 'ytc-dl-primary' if filename == 'cookies.txt' else ('ytc-backup' if 'ytc' in filename else 'manual'),
                        'writable': os.access(filepath, os.W_OK)
                    })
                
                return jsonify({
                    'centralized_directory': self.cookie_dir,
                    'total_files': len(cookie_files),
                    'cookie_files': detailed_info,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/install-ytc', methods=['POST'])
        @self.require_auth
        def install_ytc():
            """Install ytc library if not already installed"""
            try:
                # Check if already installed
                try:
                    import ytc
                    return jsonify({
                        'success': True,
                        'message': 'ytc already installed',
                        'status': 'already_installed'
                    })
                except ImportError:
                    pass
                
                # Try to install ytc
                import subprocess
                import sys
                
                result = subprocess.run([
                    sys.executable, '-m', 'pip', 'install', 'ytc'
                ], capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    return jsonify({
                        'success': True,
                        'message': 'ytc installed successfully',
                        'status': 'installed',
                        'output': result.stdout
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Failed to install ytc',
                        'status': 'install_failed',
                        'error': result.stderr,
                        'output': result.stdout
                    }), 500
                    
            except subprocess.TimeoutExpired:
                return jsonify({
                    'success': False,
                    'message': 'Installation timeout',
                    'status': 'timeout'
                }), 500
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'Installation error: {str(e)}',
                    'status': 'error',
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/transcribe-file', methods=['POST'])
        @self.require_auth
        def transcribe_file():
            """Transcribe audio/video from uploaded file using OpenAI Whisper"""
            try:
                # Check if file is uploaded
                if 'file' not in request.files:
                    return jsonify({'error': 'No file uploaded'}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': 'No file selected'}), 400
                
                # Get parameters from form data
                model_size = request.form.get('model', 'base')
                language = request.form.get('language', None)
                response_format = request.form.get('format', 'json')
                
                # Import Whisper (lazy import)
                try:
                    import whisper
                except ImportError:
                    return jsonify({
                        'error': 'OpenAI Whisper not installed',
                        'install_hint': 'Run: pip install openai-whisper'
                    }), 500
                
                # Load Whisper model
                try:
                    model = whisper.load_model(model_size)
                except Exception as e:
                    return jsonify({
                        'error': f'Failed to load Whisper model "{model_size}": {str(e)}',
                        'available_models': ['tiny', 'base', 'small', 'medium', 'large']
                    }), 500
                
                # Save uploaded file temporarily
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file.filename.split(".")[-1]}') as temp_file:
                    file.save(temp_file.name)
                    temp_path = temp_file.name
                
                try:
                    # Whisper can handle MP4, MP3, WAV, etc. directly via FFmpeg
                    transcribe_options = {
                        'language': language,
                        'task': 'transcribe'
                    }
                    
                    result = model.transcribe(temp_path, **transcribe_options)
                    
                    # Format response based on requested format
                    if response_format == 'text':
                        return Response(
                            result['text'],
                            mimetype='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{file.filename}_transcript.txt"'}
                        )
                    elif response_format == 'srt':
                        srt_content = self._whisper_to_srt(result['segments'])
                        return Response(
                            srt_content,
                            mimetype='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{file.filename}_transcript.srt"'}
                        )
                    elif response_format == 'vtt':
                        vtt_content = self._whisper_to_vtt(result['segments'])
                        return Response(
                            vtt_content,
                            mimetype='text/vtt',
                            headers={'Content-Disposition': f'attachment; filename="{file.filename}_transcript.vtt"'}
                        )
                    else:  # json format (default)
                        return jsonify({
                            'success': True,
                            'filename': file.filename,
                            'language': result.get('language', 'unknown'),
                            'text': result['text'],
                            'segments': result['segments'],
                            'model_used': model_size,
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                
                finally:
                    # Clean up temporary file
                    try:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                    except:
                        pass
                        
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/transcribe', methods=['POST'])
        @self.require_auth
        def transcribe_audio():
            """Transcribe audio from video URL using OpenAI Whisper"""
            try:
                data = request.get_json(force=True)
                if not data or 'url' not in data:
                    return jsonify({'error': 'URL is required'}), 400
                
                url = data['url']
                model_size = data.get('model', 'base')  # tiny, base, small, medium, large
                language = data.get('language', None)  # auto-detect if None
                response_format = data.get('format', 'json')  # json, text, srt, vtt
                
                # Import Whisper (lazy import to avoid startup errors if not installed)
                try:
                    import whisper
                except ImportError:
                    return jsonify({
                        'error': 'OpenAI Whisper not installed',
                        'install_hint': 'Run: pip install openai-whisper'
                    }), 500
                
                # Load Whisper model
                try:
                    model = whisper.load_model(model_size)
                except Exception as e:
                    return jsonify({
                        'error': f'Failed to load Whisper model "{model_size}": {str(e)}',
                        'available_models': ['tiny', 'base', 'small', 'medium', 'large']
                    }), 500
                
                # Extract audio using yt-dlp
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                    audio_path = temp_audio.name
                
                try:
                    # Get enhanced yt-dlp options
                    opts = data.get('options', {})
                    enhanced_opts = self._get_enhanced_ydl_opts(opts)
                    
                    # Configure for audio extraction
                    enhanced_opts.update({
                        'format': 'bestaudio',
                        'outtmpl': audio_path.replace('.wav', '.%(ext)s'),
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'wav',
                            'preferredquality': '192',
                        }]
                    })
                    
                    # Download and extract audio
                    with YoutubeDL(enhanced_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        title = info.get('title', 'Unknown')
                        duration = info.get('duration', 0)
                    
                    # Find the actual audio file (yt-dlp might change extension)
                    import glob
                    audio_files = glob.glob(audio_path.replace('.wav', '.*'))
                    if not audio_files:
                        return jsonify({'error': 'Failed to extract audio'}), 500
                    
                    actual_audio_path = audio_files[0]
                    
                    # Transcribe with Whisper
                    transcribe_options = {
                        'language': language,
                        'task': 'transcribe'
                    }
                    
                    result = model.transcribe(actual_audio_path, **transcribe_options)
                    
                    # Format response based on requested format
                    if response_format == 'text':
                        return Response(
                            result['text'],
                            mimetype='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(title)}_transcript.txt"'}
                        )
                    elif response_format == 'srt':
                        # Convert to SRT format
                        srt_content = self._whisper_to_srt(result['segments'])
                        return Response(
                            srt_content,
                            mimetype='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(title)}_transcript.srt"'}
                        )
                    elif response_format == 'vtt':
                        # Convert to VTT format
                        vtt_content = self._whisper_to_vtt(result['segments'])
                        return Response(
                            vtt_content,
                            mimetype='text/vtt',
                            headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(title)}_transcript.vtt"'}
                        )
                    else:  # json format (default)
                        return jsonify({
                            'success': True,
                            'title': title,
                            'duration': duration,
                            'language': result.get('language', 'unknown'),
                            'text': result['text'],
                            'segments': result['segments'],
                            'model_used': model_size,
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                
                finally:
                    # Clean up temporary files
                    try:
                        if os.path.exists(audio_path):
                            os.unlink(audio_path)
                        for audio_file in glob.glob(audio_path.replace('.wav', '.*')):
                            if os.path.exists(audio_file):
                                os.unlink(audio_file)
                    except:
                        pass
                        
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

    def _whisper_to_srt(self, segments):
        """Convert Whisper segments to SRT subtitle format"""
        srt_content = ""
        for i, segment in enumerate(segments, 1):
            start_time = self._seconds_to_srt_time(segment['start'])
            end_time = self._seconds_to_srt_time(segment['end'])
            text = segment['text'].strip()
            
            srt_content += f"{i}\n{start_time} --> {end_time}\n{text}\n\n"
        
        return srt_content

    def _whisper_to_vtt(self, segments):
        """Convert Whisper segments to VTT subtitle format"""
        vtt_content = "WEBVTT\n\n"
        for segment in segments:
            start_time = self._seconds_to_vtt_time(segment['start'])
            end_time = self._seconds_to_vtt_time(segment['end'])
            text = segment['text'].strip()
            
            vtt_content += f"{start_time} --> {end_time}\n{text}\n\n"
        
        return vtt_content

    def _seconds_to_srt_time(self, seconds):
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    def _seconds_to_vtt_time(self, seconds):
        """Convert seconds to VTT time format (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"

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
        print("\n📋 Authentication & Usage Help:")
        if api.auth_mode != 'none':
            print("• API Key: curl -H \"X-API-Key: your-key\" http://localhost:5002/download")
            print("• Bearer: curl -H \"Authorization: Bearer your-key\" http://localhost:5002/download")
        print("• Browser cookies: POST with {\"options\": {\"cookiesfrombrowser\": \"chrome\"}}")
        print("• Cookie file: POST with {\"options\": {\"cookiefile\": \"/path/to/cookies.txt\"}}")
        print("• Health check: GET http://localhost:5002/health")
        print("\nPress Ctrl+C to stop the server")
        print("-" * 50)
        api.run(host=args.host, port=args.port, debug=args.debug)
        
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1) 