"""
Build the adjudication queue and the answer sheet that goes with it.


Inputs:
    work/stage1_review_{imports,exports}.csv    produced by pipeline/s04_stage1c_rank.py
    work/stage1_ranked_{imports,exports}.csv
    work/commodity_inventory_{imports,exports}.csv

Output:
    decisions/stage2_adjudication_queue.csv    the evidence, regenerated freely
    decisions/stage2_decisions.csv             the answer sheet, written once and protected
    decisions/README_adjudication_queue.md


WHO THIS FILE IS FOR
--------------------
The analyst, and after them the reviewers and collaborators who will be sent it. That second
audience decides almost every choice below.

It must be readable without the code. Someone opening it in a spreadsheet has no access to the
pipeline, the inventory or the rules file, so everything needed to decide a row is IN the row:
both descriptions in full, the runner-up and its description, what the official record said,
what meaning removed and why. Nothing requires a lookup.

Codes are written with separators here, 3002.10.00.90 rather than 3002100090, because a person
reads them. Stage 0 established the opposite rule for the pipeline's own internal form, and this
is the boundary where the separators go back on: the last file before a human, and the released
outputs. Nothing downstream reads this file until Stage 2, which strips them again.

Column names say what they mean rather than what the code calls them. There is no risk_tier
here, there is priority. There is no top_candidate, there is proposed_successor.


WHY THERE ARE TWO FILES AND NOT ONE
-------------------------------------
The first version put the evidence and the blank decision columns in one file. That file had to
be both freely regenerable, because it is generated, and never overwritten, because it holds
judgement. Those are opposite requirements, and every guard written to reconcile them was
patching over the contradiction instead of removing it.

A spreadsheet settled it. Opening the combined file in Excel and saving rewrote 1988-12 as
Dec-88, 1989-01 as Jan-89, and 49753998.00 as 49753998. Nothing was lost that time because no
decision had been entered, but the same round trip would happen dozens of times across 217 rows.

So the queue is evidence and holds nothing a person wrote. A spreadsheet may mangle it freely
and the pipeline simply rebuilds it. The answer sheet holds judgement, is written once, and is
joined to the queue on the row number.

The answer sheet also repeats the evidence, so it can be sent to a collaborator on its own. That
means it does carry dates and decimals, and a spreadsheet will reformat some of them. That is
harmless, and the reason is precise rather than a shrug: nothing reads those columns back. What
must survive a round trip is the row number and the five columns a person fills, and none of
those is a date or a number a spreadsheet touches. The rule is enforced by
checks/check_adjudication_queue.py and is deliberately not restated as a list here, because an
earlier version of this comment did restate it, went stale the day the dates were added, and
sat here asserting the opposite of what the code did.

A reason is required, not optional. The 2026-08 correction round in the released crosswalk
turned on the difference between a row that was decided and a row that was merely unmarked,
because software read an unmarked row as an approval and links entered the data that nobody had
decided. An empty decision means undecided, and Stage 2 must refuse to build rather than assume.


THE HELD ROWS ARE PRESENT AND MUST NOT BE DECIDED
---------------------------------------------------
Twenty-one rows carry status "held". A correlation table could answer them and none has been
extracted yet, so a person deciding them now risks being overruled by a document later. They
are included rather than removed, because a queue that silently omits 21 rows worth
CAD 30,032,082,384 is not a queue anyone should trust. They sort last and say why.
"""

import csv
import difflib
import json
from collections import Counter, defaultdict
import os as _os
import sys as _sys
import re as _re_score
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
DECISIONS_DIR = PROJECT_ROOT / "decisions"

PRIORITY_NAMES = {
    0: "every candidate was ruled out on meaning",
    1: "a list lost an item, or one code is the leftover case of the other",
    2: "the wording matches closely but the meaning does not",
    3: "the closest wording was ruled out on meaning",
    4: "two candidates are almost equally close",
    5: "no candidate is close on wording",
    6: "the wording and the meaning both match, please spot check",
}


def dotted(code):
    """3002100090 becomes 3002.10.00.90, and 30021000 becomes 3002.10.00."""
    code = (code or "").strip()
    if len(code) == 10:
        return "%s.%s.%s.%s" % (code[:4], code[4:6], code[6:8], code[8:])
    if len(code) == 8:
        return "%s.%s.%s" % (code[:4], code[4:6], code[6:])
    return code


def next_month(period):
    year, mon = int(period[:4]), int(period[4:])
    return "%04d%02d" % (year + 1, 1) if mon == 12 else "%04d%02d" % (year, mon + 1)


def month(period):
    return "%s-%s" % (period[:4], period[4:]) if len(period) == 6 else period


# WHERE ONE COMMODITY ENDS AND THE NEXT BEGINS. Owned by Stage 1a, called rather than copied.
# This file held its own REUSE_GAP_MONTHS = 60 and its own merge loop beneath it, so it was not
# sharing even the threshold, let alone the rule. See s02_stage1_candidates.continues_the_span for
# what that cost on 2026-08-17.
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from s02_stage1_candidates import trading_spans  # noqa: E402


def _months(period):
    return int(period[:4]) * 12 + int(period[4:6]) - 1


def code_spans(flow):
    """Every trading span of every code, split where the number was reused.

    THIS RETURNED ONE ENVELOPE PER CODE UNTIL 2026-08-11, a single earliest-first and
    latest-last. For a reused number that describes neither life. 3002.90.10 showed as
    "1988-01 to 2026-06", thirty-eight years of apparent continuous trade, when it actually ran
    1988-01 to 1988-12 as blood products and then, as different goods entirely, 1997-12 onward.
    Eleven places in the artefact printed dates like that, and a reader judging whether a
    successor existed at the boundary was being shown a life the code never had.

    The candidate selection was made span-aware the same day and the display was not, which is
    the ordinary way a fix fails to travel.
    """
    grouped = {}
    for row in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
        grouped.setdefault(row["hs_code"], []).append(row)
    # The whole records, not just their intervals, because the rule reads the wording too.
    return {code: trading_spans(records) for code, records in grouped.items()}


def span_shown(spans, code, stopped):
    """The span of a candidate that is relevant to THIS retirement.

    The earliest one still running after the retirement, because that is the span that made the
    code a candidate and the span continuity was judged against. Showing any other would explain
    neither the proposal nor the veto.
    """
    alive = [s for s in spans.get(code, []) if s[1] > stopped]
    if alive:
        return min(alive)
    return spans.get(code, [("", "")])[-1]


def description_shown(lives, code, stopped):
    """The wording a candidate carried in the life that could receive THIS retirement.

    The mirror of span_shown, and missing for as long as that has existed. Eight rows printed a
    description from a life that had already closed, and on one of them the proposal read
    "Penicillin V" while the life that receives the trade reads "Amoxycillin", the same commodity
    as the retirement. A reader cannot judge a link from the wrong era's words.
    """
    entries = lives.get(code) or []
    alive = [e for e in entries if e[1] > stopped]
    if alive:
        return min(alive)[2]
    return entries[-1][2] if entries else ""


def months_between(earlier, later):
    """Whole months from one YYYY-MM to another. Both arguments carry the dash.

    Written because months_gap takes raw YYYYMM periods and silently returns arithmetic on
    nonsense when handed the dashed form the artefact prints: int("2005-01"[4:]) is int("-01").
    Two date formats live in this file, one for the pipeline and one for the reader, and only a
    separate function makes it obvious which is being used.
    """
    if not (earlier and later):
        return None
    def to_months(text):
        return int(text[:4]) * 12 + int(text[5:7]) - 1
    return to_months(later) - to_months(earlier)


def months_gap(retiring_last, successor_first):
    """Months between the retirement and the successor starting. Zero means no gap.

    Takes RAW periods, YYYYMM without a dash. See months_between for the printed form.
    """
    if not successor_first:
        return ""
    def to_months(period):
        return int(period[:4]) * 12 + int(period[4:])
    year, mon = int(retiring_last[:4]), int(retiring_last[4:])
    boundary = "%04d%02d" % (year + 1, 1) if mon == 12 else "%04d%02d" % (year, mon + 1)
    return max(0, to_months(successor_first) - to_months(boundary))


# THRESHOLDS.md section 3 sets 0.50 as the line below which a link goes to an analyst rather
# than being acted on. That line has to bind what this file recommends, not only how Stage 1c
# labels the outcome, or the method says one thing and the artefact nudges towards another.
REVIEW_THRESHOLD = 0.50

# With the subheading gone, a proposal whose meaning words overlap the retiring description's
# by less than this, counted as the shared words over the words either carries, has the shape
# of a departure from the chapter, and the suggested decision is "none" with the chapter-exit
# note rather than a link. On this delivery the shape fires on 10 rows by wording, the record
# names five departures outright, and every known departure is among them; the control in
# checks/check_adjudication_queue.py pins those counts. It is a hypothesis for a person, not a
# finding. Set by judgement. Named 2026-08-26; it was a bare literal in suggest().
LEFT_CHAPTER_MEANING = 0.40

# A proposal whose wording match reaches this is not offered a leftover line beside it unless
# a term was swapped: clutter in an artefact meant for reading is a cost like any other. The
# same line as stage 1c's HIGH_THRESHOLD, reproduced, not chosen afresh. Named 2026-08-26; it
# was a bare literal.
STRONG_PROPOSAL = 0.85

# How soon a proposal must itself stop trading before it is read as a co-casualty rather than a
# step in a chain. Of the 62 proposals that are themselves retiring, 12 fall within two years and
# the remaining 50 range from 28 to 348 months, so the line sits in a gap rather than through a
# cluster: the within-group tops out at 24 and the next value is 28, nothing at 25, 26 or 27.
#
# Re-measured 2026-08-18, finding 137, and ALL FOUR figures were stale while the reasoning was
# not. It read 61 / 13 / 48 / "twenty-five months to fifteen years". Both readings are
# internally consistent, 61 = 13 + 48 and 62 = 12 + 50, so nothing was miscounted at the time:
# the delivery and the rules moved underneath it and nothing re-derived the paragraph. The
# fifteen-year figure had drifted furthest, to 29 years. What justifies 24 is not any of the
# four counts but the gap, and that is now a control rather than a sentence.
CO_CASUALTY_MONTHS = 24

# A code still trading in the delivery's last month has not stopped; the data has. Measuring
# "stops within two years" without asking that first called 3003.49.00 a co-casualty of two
# retirements because it runs to 2026-06, which is simply where the file ends.
def still_running(last_month, delivery_end):
    return bool(last_month) and last_month >= delivery_end


# THE HYPOTHESIS BELOW, KEPT AS ITS OWN NAME BECAUSE THE RECORD IS ALLOWED TO WITHDRAW IT.
#
# "The goods may have left Chapter 30" is a guess about where trade went, drawn from the
# subheading vanishing and no wording being close. The WCO correlation can refute it outright by
# naming a destination INSIDE the chapter, and on 2026-08-14 it did so on seven rows while this
# sentence stayed on them: the sheet told the analyst that the WCO had chosen 3006.92.00.00 and,
# in the next column, that the goods may have left the chapter altogether. The code that takes
# the sentence back splits on this exact string, so it is written once and used in three places.
CHAPTER_EXIT_SUFFIX = ", so the goods may have left Chapter 30 entirely"


def suggest(subheading_survives, meaning, held=False, has_proposal=True, wording=None,
            swaps_a_term=False, swapped_from="", swapped_to=""):
    """What the evidence suggests, for a person to accept or reject.

    Every row used to propose a successor and none ever proposed that there is not one, so the
    artefact only knew how to say "here is the link" and quietly pushed towards approval.

    A departure from the chapter has a shape: the subheading disappears entirely and nothing
    left in the chapter shares the goods' meaning. Measured on this delivery that shape fires on
    19 rows and catches all 5 codes already settled as having left for heading 38.22.

    So it is a hypothesis, not a finding, and roughly a quarter of what it flags is real. It has
    to be that way: heading 38.22 is not in the delivery, so the destination is invisible and the
    same shape also fits a code that was merely renamed.

    A held row is still given a suggestion. An earlier version withheld it on the reasoning that
    the record had not spoken, which silenced the rule on four of the five codes already known to
    have left the chapter, because those four are held. The hold governs when a row may be
    DECIDED. It has no bearing on what the evidence already suggests.

    Where nothing survived the gates there is no proposal, so there is nothing to approve and
    nothing that says the goods left the chapter either. That is unresolved, and saying approve
    on an empty proposal is what this function did until 2026-08-11.

    Below the review threshold nothing is recommended. Eleven rows once said "no candidate is
    close on wording" and suggested approving one anyway, the weakest at 0.0714, four of them on
    a sole surviving candidate. The published method sends those to a person without a
    recommendation, so that is what the column now says. The proposal itself does not disappear:
    the code, both descriptions, both sets of dates and both measures stay on the row, because
    withholding the candidate would hide the very thing the reader is being asked to judge.

    Two different findings can both produce "none", and collapsing them loses the more
    interesting one. "The goods may have left Chapter 30" is a claim about where the trade went.
    "The wording is below the review threshold" is an absence of evidence. Measured 2026-08-11,
    23 of 30 rows saying "none" were indistinguishable between the two. So the word stays, the
    decision vocabulary stays, and the reason is reported alongside it.
    """
    if not has_proposal:
        return "unresolved", "nothing survived the gates, so there is nothing to judge"
    left_chapter = subheading_survives == "no" and meaning < LEFT_CHAPTER_MEANING
    below = wording is not None and wording < REVIEW_THRESHOLD
    if left_chapter and below:
        return "none", ("the subheading is gone and no wording is close" + CHAPTER_EXIT_SUFFIX)
    if left_chapter:
        return "none", ("the subheading is gone and nothing left in the chapter shares the "
                        "meaning" + CHAPTER_EXIT_SUFFIX)
    if below:
        return "none", ("a candidate exists but its wording is below the %.2f review threshold, "
                        "so the method sends it on without a recommendation"
                        % REVIEW_THRESHOLD)
    if swaps_a_term:
        return "none", ("SAME FRAME, DIFFERENT TERM: %s against %s. The wording match is scoring "
                        "the boilerplate these two share, not the word that says what the goods "
                        "are." % (swapped_from or "?", swapped_to or "?"))
    return "approve", ""


def carved_out_of(lives, distinctive, retiring_code, period, describe, successor):
    """Was the proposed successor's distinguishing term carved out of this residual line?

    A residual line means "everything in this subheading except the ones named separately". If a
    sibling was alive in the same subheading at the same moment and named term T, then this line
    was defined as the goods that are NOT T, and a successor that turns on T inverts its meaning.

    FLAGGED, NEVER REMOVED, exactly as the swapped-term rule is. It fires on two rows in the
    whole delivery and both were argued over by hand, which is far too thin a base to let it
    take a candidate out of a field.

    THREE CONSTRAINTS, each of which a first version lacked and each of which cost it a false
    positive when it was run against all 94 residual retirements:

      The successor is never its own carve-out sibling. Where a block is renumbered in place the
      successor sits in the same subheading, and without this the rule says a code carved a term
      out of the line it succeeds. Row 201.

      The term must be distinctive, by the same under-five-percent test substance_index() uses.
      Firing on "human", "use" and "other" refuted two links the analyst had already accepted,
      rows 63 and 152.

      A residual successor is never refuted. Residual to residual is the CORRECT shape, and
      without this the rule refuted row 223, which is a link the analyst accepted on the record.

    It does NOT overlap specific_vs_residual. That gate compares the two descriptions and needs
    an exclusionary marker on exactly one side; it deliberately refuses to read "nes" as
    exclusionary, because "X" against "X, nes" is a succession and reading it as a complement
    removed the correct successor on 5 retirements worth CAD 118,352,487. This reads the source
    subheading's sibling structure and never examines a link whose retiring line is specific, so
    those five are out of its reach twice over.
    """
    retiring_text = describe(retiring_code)
    successor_text = describe(successor)
    if not _gates.carries_residual_marker(_expand(retiring_text or "")):
        return "", ""
    if _gates.carries_residual_marker(_expand(successor_text or "")):
        return "", ""
    own = _gates.content_words(_expand(retiring_text or ""))
    wanted = _gates.content_words(_expand(successor_text or ""))
    for code, spans in sorted(lives.items()):
        if code[:6] != retiring_code[:6] or code in (retiring_code, successor):
            continue
        if not any(first <= period <= last for first, last, _text in spans):
            continue
        sibling = describe(code)
        hit = sorted(((_gates.content_words(_expand(sibling)) - own) & distinctive) & wanted)
        if hit:
            return ", ".join(hit), code
    return "", ""


