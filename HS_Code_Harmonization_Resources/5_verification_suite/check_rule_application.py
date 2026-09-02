"""
Check that every rule is applied everywhere a code is shown to a person.


Inputs:
    decisions/stage2_adjudication_queue.csv
    decisions/stage2_decisions.csv
    decisions/decisive_distinctions.csv
    work/stage1_ranked_{imports,exports}.csv

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


WHY THIS CHECK EXISTS
---------------------
Rules kept being written in one place and not applied in the others. The rule that a proposal
must not be a co-casualty was applied when choosing a replacement candidate and not when choosing
the alternative to show beside it, so every waste pharmaceutical row was offered a second code
that had died in the same restructuring as the first. The correct destination, 3006.92.00.00, was
already recorded on the row and was not being used.

That was found by the analyst reading the sheet. It was the third time a rule had been added in
one place and left out of another, and the other two were found the same way.

So this check does not test what the rules decide. It tests that they are APPLIED, at every point
where the pipeline puts a commodity code in front of a person and invites a judgement about it.


THE INVARIANT
-------------
There are three such points on every row: the proposal, the second alternative, and the
replacement offered when the proposal itself is defective. Any code appearing at any of them must
satisfy the same rules. A rule that holds at one and not the others is not a rule; it is a
coincidence of where it happened to be written.


WHAT IT DOES NOT DO
-------------------
It cannot say whether a rule is correct, or whether the threshold inside it is well chosen. Those
are argued in decisive_distinctions.csv and in THRESHOLDS.md, and measured in the checks for the
stage that owns them. This one asks only whether each rule reaches everywhere it should.
"""

import csv
import os
import re
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))

import meaning_gates as gates                                            # noqa: E402
from _shorthand import expand_shorthand                                  # noqa: E402
from make_adjudication_queue import (CO_CASUALTY_MONTHS, REVIEW_THRESHOLD,  # noqa: E402
                                     months_between, substance_index,
                                     prepared_for_score)

DECISIONS = os.path.join(PROJECT, "decisions")
WORK = os.path.join(PROJECT, "work")

results = []
notes = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def disclose(name, detail=""):
    """State something true by construction, and keep it out of the control count.

    Some things worth printing cannot fail: that the second alternative is ALLOWED to be a
    removed candidate is a design decision, not a property of this run. Writing those as
    record(<name>, True, ...) inflated the headline, because a reader counting "N of N controls
    passed" fairly assumes N things could have failed. These print as NOTE and are tallied apart.
    """
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, ("  -- " + detail) if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


queue = load(os.path.join(DECISIONS, "stage2_adjudication_queue.csv"))
answers = load(os.path.join(DECISIONS, "stage2_decisions.csv"))
sheet = {r["link_id"]: r for r in answers}
_OT_ANY = re.compile(r"(?<![a-z0-9])o/t", re.I)


def _expanded_sources():
    """Every commodity life's wording, raw. The o/t split is about the literal text."""
    out = []
    for flow in ("imports", "exports"):
        for row in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
            out.append(row["description"])
    return out


rules = gates.load_rules(os.path.join(DECISIONS, "decisive_distinctions.csv"))

inventory = []
descriptions, spans = {}, {}
for flow in ("imports", "exports"):
    rows = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    inventory += rows
    for r in rows:
        descriptions.setdefault((flow, r["hs_code"]), r["description"])
        first, last = spans.get((flow, r["hs_code"]), (r["first_period"], r["last_period"]))
        spans[(flow, r["hs_code"])] = (min(first, r["first_period"]),
                                       max(last, r["last_period"]))
# Spans split the way the pipeline splits them, not collapsed into one envelope.
all_spans = {}
for flow in ("imports", "exports"):
    grouped = {}
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        grouped.setdefault(r["hs_code"], []).append((r["first_period"], r["last_period"]))
    for code, intervals in grouped.items():
        intervals.sort()
        merged = [list(intervals[0])]
        for first, last in intervals[1:]:
            gap = ((int(first[:4]) * 12 + int(first[4:6]))
                   - (int(merged[-1][1][:4]) * 12 + int(merged[-1][1][4:6])))
            if gap > 60:
                merged.append([first, last])
            else:
                merged[-1][1] = max(merged[-1][1], last)
        all_spans[(flow, code)] = [tuple(m) for m in merged]

