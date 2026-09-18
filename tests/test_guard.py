# -*- coding: utf-8 -*-
"""护栏单测：三类校验 + 案例期望触发 + 指标计算。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from legal_hallu_guard.fixtures import CASES, CORPUS
from legal_hallu_guard.guard import (
    RULE_CLAIM, RULE_CITED_EXISTS, RULE_QUOTE,
    build_index, check_answer, check_answers, defect_rate,
)


class GuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = build_index(CORPUS)

    def _rules(self, answer):
        return {f["rule_id"] for f in check_answer(answer, self.index)}

    def test_good_answer_passes(self):
        self.assertEqual(self._rules(CASES[0]["answer"]), set())

    def test_fabricated_citation_caught(self):
        rules = self._rules(CASES[1]["answer"])
        self.assertIn(RULE_CITED_EXISTS, rules)

    def test_misquote_caught(self):
        rules = self._rules(CASES[2]["answer"])
        self.assertIn(RULE_QUOTE, rules)

    def test_uncited_claim_caught(self):
        rules = self._rules(CASES[3]["answer"])
        self.assertIn(RULE_CLAIM, rules)

    def test_quote_inside_cite_block_not_flagged_as_claim(self):
        # 引文里的「应当/不得」不应被判为无引用断言
        self.assertNotIn(RULE_CLAIM, self._rules(CASES[0]["answer"]))

    def test_case_expectations_align(self):
        # 案例声明的期望触发规则 == 实际触发规则（护栏行为与案例文档一致）
        for case in CASES:
            got = self._rules(case["answer"])
            self.assertEqual(got, case["expect_rules"],
                             u"案例 %s 期望 %s 实际 %s" % (
                                 case["answer_id"], case["expect_rules"], got))

    def test_batch_and_defect_rate(self):
        results = check_answers([c["answer"] for c in CASES], self.index)
        self.assertEqual(len(results), 4)
        self.assertTrue(results[0]["pass"])
        self.assertFalse(results[1]["pass"])
        metrics = defect_rate(results)
        self.assertAlmostEqual(metrics["defect_rate"], 0.75)  # 3/4 有缺陷
        self.assertEqual(metrics["by_rule"].get(RULE_CITED_EXISTS), 1)

    def test_empty_input(self):
        self.assertEqual(defect_rate([])["total"], 0)
        self.assertEqual(check_answer("", self.index), [])


if __name__ == "__main__":
    unittest.main()
