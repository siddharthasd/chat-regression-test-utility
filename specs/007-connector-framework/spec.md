# Feature Specification: Connector Framework (Module 4)

**Feature Branch**: `007-connector-framework`

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "Module 4 — Connector Framework. A pluggable connector framework with four interface methods (`connect`, `sendUtterance`, `normalize`, `disconnect`), a connector registry that connectors self-register against with a unique id + display name + configuration schema, an encryption/decryption utility for secret config fields, and a MockConnector reference implementation. Adding a new connector requires implementing the interface and registering — zero changes to the core harness."

> **Parent context**: This module is the producer side of the integration seam defined by `specs/006-evaluation-contract/spec.md`. Connectors fulfill the parent harness's `FR-006` (pass utterance/`testId`/`password` to selected connector) and `FR-007` (normalize raw chatbot response into a Standard Evaluation Contract instance). The wizard's Step 3 (`specs/003-job-creation-wizard` → `FR-007`, `FR-008`, `FR-009`, `FR-010`) is the registry's primary UI consumer. The encryption utility introduced here formalizes the harness-wide rule added in parent `FR-023a` (config-level secret-encryption-at-rest with a machine-local key). Parent-spec premises apply: single-user, no auth, no `createdBy`. The Module 4 input's mention of "encryption utility for the password field" was resolved by explicit decision (2026-05-28) to mean **connector config-level secret fields** (API keys, auth tokens) — the per-row CSV `password` rule from parent `FR-010` (in-memory only, never persisted) is unchanged. The Module 4 input's reference to "Standard Evaluation Contract schema (module 1)" was resolved to refer to `specs/006-evaluation-contract`.

## Clarifications

### Session 2026-05-28

- Q: The encryption utility "for the password field" — what does it encrypt? → A: **Config-level secret fields only.** API keys, auth tokens, and any other field a connector declares as secret inside its own configuration form. The per-row CSV `password` (parent `FR-010`) is NOT touched by this utility — it remains in-memory only, never persisted at rest. Parent spec was amended in lock-step (new parent `FR-023a`) to formalize the harness-wide rule.
- Q: When does a connector connect and disconnect across the rows of a job? → A: **Once per job.** `connect()` is invoked at job start; the resulting `ConnectionHandle` is reused for every row in the job; `disconnect()` is invoked at job end (whether the terminal state is `completed`, `failed`, or `cancelled`). Connectors with chatbot platforms that benefit from session reuse (HTTP keep-alive, SDK client pooling, paid session-setup) get the benefit by default. The framework MUST NOT invoke `connect()` mid-job; recoverable session expiry is the connector's internal concern.

### Session 2026-05-28 (Round 2)

- Q: Do connectors carry a separate version field, or is `connectorId` the sole identity? → A: **`connectorId` is the sole identity in v1; no separate version field.** When a connector evolves and needs to coexist with its predecessor, the convention is to bake the version into the id (e.g., `ms-copilot-studio-v1`, `ms-copilot-studio-v2`). The registry treats those as wholly distinct connectors with no relationship between them. The parent spec's `Registered Connector` entity mentions a `version` field; for v1 that's interpreted as "the version baked into `connectorId` by convention", not as a separate registry field. Future work MAY introduce a first-class `connectorVersion` if multiple variants of one logical connector become common.
- Q: Can the orchestrator call `sendUtterance` concurrently on the same `ConnectionHandle`? → A: **No — framework serializes per handle in v1.** The framework MUST guarantee that, for any given `ConnectionHandle`, at most one `sendUtterance` call is in flight at a time. Within a single job, rows are dispatched one at a time. Connector authors do NOT need to make their handles thread-safe or async-safe. Cross-job parallelism (multiple jobs running concurrently per parent `FR-011`) still works because each job has its own handle. This locks the parent spec's "max concurrent in-flight rows per job is implementation tuning" assumption to **1** for v1. Future work MAY introduce a per-connector opt-in (e.g., `supportsConcurrentSendUtterance`) and a corresponding orchestrator parallelism mode.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a job through a registered connector end-to-end (Priority: P1)

