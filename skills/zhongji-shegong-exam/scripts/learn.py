# -*- coding: utf-8 -*-
"""按章学习：知识点、口诀、易混点、速记要点，最后用章节测验评分。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import quiz
import suji

SKILL = Path(__file__).resolve().parent.parent
LEARN = SKILL / "runtime" / "learn.json"
ORDER = ["综合能力", "实务", "法规与政策"]
CHAPTER_ORDER = [
    "社会工作服务的内涵",
    "基本原则",
    "政治理论",
    "价值观与道德规范",
    "人类行为",
    "专业理论",
    "个案社会工作服务方法",
    "小组社会工作服务方法",
    "社区社会工作服务方法",
    "社会工作服务的管理",
    "社会工作服务督导",
    "志愿服务",
    "社会工作服务研究",
    "通用过程",
    "人民信访",
    "基层治理",
    "新就业群体",
    "社会救助",
    "司法社会工作",
    "退役军人",
    "学校",
    "医务",
    "企业",
    "防灾减灾",
    "儿童",
    "青少年",
    "老年",
    "妇女",
    "残疾人",
    "家庭",
    "方案设计与答题",
    "法规体系",
    "社会工作专业人员",
    "人民调解",
    "应急管理",
    "社区矫正禁毒治安",
    "慈善与社会组织",
    "劳动就业",
    "社会保险",
    "婚姻家庭",
    "特定人群",
]
STEPS = ["知识点", "记忆口诀", "易混点解析", "速记要点", "章节测验"]


def steps_for(subject: str) -> list[str]:
    steps = ["知识点", "记忆口诀", "易混点解析", "速记要点"]
    if "法规" in subject:
        steps.append("数字填空")
    if "实务" in subject:
        steps.append("案例写作")
    else:
        steps.append("章节测验")
    return steps


def load_session() -> dict | None:
    if not LEARN.exists():
        return None
    return json.loads(LEARN.read_text(encoding="utf-8"))


def save_session(data: dict | None) -> None:
    if data is None:
        if LEARN.exists():
            LEARN.unlink()
        return
    LEARN.parent.mkdir(parents=True, exist_ok=True)
    LEARN.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cards_for(subject: str, chapter: str) -> tuple[str, str, list[dict]]:
    rows = suji.match_subject(suji.load(), subject)
    picked = [r for r in rows if chapter in r["chapter"]]
    if not picked:
        names = "、".join(suji.chapters(rows))
        raise SystemExit(f"没有找到「{chapter}」。可选章节：{names}")
    return picked[0]["subject"], picked[0]["chapter"], picked


def chapter_catalog() -> list[tuple[str, str]]:
    rows = suji.load()
    found = []
    for subject in ORDER:
        seen = []
        for row in rows:
            if row["subject"] != subject or row["chapter"] in seen or row["chapter"] == "其他":
                continue
            seen.append(row["chapter"])
            found.append((subject, row["chapter"]))
    rank = {name: i for i, name in enumerate(CHAPTER_ORDER)}
    found.sort(key=lambda item: (ORDER.index(item[0]), rank.get(item[1], 100)))
    return found


def learning_map() -> dict:
    prog = quiz.progress()
    return prog.get("learning") or {}


def band_of(score: int | None) -> str:
    if score is None:
        return ""
    if score >= 90:
        return "掌握"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "及格"
    return "需重修"


def suggest() -> tuple[str, str] | None:
    done = learning_map()
    for subject, chapter in chapter_catalog():
        row = done.get(f"{subject}|{chapter}") or {}
        if row.get("status") != "已学":
            return subject, chapter
    return None


def chapter_question_count(subject: str, chapter: str) -> int:
    from chapters import same_chapter

    count = 0
    with quiz.BANK.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("level") != "中级":
                continue
            if subject not in (row.get("subject") or ""):
                continue
            if same_chapter(chapter, row.get("chapter") or ""):
                count += 1
    return count


def cmd_today(start: bool) -> None:
    import review

    if not learning_map():
        print("中级社工考综合能力、实务、法规与政策。每科 60 分，连续两个考试年度内三科都过才发证。")
        print("先学综合能力，把助人方法学扎实；再学法规与政策，记条件和期限；实务放在后面，用案例把方法写出来。")
        print("每天只做下面这一件。")
        print()
    if load_session() or review.load_session():
        which = "学习" if load_session() else "复习"
        print(f"今天接着上次没做完的{which}。")
        if start:
            cmd_go()
        else:
            print("说「继续」就接着做。")
        return
    due = review.due_list()
    if due:
        item = due[0]
        print(f"今日任务：复习 {item['subject']} / {item['chapter']}")
        print(f"原因：{item['reason']}。先看易混点和口诀，再做错题和小测。")
        if start:
            review.cmd_start(argparse.Namespace(subject=item["subject"], chapter=item["chapter"], restart=True))
        return
    nxt = suggest()
    if not nxt:
        print("今日任务：学过的章节都已及格，今天没有到期复习。可以做一套模拟卷。")
        return
    subject, chapter = nxt
    count = chapter_question_count(subject, chapter)
    print(f"今日任务：学习 {subject} / {chapter}")
    if "实务" in subject:
        print("顺序是知识点、口诀、易混点、速记要点，最后写一道案例，由我打分。")
    elif "法规" in subject:
        print("顺序是知识点、口诀、易混点、速记要点，然后做数字填空，再做章节测验。")
    else:
        print("顺序是知识点、口诀、易混点、速记要点，最后 5 道本章的题。")
    if count < 5 and "实务" not in subject:
        print(f"这一章目前对上的题有 {count} 道，测验做完现有的即可。")
    if start:
        cmd_start(argparse.Namespace(subject=subject, chapter=chapter, restart=True))


def cmd_go() -> None:
    import review

    if load_session():
        print("继续本章学习。")
        session = load_session()
        step = session["step"]
        if step == "数字填空":
            import numbers

            numbers.show_current()
            return
        if step == "案例写作":
            import case_write

            case_write.show()
            return
        if step == "章节测验":
            print("这一章正在测验。")
            quiz.cmd_next()
            return
        steps = session.get("steps") or steps_for(session["subject"])
        print(render_step(step, session["cards"], session["subject"], session["chapter"], steps.index(step) + 1, len(steps)))
        print("\n讲完这一节后，说「继续」。")
        return
    if review.load_session():
        print("继续本章复习。")
        review.cmd_start(argparse.Namespace(subject="", chapter="", restart=False))
        return
    cmd_today(True)


def render_step(step: str, picked: list[dict], subject: str, chapter: str, index: int, total: int) -> str:
    head = f"【{subject} · {chapter}】{step}（{index}/{total}）"
    if step == "知识点":
        titles = [r["title"] for r in picked if r["kind"] in {"要点", "模板"}]
        lines = [head, "", "这一章先过知识点，先记住名目："]
        if not titles:
            lines.append("- 这一章没有单独知识点，直接进入下一节。")
        for i, title in enumerate(titles, 1):
            lines.append(f"{i}. {title}")
        return "\n".join(lines)
    if step == "记忆口诀":
        rows = [r for r in picked if r["kind"] == "口诀"]
        lines = [head, ""]
        if not rows:
            lines.append("这一章没有单独口诀。")
        for row in rows:
            lines.append(f"- {row['title']}：{row['body'].replace(chr(10), ' / ')}")
        return "\n".join(lines)
    if step == "易混点解析":
        rows = [r for r in picked if r["kind"] == "易混"]
        lines = [head, ""]
        if not rows:
            lines.append("这一章没有单列易混点。")
        for row in rows:
            lines.append(f"- {row['title']}")
            lines.append(f"  {row['body']}")
        return "\n".join(lines)
    if step == "速记要点":
        rows = [r for r in picked if r["kind"] == "要点"]
        lines = [head, ""]
        if not rows:
            lines.append("这一章没有速记要点。")
        for row in rows:
            brief = row["body"]
            if len(brief) > 180:
                brief = brief[:180] + "…"
            lines.append(f"- {row['title']}：{brief}")
        return "\n".join(lines)
    return head


def begin_quiz(subject: str, chapter: str) -> None:
    ns = argparse.Namespace(
        mode="learn",
        level="中级",
        subject=subject,
        chapter=chapter,
        kind="",
        year="",
        paper="",
        n=5,
        learn={"key": f"{subject}|{chapter}"},
    )
    quiz.cmd_start(ns)


def cmd_status() -> None:
    done = learning_map()
    catalog = chapter_catalog()
    finished = 0
    print("章节学习进度")
    current = None
    for subject, chapter in catalog:
        key = f"{subject}|{chapter}"
        row = done.get(key) or {}
        status = row.get("status") or "未学"
        if status == "已学":
            finished += 1
        score = row.get("score")
        score_text = f"{score}分 {row.get('band') or band_of(score)}" if score is not None else "未测验"
        print(f"- {subject} / {chapter}：{status}，{score_text}")
        if current is None and status != "已学":
            current = (subject, chapter)
    print(f"已学 {finished}/{len(catalog)} 章。60 分及格，75 分良好，90 分掌握。")
    if current:
        print(f"建议下一章：{current[0]} / {current[1]}")
    else:
        print("三科章节都已达到及格。可以按低分章节再学一遍。")


def cmd_start(args) -> None:
    active = load_session()
    if active and not args.restart:
        print(f"正在学 {active['subject']} / {active['chapter']}，当前是{active['step']}。说继续进入下一节。")
        steps = active.get("steps") or steps_for(active["subject"])
        print(render_step(active["step"], active["cards"], active["subject"], active["chapter"], steps.index(active["step"]) + 1, len(steps)))
        return
    if not args.subject or not args.chapter:
        nxt = suggest()
        if not nxt:
            print("章节都已学完。指定科目和章节可以重学。")
            return
        print(f"还没指定章节。建议从 {nxt[0]} / {nxt[1]} 开始。")
        return
    subject, chapter, picked = cards_for(args.subject, args.chapter)
    steps = steps_for(subject)
    session = {"subject": subject, "chapter": chapter, "step": steps[0], "steps": steps, "cards": picked}
    save_session(session)
    print(render_step(steps[0], picked, subject, chapter, 1, len(steps)))
    print("\n讲完这一节后，说「继续」进入下一节。")


def cmd_next() -> None:
    session = load_session()
    if not session:
        print("还没有进行中的章节。先指定科目和章节开始学习。")
        return
    if session["step"] == "章节测验":
        print("这一章正在测验。做完剩余题目后会自动记分。")
        quiz.cmd_next()
        return
    if session["step"] == "数字填空":
        import numbers

        if numbers.pending():
            print("数字填空还没做完。")
            numbers.show_current()
            return
    if session["step"] == "案例写作":
        import case_write

        if case_write.pending():
            print("还没收到你的案例答案。请写完发过来，我来打分。")
            return
        save_session(None)
        print("这一章的案例写作已经记分。")
        return
    steps = session.get("steps") or steps_for(session["subject"])
    idx = steps.index(session["step"]) + 1
    step = steps[idx]
    session["step"] = step
    save_session(session)
    if step == "数字填空":
        import numbers

        print(f"【{session['subject']} · {session['chapter']}】数字填空（{idx + 1}/{len(steps)}）")
        print("填这一章的数字和期限。答错会回到口诀。")
        numbers.cmd_start(session["chapter"], 3)
        return
    if step == "案例写作":
        import case_write

        print("请按题目四层写完发过来，我来打分。")
        case_write.cmd_start(session["chapter"], f"{session['subject']}|{session['chapter']}")
        return
    if step == "章节测验":
        print(f"【{session['subject']} · {session['chapter']}】章节测验（{idx + 1}/{len(steps)}）")
        print("下面按本章抽题，做完按得分记入本章成绩。")
        begin_quiz(session["subject"], session["chapter"])
        return
    print(render_step(step, session["cards"], session["subject"], session["chapter"], idx + 1, len(steps)))
    print("\n讲完这一节后，说「继续」进入下一节。")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("next")
    sub.add_parser("today")
    sub.add_parser("go")
    p = sub.add_parser("start")
    p.add_argument("--subject", default="")
    p.add_argument("--chapter", default="")
    p.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "next":
        cmd_next()
    elif args.cmd == "today":
        cmd_today(False)
    elif args.cmd == "go":
        cmd_go()
    else:
        cmd_start(args)


if __name__ == "__main__":
    main()
