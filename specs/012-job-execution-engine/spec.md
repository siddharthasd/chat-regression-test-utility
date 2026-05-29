# Feature Specification: Job Execution Engine (Module 10)

**Feature Branch**: `012-job-execution-engine`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 10 — Job Execution Engine. Picks up queued jobs and runs the per-row pipeline end-to-end: instantiate connector + evaluator using snapshotted config; for each Utterance in `rowIndex` order, call `sendUtterance` → `normalize` → `evaluate` → persist ExecutionResult; catch and isolate per-row failures; update counters; on completion set `completedAt` and transition status to terminal. Runs asynchronously (start API returns immediately). Multiple jobs run concurrently with independent connector + evaluator instances per job. Fatal pre-row errors mark the Job `failed`."

> **Parent context**: This module is **the orchestrator** — the loop that turns a queued Job into a persisted set of ExecutionResults. It consumes every framework spec'd so far: the snapshotted config from `009 FR-001` / `009 FR-005` (via parent `FR-023`), the connector interface from `007` (`connect` → per-row `sendUtterance` → `normalize` → `disconnect`), the evaluator interface from `008` (`evaluate`), the in-memory password store from `011 FR-015`, the per-row ExecutionResult shape from `009 FR-003`, and the cancellation rules from parent `FR-024` (with stub creation per `009 FR-003a`). It is the runtime enforcement point for parent `FR-016`/`FR-017` (per-row failure isolation), `FR-025` (no retries at orchestrator layer), `FR-022` (orphan reconciliation), and the partial-completion semantics. Parent-spec premises apply: single-user, single-process, no auth. The Module 10 input's mention of `CompletedWithErrors` as a terminal state was dropped by precedent — terminal status is always `completed` regardless of `failedCount`, with the "Completed with errors" rendering being a UI label per `004` (per `009 Q2`). The user's "Module 10" maps to our `012-` directory by the convention used for prior modules.

## Clarifications

### Session 2026-05-29

- Q: Parent `FR-022` requires orphaned `running` jobs (left over from a crash/restart) to be reconciled to a deterministic terminal or paused state. The current canonical enum has no `paused`. How should the engine reconcile them? → A: **Transition to `failed`.** The engine, at process startup, scans the database for any Job whose persisted `status == running` (or `cancelling`), and atomically transitions each to `failed` with an explanatory `errorDetails` value (e.g., `"harness restarted while job was running"`) on the Job. No new lifecycle state is introduced; no parent enum amendment is needed. Recovery path: tester creates a new Job and re-uploads the CSV (per parent `FR-010a`'s "tester-visible state requires explicit re-upload"). The in-memory password store entries for the orphaned job — if any — are cleared as part of reconciliation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute a queued job end-to-end through the pipeline (Priority: P1)

The wizard's "Start Job" click (per `003 FR-017`) atomically transitions a Job from `draft` to `queued` and emits an enqueue signal. The engine, running asynchronously in the harness process, picks up the queued Job, transitions it to `running`, instantiates the snapshotted connector (decrypting any secret-declared config fields via Module 4's utility per parent `FR-023a`), calls `connect()` once, instantiates the snapshotted evaluation agent similarly, then iterates the Job's persisted Utterance rows in `rowIndex` order. For each row, it looks up the password from the in-memory store (per `011 FR-015`), calls `sendUtterance(handle, originalText, testId, password)`, calls `normalize(rawResponse)` to obtain a Standard Evaluation Contract instance (validated per `006`), calls `evaluate(contract)`, and persists a complete ExecutionResult atomically with `processedCount` and (if applicable) `failedCount` updates. Per-row password is evicted from the store immediately after `sendUtterance` returns. After the last row, the engine calls `disconnect()`, sets `completedAt`, transitions status to `completed`, and clears any remaining password store entries for the Job.

**Why this priority**: This is the entire purpose of Module 10. Without it, every preceding spec is just plumbing with no payload. It is the MVP slice.

**Independent Test**: With a Job in `queued` status carrying 5 Utterance rows + matching in-memory password store entries, a snapshotted MockConnector config (`007 FR-021`–`FR-024`), and a snapshotted MockEvaluationAgent config (`008 FR-021`–`FR-026`), trigger the engine. Verify: (a) `connect()` called exactly once with the decrypted config; (b) `sendUtterance` called exactly 5 times in `rowIndex` order with correct per-row arguments; (c) `normalize` called once per row; (d) `evaluate` called once per row with a contract that validates per `006`; (e) `disconnect()` called exactly once after the last row; (f) 5 ExecutionResult records persisted with `errorStatus == null` and `evaluationVerdict` populated; (g) Job ends with `processedCount == 5`, `failedCount == 0`, `completedAt` set, `status == completed`; (h) the in-memory password store contains zero entries for that Job at completion.

**Acceptance Scenarios**:

