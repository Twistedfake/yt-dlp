# 🍪 Chrome Cookies Update - YouTube Bot Detection Fix

## ✅ **What's Been Updated**

Your yt-dlp API has been enhanced to bypass YouTube's bot detection using Chrome cookies!

### **Files Updated:**

1. **`yt_dlp_api.py`** - Added anti-bot measures to all endpoints
2. **`Dockerfile`** - Added Google Chrome installation
3. **`docker-compose.yml`** - Added optional cookie volume mounts
4. **`API_TEST_COMMANDS.md`** - Added cookie usage examples

---

## 🔧 **New Features**

### **Automatic Chrome Cookies**
- All endpoints now automatically use Chrome cookies
- Bypasses "Sign in to confirm you're not a bot" errors
- Works with `/download`, `/info`, `/subtitles`, and `/channel` endpoints

### **Browser Options**
```json
{
  "options": {
    "cookiesfrombrowser": ["chrome", null, null, null],  // Default
    "cookiesfrombrowser": ["firefox", null, null, null], // Alternative
    "cookiesfrombrowser": ["edge", null, null, null]     // Alternative
  }
}
```

### **Enhanced Headers**
- Browser-like User-Agent
- Proper HTTP headers (Accept-Language, DNT, etc.)
- Rate limiting to avoid detection
- Referer headers for YouTube

---

## 🚀 **How to Deploy Updated Version**

### **Rebuild Docker Container:**
```bash
# Stop current container
docker-compose down

# Rebuild with Chrome support
docker-compose build --no-cache

# Start updated container
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f
```

---

## 🧪 **Test Commands**

### **1. Health Check (Port Updated to 5002)**
```bash
curl https://crispbot.bloxboom.com/yt/
```

### **2. Test YouTube Download (Should Now Work!)**
```bash
# Test the Rick Roll video that was failing before
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  --output rick_roll_fixed.mp4
```

### **3. Test Different Videos**
```bash
# Test a different YouTube video
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=9bZkp7q19f0"}' \
  --output test_video.mp4

# Test YouTube Shorts
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/shorts/yFLFkdFvNh0"}' \
  --output shorts_test.mp4
```

### **4. Test Info Endpoint**
```bash
# Get video info (should work without bot detection now)
curl -X POST https://crispbot.bloxboom.com/yt/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### **5. Test Audio Extraction**
```bash
# Download audio only
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "extractaudio": true,
      "audioformat": "mp3"
    }
  }' \
  --output rick_roll_audio.mp3
```

### **6. Test Custom Browser Cookies**
```bash
# Use Firefox cookies instead of Chrome
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "cookiesfrombrowser": ["firefox", null, null, null]
    }
  }' \
  --output test_firefox.mp4
```

---

## 🎯 **Expected Results**

### **Before Update:**
```json
{
  "error": "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot...",
  "success": false
}
```

### **After Update:**
```json
{
  "success": true,
  "X-Video-Title": "Rick Astley - Never Gonna Give You Up",
  "X-Video-Duration": "212",
  "X-Video-Format": "mp4"
}
```

---

## 🔍 **Troubleshooting**

### **If Still Getting Bot Detection:**

1. **Check Chrome Installation:**
```bash
docker exec -it yt-dlp-api google-chrome --version
```

2. **Try Different Browser:**
```bash
# Test with Firefox cookies
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "cookiesfrombrowser": ["firefox", null, null, null]
    }
  }'
```

3. **Check Logs:**
```bash
docker-compose logs -f yt-dlp-api
```

4. **Try Rate Limiting:**
```bash
curl -X POST https://crispbot.bloxboom.com/yt/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "options": {
      "sleep_interval": 3,
      "max_sleep_interval": 5
    }
  }'
```

---

## 🎉 **Summary**

Your yt-dlp API now:
- ✅ **Bypasses YouTube bot detection**
- ✅ **Uses Chrome cookies automatically**  
- ✅ **Supports multiple browsers**
- ✅ **Has enhanced headers for stealth**
- ✅ **Includes rate limiting**
- ✅ **Works with all endpoints**

**The YouTube download that was failing should now work perfectly!** 🚀 