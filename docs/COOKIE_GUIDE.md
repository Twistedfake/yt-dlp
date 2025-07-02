# YouTube Cookie Authentication Guide

YouTube increasingly requires authentication to avoid bot detection. This guide shows you how to set up cookie authentication for both local testing and VPS deployment.

## Method 1: Browser Cookies (Local Testing Only)

This works when running the API on your local machine with browsers installed.

```json
{
    "url": "https://youtube.com/watch?v=VIDEO_ID",
    "options": {
        "cookiesfrombrowser": "chrome"
    }
}
```

**Supported browsers:** `chrome`, `firefox`, `edge`, `safari`, `opera`, `brave`

**With specific profile:**
```json
{
    "options": {
        "cookiesfrombrowser": "chrome:Profile 1"
    }
}
```

## Method 2: Cookie File (Recommended for VPS)

### Step 1: Install Browser Extension

**For Chrome/Edge:**
1. Install "Get cookies.txt LOCALLY" extension from Chrome Web Store
2. **Important:** Choose the "LOCALLY" version for privacy

**For Firefox:**
1. Install "cookies.txt" extension from Firefox Add-ons

### Step 2: Export YouTube Cookies

1. **Login to YouTube** in your browser
2. **Navigate to** `https://www.youtube.com/`
3. **Click the extension icon** in your browser toolbar
4. **Export cookies** for `youtube.com` domain
5. **Save as** `youtube_cookies.txt`

### Step 3: Use Cookie File

```json
{
    "url": "https://youtube.com/watch?v=VIDEO_ID",
    "options": {
        "cookiefile": "/path/to/youtube_cookies.txt"
    }
}
```

## Method 3: Manual Cookie Extraction (Advanced)

If browser extensions don't work, you can manually extract cookies:

### For Chrome/Edge:

1. Open YouTube and login
2. Press `F12` to open Developer Tools
3. Go to **Application** tab → **Storage** → **Cookies** → `https://www.youtube.com`
4. Copy important cookies (see list below)
5. Create a Netscape format cookie file

### For Firefox:

1. Open YouTube and login  
2. Press `F12` to open Developer Tools
3. Go to **Storage** tab → **Cookies** → `https://www.youtube.com`
4. Export cookies using similar process

### Important YouTube Cookies

These are the key cookies YouTube uses for authentication:
- `SAPISID`
- `APISID` 
- `HSID`
- `SID`
- `SSID`
- `LOGIN_INFO`
- `SESSION_TOKEN`

## Cookie File Format

The cookie file should be in Netscape format:

```
# Netscape HTTP Cookie File
# http://curl.haxx.se/rfc/cookie_spec.html
.youtube.com	TRUE	/	FALSE	1640995200	SAPISID	your_cookie_value_here
.youtube.com	TRUE	/	FALSE	1640995200	APISID	your_cookie_value_here
# ... more cookies
```

## Testing Your Setup

### Local Testing

1. **Start the API server:**
```bash
python yt_dlp_api.py --debug
```

2. **Run the test script:**
```bash
python test_api_locally.py
```

3. **Manual test with curl:**
```bash
curl -X POST http://localhost:5002/info \
  -H "Content-Type: application/json" \
  -d '{"url":"https://youtube.com/watch?v=dQw4w9WgXcQ","options":{"cookiesfrombrowser":"chrome"}}'
```

### VPS Testing

1. **Upload your cookie file to VPS:**
```bash
scp youtube_cookies.txt user@your-vps:/path/to/cookies/
```

2. **Test with cookie file:**
```bash
curl -X POST http://your-vps:5002/info \
  -H "Content-Type: application/json" \
  -d '{"url":"https://youtube.com/watch?v=dQw4w9WgXcQ","options":{"cookiefile":"/path/to/cookies/youtube_cookies.txt"}}'
```

## Troubleshooting

### "Sign in to confirm you're not a bot" Error

This means cookie authentication is required. Solutions:

1. **Verify cookies are fresh** - YouTube rotates cookies frequently
2. **Re-export cookies** if they're older than a few hours
3. **Make sure you're logged in** to YouTube when exporting
4. **Try different browser** - some work better than others
5. **Clear browser cache** and re-login before exporting

### Cookie Extraction Issues

**Browser extension not working?**
- Try the manual extraction method
- Use private/incognito mode for export
- Make sure you're on `youtube.com` when exporting

**Cookies expire quickly?**
- YouTube rotates cookies for security
- Export fresh cookies before each deployment
- Consider using a dedicated YouTube account

### VPS-Specific Issues

**No GUI browsers on VPS?**
- Use cookie file method only
- Export cookies on your local machine
- Upload cookie file to VPS

**Permission issues?**
- Make sure cookie file is readable: `chmod 644 youtube_cookies.txt`
- Check file path is correct in API request

## Security Notes

⚠️ **Important Security Considerations:**

1. **Keep cookies private** - they provide access to your YouTube account
2. **Use dedicated account** - consider creating a separate YouTube account for API use
3. **Regular rotation** - export fresh cookies regularly
4. **Secure storage** - store cookie files with proper permissions on VPS
5. **Account risk** - YouTube may temporarily ban accounts for excessive API usage

## Rate Limiting

To avoid YouTube rate limits and detection:

- **Add delays** between requests: `{"sleep_interval": 2}`
- **Limit concurrent requests** on your VPS
- **Monitor usage** to stay under YouTube's thresholds
- **Use residential IP** if possible (not datacenter IPs)

## Working Example

Here's a complete working example for VPS deployment:

```json
{
    "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
        "cookiefile": "/home/user/cookies/youtube_cookies.txt",
        "sleep_interval": 2,
        "max_sleep_interval": 5,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
}
```

## Next Steps

1. **Test locally first** using the test script
2. **Export cookies** using browser extension
3. **Upload to VPS** and test with cookie file
4. **Monitor for errors** and refresh cookies as needed

Once cookie authentication is working locally, the same setup will work on your VPS! 🚀 
