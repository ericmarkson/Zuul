# Session log

Append-only. Never edit past entries — if something turns out wrong, add a new entry
that says so and supersedes it. One entry per meaningful chunk of work (not every tool
call).

---

### 2026-09-17 — Project scaffolded, research queue set

Design agreed through conversation (see `CLAUDE.md` for the current consolidated
version): a CLI-driven, graph-based .NET Framework → .NET Core upgrade harness with an
MCP knowledge-pack backend, a coordinator/implementation/QA multi-agent split, OpenBot
adopted as an optional AG-UI chat front end, plus two first-class goals added this
session — phase-lifecycle analytics/telemetry, and a provider-agnostic LLM backend
(Azure AI Foundry / Google Vertex / Anthropic / OpenAI).

User constraint set this session: usage is capped, so research runs single-stream (no
parallel subagents), and everything must be documented continuously — `CLAUDE.md` as
the living design + resume pointer, `research/` for per-track findings, this file as the
append-only activity log — so a fresh session can pick up cleanly after a usage-limit
reset without re-deriving context.

Created `CLAUDE.md`, `research/README.md` (7-track queue, A through G), and this log
file. Track A was inserted new this session, ahead of everything else: survey for
existing or forkable prior art before designing any piece of this from scratch.

Next: begin Track A research.

---

### 2026-09-17 — Track A complete: prior art surveyed

Checked (via `gh` CLI and web search, sequentially, no subagents):

- **Microsoft's GitHub Copilot upgrade agent family** — `dotnet/upgrade-assistant` →
  `dotnet/modernize-dotnet` (deprecated) → `microsoft/upgrade-agent-plugins` (current).
  Read the overview/FAQ/scenarios docs plus both repos' READMEs and LICENSE files
  directly. Functionally the closest match to our whole design (audit → plan →
  agentic upgrade → validate, skill-based knowledge packs auto-loaded by detected
  tech, plan file persisted in the repo, per-task git commits, aggregated
  duration/project-type telemetry) — but both repos ship under Microsoft's
  proprietary "Pre-Release Software License Terms" (2-year confidentiality clause,
  no fork/reuse rights), it's hard-locked to the GitHub Copilot subscription/model
  backend (fails our provider-agnostic requirement), requires internet/Copilot
  cloud infra, and is chat-session-interactive rather than unattended-by-design.
  Not usable as a base. Very useful as a feature checklist.
- **AppCAT** (Azure Migrate application and code assessment tool for .NET) — a
  standalone CLI + VS-extension static analyzer that emits JSON/CSV/HTML compatibility
  reports. Potentially usable as the engine *behind* our MCP audit skill (called, not
  forked) — license terms and exact JSON schema not yet verified, flagged as an open
  thread rather than settled.
- Did **not** yet check: whether a genuinely open-source pre-AI `dotnet-upgradeassistant`
  lineage survives independently, or generic open-source autonomous-coding-agent
  orchestration frameworks (OpenHands, SWE-agent, Aider) as a possible base for the
  coordinator/implementation/QA loop itself. Both flagged as open threads in
  `research/A-prior-art.md`, not blocking.

Verdict recorded in `research/A-prior-art.md`: no existing product/repo should be
adopted or forked wholesale; proceeding with our own harness design is justified.

Next: Track B (OpenBot computer runtime vs. .NET build/test workloads).

---

### 2026-09-17 — Track B complete: OpenBot computer runtime checked against real source

User said to keep going without stopping between tracks; usage cap is still the
constraint, so continuing single-stream with a checkpoint after each track (docs
updated immediately after every track, not batched at the end).

Read the actual OpenBot source via `gh api` (not just docs): `agent-computer/Dockerfile`,
the full `docker-compose.yml`, and `supervisor/src`'s file listing. Findings in
`research/B-openbot-computer-runtime.md`:

- `agent-computer`'s image is plain Ubuntu 24.04 + Bun + pinned Playwright — no conflict
  with adding a .NET SDK, and the image is swappable per-deployment via the
  `COMPUTER_IMAGE` env var the supervisor reads when creating each Bot's container. No
  fork needed.
- `/workspace` is a named volume by default; getting a real target repo into it is
  either a `git clone` via the Bot's own already-governed/audited shell capability, or a
  compose bind-mount override.
