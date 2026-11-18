(() => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("video-file-input");
  const dropzoneTitle = document.getElementById("dropzone-title");
  const dropzoneHint = document.getElementById("dropzone-hint");
  const uploadForm = document.getElementById("upload-form");
  const uploadSubmitBtn = document.getElementById("upload-submit-btn");
  const uploadSubmitRow = document.getElementById("upload-submit-row");
  const uploadClearBtn = document.getElementById("upload-clear-btn");
  const topbarBrowseBtn = document.getElementById("topbar-browse-btn");
  const uploadError = document.getElementById("upload-error");
  const uploadProgressWrap = document.getElementById("upload-progress-wrap");
  const uploadProgressBar = document.getElementById("upload-progress-bar");
  const uploadProgressPct = document.getElementById("upload-progress-pct");
  const uploadProgressLabel = document.getElementById("upload-progress-label");

  const youtubeForm = document.getElementById("youtube-form");
  const youtubeInput = document.getElementById("youtube-url-input");
  const youtubeSubmitBtn = document.getElementById("youtube-submit-btn");
  const youtubeError = document.getElementById("youtube-error");

  const recentJobsContainer = document.getElementById("recent-jobs-container");
  const refreshJobsBtn = document.getElementById("refresh-jobs-btn");

  const ALLOWED_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"];
  let selectedFile = null;

  function showAlert(el, message) {
    el.textContent = message;
    el.classList.remove("hidden");
  }

  function clearAlert(el) {
    el.textContent = "";
    el.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const idx = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${(bytes / 1024 ** idx).toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
  }

  function hasValidExtension(filename) {
    const lower = (filename || "").toLowerCase();
    return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  }

  function setSelectedFile(file) {
    clearAlert(uploadError);
    if (!file) {
      selectedFile = null;
      dropzoneTitle.textContent = "Drop a video file here, or click to browse";
      dropzoneHint.textContent = "MP4, MOV, MKV, WebM, AVI up to 500 MB";
      uploadSubmitRow?.classList.add("hidden");
      return;
    }

    if (!hasValidExtension(file.name)) {
      selectedFile = null;
      uploadSubmitRow?.classList.add("hidden");
      showAlert(
        uploadError,
        `Unsupported video format. Accepted extensions: ${ALLOWED_EXTENSIONS.join(", ")}.`
      );
      return;
    }

    selectedFile = file;
    dropzoneTitle.textContent = file.name;
    dropzoneHint.textContent = `${formatBytes(file.size)} · Ready to translate`;
    uploadSubmitRow?.classList.remove("hidden");
  }

  dropzone.addEventListener("click", () => fileInput.click());
  topbarBrowseBtn?.addEventListener("click", () => fileInput.click());
  uploadClearBtn?.addEventListener("click", () => {
    fileInput.value = "";
    setSelectedFile(null);
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    setSelectedFile(file || null);
  });

  ["dragenter", "dragover"].forEach((evtName) => {
    dropzone.addEventListener(evtName, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "drop"].forEach((evtName) => {
    dropzone.addEventListener(evtName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
    }
  });

  uploadForm.addEventListener("submit", (event) => {
    event.preventDefault();
    clearAlert(uploadError);

    if (!selectedFile) {
      showAlert(uploadError, "Please select a video file before submitting.");
      return;
    }

    const formData = new FormData();
    formData.append("video", selectedFile);

    uploadSubmitBtn.disabled = true;
    uploadProgressWrap.classList.remove("hidden");
    uploadProgressLabel.textContent = `Uploading ${selectedFile.name}…`;
    uploadProgressBar.style.width = "0%";
    uploadProgressPct.textContent = "0%";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");

    xhr.upload.addEventListener("progress", (progressEvent) => {
      if (progressEvent.lengthComputable) {
        const pct = Math.round((progressEvent.loaded / progressEvent.total) * 100);
        uploadProgressBar.style.width = `${pct}%`;
        uploadProgressPct.textContent = `${pct}%`;
      }
    });

    xhr.addEventListener("load", () => {
      let payload = {};
      try {
        payload = JSON.parse(xhr.responseText || "{}");
      } catch {
        payload = {};
      }

      if (xhr.status >= 200 && xhr.status < 300 && payload.redirect_url) {
        window.location.href = payload.redirect_url;
        return;
      }

      uploadSubmitBtn.disabled = false;
      uploadProgressWrap.classList.add("hidden");
      showAlert(uploadError, payload.error || "Video upload failed. Please try again.");
    });

    xhr.addEventListener("error", () => {
      uploadSubmitBtn.disabled = false;
      uploadProgressWrap.classList.add("hidden");
      showAlert(uploadError, "Network error while uploading video.");
    });

    xhr.send(formData);
  });

  function isLikelyYouTubeUrl(rawUrl) {
    try {
      const parsed = new URL(rawUrl);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
      const host = parsed.hostname.toLowerCase();
      return (
        host === "youtube.com" ||
        host === "www.youtube.com" ||
        host === "m.youtube.com" ||
        host === "music.youtube.com" ||
        host === "youtu.be" ||
        host === "www.youtu.be"
      );
    } catch {
      return false;
    }
  }

  youtubeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearAlert(youtubeError);

    const url = (youtubeInput.value || "").trim();
    if (!url) {
      showAlert(youtubeError, "Please paste a YouTube video URL.");
      youtubeInput.focus();
      return;
    }

    if (!isLikelyYouTubeUrl(url)) {
      showAlert(
        youtubeError,
        "Enter a valid youtube.com or youtu.be video URL (including https://)."
      );
      youtubeInput.focus();
      return;
    }

    youtubeSubmitBtn.disabled = true;
    youtubeSubmitBtn.textContent = "Starting Job…";

    try {
      const response = await fetch("/api/youtube", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const payload = await response.json();

      if (!response.ok || !payload.redirect_url) {
        throw new Error(payload.error || "Could not start YouTube processing job.");
      }

      window.location.href = payload.redirect_url;
    } catch (err) {
      youtubeSubmitBtn.disabled = false;
      youtubeSubmitBtn.textContent = "Process Video";
      showAlert(youtubeError, err.message || "Failed to submit YouTube URL.");
    }
  });

  function formatJobStatus(job) {
    if (job.status === "completed") {
      const words = Number.isFinite(job.word_count) ? `${job.word_count} words` : "Transcript ready";
      return `Completed · ${words}`;
    }
    if (job.status === "failed") {
      return "Failed";
    }
    return `Processing · ${job.progress ?? 0}%`;
  }

  async function loadRecentJobs() {
    try {
      const response = await fetch("/api/jobs");
      if (!response.ok) throw new Error("Failed to load jobs");
      const data = await response.json();
      const jobs = data.jobs || [];

      if (jobs.length === 0) {
        recentJobsContainer.innerHTML =
          '<p class="empty-state">No processed videos yet. Upload a video or paste a YouTube URL above to begin.</p>';
        return;
      }

      recentJobsContainer.innerHTML = "";
      jobs.forEach((job) => {
        const row = document.createElement("div");
        row.className = "job-row";

        const info = document.createElement("div");
        info.className = "job-row-info";

        const title = document.createElement("p");
        title.className = "job-row-title";
        title.textContent = job.title || job.job_id;

        const meta = document.createElement("p");
        meta.className = "job-row-meta";
        meta.textContent = `${job.source_type === "youtube" ? "YouTube" : "Upload"} · ${formatJobStatus(job)}`;

        info.appendChild(title);
        info.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "job-row-actions";

        const openLink = document.createElement("a");
        openLink.className = "btn btn-secondary btn-sm";
        openLink.href =
          job.status === "completed"
            ? `/player/${encodeURIComponent(job.job_id)}`
            : `/processing/${encodeURIComponent(job.job_id)}`;
        openLink.textContent = job.status === "completed" ? "Open" : "View status";

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "text-action-btn text-action-btn-danger";
        deleteBtn.textContent = "Delete";
        deleteBtn.setAttribute("aria-label", `Delete ${job.title || job.job_id}`);
        deleteBtn.addEventListener("click", async () => {
          deleteBtn.disabled = true;
          await fetch(`/api/jobs/${encodeURIComponent(job.job_id)}`, { method: "DELETE" });
          loadRecentJobs();
        });

        actions.appendChild(openLink);
        actions.appendChild(deleteBtn);

        row.appendChild(info);
        row.appendChild(actions);
        recentJobsContainer.appendChild(row);
      });
    } catch {
      recentJobsContainer.innerHTML =
        '<p class="empty-state">Unable to load recent jobs right now.</p>';
    }
  }

  refreshJobsBtn.addEventListener("click", loadRecentJobs);
  loadRecentJobs();
})();