The harness orchestrator picks up a queued job, looks up the job's snapshotted connector identity in the Connector Registry, decrypts the snapshotted secret config fields, invokes `connect()` once with the full config, then for every row in the job invokes `sendUtterance()` with the row's utterance + `testId` + `password` and `normalize()` on the raw response to obtain a Standard Evaluation Contract instance. After the last row is processed (or the job is cancelled or fails), the orchestrator invokes `disconnect()`. This is the integration that makes the whole pluggable-connector architecture real.

**Why this priority**: Without this story, no real chatbot ever gets talked to. It is the MVP slice of Module 4.

**Independent Test**: With a registered connector implementation (e.g., the bundled MockConnector), enqueue a 3-row job. Verify the orchestrator (a) calls `connect()` exactly once with the decrypted config, (b) calls `sendUtterance()` exactly three times in row order with the correct per-row arguments, (c) calls `normalize()` on each raw response and gets back a contract instance that validates per `specs/006-evaluation-contract` → `FR-008`, (d) calls `disconnect()` exactly once at the end.

**Acceptance Scenarios**:

1. **Given** a job whose snapshotted connector identity refers to a connector currently registered in the Connector Registry, **When** the orchestrator starts the job, **Then** it retrieves the connector, decrypts any secret-declared config fields, and invokes `connect()` exactly once with the full plaintext config plus the connection handle is held for the job's duration.
2. **Given** an active connection handle and a Test Case Row, **When** the orchestrator invokes `sendUtterance(handle, utterance, testId, password)`, **Then** the connector receives all three string arguments unmodified and returns a raw response object whose shape is connector-specific (no schema enforced at this boundary).
3. **Given** a raw response from `sendUtterance`, **When** the orchestrator invokes `normalize(rawResponse)`, **Then** the result is a JSON object that validates against the bundled Standard Evaluation Contract schema (`specs/006-evaluation-contract` → `FR-015`), with the connector's declared `connectorId` populated in the contract's `connectorId` field.
4. **Given** the job has reached a terminal state, **When** the orchestrator finishes processing, **Then** it invokes `disconnect(handle)` exactly once and the connection's resources are released. The framework MUST NOT invoke any further interface method on the handle after `disconnect()` returns.

---

### User Story 2 - Add a new chatbot platform without touching the core harness (Priority: P1)

A developer wants to add support for a new chatbot platform (e.g., AWS Bedrock Agent, Anthropic Claude API, a bespoke internal endpoint). They write a class implementing the four-method interface, declare a unique `connectorId`, a display name, and a JSON Schema describing the config fields the connector needs. They call the registry's self-registration affordance. The new connector immediately appears in the wizard's Step 3 picker for any new job; existing connectors and the orchestrator core are untouched. This is the spec's "pluggable" promise made operational.

**Why this priority**: Extensibility is the entire architectural point of having a framework rather than a hard-coded connector. Equal-priority with US1 because both are required for the framework to deliver value.

**Independent Test**: Implement a trivial new connector (e.g., an "EchoConnector" that returns the utterance back unchanged). Register it via the framework's registration mechanism. From a fresh wizard, verify the new connector appears in Step 3's picker, its declared config schema renders correctly, and a job created against it runs end-to-end exactly like a job created against any existing connector — with zero changes to any existing connector module, the registry implementation, or the orchestrator.

**Acceptance Scenarios**:

1. **Given** a new connector class that implements all four interface methods correctly and declares an as-yet-unused `connectorId`, **When** the connector self-registers, **Then** subsequent calls to the registry's "list all connectors" affordance include the new connector, and "get connector by id" with the new id returns it.
2. **Given** the new connector is registered, **When** the tester opens the wizard's Step 3, **Then** the picker shows the new connector alongside existing ones, with its display name visible.
3. **Given** the tester selects the new connector in the wizard, **When** Step 3's config form renders, **Then** the rendered fields match the connector's declared JSON Schema exactly (required fields marked, types respected, secret fields recognized as such per `specs/003-job-creation-wizard` → `FR-008` and the encryption story).
4. **Given** an EchoConnector that has been added without modifying any other connector, registry, or orchestrator file, **When** a job runs end-to-end using EchoConnector, **Then** the job completes and rows persist with EchoConnector's `connectorId` in the contract — proving the zero-core-change extensibility property.

