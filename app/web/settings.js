document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const settingsAlert = document.getElementById("settingsAlert");
  const form = document.getElementById("detectionSettingsForm");
  const reloadButton = document.getElementById("reloadDetectionSettingsButton");
  const saveButton = document.getElementById("saveDetectionSettingsButton");
  const globalConfidenceInput = document.getElementById("globalConfidenceInput");
  const motorcycleMinConfidenceInput = document.getElementById("motorcycleMinConfidenceInput");
  const vehicleMinConfidenceInput = document.getElementById("vehicleMinConfidenceInput");

  function setSaving(isSaving) {
    saveButton.disabled = isSaving;
    saveButton.textContent = isSaving ? "Saving..." : "Save Settings";
    reloadButton.disabled = isSaving;
  }

  function fillForm(payload) {
    globalConfidenceInput.value = Number(payload.global_confidence || 0).toFixed(2);
    motorcycleMinConfidenceInput.value = Number(payload.motorcycle_min_confidence || 0).toFixed(2);
    vehicleMinConfidenceInput.value = Number(payload.vehicle_min_confidence || 0).toFixed(2);
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
      vehicle_min_confidence: Number(vehicleMinConfidenceInput.value || 0),
    };

    if (Object.values(payload).some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      app.setAlert(settingsAlert, "danger", "All values must be between 0.00 and 1.00");
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
