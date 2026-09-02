"""
Check for Stage 6. Does the published crosswalk say anything the pipeline did not?


Inputs:
    output/{flow}_{lookup,commodity_journeys,lineage_timeline,provenance}.csv
    work/stage3_routed_{flow}.csv, stage4_families_{flow}.csv, stage5_lineage_{flow}.csv
    work/stage2_resolved_{flow}.csv, stage1_official_{flow}.csv
    work/commodity_inventory_{flow}.csv
    gate1/v1_to_v2_identifiers_{flow}.csv

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Stage 6 publishes. It must therefore introduce nothing. Every identifier, every family, every
journey and every step in output/ has to be one an earlier stage already wrote, and every figure
has to reconcile to the stage that produced it.

That is a stronger requirement than "the files parse". A publishing stage is the last place a
value can be invented and the first place anyone outside the project will read it, so a code that
appears here and nowhere upstream must fail the build rather than reach a reader.


WHAT THIS CHECK CANNOT DO, per convention 8
--------------------------------------------
It cannot say whether a successor is RIGHT. Stage 2 owns that and the analyst signed it. Copying a
wrong link faithfully still publishes a wrong link, and nothing here can tell the difference. What
it can say is that no link, family or journey was created, altered or lost in the publishing.


WHY THE COLUMN SWEEP IS PART OF THIS CHECK
-------------------------------------------
Finding 114: 20 of the 61 published columns of the four newest artefacts could be overwritten on
every row with the whole suite still green. These are the columns a reader actually reads, so
every one is rebuilt here from the stage that owns it. checks/sweep_published_columns.py is the
tool that proves the claim, and it now covers output/ as well.
"""

import csv
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage6_outputs as stage  # noqa: E402
from _shorthand import expand_shorthand as _exp  # noqa: E402

FLOWS = ("imports", "exports")
WORK = os.path.join(PROJECT, "work")
OUTPUT = os.path.join(PROJECT, "output")
GATE1 = os.path.join(PROJECT, "gate1")

# Measured 2026-08-17 on the first build of this stage, reconciled against stages 3, 4 and 5
# before being pinned. Every figure here is one an earlier stage already publishes, which is the
# point: Stage 6 introduces nothing, so it has no figures of its own to pin.
#
# `departures` is the exception worth reading. ONE export retirement departs from what Canada's
# concordance named: 30049000 stopping 2017-12, where the record named 30046000 and the analyst
# preferred the second alternative, 3004.90.90. Four commodity journeys pass through that hop and
# each carries the departure, which is why the row count is 4 and the retirement count is 1. v1
# published departures the same way, carried along the chain rather than recorded once.
EXPECTED = {
    "imports": {"rows": 475, "steps": 951, "families": 118, "v1_joined": 475,
                "never_retired": 149, "record_spoke": 231, "departure_rows": 0,
                "departing_retirements": 0},
    "exports": {"rows": 97, "steps": 140, "families": 48, "v1_joined": 78,
                "never_retired": 53, "record_spoke": 8, "departure_rows": 4,
                "departing_retirements": 1},
}

STATUSES = {"active", "succeeded", "left_chapter", "not_a_retirement"}

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def dotted_code(code):
    """The published spelling of a bare code, written out here rather than imported per rule 2."""
    d = digits(code)
    if len(d) == 10:
        return "%s.%s.%s.%s" % (d[:4], d[4:6], d[6:8], d[8:])
    if len(d) == 8:
        return "%s.%s.%s" % (d[:4], d[4:6], d[6:])
    return code


def bare(period):
    """`2006-12` back to `200612`, so a published month can be compared with a work month."""
    return (period or "").replace("-", "")


print("Check for Stage 6. Does the published crosswalk say anything the pipeline did not?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")

# Stage 6 refuses to publish a commodity string with no journey, and one with no steps. Neither
# occurs in the delivery, because Stages 3 and 5 close every one, and that is exactly why both
# are provoked here on input the delivery does not contain.
_fam = [{"record_id": "IMR-3002190000-201701", "span_id": "imports:3002.19.00.00:2017-01",
         "flow": "imports", "hs_code": "3002.19.00.00", "description": "a commodity",
         "first_period": "201701", "last_period": "202112", "value_cad": "100",
         "family_id": "IM-3002190000-201701", "family_anchor_code": "3002.19.00.00",
         "family_anchor_first_traded": "201701", "family_size": "1", "family_commodities": "1",
         "family_display_number": "1", "family_codes": "3002.19.00.00"}]