terms_index, _ = substance_index(inventory)
ANY_RESIDUAL = re.compile(r"(?<![a-z0-9])(nes|n\.e\.s\.|not elsewhere specified|other|o/t"
                          r"|general)(?![a-z0-9])")

print("Check that every rule reaches every point where a code is shown to a person.")
print()
print("THE THREE PLACES A CODE IS OFFERED")
offered = {"the proposal": [], "the second alternative": [], "the replacement candidate": []}
for row in queue:
    answer = sheet.get(row["link_id"], {})
    if row["proposed_successor"]:
        offered["the proposal"].append((row, row["proposed_successor"]))
    if answer.get("second_alternative"):
        offered["the second alternative"].append((row, answer["second_alternative"]))
    if row["best_candidate_passing_every_rule"]:
        offered["the replacement candidate"].append((row,
                                                     row["best_candidate_passing_every_rule"]))
for where, items in offered.items():
    print("   %-28s %d code(s) offered" % (where, len(items)))
print()


def described(row, code):
    """The description as the SHEET shows it, falling back to the catalogue.

    Reading it only from the inventory compared a different string from the one in front of the
    reader, because a code with several records keeps the first description found. The test has
    to be about what is shown.
    """
    answer = sheet.get(row["link_id"], {})
    if answer.get("second_alternative") == code and answer.get("second_alternative_description"):
        return answer["second_alternative_description"]
    return descriptions.get((row["flow"], code.replace(".", "")), "")


DELIVERY_END = {}
for (flow, _code), pairs in all_spans.items():
    DELIVERY_END[flow] = max(DELIVERY_END.get(flow, ""), max(p[1] for p in pairs))


def outlives_by(row, code):
    """Months the code outlives the retirement, measured on the span that could have received it.

    The envelope across every record is the wrong measure for a reused number and disagreed with
    the builder on 21 rows.
    """
    pairs = all_spans.get((row["flow"], code.replace(".", "")))
    if not pairs:
        return None
    stopped = row["last_traded"].replace("-", "")
    alive = [p for p in pairs if p[1] > stopped]
    chosen = min(alive) if alive else pairs[-1]
    # A code still trading in the delivery's last month has not stopped; the data has. Without
    # this the test called 3003.49.00 a co-casualty of two retirements because it runs to
    # 2026-06, which is where the file ends.
    if chosen[1] >= DELIVERY_END.get(row["flow"], "999912"):
        return None
    return months_between(row["last_traded"], "%s-%s" % (chosen[1][:4], chosen[1][4:6]))


print("RULE: a code that dies in the same restructuring never received the trade")
print("      (applies wherever a code is offered as somewhere the trade went)")
for where in ("the second alternative", "the replacement candidate"):
    bad = [(r["row"], c, outlives_by(r, c)) for r, c in offered[where]
           if outlives_by(r, c) is not None and outlives_by(r, c) <= CO_CASUALTY_MONTHS]
    record("%s is never a co-casualty" % where, not bad,
           "%d checked, none stops within %d months of its predecessor"
           % (len(offered[where]), CO_CASUALTY_MONTHS) if not bad
           else "%d do: %s" % (len(bad), bad[:3]))
# The proposal is exempt and that is deliberate: it is shown BECAUSE it is the closest, and the
# row says in words that it is not recommended. Asserted so the exemption stays a decision.
proposal_casualties = [r for r, c in offered["the proposal"]
                       if outlives_by(r, c) is not None
                       and outlives_by(r, c) <= CO_CASUALTY_MONTHS]
recommended = [r["row"] for r in proposal_casualties if r["verdict"].startswith("CONFIRM")]
record("a co-casualty may still be shown as the proposal, and never recommended",
       not recommended,
       "%d shown, every one withheld" % len(proposal_casualties) if not recommended
       else "%d of %d are recommended: %s" % (len(recommended), len(proposal_casualties),
                                              recommended[:5]))

