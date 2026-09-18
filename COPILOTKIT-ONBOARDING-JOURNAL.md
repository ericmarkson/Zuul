# CopilotKit Onboarding Journal

Notes on the CLI-driven agentic onboarding run happening in this repo, kept as a
reference for building something similar for other projects. Run id for this session:
`zKm0_r05_nkM`.

---

## Part 1 — What this run actually is

The `copilotkit@4.10.1 onboard` CLI acts as a **prompt graph**: it's not a script that
does the work itself, it's a state machine that hands the coding agent (me) one chunk of
instructions at a time via `onboard read <node>`. Each node is a Markdown prompt that ends
by telling the agent which node to read next, conditioned on what just happened. The CLI
(not the agent) holds ground truth about the run id, the protected-file baseline, proof
and classification state, telemetry checkpoints, and the gating logic that decides which
branch to take. The agent's job is to follow instructions, spawn subagents where told to,
and never assume it remembers the whole flow — it re-reads the graph at every step.

### The reusable architectural ideas

- **Run id threads everything.** One id (`zKm0_r05_nkM`) is attached to every command from
  the first `identify` call onward. Commands refuse to run without it once a run exists —
  this is what lets telemetry and state correlate across dozens of separate CLI
  invocations, and what lets a run resume cleanly if interrupted.

- **Identify, then gate on auth, before anything else.** The very first command just
  records which coding agent is driving (`onboard identify --coding-agent <slug>`). Then a
  streaming JSON-lines login check (`onboard login --json`) gates everything else — it
  only opens a browser if the session isn't already authenticated, and the agent waits on
  the *process*, not a fixed timer.

- **Read/route nodes instead of a static script.** `onboard read research/gather`,
  `onboard read credentials/plan`, `onboard read framework/langgraph-fastapi`, etc. each
  return instructions ending in an explicit "if X, read Y next" branch. Because the graph
  lives server-side (in the npm package), the flow's logic can be fixed or improved without
  redeploying anything the agent has memorized. **Addendum (confirmed empirically, see the
  final chronological entries):** `onboard read <node>` is *not* gated by prior recorded
  state at all — it answered fine even after this exact run had already routed to the
  `stopped/run-failed` ending node. Sequencing is enforced entirely by which node the
  calling agent chooses to read next, not by the CLI refusing out-of-order calls. The
  "graph" is a convention the agent follows, not a wall the server enforces.

- **Parallel read-only research subagents, each returning a structured status.** Two
  subagents gather "evidence packets" in parallel — one about the project (framework,
  frontend, CopilotKit wiring, auth boundaries), one about the environment (toolchains,
  ports, credentials present) — each required to cite file paths as evidence and to return
  a line starting `Status: passed|failed|blocked` so the orchestrator can gate on it
  programmatically instead of parsing prose.

- **Protected-path baseline before any writes.** `onboard protect` snapshots every
  changed/untracked file in the working tree with a digest, before any project file is
  touched. Two paths (`.env`, `.copilotkit/project.json`) are marked `deferred` — the only
  files the graph itself is allowed to write — and everything else becomes `protected`.
  Once the graph actually writes a deferred path, it gets re-baselined
  (`protect --rebaseline --path <path>`) and becomes protected too. This is what makes it
  safe to let an agent operate on a real, non-empty, already-in-progress repo.

- **Proof-gated routing, not self-reported routing.** Rather than asking the agent "does
  this already work?", the graph spawns a subagent that actually starts the dev servers
  and hits real endpoints (`GET /api/copilotkit/info`, a `copilotkit verify --round-trip`
  command) and classifies the project's starting state
  (`empty | agent-only | frontend-only | both | both-copilotkit-unproved | both-oss`) from
  *live* evidence, via six numbered predicates, so a failure or a skip can be reported by
  number rather than paraphrased.

- **Classify writes the decision back to the server.** `onboard classify
  --starting-state ... --agent-framework ... --frontend ...` records the decided path so
  every later step and all telemetry agree on what's happening. A bad/unlisted value is
  refused outright rather than silently accepted.

