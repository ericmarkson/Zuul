# Track G — Reconciling the two trust layers (file-hash baseline vs. OpenBot's CEL policy/audit)

Status: **done** (design decision, synthesized from Tracks A/B/C — not an external
lookup track). **Addendum (2026-09-18), strengthened after an independent QA pass flagged
the first version of this note as too soft:** this file was written assuming our
coordinator/implementer/QA agents run *as* OpenBot-gateway-managed Bots (Track C's
original framing, since corrected — see that file's addendum). **That assumption is not
just outdated, it inverts this file's own central claim.** The "Findings" section below
opens with "Track C already establishes there is no seam, structurally" — in the
corrected, standalone-by-default design, the opposite is true: **there is a seam by
construction**, because the implementer's own shell can touch anything in the working
copy, with nothing external gating it. The git-native mechanism designed below (baseline,
commit-per-phase, diff-against-plan) is not "the primary trust boundary among several" —
it is now **the only thing closing that seam** in the normal (headless) case. OpenBot's
own gateway audit becomes a bonus, structurally independent second record that exists
only if a deployment chooses to attach OpenBot — it is never what closes the gap. The
mechanism itself (git baseline, commit-per-phase, diff-against-baseline, hash carve-out
for gitignored paths) is unaffected by this correction and still stands as designed
below — only the "no seam, structurally" framing is retracted, not the design it led to.

## The question this was scoped to answer

Is there a seam where a granted MCP/shell tool could bypass our own file-integrity
check, and which system of record owns what?

## Findings, drawing on B and C

**Original claim (2026-09-17), retracted 2026-09-18 — kept for the record, not deleted:**
~~"Track C already establishes there is no seam, structurally: a Bot process never
touches its sandboxed computer directly — every shell/file/MCP action a Bot's model
requests is proxied through OpenBot's own gateway (policy check → audit row → execute),
per the signed 'run assertion' mechanism. That means any command our implementation/QA
agents run to compute or verify a file-hash baseline is itself just another governed
shell call, showing up in OpenBot's own `/admin/audit` alongside every code-editing
action. The two systems can't disagree about what ran, because there's only one
execution path."~~ This was true only for OpenBot's own *managed* Bots — not for the
standalone, bring-your-own-agent design the correction settled on, where the
implementer's shell has direct, ungated access. **There is a seam in the corrected
design**, and the git-native mechanism below is what closes it — see the file-level
addendum above.

**What they don't share is interpretation.** OpenBot's audit answers "was this tool call
permitted, and did it happen" at the action level. Our protected-path baseline answers a
different question: "did the *bytes* of a file outside the approved plan change,
regardless of which tool changed them." Those are complementary, not overlapping — a
tool-call log doesn't tell you if a permitted `shell` grant was used to `sed` an
unapproved file, but a before/after hash comparison does.

**Reconsidering the mechanism, given Track B's finding that the target repo already
needs to live in the Bot's `/workspace` as a real git working copy** (Track B: cloned in
via the Bot's own shell, or bind-mounted): a bespoke SHA-per-file baseline/audit store
(reimplementing what the CopilotKit onboarding CLI's `onboarding-protected-paths.ts`
does — walk the tree, hash every file, re-hash and diff later) is very likely
unnecessary duplication when the workspace is already a git repository. **Recommend git
itself as the primary integrity mechanism**, closer to what GitHub Copilot's upgrade
agent actually does (Track A: operates on a branch, commits each task separately,
reviewable via `git log`/`git cherry-pick`) than to CopilotKit onboarding's custom hash
store:
- Baseline = a clean `git status` (or a captured stash/diff of pre-existing uncommitted
  changes) at run start, recorded once, before any writes.
- Per-phase changes = one commit per completed node, scoped to exactly what that node's
  agent was approved to touch.
- Audit = `git diff <baseline>..HEAD --stat` (or per-path) checked against the approved
  plan's declared file/project scope, run after each phase and at final completion —
  mechanically simpler than a hash-comparison store, and it comes with cherry-pick/
  partial-acceptance for free, which the file-hash approach didn't give us.
- **A hash-based check is still needed for exactly the paths git can't see**: anything
  gitignored (credentials, `.env`-shaped files) — mirroring CopilotKit onboarding's own
  `deferred`-path carve-out for `.env`/`project.json`. Keep the hash mechanism, but scope
  it narrowly to gitignored/credential-adjacent paths only, rather than the whole tree.

**A real gap, not a false one**: OpenBot's own policy engine could legitimately *deny*
the shell commands our baseline/audit steps need (`git status`, `git diff`, hash
commands on gitignored paths) if a deployment's CEL rules are stricter than expected.
Per OpenBot's own stated philosophy ("deny evaluated before allow, a missing policy
permits nothing, a broken rule refuses rather than opens"), **the harness must treat a
denied baseline/audit check as a hard stop/friction-report condition, not something to
route around** — consistent with the project's own "fail closed" instinct, and with the
journal's structured stop/friction-report principle. This means whatever OpenBot policy
ships alongside our Bots needs an explicit allow-rule for the specific read-only
git/hash commands the baseline mechanism depends on, documented as a deployment
prerequisite rather than assumed.

## Verdict

**Corrected 2026-09-18**: in the standalone (default, headless) design, there is only
one layer that matters for integrity — **our own git-native mechanism** (commit-per-phase,
diff-checked against the approved plan's declared scope, with a narrow hash-based
carve-out for gitignored/credential paths git can't see). It is not "complementary to"
anything; nothing else is watching the working copy unless OpenBot happens to be
attached. When OpenBot *is* attached, its gateway audit becomes a genuinely independent
second record ("was this action permitted and did it happen," at the tool-call level) —
useful, but never load-bearing, and the policy-allowance concern (a stricter deployment's
CEL rules could deny the read-only git/hash commands our own audit step runs) only
applies to that optional path, not to the standalone default.
