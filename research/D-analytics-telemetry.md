# Track D — Analytics/telemetry architecture

Status: **done**.

## What was checked

Read OpenBot's own `desktop/TELEMETRY.md` in full (its desktop-app telemetry design
doc), and ran a web search to confirm the current (2026) status of OpenTelemetry's
GenAI semantic conventions, since those were the "don't reinvent this either" candidate
named when this track was first scoped.

## Findings

### OpenBot's own telemetry design is a strong, directly-reusable pattern

`desktop/TELEMETRY.md` describes a local-first, privacy-constrained telemetry system
worth copying almost directly for our own phase-lifecycle analytics:

- **A closed, allowlisted event schema**, not a free-form logger. Every event name is
  namespaced (`oss.desktop.*`), backed by a Rust enum (`EventData`) with a generated
  JSON schema (`schema_json()`), and deserialization **rejects unknown properties and
  enum values outright**. Properties are enums, booleans, counts, and milliseconds —
  e.g. `harness_chosen` carries a harness enum, `image_pull` carries an outcome enum
  plus timing and byte counts.
- **An explicit, named denylist of what the schema will never accept**: "No prompt,
  answer, credential, file name, path, hostname, email, model name, YAML value, or
  custom URL is accepted by the desktop schema." This is the right altitude for our own
  phase/gate/check events — durations, outcomes, and counts, never code content, file
  paths, or credential-adjacent strings.
- **Anonymous by construction**: a random installation UUID persisted locally, not
  derived from the machine or any account.
- **Local-first, bounded, and non-blocking**: events persist to a local bounded queue
  (256 events, drop-oldest) *before* any delivery attempt; delivery is background and
  best-effort with replay on relaunch; **"Telemetry failures do not block setup."** This
  is the same principle the journal already established for CopilotKit's own CLI
  checkpoints ("checkpoints are telemetry, not control flow") — now confirmed as the
  same design choice one layer up, in the product we're building on top of.
- **Respects the industry `DO_NOT_TRACK=1` convention**, alongside its own
  `COPILOTKIT_TELEMETRY_DISABLED` variable — both accepted, opt-out takes precedence
  over sampling, and opting out purges queued state.
- **Delivery backend named explicitly**: PostHog, via CopilotKit's own ingest contract —
  i.e., they didn't build their own ingest service, they used an existing product
  analytics platform (PostHog is self-hostable, which matters if we want the same
  option without depending on a third party's cloud).

### OpenTelemetry GenAI semantic conventions — real, active, but not stable

Confirmed via web search: `gen_ai.*` semantic conventions are a real, actively-developed
part of the OpenTelemetry project, covering exactly agent-execution-lifecycle shapes —
`invoke_agent` (an agent run) as a span containing nested `chat`/`execute_tool`/`plan`
spans, with `gen_ai.operation.name` spanning `create_agent`, `invoke_agent`,
`invoke_workflow`, `execute_tool`, `retrieval`, and `plan`. As of mid-2026 they were
split into their own dedicated repository (June 2026, v1.42.0) for a faster release
cadence, separate from OpenTelemetry's stability-bound core conventions — but **every
gen_ai.* attribute, span, and metric still carries a "Development" stability badge, not
"Stable."** **Update (2026-09-18, independent QA pass):** if anything, this is less
settled than stated above — the new dedicated repo has **no tagged release yet** and its
schema URL is still a literal `TODO`. Core chat/embedding attributes are described as
solid enough for production dashboards; **agent and tool-orchestration conventions
specifically — the part most
relevant to our phase/gate/check events — are explicitly called out as still settling.**

## Recommendation

**Two layers, not one, matching what OpenBot itself does:**

1. **Our own closed, allowlisted event schema is the source of truth**, modeled directly
   on `oss.desktop.*`'s shape: a fixed set of event types (`phase_started`,
   `phase_ended`, `gate_presented`, `gate_approved`, `check_result`, `retry_attempted`,
   `friction_reported`, `run_completed`), each with an enum/count/duration-only property
   set, explicitly forbidding free text, file paths, code content, or anything
   credential-adjacent. This is what makes the analytics goal from this session's
   design ("know when to trigger certain calls, such as start/end of specific phases")
   concrete and enforceable rather than aspirational. Persist locally first, always;
   never let a delivery failure block a phase from proceeding.
2. **Optionally express the same events as OpenTelemetry `gen_ai.*` spans** (mapping a
   phase run to `invoke_agent`, a governed tool/MCP call to `execute_tool`, the
   coordinator's plan-generation step to `plan`) purely as an **exporter**, not as the
   schema of record — because the parts of the convention we'd lean on hardest
   (agent/tool-orchestration shapes) are explicitly still in flux. This buys
   interoperability with any OTel-speaking dashboard/backend a deployment already runs,
   without coupling our correctness to a spec that might still change field names.
3. **For an optional external sink, reuse an existing product rather than building an
   ingest pipeline** — PostHog (self-hostable) is the concrete, already-proven choice
   right here in the codebase we're building on top of, so it's also the path of least
   friction if we ever want OpenBot's and our own harness's telemetry to land in one
   place. Respect `DO_NOT_TRACK=1` the same way OpenBot does, so one env var opts a
   deployment out of both systems consistently.

This satisfies "without reinventing the wheel" the same way Track E's recommendation
does: reuse an existing, already-adjacent pattern (OpenBot's own telemetry design) for
the schema discipline, and an existing spec (OTel GenAI conventions) for the wire
format where it's solid enough, without taking a hard dependency on the parts that
aren't.

## Open threads (not blocking)

1. Exact current PostHog self-hosting cost/ops footprint, if we want the optional
   external sink to actually be exercised rather than just designed for.
2. Revisit the OTel GenAI agent/tool-orchestration conventions' stability status before
   final implementation — "Development" status in a fast-moving spec means field names
   could still shift between now and whenever this is built.
