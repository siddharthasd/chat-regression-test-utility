# Feature Specification: Tester Identity & Test Credentials (Module 3)

**Feature Branch**: `010-tester-identity`

**Created**: 2026-05-29

**Last Amended**: 2026-06-01

**Status**: Draft

**Input**: User description: "Module 3 — Authentication & User Identity. Two distinct layers: (1) **Tester Identity** — the real human at the harness, OS-derived (no login, no auth flow), used for attribution / logging / UI display; and (2) **Test Credentials** — per-utterance `testId` + `password` from the CSV, opaque to the harness, passed to the connector for chatbot authentication. Tester identity is resolved at startup via `os.getlogin → getpass.getuser → 'unknown-user'`, stored in the application context read-only, auto-stamped on `Job.createdBy`, displayed in a 'Logged in as' UI indicator, written to log line prefixes, and surfaced in the CLI `harness info` output. Test credentials are masked everywhere they surface (`••••••••` in UI, `[MASKED]` in exports, redacted in logs)." *(Note: the earlier draft of this spec also auto-stamped `TesterFeedback.feedbackBy`; the feedback feature was removed entirely in Round 2 — see `Clarifications`. Only `createdBy` attribution remains.)*

> **Parent context**: This module establishes a **two-layer identity model** the prior 9 specs hadn't drawn explicitly: tester identity (who is operating the harness — OS-derived, no auth) versus test credentials (who the chatbot is being asked AS — per-row, opaque). Parent `FR-026` (added in lock-step with this spec) formalizes the tester-identity resolution rule. The test-credentials story is mostly cross-references to rules other modules already enforce — this spec consolidates them in one place and adds nothing new. The Module 3 input's directive to **persist encrypted passwords in the database** + **retain the raw uploaded CSV file** was explicitly **NOT applied** (clarified 2026-05-29) — parent `FR-010` continues to govern: passwords are in-memory only, never persisted in any form, and no raw CSV file is retained. The user's "Module 3" maps to our `010-` directory by the same convention as Modules 2/4/7 → 009/007/008. Per the precedent set by 7 prior rounds, the prior decision "no creator concept" is **partially reversed** here — there is now a creator-attribution concept (auto-derived from the OS), but there is still no authentication flow.

## Clarifications

### Session 2026-05-29

