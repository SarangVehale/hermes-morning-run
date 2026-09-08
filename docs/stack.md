# Stack

What we use, what we don't, and why. This is a personal setup — the choices reflect one person's taste, not a general recommendation.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#the-full-dependency-list">The full dependency list</a></li>
  <li><a href="#the-llm-layer">The LLM layer</a></li>
  <li><a href="#what-we-dont-use-and-why">What we don't use, and why</a></li>
  <li><a href="#the-just-fetch-it-philosophy">The "just fetch it" philosophy</a></li>
  <li><a href="#choosing-python-and-stdlib-http">Choosing Python + stdlib HTTP</a></li>
</ul>
</div>

## The full dependency list

Complete list of third-party Python packages in `~/.hermes/morning-venv/`:

| Package | Version | Purpose |
|---|---|---|
| `feedparser` | 6.0.12 | RSS / Atom parsing — the workhorse of news, papers, tech |
| `ddgs` | 9.14.4 | DuckDuckGo Search client (news topic fallback when RSS is thin) |
| `httpx` | 0.28.1 | Async HTTP; used for a few concurrent-fetch paths |
| `requests` | 2.34.2 | Sync HTTP; used by libraries that pull it in |
| `pyyaml` | 6.0.3 | `morning-config.yaml`, `_watchlist.yaml`, `_tools.yaml` |
| `lxml` | 6.1.1 | Fast XML parsing (some RSS feeds are XHTML-ish) |
| `fake_useragent` | 2.2.0 | Rotates browser UAs for feeds that 403 the default |
| `primp` | 1.3.1 | Impersonates a real browser TLS fingerprint for a few stubborn CDNs |
| `certifi` | 2026.5.20 | CA bundle for TLS |
| `urllib3` | 2.7.0 | HTTP plumbing pulled in transitively |

Everything else is stdlib: `json`, `subprocess`, `urllib.request`, `urllib.parse`, `concurrent.futures`, `hashlib`, `datetime`, `dataclasses`, `pathlib`, `re`, `argparse`.

External binaries the pipeline shells out to:

| Binary | Purpose |
|---|---|
| `claude` | Claude Code CLI, print mode — the LLM layer |
| `yt-dlp` | YouTube transcript fetch for watchlist |
| `git` | Vault commit / push, `pull --rebase` at run start |
| `defuddle` | HTML → clean markdown for blog posts (optional) |

## The LLM layer

Since v2.1, all LLM calls go through the `claude` CLI in print mode:

```bash
claude -p \
  --model sonnet \
  --restricted \
  --output-format text \
  --system-prompt "$SYSTEM" \
  <<< "$USER_PROMPT"
```

Why:

- **Auth is inherited from claude.ai OAuth.** The `claude` CLI reads `~/.claude/.credentials.json` — the same session the user's Claude Code interactive sessions use. No `ANTHROPIC_API_KEY` to manage, rotate, or leak.
- **Pro subscription covers the traffic.** Usage counts against the user's already-paid Pro plan rather than a metered API tier. For a personal daily-briefing pipeline that makes ~15-20 LLM calls per morning, this is dramatically cheaper than the API's per-token pricing.
- **`--restricted` disables built-in tools.** Bash, Edit, WebFetch, and the other agentic tools are stripped — we want a pure chat completion. If the LLM ever "hallucinates a tool call", it becomes plain text in the response rather than an actual action.
- **The CLI is already installed.** Anyone running Claude Code has it. One less thing to `pip install`.

The interface `llm.chat(system, user, ..., prefer="primary"|"fast")` preserved from the v1 API (which called `llama-server` on the inference host over HTTP). Callers didn't change.

Fallback: HP-local ollama on `http://localhost:11434/v1/chat/completions` with `hermes3:8b`. Used only when `claude` fails (CLI missing, not logged in, non-zero exit, timeout).

## What we don't use, and why

### LangChain

Zero LangChain imports. No `langchain_openai`, no `langchain_anthropic`, no chains, no runnables, no output parsers.

The v1 pipeline briefly considered LangChain-style abstractions during design and rejected them because:

1. **Every layer of abstraction is a place a URL can get mangled.** The v1 LLM-first architecture failed precisely because the model was reformatting URLs after the "output parser" pretended to validate them. Adding LangChain's `PydanticOutputParser` between the model and the render step would have added another shape-shifting layer, not solved the problem.
2. **The LLM's job in this pipeline is small.** Watchlist summarization. Curiosity synthesis. A few doctor-check questions. That's a single prompt → single response per call. There is no chain to orchestrate.
3. **We already have Python.** For selecting an item from a list, filtering by a heuristic, or deduplicating by domain, `list.sort(key=...)`, `set()`, and a for loop are shorter, clearer, and don't versionlock us to someone else's release cadence.

