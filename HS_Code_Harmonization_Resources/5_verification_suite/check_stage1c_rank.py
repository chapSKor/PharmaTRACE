"""
Check for Stage 1c. Did meaning only veto, and did text only rank?


Inputs:
    work/stage1_ranked_{imports,exports}.csv     produced by pipeline/stage1c_rank.py
    work/stage1_review_{imports,exports}.csv
    work/stage1_official_{imports,exports}.csv   produced by pipeline/stage1b_official_record.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE TWO QUESTIONS THIS CHECK ANSWERS
--------------------------------------
Did the meaning gates stay inside their authority, which is to remove a candidate and nothing
else? And is the score the published one, computed the published way?

A gate that added, reordered or decided would be doing the job of the official record, without
the record's authority. A score computed on expanded text would be a different number from
every figure the project has published, and nothing downstream would notice.


THE SCORE IS RECOMPUTED HERE, NOT IMPORTED
--------------------------------------------
The controls rebuild SequenceMatcher over the same preparation, written out in this file. If
the stage and the check ever disagree, one of them changed.


WHY THE REVIEW QUEUE IS CHECKED FOR ORDER AND NOT FOR CONTENT
---------------------------------------------------------------
The queue is ordered by risk, not by score, so that a person meets the case most likely to be
wrong before the case that is easiest to confirm. That ordering is checkable. Whether the
person then agrees is not, and this check makes no attempt to judge it.
"""

import csv
import difflib
import itertools
import os
import re
import sys
from collections import defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(PROJECT, "work")

OUTCOMES = {"settled_by_record", "text_high", "text_review", "text_low", "all_candidates_vetoed"}
HIGH_THRESHOLD = 0.85
LOW_THRESHOLD = 0.50
# Written out here rather than imported from the stage. Rule 2: a check that reads the stage's
# own constant agrees with the stage at exactly the moments the stage is wrong.
HS_REVISION_MONTHS = {"200112", "200612", "201112", "201612", "202112"}
# Filled by both flows and asserted once after the per-flow loop. See the comment where it is
# populated: the asymmetry it guards runs between an export row and its import twin.
BOUNDED_GROUPS = {}

# The subheadings the WCO tables actually speak about, read here from the evidence file
# rather than from the stage. Since 2026-08-14 the hold releases a row the tables cover, because
# its premise -- "a correlation table could answer this and none has been extracted" -- is false
# once they are extracted. A check that did not know that would be asserting the old rule.
CORRELATED = set()
_wto = os.path.join(PROJECT, "evidence", "wto", "wto_ch30_pairs.csv")
if os.path.exists(_wto):
    with open(_wto, encoding="utf-8-sig", newline="") as _fh:
        for _r in csv.DictReader(_fh):
            CORRELATED.add(("%d12" % (int(_r["boundary_to"]) - 1),
                            "".join(c for c in _r["old_code"] if c.isdigit())))

# WHAT THE DOCUMENTS SAY ABOUT A SUBHEADING THEY GIVE NO DESTINATION FOR. Finding 101. The pairs
# file holds correlations, and a deletion notice is not one, so 3002.19 was absent from it
# entirely while the document addressed it on both tables. The two rows that turn on that sentence
# carry CAD 1,636,154,203 between them, and reading it required opening the PDF.
_STATEMENTS = os.path.join(PROJECT, "evidence", "wto", "wto_ch30_statements.csv")
STATEMENTS = []
if os.path.exists(_STATEMENTS):
    with open(_STATEMENTS, encoding="utf-8-sig", newline="") as _fh:
        STATEMENTS = list(csv.DictReader(_fh))