---

### User Story 3 - Protect secret connector config fields at rest (Priority: P2)

A connector requires an API key or auth token to talk to its target chatbot. The tester enters that secret during Step 3 of the wizard. The framework persists it to the job's config snapshot in encrypted form (using a machine-local symmetric key). The detail view (`specs/004`) sees only a fully-masked placeholder. The export (`specs/005`) sees only a fully-masked placeholder. When the orchestrator needs to call `connect()` for that job, the framework decrypts the value in memory just-in-time and passes the plaintext to the connector. After the job ends, the plaintext is dropped; the encrypted form remains on disk only.

**Why this priority**: Secret handling is what makes the connector framework safe to ship beyond a single tester's laptop (and useful even on that laptop — leaked API keys are leaked API keys). Lower than US1/US2 because the framework would technically work without encryption — just unsafely.

**Independent Test**: With a connector whose config declares one secret-typed field, create a job entering a known secret value (e.g., `"SUPER-SECRET-12345"`). Verify (a) the value never appears in the SQLite database file in plaintext (grep the file after creation), (b) the detail view shows the masked placeholder, (c) the export contains the masked placeholder, (d) the orchestrator's actual call to `connect()` receives the plaintext value (verifiable via a debug instrumentation on the connector).

**Acceptance Scenarios**:

1. **Given** a connector whose declared config schema marks one field as secret (per its JSON Schema metadata), **When** the tester enters a value during the wizard's Step 3 and advances past it, **Then** the value persisted to the job's config snapshot in the database is encrypted using the harness's machine-local symmetric key.
2. **Given** a job whose snapshotted config contains an encrypted secret field, **When** the detail view renders the Job Metadata Panel (per `specs/004-job-detail-view` → `FR-005`), **Then** the field shows as a fully-masked placeholder; the plaintext is not in the rendered HTML / DOM.
3. **Given** the same job, **When** the tester downloads any export format (per `specs/005-results-export` → `FR-011`), **Then** the export's `connectorConfig` block shows the field as fully masked; the plaintext is not anywhere in the export file.
4. **Given** the orchestrator picks up the job to run, **When** it invokes `connect()`, **Then** the framework decrypts the secret in memory and passes the plaintext to the connector's `connect()` call; the decrypted value is held only for the duration of the connection (released on `disconnect()`).
5. **Given** the harness installation directory is moved to a different machine without migrating the machine-local key, **When** the harness attempts to decrypt the secret, **Then** decryption fails with an actionable error naming "machine-local key missing or wrong"; the secret is NOT recoverable from the database file alone.

---

### User Story 4 - Use the bundled MockConnector for harness self-test (Priority: P2)

The framework ships with a reference MockConnector that accepts any utterance and returns a canned response. Test authors building any harness component (the dashboard, the detail view, the export service) can configure a job to use MockConnector, run the job, and exercise their component without needing a real chatbot endpoint, real credentials, or network connectivity. MockConnector also serves as the canonical "how to implement a connector" example for new connector authors.

**Why this priority**: Without a reference implementation, every test of the harness needs either a real connector or a hand-rolled mock, which is friction. Equal-priority with US3 because both are productivity multipliers on top of US1/US2.

**Independent Test**: Without configuring any real connector, create a job in the wizard, select MockConnector, fill in its config form (which is intentionally minimal), and start the job. Verify the job runs to completion, produces persisted rows, validates against the contract, and exercises every harness surface (dashboard, detail view, export) end-to-end.

**Acceptance Scenarios**:

1. **Given** a fresh harness install with no real connectors registered, **When** the tester opens the wizard, **Then** MockConnector appears in Step 3's picker as a fully-functional choice.
2. **Given** MockConnector is selected, **When** the wizard renders Step 3's config form, **Then** the form is minimal but valid (e.g., a single optional "canned response" field; no required secrets); Step 3 can be advanced past with zero config entered.
3. **Given** a job running against MockConnector, **When** `sendUtterance` is invoked with any utterance, **Then** MockConnector returns a deterministic canned response (default: a short fixed string acknowledging the utterance; configurable via the optional config field).
4. **Given** MockConnector is in use, **When** `normalize` is invoked, **Then** the resulting contract instance validates against the bundled Standard Evaluation Contract schema and contains MockConnector's declared `connectorId`.

