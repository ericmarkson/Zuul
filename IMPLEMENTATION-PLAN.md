# InstallGraph — Implementation Plan

> **Repositioned 2026-09-18: this is now a candidate realization of `FRD.md`, not the
> primary spec.** `FRD.md` specifies *what the system must do*, tool-agnostically. This
> document specifies one way to build it, using the specific tools this project
> researched (OpenBot, LangChain, git, a custom analyzer). Before further build-out,
> re-validate this plan's phases against `FRD.md`'s numbered requirements — particularly
> Phases 3–5 and 7, since `FRD.md` §8 flags Strands Agents SDK as a possible way to
> satisfy several of those requirements with far less hand-built code than this plan
> currently assumes.

Synthesized from `research/A-prior-art.md` through `research/G-trust-layer-reconciliation.md`.
Read those first if anything here is unclear — each has the full reasoning behind the
decision it fed into this plan. This document is the "what to build, in what order";
the research files are the "why."

This is a living document, same as `CLAUDE.md`. Update phase status and the "Next
action" pointer as work happens. Do not silently rewrite a phase's plan if reality
diverges from it — add a dated note under that phase saying what changed and why,
the same append-don't-rewrite discipline as the rest of this project's docs.

---

## Decisions this plan needs from the user before the phases that depend on them

These are the open threads from research that are genuine forks in the road, not just
unfinished lookups — flagging them up front rather than burying them in a phase.

1. **Audit engine**: ~~build our own static-analysis audit skill from scratch, or wrap
   AppCAT~~ — **resolved 2026-09-18, decisively toward custom.** An independent QA pass
   fetched `dotnet-appcat`'s actual license and found it's the same "Microsoft
   Pre-Release License Terms" family as Track A's other rejected options: no
   share/publish/distribute, cannot combine with other software for others to use, and
   it expires 30 days after commercial release. Wrapping it inside our own shipped MCP
   audit skill is squarely prohibited by its own terms. **Build the custom static
   analyzer** (Phase 1, task 1 below), starting narrow. `dotnet/try-convert` (MIT,
   archived, last pushed 2024-05-17 — genuinely forkable but unmaintained ~2.3 years) is
   worth a look as reference material, not a dependency.
2. **Target repository to validate against**: does a real .NET Framework codebase exist
   to run this against end-to-end (Phase 8), or should a synthetic/sample repo be built
   for validation? Nothing in Phase 7 or 8 can be truly proven without one.
3. **LLM provider(s) actually in hand**: which of Azure AI Foundry / Google Vertex /
   Anthropic / OpenAI does the user actually have credentials for right now? Phase 3
   only needs to *prove* one non-OpenAI/Anthropic path works end-to-end to validate the
   design; it doesn't need all four built before Phase 4 starts.
4. **OpenBot deployment posture**: run OpenBot from a clean clone as-is (recommended —
   Track B/C/E found no fork is needed for anything scoped so far), or does the user
   want a fork from day one for other reasons? Plan below assumes **no fork**, consistent
   with every research track's conclusion.

Proceeding on the stated assumptions; flag if any should change before Phase 1 starts.

---

## Phase 0 — Environment stand-up

