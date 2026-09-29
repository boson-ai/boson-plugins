---
name: boson-tts
description: Generate speech audio from text with Boson AI's Higgs TTS 3 endpoint (api.boson.ai/v1/audio/speech). Use whenever the user wants text turned into voice/audio — "read this aloud", "generate a voiceover/narration/podcast intro", "make an mp3 of this", "TTS", "文字转语音", "生成语音", "配音", "读出来" — including preset voices (chloe, eleanor, jake, marcus, nora, oliver), voice cloning from a reference clip, emotion/style/prosody/sound-effect tags, word timestamps, and 100 languages. Handles long text by chunking and stitching.
---

# Boson AI Text-to-Speech (Higgs TTS 3)

Turn text into an audio file by running the bundled script `scripts/tts.py`
(path is relative to this skill's base directory — the folder containing this
SKILL.md; below it is written as `<skill-dir>/scripts/tts.py`, substitute the real
absolute path). It uses only the Python standard library (ffmpeg optional, used to
stitch long text into mp3/etc).

## Prerequisite: Boson API key

The script reads `BOSON_API_KEY` from the environment (`BOSON_BASE_URL` optionally
overrides `https://api.boson.ai/v1`). If it is missing or rejected, the script exits
with setup instructions — do not retry; walk the user through getting a key:

1. Sign in / sign up at https://www.boson.ai/workspace (Google or email code).
2. Open https://www.boson.ai/workspace/api-key → **Create API Key**, name it, and copy
   it right away (format `bai-...`).
3. Claim the **$10 free trial credit** from the banner on that page (or
   https://www.boson.ai/workspace/billing/overview). Without credit or a positive
   balance every call fails with `429 insufficient_quota`.
4. Add `export BOSON_API_KEY=bai-...` to their shell profile (`~/.zshrc` / `~/.bashrc`),
   then restart the agent so it picks up the variable.

Full guide: https://docs.boson.ai/set-up-your-account

Never ask the user to paste the key into chat, never echo or log it, and never write
it into project files that could be committed.

## Usage

```bash
python3 <skill-dir>/scripts/tts.py "Hello there!" -v chloe -o ~/Desktop/hello.mp3
```

- Text: positional arg, `-f file.txt`, or stdin (`-`). For text with quotes or
  multiple paragraphs, write it to a file first and use `-f`.
- `-o PATH` output file; format inferred from extension. Default `./tts_<time>.mp3`.
  Put output where the user will find it (their project dir or the path they gave),
  not a temp dir.
- `--format mp3|wav|opus|aac|flac|pcm` (pcm = raw 16-bit 24 kHz mono)
- `-v VOICE` preset voice (see below). Omit for the server default voice.
- `--ref-audio PATH|URL --ref-text "exact transcript"` zero-shot voice cloning.
- `--tn-language zh` normalization language hint; `--no-tn` to disable number/date expansion.
- `--timestamps` also writes `<output>.timestamps.json` with word timings (en/zh/es only).
- `--chunk-chars N` split threshold (default 300 — the API's recommended per-request size).
- `--play` play the result locally after generating (afplay on macOS).

On success the script prints one JSON line, e.g.
`{"output": "/abs/path/hello.mp3", "format": "mp3", "chunks": 1, "chars": 12, "bytes": 23456}`.
Report the output path (and duration if present) to the user; if you can send files
to the user, send the audio file. On failure it prints `error: HTTP <code> ...` to
stderr — relay the server message (400 = bad params / input too long; 401 = bad key and
429 `insufficient_quota` = no credit, both explained above).

## Choosing a voice

| voice | profile |
|---|---|
| `chloe` | female, American English, friendly & clear, informative |
| `eleanor` | female, standard American, calm & articulate — educational |
| `nora` | female, standard American, calm storyteller — narration |
| `jake` | male, American, energetic & dramatic — sports/hype |
| `marcus` | male, American, enthusiastic & confident — lecturer |
| `oliver` | male, American, calm & articulate — explanatory/reflective |

Pick one that matches the content when the user doesn't specify, and say which you
used. The model speaks 100 languages; preset voices work for non-English text too
(pass `--tn-language` for correct number/date reading). For multi-chunk text,
always set a voice (or ref audio) so every chunk sounds like the same speaker.

## Expressive control: inline tags

Tags are written directly in the text as `<|category:value|>`.

- **Leading delivery tags** — put at the very start of the text; they apply to the
  whole utterance (the script re-applies them to every chunk):
  - emotion: `elation amusement enthusiasm determination pride contentment affection
    relief contemplation confusion surprise awe longing arousal anger fear disgust
    bitterness sadness shame helplessness`
  - style: `singing shouting whispering`
  - prosody: `speed_very_slow speed_slow speed_fast speed_very_fast pitch_low
    pitch_high expressive_high expressive_low`
- **Positional pauses** — `<|prosody:pause|>` / `<|prosody:long_pause|>` exactly where
  the break should fall.
- **Sound effects** — `cough laughter crying screaming burping humming sigh sniff sneeze`.
  Put the tag right before the sound and pair it with onomatopoeia:
  `That's hilarious! <|sfx:laughter|> Hahaha.`

Example: `<|emotion:enthusiasm|><|prosody:speed_fast|> We did it! <|prosody:pause|> The launch is live.`

Only add tags when the user asks for a particular mood/delivery or the content
clearly calls for it (e.g. a dramatic script); plain text reads naturally on its own.

## Voice cloning

```bash
python3 <skill-dir>/scripts/tts.py -f script.txt \
  --ref-audio ./my_voice.wav --ref-text "Verbatim transcript of my_voice.wav, um, including fillers." \
  -o cloned.mp3
```

Reference: 5–30 s of clean single-speaker speech, no music (wav/mp3/flac/opus/aac,
≤10 MB when a local file; otherwise pass a URL). A verbatim transcript (including
filler words) noticeably improves quality. Only clone a voice the user owns or has
rights to — if that is unclear, ask before proceeding.

## Notes

- Hard API limit is 5000 chars per request; the script chunks automatically on
  sentence boundaries (Chinese/Japanese punctuation included) and stitches the audio.
  Stitching into non-wav formats needs ffmpeg; without it you get a .wav (the JSON
  summary includes a `warning`).
- Timestamps across chunks are offset so they line up with the stitched audio.
- API reference: https://docs.boson.ai/api-reference/audio/create-a-speech
