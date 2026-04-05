document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const form = document.getElementById("loginForm");
  const alertBox = document.getElementById("loginAlert");

  try {
    await app.redirectIfAuthenticated();
  } catch (error) {
    app.setAlert(alertBox, "danger", error.message);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(alertBox, "danger", "");

    const formData = new FormData(form);
    const payload = {
      username: String(formData.get("username") || "").trim(),
      password: String(formData.get("password") || ""),
    };

    try {
      await app.apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.location.href = "/videos";
    } catch (error) {
      app.setAlert(alertBox, "danger", error.message);
    }
  });
});
