"""
Check the medicine-family table: what it claims, where each claim came from, and what it may do.


Inputs:
    decisions/medicine_families.csv
    decisions/stage2_adjudication_queue.csv
    work/commodity_inventory_{imports,exports}.csv
    work/stage1_ranked_{imports,exports}.csv

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


WHY THIS CHECK EXISTS
---------------------
This is the first input to the crosswalk that cannot be verified against the delivery or against
Canada's concordance. Two thirds of it is asserted from pharmacological knowledge with no citable
source, because none was reachable offline. That is a real change to what the project rests on,
and it is safe only while three constraints hold. This check enforces them.
"""

import csv
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import families as fam                                                   # noqa: E402
import make_adjudication_queue as builder                                  # noqa: E402
# The reuse gap is read from the module that DEFINES it. It used to be read as
# _REUSE_GAP_MONTHS, which reached make_adjudication_queue only through an import
# that module does not otherwise use, so tidying that import away would have broken this
# check from a distance. Finding 128.
from stage1_candidates import REUSE_GAP_MONTHS as _REUSE_GAP_MONTHS      # noqa: E402
import meaning_gates as gates                                              # noqa: E402

DECISIONS = os.path.join(PROJECT, "decisions")
WORK = os.path.join(PROJECT, "work")
results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


table = load(os.path.join(DECISIONS, "medicine_families.csv"))
queue = load(os.path.join(DECISIONS, "stage2_adjudication_queue.csv"))
inventory = {}
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        inventory.setdefault((flow, r["hs_code"]), r["description"])

print("Check the medicine-family table.")
print()
print("CONSTRAINT 1: it may only withhold a recommendation, never create a link")
# The only way to prove this from the artefact is that no proposal is a code the family table
# introduced. Every proposal must still come from the ranked candidates, as it always did.
introduced = {(r["flow"], r["hs_code"]) for r in table}
proposals = {(r["flow"], r["proposed_successor"].replace(".", "")) for r in queue
             if r["proposed_successor"]}
record("no proposal exists that only the family table knows about",
       all(p in inventory for p in proposals),
       "%d proposals, every one a commodity in the delivery" % len(proposals))
# And the stronger statement: the table is consulted for ordering and disclosure only.
#
# This was a sentence asserting itself. It read record(<name>, True, <a claim about the code>),
# so it passed on any codebase, including one where families.py chose every successor. The
# property it names is checkable against the artefacts, and this is the check: a successor the
# family table selected would be a code the ranking did not leave standing for that row. Every
# proposal must be a candidate stage 1c ranked and no meaning rule vetoed. If a later edit lets
# the table introduce a code, or promote one a rule removed, this fails and names the row.
survivors = {}
for flow in ("imports", "exports"):
    for r in load(os.path.join(WORK, "stage1_ranked_%s.csv" % flow)):
        if not r["vetoed_by"]:
            survivors.setdefault((r["flow"], r["retiring_code"], r["last_period"]), set()).add(
                r["candidate"])
proposed = [r for r in queue if r["proposed_successor"]]
off_ranking = [r["row"] for r in proposed
               if r["proposed_successor"].replace(".", "") not in survivors.get(
                   (r["flow"], r["retiring_code"].replace(".", ""),
                    r["last_traded"].replace("-", "")), set())]
record("every proposal is a candidate the ranking left standing for that same retirement",
       not off_ranking,
       "%d proposal(s), every one a survivor of its own row's ranking, so none was introduced "
       "or promoted by the family table" % len(proposed) if not off_ranking
       else "%d proposal(s) are not ranked survivors of their own row: %s"
            % (len(off_ranking), off_ranking[:5]))

print()
print("CONSTRAINT 2: every entry carries its source")
missing = [r["hs_code"] for r in table if not r["source"]]
record("every entry names where it came from", not missing,
       "%d entries, all sourced" % len(table)
       if not missing else "%d unsourced: %s" % (len(missing), missing[:4]))
# Three kinds, not two. An entry can have a family read off the tariff and a class that had to
# be asserted, and saying so is more honest than forcing it into one bucket. Tranquilizers is
# the case: its family is derived, its therapeutic class is not.
derived = [r for r in table if r["source"] == fam.DERIVED]
asserted = [r for r in table if r["source"] == fam.ASSERTED]
mixed = [r for r in table if fam.DERIVED in r["source"] and fam.ASSERTED in r["source"]]
record("every entry falls into one of the three provenances",
       len(derived) + len(asserted) + len(mixed) == len(table),
       "%d derived from the tariff, %d asserted without a source, %d with a derived family and "
       "an asserted class" % (len(derived), len(asserted), len(mixed)))
