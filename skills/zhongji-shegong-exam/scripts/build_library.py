# -*- coding: utf-8 -*-
"""整理社工证资料，并把真题、模拟题 PDF 正文抽成题库。

页眉水印整行丢弃；答案行里的水印字样只剥离、不丢答案。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

import pymupdf

try:
    pymupdf.TOOLS.mupdf_display_errors(False)
except Exception:
    pass

SKILL = Path(__file__).resolve().parent.parent
ROOT = Path(r"D:\工作\社工证资料")
BACKUP = ROOT / "备份与重复" / "原始文件"

DROP_PHRASES = (
    "侵权必究",
    "咨询热线",
    "微信扫码",
    "免费约直播",
    "免费领取备考",
    "免费订阅",
    "移动课堂",
    "学员专用",
    "请勿外泄",
    "扫码关注",
    "扫码添加",
    "刷题好帮手",
    "学习少点难事",
    "备考干货",
    "更多备考资源",
    "官方平台",
    "hqwx.com",
    "考试小秘书",
    "环球网校",
    "环球青藤",
    "400-678-3456",
)

QNUM_RE = re.compile(r"^(\d{1,3})\s*[.、．]\s*(.*)$")
OPT_RE = re.compile(r"^([A-E])\s*[.、．、]\s*(.*)$")
KEY_LINE_RE = re.compile(
    r"^(\d{1,3})\s*[.、．]\s*([A-E](?:\s*[、,，和]\s*[A-E])*)\s*$"
)
ANS_INLINE_RE = re.compile(r"^(\d{1,3})\s*[.、．]\s*【答案】\s*(.*)$")
HASH_RE = re.compile(r"_[0-9a-fA-F]{32,64}(?=\.pdf$)", re.I)


def clean_line(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    s = re.sub(r"^【真题\s*(\d{1,3})\s*[.、．]\s*】", r"\1.", s)
    if "答案" in s or "解析" in s:
        for ph in DROP_PHRASES:
            s = s.replace(ph, "")
        s = re.sub(r"\s+", " ", s).strip()
        return s
    if any(ph in s for ph in DROP_PHRASES):
        return ""
    if re.fullmatch(r"第?\s*\d+\s*页(?:共\s*\d+\s*页)?", s):
        return ""
    if re.fullmatch(r"\d{1,3}", s):
        return ""
    return s


def extract_pairs(path: Path) -> list[tuple[int, str]]:
    doc = pymupdf.open(path)
    pairs: list[tuple[int, str]] = []
    for i, page in enumerate(doc, 1):
        for raw in page.get_text().splitlines():
            s = clean_line(raw)
            if s:
                pairs.append((i, s))
    doc.close()
    return pairs


def norm_answer(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if "正确" in s or s in {"对", "√", "是"}:
        return "正确"
    if "错误" in s or s in {"错", "×", "否"}:
        return "错误"
    letters: list[str] = []
    for ch in re.findall(r"[A-E]", s.upper()):
        if ch not in letters:
            letters.append(ch)
    return "".join(letters)


def split_embedded_answer(text: str) -> tuple[str, str]:
    m = re.search(r"(?:【答案】|【参考答案】|答案[:：])\s*([A-E][A-E、，,和\s]*)\s*$", text)
    if not m:
        return text, ""
    return text[: m.start()].strip(), norm_answer(m.group(1))


def show_answer(ans: str) -> str:
    if ans in {"", "正确", "错误", "见解析"}:
        return ans or "见解析"
    return "、".join(ans)


def question_start_info(line: str):
    m = QNUM_RE.match(line)
    if not m:
        return None
    rest = m.group(2).strip()
    if rest.startswith("【答案】") or rest.startswith("答案"):
        return None
    if re.fullmatch(r"[A-E](?:\s*[、,，和]\s*[A-E])*", rest):
        return None
    hint = ""
    hm = re.match(r"^【(多选|单选|判断)】\s*", rest)
    if hm:
        hint = {"多选": "multi", "单选": "single", "判断": "judge"}[hm.group(1)]
        rest = rest[hm.end():]
    return m.group(1), rest, hint


def is_key_header(line: str) -> bool:
    m = re.match(r"^【参考答案】\s*(.*)$", line)
    if not m:
        return False
    rest = m.group(1).strip()
    if not rest:
        return True
    return bool(re.match(r"^\d", rest))


def is_new_paper(line: str) -> bool:
    if re.search(r"练习题\s*[（(][一二三四五六七八九十0-9]+[）)]", line):
        return True
    if re.search(r"模拟(?:试题|试卷)?\s*[（(][一二三四五六七八九十0-9]+[）)]", line):
        return True
    if re.search(r"第\s*[0-9一二三四五六七八九十]+\s*套", line):
        return True
    return False


def is_key_line(line: str) -> bool:
    return KEY_LINE_RE.match(line) is not None


def find_question_indices(lines: list[str]) -> list[int]:
    idxs = []
    for i, line in enumerate(lines):
        if not question_start_info(line):
            continue
        for j in range(i + 1, min(i + 40, len(lines))):
            nxt = lines[j]
            if re.match(r"^[A-E]\s*[.、．、]", nxt):
                idxs.append(i)
                break
            if nxt.startswith("【参考答案】") or ANS_INLINE_RE.match(nxt):
                idxs.append(i)
                break
            if question_start_info(nxt) and j > i + 1:
                break
    return idxs


def parse_block(block: list[str], page: int) -> dict | None:
    info = question_start_info(block[0])
    if not info:
        return None
    qnum, stem, hint = info
    options: list[str] = []
    answer = ""
    explain: list[str] = []
    mode = "stem"
    for line in block[1:]:
        inline = ANS_INLINE_RE.match(line)
        if inline:
            answer = norm_answer(inline.group(2)) or answer
            mode = "explain"
            continue
        bare = re.match(r"^(?:【参考答案】|【答案】|参考答案[:：]|答案[:：])\s*(.*)$", line)
        if bare:
            rest = bare.group(1).strip()
            if rest and not re.match(r"^\d", rest):
                answer = norm_answer(rest) or answer
            mode = "after_ans"
            continue
        if line.startswith("【解析】") or "参考解析" in line[:8] or line.startswith("【参考解析】"):
            mode = "explain"
            rest = re.sub(r"^【[^】]*解析】", "", line).strip()
            if rest:
                explain.append(rest)
            continue
        if mode == "explain":
            if is_key_line(line) or is_new_paper(line):
                continue
            explain.append(line)
            continue
        if mode == "after_ans":
            if not answer and re.fullmatch(r"[A-E](?:\s*[、,，和]\s*[A-E])*", line):
                answer = norm_answer(line)
                continue
            if is_key_line(line) or is_new_paper(line):
                continue
            explain.append(line)
            continue
        om = OPT_RE.match(line)
        if om and mode in {"stem", "options"}:
            mode = "options"
            options.append(om.group(2).strip())
            continue
        if mode == "options" and options:
            options[-1] = (options[-1] + line).strip()
        else:
            stem += line
    if not answer:
        joined = "".join(explain)
        m = re.search(r"正确答案是\s*([A-E、，,和\s]+)", joined)
        if m:
            answer = norm_answer(m.group(1))
    stem = re.sub(r"\s+", " ", stem).strip()
    options = [re.sub(r"\s+", " ", x).strip() for x in options]
    # 有的 PDF 把「【答案】C」粘在最后一个选项同一行
    stem, embedded = split_embedded_answer(stem)
    if embedded and not answer:
        answer = embedded
    fixed_opts = []
    for opt in options:
        opt, embedded = split_embedded_answer(opt)
        if embedded and not answer:
            answer = embedded
        fixed_opts.append(opt)
    options = fixed_opts
    explain_text = clean_explain(explain)
    if len(stem) < 8:
        return None
    if len(options) < 2 and not answer:
        return None
    # 解析里的列举被误当成下一题时，通常没有题干空括号，也没有答案
    if not answer and not re.search(r"[（(]\s*[）)]|[？?]|下列|哪一|哪些|正确", stem):
        return None
    qtype = hint or ("judge" if answer in {"正确", "错误"} else "multi" if len(answer) > 1 else "single")
    if hint == "multi":
        qtype = "multi"
    if len(options) >= 5 and len(answer) > 1:
        qtype = "multi"
    return {
        "qnum": qnum,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explain": explain_text,
        "type": qtype,
        "page": page,
    }


def clean_explain(lines: list[str]) -> str:
    kept = []
    for ln in lines:
        if "http" in ln or "资料列表" in ln or "汇总页面" in ln:
            continue
        if is_key_line(ln) or is_new_paper(ln):
            continue
        kept.append(ln)
    text = re.sub(r"\s+", " ", "".join(kept)).strip()
    return text[:4000]


def assign_answer(questions: list[dict], qnum: str, ans: str) -> None:
    if not ans:
        return
    for q in questions:
        if q["qnum"] == qnum and not q["answer"]:
            q["answer"] = ans
            if q["type"] == "single" and len(ans) > 1:
                q["type"] = "multi"
            return


def parse_segment(lines: list[str], pages: list[int]) -> list[dict]:
    header_idxs = [i for i, ln in enumerate(lines) if is_key_header(ln)]
    q_idxs = find_question_indices(lines)
    cuts = sorted(set(q_idxs + header_idxs + [len(lines)]))
    questions = []
    for qi in q_idxs:
        end = next(c for c in cuts if c > qi)
        block = lines[qi:end]
        parsed = parse_block(block, pages[qi])
        if parsed:
            questions.append(parsed)
    for hi in header_idxs:
        m = re.match(r"^【参考答案】\s*(.*)$", lines[hi])
        blob = m.group(1) if m else ""
        j = hi + 1
        while j < len(lines) and (is_key_line(lines[j]) or re.fullmatch(r"[A-E](?:\s*[、,，和]\s*[A-E])*", lines[j])):
            blob += "\n" + lines[j]
            j += 1
            if j < len(lines) and is_new_paper(lines[j]):
                break
        for km in re.finditer(r"(\d{1,3})\s*[.、．]\s*([A-E](?:\s*[、,，和]\s*[A-E])*)", blob):
            assign_answer(questions, km.group(1), norm_answer(km.group(2)))
    return questions


def split_segments(pairs: list[tuple[int, str]]) -> list[tuple[list[str], list[int]]]:
    parts: list[tuple[list[str], list[int]]] = []
    cur_l: list[str] = []
    cur_p: list[int] = []
    for i, (page, text) in enumerate(pairs):
        if i > 0 and is_new_paper(text) and cur_l:
            parts.append((cur_l, cur_p))
            cur_l, cur_p = [], []
        cur_l.append(text)
        cur_p.append(page)
    if cur_l:
        parts.append((cur_l, cur_p))
    return parts


def parse_objective(pairs: list[tuple[int, str]]) -> list[dict]:
    out = []
    for lines, pages in split_segments(pairs):
        out.extend(parse_segment(lines, pages))
    return out


def parse_cases(pairs: list[tuple[int, str]]) -> list[dict]:
    lines = [t for _, t in pairs]
    pages = [p for p, _ in pairs]
    idxs = [
        i
        for i, ln in enumerate(lines)
        if re.match(r"^（[一二三四五六七八九十]+）", ln) or ("方案设计" in ln and len(ln) <= 40)
    ]
    if not idxs:
        return []
    bounds = idxs + [len(lines)]
    items = []
    for n, (a, b) in enumerate(zip(bounds, bounds[1:]), 1):
        chunk = lines[a:b]
        exp_at = None
        for i, ln in enumerate(chunk):
            if "参考解析" in ln or ln.startswith("【解析】") or ln.startswith("【参考答案】"):
                exp_at = i
                break
        if exp_at is None:
            stem = "\n".join(chunk)
            explain = ""
        else:
            stem = "\n".join(chunk[:exp_at])
            explain = clean_explain(chunk[exp_at:])
        stem = stem.strip()
        if len(stem) < 20:
            continue
        label = re.match(r"^（([一二三四五六七八九十]+)）", lines[a])
        qnum = label.group(1) if label else str(n)
        items.append(
            {
                "qnum": qnum,
                "stem": stem,
                "options": [],
                "answer": "见解析",
                "explain": explain,
                "type": "case",
                "page": pages[a],
            }
        )
    return items


def is_case_title(ln: str) -> bool:
    if re.match(r"^案例分析\s*\d+", ln):
        return True
    if re.match(r"^第[一二三四五六七八九十]+题", ln):
        return True
    if re.match(r"^方案设计题", ln) or re.match(r"^[一二三四五六七八九十]+、方案设计", ln):
        return True
    return False


def is_explain_start(ln: str) -> bool:
    if re.match(r"^【(参考答案|参考解析|答案解析|解析)", ln):
        return True
    if ln.startswith("第一问"):
        return True
    return False


def split_unmarked_case(chunk: list[str]) -> tuple[str, str]:
    """没有「参考答案」标题时，小题编号回退到 1 的位置就是解析。"""
    pidx = next((i for i, ln in enumerate(chunk) if ln.startswith("问题") or ln.startswith("【问题】")), None)
    if pidx is None:
        return "\n".join(chunk).strip(), ""
    last = 0
    cut = len(chunk)
    for i in range(pidx + 1, len(chunk)):
        m = re.match(r"^(\d+)[.、．]", chunk[i])
        if not m:
            if last:
                cut = i
                break
            continue
        num = int(m.group(1))
        if last and num <= last:
            cut = i
            break
        last = num
    return "\n".join(chunk[:cut]).strip(), clean_explain(chunk[cut:])


def parse_numbered_cases(pairs: list[tuple[int, str]]) -> list[dict]:
    """实务卷常见两种切法：第N题/案例分析N，或「1.长叙述」后接「问题：」。"""
    lines = [t for _, t in pairs]
    pages = [p for p, _ in pairs]
    titles = [i for i, ln in enumerate(lines) if is_case_title(ln)]
    numbered: list[int] = []
    for i, ln in enumerate(lines):
        if any(lines[j].startswith("问题") or lines[j].startswith("【问题】") for j in range(max(0, i - 2), i)):
            continue
        if not re.match(r"^\d+[.、．].{18,}", ln):
            continue
        if ln.endswith((":", "：", "?", "？")):
            continue
        for j in range(i + 1, min(i + 28, len(lines))):
            if lines[j].startswith("问题") or lines[j].startswith("【问题】"):
                numbered.append(i)
                break
            if is_case_title(lines[j]) or is_explain_start(lines[j]):
                break
    opens = titles if len(titles) >= 2 else sorted(set(titles + numbered))
    opens = sorted(set(opens))
    if len(opens) < 2:
        return []
    bounds = opens + [len(lines)]
    items = []
    for n, (a, b) in enumerate(zip(opens, bounds[1:]), 1):
        chunk = lines[a:b]
        exp_at = None
        for i, ln in enumerate(chunk):
            if is_explain_start(ln):
                exp_at = i
                break
        if exp_at is None:
            stem, explain = split_unmarked_case(chunk)
        else:
            stem = "\n".join(chunk[:exp_at]).strip()
            explain = clean_explain(chunk[exp_at:])
        if len(stem) < 30:
            continue
        title_no = re.search(r"第([一二三四五六七八九十]+)题", lines[a])
        m = re.match(r"^(\d+)", lines[a])
        qnum = title_no.group(1) if title_no else (m.group(1) if m else str(n))
        items.append(
            {
                "qnum": qnum,
                "stem": stem,
                "options": [],
                "answer": "见解析",
                "explain": explain,
                "type": "case",
                "page": pages[a],
            }
        )
    return items


def parse_pairs(pairs: list[tuple[int, str]]) -> list[dict]:
    lines = [t for _, t in pairs]
    opt_n = sum(1 for ln in lines if OPT_RE.match(ln))
    case_n = sum(1 for ln in lines if re.match(r"^（[一二三四五六七八九十]+）", ln))
    objective = parse_objective(pairs)
    good_obj = [q for q in objective if len(q["options"]) >= 2 and q.get("answer")]
    # 选择题够多时不要被案例切分抢走，例如 120 题专练、高频 20 题
    if len(good_obj) >= 15:
        return good_obj
    numbered = parse_numbered_cases(pairs)
    cases = parse_cases(pairs) if case_n >= 3 else []
    # 切出十几道以上的“案例”一般是把选择题误切开了
    if len(numbered) > 8:
        numbered = [q for q in numbered if len(q.get("explain") or "") > 30]
        if len(numbered) > 8:
            numbered = []
    if len(cases) > 8:
        cases = []
    numbered_solid = [q for q in numbered if len(q.get("explain") or "") > 30]
    if 4 <= len(cases) <= 6:
        return cases
    if 3 <= len(numbered_solid) <= 6:
        return numbered_solid
    if 2 <= len(numbered) <= 6:
        return numbered
    if 3 <= len(cases) <= 8:
        return cases
    if len(good_obj) >= 3 and opt_n >= max(case_n, 1) * 3 and len(good_obj) >= len(numbered):
        return good_obj
    if len(good_obj) >= 3:
        return good_obj
    return numbered or cases or good_obj


def guess_chapter(subject: str, stem: str) -> str:
    from chapters import classify

    return classify(subject, stem)


def year_of(name: str) -> int | None:
    m = re.search(r"(20\d{2})", name)
    if m:
        return int(m.group(1))
    if "25年" in name[:8]:
        return 2025
    return None


def level_of(name: str) -> str:
    if "初中级" in name:
        return "未分类"
    if "初级" in name or "助理" in name:
        return "初级"
    if "高级" in name and "中级" not in name:
        return "高级"
    if "中级" in name:
        return "中级"
    if "社会工作师" in name:
        return "中级"
    if "法规" in name:
        return "中级"
    if any(k in name for k in ("报名", "准考证", "成绩查询", "物品清单", "考前提醒", "照片上传", "账号注册", "个人信息")):
        return "事务"
    return "未分类"


def subject_of(name: str) -> str:
    if "综合" in name:
        return "综合能力"
    if "实务" in name:
        return "实务"
    if "法规" in name or "政策" in name:
        return "法规与政策"
    return ""


def kind_of(name: str) -> str:
    if "真题" in name:
        return "真题"
    if "大纲" in name or "对照表" in name:
        return "大纲"
    if "教材变动" in name or "教材解读" in name:
        return "教材变动"
    if "学习指南" in name or "学习计划" in name:
        return "学习指南"
    if "考情" in name:
        return "考情"
    if any(k in name for k in ("模拟", "练习", "必刷", "易错", "冲刺", "精选", "单选", "高频", "专练")):
        return "模拟练习"
    if re.search(r"\d+\s*题", name):
        return "模拟练习"
    if any(k in name for k in ("三色", "思维导图", "考前三页", "口诀", "好词好句", "答题模板", "采分", "宝典", "考点")):
        return "考点笔记"
    if "应试技巧" in name:
        return "应试技巧"
    if any(k in name for k in ("报名", "准考证", "成绩", "物品", "考前提醒", "照片", "账号", "个人信息")):
        return "考试事务"
    return "其他"


def dest_rel(name: str) -> Path:
    lv, sub, kd = level_of(name), subject_of(name), kind_of(name)
    if lv == "事务" or kd == "考试事务":
        return Path("考试事务") / str(year_of(name) or "其他")
    if lv == "未分类":
        return Path("未分类")
    if kd == "应试技巧":
        return Path(lv) / "应试技巧"
    if kd == "大纲" and not sub:
        return Path(lv) / "大纲"
    if not sub:
        return Path(lv) / "其他"
    return Path(lv) / sub / kd


def clean_display_name(name: str) -> str:
    base = Path(str(name).replace("\\", "/")).name
    base = HASH_RE.sub("", base)
    base = re.sub(r"\(\d+\)(?=\.pdf$)", "", base)
    base = base.replace("&mdash", "").replace("&amp;", "")
    base = base.replace("・", "·")
    base = re.sub(r"^25年", "2025年", base)
    base = re.sub(r"\s+", "", base)
    if len(base) > 140:
        base = base[:130] + ".pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def name_score(name: str) -> int:
    # 压缩包里用错编码的文件名没有汉字，不能盖过带哈希后缀的正确中文名
    cjk = len(re.findall(r"[\u4e00-\u9fff]", name))
    score = cjk * 10
    if HASH_RE.search(name):
        score -= 20
    if "(1)" in name:
        score -= 15
    if "免费下载" in name:
        score -= 5
    score -= len(re.findall(r"[Ω⌡╔╚╫╢╠Γ┘┐┌]", name)) * 30
    return score


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_zip(data: bytes) -> zipfile.ZipFile:
    zf = zipfile.ZipFile(io.BytesIO(data))
    sample = [n for n in zf.namelist() if not n.endswith("/")][:6]
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for n in sample for ch in n)
    if sample and not has_cjk:
        zf.close()
        zf = zipfile.ZipFile(io.BytesIO(data), metadata_encoding="gbk")
    return zf


def iter_zip_pdfs(data: bytes, origin: str):
    try:
        zf = open_zip(data)
    except zipfile.BadZipFile:
        return
    for info in zf.infolist():
        if info.is_dir() or "__MACOSX" in info.filename:
            continue
        raw = zf.read(info)
        lower = info.filename.lower()
        if lower.endswith(".pdf"):
            yield Path(info.filename).name, raw, origin + "!" + info.filename
        elif lower.endswith(".zip"):
            yield from iter_zip_pdfs(raw, origin + "!" + info.filename)
    zf.close()


def unique_path(folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suf = candidate.stem, candidate.suffix
    n = 2
    while True:
        nxt = folder / f"{stem}（{n}）{suf}"
        if not nxt.exists():
            return nxt
        n += 1


def organize() -> list[dict]:
    sources = [p for p in ROOT.iterdir() if p.is_file() and p.suffix.lower() in {".pdf", ".zip"}]
    if not sources:
        manifest = ROOT / "索引" / "manifest.json"
        if manifest.exists():
            return json.loads(manifest.read_text(encoding="utf-8"))
        return []
    grouped: dict[str, dict] = {}
    for src in sources:
        blob = src.read_bytes()
        if src.suffix.lower() == ".pdf":
            digest = sha256(blob)
            slot = grouped.setdefault(digest, {"data": blob, "names": [], "origins": []})
            slot["names"].append(src.name)
            slot["origins"].append(str(src))
        else:
            for inner_name, raw, origin in iter_zip_pdfs(blob, src.name):
                digest = sha256(raw)
                slot = grouped.setdefault(digest, {"data": raw, "names": [], "origins": []})
                slot["names"].append(inner_name)
                slot["origins"].append(origin)
    records = []
    for digest, slot in grouped.items():
        best = max(slot["names"], key=name_score)
        display = clean_display_name(best)
        rel = dest_rel(display)
        target = unique_path(ROOT / rel, display)
        if not target.exists() or sha256(target.read_bytes()) != digest:
            target.write_bytes(slot["data"])
        records.append(
            {
                "sha256": digest,
                "name": target.name,
                "rel": target.relative_to(ROOT).as_posix(),
                "level": level_of(display),
                "subject": subject_of(display),
                "kind": kind_of(display),
                "year": year_of(display),
                "origins": slot["origins"],
            }
        )
    BACKUP.mkdir(parents=True, exist_ok=True)
    for src in sources:
        dest = BACKUP / src.name
        if dest.exists():
            dest = BACKUP / f"{src.stem}_重复{src.suffix}"
        shutil.move(str(src), str(dest))
    (ROOT / "索引").mkdir(exist_ok=True)
    (ROOT / "索引" / "manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records


def text_density(path: Path) -> tuple[int, int]:
    doc = pymupdf.open(path)
    chars = 0
    for page in doc:
        chars += len(page.get_text().strip())
    pages = doc.page_count
    doc.close()
    return pages, chars


def build_catalog(records: list[dict]) -> None:
    lines = [
        "# 社工证资料索引",
        "",
        "面向 2027 年中级社会工作师。2026 年及以前的真题当历年卷。初级、高级只归档，默认不进入中级练习。",
        "",
        f"共 {len(records)} 份去重后的 PDF。原始压缩包和重复件在 `备份与重复/原始文件`。",
        "",
    ]
    by_dir: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_dir[str(Path(rec["rel"]).parent).replace("\\", "/")].append(rec)
    for folder in sorted(by_dir):
        lines.append(f"## {folder}")
        lines.append("")
        for rec in sorted(by_dir[folder], key=lambda r: r["name"]):
            year = rec.get("year") or ""
            lines.append(f"- {rec['name']}（{rec['kind']} {year}）")
        lines.append("")
    text = "\n".join(lines)
    (ROOT / "索引").mkdir(exist_ok=True)
    (ROOT / "索引" / "资料索引.md").write_text(text, encoding="utf-8")
    # 资料索引只写在资料盘。技能里的 catalog.md 只说明原件位置，不要覆盖。


def index_questions(records: list[dict]) -> dict:
    items = []
    stats = []
    for rec in records:
        if rec["kind"] not in {"真题", "模拟练习"}:
            continue
        if rec["level"] not in {"中级", "初级"}:
            continue
        path = ROOT / rec["rel"]
        try:
            pairs = extract_pairs(path)
            parsed = parse_pairs(pairs)
        except Exception as exc:  # 单份坏档不影响整库
            stats.append({"rel": rec["rel"], "error": str(exc), "n": 0, "answered": 0})
            continue
        answered = 0
        for q in parsed:
            q["level"] = rec["level"]
            q["subject"] = rec["subject"]
            q["year"] = rec["year"]
            q["kind"] = rec["kind"]
            q["source"] = rec["rel"]
            q["chapter"] = guess_chapter(rec["subject"], q["stem"])
            digest = hashlib.sha1(re.sub(r"\s+", "", q["stem"]).encode("utf-8")).hexdigest()[:10]
            src_bit = hashlib.sha1(rec["rel"].encode("utf-8")).hexdigest()[:4]
            code = {"综合能力": "zh", "实务": "sw", "法规与政策": "fg"}.get(rec["subject"], "xx")
            lv = "zj" if rec["level"] == "中级" else "cj"
            q["stem_hash"] = digest
            q["id"] = f"{lv}-{code}-{rec['year'] or 'na'}-{digest}-{q['qnum']}-{src_bit}"
            if q["answer"]:
                answered += 1
            items.append(q)
        stats.append(
            {
                "rel": rec["rel"],
                "n": len(parsed),
                "answered": answered,
                "types": dict(defaultdict(int, {t: sum(1 for q in parsed if q["type"] == t) for t in {q["type"] for q in parsed}})),
            }
        )
    # 按卷要保留原题顺序，跨卷重复交给抽题脚本按 stem_hash 处理
    bank = items
    qdir = SKILL / "questions"
    qdir.mkdir(parents=True, exist_ok=True)
    bank_path = qdir / "bank.jsonl"
    with bank_path.open("w", encoding="utf-8") as f:
        for q in bank:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    stat_lines = ["# 题库抽取情况", "", f"入库 {len(bank)} 题，保留各份试卷原题，不跨卷删除。", ""]
    for st in sorted(stats, key=lambda s: s["rel"]):
        if st.get("error"):
            stat_lines.append(f"- {st['rel']}：抽取失败 {st['error']}")
        else:
            stat_lines.append(f"- {st['rel']}：{st['n']} 题，有答案 {st['answered']}，题型 {st['types']}")
    (SKILL / "references").mkdir(exist_ok=True)
    (SKILL / "references" / "bank-stats.md").write_text("\n".join(stat_lines) + "\n", encoding="utf-8")
    return {"items": len(bank), "files": len(stats), "stats": stats}


def rehome() -> list[dict]:
    named: dict[str, list[str]] = defaultdict(list)
    if BACKUP.exists():
        for src in BACKUP.iterdir():
            if src.suffix.lower() == ".pdf":
                named[sha256(src.read_bytes())].append(src.name)
            elif src.suffix.lower() == ".zip":
                for inner_name, raw, _origin in iter_zip_pdfs(src.read_bytes(), src.name):
                    named[sha256(raw)].append(inner_name)
    manifest_path = ROOT / "索引" / "manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    new_records = []
    for rec in records:
        path = ROOT / rec["rel"]
        if not path.exists():
            continue
        data = path.read_bytes()
        digest = sha256(data)
        best = max(named.get(digest) or [path.name], key=name_score)
        display = clean_display_name(best)
        folder = ROOT / dest_rel(display)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / display
        if target.exists() and target.resolve() != path.resolve():
            if sha256(target.read_bytes()) == digest:
                path.unlink()
            else:
                target = unique_path(folder, display)
                shutil.move(str(path), str(target))
        elif target.resolve() != path.resolve():
            shutil.move(str(path), str(target))
        new_records.append(
            {
                "sha256": digest,
                "name": target.name,
                "rel": target.relative_to(ROOT).as_posix(),
                "level": level_of(display),
                "subject": subject_of(display),
                "kind": kind_of(display),
                "year": year_of(display),
                "origins": rec.get("origins", []),
            }
        )
    for dirpath in sorted((p for p in ROOT.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if dirpath == ROOT or dirpath == BACKUP or BACKUP in dirpath.parents or dirpath.name in {"索引", "备份与重复"}:
            continue
        if not any(dirpath.iterdir()):
            dirpath.rmdir()
    manifest_path.write_text(json.dumps(new_records, ensure_ascii=False, indent=2), encoding="utf-8")
    return new_records


def probe() -> None:
    samples = [
        "【完整版】2026年中级社会工作者考试《社会工作综合能力（中级）》真题及答案(5月24日)_b541594024597ae4fd46424151eff7a7f0cf60a2.pdf",
        "【完整版】2026年中级社会工作者考试《社会工作法规与政策》真题及答案(5月23日)_28f07473d64b85d3e76fed43603111b5f4e698b2.pdf",
        "【完整版】2026年中级社会工作者考试《社会工作实务（中级）》真题及答案(5月24日)_d62b4df50a647d661015c3b15e50ab4e11b10b19.pdf",
        "2026年中级社会工作者《法规与政策》模拟试题(8套)_4de173e066aee9d8cd204651ac9d7fd25a5e3ff2.pdf",
        "2027年中级社会工作者《社会工作综合能力》模拟80题_a9a324d6c4b6dee45ec48a667347421b325f27db.pdf",
        "2026中级社工《综合能力》115题｜备考必刷题_ed005b3af115c0e8309e6cc262d4ae081a2d0a76.pdf",
    ]
    rows = []
    for name in samples:
        path = ROOT / name
        if not path.exists():
            # 归档后按文件名尾部找
            hits = list(ROOT.rglob(name[:18] + "*.pdf"))
            path = hits[0] if hits else None
        if path is None or not path.exists():
            rows.append(name + " MISSING")
            continue
        parsed = parse_pairs(extract_pairs(path))
        ans = sum(1 for q in parsed if q["answer"] and q["answer"] != "见解析")
        types = {}
        for q in parsed:
            types[q["type"]] = types.get(q["type"], 0) + 1
        rows.append(f"{path.name[:40]} n={len(parsed)} answered={ans} types={types}")
        if parsed:
            q0 = parsed[0]
            rows.append("  Q1 " + q0["type"] + " " + show_answer(q0["answer"]) + " opts=" + str(len(q0["options"])) + " stem=" + q0["stem"][:40])
            if len(parsed) > 2:
                qn = parsed[min(10, len(parsed) - 1)]
                rows.append("  Qn " + qn["qnum"] + " " + show_answer(qn["answer"]) + " " + qn["stem"][:30])
    out = Path(r"C:\Users\81450\AppData\Local\Temp\sw-samples\probe-result.txt")
    out.write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["probe", "all", "rehome"])
    args = parser.parse_args()
    if args.cmd == "probe":
        probe()
        return
    if args.cmd == "rehome":
        records = rehome()
        build_catalog(records)
        summary = index_questions(records)
        (ROOT / "索引" / "整理报告.md").write_text(
            f"# 整理报告\n\n去重后 PDF {len(records)} 份。题库 {summary['items']} 题，来自 {summary['files']} 个文件。\n",
            encoding="utf-8",
        )
        return
    records = organize()
    if not records and (ROOT / "索引" / "manifest.json").exists():
        records = json.loads((ROOT / "索引" / "manifest.json").read_text(encoding="utf-8"))
    build_catalog(records)
    summary = index_questions(records)
    report = ROOT / "索引" / "整理报告.md"
    report.write_text(
        f"# 整理报告\n\n去重后 PDF {len(records)} 份。题库 {summary['items']} 题，来自 {summary['files']} 个文件。\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
