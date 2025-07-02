# yt-dlp API Docker Deployment

This guide explains how to build and run the yt-dlp HTTP API using Docker.

## 🐳 Quick Start

### Using Docker Compose (Recommended)

```bash
# Build and start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Using Docker Commands

```bash
# Build the image
docker build -t yt-dlp-api .

# Run the container
docker run -d \
  --name yt-dlp-api \
  -p 5002:5002 \
  --restart unless-stopped \
  yt-dlp-api

# View logs
docker logs -f yt-dlp-api

# Stop and remove
docker stop yt-dlp-api
docker rm yt-dlp-api
```

## 📋 Prerequisites

- Docker installed on your system
- Docker Compose (optional but recommended)

## 🔧 Configuration

### Environment Variables

You can customize the API using environment variables:

```yaml
# In docker-compose.yml
environment:
  - FLASK_ENV=production
  - PYTHONUNBUFFERED=1
```

### Port Configuration

By default, the API runs on port 5002. To use a different port:

```bash
# Docker run
docker run -p 8080:5002 yt-dlp-api

# Docker compose - edit docker-compose.yml
ports:
  - "8080:5002"
```

### Resource Limits

The docker-compose.yml includes resource limits:
- Memory: 2GB limit, 512MB reserved
- CPU: 1.0 limit, 0.5 reserved

Adjust these based on your needs.

## 🚀 Usage

Once running, the API will be available at:
- `http://localhost:5002` (or your configured port)

### Test the API

```bash
# Health check
curl http://localhost:5002/

# Download a video
curl -X POST http://localhost:5002/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  --output video.mp4
```

## 🔍 Health Monitoring

The container includes health checks:
- Endpoint: `http://localhost:5002/`
- Interval: 30 seconds
- Timeout: 10 seconds
- Retries: 3

Check health status:
```bash
docker ps  # Shows health status
docker inspect yt-dlp-api | grep Health  # Detailed health info
```

## 🛠️ Development

### Building with Custom Options

```bash
# Build with custom tag
docker build -t my-yt-dlp-api:v1.0 .

# Build with no cache
docker build --no-cache -t yt-dlp-api .
```

### Debugging

```bash
# Run interactively for debugging
docker run -it --rm \
  -p 5000:5000 \
  yt-dlp-api /bin/bash

# View container logs
docker logs yt-dlp-api

# Execute commands in running container
docker exec -it yt-dlp-api /bin/bash
```

## 📦 What's Included

The Docker image includes:
- Python 3.11 runtime
- FFmpeg for video processing
- All required Python dependencies
- Health check endpoint
- Non-root user for security
- Optimized build layers

## 🔒 Security Features

- Runs as non-root user (`appuser`)
- Minimal base image (Python slim)
- No unnecessary packages
- Health checks for monitoring

## 🚨 Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   # Check what's using port 5002
netstat -tulpn | grep 5002
   # Or use different port
   docker run -p 5001:5000 yt-dlp-api
   ```

2. **Container won't start**
   ```bash
   # Check logs
   docker logs yt-dlp-api
   ```

3. **FFmpeg not found**
   - FFmpeg is included in the Docker image
   - If issues persist, rebuild the image

### Performance Tips

- Increase memory limits for large videos
- Use SSD storage for better I/O performance
- Monitor resource usage with `docker stats`

## 📊 Monitoring

```bash
# Real-time resource usage
docker stats yt-dlp-api

# Container information
docker inspect yt-dlp-api

# Health status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## 🔄 Updates

To update the API:

```bash
# Rebuild image
docker-compose build --no-cache

# Restart with new image
docker-compose up -d
``` 
