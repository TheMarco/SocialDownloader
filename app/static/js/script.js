document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM Content Loaded. Script starting.");

    // --- Element Selectors ---
    const fetchBtn = document.getElementById('fetch-btn');
    const videoUrlInput = document.getElementById('video-url');
    const loadingSpinner = document.querySelector('.loading');
    const errorMessageDiv = document.getElementById('error-message');
    const videoInfoSection = document.getElementById('video-info');
    const downloadStatusSection = document.getElementById('download-status-section');
    const downloadCompleteSection = document.getElementById('download-complete');
    const videoThumbnail = document.getElementById('video-thumbnail');
    const videoTitle = document.getElementById('video-title');
    const videoAuthor = document.getElementById('video-author');
    const videoDuration = document.getElementById('video-duration');
    const downloadOptionsDiv = document.getElementById('download-options');
    const statusSpinner = document.getElementById('status-spinner');
    const downloadStatusText = document.getElementById('download-status-text');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const downloadInfoText = document.getElementById('download-info');
    const finalFilenameDisplay = document.getElementById('final-filename-display');
    const downloadLink = document.getElementById('download-link');
    const downloadAnotherBtn = document.getElementById('download-another');

    // --- State Variables ---
    let currentDownloadId = null;
    let progressCheckInterval = null;
    let fetchedVideoUrl = null;

    // --- Event Listeners ---
    if (fetchBtn) {
        fetchBtn.addEventListener('click', fetchVideoInfo);
    } else { console.error("Fetch button element (id='fetch-btn') NOT FOUND!"); }
    if (videoUrlInput) {
        videoUrlInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') fetchVideoInfo(); });
    } else { console.error("Video URL input element (id='video-url') NOT FOUND!"); }
    if (downloadAnotherBtn) {
        downloadAnotherBtn.addEventListener('click', () => resetUI());
    } else { console.error("Download another button element (id='download-another') NOT FOUND!"); }


    // --- Core Functions ---

    function fetchVideoInfo() {
        console.log("fetchVideoInfo called");
        if (!videoUrlInput) { showError("Internal error: URL input field not found."); return; }
        const url = videoUrlInput.value.trim();
        if (!url) { showError('Please paste a video URL first.'); return; }

        resetUI(true); showLoading();
        if (!fetchBtn) { console.error("Cannot disable fetch button: element is missing."); }
        else { fetchBtn.disabled = true; fetchBtn.innerHTML = `<span...</span> Fetching...`; }

        fetch('/fetch_video_info', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url }) })
        .then(response => {
             hideLoading();
             if (!response.ok) {
                 return response.json().then(errData => { throw new Error(errData.error || `Server error: ${response.status} ${response.statusText}`); })
                                    .catch(() => { throw new Error(`Server error: ${response.status} ${response.statusText}`); });
             } return response.json();
        })
        .then(data => {
            resetFetchButton(); if (data.error) { showError(data.error); fetchedVideoUrl = null; }
            else { fetchedVideoUrl = url; displayVideoInfo(data); }
        })
        .catch(error => {
            hideLoading(); resetFetchButton(); fetchedVideoUrl = null;
            showError(`Fetch failed: ${error.message}`); console.error('Fetch Error Object:', error);
        });
    }

    function displayVideoInfo(data) {
        console.log("Displaying video info");
        if (!videoThumbnail || !videoTitle || !videoAuthor || !videoDuration || !downloadOptionsDiv || !videoInfoSection) {
             showError("Internal error: Could not display video details."); return;
        }
        videoThumbnail.src = data.thumbnail || 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
        videoTitle.textContent = data.title || 'Unknown Title';
        videoAuthor.textContent = data.author ? `By: ${data.author}` : 'Unknown Author';
        const duration = data.length;
        if (duration && duration > 0) { const minutes = Math.floor(duration / 60); const seconds = Math.round(duration % 60); videoDuration.textContent = `Duration: ${minutes}:${seconds.toString().padStart(2, '0')}`; }
        else { videoDuration.textContent = 'Duration: Unknown'; }
        downloadOptionsDiv.innerHTML = '';
        if (data.streams && data.streams.length > 0) {
            data.streams.forEach(stream => {
                const row = document.createElement('div'); row.className = 'format-row d-flex justify-content-between align-items-center';
                const info = document.createElement('div'); let qualityLabel = stream.quality || 'Default'; let formatLabel = stream.format ? stream.format.toUpperCase() : ''; let typeIcon = stream.type === 'audio' ? '<i class="fas fa-music"></i>' : '<i class="fas fa-video"></i>'; let typeLabel = stream.type === 'audio' ? 'Audio Only' : 'Video';
                if (stream.itag === 'default') { qualityLabel = "Best Available"; typeIcon = '<i class="fas fa-video"></i>'; typeLabel = 'Video'; }
                info.innerHTML = `<div><strong>${qualityLabel}</strong> ${formatLabel ? `<span class="badge bg-secondary ms-1">${formatLabel}</span>` : ''}</div><small>${typeIcon} ${typeLabel}</small>`;
                const dlBtn = document.createElement('button'); dlBtn.className = 'btn btn-sm btn-success'; dlBtn.innerHTML = '<i class="fas fa-download"></i> Download'; dlBtn.title = `Download ${qualityLabel} ${formatLabel}`;
                dlBtn.addEventListener('click', () => { if (fetchedVideoUrl) { startDownload(fetchedVideoUrl, stream.itag); } else { showError("Cannot start download. Video URL information is missing."); } });
                row.appendChild(info); row.appendChild(dlBtn); downloadOptionsDiv.appendChild(row);
            });
        } else { downloadOptionsDiv.innerHTML = '<p class="text-muted">No downloadable formats found.</p>'; }
        videoInfoSection.style.display = 'block'; videoInfoSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function startDownload(url, itag) {
        console.log(`Starting download for URL: ${url}, itag: ${itag}`);
        if (!url || !itag) { showError("Cannot start download: URL or Format ID is missing."); return; }
        if (!downloadStatusSection) { showError("Internal error: Status display area not found."); return; }
        resetUI(true); downloadStatusSection.style.display = 'block';
        if(progressContainer) progressContainer.style.display = 'none';
        if(progressBar) { progressBar.style.width = '0%'; progressBar.classList.add('progress-bar-animated', 'progress-bar-striped'); progressBar.setAttribute('aria-valuenow', 0); progressBar.textContent = '0%'; }
        if(statusSpinner) statusSpinner.style.display = 'inline-block';
        if(downloadStatusText) downloadStatusText.textContent = 'Starting download...';
        if(downloadInfoText) downloadInfoText.textContent = 'Initiating process, please wait...';
        downloadStatusSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        fetch('/start_download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url, itag: itag }) })
        .then(response => { if (!response.ok) { return response.json().then(errData => { throw new Error(errData.error || `Server error ${response.status}`); }).catch(() => { throw new Error(`Server error ${response.status}`); }); } return response.json(); })
        .then(data => {
            if (data.error) { throw new Error(data.error); }
            currentDownloadId = data.download_id; console.log("Download started, ID:", currentDownloadId);
            stopPolling(); // Clear previous interval just in case before starting new one
            progressCheckInterval = setInterval(() => checkDownloadProgress(currentDownloadId), 1500);
            if(downloadStatusText) downloadStatusText.textContent = 'Download initiated'; if(downloadInfoText) downloadInfoText.textContent = 'Waiting for progress updates...';
        })
        .catch(error => {
            showError(`Failed to start download: ${error.message}`); console.error('Start Download Error:', error);
            if (downloadStatusSection) downloadStatusSection.style.display = 'none'; if (fetchedVideoUrl && videoInfoSection) { videoInfoSection.style.display = 'block'; }
        });
    }

    function checkDownloadProgress(downloadId) {
        if (!downloadId || downloadId !== currentDownloadId) {
            console.log(`Polling check: ID mismatch (current: ${currentDownloadId || 'null'}, checking: ${downloadId}). Stopping poll.`);
            stopPolling(); // Stop polling if ID changed
            return;
        }

        fetch(`/download_progress/${downloadId}`)
        .then(response => {
            if (response.status === 404) { throw new Error('not_found'); }
            if (!response.ok) { return response.json().then(errData => { throw new Error(errData.error || `Server error ${response.status}`); }).catch(() => { throw new Error(`Server error ${response.status}`); }); }
            return response.json();
        })
        .then(data => {
            if (downloadId !== currentDownloadId) { console.log(`Ignoring stale progress data for ${downloadId} after fetch.`); return; } // Re-check after async

            // --- ADDED LOGGING AROUND STOP CONDITIONS ---
            if (data.status === 'error') {
                console.log(`>>> Status is 'error'. Attempting to stop polling for ID ${downloadId}. Message: ${data.error}`); // <<< ADDED LOG
                stopPollingAndShowError(`Download failed: ${data.error || 'Unknown server error'}`);
                return; // Exit after handling error
            }

            updateProgressUI(data); // Update UI first

            if (data.status === 'complete') {
                console.log(`>>> Status is 'complete'. Attempting to stop polling for ID ${downloadId}.`); // <<< ADDED LOG
                stopPolling(); // Stop polling interval *before* timeout

                if (progressBar && progressContainer) { progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped'); progressBar.style.width = '100%'; progressBar.textContent = '100%'; progressContainer.style.display = 'block'; }
                setTimeout(() => {
                    if (downloadStatusSection) downloadStatusSection.style.display = 'none'; if (downloadCompleteSection) downloadCompleteSection.style.display = 'block';
                    const finalFilename = data.final_filename || data.filename || 'downloaded_file';
                    if (finalFilenameDisplay) finalFilenameDisplay.textContent = finalFilename;
                    if (downloadLink) { downloadLink.href = `/download_file/${downloadId}`; downloadLink.setAttribute('download', finalFilename); }
                    if (downloadCompleteSection) downloadCompleteSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 500);
            } else if (!['starting', 'processing_part1', 'downloading', 'processing', 're-encoding'].includes(data.status)) {
                 console.warn("Received unknown or unexpected status during polling:", data.status, data);
            }
            // --- END ADDED LOGGING ---

        })
        .catch(error => {
            if (downloadId !== currentDownloadId) { return; } // Ignore errors for stale downloads
            if (error.message === 'not_found') {
                console.warn(`Download ID ${downloadId} not found (404). Might be expired.`);
                stopPollingAndShowError('Download process not found. It might have expired or been removed.');
            } else {
                console.error('Progress check error:', error.message);
                if (downloadStatusText) downloadStatusText.textContent = 'Connection Issue'; if (downloadInfoText) downloadInfoText.textContent = `Polling error: ${error.message}. Retrying...`; if (statusSpinner) statusSpinner.style.display = 'inline-block';
            }
        });
    }

    function updateProgressUI(data) {
       if (!downloadStatusText || !downloadInfoText || !statusSpinner || !progressContainer || !progressBar) { console.error("Cannot update progress UI: Elements missing."); stopPolling(); return; }
        let statusText = 'Waiting...'; let infoText = data.info_text || 'Checking status...'; let showProgressBar = false; let showSpinner = true; let progressPercent = Math.max(0, Math.min(100, parseFloat(data.progress) || 0));
        switch (data.status) {
            case 'starting': statusText = 'Starting...'; showSpinner = true; showProgressBar = false; break;
            case 'processing_part1': statusText = 'Processing...'; showSpinner = true; showProgressBar = true; if(progressBar) progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped'); break;
            case 'downloading': statusText = 'Downloading...'; showSpinner = true; showProgressBar = true; if(progressBar) progressBar.classList.add('progress-bar-animated', 'progress-bar-striped'); break;
            case 'processing': statusText = 'Processing...'; showSpinner = true; showProgressBar = true; if(progressBar) progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped'); break;
            case 're-encoding': statusText = 'Re-encoding...'; showSpinner = true; showProgressBar = true; if(progressBar) progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped'); break;
            case 'complete': statusText = 'Complete!'; showSpinner = false; progressPercent = 100; showProgressBar = true; if(progressBar) progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped'); break;
            case 'error': statusText = 'Error'; showSpinner = false; progressPercent = 0; showProgressBar = false; break;
            default: statusText = 'Unknown Status'; console.warn("Unhandled status in updateProgressUI:", data.status); showSpinner = true; showProgressBar = false;
        }
        downloadStatusText.textContent = statusText; downloadInfoText.textContent = infoText; statusSpinner.style.display = showSpinner ? 'inline-block' : 'none';
        if (showProgressBar) {
            progressContainer.style.display = 'block'; const currentWidth = progressBar.style.width; const newWidth = `${progressPercent}%`;
            if (currentWidth !== newWidth) progressBar.style.width = newWidth;
            progressBar.setAttribute('aria-valuenow', progressPercent); progressBar.textContent = `${Math.round(progressPercent)}%`;
        } else { progressContainer.style.display = 'none'; }
    }

    // --- Utility Functions ---

    function stopPolling() {
        if (progressCheckInterval) {
            // --- MODIFIED LOG ---
            console.log(`>>> stopPolling() called. Clearing ACTIVE interval ID: ${progressCheckInterval}`);
            clearInterval(progressCheckInterval);
            progressCheckInterval = null; // Explicitly set to null
        } else {
            // --- MODIFIED LOG ---
            console.log(">>> stopPolling() called but no ACTIVE interval ID was found (it might have been cleared already).");
        }
    }

    function stopPollingAndShowError(msg) {
        // --- ADDED LOG ---
        console.log(">>> stopPollingAndShowError() called.");
        stopPolling(); // Call the actual stop function
        showError(msg);
        if (downloadStatusSection) downloadStatusSection.style.display = 'none';
        if (fetchedVideoUrl && videoInfoSection) { videoInfoSection.style.display = 'block'; }
        currentDownloadId = null; // Clear download ID on error
    }

    function showError(msg) {
        console.error("Showing Error Message:", msg);
        if (!errorMessageDiv) { console.error("Cannot show error: errorMessageDiv missing."); alert("Error: " + msg + "\n(Error display element missing)"); return; }
        errorMessageDiv.textContent = msg; errorMessageDiv.style.display = 'block'; hideLoading();
        if (downloadStatusSection) downloadStatusSection.style.display = 'none'; if (downloadCompleteSection) downloadCompleteSection.style.display = 'none';
        errorMessageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function showLoading() { if (!loadingSpinner) { console.error("loadingSpinner missing!"); return; } loadingSpinner.style.display = 'block'; if (errorMessageDiv) errorMessageDiv.style.display = 'none'; if (videoInfoSection) videoInfoSection.style.display = 'none'; if (downloadStatusSection) downloadStatusSection.style.display = 'none'; if (downloadCompleteSection) downloadCompleteSection.style.display = 'none'; }
    function hideLoading() { if (!loadingSpinner) return; loadingSpinner.style.display = 'none'; }
    function resetFetchButton() { if (!fetchBtn) { console.error("Cannot reset fetch button: element not found."); return; } fetchBtn.disabled = false; fetchBtn.innerHTML = 'Fetch Info'; }
    function resetUI(keepUrl = false) {
        console.log("Resetting UI state. Keep URL:", keepUrl);
        if (!keepUrl && videoUrlInput) { videoUrlInput.value = ''; fetchedVideoUrl = null; }
        if (videoInfoSection) videoInfoSection.style.display = 'none'; if (downloadStatusSection) downloadStatusSection.style.display = 'none'; if (downloadCompleteSection) downloadCompleteSection.style.display = 'none'; if (errorMessageDiv) errorMessageDiv.style.display = 'none'; hideLoading();
        if (downloadOptionsDiv) downloadOptionsDiv.innerHTML = ''; if (videoThumbnail) videoThumbnail.src = ''; if (videoTitle) videoTitle.textContent = ''; if (videoAuthor) videoAuthor.textContent = ''; if (videoDuration) videoDuration.textContent = '';
        resetFetchButton();
        stopPolling(); // Ensure polling stops on UI reset
        currentDownloadId = null;
    }

    // Initial setup
    resetUI();
    console.log("Script finished initial setup.");

}); // End DOMContentLoaded
