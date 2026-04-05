document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const alertBox = document.getElementById("countLinesAlert");
  const videoPlayer = document.getElementById("countLinesVideoPlayer");
  const canvas = document.getElementById("countLinesCanvas");
  const context = canvas.getContext("2d");
  const stage = document.getElementById("countLinesStage");
  const countLinesVideoName = document.getElementById("countLinesVideoName");
  const countLinesVideoMeta = document.getElementById("countLinesVideoMeta");
  const countLinesVideoBadges = document.getElementById("countLinesVideoBadges");
  const countLinesModeText = document.getElementById("countLinesModeText");
  const countLinesSourceText = document.getElementById("countLinesSourceText");
  const tableBody = document.getElementById("countLinesTableBody");
  const lineOrderOneButton = document.getElementById("lineOrderOneButton");
  const lineOrderTwoButton = document.getElementById("lineOrderTwoButton");
  const clearSelectedLineButton = document.getElementById("clearSelectedLineButton");
  const clearAllLinesButton = document.getElementById("clearAllLinesButton");
  const saveCountLinesButton = document.getElementById("saveCountLinesButton");
  const goToAnalysisButton = document.getElementById("goToAnalysisButton");
  const openVideoPickerButton = document.getElementById("openCountLinesVideoPickerButton");
  const videoSearchInput = document.getElementById("countLinesVideoSearch");
  const videoStatusFilter = document.getElementById("countLinesVideoStatusFilter");
  const videoPickerBody = document.getElementById("countLinesVideoPickerBody");
  const pickerModalElement = document.getElementById("countLinesVideoPickerModal");
  const pickerModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(pickerModalElement) : null;

  const state = {
    videos: [],
    selectedVideoId: null,
    videoSearchQuery: "",
    videoStatusFilter: "all",
    activeLineOrder: 1,
    pendingStart: null,
    currentLineSource: "empty",
    lines: {},
    currentVideoUrl: null,
  };

  const LINE_COLORS = {
    1: {
      stroke: "#FACC15",
      fill: "rgba(250, 204, 21, 0.18)",
      buttonClass: "btn-warning",
      badgeClass: "badge-light-warning",
    },
    2: {
      stroke: "#22D3EE",
      fill: "rgba(34, 211, 238, 0.18)",
      buttonClass: "btn-info",
      badgeClass: "badge-light-info",
    },
  };

  const PICKER_ICON = `
    <span class="app-inline-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="m5 12 4.2 4L19 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </span>
  `;

  function getSelectedVideo() {
    return state.videos.find((video) => video.id === state.selectedVideoId) || null;
  }

  function thumbnailUrl(video) {
    const stem = String(video && video.stored_filename ? video.stored_filename : "").replace(/\.[^.]+$/, "");
    return stem ? `/storage/thumbnails/${encodeURIComponent(stem)}.jpg` : "";
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
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(searchQuery);
    });
  }

  function renderVideoPickerList() {
    const videos = filteredVideos();
    if (!videos.length) {
      videoPickerBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted py-10">No videos match the current search.</td>
        </tr>
      `;
      return;
    }

    videoPickerBody.innerHTML = videos.map((video, index) => {
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
              ${PICKER_ICON}
              <span>${isSelected ? "Selected" : "Select"}</span>
            </button>
          </td>
        </tr>
      `;
    }).join("");

    bindThumbnailFallbacks(videoPickerBody);
  }

  function renderSelectedVideoSummary() {
    const video = getSelectedVideo();
    if (!video) {
      countLinesVideoName.textContent = "No video selected";
      countLinesVideoMeta.textContent = "Select a video and draw up to two counting lines.";
      countLinesVideoBadges.innerHTML = "";
      openVideoPickerButton.textContent = "Select Video";
      goToAnalysisButton.href = "/analysis";
      return;
    }

    const analysisStatus = video.analysis_job ? video.analysis_job.status : "pending";
    const sourceLabel = {
      video: "Video-specific lines",
      site: "Using the default site line",
      empty: "No active lines",
    }[state.currentLineSource] || "No active lines";
    countLinesVideoName.textContent = video.stored_filename || video.original_filename;
    countLinesVideoMeta.textContent = `${app.formatDuration(video.duration_seconds)} • ${app.formatDateTime(video.created_at)} • ${video.uploaded_by || "-"}`;
    countLinesVideoBadges.innerHTML = `
      <span class="badge ${app.statusBadge(video.status)} status-pill">${app.escapeHtml(video.status)}</span>
      <span class="badge ${app.statusBadge(analysisStatus)} status-pill">${app.escapeHtml(analysisStatus)}</span>
      <span class="badge badge-light-dark">${app.escapeHtml(sourceLabel)}</span>
    `;
    openVideoPickerButton.textContent = "Change Video";
    goToAnalysisButton.href = `/analysis?video_id=${video.id}`;
  }

  function setActiveLineOrder(lineOrder) {
    state.activeLineOrder = lineOrder;
    state.pendingStart = null;
    lineOrderOneButton.className = `btn btn-sm ${lineOrder === 1 ? "btn-warning" : "btn-light-warning"}`;
    lineOrderTwoButton.className = `btn btn-sm ${lineOrder === 2 ? "btn-info" : "btn-light-info"}`;
    const label = lineOrder === 1 ? "Line 1" : "Line 2";
    countLinesModeText.textContent = `Active mode: ${label}. Click two points on the video to create or replace this line.`;
    renderCanvas();
  }

  function renderLinesTable() {
    const rows = [1, 2].map((lineOrder) => state.lines[lineOrder] || null);
    if (!rows.some(Boolean)) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center text-muted py-10">No lines have been drawn yet.</td>
        </tr>
      `;
      return;
    }

    tableBody.innerHTML = rows.map((line, index) => {
      const lineOrder = index + 1;
      if (!line) {
        return `
          <tr>
            <td>Line ${lineOrder}</td>
            <td><span class="badge badge-light">Empty</span></td>
            <td>-</td>
            <td>-</td>
          </tr>
        `;
      }

      return `
        <tr>
          <td>Line ${lineOrder}</td>
          <td><span class="badge ${LINE_COLORS[lineOrder].badgeClass}">Active</span></td>
          <td>${line.start_x.toFixed(3)}, ${line.start_y.toFixed(3)}</td>
          <td>${line.end_x.toFixed(3)}, ${line.end_y.toFixed(3)}</td>
        </tr>
      `;
    }).join("");
  }

  function renderSourceText() {
    const textMap = {
      video: "This video already has its own count lines. Click Save Lines to update the configuration.",
      site: "The preview currently uses the default site line. If you save now, the line setup will become video-specific.",
      empty: "No default line is available yet. Draw a new line and save it to start analysis with dynamic count lines.",
    };
    countLinesSourceText.textContent = textMap[state.currentLineSource] || textMap.empty;
  }

  function syncCanvasSize() {
    const rect = videoPlayer.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return false;
    }

    const devicePixelRatio = window.devicePixelRatio || 1;
    const targetWidth = Math.max(1, Math.round(rect.width * devicePixelRatio));
    const targetHeight = Math.max(1, Math.round(rect.height * devicePixelRatio));

    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    }

    return true;
  }

  function getVideoContentBox() {
    const rect = videoPlayer.getBoundingClientRect();
    if (!rect.width || !rect.height || !videoPlayer.videoWidth || !videoPlayer.videoHeight) {
      return null;
    }

    const videoAspect = videoPlayer.videoWidth / videoPlayer.videoHeight;
    const rectAspect = rect.width / rect.height;

    if (rectAspect > videoAspect) {
      const height = rect.height;
      const width = height * videoAspect;
      return {
        left: (rect.width - width) / 2,
        top: 0,
        width,
        height,
      };
    }

    const width = rect.width;
    const height = width / videoAspect;
    return {
      left: 0,
      top: (rect.height - height) / 2,
      width,
      height,
    };
  }

  function toCanvasPoint(point) {
    const box = getVideoContentBox();
    if (!box) {
      return null;
    }
    return {
      x: box.left + (point.x * box.width),
      y: box.top + (point.y * box.height),
    };
  }

  function toNormalizedPoint(event) {
    const box = getVideoContentBox();
    if (!box) {
      return null;
    }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    if (x < box.left || x > box.left + box.width || y < box.top || y > box.top + box.height) {
      return null;
    }

    return {
      x: (x - box.left) / box.width,
      y: (y - box.top) / box.height,
    };
  }

  function drawHandle(point, color) {
    context.save();
    context.fillStyle = color;
    context.beginPath();
    context.arc(point.x, point.y, 5, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }

  function renderCanvas() {
    if (!syncCanvasSize()) {
      return;
    }

    context.clearRect(0, 0, canvas.width, canvas.height);
    const box = getVideoContentBox();
    if (!box) {
      return;
    }

    [1, 2].forEach((lineOrder) => {
      const line = state.lines[lineOrder];
      if (!line) {
        return;
      }
      const start = toCanvasPoint({ x: line.start_x, y: line.start_y });
      const end = toCanvasPoint({ x: line.end_x, y: line.end_y });
      if (!start || !end) {
        return;
      }

      context.save();
      context.strokeStyle = LINE_COLORS[lineOrder].stroke;
      context.lineWidth = state.activeLineOrder === lineOrder ? 3 : 2;
      context.beginPath();
      context.moveTo(start.x, start.y);
      context.lineTo(end.x, end.y);
      context.stroke();

      const labelX = (start.x + end.x) / 2;
      const labelY = (start.y + end.y) / 2;
      const label = `Line ${lineOrder}`;
      context.font = "600 13px sans-serif";
      const textWidth = context.measureText(label).width;
      context.fillStyle = "rgba(15, 23, 42, 0.86)";
      context.fillRect(labelX - (textWidth / 2) - 8, labelY - 24, textWidth + 16, 20);
      context.fillStyle = "#ffffff";
      context.fillText(label, labelX - (textWidth / 2), labelY - 10);
      context.restore();

      drawHandle(start, LINE_COLORS[lineOrder].stroke);
      drawHandle(end, LINE_COLORS[lineOrder].stroke);
    });

    if (state.pendingStart) {
      const pending = toCanvasPoint(state.pendingStart);
      if (pending) {
        drawHandle(pending, LINE_COLORS[state.activeLineOrder].stroke);
      }
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

  async function loadCountLines() {
    const video = getSelectedVideo();
    if (!video) {
      state.lines = {};
      state.currentLineSource = "empty";
      renderSelectedVideoSummary();
      renderLinesTable();
      renderSourceText();
      renderCanvas();
      return;
    }

    const response = await app.apiFetch(`/api/videos/${video.id}/count-lines`);
    state.currentLineSource = response.source || "empty";
    state.lines = {};
    (response.lines || []).forEach((line) => {
      state.lines[line.line_order] = {
        line_order: line.line_order,
        name: line.name,
        start_x: Number(line.start_x),
        start_y: Number(line.start_y),
        end_x: Number(line.end_x),
        end_y: Number(line.end_y),
        is_active: Boolean(line.is_active),
      };
    });
    state.pendingStart = null;
    renderSelectedVideoSummary();
    renderLinesTable();
    renderSourceText();
    renderCanvas();
  }

  async function loadSelectedVideo() {
    const video = getSelectedVideo();
    renderSelectedVideoSummary();
    renderVideoPickerList();
    if (!video) {
      videoPlayer.removeAttribute("src");
      state.currentVideoUrl = null;
      videoPlayer.load();
      stage.style.aspectRatio = "";
      await loadCountLines();
      return;
    }

    const videoUrl = `/api/videos/${video.id}/playback`;
    if (state.currentVideoUrl !== videoUrl) {
      videoPlayer.src = videoUrl;
      state.currentVideoUrl = videoUrl;
      videoPlayer.load();
    }
    await loadCountLines();
    const url = new URL(window.location.href);
    url.searchParams.set("video_id", video.id);
    window.history.replaceState({}, "", url);
  }

  async function selectVideoById(videoId, { closeModal = true } = {}) {
    if (!videoId || videoId === state.selectedVideoId) {
      if (closeModal && pickerModal) {
        pickerModal.hide();
      }
      return;
    }
    state.selectedVideoId = videoId;
    await loadSelectedVideo();
    if (closeModal && pickerModal) {
      pickerModal.hide();
    }
  }

  async function saveLines() {
    const video = getSelectedVideo();
    if (!video) {
      app.setAlert(alertBox, "danger", "Select a video first");
      return;
    }
    if (state.pendingStart) {
      app.setAlert(alertBox, "danger", "Finish the active line by setting its end point before saving");
      return;
    }

    const payload = {
      lines: Object.values(state.lines)
        .filter(Boolean)
        .sort((left, right) => left.line_order - right.line_order)
        .map((line) => ({
          line_order: line.line_order,
          name: line.name || `Line ${line.line_order}`,
          start_x: line.start_x,
          start_y: line.start_y,
          end_x: line.end_x,
          end_y: line.end_y,
          is_active: true,
        })),
    };

    const response = await app.apiFetch(`/api/videos/${video.id}/count-lines`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.currentLineSource = response.source || "video";
    app.setAlert(alertBox, "success", "Count lines saved successfully");
    await loadCountLines();
  }

  videoPlayer.addEventListener("loadedmetadata", () => {
    if (videoPlayer.videoWidth && videoPlayer.videoHeight) {
      stage.style.aspectRatio = `${videoPlayer.videoWidth} / ${videoPlayer.videoHeight}`;
    }
    renderCanvas();
  });

  videoPlayer.addEventListener("seeked", renderCanvas);
  videoPlayer.addEventListener("timeupdate", renderCanvas);
  videoPlayer.addEventListener("pause", renderCanvas);
  videoPlayer.addEventListener("play", renderCanvas);
  window.addEventListener("resize", renderCanvas);

  canvas.addEventListener("click", (event) => {
    if (!state.selectedVideoId) {
      return;
    }
    const point = toNormalizedPoint(event);
    if (!point) {
      return;
    }

    if (!state.pendingStart) {
      state.pendingStart = point;
      renderCanvas();
      return;
    }

    state.lines[state.activeLineOrder] = {
      line_order: state.activeLineOrder,
      name: `Line ${state.activeLineOrder}`,
      start_x: state.pendingStart.x,
      start_y: state.pendingStart.y,
      end_x: point.x,
      end_y: point.y,
      is_active: true,
    };
    state.pendingStart = null;
    renderLinesTable();
    renderCanvas();
  });

  openVideoPickerButton.addEventListener("click", () => {
    app.setAlert(alertBox, "danger", "");
    state.videoSearchQuery = "";
    state.videoStatusFilter = "all";
    videoSearchInput.value = "";
    videoStatusFilter.value = "all";
    renderVideoPickerList();
    if (pickerModal) {
      pickerModal.show();
    }
  });

  videoSearchInput.addEventListener("input", () => {
    state.videoSearchQuery = videoSearchInput.value || "";
    renderVideoPickerList();
  });

  videoStatusFilter.addEventListener("change", () => {
    state.videoStatusFilter = videoStatusFilter.value || "all";
    renderVideoPickerList();
  });

  videoPickerBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-picker-action='select']");
    if (!button) {
      return;
    }
    try {
      await selectVideoById(button.dataset.id, { closeModal: true });
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });

  lineOrderOneButton.addEventListener("click", () => setActiveLineOrder(1));
  lineOrderTwoButton.addEventListener("click", () => setActiveLineOrder(2));

  clearSelectedLineButton.addEventListener("click", () => {
    delete state.lines[state.activeLineOrder];
    state.pendingStart = null;
    renderLinesTable();
    renderCanvas();
  });

  clearAllLinesButton.addEventListener("click", () => {
    state.lines = {};
    state.pendingStart = null;
    renderLinesTable();
    renderCanvas();
  });

  saveCountLinesButton.addEventListener("click", async () => {
    try {
      app.setAlert(alertBox, "danger", "");
      await saveLines();
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });

  try {
    await app.requireSession();
    setActiveLineOrder(1);
    await loadVideos();
    await loadSelectedVideo();
  } catch (error) {
    app.setAlert(alertBox, "danger", error.message);
  }
});
