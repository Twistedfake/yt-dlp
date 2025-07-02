#!/usr/bin/env python3
"""
yt-dlp Channel Downloader
Complete solution for downloading YouTube channels with parallel processing,
audio conversion, transcript extraction, and smart memory management.

Usage:
    python yt_dlp_channel_downloader.py
    
Or import as module:
    from yt_dlp_channel_downloader import ChannelDownloader
    
    downloader = ChannelDownloader()
    downloader.download_channel('https://www.youtube.com/@channel/videos')
"""

import asyncio
import aiohttp
import requests
import threading
import time
import os
import psutil
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    """Result of a single download operation"""
    url: str
    title: str
    success: bool
    file_size: int = 0
    file_path: str = ""
    error: str = ""
    duration: float = 0.0
    format_downloaded: str = ""

@dataclass
class DownloadConfig:
    """Comprehensive configuration for downloads"""
    # API Settings
    api_base: str = 'http://localhost:5002'
    
    # Performance Settings
    max_workers: int = 4
    batch_size: int = 10
    max_videos: int = 50
    max_memory_percent: float = 70.0
    
    # Download Settings
    format_selector: str = 'best[height<=720][filesize<200M]'
    audio_only: bool = True
    audio_format: str = 'mp3'  # mp3, aac, wav, ogg, flac, m4a
    audio_quality: str = '192K'  # or 0-10 for VBR
    
    # Subtitle Settings
    download_subtitles: bool = False
    subtitle_languages: List[str] = field(default_factory=lambda: ['en'])
    auto_subtitles: bool = True
    
    # Retry and Rate Limiting
    retry_attempts: int = 3
    retry_delay: float = 2.0
    rate_limit_delay: float = 1.0
    batch_pause: float = 3.0
    
    # Output Settings
    output_dir: str = './downloads'
    create_channel_folder: bool = True
    sanitize_filenames: bool = True
    max_filename_length: int = 100
    
    # Advanced Settings
    use_async: bool = False
    concurrent_transcripts: bool = True
    save_video_info: bool = True
    skip_existing: bool = True

