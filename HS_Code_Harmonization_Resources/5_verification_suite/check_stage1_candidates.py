"""
Check for Stage 1a. Is the work-list complete, and is every candidate a real code?


Inputs:
    work/stage1_candidates_{imports,exports}.csv    produced by pipeline/stage1_candidates.py
    work/commodity_inventory_{imports,exports}.csv  produced by pipeline/stage0_read_source.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Does the work-list hold every retirement in the delivery, exactly once, with a candidate field
that contains only codes that really traded?

It does NOT ask whether the right successor is among the candidates. Nothing at this stage can
answer that, and one control below exists to stop a later stage from assuming it.


WHY THE RETIREMENTS ARE REBUILT RATHER THAN COUNTED
-----------------------------------------------------
The controls recompute the retirement set from the Stage 0 inventory in this file, without
calling the stage. A check that reuses the code it tests proves only that the code is
self-consistent, which this project has already paid for twice.


THE CONTROL THAT MATTERS MOST IS THE ONE ABOUT CHAPTER EXITS
--------------------------------------------------------------
The delivery holds headings 3001 to 3006. A code whose trade left Chapter 30 has a destination
that cannot appear in any candidate list, yet it is still handed a full field from its own
heading. Five such codes are known, settled in the adjudication workbook as having no successor
inside the chapter, and this stage offers them between 9 and 22 candidates each.

The control pins that. It asserts those five still receive candidates, which sounds backwards
until what it protects is clear: it is a standing reminder, in executable form, that a non-empty
candidate list is not evidence a successor exists. If a later stage ever starts treating the
candidate field as the universe of possible answers, these five are the codes it will get wrong.
"""

import csv
import os
import sys
from collections import defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(PROJECT, "work")

# Pinned from the delivery on 2026-08-10.
#
# IMPORTS RE-MEASURED 2026-08-17, and every move here is the same one event. Stage 1a now ends a
# span where a relabel crosses a decisive distinction, not only where the number was left empty,
# so 3004.50.99.30 became two retirements instead of one: "for vet use" to 1989-12 and "for human
# use" to 1997-12. Retirements 279 -> 280, the extra row sits in the same subheading so tiers move
# 240 -> 241, and a code now retires twice on imports where none did, so reused 0 -> 1.
#
# THE VALUE PIN DOES NOT MOVE, and that is the control worth reading. The two spans carry
# CAD 1,124,520 and CAD 55,679,911, which is exactly the CAD 56,804,431 the single span carried.
# Splitting a span redistributes value and never creates or destroys it, so a value pin that moved
# here would mean the split had invented trade.
# RE-MEASURED 2026-08-19, finding 146, when the boundary and concordance flags became a union
# of the last traded month and the declared termination. A line that went quiet before its
# revision now sits at the boundary the record retired it at: imports boundary 109 -> 124 and
# cbsa 89 -> 97, exports boundary 8 -> 13 and cbsa 3 -> 6. Every mover is a declared span whose
# note names a revision December; the union can only add, so no previous yes moved. Retirement
# counts, values and tiers are untouched, which is what shows the flags changed and the
# retirements did not.
EXPECTED = {
    "imports": {"retirements": 280, "value": 102128187239, "tiers": {"same_subheading": 241,
                                                                     "same_heading": 39},
                "cbsa": 97, "schedule": 133, "boundary": 124, "reused": 1},
    # RE-PINNED 2026-08-31 when the export flow moved from domestic_exports.db to exports.db
    # on the analyst's instruction. The figure moved because re-exports are now counted;
    # it did not break. Imports are untouched and their pins did not move.
    "exports": {"retirements": 40, "value": 82864746189, "tiers": {"same_subheading": 19,
                                                                   "same_heading": 21},
                "cbsa": 6, "schedule": 22, "boundary": 13, "reused": 2},
}
# A retired code number handed to different goods years later retires more than once. Five such
# events exist, four of them from the 1988-12 export restructure, and three were invisible until
# 2026-08-10 because the code's final span is still trading.
REUSE_GAP_MONTHS = 60
# 3004509930 joined on 2026-08-17 and is a different shape from the other five. Those are numbers
# left empty and later handed to different goods. This one never stopped trading: it was relabelled
# from veterinary to human use in 1990-01, which ends the span just as surely.
KNOWN_REUSED = {"imports": {"3002900020", "3004509930"},
                "exports": {"30029010", "30029020", "30033100", "30049010"}}
VALUE_TOLERANCE = 1.0

# A span also ends where a relabel crosses a decisive distinction. The RULES are shared, because
# they are the published specification in decisions/decisive_distinctions.csv; the composition is
# written out here rather than imported from Stage 1a, so this check's rebuild can still disagree
# with the stage. Importing continues_the_span would compare the stage's answer with itself.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import meaning_gates as _gates  # noqa: E402

_DISQUALIFYING = [r for r in _gates.load_rules(
    os.path.join(PROJECT, "decisions", "decisive_distinctions.csv"))
    if str(r.get("action", "")).strip() == "disqualify"]


def _relabelled(before_text, after_text):
    return any(_gates.rule_fires(rule, before_text, after_text) for rule in _DISQUALIFYING)

# The delivery is Chapter 30 and nothing else. Every rung of the candidate ladder and the whole
# chapter-exit argument rest on that. Asserted below rather than assumed, because if a future
# delivery carries another chapter, both stop being true on the same day.
EXPECTED_HEADINGS = {"3001", "3002", "3003", "3004", "3005", "3006"}

# Codes that left Chapter 30 for heading 38.22, so their real destination can never appear in a
# candidate list. The two groups are kept apart on purpose.
#
# ADJUDICATED: settled in the review workbook, signed, with a recorded reason.
# INFERRED: not adjudicated. These are the eight-digit export codes covering the same goods as
# the adjudicated import codes, retiring at the same boundary. The reasoning is sound and it is
# still reasoning. They are named separately so a reader can tell a ruling from an inference,
# and so dropping them costs one line if the analyst rules otherwise.
CHAPTER_EXITS_ADJUDICATED = {"imports": ["3006200090", "3006200020", "3002110000"],
                             "exports": []}
