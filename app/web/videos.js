document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const videosAlert = document.getElementById("videosAlert");
  const videosTableBody = document.getElementById("videosTableBody");
  const openUploadModalButton = document.getElementById("openUploadModal");
  const uploadForm = document.getElementById("uploadForm");
  const uploadRecordedDateInput = document.getElementById("uploadRecordedDate");
  const uploadRecordedTimeInput = document.getElementById("uploadRecordedTime");
  const uploadSubmitButton = document.getElementById("uploadSubmitButton");

  const uploadVideoModalElement = document.getElementById("uploadVideoModal");
  const previewVideoModalElement = document.getElementById("previewVideoModal");
  const uploadLoadingModalElement = document.getElementById("uploadLoadingModal");
  const uploadSuccessModalElement = document.getElementById("uploadSuccessModal");
  const previewVideoTitle = document.getElementById("previewVideoTitle");
  const previewVideoPlayer = document.getElementById("previewVideoPlayer");
  const previewVideoLoading = document.getElementById("previewVideoLoading");
  const previewVideoError = document.getElementById("previewVideoError");
  const uploadSuccessMessage = document.getElementById("uploadSuccessMessage");

  const uploadVideoModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(uploadVideoModalElement) : null;
  const previewVideoModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(previewVideoModalElement) : null;
  const uploadLoadingModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(uploadLoadingModalElement) : null;
  const uploadSuccessModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(uploadSuccessModalElement) : null;

  const state = {
    videos: [],
    pollHandle: null,
  };

  const ICONS = {
    actions: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="5" r="1.7" fill="currentColor"/>
          <circle cx="12" cy="12" r="1.7" fill="currentColor"/>
          <circle cx="12" cy="19" r="1.7" fill="currentColor"/>
        </svg>
      </span>
    `,
    line: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M4 17h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          <path d="M7 8h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          <circle cx="7" cy="8" r="1.6" fill="currentColor"/>
          <circle cx="17" cy="8" r="1.6" fill="currentColor"/>
          <circle cx="4" cy="17" r="1.6" fill="currentColor"/>
          <circle cx="20" cy="17" r="1.6" fill="currentColor"/>
        </svg>
      </span>
    `,
    analysis: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M5 19V9M12 19V5M19 19v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </span>
    `,
    preview: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="m9 7 8 5-8 5V7Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
          <path d="M4 12c2-4 5-6 8-6s6 2 8 6c-2 4-5 6-8 6s-6-2-8-6Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
        </svg>
      </span>
    `,
    delete: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M5 7h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          <path d="M9 7V5h6v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M8 7l1 12h6l1-12" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
        </svg>
      </span>
    `,
  };

  function getRecordedAtValue(dateInput, timeInput) {
    const dateValue = dateInput ? dateInput.value : "";
    const timeValue = timeInput ? timeInput.value : "";
    if (!dateValue) {
      return "";
    }
    return `${dateValue}T${timeValue || "00:00"}`;
  }

  function resetUploadForm() {
    uploadForm.reset();
    if (uploadRecordedDateInput) {
      uploadRecordedDateInput.value = "";
    }
    if (uploadRecordedTimeInput) {
      uploadRecordedTimeInput.value = "";
    }
  }

  function stopPolling() {
    if (state.pollHandle) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  }

  function shouldPollVideos() {
    return state.videos.some((video) => {
      const analysisStatus = video.analysis_job ? video.analysis_job.status : "pending";
      return ["converting", "processing"].includes(video.status) || ["queued", "processing"].includes(analysisStatus);
    });
  }

  function ensurePolling() {
    stopPolling();
    if (!shouldPollVideos()) {
      return;
    }
    state.pollHandle = window.setInterval(async () => {
      try {
        await loadVideos();
      } catch (error) {
        console.error("video polling failed", error);
      }
    }, 2000);
  }

  function setUploadSubmitting(isSubmitting) {
    if (!uploadSubmitButton) {
      return;
    }
    uploadSubmitButton.disabled = isSubmitting;
    const label = uploadSubmitButton.querySelector(".indicator-label");
    if (label) {
      label.textContent = isSubmitting ? "Uploading..." : "Upload Video";
    }
  }

  function showUploadLoading() {
    setUploadSubmitting(true);
    if (uploadLoadingModal) {
      uploadLoadingModal.show();
    }
  }

  function hideUploadLoading() {
    setUploadSubmitting(false);
    if (uploadLoadingModal) {
      uploadLoadingModal.hide();
    }
  }

  function thumbnailUrl(video) {
    const stem = String(video.stored_filename || "")
      .replace(/\.[^.]+$/, "");
    return stem ? `/storage/thumbnails/${encodeURIComponent(stem)}.jpg` : "";
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

  function actionMenuButton({ action, id, label, toneClass, title }) {
    return `
      <button
        class="dropdown-item app-dropdown-action ${toneClass}"
        type="button"
        data-action="${action}"
        data-id="${id}"
        title="${app.escapeHtml(title)}"
      >
        ${ICONS[action]}
        <span>${label}</span>
      </button>
    `;
  }

  function actionMenuButtonDisabled({ action, label, toneClass, title }) {
    return `
      <button
        class="dropdown-item app-dropdown-action ${toneClass}"
        type="button"
        disabled
        title="${app.escapeHtml(title)}"
      >
        ${ICONS[action]}
        <span>${label}</span>
      </button>
    `;
  }

  function actionMenuLink({ href, icon, label, toneClass, title }) {
    return `
      <a
        class="dropdown-item app-dropdown-action ${toneClass}"
        href="${href}"
        title="${app.escapeHtml(title)}"
      >
        ${icon}
        <span>${label}</span>
      </a>
    `;
  }

  function renderActionCell(video) {
    const isConverting = video.status === "converting";
    const analyzeButton = isConverting
      ? `
        <button
          class="btn btn-sm btn-light-success app-primary-row-action"
          type="button"
          disabled
          title="${app.escapeHtml(`Analyze will be available after MP4 conversion finishes for ${video.original_filename}`)}"
        >
          ${ICONS.analysis}
          <span>Analyze</span>
        </button>
      `
      : `
        <a
          class="btn btn-sm btn-light-success app-primary-row-action"
          href="/analysis?video_id=${video.id}"
          title="${app.escapeHtml(`Analyze ${video.original_filename}`)}"
        >
          ${ICONS.analysis}
          <span>Analyze</span>
        </a>
      `;

    return `
      <div class="app-row-actions">
        ${analyzeButton}
        <div class="dropdown app-actions-dropdown">
          <button
            class="btn btn-sm btn-light-primary app-actions-toggle"
            type="button"
            data-bs-toggle="dropdown"
            data-bs-auto-close="true"
            title="More actions"
            aria-label="More actions"
            aria-expanded="false"
          >
            ${ICONS.actions}
          </button>
          <div class="dropdown-menu dropdown-menu-end app-actions-menu">
            ${actionMenuLink({
              href: `/count-lines?video_id=${video.id}`,
              icon: ICONS.line,
              label: "Lines",
              toneClass: "app-dropdown-action-warning",
              title: `Set count lines for ${video.original_filename}`,
            })}
            ${isConverting ? actionMenuButtonDisabled({
              action: "preview",
              label: "Preview",
              toneClass: "app-dropdown-action-primary",
              title: `Preview will be available after MP4 conversion finishes for ${video.original_filename}`,
            }) : actionMenuButton({
              action: "preview",
              id: video.id,
              label: "Preview",
              toneClass: "app-dropdown-action-primary",
              title: `Preview ${video.original_filename}`,
            })}
            ${actionMenuButton({
              action: "delete",
              id: video.id,
              label: "Delete",
              toneClass: "app-dropdown-action-danger",
              title: `Delete ${video.original_filename}`,
            })}
          </div>
        </div>
      </div>
    `;
  }

  function renderThumbnailCell(video) {
    const src = thumbnailUrl(video);
    if (!src) {
      return `
        <div class="app-video-thumb is-fallback">
          <div class="app-video-thumb-fallback">No Preview</div>
        </div>
      `;
    }

    return `
      <div class="app-video-thumb" data-thumb-shell>
        <img
          src="${app.escapeHtml(src)}"
          alt="Thumbnail ${app.escapeHtml(video.original_filename)}"
          loading="lazy"
          data-thumb
        />
        <div class="app-video-thumb-fallback">No Preview</div>
      </div>
    `;
  }

  function renderFileNameCell(video) {
    const originalName = app.escapeHtml(video.original_filename || "-");
    const storedName = app.escapeHtml(displayPlaybackFilename(video) || "-");
    const metaLine = video.original_filename && video.original_filename !== video.stored_filename
      ? `Original: ${originalName}`
      : `${video.frame_width || "-"} x ${video.frame_height || "-"} px`;

    return `
      <div class="app-user-primary">${storedName}</div>
      <div class="app-user-secondary">${metaLine}</div>
    `;
  }

  function bindThumbnailFallbacks() {
    videosTableBody.querySelectorAll("img[data-thumb]").forEach((image) => {
      image.addEventListener("error", () => {
        const shell = image.closest("[data-thumb-shell]");
        if (shell) {
          shell.classList.add("is-fallback");
        }
      }, { once: true });
    });
  }

  function renderVideos() {
    if (!state.videos.length) {
      videosTableBody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center text-muted py-10">No videos have been uploaded yet.</td>
        </tr>
      `;
      return;
    }

    videosTableBody.innerHTML = state.videos.map((video, index) => {
      const analysisStatus = video.analysis_job ? video.analysis_job.status : "pending";
      return `
        <tr>
          <td class="text-gray-700 fw-semibold">${index + 1}</td>
          <td>${renderThumbnailCell(video)}</td>
          <td>${renderFileNameCell(video)}</td>
          <td class="wrap-cell">${app.escapeHtml(video.description || "-")}</td>
          <td>
            <div><span class="badge ${app.statusBadge(video.status)} status-pill">${app.escapeHtml(video.status)}</span></div>
            <div class="mt-2"><span class="badge ${app.statusBadge(analysisStatus)} status-pill">${app.escapeHtml(analysisStatus)}</span></div>
          </td>
          <td>${app.formatDuration(video.duration_seconds)}</td>
          <td>${app.escapeHtml(video.uploaded_by || "-")}</td>
          <td>${app.formatDateTime(video.created_at)}</td>
          <td class="text-end">
            ${renderActionCell(video)}
          </td>
        </tr>
      `;
    }).join("");

    bindThumbnailFallbacks();
  }

  async function loadVideos() {
    state.videos = await app.apiFetch("/api/videos");
    renderVideos();
    ensurePolling();
  }

  function openPreviewModal(video) {
    previewVideoTitle.textContent = displayPlaybackFilename(video) || video.original_filename || "Video Preview";
    if (previewVideoLoading) {
      previewVideoLoading.classList.remove("hidden");
    }
    if (previewVideoError) {
      previewVideoError.classList.add("hidden");
    }
    previewVideoPlayer.src = `/api/videos/${video.id}/playback`;
    previewVideoPlayer.load();
    if (previewVideoModal) {
      previewVideoModal.show();
    }
  }

  try {
    await app.requireSession();
    await loadVideos();
    resetUploadForm();
  } catch (error) {
    app.setAlert(videosAlert, "danger", error.message);
    return;
  }

  uploadVideoModalElement.addEventListener("hidden.bs.modal", () => {
    resetUploadForm();
  });

  previewVideoModalElement.addEventListener("hidden.bs.modal", () => {
    previewVideoPlayer.pause();
    previewVideoPlayer.removeAttribute("src");
    previewVideoPlayer.load();
    if (previewVideoLoading) {
      previewVideoLoading.classList.add("hidden");
    }
    if (previewVideoError) {
      previewVideoError.classList.add("hidden");
    }
  });

  previewVideoPlayer.addEventListener("loadstart", () => {
    if (previewVideoLoading) {
      previewVideoLoading.classList.remove("hidden");
    }
    if (previewVideoError) {
      previewVideoError.classList.add("hidden");
    }
  });

  const hidePreviewLoading = () => {
    if (previewVideoLoading) {
      previewVideoLoading.classList.add("hidden");
    }
  };

  previewVideoPlayer.addEventListener("loadeddata", hidePreviewLoading);
  previewVideoPlayer.addEventListener("canplay", hidePreviewLoading);
  previewVideoPlayer.addEventListener("playing", hidePreviewLoading);

  previewVideoPlayer.addEventListener("error", () => {
    hidePreviewLoading();
    if (previewVideoError) {
      previewVideoError.classList.remove("hidden");
    }
  });

  openUploadModalButton.addEventListener("click", () => {
    app.setAlert(videosAlert, "danger", "");
    resetUploadForm();
    if (uploadVideoModal) {
      uploadVideoModal.show();
    }
  });

  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(videosAlert, "danger", "");

    const formData = new FormData(uploadForm);
    const file = formData.get("file");
    const recordedAtValue = getRecordedAtValue(uploadRecordedDateInput, uploadRecordedTimeInput);
    if (!(file instanceof File) || !file.name) {
      app.setAlert(videosAlert, "danger", "A video file is required");
      return;
    }

    if (recordedAtValue) {
      formData.set("recorded_at", new Date(recordedAtValue).toISOString());
    } else {
      formData.delete("recorded_at");
    }
    formData.delete("recorded_at_date");
    formData.delete("recorded_at_time");

    if (!formData.get("auto_process")) {
      formData.delete("auto_process");
    }

    try {
      showUploadLoading();
      const createdVideo = await app.apiFetch("/api/videos", {
        method: "POST",
        body: formData,
      });
      if (uploadVideoModal) {
        uploadVideoModal.hide();
      }
      await loadVideos();
      hideUploadLoading();
      if (uploadSuccessMessage) {
        if (createdVideo && createdVideo.status === "converting") {
          uploadSuccessMessage.textContent = formData.get("auto_process")
            ? `Video ${file.name} was uploaded. MP4 conversion is now running, and analysis will start automatically when the MP4 file is ready.`
            : `Video ${file.name} was uploaded. MP4 conversion is now running in the background.`;
        } else {
          uploadSuccessMessage.textContent = `Video ${file.name} was uploaded successfully.`;
        }
      }
      if (uploadSuccessModal) {
        uploadSuccessModal.show();
      }
      app.setAlert(videosAlert, "success", "Video uploaded successfully");
    } catch (error) {
      hideUploadLoading();
      app.setAlert(videosAlert, "danger", error.message);
    }
  });

  videosTableBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    const video = state.videos.find((item) => item.id === button.dataset.id);
    if (!video) {
      return;
    }

    if (button.dataset.action === "preview") {
      app.setAlert(videosAlert, "danger", "");
      openPreviewModal(video);
      return;
    }

    if (button.dataset.action === "delete") {
      if (!window.confirm(`Delete video ${video.original_filename}?`)) {
        return;
      }

      try {
        await app.apiFetch(`/api/videos/${video.id}`, { method: "DELETE" });
        await loadVideos();
        app.setAlert(videosAlert, "success", "Video deleted successfully");
      } catch (error) {
        app.setAlert(videosAlert, "danger", error.message);
      }
    }
  });

  window.addEventListener("beforeunload", () => {
    stopPolling();
  });
});
