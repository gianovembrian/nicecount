document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const settingsAlert = document.getElementById("settingsAlert");
  const form = document.getElementById("detectionSettingsForm");
  const reloadButton = document.getElementById("reloadDetectionSettingsButton");
  const saveButton = document.getElementById("saveDetectionSettingsButton");
  const globalConfidenceInput = document.getElementById("globalConfidenceInput");
  const motorcycleMinConfidenceInput = document.getElementById("motorcycleMinConfidenceInput");
  const carMinConfidenceInput = document.getElementById("carMinConfidenceInput");
  const busMinConfidenceInput = document.getElementById("busMinConfidenceInput");
  const truckMinConfidenceInput = document.getElementById("truckMinConfidenceInput");
  const iouThresholdInput = document.getElementById("iouThresholdInput");
  const frameStrideInput = document.getElementById("frameStrideInput");
  const targetAnalysisFpsInput = document.getElementById("targetAnalysisFpsInput");
  const previewFpsInput = document.getElementById("previewFpsInput");
  const workingMaxWidthInput = document.getElementById("workingMaxWidthInput");
  const previewMaxWidthInput = document.getElementById("previewMaxWidthInput");
  const previewJpegQualityInput = document.getElementById("previewJpegQualityInput");

  function setSaving(isSaving) {
    saveButton.disabled = isSaving;
    saveButton.textContent = isSaving ? "Saving..." : "Save Settings";
    reloadButton.disabled = isSaving;
  }

  function fillForm(payload) {
    globalConfidenceInput.value = Number(payload.global_confidence || 0).toFixed(2);
    motorcycleMinConfidenceInput.value = Number(payload.motorcycle_min_confidence || 0).toFixed(2);
    carMinConfidenceInput.value = Number(payload.car_min_confidence || 0).toFixed(2);
    busMinConfidenceInput.value = Number(payload.bus_min_confidence || 0).toFixed(2);
    truckMinConfidenceInput.value = Number(payload.truck_min_confidence || 0).toFixed(2);
    iouThresholdInput.value = Number(payload.iou_threshold || 0).toFixed(2);
    frameStrideInput.value = String(Number(payload.frame_stride || 1));
    targetAnalysisFpsInput.value = String(Number(payload.target_analysis_fps || 15));
    previewFpsInput.value = String(Number(payload.preview_fps || 6));
    workingMaxWidthInput.value = String(Number(payload.working_max_width || 0));
    previewMaxWidthInput.value = String(Number(payload.preview_max_width || 0));
    previewJpegQualityInput.value = String(Number(payload.preview_jpeg_quality || 70));
  }

  function validateRange(label, value, min, max) {
    if (!Number.isFinite(value) || value < min || value > max) {
      return `${label} must be between ${min} and ${max}`;
    }
    return "";
  }

  function validateInteger(label, value, min, max) {
    if (!Number.isInteger(value) || value < min || value > max) {
      return `${label} must be a whole number between ${min} and ${max}`;
    }
    return "";
  }

  async function loadDetectionSettings() {
    const payload = await app.apiFetch("/api/settings/detection");
    fillForm(payload);
  }

  try {
    const user = await app.requireSession();
    if (!user || !user.is_admin) {
      window.location.href = "/videos";
      return;
    }
    await loadDetectionSettings();
  } catch (error) {
    app.setAlert(settingsAlert, "danger", error.message);
    return;
  }

  reloadButton.addEventListener("click", async () => {
    app.setAlert(settingsAlert, "danger", "");
    try {
      await loadDetectionSettings();
      app.setAlert(settingsAlert, "success", "Detection settings reloaded");
    } catch (error) {
      app.setAlert(settingsAlert, "danger", error.message);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(settingsAlert, "danger", "");

    const payload = {
      global_confidence: Number(globalConfidenceInput.value || 0),
      motorcycle_min_confidence: Number(motorcycleMinConfidenceInput.value || 0),
      car_min_confidence: Number(carMinConfidenceInput.value || 0),
      bus_min_confidence: Number(busMinConfidenceInput.value || 0),
      truck_min_confidence: Number(truckMinConfidenceInput.value || 0),
      iou_threshold: Number(iouThresholdInput.value || 0),
      frame_stride: Number(frameStrideInput.value || 0),
      target_analysis_fps: Number(targetAnalysisFpsInput.value || 0),
      preview_fps: Number(previewFpsInput.value || 0),
      working_max_width: Number(workingMaxWidthInput.value || 0),
      preview_max_width: Number(previewMaxWidthInput.value || 0),
      preview_jpeg_quality: Number(previewJpegQualityInput.value || 0),
    };

    const validationError = [
      validateRange("Global Confidence", payload.global_confidence, 0, 1),
      validateRange("Motorcycle Min Confidence", payload.motorcycle_min_confidence, 0, 1),
      validateRange("Car Min Confidence", payload.car_min_confidence, 0, 1),
      validateRange("Bus Min Confidence", payload.bus_min_confidence, 0, 1),
      validateRange("Truck Min Confidence", payload.truck_min_confidence, 0, 1),
      validateRange("IOU Threshold", payload.iou_threshold, 0, 1),
      validateInteger("Frame Stride", payload.frame_stride, 1, 30),
      validateRange("Target Analysis FPS", payload.target_analysis_fps, 15, 60),
      validateRange("Preview FPS", payload.preview_fps, 6, 30),
      validateInteger("Working Max Width", payload.working_max_width, 0, 7680),
      validateInteger("Preview Max Width", payload.preview_max_width, 0, 3840),
      validateInteger("Preview JPEG Quality", payload.preview_jpeg_quality, 30, 95),
    ].find(Boolean);

    if (validationError) {
      app.setAlert(settingsAlert, "danger", validationError);
      return;
    }

    try {
      setSaving(true);
      const saved = await app.apiFetch("/api/settings/detection", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      fillForm(saved);
      app.setAlert(settingsAlert, "success", "Detection settings saved successfully");
    } catch (error) {
      app.setAlert(settingsAlert, "danger", error.message);
    } finally {
      setSaving(false);
    }
  });
});
