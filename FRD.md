# Functional Requirements Document — InstallGraph

**Status**: draft, first version. **Supersedes prior documents as the primary spec.**
`IMPLEMENTATION-PLAN.md` and `research/*.md` remain valid as a researched, candidate
realization of this FRD and as supporting evidence — but this document is now the
source of truth for *what the system must do*. Implementation planning should validate
against this FRD, not the other way around.

This is a living document, same conventions as `CLAUDE.md`: append-don't-rewrite when a
requirement changes, date every substantive edit, strike superseded text visibly rather
than deleting it.

---

## 1. Purpose and scope

InstallGraph is a system that autonomously carries out a structured, multi-phase code
migration against a target codebase — the motivating case is upgrading a .NET Framework
codebase to .NET (Core) — with as little required human interaction as the risk of the
work allows. It is explicitly **not** a fully unsupervised system: it is designed around
exactly one human decision point, after which it operates unattended within a bounded,
auditable scope, and it is designed to fail safely and legibly when it hits something
outside that scope.

This document specifies **required behavior and properties**, independent of which
products, libraries, or vendors eventually implement them. Anywhere a prior research
document names a specific tool (OpenBot, LangChain, AppCAT, Strands, etc.), treat that as
one candidate way to satisfy a requirement below — never as the requirement itself.

**In scope**: the migration-orchestration system itself — assessment ingestion, plan
generation, execution, verification, integrity tracking, human approval, telemetry, and
optional observability attachment.

**Out of scope** (see §7): the specific migration domain knowledge content (what to do
about any given .NET API), procurement of LLM credentials, and any specific vendor
product's internal behavior.

---

## 2. Definitions

- **Target codebase**: the repository being migrated.
- **Assessment artifact ("audit")**: a structured, machine-readable description of the
  target codebase's migration-relevant state — what needs to change and why.
- **Knowledge source**: the swappable domain-knowledge component that interprets audit
  findings and supplies remediation instructions. Given as an MCP server per this
  project's founding premise — *how* that server is implemented is not specified here.
- **Plan**: a concrete, ordered (or partially ordered) set of phases generated for one
  run, derived from an audit artifact or a fallback default.
- **Phase**: one unit of plan execution — a scoped set of changes plus its verification.
- **Run**: one end-to-end execution of the system against a target codebase, from audit
  ingestion through completion or escalation.
- **Approval checkpoint**: the single required human decision point, occurring after
  plan generation and before any modification of the target codebase.
- **Escalation / friction report**: the structured output produced when the system
  cannot proceed within its authorized scope or retry budget.

---

## 3. Overall description

### 3.1 Operating modes

The system SHALL be operable in exactly one required mode and one optional mode:

- **Required — headless.** The entire lifecycle (audit ingestion → plan generation →
  approval → execution → verification → completion/escalation) SHALL function with no
  graphical or chat interface present. This is the baseline the system must always
  support.
- **Optional — attached observability/UI.** The system MAY additionally support
  attachment of a third-party conversational or observability interface. This mode is
  strictly additive (§6.5) — it never becomes a dependency for any required behavior.

### 3.2 Actors

- **The operator**: the human who runs the system and answers the approval checkpoint.
- **The coordinator**: the logical role that ingests the audit/plan and sequences
  execution. Does not itself modify the target codebase.
- **The implementer**: the logical role that makes the actual changes for one phase.
- **The verifier**: the logical role that independently confirms a phase's outcome by
  re-deriving evidence (e.g., a real build/test), never by trusting a self-report.

Whether these are three separate processes, three roles inside one process, or
something else is an implementation decision, not a requirement — the requirement is
the separation of responsibility and the verifier's independence (§6.2).

### 3.3 Assumptions and dependencies

- A knowledge source (MCP server) exists and is reachable, or the fallback default plan
  path (§6.1.3) is exercised instead.
