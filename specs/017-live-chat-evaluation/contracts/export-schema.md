# Contract: Session Export Schema

## Endpoints

```
GET /chat/sessions/{session_id}/export?format=json
GET /chat/sessions/{session_id}/export?format=csv
```

Access: session owner only (same enforcement as the chat interface).

In-progress turns are excluded from the export; only `completed` and `failed` turns are included.

---

## JSON Format

Filename: `{session-name-slug}_{session_id[:8]}.json`
Content-Type: `application/json`

```json
{
  "session": {
    "session_id": "uuid",
    "session_name": "My Exploratory Session",
    "connector_name": "Azure OpenAI Prod",
    "evaluator_name": "Relevance Evaluator v2",
    "owner": "user@example.com",
    "created_at": "2026-06-22T10:00:00Z",
    "exported_at": "2026-06-22T14:30:00Z"
  },
  "total_turns": 12,
  "turns": [
    {
      "turn_id": "uuid",
      "sequence": 1,
      "status": "completed",
      "created_at": "2026-06-22T10:05:00Z",
      "completed_at": "2026-06-22T10:05:08Z",
      "user_message": "What is the capital of France?",
      "assembled_response": "The capital of France is **Paris**.",
      "normalized_contract": { "utterance": "...", "chatbotResponse": "...", "evaluationScores": [] },
      "evaluation_events": [
        {
          "sequence_number": 1,
          "event_type": "score_update",
          "payload": { "dimension": "relevance", "score": 0.95 },
          "created_at": "2026-06-22T10:05:06Z"
        },
        {
          "sequence_number": 2,
          "event_type": "final",
          "payload": { "overallScore": 0.95, "passed": true, "summary": "Accurate and concise." },
          "created_at": "2026-06-22T10:05:07Z"
        }
      ],
      "final_evaluation_result": { "overallScore": 0.95, "passed": true, "summary": "Accurate and concise." },
      "error_stage": null,
      "error_details": null
    },
    {
      "turn_id": "uuid",
      "sequence": 2,
      "status": "failed",
      "created_at": "2026-06-22T10:10:00Z",
      "completed_at": "2026-06-22T10:10:30Z",
      "user_message": "Explain quantum entanglement.",
      "assembled_response": "Quantum entanglement is a pheno",
      "normalized_contract": null,
      "evaluation_events": [],
      "final_evaluation_result": null,
      "error_stage": "connector_stream",
      "error_details": "Stall timeout exceeded after 30 seconds"
    }
  ]
}
```

### Field Notes

| Field | Notes |
|-------|-------|
| `session.owner` | Display name or email; never OID |
| `turns[].sequence` | 1-based position in session; ordered ascending by `created_at` |
| `turns[].assembled_response` | May be partial on `failed` turns |
| `turns[].normalized_contract` | `null` if contract was never assembled (connector_stream failure) |
| `turns[].evaluation_events` | Empty array on failures before evaluator was invoked |
| `turns[].final_evaluation_result` | `null` if evaluation did not complete |
| Credentials | `test_id` and `password` are NEVER included in any export |
| Auth descriptors | Credential subfields within connector/evaluator auth descriptors are NEVER included |

---

## CSV Format

Filename: `{session-name-slug}_{session_id[:8]}.csv`
Content-Type: `text/csv`

One row per turn. Nested objects (`normalized_contract`, `evaluation_events`, `final_evaluation_result`) are JSON-stringified in their cells.

### Columns

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | string | Repeated on every row |
| `session_name` | string | Repeated on every row |
| `connector_name` | string | Repeated on every row |
| `evaluator_name` | string | Repeated on every row |
| `turn_id` | string | |
| `sequence` | integer | 1-based |
| `status` | string | `completed` or `failed` |
| `created_at` | ISO-8601 | |
| `completed_at` | ISO-8601 or empty | |
| `user_message` | string | |
| `assembled_response` | string | May be partial on failed turns |
| `normalized_contract` | JSON string | `""` if null |
| `evaluation_events` | JSON string | Array; `"[]"` if empty |
| `final_evaluation_result` | JSON string | `""` if null |
| `error_stage` | string | `""` if null |
| `error_details` | string | `""` if null |
