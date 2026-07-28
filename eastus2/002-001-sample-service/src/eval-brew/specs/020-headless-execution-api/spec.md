# Feature Specification: Headless Execution API

**Feature Branch**: `020-headless-execution-api`

**Created**: 2026-07-12

**Status**: Draft

**Input**: Programmatic API surface on eval-brew enabling external systems to submit test cases as JSON, execute evaluation jobs, stream live progress, and retrieve structured results without the browser UI.

---

## Clarifications

### Session 2026-07-12 (round 1)

- Q: What format does `expected_criteria` take in the test case payload? → A: There is no `expected_criteria` field. Evaluation criteria are declared at evaluator registration time in eval-brew, not per test case. The test case payload mirrors eval-brew's existing CSV job format expressed as JSON. qual-brew generates job data in that format and sends it via API instead of file upload.
- Q: What rate limiting applies to the headless API? → A: Maximum 2 headless jobs executing concurrently per user. A submission that would exceed this limit is rejected with an error indicating the current in-flight count. No per-minute submission rate limit in v1.
- Q: How many failing cases are included in the job summary and how are they selected? → A: Up to the first 5 failures in execution order. If fewer than 5 cases failed, all failures are included. No scoring-based ranking.
- Q: What happens if a headless job stalls (connector unresponsive)? → A: Headless jobs inherit the existing execution engine timeout policy — same behaviour as wizard-submitted jobs. No separate timeout configuration. On timeout, the job is marked failed, a terminal failure event is emitted, and the in-flight slot is released.
- Q: Must caller-assigned test case identifiers be unique within a submission? → A: Yes. Duplicate identifiers are rejected at validation time (before execution) with HTTP 422, identifying the duplicated value.

### Session 2026-07-12 (round 2)

- Q: What does the stream endpoint return if called after the job has already completed? → A: Immediately emits the terminal completion (or failure) event and closes. The caller receives the full result regardless of when it connects.
- Q: Where does the optional source metadata (source_system, product_name, feature_name) appear? → A: Displayed in the eval-brew dashboard job list entry alongside the "API" source label. Gives users context about which product/feature the job relates to without needing to drill into the report.
- Q: What counts toward the 2-job concurrent limit — only executing jobs, or queued ones too? → A: Any job in a non-terminal state counts from the moment of submission. Both queued and executing jobs occupy an in-flight slot until they reach completed or failed state.
- Q: Can a caller cancel an in-flight headless job? → A: Yes. A dedicated cancel endpoint transitions the job to a cancelled terminal state, emits a terminal failure event on any open stream, and releases the in-flight slot immediately. Only the submitting user may cancel their own job.
- Q: How is the stream endpoint authenticated — Bearer token header or signed URL? → A: Standard Bearer token in the request header, same as all other headless endpoints. No auth is embedded in the stream URL. The caller (qual-brew) attaches its token when opening the SSE connection.

### Session 2026-07-12 (round 3)

- Q: Are connector and evaluator discovery endpoints filtered per user, or do they return all registered active items? → A: All registered, active connectors and evaluators are returned to any authenticated user. No per-user filtering — mirrors how wizard-submitted jobs work on the LAN deployment.
- Q: Does the stream emit a lifecycle event when a queued job begins executing? → A: Yes. A `job_started` event is emitted when the job transitions from queued to executing, before the first per-case progress event. Allows the caller to distinguish queued from actively running.
- Q: What response does a cancellation request return for an already-terminal job? → A: HTTP 409 Conflict, with the response body indicating the current terminal state (completed, failed, or cancelled). The slot is already free; the caller can react to the outcome.
- Q: Do cancelled headless jobs appear in the eval-brew dashboard? → A: Yes, with a "Cancelled" status label, the "API" source label, and any source metadata. No report link is shown for cancelled or failed jobs — only completed jobs have a report link.
- Q: What does the result re-fetch endpoint return for a cancelled job? → A: Cancelled status plus any partial summary accumulated before cancellation (cases completed, cases failed, up to 5 top failures). No report link. Gives the caller visibility into how much work ran before cancellation.

