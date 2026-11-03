#!/usr/bin/env python3
"""Render an episode script (JSON) to an MP3 with a chosen Japanese voice engine.

    python3 build.py SCRIPT.json --engine polly|aivis [--out build/episode.mp3]

Script format:
    {"title": "...", "description": "...",
     "lines": [{"say": "f", "text": "..."}, {"pause": 1.5}, {"say": "en", "text": "..."}]}

Roles: narrator, f (woman), m (man), card (sentence reader), en (English).
Each spoken line is followed by a short gap unless the next item is an explicit pause.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import tts

# Japanese role -> voice, per engine. English always uses macOS `say`.
VOICES = {
    "polly": {"narrator": "Tomoko", "f": "Kazuha", "m": "Takumi", "card": "Kazuha"},
    "aivis": {"narrator": ("まお", "ノーマル"), "f": ("コハク", "ノーマル"),
              "m": ("阿井田 茂", "ノーマル"), "card": ("まお", "ノーマル")},
}
GAP = 0.45          # between consecutive lines
LOUDNESS = "I=-16:TP=-1.5:LRA=11"  # podcast-standard loudness


def render_line(engine, role, text, speakers):
    if role == "en":
        return tts.say(text)
    voice = VOICES[engine][role]
    if engine == "polly":
        return tts.polly(text, voice)
    name, style = voice
    styles = speakers[name]
    return tts.aivis(text, styles.get(style, next(iter(styles.values()))))


def build(script, engine, out):
    speakers = tts.aivis_speakers() if engine == "aivis" else {}
    parts, lines = [], script["lines"]
    for i, item in enumerate(lines):
        if "pause" in item:
            parts.append(tts.silence(item["pause"]))
            continue
        parts.append(render_line(engine, item["say"], item["text"], speakers))
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is not None and "pause" not in nxt:
            parts.append(tts.silence(GAP))
    parts = [tts.silence(0.6)] + parts + [tts.silence(1.0)]

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.writelines(f"file '{p}'\n" for p in parts)
        listing = f.name
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                    "-af", f"loudnorm={LOUDNESS}", "-ac", "1", "-ar", "44100", "-b:a", "96k",
                    "-metadata", f"title={script['title']}", "-metadata", "artist=Kikitori", out], check=True)
    os.remove(listing)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("script")
    p.add_argument("--engine", choices=sorted(VOICES), required=True)
    p.add_argument("--out")
    a = p.parse_args()
    with open(a.script) as f:
        script = json.load(f)
    out = a.out or os.path.join("build", f"{os.path.splitext(os.path.basename(a.script))[0]}-{a.engine}.mp3")
    build(script, a.engine, out)
    print(out)


if __name__ == "__main__":
    sys.exit(main())
