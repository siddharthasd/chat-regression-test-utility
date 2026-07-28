# Feature Specification: Connector Framework (Module 4)

**Feature Branch**: `007-connector-framework`

**Created**: 2026-05-28

**Last Amended**: 2026-05-29

**Status**: Draft

**Input** *(verbatim original; superseded 2026-05-29 by the remote-HTTP-service reshape — see Clarifications "Session 2026-05-29 (Reshape)" and `FR-001`–`FR-006` for the current model)*: User description: "Module 4 — Connector Framework. A pluggable connector framework with four interface methods (`connect`, `sendUtterance`, `normalize`, `disconnect`), a connector registry that connectors self-register against with a unique id + display name + configuration schema, an encryption/decryption utility for secret config fields, and a MockConnector reference implementation. Adding a new connector requires implementing the interface and registering — zero changes to the core harness."

> **Parent context**: This module defines the **wire protocol and generic HTTP client** by which the harness talks to chatbot **connector services**. Per the architectural decision recorded on 2026-05-29, connectors are no longer in-process Python plugins — they are **remote HTTP services** hosted outside the harness, each one specific to a single chatbot under test (and teams may stand up additional connector services pointing at the underlying agents of a top-level chatbot to regress those independently). The harness is a thin orchestration client that calls those services per the protocol defined here. Connectors fulfill the parent harness's `FR-006` (forward utterance/`testId`/`password` to the selected connector) and `FR-007` (receive a Standard Evaluation Contract instance back from the connector — the contract is now produced by the remote connector service, not by an in-process `normalize()` step). The CRUD lifecycle of registered connector endpoints (create, edit, delete, list) lives in the new `specs/013-connector-registry-management` module; this spec covers only the wire protocol, the generic HTTP client behavior, and the bundled mock connector service. The wizard's Step 3 (`specs/003-job-creation-wizard`) consumes the registry's "list" affordance to render a dropdown of registered connectors. The encryption utility introduced here formalizes the harness-wide rule added in parent `FR-023a` (config-level secret-encryption-at-rest with a machine-local key) and is used by `013` to encrypt stored auth credentials. Parent-spec premises apply: single-user, no auth on the harness UI. The framework / registry itself carry no `createdBy` field; parent `FR-026`'s OS-derived `Job.createdBy` (and `Job.connectorName`, snapshotted verbatim from the selected registration's `displayName` per `003 FR-009`) live on the Job snapshot.

## Clarifications

### Session 2026-05-28

- Q: The encryption utility "for the password field" — what does it encrypt? → A: **Stored connector auth credentials only** (formerly framed as "config-level secret fields"). The per-row CSV `password` (parent `FR-010`) is NOT touched by this utility — it remains in-memory only, never persisted at rest. Parent spec was amended in lock-step (new parent `FR-023a`) to formalize the harness-wide rule.
- Q: When does the harness connect and disconnect across the rows of a job? → A: **Superseded 2026-05-29.** The remote-service reshape eliminates `connect`/`disconnect` entirely. Each row is a single, stateless HTTP request. The previous answer ("once per job, with a reused ConnectionHandle") is obsolete.

### Session 2026-05-28 (Round 2)

- Q: Do connectors carry a separate version field, or is `connectorId` the sole identity? → A: **`connectorId` is the sole identity in v1; no separate version field.** When a connector evolves and needs to coexist with its predecessor, the convention is to bake the version into the id (e.g., `ms-copilot-studio-v1`, `ms-copilot-studio-v2`). The registry treats those as wholly distinct connectors with no relationship between them.
- Q: Can the orchestrator call the connector concurrently for the same job? → A: **No — harness serializes per job in v1.** The harness MUST guarantee that, for any given job, at most one connector HTTP call is in flight at a time. Within a single job, rows are dispatched one at a time. Cross-job parallelism (multiple jobs running concurrently per parent `FR-011`) is allowed because each job dispatches independently. This locks the parent spec's "max concurrent in-flight rows per job" assumption to **1** for v1.

### Session 2026-05-29 (Reshape)

- Q: Are connectors in-process Python plugins (4-method interface, self-registration) or remote HTTP services (wire protocol, CRUD-managed registry)? → A: **Remote HTTP services.** Each chatbot under test (and each independently-testable underlying agent) is fronted by its own connector service. The harness ships a generic HTTP client; the wire protocol is single-endpoint, single-shot per utterance; the connector service is responsible for normalizing its native chatbot response into a Standard Evaluation Contract instance before returning. CRUD over registered connector endpoints lives in `specs/013`.
- Q: What auth modes does the harness support when calling registered connector endpoints? → A: **Four modes:** `none`, `bearer` (Authorization: Bearer <token>), `api-key-header` (tester-named header + tester-supplied value), `basic` (Authorization: Basic <base64 user:pass>). Anything more exotic is on the tester to wrap server-side.
- Q: Does the connector service handle the per-row CSV password? → A: **Only if the registered connector declares that it expects one.** Each `ConnectorRegistration` carries an `expectsPerRowPassword` boolean (managed in `013`). When true, the harness forwards the per-row password in the HTTP body; when false, the password field is omitted from the request and the CSV upload module (`011`) treats the password column as optional for jobs targeting that connector.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a job through a registered connector service end-to-end (Priority: P1)

The harness orchestrator picks up a queued job, looks up the job's snapshotted connector endpoint (URL, auth descriptor, timeout, expects-per-row-password flag) from the Job's snapshot, and for every row issues a single HTTP `POST` to the registered endpoint carrying the row's `testId`, `utteranceText`, and (if the connector expects it) the per-row `password`. The connector service responds with a fully-normalized Standard Evaluation Contract instance, which the harness forwards directly to the evaluator service (per `012`'s per-row pipeline). This is the integration that makes the remote-connector architecture real.

