# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=yt_dlp_api.py
ENV FLASK_ENV=production

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg and Chrome
# Fix GPG signature issues by updating package lists and using newer Chrome setup
RUN apt-get clean && \
    apt-get update --allow-releaseinfo-change && \
    apt-get install -y \
        ffmpeg \
        curl \
        wget \
        gnupg \
        ca-certificates \
        apt-transport-https \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies including ytc for automated cookies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir ytc

# Create directories and set up permissions BEFORE switching to appuser
RUN mkdir -p /app/YTC-DL /app/cookies && \
    chmod 755 /app/YTC-DL /app/cookies

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy application files
COPY yt_dlp_api.py .
COPY yt_dlp_memory_downloader.py .

# Create container initialization script
COPY <<EOF /app/init_container.py
#!/usr/bin/env python3
"""
Container initialization script to set up cookies and permissions
This runs at container startup to ensure everything is configured correctly
"""
import os
import shutil
import time

def setup_cookie_directories():
    """Ensure cookie directories exist with proper permissions"""
    directories = ['/app/YTC-DL', '/app/cookies']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        # Make sure appuser can write to these directories
        try:
            os.chmod(directory, 0o755)
        except:
            pass
    print("✅ Cookie directories initialized")

def copy_existing_cookies():
    """Copy any existing cookies to centralized location"""
    cookie_sources = [
        '/app/cookies/youtube_cookies.txt',
        '/app/cookies/youtube-cookies.txt',
        '/app/cookies/cookies.txt'
    ]
    
    target = '/app/YTC-DL/cookies.txt'
    
    for source in cookie_sources:
        if os.path.exists(source) and not os.path.exists(target):
            try:
                shutil.copy2(source, target)
                os.chmod(target, 0o644)
                print(f"✅ Copied cookies from {source} to {target}")
                break
            except Exception as e:
                print(f"⚠️ Could not copy {source}: {e}")

def test_ytc_installation():
    """Test if ytc library is working"""
    try:
        import ytc
        print("✅ ytc library available for automated cookies")
        return True
    except ImportError as e:
        print(f"⚠️ ytc library not available: {e}")
        return False

def main():
    print("🚀 Initializing yt-dlp API container...")
    setup_cookie_directories()
    copy_existing_cookies()
    test_ytc_installation()
    print("✅ Container initialization complete!")

if __name__ == '__main__':
    main()
EOF

# Create startup script that runs initialization then starts the API
COPY <<EOF /app/startup.sh
#!/bin/bash
# Run initialization
python3 /app/init_container.py

# Start the API
exec python3 yt_dlp_api.py --host 0.0.0.0 --port 5002
EOF

# Make scripts executable BEFORE switching to non-root user
RUN chmod +x /app/init_container.py && \
    chmod +x /app/startup.sh

# Change ownership of app directory to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5002/ || exit 1

# Run the startup script
CMD ["/app/startup.sh"] 