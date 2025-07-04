#!/usr/bin/env python3
"""
Fix the sudo issue in yt_dlp_api.py
This script updates the execute endpoint to be smarter about sudo usage
"""

import re
import os
import shutil
import subprocess

def fix_sudo_issue():
    api_file = '/app/yt_dlp_api.py'
    backup_file = '/app/yt_dlp_api.py.backup'
    
    # Create backup if it doesn't exist
    if not os.path.exists(backup_file):
        shutil.copy2(api_file, backup_file)
        print(f"✅ Created backup: {backup_file}")
    
    # Read the current file
    with open(api_file, 'r') as f:
        content = f.read()
    
    # Define the old and new patterns
    old_pattern = r'use_sudo = data\.get\(\'sudo\', True\)  # Default to using sudo'
    
    # Smart sudo detection: default to False in container environments
    def should_use_sudo_default():
        # Check if we're in a Docker container
        if os.path.exists('/.dockerenv'):
            return False
        # Check if sudo is available
        try:
            subprocess.run(['which', 'sudo'], capture_output=True, check=True, timeout=2)
            return True
        except:
            return False
    
    new_code = '''# Smart sudo detection: default to False in container environments
                def should_use_sudo_default():
                    # Check if we're in a Docker container
                    if os.path.exists('/.dockerenv'):
                        return False
                    # Check if sudo is available
                    try:
                        subprocess.run(['which', 'sudo'], capture_output=True, check=True, timeout=2)
                        return True
                    except:
                        return False
                
                use_sudo = data.get('sudo', should_use_sudo_default())'''
    
    # Apply the fix
    if old_pattern in content:
        content = re.sub(old_pattern, new_code, content)
        
        # Write the updated content
        with open(api_file, 'w') as f:
            f.write(content)
        
        print("✅ Successfully applied sudo fix to yt_dlp_api.py")
        print("🔄 The API will now detect container environments and avoid using sudo")
        return True
    else:
        print("⚠️ Pattern not found - API may already be fixed or format changed")
        return False

if __name__ == '__main__':
    success = fix_sudo_issue()
    if success:
        print("\n🚀 Next steps:")
        print("1. Restart the Python process: kill -9 $(pidof python3)")
        print("2. Or restart the container: docker-compose restart")
        print("3. Test the fix with: curl -X POST .../execute -d '{\"command\": \"ffmpeg -version\", \"sudo\": false}'")
    else:
        print("\n❌ Fix failed - manual intervention required") 