def month_after(period):
    """The YYYYMM that follows. Written here because months_gap takes two periods and this needs
    one, and because a widening is only evidence when it is contiguous with the retirement."""
    year, part = int(period[:4]), int(period[4:])
    return "%04d%02d" % (year + 1, 1) if part == 12 else "%04d%02d" % (year, part + 1)


def widened_at_the_boundary(lives, distinctive, period, survivors, proposal):
    """Did some OTHER surviving candidate's own published scope widen at this exact boundary?

    Intends  "a leftover line was enlarged to absorb the goods whose own line was deleted".
    Computes "an unvetoed candidate that is not the proposal keeps its number across this
              boundary, carries a residual marker on both sides of it, and its wording gains at
              least one distinctive word while keeping at least one".

    WHY IT EXISTS. Text similarity reads a candidate's wording; it cannot read that the wording
    CHANGED, and a residual widening is the strongest structural evidence this delivery offers.
    3002.90.00.90 gained "antisera, vaccines, cell cultures" in 2022-01, the month 3002.19 was
    deleted, and only two codes in the whole of Chapter 30 changed wording at that boundary. The
    ranker put it 18th of 22 on 0.1646 and nothing vetoed it. Finding 100.

    FLAGGED, NEVER RANKED, in the same shape as the carve-out rule and the swapped-term rule. It
    may not lift a candidate: the layer order is that text ranks and meaning may only veto, and a
    widening is evidence about meaning, so promoting on it would let the meaning layer choose a
    successor. It changes no proposal, removes nothing, and reorders nothing.

    FOUR CONSTRAINTS, and the residual one is what keeps it honest:

      The candidate is never the proposal. If the ranker already chose it there is nothing to say.

      Only a vetoed-free candidate. A gate that removed a candidate on meaning outranks this;
      resurrecting one through a warning would invert the layer order it exists to respect.

      The change must be AT this boundary, contiguous: a life ending in the retirement's own last
      month and the next beginning the month after. A re-wording elsewhere in a code's history
      says nothing about this retirement.

      BOTH lives carry a residual marker, and the wording gains a distinctive word while keeping
      one. Without the residual test the rule fires on 3004.50.99.30, which at 1990-01 went from
      "Vitamins & their derivs, nes, for vet use" to "Multivitamins not mixed with o supplements,
      for human use": different goods on the same number, which is reuse in place rather than a
      widening, and the opposite direction on use. Without the kept-and-added test it fires on
      the 40 pure re-wordings, mostly the 2002-01 pass that restated the whole chapter.

    Measured over the delivery it flags 5 retirements carrying CAD 2,685,731,855. Four are the
    3002.90 residual at the 2017 and 2022 revisions. The fifth offers the VETERINARY hormones
    residual against a human epinephrine line, which is a real widening pointed at the wrong use
    and a reader dismisses it on sight; it is left in rather than tuned out, because the constraint
    that would remove it would be fitted to this delivery rather than argued from the tariff.
    """
    for candidate in survivors:
        code = candidate["candidate"]
        if code == proposal:
            continue
        entries = sorted(lives.get(code) or [])
        for before, after in zip(entries, entries[1:]):
            if before[1] != period or after[0] != month_after(period):
                continue
            if before[2] == after[2]:
                continue
            if not (_gates.carries_residual_marker(_expand(before[2]))
                    and _gates.carries_residual_marker(_expand(after[2]))):
                continue
            old = _gates.content_words(_expand(before[2].lower()))
            new = _gates.content_words(_expand(after[2].lower()))
            added = sorted((new - old) & distinctive)
            if not (old & new and added):
                continue
            return code, ", ".join(added), candidate["rank"]
    return "", "", ""


def aggregation_note(retiring, successor, retiring_text, successor_text):
    """Whether the successor is a broader bucket rather than an equivalent code.

    Two independent signals, and either one is worth telling a reviewer about.

    STRUCTURAL. The last two digits are the statistical breakout, and 00 is the parent. A code
    ending 10 succeeded by one ending 00 has been folded into the bucket above it.

    WORDING. The successor states strictly fewer things. "Medicaments nes, in dosage, for human
    use" against "Medicaments nes, in dosage" drops the human qualifier, so the successor also
    carries veterinary trade the predecessor never did.

    This matters far more for exports. Domestic exports are recorded at eight digits and imports
    at ten, so exports have less room for statistical breakouts, and when one retires its trade
    usually collapses into the parent. Measured on this delivery: 14 of 40 export rows against
    5 of 198 import rows.

    The link is not wrong when this fires. The trade really did go there. What is lost is
    resolution, and a family traced across such a boundary stops distinguishing what the
    predecessor distinguished. That is a limitation to disclose, not an error to correct.
    """
    if not successor:
        return "no"
    reasons = []
    if retiring[-2:] != "00" and successor[-2:] == "00":
        reasons.append("the successor ends 00, which is the parent of the breakout the retired "
                       "code sat in")
    retiring_words = meaning_word_set(retiring_text)
    successor_words = meaning_word_set(successor_text)
    if successor_words and successor_words < retiring_words:
        missing = sorted(retiring_words - successor_words)
        reasons.append("the successor drops %s, so it also covers trade the retired code did not"
                       % ", ".join('"%s"' % w for w in missing[:4]))
    # Only the flag is emitted. Which of the two signals fired is not reported, because the
    # retired and successor descriptions sit side by side in the same row and a reader can see
    # what changed. The reasoning is kept here so it can be recovered if that judgement changes.
    return "yes" if reasons else "no"


FILLER = {"not", "elsewhere", "specified", "nes", "other", "than", "whether", "or", "for", "of",
          "the", "and", "in", "to", "a", "an", "with", "on", "o", "t"}


