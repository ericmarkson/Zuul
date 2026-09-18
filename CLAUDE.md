# InstallGraph

Autonomous, MCP-backed, graph-based upgrade harness. First target use case: upgrading a
.NET Framework codebase to .NET Core, driven by an audit file, coordinated by a
multi-agent CLI harness, optionally fronted by a chat UI.

This file is the resumption point. If a session restarts (usage limit, compaction, new
machine), **read this file in full first**, then read `FRD.md` (the primary spec), then
check `research/README.md` for which research tracks are done, then check
`logs/session-log.md` for the most recent entries, then continue from "Next action"
below.

---

## Next action

**`FRD.md` now exists and is the primary spec** (added 2026-09-18) — a tool-agnostic
functional requirements document synthesizing everything below into numbered,
testable requirements (AUDIT-*, PLAN-*, EXEC-*, QA-*, APPROVAL-*, INTEGRITY-*,
ESCALATE-*, PROVIDER-*, TELEMETRY-*, ENV-*, UIATTACH-*, KNOWLEDGE-*). Read it first in
a fresh session. `IMPLEMENTATION-PLAN.md` (Phase 0–8) is now a *candidate realization*
of that FRD, not the primary plan — it needs re-validation against the FRD before
further build-out, especially since `FRD.md` §8 flags Strands Agents SDK (see below) as
a possible way to satisfy several phases with far less hand-built code than the plan
currently assumes. Research (Tracks A–G) remains the supporting evidence for both
documents. **Nothing has been built yet.**

**Next action for a fresh session**: read `FRD.md` in full, then this session's standing
recommendation (given, not yet acted on — the session ended on usage limits before the
user confirmed which way to go):

1. **Do a bounded evaluation of the Strands Agents SDK future-research item (`FRD.md`
   §8 item 1) before investing further in `IMPLEMENTATION-PLAN.md` Phases 3–5.**
   Specifically resolve the three things flagged as unverified there: whether
   `sandbox/docker.py` can host a real .NET build/test workflow (ENV-1/ENV-4), whether
   `interventions`/`hooks` satisfy APPROVAL-1 through APPROVAL-5's exact shape, and
   whether `telemetry`'s event schema meets TELEMETRY-2's privacy constraints as-is.
   Rationale: if Strands holds up, it could replace most of the hand-built
   provider-switching/AG-UI-plumbing/telemetry work those phases currently plan for —
   building that by hand first risks discarding it.
2. **Start `IMPLEMENTATION-PLAN.md` Phase 1 (audit engine / knowledge source) in
   parallel, regardless of (1)'s outcome** — it only touches AUDIT-*/KNOWLEDGE-*, which
   don't depend on the orchestration/provider/telemetry questions Strands would affect.
3. **Get two decisions only the user can make**: a real target repo to validate against
   eventually, and which LLM provider credential is actually in hand right now. Neither
   blocks (1) or (2).

`IMPLEMENTATION-PLAN.md`'s original four decisions still stand alongside these (audit
engine already resolved toward "build custom"; confirming no OpenBot fork already
resolved as "no fork").

Headline findings so far, if resuming cold — **corrected 2026-09-18 after an
independent QA pass found the correction below hadn't fully propagated**:
- No existing product should be forked (Track A) — Microsoft's GitHub Copilot upgrade
  agent family validates the whole approach but ships under a proprietary,
  non-redistributable license. (Correction: it is **not** actually model-locked — it
  supports bring-your-own-key for Anthropic/Bedrock/Google AI Studio/Microsoft
  Foundry/OpenAI/xAI. The license, not the model backend, is the real reason it can't be
  adopted.) AppCAT (a candidate audit-engine dependency) turned out to ship under the
  same proprietary license family — build a custom static analyzer instead (Phase 1).
