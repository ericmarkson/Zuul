# Functional Requirements Document — Agentic Control Plane (InstallGraph)

**Status**: draft, updated for domain-agnostic pivot (2026-09-18).
**Supersedes prior documents as the primary spec.** 

## 1. Purpose and scope

InstallGraph is an **Agentic Control Plane** that autonomously carries out structured, multi-phase code migrations and engineering tasks against a target codebase with as little required human interaction as the risk of the work allows. 

It is explicitly **not** a fully unsupervised system: it is designed around exactly one human decision point, after which it operates unattended within a bounded, auditable scope, and it is designed to fail safely and legibly when it hits something outside that scope. 

**Domain Agnosticism:** The control plane is strictly domain-agnostic. It enforces governance, state management, and execution safety. The domain knowledge (e.g., upgrading a .NET Framework codebase to .NET Core, which serves as our first reference implementation) is strictly injected via a swappable MCP knowledge pack.

**In scope**: The execution control plane itself — assessment ingestion, plan generation, execution, verification, integrity tracking, human approval, telemetry, and optional observability attachment.

**Out of scope** (see §7): The specific domain knowledge content (what to do about any given framework API), procurement of LLM credentials, and any specific vendor product's internal behavior.

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

### 4.7 Escalation / friction handling (ESCALATE)
- **ESCALATE-1**: The system SHALL halt unattended modification and produce a structured escalation report on unrecoverable errors.
- **ESCALATE-2**: The report SHALL classify the failure against a fixed, universal taxonomy (e.g., environment, credential, tooling gap, validation loop, scope conflict).
- **ESCALATE-3**: The report SHALL exclude secrets and full source content.
- **ESCALATE-4**: An escalation SHALL leave the target codebase in a state where every change made so far is individually attributable.

### 4.8 Provider / model independence (PROVIDER)
- **PROVIDER-1**: The system SHALL support configuration-driven selection of the underlying language-model backend.
- **PROVIDER-2**: Adding support for an additional provider SHOULD require incremental configuration, not a redesign.

### 4.9 Analytics and telemetry (TELEMETRY)
- **TELEMETRY-1**: The system SHALL emit a structured record of key lifecycle events (phase start/end, approval, verification outcome).
- **TELEMETRY-2**: This record SHALL use a closed, defined schema and exclude PII/Code.
- **TELEMETRY-3**: Recording SHALL be non-blocking.

### 4.10 Execution environment (ENV)
- **ENV-1**: The system SHALL be able to execute real verification operations in an execution environment appropriate for the domain knowledge injected.
- **ENV-2**: Environment limitations MUST be explicitly disclosed, never silently skipped.

### 4.11 Optional UI / observability attachment (UIATTACH)
- **UIATTACH-1**: Any optional interface attachment SHALL be additive only.
- **UIATTACH-2**: Visual renderings of approval checkpoints SHALL represent the identical underlying headless state machine.

### 4.12 Knowledge source interface (KNOWLEDGE)
- **KNOWLEDGE-1**: Domain-specific knowledge SHALL be served from a separate component via MCP.
- **KNOWLEDGE-2**: Updating domain knowledge SHALL NOT require modifying the control plane.
- **KNOWLEDGE-3**: The system SHALL treat the knowledge source as swappable.

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

## 8. Future research items
1. **Strands Agents SDK (Apache 2.0)**: Evaluate if its modules (multiagent, hooks, sandbox, interventions) satisfy EXEC, PROVIDER, TELEMETRY, and UIATTACH for the control plane natively.