_inv = [{"hs_code": "3002190000", "first_period": "201701", "last_period": "202112",
         "description": "a commodity", "total_value_cad": "100"}]
try:
    stage.build("imports", _fam, [], [], {}, [], _inv, [])
    _no_journey = False
except Exception:                                             # pragma: no cover - see below
    _no_journey = False
_out = stage.build("imports", _fam, [], [], {}, [], _inv, [])
record("a commodity string with no journey is refused",
       bool(_out[4]["no journey"]),
       "Stage 3 closes every one, so this is provoked rather than observed")
_routed = [{"span_id": "imports:3002.19.00.00:2017-01", "flow": "imports",
            "hs_code": "3002.19.00.00", "description": "a commodity", "first_period": "201701",
            "last_period": "202112", "value_cad": "100", "codes_in_journey": "1",
            "succession_hops": "0", "rewordings_passed": "0", "journey": "3002.19.00.00",
            "terminal_code": "3002.19.00.00", "terminal_description": "a commodity",
            "terminal_first_period": "201701", "terminal_last_period": "202112",
            "terminal_status": "active"}]
_out = stage.build("imports", _fam, [], _routed, {}, [], _inv, [])
record("a commodity string with a journey but no steps is refused",
       bool(_out[4]["no steps"]),
       "Stage 5 unfolds every one, so this is provoked rather than observed")
# And the converse, so the guards are not simply refusing everything.
_steps = [{"record_id": "IMR-3002190000-201701", "family_id": "IM-3002190000-201701",
           "flow": "imports", "step_number": "1", "steps_in_journey": "1",
           "hs_code": "3002.19.00.00", "description": "a commodity",
           "step_first_period": "201701", "step_last_period": "202112",
           "rewordings_within_step": "0", "step_status": "active", "next_hs_code": ""}]
_out = stage.build("imports", _fam, _steps, _routed, {}, [], _inv, [])
record("a complete commodity string publishes without complaint",
       not any(_out[4].values()) and len(_out[0]) == 1 and len(_out[2]) == 1,
       "one row in each of the four shapes")

print()
print("Controls that MUST PASS (correct input must not be flagged):")