- Our coordinator/implementer/QA core is a **standalone process** — it calls the MCP
  directly, runs its own git/shell/dotnet commands directly, and has its own CLI-based
  approval gate. It does **not** require an OpenBot MCP-plugin registration, and it does
  **not** depend on OpenBot's gateway for tool execution. (This reverses what an earlier
  version of this section said — see the 2026-09-18 decision log entries for why.)
- **OpenBot is optional, attached on top, never load-bearing.** When attached, the same
  process registers as one bring-your-own-agent AG-UI Bot (not three separate ones —
  OpenBot gives each *managed* Bot its own isolated workspace volume, which would break
  a shared working copy across three). Registration needs a documented prerequisite
  (`AGENT_ENDPOINT_ALLOWED_HOSTS`, since OpenBot's SSRF guard refuses private/loopback
  endpoints by default) and the approval gate's optional card rendering uses a
  fixed-schema granted component, not free-form content.
- OpenBot's `agent-computer` **can** run real `dotnet build`/`test` via a custom
  `COMPUTER_IMAGE`, confirmed against source (Track B) — but this is now the *optional*
  execution environment; the primary path is our own standalone environment. Target the
  **current .NET LTS at build time, not a hardcoded version** — .NET 8 reaches
  end-of-support 2026-11-10, so it must not be what this project produces as output.
- Provider-agnostic LLM backend (Track E): pattern our own provider switch directly on
  `agent-langgraph/src/model-key.ts`'s shape (`openai`/`anthropic`/`google` plus new
  `azure`/`vertex` branches via official LangChain packages) — built in our own
  codebase, not by editing an OpenBot example Bot.
- AG-UI protocol (Track C): a Bot is one streamed-SSE HTTP endpoint using MIT-licensed,
  framework-agnostic `@ag-ui/core`/`@ag-ui/encoder` — genuinely pluggable in any
  language. The "a Bot calls back into OpenBot's gateway for every tool call" pattern is
  **application-level code OpenBot's own shipped example Bots chose to write**, not a
  requirement AG-UI or OpenBot's registration imposes — confirmed directly against
  OpenBot's server source. A bring-your-own agent can execute its own tools directly.
  AG-UI's deployment-tool/surface-tool split (a call to the latter ends the run for a
  human to answer) remains a good pattern for the approval gate's *optional* card
  rendering, alongside the CLI prompt that's the default.

---

## The design, as agreed so far

**Core (required) layer — a CLI-driven, graph-based upgrade harness.**
An MCP server is the "brain": a swappable knowledge pack (e.g. .NET Framework → .NET
Core migration rules) exposed as skills. One skill runs an audit and emits a structured
audit file. A terminal-based harness (architecturally modeled on the CopilotKit
`onboard` CLI — see `COPILOTKIT-ONBOARDING-JOURNAL.md` in this repo) ingests that audit
file and dynamically builds a phase graph from it, or falls back to a generic stock
migration plan if no audit exists. The graph is nodes + documentation-only edges,
backed by a local per-run state store (run id, checkpoints, protected-path baseline).

Agents:
- **Coordinator** — walks the graph, dispatches work, never edits code itself.
- **Implementation agent(s)** — make the actual code/config changes, one phase at a
  time.
- **QA/verification agent** — proves things live (real build, real test run, granular
  itemized pass/fail per check) — never trusts a self-reported "it works."

Guardrails (all lifted from the CopilotKit onboarding graph pattern, generalized):
- File-hash baseline of the repo before any writes; audited against that baseline after.
- Exactly one consolidated human approval gate before the unattended run begins.
- Structured stop/friction-report path (fixed taxonomy, bounded retries) instead of
  silent failure or infinite retries.
- This layer must work fully headless — it is the enforceable core, not optional.

