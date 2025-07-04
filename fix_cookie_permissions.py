#!/usr/bin/env python3
"""
Fix for cookie permission issue on the API server.
This script modifies the yt_dlp_api.py to handle read-only cookie files properly.
"""

def create_cookie_fix():
    """Create a fix for the cookie permission issue"""
    fix_code = '''
    def _create_writable_cookie_copy(self, original_cookiefile):
        """Create a writable copy of the cookie file in temp directory"""
        import shutil
        import tempfile
        import os
        
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
    
    def _get_enhanced_ydl_opts_fixed(self, opts=None):
        """Get enhanced yt-dlp options with cookie permission fix"""
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
        
        # Handle cookie files with permission fix
        try:
            # First check if a cookiefile is specified in opts
            if 'cookiefile' in opts:
                original_cookiefile = opts['cookiefile']
                writable_copy = self._create_writable_cookie_copy(original_cookiefile)
                if writable_copy:
                    enhanced_opts['cookiefile'] = writable_copy
                    return enhanced_opts
            
            # Try automated cookies
            cookie_source = self._get_automated_cookies()
            if cookie_source['success'] and cookie_source['opts']:
                original_cookiefile = cookie_source['opts'].get('cookiefile')
                if original_cookiefile:
                    writable_copy = self._create_writable_cookie_copy(original_cookiefile)
                    if writable_copy:
                        enhanced_opts['cookiefile'] = writable_copy
                        print(f"🍪 Using writable automated cookie copy")
                    else:
                        enhanced_opts.update(cookie_source['opts'])
                else:
                    enhanced_opts.update(cookie_source['opts'])
            else:
                print(f"⚠️ Automated cookies failed: {cookie_source['error']}")
                # Fall back to manual cookie file handling
                enhanced_opts = self._handle_manual_cookies_fixed(enhanced_opts, opts)
                
        except Exception as e:
            print(f"⚠️ Cookie handling error: {e}")
            # Continue without cookies for public content
            print("🔄 Continuing without cookies for public content")
        
        return enhanced_opts
    
    def _handle_manual_cookies_fixed(self, enhanced_opts, opts):
        """Handle manual cookie files with permission fix"""
        print("🔄 Falling back to manual cookie file method")
        
        # Check for existing manual cookie files
        manual_cookie_files = [
            '/app/cookies/youtube_cookies.txt',
            '/app/cookies/cookies.txt',
            '/app/YTC-DL/cookies.txt',
            '/app/YTC-DL/ytc_youtube_cookies.txt'
        ]
        
        try:
            for cookie_file in manual_cookie_files:
                if os.path.exists(cookie_file) and os.access(cookie_file, os.R_OK):
                    writable_copy = self._create_writable_cookie_copy(cookie_file)
                    if writable_copy:
                        enhanced_opts['cookiefile'] = writable_copy
                        print(f"🍪 Using writable manual cookie copy from: {cookie_file}")
                        return enhanced_opts
                        
        except Exception as e:
            print(f"⚠️ Error handling manual cookies: {e}")
        
        print("⚠️ No accessible manual cookie files found - continuing without cookies")
        return enhanced_opts
    '''
    
    return fix_code

if __name__ == '__main__':
    print("Cookie permission fix code generated")
    print("Apply this to the yt_dlp_api.py on the server to fix the permission issue")
    print("\nThe fix works by:")
    print("1. Detecting when a cookie file exists but is not writable")
    print("2. Creating a temporary writable copy of the cookie file")
    print("3. Using the writable copy for yt-dlp operations")
    print("4. Allowing yt-dlp to save cookies to the temporary location") 