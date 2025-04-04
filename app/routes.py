import os
import uuid
import json
import re
import time
import threading
import traceback

from flask import request, jsonify, send_file, render_template, url_for

# Import app instance, shared state, and config from __init__ and config
from . import app, download_progress, progress_lock
from .config import DOWNLOAD_FOLDER, DOWNLOAD_FOLDER_PATH

# Import helper functions and download manager
from .utils import get_video_info
from .download_manager import download_thread

# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    # HTML is now in templates/index.html
    return render_template('index.html')

@app.route('/fetch_video_info', methods=['POST'])
def fetch_video_info_route():
    """API endpoint to fetch video information using yt-dlp."""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 415

    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided'}), 400

    url = data['url'].strip()
    if not url:
        return jsonify({'error': 'URL cannot be empty'}), 400

    # Basic URL validation and prefixing
    if not re.match(r'^https?://', url, re.IGNORECASE):
         # Allow common domains without schema, prefix with https
         if re.match(r'^(www\.)?(youtu\.be/|youtube\.com/|tiktok\.com/|instagram\.com/|twitter\.com/|x\.com/)', url, re.IGNORECASE):
              url = "https://" + url
              print(f"Prefixed URL with https:// : {url}")
         else:
              # If it doesn't start with http/https AND isn't a recognized domain pattern
              return jsonify({'error': 'Invalid URL format. Please include http:// or https://, or use a recognized domain.'}), 400

    print(f"Fetching info for URL: {url}")
    info, error = get_video_info(url)

    if error:
        print(f"Error fetching info for {url}: {error}")
        # Return a 400 Bad Request for client-side errors (like invalid URL, private video)
        # Return a 500 Internal Server Error for unexpected issues
        status_code = 400 if "Unsupported URL" in error or "private or unavailable" in error or "Could not extract" in error else 500
        return jsonify({'error': error}), status_code

    if not info:
        print(f"No info dictionary returned for {url} despite no explicit error.")
        return jsonify({'error': 'Could not retrieve video information (no data).'}), 500

    try:
        # Extract details from the info dictionary
        title = info.get('title', 'Unknown Title')
        author = info.get('uploader', info.get('channel', 'Unknown Author')) # More fallbacks
        duration = info.get('duration') # Keep as potentially None or 0
        thumbnail = info.get('thumbnail')

        # Attempt fallbacks for thumbnails on specific platforms if primary is missing
        if not thumbnail:
            print(f"Standard thumbnail missing for {url}. Attempting platform-specific fallbacks...")
            # These fallbacks depend heavily on yt-dlp's current extraction logic
            if 'tiktok.com' in url.lower():
                thumbnail = info.get('url') # Sometimes the video URL itself works as preview
                print(f"TikTok fallback thumbnail attempt -> info.get('url'): {thumbnail}")
            elif 'instagram.com' in url.lower():
                thumbnail = info.get('display_url') # Instagram often uses display_url
                print(f"Instagram fallback thumbnail attempt -> info.get('display_url'): {thumbnail}")
            # Add more platform-specific fallbacks if needed

        # Prepare available format streams for the frontend
        streams = []
        # Check if it's a YouTube URL to offer specific resolutions
        is_youtube = any(domain in url.lower() for domain in ['youtube.com', 'youtu.be'])

        if is_youtube:
            # Offer standard video resolutions for YouTube
            resolutions = {1080: '1080p', 720: '720p', 480: '480p', 360: '360p'}
            streams.extend([
                {'itag': f'mp4_{res_val}', 'quality': f'{res_label}', 'format': 'MP4', 'type': 'video'}
                for res_val, res_label in resolutions.items()
            ])
            # Offer standard MP3 audio options
            streams.extend([
                {'itag': 'mp3_high', 'quality': 'MP3 (192kbps)', 'format': 'MP3', 'type': 'audio'},
                {'itag': 'mp3_medium', 'quality': 'MP3 (128kbps)', 'format': 'MP3', 'type': 'audio'}
            ])
        else:
            # For other platforms, offer simpler options: Best Video (MP4) and MP3 Audio
            streams.extend([
                {'itag': 'default', 'quality': 'Best Available', 'format': 'MP4', 'type': 'video'},
                {'itag': 'mp3_high', 'quality': 'MP3 (192kbps)', 'format': 'MP3', 'type': 'audio'}
            ])

        # Construct the response payload
        video_details = {
            'title': title,
            'author': author,
            'length': duration if isinstance(duration, (int, float)) and duration > 0 else 0, # Ensure numeric or 0
            'thumbnail': thumbnail or '', # Ensure it's a string, even if empty
            'streams': streams,
            'video_id': info.get('id', 'unknown') # Include video ID if available
        }

        if not video_details['thumbnail']:
             print(f"Warning: No thumbnail could be found for URL: {url}")

        print(f"Successfully fetched info for {url}, Title: {title}")
        return jsonify(video_details)

    except Exception as e:
        print(f"Error processing video info for {url}: {e}")
        print(traceback.format_exc())
        return jsonify({'error': 'Internal server error while processing video information.'}), 500


