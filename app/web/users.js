document.addEventListener("DOMContentLoaded", async () => {
  const app = window.VehicleCountApp;
  const usersAlert = document.getElementById("usersAlert");
  const usersTableBody = document.getElementById("usersTableBody");
  const openCreateUserModalButton = document.getElementById("openCreateUserModal");

  const userModalElement = document.getElementById("userModal");
  const userModalTitle = document.getElementById("userModalTitle");
  const userSubmitButton = document.getElementById("userSubmitButton");
  const userPasswordGroup = document.getElementById("userPasswordGroup");
  const userForm = document.getElementById("userForm");

  const passwordModalElement = document.getElementById("passwordModal");
  const passwordTarget = document.getElementById("passwordTarget");
  const passwordForm = document.getElementById("passwordForm");

  const userModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(userModalElement) : null;
  const passwordModal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(passwordModalElement) : null;

  const state = {
    sessionUser: null,
    users: [],
  };

  const ICONS = {
    edit: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M4 20h4l10-10-4-4L4 16v4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
          <path d="m12 6 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </span>
    `,
    password: `
      <span class="app-inline-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.8"/>
          <path d="M8 11V8a4 4 0 1 1 8 0v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
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

  function showModal(instance) {
    if (instance) {
      instance.show();
    }
  }

  function hideModal(instance) {
    if (instance) {
      instance.hide();
    }
  }

  function resetUserForm() {
    userForm.reset();
    userForm.user_id.value = "";
    userForm.username.disabled = false;
    userForm.password.required = true;
    userPasswordGroup.classList.remove("hidden");
    userModalTitle.textContent = "Add User";
    userSubmitButton.textContent = "Save User";
    userForm.is_admin.value = "false";
    userForm.is_active.value = "true";
  }

  function openCreateUserModal() {
    resetUserForm();
    showModal(userModal);
  }

  function openEditUserModal(user) {
    resetUserForm();
    userForm.user_id.value = user.id;
    userForm.username.value = user.username;
    userForm.username.disabled = true;
    userForm.full_name.value = user.full_name;
    userForm.is_admin.value = String(user.is_admin);
    userForm.is_active.value = String(user.is_active);
    userForm.password.value = "";
    userForm.password.required = false;
    userPasswordGroup.classList.add("hidden");
    userModalTitle.textContent = "Edit User";
    userSubmitButton.textContent = "Update User";
    showModal(userModal);
  }

  function resetPasswordForm() {
    passwordForm.reset();
    passwordForm.user_id.value = "";
    passwordTarget.textContent = "No user selected";
  }

  function openPasswordModal(user) {
    resetPasswordForm();
    passwordForm.user_id.value = user.id;
    passwordTarget.textContent = `${user.full_name} (${user.username})`;
    showModal(passwordModal);
  }

  function actionButton({ action, id, label, className, disabled = false, title = "" }) {
    const disabledMarkup = disabled ? "disabled" : "";
    const titleMarkup = title ? `title="${app.escapeHtml(title)}"` : "";
    return `
      <button
        class="btn btn-sm ${className}"
        type="button"
        data-action="${action}"
        data-id="${id}"
        ${titleMarkup}
        ${disabledMarkup}
      >
        ${ICONS[action]}
        <span>${label}</span>
      </button>
    `;
  }

  function renderUsers() {
    if (!state.users.length) {
      usersTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted py-10">No users yet. Click "Add User" to create the first account.</td>
        </tr>
      `;
      return;
    }

    usersTableBody.innerHTML = state.users.map((user, index) => {
      const isCurrentUser = String(user.id) === String(state.sessionUser.id);
      const nameSuffix = isCurrentUser ? `<span class="badge badge-light-info ms-2">You</span>` : "";

      return `
        <tr>
          <td class="text-gray-700 fw-semibold">${index + 1}</td>
          <td>
            <div>
              <div class="app-user-primary">${app.escapeHtml(user.username)}</div>
              <div class="app-user-secondary">Login account</div>
            </div>
          </td>
          <td>
            <div class="app-user-primary">${app.escapeHtml(user.full_name)}${nameSuffix}</div>
              <div class="app-user-secondary">Last updated ${app.formatDateTime(user.updated_at)}</div>
          </td>
          <td><span class="badge ${user.is_admin ? "badge-light-primary" : "badge-light"}">${user.is_admin ? "Admin" : "User"}</span></td>
          <td><span class="badge ${user.is_active ? "badge-light-success" : "badge-light-danger"}">${user.is_active ? "Active" : "Inactive"}</span></td>
          <td>${app.formatDateTime(user.created_at)}</td>
          <td class="text-end">
            <div class="app-action-group">
              ${actionButton({
                action: "edit",
                id: user.id,
                label: "Edit",
                className: "btn-light-primary",
                title: `Edit ${user.username}`,
              })}
              ${actionButton({
                action: "password",
                id: user.id,
                label: "Set Password",
                className: "btn-light-warning",
                title: `Set password ${user.username}`,
              })}
              ${actionButton({
                action: "delete",
                id: user.id,
                label: "Delete",
                className: "btn-light-danger",
                disabled: isCurrentUser,
                title: isCurrentUser ? "The currently signed-in user cannot be deleted" : `Delete ${user.username}`,
              })}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function loadUsers() {
    state.users = await app.apiFetch("/api/users");
    renderUsers();
  }

  try {
    state.sessionUser = await app.requireSession();
    if (!state.sessionUser.is_admin) {
      window.location.href = "/videos";
      return;
    }
    resetUserForm();
    resetPasswordForm();
    await loadUsers();
  } catch (error) {
    app.setAlert(usersAlert, "danger", error.message);
    return;
  }

  userModalElement.addEventListener("hidden.bs.modal", () => {
    resetUserForm();
  });

  passwordModalElement.addEventListener("hidden.bs.modal", () => {
    resetPasswordForm();
  });

  openCreateUserModalButton.addEventListener("click", () => {
    app.setAlert(usersAlert, "danger", "");
    openCreateUserModal();
  });

  userForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(usersAlert, "danger", "");

    const payload = {
      full_name: userForm.full_name.value.trim(),
      is_admin: userForm.is_admin.value === "true",
      is_active: userForm.is_active.value === "true",
    };

    try {
      if (userForm.user_id.value) {
        await app.apiFetch(`/api/users/${userForm.user_id.value}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        app.setAlert(usersAlert, "success", "User details updated successfully");
      } else {
        const password = userForm.password.value;
        if (!password) {
          throw new Error("Password is required when creating a new user");
        }
        await app.apiFetch("/api/users", {
          method: "POST",
          body: JSON.stringify({
            username: userForm.username.value.trim(),
            password,
            ...payload,
          }),
        });
        app.setAlert(usersAlert, "success", "User created successfully");
      }

      hideModal(userModal);
      await loadUsers();
    } catch (error) {
      app.setAlert(usersAlert, "danger", error.message);
    }
  });

  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    app.setAlert(usersAlert, "danger", "");

    const userId = passwordForm.user_id.value;
    if (!userId) {
      app.setAlert(usersAlert, "danger", "Select a user from the table first");
      return;
    }

    if (passwordForm.password.value !== passwordForm.confirm_password.value) {
      app.setAlert(usersAlert, "danger", "Password confirmation does not match");
      return;
    }

    try {
      await app.apiFetch(`/api/users/${userId}/password`, {
        method: "PUT",
        body: JSON.stringify({ password: passwordForm.password.value }),
      });
      hideModal(passwordModal);
      app.setAlert(usersAlert, "success", "Password updated successfully");
    } catch (error) {
      app.setAlert(usersAlert, "danger", error.message);
    }
  });

  usersTableBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled) {
      return;
    }

    const user = state.users.find((item) => item.id === button.dataset.id);
    if (!user) {
      return;
    }

    if (button.dataset.action === "edit") {
      app.setAlert(usersAlert, "danger", "");
      openEditUserModal(user);
      return;
    }

    if (button.dataset.action === "password") {
      app.setAlert(usersAlert, "danger", "");
      openPasswordModal(user);
      return;
    }

    if (button.dataset.action === "delete") {
      if (!window.confirm(`Delete user ${user.username}?`)) {
        return;
      }

      try {
        await app.apiFetch(`/api/users/${user.id}`, { method: "DELETE" });
        await loadUsers();
        app.setAlert(usersAlert, "success", "User deleted successfully");
      } catch (error) {
        app.setAlert(usersAlert, "danger", error.message);
      }
    }
  });
});