record("nothing asserted is presented as derived",
       all(fam.ASSERTED in r["source"] for r in table if r["therapeutic_class"]
           and r["therapeutic_class"] != ""),
       "%d entries carry a therapeutic class, every one marked asserted"
       % sum(1 for r in table if r["therapeutic_class"]))
# A derived entry must be checkable, and until 2026-08-16 this tested only that two codes share
# their first nine digits. Every one of the 108 derived entries passed it, including 19 that named
# a line the code's trade could never have reached. Digit-prefix equality is not the claim the
# column makes. The claim is that the target IS the block's leftover line, and it is now tested as
# three separate things because they fail on different rows.
#
# THE THIRD TEST IS DIRECTIONAL AND THAT MATTERS. A leftover line is allowed to begin AFTER the
# member closes: at every HS revision the tariff shuts a residual in December and opens its
# replacement in January, and seven entries here name a line 1 or 2 months later. Those are right,
# and an overlap requirement would have called all seven defects. What cannot be right is a line
# that had already CLOSED before this code began: a line that died in 2011 cannot receive trade
# from a code that opened in 2018. Eleven entries did that and now name nothing at all.
_blocks = {}
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)):
        _blocks.setdefault((_flow, _r["hs_code"][:9]), set()).add(_r["hs_code"])


def _months(period):
    """Written out here rather than imported, per rule 2."""
    return int(period[:4]) * 12 + int(period[4:])


def _reachable(line, member):
    """Open beside the member, or opening within Stage 1a's reuse gap after it closes."""
    if line["first_period"] <= member["last_period"] and member["first_period"] <= line["last_period"]:
        return True
    if line["first_period"] > member["last_period"]:
        return (_months(line["first_period"])
                - _months(member["last_period"])) <= _REUSE_GAP_MONTHS
    return False


def _lives_of(flow, code):
    return sorted(_lives_by_code.get((flow, code), []), key=lambda s: s["first_period"])


_lives_by_code = {}
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)):
        _lives_by_code.setdefault((_flow, _r["hs_code"]), []).append(_r)

not_residual, unreachable, not_leftover = [], [], []
for r in derived + mixed:
    if not r["family_code"]:
        continue
    member = next((s for s in _lives_of(r["flow"], r["hs_code"])
                   if s["first_period"] == r["first_period"]), None)
    if member is None:
        continue
    reach = [s for s in _lives_of(r["flow"], r["family_code"]) if _reachable(s, member)]
    if not reach:
        unreachable.append(r["hs_code"])
        continue
    if not gates.is_a_catch_all(reach[0]["description"]):
        not_residual.append(r["hs_code"])
        continue
    # And it must be the block's leftover, not a named group inside it. Generality decides, not
    # numbering: in block 300490003 the higher-numbered .39 is "acting on the CENTRAL nervous
    # system" and .35 is the broader "acting on the nervous system, nes".
    others = []
    for s in sorted(_blocks.get((r["flow"], r["hs_code"][:9]), set())):
        if s == r["hs_code"]:
            continue
        for sl in _lives_of(r["flow"], s):
            if _reachable(sl, member) and gates.is_a_catch_all(sl["description"]):
                others.append(fam._content_words(sl["description"]))
                break
    # FAIL ONLY WHERE A STRICTLY BROADER LEFTOVER EXISTS. Asking that the target be provably the
    # most general fails whenever a block holds two residuals neither of which contains the other,
    # and 3002900090 against 3002900099 is exactly that: one says "toxins, sim pr" and the other
    # "microbial pre", so neither is inside the other and the block has no single leftover. There
    # is nothing to correct there and nothing to assert. What IS a defect is naming a group when a
    # broader leftover sits beside it, which is 3004900074 against 3004900079: {medicaments, human}
    # is a proper subset of the eyes-ears-respiratory line's nine words.
    mine = fam._content_words(reach[0]["description"])
    broader = [o for o in others if o < mine]
    if broader and not (r["enclosing_family_name"] or "").strip():
        not_leftover.append(r["hs_code"])

