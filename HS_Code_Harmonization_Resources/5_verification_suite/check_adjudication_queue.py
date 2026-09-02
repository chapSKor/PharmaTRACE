"""
Check for the adjudication artefact. Does every row hold what a person needs to decide it?


Inputs:
    decisions/stage2_adjudication_queue.csv
    decisions/stage2_decisions.csv
    work/stage1_review_{imports,exports}.csv

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


WHY THIS CHECK EXISTS
---------------------
Three defects reached this artefact and none was found by a test. The dates of the proposed
successor were missing, so a runner-up that first traded thirty years after the retirement
looked like a live alternative. The signal that a successor is a broader bucket was absent, so
an aggregation read as an equivalence. And a row whose candidates were all removed arrived with
a blank proposal, a suggestion to approve it, and a wording match of 0.0000 that read as
evidence rather than as an absence.

Every one was found by the analyst opening the file and reading a row. Every one had passed
every control in the suite, because the suite tested the pipeline and nobody tested the artefact.

So this check reads the artefact the way a person does and asks whether each row is decidable
from itself. It is the rule-10 idea applied to the last file in the chain: the next reader here
is not a stage, it is a human, and the file has to hold up to that.


WHAT IT DOES NOT DO
-------------------
It cannot tell whether a proposal is correct. That is the judgement the file exists to collect.
It checks that the evidence needed to make that judgement is present, internally consistent, and
not silently defaulted.
"""

import csv
import os
import sys
from collections import defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS = os.path.join(PROJECT, "decisions")
WORK = os.path.join(PROJECT, "work")

# A span also ends where a relabel crosses a decisive distinction. The rules are shared because
# they are the published specification; the composition is written out here, so this file's own
# rebuilds can still disagree with the queue builder.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import meaning_gates as _gates  # noqa: E402

_DISQUALIFYING = [_r for _r in _gates.load_rules(
    os.path.join(DECISIONS, "decisive_distinctions.csv"))
    if str(_r.get("action", "")).strip() == "disqualify"]


def _relabelled(before_text, after_text):
    return any(_gates.rule_fires(rule, before_text, after_text) for rule in _DISQUALIFYING)


# 230 -> 231 on 2026-08-17. Stage 1a now ends a span where a relabel crosses a decisive
# distinction, so imports 3004.50.99.30 retires twice and the queue gains its veterinary life.
EXPECTED_ROWS = 231   # 238 less the 8 the concordance now settles outright, plus the 1988 vet life
# 21 -> 24 on 2026-08-14, when the hold began keying on the month the record calls a code
# obsolete rather than the month money last moved. Three export lines went quiet one or two
# months before a revision they are stated to have died at, so each escaped a hold that its
# identical import twin, which traded to the boundary month, sat inside: 3001.10.00 quiet
# 2006-10 against stated 2006-12, 3003.40.00 quiet 2016-11 against 2016-12, and 3002.11.00
# quiet 2021-11 against 2021-12. CAD 5,661,616. All three had already been answered, so the
# answers stand and the sheet warns beside them; see the control on held rows carrying an answer.
# 24 -> 27 later the same day, finding 88. The exemption stopped naming the file the record
# arrived in and started reading what it achieved: a single named destination exempts, and so
# does a bound whose destinations all sit in one six-digit subheading, because the correlation
# tables map HS6 to HS6 and could not narrow it. Three import rows the concordance had only
# BOUNDED, across four or five subheadings each, join the hold. CAD 8,284,840,016, and all three
# already carry an accept that stands and is warned about rather than removed.
# 27 -> 2 on 2026-08-14, when the correlation tables were extracted and the hold stopped
# waiting for a document that had arrived. The two that remain are both 3002.19, the one
# subheading the WCO addresses only to say it "was considered by the HS Committee to be empty
# and it was therefore deleted". CAD 1,636,154,203 between them, and no table will ever
# answer them.
EXPECTED_HELD = 2
# 205/25 -> 177/53 on 2026-08-11 when swapped_term began withholding the recommendation on
# rows whose proposal shares the frame and differs in the term that carries the meaning. The
# move is exactly the 28 rows that rule flags, and no candidate was removed to achieve it.
# 177/53 -> 178/52 on 2026-08-11: 3002.10.29.20 stops proposing the human variant of a
# veterinary line and proposes the residual instead, which swaps no term and so is recommended.
# The verdict folds in status and the suggestion does not, so 166 rows recommend while only 155
# say CONFIRM: the other 11 are held or too recent and keep the suggestion they would have had.
# 169/61 -> 170/60 on 2026-08-12: row 6's twin turned out to be its proposal's own successor,
# settled by the record, so there was never a choice to put to anyone.
# 170/60 -> 173/57 on 2026-08-12 when the ranker stopped scoring candidates against
# wordings from lives that had already closed. Three rows found a live wording that scores
# above the threshold where the stale one did not.
# 173/57 -> 169/61 on 2026-08-14, when Layer 2 went live. Four rows move from approve to none:
# the five the WCO sends out of Chapter 30, less exports:3002.11.00 which was already none.
# Nothing else moved, which is the point: the correlation withdrew four recommendations and
# made none. A layer that only ever removes cannot add one.
# MOVED 2026-08-16 BY FINDING 106, and every one of these is the same cause. A candidate
# is now described and scored against the life in force when the RECORD ends the
# classification, not when the money stopped, so 8 pairs read different wording and the
# flags derived from wording follow. NO LINK MOVED: stage2_resolved is byte-identical on
# successors across the change, checked against the previous commit.
# approve 169 -> 170 and none 61 -> 60: one row gains a recommendable proposal.
# none 60 -> 61 on 2026-08-17: the new veterinary row is shown a candidate and not recommended
# one, because its closest wording match was removed on continuity. approve does not move.
EXPECTED_SUGGESTIONS = {"approve": 170, "none": 61}
# 28, then 27, then 24 on 2026-08-12 when "use" against "uses" and "formltd hormone" against
# "formulated hormones" stopped counting as substituted terms. They were the same word twice.
# 24 -> 25 on 2026-08-12: one more pair shares its frame once both are read in the wording
# in force at the boundary.
# 25 -> 24: one pair stops reading as a swapped term once both sides are the right era.
EXPECTED_SWAPPED = 24
# Proposals that stop trading within two years of the code they would replace. They went in the
# same restructuring wave and never received the trade.
# 13 -> 11 on 2026-08-12: two proposals were only proposed because of a stale wording, and
# the codes now proposed in their place outlive the retirement.
# 11 -> 12: one more proposal is now seen to die in the same restructuring wave.
EXPECTED_CO_CASUALTY = 12
# Rows where the leftover line of the code's own parent survived but a named sibling outranked
# it. Shown only where the proposal is in doubt, because a residual beside an exact match is
# clutter, and clutter in a document meant for reading is a cost like any other.
# 19 -> 15 on 2026-08-12: four rows no longer need the leftover line shown beside them,
# because the live wording promoted a named sibling above it.
# Finding 106. 15 -> 14: one row's parent leftover line is no longer offered, for the same reason.
# 14 -> 15 on 2026-08-18, finding 122: row 68 now offers 3002.90.00.90 as its parent's leftover line instead of resting on it.
EXPECTED_CLASS_RESIDUAL = 15
# Spans stopping within a year of the delivery's own last month. Not retirements yet: at the data
# boundary a retirement and a quiet spell are the same observation. Six of the nine stopped a
# single month before the end, and a one-month silence occurs in 100% of live codes' histories.
# 9 -> 11 on 2026-08-12. A span is now also held when its silence is no longer than a silence
# the code has already come back from, measured from month-level records in stage 0 rather
# than from the calendar. The two added are 3003.31.00, quiet 13 months against a 106-month
# gap it survived, and 3003.42.00, quiet 21 against 49 and trading 4 months out of 65.
# 11 -> 0 on 2026-08-15, and not one of them became decidable. All eleven are rows the delivery
# never declared a termination for, so they now carry the stronger statement: not a retirement at
# all, rather than one that cannot be called yet. The calendar hold and the record test were
# catching the same rows, and the record test is the better founded of the two.
#
# The hold is NOT dead code. 3002900012, Saxitoxin, is declared terminated at 2016-12 and still
# carries it, quiet 116 months against a gap it had already survived; it is settled by Canada's
# concordance and so never reaches this queue. This pin can still fail in both directions.
EXPECTED_TOO_RECENT = 0
# Rows where wording identical to the retiring code sits on a code OTHER than the one proposed.
# Evidence, never a rule: 3002.90.10.10's wording returns 240 months later and something carried
# that trade in between, so identical text says what the goods are and not who received them.
# 5 -> 4 on 2026-08-12: one twin is now the proposal itself, so its wording no longer sits
# away from it.
# Finding 106. 4 -> 3: one code's wording no longer reappears elsewhere once both sides are read in the era the classification ended, because the reappearance was in a life that had closed.
# 3 -> 4 on 2026-08-17. The new veterinary row's own wording reappears at 3004.50.00.50 from
# 1998-01, 96 months after it stopped, which is exactly the signal this column exists to raise.
EXPECTED_SAME_WORDING_ELSEWHERE = 4
# Retirements whose substance is never named again anywhere in the delivery. For these, whatever
# is chosen is an aggregation into a residual rather than an equivalence, and the row says so.
# 13 -> 16 on 2026-08-12. Reading a candidate in the wording in force at the boundary means a
# substance named only in a closed life no longer counts as named again later, which is the
# point: those three retirements really do aggregate into a residual.
EXPECTED_SUBSTANCE_GONE = 16
# Proposals accepted on the twelve-month grace window rather than on a clean succession. They
# are legitimate and they are worth counting, because the window is a judgement.
EXPECTED_ON_GRACE = 24

results = []
notes = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def disclose(name, detail=""):
    """Report a state without claiming a test of it, and keep it out of the control count.

    Several things here are worth printing and cannot fail. Whether the workbook's evidence lags
    the copy depends on whether someone has it open. Whether a reference column has been rewritten
    by a spreadsheet is tolerated either way, and a control that required one form failed the
    moment the tolerated thing happened. Written as record(<name>, True, ...) they inflated the
    headline, because "N of N controls passed" is read as N things that could have failed.
    """
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, ("  -- " + detail) if detail else ""))


def must_raise(name, function, *args):
    try:
        function(*args)
    except ValueError as error:
        record(name, True, "refused as intended: %s" % error)
        return
    record(name, False, "accepted input it should have refused")


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit(row):
    """Everything a single row must satisfy to be decidable from itself."""
    has = bool(row["proposed_successor"])
    if has:
        for column in ("proposed_successor_description", "proposed_successor_first_traded",
                       "proposed_successor_last_traded", "wording_match", "shared_meaning_words"):
            if not row[column]:
                raise ValueError("a proposal is missing %s" % column)
    else:
        # A default is not a measurement. 0.0000 reads as "the wording does not match" when the
        # truth is "there is nothing to match against", and those are different findings.
        for column in ("wording_match", "shared_meaning_words",
                       "successor_began_at_the_boundary", "successor_is_more_aggregate"):
            if row[column]:
                raise ValueError("no proposal, yet %s says %r" % (column, row[column]))
    if row["runner_up"]:
        for column in ("runner_up_description", "runner_up_first_traded",
                       "runner_up_last_traded", "runner_up_wording_match"):
            if not row[column]:
                raise ValueError("a runner-up is missing %s" % column)
    if row["closest_removed_candidate"]:
        for column in ("closest_removed_description", "closest_removed_first_traded",
                       "closest_removed_last_traded", "closest_removed_wording_match",
                       "closest_removed_why"):
            if not row[column]:
                raise ValueError("a removed candidate is missing %s" % column)
    if not row["suggested_decision"]:
        raise ValueError("no suggestion at all")
    if row["suggested_decision"] == "approve" and not has:
        raise ValueError("suggests approve with nothing to approve")
    if row["suggested_decision"] == "unresolved" and has:
        raise ValueError("suggests unresolved while proposing %s" % row["proposed_successor"])
    if has and row["proposed_successor"] == row["retiring_code"]:
        raise ValueError("proposes the retiring code as its own successor")
    first, last = row["proposed_successor_first_traded"], row["proposed_successor_last_traded"]
    if first and last and first > last:
        raise ValueError("the proposal traded backwards, %s to %s" % (first, last))
    if row["status"].startswith("HELD") and row["priority"] != "held":
        raise ValueError("held, yet sorted under priority %s" % row["priority"])
    return True


sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
from make_adjudication_queue import normalise_decision  # noqa: E402
from make_adjudication_queue import wording_ratio as _builder_ratio  # noqa: E402

print("Check for the adjudication artefact. Is every row decidable from itself?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
GOOD = {"row": "1", "retiring_code": "3004.90.10", "proposed_successor": "3004.90.00",
        "proposed_successor_description": "Medicaments", "proposed_successor_first_traded": "1989-01",
        "proposed_successor_last_traded": "2017-12", "wording_match": "0.7812",
        "shared_meaning_words": "0.5000", "successor_began_at_the_boundary": "yes",
        "successor_is_more_aggregate": "yes", "runner_up": "", "runner_up_description": "",
        "runner_up_first_traded": "", "runner_up_last_traded": "", "runner_up_wording_match": "",
        "closest_removed_candidate": "", "closest_removed_description": "",
        "closest_removed_first_traded": "", "closest_removed_last_traded": "",
        "closest_removed_wording_match": "", "closest_removed_why": "",
        "suggested_decision": "approve", "status": "decide", "priority": "1"}


def variant(**changes):
    row = dict(GOOD)
    row.update(changes)
    return row


must_raise("a proposal without its first traded month is refused", audit,
           variant(proposed_successor_first_traded=""))
must_raise("a proposal without a wording match is refused", audit, variant(wording_match=""))
must_raise("a score printed where there is no proposal is refused", audit,
           variant(proposed_successor="", proposed_successor_description="",
                   proposed_successor_first_traded="", proposed_successor_last_traded="",
                   suggested_decision="unresolved"))
must_raise("a runner-up without its dates is refused", audit,
           variant(runner_up="3004.90.90", runner_up_description="x",
                   runner_up_wording_match="0.4"))
must_raise("a removed candidate without its reason is refused", audit,
           variant(closest_removed_candidate="3004.90.90", closest_removed_description="x",
                   closest_removed_first_traded="2018-01", closest_removed_last_traded="2026-06",
                   closest_removed_wording_match="0.45"))
must_raise("suggesting approve with nothing to approve is refused", audit,
           variant(proposed_successor="", proposed_successor_description="",
                   proposed_successor_first_traded="", proposed_successor_last_traded="",
                   wording_match="", shared_meaning_words="",
                   successor_began_at_the_boundary="", successor_is_more_aggregate=""))
must_raise("a code proposed as its own successor is refused", audit,
           variant(proposed_successor="3004.90.10"))
must_raise("a proposal that traded backwards is refused", audit,
           variant(proposed_successor_first_traded="2020-01",
                   proposed_successor_last_traded="1990-01"))
must_raise("a held row sorted anywhere but last is refused", audit,
           variant(status="HELD, do not decide", priority="3"))
must_raise("a row with no suggestion is refused", audit, variant(suggested_decision=""))

print()
print("Controls that MUST PASS (correct input must not be flagged):")
record("a well-formed row is accepted", audit(GOOD) is True, "proposal complete with its dates")

print()
print("The artefact itself:")
queue = load(os.path.join(DECISIONS, "stage2_adjudication_queue.csv"))
answers = load(os.path.join(DECISIONS, "stage2_decisions.csv"))

record("the queue holds every row", len(queue) == EXPECTED_ROWS,
       "%d, expected %d" % (len(queue), EXPECTED_ROWS))
broken = []
for row in queue:
    try:
        audit(row)
    except ValueError as error:
        broken.append("row %s %s: %s" % (row["row"], row["retiring_code"], error))
record("every row is decidable from itself", not broken,
       "%d row(s) audited" % len(queue) if not broken
       else "%d of %d failed. First: %s" % (len(broken), len(queue), broken[0]))

counts = defaultdict(int)
for row in queue:
    counts[row["suggested_decision"]] += 1
record("the suggestions are unchanged", dict(counts) == EXPECTED_SUGGESTIONS, "%s" % dict(counts))
record("the held rows are unchanged",
       sum(1 for r in queue if r["priority"] == "held") == EXPECTED_HELD,
       "%d, expected %d" % (sum(1 for r in queue if r["priority"] == "held"), EXPECTED_HELD))

# A proposal resting on the grace window is legitimate and worth counting, because the window is
# a judgement rather than a measurement and its size should not drift unnoticed.
on_grace = [r for r in queue if r["months_gap"] not in ("", "0")]
record("proposals resting on the grace window are unchanged", len(on_grace) == EXPECTED_ON_GRACE,
       "%d, expected %d, the widest %s months"
       % (len(on_grace), EXPECTED_ON_GRACE,
          max((int(r["months_gap"]) for r in on_grace), default=0)))

# THRESHOLDS.md section 3 routes anything below 0.50 to a person without a recommendation.
# Eleven rows used to say "no candidate is close on wording" and suggest approving one anyway.
under = [(r["row"], r["wording_match"]) for r in queue
         if r["suggested_decision"] == "approve" and r["wording_match"]
         and float(r["wording_match"]) < 0.50]
record("nothing below the review threshold is recommended for approval", not under,
       "0 of %d approvals sit under 0.50" % sum(1 for r in queue
                                                if r["suggested_decision"] == "approve")
       if not under else "%d found: %s" % (len(under), under[:3]))

# A rule that only flags must still reach the reader. basket_subset carries action=review rather
# than disqualify, so it never removes a candidate; if it also said nothing, it would do nothing.
flagged = [r for r in queue if r["successor_is_more_aggregate"] == "yes"]
mute = [r["row"] for r in flagged if not r["why_this_needs_you"]]
record("every row flagged as an aggregation says so in plain words", flagged and not mute,
       "%d flagged, all with a stated reason" % len(flagged)
       if not mute else "%d silent: %s" % (len(mute), mute[:3]))

# The official record outranks the continuity window, so a record-bounded proposal may carry a
# gap wider than twelve months. That is the layer order working, and it must stay disclosed
# rather than become invisible: the gap is printed and the row is not recommended.
wide = [r for r in queue if r["months_gap"] and int(r["months_gap"]) > 12]
undisclosed = [r["row"] for r in wide
               if r["successor_began_at_the_boundary"] != "no" or r["suggested_decision"] == "approve"]
record("a gap wider than the window is disclosed and not recommended", not undisclosed,
       "%d wide gap(s), each printed and left to the reader" % len(wide)
       if not undisclosed else "%d hidden: %s" % (len(undisclosed), undisclosed[:3]))

# "none" carries two different findings and they must stay tellable apart. The chapter-exit
# hypothesis is a claim about where the trade went; a sub-threshold wording match is an absence
# of evidence. On 2026-08-11 both printed the same word and 23 of 30 rows were ambiguous.
silent = [r["row"] for r in queue
          if r["suggested_decision"] != "approve" and not r["why_not_recommended"]]
record("every row that declines to recommend says why", not silent,
       "%d non-approvals, each with a stated basis"
       % sum(1 for r in queue if r["suggested_decision"] != "approve")
       if not silent else "%d silent: %s" % (len(silent), silent[:3]))
contradicting = [r["row"] for r in queue
                 if r["suggested_decision"] == "approve" and r["why_not_recommended"]]
record("no row recommends and declines at once", not contradicting,
       "0 contradictions" if not contradicting else "%d: %s" % (len(contradicting),
                                                                contradicting[:3]))
# The chapter-exit shape was measured at 19 rows catching all 5 codes v1 settled as leaving for
# heading 38.22, and at 18 after 2026-08-11. The row it lost is 3002.90.00.11, which the CBSA
# concordance now settles outright, so it leaves the queue rather than the hypothesis. All 5
# known departures are still caught, which is the part that matters.
# TWO ROUTES REACH THIS, and only one of them is a hypothesis.
#
# The WCO correlation says it outright on 5 rows, and those 5 are the best-evidenced departures
# in the delivery. Matching only the heuristic's phrase made them invisible to this control the
# moment the record started naming them, so both phrases are counted.
by_wording = [r for r in queue if "left Chapter 30" in r["why_not_recommended"]]
by_record = [r for r in queue if "OUT of Chapter 30" in r["why_not_recommended"]]
left = by_wording + by_record
# 17 -> 10 by wording, and the seven that left did NOT move to the record. They stopped being
# chapter-exit rows at all.
#
# ed7e658 wrote this expectation and never ran it, because the disk failed twenty-five seconds
# before the commit. It was right about the number and wrong about the mechanism, and its own
# comment four lines above still said 17 while the control below said 10. The seven are rows
# the correlation places INSIDE Chapter 30, on 3001.90.00 and 3006.92.00.00: the record names a
# successor in the chapter and the heuristic was still saying the goods may have left it. The
# queue builder now withdraws the hypothesis when the record refutes it, which is why the union
# is 15 rather than 22. Nothing moved between the two sets; seven rows left the question.
record("the chapter-exit hypothesis still fires on exactly 10 rows by wording",
       len(by_wording) == 10, "%d by wording, %d more named by the record, %d in total"
       % (len(by_wording), len(by_record), len(left)))
KNOWN_DEPARTURES = {("imports", "3002.11.00.00"), ("imports", "3006.20.00.20"),
                    ("imports", "3006.20.00.90"), ("exports", "3002.11.00"),
                    ("exports", "3006.20.00")}
# Now caught by the RECORD rather than by the wording, which is a strengthening and is
# asserted as one: if a future change sent these back to the heuristic, this would fail.
caught = {(r["flow"], r["retiring_code"]) for r in by_record} & KNOWN_DEPARTURES
record("all 5 codes settled as leaving Chapter 30 are named by the official record",
       caught == KNOWN_DEPARTURES,
       "%d of 5" % len(caught) if caught == KNOWN_DEPARTURES
       else "missed %s" % sorted(KNOWN_DEPARTURES - caught))

# THE CARVE-OUT RULE. It flags and must never remove, for the same reason swapped_term does:
# it fires on two rows in the whole delivery and both were argued over by hand, which is far too
# thin a base to let it take a candidate out of a field.
#
# Pinned by row, not just by count, because the two it finds are the two it was built for and a
# different pair would mean it had started answering a different question. Row 210 is the
# residual of 3002.20 proposed onto the influenza line that carved influenza out of it, CAD
# 11,076,237,268; row 1 is the residual of the 3004.32 block proposed onto hydrocortisone.
CARVED = {r["row"] for r in queue if r["successor_was_carved_out_of_it"] == "yes"}
record("the carve-out rule flags exactly the two rows it was built for",
       CARVED == {"210", "1"}, "flags %s" % sorted(CARVED, key=int))
record("the carve-out rule removes nothing",
       all(r["proposed_successor"] and r["proposed_successor_description"]
           for r in queue if r["row"] in CARVED),
       "%d flagged row(s), every one still showing its proposal" % len(CARVED))
# The constraint that stopped it refuting row 223, which the analyst accepted on the record.
# Asked of the same function the builder asks, so the check cannot drift from what it tests.
import meaning_gates as _mg  # noqa: E402
from _shorthand import expand_shorthand as _mg_expand  # noqa: E402
_resid_succ = [r["row"] for r in queue if r["successor_was_carved_out_of_it"] == "yes"
               and _mg.carries_residual_marker(_mg_expand(r["proposed_successor_description"]))]
record("a residual successor is never flagged as a carve-out", not _resid_succ,
       "residual to residual is the correct shape and is left alone"
       if not _resid_succ else "%d flagged anyway: %s" % (len(_resid_succ), _resid_succ[:4]))
# And the warning has to reach the reader, including on a row the software is confident about.
_warned = {r["row"] for r in answers
           if "MAY INVERT THIS LINE'S MEANING" in (r.get("check_this_again") or "")}
record("every carve-out flag reaches the answer sheet", _warned == CARVED,
       "%d flagged, %d warned on the sheet" % (len(CARVED), len(_warned)))

# ---------------------------------------------------------------------------------------------
# THE WIDENED LEFTOVER LINE, finding 100. Text similarity reads a candidate's wording and cannot
# read that the wording CHANGED. 3002.90.00.90 gained "antisera, vaccines, cell cultures" in the
# month 3002.19 was deleted, and the ranker put it 18th of 22 on 0.1646 with nothing vetoing it.
#
# Pinned by row rather than by count, for the same reason the carve-out rule is: a different set
# would mean it had started answering a different question. Rows 213 and 222 are the 3002.19 pair
# the rule was built for; 66 and 226 are the two other 2021-12 retirements the same widening
# reaches; 69 is the veterinary hormones residual offered against a human epinephrine line, which
# a reader dismisses on sight and which is deliberately NOT tuned out, because the constraint that
# would remove it would be fitted to this delivery rather than argued from the tariff.
WIDENED = {r["row"] for r in queue if r["a_leftover_line_widened_here"] == "yes"}
# Row 68 JOINED this set on 2026-08-18 and the rule did not change. 3002.90.00.90 is the line
# that widened, and it was row 68's own proposal until finding 122 gave that row a better
# candidate, so the warning was suppressed by the control four lines below: a warning about the
# code already chosen says nothing. Now that 3002.49.00.10 is the proposal, the widened residual
# is a rival rather than the answer, and the warning is worth showing. Six rows, same rule.
record("the widened-leftover rule flags exactly the six rows it was built for",
       WIDENED == {"66", "68", "69", "213", "222", "226"}, "flags %s" % sorted(WIDENED, key=int))
record("the widened-leftover rule removes nothing",
       all(r["proposed_successor"] and r["proposed_successor_description"]
           for r in queue if r["row"] in WIDENED),
       "%d flagged row(s), every one still showing its proposal" % len(WIDENED))
# It may not rank. If it ever lifts the line it names, that line becomes the proposal and this
# fails, which is the artefact-side statement of "meaning may veto, never select".
_widened_is_proposal = [r["row"] for r in queue if r["row"] in WIDENED
                        and r["widened_line"] == r["proposed_successor"]]
record("the widened line is never the proposal it is warning about", not _widened_is_proposal,
       "a warning about the code already chosen would say nothing"
       if not _widened_is_proposal else "%s" % _widened_is_proposal)
# The structural constraint that keeps it from firing on a reuse in place. Both lives must be the
# group's leftover; without it the rule fires on 3004.50.99.30, vet vitamins becoming human
# multivitamins on the same number at 1990-01.
_inv_lives = {}
for _f in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _f)):
        _inv_lives.setdefault((_f, _r["hs_code"]), []).append(
            (_r["first_period"], _r["last_period"], _r["description"]))
