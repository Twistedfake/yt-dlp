#!/usr/bin/env python3
"""
Simple script to add cookie file support to yt_dlp_api.py
"""

import sys
import os

def add_cookie_support():
    api_file = "/app/yt_dlp_api.py"
    
    if not os.path.exists(api_file):
        print("ERROR: API file not found!")
        return False
    
    # Read the file
    with open(api_file, 'r') as f:
        content = f.read()
    
    # Check if already added
    if 'opts.get(\'cookies\')' in content:
        print("Cookie support already added!")
        return True
    
    # Find the line with "return enhanced_opts" and add before it
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        if line.strip() == 'return enhanced_opts':
            # Get the indentation from the current line
            indent = len(line) - len(line.lstrip())
            space = ' ' * indent
            
            # Add cookie handling before return
            new_lines.append(f"{space}# Handle cookies file parameter")
            new_lines.append(f"{space}cookies = opts.get('cookies')")
            new_lines.append(f"{space}if cookies:")
            new_lines.append(f"{space}    if cookies.startswith('/'):")
            new_lines.append(f"{space}        enhanced_opts['cookiefile'] = cookies")
            new_lines.append(f"{space}    else:")
            new_lines.append(f"{space}        enhanced_opts['cookiefile'] = f'/app/cookies/{{cookies}}'")
            new_lines.append("")
        
        new_lines.append(line)
    
    # Write back the file
    with open(api_file, 'w') as f:
        f.write('\n'.join(new_lines))
    
    print("SUCCESS: Cookie file support added to API!")
    return True

if __name__ == "__main__":
    add_cookie_support() 