- Q: Tester identity attribution — re-introduce `Job.createdBy` / `TesterFeedback.feedbackBy` populated from the OS user, reversing the no-creator precedent set across 7 prior specs? → A: **Yes (partial).** Re-introduce `Job.createdBy` as an OS-derived string, auto-populated at write time, immutable, not tester-editable. Add the "Logged in as: <user>" indicator to every UI surface. New parent `FR-026` formalizes the resolution rule; lock-step amendments land on `001`/`002`/`003`/`004`/`005`/`009`. There is still no login flow, no credentials challenge, no override. *(Originally this Q also included `TesterFeedback.feedbackBy`; per Round 2 below, the entire user-feedback feature was removed and `feedbackBy` no longer exists.)*
- Q: Password persistence — override parent `FR-010` by persisting encrypted passwords in `Utterance` AND retaining the raw uploaded CSV file with OS-level filesystem permissions? → A: **No.** Drop those Module 3 directives. Parent `FR-010` continues to govern: passwords are in-memory only, never persisted in any form, encrypted or otherwise; the raw uploaded CSV is NOT retained on disk. Module 3 does NOT introduce its own encryption utility for credentials. Job-resumability for credential-bearing rows after a restart remains forbidden by parent `FR-010a`. (The user's earlier choice in `009 R1 Q1` "Honor existing FR-010" stands.)

### Session 2026-05-29 (Round 2 — user-feedback feature removed)

- Q: Should the user-feedback (thumbs-up/down) feature, and Module 3's `TesterFeedback.feedbackBy` auto-stamping, remain in v1? → A: **No — removed entirely.** Driven by the cross-spec user-feedback removal. `FR-004`'s `feedbackBy` bullet is dropped; the Tester-Identity entity description no longer mentions `TesterFeedback`; User Story 2's "Persisted attribution on Jobs and Feedback" is renamed and trimmed; `SC-003` (feedback attribution verification) is removed; edge cases mentioning feedback are removed; the entity-and-assumptions blocks are trimmed. Only `Job.createdBy` auto-stamping remains. The harness has no user-feedback story in v1.

### Session 2026-05-29 (Reshape)

- Q: The 2026-05-29 architecture reshape moved connectors and evaluators from in-process Python plugins to remote HTTP services, eliminated the `sendUtterance(handle, ...)` four-method interface, replaced the `RawResponse` payload concept with `rawChatbotResponse` on `EvaluationResult`, and made the CSV `password` column conditional on the selected connector's `expectsPerRowPassword` flag. What changes for tester identity / test credentials? → A: **Test-credentials half of this spec needs re-wording; tester-identity half is unaffected.** Specifically:
  1. The per-row `password` is now forwarded to the snapshotted connector service via the per-row HTTP `POST` body field defined by `007 FR-002`, not handed to an in-process `sendUtterance(handle, utteranceText, testId, password)` method.
  2. The CSV's `password` column is conditionally required based on the selected connector's `expectsPerRowPassword` flag (per `001 FR-002`, `011 FR-006`/`FR-009`, `013` registration field). When the flag is `false`, no in-memory store entry exists and no password is forwarded.
  3. The "raw" form of the chatbot response is the persisted `rawChatbotResponse` field on `EvaluationResult` (per `009 FR-003`), not a `RawResponse` payload type.
  4. The bundled MockConnector is now the **mock connector service** — a stub HTTP server (per `007 FR-018`–`FR-022`), not a Python class.
  5. The detail view does NOT surface the per-row `password` in any form (per `004 FR-007`'s canonical column set, which has no password column); the earlier draft's `••••••••` placeholder rendering describes a UI surface that does not exist. The masking pattern of `004 FR-005` applies to stored connector / evaluator credentials, not to per-row CSV passwords.
  
  No change to: the OS-derived identity resolution chain, `Job.createdBy` stamping, "Logged in as" indicator, log-line attribution, or any tester-identity-half FR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolve the OS-derived tester identity at startup (Priority: P1)

When the harness process launches, before any module reads or writes persistent state, the framework resolves the OS-derived tester identity using a documented fallback chain. The resolved value is held in a read-only application context for the lifetime of the process. Every subsequent persistence write that needs an "operator" stamp (Job creation) pulls the identity from this context — no module ever re-resolves it, no tester ever supplies their own value, and the identity cannot change mid-process.

**Why this priority**: Without this, the attribution story falls apart — every other module that needs `createdBy` would have to fend for itself, leading to drift. This is the MVP slice.

**Independent Test**: Boot the harness in three environments: (a) a standard interactive shell where `os.getlogin()` works, (b) a stripped terminal environment where `os.getlogin()` fails and `getpass.getuser()` succeeds, (c) a fully degraded environment where both fail. Verify the resolved identity is, respectively: the OS account name, the env-var fallback's value, and the literal `"unknown-user"` string (with a warning log line). In each case, verify a subsequent Job creation stamps the resolved value into `Job.createdBy` without re-resolution.

**Acceptance Scenarios**:

1. **Given** an interactive shell where the OS exposes a logged-in user, **When** the harness starts, **Then** the resolved tester identity equals the OS account name (e.g., `"siddhartha.dhamankar"`).
2. **Given** an environment where `os.getlogin()` raises but `getpass.getuser()` returns successfully, **When** the harness starts, **Then** the resolved identity equals the `getpass.getuser()` value, and a single info-level log line records that the primary mechanism fell back.
3. **Given** an environment where both `os.getlogin()` and `getpass.getuser()` fail, **When** the harness starts, **Then** the resolved identity is the literal string `"unknown-user"`, and a single warning-level log line records the resolution failure.
4. **Given** the harness has resolved a tester identity at startup, **When** any subsequent module queries the application context for the identity, **Then** the returned value is identical to the value resolved at startup — the resolution chain is NOT re-run.

---

### User Story 2 - Persisted Job attribution via `createdBy` (Priority: P1)

Every Job's `createdBy` field carries the OS-derived tester identity captured at job-creation time. The tester does not supply, see, or edit this value via any form control. The value is surfaced in the dashboard's Created By column, the detail view's Metadata Panel, and the export's job metadata block. This is the spec's "attribution" promise made operational across persisted surfaces.

**Why this priority**: Equal-priority with US1 — the resolution is meaningless without persistence. Both are required for the attribution chain to deliver value.

**Independent Test**: Boot harness as OS user `"alice"`, create a Job via the wizard, verify `Job.createdBy == "alice"` in the database. (The earlier `TesterFeedback.feedbackBy` test case is removed per Round 2 — the feedback feature was dropped.)

**Acceptance Scenarios**:

1. **Given** the OS-derived tester identity is `"alice"`, **When** the wizard creates a new Draft Job on Step 1, **Then** `Job.createdBy == "alice"` in the persisted row.
2. **Given** any Job exists, **When** the dashboard renders, **Then** the Created By column shows the persisted `Job.createdBy` value for that row.
3. **Given** any Job exists, **When** the detail view's Metadata Panel renders, **Then** the Created By field shows the persisted `Job.createdBy` value.
4. **Given** any Job is exported, **When** the export's job-metadata block is inspected, **Then** the `createdBy` field is present with the persisted value (per `005 FR-005`).

---

### User Story 3 - Subtle "Logged in as: <user>" UI indicator on every surface (Priority: P2)

Every UI page in the harness — dashboard, wizard, detail view, and any future UI surface — displays a subtle "Logged in as: <user>" indicator (header or footer), where `<user>` is the OS-derived tester identity. The indicator is read-only — there is no UI control to change it, no logout, no login. It exists so the tester can verify what identity will be stamped on their actions without having to dig into the database. The styling is intentionally low-key (small font, muted color); it is informational, not a prominent UI element.

**Why this priority**: The indicator is what makes the attribution model visible to the tester. Without it, the identity is invisible — testers can't catch a misattribution at a glance. Lower than US1/US2 because the value is delivered via persistence even if the indicator never renders.

**Independent Test**: On a harness started as OS user `"alice"`, open each UI surface in turn (dashboard, wizard at any step, detail view of any job) and verify the "Logged in as: alice" indicator is visible on every page without scrolling. Confirm the indicator is non-interactive (no click handlers, no dropdown, no settings menu).

**Acceptance Scenarios**:

1. **Given** the harness is running with resolved identity `"alice"`, **When** the tester navigates to the dashboard, **Then** the page shows "Logged in as: alice" in a subtle position (header or footer area).
2. **Given** the same setup, **When** the tester opens the wizard at any step, **Then** the indicator is also visible.
3. **Given** the same setup, **When** the tester opens any job's detail view, **Then** the indicator is also visible.
4. **Given** the indicator is rendered, **When** the tester attempts to interact with it (click, double-click, right-click), **Then** there is no settings dialog, no logout action, no edit affordance — the indicator is purely informational.

---

### User Story 4 - Tester identity in log-line prefixes (Priority: P2)

Every log line emitted by the harness carries a tester-identity prefix (or structured field) so log files are attributable. If a tester triages a problem from log output later, they can confirm which OS account ran which session. The prefix value comes from the same application-context source as `createdBy` — no re-resolution, no drift.

**Why this priority**: Forensic value. Especially useful if multiple OS users on a shared laptop have run jobs against the same database file (a real edge case for shared lab environments). Lower priority than US1/US2 because log attribution doesn't affect the harness's runtime behavior.

**Independent Test**: Boot the harness as `"alice"`, drive a few operations (create job, run a job), inspect the log file, verify every line includes `"alice"` as a prefix or structured field.

**Acceptance Scenarios**:

1. **Given** the resolved identity is `"alice"`, **When** the harness emits any log line at any level (info, warning, error), **Then** that line includes `"alice"` as a prefix or structured field, in a documented format.
2. **Given** a single harness process resolved its identity at startup, **When** logs are inspected, **Then** every line from that process shows the SAME identity value — no mid-process drift.

---

### User Story 5 - Tester identity in the `harness info` CLI output (Priority: P3)

The harness ships a `harness info` CLI command (specced in Module 15, TBD) that prints diagnostics. Among its output: the resolved tester identity. This lets the tester confirm what the harness sees as their identity without launching the web UI — useful for scripting, automated environments, or quick verification.

**Why this priority**: Productivity feature. The same information is reachable via the UI indicator (US3); the CLI form is cheaper for automated checks.

**Independent Test**: Run `harness info` from a shell, observe the printed output, confirm the resolved tester identity is one of the visible fields.

**Acceptance Scenarios**:

1. **Given** the harness is installed, **When** the tester runs `harness info`, **Then** the output includes the resolved tester identity in a clearly-labeled field (e.g., `"tester_identity": "alice"`).

---

### User Story 6 - Test credentials remain opaque, in-memory only, and masked everywhere (Priority: P1)

For every CSV row, the `testId` and `password` are passed from the wizard's Step 2 upload through the in-memory password store (per `011 FR-015`) to the orchestrator (per `012 FR-011`), which forwards them in the per-row HTTP `POST` body to the snapshotted connector service per `007 FR-002` — `password` only when the snapshotted `connectorExpectsPerRowPassword` is `true` (per `001 FR-002`, `013` registration field). The harness does NOT validate them, does NOT store the `password`, does NOT log them. `testId` is persisted (per `009 FR-002`), surfaced in the Standard Evaluation Contract input fields per `006 FR-002` (the contract is produced by the connector service per `007 FR-003`), the EvaluationResult (per `009 FR-003`), the detail view's results table (per `004 FR-007`), and the export (per `005 FR-006`). `password` appears in NONE of those — it's a per-row value used once at the moment of connector HTTP dispatch and evicted from the in-memory store immediately afterward (per `011 FR-015` / `012 FR-011` step 3). This story consolidates rules already enforced by 6 other modules; nothing new is added here.

**Why this priority**: Critical to the harness's identity-aware testing premise. Without per-row credentials, the testing model collapses. The story is P1 even though it's mostly enforcement-by-reference because if it falls apart anywhere (e.g., a future spec drift), the whole story falls apart.

**Independent Test**: Upload a CSV containing rows with distinct `(testId, password)` pairs to a job whose snapshotted connector has `expectsPerRowPassword == true`. Run the job to completion. Inspect: (a) the database file's bytes — no password value should appear in plaintext or encrypted form (verifying `009 SC-004`); (b) the detail view's results table — `testId` column shows the values; no password column exists at all (per `004 FR-007`); (c) the export — `testId` column present, password column entirely absent per `005 FR-006` (not masked, not `[MASKED]`); (d) the log file — no password value appears anywhere.

**Acceptance Scenarios**:

1. **Given** a CSV row carries a `(testId, password)` pair against a connector whose `expectsPerRowPassword == true`, **When** the orchestrator processes the row, **Then** the per-row HTTP `POST` to the connector endpoint (per `007 FR-002` and `012 FR-011` step 2) carries both values in the JSON body; the password is NOT logged before, during, or after the call.
2. **Given** the row's processing completes (success or failure), **When** the harness writes to any persistent surface (database, exported file, log file), **Then** the `password` value MUST NOT appear in any form, encrypted or plaintext (per parent `FR-010`, `009 FR-009`, `009 SC-004`).
3. **Given** the row is rendered in the detail view, **When** the page displays, **Then** `testId` is shown in full; the `password` does NOT appear in any column, cell, or expand affordance of the row's rendering — the detail view's canonical column set (`004 FR-007`) has no password column.
4. **Given** the row appears in any export, **When** the export is generated, **Then** the password column is **absent entirely** from every output format (CSV column omitted; JSON field omitted); the actual password is not in any output byte and there is no `[MASKED]` placeholder either (per `005 FR-006`).
5. **Given** any debug log statement that includes per-row context, **When** the log line is emitted, **Then** the password is omitted entirely or replaced by `[REDACTED]`. The `testId` MAY appear in logs.

---

### Edge Cases

- The OS user account name contains characters that would need escaping in HTML (e.g., `<`, `&`) — the UI indicator MUST safely render the name as data, never as HTML/script (XSS-safe display).
- The OS user account name is extremely long (multi-segment domain account, e.g. `CORP\verylongusername.dhamankar`) — the UI indicator MAY truncate with an expand-on-hover affordance; persisted `createdBy` MUST be the full value untruncated.
- The OS user account name is empty string after the resolution chain (unlikely but technically possible on some platforms) — the resolution MUST treat empty as failure and fall through to `"unknown-user"`.
- The same harness install on a shared laptop is operated by two different OS users on different days — each Job's `createdBy` reflects the OS user at creation time; the dashboard's Created By filter shows both names as distinct options.
- A tester impersonates another tester by changing their OS account temporarily — the harness has no way to detect this; whatever value the OS reports is what gets stamped. This is acknowledged as a known limitation; the attribution is at-best advisory.
- The harness is launched from a CI runner where the OS user is something like `"runner"` or `"GITHUB_ACTIONS"` — that value is stamped verbatim. The persistence model is agnostic to whether the "user" is a person or an automation agent.
- The `harness info` CLI is run when no UI process is running — the resolution chain runs against whatever OS context the CLI invocation sees, which may differ from a UI-launched process (e.g., service account vs. login user). Acknowledged as a known limitation; both values are accurate for their respective contexts.
- A CSV row's `testId` happens to contain characters that look like a password (long alphanumeric strings) — the harness still treats it as a `testId` and surfaces it in full. The two fields are distinguished by CSV column, not by content heuristics.
- A CSV row has an empty `testId` or empty `password` value — caught by Module 8's CSV validation (TBD) before the Utterance is persisted; out of scope for this spec.

## Requirements *(mandatory)*

### Functional Requirements

#### Tester Identity (OS-derived)

- **FR-001**: The harness MUST resolve a **tester identity** at process startup, before any other module reads or writes persistent state. The identity is a single string value. The resolution mechanism is a documented fallback chain; the spec mandates the chain's behavior at each step:
  - First, attempt the primary OS-derived value (e.g., `os.getlogin()` on Python). On success, use that.
  - On failure, attempt the secondary OS-derived value (e.g., `getpass.getuser()`). On success, use that and emit an info-level log line noting the fallback.
  - On secondary failure, default to the literal string `"unknown-user"` and emit a warning-level log line.
  - The specific library/function bindings are plan-level; the behavioral chain (primary → secondary → fallback) MUST be honored.
- **FR-002**: The resolved tester identity MUST be stored in a single read-only application-context location (e.g., a shared service object or Flask `g`/app-context) for the lifetime of the process. The value MUST be readable by any harness module. The value MUST NOT be writable by any module after startup, MUST NOT change during the process lifetime, and MUST NOT be re-resolved on subsequent reads.
- **FR-003**: The harness MUST NOT expose any UI control, CLI flag, configuration option, or environment variable through which the tester can override or supply their own tester identity. The identity is system-derived only.
- **FR-004**: The tester identity MUST be auto-stamped onto persisted attribution fields at write time:
  - `Job.createdBy` at Job creation (per `009 FR-001`, wizard `003 FR-004`).
  - Other future audit fields that need an operator stamp.
  - *(The earlier draft of this FR also stamped `TesterFeedback.feedbackBy`. Per Round 2 the feedback feature was removed entirely; the `TesterFeedback` entity no longer exists, and there is nothing to stamp there.)*
- **FR-005**: Every UI surface MUST display a subtle **"Logged in as: <user>"** indicator. The indicator is read-only, non-interactive (no click handler, no edit affordance, no logout action). Position and styling are plan-level; the spec requires only that the indicator is visible without scrolling on every UI page (dashboard, wizard, detail view) and that the displayed value matches the application-context tester identity.
- **FR-006**: Every log line emitted by the harness MUST carry the tester identity as a prefix or structured field. The exact log format (prefix syntax, structured-logging field name) is plan-level; the spec requires only that every line is attributable and that the value matches the application-context tester identity (no drift mid-process).
- **FR-007**: The `harness info` CLI command (Module 15, TBD) MUST include the resolved tester identity in its output as a clearly-labeled field. Specifying the full CLI output shape is out of scope for this module; this spec only mandates that the identity is reachable via that command.

#### Test Credentials (per-row CSV `testId` and `password`)

- **FR-008**: The harness MUST treat each CSV row's `testId` and `password` as **opaque, pass-through values** for connector authentication. The harness MUST NOT validate them against any external system at upload time or at runtime. The harness MUST NOT manage, provision, rotate, or check the corresponding external test accounts.
- **FR-009**: The CSV's required schema MUST include `utteranceText` and `testId` always, plus `password` if and only if the selected connector's `expectsPerRowPassword == true` (per `001 FR-002`, `011 FR-006`/`FR-009`, `013` registration field). All required columns MUST be non-empty per row. CSV-level validation (column presence, non-empty values, encoding correctness, conditional-`password` enforcement) is performed by Module 8 (CSV Upload & Validation Service, `011`). This module does NOT implement the CSV parsing or validation; it only documents the credential-handling rules other modules must follow.
- **FR-010**: The per-row `password` MUST NOT be persisted in any form, encrypted or otherwise, in any persistent store (database, file system, log files). This is the operational form of parent `FR-010`. (The Module 3 input's directive to persist encrypted passwords was explicitly NOT applied — see `Clarifications` Q2.)
- **FR-011**: The original uploaded CSV file MUST NOT be retained on disk as a binary artifact. The Module 3 input's directive to store the raw CSV with OS-level filesystem permissions was explicitly NOT applied. Only the per-row persisted Utterance records (minus `password`) and the `Job.sourceCSVFilename` basename string (per `011 FR-017`) survive past upload. The detail view's source-CSV download (`004 FR-006`) reconstructs from those records.
- **FR-012**: The per-row `password` MUST be forwarded to the snapshotted connector service via the per-row HTTP `POST` body field defined by `007 FR-002`, and only when the snapshotted `connectorExpectsPerRowPassword` is `true` (per `001 FR-006`, `011 FR-015`, `012 FR-011` step 2). The connector service is responsible for all chatbot-side authentication logic — token acquisition, session management, retries against the chatbot's identity system. The harness's only responsibility is forwarding the raw values per the wire protocol.
- **FR-013**: The per-row `password` MUST be invisible everywhere it could surface to a tester or to a non-harness consumer:
  - **In the UI**: the `password` does NOT appear in any column, cell, or expand affordance of the detail view's results table — the canonical column set defined in `004 FR-007` has no password column at all. There is no masked placeholder either — the column simply does not exist. The `••••••••` masking pattern of `004 FR-005` applies to stored connector / evaluator credentials (within `connectorAuthDescriptor` / `evaluatorAuthDescriptor`), not to per-row CSV passwords.
  - **In exports**: the password column / field is **absent entirely** — not present at all, not masked. The CSV omits the column; the JSON omits the field (per `005 FR-006`). This is a stricter rule than the masking treatment used for connector / evaluator stored credentials (per `005 FR-011`): per-row CSV passwords don't appear in any form. Rationale: stored credentials are surfaced (masked) so testers know they exist; per-row passwords are personal credentials of the test accounts and don't belong on the export at all.
  - **In logs**: omitted entirely or rendered as `[REDACTED]`, never the underlying value. Per-row debug logs MAY include `testId` but MUST exclude `password`.
- **FR-014**: The `testId` MUST be carried through the full per-row traceability chain in plaintext form: persisted on Utterance (`009 FR-002`), included in the Standard Evaluation Contract (`006 FR-002`), denormalized onto EvaluationResult (`009 FR-003`), shown as a filterable column in the detail view's results table (`004 FR-007`, `004 FR-012`), and included in exports (`005 FR-006`). The `testId` is NEVER masked.
- **FR-015**: For the same utterance text appearing with different `(testId, password)` pairs across rows, the harness MUST treat each as an independent execution. The harness issues one independent HTTP `POST` per row to the connector service (per `007 FR-005`, `012 FR-023`); each request is stateless at the harness layer. The connector service MAY share internal session state on its side across requests with the same `testId`, but the harness's per-row records remain independent.
- **FR-016**: Connector services MUST NOT echo or leak the per-row `password` in the HTTP response body they return (which the harness persists as `rawChatbotResponse` per `009 FR-003`, alongside the validated `normalizedContract`). The bundled mock connector service (per `007 FR-018`–`FR-022`) MUST NOT echo `password` in any response field — only `testId` MAY be echoed back. This is a connector-service-implementation rule; the harness's enforcement is via the masking / absence rules of `FR-013`.

### Key Entities *(include if feature involves data)*

- **Tester Identity (application-context value)**: A single read-only string resolved at process startup per `FR-001`. Held in the application context for the lifetime of the process. Auto-stamped onto `Job.createdBy` per `FR-004`. Surfaced in UI per `FR-005`, in logs per `FR-006`, and in CLI per `FR-007`. Not a persisted entity — the persisted form is the `createdBy` field on Job.
- **Test Credential (per-row, transient)**: A `(testId, password)` pair from one CSV row, held in memory only for the duration of that row's connector HTTP dispatch. Carried as fields in the per-row HTTP `POST` body to the connector service per `FR-012` (`007 FR-002`); `password` only when the snapshotted `connectorExpectsPerRowPassword` is `true`. Not persisted in any form (per `FR-010`); never logged in plaintext (per `FR-013`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The resolved tester identity is identical across every call site within a single harness process — verifiable by querying the application-context value from multiple modules and asserting equality.
- **SC-002**: Booting the harness as OS user `<X>` and creating a new Job results in `Job.createdBy == <X>` in the database — verifiable by SQL inspection.
- **SC-003**: *(Removed in Round 2 — see `Clarifications`. Previously verified `TesterFeedback.feedbackBy` stamping; the feedback feature was removed entirely.)*
- **SC-004**: Every UI page renders a "Logged in as: <user>" indicator that matches the application-context identity — verifiable by automated UI inspection on each of: dashboard, each wizard step, detail view.
- **SC-005**: Every log line emitted by the harness during a session attributes to a single tester identity, equal to the application-context value, with no mid-process drift — verifiable by parsing the log file and grouping lines by attribution.
- **SC-006**: The `harness info` CLI output includes the resolved tester identity as a labeled field — verifiable by running the command and parsing its output.
- **SC-007**: No persisted byte of the database file contains a per-row CSV `password` value, in plaintext or encrypted form — verifiable by inserting a known-distinctive password (e.g., `"DEADBEEF-PWD-12345"`) and grepping the database file (must produce zero matches). Identical to `009 SC-004` but listed here for completeness.
- **SC-008**: No exported file (CSV, JSON, or zip) contains a per-row password value — verifiable by exporting a job and grepping the exported bytes for the known-distinctive password value.
- **SC-009**: No log file emitted during a session contains a per-row password value — verifiable by setting log level to debug, running a job that exercises every connector code path, and grepping the log file for the known-distinctive password value.
- **SC-010**: The harness has no UI control, CLI flag, configuration option, or environment variable that allows the tester to override the OS-derived identity — verifiable by reviewing the configuration surface and the UI.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Parent `FR-026` (added in lock-step with this spec) is the canonical "OS-derived tester identity resolution" rule; this spec operationalizes it.
- The library bindings used to perform OS resolution (`os.getlogin`, `getpass.getuser`, equivalent) are plan-level. The spec requires only the documented fallback chain behavior.
- "OS-derived" is honest about its trust model: the harness trusts whatever the OS reports. A user who changes their OS account between sessions, or who runs the harness via `sudo`/`runas`, will get a different attribution. The harness's role is to capture and persist what the OS says, not to verify identity in any cryptographic sense.
- The `Job.createdBy` field is NOT a substitute for authentication. It is attribution-only — useful for "who ran this on which laptop?" forensic questions, not for access control. There is no access control in the harness (it's a single-user local tool).
- The "Logged in as" indicator's exact styling, position (header vs. footer), and any responsiveness behaviors are plan-level UI choices.
- The log-line format (prefix syntax, structured-log field name) is plan-level. The spec requires only universal attribution and no mid-process drift.
- The `harness info` CLI is specced separately by Module 15 (TBD). This module only mandates that the tester identity is one of the fields it emits.
- Module 8 (CSV Upload & Validation Service, TBD) owns CSV-level validation including the presence and non-emptiness of `utteranceText` / `testId` / `password` columns. This spec only documents the credential-handling rules that Module 8 and other consuming modules must honor.
- "Modules 5/6" in the user's original Module 3 input refer to specific connector implementations (e.g., a Copilot Studio connector service, a Semantic Kernel connector service); none of those exist yet. This spec only requires that connector services honor the wire protocol defined in `007 FR-002` — accepting a `POST` body of `{testId, utteranceText, password?}` and returning a Standard Evaluation Contract instance — and never leak the `password` in their HTTP response body.
- The same harness install operated by different OS users (e.g., on a shared lab laptop) is supported: each Job's `createdBy` reflects who created it; the dashboard's Created By filter enumerates the distinct values seen in the persisted jobs.
- Forgetting the OS-derived identity is impossible — there's no logout, no UI to clear it, no opt-out. This is by design: the harness is not optional about attribution.