1. **Given** a Job in `queued` status with N Utterance rows, snapshotted connector + evaluator config, and N matching entries in the in-memory password store, **When** the engine picks up the Job, **Then** the Job transitions `queued → running`, `startedAt` is recorded (if not already set by the wizard), and the orchestration loop begins.
2. **Given** the engine is processing row K, **When** it looks up the row's password, **Then** the lookup retrieves the entry from the in-memory store keyed by `(jobId, utteranceId)`; the password is passed to `sendUtterance` and the store entry is removed immediately after `sendUtterance` returns (success or failure).
3. **Given** every row of an N-row Job completes successfully, **When** the engine finishes the loop, **Then** the Job's `processedCount == N`, `failedCount == 0`, `completedAt` is set, `status == completed`, and `disconnect()` has been called exactly once.
4. **Given** the Job completes (any terminal status), **When** the engine wraps up, **Then** the in-memory password store contains zero entries keyed by that Job's `jobId`.

---

### User Story 2 - Isolate per-row failures; the job continues (Priority: P1)

A row's `sendUtterance` raises, or `normalize` returns a non-conforming contract instance, or `evaluate` returns a malformed EvaluationResult. The engine catches the error, persists an ExecutionResult for that row with `errorStatus = "failed"`, `errorStage = "connector" | "normalization" | "evaluation"` (per parent `FR-017`), and `errorDetails` carrying the captured message; increments the Job's `failedCount`; and proceeds to the next row. The connector's `ConnectionHandle` is NOT torn down — it remains usable for subsequent rows (per `007 FR-006`). The Job continues even if every row fails — the terminal status is still `completed` (with `failedCount == totalUtteranceCount`), not `failed`.

**Why this priority**: This is the "regression-test-tool resilience" property. Without it, one flaky row torpedoes the whole run. Equal-priority with US1 because both are required for the engine to deliver value.

**Independent Test**: With a job whose Utterance rows include some that the stub connector / evaluator is instrumented to fail in different ways — row 2 fails at `sendUtterance`, row 3 returns a normalization-violating contract, row 4 returns a malformed EvaluationResult — verify: (a) 5 ExecutionResults are persisted (one per row), (b) rows 2/3/4 have `errorStatus = "failed"` with the correct `errorStage` and `errorDetails`, (c) rows 1 and 5 have `errorStatus = null` and complete evaluation data, (d) `processedCount == 5`, `failedCount == 3`, `completedAt` set, `status == completed`, (e) the connector's `ConnectionHandle` survived all 5 rows (no mid-job reconnect attempted), (f) `disconnect()` called exactly once.

**Acceptance Scenarios**:

1. **Given** a row whose `sendUtterance` raises an exception, **When** the engine catches it, **Then** an ExecutionResult is persisted for that row with `errorStatus = "failed"`, `errorStage = "connector"`, `errorDetails` carrying the captured exception message, and the Job's `failedCount` is incremented atomically.
2. **Given** a row whose `normalize` returns an object that fails Standard Evaluation Contract validation (per `006 FR-008`), **When** the engine detects the violation, **Then** an ExecutionResult is persisted with `errorStatus = "failed"`, `errorStage = "normalization"`, `errorDetails` carrying the per-field violation list (per `006 FR-009`); `failedCount` is incremented.
3. **Given** a row whose `evaluate` returns a malformed EvaluationResult (per `008 FR-005b`), **When** the engine detects the malformation, **Then** an ExecutionResult is persisted with `errorStatus = "failed"`, `errorStage = "evaluation"`, `errorDetails` carrying the specific malformation cause; `failedCount` is incremented.
4. **Given** any per-row failure, **When** the engine handles it, **Then** the next row is processed; the connector's `ConnectionHandle` is not torn down or recreated mid-job; the in-memory password store entry for the failed row is still evicted (the failure happened after `sendUtterance` was invoked).
5. **Given** a Job where EVERY row fails, **When** the engine completes the loop, **Then** the Job's `processedCount == totalUtteranceCount`, `failedCount == totalUtteranceCount`, terminal status `completed` (NOT `failed`); the dashboard / detail view render this as "Completed with errors" per `004 FR-005`.

---

### User Story 3 - Honor the soft-cancel sequence mid-run (Priority: P2)

The tester clicks Cancel on a `running` Job from the Job Detail View (per `004 FR-018`). The engine detects the cancel signal, allows the currently-in-flight row's `sendUtterance` / `normalize` / `evaluate` pipeline to run to natural completion or failure (per parent `FR-024`), then stops invoking further rows. Remaining queued Utterances get ExecutionResult stubs created by the data layer (per `009 FR-003a`) with `errorStatus = "cancelled"`. The engine calls `disconnect()` on the connector, transitions the Job from `cancelling → cancelled`, sets `completedAt`, and clears the in-memory password store for the Job.

**Why this priority**: Cancel is the primary UX escape hatch for runaway jobs. Equal-priority with US4/US5 because cancellation, restart-recovery, and concurrency are all P2 robustness layers on top of the P1 happy/per-row-fail paths.

