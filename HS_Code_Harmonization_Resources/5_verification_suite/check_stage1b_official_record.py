"""
Check for Stage 1b. Did the official record speak in order, and only within its authority?


Inputs:
    work/stage1_official_{imports,exports}.csv      produced by pipeline/stage1b_official_record.py
    work/stage1_candidates_{imports,exports}.csv    produced by pipeline/stage1_candidates.py
    work/commodity_inventory_{imports,exports}.csv  produced by pipeline/stage0_read_source.py
    evidence/cbsa/concordance_*.csv and sched_ch30_<year>.csv

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE THREE QUESTIONS THIS CHECK ANSWERS
---------------------------------------
Did every retirement get an answer, exactly once? Did the layers run in the stated order, so
that nothing weaker overruled something stronger? And did each layer stay inside what it can
actually support?

The third is the one this stage got wrong twice before this check existed, both times by
claiming more than the evidence allowed.


THE SIX-DIGIT RULE IS PINNED WITH ITS MEASUREMENT ATTACHED
------------------------------------------------------------
The tariff schedule and the trade data are two different numbering systems below six digits.
The tariff lists tariff items; Statistics Canada adds statistical breakouts beneath them.
Export code 30029020, Saxitoxin, appears in no schedule because the tariff enumerates only
30029000, not because the goods did not exist.

Matching at full length was tried and abandoned. Across every retirement in both flows, 83 import
candidates on 36 retirements and 22 export candidates on 12 match at six digits and not at full
length, every one of them for a bookkeeping reason rather than a factual one. Those numbers are
asserted below, so anyone restoring full-length matching sees the measurement in the same run.

WHAT THAT MEASUREMENT IS AND IS NOT, corrected 2026-08-16. It describes the structure of the two
numbering systems. It is NOT the price of the rule, and it was read as the price until finding 112.
The schedules are consulted last, and resolve() returns at the first layer that answers, so a
retirement the concordance or the correlation tables already decided never reaches them. Of the 83
import candidates, the schedule reads none: 75 sit on rows the concordance decided and 8 on rows
the correlation tables decided. The price actually payable is 5 candidates on 3 export retirements,
plus one export row that would lose every candidate and so be diverted to a ruling rather than
narrowed. Both figures are pinned separately below, because a defence of a rule should quote what
the rule costs and not what its subject looks like.

That error class is the worst this design can produce. Layers below the record can only narrow
further, so a candidate wrongly removed here can never be recovered.
"""

import csv
import os
import re
import sys
from collections import defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(PROJECT, "work")
CBSA = os.path.join(PROJECT, "evidence", "cbsa")

LAYERS = {"cbsa_concordance", "constraint_set", "tariff_schedule", "none",
          # Layer 2, live since 2026-08-14. Deliberately NOT a naming layer below: the tables map
          # HS6 to HS6, so it removes candidates and reports a departure, and never names the
          # ten-digit destination that `constrained` would put in official_destinations.
          "wco_correlation"}
OUTCOMES = {"decided", "constrained", "bounded_needs_ruling", "narrowed", "forced",
            "silent_no_effect", "silent_no_source", "all_candidates_absent",
            # Added 2026-08-14 when Layer 2 stopped being empty. Neither settles: the first says
            # the record sent the goods out of Chapter 30, so a person must still record `none`,
            # and the second says the record names a subheading no candidate trades under, which
            # is the record disagreeing with the candidate field rather than narrowing it.
            "correlated_left_chapter", "correlated_no_candidate"}
# A bounded set can shrink to one destination once the retired code is removed from its own set.
# That is not a decision, because the row that produces it carries a required ruling.
SETTLING_OUTCOMES = {"decided", "constrained", "bounded_needs_ruling"}
# Only the two layers that NAME destinations may settle or bound an answer. The schedule can
# only remove, and silence can do neither.
NAMING_LAYERS = {"cbsa_concordance", "constraint_set"}

