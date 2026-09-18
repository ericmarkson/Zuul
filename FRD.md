# Functional Requirements Document — Agentic Control Plane (InstallGraph)

**Status**: draft, updated for domain-agnostic pivot (2026-09-18); amended (2026-09-18) with enterprise SDLC hardening requirements (event sourcing/resumption, tamper-evident integrity, sandbox isolation, prompt-level secret redaction, hermetic testing, cost/time budgets, engineering process, traceability).
**Supersedes prior documents as the primary spec.** 

## 1. Purpose and scope

InstallGraph is an **Agentic Control Plane** that autonomously carries out structured, multi-phase code migrations and engineering tasks against a target codebase with as little required human interaction as the risk of the work allows. 

It is explicitly **not** a fully unsupervised system: it is designed around exactly one human decision point, after which it operates unattended within a bounded, auditable scope, and it is designed to fail safely and legibly when it hits something outside that scope. 

**Domain Agnosticism:** The control plane is strictly domain-agnostic. It enforces governance, state management, and execution safety. The domain knowledge (e.g., upgrading a .NET Framework codebase to .NET Core, which serves as our first reference implementation) is strictly injected via a swappable MCP knowledge pack.

**In scope**: The execution control plane itself — assessment ingestion, plan generation, execution, verification, integrity tracking, human approval, telemetry, and optional observability attachment.

**Out of scope** (see §7): The specific domain knowledge content (what to do about any given framework API), procurement of LLM credentials, and any specific vendor product's internal behavior.

**Explicit limit of this document:** satisfying every requirement in §4 makes failures bounded, legible, and verifiable. It does not, and cannot, guarantee that the code a run produces is correct, well-designed, or fit for the target codebase's actual business purpose — that remains subject to human review. This document governs process integrity, not code judgment.

## 2. Definitions

- **Agentic Control Plane**: The generic, domain-agnostic execution harness that enforces the state machine, git-native baselines, and proof-over-self-report guardrails.
- **Target codebase**: the repository being modified.
- **Assessment artifact ("audit")**: a structured, machine-readable JSON description of the target codebase's task-relevant state — what needs to change and why.
- **Knowledge source (Plugin)**: the swappable domain-knowledge component (MCP server) that interprets audit findings and supplies remediation node templates.
- **Plan**: a concrete, ordered set of phases generated for one run, derived from an audit artifact.
- **Phase**: one unit of plan execution — a scoped set of changes plus its verification.
- **Run**: one end-to-end execution of the system against a target codebase.
- **Approval checkpoint**: the single required human decision point, occurring after plan generation and before any modification of the target codebase.

## 3. Overall description

### 3.1 Operating modes
The system SHALL be operable in exactly one required mode and one optional mode:
- **Required – headless.** The entire lifecycle SHALL function with no graphical or chat interface present.
- **Optional – attached observability/UI.** The system MAY additionally support attachment of a third-party conversational or observability interface (additive only).

### 3.2 Actors
- **The operator**: the human who runs the system and answers the approval checkpoint.
- **The coordinator**: the logical role that ingests the audit/plan and sequences execution. Does not itself modify the target codebase.
- **The implementer**: the logical role that makes the actual changes for one phase.
- **The verifier**: the logical role that independently confirms a phase's outcome by re-deriving evidence (e.g., a real build/test), never by trusting a self-report.

## 4. Functional requirements

### 4.1 Assessment ingestion (AUDIT)
- **AUDIT-1**: The system SHALL accept a structured assessment artifact describing the target codebase's task-relevant findings.
- **AUDIT-2**: Each finding in the artifact SHALL carry, at minimum: a category, a severity, and a reference to the specific affected location(s).
- **AUDIT-3**: The system SHALL support running with **no** assessment artifact present, by falling back to a default, generic plan.
- **AUDIT-4**: The mechanism that *produces* an assessment artifact SHALL be replaceable independently of the rest of the system.
- **AUDIT-5**: The system SHALL NOT assume the assessment artifact is complete or correct.
- **AUDIT-6**: Every assessment artifact and generated plan SHALL declare a schema version (semver). The system SHALL tolerate minor-version differences (per AUDIT-5) but SHALL refuse to run, and SHALL escalate rather than coerce, against an unsupported major version.

