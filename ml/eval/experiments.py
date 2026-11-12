"""Experiments for the report: baseline vs. ablation vs. the full pipeline on the held-out test set.

Systems (all on the same local model, the same chats, the same checklist text and labels):
  single_prompt  - baseline: the whole checklist in one prompt (LLM as a judge)
  per_criterion  - ablation: one prompt per criterion (the generic evaluator), no narrow questions or rules
  pipeline       - the proposed method: narrow yes/no questions, deterministic rules, confirmation calls

Run from the ml/ directory (Ollama running, the model pulled):

  uv run python eval/experiments.py run --tag main
  uv run python eval/experiments.py run --tag stability --systems pipeline,single_prompt --runs 3 --temperature 0.3
  uv run python eval/experiments.py run --tag opt_off --systems pipeline     # after restarting Ollama without
                                                                            # OLLAMA_FLASH_ATTENTION / KV_CACHE_TYPE
  uv run python eval/experiments.py report

Every run writes results/<tag>/<system>-run<k>.jsonl (one line per dialog: answers, time, tokens) and
results/<tag>/<system>-run<k>.summary.json. `report` reads all of them and writes results/report.md and
results/tables.tex. Parameters are never chosen on the test set: the test set is only scored here.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maestro.baseline import evaluate_baseline  # noqa: E402
from maestro.contract import Criterion, EvaluateRequest, evaluate  # noqa: E402
from maestro.env import load_env_file  # noqa: E402
from maestro.llm import LLMOutputError, LLMUnavailable, OllamaClient  # noqa: E402
from maestro.scoring import InvalidAnswer, compute  # noqa: E402

SYSTEMS = ("single_prompt", "per_criterion", "pipeline")
DATA = ROOT / "data"
RESULTS = ROOT / "results"


# ---------------------------------------------------------------- data


def load_records(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    return raw["records"] if isinstance(raw, dict) else raw


def load_labels(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["conversation_id"]: item["expected"] for item in raw["labels"]}


def to_request(record: dict, criteria: list[Criterion], guidelines: list[str]) -> EvaluateRequest:
    transcript = [
        {"index": i, "timestamp": m.get("timestamp"), "speaker": m["speaker"], "text": m["text"]}
        for i, m in enumerate(record["transcript"])
    ]
    return EvaluateRequest(
        conversation_id=record["conversation_id"],
        channel=record.get("channel", "agent chat"),
        language=record.get("language", "RU"),
        transcript=transcript,
        criteria=criteria,
        guidelines=guidelines,
    )


def final_score(answers: dict) -> float | None:
    mapped = {f"0{code[-1]}": value for code, value in answers.items() if code[-1].isdigit()}
    try:
        return compute(mapped).final_score
    except (InvalidAnswer, KeyError, ValueError):
        return None


# ---------------------------------------------------------------- run


def vram(url: str, model: str) -> dict:
    """Memory of the loaded model as Ollama reports it (/api/ps): total and the part on the GPU."""
    try:
        models = httpx.get(f"{url}/api/ps", timeout=5).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return {}
    for m in models:
        if m.get("name") == model or m.get("model") == model:
            return {"size_gb": round(m.get("size", 0) / 1e9, 2), "size_vram_gb": round(m.get("size_vram", 0) / 1e9, 2),
                    "context_length": m.get("context_length")}
    return {}


def run(args: argparse.Namespace) -> int:
    load_env_file()
    criteria = [Criterion(**c) for c in json.loads(args.criteria.read_text(encoding="utf-8"))]
    guidelines = json.loads(args.guidelines.read_text(encoding="utf-8"))
    labels = load_labels(args.labels)
    records = [r for r in load_records(args.dataset) if r["conversation_id"] in labels]
    if args.limit:
        records = records[: args.limit]
    systems = [s.strip() for s in args.systems.split(",")]
    unknown = set(systems) - set(SYSTEMS)
    if unknown:
        raise SystemExit(f"unknown systems: {sorted(unknown)}")
    out_dir = RESULTS / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    env_flags = {k: os.getenv(k) for k in ("OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE")}
    print(f"{len(records)} labelled dialogs, systems {systems}, runs {args.runs}, temperature {args.temperature}")
    print(f"Ollama server flags seen by this shell (set them for the Ollama app): {env_flags}\n")

    for k in range(args.runs):
        seed = args.seed + k
        for system in systems:
            # The one-prompt baseline writes all criteria at once, so it needs a larger output budget.
            llm = OllamaClient.from_env(model=args.model, seed=seed, temperature=args.temperature,
                                        num_predict=1536 if system == "single_prompt" else None)
            status = llm.health()
            if not status["ok"]:
                print(f"error: {status['error']}", file=sys.stderr)
                return 2
            path = out_dir / f"{system}-run{k}.jsonl"
            rows, started = [], time.perf_counter()
            with path.open("w", encoding="utf-8") as out:
                for n, record in enumerate(records, start=1):
                    request = to_request(record, criteria, guidelines)
                    row = {"conversation_id": record["conversation_id"], "language": request.language,
                           "channel": request.channel, "turns": len(request.transcript)}
                    try:
                        if system == "single_prompt":
                            response = evaluate_baseline(request, llm)
                        else:
                            response = evaluate(request, llm, mode=system)
                    except (LLMOutputError, LLMUnavailable) as exc:
                        row.update(error=str(exc))
                        print(f"[{system} run{k} {n}/{len(records)}] {row['conversation_id']}: FAILED {exc}", flush=True)
                    else:
                        row.update(
                            answers={r.code: r.answer for r in response.results},
                            explanations={r.code: r.explanation for r in response.results},
                            seconds=response.duration_ms / 1000,
                            calls=response.usage.calls,
                            prompt_tokens=response.usage.prompt_tokens,
                            completion_tokens=response.usage.completion_tokens,
                        )
                        want = labels[row["conversation_id"]]
                        hits = sum(row["answers"].get(c) == v for c, v in want.items())
                        print(f"[{system} run{k} {n}/{len(records)}] {row['conversation_id']:10} "
                              f"{row['seconds']:5.1f}s {row['calls']:>2} calls  {hits}/{len(want)}", flush=True)
                    rows.append(row)
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
            summary = {
                "tag": args.tag, "system": system, "run": k, "seed": seed, "temperature": args.temperature,
                "model": llm.model, "dialogs": len(rows), "failed": sum("error" in r for r in rows),
                "wall_seconds": round(time.perf_counter() - started, 1),
                "memory": vram(llm.url, llm.model), "ollama_flags": env_flags,
                "host": {"python": platform.python_version(), "os": platform.platform()},
                "metrics": metrics(rows, labels),
            }
            (out_dir / f"{system}-run{k}.summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                                                  encoding="utf-8")
            m = summary["metrics"]
            print(f"--> {system} run{k}: accuracy {m['accuracy']:.1%} "
                  f"[{m['accuracy_ci95'][0]:.1%}, {m['accuracy_ci95'][1]:.1%}], "
                  f"{m['seconds_mean']:.1f}s/dialog, memory {summary['memory']}\n", flush=True)
    return 0


# ---------------------------------------------------------------- metrics


def bootstrap(per_dialog: list[tuple[int, int]], iterations: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval of label agreement, resampling dialogs (labels of one dialog are not independent)."""
    if not per_dialog:
        return (0.0, 0.0)
    rng = random.Random(seed)
    values = []
    for _ in range(iterations):
        sample = [per_dialog[rng.randrange(len(per_dialog))] for _ in per_dialog]
        total = sum(t for _, t in sample)
        values.append(sum(h for h, _ in sample) / total if total else 0.0)
    values.sort()
    return (values[int(0.025 * iterations)], values[int(0.975 * iterations) - 1])