- The target codebase is under version control, or can be placed under version control
  by the system before any modification (needed for §6.4's integrity tracking).
- At least one LLM provider credential is available (§6.6) — the system does not
  supply or select one on the operator's behalf.

---

## 4. Functional requirements

Grouped by area. Each requirement is independently testable and intentionally silent
on implementation.

### 4.1 Assessment ingestion (AUDIT)

- **AUDIT-1**: The system SHALL accept a structured assessment artifact describing the
  target codebase's migration-relevant findings.
- **AUDIT-2**: Each finding in the artifact SHALL carry, at minimum: a category, a
  severity, and a reference to the specific affected location(s) in the target
  codebase.
- **AUDIT-3**: The system SHALL support running with **no** assessment artifact
  present, by falling back to a default, generic plan (§4.2's PLAN-3).
- **AUDIT-4**: The mechanism that *produces* an assessment artifact (the audit engine)
  SHALL be replaceable independently of the rest of the system — the system consumes a
  defined artifact shape, not a specific producer.
- **AUDIT-5**: The system SHALL NOT assume the assessment artifact is complete or
  correct — findings are input to plan generation, not ground truth the system is
  forbidden from re-discovering problems outside of.

### 4.2 Plan generation (PLAN)

- **PLAN-1**: The system SHALL derive a concrete plan from the assessment artifact by
  grouping related findings into phases, rather than generating either one phase per
  individual finding (unless findings are genuinely independent) or one phase for the
  entire migration.
- **PLAN-2**: Grouping SHALL account for both category (findings of the same kind) and
  blast radius (findings that touch overlapping code should not be split across phases
  that could conflict).
- **PLAN-3**: When no assessment artifact is available, the system SHALL generate a
  default plan from a fixed, generic phase set, without requiring a structurally
  different code path from the audit-driven case.
- **PLAN-4**: The generated plan SHALL be represented in a durable, inspectable form
  before execution begins, sufficient to be the object of the approval checkpoint
  (§4.5).
- **PLAN-5**: Once approved, a plan's scope for a given run SHALL NOT silently change —
  any expansion of scope requires a new, explicit approval (§4.5's APPROVAL-4).

### 4.3 Execution model (EXEC)

- **EXEC-1**: The system SHALL execute the approved plan phase by phase, in the order
  (or partial order) the plan specifies.
- **EXEC-2**: The coordinator role SHALL NOT itself modify the target codebase — only
  the implementer role does, and only for the phase it's currently executing.
- **EXEC-3**: The system SHALL support a bounded retry policy per phase. Exceeding the
  bound SHALL trigger escalation (§4.7), never an unbounded retry loop.
- **EXEC-4**: A phase's implementation changes SHALL be individually attributable and
  reviewable, independent of other phases' changes (see INTEGRITY-2).
- **EXEC-5**: The system SHALL be able to run to completion, or to a defined escalation
  point, without further required human interaction after the approval checkpoint.

### 4.4 Verification (QA)

- **QA-1**: Every phase SHALL be independently verified by the verifier role before
  being considered complete.
- **QA-2**: Verification SHALL re-derive evidence directly (e.g., actually invoking the
  target ecosystem's real build/test toolchain against the phase's resulting state) —
  it SHALL NOT accept the implementer's own report of success as sufficient.
- **QA-3**: Verification results SHALL be reported as multiple, independently-named
  checks with individual outcomes, not as a single aggregate boolean.
- **QA-4**: The verifier role SHALL have no access to modify the target codebase, and
  no access to the knowledge source's remediation instructions — only to the phase's
  resulting state and the means to check it.
- **QA-5**: A verification failure SHALL be distinguishable, in its reporting, from a
  verification the system was unable to perform at all (e.g., due to an environment
  limitation) — "failed" and "not checked" are not the same outcome and must not be
  conflated.

### 4.5 Human approval (APPROVAL)

- **APPROVAL-1**: The system SHALL require exactly one consolidated human approval
  checkpoint per run, occurring after plan generation (§4.2) and before any
  modification of the target codebase.
- **APPROVAL-2**: The checkpoint SHALL present the complete generated plan, not a
  partial or summarized version that omits phases.
- **APPROVAL-3**: The checkpoint SHALL be answerable through the system's required
  headless mode (§3.1) at minimum — i.e., a plain command-line interaction is
  sufficient and must always be available, regardless of whether an optional UI is
  attached.
- **APPROVAL-4**: No modification of the target codebase beyond what was approved at
  the checkpoint SHALL occur without a new, explicit approval — this includes any
  mid-run scope expansion (e.g., a repair that would touch code outside the approved
  plan).
- **APPROVAL-5**: Once approved, the system SHALL NOT require further human
  interaction except at a defined escalation point (§4.7).

### 4.6 Integrity and change tracking (INTEGRITY)

- **INTEGRITY-1**: Before any modification, the system SHALL establish a baseline
  record of the target codebase's existing state, sufficient to later detect any
  change outside the approved plan's declared scope.
- **INTEGRITY-2**: Each phase's changes SHALL be recorded in a way that allows them to
  be individually inspected, and — at minimum — individually identified as belonging to
  that phase.
- **INTEGRITY-3**: After each phase, and at run completion, the system SHALL check
  actual changes against the approved plan's declared scope. Any change outside that
  scope SHALL be treated as an escalation condition (§4.7), not silently accepted or
  silently reverted.
- **INTEGRITY-4**: Paths that cannot be tracked by the system's primary
  change-tracking mechanism (e.g., paths intentionally excluded from version control,
  such as credential files) SHALL be covered by a narrowly-scoped supplementary
  mechanism — narrow enough that it does not become the primary mechanism by default.
- **INTEGRITY-5**: The system SHALL NOT read or expose the contents of credential-like
  files as part of integrity checking — presence and change detection only, never
  value inspection.

### 4.7 Escalation / friction handling (ESCALATE)

- **ESCALATE-1**: When the system cannot complete a phase within its bounded retry
  policy (EXEC-3), or encounters a condition outside its authorized scope (e.g., a
  pre-existing defect in code the current run was not asked to touch), it SHALL halt
  further unattended modification and produce a structured escalation report.
- **ESCALATE-2**: The escalation report SHALL classify the failure against a fixed,
  known taxonomy of categories (e.g., environment, credential, tooling gap, validation
  loop, scope conflict) rather than free-form prose only.
- **ESCALATE-3**: The escalation report SHALL exclude secrets, full source content, and
  raw logs beyond what is minimally necessary to act on the classification.
- **ESCALATE-4**: An escalation SHALL leave the target codebase in a state where every
  change made so far is individually attributable (per INTEGRITY-2), so a human can
  evaluate partial progress rather than facing an opaque failure.
- **ESCALATE-5**: The system SHALL NOT autonomously expand its approved scope to work
  around an escalation condition, even when a fix is plausible and small — resuming
  past an escalation requires a new explicit approval (APPROVAL-4).

### 4.8 Provider / model independence (PROVIDER)

- **PROVIDER-1**: The system SHALL support configuration-driven selection of the
  underlying language-model backend across multiple distinct providers — at minimum,
  spanning both enterprise-cloud-hosted platforms and direct model-vendor APIs —
  without requiring source-code modification to switch between them.
- **PROVIDER-2**: Adding support for an additional provider SHOULD require incremental
  configuration or adapter work, not a redesign of the coordinator/implementer/verifier
  logic.
- **PROVIDER-3**: The system SHALL NOT hardcode assumptions that only hold for one
  specific provider (e.g., a specific vendor's reasoning-effort parameter) into logic
  that is meant to be provider-agnostic; provider-specific behavior SHALL be isolated
  to the provider-selection layer.

### 4.9 Analytics and telemetry (TELEMETRY)

- **TELEMETRY-1**: The system SHALL emit a structured record of key lifecycle events
  sufficient to reconstruct a run's timeline and outcome after the fact — at minimum:
  phase start/end, approval checkpoint presented/resolved, verification outcome (per
  check, not aggregated), retry occurrences, escalation events, and run completion.
- **TELEMETRY-2**: This record SHALL use a closed, defined schema — not free-form
  logging — and SHALL exclude source code content, full file paths beyond what's
  needed for classification, prompts/model output content, and any credential-adjacent
  data.
- **TELEMETRY-3**: Recording SHALL be non-blocking: a failure to record an event SHALL
  NOT prevent the run from proceeding.
- **TELEMETRY-4**: The system SHALL function fully, including this record, without any
  external/third-party analytics service. Delivery of this data to an external or
  aggregated destination MAY be supported as a separate, optional, separately-gated
  capability, and SHALL respect a standard opt-out signal.

### 4.10 Execution environment (ENV)

- **ENV-1**: The system SHALL be able to execute real build and test operations
  against the target codebase's post-migration state, using the target ecosystem's
  actual toolchain, and treat the result as the authoritative verification evidence
  (QA-2).
- **ENV-2**: Where the *original*, pre-migration state cannot be built/validated within
  the system's execution environment (e.g., a platform mismatch between the legacy and
  modern toolchains), the system SHALL disclose this as a named, known limitation in
  its reporting — never silently omit that check without saying so.
- **ENV-3**: Any concrete version/target identifier the system migrates *to* (e.g.,
  which specific runtime version) SHALL be determined by configuration or at run time,
  not fixed permanently into the system's design — the system's own design must not
  become stale relative to the target ecosystem's release lifecycle.
- **ENV-4**: The execution environment SHOULD be portable to commodity infrastructure
  (e.g., standard Linux containers) except where the target ecosystem's own
  constraints genuinely require otherwise (per ENV-2) — such exceptions must be
  documented as such, not treated as the default expectation.

### 4.11 Optional UI / observability attachment (UIATTACH)

- **UIATTACH-1**: Any optional interface attachment (§3.1) SHALL be additive only —
  it SHALL NOT introduce a separate code path for core execution, approval enforcement,
  integrity tracking, or verification. The same underlying logic runs whether or not
  an interface is attached.
- **UIATTACH-2**: If an optional interface renders the approval checkpoint visually,
  that rendering SHALL represent the same underlying decision the headless approval
  path drives — not a second, independent gate.
- **UIATTACH-3**: The system SHALL NOT require any credential, network exposure, or
  infrastructure specific to an optional interface in order to run headlessly. Any
  such requirement (e.g., opening a local port for attachment) SHALL be scoped
  entirely to enabling that optional mode.
- **UIATTACH-4**: An attached interface MAY provide a supplementary audit/observability
  record of its own; this SHALL be treated as a bonus, secondary record, and never
  as a substitute for INTEGRITY-1 through INTEGRITY-5, which must hold regardless of
  attachment.

### 4.12 Knowledge source interface (KNOWLEDGE)

- **KNOWLEDGE-1**: Domain-specific migration knowledge (what remediation applies to a
  given category of finding, how to carry it out) SHALL be served from a component
  separate from the coordinator/implementer/verifier logic, exposed via MCP, per this
  project's founding premise.
- **KNOWLEDGE-2**: Updating or extending migration knowledge SHALL NOT require
  modifying or redeploying the coordinator/implementer/verifier logic.
- **KNOWLEDGE-3**: The system SHALL treat the knowledge source as swappable — a
  different knowledge source implementing the same interface SHALL be usable without
  code changes to the rest of the system.

---

## 5. Non-functional requirements

- **NFR-1 (Credential handling)**: The system SHALL never log, print, or transmit a
  full secret value; only presence/length/shape checks are permitted outside of the
  actual authenticated calls that need the secret. The system SHALL verify a
  secret-bearing file is excluded from version control before ever writing to it.
- **NFR-2 (Auditability)**: Every run SHALL produce a durable, human-readable record of
  what was done, sufficient for a person to reconstruct the run without access to the
  system's live process.
- **NFR-3 (Extensibility)**: Adding a new finding category, a new remediation template,
  or a new provider SHALL each be independently possible without a coordinated change
  across unrelated parts of the system.
- **NFR-4 (Idempotence/resumability)**: An interrupted run SHOULD be resumable from its
  last completed phase rather than requiring a full restart, where the target
  codebase's state allows it.
- **NFR-5 (Bounded resource use)**: Retry policies (EXEC-3), telemetry queuing
  (TELEMETRY-3), and any other unattended-operation mechanism SHALL be explicitly
  bounded — no mechanism in the system should be able to run or grow without limit.

---

## 6. Acceptance criteria (system-level)

The system SHALL be considered to satisfy this FRD when, for at least one real target
codebase:

1. Run without any prior assessment artifact and successfully generate and execute the
   default fallback plan (AUDIT-3, PLAN-3).
2. Run with a real assessment artifact and generate a plan whose phase grouping
   reflects both category and blast radius (PLAN-1, PLAN-2).
3. Halt at exactly one approval checkpoint, presented headlessly, and proceed
   unattended after approval (APPROVAL-1 through APPROVAL-5).
4. Detect a deliberately-introduced out-of-scope change during execution and escalate
   rather than silently continue (INTEGRITY-3, ESCALATE-1).
5. Produce a verification report with multiple independently-named, itemized outcomes
   for at least one phase (QA-3).
6. Produce a reconstructable telemetry record of the entire run, containing no source
   content or credentials (TELEMETRY-1, TELEMETRY-2).
7. Complete the same run twice using two different, independently-configured LLM
   providers, with no source-code change between the two runs (PROVIDER-1).
8. Run to completion with no optional interface attached, and separately, with one
   attached, without any difference in core behavior (UIATTACH-1 through UIATTACH-4).

---

## 7. Out of scope

- The specific content of .NET Framework → .NET Core migration knowledge (what to do
  about any given API or package) — this lives in the knowledge source, not this
  system's own logic, and is not specified here.
- Automatically remediating defects in code outside the approved plan's scope, even
  when a fix is small and plausible (see ESCALATE-5).
- Procuring, provisioning, or selecting LLM provider credentials on the operator's
  behalf.
- Guaranteeing pre-migration baseline validation across execution environments that
  cannot host the legacy toolchain (see ENV-2 — this is disclosed, not solved).
- Requiring or endorsing any specific vendor product (OpenBot, LangChain, Strands,
  AppCAT, or any other name appearing in `research/` or `IMPLEMENTATION-PLAN.md`) as
  part of this specification. Those remain candidate implementations, evaluated
  separately.

---

## 8. Future research items

Tool/library candidates and open questions to evaluate **against this FRD**, not
committed to. Carried forward from prior research (see `IMPLEMENTATION-PLAN.md`'s own
open-threads list for the earlier, more implementation-flavored version of several of
these) plus one new item:

1. **Strands Agents SDK (Apache 2.0, AWS-originated; reachable via `CopilotKit`'s fork
   of `strands-agents/harness-sdk`) — new, added 2026-09-18.** Its `multiagent`,
   `hooks`, `interventions`, `telemetry`, and `sandbox` modules, plus its
   `litellm`-backed model provider (which appears to satisfy PROVIDER-1's multi-cloud
   requirement without custom adapter code) and its official `ag_ui_strands` bridge for
   optional interface attachment, look like a plausible way to satisfy a substantial
   fraction of EXEC, PROVIDER, TELEMETRY, and UIATTACH in one dependency. **Not yet
   evaluated against this FRD's specific requirements** — in particular, whether its
   `sandbox/docker.py` can host the ENV-1/ENV-4 execution environment, whether its
   `interventions` module actually satisfies APPROVAL-1 through APPROVAL-5's exact
   shape, and whether its `telemetry` module's event schema meets TELEMETRY-2's privacy
   constraints as-is or needs wrapping.
2. Whether a generic open-source autonomous-coding-agent orchestration framework
   (OpenHands, SWE-agent, Aider) satisfies EXEC/QA better than a purpose-built loop —
   still open from Track A.
3. `aimock` (MIT) as a testing dependency for exercising ACCEPTANCE-1 through 8 without
   live provider costs — not a system requirement, but a development-process candidate.
4. `pathfinder`'s architecture (self-hosted, one-config-file MCP server) as a reference
   for satisfying KNOWLEDGE-1/2/3 — its Elastic License 2.0 terms mean it's a reference,
   not a dependency, for a system we'd distribute.
5. Whichever audit-engine implementation ends up satisfying AUDIT-1 through AUDIT-5 —
   `IMPLEMENTATION-PLAN.md`'s Decision 1 already ruled out AppCAT on license grounds and
   pointed toward a custom analyzer; `dotnet/try-convert` (MIT, archived) remains
   candidate reference material.
6. Whether the coordinator/implementer/verifier separation (§3.2) is best realized as
   three processes, three roles in one process, or a framework-provided pattern (e.g.
   Strands' `multiagent/graph.py`) — open until item 1 is evaluated.

---

## 9. Traceability to prior work

- `COPILOTKIT-ONBOARDING-JOURNAL.md` — the original reference pattern this whole
  project generalizes from (graph-as-nodes, one approval gate, proof-over-self-report,
  protected-path baseline) — most of §4's requirements trace directly to a specific
  principle documented there.
- `research/A-prior-art.md` through `research/G-trust-layer-reconciliation.md` — the
  evidence base; several FRD requirements exist specifically because a research track
  found a real gap (e.g., ESCALATE-4/5 trace to Track A's postmortem on GitHub Copilot
  upgrade's own route-out rules; ENV-2/ENV-3 trace to Track B's Linux/EOL findings).
- `IMPLEMENTATION-PLAN.md` — one candidate realization of this FRD, using specific
  tools (OpenBot as the optional UIATTACH implementation, a custom analyzer for AUDIT,
  git for INTEGRITY, a LangChain-based provider switch for PROVIDER). Should be
  re-validated against this FRD's numbered requirements before further build-out,
  particularly now that §8 item 1 (Strands) could change which requirements are
  satisfied "for free" versus hand-built.
