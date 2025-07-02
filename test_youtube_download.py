#!/usr/bin/env python3

import json
import requests
import time

def test_youtube_with_cookies():
    """Test downloading YouTube video with cookies"""
    
    # Test URL - a popular YouTube video
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll
    
    print("🧪 Testing YouTube download with cookies...")
    print(f"📺 Video URL: {test_url}")
    print(f"🍪 Cookie file: yt_dlp/cookies/youtube_cookies.txt")
    
    # Wait for API to start
    print("⏳ Waiting for API server to start...")
    time.sleep(5)
    
    # Test 1: Get video info using cookie file
    print("\n1️⃣ Testing video info extraction with cookies...")
    
    payload = {
        "url": test_url,
        "options": {
            "cookiefile": "yt_dlp/cookies/youtube_cookies.txt"
        }
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:5002/info",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                info = result.get('info', {})
                print("✅ SUCCESS! Video info extracted:")
                print(f"   📺 Title: {info.get('title', 'Unknown')}")
                print(f"   👤 Uploader: {info.get('uploader', 'Unknown')}")
                print(f"   ⏱️  Duration: {info.get('duration', 'Unknown')} seconds")
                print(f"   👀 Views: {info.get('view_count', 'Unknown'):,}" if info.get('view_count') else "   👀 Views: Unknown")
                print(f"   📅 Upload Date: {info.get('upload_date', 'Unknown')}")
                
                # Test 2: Try downloading (just info about formats)
                print("\n2️⃣ Testing format availability...")
                formats = info.get('formats', [])
                if formats:
                    print(f"   📊 Available formats: {len(formats)}")
                    
                    # Show some format details
                    for fmt in formats[:3]:  # Show first 3 formats
                        print(f"   • {fmt.get('format_id', 'unknown')}: {fmt.get('ext', 'unknown')} "
                              f"({fmt.get('resolution', 'unknown resolution')})")
                else:
                    print("   ⚠️  No formats found")
                
                return True
            else:
                print("❌ FAILED! API returned error:")
                print(f"   Error: {result.get('error', 'Unknown error')}")
                
                # Check for cookie-related help
                if result.get('help'):
                    print("\n💡 Suggested solutions:")
                    for solution in result.get('help', {}).get('solutions', []):
                        print(f"   • {solution}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server!")
        print("   Make sure the API server is running:")
        print("   python yt_dlp_api.py --debug")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False
    
    return False

def test_direct_ytdlp():
    """Test direct yt-dlp with cookies"""
    print("\n3️⃣ Testing direct yt-dlp with cookies...")
    
    import subprocess
    import os
    
    cookie_file = "yt_dlp/cookies/youtube_cookies.txt"
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    if not os.path.exists(cookie_file):
        print(f"❌ Cookie file not found: {cookie_file}")
        return False
    
    try:
        # Test with direct yt-dlp command
        cmd = [
            "python", "-m", "yt_dlp",
            "--cookies", cookie_file,
            "--no-download",  # Don't actually download
            "--print", "title,uploader,duration",
            test_url
        ]
        
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Direct yt-dlp SUCCESS!")
            print("Output:")
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    print(f"   {line}")
            return True
        else:
            print("❌ Direct yt-dlp FAILED!")
            print("Error output:")
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    print(f"   {line}")
                    
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
    except Exception as e:
        print(f"❌ Error running direct yt-dlp: {str(e)}")
    
    return False

if __name__ == "__main__":
    print("🚀 YouTube Cookie Authentication Test")
    print("=" * 50)
    
    # Test API approach
    api_success = test_youtube_with_cookies()
    
    # Test direct yt-dlp approach
    direct_success = test_direct_ytdlp()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"   API with cookies: {'✅ SUCCESS' if api_success else '❌ FAILED'}")
    print(f"   Direct yt-dlp: {'✅ SUCCESS' if direct_success else '❌ FAILED'}")
    
    if api_success or direct_success:
        print("\n🎉 Cookie authentication is working!")
        print("💡 You can now download YouTube videos with authentication.")
    else:
        print("\n❌ Cookie authentication needs troubleshooting.")
        print("💡 Check that:")
        print("   • Cookies are fresh (exported recently)")
        print("   • You're logged into YouTube")
        print("   • Cookie file format is correct") 