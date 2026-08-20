---
created:
updated:
topic: daily watchlist
frequency: daily
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> Processes the user's creator watchlist. For each new YouTube video or blog post from anyone in `_watchlist.yaml`, fetch the content, generate a detail summary in `08 Summaries/`, and write a stream entry here linking to the detail.
>
> The user does not want video recommendations. The user wants summaries of what was discussed, with new-to-vault concepts highlighted. The detail file is the deliverable; this stream note is the index.
>
> ## Inputs
>
> Read `~/vault-ai/_watchlist.yaml`. Structure:
>
> ```yaml
> youtube:
>   - name: Veritasium
>     channel_id: UCHnyfMqiRRG1u-2MsSQLbXA
>   - ...
> blogs:
>   - name: Siddhant Singh (qecarxiv)
>     url: https://siddhant-singh.com
>     feed: https://siddhant-singh.com/feed.xml
> ```
>
> For each entry:
>
> ### YouTube
>
> 1. Fetch the channel RSS feed: `https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}`.
> 2. Find entries published since the last successful run. Track this via a marker file `~/.hermes/state/watchlist-last-run.json` (per-creator last-seen video ID).
> 3. For each new video, fetch the transcript: `yt-dlp --skip-download --write-auto-sub --sub-lang en --sub-format json3 -o '%(id)s' {url}`. If no auto-subs are available, skip the video and note it in the stream entry with a `[!warning]` flag — do not attempt to transcribe audio.
> 4. Pass the transcript + video metadata (title, duration, upload date) to the `summarize` skill in `detailed` mode. Output goes to `08 Summaries/{Creator} - {YYYY-MM-DD} - {Topic}.md`.
>
> ### Blogs
>
> 1. Fetch the RSS/Atom feed at `feed:` URL.
> 2. Find entries since last run (track by post URL).
> 3. For each new post, fetch the HTML, run through `defuddle` for clean markdown.
> 4. Pass to the `summarize` skill in `detailed` mode. Output to `08 Summaries/{Creator} - {YYYY-MM-DD} - {Post Title}.md`.
>
> ## Stream entry format
>
> Under today's date in this note, one paragraph per video or post. Specific. Concrete. No "the video discusses" — say what it actually said.
>
> ```
> ### [[06-01-26 Sun]]
>
> [[Veritasium]] covered the Vera Rubin Observatory's 3.2 gigapixel camera — the 8.4m mirror size tradeoffs, the two-stage 173K cooling system, and the 60 PB data pipeline planned over the survey's 10 years. New-to-vault concepts: [[LSST cadence strategy]], [[atmospheric refraction correction]], [[difference imaging]]. Detail: [[Veritasium - 2026-06-01 - Vera Rubin Observatory]]. ([source](youtube.com/...))
>
> [[Alex Ziskind]] benchmarked the Strix Halo APU running local LLMs. He's getting 28 tok/s on Qwen3-30B-A3B at Q4 with unified memory, no discrete GPU. Detail: [[Alex Ziskind - 2026-06-01 - Strix Halo LLM Bench]]. ([source](youtube.com/...))
> ```
>
> ## Detail file format
>
> The `summarize` skill in `detailed` mode produces this. Verify the output matches the convention:
>
> ```
> ---
> created: 2026-06-01
> updated: 2026-06-01
> creator: [[Veritasium]]
> source: youtube
> url: https://www.youtube.com/watch?v=...
> duration: 52:14
> upload_date: 2026-05-30
> unread: true
> ---
>
> > [!summary]- One-sentence framing of the whole video.
>
> ## What was covered
>
> Section-by-section walkthrough with timestamps where they're useful. Wikilink concepts on first mention.
>
> ## New to this vault
>
> List of concepts that don't yet have notes in 07 References/, 04 People/, or 06 Research/. These will become auto-stubs at end of morning run.
>
> ## Builds on
>
> Concepts in this video that already have notes in the vault. Wikilinked.
> ```
>
> ## What counts as "new to vault"
>
> Run a grep against existing vault files for each technical noun phrase. If no file exists with that name (or a close variant), it's new. The concept-stubs script (post-run) creates the empty stubs based on the wikilinks in these summaries.
>
> ## Volume control
>
> If a single creator drops more than 2 items in a day (rare but possible — Linus Tech Tips, etc.), summarize all of them, but in the stream entry combine them: `[[Linus Tech Tips]] dropped 3 videos: ...`. Don't overload the stream.
>
> Hard cap on processing: 8 new items per morning run. If there are more, process the 8 most recent and note the skipped count in a `[!warning]` at the bottom of today's entry. The user can manually run the skill on skipped items later.
>
> ## When a feed is broken
>
> If a feed URL returns 404 or invalid XML for 3 consecutive days, write a `[!warning]` in the stream entry: `Feed broken for [[Creator Name]] — last successful fetch YYYY-MM-DD. Suggest re-discovering feed URL.` Continue processing other feeds.
>
> ## Date handling
>
> Newest day at top. Group by `## YYYY-MM`. Collapse previous day. Set `unread: true`.
