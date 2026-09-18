# -*- coding: utf-8 -*-
"""自测案例：虚构语料（5 条）+ 构造的好/坏答案，覆盖每类缺陷。全部虚构。"""

CORPUS = [
    {"id": 1, "law": "虚构测试法", "num": "第一条",
     "text": "为了规范测试行为，保障测试质量，制定本条。"},
    {"id": 2, "law": "虚构测试法", "num": "第二条",
     "text": "被测人应当如实提供材料，不得隐瞒有关情况。"},
    {"id": 3, "law": "虚构测试法", "num": "第三条",
     "text": "测试机构有权拒绝不符合规范的送检请求。"},
    {"id": 4, "law": "另一部虚构法", "num": "第一条",
     "text": "本办法适用于虚构场景下的辅助测试活动。"},
    {"id": 5, "law": "另一部虚构法", "num": "第九条",
     "text": "违反本办法规定的，由主管机关责令改正。"},
]

# 好答案：断言全部落在引用块内、引文保真
GOOD_ANSWER = (
    "根据【虚构测试法 第二条｜被测人应当如实提供材料，不得隐瞒有关情况。】"
    "被测人应当如实提供材料，不得隐瞒有关情况。"
)

# 坏答案 1：引用不存在的条文
BAD_FABRICATED = (
    "根据【虚构测试法 第九十九条】被测人应当如实提供材料。"
)

# 坏答案 2：引文拼接（原文里没有这个连续表述）
BAD_MISQUOTE = (
    "依据【虚构测试法 第二条｜被测人不得如实提供材料。】进行判断。"
)

# 坏答案 3：断言在引用块之外（引用块只覆盖第一句，「应当…」在第二句裸奔）
BAD_UNCITED = (
    "依据【虚构测试法 第三条】本条赋予拒绝权。测试机构应当直接吊销送检人资格。"
)

# 案例清单（answer_id, 期望触发的 rule_id 集合）
CASES = [
    {"answer_id": "good", "answer": GOOD_ANSWER, "expect_rules": set()},
    {"answer_id": "fabricated", "answer": BAD_FABRICATED, "expect_rules": {"FABRICATED_CITATION"}},
    {"answer_id": "misquote", "answer": BAD_MISQUOTE, "expect_rules": {"MISQUOTED_TEXT"}},
    {"answer_id": "uncited", "answer": BAD_UNCITED, "expect_rules": {"UNCITED_CLAIM"}},
]