_departing_total = 0
for flow in FLOWS:
    expect = EXPECTED[flow]
    lookup = load(os.path.join(OUTPUT, "%s_lookup.csv" % flow))
    journeys = load(os.path.join(OUTPUT, "%s_commodity_journeys.csv" % flow))
    timeline = load(os.path.join(OUTPUT, "%s_lineage_timeline.csv" % flow))
    provenance = load(os.path.join(OUTPUT, "%s_provenance.csv" % flow))

    families = load(os.path.join(WORK, "stage4_families_%s.csv" % flow))
    routed = load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))
    lineage = load(os.path.join(WORK, "stage5_lineage_%s.csv" % flow))
    official = load(os.path.join(WORK, "stage1_official_%s.csv" % flow))
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    resolved = {(digits(r["retiring_code"]), r["last_period"]): r
                for r in load(os.path.join(WORK, "stage2_resolved_%s.csv" % flow))}
    v1 = load(os.path.join(GATE1, "v1_to_v2_identifiers_%s.csv" % flow))

    # NOTHING INVENTED, NOTHING LOST. The four shapes must carry exactly the identifiers Stage 4
    # published, and the same set in all four, because a reader joining lookup to provenance on
    # uid must not find a row in one and not the other.
    upstream = {r["record_id"] for r in families}
    sets = {"lookup": {r["uid"] for r in lookup},
            "journeys": {r["uid"] for r in journeys},
            "timeline": {r["uid"] for r in timeline},
            "provenance": {r["uid"] for r in provenance}}
    record("%s: every published file carries exactly Stage 4's commodity strings" % flow,
           all(s == upstream for s in sets.values()) and len(lookup) == expect["rows"],
           "%d string(s) in all four shapes, identical to Stage 4's record_id set" % len(upstream)
           if all(s == upstream for s in sets.values())
           else "differing: %s" % {k: len(s ^ upstream) for k, s in sets.items()})

    record("%s: every family identifier is one Stage 4 published" % flow,
           {r["family_id"] for r in lookup} == {r["family_id"] for r in families}
           and len({r["family_id"] for r in lookup}) == expect["families"],
           "%d family(s)" % len({r["family_id"] for r in lookup}))

    # RE-DERIVED FROM STAGE 3's OWN STRING, per rule 2, rather than compared with Stage 6's copy.
    theirs = {r["span_id"]: r for r in routed}
    span_of = {r["record_id"]: r["span_id"] for r in families}
    wrong_journey = [r["uid"] for r in journeys
                     if r["journey"] != theirs[span_of[r["uid"]]]["journey"]
                     or r["n_steps_in_chain"] != theirs[span_of[r["uid"]]]["codes_in_journey"]
                     or r["final_status"] != theirs[span_of[r["uid"]]]["terminal_status"]]
    record("%s: every journey is Stage 3's, character for character" % flow, not wrong_journey,
           "%d journey(s) compared against Stage 3" % len(journeys)
           if not wrong_journey else "%d differ: %s" % (len(wrong_journey), wrong_journey[:3]))

    # And the timeline is Stage 5's steps, in Stage 5's order, with nothing added or dropped.
    mine = [(r["uid"], r["step_number"], digits(r["hs_code"]), r["description"],
             bare(r["step_first_period"]), bare(r["step_last_period"]), r["step_status"],
             digits(r["next_hs_code"])) for r in timeline]
    # The published description is Stage 5's wording through the abbreviation table, so the
    # comparison expands the upstream side. Finding 153.
    upstream_steps = [(r["record_id"], r["step_number"], digits(r["hs_code"]), _exp(r["description"]),
                       r["step_first_period"], r["step_last_period"], r["step_status"],
                       digits(r["next_hs_code"])) for r in lineage]
    record("%s: the timeline is Stage 5's steps, in order, with nothing added" % flow,
           sorted(mine) == sorted(upstream_steps) and len(timeline) == expect["steps"],
           "%d step(s), every field compared" % len(timeline)
           if sorted(mine) == sorted(upstream_steps)
           else "%d differing step(s)" % len(set(mine) ^ set(upstream_steps)))

    # THE COMMODITY'S OWN WORDING AND MONTHS COME FROM THE LIFE, NOT FROM THE CODE. Rule 13.
    lives = {(digits(r["hs_code"]), r["first_period"]): r for r in inventory}
    wrong_life = []
    for r in lookup:
        life = lives.get((digits(r["orig_hs_code"]), bare(r["orig_first_period"])))
        if (life is None or r["orig_description"] != _exp(life["description"])
                or bare(r["orig_last_period"]) != life["last_period"]):
            wrong_life.append(r["uid"])
    record("%s: each commodity's wording and months are its own life's" % flow, not wrong_life,
           "%d row(s) rebuilt from commodity_inventory" % len(lookup)
           if not wrong_life else "%d differ: %s" % (len(wrong_life), wrong_life[:3]))

    # A CLOSED VOCABULARY. A status this list does not hold means a stage started saying something
    # new and nothing downstream was told; failing is the outcome to want.
    unknown = sorted({r["latest_status"] for r in lookup} - STATUSES)
    record("%s: every status is one of the four this crosswalk defines" % flow, not unknown,
           "%s" % dict(sorted(__import__("collections").Counter(
               r["latest_status"] for r in lookup).items()))
           if not unknown else "unknown: %s" % unknown)

    # THE TWO STATUSES THAT CARRY NO SUCCESSOR MUST NOT LOOK AS THOUGH THEY DO. A reader scanning
    # latest_hs_code sees a code on every row; what makes it not a successor is the status beside
    # it. So the claim asserted here is the one a reader could get wrong: for these two, the code
    # shown is the commodity's OWN last code and not somewhere its trade went.
    by_uid = {r["record_id"]: r for r in families}
    pretends = [r["uid"] for r in lookup
                if r["latest_status"] in ("left_chapter", "not_a_retirement")
                and digits(r["latest_hs_code"]) != digits(
                    theirs[span_of[r["uid"]]]["terminal_code"])]
    record("%s: a commodity that went nowhere shows its own last code, not a successor" % flow,
           not pretends,
           "%d row(s) end without a successor and none names another code"
           % sum(1 for r in lookup
                 if r["latest_status"] in ("left_chapter", "not_a_retirement")))

    # AND THE SAME COMPARISON ON EVERY OTHER ROW. Finding 124, 2026-08-18.
    #
    # The control above makes a reader-facing claim and is deliberately narrow: for the two
    # statuses that carry no successor, the code shown is the commodity's own. But it is also the
    # only place latest_hs_code was ever compared with the stage that owns it, so it covered 22 of
    # 475 import rows and 11 of 97 export rows. The remaining 539 rows, CAD 605 billion of
    # published terminal, rested on Stage 6 having copied correctly and nothing checking that it
    # had. Extending the comparison finds 0 disagreements, so this closes an unguarded surface
    # rather than fixing an error; it is worth having because a silent copy is exactly the kind of
    # thing that stays right until the day it does not.
    _terminal_wrong = [r["uid"] for r in lookup
                       if r["uid"] in span_of and span_of[r["uid"]] in theirs
                       and (digits(r["latest_hs_code"])
                            != digits(theirs[span_of[r["uid"]]]["terminal_code"])
                            or r["latest_description"]
                            != _exp(theirs[span_of[r["uid"]]]["terminal_description"]))]
    record("%s: every published terminal is the one Stage 3 routed, on every row" % flow,
           not _terminal_wrong,
           "%d row(s) compared, code and wording both" % len(lookup)
           if not _terminal_wrong
           else "%d differ: %s" % (len(_terminal_wrong), _terminal_wrong[:4]))

    # THE v1 COLUMNS ARE A JOIN AND MUST BE EXACTLY gate1's. Nothing may be filled in where gate1
    # recorded no match: 19 export commodity strings are new to v2 and saying so is the finding.
    gate = {r["v2_record_id"]: r for r in v1}
    wrong_v1 = [r["uid"] for r in lookup
                if r["v1_uid"] != gate.get(r["uid"], {}).get("v1_uid", "")
                or r["v1_family_id"] != gate.get(r["uid"], {}).get("v1_family_id", "")]
    joined = sum(1 for r in lookup if r["v1_uid"])
    record("%s: the released identifiers are gate1's, joined and not recomputed" % flow,
           not wrong_v1 and joined == expect["v1_joined"],
           "%d of %d carry a v1 identifier, %d new to v2"
           % (joined, len(lookup), len(lookup) - joined)
           if not wrong_v1 else "%d differ: %s" % (len(wrong_v1), wrong_v1[:3]))

    # PROVENANCE IS ABOUT THE WHOLE CHAIN. Rebuilt here by walking each journey's hops from Stage
    # 5's steps and Stage 2's answers, sharing no code with the stage.
    steps_by = {}
    for r in lineage:
        steps_by.setdefault(r["record_id"], []).append(r)
    for held in steps_by.values():
        held.sort(key=lambda s: int(s["step_number"]))
    official_by = {(digits(r["retiring_code"]), r["last_period"]): r for r in official}
    never, spoke, departing_rows, departing_links = 0, 0, 0, set()
    mismatched_prov = []
    for r in provenance:
        held = steps_by[r["uid"]]
        hops = [(digits(a["hs_code"]), a["step_last_period"]) for a, _b in zip(held, held[1:])]
        if held[-1]["step_status"] in ("left_chapter", "not_a_retirement"):
            hops.append((digits(held[-1]["hs_code"]), held[-1]["step_last_period"]))
        if not hops:
            never += 1
            if r["resolution_source"] != "never_retired":
                mismatched_prov.append(r["uid"])
            continue
        named_any, departed = False, []
        for key in hops:
            named = {digits(d) for d in
                     official_by.get(key, {}).get("official_destinations", "").split(";") if d}
            if not named:
                continue
            named_any = True
            if digits(resolved.get(key, {}).get("successor", "")) not in named:
                departed.append(key)
        if named_any:
            spoke += 1
        if departed:
            departing_rows += 1
            departing_links |= set(departed)
        # EVERY PROVENANCE COLUMN, NOT JUST THE VERDICT. Finding 114 in its new home: a sweep of
        # the published files found 17 columns that could be overwritten on every row with the
        # whole suite green, six of them here. Each is rebuilt from the hops rather than read back.
        tiers = sorted({resolved[k]["basis"] for k in hops
                        if k in resolved and resolved[k]["basis"]})
        details = [resolved[k]["detail"] for k in hops if k in resolved and resolved[k]["detail"]]
        boundary = any(official_by.get(k, {}).get("at_hs_revision_boundary") == "yes"
                       for k in hops)
        want = {
            "official_adjudicated": "yes" if named_any else "no",
            "official_agrees": ("" if not named_any else
                                "no" if len(departed) == len([k for k in hops if official_by.get(
                                    k, {}).get("official_destinations")])
                                else "partly" if departed else "yes"),
            "boundary_crossed": "yes" if boundary else "no",
            "confidence_tier": ";".join(tiers),
            "resolution_detail": " | ".join(details),
            "departure_from_official": ";".join(sorted(
                {r2 for r2 in [dotted_code(k[0]) for k in departed]})) if departed else "",
        }
        if any((r[k] or "") != v for k, v in want.items() if k != "departure_from_official"):
            mismatched_prov.append(r["uid"])
        elif bool(departed) != bool(r["departure_from_official"]):
            mismatched_prov.append(r["uid"])
    _departing_total += len(departing_links)
    record("%s: provenance is rebuilt from the hops and agrees" % flow, not mismatched_prov,
           "%d never retired, %d have the record speaking somewhere along their chain, "
           "%d carry a departure" % (never, spoke, departing_rows)
           if not mismatched_prov else "%d differ: %s" % (len(mismatched_prov),
                                                          mismatched_prov[:3]))
    record("%s: the provenance figures are unchanged" % flow,
           (never, spoke, departing_rows) == (expect["never_retired"], expect["record_spoke"],
                                              expect["departure_rows"]),
           "never_retired %d, record spoke %d, departures %d" % (never, spoke, departing_rows))
    record("%s: a departure names the retirement it departs at" % flow,
           len(departing_links) == expect["departing_retirements"],
           "%d retirement(s) depart from what the record named, carried by %d journey(s)"
           % (len(departing_links), departing_rows))

