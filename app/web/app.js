(function () {
  async function apiFetch(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        ...(options && options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(options && options.headers ? options.headers : {}),
      },
      ...options,
    });

    if (response.status === 204) {
      return null;
    }

    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }

    if (!response.ok) {
      const message = payload && payload.detail ? payload.detail : "Request failed";
      throw new Error(message);
    }

    return payload;
  }

  function formatDateTime(value) {
    if (!value) {
      return "-";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function formatDuration(seconds) {
    if (!seconds || Number.isNaN(Number(seconds))) {
      return "-";
    }
    const totalSeconds = Math.round(Number(seconds));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const remainingSeconds = totalSeconds % 60;
    return [hours, minutes, remainingSeconds]
      .map((value) => String(value).padStart(2, "0"))
      .join(":");
  }

  function formatFileSize(bytes) {
    if (!bytes || Number.isNaN(Number(bytes))) {
      return "-";
    }
    const units = ["B", "KB", "MB", "GB"];
    let size = Number(bytes);
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setAlert(container, type, message) {
    if (!container) {
      return;
    }
    if (!message) {
      container.classList.add("hidden");
      container.innerHTML = "";
      return;
    }
    container.className = `alert alert-${type}`;
    container.innerHTML = escapeHtml(message);
  }

  async function getSession() {
    return apiFetch("/api/auth/me");
  }

  async function requireSession() {
    const session = await getSession();
    if (!session.authenticated || !session.user) {
      window.location.href = "/login";
      return null;
    }
    initShell(session.user);
    return session.user;
  }

  async function redirectIfAuthenticated() {
    const session = await getSession();
    if (session.authenticated) {
      window.location.href = "/videos";
    }
  }

  function initShell(user) {
    const fullName = String(user.full_name || "").trim();
    const initials = fullName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join("") || String(user.username || "U").slice(0, 2).toUpperCase();

    document.querySelectorAll("[data-app-user-name]").forEach((element) => {
      element.textContent = user.full_name;
    });
    document.querySelectorAll("[data-app-username]").forEach((element) => {
      element.textContent = user.username;
    });
    document.querySelectorAll("[data-app-user-initial]").forEach((element) => {
      element.textContent = initials;
    });
    document.querySelectorAll("[data-app-admin-only]").forEach((element) => {
      element.classList.toggle("hidden", !user.is_admin);
    });
    document.querySelectorAll("[data-app-logout]").forEach((element) => {
      element.addEventListener("click", async (event) => {
        event.preventDefault();
        await apiFetch("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
        window.location.href = "/login";
      });
    });
  }

  function statusBadge(status) {
    const map = {
      uploaded: "badge-light-primary",
      converting: "badge-light-info",
      processing: "badge-light-warning",
      processed: "badge-light-success",
      failed: "badge-light-danger",
      pending: "badge-light-secondary",
      queued: "badge-light-info",
      stale: "badge-light-danger",
      completed: "badge-light-success",
      stopped: "badge-light-dark",
    };
    return map[status] || "badge-light";
  }

  window.VehicleCountApp = {
    apiFetch,
    escapeHtml,
    formatDateTime,
    formatDuration,
    formatFileSize,
    getSession,
    initShell,
    redirectIfAuthenticated,
    requireSession,
    setAlert,
    statusBadge,
  };
})();