**Optional layer — OpenBot (https://github.com/CopilotKit/OpenBot) as the chat/UI front
end.**
**Corrected 2026-09-18** (see decision log): the coordinator/implementer/QA core is one
standalone process, registered — when OpenBot is attached at all — as a single
bring-your-own-agent AG-UI endpoint, not as three separate OpenBot-managed "coworkers."
The core executes its own tools directly (git, shell, dotnet, MCP calls) and has its own
CLI-based approval gate by default; when OpenBot is attached, that same approval step
can *additionally* render as an OpenBot card (a granted, fixed-schema component), and
OpenBot's own Postgres audit trail becomes a bonus second record — never the only one,
and never required. Registering the standalone process with OpenBot requires
`AGENT_ENDPOINT_ALLOWED_HOSTS` (OpenBot's SSRF guard refuses private/loopback endpoints
by default). Must stay fully decoupled/optional, same as the MCP: the harness has to run
standalone without it — confirmed as architecturally sound directly against OpenBot's
server source, not just assumed.

*Former open risk, now substantially de-risked (see Track B):* OpenBot's per-bot
sandboxed "computer" runs plain Ubuntu 24.04 and is swappable per-deployment via the
`COMPUTER_IMAGE` env var — a custom image (base + `dotnet-sdk` apt package) plus the
Bot's own shell capability cloning the target repo into `/workspace` is enough to run
real `dotnet build`/`test`, no fork required. One inherent (not OpenBot-specific)
limitation remains: a Linux container can't build the *original* .NET Framework
baseline pre-migration (needs Windows/full-framework MSBuild) — treat that baseline as
audit/static-analysis evidence only, not a live build, unless a Windows runner is
separately available. Forking OpenBot is no longer expected to be necessary for this
reason; it remains a theoretical fallback for reasons not yet discovered.

**Two goals added explicitly, to be designed for from the start, not bolted on later:**

1. **Analytics/usage instrumentation.** The harness must know when to fire tracked
   events — phase start/end, gate presented/approved, check pass/fail, retry, friction
   report, run complete — as a real event stream. Must work whether OpenBot is present
   or not. Must be additive to OpenBot's own audit trail, not a duplicate of it (OpenBot
   audits tool-calls/permissions; this is upgrade-run KPIs — phase duration, retry
   counts, approval latency, etc.).

2. **Provider-agnostic LLM backend.** Whatever calls the model must be swappable by
   config/credential across Azure AI Foundry, Google Vertex, Anthropic, and OpenAI — by
   reusing an existing abstraction layer, not by hand-rolling our own provider adapters.

---

## Constraints on how this project itself gets worked on

- **Usage-conscious: research runs single-stream, not parallelized across subagents.**
  Don't spawn parallel research agents for this project. Do lookups sequentially in the
  main session (WebSearch/WebFetch/gh/etc.), one track at a time.
- **Document everything, continuously**, specifically so a fresh session can resume
  after hitting a usage cap without re-deriving context:
  - `CLAUDE.md` (this file) — living design doc + "Next action" pointer. Update the
    "Next action" section and the architecture-decisions log below every time a
    decision is made or a track finishes.
  - `research/` — one findings file per research track, plus `research/README.md` as
    the status index.
  - `logs/session-log.md` — append-only chronological log of what was actually done
    (commands run, sources checked, decisions made), timestamped. Never edit past
    entries; only append.
- Nothing gets built yet. Current phase is research only.

---

## Architecture decisions log

(Append new entries here, most recent last, with a date. Don't rewrite history — if a
decision changes, add a new entry that supersedes the old one and say so.)

- **2026-09-17** — Core harness is CLI-driven and graph-based, modeled directly on the
  CopilotKit `onboard` CLI pattern documented in `COPILOTKIT-ONBOARDING-JOURNAL.md`.
- **2026-09-17** — OpenBot adopted as the optional UI/chat front end, via AG-UI. Kept
  strictly decoupled from the core harness.
- **2026-09-17** — Added analytics/telemetry and provider-agnostic LLM backend as
  first-class design goals, to be researched before any implementation planning.
- **2026-09-17** — Research track order set, with a new Track A inserted ahead of
  everything else: survey for existing/forkable prior art before designing any piece of
  this ourselves. See `research/README.md`.