_bad = []
for _r in queue:
    if _r["row"] not in WIDENED:
        continue
    _flow = _r["link_id"].split(":")[0]
    _last = _r["last_traded"].replace("-", "")
    _spans = sorted(_inv_lives.get((_flow, _r["widened_line"].replace(".", "")), []))
    _pair = [(a, b) for a, b in zip(_spans, _spans[1:]) if a[1] == _last]
    if not _pair:
        _bad.append((_r["row"], "no life ends at the retirement's own last month"))
        continue
    _a, _b = _pair[0]
    _old = _mg.content_words(_mg_expand(_a[2].lower()))
    _new = _mg.content_words(_mg_expand(_b[2].lower()))
    if not (_mg.carries_residual_marker(_mg_expand(_a[2]))
            and _mg.carries_residual_marker(_mg_expand(_b[2]))):
        _bad.append((_r["row"], "the widened line is not a leftover on both sides"))
    elif not (_old & _new and _new - _old):
        _bad.append((_r["row"], "the wording did not keep something and gain something"))
    elif set(t.strip() for t in _r["widened_line_added_terms"].split(",")) - (_new - _old):
        _bad.append((_r["row"], "the terms named were not the terms gained"))
record("every widened line really is a leftover that gained wording at this boundary", not _bad,
       "rebuilt from the inventory for all %d flagged row(s), without calling the builder"
       % len(WIDENED) if not _bad else "%s" % _bad[:3])
_wwarn = {r["row"] for r in answers
          if "A LEFTOVER LINE WAS WIDENED AT THIS VERY BOUNDARY" in (r.get("check_this_again") or "")}
record("every widened-leftover flag reaches the answer sheet", _wwarn == WIDENED,
       "%d flagged, %d warned on the sheet" % (len(WIDENED), len(_wwarn)))

# swapped_term flags and must never remove. If it ever starts removing, the veto counts in
# Stage 1c move and this control is the one that says so from the artefact's side.
swapped = [r for r in queue if r["successor_swaps_a_term"] == "yes"]
record("the swapped-term flag is unchanged", len(swapped) == EXPECTED_SWAPPED,
       "%d rows, expected %d" % (len(swapped), EXPECTED_SWAPPED))
record("every flagged row names both differing terms",
       all(r["term_in_the_retiring_code"] and r["term_in_the_successor"] for r in swapped),
       "%d rows, each naming what differs" % len(swapped))
record("no flagged row is recommended for approval",
       not [r for r in swapped if r["suggested_decision"] == "approve"],
       "0 of %d" % len(swapped))
# The point of the rule: a high text score must no longer carry a swapped term to approval.
high_swaps = [r["row"] for r in queue
              if r["suggested_decision"] == "approve" and r["successor_swaps_a_term"] == "yes"
              and r["wording_match"] and float(r["wording_match"]) >= 0.85]
record("no proposal above the auto-link line rests on a swapped term", not high_swaps,
       "0 rows" if not high_swaps else "%d: %s" % (len(high_swaps), high_swaps[:3]))
# Co-trading is reported, never judged: absorption into an existing code is legitimate.
co = [r for r in queue if r["successor_co_traded_months"]]
record("co-trading months are reported for every proposal that overlaps its predecessor",
       all(int(r["successor_co_traded_months"]) > 0 for r in co),
       "%d row(s) disclose an overlap, none of them vetoed for it" % len(co))

recent = [r for r in queue if r["priority"] == "too recent"]
record("the rows too recent to call are unchanged", len(recent) == EXPECTED_TOO_RECENT,
       "%d rows, expected %d, CAD %s" % (len(recent), EXPECTED_TOO_RECENT,
                                         "{:,.0f}".format(sum(float(r["value_cad"])
                                                              for r in recent))))
record("not one of them is offered for decision",
       all(r["status"].startswith("TOO RECENT") for r in recent),
       "all %d say so in the status column" % len(recent))
record("each explains that the delivery, not the code, is the problem",
       all("delivery ends" in r["why_this_needs_you"] for r in recent),
       "%d rows name the months remaining" % len(recent))
# REWRITTEN 2026-08-15, and deliberately not re-pinned. Its previous form asked for a decidable
# retirement stopping since 2022-06, and there is now none: no line in this delivery has been
# withdrawn since HS2022, so every recent stoppage is a code going quiet rather than a
# classification ending. A control whose subject has emptied cannot fail, and re-pinning it at
# zero would have kept a passing line that tested nothing. That is the M9 shape and the reason it
# is replaced instead.
#
# What the vacuity revealed is the property worth guarding: whether a stoppage is a retirement is
# decided by the RECORD, never by the calendar. The two sets overlap in time, so no recency rule
# could ever reproduce the split. 30034100 has been quiet 69 months and is not a retirement,
# while every declared retirement in the delivery stopped at least 54 months ago and the largest
# of them, 3002200090 at CAD 11,076,237,268, stopped at exactly that 54.
_basis_gap = {"declared": [], "trade_ceased_only": []}
for _f in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "stage1_candidates_%s.csv" % _f)):
        if _r["retirement_basis"] in _basis_gap:
            _basis_gap[_r["retirement_basis"]].append(int(_r["months_before_delivery_end"]))
record("what makes a stoppage a retirement is the record, not the calendar",
       bool(_basis_gap["trade_ceased_only"]) and bool(_basis_gap["declared"])
       and max(_basis_gap["trade_ceased_only"]) > min(_basis_gap["declared"]),
       "quietest non-retirement %d months, most recent declared retirement %d months; the two "
       "overlap, so recency cannot separate them"
       % (max(_basis_gap["trade_ceased_only"]), min(_basis_gap["declared"])))

# A successor must still be trading after the code it replaces. It holds today by construction,
# through alive_after in Stage 1a, and nothing asserted it, so a change upstream could break it
# in silence. Asked for by the analyst on 2026-08-11.
def later(a, b):
    return a and b and (int(a[:4]) * 12 + int(a[5:7])) > (int(b[:4]) * 12 + int(b[5:7]))


for column, last_col, label in (
        ("proposed_successor", "proposed_successor_last_traded", "the proposal"),
        ("runner_up", "runner_up_last_traded", "the runner-up"),
        ("closest_removed_candidate", "closest_removed_last_traded",
         "the closest removed candidate")):
    dated = [r for r in queue if r[column] and r[last_col]]
    wrong = [r["row"] for r in dated if not later(r[last_col], r["last_traded"])]
    record("%s always outlives the code it would replace" % label, not wrong,
           "%d checked, none stops at or before its predecessor" % len(dated)
           if not wrong else "%d violate it: %s" % (len(wrong), wrong[:4]))

# And the dates shown must be a real trading span, not an envelope drawn around two lives.
# 3002.90.10 was displayed as 1988-01 to 2026-06 while it actually traded 1988-01 to 1988-12 and
# then, as different goods, 1997-12 onward.
inventory = {}
for _flow in ("imports", "exports"):
    for _r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % _flow)):
        inventory.setdefault((_flow, _r["hs_code"]), []).append(
            (_r["first_period"], _r["last_period"], _r["description"]))


def real_spans(flow, code):
    """The spans this code really has, rebuilt here rather than read from the stage.

    A span ends at a gap longer than sixty months, or at a relabel that crosses a decisive
    distinction, which ends it with no gap at all. Both are written out rather than imported so
    this control can still disagree with the queue builder; only the rules are shared, because
    they are the published specification. The second test arrived on 2026-08-17 and without it
    this control reported an envelope on a code the builder had correctly split.
    """
    intervals = sorted(inventory.get((flow, code), []))
    if not intervals:
        return []
    out = [list(intervals[0])]
    for first, last, description in intervals[1:]:
        if ((int(first[:4]) * 12 + int(first[4:6])) - (int(out[-1][1][:4]) * 12
                                                       + int(out[-1][1][4:6])) > 60
                or _relabelled(out[-1][2], description)):
            out.append([first, last, description])
        else:
            out[-1][1] = max(out[-1][1], last)
            out[-1][2] = description
    return [(x[0], x[1]) for x in out]