> **Note (2026-09-18)**: after the Phase 4 correction, this phase is no longer a
> prerequisite for most of the plan. It only feeds the *optional* OpenBot-attached path
> (validating it later in Phase 3/4/7's secondary exit criteria). Phases 1, 2, 5, 6, and
> the standalone half of 3/4/7 don't need this phase done first. Still worth doing early
> if the optional path matters to you, since it's cheap and de-risks OpenBot's own setup
> separately from our own code — but it is no longer "feeds everything."

**Goal**: a working, unmodified OpenBot deployment on this machine, proving the
baseline before anything custom is added — needed only for the optional OpenBot-attached
path, not for the standalone core.

- Clone OpenBot (not a fork) alongside this repo.
- Get a CopilotKit Intelligence project + `INTELLIGENCE_API_KEY` (free tier is fine per
  OpenBot's README).
- Get one model provider key to start (whichever answers Decision 3 above) — likely
  Anthropic or OpenAI first, since those are OpenBot's best-tested paths per Track E.
- `bash scripts/start.sh`, confirm `/bot`, `/agents`, `/admin/audit` all load, and the
  stock `agent-langgraph` Bot answers a basic prompt end-to-end.
- Confirm `docker compose` can build/swap `COMPUTER_IMAGE` locally (a throwaway
  `RUN echo hi` layer added and rebuilt) — proves the customization point Track B relies
  on before depending on it for real in Phase 7.

**Exit criteria**: a person can chat with the stock LangGraph Bot in the OpenBot UI, and
`/admin/audit` shows the resulting tool-call rows.

**Depends on**: nothing. **Feeds**: only the optional OpenBot-attached exit criteria in
Phases 3, 4, and 7 — the standalone core does not depend on this phase.

---

## Phase 1 — MCP knowledge pack (the "brain")

**Goal**: an MCP server exposing (a) an audit skill that emits a structured findings
file, and (b) a catalogue of parameterized node templates (Track F).

Tasks, in order:
1. Build a minimal custom static analyzer per Decision 1's resolution above — start
   narrow (detect `<TargetFramework>net4*</TargetFramework>`, flag known-incompatible
   package ids from a maintained list, flag a fixed set of Framework-only APIs) rather
   than trying to match AppCAT's full breadth on day one. `dotnet/try-convert`'s source
   (MIT, archived) is worth reading for its own targeting-detection logic.
2. Define the findings schema precisely (category, severity, affected project/file
   references, a remediation-tag pointing at a template id) — Track F deliberately left
   this open until this decision was made.
3. Build the initial node-template catalogue as MCP resources: at minimum
   `retarget-sdk-style-project`, `upgrade-incompatible-package`,
   `replace-obsolete-api-usage`, `convert-config-transform`, `modernize-test-project`
   (the five named as a starting set in Track F), each a parameterized prompt fragment
   plus a `milestone` tag, mirroring the CopilotKit `index.json` node shape.
4. Expose both as MCP tools/resources: `run_audit` (returns the findings file) and
   `get_node_template(template_id, params)` (returns a rendered prompt fragment).

**Exit criteria**: running the MCP's audit skill against a sample repo produces a valid
findings file; requesting any of the five templates returns a correctly-parameterized
prompt fragment.

**Depends on**: Decision 1, Decision 2 (need a target repo, even a small one, to test
the audit skill against). **Feeds**: Phase 2.

---

## Phase 2 — Graph-generation mechanism

**Goal**: the mechanical (non-domain-aware) piece from Track F — turn a findings file
into a concrete, run-specific graph instance.

- Implement the category+blast-radius grouping logic described in Track F: group
  findings by category, keep genuinely inseparable multi-file changes (e.g. an EF6→EF
  Core migration) as one node, split independent findings under the same category into
  separate nodes when blast radius doesn't overlap.
- For each group, call the MCP's `get_node_template` and assemble a
  `graph-instance.json` in the `{name, edges, milestone}` shape from the reference
  CopilotKit graph (journal, Part 5).
- Build the stock/fallback graph path: a small fixed template set (SDK retarget → fix
  build errors → fix test failures → modernize flagged-but-uncategorized APIs →
  validate) used when Phase 1's audit skill finds nothing or isn't run.
- This is pure logic (no LLM calls needed here) — write it as a deterministic function/
  script first, testable without any agent runtime at all.

**Exit criteria**: feeding Phase 1's sample findings file through this produces a valid,
readable `graph-instance.json`; feeding it nothing produces the stock graph.

**Depends on**: Phase 1. **Feeds**: Phase 4 (the coordinator consumes this).

---

## Phase 3 — Provider-agnostic LLM backend

> **Note (2026-09-18)**: originally scoped as edits to `agent-langgraph`'s own files
> inside an OpenBot clone — the same category of drift as the original Phase 4 error,
> just smaller (a QA pass caught it as a residual issue, not a new one requiring its own
> correction narrative). Fixed below: build this in **our own codebase**, patterned on
> `model-key.ts`'s switch shape, so the headless core's model layer never depends on
> OpenBot existing. Optionally upstream the `azure`/`vertex` branches to `agent-langgraph`
> afterward if that's useful for the OpenBot-attached path, but that's a bonus, not the
> deliverable.

**Goal**: prove the multi-provider extension from Track E actually works, not just that
it's designed.

- In our own codebase (the one Phase 4 builds out), implement a provider switch patterned
  directly on `agent-langgraph/src/model-key.ts`'s shape: `openai`/`anthropic`/`google`
  from Track E's findings, plus `azure` (via `AzureChatOpenAI` — bundled in
  `@langchain/openai`) and `vertex` (`@langchain/google-vertexai`, one new package).
- Resolve Track E's open thread: verify whether plain `AzureChatOpenAI` covers the
  actual Azure AI Foundry deployment shape in hand, or whether a newer Azure-AI-
  inference-flavored LangChain integration is needed instead — do this against whichever
  Azure credential Decision 3 actually produces, not in the abstract.
- Prove at least one of the two new branches end-to-end **in our own codebase directly**
  — a standalone script/process making one real chat call, no OpenBot required to
  validate this phase.
- Leave Option 1 (LiteLLM proxy) undocumented-but-noted as a fallback; don't build it
  unless the direct-LangChain approach hits a wall.

**Exit criteria**: a real chat turn against at least one of Azure/Vertex works, called
directly from our own codebase, with no OpenBot process involved.

**Depends on**: Decision 3 only — no OpenBot dependency. **Feeds**: Phase 4 (this
becomes the coordinator/implementer's model-selection layer directly, not by way of an
OpenBot example Bot).

---

## Phase 4 — Coordinator, implementation, and QA agents (standalone core, OpenBot optional)

> **Corrected 2026-09-18.** The original version of this phase built the
> coordinator/implementer/QA agents *as* OpenBot-managed Bots whose tools execute
> through OpenBot's gateway — copying the pattern Track C found in OpenBot's own shipped
> `agent-bot`/`agent-langgraph` examples. That was a mistake: it makes OpenBot
> load-bearing for the core to function at all, which directly contradicts this
> project's non-negotiable requirement, stated since the very first design conversation
> and repeated in `CLAUDE.md`, that **the harness must run fully headless, with OpenBot
> strictly optional.** Track C's finding about the gateway-proxy pattern is real and
> correctly described — it's just a description of how OpenBot's *own* managed Bots
> choose to get OpenBot's governance benefits, not a requirement AG-UI itself imposes.
> An external, self-sufficient agent registered as "bring your own agent" (the
> `their-endpoint` credential type already visible in `desktop/src/HarnessPicker.tsx`)
> is under no such obligation. Rewritten below accordingly.

**Goal**: the actual multi-agent core, as a standalone system that works with or
without OpenBot attached.

- Build `agent-coordinator`, `agent-implementer`, and `agent-qa` as one standalone
  codebase (reusing Phase 3's provider-agnostic model-selection code, since that part of
  `agent-langgraph`'s design has nothing OpenBot-specific about it) that:
  - Calls the Phase 1 MCP server **directly**, via a plain MCP client — no OpenBot
    plugin registration required for this to work.
  - Executes its own `git`, file-edit, package-manager, and (Phase 7) `dotnet` shell
    commands **directly** against a real local working copy — no gateway, no proxy, no
    dependency on any "computer" container existing.
  - Implements the approval gate as its own pluggable step, **default: a CLI prompt**
    presenting the generated `graph-instance.json` and blocking for a yes/no — the exact
    "one approval gate, clearly announced as the last one" pattern from the original
    CopilotKit onboarding CLI (journal, Part 2). This is what makes the harness usable
    with zero UI at all.
  - Implements Phase 6's git-native audit checks **itself**, as its own primary trust
    boundary — not "complementary to OpenBot's gateway audit" as Track G originally
    framed it, since headless runs have no OpenBot gateway to be complementary to.
- **Coordinator**: walks `graph-instance.json` node by node, dispatching each node's
  rendered prompt to the implementer, then the QA step. Never touches files/shell
  itself — pure orchestration, same as before.
- **Implementer**: makes the actual changes for one node — `git`, file edits, package
  commands — run directly, recorded via Phase 6's commit-per-phase mechanism.
- **QA**: runs `dotnet build`/`dotnet test`/targeted checks directly, reports a
  granular, itemized per-check result (mirroring the journal's `verify --json` shape)
  rather than one boolean — unchanged from the original plan.
- **Optional OpenBot attachment, added on top, not load-bearing**: the same coordinator
  process additionally exposes an `/ag-ui` endpoint (reusing `@ag-ui/core`/
  `@ag-ui/encoder`, per Track C's contract description, which is accurate for this use
  regardless of the correction above) so it can be registered in OpenBot as a
  bring-your-own-agent Bot for chat/observability. When attached this way, the approval
  gate can *additionally* render as an AG-UI surface-tool card (Track C's mechanism) as
  a nicer UI for the same underlying "plan approved" state transition the CLI prompt
  already drives — it's an alternate front end for one decision point, not a second,
  separate gate. OpenBot's own audit trail becomes a bonus second record of what
  happened, never the only one.
  - **Registration prerequisite, confirmed against OpenBot's source**: OpenBot's server
    refuses to register a private/loopback endpoint by default (`server/src/agents/endpoint.ts`
    — an SSRF guard) unless it's listed in `AGENT_ENDPOINT_ALLOWED_HOSTS`, and that
    blanket allowance is itself refused under `NODE_ENV=production`. A locally-run
    harness needs an explicit host:port entry there (or a tunnel) before it can be
    attached at all — a deployment prerequisite for this optional path, not something
    that works by default.
  - **Register the whole coordinator/implementer/QA loop as ONE Bot, not three.**
    Confirmed against OpenBot's source: each OpenBot-*managed* Bot gets its own isolated
    workspace volume (`supervisor/src/names.ts`/`docker.ts` — one volume per Bot id), so
    three separately-registered OpenBot Bots would each see a different, non-shared
    working copy — breaking the commit-per-phase/QA-verifies flow from Phase 6, which
    assumes one shared repo. This only bites if the optional attachment is ever built as
    three separate OpenBot-managed Bots instead of one external process with three
    internal roles; since the whole point of the standalone design is that it's one
    process either way, register that one process as one bring-your-own-agent Bot.
  - **The approval card is a granted component with a fixed schema, not free-form.**
    OpenBot's shipped `askApproval` component (`app/src/components/gallery/decisions.tsx`)
    takes `{title, summary, details:[{label,value}], approveLabel, rejectLabel}` and must
    be explicitly granted to a Bot by an administrator. Presenting a whole
    `graph-instance.json` this way means flattening it into that shape (one row per
    node, most likely) or shipping a custom gallery component — real but small work for
    Phase 4/Phase 8, not something to assume is free once OpenBot is attached.
- The Phase 1 MCP server can *still* optionally be registered in OpenBot's
  `/admin/plugins` for a deployment that wants OpenBot itself to reach it for some other
  purpose — but our harness's own direct MCP client means this is no longer a
  dependency for our own agents to function.

**Exit criteria (headless, primary)**: running the coordinator from the command line
against a real repo, with no OpenBot process running at all, produces a generated plan,
a CLI approval prompt, and (once approved) a dispatched implementer→QA cycle for at
least one stock-graph node, end to end.

**Exit criteria (OpenBot-attached, secondary)**: the same coordinator process, also
registered in a running OpenBot as a bring-your-own-agent Bot, shows the same run's
progress as a chat channel, and the approval gate renders as a card instead of (or in
addition to) the CLI prompt.

**Depends on**: Phases 2 and 3. **Feeds**: everything after this point is refinement/
validation, not new architecture.

---

## Phase 5 — Analytics instrumentation

**Goal**: the closed, allowlisted event schema from Track D, wired into the coordinator.

- Define the event types (`phase_started`, `phase_ended`, `gate_presented`,
  `gate_approved`, `check_result`, `retry_attempted`, `friction_reported`,
  `run_completed`), each with an enum/count/duration-only property set — no free text,
  paths, or content, per Track D's explicit denylist.
- Emit locally first (append-only, bounded), non-blocking — a failure to record an event
  must never block a phase, matching both Track D's finding and the journal's own
  "checkpoints are telemetry, not control flow" principle.
- Respect `DO_NOT_TRACK=1`.
- Defer the OpenTelemetry `gen_ai.*` exporter and the optional PostHog sink to a later
  pass — Track D was explicit that these are additive, not required for correctness,
  and the GenAI conventions are still unstable enough that building against them now
  risks rework.

**Exit criteria**: running Phase 4's end-to-end test produces a local, schema-valid
event log covering the whole run (plan generated → gate presented → gate approved →
each node's phase-lifecycle events → run completed).

**Depends on**: Phase 4 (needs real phase-lifecycle points to hook into). **Feeds**:
nothing downstream blocks on this — it can slip without stalling other phases.

---

## Phase 6 — Git-native integrity/trust layer

> **Note (2026-09-18, follows the Phase 4 correction above)**: this is now the
> harness's *primary* trust boundary, run directly by the coordinator/implementer/QA
> process itself — not something that depends on an OpenBot gateway being present. The
> "OpenBot CEL policy could deny these commands" concern below only applies in the
> optional OpenBot-attached mode, and only if a deployment chooses to route this
> harness's shell access through OpenBot's own computer/gateway instead of running it
> standalone — worth restating as a deployment choice, not a default assumption.

**Goal**: Track G's recommended replacement for a bespoke file-hash baseline.

- Baseline: at run start, capture `git status`/`git stash` state of the target repo
  (living in a local working directory per Phase 7's primary/standalone path — or, only
  in the optional OpenBot-attached mode, a Bot's `/workspace`) before any writes.
- Per-phase commits: each completed node's implementer changes land as one commit,
  scoped to that node.
- Audit: after each phase and at final completion, `git diff <baseline>..HEAD --stat`
  checked against the approved plan's declared scope for that node; a diff touching
  anything outside the plan is a stop/friction-report condition, not something to route
  around (per Track G's "fail closed" conclusion).
- Narrow hash-based carve-out: only for gitignored/credential-adjacent paths (`.env`-
  shaped files) that git itself can't see — reuse the concept, not the full CopilotKit
  onboarding hash-store implementation.
- Document, as an explicit deployment prerequisite, the OpenBot CEL policy allowance
  needed for the specific read-only `git status`/`git diff` commands this depends on —
  Track G flagged that a stricter deployment's policy could otherwise legitimately deny
  them.

**Exit criteria**: a deliberately-injected out-of-scope file change during Phase 4's
end-to-end test is caught by the audit step and produces a stop/friction report, not a
silent pass.

**Depends on**: Phase 4 (needs real commits to diff). **Feeds**: Phase 8's validation.

---

## Phase 7 — .NET build/test execution environment

> **Note (2026-09-18, follows the Phase 4 correction above)**: the *primary* path is
> now the standalone harness's own execution environment — a container/environment we
> define ourselves for the coordinator/implementer/QA process, with the .NET SDK
> installed directly, no OpenBot involved. Track B's `COMPUTER_IMAGE` customization
> (below) is real and still useful, but only for the *optional* OpenBot-attached mode,
> where a deployment specifically wants OpenBot's own sandboxed computer to be the
> execution environment instead of the standalone harness's own.
>
> **Second correction, same date**: the target .NET version and the SDK package source
> were both wrong. **.NET 8 reaches end-of-support 2026-11-10** — 53 days out from when
> this was caught — so it must not be the product's target output; use whatever the
> current LTS is at build time (net10.0 as of this writing, supported to Nov 2028), and
> don't hardcode a version number anywhere that will itself go stale — resolve it at
> setup/build time instead. Separately: on Ubuntu 24.04, Microsoft's own package feed
> carries **no** .NET packages at all (confirmed against Microsoft Learn) — the
> `dotnet-sdk` apt package on 24.04 comes from Ubuntu's own (Canonical) feed, not
> Microsoft's, and only ships the `.1xx` feature band for whichever major version is
> current. The install command itself is fine; "Microsoft's apt package" was a
> misattribution. Also: the stock `agent-computer/Dockerfile` ends its existing apt
> layer with `rm -rf /var/lib/apt/lists/*`, so a new `RUN apt-get install -y dotnet-sdk-*`
> layer needs its own `apt-get update &&` — it will fail without it.

**Goal**: Track B's concrete customization, made real, for whichever execution
environment a given deployment actually uses.

- **Primary (standalone)**: package the coordinator/implementer/QA process with the
  .NET SDK installed directly (a plain Dockerfile or dev-machine setup — Ubuntu base +
  `apt-get update && apt-get install -y dotnet-sdk-10.0`, or whatever the current LTS
  package name is at build time — do not hardcode `8.0`), and have the implementer clone
  the target repo into a local working directory as its first action, using its own
  direct shell access (no gateway involved, per the Phase 4 correction).
- **Optional (OpenBot-attached)**: build a custom `agent-computer` image (the stock
  OpenBot Dockerfile plus its own `apt-get update && apt-get install -y dotnet-sdk-10.0`
  layer) and register it via `COMPUTER_IMAGE`, for a deployment that wants OpenBot's own
  sandboxed computer to run the build/test instead — same Track B mechanics as
  originally researched, now correctly scoped as a deployment option rather than the
  only path.
- Explicitly do **not** attempt to build the original .NET Framework baseline inside
  this Linux container (Track B's known limitation) — the pre-migration state is
  evidenced only by Phase 1's audit findings. Note this limitation directly in whatever
  summary the completed run presents to the user, the same way OpenBot's own
  `visual-check: skipped` was surfaced honestly in the journal rather than glossed over.
- For the optional OpenBot-attached mode specifically: turn on `COMPUTER_RUNTIME=runsc`
  (gVisor) for that Bot's computer if the deployment host supports it, per Track B's
  suggestion for a Bot about to run arbitrary build scripts from an unfamiliar repo. Not
  applicable to the standalone primary path, which has no OpenBot computer to configure.

**Exit criteria (primary)**: the standalone harness's own shell commands can run
`dotnet build` and `dotnet test` against a real net10.0-targeted (or whatever the
current LTS is) project in its own execution environment, with results visible in
Phase 5's analytics log.

**Exit criteria (OpenBot-attached, secondary)**: the same, run as `agent-qa`'s
deployment-tool shell calls inside OpenBot's own computer, additionally visible in
OpenBot's `/admin/audit`.

**Depends on**: nothing, for the primary path. Phase 0, only if the optional
OpenBot-attached variant is being built too. Can be built in parallel with Phases 1–3;
only needs to land before Phase 4's end-to-end test needs a real build/test result
rather than a stub.

---

## Phase 8 — End-to-end validation

**Goal**: run the whole thing against a real target (Decision 2) and see whether the
"as close to one-button as possible" goal actually holds.

- Point the coordinator at a real .NET Framework repo. Run the audit (Phase 1), generate
  the graph (Phase 2), present and approve the plan (Phase 4), let it run unattended
  through implementer/QA per node (Phases 4, 6, 7), and check the final state.
- Validate every guardrail actually fires under real conditions, not just the happy
  path: an out-of-scope file change is caught (Phase 6), a QA failure produces a
  granular per-check report rather than a bare pass/fail, a stuck phase produces a
  structured friction report rather than an infinite retry loop, and the analytics log
  (Phase 5) reconstructs the whole run afterward.
- Record findings the same way the journal recorded the original CopilotKit onboarding
  run — as a dated log entry here or in a new `RUNS.md`, not just as passing/failing CI
  output — since this project's own instinct (stated at the very start of this
  conversation) is that a durable, readable run log is part of what makes this
  trustworthy.

**Exit criteria**: one real .NET Framework → .NET Core upgrade, run start to finish,
with every guardrail from the original design exercised at least once and recorded.

**Depends on**: Phases 1–7. **Feeds**: nothing — this is the proof, not a dependency for
more building.

---

## Sequencing summary

> **Corrected 2026-09-18**: the original diagram rooted the entire build order at
> Phase 0 (OpenBot stand-up), which was the same load-bearing-OpenBot mistake as the
> original Phase 4, just encoded in a diagram instead of prose. Phase 0 is now a
> side-branch feeding only the optional OpenBot-attached mode, not a root dependency.

```
Phase 1 (MCP/audit) ─→ Phase 2 (graph-gen) ──────────────────────┐
Phase 3 (LLM providers, standalone) ─────────────────────────────┼─→ Phase 4 (agents) ─┬─→ Phase 5 (analytics)
Phase 7 (standalone .NET env) ────────────────────────────────────┘                    ├─→ Phase 6 (git trust layer)
                                                                                        └─→ Phase 8 (end-to-end)

Phase 0 (OpenBot stand-up, optional) ──→ feeds only the secondary/optional exit
                                          criteria in Phases 3, 4, and 7 above —
                                          not a dependency for the standalone path.
```

1, 3, and 7 (standalone paths) can proceed in parallel from the start — none of them
need Phase 0. 2 needs 1. 4 needs 2 and 3. 5 and 6 both need 4 but not each other. 8 needs
everything except Phase 0 unless the optional OpenBot-attached mode is also being
validated.

---

## Open threads inherited from research, not yet closed by this plan

Carried forward from the findings files, restated here so they aren't lost. Several
were resolved by the 2026-09-18 QA pass — marked below rather than deleted, per this
project's append-don't-erase convention.

- ~~AppCAT's exact license terms and JSON schema (Track A)~~ — **resolved**: license
  confirmed adverse (same proprietary family, no redistribution). Decision 1 above now
  points at the custom analyzer; AppCAT's JSON schema is no longer relevant to pursue.
- ~~Whether an official Python AG-UI SDK exists~~ — **resolved, exists**: OpenBot's own
  `agent-langgraph-agui/` directory depends on the `ag-ui-langgraph` PyPI package
  (pinned `0.0.45`) plus FastAPI/uvicorn. Not needed if Phase 4 stays TypeScript as
  planned, but confirmed available if a Python coordinator is ever preferred instead.
- Whether OpenBot's custom-MCP-server plugin path handles a locally-run MCP as smoothly
  as its catalogued vendors (Track C) — **now optional-path-only**: Phase 4's plugin
  registration step is no longer something our own agents depend on (they call the MCP
  directly), so this only matters if a deployment separately wants OpenBot itself to
  reach the MCP for some other purpose.
- LiteLLM's current license terms (Track E) — only matters if Phase 3's direct-LangChain
  approach hits a wall and the proxy fallback gets used.
- PostHog self-hosting footprint (Track D) — only matters once the optional external
  sink is actually built, deferred past Phase 5.
- **New, from the 2026-09-18 QA pass**: GitHub Copilot's upgrade agent is not actually
  model-locked (it supports BYOK for Anthropic/Bedrock/Google AI Studio/Microsoft
  Foundry/OpenAI/xAI) — Track A's verdict against adopting it is unaffected (the
  proprietary license is the real blocker), but `research/A-prior-art.md` and
  `CLAUDE.md`'s headline findings stated the wrong reason; both corrected.
- **New, 2026-09-18, later same day**: `CopilotKit/harness-sdk` (an unmodified fork of
  AWS's `strands-agents/harness-sdk`, Apache 2.0) surfaced as a possible way to satisfy
  much of Phases 3–5 and part of 7 with far less hand-built code — its `litellm`-backed
  model provider, `multiagent`/`hooks`/`interventions`/`telemetry`/`sandbox` modules,
  and official `ag_ui_strands` AG-UI bridge all look directly relevant. **Not yet
  evaluated in depth** — tracked as `FRD.md` §8 item 1, a future research item, not
  folded into this plan yet. See `FRD.md` for the tool-agnostic requirements this plan
  should now be validated against before any further build-out.
