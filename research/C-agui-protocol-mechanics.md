# Track C — AG-UI protocol mechanics for bringing coordinator/implementation/QA in as coworkers

Status: **done**. **Addendum (2026-09-18) — important scope correction, read before
using this file's findings to design anything:** the "a Bot never executes its own
tools" finding below is an accurate description of how OpenBot's *own shipped, managed*
example Bots (`agent-bot`, `agent-langgraph`) choose to work — it is not a requirement
AG-UI itself imposes, and it is not true of a "bring your own agent" endpoint (the
`their-endpoint` credential type in `desktop/src/HarnessPicker.tsx`), which is free to
execute its own tools directly and simply stream AG-UI events for display. This
distinction was missed when `IMPLEMENTATION-PLAN.md`'s Phase 4 was first drafted,
wrongly making OpenBot's gateway load-bearing for our core harness; see that file's
Phase 4 correction note for the fix. The wire-protocol mechanics described below
(the `/ag-ui` streamed-SSE contract, `@ag-ui/core`/`@ag-ui/encoder`, the
deployment-tool/surface-tool split) remain accurate and still apply to our harness's
*optional* AG-UI endpoint — only the "who executes the tool" assumption needed
correcting.

**Second addendum (2026-09-18) — independently verified, plus three new findings.** A
separate Opus agent was tasked specifically with re-checking the claim above against
OpenBot's actual server source rather than trusting this summary. **Confirmed true**,
read directly from source: `server/src/agents/connection-test.ts` shows registration is
just "POST once, confirm an AG-UI event comes back" (no token, no callback, no
`/health`); `server/src/agents/profile-store.ts`'s `issueCallbackToken` is a separate,
explicit admin action never triggered by registration; `server/src/copilot.ts` states
outright, in its own comment, "A Bot at an endpoint runs its own loop." The
`MANAGED_AGENT_TOKEN`/`OPENBOT_TOOL_URL`/`callsTheSurface`-ends-the-run pattern is
confirmed to be application code specific to `agent-langgraph/src/index.ts`, not
anything the AG-UI packages or OpenBot's registration path require.

Three qualifications this second pass found, relevant only to the *optional*
OpenBot-attached path (none affect the standalone/headless design):
- **SSRF gate**: `server/src/agents/endpoint.ts` refuses to register a private/loopback
  endpoint by default; the README confirms `AGENT_ENDPOINT_ALLOWED_HOSTS` is required
  (exact host:port match, no wildcards) and that the blanket private-host allowance is
  itself refused under `NODE_ENV=production`. A locally-run harness needs this
  explicitly configured (or a tunnel) before it can be attached at all.
- **Remote Bots get strictly less than built-in ones**: `copilot.ts` shows a
  registered remote Bot is offered neither `message_bot` nor `ask_person`, and a
  person's standing instructions aren't forwarded to it — worth knowing if the
  OpenBot-attached mode ever wants those capabilities.
- **The approval card is a granted component with a fixed schema, not free-form**:
  `app/src/components/gallery/decisions.tsx`'s `askApproval` takes
  `{title, summary, details:[{label,value}], approveLabel, rejectLabel}` and must be
  explicitly granted to a Bot by an administrator. Rendering a whole `graph-instance.json`
  this way (Track F) means flattening it into that shape or shipping a custom gallery
  component — real, small work, not something to assume is free.

## What was checked

