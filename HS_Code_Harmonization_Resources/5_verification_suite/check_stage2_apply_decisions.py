"""Does Stage 2 carry every answer, and only the answers, into resolved successions?


Stage 2 is the first stage that writes a link, so the questions here are different from every
earlier check. Those asked whether evidence was gathered correctly. This asks whether the answers
were transcribed without addition, loss, or invention, and whether the rows nobody has answered
are visibly open rather than quietly linked.

Written to CHECK_CONVENTIONS.md. In particular:

  rule 1  every refusal is provoked with input it must reject, in the MUST FAIL section below.
  rule 2  the expectations are rebuilt from the workbook and the official file, never by calling
          the stage. The one exception is the guard section, which must call the stage to prove
          its refusals fire, and which uses synthetic rows the delivery does not contain.
  rule 3  every loop collects and reports a count, never stops at the first bad row.
  rule 8  where a control asserts a symptom rather than a cause, it says so.
"""

import csv
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage2_apply_decisions as stage  # noqa: E402

FLOWS = ("imports", "exports")

# Measured 2026-08-14 on the first build of this stage, and reconciled before being pinned.
# 319 retirements: 89 named outright by Canada's concordance and 230 answered in the workbook.
# 287 carry a successor, 5 record that the goods left Chapter 30, and 27 are open. The 27 are
# exactly the 27 blank decisions, and the value is the sum the two flows already report.
EXPECTED = {
    # THE ANALYST RULED ON TWELVE ROWS ON 2026-08-14, and this is what moved.
    #
    # imports succeeded 262 -> 265, three accepts: 215 and 217, the veterinary vaccine lines
    # carried across the 2022 revision on the WCO record, and 216, influenza to influenza.
    # left_chapter 1 -> 4, three rejects to none: 218 and 219, blood-grouping reagents, which
    # the WCO 2017-to-2022 table sends to 3822.13, and 226, malaria diagnostic kits, which it
    # sends to 3822.11. held 16 -> 10, which is those six leaving the open set.
    #
    # Rows 210, 223 and 225 are deliberately still held. 223 and 225 were reserved by the analyst
    # pending the reasoning, and 210 is the row the sheet marks CONFIRM and this project believes
    # is wrong: a residual line proposed onto the influenza line it was defined to exclude.
    # ROUND TWO, LATER THE SAME DAY. Four more rulings, all of them imports, and exports do not
    # move at all. succeeded 265 -> 268 and held 10 -> 7: rows 223 and 225 accept the leftover
    # line under 3001.90, and row 210 rejects the influenza line and NAMES 3002.41.00.90, which
    # still succeeds because a reject that names a successor is still a link.
    #
    # Row 1 is a CHANGE to a decision already signed, from accept onto hydrocortisone to reject
    # naming 3004.32.00.19, the leftover line of the same block. It stays inside succeeded and
    # moves only from approve to reject_named, which is why the totals here barely move while the
    # crosswalk's answer on CAD 128,397,239 changed completely.
    # ROUND THREE. Rows 213 and 222, both 3002.19, answered UNRESOLVED: examined, the proposal is
    # wrong, and the right answer cannot be determined. imports held 7 -> 6 with unresolved 0 -> 1,
    # exports held 5 -> 4 with unresolved 0 -> 1. The open count does not move, because an
    # unresolved row is still open; what moves is that it is now open for a stated reason rather
    # than waiting for something.
    #
    # overrode goes 0 -> 1 on imports and 1 -> 2 on exports, and that is the point rather than a
    # side effect. Both rows carried "DO NOT DECIDE, waiting on a document". The analyst has now
    # ruled that no document is coming: the WCO says only that the subheading "was considered by
    # the HS Committee to be empty and it was therefore deleted", which is false for Canada, where
    # CAD 1,629,159,701 was imported under it. Answering over that hold is deliberate and is
    # recorded as overrode_a_hold=yes rather than being quietly absorbed.
    # ROUND FOUR, 2026-08-15, and it is the record talking rather than the analyst. Stage 1a now
    # separates a stoppage the delivery DECLARES a termination for from one where trade merely
    # stopped. Fifteen rows were the second kind and had been reaching the workbook as decisions
    # for a person to make. They resolve to not_a_retirement and carry no link.
    #
    # imports: held 6 -> 0 and left_chapter 4 -> 3, the seven of them becoming not_a_retirement.
    # NOTHING MOVED INTO OR OUT OF succeeded, on either flow. That is the property to watch: this
    # separates non-events from retirements and must never change where a real retirement went.
    # ROUND FIVE, 2026-08-15. Rows 213 and 222, both 3002.19, move from `unresolved` to
    # `reject -> 3002.90.00.90` and `-> 3002.90.90` on the tariff structure: the 2022 schedule
    # leaves the 3002.1 group with NO residual, and 3002.90 is heading 30.02's own leftover, so an
    # immunological product that is not unmixed, mixed or in measured doses has nowhere else to
    # fall. The WCO addresses 3002.19 only to call it empty, which is false for Canada, and the
    # trade cannot corroborate either way; the reason cells say both things rather than claiming
    # support they do not have. imports succeeded 268 -> 269 and unresolved 1 -> 0.
    #
    # WITH THAT, EVERY ROW IN THE DELIVERY IS ANSWERED. open falls to 0 on both flows, which is
    # Gate 2's "zero rows left undecided" met as originally written, and the bounded exception
    # that was added on 2026-08-14 and removed on 2026-08-15 is not needed after all.
    # RE-MEASURED 2026-08-17. Stage 1a now ends a span where a relabel crosses a decisive
    # distinction, so imports 3004.50.99.30 retires twice: rows 279 -> 280 and succeeded
    # 269 -> 270. The analysts settled the new row onto 3004.50.99.50 on 2026-08-17, so it arrives
    # here answered and nothing moves into held or unresolved. VALUE DOES NOT MOVE: the two spans
    # carry between them exactly what the one span carried, so a change here would mean the split
    # had invented trade rather than divided it.
    "imports": {"rows": 280, "value": 102128187239.0, "succeeded": 270, "left_chapter": 3,
                "held": 0, "not_a_retirement": 7, "unresolved": 0, "record": 89, "overrode": 1},
    # exports succeeded 25 -> 24 and left_chapter 4 -> 5 on 2026-08-14, one row.
    # exports:3002.11.00:2021-11, malaria diagnostic test kits, moved from reject -> 3002.15.00
    # to reject -> none on the official record. The WCO 2017-to-2022 correlation table maps
    # 3002.11 to 3822.11 and to nothing else, so the goods left Chapter 30 and this crosswalk has
    # no successor to record. Taken from both of the document's own tables, which are typeset
    # independently, run in opposite directions, and agree. The value is untouched: a row that
    # leaves the chapter is still accounted for, it simply carries no link.
    # And on the same day, exports succeeded 24 -> 29, five accepts: 211 and 220, the vaccine
    # lines whose descriptions match word for word across the 2022 revision; 212, antisera, onto
    # 3002.12 within the six-way 2017 subdivision of 3002.10; and 214 with 72, the dosage and
    # bulk alkaloid lines, onto the 3004.49 and 3003.49 remainders left after ephedrine,
    # pseudoephedrine and norephedrine were carved out in 2017. Row 72 REVERSES the withdrawal
    # made earlier the same day: it waited on the WCO 2012-to-2017 table, which has since been
    # extracted and read. left_chapter 5 -> 6 is row 221, the export blood-grouping line, joining
    # its two import twins. held 11 -> 5.
    # exports round four: held 4 -> 0 and left_chapter 6 -> 2, eight rows. The four leaving
    # left_chapter are the ones the analyst had already ruled `reject -> none` on exactly this
    # ground, in their own words: "The line was not withdrawn, so there is no successor to name."
    # The rule now reaches the ten that were never asked, from the record rather than row by row.
    # exports overrode 2 -> 1. exports:3003.42.00:2024-09 was held on the sparsity limb, quiet 21
    # months against a 49-month gap it had already come back from, and the analyst answered it
    # `reject -> none` anyway. That answer was right and the hold is now moot, because the row is
    # not a retirement at all. Counting it as an override would record the analyst going ahead of
    # evidence they in fact read correctly. Only exports:3002.19.00:2021-12 remains, which is a
    # genuine override of a document hold.
    # exports round five: succeeded 29 -> 30, unresolved 1 -> 0, the export twin of the same
    # ruling. Its own flow argues AGAINST it and the reason cell says so: 3002.90.90 fell CAD
    # 2,973,338 a month across the boundary while 3002.19.00 was carrying CAD 51,268. The
    # structure decides it and the money is disclosed rather than dressed up.
    # RE-PINNED 2026-08-31 when the export flow moved from domestic_exports.db to exports.db
    # on the analyst's instruction. The figure moved because re-exports are now counted;
    # it did not break. Imports are untouched and their pins did not move.
    "exports": {"rows": 40, "value": 82864746189.0, "succeeded": 30, "left_chapter": 2,
                "held": 0, "not_a_retirement": 8, "unresolved": 0, "record": 0, "overrode": 1},
}
# reject_named 11 -> 10 and reject_none 5 -> 6 on 2026-08-14: the same single row, and the
# rejects still total 16. A reject that names `none` is as decided as one that names a code.
#
# Then approve 174 -> 182 for the eight accepts, reject_none 6 -> 10 for the four rejects to
# none, and not_answered 27 -> 15 as those twelve leave the open set. decided, reject_named and
# second are untouched, which is the point of counting them apart: an analyst's ruling should
# move the analyst's own tallies and nothing the record had already decided.
#
# Round two: approve 182 -> 183 is 223 and 225 arriving and row 1 leaving; reject_named 10 -> 12
# is rows 210 and 1; not_answered 15 -> 12. Twelve rows remain open, CAD 1,973,298,085, and ten
# of those twelve can never be closed because the delivery ends underneath them.
#
# Round three adds a basis the split had never carried: unresolved, 2 rows, and not_answered
# falls 12 -> 10. Those ten are the rows the delivery ends underneath, and they are the whole of
# what Gate 2's bounded exception covers.
# Round four: not_answered 10 -> 0 and reject_none 10 -> 5, the fifteen becoming
# no_termination_declared. approve, decided, second and reject_named are all untouched, which is
# the same test as the outcome split above read from the other side: a rule about what counts as a
# retirement must not disturb a single answer about where a retirement went.
# Round five: reject_named 12 -> 14 and unresolved 2 -> 0, the same two rows. `unresolved` now
# describes no row in the delivery, and the vocabulary keeps it: a verdict that has been used and
# then withdrawn on evidence is part of the record, and removing the word would make the two
# rulings of 2026-08-14 unreadable.
# Row 23, imports:3004.20.00.65:1989-04, moved from `second` to `accept` on 2026-08-16.
# Finding 106 corrected the era its candidates were read in, which withdrew the second
# alternative and put 3004.20.00.64 in the proposal's place carrying this line's own
# wording word for word. The analyst ruled the proposal. approve 183 -> 184, second 13 -> 12.
# approve 184 -> 185 on 2026-08-17, one row and one basis. Row 231,
# imports:3004.50.99.30:1989-12, is the veterinary life Stage 1a now retires in its own right,
# and the analysts accepted its proposal 3004.50.99.50. Everything else here is untouched, which
# is the same test read from the other side: a rule about where one commodity ENDS must not move
# a single answer about where a retirement WENT.
# approve 185 -> 184 and reject_named 14 -> 15 on 2026-08-18: queue row 66 moved from
# accepting 3002.90.00.20 to naming 3002.49.00.20 instead. One decision changed category;
# the total is unchanged and no other basis moved.
EXPECTED_BASIS = {'approve': 184, 'decided': 89, 'no_termination_declared': 15,
                  'reject_named': 15, 'reject_none': 5, 'second': 12}