- Shell execution already flows through OpenBot's policy gateway + audit trail — the QA
  agent's real build/test runs get that audit trail for free, no new plumbing.
- One real, inherent limitation: this is a Linux container, so it can run
  `dotnet build`/`test` fine against a project already retargeted to net8.0+, but cannot
  build the *original* .NET Framework baseline (that needs Windows/full-framework
  MSBuild). Decided design stance: treat the pre-migration baseline as
  audit-file/static-analysis evidence only, not a live build, unless a Windows runner is
  separately available as an optional enhancement.
- This substantially de-risks the "might need to fork OpenBot" contingency noted in
  `CLAUDE.md` for the .NET-workload question specifically — looks like a config/custom-
  image exercise now, not a fork. (Note: this does not resolve every reason a fork might
  eventually be considered — just this one.)

**Reordered the queue**: while reading `docker-compose.yml` for this track, found
OpenBot already ships a working multi-provider LLM switch (`BOT_PROVIDER` across
openai/anthropic/google, plus an `OPENAI_BASE_URL` escape hatch for any OpenAI-API-
compatible endpoint) and a "harness picker" of twelve example agent-framework Bots each
declared `credential: "any-provider"`. This is squarely Track E's question, and the
findings were already in hand from files already open, so Track E is being pulled
forward ahead of C and D (cheaper than re-deriving the same reading later) — the
`research/README.md` status table reflects this reordering explicitly. C and D are still
pending, not skipped.

Next: finish Track E (multi-provider LLM backend), then return to C, then D.

---

### 2026-09-17 — Track E complete, then Track C complete

**Track E** (`research/E-llm-provider-backend.md`): confirmed via `agent-langgraph`'s
actual source (`model-key.ts`, `package.json`) that OpenBot's provider switch is
LangChain.js's own official per-provider adapter packages (`@langchain/openai`,
`@langchain/anthropic`, `@langchain/google-genai`) behind a `BOT_PROVIDER` env var, plus
an `OPENAI_BASE_URL` escape hatch already built for "any OpenAI-API-compatible
endpoint." Two non-reinventing paths recommended: (1, preferred) extend the same switch
with `azure` (via `AzureChatOpenAI`, already bundled in the already-installed
`@langchain/openai` package) and `vertex` (`@langchain/google-vertexai`, one new
official package) branches; (2, fallback) run a self-hosted LiteLLM proxy and point the
existing `OPENAI_BASE_URL` at it, requiring zero Bot code changes. Two open threads
flagged: LiteLLM's exact current license terms, and whether Azure AI Foundry's broader
model catalog needs a different LangChain integration than plain `AzureChatOpenAI`.

