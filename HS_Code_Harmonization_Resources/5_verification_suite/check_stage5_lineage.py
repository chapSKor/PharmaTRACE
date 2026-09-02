"""
Check for Stage 5. Do the steps say exactly what Stage 3 walked, and nothing more?


Inputs:
    work/stage5_lineage_{imports,exports}.csv      produced by pipeline/stage5_lineage.py
    work/stage3_routed_{imports,exports}.csv       produced by pipeline/stage3_route.py
    work/stage4_families_{imports,exports}.csv     produced by pipeline/stage4_build_families.py
    work/commodity_inventory_{imports,exports}.csv produced by pipeline/stage0_read_source.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Does folding the steps back up give exactly the journey Stage 3 wrote, for every commodity string?

Stage 5 walks the path a second time. That is deliberate, because a step needs the LIFE the trade
landed in and not only its code, and reading that back out of an arrow-joined string would mean
guessing. The cost of walking twice is that the two can disagree, so the controls below are almost
all one idea: rebuild Stage 3's answer from Stage 5's rows and require them identical.

It does NOT ask whether a step is the right step. Stage 2 settled that and Stage 3 composed it.


WHAT WOULD GO WRONG WITHOUT THIS
---------------------------------
Two files would describe one path and a reader would have no way to tell which was stale. That is
the shape of the Stage 1c defect where `review_flag` was overwritten after being used: the stage
was right, the file was ordered correctly, and the column was unusable to anything downstream
while thirteen controls passed.
"""

import csv
import os
import sys
from collections import Counter, defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage5_lineage as stage  # noqa: E402

FLOWS = ("imports", "exports")
WORK = os.path.join(PROJECT, "work")

# Measured 2026-08-16 on the first build and reconciled against Stage 3 before being pinned.
# 950 = 160 journeys of one code, 187 of two, 98 of three, 28 of four and 2 of five.
EXPECTED = {
    # steps 950 -> 951 and succeeded 475 -> 476 on 2026-08-16. Row 23 now accepts
    # 3004.20.00.64 rather than taking the second alternative 3004.20.00.69, and that route
    # carries one more code before it terminates. One journey grew by one step.
    # rewordings 209 -> 208 on 2026-08-17, matching Stage 3 exactly, which is what this pin is
    # for: the veterinary-to-human relabel on 3004.50.99.30 is a span boundary now and not a
    # re-wording the walk passes through. steps and succeeded do not move, because the step that
    # was a re-wording inside one journey has become the last step of one journey and the first
    # of another, and the two journeys already existed as two records.
    "imports": {"records": 475, "steps": 951, "succeeded": 476, "active": 453,
                "left_chapter": 8, "not_a_retirement": 14, "rewordings": 208},
    "exports": {"records": 97, "steps": 140, "succeeded": 43, "active": 86,
                "left_chapter": 2, "not_a_retirement": 9, "rewordings": 47},
}

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, "  -- " + detail if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


print("Check for Stage 5. Do the steps say exactly what Stage 3 walked?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")


def span(code, first, last, description="a commodity"):
    return {"hs_code": code, "first_period": first, "last_period": last,
            "total_value_cad": "1.00", "description": description}


_inv = [span("3002190000", "201701", "202112"), span("3002900090", "202201", "202606")]
_fam = [{"span_id": "imports:3002.19.00.00:2017-01", "record_id": "IMR-3002190000-201701",
         "family_id": "IM-3002190000"}]

# 1. Stage 3 says the journey went somewhere the walk cannot reach.
_routed = [{"span_id": "imports:3002.19.00.00:2017-01", "first_period": "201701",
            "journey": "3002.19.00.00 -> 3006.10.00.10", "codes_in_journey": "2",
            "terminal_status": "active"}]
_res = {}
_rows, _bad = stage.unfold("imports", _routed, _fam, _inv, _res, "202606")
record("a journey the walk cannot reproduce is refused", bool(_bad),
       "two stages disagreeing about one path is worse than either being wrong alone")

# 2. A routed string with no family behind it.
_routed_ok = [{"span_id": "imports:3002.19.00.00:2017-01", "first_period": "201701",
               "journey": "3002.19.00.00 -> 3002.90.00.90", "codes_in_journey": "2",
               "terminal_status": "active"}]
_res_ok = {"imports:3002.19.00.00:2021-12": {"link_id": "imports:3002.19.00.00:2021-12", "outcome": "succeeded", "successor": "3002.90.00.90"}}
_rows, _bad = stage.unfold("imports", _routed_ok, [], _inv, _res_ok, "202606")
record("a commodity string Stage 4 never named is refused", bool(_bad),
       "a step cannot carry a family identifier that was never assigned")

# 3. The converse, so the guards are not simply refusing everything.
_rows, _clean = stage.unfold("imports", _routed_ok, _fam, _inv, _res_ok, "202606")
record("a journey the walk does reproduce is unfolded without complaint",
       not _clean and len(_rows) == 2
       and [r["hs_code"] for r in _rows] == ["3002.19.00.00", "3002.90.00.90"]
       and _rows[0]["step_status"] == stage.SUCCEEDED and _rows[1]["step_status"] == "active"
       and _rows[0]["next_hs_code"] == "3002.90.00.90" and _rows[1]["next_hs_code"] == "",
       "two steps, the first pointing at the second and the second at nothing")

