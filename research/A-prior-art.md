# Track A — Prior art: does something already exist (or forkable) that does this?

Status: **done** (core question answered; two loose threads flagged for a future pass,
see "Open threads" at the bottom — not blocking).

## What was checked

### 1. GitHub Copilot upgrade / "modernize-dotnet" / `microsoft/upgrade-agent-plugins`

This is one product family that has been renamed/consolidated over time:
`dotnet/upgrade-assistant` (old repo name) → `dotnet/modernize-dotnet` (deprecated) →
`microsoft/upgrade-agent-plugins` (current, "GitHub Copilot upgrade" / "GitHub Copilot
app modernization"). Docs:
[overview](https://learn.microsoft.com/en-us/dotnet/core/porting/github-copilot-upgrade/overview),
[FAQ](https://learn.microsoft.com/en-us/dotnet/core/porting/github-copilot-upgrade/faq),
[scenarios & skills](https://learn.microsoft.com/en-us/dotnet/core/porting/github-copilot-upgrade/scenarios-and-skills).

**What it actually does — and it is a remarkably close functional match to our design:**
- Analyzes a solution, proposes an upgrade plan, executes it as a series of tasks,
  fixes build errors as it goes, reports progress, and persists a plan file
  (`.github/upgrades/`) plus a `scenario-instructions.md` that carries learned
  preferences across sessions.
- **Skill-based knowledge packs**: 30+ built-in "upgrade skills" auto-load based on
  detected technology (EF6→EF Core, Newtonsoft.Json, Azure Functions, MVC/Web
  Forms/Blazor, etc.), and custom skills/scenarios can be authored. This is
  essentially our "MCP as swappable knowledge pack" idea, already validated as the
  right shape by a shipping Microsoft product.
- **Git-native protected-path equivalent**: operates on a working branch, commits each
  task separately, so a human can `git log --oneline` / `git cherry-pick` to accept
  partial work — a different (and arguably simpler) mechanism than our file-hash
  baseline+audit, worth comparing against in Track G.
- Supports .NET Framework (any version) → .NET 8+ or → .NET Framework 4.8.1, plus
  .NET Core 1.x-3.x and .NET 5+ upgrade paths, across web/desktop/MAUI/Xamarin/test
  project types, C# and VB.
- **Telemetry it already collects**: project type, upgrade intent, and upgrade
  duration, aggregated and non-PII — a useful reference point for our own Track D
  analytics event schema (it's already validated that phase/duration-level data,
  not fine-grained content, is the right telemetry altitude for this kind of tool).

**Why it's not usable as a base, despite the close match:**
- **License**: `microsoft/upgrade-agent-plugins` and its predecessor repos ship under
  the "Microsoft Pre-Release Software License Terms" — proprietary, not OSI, with an
  explicit 2-year confidentiality clause on the software itself. Not forkable, not
  redistributable, not something we can build on top of or extract code from.
- **Locked to the GitHub Copilot subscription and its cloud infrastructure — but
  corrected 2026-09-18: NOT locked to one model backend.** An independent QA pass found
  GitHub Copilot actually ships bring-your-own-key support for Anthropic, AWS Bedrock,
  Google AI Studio, Microsoft Foundry, OpenAI, OpenAI-compatible providers, and xAI,
  across Copilot Chat, Copilot CLI, and IDEs — exactly where the upgrade agent runs. The
  FAQ's "model availability depends on your subscription and environment" is the real
  constraint, not a hard single-vendor lock. **This doesn't change the verdict** (the
  license below is the actual, sufficient reason this can't be adopted), but the
  original reason stated here was wrong and has been corrected. Google **Vertex**
  specifically is still not one of Copilot's BYOK providers — Google AI Studio is a
  different product.
- **Requires internet + GitHub Copilot cloud infrastructure** — no offline/self-hosted
  mode, which conflicts with the "runs as your own companion app" framing.
- **Interactive-chat-session shaped, not unattended-by-design** — it's driven from
  inside a Copilot chat session (VS/VS Code/Copilot CLI/GitHub.com); there's a
  separate "Copilot Coding Agent" cloud mode for PR-based automation, but the core
  product is not architected around a single up-front approval gate followed by a
  long unattended run the way our design (and the CopilotKit onboarding graph it's
  modeled on) is.

**Verdict**: not adoptable or forkable, but extremely valuable as a *feature
checklist* to compare our own design against — particularly the skill-auto-loading
mechanism, the plan-file-in-repo pattern, and the per-task-commit approach to
reviewable/partial acceptance.

### 2. AppCAT (Azure Migrate application and code assessment tool for .NET)

Docs: [overview](https://learn.microsoft.com/en-us/dotnet/azure/migration/appcat/app-code-assessment-toolkit),
[.NET CLI usage](https://learn.microsoft.com/en-us/dotnet/azure/migration/appcat/dotnet-cli).

A genuinely standalone tool (CLI + separate VS extension) that does static analysis of
a .NET codebase's source, binaries, and config, and emits a structured report — in
**HTML, CSV, or JSON** — flagging compatibility issues and giving effort-estimation and
remediation guidance. It's aimed primarily at Azure replatforming (App Service/AKS/
Container Apps) rather than specifically "Framework → Core," but Framework-specific API
usage is exactly the kind of thing this class of tool detects, so the overlap with our
"audit skill" requirement is substantial.

**Why this is worth a closer look before writing our own static analyzer**: it already
produces a machine-readable JSON audit exactly like the artifact our MCP's audit skill
is supposed to emit. If its JSON schema is usable (or close enough to normalize), the
MCP audit skill could shell out to AppCAT and translate its report into our phase-graph
input, instead of building compatibility-detection logic from scratch.

**Resolved 2026-09-18 (was "not yet verified" above) — license is adverse.** An
independent QA pass fetched the actual `dotnet-appcat` NuGet package license: "Microsoft
Pre-Release License Terms for Microsoft Azure Migrate Application and Code Assessment
.NET CLI Tool" — the same proprietary family as the GitHub Copilot upgrade agent above.
It explicitly forbids sharing/publishing/distributing it, forbids "provid[ing] the
software as a stand-alone offering or combin[ing] it with any of your applications for
others to use," forbids extending it with non-Microsoft add-ins, and **expires 30 days
after commercial release**. Wrapping it inside our own shipped MCP audit skill is
squarely prohibited by its own terms (ad hoc internal dev/test use of the CLI directly
is likely fine, but that's not the same as depending on it as a component). **AppCAT is
no longer a candidate for the audit engine** — see `IMPLEMENTATION-PLAN.md`'s Decision 1,
now resolved toward a custom static analyzer.

## Verdict for Track A

**No existing product or open-source project should be adopted or forked wholesale.**
The closest match (Microsoft's GitHub Copilot upgrade agent family) is proprietary and
cloud-dependent — it validates that this entire approach is sound and already
commercially proven, but hands us nothing legally reusable. (Correction, 2026-09-18: it
is not actually "Copilot-model-locked" as originally stated here — see the corrected
paragraph above. The license remains the real, sufficient reason it can't be adopted.)
AppCAT, once considered as a possible audit-engine dependency, is now also ruled out on
license grounds (above) — build a custom analyzer instead.

Proceeding to build our own harness is justified; nothing found here should change that
decision.

## Open threads (not blocking, worth a short follow-up pass later)

1. ~~Whether a genuinely open-source, non-AI predecessor of "upgrade-assistant"~~ —
   **resolved 2026-09-18**: `dotnet/upgrade-assistant` was renamed in place into
   `dotnet/modernize-dotnet` (same repo, now proprietary — nothing survives under the
   old name). But **`dotnet/try-convert` does survive independently**: MIT-licensed,
   archived, last pushed 2024-05-17. Genuinely forkable/embeddable as reference material
   for the custom analyzer's targeting-detection logic, though unmaintained for ~2.3
   years as of this writing.
2. Generic open-source "autonomous coding agent with graph/phase orchestration"
   frameworks (e.g. OpenHands, SWE-agent, Aider) were not yet checked as potential
   bases for the coordinator/implementation/QA agent loop itself (as opposed to the
   .NET-specific knowledge). Worth one pass before finalizing the coordinator's
   implementation, in case the orchestration loop itself (not just the .NET knowledge)
   has a solid reusable base. Still open.
3. ~~AppCAT's license terms for automated/CLI use, and its actual JSON report schema~~ —
   **resolved 2026-09-18**: license terms confirmed adverse (above). JSON schema is no
   longer relevant to pursue, since AppCAT is ruled out regardless of its shape.