- **Documentation-grounded selection, not memory.** Every framework/frontend choice
  requires fetching the live CopilotKit docs pages for that exact combination (with a
  "retry a second way — `curl`, or the same URL without `.md` — before calling a page
  unavailable" policy) instead of answering from the model's pretrained knowledge of
  CopilotKit. A selection is only valid if a current doc page actually supports it.

- **Single-question wizard discipline.** Explicit rules throughout: ask one short question
  at a time, put the recommendation first with one sentence of evidence, never combine two
  separate decisions into one question, and — the big one — never ask a question the
  repository evidence already answers. The graph consistently prefers reading the repo over
  asking the human.

- **Checkpoints are telemetry, not control flow.** `onboard checkpoint --phase X` and
  `onboard proof --step X --outcome Y` report progress (gated by the developer's own CLI
  telemetry opt-in) but the run continues regardless of whether the report "sends." They
  are fire-and-forget observability, never a blocking dependency.

- **One approval gate, clearly announced as the last one.** Every developer-facing
  question (sign-in, a handful of setup questions, then the plan) is front-loaded into a
  single block. The graph explicitly tells the developer "this is the last thing I need
  from you, you can leave the run once you approve" — because nothing after that gate asks
  another question, and the steps after it are the longest in the run.

- **Credential handling as a first-class discipline.** Never read or print a secret value —
  only presence/non-empty/length checks. Never search outside the project directory for a
  stray credential (a key found that way bills/attributes to the wrong project). Ask the
  developer *where* a credential lives (a path) rather than *what* it is. Verify `.env` is
  actually git-ignored via `git check-ignore -q <path>` (asking git, since ignore rules can
  come from a parent or global excludes file, not just the local `.gitignore`) before ever
  writing to it.

- **An explicit stop/friction-report path.** Any phase that gets stuck has a defined
  fallback: `onboard friction --phase stop --category <slug>` with a fixed taxonomy
  (docs-missing, docs-wrong, cli-gap, sdk-gap, environment, port-collision, credential,
  validation-loop, other), one or two sentences of context, and a hard refusal if the
  report would carry secrets, logs, or source code.

---

## Chronological log of this specific run

1. `onboard identify --coding-agent claude-code` — registered this session with the run.
2. `onboard login --json` — already authenticated (`already_authenticated: true`), no
   browser opened.
3. `onboard read research/gather` — returned the research-phase instructions.
4. Spawned 2 parallel research subagents:
   - **Project evidence** → `Status: passed`. Found an existing, fully scaffolded
     LangGraph + Next.js CopilotKit starter; no real auth boundary (`identifyUser`
     hardcoded to a demo stub, all users share one thread history).
   - **Environment evidence** → `Status: passed`. Found npm (root) + uv (`agent/`)
     toolchains, all versions installed; and a **port mismatch**: root `.env` sets
     `AGENT_URL=http://localhost:8000`, but the Python agent actually listens on `8123`
     by default everywhere (`agent/main.py`, `agent/serve.py`, `entrypoint.sh`).
5. Browser-control preflight: no browser-automation tool live in this session. Registered
   one (`claude mcp add -s user playwright -- npx --yes @playwright/mcp@latest --browser
   chrome --isolated --output-dir <project>/.copilotkit/proof/browser`), told the
   developer in one line, re-probed — still not live in *this* running session (needs a
   restart) — recorded `unavailable` and carried on per the graph's own rule.
6. `onboard checkpoint --phase research-returned`.
7. `onboard read research/route` — merged findings; all three route predicates (agent
   present, frontend present, CopilotKit integration present) proved from the research
   packets, not from my own reading. Routed to baseline proof.
8. `onboard protect` — captured 39 paths as the protected baseline; `.env` and
   `.copilotkit/project.json` marked `deferred`.
9. `onboard read proof/oss-baseline` — returned the live-proof instructions.
10. Spawned 1 proof subagent: it started **both dev servers for real** (Next.js on :3000,
    Python agent on :8123) and ran the 6 predicates. Result: the project is **already
    running in Intelligence mode** — `/info` showed `licenseStatus: "valid"`,
    `runtimeEntitlements` populated, `mode: "intelligence"` — but the actual chat
    round-trip check (`verify --expect-runtime oss --round-trip --agent default --json`)
    failed: no answer was ever recorded on the thread, and the local agent's access log
    showed zero incoming requests for that round trip.
11. `onboard proof --step oss-baseline --outcome failed --predicate 3` — recorded that the
    live runtime already holds a working Intelligence client (predicate 3), so this
    evidence gets preserved into the plan rather than rebuilt.
12. `onboard read credentials/plan` — framework-selection instructions.
13. Selected **LangGraph FastAPI** (matches the existing agent's `add_langgraph_fastapi_endpoint`
    usage exactly) — preserved, not asked about. Fetched and validated 4 doc pages
    (quickstart, inspector, tool-based generative UI, agent/app context).
14. `onboard read frontend/plan` → selected **Next.js** (matches existing frontend) —
    preserved, not asked about. Fetched and validated the main quickstart doc.
15. `onboard read credentials/finalize-plan` — final classification + project-selection
    instructions.
16. `onboard classify --starting-state both-copilotkit-unproved --agent-framework
    langgraph-fastapi --frontend nextjs` — accepted.
17. `git check-ignore -q .env` → exit 0 — confirmed `.env` is git-ignored before touching
    credentials.
18. Reused the existing Intelligence project (slug `cpkerictest`, from
    `.copilotkit/project.json`) instead of minting a new one, since valid project fields
    and a non-empty `CPK_INTELLIGENCE_API_KEY` already existed.
19. Spawned a verification subagent to confirm `projectId`/`projectSlug`/`clerkOrgId`/
    `CPK_INTELLIGENCE_API_KEY` are all non-empty — **without ever printing their values** →
    `Status: passed`.
20. `onboard read credentials/settle-credentials` — Learning Container instructions.
21. Derived Learning Container id `cpkerictest` from the project slug (lowercase, hyphenate,
    trim — the exact same derivation `add-learning` uses later, so both stay in sync).
    `learning containers get cpkerictest --json` → `LEARNING_CONTAINER_NOT_FOUND` — normal
    first-run state; to be created *after* plan approval (a thread that already ran an
    agent can never get Learning assigned retroactively, so this has to happen before any
    real chat message).
22. `onboard checkpoint --phase container-surveyed`.
23. `onboard read credentials/write-plan` — final planning instructions. Fetched 3 more
    docs on Intelligence runtime wiring: the runtime **must** mount the full route subtree
    (`app/api/copilotkit/[[...slug]]/route.ts` exporting `GET`, `POST`, `PATCH`, `DELETE`,
    `useSingleEndpoint={false}`) — single-route mode would 404 the `/agent/:id/run` and
    `/agent/:id/connect` paths the Intelligence client actually calls.
24. Spawned a planning subagent to draft the implementation plan (full context: repo
    findings, selected framework/frontend, known port-mismatch bug, Intelligence-mode
    baseline, Learning Container status, protected-path list, all 8 fetched doc URLs).
25. Planning subagent returned `Status: passed`. Plan: preserve the existing LangGraph
    FastAPI + Next.js + OpenAI stack as-is — no re-architecture, no dependency upgrade
    (all `@copilotkit/*` packages already above the 1.70.0 floor) — and confirmed the
    Intelligence runtime wiring (`GET`/`POST`/`PATCH`/`DELETE` export, `useSingleEndpoint=
    false`, `CopilotKitIntelligence` construction) was already correct in `route.ts`. Four
    small planned changes: fix `.env`'s `AGENT_URL` (8000 → 8123), create Learning
    Container `cpkerictest`, wire `getLearningContainerId: () => "cpkerictest"` into the
    existing Intelligence client, add a `type-check` npm script. It also caught that
    `OPENAI_API_KEY` was actually **empty** in `.env` at that point — a real blocker
    independent of the plan, named as a required follow-up rather than fixed, since
    finding/placing credential *values* is out of scope for the CLI/agent.
26. Presented the plan summary to the developer for approval, explicitly flagging the empty
    `OPENAI_API_KEY`, and stated it was the last thing needed before the unattended build
    phase. Developer set the key themselves and approved: *"openai key is set - proceed."*
27. Post-approval sequence: `onboard audit` → `Status: passed` (37 protected paths
    unchanged, 2 deferred/unaudited) → `learning containers create --id cpkerictest --name
    cpkerictest --json` → succeeded, created project 4718's first Learning Container →
    `onboard checkpoint --phase container-settled` → `onboard checkpoint --phase
    plan-written`.
28. Spawned one implementation subagent with the full approved plan, told to implement all
    4 steps in order and run the full validation list (`npm run type-check`, restart the
    Next.js dev server to pick up the corrected `.env`, then `copilotkit verify
    --round-trip --agent default --expect-runtime intelligence --expect-learning-container
    cpkerictest --json`).
29. Implementation subagent returned `Status: failed`. All 4 approved changes were applied
    exactly as planned and confirmed via `git diff` — `.env`'s `AGENT_URL` (8000 → 8123),
    `getLearningContainerId: () => "cpkerictest"` added inside the existing
    `CopilotKitIntelligence` constructor in `route.ts`, and the `type-check` script in
    `package.json`. Nothing else touched; no protected path changed. Validation still
    failed on two fronts, both diagnosed as **pre-existing, out-of-scope defects**: (a)
    `npm run type-check` surfaced 2 TS errors in files this run never opened
    (`declarative-generative-ui/renderers.tsx`, `generative-ui/charts/bar-chart.tsx`); (b)
    `verify --round-trip` failed on `agent_answers` — root-caused to a pre-existing
    `mcpApps` entry in `route.ts` pointing at `https://mcp.excalidraw.com`, which now
    throws on an unexpected redirect during MCP tool discovery and aborts every agent run
    before the LangGraph agent is ever reached. Both dev servers were confirmed running
    (Next.js on :3000 restarted fresh, Python agent on :8123 untouched).
30. Per the graph's own **route-out rules** — a failure in code this run did not write
    takes the failure ending, not a repair attempt — this run did not touch the unrelated
    `mcpApps`/Excalidraw config, even though the fix would likely have been small. Read
    `onboard read stopped/run-failed`, then sent one friction report
    (`onboard friction --phase stop --category environment`, one sentence, no
    secrets/code/logs), and stopped without further repository changes. This is Part 2's
    "front-load one approval gate" and "don't trust self-reported state" principles working
    as designed in the failure case too: the run had explicit permission for exactly 4
    changes and declined to quietly expand that scope to chase a fix, even a plausible one.

**The CLI graph's run stopped here.** What's left behind: Next.js dev server on
`localhost:3000` (fresh restart) and the Python LangGraph agent on `localhost:8123` (never
restarted) both still running; exactly the 3 files above changed; the Excalidraw MCP config
defect is unfixed and needs a separate approved change (edit or remove the
`mcpApps.servers` entry in `route.ts`, or point it at a working endpoint) before a real
round trip can prove out.

*(Superseded below — the developer asked for this fixed manually as a one-off, outside the
CLI graph, and the round trip now proves out. See steps 31–32 and the final Live Run Log
entry.)*

31. The graph's own `stopped/run-failed` node is an ending, not a resume point — it names
    no retry path, only "report, say what's left running, stop." Since the developer
    explicitly asked to fix the `mcpApps` issue directly ("yes, go fix the mcpApps entry in
    route.ts"), this became a manual follow-up outside the CLI's scripted flow rather than a
    continuation of it. Diagnosis: `curl -v https://mcp.excalidraw.com` showed a `308
    Permanent Redirect` to `/mcp`; the runtime's internal MCP client (Node `fetch`) was
    refusing to follow that redirect, which is what threw `MCP tool discovery failed` and
    aborted every agent run before it reached the LangGraph agent. Fix: one-line change in
    `route.ts` — `mcpApps.servers[0].url` default from `"https://mcp.excalidraw.com"` to
    `"https://mcp.excalidraw.com/mcp"` (confirmed via curl: `/mcp` answers directly, `405`
    on `GET` with correct MCP CORS headers, no further redirect).
32. Re-running `verify --round-trip` surfaced a second, previously-hidden issue: the Python
    agent process had been running since *before* the developer set `OPENAI_API_KEY`, so it
    held a stale empty value in its own process environment (`.env` is loaded once at
    process startup via `python-dotenv`) — every model call failed with
    `openai.AuthenticationError: 401 you didn't provide an API key`. Not a config bug, just
    a stale running process. Fix: found the process tree via `Get-CimInstance Win32_Process`
    parent-chain lookup (uv launcher → reloader → worker), killed it with `taskkill /T /F`,
    started a fresh `uv run main.py`, which picked up the now-correct `.env`. Final `verify
    --round-trip --agent default --expect-runtime intelligence --expect-learning-container
    cpkerictest --json` came back **`"ok": true`** — every check passed, including
    `agent_answers` (a real answer, recorded on a new thread) and
    `learning_container_assigned` (thread carries Learning Container `cpkerictest`).
    `npm run type-check` re-run and confirmed unchanged: only the same 2 pre-existing,
    unrelated errors as before — no regressions from either fix. (Tried to record consent
    for the `route.ts` edit via `onboard protect --authorize --unplanned` — it reported
    `Status: blocked`, "not in this run's baseline," because `route.ts` was already an
    unmodified tracked file at baseline-capture time, never untracked/changed — expected and
    benign; `onboard audit` still passed cleanly afterward.)

**Net result: proven end-to-end.** A real chat message now gets a real, persisted answer
through the Intelligence platform, and the thread survives a reload — the actual goal of
this onboarding run. Both dev servers (Next.js `:3000`, fresh-restarted agent `:8123`) are
up and working.

*(Superseded below too — the developer then asked a sharper question: if the graph is fed
this success instead of the earlier failure, does it continue? See steps 33–36 and the
final Live Run Log entry for the answer and the formal close-out.)*

33. Tested empirically rather than answered from speculation: `onboard read
    proof/round-trip` was called directly, skipping straight past the earlier
    `stopped/run-failed` routing from step 30 — and it answered normally, no refusal. This
    is the finding now folded into the "Read/route nodes" bullet in Part 1 above: the CLI
    never actually enforced the stop as a technical wall. The real constraint the whole time
    was the agent's own decision to stop, not anything the server was gating.
34. Given that, the round-trip proof was formally recorded using the real evidence already
    in hand (no new subagent run needed): `onboard checkpoint --phase journey-attempted
    --attempt 1`, then `onboard proof --step round-trip --outcome passed`, then `onboard
    audit` → `Status: passed` (still 37 protected paths unchanged) before continuing.
35. That unlocked `onboard read proof/complete` — a real closing/handoff node: developer
    summary format (app URL, start command, process IDs, package versions, Learning
    Container explanation, which untracked paths are commit-worthy `.copilotkit/project.json`
    vs. regenerable tool output), a friction-reporting step, and a final `onboard complete
    --visual-check <performed|skipped-no-browser-tool|failed> --frontend-url <url>` call.
    Sent 3 friction reports (worst first, `onboard friction --category <slug>
    --cost-seconds <n>`, no `--phase stop` this time since the run wasn't stopping) —
    these map directly onto Part 3's three postmortem findings below: `environment`/600s
    (stale process caching an empty credential), `environment`/480s (unreachable mcpApps
    endpoint found too late), `cli-gap`/300s (no resume path existed from
    `stopped/run-failed`).
36. Ran `onboard complete --visual-check skipped-no-browser-tool --frontend-url
    http://localhost:3000`. Result: **blocked, not complete** — correctly so, since no
    browser tool was actually live this session to visually drive the app (the Playwright
    MCP server registered back in step 5 still needs a fresh session to activate). The
    command named exactly what a passing CLI round trip does *not* prove: realtime delivery
    to a browser over the gateway, browser-origin CORS/CSP, the frontend provider's live
    wiring, and generative UI actually rendering a component. It also printed the full
    node-by-node route this run walked, start to finish:

    ```
    authenticate/start,research/gather,subagent/inspect-repository,research/route,
    proof/oss-baseline,subagent/prove-oss-baseline,credentials/plan,
    framework/langgraph-fastapi,frontend/plan,frontend/nextjs,
    credentials/finalize-plan,credentials/settle-credentials,credentials/write-plan,
    subagent/create-plan,implementation/build-and-validate,
    subagent/implement-and-validate,stopped/run-failed,proof/round-trip,proof/complete
    ```

    Note `stopped/run-failed` sitting mid-route, not at the end — direct proof of step 33's
    finding: the run walked straight through a node documented as an ending and kept going.

**Final state handed to the developer:** app running at `localhost:3000` (Next.js, PID
`14424`) and `localhost:8123` (Python agent, reloader PID `23092`); Learning Container
`cpkerictest` created and will start collecting toward its first automatic Learning run once
15 new-thread conversations land in it; no `@copilotkit/*` version changes; two untracked,
git-visible paths named — `COPILOTKIT-ONBOARDING-JOURNAL.md` (developer's call whether to
commit) and `.copilotkit/project.json` (recommended to commit — it's declared project state,
not regenerable debris). **Overall status: round trip proven at the API/thread level; visual
browser proof still outstanding.** That's a legitimately incomplete-but-working state, not a
failure — the completion command said so itself.

*(Superseded below — a fresh session picked up the browser tool registered back in step 5,
and the developer asked to actually try the visual check. See steps 37–39 and the final Live
Run Log entry for the true end of the run.)*

37. A new session loaded the `mcp__playwright__*` tools from the Playwright MCP server
    registered in step 5 (which needed a session restart to activate — now it had one).
    Developer: *"now try."* Confirmed both dev servers were still up (`netstat` — PID
    `14424`:3000, PID `23092`:8123, unchanged since step 36) and spawned one proof subagent
    per the graph's own `subagent/prove-round-trip` node (fetched directly by that
    subagent), running the real 10-step procedure end to end this time.
38. Subagent result — `Status: passed`, every step:
    - Steps 1–5: pinned the request ("Show Engineering Salaries by month as a bar chart"),
      confirmed both processes are this project's own (not stale/stray), full `verify
      --json` wiring pass, `verify --round-trip --expect-learning-container cpkerictest`
      pass.
    - Step 5a: this journey publishes no frontend context to the agent (no
      `useCopilotReadable`/context hooks anywhere in `src/`) — correctly recorded as
      "shares no page data" rather than forcing a comparison that doesn't apply.
    - Step 5b: sent the pinned request straight to the runtime's `agent/default/run`
      endpoint carrying the frontend's real tool registrations (`barChart`, `pieChart`,
      `scheduleTime`, `toggleTheme`, read from `use-generative-ui-examples.tsx`). The
      agent called `query_data` then **`barChart`** — a name matching the frontend's own
      registration — with `{Jan: 42000, Feb: 42000, Mar: 48000}`, exactly matching
      `agent/src/db.csv`.
    - **Step 6a — the step that was blocked every prior attempt:** actually drove a real
      browser via the Playwright MCP tools. Navigated to `localhost:3000`, confirmed the
      chat surface present, read the console before typing (0 errors), typed the exact
      pinned request, waited for the turn to finish (not a timer — watched the stream
      settle and the chart render), screenshotted, re-read the console (still 0 new
      errors), checked the network tab (two successful `POST .../agent/default/run`
      calls, matching the `query_data` → `barChart` chain from step 5b). Outcome:
      **performed.** Evidence under `.copilotkit/proof/browser/` (page snapshots, console
      log, screenshot) and `.copilotkit/proof/` (the step 5b SSE/JSON captures).
    - Step 7: both the direct-API run (5b) and the real browser-rendered chart (6a) named
      exactly the three `db.csv` records and no others — grounding confirmed on both
      paths.
    - Step 8: not applicable (starting state `both-copilotkit-unproved`, not `both-oss`).
    - Step 9: the Skills install was correctly **skipped** — it would write into
      `.agents/skills` and link into `.claude/skills`, both on the protected-path list
      handed to the subagent, so it declined rather than writing anyway. The CopilotKit
      documentation MCP server *was* registered (`claude mcp add --transport sse
      copilotkit-mcp https://mcp.copilotkit.ai/sse`) — that's the coding agent's own
      config (`~/.claude.json`), not a repository file, but worth naming here since it's a
      change to the developer's Claude Code setup made outside this project.
39. `onboard audit` → still `Status: passed` (37 protected paths unchanged) →
    `onboard checkpoint --phase journey-attempted --attempt 2` → `onboard complete
    --visual-check performed --frontend-url http://localhost:3000`. Result:

    ```
    CopilotKit onboarding marked complete.
    onboarding_route: authenticate/start,research/gather,subagent/inspect-repository,
    research/route,proof/oss-baseline,subagent/prove-oss-baseline,credentials/plan,
    framework/langgraph-fastapi,frontend/plan,frontend/nextjs,credentials/finalize-plan,
    credentials/settle-credentials,credentials/write-plan,subagent/create-plan,
    implementation/build-and-validate,subagent/implement-and-validate,stopped/run-failed,
    proof/round-trip,proof/complete,subagent/prove-round-trip
    ```

    A genuinely different outcome from step 36's `blocked` result on the same command —
    the only thing that changed between the two calls was `--visual-check performed`
    actually being true this time instead of `skipped-no-browser-tool`.

**This is the true end of the run.** Round trip proven twice over — once via CLI evidence,
once via a live browser actually rendering the chart against real project data — with the
thread persisted and Learning-tagged. The developer's original goal (a chat message getting
a real answer whose history survives a reload, provable end to end) is demonstrated, not
argued.

---

## Part 2 — A generalized playbook for building this yourself

If you want this pattern for a personal project (not CopilotKit-specific), the reusable
recipe is:

1. **Design the graph as named nodes with explicit branches, not one giant prompt.** Each
   node should be small enough that an agent can act on it fully without losing the thread
   — a page of instructions ending in "if A do X, if B do Y," not a 50-step monolith.

2. **Put the graph behind a thin CLI (or a server the CLI calls), not in the agent's
   prompt.** The agent should only need to know "fetch the current node, follow it, fetch
   whatever it says to fetch next." That means you can fix or extend the flow later without
   ever touching the agent side.

3. **Mint a run id on the first call and require it on every call after.** This is what
   lets you correlate checkpoints/telemetry across many separate invocations and lets a run
   resume instead of restarting from scratch.

4. **Separate gather → decide → act into distinct phases.** Read-only research (parallel
   subagents are great here) feeds a routing decision; the decision feeds a written plan;
   the plan requires one explicit human approval before any file gets touched.

5. **Snapshot existing state before writing anything.** A protected-path baseline (digest
   every changed/untracked file) that every later write is checked against is what makes it
   safe to point an agent at someone's real, in-progress project instead of just a scaffold.

6. **Don't trust self-reported state — prove it live.** Where you can, actually start the
   process and hit the actual endpoint rather than asking the agent to infer success from
   reading source. Source code tells you what *should* happen; a running process tells you
   what does.

7. **Front-load every question into one approval gate, and say so explicitly.** Collect
   sign-in, setup choices, and the plan itself into one block, then tell the human clearly
   that nothing after this point needs them — this is what lets the long build/prove phase
   actually run unattended instead of stalling on an assumed check-in.

8. **Treat credential handling as a first-class discipline, not an afterthought.** Never
   let the agent read or print a secret value — presence/length only. Never let it search
   outside the project for a stray credential. Ask "where does this live" (a path) instead
   of "what is this" (a value). Verify secret-bearing files are actually git-ignored
   (ask git, don't parse `.gitignore` yourself) before the first write.

9. **Build an explicit stop/report path with a fixed failure taxonomy.** When a run gets
   stuck, it should leave behind a short, structured, secret-free signal (phase + category
   + one sentence) rather than either failing silently or dumping raw logs/output.

10. **Keep a durable, append-only log as you build it.** Exactly this file — one entry per
    session/step, so decisions and gotchas accumulate across conversations instead of
    living only in a chat transcript that eventually gets summarized away.

---

## Part 3 — Postmortem: where this run's own graph fell short, generalized

This isn't app-specific debugging — it's what broke in the *pattern* (Part 1's
architecture), written up so a version of this built for another project can design the
gap away up front instead of discovering it live.

**1. Long-lived processes started before credentials were finalized went stale.**
`proof/oss-baseline` explicitly allows starting dev processes during read-only proof —
well before `credentials/settle-credentials` ever runs. The Python agent process was
started that early; `OPENAI_API_KEY` was only set much later, mid-run. When `.env` finally
changed, the implementation subagent restarted Next.js because it *knew* `AGENT_URL` had
changed and Next.js needed it — but reasoned "the Python agent doesn't need restarting,
`AGENT_URL` is Next.js-only," which was true for that one variable and blind to the fact
that the same `.env` also held `OPENAI_API_KEY`, which the Python process had cached as
empty since its stale startup. Round-trip proof then failed with a `401
AuthenticationError` buried in a Python stack trace — a confusing shape for what was really
just a stale process.
Generalizable: any system that starts long-lived processes early for live proof, and
collects credentials incrementally afterward, will eventually have a process holding a
stale/incomplete environment snapshot — and reasoning "restart the one process whose one
known-changed variable I'm fixing" will miss other variables in the same file that other
processes also depend on.
*Fix as our own onboarding step:* right before the final proof step (not earlier),
unconditionally recycle every long-lived process this run started or found running that
reads from a credential file — scope the restart to "this file changed since the process
started," not to "the one variable I know changed."

**2. A broken external dependency surfaced only deep into implementation, not during research.**
`route.ts`'s pre-existing `mcpApps.servers` config pointed at `https://mcp.excalidraw.com`
— unrelated to this run, that endpoint now 308-redirects to `/mcp`, and Node's `fetch`
refuses to follow it. Research recorded that the config *existed*, never that the service
it names was actually *reachable*. It surfaced only after a full plan was written,
approved, and implemented — as a cryptic "MCP tool discovery failed" in a dev log — at
which point the graph correctly refused to fix code it didn't write and hard-stopped via
`stopped/run-failed`, pushing the diagnosis entirely onto the developer.
Generalizable: any research phase that records "this integration exists" without also
recording "and it currently responds" lets pre-existing external breakage survive to the
most expensive possible point to diagnose it — after a full implement-and-validate cycle,
looking like something the run itself broke.
*Fix as our own onboarding step:* during read-only research, cheaply probe (HEAD/GET,
follow redirects, check status) every external URL found in the project's own config —
webhooks, third-party APIs, MCP servers, callback URLs — and record it as a finding ("this
pre-existing integration currently returns 308") surfaced at plan-approval time, so the
developer can choose to fix it in the same approved plan instead of hitting it blind at the
end.

**3. No re-entry path once the graph stops — recovery falls entirely outside the system.**
The route-out rules correctly refuse to let the agent silently expand scope onto code it
didn't write, and `stopped/run-failed` is documented as an ending, not a recovery point (it
names no retry branch). The actual fix — the `/mcp` URL correction and the stale-process
restart — happened entirely outside the CLI graph, as manual debugging the developer had to
explicitly request in plain conversation. The graph's own state (baseline, run id,
checkpoints) had no way to represent "developer approved one small incremental fix": when
that fix landed, `onboard protect --authorize --unplanned` was tried against it and refused
(`Status: blocked`, "not in this run's baseline") — the file had never been tracked by the
baseline system to begin with.
Generalizable: a safety rule good at refusing *unscoped* changes but with no matching
mechanism for developer-approved *scoped* recovery forces every recoverable failure into
"fall out of the system, debug by hand, hope you remember to log it" — which throws away
all the state/tracking machinery the run spent the whole session building.
*Fix as our own onboarding step:* add a narrow scope-expansion command (e.g. `onboard
expand-plan --path <path> --reason "<what the developer approved>"`) that lets a stopped
run record one specific developer-approved incremental change, re-enter
implementation/validation for just that change, and continue on to the final proof
automatically — same safety property (developer must explicitly approve anything outside
the original plan), no cliff where recovery means leaving the tracked system entirely.

*Addendum, discovered afterward:* the "no re-entry path" framing above is slightly too
generous to the CLI. Once the manual fix was in and genuinely working, asking "what happens
if we feed the graph success instead of failure?" and actually testing it showed
`onboard read` was never gated by the recorded stop at all — see Part 1's "Read/route
nodes" bullet and the final chronological entries. So the real gap wasn't missing
CLI-enforced machinery for scoped recovery; it was that the *agent* (correctly, per its own
safety rules) treated a documented ending node as a hard wall and stopped narrating forward,
when the underlying system would have let it keep walking the graph the whole time. The
`expand-plan`-style fix above is still worth building — it would make the re-entry
*legible and audited* instead of "nothing stopped you, so just call read again" — but the
constraint that made this feel unrecoverable was narrative, not technical.

Ties back to Part 2: this is playbook steps 6 ("prove things live") and 9 ("structured
stop/report") interacting badly. Proving things live means starting stateful processes and
probing external services *early*; the credential-collection and scope-safety machinery
only fully knows what's needed *late*. A system built this way should design explicitly for
re-proving/re-probing right before the final gate, not trust that an early proof still
holds by the time you get there.

---

## Part 4 — How the graph checked its own work (evals and verification mechanisms)

Part 2 is the playbook for *building* a system like this; this is its counterpart for
*trusting* one — the concrete mechanisms that kept this graph from ever accepting a claim
of success just because something asserted it.

**1. A mandatory status vocabulary everywhere.** Every subagent and CLI check had to open
with `Status: passed/failed/blocked`, plus a distinct three-way surface-check outcome
(`performed/skipped/failed`). This is what let the orchestrating agent route
programmatically instead of interpreting prose, and it kept "skipped" (legitimately
couldn't check) structurally separate from "failed" (checked and found a problem) —
evidenced by `onboard complete --visual-check skipped-no-browser-tool` being treated as a
distinct, honest outcome rather than a failure, throughout this run's middle phase.

**2. Granular, itemized checks instead of one boolean.** `verify --json` never returns a
single `"ok": true` — it returns an array of roughly a dozen independently-named checks
(`api_key_authenticates`, `intelligence_consumed`, `runtime_agents_declared`,
`frontend_assets_served`, `intelligence_thread_routes`, etc.), each with its own
pass/fail/undetermined. The round-trip proof instructions explicitly rank
`intelligence_consumed` (proves the credential is actually *used* by the runtime) above
`api_key_authenticates` (proves only that the credential is *valid*) — a single aggregate
check would have missed that distinction entirely, and this project's first proof attempt
genuinely needed that granularity to diagnose the real problem (a stale process, not a bad
key).

**3. Proof over self-report, at every layer.** The baseline-proof phase never asked "does
this look like it works" — it started the real dev servers and hit real endpoints
(`/info`, `verify --round-trip`). The round-trip phase never trusted that a POST returned
200 — it read the answer back off the persisted thread via the platform's own read path.
Step 3 of the round-trip proof goes further: before trusting an agent's answer, confirm
the *process* that answered is actually this repository's own agent, not a stale process
or another project's server squatting on the same port — a passing health check is
explicitly insufficient.

**4. A dedicated grounding/fabrication check (Step 7), separate from a wiring check.**
Compares the agent's actual claims against the project's real data, field by field. The
instructions are explicit that a well-rendered card citing numbers the project doesn't
have is a FAILED proof, not a near-pass, because it looks identical to a correct one in a
screenshot or a video. This is the sharpest defense against a plausible-looking false
positive, and it was exercised for real in this run: both the direct API call (step 5b)
and the live browser turn (step 6a) were checked against `agent/src/db.csv` and matched
exactly — Jan/Feb/Mar 42000/42000/48000, no invented months or categories.

**5. Explicit, honest acknowledgment of what one proof method cannot cover.** The
round-trip instructions state outright that a CLI round trip proves an agent answers but
does NOT prove realtime browser delivery, browser-origin CORS/CSP, or a component actually
rendering — so a live browser step was made mandatory for genuine completion, not optional
polish. This was directly observed: `onboard complete --visual-check
skipped-no-browser-tool` refused to mark the run complete even though every CLI check had
passed, and printed exactly which of those four things remained unverified. Only the later
live browser drive (step 6a, `performed`) flipped the same command to a genuine "CopilotKit
onboarding marked complete."

**6. Protected-path audits as a trust boundary, not a vibe check.** Every phase re-ran a
digest comparison against a baseline captured before any writes. The attribution rule was
strict: a changed path counts as "this run's own work" only if it appears in an actual
subagent's reported "Files changed" section — the instructions explicitly say that
recognizing the code, or believing you know what wrote it, is not evidence; only a
collected Files-changed section is.

**7. Bounded retries instead of infinite optimism.** Repair cycles were capped at three
attempts before the graph forced a route-out to a stop/report state, preventing a stuck
check from being retried forever while quietly never resolving — and forcing an honest
"this didn't work" report instead.

The net effect across all seven: nothing in this graph got to claim success by asserting
it — every claim had to point at a specific command's output, a specific file, or a
specific browser observation — and the final completion gate (`onboard complete`)
independently re-derived its own verdict from that evidence rather than accepting any
subagent's self-reported `Status: passed` at face value. This run's own arc proved the
point: `onboard complete` was run twice with genuinely different, evidence-driven outcomes
(`blocked`, then `complete`) from the same command against the same project, purely
because the underlying evidence changed between the two calls.

---

## Part 5 — What the graph actually is, from the real source

Parts 1-4 were inferred from watching the graph behave. This section is different in kind:
it's sourced from reading the actual installed CLI package, not inferred from behavior.

**Correction first.** The graph does not live in the `CopilotKit/CopilotKit` repo initially
assumed. `npm view copilotkit repository` points at a separate repo: `CopilotKit/Intelligence`,
directory `apps/cli`. Confirmed by reading the real installed package — every
`npx --yes copilotkit@4.10.1` call this run made left it sitting in the local npm cache at
`_npx/<hash>/node_modules/copilotkit/`, so this is the exact code that ran, not a guess from
browsing GitHub.

**1. The graph's on-disk shape.** Inside the package: `onboarding/index.json` (the whole
graph as one JSON manifest) plus `onboarding/prompts/<node-path>.md` (one markdown file per
node, ~70 files, matching every node name used throughout this run —
`authenticate/start.md`, `research/gather.md`, `framework/langgraph-fastapi.md`, etc.).
`index.json`: a `graphTree` field (a 40-char hex hash identifying this exact graph version —
the same value that showed up as `onboarding_graph_tree` in the very first message that
kicked off this whole run), a `root` field (`authenticate/start`, where a bare `onboard
start` begins), an `intentRoots` map (named entry points like `add-channels` →
`feature/channels/start`, for feature-add flows), and a `prompts` array where each entry is
`{ name, edges: string[], milestone: string }`. No engine, no DSL — a flat JSON list plus a
folder of markdown files.

**2. The single most important finding: edges are not enforced.** Read directly from
`apps/cli/src/commands/onboard.ts`, the `read` subcommand handler is exactly: parse the
prompt name argument, call `printPrompt(deps, requireBoundRun(...), promptName)`. That
resolves through `apps/cli/src/services/onboarding-graph.ts`'s `loadOnboardingPrompt`, which
does `index.prompts.find(p => p.name === name)` — a flat lookup by name against the whole
array, with no check that `name` is among the `edges` of whatever node was read previously.
This is the exact mechanism behind what this run proved empirically earlier: `onboard read
proof/round-trip` worked immediately after the run had already routed to
`stopped/run-failed`, no refusal. The `edges` field is documentation the prompts' own "if X,
read Y next" text relies on — consumed by the calling LLM agent, not enforced by the CLI.
The graph is real, but its enforcement is entirely the calling agent's good-faith compliance
with plain-English instructions in each prompt's body.

**3. Where state actually lives.** `apps/cli/src/services/onboarding-state.ts` — a local
key-value store, namespaced per-project by
`stateKey(namespace, root) = "onboarding." + namespace + "." + sha256(root)`, where `root`
is the resolved repository root path. Stored there, entirely client-side, not server state:
the bound run id + intent (`startOnboardingRun`/`readOnboardingRunId`), the run's `route` —
an append-only array of every prompt name ever read via `recordServedPrompt`, called on
every single `read` call — this is literally the mechanism producing the `onboarding_route`
trail printed at the end of `onboard complete` (the one that showed `stopped/run-failed`
sitting mid-path in an otherwise-continuing route), per-step proof outcomes
(`recordProofOutcome`/`readProofOutcome`), and the identified coding agent. All of it lives
in a local store on the developer's own machine — separate telemetry events go to
CopilotKit's analytics backend (gated by CLI telemetry opt-in), but the graph position and
route history are pure local bookkeeping, not anything server-authoritative.

**4. Two genuinely different trust models coexist in the same CLI — the most important
nuance to carry forward.**

- *Cryptographically verified (protect/audit):* `apps/cli/src/services/onboarding-protected-paths.ts`
  really walks the entire repo tree (`deriveProjectFiles`, skipping a denylist of
  directories) and SHA-hashes every file (`createHash7`) at baseline capture
  (`captureProtectedPaths`), then re-hashes and compares at audit time
  (`auditProtectedPaths`). Env-file credential *names* (not values) are tracked the same way
  via `envKeysOf`/`lostCredentials`, so a lost credential is independently detectable
  without ever reading a secret value. This layer does not trust any self-report — it
  checks bytes.

- *Purely self-reported (proof/checkpoint/visual-check/friction):* read directly from
  `onboard.ts`'s `completionReport` function:
  ```js
  function completionReport(input) {
    if (input.check.outcome !== "performed") return blockedWithoutSurfaceProof(input.check);
    return input.blocker === void 0 ? "CopilotKit onboarding marked complete.\n" : blockedAfterProof(input.blocker);
  }
  ```
  That is the entire mechanism deciding "blocked" vs "CopilotKit onboarding marked
  complete." — a string comparison against whatever `--visual-check` value the calling agent
  passed on the command line. The CLI never independently confirms a browser actually ran;
  it only records what it's told, the same way `onboard proof --step X --outcome passed`
  just records the outcome string handed to it (`recordProofOutcome`, no verification). The
  realism of this system's "evals" comes entirely from the prompt text being extremely
  explicit and paranoid ("never report a result you did not see," "a rendered result is not
  proof yet, record this step's outcome after step 7 has compared") — not from the CLI
  double-checking the agent's honesty. The one place independent verification actually
  happens is the separate `verify` command (`round-trip-checks.ts`, `round-trip-probe.ts`,
  `verify-checks.ts`, `verify-probes.ts`) — it makes real HTTP calls against the running
  app. That command is the hard-evidence layer the soft self-reported completion layer is
  supposed to be built on top of.

**5. A third category worth naming: friction report sanitization.**
`apps/cli/src/services/onboarding-report-text.ts` —
`reviewReportText`/`detectSecretShape`/`hasHighEntropyRun` actually inspect friction report
text for secret-shaped strings, code fences, excessive length/newlines, and refuse the
submission if found (this is why every friction report this run sent had to avoid quoting
code or logs verbatim). Real enforcement, not self-report, sitting right next to the
purely-trusted proof/completion layer — neither "hashes everything" nor "trusts everything,"
but "pattern-matches the text for obviously dangerous shapes."

**6. How to replicate this for a personal project — a concrete build recipe, distinct from
Part 2's more abstract playbook.**
1. Write the graph as markdown files plus a JSON index in exactly this shape — nodes with
   `name`, `edges` (documentation only, not enforced), a `milestone` tag, and file content
   ending in explicit "if X, read Y next" branches for the agent to follow.
2. Build a minimal CLI with a handful of commands: `start` (mint + locally store a run id,
   keyed by a hash of the project path — the `conf` npm package does the local key-value
   store in a handful of lines), `read <name>` (a flat lookup, no edge enforcement needed —
   don't bother building that), and optionally `checkpoint`/`proof`/`friction` only if a
   local audit trail or telemetry matters to you.
3. Don't spend effort making `read` enforce edges — the real system doesn't either. Put that
   effort into the prompt text instead: explicit, paranoid, "never claim what you didn't
   see" language, since that is where essentially all of the real system's sequencing
   discipline actually lives.
4. Build exactly one real, independently-verified layer — actual HTTP calls, actual file
   hashing, actual process identity checks — separate from the graph's bookkeeping (mirrors
   this project's `verify` command). This is the one piece worth engineering carefully,
   because every soft/self-reported claim in the system is trust resting on top of whatever
   this layer actually proves.
5. If avoiding clobbering a developer's existing files matters, steal the protect/audit
   pattern directly: hash the repo tree before any writes, hash again after, and require
   every "Files changed" claim from a subagent to be checked against that diff rather than
   trusted at face value — this is the one part of the completion story that should not be
   self-reported, per finding #4 above.
6. Ship it as a plain npm package (or any distributable) — the prompts are just files
   bundled alongside a small CLI binary. Nothing exotic; genuinely buildable by one person.

---

## Live Run Log

Append new dated entries below as the CopilotKit onboarding run continues in this
conversation.

### 2026-09-16 — Journal created, plan still in flight

Run `zKm0_r05_nkM` reached step 23/24 above (planning subagent dispatched to draft the
implementation plan) when this journal file was created. Known open items going into the
plan: fix `.env`'s `AGENT_URL` (8000 → 8123), confirm `route.ts` exports all four HTTP
verbs, create the Learning Container `cpkerictest` post-approval, and actually prove a
real chat round trip (Intelligence auth already works; an agent answer reaching the thread
does not, yet).

### 2026-09-16 — Plan approved, implementation running

Plan came back clean: almost everything already works, only 4 small changes needed (see
step 25 above), plus one real blocker the plan surfaced — `OPENAI_API_KEY` was empty. That
was flagged to the developer directly rather than guessed at or worked around. Developer
filled it in and approved in one message. `onboard audit` confirmed nothing drifted since
the baseline before implementation started. Learning Container `cpkerictest` now exists
(project 4718's first). One implementation subagent is now applying the 4 plan steps and
running the validation chain (`type-check` → dev server restart → `verify --round-trip
--expect-runtime intelligence --expect-learning-container cpkerictest`). This entry was
written proactively while waiting on that subagent, per the developer's standing request to
keep this journal current during idle background-agent waits rather than only when asked.
Next entry will record its `Files changed` and whether the round-trip finally proves out.

### 2026-09-16 — Run stopped: implementation clean, round trip blocked by a pre-existing bug

Implementation subagent applied all 4 approved changes correctly (verified via `git diff`)
and nothing else — no protected paths, no unapproved files. Validation still failed:
`type-check` hit 2 pre-existing TS errors in untouched files, and `verify --round-trip`
failed on `agent_answers` because a pre-existing `mcpApps` entry in `route.ts` points at
`https://mcp.excalidraw.com`, which now redirects in a way Node's `fetch` refuses to
follow — that throws during MCP tool discovery and kills every agent run before it reaches
the LangGraph agent, regardless of the port fix. Since the failing code predates this run
and lies outside the 4 approved changes, the graph's route-out rules applied: no repair
attempt, no scope expansion — read `stopped/run-failed`, filed one friction report
(`category: environment`), and stopped clean. Both dev servers (Next.js :3000, agent :8123)
are left running; the 3 changed files are exactly the 3 approved ones. The Excalidraw MCP
config was the next thing to fix, as its own separately-approved change, before a real chat
round trip (and thread persistence) could be proven. *(Superseded — see the next entry:
the developer asked for that fix directly, and it's done.)*

### 2026-09-16 — Fixed manually, round trip proven end-to-end

Developer: *"yes, go fix the mcpApps entry in route.ts."* Since the CLI graph's
`stopped/run-failed` node is an ending with no resume path (confirmed by reading it), this
was a manual fix outside the scripted flow, not a graph continuation. Root cause:
`mcp.excalidraw.com` now 308-redirects `/` → `/mcp`, and the runtime's MCP client refuses to
follow it — one-line fix to the hardcoded default URL. Re-running `verify --round-trip`
after that exposed a second, unrelated issue: the Python agent process had been running
since before `OPENAI_API_KEY` was set, so it was holding a stale empty value — killed the
stale process tree and restarted it fresh. Final `verify --round-trip
--expect-runtime intelligence --expect-learning-container cpkerictest --json` →
**`"ok": true"`, every check passing**, including `agent_answers` and
`learning_container_assigned`. `type-check` re-confirmed unchanged (same 2 pre-existing,
unrelated errors, no regressions). See steps 31–32 above for full detail. *(Superseded by
the next entry — the round trip worked, but formal completion turned out to need one more
question and one more step.)*

### 2026-09-16 — Formally closed out: blocked on visual proof, not a failure

Developer asked the sharp question this whole arc was building toward: now that the round
trip genuinely works, what happens if the graph is fed that success instead of the earlier
failure — does it continue? Tested directly rather than guessed: `onboard read
proof/round-trip` was called right after the earlier `stopped/run-failed` routing, with no
refusal. That's the real finding — the CLI's `read` commands were never gated by recorded
run state at all; see the addendum on Part 3's third postmortem finding and the new
"Read/route nodes" addendum in Part 1.

Recorded the real passing evidence (`onboard proof --step round-trip --outcome passed`),
re-ran the protected-path audit (still clean), and that unlocked `proof/complete`, the
graph's actual closing node. Sent 3 friction reports mapping onto Part 3's three findings,
then ran `onboard complete --visual-check skipped-no-browser-tool --frontend-url
http://localhost:3000`. Result: **blocked, not complete** — correctly, since no browser tool
was live this session to actually watch the app render. Full detail in steps 33–36 above,
including the complete node-by-node route this run walked.

**This is the actual end of the run** *(superseded — see the next entry: a fresh session
brought the browser tool online, and the visual check that was outstanding here is now
done)*. The round trip this onboarding exists to prove — a real chat message getting a
real, persisted answer, survivable across a reload — is proven and formally recorded as
such. What remains (driving the app in a real browser to prove realtime delivery, CORS/CSP,
and generative UI rendering) is legitimately outstanding, not broken, and needs a live
browser tool in a future session to close.

### 2026-09-16 — Visual check performed, onboarding formally complete

A fresh session picked up the Playwright MCP server registered back when the browser
preflight first ran — this time the `mcp__playwright__*` tools were actually live.
Developer: *"now try."* Spawned one proof subagent to run the graph's real
`subagent/prove-round-trip` procedure end to end, including the step that had been blocked
every time before: driving an actual browser.

Result: `Status: passed` on all ten steps. The subagent opened `localhost:3000`, typed
"Show Engineering Salaries by month as a bar chart" into the live chat, watched the turn
finish, and got back a rendered bar chart — Jan/Feb/Mar at 42000/42000/48000 — matching
`agent/src/db.csv` exactly, with no console errors and two successful network calls to the
runtime. It also correctly *declined* to run the Skills-install part of the continued-dev
setup because that writes into protected `.agents/`/`.claude/` paths, while still
registering the CopilotKit docs MCP server (a change to the coding agent's own config, not
the repo).

`onboard audit` stayed clean, and `onboard complete --visual-check performed
--frontend-url http://localhost:3000` returned **"CopilotKit onboarding marked
complete."** — the same command that returned `blocked` earlier in this run, now genuinely
different because the thing it was checking for actually happened this time.

**This really is the end of the run.** Every check the graph asks for passed: CLI-level
round trip, live-browser round trip, and grounding against real project data, all
consistent with each other. Nothing about this outcome was argued or inferred — it was
watched happen.