class ChannelDownloader:
    """Complete YouTube channel downloader with all features"""
    
    def __init__(self, config: DownloadConfig = None):
        self.config = config or DownloadConfig()
        self.results: List[DownloadResult] = []
        self.downloaded_count = 0
        self.failed_count = 0
        self.total_size = 0
        self.lock = threading.Lock()
        
        # Validate API connection
        self._check_api_connection()
    
    def _check_api_connection(self):
        """Check if API server is running"""
        try:
            response = requests.get(self.config.api_base, timeout=5)
            if response.status_code == 200:
                logger.info("✅ Connected to yt-dlp API server")
            else:
                logger.warning("⚠️ API server responding but may have issues")
        except requests.exceptions.ConnectionError:
            logger.error("❌ Cannot connect to API server. Start it with: python yt_dlp_api.py")
            raise ConnectionError("API server not available")
        except Exception as e:
            logger.error(f"❌ API connection error: {e}")
            raise
    
    def get_channel_info(self, channel_url: str) -> Dict:
        """Get channel information and video list"""
        logger.info(f"🔍 Fetching channel info: {channel_url}")
        
        try:
            response = requests.post(f'{self.config.api_base}/channel', json={
                'url': channel_url,
                'options': {
                    'extract_flat': True,
                    'playlist_items': f'1-{self.config.max_videos}'
                }
            }, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                channel_info = data.get('channel_info', {})
                videos = data.get('videos', [])
                
                logger.info(f"✅ Found {len(videos)} videos from '{channel_info.get('title', 'Unknown')}'")
                return {
                    'channel_info': channel_info,
                    'videos': videos,
                    'success': True
                }
            else:
                error = response.json().get('error', 'Unknown error')
                logger.error(f"❌ Failed to get channel info: {error}")
                return {'success': False, 'error': error}
                
        except Exception as e:
            logger.error(f"❌ Exception getting channel info: {e}")
            return {'success': False, 'error': str(e)}
    
    def _check_memory_usage(self) -> bool:
        """Check if memory usage is within limits"""
        memory = psutil.virtual_memory()
        if memory.percent > self.config.max_memory_percent:
            logger.warning(f"⚠️ High memory usage: {memory.percent:.1f}% (limit: {self.config.max_memory_percent}%)")
            gc.collect()
            time.sleep(1)
            
            # Check again after cleanup
            memory = psutil.virtual_memory()
            if memory.percent > self.config.max_memory_percent:
                return False
        return True
    
    def _sanitize_filename(self, filename: str) -> str:
        """Create safe filename"""
        if not self.config.sanitize_filenames:
            return filename
        
        # Replace problematic characters
        filename = filename.replace('/', '_').replace('\\', '_').replace(':', '_')
        filename = filename.replace('"', "'").replace('*', '_').replace('?', '_')
        filename = filename.replace('<', '_').replace('>', '_').replace('|', '_')
        
        # Limit length
        if len(filename) > self.config.max_filename_length:
            name, ext = os.path.splitext(filename)
            filename = name[:self.config.max_filename_length - len(ext)] + ext
        
        return filename
    
    def _prepare_output_dir(self, channel_name: str = None) -> Path:
        """Prepare output directory"""
        if self.config.create_channel_folder and channel_name:
            output_dir = Path(self.config.output_dir) / self._sanitize_filename(channel_name)
        else:
            output_dir = Path(self.config.output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def download_single_video(self, video: Dict, output_dir: Path, session: requests.Session = None) -> DownloadResult:
        """Download a single video with comprehensive options"""
        start_time = time.time()
        video_title = video.get('title', 'Unknown')
        video_url = video.get('url', '')
        
        logger.debug(f"🎬 Starting download: {video_title[:50]}...")
        
        for attempt in range(self.config.retry_attempts):
            try:
                # Memory check
                if not self._check_memory_usage():
                    return DownloadResult(
                        url=video_url,
                        title=video_title,
                        success=False,
                        error="Memory usage too high",
                        duration=time.time() - start_time
                    )
                
                # Prepare download options
                download_options = {
                    'format': self.config.format_selector,
                }
                
                # Audio extraction settings
                if self.config.audio_only:
                    download_options.update({
                        'extractaudio': True,
                        'audioformat': self.config.audio_format,
                        'audioquality': self.config.audio_quality
                    })
                
                # Subtitle settings
                if self.config.download_subtitles:
                    download_options.update({
                        'writesubtitles': True,
                        'writeautomaticsub': self.config.auto_subtitles,
                        'subtitleslangs': self.config.subtitle_languages
                    })
                
                # Make request
                if session:
                    response = session.post(f'{self.config.api_base}/download', 
                                          json={'url': video_url, 'options': download_options},
                                          timeout=300)
                else:
                    response = requests.post(f'{self.config.api_base}/download',
                                           json={'url': video_url, 'options': download_options},
                                           timeout=300)
                
                if response.status_code == 200:
                    # Determine file extension
                    if self.config.audio_only:
                        extension = self.config.audio_format
                    else:
                        extension = response.headers.get('X-Video-Format', 'mp4')
                    
                    # Create filename
                    safe_title = self._sanitize_filename(video_title)
                    filename = f"{safe_title}.{extension}"
                    filepath = output_dir / filename
                    
                    # Check if file exists and skip if configured
                    if self.config.skip_existing and filepath.exists():
                        logger.info(f"⏭️ Skipping existing: {safe_title}")
                        return DownloadResult(
                            url=video_url,
                            title=video_title,
                            success=True,
                            file_size=filepath.stat().st_size,
                            file_path=str(filepath),
                            format_downloaded=extension,
                            duration=time.time() - start_time
                        )
                    
                    # Save file
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    # Update counters thread-safely
                    with self.lock:
                        self.downloaded_count += 1
                        self.total_size += len(response.content)
                    
                    result = DownloadResult(
                        url=video_url,
                        title=video_title,
                        success=True,
                        file_size=len(response.content),
                        file_path=str(filepath),
                        format_downloaded=extension,
                        duration=time.time() - start_time
                    )
                    
                    size_mb = len(response.content) / 1024 / 1024
                    logger.info(f"✅ Downloaded: {safe_title} ({size_mb:.1f}MB)")
                    return result
                
                else:
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get('error', f'HTTP {response.status_code}')
                    
                    if attempt < self.config.retry_attempts - 1:
                        logger.warning(f"⚠️ Attempt {attempt + 1} failed for {video_title[:30]}: {error_msg}")
                        time.sleep(self.config.retry_delay * (attempt + 1))
                    else:
                        logger.error(f"❌ All attempts failed for {video_title[:30]}: {error_msg}")
                
            except Exception as e:
                if attempt < self.config.retry_attempts - 1:
                    logger.warning(f"⚠️ Attempt {attempt + 1} exception for {video_title[:30]}: {e}")
                    time.sleep(self.config.retry_delay * (attempt + 1))
        
        # All attempts failed
        with self.lock:
            self.failed_count += 1
        
        return DownloadResult(
            url=video_url,
            title=video_title,
            success=False,
            error=f"Failed after {self.config.retry_attempts} attempts",
            duration=time.time() - start_time
        )
    
    def download_batch_threaded(self, videos: List[Dict], output_dir: Path, 
                               progress_callback: Callable = None) -> List[DownloadResult]:
        """Download a batch of videos using threading"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Create session for each worker
            sessions = {i: requests.Session() for i in range(self.config.max_workers)}
            
            # Submit downloads
            future_to_video = {}
            for i, video in enumerate(videos):
                session = sessions[i % self.config.max_workers]
                future = executor.submit(self.download_single_video, video, output_dir, session)
                future_to_video[future] = video
            
            # Collect results
            for i, future in enumerate(as_completed(future_to_video)):
                result = future.result()
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(videos), result)
                
                # Rate limiting
                time.sleep(self.config.rate_limit_delay)
            
            # Close sessions
            for session in sessions.values():
                session.close()
        
        return results
    
    async def download_single_video_async(self, video: Dict, output_dir: Path, 
                                        session: aiohttp.ClientSession) -> DownloadResult:
        """Async version of single video download"""
        start_time = time.time()
        video_title = video.get('title', 'Unknown')
        video_url = video.get('url', '')
        
        for attempt in range(self.config.retry_attempts):
            try:
                if not self._check_memory_usage():
                    return DownloadResult(
                        url=video_url,
                        title=video_title,
                        success=False,
                        error="Memory usage too high",
                        duration=time.time() - start_time
                    )
                
                download_options = {'format': self.config.format_selector}
                
                if self.config.audio_only:
                    download_options.update({
                        'extractaudio': True,
                        'audioformat': self.config.audio_format,
                        'audioquality': self.config.audio_quality
                    })
                
                if self.config.download_subtitles:
                    download_options.update({
                        'writesubtitles': True,
                        'writeautomaticsub': self.config.auto_subtitles,
                        'subtitleslangs': self.config.subtitle_languages
                    })
                
                async with session.post(f'{self.config.api_base}/download',
                                       json={'url': video_url, 'options': download_options},
                                       timeout=aiohttp.ClientTimeout(total=300)) as response:
                    
                    if response.status == 200:
                        content = await response.read()
                        
                        extension = self.config.audio_format if self.config.audio_only else 'mp4'
                        safe_title = self._sanitize_filename(video_title)
                        filename = f"{safe_title}.{extension}"
                        filepath = output_dir / filename
                        
                        if self.config.skip_existing and filepath.exists():
                            logger.info(f"⏭️ Skipping existing: {safe_title}")
                            return DownloadResult(
                                url=video_url,
                                title=video_title,
                                success=True,
                                file_size=filepath.stat().st_size,
                                file_path=str(filepath),
                                format_downloaded=extension,
                                duration=time.time() - start_time
                            )
                        
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        
                        self.downloaded_count += 1
                        self.total_size += len(content)
                        
                        result = DownloadResult(
                            url=video_url,
                            title=video_title,
                            success=True,
                            file_size=len(content),
                            file_path=str(filepath),
                            format_downloaded=extension,
                            duration=time.time() - start_time
                        )
                        
                        size_mb = len(content) / 1024 / 1024
                        logger.info(f"✅ Downloaded: {safe_title} ({size_mb:.1f}MB)")
                        return result
                    
                    else:
                        error_data = await response.json() if response.content_type.startswith('application/json') else {}
                        error_msg = error_data.get('error', f'HTTP {response.status}')
                        
                        if attempt < self.config.retry_attempts - 1:
                            logger.warning(f"⚠️ Attempt {attempt + 1} failed for {video_title[:30]}: {error_msg}")
                            await asyncio.sleep(self.config.retry_delay * (attempt + 1))
            
            except Exception as e:
                if attempt < self.config.retry_attempts - 1:
                    logger.warning(f"⚠️ Attempt {attempt + 1} exception for {video_title[:30]}: {e}")
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        self.failed_count += 1
        return DownloadResult(
            url=video_url,
            title=video_title,
            success=False,
            error=f"Failed after {self.config.retry_attempts} attempts",
            duration=time.time() - start_time
        )
    
    async def download_batch_async(self, videos: List[Dict], output_dir: Path,
                                  progress_callback: Callable = None) -> List[DownloadResult]:
        """Download a batch of videos using asyncio"""
        results = []
        semaphore = asyncio.Semaphore(self.config.max_workers)
        
        async def download_with_semaphore(video):
            async with semaphore:
                result = await self.download_single_video_async(video, output_dir, session)
                await asyncio.sleep(self.config.rate_limit_delay)
                return result
        
        connector = aiohttp.TCPConnector(limit=self.config.max_workers)
        timeout = aiohttp.ClientTimeout(total=300)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [download_with_semaphore(video) for video in videos]
            
            for i, task in enumerate(asyncio.as_completed(tasks)):
                result = await task
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(videos), result)
        
        return results
    
    def download_transcripts(self, videos: List[Dict], output_dir: Path) -> Dict[str, Dict]:
        """Download transcripts for videos"""
        logger.info(f"📝 Downloading transcripts for {len(videos)} videos...")
        
        transcripts = {}
        
        for video in videos:
            try:
                response = requests.post(f'{self.config.api_base}/subtitles', json={
                    'url': video['url'],
                    'options': {
                        'writeautomaticsub': self.config.auto_subtitles,
                        'allsubtitles': True,
                        'subtitleslangs': self.config.subtitle_languages
                    }
                }, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Save transcript info
                    safe_title = self._sanitize_filename(video.get('title', 'Unknown'))
                    transcript_file = output_dir / f"{safe_title}_transcripts.json"
                    
                    with open(transcript_file, 'w', encoding='utf-8') as f:
                        import json
                        json.dump({
                            'video_info': video,
                            'subtitles': data.get('subtitles', {}),
                            'automatic_captions': data.get('automatic_captions', {})
                        }, f, indent=2, ensure_ascii=False)
                    
                    transcripts[video['url']] = data
                    logger.debug(f"✅ Transcript saved: {safe_title}")
                
                else:
                    logger.warning(f"⚠️ Failed to get transcript for: {video.get('title', 'Unknown')}")
                    
            except Exception as e:
                logger.error(f"❌ Exception getting transcript for {video.get('title', 'Unknown')}: {e}")
        
        return transcripts
    
    def download_channel(self, channel_url: str, progress_callback: Callable = None) -> Dict:
        """Download entire channel with comprehensive features"""
        start_time = time.time()
        
        logger.info(f"🚀 Starting channel download: {channel_url}")
        logger.info(f"📊 Config: {self.config.max_workers} workers, {self.config.batch_size} batch size, "
                   f"{'async' if self.config.use_async else 'threaded'} mode")
        
        # Reset counters
        self.downloaded_count = 0
        self.failed_count = 0
        self.total_size = 0
        self.results.clear()
        
        # Get channel info
        channel_data = self.get_channel_info(channel_url)
        if not channel_data['success']:
            return {'success': False, 'error': channel_data['error']}
        
        channel_info = channel_data['channel_info']
        videos = channel_data['videos']
        
        if not videos:
            return {'success': False, 'error': 'No videos found in channel'}
        
        # Prepare output directory
        channel_name = channel_info.get('title', 'Unknown_Channel')
        output_dir = self._prepare_output_dir(channel_name)
        
        logger.info(f"📂 Output directory: {output_dir}")
        
        # Save channel info
        if self.config.save_video_info:
            import json
            info_file = output_dir / 'channel_info.json'
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(channel_data, f, indent=2, ensure_ascii=False)
        
        # Download transcripts if requested
        if self.config.download_subtitles and self.config.concurrent_transcripts:
            logger.info("📝 Downloading transcripts concurrently...")
            self.download_transcripts(videos, output_dir)
        
        # Process videos in batches
        total_batches = (len(videos) + self.config.batch_size - 1) // self.config.batch_size
        all_results = []
        
        for batch_num in range(total_batches):
            start_idx = batch_num * self.config.batch_size
            end_idx = min(start_idx + self.config.batch_size, len(videos))
            batch_videos = videos[start_idx:end_idx]
            
            logger.info(f"📦 Processing batch {batch_num + 1}/{total_batches} ({len(batch_videos)} videos)")
            
            # Download batch
            if self.config.use_async:
                batch_results = asyncio.run(self.download_batch_async(batch_videos, output_dir, progress_callback))
            else:
                batch_results = self.download_batch_threaded(batch_videos, output_dir, progress_callback)
            
            all_results.extend(batch_results)
            self.results.extend(batch_results)
            
            # Memory cleanup
            gc.collect()
            
            # Pause between batches
            if batch_num < total_batches - 1:
                logger.info(f"⏸️ Pausing {self.config.batch_pause}s between batches...")
                time.sleep(self.config.batch_pause)
        
        # Final statistics
        total_time = time.time() - start_time
        successful = [r for r in all_results if r.success]
        failed = [r for r in all_results if not r.success]
        
        stats = {
            'success': True,
            'channel_name': channel_name,
            'total_videos': len(videos),
            'downloaded': len(successful),
            'failed': len(failed),
            'success_rate': len(successful) / len(videos) * 100 if videos else 0,
            'total_size_mb': self.total_size / 1024 / 1024,
            'total_time_minutes': total_time / 60,
            'average_time_per_video': total_time / len(videos) if videos else 0,
            'output_directory': str(output_dir),
            'failed_videos': [{'title': r.title, 'error': r.error} for r in failed],
            'download_results': all_results
        }
        
        logger.info(f"🎉 Channel download complete!")
        logger.info(f"✅ Downloaded: {len(successful)}/{len(videos)} videos")
        logger.info(f"📁 Total size: {stats['total_size_mb']:.1f} MB")
        logger.info(f"⏱️ Total time: {stats['total_time_minutes']:.1f} minutes")
        logger.info(f"📂 Saved to: {output_dir}")
        
        return stats

# Convenience functions
def create_audio_config(max_videos: int = 50, workers: int = 4) -> DownloadConfig:
    """Create optimized config for audio downloads"""
    return DownloadConfig(
        max_workers=workers,
        batch_size=12,
        max_videos=max_videos,
        audio_only=True,
        audio_format='mp3',
        audio_quality='192K',
        format_selector='ba[acodec^=mp3]/ba/b',
        rate_limit_delay=0.5,
        create_channel_folder=True
    )

def create_video_config(max_videos: int = 30, workers: int = 3) -> DownloadConfig:
    """Create optimized config for video downloads"""
    return DownloadConfig(
        max_workers=workers,
        batch_size=8,
        max_videos=max_videos,
        audio_only=False,
        format_selector='best[height<=720][filesize<200M]',
        rate_limit_delay=1.0,
        max_memory_percent=60.0,
        create_channel_folder=True
    )

def create_transcript_config(max_videos: int = 100, workers: int = 6) -> DownloadConfig:
    """Create optimized config for downloads with transcripts"""
    return DownloadConfig(
        max_workers=workers,
        batch_size=15,
        max_videos=max_videos,
        audio_only=True,
        audio_format='mp3',
        audio_quality='128K',
        download_subtitles=True,
        auto_subtitles=True,
        subtitle_languages=['en'],
        concurrent_transcripts=True,
        rate_limit_delay=0.8,
        create_channel_folder=True
    )

def download_channel_simple(channel_url: str, as_audio: bool = True, max_videos: int = 50) -> Dict:
    """Simple function to download a channel"""
    config = create_audio_config(max_videos, 4) if as_audio else create_video_config(max_videos, 3)
    
    downloader = ChannelDownloader(config)
    
    def progress(current, total, result):
        status = "✅" if result.success else "❌"
        print(f"{status} [{current}/{total}] {result.title[:50]}...")
    
    return downloader.download_channel(channel_url, progress_callback=progress)

# Main execution
if __name__ == '__main__':
    print("🎯 yt-dlp Channel Downloader")
    print("=" * 50)
    
    # Interactive mode
    print("\nSelect download type:")
    print("1. Audio only (MP3) - Fast")
    print("2. Video (720p max) - Slower")
    print("3. Audio + Transcripts - Comprehensive")
    print("4. Custom configuration")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    channel_url = input("Enter YouTube channel URL: ").strip()
    if not channel_url:
        channel_url = 'https://www.youtube.com/@pythondotorg/videos'
        print(f"Using default: {channel_url}")
    
    max_videos = input("Max videos to download (default 20): ").strip()
    max_videos = int(max_videos) if max_videos.isdigit() else 20
    
    if choice == '1':
        config = create_audio_config(max_videos, 6)
    elif choice == '2':
        config = create_video_config(max_videos, 3)
    elif choice == '3':
        config = create_transcript_config(max_videos, 4)
    elif choice == '4':
        # Custom config
        workers = int(input("Number of parallel workers (default 4): ").strip() or "4")
        batch_size = int(input("Batch size (default 10): ").strip() or "10")
        audio_only = input("Audio only? (y/n, default y): ").strip().lower() != 'n'
        
        config = DownloadConfig(
            max_workers=workers,
            batch_size=batch_size,
            max_videos=max_videos,
            audio_only=audio_only,
            audio_format='mp3' if audio_only else 'mp4',
            create_channel_folder=True
        )
    else:
        print("❌ Invalid choice")
        exit(1)
    
    # Create downloader and start
    downloader = ChannelDownloader(config)
    
    def progress_callback(current, total, result):
        status = "✅" if result.success else "❌"
        print(f"{status} [{current}/{total}] {result.title[:50]}...")
    
    try:
        result = downloader.download_channel(channel_url, progress_callback=progress_callback)
        
        if result['success']:
            print(f"\n🎉 Success! Downloaded {result['downloaded']}/{result['total_videos']} videos")
            print(f"📁 Files saved to: {result['output_directory']}")
            print(f"💾 Total size: {result['total_size_mb']:.1f} MB")
        else:
            print(f"\n❌ Failed: {result['error']}")
            
    except KeyboardInterrupt:
        print("\n⛔ Download cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Unhandled exception during download") 