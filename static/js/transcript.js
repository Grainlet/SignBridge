window.SignBridgeTranscript = (() => {
  function formatTimestamp(seconds) {
    const safe = Math.max(0, Number(seconds) || 0);
    const mins = Math.floor(safe / 60);
    const secs = Math.floor(safe % 60);
    const tenths = Math.floor((safe % 1) * 10);
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${tenths}`;
  }

  function findActiveSentenceIndex(sentences, currentTime) {
    for (let i = 0; i < sentences.length; i += 1) {
      const seg = sentences[i];
      if (currentTime >= seg.start && currentTime <= seg.end + 0.15) {
        return i;
      }
    }
    return -1;
  }

  function formatAslNote(seg) {
    const status = seg.asl_status || "unavailable";
    const glossText = seg.asl_gloss_text || "";
    const missing = Array.isArray(seg.missing_words) ? seg.missing_words : [];

    if (status === "matched" && glossText) {
      return `ASL: ${glossText}`;
    }
    if (status === "partial" && glossText) {
      const missStr = missing.length ? ` · Unavailable: ${missing.join(", ")}` : "";
      return `Partial ASL: ${glossText}${missStr}`;
    }
    if (status === "pending_phase_3") {
      return "ASL translation pending";
    }
    return "ASL translation unavailable for this phrase";
  }

  function initTranscript({ jobId, onSeek, onActiveSentenceChange }) {
    const summaryEl = document.getElementById("transcript-summary");
    const listEl = document.getElementById("transcript-list");
    const searchInput = document.getElementById("transcript-search");
    const copyBtn = document.getElementById("copy-transcript-btn");
    const downloadBtn = document.getElementById("download-json-btn");

    let transcriptData = null;
    let sentences = [];
    let activeIndex = -1;
    let cueButtons = [];

    function renderSentences(filterText = "") {
      const query = filterText.trim().toLowerCase();
      listEl.innerHTML = "";
      cueButtons = [];

      if (!sentences.length) {
        listEl.innerHTML =
          '<p class="empty-state">No spoken English speech was detected in this video.</p>';
        return;
      }

      const filtered = sentences
        .map((seg, idx) => ({ seg, idx }))
        .filter(
          ({ seg }) =>
            !query ||
            seg.text.toLowerCase().includes(query) ||
            (seg.asl_gloss_text || "").toLowerCase().includes(query)
        );

      if (!filtered.length) {
        listEl.innerHTML =
          '<p class="empty-state">No transcript sentences match your search.</p>';
        return;
      }

      filtered.forEach(({ seg, idx }) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "transcript-cue";
        btn.dataset.index = String(idx);
        btn.setAttribute("role", "listitem");

        const timeSpan = document.createElement("span");
        timeSpan.className = "cue-time mono tabular";
        timeSpan.textContent = formatTimestamp(seg.start);

        const bodySpan = document.createElement("span");
        bodySpan.className = "cue-body";

        const textSpan = document.createElement("span");
        textSpan.className = "cue-text";
        textSpan.textContent = seg.text;

        const statusSpan = document.createElement("span");
        statusSpan.className = "cue-asl-note";
        if (seg.asl_status === "matched") {
          statusSpan.classList.add("is-matched");
        } else if (seg.asl_status === "partial") {
          statusSpan.classList.add("is-partial");
        } else {
          statusSpan.classList.add("is-unavailable");
        }
        statusSpan.textContent = formatAslNote(seg);

        bodySpan.appendChild(textSpan);
        bodySpan.appendChild(statusSpan);

        btn.appendChild(timeSpan);
        btn.appendChild(bodySpan);

        btn.addEventListener("click", () => {
          if (onSeek) onSeek(seg.start);
        });

        if (idx === activeIndex) {
          btn.classList.add("is-active");
        }

        listEl.appendChild(btn);
        cueButtons.push({ idx, btn });
      });
    }

    async function load() {
      try {
        const response = await fetch(`/api/transcript/${encodeURIComponent(jobId)}`);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Failed to load transcript.");
        }

        transcriptData = data;
        sentences = data.sentences || [];
        const wordCount = (data.segments || []).length;
        summaryEl.textContent = `${sentences.length} lines · ${wordCount.toLocaleString()} words`;
        renderSentences();
      } catch (err) {
        summaryEl.textContent = "Unavailable";
        listEl.innerHTML = `<p class="empty-state">${err.message || "Could not load transcript."}</p>`;
      }
    }

    function syncTime(currentTime) {
      const nextIdx = findActiveSentenceIndex(sentences, currentTime);
      if (nextIdx === activeIndex) return;

      activeIndex = nextIdx;
      cueButtons.forEach(({ idx, btn }) => {
        btn.classList.toggle("is-active", idx === activeIndex);
      });

      const activeBtnObj = cueButtons.find((item) => item.idx === activeIndex);
      if (activeBtnObj) {
        activeBtnObj.btn.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }

      if (onActiveSentenceChange) {
        onActiveSentenceChange(activeIndex >= 0 ? sentences[activeIndex] : null);
      }
    }

    searchInput.addEventListener("input", () => {
      renderSentences(searchInput.value);
    });

    copyBtn.addEventListener("click", async () => {
      if (!transcriptData || !transcriptData.text) return;
      try {
        await navigator.clipboard.writeText(transcriptData.text);
        const prev = copyBtn.textContent;
        copyBtn.textContent = "Copied";
        setTimeout(() => {
          copyBtn.textContent = prev;
        }, 1200);
      } catch {
      }
    });

    downloadBtn.addEventListener("click", () => {
      if (!transcriptData) return;
      const blob = new Blob([JSON.stringify(transcriptData, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `signbridge-transcript-${jobId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });

    load();
    return { syncTime };
  }

  return { initTranscript, formatTimestamp };
})();
