# Feature Specification: Evaluation Agent Framework (Module 7)

**Feature Branch**: `008-evaluation-agent-framework`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 7 — Evaluation Agent Framework. A pluggable AI-powered evaluation agent framework. One-method interface (`evaluate(contract) → EvaluationResult`). EvaluationResult fields: `utteranceId`, `evaluationAgentId`, `evaluationTimestamp` (ISO-8601), `scores`, `verdict`, `reasoning`, `metadata`. Agents self-register with id + display name + description + config schema + scoring-dimension declaration. Registry exposes list / get / get-schema. Evaluation is non-deterministic — never cache, never dedupe, never assume repeatability. Ship a MockEvaluationAgent that returns randomized scores."

> **Parent context**: This module is the consumer side of the integration seam defined by `specs/006-evaluation-contract/spec.md` (which is the producer side of the connector framework, `specs/007-connector-framework/spec.md`). Evaluation agents fulfill the parent harness's `FR-008` (consume the normalized Standard Evaluation Contract and produce a structured Evaluation Result) and inherit parent `FR-008a`'s standardized scores payload shape. The wizard's Step 4 (`specs/003-job-creation-wizard` → `FR-011`, `FR-012`, `FR-013`, `FR-014`) is the registry's primary UI consumer. Parent-spec premises apply: single-user, no auth, no `createdBy`. The Module 7 input's "API keys for the evaluation LLM" in the config schema are config-level secret-declared fields, handled at rest by the same machine-local encryption utility introduced by parent `FR-023a` and Module 4's `FR-015` — no new encryption story here, the framework reuses what's already there. The Module 7 input's reference to "Standard Evaluation Contract" is `specs/006-evaluation-contract`. The user's module number ("Module 7") maps to our `008-` directory by the same convention used for Module 4 → `007-`.

## Clarifications

### Session 2026-05-29

- Q: Module 7's wording "scores: agent-specific, structure varies by agent" conflicts with parent `FR-008a` which standardizes `scores` as an ordered array of `{parameter_name, score, reasoning}` entries. Which wins? → A: **Hybrid — parent `FR-008a` stays, and each agent additionally declares its scoring dimensions upfront in its registry metadata.** Agents emit scores in the standardized array shape (per `FR-008a`); the dimensions list (e.g., `["relevance", "groundedness", "coherence"]`) is part of the agent's registry self-declaration so the wizard's Step 4, the detail view (`004`), and the export (`005`) all know what scoring dimensions to expect *before* any row runs.
- Q: What are the allowed values of `verdict`? → A: **Closed enum: exactly `"pass"`, `"fail"`, or `"warn"`.** Every evaluation MUST emit one of these three string values. `warn` is optional for an agent to ever choose to emit, but if used, the string MUST be exactly `"warn"`. The harness's color-coding (`specs/004-job-detail-view` → `FR-007`) and verdict-sort ordering (`specs/004-job-detail-view` → `FR-011`: `fail` > `warn` > `pass`) depend on this closed enum.

### Session 2026-05-29 (Round 2)

- Q: When the harness detects that an agent emitted scores entries with `parameter_name` values NOT in its declared scoring dimensions, where is the resulting soft-warning annotation written? → A: **In a new harness-controlled annotation block on the persisted EvaluationResult record**, distinct from the agent's `metadata` field. The agent's `metadata` remains exclusively agent-owned ("what the agent produced"); the harness annotation block (`harnessAnnotations`, sibling of `metadata`) captures "what the harness noticed post-evaluate" — including `unexpected_score_dimensions` and any future similar derivations. This keeps ownership of the two data sources cleanly separated and makes downstream consumers (`004` detail view, `005` export) able to render or hide each independently.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evaluate a row's chatbot response and persist a structured result (Priority: P1)

The harness orchestrator, having received a Standard Evaluation Contract instance from a connector for a single row, looks up the job's snapshotted evaluation-agent identity in the Evaluation Agent Registry, decrypts any secret-declared config fields, and invokes `evaluate(contract)` on the agent. The agent (which is AI-powered — typically wrapping an LLM with a structured prompt) returns an `EvaluationResult` carrying the standardized verdict + scores + reasoning + metadata. The harness persists the result, linked to the row, and proceeds to the next row.

**Why this priority**: This is the entire purpose of Module 7. Without it, the harness is just a CSV-batch chatbot caller — no evaluation, no verdict, no scores. It is the MVP slice.