EXPECTED = {
    # Re-measured 2026-08-11 after five fixes. Every movement was reconciled before it was
    # pinned, because a pin updated whenever it fires is not a pin.
    #
    # imports pairs 3489 -> 3419. Entirely the concordance year fix: the 8 retirements it now
    # decides carried 78 candidates between them and now carry one each, and 78 - 8 = 70.
    # Verified separately that the span-aware pool changes no import candidate count at all.
    #
    # imports vetoed 1147 -> 1124. specific-against-residual falls to 0, because every one of
    # its 9 firings was a catch-all "nes" succession and not a complement. use falls 387 -> 363,
    # shedding pairs it separated only because the bare word "human" matched "human blood" or
    # "of human origin", which is a material and not a purpose. Checked: none of those 36 pairs
    # became a proposal.
    #
    # imports reviewed 198 -> 190, the same 8 rows the record now settles.
    #
    # exports vetoed 48 -> 47, and inside that continuity rises 32 -> 40 while use falls 16 -> 13
    # and residual falls 1 -> 0. The continuity rise is the span fix working: a reused code
    # number can no longer offer its retired span, so 3002.90.10 and 3002.90.20 stop being
    # proposed as each other's successor and 3002.90.00 is proposed for both.
    # Tiers re-measured 2026-08-11 when swapped_term arrived and review_flag was scoped to the
    # CHOSEN candidate. It had been the union over every candidate, so a flag on an also-ran
    # raised the whole row's risk; tier 1 briefly held 94 of 190 import rows and discriminated
    # nothing. Scoped correctly it holds 26, and the review file's flag count now equals the
    # artefact's, 23 imports plus 5 exports against 28 in the queue. The outcome split and the
    # veto counts are untouched, which is the proof that a review-action rule removed nothing.
    # Re-measured 2026-08-11 after the use rule learned the animal-side purpose wordings. use rises
    # 363 to 402 and every other reason is unchanged to the unit; rows with any veto rise only 20
    # of that 39, because 19 already carried a second reason. One row moves text_high to
    # text_review: 3002.10.29.20 loses the human variant it had been offered and falls back to
    # "Blood fractions, nes", which scores lower and is almost certainly right.
    # RE-MEASURED 2026-08-12 after the ranker stopped scoring candidates against wordings from
    # lives that had already closed. A candidate's wording is now the one in force when it could
    # receive the retirement, so scores moved on 314 candidate rows across 74 retirements and the
    # tiers moved with them. No rule changed and nothing new was removed on meaning: the three
    # fewer vetoes are rows where the live wording no longer trips a gate the stale wording did.
    # RE-MEASURED 2026-08-13. vetoed rises 1141 to 1145 and nothing else moves. The origin gate is
    # a phrase pair on "human origin" against "animal origin", and two import codes write it
    # "human orig", so the gate could not see its own case on them. "orig" joined the shorthand
    # expander. The four new removals are 3002.10.10.29 against 3002.10.00.42 and .49, and
    # 3002.10.21.20 and 3002.10.21.90 against 3002.10.00.29. On one commodity pair the gate was
    # already firing for the spelled-out twin 3002.10.10.10, which is what makes this a wording
    # gap rather than a rule change. No proposal moved, no cell of the answer sheet moved, and the
    # pair contradicts neither Canada concordance. Exports are untouched at 46.
    # vetoed 1145 -> 1144 on 2026-08-14. The record's exemption had been implemented for the
    # continuity veto only, because build folded the official destinations into continuous_codes
    # and that set answers one question. Every phrase-pair gate therefore still ran on codes
    # Canada's concordance had named. Exactly one candidate in the delivery was removed that way,
    # 3004.50.00.90 on imports 3004.50.00.20 retiring 2011-12, collapsing a two-way official
    # answer worth CAD 7,548,977 to a single survivor. The gate is still evaluated and its
    # objection is recorded in the new record_overruled_gate column; it simply no longer removes.
    # NOTHING MOVED BUT DISCLOSURE: the proposal, the risk tier and every other row are unchanged,
    # and on the affected row candidates_left goes 1 to 2 with the runner-up scoring 0.3553
    # against the proposal's 0.5200, so it could not have won.
    # RE-MEASURED 2026-08-14, when Layer 2 of Stage 1b stopped being empty. The WCO
    # correlation narrows the candidate field on 25 retirements before this stage sees
    # them, so fewer pairs arrive to be scored and fewer are removed on meaning: imports
    # 3419 -> 3253 pairs and 1144 -> 1131 vetoes, exports 215 -> 186 and 46 -> 44. NO RULE
    # CHANGED. Every movement here is a candidate the official record had already ruled
    # out, which is the layer order working: what the record removes never reaches meaning.
    # RE-MEASURED 2026-08-17, and every import figure here moves by one retirement's worth.
    # Stage 1a now ends a span where a relabel crosses a decisive distinction, so
    # imports 3004.50.99.30 retires twice. The new row was scored against 25 candidates and 23 of
    # them were removed on meaning, which leaves exactly the two the queue shows, its proposal
    # 3004.50.99.50 and its runner-up 3004.50.10.00. So pairs 3253 -> 3278, vetoed 1131 -> 1154,
    # reviewed 190 -> 191, and the row scores 1.0000 on wording so text_high 146 -> 147. The
    # arithmetic closes: 3278 - 3253 = 25, 1154 - 1131 = 23, 25 - 23 = 2. NO RULE CHANGED.
    # 3278 -> 3285 and vetoed 1154 -> 1155 on 2026-08-18, finding 122, the carve-out rung. Seven
    # candidate pairs were ADDED and none removed: six codes can now reach a line born at their
    # boundary in another subheading. One of the seven, 3004401000 -> 3003400000, is vetoed by
    # `dose form` (bulk against dosage), which is the meaning layer doing its job on a candidate
    # it could not previously see. The arithmetic closes: 3285 - 3278 = 7, 1155 - 1154 = 1, so six
    # survive to be ranked. NO RULE CHANGED and nothing was removed.
    "imports": {"pairs": 3285, "reviewed": 191, "vetoed": 1155,
                "outcomes": {"text_high": 147, "text_review": 30, "text_low": 14},
                # Tiers re-measured 2026-08-12: swapped_term stopped firing on plurals and on the abbreviation
    # formltd, so three rows lost a review flag and fell from tier 1.
    # held 14 -> 17 on 2026-08-14, finding 88. The exemption stopped naming cbsa_concordance and
    # started reading what the record achieved. Twelve concordance rows are DECIDED, one
    # destination each, and stay exempt because nothing stronger is coming. Four were only
    # CONSTRAINED, and three of those are bounded across four or five different six-digit
    # subheadings, which is exactly what a correlation table can narrow: 3002.10.00.90 at CAD
    # 7,588,057,599, 3004.40.00.90 at CAD 584,366,588, and 3003.40.00.00 at CAD 112,415,829, the
    # import twin of the export row that exposed this. The fourth, 3002.10.00.30, is bounded to
    # three codes inside ONE subheading, so an HS6 table cannot discriminate and it stays exempt.
    # All three newly held rows already carry an accept; the answers stand and the sheet warns.
        # held 17 -> 1 on 2026-08-14, and this is the largest single movement in the suite.
    # The hold means "a correlation table could answer this and none has been extracted".
    # The tables are now extracted, so on every subheading they cover the premise is false
    # and the row is released. It was telling the analyst DO NOT DECIDE on twelve rows the
    # record had already answered, CAD 24,787,022,692 of them, which is worse than a wrong
    # answer: a standing instruction not to look. What remains held is exactly the rows the
    # document genuinely cannot answer, and there are two, both 3002.19, one per flow. The
    # WCO addresses that subheading only in a footnote: "This subheading was considered by
    # the HS Committee to be empty and it was therefore deleted." No correlation pair
    # exists for it, so the evidence-based test lands on it precisely.
    # tier 1 falls 26 -> 25 and tier 2 rises 4 -> 5 on 2026-08-16, one row moving between them,
    # from finding 106. A candidate is now scored against the life in force when the RECORD ends
    # the classification rather than when the money stopped, so 8 pairs read different wording and
    # one row's tier follows. Every other tier is untouched and the total is unchanged at 190.
    # tier 3 rises 13 -> 14 on 2026-08-17, the one new retirement above, which the queue prints at
    # priority 3. Every other tier is untouched and the total follows reviewed to 191.
    "tiers": {1: 25, 2: 5, 3: 14, 4: 16, 5: 12, 6: 119}, "held": 1,
                "overruled": 1},
    # RE-MEASURED 2026-08-14, exports only, for two corrections made the same day.
    #
    # pairs 210 -> 215. The schedule layer no longer removes the five HS2022 lines from 30021100
    # (see check_stage1b_official_record.py, where the movement is reconciled), so five more
    # candidates reach the ranker. vetoed is unchanged at 46 and the outcome split is unchanged,
    # which is the proof that disclosing them removed nothing and moved no proposal. The tier
    # split is unchanged too, so the row is still read at the same point in the queue.
    #
    # held 7 -> 10. The hold now keys on the month the record calls the code obsolete rather than
    # on the month money last moved. Three export lines went quiet one or two months before a
    # revision they are stated to have died at, so they escaped a hold their import twins sat
    # inside: 3001.10.00 quiet 2006-10 against stated 2006-12, 3003.40.00 quiet 2016-11 against
    # 2016-12, and 3002.11.00 quiet 2021-11 against 2021-12. CAD 5,661,616 between them. Imports
    # stay at 14 because every import row already traded to the boundary month. The test is a
    # union of the two months, never a replacement, so no row can lose a hold; a control asserts
    # that separately rather than trusting the arithmetic here.
    # RE-PINNED 2026-08-31 when the export flow moved from domestic_exports.db to exports.db
    # on the analyst's instruction. The figure moved because re-exports are now counted;
    # it did not break. Imports are untouched and their pins did not move.
    "exports": {"pairs": 186, "reviewed": 40, "vetoed": 43,
                "outcomes": {"text_review": 16, "text_high": 16, "text_low": 8},
                "tiers": {1: 12, 2: 4, 3: 1, 4: 3, 5: 8, 6: 12}, "held": 1,
                "overruled": 0},
}