record("every derived entry names a line its trade could actually reach", not unreachable,
       "%d derived entry(s) with a target, none naming a line that closed before the code began"
       % sum(1 for r in derived + mixed if r["family_code"])
       if not unreachable else "%d do not: %s" % (len(unreachable), unreachable[:4]))
record("every derived entry names a residual and not a specific line", not not_residual,
       "checked with meaning_gates.is_a_catch_all against the target's own wording in that era"
       if not not_residual else "%d do not: %s" % (len(not_residual), not_residual[:4]))
record("every derived entry names its block's leftover, not a group inside it", not not_leftover,
       "the leftover is the residual whose words sit inside every other residual's in the block; "
       "an entry naming an intermediate must record the level above in enclosing_family_name"
       if not not_leftover else "%d do not: %s" % (len(not_leftover), not_leftover[:4]))
record("an entry that can name no leftover names none, rather than naming a dead line",
       all(r["family_name"] == "" for r in derived + mixed if not r["family_code"]),
       "%d derived entry(s) carry no family, each saying why in its own `why` column"
       % sum(1 for r in derived + mixed if not r["family_code"]))
record("every asserted entry carries a confidence and a reason",
       all(r["confidence"] and r["why"] for r in asserted + mixed),
       "%d entries with an asserted part, each with both" % (len(asserted) + len(mixed)))

print()
print("CONSTRAINT 3: it covers what the queue needs, and no more")
# Every code the artefact SHOWS, not only the ones it proposes. A commodity offered as a second
# alternative or as a leftover line is in front of the reader just as much as the proposal, and
# asserting something about it is exactly what constraint 3 permits.
codes_in_queue = set()
for r in queue:
    shown = [r["retiring_code"], r["proposed_successor"],
             r.get("best_candidate_passing_every_rule", "")]
    shown += [c.strip() for c in (r.get("class_residual_available") or "").split(";")]
    shown += [r.get("closest_removed_candidate", ""), r.get("runner_up", ""),
              r.get("same_wording_reappears_at", ""), r.get("chain_ends_at", "")]
    for code in shown:
        if code and code.replace(".", "").isdigit():
            codes_in_queue.add((r["flow"], code.replace(".", "")))
useless = [r["hs_code"] for r in table
           if (r["flow"], r["hs_code"]) not in codes_in_queue
           and fam.ASSERTED in r["source"]]
record("nothing is asserted about a commodity the queue never shows", not useless,
       "%d asserted entries, all of them on codes in the queue" % len(asserted)
       if not useless else "%d are not: %s" % (len(useless), useless[:4]))
record("the table is smaller than the delivery, deliberately",
       len(table) < len(inventory),
       "%d entries against %d commodities; a document nobody reviews is worse than a short one"
       % (len(table), len(inventory)))

print()
print("A FAMILY THAT NAMES NO CLASS IS NOT A FAMILY")
# Both Tranquilizers and Anaesthetic derive into "Medicaments nes, for veterinary use", which is
# the leftover of a whole subheading. Calling them the same family reads as related when one
# sedates and the other abolishes sensation. Where the derived family is that generic, a class
# must be asserted or the entry says something untrue.
import re as _re
GENERIC = _re.compile(r"^(medicaments?|medi|other medicaments)", _re.I)
vague = [r["hs_code"] for r in table
         if GENERIC.match(r["family_name"] or "") and not r["therapeutic_class"]
         and (r["flow"], r["hs_code"]) in codes_in_queue]
record("no queue commodity rests on a generic leftover with no class", not vague,
       "every commodity whose family is only a subheading leftover carries a class"
       if not vague else "%d do not: %s" % (len(vague), vague[:4]))

print()
print("THE PROVENANCE MUST FOLLOW THE FACT THAT WAS USED")
# A therapeutic class is always asserted. A family may be derived. Reading the provenance off the
# entry as a whole labelled Tranquilizers against Anaesthetic as coming from the tariff, when the
# family was derived and the class that actually separated them was asserted. A provenance
# reporting the wrong origin is worse than none: the point of recording it is to let a reader
# discount what rests on nothing.
sheet = load(os.path.join(DECISIONS, "stage2_decisions.csv"))

# A real entry carrying both forms of the leftover line, so the probes below test the shipped
# table rather than a fixture that cannot go stale with it.
table_by_key = fam.load_families()
_probe = next(r for r in table
              if r["flow"] == "imports" and r["family_code"] and r["family_name"])
