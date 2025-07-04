# yt-dlp API Format Guide

## ✨ **NEW: Async Job Queue System**

**All download and transcription requests now return job IDs immediately!** No more waiting for downloads to complete - queue your jobs and check progress separately.

### 🚀 **Async Workflow:**
1. **Queue Job** → Get job ID instantly
2. **Check Status** → Monitor progress 
3. **Get Results** → Download completed videos/transcriptions
4. **Background Processing** → Multiple videos processed simultaneously

## Quick Reference Table

| **Request Type** | **Endpoint** | **Response** | **Description** |
|------------------|--------------|--------------|-----------------|
| **🎥 Video Download** | `/download` | `job_id` | Queue video download, returns job ID immediately |
| **🎵 Audio Download** | `/download` with audio format | `job_id` | Queue audio extraction with job ID |
| **📋 Channel Bulk** | `/channel` with `download: true` | `job_id` | Queue multiple video downloads from channel |
| **🎤 Transcription** | `/transcribe` | `job_id` | Queue audio transcription with job ID |
| **🔍 Video Search** | `/search` with `download: true` | `job_id` | Search and download videos with job ID |
| **📊 Job Status** | `/job/{job_id}` | Status object | Check job progress and completion |
| **📦 Job Results** | `/job/{job_id}/results` | Full results | Get all job data when completed |
| **⬇️ Download Video** | `/job/{job_id}/download/0` | Binary data | Download specific video from job |
| **📝 Get Transcriptions** | `/job/{job_id}/transcriptions` | Text/JSON | Get all transcriptions from job |

## Authentication

All API requests require authentication using the `X-API-Key` header:

```bash
-H "X-API-Key: your_api_key"
```

## 🔄 **Async Workflow Examples**

### **Step 1: Queue a Download Job**
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestvideo[height=720]+bestaudio",
    "transcribe": true,
    "transcribe_model": "base"
  }'
```

**Response:**
```json
{
  "success": true,
  "job_id": "abc-123-def-456",
  "status": "queued",
  "message": "Download job queued successfully",
  "queue_position": 2,
  "endpoints": {
    "status": "/job/abc-123-def-456",
    "results": "/job/abc-123-def-456/results",
    "download": "/job/abc-123-def-456/download/0"
  }
}
```

### **Step 2: Check Job Status**
```bash
curl -X GET http://localhost:5002/job/abc-123-def-456 \
  -H "X-API-Key: your_api_key"
```

**Response (In Progress):**
```json
{
  "id": "abc-123-def-456",
  "type": "download",
  "status": "processing",
  "progress_percent": 65,
  "current_item": "Downloading video...",
  "completed_items": 0,
  "total_items": 1,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:31:23"
}
```

**Response (Completed):**
```json
{
  "id": "abc-123-def-456",
  "type": "download", 
  "status": "completed",
  "progress_percent": 100,
  "completed_items": 1,
  "total_items": 1,
  "result_summary": "Downloaded: Rick Astley - Never Gonna Give You Up"
}
```

### **Step 3: Get Job Results**
```bash
curl -X GET http://localhost:5002/job/abc-123-def-456/results \
  -H "X-API-Key: your_api_key"
```

**Response:**
```json
{
  "job_id": "abc-123-def-456",
  "status": "completed",
  "total_videos": 1,
  "successful_downloads": 1,
  "transcriptions_count": 1,
  "results": [
    {
      "title": "Rick Astley - Never Gonna Give You Up",
      "file_size": 15728640,
      "format": "mp4",
      "download_time": 1705312345
    }
  ],
  "transcriptions": [
    {
      "video_title": "Rick Astley - Never Gonna Give You Up",
      "transcription": {
        "text": "We're no strangers to love...",
        "language": "en",
        "segments": [...]
      }
    }
  ]
}
```

### **Step 4: Download the Video File**
```bash
curl -X GET http://localhost:5002/job/abc-123-def-456/download/0 \
  -H "X-API-Key: your_api_key" \
  -o video.mp4
