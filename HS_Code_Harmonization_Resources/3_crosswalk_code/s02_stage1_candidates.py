"""
Stage 1a. Find every retirement and assemble the candidates, before anything decides.


Inputs:
    work/commodity_inventory_imports.csv     produced by pipeline/s01_stage0_read_source.py
    work/commodity_inventory_exports.csv

Outputs:
    work/stage1_candidates_imports.csv
    work/stage1_candidates_exports.csv
    A printed summary of the work-list and of which evidence reaches it.


WHAT THIS STAGE DOES, IN PLAIN LANGUAGE
---------------------------------------
A commodity code that stops trading before the delivery ends has retired. Something usually
took over its trade, and the crosswalk exists to say what. This stage finds every retirement
and lists what each one could possibly have become.

It decides nothing. No candidate is preferred, ranked or rejected here. Later stages consult
the official record, apply the meaning checks as vetoes, and only then let text similarity
rank whatever survives. Assembling the field and choosing from it are separate jobs, and
keeping them separate is what lets the choice be audited.


WHY THE CANDIDATE RULE IS TIERED
---------------------------------
The obvious rule, "the successor sits in the same six-digit subheading", is right for some
boundaries and wrong for others. Measured on this delivery:

  At 1997-12, 107 import codes retire and every one keeps its subheading. Canada renumbered
  beneath an unchanged international level. Same-subheading is exactly the right constraint,
  and it cuts 107 codes to roughly six candidates each.

  At 2021-12, 10 import codes retire and 8 lose their subheading outright. Same-subheading
  would return nothing at all and would look like a code that left the chapter.

So the tier is recorded rather than assumed. The narrowest tier that returns anything is
reported per row, and every tier's members are kept, so a later stage can widen when the
narrow answer turns out to be empty.


WHY A CANDIDATE IS NOT ONLY A NEWBORN CODE
--------------------------------------------
Trade can move into a code that already existed. A retiring code's trade merging into a
long-running neighbour is a real outcome and appears in this data. Restricting candidates to
codes born at the boundary would miss it. A candidate is therefore any other code still
trading after the retiring code stops, and the ones born at the boundary are flagged rather
than treated as the only possibility.


THE CANDIDATE POOL CANNOT SEE OUTSIDE CHAPTER 30
-------------------------------------------------
The delivery holds headings 3001 to 3006 and nothing else. A code whose trade moved to another
chapter has a destination this stage can never list, and it will still be handed a full field of
candidates from its own heading. Five codes are already known to have left for heading 38.22,
and the workbook settled all five as having no successor inside the chapter. This stage offers
them 17, 17, 22, 9 and 14 candidates, and not one of them is right.

Two consequences follow, and both matter more than they look.

An empty candidate list is impossible here. No later stage may read a non-empty list as evidence
that a successor exists inside the chapter, because the list is never empty.

A verdict of no successor can therefore only come from the official record. It can never be
inferred from this stage, and a similarity score computed over these candidates says nothing
about whether the right answer is among them.


WHAT WOULD MAKE THIS STAGE WRONG
---------------------------------
Stated before the numbers, so the check has something to test:

  - Treating the delivery's last month as a retirement would turn every live code into a dead
    one. A code is retired only when it stops before the delivery does.
  - Listing a code as its own successor would create a link from a code to itself.
  - Losing a retirement would remove a link nobody would notice was missing, because the
    output would still look complete.
  - Reporting a candidate that is not in the inventory would put a code into the crosswalk
    that never traded.
"""

import csv
import os as _os
import re
import sys
from collections import defaultdict
from pathlib import Path

# The decisive distinctions decide whether a relabelled number is still the same commodity, which
# is a Stage 1 question. decisive_distinctions.csv says so itself, on the punctuation row: "whether
# a twin pair is one commodity or two is a judgement for Stage 1". Only disqualifying rules are
# read, and they are read to SPLIT a span, never to choose a successor. The layer order is
# untouched: the record still decides, meaning still only ever separates, text still only ranks.
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import meaning_gates as _gates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"

FLOWS = ("imports", "exports")

# The five HS revisions the WCO correlation tables cover. A span sits at a boundary when its
# last traded month is the December before a revision, or when the delivery declares this life
# terminated in that December; money can stop before a classification does. A span at neither
# sits at no boundary, and no correlation table speaks to it. 156 of the 280 import retirements
# are in that second group. This read "170 of the 279" until 2026-08-19: 279 predates the sixth
# span split, and 170 counted the trading month alone. Findings 146 and 149.
HS_REVISIONS = {
    "200112": "1996->2002",
    "200612": "2002->2007",
    "201112": "2007->2012",
    "201612": "2012->2017",
    "202112": "2017->2022",
}

# The CBSA ten-digit concordances held in evidence/cbsa. Two boundaries, and no more. This is
# the strongest source available, because it is ten-digit and specific to Canada, and it
# reaches 89 of the 279 import retirements.
CBSA_COVERED_BOUNDARIES = {"201112", "201612"}

# The tariff schedules begin in 2005. A retirement before then has no schedule to consult, and
# reading the earliest schedule year as a birth year is a mistake this project has already made
# once, producing 195 findings that were artefacts of where the data started.
SCHEDULE_FIRST_PERIOD = "200501"


