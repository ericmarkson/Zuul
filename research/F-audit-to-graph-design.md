# Track F — Audit-file → dynamic phase-graph generation design

Status: **done** (design decision, synthesized from Tracks A/C and the journal — not an
external lookup track like A-E).

## Inputs this draws on

- The journal's Part 5: the real CopilotKit onboarding graph is `index.json` (a flat
  `prompts: [{ name, edges, milestone }]` array) plus one Markdown prompt file per node,
  with edges enforced by nobody but the calling agent's own good-faith reading of "if X,
  read Y next" text in each prompt body.
- Track A: GitHub Copilot's upgrade agent groups its 30+ built-in "skills" **by
  technology area** (EF6→EF Core, Newtonsoft.Json, Azure Functions, MVC/Web Forms,
  etc.), not by individual finding — real-world validation for category-level grouping
  as the right granularity, from a shipping product doing this exact job.
- Track C: AG-UI's split between governed "deployment tools" and frontend-rendered
  "surface tools," where a surface-tool call ends a run for a human to answer and the
  answer comes back as the next run's input — this is the mechanism the single approval
  gate is built on.

## Design

**Node templates, not node instances, are what the MCP knowledge pack owns.** The MCP
exposes a fixed catalogue of parameterized node templates — e.g.
`retarget-sdk-style-project`, `upgrade-incompatible-package`,
`replace-obsolete-api-usage`, `convert-config-transform`, `modernize-test-project` — each
a prompt fragment with placeholders (project name, package name, specific API, etc.) and
a declared `milestone` tag, exactly mirroring the shape `index.json` already uses. This
keeps the "MCP is the brain, dynamically controllable" property from the original design
intact: adding support for a new migration scenario means adding one template to the
knowledge pack, not touching the harness.

**The harness's graph-generation step is mechanical, not domain-aware**: given a
structured audit file (a list of findings, each with a category tag, severity, and
affected file/project references), it:
1. Groups findings by category — mirroring GitHub Copilot upgrade's per-technology
   skill grouping (Track A) rather than one node per individual finding, to avoid a
   combinatorial explosion of phases on a large codebase.
2. Instantiates one node per category-group from the matching MCP template, filling in
   the specific packages/APIs/files that category's findings named.
3. Emits a concrete, run-specific `graph-instance.json` (same `{name, edges, milestone}`
   shape as the reference graph) that the coordinator walks for this run only — nothing
   dynamic happens again mid-run; the graph is fully decided once, before the approval
   gate.
4. Falls back to a small, fixed **stock graph** (generic phases: SDK retarget → fix
   build errors → fix test failures → modernize flagged-but-uncategorized APIs →
   validate) when no audit file exists at all, using the same template mechanism with a
   default finding set rather than a structurally different code path.

**Grouping granularity is a deliberate middle ground, not either extreme**: pure
per-finding nodes give the best QA/retry isolation and audit resolution but risk
hundreds of trivial phases on a large legacy codebase; pure per-category nodes are
simple but blur partial failure (one failing package upgrade blocks the whole
category's node from reporting success). Recommend clustering **by category AND by
blast radius/dependency** — e.g., an EF6→EF Core migration touching many files stays one
node (it's not meaningfully separable), but two unrelated, independent package bumps
flagged under the same category get split into separate nodes if the audit data
distinguishes them cleanly. This mirrors the same tension the real GitHub Copilot
upgrade agent resolves by shipping curated, hand-written skills per technology rather
than fully mechanical one-finding-one-node generation — our MCP templates play that same
curatorial role.

**The approval gate presents the generated graph, not just a text plan**: by default
(standalone/headless) this is a CLI prompt — see `IMPLEMENTATION-PLAN.md`'s corrected
Phase 4. When OpenBot is optionally attached, the whole `graph-instance.json` (node
names, milestones, and a one-line summary per node, resolved from its template) can
*additionally* render as an AG-UI surface-tool/generative-UI card, reusing Track C's
finding that ending a run on a surface-tool call is how a human answers something.
**Correction (2026-09-18)**: that card is not free-form — Track C's second addendum
found OpenBot's shipped `askApproval` component takes a fixed schema
(`{title, summary, details:[{label,value}], approveLabel, rejectLabel}`) and must be
explicitly granted to a Bot. Presenting an N-node graph this way means flattening it
into that shape (most likely one `details` row per node) or shipping a custom gallery
component — real, small implementation work, not something to assume is automatic. The
run resumes only once that approval is present in the next run's input, exactly matching
the journal's "one approval gate, clearly announced as the
last one" principle.

## Open thread (not blocking, explicitly deferred to when an audit tool is chosen)

The concrete finding-category taxonomy and JSON shape depend on what actually produces
the audit file — our own MCP audit skill, a wrapped AppCAT run (Track A's open thread),
or both. This design intentionally stays agnostic to that shape (assumes only "a list of
categorizable findings," not a specific schema) so it isn't invalidated once Track A's
AppCAT-schema question is resolved.
