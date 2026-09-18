# Agentic Control Plane — Implementation Plan

> **Repositioned 2026-09-18: this is now a candidate realization of `FRD.md`.** 
> The system has pivoted from a hardcoded utility to a domain-agnostic **Agentic Control Plane**. 
> Phase 1 explicitly represents the creation of the *first reference MCP plugin* (.NET migration), while the subsequent phases dictate the build-out of the universal execution harness.

## Decisions this plan needs from the user
1. **Target repository to validate against**: does a real .NET Framework codebase exist to run this against end-to-end (Phase 8), or should a synthetic/sample repo be built for validation?
2. **LLM provider(s) actually in hand**: which of Azure AI / Vertex / Anthropic / OpenAI does the user actually have credentials for right now? 
3. **OpenBot deployment posture**: run OpenBot from a clean clone as-is (recommended, no fork needed).

## Phase 0 — Environment stand-up (Optional UI)
**Goal**: a working, unmodified OpenBot deployment for the optional UI path. (Not required for the standalone control plane).
- Clone OpenBot, setup basic keys, verify local agent testing capabilities.

## Phase 1 — Reference MCP Knowledge Pack (.NET Migration Plugin)
**Goal**: Build the first domain-specific plugin for the control plane: an MCP server exposing (a) a .NET audit skill and (b) a catalogue of parameterized .NET node templates.
- **Task 1**: Build a minimal custom static analyzer for .NET targeting detection.
- **Task 2**: Define the findings schema (category, severity, affected project, remediation-tag). *This JSON schema acts as the universal contract for the control plane.*
- **Task 3**: Build the initial node-template catalogue as MCP resources (e.g., `retarget-sdk-style-project`, `upgrade-incompatible-package`).
- **Exit criteria**: The MCP emits a compliant findings file against a .NET repo and serves parameterized prompt fragments.

## Phase 2 — Universal Graph-Generation Mechanism
**Goal**: The domain-agnostic logic inside the control plane that turns *any* findings file into a concrete, run-specific graph instance.
- Implement the grouping logic: group findings by category and blast radius.
- Request MCP templates dynamically to assemble a `graph-instance.json`.
- Build the stock/fallback generic graph path.
- **Exit criteria**: The control plane successfully generates a `graph-instance.json` from Phase 1's mock output.

## Phase 3 — Provider-Agnostic LLM Backend
**Goal**: Wire in multi-provider support for the control plane orchestrator.
- Implement a provider switch (Azure, Vertex, OpenAI, Anthropic) patterned on Langchain's existing adapters directly within our standalone control plane codebase.

## Phase 4 — Agentic Control Plane (Standalone Core)
**Goal**: The actual multi-agent control plane, functioning completely standalone.
- Build `agent-coordinator`, `agent-implementer`, and `agent-qa` as one standalone process.
- **Direct Execution:** Calls MCP directly, runs shell/git directly against local copies.
- **Approval Gate:** Implements the universal CLI prompt approval step, presenting the generated graph.
- **Optional AG-UI:** Exposes an `/ag-ui` endpoint so it can be registered in OpenBot as a bring-your-own-agent Bot to render visual approval cards.
- **Exit criteria (headless)**: CLI execution produces a plan, pauses for approval, and dispatches the implementer/QA cycle.

## Phase 5 — Universal Analytics Instrumentation
**Goal**: Wire the schema-defined telemetry into the control plane.
- Define universal events (`phase_started`, `gate_approved`, `check_result`, `friction_reported`).
- Emit locally first, ensuring no PII or codebase secrets leak into the logs.

## Phase 6 — Git-Native Integrity/Trust Layer
**Goal**: The core enforcement mechanism of the control plane.
- Baseline capture via `git status`/stash before any phase.
- Enforce commit-per-phase.
- **Audit Step:** Run `git diff <baseline>..HEAD --stat` after each phase. If the agent touched files outside the approved plan's scope, trigger a universal friction/escalation report immediately (Fail closed).
- Implement supplementary file hashing exclusively for un-tracked `.env` files.

## Phase 7 — Execution Environments
**Goal**: Ensure the QA verifier can execute real tests. For the reference implementation, this requires a .NET SDK.
- **Primary (standalone)**: Package the control plane with the required dependencies for the active MCP plugin (e.g., `dotnet-sdk-<current-LTS>`).
- Note domain-specific limitations (e.g., Linux containers cannot run legacy .NET Framework full MSBuilds) transparently in the verification outputs.

## Phase 8 — End-to-End Validation
**Goal**: Run the generalized Agentic Control Plane using the Phase 1 reference plugin against a real codebase.
- Validate that the universal guardrails (Phase 6 scope violation checks, Phase 5 telemetry, Phase 4 approvals) trigger perfectly during a real .NET migration attempt.

## Sequencing summary
Phases 1, 3, and 7 can proceed in parallel.
Phase 2 needs 1. Phase 4 needs 2 and 3. Phases 5 and 6 need 4. Phase 8 needs everything.