CHAPTER_EXITS_INFERRED = {"imports": [],
                          "exports": ["30062000", "30021100"]}

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def must_raise(name, function, *args):
    try:
        function(*args)
    except ValueError as error:
        record(name, True, "refused as intended: %s" % error)
        return
    record(name, False, "accepted input it should have refused")


def next_period(period):
    """Written out here rather than imported, so a fault cannot hide in both."""
    if len(period) != 6 or not period.isdigit():
        raise ValueError("period %r is not YYYYMM" % period)
    year, month = int(period[:4]), int(period[4:])
    if not 1 <= month <= 12:
        raise ValueError("period %r has month %d" % (period, month))
    return "%04d%02d" % (year + 1, 1) if month == 12 else "%04d%02d" % (year, month + 1)


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


print("Check for Stage 1a. Is the work-list complete, and is every candidate a real code?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
must_raise("a period that is not YYYYMM is refused", next_period, "1997")
must_raise("a period with an impossible month is refused", next_period, "199713")

print()
print("Controls that MUST PASS (correct input must not be flagged):")
record("December rolls into the next January", next_period("199712") == "199801",
       "199712 -> %s" % next_period("199712"))
record("a mid-year month rolls forward", next_period("201106") == "201107",
       "201106 -> %s" % next_period("201106"))

for flow in ("imports", "exports"):
    print()
    print("%s, rebuilt from the Stage 0 inventory without calling the stage:" % flow)
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    worklist = load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow))
    expect = EXPECTED[flow]

    lives = defaultdict(list)
    for r in inventory:
        lives[r["hs_code"]].append(r)
    delivery_end = max(r["last_period"] for r in inventory)
    # Spans rebuilt here, not imported. A gap longer than the reuse threshold starts a new span,
    # and every span ending before the delivery does is its own retirement.
    def to_months(p):
        return int(p[:4]) * 12 + int(p[4:])

    rebuilt = set()
    rebuilt_basis = {}
    for c, rs in lives.items():
        # A span ends at a gap the number was left empty for, OR at a relabel that crosses a
        # decisive distinction, which ends it with no gap at all. Both are written out here
        # rather than imported, so this rebuild can still disagree with Stage 1a. Only the rules
        # themselves are shared, because they are the published specification.
        ordered = sorted(rs, key=lambda x: (x["first_period"], x["last_period"]))
        spans = [[ordered[0]["first_period"], ordered[0]["last_period"],
                  ordered[0]["description"]]]
        for x in ordered[1:]:
            f, l, d = x["first_period"], x["last_period"], x["description"]
            if (to_months(f) - to_months(spans[-1][1]) > REUSE_GAP_MONTHS
                    or _relabelled(spans[-1][2], d)):
                spans.append([f, l, d])
            else:
                spans[-1][1] = max(spans[-1][1], l)
                spans[-1][2] = d
        for position, (_first, last, _description) in enumerate(spans, start=1):
            if last != delivery_end:
                rebuilt.add((c, last))
                # Rebuilt from the two facts the rule rests on, read off the inventory here
                # rather than taken from the stage's own columns: Statistics Canada's
                # termination note on this span's final record, and whether a later span exists.
                # AND WHOSE NOTE IT IS. Statistics Canada attaches "(Terminated YYYY-MM)" to the
                # commodity string, so a recycled number carries it on every life it ever had.
                # Stage 0 works out which life it describes; taking it at face value made exports
                # 30029020's 1988 blood line look declared by a note about Saxitoxin. Finding 105.
                note = next((x["stated_termination"] for x in rs
                             if x["last_period"] == last
                             and x.get("stated_termination_is_this_life") != "no"), "")
                rebuilt_basis[(c, last)] = ("declared" if note
                                            else "code_reused" if position < len(spans)
                                            else "trade_ceased_only")
    listed = {(r["retiring_code"], r["last_period"]) for r in worklist}

    record("%s: the work-list holds exactly the retirements in the delivery" % flow,
           rebuilt == listed,
           "rebuilt %d, listed %d, differing %d"
           % (len(rebuilt), len(listed), len(rebuilt ^ listed)))
    record("%s: no code and span end appears twice" % flow, len(listed) == len(worklist),
           "%d distinct of %d row(s)" % (len(listed), len(worklist)))
    listed_basis = {(r["retiring_code"], r["last_period"]): r["retirement_basis"]
                    for r in worklist}
    tally = {}
    for value in rebuilt_basis.values():
        tally[value] = tally.get(value, 0) + 1
    record("%s: what makes each stoppage a retirement is rebuilt and agrees" % flow,
           listed_basis == rebuilt_basis,
           "%s, %d row(s) disagree" % (dict(sorted(tally.items())),
                                       sum(1 for k, v in listed_basis.items()
                                           if rebuilt_basis.get(k) != v)))
    reused = {r["retiring_code"] for r in worklist if int(r["span_count"]) > 1}
    record("%s: the reused code numbers are the ones already known" % flow,
           reused == KNOWN_REUSED[flow], "%s, expected %s" % (sorted(reused), sorted(KNOWN_REUSED[flow])))
    twice = {c for c in reused if sum(1 for r in worklist if r["retiring_code"] == c) > 1}
    record("%s: codes that retired twice are listed twice" % flow,
           len(twice) == expect["reused"], "%d, expected %d" % (len(twice), expect["reused"]))
    record("%s: no code still trading at the delivery's end is called retired" % flow,
           all(r["last_period"] != delivery_end for r in worklist),
           "delivery ends %s" % delivery_end)
    record("%s: the retirement count is unchanged" % flow, len(worklist) == expect["retirements"],
           "%d, expected %d" % (len(worklist), expect["retirements"]))
    value = sum(float(r["total_value_cad"]) for r in worklist)
    record("%s: the value carried by the retirements is unchanged" % flow,
           abs(value - expect["value"]) < VALUE_TOLERANCE,
           "CAD {:,.0f}, expected CAD {:,.0f}".format(value, expect["value"]))

    codes = set(lives)
    # Every failure is collected rather than the first one reported. One bad row and a hundred
    # bad rows are different problems calling for different responses, and a check that stops at
    # the first cannot tell them apart.
    bad_candidates = []
    self_listed = []
    for r in worklist:
        cands = [c for c in r["candidates_narrowest"].split(";") if c]
        if r["retiring_code"] in cands:
            self_listed.append(r["retiring_code"])
        for c in cands:
            if c not in codes:
                bad_candidates.append("%s lists %s" % (r["retiring_code"], c))
    record("%s: every candidate is a code that really traded" % flow, not bad_candidates,
           "all candidates found in the inventory" if not bad_candidates
           else "%d bad candidate(s) across the work-list. First: %s"
                % (len(bad_candidates), "; ".join(bad_candidates[:3])))
    record("%s: no code is offered as its own successor" % flow, not self_listed,
           "0 self-listed" if not self_listed else "self-listed: %s" % self_listed[:5])

    stale = [r["retiring_code"] for r in worklist
             if any(lives[c] and max(x["last_period"] for x in lives[c]) <= r["last_period"]
                    for c in r["candidates_narrowest"].split(";") if c)]
    record("%s: no candidate stopped trading before the code it would succeed" % flow, not stale,
           "0 stale" if not stale else "stale: %s" % stale[:5])

    record("%s: the boundary is the month after the last traded month" % flow,
           all(r["boundary"] == next_period(r["last_period"]) for r in worklist),
           "%d row(s) checked" % len(worklist))

    tiers = defaultdict(int)
    for r in worklist:
        tiers[r["narrowest_tier"]] += 1
    record("%s: the narrowest-tier split is unchanged" % flow,
           dict(tiers) == expect["tiers"], "%s, expected %s" % (dict(tiers), expect["tiers"]))

    for label, key, pin in (("CBSA concordance", "cbsa_concordance_covers", expect["cbsa"]),
                            ("tariff schedule", "tariff_schedule_covers", expect["schedule"]),
                            ("HS revision boundary", "at_hs_revision_boundary", expect["boundary"])):
        n = sum(1 for r in worklist if r[key] == "yes")
        record("%s: retirements reached by the %s are unchanged" % (flow, label), n == pin,
               "%d, expected %d" % (n, pin))

