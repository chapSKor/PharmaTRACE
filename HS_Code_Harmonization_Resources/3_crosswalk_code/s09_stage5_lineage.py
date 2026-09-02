"""Stage 5. Write every journey out step by step, so a reader can follow one commodity by eye.


Stage 3 gave each commodity string its whole path as a single arrow-joined string, which is right
for joining and useless for reading. Stage 4 named the families. This turns the path back into
rows: one per step, carrying what the code was called at that step, when it held the trade, and
what it became.

It decides nothing and it discovers nothing. Every step it writes was walked in Stage 3, and a
control requires that re-walking here reproduces Stage 3's journey string EXACTLY, for all 572
commodity strings. If the two ever disagree the build fails rather than publishing two answers.

WHY IT RE-WALKS INSTEAD OF READING STAGE 3's STRING
----------------------------------------------------
The string holds codes and nothing else. A step also needs the LIFE the trade landed in: its
wording at that moment, and the months it held it. Reading those back from the string would mean
guessing which life, and guessing is what `receiving_span` exists to stop. So the walk is repeated
using Stage 3's own `receiving_span` and Stage 1a's own `REUSE_GAP_MONTHS`, both imported rather
than restated, and then checked against Stage 3's answer.

A RE-WORDING IS NOT A STEP
---------------------------
A code whose description is restated is still one code holding the trade, so it is one step. The
step's first month is the life that received the trade and its last month is the end of the whole
run, which is where the retirement is keyed. `rewordings_within_step` records how many restatements
were crossed, because a reader looking at a step whose wording changed underneath it deserves to be
told rather than to discover it.

WHAT A STEP'S STATUS MEANS
---------------------------
  succeeded          it ended and the trade transferred to the next step
  active             it is still trading in the delivery's last month
  left_chapter       the goods left Chapter 30
  not_a_retirement   trade stopped while the classification stood

The month is carried in its own column and never folded into the status. v1 wrote `ended_2006-12`,
which puts two facts in one string and forces every reader to parse it; the released shape can be
rendered from these columns in Stage 6 without the reverse being possible.
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s05_make_adjudication_queue import dotted  # noqa: E402
from s02_stage1_candidates import continues_the_span  # noqa: E402
from s07_stage3_route import ACTIVE, link_id_for, receiving_span  # noqa: E402

FLOWS = ("imports", "exports")

SUCCEEDED = "succeeded"

COLUMNS = [
    "record_id", "family_id", "flow", "step_number", "steps_in_journey",
    "hs_code", "description", "step_first_period", "step_last_period",
    "rewordings_within_step", "step_status", "next_hs_code",
]


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def stop(message, examples=()):
    print()
    print("Stage 5 STOPPED: %s" % message)
    for item in list(examples)[:8]:
        print("    %s" % (item,))
    raise SystemExit(1)


def run_to_the_end(spans, span, position):
    """From the life that received the trade, follow re-wordings to the end of the trading run.

    Stage 1a merges description-spans into one trading span where the gap is short enough, and the
    retirement is keyed on the END of that merged run. A step therefore ends where the run ends,
    not where the receiving life's wording happens to stop. Same threshold as Stage 1a and Stage 3,
    imported from the one place that owns it.
    """
    crossed = 0
    while True:
        lives = spans[span["hs_code"]]
        index = position[(span["hs_code"], span["first_period"])]
        following = lives[index + 1] if index + 1 < len(lives) else None
        if following is None:
            return span, crossed
        if not continues_the_span(span, following):
            return span, crossed
        span, crossed = following, crossed + 1


def unfold(flow, routed, families, inventory, resolved, delivery_end):
    """One row per step. The walk is Stage 3's, repeated, and checked against it afterwards."""
    spans = defaultdict(list)
    for record in inventory:
        spans[record["hs_code"]].append(record)
    for lives in spans.values():
        lives.sort(key=lambda s: s["first_period"])
    position = {(s["hs_code"], s["first_period"]): i
                for lives in spans.values() for i, s in enumerate(lives)}
    by_span = {r["span_id"]: r for r in families}

    rows, disagreed = [], []
    for journey in routed:
        family = by_span.get(journey["span_id"])
        if family is None:
            disagreed.append("%s has no family" % journey["span_id"])
            continue
        codes = [digits(c) for c in journey["journey"].split(" -> ")]
        landed = [s for s in spans[codes[0]] if s["first_period"] == journey["first_period"]]
        if not landed:
            disagreed.append("%s does not start at a life the inventory holds" % journey["span_id"])
            continue

        # WALKED FROM STAGE 2's ANSWERS, NOT FROM STAGE 3's STRING, and it was the other way round
        # until 2026-08-16. `walked` used to be built by appending Stage 3's own codes, so it
        # could differ only where the loop broke early and the comparison below could not fail.
        # Proven inert: replacing a journey with a hop Stage 2 never settled left Stage 5 exiting
        # 0 and publishing a step for the invented code. The path is now derived here the way
        # Stage 3 derives it -- from the resolved successions -- so the two can genuinely
        # disagree, which is the only reason walking twice is worth anything. Finding 108.
        here, walked, steps = landed[0], [], []
        while True:
            ending, crossed = run_to_the_end(spans, here, position)
            walked.append(here["hs_code"])
            steps.append((here, ending, crossed))
            if ending["last_period"] == delivery_end:
                status = ACTIVE
                break
            answer = resolved.get(link_id_for(flow, here["hs_code"], ending["last_period"]))
            if answer is None or answer["outcome"] not in (
                    "succeeded", "left_chapter", "not_a_retirement"):
                disagreed.append("%s: %s is not settled by Stage 2"
                                 % (journey["span_id"], here["hs_code"]))
                status = None
                break
            if answer["outcome"] != "succeeded":
                status = answer["outcome"]
                break
            landing = receiving_span(spans, digits(answer["successor"]), ending["last_period"])
            if landing is None:
                disagreed.append("%s: %s has no life open after %s"
                                 % (journey["span_id"], answer["successor"],
                                    ending["last_period"]))
                status = None
                break
            here = landing
        if status is None:
            continue
        if walked != codes or status != journey["terminal_status"]:
            disagreed.append("%s: re-walked %s ending %s, Stage 3 wrote %s ending %s"
                             % (journey["span_id"], " -> ".join(walked), status,
                                journey["journey"], journey["terminal_status"]))
            continue
        for number, (start_life, ending, crossed) in enumerate(steps, start=1):
            last = number == len(steps)
            rows.append({
                "record_id": family["record_id"], "family_id": family["family_id"], "flow": flow,
                "step_number": number, "steps_in_journey": len(steps),
                "hs_code": dotted(start_life["hs_code"]), "description": ending["description"],
                "step_first_period": start_life["first_period"],
                "step_last_period": ending["last_period"],
                "rewordings_within_step": crossed,
                "step_status": status if last else SUCCEEDED,
                "next_hs_code": "" if last else dotted(steps[number][0]["hs_code"]),
            })
    return rows, disagreed