---

## User Scenarios & Testing

### User Story 1 - Submit Test Cases and Stream Execution Progress (Priority: P1)

An external system (qual-brew) has generated test cases for a product feature. A user asks qual-brew to run those test cases against a chatbot. qual-brew authenticates with eval-brew using the user's identity, submits the test cases as JSON specifying the chatbot connector and evaluator to use, and receives a live stream of execution progress. When execution completes, qual-brew receives a results summary and a link to the full eval-brew report, which it presents in the chat window.

**Why this priority**: This is the end-to-end happy path that delivers the entire value of the feature. All other stories are prerequisites or recovery paths.

**Independent Test**: Can be tested by submitting a JSON payload with a small set of test cases to the submission endpoint, opening the returned stream URL, and observing progress events followed by a terminal completion event containing a valid report link.

**Acceptance Scenarios**:

1. **Given** a valid authenticated request with 5 test cases, a valid connector identifier, and a valid evaluator identifier, **When** the job is submitted, **Then** the response contains a job identifier, a stream URL, and a result URL with HTTP 201.
2. **Given** a job is queued and the stream is open, **When** the job transitions to executing, **Then** a `job_started` event is emitted on the stream.
3. **Given** a job is executing and the stream is open, **When** each test case completes evaluation, **Then** a progress event is emitted containing the running count of completed and failed cases.
4. **Given** all test cases have been evaluated, **When** the job finishes, **Then** a terminal completion event is emitted containing the report URL and a summary with total, passed, and failed counts plus the top failing cases.
5. **Given** an unrecoverable execution error occurs mid-job, **When** the error is encountered, **Then** a terminal failure event is emitted before the stream closes, containing an error message and any partial summary accumulated before the failure.

---

### User Story 2 - Discover Available Connectors and Evaluators (Priority: P2)

Before submitting a job, qual-brew needs to present the user with a list of chatbot connectors and evaluators configured in eval-brew. An admin has mapped product-specific connectors and evaluators in qual-brew's configuration. When the user initiates execution, qual-brew fetches the available options from eval-brew to populate the selection interface.

**Why this priority**: Discovery is a prerequisite for job submission — callers must know valid connector and evaluator identifiers before they can submit. Without this, the submission step cannot be driven by user selection.

**Independent Test**: Can be tested by calling the connectors and evaluators list endpoints with a valid authenticated token and verifying that the response lists available items with identifier, name, and description fields.

**Acceptance Scenarios**:

1. **Given** a valid authenticated request, **When** the connectors list endpoint is called, **Then** the response lists all registered, active connectors, each with an identifier, name, and description, with HTTP 200.
2. **Given** a valid authenticated request, **When** the evaluators list endpoint is called, **Then** the response lists all registered, active evaluators, each with an identifier, name, and description, with HTTP 200.
3. **Given** a request with no authentication or an expired token, **When** either discovery endpoint is called, **Then** the response is HTTP 401 with a clear error message.
4. **Given** no connectors or evaluators have been registered in eval-brew, **When** the respective list endpoint is called, **Then** the response is an empty list with HTTP 200.

---

### User Story 3 - Re-fetch Results After Stream Closes (Priority: P3)

qual-brew's connection to the live progress stream is interrupted before the terminal event arrives. When the job eventually completes, qual-brew uses the result URL returned at submission time to retrieve the final results summary and report link — without needing to reconnect to the stream.

**Why this priority**: Network interruptions are an operational reality in LAN deployments. The re-fetch endpoint ensures results are never lost due to a dropped stream connection.

**Independent Test**: Can be tested by submitting a job, closing the stream connection before the terminal event, waiting for the job to complete, then calling the result endpoint and verifying the same summary and report link are returned.

**Acceptance Scenarios**:

