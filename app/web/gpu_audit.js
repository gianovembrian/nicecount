document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const alertBox = document.getElementById("gpuAuditAlert");
  const reloadButton = document.getElementById("gpuAuditReloadButton");
  const checklistContainer = document.getElementById("gpuAuditChecklist");
  const runtimeTable = document.getElementById("gpuAuditRuntimeTable");
  const configTable = document.getElementById("gpuAuditConfigTable");
  const recentJobsTable = document.getElementById("gpuAuditRecentJobsTable");
  const commandList = document.getElementById("gpuAuditCommandList");
  const overallStatus = document.getElementById("gpuAuditOverallStatus");
  const hostNote = document.getElementById("gpuAuditHostNote");
  const torchVersion = document.getElementById("gpuAuditTorchVersion");
  const torchRuntime = document.getElementById("gpuAuditTorchRuntime");
  const cudaStatus = document.getElementById("gpuAuditCudaStatus");
  const cudaDevices = document.getElementById("gpuAuditCudaDevices");
  const recentDevice = document.getElementById("gpuAuditRecentDevice");
  const recentPerf = document.getElementById("gpuAuditRecentPerf");

  function statusBadgeClass(status) {
    const map = {
      pass: "badge-light-success",
      warning: "badge-light-warning",
      fail: "badge-light-danger",
      info: "badge-light-info",
    };
    return map[status] || "badge-light";
  }

  function statusText(status) {
    const map = {
      pass: "Pass",
      warning: "Warning",
      fail: "Fail",
      info: "Info",
    };
    return map[status] || status;
  }

  function toDisplay(value) {
    if (value === null || value === undefined || value === "") {
      return "-";
    }
    if (typeof value === "boolean") {
      return value ? "Yes" : "No";
    }
    return String(value);
  }

  function renderKeyValueRows(container, entries) {
    container.innerHTML = entries
      .map(
        ([label, value]) => `
          <tr>
            <td class="text-muted fw-semibold w-45">${app.escapeHtml(label)}</td>
            <td class="text-gray-900 fw-semibold">${app.escapeHtml(toDisplay(value))}</td>
          </tr>
        `
      )
      .join("");
  }

  function renderChecklist(items) {
    checklistContainer.innerHTML = items
      .map(
        (item) => `
          <div class="app-gpu-audit-item">
            <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
              <div>
                <div class="fw-bold text-gray-900 fs-5">${app.escapeHtml(item.title)}</div>
                <div class="text-muted fs-7 mt-1">${app.escapeHtml(item.summary || "")}</div>
              </div>
              <span class="badge ${statusBadgeClass(item.status)}">${statusText(item.status)}</span>
            </div>
            <div class="text-gray-700 fs-7">${app.escapeHtml(item.detail || "-")}</div>
          </div>
        `
      )
      .join("");
  }

  function renderRecentJobs(items) {
    if (!items.length) {
      recentJobsTable.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted py-10">No analysis jobs found yet.</td>
        </tr>
      `;
      return;
    }

    recentJobsTable.innerHTML = items
      .map(
        (job) => `
          <tr>
            <td class="fw-semibold text-gray-900">${app.escapeHtml(job.video_name)}</td>
            <td><span class="badge ${app.statusBadge(job.status)}">${app.escapeHtml(job.status)}</span></td>
            <td>${app.escapeHtml(job.model_name || "-")}</td>
            <td>${app.escapeHtml((job.device || "-").toUpperCase())}</td>
            <td>${job.processing_fps ? Number(job.processing_fps).toFixed(2) : "-"}</td>
            <td>${job.effective_analysis_fps ? Number(job.effective_analysis_fps).toFixed(2) : "-"}</td>
            <td>${app.escapeHtml(app.formatDateTime(job.updated_at))}</td>
          </tr>
        `
      )
      .join("");
  }

  function renderCommands(items) {
    commandList.innerHTML = items
      .map(
        (item) => `
          <div class="app-gpu-command">
            <div class="fw-bold text-gray-900 fs-6 mb-2">${app.escapeHtml(item.label)}</div>
            <pre class="app-gpu-command-box">${app.escapeHtml(item.command)}</pre>
          </div>
        `
      )
      .join("");
  }

  function fillSummary(payload) {
    overallStatus.innerHTML = `<span class="badge ${statusBadgeClass(payload.overall_status)} fs-7">${statusText(payload.overall_status)}</span>`;
    hostNote.textContent = payload.host_note || "This audit helps verify whether the host is using CUDA, MPS, or CPU fallback.";

    torchVersion.textContent = payload.runtime.torch_version || "Not installed";
    torchRuntime.textContent = payload.runtime.torch_runtime_error
      || `CUDA build: ${payload.runtime.cuda_built_version || "none"} | Ultralytics: ${payload.runtime.ultralytics_version || "-"}`;

    cudaStatus.textContent = payload.runtime.cuda_available
      ? "CUDA Active"
      : (payload.runtime.mps_available ? "MPS Active" : "CPU Fallback");
    cudaDevices.textContent = payload.runtime.cuda_devices.length
      ? payload.runtime.cuda_devices.join(", ")
      : (payload.runtime.nvidia_smi_summary || "No CUDA device detected");

    const latestJob = payload.recent_jobs[0];
    recentDevice.textContent = latestJob?.device ? String(latestJob.device).toUpperCase() : "No Jobs";
    recentPerf.textContent = latestJob
      ? `Processing ${latestJob.processing_fps ? Number(latestJob.processing_fps).toFixed(2) : "-"} FPS`
      : "Run one analysis job to populate this section.";
  }

  function fillTables(payload) {
    renderKeyValueRows(runtimeTable, [
      ["Platform", `${payload.runtime.platform_system} ${payload.runtime.platform_release}`],
      ["Platform Version", payload.runtime.platform_version],
      ["Machine", payload.runtime.machine],
      ["Processor", payload.runtime.processor],
      ["Python", payload.runtime.python_version],
      ["Torch", payload.runtime.torch_version],
      ["Ultralytics", payload.runtime.ultralytics_version],
      ["CUDA Build", payload.runtime.cuda_built_version],
      ["CUDA Available", payload.runtime.cuda_available],
      ["CUDA Device Count", payload.runtime.cuda_device_count],
      ["CUDA Devices", payload.runtime.cuda_devices.join(", ")],
      ["MPS Built", payload.runtime.mps_built],
      ["MPS Available", payload.runtime.mps_available],
      ["nvidia-smi", payload.runtime.nvidia_smi_available],
      ["nvidia-smi Summary", payload.runtime.nvidia_smi_summary],
      ["ffmpeg", payload.runtime.ffmpeg_available],
    ]);

    renderKeyValueRows(configTable, [
      ["DEFAULT_INFERENCE_DEVICE", payload.config.default_inference_device],
      ["DEFAULT_MODEL_PATH", payload.config.default_model_path],
      ["DEFAULT_TARGET_ANALYSIS_FPS", payload.config.target_analysis_fps],
      ["DEFAULT_PREVIEW_FPS", payload.config.preview_fps],
      ["DEFAULT_INFERENCE_IMGSZ", payload.config.inference_imgsz],
      ["DEFAULT_WORKING_MAX_WIDTH", payload.config.working_max_width],
      ["SAVE_ANNOTATED_VIDEO", payload.config.save_annotated_video],
    ]);
  }

  async function loadAudit() {
    const payload = await app.apiFetch("/api/settings/gpu-audit");
    fillSummary(payload);
    renderChecklist(payload.checklist || []);
    fillTables(payload);
    renderRecentJobs(payload.recent_jobs || []);
    renderCommands(payload.commands || []);
  }

  try {
    const user = await app.requireSession();
    if (!user || !user.is_admin) {
      window.location.href = "/videos";
      return;
    }
    await loadAudit();
  } catch (error) {
    app.setAlert(alertBox, "danger", error.message);
    return;
  }

  reloadButton.addEventListener("click", async () => {
    app.setAlert(alertBox, "danger", "");
    reloadButton.disabled = true;
    try {
      await loadAudit();
      app.setAlert(alertBox, "success", "GPU audit reloaded successfully");
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    } finally {
      reloadButton.disabled = false;
    }
  });
});