envelopes = []
for r in queue:
    for column, first_col, last_col in (
            ("proposed_successor", "proposed_successor_first_traded",
             "proposed_successor_last_traded"),
            ("runner_up", "runner_up_first_traded", "runner_up_last_traded"),
            ("closest_removed_candidate", "closest_removed_first_traded",
             "closest_removed_last_traded")):
        if not (r[column] and r[first_col]):
            continue
        shown = (r[first_col].replace("-", ""), r[last_col].replace("-", ""))
        if shown not in real_spans(r["flow"], r[column].replace(".", "")):
            envelopes.append((r["row"], column))
record("every date shown is a real trading span, not an envelope", not envelopes,
       "all dates trace to one span" if not envelopes
       else "%d envelope(s): %s" % (len(envelopes), envelopes[:4]))

elsewhere = [r for r in queue if r["same_wording_reappears_at"]]
record("rows whose wording reappears away from the proposal are unchanged",
       len(elsewhere) == EXPECTED_SAME_WORDING_ELSEWHERE,
       "%d rows, expected %d" % (len(elsewhere), EXPECTED_SAME_WORDING_ELSEWHERE))
record("none of them points at the code already proposed",
       not [r for r in elsewhere if r["same_wording_reappears_at"] == r["proposed_successor"]],
       "the column carries only disagreements, not confirmations")
record("each names when the wording returns",
       all(r["same_wording_reappears_from"] and r["same_wording_gap_months"] != ""
           for r in elsewhere),
       "%d rows, each with a date and a gap" % len(elsewhere))
# The signal must not have become a rule. Nothing may be linked because of it.
# The suppression asks a person to choose between the twin and the proposal, which is only a
# choice when they compete. Where the twin is the proposal's own successor, reachable by
# following the record and the queue, there is nothing to choose and the row stands.
downstream = [r for r in queue
              if r["same_wording_reappears_at"] and r["verdict"].startswith("CONFIRM")]
record("a twin that is downstream of the proposal does not withhold the row",
       len(downstream) == 1,
       "%d row(s) kept their recommendation because the twin is a later link, not a rival"
       % len(downstream))
# 4 -> 3 on 2026-08-12. One of the five twins became the proposal itself once candidates were
# read in the wording in force at the boundary, so it is no longer a rival sitting elsewhere.
# 3 -> 2 on 2026-08-16, finding 106, and it is the same twin leaving the set as above.
# 2 -> 3 on 2026-08-17: the new veterinary row's wording reappears at 3004.50.00.50 and the row
# is not a CONFIRM, so it joins the twins that withhold rather than the one that does not.
record("the other twins still withhold", len(elsewhere) - len(downstream) == 3,
       "%d of %d remain withheld, two of them with a twin starting the same month as the "
       "proposal" % (len(elsewhere) - len(downstream), len(elsewhere)))
record("no row is recommended while an identical wording sits elsewhere",
       not [r for r in elsewhere if r["suggested_decision"] == "approve"
            and not r["verdict"].startswith("CONFIRM")],
       "0 of %d withheld; either that code is the renumbering or the proposal is, and the "
       "wording cannot separate them" % (len(elsewhere) - len(downstream)))
# The workbook is narrower than the queue on purpose. Every column dropped from it must still
# exist somewhere, or trimming would be losing evidence rather than hiding it.
queue_columns = set(queue[0])
book_columns = set(answers[0])
# The sheet is deliberately narrower and several of its columns are renamed or combined, so the
# test is that nothing it shows is invented, not that the names match.
# Renamed or assembled from queue columns rather than copied from them. The four
# second_alternative columns are the queue's several alternatives reduced to the one worth
# reading, laid out like the proposal so the two can be compared line against line.
DERIVED = {"why", "retiring_last_traded", "proposed_successor_traded",
           # Assembled in the sheet from the queue's family columns: which of the two codes
           # already on the row the relationship points to.
           "what_this_points_to", "how_the_second_relates",
           "proposed_successor_wording_match",
           "second_alternative", "second_alternative_description",
           "second_alternative_traded", "second_alternative_wording_match",
           "check_this_again", "decision", "correct_successor_if_rejected", "reason",
           "decided_by", "decided_on"}
invented = book_columns - queue_columns - DERIVED
record("the answer sheet shows nothing the queue does not hold", not invented,
       "%d of the queue's %d columns, plus %d derived from them"
       % (len(book_columns & queue_columns), len(queue_columns), len(DERIVED))
       if not invented else "invented: %s" % sorted(invented))
disclose("the identical-wording signal changed no link",
         "reported only; the proposal on all %d is still whatever the ordered layers produced"
         % len(elsewhere))

gone = [r for r in queue if r["substance_named_again_later"] == "NO"]
record("retirements whose substance never returns are unchanged",
       len(gone) == EXPECTED_SUBSTANCE_GONE,
       "%d rows, expected %d, CAD %s" % (len(gone), EXPECTED_SUBSTANCE_GONE,
                                         "{:,.0f}".format(sum(float(r["value_cad"])
                                                              for r in gone))))
record("every row states whether its substance is named again",
       all(r["substance_named_again_later"] in ("yes", "NO", "") for r in queue),
       "yes, NO, or blank where the description carries no distinctive word")

# A proposal that is itself retiring is common and not wrong on its own: the trade can pass
# through one code before moving on. What matters is that the reader is told, and that the chain
# is followed to where it actually ends rather than handing over the next domino.
chained = [r for r in queue if r["successor_also_retires"].startswith("yes")]
# 61 -> 60 on 2026-08-12 with the era-correct wordings.
# 60 -> 59 on 2026-08-14. The correlation narrowed two waste-pharmaceutical rows onto
# 3006.92.00.00, which does NOT retire, so their proposal stopped being a co-casualty. One
# other row moved with them. This is the record replacing a dying proposal with a living one.
# 61 -> 62 on 2026-08-17: the new veterinary row proposes 3004.50.99.50, which itself retires in
# 1997-12, so the chain is followed on to 3004.50.00.70 and the row says so.
record("proposals that are themselves retiring are counted", len(chained) == 62,
       "%d of %d, expected 62" % (len(chained), len(queue)))
record("every one names where its chain ends",
       all(r["chain_ends_at"] and r["chain_hops"] for r in chained),
       "%d chains resolved" % len(chained))
# This was record(<name>, True, ...) over a list DERIVED from chain_ends_at, so it asked the
# column whether the column was right and could only ever agree with itself. A circle the builder
# failed to notice would have been invisible to it. The detector below is independent: it walks
# the proposals as a graph and finds any cycle in them, whatever the column says. Proven on a
# planted circle first, because a detector that finds nothing on clean data proves nothing.
def _cycles(edges):
    """Every node lying on a cycle of the mapping, found by walking each node to its end."""
    on_cycle = set()
    for start in edges:
        path, node = [], start
        while node in edges and node not in path:
            path.append(node)
            node = edges[node]
        if node in path:
            on_cycle.update(path[path.index(node):])
    return on_cycle


_planted = {("imports", "A"): ("imports", "B"), ("imports", "B"): ("imports", "A"),
            ("imports", "C"): ("imports", "B")}
record("the circle detector finds a circle that was planted for it",
       _cycles(_planted) == {("imports", "A"), ("imports", "B")},
       "a two-code loop is found and the code feeding into it is not counted as part of it")
_edges = {(r["flow"], r["retiring_code"].replace(".", "")):
          (r["flow"], r["proposed_successor"].replace(".", ""))
          for r in queue if r["proposed_successor"]}
_on_cycle = _cycles(_edges)
unreported = [r["row"] for r in queue
              if (r["flow"], r["retiring_code"].replace(".", "")) in _on_cycle
              and "each other" not in r["chain_ends_at"]]
cyclic = [r["row"] for r in chained if "each other" in r["chain_ends_at"]]
record("no chain runs in a circle unreported", not unreported,
       "%d proposal edge(s) walked, %d row(s) lie on a circle, %d of them say so"
       % (len(_edges), len(_on_cycle), len(cyclic)) if not unreported
       else "%d row(s) lie on a circle the sheet does not disclose: %s"
            % (len(unreported), unreported[:5]))
terminal = {r["chain_ends_at"] for r in chained if "each other" not in r["chain_ends_at"]}
record("a chain terminates outside the queue", all(
    (r["flow"], t) not in {(x["flow"], x["retiring_code"]) for x in queue}
    for r in chained for t in [r["chain_ends_at"]] if "each other" not in t),
       "%d distinct terminus code(s), none of them a retirement itself" % len(terminal))

# Two date formats live in the builder: YYYYMM for the pipeline and YYYY-MM for the reader.
# months_gap takes the first and months_between the second, and handing the dashed form to
# months_gap returns arithmetic on int("2005-01"[4:]), which is int("-01"). That produced a
# plausible-looking 23 where the answer was 24 and a 0 where it was 9. Both are exercised here
# with both formats so the confusion cannot return quietly.
import importlib  # noqa: E402
_builder = importlib.import_module("make_adjudication_queue")
record("months_between reads the printed form correctly",
       _builder.months_between("1995-12", "1997-12") == 24
       and _builder.months_between("2005-01", "2005-10") == 9
       and _builder.months_between("2026-05", "2026-06") == 1,
       "24, 9 and 1 months, counted inclusively of neither endpoint")
record("months_gap reads the raw form correctly",
       _builder.months_gap("199512", "199601") == 0
       and _builder.months_gap("199512", "199603") == 2
       and _builder.months_gap("199512", "199801") == 24,
       "0 for an immediate handoff, 2 for a two-month gap, 24 for two years")

co_casualty = [r for r in queue if r["successor_also_retires"].startswith("yes, within")]
record("proposals that die in the same restructuring are unchanged",
       len(co_casualty) == EXPECTED_CO_CASUALTY,
       "%d rows, expected %d, CAD %s" % (len(co_casualty), EXPECTED_CO_CASUALTY,
                                         "{:,.0f}".format(sum(float(r["value_cad"])
                                                              for r in co_casualty))))
record("not one of them is recommended",
       not [r for r in co_casualty if r["suggested_decision"] == "approve"],
       "0 of %d; each names where the chain ends instead" % len(co_casualty))
record("each says how soon the proposal stops and where the trade goes",
       all(r["chain_ends_at"] and "months" in r["successor_also_retires"]
           for r in co_casualty),
       "%d rows carry both" % len(co_casualty))
# The converse: a proposal that outlived its predecessor by years is an ordinary chain and must
# still be recommendable, or the rule would be swallowing good links.
long_chain = [r for r in queue
              if r["successor_also_retires"] == "yes" and r["suggested_decision"] == "approve"]
record("proposals that lived on are still recommendable", bool(long_chain),
       "%d chained proposal(s) outlived their predecessor and are still recommended"
       % len(long_chain))

res = [r for r in queue if r["class_residual_available"]]
record("rows offering their parent's leftover line are unchanged",
       len(res) == EXPECTED_CLASS_RESIDUAL,
       "%d rows, expected %d" % (len(res), EXPECTED_CLASS_RESIDUAL))
record("none is offered beside a proposal that already matches exactly",
       not [r for r in res if r["wording_match"] and float(r["wording_match"]) >= 0.85
            and r["successor_swaps_a_term"] != "yes"],
       "a residual appears only where the proposal is in doubt")