1. **Given** a job has completed, **When** the result endpoint is called with the job's identifier, **Then** the response contains the report URL and the final summary matching what the terminal stream event would have contained.
2. **Given** a job is still executing, **When** the result endpoint is called, **Then** the response indicates the job is in progress and includes the current running counts.
3. **Given** a job was cancelled, **When** the result endpoint is called, **Then** the response contains the cancelled status and any partial summary accumulated before cancellation, with no report link.
4. **Given** a job identifier that does not belong to the authenticated user, **When** the result endpoint is called, **Then** the response is HTTP 403.

---

### User Story 4 - View Headless-Submitted Jobs in the Eval-brew Dashboard (Priority: P4)

A user submitted several jobs via qual-brew over the past week. They open eval-brew's job dashboard to review their execution history. Their headless-submitted jobs appear alongside their wizard-submitted jobs, clearly labeled as submitted via API, with full access to the report view.

**Why this priority**: Dashboard visibility ensures users can audit their execution history and access results independently of qual-brew. It validates that headless jobs are first-class citizens in eval-brew.

**Independent Test**: Can be tested by submitting a headless job, navigating to the eval-brew job dashboard, and verifying the job appears with an "API" source label and a working link to the full report.

**Acceptance Scenarios**:

1. **Given** a job was submitted via the headless API with product name and feature name metadata, **When** the user views the eval-brew job dashboard, **Then** the job appears in the list with an "API" source label and the supplied product name and feature name displayed alongside it.
2. **Given** a headless job appears in the dashboard, **When** the user navigates to the job's report, **Then** the full result detail view is accessible and behaves identically to a wizard-submitted job report.
3. **Given** a headless job was cancelled before or during execution, **When** the user views the eval-brew job dashboard, **Then** the job appears with a "Cancelled" status and the "API" source label, with no report link.

---

### Edge Cases

- What happens when the submission contains more than 100 test cases? The submission is rejected before execution with an error stating the limit and the count submitted.
- What happens when a connector or evaluator identifier does not exist, or the authenticated user does not have access to it? The submission is rejected before execution with an error identifying which identifier is invalid.
- What happens when a test case has an empty or missing input message? The submission is rejected before execution with an error identifying the offending test case by its caller-assigned identifier.
- What happens when two test cases in the same submission share the same caller-assigned identifier? The submission is rejected before execution with an error identifying the duplicated identifier value.
- What happens when the authenticated user has no connectors or evaluators available? The discovery endpoints return empty lists with a success response — they do not error.
- What happens when the stream is open but execution encounters an unrecoverable error? A terminal failure event is emitted before the stream closes; results accumulated up to that point are preserved.
- What happens if the chatbot connector becomes unresponsive mid-execution and the job stalls? The job is subject to the same execution timeout policy as wizard-submitted jobs. When the timeout is reached, the job is marked failed, a terminal failure event is emitted on the stream, and the in-flight slot is released.
- What happens when a caller opens the stream endpoint after the job has already completed? The stream immediately emits the terminal completion (or failure) event and closes. The caller receives the full result regardless of when it connects.
- What happens when a caller requests another user's job result? The request is rejected as unauthorized, regardless of whether the job exists.
- What happens when the submitting user cancels an in-flight job? The job transitions to a cancelled terminal state, a terminal failure event is emitted on any open stream, and the in-flight slot is released immediately.
- What happens when a user attempts to cancel another user's job? The request is rejected as unauthorized.
- What happens when a caller tries to cancel a job that has already reached a terminal state? The request returns HTTP 409 Conflict, with the response body indicating the job's current terminal state (completed, failed, or cancelled).
- What happens when the authenticated user already has 2 headless jobs in a non-terminal state (queued or executing)? The submission is rejected with an error naming the in-flight count and instructing the caller to wait for one to reach a terminal state before resubmitting.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST expose an endpoint to list all registered, active chatbot connectors, returning each connector's identifier, name, and description. All authenticated users see the same list — no per-user filtering applies.

