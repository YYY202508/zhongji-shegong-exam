# -*- coding: utf-8 -*-
"""法规数字和期限填空。答错时回看对应口诀。"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CARDS = SKILL / "suji" / "cards.jsonl"
SESSION = SKILL / "runtime" / "numbers.json"
UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(周岁|日|天|年|级|个月|倍|%|人|元)")


def load_cards() -> list[dict]:
    rows = []
    with CARDS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def blanks(text: str) -> tuple[str, list[str]]:
    found: list[str] = []

    def repl(match: re.Match) -> str:
        if len(found) >= 3:
            return match.group(0)
        found.append(match.group(1))
        return "____" + match.group(2)

    prompt = re.sub(r"\s+", " ", UNIT.sub(repl, text)).strip()
    return prompt, found


def build_items(chapter: str) -> list[dict]:
    cards = load_cards()
    koujue = {
        (row["chapter"], row["title"]): row.get("body") or ""
        for row in cards
        if row.get("subject") == "法规与政策" and row.get("kind") == "口诀"
    }
    items = []
    for row in cards:
        if row.get("subject") != "法规与政策" or row.get("kind") != "要点":
            continue
        if chapter and chapter not in row.get("chapter", ""):
            continue
        prompt, answers = blanks(row.get("body") or "")
        if not answers:
            continue
        marks = [match.start() for match in re.finditer("____", prompt)]
        start = max(0, marks[0] - 30)
        end = min(len(prompt), marks[-1] + 12)
        shown = prompt[start:end]
        shown = re.sub(
            r"(?<!_)\d+(?:\.\d+)?(?=\s*(?:周岁|日|天|年|级|个月|倍|%|人|元))",
            "□",
            shown,
        )
        items.append(
            {
                "chapter": row["chapter"],
                "title": row["title"],
                "prompt": shown,
                "answers": answers,
                "koujue": koujue.get((row["chapter"], row["title"]), ""),
                "detail": re.sub(r"\s+", " ", row.get("body") or "")[:240],
            }
        )
    random.shuffle(items)
    return items


def load_session() -> dict | None:
    if not SESSION.exists():
        return None
    return json.loads(SESSION.read_text(encoding="utf-8"))


def save_session(data: dict | None) -> None:
    if data is None:
        if SESSION.exists():
            SESSION.unlink()
        return
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pending() -> bool:
    session = load_session()
    return bool(session) and session.get("cursor", 0) < len(session.get("items") or [])


def show_current() -> None:
    session = load_session()
    if not session or not pending():
        print("数字填空已经做完。")
        return
    item = session["items"][session["cursor"]]
    index = session["cursor"] + 1
    total = len(session["items"])
    print(f"【法规与政策 · {item['chapter']}】数字填空 {index}/{total}")
    print(item["title"])
    print(item["prompt"])
    print("按空格顺序填数字，例如：60 16")


def cmd_start(chapter: str, n: int) -> None:
    items = build_items(chapter)[:n]
    if not items:
        print("这一章没有带数字或期限的要点。")
        save_session({"cursor": 0, "items": [], "correct": 0, "done": True})
        return
    save_session({"cursor": 0, "items": items, "correct": 0, "done": False})
    show_current()


def cmd_grade(answer: str) -> None:
    session = load_session()
    if not session or not pending():
        print("没有进行中的数字填空。")
        return
    item = session["items"][session["cursor"]]
    given = re.findall(r"\d+(?:\.\d+)?", answer or "")
    ok = given == item["answers"]
    if ok:
        session["correct"] += 1
        print("对。")
    else:
        print("错。正确答案：" + "、".join(item["answers"]))
        if item.get("koujue"):
            print("口诀：" + item["koujue"])
        print("原句：" + item["detail"])
    session["cursor"] += 1
    if session["cursor"] >= len(session["items"]):
        session["done"] = True
        save_session(session)
        print(f"数字填空 {session['correct']}/{len(session['items'])}。说「继续」进入章节测验。")
        return
    save_session(session)
    print()
    show_current()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--chapter", default="")
    start.add_argument("--n", type=int, default=3)
    grade = sub.add_parser("grade")
    grade.add_argument("--answer", nargs="*", default=[])
    args = parser.parse_args()
    if args.cmd == "start":
        cmd_start(args.chapter, args.n)
    else:
        cmd_grade(" ".join(args.answer))


if __name__ == "__main__":
    main()