---

### Edge Cases

- A connector implementation is missing one of the four interface methods — registration MUST fail with a clear error naming the missing method; the connector MUST NOT be reachable from the registry.
- Two connectors attempt to register with the same `connectorId` — registration of the second one MUST fail with a clear collision error; the first MUST remain registered unchanged.
- A connector's `connect()` raises an exception (network failure, bad config, etc.) — the orchestrator MUST treat this as a per-job-level connector failure, mark the job's status `failed`, and the framework MUST NOT attempt `sendUtterance` for any row.
- A connector's `sendUtterance()` raises an exception for one row — the orchestrator MUST treat this as a per-row connector failure (per parent `FR-016`, `FR-017`); the connection handle MUST remain valid for subsequent rows (the framework MUST NOT auto-reconnect or auto-disconnect mid-job).
- A connector's `normalize()` raises an exception or returns an object that fails Standard Evaluation Contract validation — the orchestrator MUST record the per-row failure with stage `normalization` (per `specs/006-evaluation-contract` → `FR-009`); subsequent rows proceed.
- A connector's `disconnect()` raises an exception — the failure MUST be captured in the harness's logs but MUST NOT alter the job's terminal status (which is determined by the row outcomes, not by disconnect cleanliness).
- A connector is unregistered (e.g., removed from the harness install) between when a job was created and when the orchestrator picks it up — the orchestrator MUST detect this at startup, mark the job as `failed` with a clear error naming the missing connector, and MUST NOT proceed (this is the runtime mirror of the wizard's Step 5 unavailability check in `specs/003-job-creation-wizard` → `FR-016`).
- A connector's declared config JSON Schema is invalid (cannot be used to render a form, cannot be used to validate input) — registration MUST fail with a clear error naming the schema problem; the connector MUST NOT be reachable.
- A connector's config snapshot includes an encrypted secret whose ciphertext cannot be decrypted (key rotated without re-encrypt, file moved to a new machine) — the orchestrator MUST treat this as a connector-config failure, mark the job `failed` with the actionable "machine-local key missing or wrong" message, and MUST NOT attempt `connect()`.
- The machine-local key file is missing entirely on a fresh install — the framework MUST generate one on first use, store it in its plan-defined location, and protect it with OS-appropriate permissions (this is the bootstrapping path; the spec only requires that the key exists by the time the first secret needs to be persisted).
- Two jobs run concurrently and both use the same connector — each job MUST have its own `ConnectionHandle` (its own `connect()` call); the framework MUST NOT share handles across jobs (per `FR-007`).
- The MockConnector is used in a job that exercises the encryption story — MockConnector's config schema MAY include an optional secret-declared field purely for testing the encryption path; in v1 it does not require one.

## Requirements *(mandatory)*

### Functional Requirements

#### Connector Interface

- **FR-001**: The framework MUST define a Connector Interface that every chatbot connector MUST implement. The interface MUST consist of exactly four behavioral methods: `connect`, `sendUtterance`, `normalize`, `disconnect` (the literal language-binding shape — class vs. functions, async vs. sync, type-annotation style — is plan-level).
- **FR-002**: `connect(config)` MUST accept the connector's declared configuration (a plain object whose shape matches the connector's published JSON Schema, with secret fields already decrypted) and MUST return a `ConnectionHandle` — an opaque value that subsequent `sendUtterance` / `disconnect` calls reference. `connect` MUST raise (or return a clearly-typed error) if the configuration is invalid or if the target chatbot cannot be reached with the provided config.
- **FR-003**: `sendUtterance(handle, utterance, testId, password)` MUST accept an active connection handle, a single utterance string, a `testId` string, and a `password` string (the per-row CSV credentials passed through unmodified per parent `FR-006`). It MUST return a `RawResponse` — an opaque value whose internal shape is connector-specific and is NOT constrained by the Standard Evaluation Contract.
- **FR-004**: `normalize(rawResponse)` MUST accept a raw response previously returned by `sendUtterance` and MUST return a JSON object that conforms to the Standard Evaluation Contract (per `specs/006-evaluation-contract`). The connector MUST populate at minimum every required field defined in `specs/006-evaluation-contract` → `FR-002` and `FR-003`, including a `connectorId` value that matches the connector's declared id.
- **FR-005**: `disconnect(handle)` MUST tear down the connection identified by the handle and release any resources. After `disconnect` returns, the framework MUST NOT invoke any further interface method on the handle.
- **FR-006**: The framework MUST invoke `connect()` exactly once per job, before any `sendUtterance` call for that job, and MUST invoke `disconnect()` exactly once per job, after the last `sendUtterance` of that job (whether the job ends via `completed`, `failed`, or `cancelled`). The same `ConnectionHandle` MUST be reused across every row of the job. The framework MUST NOT issue mid-job `connect()` / `disconnect()` calls; recoverable session expiry is the connector's internal concern.
- **FR-007**: Concurrent jobs (per parent `FR-011`) MUST receive independent connection handles — even when they reference the same connector, each job's `connect()` call is its own; handles MUST NOT be shared across jobs.
- **FR-007a**: Within a single job, the framework MUST serialize `sendUtterance` calls on the same `ConnectionHandle` — at most one call MAY be in flight at any moment. Connector authors MUST NOT be required to make their handles thread-safe or async-safe. This pins parent's "max concurrent in-flight rows per job" tuning value to **1** for v1. Cross-job parallelism is unaffected (each job has its own handle per `FR-007`).

