# Using ABCD to test the scorer

[ABCD](https://github.com/asappresearch/abcd) is ~10k English customer-service dialogs (agent, customer and system
events). It has **no quality scores**, so it cannot say how good an operator was and it is not training data for the
checklist. What it can do:

1. **A labelled English benchmark** with known answers for c1, c2, c3, c5, c6, c7, c8 (`tools/abcd_bench.py build`).
2. **An audit of the code-only layer** (`rules.py` regexes) on ~10k real agent openers and closers, with no model.

## Where the labels come from

| Kind | Source | Criteria |
|---|---|---|
| natural | ABCD structure on the untouched dialog: identity events ("Account has been pulled up"), flow (general-question flows need no identification), how the agent opens and closes. Ambiguous dialogs are left unlabelled. | c1, c2, c3, c7, c8 |
| mutation | One edit with a known effect: greeting removed or name added, order ID asked twice, identity checks removed before a protected action, closing removed or chat cut off, insult / off-company offer / leaked customer data inserted, complaint answered coldly or with empathy, one incoherent reply. Only the targeted criterion is labelled. | c1, c2, c3, c5, c6, c7, c8 |

Not covered: **c4** (correctness and completeness) needs domain judgement, and ABCD's shop has nothing in common
with Freedom Broker. c6 is only checked for the incoherent-reply case (0, or 4 counted as close).
These are team-made labels on English shop chats, not organizer ground truth: use them to find regressions and weak
probes, not as the accuracy number.

## Run

```sh
cd ml
uv run python tools/abcd_bench.py build abcd_v1_1_json.gz --size small     # 156 dialogs; medium 390
uv run python eval/run_dev.py data/abcd/abcd_dataset.json --labels data/abcd/abcd_labels.json --out runs/abcd
uv run python tools/abcd_bench.py score runs/abcd/responses.jsonl data/abcd/abcd_labels.json
uv run python tools/abcd_bench.py audit abcd_v1_1_json.gz                  # no model needed
```

`score` prints agreement per criterion and per mutation, then the misses. A weak row names the probe to look at, for
example `no_greeting` low = the `greeted` probe, `drop_identity` low = `identification_required`.
`small` is about 1 hour on the laptop with `qwen3.5:9b`; `--backend openai --workers 6` is a few minutes.

## What the audit found (English)

| Wording | Settled by code before | After |
|---|---|---|
| Introduction ("I'm Maya", "this is Amy") | 36/90 | 115/115 |
| Goodbye ("have a good one", "take care", "wonderful rest of your day") | 83.9% | 95.0% |
| Greeting ("hey") | 95.5% | 95.9% |

Fixed in `maestro/rules.py` (tests in `tests/test_pipeline.py`). On the team's own dialogs (DEV and test) the new
patterns settle 17 more introductions and no false positives. Left alone on purpose: "Welcome to ..." is not counted
as a greeting.