```

## 🔍 **NEW: Video Search with Async Processing**

Search videos across multiple platforms with optional download and transcription:

### **Basic Search (Info Only)**
```bash
curl -X POST http://localhost:5002/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "query": "python programming tutorial",
    "platform": "youtube",
    "max_results": 10,
    "video_type": "video"
  }'
```

### **Search + Download + Transcribe (Async)**
```bash
curl -X POST http://localhost:5002/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "query": "javascript tutorial",
    "platform": "youtube", 
    "max_results": 5,
    "video_type": "all",
    "download": true,
    "transcribe": true,
    "transcribe_model": "small",
    "transcribe_format": "json"
  }'
```

**Response:**
```json
{
  "success": true,
  "job_id": "search-789-xyz-123",
  "status": "queued",
  "message": "Search job queued successfully for query: \"javascript tutorial\"",
  "search_params": {
    "query": "javascript tutorial",
    "type": "all",
    "platform": "youtube",
    "max_results": 5,
    "download": true,
    "transcribe": true
  },
  "endpoints": {
    "status": "/job/search-789-xyz-123",
    "results": "/job/search-789-xyz-123/results",
    "transcriptions": "/job/search-789-xyz-123/transcriptions"
  }
}
```

### **Search Platform Options**

| **Platform** | **Value** | **Video Types Supported** |
|--------------|-----------|---------------------------|
| **YouTube** | `youtube` | video, shorts, live, all |
| **TikTok** | `tiktok` | video, all |
| **Twitter/X** | `twitter` | video, all |
| **Instagram** | `instagram` | video, all |

## 📋 **Enhanced Channel Processing**

The `/channel` endpoint now supports async processing for bulk downloads:

### **Channel Info Only (Sync)**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name",
    "max_videos": 10,
    "video_types": ["regular", "shorts"]
  }'
```

### **Channel Bulk Download (Async)**
```bash
curl -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name",
    "max_videos": 5,
    "video_types": ["regular"],
    "download": true,
    "transcribe": true,
    "transcribe_model": "base",
    "format": "bestaudio[filesize<30M]"
  }'
```

**Returns job_id for async processing of multiple videos.**

## 📊 **Job Management Endpoints**

### **List All Jobs**
```bash
curl -X GET http://localhost:5002/jobs \
  -H "X-API-Key: your_api_key"
```

### **Get Job Status**
```bash
curl -X GET http://localhost:5002/job/{job_id} \
  -H "X-API-Key: your_api_key"
```

### **Get Job Transcriptions Only**
```bash
curl -X GET http://localhost:5002/job/{job_id}/transcriptions \
  -H "X-API-Key: your_api_key"
```

### **Download Specific Video from Job**
```bash
# Download first video (index 0)
curl -X GET http://localhost:5002/job/{job_id}/download/0 \
  -H "X-API-Key: your_api_key" \
  -o video_0.mp4

# Download second video (index 1)  
curl -X GET http://localhost:5002/job/{job_id}/download/1 \
  -H "X-API-Key: your_api_key" \
  -o video_1.mp4
```

## ⚡ **Queue Management**

### **Get Queue Statistics**
```bash
curl -X GET http://localhost:5002/queue/stats \
  -H "X-API-Key: your_api_key"
```

**Response:**
```json
{
  "success": true,
  "queue_stats": {
    "total_processed": 245,
    "total_failed": 12,
    "current_queue_size": 3,
    "active_workers": 2
  },
  "worker_info": {
    "max_workers": 3,
    "active_workers": 2, 
    "is_running": true
  },
  "queue_info": {
    "max_queue_size": 100,
    "current_size": 3,
    "is_full": false
  }
}
```

### **Restart Queue Workers**
```bash
curl -X POST http://localhost:5002/queue/control \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"action": "restart_workers"}'
```

## 🎯 **Legacy Sync Endpoints (Still Available)**

Some endpoints still work synchronously for simple use cases:

### **Quick Video Info (Sync)**
```bash
curl -X POST http://localhost:5002/info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"url": "https://youtube.com/watch?v=VIDEO_ID"}'
```