print()
print("The scope every rung of the ladder rests on:")
for flow in ("imports", "exports"):
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    headings = {r["heading"] for r in inventory}
    # If this ever fails, the chapter-exit argument and the ladder's naming both stop holding
    # on the same day, and the stage needs rethinking rather than patching.
    record("%s: the delivery holds Chapter 30 and nothing else" % flow,
           headings == EXPECTED_HEADINGS,
           "%s, expected %s" % (sorted(headings), sorted(EXPECTED_HEADINGS)))

# The chapter rung and the everything rung must coincide exactly while the scope above holds.
# The moment they diverge, either the delivery grew or the filter broke.
for flow in ("imports", "exports"):
    worklist = load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow))
    diverging = [r["retiring_code"] for r in worklist
                 if r["n_same_chapter"] != r["n_any_alive"]]
    record("%s: the chapter rung and the everything rung coincide" % flow, not diverging,
           "0 diverge across %d row(s)" % len(worklist) if not diverging
           else "diverge: %s" % diverging[:5])
    used_widest = [r["retiring_code"] for r in worklist if r["narrowest_tier"] == "any_alive"]
    record("%s: no retirement has to fall back past the chapter rung" % flow, not used_widest,
           "0 rows reach any_alive" if not used_widest else "reached: %s" % used_widest[:5])

print()
print("The blind spot, pinned so a later stage cannot forget it:")
for flow in ("imports", "exports"):
    worklist = {r["retiring_code"]: r for r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow))}
    for label, table in (("adjudicated", CHAPTER_EXITS_ADJUDICATED),
                         ("inferred, not adjudicated", CHAPTER_EXITS_INFERRED)):
        exits = table[flow]
        if not exits:
            continue
        present = [c for c in exits if c in worklist]
        record("%s: the %s chapter exits are still in the work-list" % (flow, label),
               len(present) == len(exits), "%d of %d present" % (len(present), len(exits)))
        # Each is offered candidates, none of which can be right. This keeps the limitation
        # executable rather than leaving it in a comment. It asserts the symptom persists; it
        # cannot tell whether the candidates are wrong, because it does not know the answer.
        offered = {c: int(worklist[c]["narrowest_count"]) for c in present}
        record("%s: each %s exit is still offered candidates that cannot be right" % (flow, label),
               all(n > 0 for n in offered.values()), "%s" % offered)

record("an empty candidate list never occurs, so it can never mean 'no successor'",
       all(int(r["narrowest_count"]) > 0
           for flow in ("imports", "exports")
           for r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow))),
       "a verdict of no successor must come from the official record, never from this stage")

print()
print("Probes: paths that this delivery never reaches, exercised with wordings it does not contain.")
print("A branch that has never run is untested, however green the rest of the report looks.")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage1_candidates as stage  # noqa: E402

# Three rungs of the ladder return nothing on the current delivery, because every retirement
# finds a candidate in its own subheading or heading. Each is reachable with a plausible
# delivery, so each is exercised here on a synthetic one.
# Hand-built, never derived from the stage under test. Each entry carries its spans as well as
# the outer envelope, because since 2026-08-11 the stage reads spans and a fixture without them
# would exercise nothing. The two are deliberately identical here: these are single-life codes,
# and the reuse case is probed separately below.
def _life(first, last, spans=None):
    return {"first_period": first, "last_period": last,
            "spans": spans if spans is not None else [(first, last)]}