### 4.2 Plan generation (PLAN)
- **PLAN-1**: The system SHALL derive a concrete plan from the assessment artifact by grouping related findings into phases.
- **PLAN-2**: Grouping SHALL account for both category (findings of the same kind) and blast radius (findings that touch overlapping code).
- **PLAN-3**: When no assessment artifact is available, the system SHALL generate a default plan from a fixed, generic phase set.
- **PLAN-4**: The generated plan SHALL be represented in a durable, inspectable form before execution begins.
- **PLAN-5**: Once approved, a plan's scope for a given run SHALL NOT silently change.

### 4.3 Execution model (EXEC)
- **EXEC-1**: The system SHALL execute the approved plan phase by phase.
- **EXEC-2**: The coordinator role SHALL NOT itself modify the target codebase.
- **EXEC-3**: The system SHALL support a bounded retry policy per phase. 
- **EXEC-4**: A phase's implementation changes SHALL be individually attributable and reviewable.
- **EXEC-5**: The system SHALL be able to run to completion unattended after the approval checkpoint.
- **EXEC-6**: Execution state SHALL be persisted as an append-only event log using a fixed enum of event types (e.g., `RUN_STARTED`, `PLAN_GENERATED`, `GATE_APPROVED`, `PHASE_STARTED`, `CHECK_FAILED`, `PHASE_COMMITTED`, `SCOPE_VIOLATION_DETECTED`, `ESCALATED`, `RUN_COMPLETED`). The current run state SHALL be derived solely by replaying this log — the system SHALL NOT maintain or mutate a separate status field independently of it.
- **EXEC-7**: On restart, the system SHALL detect an in-progress run and resume from the last safe event boundary (e.g., `PHASE_COMMITTED`). If the log shows a phase attempt in progress with no corresponding verification/commit event, the system SHALL reset the target codebase to that phase's pre-attempt baseline (INTEGRITY-1) before re-attempting, and the re-attempt SHALL count against that phase's retry budget (EXEC-3).
- **EXEC-8**: The system SHALL prevent two processes from concurrently resuming or advancing the same run (e.g., via an exclusive lock keyed to run id).

### 4.4 Verification (QA)
- **QA-1**: Every phase SHALL be independently verified by the verifier role.
- **QA-2**: Verification SHALL re-derive evidence directly (e.g., actually invoking real build/test toolchains). It SHALL NOT accept self-reports.
- **QA-3**: Verification results SHALL be reported as multiple, independently-named checks.
- **QA-4**: The verifier role SHALL have no access to modify the target codebase.

### 4.5 Human approval (APPROVAL)
- **APPROVAL-1**: The system SHALL require exactly one consolidated human approval checkpoint per run.
- **APPROVAL-2**: The checkpoint SHALL present the complete generated plan.
- **APPROVAL-3**: The checkpoint SHALL be answerable through the system's required headless mode (CLI).
- **APPROVAL-4**: No modification of the target codebase beyond what was approved SHALL occur without explicit approval.

### 4.6 Integrity and change tracking (INTEGRITY)
- **INTEGRITY-1**: Before any modification, the system SHALL establish a baseline record of the target codebase's existing state (e.g., git-native baseline).
- **INTEGRITY-2**: Each phase's changes SHALL be individually reviewable (e.g., commit-per-phase).
- **INTEGRITY-3**: After each phase, actual changes SHALL be checked against the approved plan's declared scope. Out-of-scope changes trigger escalation.
- **INTEGRITY-4**: Un-trackable paths (e.g., `.env`) SHALL be covered by narrowly-scoped supplementary mechanisms (e.g., hashing).
- **INTEGRITY-5**: The system SHALL NOT read or expose the contents of credential files.
- **INTEGRITY-6**: Before the first write to the target codebase, the system SHALL verify that known credential-shaped paths (e.g., `.env`, `*.pfx`, cloud credential files) are excluded from version control. If any such path is not excluded, the system SHALL halt and escalate rather than proceed.
- **INTEGRITY-7**: The event log (EXEC-6) SHALL be tamper-evident (e.g., each record hash-chained to the previous one). The system SHALL verify chain integrity on resume and SHALL halt and escalate on any mismatch.
- **INTEGRITY-8**: Remediation node templates supplied by the knowledge source SHALL declare a side-effect class (`file-only`, `package-manager-mutating`, or `external-service-call`). Only `file-only` phases are eligible for the automatic baseline-reset retry described in EXEC-7; phases in the other classes SHALL require either a pack-supplied undo action or a documented compensating action in the escalation report before any retry.