# NO MODULE MAY HOLD A CODE-TO-WORDING MAP THAT IGNORES THE ERA.
# A reused number carries a different description in each life. Three separate readers of an
# earliest-wording map were found and fixed one at a time, each after the analyst noticed a row
# that made no sense, so the map itself is the hazard and its absence is what gets asserted.
import ast as _ast
SUBSCRIPT_ASSIGNMENT = r"\w+\s*\[.+\]\s*=(?!=)"


def _hazard_lines(text, label):
    """THE predicate. Both the sweep and the probes below call this and nothing else.

    It used to exist twice: once in the sweep and once inside _matches_the_hazard, copied line
    for line. The probes that prove the matcher works therefore proved the COPY worked, so
    weakening the real one would not have failed anything. A control demonstrated by a duplicate
    of itself demonstrates nothing. Finding 130, 2026-08-18.
    """
    found = []
    for node in _ast.walk(_ast.parse(text)):
        if not isinstance(node, _ast.Compare):
            continue
        src = _ast.get_source_segment(text, node) or ""
        if "first_period" in src and "<" in src and "description" in text:
            # The comparison and the assignment it guards are usually on DIFFERENT lines. Three
            # lines is the window an if/assign pair occupies. The test is the SHAPE, a subscript
            # assignment beside a first_period comparison, rather than three spellings someone
            # happened to have written. Finding 110.
            window = chr(10).join(text.splitlines()[node.lineno - 1:node.lineno + 2])
            if re.search(SUBSCRIPT_ASSIGNMENT, window) or "descriptions[" in window:
                found.append("%s:%d" % (label, node.lineno))
    return found


def _earliest_wording_maps():
    """Any assignment that keys a description by code while comparing first_period.

    THE SWEEP READS checks/ AND gate1/ AS WELL AS pipeline/. It read only pipeline/ until
    2026-08-18, and an era-blind map was sitting in check_stage1_candidates.py the whole time,
    deciding the subject of a published error rate: 3002900020's second life begins at the very
    boundary that proxy asks about, and the code's earliest first_period hid it. A rule about
    which shapes are forbidden does not stop applying because the file is a check. Finding 129.
    """
    found = []
    for folder in (os.path.join(PROJECT, "pipeline"),
                   os.path.join(PROJECT, "checks"),
                   os.path.join(PROJECT, "gate1")):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".py"):
                continue
            text = open(os.path.join(folder, name), encoding="utf-8").read()
            found += _hazard_lines(text, name)
    return found


def _matches_the_hazard(source):
    """Would the sweep flag this snippet? Calls the real predicate, never a copy of it."""
    return bool(_hazard_lines(source, "probe"))


PIPELINE = os.path.join(PROJECT, "pipeline")

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


