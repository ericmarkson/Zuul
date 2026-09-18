# Track B — OpenBot's "computer" runtime vs. real .NET build/test workloads

Status: **done**. **Addendum (2026-09-18):** this file's mechanics are all confirmed
accurate (re-verified against source during an independent QA pass, plus two factual
corrections below on .NET version and package source). Scope note, following the Phase
4 correction in `IMPLEMENTATION-PLAN.md`: the OpenBot `agent-computer`/`COMPUTER_IMAGE`
mechanism described here is now the **optional** execution environment (used only when
OpenBot is attached), not the harness's primary one — the standalone core defines its
own execution environment directly. Everything below about the mechanism itself remains
accurate for that optional path.

## What was checked

Read the actual source, not just docs: `agent-computer/Dockerfile`, `docker-compose.yml`
(the `agent-computer` and `supervisor` service definitions), and the top-level directory
listing of `supervisor/src`, directly from the `CopilotKit/OpenBot` repo via `gh api`.

## Findings

**Base image is plain Ubuntu 24.04** (`agent-computer/Dockerfile`), with Bun and a
pinned Playwright/Chromium install layered on top. Nothing .NET-specific, but nothing
that would conflict with adding .NET either — it's a completely ordinary Debian-family
base, and a `dotnet-sdk` apt package installs cleanly on Ubuntu 24.04.

**Correction (2026-09-18, independent QA pass) — two factual errors in the original
version of this paragraph:**
1. **The target version, not just the example**: .NET 8 reaches end-of-support
   2026-11-10. Any concrete version named in this design should be "whatever the
   current LTS is at build time," not a hardcoded `8.0` — that number will itself be
   stale by the time anything here gets built. (As of this writing, that's .NET 10,
   supported to Nov 2028 — but don't hardcode that either; resolve it at setup time.)
2. **Package source misattribution**: this was called "the Microsoft `dotnet-sdk-*` apt
   package," which is wrong for Ubuntu 24.04 specifically. Microsoft's own Learn docs
   confirm Microsoft's package feed carries **no** .NET packages at all for Ubuntu 24.04
   — the package comes from Ubuntu's own (Canonical) feed instead, which only ships the
   `.1xx` feature band for whichever major version is current. The install command
   itself is correct and works; only the "Microsoft's package" framing was wrong.
   Practical consequence: the stock Dockerfile's existing apt layer ends with
   `rm -rf /var/lib/apt/lists/*`, so a new `RUN apt-get install -y dotnet-sdk-*` layer
   needs its own `apt-get update &&` first, or it will fail.

**No fork required for this part**: the image is swappable per-deployment via the
`COMPUTER_IMAGE` environment variable that both `docker-compose.yml`'s `agent-computer`
service and the `supervisor` (which is what actually creates one container per Bot,
`COMPUTER_IMAGE: ${COMPUTER_IMAGE:-openbot-agent-computer:latest}`) read. A custom image
— the same Dockerfile plus its own `RUN apt-get update && apt-get install -y
dotnet-sdk-<current-LTS>` layer — is a supported, first-class customization point, not a
patch to the base repo.

**Workspace persistence**: `/workspace` is a named Docker volume
(`agent-workspace:/workspace`), not a host bind-mount, in the stock compose file. Two
ways to get a real target repository into it, neither requiring a fork:
1. Have the Bot's own shell capability `git clone` the target repo into `/workspace` as
   an explicit first step (goes through the same governed/audited gateway as every other
   shell action — consistent with the rest of the design, no special-casing needed).
2. Override the compose file for a bind mount if the deployment wants the host's actual
   working copy to be the one being edited/built, instead of a clone.

**Shell execution is a first-class, already-governed capability** (confirmed against the
README's own feature description, and consistent with what the Dockerfile builds):
"a Bot can run a command in its workspace, install what it needs" — through the same
policy gateway and audit trail as browser/file/MCP actions, so `dotnet build`,
`dotnet test`, `dotnet publish`, `git` commands all flow through OpenBot's existing
CEL policy + audit layer for free. This is directly usable by the QA agent's
"proof over self-report" requirement (Part 4 of the journal) — no new plumbing needed to
get a real build/test result recorded.

**One real limitation, worth designing around rather than ignoring**: this is a Linux
container. `dotnet build`/`dotnet test` against a project already retargeted to a
modern .NET (Core) target (i.e., **after** the migration's SDK-retargeting phase) works
fine cross-platform — that's the whole point of .NET (Core)'s portability, and it's exactly
the state the QA agent needs to validate. But building the **original**, unmodified
`.NET Framework`-targeted project (e.g. as a pre-migration baseline sanity check, using
the classic full-framework MSBuild) is not something this Linux container can do — that
toolchain is Windows-only (or requires Mono, which is its own can of worms and not
something to lean on for a real build/test proof). **Design implication**: any phase of
our harness that wants to prove "the app builds today, before any changes" as a baseline
needs either (a) a Windows-based computer/runner for that one pre-check, skipped or
best-effort if unavailable, or (b) accept that the pre-migration baseline is
static-analysis-only (audit file findings) and the first *live, run* proof is
post-retarget. Leaning toward (b) as the default, with (a) as an optional enhancement if
a Windows runner is available — matches the "prove things live, but be honest about what
one proof method can't cover" principle from the journal's Part 4.

**Governance fit**: `COMPUTER_RUNTIME=runsc` is available for gVisor-sandboxed execution
of the computer container, if stronger isolation is wanted for a Bot that's about to run
arbitrary build scripts from an unfamiliar repo — worth turning on for this specific use
case even if not the deployment's default.

## Verdict

**No fork needed for Track B's core question.** A custom `agent-computer` image (base
Dockerfile + `dotnet-sdk` package) registered via `COMPUTER_IMAGE`, combined with the
Bot's existing shell capability to clone the target repo into `/workspace`, is
sufficient to run real `dotnet build`/`dotnet test` against a real .NET Core-targeted
codebase inside OpenBot's own governance and audit model. The one gap — building the
*original* .NET Framework baseline pre-migration — is a Windows-vs-Linux limitation
inherent to .NET Framework itself, not an OpenBot limitation, and should be designed
around (treat the pre-migration baseline as audit-file/static-analysis evidence, not a
live build) rather than solved by forking anything.

This substantially de-risks the "phase 2 fork" contingency noted in `CLAUDE.md` — it
now looks like a config/custom-image exercise, not a fork. Recommend downgrading that
risk note next time `CLAUDE.md` is revised.

## Related discovery, expanded properly under Track E

While reading `docker-compose.yml` for this track, found that OpenBot already ships a
working multi-provider LLM switch (`BOT_PROVIDER` env var across `openai`/`anthropic`/
`google` for the `agent-langgraph` example Bot, plus an `OPENAI_BASE_URL` escape hatch
for any OpenAI-API-compatible endpoint) and a "harness picker" concept (twelve
example agent-framework Bots, each declared `credential: "any-provider"` in
`desktop/src/HarnessPicker.tsx`). This is directly relevant to our provider-agnostic
requirement and is written up properly in `research/E-llm-provider-backend.md` rather
than duplicated here.