results = []
notes = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, "  -- " + detail if detail else ""))


def disclose(name, detail=""):
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, "  -- " + detail if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


# ---------------------------------------------------------------------------------------------
# Rule 1. Each refusal, provoked with input it must reject. Synthetic rows, because the delivery
# contains none of these shapes and a refusal never exercised is an assumption in a function's
# clothes.
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")

# The retiring code is in here deliberately. A self-link is only reachable for a code that
# exists, and every retirement does, so leaving it out let the "never traded" refusal catch the
# self-link first and the self guard was never exercised at all. Found by this control failing.
# ONE ENTRY PER LIFE, matching the shape the stage now builds. The stage reads which life could
# receive a given retirement; a map holding one life per code cannot answer that question, and
# holding one used to be the defect (finding 102).
LIVES = {"3002190000": [("201701", "202112", "Immunological products, nes")],
         "3002100090": [("198801", "201612", "the retirement itself")]}


def official_row(code="3002100090", outcome="silent_no_source", dests=""):
    return {"retiring_code": code, "last_period": "201612", "total_value_cad": "1000.00",
            "description": "a retirement", "outcome": outcome, "official_destinations": dests,
            "boundary": "201701"}


def answer_row(**changes):
    row = {"decision": "", "proposed_successor": "3002.19.00.00", "second_alternative": "",
           "correct_successor_if_rejected": "", "verdict": "ANALYST - a candidate is shown",
           "decided_by": "", "decided_on": "", "reason": ""}
    row.update(changes)
    return row


