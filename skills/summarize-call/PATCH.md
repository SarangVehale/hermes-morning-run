# Patch — summarize-call skill for CPU-only Whisper

The original `SKILL.md` in this directory is the unmodified file from the ai-life-skills repo. It depends on `mlx_whisper` (Apple Silicon only) or ElevenLabs Scribe (paid). Neither works for Sarang's setup.

This patch swaps in `whisper.cpp` (CPU-only, free, open-source). Quality is comparable; speed is dramatically worse.

## What to change

Open `SKILL.md` in this directory. Find every reference to `mlx_whisper` or `whisper_cli` or `mlx-whisper`. Replace with `whisper.cpp` invocations.

## Installation (on the HP, where the call summarizer runs)

```bash
# Build whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp
make -j$(nproc)

# Download a model (medium is the sweet spot for English calls)
bash ./models/download-ggml-model.sh medium.en

# Symlink the binary somewhere on PATH (or use absolute path in the skill)
mkdir -p ~/.local/bin
ln -s ~/whisper.cpp/main ~/.local/bin/whisper-cpp
```

## Replacement command

Wherever the skill called `mlx_whisper`, use this instead:

```bash
~/whisper.cpp/main \
  -m ~/whisper.cpp/models/ggml-medium.en.bin \
  -f /path/to/audio.wav \
  -otxt \
  -of /tmp/transcript \
  -t 8
```

This writes `/tmp/transcript.txt` with the transcription. The skill reads from there.

For audio formats other than wav, preprocess with ffmpeg:

```bash
ffmpeg -i input.m4a -ar 16000 -ac 1 -c:a pcm_s16le /tmp/audio.wav
```

## Realistic expectations on the HP's Haswell i5

- A 30-minute call file transcribes in roughly **30-60 minutes** with the `medium.en` model. Slower than real-time. Acceptable for one-off use, not for routine multi-call days.
- If speed becomes intolerable, switch to `small.en` (model file ~500 MB) — roughly real-time on a Haswell i5. Quality drops noticeably but still readable.
- Even smaller: `base.en` — faster than real-time, quality is rough. Useful only for searchability, not for content review.

## Skill triggers

The user has explicitly said this skill is low priority. Don't auto-run it. It's available ad-hoc when the user asks "summarize this call recording" pointing at a file.

## Don't touch

Everything else in the skill (diarization parsing if the model supports it, the note-writing template, the relationship to person notes in `04 People/`) stays.