### **File Upload Transcription (Sync)**
```bash
curl -X POST http://localhost:5002/transcribe-file \
  -H "X-API-Key: your_api_key" \
  -F "file=@video.mp4" \
  -F "model=base" \
  -F "format=json"
```

## 📝 **Job Status Types**

| **Status** | **Description** |
|------------|-----------------|
| `queued` | Job added to queue, waiting for worker |
| `processing` | Job currently being processed |
| `completed` | Job finished successfully |
| `failed` | Job failed with error |

## ⚠️ **Rate Limits & Best Practices**

### **Queue Limits**
- **Max Queue Size**: 100 jobs (configurable)
- **Max Workers**: 3 simultaneous jobs (configurable)
- **Job Timeout**: 30 minutes per video
- **Queue Full Response**: HTTP 503 with retry message

### **Recommended Usage**
- **Small Videos** (≤50MB): 5-10 per job
- **Large Videos** (>50MB): 2-3 per job  
- **Audio Only**: 10-15 per job
- **With Transcription**: Same limits (minimal overhead)

### **Performance Optimization**
```bash
# Good: Queue multiple small jobs
curl -X POST /download -d '{"url": "...", "format": "bestaudio[filesize<30M]"}'

# Better: Use channel endpoint for bulk
curl -X POST /channel -d '{"url": "...", "max_videos": 5, "download": true}'

# Best: Search + download in one job
curl -X POST /search -d '{"query": "...", "max_results": 5, "download": true}'
```

## 🔧 **Server Configuration**

### **Starting with Custom Queue Settings**
```bash
python yt_dlp_api.py --workers 5 --queue-size 200 --port 5002
```

### **Environment Variables**
```bash
export API_KEY="your-secret-api-key"
export WORKERS=3
export QUEUE_SIZE=100
```

## 🎬 **Transcription with OpenAI Whisper**

### **Async Transcription Job**
```bash
curl -X POST http://localhost:5002/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "model": "small",
    "language": "en",
    "format": "srt"
  }'
```

**Response:**
```json
{
  "success": true,
  "job_id": "transcribe-456-abc-789",
  "status": "queued",
  "message": "Transcription job queued successfully",
  "endpoints": {
    "status": "/job/transcribe-456-abc-789",
    "results": "/job/transcribe-456-abc-789/results",
    "transcriptions": "/job/transcribe-456-abc-789/transcriptions"
  }
}
```

### **Download + Transcribe in One Job**
```bash
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "bestvideo[height=720]+bestaudio",
    "transcribe": true,
    "transcribe_model": "base",
    "transcribe_format": "both"
  }'
```

### **Whisper Model Options**

| **Model** | **Size** | **Speed** | **Accuracy** | **Async Recommended** |
|-----------|----------|-----------|--------------|----------------------|
| `tiny` | ~39 MB | Fastest | Basic | ✅ Good for bulk jobs |
| `base` | ~74 MB | Fast | Good | ✅ Balanced choice |
| `small` | ~244 MB | Medium | Better | ✅ High quality |
| `medium` | ~769 MB | Slow | High | ⚠️ Use for important content |
| `large` | ~1550 MB | Slowest | Highest | ❌ Not recommended for async |

### **Transcription Formats**

| **Format** | **Output** | **Use Case** |
|------------|------------|--------------|
| `json` | Full segments + timing | API integration |
| `text` | Plain text only | Simple transcripts |
| `srt` | SRT subtitles | Video players |
| `vtt` | WebVTT subtitles | Web players |
| `both` | Video data + transcript | Complete package |

## 🔄 **Migration from Sync to Async**

### **Old Sync Way:**
```bash
# This still works but blocks until complete
curl -X POST /download -d '{"url": "..."}' 
# Returns video data after 30-60 seconds
```

### **New Async Way:**
```bash
# Step 1: Queue (instant response)
curl -X POST /download -d '{"url": "..."}' 
# Returns: {"job_id": "abc-123"}

# Step 2: Check status (optional)
curl -X GET /job/abc-123
# Returns: {"status": "processing", "progress": 45}

# Step 3: Get results when ready
curl -X GET /job/abc-123/results
# Returns: Full job data

# Step 4: Download video
curl -X GET /job/abc-123/download/0 -o video.mp4
```