LIVES = {
    "3001100010": _life("198801", "199712"),   # the retiring code
    "3001100090": _life("199801", "202606"),   # same subheading
    "3001200000": _life("199801", "202606"),   # same heading
    "3002100000": _life("199801", "202606"),   # same chapter only
    "3801000000": _life("199801", "202606"),   # another chapter
}
def rung(available, existence=None):
    # An empty existence table means the tariff says nothing, so continuity falls back to trade.
    # That is the pre-2005 case and it is the one these probes exercise.
    return stage.assemble_candidates("3001100010",
                                     {k: v for k, v in LIVES.items()
                                      if k == "3001100010" or k in available},
                                     "199712", existence or {})["narrowest_tier"]

record("probe: a candidate in the same subheading takes the narrowest rung",
       rung({"3001100090", "3001200000", "3002100000"}) == "same_subheading", "same_subheading")
record("probe: with none in the subheading, the heading rung is used",
       rung({"3001200000", "3002100000"}) == "same_heading", "same_heading")
record("probe: with none in the heading, the chapter rung is used",
       rung({"3002100000", "3801000000"}) == "same_chapter",
       "same_chapter, never reached by this delivery")
record("probe: with none in the chapter, the widest rung is used",
       rung({"3801000000"}) == "any_alive",
       "any_alive, never reached by this delivery")
record("probe: with nothing alive afterwards, no rung returns anything",
       rung(set()) == "none",
       "none, never reached by this delivery and the only way a candidate list can be empty")

# Continuity, probed on both sides. The trade view alone would exclude a code the tariff shows
# already in force, which is the defect found on 2026-08-11: 30021100 was in the 2017 schedule
# and first traded 2017-02, and reading first-traded as first-existing removed it.
# A REUSED CODE NUMBER MUST NOT RESCUE ITS OWN RETIRED SPAN.
#
# 3002.90.20 traded 1988-01 to 1988-12 as veterinary blood products and again 2000-10 to 2016-11
# as Saxitoxin. Read as one lifespan it looks alive from 1988 to 2016, so its retired 1988 span
# was offered as successor to 3002.90.10, which retired in the very same month, and each of the
# pair was proposed as the other's successor. This probe is that shape, in miniature.
REUSE = {
    "3001100010": _life("198801", "198812"),                       # retires 1988-12
    # Same shape as 3002.90.20: dead alongside it, then a different commodity years later.
    "3001100090": _life("198801", "201611", [("198801", "198812"), ("200010", "201611")]),
    # A genuine successor, so the field is not empty and the probe tests exclusion rather than
    # the never-empty fallback.
    "3001100077": _life("198901", "202606"),
}
reuse_field = stage.assemble_candidates("3001100010", REUSE, "198812", {})
record("probe: a code whose only later life is a reuse is not continuous with this retirement",
       "3001100090" not in reuse_field["continuous"],
       "3001100090 excluded; continuous = %s" % reuse_field["continuous"])
record("probe: the genuine successor is still found",
       "3001100077" in reuse_field["continuous"], "3001100077 present")
# And the converse, so the exclusion is not merely "any code with two spans is dropped".
STRADDLE = dict(REUSE)
STRADDLE["3001100090"] = _life("198801", "202606", [("198801", "199512"), ("199601", "202606")])
record("probe: a code with two spans that genuinely straddles the retirement is kept",
       "3001100090" in stage.assemble_candidates("3001100010", STRADDLE, "198812",
                                                 {})["continuous"],
       "kept, because one of its spans both outlives the retirement and had begun by then")

# The tail of the delivery. A span ending one month before the data does is not a retirement;
# it is a code that had a quiet month while the file ran out. Probed directly because the
# artefact only shows the consequence.
record("probe: the window that holds recent stoppages is twelve months",
       stage.TAIL_MONTHS_NOT_YET_DECIDABLE == 12,
       "%d months, derived from live codes: a 1-month silence occurs in 100%% of their gaps, "
       "a 12-month one in about 2%%" % stage.TAIL_MONTHS_NOT_YET_DECIDABLE)
LATE = dict(LIVES)
LATE["3001100055"] = _life("200003", "202606")   # begins well after
# A continuous candidate must be present, or the never-empty fallback restores the late one and
# the probe tests nothing. That fallback is correct and this probe exists beside it, not against
# it: exclusion only applies while some continuous candidate survives.
def field(available, existence=None):
    return stage.assemble_candidates("3001100010",
                                     {k: LATE[k] for k in ("3001100010",) + tuple(available)},
                                     "199712", existence or {})

# Continuity is DERIVED here and applied in Stage 1c. These probe the derivation, and the first
# one is the guarantee that matters: this stage removes nothing, so nothing can be lost here.
late = field(("3001100090", "3001100055"))
record("probe: a candidate beginning long after the retirement is still offered",
       "3001100055" in late["narrowest"],
       "this stage filters nothing, so no inference here can be irreversible")
record("probe: but it is not marked continuous",
       "3001100055" not in late["continuous"] and "3001100090" in late["continuous"],
       "continuous: %s" % sorted(late["continuous"]))
record("probe: the tariff showing it in force marks it continuous after all",
       "3001100055" in field(("3001100055",), {1998: {"3001100055"}})["continuous"],
       "presence in the boundary-year schedule proves existence")
record("probe: absence from the schedule never unmarks a trade-continuous candidate",
       "3001100090" in field(("3001100090",), {1998: set()})["continuous"],
       "the tariff omits statistical breakouts, so absence proves nothing")

print()
print("Proxies: what each rule intends, what it computes, and how far apart they are.")
# Convention 11. Every rule here constrains something it cannot observe using something it can.
# These pin the distance between the two, so a proxy drifting from the thing it stands for is a
# failing control rather than a discovery someone makes later.
import glob as _glob
import re as _re

_best = {}
for _path in _glob.glob(os.path.join(PROJECT, "evidence", "cbsa", "sched_ch30_*.csv")):
    _m = _re.search(r"sched_ch30_(\d{4})(?:-(\d+))?\.csv$", _path)
    if not _m:
        continue
    _y, _a = int(_m.group(1)), int(_m.group(2) or 0)
    if _y not in _best or _a > _best[_y][0]:
        _best[_y] = (_a, _path)