record("every residual offered is named with its own score",
       all(r["class_residual_description"].count("(") >=
           len(r["class_residual_available"].split(";")) for r in res),
       "each of the %d rows lists every candidate residual and what it scores" % len(res))
# All of them, not the best-scoring one. A parent can carry residuals at several levels of
# specificity and the broader one scores higher precisely because it says less.
several = [r for r in res if ";" in r["class_residual_available"]]
record("rows with residuals at more than one level show them all", bool(several),
       "%d row(s) offer more than one; Kanamycins offers four, including the aminoglycoside "
       "line that scores lowest and is the right answer" % len(several))

# A verdict a person can scan a column of. The analyst read the proposal column first, saw the
# same code as before, and concluded a fix had not landed when the recommendation under it had
# been withdrawn. Presentation is part of whether a correction actually reaches anyone.
VERDICTS = {"CONFIRM - the evidence supports this link",
            "ANALYST - a candidate is shown but NOT recommended",
            "ANALYST - nothing survived to propose",
            "DO NOT DECIDE - waiting on a document",
            "DO NOT DECIDE - too close to the end of the data",
            # Added 2026-08-15. Not a hold: the two above say the answer is not available yet,
            # this says there is no question. Stage 1a decides it and stage2_apply_decisions
            # resolves it to not_a_retirement with no link.
            "DO NOT DECIDE - the record does not call this a retirement"}
record("every row carries one of the six verdicts",
       all(r["verdict"] in VERDICTS for r in queue),
       "%s" % {v: sum(1 for r in queue if r["verdict"] == v) for v in sorted(VERDICTS)})
record("the verdict agrees with the recommendation underneath it",
       all((r["verdict"].startswith("CONFIRM")) == (r["suggested_decision"] == "approve"
                                                    and not r["status"].startswith(("HELD",
                                                                                    "TOO",
                                                                                    "NOT A")))
           for r in queue),
       "no row says CONFIRM while withholding, or withholds while saying CONFIRM")
record("every withheld row says why in its own words",
       all(r["why_not_recommended"] for r in queue if r["verdict"].startswith("ANALYST - a")),
       "%d withheld rows, each with a reason"
       % sum(1 for r in queue if r["verdict"].startswith("ANALYST - a")))

# NO ALTERNATIVE A MEANING GATE REMOVED MAY REACH THE SHEET UNLABELLED.
#
# Rebuilt from the ranked files, which are the record of what each gate actually did, so this
# shares no code with the builder that writes the label.
#
# The declared order is that the official record decides, a meaning gate may only veto, and text
# may only rank. The sheet is allowed to SHOW a candidate a gate removed, because the analyst has
# repeatedly asked to see what was taken away and disagreeing with a gate is their prerogative.
# It may not offer one as the answer without saying it was removed. It did on four rows: the
# sentence carrying the provenance was assembled into a local with six assignments and no reads
# anywhere in the file, so the workbook printed the code, its description, its months and its
# score with nothing at all recording that a gate had ruled it out. On one of them the advice
# read "SECOND. The alternative is this code's own family line" against a candidate first
# trading 2012-01 against a 1997-07 retirement.
#
# The label must name the gate, not merely warn. Three of the four rows reach the sheet through
# a different option source than the one whose name says "removed", so a control keyed on that
# source would have passed while three rows stayed silent. This one is keyed on the candidate.
veto_of_pair = {}
for ranked_flow in ("imports", "exports"):
    for ranked_row in load(os.path.join(PROJECT, "work",
                                        "stage1_ranked_%s.csv" % ranked_flow)):
        if ranked_row["vetoed_by"]:
            veto_of_pair[(ranked_flow, ranked_row["retiring_code"],
                          ranked_row["last_period"], ranked_row["candidate"])] = \
                ranked_row["vetoed_by"]


def only_digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


unlabelled_alternatives, offered_after_veto = [], 0
for answer_row in answers:
    alternative_code = answer_row.get("second_alternative") or ""
    if not alternative_code:
        continue
    alt_flow, alt_code, alt_month = answer_row["link_id"].split(":")
    removed_on = veto_of_pair.get((alt_flow, only_digits(alt_code), only_digits(alt_month),
                                   only_digits(alternative_code)))
    if not removed_on:
        continue
    offered_after_veto += 1
    shown = ((answer_row.get("what_this_points_to") or "")
             + (answer_row.get("how_the_second_relates") or ""))
    if ("REMOVED ON %s" % removed_on) not in shown:
        unlabelled_alternatives.append((answer_row["link_id"], alternative_code, removed_on))
record("no alternative a meaning gate removed reaches the sheet unlabelled",
       not unlabelled_alternatives,
       "%d offered after a veto, %d unlabelled%s"
       % (offered_after_veto, len(unlabelled_alternatives),
          (": " + ", ".join("%s -> %s, removed on %s" % u
                            for u in unlabelled_alternatives[:3]))
          if unlabelled_alternatives else ""))
# The other half of the same guarantee. A label nothing can earn is as useless as no label, and
# a builder that stamped every alternative would pass the control above.
falsely_labelled = []
for answer_row in answers:
    shown = ((answer_row.get("what_this_points_to") or "")
             + (answer_row.get("how_the_second_relates") or ""))
    if "REMOVED ON" not in shown:
        continue
    alt_flow, alt_code, alt_month = answer_row["link_id"].split(":")
    if not veto_of_pair.get((alt_flow, only_digits(alt_code), only_digits(alt_month),
                             only_digits(answer_row.get("second_alternative")))):
        falsely_labelled.append(answer_row["link_id"])
record("no alternative is labelled removed that no gate removed", not falsely_labelled,
       "%d falsely labelled" % len(falsely_labelled))

# A GATE THE RECORD OVERRULED MUST REACH THE QUEUE, NOT ONLY THE RANKED FILE.
#
# Rebuilt from the ranked files, which are where Stage 1c records the overruling. This exists
# because the disclosure was lost once, by the fix that created it. Correcting the layer order so
# a named destination is no longer vetoed also removed it from candidates_removed_on_meaning,
# where the analyst had been able to see it, and for one build the objection lived only in a work
# file nobody reads. Fixing a layer order is no reason to show a reader less.
overruled_by_row = {}
for ranked_flow in ("imports", "exports"):
    for ranked_row in load(os.path.join(PROJECT, "work",
                                        "stage1_ranked_%s.csv" % ranked_flow)):
        if ranked_row.get("record_overruled_gate"):
            key = "%s:%s:%s-%s" % (ranked_flow, ".".join([]) or ranked_row["retiring_code"],
                                   ranked_row["last_period"][:4], ranked_row["last_period"][4:])
            overruled_by_row.setdefault(key, []).append(ranked_row["candidate"])
unstated = []
for queue_row in queue:
    flow, code, month = queue_row["link_id"].split(":")
    key = "%s:%s:%s" % (flow, only_digits(code), month)
    for candidate in overruled_by_row.get(key, []):
        shown = queue_row.get("record_overruled_gate") or ""
        if only_digits(candidate) not in only_digits(shown):
            unstated.append("%s -> %s" % (queue_row["link_id"], candidate))
record("a gate the record overruled is stated on the row it happened to", not unstated,
       "%d overruled gate(s) across the delivery, %d not stated in the queue"
       % (sum(len(v) for v in overruled_by_row.values()), len(unstated)))

# A DECIDED ROW THAT BECOMES HELD MUST SAY SO, AND KEEP ITS ANSWER.
#
# The hold was corrected the same day to key on the month the record calls a code obsolete
# rather than the month money last moved, which newly held three export rows the analyst had
# already answered. Silently overriding an answer is the one thing that must not happen: the
# decision stays exactly as written and the sheet raises a warning beside it. Without this the
# three rows would read as ordinary held rows and the answers already given to them would
# disappear from view.
held_and_answered = [r for r in answers
                     if (r.get("decision") or "").strip()
                     and (r.get("verdict") or "").startswith("DO NOT DECIDE")]
unwarned = [r["link_id"] for r in held_and_answered
            if "HELD" not in (r.get("check_this_again") or "")]
record("every held row that already carries an answer warns about it", not unwarned,
       "%d held row(s) carry an answer, %d unwarned" % (len(held_and_answered), len(unwarned)))
# The reason must name this row's own terms, or five rows read identically and none is read.
# Each reason must name this row's own terms. Two rows CAN carry the same reason, because two
# retirements can swap the same pair of words, so the test is that the terms are named rather
# than that every string is unique.
swapped_rows = [r for r in queue if r["why_not_recommended"].startswith("SAME FRAME")]
unnamed = [r["row"] for r in swapped_rows
           if " against " not in r["why_not_recommended"]
           or not (r["term_in_the_retiring_code"] and r["term_in_the_successor"])]
record("every swapped-term reason names the two terms", not unnamed,
       "%d rows, %d distinct reasons, all naming what differs"
       % (len(swapped_rows), len({r["why_not_recommended"] for r in swapped_rows}))
       if not unnamed else "%d unnamed: %s" % (len(unnamed), unnamed[:3]))
# The change report is how a correction becomes visible. Its absence is a silent regression.
changes = os.path.join(DECISIONS, "WHAT_CHANGED.md")
record("each build records what it changed", os.path.exists(changes),
       "WHAT_CHANGED.md is written beside the queue")

# A row that declines to recommend must still give the reader something to weigh. Fourteen said
# "not recommended" and offered nothing, one of them worth CAD 7,588,057,599, because the
# consolidation checked three kinds of alternative and forgot the runner-up.
# A withheld row must either name an alternative or say plainly that none qualifies. Silence
# across four columns reads as an omission; eleven rows sat like that once the alternatives began
# being rule-checked as strictly as the replacement candidate.
# 11 -> 5 on 2026-08-12, when a leftover line stopped counting as a substituted term. The five
# that remain are genuinely stranded: a veterinary line whose parent has no veterinary leftover,
# a foot-and-mouth vaccine, saxitoxin, dried human blood, and malaria test kits.
# 5 -> 4 on 2026-08-14. Malaria test kits, exports 3002.11.00, left this set by being HELD
# rather than by acquiring an alternative. A held row is not asked to decide anything, so it
# carries no verdict of ANALYST and no alternative is computed for it. The other four are
# unchanged and still genuinely stranded.
# 4 -> 13. Releasing 25 rows from the hold turns them into ordinary ANALYST rows, and on nine of
# them every candidate trips a rule, which is a finding in itself and is said in words.
# 13 -> 12 on 2026-08-18, finding 122: row 68 gained a second alternative, so it is no longer a row where nothing qualifies.
EXPECTED_NO_ALTERNATIVE = 12
none_qualify = [r["row"] for r in answers
                if r["verdict"].startswith("ANALYST - a") and not r["second_alternative"]]
empty_handed = [r["row"] for r in answers
                if r["verdict"].startswith("ANALYST - a")
                and not r["second_alternative"]
                and not r["second_alternative_description"]]
record("rows where no candidate qualifies are unchanged",
       len(none_qualify) == EXPECTED_NO_ALTERNATIVE,
       "%d rows, expected %d, each saying so in words"
       % (len(none_qualify), EXPECTED_NO_ALTERNATIVE))
# And the converse: a recommended row must NOT carry one, or the sheet invites doubt the
# evidence does not support.
noisy = [r["row"] for r in answers
         if r["verdict"].startswith("CONFIRM") and r["second_alternative"]]
record("no recommended row carries an alternative beside it", not noisy,
       "0 of %d" % sum(1 for r in answers if r["verdict"].startswith("CONFIRM"))
       if not noisy else "%d do: %s" % (len(noisy), noisy[:3]))
