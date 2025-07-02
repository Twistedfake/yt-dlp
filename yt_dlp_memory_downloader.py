"""
Custom memory downloader for yt-dlp that stores video content in memory instead of saving to disk.
"""

import io
import time
from yt_dlp.downloader.http import HttpFD
from yt_dlp.utils import ContentTooShortError


class MemoryHttpFD(HttpFD):
    """HTTP downloader that stores content in memory instead of writing to disk"""
    
    def __init__(self, ydl, params):
        super().__init__(ydl, params)
        self.data_buffer = io.BytesIO()
        
    def real_download(self, filename, info_dict):
        """Download content to memory buffer"""
        url = info_dict['url']
        request_data = info_dict.get('request_data', None)

        class DownloadContext(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__
            __delattr__ = dict.__delitem__

        ctx = DownloadContext()
        ctx.filename = filename
        ctx.tmpfilename = filename  # We don't need temp files
        ctx.stream = self.data_buffer  # Use our memory buffer instead of file
        ctx.data_buffer = self.data_buffer
        
        # Initialize context
        ctx.open_mode = 'wb'
        ctx.resume_len = 0
        ctx.block_size = self.params.get('buffersize', 1024)
        ctx.start_time = time.time()
        ctx.throttle_start = None

        headers = {'Accept-Encoding': 'identity'}
        headers.update(info_dict.get('http_headers', {}))

        is_test = self.params.get('test', False)
        chunk_size = self._TEST_FILE_SIZE if is_test else (
            self.params.get('http_chunk_size')
            or info_dict.get('downloader_options', {}).get('http_chunk_size')
            or 0)

        class SucceedDownload(Exception):
            pass

        class RetryDownload(Exception):
            def __init__(self, source_error):
                self.source_error = source_error

        def establish_connection():
            from yt_dlp.networking import Request
            
            request = Request(url, request_data, headers)
            try:
                ctx.data = self.ydl.urlopen(request)
                ctx.content_len = int(ctx.data.headers.get('Content-length') or 0)
                ctx.data_len = ctx.content_len
            except Exception as err:
                raise RetryDownload(err)

        def download():
            data_len = ctx.data.headers.get('Content-length')
            
            if ctx.data.headers.get('Content-encoding'):
                data_len = None

            if is_test and (data_len is None or int(data_len) > self._TEST_FILE_SIZE):
                data_len = self._TEST_FILE_SIZE

            if data_len is not None:
                data_len = int(data_len)
                min_data_len = self.params.get('min_filesize')
                max_data_len = self.params.get('max_filesize')
                if min_data_len is not None and data_len < min_data_len:
                    self.to_screen(f'\r[download] File is smaller than min-filesize ({data_len} bytes < {min_data_len} bytes). Aborting.')
                    return False
                if max_data_len is not None and data_len > max_data_len:
                    self.to_screen(f'\r[download] File is larger than max-filesize ({data_len} bytes > {max_data_len} bytes). Aborting.')
                    return False

            byte_counter = 0
            block_size = ctx.block_size
            start = time.time()
            now = None
            before = start

            while True:
                try:
                    # Download chunk
                    data_block = ctx.data.read(block_size if not is_test else min(block_size, data_len - byte_counter))
                except Exception as err:
                    self.report_error(f'Error reading data: {err}')
                    return False

                byte_counter += len(data_block)

                # Exit loop when download is finished
                if len(data_block) == 0:
                    break

                # Write to our memory buffer
                try:
                    ctx.stream.write(data_block)
                except Exception as err:
                    self.report_error(f'Unable to write data: {err}')
                    return False

                # Apply rate limit
                self.slow_down(start, now, byte_counter)

                # End measuring of one loop run
                now = time.time()
                after = now

                # Adjust block size
                if not self.params.get('noresizebuffer', False):
                    block_size = self.best_block_size(after - before, len(data_block))

                before = after

                # Progress message
                speed = self.calc_speed(start, now, byte_counter)
                if ctx.data_len is None:
                    eta = None
                else:
                    eta = self.calc_eta(start, time.time(), ctx.data_len, byte_counter)

                self._hook_progress({
                    'status': 'downloading',
                    'downloaded_bytes': byte_counter,
                    'total_bytes': ctx.data_len,
                    'tmpfilename': ctx.tmpfilename,
                    'filename': ctx.filename,
                    'eta': eta,
                    'speed': speed,
                    'elapsed': now - ctx.start_time,
                    'ctx_id': info_dict.get('ctx_id'),
                }, info_dict)

                if data_len is not None and byte_counter == data_len:
                    break

                # Check for throttling
                throttled_rate = self.params.get('throttledratelimit')
                if throttled_rate and speed and speed < throttled_rate:
                    if ctx.throttle_start is None:
                        ctx.throttle_start = now
                    elif now - ctx.throttle_start > 3:
                        from yt_dlp.utils import ThrottledDownload
                        raise ThrottledDownload
                elif speed:
                    ctx.throttle_start = None

            if byte_counter == 0:
                self.report_error('Did not get any data blocks')
                return False

            if data_len is not None and byte_counter != data_len:
                err = ContentTooShortError(byte_counter, int(data_len))
                self.report_error(f'Content too short: {err}')
                return False

            self._hook_progress({
                'downloaded_bytes': byte_counter,
                'total_bytes': byte_counter,
                'filename': ctx.filename,
                'status': 'finished',
                'elapsed': time.time() - ctx.start_time,
                'ctx_id': info_dict.get('ctx_id'),
            }, info_dict)

            return True

        # Main download loop with retries
        from yt_dlp.utils import RetryManager
        
        for retry in RetryManager(self.params.get('retries', 3), self.report_retry):
            try:
                establish_connection()
                return download()
            except RetryDownload as err:
                retry.error = err.source_error
                continue
            except SucceedDownload:
                return True
            except Exception as e:
                self.report_error(f'Download failed: {e}')
                return False
        
        return False
    
    def get_downloaded_data(self):
        """Return the downloaded data as bytes"""
        return self.data_buffer.getvalue()
    
    def reset_buffer(self):
        """Reset the memory buffer"""
        self.data_buffer = io.BytesIO() 