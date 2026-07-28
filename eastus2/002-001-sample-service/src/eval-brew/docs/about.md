# About EvalBrew

## What is it?

EvalBrew is a tool that helps teams test their AI chatbots and virtual
assistants in a systematic, repeatable way. Think of it as an automated quality checker: you
give it a list of questions, tell it which chatbot to ask and how to judge the answers, and it
does all the work — sending every question, capturing every response, scoring every result, and
giving you a report you can act on.

This matters because AI chatbots change over time. Models get updated, prompts get adjusted,
integrations shift. Without a harness like this, you'd have to manually re-test every scenario
after every change to know whether the bot still behaves as expected. The harness replaces that
manual effort with a push of a button.

---

## Key concepts

### Jobs

A **job** is a single test run. To create one you:

1. Upload a CSV file containing the list of questions (or "utterances") you want to test.
2. Choose which chatbot connection to use.
3. Choose which evaluation method to use.
4. Click **Start Job**.

The harness then works through your list automatically — one question at a time — and records
the chatbot's answer and the evaluation verdict for each. You can watch the run progress live
on the dashboard, and when it finishes you can inspect every result in full detail or download
the complete report as a CSV or JSON file.

A job captures a snapshot of everything relevant at the time it was created: which connector
was used, which evaluator was used, and all the test inputs. This means past job results are
preserved exactly as they were, even if the connector or evaluator is later updated.

Jobs finish in one of three states:

| Status | Meaning |
|---|---|
| **Completed** | All rows processed successfully. |
| **Completed with errors** | Most rows succeeded; some rows encountered an error (the rest still ran). |
| **Failed** | A problem stopped the job before it could finish. |

A single failing row never stops the whole run. Each row is independent.

---

### Connectors

A **connector** is a small service that sits between the harness and your chatbot. It translates
the harness's standard request into whatever format your specific chatbot needs, calls your
chatbot, and returns the answer in a format the harness understands.

**Why connectors exist:** Every chatbot is different. Some are REST APIs, some are web services,
some need special authentication, some need user credentials, some return structured JSON while
others return plain text. Rather than trying to support every chatbot natively, the harness
uses a simple, universal interface — and connectors are the bridge.

**The key freedom:** You (or your team's developer) write and deploy the connector wherever
makes sense for your project — inside your company's network, in a cloud environment, on a
test server, anywhere. The harness just needs a URL to call. This means:

- You control how your chatbot is accessed.
- You control what environment it runs in.
- You control authentication and security.
- The harness stays completely neutral about your chatbot's technology stack.

Connectors are registered in the harness by name. Once registered, testers simply select the
connector by its display name when creating a job — they never need to know the technical
details behind it.

---

### Evaluators

An **evaluator** is a service that scores the chatbot's answer. After the connector retrieves
a response, the harness sends that response to the evaluator, which returns a verdict
(**pass**, **fail**, or **warn**) and, optionally, scores across named dimensions (such as
relevance, accuracy, tone, or groundedness).

**Why evaluators exist:** "Is this answer good?" is not a simple question. Different use cases
have different standards. A customer support bot needs different qualities than a knowledge
retrieval bot or a creative writing assistant. Evaluation logic belongs to the people who
understand the use case, not in the harness itself.

**The same key freedom as connectors:** You deploy your evaluator wherever you like — alongside
the chatbot, in a separate service, in the cloud, on-premises. It can be a simple rule-based
checker, a human-in-the-loop review service, or an LLM judge. The harness does not care about
the implementation. It sends the chatbot's response to your URL and trusts you to score it.

This design gives the **use case owner full control** over both how the chatbot is accessed
and how its responses are judged — while the harness handles all the orchestration,
persistence, reporting, and administration.

---

## Features at a glance

| Feature | What it does |
|---|---|
| **Job creation wizard** | Step-by-step guided flow for creating and starting a test run |
| **CSV upload** | Upload a list of test questions; the harness validates the file before you can proceed |
| **Live dashboard** | See all jobs and their current status at a glance |
| **Real-time progress** | Watch row-by-row results appear as the job runs |
| **Full traceability** | Every row's complete request, response, and evaluation result is stored and viewable |
| **Results export** | Download complete results as CSV, JSON, or both (zipped) |
| **Connector Registry** | Register, manage, and test chatbot connections |
| **Evaluator Registry** | Register, manage, and test evaluation agents |
| **Role-based access** | Admin and standard-user roles, backed by Azure Active Directory |
| **Credential security** | Service credentials are encrypted at rest and never appear in exports or logs |
| **Job maintenance** | Admins can clear old completed jobs to manage database size |

---

## A note on deployment

The harness runs as a web application on a server that you control. Connectors and evaluators
are separate services that you also deploy and control. The only connection between them is
an HTTP call — the harness calls your connector with a question, and calls your evaluator
with the chatbot's answer. Nothing else is shared.

This separation is intentional. It means:

- **The harness never needs access to your chatbot directly.** Your connector handles that,
  inside whatever security boundary your chatbot lives in.
- **Your evaluation logic is yours.** You can build it, host it, change it, and keep it
  completely private to your team.
- **Multiple teams can share one harness** while each using their own connectors and
  evaluators tailored to their specific chatbot and quality standards.

---

## About this solution

The EvalBrew was designed and developed by **Siddhartha Dhamankar** using
**[Claude Code](https://claude.ai/code)** — Anthropic's AI-assisted software development
environment — and **Spec-Driven Development** powered by
**[GitHub Speckit](https://github.com/acm-will/speckit)**. Every feature was first expressed
as a precise, testable specification before implementation, ensuring consistent quality and
full traceability from requirement to working code.