EXPECTED = {
    # A code whose number was reused retires more than once, so the key is the code AND the
    # month its span ended. Two export codes appear twice for that reason.
    # These went stale for one afternoon on 2026-08-11, while continuity was briefly a filter in
    # Stage 1a. Moving it to a veto in Stage 1c restored every one of them exactly, which is the
    # cleanest evidence that the move changed where the reasoning lives and not what it decides.
    # Re-measured 2026-08-11: decided 81 -> 89 and silent_no_effect 36 -> 28, the same eight
    # rows. The concordance is now matched on the year it calls a code obsolete rather than on
    # the month trade stopped under it. Money stops before a classification does, so eight codes
    # that went quiet one to four months before a revision were missing the lookup entirely while
    # Canada's own concordance named their successor. Nothing else in the split moved.
    # full_length_would_exclude RE-MEASURED 2026-08-14, imports 109 -> 83 across 36 -> 30 rows.
    # Not a change in what the six-digit rule costs, but in how the price is computed. Both sides
    # of the comparison now read every vintage in the transfer window, where before both read the
    # boundary year alone. Widening only the six-digit side would have priced the window instead
    # of the matching depth and reported 31 across 13 on exports; widening both leaves exports at
    # 22 across 12, unmoved, and drops imports because a ten-digit code absent from the boundary
    # year's tariff is often present in the next one. The decision the number defends is
    # unchanged: full-length matching still wrongly excludes 83 import candidates.
    # RE-MEASURED 2026-08-14, when Layer 2 stopped being empty. Fifteen import rows leave
    # silent_no_effect, 28 to 13, and land where the correlation put them: narrowed 4 to 6,
    # forced 0 to 4, correlated_left_chapter 0 to 3, correlated_no_candidate 0 to 6. That is
    # 2 + 4 + 3 + 6 = 15 and the total holds at 279. decided, constrained and silent_no_source
    # are untouched, which is the proof that the new layer took nothing from the layer above it:
    # it only spoke where the schedule had been the last word.
    # RE-MEASURED 2026-08-17, one row, one outcome. Stage 1a now ends a span where a relabel
    # crosses a decisive distinction, so imports 3004.50.99.30 retires twice and the total moves
    # 279 -> 280. The new row lands in silent_no_source, 150 -> 151, which is the right place and
    # is the point: no CBSA concordance and no WCO table reaches the 1990-01 boundary, so the
    # record says nothing about it. Every other outcome is untouched, which is what shows the
    # extra retirement took nothing from any layer that had already spoken.
    "imports": {"total": 280, "outcomes": {"decided": 89, "constrained": 8, "narrowed": 6,
                                           "forced": 4, "correlated_left_chapter": 3,
                                           "correlated_no_candidate": 6,
                                           "silent_no_effect": 13, "silent_no_source": 151},
                # wco_reach 20 -> 27 on 2026-08-19, finding 146: the boundary flag became a
                # union of the trading month and the declared termination, so seven declared
                # import spans that went quiet before their revision now sit at it.
                "wco_reach": 27, "full_length_would_exclude": 83, "full_length_rows": 30,
                # Measured 2026-08-16, findings 111 and 112. The schedule layer answers 13 import
                # retirements and removes a candidate on none of them, so both controls that guard
                # its narrowing have an empty subject and now say so. Attributing the 83 by the
                # layer that decided the row: cbsa_concordance 75 across 26, wco_correlation 8
                # across 4, tariff_schedule 0 across 0. Nothing is payable on imports.
                "schedule_removals": 0, "schedule_narrowings": 0,
                "full_length_payable": (0, 0, 0)},
    # RE-MEASURED 2026-08-14, exports only, when the schedule layer stopped reading the vintage
    # of the boundary's own year. narrowed 2 -> 1 and silent_no_effect 13 -> 14, one row moving
    # between them: 30021100, Malaria diagnostic test kits, quiet from 2021-11 and stated
    # terminated at 2021-12. Its boundary is 2021-12, so the 2021 schedule was read, and the five
    # HS2022 lines created the following January -- 30024100, 30024200, 30024900, 30025100 and
    # 30025900 -- were absent from it and removed as though withdrawn. The layer now reads every
    # vintage across the transfer window and the union holds all fourteen candidates, so it
    # excludes none and says so. Imports are untouched to the unit: 0 survivor sets moved there
    # and 10 rows changed only the year named in their note. No candidate anywhere was newly
    # removed, which the union guarantees by construction and a control asserts by measurement.
    # Exports the same day: five rows leave silent_no_effect, 14 to 9, and the single narrowed
    # row goes with them, producing 4 forced and 2 correlated_left_chapter. -1 + 4 + 2 - 5 = 0
    # and the total holds at 40. constrained, bounded_needs_ruling and silent_no_source untouched.
    "exports": {"total": 40, "outcomes": {"constrained": 3, "bounded_needs_ruling": 1,
                                          "forced": 4, "correlated_left_chapter": 2,
                                          "silent_no_effect": 9,
                                          "silent_no_source": 21},
                # wco_reach 8 -> 13 on 2026-08-19, finding 146, the same union: five declared
                # export spans join the boundary the record retired them at.
                "wco_reach": 13, "full_length_would_exclude": 22, "full_length_rows": 12,
                # Measured 2026-08-16 alongside imports. The schedule answers 9 export retirements
                # and removes nothing on any of them, so both subjects are empty here too. Of the
                # 22, only 7 across 4 rows sit on rows the schedule decides: constraint_set holds
                # 6 across 3 and wco_correlation 9 across 5. One of those 4, 30029020 retiring
                # 2016-11, would lose BOTH its candidates, and that is all_candidates_absent,
                # which returns the field intact for a ruling rather than excluding anything. So
                # the price actually payable across both flows is 5 candidates on 3 export rows
                # plus 1 row diverted, against the 105 across 42 the docstring advertised.
                "schedule_removals": 0, "schedule_narrowings": 0,
                "full_length_payable": (5, 3, 1)},
}

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