#### Connector Registry

- **FR-008**: The framework MUST provide a **Connector Registry** — a service that maintains a catalog of all currently-registered connectors. The registry MUST be the single source of truth for "which connectors does this harness installation know about?"
- **FR-009**: Each connector MUST self-register with the registry. Registration MUST require the connector to supply: (a) a unique `connectorId` string, (b) a human-readable display name, (c) a JSON Schema describing the connector's configuration fields (including which are required and which are secret), and (d) a handle or factory by which the framework can obtain an instance to invoke interface methods on. `connectorId` is the **sole identity** in v1 — there is no separate connector-version field; if a connector needs to coexist with a predecessor variant, the convention is to bake the version into the id (e.g., `ms-copilot-studio-v1` vs. `ms-copilot-studio-v2`), and the registry treats the resulting ids as wholly distinct.
- **FR-010**: The registry MUST reject duplicate `connectorId` registration with an actionable error; the first-registered connector for a given id MUST remain in place.
- **FR-011**: The registry MUST reject registration when (a) the supplied JSON Schema is invalid (cannot be parsed or used to validate input), (b) any of the four interface methods is missing from the supplied implementation handle, (c) `connectorId` is empty or already in use.
- **FR-012**: The registry MUST expose at minimum the following query affordances to callers in the harness: (a) **list all registered connectors** (returning at least each connector's id, display name), (b) **retrieve a connector by id** (returning enough to invoke the interface methods on it, or an explicit "not found" result), (c) **retrieve the configuration schema for a given connector id** (so the wizard's Step 3 form can render — per `specs/003-job-creation-wizard` → `FR-008`).
- **FR-013**: The registry MUST be queryable by both the wizard (at job-creation time) and the orchestrator (at job-execution time); both surfaces MUST see the same set of registered connectors at any given moment.
- **FR-014**: The framework MUST support adding new connectors **without modifying** the core harness code, the registry implementation, the orchestrator, the wizard, the dashboard, the detail view, the export service, the contract, or any other existing connector. The discovery / loading mechanism by which a new connector reaches the registry is plan-level (e.g., Python entry points, file-system scan of a known directory, manifest file); the spec requires only that the operation is zero-touch on existing modules.

#### Secret Encryption Utility

