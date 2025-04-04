import re
import time
import traceback
from urllib.parse import parse_qs, urlparse
import yt_dlp

from .config import COMMON_HTTP_HEADERS

# --- Helper Functions ---

def extract_video_id(url):
    """Extract the video ID from a YouTube URL."""
    try:
        if 'youtu.be' in url:
            return url.split('/')[-1].split('?')[0]
        elif 'youtube.com' in url:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            return query_params.get('v', [None])[0]
    except Exception:
        pass
    return None

def get_video_info(url):
    """Get video info using yt-dlp without downloading."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'http_headers': COMMON_HTTP_HEADERS,
            'extract_flat': 'in_playlist', # Faster for playlists, gets first item info
            'playlist_items': '1',          # Only process the first item if it's a playlist
            'cachedir': False,             # Don't use cache
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # If it's a playlist, use the first entry's info
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
        return info, None
    except yt_dlp.utils.DownloadError as e:
        error_message = f"Failed to get video info: {str(e)}"
        print(f"yt-dlp DownloadError in get_video_info: {error_message}")
        # Refine common user-facing errors
        if "Unsupported URL" in str(e):
            error_message = "Unsupported URL."
        elif "Private video" in str(e) or "Video unavailable" in str(e):
            error_message = "This video is private or unavailable."
        elif "unable to extract" in str(e).lower():
             error_message = "Could not extract video information from the URL."
        # Log the original error for debugging
        print(f"Original yt-dlp error: {str(e)}")
        return None, error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while fetching video info: {str(e)}"
        print(f"Exception in get_video_info: {error_message}")
        print(traceback.format_exc())
        return None, error_message

# --- FFmpeg Time Parsing Helper ---
def parse_ffmpeg_time(time_str):
    """Converts HH:MM:SS.ms time string to seconds."""
    try:
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_ms = float(parts[2])
        total_seconds = (hours * 3600) + (minutes * 60) + seconds_ms
        return total_seconds
    except Exception:
        # print(f"Failed to parse ffmpeg time: {time_str}") # Optional debug log
        return None # Return None if parsing fails