empty_subjects = []


def record_over(name, passed, subject, expected_subject, detail=""):
    """Record a control together with the size of the set it actually examined.

    Convention 5, applied inside a check rather than to a whole check. Two of the controls below
    guard the tariff-schedule layer's narrowing, and that layer narrows nothing in this delivery:
    it answers 13 import and 9 export retirements and every one of them is silent_no_effect. Both
    controls therefore ran to completion over an empty set and printed the same clean line they
    would print over a hundred real narrowings. A reader counting green lines could not tell the
    two apart, which is exactly the reading convention 5 forbids.

    Two things change here. The line prints EMPTY rather than PASS when nothing was examined, so
    the distinction is visible. And the subject SIZE is pinned like every other figure in this
    file, so the day the schedule starts narrowing, this check fails until someone looks at the
    rows it has started to examine and re-pins the count deliberately. An empty subject that is
    pinned at zero cannot drift into a silent pass.
    """
    if subject != expected_subject:
        record(name, False, "examined %d row(s), %d pinned. Re-read them before re-pinning."
                            % (subject, expected_subject))
        return
    if subject == 0:
        empty_subjects.append(name)
        results.append((name, True, detail))
        print("  [EMPTY] %s  -- examined 0 rows, pinned at 0%s"
              % (name, ("; " + detail) if detail else ""))
        return
    record(name, passed, "%d row(s) examined%s" % (subject, ("; " + detail) if detail else ""))


def must_raise(name, function, *args):
    try:
        function(*args)
    except ValueError as error:
        record(name, True, "refused as intended: %s" % error)
        return
    record(name, False, "accepted input it should have refused")