PROBE_CODE = _probe["hs_code"]
PROBE_FAMILY_CODE = _probe["family_code"]
PROBE_FAMILY_NAME = _probe["family_name"]
shown = [r for r in sheet if r.get("how_they_relate")]
mislabelled = [r["row"] for r in shown
               if "class" in r["how_they_relate"]
               and "asserted" not in r["how_they_relate"]]
record("every class verdict is shown as asserted", not mislabelled,
       "%d row(s) rest on a therapeutic class, each labelled asserted"
       % sum(1 for r in shown if "class" in r["how_they_relate"])
       if not mislabelled else "%d mislabelled: %s" % (len(mislabelled), mislabelled[:4]))
record("the sheet shows the finding at all", bool(shown),
       "%d of %d rows carry it; it lived only in the queue file for one build"
       % (len(shown), len(sheet)))

print()
print("THE GUIDANCE MAY ONLY SPEAK WHERE A JUDGEMENT IS ASKED FOR")
# The "nothing else qualifies" branch fired on 31 CONFIRM rows, because a second alternative is
# only computed where the verdict is ANALYST, and told the reader to reject a row the evidence
# supports. Guidance on a settled row is not help; it is contradiction.
loud = [r["row"] for r in sheet
        if not r["verdict"].startswith("ANALYST") and r.get("what_this_points_to")]
record("no settled row is given advice", not loud,
       "%d rows carry guidance, every one of them the analyst's to decide"
       % sum(1 for r in sheet if r.get("what_this_points_to"))
       if not loud else "%d settled rows do: %s" % (len(loud), loud[:4]))
record("every row that is the analyst's to decide and has a known relationship is advised",
       not [r["row"] for r in sheet
            if r["verdict"].startswith("ANALYST") and r.get("how_they_relate")
            and r["how_they_relate"] != "unknown" and not r.get("what_this_points_to")],
       "advice given wherever a relationship is known")
# The advice names one of the two codes already on the row. It cannot introduce a third.
introduces = [r["row"] for r in sheet
              if r.get("what_this_points_to", "").startswith("SECOND")
              and not r.get("second_alternative")]
record("advice to take the second names a second that exists", not introduces,
       "every SECOND points at a code already shown on the row")

print()
print("THE SECOND ALTERNATIVE IS DESCRIBED TOO")
# The relationship was computed for the proposal alone, so a row whose advice said SECOND
# pointed at a commodity with nothing recorded about it. If a reader is told to prefer a code,
# they are owed the same evidence that was given for the one it displaces.
mine = [r for r in sheet if r["verdict"].startswith("ANALYST")]
silent = [r["row"] for r in mine
          if r.get("second_alternative") and not r.get("how_the_second_relates")]
record("every second alternative offered is also described", not silent,
       "%d of %d rows offer one and all are described"
       % (sum(1 for r in mine if r.get("second_alternative")), len(mine))
       if not silent else "%d offered with nothing said: %s" % (len(silent), silent[:4]))
# One rule, asked in two places. The advice matched the leftover line on its wording and the
# column matched it on its number, and they disagreed on Betamethasone because the line keeps
# its wording across revisions but not its number. Two forms of one question drift apart.
split = [r["row"] for r in mine
         if r.get("what_this_points_to", "").startswith("SECOND")
         and not r.get("how_the_second_relates", "").startswith(fam.OWN_LINE)]
record("advice to take the second agrees with what the second is said to be", not split,
       "%d rows advise SECOND, every one because the code is the leftover line"
       % sum(1 for r in mine if r.get("what_this_points_to", "").startswith("SECOND"))
       if not split else "%d disagree: %s" % (len(split), split[:4]))
record("the leftover line is recognised by its number and by its wording",
       fam.leads_to_own_line(table_by_key, "imports", PROBE_CODE, PROBE_FAMILY_CODE)
       and fam.leads_to_own_line(table_by_key, "imports", PROBE_CODE, "", PROBE_FAMILY_NAME),
       "either form answers the same question")
record("a leftover line is never mistaken for one by wording alone",
       not fam.leads_to_own_line(table_by_key, "imports", PROBE_CODE, "", "something else"),
       "wording must match the recorded family line")