- **2026-09-17** — All 7 research tracks (A–G) completed in one single-stream session
  (no parallel subagents, per usage constraint). Key resulting decisions, each argued in
  full in its findings file: (1) build our own harness, nothing found is forkable
  (Track A); (2) our MCP knowledge pack owns node *templates*, the harness's
  graph-generation step is purely mechanical — group audit findings by category (and
  blast radius), instantiate templates, emit a run-specific graph once before the
  approval gate (Track F); (3) provider-agnostic LLM support extends OpenBot's existing
  LangChain-adapter switch with `azure`/`vertex` branches, not a new abstraction
  (Track E); (4) our coordinator/implementation/QA agents are AG-UI servers whose tools
  are executed by OpenBot's gateway, never by our own agent code directly — so the MCP
  must be registered as an OpenBot plugin, and the one approval gate is built on AG-UI's
  existing surface-tool/end-run mechanism (Track C); (5) git (commit-per-phase, diff
  against baseline) replaces a bespoke file-hash store as the primary integrity
  mechanism, with hashing reserved only for gitignored/credential paths git can't see
  (Track G); (6) analytics uses a closed, allowlisted local event schema modeled on
  OpenBot's own `oss.desktop.*` telemetry design, optionally exported as OpenTelemetry
  `gen_ai.*` spans (still "Development" stability — exporter only, not schema of
  record), with PostHog as the reused option for an external sink (Track D).
