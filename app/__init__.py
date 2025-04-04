import os
import threading
import time
from flask import Flask

# Import configuration before other app components
from .config import DOWNLOAD_FOLDER

# Create downloads directory if it doesn't exist
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Dictionary to store download progress (shared resource)
download_progress = {}
# Lock for thread-safe access to download_progress
progress_lock = threading.Lock()

# Create the Flask App Instance
app = Flask(__name__) # Will look for templates/static folders relative to here

# --- Import other parts of the application ---
# Import routes AFTER app instance is created and shared state is defined
from . import routes
# Import background tasks
from . import tasks

# --- Start Background Tasks ---
# Ensure the cleanup task runs only once when the app starts
# Check if running in the main process (relevant for some WSGI servers/debug mode)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true': # Avoid starting thread twice in debug mode
    print("Starting cleanup thread...")
    cleanup_thread = threading.Thread(target=tasks.cleanup_old_downloads, args=(DOWNLOAD_FOLDER, download_progress, progress_lock), name="CleanupThread")
    cleanup_thread.daemon = True
    cleanup_thread.start()
else:
     print("Skipping background thread start in Werkzeug reloader process.")
