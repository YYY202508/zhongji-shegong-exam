# -*- coding: utf-8 -*-
"""中级社工题库抽题、判分、错题本。出题时不把答案打到 stdout。"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
BANK = SKILL / "questions" / "bank.jsonl"
SESSION = SKILL / "runtime" / "session.json"
PROGRESS = SKILL / "progress.json"
WRONG = SKILL / "wrongbook.json"


def show_answer(ans: str) -> str:
    if not ans or ans in {"正确", "错误", "见解析"}:
        return ans or "见解析"
    return "、".join(ans)


def norm_user(s: str) -> str:
    s = (s or "").strip().upper()
    if s in {"正确", "对", "√", "是"}:
        return "正确"
    if s in {"错误", "错", "×", "否"}:
        return "错误"
    letters = []
    for ch in s:
        if ch in "ABCDE" and ch not in letters:
            letters.append(ch)
    return "".join(letters)


def load_bank() -> list[dict]:
    if not BANK.exists():
        raise SystemExit("题库还没生成")
    rows = []
    with BANK.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def progress() -> dict:
    return load_json(
        PROGRESS,
        {"edition": "", "subjects": {}, "chapters": {}, "papers": [], "mocks": [], "learning": {}},
    )


def wrongs() -> dict:
    return load_json(WRONG, {})


def render_markdown() -> None:
    prog = progress()
    wb = wrongs()
    lines = ["# 学习进度", "", f"教材版本：{prog.get('edition') or '未记录'}", ""]
    lines.append("| 科目 | 作答 | 全对 | 正确率 |")
    lines.append("| --- | --- | --- | --- |")
    for name, row in sorted(prog.get("subjects", {}).items()):
        n, c = row.get("attempts", 0), row.get("correct", 0)
        rate = f"{(100 * c / n):.0f}%" if n else "-"
        lines.append(f"| {name} | {n} | {c} | {rate} |")
    lines += ["", "## 模考", ""]
    for m in prog.get("mocks", [])[-8:]:
        lines.append(
            f"- {m['date']} {m['subject']} {m['score']}/{m['full']} 分"
            if "score" in m
            else f"- {m['date']} {m['subject']} {m['correct']}/{m['n']}"
        )
    if not prog.get("mocks"):
        lines.append("- 还没有")
    lines += ["", "## 章节学习", ""]
    learning = prog.get("learning") or {}
    if not learning:
        lines.append("- 还没有")
    for key, row in learning.items():
        score = row.get("score")
        score_text = f"{score}分 {row.get('band') or ''}".strip() if score is not None else "未测验"
        lines.append(
            f"- {key}：{row.get('status') or '未学'}，{score_text}，上次复习 {row.get('last_review') or '无'}"
        )
    (SKILL / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    wlines = ["# 错题本", ""]
    open_items = [v for v in wb.values() if v.get("status") != "已攻克"]
    wlines.append(f"未攻克 {len(open_items)} 题。连对 2 次记为已攻克。")
    wlines.append("")
    for item in open_items[:80]:
        wlines.append(f"### {item['id']}")
        wlines.append(f"- {item.get('subject')} / {item.get('chapter')} / {item.get('stem_preview')}")
        wlines.append(f"- 我的答案：{item.get('user_answer')}｜正确答案：{item.get('correct')}")
        wlines.append(f"- 连对：{item.get('streak', 0)}｜状态：{item.get('status')}")
        wlines.append("")
    (SKILL / "wrongbook.md").write_text("\n".join(wlines), encoding="utf-8")


def bump(bucket: dict, key: str, ok: bool) -> None:
    row = bucket.setdefault(key, {"attempts": 0, "correct": 0})
    row["attempts"] += 1
    if ok:
        row["correct"] += 1


def record(q: dict, user: str, ok: bool, mode: str) -> None:
    prog = progress()
    bump(prog["subjects"], q.get("subject") or "未分科", ok)
    chapter = q.get("chapter") or "未分章"
    bump(prog["chapters"], f"{q.get('subject')}|{chapter}", ok)
    if mode == "mock" and q.get("_mock_tail"):
        prog["mocks"].append(
            {
                "date": date.today().isoformat(),
                "subject": q.get("subject"),
                "correct": q["_mock_correct"],
                "n": q["_mock_n"],
            }
        )
    save_json(PROGRESS, prog)
    wb = wrongs()
    item = wb.get(q["id"])
    if ok:
        if item and item.get("status") != "已攻克":
            item["streak"] = item.get("streak", 0) + 1
            item["last"] = date.today().isoformat()
            if item["streak"] >= 2:
                item["status"] = "已攻克"
            wb[q["id"]] = item
    else:
        preview = (q.get("stem") or "").replace("\n", " ")[:28]
        if not item:
            item = {
                "id": q["id"],
                "subject": q.get("subject"),
                "chapter": q.get("chapter"),
                "source": q.get("source"),
                "stem_preview": preview,
                "first_wrong": date.today().isoformat(),
                "streak": 0,
                "status": "未攻克",
            }
        item["user_answer"] = user
        item["correct"] = show_answer(q.get("answer") or "")
        item["streak"] = 0
        item["status"] = "未攻克"
        item["last"] = date.today().isoformat()
        wb[q["id"]] = item
    save_json(WRONG, wb)
    render_markdown()


def format_question(q: dict, index: int, total: int) -> str:
    kind = q.get("paper_part") or {"single": "单选", "multi": "多选", "judge": "判断", "case": "案例"}.get(q["type"], q["type"])
    points = q.get("paper_points")
    point_text = f"（{int(points)}分）" if points else ""
    head = f"【{q.get('level','')} {q.get('subject','')}·{q.get('kind','')}·{q.get('year') or ''}】{kind}{point_text} {index}/{total}  {q.get('chapter') or ''}"
    lines = [head, q.get("stem") or ""]
    for i, opt in enumerate(q.get("options") or []):
        lines.append(f"{chr(65+i)}. {opt}")
    if q["type"] == "multi":
        lines.append("（多选，满分 2 分。错选不得分，少选每个选项 0.5 分）")
    if q["type"] == "case":
        full = int(q.get("paper_points") or 1)
        lines.append(f"（本题 {full} 分。答完后按要点自评：full / half / wrong）")
    return "\n".join(lines)


def pick(args) -> list[dict]:
    rows = load_bank()
    level = args.level or "中级"
    rows = [q for q in rows if q.get("level") == level]
    if args.subject:
        rows = [q for q in rows if args.subject in (q.get("subject") or "")]
    if args.chapter:
        from chapters import same_chapter

        rows = [q for q in rows if same_chapter(args.chapter, q.get("chapter") or "")]
    if args.kind:
        rows = [q for q in rows if args.kind in (q.get("kind") or "")]
    if args.year:
        rows = [q for q in rows if str(q.get("year")) == str(args.year)]
    if args.paper:
        rows = [q for q in rows if args.paper in (q.get("source") or "")]
        rows.sort(key=lambda q: (q.get("source") or "", int(q["qnum"]) if str(q.get("qnum", "")).isdigit() else 0))
    elif args.mode == "wrong":
        wb = wrongs()
        ids = {k for k, v in wb.items() if v.get("status") != "已攻克"}
        rows = [q for q in rows if q["id"] in ids]
    else:
        # 章节和模考去掉重复题干，真题优先，解析更长的优先
        best = {}
        for q in rows:
            key = q.get("stem_hash") or q["id"]
            prev = best.get(key)
            rank = (q.get("kind") == "真题", len(q.get("explain") or ""))
            if prev is None or rank > prev[0]:
                best[key] = (rank, q)
        rows = [v[1] for v in best.values()]
        random.shuffle(rows)
    if args.mode == "mock" and not args.paper:
        rows = build_mock(rows, args.subject or "")
    elif not args.paper:
        rows = rows[: args.n or 10]
    elif args.n:
        rows = rows[: args.n]
    return rows


def is_plan(q: dict) -> bool:
    return "方案设计" in (q.get("stem") or "")


def build_mock(rows: list[dict], subject: str) -> list[dict]:
    """按真题结构组卷：客观题 60+20，实务 4 道案例加 1 道方案设计。"""
    if "实务" in subject:
        cases = [q for q in rows if q.get("type") == "case" and q.get("kind") == "真题"]
        plans = [q for q in cases if is_plan(q)]
        analyses = [q for q in cases if q not in plans]
        random.shuffle(analyses)
        random.shuffle(plans)
        chosen = analyses[:4] + plans[:1]
        for q in chosen:
            q["paper_points"] = 20
            q["paper_part"] = "方案设计" if is_plan(q) else "案例分析"
        return chosen
    singles = [q for q in rows if q.get("type") == "single"]
    multis = [q for q in rows if q.get("type") == "multi"]
    random.shuffle(singles)
    random.shuffle(multis)
    chosen = singles[:60] + multis[:20]
    for q in chosen:
        q["paper_points"] = 2 if q.get("type") == "multi" else 1
        q["paper_part"] = "多项选择题" if q.get("type") == "multi" else "单项选择题"
    return chosen


def mock_banner(rows: list[dict]) -> str:
    singles = sum(1 for q in rows if q.get("paper_part") == "单项选择题")
    multis = sum(1 for q in rows if q.get("paper_part") == "多项选择题")
    analyses = sum(1 for q in rows if q.get("paper_part") == "案例分析")
    plans = sum(1 for q in rows if q.get("paper_part") == "方案设计")
    if analyses or plans:
        return f"实务模拟卷：案例分析 {analyses} 题×20 分，方案设计 {plans} 题×20 分。满分 {analyses * 20 + plans * 20} 分，60 分及格。"
    return f"模拟卷：单项选择 {singles} 题×1 分，多项选择 {multis} 题×2 分。满分 {singles + multis * 2} 分，60 分及格。"


def cmd_start(args) -> None:
    if args.mode == "mock" and not args.paper and not args.subject:
        print("模拟考要指定科目：综合能力、法规与政策，或实务。")
        return
    rows = pick(args)
    if not rows:
        print("没有抽到题。放宽科目、章节或年份再试。")
        return
    session = {"cursor": 0, "mode": args.mode, "items": rows, "results": [], "learn": getattr(args, "learn", None)}
    save_json(SESSION, session)
    if args.mode == "mock":
        print(mock_banner(rows))
    print(format_question(rows[0], 1, len(rows)))
    print(f"\n本卷共 {len(rows)} 题。做一题判一题，全部做完给出卷面分。")


def current():
    if not SESSION.exists():
        raise SystemExit("没有进行中的练习")
    return load_json(SESSION, {})


def score_multi(correct: str, user: str) -> tuple[bool, float, str]:
    cset, uset = set(correct), set(user)
    if not uset:
        return False, 0, "未作答"
    if uset - cset:
        return False, 0, "错选，不得分"
    if uset == cset:
        return True, 2, "全对"
    return False, 0.5 * len(uset), f"少选，得 {0.5 * len(uset)} 分（满分 2 分）"


def cmd_grade(args) -> None:
    session = current()
    items = session["items"]
    cur = session["cursor"]
    if cur >= len(items):
        print("这一轮已经做完。")
        return
    q = items[cur]
    if q["type"] == "case":
        rating = (args.rating or "").lower()
        if rating not in {"full", "half", "wrong"}:
            print(q.get("explain") or "这题没有解析。")
            print("案例请按要点自评后重跑，并带上 --rating full|half|wrong")
            return
        ok = rating == "full"
        full = float(q.get("paper_points") or 1)
        points = {"full": full, "half": full / 2, "wrong": 0.0}[rating]
        note = {"full": f"得 {points:g} 分", "half": f"得 {points:g} 分", "wrong": "不得分"}[rating]
        record(q, rating, ok, session.get("mode") or "chapter")
        print(note)
        print(q.get("explain") or "")
    else:
        user = norm_user(args.answer or "")
        correct = q.get("answer") or ""
        if q["type"] == "multi":
            ok, points, note = score_multi(correct, user)
            full = 2.0
        else:
            ok = user == correct and bool(correct)
            full = float(q.get("paper_points") or 1)
            points = full if ok else 0.0
            note = f"得 {points:g} 分" if ok else "不得分"
        record(q, show_answer(user), ok, session.get("mode") or "chapter")
        mark = "对" if ok else "错"
        print(f"{mark}。正确答案 {show_answer(correct)}。你的答案 {show_answer(user) or '空'}。{note}")
        if q.get("explain"):
            print(q["explain"])
        else:
            print("这题原文没有解析。")
    session["results"].append({"id": q["id"], "ok": ok, "points": points, "full": full})
    session["cursor"] = cur + 1
    save_json(SESSION, session)
    left = len(items) - session["cursor"]
    print(f"\n还剩 {left} 题。")
    if left == 0 and session.get("mode") in {"learn", "review"}:
        finish_learn_quiz(session)
    elif left == 0 and session.get("mode") == "mock":
        finish_mock(session)


def save_chapter_score(key: str, score: int, correct: int, n: int, review: bool = False) -> None:
    if score >= 90:
        band = "掌握"
    elif score >= 75:
        band = "良好"
    elif score >= 60:
        band = "及格"
    else:
        band = "需重修"
    prog = progress()
    learning = prog.setdefault("learning", {})
    old = learning.get(key) or {}
    today = date.today().isoformat()
    learning[key] = {
        "status": "已学" if score >= 60 else "需重修",
        "score": score,
        "best": max(int(old.get("best") or 0), score),
        "band": band,
        "correct": correct,
        "n": n,
        "date": old.get("date") or today,
        "last_review": today,
        "times": int(old.get("times") or 0) + (0 if review else 1),
        "review_times": int(old.get("review_times") or 0) + (1 if review else 0),
    }
    save_json(PROGRESS, prog)
    render_markdown()
    print(f"{key} 得分 {score}（{band}）。已记入学习进度。")


def finish_learn_quiz(session: dict) -> None:
    results = session.get("results") or []
    got = sum(float(r.get("points") or 0) for r in results)
    full = sum(float(r.get("full") or 0) for r in results)
    score = round(100 * got / full) if full else 0
    key = (session.get("learn") or {}).get("key") or ""
    if not key:
        print(f"本章测验得分 {score}。")
        return
    save_chapter_score(key, score, sum(1 for r in results if r.get("ok")), len(results), review=session.get("mode") == "review")


def finish_mock(session: dict) -> None:
    results = session.get("results") or []
    got = sum(float(item.get("points") or 0) for item in results)
    full = sum(float(item.get("full") or 0) for item in results)
    subject = (session.get("items") or [{}])[0].get("subject") or ""
    prog = progress()
    prog.setdefault("mocks", []).append(
        {
            "date": date.today().isoformat(),
            "subject": subject,
            "score": got,
            "full": full,
            "correct": sum(1 for item in results if item.get("ok")),
            "n": len(results),
        }
    )
    save_json(PROGRESS, prog)
    render_markdown()
    verdict = "及格" if got >= 60 else "未及格"
    print(f"模拟考卷面 {got:g}/{full:g} 分，{verdict}。60 分及格。")


def cmd_next() -> None:
    session = current()
    cur = session["cursor"]
    items = session["items"]
    if cur >= len(items):
        print("这一轮已经做完。")
        return
    print(format_question(items[cur], cur + 1, len(items)))


def cmd_status() -> None:
    rows = load_bank() if BANK.exists() else []
    prog = progress()
    wb = wrongs()
    open_n = sum(1 for v in wb.values() if v.get("status") != "已攻克")
    print(f"教材版本：{prog.get('edition') or '未记录'}")
    print(f"题库 {len(rows)} 题。未攻克错题 {open_n}。")
    by = {}
    for q in rows:
        if q.get("level") != "中级":
            continue
        key = q.get("subject") or "?"
        by[key] = by.get(key, 0) + 1
    for k, n in sorted(by.items()):
        row = prog.get("subjects", {}).get(k, {})
        att, cor = row.get("attempts", 0), row.get("correct", 0)
        rate = f"{(100 * cor / att):.0f}%" if att else "还没练"
        print(f"- {k}：题库 {n}，已练 {att}，正确率 {rate}")
    chapters = prog.get("chapters", {})
    weak = []
    for key, row in chapters.items():
        if row.get("attempts", 0) < 3:
            continue
        rate = row["correct"] / row["attempts"]
        weak.append((rate, key, row))
    weak.sort()
    if weak:
        print("正确率偏低的章节：")
        for rate, key, row in weak[:3]:
            print(f"- {key} {row['correct']}/{row['attempts']}")


def cmd_report() -> None:
    render_markdown()
    cmd_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("report")
    sub.add_parser("next")
    p = sub.add_parser("start")
    p.add_argument("--mode", default="chapter", choices=["chapter", "mock", "wrong", "paper", "learn", "review"])
    p.add_argument("--level", default="中级")
    p.add_argument("--subject", default="")
    p.add_argument("--chapter", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--year", default="")
    p.add_argument("--paper", default="")
    p.add_argument("--n", type=int, default=10)
    g = sub.add_parser("grade")
    g.add_argument("--answer", default="")
    g.add_argument("--rating", default="")
    e = sub.add_parser("edition")
    e.add_argument("name")
    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "report":
        cmd_report()
    elif args.cmd == "next":
        cmd_next()
    elif args.cmd == "start":
        cmd_start(args)
    elif args.cmd == "grade":
        cmd_grade(args)
    elif args.cmd == "edition":
        prog = progress()
        prog["edition"] = args.name
        save_json(PROGRESS, prog)
        render_markdown()
        print(f"已记下教材版本：{args.name}")


if __name__ == "__main__":
    main()