print()
print("Controls that MUST PASS (correct input must not be flagged):")

for flow in FLOWS:
    expect = EXPECTED[flow]
    steps = load(os.path.join(WORK, "stage5_lineage_%s.csv" % flow))
    routed = {r["span_id"]: r for r in load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))}
    families = load(os.path.join(WORK, "stage4_families_%s.csv" % flow))
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    by_record = {r["record_id"]: r for r in families}
    span_of = {r["record_id"]: r["span_id"] for r in families}

    record("%s: every commodity string is unfolded exactly once" % flow,
           len({r["record_id"] for r in steps}) == expect["records"] == len(families),
           "%d string(s), %d step(s)" % (len({r["record_id"] for r in steps}), len(steps)))
    record("%s: the step count is what Stage 3's own journey lengths imply" % flow,
           len(steps) == expect["steps"]
           and len(steps) == sum(int(r["codes_in_journey"]) for r in routed.values()),
           "%d step(s), rebuilt from Stage 3's codes_in_journey" % len(steps))
    # Finding 114. The last of the sixteen columns the corruption sweep could overwrite on every
    # row with the suite still green. It is a constant per file, which is why nothing noticed, and
    # a constant nothing asserts is a constant nothing keeps.
    record("%s: every row names the flow of the file it is written to" % flow,
           all(r["flow"] == flow for r in steps),
           "%d row(s) disagree" % sum(1 for r in steps if r["flow"] != flow))

    grouped = defaultdict(list)
    for r in steps:
        grouped[r["record_id"]].append(r)
    for group in grouped.values():
        group.sort(key=lambda r: int(r["step_number"]))

    # RULE 10. Fold the steps back into a journey and require Stage 3's string, character for
    # character. This is the control the whole stage rests on.
    rebuilt, broken_chain, wrong_end, bad_numbers = [], [], [], []
    for rid, group in grouped.items():
        journey = " -> ".join(r["hs_code"] for r in group)
        source = routed[span_of[rid]]
        if journey != source["journey"]:
            rebuilt.append("%s: %s against %s" % (rid, journey, source["journey"]))
        if [int(r["step_number"]) for r in group] != list(range(1, len(group) + 1)):
            bad_numbers.append(rid)
        if any(int(r["steps_in_journey"]) != len(group) for r in group):
            bad_numbers.append(rid)
        for a, b in zip(group, group[1:]):
            if a["next_hs_code"] != b["hs_code"] or a["step_status"] != stage.SUCCEEDED:
                broken_chain.append(rid)
        last = group[-1]
        if (last["next_hs_code"] or last["step_status"] != source["terminal_status"]
                or last["hs_code"] != source["terminal_code"]):
            wrong_end.append(rid)
    record("%s: folding the steps back up gives Stage 3's journey exactly" % flow, not rebuilt,
           "%d journey(s) rebuilt from their own steps" % len(grouped)
           if not rebuilt else "%d differ: %s" % (len(rebuilt), rebuilt[:2]))
    record("%s: step numbers run 1..n with no gap" % flow, not bad_numbers,
           "%d row(s) misnumbered" % len(set(bad_numbers)))
    record("%s: every step but the last points at the next one and is marked succeeded" % flow,
           not broken_chain, "%d chain break(s)" % len(set(broken_chain)))
    record("%s: the last step is Stage 3's terminal and points nowhere" % flow, not wrong_end,
           "%d journey(s) end where Stage 3 says they end" % len(grouped)
           if not wrong_end else "%d disagree: %s" % (len(wrong_end), wrong_end[:3]))

    by_status = Counter(r["step_status"] for r in steps)
    record("%s: the step outcomes are unchanged" % flow,
           all(by_status.get(k, 0) == expect[k] for k in
               ("succeeded", "active", "left_chapter", "not_a_retirement")),
           "%s" % dict(by_status))
    record("%s: the succeeded steps are exactly Stage 3's succession hops" % flow,
           by_status.get(stage.SUCCEEDED, 0)
           == sum(int(r["succession_hops"]) for r in routed.values()) == expect["succeeded"],
           "%d hop(s) on both sides" % by_status.get(stage.SUCCEEDED, 0))
    record("%s: the re-wordings crossed are exactly Stage 3's, and none became a step" % flow,
           sum(int(r["rewordings_within_step"]) for r in steps)
           == sum(int(r["rewordings_passed"]) for r in routed.values()) == expect["rewordings"],
           "%d crossed inside steps, adding no code to any journey"
           % sum(int(r["rewordings_within_step"]) for r in steps))

    # FINDING 97's DISCIPLINE. Every description shown is the delivery's own wording for that code
    # in a life it really held, never a tariff phrase and never another era's words.
    held = defaultdict(set)
    lives_by_code = defaultdict(list)
    for r in inventory:
        held[r["hs_code"]].add(r["description"])
        lives_by_code[r["hs_code"]].append(r)
    invented = [r["record_id"] for r in steps if r["description"] not in held[digits(r["hs_code"])]]
    record("%s: every step's wording is the delivery's own for that code" % flow, not invented,
           "%d step(s) checked against %d inventory description(s)" % (len(steps), len(inventory))
           if not invented else "%d invented: %s" % (len(invented), invented[:3]))

    # AND IT IS THE WORDING OF THE RIGHT LIFE, which the control above cannot tell. Membership in
    # the code's set of descriptions passes on ANY era's words, and a recycled number's two lives
    # are both "the delivery's own"; on 227 of 1,090 steps the code carries more than one. The
    # step publishes the wording at the END of its run, so that is what is rebuilt here. Also
    # rebuilt: step_first_period and step_last_period, which no control read at all. Finding 109.
    wrong_era, wrong_bounds = [], []
    for r in steps:
        code = digits(r["hs_code"])
        at_end = [x for x in lives_by_code[code] if x["last_period"] == r["step_last_period"]]
        if not at_end:
            wrong_bounds.append(r["record_id"])
            continue
        if r["description"] != at_end[0]["description"]:
            wrong_era.append(r["record_id"])
        starts = {x["first_period"] for x in lives_by_code[code]}
        if r["step_first_period"] not in starts:
            wrong_bounds.append(r["record_id"])
        elif r["step_first_period"] > r["step_last_period"]:
            wrong_bounds.append(r["record_id"])
    record("%s: every step's wording is the one in force where the step ends" % flow,
           not wrong_era,
           "%d step(s), including %d on codes carrying more than one life"
           % (len(steps), sum(1 for r in steps if len(lives_by_code[digits(r["hs_code"])]) > 1))
           if not wrong_era else "%d read another era: %s" % (len(wrong_era), wrong_era[:3]))
    record("%s: every step's months are real span bounds, and run forwards" % flow,
           not wrong_bounds,
           "%d step(s); both period columns rebuilt from the inventory" % len(steps)
           if not wrong_bounds else "%d wrong: %s" % (len(wrong_bounds), wrong_bounds[:3]))

    wrong_family = [r["record_id"] for r in steps
                    if r["family_id"] != by_record[r["record_id"]]["family_id"]]
    record("%s: every step carries the family Stage 4 assigned" % flow, not wrong_family,
           "%d step(s) agree with stage4_families_%s.csv" % (len(steps), flow))