def meaning_word_set(text):
    import re as _re
    cleaned = _re.sub(r"\s+", " ", _re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()
    return frozenset(w for w in cleaned.split() if w not in FILLER)


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# link_id identifies the retirement itself, and it is the only key anything joins on.
#
# The queue is sorted for reading: held rows last, then by risk, then by value. That order is a
# presentation choice and it moves whenever the ranking changes. Measured on 2026-08-11, changing
# what the suggestion column recommends moved 214 of 238 row numbers onto different retirements.
# Had the answer sheet still been joined on "row", every decision made before that change would
# have silently reattached to the wrong code. No error, no warning, a corrupt crosswalk.
#
# flow, code and the month the code stopped trading are properties of the retirement. They do not
# move when the sort does. The month is what separates the two retirements of 3002.90.20 and
# 3003.31.00, which reuse the same code number decades apart; span_index cannot do it, because
# until 2026-08-11 it was defaulted to 1 for every row in this file's inputs.
COLUMNS = [
    "link_id",
    "row", "verdict", "status", "priority", "why_this_needs_you", "flow",
    "retiring_code", "retiring_description", "last_traded", "value_cad",
    "proposed_successor", "proposed_successor_description",
    "proposed_successor_first_traded", "proposed_successor_last_traded",
    "successor_began_at_the_boundary",
    "successor_is_more_aggregate", "months_gap", "gap_named_by_the_record",
    "suggested_decision", "why_not_recommended",
    "wording_match", "shared_meaning_words",
    "runner_up", "runner_up_description",
    "runner_up_first_traded", "runner_up_last_traded", "runner_up_wording_match",
    "other_candidates_considered", "official_record",
    "closest_removed_candidate", "closest_removed_description",
    "closest_removed_first_traded", "closest_removed_last_traded",
    "closest_removed_wording_match", "closest_removed_why",
    "candidates_removed_on_meaning",
    "record_overruled_gate",
    "official_record_note",
    "record_narrowed_note",
    # What the tier narrowing never offered. Not a removal and not a rejection: these codes were
    # alive and were simply outside the tightest rung of the structural ladder, so no gate ever
    # saw them. On 220 retirements no official source speaks, which makes that narrowing the only
    # thing standing between a code and consideration, and until now it was invisible.
    "best_candidate_passing_every_rule", "best_candidate_description",
    "best_candidate_wording_match", "best_candidate_is_the_leftover_line",
    "how_they_relate", "family_of_the_retiring_code", "family_evidence",
    "class_residual_available", "class_residual_description",
    "class_residual_wording_match",
    "same_wording_reappears_at", "same_wording_reappears_from", "same_wording_gap_months",
    "substance_named_again_later",
    "successor_also_retires", "chain_ends_at", "chain_hops",
    "successor_swaps_a_term", "term_in_the_retiring_code", "term_in_the_successor",
    "successor_was_carved_out_of_it", "carved_out_term", "carved_out_by",
    "a_leftover_line_widened_here", "widened_line", "widened_line_added_terms",
    "widened_line_rank",
    "successor_co_traded_months",
    "codes_never_considered", "closest_never_considered", "closest_never_considered_description",
    "closest_never_considered_wording_match",
]

# The answer sheet. Separate from the queue because Excel rewrote 1988-12 as Dec-88 and
# 49753998.00 as 49753998 in the combined file. It repeats the evidence so it stands alone, so
# it does hold dates; what it must never hold is a date or a decimal in a column that is read
# back. checks/check_adjudication_queue.py enforces that and is the only place the list lives.
# WHAT THE WORKBOOK CARRIES.
#
# Everything the pipeline knows lives in stage2_adjudication_queue.csv, all 48 columns of it.
# This is the shorter list: what a person actually reads to reach a judgement. A wide sheet is
# not a more informative one, it is a harder one to navigate, and the analyst was navigating 45
# columns to fill in five.
#
# Dropped here and still in the queue file: the meaning-word overlap, which is a diagnostic and
# never a score; the months_gap, which the two date columns already state; the dates and score of
# the removed candidate, where the reason it went is the part that matters; the co-trading
# months, the chain length, and the closest code the structural narrowing never considered.
DECISION_COLUMNS = [
    # Eighteen columns, because the sheet is for reaching a judgement and not for holding
    # everything known. It was 45, then 33, and the analyst reported that the width itself was
    # making adjudication harder. Every column dropped is still in
    # stage2_adjudication_queue.csv, which is the evidence file and is not meant to be filled in.
    "link_id", "row",
    # The answer at a glance, and one sentence of why when it is not CONFIRM.
    "verdict", "why",
    # What retired.
    "retiring_code", "retiring_description", "retiring_last_traded",
    # What is proposed and how close it reads.
    "proposed_successor", "proposed_successor_description", "proposed_successor_traded",
    "proposed_successor_wording_match",
    # The next thing worth looking at, laid out the same way so the two can be read line against
    # line. Filled only where the verdict is ANALYST. The queue file lists every alternative.
    "second_alternative", "second_alternative_description", "second_alternative_traded",
    "second_alternative_wording_match",
    # What kind of medicine each is, how confidently that is known, and which word it points to.
    "how_they_relate", "how_the_second_relates", "what_this_points_to",
    # Set only when something needs attention again, so an empty column means settled.
    "check_this_again",
    # The five the analyst fills in.
    "decision", "correct_successor_if_rejected", "reason", "decided_by", "decided_on",
]

# The four answers, and no others. Stage 2 rejects anything else rather than guessing.
#
# approve and reject are the words the 126 signed decisions already use, so the comparison
# against them is a direct match with no mapping to defend. none is the word the 19-row boundary
# workbook already uses, and it means the same thing here.
#
# unresolved exists because "examined, the proposal is wrong, and I cannot tell what is right"
# is a real outcome across 217 rows, and it must be distinguishable from a row nobody reached.
# Leaving it blank is what the released crosswalk did, and software read the blank as approval.
# Words a person may reasonably write meaning the same thing. Adapting the software is cheaper
# and safer than asking someone mid-way through 200 judgements to retype what they have already
# entered, and "accept" is the more natural English for what the column is asking. Normalised on
# read, never rewritten in the file, so what the analyst typed stays visible.
DECISION_SYNONYMS = {
    "second alternative": "second", "2nd": "second", "alternative": "second", "alt": "second",
    "accept": "approve", "accepted": "approve", "approved": "approve", "yes": "approve",
    "ok": "approve", "y": "approve",
    "rejected": "reject", "no": "reject", "n": "reject",
    "no successor": "none", "left chapter": "none",
}


def normalise_decision(written):
    """What a person wrote, mapped to the recorded vocabulary. Empty when nothing was written."""
    text = (written or "").strip().lower()
    if not text:
        return ""
    if text in DECISION_VALUES:
        return text
    return DECISION_SYNONYMS.get(text, "")


DECISION_VALUES = {
    "approve": "the proposed successor is correct. The workbook called this crosswalk",
    "second": ("the SECOND ALTERNATIVE is correct, not the proposal. Written when the software "
               "declined to recommend and the alternative beside it is the better answer"),
    "reject": "the proposed successor is wrong and another code is right. Name it",
    "none": "this code has no successor inside Chapter 30. The workbook uses the same word",
    "unresolved": "examined, the proposal is wrong, and the right answer cannot be determined",
}

# One string, used to render the outcome AND to recognise it further down. The first version
# tested `row["official_outcome"]`, which the queue row does not carry: it carries the rendered
# prose under `official_record`. The branch therefore never fired, and the five affected rows
# looked correct only because an unrelated chapter-exit heuristic had already suggested `none`.
# A silent no-op that produces the right answer by accident is worse than one that produces the
# wrong answer, because nothing shows it.
LEFT_CHAPTER_PROSE = "the WCO correlation sends this subheading OUT of Chapter 30"

OFFICIAL_PLAIN = {
    "decided": "named outright by Canada's ten-digit concordance",
    "constrained": "the record bounds the answer to a short list",
    "bounded_needs_ruling": "the record bounds it and this row needs a ruling",
    "narrowed": "the tariff schedule ruled some candidates out",
    "forced": "the tariff schedule left only one candidate",
    "silent_no_effect": "a tariff schedule was read and ruled nothing out",
    "silent_no_source": "no official source reaches this boundary",
    "all_candidates_absent": "the schedule holds none of the candidates",
    # Added 2026-08-14, when Layer 2 stopped being empty.
    "correlated_left_chapter": LEFT_CHAPTER_PROSE,
    "correlated_no_candidate": ("the WCO correlation names a subheading no candidate trades "
                                "under"),
}

# THE RECORD SAYS THESE GOODS LEFT CHAPTER 30, SO NOTHING INSIDE IT CAN BE THE SUCCESSOR.
#
# Kept as its own name because two places need it and because the first build after Layer 2 was
# wired showed why it matters: the three blood-grouping reagent rows came off their hold, the
# ranker did its ordinary job on candidates that are all still in Chapter 30, and the sheet
# offered "Other dental fillings, nes" at 0.4250 against a commodity the WCO had just said went
# to 3822.13. Ranking is not wrong there; it is answering a question the record has closed.
CORRELATION_LEFT_CHAPTER = "correlated_left_chapter"


def official_prose(layer, outcome):
    """What the record did, named by the layer that did it."""
    if layer == "wco_correlation":
        if outcome == "narrowed":
            return "the WCO correlation narrowed this to one subheading"
        if outcome == "forced":
            return "the WCO correlation left one candidate"
    return OFFICIAL_PLAIN.get(outcome, outcome)


_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import meaning_gates as _gates
# The SAME preparation Stage 1c fires the rule on. Naming the differing terms from raw text while
# the rule fired on expanded text made the two disagree on one row, which is the ordinary result
# of computing one thing in two places.
from _shorthand import expand_shorthand as _expand
import _xlsx
import families as _families


RESIDUAL_WORD = _re_score.compile(r"(?<![a-z0-9])(nes|other)(?![a-z0-9])")
# Wider than RESIDUAL_WORD, for asking whether a description is a catch-all of any kind rather
# than which leftover line belongs to a parent.
ANY_RESIDUAL = _re_score.compile(
    r"(?<![a-z0-9])(nes|n\.e\.s\.|not elsewhere specified|other|o/t|general)(?![a-z0-9])")


def prepared_for_score(text):
    """The same preparation Stage 1c uses, so a disclosed score is comparable to a ranked one."""
    return _re_score.sub(r"\s+", " ",
                         _re_score.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def wording_ratio(a, b):
    return round(difflib.SequenceMatcher(None, prepared_for_score(a),
                                         prepared_for_score(b)).ratio(), 4)


def substance_index(records):
    """Words distinctive enough to name a substance, and every code that uses each one.

    A description in this chapter is mostly boilerplate: "for human use", "in dosage", "o/t No
    30.02/05/06". What identifies the goods is the one or two words that are NOT boilerplate, and
    in a pharmaceutical chapter those words are usually the substance. A word appearing in fewer
    than five percent of descriptions is treated as distinctive; anything commoner is scaffolding.

    This exists because the crosswalk had no notion of what a medicine IS. Quinidine sulphate was
    offered Vincristine's successor and Polymyxins was offered Vancomycin: same subheading, same
    boilerplate, different drugs. Knowing whether the substance is ever named again is what tells
    a reader that no equivalent successor exists and any choice will be an aggregation.
    """
    total = len(records) or 1
    frequency = Counter()
    for record in records:
        frequency.update(set(prepared_for_score(record["description"]).split()))
    boilerplate = {word for word, n in frequency.items() if n >= total * 0.05}
    index = defaultdict(set)
    for record in records:
        for word in set(prepared_for_score(record["description"]).split()) - boilerplate:
            index[word].add((record["hs_code"], record["first_period"], record["last_period"]))
    return index, boilerplate


def build():
    rows = []
    family_table = _families.load_families()
    # One substance vocabulary per flow. Held here rather than inside the loop because the
    # post-pass below runs after both flows are read, and a closure over the loop variable would
    # test every import row against the export word list. It did, for one build: "coccidiostats"
    # is not in the export vocabulary, so the row it should have caught went quiet and a row it
    # should have left alone was flagged instead.
    vocabulary = {}
    # Kept per flow so the answer sheet, written after both flows are read, can look up the
    # trading span of whichever code it is about to print.
    spans_by_flow = {}
    lives_by_flow, ends_by_flow = {}, {}
    delivery_ends = {}
    settled_successions = {}
    descriptions_by_flow = {}
    for flow in ("imports", "exports"):
        review = load(WORK_DIR / ("stage1_review_%s.csv" % flow))
        worklist = {(r["retiring_code"], r["last_period"]): r
                    for r in load(WORK_DIR / ("stage1_candidates_%s.csv" % flow))}
        ranked = load(WORK_DIR / ("stage1_ranked_%s.csv" % flow))
        # EVERY LIFE OF A REUSED NUMBER, not only the earliest. A code that is reused carries a
        # different description in each life, and this kept the first one, so the wording shown
        # for a candidate was often from a life that ended before the retirement it was being
        # offered to. 3002.90.90 was shown as "Human blood; animal blood ... microbial prep" when
        # the life that receives Saxitoxin's trade reads "... toxins, micro-orga cul", which is
        # the word that settles the row.
        lives = {}
        # THE MONTH THE RECORD ENDS EACH CLASSIFICATION, beside the month its money stopped.
        # A candidate is described by the life in force when the classification ended, not when
        # the last shipment cleared; Stage 1c scores it that way and the sheet must show the
        # wording that score was computed on, or a reader compares one era against another.
        # Only notes Stage 0 says belong to THIS life are read. Findings 105 and 106.
        classification_end = {}
        for r in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
            code = r["hs_code"]
            lives.setdefault(code, []).append(
                (r["first_period"], r["last_period"], r["description"]))
            note = (r.get("stated_termination") or "").strip()
            if note and r.get("stated_termination_is_this_life") != "no" and note >= r["last_period"]:
                classification_end[(code, r["last_period"])] = note
            # No earliest-wording map is built any more. One survived every previous pass and
            # was still describing the second alternative, so the map itself is the hazard.
        spans = code_spans(flow)
        lives_by_flow[flow] = lives
        ends_by_flow[flow] = classification_end
        spans_by_flow[flow] = spans
        delivery_ends[flow] = max(p[1] for pairs in spans.values() for p in pairs)
        descriptions_by_flow[flow] = {c: v[-1][2] for c, v in lives.items()}
        inventory = load(WORK_DIR / ("commodity_inventory_%s.csv" % flow))
        # Codes grouped by the exact wording of their description, so a renumbering that kept the
        # words can be found anywhere in the chapter rather than only inside the narrowed tier.
        by_text = defaultdict(set)
        for record in inventory:
            by_text[prepared_for_score(record["description"])].add(
                (record["hs_code"], record["first_period"], record["last_period"]))
        terms_index, _boilerplate = substance_index(inventory)

        vocabulary[flow] = set(terms_index)
        off_by_key = {(r["retiring_code"], r["last_period"]): r
                      for r in load(WORK_DIR / ("stage1_official_%s.csv" % flow))}
        # Successions the official record settles outright. They never reach the queue, so
        # without them a chain cannot be followed past the first code the record decides.
        for r in off_by_key.values():
            named = [d for d in (r["official_destinations"] or "").split(";") if d]
            if r["outcome"] == "decided" and len(named) == 1:
                settled_successions[(flow, r["retiring_code"])] = named[0]
        by_retirement = {}
        for r in ranked:
            by_retirement.setdefault((r["retiring_code"], r["last_period"]), []).append(r)

        for entry in review:
            key = (entry["retiring_code"], entry["last_period"])
            candidates = sorted(by_retirement.get(key, []), key=lambda r: int(r["rank"]))
            survivors = [c for c in candidates if not c["vetoed_by"]]
            vetoed = [c for c in candidates if c["vetoed_by"]]
            # A DESTINATION THE RECORD NAMES THAT A GATE OBJECTED TO, AND WAS OVERRULED ON.
            # It is not in `vetoed`, because it was not removed: the record outranks the gate,
            # and Stage 1c now applies that to every gate rather than to the continuity veto
            # alone. Carried here because correcting that would otherwise show the analyst LESS.
            # Before the fix 3004.50.00.90 appeared under candidates_removed_on_meaning as
            # "removed on use"; after it the code became an ordinary runner-up and the objection
            # disappeared from the sheet. Fixing a layer order is no reason to hide a finding.
            overruled = [c for c in candidates if c.get("record_overruled_gate")]
            runner_up = survivors[1] if len(survivors) > 1 else None
            held = entry["held_for_official_evidence"] == "yes"
            tier = int(entry["risk_tier"])
            work = worklist[(entry["retiring_code"], entry["last_period"])]
            top_first = span_shown(spans, entry["top_candidate"], entry["last_period"])[0]
            gap = months_gap(entry["last_period"], top_first)
            official_named = entry["top_candidate"] in (
                {d for d in (off_by_key.get((entry["retiring_code"], entry["last_period"]),
                                            {}).get("official_destinations") or "").split(";") if d})
            # Does the proposal differ from the retiring code only by a swapped term? Flagged,
            # never removed: the shape fires on 5 of 125 known-correct successions.
            top_row = survivors[0] if survivors else None
            swaps = bool(top_row) and "swapped term" in (top_row["review_flag"] or "")
            swap_before = swap_after = ""
            if swaps:
                swap_before, swap_after = _gates.swapped_terms_named(
                    _expand(top_row["retiring_description"] or "").lower(),
                    _expand(top_row["candidate_description"] or "").lower())
            carved_term, carved_by = ("", "")
            # How long the proposal was already trading before this code stopped. Absorption into
            # a code that already existed is legitimate and common, so this is reported and not
            # judged: 51 of the 53 rows carrying it are not aggregations, which is why it is
            # worth a reader's eye.
            # The wording each candidate carried in the life that could receive THIS
            # retirement. Used everywhere a description is read, so a rule never fires on
            # words the sheet does not show.
            _ends_at = ends_by_flow[flow].get(
                (entry["retiring_code"], entry["last_period"]), entry["last_period"])

            def describe(code, _stopped=_ends_at, _lives=lives):
                return description_shown(_lives, code, _stopped)

            # Was the proposal's distinguishing term carved out of this residual line by a
            # sibling alive beside it? Flagged, never removed. Placed here because it reads
            # descriptions through describe(), so every word it fires on is a word the sheet
            # shows, which is the same discipline the swapped-term rule follows.
            if survivors:
                carved_term, carved_by = carved_out_of(
                    lives, vocabulary[flow], entry["retiring_code"], entry["last_period"],
                    describe, entry["top_candidate"])

            # Did a DIFFERENT surviving candidate's leftover line widen at this boundary? Read
            # from the wording each life carried rather than from the wording shown, because the
            # whole point is that the wording CHANGED and describe() returns only one side of it.
            widened_code, widened_terms, widened_rank = ("", "", "")
            if survivors:
                widened_code, widened_terms, widened_rank = widened_at_the_boundary(
                    lives, vocabulary[flow], entry["last_period"], survivors,
                    entry["top_candidate"])

            co_months = ""
            if survivors:
                first = span_shown(spans, entry["top_candidate"], entry["last_period"])[0]
                last = span_shown(spans, entry["top_candidate"], entry["last_period"])[1]
                if first and last and first < entry["last_period"] < last:
                    co_months = months_gap(first, entry["last_period"]) or ""
            suggestion, basis = suggest(work["subheading_survives"],
                                        float(entry["meaning_overlap"]), held,
                                        has_proposal=bool(survivors),
                                        wording=(float(entry["top_score"])
                                                 if survivors else None),
                                        swaps_a_term=swaps, swapped_from=swap_before,
                                        swapped_to=swap_after)
            # The codes the structural ladder never offered. Scored with the same measure the
            # ranking uses, so the reader can compare it directly against wording_match and see
            # whether anything outside the tier would have beaten what was proposed.
            # The same wording, somewhere else in the chapter, starting after this code stopped.
            # Reported and never acted on: 3002.90.10.10's wording returns twenty years later,
            # and something carried that trade in between, so identical text shows what the
            # goods are and not necessarily who received them next.
            # The retiring code's own wording at the month it stopped. Stage 1a already records
            # exactly that, and the fallback behind it used to reach the earliest-wording map,
            # which for a reused number is a different commodity's words.
            retiring_text = prepared_for_score(
                entry["description"] if "description" in entry
                else description_shown(lives, entry["retiring_code"], entry["last_period"]))
            twins = sorted((f, h, l) for h, f, l in by_text.get(retiring_text, set())
                           if h != entry["retiring_code"] and f > entry["last_period"])
            # Populated ONLY when the identical wording sits somewhere other than the code being
            # proposed. On 115 of 120 matches it IS the proposal, which wording_match already
            # says with a 1.0000, and a column repeating it would read as a discrepancy where
            # there is none. The five that disagree are the ones worth a reader's attention.
            twin_code = twin_from = twin_gap = ""
            if twins:
                candidate_from, candidate_code, _last = twins[0]
                if candidate_code != entry.get("top_candidate"):
                    twin_gap = months_gap(entry["last_period"], candidate_from) or "0"
                    twin_from = month(candidate_from)
                    twin_code = dotted(candidate_code)
            # Whether the substance is ever named again, anywhere, after this code stops.
            own_terms = set(retiring_text.split()) & set(terms_index)
            named_later = any(last > entry["last_period"] and code != entry["retiring_code"]
                              for word in own_terms
                              for code, _first, last in terms_index[word])
            # The leftover line of this code's own parent, if one survived the gates.
            #
            # Measured against Canada's concordance, a specific substance line goes to a residual
            # 62% of the time, and of the 38% going to a named substance 19 of 27 are the same
            # substance renamed. Only 8 of 71 succeed to a genuinely different named substance,
            # which is the case a character-similarity ranking proposes by default because every
            # sibling shares the class and the boilerplate.
            #
            # Kanamycins is the plain example. Its own class residual, "Aminoglycoside
            # antibiotics, nes", survived every gate and ranked seventeenth of twenty-four at
            # 0.6591 while Gentamycins ranked first at 0.9275. Both are aminoglycosides; only one
            # of them is where the trade goes.
            #
            # REPORTED, NEVER RANKED. The same-parent test is crude: for Quinidine sulphate it
            # picks "Codeine or its derivs nes", which is codeine's leftover line and not the
            # alkaloid one. A column a reader can reject costs nothing; a reranking on a detector
            # that mispicks would repeat a mistake this project has already made twice.
            parent = entry["retiring_code"][:8]
            residuals = [c for c in survivors
                         if c["candidate"][:8] == parent
                         and RESIDUAL_WORD.search(
                             (describe(c["candidate"]) or "").lower())]
            # THE FAMILY LEFTOVER LINE OUTRANKS THE BEST-SCORING ONE.
            #
            # Ordering residuals by wording put "Antibiotics, nes" (0.7945) ahead of
            # "Aminoglycoside antibiotics, nes" (0.6591) for Kanamycins, and a kanamycin is an
            # aminoglycoside. The broader line scores higher precisely because it says less.
            # Where the tariff's own block structure names the family, that is the target.
            own_family = _families.family_of(family_table, flow, entry["retiring_code"],
                                             entry["last_period"])
            # ALL of them, not the best-scoring one. A parent can carry residuals at more than
            # one level of specificity, and the broader one scores higher precisely because it
            # says less. Kanamycins is the case: "Antibiotics, nes" scores 0.7945 and
            # "Aminoglycoside antibiotics, nes" 0.6591, and the aminoglycoside line is the right
            # answer because that is what a kanamycin is. Choosing between them is chemistry, not
            # string comparison, so both are shown and neither is chosen.
            residuals.sort(key=lambda c: -float(c["similarity_score"]))
            # Applied AFTER the score sort, which would otherwise undo it. The family leftover
            # line leads even when a broader one scores higher, because the broader one scores
            # higher by saying less.
            if own_family:
                named = [c for c in residuals
                         if (describe(c["candidate"]) or "").strip()
                         == own_family.strip()]
                residuals = named + [c for c in residuals if c not in named]
            # Shown only where the proposal is actually in doubt. Offering a leftover line
            # beside a proposal whose wording matches exactly is clutter, and clutter in an
            # artefact meant for reading is a cost like any other.
            proposal_is_strong = (bool(survivors)
                                  and float(survivors[0]["similarity_score"]) >= STRONG_PROPOSAL)
            outranked = bool(residuals and survivors
                             and residuals[0]["candidate"] != survivors[0]["candidate"]
                             and not (proposal_is_strong and not swaps))
            # THE BEST CANDIDATE THAT PASSES EVERY RULE.
            #
            # Until now the rules could only veto the top pick. Nothing chose a replacement, so a
            # withheld row handed the reader a candidate the software had just rejected and left
            # it there. This walks the survivors in score order and returns the first one that
            # trips none of the rules the rest of this file applies: it must not swap the term
            # that carries the meaning, must share at least one distinctive word unless one side
            # is a catch-all, and must not itself stop trading within two years.
            #
            # Where a leftover line of the same parent qualifies it is preferred over a named
            # sibling, because measured against Canada's concordance a specific substance line
            # goes to a residual 62% of the time and to a genuinely different named substance in
            # only 8 of 71 cases.
            #
            # It is a recommendation and not an answer. It cannot know that a kanamycin is an
            # aminoglycoside, so where several leftover lines qualify it takes the closest on
            # wording and the row still lists them all.
            retiring_words = (entry["description"] if "description" in entry
                              else (candidates[0]["retiring_description"] if candidates else ""))

            def passes_every_rule(candidate):
                text = describe(candidate["candidate"])
                expanded_candidate = _expand(text or "").lower()
                expanded_retiring = _expand(retiring_words or "").lower()
                if _gates.swapped_term(expanded_retiring, expanded_candidate):
                    return False
                if not (ANY_RESIDUAL.search((retiring_words or "").lower())
                        or ANY_RESIDUAL.search((text or "").lower())):
                    mine = {w for w in set(prepared_for_score(retiring_words).split())
                            & set(terms_index) if not w.isdigit()}
                    theirs = {w for w in set(prepared_for_score(text).split())
                              & set(terms_index) if not w.isdigit()}
                    if mine and theirs and not (mine & theirs):
                        return False
                # span_shown, not spans.get: the latter returns every span this code ever had,
                # and indexing it would compare against whichever life came second.
                other = span_shown(spans, candidate["candidate"], entry["last_period"])
                if other and other[1] and not still_running(
                        other[1], delivery_ends.get(flow, "999912")):
                    outlives = months_between(month(entry["last_period"]), month(other[1]))
                    if outlives is not None and outlives <= CO_CASUALTY_MONTHS:
                        return False
                return True

            # OFFERED ONLY WHERE THE PROPOSAL ITSELF IS THE PROBLEM.
            #
            # A row can be withheld for two quite different reasons. The proposal may be
            # defective: it swaps the term that carries the meaning, it shares nothing with the
            # retiring description, or it dies in the same restructuring. Then a replacement is
            # worth having. Or the proposal may be sound and the ROW uncertain: an identical
            # wording sits on another code, or the wording is below the review threshold. Then
            # there is nothing to replace, and walking down the score list only produces
            # something worse.
            #
            # Ignoring that distinction offered 0.6372 in place of a 1.0000 exact match on one
            # row, and 0.2897 in place of 0.9718 on another. Both rejections were wording
            # conflicts, not faults in the proposal.
            proposal_is_the_problem = bool(survivors) and not passes_every_rule(survivors[0])
            clean = ([c for c in survivors[1:] if passes_every_rule(c)]
                     if proposal_is_the_problem else [])
            clean_residual = [c for c in clean if c["candidate"][:8] == entry["retiring_code"][:8]
                              and RESIDUAL_WORD.search(
                                  (describe(c["candidate"]) or "").lower())]
            # The family line leads here as well. Without this the replacement for Polymyxins was
            # "Antibiotics, nes" while its own family line, "Polypeptide antibiotics, nes", sat
            # second, and the replacement is what the second alternative takes first.
            if own_family and clean_residual:
                named = [c for c in clean_residual
                         if (describe(c["candidate"]) or "").strip()
                         == own_family.strip()]
                clean_residual = named + [c for c in clean_residual if c not in named]
            replacement = (clean_residual or clean or [None])[0]

            never = [c for c in (work.get("candidates_outside_narrowest") or "").split(";") if c]
            never_n = len(never)
            never_best, never_score = "", 0.0
            if never:
                retiring_text = describe(entry["retiring_code"])
                never_best, never_score = max(
                    ((c, wording_ratio(retiring_text, describe(c)))
                     for c in never), key=lambda pair: pair[1])
            # A span stopping within a year of the delivery's own last month is not a proven
            # retirement: at the data boundary, absence and quiet look identical. Held rather
            # than decided, and the next delivery settles it without anyone adjudicating.
            too_recent = work.get("too_recent_to_call") == "yes"
            # Stronger than either hold above, and it outranks them: those say the answer is not
            # available yet, this says there is no question. Stage 1a owns the rule.
            not_a_retirement = work.get("retirement_basis") == "trade_ceased_only"
            rows.append({
                "status": ("NOT A RETIREMENT, nothing to decide" if not_a_retirement
                           else "TOO RECENT, cannot be decided yet" if too_recent
                           else "HELD, do not decide yet" if held else "decide"),
                "priority": (100 if not_a_retirement else 98 if too_recent
                             else 99 if held else tier),
                "why_this_needs_you": (
                    "the delivery records no termination for this line and the number was never "
                    "handed to different goods, so trade stopped without the classification "
                    "ending. There is no transfer to trace and nothing here to answer."
                    if not_a_retirement
                    else "this code last traded %s month(s) before the delivery ends, so it cannot "
                    "yet be shown to have retired at all. A one-month silence occurs in every "
                    "live code's history, and a twelve-month one in about one in forty. Leave "
                    "it: the next delivery settles it without anyone deciding anything."
                    % work.get("months_before_delivery_end", "?") if too_recent
                    else "a correlation table could answer this and none has been extracted yet, "
                    "so deciding now risks being overruled by a document" if held
                    else PRIORITY_NAMES.get(tier, "")),
                "flow": flow,
                "retiring_code": dotted(entry["retiring_code"]),
                "retiring_description": entry["description"] if "description" in entry
                else (candidates[0]["retiring_description"] if candidates else ""),
                "last_traded": month(entry["last_period"]),
                "value_cad": "%.2f" % float(entry["total_value_cad"]),
                "proposed_successor": dotted(entry["top_candidate"]),
                "proposed_successor_description": describe(entry["top_candidate"]),
                "proposed_successor_first_traded": month(span_shown(spans, entry["top_candidate"], entry["last_period"])[0]),
                "proposed_successor_last_traded": month(span_shown(spans, entry["top_candidate"], entry["last_period"])[1]),
                "successor_began_at_the_boundary": (
                    "" if not survivors
                    else "yes" if span_shown(spans, entry["top_candidate"], entry["last_period"])[0]
                    == next_month(entry["last_period"]) else "no"),
                # Blank, not zero. With no surviving candidate there is nothing to score, and a
                # printed 0.0000 reads as "the wording does not match" rather than "there is
                # nothing to match against".
                "wording_match": entry["top_score"] if survivors else "",
                "shared_meaning_words": entry["meaning_overlap"] if survivors else "",
                "runner_up": dotted(runner_up["candidate"]) if runner_up else "",
                "runner_up_description": (describe(runner_up["candidate"])
                                          if runner_up else ""),
                "runner_up_first_traded": (month(span_shown(spans, runner_up["candidate"], entry["last_period"])[0])
                                           if runner_up else ""),
                "runner_up_last_traded": (month(span_shown(spans, runner_up["candidate"], entry["last_period"])[1])
                                          if runner_up else ""),
                "runner_up_wording_match": runner_up["similarity_score"] if runner_up else "",
                "other_candidates_considered": max(len(survivors) - 2, 0),
                "months_gap": gap,
                "gap_named_by_the_record": ("" if not survivors
                                            else "yes" if (gap and official_named) else "no"),
                "suggested_decision": suggestion, "why_not_recommended": basis,
                "successor_is_more_aggregate": "" if not survivors else aggregation_note(
                    entry["retiring_code"], entry["top_candidate"],
                    candidates[0]["retiring_description"] if candidates else "",
                    describe(entry["top_candidate"])),
                # RENDERED FROM THE LAYER AND THE OUTCOME, NOT THE OUTCOME ALONE.
                # OFFICIAL_PLAIN is keyed on outcome, and `narrowed` and `forced` are
                # phrased as the tariff schedule because until 2026-08-14 only the
                # schedule produced them. The WCO correlation now produces both, and the
                # sheet was telling the analyst "the tariff schedule ruled some candidates
                # out" on ten rows the correlation had narrowed. Crediting the wrong
                # source is not a wording slip on a document headed for review.
                "official_record": official_prose(entry["official_layer"],
                                                  entry["official_outcome"]),
                # The record's own sentence, carried rather than paraphrased, so the
                # sheet and the work file cannot drift apart.
                "record_narrowed_note": "",
                "official_record_note": (off_by_key.get(
                    (entry["retiring_code"], entry["last_period"]), {}).get("note", "")),
                # The best of what was removed, shown in full rather than as a bare code. A row
                # whose candidates were all vetoed would otherwise arrive blank, and a reviewer
                # cannot disagree with a rejection they cannot see. It is listed as removed, not
                # proposed, so nothing here reads as a recommendation.
                "closest_removed_candidate": dotted(vetoed[0]["candidate"]) if vetoed else "",
                "closest_removed_description": (describe(vetoed[0]["candidate"])
                                                if vetoed else ""),
                "closest_removed_first_traded": (month(span_shown(spans, vetoed[0]["candidate"], entry["last_period"])[0])
                                                 if vetoed else ""),
                "closest_removed_last_traded": (month(span_shown(spans, vetoed[0]["candidate"], entry["last_period"])[1])
                                                if vetoed else ""),
                "closest_removed_wording_match": vetoed[0]["similarity_score"] if vetoed else "",
                "closest_removed_why": vetoed[0]["vetoed_by"] if vetoed else "",
                "best_candidate_passing_every_rule": (dotted(replacement["candidate"])
                                                      if replacement else ""),
                "best_candidate_description": (
                    describe(replacement["candidate"])
                    if replacement else ""),
                "best_candidate_wording_match": (replacement["similarity_score"]
                                                 if replacement else ""),
                "best_candidate_is_the_leftover_line": (
                    "yes" if replacement and replacement in clean_residual else
                    ("no" if replacement else "")),
                "class_residual_available": ("; ".join(dotted(c["candidate"])
                                                       for c in residuals)
                                             if outranked else ""),
                "class_residual_description": ("; ".join(
                    "%s (%s)" % (describe(c["candidate"]),
                                 c["similarity_score"]) for c in residuals)
                                               if outranked else ""),
                "class_residual_wording_match": (residuals[0]["similarity_score"]
                                                 if outranked else ""),
                "how_they_relate": _families.relationship(
                    family_table, flow, entry["retiring_code"],
                    entry["top_candidate"],
                    describe(entry["top_candidate"]),
                    retiring_words,
                    entry["last_period"]) if survivors else "",
                "family_of_the_retiring_code": own_family,
                # The provenance of the fact that was USED, not of the entry as a whole. A
                # therapeutic class is always asserted; a family may be either.
                "family_evidence": (
                    "asserted, unsourced"
                    if _families.basis_of(family_table, flow, entry["retiring_code"],
                                          entry["top_candidate"], "",
                                          entry["last_period"]) == "class"
                    else _families.source_of(family_table, flow, entry["retiring_code"],
                                             entry["last_period"])),
                "same_wording_reappears_at": twin_code,
                "same_wording_reappears_from": twin_from,
                "same_wording_gap_months": twin_gap,
                "substance_named_again_later": ("" if not own_terms
                                                else "yes" if named_later else "NO"),
                "successor_swaps_a_term": "yes" if swaps else ("" if not survivors else "no"),
                "term_in_the_retiring_code": swap_before,
                "term_in_the_successor": swap_after,
                "successor_was_carved_out_of_it": ("yes" if carved_term
                                                   else ("" if not survivors else "no")),
                "carved_out_term": carved_term,
                "carved_out_by": dotted(carved_by) if carved_by else "",
                "a_leftover_line_widened_here": ("yes" if widened_code
                                                 else ("" if not survivors else "no")),
                "widened_line": dotted(widened_code) if widened_code else "",
                "widened_line_added_terms": widened_terms,
                "widened_line_rank": widened_rank,
                "successor_co_traded_months": co_months,
                "codes_never_considered": never_n,
                "closest_never_considered": dotted(never_best) if never_best else "",
                "closest_never_considered_description":
                    describe(never_best) if never_best else "",
                "closest_never_considered_wording_match":
                    "%.4f" % never_score if never_best else "",
                "candidates_removed_on_meaning": "; ".join(
                    "%s (%s)" % (dotted(c["candidate"]), c["vetoed_by"]) for c in vetoed) or "none",
                "record_overruled_gate": "; ".join(
                    "%s (the %s rule objects; the official record names it, so it stands)"
                    % (dotted(c["candidate"]), c["record_overruled_gate"])
                    for c in overruled) or "none",
            })
    # WHERE THE TRADE ACTUALLY ENDED UP, when the proposal is itself on its way out.
    #
    # 61 of the proposals are themselves retirements in this queue. Some are real chains: the
    # trade passed through one code before moving on, and the crosswalk should record both hops.
    # Others are co-casualties, where two codes ended in the same restructure and neither ever
    # received the other's trade. Time separates them. A proposal outliving its predecessor by
    # years carried the trade; one dying within months went with it.
    #
    # The waste pharmaceuticals block is the clear case. 3006.80.90.30 proposes .10, which
    # proposes .20, which proposes .50, each dying within months of the last, and the whole block
    # ends at 3006.92.00.00 "Waste pharmaceuticals, nes". Following the chain to that terminus is
    # what a reader needs; being handed the next domino is not.
    proposal_of = {(r["flow"], r["retiring_code"]): r["proposed_successor"] for r in rows}
    ends_at = {(r["flow"], r["retiring_code"]): r["last_traded"] for r in rows}
    for row in rows:
        successor = row["proposed_successor"]
        key = (row["flow"], successor)
        row["successor_also_retires"] = "yes" if key in proposal_of else ""
        row["chain_ends_at"] = ""
        # NOTHING IN COMMON, AND NEITHER SIDE IS A CATCH-ALL.
        #
        # swapped_term needs three shared content words before it can speak, so it goes quiet
        # exactly where two descriptions are most different. "Coccidiostats, in dosage" against
        # "Antacids, for human use, in dosage" shares one, and was recommended.
        #
        # Sharing no distinctive word cannot on its own mean anything: tested against the 125
        # successions the concordance states outright it flags 56 of them, because revisions
        # reword freely, and "Hormones, nes, not containing antibiotics, in bulk" really does
        # become "Medi,cont horm/prostaglandins/thromboxanes". Requiring that neither side be a
        # catch-all brings that to 6 of 125, the same 4.8% that decided swapped_term should flag
        # rather than remove. The six are specific lines absorbed into a broader named parent,
        # such as Penicillin G sodium into Medicaments containing penicillins.
        if (row["suggested_decision"] == "approve" and row["proposed_successor_description"]
                and not ANY_RESIDUAL.search(row["retiring_description"].lower())
                and not ANY_RESIDUAL.search(row["proposed_successor_description"].lower())):
            words = vocabulary.get(row["flow"], set())
            mine = {w for w in set(prepared_for_score(row["retiring_description"]).split())
                    & words if not w.isdigit()}
            theirs = {w for w in
                      set(prepared_for_score(row["proposed_successor_description"]).split())
                      & words if not w.isdigit()}
            if mine and theirs and not (mine & theirs):
                row["suggested_decision"] = "none"
                row["why_not_recommended"] = (
                    "NOTHING IN COMMON: this names %s and the proposal names %s, and neither is "
                    "a catch-all that could absorb the other. The score comes from shared "
                    "phrasing." % (", ".join(sorted(mine))[:60], ", ".join(sorted(theirs))[:60]))

        # An identical description sitting on a code that is NOT the proposal is a choice the
        # reader has to make, so no recommendation is offered on it. 3004.50.99.22 was
        # recommended at 0.6923 while a code carrying its exact wording began the month after it
        # stopped. This does not decide anything: the twin can be twenty years later and
        # irrelevant, as it is for 3002.90.10.10, and only a person can tell which.
        # UNLESS THE TWIN IS DOWNSTREAM OF THE PROPOSAL.
        #
        # The suppression assumes the twin and the proposal compete for the same link. They can
        # instead be two links in one chain: 3002.90.10.10 goes to 3002.90.00.19, which the
        # record then sends to 3002.90.00.10, and that last code is the twin. Nothing is
        # ambiguous, so asking a person to resolve it wastes the one resource this file spends.
        #
        # Measured over the five rows the suppression fires on, exactly one is downstream. The
        # other four are genuine forks, two of them with a twin beginning the same month as the
        # proposal.
        twin_is_downstream = False
        if row["same_wording_reappears_at"]:
            here = row["proposed_successor"].replace(".", "")
            target = row["same_wording_reappears_at"].replace(".", "")
            visited = set()
            for _hop in range(8):
                if here == target:
                    twin_is_downstream = True
                    break
                if here in visited:
                    break
                visited.add(here)
                nxt = (settled_successions.get((row["flow"], here))
                       or proposal_of.get((row["flow"], dotted(here)), "").replace(".", ""))
                if not nxt:
                    break
                here = nxt
        if (row["same_wording_reappears_at"] and row["suggested_decision"] == "approve"
                and not twin_is_downstream):
            row["suggested_decision"] = "none"
            row["why_not_recommended"] = (
                "a different code, %s, carries this description word for word from %s, %s "
                "month(s) after this one stopped. Either that is the renumbering or the proposal "
                "is, and the wording cannot separate them."
                % (row["same_wording_reappears_at"], row["same_wording_reappears_from"],
                   row["same_wording_gap_months"]))

        row["chain_hops"] = ""
        if key not in proposal_of:
            continue
        # Walk it, refusing to loop. A cycle means the block collapsed into itself and no
        # terminus exists inside the queue, which is itself worth saying.
        seen, here, hops = {(row["flow"], row["retiring_code"])}, key, 1
        while here in proposal_of and here not in seen:
            seen.add(here)
            nxt = proposal_of[here]
            if not nxt:
                break
            here, hops = (row["flow"], nxt), hops + 1
        row["chain_hops"] = hops
        row["chain_ends_at"] = ("they point at each other, no terminus"
                                if here in seen else here[1])
        # A proposal that dies in the same restructuring wave never received the trade.
        #
        # Measured on this queue: of the 61 proposals that are themselves retiring, 13 outlive
        # their predecessor by two years or less and the other 48 by anything from twenty-five
        # months to fifteen years. The long-lived ones are ordinary chains, where the trade did
        # pass through one code before moving on, and those links stand. The short-lived ones
        # went together, and handing a reader the next domino is not an answer.
        outlived = months_between(row["last_traded"], row["proposed_successor_last_traded"])
        if (outlived is not None and outlived <= CO_CASUALTY_MONTHS
                and not still_running(row["proposed_successor_last_traded"].replace("-", ""),
                                      delivery_ends.get(row["flow"], "999912"))):
            row["successor_also_retires"] = "yes, within %s months" % outlived
            if row["suggested_decision"] == "approve":
                row["suggested_decision"] = "none"
                row["why_not_recommended"] = (
                    "the code proposed here stops trading %s months after the one it would "
                    "replace, so the two ended in the same restructuring and neither received "
                    "the other's trade. Following the chain, the trade appears to end at %s."
                    % (outlived, row["chain_ends_at"]))

    # THE RECORD CLOSES THE QUESTION WHERE IT SENDS THE GOODS OUT OF THE CHAPTER.
    #
    # Applied last so it overrides every suggestion made above it, which is the layer order: the
    # official record outranks meaning, text, and every rule built on them. The candidates stay
    # visible, because the analyst still has to write `none` and is entitled to see what was on
    # offer when they do, but nothing inside Chapter 30 is recommended and the reason names the
    # destination and the document.
    # EVERY ROW THE CORRELATION TOUCHED SAYS SO, IN THE COLUMN THE ANALYST READS.
    #
    # The `why` column on the answer sheet is fed from why_not_recommended. Until this was added
    # it was blank on the narrowed and forced correlation rows, so the sheet showed a proposal
    # that the WCO had chosen and gave no hint that the WCO had chosen it. The analyst's words:
    # "how can I judge it if I don't know what and where these rows are". They could not, and the
    # strongest evidence on the row was the part not shown.
    #
    # The note is the record's own sentence, carried through from Stage 1b rather than rewritten
    # here, so the sheet and the work file cannot drift.
    left_chapter_rows = correlated_rows = withdrawn_rows = 0
    for row in rows:
        official = row.get("official_record") or ""
        if "WCO correlation" not in official:
            continue
        correlated_rows += 1
        if LEFT_CHAPTER_PROSE not in official:
            # `points_to`, NOT `why_not_recommended`. The second means "why the software declines
            # to recommend", and a control asserts that no row recommends and declines at once.
            # Writing the narrowing there put the note on CONFIRM rows and broke that invariant
            # on six of them within one build. The correlation narrowing STRENGTHENS a proposal;
            # it is what the row points to, not a reason to doubt it.
            note = (row.get("official_record_note") or "").strip()
            row["record_narrowed_note"] = (
                "THE OFFICIAL RECORD NARROWED THIS ROW: %s. The proposal rests on the "
                "correlation table and not on wording alone. The tables map six digits to six "
                "digits, so the record chose the SUBHEADING; the statistical line beneath it is "
                "still the analyst's." % (note or official))
            # AND THE RECORD WITHDRAWS THE CHAPTER-EXIT HYPOTHESIS IT HAS JUST REFUTED.
            #
            # The record has named a destination INSIDE Chapter 30. The wording heuristic had
            # already guessed the opposite on seven of these rows and left the guess in the `why`
            # column, so the sheet asserted both at once: "the WCO correlation left one candidate"
            # beside "the goods may have left Chapter 30 entirely", with 3006.92.00.00 sitting on
            # the row as the proposal. Both cannot be true, and the record is the stronger of the
            # two by the same reasoning as findings 88 and 89.
            #
            # Only the inference is withdrawn. The observation that produced it, that the
            # subheading is gone and the wording is weak, is true and is kept, so the row is
            # still not recommended and is still the analyst's to decide. Nothing is promoted
            # here and no verdict moves.
            reason = row.get("why_not_recommended") or ""
            if CHAPTER_EXIT_SUFFIX in reason:
                withdrawn_rows += 1
                row["why_not_recommended"] = (
                    "%s. THE RECORD PLACES THIS INSIDE CHAPTER 30 and the departure hypothesis "
                    "is withdrawn: %s. The proposal is still not recommended, because the "
                    "wording is weak, and that is now the only reason."
                    % (reason.split(CHAPTER_EXIT_SUFFIX)[0], note or official))
            continue
        left_chapter_rows += 1
        row["suggested_decision"] = "none"
        row["why_not_recommended"] = (
            "the WCO correlation table for this revision sends the whole subheading OUT of "
            "Chapter 30, so no code in this chapter is its successor. The candidates below are "
            "shown because the answer still has to be recorded, not because any of them "
            "qualifies. Expected answer: reject, with the successor written `none`.")
    if left_chapter_rows:
        print("  the record sends %d row(s) out of Chapter 30; none of them is recommended a "
              "successor" % left_chapter_rows)
    if withdrawn_rows:
        print("  the record places %d row(s) inside Chapter 30, withdrawing the chapter-exit "
              "hypothesis the wording had raised on them" % withdrawn_rows)

    # Held last, then by priority, then by value. The same order the review queue uses.
    rows.sort(key=lambda r: (r["priority"], -float(r["value_cad"])))
    for row in rows:
        row["link_id"] = "%s:%s:%s" % (row["flow"], row["retiring_code"], row["last_traded"])

    # THE ROW NUMBER IS A LABEL, NOT A POSITION. It was the index in the sorted order, so
    # anything that changed a score changed the order and renumbered the sheet: correcting the
    # ranker moved 173 of the 230. Everything outside this file refers to rows by that number,
    # including 63 entries in the findings register and every question the analyst has asked, so
    # a number that moves silently invalidates the whole record of the work. Once assigned it is
    # kept, and a retirement appearing for the first time takes the next free number. The sheet
    # still SORTS by priority and value; only the label is fixed.
    assigned = {}
    ledger = WORK_DIR / "_row_numbers.json"
    if ledger.exists():
        try:
            assigned = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            assigned = {}
    next_free = max(assigned.values(), default=0) + 1
    for row in rows:
        if row["link_id"] not in assigned:
            assigned[row["link_id"]] = next_free
            next_free += 1
        row["row"] = assigned[row["link_id"]]
        if row["priority"] == 100:
            row["priority"] = "not a retirement"
        elif row["priority"] == 99:
            row["priority"] = "held"
        elif row["priority"] == 98:
            row["priority"] = "too recent"
    ledger.write_text(json.dumps(assigned, indent=0, sort_keys=True), encoding="utf-8")

    # AND THE FILE READS IN THAT ORDER. Sorting by priority while the label stayed fixed put row
    # 66 at the top of the sheet above row 1, which is worse than either arrangement on its own.
    # The numbers were themselves assigned by priority, so ordering by number preserves it and
    # never moves again. The priority column is still there to re-sort by.
    rows.sort(key=lambda r: r["row"])
    # A verdict a person can scan a column of, rather than read. Written last so it reflects
    # every downgrade applied above, and placed near the front of both files because the analyst
    # was reading the proposal first and concluding nothing had changed when the recommendation
    # had been withdrawn underneath it.
    for row in rows:
        row["_spans"] = spans_by_flow
        row["_descriptions"] = descriptions_by_flow
        row["_classification_ends"] = {(f, c, l): e for f, m in ends_by_flow.items()
                                        for (c, l), e in m.items()}
        row["_lives"] = lives_by_flow
        row["_vocabulary"] = vocabulary
        row["_delivery_ends"] = delivery_ends
        if row["priority"] == "not a retirement":
            row["verdict"] = "DO NOT DECIDE - the record does not call this a retirement"
        elif row["priority"] == "held":
            row["verdict"] = "DO NOT DECIDE - waiting on a document"
        elif row["priority"] == "too recent":
            row["verdict"] = "DO NOT DECIDE - too close to the end of the data"
        elif row["suggested_decision"] == "approve":
            row["verdict"] = "CONFIRM - the evidence supports this link"
        elif row["suggested_decision"] == "unresolved":
            row["verdict"] = "ANALYST - nothing survived to propose"
        else:
            row["verdict"] = "ANALYST - a candidate is shown but NOT recommended"

    seen = {}
    for row in rows:
        if row["link_id"] in seen:
            raise ValueError("Two rows claim the same link_id %s. It is the join key for every "
                             "decision, so a collision cannot be written." % row["link_id"])
        seen[row["link_id"]] = True
    return rows


README = """# The adjudication queue, and how to fill it in

`stage2_adjudication_queue.csv` holds every retired commodity code whose successor the official
record could not settle. One row is one decision.

Everything needed to decide a row is in the row itself. The code, the tariff schedules
and every other file are unnecessary.

## Fill in these five columns

| Column | What to put |
|---|---|
| `decision` | `approve` if the proposed successor is right, `reject` if it is not, `none` if the goods left Chapter 30 entirely |
| `correct_successor_if_rejected` | the code held to be right, where one is known; left blank otherwise |
| `reason` | why. Required on every reject; welcome on any row |
| `decided_by` | the name of whoever ruled |
| `decided_on` | the date |

**A blank decision means undecided, and the next stage refuses to build until none are left.**
That is deliberate. In the released crosswalk an unmarked row was read as an approval, and links
entered the data that nobody had decided.

## The dates, and why they often decide a row on their own

`proposed_successor_first_traded` and `..._last_traded` say when the proposed successor actually
traded, and the runner-up carries the same two columns.

`successor_began_at_the_boundary` is `yes` when the successor first appears the month after the
retirement. That is the strongest structural evidence available and it holds for {boundary_yes} of the {queue_rows}
rows. Where it is `no`, the successor already existed and absorbed the trade, which is a real
outcome but deserves more scrutiny.

The dates frequently settle a row by themselves. In row 1 the runner-up did not begin trading
until 2018-01, thirty years after the code retired, so it was never a possible successor.

## When the successor is a broader bucket, not an equivalent

`successor_is_more_aggregate` is `yes` when the proposed successor covers more than the retired
code did, and the two descriptions in the row show what changed.

Two signals set it. The structural one: the last two digits are the statistical breakout and `00` is the parent, so
a code ending `10` succeeded by one ending `00` has been folded into the bucket above it.

The wording one: the successor states strictly fewer things. `Medicaments nes, in dosage, for
human use` succeeded by `Medicaments nes, in dosage` drops the human qualifier, so the successor
also carries veterinary trade the predecessor never did.

**This is far more common on exports, and the reason is structural.** Domestic exports are
recorded at eight digits and imports at ten, so exports have much less room for statistical
breakouts. When an export breakout retires, its trade usually collapses into the parent. On this
delivery the flag fires on {aggregate_exports} export rows and {aggregate_imports} import rows, and the export cases cluster at
December 1988, which was an aggregation of the export nomenclature rather than a renumbering.

**A flagged link is not wrong.** The trade really did move there. What is lost is resolution: a
series traced across such a boundary stops distinguishing what the predecessor distinguished.
Approving one of these is approving a real succession with a real loss of detail, and it is
worth noting in the reason so the limitation is recorded rather than inferred later.

## Reading the evidence columns

`wording_match` is how similar the two descriptions are as text, from 0 to 1. It is the published
similarity score. It counts shared letters and cannot read meaning, so a high number is not proof.

`shared_meaning_words` is how much of their meaning the two descriptions share, after shorthand
is expanded and filler words are dropped. **It is not a score and no threshold uses it.** It is
there because wording and meaning can disagree: two descriptions can share nine tenths of their
characters while the part that decides the code is a heading reference occupying a fraction of
the string.

`official_record` says what the documents settled before anyone was asked. Where it says no
official source reaches the boundary, the analyst's judgement is the only thing available.

`candidates_removed_on_meaning` lists codes already ruled out, with the reason. They are shown
so the ranking can be disagreed with.

**The removals are proposals too, and they can be overturned.** Where a code was removed
wrongly, the row is marked `reject`, that code is named in `correct_successor_if_rejected`, and
a reason is given. The software removed it; the ruling belongs to the analyst.

`closest_removed_candidate` gives the best of those in full, with its description, the months it
traded, its wording match and why it went. It carries the same evidence as the proposal so the
two can be weighed against each other. A row where everything was ruled out would otherwise arrive with an
empty proposal and no way to see what was rejected, and a rejection that cannot be read cannot
be disagreed with. It is labelled removed, never proposed, so nothing about it reads as a
recommendation.

Two reasons appear there that are not about meaning. `continuity` means the code had not begun
trading when the retirement happened, allowing a year of grace for the lag between a code
coming into force and its first shipment. `use`, `mixing`, `origin` and the rest are the
tariff distinctions.

## How the two numbers are computed

Stated so the figures can be reproduced or challenged without reading the code.

**`wording_match`** is `difflib.SequenceMatcher(None, a, b).ratio()` from the Python standard
library. It reports twice the number of matching characters divided by the total length of both
strings, so 1.0 means the two strings are identical. The comparison is a gestalt pattern match
of the Ratcliff and Obershelp kind: it finds the longest matching run, then recurses either side
of it.

Both descriptions are prepared the same way before the comparison, and only this way: lowercase,
then every character other than a letter, a digit or a space becomes a space, then repeated
spaces are collapsed. **Shorthand is not expanded.** "vet" is compared as the three letters
"vet", not as "veterinary". That is deliberate. It is the preparation every published figure in
this project already rests on, and changing it would make the new numbers incomparable with the
old ones.

**`shared_meaning_words`** is the Jaccard similarity coefficient, the size of the intersection
divided by the size of the union, computed over the two sets of meaning words. A word set is
built by expanding shorthand through this project's own lookup table, applying the same
preparation as above, then dropping twenty filler words: not, elsewhere, specified, nes, other,
than, whether, or, for, of, the, and, in, to, a, an, with, on, o, t.

A set comparison, and not a second run of the sequence matcher. Running the matcher over
expanded text was tried and rejected: expanding "nes" to "not elsewhere specified" injects a
long shared phrase, which the matcher rewards when both descriptions carry it and penalises when
only one does. That moved 843 of 3,699 candidate pairs by more than 0.10 in a direction which
tracked boilerplate rather than meaning. A set has no order and no length, so it is immune to
both effects.

**Tools.** Python 3, standard library only. `difflib` for the wording comparison, `re` for text
preparation, `csv` for every file, `sqlite3` to read the trade databases, `hashlib` for the
reproducibility hashes. There are no third-party packages anywhere in the pipeline or its
checks, verified by parsing every source file rather than by searching the text. Nothing needs
installing beyond Python itself.

## The order

Rows are ordered by how likely they are to be wrong, not by how close the wording is. The first
rows are the ones where the evidence conflicts. The long tail marked *please spot check* is
where wording and meaning both agree, and those need confirming rather than deciding.

## The rows marked HELD

Twenty-one rows say `HELD, do not decide yet`. An international correlation table could answer
them and it has not been extracted yet. Deciding them now risks a document overruling the ruling
later, which would reopen a decision already signed. They are shown rather than hidden so that nothing
is missing from the count.
"""


# Any of these being filled means a person has worked on the row. A decision is the obvious
# one, but a half-written reason or a proposed correction is work too, and a queue is filled in
# over days rather than in atomic rows.
#
# FOUR HERE, FIVE IN THE RUNNER'S ANALYST_COLUMNS, AND THE ODD ONE OUT IS decided_on. That is not
# an oversight. The two lists answer different questions. ANALYST_COLUMNS asks "which columns
# cannot be reproduced by a rebuild", and a date the analyst typed cannot be. This list asks
# "which columns prove a person worked on this row", and since 2026-08-14 a date no longer does,
# because load_decision_dates() fills it from evidence. Treating a machine-written date as
# human work would make this guard refuse to overwrite files nobody had touched.
WORK_COLUMNS = ("decision", "correct_successor_if_rejected", "reason", "decided_by")


def load_decision_dates():
    """link_id -> the date the decision entered the record, from evidence.

    Produced by evidence/provenance/derive_decision_dates.py, which reads the repository's own
    history and is run by hand. THIS MODULE MUST NOT READ THE CLOCK, and neither must anything
    else under pipeline/ or checks/. Nothing in either does, which is the only reason the
    end-to-end runner can delete thirteen artefacts, rebuild them twice and compare them byte
    for byte. A date fetched at build time would make every artefact a function of the day it
    was built and the comparison would prove nothing.

    Missing is not fatal. The build produced a crosswalk without these dates for weeks and can
    still do so. The loud failure belongs in checks/, where a control asserts that every decided
    row carries a date, so a forgotten run fails where failures are read rather than stopping a
    rebuild that is otherwise sound.
    """
    path = PROJECT_ROOT / "evidence" / "provenance" / "decision_dates.csv"
    if not path.exists():
        return {}
    dates = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = (row.get("decided_on") or "").strip()
            if value:
                dates[row["link_id"]] = value
    return dates


def rows_with_work(path):
    """How many rows already carry human work. Raises rather than guessing.

    This FAILS SAFE. An earlier version returned zero when the file could not be read, which
    means "no work, safe to overwrite" and is the worst possible answer to "I cannot tell".
    A file that exists and cannot be parsed is treated as full of work, not empty of it.
    """
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return sum(1 for row in csv.DictReader(handle)
                       if any((row.get(column) or "").strip() for column in WORK_COLUMNS))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise SystemExit(
            "Adjudication queue not written. %s exists but could not be read (%s: %s).\n"
            "It is treated as holding work, because a file that cannot be read cannot be "
            "shown to be empty.\n"
            "Move it aside if it is genuinely disposable."
            % (path.name, type(error).__name__, error))


WORKBOOK = "stage2_decisions.xlsx"


def read_existing_answers(path):
    """Every answer already on file, keyed on link_id. Unreadable means stop, never means empty.

    A file that cannot be parsed is not an empty file. Returning {} on a parse error would let a
    rebuild silently replace a sheet full of judgement with a blank one, which is the same class
    of failure as deleting it.

    A sheet written before link_id existed is also a stop. Its rows are keyed on a row number
    that has since moved, so there is no sound way to attach those answers to a retirement, and
    guessing would put decisions on the wrong codes.
    """
    # THE WORKBOOK IS THE FILE BEING FILLED IN. The CSV beside it is a copy, kept because every
    # other stage reads CSV and because a plain-text mirror is what a reviewer can diff. When both
    # exist the workbook wins, or a decision typed into it would be silently outranked by an older
    # copy of itself.
    book = path.parent / WORKBOOK
    if book.exists():
        try:
            columns, raw = _xlsx.read(book)
            rows = [{name: value for name, (value, _style) in row.items()} for row in raw]
        except Exception as error:                      # noqa: BLE001 - any failure means stop
            raise SystemExit(
                "Adjudication answers not read. %s exists but could not be opened (%s: %s).\n"
                "Nothing was written. A workbook that cannot be read cannot be shown to be empty."
                % (book.name, type(error).__name__, error))
        work = [r for r in rows if any((r.get(c) or "").strip() for c in WORK_COLUMNS)]
        if "link_id" not in columns:
            raise SystemExit(
                "Adjudication answers not written. %s predates the link_id column, so it is keyed "
                "on a row number that has since moved. Move it aside and rebuild." % book.name)
        return {r["link_id"]: r for r in work if (r.get("link_id") or "").strip()}
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise SystemExit(
            "Adjudication answers not read. %s exists but could not be parsed (%s: %s).\n"
            "Nothing was written. A file that cannot be read cannot be shown to be empty."
            % (path.name, type(error).__name__, error))
    work = [r for r in rows if any((r.get(c) or "").strip() for c in WORK_COLUMNS)]
    if "link_id" not in columns:
        if work:
            raise SystemExit(
                "Adjudication answers not written. %s holds work on %d row(s) but predates the "
                "link_id column, so it is keyed on a row number that has since moved.\n"
                "Measured on 2026-08-11, 214 of 238 row numbers changed which retirement they "
                "pointed at. Re-attaching those answers automatically would put decisions on the "
                "wrong codes.\n"
                "Move the file aside and re-enter the %d decision(s) against the rebuilt sheet."
                % (path.name, len(work), len(work)))
        return {}
    return {r["link_id"]: r for r in work if (r.get("link_id") or "").strip()}


def existing_decisions(path):
    """Kept as the older name. Both count any human work, not decisions alone."""
    return rows_with_work(path)


# The columns a reader ACTS on, named as the sheet names them. This list watched
# suggested_decision and why_not_recommended, both of which the sheet stopped carrying when it
# was narrowed, and watched none of the columns that hold the advice. It was also fed the queue
# rows, and what_this_points_to, second_alternative and how_the_second_relates are assembled in
# the sheet and absent from the queue, so the report could not see the three columns most likely
# to change a decision even in principle.
#
# The two scores joined on 2026-08-13. A number moving beside an unchanged code is advice
# changing: rows 40, 41 and 50 were decided accept while the alternative's score was blank, and
# it turned out to equal or beat the proposal's. Had the score been watched, filling it would
# have raised the row rather than passing unremarked.
WATCHED = ("verdict", "proposed_successor", "proposed_successor_description",
           "proposed_successor_wording_match",
           "how_they_relate", "what_this_points_to",
           "second_alternative", "second_alternative_description",
           "second_alternative_wording_match", "how_the_second_relates",
           "check_this_again")


def report_changes(rows, reader_saw_it=True):
    """What moved since the last build, written where a person will find it.

    A fix that withdraws a recommendation changes nothing a reader notices while scrolling: the
    proposal column still shows the same code, because the closest candidate is still worth
    seeing. The analyst reported flagging the same rows twice for exactly that reason. So each
    build records what it changed, and says so in a file rather than leaving it to be discovered.
    """
    snapshot = WORK_DIR / "_queue_previous.json"
    now = {r["link_id"]: {k: str(r.get(k, "")) for k in WATCHED} for r in rows}
    before, rebaselined = {}, False
    if snapshot.exists():
        try:
            stored = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        # The watched set is stored with the snapshot. When it changes, the two are not
        # comparable and every row would report as moved, which is 230 false changes reading
        # exactly like real ones. A widened list rebaselines and says so instead.
        if stored.get("watched") == list(WATCHED):
            before = stored.get("rows", {})
        elif stored:
            rebaselined = True
    changed = []
    for link, current in now.items():
        was = before.get(link)
        if was is None:
            continue
        moved = {k: (was[k], current[k]) for k in WATCHED if was.get(k) != current[k]}
        if moved:
            changed.append((link, moved))
    by_link = {r["link_id"]: r for r in rows}
    lines = ["# What changed in the last rebuild", ""]
    if not reader_saw_it:
        lines.append("The workbook was open and was not refreshed, so what follows is not in it "
                     "yet. This list is being held rather than counted against a file never "
                     "saw, and will still be here after the next build.")
        lines.append("")
    if rebaselined:
        lines.append("The set of columns being watched was widened, so this build is a new "
                     "baseline. The columns carrying the advice were not watched before and "
                     "changes to them were never reported. From the next build they are.")
    elif not before:
        lines.append("No earlier build to compare against. This is the baseline.")
    elif not changed:
        lines.append("Nothing changed. Every row carries the same verdict, recommendation and "
                     "proposal as the previous build.")
    else:
        lines.append("%d row(s) changed. Rows not listed here are exactly as last seen."
                     % len(changed))
        lines.append("")
        for link, moved in sorted(changed,
                                  key=lambda pair: -float(by_link[pair[0]]["value_cad"])):
            row = by_link[link]
            lines.append("## Row %s, %s" % (row["row"], row["retiring_code"]))
            lines.append("")
            lines.append("%s &mdash; CAD %s"
                         % (row["retiring_description"], "{:,.0f}".format(float(row["value_cad"]))))
            lines.append("")
            for field, (was, current) in sorted(moved.items()):
                lines.append("- **%s**" % field)
                lines.append("  - was: %s" % (was or "(blank)"))
                lines.append("  - now: %s" % (current or "(blank)"))
            lines.append("")
    (DECISIONS_DIR / "WHAT_CHANGED.md").write_text("\n".join(lines), encoding="utf-8")
    # The snapshot advances only when the artefact the reader opens was written. It advanced on
    # every build, so a build that skipped a locked workbook still consumed the difference, and
    # the next build reported nothing changed while the sheet had changed on fourteen rows.
    if reader_saw_it:
        snapshot.write_text(json.dumps({"watched": list(WATCHED), "rows": now},
                                       indent=0, sort_keys=True), encoding="utf-8")
    return len(changed), bool(before)


def main():
    rows = build()
    # Lifted off the rows and dropped, so the private key never reaches a file.
    SPANS = rows[0].pop("_spans") if rows else {}
    family_table_by_flow = _families.load_families()
    rows[0].pop("_descriptions", None) if rows else None
    LIVES = rows[0].pop("_lives") if rows else {}
    # The month the RECORD ends each classification, carried beside the lives for the same reason
    # Stage 1c carries it: a candidate is described by the life in force when the classification
    # ended, not when the last shipment cleared. This was the THIRD reader keyed on last_traded,
    # and it made the sheet show a wording that does not produce the score printed beside it.
    # Finding 106.
    ENDS = rows[0].pop("_classification_ends") if rows else {}
    vocabulary = rows[0].pop("_vocabulary") if rows else {}
    DELIVERY_ENDS = rows[0].pop("_delivery_ends") if rows else {}
    for row in rows:
        row.pop("_spans", None)
        row.pop("_descriptions", None)
        row.pop("_lives", None)
        row.pop("_classification_ends", None)
        row.pop("_vocabulary", None)
        row.pop("_delivery_ends", None)
    DECISIONS_DIR.mkdir(exist_ok=True)
    destination = DECISIONS_DIR / "stage2_adjudication_queue.csv"

    # The queue is evidence and holds nothing a person wrote, so it is always safe to rebuild.
    # That is the point of the split: a spreadsheet may mangle this file freely and no judgement
    # is at risk, because the answers live somewhere else.
    # The two files are written independently. The queue is the one likely to be open in a
    # spreadsheet, and it must not block the answer sheet: they serve different purposes and a
    # lock on one says nothing about the other.
    failures = []
    try:
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        wrote_queue = True
    except PermissionError:
        wrote_queue = False
        failures.append("%s is open in another program and was not rewritten" % destination.name)
    try:
        # Every number in this document is counted from the queue being written, so it
        # cannot fall behind the file it describes. Two of them were typed once and were still
        # quoting 143 of 238 on a queue of 231 rows.
        _boundary = sum(1 for _r in rows
                        if (_r.get("successor_began_at_the_boundary") or "").strip() == "yes")
        _aggregate = [_r for _r in rows
                      if (_r.get("successor_is_more_aggregate") or "").strip() == "yes"]
        (DECISIONS_DIR / "README_adjudication_queue.md").write_text(
            README.format(
                boundary_yes=_boundary,
                queue_rows=len(rows),
                aggregate_exports=sum(1 for _r in _aggregate
                                      if _r["link_id"].startswith("exports:")),
                aggregate_imports=sum(1 for _r in _aggregate
                                      if _r["link_id"].startswith("imports:"))),
            encoding="utf-8")
    except PermissionError:
        failures.append("README_adjudication_queue.md is open and was not rewritten")

    # The answer sheet. It holds judgement, so it is merged rather than overwritten.
    #
    # It used to be written once and never again, which was safe and too strict. It meant no
    # column could be added or corrected after the first decision was entered, so every
    # improvement to the evidence had to be finished before adjudication could start. That is
    # backwards: the evidence improves as the work proceeds.
    #
    # So a rebuild now refreshes every evidence column and carries the five judgement columns
    # across untouched, matched on link_id. A decision whose link_id is absent from the new build
    # stops the write and is listed, because a decision that no longer has a retirement to attach
    # to is either a renamed key or a lost row, and neither may be discarded quietly.
    # What the previous build showed, so a corrected wording can be pointed out rather than
    # left for the reader to notice.
    # WHAT WAS ON SCREEN WHEN EACH DECISION WAS TAKEN. Comparing against the previous BUILD made
    # the warning last exactly one rebuild: row 66 was rejected while its proposal read
    # "Butter-making ferment cultures", the wording was corrected, the flag fired once, and by
    # the next build there was no difference left to notice. A decision resting on evidence that
    # has since changed stays flagged until it is decided again.
    _seen_path = WORK_DIR / "_decisions_seen.json"
    _seen = {}
    if _seen_path.exists():
        try:
            _seen = json.loads(_seen_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _seen = {}

    answers = DECISIONS_DIR / "stage2_decisions.csv"
    # Kept so the change report can be run against the sheet rather than the queue. Three of the
    # columns a reader acts on exist only here.
    sheet_entries = []
    kept = read_existing_answers(answers)
    # Filled only where the analyst left it blank, so a typed date always wins.
    decision_dates = load_decision_dates()
    dated_from_evidence = 0
    orphans = sorted(set(kept) - {r["link_id"] for r in rows})
    if orphans:
        raise SystemExit(
            "Adjudication answers not written. %d decision(s) refer to a retirement this build "
            "does not contain:\n  %s\n"
            "Nothing was changed. Either the delivery or a rule moved underneath them, and which "
            "one it was has to be established before those decisions are carried forward."
            % (len(orphans), "\n  ".join(orphans[:20])))
    try:
        with open(answers, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DECISION_COLUMNS)
            writer.writeheader()
            for row in rows:
                held = kept.get(row["link_id"], {})
                answered = bool((held.get("decision") or "").strip())
                # Sticky: once recorded it is never refreshed, or it could not detect a change.
                decided_against = (held.get("decided_against_successor") or "").strip()
                if answered and not decided_against:
                    decided_against = (held.get("proposed_successor") or "").strip()
                if not answered:
                    decided_against = ""
                # Derived from the queue row rather than transcribed into a literal. The
                # literal that used to sit here was not updated when columns were added, so
                # seven of them reached the workbook empty while the queue held their values.
                span = " to ".join(x for x in (row["proposed_successor_first_traded"],
                                               row["proposed_successor_last_traded"]) if x)
                # THE SECOND ALTERNATIVE, laid out exactly like the proposal above it.
                #
                # It was one prose column called best_alternative, which was both hard to read
                # and wrongly named: if it were the best it would have been proposed. It is the
                # next thing worth looking at, so it is named that and given the same four
                # columns the proposal has, to be compared line against line.
                #
                # Filled only where the verdict is ANALYST. A CONFIRM row has a proposal the
                # evidence supports, and offering an alternative beside it invites doubt the
                # software does not have.
                second = second_text = second_span = second_score = ""
                # WHY THE CHOSEN ALTERNATIVE WAS REMOVED, on the rows where one had been.
                #
                # closest_removed_candidate is one of the option sources below, so a candidate a
                # meaning gate ruled out can be, and is, offered here. The sentence that said so
                # was assembled into a local named `alternative` that nothing ever read: six
                # assignments and not one load anywhere in the file. So the workbook showed the
                # code, its description, its months and its score with nothing at all recording
                # that it had been removed. On sheet row 74, imports 3003.39.91.00 retiring
                # 1997-07, the advice read "SECOND. The alternative is this code's own family
                # line" against a candidate vetoed on continuity that first trades 2012-01,
                # fourteen years after the retirement it was offered for.
                #
                # The declared order is that the official record decides, a meaning gate may only
                # veto, and text may only rank. An unlabelled recommendation onto a vetoed
                # candidate is that order running backwards. The candidate is still shown, because
                # hiding it would be worse and the analyst has repeatedly wanted to see what was
                # removed. It is labelled instead.
                second_removed_why = ""
                if row["verdict"].startswith("ANALYST"):
                    # EVERY OPTION IS RULE-CHECKED, not only the first.
                    #
                    # passes_every_rule was applied to the replacement candidate and to nothing
                    # else, so when no replacement existed the fallbacks were offered unchecked.
                    # On the waste pharmaceuticals block that handed back another co-casualty
                    # every time: 3006.80.90.30 stops 2005-01 and was offered a code stopping
                    # 2005-11, while chain_ends_at already held 3006.92.00.00, where the whole
                    # block actually went.
                    #
                    # The terminus now sits second, after the checked replacement, because a
                    # chain followed to its end IS the destination and no scoring can beat that.
                    # EVERY option source is checked against the removals, not just the one whose
                    # name says "removed". Tagging closest_removed_candidate alone caught one row
                    # of the four: a candidate a gate removed can also arrive as the class
                    # residual or as the runner up, and on three rows it did. So the removal is
                    # looked up by CODE, from the row's own record of what was removed and why,
                    # which is the only form that cannot depend on which branch offered it.
                    removed_on_meaning = {}
                    for item in (row["candidates_removed_on_meaning"] or "").split(";"):
                        item = item.strip()
                        if not item or item == "none" or "(" not in item:
                            continue
                        name, _, why = item.partition("(")
                        removed_on_meaning[name.strip()] = why.rstrip(")").strip()
                    options = []
                    if row["best_candidate_passing_every_rule"]:
                        options.append((row["best_candidate_passing_every_rule"],
                                        row["best_candidate_description"],
                                        row["best_candidate_wording_match"], True))
                    if row["chain_ends_at"] and "each other" not in row["chain_ends_at"]:
                        # Rule-checked like everything else. Exempting it offered Hydrocortisone
                        # as the terminus for Betamethasone, which is the swapped term the row
                        # was withheld for in the first place.
                        options.append((row["chain_ends_at"], "", "", False))
                    if row["same_wording_reappears_at"]:
                        options.append((row["same_wording_reappears_at"],
                                        row["retiring_description"], "1.0000", False))
                    if row["class_residual_available"]:
                        options.append((row["class_residual_available"].split(";")[0].strip(),
                                        row["class_residual_description"].split(";")[0].strip(),
                                        row["class_residual_wording_match"], False))
                    if row["closest_removed_candidate"]:
                        options.append((row["closest_removed_candidate"],
                                        row["closest_removed_description"],
                                        row["closest_removed_wording_match"], False))
                    if row["runner_up"]:
                        options.append((row["runner_up"], row["runner_up_description"],
                                        row["runner_up_wording_match"], False))
                    for code, text, score, already_checked in options:
                        bare = code.replace(".", "")
                        pair = span_shown(SPANS[row["flow"]], bare,
                                          row["last_traded"].replace("-", ""))
                        # The catalogue description, always. class_residual_description carries
                        # "text (score)" for display, and filtering on that compared a score
                        # against nothing and let four codes through.
                        # The wording in force at THIS boundary, as everywhere else. This
                        # was the last reader of the earliest-wording map, so the second
                        # alternative was described, and rule-checked, in whatever the code was
                        # called when it began.
                        _stop = row["last_traded"].replace("-", "")
                        _stop = ENDS.get((row["flow"], row["retiring_code"].replace(".", ""),
                                          _stop), _stop)
                        body = description_shown(LIVES[row["flow"]], bare, _stop) or text
                        if not already_checked:
                            # EVERY rule, not just the timing one. Filtering for co-casualty
                            # alone still offered eight codes that swap the term carrying the
                            # meaning and five that share no distinctive word with the
                            # retirement. Found by the audit in check_rule_application.
                            if pair and pair[1] and not still_running(
                                    pair[1], DELIVERY_ENDS.get(row["flow"], "999912")):
                                outlives = months_between(row["last_traded"], month(pair[1]))
                                if outlives is not None and outlives <= CO_CASUALTY_MONTHS:
                                    continue
                            if _gates.swapped_term(_expand(row["retiring_description"]).lower(),
                                                   _expand(body or "").lower()):
                                continue
                            if body and not (
                                    ANY_RESIDUAL.search(row["retiring_description"].lower())
                                    or ANY_RESIDUAL.search(body.lower())):
                                words = vocabulary.get(row["flow"], set())
                                mine = {w for w in set(prepared_for_score(
                                    row["retiring_description"]).split()) & words
                                    if not w.isdigit()}
                                theirs = {w for w in set(prepared_for_score(body).split())
                                          & words if not w.isdigit()}
                                if mine and theirs and not (mine & theirs):
                                    continue
                        # A BLANK SCORE READS AS "NO SCORE EXISTS", AND ON FOUR ROWS ONE DID.
                        # The chain terminus is the only option offered without a score, because
                        # it comes from chain_ends_at rather than from the ranking, and it reached
                        # the sheet unscored on all ten rows that took it. On rows 40, 41 and 50
                        # the alternative equalled or beat the proposal it sat beside, and the
                        # reader could not see it. Computed here with the ranker's own function
                        # against the wording in force at this boundary, so the number beside the
                        # alternative means what the number beside the proposal means. Verified
                        # to reproduce the ranked score exactly on the four that carry one.
                        # On the six waste rows the terminus was never a ranked candidate at all,
                        # and its computed score is well below the proposal's, which is the point:
                        # it is offered because the chain ends there, not because it reads alike.
                        second, second_text = code, body
                        second_removed_why = removed_on_meaning.get(code, "")
                        second_score = score or ("%.4f" % wording_ratio(
                            row["retiring_description"], body) if body else "")
                        second_span = " to ".join(month(x) for x in pair if x)
                        break
                # Said in words, because a blank in four columns reads as something forgotten
                # rather than as a finding. On these rows every candidate the pipeline can see
                # trips a rule, which is itself worth knowing before deciding.
                if row["verdict"].startswith("ANALYST") and not second:
                    second_text = ("no other candidate passes the rules; every one either swaps "
                                   "the term that carries the meaning, shares nothing with this "
                                   "description, or stops trading within two years of it")
                rel_second = (_families.relationship(family_table_by_flow, row["flow"],
                                                     row["retiring_code"], second, second_text,
                                                     row["retiring_description"],
                                                     row["last_traded"].replace("-", ""))
                              if second else "")
                relation = (row["how_they_relate"] or "").split(" (")[0]
                # The retiring wording goes in too. Without it the guard against a family
                # crossing a declared distinction cannot fire, and the advice went on calling a
                # veterinary residual the human code's own family line after the relationship
                # column had stopped doing so. Two answers to one question, from one function
                # called two ways.
                alt_is_own_line = _families.leads_to_own_line(
                    family_table_by_flow, row["flow"], row["retiring_code"], second, second_text,
                    row["retiring_description"], row["last_traded"].replace("-", ""))
                # Only where the row is the analyst's to decide. A CONFIRM row has no second alternative
                # computed, so the "nothing else qualifies" branch fired on 31 of them and told
                # the reader to reject a row the evidence supports.
                if not row["verdict"].startswith("ANALYST") or not relation or relation == "unknown":
                    points_to = ""
                elif (row["retiring_description"].strip().lower()
                        == row["proposed_successor_description"].strip().lower()):
                    # Ahead of every family test. An identical wording is the strongest evidence
                    # on the row and it is not a judgement call. Putting the leftover-line test
                    # first sent rows 41 and 127 to SECOND when their proposal carried the very
                    # same description, which is the same commodity under a new number.
                    points_to = ("ACCEPT: the wording is identical, so this is the same "
                                 "commodity under a new number.")
                elif relation == _families.OWN_LINE:
                    points_to = ("ACCEPT: the proposal IS this code's own family line, which "
                                 "is where a closing line usually goes.")
                elif alt_is_own_line:
                    points_to = ("SECOND. The alternative is this code's own family line, which "
                                 "is where a closing line usually goes.")
                elif relation == _families.CATCH_ALL:
                    points_to = ("The proposal is a catch-all line, so accepting it aggregates "
                                 "these goods rather than matching them. Judge whether that is "
                                 "where the trade went.")
                elif relation.startswith("same"):
                    # Tested BEFORE the absence of an alternative. Whether anything ELSE
                    # qualifies says nothing about whether the proposal is right, and asking
                    # it first let an empty alternative overrule the evidence: rows 5 and 59
                    # were advised to reject a proposal the table calls the same kind of
                    # medicine.
                    #
                    # The closing clause used to read "though they are different substances"
                    # on every one of these, which the table does not know and which was false
                    # on five of fourteen: rows 41 and 127 carry identical wording, and adrenal
                    # cortical against corticosteroid is one substance under two names. It now
                    # says only what the row can show.
                    kind = ("same kind of medicine" if "class" in relation else "same family")
                    if (row["retiring_description"].strip().lower()
                            == row["proposed_successor_description"].strip().lower()):
                        points_to = ("ACCEPT: the wording is identical, so this is the same "
                                     "commodity under a new number.")
                    elif row["successor_swaps_a_term"] == "yes":
                        points_to = ("ACCEPT is defensible: both are the %s. Confirm that %s "
                                     "and %s name the same goods."
                                     % (kind, row["term_in_the_retiring_code"],
                                        row["term_in_the_successor"]))
                    else:
                        points_to = "ACCEPT is defensible: both are the %s." % kind
                elif not second:
                    points_to = ("REJECT and name a code, or NONE if the goods left the chapter. "
                                 "The proposal is a %s and nothing else here qualifies."
                                 % ("different kind of medicine" if "class" in relation
                                    else "different family"))
                else:
                    points_to = ("NOT the proposal: it is a %s. Neither code offered is this "
                                 "one's own family line, so weigh both."
                                 % ("different kind of medicine" if "class" in relation
                                    else "different family"))
                # THE REMOVAL, SAID OUT LOUD, AND SAID FIRST.
                #
                # It goes at the FRONT of the advice rather than beside the code, because the
                # column a reader scans is this one and the removal is the part that changes what
                # the row means. A gate ruled this candidate out; the sheet may show it, so the
                # analyst can disagree with the gate, but it may not recommend it silently.
                #
                # Everything between here and the ledger below used to be three verbatim copies
                # of the answered/decided_against/span block already computed at the top of this
                # loop, wrapped around a 27-line if/elif chain assigning a local named
                # `alternative` that nothing anywhere read. The chain's fourth branch is where
                # the removal sentence lived, which is exactly why the workbook never carried it.
                # ONLY where the advice actually sends the reader to the alternative. The first
                # version of this put the warning in front of every points_to on a row whose
                # alternative had been removed, and three of the four say ACCEPT about the
                # PROPOSAL, which the removal has nothing to do with. Row 41 then read "REMOVED
                # ON continuity ... ACCEPT: the wording is identical", which says the opposite of
                # the truth: the proposal's wording is identical and stands, and it is the
                # alternative beside it that a gate took out. Two controls in
                # check_medicine_families.py caught it, both asserting that a row whose wording
                # is identical says so. They were right and the prefix was wrong.
                if second and second_removed_why and points_to.startswith("SECOND"):
                    points_to = ("REMOVED ON %s, so this is shown as evidence and NOT as a "
                                 "recommendation. Weigh the removal before anything else. %s"
                                 % (second_removed_why, points_to)).strip()
                # Carried on the alternative's own column in every case, which is the column that
                # is unambiguously about it. This is what the unlabelled control reads, so the
                # guarantee does not depend on the advice happening to mention it.
                removal_note = (" [REMOVED ON %s]" % second_removed_why
                                if second and second_removed_why else "")
                answered = bool((held.get("decision") or "").strip())
                # Recorded the first time a decision appears, and refreshed only when the
                # decision itself changes. So the evidence on file is what was on screen when
                # the judgement was made, and a later correction stays visible against it
                # instead of expiring with the next rebuild.
                decision_now = (held.get("decision") or "").strip()
                was = _seen.get(row["link_id"], {})
                if answered and was.get("decision") != decision_now:
                    was = {"decision": decision_now,
                           "proposed_successor": row["proposed_successor"],
                           "proposed_successor_description":
                               row["proposed_successor_description"]}
                    _seen[row["link_id"]] = was
                elif not answered:
                    _seen.pop(row["link_id"], None)
                recheck = ""
                # Read from the ledger, not from the sheet. decided_against fell back to
                # whatever the sheet currently showed, so once a rebuild wrote the new proposal
                # into it the two agreed again and the warning vanished. Row 71 was decided
                # against the blood residual, was moved to Ricin, said so once, and then stopped.
                # THE STRONGEST OF THESE, so it is asked first. A held row is one the official
                # record may still speak on, and an answer already given to it is not merely
                # unrecommended: it is a judgement a document can overturn, which is the precise
                # sequence the hold exists to prevent. Three export rows arrived in this state
                # when the hold was corrected to key on the stated termination rather than on the
                # last month with trade, and every one of them was already answered. The decision
                # is left exactly as the analyst wrote it; only the warning is added.
                # BOTH, WHERE BOTH APPLY, AND THE MOVED PROPOSAL LEADS.
                #
                # The hold branch was written first and tested first, on the reasoning that a
                # hold is the stronger statement. It is not the more USEFUL one: the verdict
                # column already says a row is held, in words, one column away. That a proposal
                # moved underneath a decision is the thing a reader cannot see anywhere else.
                # When Layer 2 went live three decided rows had their proposal changed by the
                # official record and every one of them reported only "it is now HELD", which is
                # true, visible elsewhere, and not the point.
                held_note = ""
                if answered and row["verdict"].startswith("DO NOT DECIDE"):
                    held_note = (" It is also HELD (%s): the hold is not a disagreement with the "
                                 "answer, it says the record may still overturn it."
                                 % row["verdict"].split("-", 1)[-1].strip())
                if answered and was.get("proposed_successor", row["proposed_successor"]) \
                        != row["proposed_successor"]:
                    recheck = ("this was decided while it proposed %s; it now proposes %s, %s"
                               % (was.get("proposed_successor", ""), row["proposed_successor"],
                                  row["proposed_successor_description"]))
                elif answered and was.get("proposed_successor_description",
                                          row["proposed_successor_description"]) \
                        != row["proposed_successor_description"]:
                    # The strongest reason to look again, and it had no branch. Ten proposals
                    # were printing a description from a life that had already closed, four of
                    # them on rows already decided, and row 7 showed "Penicillin V" where the
                    # life receiving the trade reads "Amoxycillin", the retirement's own name.
                    recheck = ("this was decided while the proposal read %r; it now reads %s"
                               % (was.get("proposed_successor_description", ""),
                                  row["proposed_successor_description"]))
                elif answered and row["verdict"].startswith("DO NOT DECIDE"):
                    recheck = ("this one was decided and it is now HELD (%s). The hold is not a "
                               "disagreement with the answer; it says the official record has "
                               "not been read yet and may overturn it"
                               % row["verdict"].split("-", 1)[-1].strip())
                    held_note = ""
                elif answered and not row["verdict"].startswith("CONFIRM"):
                    # Says only what is true. This read "a rule added after the ruling no
                    # longer recommends it", on every answered row the method does not recommend,
                    # whether or not any rule had been added since.
                    recheck = ("this one was decided and the method still does not recommend the "
                               "proposal; the reason is in the why column")
                # THE CARVE-OUT WARNING, WHICH SPEAKS WHATEVER THE VERDICT IS.
                #
                # It goes in check_this_again rather than what_this_points_to because the latter
                # is guidance and may speak only where a judgement is asked for, and this needs
                # to reach a CONFIRM row: row 210, the largest link in the delivery, carried a
                # CONFIRM onto the influenza line it was defined to exclude. A warning that goes
                # quiet on exactly the rows the software is most confident about is no warning.
                if row.get("successor_was_carved_out_of_it") == "yes":
                    carved = ("THE PROPOSAL MAY INVERT THIS LINE'S MEANING: %s is a leftover "
                              "line, and %s named %s beside it while it traded, so this line "
                              "was the goods that are NOT that. The proposal turns on %s. "
                              "Flagged, not removed."
                              % (row["retiring_code"], row["carved_out_by"],
                                 row["carved_out_term"], row["carved_out_term"]))
                    recheck = (recheck + " " + carved) if recheck else carved
                # Same placement and the same reason: this has to reach a CONFIRM row, because
                # the ranker being confident is not evidence that it read the boundary.
                if row.get("a_leftover_line_widened_here") == "yes":
                    widened = ("A LEFTOVER LINE WAS WIDENED AT THIS VERY BOUNDARY: %s kept its "
                               "number across %s and its published scope gained %s. Wording "
                               "similarity cannot see that a description CHANGED, so it ranks "
                               "that line %s. Check whether the goods went there. Flagged, not "
                               "ranked."
                               % (row["widened_line"], row["last_traded"],
                                  row["widened_line_added_terms"], row["widened_line_rank"]))
                    recheck = (recheck + " " + widened) if recheck else widened
                if recheck and held_note:
                    recheck += held_note
                entry_row = {
                    "link_id": row["link_id"], "row": row["row"], "verdict": row["verdict"],
                    "why": row["why_not_recommended"],
                    "retiring_code": row["retiring_code"],
                    "retiring_description": row["retiring_description"],
                    "retiring_last_traded": row["last_traded"],
                    "proposed_successor": row["proposed_successor"],
                    "proposed_successor_description": row["proposed_successor_description"],
                    "proposed_successor_traded": span,
                    "proposed_successor_wording_match": row["wording_match"],
                    # One column, not the queue's three. It carries the finding and where the
                    # finding came from, because "different class" asserted from memory and
                    # "different family" read off the tariff are not equally strong and a reader
                    # deciding a row is entitled to know which they are looking at.
                    # Two relations rest on nothing the table supplied and must not borrow its
                    # provenance. Identical wording is OBSERVED, in the two columns beside it,
                    # and 94 rows were reporting it as asserted. Whether a line is a catch-all is
                    # read off the description in the same way.
                    "how_they_relate": (
                        "%s (%s)" % (row["how_they_relate"],
                                     "the two descriptions match"
                                     if row["how_they_relate"] == _families.SAME_COMMODITY
                                     else "read off the successor's own wording"
                                     if row["how_they_relate"] == _families.CATCH_ALL
                                     else "from the tariff structure"
                                     if row["family_evidence"].startswith("derived")
                                     else "asserted, no source")
                        if row["how_they_relate"] and row["how_they_relate"] != "unknown"
                        else row["how_they_relate"]),
                    # WHICH WORD THE RELATIONSHIP POINTS TO. Advisory, and only that: it names
                    # one of the two codes already on the row and cannot introduce a third. The
                    # provenance sits beside it, so a suggestion resting on an asserted class can
                    # be weighed differently from one read off the tariff.
                    #
                    # The strongest case is the alternative being this code's own family line:
                    # measured against Canada's concordance, a specific line closing goes to a
                    # leftover 62% of the time and to a genuinely different named substance in 8
                    # of 71 cases.
                    # The record's narrowing leads, because it outranks everything the
                    # advice below it is derived from.
                    #
                    # ON A ANALYST ROW ONLY. This column is guidance, and the standing rule is that
                    # guidance may speak only where a judgement is asked for. Moving the note out
                    # of why_not_recommended fixed a decline appearing on CONFIRM rows and then
                    # reproduced the same fault one column across: the note landed on the same six
                    # settled rows, which are told to confirm and given advice in the same breath.
                    # On two of them, 215 and 220, no advice had been computed at all, so the note
                    # became the whole column and displaced the "ACCEPT: the wording is identical"
                    # lead that identical wording is required to keep.
                    #
                    # The evidence is not lost, it is where the evidence belongs. All six rows
                    # still carry official_record naming the WCO correlation in
                    # stage2_adjudication_queue.csv, which is the evidence file. The sheet is the
                    # answer file and does not carry that column at all. Splitting the two is
                    # deliberate and predates this, and a settled row is precisely the row whose
                    # evidence the analyst is not being asked to weigh.
                    "what_this_points_to": " ".join(x for x in (
                        ((row.get("record_narrowed_note") or "")
                         if row["verdict"].startswith("ANALYST") else ""), points_to) if x),
                    "second_alternative": second,
                    "second_alternative_description": second_text,
                    "second_alternative_traded": second_span,
                    "second_alternative_wording_match": second_score,
                    # The same question asked of the OTHER code on the row. The relationship was
                    # computed for the proposal alone, so a row whose guidance said SECOND
                    # pointed at a commodity with nothing said about it. If the reader is being
                    # told to prefer it, they are entitled to the same evidence.
                    # The removal is repeated here, beside the relationship, because these two
                    # columns are read together and a reader who starts at the relationship
                    # would otherwise meet a vetoed candidate described as though it stood.
                    "how_the_second_relates": ((
                        "%s (%s)" % (rel_second,
                                     "the two descriptions match"
                                     if rel_second == _families.SAME_COMMODITY
                                     else "read off the alternative's own wording"
                                     if rel_second == _families.CATCH_ALL
                                     else "asserted, no source"
                                     if _families.basis_of(family_table_by_flow, row["flow"],
                                                           row["retiring_code"], second,
                                                           second_text,
                                                           row["last_traded"].replace("-", "")
                                                           ) == "class"
                                     else "from the tariff structure")
                        if rel_second and rel_second != "unknown" else rel_second)
                        + removal_note),
                    "check_this_again": recheck,
                    "decision": held.get("decision", ""),
                    "correct_successor_if_rejected":
                        held.get("correct_successor_if_rejected", ""),
                    "reason": held.get("reason", ""),
                    "decided_by": held.get("decided_by", ""),
                    # THE ANALYST'S OWN VALUE ALWAYS WINS. Evidence fills a blank and never
                    # replaces a date somebody typed, because the two mean different things: a
                    # typed date is when the decision was taken and the derived one is when it
                    # was written down. Overwriting the first with the second would quietly
                    # downgrade the better record on exactly the rows that have one.
                    "decided_on": (held.get("decided_on", "").strip()
                                   or decision_dates.get(row["link_id"], "")),
                }
                if (not held.get("decided_on", "").strip()
                        and decision_dates.get(row["link_id"])
                        and (held.get("decision") or "").strip()):
                    dated_from_evidence += 1
                writer.writerow({c: entry_row.get(c, "") for c in DECISION_COLUMNS})
                sheet_entries.append(dict(entry_row, value_cad=row["value_cad"]))
        _seen_path.write_text(json.dumps(_seen, indent=0, sort_keys=True), encoding="utf-8")
        answered = sum(1 for r in rows
                       if any((kept.get(r["link_id"], {}).get(c) or "").strip()
                              for c in WORK_COLUMNS))
        print("  written: %s%s" % (answers.relative_to(PROJECT_ROOT),
                                   "  (%d answer(s) carried across)" % answered
                                   if answered else ""))
        if decision_dates:
            print("  provenance: %d decision date(s) filled from evidence, %d already recorded "
                  "by hand" % (dated_from_evidence, answered - dated_from_evidence))
        else:
            print("  provenance: evidence/provenance/decision_dates.csv is absent, so decided_on "
                  "is left blank. Run evidence/provenance/derive_decision_dates.py.")
        # The workbook, refreshed in place. Formatting is carried across on link_id rather than
        # on position, because a rebuild reorders rows and a highlight moved onto a different
        # retirement would say nothing about having moved.
        book = DECISIONS_DIR / WORKBOOK
        try:
            sheet_rows = list(csv.DictReader(
                open(answers, encoding="utf-8-sig", newline="")))
            styling = {}
            if book.exists():
                had_columns, had_rows = _xlsx.read(book)
                styling = _xlsx.formatting_by_key(had_columns, had_rows, "link_id")
            # A HIGHLIGHT IS A PROPERTY OF THE ROW, NOT OF THE CELLS THAT HAPPEN TO SURVIVE.
            #
            # Formatting is captured per column, so trimming the sheet from 33 columns to 18 left
            # the analyst's twelve highlighted rows shaded across seven columns instead of
            # sixteen: the same rows, looking half marked. Where a row carries one dominant style
            # across several columns, that style is spread over the whole row again. The date
            # columns are excluded because Excel puts its own number format there and it is not
            # a highlight anyone applied.
            DATE_FORMATTED = {"last_traded", "retiring_last_traded",
                              "proposed_successor_first_traded",
                              "proposed_successor_last_traded", "proposed_successor_traded",
                              "closest_removed_first_traded", "closest_removed_last_traded"}
            painted = []
            for r in sheet_rows:
                marks = styling.get(r["link_id"], {})
                applied = [style for column, style in marks.items()
                           if column not in DATE_FORMATTED]
                whole_row = ""
                if applied:
                    whole_row = max(set(applied), key=applied.count)
                painted.append({c: ((r[c], marks[c]) if c in marks
                                    else (r[c], whole_row) if whole_row
                                    else r[c])
                                for c in DECISION_COLUMNS})
            if book.exists():
                _xlsx.write(book, DECISION_COLUMNS, painted)
            else:
                _xlsx.write(book, DECISION_COLUMNS, painted,
                            template=PROJECT_ROOT / "pipeline" / "_blank_workbook.xlsx")
            # Rows carrying a COLOUR, not rows carrying a style id. Excel writes an explicit
            # style on every cell when it saves, so counting style ids reported 230 rows kept
            # their highlighting on a workbook holding three marks, which reads as reassurance
            # and is not one.
            coloured = _xlsx.coloured_rows(book) if book.exists() else set()
            kept_marks = sum(1 for r in sheet_rows if r["link_id"] in coloured)
            print("  written: %s  (%d row(s) kept their highlighting)"
                  % (book.relative_to(PROJECT_ROOT), kept_marks))
        except PermissionError:
            failures.append("%s is open in another program and was not refreshed" % WORKBOOK)
        except Exception as error:                      # noqa: BLE001
            failures.append("%s could not be refreshed (%s: %s)"
                            % (WORKBOOK, type(error).__name__, error))
    except PermissionError:
        failures.append("%s is open in another program and was not written" % answers.name)

    # Reported against the SHEET, which is the file the reader opens, and counted as seen only
    # when the workbook itself was refreshed.
    workbook_refreshed = not any("open in another program" in f for f in failures)
    moved, had_baseline = report_changes(sheet_entries or rows, workbook_refreshed)
    print("  written: %s%s" % ((DECISIONS_DIR / "WHAT_CHANGED.md").relative_to(PROJECT_ROOT),
                               "  (%d row(s) changed since the last build)" % moved
                               if had_baseline else "  (baseline, nothing to compare)"))

    decide = [r for r in rows if r["status"] == "decide"]
    print("Adjudication queue built.")
    print("  rows total            : %d" % len(rows))
    print("  to decide now         : %d, CAD {:,.0f}".format(
        sum(float(r["value_cad"]) for r in decide)) % len(decide))
    print("  held, do not decide   : %d, CAD {:,.0f}".format(
        sum(float(r["value_cad"]) for r in rows if r["status"] != "decide"))
        % (len(rows) - len(decide)))
    print()
    counts = {}
    for r in decide:
        counts[r["priority"]] = counts.get(r["priority"], 0) + 1
    for priority in sorted(counts):
        print("     priority %s  %-58s %3d"
              % (priority, PRIORITY_NAMES.get(priority, ""), counts[priority]))
    print()
    if wrote_queue:
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
    if wrote_queue:
        print("  written: %s" % (DECISIONS_DIR / "README_adjudication_queue.md").relative_to(PROJECT_ROOT))
    if failures:
        print()
        for failure in failures:
            print("  NOT WRITTEN: %s" % failure)
        print("  Close the file and run this again. Everything else above was written.")
        return 4


if __name__ == "__main__":
    sys.exit(main() or 0)