**Independent Test**: With a registered evaluation agent (e.g., the bundled MockEvaluationAgent) and a stub connector that emits a known contract instance, run a one-row job and verify (a) the orchestrator invokes `evaluate()` exactly once with that contract, (b) the agent returns an `EvaluationResult` whose `utteranceId` matches the input contract's `utteranceId`, whose `evaluationAgentId` matches the registered id, whose `scores` matches the standardized `{parameter_name, score, reasoning}` array shape, whose `verdict` is one of `pass`/`fail`/`warn`, and whose `evaluationTimestamp` is a valid ISO-8601 string close to "now".

**Acceptance Scenarios**:

1. **Given** a contract instance handed to a registered evaluation agent, **When** the orchestrator invokes `evaluate(contract)`, **Then** the agent returns an `EvaluationResult` object containing all seven required fields (`utteranceId`, `evaluationAgentId`, `evaluationTimestamp`, `scores`, `verdict`, `reasoning`, `metadata`) with valid values per the spec's field rules.
2. **Given** the returned `EvaluationResult`, **When** the harness validates it, **Then** `utteranceId` equals the input contract's `utteranceId`, `evaluationAgentId` equals the registered agent's id, `verdict` is one of `pass`/`fail`/`warn`, and `scores` is an ordered array conforming to parent `FR-008a`'s `{parameter_name, score, reasoning}` entry shape.
3. **Given** a valid `EvaluationResult`, **When** the harness persists it, **Then** the row's persisted record carries the verdict, the structured scores array, the reasoning string, and the metadata object exactly as the agent produced them.

---

### User Story 2 - Add a new evaluation strategy without touching the core harness (Priority: P1)

A developer wants to add a new evaluation strategy — say, a faithfulness evaluator that checks whether the chatbot's response is grounded in a retrieved document, or a tone evaluator that scores response empathy. They write a class implementing the single-method interface, declare a unique `evaluationAgentId`, a display name, a description, a JSON Schema for its config (including any secret fields like the LLM API key it uses internally), and its declared scoring dimensions. They register it with the framework. The new agent immediately appears in the wizard's Step 4 picker; existing agents and the orchestrator core are untouched. This is the spec's "pluggable" promise made operational for evaluation agents.

**Why this priority**: Extensibility is the entire architectural point of having a framework rather than a hard-coded evaluator. Equal-priority with US1 because both are required for the framework to deliver value.

**Independent Test**: Implement a trivial new evaluation agent (e.g., a "LengthEvaluator" that scores `response_length` and emits `pass` if response length is within a configurable range). Register it via the framework's registration mechanism. From a fresh wizard, verify the new agent appears in Step 4's picker, its declared config schema renders correctly, its declared scoring dimensions are visible to the harness, and a job using it runs end-to-end exactly like a job using any existing agent — with zero changes to any existing agent module, the registry implementation, or the orchestrator.

**Acceptance Scenarios**:

1. **Given** a new evaluation-agent class that implements `evaluate()` correctly and declares an as-yet-unused `evaluationAgentId`, **When** the agent self-registers, **Then** the registry's "list" and "get by id" affordances return it.
2. **Given** the new agent is registered, **When** the tester opens the wizard's Step 4, **Then** the picker shows the new agent alongside existing ones, with its display name and description visible.
3. **Given** the new agent's declared scoring dimensions include `"response_length"`, **When** the wizard or detail view queries the registry for that agent's dimensions, **Then** `"response_length"` is in the returned list.
4. **Given** a brand-new evaluation agent added to the framework without modifying any other agent, the registry implementation, or the orchestrator file, **When** a job runs end-to-end using it, **Then** every row produces an EvaluationResult that validates per US1's acceptance scenarios — proving the zero-core-change extensibility property.

---

### User Story 3 - Surface the declared scoring dimensions to the UI and exports (Priority: P2)