- **2026-09-18** — **Correction**: `IMPLEMENTATION-PLAN.md`'s original Phase 4 wrongly
  built the coordinator/implementer/QA core as OpenBot-gateway-managed Bots (copying
  the pattern Track C found in OpenBot's *own shipped* example Bots), which made
  OpenBot load-bearing for the core to function — directly contradicting this project's
  original, never-revoked requirement that the harness run fully headless with OpenBot
  strictly optional. Fixed: the core is now a standalone process that executes its own
  git/shell/dotnet/MCP calls directly and implements its own approval gate (CLI prompt
  by default), with OpenBot attachable only as an optional "bring-your-own-agent" AG-UI
  endpoint for chat/observability — never as the execution path. Track G's git-native
  trust layer is now the harness's primary audit mechanism, not something complementary
  to a gateway that may not exist. See addenda in `research/C-agui-protocol-mechanics.md`,
  `research/G-trust-layer-reconciliation.md`, and the Phase 4/6/7 correction notes in
  `IMPLEMENTATION-PLAN.md`.
- **2026-09-18** — **Independent QA pass** (a separate Opus agent, tasked specifically
  with fact-checking the correction above against OpenBot's actual server source rather
  than trusting our own research files' summaries), requested after the correction above
  was flagged as unverified inference. Findings:
  - **The core claim is confirmed true, not just plausible.** Read directly:
    `server/src/agents/connection-test.ts` (registration is just "POST once, confirm an
    AG-UI event comes back" — no token, no callback), `profile-store.ts`
    (`issueCallbackToken` is a separate, explicit admin action never triggered by
    registration), and `copilot.ts` ("A Bot at an endpoint runs its own loop..."). The
    gateway-proxy pattern (`MANAGED_AGENT_TOKEN`, `OPENBOT_TOOL_URL`, the
    `callsTheSurface` conditional edge) is confirmed to be **application-level code
    inside `agent-langgraph/src/index.ts` itself** — not anything `@ag-ui/core`/
    `@ag-ui/encoder` or OpenBot's registration path requires.
  - **But the correction hadn't fully propagated** — this file's own "headline findings"
    and OpenBot-design sections still stated the pre-correction architecture as fact,
    120 lines below the fix. Now corrected (see above sections).
  - **Three independent factual errors found**, none related to the architecture fix:
    (1) .NET 8 reaches end-of-support 2026-11-10 — the plan targeted it as the migration
    output throughout; now corrected to "current LTS at build time, not hardcoded."
    (2) GitHub Copilot's upgrade agent is not model-locked (it has BYOK for
    Anthropic/Bedrock/Google AI Studio/Microsoft Foundry/OpenAI/xAI) — the license is
    the real reason it can't be adopted, not the model backend; Track A's verdict
    survives, its stated reason didn't. (3) AppCAT — Phase 1's leading audit-engine
    candidate — ships under the same proprietary, non-redistributable license family as
    the rejected Copilot products; Decision 1 now points at a custom analyzer.
  - **New findings about the optional OpenBot-attached path**: it needs
    `AGENT_ENDPOINT_ALLOWED_HOSTS` configured (OpenBot's SSRF guard refuses
    private/loopback registration by default); it should register the whole
    coordinator/implementer/QA loop as **one** Bot, not three (OpenBot gives each
    *managed* Bot an isolated workspace volume, which would break a shared working
    copy across three); and the approval card is a granted, fixed-schema component
    (`askApproval` in `app/src/components/gallery/decisions.tsx`), not free-form.
  - Full report incorporated into `IMPLEMENTATION-PLAN.md` (corrections in Phases 0, 1,
    3, 4, 6, 7, the sequencing diagram, and the open-threads list) and this file's
    headline findings / OpenBot-design sections above.
- **2026-09-18** — User surfaced `CopilotKit/harness-sdk` (confirmed to be an
  unmodified fork of AWS's `strands-agents/harness-sdk`, Apache 2.0) and asked for a
  survey of the rest of the CopilotKit org. Findings (full detail in conversation, not
  yet a dedicated research file): Strands' `litellm`-backed provider, `multiagent`/
  `hooks`/`interventions`/`telemetry`/`sandbox` modules, and official `ag_ui_strands`
  AG-UI bridge look like they could satisfy much of `IMPLEMENTATION-PLAN.md`'s Phases
  3–5 and part of 7 with far less hand-built code — not yet evaluated in depth. Of the
  rest of the org, `aimock` (MIT — mocks LLM/MCP/AG-UI, useful for testing) and
  `pathfinder` (Elastic License 2.0 — self-hosted MCP server, reference only) were the
  other genuinely relevant finds; `open-mcp-client` and `open-multi-agent-canvas` were
  not (demo-only / requires CopilotKit Cloud respectively).
- **2026-09-18** — **`FRD.md` created and made the primary spec.** User asked to
  generalize the project's direction away from specific tools and toward a tool-agnostic
  functional requirements document, and to park the Strands finding above as a future
  research item rather than act on it immediately. `IMPLEMENTATION-PLAN.md` and
  `research/*.md` repositioned as a candidate realization and supporting evidence,
  respectively — not superseded, just subordinate. See `FRD.md` §8 for the future
  research items list (Strands SDK, generic OSS agent-orchestration frameworks, aimock,
  pathfinder, the audit-engine choice, and the coordinator/implementer/verifier
  process-topology question).

---

## Key references

- `FRD.md` (this repo) — **the primary spec.** Tool-agnostic functional requirements.
  Read this before `IMPLEMENTATION-PLAN.md`.
- `IMPLEMENTATION-PLAN.md` (this repo) — one candidate realization of the FRD, using
  specific researched tools. Needs re-validation against `FRD.md` before further
  build-out.
- `COPILOTKIT-ONBOARDING-JOURNAL.md` (this repo) — the reference pattern for the
  CLI/graph harness, reverse-engineered from a real onboarding run plus the actual
  installed CLI source.
- OpenBot: https://github.com/CopilotKit/OpenBot
- AG-UI protocol: https://github.com/ag-ui-protocol/ag-ui
- Strands Agents SDK (future research item, not yet adopted): https://github.com/strands-agents/harness-sdk
  (mirrored, unmodified, at https://github.com/CopilotKit/harness-sdk)