def metrics(rows: list[dict], labels: dict[str, dict]) -> dict:
    per_criterion: dict[str, list[bool]] = defaultdict(list)
    per_language: dict[str, list[bool]] = defaultdict(list)
    per_dialog: list[tuple[int, int]] = []
    confusion: dict[str, Counter] = defaultdict(Counter)
    score_errors: list[float] = []
    flag = Counter()  # gross violation flag c8: tp, fp, fn
    for row in rows:
        want = labels[row["conversation_id"]]
        got = row.get("answers")
        if got is None:  # a failed dialog counts as wrong on every label
            per_dialog.append((0, len(want)))
            for code in want:
                per_criterion[code].append(False)
                per_language[row["language"]].append(False)
            continue
        hits = 0
        for code, value in want.items():
            ok = got.get(code) == value
            hits += ok
            per_criterion[code].append(ok)
            per_language[row["language"]].append(ok)
            if not ok:
                confusion[code][f"{value}->{got.get(code)}"] += 1
        per_dialog.append((hits, len(want)))
        ws, gs = final_score(want), final_score(got)
        if ws is not None and gs is not None:
            score_errors.append(abs(ws - gs))
        w8, g8 = want.get("c8") == "yes", got.get("c8") == "yes"
        flag["tp"] += w8 and g8
        flag["fp"] += g8 and not w8
        flag["fn"] += w8 and not g8
    total = [ok for v in per_criterion.values() for ok in v]
    done = [r for r in rows if "seconds" in r]
    return {
        "accuracy": sum(total) / len(total) if total else 0.0,
        "hits": sum(total), "labels": len(total),
        "accuracy_ci95": bootstrap(per_dialog),
        "per_criterion": {c: [sum(v), len(v)] for c, v in sorted(per_criterion.items())},
        "per_language": {lang: [sum(v), len(v)] for lang, v in sorted(per_language.items())},
        "confusion": {c: dict(v) for c, v in sorted(confusion.items())},
        "score_mae": statistics.mean(score_errors) if score_errors else None,
        "flag_c8": dict(flag),
        "seconds_mean": statistics.mean(r["seconds"] for r in done) if done else 0.0,
        "seconds_median": statistics.median(r["seconds"] for r in done) if done else 0.0,
        "calls_mean": statistics.mean(r["calls"] for r in done) if done else 0.0,
        "prompt_tokens_mean": statistics.mean(r["prompt_tokens"] for r in done) if done else 0.0,
        "completion_tokens_mean": statistics.mean(r["completion_tokens"] for r in done) if done else 0.0,
    }