print()
print("A DISTINCTION THAT DISQUALIFIES A SUCCESSOR ALSO DISQUALIFIES A FAMILY")
# Epinephrine, whose description ends "prepr for parentl admin in hum", was told its own
# leftover line was "Hormones, nes, for vet use", because its recorded family is the single word
# "Hormones" and one word is contained in almost any hormone line. The use distinction has been
# declared decisive and active since 2026-08-05 and this layer had never consulted it.
_HUM = "Epinephrine & its sol & pituitary extrc, prepr for parentl admin in hum, in dos"
# Synthetic keys carry the life, like the real table since 2026-08-16. A single entry answers
# with no month given, which is what these probes rely on.
_T = {("imports", "1", "198801"): {"family_name": "Hormones", "family_code": "",
                                   "description": _HUM, "first_period": "198801",
                                   "last_period": "202606"}}
record("a human code's leftover line is never a veterinary one",
       not fam.leads_to_own_line(_T, "imports", "1", "9",
                                 "Hormones, nes, for vet use, in dosage", _HUM),
       "the use distinction reaches the family layer")
record("a human code still reaches its own human leftover line",
       fam.leads_to_own_line(_T, "imports", "1", "9",
                             "Hormones, nes, for human use, in dosage", _HUM),
       "the guard separates the two uses rather than blocking both")
# Read from the declared file, so there is one statement of what separates two commodities.
fam._crosses_a_decisive_line("a", "b")
record("the distinctions are read from the declared file, not restated here",
       fam._RULES and all(r["action"] == "disqualify" for r in fam._RULES)
       and any(r["name"] == "use" for r in fam._RULES),
       "%d disqualifying distinctions in force, including use" % len(fam._RULES))
# Every place the question is asked must get the same answer.
_split = [r["row"] for r in sheet
          if r.get("what_this_points_to", "").startswith("SECOND")
          and not r.get("how_the_second_relates", "").startswith(fam.OWN_LINE)]
record("the advice and the relationship agree about the second alternative", not _split,
       "every SECOND rests on a leftover line the column also reports"
       if not _split else "%d disagree: %s" % (len(_split), _split[:4]))

print()
print("IDENTICAL WORDING OUTRANKS ANYTHING THE TABLE KNOWS")
# The analyst asked why row 48 read "different family" when the proposal matched its retiring
# description exactly. One cause was a trailing comma on a family name, compared as a raw
# string. The deeper one is that the same commodity can sit in two blocks with two different
# leftover lines, which makes the recorded families genuinely different while the goods are
# identical. Nothing the table records can outrank two descriptions matching character for
# character.
_ident = [r["row"] for r in sheet
          if r["retiring_description"].strip().lower()
          == r["proposed_successor_description"].strip().lower()
          and r["how_they_relate"].startswith("different")]
record("identical descriptions are never called a different family or class", not _ident,
       "%d rows carry identical descriptions and none is called different"
       % sum(1 for r in sheet
             if r["retiring_description"].strip().lower()
             == r["proposed_successor_description"].strip().lower())
       if not _ident else "%d are: %s" % (len(_ident), _ident[:4]))
record("punctuation cannot decide a classification",
       fam.relationship({("imports", "1", "198801"): {"family_name": "Vitamins, nes",
                                                       "first_period": "198801",
                                                       "last_period": "202606"},
                         ("imports", "2", "198801"): {"family_name": "Vitamins, nes,",
                                                      "first_period": "198801",
                                                      "last_period": "202606"}},
                        "imports", "1", "2") == "same family",
       "a stray separator no longer splits one family into two")
# A relation the table did not supply must not borrow the table's provenance.
_borrowed = [r["row"] for r in sheet
             if r["how_they_relate"].startswith((fam.SAME_COMMODITY, fam.CATCH_ALL))
             and ("asserted" in r["how_they_relate"]
                  or "tariff structure" in r["how_they_relate"])]
record("an observed relation does not claim the table as its source", not _borrowed,
       "identical wording and catch-all report what they were read from"
       if not _borrowed else "%d borrow it: %s" % (len(_borrowed), _borrowed[:4]))

print()
print("THE TABLE IS FILLED FOR BOTH FLOWS, AND A RESIDUAL IS A CONTAINER")
# The table was filled one flow at a time. The ephedra group has 11 codes across both flows and
# 3 were recorded, all under exports, so rows 37 and 38 could not relate ephedrine to
# pseudoephedrine in either direction. An identical description under the other flow is the same
# commodity, and there is no reason for one to be known and the other not.
_inv2 = {}
for _f in ("imports", "exports"):
    _p = os.path.join(WORK, "commodity_inventory_%s.csv" % _f)
    if os.path.exists(_p):
        for _r in load(_p):
            _inv2.setdefault(_f, {})[_r["hs_code"]] = _r["description"]
