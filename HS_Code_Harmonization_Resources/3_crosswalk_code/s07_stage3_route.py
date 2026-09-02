"""Stage 3. Follow every commodity through the chain of successions until it stops.


Stage 2 answered one question per retirement: where did THIS line go. That is one hop. A reader
asking "where did this commodity end up" needs the whole path, and a family cannot be built from
hops alone. This stage composes them.

It decides nothing. Every edge it walks was already settled by the record or by the analyst in
Stage 2, and this stage refuses to run if it meets one that was not.

TWO KINDS OF EDGE, AND ONLY ONE OF THEM IS A SUCCESSION
--------------------------------------------------------
A commodity string can end for two quite different reasons and the difference matters here:

  RE-WORDING   The code keeps trading and Statistics Canada restates its description. The
               inventory holds one row per code AND description, so `3002.90.00.90` is two rows
               either side of 2022-01. That is one commodity carrying on, not two, and the code
               must appear in the journey ONCE. Finding 100 is about exactly these boundaries.

  SUCCESSION   The classification ended and the trade transferred to a different code. That is a
               Stage 2 answer and it is the only kind of edge that adds a code to the journey.

Stage 1a already merges description-spans into trading spans, splitting only where a number was
left empty longer than REUSE_GAP_MONTHS and handed to different goods. This stage uses the same
threshold, imported rather than restated, so a re-wording and a reuse can never disagree between
the two stages. A reuse is a different commodity and the journey stops before it.

WHERE A JOURNEY ENDS
--------------------
  active            the code is still trading in the delivery's last month
  left_chapter      the goods left Chapter 30, decided and deliberate
  not_a_retirement  trade stopped while the classification stood (Stage 1a's `trade_ceased_only`)

There is no fourth. A row that is open, held or unresolved would produce a journey that neither
continues nor ends, and Stage 2 now leaves none: the build refuses rather than writing one.

WHAT IT REFUSES TO DO
---------------------
  - walk an edge Stage 2 did not settle, or one it settled as anything but `succeeded`
  - follow a successor into a span that had already closed before the predecessor stopped
  - loop, however long the loop is
  - lose a commodity string, invent one, or let the value stop reconciling

THE LOOP REFUSAL IS A BACKSTOP AND CANNOT FIRE, WHICH IS SAID HERE RATHER THAN HIDDEN
--------------------------------------------------------------------------------------
Every hop lands on a life still open AFTER the predecessor stopped, so a walk moves strictly
forward in time and cannot return to where it has been. Two codes naming each other produce
`stranded`, not `cycle`, because neither outlives the other. The refusal is kept because it costs
nothing and because the monotonic rule could be edited away by someone who did not know it was
load-bearing. It is not counted as a control: `check_stage3_route.py` reports it as a disclosure
and asserts the monotonic property over the whole delivery instead, which is the thing that would
actually break first.
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s05_make_adjudication_queue import dotted  # noqa: E402
# Imported, never restated. Stage 1a owns what separates a re-wording from a reuse, and two files
# holding one threshold is how they drift apart.
from s02_stage1_candidates import continues_the_span  # noqa: E402

FLOWS = ("imports", "exports")

ACTIVE = "active"
LEFT_CHAPTER = "left_chapter"
NOT_A_RETIREMENT = "not_a_retirement"

COLUMNS = [
    "span_id", "flow", "hs_code", "description", "first_period", "last_period", "value_cad",
    "codes_in_journey", "succession_hops", "rewordings_passed", "journey",
    "terminal_code", "terminal_description", "terminal_first_period", "terminal_last_period",
    "terminal_status",
]


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def span_id_for(flow, code, first):
    """The name a commodity string is known by. The code and the month it first traded.

    IT DOES NOT CARRY THE LAST MONTH, and it did until 2026-08-15. A string still trading ends at
    the delivery's own last month, so 146 of 572 identifiers, 26 per cent, held `2026-06` and
    would every one of them have changed on the next delivery. That is the same defect as
    numbering records by position, reached by a different route, and it was caught while deciding
    against the counter rather than by anything here.

    First-traded month is fixed by the delivery and unique per code: verified over 475 import and
    97 export strings with no collision in either flow. `METHOD_family_id.md` settles the form,
    and the shuffle control in check_stage3_route.py proves this is a function of the string alone.
    """
    return "%s:%s:%s-%s" % (flow, dotted(code), first[:4], first[4:])


def link_id_for(flow, code, last_period):
    """Built exactly as Stage 2 builds it, so the two files join."""
    return "%s:%s:%s-%s" % (flow, dotted(code), last_period[:4], last_period[4:])


def stop(message, examples=()):
    print()
    print("Stage 3 STOPPED: %s" % message)
    for item in list(examples)[:8]:
        print("    %s" % (item,))
    raise SystemExit(1)


def receiving_span(spans, code, stopped):
    """The life of `code` that could have received trade leaving at `stopped`.

    The earliest life still open after the predecessor stopped. A code with two lives separated by
    a reuse gap must not offer its retired one. Reading the wrong life here would route a
    commodity into goods that had already gone.

    IT IS DELIBERATELY MORE PERMISSIVE THAN STAGE 1a's FUNCTION OF THE SAME NAME, and until
    2026-08-18 this docstring claimed they were the same rule. They are not. Stage 1a also
    requires the life to have BEGUN by the end of the continuity grace window, because it is
    assembling candidates and a life starting long after the boundary cannot have received the
    trade. This function is not assembling candidates. It is routing a successor a person already
    chose, and the analyst may knowingly accept a gap the heuristic would refuse.

    Measured: five settled links where the two rules pick differently, every one authority=analyst.
    Four are 3006.80.90.10/.20/.30/.43, where the analyst rejected the proposal and named
    3006.92.00.00 on the WCO 2002-to-2007 correlation, whose own note records that no candidate
    trades under that subheading; its life begins 2007-01, past the window. The fifth is
    exports:3003.40.00:2016-11 to 30034900, which begins 2018-05. Applying Stage 1a's bound here
    would silently discard five decisions the analyst made on the record's authority.
    """
    alive = [s for s in spans.get(code, []) if s["last_period"] > stopped]
    return min(alive, key=lambda s: s["first_period"]) if alive else None


def route(flow, inventory, resolved, delivery_end):
    """One row per commodity string. Nothing here chooses an edge; it reads which were chosen."""
    spans = defaultdict(list)
    for record in inventory:
        spans[record["hs_code"]].append(record)
    for lives in spans.values():
        lives.sort(key=lambda s: s["first_period"])
    position = {(s["hs_code"], s["first_period"]): i
                for lives in spans.values() for i, s in enumerate(lives)}

    rows, problems = [], {"unsettled": [], "stranded": [], "cycle": []}
    for start in inventory:
        here = start
        journey = [here["hs_code"]]
        successions = rewordings = 0
        seen = {(here["hs_code"], here["first_period"])}
        status = None
        while status is None:
            if here["last_period"] == delivery_end:
                status = ACTIVE
                break
            lives = spans[here["hs_code"]]
            index = position[(here["hs_code"], here["first_period"])]
            following = lives[index + 1] if index + 1 < len(lives) else None
            # The code carries on under new wording. Same commodity, same code, so the journey
            # gains nothing but the span pointer moves. The test is Stage 1a's own predicate,
            # called rather than restated: a short gap is not sufficient on its own, because a
            # relabel across a decisive distinction ends the span with no gap at all.
            if following is not None and continues_the_span(here, following):
                here, rewordings = following, rewordings + 1
                key = (here["hs_code"], here["first_period"])
                if key in seen:
                    problems["cycle"].append(
                        span_id_for(flow, start["hs_code"], start["first_period"]))
                    break
                seen.add(key)
                continue
            answer = resolved.get(link_id_for(flow, here["hs_code"], here["last_period"]))
            if answer is None or answer["outcome"] not in (
                    "succeeded", LEFT_CHAPTER, NOT_A_RETIREMENT):
                problems["unsettled"].append(
                    "%s -> %s" % (start["hs_code"],
                                  link_id_for(flow, here["hs_code"], here["last_period"])))
                break
            if answer["outcome"] != "succeeded":
                status = answer["outcome"]
                break
            successor = digits(answer["successor"])
            landing = receiving_span(spans, successor, here["last_period"])
            if landing is None:
                problems["stranded"].append("%s -> %s" % (answer["link_id"], answer["successor"]))
                break
            key = (landing["hs_code"], landing["first_period"])
            if key in seen:
                problems["cycle"].append(answer["link_id"])
                break
            seen.add(key)
            here, successions = landing, successions + 1
            journey.append(here["hs_code"])
        if status is None:
            continue
        rows.append({
            "span_id": span_id_for(flow, start["hs_code"], start["first_period"]),
            "flow": flow,
            "hs_code": dotted(start["hs_code"]),
            "description": start["description"],
            "first_period": start["first_period"],
            "last_period": start["last_period"],
            "value_cad": start["total_value_cad"],
            "codes_in_journey": len(journey),
            "succession_hops": successions,
            "rewordings_passed": rewordings,
            "journey": " -> ".join(dotted(c) for c in journey),
            "terminal_code": dotted(here["hs_code"]),
            "terminal_description": here["description"],
            "terminal_first_period": here["first_period"],
            "terminal_last_period": here["last_period"],
            "terminal_status": status,
        })
    return rows, problems


def describe(flow, rows):
    print("%s:" % flow)
    print("  commodity strings routed          : %d" % len(rows))
    print("  value carried by them             : CAD {:,.0f}".format(
        sum(float(r["value_cad"]) for r in rows)))
    print("  where the journeys end:")
    ends = Counter(r["terminal_status"] for r in rows)
    values = defaultdict(float)
    for r in rows:
        values[r["terminal_status"]] += float(r["value_cad"])
    for status in (ACTIVE, LEFT_CHAPTER, NOT_A_RETIREMENT):
        if ends.get(status):
            print("      %-18s %4d  CAD {:>18,.0f}".format(values[status])
                  % (status, ends[status]))
    print("  codes in a journey:")
    for n, count in sorted(Counter(int(r["codes_in_journey"]) for r in rows).items()):
        print("      %d code(s) %s %d" % (n, "." * (14 - len(str(n))), count))
    moved = [r for r in rows if int(r["succession_hops"])]
    print("  strings that moved at all         : %d of %d" % (len(moved), len(rows)))
    print("  re-wordings passed through        : %d, on codes that never changed"
          % sum(int(r["rewordings_passed"]) for r in rows))


def main():
    print("Stage 3: follow every commodity to the end of its chain. This stage decides nothing.")
    print()
    for flow in FLOWS:
        inventory_path = WORK_DIR / ("commodity_inventory_%s.csv" % flow)
        resolved_path = WORK_DIR / ("stage2_resolved_%s.csv" % flow)
        for path, owner in ((inventory_path, "s01_stage0_read_source.py"),
                            (resolved_path, "s06_stage2_apply_decisions.py")):
            if not path.exists():
                stop("%s not found. Run %s first." % (path, owner))
        inventory = load(inventory_path)
        resolved = {r["link_id"]: r for r in load(resolved_path)}
        delivery_end = max(r["last_period"] for r in inventory)

        rows, problems = route(flow, inventory, resolved, delivery_end)

        if problems["unsettled"]:
            stop("%d journey(s) reach a stoppage Stage 2 did not settle. A chain cannot be walked "
                 "through a row that is still open." % len(problems["unsettled"]),
                 problems["unsettled"])
        if problems["stranded"]:
            stop("%d succession(s) name a successor with no life open after the predecessor "
                 "stopped, so the trade had nowhere to land." % len(problems["stranded"]),
                 problems["stranded"])
        if problems["cycle"]:
            stop("%d journey(s) return to a code they already passed through. A cycle has no "
                 "terminus and no family." % len(problems["cycle"]), problems["cycle"])
        if len(rows) != len(inventory):
            stop("%d commodity string(s) in, %d out. Nothing may be lost or invented here."
                 % (len(inventory), len(rows)))
        expected = sum(float(r["total_value_cad"]) for r in inventory)
        got = sum(float(r["value_cad"]) for r in rows)
        if abs(expected - got) > 0.005:
            stop("value does not reconcile: CAD %.2f in, CAD %.2f out" % (expected, got))

        describe(flow, rows)
        destination = WORK_DIR / ("stage3_routed_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()

    print("Stage 3 complete. Every commodity string carries the whole path it travelled.")


if __name__ == "__main__":
    main()
