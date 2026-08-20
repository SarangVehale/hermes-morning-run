# Patch — summarize skill for no-GPU environment

The original `SKILL.md` in this directory is the unmodified file from the ai-life-skills repo. It supports two YouTube paths: prefer auto-subtitles, fall back to audio download + Whisper transcription. The fallback needs a GPU (mlx_whisper) or a paid API (ElevenLabs Scribe). Sarang has neither.

This patch removes the audio fallback. If a YouTube video has no auto-subs, the skill returns a clean error instead of attempting transcription.

## What to change

Open `SKILL.md` in this directory. Find the section titled approximately "**Step 2: Acquire content**" → YouTube subsection (look for the heading or comment that introduces the YouTube branch — roughly line 150-250 in the original).

Inside the YouTube content acquisition block:

1. **Keep** the auto-subtitles attempt (the `yt-dlp --write-auto-sub --sub-lang en --skip-download` block).
2. **Keep** the JSON3 → plain text extraction step.
3. **Remove or comment out** any block that:
   - Downloads the video's audio (anything with `--extract-audio` or `-x` or `--audio-format` in yt-dlp args)
   - Calls `mlx_whisper`, `whisper.cpp`, `whisper` (the original Python one), or `whisper_cli`
   - Calls the ElevenLabs API (`ELEVENLABS_API_KEY`, anything fetching from `api.elevenlabs.io`)
4. **Replace** the fallback path with this behavior: if `yt-dlp --write-auto-sub` returns nothing, write a clear error message to stderr and exit the skill with a non-zero status:

```
echo "ERROR: no auto-subtitles available for $url. Skill cannot transcribe audio in this environment." >&2
exit 2
```

5. **Also remove** the prerequisite check for mlx_whisper / ElevenLabs in Step 0c (the "Check required CLI tools" section). The remaining required tools are: `yt-dlp`, `defuddle`, `pdftotext`, `pandoc`.

## Why this is OK

For the user's primary use case (the Daily Watchlist skill processing creator videos), the creators all have auto-subs enabled (YouTube enables them by default for any monetized or sufficiently popular channel). The failure mode is rare and the error message tells the user exactly what happened.

For ad-hoc use (`summarize this YouTube video` on a video with no auto-subs), the user will get a clear error and can manually grab a transcript from somewhere else if they really want one.

## What the original supports that we're losing

- Transcription of YouTube videos with subs disabled (rare on public content)
- Transcription of podcast audio files (.mp3, .m4a) — the file-path code path also lost transcription
- Transcription of arbitrary audio files

If Sarang later gets a GPU machine or decides to enable ElevenLabs, this patch can be reverted by `cp` from the ai-life-skills repo over the patched version.

## Don't touch

The rest of the skill (article extraction via defuddle, PDF via pdftotext, EPUB via pandoc, the note-writing conventions, the reference-creation logic) all stays. Only the audio-transcription path is removed.
