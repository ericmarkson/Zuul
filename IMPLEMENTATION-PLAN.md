# Agentic Control Plane — Implementation Plan

> **Repositioned 2026-09-18: this is a candidate realization of `FRD.md`.**
> **Re-sequenced 2026-09-18 (rightsizing pass)** after the independent design review of `FRD.md`.
> Every phase below is now tagged against the FRD's **v1 / v2** split. The single largest change
> is that a **vertical slice (Phase A) now comes before everything else**, including before the
> reference knowledge pack, and deliberately contains **no LLM at all**. The review's central
> finding was that ~200 lines of code would have falsified or confirmed more of the spec than
> three sessions of writing it did. Phase A is those ~200 lines.

## Decisions this plan needs from the user
1. **Target repository to validate against**: does a real .NET Framework codebase exist to run
   this against end-to-end, or should a synthetic/sample repo be built? **Phase A needs this
   (or a small stand-in) and nothing else does** — it is now the first blocking decision, not
   the last.
2. **LLM provider(s) actually in hand**: which of Azure AI / Vertex / Anthropic / OpenAI is
   actually credentialed right now? **No longer urgent**: FRD `PROVIDER-1` is v2, v1 ships on
   one model, and Phases A and B need no model at all.
3. **OpenBot deployment posture**: moot for now — FRD `UIATTACH-*` is v2. Run from a clean
   clone if and when the optional UI path is picked up.

---

## Phase A — Vertical slice (no LLM) — **NEW, and first**
**Goal**: prove the governance spine end-to-end against a real repository, with a hand-written
plan and a scripted "implementer" that just applies a known edit. Answers with code what the FRD
currently asserts.

Covers FRD v1: `PLAN-1` (operator-authored plan path), `PLAN-5`, `INTEGRITY-1`, `INTEGRITY-2`,
`INTEGRITY-3`, `INTEGRITY-9`, `QA-1`, `QA-2`, `QA-5`, `APPROVAL-1`, `APPROVAL-5`, `ESCALATE-1`,
`ESCALATE-2`, `EXEC-6`, `DIAG-1`.

- **Task 1**: Read a hand-written `plan.json` — phases, each with declared scope globs, a check
  set (command + expected result artifact), and a side-effect class.
- **Task 2**: Capture the baseline commit, refuse a dirty tree, create the run branch from it.
- **Task 3**: Run the check set against the baseline and record baseline check results (`QA-5`).
  **This is the experiment that answers FRD §8 item 3** — what a real legacy repo's baseline
  actually looks like.
- **Task 4**: Present the CLI approval gate (plan + scope + checks + baseline results); accept or
  abort, nothing else.
- **Task 5**: Apply each phase via a scripted edit; commit per phase; `git diff` the result
  against the declared scope; escalate on violation.
- **Task 6**: Re-run the check set, derive verdicts from exit codes and TRX/JUnit output only,
  evaluate as a delta against baseline.
- **Task 7**: Append every step to a JSONL event log committed into the run branch; write a
  verbose diagnostic log to a gitignored run directory.
- **Exit criteria**: `FRD.md` §6 acceptance criteria 1, 2, 3, 4, 5, 7, 8, 12 pass with a scripted
  implementer and no model in the loop. Criterion 6's determinism test passes with a stub that
  *claims* success while the build exits non-zero.
- **Explicitly answers**: FRD §8 items 2 (`git worktree` verifier isolation — try it here, it is
  probably 30 lines), 3 (baseline reality), and §10.1 (git hooks — find out immediately whether
  a `pre-commit` hook trips `INTEGRITY-3`).

## Phase B — Spikes that unblock deferred requirements
**Goal**: answer the questions the FRD currently documents as contradictions rather than
resolving.

**⚠ B1 changed on 2026-09-18, after Phase A shipped, before this phase started.** The original
B1 (build .NET Framework inside a Windows container) is retired without being run: the operator
ruled out Windows containers directly, and confirmed that build/verify execution is meant to use
the real MSBuild already installed on the operator's machine — which even the migrated .NET Core
side of this org's real workflow does too (build locally, containerize only the finished output).
A quick read of the stretch-goal target's actual `.csproj` confirmed it is genuine legacy-format
MSBuild, which only real `MSBuild.exe` can build. FRD `ENV-3` is now **won't-do for this domain's
build/verify step**, documented in place; see `FRD.md` §12 for the full resolution and the new
`ENV-5` (implementer-only sandboxing, no toolchain blocker). The Mono/Linux-hosted-MSBuild
question was deliberately not spiked — deferred by the operator's own call, not answered by code.

- **B1 (reframed)**: spike `ENV-5` instead — stand up a plain Linux container (no .NET toolchain
  at all) that can check out the run branch, apply a scripted edit, and commit. This is a much
  easier spike than the one it replaces, since it was never blocked by MSBuild.
- **B2**: Restore from an authenticated private feed (Azure Artifacts / Artifactory) and
  determine what the control plane must do with `NuGet.config` credentials. (FRD `ENV-4`, §10.6.)
  Unaffected by B1's change — package restore happens during the unsandboxed host build either way.