# THE WORDING A STEP SHOWS MUST BELONG TO THE PERIOD THE STEP CLAIMS. Finding 123, 2026-08-18.
#
# A step spans months and Statistics Canada rewords a line in place, so a step legitimately
# absorbs re-wordings and shows one of them: 226 steps carry a wording that was not in force on
# their own first month, and almost all are cosmetic, "Antisera & o blood fractions" against
# "Antisera and other blood fractions". That is not the defect.
#
# The defect is a step whose shown wording crosses a DECISIVE distinction from the one in force
# when the step began. IM_0166 was exactly that and it is why the end-of-pipeline meaning audit
# could not see it. That audit compares consecutive steps' shown wordings; IM_0166 lived INSIDE
# step 1, stamped 1988-01..1997-12 and showing "Multivitamins ... for human use" when the wording
# in force at 1988-01 was "Vitamins & their derivs,nes,for vet use". Comparing step 1 with step 2
# compares two human wordings and sees nothing, and so does comparing the journey's endpoints.
# The evidence was erased from the artefact before the audit read it.
#
# Proven to fail: 1 hit on output/imports_lineage_timeline.csv at commit 4b663d4~1, naming
# IMR-3004509930-198801 step 1 and the `use` rule. 0 on this build.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import meaning_gates as _mg  # noqa: E402
from _shorthand import expand_shorthand as _ex  # noqa: E402
_DISQ = [r for r in _mg.load_rules(os.path.join(PROJECT, "decisions", "decisive_distinctions.csv"))
         if str(r.get("action", "")).strip() == "disqualify"]
for flow in ("imports", "exports"):
    _inv = {}
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        _inv.setdefault(r["hs_code"], []).append(r)
    _wrong = []
    for step in load(os.path.join(PROJECT, "output", "%s_lineage_timeline.csv" % flow)):
        _code = step["hs_code"].replace(".", "")
        _first = (step["step_first_period"] or "").replace("-", "")
        _then = [r["description"] for r in _inv.get(_code, [])
                 if r["first_period"] <= _first <= r["last_period"]]
        if not _first or not _then or step["description"] in _then:
            continue
        if any(_mg.rule_fires(rule, _ex(_then[0]).lower(), _ex(step["description"]).lower())
               for rule in _DISQ):
            _wrong.append("%s step %s" % (step["uid"], step["step_number"]))
    record("%s: no step shows a wording that contradicts the one in force when it began" % flow,
           not _wrong,
           "re-wordings inside a step are allowed; crossing a decisive distinction is not"
           if not _wrong else "%d step(s) do: %s" % (len(_wrong), _wrong[:4]))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if failed:
    print()
    print("Stage 5 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 5 is validated. The steps and the journeys are one answer, not two.")
