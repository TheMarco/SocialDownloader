import os
import threading
from app import app, tasks # Import the app instance and tasks module
from app.config import DOWNLOAD_FOLDER # Import config for printing

if __name__ == '__main__':
    # Cleanup thread is started in app/__init__.py
    print("-----------------------------------------------------")
    print(" Starting Social Media Downloader Flask App ")
    print(f" Downloads in: {os.path.abspath(DOWNLOAD_FOLDER)}")
    print(f" Cleanup after 2 hours.")
    print(" Ensure FFmpeg is in PATH.")
    print(" Ensure yt-dlp is updated (`pip install -U yt-dlp`).")
    print(" Access at: http://localhost:8080 (or server IP)")
    print("-----------------------------------------------------")

    # Use app.run() for development/simple deployment.
    # For production, consider a WSGI server like Gunicorn or Waitress.
    # Example using Waitress (if installed: pip install waitress):
    # from waitress import serve
    # serve(app, host='0.0.0.0', port=8080)

    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