The wizard at Step 4 (after selecting an evaluation agent) can show the tester which scoring dimensions the agent will produce — so the tester sets expectations before running. The detail view (`004`) can pre-render the Scores column structure based on the dimensions (e.g., show "Awaiting: relevance, groundedness, coherence" placeholders for rows that haven't been evaluated yet). The export (`005`) can use the dimensions to write a stable column header order. All three benefit from the upfront declaration.

**Why this priority**: Pre-rendering and predictable column ordering are productivity layers on top of US1/US2. The framework works without them; with them it feels much more polished.

**Independent Test**: With one agent declaring `["relevance", "groundedness"]` and another declaring `["coherence", "fluency", "factuality"]`, verify that (a) the wizard shows both agents' dimension lists at Step 4 after selection, (b) the detail view's row-loading state references the correct dimensions for the job's chosen agent, (c) the export's column order for `scores` reflects the chosen agent's declared dimension order.

**Acceptance Scenarios**:

1. **Given** a registered agent that declares scoring dimensions `["X", "Y", "Z"]` in its registry metadata, **When** any UI surface queries the registry for that agent's dimensions, **Then** it receives the ordered list `["X", "Y", "Z"]`.
2. **Given** the agent's evaluate() output for a row contains scores entries with `parameter_name` values that match the declared dimensions, **When** the UI renders, **Then** the cells appear in the declared dimension order (not the order they happen to arrive in the persisted JSON).
3. **Given** an agent's actual evaluate() output for one row emits scores entries with `parameter_name` values NOT in the agent's declared dimension list (e.g., declared `["X","Y"]`, emitted `[{parameter_name: "X", ...}, {parameter_name: "Z", ...}]`), **When** the harness persists the result, **Then** the unexpected `parameter_name` is persisted unchanged but flagged in the row's metadata (e.g., as `unexpected_score_dimensions: ["Z"]`); evaluation is not rejected for this discrepancy.

---

### User Story 4 - Honor the non-determinism guarantee (Priority: P2)

The framework MUST treat every `evaluate()` invocation as a fresh AI-powered evaluation. No memoization, no deduplication of identical-input contracts, no "we already evaluated this row, here's the cached result". This is a core promise to the tester: the result reflects the agent's *current* judgment, not a stale prior judgment. The same contract evaluated twice MAY return different scores, different reasoning, and even a different verdict — and that variability is acceptable and expected.

**Why this priority**: Caching would silently break the trust model of a regression test harness (the whole point is to surface AI variability, not hide it). Equal-priority with US3 because the framework can deliver value before either is implemented, but both are non-negotiable parts of the v1 promise.

**Independent Test**: Configure a job to evaluate the same row's contract twice (e.g., by submitting a CSV with the same utterance + testId twice). Verify that both invocations of evaluate() actually run (instrumented via the agent counting calls); the two persisted EvaluationResults may have different scores, reasoning, or verdict, and that variability is preserved in the harness's output.

**Acceptance Scenarios**:

1. **Given** two rows in the same job carrying identical input contract content (utterance + testId + chatbotResponse), **When** the orchestrator processes them, **Then** the agent's `evaluate()` method is invoked twice (not once); each invocation runs the agent's full evaluation logic.
2. **Given** the two invocations produce different verdict / scores / reasoning, **When** the harness persists both results, **Then** the two persisted results show the actual emitted values (no normalization, no "we noticed a discrepancy" merging).
3. **Given** the harness's caching, deduplication, or memoization layer is inspected by code review or instrumentation, **When** the inspection runs, **Then** no such layer exists between the orchestrator and the agent's `evaluate()` method.

---

### User Story 5 - Use the bundled MockEvaluationAgent for harness self-test (Priority: P2)

The framework ships with a reference MockEvaluationAgent that returns randomized but well-formed EvaluationResults for any input contract. Test authors building any harness component (the dashboard, the detail view, the export service, the wizard) can configure a job to use MockEvaluationAgent and exercise their component without needing real LLM credentials, real network access, or a real evaluation strategy. MockEvaluationAgent also serves as the canonical "how to implement an evaluation agent" example for new agent authors.

**Why this priority**: Without a reference implementation, every test of the harness needs either a real LLM-backed agent or a hand-rolled mock, which is friction. Equal-priority with US3/US4 because all three are productivity multipliers.

**Independent Test**: Without configuring any real evaluation agent, create a job in the wizard, select MockEvaluationAgent (with the bundled MockConnector), fill in its minimal config, and start the job. Verify the job runs to completion, produces persisted rows whose EvaluationResults are well-formed and conform to parent `FR-008a`, and that every harness UI surface (dashboard, detail view, export) handles the results correctly.

**Acceptance Scenarios**:

1. **Given** a fresh harness install with no real evaluation agents registered, **When** the tester opens the wizard, **Then** MockEvaluationAgent appears in Step 4's picker as a fully-functional choice.
2. **Given** MockEvaluationAgent is selected, **When** the wizard renders Step 4's config form, **Then** the form is minimal but valid; the tester can advance past Step 4 with zero secrets entered.
3. **Given** a job using MockEvaluationAgent, **When** `evaluate()` is invoked for any contract instance, **Then** the agent returns an EvaluationResult with: well-formed `scores` entries matching the declared dimensions (with randomized score values within a documented range, e.g., 0.0 to 1.0); a randomized `verdict` chosen from `{pass, fail, warn}`; a non-empty `reasoning` string (e.g., "Mock evaluation — randomized for testing"); a non-null `metadata` object.
4. **Given** repeated invocations of MockEvaluationAgent on identical input, **When** the test compares outputs, **Then** the outputs are observably non-identical across invocations (consistent with the non-determinism guarantee per US4) — verifying both that the agent is being re-invoked AND that the agent itself is non-deterministic.

---

### Edge Cases

- An evaluation agent's `evaluate()` raises an exception — the orchestrator records the per-row failure with stage `evaluation` (per parent `FR-017`); subsequent rows proceed (per parent `FR-016`).
- An evaluation agent's `evaluate()` returns an object missing one of the required EvaluationResult fields — the orchestrator MUST reject the malformed result, record the row as failed with stage `evaluation` and an actionable detail naming the missing field; subsequent rows proceed.
- An evaluation agent returns a `verdict` value not in the closed enum `{pass, fail, warn}` (e.g., `"inconclusive"`, `"needs-review"`) — the orchestrator MUST reject the result, record the row as failed with stage `evaluation` and a detail naming the invalid verdict value; subsequent rows proceed.
- An evaluation agent returns scores whose entries do NOT conform to the `{parameter_name, score, reasoning}` shape (e.g., missing `reasoning`, wrong types) — the orchestrator MUST reject the result, record the row as failed with stage `evaluation` and a detail naming the offending entry path; subsequent rows proceed.
- An evaluation agent returns scores entries whose `parameter_name` values include some that ARE in the agent's declared scoring dimensions and some that are NOT — the agent's output is persisted unchanged, AND the harness writes `harnessAnnotations.unexpected_score_dimensions: [...]` (see `FR-005a`) listing the unexpected names. The agent's own `metadata` field is NOT mutated by the harness. This is a SOFT warning, not a hard failure.
- An evaluation agent is unregistered between when a job was created and when the orchestrator picks it up — the orchestrator MUST detect this at startup, mark the job `failed` with a clear "evaluation agent no longer registered" message, mirror of `specs/003-job-creation-wizard` → `FR-016` and `specs/007-connector-framework` edge case.
- An evaluation agent's declared scoring dimensions are empty (zero dimensions) — the agent MUST still emit a `verdict`, `reasoning`, and an empty `scores` array on every `evaluate()` call; this is valid (e.g., a purely-verdict-based agent like a binary safety classifier).
- An evaluation agent declares a scoring dimension whose name contains characters that would need special handling in CSV (commas, quotes, newlines) — the framework MUST accept the declaration; downstream consumers (`005` export) handle CSV escaping per their existing rules.
- An evaluation agent declares it accepts only certain `contractVersion` values (parent `FR-020`) but the harness's bundled contract is a different version — caught by the wizard's Step 4 compatibility check (`specs/003-job-creation-wizard` → `FR-014`) before the job starts; the framework does NOT re-check at runtime.
- The harness restarts mid-evaluation of a row — the row's persisted state is whatever was committed before the restart (likely the connector's contract is persisted but the EvaluationResult is not); on next startup, parent `FR-022` reconciles the orphaned job; the row is left as `failed` with stage `evaluation` (or whatever the orchestrator's restart policy is — parent-spec concern, not Module 7).
- An evaluation agent's `evaluate()` returns an `evaluationTimestamp` in the future, or wildly in the past, or in a non-ISO-8601 format — the orchestrator MUST treat the row as failed with stage `evaluation` and an actionable detail naming the timestamp problem (mirrors `specs/006-evaluation-contract` → `FR-013`).
- Two concurrent jobs use the same evaluation agent — each job MUST have its own independent agent invocation context; the framework MUST NOT share state across concurrent jobs (mirrors `specs/007-connector-framework` → `FR-007`).

## Requirements *(mandatory)*

### Functional Requirements

#### Evaluation Agent Interface

- **FR-001**: The framework MUST define an Evaluation Agent Interface that every evaluation agent MUST implement. The interface MUST consist of exactly one behavioral method: `evaluate`. The literal language-binding shape (sync vs. async, function vs. class) is plan-level.
- **FR-002**: `evaluate(contract)` MUST accept a Standard Evaluation Contract instance (as defined by `specs/006-evaluation-contract/spec.md`) that has already been validated by the harness against the bundled schema. The agent MAY assume the contract is well-formed and MUST NOT re-validate the contract itself.
- **FR-003**: `evaluate(contract)` MUST return an `EvaluationResult` — a JSON-serializable object carrying exactly the following required top-level fields:
  - `utteranceId` (string) — MUST exactly equal the input contract's `utteranceId`. Echoed for traceability.
  - `evaluationAgentId` (string) — MUST exactly equal the agent's registered id.
  - `evaluationTimestamp` (string) — ISO-8601 / RFC 3339-compatible datetime, indicating when the agent produced this result.
  - `scores` (array) — an ordered collection of zero or more entries, each entry conforming to parent `FR-008a`'s shape: `{ parameter_name: string, score: number-or-short-string, reasoning: string }`.
  - `verdict` (string) — exactly one of the closed enum values `"pass"`, `"fail"`, `"warn"`.
  - `reasoning` (string) — natural-language explanation justifying the verdict (and, taken together with the per-entry `reasoning` fields in `scores`, the full evaluation). Empty string permitted only when the agent has no meaningful explanation; the field MUST be present.
  - `metadata` (object) — agent-specific extra structured data (e.g., model name and version used internally, total token cost, latency, retrieval document references). Free-form; the framework does NOT constrain its keys. Empty object `{}` is valid.
- **FR-004**: The `verdict` field MUST be one of exactly three string values: `"pass"`, `"fail"`, `"warn"`. Any other value MUST cause the EvaluationResult to be rejected with stage `evaluation`. `warn` is OPTIONAL for an agent to ever emit; if an agent never produces ambiguous results, it MAY use only `pass` and `fail`. But if an agent does produce a `warn`, the string MUST be exactly `"warn"` (lowercase, no whitespace, no variants).
- **FR-005**: The `scores` array MUST follow parent `FR-008a` exactly — every entry MUST be an object with the three fields `parameter_name`, `score`, `reasoning`. Empty array `[]` is valid (e.g., a purely-verdict-based agent). Each `parameter_name` SHOULD be one of the agent's declared scoring dimensions (per `FR-008` of this spec); entries with `parameter_name` values NOT in the declared dimension list are PERSISTED but trigger a soft warning recorded in the harness annotation block defined by `FR-005a`.
- **FR-005a**: The harness MUST persist EvaluationResults with a top-level **`harnessAnnotations`** object alongside (not nested inside) the agent's `metadata` field. This block holds annotations the harness derives post-evaluate from the agent's output — it is NEVER written by the agent. In v1 the harness writes at minimum:
  - `unexpected_score_dimensions` (array of strings) — listing any `parameter_name` values present in `scores` but NOT declared by the agent. Omitted (or empty array) when the agent's output is fully aligned with its declaration.
  
  The block is otherwise extensible: future spec revisions MAY add more harness-derived annotation keys without bumping any contract version (the harness-annotations block is harness-internal and is not part of any consumer-facing contract). Downstream consumers (`004` detail view, `005` export) MUST treat `harnessAnnotations` as informational; they MUST render or expose it visibly (so the tester understands the soft warning) but they MUST NOT use it to gate any other behavior.
- **FR-005b**: Validation of the EvaluationResult MUST hard-reject the row (mark `failed` with stage `evaluation` per parent `FR-017`) when ANY of the following hold:
  - `utteranceId` in the result does not exactly equal the input contract's `utteranceId` (per `FR-003`'s echo requirement).
  - `evaluationAgentId` in the result does not exactly equal the registered agent's id (per `FR-003`'s echo requirement).
  - `verdict` is not one of `"pass"` / `"fail"` / `"warn"` (per `FR-004`).
  - Any required EvaluationResult field is missing or has the wrong top-level type.
  - Any `scores` entry is not an object, or is missing one of `parameter_name` / `score` / `reasoning`, or any of those fields has the wrong type.
  - `evaluationTimestamp` is not a valid ISO-8601 string.
  
  These are sanity-check rejections, distinct from the soft-warning case in `FR-005`/`FR-005a` (unexpected-but-structurally-valid score names). The failure detail MUST name the specific check that failed and the offending value where applicable.