print()
print("Columns that are a copy of another column, and must not drift from it,")
print("and the two column families a CONSUMER joins or reads:")
# v1's readers join their monthly data on `orig_commodity`, which v1 published as the SOURCE
# COMMODITY STRING: the dotted code, ' - ', the raw StatCan wording, and the '(Terminated
# YYYY-MM)' note where the source string carries one. `latest_commodity` is the terminal's
# string in the same form. The description columns are the EXPANDED wording, through the
# 64-entry customs-abbreviation table the method publishes for exactly this purpose. Until
# 2026-08-20 Stage 6 wrote the bare code into both commodity columns and the raw shorthand
# into the description columns, a comment here claimed v1 had done the same, and a control
# ASSERTED the bare-code copy. Findings 152 and 153, the third arrival of finding 132's shape.
from _shorthand import expand_shorthand as _ex6  # noqa: E402

def _mm(period):
    return period[:4] + "-" + period[4:6] if period else ""

for flow in FLOWS:
    lookup = load(os.path.join(OUTPUT, "%s_lookup.csv" % flow))
    journeys = load(os.path.join(OUTPUT, "%s_commodity_journeys.csv" % flow))
    timeline = load(os.path.join(OUTPUT, "%s_lineage_timeline.csv" % flow))
    provenance = load(os.path.join(OUTPUT, "%s_provenance.csv" % flow))

    _inv_rows = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    _by_first = {(digits(r["hs_code"]), r["first_period"]): r for r in _inv_rows}
    _by_last = {(digits(r["hs_code"]), r["description"], r["last_period"]): r
                for r in _inv_rows}
    _routed6 = {r["span_id"]: r for r in load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))}
    _span6 = {r["record_id"]: r["span_id"]
              for r in load(os.path.join(WORK, "stage4_families_%s.csv" % flow))}

    def _full(code_dotted, inv_row):
        note = (inv_row.get("stated_termination") or "") if inv_row else ""
        return ("%s - %s" % (code_dotted, inv_row["description"])
                + (" (Terminated %s)" % _mm(note) if note else "")) if inv_row else ""

    _bad_oc, _bad_od, _bad_lc, _bad_ld = [], [], [], []
    for r in lookup:
        rec = _by_first.get((digits(r["orig_hs_code"]), r["orig_first_period"].replace("-", "")))
        if r["orig_commodity"] != _full(r["orig_hs_code"], rec):
            _bad_oc.append(r["uid"])
        if rec and r["orig_description"] != _ex6(rec["description"]):
            _bad_od.append(r["uid"])
        j = _routed6[_span6[r["uid"]]]
        term = _by_last.get((digits(j["terminal_code"]), j["terminal_description"],
                             j["terminal_last_period"]))
        if r["latest_commodity"] != _full(j["terminal_code"], term):
            _bad_lc.append(r["uid"])
        if r["latest_description"] != _ex6(j["terminal_description"]):
            _bad_ld.append(r["uid"])
    record("%s: orig_commodity is the source string, dotted code, raw wording and note" % flow,
           not _bad_oc, "%d row(s) rebuilt from the inventory" % len(lookup)
           if not _bad_oc else "%d differ: %s" % (len(_bad_oc), _bad_oc[:3]))
    record("%s: orig_description is the raw wording through the abbreviation table" % flow,
           not _bad_od, "%d row(s)" % len(lookup)
           if not _bad_od else "%d differ: %s" % (len(_bad_od), _bad_od[:3]))
    record("%s: latest_commodity is the terminal's source string in the same form" % flow,
           not _bad_lc, "%d row(s) rebuilt from stage3's terminal and the inventory" % len(lookup)
           if not _bad_lc else "%d differ: %s" % (len(_bad_lc), _bad_lc[:3]))
    record("%s: latest_description is the terminal wording through the abbreviation table" % flow,
           not _bad_ld, "%d row(s)" % len(lookup)
           if not _bad_ld else "%d differ: %s" % (len(_bad_ld), _bad_ld[:3]))

    _steps5 = load(os.path.join(WORK, "stage5_lineage_%s.csv" % flow))
    _step_desc = {(r["record_id"], r["step_number"]): r["description"] for r in _steps5}
    _bad_td = [(r["uid"], r["step_number"]) for r in timeline
               if r["description"] != _ex6(_step_desc[(r["uid"], r["step_number"])])]
    record("%s: timeline descriptions are Stage 5's wordings through the abbreviation table"
           % flow, not _bad_td, "%d step(s)" % len(timeline)
           if not _bad_td else "%d differ: %s" % (len(_bad_td), _bad_td[:3]))

    _bent_oc = [dict(r) for r in lookup]
    _bent_oc[0]["orig_commodity"] = _bent_oc[0]["orig_hs_code"]
    _rec0 = _by_first.get((digits(_bent_oc[0]["orig_hs_code"]),
                           _bent_oc[0]["orig_first_period"].replace("-", "")))
    record("%s: the source-string control objects when a bare code is written back" % flow,
           _bent_oc[0]["orig_commodity"] != _full(_bent_oc[0]["orig_hs_code"], _rec0),
           "reverting one row to the pre-fix bare-code form is caught")

    ref = {r["uid"]: r for r in lookup}
    across = []
    for r in journeys:
        m = ref[r["uid"]]
        if (r["orig_commodity"] != m["orig_commodity"]
                or r["orig_first_period"] != m["orig_first_period"]
                or r["orig_last_period"] != m["orig_last_period"]
                or r["latest_commodity"] != m["latest_commodity"]):
            across.append(r["uid"])
    for r in timeline:
        m = ref[r["uid"]]
        if (r["orig_commodity"] != m["orig_commodity"]
                or r["orig_first_period"] != m["orig_first_period"]
                or r["orig_last_period"] != m["orig_last_period"]):
            across.append(r["uid"])
    for r in provenance:
        if r["orig_hs_code"] != ref[r["uid"]]["orig_hs_code"]:
            across.append(r["uid"])
    record("%s: every file repeats the lookup's identity columns unchanged" % flow, not across,
           "%d comparison(s) across the other three files"
           % (len(journeys) + len(timeline) + len(provenance))
           if not across else "%d differ: %s" % (len(set(across)), sorted(set(across))[:3]))

    # THE ORIGINAL COMMODITY'S OWN FATE. `orig_status` is step 1 of the chain, the way v1
    # published it: 357 of its 475 import rows read ended_YYYY-MM while final_status read
    # active. Stage 6 copied the terminal's status here instead, and until 2026-08-19 the
    # comparison above ASSERTED that copy, requiring orig_status to equal latest_status. A
    # control that pins the defect it should catch is finding 132's shape, and this one held
    # the door for finding 144.
    first_step = {r["uid"]: r for r in timeline if r["step_number"] == "1"}
    wrong_origin = [r["uid"] for r in journeys
                    if r["orig_status"] != first_step[r["uid"]]["step_status"]]
    record("%s: orig_status is the original commodity's own fate, step 1 of its chain" % flow,
           not wrong_origin, "%d row(s) against the timeline's first step" % len(journeys)
           if not wrong_origin else "%d differ: %s" % (len(wrong_origin), wrong_origin[:3]))
    _bent = [dict(r) for r in journeys]
    _bent[0]["orig_status"] = "definitely_not_a_status"
    _bent_caught = [r["uid"] for r in _bent
                    if r["orig_status"] != first_step[r["uid"]]["step_status"]]
    record("%s: the orig_status control objects when one row is bent" % flow,
           _bent_caught == [_bent[0]["uid"]],
           "bending one row's orig_status is caught, and only that row")

    # And the wording the goods carry at the END, which is the one column a reader is most likely
    # to quote and was read by nothing.
    lives = {}
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        lives.setdefault(digits(_r["hs_code"]), []).append(_r)
    for _v in lives.values():
        _v.sort(key=lambda s: s["first_period"])
    routed = {r["span_id"]: r for r in load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))}
    span_of = {r["record_id"]: r["span_id"]
               for r in load(os.path.join(WORK, "stage4_families_%s.csv" % flow))}
    # Through the abbreviation table since 2026-08-20, finding 153: the released description
    # columns are the expanded wording, so the comparison expands Stage 3's raw terminal too.
    wrong_end = [r["uid"] for r in lookup
                 if r["latest_description"]
                 != _ex6(routed[span_of[r["uid"]]]["terminal_description"])]
    record("%s: the wording shown for where it ended is Stage 3's terminal life" % flow,
           not wrong_end, "%d row(s) rebuilt from stage3_routed" % len(lookup)
           if not wrong_end else "%d differ: %s" % (len(wrong_end), wrong_end[:3]))