**Why this priority**: Without this story, no real chatbot ever gets talked to. It is the MVP slice of Module 4.

**Independent Test**: With a registered connector endpoint (e.g., the bundled mock connector service running on localhost), enqueue a 3-row job. Verify the harness issues exactly three HTTP `POST` calls in row order, with the correct auth header and body for each, receives three contract-conformant JSON responses, and forwards each to the next pipeline step. No `connect`/`disconnect` calls. No retries. No mid-job state.

**Acceptance Scenarios**:

1. **Given** a job whose snapshotted connector identity refers to an active (non-archived) `ConnectorRegistration`, **When** the orchestrator starts the job, **Then** it resolves the registration to its endpoint URL, auth descriptor, timeout, and expects-per-row-password flag from the Job's snapshot (per parent `FR-023`) — NOT from the live registry, so post-registration edits do not affect already-snapshotted jobs.
2. **Given** an active endpoint resolution and an Utterance, **When** the orchestrator dispatches the row, **Then** the harness issues a single `POST` to the endpoint URL with the auth header constructed per the auth descriptor (decrypting the stored credential just-in-time), `Content-Type: application/json`, and a body of `{"testId": "...", "utteranceText": "..."}` (with `"password": "..."` included if and only if the registration's `expectsPerRowPassword` is true).
3. **Given** a successful HTTP response with status 200 and a JSON body, **When** the harness receives the response, **Then** the body MUST validate against the bundled Standard Evaluation Contract schema (`specs/006-evaluation-contract` → `FR-008`/`FR-015`) with the connector's `connectorId` populated; if it does not validate, the row MUST be recorded with `errorStage = connector_normalization` (per `006 FR-009`).
4. **Given** any of the rows finishes, **When** the orchestrator moves to the next row, **Then** it issues a wholly independent HTTP `POST` — no session, no keep-alive guarantee at the protocol level, no shared state between rows.
5. **Given** the connector's response body has been validated against the Standard Evaluation Contract schema (per `006 FR-008`), **When** the orchestrator advances to the next pipeline step, **Then** the validated contract instance is forwarded as the HTTP request body to the evaluator service (per `008 FR-002` and `012 FR-011` step 5); the harness performs no additional in-process normalization or transformation on the contract between receipt from the connector and forwarding to the evaluator.

---

### User Story 2 - Add support for a new chatbot platform by hosting a new connector service (Priority: P1)

A developer (or tester capable of standing up an HTTP service) wants to add support for a new chatbot platform — e.g., AWS Bedrock Agent, Anthropic Claude API, a bespoke internal chatbot, or one of the underlying agents of a composite chat application. They build a service that implements the connector wire protocol defined in this spec, host it at a reachable URL, and register the endpoint in the Connector Registry via `specs/013`'s CRUD UI. The new connector immediately appears in the wizard's Step 3 dropdown for any new job; **zero code changes** to the harness are required.

**Why this priority**: Extensibility is the entire architectural point of the framework. Equal-priority with US1 because both are required for the framework to deliver value.

**Independent Test**: Stand up a trivial new connector service (e.g., an "EchoConnector" service that returns a canned Standard Evaluation Contract instance reflecting the incoming utterance). Register its endpoint in `013`. From a fresh wizard, verify the new connector appears in Step 3's dropdown with the human-readable name supplied at registration, and a job created against it runs end-to-end exactly like a job created against any existing connector — with zero changes to the harness codebase.

**Acceptance Scenarios**:

1. **Given** a connector service hosted at a reachable URL whose responses conform to the wire protocol (request schema accepted, response is a Standard Evaluation Contract instance), **When** the tester registers it via `013`, **Then** subsequent calls to the registry's "list active connectors" affordance include it and "get by id" returns its endpoint + auth descriptor + timeout + expects-per-row-password flag.
2. **Given** the new connector is registered (not archived), **When** the tester opens the wizard's Step 3, **Then** the dropdown shows the new connector alongside existing ones, ordered per `003`'s display rules.
3. **Given** the tester selects the new connector in the wizard, **When** the wizard finalizes Step 3 via Next, **Then** the wizard snapshots the full registration onto the Draft Job per `003 FR-009` — including the registration's `displayName` as `Job.connectorName` (verbatim snapshot; not tester-editable in the wizard post-2026-05-29-reshape). No per-job config form is rendered, because all connector configuration (endpoint, auth, timeout, expects-per-row-password) lives on the registration, not the job.
4. **Given** an EchoConnector service that has been registered without modifying any harness code, **When** a job runs end-to-end against it, **Then** the job completes and rows persist with EchoConnector's `connectorId` in the contract — proving the zero-core-change extensibility property.

---

### User Story 3 - Protect stored connector auth credentials at rest (Priority: P2)

A registered connector requires an auth credential (bearer token, API key value, basic auth password) to talk to its target chatbot. The tester enters that credential during connector registration in `013`. The framework persists it to the database in encrypted form using a machine-local symmetric key. The detail view (`004`) and any registry list/edit UI see only a fully-masked placeholder. The export (`005`) sees only a fully-masked placeholder. When the orchestrator needs to call the connector for a job, the framework decrypts the value in memory just-in-time, constructs the auth header, makes the HTTP request, and drops the plaintext after the request completes.

**Why this priority**: Credential handling is what makes the connector registry safe to use beyond a single tester's laptop (and useful even on that laptop — leaked tokens are leaked tokens). Lower than US1/US2 because the framework would technically work without encryption — just unsafely.

**Independent Test**: Register a connector whose auth descriptor specifies `bearer` mode with a known-distinctive token value (e.g., `"SUPER-SECRET-12345"`). Verify (a) the value never appears in the SQLite database file in plaintext (grep the file after creation), (b) the registry's edit form and the job detail view show a fully-masked placeholder, (c) any export contains the masked placeholder, (d) the harness's actual HTTP call to the connector carries the correct `Authorization: Bearer SUPER-SECRET-12345` header (verifiable via a debug-instrumented mock connector service).

**Acceptance Scenarios**:

1. **Given** a tester registers a connector with an auth credential, **When** the registration is saved, **Then** the credential persisted to the database is encrypted using the harness's machine-local symmetric key; the plaintext is not anywhere in the SQLite file.
2. **Given** a Job that snapshotted a registered connector with an encrypted credential, **When** the detail view renders the Job Metadata Panel (per `004 FR-005`), **Then** the credential shows as a fully-masked placeholder; the plaintext is not in the rendered HTML / DOM.
3. **Given** the same job, **When** the tester downloads any export format (per `005 FR-011`), **Then** the snapshotted `connectorAuthDescriptor` in the export shows the credential subfield as fully masked; the plaintext is not anywhere in the export file.
4. **Given** the orchestrator dispatches a row to that connector, **When** the harness constructs the HTTP request, **Then** the framework decrypts the credential in memory, builds the auth header per the descriptor's mode, sends the request, and discards the plaintext no later than when the HTTP response is received.
5. **Given** the harness installation directory is moved to a different machine without migrating the machine-local key, **When** the harness attempts to decrypt a stored credential, **Then** decryption fails with an actionable error naming "machine-local key missing or wrong"; the credential is NOT recoverable from the database file alone.

---

### User Story 4 - Use the bundled mock connector service for harness self-test (Priority: P2)

The harness ships with a **bundled mock connector service** — a small stub HTTP server the tester can spin up locally (or that the harness can launch as a child process for self-tests). The mock connector accepts any utterance and returns a deterministic Standard Evaluation Contract instance. Test authors building any harness component (the dashboard, the detail view, the export service) can register the mock connector's local URL, create a job against it, and exercise their component without needing a real chatbot endpoint, real credentials, or external network connectivity. The mock connector also serves as the canonical "minimum viable connector service" reference for new connector authors.

**Why this priority**: Without a reference implementation, every test of the harness needs either a real connector or a hand-rolled stub, which is friction. Equal-priority with US3 because both are productivity multipliers on top of US1/US2.

**Independent Test**: Without registering any real connector, launch the bundled mock connector service, register its local URL in `013`, create a job against it in the wizard, and start the job. Verify the job runs to completion, produces persisted rows whose contracts validate against the bundled schema, and exercises every harness surface (dashboard, detail view, export) end-to-end.

**Acceptance Scenarios**:

1. **Given** a fresh harness install, **When** the tester runs the documented "launch bundled mock connector" command (or the harness's self-test launches it as a child process), **Then** a local HTTP server starts on a plan-defined port and accepts requests conforming to the connector wire protocol.
2. **Given** the mock connector is running, **When** the tester registers its URL in `013` (auth mode `none`, expects-per-row-password `false`), **Then** the registration succeeds and the mock connector appears in the wizard's Step 3 dropdown.
3. **Given** a job running against the mock connector, **When** the harness POSTs an utterance to it, **Then** the mock returns a deterministic Standard Evaluation Contract instance (with the mock's declared `connectorId`, e.g., `"mock"`, populated correctly) within a short, bounded response time.
4. **Given** the mock connector is in use, **When** the harness validates the response against the Standard Evaluation Contract schema, **Then** the validation passes.

---

### Edge Cases

- A registered connector's endpoint URL is unreachable when a row is dispatched (DNS failure, connection refused, TLS handshake failure) — the row MUST be recorded with `errorStage = connector_transport` (per `006 FR-009`); the connection failure MUST NOT cause the job to abort; subsequent rows proceed and may succeed or fail independently.
- The connector service returns a non-2xx HTTP status — the row MUST be recorded with `errorStage = connector_response`; the response body (truncated to a plan-defined byte limit) MUST be captured in `errorDetails` for diagnosis; subsequent rows proceed.
- The connector service returns a 2xx HTTP status but the response body is not valid JSON, OR is valid JSON but fails Standard Evaluation Contract validation — the row MUST be recorded with `errorStage = connector_normalization`; the offending body (truncated) MUST be captured in `errorDetails`; subsequent rows proceed.
- The connector service does not respond within the registered `timeoutSeconds` — the harness MUST abort the HTTP call locally; the row MUST be recorded with `errorStage = connector_transport` with a clear "timeout exceeded" detail; subsequent rows proceed. The harness MUST NOT retry.
- The job's snapshotted connector points to a `ConnectorRegistration` that has since been hard-deleted from the registry — because the Job carries a full snapshot of endpoint + auth descriptor + timeout (per parent `FR-023` and `009 FR-001a`), the orchestrator MUST still be able to dispatch rows using the snapshot. (Note: hard-delete of a registration referenced by historical jobs is gated by `013 FR-019`, so this case cannot occur in normal operation; the snapshot-self-sufficiency property is a defensive guarantee for the case where the gate is somehow bypassed.)
- The job's snapshotted connector points to an `archived` (soft-deleted) registration — the orchestrator MUST dispatch rows normally using the snapshot; archival affects only the wizard's dropdown selectability, not historical job execution.
- Two jobs run concurrently and both target the same registered connector — each job dispatches its own HTTP requests independently; there is no shared state between jobs at the protocol level. The connector service is responsible for handling concurrent inbound requests.
- A registered connector's stored auth credential cannot be decrypted (key rotated without re-encrypt, file moved to a new machine) — the row MUST be recorded with `errorStage = connector_auth` and the actionable "machine-local key missing or wrong" message; subsequent rows MAY fail the same way if the credential is shared; the job's terminal status is determined by per-row outcomes per parent `FR-016` / `FR-017`.
- The machine-local key file is missing entirely on a fresh install — the framework MUST generate one on first use, store it in its plan-defined location, and protect it with OS-appropriate permissions.
- The connector service responds with a contract whose `connectorId` field differs from the registered `connectorId` — the harness MUST trust the wire response's `connectorId` value (it is the connector service's authoritative self-identification) but MUST log a warning naming the mismatch for diagnosis. This does NOT fail the row.
- The wizard's Step 3 dropdown is empty because no connectors have been registered yet — the wizard MUST surface a clear affordance directing the tester to `specs/013` to register one before continuing (per `003`'s amendments).

## Requirements *(mandatory)*

### Functional Requirements

#### Connector Wire Protocol

- **FR-001**: The framework MUST define a **Connector Wire Protocol** — a single-endpoint HTTP contract that every chatbot connector service MUST honor. The protocol is single-shot per utterance: one row = one request = one response. There is no session, no `connect`/`disconnect`, no streaming in v1.
- **FR-002**: A connector request MUST be an HTTP `POST` to the connector's registered endpoint URL with `Content-Type: application/json` and a JSON body of the form `{"testId": <string>, "utteranceText": <string>, "password": <string-or-omitted>}`. The `password` field MUST be present if and only if the connector's `ConnectorRegistration.expectsPerRowPassword` is `true`; otherwise it MUST be omitted from the body entirely (not sent as `null`, not sent as empty string).
- **FR-003**: A successful connector response MUST be HTTP 200 with `Content-Type: application/json` and a body that is a single, complete JSON object conforming to the Standard Evaluation Contract schema defined in `specs/006-evaluation-contract`. The connector service is responsible for any chatbot-specific normalization to produce a conformant contract instance; the harness performs no in-process normalization.
- **FR-004**: The harness MUST enforce a per-row response timeout equal to the connector's registered `timeoutSeconds` value. When the timeout is exceeded the harness MUST abort the HTTP call locally and record `errorStage = connector_transport` with a "timeout exceeded" detail. The harness MUST NOT retry the request (per parent `FR-025`).
- **FR-005**: The harness MUST issue connector requests serially within a single job — at most one connector HTTP call MAY be in flight at any moment for a given job. Cross-job parallelism (per parent `FR-011`) is unaffected; concurrent jobs dispatch independently.
- **FR-006**: HTTP-level error categorization in the harness MUST map to the following `errorStage` values from the canonical nine-value enum (per `012 FR-012` / `009 FR-003`; `006 FR-009` is the contract-validation anchor for `connector_normalization` specifically): transport / DNS / TLS / timeout failures → `connector_transport`; non-2xx status responses → `connector_response`; 2xx with invalid JSON or contract-non-conformant body → `connector_normalization`; auth credential decryption failure (before the request is sent) → `connector_auth`.

#### Auth Modes

- **FR-007**: The harness MUST support exactly four auth modes when calling a registered connector endpoint: `none`, `bearer`, `api-key-header`, `basic`. Each registered connector MUST declare exactly one mode.
- **FR-007a**: For mode `none`, the harness MUST send the request with no auth-related headers added by the harness.
- **FR-007b**: For mode `bearer`, the harness MUST send `Authorization: Bearer <token>` where `<token>` is the decrypted credential stored on the registration.
- **FR-007c**: For mode `api-key-header`, the registration MUST carry both a tester-named header name (e.g., `X-Api-Key`) and the credential value; the harness MUST send `<header-name>: <credential-value>`.
- **FR-007d**: For mode `basic`, the registration MUST carry a username and a password value; the harness MUST send `Authorization: Basic <base64(username:password)>`.
- **FR-008**: Any auth mode beyond the four named here is out of scope for v1. Testers needing custom schemes MUST wrap their service in a reverse-proxy that exposes one of the four.

#### Connector Registry (read surface)

- **FR-009**: The framework MUST expose a **Connector Registry read API** that other harness modules query. The registry is the single source of truth for "which connectors does this harness installation know about?" Write operations (create / edit / archive / restore / hard-delete) live in `specs/013`; this spec covers only the read surface.
- **FR-010**: The read API MUST expose at minimum: (a) **list active connectors** — returning at least the minimum tuple `(connectorId, displayName, description, expectsPerRowPassword)` for each entry; consumers needing additional fields (endpoint URL, auth descriptor, timeout) MUST use the get-by-id affordance below. Consumed by the wizard's Step 3 dropdown (per `003 FR-007`); archived registrations MUST NOT appear in this list. (b) **get connector by id** (returning the full registration record: `displayName`, `description`, `endpointUrl`, `authDescriptor` including encrypted credentials, `timeoutSeconds`, `expectsPerRowPassword`, `archived` state, audit timestamps) — consumed by the wizard at job-creation snapshot time (per `003 FR-009`). At execution time the orchestrator (`012 FR-004`) MUST resolve connector configuration from the Job's snapshot per parent `FR-023`, NOT from this live read API.
- **FR-011**: The read API MUST return identical data regardless of which harness surface (wizard, orchestrator, registry-management UI) is calling.
- **FR-012**: The framework MUST support adding new connectors **without modifying** the core harness code, the registry implementation, the orchestrator, the wizard, the dashboard, the detail view, the export service, the contract, or any existing connector. The only operations required are: (a) host an HTTP service that honors the wire protocol, (b) register its endpoint in `013`'s CRUD UI.

#### Stored Credential Encryption Utility

- **FR-013**: The framework MUST provide a utility for symmetric encryption and decryption of stored auth credentials. The utility MUST be used by `013` to encrypt any credential value (bearer token, api-key-header value, basic-auth password) before persisting it. The utility MUST be used by the harness's HTTP client to decrypt those same values just-in-time when constructing an auth header. (This formalizes parent `FR-023a`.)
- **FR-014**: The encryption utility MUST use symmetric cryptography with a key that is **machine-local** — i.e., stored on the host machine in a way that another machine cannot trivially obtain it. Plan-level concerns include: key file location, file-system permissions, generation on first use, rotation policy. The spec requires only that (a) the key is not in the SQLite database file, (b) the key is not in source control, and (c) copying just the database file to another machine MUST NOT yield the underlying credentials.
- **FR-015**: Decrypted plaintext MUST exist only in memory and only for the duration of a single HTTP request — constructed when the auth header is being built, discarded no later than when the HTTP response is received (or the request is aborted). Decrypted plaintext MUST NEVER appear in UI rendering (per `004 FR-005`), in any export (per `005 FR-011`), or in application logs.
- **FR-016**: When decryption fails (e.g., key missing, ciphertext corrupt, key mismatch from a moved installation), the harness MUST surface an actionable error including a remediation hint ("machine-local key missing or wrong"). The owning row MUST transition to `failed` with `errorStage = connector_auth`. Subsequent rows MAY fail the same way if the credential is shared.
- **FR-017**: The per-row CSV `password` (the `password` field of the request body per `FR-002`) is **NOT** within the encryption utility's scope. It remains in-memory only, never persisted, per parent `FR-010` and `011 FR-015`. The utility encrypts stored registration credentials only.

#### Bundled Mock Connector Service

- **FR-018**: The harness MUST ship a **bundled mock connector service** — a stub HTTP server implementing the connector wire protocol, launchable as either a standalone process or as a child process of the harness's self-test runner.
- **FR-019**: The mock connector service MUST emit a Standard-Evaluation-Contract-conformant instance from every successful request, with a `connectorId` value that is unambiguously identifiable as the mock (e.g., `"mock"`).
- **FR-020**: The mock connector's response MUST be deterministic — by default a short fixed acknowledgement reflecting the inbound utterance; the behavior MAY be parameterized via process-level configuration (env vars, command-line flags) for testing edge cases (e.g., emit a non-conformant body, emit a non-2xx status, sleep before responding to test the timeout path).
- **FR-021**: The mock connector MUST be safe to use in unit, integration, and end-to-end tests of every other harness module without requiring external network access or any out-of-process dependency beyond a free local port.
- **FR-022**: The mock connector service MUST require no auth by default (the documented quickstart registration uses auth mode `none`); the service MAY accept any auth headers it receives and ignore them, to simplify mixed-mode self-tests.

### Key Entities *(include if feature involves data)*

- **Connector Service**: A remote HTTP service implementing the connector wire protocol, hosted outside the harness (or, for the mock, bundled with the harness and launched as a local child process). Each chatbot under test (or independently-testable underlying agent) is fronted by its own connector service. Authored by the team that owns the chatbot or its integration; not part of the harness codebase.
- **ConnectorRegistration**: The persisted record describing a connector service known to the harness. Carries: `connectorId` (unique string), human-readable `displayName`, optional `description`, `endpointUrl`, `authDescriptor` (with `mode` / `headerName` / `credential` / `username` subfields per the four auth modes — see `013 FR-005` for the canonical shape), `timeoutSeconds`, `expectsPerRowPassword` boolean, `archived` flag, audit timestamps (`createdAt` / `updatedAt` / `archivedAt`). Lifecycle (create/edit/archive/restore/hard-delete) lives in `013`. Snapshotted (full record) onto the Job at job-creation time (parent `FR-023`); the entity definition is in `009 FR-001a`.
- **Connector Registry**: The catalog of all `ConnectorRegistration` records in the harness installation. Backed by the persistence layer (`009`). Read surface defined here (`FR-009`–`FR-012`); write surface defined in `013`.
- **Connector Wire Protocol**: The HTTP contract defined by `FR-001`–`FR-006`. Stable across connector services; versioned at the framework level (v1 here).
- **Stored Credential Encryption Key**: A symmetric key stored machine-locally, used by the encryption utility to encrypt registered credentials before persistence and decrypt them just-in-time for HTTP requests. NOT in the database file, NOT in source control. Generation and rotation are plan-level.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A job using a registered connector runs end-to-end and produces persisted rows whose contract instances validate against the bundled Standard Evaluation Contract schema — verifiable by running an end-to-end test against the bundled mock connector and inspecting every row's persisted contract.
- **SC-002**: Adding a brand-new connector requires **zero modifications** to the harness codebase — verifiable by registering the bundled mock connector in `013`'s CRUD UI and running a job, with no source-tree change required.
- **SC-003**: The Connector Registry's "list active" and "get by id" affordances return identical data regardless of which harness surface is asking — verifiable by querying from the wizard and the orchestrator simultaneously in a test.
- **SC-004**: A registration whose auth descriptor includes a credential (bearer / api-key-header / basic) produces persistence whose database row, exported file, and any rendered UI all show that credential's plaintext value **nowhere** — verifiable by inserting a known-distinctive credential (e.g., `"DEADBEEF-12345"`) and grepping the database file, the export file, and the rendered registry-edit page for that exact string (must produce zero matches).
- **SC-005**: A copy of the database file moved to a different machine (without the machine-local key) cannot be used to recover any previously-stored credential — verifiable by copying the file to a clean machine and attempting decryption.
- **SC-006**: The harness issues exactly one HTTP request per row of a job — verifiable by instrumenting the bundled mock connector to count requests and asserting `request_count == row_count` for a clean run.
- **SC-007**: Two concurrent jobs targeting the same registered connector dispatch independent HTTP requests — verifiable by enqueuing two simultaneous jobs against the mock connector, instrumented to record incoming request streams, and asserting the streams are independently sequenced per job.
- **SC-008**: A registered connector that returns a non-2xx status for one row does NOT cause the job to abort; remaining rows proceed and the failing row is recorded with `errorStage = connector_response` — verifiable by a test where the mock connector is configured to return 500 on row 2 of a 5-row job.
- **SC-009**: A registered connector that returns a non-conformant body for one row records that row with `errorStage = connector_normalization`; subsequent rows proceed — verifiable by a test where the mock connector is configured to emit malformed JSON on row 3 of a 5-row job.
- **SC-010**: A registered connector that times out for one row records that row with `errorStage = connector_transport` and the harness aborts the HTTP call locally; subsequent rows proceed — verifiable by a test where the mock connector is configured to sleep past the registered timeout on row 4 of a 5-row job.
- **SC-011**: The bundled mock connector is usable in a brand-new harness install with zero additional external setup (no real chatbot, no external credentials, no internet access) — verifiable by clean-install testing.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth on the harness UI. The framework / registry / connector services carry no `createdBy` field of their own. Parent `FR-026` adds OS-derived `Job.createdBy` (and `Job.connectorName`, sourced from the selected registration's display name) at the Job level — those persist on the Job's snapshot, not on the connector framework's runtime state.
- The Standard Evaluation Contract (the canonical schema connector services produce instances of) is fully defined in `specs/006-evaluation-contract/spec.md`. This spec depends on it but does not redefine it.
- The CRUD lifecycle of `ConnectorRegistration` records (create, edit, archive, restore, hard-delete, test-connection) lives in `specs/013-connector-registry-management`. This spec covers only the wire protocol, the generic HTTP client behavior, the registry's read API, the encryption utility, and the bundled mock service.
- The wizard's Step 3 (`specs/003-job-creation-wizard`) consumes the registry's "list active" affordance to render a dropdown. The wizard does not render a per-connector config form — all connector configuration lives on the registration (configured in `013`), not on the job.
- The orchestrator (`012`) reads endpoint + auth descriptor + timeout + expects-per-row-password from the Job's snapshot, not from the live registry, for any already-created job. This is per parent `FR-023` (snapshot immutability).
- Connector-internal retry logic (whether a connector service retries an internal HTTP call on a transient failure before responding) is the connector service's concern; the harness MUST NOT retry at the protocol layer (per parent `FR-025`).
- Key management for the encryption utility (key location, generation, rotation, OS-level permissions) is a plan-level decision. The spec requires only the machine-local + not-in-DB + not-in-source-control properties.
- Mock connector service is intended for harness self-test and as a reference example. It is NOT intended to be used against real chatbot endpoints (it does no real I/O against a chatbot).
- The wire protocol's request body parameter `utteranceText` (not `utterance`) and the response body's contract field names follow the canonical ontology established in the harness's earlier audits (parent `FR-001`/`FR-006`/`FR-008`, `006`, `008`, `009`).
- Historical context (superseded 2026-05-29): earlier drafts of this module described a four-method Python interface (`connect`/`sendUtterance`/`normalize`/`disconnect`) with a `ConnectionHandle`, a connector-supplied config JSON Schema rendered by the wizard, and a self-registration mechanism via Python entry points or filesystem scan. That model is replaced in full by the remote-service wire-protocol model in this revision. The terms "ConnectionHandle", "RawResponse", "config schema", and "self-register" no longer appear as load-bearing concepts.