def validate(row):
    """The contract every answer must satisfy. Provoked below before it is trusted."""
    layer, outcome = row["deciding_layer"], row["outcome"]
    before, after = int(row["candidates_before"]), int(row["n_after"])
    named = [d for d in row["official_destinations"].split(";") if d]
    if layer not in LAYERS:
        raise ValueError("unknown layer %r" % layer)
    if outcome not in OUTCOMES:
        raise ValueError("unknown outcome %r" % outcome)
    if outcome in SETTLING_OUTCOMES and layer not in NAMING_LAYERS:
        raise ValueError("%s claims to have %s, but only a naming layer can" % (layer, outcome))
    if outcome == "bounded_needs_ruling" and layer != "constraint_set":
        raise ValueError("%s claims a bounded set needing a ruling, which only the sets carry" % layer)
    if outcome == "bounded_needs_ruling" and not named:
        raise ValueError("a bounded answer needing a ruling names nothing at all")
    if outcome == "decided" and len(named) != 1:
        raise ValueError("a decided answer names %d destinations, not one" % len(named))
    if outcome == "constrained" and len(named) < 2:
        raise ValueError("a constrained answer names %d destinations, so it is not bounded" % len(named))
    if layer == "tariff_schedule" and named:
        raise ValueError("the schedule named %d destinations, which it cannot do" % len(named))
    if after > before and layer == "tariff_schedule":
        raise ValueError("the schedule widened the field from %d to %d" % (before, after))
    if after == 0:
        raise ValueError("no candidate survives, which leaves nothing for the later stages")
    return True


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return re.sub(r"\D", "", text or "")