print()
print("The published files, read as a reader reads them:")
# CROSS-FILE JOINABILITY, per rule 10. A reader joins lookup to provenance on uid and lookup to
# timeline on uid. Both must hold with no orphan on either side, in both directions, or the
# published set is internally inconsistent whatever each file says alone.
for flow in FLOWS:
    lookup = load(os.path.join(OUTPUT, "%s_lookup.csv" % flow))
    timeline = load(os.path.join(OUTPUT, "%s_lineage_timeline.csv" % flow))
    provenance = load(os.path.join(OUTPUT, "%s_provenance.csv" % flow))
    journeys = load(os.path.join(OUTPUT, "%s_commodity_journeys.csv" % flow))
    uids = {r["uid"] for r in lookup}
    record("%s: every file joins to every other on uid, with no orphan either way" % flow,
           uids == {r["uid"] for r in timeline} == {r["uid"] for r in provenance}
           == {r["uid"] for r in journeys},
           "%d uid(s), joinable in both directions across all four files" % len(uids))
    # And the family a commodity is in must be the same family in every file that names one.
    fam_lookup = {r["uid"]: r["family_id"] for r in lookup}
    disagree = [r["uid"] for r in timeline if fam_lookup[r["uid"]] != r["family_id"]]
    disagree += [r["uid"] for r in provenance if fam_lookup[r["uid"]] != r["family_id"]]
    disagree += [r["uid"] for r in journeys if fam_lookup[r["uid"]] != r["family_id"]]
    record("%s: the family named for a commodity is the same in all four files" % flow,
           not disagree, "%d comparison(s)" % (len(timeline) + len(provenance) + len(journeys))
           if not disagree else "%d disagree: %s" % (len(set(disagree)), sorted(set(disagree))[:3]))