@app.route('/start_download', methods=['POST'])
def start_download_route():
    """API endpoint to initiate a download in a background thread."""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 415

    data = request.get_json()
    url = data.get('url', '').strip()
    itag = data.get('itag', '').strip() # 'itag' now represents the format ID selected by user

    if not url or not itag:
        return jsonify({'error': 'URL and Format ID (itag) are required.'}), 400

    download_id = str(uuid.uuid4())
    # The download thread will create the specific subdirectory: DOWNLOAD_FOLDER / download_id
    # We just pass the root download folder path here.
    download_path_base = DOWNLOAD_FOLDER_PATH # Use absolute path from config

    # Start the download in a separate thread
    thread = threading.Thread(
        target=download_thread,
        args=(url, itag, download_path_base, download_id),
        name=f"DownloadThread-{download_id[:8]}" # Optional: Name the thread
    )
    thread.daemon = True # Allow main program to exit even if threads are running
    thread.start()

    print(f"Started download thread ID: {download_id}, URL: {url[:50]}..., Format: {itag}")
    # Return 202 Accepted status code indicates the request is accepted for processing
    return jsonify({'success': True, 'download_id': download_id}), 202


@app.route('/download_progress/<download_id>')
def get_download_progress_route(download_id):
    """API endpoint to check the progress of a download."""
    if not download_id:
        return jsonify({'status': 'error', 'error': 'No download ID provided'}), 400

    with progress_lock:
        if download_id not in download_progress:
            # Download ID not found, might be invalid, expired, or cleaned up
            return jsonify({'status': 'not_found', 'error': 'Download ID not found or expired.'}), 404

        # Return a copy of the progress data, excluding the sensitive filepath
        progress_data = download_progress[download_id].copy()
        progress_data.pop('filepath', None) # Remove server-side filepath from response

    return jsonify(progress_data)


@app.route('/download_file/<download_id>')
def download_file_route(download_id):
    """API endpoint to download the completed file."""
    if not download_id:
        return "Invalid request: No download ID provided.", 400

    progress_info = None
    with progress_lock:
        if download_id not in download_progress:
            return "Download not found or expired.", 404
        # Get a copy of the progress info
        progress_info = download_progress[download_id].copy()

    # Check if the download is actually complete
    if progress_info.get('status') != 'complete':
        current_status = progress_info.get('status', 'unknown')
        error_details = progress_info.get('error', 'Not complete or failed.')
        print(f"Download attempt denied for {download_id}. Status: {current_status}. Error: {error_details}")
        # 409 Conflict is appropriate here, the resource isn't in the state required for download
        return f"Download not ready. Current status: {current_status}. Details: {error_details}", 409

    filepath = progress_info.get('filepath')
    filename = progress_info.get('final_filename') or progress_info.get('filename') # Use final_filename if available

    if not filepath or not filename:
        print(f"Error: File path or filename missing in progress info for completed download {download_id}.")
        return "Server error: Essential file information is missing.", 500

    # Double-check if the file physically exists before sending
    if not os.path.exists(filepath):
        print(f"Error: File not found at path '{filepath}' for completed download {download_id}.")
        # Update status to error if file is missing post-completion
        with progress_lock:
            if download_id in download_progress:
                 download_progress[download_id]['status'] = 'error'
                 download_progress[download_id]['error'] = 'Completed file is missing from storage.'
        return "Error: The downloaded file could not be found on the server.", 404

    try:
        print(f"Sending file for download ID {download_id}: {filename}")
        # Use send_file to stream the file to the client
        return send_file(
            filepath,
            as_attachment=True,     # Trigger browser download dialog
            download_name=filename  # Suggest the correct filename to the user
        )
    except Exception as e:
        print(f"Error sending file {filename} for download ID {download_id}: {e}")
        print(traceback.format_exc())
        # Return a generic server error if sending fails
        return "Server error: Could not send the file.", 500