# A retired code number can be handed to different goods years later. Statistics Canada retired
# 3002900020, butter-making ferment cultures, after 2016-12, left the number empty for five
# years, and revived it in 2022-01 for the toxoid basket. The review workbook settled those as
# two different commodities, not one with a quiet patch.
#
# A code is therefore traced as one or more trading SPANS rather than a single lifespan. A
# RELABELLED resumption after a gap longer than this many months splits one span from the next,
# and each span that ends before the delivery does is its own retirement.
#
# THE WORD RELABELLED CARRIES THE RULE, and it was missing until 2026-08-19. Stage 0 groups the
# delivery into one record per code and wording, and the gap is tested between consecutive
# records, so a silence under one unchanged wording never splits a span, whatever its length.
# The delivery holds NINE such silences past the threshold, 61 to 121 months, on imports
# 3002200020, 3002900011, 3002900012, 3003399100, 3004321000 and 3004409011 and exports
# 30031000, 30033100 and 30034000. The smallest, 61 months on 3004321000, is exactly the gap
# that split the number 3002900020 into two commodities. They are kept by design rather than by
# accident: the wording is unchanged across each, and where the delivery states a termination
# it postdates the silence, so the classification stood while nothing shipped. Ricin resuming
# as Ricin is one commodity. They are disclosed in gate1/reuse_silence_disclosure.csv and
# pinned by a control, so a tenth appearing in a later delivery is seen rather than absorbed.
# What the threshold decides is therefore only the relabelled resumptions, and every published
# statement of this rule said otherwise. Finding 143.
#
# Sixty months follows the workbook's own precedent on 3002900020, whose gap was 61. Among
# RELABELLED resumptions the choice separates cleanly: the FIVE gaps it treats as reuse are 61,
# 108, 132, 142 and 350 months, and the four it treats as sparse trade are 16, 18, 23 and 34,
# so 27 months separate the largest sparse gap from the smallest reuse gap. Stated over ALL
# trading gaps that separation is false, because the nine same-worded silences above sit
# between 61 and 121; the previous form of this paragraph said no gap in the delivery falls
# between 34 and 61, which is true only of the relabelled population it was measured on.
#
# Re-measured 2026-08-18, finding 135, which corrected two earlier errors here: four values
# named for five gaps, 132 omitted, and a claim that 36 months would move an event when it
# moves nothing. Re-scoped 2026-08-19, finding 143, as above.
#
# AND THE GAP IS NO LONGER THE ONLY THING THAT SPLITS A SPAN. Since 2026-08-18 a relabelling
# that crosses a decisive distinction splits one too, which is `continues_the_span` below.
# The delivery has SIX splits: these five, and imports 3004509930 at a one-month gap where
# veterinary vitamins became human multivitamins. A reader counting gaps would find five and
# conclude one was missing. check_stage1_candidates.py pins all six by cause.
REUSE_GAP_MONTHS = 60

# A span that stops close to the delivery's own last month cannot be shown to be a retirement.
# Absence of trade at the end of the data is indistinguishable from a quiet spell, because there
# is no later evidence to settle it.
#
# Measured on this delivery, over codes that are demonstrably alive because they traded in the
# final month: a one-month silence occurs in 100 percent of their trading gaps, so it carries no
# information whatever. Two months, 33 percent of import gaps and 45 percent of export gaps.
# Six months, 6.2 and 9.2 percent. Twelve months, 2.1 and 2.7 percent.
#
# Twelve is used, and the direction of the error is deliberate. Holding a genuine retirement
# costs a delay until the next delivery resolves it. Calling a live code retired puts a false
# link in the crosswalk and asks a person to adjudicate an event that never happened. The first
# error is cheap and self-correcting; the second is neither.
#
# 3004.41.00.00 is why this exists. It last traded 2026-05, one month before the delivery ends,
# and arrived in the queue as a retirement worth CAD 8,250,035 with a different substance
# proposed as its successor.
TAIL_MONTHS_NOT_YET_DECIDABLE = 12

# WHAT MAKES A STOPPAGE A RETIREMENT AT ALL.
# Intends  "the classification ended".
# Computes "Statistics Canada declared the line terminated, or the number was later handed to
#           different goods".
#
# Every rule above this one asks how long a code has been quiet. None of them asks whether
# anything in the record says the line ended, and those are different questions. A commodity that
# merely stops being traded has not been withdrawn from the tariff, and a crosswalk that gives it
# a successor asserts a transfer that never happened. This is the same error as the concordance
# defect of 2026-08-11 and as M4 and M6: keying on the month the money stopped rather than the
# month the record ends the classification.
#
# The evidence is Statistics Canada's own "(Terminated YYYY-MM)" note, parsed in Stage 0. Measured
# on this delivery, 300 of the 319 retirements carry one. Four more carry no note but are a reused
# number, whose earlier life demonstrably ended because the number now holds different goods:
# 30049010 was "Medicaments nes, in dosage, for human use" until 1988-12 and is cannabis from
# 2018-02. The remaining 15, CAD 345,974,865, carry neither and had been reaching the workbook as
# decisions for a person to make.
#
# THE GAP, AND WHERE IT MATTERS. The note is not written everywhere, so its absence is not
# uniformly good evidence. Coverage of spans that end before the delivery does runs 94 per cent on
# 2017-2021 imports and 62 to 85 per cent earlier, but on 2000-2011 exports it is 4 of 16. Absence
# is therefore weak evidence in that window and sound evidence from 2012 on. Every one of the 15
# stops in 2020 or later and not one is pre-2012. That is measured, not assumed, and
# check_stage1_candidates.py pins it, so a later delivery that puts one of these rows in the weak
# window fails loudly instead of inheriting a rule its evidence does not support.
RETIREMENT_DECLARED = "declared"
RETIREMENT_CODE_REUSED = "code_reused"
RETIREMENT_TRADE_CEASED_ONLY = "trade_ceased_only"

# The era from which a missing termination note is sound evidence that the line still stands.
# Below it the note is too often absent for its absence to mean anything.
TERMINATION_NOTE_RELIABLE_FROM = "201201"

