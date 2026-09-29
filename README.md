# Boson AI plugins

Agent plugins for Boson AI models. Works with **Claude Code** and **Codex**
(both read the `.claude-plugin/` manifests; the skills follow the shared
`SKILL.md` format).

## boson-tts

Lets your coding agent generate speech from text with Boson AI's Higgs TTS 3
(`POST https://api.boson.ai/v1/audio/speech`). Ask things like "read this aloud",
"make an mp3 voiceover of this paragraph", "用 nora 的声音把这段话生成语音".

### Install — Claude Code

```
/plugin marketplace add boson-ai/boson-plugins
/plugin install boson-tts@boson-ai
```

### Install — Codex

Add the marketplace in the Codex app's plugin settings using
`https://github.com/boson-ai/boson-plugins.git`, or add it to `~/.codex/config.toml`:

```toml
[marketplaces.boson-ai]
source_type = "git"
source = "https://github.com/boson-ai/boson-plugins.git"
```

Then install **Boson TTS** (`boson-tts@boson-ai`) from the plugin list.

### Configure

Set your API key (in `~/.zshrc` / `~/.bashrc`) and restart the agent:

```bash
export BOSON_API_KEY=your_key_here
```

Requirements: Python 3.8+. Optional: `ffmpeg` (needed to stitch long text into
mp3/opus/etc; without it long text is saved as .wav).

### Install without a plugin system

Copy `plugins/boson-tts/skills/boson-tts/` into your agent's skills directory:
`~/.claude/skills/` (Claude Code), `~/.codex/skills/` or `~/.agents/skills/` (Codex),
or a project's `.claude/skills/` to share it through a repo.