def prepared(text):
    """The published preparation, written out here rather than imported."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def rescore(a, b):
    return round(difflib.SequenceMatcher(None, prepared(a), prepared(b)).ratio(), 4)


def validate(row):
    """The contract every summary row must satisfy."""
    outcome = row["outcome"]
    total, vetoed, left = (int(row["candidates_in"]), int(row["candidates_vetoed"]),
                           int(row["candidates_left"]))
    top = float(row["top_score"])
    if outcome not in OUTCOMES:
        raise ValueError("unknown outcome %r" % outcome)
    if vetoed + left != total:
        raise ValueError("%d vetoed plus %d left is not %d in" % (vetoed, left, total))
    if not 0.0 <= top <= 1.0:
        raise ValueError("a score of %r is outside 0 to 1" % top)
    if outcome == "all_candidates_vetoed" and left != 0:
        raise ValueError("all candidates vetoed, yet %d survive" % left)
    if outcome == "text_high" and top < HIGH_THRESHOLD:
        raise ValueError("classed above the automatic gate at %.4f" % top)
    if outcome == "text_low" and top >= LOW_THRESHOLD:
        raise ValueError("classed below the review floor at %.4f" % top)
    if outcome not in ("settled_by_record", "all_candidates_vetoed") and left == 0:
        raise ValueError("no candidate survives, yet the outcome is %r" % outcome)
    return True


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


print("Check for Stage 1c. Did meaning only veto, and did text only rank?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
GOOD = {"outcome": "text_high", "candidates_in": "5", "candidates_vetoed": "2",
        "candidates_left": "3", "top_score": "0.9000"}


def variant(**changes):
    row = dict(GOOD)
    row.update(changes)
    return row


must_raise("an unknown outcome is refused", validate, variant(outcome="probably"))
must_raise("candidate arithmetic that does not add up is refused", validate,
           variant(candidates_vetoed="4"))
must_raise("a score outside zero to one is refused", validate, variant(top_score="1.4000"))
must_raise("everything vetoed while candidates survive is refused", validate,
           variant(outcome="all_candidates_vetoed"))
must_raise("a high classification below the automatic gate is refused", validate,
           variant(top_score="0.6000"))
must_raise("a low classification above the review floor is refused", validate,
           variant(outcome="text_low", top_score="0.7000"))
must_raise("an outcome with no surviving candidate is refused", validate,
           variant(candidates_vetoed="5", candidates_left="0"))

print()
print("Controls that MUST PASS (correct input must not be flagged):")
record("a well-formed summary row is accepted", validate(GOOD) is True, "5 in, 2 vetoed, 3 left")
record("the published preparation strips punctuation and case",
       prepared("Vaccines, HUMAN use (nes)") == "vaccines human use nes",
       prepared("Vaccines, HUMAN use (nes)"))
record("identical wordings score exactly one", rescore("Vaccines, human", "Vaccines, human") == 1.0,
       "1.0")

for flow in ("imports", "exports"):
    print()
    print("%s:" % flow)
    expect = EXPECTED[flow]
    ranked = load(os.path.join(WORK, "stage1_ranked_%s.csv" % flow))
    review = load(os.path.join(WORK, "stage1_review_%s.csv" % flow))
    official = {(r["retiring_code"], r["last_period"]): r
                for r in load(os.path.join(WORK, "stage1_official_%s.csv" % flow))}

    record("%s: the number of scored candidate pairs is unchanged" % flow,
           len(ranked) == expect["pairs"], "%d, expected %d" % (len(ranked), expect["pairs"]))
    record("%s: every candidate carries a score" % flow,
           all(r["similarity_score"] not in ("", None) for r in ranked),
           "%d pair(s), none blank" % len(ranked))

    # The score, recomputed here. If the two disagree, one of them changed.
    wrong = [r["candidate"] for r in ranked
             if abs(float(r["similarity_score"])
                    - rescore(r["retiring_description"], r["candidate_description"])) > 1e-9]
    record("%s: every score matches an independent recomputation" % flow, not wrong,
           "0 differ across %d pair(s)" % len(ranked) if not wrong
           else "%d differ. First: %s" % (len(wrong), wrong[0]))

    # A gate may remove. It may never add. The candidate set must be exactly what arrived.
    def by_retirement(rows, also_rank=False):
        key = (lambda r: (r["retiring_code"], r["last_period"], int(r["rank"])) if also_rank
               else (r["retiring_code"], r["last_period"]))
        pair = lambda r: (r["retiring_code"], r["last_period"])
        return [(k, list(v)) for k, v in itertools.groupby(sorted(rows, key=key), key=pair)]

    added = []
    for key, group in by_retirement(ranked):
        arrived = {c for c in official[key]["candidates_after"].split(";") if c}
        present = {r["candidate"] for r in group}
        if present != arrived:
            added.append("%s: %s" % (key[0], sorted(present ^ arrived)[:3]))
    record("%s: the gates removed candidates and added none" % flow, not added,
           "the candidate set is exactly what Stage 1b passed on" if not added
           else "%d differ. First: %s" % (len(added), added[0]))

    misordered = []
    for key, group in by_retirement(ranked, also_rank=True):
        scores = [float(r["similarity_score"]) for r in group]
        if scores != sorted(scores, reverse=True):
            misordered.append(key[0])
    record("%s: candidates are ranked by score, highest first" % flow, not misordered,
           "0 misordered" if not misordered else "misordered: %s" % misordered[:3])

    vetoed = [r for r in ranked if r["vetoed_by"]]
    record("%s: the number removed by meaning is unchanged" % flow,
           len(vetoed) == expect["vetoed"], "%d, expected %d" % (len(vetoed), expect["vetoed"]))
    record("%s: a vetoed candidate always names the rule that removed it" % flow,
           all(r["vetoed_by"].strip() for r in vetoed), "%d vetoed, all attributed" % len(vetoed))

    # The layer order, stated as a testable claim rather than as a design intention.
    #
    # Rank is positional over every candidate, so a vetoed one legitimately sits at rank 1 when
    # its wording is the closest. Measured 2026-08-11 that happens 23 times on imports and 4 on
    # exports. What must never happen is that such a candidate is CHOSEN: meaning removes, text
    # only orders what survives. Nothing pinned this until now, and it is the single guarantee
    # the whole design rests on.
    removed = {(r["retiring_code"], r["last_period"], r["candidate"]): r["vetoed_by"]
               for r in ranked if r["vetoed_by"]}
    survivors = {(r["retiring_code"], r["last_period"], r["candidate"])
                 for r in ranked if not r["vetoed_by"]}
    chosen_but_removed = [(r["retiring_code"], r["top_candidate"])
                          for r in review if r["top_candidate"]
                          and (r["retiring_code"], r["last_period"],
                               r["top_candidate"]) in removed]
    # A DESTINATION THE RECORD NAMES IS NEVER REMOVED BY A GATE.
    #
    # Rebuilt from the official file, which is the record's own answer, and never from the stage.
    # This is the layer order stated as an assertion instead of as a docstring. It was a docstring
    # for as long as the stage existed and was false for one candidate the whole time: the
    # exemption reached the continuity veto only, so the phrase-pair gates still ran on codes
    # Canada's concordance had named, and `use` removed 3004.50.00.90 from a two-way official
    # answer worth CAD 7,548,977.
    #
    # Two claims, because dropping the second would let a future fix pass by simply not
    # evaluating the gate, which would hide the disagreement rather than resolve it in the
    # record's favour.
    named = {}
    for r in load(os.path.join(PROJECT, "work", "stage1_official_%s.csv" % flow)):
        named[(r["retiring_code"], r["last_period"])] = {
            d for d in r["official_destinations"].split(";") if d}
    vetoed_official, overruled_rows = [], []
    for r in ranked:
        if r["candidate"] not in named.get((r["retiring_code"], r["last_period"]), ()):
            continue
        if r["vetoed_by"]:
            vetoed_official.append((r["retiring_code"], r["candidate"], r["vetoed_by"]))
        if r["record_overruled_gate"]:
            overruled_rows.append((r["retiring_code"], r["candidate"], r["record_overruled_gate"]))
    record("%s: no destination the record names is vetoed by a gate" % flow,
           not vetoed_official,
           "%d official destination(s) carry a veto%s"
           % (len(vetoed_official),
              (": " + ", ".join("%s -> %s on %s" % v for v in vetoed_official[:3]))
              if vetoed_official else ""))
    # PINNED, because the alternative could not fail. This control first read "no candidate the
    # record never named carries an overruled flag", which is trivially true when the flag is
    # never set at all, so it passed against the very defect it was written for. That is the
    # audit's own finding about a control whose name claims more than its assertion tests,
    # reproduced while fixing a different one. A measured count fails on 0 against 1.
    stray_flag = [r["candidate"] for r in ranked if r["record_overruled_gate"]
                  and r["candidate"] not in named.get((r["retiring_code"], r["last_period"]), ())]
    record("%s: the record overruled a gate on exactly the candidates measured" % flow,
           len(overruled_rows) == expect["overruled"] and not stray_flag,
           "%d overruled, expected %d; %d on a candidate the record never named"
           % (len(overruled_rows), expect["overruled"], len(stray_flag)))

    record("%s: a candidate removed on meaning is never the one chosen" % flow,
           not chosen_but_removed,
           "%d vetoed candidate(s) rank first on wording, none was chosen"
           % sum(1 for r in ranked if r["vetoed_by"] and r["rank"] == "1")
           if not chosen_but_removed else "CHOSEN ANYWAY: %s" % chosen_but_removed[:3])
    not_a_survivor = [r["retiring_code"] for r in review if r["top_candidate"]
                      and (r["retiring_code"], r["last_period"],
                           r["top_candidate"]) not in survivors]
    record("%s: every chosen candidate is one that survived the gates" % flow,
           not not_a_survivor,
           "all %d choices trace to a survivor"
           % sum(1 for r in review if r["top_candidate"])
           if not not_a_survivor else "%d do not: %s" % (len(not_a_survivor),
                                                         not_a_survivor[:3]))

    broken = []
    for r in review:
        try:
            validate(r)
        except ValueError as error:
            broken.append("%s: %s" % (r["retiring_code"], error))
    record("%s: every review row satisfies the contract" % flow, not broken,
           "%d row(s) checked" % len(review) if not broken
           else "%d of %d failed. First: %s" % (len(broken), len(review), broken[0]))

    record("%s: the review queue holds every unsettled retirement" % flow,
           len(review) == expect["reviewed"], "%d, expected %d" % (len(review), expect["reviewed"]))
    counts = defaultdict(int)
    for r in review:
        counts[r["outcome"]] += 1
    record("%s: the outcome split is unchanged" % flow, dict(counts) == expect["outcomes"],
           "%s" % dict(counts))
    record("%s: nothing already settled by the record reaches the queue" % flow,
           all(r["outcome"] != "settled_by_record" for r in review),
           "%d row(s)" % len(review))

    # Risk, not score. The queue must not be in score order.
    scores = [float(r["top_score"]) for r in review]
    tiers = defaultdict(int)
    for r in review:
        tiers[int(r["risk_tier"])] += 1
    record("%s: the risk tier split is unchanged" % flow, dict(tiers) == expect["tiers"],
           "%s" % dict(sorted(tiers.items())))
    # What the record achieved on each retirement, loaded here because three controls below turn
    # on it and none of them may ask the stage.
    official = {(r["retiring_code"], r["last_period"]): r
                for r in load(os.path.join(PROJECT, "work", "stage1_official_%s.csv" % flow))}
    held = [r for r in review if r["held_for_official_evidence"] == "yes"]
    record("%s: the rows held for official evidence are the ones already known" % flow,
           len(held) == expect["held"], "%d, expected %d" % (len(held), expect["held"]))
    record("%s: every held row sits at the end of the queue" % flow,
           all(r["held_for_official_evidence"] == "no" for r in review[:len(review)-len(held)]),
           "held rows occupy the last %d position(s), so judgement is not spent on them" % len(held))
    # This asserted `official_layer != "cbsa_concordance"` until 2026-08-14, which is the rule
    # finding 88 records as wrong: it treats a concordance that merely BOUNDED a row as though it
    # had answered.
    #
    # The obvious replacement, `official_outcome != "decided"`, was written and thrown away in the
    # same sitting: a decided row is settled, a settled row never enters the review queue, and a
    # control that cannot fail is the defect M9 was about. The property below can fail, and does
    # the moment the six-digit test is removed, because imports 3002.10.00.30 is bounded to three
    # codes inside one subheading and would join the hold.
    narrowable = []
    for r in held:
        dests = [d for d in official[(r["retiring_code"],
                                      r["last_period"])]["official_destinations"].split(";") if d]
        if dests and len({d[:6] for d in dests}) == 1:
            narrowable.append(r["retiring_code"])
    record("%s: every held row is one the awaited table could still narrow" % flow,
           not narrowable,
           "%d held row(s); %d bounded inside a single subheading, where an HS6 table is silent "
           "by construction" % (len(held), len(narrowable)))
    record("%s: the queue is not ordered by score" % flow,
           scores != sorted(scores, reverse=True),
           "ordered by risk, so a high score can sit below a low one")

    # THE HOLD READS THE STATED TERMINATION, NOT THE MONTH MONEY STOPPED.
    #
    # Rebuilt here from the inventory without calling the stage, per rule 2. A code the record
    # states was terminated at an international revision must be held even if its last shipment
    # fell a month or two earlier, because money stops before a classification does. Three export
    # rows were outside the hold for exactly that reason while the identical import commodity at
    # the identical boundary sat inside it.
    inventory = load(os.path.join(PROJECT, "work", "commodity_inventory_%s.csv" % flow))
    stated_end = {}
    for r in inventory:
        value = (r.get("stated_termination") or "").strip()
        if value:
            stated_end[(r["hs_code"], r["last_period"])] = value

    def subheading_is_gone(row):
        """Rebuilt from the inventory, not read from the stage's own answer."""
        return not any(o["last_period"] > row["last_period"] for o in inventory
                       if o["hs_code"][:6] == row["retiring_code"][:6])

    escaped = [r for r in review
               if r["held_for_official_evidence"] == "no"
               and r["official_layer"] != "cbsa_concordance"
               and stated_end.get((r["retiring_code"], r["last_period"]), "") in HS_REVISION_MONTHS
               and r["last_period"] not in HS_REVISION_MONTHS
               and subheading_is_gone(r)]
    escaped = [r for r in escaped
               if (stated_end.get((r["retiring_code"], r["last_period"]), r["last_period"]),
                   r["retiring_code"][:6]) not in CORRELATED]
    record("%s: no retirement stated terminated at a revision escapes the hold" % flow,
           not escaped,
           "%d escaped%s" % (len(escaped),
                             (": " + ", ".join("%s ending %s, stated %s"
                                               % (e["retiring_code"], e["last_period"],
                                                  stated_end[(e["retiring_code"],
                                                              e["last_period"])])
                                               for e in escaped[:3])) if escaped else ""))
    # The union, stated separately. The corrected test ORs the two months rather than replacing
    # one with the other, so a row whose last trade lands on a revision keeps its hold whatever
    # the record says about it. Without this a later simplification to "stated termination only"
    # would look correct and would quietly drop holds.
    lost = [r for r in review
            if r["held_for_official_evidence"] == "no"
            and r["last_period"] in HS_REVISION_MONTHS
            and r["official_layer"] != "cbsa_concordance"
            and subheading_is_gone(r)]
    # RESTATED 2026-08-14. It read "no hold was taken away", which was right when the only
    # change was the M4 union and wrong the moment the correlation tables arrived: a row the
    # tables cover SHOULD lose its hold, because the document it was waiting for has been read.
    # What must still never happen is losing a hold with no such reason, so the exemption is
    # named explicitly and everything else must stay held.
    lost = [r for r in lost
            if (stated_end.get((r["retiring_code"], r["last_period"]), r["last_period"]),
                r["retiring_code"][:6]) not in CORRELATED]
    record("%s: no hold was taken away except by the tables being read" % flow, not lost,
           "%d row(s) lost a hold for no stated reason" % len(lost))

    # THE HOLD IS A FUNCTION OF WHAT THE RECORD ACHIEVED, NEVER OF WHICH FILE IT ARRIVED IN.
    #
    # Re-derived here in full from the official file and the inventory, sharing no code with the
    # stage, and deliberately never reading deciding_layer. The exemption used to name
    # cbsa_concordance, so a row that concordance merely CONSTRAINED was exempt while a row a
    # constraint set bounded to the identical destinations was held: exports 3003.40.00 and its
    # import twin carried the same four destinations and were treated differently on provenance
    # alone. Sixteen rows were exempt, of which twelve are genuinely decided and four only bounded.
    #
    # The two exemptions that replace it both ask whether the awaited document could say anything.
    # A single named destination is already an answer. A bound whose destinations all sit in one
    # six-digit subheading cannot be narrowed by a correlation table, because those tables map HS6
    # to HS6; imports 3002.10.00.30 is the one row in that position, CAD 1,100,455,460.
    wrong_hold = []
    for r in review:
        off = official[(r["retiring_code"], r["last_period"])]
        end = stated_end.get((r["retiring_code"], r["last_period"]), "")
        if not end or end < r["last_period"]:
            end = r["last_period"]
        at_revision = r["last_period"] in HS_REVISION_MONTHS or end in HS_REVISION_MONTHS
        dests = [d for d in off["official_destinations"].split(";") if d]
        if not at_revision:
            expected = False
        elif (end, r["retiring_code"][:6]) in CORRELATED:
            # The awaited document has been read and it speaks about this subheading.
            expected = False
        elif off["outcome"] == "decided":
            expected = False
        elif dests and len({d[:6] for d in dests}) == 1:
            expected = False
        else:
            expected = subheading_is_gone(r)
        if expected != (r["held_for_official_evidence"] == "yes"):
            wrong_hold.append((r["retiring_code"], r["last_period"], off["deciding_layer"],
                               off["outcome"], expected))
    record("%s: the hold re-derives without ever reading which source spoke" % flow,
           not wrong_hold,
           "%d disagree%s" % (len(wrong_hold),
                              (": " + ", ".join("%s %s (%s/%s) expected %s" % w
                                                for w in wrong_hold[:3])) if wrong_hold else ""))

    # And the symmetry the finding is actually about. Accumulated ACROSS BOTH FLOWS and asserted
    # once after the loop, because the asymmetry it exists to catch is between an export row and
    # its import twin; a per-flow version was written first and could not see the case at all.
    #
    # Keyed on the month the record ENDS the classification, never on the last trading month.
    # Exports 3003.40.00 stops 2016-11 and imports 3003.40.00.00 stops 2016-12 while both are
    # stated terminated 2016-12, so keying on trade would separate the very pair being compared.
    for r in review:
        off = official[(r["retiring_code"], r["last_period"])]
        dests = [d for d in off["official_destinations"].split(";") if d]
        if len(dests) < 2:
            continue
        end = stated_end.get((r["retiring_code"], r["last_period"]), "")
        if not end or end < r["last_period"]:
            end = r["last_period"]
        key = (end, frozenset(d[:6] for d in dests))
        BOUNDED_GROUPS.setdefault(key, {})[
            "%s:%s" % (flow, r["retiring_code"])] = r["held_for_official_evidence"]

    # EVERY TIER-6 REASON AGREES WITH THE ROW'S OWN NUMBERS.
    #
    # Tier 6 is reached two ways and its text used to describe only one. 19 of 135 tier-6 rows
    # printed "a high score with an identical meaning-word set" while scoring below the gate or
    # sharing fewer than all their meaning words, CAD 72,036,869,803 of them, including the
    # largest object in the export crosswalk. The tier was right on every one; only the sentence
    # was false, which no count could catch because nothing ever disagreed with it.
    contradicted = [r for r in review
                    if r["risk_tier"] == "6"
                    and "identical meaning-word set" in r["risk_reason"]
                    and (float(r["top_score"]) < HIGH_THRESHOLD
                         or float(r["meaning_overlap"]) < 1.0)]
    record("%s: no tier-6 reason claims a high score the row does not carry" % flow,
           not contradicted,
           "%d contradicted%s" % (len(contradicted),
                                  (": " + ", ".join("%s top=%s overlap=%s"
                                                    % (c["retiring_code"], c["top_score"],
                                                       c["meaning_overlap"])
                                                    for c in contradicted[:3]))
                                  if contradicted else ""))