- **FR-006**: The framework MUST NOT inject any init / teardown method beyond `evaluate()`. Agents that need expensive setup (loading model weights, opening LLM clients) MUST manage their own internal lifecycle — lazy initialization on first call, internal caching of stateful resources, cleanup on garbage collection or process shutdown. The framework MUST NOT make any promises about when or how often it will invoke `evaluate()` on the same agent instance.

#### Evaluation Agent Registry

- **FR-007**: The framework MUST provide an **Evaluation Agent Registry** — a service that maintains a catalog of all currently-registered evaluation agents. The registry MUST be the single source of truth for "which evaluation agents does this harness installation know about?"
- **FR-008**: Each evaluation agent MUST self-register with the registry. Registration MUST require the agent to supply: (a) a unique `evaluationAgentId` string, (b) a human-readable display name, (c) a human-readable description of what the agent evaluates and how, (d) a JSON Schema describing the agent's configuration fields (including which are required and which are secret), (e) an ordered list of declared scoring dimensions (the `parameter_name` values the agent expects to emit in its `scores` array, in the order they should be rendered), and (f) a handle or factory by which the framework can obtain an instance to invoke `evaluate()` on.
- **FR-009**: The registry MUST reject duplicate `evaluationAgentId` registration with an actionable error; the first-registered agent for a given id MUST remain in place.
- **FR-010**: The registry MUST reject registration when (a) the supplied config JSON Schema is invalid, (b) `evaluate()` is missing from the supplied implementation handle, (c) `evaluationAgentId` is empty or already in use, (d) the declared scoring-dimensions list is not a list of strings.
- **FR-011**: The registry MUST expose at minimum the following query affordances: (a) **list all registered agents** (returning at least each agent's id, display name, description), (b) **retrieve an agent by id** (returning enough to invoke `evaluate()` on it, or an explicit "not found" result), (c) **retrieve the configuration schema for a given agent id** (so the wizard's Step 4 form can render — per `specs/003-job-creation-wizard` → `FR-012`), (d) **retrieve the declared scoring dimensions for a given agent id** (so the wizard, detail view, and export can pre-render columns / expectations).
- **FR-012**: The registry MUST be queryable by the wizard (at job-creation time), the orchestrator (at job-execution time), the detail view (`004`), and the export service (`005`); all surfaces MUST see the same set of registered agents at any given moment.
- **FR-013**: The framework MUST support adding new evaluation agents **without modifying** the core harness code, the registry implementation, the orchestrator, the wizard, the dashboard, the detail view, the export service, the contract, the connector framework, any other existing evaluation agent, or any existing connector. The discovery / loading mechanism by which a new agent reaches the registry is plan-level (Python entry points, file-system scan, manifest file); the spec requires only that adding an agent is zero-touch on existing modules.