CODES_IN, SUBS_IN = {}, {}
for _y, (_a, _path) in _best.items():
    _c, _s = set(), set()
    for _r in load(_path):
        for _v in (_re.sub(r"\D", "", _r.get("hs10") or ""),
                   _re.sub(r"\D", "", _r.get("tariff_item8") or "")):
            if len(_v) >= 8:
                _c.add(_v)
            if len(_v) >= 6:
                _s.add(_v[:6])
    CODES_IN[_y], SUBS_IN[_y] = _c, _s

# Intends "was this subheading abolished". Computes "did anything under it trade afterwards".
tested = disagree = 0
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % flow)):
        year = int(r["boundary"][:4])
        if year not in SUBS_IN:
            continue
        tested += 1
        if (r["subheading_survives"] == "yes") != (r["subheading"] in SUBS_IN[year]):
            disagree += 1
record("proxy: subheading_survives disagrees with the tariff at the measured rate",
       (tested, disagree) == (148, 11),
       "%d of %d disagree, expected 11 of 148. It feeds the suggestion that a code left the "
       "chapter, so it is wrong about one time in fourteen" % (disagree, tested))

# Intends "the successor was created here". Computes "its first shipment fell the month after".
born_tested = born_wrong = 0
for flow in ("imports", "exports"):
    # THE STARTS OF EVERY LIFE, NOT THE EARLIEST START OF THE CODE. Finding 129, 2026-08-18.
    #
    # This was a map from code to its earliest first_period, which is the era-blind wording map
    # this project has now paid for seven times, wearing a different hat: it keys on the code and
    # forgets that a recycled number has more than one life. 3002900020 first traded 1998-01 as
    # "Butter-making ferment cultures" and again 2022-01 as "Toxoids, antitoxins, ...", so asking
    # whether it "begins at the boundary" of 2021-12 got 1998-01 and answered no. The row was
    # dropped from the subject of a PUBLISHED error rate. Measured: 28 testable rows era-blind
    # against 29 era-aware, the same 1 disagreement, so the rate was right and the subject was not.
    _starts = {}
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        _starts.setdefault(r["hs_code"], []).append(r)
    first = {code: [f for f, _last in stage.trading_spans(rows)]
             for code, rows in _starts.items()}
    for r in load(os.path.join(WORK, "stage1_review_%s.csv" % flow)):
        top, last = r["top_candidate"], r["last_period"]
        if not top or last[4:] != "12":
            continue
        boundary_year = int(last[:4]) + 1
        if boundary_year - 1 not in CODES_IN:
            continue
        if ("%04d01" % boundary_year) not in first.get(top, []):
            continue
        born_tested += 1
        if top in CODES_IN[boundary_year - 1]:
            born_wrong += 1
# 25 -> 27 testable rows on 2026-08-14. The proxy's ERROR RATE is unchanged at 1: two more rows
# became testable because Layer 2 narrowed their candidate field onto a top candidate that begins
# at the boundary, which is what this proxy is about. The quantity being measured did not move.
# 27 -> 28 on 2026-08-18 with the carve-out rung, and again the error rate is unchanged at 1.
# 3002900050's top candidate became 3002490010, which is born at the boundary, so the row became
# testable for the first time; it is not a new disagreement. Re-measured, not relaxed.
# 28 -> 29 the same day, finding 129: reading every life's start rather than the code's earliest
# recovered 3002900020, whose second life begins at this very boundary. Still 1 disagreement.
record("proxy: successor_began_at_the_boundary disagrees at the measured rate",
       (born_tested, born_wrong) == (29, 1),
       "%d of %d were already in the previous year's schedule, expected 1 of 29"
       % (born_wrong, born_tested))

# Intends "the number was reassigned". Computes "trade stopped for over 60 months".
REUSE_CORROBORATED = {"3002900020": 5, "30049010": 13}
corroborated = {}
for flow in ("imports", "exports"):
    spans = defaultdict(list)
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        spans[r["hs_code"]].append((r["first_period"], r["last_period"]))
    for code in REUSE_CORROBORATED:
        if code not in spans:
            continue
        iv = sorted(spans[code])
        years = [y for y in sorted(CODES_IN)
                 if any(int(iv[i][1][:4]) < y < int(iv[i + 1][0][:4]) for i in range(len(iv) - 1))]
        if years and not any(code in CODES_IN[y] for y in years):
            corroborated[code] = len(years)
record("proxy: the reuse threshold is corroborated by the tariff where it can be seen",
       corroborated == REUSE_CORROBORATED,
       "%s, expected %s. Absent from the tariff for every year of the gap, so the number really "
       "was out of use" % (corroborated, REUSE_CORROBORATED))


print()
print("SILENCE IS READ AGAINST THE CODE'S OWN HISTORY, NOT THE CALENDAR")
# The analyst asked why commodities that stopped in 2024 to 2026 were being offered for decision
# when it may be too early to tell. Twelve months is calendar time, and what silence means
# depends on how often a code ever traded: 3003.42.00 traded 4 months out of 65 and has already
# come back from a 49-month gap.
_inv = {}
for _f in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _f)):
        _inv[(_f, _r["hs_code"])] = _r
record("every commodity records the longest silence it came back from",
       all("longest_quiet_months" in r for r in _inv.values()),
       "%d commodities carry it" % len(_inv))
record("that silence is bounded by trade on both sides",
       all(int(r["longest_quiet_months"]) <
           (int(r["last_period"][:4]) - int(r["first_period"][:4])) * 12
           + int(r["last_period"][4:]) - int(r["first_period"][4:]) + 1
           for r in _inv.values()),
       "no code claims a gap longer than its own span")
_all_rows = []
for _f in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % _f)):
        _r["flow"] = _f
        _all_rows.append(_r)
