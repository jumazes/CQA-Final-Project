"""Turn the ABCD customer-service corpus into a labelled English benchmark for Maestro.

ABCD (https://github.com/asappresearch/abcd) has no quality scores. What it does have is real structure we can
trust: system events ("Identity verification in progress", "Account has been pulled up"), the flow of every
dialog (which flows need identity verification and which are general questions), and how agents open and close.
Labels therefore come from two places:

  natural   labels read off the untouched dialog, only where ABCD's own structure makes them clear
            (c1 greeting + introduction, c2, c3, c7, c8). Anything ambiguous is left unlabelled.
  mutation  one controlled edit with a known effect (greeting removed, verification skipped, insult inserted, ...).
            Only the criterion the edit targets is labelled.

Run from the ml/ directory:

    uv run python tools/abcd_bench.py build  abcd_v1.1.json.gz --size small
    uv run python eval/run_dev.py data/abcd/abcd_dataset.json --labels data/abcd/abcd_labels.json --out runs/abcd
    uv run python tools/abcd_bench.py score  runs/abcd/responses.jsonl data/abcd/abcd_labels.json
    uv run python tools/abcd_bench.py audit  abcd_v1.1.json.gz        # no model needed: checks the regex layer
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Flows where the agent answers a general question and never needs to identify the customer.
NO_ID_FLOWS = {"storewide_query", "single_item_query", "troubleshoot_site"}
SPEAKER = {"agent": "operator", "customer": "client", "action": "system"}
NAMES = ["Maya", "Daniel", "Sofia", "Michael", "Aisha", "Thomas", "Elena", "Omar", "Grace", "Lucas"]
NOT_NAMES = {"sorry", "glad", "happy", "here", "just", "sure", "acme", "acmebrands", "acmecorp", "acmebrand"}

GREET = re.compile(r"\b(hello|hi|hey|greetings|good (morning|afternoon|evening)|welcome)\b", re.I)
GREET_STRIP = re.compile(r"^\s*((hello|hi|hey|greetings|good (morning|afternoon|evening))\b[\s,.!-]*)+", re.I)
INTRO = re.compile(r"\b(my name is|my name['’]s|i am|i['’]m|this is)\s+(?-i:([A-Z][a-z]{2,}))\b", re.I)
GOODBYE = re.compile(
    r"(have a (great|nice|good|wonderful|lovely|fantastic|blessed)\b|goodbye|\bbye\b|take care|farewell|see you|"
    r"talk (to you )?(soon|later)|enjoy your|be safe|stay well|end this chat|pleasure to help)", re.I)
OFFER = re.compile(
    r"(anything else|something else|further (assist|help)|other (questions|issues)|else i can|"
    r"(more|further) (help|questions)|can i help you with)", re.I)
ASK = re.compile(
    r"(\?|may i (have|get)|can i (have|get)|could (i|you)|please (provide|give|send|share|tell|confirm)|"
    r"what('s| is) your|do you have)", re.I)
DETAIL_TYPES = {
    "name": re.compile(r"\bname\b", re.I), "username": re.compile(r"user ?name", re.I),
    "email": re.compile(r"e-?mail", re.I), "order": re.compile(r"order (id|number)|\border\b.*\bid\b", re.I),
    "zip": re.compile(r"\bzip\b", re.I), "phone": re.compile(r"phone", re.I),
    "membership": re.compile(r"member(ship)?( level)?", re.I), "account": re.compile(r"account (id|number)", re.I),
}
ID_EVENT = re.compile(r"identity verification|account has been pulled up", re.I)
VERIFY_NOISE = re.compile(r"identity verification|account has been pulled up|purchase validation", re.I)
PROTECTED_ACTION = re.compile(r"has been (made|generated|updated|created|changed|entered)", re.I)
RUDE = re.compile(r"\b(stupid|idiot|dumb|shut up|not my problem|whatever)\b", re.I)
ORDER_ID = re.compile(r"\b\d{8,}\b")

LINES = {
    "insult": [
        "Honestly, that is a stupid question. Read the page before you write to us.",
        "You clearly have no idea what you are doing, are you an idiot?",
    ],
    "off_company_offer": [
        "Between us, I can sort this faster if you send $20 straight to my personal card instead of going through the company.",
        "I can do this off the books if you pay me privately, the company does not need to know.",
    ],
    "confidential_disclosure": [
        "By the way, another customer, John Carter, had the same issue yesterday. His card ends in 4417 and he lives at 12 Oak St.",
    ],
}
COMPLAINT = [
    "This is really frustrating, I have been trying to sort this out for a week.",
    "I'm honestly annoyed, this is the second time this has happened to me.",
]
DISMISSIVE = [
    "That's not my problem. Read the policy.",
    "Not my concern. Everyone has this issue, just follow the standard procedure.",
]
EMPATHETIC = [
    "I'm really sorry about the trouble, a week is far too long. Let me sort this out for you right now.",
    "I understand how annoying it is that this happened twice, I'm sorry. Let's fix it now.",
]
INCOHERENT = [
    "The blue invoice is happening before the tomorrow of your shirt, so no, yes.",
    "Please restart the warehouse of the password and also do not do that, thank you red.",
]

Turns = list[list[str]]  # [[speaker, text], ...] with ABCD speakers: agent / customer / action


# ---------- helpers ----------

def agents(turns: Turns) -> list[int]:
    return [i for i, (s, _) in enumerate(turns) if s == "agent"]


def customers(turns: Turns) -> list[int]:
    return [i for i, (s, _) in enumerate(turns) if s == "customer"]


def flow_needs_id(conv: dict) -> bool:
    return conv["scenario"]["flow"] not in NO_ID_FLOWS


def has_id_event(turns: Turns) -> bool:
    return any(s == "action" and ID_EVENT.search(t) for s, t in turns)


def introduced(text: str) -> bool:
    return any(m.group(2).lower() not in NOT_NAMES for m in INTRO.finditer(text))


def tail_text(turns: Turns, n: int = 3) -> str:
    return " ".join(turns[i][1] for i in agents(turns)[-n:])


def remainder(text: str) -> str:
    rest = GREET_STRIP.sub("", text).strip()
    return rest[:1].upper() + rest[1:] if rest else rest


# ---------- natural labels ----------

def natural_labels(conv: dict) -> dict:
    turns = conv["original"]
    ag = agents(turns)
    if len(ag) < 3 or len(customers(turns)) < 2:
        return {}
    labels: dict = {}
    first = turns[ag[0]][1]
    labels["c1"] = "yes" if GREET.search(first) and introduced(first) else "no"

    asks, kinds, repeated = [], Counter(), False
    for i in ag[1:]:
        text = turns[i][1]
        if ASK.search(text) and not OFFER.search(text) and not GOODBYE.search(text):
            asks.append(i)
            for kind, pattern in DETAIL_TYPES.items():
                if pattern.search(text):
                    kinds[kind] += 1
    repeated = any(v > 1 for v in kinds.values())
    needs_id, id_event = flow_needs_id(conv), has_id_event(turns)
    if needs_id and id_event and asks and not repeated:
        labels["c2"] = "yes"
    elif not needs_id and not asks:
        labels["c2"] = "na"

    if needs_id and id_event:
        labels["c3"] = "yes"
    elif not needs_id and not id_event:
        labels["c3"] = "na"

    tail = tail_text(turns, 4 if turns[-1][0] == "customer" else 3)
    if GOODBYE.search(tail) and OFFER.search(tail):
        labels["c7"] = "yes"
    elif not GOODBYE.search(tail) and not OFFER.search(tail) and turns[-1][0] == "agent":
        labels["c7"] = "no"

    if not any(RUDE.search(turns[i][1]) for i in ag):
        labels["c8"] = "no"
    return labels


# ---------- mutations: each returns (new_turns, expected) or None when the base does not fit ----------

def m_no_greeting(conv, rng):
    turns = [list(t) for t in conv["original"]]
    ag = agents(turns)
    if not ag or not GREET.search(turns[ag[0]][1]):
        return None
    rest = remainder(turns[ag[0]][1])
    turns[ag[0]][1] = rest if len(rest) > 8 and not GREET.search(rest) else "What can I do for you?"
    return turns, {"c1": "no"}


def m_add_intro(conv, rng):
    turns = [list(t) for t in conv["original"]]
    ag = agents(turns)
    if not ag or introduced(turns[ag[0]][1]) or not GREET.search(turns[ag[0]][1]):
        return None
    name = rng.choice(NAMES)
    opener = rng.choice([f"Hello, my name is {name}. ", f"Hi, I'm {name} from support. ", f"Good afternoon! This is {name}. "])
    turns[ag[0]][1] = opener + (remainder(turns[ag[0]][1]) or "How can I help you?")
    return turns, {"c1": "yes"}


def m_reask_known(conv, rng):
    turns = [list(t) for t in conv["original"]]
    if not flow_needs_id_and_event(conv):
        return None
    for j in customers(turns):
        if ORDER_ID.search(turns[j][1]):
            nxt = next((k for k in range(j + 1, len(turns)) if turns[k][0] == "agent"), None)
            if nxt is None or nxt >= len(turns) - 3:
                return None
            turns[nxt:nxt] = [["agent", "Sorry, could you send me your order ID once more?"],
                              ["customer", "I already sent it a moment ago, it is in my message above."]]
            return turns, {"c2": "no"}
    return None


def flow_needs_id_and_event(conv) -> bool:
    return flow_needs_id(conv) and has_id_event(conv["original"])


def m_drop_identity(conv, rng):
    turns = [list(t) for t in conv["original"]]
    if not flow_needs_id_and_event(conv):
        return None
    last_action = max((i for i, (s, t) in enumerate(turns) if s == "action" and PROTECTED_ACTION.search(t)), default=None)
    if last_action is None:
        return None
    # What the agent asks for to identify the customer; the customer's replies right after are dropped too.
    ask = re.compile(r"(full name|your name|user ?name|e-?mail|order (id|number)|account (id|number)|phone number|zip)", re.I)
    drop: set[int] = set()
    ag = agents(turns)
    for i in ag[1:]:
        if i < last_action and ask.search(turns[i][1]):
            drop.add(i)
            k = i + 1
            while k < len(turns) and turns[k][0] == "customer":
                drop.add(k)
                k += 1
    for i, (s, t) in enumerate(turns):
        if s == "action" and VERIFY_NOISE.search(t):
            drop.add(i)
    kept = [t for i, t in enumerate(turns) if i not in drop]
    if any(re.search(r"verif|identity", t, re.I) for sp, t in kept if sp == "agent"):
        return None  # the agent still claims to have verified the customer, so "no" would be a wrong label
    if not drop or len(kept) < 8 or len(agents(kept)) < 3 or not any(s == "action" and PROTECTED_ACTION.search(t) for s, t in kept):
        return None
    return kept, {"c3": "no"}


def m_no_goodbye(conv, rng):
    turns = [list(t) for t in conv["original"]]
    if natural_labels(conv).get("c7") != "yes":
        return None
    while turns and (turns[-1][0] != "agent" or GOODBYE.search(turns[-1][1]) or OFFER.search(turns[-1][1])
                     or turns[-1][1].rstrip().endswith("?")):
        turns.pop()
    if len(turns) < 6 or len(agents(turns)) < 3:
        return None
    turns.append(["action", "Agent closed the chat."])
    return turns, {"c7": "no"}


def m_cut_off(conv, rng):
    turns = [list(t) for t in conv["original"]]
    cuts = [i for i in customers(turns) if 0.4 * len(turns) <= i <= 0.75 * len(turns)]
    if not cuts:
        return None
    cut = rng.choice(cuts)
    kept = turns[: cut + 1]
    if len(agents(kept)) < 2 or GOODBYE.search(tail_text(kept)):
        return None
    kept.append(["action", "Customer left the chat."])
    return kept, {"c7": "na"}


def _insert_after_customer(turns: Turns, rng, rows: Turns):
    options = [i for i in customers(turns)[1:-1]]
    if not options:
        return None
    at = rng.choice(options) + 1
    turns[at:at] = rows
    return turns


def _gross(kind):
    def mutate(conv, rng):
        turns = _insert_after_customer([list(t) for t in conv["original"]], rng, [["agent", rng.choice(LINES[kind])]])
        return (turns, {"c8": "yes"}) if turns else None
    return mutate


def _complaint(reply_pool, expected):
    def mutate(conv, rng):
        turns = [list(t) for t in conv["original"]]
        cs = customers(turns)
        if len(cs) < 3:
            return None
        at = cs[1] + 1
        turns[at:at] = [["customer", rng.choice(COMPLAINT)], ["agent", rng.choice(reply_pool)]]
        return turns, {"c5": expected}
    return mutate


def m_nonsequitur(conv, rng):
    turns = [list(t) for t in conv["original"]]
    ag = agents(turns)
    middle = ag[2:-3]
    if not middle:
        return None
    turns[rng.choice(middle)][1] = rng.choice(INCOHERENT)
    return turns, {"c6": 0}


MUTATIONS = {
    "no_greeting": m_no_greeting, "add_intro": m_add_intro, "reask_known": m_reask_known,
    "drop_identity": m_drop_identity, "no_goodbye": m_no_goodbye, "cut_off": m_cut_off,
    "insult": _gross("insult"), "off_company_offer": _gross("off_company_offer"),
    "confidential_disclosure": _gross("confidential_disclosure"),
    "complaint_dismissed": _complaint(DISMISSIVE, "no"), "complaint_empathy": _complaint(EMPATHETIC, "yes"),
    "nonsequitur": m_nonsequitur,
}
SIZES = {"small": (60, 8), "medium": (150, 20), "large": (300, 40)}  # natural dialogs, dialogs per mutation


# ---------- build ----------

def to_record(cid: str, conv: dict, turns: Turns, rng: random.Random) -> dict:
    seconds, transcript = 0, []
    for speaker, text in turns:
        seconds += rng.randint(8, 45) if speaker != "action" else rng.randint(1, 3)
        transcript.append({"timestamp": f"{seconds // 60:02d}:{seconds % 60:02d}", "speaker": SPEAKER[speaker],
                           "text": text.strip() or "[empty]"})
    return {"conversation_id": cid, "channel": "agent chat", "language": "EN", "transcript": transcript,
            "audio_url": None, "abcd": {"convo_id": conv["convo_id"], "flow": conv["scenario"]["flow"],
                                        "subflow": conv["scenario"]["subflow"]}}


def load(path: Path, split: str) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    return [c for s in (data if split == "all" else [split]) for c in (data[s] if split != "all" else data[s])]


def build(args) -> None:
    rng = random.Random(args.seed)
    pool = load(args.abcd, args.split)
    rng.shuffle(pool)
    n_natural, n_mut = SIZES[args.size]
    n_natural, n_mut = args.natural or n_natural, args.per_mutation or n_mut
    records, labels = [], []

    for conv in pool:
        if len([x for x in labels if x["kind"] == "natural"]) >= n_natural:
            break
        found = natural_labels(conv)
        if found:
            records.append(to_record(f"abcd-{conv['convo_id']}", conv, conv["original"], rng))
            labels.append({"conversation_id": records[-1]["conversation_id"], "kind": "natural", "mutation": None,
                           "expected": found})
    for name, mutate in MUTATIONS.items():
        made = 0
        for conv in pool:
            if made >= n_mut:
                break
            outcome = mutate(conv, rng)
            if outcome is None:
                continue
            turns, expected = outcome
            records.append(to_record(f"abcd-{conv['convo_id']}-{name}", conv, turns, rng))
            labels.append({"conversation_id": records[-1]["conversation_id"], "kind": "mutation", "mutation": name,
                           "expected": expected})
            made += 1
        if made < n_mut:
            print(f"note: only {made}/{n_mut} bases fit mutation {name}")

    args.out.mkdir(parents=True, exist_ok=True)
    dataset = {"error": None, "isSuccess": True,
               "data": {"dataset_group_id": "ABCD", "total_records": len(records), "records": records}}
    (args.out / "abcd_dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")
    about = ("Benchmark derived from ABCD (asappresearch/abcd). Natural labels come from ABCD structure, mutation "
             "labels from a known edit. Only the labelled criteria are compared. NOT organizer ground truth.")
    (args.out / "abcd_labels.json").write_text(
        json.dumps({"about": about, "labels": labels}, ensure_ascii=False, indent=1), encoding="utf-8")
    per = Counter()
    for item in labels:
        for code, value in item["expected"].items():
            per[(code, str(value))] += 1
    print(f"{len(records)} dialogs -> {args.out}")
    print("label counts:", {f"{c}={v}": n for (c, v), n in sorted(per.items())})


# ---------- score ----------

def score(args) -> None:
    labels = {x["conversation_id"]: x for x in json.loads(args.labels.read_text(encoding="utf-8"))["labels"]}
    cells: dict[tuple, list[bool]] = defaultdict(list)
    misses = []
    for line in args.responses.read_text(encoding="utf-8").splitlines():
        resp = json.loads(line)
        item = labels.get(resp["conversation_id"])
        if not item:
            continue
        got = {r["code"]: r["answer"] for r in resp["results"]}
        for code, want in item["expected"].items():
            ok = got.get(code) == want
            if code == "c6" and want == 0:  # an incoherent reply: 0 is right, 4 (client has to ask again) is close
                ok = got.get(code) in (0, 4)
            cells[(code, item["mutation"] or "natural")].append(ok)
            if not ok:
                misses.append(f"{resp['conversation_id']}: {code} want {want} got {got.get(code)}")
    total = [ok for v in cells.values() for ok in v]
    print(f"agreement: {sum(total)}/{len(total)} = {sum(total) / max(len(total), 1):.1%}\n")
    print(f"{'criterion':10}{'set':26}{'hits':>8}")
    for (code, kind), values in sorted(cells.items()):
        print(f"{code:10}{kind:26}{sum(values):>4}/{len(values):<4} {sum(values) / len(values):.0%}")
    print("\nmisses (first 40):")
    print("\n".join(misses[:40]))


# ---------- audit: the code-only layer against ABCD wording ----------

def audit(args) -> None:
    from maestro.rules import GOODBYE as P_GOODBYE, GREETING as P_GREETING, INTRODUCTION as P_INTRO

    convs = load(args.abcd, "all")
    stats = {"greeting": [0, 0], "introduction": [0, 0], "goodbye": [0, 0]}
    missed: dict[str, Counter] = {k: Counter() for k in stats}
    for conv in convs:
        turns = conv["original"]
        ag = agents(turns)
        if len(ag) < 3:
            continue
        first = turns[ag[0]][1]
        tail = " ".join(turns[i][1] for i in ag[-2:])
        for key, mine, project, text in (("greeting", GREET, P_GREETING, first), ("introduction", INTRO, P_INTRO, first),
                                         ("goodbye", GOODBYE, P_GOODBYE, tail)):
            truth = introduced(text) if key == "introduction" else bool(mine.search(text))
            if truth:
                stats[key][1] += 1
                if project.search(text):
                    stats[key][0] += 1
                else:
                    missed[key][re.sub(r"\s+", " ", text.lower().strip())[:90]] += 1
    print("project regex hits on wording that clearly is a greeting / introduction / goodbye (ABCD, English):")
    for key, (hit, total) in stats.items():
        print(f"  {key:13} {hit}/{total} = {hit / max(total, 1):.1%} settled without the model")
        for text, n in missed[key].most_common(args.top):
            print(f"      missed x{n}: {text}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("abcd", type=Path, help="abcd_v1.1.json.gz")
    b.add_argument("--out", type=Path, default=ROOT / "data" / "abcd")
    b.add_argument("--size", choices=SIZES, default="small")
    b.add_argument("--natural", type=int, help="override the number of untouched dialogs")
    b.add_argument("--per-mutation", type=int, help="override dialogs per mutation")
    b.add_argument("--split", choices=["train", "dev", "test", "all"], default="dev")
    b.add_argument("--seed", type=int, default=7)
    b.set_defaults(fn=build)
    s = sub.add_parser("score")
    s.add_argument("responses", type=Path)
    s.add_argument("labels", type=Path)
    s.set_defaults(fn=score)
    a = sub.add_parser("audit")
    a.add_argument("abcd", type=Path)
    a.add_argument("--top", type=int, default=12)
    a.set_defaults(fn=audit)
    args = parser.parse_args()
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