def provoke(official, answers, bases=None):
    _rows, problems = stage.resolve("imports", official, answers, {}, LIVES, bases or {})
    return problems


LINK = stage.link_id_for("imports", "3002100090", "201612")

record("a retirement settled by the record AND answered is refused",
       bool(provoke([official_row(outcome="decided", dests="3002190000")],
                    {LINK: answer_row(decision="accept")})["both"]),
       "one of the two answers would have to lose silently")
record("a retirement in neither the record nor the workbook is refused",
       bool(provoke([official_row()], {})["neither"]),
       "it would vanish from the crosswalk with nothing saying so")
record("a decision word the vocabulary cannot read is refused",
       bool(provoke([official_row()], {LINK: answer_row(decision="probably")})["unreadable"]),
       "a misspelling looks decided and reads as blank, which is defect D1's shape")
record("a reject naming neither a successor nor `none` is refused",
       bool(provoke([official_row()], {LINK: answer_row(decision="reject")})["no_target"]),
       "a reject records only that the proposal is wrong, never what is right")
record("a successor that never traded is refused",
       bool(provoke([official_row()],
                    {LINK: answer_row(decision="accept",
                                      proposed_successor="9999.99.99.99")})["unreal"]),
       "naming a destination that never traded puts a code in the crosswalk that does not exist")
record("a code named as its own successor is refused",
       bool(provoke([official_row()],
                    {LINK: answer_row(decision="accept",
                                      proposed_successor="3002.10.00.90")})["self"]),
       "a self-link is a chain that never terminates")
record("a successor named for a stoppage the delivery never called a termination is refused",
       bool(provoke([official_row()],
                    {LINK: answer_row(decision="accept")},
                    {("3002100090", "201612"): "trade_ceased_only"})["would_link"]),
       "the record says no transfer happened and the answer says where it went; a person settles "
       "that, and silently keeping either one would hide the disagreement")