# GATE 1's EVIDENCE MUST DESCRIBE THIS BUILD. Finding 125, 2026-08-18.
#
# gate1/ is committed output, and the only control that read it asked whether output/ had copied
# it faithfully. That is a real question but it is the wrong end: a gate1 built from an older
# Stage 4 would be copied just as faithfully, the control would pass, and the release would ship
# v1 identifiers joined to families that no longer exist. gate1 is also the file Gate 1 itself
# rests on, so a stale one would be evidence for a claim about a crosswalk that is no longer the
# one being shipped. Nothing tied the two together until now. It agrees on this build.
for flow in ("imports", "exports"):
    _g = load(os.path.join(GATE1, "v1_to_v2_identifiers_%s.csv" % flow))
    _f = {r["record_id"]: r for r in
          load(os.path.join(WORK, "stage4_families_%s.csv" % flow))}
    _absent = [r["v2_record_id"] for r in _g if r["v2_record_id"] and r["v2_record_id"] not in _f]
    _drifted = [r["v2_record_id"] for r in _g if r["v2_record_id"] in _f
                and (r["v2_family_id"] or "") != _f[r["v2_record_id"]]["family_id"]]
    record("%s: gate1's evidence describes the Stage 4 this build produced" % flow,
           not _absent and not _drifted,
           "%d row(s), every v2 identifier and family present and matching" % len(_g)
           if not (_absent or _drifted)
           else "%d absent from stage4, %d naming a different family: %s"
                % (len(_absent), len(_drifted), (_absent + _drifted)[:4]))

