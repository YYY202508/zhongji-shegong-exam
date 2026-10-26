# -*- coding: utf-8 -*-
"""实务案例写作。用户只交答案，采分由教练判断后记分。"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import quiz
from chapters import same_chapter

SKILL = Path(__file__).resolve().parent.parent
BANK = SKILL / "questions" / "bank.jsonl"
SESSION = SKILL / "runtime" / "case_write.json"
ANALYSIS = ["问题", "理论", "目标", "介入"]
PLAN = ["对象", "目标", "理论", "内容"]


def is_plan(q: dict) -> bool:
    return "方案设计" in (q.get("stem") or "")


def load_cases(chapter: str) -> list[dict]:
    rows = []
    with BANK.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("level") != "中级" or row.get("subject") != "实务" or row.get("type") != "case":
                continue
            if row.get("kind") != "真题" or len(row.get("stem") or "") < 180:
                continue
            rows.append(row)
    if chapter:
        matched = [row for row in rows if same_chapter(chapter, row.get("chapter") or "")]
        if matched:
            rows = matched
    random.shuffle(rows)
    return rows


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
    return bool(session) and not session.get("graded")


def show() -> None:
    session = load_session()
    if not session:
        print("没有进行中的案例写作。")
        return
    kind = "方案设计" if session.get("plan") else "案例分析"
    layers = "、".join(session["layers"])
    print(f"【实务 · {session['chapter']}】{kind}（每层 5 分，共 20 分）")
    print(f"请按这四层写完发过来：{layers}。我来打分。")
    print(session["stem"])


def cmd_start(chapter: str, key: str) -> None:
    cases = load_cases(chapter)
    if not cases:
        print("没有可用的实务真题案例。")
        return
    case = cases[0]
    plan = is_plan(case)
    save_session(
        {
            "stem": case.get("stem") or "",
            "explain": case.get("explain") or "",
            "chapter": case.get("chapter") or chapter,
            "plan": plan,
            "layers": PLAN if plan else ANALYSIS,
            "key": key,
            "graded": False,
        }
    )
    show()


def cmd_grade(hit: str) -> None:
    session = load_session()
    if not session:
        print("没有进行中的案例写作。")
        return
    # 命中层由教练看完用户答案后传入，不要求用户自己对答案。
    layers = session["layers"]
    hits = [part.strip() for part in hit.split(",") if part.strip() in layers]
    points = 5 * len(hits)
    score = round(100 * points / 20)
    missed = [part for part in layers if part not in hits]
    print(f"命中 {'、'.join(hits) or '无'}。缺少 {'、'.join(missed) or '无'}。")
    print(f"案例得分 {points}/20。")
    if session.get("key"):
        quiz.save_chapter_score(session["key"], score, 1 if score >= 60 else 0, 1)
    print("参考答案")
    print(session.get("explain") or "这道题没有解析。")
    session["graded"] = True
    save_session(session)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--chapter", default="")
    start.add_argument("--key", default="")
    grade = sub.add_parser("grade")
    grade.add_argument("--hit", default="")
    args = parser.parse_args()
    if args.cmd == "start":
        cmd_start(args.chapter, args.key)
    else:
        cmd_grade(args.hit)


if __name__ == "__main__":
    main()
