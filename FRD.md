# Functional Requirements Document — Agentic Control Plane (InstallGraph)

**Status**: draft, **rightsized 2026-09-18** following an independent staff-engineer design review of the 2026-09-18 enterprise-hardening amendment.
**Supersedes prior documents as the primary spec.**

**What changed in the rightsizing pass** (details in §11): every requirement now carries a priority tag — **[v1]**, **[v2]**, or **[won't-do]**. The pre-review document had 63 untagged `SHALL`s of uniform normative weight, which meant it could not answer "what are we building first." It now has **29 v1 requirement IDs** (28 governing a run, plus PROCESS-1 governing this project's own codebase; `EXEC-10` promoted from v2 on 2026-09-19 — see §13), several of which absorb two or three former IDs verbatim. Requirements the review identified as aimed at an implausible adversary, or as speculative generality, were cut or demoted and the reasoning is recorded inline so they do not get silently re-promoted. Requirements the review identified as load-bearing but *missing* — verifier isolation mechanism, deterministic verdict derivation, run branch, delta-vs-baseline evaluation, local diagnostics, data-disclosure policy, gate rejection path — were added.

---

## 1. Purpose and scope

InstallGraph is an **Agentic Control Plane** that autonomously carries out structured, multi-phase code migrations and engineering tasks against a target codebase with as little required human interaction as the risk of the work allows.

It is explicitly **not** a fully unsupervised system: it is designed around one human decision point before any write, after which it operates unattended within a bounded, auditable scope, and it is designed to fail safely and legibly when it hits something outside that scope.