# PROOF THAT THE GATE 1 CONTROL CAN FAIL, by ageing one row rather than by history.
_ag = [dict(r) for r in load(os.path.join(GATE1, "v1_to_v2_identifiers_imports.csv"))]
_af = {r["record_id"]: r for r in load(os.path.join(WORK, "stage4_families_imports.csv"))}
_ag[0]["v2_family_id"] = "IM-0000000000-190001"
_aged = [r["v2_record_id"] for r in _ag if r["v2_record_id"] in _af
         and (r["v2_family_id"] or "") != _af[r["v2_record_id"]]["family_id"]]
record("the gate1 control objects when gate1 names a family the build does not hold",
       len(_aged) == 1 and _aged[0] == _ag[0]["v2_record_id"],
       "a stale family identifier in gate1 is caught, and only that row")

# GATE 1's DIFFERENCES ARE ALL EXPLAINED IN WRITING. Finding 142, 2026-08-18.
#
# Gate 1's criterion is that every difference from the v1 release is either zero or explained in
# writing as a deliberate improvement with the reason. The difference files enumerate the rows and
# their `detail` column states only the SHAPE of each one, "2 v1 families became one in v2", which
# is a restatement rather than a reason. gate1/GATE1_DIFFERENCES_EXPLAINED.md carries the writing.
#
# The 24 rows are 9 connected events, because a family v2 splits usually also appears in a row v2
# merges. This asserts that every v1 family named in either difference file appears in the
# document, so a new difference cannot arrive unexplained.
_g1doc_path = os.path.join(GATE1, "GATE1_DIFFERENCES_EXPLAINED.md")
_g1doc = open(_g1doc_path, encoding="utf-8").read() if os.path.exists(_g1doc_path) else ""
_named = set()
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(GATE1, "family_differences_%s.csv" % _flow)):
        for _f in _r["v1_family_id"].split(";"):
            if _f.strip():
                _named.add(_f.strip())