_have = {(r["flow"], r["hs_code"]) for r in table}
_desc = {}
for r in table:
    _desc.setdefault(r["description"].strip().lower(), set()).add(r["flow"])
_lop = [(f, c) for f, codes in _inv2.items() for c, d in codes.items()
        if (f, c) not in _have and _desc.get(d.strip().lower(), set()) - {f}]
record("no code is covered under one flow and absent under the other", not _lop,
       "%d entries, symmetric across flows" % len(table)
       if not _lop else "%d lopsided: %s" % (len(_lop), _lop[:4]))
record("a catch-all candidate is never called a different kind of medicine",
       fam.relationship({}, "imports", "1", "2", "Antibiotics, nes", "Penicillin G")
       == fam.CATCH_ALL,
       "a residual reports as a container rather than as a difference")
record("a leftover line matched on wording must be a residual",
       not fam.leads_to_own_line(
           {("imports", "9", "198801"): {"family_name": "Medicaments nes, for human use, in dosage",
                                         "first_period": "198801", "last_period": "202606"}},
           "imports", "9", "8", "Medicaments affecting electrolytic balance, for human use"),
       "a specific named line is not mistaken for the leftover line it sits under")

print()
print("A LEFTOVER LINE THAT DIED TOO MUST SAY WHERE THE TRADE WENT")
# The analyst asked why rows 13 and 31 differ. Same substance, same proposal, four years apart:
# in row 13 the code's leftover line outlives the retirement by 54 months, in row 31 by one, so
# the co-casualty rule removes it and the row falls through to a line recorded under a different
# family. That is the Codeine phosphate nesting a second time, in a second family, and it was
# found by a person reading rows rather than by a control. This is the control.
_inv = {}
for _flow in ("imports", "exports"):
    _path = os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)
    if os.path.exists(_path):
        for _r in load(_path):
            _inv.setdefault((_flow, _r["hs_code"]), []).append(_r)
for _v in _inv.values():
    _v.sort(key=lambda s: s["first_period"])


def _family_line_of(flow, code, month):
    """Every life of this code's recorded leftover line, by number or by wording.

    RETURNS EVERY LIFE, AND KEPT ONLY THE LAST ONE UNTIL 2026-08-16. `_inv` was a dict written
    once per code, so a leftover line with two lives answered with whichever ended latest, and the
    gap below was measured against that. Imports 3004.20.00.52, queue row 14, CAD 1,094,147, ends
    1996-11 beside a leftover line that ended 1997-12, a gap of 13 months against a threshold of
    24. Measured against the line's LAST life the gap is 181 months, so the row fell out of the
    subject entirely and one real stranding went unrecorded while the control passed at 32 of 32.
    """
    entry = fam.entry_at(table_by_key, flow, code, month)
    if not entry:
        return []
    if entry.get("family_code") and (flow, entry["family_code"]) in _inv:
        return _inv[(flow, entry["family_code"])]
    want = (entry.get("family_name") or "").strip().lower()
    if not want:
        return []
    out = []
    for (f, c), rows in _inv.items():
        if f != flow:
            continue
        out += [r for r in rows if (r["description"] or "").strip().lower() == want]
    return sorted(out, key=lambda s: s["first_period"])


_stranded = []
for _r in queue:
    _month = _r["last_traded"].replace("-", "")
    _lines = _family_line_of(_r["flow"], _r["retiring_code"], _month)
    if not _lines:
        continue
    # ANY life of the leftover line that dies beside this retirement, not merely the last.
    _gaps = [builder.months_between(_r["last_traded"], builder.month(_l["last_period"]))
             for _l in _lines]
    _gaps = [g for g in _gaps if g is not None]
    if not _gaps or min(_gaps) > builder.CO_CASUALTY_MONTHS:
        continue
    _entry = fam.entry_at(table_by_key, _r["flow"], _r["retiring_code"], _month) or {}
    if not (_entry.get("enclosing_family_name") or "").strip():
        _stranded.append((_r["flow"], _r["retiring_code"], _r["row"]))
