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

## Phase D — Audit → plan generation — *was Phase 2* — **done, then re-done under the pivoted design, 2026-09-20**

**The pivot described in `CLAUDE.md`'s "ARCHITECTURAL PIVOT IN PROGRESS" section is now built.**
The fixed node-template catalogue (`knowledge-packs/dotnet-framework-to-core/templates/`) and
`plangen.py`'s `load_templates`/template-matching core (`b25eda5`) are deleted, not extended.
`controlplane/plangen_llm.py` is new: one model call per finding-group (grouped by the same
lexical category + path-overlap rule as before, unaffected by this pivot) proposes that phase's
`side_effect_class`, description, any scope beyond the findings' own `affected_paths`, and
whatever Python-script check(s) would actually prove that specific remediation happened.
`plangen.py` calls it in place of the old template lookup; the on-disk plan shape, the single
approval gate, and `runner.py` are all unchanged. The four templates were deliberately **not**
kept as few-shot context, on the reasoning that they encoded exactly the failure modes Phase F's
first run found (see below) and would risk the model re-learning them from the "free" examples —
recorded as the resolution to the "open, not yet decided" question in `CLAUDE.md`.
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
- **Re-validated live against the real target after the pivot, 2026-09-20**: ran
  `python -m controlplane.cli generate-plan` against the real `alloy-mvc-template` audit
  (11 findings) with `gpt-5.6-sol` — 4 phases, ~3.5k input / ~3.5k output tokens, ~$0.09. Read
  by hand, not just structurally validated: phase-3 (`replace-incompatible-api`)'s
  `declared_scope` now includes the actual `.cs` usage-site files (every affected controller,
  `Global.asax.cs`, `Business/*`, `Views`) rather than being confined to the `.csproj`'s
  `<Reference>` list — direct evidence against Phase F's gap 1 below. Phase-4
  (`modernize-config-file`)'s proposed `additional_scope` included `appsettings.json` unprompted,
  and its proposed check verifies both that the legacy config files are gone *and* that
  `appsettings.json` parses as a JSON object — direct evidence against Phase F's gap 2. Neither
  fix is hardcoded; both came from the model reasoning about the specific findings in front of
  it. Plan artifact not committed (a smoke-test output, not a project file); the generation
  command is reproducible from `.scratch/audits/alloy-mvc-template.json`.

## Phase E — Agentic implementer — *was Phase 4* — **done, then extended into a tool-calling agent, 2026-09-20**

**The pivot's point 2 is now built.** `controlplane/llm_implementer.py`'s `request_edits` is no
longer one completion call — it runs a bounded loop (`max_tool_rounds`, default 6, plumbed
through `Runner`/CLI as `--llm-max-tool-rounds`) via a new `ModelProvider.complete_with_tools`
method, giving the model two read-only context tools (`read_file`, `list_directory`, confined to
the target repo by a path-traversal guard) before it must call `finalize_edits` exactly once to
submit its proposed full-file-content edits. `EXEC-2` is unaffected: `finalize_edits` is the only
way to produce output, the model still gets no file-write tool of its own, and
`INTEGRITY-3`'s post-commit scope diff is still the actual enforcement. `BudgetedProvider` wraps
`complete_with_tools` with the identical per-phase/per-run budget accounting as plain `complete`
(refactored into shared `_pre_call_cap`/`_record_usage` helpers). `OpenAIProvider.complete_with_tools`
is the only place that translates this project's generic message/tool-call shape to and from the
OpenAI SDK's own function-calling schema.
- **A second real bug found and fixed the first time this path touched the real API**:
  `gpt-5.6-sol`'s `/v1/chat/completions` endpoint rejects function tools combined with any
  `reasoning_effort` other than `"none"` ("Function tools with reasoning_effort are not
  supported... use /v1/responses or set reasoning_effort to 'none'"). `complete_with_tools` now
  hardcodes `reasoning_effort="none"` for tool-calling requests specifically; the plain
  `complete()` path (plan generation) is unaffected and still honors the configured value.
- **Live-verified against the real API and the real model**, safe synthetic fixture only: asked
  for a new `Calculator.Square` method plus a matching test, explicitly prompted to `read_file`
  the test file first. The model instead finalized directly in one round — it already had that
  file's content in its first-turn prompt (the file was inside the phase's own declared scope,
  which is always shown upfront) so there was nothing left to read — and produced correct,
  idiomatic code verified by hand against `git diff`. This proves the `finalize_edits` path and
  the reasoning-effort fix against the real API; it does **not** exercise an actual multi-round
  `read_file` round-trip live (that mechanic is covered directly by the hermetic
  `MockModelProvider` suite in `test_llm_implementer.py`, not yet by a live call). ~3.4k input /
  ~1k output tokens, ~$0.03.
**Goal**: replace Phase A's scripted implementer with a model, and only that.

Covers FRD v1: `EXEC-1`, `EXEC-2`, `EXEC-3`, `EXEC-7`, `BUDGET-1`, `BUDGET-2`, `SECRET-1`,
`DISCLOSE-1`, `TEST-1` — all of it now, including `EXEC-7` (crash/resume), built in a follow-up
pass the same day once the rest of the phase was live-verified.

- `controlplane/model_provider.py`: `ModelProvider` protocol, `MockModelProvider` (`TEST-1`,
  scripted responses/exceptions, zero network), `OpenAIProvider` (the only module that imports
  the `openai` SDK), and `BudgetedProvider` — wraps either, enforces `BUDGET-1/2` per-phase and
  per-run token ceilings and wall-clock limits, capping the outgoing request when it can and
  still checking real usage afterward rather than trusting the cap was honored.
