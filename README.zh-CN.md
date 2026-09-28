[English](./README.md) · 简体中文

# legal-hallu-guard · 法律答案引用护栏

对「带引用标记的法律答案」做**确定性引用校验**，抓「看起来很专业但引用是假的」的输出——引用不存在的条文、引文拼接改写、断言无引用支撑。配套错误引用率指标，让「懂边界」从口说变成可测量；全程无模型判断，错误引用率是可测的指标，不是感觉。

**当前版本 v0.2：三类确定性校验 + 虚构案例自检 + 真实语料构造基线——14,212 条真实法条上 FP=0.0%，fabricated / misquoted / uncited 检出率均 100%。与 statute-rag 的 Citation 结构对齐，可直接消费其导出语料。零依赖，仅用 Python 标准库。**

## 问题

法律问答里最危险的不是答不上，而是**一本正经地引一部不存在的法条**。幻觉治理的分层里（grounding / 结构化 / 一致性 / 置信度 / 免责），「引用可校验」是最确定性的一层：不需要模型判断，只需要比对。

## 边界

- **只校验引用，不判断法律观点对错**：本工具不评价结论是否正确，只保证「引用的条文存在、引文没被拼接、断言有出处」；
- **断言词表是 v0.1 封闭集**（应当/不得/有权/构成/无效/视为/负责/承担），漏网断言需扩表；
- **引用格式约定**：`【法名 第X条】` 或 `【法名 第X条｜引文】`，与 statute-rag 的 Citation 输出约定一致；
- 内置案例语料为**完全虚构**文本。

## 机制

```
带引用答案 ──三类校验──> findings（rule_id/severity/position/message）
  1 FABRICATED_CITATION  引用的（法名，条号）不在语料索引        → P0
  2 MISQUOTED_TEXT       引文不是所引条文的连续子串（去空白比对）  → P0
  3 UNCITED_CLAIM        含断言词的句子与任何引用块无重叠          → P1
        ──metrics──> 错误引用率（有缺陷答案占比）+ 按规则计数
```

每次校验都是对答案文本与语料索引的纯函数。

设计决策：句子与引用块**有重叠**即算有支撑——引用本身的真假由校验 1/2 负责，避免对同一缺陷双重扣分；「任何一方有权解除」这类不指向具体条文的表述不计入引用归属。

## 使用

### CLI

```bash
# 用内置虚构语料跑
python scripts/run_checks.py cases/selftest.jsonl
# 用自备语料跑（statute-rag 导出格式，JSONL）
python scripts/run_checks.py cases/selftest.jsonl --corpus data/corpus.jsonl
# 在真实语料上跑构造评测基线（确定性构造，无模型；详见 docs/baseline-report.md）
python scripts/run_baseline_eval.py --corpus /path/to/corpus.jsonl --out docs/baseline-metrics.json
```

案例文件为 JSONL，字段 `answer_id` / `answer`。

### 作为库调用

```python
from legal_hallu_guard.guard import build_index, check_answer, check_answers, defect_rate

index = build_index(corpus)             # corpus 元素：含 law / num / text 字段的 dict
findings = check_answer(answer, index)  # [{rule_id, severity, position, message}]
results = check_answers(answers, index)
metrics = defect_rate(results)          # {"defect_rate", "defective", "total", "by_rule"}
```

三类校验可各自开关（`check_exists` / `check_quote` / `check_claim`）。

### 测试

单元测试 9 例：`python -m unittest discover -s tests`。CI 在 Python 3.9 与 3.13 上运行同一套测试。

## 验证

### 真实语料构造基线（v0.2 · 构造评测，无模型）

在 statute-rag 真实语料（14,212 条 / 238 部法律法规及司法解释）上以确定性规则构造 550 条答案跑批量校验，固定种子可复现：

| 组别 | n | 比率 |
|---|---|---|
| grounded（引文保真+引用正确） | 250 | 误报 FP **0.0%** |
| fabricated（引不存在条号） | 120 | 检出 **100.0%** |
| misquoted（数字替换/同义词/拼接改写） | 120 | 检出 **100.0%** |
| uncited（断言无引用） | 60 | 检出 **100.0%** |

首轮实跑曾暴露一个真 bug：语料中同一（法名，条号）重复时索引「后者覆盖前者」，判定随行序翻转，误报 2.0%——已修复（索引保留全部版本，与任一版本文本一致即算保真）并锁定回归测试。方法、逐条误报分析与边界声明见 [docs/baseline-report.md](./docs/baseline-report.md)。

复现：`python scripts/run_baseline_eval.py --out docs/baseline-metrics.json`（语料只读引用，不复制进本仓库）。

### 虚构案例自检（v0.1，最小冒烟）

| 案例 | 期望触发 | 实际 |
|---|---|---|
| good（引用+引文保真） | 无 | PASS |
| fabricated（引不存在条文） | FABRICATED_CITATION | ✅ 命中 |
| misquote（引文改写一个字） | MISQUOTED_TEXT | ✅ 命中 |
| uncited（断言在引用块外裸奔） | UNCITED_CLAIM | ✅ 命中 |

- 错误引用率输出：75.0%（3/4，按设计）
- 复现：`python scripts/run_checks.py cases/selftest.jsonl`

## Roadmap

- **v0.2**：✅ 已完成——接入 [statute-rag](https://github.com/1438388098-glitch/statute-rag) 真实语料（14,212 条）跑批量校验，产出「错误引用率基线」（构造评测，FP=0.0%，三类检出均 100%，[报告](./docs/baseline-report.md)）。待办：对真实模型问答输出的评测（需模型 API）；断言词表领域化扩展；与 clause-scope 风险点串联（风险提示自动携带法条依据并由本工具复核）
- **v0.3**：「检索不到就拒答」策略评测、幻觉护栏回归集

## License

[MIT](LICENSE)
