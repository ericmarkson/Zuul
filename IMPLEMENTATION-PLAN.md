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

- **B3 — done, 2026-09-19. `EXEC-10` promoted to v1.** Second `git worktree`, checked out by raw
  commit SHA (detached, never by branch name), gives the verifier a working directory the
  implementer's process never touches. Implemented directly in `controlplane/gitops.py`
  (`add_worktree`/`remove_worktree`) and `controlplane/runner.py` (`_run_check_set` now checks
  the verifier worktree out to the implementer's latest commit before every check run, baseline
  included) — ~15 lines, cheaper than the "probably 30 lines" estimate. Locked down by
  `controlplane/tests/test_verifier_worktree.py`. Full re-verification: 15/15 hermetic tests
  pass, live run reproduces the same happy-path-then-escalation behavior, worktree created once
  and cleaned up on every exit path (success, escalation, rejection). See `FRD.md` §13.
- **B1 (reframed)**: spike `ENV-5` — stand up a plain Linux container (no .NET toolchain
  at all) that can check out the run branch, apply a scripted edit, and commit. This is a much
  easier spike than the one it replaces, since it was never blocked by MSBuild. **Not yet done.**
- **B2**: Restore from an authenticated private feed (Azure Artifacts / Artifactory) and
  determine what the control plane must do with `NuGet.config` credentials. (FRD `ENV-4`, §10.6.)
  Unaffected by B1's change — package restore happens during the unsandboxed host build either
  way. **Not yet done.**
- **Exit criteria**: written answers appended to `logs/session-log.md` for B1(reframed) and B2,
  each either promoting a v2 requirement, confirming its deferral, or converting it to won't-do.
  B3's answer is already recorded (promoted).

## Phase C — Reference knowledge pack (.NET) — *was Phase 1* — **done, 2026-09-20**
**Goal**: the first domain-specific knowledge source: an audit that emits an `AUDIT-1`-compliant
findings file, plus a catalogue of parameterized node templates.

Covers FRD v1: `AUDIT-1`, and lays groundwork for `PLAN-1` (audit-derived path — the plan
*generator* that consumes this output is Phase D, not this phase) and the v1 half of
`KNOWLEDGE-4` (the pack now computes its own content hash; wiring the control plane to record
it in the event log at run time is a Phase D/E integration point, not done here).

- **Task 1 — done**: `knowledge-packs/dotnet-framework-to-core/analyzer.py`. Read-only static
  analysis, zero network, zero build/execution: parses `.csproj`/`.config` XML and file
  presence only. Detects legacy (non-SDK) project format, the declared target framework,
  `packages.config` vs `PackageReference`, Framework-only assembly references with no direct
  .NET Core equivalent (`System.Web`, `System.Windows.Forms`, `System.Drawing`,
  `System.ServiceModel`, `System.EnterpriseServices`, `System.Web.Services`,
  `System.Workflow`), and legacy `App.config`/`Web.config` files.
- **Task 2 — done**: `findings.py`. Every finding carries `category`, `severity`,
  `affected_paths` (AUDIT-1's minimum) plus `id`, `description`, `remediation_tag`, and
  `evidence`. The findings file itself carries a `pack_content_hash` (the pack hashing its own
  source tree) and `schema_version`.
- **Task 3 — done**: four node templates in `templates/` (`retarget-sdk-style-project`,
  `migrate-packages-config-to-package-reference`, `replace-incompatible-api`,
  `modernize-config-file`), each declaring an `INTEGRITY-8` side-effect class. Three are
  `file-only`; the packages.config migration is `package-manager-mutating`, matching the FRD's
  own observation that this is the common case for this domain, not the exception.
- **Changed from the original plan, as already flagged**: **the pack is a local versioned
  directory plus a CLI, not an MCP server** (`cli.py`, invoked directly by path — the
  directory's hyphenated name is deliberate, it can never be `import`ed from `controlplane/`).
  See FRD `KNOWLEDGE-1`.
- **Exit criteria — met**: `python knowledge-packs/dotnet-framework-to-core/cli.py audit --repo
  <path> --out <file>` run against two real targets. Against `fixtures/sample-dotnet-app`
  (already modern SDK-style): 2 low-severity findings only, correctly quiet. Against the
  stretch-goal target `C:\Code\_sandbox\Opti11\alloy-mvc-template` (read-only, never modified):
  **11 findings — 4 high, 2 medium, 5 low** — correctly identified the legacy project format,
  `v4.6.1` targeting, `packages.config`, three incompatible-API groups (15 `System.Web.*`
  assemblies alone), and five legacy config files. `controlplane/`'s test suite (15/15) and a
  live Phase A run were re-verified afterward — the plan loader was never touched and behaves
  identically. 9/9 hermetic analyzer tests pass, zero network.

## Phase D — Audit → plan generation — *was Phase 2* — **done, 2026-09-20**
**Goal**: turn any findings file into a concrete plan of the same shape Phase A already executes.

Covers FRD v1: `PLAN-1` path (a). **Grouping is category (here: remediation tag) + declared-path
overlap only** — lexical operations the domain-agnostic core can honestly perform, implemented
in `controlplane/plangen.py`. Blast-radius grouping (`PLAN-2`) is still v2 and untouched.

`plangen.py` knows nothing about .NET or any other domain: it reads the generic findings-file
contract (category/severity/affected_paths/remediation_tag) and a directory of node-template
JSON files (id → side_effect_class), both pack-supplied data, never pack code. Component
detection (which project a finding belongs to, for the path-overlap half of grouping) is pure
path-prefix matching against the directories of `.csproj`-affecting findings — no parsing of
what a project actually contains. A finding with no `remediation_tag` (informational only, no
action to group) is dropped from the plan but never silently — its id is recorded in the
generated plan's `_generated_from.dropped_informational_findings` field.

- **Exit criteria — met, against the real stretch-goal target, not a synthetic one.** Generated
  a plan from Phase C's real `alloy-mvc-template` audit (11 findings → **4 phases**, one per
  remediation tag, zero findings dropped) and ran it through Phase A's **completely unmodified**
  `runner.py`/`plan.py` against a scratch copy of the real repo (`python -m controlplane.cli run
  --plan <generated> --fixture C:\Code\_sandbox\Opti11\alloy-mvc-template --yes`). Result: `SECRET-1`
  found two genuine secrets in the real repo for the first time (a connection-string password in
  `ConnectionStrings.config` and another in `build/database/Alloy.mdf`) and correctly forced
  acknowledgment before the gate; the baseline `dotnet build Alloy.Mvc.Template.sln` genuinely
  failed (legacy MSBuild format, as expected — `ENV-3`'s resolution predicted exactly this) and
  `QA-5` correctly treated it as a pre-existing, non-blocking delta; all 4 phases committed
  (exactly one commit each, `git log` confirms) with zero scope violations and zero regressions;
  `RUN_COMPLETED` fired. Since generated phases have empty `edits` by design (no LLM or
  hand-authored remediation exists yet — that's Phase E), this proves structural and mechanical
  correctness end to end, not that the *migration* succeeded. Generated phases read as sensible
  on review: retarget-to-SDK-style first, then package management, then the incompatible-API
  rewrite, then config modernization — a defensible real migration order.
- **Not built**: any actual remediation content. This was always Phase E's job, and the
  generator says so in every plan it produces (`plan_description` states this explicitly).

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
