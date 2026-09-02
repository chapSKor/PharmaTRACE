"""
Stage 1c. Let meaning veto, then let text rank what is left.


Inputs:
    work/stage1_official_{imports,exports}.csv      produced by pipeline/s03_stage1b_official_record.py
    work/commodity_inventory_{imports,exports}.csv  produced by pipeline/s01_stage0_read_source.py
    decisions/decisive_distinctions.csv             13 contrasts and 2 relationship rules

Outputs:
    work/stage1_ranked_{imports,exports}.csv        every candidate, with its score and its fate
    work/stage1_review_{imports,exports}.csv        what a person should look at, hardest first
    A printed summary of what meaning removed and what text could and could not settle.


THE ORDER, AND WHY MEANING GOES SECOND AND NOT FIRST
------------------------------------------------------
Stage 1b already let the official record speak. What arrives here is what the record could not
settle: 150 import and 21 export retirements it never reached, plus those it only narrowed.

Two things then happen, and the order is the whole design.

Meaning goes first, and it may only VETO. A contrast the tariff treats as decisive removes a
candidate from the field. It never proposes one, never ranks, and never overrides the record.

Text goes last, and it only RANKS. The score cannot read meaning, so it is not allowed to
remove anything. It orders what survived so a person reads the hardest case first.

Doing it the other way round, ranking first and checking meaning afterwards, would let a
verbatim string match win before anyone asked whether the two products are the same thing.


THE SCORE IS THE ONE THE PROJECT ALREADY PUBLISHED
----------------------------------------------------
difflib.SequenceMatcher on text that is lowercased, has every character other than a letter,
a digit or a space replaced by a space, and repeated spaces collapsed. No abbreviation is
expanded. That is the preparation documented in THRESHOLDS.md section 2.1 and it is reproduced
here rather than improved, because changing it would make every published figure incomparable.

Note the asymmetry, which is deliberate: the score is computed on unexpanded text, and the
meaning gates run on expanded text. The gates need "vet" to read as "veterinary". The score must
not, or it would no longer be the published score.


WHAT THE SCORE IS AND IS NOT EVIDENCE FOR
-------------------------------------------
Measured on this project's own data, the score has an area under the curve of 0.536 against
0.500 for a coin toss. Of 50 successions confirmed by correlation tables, 5 score above 0.85 and
21 below 0.50.

So the score is not used to decide anything that another layer can decide. It is recorded on
every candidate, which is what Reviewer 3 asked for and what the repository has never had, and
it orders the review queue. Where it is the only thing left, that is stated on the row rather
than hidden behind a threshold.


WHAT WOULD MAKE THIS STAGE WRONG
---------------------------------
  - A gate that removed the last candidate would turn "we cannot tell" into "there is no
    successor", which only the official record may say.
  - A gate that added or reordered a candidate would be deciding, not vetoing.
  - Scoring on expanded text would silently produce a different number from the published one.
  - Ranking the review queue by score would put the easy cases first, which is backwards.
"""

import csv
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

import meaning_gates as gates          # noqa: E402
from _shorthand import expand_shorthand  # noqa: E402

FLOWS = ("imports", "exports")
RULES_FILE = PROJECT_ROOT / "decisions" / "decisive_distinctions.csv"

# From THRESHOLDS.md section 3. Reproduced, not chosen.
HIGH_THRESHOLD = 0.85
LOW_THRESHOLD = 0.50

# A top candidate at or above HIGH_THRESHOLD is trusted only when its meaning words are the
# retiring description's meaning words exactly. Overlap is meaning_overlap() below: the words
# the two descriptions share, as a share of the words either carries, so 1.0 means identical
# sets and a single extra or missing word scores below it. Any difference sends the row to
# review (tier 2); identity goes to spot checking (tier 6). Identity is the only overlap that
# leaves nothing to judge, so this is not a chosen value. Named 2026-08-26; it was a bare
# literal.
FULL_MEANING_OVERLAP = 1.0

# Two candidates whose scores sit within this of each other are a near tie that text cannot
# settle, and the row goes to a person (tier 4). Set by judgement; no calibration exercise
# produced it. Named 2026-08-26; it was a bare literal.
NEAR_TIE_MARGIN = 0.05

