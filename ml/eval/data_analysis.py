"""Data analysis for the report: size and structure of the sets, label balance, DEV/TEST overlap.

No model is needed. Run from the ml/ directory:

    uv run python eval/data_analysis.py            # -> results/data_analysis.md

Overlap check: every TEST dialogue is compared with every DEV dialogue by exact text and by the Jaccard
similarity of word 3-gram shingles of the whole transcript; the same for single messages longer than 40
characters. High similarity would mean a TEST dialogue (or its parts) leaked into development.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT.parent / "backend" / "data" / "dev_dataset.json"
TEST = ROOT / "data" / "test" / "test_dataset.json"
LABELS = {
    "TEST (external annotator)": ROOT / "data" / "test" / "test_labels.json",
    "DEV-19 (team)": ROOT / "data" / "reference" / "dev_reference.json",
}
OUT = ROOT / "results" / "data_analysis.md"


def records(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw = raw.get("data", raw) if isinstance(raw, dict) else raw
    return raw["records"] if isinstance(raw, dict) else raw


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def describe(name: str, recs: list[dict]) -> list[str]:
    turns = [len(r["transcript"]) for r in recs]
    chars = [sum(len(m["text"]) for m in r["transcript"]) for r in recs]
    roles = Counter(m["speaker"] for r in recs for m in r["transcript"])
    by = Counter((r.get("language"), r.get("channel")) for r in recs)
    empty = sum(1 for r in recs for m in r["transcript"] if not m["text"].strip())
    return [
        f"### {name}: {len(recs)} dialogues",
        "",
        "| | min | median | mean | max |",
        "|---|---|---|---|---|",
        f"| messages | {min(turns)} | {statistics.median(turns):.0f} | {statistics.mean(turns):.1f} | {max(turns)} |",
        f"| characters | {min(chars)} | {statistics.median(chars):.0f} | {statistics.mean(chars):.0f} | {max(chars)} |",
        "",
        "Language / channel: " + ", ".join(f"{lang} {ch}: {n}" for (lang, ch), n in sorted(by.items())),
        "",
        "Messages by speaker: " + ", ".join(f"{k} {v} ({v / sum(roles.values()):.0%})" for k, v in roles.most_common()),
        f"; empty messages: {empty}.",
        "",
    ]


def label_balance(name: str, path: Path) -> list[str]:
    labels = json.loads(path.read_text(encoding="utf-8"))["labels"]
    codes = sorted({c for item in labels for c in item["expected"]})
    lines = [f"### {name}: {len(labels)} dialogues", "", "| Criterion | answers |", "|---|---|"]
    for code in codes:
        values = Counter(str(item["expected"].get(code)) for item in labels if code in item["expected"])
        lines.append(f"| {code} | " + ", ".join(f"{v}: {n}" for v, n in sorted(values.items())) + " |")
    na = sum(1 for item in labels for v in item["expected"].values() if v == "na")
    total = sum(len(item["expected"]) for item in labels)
    lines += ["", f"N/A labels: {na} of {total} ({na / total:.0%}).", ""]
    return lines


HUMAN = ("client", "operator")  # bot and system messages are templates shared by all dialogues


def text_of(r: dict, speakers=HUMAN) -> str:
    return " ".join(m["text"] for m in r["transcript"] if m["speaker"] in speakers)


def nearest(sh: set, pool: dict[str, set], skip: str | None = None) -> tuple[str, float]:
    return max(((i, jaccard(sh, s)) for i, s in pool.items() if i != skip), key=lambda x: x[1])


def overlap(dev: list[dict], test: list[dict]) -> list[str]:
    lines = []
    for label, speakers in (("all messages", None), ("client and operator messages only", HUMAN)):
        get = (lambda r: " ".join(m["text"] for m in r["transcript"])) if speakers is None else text_of  # noqa: E731
        dev_sh = {r["conversation_id"]: shingles(get(r)) for r in dev}
        # Reference: how similar DEV dialogues are to their nearest *other* DEV dialogue.
        ref = sorted(nearest(s, dev_sh, skip=i)[1] for i, s in dev_sh.items())
        test_nn = [(r["conversation_id"], *nearest(shingles(get(r)), dev_sh)) for r in test]
        lines += [f"### {label}", "",
                  f"DEV to nearest other DEV dialogue (reference): median {statistics.median(ref):.3f}, "
                  f"90th percentile {ref[int(0.9 * len(ref))]:.3f}, max {ref[-1]:.3f}.", "",
                  "| TEST dialogue | nearest DEV dialogue | Jaccard (word 3-grams) |", "|---|---|---|"]
        lines += [f"| {cid} | {did} | {sim:.3f} |" for cid, did, sim in test_nn]
        above = [cid for cid, _, sim in test_nn if sim > ref[-1]]
        lines += ["", f"TEST dialogues more similar to DEV than any DEV dialogue is to another: {above or 'none'}.", ""]
    dev_msgs = {m["text"].strip().lower() for r in dev for m in r["transcript"]
                if m["speaker"] in HUMAN and len(m["text"].strip()) > 40}
    shared = [(r["conversation_id"], m["speaker"], m["text"][:90]) for r in test for m in r["transcript"]
              if m["speaker"] in HUMAN and len(m["text"].strip()) > 40 and m["text"].strip().lower() in dev_msgs]
    same_ids = sorted({r["conversation_id"] for r in dev} & {r["conversation_id"] for r in test})
    lines += ["### Identical client/operator messages (longer than 40 characters)", ""]
    lines += [f"- {cid} ({who}): {text}" for cid, who, text in shared] or ["none"]
    lines += ["", f"Shared conversation IDs: {same_ids or 'none'}.", ""]
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dev, test = records(DEV), records(TEST)
    md = ["# Data analysis", "", "## Sets", ""]
    md += describe("DEV", dev) + describe("TEST", test)
    md += ["## Label balance", ""]
    for name, path in LABELS.items():
        md += label_balance(name, path)
    md += ["## Overlap between DEV and TEST", ""] + overlap(dev, test)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nwritten {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
