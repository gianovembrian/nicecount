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
  const analysisEstimatedTimeText = document.getElementById("analysisEstimatedTimeText");
  const analysisProcessingTimeText = document.getElementById("analysisProcessingTimeText");
  const videoShell = document.getElementById("analysisVideoShell");
  const playbackShell = document.getElementById("analysisPlaybackShell");
  const livePreview = document.getElementById("analysisLivePreview");
  const videoPlayer = document.getElementById("analysisVideoPlayer");
  const overlayCanvas = document.getElementById("analysisOverlayCanvas");
  const overlayContext = overlayCanvas.getContext("2d");
  const overlayMath = window.AnalysisOverlayMath || {};
  const videoTitle = document.getElementById("analysisVideoTitle");
  const videoDescription = document.getElementById("analysisVideoDescription");
  const previewMode = document.getElementById("analysisPreviewMode");
  const previewHint = document.getElementById("analysisPreviewHint");
  const analysisTotalSummary = document.getElementById("analysisTotalSummary");
  const analysisMetricsGrid = document.getElementById("analysisMetricsGrid");
  const analysisClassChartElement = document.getElementById("analysisClassChart");
  const analysisChartSummary = document.getElementById("analysisChartSummary");
  const eventsBody = document.getElementById("analysisEventsBody");
  const alertBox = document.getElementById("analysisAlert");
  const exportAnalysisExcelButton = document.getElementById("exportAnalysisExcelButton");
  const clearAnalysisLogsButton = document.getElementById("clearAnalysisLogsButton");
  const analysisLineTabsShell = document.getElementById("analysisLineTabsShell");
  const analysisLineTabs = document.getElementById("analysisLineTabs");
  const videoPickerModalElement = document.getElementById("videoPickerModal");
  const analysisVideoSearch = document.getElementById("analysisVideoSearch");
  const analysisVideoStatusFilter = document.getElementById("analysisVideoStatusFilter");
  const analysisVideoPickerBody = document.getElementById("analysisVideoPickerBody");
  const videoPickerModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(videoPickerModalElement) : null;

  const METRIC_CARD_THEMES = [
    "metric-card-success",
    "metric-card-warning",
    "metric-card-primary",
    "metric-card-info",
    "metric-card-danger",
    "metric-card-dark",
  ];
  const CHART_BAR_COLORS = [
    "#50CD89",
    "#FFC700",
    "#009EF7",
    "#50CDFF",
    "#F1416C",
    "#3F4254",
  ];
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
    statusClockHandle: null,
    masterClasses: [],
    classChart: null,
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
  const ANALYSIS_ACTION_ICONS = {
    start: `
      <svg viewBox="0 0 24 24" fill="none">
        <path d="m9 7 8 5-8 5V7Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
      </svg>
    `,
    stop: `
      <svg viewBox="0 0 24 24" fill="none">
        <rect x="7" y="7" width="10" height="10" rx="1.8" stroke="currentColor" stroke-width="1.8"/>
      </svg>
    `,
    refresh: `
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M20 12a8 8 0 1 1-2.34-5.66" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M20 5v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
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

  function setAnalysisActionButton({ mode, disabled = false }) {
    const iconNode = startAnalysisButton.querySelector("[data-button-icon]");
    startAnalysisButton.classList.remove("btn-primary", "btn-danger", "btn-light-primary", "btn-light-danger");

    if (mode === "stop") {
      startAnalysisButton.classList.add("btn-danger");
      if (iconNode) {
        iconNode.innerHTML = ANALYSIS_ACTION_ICONS.stop;
      }
      setButtonLabel(startAnalysisButton, "Stop Analysis");
    } else if (mode === "stopping") {
      startAnalysisButton.classList.add("btn-light-danger");
      if (iconNode) {
        iconNode.innerHTML = ANALYSIS_ACTION_ICONS.stop;
      }
      setButtonLabel(startAnalysisButton, "Stopping...");
    } else if (mode === "converting") {
      startAnalysisButton.classList.add("btn-light-primary");
      if (iconNode) {
        iconNode.innerHTML = ANALYSIS_ACTION_ICONS.start;
      }
      setButtonLabel(startAnalysisButton, "Converting...");
    } else {
      startAnalysisButton.classList.add("btn-primary");
      if (iconNode) {
        iconNode.innerHTML = ANALYSIS_ACTION_ICONS.start;
      }
      setButtonLabel(startAnalysisButton, "Start Analysis");
    }

    setButtonDisabled(startAnalysisButton, disabled);
  }

  function setRefreshButtonLoading(isLoading) {
    const iconNode = refreshAnalysisButton.querySelector(".app-inline-icon");
    if (iconNode) {
      iconNode.innerHTML = ANALYSIS_ACTION_ICONS.refresh;
    }
    setButtonLabel(refreshAnalysisButton, isLoading ? "Reloading..." : "Reload Status");
    setButtonDisabled(refreshAnalysisButton, isLoading);
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
    if (state.classChart && typeof state.classChart.destroy === "function") {
      state.classChart.destroy();
      state.classChart = null;
    }
    analysisTotalSummary.innerHTML = "";
    analysisMetricsGrid.innerHTML = "";
    if (analysisClassChartElement) {
      analysisClassChartElement.innerHTML = "";
    }
    if (analysisChartSummary) {
      analysisChartSummary.textContent = "No analysis selected";
    }
    state.masterClasses = [];
  }

  function renderMasterClassCards(masterClasses) {
    state.masterClasses = Array.isArray(masterClasses)
      ? masterClasses
        .slice()
        .sort((left, right) => Number(left.sort_order || 0) - Number(right.sort_order || 0))
      : [];

    if (!state.masterClasses.length) {
      resetMetrics();
      return;
    }

    analysisTotalSummary.innerHTML = `
      <div class="card analysis-total-card">
        <div class="card-body analysis-total-card-body">
          <div class="analysis-total-card-copy">
            <div class="analysis-total-card-kicker">Overall Total</div>
            <div class="analysis-total-card-title">Total detected vehicles</div>
            <div class="analysis-total-card-note">The accumulated vehicle count from the selected analysis result.</div>
          </div>
          <div class="analysis-total-card-metric">
            <div id="metric_total" class="analysis-total-card-value">0</div>
            <div class="analysis-total-card-pill">vehicles</div>
          </div>
        </div>
      </div>
    `;

    analysisMetricsGrid.innerHTML = state.masterClasses.map((item, index) => `
      <div class="col-xxl-2 col-xl-3 col-md-4 col-sm-6">
        <div class="card metric-card ${METRIC_CARD_THEMES[index % METRIC_CARD_THEMES.length]} h-100">
          <div class="card-body metric-card-body">
            <div class="d-flex align-items-center justify-content-between gap-3 mb-2">
              <div id="metric_title_${item.code}" class="metric-card-title mb-0">${app.escapeHtml(item.label || item.code)}</div>
              <span class="badge badge-light">${app.escapeHtml(String(item.code || ""))}</span>
            </div>
            <div id="metric_${item.code}" class="metric-value">0</div>
            <div id="metric_note_${item.code}" class="metric-card-note">${app.escapeHtml(item.description || "-")}</div>
            <div class="metric-card-bar" aria-hidden="true"><span></span></div>
          </div>
        </div>
      </div>
    `).join("");
  }

  function updateMetricValues(totals, totalVehicleCount) {
    state.masterClasses.forEach((item) => {
      const code = String(item.code || "");
      const metric = document.getElementById(`metric_${code}`);
      if (metric) {
        metric.textContent = String(totals[code] || 0);
      }
    });
    const totalMetric = document.getElementById("metric_total");
    if (totalMetric) {
      totalMetric.textContent = String(totalVehicleCount || 0);
    }
  }

  function chartSeriesEntries(totals) {
    return state.masterClasses.map((item, index) => ({
      code: String(item.code || ""),
      label: item.label || item.code,
      value: Number(totals[String(item.code || "")] || 0),
      color: CHART_BAR_COLORS[index % CHART_BAR_COLORS.length],
    }));
  }

  function renderClassDistributionChart(totals, totalVehicleCount) {
    if (!analysisClassChartElement) {
      return;
    }

    if (state.classChart && typeof state.classChart.destroy === "function") {
      state.classChart.destroy();
      state.classChart = null;
    }

    const entries = chartSeriesEntries(totals);
    const scopeLabel = state.availableLines.length > 1 && state.selectedLineOrder
      ? formatLineDisplayName(state.selectedLineOrder)
      : "All lines";
    if (analysisChartSummary) {
      analysisChartSummary.textContent = `${scopeLabel} • Total ${totalVehicleCount || 0} vehicles`;
    }

    if (!window.ApexCharts) {
      analysisClassChartElement.innerHTML = `
        <div class="text-muted py-10 text-center">Chart library is unavailable on this page.</div>
      `;
      return;
    }

    const labelColor = "#A1A5B7";
    const borderColor = "#EFF2F5";
    const baseColor = "#181C32";
    const seriesData = entries.map((entry) => ({
      x: entry.code,
      y: entry.value,
      fillColor: entry.color,
      metaLabel: entry.label,
    }));

    state.classChart = new window.ApexCharts(analysisClassChartElement, {
      chart: {
        type: "bar",
        height: 360,
        toolbar: { show: false },
        animations: {
          enabled: true,
          easing: "easeinout",
          speed: 420,
        },
        fontFamily: "inherit",
      },
      series: [
        {
          name: "Vehicles",
          data: seriesData,
        },
      ],
      plotOptions: {
        bar: {
          distributed: true,
          borderRadius: 7,
          columnWidth: "42%",
          dataLabels: {
            position: "top",
          },
        },
      },
      dataLabels: {
        enabled: true,
        offsetY: -18,
        style: {
          fontSize: "11px",
          fontWeight: "700",
          colors: [baseColor],
        },
        formatter(value) {
          return String(value);
        },
      },
      legend: { show: false },
      colors: entries.map((entry) => entry.color),
      grid: {
        borderColor,
        strokeDashArray: 4,
        yaxis: {
          lines: {
            show: true,
          },
        },
      },
      xaxis: {
        type: "category",
        categories: entries.map((entry) => entry.code),
        axisBorder: { show: false },
        axisTicks: { show: false },
        labels: {
          style: {
            colors: entries.map(() => labelColor),
            fontSize: "12px",
            fontWeight: 600,
          },
        },
        tooltip: { enabled: false },
      },
      yaxis: {
        min: 0,
        forceNiceScale: true,
        decimalsInFloat: 0,
        labels: {
          style: {
            colors: [labelColor],
            fontSize: "12px",
          },
          formatter(value) {
            return String(Math.round(value));
          },
        },
      },
      tooltip: {
        theme: "light",
        y: {
          formatter(value) {
            return `${Math.round(Number(value || 0))} vehicles`;
          },
        },
        x: {
          formatter(value, { dataPointIndex }) {
            const entry = entries[dataPointIndex];
            return entry ? `${entry.code} • ${entry.label}` : String(value);
          },
        },
      },
      states: {
        normal: { filter: { type: "none" } },
        hover: { filter: { type: "lighten", value: 0.06 } },
        active: { filter: { type: "darken", value: 0.08 } },
      },
    });

    state.classChart.render();
  }

  function formatDetectedType(event) {
    if (event && event.vehicle_type_label) {
      return event.vehicle_type_label;
    }
    if (event && event.detected_label) {
      return event.detected_label;
    }
    if (event && event.source_label) {
      return event.source_label;
    }
    const normalizedVehicleClass = String(event && event.vehicle_class ? event.vehicle_class : "").trim().toLowerCase();
    return normalizedVehicleClass || "-";
  }

  function formatCrossedTimeDisplay(seconds) {
    const value = Number(seconds || 0);
    if (!Number.isFinite(value)) {
      return "-";
    }
    if (value < 60) {
      return `${value.toFixed(2)} s`;
    }
    let minutes = Math.floor(value / 60);
    let remainingSeconds = Math.round((value - (minutes * 60)) * 100) / 100;
    if (remainingSeconds >= 60) {
      minutes += 1;
      remainingSeconds = 0;
    }
    const wholeSeconds = Math.floor(remainingSeconds);
    return `${minutes}.${String(wholeSeconds).padStart(2, "0")} min`;
  }

  function getSelectedVideo() {
    return state.videos.find((video) => video.id === state.selectedVideoId) || null;
  }

  function needsPlaybackConversion(video) {
    const storedFilename = String(video && video.stored_filename ? video.stored_filename : "").toLowerCase();
    return storedFilename ? !storedFilename.endsWith(".mp4") : false;
  }

  function displayPlaybackFilename(video) {
    const storedFilename = String(video && video.stored_filename ? video.stored_filename : "");
    if (!storedFilename) {
      return String(video && video.original_filename ? video.original_filename : "");
    }
    if (!needsPlaybackConversion(video)) {
      return storedFilename;
    }
    return storedFilename.replace(/\.[^.]+$/, ".mp4");
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
    selectedAnalysisVideoName.textContent = displayPlaybackFilename(video) || video.original_filename;
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
            <div class="app-user-primary">${app.escapeHtml(displayPlaybackFilename(video) || video.original_filename)}</div>
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

  function stopStatusClock() {
    if (state.statusClockHandle) {
      window.clearInterval(state.statusClockHandle);
      state.statusClockHandle = null;
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

  function formatClockDuration(totalSeconds) {
    const safeSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }

  function formatEstimate(totalSeconds) {
    const safeSeconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
    if (!safeSeconds) {
      return "Estimating...";
    }
    if (safeSeconds < 60) {
      return `${safeSeconds} sec`;
    }
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;
    if (hours > 0) {
      return `${hours} hr ${String(minutes).padStart(2, "0")} min`;
    }
    if (minutes > 0 && seconds === 0) {
      return `${minutes} min`;
    }
    return `${minutes} min ${String(seconds).padStart(2, "0")} sec`;
  }

  function calculateProcessingMetrics(payload) {
    const job = payload && payload.job ? payload.job : null;
    if (!job) {
      return {
        elapsedSeconds: 0,
        estimatedRemainingSeconds: null,
      };
    }

    const startedAtValue = job.started_at ? new Date(job.started_at).getTime() : null;
    const nowMs = Date.now();
    const elapsedSeconds = startedAtValue && !Number.isNaN(startedAtValue)
      ? Math.max(0, (nowMs - startedAtValue) / 1000)
      : 0;

    const performance = job.summary_json && job.summary_json.performance ? job.summary_json.performance : {};
    const processingFps = Number(performance.processing_fps || 0);
    const processedFrames = Number(job.processed_frames || 0);
    const totalFrames = Number(job.total_frames || 0);
    let estimatedRemainingSeconds = null;

    if (processingFps > 0 && totalFrames > 0 && processedFrames >= 0) {
      const remainingFrames = Math.max(totalFrames - processedFrames, 0);
      estimatedRemainingSeconds = remainingFrames / processingFps;
    } else {
      const progressPercent = Number(payload.progress_percent || 0);
      if (elapsedSeconds > 0 && progressPercent > 0 && progressPercent < 100) {
        const estimatedTotalSeconds = elapsedSeconds / (progressPercent / 100);
        estimatedRemainingSeconds = Math.max(estimatedTotalSeconds - elapsedSeconds, 0);
      }
    }

    return {
      elapsedSeconds,
      estimatedRemainingSeconds,
    };
  }

  function renderProcessingMeta() {
    const payload = state.lastAnalysisPayload;
    const job = payload && payload.job ? payload.job : null;
    const isRunning = job && ["queued", "processing"].includes(job.status) && !isStaleRunningJob(job);
    const isConverting = payload && payload.video && payload.video.status === "converting";

    if (isConverting) {
      analysisEstimatedTimeText.textContent = "Waiting for MP4 conversion";
      analysisProcessingTimeText.textContent = "00:00:00";
      return;
    }

    if (!isRunning) {
      analysisEstimatedTimeText.textContent = job && job.status === "completed" ? "Completed" : "-";
      if (job && job.started_at && job.finished_at) {
        const startedMs = new Date(job.started_at).getTime();
        const finishedMs = new Date(job.finished_at).getTime();
        const elapsedSeconds = (!Number.isNaN(startedMs) && !Number.isNaN(finishedMs))
          ? Math.max(0, (finishedMs - startedMs) / 1000)
          : 0;
        analysisProcessingTimeText.textContent = formatClockDuration(elapsedSeconds);
      } else {
        analysisProcessingTimeText.textContent = "00:00:00";
      }
      stopStatusClock();
      return;
    }

    const metrics = calculateProcessingMetrics(payload);
    analysisEstimatedTimeText.textContent = metrics.estimatedRemainingSeconds === null
      ? "Estimating..."
      : formatEstimate(metrics.estimatedRemainingSeconds);
    analysisProcessingTimeText.textContent = formatClockDuration(metrics.elapsedSeconds);
  }

  function ensureStatusClock() {
    stopStatusClock();
    const payload = state.lastAnalysisPayload;
    const job = payload && payload.job ? payload.job : null;
    if (job && ["queued", "processing"].includes(job.status) && !isStaleRunningJob(job)) {
      state.statusClockHandle = window.setInterval(renderProcessingMeta, 1000);
    }
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

  function getDisplayedVideoBox() {
    const rect = videoPlayer.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return null;
    }

    if (typeof overlayMath.getVideoContentBox !== "function") {
      return {
        left: 0,
        top: 0,
        width: rect.width,
        height: rect.height,
      };
    }

    return overlayMath.getVideoContentBox(rect.width, rect.height, videoPlayer.videoWidth, videoPlayer.videoHeight);
  }

  function overlaySourceStepSeconds() {
    const performance = state.overlayData && state.overlayData.analysis && state.overlayData.analysis.performance
      ? state.overlayData.analysis.performance
      : {};
    const effectiveAnalysisFps = Number(performance.effective_analysis_fps || 0);
    if (effectiveAnalysisFps > 0) {
      return 1 / effectiveAnalysisFps;
    }

    const effectiveFrameStride = Number(performance.effective_frame_stride || 0);
    const sourceFps = Number(state.overlayData && state.overlayData.source ? state.overlayData.source.fps : 0);
    if (effectiveFrameStride > 0 && sourceFps > 0) {
      return effectiveFrameStride / sourceFps;
    }

    return 0.16;
  }

  function overlayHoldWindowSeconds() {
    return Math.max(overlaySourceStepSeconds() * 2.4, 0.35);
  }

  function overlayInterpolationWindowSeconds() {
    return Math.max(overlaySourceStepSeconds() * 4.0, 0.6);
  }

  function overlayTrackKey(detection, index) {
    if (detection && detection.track_id !== null && detection.track_id !== undefined) {
      return `track:${detection.track_id}`;
    }
    return `anon:${index}`;
  }

  function lerpNumber(startValue, endValue, ratio) {
    return Number(startValue || 0) + ((Number(endValue || 0) - Number(startValue || 0)) * ratio);
  }

  function findOverlayFrameWindow(timeSeconds) {
    const frames = state.overlayData && state.overlayData.frames ? state.overlayData.frames : [];
    if (!frames.length) {
      return { previous: null, next: null };
    }

    let low = 0;
    let high = frames.length - 1;
    let insertionIndex = frames.length;

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const frameTime = Number(frames[mid].time_seconds || 0);
      if (frameTime >= timeSeconds) {
        insertionIndex = mid;
        high = mid - 1;
      } else {
        low = mid + 1;
      }
    }

    let previousIndex = insertionIndex - 1;
    if (insertionIndex < frames.length && Number(frames[insertionIndex].time_seconds || 0) <= timeSeconds) {
      previousIndex = insertionIndex;
    }
    while (previousIndex >= 0) {
      const detections = frames[previousIndex].detections || [];
      if (detections.length) {
        break;
      }
      previousIndex -= 1;
    }

    let nextIndex = insertionIndex;
    while (nextIndex < frames.length) {
      const detections = frames[nextIndex].detections || [];
      if (detections.length) {
        break;
      }
      nextIndex += 1;
    }

    return {
      previous: previousIndex >= 0 ? frames[previousIndex] : null,
      next: nextIndex < frames.length ? frames[nextIndex] : null,
    };
  }

  function interpolateDetections(previousFrame, nextFrame, timeSeconds) {
    const previousDetections = previousFrame && Array.isArray(previousFrame.detections) ? previousFrame.detections : [];
    const nextDetections = nextFrame && Array.isArray(nextFrame.detections) ? nextFrame.detections : [];
    if (!previousDetections.length && !nextDetections.length) {
      return [];
    }

    const previousTime = previousFrame ? Number(previousFrame.time_seconds || 0) : null;
    const nextTime = nextFrame ? Number(nextFrame.time_seconds || 0) : null;
    const maxGapSeconds = overlayInterpolationWindowSeconds();
    const holdWindowSeconds = overlayHoldWindowSeconds();
    const previousMap = new Map(previousDetections.map((detection, index) => [overlayTrackKey(detection, index), detection]));
    const nextMap = new Map(nextDetections.map((detection, index) => [overlayTrackKey(detection, index), detection]));
    const keys = new Set([...previousMap.keys(), ...nextMap.keys()]);
    const mergedDetections = [];

    keys.forEach((key) => {
      const previousDetection = previousMap.get(key);
      const nextDetection = nextMap.get(key);

      if (previousDetection && nextDetection && previousTime !== null && nextTime !== null) {
        const gapSeconds = nextTime - previousTime;
        if (gapSeconds > 0 && gapSeconds <= maxGapSeconds) {
          const ratio = Math.min(Math.max((timeSeconds - previousTime) / gapSeconds, 0), 1);
          const referenceDetection = ratio < 0.5 ? previousDetection : nextDetection;
          mergedDetections.push({
            ...referenceDetection,
            x1: lerpNumber(previousDetection.x1, nextDetection.x1, ratio),
            y1: lerpNumber(previousDetection.y1, nextDetection.y1, ratio),
            x2: lerpNumber(previousDetection.x2, nextDetection.x2, ratio),
            y2: lerpNumber(previousDetection.y2, nextDetection.y2, ratio),
            confidence: lerpNumber(previousDetection.confidence, nextDetection.confidence, ratio),
          });
          return;
        }
      }

      if (previousDetection && previousTime !== null && (timeSeconds - previousTime) <= holdWindowSeconds) {
        mergedDetections.push(previousDetection);
        return;
      }

      if (nextDetection && nextTime !== null && (nextTime - timeSeconds) <= (holdWindowSeconds * 0.75)) {
        mergedDetections.push(nextDetection);
      }
    });

    return mergedDetections;
  }

  function sampleOverlayDetections(timeSeconds) {
    const frameWindow = findOverlayFrameWindow(timeSeconds);
    if (!frameWindow.previous && !frameWindow.next) {
      return [];
    }
    return interpolateDetections(frameWindow.previous, frameWindow.next, timeSeconds);
  }

  function drawOverlayLines(contentBox) {
    const analysis = state.overlayData && state.overlayData.analysis ? state.overlayData.analysis : null;
    const lines = analysis && Array.isArray(analysis.lines) && analysis.lines.length
      ? analysis.lines
      : (analysis && analysis.line ? [analysis.line] : []);
    if (!lines.length || !contentBox) {
      return;
    }

    const colors = ["#FACC15", "#22D3EE"];
    lines.forEach((line, index) => {
      const startPoint = typeof overlayMath.mapNormalizedPointToDisplay === "function"
        ? overlayMath.mapNormalizedPointToDisplay({ x: line.start_x, y: line.start_y }, contentBox)
        : {
          x: contentBox.left + (Number(line.start_x || 0) * contentBox.width),
          y: contentBox.top + (Number(line.start_y || 0) * contentBox.height),
        };
      const endPoint = typeof overlayMath.mapNormalizedPointToDisplay === "function"
        ? overlayMath.mapNormalizedPointToDisplay({ x: line.end_x, y: line.end_y }, contentBox)
        : {
          x: contentBox.left + (Number(line.end_x || 0) * contentBox.width),
          y: contentBox.top + (Number(line.end_y || 0) * contentBox.height),
        };
      overlayContext.save();
      overlayContext.strokeStyle = colors[index % colors.length];
      overlayContext.lineWidth = 3;
      overlayContext.beginPath();
      overlayContext.moveTo(startPoint.x, startPoint.y);
      overlayContext.lineTo(endPoint.x, endPoint.y);
      overlayContext.stroke();
      overlayContext.restore();
    });
  }

  function drawOverlayBoxes(detections, contentBox) {
    if (!contentBox) {
      return;
    }
    detections.forEach((detection) => {
      const box = typeof overlayMath.mapNormalizedRectToDisplay === "function"
        ? overlayMath.mapNormalizedRectToDisplay(
          {
            x1: detection.x1,
            y1: detection.y1,
            x2: detection.x2,
            y2: detection.y2,
          },
          contentBox
        )
        : {
          x1: contentBox.left + (Number(detection.x1 || 0) * contentBox.width),
          y1: contentBox.top + (Number(detection.y1 || 0) * contentBox.height),
          x2: contentBox.left + (Number(detection.x2 || 0) * contentBox.width),
          y2: contentBox.top + (Number(detection.y2 || 0) * contentBox.height),
          width: Math.max((Number(detection.x2 || 0) - Number(detection.x1 || 0)) * contentBox.width, 1),
          height: Math.max((Number(detection.y2 || 0) - Number(detection.y1 || 0)) * contentBox.height, 1),
        };
      const x1 = box.x1;
      const y1 = box.y1;
      const width = box.width;
      const height = box.height;
      const label = `${detection.track_id ?? "-"} ${detection.detected_label || detection.source_label || detection.vehicle_class} ${(Number(detection.confidence || 0) * 100).toFixed(0)}%`;

      overlayContext.save();
      overlayContext.strokeStyle = "#00E676";
      overlayContext.lineWidth = 2;
      overlayContext.strokeRect(x1, y1, width, height);

      overlayContext.font = "600 13px Inter, sans-serif";
      const textWidth = overlayContext.measureText(label).width;
      const textX = Math.min(Math.max(x1, contentBox.left + 4), Math.max((contentBox.left + contentBox.width) - textWidth - 16, contentBox.left + 4));
      const textY = Math.max(y1 - 22, contentBox.top + 6);
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

    const contentBox = getDisplayedVideoBox();
    if (!contentBox) {
      overlayCanvas.classList.add("hidden");
      clearOverlayCanvas();
      return;
    }
    clearOverlayCanvas();
    drawOverlayLines(contentBox);
    drawOverlayBoxes(sampleOverlayDetections(videoPlayer.currentTime || 0), contentBox);
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
          <td colspan="7" class="text-center text-muted py-10">No vehicles have been recorded yet.</td>
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
            ${formatCrossedTimeDisplay(event.crossed_at_seconds)}
          </button>
        </td>
        <td>${event.track_id ?? "-"}</td>
        <td>${app.escapeHtml(formatDetectedType(event))}</td>
        <td>
          <div class="d-flex flex-column align-items-start gap-1">
            <span class="badge badge-light-primary">${app.escapeHtml(String(event.golongan_code || "-"))}</span>
            <span class="text-muted fs-8 lh-sm">${app.escapeHtml(event.golongan_label || "-")}</span>
          </div>
        </td>
        <td>${app.escapeHtml(event.direction)}</td>
        <td>${event.confidence ? `${(Number(event.confidence) * 100).toFixed(1)}%` : "-"}</td>
      </tr>
    `).join("");
  }

  function getCurrentVisibleEvents() {
    const events = state.lastAnalysisPayload && Array.isArray(state.lastAnalysisPayload.recent_events)
      ? state.lastAnalysisPayload.recent_events
      : [];
    return getVisibleEvents(events);
  }

  function safeExcelCell(value) {
    const text = String(value ?? "");
    return app.escapeHtml(text)
      .replace(/\n/g, "<br/>");
  }

  function buildExportFileName() {
    const video = getSelectedVideo();
    const baseName = String(
      (video && (displayPlaybackFilename(video) || video.original_filename)) || "detected_vehicles"
    )
      .replace(/\.[^.]+$/, "")
      .replace(/[^A-Za-z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 80) || "detected_vehicles";
    const lineSuffix = state.availableLines.length > 1 && state.selectedLineOrder
      ? `_line_${state.selectedLineOrder}`
      : "";
    const timestamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 19);
    return `${baseName}_detected_vehicles${lineSuffix}_${timestamp}.xls`;
  }

  function buildExcelHtml(events) {
    const video = getSelectedVideo();
    const lineLabel = state.availableLines.length > 1 && state.selectedLineOrder
      ? formatLineDisplayName(state.selectedLineOrder)
      : "All Lines";
    const exportedAt = new Date().toLocaleString("en-GB", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    const rows = events.map((event, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${safeExcelCell(formatCrossedTimeDisplay(event.crossed_at_seconds))}</td>
        <td>${safeExcelCell(event.track_id ?? "-")}</td>
        <td>${safeExcelCell(formatDetectedType(event))}</td>
        <td>${safeExcelCell(String(event.golongan_code || "-"))}</td>
        <td>${safeExcelCell(event.golongan_label || "-")}</td>
        <td>${safeExcelCell(event.direction || "-")}</td>
        <td>${safeExcelCell(event.confidence ? `${(Number(event.confidence) * 100).toFixed(1)}%` : "-")}</td>
      </tr>
    `).join("");

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { font-family: Arial, sans-serif; font-size: 12px; color: #1f2937; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #d1d5db; padding: 8px 10px; vertical-align: top; }
    th { background: #eef6ff; font-weight: 700; text-align: left; }
    .meta { margin-bottom: 16px; }
    .meta td { border: none; padding: 4px 0; }
    .title { font-size: 18px; font-weight: 700; padding-bottom: 8px; }
  </style>
</head>
<body>
  <table class="meta">
    <tr><td class="title" colspan="2">Detected Vehicles Export</td></tr>
    <tr><td><strong>Video</strong></td><td>${safeExcelCell((video && (displayPlaybackFilename(video) || video.original_filename)) || "-")}</td></tr>
    <tr><td><strong>Description</strong></td><td>${safeExcelCell((video && video.description) || "-")}</td></tr>
    <tr><td><strong>Line</strong></td><td>${safeExcelCell(lineLabel)}</td></tr>
    <tr><td><strong>Exported At</strong></td><td>${safeExcelCell(exportedAt)}</td></tr>
    <tr><td><strong>Total Rows</strong></td><td>${events.length}</td></tr>
  </table>

  <table>
    <thead>
      <tr>
        <th>No</th>
        <th>Time</th>
        <th>ID</th>
        <th>Detected Type</th>
        <th>Class Code</th>
        <th>Class Label</th>
        <th>Direction</th>
        <th>Confidence</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>
</body>
</html>`;
  }

  function exportVisibleEventsToExcel() {
    const events = getCurrentVisibleEvents();
    if (!state.selectedVideoId) {
      app.setAlert(alertBox, "danger", "Select a video first");
      return;
    }
    if (!events.length) {
      app.setAlert(alertBox, "danger", "There is no detected vehicle data to export");
      return;
    }

    const html = buildExcelHtml(events);
    const blob = new Blob(["\ufeff", html], {
      type: "application/vnd.ms-excel;charset=utf-8",
    });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = buildExportFileName();
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    app.setAlert(alertBox, "success", "Detected vehicle data exported to Excel");
  }

  function applyPendingSeek() {
    if (state.pendingSeekSeconds === null || Number.isNaN(Number(state.pendingSeekSeconds))) {
      return;
    }

    const duration = Number(videoPlayer.duration || 0);
    const targetSeconds = duration > 0
      ? Math.min(Math.max(Number(state.pendingSeekSeconds), 0), Math.max(duration - 0.05, 0))
      : Math.max(Number(state.pendingSeekSeconds), 0);

    state.pendingSeekSeconds = null;
    videoPlayer.currentTime = targetSeconds;
    videoPlayer.pause();
    drawCurrentOverlayFrame();
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
    if (videoShell) {
      videoShell.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }

    if (videoPlayer.readyState >= 1) {
      applyPendingSeek();
      return;
    }

    drawCurrentOverlayFrame();
  }

  async function renderAnalysis(payload) {
    state.lastAnalysisPayload = payload;
    const video = payload.video;
    const job = payload.job;
    const playbackUrl = video ? `/api/videos/${video.id}/playback` : null;
    const isConverting = video.status === "converting";

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

    updateMetricValues(totals, totalVehicleCount);
    renderClassDistributionChart(totals, totalVehicleCount);

    videoTitle.textContent = displayPlaybackFilename(video) || video.original_filename;
    videoDescription.textContent = video.description || "No description";
    openVideoButton.href = payload.video_url || "/videos";
    openVideoButton.target = "_blank";
    openVideoButton.rel = "noreferrer";
    setButtonLabel(openVideoButton, "Open Playback Video");

    const jobStatus = job ? job.status : "pending";
    const isStaleRunning = isStaleRunningJob(job);
    const displayJobStatus = isStaleRunning ? "stale" : jobStatus;
    statusText.innerHTML = `
      <span class="badge ${app.statusBadge(displayJobStatus)} status-pill me-2">${app.escapeHtml(displayJobStatus)}</span>
      <span class="soft-note">Video status: ${app.escapeHtml(video.status)}</span>
    `;
    setProgress(payload.progress_percent || 0);
    renderProcessingMeta();
    ensureStatusClock();

    if (job && job.error_message) {
      app.setAlert(alertBox, "danger", job.error_message);
    } else if (video.processing_error) {
      app.setAlert(alertBox, "danger", video.processing_error);
    }

    renderEvents(visibleEvents);

    const isRunning = jobStatus === "processing" || jobStatus === "queued";
    if (isConverting) {
      stopLivePreview();
      resetOverlayState();
      videoPlayer.removeAttribute("src");
      state.currentPlaybackUrl = null;
      videoPlayer.load();
      showPlaybackShell();
      openVideoButton.href = "/videos";
      openVideoButton.target = "";
      openVideoButton.rel = "";
      setButtonLabel(openVideoButton, "Manage Videos");
      setPreviewMode(
        "badge-light-info",
        "Converting",
        "The uploaded file is being converted to MP4 in the background. Playback and analysis will become available automatically when conversion finishes."
      );
    } else if (isRunning && !isStaleRunning) {
      stopLivePreview();
      await showPlayback({
        videoUrl: playbackUrl,
        overlayUrl: null,
        hint: jobStatus === "queued"
          ? "The analysis worker is preparing the model. You can still play the video now. Overlay markers will appear only after analysis completes."
          : "Analysis is running in the background. The video can still be played normally now. Overlay markers will appear only after analysis completes.",
        badgeText: jobStatus === "queued" ? "Preparing Analysis" : "Playback During Analysis",
      });
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

    if (isConverting) {
      setAnalysisActionButton({ mode: "converting", disabled: true });
    } else if (isRunning && !isStaleRunning) {
      setAnalysisActionButton({ mode: "stop", disabled: false });
    } else {
      setAnalysisActionButton({ mode: "start", disabled: !state.selectedVideoId });
    }
    setButtonDisabled(exportAnalysisExcelButton, !state.selectedVideoId || !visibleEvents.length);
    setButtonDisabled(clearAnalysisLogsButton, !state.selectedVideoId || isConverting || (isRunning && !isStaleRunning));
    setRefreshButtonLoading(false);

    stopPolling();
    if (isRunning || isConverting) {
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
      setAnalysisActionButton({ mode: "start", disabled: false });
      setRefreshButtonLoading(false);
      analysisEstimatedTimeText.textContent = "-";
      analysisProcessingTimeText.textContent = "00:00:00";
      setCountLinesButton.href = "/count-lines";
      setButtonDisabled(clearAnalysisLogsButton, true);
      setButtonDisabled(exportAnalysisExcelButton, true);
      stopStatusClock();
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
    try {
      app.setAlert(alertBox, "danger", "");
      setRefreshButtonLoading(true);
      await loadVideos();
      await loadAnalysis();
      app.setAlert(alertBox, "success", "Analysis status reloaded");
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    } finally {
      setRefreshButtonLoading(false);
    }
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

  exportAnalysisExcelButton.addEventListener("click", () => {
    exportVisibleEventsToExcel();
  });

  startAnalysisButton.addEventListener("click", async () => {
    if (!state.selectedVideoId) {
      app.setAlert(alertBox, "danger", "Select a video first");
      return;
    }

    const currentJob = state.lastAnalysisPayload ? state.lastAnalysisPayload.job : null;
    const isRunning = currentJob && ["queued", "processing"].includes(currentJob.status) && !isStaleRunningJob(currentJob);

    try {
      app.setAlert(alertBox, "danger", "");
      if (isRunning) {
        if (!window.confirm("Are you sure you want to stop the current analysis?")) {
          return;
        }
        setAnalysisActionButton({ mode: "stopping", disabled: true });
        await app.apiFetch(`/api/videos/${state.selectedVideoId}/analysis/stop`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        app.setAlert(alertBox, "success", "Stop request sent. Waiting for the worker to halt.");
      } else {
        setAnalysisActionButton({ mode: "start", disabled: true });
        await app.apiFetch(`/api/videos/${state.selectedVideoId}/analysis/start`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        state.hasLiveFrame = false;
        resetOverlayState();
      }
      await loadAnalysis();
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
      setAnalysisActionButton({ mode: isRunning ? "stop" : "start", disabled: false });
    }
  });

  window.addEventListener("beforeunload", () => {
    stopPolling();
    stopStatusClock();
    stopLivePreview();
    resetOverlayState();
  });
});