**Track C** (`research/C-agui-protocol-mechanics.md`): read `agent-langgraph/src/index.ts`
in full. Confirmed the AG-UI contract is small (one streamed-SSE HTTP endpoint,
`@ag-ui/core`/`@ag-ui/encoder`, both MIT and framework-agnostic) and genuinely pluggable
in any language, not OpenBot-specific. Two findings with direct design impact: (1) a Bot
process never executes its own tools — it calls back into OpenBot's own server carrying
an opaque signed "run assertion," and OpenBot's gateway is what actually resolves
policy/audit/execution against that Bot's sandboxed computer, which means our MCP
knowledge-pack skills need to be registered as OpenBot MCP plugins and granted per-Bot,
not called directly by our agent code; (2) AG-UI already distinguishes governed
"deployment tools" from frontend-rendered "surface tools" (a call to the latter ends the
run so a human can answer, and the answer comes back as the next run's input) — this is
exactly the mechanism to build our one approval gate on, no new plumbing needed. Two
open threads flagged: whether a Python AG-UI SDK exists (there's an
`agent-langgraph-agui` directory in the repo not yet opened that may answer this), and
whether the custom-MCP-server path in `/admin/plugins` is solid enough for our own
locally-run migration MCP.

Next: Track D (analytics/telemetry architecture) — OpenBot's own `desktop/TELEMETRY.md`
and `desktop/src/telemetry.ts` are already known to exist from the earlier repo-wide
"harness" search and look directly relevant; check those first before deciding on OTel
GenAI semantic conventions vs. something bespoke.

---

### 2026-09-17 — Track D complete, then F and G complete: all 7 research tracks done

**Track D** (`research/D-analytics-telemetry.md`): read `desktop/TELEMETRY.md` in full.
OpenBot's own desktop telemetry is a strong, directly-reusable pattern: a closed,
allowlisted event schema (Rust `EventData` enum, generated JSON schema, unknown
properties/enum values rejected outright), an explicit named denylist of what's never
accepted (no prompts, answers, credentials, file names, paths, hostnames, emails, model
names, YAML values, or custom URLs), anonymous random-UUID identity, local-first bounded
queue with non-blocking best-effort delivery, and respect for the `DO_NOT_TRACK=1`
convention. Delivery backend is PostHog (self-hostable). Web-searched OpenTelemetry's
GenAI semantic conventions to check current status: confirmed real and actively
developed (agent-lifecycle spans like `invoke_agent`/`execute_tool`/`plan`, moved to
their own repo in June 2026 for faster iteration) but every `gen_ai.*` attribute/span
still carries "Development," not "Stable," status as of mid-2026 — agent/tool-
orchestration conventions specifically called out as still settling. Recommendation:
our own closed allowlisted schema (modeled on OpenBot's) as the source of truth, OTel
`gen_ai.*` spans as an optional exporter only (not schema of record, since it's not
stable yet), PostHog as the reused option for an external sink.

**Track F** (`research/F-audit-to-graph-design.md`, a design synthesis, not an external
lookup): the MCP knowledge pack owns parameterized node *templates*; the harness's
graph-generation step is purely mechanical — group audit findings by category and
blast-radius (mirroring GitHub Copilot upgrade's real per-technology skill grouping
from Track A, not naive one-finding-one-node), instantiate templates into a concrete
run-specific `graph-instance.json` (same shape as the reference CopilotKit `index.json`),
and present the whole thing as one AG-UI surface-tool card at the approval gate (reusing
Track C's end-run-for-human-answer mechanism directly). Stock/fallback graph uses the
same mechanism with a default finding set when no audit file exists. Left the concrete
finding-taxonomy/JSON-shape question open, deliberately, pending which audit tool is
actually chosen (ties back to Track A's AppCAT open thread).

**Track G** (`research/G-trust-layer-reconciliation.md`, also a design synthesis): no
seam exists between OpenBot's gateway audit and our own integrity check, structurally,
because (per Track C) a Bot never touches its computer directly — every command our
agents run is already a governed, audited OpenBot action. The two systems answer
different questions (action-permitted-and-happened vs. approved-scope-held) and are
complementary. Recommended **replacing the bespoke file-hash baseline/audit store with
git itself** (commit-per-phase, diff against a start-of-run baseline commit) as the
primary integrity mechanism, since the target repo already has to live in the Bot's
`/workspace` as a real working copy (Track B) — closer to what GitHub Copilot's upgrade
agent actually does (Track A) than to CopilotKit onboarding's custom SHA store. Reserved
hash-based checking only for gitignored/credential paths git can't see. Flagged a real
(not structural) gap: OpenBot's own CEL policy could legitimately deny the read-only
git/hash commands our audit step needs, so the harness must fail closed on a denied
baseline check, and a deployment needs an explicit policy allowance for those specific
commands as a documented prerequisite.

**All 7 tracks (A–G) are now done.** `research/README.md`, `CLAUDE.md`'s decision log
and "Next action," and this log are all updated to reflect that the research phase is
complete. **Nothing has been implemented or built yet** — every track produced a
finding/recommendation, not code. The next session's job (per `CLAUDE.md`) is to read
all seven findings files and write the actual phased implementation plan, which has not
been started.

---

### 2026-09-18 — Implementation plan written

User asked to start the implementation plan. Wrote `IMPLEMENTATION-PLAN.md` at the repo
root, synthesizing all seven research findings into nine phases:

- **Phase 0** — environment stand-up (clean OpenBot clone, no fork, per every research
  track's conclusion).
- **Phase 1** — MCP knowledge pack: audit skill + node-template catalogue (Track F),
  starting with resolving Track A's open AppCAT license/schema question.
- **Phase 2** — mechanical graph-generation logic (category+blast-radius grouping,
  stock-graph fallback) — pure logic, no agent runtime needed to build/test it.
- **Phase 3** — provider-agnostic LLM backend: extend `agent-langgraph`'s existing
  switch with `azure`/`vertex` LangChain branches (Track E), proven against whichever
  credential is actually in hand.
- **Phase 4** — the actual multi-agent core: coordinator/implementer/QA as three AG-UI
  Bots built on `agent-langgraph`'s file layout, MCP registered as an OpenBot plugin,
  approval gate built on AG-UI's surface-tool/end-run mechanism (Track C).
- **Phase 5** — analytics: closed allowlisted local event schema modeled on OpenBot's
  own desktop telemetry (Track D), OTel/PostHog deferred as optional/additive.
- **Phase 6** — git-native integrity layer replacing a bespoke hash store (Track G):
  baseline via git status/stash, commit-per-phase, diff-against-baseline audits, fail
  closed on a denied policy check.
- **Phase 7** — custom `agent-computer` image with the .NET SDK (Track B), explicit
  acknowledgment that the pre-migration Framework baseline can't be built in this Linux
  container and should be surfaced honestly rather than glossed over.
- **Phase 8** — end-to-end validation against a real target repo, checking that every
  guardrail (scope violation, granular QA failure, friction report, analytics
  reconstruction) actually fires, not just the happy path.

Flagged four decisions up front that gate later phases but not Phase 0: audit-engine
choice (AppCAT vs. custom), which real repo to validate against, which LLM provider
credential is actually available right now, and confirming no OpenBot fork (assumed
"no," consistent with every research track). `CLAUDE.md`'s "Next action" now points at
starting Phase 0.

**Next: begin Phase 0** (environment stand-up) once the user confirms readiness to
move from planning into actual setup/build work.

---

### 2026-09-18 (earlier) — Design correction: Phase 4 wrongly made OpenBot load-bearing

User caught this directly: *"I thought we werent going to use openbot because it didnt
do what we wanted. last you said we were going to roll our own. what changed?"* Good
catch — nothing was supposed to change, but the implementation plan drifted.

Root cause: two separate "roll our own" decisions got conflated while writing Phase 4.
Track A's "roll our own" verdict was about *not* adopting Microsoft's proprietary
GitHub Copilot upgrade agent family — unrelated to OpenBot, which was separately and
explicitly agreed as the *optional* UI front end (message: "Lets bake it in just as you
said"). When Phase 4 was drafted, Track C's accurate finding that OpenBot's own shipped
`agent-bot`/`agent-langgraph` Bots proxy every tool call through OpenBot's gateway got
mistakenly applied as if it were a requirement for *any* AG-UI Bot — so the
coordinator/implementer/QA agents were designed to depend on OpenBot's gateway for
tool execution, MCP access, and the approval gate. That makes OpenBot required for the
core to function at all, contradicting the project's original, never-revoked
requirement (stated in `CLAUDE.md` from the first design conversation) that the harness
must run fully headless with OpenBot strictly optional.

Fixed, without waiting for further direction since the correction was unambiguous:
- Rewrote `IMPLEMENTATION-PLAN.md` Phase 4: coordinator/implementer/QA are now a
  standalone codebase that calls the MCP directly, runs its own git/shell/dotnet
  commands directly, and implements its own approval gate (CLI prompt by default, same
  pattern as the original CopilotKit onboarding CLI). OpenBot attachment is now clearly
  optional and additive — a "bring-your-own-agent" AG-UI endpoint (the `their-endpoint`
  mode already visible in OpenBot's own `HarnessPicker.tsx`) for chat/observability
  only, never the execution path.
- Adjusted Phase 6's note: git-native integrity is now the harness's *primary* trust
  boundary, not "complementary to OpenBot's gateway audit" — that framing only holds if
  OpenBot happens to be attached.
- Adjusted Phase 7: primary .NET execution environment is now the standalone harness's
  own container/environment; the `COMPUTER_IMAGE` customization from Track B is
  reframed as an option for the OpenBot-attached mode specifically, not the only path.
- Added addenda (not rewrites) to `research/C-agui-protocol-mechanics.md` and
  `research/G-trust-layer-reconciliation.md` flagging the scope correction, so those
  files stay accurate about what they actually found (the AG-UI wire mechanics are
  still correct) versus what got wrongly generalized from them.
- Logged the correction in `CLAUDE.md`'s decision log rather than silently editing past
  entries, per this project's own append-don't-rewrite convention.

Net effect: no research finding was wrong, and no new research is needed — this was a
synthesis error when going from findings to plan, now corrected. Phases 0–3, 5, and 8
are substantively unchanged.

---

### 2026-09-18 (later) — Independent Opus QA pass on the correction, then a second, larger correction round

User's reaction to the self-reported correction above: *"I dont like that you are
already saying that you conflated things. This needs to be spot on."* Launched a fresh
(non-fork) general-purpose agent, model `opus`, with an explicit read-only mandate:
independently re-verify the fix against OpenBot's actual server source rather than trust
our own research files' summaries, treating the "BYO agent doesn't need OpenBot's
gateway" claim as unverified inference until proven otherwise. Full prompt logged in the
conversation transcript; agent used a shallow clone of `CopilotKit/OpenBot@main`, `gh
api` against four repos plus two LICENSE files, the actual `dotnet-appcat` NuGet
license, three Microsoft Learn pages, and three fresh web searches — real investigation,
not a skim (196k tokens, 60 tool calls, ~9.5 minutes).

**Verdict on the core claim: confirmed true**, from source
(`server/src/agents/connection-test.ts`, `profile-store.ts`, `copilot.ts`) — a
bring-your-own AG-UI endpoint genuinely needs no token/callback/run-assertion, and the
gateway-proxy pattern is application code specific to `agent-langgraph`'s own example,
not an AG-UI or OpenBot-registration requirement. The architecture is sound.

**But found real problems anyway**, all now fixed across every affected file:
1. **The correction hadn't fully propagated.** `CLAUDE.md`'s "headline findings" and
   OpenBot-design sections still stated the pre-correction architecture as live fact,
   120 lines below the fix — the exact thing a cold-resumed session would read first and
   re-derive the same mistake from. Rewrote both sections plus added a new decision-log
   entry (not a rewrite of the old one).
2. **Three independent factual errors, unrelated to the architecture fix, each only
   findable by checking primary sources**: (a) .NET 8 reaches end-of-support
   2026-11-10 — the plan targeted it as the migration's output throughout; every
   `net8.0`/`dotnet-sdk-8.0` reference in `IMPLEMENTATION-PLAN.md` and
   `research/B-openbot-computer-runtime.md` corrected to "current LTS at build time, not
   hardcoded." (b) GitHub Copilot's upgrade agent is not actually model-locked (it has
   BYOK for Anthropic/Bedrock/Google AI Studio/Microsoft Foundry/OpenAI/xAI) — the
   proprietary license is the real, sufficient reason it can't be adopted; Track A's
   verdict survives, its stated reason didn't; corrected in `research/A-prior-art.md`,
   `CLAUDE.md`, and `IMPLEMENTATION-PLAN.md`'s open-threads list. (c) AppCAT — Phase 1's
   leading audit-engine candidate, deliberately left as an open thread rather than
   assumed — resolves against it: same proprietary, non-redistributable license family
   as the rejected Copilot products, confirmed via its actual NuGet license text.
   Decision 1 now points at a custom analyzer; `dotnet/try-convert` (MIT, archived, ~2.3
   years stale) noted as reference material, not a dependency.
3. **New findings about the optional OpenBot-attached path specifically** (none affect
   the standalone default): registering a locally-run harness needs
   `AGENT_ENDPOINT_ALLOWED_HOSTS` configured (OpenBot's SSRF guard refuses
   private/loopback endpoints by default); the whole coordinator/implementer/QA loop
   should register as **one** Bot, not three (OpenBot gives each *managed* Bot an
   isolated workspace volume, which would break a shared working copy across three); the
   approval card is a granted, fixed-schema component
   (`app/src/components/gallery/decisions.tsx`'s `askApproval`), not free-form — needs
   flattening the graph into it or a custom component.
4. **Track G's central argument needed retracting, not just softening.** Its original
   text opened with "Track C already establishes there is no seam, structurally" — in
   the corrected standalone design, the opposite is true (there *is* a seam by
   construction; the git-native mechanism is the only thing closing it). Struck the
   original claim visibly (kept, not deleted, per this project's convention) and
   rewrote the Verdict section accordingly, rather than letting the softer first-pass
   addendum stand next to an unretracted contradictory claim.

Files touched this round: `CLAUDE.md` (headline findings, OpenBot-design section, new
decision-log entry), `IMPLEMENTATION-PLAN.md` (Decisions, Phase 0, 1, 3, 4, 6, 7,
sequencing diagram, open threads), `research/A-prior-art.md`, `research/B-openbot-computer-runtime.md`,
`research/C-agui-protocol-mechanics.md` (second addendum), `research/D-analytics-telemetry.md`,
`research/F-audit-to-graph-design.md`, `research/G-trust-layer-reconciliation.md`. Every
edit followed this project's append/strike-don't-silently-erase convention — nothing was
deleted, superseded claims are visibly marked as such.

Two open items intentionally NOT resolved by this pass (unchanged, still open):
whether a generic open-source agent-orchestration framework (OpenHands/SWE-agent/Aider)
could underlie the coordinator loop itself (Track A open thread 2), and LiteLLM's
current license terms (Track E open thread) / PostHog's self-hosting footprint (Track D
open thread) — neither was in scope for this QA pass and neither blocks Phase 1 or 3.

**Next: begin Phase 1 or Phase 3** (both standalone, no OpenBot needed) once the user is
ready to move from planning into actual build work. Phase 0 (OpenBot stand-up) is now
explicitly optional and no longer a prerequisite for anything except the OpenBot-attached
exit criteria in later phases.

---

### 2026-09-18 (later still) — CopilotKit org survey, then FRD.md created as the primary spec

User asked to review `CopilotKit/harness-sdk` and the rest of the CopilotKit GitHub org
for anything reusable, explicitly requesting findings only — no changes until reviewed.
Checked directly against source (`gh api`, no guessing):

- **`CopilotKit/harness-sdk` is an unmodified fork of `strands-agents/harness-sdk`**
  (0 commits ahead, 194 behind) — AWS's "Strands Agents" SDK, not a CopilotKit-original
  product. Apache 2.0. Read its actual module layout: a real (non-stub) `litellm.py`
  model provider (covers Azure/Vertex via LiteLLM's model-id convention with no custom
  adapter code), plus `multiagent/` (`graph.py`, `swarm.py`, `a2a/`), `hooks/`,
  `interventions/`, `telemetry/` (`tracer.py`, `metrics.py`), and `sandbox/`
  (`docker.py`, `ssh.py`, `posix_shell.py`) modules. Confirmed OpenBot's own
  `agent-strands/src/main.py` bridges a Strands `Agent` to AG-UI in four lines via the
  official `ag_ui_strands` package ("which AG-UI maintains," per its own docstring) —
  dramatically simpler than the ~400 lines of hand-written AG-UI plumbing
  `agent-langgraph` uses, and with no gateway-proxy pattern in evidence.
- Surveyed the rest of the org (~90 non-fork repos via `gh repo list`, sorted by stars,
  checked the 5 most relevant directly): `aimock` (MIT, actively maintained — mocks
  LLM/MCP/AG-UI/vector-DB calls, useful for testing) and `pathfinder` (Elastic License
  2.0 — self-hosted MCP server for docs/code search, good architecture reference, not a
  redistributable dependency) were genuinely relevant. `open-mcp-client` (demo/starter
  only), `with-microsoft-agent-framework-dotnet` (archived, moved into the main
  CopilotKit monorepo), and `open-multi-agent-canvas` (requires CopilotKit Cloud) were
  not adopted as leads.
- Presented all of this to the user as findings only, per their instruction — no files
  changed during the research itself.

**User's follow-up**: park the Strands finding as a future research item rather than
act on it now, and — more significantly — generalize the project's direction away from
specific tools and toward a tool-agnostic specification. Asked directly: "Can we create
an FRD now?"

**Created `FRD.md`** — a functional requirements document, organized into AUDIT-*,
PLAN-*, EXEC-*, QA-*, APPROVAL-*, INTEGRITY-*, ESCALATE-*, PROVIDER-*, TELEMETRY-*,
ENV-*, UIATTACH-*, and KNOWLEDGE-* requirement groups, each independently testable and
silent on implementation, synthesized from everything learned across the journal, all
seven research tracks, and the corrected implementation plan. Includes system-level
acceptance criteria (§6), an explicit out-of-scope section (§7) naming that no specific
vendor product is required by the spec, a "Future research items" section (§8) carrying
forward the Strands finding plus the other still-open threads from research, and a
traceability section (§9) linking specific requirements back to the research findings
that motivated them.

**Repositioned the existing documents rather than replacing them**: `IMPLEMENTATION-PLAN.md`
now carries a note at its top identifying it as one candidate realization of the FRD,
needing re-validation against it before further build-out — not rewritten otherwise.
`CLAUDE.md`'s "Next action," decision log, and "Key references" updated to make `FRD.md`
the first thing a fresh session reads, ahead of the implementation plan.

**Next**: user's call — either evaluate the Strands Agents SDK future-research item
against `FRD.md` before committing to `IMPLEMENTATION-PLAN.md`'s current tool choices,
or proceed with the implementation plan as-is and revisit Strands later.

---

### 2026-09-18 (session close) — Session ending at 96% usage; full state checkpointed for resumption

User flagged the session was at 96% usage and asked to ensure everything is documented
before the limit resets. This is a clean, deliberate stopping point, not an interruption
mid-task — the last substantive exchange was the user asking "What do you recommend is
our next steps?" and receiving a three-part recommendation. **That recommendation was
given but not yet acted on or confirmed by the user** — this is the exact state a fresh
session needs to pick up from.

**The recommendation, now also written into `CLAUDE.md`'s "Next action" verbatim** so
it isn't lost to context/compaction:
1. Do a bounded evaluation of the Strands Agents SDK (`FRD.md` §8 item 1) against three
   specific open questions — .NET workload support in `sandbox/docker.py`, whether
   `interventions`/`hooks` satisfy the APPROVAL-* requirements' exact shape, and whether
   `telemetry`'s schema meets TELEMETRY-2's privacy bar — **before** investing further
   in `IMPLEMENTATION-PLAN.md` Phases 3–5, since Strands could replace most of that
   hand-built work if it holds up.
2. Start `IMPLEMENTATION-PLAN.md` Phase 1 (audit engine / knowledge source) in
   parallel — it's independent of the Strands question (only touches
   AUDIT-*/KNOWLEDGE-*).
3. Get two user-only decisions resolved: a real target repo to validate against, and
   which LLM provider credential is actually in hand.

**Full document state at session close**, for a fresh session's orientation:
- `CLAUDE.md` — living design doc + resume pointer. "Next action" section now contains
  the three-part recommendation above verbatim. Decision log runs through six
  2026-09-18 entries (the Phase 4 correction, the independent QA pass, the CopilotKit
  org survey, and the FRD creation) plus the four 2026-09-17 entries from the original
  research phase. Fully current as of this entry.
- `FRD.md` — the primary spec, tool-agnostic, 12 requirement groups (AUDIT/PLAN/EXEC/
  QA/APPROVAL/INTEGRITY/ESCALATE/PROVIDER/TELEMETRY/ENV/UIATTACH/KNOWLEDGE), acceptance
  criteria, out-of-scope section, §8 future research items (Strands SDK is item 1),
  §9 traceability to prior work. Created this session, not yet revised.
- `IMPLEMENTATION-PLAN.md` — repositioned as a candidate realization of the FRD (note
  at its top says so explicitly). Phases 0–8 all carry their 2026-09-18 correction notes
  from the independent QA pass (net10 not net8, standalone-not-OpenBot-gateway
  architecture, resolved AppCAT/Decision-1, etc.). Not yet re-validated against `FRD.md`
  requirement-by-requirement — that re-validation is implicitly what recommendation
  item 1 above would inform.
- `research/README.md` + all 7 files (A–G) — done, each with its 2026-09-18 correction
  addenda where applicable (A, B, C, D, F, G were all touched; E was not).
- `COPILOTKIT-ONBOARDING-JOURNAL.md` — untouched this session, still the original
  reference pattern document.
- This file (`logs/session-log.md`) — append-only, now ~13 dated entries covering the
  whole arc from project scaffolding through this close-out.

**Nothing has been built.** Every artifact in this project is a design/spec/research
document. The Strands Agents SDK evaluation (recommendation item 1) has not been
started — no repo has been cloned or tested for it beyond the read-only `gh api`
exploration already captured in the "CopilotKit org survey" entry above.

**To resume cold**: read `CLAUDE.md` in full, then `FRD.md` in full, then act on the
three-part recommendation in `CLAUDE.md`'s "Next action" (or check with the user first,
since it was a recommendation awaiting their confirmation, not yet agreed direction).