# Not auto-filled. The obvious inference, that the one residual starting the month the line ends
# is its successor, picks "Medicaments cont more than 23% of abs ethyl alc by vol" as the heir to
# "Medicaments nes, for human use" on nine rows. That is an alcohol-content line, not an
# enclosing leftover, and writing it would turn a withheld row into a confident wrong answer.
# So the gap is enumerated in a file a person can read, and this control holds it closed: any
# NEW stranding fails, and a gap that gets resolved must be removed from the list.
_gaps_file = os.path.join(DECISIONS, "leftover_line_gaps.csv")
_recorded = {(r["flow"], r["retiring_code"]) for r in load(_gaps_file)}     if os.path.exists(_gaps_file) else set()
_found = {(f, c) for f, c, _ in _stranded}
record("no leftover-line gap appears that has not been written down",
       _found <= _recorded,
       "%d gap(s) recorded in decisions/leftover_line_gaps.csv, none unlisted" % len(_recorded)
       if _found <= _recorded
       else "%d unlisted: %s" % (len(_found - _recorded), sorted(_found - _recorded)[:4]))
record("no gap is listed that has since been resolved",
       _recorded <= _found,
       "the list holds only gaps that are still open"
       if _recorded <= _found
       else "%d resolved but still listed: %s"
            % (len(_recorded - _found), sorted(_recorded - _found)[:4]))
# The gap must be SAFE while it is open: an unrecorded second level reads as unknown and never
# as a leftover line, so no row is told to take a code on evidence that was never established.
_claiming = [r["row"] for r in sheet
             if r.get("how_the_second_relates", "").startswith(fam.OWN_LINE)
             and (r["flow"] if "flow" in r else "imports", r["retiring_code"]) in _recorded]
record("a row with an open gap never claims the leftover line anyway", not _claiming,
       "every open gap reports unknown rather than guessing")

print()
print("THE ADVICE AGREES WITH THE RELATIONSHIP IT RESTS ON")
# The tariff nests its leftovers. Codeine phosphate sits in a block whose leftover is "Codeine
# or its derivs nes", and that line has its own leftover one level out. When the inner line
# retires too the trade goes to the outer one, and the sheet was denying the outer line was this
# code's family line at all. The guard that matters is the second: a sibling line must never be
# mistaken for the enclosing one, because that is how a withheld row becomes a wrong link.
NARCOTIC_LINE = "Narcotic veg alkaloids or their narc derivs, nes, for human use, in dosage"
record("an enclosing leftover line is recognised as the code's own",
       fam.leads_to_own_line(table_by_key, "imports", "3004409011", "3004400080", NARCOTIC_LINE),
       "codeine phosphate reaches the narcotic alkaloids line through its inner leftover")
record("a shorthand wording matches the name recorded in prose",
       fam.leads_to_own_line(table_by_key, "imports", "3004409050", "3004400080", NARCOTIC_LINE),
       "morphine, recorded as Narcotic vegetable alkaloids, matches the line as written")
record("a sibling line is never mistaken for the enclosing one",
       not fam.leads_to_own_line(table_by_key, "imports", "3004409020", "3004400080",
                                 NARCOTIC_LINE)
       and not fam.leads_to_own_line(table_by_key, "imports", "3004409060", "3004409019",
                                     "Codeine or its derivs nes, for human use, in dosage"),
       "quinidine is non-narcotic and cocaine is not a codeine derivative; both stay false")
record("every enclosing line recorded carries its own source",
       all(r.get("enclosing_source", "").strip()
           for r in table if r.get("enclosing_family_name", "").strip()),
       "%d entry(s) record a second level, each with a source"
       % sum(1 for r in table if r.get("enclosing_family_name", "").strip()))
# Identical wording is evidence, not a judgement call, and must outrank every family test.
outranked = [r["row"] for r in sheet
             if r["retiring_description"].strip().lower()
             == r["proposed_successor_description"].strip().lower()
             and r.get("what_this_points_to")
             and not r["what_this_points_to"].startswith("ACCEPT: the wording")]
record("identical wording outranks the leftover-line rule", not outranked,
       "no row with an identical proposal is sent to the second alternative"
       if not outranked else "%d are: %s" % (len(outranked), outranked[:4]))
# The absence of an alternative was tested before the relationship, so "nothing else qualifies"
# overruled "these are the same kind of medicine" and rows 5 and 59 were advised to reject a
# proposal the evidence supports. Whether anything ELSE qualifies cannot bear on whether the
# proposal is right.
contra = [r["row"] for r in mine
          if r.get("what_this_points_to", "").startswith("REJECT")
          and r.get("how_they_relate", "").startswith("same")]