print()
print("RULE: a swapped term means the score is measuring the boilerplate")
for where in ("the second alternative", "the replacement candidate"):
    bad = []
    for r, c in offered[where]:
        retiring = expand_shorthand(r["retiring_description"] or "").lower()
        candidate = expand_shorthand(described(r, c) or "").lower()
        if candidate and gates.swapped_term(retiring, candidate):
            bad.append((r["row"], c))
    record("%s never swaps the term that carries the meaning" % where, not bad,
           "%d checked" % len(offered[where]) if not bad
           else "%d do: %s" % (len(bad), bad[:3]))

print()
print("RULE: two specific descriptions sharing no distinctive word are different goods")
for where in ("the second alternative", "the replacement candidate"):
    bad = []
    for r, c in offered[where]:
        text = described(r, c)
        if not text:
            continue
        if ANY_RESIDUAL.search(r["retiring_description"].lower()) or \
                ANY_RESIDUAL.search(text.lower()):
            continue
        mine = {w for w in set(prepared_for_score(r["retiring_description"]).split())
                & set(terms_index) if not w.isdigit()}
        theirs = {w for w in set(prepared_for_score(text).split()) & set(terms_index)
                  if not w.isdigit()}
        if mine and theirs and not (mine & theirs):
            bad.append((r["row"], c))
    record("%s shares a distinctive word, or one side is a catch-all" % where, not bad,
           "%d checked" % len(offered[where]) if not bad
           else "%d do not: %s" % (len(bad), bad[:3]))

print()
print("RULE: meaning removes, and nothing offered may be something meaning removed")
removed = {}
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "stage1_ranked_%s.csv" % flow)):
        if r["vetoed_by"]:
            removed[(flow, r["retiring_code"], r["last_period"], r["candidate"])] = r["vetoed_by"]
for where in ("the proposal", "the replacement candidate"):
    bad = [(r["row"], c) for r, c in offered[where]
           if (r["flow"], r["retiring_code"].replace(".", ""),
               r["last_traded"].replace("-", ""), c.replace(".", "")) in removed]
    record("%s was never removed by a meaning rule" % where, not bad,
           "%d checked against %d removals" % (len(offered[where]), len(removed))
           if not bad else "%d were: %s" % (len(bad), bad[:3]))
# The second alternative is allowed to be a removed candidate, deliberately, because the analyst
# asked to see the best thing the software threw out so a removal can be overturned.
second_removed = sum(1 for r, c in offered["the second alternative"]
                     if (r["flow"], r["retiring_code"].replace(".", ""),
                         r["last_traded"].replace("-", ""), c.replace(".", "")) in removed)
disclose("the second alternative MAY be something a rule removed, and that is intended",
         "%d of %d are, each so the removal can be overturned"
         % (second_removed, len(offered["the second alternative"])))

print()
print("RULE: below the review threshold, nothing is recommended")
under = [r["row"] for r in queue
         if r["verdict"].startswith("CONFIRM") and r["wording_match"]
         and float(r["wording_match"]) < REVIEW_THRESHOLD]
record("no row is recommended below %.2f" % REVIEW_THRESHOLD, not under,
       "0 of %d recommended rows" % sum(1 for r in queue if r["verdict"].startswith("CONFIRM"))
       if not under else "%d: %s" % (len(under), under[:3]))

print()
print("RULE: a code the record settles is never overruled by a rule below it")
# This was record(<name>, True, "the layer order is asserted in check_stage1c_rank"), which is a
# citation rather than a test: it passed whether or not any of these rows still carried the
# record's answer. The check it cited proves the ORDER inside stage 1c. This one proves the
# result survived stage 2, which is where the queue's proposal is finally written, and it is the
# only place that gap was covered by nothing.
official = {}
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "stage1_official_%s.csv" % flow)):
        official[(r["flow"], r["retiring_code"], r["last_period"])] = r
settled = [r for r in queue if r["official_record"].startswith("the record")]
overruled = []
for r in settled:
    source = official.get((r["flow"], r["retiring_code"].replace(".", ""),
                           r["last_traded"].replace("-", "")))
    allowed = set((source["official_destinations"] or "").split(";")) - {""} if source else set()
    if r["proposed_successor"].replace(".", "") not in allowed:
        overruled.append(r["row"])