- **FR-002**: The system MUST expose an endpoint to list all registered, active evaluators, returning each evaluator's identifier, name, and description. All authenticated users see the same list — no per-user filtering applies.

- **FR-003**: The system MUST expose a job submission endpoint that accepts a JSON payload containing: a list of test cases, a connector identifier, an evaluator identifier, and optional metadata (source system name, product name, feature name). A successful submission returns a job identifier, a stream URL, and a result URL.

- **FR-004**: Each submitted test case MUST include a caller-assigned identifier and the input fields defined by eval-brew's existing job input specification — the same data that would appear in a row of a wizard-submitted CSV job. No per-test-case evaluation criteria are accepted; scoring criteria are declared at evaluator registration time and applied automatically. Multi-turn conversation sequences are out of scope for v1.

- **FR-005**: The system MUST expose a live progress stream endpoint that emits the following events in order: a `job_started` event when the job transitions from queued to actively executing; a `progress` event each time a test case completes evaluation (carrying the running count of completed and failed cases); and a terminal `job_complete` or `job_failed` event when the job finishes, containing the report URL and a summary of total cases, passed count, failed count, and up to the first 5 failing cases in execution order. If the stream endpoint is called after the job has already completed, the terminal event MUST be emitted immediately and the stream closed — the caller receives the full result regardless of when it connects.

- **FR-006**: The system MUST expose a result re-fetch endpoint that returns: the final results summary and report URL for a completed job; the current running counts for an in-progress job; and the cancelled status plus any partial summary accumulated before cancellation (cases completed, cases failed, up to 5 top failures collected) for a cancelled job, with no report link. Access MUST be restricted to the user who submitted the job.

- **FR-007**: Headless-submitted jobs MUST execute through the same evaluation engine as wizard-submitted jobs. No separate execution code path is introduced.

- **FR-008**: Headless-submitted jobs MUST appear in the eval-brew job dashboard alongside wizard-submitted jobs in all terminal states, including cancelled. Each entry MUST display an "API" source label, the job's terminal status (completed, failed, or cancelled), and any source metadata supplied at submission (source system, product name, feature name). A report link MUST be shown for completed jobs; no report link is shown for failed or cancelled jobs.

- **FR-009**: All headless endpoints MUST require Azure Active Directory JWT Bearer token authentication via the request header, including the stream and cancellation endpoints. Requests without a valid token MUST be rejected. No auth is embedded in URLs. Jobs MUST be associated with the authenticated user's identity.

- **FR-010**: Submissions containing more than 100 test cases MUST be rejected before any execution begins, with a response that states the maximum allowed and the count received.

- **FR-013**: A user MUST NOT have more than 2 headless jobs in a non-terminal state concurrently. Any job that has been submitted but has not yet reached a completed or failed terminal state counts toward this limit, regardless of whether it is queued or actively executing. A submission that would exceed this limit MUST be rejected with an error indicating how many jobs are currently in flight and that the caller should wait for one to complete before resubmitting.

- **FR-011**: Submissions referencing a connector identifier or evaluator identifier that does not exist or is not accessible to the authenticated user MUST be rejected before any execution begins.

- **FR-012**: Submissions containing a test case with an empty or missing input message MUST be rejected before any execution begins, identifying the offending test case by its caller-assigned identifier.

- **FR-014**: Caller-assigned test case identifiers MUST be unique within a single submission. Submissions containing duplicate identifiers MUST be rejected before any execution begins, with a response identifying the duplicated value.

- **FR-015**: The system MUST expose a job cancellation endpoint that allows the submitting user to cancel a headless job in any non-terminal state. Cancellation MUST transition the job to a cancelled terminal state, emit a terminal failure event on any open stream for that job, and release the in-flight slot immediately. Only the user who submitted the job may cancel it. Cancellation requests against a job already in a terminal state MUST return HTTP 409, with the response indicating the job's current terminal state.

### Key Entities