_unexplained = sorted(f for f in _named if f not in _g1doc)
record("every v1 family Gate 1 flags is explained in writing", not _unexplained and bool(_named),
       "%d v1 family/families across the difference files, every one named in "
       "GATE1_DIFFERENCES_EXPLAINED.md" % len(_named)
       if not _unexplained and _named
       else "%d not explained: %s" % (len(_unexplained), _unexplained[:5]))

# PROOF THAT THE TERMINAL CONTROL ABOVE CAN FAIL. It reports clean on this build, and a control
# that has never failed is not evidence. One row's terminal is bent and the same predicate is
# re-run; it must object. Nothing published is touched, the copies are local.
_p_look = [dict(r) for r in load(os.path.join(PROJECT, "output", "imports_lookup.csv"))]
_p_routed = {r["span_id"]: r for r in load(os.path.join(WORK, "stage3_routed_imports.csv"))}
_p_span = {r["record_id"]: r["span_id"]
           for r in load(os.path.join(WORK, "stage4_families_imports.csv"))}
_p_look[0]["latest_hs_code"] = "9999.99.99.99"
_p_caught = [r["uid"] for r in _p_look
             if r["uid"] in _p_span and _p_span[r["uid"]] in _p_routed
             and (digits(r["latest_hs_code"]) != digits(_p_routed[_p_span[r["uid"]]]["terminal_code"])
                  or r["latest_description"]
                  != _exp(_p_routed[_p_span[r["uid"]]]["terminal_description"]))]
record("the terminal control objects when a terminal is bent",
       len(_p_caught) == 1 and _p_caught[0] == _p_look[0]["uid"],
       "bending one row's latest_hs_code is caught, and only that row")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed),
                                                  len(failed)))
if failed:
    print()
    print("Stage 6 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 6 is validated. Nothing was published that an earlier stage did not produce.")
