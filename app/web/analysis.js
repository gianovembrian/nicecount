document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const startAnalysisButton = document.getElementById("startAnalysisButton");
  const refreshAnalysisButton = document.getElementById("refreshAnalysisButton");
  const openVideoButton = document.getElementById("openVideoButton");
  const setCountLinesButton = document.getElementById("setCountLinesButton");
  const openVideoPickerButton = document.getElementById("openVideoPickerButton");
  const selectedAnalysisVideoName = document.getElementById("selectedAnalysisVideoName");
  const selectedAnalysisVideoMeta = document.getElementById("selectedAnalysisVideoMeta");
  const selectedAnalysisVideoBadges = document.getElementById("selectedAnalysisVideoBadges");
  const statusText = document.getElementById("analysisStatusText");
  const progressBar = document.getElementById("analysisProgressBar");
  const progressText = document.getElementById("analysisProgressText");
  const videoShell = document.getElementById("analysisVideoShell");
  const playbackShell = document.getElementById("analysisPlaybackShell");
  const livePreview = document.getElementById("analysisLivePreview");
  const videoPlayer = document.getElementById("analysisVideoPlayer");
  const overlayCanvas = document.getElementById("analysisOverlayCanvas");
  const overlayContext = overlayCanvas.getContext("2d");
  const videoTitle = document.getElementById("analysisVideoTitle");
  const videoDescription = document.getElementById("analysisVideoDescription");
  const previewMode = document.getElementById("analysisPreviewMode");
  const previewHint = document.getElementById("analysisPreviewHint");
  const eventsBody = document.getElementById("analysisEventsBody");
  const alertBox = document.getElementById("analysisAlert");
  const clearAnalysisLogsButton = document.getElementById("clearAnalysisLogsButton");
  const analysisLineTabsShell = document.getElementById("analysisLineTabsShell");
  const analysisLineTabs = document.getElementById("analysisLineTabs");
  const videoPickerModalElement = document.getElementById("videoPickerModal");
  const analysisVideoSearch = document.getElementById("analysisVideoSearch");
  const analysisVideoStatusFilter = document.getElementById("analysisVideoStatusFilter");
  const analysisVideoPickerBody = document.getElementById("analysisVideoPickerBody");
  const videoPickerModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(videoPickerModalElement) : null;

  const golonganCodes = ["golongan_1", "golongan_2", "golongan_3", "golongan_4", "golongan_5"];
  const detectedTypeLabels = {
    motorcycle: "motorcycle",
    car: "car (sedan, jeep, suv, pick up kecil)",
    bus: "bus",
    truck: "truck",
  };
  const state = {
    videos: [],
    selectedVideoId: null,
    pollHandle: null,
    previewHandle: null,
    currentPreviewUrl: null,
    currentPreviewObjectUrl: null,
    lastFrameSequence: null,
    previewRequestInFlight: false,
    hasLiveFrame: false,
    currentPlaybackUrl: null,
    overlayUrl: null,
    overlayData: null,
    overlayRenderHandle: null,
    overlayLoadPromise: null,
    videoSearchQuery: "",
    videoStatusFilter: "all",
    availableLines: [],
    selectedLineOrder: null,
    lastAnalysisPayload: null,
    pendingSeekSeconds: null,
  };

  const PICKER_ICONS = {
    select: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="m5 12 4.2 4L19 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </span>
    `,
  };

  function setButtonLabel(button, label) {
    if (!button) {
      return;
    }
    const labelNode = button.querySelector("[data-button-label]");
    if (labelNode) {
      labelNode.textContent = label;
      return;
    }
    button.textContent = label;
  }

  function setButtonDisabled(button, disabled) {
    if (!button) {
      return;
    }
    button.disabled = disabled;
  }

  function formatLineDisplayName(lineOrder) {
    return `Line ${lineOrder}`;
  }

  function getLineEventCount(lineOrder) {
    const events = state.lastAnalysisPayload && Array.isArray(state.lastAnalysisPayload.recent_events)
      ? state.lastAnalysisPayload.recent_events
      : [];
    return events.filter((event) => Number(event.count_line_order || 0) === lineOrder).length;
  }

  function normalizeAnalysisLines(lines) {
    return (lines || [])
      .filter((line) => line && line.is_active !== false)
      .map((line) => ({
        line_order: Number(line.line_order),
        name: formatLineDisplayName(Number(line.line_order)),
      }))
      .sort((left, right) => left.line_order - right.line_order);
  }

  function renderLineTabs() {
    const hasTabs = state.availableLines.length > 1;
    if (!hasTabs) {
      analysisLineTabsShell.classList.add("hidden");
      analysisLineTabs.innerHTML = "";
      state.selectedLineOrder = state.availableLines.length === 1 ? state.availableLines[0].line_order : null;
      return;
    }

    if (!state.availableLines.some((line) => line.line_order === state.selectedLineOrder)) {
      state.selectedLineOrder = state.availableLines[0].line_order;
    }

    analysisLineTabsShell.classList.remove("hidden");
    analysisLineTabs.innerHTML = state.availableLines.map((line) => `
      <button
        class="analysis-line-tab${line.line_order === state.selectedLineOrder ? " active" : ""}"
        type="button"
        data-line-order="${line.line_order}"
      >
        <span class="analysis-line-tab-badge">${line.line_order}</span>
        <span class="analysis-line-tab-label">${app.escapeHtml(line.name)}</span>
        <span class="analysis-line-tab-count">${getLineEventCount(line.line_order)}</span>
      </button>
    `).join("");
  }

  function getVisibleEvents(events) {
    if (state.availableLines.length <= 1 || !state.selectedLineOrder) {
      return events;
    }
    return events.filter((event) => Number(event.count_line_order || 0) === state.selectedLineOrder);
  }

  function buildTotalsFromEvents(events) {
    const totals = {};
    let totalVehicleCount = 0;
    events.forEach((event) => {
      const code = String(event.golongan_code || "");
      if (!code) {
        return;
      }
      totals[code] = (totals[code] || 0) + 1;
      totalVehicleCount += 1;
    });
    return { totals, totalVehicleCount };
  }

  function resetMetrics() {
    golonganCodes.forEach((code) => {
      const metric = document.getElementById(`metric_${code}`);
      if (metric) {
        metric.textContent = "0";
      }
    });
    document.getElementById("metric_total").textContent = "0";
  }

  function renderMasterClassCards(masterClasses) {
    const items = Array.isArray(masterClasses) ? masterClasses : [];
    items.forEach((item) => {
      const code = String(item.code || "");
      if (!code) {
        return;
      }
      const titleElement = document.getElementById(`metric_title_${code}`);
      const noteElement = document.getElementById(`metric_note_${code}`);
      if (titleElement) {
        titleElement.textContent = item.label || code;
      }
      if (noteElement) {
        noteElement.textContent = item.description || "-";
      }
    });
  }

  function formatDetectedType(event) {
    const normalizedVehicleClass = String(event && event.vehicle_class ? event.vehicle_class : "").trim().toLowerCase();
    if (detectedTypeLabels[normalizedVehicleClass]) {
      return detectedTypeLabels[normalizedVehicleClass];
    }
    return event && event.detected_label ? event.detected_label : (normalizedVehicleClass || "-");
  }

  function getSelectedVideo() {
    return state.videos.find((video) => video.id === state.selectedVideoId) || null;
  }

  function thumbnailUrl(video) {
    const stem = String(video && video.stored_filename ? video.stored_filename : "")
      .replace(/\.[^.]+$/, "");
    return stem ? `/storage/thumbnails/${encodeURIComponent(stem)}.jpg` : "";
  }

  function renderSelectedVideoSummary() {
    const video = getSelectedVideo();
    if (!video) {
      selectedAnalysisVideoName.textContent = "No video selected";
      selectedAnalysisVideoMeta.textContent = "Select a video from the Videos module or click the button below to search.";
      selectedAnalysisVideoBadges.innerHTML = "";
      openVideoPickerButton.textContent = "Select Video";
      setCountLinesButton.href = "/count-lines";
      return;
    }

    const analysisStatus = video.analysis_job ? video.analysis_job.status : "pending";
    const recordedOrCreated = video.recorded_at
      ? `Recorded ${app.formatDateTime(video.recorded_at)}`
      : `Uploaded ${app.formatDateTime(video.created_at)}`;
    selectedAnalysisVideoName.textContent = video.stored_filename || video.original_filename;
    selectedAnalysisVideoMeta.textContent = `${recordedOrCreated} • Duration ${app.formatDuration(video.duration_seconds)} • By ${video.uploaded_by || "-"}`;
    selectedAnalysisVideoBadges.innerHTML = `
      <span class="badge ${app.statusBadge(video.status)} status-pill">${app.escapeHtml(video.status)}</span>
      <span class="badge ${app.statusBadge(analysisStatus)} status-pill">${app.escapeHtml(analysisStatus)}</span>
    `;
    openVideoPickerButton.textContent = "Change Video";
    setCountLinesButton.href = `/count-lines?video_id=${video.id}`;
  }

  function renderPickerThumbnail(video) {
    return `
      <div class="app-video-thumb" data-thumb-shell>
        <img
          src="${app.escapeHtml(thumbnailUrl(video))}"
          alt="Thumbnail ${app.escapeHtml(video.original_filename)}"
          loading="lazy"
          data-thumb
        />
        <div class="app-video-thumb-fallback">No Preview</div>
      </div>
    `;
  }

  function bindThumbnailFallbacks(container) {
    container.querySelectorAll("img[data-thumb]").forEach((image) => {
      image.addEventListener("error", () => {
        const shell = image.closest("[data-thumb-shell]");
        if (shell) {
          shell.classList.add("is-fallback");
        }
      }, { once: true });
    });
  }

  function filteredVideos() {
    const searchQuery = state.videoSearchQuery.trim().toLowerCase();
    return state.videos.filter((video) => {
      if (state.videoStatusFilter !== "all" && video.status !== state.videoStatusFilter) {
        return false;
      }

      if (!searchQuery) {
        return true;
      }

      const haystack = [
        video.original_filename,
        video.stored_filename,
        video.description,
        video.uploaded_by,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return haystack.includes(searchQuery);
    });
  }

  function renderVideoPickerList() {
    const videos = filteredVideos();
    if (!videos.length) {
      analysisVideoPickerBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted py-10">No videos match the current search.</td>
        </tr>
      `;
      return;
    }

    analysisVideoPickerBody.innerHTML = videos.map((video, index) => {
      const analysisStatus = video.analysis_job ? video.analysis_job.status : "pending";
      const isSelected = video.id === state.selectedVideoId;
      return `
        <tr>
          <td class="text-gray-700 fw-semibold">${index + 1}</td>
          <td>${renderPickerThumbnail(video)}</td>
          <td>
            <div class="app-user-primary">${app.escapeHtml(video.stored_filename || video.original_filename)}</div>
            <div class="app-user-secondary">${app.escapeHtml(video.description || video.original_filename || "-")}</div>
          </td>
          <td>
            <div><span class="badge ${app.statusBadge(video.status)} status-pill">${app.escapeHtml(video.status)}</span></div>
            <div class="mt-2"><span class="badge ${app.statusBadge(analysisStatus)} status-pill">${app.escapeHtml(analysisStatus)}</span></div>
          </td>
          <td>${app.formatDuration(video.duration_seconds)}</td>
          <td>${app.formatDateTime(video.created_at)}</td>
          <td class="text-end">
            <button
              class="btn btn-sm ${isSelected ? "btn-primary" : "btn-light-primary"}"
              type="button"
              data-picker-action="select"
              data-id="${video.id}"
            >
              ${PICKER_ICONS.select}
              <span>${isSelected ? "Selected" : "Select"}</span>
            </button>
          </td>
        </tr>
      `;
    }).join("");

    bindThumbnailFallbacks(analysisVideoPickerBody);
  }

  async function selectVideoById(videoId, { closeModal = true } = {}) {
    if (!videoId || videoId === state.selectedVideoId) {
      if (closeModal && videoPickerModal) {
        videoPickerModal.hide();
      }
      return;
    }

    state.selectedVideoId = videoId;
    renderSelectedVideoSummary();
    renderVideoPickerList();
    stopPolling();
    stopLivePreview();
    resetOverlayState();
    state.availableLines = [];
    state.selectedLineOrder = null;
    state.lastAnalysisPayload = null;
    renderLineTabs();
    resetMetrics();
    await loadAnalysis();
    if (closeModal && videoPickerModal) {
      videoPickerModal.hide();
    }
  }

  function stopPolling() {
    if (state.pollHandle) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  }

  function setPreviewMode(badgeClass, text, hint) {
    previewMode.className = `badge ${badgeClass}`;
    previewMode.textContent = text;
    previewHint.textContent = hint;
  }

  function clearOverlayCanvas() {
    overlayContext.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  }

  function stopOverlayLoop() {
    if (state.overlayRenderHandle) {
      window.cancelAnimationFrame(state.overlayRenderHandle);
      state.overlayRenderHandle = null;
    }
  }

  function resetOverlayState({ keepData = false } = {}) {
    stopOverlayLoop();
    if (!keepData) {
      state.overlayUrl = null;
      state.overlayData = null;
      state.overlayLoadPromise = null;
    }
    overlayCanvas.classList.add("hidden");
    clearOverlayCanvas();
  }

  function stopLivePreview() {
    if (state.previewHandle) {
      window.clearInterval(state.previewHandle);
      state.previewHandle = null;
    }

    if (state.currentPreviewObjectUrl) {
      URL.revokeObjectURL(state.currentPreviewObjectUrl);
      state.currentPreviewObjectUrl = null;
    }

    livePreview.removeAttribute("src");
    state.currentPreviewUrl = null;
    state.lastFrameSequence = null;
    state.previewRequestInFlight = false;
    state.hasLiveFrame = false;
  }

  function showPlaybackShell() {
    livePreview.classList.add("hidden");
    playbackShell.classList.remove("hidden");
    videoPlayer.classList.remove("hidden");
  }

  function showLivePreviewShell() {
    playbackShell.classList.add("hidden");
    livePreview.classList.remove("hidden");
  }

  function setProgress(value) {
    const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
    progressBar.style.width = `${safeValue}%`;
    progressText.textContent = `${safeValue.toFixed(1)}%`;
  }

  function isStaleRunningJob(job) {
    if (!job || !["processing", "queued"].includes(job.status)) {
      return false;
    }

    const referenceValue = job.updated_at || job.started_at || job.created_at;
    if (!referenceValue) {
      return false;
    }

    const referenceTime = new Date(referenceValue);
    if (Number.isNaN(referenceTime.getTime())) {
      return false;
    }

    return (Date.now() - referenceTime.getTime()) > 45000;
  }

  async function fetchLatestPreviewFrame() {
    if (!state.currentPreviewUrl || state.previewRequestInFlight) {
      return;
    }

    state.previewRequestInFlight = true;
    try {
      const response = await fetch(`${state.currentPreviewUrl}?t=${Date.now()}`, {
        credentials: "same-origin",
        cache: "no-store",
      });

      if (response.status === 204 || !response.ok) {
        return;
      }

      const frameSequence = response.headers.get("X-Frame-Sequence");
      if (frameSequence && state.lastFrameSequence === frameSequence) {
        return;
      }

      const frameBlob = await response.blob();
      const objectUrl = URL.createObjectURL(frameBlob);

      if (state.currentPreviewObjectUrl) {
        URL.revokeObjectURL(state.currentPreviewObjectUrl);
      }

      state.currentPreviewObjectUrl = objectUrl;
      state.lastFrameSequence = frameSequence;
      state.hasLiveFrame = true;
      livePreview.src = objectUrl;
      showLivePreviewShell();
    } catch (error) {
      console.error("preview polling failed", error);
    } finally {
      state.previewRequestInFlight = false;
    }
  }

  function showLivePreview(frameUrl, hint, badgeText = "Live Detection") {
    resetOverlayState();
    if (state.currentPreviewUrl !== frameUrl) {
      stopLivePreview();
      state.currentPreviewUrl = frameUrl;
      state.lastFrameSequence = null;
    }

    setPreviewMode("badge-light-success", badgeText, hint);
    if (!state.previewHandle) {
      fetchLatestPreviewFrame();
      state.previewHandle = window.setInterval(fetchLatestPreviewFrame, 350);
    }
  }

  async function ensureOverlayData(overlayUrl) {
    if (!overlayUrl) {
      resetOverlayState();
      return null;
    }

    if (state.overlayUrl === overlayUrl && state.overlayData) {
      return state.overlayData;
    }

    if (state.overlayUrl === overlayUrl && state.overlayLoadPromise) {
      return state.overlayLoadPromise;
    }

    state.overlayUrl = overlayUrl;
    state.overlayData = null;
    state.overlayLoadPromise = fetch(`${overlayUrl}?t=${Date.now()}`, {
      credentials: "same-origin",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error("Failed to load overlay metadata");
      }
      return response.json();
    }).then((payload) => {
      state.overlayData = payload;
      return payload;
    }).finally(() => {
      state.overlayLoadPromise = null;
    });

    return state.overlayLoadPromise;
  }

  function syncCanvasSize() {
    const rect = videoPlayer.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return false;
    }

    const devicePixelRatio = window.devicePixelRatio || 1;
    const targetWidth = Math.max(1, Math.round(rect.width * devicePixelRatio));
    const targetHeight = Math.max(1, Math.round(rect.height * devicePixelRatio));

    if (overlayCanvas.width !== targetWidth || overlayCanvas.height !== targetHeight) {
      overlayCanvas.width = targetWidth;
      overlayCanvas.height = targetHeight;
      overlayContext.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    }

    return true;
  }

  function findOverlayFrame(timeSeconds) {
    const frames = state.overlayData && state.overlayData.frames ? state.overlayData.frames : [];
    if (!frames.length) {
      return null;
    }

    let low = 0;
    let high = frames.length - 1;
    let result = frames[0];

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const frame = frames[mid];
      if (Number(frame.time_seconds || 0) <= timeSeconds) {
        result = frame;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    return result;
  }

  function drawOverlayLines(canvasWidth, canvasHeight) {
    const analysis = state.overlayData && state.overlayData.analysis ? state.overlayData.analysis : null;
    const lines = analysis && Array.isArray(analysis.lines) && analysis.lines.length
      ? analysis.lines
      : (analysis && analysis.line ? [analysis.line] : []);
    if (!lines.length) {
      return;
    }

    const colors = ["#FACC15", "#22D3EE"];
    lines.forEach((line, index) => {
      overlayContext.save();
      overlayContext.strokeStyle = colors[index % colors.length];
      overlayContext.lineWidth = 3;
      overlayContext.beginPath();
      overlayContext.moveTo(Number(line.start_x || 0) * canvasWidth, Number(line.start_y || 0) * canvasHeight);
      overlayContext.lineTo(Number(line.end_x || 0) * canvasWidth, Number(line.end_y || 0) * canvasHeight);
      overlayContext.stroke();
      overlayContext.restore();
    });
  }

  function drawOverlayBoxes(frame, canvasWidth, canvasHeight) {
    const detections = frame && frame.detections ? frame.detections : [];
    detections.forEach((detection) => {
      const x1 = Number(detection.x1 || 0) * canvasWidth;
      const y1 = Number(detection.y1 || 0) * canvasHeight;
      const x2 = Number(detection.x2 || 0) * canvasWidth;
      const y2 = Number(detection.y2 || 0) * canvasHeight;
      const width = Math.max(x2 - x1, 1);
      const height = Math.max(y2 - y1, 1);
      const label = `${detection.track_id ?? "-"} ${detection.source_label || detection.vehicle_class} ${(Number(detection.confidence || 0) * 100).toFixed(0)}%`;

      overlayContext.save();
      overlayContext.strokeStyle = "#00E676";
      overlayContext.lineWidth = 2;
      overlayContext.strokeRect(x1, y1, width, height);

      overlayContext.font = "600 13px Inter, sans-serif";
      const textWidth = overlayContext.measureText(label).width;
      const textX = x1;
      const textY = Math.max(y1 - 22, 6);
      overlayContext.fillStyle = "rgba(0, 20, 48, 0.88)";
      overlayContext.fillRect(textX, textY, textWidth + 12, 20);
      overlayContext.fillStyle = "#FFFFFF";
      overlayContext.fillText(label, textX + 6, textY + 14);
      overlayContext.restore();
    });
  }

  function drawCurrentOverlayFrame() {
    if (!state.overlayData || !syncCanvasSize()) {
      overlayCanvas.classList.add("hidden");
      clearOverlayCanvas();
      return;
    }

    const canvasWidth = overlayCanvas.width / (window.devicePixelRatio || 1);
    const canvasHeight = overlayCanvas.height / (window.devicePixelRatio || 1);
    clearOverlayCanvas();
    drawOverlayLines(canvasWidth, canvasHeight);
    drawOverlayBoxes(findOverlayFrame(videoPlayer.currentTime || 0), canvasWidth, canvasHeight);
    overlayCanvas.classList.remove("hidden");
  }

  function stepOverlayLoop() {
    drawCurrentOverlayFrame();
    if (!videoPlayer.paused && !videoPlayer.ended) {
      state.overlayRenderHandle = window.requestAnimationFrame(stepOverlayLoop);
    } else {
      state.overlayRenderHandle = null;
    }
  }

  function restartOverlayLoop() {
    stopOverlayLoop();
    if (!state.overlayData) {
      return;
    }

    stepOverlayLoop();
  }

  async function showPlayback(options) {
    const {
      videoUrl,
      hint,
      badgeText = "Playback",
      overlayUrl = null,
    } = options;

    stopLivePreview();
    showPlaybackShell();

    if (videoUrl && state.currentPlaybackUrl !== videoUrl) {
      videoPlayer.src = videoUrl;
      state.currentPlaybackUrl = videoUrl;
      videoPlayer.load();
    }

    if (overlayUrl) {
      try {
        await ensureOverlayData(overlayUrl);
        setPreviewMode("badge-light-primary", badgeText, hint);
        if (!videoPlayer.paused && !videoPlayer.ended) {
          restartOverlayLoop();
        } else {
          drawCurrentOverlayFrame();
        }
      } catch (error) {
        resetOverlayState();
        setPreviewMode("badge-light-warning", "Playback", "Overlay metadata could not be loaded. The video will continue to play normally.");
      }
    } else {
      resetOverlayState();
      setPreviewMode("badge-light-primary", badgeText, hint);
    }
  }

  function renderEvents(events) {
    if (!events.length) {
      eventsBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-muted py-10">No vehicles have been recorded yet.</td>
        </tr>
      `;
      return;
    }

    eventsBody.innerHTML = events.map((event, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>
          <button
            class="analysis-time-button"
            type="button"
            data-seek-seconds="${Number(event.crossed_at_seconds || 0).toFixed(4)}"
            title="Jump playback to this time"
          >
            ${Number(event.crossed_at_seconds || 0).toFixed(2)} s
          </button>
        </td>
        <td>${app.escapeHtml(formatDetectedType(event))}</td>
        <td><span class="badge badge-light-primary">${app.escapeHtml(event.golongan_label)}</span></td>
        <td>${app.escapeHtml(event.direction)}</td>
        <td>${event.confidence ? `${(Number(event.confidence) * 100).toFixed(1)}%` : "-"}</td>
      </tr>
    `).join("");
  }

  function applyPendingSeek({ autoplay = false } = {}) {
    if (state.pendingSeekSeconds === null || Number.isNaN(Number(state.pendingSeekSeconds))) {
      return;
    }

    const duration = Number(videoPlayer.duration || 0);
    const targetSeconds = duration > 0
      ? Math.min(Math.max(Number(state.pendingSeekSeconds), 0), Math.max(duration - 0.05, 0))
      : Math.max(Number(state.pendingSeekSeconds), 0);

    state.pendingSeekSeconds = null;
    videoPlayer.currentTime = targetSeconds;
    drawCurrentOverlayFrame();

    if (autoplay) {
      const playPromise = videoPlayer.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => {});
      }
    }
  }

  function seekPlaybackTo(seconds) {
    const targetSeconds = Number(seconds);
    if (!Number.isFinite(targetSeconds)) {
      return;
    }

    if (playbackShell.classList.contains("hidden")) {
      stopLivePreview();
      showPlaybackShell();
    }

    state.pendingSeekSeconds = Math.max(targetSeconds, 0);

    if (videoPlayer.readyState >= 1) {
      applyPendingSeek({ autoplay: true });
      return;
    }

    drawCurrentOverlayFrame();
  }

  async function renderAnalysis(payload) {
    state.lastAnalysisPayload = payload;
    const video = payload.video;
    const job = payload.job;
    const playbackUrl = video ? `/api/videos/${video.id}/playback` : null;

    renderSelectedVideoSummary();
    renderVideoPickerList();
    renderMasterClassCards(payload.master_classes);
    state.availableLines = normalizeAnalysisLines(payload.count_lines);
    renderLineTabs();

    const visibleEvents = getVisibleEvents(payload.recent_events || []);
    const hasLineTabs = state.availableLines.length > 1;
    const totals = {};
    let totalVehicleCount = 0;
    if (hasLineTabs) {
      const lineTotals = buildTotalsFromEvents(visibleEvents);
      Object.assign(totals, lineTotals.totals);
      totalVehicleCount = lineTotals.totalVehicleCount;
    } else {
      (payload.totals || []).forEach((row) => {
        totals[row.golongan_code] = row.vehicle_count;
        totalVehicleCount += Number(row.vehicle_count || 0);
      });
    }

    golonganCodes.forEach((code) => {
      const metric = document.getElementById(`metric_${code}`);
      if (metric) {
        metric.textContent = String(totals[code] || 0);
      }
    });
    document.getElementById("metric_total").textContent = String(totalVehicleCount);

    videoTitle.textContent = video.original_filename;
    videoDescription.textContent = video.description || "No description";
    openVideoButton.href = payload.video_url || "/videos";
    openVideoButton.target = "_blank";
    openVideoButton.rel = "noreferrer";
    setButtonLabel(openVideoButton, "Open Original File");

    const jobStatus = job ? job.status : "pending";
    const isStaleRunning = isStaleRunningJob(job);
    const displayJobStatus = isStaleRunning ? "stale" : jobStatus;
    statusText.innerHTML = `
      <span class="badge ${app.statusBadge(displayJobStatus)} status-pill me-2">${app.escapeHtml(displayJobStatus)}</span>
      <span class="soft-note">Video status: ${app.escapeHtml(video.status)}</span>
    `;
    setProgress(payload.progress_percent || 0);

    if (job && job.error_message) {
      app.setAlert(alertBox, "danger", job.error_message);
    }

    renderEvents(visibleEvents);

    const isRunning = jobStatus === "processing" || jobStatus === "queued";
    if (isRunning && !isStaleRunning && payload.analysis_frame_url) {
      if (playbackUrl && state.currentPlaybackUrl !== playbackUrl) {
        videoPlayer.src = playbackUrl;
        state.currentPlaybackUrl = playbackUrl;
        videoPlayer.load();
      }

      if (!state.hasLiveFrame) {
        showPlaybackShell();
        resetOverlayState();
      }

      const liveHint = jobStatus === "queued"
        ? "The model is being prepared. The live preview will appear as soon as the first frame is processed."
        : "Analysis is running. A snapshot preview is shown for now. When processing finishes, the video will play normally with synchronized overlay boxes.";
      showLivePreview(payload.analysis_frame_url, liveHint, jobStatus === "queued" ? "Preparing Live Preview" : "Live Detection");
    } else {
      const playbackHint = isStaleRunning
        ? "The previous analysis job is no longer active. Click Start Analysis to run it again."
        : payload.analysis_overlay_url
        ? "The original video plays normally. Detection boxes are drawn in sync on the canvas overlay using batch analysis results."
        : payload.annotated_video_url
        ? "Analysis is complete. An annotated result video is available."
        : "No live preview is active yet. You can play the original video or start analysis.";

      await showPlayback({
        videoUrl: playbackUrl,
        overlayUrl: payload.analysis_overlay_url,
        hint: playbackHint,
        badgeText: payload.analysis_overlay_url ? "Smooth Overlay Playback" : (payload.annotated_video_url ? "Annotated Playback" : "Playback"),
      });

      if (payload.annotated_video_url) {
        openVideoButton.href = payload.annotated_video_url;
        setButtonLabel(openVideoButton, "Open Result Video");
      }
    }

    startAnalysisButton.disabled = !state.selectedVideoId || (isRunning && !isStaleRunning);
    setButtonDisabled(clearAnalysisLogsButton, !state.selectedVideoId || (isRunning && !isStaleRunning));

    stopPolling();
    if (isRunning) {
      state.pollHandle = window.setInterval(loadAnalysis, 1200);
    }
  }

  async function loadVideos() {
    state.videos = await app.apiFetch("/api/videos");
    const url = new URL(window.location.href);
    const requestedId = url.searchParams.get("video_id");
    if (requestedId && state.videos.some((video) => video.id === requestedId)) {
      state.selectedVideoId = requestedId;
    } else if (state.selectedVideoId && !state.videos.some((video) => video.id === state.selectedVideoId)) {
      state.selectedVideoId = null;
    }
    renderSelectedVideoSummary();
    renderVideoPickerList();
  }

  async function loadAnalysis() {
    if (!state.selectedVideoId) {
      statusText.textContent = "No video selected";
      resetMetrics();
      renderEvents([]);
      state.availableLines = [];
      state.selectedLineOrder = null;
      state.lastAnalysisPayload = null;
      renderLineTabs();
      renderSelectedVideoSummary();
      videoTitle.textContent = "No video selected";
      videoDescription.textContent = "Select a video from the video list or use the Select Video button to find a video to analyze.";
      openVideoButton.href = "/videos";
      openVideoButton.target = "";
      openVideoButton.rel = "";
      setButtonLabel(openVideoButton, "Manage Videos");
      setCountLinesButton.href = "/count-lines";
      setButtonDisabled(clearAnalysisLogsButton, true);
      stopLivePreview();
      resetOverlayState();
      videoPlayer.removeAttribute("src");
      state.currentPlaybackUrl = null;
      videoPlayer.load();
      showPlaybackShell();
      setPreviewMode("badge-light", "Idle", "While analysis is running, this area will show a live preview. After processing finishes, the video will play normally with synchronized overlay boxes.");
      setProgress(0);
      return;
    }

    try {
      app.setAlert(alertBox, "danger", "");
      const payload = await app.apiFetch(`/api/videos/${state.selectedVideoId}/analysis`);
      await renderAnalysis(payload);
      const url = new URL(window.location.href);
      url.searchParams.set("video_id", state.selectedVideoId);
      window.history.replaceState({}, "", url);
    } catch (error) {
      stopPolling();
      app.setAlert(alertBox, "danger", error.message);
    }
  }

  videoPlayer.addEventListener("loadedmetadata", () => {
    if (videoPlayer.videoWidth && videoPlayer.videoHeight) {
      videoShell.style.aspectRatio = `${videoPlayer.videoWidth} / ${videoPlayer.videoHeight}`;
    }
    applyPendingSeek();
    if (state.overlayData && !videoPlayer.paused && !videoPlayer.ended) {
      restartOverlayLoop();
      return;
    }
    drawCurrentOverlayFrame();
  });
  videoPlayer.addEventListener("play", restartOverlayLoop);
  videoPlayer.addEventListener("pause", () => {
    stopOverlayLoop();
    drawCurrentOverlayFrame();
  });
  videoPlayer.addEventListener("seeked", drawCurrentOverlayFrame);
  videoPlayer.addEventListener("timeupdate", drawCurrentOverlayFrame);
  videoPlayer.addEventListener("ended", () => {
    stopOverlayLoop();
    drawCurrentOverlayFrame();
  });
  window.addEventListener("resize", drawCurrentOverlayFrame);

  try {
    await app.requireSession();
    await loadVideos();
    await loadAnalysis();
  } catch (error) {
    app.setAlert(alertBox, "danger", error.message);
    return;
  }

  openVideoPickerButton.addEventListener("click", () => {
    app.setAlert(alertBox, "danger", "");
    state.videoSearchQuery = "";
    state.videoStatusFilter = "all";
    analysisVideoSearch.value = "";
    analysisVideoStatusFilter.value = "all";
    renderVideoPickerList();
    if (videoPickerModal) {
      videoPickerModal.show();
    }
  });

  analysisVideoSearch.addEventListener("input", () => {
    state.videoSearchQuery = analysisVideoSearch.value || "";
    renderVideoPickerList();
  });

  analysisVideoStatusFilter.addEventListener("change", () => {
    state.videoStatusFilter = analysisVideoStatusFilter.value || "all";
    renderVideoPickerList();
  });

  analysisVideoPickerBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-picker-action='select']");
    if (!button) {
      return;
    }

    await selectVideoById(button.dataset.id);
  });

  eventsBody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-seek-seconds]");
    if (!button) {
      return;
    }

    seekPlaybackTo(button.dataset.seekSeconds);
  });

  analysisLineTabs.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-line-order]");
    if (!button) {
      return;
    }
    const lineOrder = Number(button.dataset.lineOrder || 0);
    if (!lineOrder || lineOrder === state.selectedLineOrder) {
      return;
    }
    state.selectedLineOrder = lineOrder;
    renderLineTabs();
    if (state.lastAnalysisPayload) {
      await renderAnalysis(state.lastAnalysisPayload);
    }
  });

  refreshAnalysisButton.addEventListener("click", async () => {
    await loadVideos();
    await loadAnalysis();
  });

  clearAnalysisLogsButton.addEventListener("click", async () => {
    if (!state.selectedVideoId) {
      app.setAlert(alertBox, "danger", "Select a video first");
      return;
    }

    if (!window.confirm("Are you sure you want to delete the Detected Vehicle Logs?")) {
      return;
    }

    try {
      app.setAlert(alertBox, "danger", "");
      await app.apiFetch(`/api/videos/${state.selectedVideoId}/analysis/clear`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      state.hasLiveFrame = false;
      await loadVideos();
      await loadAnalysis();
      app.setAlert(alertBox, "success", "Detected vehicle logs deleted successfully");
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });

  startAnalysisButton.addEventListener("click", async () => {
    if (!state.selectedVideoId) {
      app.setAlert(alertBox, "danger", "Select a video first");
      return;
    }

    try {
      app.setAlert(alertBox, "danger", "");
      await app.apiFetch(`/api/videos/${state.selectedVideoId}/analysis/start`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      state.hasLiveFrame = false;
      resetOverlayState();
      await loadAnalysis();
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });

  window.addEventListener("beforeunload", () => {
    stopPolling();
    stopLivePreview();
    resetOverlayState();
  });
});
