(() => {
  const jobId = document.body.dataset.jobId;
  if (!jobId) return;

  const jobTitleEl = document.getElementById("job-title");
  const jobMetaEl = document.getElementById("job-meta");
  const jobStatusTextEl = document.getElementById("job-status-text");
  const stageLabelEl = document.getElementById("stage-label");
  const progressPctEl = document.getElementById("overall-progress-pct");
  const progressBarEl = document.getElementById("overall-progress-bar");
  const stageRows = Array.from(document.querySelectorAll(".pipeline-stage"));
  const previewBox = document.getElementById("preview-box");
  const previewText = document.getElementById("transcript-preview-text");
  const errorBox = document.getElementById("error-box");
  const errorMsg = document.getElementById("error-message");
  const completeActions = document.getElementById("complete-actions");

  const STAGE_ORDER = [
    "ingesting",
    "extracting_audio",
    "transcribing",
    "translating",
    "matching",
    "compiling",
    "completed",
  ];
  let pollTimer = null;
  let redirected = false;

  function updateStageList(currentStage, status) {
    const activeIndex = STAGE_ORDER.indexOf(currentStage);

    stageRows.forEach((row) => {
      const rowStage = row.dataset.stage;
      const rowIndex = STAGE_ORDER.indexOf(rowStage);
      const stateEl = row.querySelector(".stage-state");

      row.classList.remove("is-active", "is-done", "is-failed");

      if (status === "failed") {
        if (rowIndex < activeIndex || (activeIndex === -1 && rowIndex === 0)) {
          row.classList.add("is-failed");
          stateEl.textContent = "Stopped";
        } else {
          stateEl.textContent = "Pending";
        }
        return;
      }

      if (status === "completed") {
        row.classList.add("is-done");
        stateEl.textContent = "Done";
        return;
      }

      if (rowIndex < activeIndex) {
        row.classList.add("is-done");
        stateEl.textContent = "Done";
      } else if (rowIndex === activeIndex) {
        row.classList.add("is-active");
        stateEl.textContent = "In progress";
      } else {
        stateEl.textContent = "Pending";
      }
    });
  }

  async function pollJobStatus() {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job = await response.json();

      if (!response.ok) {
        throw new Error(job.error || "Processing job could not be found.");
      }

      jobTitleEl.textContent = job.title || "Untitled video";
      const sourceText = job.source_type === "youtube" ? "YouTube video" : "Uploaded file";
      jobMetaEl.textContent = sourceText;

      const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
      progressPctEl.textContent = `${pct}%`;
      progressBarEl.style.width = `${pct}%`;
      stageLabelEl.textContent = job.stage_label || "Processing…";

      updateStageList(job.stage, job.status);

      if (job.transcript_preview) {
        previewBox.classList.remove("hidden");
        previewText.textContent = job.transcript_preview;
      }

      jobStatusTextEl.classList.remove("is-completed", "is-failed");

      if (job.status === "completed") {
        jobStatusTextEl.textContent = "Completed";
        jobStatusTextEl.classList.add("is-completed");
        completeActions.classList.remove("hidden");
        clearInterval(pollTimer);
        if (!redirected) {
          redirected = true;
          setTimeout(() => {
            window.location.href = `/player/${encodeURIComponent(jobId)}`;
          }, 700);
        }
        return;
      }

      if (job.status === "failed") {
        jobStatusTextEl.textContent = "Failed";
        jobStatusTextEl.classList.add("is-failed");
        errorMsg.textContent = job.error || "Processing failed.";
        errorBox.classList.remove("hidden");
        clearInterval(pollTimer);
        return;
      }

      jobStatusTextEl.textContent = "Processing";
    } catch (err) {
      jobStatusTextEl.textContent = "Error";
      jobStatusTextEl.classList.add("is-failed");
      errorMsg.textContent = err.message || "Unable to fetch job status.";
      errorBox.classList.remove("hidden");
      clearInterval(pollTimer);
    }
  }

  pollJobStatus();
  pollTimer = setInterval(pollJobStatus, 800);
})();
