# -*- coding: utf-8 -*-
"""复习已学章节：易混点和口诀、错题，再用小测更新分数。"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import learn
import quiz

SKILL = Path(__file__).resolve().parent.parent
REVIEW = SKILL / "runtime" / "review.json"
STEPS = ["回顾", "错题", "复习测验"]
INTERVAL = {"需重修": 0, "及格": 2, "良好": 5, "掌握": 10}


def load_session() -> dict | None:
    if not REVIEW.exists():
        return None
    return json.loads(REVIEW.read_text(encoding="utf-8"))


def save_session(data: dict | None) -> None:
    if data is None:
        if REVIEW.exists():
            REVIEW.unlink()
        return
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def open_wrongs(subject: str, chapter: str) -> list[dict]:
    return [
        item
        for item in quiz.wrongs().values()
        if item.get("status") != "已攻克"
        and subject in (item.get("subject") or "")
        and chapter in (item.get("chapter") or "")
    ]


def due_list() -> list[dict]:
    today = date.today()
    rows = []
    learned = learn.learning_map()
    for subject, chapter in learn.chapter_catalog():
        key = f"{subject}|{chapter}"
        row = learned.get(key) or {}
        if row.get("score") is None and row.get("status") not in {"已学", "需重修"}:
            continue
        anchor = row.get("last_review") or row.get("date")
        if not anchor:
            continue
        band = row.get("band") or learn.band_of(row.get("score"))
        gap = 0 if row.get("status") == "需重修" else INTERVAL.get(band, 2)
        due_on = date.fromisoformat(anchor) + timedelta(days=gap)
        wrongs = open_wrongs(subject, chapter)
        overdue = (today - due_on).days
        if overdue < 0 and not wrongs:
            continue
        rows.append(
            {
                "subject": subject,
                "chapter": chapter,
                "key": key,
                "band": band,
                "score": row.get("score"),
                "status": row.get("status") or "已学",
                "overdue": overdue,
                "wrongs": len(wrongs),
                "reason": "有未攻克错题" if overdue < 0 else ("需重修" if gap == 0 else f"到期 {overdue} 天"),
            }
        )
    rows.sort(key=lambda item: (item["status"] != "需重修", -item["wrongs"], -item["overdue"]))
    return rows


def render_recall(subject: str, chapter: str, cards: list[dict]) -> str:
    mix = [r for r in cards if r["kind"] == "易混"]
    kou = [r for r in cards if r["kind"] == "口诀"]
    lines = [f"【{subject} · {chapter}】复习回顾（1/3）", "", "先看易混点，再背口诀。"]
    lines.append("")
    lines.append("易混点解析")
    if mix:
        for row in mix:
            lines.append(f"- {row['title']}")
            lines.append(f"  {row['body']}")
    else:
        lines.append("- 这一章没有单列易混点。")
    lines.append("")
    lines.append("记忆口诀")
    if kou:
        for row in kou:
            lines.append(f"- {row['title']}：{row['body'].replace(chr(10), ' / ')}")
    else:
        lines.append("- 这一章没有单独口诀。")
    return "\n".join(lines)


def quiz_pending() -> dict | None:
    if not quiz.SESSION.exists():
        return None
    session = json.loads(quiz.SESSION.read_text(encoding="utf-8"))
    if session.get("cursor", 0) < len(session.get("items") or []):
        return session
    return None


def begin_quiz(mode: str, subject: str, chapter: str, n: int) -> None:
    ns = argparse.Namespace(
        mode=mode,
        level="中级",
        subject=subject,
        chapter=chapter,
        kind="",
        year="",
        paper="",
        n=n,
        learn={"key": f"{subject}|{chapter}"},
    )
    quiz.cmd_start(ns)


def cmd_status() -> None:
    due = due_list()
    learned = [k for k, v in learn.learning_map().items() if v.get("score") is not None or v.get("status") in {"已学", "需重修"}]
    print(f"已学 {len(learned)} 章。复习间隔：需重修当天，及格 2 天，良好 5 天，掌握 10 天。")
    if not learned:
        print("还没有学过的章节。先用学习功能学完一章，再来复习。")
        return
    if not due:
        print("今天没有到期章节。")
        return
    print("今天该复习：")
    for item in due:
        score = f"{item['score']}分" if item["score"] is not None else "未测验"
        wrong = f"，错题 {item['wrongs']}" if item["wrongs"] else ""
        print(f"- {item['subject']} / {item['chapter']}：{score} {item['band']}，{item['reason']}{wrong}")


def cmd_start(args) -> None:
    active = load_session()
    if active and not args.restart:
        print(f"正在复习 {active['subject']} / {active['chapter']}，当前是{active['step']}。说继续进入下一步。")
        if active["step"] == "回顾":
            print(render_recall(active["subject"], active["chapter"], active["cards"]))
        return
    if args.subject and args.chapter:
        subject, chapter, cards = learn.cards_for(args.subject, args.chapter)
        row = learn.learning_map().get(f"{subject}|{chapter}") or {}
        if row.get("score") is None and row.get("status") not in {"已学", "需重修"}:
            print(f"{subject} / {chapter} 还没学过。先学完再复习。")
            return
    else:
        due = due_list()
        if not due:
            cmd_status()
            return
        subject, chapter = due[0]["subject"], due[0]["chapter"]
        _, _, cards = learn.cards_for(subject, chapter)
    session = {"subject": subject, "chapter": chapter, "step": "回顾", "cards": cards}
    save_session(session)
    print(render_recall(subject, chapter, cards))
    print("\n看完后说「继续」，先做错题，再做复习测验。")


def cmd_next() -> None:
    session = load_session()
    if not session:
        print("还没有进行中的复习。先看今天到期的章节。")
        cmd_status()
        return
    pending = quiz_pending()
    if pending and session["step"] in {"错题", "复习测验"}:
        print("还有题没做完。")
        quiz.cmd_next()
        return
    subject, chapter = session["subject"], session["chapter"]
    if session["step"] == "回顾":
        wrongs = open_wrongs(subject, chapter)
        if not wrongs:
            session["step"] = "复习测验"
            save_session(session)
            print(f"【{subject} · {chapter}】没有未攻克错题，进入复习测验（3/3）。")
            begin_quiz("review", subject, chapter, 5)
            return
        session["step"] = "错题"
        save_session(session)
        print(f"【{subject} · {chapter}】错题重练（2/3），共 {len(wrongs)} 题。")
        begin_quiz("wrong", subject, chapter, min(5, len(wrongs)))
        return
    if session["step"] == "错题":
        session["step"] = "复习测验"
        save_session(session)
        print(f"【{subject} · {chapter}】复习测验（3/3）。做完会更新本章分数和下次复习时间。")
        begin_quiz("review", subject, chapter, 5)
        return
    save_session(None)
    print(f"{subject} / {chapter} 的复习已经记分。可以再看今天还有没有到期章节。")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("next")
    p = sub.add_parser("start")
    p.add_argument("--subject", default="")
    p.add_argument("--chapter", default="")
    p.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "next":
        cmd_next()
    else:
        cmd_start(args)


if __name__ == "__main__":
    main()
