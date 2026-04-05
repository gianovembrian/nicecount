document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const alertBox = document.getElementById("masterClassesAlert");
  const form = document.getElementById("masterClassesForm");
  const grid = document.getElementById("masterClassesGrid");
  const reloadButton = document.getElementById("reloadMasterClassesButton");
  const saveButton = document.getElementById("saveMasterClassesButton");
  let currentItems = [];

  function setSaving(isSaving) {
    saveButton.disabled = isSaving;
    reloadButton.disabled = isSaving;
    saveButton.textContent = isSaving ? "Saving..." : "Save Master Class";
  }

  function renderItems(items) {
    currentItems = Array.isArray(items) ? items.slice() : [];
    grid.innerHTML = currentItems.map((item) => `
      <div class="col-xl-6">
        <div class="card border border-gray-200 h-100 shadow-sm">
          <div class="card-body">
            <div class="d-flex align-items-center justify-content-between gap-4 mb-5">
              <div>
                <div class="fw-bold fs-4 text-gray-900">${app.escapeHtml(item.code)}</div>
                <div class="text-muted fs-7">Order ${Number(item.sort_order || 0)}</div>
              </div>
              <span class="badge badge-light-primary">${app.escapeHtml(item.label || item.code)}</span>
            </div>

            <div class="mb-5">
              <label class="form-label fw-semibold" for="masterClassLabel_${app.escapeHtml(item.code)}">Class Label</label>
              <input
                id="masterClassLabel_${app.escapeHtml(item.code)}"
                class="form-control form-control-solid"
                type="text"
                maxlength="100"
                value="${app.escapeHtml(item.label || "")}"
                data-master-class-input="label"
                data-code="${app.escapeHtml(item.code)}"
              />
            </div>

            <div>
              <label class="form-label fw-semibold" for="masterClassDescription_${app.escapeHtml(item.code)}">Description</label>
              <textarea
                id="masterClassDescription_${app.escapeHtml(item.code)}"
                class="form-control form-control-solid"
                rows="4"
                maxlength="500"
                data-master-class-input="description"
                data-code="${app.escapeHtml(item.code)}"
              >${app.escapeHtml(item.description || "")}</textarea>
            </div>
          </div>
        </div>
      </div>
    `).join("");
  }

  function buildPayload() {
    return {
      items: currentItems.map((item) => {
        const labelInput = grid.querySelector(`[data-master-class-input="label"][data-code="${item.code}"]`);
        const descriptionInput = grid.querySelector(`[data-master-class-input="description"][data-code="${item.code}"]`);
        return {
          code: item.code,
          label: String(labelInput && labelInput.value ? labelInput.value : "").trim(),
          description: String(descriptionInput && descriptionInput.value ? descriptionInput.value : "").trim(),
        };
      }),
    };
  }

  async function loadMasterClasses() {
    const payload = await app.apiFetch("/api/settings/master-classes");
    renderItems(payload);
  }

  try {
    const user = await app.requireSession();
    if (!user || !user.is_admin) {
      window.location.href = "/videos";
      return;
    }
    await loadMasterClasses();
  } catch (error) {
    app.setAlert(alertBox, "danger", error.message);
    return;
  }

  reloadButton.addEventListener("click", async () => {
    app.setAlert(alertBox, "danger", "");
    try {
      await loadMasterClasses();
      app.setAlert(alertBox, "success", "Master class reloaded");
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(alertBox, "danger", "");

    const payload = buildPayload();
    if (payload.items.some((item) => !item.label)) {
      app.setAlert(alertBox, "danger", "Each master class must have a label");
      return;
    }

    try {
      setSaving(true);
      const saved = await app.apiFetch("/api/settings/master-classes", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      renderItems(saved);
      app.setAlert(alertBox, "success", "Master class saved successfully");
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    } finally {
      setSaving(false);
    }
  });
});