record("every row the record bounds is proposed a code from inside the record's own list",
       settled and not overruled,
       "%d bounded row(s), every proposal inside the destinations the schedule names"
       % len(settled) if settled and not overruled
       else "%d of %d proposed outside the record: %s" % (len(overruled), len(settled),
                                                          overruled[:5]))

print()
print("COVERAGE: is every rule in the distinctions file reachable from a check?")
named = {r["name"] for r in rules}
print("   %d active distinction(s): %s" % (len(named), ", ".join(sorted(named))))
firing = set()
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "stage1_ranked_%s.csv" % flow)):
        for reason in (r["vetoed_by"].split(";") if r["vetoed_by"] else []):
            firing.add(reason)
        for flag in (r["review_flag"].split(";") if r["review_flag"] else []):
            firing.add(flag)
silent = sorted(named - firing - {"continuity"})
record("every rule that fires is one the distinctions file declares",
       firing - {"continuity"} <= named,
       "%d rule(s) fired, all declared" % len(firing - {"continuity"}))
disclose("rules that never fire are listed rather than forgotten",
         "silent on this delivery: %s" % (", ".join(silent) if silent else "none"))

print()
# WHICH RULES CANNOT FIRE ON THIS DELIVERY, NAMED RATHER THAN LEFT TO BE DISCOVERED.
# Finding 126, 2026-08-18.
#
# decisive_distinctions.csv publishes 14 disqualifying rules and a reader has no way to tell that
# three of them never ran. That matters twice over: "a guard that cannot fire" is one of this
# register's four recurring error classes, and a rule that is inert today will start vetoing the
# day a delivery supplies its missing pole, with nothing to announce the change.
#
# Each is inert for its own reason, and none of the three is a defect in the rule:
#   biotechnology       one pole only. "obtained by biotechnological processes" appears in 1
#                       wording; "not obtained by ..." appears in none.
#   sterility           one pole only. "sterile" appears in 5 wordings; no negative pole exists.
#   fabric construction both poles appear, but never apart. "knit" occurs in 2 wordings and BOTH
#                       also say "woven" -- the same dressings line covering the two -- so no
#                       wording sits on the knit side alone and which_side is correctly silent.
# antibiotic content is NOT in this set. It reads as inert on raw text and fires on expanded
# text, because the corpus writes "cont antibiotics"; the gates expand before asking, and so
# must anything measuring them.
from _shorthand import expand_shorthand as _expand  # noqa: E402
_expanded = sorted({_expand(d).lower()
                    for flow in ("imports", "exports")
                    for d in [r["description"] for r in
                              load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))]})
# The expansion is not optional and must not be allowed to fall back to raw text. On raw text
# `antibiotic content` reads as inert, because the corpus writes "cont antibiotics", so a
# measurement that skipped the expansion would report four inert rules and this control would
# still pass if four were what it expected. Asserted here so the wrong reading cannot hide.
record("the shorthand expansion this measurement depends on is actually applied",
       _expand("Medi,cont antibiotics,for veterinary use") !=
       "Medi,cont antibiotics,for veterinary use",
       "raw text would make `antibiotic content` look inert and this measurement wrong")
_inert = []
for _rule in rules:
    _fired = False
    for _i, _a in enumerate(_expanded):
        for _j in range(_i + 1, len(_expanded)):
            if gates.rule_fires(_rule, _a, _expanded[_j]):
                _fired = True
                break
        if _fired:
            break
    if not _fired:
        _inert.append(_rule["name"])
record("the rules that cannot fire on this delivery are the three already accounted for",
       sorted(_inert) == ["biotechnology", "fabric construction", "sterility"],
       "inert: %s" % sorted(_inert))