record("a workbook row describing a retirement the delivery lacks is refused",
       bool(provoke([official_row()],
                    {LINK: answer_row(decision="accept"),
                     "imports:9999.99.99.99:2016-12": answer_row()}).get("stray")),
       "an answer with nothing to attach to is an answer about the wrong delivery")

# A blank is the one thing that must NOT be refused, and must NOT become a link.
_blank_rows, _blank_problems = stage.resolve(
    "imports", [official_row()], {LINK: answer_row(decision="")}, {}, LIVES, {})
record("a blank decision is held, never refused and never linked",
       not any(_blank_problems.values()) and len(_blank_rows) == 1
       and _blank_rows[0]["outcome"] == stage.HELD and _blank_rows[0]["successor"] == "",
       "outcome=%s, successor=%r" % (_blank_rows[0]["outcome"], _blank_rows[0]["successor"]))

# The converse of the refusal above, and the reason it is safe. An answer that names no successor
# agrees with the record rather than contradicting it, so it resolves rather than refusing. This
# is the shape all five answered rows in the delivery actually have.
_tc_rows, _tc_problems = stage.resolve(
    "imports", [official_row()],
    {LINK: answer_row(decision="reject", correct_successor_if_rejected="none")},
    {}, LIVES, {("3002100090", "201612"): "trade_ceased_only"})
record("a stoppage the delivery never called a termination resolves without a link",
       not any(_tc_problems.values()) and len(_tc_rows) == 1
       and _tc_rows[0]["outcome"] == stage.NOT_A_RETIREMENT and _tc_rows[0]["successor"] == "",
       "outcome=%s, successor=%r" % (_tc_rows[0]["outcome"], _tc_rows[0]["successor"]))
record("and the analyst's own cells survive it",
       _tc_rows[0]["decided_by"] == "" and _tc_rows[0]["basis"] == "no_termination_declared",
       "the outcome is replaced, the answer is not erased")

print()
print("Controls that MUST PASS (correct input must not be flagged):")

answers = {r["link_id"]: r for r in load(os.path.join(PROJECT, "decisions",
                                                      "stage2_decisions.csv"))}
all_rows = []