# ---------------------------------------------------------------------------------------------
# WHAT MAKES A STOPPAGE A RETIREMENT, pinned across both flows. Convention 4: the figures state
# what the delivery contains, so a later extract fails here instead of drifting downstream into a
# crosswalk that links events which never happened.
_basis_n, _basis_value = {}, {}
for _r in _all_rows:
    _b = _r["retirement_basis"]
    _basis_n[_b] = _basis_n.get(_b, 0) + 1
    _basis_value[_b] = _basis_value.get(_b, 0.0) + float(_r["total_value_cad"])
# 300/4/15 -> 299/5/15 on 2026-08-16, finding 105, and it is ONE row: exports 30029020's
# 1988-12 life carried "(Terminated 2016-12)", which describes the Saxitoxin line that replaced
# it twelve years later. A first correction moved 43 rows and was wrong: the other 42 are notes
# landing a few months AFTER the money stopped, which is the M4 pattern and not a misattribution.
# A note belongs elsewhere only when it lands at or after a LATER life's first month.
# 5 -> 6 reused on 2026-08-17, and again it is ONE row: imports 3004.50.99.30's veterinary life,
# which Stage 1a now ends at 1989-12 where the number was relabelled for human use. It reads
# code_reused because a later span of the same number exists, which is what that basis means. The
# number was not left empty first, so this is the basis stretching to a second shape of the same
# fact rather than a new basis. declared and trade_ceased_only do not move.
record("the retirement basis splits 299 declared, 6 reused, 15 trade-ceased",
       _basis_n == {"declared": 299, "code_reused": 6, "trade_ceased_only": 15},
       "%s" % dict(sorted(_basis_n.items())))
record("and the three account for the whole delivery to the cent",
       # RE-PINNED 2026-08-31 with the export basis. The split 299/6/15 did not move; only
       # the value did, by CAD 5,443,649,037, which is exactly the change in the export
       # retirement value and so is the re-exports and nothing else.
       abs(sum(_basis_value.values()) - 184992933428.0) < 0.005,
       "CAD {:,.2f}; declared {:,.0f}, reused {:,.0f}, trade-ceased {:,.0f}".format(
           sum(_basis_value.values()), _basis_value.get("declared", 0),
           _basis_value.get("code_reused", 0), _basis_value.get("trade_ceased_only", 0)))

# Convention 11. The rule reads an ABSENCE, so it is only as good as how reliably the note is
# written. Measured here rather than assumed, and the era where it is unreliable is named.
_note_cover = {}
for _f in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _f)):
        _era = "2000-2011 exports" if (_f == "exports" and "200001" <= _r["last_period"] <= "201112") else "other"
        _seen, _with = _note_cover.get(_era, (0, 0))
        _note_cover[_era] = (_seen + 1, _with + (1 if _r["stated_termination"] else 0))
_weak_seen, _weak_with = _note_cover.get("2000-2011 exports", (0, 0))
_too_early = [(r["flow"], r["retiring_code"], r["last_period"]) for r in _all_rows
              if r["retirement_basis"] == "trade_ceased_only"
              and r["last_period"] < stage.TERMINATION_NOTE_RELIABLE_FROM]
record("no stoppage is called a non-retirement from an era where the note is unreliable",
       not _too_early,
       "2000-2011 exports carry a termination note on %d of %d spans, so absence means little "
       "there; every trade_ceased_only row stops in %s or later, %d before it"
       % (_weak_with, _weak_seen, stage.TERMINATION_NOTE_RELIABLE_FROM, len(_too_early)))

_held = [r for r in _all_rows if r["too_recent_to_call"] == "yes"]
_calendar = [r for r in _held
             if int(r["months_before_delivery_end"]) <= stage.TAIL_MONTHS_NOT_YET_DECIDABLE]
record("a hold names which of the two reasons applies",
       all(int(r["months_before_delivery_end"]) <= stage.TAIL_MONTHS_NOT_YET_DECIDABLE
           or int(r["months_before_delivery_end"])
           <= max((int(_inv[(r["flow"], r["retiring_code"])]["longest_quiet_months"])
                   for _ in [0]), default=0)
           for r in _held if (r["flow"], r["retiring_code"]) in _inv),
       "%d held on the calendar, %d on the code's own quiet history"
       % (len(_calendar), len(_held) - len(_calendar)))
# A retirement the tariff abolished is not held on silence, because the tariff settles it.
record("a retirement at an HS revision boundary is never held on silence alone",
       not [r for r in _held
            if r["last_period"] in stage.HS_REVISIONS
            and int(r["months_before_delivery_end"]) > stage.TAIL_MONTHS_NOT_YET_DECIDABLE],
       "the tariff decides those, not the gap")

# THE CARVE-OUT RUNG. Added 2026-08-18 with finding 122.
#
# The ladder narrows to the tightest rung that returns anything and widens only when the narrow
# answer is EMPTY. At 2021-12 subheading 300290 survived while part of its content moved into the
# brand-new 300249, so the rung kept returning members, never widened, and the receiving lines
# were never candidates. No later layer could repair it, because the official record only vetoes:
# it cannot add a code the pool never held. These two are the delivery's whole subject for the
# rung, so they are named rather than counted.
_carve, _by_key = {}, {}
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % _flow)):
        _k = (_flow, _r["retiring_code"], _r["last_period"])
        _by_key[_k] = _r
        if _r["candidates_carve_out"]:
            _carve[_k] = _r["candidates_carve_out"].split(";")
record("the toxins line can reach the toxins line that replaced it",
       "3002490020" in _carve.get(("imports", "3002900010", "202112"), []),
       "3002900010 'Toxins, toxoids, antitoxins...' reaches 3002490020 'Toxins and similar "
       "products', born 202201 in a subheading the rung cannot see")
record("the cultures line can reach the cultures line that replaced it",
       "3002490010" in _carve.get(("imports", "3002900050", "202112"), []),
       "3002900050 'Micro-organisms cultures' reaches 3002490010 'Cultures, of micro-organisms "
       "(excluding yeasts) and similar products'")