def describe(flow, rows, routed):
    print("%s:" % flow)
    print("  commodity strings unfolded        : %d" % len({r["record_id"] for r in rows}))
    print("  steps written                     : %d" % len(rows))
    print("  where each step ends:")
    for status, n in sorted(Counter(r["step_status"] for r in rows).items(), key=lambda kv: -kv[1]):
        print("      %-18s %5d" % (status, n))
    lengths = Counter(int(r["steps_in_journey"]) for r in rows if int(r["step_number"]) == 1)
    print("  journeys by length:")
    for n, count in sorted(lengths.items()):
        print("      %d step(s) %s %d" % (n, "." * (12 - len(str(n))), count))
    crossed = sum(int(r["rewordings_within_step"]) for r in rows)
    print("  re-wordings crossed inside a step : %d, none of them a new step" % crossed)


def main():
    print("Stage 5: unfold every journey into steps. This stage decides nothing.")
    print()
    for flow in FLOWS:
        paths = {name: WORK_DIR / ("%s_%s.csv" % (name, flow))
                 for name in ("stage3_routed", "stage4_families", "commodity_inventory")}
        for name, path in paths.items():
            if not path.exists():
                stop("%s not found. Run the earlier stages first." % path)
        routed = load(paths["stage3_routed"])
        families = load(paths["stage4_families"])
        inventory = load(paths["commodity_inventory"])
        delivery_end = max(r["last_period"] for r in inventory)

        resolved = {r["link_id"]: r
                    for r in load(WORK_DIR / ("stage2_resolved_%s.csv" % flow))}
        rows, disagreed = unfold(flow, routed, families, inventory, resolved,
                                 delivery_end)

        if disagreed:
            stop("%d journey(s) could not be unfolded the way Stage 3 walked them. Two stages "
                 "disagreeing about one path is worse than either being wrong alone."
                 % len(disagreed), disagreed)
        expected_steps = sum(int(r["codes_in_journey"]) for r in routed)
        if len(rows) != expected_steps:
            stop("%d step(s) expected from Stage 3's own counts, %d written."
                 % (expected_steps, len(rows)))
        if len({r["record_id"] for r in rows}) != len(routed):
            stop("%d commodity string(s) in, %d unfolded."
                 % (len(routed), len({r["record_id"] for r in rows})))

        describe(flow, rows, routed)
        destination = WORK_DIR / ("stage5_lineage_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()

    print("Stage 5 complete. Every journey reads as a sequence a person can follow.")


if __name__ == "__main__":
    main()