for flow in FLOWS:
    expect = EXPECTED[flow]
    resolved = load(os.path.join(PROJECT, "work", "stage2_resolved_%s.csv" % flow))
    official = load(os.path.join(PROJECT, "work", "stage1_official_%s.csv" % flow))
    inventory = load(os.path.join(PROJECT, "work", "commodity_inventory_%s.csv" % flow))
    traded = {r["hs_code"] for r in inventory}
    all_rows.extend(resolved)

    # Nothing lost, nothing invented, nothing duplicated.
    record("%s: every retirement appears exactly once" % flow,
           len(resolved) == expect["rows"] and len({r["link_id"] for r in resolved}) == len(resolved),
           "%d row(s), %d distinct link_id(s), expected %d"
           % (len(resolved), len({r["link_id"] for r in resolved}), expect["rows"]))
    record("%s: the retirement set is exactly Stage 1b's" % flow,
           {r["link_id"] for r in resolved}
           == {stage.link_id_for(flow, r["retiring_code"], r["last_period"]) for r in official},
           "compared as link_ids against %d official row(s)" % len(official))

    # THE SIX COLUMNS NO CONTROL READ, AND THE ONE THAT WAS HALF-READ. Finding 114. A corruption
    # sweep overwrote every column of this artefact on every row, first with a token and then with
    # blank, and ran the whole suite after each: flow, span_index, retiring_description, detail,
    # decided_by and decided_on survived both. `reason` survived garbling and was caught only when
    # blanked, so its content was unverified while its presence was not.
    #
    # decided_by and decided_on are the provenance of 220 analyst judgements. Two controls in
    # check_adjudication_queue.py do read them, but they read decisions/stage2_decisions.csv, the
    # source. The TRANSCRIPTION of those 220 signatures and dates into the delivered artefact was
    # verified by nothing, and blanking either column on all 319 rows was caught by nothing.
    #
    # Every one is rebuilt from the file the stage read it out of, never from the stage.
    candidate_spans = {(digits(r["retiring_code"]), r["last_period"]): r["span_index"]
                       for r in load(os.path.join(PROJECT, "work",
                                                  "stage1_candidates_%s.csv" % flow))}
    official_by_link = {stage.link_id_for(flow, r["retiring_code"], r["last_period"]): r
                        for r in official}
    wrong_flow, wrong_span, wrong_wording, no_detail = [], [], [], []
    wrong_signature, signed = [], 0
    for r in resolved:
        if r["flow"] != flow:
            wrong_flow.append(r["link_id"])
        if r["span_index"] != candidate_spans.get((digits(r["retiring_code"]),
                                                   r["last_period"]), ""):
            wrong_span.append(r["link_id"])
        entry = official_by_link.get(r["link_id"])
        if entry is None or r["retiring_description"] != entry["description"]:
            wrong_wording.append(r["link_id"])
        # `detail` is the column that carries the D1 protection in readable form. Asserting only
        # that it is non-empty left it caught when blanked and invisible when garbled, so the
        # sentence is rebuilt here from the outcome it is supposed to describe.
        #
        # THE VOCABULARY IS WRITTEN OUT HERE, per rule 2, and it is deliberately closed: a pair
        # this list does not hold fails rather than being waved through. `held` rows carry a
        # seventh phrasing taken from the verdict, and there are none in the delivery because
        # Stage 2 now closes every row. If one ever appears, this control fails and someone
        # extends the list on purpose, which is the outcome to want. An open list would have
        # accepted the new phrasing silently and asserted nothing about it.
        wanted = {
            ("analyst", "approve"): "the analyst accepted the proposal",
            ("analyst", "second"): "the analyst preferred the second alternative to the proposal",
            ("analyst", "reject_named"):
                "the analyst rejected the proposal and named %s instead" % r["successor"],
            ("analyst", "reject_none"):
                "the analyst rejected the proposal and recorded no successor in this chapter",
            # The edition, not the hop month. "at 201610" cited a concordance that does not
            # exist; the record is matched on the year it calls the code obsolete, and that
            # year names which of the two editions spoke. Finding 151.
            ("official_record", "decided"):
                "named outright by Canada's ten-digit concordance, %s to %s" % (
                    (entry or {}).get("last_period", "")[:4],
                    str(int((entry or {}).get("last_period", "0000")[:4] or 0) + 1)),
            ("delivery", "no_termination_declared"):
                "the delivery declares no termination for this line and the number was never "
                "reused, so trade ceased without the classification ending",
        }.get((r["authority"], r["basis"]))
        if wanted is None or (r["detail"] or "").strip() != wanted:
            no_detail.append(r["link_id"])
        # The analyst's own three columns, compared against the workbook they were typed into.
        # A row the workbook holds no written decision for must carry none of them, and that
        # asymmetry is asserted too: a signature on a row no person answered is a forged
        # provenance, and it is the shape a copy-down in a spreadsheet produces.
        #
        # THE SUBJECT IS "THE WORKBOOK HOLDS A DECISION", NOT "authority IS analyst", and the
        # difference is five rows. The five not_a_retirement rows carry authority=delivery,
        # because it is the delivery that establishes the classification never ended, and a
        # person still wrote and signed each of them. Keying the rule on the artefact's own
        # authority column would have called those five forged, and would also have let this
        # control be satisfied by the very column it is supposed to be independent of.
        source = answers.get(r["link_id"], {})
        answered = bool((source.get("decision") or "").strip())
        expected = {k: (source.get(k) or "").strip() if answered else ""
                    for k in ("decided_by", "decided_on", "reason")}
        if any((r[k] or "").strip() != expected[k] for k in expected):
            wrong_signature.append(r["link_id"])
        if answered:
            signed += 1
    record("%s: every row names the flow of the file it is written to" % flow, not wrong_flow,
           "%d row(s) disagree" % len(wrong_flow))
    record("%s: span_index is Stage 1a's, not a number this stage chose" % flow, not wrong_span,
           "%d row(s) rebuilt from stage1_candidates, %d disagree"
           % (len(resolved), len(wrong_span)))
    record("%s: the retiring wording is the official record's" % flow, not wrong_wording,
           "%d row(s) rebuilt from stage1_official, %d disagree"
           % (len(resolved), len(wrong_wording)))
    record("%s: every row's stated reason is the one its outcome implies" % flow, not no_detail,
           "%d row(s) rebuilt from (authority, basis) and the successor or boundary each names"
           % len(resolved)
           if not no_detail else "%d disagree: %s" % (len(no_detail), no_detail[:3]))
    record("%s: every signature, date and reason is the workbook's, transcribed" % flow,
           not wrong_signature,
           "%d signed row(s) compared word for word against decisions/stage2_decisions.csv, "
           "and %d record-settled row(s) required to carry no signature at all"
           % (signed, len(resolved) - signed)
           if not wrong_signature else "%d disagree: %s" % (len(wrong_signature),
                                                            wrong_signature[:3]))

    # Rebuilt from the official file, per rule 2, and asserted to the cent.
    value = sum(float(r["total_value_cad"]) for r in resolved)
    independent = sum(float(r["total_value_cad"]) for r in official)
    record("%s: the value reconciles to the cent" % flow,
           abs(value - expect["value"]) < 0.005 and abs(value - independent) < 0.005,
           "CAD {:,.2f}, expected CAD {:,.2f}".format(value, expect["value"]))

    counts = {}
    for r in resolved:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    record("%s: the outcome split is unchanged" % flow,
           all(counts.get(k, 0) == expect[k]
               for k in ("succeeded", "left_chapter", "held", "not_a_retirement", "unresolved")),
           "%s" % {k: counts.get(k, 0) for k in
                   ("succeeded", "left_chapter", "held", "not_a_retirement", "unresolved")})

    # Read back from the written file, per rule 10, and re-derived against Stage 1a's own column
    # rather than against this stage's memory of it. The two files must agree row for row on which
    # stoppages are not retirements, because a disagreement here is a link appearing or vanishing.
    declared_basis = {(r["retiring_code"], r["last_period"]): r["retirement_basis"]
                      for r in load(os.path.join(PROJECT, "work",
                                                 "stage1_candidates_%s.csv" % flow))}
    ceased = {stage.link_id_for(flow, code, last)
              for (code, last), b in declared_basis.items() if b == "trade_ceased_only"}
    got = {r["link_id"] for r in resolved if r["outcome"] == stage.NOT_A_RETIREMENT}
    record("%s: not_a_retirement is exactly what Stage 1a called trade_ceased_only" % flow,
           got == ceased,
           "%d row(s), rebuilt from stage1_candidates_%s.csv" % (len(ceased), flow))
    linked = [r["link_id"] for r in resolved
              if r["outcome"] == stage.NOT_A_RETIREMENT and r["successor"]]
    record("%s: no row that is not a retirement carries a link" % flow, not linked,
           "an event that did not happen cannot have a destination; %d here" % len(linked))

    # A successor exists on exactly the rows that claim one, and nowhere else.
    wrong_link = [r["link_id"] for r in resolved
                  if bool(r["successor"]) != (r["outcome"] == stage.SUCCEEDED)]
    record("%s: a link exists on exactly the rows that succeeded" % flow, not wrong_link,
           "%d row(s) disagree with their own outcome" % len(wrong_link))
    held_linked = [r["link_id"] for r in resolved if r["outcome"] == stage.HELD and r["successor"]]
    record("%s: no held row carries a link" % flow, not held_linked,
           "the released crosswalk read a blank as approval; %d here" % len(held_linked))

    # THE THREE SUCCESSOR-LIFE COLUMNS, WHICH HAD NO CONTROL AT ALL UNTIL 2026-08-16. Finding 102:
    # the stage kept one life per code, the one that ended latest, so 107 of 299 links carried a
    # span from a life that had already closed and 89 also carried its wording. Rebuilt here from
    # the inventory without calling the stage: the life that could receive a retirement is the
    # earliest one still open after it stopped, and where none is open it is the code's last.
    lives_by_code = {}
    for r in inventory:
        lives_by_code.setdefault(r["hs_code"], []).append(r)
    for entries in lives_by_code.values():
        entries.sort(key=lambda x: x["first_period"])
    wrong_era = []
    for r in resolved:
        if r["outcome"] != stage.SUCCEEDED or not r["successor"]:
            continue
        entries = lives_by_code.get(digits(r["successor"]), [])
        if not entries:
            continue
        open_after = [e for e in entries if e["last_period"] > r["last_period"]]
        receiving = min(open_after, key=lambda e: e["first_period"]) if open_after else entries[-1]
        if (r["successor_description"] != receiving["description"]
                or r["successor_first_traded"] != receiving["first_period"]
                or r["successor_last_traded"] != receiving["last_period"]):
            wrong_era.append(r["link_id"])
    record("%s: every successor is described by the life that could receive the trade" % flow,
           not wrong_era,
           "%d link(s) checked against the inventory's own lives"
           % sum(1 for r in resolved if r["outcome"] == stage.SUCCEEDED)
           if not wrong_era else "%d read another era: %s" % (len(wrong_era), wrong_era[:3]))
    # The one that motivated it, pinned by name. 3001.90.00.90 was published as "Heparin & its
    # salts" against a 1997-12 retirement, which is the reading the analyst had to refute by hand
    # at rows 223 and 225: the word is the SUBHEADING title carried onto the residual line.
    if flow == "imports":
        heparin = [r for r in resolved if r["link_id"] == "imports:3001.90.90.00:1997-12"]
        record("imports: the 3001.90.00.90 residual is not described as heparin",
               bool(heparin) and "Heparin" not in heparin[0]["successor_description"]
               and heparin[0]["successor_last_traded"] == "200112",
               "shown as %r, life %s..%s"
               % (heparin[0]["successor_description"][:40] if heparin else "MISSING",
                  heparin[0]["successor_first_traded"] if heparin else "",
                  heparin[0]["successor_last_traded"] if heparin else ""))

    unreal = [r["link_id"] for r in resolved if r["successor"] and digits(r["successor"]) not in traded]
    record("%s: every successor traded in this delivery" % flow, not unreal,
           "%d successor(s) rebuilt against %d inventory code(s)" % (len(unreal), len(traded)))
    selfish = [r["link_id"] for r in resolved
               if r["successor"] and digits(r["successor"]) == digits(r["retiring_code"])]
    record("%s: no code is its own successor" % flow, not selfish, "%d self-link(s)" % len(selfish))

    # THE LAYER ORDER. A retirement the record named is never the analyst's to answer.
    record_rows = [r for r in resolved if r["authority"] == "official_record"]
    decided = {stage.link_id_for(flow, r["retiring_code"], r["last_period"])
               for r in official if r["outcome"] == "decided"}
    record("%s: the record's own answers are taken from the record" % flow,
           {r["link_id"] for r in record_rows} == decided
           and len(record_rows) == expect["record"],
           "%d row(s) named outright, expected %d" % (len(record_rows), expect["record"]))
    crossed = [r["link_id"] for r in record_rows if r["link_id"] in answers]
    record("%s: no record-named retirement reached the workbook" % flow, not crossed,
           "asking would invite an answer that outranks its own evidence; %d did" % len(crossed))

    # The hold, and the analyst's right to answer over it.
    overrode = [r for r in resolved if r["overrode_a_hold"] == "yes"]
    # Rows the record rules are excluded on both sides. Their verdict reads DO NOT DECIDE only
    # because the not-a-retirement rule now writes it there, and counting the five answers taken
    # before that rule existed as overrides would record a recklessness that did not happen.
    expected_over = {lid for lid, a in answers.items()
                     if lid.startswith(flow + ":") and (a.get("decision") or "").strip()
                     and (a.get("verdict") or "").startswith("DO NOT DECIDE")
                     and lid not in ceased}
    record("%s: every answer given over a hold is marked as one" % flow,
           {r["link_id"] for r in overrode} == expected_over
           and len(overrode) == expect["overrode"],
           "%d answered while held, expected %d" % (len(overrode), expect["overrode"]))