#### Non-determinism guarantee

- **FR-014**: The framework MUST treat every `evaluate()` invocation as a fresh evaluation. The framework MUST NOT cache evaluation results, MUST NOT deduplicate calls based on input-contract-content equality, MUST NOT memoize based on `utteranceId`, MUST NOT use any "we already evaluated this row" shortcut. Every invocation that reaches the framework's `evaluate()` boundary MUST be passed through to the agent.
- **FR-015**: Consumers of EvaluationResults (the detail view, the export, downstream tooling) MUST NOT assume that two evaluations of the same contract content produce identical (or even similar) verdicts, scores, or reasoning. The harness's documentation, UI affordances, and export annotations SHOULD make this explicit where relevant (e.g., the detail view's expand-on-click full trace shows the timestamp of evaluation alongside the result, signaling that this result is the agent's judgment *at that moment*, not a stable fact).
- **FR-016**: The same `evaluationAgentId` MAY be invoked many times within the same job (once per row) and MAY produce different verdict / scores / reasoning each time. The framework treats this as expected behavior, not as an inconsistency.

#### Secret config field handling

- **FR-017**: Configuration fields the agent declares as secret in its JSON Schema (e.g., the LLM API key the agent uses internally) MUST be persisted at rest in encrypted form per parent `FR-023a` and `specs/007-connector-framework` → `FR-015`–`FR-019`. The same machine-local symmetric key utility is shared; the framework does NOT introduce a separate encryption utility for evaluation agents.
- **FR-018**: Decrypted secrets MUST be passed to the agent only at the moment they are needed (typically when the agent makes its first LLM call within a job); they MUST NOT appear in UI rendering (per `specs/004-job-detail-view` → `FR-005`), in exports (per `specs/005-results-export` → `FR-011`), or in application logs.

