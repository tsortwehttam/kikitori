#!/usr/bin/env python3
"""Render an episode script (JSON) to an MP3 with a chosen Japanese voice engine.

    python3 build.py SCRIPT.json --engine polly|aivis [--out build/episode.mp3]

Script format:
    {"title": "...", "description": "...",
     "lines": [{"say": "f", "text": "..."}, {"pause": 1.5}, {"say": "en", "text": "..."},
               {"card": {"ja": "...", "en": "..."}}, {"chime": true}]}

A "card" item plays Japanese, English, then the Japanese again, followed by a chime.

Roles: narrator, f (woman), m (man), card (sentence reader), en (English).
A role can also name a voice directly, for auditions: "aivis:花音", "polly:Ruth:generative", "say:Samantha".
Each spoken line is followed by a short gap unless the next item is an explicit pause.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import tts

# Japanese role -> voice, per engine. English uses EN_VOICE whatever the engine.
EN_VOICE = "say:Samantha"
VOICES = {
    "polly": {"narrator": "Tomoko", "f": "Kazuha", "m": "Takumi", "card": "Kazuha"},
    "aivis": {"narrator": ("花音", "ノーマル"), "f": ("わかな", "ノーマル"),
              "m": ("阿井田 茂", "ノーマル"), "card": ("花音", "ノーマル")},
}
GAP = 0.45          # between consecutive lines
CARD_PAUSE = 1.2    # inside a card: after the Japanese and after the English
LOUDNESS = "I=-16:TP=-1.5:LRA=11"  # podcast-standard loudness


def expand(lines):
    """Turn card items into their spoken lines, pauses, and closing chime."""
    out = []
    for item in lines:
        if "card" in item:
            ja, en = item["card"]["ja"], item["card"]["en"]
            out += [{"say": "card", "text": ja}, {"pause": CARD_PAUSE}, {"say": "en", "text": en},
                    {"pause": CARD_PAUSE}, {"say": "card", "text": ja}, {"pause": 0.7},
                    {"chime": True}, {"pause": 0.7}]
        else:
            out.append(item)
    return out


def render_line(engine, role, text, speakers):
    if role == "en":
        role = EN_VOICE
    if ":" in role:  # an explicit voice
        kind, *rest = role.split(":")
        if kind == "say":
            return tts.say(text, rest[0])
        if kind == "polly":
            return tts.polly(text, *rest)
        engine, voice = "aivis", (rest[0], "ノーマル")
    else:
        voice = VOICES[engine][role]
        if engine == "polly":
            return tts.polly(text, voice)
    name, style = voice
    if not speakers:
        speakers.update(tts.aivis_speakers())
    match = next(k for k in speakers if k.startswith(name))
    styles = speakers[match]
    return tts.aivis(text, styles.get(style, next(iter(styles.values()))))


def build(script, engine, out):
    speakers = tts.aivis_speakers() if engine == "aivis" else {}
    parts, lines = [], expand(script["lines"])
    for i, item in enumerate(lines):
        if "pause" in item:
            parts.append(tts.silence(item["pause"]))
            continue
        if "chime" in item:
            parts.append(tts.chime())
            continue
        parts.append(render_line(engine, item["say"], item["text"], speakers))
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is not None and "say" in nxt:
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
