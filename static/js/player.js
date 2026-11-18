(() => {
  const jobId = document.body.dataset.jobId;
  if (!jobId) return;

  const titleEl = document.getElementById("player-video-title");
  const metaEl = document.getElementById("player-video-meta");
  const errorBanner = document.getElementById("player-error-banner");

  const workspaceGrid = document.getElementById("workspace-grid");
  const stageContainer = document.getElementById("stage-container");
  const primaryWrap = document.querySelector(".primary-video-wrap");
  const video = document.getElementById("original-video");
  const interpreterVideo = document.getElementById("interpreter-video");
  const interpreterPlaceholder = document.getElementById("interpreter-placeholder");
  const interpreterLiveCaption = document.getElementById("interpreter-live-caption");
  const interpreterStatusBar = document.getElementById("interpreter-status-bar");
  const interpreterGlossReadout = document.getElementById("interpreter-gloss-readout");
  const interpreterWindow = document.getElementById("interpreter-window");
  const interpreterDragHandle = document.getElementById("interpreter-drag-handle");
  const interpreterResizeHandle = document.getElementById("interpreter-resize-handle");

  const playPauseBtn = document.getElementById("play-pause-btn");
  const playIcon = document.getElementById("play-icon");
  const pauseIcon = document.getElementById("pause-icon");
  const timeReadout = document.getElementById("time-readout");
  const seekSlider = document.getElementById("seek-slider");
  const muteBtn = document.getElementById("mute-btn");
  const volumeOnIcon = document.getElementById("volume-on-icon");
  const volumeOffIcon = document.getElementById("volume-off-icon");
  const volumeSlider = document.getElementById("volume-slider");
  const speedSelect = document.getElementById("speed-select");
  const fullscreenBtn = document.getElementById("fullscreen-btn");

  const toggleLayoutBtn = document.getElementById("toggle-layout-btn");
  const toggleInterpreterBtn = document.getElementById("toggle-interpreter-btn");
  const toggleTranscriptBtn = document.getElementById("toggle-transcript-btn");
  const transcriptPanel = document.getElementById("transcript-panel");

  let interpreterAvailable = false;
  let isSeeking = false;
  let syncSegments = [];

  function formatClock(seconds) {
    const safe = Math.max(0, Math.floor(Number(seconds) || 0));
    const mins = Math.floor(safe / 60);
    const secs = safe % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  function updateTimeUI() {
    const current = video.currentTime || 0;
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    timeReadout.textContent = `${formatClock(current)} / ${formatClock(duration)}`;
    if (!isSeeking && duration > 0) {
      seekSlider.max = String(duration);
      seekSlider.value = String(current);
    }
  }

  function mapMasterToInterpreterTime(masterTime) {
    if (!syncSegments.length) return masterTime;
    for (let i = 0; i < syncSegments.length; i += 1) {
      const seg = syncSegments[i];
      if (masterTime >= seg.original_start && masterTime <= seg.original_end) {
        if (
          typeof seg.interpreter_start === "number" &&
          typeof seg.interpreter_end === "number"
        ) {
          const origSpan = Math.max(0.05, seg.original_end - seg.original_start);
          const interpSpan = Math.max(0.05, seg.interpreter_end - seg.interpreter_start);
          const ratio = Math.max(0, Math.min(1, (masterTime - seg.original_start) / origSpan));
          return seg.interpreter_start + ratio * interpSpan;
        }
      }
    }
    return masterTime;
  }

  function syncInterpreterClock(forceSeek = false) {
    if (!interpreterAvailable || interpreterVideo.readyState < 1) return;
    if (interpreterVideo.playbackRate !== video.playbackRate) {
      interpreterVideo.playbackRate = video.playbackRate;
    }

    const targetTime = Math.min(
      Number.isFinite(interpreterVideo.duration) ? interpreterVideo.duration : Infinity,
      Math.max(0, mapMasterToInterpreterTime(video.currentTime || 0))
    );
    const drift = Math.abs((interpreterVideo.currentTime || 0) - targetTime);
    if (forceSeek || drift > 0.25) {
      interpreterVideo.currentTime = targetTime;
    }
  }

  function updateInterpreterStatus(sentence) {
    if (!sentence) {
      if (interpreterAvailable) {
        interpreterStatusBar.classList.add("hidden");
      } else {
        interpreterLiveCaption.textContent = "Listening for speech…";
      }
      return;
    }

    if (!interpreterAvailable) {
      interpreterLiveCaption.textContent = sentence.text;
      return;
    }

    interpreterStatusBar.classList.remove("hidden");
    if (sentence.asl_status === "matched" && sentence.asl_gloss_text) {
      interpreterGlossReadout.textContent = `ASL: ${sentence.asl_gloss_text}`;
    } else if (sentence.asl_status === "partial" && sentence.asl_gloss_text) {
      const missing = (sentence.missing_words || []).join(", ");
      interpreterGlossReadout.textContent = missing
        ? `Partial ASL: ${sentence.asl_gloss_text} (missing: ${missing})`
        : `Partial ASL: ${sentence.asl_gloss_text}`;
    } else {
      interpreterGlossReadout.textContent = "Translation unavailable for this phrase";
    }
  }

  const transcriptController = window.SignBridgeTranscript.initTranscript({
    jobId,
    onSeek: (seconds) => {
      video.currentTime = seconds;
      syncInterpreterClock(true);
      updateTimeUI();
      video.play().catch(() => {});
    },
    onActiveSentenceChange: (sentence) => {
      updateInterpreterStatus(sentence);
    },
  });

  playPauseBtn.addEventListener("click", () => {
    if (video.paused || video.ended) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  });

  video.addEventListener("play", () => {
    playIcon?.classList.add("hidden");
    pauseIcon?.classList.remove("hidden");
    playPauseBtn.setAttribute("aria-label", "Pause");
    playPauseBtn.setAttribute("title", "Pause");
    if (interpreterAvailable) {
      syncInterpreterClock(true);
      interpreterVideo.play().catch(() => {});
    }
  });

  video.addEventListener("pause", () => {
    playIcon?.classList.remove("hidden");
    pauseIcon?.classList.add("hidden");
    playPauseBtn.setAttribute("aria-label", "Play");
    playPauseBtn.setAttribute("title", "Play");
    if (interpreterAvailable) {
      interpreterVideo.pause();
    }
  });

  video.addEventListener("waiting", () => {
    if (interpreterAvailable && !interpreterVideo.paused) {
      interpreterVideo.pause();
    }
  });

  video.addEventListener("playing", () => {
    if (interpreterAvailable && !video.paused) {
      syncInterpreterClock(false);
      interpreterVideo.play().catch(() => {});
    }
  });

  video.addEventListener("loadedmetadata", () => {
    updateTimeUI();
  });

  video.addEventListener("timeupdate", () => {
    updateTimeUI();
    syncInterpreterClock(false);
    transcriptController.syncTime(video.currentTime || 0);
  });

  video.addEventListener("seeked", () => {
    syncInterpreterClock(true);
    transcriptController.syncTime(video.currentTime || 0);
  });

  video.addEventListener("ratechange", () => {
    if (interpreterAvailable) {
      interpreterVideo.playbackRate = video.playbackRate;
    }
  });

  video.addEventListener("ended", () => {
    if (interpreterAvailable) {
      interpreterVideo.pause();
    }
  });

  video.addEventListener("error", () => {
    errorBanner.textContent = "Unable to decode or play the original video file in this browser.";
    errorBanner.classList.remove("hidden");
  });

  interpreterVideo.addEventListener("loadedmetadata", () => {
    syncInterpreterClock(true);
  });

  seekSlider.addEventListener("input", () => {
    isSeeking = true;
    video.currentTime = Number(seekSlider.value);
    updateTimeUI();
  });

  seekSlider.addEventListener("change", () => {
    isSeeking = false;
    syncInterpreterClock(true);
  });

  function updateMuteIcons() {
    const isMuted = video.muted || video.volume === 0;
    volumeOnIcon?.classList.toggle("hidden", isMuted);
    volumeOffIcon?.classList.toggle("hidden", !isMuted);
    muteBtn.setAttribute("aria-label", isMuted ? "Unmute" : "Mute");
    muteBtn.setAttribute("title", isMuted ? "Unmute" : "Mute");
  }

  muteBtn.addEventListener("click", () => {
    video.muted = !video.muted;
    updateMuteIcons();
  });

  volumeSlider.addEventListener("input", () => {
    video.volume = Number(volumeSlider.value);
    if (video.volume > 0 && video.muted) {
      video.muted = false;
    }
    updateMuteIcons();
  });

  speedSelect.addEventListener("change", () => {
    video.playbackRate = Number(speedSelect.value);
  });

  fullscreenBtn.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      stageContainer.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  });

  toggleLayoutBtn.addEventListener("click", () => {
    const isSideBySide = stageContainer.classList.toggle("layout-side-by-side");
    stageContainer.classList.toggle("layout-pip", !isSideBySide);
    toggleLayoutBtn.textContent = isSideBySide ? "Floating PIP" : "Side-by-Side";
    if (isSideBySide) {
      interpreterWindow.style.left = "";
      interpreterWindow.style.top = "";
      interpreterWindow.style.right = "";
      interpreterWindow.style.bottom = "";
    }
  });

  toggleInterpreterBtn.addEventListener("click", () => {
    const hidden = interpreterWindow.classList.toggle("hidden");
    toggleInterpreterBtn.textContent = hidden ? "Show interpreter" : "Hide interpreter";
  });

  toggleTranscriptBtn.addEventListener("click", () => {
    const hidden = transcriptPanel.classList.toggle("hidden");
    workspaceGrid.classList.toggle("transcript-hidden", hidden);
    toggleTranscriptBtn.textContent = hidden ? "Show transcript" : "Hide transcript";
  });

  let dragState = null;
  interpreterDragHandle.addEventListener("pointerdown", (event) => {
    if (stageContainer.classList.contains("layout-side-by-side")) return;
    event.preventDefault();
    const wrapRect = primaryWrap.getBoundingClientRect();
    const winRect = interpreterWindow.getBoundingClientRect();
    dragState = {
      startX: event.clientX,
      startY: event.clientY,
      initLeft: winRect.left - wrapRect.left,
      initTop: winRect.top - wrapRect.top,
      maxLeft: Math.max(0, wrapRect.width - winRect.width),
      maxTop: Math.max(0, wrapRect.height - winRect.height),
    };
    interpreterDragHandle.setPointerCapture(event.pointerId);
  });

  interpreterDragHandle.addEventListener("pointermove", (event) => {
    if (!dragState) return;
    const nextLeft = Math.min(
      dragState.maxLeft,
      Math.max(0, dragState.initLeft + (event.clientX - dragState.startX))
    );
    const nextTop = Math.min(
      dragState.maxTop,
      Math.max(0, dragState.initTop + (event.clientY - dragState.startY))
    );
    interpreterWindow.style.right = "auto";
    interpreterWindow.style.bottom = "auto";
    interpreterWindow.style.left = `${nextLeft}px`;
    interpreterWindow.style.top = `${nextTop}px`;
  });

  interpreterDragHandle.addEventListener("pointerup", () => {
    dragState = null;
  });

  let resizeState = null;
  interpreterResizeHandle.addEventListener("pointerdown", (event) => {
    if (stageContainer.classList.contains("layout-side-by-side")) return;
    event.preventDefault();
    const winRect = interpreterWindow.getBoundingClientRect();
    resizeState = {
      startX: event.clientX,
      startY: event.clientY,
      initWidth: winRect.width,
      initHeight: winRect.height,
    };
    interpreterResizeHandle.setPointerCapture(event.pointerId);
  });

  interpreterResizeHandle.addEventListener("pointermove", (event) => {
    if (!resizeState) return;
    const nextWidth = Math.min(
      460,
      Math.max(170, resizeState.initWidth + (event.clientX - resizeState.startX))
    );
    const nextHeight = Math.min(
      320,
      Math.max(112, resizeState.initHeight + (event.clientY - resizeState.startY))
    );
    interpreterWindow.style.width = `${nextWidth}px`;
    interpreterWindow.style.height = `${nextHeight}px`;
  });

  interpreterResizeHandle.addEventListener("pointerup", () => {
    resizeState = null;
  });

  async function loadPlayerMetadata() {
    try {
      const response = await fetch(`/api/player/${encodeURIComponent(jobId)}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Player data could not be loaded.");
      }

      titleEl.textContent = data.title || "Untitled video";
      const dur = data.media_info?.duration_seconds
        ? formatClock(data.media_info.duration_seconds)
        : "";
      const dims =
        data.media_info?.width && data.media_info?.height
          ? `${data.media_info.width}×${data.media_info.height}`
          : "";
      metaEl.textContent = [
        data.source_type === "youtube" ? "YouTube" : "Uploaded file",
        dims,
        dur,
      ]
        .filter(Boolean)
        .join(" · ");

      if (data.original_video_url) {
        video.src = data.original_video_url;
      } else {
        errorBanner.textContent = "Original video file is missing for this job.";
        errorBanner.classList.remove("hidden");
      }

      if (data.sync_url) {
        try {
          const syncResp = await fetch(data.sync_url);
          if (syncResp.ok) {
            const syncData = await syncResp.json();
            syncSegments = syncData.segments || [];
          }
        } catch {
          syncSegments = [];
        }
      }

      if (data.interpreter_available && data.interpreter_video_url) {
        interpreterAvailable = true;
        interpreterVideo.src = data.interpreter_video_url;
        interpreterVideo.classList.remove("hidden");
        interpreterPlaceholder.classList.add("hidden");
      }
    } catch (err) {
      errorBanner.textContent = err.message || "Failed to initialize video player.";
      errorBanner.classList.remove("hidden");
    }
  }

  loadPlayerMetadata();
})();
