#!/usr/bin/env python3
"""Expand a JLPT-style dialogue spec into build/seg-dialogue.json.

    python3 dialogue.py build/dialogue-src.json

Spec:
    {"intro_en": "Part three. A JLPT-style dialogue, with four questions at the end.",
     "setup": "家で、男の人と女の人が話しています。話を聞いて、あとの質問に答えてください。",
     "lines": [["f", "ねえ、..."], ["m", "えっ、..."]],
     "questions": [{"q": "質問1。...", "choices": ["駅から遠いから", "...", "...", "..."],
                    "answer": 3, "en": "Question 1: why she wants to move. Answer 3: ..."}],
     "vocab_used": ["気が気でない", "..."]}

The narrator reads the setup, the speakers ("f", "m") act the dialogue, then the narrator
asks each question with its four choices and a 6-second pause, a chime, and the answers
in Japanese with an English explanation.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
N = "narrator"


def expand(spec):
    lines = [{"say": N, "text": spec["setup"]}, {"pause": 1.0}]
    for role, text in spec["lines"]:
        if role not in ("f", "m"):
            raise SystemExit(f"dialogue roles must be 'f' or 'm', got {role!r}")
        lines.append({"say": role, "text": text})
    lines += [{"pause": 1.5}, {"say": N, "text": "では、質問です。"}, {"pause": 0.8}]
    for q in spec["questions"]:
        if len(q["choices"]) != 4 or not 1 <= q["answer"] <= 4:
            raise SystemExit(f"each question needs 4 choices and an answer 1-4: {q['q']}")
        choices = "".join(f"{i}、{c.rstrip('。')}。" for i, c in enumerate(q["choices"], 1))
        lines += [{"say": N, "text": q["q"]}, {"pause": 0.6}, {"say": N, "text": choices}, {"pause": 6.0}]
    lines += [{"chime": True}, {"pause": 0.8}, {"say": N, "text": "正解を確認します。"}, {"pause": 0.6}]
    for i, q in enumerate(spec["questions"], 1):
        lines += [{"say": N, "text": f"質問{i}は、{q['answer']}番です。"}, {"pause": 0.4},
                  {"say": "en", "text": q["en"]}, {"pause": 1.0}]
    return {"title_en": "JLPT-style dialogue", "intro_en": spec["intro_en"], "lines": lines,
            "vocab_used": spec.get("vocab_used", [])}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    with open(sys.argv[1]) as f:
        seg = expand(json.load(f))
    out = os.path.join(ROOT, "build", "seg-dialogue.json")
    with open(out, "w") as f:
        json.dump(seg, f, ensure_ascii=False, indent=1)
    print(out)


if __name__ == "__main__":
    main()