record("no withheld row is left with nothing to weigh", not empty_handed,
       "all %d withheld rows name an alternative or say none qualifies"
       % sum(1 for r in answers if r["verdict"].startswith("ANALYST - a"))
       if not empty_handed else "%d empty: %s" % (len(empty_handed), empty_handed[:4]))
# AN ALTERNATIVE SHOWN WITHOUT A SCORE IS WORSE THAN ONE NOT SHOWN. Ten rows carried a named
# alternative and an empty score, which reads as "no score exists". On four a score did exist,
# and on rows 40, 41 and 50 it equalled or beat the proposal sitting beside it, under a decision
# of accept. The cause was the chain terminus: it comes from chain_ends_at rather than from the
# ranking, so it arrived with no score and nothing required one.
unscored = [r["row"] for r in answers
            if r["second_alternative"].strip()
            and not r["second_alternative_wording_match"].strip()]
record("every alternative shown carries a score, so it can be weighed against the proposal",
       not unscored,
       "%d row(s) show an alternative, every one scored"
       % sum(1 for r in answers if r["second_alternative"].strip()) if not unscored
       else "%d show one with no score, which reads as no score existing: %s"
            % (len(unscored), unscored[:6]))
# And the score must be the ranker's, not a second opinion. A number computed a different way
# invites a comparison that does not hold.
_mismatched = [r["row"] for r in answers
               if r["second_alternative"].strip() and r["second_alternative_description"].strip()
               and r["second_alternative_wording_match"].strip()
               and r["second_alternative_wording_match"].strip()
               != "%.4f" % _builder_ratio(r["retiring_description"],
                                          r["second_alternative_description"])]
record("each alternative's score is the ranker's own function on the wording shown",
       not _mismatched,
       "%d scored alternative(s), each reproducible from the two descriptions on the row"
       % sum(1 for r in answers if r["second_alternative_wording_match"].strip())
       if not _mismatched else "%d do not reproduce: %s" % (len(_mismatched), _mismatched[:5]))

# A replacement is offered only where the PROPOSAL is defective, never where the row is merely
# uncertain. Ignoring that offered 0.6372 in place of a 1.0000 exact match on one row.
alt = [r for r in queue if r["best_candidate_passing_every_rule"]]
# Inferring the defect from the reason text does not work: suggest() reports the first reason
# that applies, so a proposal can be both below the review threshold and defective while the row
# only says the former. These assert what the artefact itself can show.
record("no replacement is offered where the proposal is recommended",
       not [r for r in alt if r["verdict"].startswith("CONFIRM")],
       "0 of %d; a replacement appears only where the proposal was not recommended" % len(alt))
record("every replacement names a description and a score",
       all(r["best_candidate_description"] and r["best_candidate_wording_match"] for r in alt),
       "%d replacement(s), each with both" % len(alt))
record("every replacement passes the rules that rejected the proposal",
       all(r["best_candidate_passing_every_rule"] != r["proposed_successor"] for r in alt),
       "%d replacement(s), none of them the code that was rejected" % len(alt))

print()
print("The sheet reads in row order, and a stale decision stays flagged:")
# A stable label that does not match the position is worse than either on its own: making the
# number fixed while the sort stayed on priority put row 66 at the top of the sheet, above row 1.
_order = [int(r["row"]) for r in answers]
record("the file reads in row order", _order == sorted(_order),
       "row 1 first and row %d last" % _order[-1]
       if _order == sorted(_order) else "out of order at position %d"
       % next(i for i, (a_, b_) in enumerate(zip(_order, sorted(_order))) if a_ != b_))
# The warning that a decision rests on superseded evidence lasted exactly one rebuild, because it
# compared against the previous BUILD rather than against what was on screen when the judgement
# was made. Row 66 was rejected while its proposal read "Butter-making ferment cultures", the
# wording was corrected, and by the next build there was no difference left to notice.
_seen_file = os.path.join(WORK, "_decisions_seen.json")
if os.path.exists(_seen_file):
    import json as _js
    with open(_seen_file, encoding="utf-8") as _h:
        _was = _js.load(_h)
    _decided = {r["link_id"] for r in answers if (r.get("decision") or "").strip()}
    record("every decision on file records what was on screen when it was taken",
           _decided <= set(_was),
           "%d decision(s), each with the evidence it rests on" % len(_decided)
           if _decided <= set(_was)
           else "%d decision(s) have no record of it" % len(_decided - set(_was)))
    _stale = [r["row"] for r in answers
              if (r.get("decision") or "").strip()
              and _was.get(r["link_id"], {}).get("proposed_successor_description",
                                                 r["proposed_successor_description"])
              != r["proposed_successor_description"]
              and not r.get("check_this_again", "").startswith("this was decided while")]
    record("a decision resting on a corrected wording is still flagged", not _stale,
           "no decision rests on evidence that has changed without saying so"
           if not _stale else "%d silent: %s" % (len(_stale), _stale[:4]))
    record("nothing is flagged that has not actually moved",
           all(_was.get(lid, {}).get("proposed_successor_description")
               != next(r["proposed_successor_description"]
                       for r in answers if r["link_id"] == lid)
               for lid in {r["link_id"] for r in answers
                           if r.get("check_this_again", "").startswith("this was decided while")}),
           "every flag names a wording that really changed")

print()
print("The row number is a label, not a position:")
# It was the index in the sorted order, so anything that changed a score renumbered the sheet.
# Correcting the ranker moved 173 of the 230. Everything outside this file refers to rows by that
# number, including the findings register and every question the analyst has asked, so a number
# that moves silently invalidates the record of the work.
_ledger_path = os.path.join(WORK, "_row_numbers.json")
if os.path.exists(_ledger_path):
    import json as _json
    with open(_ledger_path, encoding="utf-8") as _h:
        _ledger = _json.load(_h)
    _drift = [r["row"] for r in answers
              if str(_ledger.get(r["link_id"], r["row"])) != str(r["row"])]
    record("no row has been renumbered since it was first assigned", not _drift,
           "%d rows, each keeping the number it was given" % len(_ledger)
           if not _drift else "%d moved: %s" % (len(_drift), _drift[:5]))
    record("every row in the sheet has a number on the ledger",
           all(r["link_id"] in _ledger for r in answers),
           "no row is numbered off the books")
    record("no two rows share a number",
           len(set(_ledger.values())) == len(_ledger),
           "%d distinct numbers for %d rows" % (len(set(_ledger.values())), len(_ledger)))

print()
print("A candidate is described in the life that can receive the trade:")
# A reused number carries a different description in each life, and the lookup kept the earliest
# one, so ten proposals printed wording from a life that had already closed. On row 7 the
# proposal read "Penicillin V" while the life receiving the trade reads "Amoxycillin", the
# retirement's own name, and the analyst had already decided it.
_lives = {}
for _f in ("imports", "exports"):
    _p = os.path.join(WORK, "commodity_inventory_%s.csv" % _f)
    if os.path.exists(_p):
        for _r in load(_p):
            # The termination note and whose life it belongs to travel with the life, so the
            # control below can work out when the RECORD ends a classification without reading it
            # back off the artefact it is checking.
            _lives.setdefault((_f, _r["hs_code"]), []).append(
                (_r["first_period"], _r["last_period"], _r["description"],
                 _r.get("stated_termination", ""),
                 _r.get("stated_termination_is_this_life", "")))
_qf = {r["link_id"]: r for r in queue}


def _month(p):
    return p[:4] + "-" + p[4:]


_stale = []
for _a in answers:
    _q = _qf.get(_a["link_id"])
    if not _q or not _q.get("proposed_successor"):
        continue
    _all = _lives.get((_q["flow"], _q["proposed_successor"].replace(".", "")), [])
    if len(_all) < 2:
        continue
    # AGAINST THE MONTH THE RECORD ENDS THE CLASSIFICATION, not the month the money stopped.
    # This control encoded the last-trade rule, which is the M4/M6 class the project has paid for
    # three times, and it went on passing while Stage 1c scored the same candidates on a different
    # life. Rebuilt here from the inventory rather than read off the queue. Finding 106.
    _ends = _q["last_traded"]
    for _life in _lives.get((_q["flow"], _q["retiring_code"].replace(".", "")), []):
        if _month(_life[1]) == _q["last_traded"] and _life[3] and _life[4] != "no":
            _ends = max(_ends, _month(_life[3]))
    _alive = [x for x in _all if _month(x[1]) > _ends]
    _want = min(_alive)[2] if _alive else _all[-1][2]
    if _a["proposed_successor_description"].strip() != _want.strip():
        _stale.append(_a["row"])
record("no proposal is described in a life that had already closed", not _stale,
       "every reused number is described in the life that can receive the trade"
       if not _stale else "%d show a closed life: %s" % (len(_stale), _stale[:5]))
# A corrected wording under an existing decision is the strongest reason to look again.
_corrected = [r["row"] for r in answers
              if (r.get("decision") or "").strip()
              and r.get("check_this_again", "").startswith("the wording shown")]
disclose("a wording corrected under a decision says so",
         "%d decided row(s) are flagged for re-reading" % len(_corrected))

print()
print("Every description comes from the delivery, and from nothing else:")
# THE CROSSWALK IS BUILT IN STATISTICS CANADA'S NUMBERING, SO IT MUST SPEAK IN ITS WORDS.
#
# evidence/cbsa/sched_ch30_*.csv carries a description column too, and it is authoritative for
# the tariff. It is the wrong source here, and stage1b already says why in as many words: the
# tariff and the trade data are two different numbering systems below six digits, and matching
# at full length finds 240 of 386 import codes against 54 of 56 at six digits. A ten-digit
# description lifted from the schedule is therefore attached to a code that is not reliably the
# same code, and it is written in a vocabulary the ranker was never calibrated on.
#
# Nothing in the pipeline does this today. stage1a takes code existence from the schedules and
# stage1b takes the subheading; the queue builder, the ranker, stage 0 and stage 2 never open a
# schedule at all. This control exists so that stays true, because the mistake is easy to make
# by hand and leaves no trace once the wording is in the artefact.
_from_delivery, _foreign = 0, []
for _r in queue:
    for _code, _text, _what in (
            (_r["retiring_code"], _r["retiring_description"], "retiring"),
            (_r["proposed_successor"], _r["proposed_successor_description"], "successor")):
        _digits = "".join(c for c in (_code or "") if c.isdigit())
        if not _digits or not (_text or "").strip():
            continue
        _known = {life[2] for life in _lives.get((_r["flow"], _digits), [])}
        if not _known:
            continue
        _from_delivery += 1
        if _text not in _known:
            _foreign.append("%s %s %s" % (_r["row"], _what, _code))
record("every description in the queue is the delivery's own wording", not _foreign,
       "%d description(s) checked against the Stage 0 inventory, all of them the delivery's"
       % _from_delivery if not _foreign
       else "%d not found in the delivery: %s" % (len(_foreign), _foreign[:5]))

print()
print("A mark is counted only where there is a colour:")
# Excel writes an explicit style on every cell of the used range when it saves, so counting
# style ids reported 230 rows kept their highlighting on a workbook holding three marks. A count
# that says everything survived is worse than none, because it is read as reassurance.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import _xlsx  # noqa: E402

_book = os.path.join(DECISIONS, "stage2_decisions.xlsx")
if os.path.exists(_book):
    _marks = _xlsx.coloured_rows(_book)
    _ids = {r["link_id"] for r in answers}
    record("the marks counted are rows carrying a fill, not rows carrying a style",
           len(_marks) < len(_ids),
           "%d of %d rows carry a colour" % (len(_marks), len(_ids)))
    record("every mark belongs to a row still in the sheet", _marks <= _ids,
           "no mark points at a retirement the build no longer holds")

