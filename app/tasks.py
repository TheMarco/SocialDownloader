import os
import time
import shutil
import traceback

# Import config and potentially shared state if needed
from .config import CLEANUP_INTERVAL_SECONDS, CLEANUP_AGE_SECONDS

# --- Cleanup Task ---

def cleanup_old_downloads(download_folder_root, download_progress, progress_lock):
    """Periodically cleans up old download directories."""
    print(f"Cleanup thread started. Checking every {CLEANUP_INTERVAL_SECONDS / 60:.1f} minutes for items older than {CLEANUP_AGE_SECONDS / 3600:.1f} hours.")
    while True:
        try:
            # Wait for the specified interval before running cleanup
            time.sleep(CLEANUP_INTERVAL_SECONDS)

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running cleanup task...")
            current_time = time.time()
            cutoff_time = current_time - CLEANUP_AGE_SECONDS

            if not os.path.exists(download_folder_root):
                print(f"Cleanup: Downloads folder '{download_folder_root}' missing, skipping cycle.")
                continue

            cleaned_dirs = 0
            cleaned_entries = 0
            checked_items = 0
            active_dl_ids = set()

            # Get a snapshot of active download IDs under lock
            with progress_lock:
                active_dl_ids = set(download_progress.keys())

            items_in_folder = []
            try:
                items_in_folder = os.listdir(download_folder_root)
            except OSError as e:
                print(f"Cleanup Error: Could not list directory '{download_folder_root}': {e}")
                continue # Skip this cycle

            # --- Clean up old directories ---
            for item_name in items_in_folder:
                item_path = os.path.join(download_folder_root, item_name)
                checked_items += 1
                try:
                    # Check if it looks like a download ID directory (UUID format) and is actually a directory
                    if os.path.isdir(item_path) and len(item_name) == 36: # Basic UUID check
                         mod_time = os.path.getmtime(item_path)
                         # Check if modification time is older than cutoff and it's not in the active list
                         if mod_time < cutoff_time and item_name not in active_dl_ids:
                             print(f"Cleanup: Removing old directory: {item_path} (Last modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mod_time))})")
                             shutil.rmtree(item_path)
                             cleaned_dirs += 1
                             # Also remove from progress dict if it somehow lingered
                             with progress_lock:
                                 download_progress.pop(item_name, None)
                         # Optional: Add logic here to remove very old *active* downloads if needed (e.g., stuck > 24h)
                except FileNotFoundError:
                    # Directory was deleted between listdir and check, ignore
                    print(f"Cleanup Info: Item '{item_name}' disappeared during cleanup scan.")
                    continue
                except Exception as item_err:
                    print(f"Cleanup Error: Failed to process item '{item_path}': {item_err}")
                    traceback.print_exc() # Print stack trace for unexpected errors

            # --- Clean up orphaned entries in download_progress ---
            zombie_entries = []
            with progress_lock:
                # Iterate over a copy of keys to allow modification during iteration
                for dl_id in list(download_progress.keys()):
                    # Check if the corresponding directory is missing
                    expected_dir_path = os.path.join(download_folder_root, dl_id)
                    if not os.path.exists(expected_dir_path):
                        # Also check if the entry itself is old enough to be considered a zombie
                        entry_start_time = download_progress[dl_id].get('start_time', 0)
                        if entry_start_time < cutoff_time:
                            zombie_entries.append(dl_id)

            if zombie_entries:
                 with progress_lock:
                    for zombie_id in zombie_entries:
                         # Final check if it still exists before removing
                         if zombie_id in download_progress:
                             print(f"Cleanup: Removing orphaned progress entry: {zombie_id}")
                             del download_progress[zombie_id]
                             cleaned_entries += 1

            print(f"Cleanup finished. Checked {checked_items} items. Removed {cleaned_dirs} old directories and {cleaned_entries} orphaned entries.")

        except Exception as e:
            # Catch broad exceptions to prevent the cleanup thread from dying
            print(f"!!! CRITICAL ERROR IN CLEANUP THREAD: {e} !!!")
            print(traceback.format_exc())
            # Sleep longer after a major error to avoid spamming logs
            time.sleep(60 * 60)