# An outcome Stage 1b already settled needs no ranking and gets none.
SETTLED = {"decided"}


def prepared(text):
    """The published preparation. Lowercase, non-alphanumerics to spaces, spaces collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def score(a, b):
    return round(difflib.SequenceMatcher(None, prepared(a), prepared(b)).ratio(), 4)


def content_word_set(text):
    return frozenset(prepared(text).split())


# Words that carry no meaning when two descriptions are compared as sets. Listed rather than
# guessed, because what counts as filler is a judgement and a reader is entitled to see it.
# "nes" expands to "not elsewhere specified", which is boilerplate on both sides of almost
# every pair, so leaving it in would make unrelated goods look alike.
FILLER_WORDS = {"not", "elsewhere", "specified", "nes", "other", "than", "whether", "or",
                "for", "of", "the", "and", "in", "to", "a", "an", "with", "on", "o", "t"}


def meaning_words(text):
    """The words that carry meaning, after shorthand is expanded and filler is removed."""
    return frozenset(w for w in prepared(expand_shorthand(text or "")).split()
                     if w not in FILLER_WORDS)


def meaning_overlap(a, b):
    """How much of their meaning two descriptions share, from 0 to 1.

    THIS IS NOT A SCORE AND MUST NEVER BE CALLED ONE. The similarity score is the published
    figure every threshold and every reported result rests on, and it is untouched. This is a
    diagnostic that orders the review queue and decides nothing.

    It exists because the score can be high while the meaning differs. Waste pharmaceuticals of
    heading 30.03 and of subheading 3004.90 agree on nine tenths of their characters and share
    a third of their meaning words, because the part that decides the code is a heading
    reference occupying a fraction of the string. Seven such pairs clear the automatic gate.

    Set comparison rather than a second sequence match, deliberately. Running SequenceMatcher
    over expanded text was tried and abandoned: expanding "nes" injects a long shared phrase
    that the matcher rewards when both sides carry it and punishes when only one does, which
    moved 843 of 3,699 pairs by more than 0.10 in a direction that tracked boilerplate rather
    than meaning.
    """
    first, second = meaning_words(a), meaning_words(b)
    union = first | second
    return round(len(first & second) / len(union), 4) if union else 0.0


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# The five international revisions the correlation tables cover. A code retiring in any other
# month has no table that speaks to it.
HS_REVISIONS = {"200112", "200612", "201112", "201612", "202112"}


def code_last_periods(flow):
    last = {}
    for row in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
        code = row["hs_code"]
        if code not in last or row["last_period"] > last[code]:
            last[code] = row["last_period"]
    return last


def correlated_subheadings_from_evidence():
    """(revision month, subheading) the WCO correlation tables actually speak about.

    Read straight from evidence/wto/wto_ch30_pairs.csv, not from Stage 1b. The question this
    answers is "has the awaited document said anything about this subheading", which is a
    property of the evidence; routing it through the layer that used the evidence would make it
    a property of provenance again, and that is finding 88.

    Every section counts, and every row, marked or not. A table that mentions a subheading at
    all has spoken about it, even where it says the content split and bounds nothing: "the
    record was read and it does not settle this" is an answer, and a different one from "the
    record has not been read".
    """
    path = PROJECT_ROOT / "evidence" / "wto" / "wto_ch30_pairs.csv"
    if not path.exists():
        return set()
    seen = set()
    for row in load(path):
        month = "%d12" % (int(row["boundary_to"]) - 1)
        seen.add((month, "".join(c for c in row["old_code"] if c.isdigit())))
    return seen


def code_stated_terminations(flow):
    """The month the record calls each code obsolete, keyed as the inventory keys it.

    Deliberately a second map beside code_last_periods rather than a column added to it,
    because the two answer different questions and the gap between them is the whole point.
    Money stops before a classification does.
    """
    ends = {}
    for row in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
        stated = (row.get("stated_termination") or "").strip()
        # AND ONLY WHERE THE NOTE IS ABOUT THIS LIFE. A recycled number carries the note on every
        # life it ever had, so exports 30029020's 1988 blood line reads "(Terminated 2016-12)",
        # which belongs to the Saxitoxin line that followed it. Taking that at face value would
        # make this stage read a classification as ending twenty-eight years after it did, and it
        # is read here to choose which life a candidate is scored against. Stage 0 answers whose
        # note it is; 51 lives across the delivery carry someone else's. Finding 105.
        if stated and row.get("stated_termination_is_this_life") != "no":
            ends[(row["hs_code"], row["last_period"])] = stated
    return ends


def classification_ends(row, stated_ends):
    """The month the classification ended: what the record states, else the last trade.

    Never earlier than the last trade. A stated termination preceding observed trade would be
    a contradiction in the source, and taking the earlier of the two would silently discard
    months the delivery actually reports.
    """
    stated = stated_ends.get((row["retiring_code"], row["last_period"]), "")
    return stated if stated and stated >= row["last_period"] else row["last_period"]


def held_for_official_evidence(row, last_periods, stated_ends,
                               correlated_subheadings=frozenset()):
    """True when a correlation table could answer this and none has been extracted yet.

    The official record outranks every later layer, so it must speak BEFORE a person is asked
    to judge. A row settled by hand today that a correlation table contradicts tomorrow is not
    a clean override: it reopens a signed decision and leaves an audit trail the record
    overruled.

    THE WHOLE TEST IS ONE QUESTION: could the awaited table say anything this row does not
    already have? Everything below is that question asked four ways, and a No on any of them
    releases the row.

      1. The classification ends at an international revision, so a table speaks to it at all.
      2. The record has not already NAMED a single destination. If it has, the row is answered
         and nothing stronger is coming.
      3. Where the record BOUNDS the row instead, its destinations do not all sit in one
         six-digit subheading. The correlation tables map HS6 to HS6, so a bound inside a
         single subheading is one such a table cannot narrow by construction.
      4. The whole subheading disappears, so the table has something to say rather than
         mapping the subheading to itself.

    Condition 3 used to read `deciding_layer == "cbsa_concordance"`, which asked WHICH FILE the
    record arrived in rather than what it achieved, so a concordance that merely constrained a
    row exempted it while a constraint set bounding it to the identical codes did not. That is
    finding 88, and this docstring described that superseded rule for the length of one commit,
    which is the failure CHECK_CONVENTIONS.md rule 12 exists to name.

    A fifth limb is NOT enforced: nothing checks that a correlation table for the boundary is
    actually on disk. All five revision boundaries have one today and all 27 held rows wait on
    a file that exists, so the gap is currently theoretical. It is pinned in
    check_stage1c_rank.py rather than tested here, because the stage has no business reading
    the evidence directory.

    THE FIRST CONDITION READS THE STATED TERMINATION, NOT THE MONTH TRADE STOPPED.
    It used to read at_hs_revision_boundary, which Stage 1a computes from the last trading
    month alone. Money stops before a classification does, so a line that went quiet one or
    two months before a revision fell outside the hold while its twin on the other flow, which
    traded to the final month, stayed inside it. Three export rows were in that position,
    CAD 5,661,616: 3001.10.00 quiet from 2006-10 and 3002.11.00 from 2021-11, both stated
    terminated at the revision itself and both decided by hand while the identical import
    commodity at the identical boundary sat blank and held. This is the same defect the
    concordance lookup carried until 2026-08-11, in a third place; see load_concordances in
    s03_stage1b_official_record.py, which states the principle and was fixed for it.

    The test is a union rather than a replacement, so the fix can only ever ADD a hold. A code
    whose last trade lands on a revision stays held even if the record states a later
    termination, which keeps every one of the 21 existing holds intact by construction.

    These rows stay in the queue and sort to the end of it, visible and deliberately not yet
    actionable. Nothing is hidden.
    """
    at_revision = (row["last_period"] in HS_REVISIONS
                   or classification_ends(row, stated_ends) in HS_REVISIONS)
    if not at_revision:
        return False
    # THE EXEMPTION READS WHAT THE RECORD ACHIEVED, NOT WHICH FILE IT ARRIVED IN.
    #
    # It used to be `deciding_layer == "cbsa_concordance"`, which exempted a row the concordance
    # merely CONSTRAINED as readily as one it decided, while a constraint set bounding a row to
    # the identical codes did not exempt at all. Exports 3003.40.00 and its import twin carry the
    # same four destinations from the record and were treated differently on that basis alone.
    # Sixteen rows were exempt; twelve of them are genuinely decided and four are only bounded.
    #
    # Two tests replace it, and both ask whether the document being waited for could say anything.
    # THE AWAITED DOCUMENT, ASKED OF THE EVIDENCE RATHER THAN OF THE LAYER NAME.
    #
    # This hold means "a correlation table could answer this and none has been extracted". Since
    # 2026-08-14 they ARE extracted, so on any subheading the tables cover the premise is simply
    # false, and the sheet was telling the analyst DO NOT DECIDE on twelve rows the record had
    # already answered, CAD 24,787,022,692 of them. That is worse than a wrong answer: it is a
    # standing instruction not to look.
    #
    # Exempting on `deciding_layer == "wco_correlation"` was tried first and reverted the same
    # hour. It is finding 88 repeating, keying the hold on WHICH SOURCE spoke, and the control
    # written for finding 88 caught it in one run. Asking the evidence directly is the same
    # question without the provenance: does the extracted table hold an entry for this subheading
    # at this revision? If it does, the document has spoken, whatever layer ended up using it.
    if correlated_subheadings and (classification_ends(row, stated_ends),
                                   row["retiring_code"][:6]) in correlated_subheadings:
        return False
    if row["outcome"] == "decided":
        # One destination, named by the record. Nothing stronger is coming.
        return False
    destinations = [d for d in row["official_destinations"].split(";") if d]
    if destinations and len({d[:6] for d in destinations}) == 1:
        # Bounded, but every destination sits in ONE six-digit subheading. The correlation tables
        # map HS6 to HS6, so such a table cannot discriminate among them by construction and the
        # hold would buy nothing. One row is in this position, imports 3002.10.00.30, bounded to
        # three codes inside a single subheading, CAD 1,100,455,460.
        return False
    subheading = row["retiring_code"][:6]
    return not any(last > row["last_period"] for code, last in last_periods.items()
                   if code[:6] == subheading)


def descriptions_by_life(flow):
    """Every wording a code has carried, with the months each was in force.

    This used to return only the wording in force when the code BEGAN, which is the wrong
    question. What a candidate is called when it starts says nothing about what it is called
    when it could receive a retirement's trade, and a reused number carries a different
    description in each life. 314 candidate rows across 74 retirements were scored against a
    life that had already closed.

    It changed the answer. Insulin was offered the alkaloids residual, because the hormones
    residual it belongs under was compared using its 1988 wording "Hormones nes, formulated, in
    bulk" rather than the wording it has carried since 2002.
    """
    lives = {}
    for row in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
        lives.setdefault(row["hs_code"], []).append(
            (row["first_period"], row["last_period"], row["description"]))
    return lives


def wording_at(lives, code, stopped):
    """The wording a code carried in the earliest life still running after `stopped`.

    The same choice span_shown makes in the next stage: the life that could receive this
    retirement is the one that explains the link, and any other explains nothing.
    """
    entries = lives.get(code) or []
    alive = [e for e in entries if e[1] > stopped]
    if alive:
        return min(alive)[2]
    return entries[-1][2] if entries else ""


# Continuity is a veto here rather than a filter in Stage 1a, and the reason is that Stage 1a
# can never prove non-existence. Absence of trade is not proof, and absence from the tariff is
# not either, because the tariff omits the statistical breakouts beneath its items. Filtering
# there removed 1,018 candidates on pre-2005 rows with no schedule to check them and no official
# source that would ever speak, and nothing downstream could undo it.
#
# So it lands with the meaning gates: applied after the official record has spoken, recorded per
# candidate with a reason, and reversible by changing this stage rather than baked into a field.
CONTINUITY_VETO = "continuity"


def apply_gates(rules, retiring_text, candidate_text, continuous, named_by_record=False):
    """Which rules fire, split by what they instruct. Gates veto; they never propose.

    A DESTINATION THE OFFICIAL RECORD NAMES CANNOT BE VETOED BY A GATE AT ALL.

    That is the module's first stated rule, and until 2026-08-14 it was implemented for exactly
    one veto. `build` folded the record's destinations into `continuous_codes`, which suppresses
    the continuity veto and nothing else, so every phrase-pair rule still ran on codes Canada's
    concordance had named. One candidate in the delivery was removed that way: on
    imports 3004.50.00.20 retiring 2011-12, the concordance names both 3004.50.00.19 and
    3004.50.00.90 and the `use` gate removed the second, collapsing a two-way official answer to
    one survivor worth CAD 7,548,977. The narrowing was defensible on the merits, the source
    reading "for human use" and the removed code "for veterinary use", and the queue disclosed
    it. The layer order still ran backwards, and the layer order is the design's central claim.

    The gate is still evaluated, because what it says is worth knowing. It is returned as an
    OVERRULED gate rather than as a veto, so the candidate stays in the field and the reader can
    see both that the record named it and that a rule objects. Suppressing the evaluation instead
    would have hidden the disagreement, which is the opposite of the point.
    """
    vetoes, reviews, overruled = [], [], []
    if not continuous:
        vetoes.append(CONTINUITY_VETO)
    for rule in rules:
        if gates.rule_fires(rule, retiring_text, candidate_text):
            (vetoes if rule["action"] == "disqualify" else reviews).append(rule["name"])
    if named_by_record and vetoes:
        overruled, vetoes = vetoes, []
    return vetoes, reviews, overruled


def rank_one(row, rules, descriptions, continuous_codes, official_codes=(), ends_at=None):
    """Veto, then score, then order. Returns one entry per candidate.

    `descriptions` maps a code to its lives; the wording used is the one in force when this
    retirement stopped, not the one the code was born with.

    `official_codes` is passed SEPARATELY from `continuous_codes` rather than merged into it.
    Merging them is what limited the record's exemption to the continuity veto for as long as
    this stage has existed: one set was being asked two different questions.
    """
    retiring_raw = row["description"]
    retiring_expanded = expand_shorthand(retiring_raw or "").lower()
    # Defaults to the month money stopped ONLY when a caller has nothing better, which is the
    # synthetic case in the check. Every real caller passes classification_ends.
    ends_at = ends_at or row["last_period"]
    entries = []
    for code in [c for c in row["candidates_after"].split(";") if c]:
        # SCORED AGAINST THE LIFE THAT COULD RECEIVE THIS RETIREMENT, which is settled by when
        # the RECORD ends the classification and not by when the money stopped. classification_ends
        # has existed two hundred lines above this since the stage was written and was not called
        # here. Finding 106; same class as M4, M6 and the 2026-08-11 concordance defect.
        candidate_raw = wording_at(descriptions, code, ends_at)
        vetoes, reviews, overruled = apply_gates(rules, retiring_expanded,
                                                 expand_shorthand(candidate_raw or "").lower(),
                                                 code in continuous_codes,
                                                 code in official_codes)
        entries.append({
            "candidate": code,
            # Empty on all but the rare candidate the record names AND a gate objects to. Not a
            # veto and not silence: the record won, and the objection is on the record too.
            "record_overruled_gate": ";".join(overruled),
            # The score is recorded on EVERY candidate, including vetoed ones. A reviewer asked
            # for the candidates and their scores, and a vetoed candidate with a high score is
            # exactly the case worth seeing.
            "score": score(retiring_raw, candidate_raw),
            "vetoed_by": ";".join(vetoes),
            "review_flag": ";".join(reviews),
            "same_content_words": content_word_set(retiring_raw) == content_word_set(candidate_raw),
        })
    entries.sort(key=lambda e: (-e["score"], e["candidate"]))
    return entries


def classify(survivors):
    """What text alone can and cannot settle, using the thresholds already published."""
    if not survivors:
        return "all_candidates_vetoed", 0.0, 0.0
    top = survivors[0]["score"]
    runner_up = survivors[1]["score"] if len(survivors) > 1 else 0.0
    if top >= HIGH_THRESHOLD:
        return "text_high", top, runner_up
    if top >= LOW_THRESHOLD:
        return "text_review", top, runner_up
    return "text_low", top, runner_up


# Risk beats score for ordering a queue. A person should meet the case most likely to be wrong
# first, not the case that is easiest to confirm.
def risk_rank(row):
    """The tier and the reason. Re-derivable from the written row, which is the point.

    An earlier version read review_flag, a column the writer then overwrote with this very
    reason. Reading the output back and calling this returned tier 1 for every row, so any
    later stage that re-derived the tier from the file got the wrong answer. review_flag now
    holds only rules that actually fired, and the tier and reason are recorded in their own
    columns.
    """
    if row["outcome"] == "all_candidates_vetoed":
        return 0, "every candidate removed by a meaning gate, so nothing is left to confirm"
    if row["review_flag"]:
        return 1, "a relationship rule asks for a person: %s" % row["review_flag"]
    overlap = float(row["meaning_overlap"])
    if float(row["top_score"]) >= HIGH_THRESHOLD and overlap < FULL_MEANING_OVERLAP:
        return 2, ("scores %s above the automatic gate while sharing %.4f of its meaning words"
                   % (row["top_score"], overlap))
    if row["top_vetoed_candidate"]:
        return 3, "the highest scoring candidate was vetoed on meaning: %s" % row["top_vetoed_reason"]
    margin = float(row["top_score"]) - float(row["runner_up_score"])
    if float(row["top_score"]) >= LOW_THRESHOLD and margin < NEAR_TIE_MARGIN:
        return 4, "the leader and the runner up are within %.4f" % margin
    if row["outcome"] == "text_low":
        return 5, "nothing scores above %.2f, so text settles nothing" % LOW_THRESHOLD
    # Tier 6 is reached two ways and the reason has to say which. The sentence below was an
    # unconditional catch-all describing only the first of them, so 19 of the 135 tier-6 rows,
    # CAD 72,036,869,803, printed "a high score with an identical meaning-word set" against
    # numbers that say the opposite. Exports 30049000, the largest object in the crosswalk at
    # CAD 62,379,640,484, scores 0.5660 and shares 0.5556 of its meaning words under that text.
    # Every one of the 19 arrives by outcome text_review, which is LOW <= top < HIGH by
    # construction in classify(). The tier is right on both paths; only the explanation was
    # false, which is the harder error to catch because no number ever disagrees with it.
    if float(row["top_score"]) >= HIGH_THRESHOLD and overlap >= FULL_MEANING_OVERLAP:
        return 6, "a high score with an identical meaning-word set, for spot checking"
    return 6, ("scores %s between the %.2f and %.2f gates while sharing %.4f of its meaning "
               "words, and no rule fired on it"
               % (row["top_score"], LOW_THRESHOLD, HIGH_THRESHOLD, overlap))


RANKED_COLUMNS = ["retiring_code", "span_index", "flow", "last_period", "total_value_cad",
                  "retiring_description", "rank", "candidate", "candidate_description",
                  "similarity_score", "vetoed_by", "record_overruled_gate", "review_flag",
                  "same_content_words"]

SUMMARY_COLUMNS = ["retiring_code", "span_index", "flow", "last_period", "total_value_cad",
                   "official_layer", "official_outcome", "outcome", "candidates_in",
                   "candidates_vetoed", "candidates_left", "top_candidate", "top_score",
                   "runner_up_score", "margin", "top_same_content_words", "meaning_overlap",
                   "top_vetoed_candidate", "top_vetoed_reason", "review_flag",
                   "review_flag_other_candidates",
                   "risk_tier", "risk_reason", "held_for_official_evidence"]


def build(flow, rules):
    descriptions = descriptions_by_life(flow)
    last_periods = code_last_periods(flow)
    stated_ends = code_stated_terminations(flow)
    correlated = correlated_subheadings_from_evidence()
    official = load(WORK_DIR / ("stage1_official_%s.csv" % flow))
    # Which candidates could have received the trade, derived by Stage 1a and applied here.
    # The official record's own destinations are exempt: the record outranks this reasoning and
    # ten of its named destinations legitimately carry a gap.
    continuity = {}
    # The span number travels with the retirement rather than being defaulted here. It used to be
    # read as row.get("span_index", "1") against the official file, which never carried the
    # column, so the default fired on every row. Both retirements of 3002.90.20 and 3003.31.00
    # were therefore labelled span 1, and a column that exists to tell two retirements of the
    # same code apart told them apart from nothing. A default is not a measurement.
    span_of = {}
    for r in load(WORK_DIR / ("stage1_candidates_%s.csv" % flow)):
        key = (r["retiring_code"], r["last_period"])
        continuity[key] = {c for c in r["candidates_continuous"].split(";") if c}
        span_of[key] = r["span_index"]
    ranked_rows, summaries = [], []

    for row in official:
        settled = row["outcome"] in SETTLED
        exempt = {d for d in row["official_destinations"].split(";") if d}
        key = (row["retiring_code"], row["last_period"])
        if key not in span_of:
            raise ValueError("Stage 1a did not describe the retirement %s ending %s. Refusing to "
                             "invent a span number for it." % key)
        span_index = span_of[key]
        allowed = continuity.get(key, set()) | exempt
        entries = rank_one(row, rules, descriptions, allowed, exempt,
                           ends_at=classification_ends(row, stated_ends))
        survivors = [e for e in entries if not e["vetoed_by"]]
        vetoed = [e for e in entries if e["vetoed_by"]]

        if settled:
            outcome, top, runner_up = "settled_by_record", (entries[0]["score"] if entries else 0.0), 0.0
        else:
            outcome, top, runner_up = classify(survivors)

        for position, entry in enumerate(entries, start=1):
            ranked_rows.append({
                "retiring_code": row["retiring_code"], "span_index": span_index,
                "flow": flow, "last_period": row["last_period"],
                "total_value_cad": row["total_value_cad"],
                "retiring_description": row["description"],
                "rank": position, "candidate": entry["candidate"],
                "candidate_description": wording_at(descriptions, entry["candidate"],
                                                   classification_ends(row, stated_ends)),
                "similarity_score": "%.4f" % entry["score"],
                "vetoed_by": entry["vetoed_by"],
                "record_overruled_gate": entry["record_overruled_gate"],
                "review_flag": entry["review_flag"],
                "same_content_words": "yes" if entry["same_content_words"] else "no",
            })

        top_entry = entries[0] if entries else None
        summaries.append({
            "retiring_code": row["retiring_code"], "span_index": span_index,
            "flow": flow, "last_period": row["last_period"],
            "total_value_cad": row["total_value_cad"],
            "official_layer": row["deciding_layer"], "official_outcome": row["outcome"],
            "outcome": outcome,
            "candidates_in": len(entries), "candidates_vetoed": len(vetoed),
            "candidates_left": len(survivors),
            "top_candidate": survivors[0]["candidate"] if survivors else "",
            "top_score": "%.4f" % top, "runner_up_score": "%.4f" % runner_up,
            "margin": "%.4f" % (top - runner_up),
            "top_same_content_words": ("yes" if survivors and survivors[0]["same_content_words"]
                                       else "no"),
            "meaning_overlap": "%.4f" % (
                meaning_overlap(row["description"],
                                wording_at(descriptions, survivors[0]["candidate"],
                                           row["last_period"]))
                if survivors else 0.0),
            "top_vetoed_candidate": (top_entry["candidate"]
                                     if top_entry and top_entry["vetoed_by"] else ""),
            "top_vetoed_reason": (top_entry["vetoed_by"] if top_entry and top_entry["vetoed_by"]
                                  else ""),
            # THE FLAG ON THE CANDIDATE THAT WAS CHOSEN, not on any candidate anywhere.
            #
            # This was the union over every entry, so a flag on an also-ran raised the whole
            # row's risk even when the proposal itself was clean. It went unnoticed while
            # basket_subset was the only review-action rule and fired 14 times. When
            # swapped_term arrived and fired on 451 pairs, tier 1 went from 8 rows to 94 and
            # stopped discriminating anything. A flag on a candidate nobody is proposing is not
            # a risk to the proposal; it is recorded beside it instead.
            "review_flag": survivors[0]["review_flag"] if survivors else "",
            "review_flag_other_candidates": ";".join(sorted(
                {f for e in entries[1:] if e is not (survivors[0] if survivors else None)
                 for f in e["review_flag"].split(";") if f})),
            "held_for_official_evidence": ("yes" if held_for_official_evidence(
                row, last_periods, stated_ends, correlated) else "no"),
        })
    return ranked_rows, summaries


def describe(flow, ranked, summaries):
    unsettled = [s for s in summaries if s["outcome"] != "settled_by_record"]
    print("  retirements arriving here        : %d, of which %d were already settled by the record"
          % (len(summaries), len(summaries) - len(unsettled)))
    print("  candidate pairs scored           : %d, every one carrying its score" % len(ranked))
    removed = sum(int(s["candidates_vetoed"]) for s in summaries)
    print("  candidates removed by meaning    : %d of %d (%.1f%%)"
          % (removed, len(ranked), 100.0 * removed / len(ranked) if ranked else 0))
    counts = defaultdict(int)
    for s in unsettled:
        counts[s["outcome"]] += 1
    for name in ("text_high", "text_review", "text_low", "all_candidates_vetoed"):
        if counts[name]:
            value = sum(float(s["total_value_cad"]) for s in unsettled if s["outcome"] == name)
            print("      {:<22} {:>4}  CAD {:>18,.0f}".format(name, counts[name], value))
    held = [s for s in summaries if s.get("held_for_official_evidence") == "yes"]
    if held:
        print("  held for official evidence not yet extracted: %d, CAD {:,.0f}".format(
            sum(float(s["total_value_cad"]) for s in held)) % len(held))
        print("      (a correlation table could answer these and none has been extracted. They")
        print("       sort to the end of the queue and must not be adjudicated until it has)")
    emptied = [s for s in summaries if s["outcome"] == "all_candidates_vetoed"]
    if emptied:
        print("  RETIREMENTS LEFT WITH NO CANDIDATE BY THE GATES: %d" % len(emptied))
        for s in emptied[:6]:
            print("      %s stops %s  %s" % (s["retiring_code"], s["last_period"], s["review_flag"]))
        print("      (a gate may veto. It may not conclude there is no successor, so these are")
        print("       carried to review rather than answered)")


def main():
    rules = gates.load_rules(str(RULES_FILE))
    print("Stage 1c. Meaning vetoes, then text ranks what is left.")
    print("A gate may remove a candidate. It may never add one, reorder one, or decide.")
    print()
    print("  active rules loaded              : %d (%d contrasts, %d relationship rules)"
          % (len(rules), sum(1 for r in rules if r["kind"] == gates.KIND_PHRASE_PAIR),
             sum(1 for r in rules if r["kind"] in gates.PATTERN_KINDS)))
    print("  score                            : SequenceMatcher on unexpanded text, "
          "gates on expanded text")
    print("  thresholds                       : %.2f automatic, %.2f review, both as published"
          % (HIGH_THRESHOLD, LOW_THRESHOLD))
    print()
    for flow in FLOWS:
        print("%s:" % flow)
        ranked, summaries = build(flow, rules)
        describe(flow, ranked, summaries)
        for name, rows, columns in (("ranked", ranked, RANKED_COLUMNS),
                                    ("review", summaries, SUMMARY_COLUMNS)):
            if name == "review":
                rows = [r for r in rows if r["outcome"] != "settled_by_record"]
                for r in rows:
                    tier, reason = risk_rank(r)
                    r["risk_tier"], r["risk_reason"] = tier, reason
                # Within a tier, the worst meaning disagreement leads, then the largest value.
                # Ordering tier 2 by value alone put a pair sharing nine tenths of its meaning
                # ahead of one sharing a third.
                # Held rows sort last. They are not less risky, they are not yet answerable,
                # and putting them at the end keeps a reviewer from spending judgement on a
                # question a document is about to settle.
                rows.sort(key=lambda r: (r["held_for_official_evidence"] == "yes",
                                         int(r["risk_tier"]),
                                         float(r["meaning_overlap"]) if int(r["risk_tier"]) == 2 else 0.0,
                                         -float(r["total_value_cad"])))
            destination = WORK_DIR / ("stage1_%s_%s.csv" % (name, flow))
            with open(destination, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            print("  written: %s  (%d rows)" % (destination.relative_to(PROJECT_ROOT), len(rows)))
        print()
    print("Stage 1c complete. Nothing here decided a link. It removed the impossible and")
    print("ordered the rest so the hardest case is read first.")


if __name__ == "__main__":
    sys.exit(main() or 0)
