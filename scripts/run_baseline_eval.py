# -*- coding: utf-8 -*-
"""构造评测（constructed evaluation）：在 statute-rag 真实语料上批量校验，产出错误引用率基线。

**本基线不含任何模型生成环节**：四组案例全部由确定性规则从真实条文构造，
测的是 guard 本身的检出率（fabricated / misquoted / uncited 三组）
与误报率（grounded 组）。每条案例的构造规则见 docs/baseline-report.md。

四组构造规则：
  grounded    引文 = 条文逐字片段，引用 = 该条文正确 Citation → 期望 0 命中（测 FP）
  fabricated  引用改为该法不存在的条号（9001 起编号，保证不在语料中）→ 测检出率
  misquoted   引文做系统性改写（数字替换 / 同义词替换 / 拼接两条不同条文），
              构造时验证改写结果确非原文子串（保证缺陷真实存在）→ 测检出率
  uncited     取真实条文中含断言词的句子作为无引用断言 → 测检出率

用法：
  py -3.13 scripts/run_baseline_eval.py --corpus <statute-rag>/data/corpus.jsonl --out <json>
  （语料不在本仓库，必须用 --corpus 指向 statute-rag 仓导出的 data/corpus.jsonl）
"""
import argparse
import io
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from legal_hallu_guard.guard import (
    CLAIM_PAT, _norm, build_index, check_answer,
)

DEFAULT_CORPUS = None  # 语料不在本仓库，必须显式传 --corpus
DEFAULT_SEED = 20260928

CN_DIGITS = "零一二三四五六七八九"