**Independent Test**: Start a job with 10 long-running rows (artificial delay in MockConnector). Mid-run, after row 4 starts but before row 5, trigger Cancel. Verify: (a) row 4 finishes naturally and gets a normal ExecutionResult (not cancelled); (b) rows 5–10 get cancellation-stub ExecutionResults (per `009 FR-003a`); (c) Job's `processedCount` counts rows 1–4 (per `009 FR-001`'s definition that excludes `cancelled`); (d) `failedCount == 0` if rows 1–4 succeeded; (e) `disconnect()` called exactly once; (f) Job transitions through `running → cancelling → cancelled` atomically with the stub creation; (g) the in-memory password store is empty for the Job after cancellation.

**Acceptance Scenarios**:

1. **Given** a `running` Job whose tester has clicked Cancel, **When** the engine receives the signal, **Then** the engine transitions the Job's status to `cancelling`; the in-flight row's pipeline runs to natural completion (success or failure) and its ExecutionResult is persisted normally.
2. **Given** the in-flight row has completed (the Job is in `cancelling`), **When** the engine considers the next row, **Then** the engine STOPS — no further `sendUtterance` calls are made; the data layer's atomic `cancelling → cancelled` transition creates ExecutionResult stubs for every remaining Utterance (per `009 FR-003a`).
3. **Given** the cancellation completes, **When** the engine wraps up, **Then** `disconnect()` is called exactly once, `completedAt` is set, status is `cancelled`, and the in-memory password store contains zero entries for the Job.
4. **Given** a Cancel signal arrives AFTER the engine has already begun the `running → completed` transition (race), **When** the data layer applies updates, **Then** the cancel is refused (the Job is already terminal) and the tester is shown an actionable message per `004 FR-018`'s race-edge case.

---

### User Story 4 - Reconcile orphaned `running` / `cancelling` jobs at process startup (Priority: P2)

A previous harness run crashed or was killed mid-job. On restart, the database holds at least one Job in `running` or `cancelling` status whose orchestrator process no longer exists. The engine, before doing any other work, scans for such jobs and atomically marks each `failed` with an explanatory `errorDetails`. The in-memory password store for those orphaned jobs is empty (it didn't survive the restart per `011 FR-015`'s process-exit-clear rule); per parent `FR-010a`, recovery requires the tester to re-upload the CSV against a new Job.

**Why this priority**: Without reconciliation, every crashed harness leaves a "stuck running" Job in the database that the dashboard shows confusingly forever. Equal-priority with US3/US5.

**Independent Test**: Manually set a Job's persisted status to `running` (simulating a crash mid-job). Boot the harness. Verify: (a) within 5 seconds of startup, the Job's status transitions to `failed` with `errorDetails` carrying a clear orphan-recovery message; (b) the Job's `completedAt` is set; (c) the in-memory password store contains zero entries for that Job; (d) the dashboard shows the Job as `failed` (per `002 FR-004`); (e) the tester can create a new Job and re-upload the CSV to retry.

**Acceptance Scenarios**:

1. **Given** the harness process starts, **When** the engine performs its orphan-reconciliation pass, **Then** it queries the data layer for every Job whose `status` is `running` or `cancelling`, and atomically transitions each to `failed` with `errorDetails` set to a clear orphan-recovery message (e.g., `"harness restarted while job was running; create a new job to retry"`) and `completedAt` set to the current moment.
2. **Given** the orphan reconciliation has completed, **When** any other module reads or writes persistent state, **Then** no Job is in `running` or `cancelling` status — they have all been reconciled. This matches parent `SC-008`'s "no job remains in `running` after restart within 5 seconds."
3. **Given** an orphaned Job had ExecutionResult stubs created mid-run, **When** the orphan reconciliation runs, **Then** any existing ExecutionResults are preserved as-is (they reflect rows that did execute before the crash); only the Job's status changes. No retroactive stub creation runs.

---

### User Story 5 - Run multiple jobs concurrently without interference (Priority: P2)

The tester starts Job A; the engine begins processing. Before A finishes, the tester starts Job B. The engine picks up B and runs it concurrently. Each Job has its own `ConnectionHandle` (per `007 FR-007`), its own agent invocation context (per `008 FR-020`), and its own in-memory password store entries. Each Job's `processedCount` / `failedCount` / `status` updates independently. Per `007 FR-007a` and `008 FR-019`, rows within each Job are serialized — but two Jobs' rows can be in flight simultaneously.

**Why this priority**: Comparative testing — running two configurations side by side against the same CSV — is the harness's headline use case (per parent User Story 3). Without concurrent execution, the harness becomes a one-at-a-time bottleneck.

**Independent Test**: Start two Jobs simultaneously (or as close as possible). Verify: (a) both have `status == running` at the same time, (b) each has independent ExecutionResults accumulating, (c) each has its own `processedCount` ticking up independently, (d) closing or cancelling one Job does not affect the other, (e) terminal status of one Job is reached without waiting for the other.

