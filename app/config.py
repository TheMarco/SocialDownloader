import os

# --- Configuration Variables ---

# Directory for storing downloaded files (relative to project root)
DOWNLOAD_FOLDER = 'downloads'

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_FOLDER_PATH = os.path.join(BASE_DIR, '..', DOWNLOAD_FOLDER) # Absolute path

# Enhanced HTTP headers for yt-dlp
COMMON_HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.google.com/' # General referer, yt-dlp might override
}

# Cleanup settings
CLEANUP_INTERVAL_SECONDS = 60 * 30 # 30 minutes
CLEANUP_AGE_SECONDS = 60 * 60 * 2   # 2 hours