- `controlplane/llm_implementer.py`: builds the prompt (phase description, declared scope,
  current file contents, check commands, and prior-attempt failure feedback on retry) and
  parses the model's JSON response into proposed full-file-content edits. Malformed responses
  raise, they don't crash the run.
- `controlplane/runner.py`: `_execute_phase` now owns an `EXEC-3` retry loop (bounded by
  `retry_budget`, default 2) around whichever implementer produced no pre-authored edits.
  Between attempts it does an `INTEGRITY-8` file-only `git reset --hard` to the phase's own
  pre-attempt commit — a failed attempt never leaks into the next one. Scope violations and
  budget overruns are never retried; both escalate immediately, fail closed, exactly like the
  scripted path always has. `PHASE_COMMITTED` now records `attempts`, `input_tokens`, and
  `output_tokens` per `EXEC-6`'s cumulative-usage requirement. `EXEC-2` is unaffected — the
  model still gets no file-write tools of its own; the runner writes what it proposes and
  `INTEGRITY-3`'s post-commit diff is still the actual enforcement.
- **A real bug found and fixed while wiring this in**: `gate.py`'s disclosure-policy text had a
  hardcoded "no third-party model provider is used" line from Phase A — a `DISCLOSE-1`
  compliance bug the instant a real provider was configured. Now built from the run's actual
  `model_in_use`/`model_name` state.
- **`EXEC-7`, built same day in a follow-up pass**: `controlplane/run_lock.py` — an exclusive
  lock keyed to run id, using OS-native advisory file locking (`msvcrt` on Windows, `fcntl`
  elsewhere) rather than a plain marker file, specifically because the OS releases it
  automatically when the holding process dies, including a real crash, which a marker file
  cannot do. `controlplane/resume.py` — on startup, if a run id's event log has events but none
  of them is `RUN_COMPLETED`/`RUN_ABANDONED`/`ESCALATED`, the system halts and writes a
  `resume_report.json` (last committed phase, run branch head, working-tree dirty state) rather
  than auto-resuming or auto-resetting, exactly as specified — resuming stays an operator
  decision in v1. `Runner` gained an optional `run_id` constructor arg and the CLI a `--run-id`
  flag, since a run needs a stable, caller-supplied identity to be addressable across process
  restarts at all; a fresh UUID (the default) never collides with anything, by construction.
  Also refuses outright if a run id is reused after it already completed. Verified with a real
  simulated crash, not just a unit test of the pieces: a `MockModelProvider` scripted to raise
  mid-phase leaves genuinely incomplete state, and a second `Runner` instance against the same
  run id correctly detects it, writes the report, and never re-attempts the phase.
- **Exit criteria — met.** FRD §6 criteria 6 (deterministic verdicts), 9 (budgets halt), 11
  (crash is legible), and 13 (hermetic) all pass. **A full run completed against the real
  model, model doing the edits**: `gpt-5.6-sol` via the real OpenAI API, live, against the
  Phase A synthetic fixture (deliberately not the real stretch-goal target on this first live
  run) — both phases succeeded on the first attempt, zero retries needed, ~1500 input / ~1100
  output tokens, ~$0.03. Generated code verified by hand against `git diff`: a correct
  divide-by-zero guard and a correct `Multiply` method plus test, following the existing code's
  own conventions, touching nothing outside declared scope. 64/64 hermetic tests pass (31 new
  across the two passes: `test_model_provider.py`, `test_llm_implementer.py`,
  `test_runner_llm.py`, `test_run_lock.py`, `test_resume.py`, `test_runner_resume.py` — the
  `_runner_*` files drive `Runner` itself, not just the isolated pieces, through
  `MockModelProvider` and a real simulated crash).

## Phase F — Real-repo validation — *was Phase 8* — **first run done, 2026-09-20; gaps found, not yet fixed**
**Goal**: run the whole thing against a real .NET Framework codebase and see what breaks.
- Validate all 14 of FRD §6's v1 acceptance criteria.
- Expect FRD §10's open issues (git hooks, context-window limits, flaky checks, private feeds)
  to surface here if they have not already. **Resolving them is a requirements change earned by
  evidence — the only kind this project should be accepting for now.**

**First run, against `alloy-mvc-template` (scratch copy, real repo confirmed untouched
afterward): the pipeline mechanics worked; the migration content quality was mixed, and it
surfaced exactly the kind of evidence-earned findings this phase exists to produce, not a clean
pass. Full detail in `logs/session-log.md`'s "Phase F, first run" entry. Two real gaps found,
neither fixed yet, pending direction:**
1. Phase C/D's `declared_scope` for `incompatible-api` findings covers only where the analyzer's
   evidence lived (the `.csproj`'s `<Reference>` list), not the actual `.cs` usage sites — a
   phase built from it cannot do a real fix within its own declared scope. Deleting the
   references was the only in-scope move available, and it would make a real build fail in a
   new way if this repo could be built here at all.
2. A phase (`modernize-config-file`) deleted 543 lines across 5 config files and produced none
   of the `appsettings.json` replacement its own description promised — a real, "helpfully
   reforms the repository" failure (FRD §5a's named threat), and the pipeline reported it as
   verified, because `QA-5`'s delta check answers "did the build get worse," not "did this
   phase do what it said it would." `dotnet build` already failed identically before and after
   every phase in this environment (no real MSBuild), so delta-neutrality gave zero signal
   either way — known going in, but this run made the consequence concrete rather than
   theoretical.

Not yet resolved: whether/how to fix declared-scope generation for `incompatible-api`, and
whether a new requirement (something checking a phase actually did what it claimed, independent
of build success) is warranted. Per this project's own rule, this is earned evidence, not a
checklist item — the next FRD change here should be scoped to exactly these two findings.

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