**Acceptance Scenarios**:

1. **Given** two Jobs both in `queued` status when the engine boots (or are enqueued in close succession), **When** the engine picks them up, **Then** each Job gets its own `ConnectionHandle` (independent `connect()` calls per `007 FR-007`) and its own agent invocation context (independent state per `008 FR-020`).
2. **Given** two concurrent running Jobs use the same connector identity (e.g., both use the same registered MS Copilot Studio connector), **When** they execute concurrently, **Then** each receives its own `ConnectionHandle`; no shared state leaks between them.
3. **Given** two concurrent running Jobs, **When** one is cancelled, **Then** the other continues unaffected — `disconnect()` is called only for the cancelled Job's handle, not the running one's.
4. **Given** two concurrent running Jobs A and B, **When** Job A's status updates (e.g., to `cancelling`), **Then** Job B's status is unchanged; the in-memory password store keyed by A's `jobId` is cleared independently of B's entries.

---

### User Story 6 - Fail the Job cleanly when pre-row setup fails (Priority: P3)

The engine picks up a `queued` Job but cannot proceed — the snapshotted connector is no longer registered in the Connector Registry, OR the snapshotted evaluator is unregistered, OR `connect()` raises (bad config, unreachable endpoint), OR decryption of secret config fields fails (machine-local key missing/wrong per parent `FR-023a`), OR the in-memory password store is empty for this Job. In every case, the engine atomically transitions the Job to `failed` with `errorDetails` naming the specific failure cause, sets `completedAt`, calls `disconnect()` if a `ConnectionHandle` was obtained, and DOES NOT invoke any per-row pipeline.

