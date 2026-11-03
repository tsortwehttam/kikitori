#!/usr/bin/env python3
"""Export the day's Anki cards for an episode, through AnkiConnect.

    python3 cards.py [--days N] [--max 30]

Syncs Anki with AnkiWeb (so reviews done on the phone count), then writes:
- build/cards-today.json: [{"ja", "en"}] card sentences, in this order of priority:
  cards added since the last episode was built, production cards added since then, cards
  failed in the review window, then other cards reviewed in it (shortest interval first).
- build/vocab.txt: "word (meaning)" lines for the segment writers to work in: words added
  in the last 30 days, words with production cards, and words reviewed in the window.

The review window defaults to the days since the last episode in build/history.jsonl (1 to 7).
--days also resets "added since" to that many days back.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")
ANKI = "http://127.0.0.1:8765"
CORE = 'deck:"TOP::Core" note:"RTK Core 6K"'
PROD = 'deck:"TOP::Production"'


def invoke(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    for attempt in range(60):
        try:
            with urllib.request.urlopen(urllib.request.Request(ANKI, body), timeout=60) as r:
                reply = json.load(r)
            break
        except urllib.error.URLError:
            if attempt == 0:
                subprocess.run(["open", "-g", "-a", "Anki"], check=False)
            time.sleep(1)
    else:
        raise SystemExit("AnkiConnect is not reachable. Check that Anki opens and AnkiConnect is enabled.")
    if reply.get("error"):
        raise SystemExit(f"AnkiConnect {action}: {reply['error']}")
    return reply["result"]


def plain(s):
    """Strip HTML and Anki furigana: '<b> 集客[しゅうきゃく]</b>に' -> '集客に'."""
    s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ")
    return re.sub(r"\[[^\]]*\]", "", s).replace(" ", "").strip()


def text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ")).strip()


def notes(query):
    ids = invoke("findNotes", query=query)
    return invoke("notesInfo", notes=ids) if ids else []


def field(n, k):
    return n["fields"][k]["value"] if k in n["fields"] else ""


def last_episode():
    """(days since the last episode, 1-7; when it was built, epoch seconds) or (1, None)."""
    path = os.path.join(BUILD, "history.jsonl")
    if not os.path.exists(path):
        return 1, None
    with open(path) as f:
        last = [json.loads(line) for line in f if line.strip()][-1]
    gap = (datetime.date.today() - datetime.date.fromisoformat(last["date"])).days
    return max(1, min(gap, 7)), last.get("built_at")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, help="window in days (default: since the last episode, 1-7)")
    p.add_argument("--max", type=int, default=30, help="most card sentences to include")
    a = p.parse_args()
    days, since = last_episode()
    if a.days:
        days, since = a.days, None
    since = since or time.time() - days * 86400
    added = f"added:{days + 1}"  # note ids are creation times in ms; filter to "since" below

    try:
        invoke("sync")
    except SystemExit as e:
        print(f"Sync failed, using local data: {e}")

    cards, seen = [], set()

    def add(ja, en, word):
        if ja and en and ja not in seen:
            seen.add(ja)
            cards.append({"ja": ja, "en": en, "word": word})

    for n in notes(f"{CORE} {added}"):
        if n["noteId"] / 1000 < since:
            continue
        add(plain(field(n, "Expression")), text(field(n, "Sentence-English")), plain(field(n, "Vocabulary-Kanji")))
    for n in notes(f"{PROD} {added}"):
        if n["noteId"] / 1000 < since:
            continue
        add(plain(field(n, "Japanese")), text(field(n, "English")), plain(field(n, "Word")))

    # Reviewed cards: failed ones first, then the youngest (shortest interval) first.
    failed = set(invoke("findNotes", query=f"{CORE} rated:{days}:1"))
    reviewed = notes(f"{CORE} rated:{days}")
    if reviewed:
        ivl = {c["note"]: c["interval"] for c in invoke("cardsInfo", cards=[n["cards"][0] for n in reviewed])}
        reviewed.sort(key=lambda n: (n["noteId"] not in failed, ivl.get(n["noteId"], 0)))
    for n in reviewed:
        add(plain(field(n, "Expression")), text(field(n, "Sentence-English")), plain(field(n, "Vocabulary-Kanji")))
    cards = cards[: a.max]

    vocab = {}
    for n in notes(f"{CORE} added:30") + notes('note:"RTK Core 6K" tag:produced') + reviewed[:40]:
        word = plain(field(n, "Vocabulary-Kanji"))
        if word:
            vocab.setdefault(word, text(field(n, "Vocabulary-English")))

    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "cards-today.json"), "w") as f:
        json.dump([{"ja": c["ja"], "en": c["en"]} for c in cards], f, ensure_ascii=False, indent=1)
    with open(os.path.join(BUILD, "vocab.txt"), "w") as f:
        f.writelines(f"{w} ({m})\n" for w, m in vocab.items())
    print(f"Window: {days} day(s). {len(cards)} card sentences -> build/cards-today.json; "
          f"{len(vocab)} words -> build/vocab.txt")
    print("Card words: " + "、".join(c["word"] for c in cards))


if __name__ == "__main__":
    main()
