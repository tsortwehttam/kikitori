#!/usr/bin/env python3
"""Assemble a daily episode script from its segments.

    python3 episode.py [--date 2026-11-03] [--cards build/cards-today.json] [--max-cards 30] [--allow-stale]

Reads build/seg-{news,dialogue,essay,translation}.json (each {"intro_en", "lines", ...},
Japanese lines marked "say": "ja") and a card list [{"ja", "en"}], and writes
scripts/episode-YYYYMMDD.json for build.py. Each segment gets its own reader, and the
card sentences rotate through all three Japanese voices.

After the news, column, and essay come their word lists from build/glossary-YYYYMMDD.json
(written by glossary.py): each word in Japanese, English, Japanese again, then the line it
appeared in, so the episode can be played a second time with the words known.

Segment files must have been written on the episode's date (--allow-stale to skip the
check). Each run records the episode's topics and sources in build/history.jsonl, which
the next episode reads so it doesn't repeat a column topic or translated essay.
"""
import argparse
import datetime
import json
import os
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
# (segment file, reader for its "ja" lines). The dialogue sets its own roles.
SEGMENTS = [("news", "m"), ("dialogue", None), ("essay", "f"), ("translation", "narrator")]
WORDS_INTRO = {"news": "Words from the news.", "essay": "Words from the column.",
               "translation": "Words from the essay.", "dialogue": "Words from the dialogue."}
CARD_VOICES = ["card", "f", "m"]


def load(name, day, allow_stale):
    path = os.path.join(ROOT, "build", f"seg-{name}.json")
    written = datetime.date.fromtimestamp(os.path.getmtime(path))
    if written != day and not allow_stale:
        raise SystemExit(f"{path} was written on {written}, not {day}. Write today's segment first "
                         "(or pass --allow-stale).")
    with open(path) as f:
        return json.load(f)


def load_glossary(day, segs):
    """{segment: [word, ...]} from build/glossary-YYYYMMDD.json, or {} if there is none."""
    path = os.path.join(ROOT, "build", f"glossary-{day:%Y%m%d}.json")
    if not os.path.exists(path):
        if any(seg.get("glossary") for seg, _ in segs):
            raise SystemExit(f"The segments have glossary candidates but {path} is missing. "
                             "Run python3 glossary.py first.")
        return {}
    with open(path) as f:
        return json.load(f)["segments"]


def word_lines(name, words, voice):
    lines = [{"pause": 1.2}, {"section": f"Words: {name}"}, {"say": "en", "text": WORDS_INTRO[name]},
             {"pause": 1.0}]
    for w in words:
        lines += [{"say": voice, "text": w["term"]}, {"pause": 1.0}, {"say": "en", "text": w["en"]},
                  {"pause": 1.0}, {"say": voice, "text": w["term"]}, {"pause": 0.8},
                  {"say": voice, "text": w["line"]}, {"pause": 0.7}, {"chime": True}, {"pause": 0.7}]
    return lines


def record(day, title, segs, cards, glossary):
    """Replace this date's line in build/history.jsonl."""
    path = os.path.join(ROOT, "build", "history.jsonl")
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    by_name = {name: seg for (name, _), (seg, _) in zip(SEGMENTS, segs)}
    rows = [r for r in rows if r["date"] != day.isoformat()] + [{
        "date": day.isoformat(), "title": title, "cards": len(cards), "built_at": int(time.time()),
        "glossary": [w["term"] for words in glossary.values() for w in words],
        "topics": {name: seg.get("intro_en", "") for name, seg in by_name.items()},
        "sources": by_name["news"].get("sources", []) + ([by_name["translation"]["source"]]
                                                          if by_name["translation"].get("source") else []),
    }]
    with open(path, "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(rows, key=lambda r: r["date"]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--cards", default=os.path.join(ROOT, "build", "cards-today.json"))
    p.add_argument("--max-cards", type=int, default=30)
    p.add_argument("--allow-stale", action="store_true", help="use segment files written on another day")
    a = p.parse_args()
    day = datetime.date.fromisoformat(a.date)
    spoken_day = f"{day:%A}, {day:%B} {day.day}"

    with open(a.cards) as f:
        cards = json.load(f)[-a.max_cards:]
    segs = [(load(name, day, a.allow_stale), voice) for name, voice in SEGMENTS]
    glossary = load_glossary(day, segs)

    lines = [{"say": "en", "text": f"Kikitori for {spoken_day}. Today: sentences from your cards, the news, "
                                     "a JLPT-style dialogue, an opinion column, and a translated essay."},
             {"pause": 1.2},
             {"section": "Card sentences"}, {"say": "en", "text": "Part one. Sentences from your cards."},
             {"pause": 1.0}]
    for i, c in enumerate(cards):
        lines.append({"card": {"ja": c["ja"], "en": c["en"], "voice": CARD_VOICES[i % len(CARD_VOICES)]}})

    vocab, sources = set(), []
    for (name, _), (seg, voice) in zip(SEGMENTS, segs):
        lines += [{"pause": 1.2}, {"chime": True}, {"pause": 0.4}, {"chime": True}, {"pause": 1.2},
                  {"section": seg.get("title_en", "")}, {"say": "en", "text": seg["intro_en"]}, {"pause": 1.2}]
        for item in seg["lines"]:
            if item.get("say") == "ja":
                item = {**item, "say": voice}
            lines.append(item)
        if glossary.get(name):
            lines += word_lines(name, glossary[name], voice or "narrator")
        vocab.update(seg.get("vocab_used", []))
        sources += seg.get("sources", []) + ([seg["source"]] if seg.get("source") else [])
    lines += [{"pause": 1.5}, {"say": "en", "text": "That's all for today. See you tomorrow."}]

    script = {
        "title": f"{day.month}/{day.day} ({day:%a}) 聞き取り",
        "description": "Cards, news, JLPT dialogue, column, translated essay. Vocabulary: "
                       + "、".join(sorted(vocab)) + (". Sources: " + " ".join(sources) if sources else ""),
        "lines": lines,
    }
    out = os.path.join(ROOT, "scripts", f"episode-{day:%Y%m%d}.json")
    with open(out, "w") as f:
        json.dump(script, f, ensure_ascii=False, indent=1)
    record(day, script["title"], segs, cards, glossary)
    print(out)
    print(script["title"])


if __name__ == "__main__":
    main()
