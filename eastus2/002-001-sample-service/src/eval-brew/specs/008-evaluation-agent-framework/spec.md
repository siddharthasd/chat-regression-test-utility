# Feature Specification: Evaluation Agent Framework (Module 7)

**Feature Branch**: `008-evaluation-agent-framework`

**Created**: 2026-05-29

**Last Amended**: 2026-05-29

**Status**: Draft

**Input** *(verbatim original; superseded 2026-05-29 by the remote-HTTP-service reshape — see Clarifications "Session 2026-05-29 (Reshape)" and `FR-001`–`FR-006a` for the current model)*: User description: "Module 7 — Evaluation Agent Framework. A pluggable AI-powered evaluation agent framework. One-method interface (`evaluate(contract) → EvaluationResult`). EvaluationResult fields: `utteranceId`, `evaluationAgentId`, `evaluationTimestamp` (ISO-8601), `scores`, `verdict`, `reasoning`, `metadata`. Agents self-register with id + display name + description + config schema + scoring-dimension declaration. Registry exposes list / get / get-schema. Evaluation is non-deterministic — never cache, never dedupe, never assume repeatability. Ship a MockEvaluationAgent that returns randomized scores."

> **Parent context**: This module defines the **wire protocol and generic HTTP client** by which the harness talks to evaluation **agent services**. Per the architectural decision recorded on 2026-05-29, evaluation agents are no longer in-process Python plugins — they are **remote HTTP services** hosted outside the harness, parallel to connector services (`specs/007-connector-framework`). The interface is symmetric with the connector wire protocol: single endpoint, single-shot per row, JSON in, JSON out. Evaluation agents fulfill the parent harness's `FR-008` (consume the Standard Evaluation Contract produced by the connector service and produce a structured EvaluationResult) and inherit parent `FR-008a`'s standardized scores payload shape. The CRUD lifecycle of registered evaluator endpoints (create, edit, archive, restore, hard-delete, test-connection) lives in the new `specs/014-evaluator-registry-management` module; this spec covers only the wire protocol, the generic HTTP client behavior, the registry's read API, and the bundled mock evaluator service. The wizard's Step 4 (`specs/003-job-creation-wizard`) consumes the registry's "list" affordance to render a dropdown of registered evaluators. Stored auth credentials are encrypted at rest via the same machine-local symmetric utility introduced by parent `FR-023a` and `007 FR-013`–`FR-017` — no separate encryption utility here, the framework reuses what is already there. Parent-spec premises apply: single-user, no auth on the harness UI. The framework / registry / `EvaluationResult` payload carry no `createdBy` field; parent `FR-026`'s OS-derived `Job.createdBy` (and `Job.evaluationAgentName`, snapshotted verbatim from the selected registration's `displayName` per `003 FR-012`) live on the Job snapshot.

## Clarifications

### Session 2026-05-29

- Q: Module 7's wording "scores: agent-specific, structure varies by agent" conflicts with parent `FR-008a` which standardizes `scores` as an ordered array of `{parameter_name, score, reasoning}` entries. Which wins? → A: **Hybrid — parent `FR-008a` stays, and each registered evaluator additionally declares its scoring dimensions upfront on its `EvaluationAgentRegistration` record.** Evaluator services emit scores in the standardized array shape (per `FR-008a`); the dimensions list (e.g., `["relevance", "groundedness", "coherence"]`) is supplied by the tester at registration time (in `014`'s CRUD UI) so the wizard's Step 4, the detail view (`004`), and the export (`005`) all know what scoring dimensions to expect *before* any row runs.
- Q: What are the allowed values of `evaluationVerdict`? → A: **Closed enum: exactly `"pass"`, `"fail"`, or `"warn"`.** Every evaluation MUST emit one of these three string values. `warn` is optional for an evaluator to ever choose to emit, but if used, the string MUST be exactly `"warn"`. The harness's color-coding (`specs/004-job-detail-view` → `FR-007`) and verdict-sort ordering (`specs/004-job-detail-view` → `FR-011`: `fail` > `warn` > `pass`) depend on this closed enum.

### Session 2026-05-29 (Round 2)

- Q: When the harness detects that an evaluator emitted scores entries with `parameter_name` values NOT in its declared scoring dimensions, where is the resulting soft-warning annotation written? → A: **In a top-level harness-controlled annotation column on the persisted EvaluationResult record**, distinct from the evaluator's `metadata` field. The evaluator's `metadata` remains exclusively evaluator-owned ("what the evaluator service produced"); the harness annotation block (`harnessAnnotations`, sibling of `metadata` per `009 FR-003`) captures "what the harness noticed post-response" — including `unexpected_score_dimensions` and any future similar derivations. This keeps ownership of the two data sources cleanly separated and makes downstream consumers (`004` detail view, `005` export) able to render or hide each independently.

### Session 2026-05-29 (Round 3 — ontology consistency)