### 4.7 Escalation / friction handling (ESCALATE)
- **ESCALATE-1**: The system SHALL halt unattended modification and produce a structured escalation report on unrecoverable errors.
- **ESCALATE-2**: The report SHALL classify the failure against a fixed, universal taxonomy (e.g., environment, credential, tooling gap, validation loop, scope conflict).
- **ESCALATE-3**: The report SHALL exclude secrets and full source content.
- **ESCALATE-4**: An escalation SHALL leave the target codebase in a state where every change made so far is individually attributable.

### 4.8 Provider / model independence (PROVIDER)
- **PROVIDER-1**: The system SHALL support configuration-driven selection of the underlying language-model backend.
- **PROVIDER-2**: Adding support for an additional provider SHOULD require incremental configuration, not a redesign.
- **PROVIDER-3**: The same dependency-inversion rule SHALL apply uniformly to telemetry sinks (§4.9) and the run-state store (§4.13): the orchestration core SHALL depend only on abstract interfaces (`ModelProvider`, `TelemetrySink`, `RunStore`) selected by a factory at bootstrap, and SHALL NOT import any concrete vendor SDK directly.

### 4.9 Analytics and telemetry (TELEMETRY)
- **TELEMETRY-1**: The system SHALL emit a structured record of key lifecycle events (phase start/end, approval, verification outcome).
- **TELEMETRY-2**: This record SHALL use a closed, defined schema and exclude PII/Code.
- **TELEMETRY-3**: Recording SHALL be non-blocking.
- **TELEMETRY-4**: Telemetry events SHALL be validated against a closed JSON Schema at emission time. A malformed event SHALL be blocked from emission and SHALL itself raise an internal (ESCALATE-class) error rather than being shipped.
- **TELEMETRY-5**: Telemetry event fields SHALL be restricted to enumerated categorical values and precise (ISO-8601) timestamps. The only free-text fields permitted are the fixed failure-taxonomy codes defined in ESCALATE-2 — no source code, file content, or arbitrary strings.

### 4.10 Execution environment (ENV)
- **ENV-1**: The system SHALL be able to execute real verification operations in an execution environment appropriate for the domain knowledge injected.
- **ENV-2**: Environment limitations MUST be explicitly disclosed, never silently skipped.
- **ENV-3**: Implementer and verifier code execution SHALL occur in an ephemeral, isolated environment (e.g., a container), which the control plane SHALL treat as running untrusted code. The environment SHALL be destroyed at run end or upon escalation.
- **ENV-4**: Network egress from the execution environment SHALL default to denied, permitting only an explicit allowlist required by the active knowledge pack and provider configuration (e.g., the LLM provider endpoint, required package registries).

### 4.11 Optional UI / observability attachment (UIATTACH)
- **UIATTACH-1**: Any optional interface attachment SHALL be additive only.
- **UIATTACH-2**: Visual renderings of approval checkpoints SHALL represent the identical underlying headless state machine.

### 4.12 Knowledge source interface (KNOWLEDGE)
- **KNOWLEDGE-1**: Domain-specific knowledge SHALL be served from a separate component via MCP.
- **KNOWLEDGE-2**: Updating domain knowledge SHALL NOT require modifying the control plane.
- **KNOWLEDGE-3**: The system SHALL treat the knowledge source as swappable.
- **KNOWLEDGE-4**: Every run SHALL record the active knowledge pack's immutable identity (e.g., git commit SHA or content hash) in the event log, for reproducibility. The system SHALL maintain an allowlist of trusted pack sources by hash or signing key; a pack not on the allowlist SHALL require explicit, one-time operator opt-in surfaced at the approval checkpoint (APPROVAL-2). A pack that ships executable code (not only data/templates) SHALL be subject to the same sandboxing as ENV-3.

### 4.13 Component abstraction and storage (STORAGE)
- **STORAGE-1**: Run state (event log, checkpoints, baselines) SHALL be persisted behind an abstract store interface (`RunStore`), selectable by configuration (per PROVIDER-3).
- **STORAGE-2**: The concrete storage backend SHALL be swappable (e.g., SQLite, Postgres, flat file) without changes to orchestration logic.

### 4.14 Prompt-level secret handling (PROMPT)
- **PROMPT-1**: Any content passed to an LLM provider SHALL first pass a secret-detection filter (regex and/or entropy-based); matches SHALL be masked before inclusion in the request.
- **PROMPT-2**: The secret-detection ruleset applied to prompts SHALL be the same ruleset, or a superset, of the one used to enforce TELEMETRY-2's PII/secret exclusion.

