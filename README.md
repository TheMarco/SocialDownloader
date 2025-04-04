#Social Media Video Downloader App v1.1

This is a (Python) Flask-based Downloader application that allows you to download social media videos or extract audio from them using yt-dlp.

#Installation
------------
1. Ensure you have Python 3.7 or higher installed on your system.
2. Clone or download the project files.
3. (Optional) Create and activate a virtual environment:
   - On Linux/Mac:
       python3 -m venv venv
       source venv/bin/activate
   - On Windows:
       python -m venv venv
       venv\Scripts\activate
4. Install the dependencies using pip:
       pip install -r requirements.txt

#Usage
-----
1. Run the Flask application:
       python run.py
2. Open your web browser and navigate to:
       http://localhost:8080
3. Enter a YouTube URL in the input field and click "Fetch Video" to retrieve video information and available download options.
4. Choose your preferred format (video or audio) and click "Download" to start the download.
5. Once the download is complete, a download link will be provided so you can save the file to your device.

#Additional Notes
----------------
- **FFmpeg Requirement:**
  If you plan to extract audio (MP3), ensure that FFmpeg is installed on your system. Download it from: https://ffmpeg.org/download.html

- **HTTP 403 Errors:**
  The app uses enhanced HTTP headers to mimic a browser request. If you continue to face HTTP 403 errors, consider updating yt-dlp to the latest version or supplying a cookies file for age-restricted/region-locked content.

- **Cleanup:**
  The application automatically cleans up downloads older than 1 hour.

- **Documentation:**
  For more information, refer to:
      - Flask Documentation: https://flask.palletsprojects.com/
      - yt-dlp Documentation: https://github.com/yt-dlp/yt-dlp

Enjoy and let me know if you have any further questions!

Marco van Hylckama Vlieg

https://x.com/AIandDesign
