# Evaluator Contract Specification
## AI Quality Engineering Platform - Part 2 to Part 3 Integration Contract

Version: 1.0 (MVP Locked)
Status: Approved Design

---

# 1. Purpose

This specification defines the standard Evaluator Contract used by the Agent Regression Harness (Part 2) and the Analytics Platform (Part 3).

The objective is to enable multiple evaluators to participate in a single test execution while ensuring that analytics can be generated dynamically without requiring evaluator-specific dashboard implementations.

The contract standardises:

- Evaluator outputs
- Parameter scoring
- Verdict classification
- Reasoning capture
- Aggregation semantics
- Dashboard consumption model

---

# 2. Design Principles

## 2.1 Universal Analytics

All evaluators must emit data that can be consumed by a generic analytics engine.

Evaluator-specific dashboards are prohibited.

## 2.2 Numeric Scoring

For MVP, every evaluation parameter must emit a numeric score.

This allows a common aggregation model.

## 2.3 Flexible Verdicts

Evaluators may define their own verdict values.

The framework will not restrict evaluators to Pass/Fail.

## 2.4 Human Explainability

Every evaluation parameter must include reasoning.

Analytics must always be traceable to evaluator justification.

## 2.5 Dashboard Independence

The dashboard must consume metadata rather than being hard-coded to specific evaluators.

---

# 3. Evaluator Output Model

Every evaluator execution produces:

- Evaluator Metadata
- Overall Evaluator Result
- One or more Evaluation Parameters

Conceptually:

Evaluator
  └── Parameter
  └── Parameter
  └── Parameter

---

# 4. Evaluation Parameter

The Evaluation Parameter is the atomic analytical unit.

Every parameter MUST contain:

- parameterId
- parameterName
- score
- verdict
- reasoning

---

## Required Fields

### parameterId

Unique identifier.

Example:

groundedness

### parameterName

Human-readable label.

Example:

Groundedness

### score

Numeric value.

Rules:

- Must be numeric
- Higher value should generally indicate better outcome
- Preferred range: 0.0 to 1.0
- Dashboard must not assume range

Examples:

0.91
0.45
0.78

### verdict

Categorical classification.

Examples:

Pass
Warning
Fail

or

Excellent
Good
Fair
Poor
Critical

The platform must support evaluator-defined verdict values.

### reasoning

Human-readable explanation.

Purpose:

- Auditability
- Transparency
- Future LLM summarisation

---

# 5. Verdict Framework

## Design Decision

Verdicts are classification labels.

Verdicts are not restricted to binary outcomes.

---

## Examples

Binary Model

- Pass
- Fail

Ternary Model

- Pass
- Warning
- Fail

Five State Model

- Excellent
- Good
- Fair
- Poor
- Critical

Risk Model

- Low Risk
- Medium Risk
- High Risk
- Critical Risk

---

## Verdict Aggregation

Analytics must support:

- Verdict Counts
- Verdict Percentages
- Verdict Distributions

Example:

Pass      420
Warning    31
Fail        9

---

# 6. Evaluator Metadata

Every evaluator must publish metadata.

Example:

- evaluatorId
- evaluatorName
- evaluatorVersion

Optional:

- evaluatorDescription
- evaluatorOwner

---

# 7. Evaluator Manifest

Each evaluator should publish a manifest describing supported parameters.

Example:

Groundedness Evaluator

Parameters:

- Groundedness
- Completeness
- Accuracy

The analytics engine uses this information to dynamically render dashboards.

---

# 8. JSON Contract

```json
{
  "evaluatorId": "quality-evaluator",
  "evaluatorName": "Quality Evaluator",
  "evaluatorVersion": "1.0",
  "overallScore": 0.88,
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

---

# 9. Analytics Consumption Model

Part 3 must normalise evaluator output.

Every parameter becomes an analytical record.

Conceptual structure:

Session
Scenario
Test Case
Utterance
Evaluator
Parameter
Score
Verdict
Reasoning

---

# 10. Supported Aggregations

## Numeric Score Aggregations

Dashboard may calculate:

- Average
- Median
- Minimum
- Maximum
- Distribution
- Standard Deviation

Across:

- Session
- Scenario
- Test Case
- Evaluator
- Parameter

---

## Verdict Aggregations

Dashboard may calculate:

- Count
- Percentage
- Distribution

Across:

- Session
- Scenario
- Test Case
- Evaluator
- Parameter

---

# 11. Dashboard Behaviour

The dashboard must dynamically discover:

- Available evaluators
- Available parameters
- Available verdict values

No evaluator-specific coding is permitted.

Example:

Detected Parameters

- Groundedness
- Completeness
- Accuracy
- Relevance

The dashboard automatically renders statistics for each.

---

# 12. MVP Analytics Views

## Executive Summary

Displays:

- Overall Score
- Overall Verdict Distribution
- Total Utterances
- Failure Counts

## Parameter Breakdown

Displays:

- Average Score per Parameter
- Verdict Distribution per Parameter

## Evaluator Breakdown

Displays:

- Score by Evaluator
- Verdict Distribution by Evaluator

## Detailed Result Explorer

Displays:

- Utterance
- Response
- Parameter
- Score
- Verdict
- Reasoning

---

# 13. Future Expansion (Post-MVP)

Deferred capabilities:

- Non-numeric parameter values
- Boolean parameter types
- Categorical parameter values
- Ordinal parameter values
- Custom aggregation methods
- Evaluator-specific visualisations
- AI-generated analytical narratives
- Conversational analytics chatbot

The MVP contract intentionally limits parameter values to numeric scores to maximise implementation simplicity and enable universal analytics.

---

# 14. Locked MVP Decision

The following design decision is formally locked:

1. Every evaluation parameter must emit a numeric score.
2. Every evaluation parameter must emit a verdict.
3. Every evaluation parameter must emit reasoning.
4. Evaluators may define their own verdict values.
5. Analytics must aggregate scores generically.
6. Analytics must aggregate verdicts generically.
7. Evaluator-specific dashboard implementations are prohibited.
8. Dashboard rendering must be metadata-driven.

This design enables a scalable analytics platform while keeping MVP implementation complexity low.