### 4.15 Hermetic testing (TEST)
- **TEST-1**: The control plane's own automated test suite SHALL execute with zero live network calls to any LLM provider, MCP knowledge pack, or telemetry sink.
- **TEST-2**: A deterministic mock model provider SHALL be available to tests, supporting scripted response sequences, malformed/truncated payloads, and injected timeouts.
- **TEST-3**: The test suite SHALL include fixtures for malformed or schema-invalid assessment/plan artifacts (missing required fields, wrong types, oversized payloads, unsupported schema major version per AUDIT-6).
- **TEST-4**: The test suite SHALL include fault-injection tests that terminate the process at each event-type boundary (EXEC-6) and assert correct resume or reset behavior (EXEC-7).

### 4.16 Cost and time governance (BUDGET)
- **BUDGET-1**: The system SHALL enforce a hard wall-clock timeout per phase and per run.
- **BUDGET-2**: The system SHALL enforce a hard token/request ceiling per phase, enforced by the provider abstraction itself rather than relied upon from the model's own behavior.
- **BUDGET-3**: Exceeding a budget SHALL be treated identically to exhausting a retry budget (EXEC-3): halt and escalate (ESCALATE-1), never continue silently.
- **BUDGET-4**: Telemetry SHALL record cumulative token/cost usage per run.

### 4.17 Engineering process for the control plane itself (PROCESS)
- **PROCESS-1**: The control plane's own codebase SHALL pass strict type-checking and linting in CI before merge.
- **PROCESS-2**: No change to the state-machine, integrity-check, or approval-gate code paths SHALL merge without passing the full TEST-* hermetic suite and a human review, given these are the system's highest-blast-radius code.

## 6. Acceptance criteria (system-level)
The system SHALL be considered to satisfy this FRD when, for at least one real target codebase (e.g., .NET reference):
1. Runs and executes fallback plans (AUDIT-3, PLAN-3).
2. Translates a real assessment artifact into a blast-radius grouped plan (PLAN-1, PLAN-2).
3. Halts at exactly one headless approval checkpoint (APPROVAL-1).
4. Detects out-of-scope changes and escalates (INTEGRITY-3, ESCALATE-1).
5. Produces multi-check verification (QA-3).
6. Generates telemetry without secrets (TELEMETRY-1).
7. Operates successfully via two distinct LLM providers (PROVIDER-1).
8. Runs headlessly, and separately via UI, with identical core behavior (UIATTACH-1).
9. Survives a forced kill mid-phase and correctly resumes or resets on restart (EXEC-6, EXEC-7).
10. Detects an unexcluded credential-shaped file pre-write and halts before any modification (INTEGRITY-6).
11. Passes its full hermetic test suite (TEST-1 through TEST-4) with zero live network calls.
12. Halts and escalates when a configured budget is exceeded, mid-run (BUDGET-3).
13. Every requirement ID in §4 has at least one mapped test and, where applicable, telemetry event, per §9.

## 8. Future research items
1. **Strands Agents SDK (Apache 2.0)**: Evaluate if its modules (multiagent, hooks, sandbox, interventions) satisfy EXEC, PROVIDER, TELEMETRY, and UIATTACH for the control plane natively. Now also evaluate against EXEC-6/7/8 (event sourcing/resumption), ENV-3/4 (sandbox isolation), and BUDGET-* — `sandbox/docker.py` and `interventions` are the modules most likely to already cover these.

## 9. Traceability

Every requirement ID in §4 SHALL have at least one entry in a generated `traceability.yaml` (or equivalent), mapping:
- the requirement ID (e.g., `EXEC-7`) →
- the test(s) that exercise it (TEST-* fixtures, unit/fault-injection tests), and →
- the telemetry event type(s), if any, that would prove it fired in a real run (EXEC-6's event enum).

CI SHALL fail if any requirement ID has zero mapped tests. This turns §4 from a policy statement into an enforced contract: a requirement that nothing tests is, by construction, unverifiable, and this mechanism makes that condition a build failure rather than a silent gap.

This does not by itself guarantee the *content* produced by a run is correct or fit for business purpose — see the note in §1 on scope. It guarantees that every governance rule this document states is either checked automatically or visibly unchecked.