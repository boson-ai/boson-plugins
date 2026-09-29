#!/usr/bin/env python3
"""Boson AI Higgs TTS 3 client (stdlib only).

POST {BOSON_BASE_URL:-https://api.boson.ai/v1}/audio/speech
Docs: https://docs.boson.ai/models/higgs-tts/overview

Long text is split on sentence boundaries into chunks, each chunk is
synthesized as WAV, the PCM is concatenated, and the result is converted to
the requested format with ffmpeg (falls back to .wav if ffmpeg is missing).
Prints a one-line JSON summary to stdout on success.
"""

import argparse
import base64
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

DEFAULT_BASE_URL = "https://api.boson.ai/v1"
MODEL = "higgs-tts-3"
FORMATS = ["mp3", "wav", "opus", "aac", "flac", "pcm"]
MAX_INPUT_CHARS = 5000
MAX_REF_BYTES = 10 * 1024 * 1024
KEY_HELP = (
    "Get a key: sign in at https://www.boson.ai/workspace, then create one at "
    "https://www.boson.ai/workspace/api-key (keys look like bai-...). Claim the free "
    "trial credit there too, or calls fail with 429 insufficient_quota. Then add "
    "`export BOSON_API_KEY=bai-...` to your shell profile and restart the agent. "
    "Guide: https://docs.boson.ai/set-up-your-account"
)
# Leading delivery tags (emotion/style/speed/pitch/expressiveness) apply to the
# whole turn, so they are re-applied to every chunk.
LEADING_TAGS_RE = re.compile(r"^\s*((?:<\|[a-z]+:[a-z_]+\|>\s*)+)")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？；;…])\s*|\n+")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def read_text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text is None or args.text == "-":
        return sys.stdin.read()
    return args.text


def resolve_ref_audio(ref):
    """Local path -> base64 data URI; URLs / data URIs / raw base64 pass through."""
    if ref is None or ref.startswith(("http://", "https://", "data:")):
        return ref
    path = os.path.expanduser(ref)
    if not os.path.isfile(path):
        return ref  # assume caller passed raw base64
    size = os.path.getsize(path)
    if size > MAX_REF_BYTES:
        die(f"ref audio {path} is {size} bytes; inline limit is 10 MB (pass a URL instead)")
    mime = mimetypes.guess_type(path)[0] or "audio/wav"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def split_text(text, limit):
    text = text.strip()
    m = LEADING_TAGS_RE.match(text)
    prefix = m.group(1).strip() + " " if m else ""
    body = text[m.end():] if m else text
    if len(text) <= limit:
        return [text]

    budget = max(50, limit - len(prefix))
    chunks, cur = [], ""
    for sent in (s.strip() for s in SENTENCE_SPLIT_RE.split(body)):
        if not sent:
            continue
        while len(sent) > budget:  # hard-split an overlong sentence
            cut = sent.rfind(" ", 0, budget)
            cut = cut if cut > budget // 2 else budget
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        sep = "" if not cur or re.match(r"[　-鿿＀-￯]", sent[:1]) else " "
        if len(cur) + len(sep) + len(sent) > budget:
            chunks.append(cur)
            cur = sent
        else:
            cur = f"{cur}{sep}{sent}"
    if cur:
        chunks.append(cur)
    return [prefix + c for c in chunks]


