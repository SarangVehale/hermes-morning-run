---
created:
updated:
topic: github releases
frequency: daily
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> Tracks GitHub releases for tools the user actively uses. Surfaces breaking changes, new features, and migration concerns before they cause surprise on the user's machine.
>
> ## Inputs
>
> Read `~/vault-ai/_tools.yaml`. Structure:
>
> ```yaml
> tools:
>   - repo: NousResearch/hermes-agent
>     name: Hermes Agent
>     reason: orchestrator we depend on
>   - repo: ggerganov/llama.cpp
>     name: llama.cpp
>     reason: inference engine on Ryzen
>   - repo: yt-dlp/yt-dlp
>     name: yt-dlp
>     reason: watchlist depends on this for YouTube transcripts
>   - ...
> ```
>
> For each repo, fetch releases since last run.
>
> ## API
>
> GitHub REST API: `https://api.github.com/repos/{owner}/{repo}/releases?per_page=10`
>
> Unauthenticated rate limit: 60 requests/hour from one IP. For a watchlist under 30 tools, one daily run uses ~30 requests — comfortable.
>
> If the user wants more headroom, set `GITHUB_TOKEN` env var (a fine-grained PAT with no scopes works, just needs to exist) → bumps to 5000 req/hour.
>
> ## Filtering
>
> For each repo, find the most recent release with `published_at` > last-run timestamp. Track per-repo last-seen via `~/.hermes/state/github-releases-last-run.json`.
>
> Skip:
>
> - Pre-releases (`prerelease: true`) unless the repo has no stable releases.
> - Draft releases (`draft: true`).
> - Releases without notes (empty `body` field).
>
> ## Output format per release
>
> ```
> > [!note]- llama.cpp b4521 — flash-attn improvements, breaking config change for --threads-batch
> > Two-sentence summary of what's in the release notes. Wikilink the tool. Note explicitly if there are breaking changes affecting our setup (e.g. flag rename, default behavior change, new dependency).
> > [Release notes](https://github.com/.../releases/tag/...)
> ```
>
> If the release contains breaking changes that affect tools used in the user's morning workflow (Hermes Agent, llama.cpp, yt-dlp, defuddle, the Obsidian plugins), elevate to `[!breaking]-` and explicitly say what config or script needs updating.
>
> If a release is informational-only (bug fixes, minor features), `[!note]-` is fine.
>
> ## Wikilinks
>
> Tool names: `[[llama.cpp]]`, `[[Hermes Agent]]`. Stubs land in `07 References/` and accumulate over time into a personal "tools I depend on" map.
>
> ## Quiet days
>
> If no tracked tools released anything since last run, write `No new releases since {last-run-date}.` Do not pad.
>
> ## Date handling
>
> Newest day at top. Group by `## YYYY-MM`. Collapse previous day. Set `unread: true` and update `updated:`.
>
> ## When the user updates a tool
>
> The user maintains the list manually in `_tools.yaml`. When they remove a tool (stopped using it), this skill forgets it. When they add one, this skill picks it up on the next run.
>
> No state cleanup needed on remove; the per-repo state file simply has stale entries that get ignored.