print("Check for Stage 1b. Did the official record speak in order, and within its authority?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
GOOD = {"deciding_layer": "cbsa_concordance", "outcome": "decided",
        "official_destinations": "3002120011", "candidates_before": "5", "n_after": "1"}


def variant(**changes):
    row = dict(GOOD)
    row.update(changes)
    return row


must_raise("an unknown layer is refused", validate, variant(deciding_layer="guesswork"))
must_raise("an unknown outcome is refused", validate, variant(outcome="probably"))
must_raise("the schedule claiming to decide is refused", validate,
           variant(deciding_layer="tariff_schedule", official_destinations=""))
must_raise("a decided answer naming two destinations is refused", validate,
           variant(official_destinations="3002120011;3002120012"))
must_raise("a constrained answer naming one destination is refused", validate,
           variant(outcome="constrained"))
must_raise("the schedule naming a destination is refused", validate,
           variant(deciding_layer="tariff_schedule", outcome="narrowed", n_after="3"))
must_raise("the schedule widening the field is refused", validate,
           variant(deciding_layer="tariff_schedule", outcome="narrowed",
                   official_destinations="", n_after="9"))
must_raise("an answer leaving no candidate at all is refused", validate, variant(n_after="0"))

print()
print("Controls that MUST PASS (correct input must not be flagged):")
record("a well-formed decided answer is accepted", validate(GOOD) is True, "one destination named")
record("a well-formed narrowing is accepted",
       validate(variant(deciding_layer="tariff_schedule", outcome="narrowed",
                        official_destinations="", n_after="3")) is True,
       "schedule removed candidates and named none")

# Independent view of the schedules, rebuilt here rather than imported.
sched_subs, sched_full, vintages = {}, {}, {}
for path in sorted(os.listdir(CBSA)):
    match = re.match(r"sched_ch30_(\d{4})(?:-(\d+))?\.csv$", path)
    if not match:
        continue
    year, amendment = int(match.group(1)), int(match.group(2) or 0)
    vintages.setdefault(year, []).append((amendment, path))
for year, options in vintages.items():
    amendment, path = max(options)
    rows = load(os.path.join(CBSA, path))
    subs, full = set(), set()
    for r in rows:
        for value in (digits(r.get("hs10") or ""), digits(r.get("tariff_item8") or "")):
            if len(value) >= 6:
                subs.add(value[:6])
            if len(value) >= 8:
                full.add(value)
    sched_subs[year], sched_full[year] = subs, full

for flow in ("imports", "exports"):
    print()
    print("%s:" % flow)
    expect = EXPECTED[flow]
    official = load(os.path.join(WORK, "stage1_official_%s.csv" % flow))
    # Keyed on code AND span end. Keying on the code alone silently collapsed the two export
    # codes that retired twice, and reported 38 retirements where the stage produced 40.
    worklist = {(r["retiring_code"], r["last_period"]): r
                for r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow))}
    inventory = {r["hs_code"] for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))}

    record("%s: every retirement has exactly one answer" % flow,
           {(r["retiring_code"], r["last_period"]) for r in official} == set(worklist)
           and len(official) == len(worklist),
           "%d answers for %d retirements" % (len(official), len(worklist)))
    record("%s: the answer count is unchanged" % flow, len(official) == expect["total"],
           "%d, expected %d" % (len(official), expect["total"]))

    # Every violation is collected. Stopping at the first one hides the scale, and the scale is
    # what decides whether a defect is a single bad row or a broken rule.
    broken = []
    for r in official:
        try:
            validate(r)
        except ValueError as error:
            broken.append("%s: %s" % (r["retiring_code"], error))
    record("%s: every answer satisfies the contract" % flow, not broken,
           "%d answer(s) checked" % len(official) if not broken
           else "%d of %d failed. First: %s" % (len(broken), len(official), broken[0]))

    counts = defaultdict(int)
    for r in official:
        counts[r["outcome"]] += 1
    record("%s: the outcome split is unchanged" % flow, dict(counts) == expect["outcomes"],
           "%s" % dict(counts))

    # The order. A weaker layer must never answer where a stronger one had something to say.
    # KEYED ON THE YEAR, AS THE STAGE IS, and it was keyed on the exact month until 2026-08-16.
    # The 2026-08-11 correction moved the stage from "the month trade stopped" to "the year the
    # concordance calls the code obsolete", because money stops before a classification does. The
    # correction was made in the stage and not in its guard, so the 8 rows it recovered --
    # CAD 167,730,730, retirements whose last trade was not exactly 2011-12 or 2016-12 -- sat
    # OUTSIDE the subject of the only control asserting that nothing overrules Canada's own
    # concordance. A control that cannot see the rows a fix was made for is not guarding the fix.
    named_codes = set()
    for filename, source_col, month in (("concordance_2011_2012_ch30.csv", "obsolete_2011", "201112"),
                                        ("concordance_2016_2017_ch30.csv", "obsolete_2016", "201612")):
        for r in load(os.path.join(CBSA, filename)):
            named_codes.add((month[:4], digits(r[source_col])))
    in_subject = [r for r in official
                  if (r["last_period"][:4], r["retiring_code"]) in named_codes]
    overruled = [r["retiring_code"] for r in in_subject
                 if r["deciding_layer"] != "cbsa_concordance"]
    record("%s: nothing overrules the ten-digit concordance" % flow, not overruled,
           "0 overruled, across %d retirement(s) the concordance names" % len(in_subject)
           if not overruled else "overruled: %s" % overruled[:5])

    bounded = {r["source_code"] for r in load(os.path.join(PROJECT, "decisions",
                                                           "official_constraint_sets.csv"))}
    skipped = [r["retiring_code"] for r in official
               if r["retiring_code"] in bounded and flow == "exports"
               and r["deciding_layer"] not in ("cbsa_concordance", "constraint_set")]
    record("%s: nothing overrules a bounded official set" % flow, not skipped,
           "0 skipped" if not skipped else "skipped: %s" % skipped[:5])

    record("%s: only a naming layer ever decides or bounds" % flow,
           all(r["deciding_layer"] in NAMING_LAYERS
               for r in official if r["outcome"] in SETTLING_OUTCOMES),
           "checked %d settled answer(s)"
           % sum(1 for r in official if r["outcome"] in SETTLING_OUTCOMES))

    # Everything the record names must be a code that really traded.
    unreal = []
    for r in official:
        for dest in r["official_destinations"].split(";"):
            if dest and dest not in inventory and dest != "30034300":
                unreal.append((r["retiring_code"], dest))
    record("%s: every named destination traded, or is the one declared exception" % flow,
           not unreal, "0 unreal" if not unreal else "unreal: %s" % unreal[:5])

    # A layer may narrow. It may never widen.
    widened = [r["retiring_code"] for r in official
               if r["deciding_layer"] == "tariff_schedule"
               and int(r["n_after"]) > int(r["candidates_before"])]
    record("%s: the schedule never widens the field" % flow, not widened,
           "0 widened" if not widened else "widened: %s" % widened[:5])

    # The stated termination, read straight from the inventory. The window below needs it and
    # the stage must not be asked for it.
    stated_end = {}
    for r in load(os.path.join(PROJECT, "work", "commodity_inventory_%s.csv" % flow)):
        value = (r.get("stated_termination") or "").strip()
        if value:
            stated_end[(r["hs_code"], r["last_period"])] = value

    def vintages_for(row):
        """Every tariff year in force from the boundary to the month after the record's end.

        Written out here rather than imported, per rule 2. The base year gates the whole layer,
        exactly as the stage does, so a row with no schedule at its boundary gets none here
        either and the two agree about silence as well as about content.
        """
        end = stated_end.get((row["retiring_code"], row["last_period"]), "")
        if not end or end < row["last_period"]:
            end = row["last_period"]
        low = int(row["boundary"][:4])
        after = "%04d%02d" % (int(end[:4]) + 1, 1) if end[4:] == "12" else end
        return [y for y in range(low, max(low, int(after[:4])) + 1) if y in sched_subs]

    # THE SCHEDULE MAY ONLY RULE OUT A CANDIDATE THAT EXISTED AT NO POINT IN THE WINDOW.
    #
    # Recomputed from the schedule files and the inventory, sharing no code with the stage. The
    # layer used to read the vintage of the boundary's own year, so a code quiet in November of a
    # revision year was tested against the PRE-revision schedule and the lines that revision
    # created the following January were removed as though they had been withdrawn. exports
    # 30021100 lost five HS2022 successors that way, and the note it wrote said they sat in a
    # subheading the schedule "no longer holds" when the schedule did not hold them YET.
    #
    # What this control cannot do, per rule 8: it asserts that nothing present in the window was
    # removed. It cannot say whether a candidate absent from every vintage is genuinely the wrong
    # answer, because the schedule is silent about statistical breakouts below six digits.
    # THE SUBJECT IS THE REMOVALS, NOT THE ROWS. This iterated 13 import and 9 export rows and
    # looked like a control with a subject, but its violation predicate reads `c not in kept`, and
    # the schedule keeps every candidate on every one of those rows. So it examined 22 rows and
    # 0 removals, and reported clean. `schedule_removals` is now counted and pinned. Finding 111.
    too_early, schedule_removals = [], 0
    for r in official:
        if r["deciding_layer"] != "tariff_schedule":
            continue
        years = vintages_for(r)
        if not years:
            continue
        present = set().union(*(sched_subs[y] for y in years))
        kept = {c for c in r["candidates_after"].split(";") if c}
        offered = [c for c in worklist[(r["retiring_code"],
                                       r["last_period"])]["candidates_narrowest"].split(";") if c]
        removed = [c for c in offered if c not in kept]
        schedule_removals += len(removed)
        too_early.extend((r["retiring_code"], c) for c in removed if c[:6] in present)
    record_over("%s: the schedule removed no candidate any vintage in the window holds" % flow,
                not too_early, schedule_removals, expect["schedule_removals"],
                "%d removed too early%s" % (len(too_early),
                                            (": " + ", ".join("%s lost %s" % t for t in too_early[:3]))
                                            if too_early else ""))

    # The six-digit rule, recomputed here and pinned with the cost of abandoning it.
    #
    # `payable` was added 2026-08-16. The two would_exclude figures below count every retirement
    # whose candidates match at six digits and not at full length, REGARDLESS of which layer
    # answered the row, and resolve() returns at the first layer that answers. On imports all 83
    # of them sit on rows the concordance (75) or the correlation tables (8) had already decided,
    # so the schedule never reads a single one and restoring full-length matching would exclude
    # nothing at all. The advertised price of the rule was therefore uncollectable on the flow
    # that carries most of the trade. Finding 112.
    mismatched, would_exclude, would_rows = [], 0, 0
    payable_candidates, payable_rows, diverted_rows = 0, 0, 0
    for r in official:
        year = int(r["boundary"][:4])
        cands = [c for c in worklist[(r["retiring_code"], r["last_period"])]["candidates_narrowest"].split(";") if c]
        if year not in sched_subs:
            continue
        # BOTH sides read the window, not the boundary year alone. Two reasons. This
        # recomputation would otherwise assert the very rule that was just corrected and would
        # fail the moment a narrowing spans a revision. And the figure is a comparison between
        # two matching depths, so letting one side see a vintage the other cannot would price
        # the window rather than the depth, which is not what the number is for.
        years = vintages_for(r)
        if not years:
            continue
        by_sub = [c for c in cands if c[:6] in set().union(*(sched_subs[y] for y in years))]
        by_full = [c for c in cands if any(c in sched_full[y] for y in years)]
        extra = [c for c in by_sub if c not in by_full]
        if extra:
            would_exclude += len(extra)
            would_rows += 1
            # What the change would actually cost, which is only what the schedule layer reads.
            # A row that loses EVERY candidate is not an exclusion: the stage returns
            # all_candidates_absent and hands back the field intact for a person to rule on.
            if r["deciding_layer"] == "tariff_schedule":
                if len(by_full) == 0:
                    diverted_rows += 1
                else:
                    payable_candidates += len(extra)
                    payable_rows += 1
        if r["deciding_layer"] == "tariff_schedule" and r["outcome"] in ("narrowed", "forced"):
            if sorted(c for c in r["candidates_after"].split(";") if c) != sorted(by_sub):
                mismatched.append(r["retiring_code"])
    narrowings = sum(1 for r in official if r["deciding_layer"] == "tariff_schedule"
                     and r["outcome"] in ("narrowed", "forced"))
    record_over("%s: every narrowing matches an independent six-digit recomputation" % flow,
                not mismatched, narrowings, expect["schedule_narrowings"],
                "0 mismatched" if not mismatched else "mismatched: %s" % mismatched[:5])
    record("%s: the cost of full-length matching is priced where it would be paid" % flow,
           (payable_candidates, payable_rows, diverted_rows) == tuple(expect["full_length_payable"]),
           "%d candidate(s) across %d row(s) excluded and %d row(s) diverted to a ruling, "
           "out of %d across %d measured" % (payable_candidates, payable_rows, diverted_rows,
                                             would_exclude, would_rows))
    record("%s: full-length matching would wrongly exclude the same count as measured" % flow,
           would_exclude == expect["full_length_would_exclude"]
           and would_rows == expect["full_length_rows"],
           "%d candidate(s) across %d retirement(s), expected %d across %d"
           % (would_exclude, would_rows, expect["full_length_would_exclude"], expect["full_length_rows"]))

    reach = sum(1 for r in official if r["at_hs_revision_boundary"] == "yes"
                and r["deciding_layer"] != "cbsa_concordance")
    record("%s: the reach of the empty correlation layer is unchanged" % flow,
           reach == expect["wco_reach"], "%d, expected %d" % (reach, expect["wco_reach"]))

