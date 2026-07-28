# Contract: Connector Wire Protocol (v1)

**Stability**: Stable contract every connector service must honor. Single-shot per utterance (FR-001).

---

## Request

`POST <endpoint_url>` with `Content-Type: application/json` and body:

```json
{ "testId": "<string>", "utteranceText": "<string>", "password": "<string, optional>" }
```

- `password` is present **iff** the registration's `expectsPerRowPassword` is `true`; otherwise the key is omitted entirely (not `null`, not `""`) — FR-002.
- Auth header per the registration's mode (FR-007): `none` (none), `bearer` (`Authorization: Bearer <token>`), `api-key-header` (`<headerName>: <value>`), `basic` (`Authorization: Basic <base64(user:pass)>`).
- The harness issues at most one request per row, serial within a job, and never retries (FR-004/005).

## Success Response

- HTTP `200`, `Content-Type: application/json`.
- Body: a single complete JSON object conforming to the Standard Evaluation Contract (`006`), with `connectorId` populated. The connector service performs all chatbot-specific normalization; the harness does none (FR-003).

## Failure Categorization (harness side, FR-006)

| What the harness observes | Recorded `errorStage` | `errorDetails` |
|---|---|---|
| timeout / connection refused / DNS / TLS | `connector_transport` | "timeout exceeded" or transport error |
| HTTP status ≠ 2xx | `connector_response` | truncated response body |
| 2xx but not JSON, or fails contract validation | `connector_normalization` | truncated offending body / violation summary |
| stored credential cannot be decrypted (pre-send) | `connector_auth` | "machine-local key missing or wrong" |

A connector whose response `connectorId` differs from the registered id is **trusted** (the service's self-identification) but logged as a warning; the row does **not** fail (spec edge case).