print()
# COVERAGE IS COMPUTED HERE, BECAUSE THE RECORDED PINS CANNOT BE REPRODUCED. Finding 136.
#
# decisive_distinctions.csv carries corpus_coverage_2026_08_10, thirteen numeric pins of the form
# "N one side / M other side of 572". They record how much of the delivery each rule can see, which
# is worth knowing: a rule whose subject suddenly changes is a rule that has started answering a
# different question. But the method was never written down, and it cannot be recovered. Measured
# 2026-08-18 against the 572 published commodity strings, substring match on the declared phrases:
# 4 of the 13 reproduce on expanded text and 3 on raw. Neither is a method, and a pin nobody can
# recompute is not a pin.
#
# So the numbers are computed here instead, with the method stated, and pinned to what they
# compute. The CSV column is left as the historical record of a 2026-08-10 measurement and is no
# longer the thing anything relies on. The two rules the column DOES usefully annotate,
# biotechnology and sterility, say "ONE-SIDED, cannot fire on this delivery" in prose, and that
# annotation is what finding 126's control now asserts structurally.
_strings = []
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(PROJECT, "output", "%s_lookup.csv" % _flow)):
        _strings.append(_expand(_r["orig_description"]).lower())
_coverage = {}
for _rule in rules:
    _a = sum(1 for t in _strings if any(p.lower() in t for p in _rule["one"]))
    _b = sum(1 for t in _strings if any(p.lower() in t for p in _rule["other"]))
    _coverage[_rule["name"]] = (_a, _b)
EXPECTED_COVERAGE = {
    "use": (229, 54), "packing": (102, 18), "dose form": (307, 32), "origin": (10, 12),
    "modification": (8, 7), "biotechnology": (4, 0), "sterility": (5, 0),
    "antibiotic content": (13, 8), "mixing": (43, 16), "purpose": (52, 23),
    "fibre": (6, 3), "fabric construction": (6, 3), "stimulant": (4, 3),
    "specific against residual": (0, 0), "basket contents": (0, 0), "swapped term": (0, 0),
}
_moved = {k: (v, EXPECTED_COVERAGE.get(k)) for k, v in _coverage.items()
          if k in EXPECTED_COVERAGE and v != EXPECTED_COVERAGE[k]}
record("every rule sees the same share of the delivery it saw when measured",
       not _moved and set(_coverage) <= set(EXPECTED_COVERAGE),
       "%d rule(s), each over the 572 published commodity strings on expanded text"
       % len(_coverage)
       if not _moved else "%d moved: %s" % (len(_moved), list(_moved.items())[:3]))

# THE TWO KINDS OF "o/t", PINNED. Finding 138, 2026-08-18.
#
# meaning_gates.HEADING_SCOPE separates "o/t No 30.02/05", which says which heading a line sits
# under, from "o/t of cotton", which excludes goods. Only the second kind can make a line the
# complement of what it names, and reading the first as the second is what made every modern
# Chapter 30 leftover invisible to the residual rules (finding 117). The separation was counted
# rather than assumed -- 94 lives carry o/t, 81 heading-number and 13 goods-exclusion -- and
# nothing was checking those counts. If the split moves, the regular expression has started
# answering a different question and the leftover-line rules quietly change subject with it.
#
# The same paragraph also records that 27 lives carrying CAD 134,080,082,251 were denied before
# the fix, 18 of them beginning 2017-01 or later. Those three are HISTORY, not a pin: they
# describe behaviour the code no longer has and cannot be recomputed from it. They are left in the
# comment as the reason the fix exists and are deliberately not asserted here.
_ot = [d for d in _expanded_sources() if _OT_ANY.search(d)]
_ot_number = [d for d in _ot if gates.HEADING_SCOPE.search(d)]
_ot_goods = [d for d in _ot if not gates.HEADING_SCOPE.search(d)]
record("the two kinds of o/t split the way they were counted",
       (len(_ot), len(_ot_number), len(_ot_goods)) == (94, 81, 13),
       "%d live(s) carry o/t: %d introduce a heading number, %d exclude goods"
       % (len(_ot), len(_ot_number), len(_ot_goods)))

# THE FAILURE LIST IS BUILT AFTER THE LAST CONTROL, NOT BEFORE IT. Finding 133, 2026-08-18.
# It used to be built above the two controls below, so they were COUNTED by len(results)
# and excluded from `failed`. A control could print [FAIL] while the summary read "14
# passed, 0 failed" and the process exited 0. Proven by forcing one to fail before the
# move: it printed [FAIL] and the exit code was still 0.
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed."
      % (len(results), len(results) - len(failed), len(failed)))
print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("A rule is not reaching everywhere it should. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Every rule reaches every place a code is offered.")