print()
print("Across both flows: the answers, counted independently from the workbook.")

basis = {}
for r in all_rows:
    basis[r["basis"]] = basis.get(r["basis"], 0) + 1
record("the basis split matches the workbook counted independently",
       basis == EXPECTED_BASIS, "%s" % dict(sorted(basis.items())))

# Recount the workbook without reference to the stage's output. Rows the record rules are counted
# APART rather than excused: the identity must still hold exactly on every other row, and the
# rows ruled by the record must account for the whole of the difference. An answer that simply
# stopped arriving would show up here as a mismatch, which is what this control is for.
ceased_ruled = [r for r in all_rows
                if r["basis"] == "no_termination_declared" and r["link_id"] in answers]
written = {}
written_ceased = {}
for lid, a in answers.items():
    word = stage.normalise_decision((a.get("decision") or "").strip())
    bucket = written_ceased if lid in {r["link_id"] for r in ceased_ruled} else written
    bucket[word or "blank"] = bucket.get(word or "blank", 0) + 1
record("every workbook answer reached the resolved file",
       written.get("approve", 0) == basis.get("approve", 0)
       and written.get("second", 0) == basis.get("second", 0)
       and written.get("reject", 0) == basis.get("reject_named", 0) + basis.get("reject_none", 0)
       and written.get("blank", 0) == basis.get("not_answered", 0)
       and sum(written_ceased.values()) == len(ceased_ruled),
       "workbook %s; ruled by the record instead %s"
       % (dict(sorted(written.items())), dict(sorted(written_ceased.items()))))