print()
print("The hold's unenforced limb: a row may only wait for a document that exists.")
# The stage asks four ways whether the awaited table could say anything, and cannot ask the
# fifth, because reading the evidence directory is no business of a ranking stage. So it is
# asked here. A row held for a correlation table that does not exist is not waiting, it is
# stuck, and the queue would carry it forever without anything saying so.
#
# All five revision boundaries have a table today, so this passes on the delivery as it stands.
# It is written because the condition is invisible until it is false: the boundary set and the
# evidence directory are maintained in different places by different hands.
WCO_FOR_BOUNDARY = {
    "200112": "WTO_HSCodes_1996_to_2002.pdf", "200612": "WTO_HSCodes_2002_to_2007.pdf",
    "201112": "WTO_HSCodes_2007_to_2012.pdf", "201612": "WTO_HSCodes_2012_to_2017.pdf",
    "202112": "WTO_HSCodes_2017_to_2022.pdf",
}
_wto_dir = os.path.join(PROJECT, "evidence", "wto")
_on_disk = set(os.listdir(_wto_dir)) if os.path.isdir(_wto_dir) else set()
_stranded, _held_total = [], 0
for _flow in ("imports", "exports"):
    _inv_end = {}
    for _r in load(os.path.join(PROJECT, "work", "commodity_inventory_%s.csv" % _flow)):
        _v = (_r.get("stated_termination") or "").strip()
        if _v:
            _inv_end[(_r["hs_code"], _r["last_period"])] = _v
    for _r in load(os.path.join(PROJECT, "work", "stage1_review_%s.csv" % _flow)):
        if _r["held_for_official_evidence"] != "yes":
            continue
        _held_total += 1
        _last = _r["last_period"]
        _end = _inv_end.get((_r["retiring_code"], _last), _last)
        _boundary = (_last if _last in HS_REVISION_MONTHS
                     else _end if _end in HS_REVISION_MONTHS else None)
        if _boundary is None or WCO_FOR_BOUNDARY.get(_boundary) not in _on_disk:
            _stranded.append((_flow, _r["retiring_code"], _boundary))
