English · [简体中文](./README.zh-CN.md)

# legal-hallu-guard · Citation Guardrails for Legal Answers

Deterministic citation checks for legal Q&A answers that carry citation markers: it catches the outputs that "look professional but cite fake law" — citing nonexistent articles, stitched-up or reworded quotations, and assertions with no citation behind them. Paired with a wrong-citation-rate metric, it turns "knowing the answers' limits" from a spoken claim into a measurable number. No model judgment involved — the wrong-citation rate becomes a metric instead of a vibe.

**Current version v0.2: three deterministic checks + a self-check on fictional cases + a constructed baseline on the real corpus — 14,212 real articles: FP 0.0%, fabricated / misquoted / uncited detection all 100%. The citation schema is aligned with the Citation structure of [statute-rag](https://github.com/1438388098-glitch/statute-rag), so this tool can consume its exported corpus directly. Zero dependencies — Python standard library only.**

## The problem

In legal Q&A, the most dangerous failure is not failing to answer — it is answering with complete confidence while citing a statute that does not exist. Within the usual layering of hallucination mitigation (grounding / structuring / consistency / confidence / disclaimers), "verifiable citations" is the most deterministic layer: it needs no model judgment, only comparison.

## Boundaries

- **Checks citations only; does not judge whether legal conclusions are correct.** The tool never evaluates whether an answer's conclusion is right — it only guarantees that cited articles exist, quotations are unaltered, and assertions have a source;
- **The assertion vocabulary is a v0.1 closed set**: 应当 (shall) / 不得 (must not) / 有权 (has the right to) / 构成 (constitutes) / 无效 (void) / 视为 (is deemed) / 负责 (is liable) / 承担 (bears). Assertions outside this list require extending the vocabulary;
- **Citation format convention**: `【law name 第X条】` or `【law name 第X条｜quotation】`, identical to statute-rag's Citation output convention;
- The built-in case corpus is **entirely fictional** text.

## How it works

```
answer with citations ──three checks──> findings (rule_id / severity / position / message)
  1 FABRICATED_CITATION  the cited (law name, article no.) is absent from the corpus index → P0
  2 MISQUOTED_TEXT       the quoted text is not a contiguous substring of the cited article
                         (whitespace-stripped comparison: stitching or rewording) → P0
  3 UNCITED_CLAIM        a sentence containing an assertion word does not overlap any citation block → P1
        ──metrics──> wrong-citation rate (share of defective answers) + per-rule counts
```

Each check is a pure function over the answer text and the corpus index.

Design decision: a sentence counts as supported if it **overlaps** any citation block — whether the citation itself is genuine is the job of checks 1/2, so the same defect is not double-counted; phrasings that do not point to a specific article (e.g. 「任何一方有权解除」 / "either party has the right to terminate") are not attributed to any citation.

## Usage

### CLI

```bash
# run against the built-in fictional corpus
python scripts/run_checks.py cases/selftest.jsonl
# run against your own corpus (statute-rag export format, JSONL)
python scripts/run_checks.py cases/selftest.jsonl --corpus data/corpus.jsonl
# run the constructed-evaluation baseline on a real corpus (deterministic, no model; see docs/baseline-report.md)
python scripts/run_baseline_eval.py --corpus /path/to/corpus.jsonl --out docs/baseline-metrics.json
```

The case file is JSONL with `answer_id` / `answer` fields.

### As a library

```python
from legal_hallu_guard.guard import build_index, check_answer, check_answers, defect_rate

index = build_index(corpus)             # corpus items: dicts with law / num / text fields
findings = check_answer(answer, index)  # [{rule_id, severity, position, message}]
results = check_answers(answers, index)
metrics = defect_rate(results)          # {"defect_rate", "defective", "total", "by_rule"}
```

Each of the three checks can be switched off individually (`check_exists` / `check_quote` / `check_claim`).

### Tests

9 unit tests: `python -m unittest discover -s tests`. CI runs the same suite on Python 3.9 and 3.13.

## Verification

### Constructed baseline on the real corpus (v0.2 · constructed evaluation, no model in the loop)

550 answers built by deterministic rules over statute-rag's real corpus (14,212 articles, 238 laws and judicial interpretations), fixed seed for reproducibility:

| Group | n | Rate |
|---|---|---|
| grounded (faithful quote + correct citation) | 250 | FP **0.0%** |
| fabricated (cites a nonexistent article no.) | 120 | detection **100.0%** |
| misquoted (number swap / synonym / stitched rewrite) | 120 | detection **100.0%** |
| uncited (assertion without citation) | 60 | detection **100.0%** |

The first run exposed a real guard bug: when the corpus contains duplicate (law name, article no.) entries, the index silently kept the last text, making verdicts depend on JSONL line order — 2.0% false positives. Fixed (the index now keeps all variants; a quote matching any variant counts as faithful) and locked with a regression test. Method, per-item FP analysis and boundary statements: [docs/baseline-report.md](./docs/baseline-report.md).

Reproduce: `python scripts/run_baseline_eval.py --corpus <statute-rag>/data/corpus.jsonl --out docs/baseline-metrics.json` (the corpus is not in this repo — point `--corpus` at statute-rag's `data/corpus.jsonl`; it is read in place, never copied into this repo).

### Self-check on fictional cases (v0.1, minimal smoke test)

| Case | Expected rule | Actual |
|---|---|---|
| good (citation + faithful quotation) | none | PASS |
| fabricated (cites a nonexistent article) | FABRICATED_CITATION | ✅ hit |
| misquote (one-character alteration in the quote) | MISQUOTED_TEXT | ✅ hit |
| uncited (assertion runs free outside citation blocks) | UNCITED_CLAIM | ✅ hit |

- Wrong-citation rate output: 75.0% (3/4, by design)
- Reproduce: `python scripts/run_checks.py cases/selftest.jsonl`

## Roadmap

- **v0.2**: ✅ done — ingested statute-rag's real corpus (14,212 articles), ran batch checks and produced a wrong-citation-rate baseline (constructed evaluation: FP 0.0%, fabricated/misquoted/uncited detection all 100%, [report](./docs/baseline-report.md)). Remaining: evaluation on real model Q&A outputs (requires a model API); domain-specific assertion vocabulary; chaining with clause-scope risk points (risk warnings automatically carry their statutory basis, re-checked by this tool)
- **v0.3**: evaluation of "refuse to answer when retrieval finds nothing" strategies; a hallucination-guard regression set

## License

[MIT](LICENSE)
