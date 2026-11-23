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

## Reading the numbers

- **Natural c1 is circular.** The natural c1 label uses the same introduction regex that `maestro/rules.py` now
  uses, so code and label agree by construction. In the small set 59 of 60 natural c1 labels are "no". These rows
  only show that the model does not invent an introduction. The mutation rows (`no_greeting`, `add_intro`) are the
  real c1 check.
- **c6 = 0 is debatable.** The mutation replaces one agent reply with nonsense. By the checklist scale a single slip
  the client can still follow is 7, not 0, so a 7 counts as a miss here. Read the `nonsequitur` row as "does the
  model notice the broken reply", not as c6 accuracy.
- **Read `abcd_bench.py score`, not the summary of `run_dev.py`.** `run_dev.py` compares strictly, so it does not
  count c6 = 4 as close. Its "final score mean abs error" is also meaningless here, because most dialogs have only
  one labelled criterion.

## Run

The source corpus is not in this repo. Download
[`abcd_v1.1.json.gz`](https://github.com/asappresearch/abcd/raw/master/data/abcd_v1.1.json.gz) (~37 MB) into `ml/`.
ABCD is released under the MIT license. `data/abcd/` holds dialogs derived from it, which `build` regenerates.

```sh
cd ml
uv run python tools/abcd_bench.py build abcd_v1.1.json.gz --size small     # 156 dialogs; medium 390
uv run python eval/run_dev.py data/abcd/abcd_dataset.json --labels data/abcd/abcd_labels.json --out runs/abcd
uv run python tools/abcd_bench.py score runs/abcd/responses.jsonl data/abcd/abcd_labels.json
uv run python tools/abcd_bench.py audit abcd_v1.1.json.gz                  # no model needed
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

The audit treats a wording as a clear introduction when the bench's own regex matches it, and that regex is close to
the one now in `rules.py`, so the 115/115 holds by construction. The check that matters is on the team's own dialogs.

Fixed in `maestro/rules.py` (tests in `tests/test_pipeline.py`). On the team's own dialogs (DEV and test, 78
dialogs) the new patterns settle 16 more introductions, all real English "Hi, I'm ..." openers, and 1 more goodbye
("Take care!"), with no false positives. Greetings are unchanged. Left alone on purpose: "Welcome to ..." is not
counted as a greeting.
