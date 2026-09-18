# InstallGraph: Agentic Control Plane

Autonomous, MCP-backed, graph-based Agentic Control Plane. 

**Core Identity Pivot:** This system is a generalized domain-agnostic orchestrator (an Agentic Control Plane). It oversees complex, multi-phase codebase transformations driven by swappable MCP knowledge packs. 
*First reference implementation:* upgrading a .NET Framework codebase to .NET Core, driven by an audit file, coordinated by a multi-agent CLI control plane, optionally fronted by a chat UI.

This file is the resumption point. If a session restarts (usage limit, compaction, new machine), **read this file in full first**, then read `FRD.md` (the primary spec), then check `research/README.md` for which research tracks are done, then check `logs/session-log.md` for the most recent entries, then continue from "Next action" below.

## Next action

**`FRD.md` now exists and is the primary spec** (updated 2026-09-18)
A tool-agnostic functional requirements document synthesizing everything below into numbered, testable requirements (AUDIT-*, PLAN-*, EXEC-*, QA-*, APPROVAL-*, INTEGRITY-*, ESCALATE-*, PROVIDER-*, TELEMETRY-*, ENV-*, UIATTACH-*, KNOWLEDGE-*). Read it first in a fresh session.

`IMPLEMENTATION-PLAN.md` (Phase 0-8) is now a *candidate realization* of that FRD, not the primary plan. It positions the .NET migration explicitly as Phase 1 (Reference Plugin), decoupling it from the core control plane.

**Nothing has been built yet.**

**Next action for a fresh session**: read `FRD.md` in full, then this session's standing recommendation:
1. **Do a bounded evaluation of the Strands Agents SDK future-research item (`FRD.md` §8 item 1) before investing further in `IMPLEMENTATION-PLAN.md` Phases 3-5.**
   Specifically resolve whether `sandbox/docker.py` can host a real build/test workflow (ENV-1/ENV-4), whether `interventions`/`hooks` satisfy APPROVAL-1 through APPROVAL-5's exact shape, and whether `telemetry`'s event schema meets TELEMETRY-2's privacy constraints as-is.
2. **Start `IMPLEMENTATION-PLAN.md` Phase 1 (reference audit engine / knowledge source) in parallel, regardless of (1)'s outcome**
   It only touches AUDIT-*/KNOWLEDGE-*, which don't depend on the orchestration/provider/telemetry questions Strands would affect.
3. **Get two decisions only the user can make**: a real target repo to validate against eventually, and which LLM provider credential is actually in hand right now. Neither blocks (1) or (2).

Headline findings so far (Corrected 2026-09-18):
- **Universal Contract:** The control plane strictly enforces governance (git-native baselines, proof over self-report). The MCP purely supplies the domain knowledge (audit rules, node templates).
- No existing product should be forked (Track A). Copilot upgrade agent validates the approach but has a proprietary license. AppCAT has the same license; building a custom reference static analyzer for the .NET proof-of-concept (Phase 1).
- Our coordinator/implementer/QA core is a **standalone process** (the Agentic Control Plane). It calls the MCP directly, runs its own git/shell commands directly, and has its own CLI-based approval gate.
- **OpenBot is optional, attached on top, never load-bearing.** When attached, the same process registers as one bring-your-own-agent AG-UI Bot.

## The design, as agreed so far

**Core (required) layer — a CLI-driven, graph-based Agentic Control Plane.**
An MCP server is the "brain": a swappable knowledge pack (e.g. .NET Framework -> .NET Core migration rules, or arbitrary future domains) exposed as skills. One skill runs an audit and emits a structured audit file. A terminal-based control plane ingests that audit file and dynamically builds a phase graph from it, or falls back to a generic stock migration plan if no audit exists. The graph is nodes + documentation-only edges, backed by a local per-run state store (run id, checkpoints, protected-path baseline).

Agents:
- **Coordinator** – walks the graph, dispatches work, never edits code itself.
- **Implementation agent(s)** – make the actual code/config changes, one phase at a time.
- **QA/verification agent** – proves things live (real build, real test run, granular itemized pass/fail per check) – never trusts a self-reported "it works."

Guardrails:
- File-hash/git baseline of the repo before any writes; audited against that baseline after.
- Exactly one consolidated human approval gate before the unattended run begins.
- Structured stop/friction-report path (fixed taxonomy, bounded retries).
- This layer must work fully headless — it is the enforceable core, not optional.

**Optional layer — OpenBot (https://github.com/CopilotKit/OpenBot) as the chat/UI front end.**
The standalone process executes its own tools directly and has its own CLI-based approval gate by default; when OpenBot is attached, that same approval step can *additionally* render as an OpenBot card.

**Two goals added explicitly:**
1. **Analytics/usage instrumentation.** The control plane must know when to fire tracked events (phase start/end, gate approved, etc.).
2. **Provider-agnostic LLM backend.** Swappable by config across Azure AI Foundry, Google Vertex, Anthropic, and OpenAI.

## Constraints on how this project itself gets worked on
- **Usage-conscious:** research runs single-stream, not parallelized across subagents.
- **Document everything, continuously:** Update `CLAUDE.md`, `research/`, and `logs/session-log.md` constantly.
- Nothing gets built yet. Current phase is research / specification only.

## Architecture decisions log
- **2026-09-17** – Core harness is CLI-driven and graph-based. OpenBot adopted as optional UI.
- **2026-09-18** – Fixed architecture: The core is a standalone process that executes its own commands directly, not managed by OpenBot.
- **2026-09-18** – Evaluated CopilotKit/harness-sdk (Strands fork) as high potential for satisfying Phase 3-5 execution/telemetry.
- **2026-09-18** – `FRD.md` created as primary spec.
- **2026-09-18** – **PIVOT:** Redefined the system as a generalized "Agentic Control Plane." Decoupled the .NET domain logic into a "reference implementation knowledge pack." The core system is now explicitly domain-agnostic.
- **2026-09-18** – **Enterprise SDLC hardening.** User issued "Principal Engineering Directives" (contract-driven interfaces, dependency inversion, event sourcing, bounded autonomy, ephemeral sandboxing, fail-closed integrity, zero-trust credentialing, proof-over-prose verification, hermetic LLM testing, schema-validated telemetry). Gap analysis against `FRD.md` found 14 real gaps (schema versioning, storage/telemetry dependency inversion, event sourcing, crash resumption, sandbox isolation, prompt-level secret redaction, knowledge-pack supply chain, hermetic testing, telemetry schema validation, control-plane's own code quality, cost/time budgets, event-log tamper evidence, non-git side-effect handling, requirement→test→telemetry traceability). All 14 resolved into new/amended FRD requirement IDs: `AUDIT-6`, `KNOWLEDGE-4`, `EXEC-6/7/8`, `INTEGRITY-6/7/8`, `PROVIDER-3`, `TELEMETRY-4/5`, `ENV-3/4`, and new families `STORAGE-*` (§4.13), `PROMPT-*` (§4.14), `TEST-*` (§4.15), `BUDGET-*` (§4.16), `PROCESS-*` (§4.17), plus a new `§9 Traceability` mechanism. **Explicit caveat added to FRD §1**: this governs process integrity, not code correctness — no set of requirements gives "100% certainty" of enterprise-grade output; human review of generated code remains load-bearing.

## Key references
- `FRD.md` (this repo) – **the primary spec.** Tool-agnostic, domain-agnostic functional requirements.
- `IMPLEMENTATION-PLAN.md` (this repo) – one candidate realization of the FRD.
- `COPILOTKIT-ONBOARDING-JOURNAL.md` (this repo) – the reference pattern for the CLI/graph execution.