print()
print("Probes: the empty-subject reporter itself, which is new and guards four green lines.")
# WRITTEN IN THE SAME SITTING AS record_over, per convention 11, and provoked because a reporter
# that cannot report a failure is worse than the silent PASS it replaced: it would look like a
# correction while changing nothing. The three branches are the three ways a pinned subject moves.
_probe = []


def _capture(name, passed, detail=""):
    _probe.append((name, passed, detail))


_real_record, _real_results, _real_empty = record, results, empty_subjects
record, results, empty_subjects = _capture, [], []
record_over("probe subject grew", True, 3, 0)
record_over("probe subject shrank", True, 0, 3)
record_over("probe subject held and the control failed", False, 3, 3)
record_over("probe subject held and the control passed", True, 3, 3)
_probe_empty = list(empty_subjects)
record, results, empty_subjects = _real_record, _real_results, _real_empty
_by = {n: (p, d) for n, p, d in _probe}
record("probe: a pinned-at-0 subject that gains rows fails rather than reporting a clean result",
       not _by["probe subject grew"][0], _by["probe subject grew"][1])
record("probe: a subject that loses rows fails too, so a control cannot be quietly emptied",
       not _by["probe subject shrank"][0], _by["probe subject shrank"][1])
record("probe: a real subject still reports the control's own verdict, pass and fail alike",
       not _by["probe subject held and the control failed"][0]
       and _by["probe subject held and the control passed"][0],
       "failing verdict reported as FAIL, passing verdict as PASS, both over 3 rows")
