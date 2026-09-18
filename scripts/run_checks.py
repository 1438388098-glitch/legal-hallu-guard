# -*- coding: utf-8 -*-
"""护栏 CLI：对案例集（JSONL，字段 answer_id/answer）跑检查并输出错误引用率。

用法：
  python scripts/run_checks.py cases/selftest.jsonl
  python scripts/run_checks.py cases/selftest.jsonl --corpus data/corpus.jsonl
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from legal_hallu_guard.fixtures import CORPUS
from legal_hallu_guard.guard import build_index, check_answers, defect_rate

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="legal-hallu-guard 引用护栏")
    parser.add_argument("cases", help="案例 JSONL（answer_id / answer 字段）")
    parser.add_argument("--corpus", help="语料 JSONL（statute-rag 格式）；缺省用内置虚构语料")
    args = parser.parse_args()

    if args.corpus:
        corpus = []
        with io.open(args.corpus, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    corpus.append(json.loads(line))
    else:
        corpus = CORPUS

    answers = []
    with io.open(args.cases, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                answers.append(json.loads(line))

    index = build_index(corpus)
    results = check_answers([a["answer"] for a in answers], index)
    metrics = defect_rate(results)

    for a, r in zip(answers, results):
        status = "PASS" if r["pass"] else "FAIL"
        rules = "、".join(sorted({x["rule_id"] for x in r["findings"]})) or "-"
        print("[%s] %s  触发规则：%s" % (status, a.get("answer_id", a["answer"][:12]), rules))
    print("")
    print("错误引用率（有缺陷答案占比）：%.1f%%（%d/%d）" % (
        metrics["defect_rate"] * 100, metrics["defective"], metrics["total"]))
    print("按规则：", metrics["by_rule"] or "无")


if __name__ == "__main__":
    main()
