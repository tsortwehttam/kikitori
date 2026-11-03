#!/usr/bin/env python3
"""Assemble a daily episode script from its segments.

    python3 episode.py [--date 2026-11-03] [--cards build/cards-today.json] [--max-cards 29]

Reads build/seg-{news,dialogue,essay,translation}.json (each {"intro_en", "lines", ...},
Japanese lines marked "say": "ja") and a card list [{"ja", "en"}], and writes
scripts/episode-YYYYMMDD.json for build.py. Each segment gets its own reader, and the
card sentences rotate through all three Japanese voices.
"""
import argparse
import datetime
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
# (segment file, reader for its "ja" lines). The dialogue sets its own roles.
SEGMENTS = [("news", "m"), ("dialogue", None), ("essay", "f"), ("translation", "narrator")]
CARD_VOICES = ["card", "f", "m"]


def load(name):
    with open(os.path.join(ROOT, "build", f"seg-{name}.json")) as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--cards", default=os.path.join(ROOT, "build", "cards-today.json"))
    p.add_argument("--max-cards", type=int, default=29)
    a = p.parse_args()
    day = datetime.date.fromisoformat(a.date)
    spoken_day = f"{day:%A}, {day:%B} {day.day}"

    with open(a.cards) as f:
        cards = json.load(f)[-a.max_cards:]
    segs = [(load(name), voice) for name, voice in SEGMENTS]

    lines = [{"say": "en", "text": f"Kikitori for {spoken_day}. Today: sentences from your cards, the news, "
                                     "a JLPT-style dialogue, an opinion column, and a translated essay."},
             {"pause": 1.2},
             {"section": "Card sentences"}, {"say": "en", "text": "Part one. Sentences from your cards."},
             {"pause": 1.0}]
    for i, c in enumerate(cards):
        lines.append({"card": {"ja": c["ja"], "en": c["en"], "voice": CARD_VOICES[i % len(CARD_VOICES)]}})

    vocab, sources = set(), []
    for seg, voice in segs:
        lines += [{"pause": 1.2}, {"chime": True}, {"pause": 0.4}, {"chime": True}, {"pause": 1.2},
                  {"section": seg.get("title_en", "")}, {"say": "en", "text": seg["intro_en"]}, {"pause": 1.2}]
        for item in seg["lines"]:
            if item.get("say") == "ja":
                item = {**item, "say": voice}
            lines.append(item)
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
    print(out)


if __name__ == "__main__":
    main()
