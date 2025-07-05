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
import uuid
import threading
from datetime import datetime, timedelta
import hashlib
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import queue

# Ensure FFmpeg is in PATH
os.environ["PATH"] = "/usr/bin:" + os.environ.get("PATH", "")

from flask import Flask, Response, jsonify, request, stream_template_string
from werkzeug.exceptions import BadRequest, Unauthorized
import requests

from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_filename
from yt_dlp_memory_downloader import MemoryHttpFD


class JobQueue:
    """Background job queue for async video processing"""
    
    def __init__(self, max_workers=3, max_queue_size=100, api_instance=None):
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.max_workers = max_workers
        self.workers = []
        self.is_running = False
        self.api_instance = api_instance
        self.stats = {
            'total_processed': 0,
            'total_failed': 0,
            'current_queue_size': 0,
            'active_workers': 0
        }
        
    def start(self):
        """Start background workers"""
        if self.is_running:
            return
            
        self.is_running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker, name=f'JobWorker-{i+1}', daemon=True)
            worker.start()
            self.workers.append(worker)
        
        print(f"✅ Started {self.max_workers} background workers")
        
    def stop(self):
        """Stop background workers"""
        self.is_running = False
        
        # Add stop signals for each worker
        for _ in self.workers:
            self.queue.put(None)
            
        print("🛑 Stopping background workers...")
        
    def add_job(self, job_data):
        """Add job to queue"""
        try:
            self.queue.put(job_data, timeout=1)
            self.stats['current_queue_size'] = self.queue.qsize()
            return True
        except queue.Full:
            return False
            
    def _worker(self):
        """Background worker that processes jobs"""
        worker_name = threading.current_thread().name
        print(f"🚀 {worker_name} started")
        
        while self.is_running:
            try:
                # Get job from queue
                job_data = self.queue.get(timeout=1)
                
                # Stop signal
                if job_data is None:
                    break
                    
                self.stats['active_workers'] += 1
                self.stats['current_queue_size'] = self.queue.qsize()
                
                print(f"📋 {worker_name} processing job {job_data.get('job_id', 'unknown')}")
                
                # Process job - add api_instance reference
                job_data['api_instance'] = self.api_instance
                success = self._process_job(job_data)
                
                # Update stats
                if success:
                    self.stats['total_processed'] += 1
                else:
                    self.stats['total_failed'] += 1
                    
                self.stats['active_workers'] -= 1
                self.queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ {worker_name} error: {e}")
                self.stats['total_failed'] += 1
                self.stats['active_workers'] -= 1
                
        print(f"🛑 {worker_name} stopped")
        
    def _process_job(self, job_data):
        """Process a single job"""
        job_id = job_data.get('job_id')
        job_type = job_data.get('type')
        api_instance = job_data.get('api_instance')
        
        try:
            if job_type == 'download':
                return self._process_download_job(job_data, api_instance)
            elif job_type == 'transcribe':
                return self._process_transcribe_job(job_data, api_instance)
            elif job_type == 'channel':
                return self._process_channel_job(job_data, api_instance)
            elif job_type == 'search':
                return api_instance._process_search_job(job_data, api_instance)
            else:
                print(f"❌ Unknown job type: {job_type}")
                api_instance.update_job(job_id, status='failed', error='Unknown job type')
                return False
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Job {job_id} failed: {error_msg}")
            api_instance.update_job(job_id, 
                status='failed', 
                error=error_msg,
                traceback=traceback.format_exc()
            )
            return False
            
    def _process_download_job(self, job_data, api_instance):
        """Process video download job"""
        job_id = job_data['job_id']
        url = job_data['url']
        opts = job_data.get('options', {})
        format_selector = job_data.get('format')
        should_transcribe = job_data.get('transcribe', False)
        transcribe_model = job_data.get('transcribe_model', 'base')
        transcribe_language = job_data.get('transcribe_language', None)
        transcribe_format = job_data.get('transcribe_format', 'json')
        
        api_instance.update_job(job_id, status='processing', progress=10)
        
        # Download video
        enhanced_opts = api_instance._get_enhanced_ydl_opts(opts)
        if format_selector:
            enhanced_opts['format'] = format_selector
            
        class MemoryYDL(YoutubeDL):
            def __init__(self, params=None):
                super().__init__(params)
                self.video_data = None
                
            def dl(self, name, info, subtitle=False, test=False):
                fd = MemoryHttpFD(self, self.params)
                success = fd.real_download(name, info)
                self.video_data = fd.get_downloaded_data()
                return ('finished', info) if success else ('error', info)
                
        with MemoryYDL(enhanced_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                video_data = ydl.video_data
                
                if not video_data:
                    raise Exception("No video data received")
                    
                api_instance.update_job(job_id, progress=60)
                
                # Prepare result
                result = {
                    'success': True,
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'format': info.get('ext', 'mp4'),
                    'file_size': len(video_data),
                    'video_data': video_data,
                    'download_time': time.time()
                }
                
                # Handle transcription if requested
                if should_transcribe:
                    api_instance.update_job(job_id, progress=70, status_message='Transcribing...')
                    
                    try:
                        import whisper
                        import tempfile
                        import os
                        
                        model = whisper.load_model(transcribe_model)
                        
                        # Create temporary directory for better file management
                        with tempfile.TemporaryDirectory() as temp_dir:
                            audio_path = os.path.join(temp_dir, 'audio.%(ext)s')
                            
                            # Configure audio extraction with more robust settings
                            audio_opts = api_instance._get_enhanced_ydl_opts(opts)
                            audio_opts.update({
                                'format': 'bestaudio[filesize<30M]/bestaudio',
                                'quiet': True,
                                'no_warnings': True,
                                'outtmpl': audio_path,
                                'postprocessors': [{
                                    'key': 'FFmpegExtractAudio',
                                    'preferredcodec': 'mp3',
                                    'preferredquality': '128',
                                }]
                            })
                            
                            try:
                                # Download audio for transcription
                                with YoutubeDL(audio_opts) as ydl:
                                    ydl.download([url])
                                
                                # Find extracted audio file
                                import glob
                                audio_files = glob.glob(os.path.join(temp_dir, 'audio.*'))
                                if not audio_files:
                                    raise Exception('Failed to extract audio - no audio files found')
                                
                                actual_audio_path = audio_files[0]
                                
                                # Verify audio file exists and has content
                                if not os.path.exists(actual_audio_path):
                                    raise Exception('Audio file does not exist after extraction')
                                
                                file_size = os.path.getsize(actual_audio_path)
                                if file_size == 0:
                                    raise Exception('Audio file is empty after extraction')
                                
                                print(f"Audio file ready for transcription: {actual_audio_path} ({file_size} bytes)")
                                
                                # Transcribe with error handling
                                transcribe_options = {
                                    'language': transcribe_language,
                                    'task': 'transcribe',
                                    'fp16': False,  # Disable FP16 for stability
                                }
                                
                                whisper_result = model.transcribe(actual_audio_path, **transcribe_options)
                                
                                if transcribe_format == 'text':
                                    transcription = whisper_result['text']
                                else:
                                    transcription = {
                                        'text': whisper_result['text'],
                                        'language': whisper_result.get('language', 'unknown'),
                                        'segments': whisper_result['segments'],
                                        'model_used': transcribe_model,
                                        'audio_file_size': file_size
                                    }
                                
                                result['transcription'] = transcription
                                
                            except Exception as e:
                                result['transcription_error'] = f'Audio extraction failed: {str(e)}'
                                
                    except ImportError:
                        result['transcription_error'] = 'Whisper not installed'
                    except Exception as e:
                        result['transcription_error'] = f'Transcription setup failed: {str(e)}'
                
                # Store result
                api_instance.add_job_result(job_id, result)
                api_instance.update_job(job_id, 
                    status='completed', 
                    progress=100,
                    completed_at=time.time(),
                    result_summary=f"Downloaded: {result['title']}"
                )
                
                return True
                
            except Exception as e:
                raise Exception(f"Download failed: {str(e)}")
                
    def _process_transcribe_job(self, job_data, api_instance):
        """Process transcription-only job"""
        job_id = job_data['job_id']
        url = job_data['url']
        opts = job_data.get('options', {})
        model_size = job_data.get('model', 'base')
        language = job_data.get('language')
        response_format = job_data.get('format', 'json')
        
        api_instance.update_job(job_id, status='processing', progress=10)
        
        try:
            import whisper
            import tempfile
            import glob
            import os
            
            model = whisper.load_model(model_size)
            api_instance.update_job(job_id, progress=30, status_message='Extracting audio...')
            
            # Extract audio using more robust settings
            enhanced_opts = api_instance._get_enhanced_ydl_opts(opts)
            enhanced_opts.update({
                'format': 'bestaudio[filesize<30M]/bestaudio',
                'quiet': True,
                'no_warnings': True
            })
            
            # Create temporary directory for better file management
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = os.path.join(temp_dir, 'audio.%(ext)s')
                
                enhanced_opts['outtmpl'] = audio_path
                enhanced_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }]
                
                try:
                    with YoutubeDL(enhanced_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        title = info.get('title', 'Unknown')
                        duration = info.get('duration', 0)
                    
                    api_instance.update_job(job_id, progress=60, status_message='Transcribing audio...')
                    
                    # Find extracted audio file
                    audio_files = glob.glob(os.path.join(temp_dir, 'audio.*'))
                    if not audio_files:
                        raise Exception('Failed to extract audio - no audio files found')
                    
                    actual_audio_path = audio_files[0]
                    
                    # Verify audio file exists and has content
                    if not os.path.exists(actual_audio_path):
                        raise Exception('Audio file does not exist after extraction')
                    
                    file_size = os.path.getsize(actual_audio_path)
                    if file_size == 0:
                        raise Exception('Audio file is empty after extraction')
                    
                    print(f"Audio file ready: {actual_audio_path} ({file_size} bytes)")
                    
                    # Transcribe with error handling
                    transcribe_options = {
                        'language': language,
                        'task': 'transcribe',
                        'fp16': False,  # Disable FP16 for stability
                    }
                    
                    result = model.transcribe(actual_audio_path, **transcribe_options)
                    
                    # Format result
                    transcription_result = {
                        'success': True,
                        'title': title,
                        'duration': duration,
                        'language': result.get('language', 'unknown'),
                        'text': result['text'],
                        'segments': result['segments'],
                        'model_used': model_size,
                        'format': response_format,
                        'audio_file_size': file_size
                    }
                    
                    api_instance.add_job_result(job_id, transcription_result)
                    api_instance.update_job(job_id,
                        status='completed',
                        progress=100,
                        completed_at=time.time(),
                        result_summary=f"Transcribed: {title}"
                    )
                    
                    return True
                    
                except Exception as e:
                    raise Exception(f'Audio extraction failed: {str(e)}')
                    
        except ImportError:
            raise Exception('OpenAI Whisper not installed')
        except Exception as e:
            raise Exception(f'Transcription job failed: {str(e)}')
    
    def _process_channel_job(self, job_data, api_instance):
        """Process channel download and transcription job"""
        try:
            job_id = job_data['job_id']
            videos = job_data['videos']
            should_download = job_data['download']
            should_transcribe = job_data['transcribe']
            transcribe_model = job_data.get('transcribe_model', 'base')
            transcribe_format = job_data.get('transcribe_format', 'json')
            enhanced_opts = job_data['enhanced_opts']
            
            api_instance.update_job(job_id, status='processing')
            
            for i, video in enumerate(videos):
                video_url = f"https://www.youtube.com/watch?v={video['id']}"
                video_title = video.get('title', 'Unknown Title')
                
                try:
                    api_instance.update_job(job_id, current_item=f"Processing: {video_title}")
                    
                    video_result = {
                        'id': video['id'],
                        'title': video_title,
                        'url': video_url,
                        'duration': video.get('duration', 0),
                        'upload_date': video.get('upload_date', ''),
                        'success': True
                    }
                    
                    # Download video if requested
                    if should_download:
                        download_opts = enhanced_opts.copy()
                        download_opts.update({
                            'format': job_data.get('format', 'best[filesize<50M]'),
                            'writesubtitles': False,
                            'writeautomaticsub': False,
                            'writethumbnail': False,
                            'writeinfojson': False,
                            'postprocessors': [],
                            'quiet': True
                        })
                        
                        # Download to memory
                        from yt_dlp_memory_downloader import MemoryHttpFD
                        
                        class MemoryYDL(YoutubeDL):
                            def __init__(self, params=None):
                                super().__init__(params)
                                self.memory_downloader = None
                                
                            def dl(self, name, info, subtitle=False, test=False):
                                if not info.get('url'):
                                    self.raise_no_formats(info, True)
                                self.memory_downloader = MemoryHttpFD(self, self.params)
                                success = self.memory_downloader.real_download(name, info)
                                return ('finished', info) if success else ('error', info)
                        
                        with MemoryYDL(download_opts) as ydl:
                            info = ydl.extract_info(video_url, download=True)
                            
                            if ydl.memory_downloader:
                                video_data = ydl.memory_downloader.get_downloaded_data()
                                
                                if video_data:
                                    import base64
                                    video_result.update({
                                        'file_size': len(video_data),
                                        'format': info.get('ext', 'unknown'),
                                        'video_data': base64.b64encode(video_data).decode('utf-8')
                                    })
                    
                    # Transcribe if requested
                    if should_transcribe:
                        try:
                            import whisper
                            import tempfile
                            import os
                            
                            model = whisper.load_model(transcribe_model)
                            
                            # Download audio for transcription with more robust settings
                            audio_opts = enhanced_opts.copy()
                            audio_opts.update({
                                'format': 'bestaudio[filesize<30M]/bestaudio',
                                'quiet': True,
                                'no_warnings': True
                            })
                            
                            # Create temporary directory for better file management
                            with tempfile.TemporaryDirectory() as temp_dir:
                                audio_path = os.path.join(temp_dir, f'audio_{i}.%(ext)s')
                                
                                audio_opts['outtmpl'] = audio_path
                                audio_opts['postprocessors'] = [{
                                    'key': 'FFmpegExtractAudio',
                                    'preferredcodec': 'mp3',
                                    'preferredquality': '128',
                                }]
                                
                                try:
                                    with YoutubeDL(audio_opts) as ydl:
                                        ydl.download([video_url])
                                    
                                    # Find extracted audio file
                                    import glob
                                    audio_files = glob.glob(os.path.join(temp_dir, f'audio_{i}.*'))
                                    if not audio_files:
                                        raise Exception('Failed to extract audio - no audio files found')
                                    
                                    actual_audio_path = audio_files[0]
                                    
                                    # Verify audio file exists and has content
                                    if not os.path.exists(actual_audio_path):
                                        raise Exception('Audio file does not exist after extraction')
                                    
                                    file_size = os.path.getsize(actual_audio_path)
                                    if file_size == 0:
                                        raise Exception('Audio file is empty after extraction')
                                    
                                    print(f"Audio file ready for {video_title}: {actual_audio_path} ({file_size} bytes)")
                                    
                                    # Transcribe with error handling
                                    transcribe_options = {
                                        'language': None,  # Let Whisper auto-detect
                                        'task': 'transcribe',
                                        'fp16': False,  # Disable FP16 for stability
                                    }
                                    
                                    whisper_result = model.transcribe(actual_audio_path, **transcribe_options)
                                    
                                    if transcribe_format == 'text':
                                        transcription = whisper_result['text']
                                    else:
                                        transcription = {
                                            'text': whisper_result['text'],
                                            'language': whisper_result.get('language', 'unknown'),
                                            'segments': whisper_result['segments'] if transcribe_format == 'json' else len(whisper_result['segments']),
                                            'model_used': transcribe_model,
                                            'audio_file_size': file_size
                                        }
                                    
                                    video_result['transcription'] = transcription
                                    
                                except Exception as e:
                                    video_result['transcription_error'] = f'Audio extraction failed: {str(e)}'
                                    
                        except ImportError:
                            video_result['transcription_error'] = 'Whisper not installed'
                        except Exception as e:
                            video_result['transcription_error'] = f'Transcription setup failed: {str(e)}'
                    
                    api_instance.add_job_result(job_id, video_result)
                    
                except Exception as e:
                    error_result = {
                        'id': video['id'],
                        'title': video_title,
                        'url': video_url,
                        'success': False,
                        'error': str(e)
                    }
                    api_instance.add_job_result(job_id, error_result)
            
            api_instance.update_job(job_id, status='completed', current_item=None)
            return True
            
        except Exception as e:
            api_instance.update_job(job_id, status='failed', error=str(e))
            return False
    
    def get_stats(self):
        """Get queue statistics"""
        return {
            **self.stats,
            'current_queue_size': self.queue.qsize(),
            'is_running': self.is_running,
            'total_workers': len(self.workers)
        }


class YtDlpAPI:
    """HTTP API wrapper for yt-dlp that returns binary content with authentication"""
    
    def __init__(self, max_workers=3, max_queue_size=100):
        self.app = Flask(__name__)
        self.setup_logging()
        self.setup_auth()
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self.cookie_dir = "/app/cookies"
        
        # Initialize job queue
        self.job_queue = JobQueue(max_workers=max_workers, max_queue_size=max_queue_size, api_instance=self)
        self.job_queue.start()
        
        self.setup_routes()
    
    def setup_logging(self):
        """Setup logging for the API"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def setup_auth(self):
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
        import tempfile
        
        # Use YTC-DL directory as the primary cookie location for consistency
        ytc_dl_dir = os.path.join(os.getcwd(), 'YTC-DL')
        
        # Determine the best cookie directory location with YTC-DL as priority
        possible_dirs = [
            ytc_dl_dir,               # YTC-DL directory (highest priority)
            '/app/cookies',           # Docker/VPS standard
            './cookies',              # Local development
            os.path.expanduser('~/.yt-dlp/cookies'),  # User home directory
            '/tmp/yt-dlp-cookies',    # Fallback temp directory
            tempfile.gettempdir()     # System temp directory as last resort
        ]
        
        cookie_dir = None
        for dir_path in possible_dirs:
            try:
                # Create directory if it doesn't exist
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                
                # Test write permissions
                test_file = os.path.join(dir_path, '.test_write')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                cookie_dir = dir_path
                print(f"🍪 Cookie directory: {cookie_dir}")
                break
            except (OSError, PermissionError) as e:
                print(f"⚠️ Cannot use {dir_path}: {e}")
                continue
        
        if not cookie_dir:
            # If all else fails, use a temp directory that we know we can write to
            try:
                cookie_dir = tempfile.mkdtemp(prefix='yt-dlp-cookies-')
                print(f"🍪 Using temporary cookie directory: {cookie_dir}")
            except Exception as e:
                print(f"⚠️ Warning: Could not create any cookie directory: {e}")
                # Return current directory as absolute fallback
                cookie_dir = os.getcwd()
                print(f"⚠️ Using current directory as cookie fallback: {cookie_dir}")
        
        return cookie_dir

    def create_job(self, job_type, total_items=0, **kwargs):
        """Create a new job and return job_id"""
        job_id = str(uuid.uuid4())
        
        with self.jobs_lock:
            self.jobs[job_id] = {
                'id': job_id,
                'type': job_type,  # 'download', 'channel', 'transcribe'
                'status': 'starting',  # starting, running, completed, failed
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'total_items': total_items,
                'completed_items': 0,
                'failed_items': 0,
                'current_item': None,
                'results': [],
                'failed_results': [],
                'error': None,
                'progress_percent': 0,
                'estimated_time_remaining': None,
                'transcriptions': [],  # Store all transcriptions
                **kwargs
            }
        
        return job_id
    
    def update_job(self, job_id, **updates):
        """Update job status and data"""
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)
                self.jobs[job_id]['updated_at'] = datetime.now().isoformat()
                
                # Calculate progress
                if self.jobs[job_id]['total_items'] > 0:
                    completed = self.jobs[job_id]['completed_items']
                    total = self.jobs[job_id]['total_items']
                    self.jobs[job_id]['progress_percent'] = (completed / total) * 100
    
    def get_job(self, job_id):
        """Get job data"""
        with self.jobs_lock:
            return self.jobs.get(job_id, None)
    
    def add_job_result(self, job_id, result):
        """Add a result to job"""
        with self.jobs_lock:
            if job_id in self.jobs:
                if result.get('success', False):
                    self.jobs[job_id]['results'].append(result)
                    self.jobs[job_id]['completed_items'] += 1
                else:
                    self.jobs[job_id]['failed_results'].append(result)
                    self.jobs[job_id]['failed_items'] += 1
                
                # Add transcription if present
                if 'transcription' in result:
                    self.jobs[job_id]['transcriptions'].append({
                        'video_title': result.get('title', 'Unknown'),
                        'video_url': result.get('url', ''),
                        'transcription': result['transcription']
                    })

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
        
        # Explicit paths since we know where ffmpeg is located
        if not is_windows:
            # Linux/Unix - try known locations first
            known_locations = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/ffmpeg/bin/ffmpeg',
                '/snap/bin/ffmpeg',  # Snap package
            ]
            
            for location in known_locations:
                if os.path.isfile(location):
                    try:
                        # Test that ffmpeg actually works
                        subprocess.run([location, '-version'], 
                                     capture_output=True, check=True, timeout=5)
                        print(f"✅ Found working ffmpeg at: {location}")
                        
                        # Also check for ffprobe in same directory
                        ffprobe_location = location.replace('/ffmpeg', '/ffprobe')
                        if os.path.isfile(ffprobe_location):
                            try:
                                subprocess.run([ffprobe_location, '-version'], 
                                             capture_output=True, check=True, timeout=5)
                                print(f"✅ Found working ffprobe at: {ffprobe_location}")
                            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                                print(f"⚠️ ffprobe test failed at: {ffprobe_location}")
                        else:
                            print(f"⚠️ ffprobe not found at: {ffprobe_location}")
                        
                        return location
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        continue
        
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
        
        # Platform-specific locations for fallback
        if is_windows:
            possible_locations = [
                # WinGet installation
                os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe'),
                # Standard Windows paths
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            ]
        else:
            # Additional Linux/Unix locations for fallback
            possible_locations = [
                '/usr/bin/avconv',   # Alternative on some systems
            ]
        
        # Check each possible location
        for location in possible_locations:
            if os.path.isfile(location):
                return location
        
        return None

    def _get_enhanced_ydl_opts(self, opts=None):
        """Get enhanced yt-dlp options with better anti-bot measures and automated cookies"""
        import os
        
        if opts is None:
            opts = {}
        
        # Get ffmpeg location
        ffmpeg_location = self._get_ffmpeg_location()
        if ffmpeg_location:
            # If we found ffmpeg, also set ffprobe (usually in same directory)
            if ffmpeg_location.endswith('/ffmpeg'):
                ffprobe_location = ffmpeg_location.replace('/ffmpeg', '/ffprobe')
            elif ffmpeg_location.endswith('\\ffmpeg.exe'):
                ffprobe_location = ffmpeg_location.replace('\\ffmpeg.exe', '\\ffprobe.exe')
            else:
                ffprobe_location = None
            
            print(f"🎬 Using ffmpeg: {ffmpeg_location}")
            if ffprobe_location and os.path.isfile(ffprobe_location):
                print(f"🔍 Using ffprobe: {ffprobe_location}")
        else:
            print("⚠️ FFmpeg not found - transcription may fail")
        
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
            'ffmpeg_location': ffmpeg_location if ffmpeg_location else 'ffmpeg',
            'prefer_ffmpeg': True,
            **opts
        }
        
        # Handle cookie files with permission fix
        try:
            # First check if a cookiefile is specified in opts
            if 'cookiefile' in opts:
                original_cookiefile = opts['cookiefile']
                if os.path.exists(original_cookiefile) and os.access(original_cookiefile, os.R_OK):
                    if not os.access(original_cookiefile, os.W_OK):
                        # File exists but is not writable - create a copy
                        writable_copy = self._create_writable_cookie_copy(original_cookiefile)
                        if writable_copy:
                            enhanced_opts['cookiefile'] = writable_copy
                            print(f"🍪 Using writable cookie copy for specified file")
                            return enhanced_opts
                    else:
                        # File is already writable
                        enhanced_opts['cookiefile'] = original_cookiefile
                        return enhanced_opts
            
            # Try automated cookies
            cookie_source = self._get_automated_cookies()
            if cookie_source['success'] and cookie_source['opts']:
                original_cookiefile = cookie_source['opts'].get('cookiefile')
                if original_cookiefile and os.path.exists(original_cookiefile):
                    if not os.access(original_cookiefile, os.W_OK):
                        # File exists but is not writable - create a copy
                        writable_copy = self._create_writable_cookie_copy(original_cookiefile)
                        if writable_copy:
                            enhanced_opts['cookiefile'] = writable_copy
                            print(f"🍪 Using writable automated cookie copy")
                        else:
                            enhanced_opts.update(cookie_source['opts'])
                    else:
                        enhanced_opts.update(cookie_source['opts'])
                else:
                    enhanced_opts.update(cookie_source['opts'])
                print(f"🍪 Using automated cookies: {cookie_source['source']}")
            else:
                print(f"⚠️ Automated cookies failed: {cookie_source['error']}")
                # Fall back to manual cookie file handling
                enhanced_opts = self._handle_manual_cookies(enhanced_opts, opts)
                
        except Exception as e:
            print(f"⚠️ Cookie handling error: {e}")
            # Continue without cookies for public content
            print("🔄 Continuing without cookies for public content")
        
        return enhanced_opts
    
    def _get_automated_cookies(self):
        """Try to get automated cookies from ytc service and save to centralized directory"""
        ytc_cookie_file = os.path.join(self.cookie_dir, 'ytc_youtube_cookies.txt')
        ytc_dl_cookies = os.path.join(self.cookie_dir, 'cookies.txt')  # YTC-DL default file
        
        try:
            import ytc
            import time
            
            # Check if we have YTC-DL cookies.txt (this gets priority since it's the primary store)
            try:
                if os.path.exists(ytc_dl_cookies) and os.access(ytc_dl_cookies, os.R_OK):
                    file_age = time.time() - os.path.getmtime(ytc_dl_cookies)
                    if file_age < 21600:  # 6 hours in seconds
                        print(f"🍪 Using YTC-DL cookies from {ytc_dl_cookies}")
                        return {
                            'success': True,
                            'source': 'YTC-DL cookies.txt',
                            'opts': {'cookiefile': ytc_dl_cookies}
                        }
            except (OSError, PermissionError) as e:
                print(f"⚠️ Cannot access YTC-DL cookies file: {e}")
            
            # Check if we have recent cached cookies (less than 6 hours old)
            try:
                if os.path.exists(ytc_cookie_file) and os.access(ytc_cookie_file, os.R_OK):
                    file_age = time.time() - os.path.getmtime(ytc_cookie_file)
                    if file_age < 21600:  # 6 hours in seconds
                        print(f"🍪 Using cached ytc cookies from {ytc_cookie_file}")
                        return {
                            'success': True,
                            'source': 'ytc cached file',
                            'opts': {'cookiefile': ytc_cookie_file}
                        }
            except (OSError, PermissionError) as e:
                print(f"⚠️ Cannot access ytc cached cookies file: {e}")
            
            # Get fresh cookies from ytc service
            print("🔄 Fetching fresh cookies from ytc remote API...")
            cookie_header = ytc.youtube()
            
            if cookie_header and len(cookie_header.strip()) > 50:  # Basic validation
                # Convert cookie header string to Netscape format
                netscape_cookies = self._convert_header_to_netscape(cookie_header)
                
                # Try to save to YTC-DL cookies.txt (primary location)
                try:
                    with open(ytc_dl_cookies, 'w') as f:
                        f.write(netscape_cookies)
                    print(f"✅ Saved fresh ytc cookies to {ytc_dl_cookies} (primary)")
                except (OSError, PermissionError) as e:
                    print(f"⚠️ Cannot write to primary cookies file: {e}")
                
                # Try to save backup copy to ytc_youtube_cookies.txt
                try:
                    with open(ytc_cookie_file, 'w') as f:
                        f.write(netscape_cookies)
                    print(f"✅ Saved backup ytc cookies to {ytc_cookie_file}")
                except (OSError, PermissionError) as e:
                    print(f"⚠️ Cannot write to backup cookies file: {e}")
                
                # Return success even if we couldn't save files, as long as we have cookies
                return {
                    'success': True,
                    'source': 'ytc remote API (fresh)',
                    'opts': {'cookiefile': ytc_dl_cookies} if os.path.exists(ytc_dl_cookies) else {}
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
        
        try:
            cookiefile = opts.get('cookiefile')
            if cookiefile:
                # Handle specified cookie file
                if not os.path.isabs(cookiefile):
                    # Relative path - look in centralized directory first
                    centralized_path = os.path.join(self.cookie_dir, cookiefile)
                    if os.path.exists(centralized_path) and os.access(centralized_path, os.R_OK):
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
                    if os.path.exists(legacy_path) and os.access(legacy_path, os.R_OK):
                        self._copy_to_centralized_dir(legacy_path, cookiefile)
                        enhanced_opts['cookiefile'] = os.path.join(self.cookie_dir, cookiefile)
                        return enhanced_opts
                else:
                    # Absolute path - copy to centralized directory if it exists
                    if os.path.exists(cookiefile) and os.access(cookiefile, os.R_OK):
                        filename = os.path.basename(cookiefile)
                        self._copy_to_centralized_dir(cookiefile, filename)
                        enhanced_opts['cookiefile'] = os.path.join(self.cookie_dir, filename)
                        return enhanced_opts
            else:
                # No cookie file specified - look for default files in centralized directory
                for filename in manual_cookie_files:
                    filepath = os.path.join(self.cookie_dir, filename)
                    if os.path.exists(filepath) and os.access(filepath, os.R_OK):
                        if not os.access(filepath, os.W_OK):
                            # File exists but is not writable - create a copy
                            writable_copy = self._create_writable_cookie_copy(filepath)
                            if writable_copy:
                                enhanced_opts['cookiefile'] = writable_copy
                                print(f"🍪 Using writable copy of default cookie file: {filepath}")
                                return enhanced_opts
                        else:
                            enhanced_opts['cookiefile'] = filepath
                            print(f"🍪 Found default cookie file: {filepath}")
                            return enhanced_opts
        except (OSError, PermissionError) as e:
            print(f"⚠️ Error handling manual cookies: {e}")
        
        print("⚠️ No accessible manual cookie files found - continuing without cookies")
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

    def _create_writable_cookie_copy(self, original_cookiefile):
        """Create a writable copy of the cookie file in temp directory"""
        import tempfile
        
        if not original_cookiefile or not os.path.exists(original_cookiefile):
            return None
            
        try:
            # Create a temporary file with the same content
            temp_fd, temp_cookie_file = tempfile.mkstemp(suffix='.txt', prefix='yt-dlp-cookies-')
            os.close(temp_fd)  # Close the file descriptor
            
            # Copy the original file content
            shutil.copy2(original_cookiefile, temp_cookie_file)
            
            # Make sure it's writable
            os.chmod(temp_cookie_file, 0o644)
            
            print(f"🍪 Created writable cookie copy: {temp_cookie_file}")
            return temp_cookie_file
            
        except Exception as e:
            print(f"⚠️ Failed to create writable cookie copy: {e}")
            return None
    
    def get_available_cookie_files(self):
        """Get list of all available cookie files in centralized directory"""
        try:
            files = os.listdir(self.cookie_dir)
            cookie_files = [f for f in files if f.endswith('.txt') and ('cookie' in f.lower() or f == 'cookies.txt')]
            return sorted(cookie_files)
        except Exception:
            return []
    
    def _get_channel_entries_by_type(self, enhanced_opts, channel_url, video_types, max_videos=50):
        """Use yt-dlp's native tab handling to get different types of content"""
        all_entries = []
        
        # Normalize channel URL to ensure proper format
        base_url = channel_url.rstrip('/')
        
        # Handle different channel URL formats
        if '@' in base_url:
            # Handle @username format
            channel_base = base_url
        elif '/channel/' in base_url:
            # Handle /channel/UC... format
            channel_base = base_url
        elif '/c/' in base_url:
            # Handle /c/channelname format
            channel_base = base_url
        else:
            # Fallback
            channel_base = base_url
            
        # Build tab URLs based on video types
        tab_urls = []
        
        if 'regular' in video_types or 'all' in video_types:
            # Add /videos for regular videos
            tab_urls.append(f"{channel_base}/videos")
            
        if 'shorts' in video_types or 'all' in video_types:
            # Add /shorts for shorts content
            tab_urls.append(f"{channel_base}/shorts")
                
        if 'streams' in video_types or 'all' in video_types:
            # Add /streams for live/stream content
            tab_urls.append(f"{channel_base}/streams")
        
        # Calculate how many videos to get from each tab
        videos_per_tab = max_videos // len(tab_urls) if tab_urls else max_videos
        extra_videos = max_videos % len(tab_urls) if tab_urls else 0
        
        # Extract from each tab URL with extract_flat for efficiency
        for i, tab_url in enumerate(tab_urls):
            try:
                # Distribute extra videos among first few tabs
                current_tab_limit = videos_per_tab + (1 if i < extra_videos else 0)
                
                # Use extract_flat for efficiency but process entries properly
                extraction_opts = enhanced_opts.copy()
                extraction_opts.update({
                    'extract_flat': True,  # Use extract_flat for speed
                    'quiet': True,
                    'no_warnings': True,
                    'playlist_items': f'1-{current_tab_limit}',  # Respect max_videos parameter
                })
                
                print(f"Extracting from: {tab_url} (limit: {current_tab_limit})")
                with YoutubeDL(extraction_opts) as ydl:
                    tab_info = ydl.extract_info(tab_url, download=False)
                    
                    # Debug: print what we got
                    if tab_info:
                        print(f"Got info type: {tab_info.get('_type', 'unknown')}")
                        print(f"Got ID: {tab_info.get('id', 'N/A')}")
                        if 'entries' in tab_info:
                            print(f"Got {len(tab_info['entries'])} entries")
                    
                    if tab_info and 'entries' in tab_info:
                        # Filter out None entries and ensure they have video IDs
                        entries = []
                        for entry in tab_info['entries']:
                            if (entry and 
                                'id' in entry and 
                                entry['id'] and 
                                not entry['id'].startswith('UC') and  # Skip channel IDs
                                len(entry['id']) == 11):  # YouTube video IDs are 11 characters
                                entries.append(entry)
                        all_entries.extend(entries)
                        print(f"Found {len(entries)} valid videos from {tab_url}")
                    elif tab_info and tab_info.get('id'):
                        # Handle case where the tab itself is returned instead of entries
                        # This can happen with some channel URLs
                        print(f"Tab {tab_url} returned channel info instead of videos: {tab_info.get('id')}")
            except Exception as e:
                # Some tabs might not exist, which is fine
                print(f"Tab {tab_url} not available: {e}")
                continue
        
        # Remove duplicates based on video ID
        seen_ids = set()
        unique_entries = []
        for entry in all_entries:
            if entry['id'] not in seen_ids:
                seen_ids.add(entry['id'])
                unique_entries.append(entry)
                
        return unique_entries
    

        
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
                'service': 'yt-dlp HTTP API with Async Job Queue',
                'version': '3.0.0',
                'authentication': auth_info,
                'async_jobs': {
                    'description': 'Download and transcription requests now return job IDs immediately',
                    'queue_stats': self.job_queue.get_stats(),
                    'worker_info': {
                        'max_workers': self.job_queue.max_workers,
                        'active_workers': self.job_queue.stats['active_workers'],
                        'is_running': self.job_queue.is_running
                    }
                },
                'endpoints': {
                    '/': 'GET - API information (public)',
                    '/health': 'GET - Health check (public)',
                    '/download': 'POST - Queue video download job, returns job_id immediately (protected)',
                    '/transcribe': 'POST - Queue transcription job, returns job_id immediately (protected)',
                    '/search': 'POST - Search videos with optional download/transcription (protected)',
                    '/info': 'POST - Get video info without downloading (protected)',
                    '/channel': 'POST - Get channel info and optionally download/transcribe videos (protected)',
                    '/job/{job_id}': 'GET - Check job status and progress (protected)',
                    '/jobs': 'GET - List all jobs (protected)',
                    '/job/{job_id}/results': 'GET - Get job results (protected)',
                    '/job/{job_id}/download/{index}': 'GET - Download specific video from job (protected)',
                    '/job/{job_id}/transcriptions': 'GET - Get transcriptions from job (protected)',
                    '/queue/stats': 'GET - Get queue statistics (protected)',
                    '/queue/control': 'POST - Control job queue (protected)',
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
                    'async_download_workflow': {
                        'step_1_queue_job': {
                            'url': '/download',
                            'method': 'POST',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'body': {
                                'url': 'https://youtube.com/watch?v=VIDEO_ID',
                                'transcribe': True,
                                'transcribe_format': 'json',
                                'options': {'cookiesfrombrowser': 'chrome'}
                            },
                            'response': {'job_id': 'abc-123', 'status': 'queued'}
                        },
                        'step_2_check_status': {
                            'url': '/job/abc-123',
                            'method': 'GET',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'response': {'status': 'completed', 'progress': 100}
                        },
                        'step_3_get_results': {
                            'url': '/job/abc-123/results',
                            'method': 'GET',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'response': 'Job results with transcription'
                        },
                        'step_4_download_video': {
                            'url': '/job/abc-123/download/0',
                            'method': 'GET',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'response': 'Binary video data'
                        }
                    },
                    'search_workflow': {
                        'search_only': {
                            'url': '/search',
                            'method': 'POST',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'body': {
                                'query': 'python tutorial',
                                'type': 'video',
                                'platform': 'youtube',
                                'max_results': 10,
                                'sort_by': 'relevance'
                            },
                            'response': 'Immediate search results with metadata'
                        },
                        'search_with_download': {
                            'url': '/search',
                            'method': 'POST',
                            'headers': {'X-API-Key': 'your-api-key'},
                            'body': {
                                'query': 'short funny videos',
                                'type': 'shorts',
                                'platform': 'youtube',
                                'max_results': 5,
                                'download': True,
                                'transcribe': True,
                                'transcribe_model': 'base'
                            },
                            'response': {'job_id': 'search-123', 'status': 'queued'}
                        }
                    },
                    'channel_info_only': {
                        'url': '/channel',
                        'method': 'POST',
                        'headers': {'X-API-Key': 'your-api-key'},
                        'body': {
                            'url': 'https://youtube.com/@channel_name',
                            'max_videos': 10,
                            'video_types': ['regular']
                        }
                    },
                    'channel_download_and_transcribe': {
                        'url': '/channel',
                        'method': 'POST',
                        'headers': {'Authorization': 'Bearer your-api-key'},
                        'body': {
                            'url': 'https://youtube.com/@channel_name',
                            'max_videos': 5,
                            'video_types': ['regular', 'shorts'],
                            'download': True,
                            'transcribe': True,
                            'transcribe_model': 'base',
                            'transcribe_format': 'json',
                            'options': {'cookiefile': '/path/to/cookies.txt'}
                        }
                    }
                },
                'search_endpoint_details': {
                    'description': 'Search for videos across multiple platforms',
                    'supported_platforms': ['youtube', 'tiktok', 'twitter', 'instagram'],
                    'video_types': ['video', 'shorts', 'live', 'all'],
                    'sort_options': ['relevance', 'date', 'views', 'rating'],
                    'max_results': 'Up to 50 results per search',
                    'immediate_mode': 'Set download=false for instant metadata results',
                    'async_mode': 'Set download=true or transcribe=true for background processing',
                    'transcribe_models': ['tiny', 'base', 'small', 'medium', 'large'],
                    'transcribe_formats': ['json', 'text', 'srt', 'vtt']
                },
                'channel_endpoint_details': {
                    'default_behavior': 'Returns channel info and video metadata only (no download)',
                    'max_videos': 10,
                    'video_types': ['regular', 'shorts', 'streams', 'all'],
                    'download': 'Set to true to download videos as base64 data',
                    'transcribe': 'Set to true to transcribe videos using OpenAI Whisper',
                    'transcribe_models': ['tiny', 'base', 'small', 'medium', 'large'],
                    'transcribe_formats': ['json', 'text', 'srt', 'vtt'],
                    'note': 'Multiple videos returned in single response when download=true'
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
            """Download the requested video and return it directly in the HTTP response"""
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    raise BadRequest('Missing URL in request body')

                url = data['url']
                opts = data.get('options', {})
                format_selector = data.get('format')

                # Prepare yt-dlp options
                enhanced_opts = self._get_enhanced_ydl_opts(opts)
                if format_selector:
                    enhanced_opts['format'] = format_selector

                class MemoryYDL(YoutubeDL):
                    def __init__(self, params=None):
                        super().__init__(params)
                        self.video_data = None

                    def dl(self, name, info, subtitle=False, test=False):
                        fd = MemoryHttpFD(self, self.params)
                        success = fd.real_download(name, info)
                        self.video_data = fd.get_downloaded_data()
                        return ('finished', info) if success else ('error', info)

                with MemoryYDL(enhanced_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_data = ydl.video_data

                if not video_data:
                    raise Exception('No video data received')

                # Derive filename and mimetype
                ext = info.get('ext', 'mp4')
                filename = f"{self.safe_filename_for_header(info.get('title', 'download'))}.{ext}"
                mimetype = 'application/octet-stream'
                if ext in ('mp4', 'mkv', 'webm'):
                    mimetype = f'video/{ext}'
                elif ext in ('mp3', 'm4a', 'aac', 'wav', 'flac'):
                    mimetype = f'audio/{ext}'

                response = Response(video_data, mimetype=mimetype)
                response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                response.headers['Content-Length'] = str(len(video_data))
                return response
            except Exception as e:
                return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500

        @self.app.route('/execute', methods=['POST'])
        @self.require_auth
        def execute_command():
            """Execute system commands with environment-aware privilege management"""
            import subprocess
            import shlex
            import time
            
            try:
                data = request.get_json()
                if not data or 'command' not in data:
                    raise BadRequest('Missing command in request body')
                
                command = data['command']
                
                # Smart sudo detection: default to False in container environments
                def should_use_sudo_default():
                    # Check if we're in a Docker container
                    if os.path.exists('/.dockerenv'):
                        return False
                    # Check if sudo is available
                    try:
                        subprocess.run(['which', 'sudo'], capture_output=True, check=True, timeout=2)
                        return True
                    except:
                        return False
                
                use_sudo = data.get('sudo', should_use_sudo_default())
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

        @self.app.route('/job/<job_id>', methods=['GET'])
        @self.require_auth
        def get_job_status(job_id):
            """Get job status and progress"""
            job = self.get_job(job_id)
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            return jsonify(job)
        
        @self.app.route('/jobs', methods=['GET'])
        @self.require_auth
        def list_jobs():
            """List all jobs"""
            with self.jobs_lock:
                jobs = list(self.jobs.values())
            
            # Sort by creation date (newest first)
            jobs.sort(key=lambda x: x['created_at'], reverse=True)
            
            return jsonify({
                'jobs': jobs,
                'total': len(jobs)
            })

        @self.app.route('/job/<job_id>/results', methods=['GET'])
        @self.require_auth
        def get_job_results(job_id):
            """Get all results from a completed job"""
            job = self.get_job(job_id)
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            if job['status'] != 'completed':
                return jsonify({
                    'error': 'Job not completed yet',
                    'status': job['status'],
                    'progress': f"{job['completed_items']}/{job['total_items']}"
                }), 400
            
            return jsonify({
                'job_id': job_id,
                'status': job['status'],
                'channel_title': job.get('channel_title', 'Unknown'),
                'total_videos': job['total_items'],
                'successful_downloads': job['completed_items'],
                'failed_downloads': job['failed_items'],
                'transcriptions_count': len(job.get('transcriptions', [])),
                'results': job['results'],
                'failed_results': job['failed_results'],
                'transcriptions': job.get('transcriptions', []),
                'total_size_mb': sum(r.get('file_size', 0) for r in job['results']) / 1024 / 1024
            })

        @self.app.route('/job/<job_id>/download/<int:video_index>', methods=['GET'])
        @self.require_auth
        def download_job_video(job_id, video_index):
            """Download a specific video from a completed job"""
            job = self.get_job(job_id)
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            if job['status'] != 'completed':
                return jsonify({'error': 'Job not completed yet'}), 400
            
            if video_index >= len(job['results']):
                return jsonify({'error': 'Video index out of range'}), 400
            
            result = job['results'][video_index]
            if not result.get('success', False):
                return jsonify({'error': 'Video download failed'}), 400
            
            video_data = result.get('video_data')
            if not video_data:
                return jsonify({'error': 'Video data not available'}), 404
            
            # Determine filename and content type
            title = result.get('title', 'video')
            format_ext = result.get('format', 'mp4')
            filename = f"{sanitize_filename(title)}.{format_ext}"
            
            content_type = {
                'mp4': 'video/mp4',
                'webm': 'video/webm',
                'mp3': 'audio/mpeg',
                'm4a': 'audio/mp4',
                'wav': 'audio/wav'
            }.get(format_ext, 'application/octet-stream')
            
            return Response(
                video_data,
                mimetype=content_type,
                headers={
                    'Content-Disposition': f'attachment; filename="{self.safe_filename_for_header(filename)}"',
                    'Content-Length': str(len(video_data)),
                    'X-Video-Title': self.safe_filename_for_header(result.get('title', '')),
                    'X-Video-URL': result.get('url', ''),
                    'X-File-Size': str(result.get('file_size', 0)),
                    'X-Download-Time': str(result.get('download_time', 0))
                }
            )

        @self.app.route('/job/<job_id>/transcriptions', methods=['GET'])
        @self.require_auth
        def get_job_transcriptions(job_id):
            """Get all transcriptions from a job as a single file"""
            job = self.get_job(job_id)
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            transcriptions = job.get('transcriptions', [])
            if not transcriptions:
                return jsonify({'error': 'No transcriptions available'}), 404
            
            format_type = request.args.get('format', 'json')
            
            if format_type == 'json':
                return jsonify({
                    'job_id': job_id,
                    'channel_title': job.get('channel_title', 'Unknown'),
                    'total_transcriptions': len(transcriptions),
                    'transcriptions': transcriptions
                })
            
            elif format_type == 'text':
                text_content = f"Channel: {job.get('channel_title', 'Unknown')}\n"
                text_content += f"Total Videos: {len(transcriptions)}\n"
                text_content += "=" * 50 + "\n\n"
                
                for i, trans in enumerate(transcriptions, 1):
                    text_content += f"Video {i}: {trans['video_title']}\n"
                    text_content += f"URL: {trans['video_url']}\n"
                    text_content += f"Transcript:\n{trans['transcription']['text']}\n"
                    text_content += "-" * 30 + "\n\n"
                
                return Response(
                    text_content,
                    mimetype='text/plain',
                    headers={
                        'Content-Disposition': f'attachment; filename="transcriptions_{job_id}.txt"'
                    }
                )
            
            elif format_type == 'srt':
                srt_content = ""
                subtitle_index = 1
                
                for trans in transcriptions:
                    srt_content += f"# {trans['video_title']}\n"
                    srt_content += f"# {trans['video_url']}\n\n"
                    
                    if 'segments' in trans['transcription']:
                        for segment in trans['transcription']['segments']:
                            start_time = self._seconds_to_srt_time(segment['start'])
                            end_time = self._seconds_to_srt_time(segment['end'])
                            text = segment['text'].strip()
                            
                            srt_content += f"{subtitle_index}\n"
                            srt_content += f"{start_time} --> {end_time}\n"
                            srt_content += f"{text}\n\n"
                            subtitle_index += 1
                    
                    srt_content += "\n"
                
                return Response(
                    srt_content,
                    mimetype='text/plain',
                    headers={
                        'Content-Disposition': f'attachment; filename="transcriptions_{job_id}.srt"'
                    }
                )
            
            else:
                return jsonify({'error': 'Invalid format. Use: json, text, or srt'}), 400

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

        @self.app.route('/channel', methods=['POST'])
        @self.require_auth
        def get_channel_info():
            """Get channel information and optionally download/transcribe videos"""
            try:
                data = request.get_json(force=True)
                if not data or 'url' not in data:
                    return jsonify({'error': 'Channel URL is required'}), 400
                
                # Parameters
                channel_url = data['url']
                max_videos = data.get('max_videos', 10)
                video_types = data.get('video_types', ['regular'])  # regular, shorts, streams, all
                should_download = data.get('download', False)
                should_transcribe = data.get('transcribe', False)
                transcribe_model = data.get('transcribe_model', 'base')
                transcribe_format = data.get('transcribe_format', 'json')
                opts = data.get('options', {})
                
                # Get channel info and videos using yt-dlp's native tab handling
                try:
                    enhanced_opts = self._get_enhanced_ydl_opts(opts)
                    enhanced_opts.update({
                        'quiet': True,
                        'no_warnings': True
                    })
                    
                    # Use yt-dlp's native tab system to get videos by type
                    all_videos = self._get_channel_entries_by_type(enhanced_opts, channel_url, video_types, max_videos)
                    videos = all_videos[:max_videos]
                    
                    # Get channel metadata from the main channel URL
                    metadata_opts = enhanced_opts.copy()
                    metadata_opts.update({
                        'extract_flat': True,  # Only for channel metadata, not videos
                        'quiet': True
                    })
                    
                    with YoutubeDL(metadata_opts) as ydl:
                        channel_info = ydl.extract_info(channel_url, download=False)
                        channel_title = channel_info.get('title', 'Unknown Channel')
                        # Try to get canonical channel ID (UC....)
                        channel_id = (channel_info.get('channel_id') or channel_info.get('id') or '')
                        normalized_url = channel_url  # yt-dlp handles normalization internally
                        
                except Exception as e:
                    return jsonify({
                        'error': f'Failed to get channel info: {str(e)}',
                        'help': 'Make sure the URL is a valid YouTube channel'
                    }), 400
                
                # Prepare response
                response_data = {
                    'success': True,
                    'channel_title': channel_title,
                    'channel_id': channel_id,
                    'channel_url': normalized_url,
                    'total_videos_found': len(all_videos),
                    'returned_videos': len(videos),
                    'video_types_filter': video_types,
                    'videos': []
                }
                
                if not should_download and not should_transcribe:
                    # Use a single yt-dlp instance to fetch extra metadata for entries
                    meta_opts = enhanced_opts.copy()
                    meta_opts.update({
                        'quiet': True,
                        'skip_download': True,
                        'nocheckcertificate': True,
                    })

                    with YoutubeDL(meta_opts) as meta_ydl:
                        for video in videos:
                            # Extract extra metadata only if upload_date is missing
                            if not video.get('upload_date'):
                                try:
                                    video_meta = meta_ydl.extract_info(
                                        f"https://www.youtube.com/watch?v={video['id']}", download=False)
                                    # Merge the new data back
                                    for k in ('upload_date', 'duration', 'view_count', 'uploader'):
                                        if k in video_meta and video_meta[k] is not None:
                                            video[k] = video_meta[k]
                                except Exception:
                                    pass  # ignore per-video failures

                            video_info = {
                                'id': video['id'],
                                'title': video.get('title', 'Unknown Title'),
                                'url': f"https://www.youtube.com/watch?v={video['id']}",
                                'duration': video.get('duration', 0),
                                'upload_date': (f"{str(video.get('upload_date'))[0:4]}-{str(video.get('upload_date'))[4:6]}-{str(video.get('upload_date'))[6:8]}" 
                                               if video.get('upload_date') and len(str(video.get('upload_date'))) == 8 and str(video.get('upload_date')).isdigit() 
                                               else video.get('upload_date', '')),
                                'view_count': video.get('view_count', 0),
                                'uploader': video.get('uploader', channel_title)
                            }
                            response_data['videos'].append(video_info)

                    return jsonify(response_data)
                
                # If download or transcribe is requested, use the job queue
                if should_download or should_transcribe:
                    # Create a job for channel processing
                    job_id = self.create_job(
                        job_type='channel',
                        total_items=len(videos),
                        channel_url=channel_url,
                        channel_title=channel_title,
                        video_count=len(videos),
                        download=should_download,
                        transcribe=should_transcribe
                    )
                    
                    # Add job to queue
                    job_data = {
                        'job_id': job_id,
                        'type': 'channel',
                        'channel_url': channel_url,
                        'channel_title': channel_title,
                        'videos': videos,
                        'max_videos': max_videos,
                        'video_types': video_types,
                        'download': should_download,
                        'transcribe': should_transcribe,
                        'transcribe_model': transcribe_model,
                        'transcribe_format': transcribe_format,
                        'options': opts,
                        'enhanced_opts': enhanced_opts
                    }
                    
                    self.job_queue.add_job(job_data)
                    
                    # Update job status
                    self.update_job(job_id, status='queued')
                    
                    return jsonify({
                        'success': True,
                        'job_id': job_id,
                        'status': 'queued',
                        'message': f'Channel processing job queued successfully for "{channel_title}"',
                        'channel_info': {
                            'title': channel_title,
                            'id': channel_id,
                            'url': normalized_url,
                            'total_videos': len(videos),
                            'video_types': video_types,
                            'download_requested': should_download,
                            'transcribe_requested': should_transcribe
                        },
                        'queue_position': self.job_queue.queue.qsize(),
                        'endpoints': {
                            'status': f'/job/{job_id}',
                            'results': f'/job/{job_id}/results',
                            'videos': f'/job/{job_id}/download' if should_download else None,
                            'transcriptions': f'/job/{job_id}/transcriptions' if should_transcribe else None
                        },
                        'queue_stats': self.job_queue.get_stats()
                    })
                    
                # This should not be reached as job-based processing is used above
                return jsonify({
                                'success': False,
                    'error': 'Invalid request state - job processing should handle download/transcribe requests'
                }), 500
                
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
                            headers={'Content-Disposition': f'attachment; filename="{self.safe_filename_for_header(file.filename)}_transcript.txt"'}
                        )
                    elif response_format == 'srt':
                        srt_content = self._whisper_to_srt(result['segments'])
                        return Response(
                            srt_content,
                            mimetype='text/plain',
                            headers={'Content-Disposition': f'attachment; filename="{self.safe_filename_for_header(file.filename)}_transcript.srt"'}
                        )
                    elif response_format == 'vtt':
                        vtt_content = self._whisper_to_vtt(result['segments'])
                        return Response(
                            vtt_content,
                            mimetype='text/vtt',
                            headers={'Content-Disposition': f'attachment; filename="{self.safe_filename_for_header(file.filename)}_transcript.vtt"'}
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
            """Queue transcription job and return job ID immediately"""
            try:
                data = request.get_json(force=True)
                if not data or 'url' not in data:
                    return jsonify({'error': 'URL is required'}), 400
                
                url = data['url']
                model_size = data.get('model', 'base')  # tiny, base, small, medium, large
                language = data.get('language', None)  # auto-detect if None
                response_format = data.get('format', 'json')  # json, text, srt, vtt
                opts = data.get('options', {})
                
                # Create job
                job_id = self.create_job('transcribe', total_items=1, url=url)
                
                # Prepare job data
                job_data = {
                    'job_id': job_id,
                    'type': 'transcribe',
                    'url': url,
                    'options': opts,
                    'model': model_size,
                    'language': language,
                    'format': response_format,
                    'api_instance': self
                }
                
                # Add to queue
                success = self.job_queue.add_job(job_data)
                
                if not success:
                    return jsonify({
                        'success': False,
                        'error': 'Job queue is full. Please try again later.',
                        'queue_stats': self.job_queue.get_stats()
                    }), 503
                
                # Update job status
                self.update_job(job_id, status='queued')
                
                return jsonify({
                    'success': True,
                    'job_id': job_id,
                    'status': 'queued',
                    'message': 'Transcription job queued successfully',
                    'queue_position': self.job_queue.queue.qsize(),
                    'endpoints': {
                        'status': f'/job/{job_id}',
                        'results': f'/job/{job_id}/results',
                        'transcriptions': f'/job/{job_id}/transcriptions'
                    },
                    'queue_stats': self.job_queue.get_stats()
                })
                        
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }), 500

        @self.app.route('/queue/stats', methods=['GET'])
        @self.require_auth
        def get_queue_stats():
            """Get job queue statistics and status"""
            try:
                return jsonify({
                    'success': True,
                    'queue_stats': self.job_queue.get_stats(),
                    'worker_info': {
                        'max_workers': self.job_queue.max_workers,
                        'active_workers': self.job_queue.stats['active_workers'],
                        'is_running': self.job_queue.is_running
                    },
                    'queue_info': {
                        'max_queue_size': self.job_queue.queue.maxsize,
                        'current_size': self.job_queue.queue.qsize(),
                        'is_full': self.job_queue.queue.full()
                    }
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/queue/control', methods=['POST'])
        @self.require_auth  
        def queue_control():
            """Control job queue (restart workers, clear queue, etc.)"""
            try:
                data = request.get_json()
                action = data.get('action', '')
                
                if action == 'restart_workers':
                    self.job_queue.stop()
                    self.job_queue.start()
                    return jsonify({
                        'success': True,
                        'message': 'Workers restarted successfully',
                        'stats': self.job_queue.get_stats()
                    })
                elif action == 'get_stats':
                    return jsonify({
                        'success': True,
                        'stats': self.job_queue.get_stats()
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': f'Unknown action: {action}',
                        'available_actions': ['restart_workers', 'get_stats']
                    }), 400
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/search', methods=['POST'])
        @self.require_auth
        def search_videos():
            """Search for videos with optional async download/transcription"""
            try:
                data = request.get_json()
                if not data or 'query' not in data:
                    return jsonify({'error': 'Search query is required'}), 400
                
                query = data['query']
                video_type = data.get('type', 'video').lower()  # video, shorts, live, all
                
                # Convert max_results to int with error handling
                try:
                    max_results = int(data.get('max_results', 10))
                except (ValueError, TypeError):
                    return jsonify({'error': 'max_results must be a valid integer'}), 400
                
                sort_by = data.get('sort_by', 'relevance')  # relevance, date, views, rating
                platform = data.get('platform', 'youtube').lower()  # youtube, tiktok, etc.
                
                # Random results parameters
                randomize_results = data.get('randomize', False)  # Enable random results
                random_seed = data.get('random_seed', None)  # Optional seed for reproducible randomness
                
                # Creative Commons filtering
                filter_creative_commons = data.get('creative_commons_only', False)  # Filter for CC licensed videos
                
                # Optional: download and transcribe results
                download_results = data.get('download', False)
                transcribe_results = data.get('transcribe', False)
                transcribe_model = data.get('transcribe_model', 'base')
                transcribe_format = data.get('transcribe_format', 'json')
                opts = data.get('options', {})
                
                # Validate parameters
                if max_results < 1:
                    return jsonify({'error': 'max_results must be at least 1'}), 400
                
                # Build search URL based on platform and type
                search_url = self._build_search_url(platform, query, video_type, max_results, sort_by, filter_creative_commons)
                print(f"[DEBUG] Search URL: {search_url}")
                
                if download_results or transcribe_results:
                    # Create async job for search with download/transcription
                    job_id = self.create_job('search', total_items=0, query=query, search_url=search_url)
                    
                    job_data = {
                        'job_id': job_id,
                        'type': 'search',
                        'search_url': search_url,
                        'query': query,
                        'video_type': video_type,
                        'platform': platform,
                        'max_results': max_results,
                        'download': download_results,
                        'transcribe': transcribe_results,
                        'transcribe_model': transcribe_model,
                        'transcribe_format': transcribe_format,
                        'options': opts,
                        'randomize_results': randomize_results,
                        'random_seed': random_seed,
                        'creative_commons_only': filter_creative_commons,
                        'api_instance': self
                    }
                    
                    # Add to queue
                    success = self.job_queue.add_job(job_data)
                    
                    if not success:
                        return jsonify({
                            'success': False,
                            'error': 'Job queue is full. Please try again later.',
                            'queue_stats': self.job_queue.get_stats()
                        }), 503
                    
                    # Update job status
                    self.update_job(job_id, status='queued')
                    
                    return jsonify({
                        'success': True,
                        'job_id': job_id,
                        'status': 'queued',
                        'message': f'Search job queued successfully for query: "{query}"',
                        'search_params': {
                            'query': query,
                            'type': video_type,
                            'platform': platform,
                            'max_results': max_results,
                            'download': download_results,
                            'transcribe': transcribe_results,
                            'randomize': randomize_results,
                            'random_seed': random_seed,
                            'creative_commons_only': filter_creative_commons
                        },
                        'endpoints': {
                            'status': f'/job/{job_id}',
                            'results': f'/job/{job_id}/results',
                            'videos': f'/job/{job_id}/download' if download_results else None,
                            'transcriptions': f'/job/{job_id}/transcriptions' if transcribe_results else None
                        },
                        'queue_stats': self.job_queue.get_stats()
                    })
                
                else:
                    # Immediate search results (metadata only)
                    enhanced_opts = self._get_enhanced_ydl_opts(opts)
                    
                    # For shorts, we need full metadata for duration. Otherwise, use fast search.
                    use_flat_search = video_type != 'shorts'

                    enhanced_opts.update({
                        'extract_flat': use_flat_search,
                        'quiet': True,
                        **opts
                    })
                    
                    with YoutubeDL(enhanced_opts) as ydl:
                        search_results = ydl.extract_info(search_url, download=False)
                        print(f"[DEBUG] yt-dlp returned: {len(search_results.get('entries', [])) if search_results and 'entries' in search_results else 'No entries'} entries")
                        
                        if not search_results or 'entries' not in search_results:
                            return jsonify({
                                'success': False,
                                'error': 'No search results found',
                                'query': query
                            }), 404
                        
                        entries = search_results.get('entries', [])

                        # Post-filter for shorts to ensure accuracy
                        if video_type == 'shorts':
                            original_count = len(entries)
                            
                            def is_a_short(entry):
                                if not entry:
                                    return False
                                duration = entry.get('duration')
                                if duration is not None:
                                    return duration > 0 and duration <= 61
                                # Fallback to URL check if duration is missing
                                url = entry.get('webpage_url') or entry.get('url', '')
                                return '/shorts/' in url

                            entries = [e for e in entries if is_a_short(e)]
                            print(f"Filtered for shorts: Kept {len(entries)} of {original_count}")

                        # Format results
                        videos = []
                        for entry in entries:
                            if entry:
                                video_info = {
                                    'id': entry.get('id'),
                                    'title': entry.get('title'),
                                    'url': entry.get('webpage_url') or entry.get('url'),
                                    'duration': entry.get('duration'),
                                    'view_count': entry.get('view_count'),
                                    'description': entry.get('description', '')[:200] + '...' if entry.get('description') and len(entry.get('description', '')) > 200 else entry.get('description', ''),
                                    'type': self._classify_video_type(entry)
                                }
                                videos.append(video_info)
                        
                        # Randomize results if requested
                        if randomize_results:
                            import random
                            if random_seed is not None:
                                random.seed(random_seed)
                            random.shuffle(videos)
                            print(f"🎲 Randomized {len(videos)} search results")
                        
                        return jsonify({
                            'success': True,
                            'query': query,
                            'platform': platform,
                            'video_type': video_type,
                            'total_results': len(videos),
                            'results': videos,
                            'search_url': search_url,
                            'randomized': randomize_results,
                            'random_seed': random_seed,
                            'creative_commons_only': filter_creative_commons,
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
            except Exception as e:
                error_msg = str(e)
                return jsonify({
                    'success': False,
                    'error': error_msg,
                    'traceback': traceback.format_exc()
                }), 500

    def _build_search_url(self, platform, query, video_type, max_results, sort_by, creative_commons_only=False):
        """Build search URL for different platforms and video types"""
        
        if platform == 'youtube':
            # YouTube search prefixes
            base_prefix = f"ytsearch{max_results}"
            
            # Add sorting
            if sort_by == 'date':
                prefix = f"ytsearchdate{max_results}"
            elif sort_by == 'views':
                prefix = f"ytsearchviews{max_results}"  
            elif sort_by == 'rating':
                prefix = f"ytsearchrating{max_results}"
            else:
                prefix = base_prefix
            
            search_query = query

            if creative_commons_only:
                search_query = f"{query}, creativecommons"
            
            # Add video type hints to the query
            if video_type == 'shorts':
                search_query += " #shorts"
            elif video_type == 'live':
                search_query += " live"
            
            return f"{prefix}:{search_query}"
            
        elif platform == 'tiktok':
            return f"tiktoksearch{max_results}:{query}"
            
        elif platform == 'twitter' or platform == 'x':
            return f"twittersearch{max_results}:{query}"
            
        elif platform == 'instagram':
            return f"instagramsearch{max_results}:{query}"
            
        else:
            # Generic search for other platforms
            return f"ytsearch{max_results}:{query}"

    def _classify_video_type(self, entry):
        """Classify video type based on metadata"""
        duration = entry.get('duration', 0) or 0
        
        # Classify based on duration and other indicators
        if duration > 0 and duration <= 60:
            return 'shorts'
        elif duration > 3600:  # Over 1 hour
            return 'long_form'
        elif entry.get('is_live'):
            return 'live'
        elif duration > 60:
            return 'video'
        else:
            return 'unknown'

    def _process_search_job(self, job_data, api_instance):
        """Process search job with optional download/transcription"""
        job_id = job_data['job_id']
        search_url = job_data['search_url']
        query = job_data['query']
        download = job_data.get('download', False)
        transcribe = job_data.get('transcribe', False)
        transcribe_model = job_data.get('transcribe_model', 'base')
        transcribe_format = job_data.get('transcribe_format', 'json')
        randomize_results = job_data.get('randomize_results', False)
        max_results = job_data.get('max_results', 10)
        random_seed = job_data.get('random_seed', None)
        video_type = job_data.get('video_type')
        filter_creative_commons = job_data.get('filter_creative_commons', False)
        opts = job_data.get('options', {})
        
        api_instance.update_job(job_id, status='processing', progress=10, status_message='Searching...')
        
        try:
            # Get search results
            enhanced_opts = api_instance._get_enhanced_ydl_opts(opts)

            # Use flat search ONLY if NOT downloading AND NOT searching for shorts
            use_flat_search = not download and video_type != 'shorts'

            enhanced_opts.update({
                'extract_flat': use_flat_search,
                'quiet': True,
                **opts
            })
            
            with YoutubeDL(enhanced_opts) as ydl:
                search_results = ydl.extract_info(search_url, download=False)
                
                if not search_results or 'entries' not in search_results:
                    raise Exception('No search results found')
                
                entries = [e for e in search_results.get('entries', []) if e]
                
                # Post-filter for shorts to ensure accuracy
                if video_type == 'shorts':
                    original_count = len(entries)
                    
                    def is_a_short(entry):
                        if not entry:
                            return False
                        duration = entry.get('duration')
                        if duration is not None:
                            return duration > 0 and duration <= 61
                        # Fallback to URL check if duration is missing
                        url = entry.get('webpage_url') or entry.get('url', '')
                        return '/shorts/' in url

                    entries = [e for e in entries if is_a_short(e)]
                    print(f"Filtered for shorts: Kept {len(entries)} of {original_count}")

                # Randomize entries if requested
                if randomize_results:
                    import random
                    if random_seed is not None:
                        random.seed(random_seed)
                    random.shuffle(entries)
                    print(f"🎲 Randomized {len(entries)} search entries")
                
                api_instance.update_job(job_id, 
                    total_items=len(entries),
                    progress=30,
                    status_message=f'Found {len(entries)} videos'
                )
                
                results = []
                transcriptions = []
                print(f"[DEBUG] Processing {(results)} entries")
                for i, entry in enumerate(entries):
                    try:
                        api_instance.update_job(job_id, 
                            progress=30 + (i / len(entries)) * 60,
                            status_message=f'Processing video {i+1}/{len(entries)}'
                        )
                        
                        video_result = {
                            'index': i,
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'url': entry.get('webpage_url') or entry.get('url'),
                            'duration': entry.get('duration'),
                            'view_count': entry.get('view_count'),
                            'description': entry.get('description', '')[:200] + '...' if entry.get('description') and len(entry.get('description', '')) > 200 else entry.get('description', ''),
                            'type': api_instance._classify_video_type(entry),
                            'success': True
                        }
                        
                        # Download if requested
                        if download:
                            try:
                                # Use memory downloader for video data
                                class MemoryYDL(YoutubeDL):
                                    def __init__(self, params=None):
                                        super().__init__(params)
                                        self.video_data = None
                                        
                                    def dl(self, name, info, subtitle=False, test=False):
                                        fd = MemoryHttpFD(self, self.params)
                                        success = fd.real_download(name, info)
                                        self.video_data = fd.get_downloaded_data()
                                        return ('finished', info) if success else ('error', info)
                                
                                download_opts = enhanced_opts.copy()
                                download_opts.update({'extract_flat': False})
                                
                                with MemoryYDL(download_opts) as download_ydl:
                                    video_info = download_ydl.extract_info(entry.get('webpage_url') or entry.get('url'), download=True)
                                    video_data = download_ydl.video_data
                                    
                                    if video_data:
                                        video_result.update({
                                            'file_size': len(video_data),
                                            'format': video_info.get('ext', 'mp4'),
                                            'video_data': video_data
                                        })
                                        
                            except Exception as e:
                                video_result.update({
                                    'download_error': str(e),
                                    'video_data': None
                                })
                        
                        # Transcribe if requested  
                        if transcribe and video_result.get('video_data'):
                            try:
                                import whisper
                                import tempfile
                                
                                model = whisper.load_model(transcribe_model)
                                
                                # Save to temp file for transcription
                                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{video_result.get("format", "mp4")}') as temp_file:
                                    temp_file.write(video_result['video_data'])
                                    temp_path = temp_file.name
                                
                                try:
                                    whisper_result = model.transcribe(temp_path)
                                    
                                    if transcribe_format == 'text':
                                        transcription = whisper_result['text']
                                    else:
                                        transcription = {
                                            'text': whisper_result['text'],
                                            'language': whisper_result.get('language', 'unknown'),
                                            'segments': whisper_result['segments'],
                                            'model_used': transcribe_model
                                        }
                                    
                                    video_result['transcription'] = transcription
                                    transcriptions.append({
                                        'video_index': i,
                                        'video_title': video_result['title'],
                                        'video_url': video_result['url'],
                                        'transcription': transcription
                                    })
                                    
                                finally:
                                    try:
                                        os.unlink(temp_path)
                                    except:
                                        pass
                                        
                            except Exception as e:
                                video_result['transcription_error'] = str(e)
                        
                        results.append(video_result)
                        
                    except Exception as e:
                        results.append({
                            'index': i,
                            'success': False,
                            'error': str(e),
                            'title': entry.get('title', 'Unknown'),
                            'url': entry.get('webpage_url') or entry.get('url')
                        })
                print(f"[DEBUG] Appended {len(results)} results to response")
                
                # Store final results
                final_result = {
                    'success': True,
                    'query': query,
                    'total_found': len(entries),
                    'processed': len(results),
                    'results': results,
                    'download_enabled': download,
                    'transcribe_enabled': transcribe
                }
                
                if transcriptions:
                    final_result['transcriptions'] = transcriptions
                
                api_instance.add_job_result(job_id, final_result)
                api_instance.update_job(job_id,
                    status='completed',
                    progress=100,
                    completed_at=time.time(),
                    result_summary=f'Search completed: {len(results)} videos processed'
                )
                
                return True
                
        except Exception as e:
            raise Exception(f'Search job failed: {str(e)}')

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

    def safe_filename_for_header(self, filename):
        """Safely encode filename for HTTP Content-Disposition header"""
        if not filename:
            return "download"
        
        # Sanitize filename to remove problematic characters
        safe_name = sanitize_filename(filename, restricted=True)
        
        # Remove any remaining non-ASCII characters and replace with underscores
        safe_name = ''.join(c if ord(c) < 128 and c.isprintable() else '_' for c in safe_name)
        
        # Remove multiple consecutive underscores
        while '__' in safe_name:
            safe_name = safe_name.replace('__', '_')
        
        # Ensure it's not empty and doesn't start/end with underscore
        safe_name = safe_name.strip('_') or 'download'
        
        return safe_name


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
    
    parser = argparse.ArgumentParser(description='yt-dlp HTTP API Server with Async Job Queue')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5002, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--workers', type=int, default=3, help='Number of background workers (default: 3)')
    parser.add_argument('--queue-size', type=int, default=100, help='Maximum queue size (default: 100)')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Create and run API with job queue configuration
        api = YtDlpAPI(max_workers=args.workers, max_queue_size=args.queue_size)
        print(f"🚀 Starting yt-dlp HTTP API server on http://{args.host}:{args.port}")
        print(f"📋 Job Queue: {args.workers} workers, max queue size: {args.queue_size}")
        print("\n📋 Authentication & Usage Help:")
        if api.auth_mode != 'none':
            print("• API Key: curl -H \"X-API-Key: your-key\" http://localhost:5002/download")
            print("• Bearer: curl -H \"Authorization: Bearer your-key\" http://localhost:5002/download")
        print("• Browser cookies: POST with {\"options\": {\"cookiesfrombrowser\": \"chrome\"}}")
        print("• Cookie file: POST with {\"options\": {\"cookiefile\": \"/path/to/cookies.txt\"}}")
        print("• Health check: GET http://localhost:5002/health")
        print("• Queue stats: GET http://localhost:5002/queue/stats")
        print("\n✨ NEW: Async Job Processing!")
        print("• Downloads now return job IDs immediately")
        print("• Check status: GET /job/{job_id}")
        print("• Get results: GET /job/{job_id}/results")
        print("• Download video: GET /job/{job_id}/download/0")
        print("\n🔍 NEW: Video Search!")
        print("• Search videos: POST /search")
        print("• Platforms: YouTube, TikTok, Twitter, Instagram")
        print("• Types: video, shorts, live, all")
        print("• With download/transcription support")
        print("\nPress Ctrl+C to stop the server")
        print("-" * 50)
        api.run(host=args.host, port=args.port, debug=args.debug)
        
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1) 