def paired_difference(a: list[dict], b: list[dict], labels: dict, iterations: int = 2000) -> dict:
    """Accuracy of b minus a on the same dialogs, with a 95% paired bootstrap interval."""
    by_a = {r["conversation_id"]: r for r in a}
    pairs = []
    for rb in b:
        ra = by_a.get(rb["conversation_id"])
        if ra is None:
            continue
        want = labels[rb["conversation_id"]]
        hit = lambda r: sum((r.get("answers") or {}).get(c) == v for c, v in want.items())  # noqa: E731
        pairs.append((hit(ra), hit(rb), len(want)))
    rng = random.Random(1)
    diffs = []
    for _ in range(iterations):
        s = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        n = sum(t for _, _, t in s)
        diffs.append((sum(y for _, y, _ in s) - sum(x for x, _, _ in s)) / n)
    diffs.sort()
    n = sum(t for _, _, t in pairs)
    return {"difference": (sum(y for _, y, _ in pairs) - sum(x for x, _, _ in pairs)) / n,
            "ci95": (diffs[int(0.025 * iterations)], diffs[int(0.975 * iterations) - 1]),
            "share_of_bootstrap_above_zero": sum(d > 0 for d in diffs) / iterations}


def flip_rate(runs: list[list[dict]]) -> float:
    """Share of (dialog, criterion) answers that are not identical across repeated runs."""
    answers = defaultdict(set)
    for rows in runs:
        for r in rows:
            for code, value in (r.get("answers") or {}).items():
                answers[(r["conversation_id"], code)].add(str(value))
    return sum(len(v) > 1 for v in answers.values()) / len(answers) if answers else 0.0


