# Track E — Provider-agnostic LLM backend (Azure AI Foundry / Google Vertex / Anthropic / OpenAI)

Status: **done**. (Pulled forward ahead of C/D — see `logs/session-log.md` for why.)

## What was checked

Read the actual source, not docs: `agent-langgraph/src/model-key.ts`,
`agent-langgraph/src/model-options.ts`, `agent-langgraph/package.json`, and the relevant
environment blocks in `docker-compose.yml` for `agent-langgraph`, `agent-bot`, and
`agent-harness`, plus `desktop/src/HarnessPicker.tsx` for the "any-provider" framing
given to the twelve example Bots.

## Findings

**OpenBot already has a working, non-hardcoded provider switch — but it only covers
three providers directly.** `agent-langgraph/src/model-key.ts` maps a `provider` string
to a required key env var:

```ts
export const KEY_VARIABLE: Record<string, string> = {
  openai: "OPENAI_API_KEY",
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_API_KEY",
};
```

selected via `BOT_PROVIDER` (see `docker-compose.yml`'s `agent-langgraph` service), and
`package.json` confirms this is backed by LangChain.js's official per-provider adapter
packages: `@langchain/openai`, `@langchain/anthropic`, `@langchain/google-genai` (this
last one is the **Gemini Developer API**, i.e. Google AI Studio — not Vertex AI, which
is a separate LangChain package). This is the concrete, already-proven mechanism behind
the `HarnessPicker.tsx` claim that "any of these works with any AI provider": it's
LangChain's provider-adapter pattern, not a bespoke abstraction OpenBot invented, and
not a universal gateway either — it's a short, explicit list, extended by adding one
more official LangChain package plus one more switch branch.

**A second, already-built escape hatch matters more for us**: `keyIsRequired()` in the
same file special-cases `provider === "openai"` with a custom `OPENAI_BASE_URL` — no key
required, because "any endpoint speaking that API" (Ollama, vLLM, LM Studio, llama.cpp
are named explicitly in the comments) is already a supported, no-fork configuration.
**This is also exactly the shape of an OpenAI-compatible proxy in front of other
providers** — which is what LiteLLM's proxy mode is. Point `OPENAI_BASE_URL` at a
self-hosted LiteLLM proxy, and Azure AI Foundry, Google Vertex, Anthropic, and OpenAI
all become reachable through **zero changes to OpenBot's Bot code** — the proxy does the
per-provider translation, and OpenBot already treats "custom OpenAI-compatible endpoint,
no key needed here because the proxy holds the real credentials" as a first-class,
already-tested case.

## Two viable paths, neither of which reinvents anything

**Option 1 — LiteLLM (or an equivalent OpenAI-compatible gateway) in front, no Bot code
changes.** Stand up a LiteLLM proxy (self-hosted; routes to Azure AI Foundry, Vertex,
Anthropic, and OpenAI from one config file, presenting a single OpenAI-compatible
`/chat/completions` surface) and point the existing `OPENAI_BASE_URL` var at it. Uses
OpenBot's *already-shipped, already-tested* no-key-custom-endpoint path verbatim.
- Pro: touches none of OpenBot's or our own agent code; provider choice becomes a config
  file on the proxy, fully decoupled from the harness.
- Con: one more service to deploy, secure (it now holds every provider credential), and
  keep documented; LiteLLM's exact current license terms for the proxy vs. its paid
  enterprise features should be re-verified before depending on it operationally (not
  yet independently confirmed this session — flagged as an open thread below, not a
  blocker to recommending the approach).

**Option 2 — extend the existing switch with two more official LangChain adapters.**
Add `azure` (LangChain.js's `@langchain/openai` package already ships `AzureChatOpenAI`
in the same dependency that's already installed — literally no new package for Azure
OpenAI-flavored access) and `vertex` (`@langchain/google-vertexai`, one new official
LangChain package) as two more `KEY_VARIABLE`/switch branches, following the exact
pattern `model-key.ts` already established.
- Pro: no extra service to run or secure; stays inside the same process; matches the
  project's existing convention exactly (whoever maintains this later sees one familiar
  pattern, not a proxy layer to also understand).
- Con: touches Bot source for every framework example we want this in (LangGraph today;
  potentially others later), and "Azure AI Foundry" as Microsoft currently brands it is
  broader than plain Azure OpenAI (it also fronts a wider model catalog) — worth
  checking whether `AzureChatOpenAI` covers the specific Foundry deployment shape we'll
  actually be pointed at, or whether the newer `@langchain/community`
  Azure-AI-inference-style integration is the better fit. Not yet verified.

## Recommendation

**Option 2 as the default** — it's the smaller, more legible change, it's a direct
extension of a pattern OpenBot's own maintainers already chose and shipped (so it stays
idiomatic if we ever want to send a change upstream or diff against future OpenBot
releases), and it avoids standing up + securing a whole extra proxy service just to pick
a model provider. Keep **Option 1 in reserve** for a deployment that specifically wants
provider choice to be an ops-level config file rather than anything in the agent's own
image (e.g., a platform team that wants to swap providers without redeploying Bots).

Either way: **do not build our own provider-adapter layer.** Both options reuse
existing, officially-maintained abstractions (LangChain's provider packages, or
LiteLLM's proxy), exactly per the original instruction not to reinvent this.

## Open threads (not blocking)

1. LiteLLM's current exact license terms for proxy/self-hosted use (core vs. enterprise
   feature split) — verify before treating Option 1 as fully free to operate.
2. Whether `AzureChatOpenAI` (from `@langchain/openai`) is the right integration for
   Azure **AI Foundry** specifically, versus a newer Azure-AI-inference-flavored LangChain
   integration meant for Foundry's broader model catalog beyond OpenAI models — verify
   against current LangChain.js docs before implementing Option 2's Azure branch.