# THE RUNG MUST NOT BECOME A SECOND LADDER. It fires on 6 import rows and none on export. An
# earlier draft matched on a shared leading word and fired on 126 of 280 import rows, because
# Chapter 30 lines lead on "medicaments" and "human"; a second draft tested only the newborn's
# head noun and fired on 71. Requiring both lines' head nouns to appear in the other's wording is
# what holds it to the carve-outs. If this count moves, the rule has loosened, not the delivery.
record("the carve-out rung stays a rung and not a ladder",
       len(_carve) == 6 and all(f == "imports" for f, _c, _p in _carve),
       "%d row(s) gain a carve-out candidate, all imports" % len(_carve))
# AND IT MAY ONLY ADD. Every carve-out candidate must also appear in the considered set, and the
# considered set must still partition the pool with what sits outside it.
_broke = [k for k in _carve
          for _row in [_by_key[k]]
          if not set(_carve[k]) <= set(_row["candidates_narrowest"].split(";"))]
record("every carve-out candidate is actually considered", not _broke,
       "the rung adds to candidates_narrowest and removes nothing"
       if not _broke else "%d row(s) record a carve-out that is not considered: %s" % (len(_broke), _broke[:3]))

# EVERY SPAN SPLIT, BY CAUSE. Finding 135, 2026-08-18.
#
# The paragraph justifying REUSE_GAP_MONTHS listed four gap values for five gaps, omitted 132,
# and claimed a 36-month threshold would move an event when it moves none. Nothing was checking
# it, so it drifted quietly and then drifted again when a second splitting cause was added. A
# split changes which family a record belongs to, so the inventory is pinned rather than described.
_splits = {"gap": [], "distinction": []}
for _flow in ("imports", "exports"):
    _recs = {}
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)):
        _recs.setdefault(_r["hs_code"], []).append(_r)
    for _code, _rows in _recs.items():
        _runs = stage.span_runs(_rows)
        for _prev, _next in zip(_runs, _runs[1:]):
            _plast = max(r["last_period"] for r in _prev)
            _gap = (stage.period_to_months(_next[0]["first_period"])
                    - stage.period_to_months(_plast))
            _splits["gap" if _gap > stage.REUSE_GAP_MONTHS else "distinction"].append(
                (_flow, _code, _gap))
_gapvals = sorted(g for _f, _c, g in _splits["gap"])
record("the gaps that split a span are the five measured ones",
       # Two export silences SHORTENED when re-exports filled months inside them: 132 -> 101
       # on 30029020 and 142 -> 107 on 30033100. The same five spans still split, at the same
       # places, and every gap is still over the 60-month threshold. The imports gap of 61 on
       # 3002900020 did not move.
       _gapvals == [61, 101, 107, 108, 350],
       "61, 101, 107, 108 and 350 months; the justification names all five")
record("exactly one span is split by a decisive distinction rather than a gap",
       sorted(_splits["distinction"]) == [("imports", "3004509930", 1)],
       "imports 3004509930, veterinary vitamins to human multivitamins at a one-month gap")
# The claim that nothing sits near the line, asserted rather than asserted about. SCOPED TO
# RELABELLED RESUMPTIONS on 2026-08-19, finding 143: these are gaps between RECORDS, meaning
# the wording changed across each, and they are the only gaps the threshold ever tests. This
# control's message used to read "largest gap kept inside a span", which claimed the whole
# delivery while measuring only the relabelled population; the nine same-worded silences the
# rule never sees run 61 to 121 months and are held to disclosure by the controls below.
_allgaps = []
_inv_records = {}
for _flow in ("imports", "exports"):
    _inv_records[_flow] = load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow))
    _recs = {}
    for _r in _inv_records[_flow]:
        _recs.setdefault(_r["hs_code"], []).append(_r)
    for _code, _rows in _recs.items():
        _o = sorted(_rows, key=lambda r: (r["first_period"], r["last_period"]))
        for _a, _b in zip(_o, _o[1:]):
            _g = (stage.period_to_months(_b["first_period"])
                  - stage.period_to_months(_a["last_period"]))
            if _g > 1:
                _allgaps.append(_g)
_below = max([g for g in _allgaps if g <= stage.REUSE_GAP_MONTHS] or [0])
_above = min([g for g in _allgaps if g > stage.REUSE_GAP_MONTHS] or [0])
record("no relabelled trading gap sits near the reuse threshold",
       _below == 34 and _above == 61,
       "largest relabelled gap kept inside a span is %d months, smallest that splits is %d, "
       "so the threshold could move anywhere between them and split the same relabelled "
       "resumptions" % (_below, _above))

print()
print("SILENCES THE REUSE RULE NEVER SEES, held equal to their disclosure:")
# A silence inside one record, under one unchanged wording, is never tested against
# REUSE_GAP_MONTHS, whatever its length. Nine such silences past the threshold exist and are
# disclosed with their evidence in gate1/reuse_silence_disclosure.csv. This control holds the
# disclosure equal to the delivery in both directions, so a new qualifying silence in a later
# delivery fails the build until it is disclosed, and a disclosed silence the delivery does not
# hold fails it too. The equivalence: a record's longest quiet stretch of N silent months is a
# trading gap of N+1, and the rule splits where the gap EXCEEDS the threshold, so a record
# qualifies at longest_quiet_months >= REUSE_GAP_MONTHS. Finding 143.
_qualifying = set()
for _flow in ("imports", "exports"):
    for _r in _inv_records[_flow]:
        if int(_r["longest_quiet_months"] or 0) >= stage.REUSE_GAP_MONTHS:
            _qualifying.add((_flow, _r["hs_code"], _r["first_period"]))
_disclosed_rows = load(os.path.join(PROJECT, "gate1", "reuse_silence_disclosure.csv"))
_disclosed = {(_r["flow"], _r["hs_code"], _r["record_first_period"]) for _r in _disclosed_rows}
record("every same-worded silence past the threshold is disclosed",
       _qualifying <= _disclosed,
       "%d qualifying record(s), %d disclosed" % (len(_qualifying), len(_disclosed))
       if _qualifying <= _disclosed
       else "undisclosed: %s" % sorted(_qualifying - _disclosed))
