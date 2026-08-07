# User Management Guide

This guide covers how to manage who can access the harness when Azure AD
authentication is enabled (`HARNESS_AUTH_ENABLED=true`).

---

## How access works

The harness uses a **two-step access model**:

1. **Azure AD authenticates** the user (verifies their identity via Microsoft login, or validates a Bearer token for API callers).
2. **The harness authorises** the user by checking that their email exists in the
   harness user registry and reading their assigned role.

A valid Azure AD account is not enough on its own — the user must also be
pre-registered in the harness registry. If they log in and are not registered,
they are shown an "Access Denied" page.

### Roles

| Role | What they can do |
|---|---|
| `admin` | Full access: run jobs, view all jobs, manage connectors and evaluators, manage the user registry. |
| `user` | Run jobs and view their own jobs. Cannot manage connectors, evaluators, or users. |

### Access methods

| Method | Who uses it | How identity is verified |
|---|---|---|
| Browser login | Human users | Azure AD OAuth2 (Microsoft login page) |
| Bearer token | External systems using the headless API | Azure AD JWT validated on each request |

Both methods require the caller to be pre-registered in the harness user registry.

---

## Managing users via the Admin UI

Navigate to **Users** in the top navigation bar (visible to admins only).

### Register a new user

1. Go to **Users → Register New User**.
2. Enter the user's Accenture email address, an optional display name, and choose a role.
3. Click **Register**.

The user can now log in with their Microsoft account. On first login the harness
automatically links their Azure AD identity to their registration record.

### Change a user's role

On the **Users** page, find the user's row, select a new role from the dropdown,
and click **Change**.

### Remove a user

On the **Users** page, click **Remove** next to the user's row. You cannot remove
your own account — this prevents accidental lockout.

---

## Managing users via the CLI

The `harness users` command group lets you manage the registry from a terminal,
which is useful for initial bootstrap and scripted provisioning. Run commands in
the project directory so the harness can locate the correct database.

### Add a user

```
harness users add <email> [--role admin|user] [--name "Display Name"]
```

Examples:

```bash
# Register a regular user
harness users add alice@accenture.com

# Register an admin
harness users add bob@accenture.com --role admin --name "Bob Smith"
```

The default role is `user` if `--role` is not specified.

### List all users

```
harness users list
```

Output shows email, role, whether the Azure AD account has been linked (i.e.
whether the user has logged in at least once), and display name.

### Change a user's role

```
harness users change-role <email> <admin|user>
```

Example:

```bash
harness users change-role alice@accenture.com admin
```

### Remove a user

```
harness users remove <email> [--yes]
```

You will be prompted to confirm unless `--yes` is passed.

```bash
harness users remove alice@accenture.com
harness users remove alice@accenture.com --yes   # skip prompt
```

---

## Bootstrap: adding the first admin

Before anyone can manage users via the UI, at least one admin must exist in the
registry. Use the CLI on the server immediately after the first `harness serve`:

```bash
harness users add you@accenture.com --role admin
```

Then navigate to the harness URL and log in with your Microsoft account. You will
land on the dashboard with an **admin** badge in the navbar and the **Users** link
visible.

---

## Headless API access

The harness exposes a headless API at `/api/headless/` for external systems such
as qual-brew to submit and run evaluation jobs programmatically. API callers
authenticate with an Azure AD Bearer token instead of the browser login flow, but
they are subject to the same user registry requirement as human users.

To grant an external system access:

1. Ensure the system has an Azure AD identity (a service principal or a user
   account that will obtain tokens on its behalf).
2. Register its email address in the harness user registry:

   ```bash
   harness users add system@accenture.com --role user --name "qual-brew"
   ```

3. On the first authenticated API call the harness links the Azure AD OID from
   the Bearer token to the registration record automatically, the same way it
   does for human users on first browser login.

The `user` role is sufficient for all headless API operations.

---

## Common scenarios

**A new team member needs access**

Register them via the UI (Users → Register New User) or the CLI:

```bash
harness users add newperson@accenture.com
```

They can log in immediately using their existing Microsoft account — no further
Azure AD configuration is needed.

**A user leaves the team**

Remove them via the UI or the CLI:

```bash
harness users remove ex-employee@accenture.com --yes
```

Their Azure AD account is unaffected; only the harness registry entry is removed.
They will be shown "Access Denied" on their next login attempt. For API callers,
the next request receives HTTP 403.

**A user should become an admin**

```bash
harness users change-role user@accenture.com admin
```

The change takes effect on the user's next login (the role is written into the
session at login time, not re-read on every request).

**A user registered but cannot log in**

Check the **Linked** column in `harness users list`. If it shows `no`, the user
has not logged in yet — their Azure AD OID has not been matched to the
registration. Have them attempt to log in; the link is created automatically on
first successful authentication.

If it still shows `no` after a login attempt, confirm the email address in the
registry exactly matches the `preferred_username` in their Azure AD account
(usually their UPN, e.g. `firstname.lastname@accenture.com`).

**An API caller receives HTTP 403**

Check that the service account's email is registered (`harness users list`) and
that the **Linked** column shows `yes`. If it shows `no`, the OID in the Bearer
token has never matched the registration — verify the email used at registration
matches the identity in the token, then have the caller make one authenticated
request to trigger the link.
