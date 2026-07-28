# Contract: Evaluator SSE Events

The evaluator streams SSE events in response to a Standard Evaluation Contract POST. The server consumes this stream and relays events to the browser.

## Request (from server to evaluator)

```
POST {evaluator_endpoint_url}
Content-Type: application/json
Accept: text/event-stream
```

Body: the complete Standard Evaluation Contract (as produced by the connector's `contract` event), after validation.

## Wire Format

Same standard SSE format as the connector:

```
event: <event-type>
data: <JSON payload>

```

## Defined Event Types

### `score_update`

A partial or interim scoring signal. Zero or more may arrive before `final`.

```
event: score_update
data: {"dimension": "relevance", "score": 0.82, "partial": true}

```

### `warning`

A non-fatal observation about the response quality.

```
event: warning
data: {"message": "Response contains ambiguous claim about X"}

```

### `insight`

A positive or explanatory observation.

```
event: insight
data: {"message": "Response correctly cites source Y"}

```

### `diagnostic`

Internal evaluator diagnostic information.

```
event: diagnostic
data: {"stage": "embedding", "latency_ms": 142}

```

### `final`

The last event in the stream; carries the complete `EvaluationResult`.

```
event: final
data: {
  "evaluatorId": "quality-evaluator",
  "evaluatorName": "Quality Evaluator",
  "evaluatorVersion": "1.0",
  "overallScore": 0.91,
  "overallVerdict": "Pass",
  "parameters": [
    {
      "parameterId": "groundedness",
      "parameterName": "Groundedness",
      "score": 0.91,
      "verdict": "Pass",
      "reasoning": "Response fully grounded in supplied content."
    },
    {
      "parameterId": "completeness",
      "parameterName": "Completeness",
      "score": 0.82,
      "verdict": "Warning",
      "reasoning": "Response omitted approval timeline."
    }
  ]
}

```

Field names `overallVerdict` and `parameters` are canonical per `references/Evaluator_Contract_Specification_MVP.md §8`. The analytics engine (018/019) reads `.get("overallVerdict")` and `.get("parameters", [])` from this stored payload. Using any other key names (e.g., `dimensions`, `passed`) will cause analytics to silently produce zero results.

The server reads the `final` payload directly into `ChatTurnResult.final_evaluation_result`.

## Unknown Event Types

If the evaluator emits an event whose type is not one of the five defined types above, the server MUST:
- Forward the event to the browser as-is (with its raw type string)
- Persist it as an `EvaluationEvent` row with the raw type string in `event_type`
- NOT raise an error or fail the turn

This preserves forward compatibility as evaluator implementations evolve.

## Stream Completion Rules

- The stream MUST end with exactly one `final` event.
- If the stream closes before a `final` event is received, the turn fails with `error_stage = evaluator_stream`.
- All events received before the failure are persisted.

## Stall Timeout

If no event is received within `ChatSession.evaluator_timeout_seconds` of the previous event, the server treats the stream as stalled and fails the turn with `error_stage = evaluator_stream`.
