# -*- coding: utf-8 -*-
"""法律答案引用护栏：三类确定性校验，抓「看起来很专业但引用是假的」的答案。

校验对象是**带引用标记的答案**（引用格式：`【法名 第X条】`，可内嵌引文
`【法名 第X条｜引文…】`），与 statute-rag 的 Citation 结构对齐。

三类校验（各自可开关）：
1. cited_exists   引用存在性：被引的（法名, 条号）必须出现在语料索引中
2. quote_fidelity 引文保真：引用块内的引文必须是所引条文的连续子串（去空白）
3. claim_coverage 断言覆盖：含法律断言词的句子必须落在某个引用块内
   （「应当/不得/有权/构成/无效…」是法律答案的命门，无引用支撑即报）

输出：findings 列表（rule_id / severity / position / message）+
错误引用率（有缺陷的答案数 / 答案总数，或按缺陷数计）。
"""
import re

# 引用块：【法名 第X条】 或 【法名 第X条｜引文】
CITE_RE = re.compile(r"【([^｜】\n]+?)\s*(第[一二三四五六七八九十百千零\d]+条)\s*(?:｜([^】\n]*))?】")
# 法律断言词（v0.1 词表，可按领域扩展）
CLAIM_PAT = re.compile(r"应当|不得|有权|构成|无效|视为|负责|承担")
SENTENCE_SPLIT_RE = re.compile(r"[。！？\n]")

RULE_CITED_EXISTS = "FABRICATED_CITATION"
RULE_QUOTE = "MISQUOTED_TEXT"
RULE_CLAIM = "UNCITED_CLAIM"


def _norm(s):
    return "".join((s or "").split())


def build_index(corpus):
    """{(法名, 条号): 条文文本} —— corpus 为 statute-rag importer.load_corpus 的产物，
    或任何含 law/num/text 字段的 dict 列表。"""
    return {(x["law"], x["num"]): x["text"] for x in corpus}


def check_answer(answer, index, check_exists=True, check_quote=True, check_claim=True):
    """对单个答案跑护栏，返回 findings 列表。

    每条 finding：{rule_id, severity, position, message}
    severity：引用类造假 P0、引文失真 P0、断言无引用 P1。
    """
    findings = []
    cites = list(CITE_RE.finditer(answer))
    cite_spans = [(m.start(), m.end()) for m in cites]

    for m in cites:
        law, num, quote = m.group(1).strip(), m.group(2), (m.group(3) or "").strip()
        key = (law, num)
        if check_exists and key not in index:
            findings.append({
                "rule_id": RULE_CITED_EXISTS, "severity": "P0",
                "position": m.start(),
                "message": u"引用了语料中不存在的条文：%s%s" % (law, num),
            })
            continue
        if check_quote and quote and key in index:
            article = _norm(index[key])
            if _norm(quote) not in article:
                findings.append({
                    "rule_id": RULE_QUOTE, "severity": "P0",
                    "position": m.start(),
                    "message": u"引文在 %s%s 原文中不存在（拼接或改写）" % (law, num),
                })

    if check_claim:
        pos = 0
        for sent in SENTENCE_SPLIT_RE.split(answer):
            start = pos
            pos += len(sent) + 1
            sent = sent.strip()
            if not sent or not CLAIM_PAT.search(sent):
                continue
            end = start + len(sent) - 1
            # 句子与任一引用块有重叠即视为有引用支撑
            # （引用本身造假由 FABRICATED_CITATION / MISQUOTED_TEXT 负责，不重复扣）
            covered = any(not (ce < start or cs > end) for cs, ce in cite_spans)
            if not covered:
                findings.append({
                    "rule_id": RULE_CLAIM, "severity": "P1",
                    "position": start,
                    "message": u"含法律断言但无引用支撑：「%s…」" % sent[:20],
                })
    return findings


def check_answers(answers, index, **kwargs):
    """批量检查。返回 [{answer_id, findings, pass}]。"""
    results = []
    for i, answer in enumerate(answers):
        findings = check_answer(answer, index, **kwargs)
        results.append({
            "answer_id": i + 1,
            "findings": findings,
            "pass": not findings,
        })
    return results


def defect_rate(results):
    """有缺陷答案占比（按答案数计的「错误引用率」）。"""
    if not results:
        return {"defect_rate": 0.0, "defective": 0, "total": 0, "by_rule": {}}
    by_rule = {}
    defective = 0
    for r in results:
        if not r["pass"]:
            defective += 1
        for f in r["findings"]:
            by_rule[f["rule_id"]] = by_rule.get(f["rule_id"], 0) + 1
    return {
        "defect_rate": defective / float(len(results)),
        "defective": defective,
        "total": len(results),
        "by_rule": by_rule,
    }