Read `agent-langgraph/src/index.ts` in full (the complete AG-UI server implementation
for OpenBot's LangGraph example Bot), plus `stream.ts`'s event-translation logic, and
confirmed `ag-ui-protocol/ag-ui` is the real upstream spec (MIT, ~16k stars, so it's a
genuinely standalone, framework-agnostic protocol rather than an OpenBot-only concept).

## Findings

**The contract a Bot must implement is small and precise:**
1. One HTTP endpoint (here, `POST /ag-ui`) that accepts a `RunAgentInput` JSON body
   (thread id, run id, messages, the caller's tool declarations, `forwardedProps`) and
   returns a **streamed SSE response** of typed AG-UI events:
   `RUN_STARTED` → some sequence of `TEXT_MESSAGE_START`/`_CONTENT`/`_END` and tool-call
   events → `RUN_FINISHED` (or `RUN_ERROR` on failure). `@ag-ui/core` + `@ag-ui/encoder`
   (both MIT, from the AG-UI project, not OpenBot-specific) provide the types and the
   SSE encoder — nothing bespoke to reimplement there.
2. A `/health` endpoint returning basic JSON status — used by Docker healthchecks, not
   part of the AG-UI spec itself, but a de facto OpenBot convention worth matching.
3. Auth via a shared bearer-style token (`MANAGED_AGENT_TOKEN`) the server sends and the
   Bot checks — simple, not part of AG-UI itself, an OpenBot-level convention for
   managed (server-registered) Bots specifically.

**Genuinely framework-agnostic, confirmed by the code's own comment**: "A Bot is a
registry row pointing at an AG-UI endpoint, so adding a framework does not require
server changes." The same contract is implemented independently by every one of
OpenBot's twelve example Bots (LangGraph, CrewAI, ADK, Pydantic AI, Mastra, etc.) —
confirming this is genuinely pluggable, not something only the shipped examples can do.
**Our coordinator/implementation/QA agents can be Python/LangGraph** (matching the
existing .NET agent's own stack from the journal) rather than TypeScript, as long as
something implements this same event-stream contract on the Python side — flagged as an
open thread below (whether an official Python AG-UI SDK exists, vs. hand-rolling the SSE
encoding, which is not hard but not zero effort either).

**The most important structural finding, with direct design implications**: *the Bot
process never executes its own tools.* When the model wants to call a tool, the Bot
process does **not** run it — it POSTs to `OPENBOT_TOOL_URL` (OpenBot's own server),
carrying an **opaque, signed "run assertion"** (`forwardedProps.openbotRun`) the Bot
cannot read or forge, and OpenBot's server is what actually resolves the tool, checks
policy, writes the audit row, and executes it against that Bot's sandboxed computer —
then hands the result back. This is *why* the gateway/audit model from the README holds
even for a fully custom framework Bot: governance lives entirely on the OpenBot side of
the wire, never trusted to the Bot's own process. Direct implication for our design:
**our MCP knowledge-pack skills need to be registered as MCP plugins in OpenBot's
`/admin/plugins` and granted per-Bot**, not called directly by our coordinator/
implementation code — the coordinator just declares/requests the tool the way any AG-UI
tool call works, and OpenBot's gateway is what actually reaches the MCP server. That
keeps MCP calls inside the same audit trail as everything else, which is exactly the
"stack the two trust layers" plan from the original design.

**A second structural finding, directly reusable for our one approval gate**: AG-UI
already distinguishes **"deployment tools"** (governed, executed server-side — shell,
file, MCP) from **"surface tools"** (drawn or answered by the *frontend* — generative UI
components, approval cards). A tool call naming something outside the Bot's own declared
`openbotDeploymentTools` set **ends the run** rather than executing anything, so the
frontend can render it and a human can answer — the next run then carries that answer as
input. **This is precisely the mechanism to build our single consolidated approval gate
on**: present the dynamically-built phase plan as a surface-tool/generative-UI card, end
the run, and only proceed to the next graph node once a resumed run carries the human's
approval in its input. No separate approval-gate plumbing needs inventing — it's the
same mechanism AG-UI already uses for every human-in-the-loop moment.

## Verdict

No fork, no reinvention needed for the wire protocol itself — `@ag-ui/core` /
`@ag-ui/encoder` (or a Python equivalent) plus a small HTTP server is genuinely all
that's required to become a coworker. The one real design commitment this creates: our
coordinator/implementation/QA agents must be **AG-UI servers that declare tools and let
OpenBot's gateway execute them**, not standalone processes that reach out to the MCP or
shell themselves — this is a constraint worth stating explicitly in the eventual
implementation plan, since it changes where the MCP client actually lives (OpenBot's
plugin system, not our agent code).

## Open threads (not blocking)

1. Whether an official Python AG-UI SDK/encoder exists (mirroring `@ag-ui/core` /
   `@ag-ui/encoder`) for a Python-based coordinator, or whether the SSE event encoding
   would need to be hand-implemented against the spec. `agent-langgraph-agui` (a
   *second*, differently-named LangGraph example directory in the repo, not yet opened)
   may already answer this — worth checking before assuming either way.
2. Whether OpenBot's `/admin/plugins` MCP integration passes through arbitrary custom
   MCP servers (the README said "custom servers must pass URL checks" for the general
   plugin system) cleanly enough for our own locally-run migration-knowledge MCP, or
   whether it's tuned mainly for the shipped catalogue (Google Drive, Notion, Composio).