#### Concurrency

- **FR-019**: Within a single job, the framework MUST serialize `evaluate()` calls on the same agent instance — at most one call MAY be in flight at any moment. Agent authors MUST NOT be required to make their agents thread-safe or async-safe. This pins parent's "max concurrent in-flight rows per job" tuning value to **1** for v1, consistent with `specs/007-connector-framework` → `FR-007a`.
- **FR-020**: Concurrent jobs (per parent `FR-011`) using the same evaluation agent MUST each receive an independent invocation context — the framework MUST NOT share agent state across concurrent jobs. (For agent implementations that cache stateful resources internally, this means: caching is OK within a job; it MUST NOT bleed across jobs.)

#### MockEvaluationAgent reference implementation

- **FR-021**: The framework MUST ship a **MockEvaluationAgent** reference implementation. MockEvaluationAgent MUST be registered in the Evaluation Agent Registry by default in a stock harness installation (no extra setup required by the tester).
- **FR-022**: MockEvaluationAgent's `evaluate()` MUST return a well-formed EvaluationResult on every call, with:
  - `utteranceId` correctly echoing the input contract.
  - `evaluationAgentId` matching its registered id (e.g., `"mock-evaluator"`).
  - `evaluationTimestamp` set to the current moment in ISO-8601.
  - `scores` an array of entries matching its declared scoring dimensions, with randomized `score` values within a documented range (e.g., 0.0–1.0) and short randomized `reasoning` strings.
  - `verdict` randomized from the closed enum `{pass, fail, warn}`.
  - `reasoning` a non-empty string (e.g., `"Mock evaluation — values randomized for testing."`).
  - `metadata` a non-null object (e.g., `{ mock: true }`).