record("every held row waits on a correlation table that is actually on disk",
       not _stranded,
       "%d held row(s) across %d boundary/boundaries, %d stranded%s"
       % (_held_total, len({b for b in WCO_FOR_BOUNDARY}), len(_stranded),
          (": " + ", ".join("%s %s at %s" % s for s in _stranded[:3])) if _stranded else ""))

print()
print("Across both flows: the hold cannot depend on which file the record arrived in.")
_split = {k: v for k, v in BOUNDED_GROUPS.items() if len(set(v.values())) > 1}
_cross = sum(1 for v in BOUNDED_GROUPS.values()
             if len({m.split(":")[0] for m in v}) > 1)
record("retirements bounded to the same subheadings reach the same hold",
       not _split,
       "%d bounded group(s), %d spanning both flows, %d split%s"
       % (len(BOUNDED_GROUPS), _cross, len(_split),
          (": " + "; ".join("%s -> %s" % (sorted(k[1]), v) for k, v in list(_split.items())[:2]))
          if _split else ""))

print()
print("Round trip: read the output back the way the next stage will, and re-derive it.")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage1c_rank as _stage  # noqa: E402

# Rule 10. Every claim above was about what the stage PRODUCED. This asks what the next stage
# will SEE. The two came apart once already: the writer overwrote review_flag with the risk
# reason, so reading the file back and re-deriving the tier returned 1 for every row, and no
# control noticed because none of them ever re-read the output.
for flow in ("imports", "exports"):
    review = load(os.path.join(WORK, "stage1_review_%s.csv" % flow))
    undrivable = [r["retiring_code"] for r in review
                  if _stage.risk_rank(r)[0] != int(r["risk_tier"])]
    record("%s: the recorded tier re-derives from the written row" % flow, not undrivable,
           "%d row(s) re-derived" % len(review) if not undrivable
           else "%d of %d do not: %s" % (len(undrivable), len(review), undrivable[:3]))
    mismatched = [r["retiring_code"] for r in review
                  if _stage.risk_rank(r)[1] != r["risk_reason"]]
    record("%s: the recorded reason re-derives from the written row" % flow, not mismatched,
           "%d row(s)" % len(review) if not mismatched else "%d differ" % len(mismatched))
    # review_flag must hold rules, not prose. A reader has to be able to tell them apart.
    # Every rule whose action is review. swapped_term joined them 2026-08-11.
    RULE_NAMES = {"basket contents", "specific against residual", "swapped term"}
    polluted = [r["retiring_code"] for r in review
                if r["review_flag"] and not set(r["review_flag"].split(";")) <= RULE_NAMES]
    record("%s: review_flag holds only rules that fired" % flow, not polluted,
           "%d row(s) carry a rule, the rest are empty"
           % sum(1 for r in review if r["review_flag"]) if not polluted
           else "%d polluted: %s" % (len(polluted), polluted[:3]))
    ordered = [(r["held_for_official_evidence"] == "yes",
                int(r["risk_tier"]),
                float(r["meaning_overlap"]) if int(r["risk_tier"]) == 2 else 0.0,
                -float(r["total_value_cad"])) for r in review]
    record("%s: the file is in the order the tiers imply" % flow, ordered == sorted(ordered),
           "%d row(s): held last, then tier, then worst meaning first inside tier 2" % len(review))
    # The diagnostic must never be mistaken for the published score.
    overlaps = [float(r["meaning_overlap"]) for r in review]
    record("%s: meaning overlap is recorded on every row and is not the score" % flow,
           all(0.0 <= o <= 1.0 for o in overlaps)
           and any(abs(o - float(r["top_score"])) > 1e-9 for o, r in zip(overlaps, review)),
           "%d value(s), and they differ from the score, so the two cannot be confused"
           % len(overlaps))

