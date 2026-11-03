"""Text-to-speech engines. Each returns a 24 kHz mono 16-bit WAV file path.

- polly: Amazon Polly neural Japanese voices (Kazuha, Tomoko, Takumi), profile new-account.
- aivis: AivisSpeech Engine running locally on port 10101 (free, Style-Bert-VITS2 models).
- say:   macOS `say`, used for the English parts.
"""
import hashlib
import json
import os
import subprocess
import urllib.parse
import urllib.request

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "tts-cache")
AWS = ["aws", "--profile", "new-account", "--region", "us-east-1"]
AIVIS = "http://127.0.0.1:10101"
RATE = "24000"


def _cached(engine, voice, text, opts=""):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(f"{engine}|{voice}|{opts}|{text}".encode()).hexdigest()[:20]
    return os.path.join(CACHE, f"{engine}-{key}.wav")


def _to_wav(src, dst):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", RATE,
                    "-sample_fmt", "s16", dst], check=True)


def polly(text, voice):
    out = _cached("polly", voice, text)
    if not os.path.exists(out):
        mp3 = out + ".mp3"
        subprocess.run(AWS + ["polly", "synthesize-speech", "--engine", "neural", "--voice-id", voice,
                              "--output-format", "mp3", "--sample-rate", RATE, "--text", text, mp3],
                       check=True, stdout=subprocess.DEVNULL)
        _to_wav(mp3, out)
        os.remove(mp3)
    return out


def aivis_speakers():
    """{speaker name: {style name: style id}}"""
    with urllib.request.urlopen(f"{AIVIS}/speakers") as r:
        return {s["name"]: {st["name"]: st["id"] for st in s["styles"]} for s in json.load(r)}


def aivis(text, style_id, speed=1.0):
    out = _cached("aivis", str(style_id), text, f"speed={speed}")
    if not os.path.exists(out):
        q = urllib.parse.urlencode({"text": text, "speaker": style_id})
        with urllib.request.urlopen(urllib.request.Request(f"{AIVIS}/audio_query?{q}", method="POST")) as r:
            query = json.load(r)
        query["speedScale"] = speed
        req = urllib.request.Request(f"{AIVIS}/synthesis?speaker={style_id}", json.dumps(query).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r, open(out + ".raw.wav", "wb") as f:
            f.write(r.read())
        _to_wav(out + ".raw.wav", out)
        os.remove(out + ".raw.wav")
    return out


def say(text, voice="Samantha"):
    out = _cached("say", voice, text)
    if not os.path.exists(out):
        aiff = out + ".aiff"
        subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
        _to_wav(aiff, out)
        os.remove(aiff)
    return out


def silence(seconds):
    out = _cached("silence", "", f"{seconds:.2f}")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"anullsrc=r={RATE}:cl=mono", "-t", f"{seconds:.2f}", "-sample_fmt", "s16", out],
                       check=True)
    return out