def synthesize(base_url, api_key, payload, timeout):
    req = urllib.request.Request(
        base_url.rstrip("/") + "/audio/speech",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:2000]
            if e.code == 401:
                die(f"HTTP 401 from Boson TTS (API key missing or invalid): {body}\n{KEY_HELP}")
            if e.code == 429 and "insufficient_quota" in body:
                die(f"HTTP 429 insufficient_quota: the account has no credit. Claim the free trial "
                    f"credit or top up at https://www.boson.ai/workspace/billing/overview\n{body}")
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            die(f"HTTP {e.code} from Boson TTS: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            die(f"request failed: {e}")


def unwrap(data, ctype, want_timestamps):
    """Returns (audio_bytes, timestamps_or_None)."""
    if "application/json" in ctype or (want_timestamps and data[:1] == b"{"):
        obj = json.loads(data)
        return base64.b64decode(obj["audio"]), obj.get("timestamps")
    return data, None


def wav_duration(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / float(w.getframerate())


def convert(src_path, dst_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src_path, dst_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"warning: ffmpeg failed: {r.stderr.strip()}", file=sys.stderr)
        return False
    return True


def main():
    p = argparse.ArgumentParser(description="Text-to-speech via Boson AI Higgs TTS 3")
    p.add_argument("text", nargs="?", help="text to speak ('-' or omit to read stdin)")
    p.add_argument("-f", "--file", help="read text from a UTF-8 file")
    p.add_argument("-o", "--output", help="output path (default ./tts_<time>.<format>)")
    p.add_argument("-v", "--voice", help="preset voice: chloe, eleanor, jake, marcus, nora, oliver (default: server default)")
    p.add_argument("--format", choices=FORMATS, help="audio format (default: from -o extension, else mp3)")
    p.add_argument("--ref-audio", help="voice-clone reference: local file, URL, data URI or base64")
    p.add_argument("--ref-text", help="verbatim transcript of the reference audio")
    p.add_argument("--tn-language", help="ISO 639-1 code for text normalization (auto if omitted)")
    p.add_argument("--no-tn", action="store_true", help="disable text normalization")
    p.add_argument("--timestamps", action="store_true",
                   help="also write word timestamps to <output>.timestamps.json (en/zh/es only)")
    p.add_argument("--chunk-chars", type=int, default=300,
                   help="split text longer than this on sentence boundaries (default 300, max 5000)")
    p.add_argument("--play", action="store_true", help="play the result (afplay/ffplay)")
    p.add_argument("--timeout", type=float, default=120, help="per-request timeout seconds")
    args = p.parse_args()

    api_key = os.environ.get("BOSON_API_KEY")
    if not api_key:
        die(f"BOSON_API_KEY is not set.\n{KEY_HELP}")
    base_url = os.environ.get("BOSON_BASE_URL", DEFAULT_BASE_URL)

    text = read_text(args).strip()
    if not text:
        die("no text to synthesize")

    fmt = args.format
    if not fmt and args.output:
        ext = os.path.splitext(args.output)[1].lstrip(".").lower()
        fmt = ext if ext in FORMATS else None
    fmt = fmt or "mp3"
    out = args.output or f"tts_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
    out = os.path.abspath(os.path.expanduser(out))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    base = {"model": MODEL}
    if args.voice:
        base["voice"] = args.voice.lower()
    if args.ref_audio:
        base["ref_audio"] = resolve_ref_audio(args.ref_audio)
        if args.ref_text:
            base["ref_text"] = args.ref_text
    if args.no_tn:
        base["enable_tn"] = False
    if args.tn_language:
        base["tn_language"] = args.tn_language
    if args.timestamps:
        base["timestamps"] = True

    chunks = split_text(text, min(max(args.chunk_chars, 50), MAX_INPUT_CHARS))
    summary = {"output": out, "format": fmt, "chunks": len(chunks), "chars": len(text)}

    if len(chunks) == 1:
        data, ctype = synthesize(base_url, api_key, {**base, "input": chunks[0], "response_format": fmt}, args.timeout)
        audio, ts = unwrap(data, ctype, args.timestamps)
        with open(out, "wb") as f:
            f.write(audio)
        if fmt == "wav":
            summary["duration_sec"] = round(wav_duration(audio), 2)
    else:
        # Synthesize each chunk as WAV, stitch PCM, then transcode once.
        params, frames, ts, offset = None, [], [], 0.0
        for i, chunk in enumerate(chunks, 1):
            print(f"[{i}/{len(chunks)}] {len(chunk)} chars", file=sys.stderr)
            data, ctype = synthesize(base_url, api_key, {**base, "input": chunk, "response_format": "wav"}, args.timeout)
            audio, chunk_ts = unwrap(data, ctype, args.timestamps)
            with wave.open(io.BytesIO(audio)) as w:
                cur = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                if params and cur != params:
                    die(f"chunk {i} audio params {cur} differ from {params}")
                params = cur
                frames.append(w.readframes(w.getnframes()))
                dur = w.getnframes() / float(w.getframerate())
            for t in chunk_ts or []:
                ts.append({**t, "start": round(t["start"] + offset, 3), "end": round(t["end"] + offset, 3)})
            offset += dur
        ts = ts if args.timestamps else None
        summary["duration_sec"] = round(offset, 2)

        pcm = b"".join(frames)
        if fmt == "pcm":
            with open(out, "wb") as f:
                f.write(pcm)
        else:
            wav_target = out if fmt == "wav" else tempfile.mktemp(suffix=".wav")
            with wave.open(wav_target, "wb") as w:
                w.setnchannels(params[0]); w.setsampwidth(params[1]); w.setframerate(params[2])
                w.writeframes(pcm)
            if fmt != "wav":
                if convert(wav_target, out):
                    os.remove(wav_target)
                else:
                    out = os.path.splitext(out)[0] + ".wav"
                    shutil.move(wav_target, out)
                    summary.update(output=out, format="wav",
                                   warning="ffmpeg unavailable; saved WAV instead")

    if args.timestamps:
        ts_path = os.path.splitext(out)[0] + ".timestamps.json"
        with open(ts_path, "w", encoding="utf-8") as f:
            json.dump(ts, f, ensure_ascii=False, indent=2)
        summary["timestamps"] = ts_path if ts else None
        if not ts:
            summary["timestamps_note"] = "server returned no timestamps (only en/zh/es are supported)"

    summary["bytes"] = os.path.getsize(out)
    print(json.dumps(summary, ensure_ascii=False))

    if args.play:
        player = shutil.which("afplay") or shutil.which("ffplay")
        if player:
            cmd = [player, out] if player.endswith("afplay") else [player, "-autoexit", "-nodisp", "-loglevel", "error", out]
            subprocess.run(cmd)


if __name__ == "__main__":
    main()