- Q: Cross-spec ontology audit found name drift on EvaluationResult fields. Pick canonical names? → A: Yes — names harmonized:
  - `scores` → **`evaluationScores`** (matches export field name and parent `FR-008a`'s renamed field).
  - `verdict` → **`evaluationVerdict`** (matches the existing denormalized column in `009 FR-003` and the export field).
  - Top-level `reasoning` field — **REMOVED**. There is no overall-evaluation reasoning at the EvaluationResult level. Per-score `reasoning` (one per `evaluationScores` entry, per `FR-008a`) is the only `reasoning` in the spec. Evaluators that want to convey overall reasoning can place a key inside `metadata`.

### Session 2026-05-29 (Reshape)

- Q: Are evaluation agents in-process Python plugins (single-method interface, self-registration) or remote HTTP services (wire protocol, CRUD-managed registry)? → A: **Remote HTTP services.** Each evaluation strategy is hosted as its own HTTP service (built and run outside the harness, e.g., a service wrapping an LLM with a structured prompt). The harness ships a generic HTTP client; the wire protocol is single-endpoint, single-shot per row, symmetric with the connector wire protocol. CRUD over registered evaluator endpoints lives in `specs/014`.
- Q: What auth modes does the harness support when calling registered evaluator endpoints? → A: **Same four modes as connectors:** `none`, `bearer`, `api-key-header`, `basic` (per `007 FR-007`). Anything more exotic is on the tester to wrap server-side.
- Q: Does the evaluator service receive the per-row CSV password? → A: **No.** Evaluator services receive only the Standard Evaluation Contract instance produced by the connector service. The per-row CSV password is consumed exclusively by the connector path (per `007 FR-002`) and is never forwarded into the evaluator path. There is no `expectsPerRowPassword` flag on `EvaluationAgentRegistration`.
- Q: Where are scoring dimensions declared in the new model? → A: **On the `EvaluationAgentRegistration` record**, supplied by the tester via `014`'s CRUD form. The dimensions are a property of the *registered configuration* — not the running evaluator service. The same evaluator service could be registered twice with different declared dimension lists if the tester wants distinct entries (though that is unusual). The registered dimensions are snapshotted onto the Job at job-creation time (parent `FR-023`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evaluate a row's chatbot response via a registered evaluator service end-to-end (Priority: P1)

The harness orchestrator, having received a Standard Evaluation Contract instance from a connector service for a single row, looks up the job's snapshotted evaluator endpoint (URL, auth descriptor, timeout, declared scoring dimensions) and issues a single HTTP `POST` to the evaluator carrying the contract instance as the request body. The evaluator service (which is AI-powered — typically wrapping an LLM with a structured prompt — or a deterministic rule-based service) responds with an `EvaluationResult` carrying the standardized verdict + scores + reasoning + metadata. The harness validates the response, applies harness-derived annotations (`harnessAnnotations`), and persists the result, linked to the row, before proceeding to the next row.

**Why this priority**: This is the entire purpose of Module 7. Without it, the harness is just a CSV-batch chatbot caller — no evaluation, no verdict, no scores. It is the MVP slice.

**Independent Test**: With a registered evaluator endpoint (e.g., the bundled mock evaluator service running on localhost) and a stub connector that emits a known contract instance, run a one-row job and verify (a) the harness issues exactly one HTTP POST to the evaluator endpoint with the full contract instance as the body, (b) the evaluator returns an `EvaluationResult` whose `utteranceId` matches the input contract's `utteranceId`, whose `evaluationAgentId` matches the registered id, whose `evaluationScores` matches the standardized `{parameter_name, score, reasoning}` array shape, whose `evaluationVerdict` is one of `pass`/`fail`/`warn`, and whose `evaluationTimestamp` is a valid ISO-8601 string close to "now".

**Acceptance Scenarios**:

1. **Given** a contract instance handed to the harness for a row whose job snapshotted a registered evaluator, **When** the orchestrator dispatches the evaluator call, **Then** the harness issues a single `POST` to the evaluator's endpoint URL with the auth header constructed per the auth descriptor (decrypting the stored credential just-in-time), `Content-Type: application/json`, and a body that is exactly the contract instance JSON.
2. **Given** a successful HTTP response with status 200 and a JSON body, **When** the harness receives the response, **Then** the body MUST contain the six required EvaluationResult fields (`utteranceId`, `evaluationAgentId`, `evaluationTimestamp`, `evaluationScores`, `evaluationVerdict`, `metadata`) with valid values per the spec's field rules.
3. **Given** the returned `EvaluationResult`, **When** the harness validates it, **Then** `utteranceId` equals the input contract's `utteranceId`, `evaluationAgentId` equals the registered evaluator's id, `evaluationVerdict` is one of `pass`/`fail`/`warn`, and `evaluationScores` is an ordered array conforming to parent `FR-008a`'s `{parameter_name, score, reasoning}` entry shape (per-score reasoning).
4. **Given** a valid `EvaluationResult`, **When** the harness persists it, **Then** the row's persisted record carries the verdict, the structured scores array, the metadata object exactly as the evaluator produced them, and the harness-derived `harnessAnnotations` block (containing `unexpected_score_dimensions` only when the evaluator's emitted dimension names diverged from the registration's declared list).

---

### User Story 2 - Add a new evaluation strategy by hosting a new evaluator service (Priority: P1)

A developer wants to add a new evaluation strategy — say, a faithfulness evaluator that checks whether the chatbot's response is grounded in a retrieved document, or a tone evaluator that scores response empathy. They build an HTTP service implementing the evaluator wire protocol defined in this spec, host it at a reachable URL, and register the endpoint in `014`'s CRUD UI (supplying display name, description, declared scoring dimensions, auth, timeout). The new evaluator immediately appears in the wizard's Step 4 dropdown; **zero code changes** to the harness are required.

**Why this priority**: Extensibility is the entire architectural point of the framework. Equal-priority with US1 because both are required for the framework to deliver value.

**Independent Test**: Stand up a trivial new evaluator service (e.g., a "LengthEvaluator" service that scores `response_length` and emits `pass` if response length is within a configurable range). Register its endpoint in `014` with declared dimensions `["response_length"]`. From a fresh wizard, verify the new evaluator appears in Step 4's dropdown, its declared scoring dimensions are visible to the harness, and a job using it runs end-to-end exactly like a job using any existing evaluator — with zero changes to the harness codebase.

**Acceptance Scenarios**:

1. **Given** an evaluator service hosted at a reachable URL whose responses conform to the wire protocol, **When** the tester registers it via `014` (supplying display name, description, declared scoring dimensions, auth descriptor, timeout), **Then** subsequent calls to the registry's "list active evaluators" affordance include it and "get by id" returns the full registration.
2. **Given** the new evaluator is registered (not archived), **When** the tester opens the wizard's Step 4, **Then** the dropdown shows the new evaluator alongside existing ones, with its display name and description visible.
3. **Given** the new evaluator's declared scoring dimensions include `"response_length"`, **When** the wizard or detail view queries the registry for that evaluator's dimensions, **Then** `"response_length"` is in the returned list.
4. **Given** an evaluator service registered without any change to the harness codebase, **When** a job runs end-to-end using it, **Then** every row produces an EvaluationResult that validates per US1's acceptance scenarios — proving the zero-core-change extensibility property.

---

### User Story 3 - Surface the declared scoring dimensions to the UI and exports (Priority: P2)

The wizard at Step 4 (after selecting a registered evaluator) can show the tester which scoring dimensions the evaluator will produce — so the tester sets expectations before running. The detail view (`004`) can pre-render the Scores column structure based on the declared dimensions (e.g., show "Awaiting: relevance, groundedness, coherence" placeholders for rows that haven't been evaluated yet). The export (`005`) can use the dimensions to write a stable column header order. All three benefit from the upfront declaration on the registration.

**Why this priority**: Pre-rendering and predictable column ordering are productivity layers on top of US1/US2. The framework works without them; with them it feels much more polished.

**Independent Test**: With one evaluator registered as declaring `["relevance", "groundedness"]` and another declaring `["coherence", "fluency", "factuality"]`, verify that (a) the wizard shows both evaluators' dimension lists at Step 4 after selection, (b) the detail view's row-loading state references the correct dimensions for the job's chosen evaluator, (c) the export's column order for `evaluationScores` reflects the chosen evaluator's declared dimension order (as snapshotted on the Job per parent `FR-023`).

**Acceptance Scenarios**:

1. **Given** a registered evaluator whose `EvaluationAgentRegistration` declares scoring dimensions `["X", "Y", "Z"]`, **When** any UI surface queries the registry for that evaluator's dimensions, **Then** it receives the ordered list `["X", "Y", "Z"]`.
2. **Given** the evaluator's response for a row contains scores entries with `parameter_name` values that match the declared dimensions, **When** the UI renders, **Then** the cells appear in the declared dimension order (not the order they happen to arrive in the persisted JSON).
3. **Given** an evaluator's actual response for one row emits scores entries with `parameter_name` values NOT in the registration's declared dimension list (e.g., declared `["X","Y"]`, emitted `[{parameter_name: "X", ...}, {parameter_name: "Z", ...}]`), **When** the harness persists the result, **Then** the unexpected `parameter_name` is persisted unchanged but flagged in `harnessAnnotations.unexpected_score_dimensions: ["Z"]`; evaluation is not rejected for this discrepancy.

---

### User Story 4 - Honor the non-determinism guarantee (Priority: P2)

The framework MUST treat every evaluator HTTP call as a fresh AI-powered evaluation. No memoization, no deduplication of identical-input contracts, no "we already evaluated this row, here's the cached result" within the harness. This is a core promise to the tester: the result reflects the evaluator's *current* judgment, not a stale prior judgment. The same contract submitted twice MAY return different scores, different reasoning, and even a different verdict — and that variability is acceptable and expected. (The evaluator service itself MAY have internal caching; the harness does not introspect that.)

**Why this priority**: Caching within the harness would silently break the trust model of a regression test harness (the whole point is to surface AI variability, not hide it). Equal-priority with US3 because the framework can deliver value before either is implemented, but both are non-negotiable parts of the v1 promise.

**Independent Test**: Configure a job to evaluate the same row's contract twice (e.g., by submitting a CSV with the same utterance + testId twice). Verify that the harness issues two HTTP POSTs to the evaluator (instrumented via request count on the mock evaluator); the two persisted EvaluationResults may have different `evaluationScores`, per-score `reasoning`, or `evaluationVerdict`, and that variability is preserved in the harness's output.

**Acceptance Scenarios**:

1. **Given** two rows in the same job carrying identical input contract content (utterance + testId + chatbotResponse), **When** the orchestrator processes them, **Then** the harness issues two HTTP POSTs to the evaluator endpoint (not one); each row's POST runs independently.
2. **Given** the two invocations produce different verdict / scores / reasoning, **When** the harness persists both results, **Then** the two persisted results show the actual emitted values (no normalization, no "we noticed a discrepancy" merging).
3. **Given** the harness's caching, deduplication, or memoization layer is inspected by code review or instrumentation, **When** the inspection runs, **Then** no such layer exists between the orchestrator and the evaluator HTTP call.

---

### User Story 5 - Use the bundled mock evaluator service for harness self-test (Priority: P2)

The harness ships with a **bundled mock evaluator service** — a small stub HTTP server the tester can spin up locally (or that the harness can launch as a child process for self-tests). The mock evaluator accepts any conformant contract and returns a deterministic-shape-but-randomized-content EvaluationResult. Test authors building any harness component (the dashboard, the detail view, the export service, the wizard) can register the mock evaluator's local URL, create a job against it, and exercise their component without needing real LLM credentials, real network access, or a real evaluation strategy. The mock evaluator also serves as the canonical "minimum viable evaluator service" reference for new evaluator authors.

**Why this priority**: Without a reference implementation, every test of the harness needs either a real LLM-backed service or a hand-rolled stub, which is friction. Equal-priority with US3/US4 because all three are productivity multipliers.

**Independent Test**: Without registering any real evaluator, launch the bundled mock evaluator service, register its local URL in `014`, create a job against it (with the bundled mock connector for the connector slot), and start the job. Verify the job runs to completion, produces persisted rows whose EvaluationResults are well-formed and conform to parent `FR-008a`, and that every harness UI surface (dashboard, detail view, export) handles the results correctly.

**Acceptance Scenarios**:

1. **Given** a fresh harness install, **When** the tester runs the documented "launch bundled mock evaluator" command (or the harness's self-test launches it as a child process), **Then** a local HTTP server starts on a plan-defined port and accepts requests conforming to the evaluator wire protocol.
2. **Given** the mock evaluator is running, **When** the tester registers its URL in `014` (auth mode `none`, declared scoring dimensions e.g., `["mock_dimension_a", "mock_dimension_b"]`), **Then** the registration succeeds and the mock evaluator appears in the wizard's Step 4 dropdown.
3. **Given** a job running against the mock evaluator, **When** the harness POSTs a contract instance to it, **Then** the mock returns a well-formed EvaluationResult with: well-formed `evaluationScores` entries matching its operator-configured dimensions (with randomized score values within a documented range, e.g., 0.0 to 1.0, and short randomized per-score `reasoning` strings); a randomized `evaluationVerdict` chosen from `{pass, fail, warn}`; a non-null `metadata` object (e.g., `{ mock: true }`).
4. **Given** repeated invocations of the mock evaluator on identical input, **When** the test compares outputs, **Then** the outputs are observably non-identical across invocations (consistent with the non-determinism guarantee per US4).

---

### Edge Cases

- A registered evaluator's endpoint URL is unreachable when a row is dispatched (DNS failure, connection refused, TLS handshake failure) — the row MUST be recorded with `errorStage = evaluator_transport`; the connection failure MUST NOT cause the job to abort; subsequent rows proceed.
- The evaluator service returns a non-2xx HTTP status — the row MUST be recorded with `errorStage = evaluator_response`; the response body (truncated to a plan-defined byte limit) MUST be captured in `errorDetails`; subsequent rows proceed.
- The evaluator service returns a 2xx HTTP status but the response body is not valid JSON, OR is valid JSON but fails EvaluationResult validation per `FR-005b` (missing field, wrong type, bad verdict value, bad scores entry shape, bad timestamp) — the row MUST be recorded with `errorStage = evaluator_result`; the offending body (truncated) MUST be captured in `errorDetails`; subsequent rows proceed.
- The evaluator service does not respond within the registered `timeoutSeconds` — the harness MUST abort the HTTP call locally; the row MUST be recorded with `errorStage = evaluator_transport` with a clear "timeout exceeded" detail; subsequent rows proceed. The harness MUST NOT retry.
- An evaluator returns scores entries whose `parameter_name` values include some that ARE in the registration's declared scoring dimensions and some that are NOT — the evaluator's output is persisted unchanged AND the harness writes `harnessAnnotations.unexpected_score_dimensions: [...]` listing the unexpected names. The evaluator's own `metadata` field is NOT mutated. This is a SOFT warning, not a hard failure.
- The evaluator returns an `evaluationVerdict` value not in the closed enum `{pass, fail, warn}` (e.g., `"inconclusive"`, `"needs-review"`) — the row MUST be recorded with `errorStage = evaluator_result` and a detail naming the invalid verdict; subsequent rows proceed.
- The evaluator's response `utteranceId` does NOT match the input contract's `utteranceId` — the row MUST be recorded with `errorStage = evaluator_result` and a detail naming the mismatch; subsequent rows proceed. (This is a sanity check guarding against evaluator services that lose track of correlation.)
- The evaluator's response `evaluationAgentId` does NOT match the registered evaluator's id — the row is PERSISTED unchanged (the evaluator service's self-declared id is authoritative for its own output) but the harness MUST log a warning naming the mismatch for diagnosis. This does NOT fail the row.
- The job's snapshotted evaluator points to an `archived` (soft-deleted) registration — the orchestrator MUST dispatch rows normally using the snapshot; archival affects only the wizard's dropdown selectability, not historical job execution.
- The job's snapshotted evaluator points to an `EvaluationAgentRegistration` that has since been hard-deleted from the registry — because the Job carries a full snapshot of endpoint + auth descriptor + timeout + declared scoring dimensions (per parent `FR-023` and `009 FR-001b`), the orchestrator MUST still be able to dispatch rows using the snapshot. (Note: hard-delete of a registration referenced by historical jobs is gated by `014 FR-024`, so this case cannot occur in normal operation; the snapshot-self-sufficiency property is a defensive guarantee for the case where the gate is somehow bypassed.)
- The registered evaluator's stored auth credential cannot be decrypted (key rotated without re-encrypt, file moved to a new machine) — the row MUST be recorded with `errorStage = evaluator_auth` and the actionable "machine-local key missing or wrong" message; subsequent rows MAY fail the same way if the credential is shared.
- An evaluator's declared scoring dimensions are empty (zero dimensions) — valid; the evaluator MUST still emit an `evaluationVerdict` and an empty `evaluationScores` array on every response (e.g., a purely-verdict-based evaluator like a binary safety classifier).
- An evaluator's declared scoring dimension names contain characters that would need special handling in CSV (commas, quotes, newlines) — the registration form MUST accept them; downstream consumers (`005` export) handle CSV escaping per their existing rules.
- The harness restarts mid-evaluation of a row — the row's persisted state is whatever was committed before the restart (likely the connector's contract is persisted but the EvaluationResult is not); on next startup, parent `FR-022` reconciles the orphaned job; the row is left as `failed` with `errorStage = evaluator_transport` (or whatever the orchestrator's restart policy is — parent-spec concern, not Module 7).
- The evaluator's `evaluationTimestamp` is in the future, or wildly in the past, or in a non-ISO-8601 format — the row MUST be recorded with `errorStage = evaluator_result` and an actionable detail.
- Two concurrent jobs use the same registered evaluator — each job dispatches its own HTTP requests independently; there is no shared state between jobs at the protocol level. The evaluator service is responsible for handling concurrent inbound requests.

## Requirements *(mandatory)*

### Functional Requirements

#### Evaluator Wire Protocol

- **FR-001**: The framework MUST define an **Evaluator Wire Protocol** — a single-endpoint HTTP contract that every evaluator service MUST honor. The protocol is single-shot per row: one row = one request = one response. There is no session, no streaming in v1.
- **FR-002**: An evaluator request MUST be an HTTP `POST` to the evaluator's registered endpoint URL with `Content-Type: application/json` and a JSON body that is the full Standard Evaluation Contract instance produced by the connector service for the row being evaluated (as defined by `specs/006-evaluation-contract`). The body MUST NOT carry any harness-specific wrapping fields; it is the contract instance verbatim.
- **FR-003**: A successful evaluator response MUST be HTTP 200 with `Content-Type: application/json` and a body that is a single, complete JSON object carrying exactly the six required EvaluationResult fields (the harness persists this inline as columns on the `EvaluationResult` entity per `009 FR-003`):
  - `utteranceId` (string) — MUST exactly equal the input contract's `utteranceId`. Echoed for traceability.
  - `evaluationAgentId` (string) — MUST exactly equal the registered evaluator's id.
  - `evaluationTimestamp` (string) — ISO-8601 / RFC 3339-compatible datetime, indicating when the evaluator produced this result.
  - `evaluationScores` (array) — an ordered collection of zero or more entries, each entry conforming to parent `FR-008a`'s shape: `{ parameter_name: string, score: number-or-short-string, reasoning: string }`. The per-entry `reasoning` is per-score (per parameter), NOT a top-level field on EvaluationResult.
  - `evaluationVerdict` (string) — exactly one of the closed enum values `"pass"`, `"fail"`, `"warn"`.
  - `metadata` (object) — evaluator-specific extra structured data (e.g., model name and version, token cost, latency, retrieval document references). Free-form; the harness does NOT constrain its keys. Empty object `{}` is valid.
  - **There is NO top-level `reasoning` field on EvaluationResult.** Per-score reasoning lives inside each `evaluationScores` entry.
- **FR-004**: The `evaluationVerdict` field MUST be one of exactly three string values: `"pass"`, `"fail"`, `"warn"`. Any other value MUST cause the row to be recorded with `errorStage = evaluator_result`. `warn` is OPTIONAL for an evaluator to ever emit; if an evaluator never produces ambiguous results, it MAY use only `pass` and `fail`. But if used, the string MUST be exactly `"warn"` (lowercase, no whitespace, no variants).
- **FR-005**: The `evaluationScores` array MUST follow parent `FR-008a` exactly — every entry MUST be an object with the three fields `parameter_name`, `score`, `reasoning`. Empty array `[]` is valid. Each `parameter_name` SHOULD be one of the registration's declared scoring dimensions; entries with `parameter_name` values NOT in the declared dimension list are PERSISTED but trigger a soft warning recorded in `harnessAnnotations.unexpected_score_dimensions` per `FR-005a`.
- **FR-005a**: The harness MUST persist EvaluationResults with a top-level **`harnessAnnotations`** column alongside (not nested inside) the evaluator's `metadata` field — both are top-level columns on the persisted `EvaluationResult` entity (per `009 FR-003`). `harnessAnnotations` holds annotations the harness derives post-response from the evaluator's output — it is NEVER written by the evaluator service. In v1 the harness writes at minimum:
  - `unexpected_score_dimensions` (array of strings) — listing any `parameter_name` values present in `evaluationScores` but NOT declared in the registration's dimension list. Omitted (or empty array) when the evaluator's output is fully aligned with its declaration.
  
  The block is extensible: future spec revisions MAY add more harness-derived annotation keys. Downstream consumers (`004` detail view, `005` export) MUST treat `harnessAnnotations` as informational; they MUST render or expose it visibly (so the tester understands the soft warning) but they MUST NOT use it to gate any other behavior.
- **FR-005b**: Validation of the evaluator response MUST hard-reject the row with `errorStage = evaluator_result` when ANY of the following hold:
  - The response body is not valid JSON, or is not a JSON object.
  - Any required EvaluationResult field is missing or has the wrong top-level type.
  - `utteranceId` in the response does not exactly equal the input contract's `utteranceId`.
  - `evaluationVerdict` is not one of `"pass"` / `"fail"` / `"warn"`.
  - Any `evaluationScores` entry is not an object, or is missing one of `parameter_name` / `score` / `reasoning`, or any of those fields has the wrong type.
  - `evaluationTimestamp` is not a valid ISO-8601 string.
  
  These are sanity-check rejections, distinct from the soft-warning case in `FR-005`/`FR-005a` (unexpected-but-structurally-valid score names). The failure detail MUST name the specific check that failed and the offending value where applicable. The `evaluationAgentId` mismatch case is intentionally NOT in this list — see edge case above for why.
- **FR-006**: The harness MUST enforce a per-row response timeout equal to the evaluator's registered `timeoutSeconds` value. When the timeout is exceeded the harness MUST abort the HTTP call locally and record `errorStage = evaluator_transport` with a "timeout exceeded" detail. The harness MUST NOT retry (per parent `FR-025`).
- **FR-006a**: HTTP-level error categorization in the harness MUST map to the following `errorStage` values: transport / DNS / TLS / timeout failures → `evaluator_transport`; non-2xx status responses → `evaluator_response`; 2xx with invalid JSON or invalid EvaluationResult body → `evaluator_result`; auth credential decryption failure (before the request is sent) → `evaluator_auth`.

#### Auth Modes

- **FR-007**: The harness MUST support the same four auth modes when calling a registered evaluator endpoint as it does for connectors: `none`, `bearer`, `api-key-header`, `basic`. The mode's behavior (header construction, credential handling) is identical to `007 FR-007`–`FR-007d`. Anything beyond these four modes is out of scope for v1.

#### Evaluator Registry (read surface)

- **FR-008**: The framework MUST expose an **Evaluator Registry read API**. The registry is the single source of truth for "which evaluators does this harness installation know about?" Write operations (create / edit / archive / restore / hard-delete) live in `specs/014`; this spec covers only the read surface.
- **FR-009**: The read API MUST expose at minimum: (a) **list active evaluators** — returning at least the minimum tuple `(evaluationAgentId, displayName, description, declaredScoringDimensions)` for each entry; consumers needing additional fields (endpoint URL, auth descriptor, timeout) MUST use the get-by-id affordance below. Consumed by the wizard's Step 4 dropdown (per `003 FR-010`); archived registrations MUST NOT appear in this list. (b) **get evaluator by id** (returning the full registration record: `displayName`, `description`, `endpointUrl`, `authDescriptor` including encrypted credentials, `timeoutSeconds`, `declaredScoringDimensions`, `archived` state, audit timestamps) — consumed by the wizard at job-creation snapshot time (per `003 FR-012`). At execution time the orchestrator (`012 FR-004`) MUST resolve evaluator configuration from the Job's snapshot per parent `FR-023`, NOT from this live read API. (c) **get declared scoring dimensions for a given evaluator id** (a convenience accessor for the wizard, detail view, and export to pre-render columns / expectations without pulling the full registration).
- **FR-010**: The read API MUST return identical data regardless of which harness surface (wizard, orchestrator, detail view, export, registry-management UI) is calling.
- **FR-011**: The framework MUST support adding new evaluators **without modifying** the core harness code, the registry implementation, the orchestrator, the wizard, the dashboard, the detail view, the export service, the contract, the connector framework, any other existing evaluator, or any existing connector. The only operations required are: (a) host an HTTP service that honors the evaluator wire protocol, (b) register its endpoint in `014`'s CRUD UI.
- **FR-012**: The orchestrator MUST resolve endpoint + auth descriptor + timeout + declared scoring dimensions from the **Job snapshot** (per parent `FR-023` and `009`), not from the live registry, for any already-created job. This guarantees that edits to a registration after job creation do not retroactively change historical jobs' execution behavior or display.
- **FR-013**: The job's snapshotted evaluator pointing to an `archived` registration MUST still be executable — soft-deletion affects only future selectability (wizard dropdown), not historical execution or display.

#### Stored Credential Encryption (shared with `007`)

- **FR-014**: The credential subfield within the registered evaluator's `authDescriptor` (e.g., the bearer token / api-key-header value / basic-auth password the harness sends when calling the evaluator endpoint) MUST be persisted at rest in encrypted form per parent `FR-023a` and `007 FR-013`–`FR-017`. The same machine-local symmetric key utility is shared; the framework does NOT introduce a separate encryption utility for evaluators. (The evaluator service's own internal downstream credentials — e.g., its OpenAI / Anthropic API key — are the evaluator service's concern, NOT what the harness's `authDescriptor` encrypts; see the 2026-05-29 Reshape clarification in this spec.)
- **FR-015**: Decrypted credentials MUST be passed to the HTTP client only at the moment the auth header is being constructed; they MUST NOT appear in UI rendering (per `004 FR-005`), in exports (per `005 FR-011`), or in application logs. Plaintext lifetime is bounded by a single HTTP request.
- **FR-016**: When decryption fails (e.g., key missing, ciphertext corrupt, key mismatch from a moved installation), the harness MUST surface an actionable error including the remediation hint "machine-local key missing or wrong". The owning row MUST be recorded with `errorStage = evaluator_auth`. Subsequent rows MAY fail the same way if the credential is shared.
- **FR-017**: The per-row CSV `password` (consumed only on the connector path per `007 FR-002`) is NOT forwarded to the evaluator. The evaluator wire protocol body contains only the Standard Evaluation Contract.

#### Non-determinism guarantee

- **FR-018**: The framework MUST treat every evaluator HTTP call as a fresh evaluation. The framework MUST NOT cache evaluator responses, MUST NOT deduplicate calls based on input-contract-content equality, MUST NOT memoize based on `utteranceId`, MUST NOT use any "we already evaluated this row" shortcut. Every row that reaches the evaluator dispatch step MUST result in a fresh HTTP `POST` to the evaluator endpoint.
- **FR-019**: Consumers of EvaluationResults (the detail view, the export, downstream tooling) MUST NOT assume that two evaluations of the same contract content produce identical (or even similar) verdicts, scores, or reasoning. The harness's documentation, UI affordances, and export annotations SHOULD make this explicit where relevant (e.g., the detail view's expand-on-click full trace shows the timestamp of evaluation alongside the result, signaling that this result is the evaluator's judgment *at that moment*, not a stable fact).
- **FR-020**: The same `evaluationAgentId` MAY be invoked many times within the same job (once per row) and MAY produce different verdict / scores / reasoning each time. The framework treats this as expected behavior, not as an inconsistency.

#### Concurrency

- **FR-021**: The harness MUST issue evaluator requests serially within a single job — at most one evaluator HTTP call MAY be in flight at any moment for a given job, consistent with the connector serialization rule in `007 FR-005`. Cross-job parallelism (per parent `FR-011`) is unaffected; concurrent jobs dispatch independently.

#### Bundled Mock Evaluator Service

- **FR-022**: The harness MUST ship a **bundled mock evaluator service** — a stub HTTP server implementing the evaluator wire protocol, launchable as either a standalone process or as a child process of the harness's self-test runner.
- **FR-023**: The mock evaluator service MUST emit a well-formed EvaluationResult on every successful request, with:
  - `utteranceId` correctly echoing the input contract.
  - `evaluationAgentId` matching its registered id (e.g., `"mock-evaluator"`).
  - `evaluationTimestamp` set to the current moment in ISO-8601.
  - `evaluationScores` an array of entries matching the dimensions the tester configured at registration time (the mock service MAY accept its dimension list via a launch-time argument or environment variable so its emitted `parameter_name` values align with the registration), with randomized `score` values within a documented range (e.g., 0.0–1.0) and short randomized per-score `reasoning` strings.
  - `evaluationVerdict` randomized from the closed enum `{pass, fail, warn}`.
  - `metadata` a non-null object (e.g., `{ mock: true }`; the mock MAY put a summary string inside `metadata` if useful — there is no top-level `reasoning` field).
- **FR-024**: The mock evaluator's randomization MUST produce observably different output across successive calls on identical input — exercising and verifying the non-determinism guarantee (US4) by construction.
- **FR-025**: The mock evaluator service MUST require no auth by default (documented quickstart registration uses auth mode `none`); the service MAY accept any auth headers it receives and ignore them, to simplify mixed-mode self-tests.
- **FR-026**: The mock evaluator MUST be safe to use in unit, integration, and end-to-end tests of every other harness module without requiring external network access, real LLM credentials, or any out-of-process dependency beyond a free local port.
- **FR-027**: The mock evaluator MAY expose process-level configuration knobs (env vars, command-line flags) for testing edge cases (e.g., emit a non-conformant body, emit a non-2xx status, sleep before responding to test the timeout path, emit `unexpected_score_dimensions`-triggering names).

### Key Entities *(include if feature involves data)*

- **Evaluator Service**: A remote HTTP service implementing the evaluator wire protocol, hosted outside the harness (or, for the mock, bundled with the harness and launched as a local child process). Authored by the team that owns the evaluation strategy (typically a service wrapping an LLM with a structured prompt, or a rules-based service); not part of the harness codebase.
- **EvaluationAgentRegistration**: The persisted record describing an evaluator service known to the harness. Carries: `evaluationAgentId` (unique string), human-readable `displayName`, required `description`, `endpointUrl`, `authDescriptor` (with `mode` / `headerName` / `credential` / `username` subfields per the four auth modes — see `013 FR-005` for the canonical shape, shared with connectors), `timeoutSeconds`, `declaredScoringDimensions` (ordered list of strings, MAY be empty), `archived` flag, audit timestamps (`createdAt` / `updatedAt` / `archivedAt`). Lifecycle (create/edit/archive/restore/hard-delete) lives in `014`. Snapshotted (full record) onto the Job at job-creation time (parent `FR-023`); the entity definition is in `009 FR-001b`.
- **Evaluator Registry**: The catalog of all `EvaluationAgentRegistration` records in the harness installation. Backed by the persistence layer (`009`). Read surface defined here (`FR-008`–`FR-013`); write surface defined in `014`.
- **Evaluator Wire Protocol**: The HTTP contract defined by `FR-001`–`FR-006a`. Stable across evaluator services; versioned at the framework level (v1 here).
- **EvaluationResult**: The structured output the evaluator service returns. Carries the six required fields enumerated in `FR-003`. Same entity name as the persisted row in `009 FR-003` — the evaluator emits this subset, and the harness persists it inline as columns on the `EvaluationResult` row along with the connector-emitted fields (`rawChatbotResponse`, `normalizedContract` — both produced by the connector service per `007 FR-003`), the harness-derived `harnessAnnotations`, error fields, and a `testId` denormalization.
- **Declared Scoring Dimensions**: An evaluator registration's upfront promise of what `parameter_name` values its evaluator service will populate in its scores array. Ordered list of strings. Supplied by the tester at registration time in `014`. Consumed by the wizard's Step 4 (informational display), the detail view (pre-render placeholders before a row is evaluated; canonical column order), and the export (canonical column order in CSV; canonical key order in JSON).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A job using a registered evaluator runs end-to-end and produces persisted EvaluationResults whose six required fields are all populated with valid values per `FR-003` — verifiable by running an end-to-end test against the bundled mock evaluator and inspecting every persisted row.
- **SC-002**: Adding a brand-new evaluator requires **zero modifications** to the harness codebase — verifiable by registering the bundled mock evaluator in `014`'s CRUD UI and running a job, with no source-tree change required.
- **SC-003**: The Evaluator Registry's "list active", "get by id", and "get dimensions" affordances return identical data regardless of which harness surface is asking — verifiable by querying from each surface and comparing results.
- **SC-004**: An evaluator whose registration declares scoring dimensions `[A, B, C]` and that emits scores entries `[B, A, C]` (correct names, different order) has its scores rendered in the declared order `[A, B, C]` by the detail view and export — verifiable by inspection of the rendered UI and exported file.
- **SC-005**: The same evaluator endpoint called twice on identical input within the same job (e.g., a job with two CSV rows that have identical utterance + testId) produces two persisted EvaluationResults whose verdict, scores, or reasoning differ in at least one observable way — verifiable by running such a job against the mock evaluator and diffing the two results.
- **SC-006**: There is no code path within the framework between the orchestrator and the evaluator HTTP call that caches, dedupes, or short-circuits invocations — verifiable by code review or by instrumenting the mock evaluator to count requests and asserting count equals row count.
- **SC-007**: An evaluator whose response is malformed (wrong verdict value, missing required field, scores entry that doesn't match parent `FR-008a`, mismatched `utteranceId`) causes the affected row to be recorded with `errorStage = evaluator_result` and an actionable detail; subsequent rows proceed — verifiable by instrumenting the mock evaluator to emit malformed output on row 3 of a 5-row job.
- **SC-008**: An evaluator that returns a non-2xx status for one row records that row with `errorStage = evaluator_response`; subsequent rows proceed — verifiable by a test where the mock evaluator is configured to return 500 on row 2 of a 5-row job.
- **SC-009**: An evaluator that times out for one row records that row with `errorStage = evaluator_transport` and the harness aborts the HTTP call locally; subsequent rows proceed — verifiable by a test where the mock evaluator is configured to sleep past the registered timeout on row 4 of a 5-row job.
- **SC-010**: Concurrent jobs (per parent `FR-011`) using the same evaluator do not share state at the harness layer — verifiable by running two simultaneous jobs against an instrumented mock evaluator and confirming each job's request stream is independently sequenced.
- **SC-011**: A registration's declared scoring dimensions list is retrievable from the registry independently of any running job — verifiable by registering an evaluator in `014`, calling the dimension-query affordance, and asserting the returned list matches what the tester entered.
- **SC-012**: The bundled mock evaluator is usable in a brand-new harness install with zero additional external setup (no real LLM, no API keys, no internet access) and produces observably non-deterministic output across runs — verifiable by clean-install end-to-end testing.
- **SC-013**: Auth credentials stored on EvaluationAgentRegistration records (bearer / api-key-header / basic) never appear in plaintext in the database file, in any export, or in the rendered registry-edit UI — verifiable by the same end-to-end test pattern as `007 SC-004` but with an evaluator in place of a connector.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth on the harness UI. The evaluator framework / registry / evaluator services / `EvaluationResult` payload carry no `createdBy` field. Parent `FR-026` adds OS-derived `Job.createdBy` (and `Job.evaluationAgentName`) at the Job level — those persist on the Job's snapshot, not on the framework's runtime state or the per-row result.
- The Standard Evaluation Contract is fully defined in `specs/006-evaluation-contract/spec.md`. This spec depends on it but does not redefine it.
- The connector framework (`specs/007-connector-framework`) defines the producer side of the same integration seam. The evaluator framework is the consumer side; together they make the remote-service pluggability model complete.
- The CRUD lifecycle of `EvaluationAgentRegistration` records (create, edit, archive, restore, hard-delete, test-connection, declared-dimensions editing) lives in `specs/014-evaluator-registry-management`. This spec covers only the wire protocol, the generic HTTP client behavior, the registry's read API, the encryption story (inherited from `007`), and the bundled mock service.
- The wizard's Step 4 (`specs/003-job-creation-wizard`) consumes the registry's "list active" and "get declared dimensions" affordances. The wizard does not render a per-evaluator config form — all evaluator configuration (endpoint, auth, timeout, dimensions) lives on the registration in `014`, not on the job.
- The orchestrator (`012`) reads endpoint + auth descriptor + timeout + declared scoring dimensions from the Job's snapshot, not from the live registry, for any already-created job. This is per parent `FR-023`.
- Evaluator-internal retry logic (whether an evaluator service retries an internal LLM call on a transient failure before responding) is the evaluator service's concern; the harness MUST NOT retry at the protocol layer (per parent `FR-025`).
- The closed verdict enum `{pass, fail, warn}` is sufficient for v1. Future contract-shape changes that add new verdict values would be a breaking change to the EvaluationResult shape and would require a new harness major version.
- "Declared scoring dimensions" is a soft promise — evaluators emit what they emit, and the harness annotates rather than rejects when emitted dimensions diverge from declared. This keeps the system robust to evaluator drift while preserving the UI/export benefit of upfront declaration.
- The mock evaluator's randomization is unseeded by default (truly non-deterministic). Plan-level decisions MAY include an optional environment-variable knob for seeded determinism if test authors find unpredictable output annoying. The spec only requires that the default behavior exercises the non-determinism guarantee.
- The framework does NOT define a "Standard Evaluation Result Contract" version separate from the Standard Evaluation Contract. The EvaluationResult shape is harness-canonical and changes only when the harness itself ships a major version. Evaluator services authoring against this spec follow `FR-003`'s shape exactly.
- Historical context (superseded 2026-05-29): earlier drafts of this module described a single-method Python interface (`evaluate(contract) → EvaluationResult`) with self-registration via Python entry points / filesystem scan / manifest, declared scoring dimensions as a property of the agent class, and a "MockEvaluationAgent" Python class. That model is replaced in full by the remote-service wire-protocol model in this revision. The terms "self-register", "config JSON Schema rendered by wizard", and "MockEvaluationAgent class" no longer appear as load-bearing concepts.
