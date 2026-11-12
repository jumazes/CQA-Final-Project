"""Check of the personal-data masking applied before a dialogue is sent to a cloud model.

The masking (backend/app/ml/pii.py) is a set of regular expressions. This script measures it on
hand-written cases in Russian, Kazakh and English: personal data that must be masked and look-alike
numbers that must stay (amounts, dates, order numbers, prices). It also counts how often each rule fires on
the DEV dialogues (counts only; matched values are never printed). All values below are invented.

    uv run python eval/pii_check.py        # -> results/pii_check.md
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PII = ROOT.parent / "backend" / "app" / "ml" / "pii.py"
DEV = ROOT.parent / "backend" / "data" / "dev_dataset.json"
OUT = ROOT / "results" / "pii_check.md"

spec = importlib.util.spec_from_file_location("pii", PII)
pii = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pii)

# (text, kinds that must be masked in it); an empty set means nothing may be masked.
CASES: list[tuple[str, set[str]]] = [
    ("Мой ИИН 900101300123, проверьте пожалуйста", {"iin"}),
    ("ЖСН: 851231400567", {"iin"}),
    ("My national ID is 020304500789.", {"iin"}),
    ("Карта 4400 4301 2345 6789 не проходит", {"card"}),
    ("card 5169-4931-0012-3456 was blocked", {"card"}),
    ("Картам 4400430123456789", {"card"}),
    ("Переведите на KZ12722C000012345678", {"iban"}),
    ("IBAN kz86125KZT5004100100 please", {"iban"}),
    ("Позвоните мне +7 701 234 56 78", {"phone"}),
    ("тел. 8 (747) 123-45-67", {"phone"}),
    ("Нөмірім +77012345678", {"phone"}),
    ("Call me at +44 20 7946 0958", {"phone"}),
    ("Почта ivanov.a@mail.kz", {"email"}),
    ("my email is john_doe+test@gmail.com", {"email"}),
    ("ИИН 900101300123, тел +7 701 234 56 78, почта a@b.kz", {"iin", "phone", "email"}),
    # look-alikes that must stay
    ("Сумма вывода 1 500 000 тенге", set()),
    ("Заявка №48213 от 12.03.2025 в 14:35", set()),
    ("Order 20250312 was executed at 187.45 USD", set()),
    ("Купил 300 акций AAPL по 172,5", set()),
    ("Счёт брокерский 12345678", set()),
    ("Комиссия 0,25% но не менее 1 000 тг", set()),
    ("Тикер KZTO, ISIN KZ1C00000876", set()),
    ("Код подтверждения 482913", set()),
    ("Дивиденды за 2024 год: 2 450,75 тенге", set()),
]

KIND_OF = {"[IIN]": "iin", "[CARD]": "card", "[IBAN]": "iban", "[PHONE]": "phone", "[EMAIL]": "email"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    md = ["# Personal-data masking check", "", "| # | input | masked | expected | result |", "|---|---|---|---|---|"]
    tp, fn, fp = Counter(), Counter(), Counter()
    for n, (text, want) in enumerate(CASES, start=1):
        counter: Counter[str] = Counter()
        out = pii.mask(text, counter)
        got = set(counter)
        for kind in want:
            (tp if kind in got else fn)[kind] += 1
        for kind in got - want:
            fp[kind] += 1
        ok = got == want
        md.append(f"| {n} | {text} | {out} | {', '.join(sorted(want)) or '—'} | {'ok' if ok else 'WRONG'} |")
    kinds = sorted(set(tp) | set(fn) | set(fp))
    md += ["", "| type | masked (of expected) | false alarms |", "|---|---|---|"]
    md += [f"| {k} | {tp[k]}/{tp[k] + fn[k]} | {fp[k]} |" for k in kinds]

    raw = json.loads(DEV.read_text(encoding="utf-8"))
    recs = raw["data"]["records"]
    fired, msgs = Counter(), 0
    for r in recs:
        for m in r["transcript"]:
            msgs += 1
            c: Counter[str] = Counter()
            pii.mask(m["text"], c)
            fired.update(c)
    md += ["", f"On DEV ({len(recs)} dialogues, {msgs} messages) the rules fired: "
           + (", ".join(f"{k} {v}" for k, v in fired.most_common()) or "never") + "."]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