**Domain agnosticism — claimed, not yet earned.** The control plane is *intended* to be domain-agnostic: it enforces governance, state management, and execution safety, while domain knowledge (e.g., upgrading a .NET Framework codebase to .NET Core, the first reference implementation) is injected by a swappable knowledge pack. The review correctly noted that this boundary is being drawn from zero implemented domains and is already leaking (INTEGRITY-8's side-effect class, ENV-1's toolchain provisioning, PLAN-2's blast-radius grouping are all domain concerns sitting in or pressing on the core). **Disposition: build the .NET path concretely; extract the control plane when a second domain forces the seam.** The naming is retained because it describes the intent, not a validated property. See §10.5.

**In scope**: the execution control plane itself — assessment ingestion, plan generation, execution, verification, integrity tracking, human approval, diagnostics, and (v2) telemetry and optional observability attachment.

**Out of scope**: see §7.

**Explicit limit of this document:** satisfying every requirement in §4 makes failures bounded, legible, and verifiable. It does not, and cannot, guarantee that the code a run produces is correct, well-designed, or fit for the target codebase's actual business purpose — that remains subject to human review. This document governs process integrity, not code judgment.

## 2. Definitions

- **Agentic Control Plane**: the domain-agnostic execution harness that enforces the state machine, git-native baselines, and proof-over-self-report guardrails.
- **Target codebase**: the repository being modified.
- **Assessment artifact ("audit")**: a structured, machine-readable JSON description of the target codebase's task-relevant state — what needs to change and why.
- **Knowledge source (pack)**: the swappable domain-knowledge component that interprets audit findings and supplies remediation node templates.
- **Plan**: a concrete, ordered set of phases generated (or authored) for one run.
- **Phase**: one unit of plan execution — a scoped set of changes plus its verification.
- **Declared scope**: the explicit set of path globs a phase is permitted to modify, fixed at the approval checkpoint.
- **Check set**: the explicit, ordered list of verification commands for a phase (command + working directory + expected machine-readable result artifact), fixed at the approval checkpoint.
- **Side-effect class**: a phase's declared reversibility category — `file-only`, `package-manager-mutating`, or `external-service-call`.
- **Baseline commit**: the commit of the target codebase captured immediately before any modification.
- **Run branch**: the dedicated git branch, created from the baseline commit, on which all of a run's writes occur.
- **Baseline check results**: the result of executing the full check set against the baseline commit, *before* the approval checkpoint. All later verdicts are deltas against this.
- **Run**: one end-to-end execution of the system against a target codebase.
- **Approval checkpoint**: the required human decision point, occurring after plan generation and before any modification of the target codebase.

## 3. Overall description

### 3.1 Operating modes
- **Required – headless.** The entire lifecycle SHALL function with no graphical or chat interface present.
- **Optional – attached observability/UI (v2).** The system MAY additionally support attachment of a third-party conversational or observability interface (additive only).

### 3.2 Actors and the honest state of role separation

- **The operator**: the human who runs the system and answers the approval checkpoint.
- **The coordinator**: the logical role that ingests the audit/plan and sequences execution.
- **The implementer**: the logical role that makes the actual changes for one phase.
- **The verifier**: the logical role that confirms a phase's outcome by re-deriving evidence.

**Coordinator and implementer are roles, not security boundaries, in v1; the verifier is now a partial exception.** The coordinator and implementer still run in one process, against one working copy, with one shell — EXEC-2 states what is actually true and enforceable for that pair, a configuration constraint (SHALL NOT be instructed to), not a capability boundary. `research/G-trust-layer-reconciliation.md` already said this in plain language: *"there is a seam by construction."* The verifier is different as of 2026-09-19: EXEC-10 (promoted to v1) gives it a genuinely independent working directory — a second `git worktree` the implementer's process never touches — so a verifier that tried to write into the implementer's checkout physically couldn't reach it. That closes the seam for the verifier specifically; it does not touch the coordinator/implementer pair, which remains a configuration constraint backstopped by INTEGRITY-3's after-the-fact scope diff.

What *does* close the seam in v1 is not role separation: it is INTEGRITY-3 (post-phase diff against declared scope, fail closed) operating on a dedicated run branch (INTEGRITY-9). That is the load-bearing control. Everything else in the integrity family supports it.

---

## 4. Functional requirements

Every requirement carries one of:

- **[v1]** — in scope for the first working system. 29 IDs.
- **[v2]** — deferred. Real, not abandoned; revisit when the named trigger condition is met.
- **[won't-do]** — deliberately rejected, with the reason recorded so it stays rejected.

Retired IDs are listed in place with their disposition rather than deleted, so that a later reader (or a later session) can see that the absence was a decision.

**v1 index** (29): AUDIT-1 · PLAN-1 · PLAN-5 · EXEC-1 · EXEC-2 · EXEC-3 · EXEC-6 · EXEC-7 · EXEC-10 · QA-1 · QA-2 · QA-5 · APPROVAL-1 · APPROVAL-5 · INTEGRITY-1 · INTEGRITY-2 · INTEGRITY-3 · INTEGRITY-8 · INTEGRITY-9 · ESCALATE-1 · ESCALATE-2 · DIAG-1 · SECRET-1 · DISCLOSE-1 · ENV-1 · BUDGET-1 · BUDGET-2 · TEST-1 · PROCESS-1

*(PROCESS-1 governs the control plane's own codebase rather than a run, and so is excluded from the run-level acceptance criteria in §6; the runtime v1 set is the other 28. The review's estimate was ~15 v1 requirements. This lands at 29 because most of these IDs now carry what 63 carried before — AUDIT-1 alone absorbs three former requirements, PLAN-1 absorbs three, EXEC-6 absorbs four — plus one genuine promotion: EXEC-10 moved from v2 to v1 on 2026-09-19 after the Phase B spike showed it costs far less than estimated. The cost-weighted v1 surface is smaller than the count suggests; padding was resisted, merging was not.)*

### 4.1 Assessment ingestion (AUDIT)

- **AUDIT-1** **[v1]** — The system SHALL accept a structured assessment artifact describing the target codebase's task-relevant findings. Each finding SHALL carry, at minimum: a category, a severity, and one or more affected paths. The system SHALL NOT assume the artifact is complete or correct: a finding whose affected paths do not resolve against the baseline commit SHALL be dropped from plan generation and recorded as a `FINDING_DISCARDED` event (EXEC-6), never silently skipped and never guessed at.
  *Absorbs former AUDIT-2 (field contract) and AUDIT-5 (don't trust the audit), which were separate statements of one input contract.*

- **AUDIT-2** — *merged into AUDIT-1.*

- **AUDIT-3** — *merged into PLAN-1* (running without an audit is a plan-source question, not an ingestion question).

- **AUDIT-4** **[v2]** — The mechanism that *produces* an assessment artifact SHOULD be replaceable independently of the rest of the system. *Deferred: there is one producer. The seam is preserved by AUDIT-1 being a file contract rather than an API call, which costs nothing.*

- **AUDIT-5** — *merged into AUDIT-1.*

- **AUDIT-6** **[v2]** — Assessment artifacts and plans SHALL declare a semver schema version; the system SHALL refuse to run against an unsupported major version rather than coerce. *Deferred: one producer and one consumer, authored together, versioned by the same git commit. Trigger to promote: a pack authored outside this repo, or the first backwards-incompatible schema change after a real run has been archived.*

### 4.2 Plan generation (PLAN)

- **PLAN-1** **[v1]** — A run SHALL execute from a plan that is (a) derived from an assessment artifact by grouping related findings into phases, **or** (b) authored directly by the operator as a plan file. Both paths SHALL produce the same on-disk plan representation. The plan SHALL be written in a durable, inspectable form and committed to the run branch (INTEGRITY-9) as that branch's first commit, before execution begins. That commit SHALL contain only control-plane artifacts (the plan and the event log) under a dedicated run directory, and SHALL modify no pre-existing file — it is therefore not a modification of the target codebase for the purposes of APPROVAL-1.
  *Absorbs former AUDIT-3 and PLAN-3 (fallback/no-audit path) and PLAN-4 (durable representation). Path (b) is also the vertical-slice path: it lets the whole governance spine be built and tested before any audit engine or LLM exists.*

- **PLAN-2** **[v2]** — Grouping SHOULD account for blast radius (findings that touch overlapping code), not only category. *Deferred and flagged: blast-radius grouping requires understanding project and dependency structure, which is domain knowledge, yet PLAN-2 sits in the domain-agnostic core. This is the clearest instance of the abstraction leak noted in §1. Before promoting it, decide whether grouping belongs in the pack. v1 groups by category and declared path overlap only — a purely lexical operation the core can honestly perform.*

- **PLAN-3** — *merged into PLAN-1.*

- **PLAN-4** — *merged into PLAN-1.*

- **PLAN-5** **[v1]** — Each phase in the plan SHALL declare, before approval: its **declared scope** (path globs it may modify), its **check set** (QA-1), and its **side-effect class** (INTEGRITY-8). Once approved, none of these SHALL change for that run. Any change requires a new approval checkpoint (APPROVAL-1). In particular, an executing phase SHALL NOT be able to alter its own or any other phase's check set — the check set is an input to execution, never an output of it.
  *Absorbs former PLAN-5 (scope doesn't silently change), former PLAN-6, and former APPROVAL-4. The final sentence closes the attack surface the review identified: without it, "verification" is chosen by the thing being verified.*

### 4.3 Execution model (EXEC)

- **EXEC-1** **[v1]** — The system SHALL execute the approved plan phase by phase, and SHALL be able to run to completion unattended after the approval checkpoint, halting only under ESCALATE-1 or BUDGET-2.
  *Absorbs former EXEC-5.*

- **EXEC-2** **[v1]** — The coordinator and verifier roles **SHALL NOT be instructed to modify the target codebase**, and the control plane SHALL NOT expose file-write or code-editing tools to them. This is a *configuration* constraint, not a capability boundary: in the v1 single-process topology the underlying shell is shared and a determined or confused model could write through it. Detection of such a write is INTEGRITY-3's job, not this requirement's. Restating this honestly is deliberate — see §3.2.
  *Absorbs former QA-4, whose phrasing ("SHALL have no access to modify") asserted enforcement that no mechanism in this document or the implementation plan provides.*

- **EXEC-3** **[v1]** — The system SHALL enforce a bounded retry budget per phase. Exhausting it SHALL halt and escalate (ESCALATE-1), never continue.

- **EXEC-4** — *merged into INTEGRITY-2* (both stated "individually attributable").

- **EXEC-5** — *merged into EXEC-1.*

- **EXEC-6** **[v1]** — Execution state SHALL be persisted as an append-only JSONL event log using a fixed enum of event types (`RUN_STARTED`, `BASELINE_CAPTURED`, `PLAN_GENERATED`, `FINDING_DISCARDED`, `GATE_PRESENTED`, `GATE_APPROVED`, `GATE_REJECTED`, `PHASE_STARTED`, `CHECK_RESULT`, `SCOPE_VIOLATION_DETECTED`, `PHASE_COMMITTED`, `BUDGET_EXCEEDED`, `ESCALATED`, `RUN_COMPLETED`, `RUN_ABANDONED`). The log SHALL be the **sole source of truth** for run state: any derived or cached state SHALL be fully reconstructible from it by replay, and SHALL never be the thing that is trusted when the two disagree. The log SHALL be committed into the run branch (INTEGRITY-9) at each `PHASE_COMMITTED`. Each run's events SHALL record the plan's content hash and, when a knowledge pack is active, the pack's immutable identity (commit SHA or content hash); each `PHASE_COMMITTED` SHALL record cumulative token and cost usage for the run.
  *Rewritten from the absolutist original ("state SHALL be derived solely by replaying this log — SHALL NOT maintain a separate status field"), which forbade even a cached projection and would have been violated in week two. Committing the log into the run branch replaces INTEGRITY-7's hash chain: git objects are already content-addressed and chained, so this deletes a requirement instead of adding one. Absorbs former BUDGET-4 and the surviving half of former KNOWLEDGE-4.*

- **EXEC-7** **[v1]** — The system SHALL hold an exclusive lock keyed to run id for the duration of a run, and SHALL refuse to start a second process against the same run. On startup, if the event log shows a run that is neither `RUN_COMPLETED`, `RUN_ABANDONED`, nor `ESCALATED`, the system SHALL **halt and emit a resume report** — describing the last committed phase, the run branch head, and any uncommitted working-tree state — rather than automatically resuming or resetting. Resuming is an operator decision in v1.
  *Absorbs former EXEC-8. Downgraded from the original automatic replay-and-reset because of the finding recorded under INTEGRITY-8: automatic baseline-reset retry is only sound for `file-only` phases, which in the reference domain are the minority. Automatic resumption that covers only the phases that don't matter is not worth its test matrix in v1.*

- **EXEC-8** — *merged into EXEC-7.*

- **EXEC-9** **[v2]** — On restart, the system MAY automatically resume from the last safe event boundary, resetting the target codebase to the phase's pre-attempt baseline where INTEGRITY-8 permits, with the re-attempt counted against the phase's retry budget. *Trigger to promote: evidence from real runs that mid-phase crashes are frequent enough to be worth automating, and a resolution for `package-manager-mutating` phases better than "escalate to the operator."*

- **EXEC-10** **[v1, promoted 2026-09-19]** — The verifier SHALL execute against an independent checkout of the run branch that the implementer cannot write to (a separate working directory at minimum), making EXEC-2 a real capability boundary for the verifier specifically, rather than only a configuration constraint. *This is the honest mechanism for what former QA-4 merely asserted.*
  *Promoted via the Phase B "B3" spike: a second `git worktree`, checked out by raw commit SHA (detached, never by branch name) so it never collides with the implementer's branch checkout, turned out to be genuinely cheap — implemented directly in `controlplane/runner.py`/`gitops.py` (`add_worktree`/`remove_worktree`), covering every check execution including the baseline run. Locked down by `controlplane/tests/test_verifier_worktree.py`, including the specific guarantee that an uncommitted implementer edit is invisible from the verifier's worktree, and that deleting the run branch never conflicts with the detached verifier checkout. This was ~15 lines of real change, not the "probably 30 lines" §8 item 2 estimated — cheaper than expected because git worktrees already provide exactly this primitive. The original v2 rationale (v1's adversary is a confused model, not a malicious one, and INTEGRITY-3 already detects the failure after the fact) still stands as the reason this wasn't blocking — it's promoted because it turned out to cost near nothing, not because the threat model changed.*

### 4.4 Verification (QA)

- **QA-1** **[v1]** — Every phase SHALL be verified by executing its approved check set (PLAN-5). Results SHALL be reported as multiple, independently named checks. A check that could not be executed at all (missing toolchain, unavailable environment) SHALL be reported as `not-run` with the reason, and `not-run` SHALL NOT be treated as a pass anywhere in the system.
  *Absorbs former QA-3 (multi-check reporting) and former ENV-2 (limitations disclosed, never silently skipped) — the latter is only meaningful as a property of how checks report, which is here.*

- **QA-2** **[v1]** — A check's pass/fail verdict SHALL be derived deterministically by the control plane from the check process's **exit code** and, where the check produces one, its **machine-readable result artifact** (e.g., TRX, JUnit XML, SARIF). A language model SHALL NOT author, adjust, or summarize a verdict. A model MAY be used to *explain* a failure and to *propose* a remediation, and its output SHALL be recorded as commentary, clearly distinguished from the verdict. The check set itself is fixed at approval (PLAN-5) and is never selected at verification time.
  *This is the entire substance of "proof over self-report," and it was not in the pre-review document. The original QA-2 ("SHALL re-derive evidence directly... SHALL NOT accept self-reports") moved the self-report one agent to the left: the verifier was itself a model summarizing a build log.*

- **QA-3** — *merged into QA-1.*

- **QA-4** — *merged into EXEC-2 (honest restatement) and EXEC-10 (the mechanism — promoted to v1 2026-09-19).*

- **QA-5** **[v1]** — Before the approval checkpoint, the system SHALL execute the full check set against the baseline commit and record the result as the run's **baseline check results**. All subsequent phase verdicts SHALL be evaluated as a **delta** against that baseline: a check that was already failing at baseline and still fails identically SHALL NOT by itself fail a phase; a check that was passing at baseline and now fails SHALL fail the phase. A check that changes from failing to passing SHALL be recorded as an improvement, not as a fault. The baseline check results SHALL be presented at the approval checkpoint (APPROVAL-1).
  *Legacy enterprise repositories routinely do not build clean on day one. Absolute green/red evaluation would halt on phase one of every real repository the system is pointed at. This is a v1 requirement because without it the system cannot run against its own reference domain.*

### 4.5 Human approval (APPROVAL)

- **APPROVAL-1** **[v1]** — The system SHALL require human approval **before the first write to the target codebase**, answerable through the required headless mode (CLI), and SHALL require no further approval for the remainder of the run except where it escalates (ESCALATE-1). The checkpoint SHALL present: the complete generated plan; each phase's declared scope, check set, and side-effect class (PLAN-5); the baseline check results (QA-5); the findings of the pre-run secret scan (SECRET-1); a summary of what will be disclosed to the third-party model provider (DISCLOSE-1); and the plan and knowledge-pack content hashes (EXEC-6).
  *Restated from "exactly one consolidated human approval checkpoint per run," which was a product claim dressed as a safety property: INTEGRITY-3 escalations mean there will be many human interactions, just unplanned ones. What the system actually guarantees is "no writes before approval, and no scheduled interruptions after it." Absorbs former APPROVAL-2 (what is presented) and APPROVAL-3 (headless-answerable).*

- **APPROVAL-2** — *merged into APPROVAL-1.*
- **APPROVAL-3** — *merged into APPROVAL-1.*
- **APPROVAL-4** — *merged into PLAN-5.*

- **APPROVAL-5** **[v1]** — The approval checkpoint SHALL be **accept-all-or-abort**. The operator SHALL have exactly two responses: approve the plan as presented, or reject it. On rejection the system SHALL emit `GATE_REJECTED`, make no modification to the target codebase, restore the checkout to the baseline commit, delete the run branch (which at that point holds only PLAN-1's control-plane commit and no phase commits, so INTEGRITY-9's no-delete rule does not apply), and exit non-zero. Partial approval SHALL be achieved by the operator editing the plan file and re-running, which produces a new plan hash and a new approval checkpoint — not by an interactive subset-selection flow.
  *A deliberate product decision, chosen over in-gate editing because an editable gate makes "what was approved" ambiguous, and PLAN-5's freeze depends on that being unambiguous. `CLAUDE.md` previously referenced an APPROVAL-5 that did not exist in any version of this document; this is it.*

### 4.6 Integrity and change tracking (INTEGRITY)

- **INTEGRITY-1** **[v1]** — Before any modification, the system SHALL record a baseline commit identifying the target codebase's exact starting state, and SHALL emit `BASELINE_CAPTURED`. If the working tree is not clean at that moment, the system SHALL halt and escalate rather than stash, commit, or discard the operator's uncommitted work.

- **INTEGRITY-2** **[v1]** — Each phase's changes SHALL be recorded as exactly one commit on the run branch, so that every change is individually attributable, reviewable, revertable, and cherry-pickable.
  *Absorbs former EXEC-4 and the surviving intent of former ESCALATE-4.*

- **INTEGRITY-3** **[v1]** — After each phase, the diff between the phase's parent commit and its result SHALL be checked against that phase's declared scope (PLAN-5). Any modified path outside the declared scope SHALL emit `SCOPE_VIOLATION_DETECTED` and halt the run (ESCALATE-1). Fail closed: if the check itself cannot be performed, that is a halt, not a pass.
  *This is the single load-bearing integrity control in the system and the only thing closing the seam described in §3.2 and in `research/G-trust-layer-reconciliation.md`. If exactly one requirement from this document is implemented, it is this one.*

- **INTEGRITY-4** **[v2]** — Paths git cannot see (gitignored, credential-adjacent) SHOULD be covered by a narrowly scoped supplementary hash check. *Deferred: INTEGRITY-3 covers everything tracked, and SECRET-1 plus DISCLOSE-1 cover the credential case by policy in v1. Trigger to promote: a real run where a gitignored file was modified and it mattered.*

- **INTEGRITY-5** — *merged into DISCLOSE-1.* The original ("SHALL NOT read or expose the contents of credential files") directly contradicted the reference domain: migrating `web.config` and `appsettings.json` is core work, and those are exactly where .NET secrets live. The workable rule is about what leaves the machine, not about what is read, and it belongs with the disclosure policy.

- **INTEGRITY-6** — *merged into SECRET-1.*

- **INTEGRITY-7** **[won't-do]** — *Hash-chained tamper-evident event log.* Rejected on threat-model grounds (§5). The only writer of the log is the same process, as the same user, on the same box, holding everything needed to recompute the whole chain; a self-chained log detects accidental truncation and naive hand-edits, not the adversary "tamper-evident" implies. Real tamper-evidence costs *less*: EXEC-6 commits the log into the run branch, where git's own content-addressed, parent-chained objects provide it for free. This requirement is recorded as rejected, with its reason, so it is not reintroduced as an oversight.

- **INTEGRITY-8** **[v1]** — Every phase SHALL declare a side-effect class: `file-only`, `package-manager-mutating`, or `external-service-call`. Only `file-only` phases are eligible for any automatic baseline-reset retry. For the other two classes, a failed phase SHALL halt and escalate, and the escalation report SHALL include a **compensating-action section** naming, per class, what the operator must do by hand before re-running (for `package-manager-mutating`: the lockfile/manifest paths touched, the package-manager restore or cache commands to re-run, and whether a global cache was mutated; for `external-service-call`: the calls made, with idempotency noted per call). This manual path is a **first-class, documented outcome**, not a fallthrough.
  *The original stated the restriction but not the consequence. In the reference domain (.NET Framework → .NET Core) the substantive phases — package upgrades, SDK retargeting — are `package-manager-mutating` by definition, so the manual compensating path is the **common** case, not the exception, and the spec must treat it that way. This is also why EXEC-9 is v2: automatic resumption covers approximately the phases that don't matter.*

- **INTEGRITY-9** **[v1]** — All modification of the target codebase SHALL occur on a dedicated **run branch** created from the baseline commit and named deterministically from the run id. The system SHALL NOT commit to, rebase, merge into, or force-update any pre-existing branch, and SHALL NOT push. On escalation the run branch SHALL be left intact with all phase commits on it, and the escalation report SHALL state the branch name, the baseline commit, and the two operator options — keep the branch for inspection/cherry-pick, or abandon it — together with the exact command that abandons it. Abandonment SHALL emit `RUN_ABANDONED`. Cleanup is the operator's decision; the system SHALL never delete a run branch that contains **phase** commits without an explicit operator action. (The sole exception is gate rejection, where the branch holds only PLAN-1's control-plane commit — see APPROVAL-5.)
  *The cheapest, highest-value integrity requirement available, and it was entirely absent: INTEGRITY-1/2 implied commits but never said where. It also supplies whole-run abandon for free, which was likewise missing — the pre-review document left N commits sitting somewhere after escalation with nothing saying who cleans up.*

### 4.7 Escalation / friction handling (ESCALATE)

- **ESCALATE-1** **[v1]** — On an unrecoverable error, exhausted retry budget (EXEC-3), exceeded budget (BUDGET-2), or detected scope violation (INTEGRITY-3), the system SHALL halt all unattended modification, emit `ESCALATED`, and produce a structured escalation report.

- **ESCALATE-2** **[v1]** — The escalation report SHALL classify the failure against a fixed, closed taxonomy (`environment`, `credential`, `tooling-gap`, `validation-loop`, `scope-conflict`, `budget-exceeded`, `side-effect-uncompensated`, `internal-error`), and SHALL contain: the failing phase, the check-level results (QA-1), the run branch and baseline commit (INTEGRITY-9), the compensating-action section where INTEGRITY-8 requires one, and a pointer to the local diagnostic log (DIAG-1). It SHALL NOT contain secrets or full source content.
  *Absorbs former ESCALATE-3. The pointer to DIAG-1 is what makes the exclusion survivable — see §4.9.*

- **ESCALATE-3** — *merged into ESCALATE-2.*
- **ESCALATE-4** — *merged into INTEGRITY-2 and INTEGRITY-9.*

### 4.8 Provider / model independence (PROVIDER)

- **PROVIDER-1** **[v2]** — The system SHALL support configuration-driven selection of the underlying language-model backend. *Demoted from v1 acceptance. Transport-level provider swapping is a commodity (`research/E-llm-provider-backend.md` found LiteLLM does it); what is not portable is behavior — tool-calling reliability, long-context instruction adherence, and "only touch these files" compliance vary enormously by model, and INTEGRITY-3's violation rate will differ per provider accordingly. v1 ships on one model. The core SHALL still depend on a single `ModelProvider` interface rather than importing a vendor SDK throughout, because that seam costs nothing and BUDGET-1 enforces its ceilings there; that is a design note, not a requirement with a test.*

- **PROVIDER-2** **[v2]** — Adding a provider SHOULD require incremental configuration, not a redesign. *Meaningless to verify until PROVIDER-1 is promoted.*

- **PROVIDER-3** **[won't-do]** — *Uniform dependency inversion across `ModelProvider`, `TelemetrySink`, and `RunStore`.* The `ModelProvider` seam survives as a design note under PROVIDER-1. `TelemetrySink` is moot while §4.9 is v2. `RunStore` is rejected with STORAGE-1/2.

### 4.9 Diagnostics and telemetry (DIAG, TELEMETRY)

Split deliberately. The pre-review document constrained telemetry so tightly for privacy that it could no longer explain a failure, and then provided no alternative — leaving `CHECK_FAILED, taxonomy=validation-loop` as the entire diagnostic surface for a phase that failed at 3am on run 40.

- **DIAG-1** **[v1]** — The system SHALL write a verbose local diagnostic log per run, containing whatever is needed to debug it: full command lines, full stdout/stderr of check and implementer commands, model request/response metadata, timing, and retry decisions. This log SHALL be local-only and SHALL NOT be exported, transmitted, or included in any telemetry pipeline or escalation report; escalation reports reference it by path (ESCALATE-2). It SHALL be written under a gitignored run directory and SHALL NOT be committed to the run branch. Its retention SHALL be operator-controlled.

- **TELEMETRY-1** **[v2]** — Emit a structured record of key lifecycle events to an external sink. *Deferred: there are zero telemetry consumers. EXEC-6's event log already records every lifecycle event locally and is strictly more useful today. Trigger to promote: an actual consumer — a dashboard, a usage question someone is paying to answer, or a second operator.*
- **TELEMETRY-2** **[v2]** — Closed schema, excludes PII and code. *Rides with TELEMETRY-1.*
- **TELEMETRY-3** **[v2]** — Non-blocking emission. *Rides with TELEMETRY-1.*
- **TELEMETRY-4** **[won't-do]** — *Emission-time JSON Schema validation, malformed events raising an ESCALATE-class error.* Rejected: it makes a telemetry defect capable of halting a migration run, which inverts the priority between the work and the instrumentation about the work. If TELEMETRY-1 is promoted, validate in tests and drop malformed events with a DIAG-1 line.
- **TELEMETRY-5** **[won't-do]** — *Enum-only fields, no free text.* Rejected: this is the requirement that made the system undebuggable. Privacy is satisfied by DIAG-1 being local-only and by the telemetry payload being an explicit allowlist of fields; it does not require banning free text a priori from a pipeline that does not exist.

### 4.10 Execution environment (ENV)

- **ENV-1** **[v1]** — The system SHALL be able to execute real build and test operations for the active domain on the operator's machine, and SHALL verify the required toolchain is present before the approval checkpoint, reporting any missing toolchain as a `not-run` check (QA-1) at the baseline stage (QA-5) rather than discovering it mid-run.

- **ENV-2** — *merged into QA-1.*

- **ENV-3** **[won't-do, for this domain's build/verify step specifically]** — Sandboxing the *verifier's build/check execution* inside a container is rejected for the .NET reference domain, not deferred pending a spike. Resolved 2026-09-18 without the Windows-container spike §8 originally called for, on the strength of two pieces of evidence: (1) the stretch-goal target `alloy-mvc-template` is a genuine legacy-format project (`ToolsVersion="4.0"`, non-SDK MSBuild XML, `packages.config`, heavy `System.Web.*` references) — it requires real `MSBuild.exe`, a Windows-only toolchain that Linux containers cannot run and that the operator explicitly ruled Windows containers out for (multi-GB, Hyper-V, not worth it); (2) the operator confirmed that even the *migrated* .NET Core side of this org's real workflow builds locally and only containerizes the already-built output for deployment — never compiles inside the container. Sandboxed build execution isn't just hard here, it doesn't match how this domain is actually built on either side of the migration. **This SHALL be revisited per-domain, not globally**, if a future knowledge pack targets a toolchain that is genuinely container-native — the rejection is about this domain's toolchain, not a claim that build sandboxing is never worthwhile. The Mono/Linux-container path was deliberately not empirically tested (the operator chose to defer that spike rather than spend the time); if harder evidence is ever wanted, that spike is still available. For v1 the isolation story stays INTEGRITY-9's dedicated run branch plus INTEGRITY-3's scope check, against a repository the operator already trusts, on the operator's own box.
  *See ENV-5 for the part of the original ENV-3 that this split off and kept alive: sandboxing the implementer specifically, which has no toolchain dependency and remains a live v2 candidate.*

- **ENV-4** **[v2]** — Network egress from the execution environment SHOULD default to denied with an explicit allowlist. This now presupposes **ENV-5's** implementer container (ENV-3's build/verify step is unsandboxed on the host by design and is not a candidate for egress control).
  **One known blocker, unchanged:** `nuget.org` is allowlistable; private Azure Artifacts / Artifactory feeds are not, without credentials — and those credentials live in `NuGet.config`, precisely the kind of file INTEGRITY-5 forbade reading. Nothing in v1 covers authenticated private package feeds, and that is a hard blocker for any real .NET enterprise codebase (§10.6) — this is unaffected by ENV-3's resolution, since package restore happens during the unsandboxed host build either way. Trigger to promote: ENV-5 built, and an authenticated-private-feed story that works.

- **ENV-5** **[v2]** — Implementer code execution (file edits and git operations within a phase's declared scope) MAY occur in an ephemeral, isolated Linux container, independent of where verification executes (ENV-3). No domain toolchain is required inside it — the implementer never runs `dotnet build` or `MSBuild.exe` itself; the verifier does that, on the host, against the commit the implementer produced. This is why ENV-5 is not blocked by the same wall ENV-3 hit: it was never contingent on legacy MSBuild running anywhere but the host.
  *Split off from the original ENV-3 on 2026-09-18. Genuinely low-cost relative to the original: no toolchain provisioning, no Windows-vs-Linux question, just git + a file-editing agent in a container. Trigger to promote: same as EXEC-10's threat model (§5a), but with the blocker that stalled the original ENV-3 removed — this is now mostly a matter of prioritization, not feasibility.*

### 4.11 Optional UI / observability attachment (UIATTACH)

- **UIATTACH-1** **[v2]** — Any optional interface attachment SHALL be additive only.
- **UIATTACH-2** **[v2]** — Visual renderings of approval checkpoints SHALL represent the identical underlying headless state machine.
  *Both deferred wholesale: the headless CLI path is the enforceable core and must exist and work first. Neither is abandoned; the constraint they encode (the UI never becomes load-bearing) is already honored by building headless-first.*

### 4.12 Knowledge source interface (KNOWLEDGE)

- **KNOWLEDGE-1** **[v2]** — Domain-specific knowledge SHALL be served from a separate component via MCP.
  **Open question the document never asked: what does MCP buy here?** MCP exposes tools and resources to a *model at inference time*. What the pack is actually being asked to do is (a) run a static analyzer, (b) serve prompt templates, (c) declare side-effect classes, and (d) possibly ship executable code. That is a versioned package with a documented schema — `npx my-pack audit --json` plus a directory of templates — not a conversational tool server. Choosing MCP adds a server process, a lifecycle, a handshake, and a supply-chain surface to solve a problem a package already solves. **v1 decision: the knowledge pack is a local, versioned directory (a CLI that emits the AUDIT-1 artifact, plus template files), identified by content hash in the event log (EXEC-6).** Trigger to promote MCP: a concrete, written-down case where the *implementer model* needs to call pack tools live, mid-phase, with arguments not known at plan time. If that case never materializes, MCP is not needed at all.

- **KNOWLEDGE-2** **[v2]** — Updating domain knowledge SHALL NOT require modifying the control plane. *Literally untestable until a second pack exists from a second domain. Kept as a design intention; see §1 on the unearned domain-agnosticism claim.*
- **KNOWLEDGE-3** **[v2]** — The knowledge source SHALL be treated as swappable. *Rides with KNOWLEDGE-2.*
- **KNOWLEDGE-4** — *split.* The provenance half (record the pack's immutable content hash in the event log) is **[v1]**, merged into EXEC-6 — one line, real reproducibility value. The allowlist / signing-key / operator-opt-in / pack-sandboxing half is **[won't-do]**: it is a supply-chain trust model for an ecosystem of exactly one pack, authored by the same person who wrote the control plane. Revisit if and when a second pack exists from a second author.

### 4.13 Storage (STORAGE)

- **STORAGE-1** **[won't-do]** — *Abstract `RunStore` interface selectable by configuration.*
- **STORAGE-2** **[won't-do]** — *Swappable SQLite / Postgres / flat-file backends.*
  *Rejected as speculative generality for a single-user CLI tool. **Decision: run state is JSONL files under a per-run directory, plus the run branch itself** (EXEC-6). "Swappable backend" as a requirement means owing three adapters and three test matrices for a need that does not exist. If a seam is ever wanted, it is one module with a narrow function signature — a refactor, not a requirement.*

### 4.14 Secret handling and third-party disclosure (SECRET, DISCLOSE)

- **PROMPT-1** **[won't-do]** — *Regex/entropy secret-detection filter masking all outbound LLM content.*
- **PROMPT-2** **[won't-do]** — *Prompt ruleset must be a superset of the telemetry ruleset.*
  *Rejected as written. Regex/entropy detection over arbitrary source has a high false-negative rate on exactly what matters (connection strings in `web.config`, hardcoded keys, base64 blobs) and false-positives on GUIDs, signing-key blobs, resource files, and test fixtures. False positives are worse than they look: masking corrupts the input the implementer is reasoning about, and nothing required the masking to be reversible or masked regions to be excluded from edit targets. Worst of all it manufactures a compliance claim — "secrets never reach the provider" — that cannot be substantiated and would not survive a real security review. Replaced by SECRET-1 + DISCLOSE-1.*

- **SECRET-1** **[v1]** — Before the approval checkpoint, the system SHALL run a secret scan over the baseline commit (an external scanner is acceptable and preferred) and SHALL present its findings at the checkpoint (APPROVAL-1). It SHALL additionally verify that known credential-shaped paths (`.env`, `*.pfx`, `*.p12`, cloud credential files) are excluded from version control, and SHALL present any that are not as a finding of the same kind. **The operator SHALL be required to acknowledge these findings explicitly before approval is accepted.** The system SHALL NOT claim to remove, mask, or neutralize secrets, and SHALL NOT silently proceed past findings.
  *Absorbs former INTEGRITY-6. The scan is advisory-with-forced-acknowledgment, which is a claim that can actually be honored, rather than a filter, which is a claim that cannot.*

- **DISCLOSE-1** **[v1]** — The system SHALL state, and the approval checkpoint SHALL summarize, its third-party data-disclosure policy:
  - **What is sent to the model provider**: the contents of files within the active phase's declared scope, the plan and phase description, the assessment findings for that phase, and check output excerpts on failure.
  - **What is never sent**: any file outside the active phase's declared scope; the contents of the diagnostic log (DIAG-1); any file matching the credential-path patterns of SECRET-1, even if it is inside a declared scope — such a file SHALL cause the phase to halt and escalate rather than be sent, since a phase that must edit a credential file is a phase a human should do.
  - **What the operator is responsible for**: confirming the target repository is eligible for third-party disclosure under their own organization's policy; confirming the provider account's data-retention and training-use terms (zero-retention where required) before configuring it; and **not running this system against a repository containing live secrets** — SECRET-1 surfaces them, it does not make them safe.
  *Absorbs former INTEGRITY-5 in a form that does not contradict the reference domain's core work. For a document whose hardening rationale was "enterprise," the absence of any third-party disclosure statement was a more serious omission than an unhashed local log file.*

### 4.15 Hermetic testing (TEST)

- **TEST-1** **[v1]** — The control plane's own test suite SHALL execute with zero live network calls to any model provider, knowledge pack, or telemetry sink, and SHALL include a deterministic mock model provider supporting scripted response sequences, malformed/truncated payloads, and injected timeouts.
  *Absorbs former TEST-2. Not ceremony: it is the only way to iterate without burning tokens, and it is needed in week one regardless.*

- **TEST-2** — *merged into TEST-1.*

- **TEST-3** **[v2]** — Fixtures for malformed or schema-invalid assessment/plan artifacts. *Partially covered in v1 by AUDIT-1's unresolvable-path handling, which does need a test. The full malformed-artifact matrix rides with AUDIT-6.*

- **TEST-4** **[v2, rescoped]** — Fault-injection tests that terminate the process and assert correct behavior on restart — **at three boundaries only** (before `PHASE_STARTED`, mid-phase with uncommitted writes, after `PHASE_COMMITTED`), not at every event-type boundary. *Rides with EXEC-9; under v1's EXEC-7 the assertion is simply "halts with a correct resume report," which is one test, not a combinatorial harness.*

### 4.16 Cost and time governance (BUDGET)

- **BUDGET-1** **[v1]** — The system SHALL enforce a hard wall-clock timeout per phase and per run, and a hard token/request ceiling per phase and per run. The token ceiling SHALL be enforced by the provider wrapper itself, never relied upon from the model's own behavior.
- **BUDGET-2** **[v1]** — Exceeding any budget SHALL emit `BUDGET_EXCEEDED` and be treated identically to exhausting a retry budget: halt and escalate (ESCALATE-1), never continue silently.
  *Absorbs former BUDGET-3. Together these are the cheapest high-value requirements in the document — they are what stops a $400 overnight runaway, and they are an afternoon's work.*
- **BUDGET-3** — *merged into BUDGET-2.*
- **BUDGET-4** — *merged into EXEC-6* (cumulative token/cost recorded in the event log; no telemetry pipeline needed to hold it).

### 4.17 Engineering process for the control plane itself (PROCESS)

- **PROCESS-1** **[v1]** — The control plane's own codebase SHALL pass strict type-checking and linting in CI before merge, and no change to the state-machine, integrity-check, approval-gate, or verdict-derivation code paths SHALL merge without the full TEST-1 hermetic suite passing.
  *Absorbs former PROCESS-2, minus its "and a human review" clause: on a solo project that clause is a no-op — the author approving their own pull request — and stating an unenforceable control alongside enforceable ones devalues both. If a second contributor joins, restore it.*

- **PROCESS-2** — *merged into PROCESS-1.*

---

## 5. Threat model

The pre-review document asserted controls without naming an adversary, and consequently spent its most expensive requirements on its least plausible one. This section exists so that the cuts in §4 stay cut for a stated reason.

**Three distinct adversaries were conflated:**

**(a) A sloppy or confused LLM agent — the only real v1 threat.** The implementer edits files outside its scope, "helpfully" reformats the repository, deletes a test it cannot make pass, claims a build succeeded that did not, loops on a fix for forty minutes, or burns $400 of tokens overnight. This is not hypothetical; it is the expected, normal behavior of the system's central component. Controls: **INTEGRITY-3** (scope diff, fail closed), **INTEGRITY-9** (run branch — the blast radius never leaves it), **INTEGRITY-2** (commit-per-phase — every change attributable and revertable), **QA-2** (verdicts from exit codes, so "it works" cannot be asserted), **QA-5** (delta evaluation, so the agent cannot be blamed for pre-existing red), **EXEC-3** and **BUDGET-1/2** (bounded time, retries, money), **ESCALATE-1/2** (halt legibly). Note that all of these are v1 and all are cheap. That is the intended shape.

**(b) A compromised or malicious knowledge pack — not a v1 threat.** There is exactly one pack, in this repository, authored by the same person as the control plane, loaded from local disk. There is no distribution channel to compromise. Controls retained: the pack's content hash is recorded per run (EXEC-6), which is one line and gives reproducibility. Controls rejected: KNOWLEDGE-4's allowlist, signing keys, and operator opt-in; ENV-5's pack sandboxing (this line predates ENV-3's 2026-09-18 split — the pack-sandboxing question was always closer to ENV-5's implementer-isolation shape than to ENV-3's build-toolchain question). Promote when a pack exists that this project's author did not write.

**(c) A malicious operator forging their own audit trail — not a threat at all, here.** The operator owns the machine, the repository, the log file, the git history, and the process. There is no second party to whom the log is evidence, no compliance regime consuming it, and no privileged-separation boundary anywhere in the design. INTEGRITY-7's hash chain was aimed squarely at this adversary and would not have stopped them in any case, since they hold everything needed to recompute the chain. **This was the single largest misallocation in the pre-review document**: the most expensive new controls defended against the least plausible adversary, while the controls for (a) — deterministic verdicts, run branch, delta evaluation — were missing entirely.

**Not in the model at all for v1**: multi-tenant use, untrusted target repositories, network attackers, and supply-chain attacks on the control plane's own dependencies. Each of those, if it becomes real, promotes a specific deferred requirement (**ENV-5**, ENV-4, KNOWLEDGE-4's rejected half) rather than requiring a redesign. Note this is `ENV-5`, not `ENV-3` — `ENV-3` (build/verify sandboxing) is won't-do *for this domain's toolchain specifically*, and an untrusted-repo scenario doesn't change what toolchain MSBuild requires; it would promote implementer isolation (`ENV-5`) and, separately, argue for `EXEC-10`'s verifier separation, not resurrect `ENV-3`.

---

## 6. Acceptance criteria (v1)

The v1 system SHALL be considered to satisfy this FRD when, against one real target codebase (the .NET reference), all of the following hold:

1. **Baseline and branch.** The system captures a baseline commit, refuses to proceed on a dirty working tree, creates a dedicated run branch from the baseline, and never writes to any pre-existing branch. (INTEGRITY-1, INTEGRITY-9)
2. **Plan from either source.** It produces the same plan representation from an assessment artifact and from an operator-authored plan file, with per-phase declared scope, check set, and side-effect class present in both. (AUDIT-1, PLAN-1, PLAN-5)
3. **Baseline checks run first.** The full check set executes against the baseline commit *before* the approval checkpoint, and repos that do not build clean are handled as deltas rather than halting the run. (QA-5, ENV-1)
4. **One gate, with real contents.** A single headless checkpoint presents the plan, per-phase scope and checks, baseline check results, secret-scan findings requiring acknowledgment, and the disclosure summary — before any write. (APPROVAL-1, SECRET-1, DISCLOSE-1)
5. **Rejection is clean.** Rejecting the gate leaves the target codebase byte-identical, deletes the run branch, emits `GATE_REJECTED`, and exits non-zero. (APPROVAL-5)
6. **Deterministic verdicts.** A phase whose build fails is failed by the control plane on exit code and machine-readable test output, with no model involved in the verdict, and this is demonstrated by a test in which the mock model asserts success while the check exits non-zero. (QA-1, QA-2, TEST-1)
7. **Scope violation is caught and fails closed.** An intentionally out-of-scope write during a phase produces `SCOPE_VIOLATION_DETECTED`, halts the run, and yields an escalation report naming the run branch, baseline, and taxonomy code. (INTEGRITY-3, ESCALATE-1, ESCALATE-2)
8. **Commit per phase.** Each completed phase is exactly one commit on the run branch, individually revertable and cherry-pickable. (INTEGRITY-2)
9. **Budgets halt.** A configured wall-clock or token budget exceeded mid-run emits `BUDGET_EXCEEDED` and escalates rather than continuing. (BUDGET-1, BUDGET-2)
10. **Side effects are handled as a first-class path.** A failed `package-manager-mutating` phase escalates with a populated compensating-action section rather than attempting an automatic reset. (INTEGRITY-8)
11. **Crash is legible.** A forced kill mid-phase, followed by restart, produces a resume report naming the last committed phase and the uncommitted state, and refuses to advance the run automatically; a second concurrent process is refused by the lock. (EXEC-6, EXEC-7)
12. **Debuggable.** For any escalation above, the local diagnostic log contains the full command lines and output needed to explain it, and nothing from that log appears in the escalation report. (DIAG-1, ESCALATE-2)
13. **Hermetic.** The full test suite passes with zero live network calls. (TEST-1)
14. **Traceable.** Every **v1-tagged** requirement ID has at least one mapped test, per §9.
15. **Verifier isolation.** Every check executes in an independent working directory the implementer's edits never reach directly; an uncommitted implementer edit is invisible from it, and it advances only on an explicit checkout to a specific commit. (EXEC-10)

*Removed from the pre-review criteria:* "operates successfully via two distinct LLM providers" (vacuous — satisfiable by a hello-world completion, and provider-agnosticism is now v2, see PROVIDER-1); "runs headlessly and separately via UI with identical behavior" (UIATTACH is v2); "generates telemetry without secrets" (TELEMETRY is v2; DIAG-1 and criterion 12 carry the real need).

---

## 7. Out of scope

This section was cross-referenced from §1 in every prior version of this document and never written. It now exists.

Explicitly out of scope for this FRD, at any version:

1. **Domain knowledge content.** What to do about any given framework API, package, or language feature. That lives in a knowledge pack (§4.12), not here.
2. **Correctness or fitness of generated code.** See the limit stated in §1. This document governs process integrity only.
3. **Procurement of model-provider credentials**, their billing, and their contractual terms. DISCLOSE-1 places the responsibility for reviewing retention/training terms on the operator; it does not select or obtain a provider.
4. **Any specific vendor product's internal behavior.** No requirement in §4 is satisfiable only by a named product. Where a product is mentioned (OpenBot, Strands, LiteLLM) it is a candidate realization, evaluated in `IMPLEMENTATION-PLAN.md` or `research/`, never a requirement.
5. **Multi-user, multi-tenant, or hosted operation.** Single operator, single machine, single run at a time (EXEC-7). This assumption is load-bearing for the threat model in §5 and must be revisited wholesale if it changes, not patched requirement by requirement.
6. **Post-run integration.** Opening pull requests, pushing branches, CI/CD integration, deployment. The system's output is a run branch and a report (INTEGRITY-9); what happens to that branch is the operator's workflow.
7. **Repository acquisition and setup.** Cloning, submodule initialization, LFS hydration, dependency pre-restore, and machine provisioning are preconditions the operator meets before a run. (See §10.1 — the *detection* of unmet preconditions is in scope and currently unresolved.)

---

## 8. Open technical questions requiring a spike, not a requirement

Each item below is something the pre-review document asserted past. Each should be answered with code, in an afternoon, before any requirement is written about it.

1. ~~Does the .NET Framework toolchain function under any container isolation at all?~~ **Resolved 2026-09-18 without a hands-on spike.** ENV-3 is now won't-do for this domain's build/verify step (see ENV-3's own entry for the evidence: the stretch-goal target's confirmed legacy csproj format, and the operator's confirmation that even the migrated .NET Core side builds on the host and only containerizes the output). Windows containers were ruled out directly by the operator, not tested. The Mono/Linux-container path was reasoned through, not empirically run — that spike remains available if firmer evidence is ever wanted, but was explicitly deferred. **Replacement spike:** stand up a plain Linux container (no .NET toolchain) that can check out the run branch, apply a scripted edit, and commit — i.e. prove ENV-5's implementer-only isolation is viable. This is a materially easier spike than the one it replaces, since it was never blocked by MSBuild in the first place.
2. ~~Can the verifier be given an independent, non-writable view of the run branch cheaply?~~ **Resolved 2026-09-19, confirmed.** A second `git worktree`, checked out by raw commit SHA (never by branch name, so it can't collide with the implementer's branch checkout), took ~15 lines in `gitops.py`/`runner.py`. `EXEC-10` promoted to v1; see its own entry and §13.
3. **What does a real legacy repository's baseline check actually look like?** (QA-5). Green, red, or mixed; how long; how stable across re-runs. This determines whether delta evaluation is sufficient or needs a flakiness allowance.
4. **Does audit → phase grouping produce phases a human would accept?** (PLAN-1, PLAN-2). Until a real audit is grouped and eyeballed, the grouping requirements are unfalsifiable.
5. **Authenticated private package feeds** (ENV-4, §10.6). What does the system need to do to let a phase restore from an Azure Artifacts feed without reading or exfiltrating credentials? Currently unanswered, and a hard blocker for any real enterprise .NET codebase.
6. **Strands Agents SDK (Apache 2.0)** — carried forward from the prior version. Evaluate whether its `multiagent`, `hooks`, `sandbox`, and `interventions` modules cover EXEC-*, BUDGET-*, and the v2 PROVIDER/TELEMETRY families natively. **Note the sequencing change**: this evaluation is now *lower* priority than items 1–4, because the requirements it would most affect (ENV-3/4, TELEMETRY-*, PROVIDER-*) are all v2 or won't-do after the rightsizing. Adopting a framework to satisfy deferred requirements is precisely the inversion this pass was meant to correct.

---

## 9. Traceability

**Two distinct linkages, both required, neither enum-heavy.**

### 9.1 Requirement → test (enforced)

A single checked-in table (`traceability.md`, or a table in this file once tests exist) SHALL map each **v1-tagged** requirement ID to the test(s) that exercise it. A CI script SHALL fail the build if a **v1-tagged** requirement ID has zero mapped tests.

**The gate is scoped to v1 deliberately.** The pre-review version required every ID in §4 to have a mapped test, which would have been red against 60+ unimplemented requirements from the first commit, guaranteeing an immediate blanket exemption list — the exact silent gap the mechanism exists to prevent. Scoped to the 29 v1 IDs, the gate is red only while v1 is genuinely incomplete, which is information rather than noise. When a requirement is promoted from v2 to v1, the gate turns red until it has a test; that is the promotion cost, and it is the point — `EXEC-10`'s 2026-09-19 promotion is the first live example: it shipped with `controlplane/tests/test_verifier_worktree.py` in the same change, not after.

### 9.2 Requirement → rationale (the more valuable half)

Each requirement in §4 carries, inline, *why it exists*: a research finding, a review finding, or a stated decision. This linkage was present in the original §9 and was overwritten by the hardening amendment; the review correctly identified it as the more valuable of the two. It is restored in a more durable form — written next to each requirement rather than in a separate section that can drift out of sync.

The principal rationale sources, for a reader tracing any requirement backwards:

- **`research/G-trust-layer-reconciliation.md`** → INTEGRITY-1/2/3/9, EXEC-2, §3.2. The git-native integrity mechanism, and the admission that there is a seam by construction in the standalone design.
- **`research/A-prior-art.md`** → INTEGRITY-2, INTEGRITY-9. Branch-per-run, commit-per-task, reviewable via `git log`/`cherry-pick`, as validated by GitHub Copilot's upgrade agent.
- **`research/E-llm-provider-backend.md`** → PROVIDER-1's demotion. Transport-level swapping is a solved commodity; behavioral portability is not, and is what actually matters.
- **`research/F-audit-to-graph-design.md`** → AUDIT-1, PLAN-1, PLAN-2.
- **`COPILOTKIT-ONBOARDING-JOURNAL.md`** → EXEC-1, ESCALATE-1/2, INTEGRITY-4's deferral (the protected-path hash store this project decided *not* to reimplement).
- **The 2026-09-18 independent design review** → QA-2, QA-5, EXEC-2, EXEC-10, INTEGRITY-8's follow-through, INTEGRITY-9, APPROVAL-5, DIAG-1, SECRET-1, DISCLOSE-1, §5, §7, §10, and every `[won't-do]` disposition.

### 9.3 What traceability does not buy

It does not guarantee the *content* a run produces is correct or fit for business purpose — see §1. It guarantees that every governance rule this document states as v1 is either checked automatically or visibly unchecked.

---

## 10. Known open issues

Surfaced by the 2026-09-18 review and **not resolved in this pass**, deliberately. These are recorded here so they are visible as open rather than silently absent. Each is expected to be forced into resolution by the vertical slice, which is the correct order: they are all questions about what real repositories actually do, and the repo currently contains no code with which to find out.

1. **Pre-existing repository state.** Dirty working tree is handled (INTEGRITY-1 halts). Everything else is not: submodules, LFS, existing branch name collisions with the run branch, and — most urgently — **git hooks**. A `husky`/`pre-commit` hook that reformats on commit will rewrite files across the tree and trip INTEGRITY-3 on every single phase. That is a guaranteed false-positive source in any modern repository, and nothing in §4 addresses it. Likely resolutions to evaluate: run all commits with `--no-verify`, or detect hooks pre-run and require operator acknowledgment. **Pick one during the slice, then write the requirement.**
2. **Context-window management.** How does an implementer operate on a 500-project solution that does not fit in any context window — file selection, chunking, summarization, cross-file coherence? BUDGET-1 caps tokens without saying how the work fits inside them. This is plausibly the hardest technical problem in the system and there is no requirement ID for it. It is deliberately not being specified from an armchair; it needs the slice plus one real repository first.
3. **Mid-run human intervention.** EXEC-1 says "unattended," and for the first fifty runs the operator will want to pause, inspect, and steer constantly. Nothing specifies what that looks like. INTEGRITY-9's run branch at least makes ad-hoc inspection safe (`git log` on another terminal), which is why this is tolerable as open rather than blocking.
4. **Audit idempotency.** Can the assessment be re-run mid-run, after the tree has changed? Undefined. v1's PLAN-5 freeze makes it moot *within* a run; the question returns the moment re-planning is wanted.
5. **Whether the domain-agnostic boundary is in the right place.** §1 states the claim is unearned. The concrete test is the second domain, and there is no second domain. Until then, resist moving anything into "the core" for generality reasons alone.
6. **Authenticated private package feeds.** Real enterprise .NET repositories restore from Azure Artifacts or Artifactory, with credentials in `NuGet.config`. v1 has no story for this beyond "it happens to work because the operator's machine is already authenticated" — which is probably true on the operator's own box and definitely false anywhere else. Also see ENV-4.
7. **Flaky checks.** QA-5 evaluates deltas but assumes a check's baseline result is stable. Real test suites are not. Re-run policy, quarantine lists, and flakiness tolerance are unspecified; see §8 item 3.

---

## 11. Revision note — 2026-09-18 rightsizing

This document was amended on 2026-09-18 with an enterprise SDLC hardening pass that converted a 14-item gap analysis into 14 formal requirement families in a single sitting — a 100% conversion rate, with no gap receiving the dispositions "acknowledged risk, not addressed in v1," "needs a spike first," or "won't do — wrong threat model." An independent staff-engineer design review of the result was accepted in full. This revision implements it.

**What was cut and why (summary; details inline in §4):**

| Cut | Disposition | Reason |
|---|---|---|
| INTEGRITY-7 (hash-chained log) | won't-do | Wrong adversary (§5c); git objects already provide it via EXEC-6 |
| STORAGE-1/2 (pluggable backends) | won't-do | Speculative generality; decided: JSONL + run branch |
| KNOWLEDGE-4 allowlist/signing | won't-do | Supply-chain model for an ecosystem of one pack, one author |
| TELEMETRY-4/5 (schema validation, enum-only) | won't-do | Made the system undebuggable; inverted priority between work and instrumentation |
| PROMPT-1/2 (outbound secret masking) | won't-do | Unsubstantiable compliance claim; corrupts implementer input |
| PROVIDER-3 (uniform DI) | won't-do | The only seam that mattered survives as a design note |
| PROVIDER-1/2 (multi-provider) | v2 | Behavioral portability is the hard part and is untested; dropped from acceptance |
| ENV-3/4 (sandbox, egress deny) | v2 + ⚠ | Contradicts the .NET Framework reference domain; contradiction now documented in place |
| TELEMETRY-1/2/3 | v2 | Zero consumers; EXEC-6's local log is strictly more useful today |
| UIATTACH-1/2, KNOWLEDGE-1/2/3 | v2 | Headless core first; the MCP choice itself is now an open question |
| AUDIT-4/6, PLAN-2, INTEGRITY-4, TEST-3/4, EXEC-9 | v2 | Real, deferred, each with a named promotion trigger |
| ~18 IDs | merged | Duplicate statements of one contract, now single requirements with clauses |

**What was added, because it was missing and load-bearing:** EXEC-10 (verifier isolation mechanism), QA-2 (deterministic verdict derivation), QA-5 (delta-vs-baseline evaluation), INTEGRITY-9 (run branch + abandon path), APPROVAL-5 (rejection path), DIAG-1 (local diagnostics), SECRET-1 (scan + acknowledgment), DISCLOSE-1 (third-party disclosure policy), INTEGRITY-8's compensating-action follow-through, §5 (threat model), §7 (out of scope — cross-referenced since the first version, never written), §10 (known open issues).

**The forcing function this document was missing is not more review — it is a build directory.** The next work on this project is the vertical slice described in §8 items 1–4, not another amendment to §4. Requirements added to this document before that slice runs should be treated with suspicion by default.

## 12. Revision note — 2026-09-18 ENV-3 resolution (post-Phase-A)

Phase A (the vertical slice) was built and passed the same day as the rightsizing above. Immediately after, the operator corrected the framing behind §8 item 1 before Phase B started: the reason build/verify execution was always intended to run in a terminal, not a sandbox, is to use the real MSBuild already installed on the operator's machine — and confirmed that even the migrated .NET Core side of this org's actual workflow builds locally and only containerizes the finished output, never compiles inside the container. Windows containers were ruled out directly. A quick read of the stretch-goal target (`C:\Code\_sandbox\Opti11\alloy-mvc-template`)'s actual `.csproj` confirmed it is genuine legacy-format MSBuild (non-SDK XML, `packages.config`, heavy `System.Web.*`), which only real `MSBuild.exe` can build.

This resolved §8 item 1 without the spike it called for, and — more importantly — showed that the original ENV-3 was asking one question about two different things with two different answers. **ENV-3 is now split**: the verifier's build/check execution is won't-do for sandboxing in this domain, by design, not by limitation (documented in place so it cannot be silently re-promoted); the implementer's file-editing/git execution has no such blocker and continues as **ENV-5**, a plain v2 candidate. EXEC-10 (worktree-based verifier separation) is elevated as the nearer-term, toolchain-independent mechanism, since it doesn't depend on either half of ENV-3's split landing first. The empirical question of whether Mono/Linux-hosted MSBuild could ever build a project like this was deliberately not spiked — the operator chose to defer that specific investment rather than spend the time confirming what the evidence already strongly implied.

## 13. Revision note — 2026-09-19 EXEC-10 promoted (Phase B, "B3")

Immediately after §12's resolution, Phase B's reframed B3 (elevated to go first, since it doesn't depend on either half of the ENV-3 split) was spiked directly against Phase A's existing `controlplane/` code rather than as a standalone throwaway: `gitops.add_worktree`/`remove_worktree` wrap `git worktree add --detach` / `git worktree remove --force`, and `Runner._run_check_set` now checks the verifier's worktree out to whatever commit the implementer last produced before every check execution — baseline included. Total change: ~15 lines across `gitops.py` and `runner.py`, well under the "probably 30 lines" §8 item 2 estimated.

**EXEC-10 is promoted to v1** as a result — not because the threat model changed (§5a's disposition, "cheap and all v1," still describes why this wasn't blocking), but because the promotion cost turned out to be close to zero. `§3.2` is amended to state the verifier's separation as real rather than a v2 aspiration; the coordinator/implementer pair is unaffected and remains a configuration constraint. A new test file, `controlplane/tests/test_verifier_worktree.py`, locks down the actual guarantee — not just that the pipeline still runs, but that an uncommitted implementer edit is invisible from the verifier's worktree, and that deleting the run branch never conflicts with the detached verifier checkout — and shipped in the same change as the promotion, per §9's rule that a promotion's test debt is due immediately, not eventually.

Full end-to-end re-verification after this change: 15/15 hermetic tests pass; a live run against `fixtures/sample-dotnet-app` reproduces the same happy-path-then-escalation behavior as before, with `diagnostics.log` now showing the verifier worktree being created once and re-checked-out at each of baseline, phase-1, and phase-2, and removed on both the escalation exit path and the rejection exit path.

v1 count: **29** (was 28). `IMPLEMENTATION-PLAN.md` Phase B's B3 marked done; B1 (`ENV-5` spike) and B2 (private feeds) remain open.
