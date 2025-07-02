#!/usr/bin/env python3
"""
Test script for yt-dlp API with enhanced cookie support
Run this locally to test YouTube cookie authentication before deploying to VPS
"""

import json
import requests
import sys
import time

def test_api_endpoint(url, data=None, method='GET'):
    """Test an API endpoint with error handling"""
    try:
        if method == 'POST':
            response = requests.post(url, json=data, timeout=30)
        else:
            response = requests.get(url, timeout=30)
        
        print(f"Status: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"Non-JSON response: {response.text[:200]}...")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server. Make sure it's running!")
        return None
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    base_url = "http://localhost:5000"
    
    print("🧪 Testing yt-dlp API with Cookie Authentication")
    print("=" * 50)
    
    # Test 1: Check if server is running
    print("\n1️⃣ Testing server connection...")
    result = test_api_endpoint(base_url)
    if not result:
        print("\n❌ Server is not running. Start it with:")
        print("python yt_dlp_api.py --debug")
        return
    
    print("✅ Server is running!")
    
    # Test 2: Test cookie extraction capabilities
    print("\n2️⃣ Testing cookie extraction capabilities...")
    result = test_api_endpoint(f"{base_url}/test-cookies")
    if result and result.get('success'):
        print("✅ Cookie test completed!")
        browsers = result.get('cookie_test_results', {})
        available_browsers = [browser for browser, status in browsers.items() if 'Available' in status]
        
        if available_browsers:
            print(f"🍪 Available browsers for cookie extraction: {', '.join(available_browsers)}")
            recommended_browser = available_browsers[0]
        else:
            print("⚠️ No browsers available for cookie extraction")
            print("Make sure you have Chrome/Firefox/Edge installed and have visited YouTube")
            recommended_browser = 'chrome'  # fallback
    else:
        print("⚠️ Cookie test failed, but continuing...")
        recommended_browser = 'chrome'  # fallback
    
    # Test 3: Test YouTube video info extraction (the problematic video from the error)
    print("\n3️⃣ Testing YouTube info extraction with cookies...")
    test_url = "https://youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll - the one that failed
    
    # First try without cookies
    print("\n📋 Testing WITHOUT cookies (should fail)...")
    data = {
        "url": test_url
    }
    result = test_api_endpoint(f"{base_url}/info", data, 'POST')
    
    if result and not result.get('success'):
        print("✅ Expected failure without cookies confirmed")
    
    # Now try with browser cookies
    print(f"\n🍪 Testing WITH browser cookies ({recommended_browser})...")
    data = {
        "url": test_url,
        "options": {
            "cookiesfrombrowser": recommended_browser
        }
    }
    result = test_api_endpoint(f"{base_url}/info", data, 'POST')
    
    if result and result.get('success'):
        print("🎉 SUCCESS! Cookie authentication is working!")
        info = result.get('info', {})
        print(f"📺 Video: {info.get('title')}")
        print(f"👤 Uploader: {info.get('uploader')}")
        print(f"⏱️ Duration: {info.get('duration')} seconds")
        print(f"👀 Views: {info.get('view_count'):,}" if info.get('view_count') else "👀 Views: Unknown")
    else:
        print("❌ Cookie authentication failed!")
        if result:
            print("Error details:", result.get('error'))
            if result.get('help'):
                print("\n💡 Suggestions:")
                for solution in result.get('help', {}).get('solutions', []):
                    print(f"  • {solution}")
    
    # Test 4: Test different video (in case Rick Roll is blocked)
    print("\n4️⃣ Testing with different video...")
    alternate_url = "https://youtube.com/watch?v=9bZkp7q19f0"  # PSY - Gangnam Style
    
    data = {
        "url": alternate_url,
        "options": {
            "cookiesfrombrowser": recommended_browser
        }
    }
    result = test_api_endpoint(f"{base_url}/info", data, 'POST')
    
    if result and result.get('success'):
        print("✅ Alternate video test passed!")
        info = result.get('info', {})
        print(f"📺 Video: {info.get('title')}")
    else:
        print("⚠️ Alternate video test failed")
    
    # Test 5: Test download endpoint (just info, not actual download)
    print("\n5️⃣ Testing download endpoint readiness...")
    print("(Note: Not actually downloading, just testing endpoint)")
    
    data = {
        "url": test_url,
        "options": {
            "cookiesfrombrowser": recommended_browser,
            "format": "worst"  # Use worst quality for testing
        }
    }
    
    print("Testing download endpoint (this may take a moment)...")
    start_time = time.time()
    
    try:
        response = requests.post(f"{base_url}/download", json=data, timeout=60, stream=True)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Download endpoint working! (Response received in {elapsed:.1f}s)")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print(f"Content-Length: {response.headers.get('content-length')} bytes")
            print(f"Video Title: {response.headers.get('x-video-title')}")
        else:
            print(f"❌ Download failed with status {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('error')}")
            except:
                print(f"Response: {response.text[:200]}...")
                
    except requests.exceptions.Timeout:
        print("⚠️ Download test timed out (this is normal for large videos)")
    except Exception as e:
        print(f"❌ Download test error: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY")
    print("=" * 50)
    print("✅ If info extraction worked with cookies, you're ready for VPS deployment!")
    print("❌ If tests failed, check the troubleshooting steps below:")
    print()
    print("🔧 TROUBLESHOOTING:")
    print("1. Make sure you're logged into YouTube in your browser")
    print("2. Try different browsers (chrome, firefox, edge)")
    print("3. Clear browser cache and re-login to YouTube")
    print("4. For VPS deployment, export cookies to a file instead:")
    print("   • Install 'Get cookies.txt LOCALLY' extension")
    print("   • Export YouTube cookies")
    print("   • Upload cookies.txt to VPS")
    print("   • Use: {'options': {'cookiefile': '/path/to/cookies.txt'}}")
    print()
    print("🚀 Ready for VPS? Copy this working configuration:")
    print(f"   {{'options': {{'cookiesfrombrowser': '{recommended_browser}'}}}}")

if __name__ == "__main__":
    main() 