### LangGraph

Same reasoning, more so. LangGraph is for building agent graphs with cyclic state machines. This pipeline has no cycles, no agent state, no branching decisions that need a graph. It's a linear waterfall: fetch → select → render → write, once per stream, then a composer at the end. `runner.py` orchestrates it in ~500 lines of plain Python with `ThreadPoolExecutor`.

If we wanted the LLM to *decide* what streams to run based on today's data — that would be agentic and would potentially justify a graph. We don't. The stream list is a fixed config.

### LlamaIndex / LlamaHub

We don't do RAG. The vault isn't a corpus we query — it's the *output* of the pipeline, read by a human. There's nothing to embed, index, or retrieve over. LlamaIndex would be dead weight.

The one place LlamaIndex-shaped thinking might apply is `connection-finder.py`, which surfaces cross-note conceptual links — but that runs infrequently, works on a small local set, and uses direct LLM prompting rather than embeddings.

### Anthropic Python SDK

For this pipeline specifically, the `anthropic` SDK is not needed because we shell out to the `claude` CLI. If a fork wanted to use the API directly, they'd swap `llm.py` for an SDK-based implementation — the `chat(system, user, ...)` interface is stable across implementations.

### OpenAI / GPT / Gemini

We use exactly one LLM provider — Anthropic, via the `claude` CLI. There's no router, no fallback across providers. The user is already paying for Claude Code; multi-provider ceremony would be gratuitous.

### Prefect / Airflow / Dagster

The pipeline is one bash script and one systemd timer. If you can `systemctl --user enable hermes-morning.timer` you don't need a workflow orchestrator.

### Docker / Kubernetes

The pipeline runs as the user, on the user's machine, reading and writing files under the user's home directory. Containerization would add complexity and buy nothing — there's no isolation requirement (the user already owns everything the pipeline touches), no scheduling to distribute, no dependency to sandbox.

### A database

State is JSON files under `~/.hermes/state/`. Total state size is under 10MB. `feedparser` is faster than any database query we could make against this volume. If we were to grow state past ~100MB or across multiple concurrent writers, SQLite would be the answer — not Postgres, not Redis.

## The "just fetch it" philosophy

The v1 → v2 rewrite (see [History](history.html#the-rss-first-insight-august-20-morning)) was a rediscovery of something obvious: publishers already ship structured metadata via RSS. Title, description, publish date, image URL — it's all there. Feeding that to an LLM to re-summarize is adding a layer that has:

- Non-zero failure rate (URL mangling, JSON errors, timeouts)
- Non-zero cost (tokens)
- Non-zero latency (30-90s per call vs 100-500ms per RSS fetch)
- Non-zero opinion (the model picks based on training biases, not user preferences)

...in exchange for what? A slightly nicer prose paraphrase of a paraphrase.

The philosophy that fell out:

- **Fetch from the source.** Publishers are the authority on their own content. Don't infer, don't summarize, don't paraphrase — quote.
- **Select deterministically.** A round-robin across categories or sources will eventually surface everything. An LLM curator has favorites and never shows you the rest.
- **Use the LLM only where it earns its keep.** Transcript summarization (converting a 30-minute video into 3 paragraphs) genuinely needs an LLM. Aggregating five titles into a picked-three does not.

This is the opposite of the current LLM-first zeitgeist. It works because the tasks in this pipeline mostly aren't LLM-shaped.

## Choosing Python + stdlib HTTP

Python because:

- `feedparser` is the reference implementation of RSS/Atom parsing in any language.
- `subprocess` + `stdin` is a clean way to shell out to `claude` and `yt-dlp`.
- We already had Python installed for `yt-dlp`.

`stdlib urllib.request` for most HTTP because:

- Zero dependencies.
- The morning pipeline's HTTP needs are trivial: GET some URLs, parse JSON, done.
- `requests` would be nicer syntactically but adds ~15 transitive dependencies.

`httpx` where we do want async (a few paths in `runner.py`'s parallel dispatch). `feedparser` uses `urllib` internally and doesn't take a client, so async fetching is done at the executor level, not the HTTP-client level.

{% include nav.html
  prev="architecture" prev_title="Architecture"
  next="setup" next_title="Setup" %}