print()
print("Probes: outcomes this delivery never produces.")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage1c_rank as stage  # noqa: E402

# No retirement in this delivery has every candidate removed by a gate. The branch exists and
# must behave: it may not report a successor, and it may not empty the field either, because
# only the official record may conclude that nothing succeeded a code.
outcome, top, runner_up = stage.classify([])
record("probe: with every candidate vetoed the outcome says so",
       outcome == "all_candidates_vetoed" and top == 0.0,
       "%s, never reached by this delivery" % outcome)
outcome, _t, _r = stage.classify([{"score": 0.90, "candidate": "x", "same_content_words": True}])
record("probe: a lone survivor above the gate is classed high", outcome == "text_high", outcome)
outcome, _t, _r = stage.classify([{"score": 0.10, "candidate": "x", "same_content_words": False}])
record("probe: a lone survivor below the floor is classed low", outcome == "text_low", outcome)
record("probe: the score is computed on unexpanded text, unlike the gates",
       stage.score("Vaccines, vet use", "Vaccines, veterinary use") < 1.0,
       "%.4f, which would be 1.0 if the score expanded shorthand the way the gates do"
       % stage.score("Vaccines, vet use", "Vaccines, veterinary use"))

print()
print("NO MODULE HOLDS A CODE-TO-WORDING MAP THAT IGNORES THE ERA")
_maps = _earliest_wording_maps()
# PROVOKED ON SPELLINGS THE PIPELINE DOES NOT CONTAIN. A guard whose subject is empty passes for
# the same reason a broken one does, and this guard's subject IS empty by design: the maps it
# forbids have all been removed. Convention 9 says probe the branches the delivery never reaches,
# so the matcher is fed the hazard in two wordings it used to walk straight past.
for _spelling, _label in (
        ("""
for r in inventory:
    if r["first_period"] < earliest[r["hs_code"]]:
        wording[r["hs_code"]] = r["description"]
""", "a map named `wording`"),
        ("""
for row in rows:
    if row["first_period"] < seen[row["code"]]:
        seen[row["code"]] = row["description"]
""", "a map named `seen`")):
    record("probe: the earliest-wording matcher catches %s" % _label,
           _matches_the_hazard(_spelling),
           "both spellings passed the three-token test this replaced")