# ---------------------------------------------------------------- report


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def report(args: argparse.Namespace) -> int:
    labels = load_labels(args.labels)
    summaries = sorted(RESULTS.glob("*/*.summary.json"))
    if not summaries:
        raise SystemExit(f"no runs in {RESULTS}")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in summaries:
        s = json.loads(p.read_text(encoding="utf-8"))
        s["rows"] = read_rows(p.with_name(p.name.replace(".summary.json", ".jsonl")))
        groups[(s["tag"], s["system"])].append(s)

    md = ["# Experiment results", "", f"Test set: {len(labels)} dialogs, "
          f"{sum(len(v) for v in labels.values())} labels.", ""]
    md += ["| Tag | System | Runs | T | Accuracy | 95% CI (run 0) | Score MAE | s/dialog | calls | tokens in/out | memory GB (GPU) | flip rate |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    tex_rows = []
    for (tag, system), runs in sorted(groups.items()):
        runs.sort(key=lambda s: s["run"])
        accs = [s["metrics"]["accuracy"] for s in runs]
        m0 = runs[0]["metrics"]
        acc = f"{statistics.mean(accs):.1%}" + (f" ± {statistics.stdev(accs):.1%}" if len(accs) > 1 else "")
        ci = f"[{m0['accuracy_ci95'][0]:.1%}, {m0['accuracy_ci95'][1]:.1%}]"
        mem = runs[0].get("memory") or {}
        mem_s = f"{mem.get('size_gb', '?')} ({mem.get('size_vram_gb', '?')})"
        flips = flip_rate([s["rows"] for s in runs]) if len(runs) > 1 else None
        mae = m0["score_mae"]
        md.append(f"| {tag} | {system} | {len(runs)} | {runs[0]['temperature']} | {acc} | {ci} | "
                  f"{mae:.1f} | {m0['seconds_mean']:.1f} | {m0['calls_mean']:.1f} | "
                  f"{m0['prompt_tokens_mean']:.0f}/{m0['completion_tokens_mean']:.0f} | {mem_s} | "
                  f"{'' if flips is None else f'{flips:.1%}'} |")
        tex_rows.append(f"{tag.replace('_', ' ')} & {system.replace('_', ' ')} & {acc.replace('%', '\\%')} & "
                        f"{ci.replace('%', '\\%')} & {mae:.1f} & {m0['seconds_mean']:.1f} & {m0['calls_mean']:.1f} \\\\")

    # Per criterion and per language, run 0 of every group.
    codes = sorted(next(iter(labels.values())))
    md += ["", "## Per criterion (run 0)", "", "| Tag | System | " + " | ".join(codes) + " |",
           "|---|---|" + "---|" * len(codes)]
    tex_crit = []
    for (tag, system), runs in sorted(groups.items()):
        pc = runs[0]["metrics"]["per_criterion"]
        cells = [f"{pc[c][0]}/{pc[c][1]}" if c in pc else "" for c in codes]
        md.append(f"| {tag} | {system} | " + " | ".join(cells) + " |")
        tex_crit.append(f"{system.replace('_', ' ')} ({tag.replace('_', ' ')}) & " + " & ".join(cells) + " \\\\")
    md += ["", "## Per language (run 0)", ""]
    for (tag, system), runs in sorted(groups.items()):
        pl = runs[0]["metrics"]["per_language"]
        md.append(f"- {tag} / {system}: " + ", ".join(f"{lang} {h}/{n} ({h / n:.0%})" for lang, (h, n) in pl.items()))
    md += ["", "## Gross violation flag c8 (run 0)", ""]
    for (tag, system), runs in sorted(groups.items()):
        md.append(f"- {tag} / {system}: {runs[0]['metrics']['flag_c8']}")
    md += ["", "## Errors: expected -> predicted (run 0)", ""]
    for (tag, system), runs in sorted(groups.items()):
        md.append(f"- {tag} / {system}: {json.dumps(runs[0]['metrics']['confusion'], ensure_ascii=False)}")

    # Paired comparisons on the same dialogs, run 0, same tag.
    md += ["", "## Paired comparisons (run 0, same dialogs)", ""]
    for (tag, system), runs in sorted(groups.items()):
        if system == "pipeline":
            for other in ("single_prompt", "per_criterion"):
                if (tag, other) in groups:
                    d = paired_difference(groups[(tag, other)][0]["rows"], runs[0]["rows"], labels)
                    md.append(f"- {tag}: pipeline - {other} = {d['difference']:+.1%}, 95% CI "
                              f"[{d['ci95'][0]:+.1%}, {d['ci95'][1]:+.1%}], P(diff > 0) = "
                              f"{d['share_of_bootstrap_above_zero']:.2f}")

    # Every disagreement of the pipeline, for the error analysis.
    md += ["", "## Pipeline disagreements with the labels (run 0 of each tag)", ""]
    for (tag, system), runs in sorted(groups.items()):
        if system != "pipeline":
            continue
        for row in runs[0]["rows"]:
            want, got = labels[row["conversation_id"]], row.get("answers") or {}
            for code, value in want.items():
                if got.get(code) != value:
                    why = (row.get("explanations") or {}).get(code, "")[:160].replace("|", "/")
                    md.append(f"- [{tag}] {row['conversation_id']} ({row['language']}) {code}: "
                              f"label {value}, predicted {got.get(code)}. {why}")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (RESULTS / "tables.tex").write_text(
        "% generated by eval/experiments.py report\n% main table rows: tag & system & accuracy & CI & MAE & s/dialog & calls\n"
        + "\n".join(tex_rows) + "\n\n% per criterion rows: " + " & ".join(codes) + "\n" + "\n".join(tex_crit) + "\n",
        encoding="utf-8")
    print("\n".join(md))
    print(f"\nwritten {RESULTS / 'report.md'} and {RESULTS / 'tables.tex'}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "report"):
        p = sub.add_parser(name)
        p.add_argument("--dataset", type=Path, default=DATA / "test" / "test_dataset.json")
        p.add_argument("--labels", type=Path, default=DATA / "test" / "test_labels.json")
        p.add_argument("--criteria", type=Path, default=DATA / "default_checklist.json")
        p.add_argument("--guidelines", type=Path, default=DATA / "default_guidelines.json")
        if name == "run":
            p.add_argument("--tag", required=True, help="name of this experiment, e.g. main, stability, opt_off")
            p.add_argument("--systems", default=",".join(SYSTEMS))
            p.add_argument("--runs", type=int, default=1)
            p.add_argument("--temperature", type=float, default=0.0)
            p.add_argument("--seed", type=int, default=42)
            p.add_argument("--model", help="Ollama model (default: MAESTRO_MODEL)")
            p.add_argument("--limit", type=int, help="only the first N dialogs (a smoke test)")
    args = parser.parse_args()
    return run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    raise SystemExit(main())