record("probe: only the empty case is listed as EMPTY", _probe_empty == [],
       "no synthetic control reached the empty branch, because none was pinned at 0 and empty")

print()
print("Probes: outcomes this delivery never produces, exercised on input it does not contain.")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage1b_official_record as stage  # noqa: E402

# Two outcomes exist in the code and occur nowhere in the delivery. Both are reachable, so both
# are exercised on a synthetic row rather than left to run for the first time in production.
FAKE_SCHEDULES = {2018: {"300110", "300120"}}
def probe(candidates, classification_end="201712"):
    row = {"retiring_code": "3001100010", "boundary": "201801", "last_period": "201712",
           "flow": "imports", "candidates_narrowest": ";".join(candidates)}
    # {} for correlations: these probes exercise the schedule layer, and an empty
    # correlation map is the honest way to say the tables do not reach this synthetic row.
    return stage.resolve(row, {}, FAKE_SCHEDULES, {}, classification_end, {})

got = probe(["3001100090", "3009900000"])
record("probe: the schedule forces an answer when one candidate survives",
       got["outcome"] == "forced" and got["surviving"] == ["3001100090"],
       "%s -> %s, never reached by this delivery" % (got["outcome"], got["surviving"]))
got = probe(["3009900000", "3009910000"])
record("probe: the schedule reporting no surviving subheading asks for a ruling",
       got["outcome"] == "all_candidates_absent" and len(got["surviving"]) == 2,
       "%s, and the field is left intact rather than emptied" % got["outcome"])