- **Headless Job**: A job submitted programmatically rather than through the wizard UI. Carries the submitting user's identity, the chosen connector and evaluator, optional source metadata (system, product, feature), execution status, and a reference to the resulting report. Terminal states are: completed, failed, and cancelled. Non-terminal states (which count toward the 2-job in-flight limit) are: submitted, queued, and executing.

- **Headless Test Case (Input)**: The programmatic representation of a single test case at submission time. Contains a caller-assigned identifier and the input fields defined by eval-brew's existing job input specification. No evaluation criteria are carried per test case — criteria are embedded in the evaluator's registration and applied automatically at scoring time.

- **Job Started Event**: A streaming event emitted once when the job transitions from queued to actively executing. Signals to the caller that evaluation has begun and per-case progress events will follow.

- **Job Progress Event**: A real-time streaming event emitted each time a test case completes evaluation. Carries the current running count of completed and failed test cases.

- **Job Completion Event**: The terminal streaming event emitted when execution finishes. Carries the report URL, total case count, passed count, failed count, and up to the first 5 failing cases in execution order (by caller-assigned identifier). If fewer than 5 cases failed, all failures are included.

- **Job Summary**: The persistent record of a completed job's outcome. Contains the same fields as the Job Completion Event and is accessible via the result re-fetch endpoint.

- **Connector (Discovery View)**: A read-only representation of a chatbot connector available to the authenticated user: identifier, name, and description.

- **Evaluator (Discovery View)**: A read-only representation of a scoring evaluator available to the authenticated user: identifier, name, and description.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: An external caller can submit a 50-case job and receive the first progress event within 10 seconds of submission under normal operating conditions.
- **SC-002**: An external caller that misses the terminal stream event can retrieve the complete results summary via the result endpoint within 5 seconds of the job completing.
- **SC-003**: Headless-submitted jobs appear in the eval-brew dashboard within 5 seconds of a successful submission.
- **SC-004**: Requests with missing, expired, or malformed authentication tokens receive an error response within 2 seconds.
- **SC-005**: Submissions violating input constraints (case count limit, empty fields, invalid identifiers) are rejected before any execution begins and respond within 2 seconds of submission.
- **SC-006**: The pass rate and response times of existing wizard-based job creation flows are unchanged after this feature is introduced.

---

## Assumptions

- The Azure Active Directory tenant used by qual-brew and eval-brew is the same, so tokens issued by qual-brew are valid for eval-brew to validate.
- All registered, active connectors and evaluators are visible to any authenticated user via the discovery endpoints. No per-user filtering applies — this mirrors how wizard-submitted jobs work on the LAN deployment.
- The caller (qual-brew) is responsible for handling SSE reconnection. eval-brew provides the result re-fetch endpoint as the recovery mechanism; it does not attempt to re-push events to reconnecting clients.
- Job results are retained for the same duration as wizard-submitted jobs.
- The 100-case-per-job cap is appropriate for v1 given that qual-brew generates a maximum of 10 cases per output type per generation cycle. The cap can be raised in a future revision without a breaking change.
- The headless API runs within the same deployed process as the existing eval-brew application. No separate service deployment is required.
- Headless jobs are subject to the same execution timeout as wizard-submitted jobs. No separate timeout configuration is introduced for the headless API.
- A multi-turn test case format (conversation sequences) will be defined in a future spec; this spec establishes the single-turn baseline only.
- Evaluation criteria are not part of the test case payload. They are declared when an evaluator is registered in eval-brew via the evaluator registration wizard. The headless API applies whichever evaluator the caller selects; it does not accept or override per-case scoring rules.

---

## Out of Scope

- qual-brew-side implementation: the execution intent handler, test case format transformation, and product-to-connector/evaluator mapping admin screen.
- Multi-turn conversation test case sequences.
- Webhook callbacks on job completion — callers use the SSE stream or the result re-fetch endpoint.
- Admin access to other users' headless-submitted jobs via this API.
- A separate CSV-based submission path for headless jobs.