- **B3 (elevated — do this one first)**: Second `git worktree` as a read-only verifier view (FRD
  `EXEC-10`). With build/verify staying host-executed by design, this is now the cheapest real
  implementer/verifier separation available, and doesn't depend on B1 landing first.
- **Exit criteria**: written answers appended to `logs/session-log.md` for B1(reframed), B2, and
  B3, each either promoting a v2 requirement, confirming its deferral, or converting it to won't-do.

## Phase C — Reference knowledge pack (.NET) — *was Phase 1*
**Goal**: the first domain-specific knowledge source: an audit that emits an `AUDIT-1`-compliant
findings file, plus a catalogue of parameterized node templates.

Covers FRD v1: `AUDIT-1`, `PLAN-1` (audit-derived path), and the v1 half of `KNOWLEDGE-4`
(content hash recorded).

- **Task 1**: Minimal custom static analyzer for .NET targeting detection.
- **Task 2**: Findings schema — category, severity, affected paths, remediation tag. This JSON
  file is the contract between pack and control plane.
- **Task 3**: Node-template catalogue as plain versioned files (e.g.
  `retarget-sdk-style-project`, `upgrade-incompatible-package`), each declaring a side-effect
  class per `INTEGRITY-8`.
- **⚠ Changed from the original plan**: **this is a local versioned directory plus a CLI, not an
  MCP server.** See FRD `KNOWLEDGE-1` — MCP is now v2 and gated on a written-down case where the
  *implementer model* must call pack tools live, mid-phase. Building the pack as a package first
  costs nothing and keeps that option open.
- **Exit criteria**: the pack emits a compliant findings file against a real .NET repo, and
  Phase A's plan loader consumes it unchanged.

## Phase D — Audit → plan generation — *was Phase 2*
**Goal**: turn any findings file into a concrete plan of the same shape Phase A already executes.

Covers FRD v1: `PLAN-1`. **Grouping is category + declared-path overlap only** — lexical
operations the domain-agnostic core can honestly perform. Blast-radius grouping (`PLAN-2`) is v2
and flagged in the FRD as the clearest instance of the domain-abstraction leak; do not implement
it in the core without deciding first whether it belongs in the pack.

- **Exit criteria**: a plan generated from Phase C's real output is executed by Phase A's engine
  with no changes to that engine, and a human reviewing the generated phases says they are
  sensible. (FRD §8 item 4.)

## Phase E — Agentic implementer — *was Phase 4*
**Goal**: replace Phase A's scripted implementer with a model, and only that.

Covers FRD v1: `EXEC-1`, `EXEC-2`, `EXEC-3`, `EXEC-7`, `BUDGET-1`, `BUDGET-2`, `SECRET-1`,
`DISCLOSE-1`, `TEST-1`.

- Single process, coordinator/implementer/verifier as roles. **The verifier gets no file-write
  tools** (`EXEC-2`) — a configuration constraint, honestly labelled, with `INTEGRITY-3` as the
  actual detection mechanism.
- One provider, behind one `ModelProvider` interface. Budgets enforced in that wrapper, not
  asked of the model.
- Deterministic mock provider first (`TEST-1`), so the whole cycle is testable without tokens.
- Pre-run secret scan surfaced at the gate with forced acknowledgment (`SECRET-1`).
- **Exit criteria**: FRD §6 criteria 6, 9, 11, 13 pass; a full run completes against the Phase A
  target repo with the model doing the edits.

## Phase F — Real-repo validation — *was Phase 8*
**Goal**: run the whole thing against a real .NET Framework codebase and see what breaks.
- Validate all 14 of FRD §6's v1 acceptance criteria.
- Expect FRD §10's open issues (git hooks, context-window limits, flaky checks, private feeds)
  to surface here if they have not already. **Resolving them is a requirements change earned by
  evidence — the only kind this project should be accepting for now.**

---

## Deferred (previously Phases 0, 3, 5, 7) — all now FRD v2
- **Optional OpenBot UI** (was Phase 0): FRD `UIATTACH-*` is v2. Headless core first; the UI must
  never become load-bearing, which building headless-first enforces for free.
- **Multi-provider backend** (was Phase 3): FRD `PROVIDER-1/2` are v2 and were removed from the
  acceptance criteria. Ship on one model; keep the interface seam because it costs nothing.
- **Exported telemetry** (was Phase 5): FRD `TELEMETRY-*` is v2 — zero consumers today, and
  `EXEC-6`'s committed event log plus `DIAG-1`'s local diagnostic log are strictly more useful.
- **Sandboxed build/verify execution** (was Phase 7): FRD `ENV-3` is **won't-do for this domain**,
  resolved 2026-09-18 without B1's original spike — the reference domain's real toolchain
  (`MSBuild.exe`) is Windows-only, Windows containers were ruled out directly by the operator, and
  even the migrated .NET Core side of this org's workflow builds on the host and only
  containerizes the output afterward. Do not re-promote for this domain without new evidence; see
  `FRD.md` §12. Implementer-only sandboxing survives as **`ENV-5`**, unblocked by any of this —
  that's what the reframed Phase B1 now spikes.

## Sequencing summary
**A and B run in parallel and come first.** C needs a target repo (same decision as A). D needs C
and A. E needs D. F needs everything. Nothing needs an LLM credential until E.