got = probe(["3001100090", "3001200000"])
record("probe: a schedule holding every candidate excludes none",
       got["outcome"] == "silent_no_effect", got["outcome"])

# THE TRANSFER WINDOW, probed as a matched pair on the shape that used to be got wrong: a
# candidate that exists ONLY in the vintage after the boundary's own year. Exactly one row in
# the delivery has that shape, so the behaviour is pinned here rather than resting on it.
WINDOW_SCHEDULES = {2018: {"300110"}, 2019: {"300110", "300250"}}
WINDOW_ROW = {"retiring_code": "3001100010", "boundary": "201801", "last_period": "201712",
              "flow": "imports", "candidates_narrowest": "3001100090;3002500000"}
got = stage.resolve(WINDOW_ROW, {}, WINDOW_SCHEDULES, {}, "201812", {})
record("probe: a candidate created after the boundary survives the window",
       got["outcome"] == "silent_no_effect" and len(got["surviving"]) == 2,
       "%s: %s, so a line the next revision creates is not removed as though withdrawn"
       % (got["outcome"], got["surviving"]))
got = stage.resolve(WINDOW_ROW, {}, WINDOW_SCHEDULES, {}, "201712", {})
record("probe: with no window that same candidate is removed",
       got["outcome"] == "forced" and got["surviving"] == ["3001100090"],
       "%s: %s, which is precisely the defect the window corrects"
       % (got["outcome"], got["surviving"]))

print()
print("The tariff vintages, chosen rather than assumed:")
record("a year with several vintages resolves to the highest amendment",
       all(max(v)[0] == max(a for a, _ in v) for v in vintages.values()),
       "%d year(s), %d with more than one vintage"
       % (len(vintages), sum(1 for v in vintages.values() if len(v) > 1)))
record("the schedules begin in 2005 and none is read before then",
       min(vintages) == 2005, "earliest vintage %d" % min(vintages))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if empty_subjects:
    print()
    print("%d control(s) examined an empty set and are reported as EMPTY, not as passing. Their"
          % len(empty_subjects))
    print("subject sizes are pinned at 0, so this check fails the day any of them gains a row:")
    for name in empty_subjects:
        print("  - %s" % name)
if failed:
    print()
    print("Stage 1b is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 1b is validated. The record spoke in order, and no layer claimed more than it can.")
