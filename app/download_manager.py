import os
import re
import time
import traceback
import subprocess
import shutil
import threading
import yt_dlp

# Import necessary components from the app package
from . import download_progress, progress_lock
from .config import COMMON_HTTP_HEADERS, DOWNLOAD_FOLDER_PATH # Use absolute path from config
from .utils import parse_ffmpeg_time

# --- Download Thread ---

def download_thread(url, format_id, output_path_base, download_id):
    """Thread function to download the video and optionally re-encode."""
    start_time = time.time()
    output_path = os.path.join(output_path_base, download_id)

    initial_progress_data = {
        'status': 'starting', 'progress': 0, 'filename': None,
        'final_filename': None, 'filepath': None, 'error': None,
        'start_time': start_time, '_download_phase': 1,
        '_last_hook_status': None, 'info_text': 'Initializing...'
    }

    with progress_lock:
        try:
             if not os.path.exists(output_path): os.makedirs(output_path, exist_ok=True)
        except OSError as e:
             print(f"CRITICAL [{download_id}]: Failed to create download dir {output_path}: {e}")
             initial_progress_data.update({'status': 'error', 'error': f'Server setup error: {e}', '_download_phase': 0, 'info_text': f'Failed: {e}'})
             download_progress[download_id] = initial_progress_data
             return

        download_progress[download_id] = initial_progress_data

    try:
        # --- Progress Hook ---
        def progress_hook(d):
            # Add a log at the very beginning of the hook
            # print(f"Hook [{download_id}]: Received hook data - Status: {d.get('status')}") # Optional: Uncomment for very verbose hook logging
            if d is None: return
            with progress_lock:
                if download_id not in download_progress: return
                current_progress_data = download_progress[download_id]
                if current_progress_data.get('status') in ['complete', 'error']: return

                hook_status = d['status']
                hook_filename = os.path.basename(d.get('filename', '')) or current_progress_data.get('filename', 'download')
                current_phase = current_progress_data.get('_download_phase', 1)
                last_hook_status = current_progress_data.get('_last_hook_status')

                # Phase transitions (simplified - correction happens after ydl finishes)
                if last_hook_status == 'downloading' and hook_status == 'finished' and current_phase == 1:
                     current_progress_data['_download_phase'] = 2 # Tentative phase 2
                     current_progress_data['progress'] = 50.0
                     current_progress_data['info_text'] = "Finishing download step..."
                     current_progress_data['status'] = 'processing_part1'
                     current_phase = 2
                elif last_hook_status == 'downloading' and hook_status == 'finished' and current_phase == 2:
                     current_progress_data['_download_phase'] = 3 # Tentative phase 3
                     current_progress_data['progress'] = 99.0
                     current_progress_data['info_text'] = "Finishing download step..."
                     current_progress_data['status'] = 'processing'
                     current_phase = 3

                current_progress_data['_last_hook_status'] = hook_status

                if hook_status == 'downloading':
                    percent_str = d.get('_percent_str')
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                    downloaded_bytes = d.get('downloaded_bytes')
                    percent = None
                    if total_bytes and downloaded_bytes is not None and total_bytes > 0: percent = (downloaded_bytes / total_bytes) * 100
                    elif d.get('fragment_index') is not None and d.get('fragment_count') is not None and d['fragment_count'] > 0: percent = (d['fragment_index'] / d['fragment_count']) * 100
                    elif percent_str:
                        try: percent = float(percent_str.replace('%','').strip())
                        except (ValueError, TypeError): pass

                    if percent is not None:
                        scaled_progress = 0; info_suffix = ""
                        effective_phase = current_progress_data.get('_download_phase', 1)
                        if effective_phase == 2: scaled_progress = 50.0 + min(percent * 0.49, 49.0); info_suffix = "(part 2/2)"
                        else: scaled_progress = min(percent * 0.5, 49.9); info_suffix = "(part 1/2)"
                        new_progress = min(max(current_progress_data.get('progress', 0), scaled_progress), 99.8)
                        current_progress_data.update({'status': 'downloading', 'progress': round(new_progress, 1), 'filename': hook_filename, 'info_text': f"Downloading {info_suffix}...", 'error': None})
                    else:
                         info_suffix = "(part 1/2)" if current_progress_data.get('_download_phase', 1) == 1 else "(part 2/2)"
                         current_progress_data.update({'status': 'downloading', 'filename': hook_filename, 'info_text': f"Downloading {info_suffix}...", 'error': None})
                elif hook_status == 'finished':
                    # Just mark high progress, actual status correction happens later
                     current_progress_data.update({'progress': 99.0, 'filename': hook_filename, 'info_text': "Finishing download step...",'error': None})
                elif hook_status == 'error':
                    error_msg = d.get('error', 'Unknown download hook error'); print(f"Hook Error reported for {download_id}: {error_msg}")
                    current_progress_data.update({'status': 'error', 'progress': 0, 'error': f"Download failed: {error_msg}", '_download_phase': 0, 'info_text': f"Error: {error_msg}"})


        # --- Configure yt-dlp options ---
        base_outtmpl = os.path.join(output_path, '%(id)s.%(ext)s')
        ydl_opts = {
            'progress_hooks': [progress_hook], 'http_headers': COMMON_HTTP_HEADERS,
            'outtmpl': base_outtmpl, 'quiet': True, 'no_warnings': True, 'verbose': False,
            'ignoreerrors': False, 'noprogress': True, 'cachedir': False,
        }
        is_audio_only = False; final_expected_ext = '.mp4'
        if format_id == 'default': ydl_opts['format'] = 'bestvideo+bestaudio/best'; ydl_opts['merge_output_format'] = 'mp4';
        elif format_id.startswith('mp3_'):
            is_audio_only = True; final_expected_ext = '.mp3';
            quality = '192' if format_id == 'mp3_high' else '128';
            ydl_opts['format'] = 'bestaudio/best';
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}];
            ydl_opts['outtmpl'] = os.path.join(output_path, '%(title)s.%(ext)s')
            with progress_lock:
                if download_id in download_progress: download_progress[download_id]['_download_phase'] = 3; download_progress[download_id]['info_text'] = 'Downloading audio...';
        else:
            try: res = max(144, min(int(format_id.split("_")[1]), 4320))
            except Exception: res = 720
            ydl_opts['format'] = f'bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={res}]+bestaudio/best[height<={res}]';
            ydl_opts['merge_output_format'] = 'mp4'

        # --- Execute Download ---
        final_filepath = None; downloaded_info = None
        try:
            print(f"Starting yt-dlp download for ID: {download_id}, URL: {url[:50]}..., Format: {format_id}")

            # --- ADDED LOGS AROUND YT-DLP EXECUTION ---
            print(f"DEBUG [{download_id}]: >>> ENTERING yt-dlp context manager <<<")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print(f"DEBUG [{download_id}]: Inside context manager, calling ydl.extract_info...")
                    downloaded_info = ydl.extract_info(url, download=True)
                    print(f"DEBUG [{download_id}]: ydl.extract_info call completed.") # Check if this line is reached
            except Exception as ydl_ctx_err:
                 print(f"ERROR [{download_id}]: Exception occurred *during* yt-dlp context manager execution: {ydl_ctx_err}")
                 print(traceback.format_exc()) # Print detailed traceback for this specific error
                 raise # Re-raise the exception to be caught by the main handler below
            print(f"DEBUG [{download_id}]: >>> EXITING yt-dlp context manager <<<")
            # --- END ADDED LOGS ---


            # --- STATE CORRECTION LOGIC ---
            # (This logic only runs if the 'with yt_dlp...' block above completes without error)
            print(f"DEBUG [{download_id}]: Entering state correction logic.")
            num_requested_formats = 0
            if downloaded_info and downloaded_info.get('requested_formats'):
                 num_requested_formats = len(downloaded_info['requested_formats'])
                 print(f"DEBUG [{download_id}]: Info - Requested Formats Count: {num_requested_formats}")
            elif downloaded_info:
                 print(f"DEBUG [{download_id}]: Info - 'requested_formats' missing/None. Format selected: {downloaded_info.get('format')}")
                 if downloaded_info.get('format') and '+' not in downloaded_info.get('format'):
                     num_requested_formats = 1
            else:
                 print(f"WARNING [{download_id}]: yt-dlp finished but returned None info. Cannot correct state.")
                 # Allow potential file finding below, but log warning
                 # raise Exception("yt-dlp returned no information after download.") # Maybe too strict?

            if not is_audio_only and num_requested_formats == 1:
                print(f"INFO [{download_id}]: Detected single-file download. Correcting state.")
                with progress_lock:
                     if download_id in download_progress and download_progress[download_id]['status'] != 'error':
                          if download_progress[download_id]['_download_phase'] < 3: download_progress[download_id]['_download_phase'] = 3
                          download_progress[download_id]['progress'] = 99.0
                          download_progress[download_id]['status'] = 'processing'
                          download_progress[download_id]['info_text'] = 'Processing downloaded file...'
            elif not is_audio_only and num_requested_formats > 1:
                 print(f"INFO [{download_id}]: Detected multi-file download/merge (count={num_requested_formats}). Verifying state.")
                 with progress_lock:
                     if download_id in download_progress and download_progress[download_id]['status'] != 'error':
                         if download_progress[download_id]['_download_phase'] < 3: print(f"WARNING [{download_id}]: Forcing phase 3."); download_progress[download_id]['_download_phase'] = 3
                         if download_progress[download_id]['status'] not in ['processing', 're-encoding']: download_progress[download_id]['status'] = 'processing'
                         download_progress[download_id]['progress'] = max(download_progress[download_id].get('progress', 0), 99.0)
                         download_progress[download_id]['info_text'] = 'Merging downloaded files...'
            # --- End STATE CORRECTION LOGIC ---

            print(f"yt-dlp processing stage finished for {download_id}.") # Log completion of this stage

            # --- Determine final file path ---
            # (File path finding logic remains the same)
            if downloaded_info:
                if 'requested_downloads' in downloaded_info and downloaded_info['requested_downloads']: final_filepath = downloaded_info['requested_downloads'][0].get('filepath')
                if not final_filepath: final_filepath = downloaded_info.get('filepath') or downloaded_info.get('_filename')
                if not final_filepath and 'entries' in downloaded_info and downloaded_info['entries']: final_filepath = downloaded_info['entries'][0].get('filepath') or downloaded_info['entries'][0].get('_filename')
            if not final_filepath or not os.path.exists(final_filepath):
                print(f"Warning: Could not reliably determine final filename for {download_id}. Scanning {output_path}.")
                potential_files = [os.path.join(output_path, f) for f in os.listdir(output_path) if os.path.isfile(os.path.join(output_path, f)) and f.lower().endswith(final_expected_ext)]
                if potential_files: potential_files.sort(key=os.path.getmtime, reverse=True); final_filepath = potential_files[0]; print(f"Fallback Scan: Selected newest matching file '{os.path.basename(final_filepath)}'.")
                else:
                     all_files = [os.path.join(output_path, f) for f in os.listdir(output_path) if os.path.isfile(os.path.join(output_path, f))]
                     if all_files: all_files.sort(key=os.path.getmtime, reverse=True); final_filepath = all_files[0]; print(f"Last Resort Fallback: Selected newest file '{os.path.basename(final_filepath)}'.")
                     else: raise FileNotFoundError(f"State corrected, but could not find any media file in {output_path} for {download_id}.")
            if not final_filepath or not os.path.exists(final_filepath): raise FileNotFoundError(f"Final file path determination failed after correction. Path ('{final_filepath}') not found for {download_id}.")


            # --- Sanitize filename and Rename ---
            # (Sanitize/Rename logic remains the same)
            base_title = downloaded_info.get('title', 'downloaded_video') if downloaded_info else 'downloaded_video'
            sanitized_title = re.sub(r'[\\/*?:"<>|]', '_', base_title)[:150]; file_ext = os.path.splitext(final_filepath)[1]
            if not file_ext: file_ext = final_expected_ext
            final_target_basename = f"{sanitized_title}{file_ext}"; final_target_path = os.path.join(output_path, final_target_basename)
            if os.path.abspath(final_filepath) != os.path.abspath(final_target_path):
                print(f"Renaming '{os.path.basename(final_filepath)}' to '{final_target_basename}' for {download_id}")
                try:
                    if os.path.exists(final_target_path): os.remove(final_target_path)
                    shutil.move(final_filepath, final_target_path); final_filepath = final_target_path
                except Exception as move_err: print(f"Warning: Failed to rename file: {move_err}. Using original: {os.path.basename(final_filepath)}"); final_target_basename = os.path.basename(final_filepath)
            else: print(f"Skipping rename for {download_id}, source/target same: {final_target_basename}")


            # --- Optional Re-encoding ---
            # (FFmpeg logic remains the same as the previous working version)
            print(f"DEBUG [{download_id}]: Checking if re-encoding is needed (is_audio_only={is_audio_only})...")
            if not is_audio_only:
                print(f"DEBUG [{download_id}]: >>> ENTERING FFmpeg Re-encoding Block <<<")
                with progress_lock:
                    if download_id in download_progress: download_progress[download_id]['_download_phase'] = 4
                total_duration = downloaded_info.get('duration'); print(f"DEBUG [{download_id}]: FFmpeg section. Duration: {total_duration} seconds")
                if not total_duration or total_duration <= 0: print(f"WARNING [{download_id}]: Invalid duration. FFmpeg progress unavailable."); total_duration = None
                with progress_lock:
                    if download_id in download_progress and download_progress[download_id].get('status') != 'error':
                        download_progress[download_id].update({'status': 're-encoding', 'progress': 0, 'filename': final_target_basename, 'info_text': 'Optimizing format...' if total_duration else 'Optimizing format (progress unavailable)...', 'error': None})
                quicktime_basename = f"{os.path.splitext(final_target_basename)[0]}_quicktime.mp4"; quicktime_filepath = os.path.join(output_path, quicktime_basename)
                ffmpeg_command = ['ffmpeg', '-v', 'quiet', '-stats', '-y', '-i', final_filepath, '-c:v', 'libx264', '-profile:v', 'high', '-level', '4.1', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', quicktime_filepath]
                process = None
                try:
                    print(f"DEBUG [{download_id}]: Preparing to execute FFmpeg command: {' '.join(ffmpeg_command)}")
                    process = subprocess.Popen(ffmpeg_command, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1)
                    print(f"DEBUG [{download_id}]: FFmpeg process started (PID: {process.pid}). Reading stderr...")
                    initial_poll = process.poll();
                    if initial_poll is not None: print(f"WARNING [{download_id}]: FFmpeg process exited immediately after start with code {initial_poll}.")
                    print(f"DEBUG [{download_id}]: Entering FFmpeg stderr reading loop...")
                    lines_processed = 0; last_logged_percent = -1
                    while True:
                        if process.stderr is None: print(f"DEBUG [{download_id}]: Loop start: stderr is None. Breaking."); break
                        line = process.stderr.readline()
                        if not line: final_poll = process.poll(); print(f"DEBUG [{download_id}]: Loop: readline() returned empty. Process poll: {final_poll}. Breaking."); break
                        lines_processed += 1
                        # print(f"FFMPEG_RAW_LINE [{download_id}][{lines_processed}]: {line.strip()}") # Uncomment for extreme debug
                        if total_duration:
                            match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
                            if match:
                                current_time_str = match.group(1); current_time_sec = parse_ffmpeg_time(current_time_str)
                                if current_time_sec is not None:
                                    progress_percent = min(max(round((current_time_sec / total_duration) * 100, 1), 0), 99.9)
                                    should_update = False; current_prog = -1
                                    with progress_lock:
                                        if download_id in download_progress and download_progress[download_id].get('status') == 're-encoding':
                                            current_prog = download_progress[download_id].get('progress', 0)
                                            if progress_percent > current_prog: download_progress[download_id]['progress'] = progress_percent; should_update = True
                                        else: print(f"DEBUG [{download_id}]: Status changed during FFmpeg parsing. Stopping."); break
                                    if should_update and (progress_percent > last_logged_percent + 1 or progress_percent > 99):
                                        print(f"DEBUG [{download_id}]: Updated FFmpeg progress from {current_prog:.1f}% to {progress_percent:.1f}% (time={current_time_str})")
                                        last_logged_percent = progress_percent
                    print(f"DEBUG [{download_id}]: Exited FFmpeg stderr loop. Lines: {lines_processed}")
                    print(f"DEBUG [{download_id}]: Waiting for FFmpeg process finish...")
                    process.wait(); return_code = process.returncode
                    print(f"DEBUG [{download_id}]: FFmpeg process finished code: {return_code}")
                    if return_code != 0:
                        error_output = "";
                        try:
                            if process.stderr and not process.stderr.closed: error_output = process.stderr.read(4096)
                        except Exception as e: print(f"Error reading final stderr {download_id}: {e}")
                        print(f"!!! FFmpeg Error {download_id} !!!\nCMD: {' '.join(ffmpeg_command)}\nRC: {return_code}\nSTDERR: {error_output}\n!!! End FFmpeg Error !!!"); raise Exception(f"FFmpeg failed (code {return_code}).")
                    print(f"FFmpeg re-encoding successful for {download_id}.")
                    with progress_lock:
                         if download_id in download_progress and download_progress[download_id].get('status') == 're-encoding': download_progress[download_id]['progress'] = 100.0; download_progress[download_id]['info_text'] = "Re-encoding complete."
                    try:
                        if os.path.exists(final_filepath): os.remove(final_filepath); print(f"Removed original: {final_target_basename}")
                        else: print(f"Original {final_target_basename} already gone.")
                    except OSError as remove_err: print(f"Warning: Could not remove original '{final_target_basename}': {remove_err}")
                    final_filepath = quicktime_filepath; final_target_basename = quicktime_basename
                except FileNotFoundError:
                    print(f"ERROR [{download_id}]: FFmpeg command not found. Make sure FFmpeg is installed and in system PATH.")
                    with progress_lock:
                        if download_id in download_progress:
                            download_progress[download_id].update({'status':'error', 'error':'FFmpeg not found', 'info_text':'Error: FFmpeg not found.'})
                except Exception as ffmpeg_err:
                    print(f"ERROR [{download_id}]: An error occurred during FFmpeg execution: {ffmpeg_err}")
                    if process and process.poll() is None:
                        print(f"Terminating FFmpeg process {download_id} due to error: {ffmpeg_err}"); process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: print(f"FFmpeg kill {download_id}."); process.kill()
                    with progress_lock:
                         if download_id in download_progress: download_progress[download_id].update({'status':'error', 'error':f'FFmpeg processing failed: {ffmpeg_err}', 'info_text':f'Error: {ffmpeg_err}'})
                    raise ffmpeg_err

            else: # is_audio_only was True
                print(f"DEBUG [{download_id}]: Skipping FFmpeg re-encoding block because is_audio_only is True.")
                with progress_lock:
                     if download_id in download_progress and download_progress[download_id]['status'] == 'processing':
                          download_progress[download_id]['_download_phase'] = 5
                          download_progress[download_id]['progress'] = 99.9
                          download_progress[download_id]['info_text'] = "Converting audio to MP3..."


            # --- Final Success Update ---
            print(f"DEBUG [{download_id}]: Reached final success update section.")
            with progress_lock:
                if download_id in download_progress and download_progress[download_id].get('status') != 'error':
                    final_status = 'complete'; final_progress = 100.0; final_info = 'Download complete!'
                    current_status = download_progress[download_id].get('status')
                    if current_status == 're-encoding' and download_progress[download_id].get('progress', 0) < 100: print(f"WARNING [{download_id}]: Marking complete, but re-encoding progress was {download_progress[download_id].get('progress', 0)} not 100.")
                    download_progress[download_id].update({
                        'status': final_status, 'progress': final_progress, 'filename': final_target_basename,
                        'final_filename': final_target_basename, 'filepath': final_filepath, 'error': None,
                        'info_text': final_info, '_download_phase': 5 # Final phase
                    })
            print(f"Download and processing complete for {download_id}: {final_target_basename}")

        # --- Main Exception Handling Block ---
        except FileNotFoundError as fnf_err: err_msg = f"File handling error: {fnf_err}"; print(f"FileNotFoundError for download {download_id}: {err_msg}"); print(traceback.format_exc())
        except yt_dlp.utils.DownloadError as dl_error:
            clean_dl_error_msg = str(dl_error);
            if dl_error.args and isinstance(dl_error.args[0], str): clean_dl_error_msg = dl_error.args[0].split(':')[-1].strip()
            err_msg = f"Download failed: {clean_dl_error_msg}"; print(f"yt-dlp DownloadError for download {download_id}: {str(dl_error)}"); print(traceback.format_exc())
        except Exception as thread_err: err_msg = f"Processing failed: {str(thread_err)}"; print(f"General exception in download thread {download_id}: {err_msg}"); print(traceback.format_exc())
        else: err_msg = None

        if err_msg:
             with progress_lock:
                 if download_id in download_progress:
                      current_filename = download_progress[download_id].get('filename')
                      download_progress[download_id].update({'status': 'error', 'progress': 0, 'error': err_msg, 'filename': current_filename, '_download_phase': 0, 'info_text': f"Failed: {err_msg}"})

    # --- Outer Exception Handling ---
    except Exception as outer_err:
        error_message = f"Critical setup error in download thread {download_id}: {outer_err}"; print(error_message); print(traceback.format_exc())
        with progress_lock:
             if download_id in download_progress: download_progress[download_id].update({'status': 'error', 'progress': 0, 'error': f"Failed to start process: {outer_err}", '_download_phase': 0, 'info_text': f"Failed: {outer_err}"})

# --- END OF FILE app/download_manager.py ---