- **FR-015**: The framework MUST provide a utility for symmetric encryption and decryption of configuration field values. The utility MUST be used by the wizard (or the orchestrator) to encrypt any config field declared `secret` in a connector's JSON Schema before that value is persisted to the database. The utility MUST be used by the orchestrator to decrypt those same fields just before invoking `connect()`. (This formalizes parent `FR-023a`.)
- **FR-016**: The encryption utility MUST use symmetric cryptography with a key that is **machine-local** — i.e., stored on the host machine in a way that another machine cannot trivially obtain it. Plan-level concerns include: key file location, file-system permissions, generation on first use, rotation policy. The spec requires only that (a) the key is not in the SQLite database file, (b) the key is not in source control, and (c) copying just the database file to another machine MUST NOT yield the underlying secrets.
- **FR-017**: Decrypted plaintext MUST exist only in memory and only for the duration it's needed — held during the active `connect()` call and released no later than `disconnect()`. Decrypted plaintext MUST NEVER appear in UI rendering (per `specs/004-job-detail-view` → `FR-005`), in any export (per `specs/005-results-export` → `FR-011`), or in application logs.
- **FR-018**: When decryption fails (e.g., key missing, ciphertext corrupt, key mismatch from a moved installation), the framework MUST surface an actionable error including a remediation hint ("machine-local key missing or wrong"). The owning job MUST transition to `failed` and MUST NOT attempt to proceed with the connector.
- **FR-019**: The per-row CSV `password` (the parameter to `sendUtterance` per `FR-003`) is **NOT** within the encryption utility's scope. It remains in-memory only, never persisted, per parent `FR-010`. The utility encrypts config-level secrets only.

#### MockConnector reference implementation

- **FR-020**: The framework MUST ship a **MockConnector** reference implementation. MockConnector MUST be registered in the Connector Registry by default in a stock harness installation (no extra setup required by the tester).
- **FR-021**: MockConnector MUST implement all four interface methods correctly and emit a Standard-Evaluation-Contract-conformant instance from `normalize()`. Its declared `connectorId` MUST be unambiguously identifiable as the mock (e.g., `"mock"`).
- **FR-022**: MockConnector's `sendUtterance()` MUST return a deterministic canned response — by default a short fixed acknowledgement of the utterance; optionally configurable via a non-secret field in MockConnector's config schema.
- **FR-023**: MockConnector's config schema MUST have no required fields, so the wizard's Step 3 can be advanced past with zero tester input. Optional fields (e.g., the "canned response" field) MAY be declared.
- **FR-024**: MockConnector MUST be safe to use in unit, integration, and end-to-end tests of every other harness module without requiring network access, external credentials, or any out-of-process dependency.

### Key Entities *(include if feature involves data)*