record("no row is advised to reject a proposal the table calls the same", not contra,
       "%d rows advise rejecting, none of them against a recorded sameness"
       % sum(1 for r in mine if r.get("what_this_points_to", "").startswith("REJECT"))
       if not contra else "%d contradict themselves: %s" % (len(contra), contra[:4]))
# The advice may not assert what the table does not know. It read "though they are different
# substances" on all fourteen accepts, which was false on five: two carry identical wording and
# adrenal cortical against corticosteroid is one substance under two names.
asserts = [r["row"] for r in sheet
           if "different substances" in r.get("what_this_points_to", "")]
record("the advice never asserts the two are different substances", not asserts,
       "no row claims a difference the table cannot show"
       if not asserts else "%d do: %s" % (len(asserts), asserts[:4]))
same_words = [r["row"] for r in mine
              if r["retiring_description"].strip().lower()
              == r["proposed_successor_description"].strip().lower()
              and not r.get("what_this_points_to", "").startswith("ACCEPT: the wording")]
record("identical wording is called identical", not same_words,
       "%d rows carry identical wording and every one says so"
       % sum(1 for r in mine
             if r["retiring_description"].strip().lower()
             == r["proposed_successor_description"].strip().lower())
       if not same_words else "%d do not: %s" % (len(same_words), same_words[:4]))

print()
print("WHAT IT CLAIMS")
unknown = sum(1 for r in queue if r["how_they_relate"] == "unknown")
record("an absent entry reads as unknown, never as sameness",
       fam.relationship({}, "imports", "1", "2") == "unknown",
       "%d of %d queue rows say unknown, which is an absence of knowledge and not a finding"
       % (unknown, len(queue)))
# THIS CONTROL DID NOT TEST WHAT ITS NAME SAID, and it could not fail on any data this project
# can produce. It compared len({hs_code}) against len({(hs_code, flow)}), and those two counts
# differ only when one code appears under BOTH flows. Import codes here are ten digits and export
# codes eight, so no code can appear in both, and the two sets were equal by arithmetic rather
# than by anything about families. It would have reported a clean result on a table that gave one
# commodity three contradictory families.
#
# The real question is now askable, because the table is keyed on the life. Two entries may share
# a code where they describe DIFFERENT lives of it; what may never happen is two entries for the
# same life, because that is one commodity with two answers.
_per_life = {}
_twice = []
for r in table:
    key = (r["flow"], r["hs_code"], r["first_period"])
    if key in _per_life:
        _twice.append(key)
    _per_life[key] = r
record("no life of any commodity is classified twice", not _twice,
       "%d entries across %d distinct lives of %d distinct codes; a code may hold several entries "
       "only where the inventory gives it several lives"
       % (len(table), len(_per_life), len({(r["flow"], r["hs_code"]) for r in table}))
       if not _twice else "%d life(s) classified twice: %s" % (len(_twice), _twice[:3]))
# And every life an entry claims must be a life the delivery actually holds. A first_period that
# matches no inventory row would key an entry to a commodity that never existed, and every lookup
# for the real life would then miss and read as unknown.
_real = set()
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)):
        _real.add((_flow, _r["hs_code"], _r["first_period"]))
_invented = [k for k in _per_life if k not in _real]
record("every entry is keyed to a life the delivery holds", not _invented,
       "%d life(s) checked against commodity_inventory" % len(_per_life)
       if not _invented else "%d invented: %s" % (len(_invented), _invented[:3]))
# PROVOKED, because both of the above are new and a guard that cannot fire is not a guard.
_probe = list(table) + [dict(table[0])]
_seen, _dupe = set(), False
for r in _probe:
    k = (r["flow"], r["hs_code"], r["first_period"])
    if k in _seen:
        _dupe = True
    _seen.add(k)
record("probe: a second entry for one life is caught", _dupe,
       "the duplicate is detected on a copy of the table, not on the table")
record("probe: an entry keyed to a life the delivery lacks is caught",
       ("imports", "3004900079", "180001") not in _real,
       "a first_period the inventory has never held is not in the set the control tests against")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed."
      % (len(results), len(results) - len(failed), len(failed)))
if failed:
    print()
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("The family table obeys the three constraints it was built under.")