record("every disclosed silence exists in the delivery",
       _disclosed <= _qualifying,
       "%d row(s) checked against the inventory" % len(_disclosed)
       if _disclosed <= _qualifying
       else "disclosed but not in the delivery: %s" % sorted(_disclosed - _qualifying))
# NINE -> EIGHT on 2026-08-31, and the explanation the pin demands: the export flow moved
# from domestic_exports.db to exports.db, and a re-export of CAD 239,444 in 2013-07 lands
# inside what was a 71-month silence on exports 30031000. It breaks that silence into runs
# of 20 and 51 months, both under the 60-month threshold, so the record no longer has a
# qualifying silence and is no longer disclosed. The wording is identical in all three
# months, so this is one record throughout and not a relabelling. The other eight are
# unchanged. This is a change in the delivery, which is what the pin asks to be told.
record("the silence disclosure count is pinned at eight",
       len(_disclosed_rows) == 8, "%d row(s); a change here is a change in the delivery and "
       "must be explained, not absorbed" % len(_disclosed_rows))
_probe_missing = _qualifying - (_disclosed - {sorted(_disclosed)[0]})
record("the disclosure control objects when a disclosed silence is removed",
       len(_probe_missing) == 1,
       "dropping one disclosure row leaves exactly one silence undisclosed")
_probe_extra = (_disclosed | {("imports", "9999999999", "199001")}) - _qualifying
record("the disclosure control objects when a silence is invented",
       _probe_extra == {("imports", "9999999999", "199001")},
       "a fabricated disclosure row is caught, and only that row")

print()
print("A HOLD FIRES ONLY WHERE SILENCE IS THE ONLY EVIDENCE, and the flags read the")
print("classification's own end:")
# Finding 147: a declared or reused retirement is established by the record, not by the gap, so
# only a trade_ceased_only span may be held as too recent. Saxitoxin, imports 3002.90.00.12,
# sat held 116 months after its last trade while the concordance named its successor.
_held_wrong = [(r["flow"], r["retiring_code"], r["retirement_basis"]) for r in _all_rows
               if r["too_recent_to_call"] == "yes"
               and r["retirement_basis"] != "trade_ceased_only"]
record("a declared or reused retirement is never held on silence",
       not _held_wrong,
       "%d held row(s), every one trade_ceased_only"
       % sum(1 for r in _all_rows if r["too_recent_to_call"] == "yes")
       if not _held_wrong else "held on a settled basis: %s" % _held_wrong)
_probe_hold = [dict(r) for r in _all_rows if r["too_recent_to_call"] == "yes"][:1]
_probe_hold[0]["retirement_basis"] = "declared"
record("the hold control objects when a declared row is held",
       [(_probe_hold[0]["flow"], _probe_hold[0]["retiring_code"], "declared")]
       == [(r["flow"], r["retiring_code"], r["retirement_basis"]) for r in _probe_hold
           if r["too_recent_to_call"] == "yes"
           and r["retirement_basis"] != "trade_ceased_only"],
       "doctoring one held row to declared is caught")

# Finding 146: the boundary and concordance flags are a union of the last traded month and the
# life-owned declared termination, because money stops before a classification does. Stage 1b
# matches the concordance by the declared year and Stage 1c holds on the same union; the flags
# were the remaining place reading the trading month alone, and twelve published rows read
# adjudicated-yes and boundary-no at once.
_note_of = {}
for _flow in ("imports", "exports"):
    for _r in _inv_records[_flow]:
        if _r["stated_termination"] and _r.get("stated_termination_is_this_life") != "no":
            _note_of[(_flow, _r["hs_code"], _r["last_period"])] = _r["stated_termination"]
_flag_wrong = []
for _r in _all_rows:
    _declared = (_note_of.get((_r["flow"], _r["retiring_code"], _r["last_period"]), "")
                 if _r["retirement_basis"] == "declared" else "")
    _end = _declared if _declared and _declared >= _r["last_period"] else _r["last_period"]
    _want_bnd = "yes" if (_r["last_period"] in stage.HS_REVISIONS
                          or _end in stage.HS_REVISIONS) else "no"
    _want_cov = "yes" if (_r["last_period"] in stage.CBSA_COVERED_BOUNDARIES
                          or _end in stage.CBSA_COVERED_BOUNDARIES) else "no"
    if (_r["at_hs_revision_boundary"] != _want_bnd
            or _r["cbsa_concordance_covers"] != _want_cov):
        _flag_wrong.append((_r["flow"], _r["retiring_code"], _r["last_period"]))
record("the boundary and concordance flags read the union of trade end and declared end",
       not _flag_wrong,
       "%d row(s) rebuilt from the inventory's own notes" % len(_all_rows)
       if not _flag_wrong else "%d differ: %s" % (len(_flag_wrong), _flag_wrong[:4]))
_probe_flag = [dict(r) for r in _all_rows if r["at_hs_revision_boundary"] == "yes"][:1]
_probe_flag[0]["at_hs_revision_boundary"] = "no"
_pf = _probe_flag[0]
_pf_declared = (_note_of.get((_pf["flow"], _pf["retiring_code"], _pf["last_period"]), "")
                if _pf["retirement_basis"] == "declared" else "")
_pf_end = (_pf_declared if _pf_declared and _pf_declared >= _pf["last_period"]
           else _pf["last_period"])
record("the flag control objects when a boundary flag is bent",
       ("yes" if (_pf["last_period"] in stage.HS_REVISIONS
                  or _pf_end in stage.HS_REVISIONS) else "no")
       != _pf["at_hs_revision_boundary"],
       "bending one row's at_hs_revision_boundary to no is caught")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if failed:
    print()
    print("Stage 1a is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 1a is validated. Every retirement is listed once and every candidate really traded.")