- **FR-023**: MockEvaluationAgent MUST declare a non-empty scoring-dimensions list (e.g., `["mock_dimension_a", "mock_dimension_b"]`) so US3's dimension-declaration plumbing is exercised in the default install.
- **FR-024**: MockEvaluationAgent MUST have no required config fields, so the wizard's Step 4 can be advanced past it with zero tester input. Optional fields (e.g., a "score range" knob) MAY be declared.
- **FR-025**: MockEvaluationAgent's randomization MUST produce observably different output across successive calls on identical input — exercising and verifying the non-determinism guarantee (US4) by construction.
- **FR-026**: MockEvaluationAgent MUST be safe to use in unit, integration, and end-to-end tests of every other harness module without requiring network access, real LLM credentials, or any out-of-process dependency.

### Key Entities *(include if feature involves data)*

- **Evaluation Agent**: An implementation of the single-method interface (`evaluate`) that consumes a Standard Evaluation Contract and produces an EvaluationResult. Carries: `evaluationAgentId` (unique string), display name, description, config JSON Schema (with secret-field annotations), declared scoring dimensions (ordered list of strings), implementation handle. Self-registers with the Evaluation Agent Registry. Snapshotted (identity + config + declared dimensions) onto the Test Job at job-creation time (parent `FR-023`).
- **Evaluation Agent Registry**: The catalog of all currently-registered evaluation agents in the harness installation. Single source of truth for "what evaluation strategies can a tester pick?" in the wizard and "which agent does the orchestrator invoke?" at runtime. Queryable by id and as a list; returns config schemas and dimension lists for UI rendering.
- **EvaluationResult**: The structured output of `evaluate()`. Carries the seven required fields enumerated in `FR-003`. The persisted record adds a `harnessAnnotations` block (per `FR-005a`) alongside the agent's `metadata` field. Distinct from (but feeding into) the parent's `Evaluation Result` data entity, which is the persisted record that also carries the per-row timestamps, the stage where the agent failed (if any), and the linkage to the parent job.
- **Declared Scoring Dimensions**: An agent's upfront promise of what `parameter_name` values it will populate in its scores array. Ordered list of strings. Consumed by the wizard's Step 4 (informational display), the detail view (pre-render placeholders before a row is evaluated; canonical column order), and the export (canonical column order in CSV; canonical key order in JSON).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A job using a registered evaluation agent produces a persisted EvaluationResult per row whose seven required fields are all populated with valid values per `FR-003` — verifiable by running an end-to-end test against MockEvaluationAgent and inspecting every persisted row.
- **SC-002**: Adding a brand-new evaluation agent requires **zero modifications** to any existing file outside of (a) the new agent's own module and (b) the registration manifest (or equivalent plan-defined registration mechanism) — verifiable by `git diff` showing the change set is entirely additive on existing files.
- **SC-003**: The Evaluation Agent Registry's "list all", "get by id", "get config schema", and "get scoring dimensions" affordances return the same data regardless of which harness surface (wizard, orchestrator, detail view, export) is asking — verifiable by querying from each surface and comparing results.
- **SC-004**: An agent that declares scoring dimensions `[A, B, C]` and emits scores entries `[B, A, C]` (correct names, different order) has its scores rendered in the declared order `[A, B, C]` by the detail view and export — verifiable by inspection of the rendered UI and exported file.
- **SC-005**: The same agent invoked twice on identical input within the same job (e.g., a job with two CSV rows that have identical utterance + testId) produces two persisted EvaluationResults whose verdict, scores, or reasoning differ in at least one observable way — verifiable by running such a job against MockEvaluationAgent and diffing the two results.
- **SC-006**: There is no code path within the framework between the orchestrator and the agent's `evaluate()` method that caches, dedupes, or short-circuits invocations — verifiable by code review or by instrumenting the agent to count calls and asserting count equals row count.
- **SC-007**: An agent whose `evaluate()` returns a malformed EvaluationResult (wrong verdict value, missing required field, scores entry that doesn't match parent `FR-008a`) causes the affected row to be recorded as failed with stage `evaluation` and an actionable detail; subsequent rows proceed — verifiable by instrumenting MockEvaluationAgent to emit malformed output on row 3 of a 5-row job and inspecting the persisted state.
- **SC-008**: Concurrent jobs (per parent `FR-011`) using the same evaluation agent identifier do not share state — verifiable by running two simultaneous jobs against an instrumented MockEvaluationAgent and confirming each job's call counts and results are independent.
- **SC-009**: An evaluation agent whose `evaluate()` raises is treated as a per-row failure with stage `evaluation`; the job is NOT aborted; remaining rows are processed — verifiable per parent `FR-016`, `FR-017` plus this spec's edge cases.
- **SC-010**: An agent's declared scoring dimensions list is retrievable from the registry independently of any running job — verifiable by registering an agent, calling the dimension-query affordance, and asserting the returned list matches the declaration.
- **SC-011**: MockEvaluationAgent is usable in a brand-new harness install with zero additional setup, requires no API keys or network access, and produces observably non-deterministic output across runs — verifiable by clean-install end-to-end testing.
- **SC-012**: Secret-declared config fields on evaluation agents (e.g., the LLM API key) never appear in plaintext in the database file, in any export, or in the rendered detail page — verifiable by the same end-to-end test as `specs/007-connector-framework` → `SC-004` but with an evaluation agent in place of a connector.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth, no `createdBy` anywhere.
- The Standard Evaluation Contract is fully defined in `specs/006-evaluation-contract/spec.md`. This spec depends on it but does not redefine it.
- The connector framework (`specs/007-connector-framework`) defines the producer side of the same integration seam. The Module 7 spec is the consumer side; together they make the pluggability model complete.
- The wizard's Step 4 (`specs/003-job-creation-wizard` → `FR-011`–`FR-014`) consumes the registry's "list", "get config schema", "get scoring dimensions", and contract-version compatibility check. The wizard does NOT introspect agent internals beyond those affordances.
- The orchestrator (Module 10, TBD) consumes the registry's "get by id" affordance plus the single `evaluate()` method.
- The framework's agent discovery / loading mechanism is plan-level (Python entry points vs. file-system scan vs. manifest); the spec requires only zero-touch-on-existing-modules.
- The encryption story for config-level secrets is inherited from parent `FR-023a` and Module 4's encryption utility (`specs/007-connector-framework` → `FR-015`–`FR-019`). The Module 7 framework does NOT introduce its own encryption utility; it reuses what's there.
- Connection-style lifecycle (init / teardown) is intentionally NOT part of this framework's interface. Agents that need expensive setup manage it internally via lazy initialization and per-process caching. Future work MAY add explicit `initialize` / `shutdown` methods if real-world experience justifies the additional complexity.
- The closed verdict enum `{pass, fail, warn}` is sufficient for v1. Future contract-shape changes that add new verdict values would be a breaking change to the EvaluationResult shape and would require a new harness major version. (This spec does not define a result-shape version; the contract has a version, but the result's shape is fixed at the harness level for now.)
- "Declared scoring dimensions" is a soft promise — agents emit what they emit, and the harness annotates rather than rejects when emitted dimensions diverge from declared. This keeps the system robust to evaluator drift while preserving the UI/export benefit of upfront declaration.
- MockEvaluationAgent's randomization is unseeded by default (truly non-deterministic); plan-level decisions MAY include an optional config knob for seeded determinism if test authors find unpredictable output annoying. The spec only requires that the default behavior exercises the non-determinism guarantee.
- The framework does NOT define a "Standard Evaluation Result Contract" version separate from the Standard Evaluation Contract. The EvaluationResult shape is harness-canonical and changes only when the harness itself ships a major version. Evaluators authoring against this spec follow `FR-003`'s shape exactly.