- **Connector**: An implementation of the four-method interface that talks to one specific chatbot platform. Carries: `connectorId` (unique string), display name (human-readable), config JSON Schema (with secret-field annotations), implementation handle. Self-registers with the Connector Registry. Snapshotted (identity + config) onto the Test Job at job-creation time (parent `FR-023`).
- **Connector Registry**: The catalog of all currently-registered connectors in the harness installation. In-process service; queryable by id or as a list; returns config schemas for UI rendering. The Single Source of Truth for "what can I pick?" in the wizard and "what can I invoke?" in the orchestrator.
- **ConnectionHandle**: An opaque per-job-per-connector reference returned by `connect()` and consumed by `sendUtterance` / `disconnect`. Its internal shape is connector-specific and is not introspected by the framework. Lifecycle: created once at job start, destroyed once at job end, reused for every row in between.
- **RawResponse**: An opaque per-row connector output produced by `sendUtterance` and consumed by `normalize`. Its internal shape is connector-specific; only `normalize`'s output is constrained by the Standard Evaluation Contract.
- **Secret Encryption Key**: A symmetric key stored machine-locally, used by the encryption utility to encrypt config-level secret fields before persistence and decrypt them just-in-time for `connect()` calls. NOT in the database file, NOT in source control. Generation and rotation are plan-level.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A job using a registered connector runs end-to-end and produces persisted rows whose contract instances validate against the bundled Standard Evaluation Contract schema — verifiable by running an end-to-end test against MockConnector and inspecting every row's persisted contract.
- **SC-002**: Adding a brand-new connector requires **zero modifications** to any existing file outside of (a) the new connector's own module and (b) the registration manifest (or equivalent plan-defined registration mechanism) — verifiable by `git diff` showing the change set is entirely additive on existing files.
- **SC-003**: The Connector Registry's "list all" and "get by id" affordances return the same set of connectors regardless of which harness surface (wizard, orchestrator) is doing the asking — verifiable by querying from both surfaces simultaneously in a test.
- **SC-004**: A connector whose declared config schema marks at least one field as secret produces a job whose database row, exported file, and detail-view rendering all show that field's plaintext value **nowhere** — verifiable by inserting a known-distinctive secret value (e.g., `"DEADBEEF-12345"`) and grepping the database file, the export file, and the rendered detail page for that exact string (must produce zero matches).
- **SC-005**: A copy of the database file moved to a different machine (without the machine-local key) cannot be used to recover any previously-stored secret — verifiable by copying the file to a clean machine and attempting decryption.
- **SC-006**: `connect()` is invoked exactly once per job and `disconnect()` is invoked exactly once per job, regardless of the job's terminal status (completed, failed, or cancelled) and regardless of how many rows the job has — verifiable by instrumenting MockConnector to count calls.
- **SC-007**: Two concurrent jobs using the same connector hold independent connection handles — verifiable by enqueuing two simultaneous jobs against MockConnector, instrumented to record handle identity, and asserting the two handles are not equal.
- **SC-008**: A connector implementation missing any of the four interface methods fails to register; the registry's "list all" output never includes it — verifiable by attempting to register a deliberately incomplete connector and observing the error.
- **SC-009**: A connector whose `sendUtterance()` raises for one row does NOT cause the job to abort; remaining rows proceed and the failing row is recorded as `failed` with stage `connector` (per parent `FR-017`) — verifiable by a test where MockConnector is configured to throw on row 2 of a 5-row job.
- **SC-010**: A `normalize()` output that fails Standard-Evaluation-Contract validation results in the row being recorded with stage `normalization` (per `specs/006-evaluation-contract` → `FR-009`); subsequent rows proceed — verifiable by a test where MockConnector is configured to emit a non-conformant instance on row 3 of a 5-row job.
- **SC-011**: MockConnector is usable in a brand-new harness install with zero additional setup — verifiable by clean-install testing through the wizard.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth, no `createdBy` anywhere.
- The Standard Evaluation Contract (the canonical schema connectors produce instances of) is fully defined in `specs/006-evaluation-contract/spec.md`. This spec depends on it but does not redefine it.
- The wizard's Step 3 (`specs/003-job-creation-wizard` → `FR-007`, `FR-008`, `FR-009`, `FR-010`) consumes the registry's "list" and "get config schema" affordances. The wizard does NOT introspect connector internals beyond what those affordances expose.
- The orchestrator (Module 10, TBD) consumes the registry's "get by id" affordance plus the four interface methods. It does NOT introspect connector internals beyond that.
- The framework's connector discovery / loading mechanism (Python entry points vs. file-system scan vs. manifest file vs. import hook) is a plan-level decision. The spec requires only the zero-touch-on-existing-modules property.
- Key management for the encryption utility (key location, generation, rotation, OS-level permissions) is a plan-level decision. The spec requires only the machine-local + not-in-DB + not-in-source-control properties.
- Connector-internal retry logic (whether a connector retries an internal HTTP call on a transient failure before raising) is a connector-implementation concern; the framework MUST NOT retry at the orchestrator layer (per parent `FR-025`).
- "Adding a new connector requires zero changes to the core harness" is a structural property of the codebase, not a runtime property. Verified by review / `git diff`, not by runtime introspection.
- MockConnector is intended for harness self-test and as a reference example. It is NOT intended to be used against real chatbot endpoints (it does no I/O).
- The interface method signature `sendUtterance(handle, utterance, testId, password)` exposes `password` as a parameter, consistent with parent `FR-006`. The connector is free to use it (for chatbot-target authentication) or ignore it; the framework neither inspects nor logs it.
