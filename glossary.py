#!/usr/bin/env python3
"""Pick the words to review after each segment, from the writers' candidates.

    python3 glossary.py [--date 2026-11-04] [--max N] [--recent 5]

Each segment writer adds a "glossary" list to its build/seg-*.json: the words and phrases
an N2-N3 listener might not catch, in the order they appear:
    {"term": "注目が集まる", "reading": "ちゅうもくがあつまる", "en": "to draw attention",
     "line": "the segment line it appears in, copied exactly"}

This filters them against Anki and recent episodes, and writes build/glossary-YYYYMMDD.json,
which episode.py plays after each segment. A candidate is:
- kept first if it's on a studied Core or Production card that is still young (interval
  under 21 days) or was failed in the last week: a word Matt is learning (cards not yet
  studied count as not in Anki);
- dropped if it's on a mature card (21 days or more): a word he knows;
- dropped if it's a single N5 or N4 word on the JLPT list (phrases are never dropped this
  way, since each part of a phrase can be easy when the whole isn't);
- dropped if an earlier episode in the last --recent reviewed it, unless it's young in Anki;
- dropped if its line isn't in the segment and the term doesn't appear in any line.
At most CAPS[segment] are kept (10 after the news, 7 after the shorter column and essay;
--max sets one cap for all): learning words first, then the rest spread evenly through
the segment, played in the order they appear.
"""
import argparse
import datetime
import json
import os

from cards import BUILD, CORE, PROD, field, invoke, notes, plain

ROOT = os.path.dirname(os.path.abspath(__file__))
CAPS = {"news": 10, "essay": 7, "translation": 7, "dialogue": 7}  # most words in each word list
SEGMENTS = ["news", "essay", "translation", "dialogue"]
MATURE = 21  # days
# Standard (unofficial) JLPT word list, word -> level 1-5 (github.com/elzup/jlpt-word-list).
JLPT_FILE = os.environ.get("KIKITORI_JLPT", os.path.expanduser("~/.claude/skills/anki/jlpt.json"))


def anki_status(term):
    """'young', 'mature', or None if no Core or Production card has this word."""
    q = term.replace('"', "")
    hits = [n for n in notes(f'{CORE} ("Vocabulary-Kanji:*{q}*" or "Vocabulary-Kana:{q}")')
            if term in (plain(field(n, "Vocabulary-Kanji")), plain(field(n, "Vocabulary-Kana")))]
    hits += [n for n in notes(f'{PROD} "Word:*{q}*"') if plain(field(n, "Word")) == term]
    if not hits:
        return None
    infos = [c for c in invoke("cardsInfo", cards=[c for n in hits for c in n["cards"]]) if c["type"] != 0]
    if not infos:  # cards not yet studied count as not in Anki
        return None
    failed = invoke("findCards", query=f"cid:{','.join(str(c['cardId']) for c in infos)} rated:7:1")
    return "young" if failed or max(c["interval"] for c in infos) < MATURE else "mature"


def recent_terms(day, count):
    path = os.path.join(BUILD, "history.jsonl")
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rows = [r for r in rows if r["date"] < day.isoformat()][-count:]
    return {t for r in rows for t in r.get("glossary", [])}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--max", type=int, help="most words per segment, overriding CAPS")
    p.add_argument("--recent", type=int, default=5, help="skip words reviewed in this many earlier episodes")
    a = p.parse_args()
    day = datetime.date.fromisoformat(a.date)
    jlpt = {}
    if os.path.exists(JLPT_FILE):
        with open(JLPT_FILE) as f:
            jlpt = json.load(f)
    else:
        print(f"No JLPT list at {JLPT_FILE}; not filtering easy words.")
    recent = recent_terms(day, a.recent)

    out = {"date": day.isoformat(), "segments": {}, "dropped": []}
    for name in SEGMENTS:
        path = os.path.join(BUILD, f"seg-{name}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            seg = json.load(f)
        texts = [item["text"] for item in seg["lines"] if "text" in item]
        kept = []
        for order, c in enumerate(seg.get("glossary", [])):
            term = c["term"].strip()

            def drop(why):
                out["dropped"].append({"segment": name, "term": term, "why": why})

            line = c.get("line", "").strip()
            if line not in texts:
                line = next((t for t in texts if term in t), None)
                if not line:
                    drop("not in the segment")
                    continue
            status = anki_status(term)
            if status == "mature":
                drop("mature in Anki")
            elif status is None and jlpt.get(term) in (4, 5):
                drop(f"N{jlpt[term]}")
            elif status is None and term in recent:
                drop("reviewed in a recent episode")
            elif any(k["term"] == term for k in kept):
                drop("duplicate")
            else:
                kept.append({"term": term, "reading": c.get("reading", ""), "en": c["en"], "line": line,
                             "anki": status or "new", "_order": order})
        cap = a.max or CAPS[name]
        if len(kept) > cap:  # learning words first, the rest spread evenly through the segment
            young = [k for k in kept if k["anki"] == "young"][:cap]
            rest = [k for k in kept if k["anki"] != "young"]
            slots = cap - len(young)
            picks = {round(i * len(rest) / slots) for i in range(slots)} if slots else set()
            chosen = young + [k for i, k in enumerate(rest) if i in picks]
            for k in kept:
                if k not in chosen:
                    out["dropped"].append({"segment": name, "term": k["term"], "why": f"over the cap of {cap}"})
            kept = sorted(chosen, key=lambda k: k["_order"])
        for k in kept:
            del k["_order"]
        if kept:
            out["segments"][name] = kept

    dest = os.path.join(BUILD, f"glossary-{day:%Y%m%d}.json")
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for name, items in out["segments"].items():
        print(f"{name}: " + "、".join(k["term"] + ("*" if k["anki"] == "young" else "") for k in items))
    if out["dropped"]:
        print("dropped: " + "、".join(f"{d['term']} ({d['why']})" for d in out["dropped"]))
    print(dest)


if __name__ == "__main__":
    main()