def cn_num(n):
    """1..9999 → 中文数字（与语料条号书写一致）。"""
    assert 1 <= n <= 9999
    parts = []
    if n >= 1000:
        parts.append(CN_DIGITS[n // 1000] + "千")
        n %= 1000
    if n >= 100:
        parts.append(CN_DIGITS[n // 100] + "百")
        n %= 100
    rest = n
    if rest > 0 and rest < 10 and parts and parts[-1].endswith("百"):
        parts.append("零")
    elif rest > 0 and rest < 100 and parts and not any(p.endswith("百") for p in parts):
        parts.append("零")
    if rest >= 10:
        t = rest // 10
        prefix = "" if (not parts and t == 1) else CN_DIGITS[t]
        parts.append(prefix + "十")
        rest %= 10
    if rest > 0:
        parts.append(CN_DIGITS[rest])
    return "".join(parts)


def load_corpus(path):
    corpus = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                corpus.append(json.loads(line))
    return corpus


def make_quote(text, max_len=80):
    """取条文开头的逐字片段（连续子串，词法上与 guard 的去空白比对一致）。"""
    t = text.strip()
    if len(t) <= max_len:
        return t
    q = t[:max_len]
    cut = q.rfind(u"。")
    if cut >= 20:
        q = q[:cut + 1]
    return q


# ---- misquoted 的三种系统性改写（按序尝试，直到改写结果确非原文子串）----

NUM_REMAP = {"一": "二", "二": "三", "三": "四", "四": "五", "五": "六",
             "六": "七", "七": "八", "八": "九", "九": "一",
             "0": "1", "1": "2", "2": "3", "3": "4", "4": "5",
             "5": "6", "6": "7", "7": "8", "8": "9", "9": "0"}

SYNONYM_PAIRS = [(u"应当", u"必须"), (u"不得", u"禁止"), (u"可以", u"能够"),
                 (u"有权", u"有权利"), (u"视为", u"看作"), (u"无效", u"不生效力")]


def rewrite_numeral(quote, article_norm):
    for i, ch in enumerate(quote):
        if ch in NUM_REMAP:
            cand = quote[:i] + NUM_REMAP[ch] + quote[i + 1:]
            if _norm(cand) not in article_norm:
                return cand, u"数字替换"
    return None, None


def rewrite_synonym(quote, article_norm):
    for old, new in SYNONYM_PAIRS:
        start = 0
        while True:
            i = quote.find(old, start)
            if i < 0:
                break
            cand = quote[:i] + new + quote[i + len(old):]
            if _norm(cand) not in article_norm:
                return cand, u"同义词替换"
            start = i + 1
    return None, None


def rewrite_stitch(quote, article_norm, partner_text):
    """拼接：前半句取自本文条文片段，后半句取自同法另一条文的片段。"""
    p = partner_text.strip()
    if len(p) < 20:
        return None, None
    half = max(1, len(quote) // 2)
    cand = quote[:half] + p[len(p) // 2:len(p) // 2 + len(quote) - half]
    if _norm(cand) not in article_norm:
        return cand, u"拼接两条条文"
    return None, None


# ---- 四组构造器：只按内容规则构造，不按 guard 结果筛选（grounded 组尤其不能筛，
#      否则会把真误报藏起来；misquoted 组的子串验证是构造正控样本的必要条件）----

def build_grounded(articles, index, rng, n):
    pool = [a for a in articles if len(a["text"].strip()) >= 20]
    picked = rng.sample(sorted(pool, key=lambda x: (x["law"], x["num"], x["id"])), n)
    cases = []
    for a in picked:
        quote = make_quote(a["text"])
        answer = u"根据【%s %s｜%s】，该条文对相关情形作出了明确规定。" % (a["law"], a["num"], quote)
        cases.append({"group": "grounded", "law": a["law"], "num": a["num"],
                      "answer": answer, "expected_rules": set()})
    return cases


def build_fabricated(articles, index, rng, n):
    pool = [a for a in articles if len(a["text"].strip()) >= 20]
    picked = rng.sample(sorted(pool, key=lambda x: (x["law"], x["num"], x["id"])), n)
    cases = []
    for i, a in enumerate(picked):
        fake_num = u"第%s条" % cn_num(9001 + i)
        assert (a["law"], fake_num) not in index, fake_num
        quote = make_quote(a["text"])
        answer = u"根据【%s %s｜%s】的规定，该条文对相应行为设定了明确要求。" % (a["law"], fake_num, quote)
        cases.append({"group": "fabricated", "law": a["law"], "num": fake_num,
                      "answer": answer, "expected_rules": {"FABRICATED_CITATION"}})
    return cases


def build_misquoted(articles, index, rng, n):
    by_law = {}
    for a in articles:
        if len(a["text"].strip()) >= 60:
            by_law.setdefault(a["law"], []).append(a)
    for law in by_law:
        by_law[law].sort(key=lambda x: (x["num"], x["id"]))
    pool = sorted([a for lst in by_law.values() for a in lst],
                  key=lambda x: (x["law"], x["num"], x["id"]))
    picked = rng.sample(pool, n)
    cases = []
    skipped = 0
    for a in picked:
        quote = make_quote(a["text"], max_len=60)
        article_norm = _norm(a["text"])
        siblings = [s for s in by_law[a["law"]] if s["id"] != a["id"]]
        partner = siblings[0]["text"] if siblings else None
        bad_quote, strategy = rewrite_numeral(quote, article_norm)
        if bad_quote is None:
            bad_quote, strategy = rewrite_synonym(quote, article_norm)
        if bad_quote is None and partner:
            bad_quote, strategy = rewrite_stitch(quote, article_norm, partner)
        if bad_quote is None:
            skipped += 1
            continue
        answer = u"依据【%s %s｜%s】，相关规则可参照适用。" % (a["law"], a["num"], bad_quote)
        cases.append({"group": "misquoted", "law": a["law"], "num": a["num"],
                      "answer": answer, "expected_rules": {"MISQUOTED_TEXT"},
                      "strategy": strategy})
    return cases, skipped


def build_uncited(articles, index, rng, n):
    pool = []
    for a in articles:
        for sent in a["text"].strip().split(u"。"):
            sent = sent.strip()
            if len(sent) >= 10 and CLAIM_PAT.search(sent):
                pool.append((a, sent))
                break
    pool.sort(key=lambda x: (x[0]["law"], x[0]["num"], x[0]["id"]))
    picked = rng.sample(pool, n)
    cases = []
    for a, sent in picked:
        answer = u"法律意见：" + sent + u"。"
        cases.append({"group": "uncited", "law": a["law"], "num": a["num"],
                      "answer": answer, "expected_rules": {"UNCITED_CLAIM"}})
    return cases


def evaluate(cases, index):
    """跑 guard 并按组汇总：n / 触发数 / 检出率 / 预期规则命中 / 按规则计数 / 异常明细。"""
    groups = {}
    for c in cases:
        findings = check_answer(c["answer"], index)
        g = groups.setdefault(c["group"], {
            "n": 0, "flagged": 0, "expected_rule_hits": 0,
            "by_rule": {}, "unexpected": [],
        })
        g["n"] += 1
        rule_ids = {f["rule_id"] for f in findings}
        if findings:
            g["flagged"] += 1
        if rule_ids & c["expected_rules"]:
            g["expected_rule_hits"] += 1
        for f in findings:
            g["by_rule"][f["rule_id"]] = g["by_rule"].get(f["rule_id"], 0) + 1
        unexpected = rule_ids - c["expected_rules"]
        if unexpected:
            g["unexpected"].append({
                "law": c["law"], "num": c["num"],
                "unexpected_rules": sorted(unexpected),
                "messages": [f["message"] for f in findings
                             if f["rule_id"] in unexpected],
            })
    return groups


def finalize(groups):
    out = {}
    for name, g in groups.items():
        g = dict(g)
        if name == "grounded":
            g["fp_rate"] = g["flagged"] / float(g["n"]) if g["n"] else 0.0
        else:
            g["detection_rate"] = (g["expected_rule_hits"] / float(g["n"])
                                   if g["n"] else 0.0)
        out[name] = g
    return out


def main():
    parser = argparse.ArgumentParser(description=u"legal-hallu-guard 构造评测基线（无模型）")
    parser.add_argument("--corpus", default=DEFAULT_CORPUS,
                        help=u"statute-rag 语料 JSONL 路径（只读，不复制进本仓库）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=u"固定随机种子")
    parser.add_argument("--grounded", type=int, default=250)
    parser.add_argument("--fabricated", type=int, default=120)
    parser.add_argument("--misquoted", type=int, default=120)
    parser.add_argument("--uncited", type=int, default=60)
    parser.add_argument("--out", help=u"汇总 JSON 输出路径（缺省只打印）")
    args = parser.parse_args()

    if not args.corpus:
        print(u"[!] 未指定语料：本仓库不含语料文件，请用 --corpus 指向 statute-rag 仓的 data/corpus.jsonl，见 README。")
        raise SystemExit(2)

    corpus = load_corpus(args.corpus)
    index = build_index(corpus)
    laws = {x["law"] for x in corpus}
    rng = random.Random(args.seed)
    articles = list(corpus)

    cases = []
    cases += build_grounded(articles, index, rng, args.grounded)
    cases += build_fabricated(articles, index, rng, args.fabricated)
    misquoted_cases, skipped = build_misquoted(articles, index, rng, args.misquoted)
    cases += misquoted_cases
    cases += build_uncited(articles, index, rng, args.uncited)

    groups = finalize(evaluate(cases, index))

    print("")
    print(u"构造评测基线（无模型，语料 %d 条 / %d 部法律，seed=%d）" % (
        len(corpus), len(laws), args.seed))
    print(u"=" * 72)
    print(u"%-12s %6s %10s %10s %14s" % (
        u"组别", u"n", u"触发数", u"比率", u"预期规则命中"))
    print(u"-" * 72)
    for name in ("grounded", "fabricated", "misquoted", "uncited"):
        g = groups[name]
        if name == "grounded":
            rate = u"FP %.1f%%" % (g["fp_rate"] * 100)
            hits = u"-"
        else:
            rate = u"%.1f%%" % (g["detection_rate"] * 100)
            hits = u"%d/%d" % (g["expected_rule_hits"], g["n"])
        print(u"%-12s %6d %10d %10s %14s" % (name, g["n"], g["flagged"], rate, hits))
    print(u"-" * 72)
    total_flagged = sum(g["flagged"] for g in groups.values())
    total_n = sum(g["n"] for g in groups.values())
    print(u"整体：构造答案 %d 条，触发 %d 条，构造语料错误引用率 %.1f%%（按设计存在缺陷的组占主导）" % (
        total_n, total_flagged, total_flagged / float(total_n) * 100))
    if skipped:
        print(u"misquoted 组跳过 %d 条（三种改写策略均无法破坏子串性质，未纳入统计）" % skipped)
    for name, g in groups.items():
        if g["unexpected"]:
            print(u"[!] %s 组出现预期外规则 %d 条，需逐条分析（见 --out JSON）" % (
                name, len(g["unexpected"])))

    if args.out:
        payload = {
            "meta": {
                "kind": "constructed evaluation (no model generation)",
                "corpus_path": args.corpus,
                "corpus_articles": len(corpus),
                "corpus_laws": len(laws),
                "seed": args.seed,
                "misquoted_skipped": skipped,
                "sizes": {k: groups[k]["n"] for k in ("grounded", "fabricated",
                                                      "misquoted", "uncited")},
            },
            "groups": groups,
        }
        with io.open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(u"汇总 JSON 已写入 %s" % args.out)


if __name__ == "__main__":
    main()