## 🔌 **API Information Endpoint**

### **Get Full API Capabilities**
```bash
curl -X GET http://localhost:5002/ 
```

**Response includes:**
- Authentication requirements
- Queue statistics 
- Available endpoints
- Async workflow examples
- Worker information

## 🐳 **Docker & Deployment**

### **Docker with Queue Configuration**
```yaml
# docker-compose.yml
services:
  yt-dlp-api:
    build: .
    environment:
      - API_KEY=your-secret-key
      - WORKERS=5
      - QUEUE_SIZE=200
    command: ["python", "yt_dlp_api.py", "--workers", "5", "--queue-size", "200"]
```

### **Health Check**
```bash
curl -X GET http://localhost:5002/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "queue_stats": {
    "active_workers": 2,
    "queue_size": 5,
    "is_running": true
    }
}
```

## 🎯 **Complete Example: Bulk Channel Processing**

```bash
# 1. Queue channel download job
RESPONSE=$(curl -s -X POST http://localhost:5002/channel \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "url": "https://youtube.com/@channel_name",
    "max_videos": 10,
    "video_types": ["regular", "shorts"],
    "download": true,
    "transcribe": true,
    "transcribe_model": "base",
    "format": "bestaudio[filesize<25M]"
  }')

# 2. Extract job ID
JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# 3. Monitor progress
while true; do
  STATUS=$(curl -s -X GET http://localhost:5002/job/$JOB_ID \
    -H "X-API-Key: your_api_key" | jq -r '.status')
  
  if [ "$STATUS" = "completed" ]; then
    echo "Job completed!"
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Job failed!"
    break
  else
    echo "Status: $STATUS"
    sleep 10
  fi
done

# 4. Get results
curl -s -X GET http://localhost:5002/job/$JOB_ID/results \
  -H "X-API-Key: your_api_key" | jq .

# 5. Download all videos
curl -s -X GET http://localhost:5002/job/$JOB_ID/results \
  -H "X-API-Key: your_api_key" | jq -r '.results | length' | \
while read -r count; do
  for i in $(seq 0 $((count-1))); do
    curl -X GET http://localhost:5002/job/$JOB_ID/download/$i \
  -H "X-API-Key: your_api_key" \
      -o "video_$i.mp4"
  done
done
```

## 🚀 **Performance Benefits**

### **Before (Sync):**
- ❌ Client waits 30-60 seconds per video
- ❌ One video at a time  
- ❌ Connection timeouts on large files
- ❌ No progress visibility

### **After (Async):**
- ✅ Instant job ID response (< 1 second)
- ✅ 3 videos processed simultaneously
- ✅ No connection timeouts
- ✅ Real-time progress monitoring
- ✅ Background processing continues if client disconnects
- ✅ Results available anytime after completion

## 🔍 **Troubleshooting**

### **Queue Full (HTTP 503)**
```json
{
  "success": false,
  "error": "Job queue is full. Please try again later.",
  "queue_stats": {"current_queue_size": 100}
}
```
**Solution:** Wait or increase queue size with `--queue-size` parameter.

### **Job Not Found (HTTP 404)**
```json
{"error": "Job not found"}
```
**Solution:** Check job ID spelling or use `/jobs` to list all jobs.

### **Worker Errors**
```bash
# Restart workers
curl -X POST /queue/control -d '{"action": "restart_workers"}'
```

## 📚 **API Version History**

- **v3.0.0**: Async job queue system, search functionality
- **v2.0.0**: Channel processing, enhanced transcription
- **v1.0.0**: Basic download and transcription

---

## 💡 **Tips for Optimal Usage**

1. **Use async endpoints** for any job that might take >10 seconds
2. **Monitor queue stats** to avoid hitting limits
3. **Use appropriate video quality** to manage file sizes
4. **Batch similar jobs** using channel or search endpoints
5. **Check job status periodically** rather than polling continuously
6. **Use audio formats** for faster transcription jobs
7. **Set reasonable max_videos** limits (≤10 for most use cases)