# Replacing an outcome must not destroy the answer underneath it. The five rows here that the
# analyst had already ruled carry full prose reasons, and those reasons are the record of a
# judgement that agreed with this rule before it existed.
erased = [r["link_id"] for r in ceased_ruled
          if (answers[r["link_id"]].get("reason") or "").strip() and not r["reason"]]
record("no answer was erased by the record ruling over it", not erased,
       "%d of %d rows ruled by the record carry an answer, and none lost it"
       % (len([r for r in ceased_ruled if (answers[r["link_id"]].get("decision") or "").strip()]),
          len(ceased_ruled)))

open_rows = [r for r in all_rows if r["outcome"] in (stage.HELD, stage.UNRESOLVED)]
open_value = sum(float(r["total_value_cad"]) for r in open_rows)
record("every open row states why it is open", all(r["detail"] for r in open_rows),
       "%d open row(s), CAD {:,.0f}".format(open_value) % len(open_rows))

# Rule 8: a symptom, stated rather than tested. This check cannot judge whether a successor is
# the RIGHT one; only that it was answered, exists, and was transcribed faithfully.
disclose("this check cannot judge whether a successor is correct",
         "it verifies transcription, existence and reconciliation. Whether 3004.90.90 is the "
         "right home for 3004.90.00 is the analyst's judgement and is recorded, not tested")
vetoed_pairs = set()
for flow in FLOWS:
    for r in load(os.path.join(PROJECT, "work", "stage1_ranked_%s.csv" % flow)):
        if r["vetoed_by"]:
            vetoed_pairs.add((flow, r["retiring_code"], r["last_period"], r["candidate"]))
over_veto = [r["link_id"] for r in all_rows if r["successor"]
             and (r["flow"], digits(r["retiring_code"]), r["last_period"],
                  digits(r["successor"])) in vetoed_pairs]
disclose("successors chosen over a meaning-gate veto",
         "%d. The analyst may overrule a gate and the workbook labels every such candidate; "
         "this is disclosure, not a fault" % len(over_veto))

_decided_ids = {d["link_id"] for d in load(os.path.join(PROJECT, "decisions",
                                                       "stage2_decisions.csv"))
                if (d.get("decision") or "").strip()}