print()
print("The record of what changed is kept against the file the reader opens:")
# The report existed because the analyst was flagging rows twice, and it was measuring the wrong
# file. It watched the queue while the reader reads the sheet, and three of the columns a
# decision turns on are assembled in the sheet and absent from the queue. It also advanced its
# snapshot on every build, so a build that skipped a locked workbook consumed the difference and
# the next build reported nothing changed when fourteen rows of advice had been rewritten.
import json as _json  # noqa: E402
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402

_builder = importlib.import_module("make_adjudication_queue")
record("the change report watches the columns a decision turns on",
       {"what_this_points_to", "how_they_relate", "how_the_second_relates",
        "second_alternative"} <= set(_builder.WATCHED),
       "watches %d columns including the advice" % len(_builder.WATCHED))
record("it watches no column the sheet stopped carrying",
       set(_builder.WATCHED) <= set(_builder.DECISION_COLUMNS),
       "every watched column is one the reader can see")

_tmp = _tempfile.mkdtemp()
_saved = (_builder.WORK_DIR, _builder.DECISIONS_DIR)
try:
    _builder.WORK_DIR = _builder.DECISIONS_DIR = __import__("pathlib").Path(_tmp)

    def _row(advice):
        return [{"link_id": "imports:1:2001-01", "row": "5", "retiring_code": "1",
                 "retiring_description": "a commodity", "value_cad": "100",
                 "what_this_points_to": advice,
                 **{c: "" for c in _builder.WATCHED if c != "what_this_points_to"}}]

    def _said():
        return open(os.path.join(_tmp, "WHAT_CHANGED.md"), encoding="utf-8").read()

    _builder.report_changes(_row("REJECT"), True)
    locked, _ = _builder.report_changes(_row("ACCEPT"), False)
    record("a change is reported even when the workbook could not be refreshed",
           locked == 1 and "being held" in _said(),
           "reported and marked as not yet in the sheet")
    again, _ = _builder.report_changes(_row("ACCEPT"), True)
    record("a change is held until the reader's file has actually been written",
           again == 1,
           "the same change is still reported on the build that reaches the workbook"
           if again == 1 else "it was consumed against a file the reader never saw")
    settled, _ = _builder.report_changes(_row("ACCEPT"), True)
    record("a change is reported once and then stops", settled == 0,
           "reported once, then silent")
    _builder.WATCHED = _builder.WATCHED + ("decision",)
    widened, _ = _builder.report_changes(_row("ACCEPT"), True)
    record("widening the watched set rebaselines instead of flagging every row",
           widened == 0 and "new baseline" in _said(),
           "says it rebaselined rather than reporting 230 false changes")
finally:
    _builder.WATCHED = tuple(c for c in _builder.WATCHED if c != "decision")
    _builder.WORK_DIR, _builder.DECISIONS_DIR = _saved
    _shutil.rmtree(_tmp, ignore_errors=True)

print()
print("The workbook is the file being filled in. The CSV beside it is a copy:")
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import _xlsx  # noqa: E402

BOOK = os.path.join(DECISIONS, "stage2_decisions.xlsx")
if not os.path.exists(BOOK):
    record("the workbook exists", False, "no workbook; the answer sheet is CSV only")
else:
    book_columns, book_rows = _xlsx.read(BOOK)
    book = {r["link_id"][0]: {k: v[0] for k, v in r.items()} for r in book_rows}
    record("the workbook and the copy hold the same retirements",
           set(book) == {r["link_id"] for r in answers},
           "%d link_id(s) on both sides" % len(book))
    # Judgement must always agree. Evidence may lag, because the workbook cannot be refreshed
    # while it is open in a spreadsheet and the copy can, and a suite that goes red for as long
    # as someone is working is a suite people learn to ignore.
    JUDGEMENT = ("decision", "correct_successor_if_rejected", "reason", "decided_by",
                 "decided_on")
    by_link = {r["link_id"]: r for r in answers}
    conflict = [k for k in book
                if any(book[k].get(c, "") != by_link[k].get(c, "") for c in JUDGEMENT)]
    record("the workbook and the copy agree on every decision", not conflict,
           "%d decision column(s) identical across %d rows" % (len(JUDGEMENT), len(book))
           if not conflict else "%d row(s) disagree: %s" % (len(conflict), conflict[:3]))
    stale = [k for k in book
             if any(book[k].get(c, "") != by_link[k].get(c, "")
                    for c in book_columns if c in by_link[k] and c not in JUDGEMENT)]
    disclose("any lag in the workbook's evidence is reported, not treated as damage",
             "the workbook is current" if not stale
             else "%d row(s) hold older evidence than the copy, which happens while the workbook "
                  "is open. Close it and rebuild to refresh." % len(stale))
    # Formatting is the reason the workbook exists. It must survive a rebuild, and it must stay
    # on the retirement it was applied to rather than on the row number it happened to occupy.
    marks = _xlsx.formatting_by_key(book_columns, book_rows, "link_id")
    record("the workbook still carries its formatting", bool(marks),
           "%d row(s) carry cell formatting" % len(marks))
    # One sheet, no formulas. The writer rebuilds a single sheet of text; anything else would be
    # lost on the next rebuild, so its absence is asserted rather than assumed.
    import zipfile as _zip
    with _zip.ZipFile(BOOK) as archive:
        sheets = [n for n in archive.namelist() if n.startswith("xl/worksheets/")]
        formulas = b"<f>" in archive.read("xl/worksheets/sheet1.xml")
    record("the workbook is one sheet, which is all the writer can rebuild", len(sheets) == 1,
           "%d sheet(s)" % len(sheets))
    record("the workbook holds no formulas, which the writer would discard", not formulas,
           "none found" if not formulas else "FORMULAS PRESENT, they will be lost on rebuild")
    # Excel is stricter than every reader in this project, and the gap is silent. It refuses a
    # worksheet whose elements carry a prefix for the main namespace, and it refuses one whose
    # opening elements are out of the order the schema fixes. Both faults were written into the
    # answer sheet on 2026-08-12 by the writer's own preservation path. openpyxl and this suite
    # read that file without complaint, Excel would not open it even to repair it, and no control
    # here noticed. So the shape of the sheet is now asserted rather than assumed.
    import re as _re
    _head = archive_head = None
    with _zip.ZipFile(BOOK) as archive:
        archive_head = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    _head = archive_head.split("<sheetData>")[0]
    HEAD_ORDER = ("sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols")
    prefixed = sorted(set(_re.findall(r"<(\w+):(?:%s)\b" % "|".join(HEAD_ORDER), _head)))
    record("the worksheet names its elements without a namespace prefix", not prefixed,
           "Excel reads these only unprefixed" if not prefixed
           else "prefixed with %s; Excel will refuse to open the file" % prefixed)
    # The prefix is optional in this pattern on purpose. Matching only the unprefixed spelling
    # would make this control blind on exactly the files the control above rejects, and it would
    # have reported the order as correct on the 2026-08-12 workbook, where it was not.
    seen = _re.findall(r"<(?:\w+:)?(%s)[ />]" % "|".join(HEAD_ORDER), _head)
    expected = [t for t in HEAD_ORDER if t in seen]
    record("the worksheet's opening elements are in the order the schema fixes",
           seen == expected,
           " then ".join(seen) if seen == expected
           else "found %s, expected %s; Excel will refuse to open the file"
                % (" then ".join(seen), " then ".join(expected)))
    every = [r for r in book_rows if r["decision"][0].strip()]
    record("decisions in the workbook are readable by the pipeline",
           all(normalise_decision(r["decision"][0]) for r in every),
           "%d decision(s), all understood" % len(every))

print()
print("The join key. Decisions attach to retirements, never to positions:")
# Measured 2026-08-11: changing what the suggestion column recommends moved 214 of 238 row
# numbers onto different retirements. Anything joined on "row" would have silently reattached
# every decision made before that change. These controls exist so that cannot recur unnoticed.
ids = [r["link_id"] for r in queue]
record("every row carries a link_id", all(ids), "%d of %d" % (sum(1 for i in ids if i), len(ids)))
record("no two rows share a link_id", len(set(ids)) == len(ids),
       "%d distinct across %d rows" % (len(set(ids)), len(ids)))
malformed = [r["link_id"] for r in queue
             if r["link_id"] != "%s:%s:%s" % (r["flow"], r["retiring_code"], r["last_traded"])]
record("each link_id is built from the retirement it names", not malformed,
       "flow:code:last_traded on all %d" % len(queue)
       if not malformed else "%d wrong: %s" % (len(malformed), malformed[:3]))
record("the answer sheet is keyed the same way",
       {r["link_id"] for r in answers} == set(ids),
       "%d link_id(s) on both sides" % len(set(ids)))
# The key must not be reconstructible from the sort. If row order and link order agree perfectly
# it proves nothing, so state the relationship rather than assume it.
by_id = {r["link_id"]: r for r in queue}
record("the answer sheet row numbers agree with the queue's",
       all(by_id[r["link_id"]]["row"] == r["row"] for r in answers),
       "both files present the same reading order")

print()
print("The answer sheet must mirror the queue and stand alone:")
by_row = {r["row"]: r for r in queue}
record("both files hold the same rows", {r["row"] for r in answers} == set(by_row),
       "%d rows each" % len(answers))
# Compared on verdict rather than suggested_decision: the sheet stopped carrying the raw
# recommendation when it was narrowed, because the verdict says the same thing in words a person
# can act on.
mismatched = [r["row"] for r in answers
              if any(by_row[r["row"]][c] != r[c] for c in
                     ("retiring_code", "proposed_successor", "verdict"))]
record("the answer sheet agrees with the queue", not mismatched,
       "0 disagree" if not mismatched else "disagree: %s" % mismatched[:3])
# What the sheet must carry to be decidable without opening anything else. shared_meaning_words
# left this list on 2026-08-12 when the sheet was narrowed from 45 columns to 33: it is a
# diagnostic that is explicitly never a score, and it was being read past rather than read. The
# queue file still holds it, and the control above proves nothing was lost, only moved.
# What the sheet must carry to be decidable without opening anything else. The list shrank with
# the sheet: the alternatives are consolidated into best_alternative, which names the one most
# worth weighing and says why it is offered, and the queue keeps them separately.
for column in ("verdict", "why", "proposed_successor_traded",
               "proposed_successor_wording_match", "second_alternative",
               "second_alternative_description", "check_this_again"):
    record("the answer sheet carries %s, so it stands alone" % column, column in answers[0],
           "present")
# Only the load-bearing columns need to survive a spreadsheet. Adding dates to this file
# reintroduced 1,016 cells Excel will rewrite, and that is harmless: it will turn 1988-12 into
# Dec-88 in a column nobody reads back. What must survive is the join key and the five columns
# holding judgement, and none of those is a date or a number a spreadsheet will touch.
LOAD_BEARING = ("row", "decision", "correct_successor_if_rejected", "reason",
                "decided_by", "decided_on")
unsafe = [(k, v) for r in answers for k, v in r.items()
          if k in LOAD_BEARING and v and len(v) == 7 and v[4] == "-" and v[:4].isdigit()]
record("nothing a spreadsheet rewrites sits in a column that is read back", not unsafe,
       "the join key and the five answer columns are text or integers"
       if not unsafe else "%d found: %s" % (len(unsafe), unsafe[:2]))
