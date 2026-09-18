# Research track index

Status values: `pending`, `in-progress`, `done`, `blocked`. Update this table and link
the findings file as soon as a track finishes. See `../CLAUDE.md` for the "Next action"
pointer, which is the actual resume marker.

| ID | Track | Status | Findings |
| -- | ----- | ------ | -------- |
| A | Prior art: does something already exist (or forkable) that does what we're building, in whole or part | done | [A-prior-art.md](A-prior-art.md) |
| B | OpenBot's "computer" runtime vs. real .NET build/test workloads | done | [B-openbot-computer-runtime.md](B-openbot-computer-runtime.md) |
| C | AG-UI protocol mechanics for bringing our own coordinator/implementation/QA agents in as coworkers | done | [C-agui-protocol-mechanics.md](C-agui-protocol-mechanics.md) |
| D | Analytics/telemetry architecture — what to reuse (e.g. OTel GenAI semantic conventions) vs. build | done | [D-analytics-telemetry.md](D-analytics-telemetry.md) |
| E | Provider-agnostic LLM backend — what existing abstraction to reuse (CopilotKit adapters, LangChain, Vercel AI SDK, LiteLLM) | done | [E-llm-provider-backend.md](E-llm-provider-backend.md) |
| F | Audit-file → dynamic phase-graph generation design | done | [F-audit-to-graph-design.md](F-audit-to-graph-design.md) |
| G | Reconciling the two trust layers (file-hash baseline vs. OpenBot's CEL policy/audit) | done | [G-trust-layer-reconciliation.md](G-trust-layer-reconciliation.md) |

**All 7 tracks complete as of 2026-09-17.** This research phase is done.

**Stale note, kept for history, corrected 2026-09-18**: the line that used to be here
said to move straight to writing the implementation plan. That happened
(`IMPLEMENTATION-PLAN.md`), got corrected twice (see `CLAUDE.md`'s decision log), and
has since been repositioned as a candidate realization of `FRD.md`, which is now the
primary spec. **For current status and next action, always defer to `CLAUDE.md`** — do
not treat this file's prose as current, only the status table above.

Order is sequential by design (usage-conscious — no parallel research subagents for this
project). Each track's findings file should end with a clear verdict/recommendation, not
just raw notes.