**Why this priority**: Pre-row failures are rare (most are caught at job-creation time by the wizard's compatibility check per `003 FR-014` / `FR-016`) but they're real: connectors get unregistered between job creation and execution; key files get deleted; networks go down. The engine must fail cleanly rather than crash, hang, or leave the Job in `running`.

**Independent Test**: For each pre-row failure mode in turn, trigger it and verify: (a) the Job's terminal status is `failed`, (b) `errorDetails` names the specific failure mode, (c) `completedAt` is set, (d) no ExecutionResult rows exist for that Job's Utterances (no pipeline was invoked), (e) `disconnect()` was called only if `connect()` had previously succeeded, (f) the in-memory password store is empty for that Job.

**Acceptance Scenarios**:

1. **Given** a `queued` Job whose snapshotted `connectorType` is no longer present in the Connector Registry, **When** the engine picks up the Job, **Then** the Job transitions to `failed` with `errorDetails` naming the missing connector id; no `connect()` is attempted; no ExecutionResults are created.
2. **Given** the snapshotted `evaluationAgentId` is no longer present in the Evaluation Agent Registry, **When** the engine picks up the Job, **Then** the Job transitions to `failed` with `errorDetails` naming the missing agent id; no per-row pipeline runs.
3. **Given** decryption of a secret-declared config field fails (per parent `FR-023a` / `007 FR-018`), **When** the engine attempts to instantiate the connector or evaluator, **Then** the Job transitions to `failed` with `errorDetails` carrying the "machine-local key missing or wrong" message; no per-row pipeline runs.
4. **Given** `connect()` raises an exception (bad config, unreachable endpoint), **When** the engine catches it, **Then** the Job transitions to `failed` with `errorDetails` carrying the captured exception message; no per-row pipeline runs.
5. **Given** the in-memory password store is empty for this Job's `jobId` (e.g., the wizard restarted after upload), **When** the engine attempts to look up the first row's password, **Then** the Job transitions to `failed` with `errorDetails` carrying a "credentials no longer in memory — re-upload CSV via a new Job" message per parent `FR-010a`; no `sendUtterance` is called.

---

### Edge Cases

- A Job has zero Utterance rows (impossible via Module 8's validation per `011 FR-009`'s "no data rows" rejection, but defensive). The engine immediately calls `connect()` → `disconnect()` and transitions to `completed` with `processedCount == 0`, `failedCount == 0`. Plan-level whether to bypass `connect()` entirely.
- The engine is processing row N when the harness gets a SIGTERM. The in-flight row's pipeline completes if possible; otherwise the Job is left in `running` and gets reconciled to `failed` on next startup per US4.
- A Cancel arrives DURING the engine's startup orphan-reconciliation pass (impossible in practice — startup runs before any tester action — but defensive). The orphan pass overrides; the Job ends in `failed`.
- Concurrent jobs collide on shared resources (e.g., both use the same Mock LLM endpoint). Each Job's connector handles its own retries / rate-limit responses (no harness-layer retry per parent `FR-025`). Failures surface as per-row `failed` rows per US2.
- A row's `sendUtterance` returns but `normalize` is never called because the engine crashed in between. On orphan reconciliation, the Job goes to `failed`; the unsaved row is lost (no ExecutionResult; the tester re-uploads CSV in a new Job to retry).
- A row's connector call hangs forever (no timeout). The engine waits — there is no orchestrator-layer timeout in v1. Plan-level enhancement to add a per-row timeout would be a v1+ feature. The tester's recourse is Cancel.
- A Job's snapshotted contract version is incompatible with the bundled schema (e.g., emit `"4"` but harness only knows `"1"`–`"3"`). Per `006 FR-015`, the contract instance is rejected at validation time with `errorStage = "normalization"`. Per parent `FR-020` / wizard `003 FR-014`, this should have been caught at job-creation time; the runtime rejection is defense-in-depth.
- The data layer write fails mid-row (e.g., disk full while persisting the ExecutionResult). The engine catches the failure, leaves the row's pipeline state as `failed` with `errorDetails` naming the persistence failure (best-effort), and proceeds to the next row. Subsequent rows likely fail with the same cause; eventually the Job reaches terminal `completed` with all rows `failed`. The harness operator must resolve the disk issue out-of-band.
- The engine attempts to start a row's pipeline but the Utterance's password is absent from the in-memory store (e.g., it was somehow evicted prematurely). The engine marks the row `failed` with `errorStage = "connector"` (the row failed to invoke the connector because no password was available) and `errorDetails` carrying the cause. Proceeds to the next row.
- `disconnect()` raises during cleanup. The exception is captured to the log but does NOT alter the Job's terminal status. The Job's terminal status was determined by row outcomes (US1) or cancellation (US3), not by disconnect cleanliness (per `007` edge case).
- The engine's instance-of-the-month for the connector or evaluator caches stateful resources (LLM client, HTTP session) internally. Per `008 FR-006`, the framework makes no promises about when `evaluate` is invoked; per `007 FR-006`, `connect` is once per job. The engine doesn't introspect this caching.
- A new job is enqueued while the engine is at its concurrency limit (plan-level cap). The job stays in `queued` until a slot frees. The dashboard shows `queued` per `002 FR-004`. Plan-level: when slots free, FIFO or some other ordering.

## Requirements *(mandatory)*

### Functional Requirements

#### Engine lifecycle and job pickup

- **FR-001**: The engine MUST run **asynchronously** with respect to the request that enqueued a Job. The wizard's `start` action (per `003 FR-017`) MUST return as soon as the Job's status is `queued` and the enqueue signal has been emitted; the engine then picks up the Job in the background. No tester-facing call blocks waiting for Job completion.
- **FR-002**: At process startup, BEFORE any other module reads or writes persistent state, the engine MUST perform an **orphan-reconciliation pass** over the data layer: scan every Job whose persisted `status` is `running` or `cancelling`, atomically transition each to `failed` with `errorDetails` set to a clear orphan-recovery message (e.g., `"harness restarted while job was running"`) and `completedAt` set to the current moment. The in-memory password store contains no entries from prior process lifetimes (per `011 FR-015`'s process-exit-clear rule); the engine MUST NOT attempt to restore them. The orphan-reconciliation pass MUST complete within 5 seconds of startup (mirrors parent `SC-008`).
- **FR-003**: After orphan reconciliation, the engine MUST pick up Jobs whose status is `queued` and begin processing them. The engine MAY process multiple Jobs concurrently (per parent `FR-011`, this spec's US5). Per-job processing MUST be initiated by a status transition `queued → running` and the recording of `startedAt` (if not already set).
- **FR-004**: When the engine picks up a Job, it MUST read the Job's snapshotted configuration from the data layer (per `009 FR-001`): `connectorType`, `connectorConfigSnapshot`, `evaluationAgentId`, `evaluationAgentConfigSnapshot`. The engine MUST NOT consult the current state of the Connector Registry or Evaluation Agent Registry for the config values themselves — the snapshot is the source of truth (per parent `FR-023`). The registries are queried only to obtain the *implementation* by id.
- **FR-005**: The engine MUST decrypt secret-declared fields within the snapshotted configs using Module 4's machine-local encryption utility (per parent `FR-023a` / `007 FR-015`–`FR-019`) at the moment of `connect()` / first `evaluate()`. Decrypted plaintext MUST NEVER appear in any persistent surface (logs, exports, UI, database) per `007 FR-017`.

#### Connector + Evaluator instantiation

- **FR-006**: The engine MUST obtain the connector implementation from the Connector Registry by the snapshotted `connectorType` id. If the connector is no longer registered, the engine MUST transition the Job to `failed` with `errorDetails` naming the missing id; no further work for that Job.
- **FR-007**: Similarly, the engine MUST obtain the evaluator implementation from the Evaluation Agent Registry by the snapshotted `evaluationAgentId`. If the agent is no longer registered, the Job transitions to `failed` with `errorDetails` naming the missing id.
- **FR-008**: The engine MUST call `connect(config)` exactly ONCE per Job, with the decrypted snapshotted config. If `connect()` raises (bad config, unreachable target, etc.), the engine MUST capture the exception, transition the Job to `failed` with `errorDetails` carrying the captured exception, and NOT invoke any per-row pipeline. `disconnect()` is NOT called in this case (the handle was never obtained).
- **FR-009**: The engine MUST hold the `ConnectionHandle` returned by `connect()` for the entire Job's runtime; it MUST be reused across every row (per `007 FR-006`); it MUST NOT be discarded or re-obtained mid-job.
- **FR-010**: The engine MUST invoke the evaluator's `evaluate()` method on the snapshotted agent implementation for each row; the agent handles its own internal state caching per `008 FR-006`. The engine MUST NOT impose any init/teardown methods on the agent.

#### Per-row pipeline

- **FR-011**: For each Utterance row of the Job (ordered by `rowIndex` per `009 FR-002`), the engine MUST run the following pipeline in sequence:
  1. **Password lookup**: look up the row's password from the in-memory password store keyed by `(jobId, utteranceId)` (per `011 FR-015`). If absent (e.g., process restart between upload and execution), transition the Job to `failed` with `errorDetails` carrying the "credentials no longer in memory — re-upload CSV via a new Job" message; halt further per-row processing.
  2. **`sendUtterance`**: call `sendUtterance(handle, originalText, testId, password)`. The engine MUST catch any exception; on success, the return value (`RawResponse`) is held for the next step.
  3. **Password eviction**: IMMEDIATELY after `sendUtterance` returns (success or failure), the engine MUST evict the row's password entry from the in-memory store (per `011 FR-015` per-row eviction).
  4. **`normalize`**: if `sendUtterance` succeeded, call `normalize(rawResponse)`. The engine MUST catch any exception; on success, the return value (Standard Evaluation Contract instance) is held.
  5. **Contract validation**: the harness validates the normalized contract against the bundled schema (per `006 FR-008`). If validation fails, this is recorded as a normalization-stage failure (per `006 FR-009`).
  6. **`evaluate`**: if validation succeeded, call `evaluate(contract)` on the agent. The engine MUST catch any exception; the agent's `EvaluationResult` is validated structurally (per `008 FR-005b`); validation failure is an evaluation-stage failure.
  7. **Persist**: the engine MUST persist exactly one ExecutionResult row per Utterance (per `009 FR-003`), atomically with the Job's counter updates. The ExecutionResult carries whichever stage data succeeded (some/all of `rawChatbotResponse` / `normalizedContract` / `evaluationResult` may be null for failed rows); `errorStatus` / `errorStage` / `errorDetails` reflect the failure stage if any.
- **FR-012**: Per-row failures at ANY stage (connector / normalization / evaluation / password-lookup) MUST be isolated: the row's ExecutionResult is persisted with `errorStatus = "failed"` and `errorStage` set to the stage where the failure occurred (per parent `FR-017`'s three-stage taxonomy plus the `"connector"` stage for the password-lookup failure mode); the Job's `failedCount` is incremented atomically with the persistence (per `009 FR-001` / `FR-020`); the next row is processed. Per-row failure MUST NOT cause `disconnect()` to be called, MUST NOT cause a `connect()` retry, MUST NOT cause the Job to abort (per parent `FR-016`, this spec's US2).
- **FR-013**: The engine MUST NOT retry any failed per-row call (per parent `FR-025`). Each `sendUtterance` / `normalize` / `evaluate` invocation is single-shot. Individual connector or evaluator implementations MAY retry internally per their own design; the engine does not.
- **FR-014**: The engine MUST update the Job's `processedCount` atomically when persisting each row's ExecutionResult. Per `009 FR-001`, `processedCount` counts ExecutionResults where `errorStatus IN (null, "failed")` — i.e., success OR failure of an attempted row. Cancelled-before-process rows (whose stubs are created at `cancelling → cancelled` per `009 FR-003a`) are NOT counted here.
- **FR-015**: When the engine finishes processing all rows of a Job (or stops processing due to soft cancel per US3 / fatal pre-row error per US6), it MUST call `disconnect(handle)` exactly once on the connector if a handle was obtained — regardless of whether the Job ended `completed` / `failed` / `cancelled`. If `disconnect()` raises, the exception is captured to the log but does NOT alter the Job's terminal status (per `007` edge case).

#### Terminal transition

- **FR-016**: When the engine finishes a Job's per-row loop without cancellation or fatal failure, it MUST atomically: (a) set `completedAt` to the current moment, (b) transition `status` to **`completed`** — regardless of whether `failedCount == 0` or `failedCount > 0` or even `failedCount == totalUtteranceCount` (per `004 FR-005`, the "Completed with errors" rendering is a UI label, NOT a stored state), (c) clear all remaining in-memory password store entries for the Job (the Job-terminal backstop per `011 FR-015`).
- **FR-017**: If the engine encountered a fatal pre-row error (per US6: missing registry entry, decryption failure, `connect()` raise, empty password store), it MUST atomically: (a) set `completedAt`, (b) transition `status` to **`failed`** with `errorDetails` naming the cause, (c) call `disconnect()` if a `ConnectionHandle` was obtained, (d) clear the in-memory password store for the Job. No ExecutionResults are created in this pathway.
- **FR-018**: The engine MUST NEVER transition a Job's stored `status` to `CompletedWithErrors` or `Configured` or any value not in the canonical lifecycle enum (parent `Test Job` entity). These are not lifecycle states; the canonical enum is `draft / queued / running / cancelling / completed / failed / cancelled` (per `009 R1 Q2`). UI labels derived from those states (e.g., "Completed with errors") are the consumers' responsibility.

#### Cancellation handling

- **FR-019**: When the data layer signals a Cancel for a `running` Job (the tester triggered `004 FR-018`'s Cancel control, which transitions the Job to `cancelling` per parent `FR-024`), the engine MUST detect the signal at the next per-row boundary AND MUST allow the currently-in-flight row's pipeline to run to natural completion or failure. The engine MUST NOT interrupt an in-flight `sendUtterance` / `normalize` / `evaluate` call.
- **FR-020**: After the in-flight row completes (its ExecutionResult is persisted normally), the engine MUST stop invoking further rows for that Job. It MUST coordinate with the data layer to atomically (a) create ExecutionResult stubs for all remaining Utterances with `errorStatus = "cancelled"` per `009 FR-003a`, (b) transition the Job from `cancelling` to terminal `cancelled`, (c) set `completedAt`, (d) call `disconnect()` exactly once, (e) clear the in-memory password store for the Job.
- **FR-021**: A Cancel signal that arrives AFTER the engine has already begun the `running → completed` transition (race) MUST be refused by the data layer (per `004 FR-018`'s race-edge case); the engine MUST NOT receive or act on such a refused signal.

#### Concurrent execution

- **FR-022**: The engine MUST support multiple Jobs running concurrently without interference (per parent `FR-011`, US5). Each concurrent Job MUST have its own `ConnectionHandle` (per `007 FR-007`), its own evaluator invocation context (per `008 FR-020`), and its own in-memory password store entries (the store is keyed by `(jobId, utteranceId)` so independence is structural).
- **FR-023**: Within a single Job, the engine MUST serialize `sendUtterance` calls on the same handle (per `007 FR-007a`) and serialize `evaluate` calls on the same agent invocation context (per `008 FR-019`). No two rows of the same Job are in flight simultaneously in v1.
- **FR-024**: Cancellation or terminal transition of one concurrent Job MUST NOT affect another concurrent Job's state — handles, agent state, password store entries, counters, and lifecycle status all remain isolated per `(jobId)`.

### Key Entities *(include if feature involves data)*

- **Job Execution Worker** *(in-process, plan-level shape)*: The async unit of work that owns one Job's runtime — its `ConnectionHandle`, its evaluator invocation context, its per-row loop state, its counter updates. One worker per concurrent Job. Lives for the duration of the Job; ends when the Job reaches terminal status. Concrete implementation (asyncio task, threading.Thread, separate worker process, etc.) is plan-level.
- **Per-row Pipeline State** *(transient, per-row, in-memory)*: The intermediate state of one row's pipeline: the password (briefly), the `RawResponse` (briefly), the normalized contract (briefly), the evaluator's result. Lives only for the duration of one row's processing; discarded after the row's ExecutionResult is persisted. Notably: the password is evicted from the in-memory store IMMEDIATELY after `sendUtterance` returns, not at end-of-row.
- **Orphan Reconciliation Pass** *(transient, startup)*: A one-shot operation at engine boot that walks the data layer for Jobs in `running` / `cancelling` status, transitions them to `failed`, and clears any stale in-memory state (there isn't any in practice, since the store is process-scoped). Completes within 5 seconds of startup.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A `queued` Job with N Utterance rows + matching password store entries + valid snapshotted config completes successfully: status reaches `completed`, `processedCount == N`, `failedCount == 0`, `completedAt` set, `connect()` called once, `sendUtterance` called N times in `rowIndex` order, `disconnect()` called once, in-memory password store empty for the Job. Verifiable by automated end-to-end test against MockConnector + MockEvaluationAgent.
- **SC-002**: For a Job where K of N rows fail at various stages (connector / normalization / evaluation): the Job's terminal status is `completed` (NOT `failed`); `processedCount == N`; `failedCount == K`; each failed row's ExecutionResult carries `errorStatus = "failed"`, `errorStage` matching the actual stage, and `errorDetails`; the connector's `ConnectionHandle` was reused across all N rows (no mid-job reconnect). Verifiable by automated test.
- **SC-003**: A Job with EVERY row failing reaches terminal status `completed` (NOT `failed`), with `failedCount == totalUtteranceCount`. Verifiable per US2 scenario 5.
- **SC-004**: A Cancel mid-running Job produces the exact sequence: in-flight row completes naturally; remaining Utterances get ExecutionResult stubs with `errorStatus = "cancelled"` per `009 FR-003a`; `disconnect()` called once; status transitions through `running → cancelling → cancelled`; password store empty for the Job. Verifiable per US3 independent test.
- **SC-005**: A simulated harness crash mid-Job, followed by restart, transitions the orphaned Job to `failed` within 5 seconds of startup with an explanatory `errorDetails`, and no Job remains in `running` or `cancelling` after the orphan pass completes. Verifiable per US4 independent test (matches parent `SC-008`).
- **SC-006**: A fatal pre-row error (missing connector, missing evaluator, decryption failure, `connect()` raise, empty password store) results in the Job reaching terminal `failed` with `errorDetails` naming the cause; no ExecutionResult rows are created; `disconnect()` is called only if a handle was obtained. Verifiable per US6 scenarios.
- **SC-007**: Two concurrent Jobs against the same connector + evaluator identities run with fully independent state (handles, agent contexts, password store entries, counters, statuses). Verifiable by running two Jobs simultaneously and inspecting their persisted states and instrumented handle/agent identities.
- **SC-008**: The per-row password store entry for a row is removed from the store IMMEDIATELY after `sendUtterance` returns — verifiable by instrumenting the store with a probe and asserting the absence of the entry by the time `normalize` is called.
- **SC-009**: After any Job reaches terminal status (`completed` / `failed` / `cancelled`), the in-memory password store contains zero entries keyed by that Job's `jobId`. Verifiable by probing the store at the moment of terminal transition.
- **SC-010**: The engine's per-row failure-isolation behavior produces exactly one ExecutionResult per Utterance for every successfully-attempted row, regardless of whether the row succeeded or failed at any stage. Verifiable by counting ExecutionResults vs. Utterances after end-to-end runs with deliberately-induced per-stage failures.
- **SC-011**: A `running` Job's stored `status` is NEVER `CompletedWithErrors`, `Configured`, `Paused`, or any other value not in the canonical enum — verifiable by an automated test that enumerates persisted status values across many runs and asserts each is in `{draft, queued, running, cancelling, completed, failed, cancelled}`.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, single-process. Concurrent multi-process orchestration is out of scope; the engine assumes it is the sole orchestrator within its process.
- The engine consumes (does not redefine) the interfaces and behaviors specified in:
  - Module 2 (`009`): Job, Utterance, ExecutionResult, TesterFeedback schemas; snapshot immutability; cascade delete; bulk delete; `009 FR-003a` cancellation-stub creation; transaction atomicity.
  - Module 4 (`007`): Connector interface (`connect`/`sendUtterance`/`normalize`/`disconnect`); Registry; encryption utility for secret config fields; once-per-job lifecycle; serialized `sendUtterance` per handle.
  - Module 6 (`006`): Standard Evaluation Contract schema; per-row validation; contract version compatibility.
  - Module 7 (`008`): Evaluator interface (`evaluate`); Registry; closed verdict enum; standardized scores shape; declared scoring dimensions; harness-derived `harnessAnnotations`.
  - Module 8 (`011`): In-memory password store (the engine is the canonical consumer); per-row eviction discipline; replace-on-upload semantics (which the engine respects by re-reading password entries on each row).
  - Module 9 (`003`): `draft → queued` transition on Start; enqueue signal that the engine listens for.
  - Module 3 (`010`): OS-derived tester identity (the engine logs the identity as part of log-line prefixes per `010 FR-006`).
- The engine's async / scheduling implementation (asyncio, threading, a worker pool, a separate process) is plan-level. The spec requires only the observable behaviors: async-start (`FR-001`), concurrent Jobs (`FR-022`), bounded startup orphan-reconciliation (`FR-002`).
- The maximum number of concurrent Jobs the engine processes is plan-level. Parent assumption already settles this: "Concurrency limits (e.g., maximum simultaneous in-flight rows per job) are an implementation tuning concern, not a specification concern." Same applies to concurrent-Job count.
- Per-row timeouts (e.g., a hard limit on how long `sendUtterance` may take) are NOT implemented at the engine layer in v1. Connectors set their own timeouts internally. A future v1+ may add a configurable engine-layer timeout; out of scope here.
- "Plan-level" decisions about queue ordering (FIFO vs. priority), backpressure, throttling, and concurrent-job scheduling are deferred to `/speckit-plan`.
- The engine's status updates (lifecycle transitions, counter updates) feed the dashboard's near-real-time row updates (per `002 FR-012`, `004 FR-015`) and the export's snapshot-at-click-time semantics (per `005 FR-003`). The engine itself just writes to persistence; consumers read from there.
- The engine is the SOLE source of per-row pipeline invocation. There is no debug-mode "manually invoke `sendUtterance` for one row" surface in v1; that would belong in some future testing-tool module.
- "Module 10" maps to our `012-` directory. The forward references in earlier specs to "Module 10 (TBD)" / "the orchestrator (TBD)" all resolve here.
