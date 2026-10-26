# -*- coding: utf-8 -*-
"""从整理好的速记卡片里取某一章的口诀、易混点和要点。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CARDS = SKILL / "suji" / "cards.jsonl"


def load() -> list[dict]:
    if not CARDS.exists():
        raise SystemExit("速记卡片还没生成，先运行 scripts/build_suji.py")
    rows = []
    with CARDS.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def match_subject(rows: list[dict], subject: str) -> list[dict]:
    if not subject:
        return rows
    hit = [r for r in rows if subject in r["subject"]]
    return hit or rows


def chapters(rows: list[dict]) -> list[str]:
    seen = []
    for row in rows:
        if row["chapter"] not in seen:
            seen.append(row["chapter"])
    return seen


def render_chapter(rows: list[dict], subject: str, chapter: str) -> str:
    picked = [r for r in rows if chapter in r["chapter"]]
    if not picked:
        names = "、".join(chapters(rows))
        return f"没有找到「{chapter}」。这一科可以速记的章节：{names}"
    kou = [r for r in picked if r["kind"] == "口诀"]
    mix = [r for r in picked if r["kind"] == "易混"]
    points = [r for r in picked if r["kind"] == "要点"]
    template = [r for r in picked if r["kind"] == "模板"]
    real_subject = picked[0]["subject"]
    real_chapter = picked[0]["chapter"]
    lines = [f"【{real_subject} · {real_chapter}】速记", ""]
    lines.append("记忆口诀")
    if kou:
        for row in kou:
            lines.append(f"- {row['title']}：{row['body'].replace(chr(10), ' / ')}")
    else:
        lines.append("- 这一章没有单独口诀，先记下面的易混点。")
    lines.append("")
    lines.append("易混点解析")
    if mix:
        for row in mix:
            lines.append(f"- {row['title']}")
            lines.append(f"  {row['body']}")
    else:
        lines.append("- 这一章没有单列易混点。相邻概念看口诀里的对比。")
    if template:
        lines.append("")
        lines.append("答题模板")
        lines.append(template[0]["body"])
    if points:
        lines.append("")
        lines.append("速记要点")
        for row in points:
            brief = row["body"]
            if len(brief) > 180:
                brief = brief[:180] + "…"
            lines.append(f"- {row['title']}：{brief}")
    return "\n".join(lines)


def render_index(rows: list[dict], subject: str) -> str:
    lines = [f"【{subject or '全部'}】可速记章节", ""]
    for name in chapters(rows):
        kou = next((r for r in rows if r["chapter"] == name and r["kind"] == "口诀"), None)
        mix = sum(1 for r in rows if r["chapter"] == name and r["kind"] == "易混")
        tip = ""
        if kou:
            tip = kou["body"].split("\n")[0]
        lines.append(f"- {name}" + (f"：{tip}" if tip else "") + (f"（易混 {mix}）" if mix else ""))
    lines.append("")
    lines.append("指定章节后再展开口诀和易混点。")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="")
    parser.add_argument("--chapter", default="")
    parser.add_argument("--mix", action="store_true")
    args = parser.parse_args()
    rows = load()
    if not args.subject and not args.chapter:
        subjects = []
        for row in rows:
            if row["subject"] not in subjects:
                subjects.append(row["subject"])
        print("速记科目：" + "、".join(subjects))
        print("先选综合能力、实务或法规与政策。")
        return
    picked = match_subject(rows, args.subject)
    if args.mix and not args.chapter:
        lines = [f"【{args.subject}】易混点", ""]
        for row in picked:
            if row["kind"] != "易混":
                continue
            lines.append(f"- {row['chapter']} · {row['title']}")
            lines.append(f"  {row['body']}")
        print("\n".join(lines))
        return
    if not args.chapter:
        subject_name = picked[0]["subject"] if picked else args.subject
        print(render_index(picked, subject_name))
        return
    print(render_chapter(picked, args.subject, args.chapter))


if __name__ == "__main__":
    main()
