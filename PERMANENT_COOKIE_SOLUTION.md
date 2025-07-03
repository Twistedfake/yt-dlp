# 🍪 Permanent Cookie Solution for yt-dlp API

## 🎯 **Problem Solved**

This permanent solution eliminates the need to manually fix cookies every time you rebuild the Docker container. The API now automatically handles YouTube authentication using multiple fallback methods.

---

## ✅ **What's Been Fixed Permanently**

### **1. Docker Image Enhancements**
- **ytc library pre-installed** - Automated cookie service built into the image
- **Cookie directories pre-created** - `/app/YTC-DL` and `/app/cookies` with proper permissions
- **Initialization script** - Runs on every container startup to set up cookies
- **Startup automation** - Container handles all cookie setup automatically

### **2. API Code Improvements**
- **Auto-setup on startup** - Copies existing cookies and tests ytc library
- **Centralized cookie management** - All cookies stored in `/app/YTC-DL/`
- **Enhanced fallback system** - Multiple cookie sources with priority order
- **Better error handling** - Clear messages when cookies fail

### **3. Deployment Automation**
- **One-command deployment** - `./deploy-permanent-fix.sh` handles everything
- **Comprehensive testing** - Automatically tests API and YouTube functionality
- **Status reporting** - Clear feedback on what's working

---

## 🔧 **How It Works**

### **Container Startup Flow**
1. **Initialization Script** (`/app/init_container.py`) runs first:
   - Creates cookie directories with proper permissions
   - Copies any existing cookies to centralized location
   - Tests ytc library installation
   - Reports status

2. **API Startup** (`yt_dlp_api.py`) then:
   - Sets up centralized cookie directory
   - Auto-copies cookies from various sources
   - Attempts to get fresh ytc cookies
   - Lists available cookie files

### **Cookie Priority System**
1. **YTC Automated Cookies** (Primary)
   - Fresh cookies from ytc remote service
   - Cached for 6 hours
   - Automatically refreshed

2. **Manual Cookies** (Fallback)
   - `/app/YTC-DL/cookies.txt` (centralized location)
   - Auto-copied from various sources on startup

3. **Browser Cookies** (Last Resort)
   - `cookiesfrombrowser` options
   - Chrome, Firefox, Edge support

---

## 🚀 **Deployment Instructions**

### **Option 1: Automated Deployment (Recommended)**
```bash
# Make the deployment script executable
chmod +x deploy-permanent-fix.sh

# Run the complete deployment
./deploy-permanent-fix.sh
```

### **Option 2: Manual Deployment**
```bash
# Stop existing container
docker-compose down

# Build with permanent fixes
docker-compose build --no-cache

# Start with auto-setup
docker-compose up -d

# Check status
docker-compose logs -f
```

---

## 📊 **Testing Your Setup**

### **1. Health Check**
```bash
curl http://localhost:5002/health
```

### **2. Cookie Status**
```bash
curl http://localhost:5002/cookie-status
```

### **3. YouTube Test**
```bash
curl -X POST http://localhost:5002/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### **4. Download Test**
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  --output test_video.mp4
```

---

## 🛠️ **For VPS Deployment**

### **API Endpoints for Remote Management**
```bash
# Health check
curl https://crispbot.bloxboom.com/yt/health

# Cookie status
curl -H "X-API-Key: YOUR_KEY" https://crispbot.bloxboom.com/yt/cookie-status

# Refresh ytc cookies
curl -X POST -H "X-API-Key: YOUR_KEY" https://crispbot.bloxboom.com/yt/refresh-ytc-cookies

# Test YouTube
curl -X POST -H "X-API-Key: YOUR_KEY" https://crispbot.bloxboom.com/yt/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

---

## 📁 **File Structure**

```
yt-dlp/
├── Dockerfile                 # Enhanced with ytc + initialization
├── docker-compose.yml         # Cookie volume mounts
├── requirements.txt           # ytc library included
├── yt_dlp_api.py             # Auto-setup on startup
├── deploy-permanent-fix.sh    # One-command deployment
├── yt_dlp/cookies/           # Host cookie directory
│   └── youtube_cookies.txt   # Your manual cookies (optional)
└── Container:
    ├── /app/YTC-DL/          # Centralized cookie directory
    │   └── cookies.txt       # Primary cookie file
    ├── /app/cookies/         # Volume mount from host
    ├── /app/init_container.py # Startup initialization
    └── /app/startup.sh       # Container entry point
```

---

## 🔄 **Container Lifecycle**

### **Every Container Start:**
1. ✅ Directories created with proper permissions
2. ✅ Existing cookies auto-copied to centralized location
3. ✅ ytc library tested and fresh cookies attempted
4. ✅ Available cookie files listed
5. ✅ API starts with full cookie support

### **No Manual Intervention Required:**
- No more permission fixes
- No more cookie copying
- No more ytc installation
- No more directory creation

---

## 🐛 **Troubleshooting**

### **If YouTube Still Fails:**
1. **Check Container Logs:**
   ```bash
   docker-compose logs yt-dlp-api
   ```

2. **Verify Cookie Status:**
   ```bash
   curl http://localhost:5002/cookie-status
   ```

3. **Test Different Cookie Sources:**
   ```bash
   # Try with manual cookie file
   curl -X POST http://localhost:5002/info \
     -H "Content-Type: application/json" \
     -d '{"url": "...", "options": {"cookiefile": "/app/YTC-DL/cookies.txt"}}'
   
   # Try with browser cookies
   curl -X POST http://localhost:5002/info \
     -H "Content-Type: application/json" \
     -d '{"url": "...", "options": {"cookiesfrombrowser": "chrome"}}'
   ```

### **Common Issues:**
- **"No cookie files found"** → Place cookies in `yt_dlp/cookies/youtube_cookies.txt`
- **"ytc library not available"** → Rebuild container: `docker-compose build --no-cache`
- **"Permission denied"** → Fixed automatically by initialization script

---

## 🎉 **Benefits of This Solution**

✅ **Zero Manual Setup** - Everything happens automatically
✅ **Survives Rebuilds** - Permanent fix in Docker image
✅ **Multiple Fallbacks** - ytc → manual → browser cookies
✅ **VPS Compatible** - Works remotely via API
✅ **Self-Healing** - Auto-fixes permissions and copies cookies
✅ **Future-Proof** - Handles new yt-dlp updates

---

## 📝 **Summary**

This permanent solution transforms your yt-dlp API from a manual setup nightmare into a fully automated, self-configuring system. Once deployed, you'll never need to manually fix cookies again - the container handles everything automatically on startup.

**Deploy once, work forever!** 🚀 