# GATE 2's TWO AMBIGUITIES, MADE EXPLICIT. Finding 131, 2026-08-18.
#
# Gate 2 reads "Zero rows left undecided. No exception." Ten rows carry an empty decision cell,
# CAD 337,143,882, so on the cell reading the gate fails and on the event reading it passes:
# every one of them is settled, by the delivery rather than by a person. Which reading is meant is
# the analyst's to state and is NOT decided here. What is asserted here is the thing that makes the
# question safe either way, because it is what would make the empty cells matter if it stopped
# being true.
#
# The 15 rows the queue marks NOT A RETIREMENT are split 10 blank and 5 answered, which is the
# same category answered two ways. It is harmless only because the answers are INERT: all 15
# resolve not_a_retirement on authority=delivery, so the five who received a decision got the same
# outcome as the ten who did not. If an answer on one of these ever changed an outcome, the split
# would stop being a record-keeping untidiness and become a live inconsistency.
_queue = {r["link_id"]: r for r in load(os.path.join(PROJECT, "decisions",
                                                     "stage2_adjudication_queue.csv"))}
_resolved = {r["link_id"]: r for r in all_rows}
_nar = [l for l, q in _queue.items() if q["status"].startswith("NOT A RETIREMENT")]
_nar_bad = [l for l in _nar if l in _resolved
            and (_resolved[l]["outcome"] != "not_a_retirement"
                 or _resolved[l]["authority"] != "delivery")]
record("a row the queue calls no retirement is settled by the delivery, answered or not",
       not _nar_bad,
       "%d such row(s); the %d that carry a decision reach the same outcome as the %d that do not"
       % (len(_nar), sum(1 for l in _nar if l in _decided_ids), 
          len(_nar) - sum(1 for l in _nar if l in _decided_ids))
       if not _nar_bad else "%d differ: %s" % (len(_nar_bad), _nar_bad[:4]))

# And the second: two rows the queue still marks HELD carry decisions. That is allowed, because a
# hold is advice about evidence not yet read and the analyst may overrule it, but it may never be
# silent. Rows 213 and 222 each carry a full written argument and overrode_a_hold=yes.
_held = [l for l, q in _queue.items() if q["status"].startswith("HELD")]
_silent = [l for l in _held if l in _decided_ids
           and _resolved.get(l, {}).get("overrode_a_hold") != "yes"]
record("a held row that was decided anyway says so", not _silent,
       "%d held row(s), %d decided, every one recording overrode_a_hold=yes"
       % (len(_held), sum(1 for l in _held if l in _decided_ids))
       if not _silent else "%d decided a hold silently: %s" % (len(_silent), _silent[:4]))

# The event reading of the gate, asserted outright: nothing is both undecided and unsettled.
_open = [l for l in _queue if l not in _decided_ids
         and _resolved.get(l, {}).get("outcome") in (None, "", "held", "open", "undecided")]
# GATE 2 CLAUSE 5: THE TAIL IS DISCLOSED. Finding 134, 2026-08-18.
#
# A row resolved not_a_retirement on `no_termination_declared` rests on an ABSENCE: Statistics
# Canada has not said the line was withdrawn. That is the right call on this delivery and it is not
# permanent, because a later delivery can say so and turn the row into a retirement needing a
# successor. Seven of the fifteen stopped within three months of 2026-06. The gate does not count
# them against the release; it requires them listed, and this asserts the list is complete and
# holds nothing else.
_tail_path = os.path.join(PROJECT, "gate1", "gate2_tail_disclosure.csv")
_should = {r["link_id"] for r in all_rows if r.get("basis") == "no_termination_declared"}
if os.path.exists(_tail_path):
    _listed = {r["link_id"] for r in load(_tail_path)}
    _tail_rows = {r["link_id"]: r for r in load(_tail_path)}
else:
    _listed, _tail_rows = set(), {}
record("every row resting on an absent termination notice is disclosed",
       _listed == _should and bool(_should),
       "%d row(s) listed in gate1/gate2_tail_disclosure.csv, exactly the ones whose basis is "
       "no_termination_declared" % len(_listed)
       if _listed == _should and _should
       else "listed %d, should be %d; missing %s; extra %s"
            % (len(_listed), len(_should), sorted(_should - _listed)[:3],
               sorted(_listed - _should)[:3]))
# And each must say how exposed it is, because that is the whole reason for the list.
_no_distance = [l for l, r in _tail_rows.items()
                if not str(r.get("months_before_delivery_end") or "").strip()
                or not (r.get("what_would_change_it") or "").strip()]
record("every disclosed row states its distance from the delivery end and what would change it",
       not _no_distance,
       "%d row(s), each carrying months_before_delivery_end and what_would_change_it"
       % len(_tail_rows)
       if not _no_distance else "%d incomplete: %s" % (len(_no_distance), _no_distance[:3]))

record("no row is both undecided and unsettled", not _open,
       "every queue row reaches an outcome, whoever supplied it"
       if not _open else "%d row(s): %s" % (len(_open), _open[:4]))


print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed),
                                                  len(failed)))
print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("Stage 2 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 2 is validated. Every answer carried, nothing invented, and the open rows are open.")