record("probe: it does not fire on a first_period comparison that writes no map",
       not _matches_the_hazard("""
for r in inventory:
    if r["first_period"] < cutoff:
        keep.append(r["description"])
"""),
       "appending is not building a code-to-wording map")
record("no earliest-wording map survives in pipeline, checks or gate1", not _maps,
       "a candidate's wording is read from its lives, never from a single map"
       if not _maps else "found at %s" % _maps)
from stage1c_rank import wording_at as _wording_at   # noqa: E402
_probe = {"9": [("199801", "201112", "old words"), ("201201", "202606", "new words")]}
record("the era lookup returns the life that can receive the retirement",
       _wording_at(_probe, "9", "201112") == "new words"
       and _wording_at(_probe, "9", "200506") == "old words",
       "a retirement in 2011-12 sees the 2012 wording; one in 2005 sees the 1998 wording")
record("a code with one life is unaffected",
       _wording_at({"8": [("199801", "202606", "only words")]}, "8", "201112") == "only words",
       "360 of the 460 codes have a single life and read exactly as before")

print()
print("What the WCO documents say about subheadings they give no destination for:")
# Finding 101. Pinned by CONTENT, not by count. The failure this guards is silent: the extractor
# refuses to let a prose line start a data block, which is right and is what stopped it inventing
# `3002.19 -> 3006.93`, but the same guard threw the code away and the pairs file then held no
# trace of the sentence. Asserting "2 statements exist" would pass on two empty strings.
_by_section = {(r["section"], r["code"]): r["statement"] for r in STATEMENTS}
record("both tables record that 3002.19 was deleted as empty",
       ("TABLE_I", "3002.19") in _by_section and ("TABLE_II", "3002.19") in _by_section
       and "considered by the HS Committee as empty" in _by_section[("TABLE_I", "3002.19")]
       and "to be empty and it was therefore deleted" in _by_section[("TABLE_II", "3002.19")],
       "%d statement(s) across both independently typeset tables" % len(STATEMENTS))
# The wrapped sentence must not run on into the next data block, which is how it first read
# "...therefore deleted 30.04 ex3006.93 Applicable subheadings of 30.04".
_ran_on = [s for s in STATEMENTS if re.search(r"\d{2,4}\.\d{2}", s["statement"])]
record("no statement runs on into the codes beneath it", not _ran_on,
       "a wrapped remark stops at the first line carrying a code"
       if not _ran_on else "%d ran on: %s" % (len(_ran_on), _ran_on[0]["statement"][:90]))
# And a statement is never a correlation. Reading one as a pair is the defect that produced a
# false official answer on 3002.19 in the first place.
_leaked = [s for s in STATEMENTS
           if ("%d12" % (int(s["boundary_to"]) - 1), s["code"].replace(".", "")) in CORRELATED
           and s["boundary_to"] == "2022"]
record("a deletion notice never becomes a correlation pair", not _leaked,
       "3002.19 is addressed by the documents and absent from the pairs file, which is correct"
       if not _leaked else "%d leaked into the pairs file" % len(_leaked))

# EVERY THRESHOLD IS DECLARED WHERE THE PROJECT SAYS IT IS. Finding 140, 2026-08-18.
#
# INSPIRE2_V2_PLAN.md section 5: "Every threshold is declared in one place with a written
# rationale, and the rationale is part of the released documentation." THRESHOLDS.md was written
# on 2026-08-05 against v1's builder and documented two of the eleven numeric constants v2 uses.
# The nine it missed include REUSE_GAP_MONTHS, which decides whether a recycled number is one
# commodity or two. A principle nothing enforces is a preference, so it is enforced here: a
# constant added to pipeline/ without a line in THRESHOLDS.md fails this.
_thresholds_doc = open(os.path.join(PROJECT, "THRESHOLDS.md"), encoding="utf-8").read()
_constants = {}
for _name in sorted(os.listdir(PIPELINE)):
    if not _name.endswith(".py"):
        continue
    _text = open(os.path.join(PIPELINE, _name), encoding="utf-8").read()
    for _m in re.finditer(r"^([A-Z][A-Z0-9_]{3,})\s*=\s*[-\d.]+\s*$", _text, re.M):
        _constants[_m.group(1)] = _name
_undeclared = sorted(c for c in _constants if c not in _thresholds_doc)
record("every numeric threshold the pipeline defines is declared in THRESHOLDS.md",
       not _undeclared,
       "%d constant(s) across pipeline/, each named in the document" % len(_constants)
       if not _undeclared
       else "%d undeclared: %s" % (len(_undeclared),
                                   [(c, _constants[c]) for c in _undeclared[:4]]))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if failed:
    print()
    print("Stage 1c is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 1c is validated. Meaning only removed, text only ranked, and every score is recorded.")