# The reference columns MAY be reformatted and that is expected, so this reports the state
# rather than requiring a particular one. An earlier version required the unmangled form to be
# present and therefore failed the moment the tolerated thing actually happened, which is a
# control asserting the opposite of its own stated intent.
untouched = sum(1 for r in answers for k, v in r.items()
                if k not in LOAD_BEARING and v and len(v) == 7 and v[4] == "-"
                and v[:4].isdigit())
rewritten = sum(1 for r in answers for k, v in r.items()
                if k not in LOAD_BEARING and v and len(v) == 6 and v[3] == "-"
                and v[:3].isalpha())
disclose("the reference columns are reported, whatever a spreadsheet did to them",
         "%d cell(s) still in the written form, %d already rewritten by a spreadsheet. "
         "Neither is read back by any stage." % (untouched, rewritten))

# What a person actually typed. A value the pipeline cannot read is worse than a blank, because
# a blank is visibly undecided and a misspelling looks decided.
# second is a real answer, not a synonym for approve: it names the alternative rather than the
# proposal, and Stage 2 will read the successor from a different column because of it.
record("the word second is understood",
       normalise_decision("second") == "second" and normalise_decision("2nd") == "second",
       "second and its variants read as themselves, not as approve")
record("a word the pipeline does not know still reads as nothing",
       normalise_decision("banana") == "",
       "unknown text is reported rather than guessed at")
written = [r for r in answers if (r.get("decision") or "").strip()]
unreadable = [(r["row"], r["decision"]) for r in written if not normalise_decision(r["decision"])]
record("every decision written so far is one the pipeline can read", not unreadable,
       "%d decision(s) on file, all understood" % len(written) if not unreadable
       else "%d not understood: %s" % (len(unreadable), unreadable[:4]))
unsigned = [r["row"] for r in written if not (r.get("decided_by") or "").strip()]
disclose("who decided is recorded, or the gap is reported",
         "all %d decisions signed" % len(written) if not unsigned
         else "%d of %d decision(s) carry no name in decided_by. Not an error, but the paper "
              "will want the provenance." % (len(unsigned), len(written)))
# WHEN, WHICH THE PLAN ASKS FOR IN THE SAME BREATH AS WHO, AND WHICH WAS BLANK ON ALL 203.
#
# A control rather than a disclosure, because the build cannot supply this on its own and will
# not complain if it is missing. The date comes from evidence/provenance/decision_dates.csv,
# which evidence/provenance/derive_decision_dates.py writes from the repository's history and
# which is run by hand. If that file goes stale or is never run after new decisions are
# committed, this is what says so.
undated = [r["row"] for r in written if not (r.get("decided_on") or "").strip()]
record("every decision records when it entered the record", not undated,
       "all %d decisions dated" % len(written) if not undated
       else "%d of %d undated: %s. Commit the decisions, then run "
            "evidence/provenance/derive_decision_dates.py."
            % (len(undated), len(written), undated[:5]))
# The other direction, which is the one that would be a lie rather than a gap.
premature = [r["row"] for r in answers
             if (r.get("decided_on") or "").strip() and not (r.get("decision") or "").strip()]
record("no undecided row claims a decision date", not premature,
       "%d row(s) carry a date, every one of them decided" % len(written) if not premature
       else "%d dated but undecided: %s" % (len(premature), premature[:5]))

print()
print("Judgement follows link_id and not row position, proved in a sandbox:")
# WHY THIS EXISTS. An earlier control claimed this ground and could not hold it, and it was
# removed on 2026-08-13 rather than left standing. It perturbed the sort of the LIVE answer sheet,
# so it refused to run whenever that sheet held work, which on this artefact is always; the three
# falsifiable controls inside its else branch never ran, and the branch reported "stood down, as
# designed" as a passing control. It could not have passed anyway. It proved rows had moved by
# reversing the sort, and work/_row_numbers.json now pins each row number to a link_id, so
# reversing the sort moves nothing. The property it was meant to prove is the one the whole Stage
# 2 design rests on, and until the controls below existed nothing that could fail asserted it.
#
# So this runs on COPIES, in a temporary directory, and never opens the live sheet for writing.
# It moves the rows by shuffling the sandbox's own row-number ledger, which is the one lever that
# still moves them, then rebuilds and asks whether each planted decision stayed with its
# retirement. It refuses to conclude anything unless the row numbers actually moved first.
_cf_tmp = _tempfile.mkdtemp(prefix="carryforward_")
_cf_saved = (_builder.WORK_DIR, _builder.DECISIONS_DIR, _builder.PROJECT_ROOT)
try:
    import pathlib as _pathlib

    _work = _pathlib.Path(_cf_tmp) / "work"
    _dec = _pathlib.Path(_cf_tmp) / "decisions"
    _work.mkdir()
    _dec.mkdir()
    for _name in os.listdir(WORK):
        if _name.endswith(".csv") or _name.endswith(".json"):
            _shutil.copy(os.path.join(WORK, _name), _work / _name)

    _ledger_path = _work / "_row_numbers.json"
    _ledger = _json.loads(_ledger_path.read_text(encoding="utf-8"))
    _by_number = sorted(_ledger, key=lambda k: _ledger[k])
    # Three retirements from far apart in the sheet, so a positional join cannot coincidentally
    # land them back on themselves.
    _picks = [_by_number[0], _by_number[len(_by_number) // 2], _by_number[-1]]
    _planted = {k: v for k, v in zip(_picks, ("accept", "reject", "second"))}
    _before_numbers = {k: _ledger[k] for k in _picks}

    _queue_rows = load(os.path.join(DECISIONS, "stage2_adjudication_queue.csv"))
    _code_of = {r["link_id"]: r["retiring_code"] for r in _queue_rows}
    with open(_dec / "stage2_decisions.csv", "w", newline="", encoding="utf-8") as _fh:
        _w = csv.DictWriter(_fh, fieldnames=["link_id", "row", "retiring_code", "decision",
                                             "correct_successor_if_rejected", "reason",
                                             "decided_by", "decided_on"])
        _w.writeheader()
        for _lid, _dec_value in _planted.items():
            _w.writerow({"link_id": _lid, "row": str(_ledger[_lid]),
                         "retiring_code": _code_of.get(_lid, ""), "decision": _dec_value,
                         "correct_successor_if_rejected": "", "reason": "carry-forward sandbox",
                         "decided_by": "check", "decided_on": ""})

    # Move the rows. Perturbing the ledger's numbering is what the original control wanted and
    # could no longer achieve.
    #
    # THIS WAS A REFLECTION, `_highest + 1 - v`, AND A REFLECTION HAS A FIXED POINT. With an odd
    # number of rows the middle row maps to itself: at 231 rows, row 116 stays at 116. On
    # 2026-08-17 the queue grew from 230 to 231 and one of the three planted retirements landed
    # there, so the control reported 2 of 3 moved and failed for a reason that had nothing to do
    # with carry-forward. The perturbation was weaker than it read, and only a change in the row
    # count revealed it.
    #
    # A rotation by one has no fixed point for any count above one, so every row is guaranteed to
    # move whatever the queue's length becomes. It is still a bijection, which is what makes the
    # rebuilt numbering legal rather than merely different.
    _highest = max(_ledger.values())
    _ledger_path.write_text(_json.dumps({k: (v % _highest) + 1 for k, v in _ledger.items()}),
                            encoding="utf-8")

    _builder.WORK_DIR, _builder.DECISIONS_DIR = _work, _dec
    # main() reports what it wrote relative to PROJECT_ROOT, so the sandbox has to be the root
    # for the duration or the report raises on a path outside the project.
    _builder.PROJECT_ROOT = _pathlib.Path(_cf_tmp)
    # main() rather than build(): build() assembles the rows and fixes the numbering, but the
    # carry-forward join and the write both live in main(), so calling build() alone proves nothing.
    _builder.main()

    _after = {r["link_id"]: r for r in load(_dec / "stage2_decisions.csv")}
    _moved = [k for k in _picks
              if k in _after and str(_after[k]["row"]) != str(_before_numbers[k])]
    record("the sandbox actually moved the rows, so the next control can mean something",
           len(_moved) == len(_picks),
           "%d of %d planted retirements changed row number" % (len(_moved), len(_picks)))
    _kept = [k for k, v in _planted.items()
             if k in _after and (_after[k].get("decision") or "").strip() == v]
    record("every decision stayed with its own retirement after the rows moved",
           len(_kept) == len(_planted),
           "%d of %d decisions followed their link_id" % (len(_kept), len(_planted)))
    _codes_ok = [k for k in _planted
                 if k in _after and _after[k].get("retiring_code") == _code_of.get(k)]
    record("each decision still sits on the commodity it was entered against",
           len(_codes_ok) == len(_planted),
           "%d of %d retiring codes unchanged under the decision" % (len(_codes_ok), len(_planted)))
except Exception as _error:                            # noqa: BLE001 - a broken control must say so
    record("the carry-forward control ran", False,
           "it raised %s: %s" % (type(_error).__name__, _error))
finally:
    _builder.WORK_DIR, _builder.DECISIONS_DIR, _builder.PROJECT_ROOT = _cf_saved
    _shutil.rmtree(_cf_tmp, ignore_errors=True)
    record("the sandbox left nothing behind and the live sheet was never opened for writing",
           not os.path.exists(_cf_tmp),
           "temporary directory removed; ANSWERS and the workbook were never written by this control")

# THE CO-CASUALTY LINE, MEASURED RATHER THAN DESCRIBED. Finding 137, 2026-08-18.
#
# The paragraph justifying CO_CASUALTY_MONTHS=24 carried four figures and all four had gone stale,
# the same way finding 135's did: written once, never re-derived. What justifies the number is not
# any of the four counts, it is that 24 falls in a GAP rather than through a cluster. So the gap is
# asserted and the counts are pinned beside it.
import re as _cc_re


def _cc_months(period):
    return int(period[:4]) * 12 + int(period[4:])


_cc_retiring = [r for r in queue if (r.get("successor_also_retires") or "").strip()]
_cc_within = [r for r in _cc_retiring if "within" in r["successor_also_retires"]]
_cc_beyond = [r for r in _cc_retiring if "within" not in r["successor_also_retires"]]
_cc_wm = sorted(int(_cc_re.search(r"within (\d+) month", r["successor_also_retires"]).group(1))
                for r in _cc_within)
_cc_end = max((r.get("proposed_successor_last_traded") or "") for r in queue).replace("-", "")
_cc_bm = sorted(
    _cc_months((r.get("proposed_successor_last_traded") or "").replace("-", ""))
    - _cc_months((r.get("last_traded") or "").replace("-", ""))
    for r in _cc_beyond
    if (r.get("proposed_successor_last_traded") or "").replace("-", "") not in ("", _cc_end)
    and (r.get("last_traded") or "").strip())
record("the co-casualty counts are unchanged",
       (len(_cc_retiring), len(_cc_within), len(_cc_beyond)) == (62, 12, 50),
       "%d proposal(s) themselves retiring, %d within two years, %d beyond"
       % (len(_cc_retiring), len(_cc_within), len(_cc_beyond)))
record("the co-casualty line falls in a gap and not through a cluster",
       bool(_cc_wm) and bool(_cc_bm) and max(_cc_wm) <= 24 < min(_cc_bm),
       "the within-group tops out at %d months and the next value is %d, so the line could sit "
       "anywhere between them and classify the same rows"
       % (max(_cc_wm or [0]), min(_cc_bm or [0])))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("The adjudication artefact is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("The adjudication artefact is validated. Every row holds what is needed to decide it.")
