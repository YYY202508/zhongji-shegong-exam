# -*- coding: utf-8 -*-
"""把口诀、考前三页纸、答题模板整理成按章节调用的速记卡片。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

SKILL = Path(__file__).resolve().parent.parent
# 技能不再携带 PDF，重建卡片时读资料盘上的原件。
MATERIALS = Path(r"D:\工作\社工证资料") / "中级"
OUT = SKILL / "suji" / "cards.jsonl"

DROP = (
    "咨询热线",
    "微信扫码",
    "免费约",
    "免费领取",
    "免费订阅",
    "环球网校",
    "环球青藤",
    "扫码关注",
    "移动课堂",
    "侵权必究",
    "学员专用",
    "请勿外泄",
    "400-678-3456",
    "第1 页",
    "第2 页",
    "第3 页",
)


def page_lines(path: Path) -> list[str]:
    doc = pymupdf.open(path)
    lines = []
    for page in doc:
        for raw in page.get_text().splitlines():
            s = raw.strip()
            if not s or any(w in s for w in DROP):
                continue
            if re.fullmatch(r"第\s*\d+\s*页共\s*\d+\s*页", s):
                continue
            lines.append(s)
    doc.close()
    return lines


def chapter_of(title: str, body: str) -> tuple[str, str]:
    rules = [
        ("法规与政策", "法规体系", ["法规的种类"]),
        ("法规与政策", "人民信访", ["信访的形式", "信访工作法规"]),
        ("法规与政策", "基层治理", ["基层治理遵循", "居民委员会", "村民委员会", "乡镇（街道）", "乡镇(街道)"]),
        ("法规与政策", "志愿服务", ["志愿者的权利", "志愿服务的特征", "志愿者权利"]),
        ("法规与政策", "社会工作专业人员", ["继续教育"]),
        ("法规与政策", "人民调解", ["人民调解", "当事人在人民调解"]),
        ("法规与政策", "社会救助", ["最低生活保障", "特困", "共同生活的家庭", "无劳动能力", "供养内容", "终止救助", "受灾人员", "临时救助", "医疗救助", "教育救助", "住房救助", "就业救助"]),
        ("法规与政策", "应急管理", ["突发事件分级", "应急管理体制"]),
        ("法规与政策", "社区矫正禁毒治安", ["社区矫正适用", "强制隔离戒毒", "治安管理处罚", "担保人"]),
        ("法规与政策", "退役军人", ["军士和义务兵", "退役军人", "优抚", "褒扬"]),
        ("法规与政策", "慈善与社会组织", ["慈善组织", "慈善募捐", "基金会"]),
        ("法规与政策", "劳动就业", ["劳动合同", "劳动争议", "集体协商", "劳动权益"]),
        ("法规与政策", "社会保险", ["养老保险", "医疗保险", "工伤", "失业保险"]),
        ("法规与政策", "婚姻家庭", ["收养人", "遗嘱", "夫妻间", "婚姻的成立"]),
        ("法规与政策", "特定人群", ["特定人群"]),
        ("实务", "方案设计与答题", ["答题模板", "方案设计题", "万能"]),
        ("实务", "人民信访", ["人民信访"]),
        ("实务", "基层治理", ["基层治理和基层政权", "基层治理社会工作", "村（居）民", "资源的链接", "网络分析", "自助小组", "培育志愿者", "协同共治"]),
        ("实务", "新就业群体", ["新就业", "职业发展与保障"]),
        ("实务", "社会救助", ["社会救助社会工作", "精准识别救助"]),
        ("实务", "司法社会工作", ["司法社会工作", "禁毒社会工作"]),
        ("实务", "退役军人", ["光荣院", "军休", "英烈", "退役军人事务社会工作"]),
        ("实务", "学校", ["学校社会工作"]),
        ("实务", "医务", ["医务社会工作"]),
        ("实务", "企业", ["企业社会工作"]),
        ("实务", "防灾减灾", ["防灾", "韧性社区"]),
        ("实务", "儿童", ["儿童社会工作"]),
        ("实务", "青少年", ["青少年社会工作"]),
        ("实务", "老年", ["老年社会工作", "老年人"]),
        ("实务", "妇女", ["妇女社会工作"]),
        ("实务", "残疾人", ["残疾人社会工作"]),
        ("实务", "家庭", ["家庭社会工作", "与家庭建立关系"]),
        ("实务", "通用过程", ["接案", "预估", "人在情境", "全人视角", "能力视角", "结案"]),
        ("综合能力", "政治理论", ["政治理论", "二十大", "十个明确", "社会主义核心价值观", "中央社会工作", "党领思想"]),
        ("综合能力", "价值观与道德规范", ["价值观", "道德规范", "文化基础"]),
        ("综合能力", "人类行为", ["社会环境的构成", "人类行为"]),
        ("综合能力", "个案社会工作服务方法", ["心理社会", "认知行为", "理性情绪", "任务中心", "危机介入", "人本", "家庭治疗", "萨提亚", "结构式", "个案", "会谈"]),
        ("综合能力", "小组社会工作服务方法", ["社会目标", "治疗模式", "互动模式", "发展模式", "小组"]),
        ("综合能力", "社区社会工作服务方法", ["邻里互助", "组织动员", "关爱照顾", "教育培训", "社区社会工作"]),
        ("综合能力", "专业理论", ["协同治理", "服务联动", "社会关系视角", "系统视角", "优势视角", "增能", "社会发展", "建构", "叙事", "焦点解决", "心理取向", "四个基本系统", "改变媒介"]),
        ("综合能力", "社会工作服务的管理", ["项目的", "机构的", "战略规划"]),
        ("综合能力", "社会工作服务督导", ["督导"]),
        ("综合能力", "志愿服务", ["志愿服务和社会工作"]),
        ("综合能力", "社会工作服务研究", ["定量研究", "定性研究", "行动研究", "干预研究"]),
        ("综合能力", "社会工作服务的内涵", ["社会工作服务的目标", "社会工作服务的功能"]),
        ("综合能力", "基本原则", ["基本原则"]),
    ]

    def hit(text: str) -> tuple[str, str] | None:
        for subject, chapter, words in rules:
            if any(w in text for w in words):
                return subject, chapter
        return None

    return hit(title) or hit(title + body) or ("综合能力", "其他")


def parse_kaodian(lines: list[str]) -> list[dict]:
    text = "\n".join(lines)
    parts = re.split(r"(?=【考点\d+】)", text)
    cards = []
    for part in parts:
        m = re.match(r"【考点\d+】\s*(.+)", part)
        if not m:
            continue
        first, _, rest = part.partition("\n")
        title = re.sub(r"^【考点\d+】\s*", "", first).strip()
        body = re.sub(r"\s+", " ", rest).strip()
        if len(title) < 2:
            continue
        subject, chapter = chapter_of(title, body)
        cards.append(
            {
                "subject": subject,
                "chapter": chapter,
                "kind": "要点",
                "title": title,
                "body": body,
            }
        )
    return cards


def still_koujue(line: str, prev: str | None) -> bool:
    if prev is None:
        return True
    if prev.endswith(("，", "、", "；", ",", "（", "级")):
        return True
    if line.endswith("）") and len(line) <= 8:
        return True
    if line.startswith(("三件大事", "六个坚持", "五大特色", "领域")):
        return True
    if line.endswith("。") and len(line) > 24:
        return True
    if ("“" in line or '"' in line) and ("：" in line or ":" in line):
        return True
    return False


def parse_koujue(lines: list[str]) -> list[dict]:
    lines = [
        ln
        for ln in lines
        if "十页纸" not in ln
        and "好词好句" not in ln
        and "备考" not in ln
        and not re.match(r"^[一二三四五六七八九十]+、", ln)
    ]
    cards = []
    title = None
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("【") and "总口诀" in line:
            title = "七大模式总口诀" if "七大" in line else "四大模式总口诀"
            body = []
            kou = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith("【"):
                    break
                if len(nxt) < 22 and "，" not in nxt and "。" not in nxt:
                    break
                kou.append(nxt)
                i += 1
            subject, chapter = chapter_of(title, "")
            if "七大" in title:
                subject, chapter = "综合能力", "个案社会工作服务方法"
            else:
                subject, chapter = "综合能力", "小组社会工作服务方法"
            cards.append(
                {
                    "subject": subject,
                    "chapter": chapter,
                    "kind": "口诀",
                    "title": title,
                    "body": "\n".join(kou).strip(),
                    "detail": "",
                }
            )
            title, body = None, []
            continue
        if line.startswith("【记忆口诀】"):
            kou: list[str] = []
            extra = line.replace("【记忆口诀】", "").strip()
            if extra:
                kou.append(extra)
            i += 1
            prev = kou[-1] if kou else None
            while i < len(lines) and still_koujue(lines[i], prev):
                kou.append(lines[i])
                prev = lines[i]
                i += 1
            if title and "囊括" not in title and "直击" not in title and len(title) <= 40:
                blob = "\n".join(body)
                subject, chapter = chapter_of(title, blob)
                cards.append(
                    {
                        "subject": subject,
                        "chapter": chapter,
                        "kind": "口诀",
                        "title": title,
                        "body": "\n".join(kou).strip(),
                        "detail": re.sub(r"\s+", " ", blob).strip(),
                    }
                )
            title, body = None, []
            continue
        if title is None:
            title = line
        else:
            body.append(line)
        i += 1
    return cards


def parse_template(lines: list[str]) -> list[dict]:
    body = "\n".join(lines[1:])
    return [
        {
            "subject": "实务",
            "chapter": "方案设计与答题",
            "kind": "模板",
            "title": "案例分析与方案设计答题模板",
            "body": body.strip(),
        }
    ]


def main() -> None:
    cards: list[dict] = []
    cards.extend(parse_kaodian(page_lines(MATERIALS / "综合能力/考点笔记/2026中级社工-综合能力-考前三页纸.pdf")))
    cards.extend(parse_kaodian(page_lines(MATERIALS / "实务/考点笔记/2026中级社工-实务-考前三页纸.pdf")))
    cards.extend(parse_kaodian(page_lines(MATERIALS / "法规与政策/考点笔记/2026中级社工-法规与政策-考前三页纸.pdf")))
    cards.extend(parse_koujue(page_lines(MATERIALS / "法规与政策/考点笔记/2026中级-社会工作法规与政策-记忆口诀十页纸.pdf")))
    cards.extend(parse_koujue(page_lines(MATERIALS / "实务/考点笔记/2026中级-社会工作实务-记忆口诀十页纸.pdf")))
    cards.extend(parse_template(page_lines(MATERIALS / "实务/考点笔记/2026年社工中级实务通用答题模板.pdf")))
    mixups = json.loads((SKILL / "suji" / "mixups.json").read_text(encoding="utf-8"))
    for item in mixups:
        cards.append(
            {
                "subject": item["subject"],
                "chapter": item["chapter"],
                "kind": "易混",
                "title": item["title"],
                "body": item["body"],
            }
        )
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    from collections import Counter

    c = Counter((x["subject"], x["chapter"], x["kind"]) for x in cards)
    print("cards", len(cards))
    for k, n in sorted(c.items()):
        print(f"{n:3d} {k}")


if __name__ == "__main__":
    main()