# A code does not record a shipment the instant it comes into force. 30043220 retired 1988-11
# and the aggregate that replaced it, 30043200, first traded 1989-01, one month past the
# boundary. With no grace at all that reads as "this code did not exist" and the retirement is
# left with nothing at all to link to.
#
# The tariff can settle this only from 2005. Where it can testify, of 48 candidates with a gap
# of 1 to 12 months it shows 22 already in force, 46 per cent, while of 13 with a longer gap it
# shows 1, 8 per cent. Short gaps are frequently a reporting lag and long ones essentially never
# are.
#
# Twelve months is a judgement informed by that, not a value derived from it. The sample is 61
# cases, and 46 per cent is a floor rather than a rate, because absence from the tariff proves
# nothing about a statistical breakout it never lists. Anything beyond a year is where the
# evidence stops supporting the benefit of the doubt.
CONTINUITY_GRACE_MONTHS = 12


def add_months(period, count):
    total = int(period[:4]) * 12 + int(period[4:]) - 1 + count
    return "%04d%02d" % (total // 12, total % 12 + 1)


def period_to_months(period):
    return int(period[:4]) * 12 + int(period[4:])


def next_period(period):
    """The month after a YYYYMM period. 199712 gives 199801."""
    year, month = int(period[:4]), int(period[4:])
    return "%04d%02d" % (year + 1, 1) if month == 12 else "%04d%02d" % (year, month + 1)


_DISQUALIFYING = None


def crosses_a_decisive_distinction(before_text, after_text):
    """True when consecutive lives of one code sit on opposite sides of a decisive distinction.

    A trading gap is not the only way one number stops carrying one commodity and starts
    carrying another. Statistics Canada also relabels a number in place, and where the relabel
    crosses a distinction this project has declared decisive, the goods changed even though the
    money never stopped.

    Only DISQUALIFYING rules are consulted. A review rule may not decide anything, here or
    anywhere, and a rewording must never split a span: 106 of the 107 contiguous life boundaries
    in this delivery are rewordings, and splitting on any description change would turn them all
    into retirements needing an answer.
    """
    global _DISQUALIFYING
    if _DISQUALIFYING is None:
        path = PROJECT_ROOT / "decisions" / "decisive_distinctions.csv"
        rules = _gates.load_rules(str(path)) if path.exists() else []
        # load_rules has already dropped anything not active and does not carry the status
        # column through, so filtering on status here would empty the list silently. That
        # already happened once in families.py and the comment there says so.
        _DISQUALIFYING = [r for r in rules if str(r.get("action", "")).strip() == "disqualify"]
    return any(_gates.rule_fires(rule, before_text, after_text) for rule in _DISQUALIFYING)


def trading_spans(records):
    """Merge a code's records into trading spans, splitting where the goods changed.

    Records overlap and abut, so they are merged first. A span ends where the NEXT RECORD fails
    to continue it, at either of two events: a record arriving after a gap longer than
    REUSE_GAP_MONTHS, which is the number being reused after lying empty, or a relabel that
    crosses a decisive distinction, which is the number being handed to different goods without
    a break in trade. The test runs between records, so a silence inside one record, meaning
    under one unchanged wording, never ends a span whatever its length; the nine such silences
    in this delivery are disclosed in gate1/reuse_silence_disclosure.csv. Finding 143.

    THE SECOND CASE WAS MISSING AND IT IS THIS PROJECT'S OWN ERROR CLASS. 3004.50.99.30 traded
    as "Vitamins & their derivs, nes, for vet use" to 1989-12 and as "Multivitamins not mixed
    with o supplements, for human use" from 1990-01, with no gap at all. Grouped on the interval
    alone the two became one span running 1988-01 to 1997-12, the summed value of both lives, and
    the description of the LATER one. Stage 2 then answered one retirement, and Stage 3 routed
    both lives through it, so a veterinary record acquired a human terminal at 3004.50.00.19.
    That is keying on the month the money stopped rather than the month the record ended the
    classification, which the findings register carries four times over.
    """
    return [(run[0]["first_period"], max(r["last_period"] for r in run))
            for run in span_runs(records)]


def continues_the_span(before, after):
    """True when `after` is the same commodity carrying on, rather than a new span.

    THIS IS THE ONE PLACE THAT ANSWERS THE QUESTION. Stages 3, 4, 5 and the queue builder each
    used to answer it themselves, importing REUSE_GAP_MONTHS and restating the rule around it,
    and each said in its own comment that it imported rather than restated so the stages could
    not disagree. Sharing the threshold while copying the rule is not sharing the rule: when the
    relabel test was added here on 2026-08-17 the other four kept the old answer, Stage 4 could
    no longer place a settled succession on a span, and the build stopped. That is finding 103's
    shape returning from the other direction, and it is why this predicate is now public and the
    copies are gone.

    `before` is the life that most recently extended the span, `after` the next one.
    """
    gap = period_to_months(after["first_period"]) - period_to_months(before["last_period"])
    if gap > REUSE_GAP_MONTHS:
        return False
    return not crosses_a_decisive_distinction(before["description"], after["description"])


def span_runs(records):
    """One code's records, grouped into the runs that each make a trading span.

    Everything else about spans is derived from this: the intervals Stage 1a retires on, the
    nodes Stage 4 builds families over, and the life-to-span map both need. Returning the runs
    rather than the intervals is what lets a caller keep the records, which Stage 4 needs and
    used to recompute.
    """
    ordered = sorted(records, key=lambda r: (r["first_period"], r["last_period"]))
    runs = [[ordered[0]]]
    for record in ordered[1:]:
        run = runs[-1]
        # The gap is measured from the furthest the run has reached, not from the last record
        # read, because records overlap. The wording is taken from the last record read, because
        # the question is where the classification ended.
        previous = {"last_period": max(r["last_period"] for r in run),
                    "description": run[-1]["description"]}
        if continues_the_span(previous, record):
            run.append(record)
        else:
            runs.append([record])
    return runs


CBSA_DIR = PROJECT_ROOT / "evidence" / "cbsa"


def span_descriptions(records):
    """Each trading span with the wording it was born with AND the one it ended on.

    Both are needed and they are not interchangeable. A retiring line is judged on what it was
    called when it STOPPED, which is what a successor has to account for. A candidate is judged
    on what it is called when it STARTS receiving, which is what the trade moved into. Statistics
    Canada rewords a line in place often enough that the two differ.
    """
    out = []
    for run in span_runs(records):
        first = run[0]["first_period"]
        last = max(r["last_period"] for r in run)
        born = next(r["description"] for r in run if r["first_period"] == first)
        ended = next(r["description"] for r in run if r["last_period"] == last)
        out.append((first, last, born, ended))
    return out


def tariff_existence():
    """Which codes the tariff schedule shows existing in each year, 2005 onward.

    THE INVENTORY RECORDS TRADE. THE SCHEDULE RECORDS EXISTENCE, AND THEY ARE NOT THE SAME.
    A new code routinely records its first shipment a month or two after it comes into force.
    Reading first-traded as first-existing removed 124 import and 40 export candidates that were
    in the tariff at the boundary and simply had not traded yet, 30021100 among them, in force
    for 2017 and first traded 2017-02.

    Presence here proves existence. ABSENCE PROVES NOTHING, because the tariff lists tariff items
    and Statistics Canada adds statistical breakouts beneath them that the tariff never names.
    So this is used only to RESCUE a candidate that trade alone would have excluded, and never to
    exclude one. The union can only widen the field, which is the safe direction for a filter
    that sits upstream of everything.

    Schedules begin in 2005. Before that, trade remains the only available proxy for existence,
    and that limitation is stated rather than hidden.
    """
    digits = lambda text: re.sub(r"\D", "", text or "")
    best = {}
    for path in sorted(CBSA_DIR.glob("sched_ch30_*.csv")):
        match = re.search(r"sched_ch30_(\d{4})(?:-(\d+))?\.csv$", path.name)
        if not match:
            continue
        year, amendment = int(match.group(1)), int(match.group(2) or 0)
        if year not in best or amendment > best[year][0]:
            best[year] = (amendment, path)
    existence = {}
    for year, (_amendment, path) in best.items():
        with open(path, encoding="utf-8-sig", newline="") as handle:
            codes = set()
            for row in csv.DictReader(handle):
                for value in (digits(row.get("hs10") or ""), digits(row.get("tariff_item8") or "")):
                    if len(value) in (8, 10):
                        codes.add(value)
        existence[year] = codes
    return existence


def read_inventory(flow):
    path = WORK_DIR / ("commodity_inventory_%s.csv" % flow)
    if not path.exists():
        raise SystemExit("Stage 1a stopped: %s not found. Run s01_stage0_read_source.py first." % path)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def code_lifespans(records):
    """One entry per code: when it started, when it stopped, what it was worth, how described."""
    grouped = defaultdict(list)
    for record in records:
        grouped[record["hs_code"]].append(record)
    lifespans = {}
    for code, rows in grouped.items():
        last = max(r["last_period"] for r in rows)
        lifespans[code] = {
            "first_period": min(r["first_period"] for r in rows),
            "last_period": last,
            "total_value_cad": round(sum(float(r["total_value_cad"]) for r in rows), 2),
            # The description in force when the code stopped, which is the one a successor
            # should be compared against.
            "description": next(r["description"] for r in rows if r["last_period"] == last),
            "records": len(rows),
            # THE SPANS, NOT ONLY THE OUTER ENVELOPE.
            #
            # A reused code number has two lives, and collapsing them to one min and one max
            # describes neither. 3002.90.20 traded 1988-01 to 1988-12 as veterinary blood
            # products and again 2000-10 to 2016-11 as Saxitoxin. Read as a single lifespan it
            # looks alive from 1988 to 2016, so its retired 1988 span was offered as a successor
            # to the code that retired beside it, and each of the pair was proposed as the
            # other's successor. The span machinery exists to keep those apart, and reading only
            # the envelope here walked straight past it.
            "spans": trading_spans(rows),
            # THE WORDING EACH SPAN IS BORN WITH, kept beside the spans themselves.
            #
            # "description" above is the one in force when the code STOPPED, which is the right
            # wording to judge a retiring line by and the wrong one to judge a newborn line by.
            # A candidate is weighed on what it is called when it starts receiving trade. A
            # recycled number's second life is named differently from its first, so reading the
            # envelope would compare a 2022 line against a 1988 name. Both wordings are needed,
            # so both are kept.
            "span_descriptions": span_descriptions(rows),
        }
    return lifespans


def receiving_span(candidate_spans, stopped, limit):
    """The one span of a candidate that could actually have received this trade, or None.

    A span qualifies when it is still running after the retirement AND had begun by the end of
    the grace window. Both conditions must hold of the SAME span. Testing them against a code's
    outer envelope lets an early span satisfy one and a much later reuse satisfy the other, which
    is how a code that retired in the same month as its predecessor became its successor.
    """
    qualifying = [(first, last) for first, last in candidate_spans
                  if last > stopped and first <= limit]
    # If more than one qualifies, the earliest is the one that received the trade.
    return min(qualifying) if qualifying else None


def carve_out_candidates(code, lifespans, stopped, boundary, already):
    """Codes born at this boundary, outside the rung, named for something this line names.

    WHY THE RUNG ALONE IS NOT ENOUGH.

    The ladder below narrows to the tightest rung that returns anything, and widens only when
    the narrow answer is EMPTY. That is right when a subheading is renumbered beneath an
    unchanged international level, which is most of this delivery. It is wrong when a subheading
    survives while part of its content is carved out into a NEW subheading, because the rung
    still returns members and never widens, so the receiving line is never a candidate and no
    later layer can rescue it: the official record only vetoes, it cannot add.

    Measured on this delivery, both at 2021-12, the HS2022 restructure of heading 3002:

      3002900010 "Toxins, toxoids, antitoxins, viruses, bacteriophage and bacterial lysates"
      retires. Subheading 300290 survives through .20 and .90, so the rung stays same_subheading
      and 3002490020 "Toxins and similar products", born 202201, sits among 111 codes never
      considered. The queue row says "a list lost an item" and cannot say where it went.

      3002900050 "Micro-organisms cultures" retires to the residual 3002900090 while
      3002490010 "Cultures, of micro-organisms (excluding yeasts) and similar products" is born
      at the same boundary, unseen. CAD 257,772,832.

    Text similarity would not have found either. 3002900020 scores 0.9466 against the toxin
    line because it keeps five of its six terms; the line that took the sixth scores far lower.
    So this rung is structural, not textual: it asks whether a NEWBORN line is NAMED for
    something the retiring line names, using the leading clause only, which is what a tariff
    line is about. It ADDS candidates and never removes any, so it cannot lose a link that the
    ladder already found, and everything it adds is disclosed in its own column.
    """
    import families as _fam
    mine = _fam._content_words(_wording_at(lifespans[code], stopped))
    if not mine:
        return []
    # WHAT MAKES A TERM A CARVE-OUT RATHER THAN A FAMILY RESEMBLANCE.
    #
    # The first version of this rung asked only whether a newborn line shared a word with the
    # retiring line's leading clause. That fired on 126 of 280 import rows, because Chapter 30
    # lines overwhelmingly lead on "medicaments", "blood", "dressings" and a dozen other words
    # that say what the chapter is, not what the line is.
    #
    # A term has been CARVED OUT of a subheading only when the subheading stops leading on it.
    # So the test is comparative: the newborn's head noun must be one the retiring line names,
    # AND NOTHING LEFT IN THE CODE'S OWN RUNG may still lead on it. If a sibling still leads on
    # the term, the term did not leave, and the rung is the right place to look. This is what
    # separates 3002900010 -- whose rung keeps 3002900020 "Toxoids..." and 3002900090 "Human
    # blood...", neither leading on toxins -- from 3004909915 "Medicaments, for human use,
    # acting on the nervous system", whose rung is full of lines still leading on medicaments.
    #
    # AND THE MATCH MUST RUN BOTH WAYS. Testing only the newborn's head noun against the
    # retiring line fired on 71 rows, because a head noun is often a QUALIFIER: "Human
    # blood;anml blood therap/prophltc/diag uses" heads on "human", which every "for human use"
    # line in the chapter contains, so one blood line was offered to forty medicaments. Requiring
    # each line's head noun to appear in the other's wording makes the two lines agree about what
    # they are about. 3002900010 leads on toxins and 3002490020 contains toxins; 3002490020 leads
    # on toxins and 3002900010 contains toxins. A medicament leading on "analgesics" finds no
    # analgesics in a blood line, and the pair is dropped.
    my_head = _head_noun(_wording_at(lifespans[code], stopped))
    rung_heads = {_head_noun(_wording_covering(lifespans[c], boundary)) for c in already}
    rung_heads.discard("")
    out = []
    for other, life in lifespans.items():
        if other == code or other in already or other[:2] != code[:2]:
            continue
        born = next((d for first, _last, d, _ended in life.get("span_descriptions", ())
                     if first == boundary), None)
        if born is None:
            continue
        head = _head_noun(born)
        if not head or head not in mine or head in rung_heads:
            continue
        if not my_head or my_head not in _fam._content_words(born):
            continue
        out.append(other)
    return sorted(out)


def _head_noun(text):
    """The first content word of the leading clause: what the line is ABOUT.

    A tariff line names its subject first and qualifies it afterwards. "Toxins and similar
    products" is about toxins; "Human blood;animal blood therap/diag,etc;antisera,etc" is about
    blood and merely mentions the rest.
    """
    import families as _fam
    clause = (text or "").split(",")[0].split(";")[0]
    keep = _fam._content_words(clause)
    for raw in re.findall(r"[a-z]+", clause.lower()):
        word = _fam.SHORTHAND.get(raw, raw)
        if word in keep:
            return word
    return ""


def _wording_covering(life, period):
    """The wording of the span in force at this month, or the envelope if none covers it."""
    for first, last, born, _ended in life.get("span_descriptions", ()):
        if first <= period <= last:
            return born
    return life.get("description", "")


def _wording_at(life, stopped):
    """The wording in force at the span that ended here, not the code's outer envelope."""
    for _first, last, _born, ended in life.get("span_descriptions", ()):
        if last == stopped:
            return ended
    return life.get("description", "")


def assemble_candidates(code, lifespans, stopped, existence):
    """Every other code still trading after this span stops, grouped by how close it sits.

    A code is never its own candidate, which also settles the reused-number case: when
    3002900020 retires in 2016 and the same number returns in 2022, the later span is not
    offered as the successor of the earlier one. The review workbook settled those as two
    different commodities.
    """
    boundary = next_period(stopped)
    # Alive means one of the code's own spans outlives this retirement, not that the code number
    # was in use again at some later date under different goods.
    alive_after = [c for c, v in lifespans.items()
                   if c != code and any(last > stopped for _first, last in v["spans"])]

    # BOTH ENDS OF THE WINDOW, NOT ONE. Until 2026-08-11 this stage required a candidate to
    # survive the retirement and never required it to have existed at it, so a code born in 2015
    # was offered as a successor to one that died in 1989. That is not a weak candidate. It is
    # not a candidate: the trade moved in 1989 and that code did not yet exist to receive it.
    #
    # A candidate is continuous when it was already trading at the retirement, which is a merge,
    # or begins the month after, which is a succession. Anything later leaves months in which the
    # trade existed and the successor did not, and an unbroken series is the whole point of a
    # crosswalk.
    #
    # Measured before the rule was added: 1,027 of 3,489 import candidate pairs and 53 of 210
    # export pairs could not have received the trade at the time, and 35 proposals leave a gap
    # while a continuous candidate was available, one of them by 312 months.
    # Continuous by trade, or shown by the tariff to have existed already, or within the grace
    # window below.
    in_force = existence.get(int(boundary[:4]), set())
    limit = add_months(boundary, CONTINUITY_GRACE_MONTHS)
    # Both halves of the test must hold of one span. The tariff rescue is unchanged: presence
    # proves existence and may widen the field, absence never narrows it.
    continuous = [c for c in alive_after
                  if receiving_span(lifespans[c]["spans"], stopped, limit) or c in in_force]

    # CONTINUITY IS DERIVED HERE AND APPLIED IN STAGE 1C, NOT HERE.
    #
    # It was briefly a filter at this stage and that was wrong, for a reason that took three
    # measurements to see. This stage can never PROVE non-existence: absence of trade is not
    # proof, and absence from the tariff is not either, because the tariff omits the statistical
    # breakouts Statistics Canada adds beneath its items. Every exclusion here would therefore be
    # inferential, and this is the one place where inference cannot be undone, since every later
    # layer only narrows further.
    #
    # Measured: filtering here removed 1,018 candidates from pre-2005 rows that have no schedule
    # to check them against and no official source that will ever speak, so nothing downstream
    # could have corrected it.
    #
    # So the ladder runs over every surviving code, as it did before, and continuity travels
    # alongside as a recorded property. Stage 1c vetoes on it, after the official record has
    # spoken, with a reason attached to each candidate. Deriving it is structural and belongs
    # here. Acting on it is judgement and belongs there.
    pool = alive_after
    same_subheading = [c for c in pool if c[:6] == code[:6]]
    same_heading = [c for c in pool if c[:4] == code[:4]]
    # The chapter rung applies a real two-digit filter. An earlier version named this rung
    # same_chapter and applied no filter at all, so it held every surviving code. That was
    # accidentally true, because the delivery holds Chapter 30 and nothing else, and it would
    # have become false the moment another chapter arrived. The rung below it, any_alive,
    # is the one that holds everything. While the delivery stays inside Chapter 30 the two
    # are identical, and a control asserts exactly that.
    same_chapter = [c for c in pool if c[:2] == code[:2]]
    born_at_boundary = [c for c in pool
                        if any(first == boundary for first, _last in lifespans[c]["spans"])]
    # The narrowest rung that returns anything at all. Recorded, never assumed.
    # Recorded so the artefact can disclose it. Narrowing to the tightest rung is deliberate and
    # usually right, but it is an inference, and on 220 retirements where no official source
    # speaks it is the ONLY thing standing between a code and consideration. Until 2026-08-11 the
    # codes it dropped appeared nowhere: not proposed, not runner-up, not removed, because nothing
    # removed them. They were never candidates. A reader cannot weigh what they cannot see.
    if same_subheading:
        tier, narrowest = "same_subheading", same_subheading
    elif same_heading:
        tier, narrowest = "same_heading", same_heading
    elif same_chapter:
        tier, narrowest = "same_chapter", same_chapter
    elif pool:
        tier, narrowest = "any_alive", pool
    else:
        tier, narrowest = "none", []
    # THE CARVE-OUT RUNG SITS BESIDE THE LADDER RATHER THAN ON IT.
    #
    # Putting it on the ladder would mean choosing between it and the rung, and the ladder's
    # whole design is that the narrowest rung wins. This is not a narrower rung, it is a rung
    # the ladder cannot reach: a line born in a DIFFERENT subheading at this very boundary,
    # named for something the retiring line names. It is added to what gets considered and
    # recorded in its own column, so the rung the ladder chose is still disclosed unchanged in
    # narrowest_tier and narrowest_rung_only. It only ever ADDS.
    carve_out = [c for c in carve_out_candidates(code, lifespans, stopped, boundary,
                                                 set(narrowest)) if c in set(pool)]
    considered = sorted(set(narrowest) | set(carve_out))
    return {
        "boundary": boundary,
        "same_subheading": sorted(same_subheading),
        "same_heading": sorted(same_heading),
        "same_chapter": sorted(same_chapter),
        "any_alive": sorted(pool),
        "continuous": sorted(continuous),
        "n_continuous": len(continuous),
        "n_alive_after": len(alive_after),
        "born_at_boundary": sorted(born_at_boundary),
        "narrowest_tier": tier,
        "narrowest": considered,
        "narrowest_rung_only": sorted(narrowest),
        "carve_out": sorted(carve_out),
        "outside_narrowest": sorted(set(pool) - set(considered)),
    }


def subheading_survives(code, stopped, lifespans):
    """True when some other code under the same subheading is still trading afterwards."""
    return any(c != code and c[:6] == code[:6] and v["last_period"] > stopped
               for c, v in lifespans.items())


def build(flow, existence):
    records = read_inventory(flow)
    lifespans = code_lifespans(records)
    delivery_end = max(v["last_period"] for v in lifespans.values())

    grouped = defaultdict(list)
    for record in records:
        grouped[record["hs_code"]].append(record)

    rows = []
    for code in sorted(lifespans):
        life = lifespans[code]
        spans = trading_spans(grouped[code])
        for index, (span_first, span_last) in enumerate(spans, start=1):
            # A span is retired only when it stops before the delivery does. Treating the
            # delivery's own last month as a retirement would turn every live code into a dead
            # one. A code with two spans can retire twice, and the earlier retirement was
            # invisible until 2026-08-10.
            if span_last == delivery_end:
                continue
            # Recorded, never dropped. The row stays in the work-list carrying a reason, so the
            # count reconciles and the next delivery can settle it.
            silence = period_to_months(delivery_end) - period_to_months(span_last)
            stopped = span_last
            span_records = [r for r in grouped[code]
                            if span_first <= r["first_period"] and r["last_period"] <= span_last]
            # The termination note belongs to THIS span's own final record, never to the code. A
            # reused number carries two lives and the earlier one's note says nothing about the
            # later one. Read the same way the description is read, four lines below.
            # AND THE NOTE MUST BE ABOUT THIS LIFE. Statistics Canada attaches the note to the
            # commodity string, so a recycled number carries it on every life it ever had:
            # exports 30029020's 1988 blood line reads "(Terminated 2016-12)", which describes the
            # Saxitoxin line that replaced it twelve years later. Stage 0 works out whose note it
            # is and this reads the answer rather than re-deriving it. Finding 105.
            declared = next((r.get("stated_termination") or "" for r in span_records
                             if r["last_period"] == stopped
                             and r.get("stated_termination_is_this_life") != "no"), "")
            if declared:
                retirement_basis = RETIREMENT_DECLARED
            elif index < len(spans):
                # A later span exists, so the number was handed on. The earlier commodity ended
                # whether or not anyone wrote it down.
                retirement_basis = RETIREMENT_CODE_REUSED
            else:
                retirement_basis = RETIREMENT_TRADE_CEASED_ONLY
            # THE MONTH THE CLASSIFICATION ENDED, as opposed to the month money stopped. Where
            # the delivery declares a termination for this life, the declaration is the end of
            # the line, and money can stop months or years earlier. No declared month in this
            # delivery precedes the last trade, and the guard keeps that true by construction.
            # Stage 1b matches the concordance this way and Stage 1c holds this way; the flag
            # columns below were the remaining place still reading the trading month alone.
            # Finding 146.
            classification_end = declared if declared and declared >= stopped else stopped
            # TWELVE MONTHS IS THE WRONG YARDSTICK FOR A SPARSE CODE. The window is calendar
            # time, but what silence means depends on how often the code ever traded. 3003.42.00
            # traded 4 months out of 65 and has already survived a 49-month gap, so 21 months of
            # quiet says nothing; 3003.31.00 has survived 106. Both were being offered for
            # decision as retirements. A code is only silent enough to call when it has been
            # quiet LONGER than it has ever been quiet before and come back.
            #
            # ONLY WHERE SILENCE IS THE ONLY EVIDENCE. That sentence is the rule and both of its
            # cases are now enforced. A retirement at an HS revision boundary is established by
            # the tariff: the line was abolished, and the code being quiet afterwards is a
            # consequence rather than the finding. A retirement the delivery DECLARES, or one a
            # reused number proves, is established the same way, by the record rather than by
            # the gap, so only a trade_ceased_only span can be held. Until 2026-08-19 the
            # declared case was not enforced: imports 3002.90.00.12, Saxitoxin, declared
            # terminated 2016-12 and named by the concordance, sat flagged too_recent_to_call
            # 116 months after its last trade, because the flag read only the trading gap.
            # Finding 147.
            quiet_before = max((int(r.get("longest_quiet_months") or 0)
                                for r in grouped[code]), default=0)
            too_recent = (retirement_basis == RETIREMENT_TRADE_CEASED_ONLY
                          and (silence <= TAIL_MONTHS_NOT_YET_DECIDABLE
                               or (span_last not in HS_REVISIONS
                                   and silence <= quiet_before)))
            cand = assemble_candidates(code, lifespans, span_last, existence)
            rows.append({
                "too_recent_to_call": "yes" if too_recent else "no",
                "retirement_basis": retirement_basis,
                "months_before_delivery_end": (period_to_months(delivery_end)
                                               - period_to_months(span_last)),
                "retiring_code": code,
                "span_index": index,
                "span_count": len(spans),
                "span_first_period": span_first,
                    "flow": flow,
                "heading": code[:4],
                "subheading": code[:6],
                "last_period": stopped,
                "boundary": cand["boundary"],
                # The value and wording of THIS span, not of the whole code. A reused number
                # carries two commodities, and attributing one span's trade to the other would
                # overstate both.
                "total_value_cad": "%.2f" % round(
                    sum(float(r["total_value_cad"]) for r in span_records), 2),
                "description": next((r["description"] for r in span_records
                                     if r["last_period"] == stopped), life["description"]),
                "subheading_survives": "yes" if subheading_survives(code, stopped, lifespans) else "no",
                # A UNION, NEVER A REPLACEMENT: the trading month or the declared month, so no
                # span that sat at a boundary can leave it. Keyed on the trading month alone,
                # a line that went quiet before its revision read "no boundary" while the
                # concordance named its successor at that very revision; twelve published rows
                # said adjudicated-yes and boundary-no at once. Stage 1c states the same union
                # for its hold and calls the trading-month reading the concordance lookup's old
                # defect in a third place; this was the fourth. Finding 146.
                "at_hs_revision_boundary": ("yes" if (stopped in HS_REVISIONS
                                                      or classification_end in HS_REVISIONS)
                                            else "no"),
                "wco_table": (HS_REVISIONS.get(stopped)
                              or HS_REVISIONS.get(classification_end, "")),
                "cbsa_concordance_covers": ("yes" if (stopped in CBSA_COVERED_BOUNDARIES
                                                      or classification_end
                                                      in CBSA_COVERED_BOUNDARIES)
                                            else "no"),
                "tariff_schedule_covers": "yes" if stopped >= SCHEDULE_FIRST_PERIOD else "no",
                "narrowest_tier": cand["narrowest_tier"],
                "narrowest_count": len(cand["narrowest"]),
                "n_same_subheading": len(cand["same_subheading"]),
                "n_same_heading": len(cand["same_heading"]),
                "n_same_chapter": len(cand["same_chapter"]),
                "n_any_alive": len(cand["any_alive"]),
                "n_continuous": cand["n_continuous"],
                "n_alive_after_ignoring_continuity": cand["n_alive_after"],
                "candidates_continuous": ";".join(
                    c for c in cand["narrowest"] if c in set(cand["continuous"])),
                "n_born_at_boundary": len(cand["born_at_boundary"]),
                "n_carve_out": len(cand["carve_out"]),
                "candidates_carve_out": ";".join(cand["carve_out"]),
                "candidates_narrowest": ";".join(cand["narrowest"]),
                "candidates_outside_narrowest": ";".join(cand["outside_narrowest"]),
                "candidates_born_at_boundary": ";".join(cand["born_at_boundary"]),
            })
    rows.sort(key=lambda r: (r["retiring_code"], r["last_period"]))
    return rows, lifespans, delivery_end


COLUMNS = ["too_recent_to_call", "retirement_basis",
           "months_before_delivery_end", "retiring_code", "span_index", "span_count", "span_first_period",
           "flow", "heading", "subheading", "last_period", "boundary",
           "total_value_cad", "description", "subheading_survives", "at_hs_revision_boundary",
           "wco_table", "cbsa_concordance_covers", "tariff_schedule_covers",
           "narrowest_tier", "narrowest_count", "n_same_subheading", "n_same_heading",
           "n_same_chapter", "n_any_alive", "n_continuous",
           "n_alive_after_ignoring_continuity", "candidates_continuous",
           "n_born_at_boundary", "n_carve_out", "candidates_narrowest",
           "candidates_outside_narrowest",
           "candidates_born_at_boundary", "candidates_carve_out"]


def describe(flow, rows, delivery_end):
    total_value = sum(float(r["total_value_cad"]) for r in rows)
    print("  delivery ends                     : %s" % delivery_end)
    print("  retirements to be linked          : %d" % len(rows))
    print("  value carried by them             : CAD {:,.0f}".format(total_value))
    counts = sorted(int(r["narrowest_count"]) for r in rows)
    print("  candidates per retirement, median : %d" % (counts[len(counts) // 2] if counts else 0))

    tiers = defaultdict(int)
    for r in rows:
        tiers[r["narrowest_tier"]] += 1
    print("  narrowest tier that returns anything:")
    for tier in ("same_subheading", "same_heading", "same_chapter", "any_alive", "none"):
        if tiers[tier]:
            share = 100.0 * tiers[tier] / len(rows)
            print("      %-16s %4d  (%.0f%%)" % (tier, tiers[tier], share))

    print("  official evidence reaching them:")
    for label, key in (("CBSA ten-digit concordance", "cbsa_concordance_covers"),
                       ("tariff schedule, 2005 on", "tariff_schedule_covers"),
                       ("at an HS revision boundary", "at_hs_revision_boundary")):
        n = sum(1 for r in rows if r[key] == "yes")
        value = sum(float(r["total_value_cad"]) for r in rows if r[key] == "yes")
        print("      {:<28} {:>4} of {}  CAD {:,.0f}".format(label, n, len(rows), value))

    stranded = [r for r in rows if r["narrowest_tier"] == "none"]
    if stranded:
        print("  RETIREMENTS WITH NO CANDIDATE AT ALL: %d" % len(stranded))
        for r in stranded[:8]:
            print("      %s stops %s  CAD %s  %s"
                  % (r["retiring_code"], r["last_period"],
                     format(round(float(r["total_value_cad"])), ","), r["description"][:44]))
        print("      (a code with no candidate left the chapter. That is a finding, not an error,")
        print("       and it is what the cross-chapter exits to heading 38.22 look like)")


def main():
    print("Stage 1a. Finding every retirement and assembling its candidates.")
    print("Nothing is decided here. No candidate is preferred, ranked or rejected.")
    print()
    WORK_DIR.mkdir(exist_ok=True)
    existence = tariff_existence()
    print("  tariff vintages read for existence: %d, %d to %d"
          % (len(existence), min(existence), max(existence)))
    print()
    for flow in FLOWS:
        print("%s:" % flow)
        rows, _lifespans, delivery_end = build(flow, existence)
        describe(flow, rows, delivery_end)
        destination = WORK_DIR / ("stage1_candidates_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()
    print("Stage 1a complete. Every retirement has a field of candidates and no successor.")


if __name__ == "__main__":
    sys.exit(main() or 0)
