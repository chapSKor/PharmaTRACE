"""
Stage 1b. Let the official record speak, in order, before anything else is consulted.


Inputs:
    work/stage1_candidates_{imports,exports}.csv    produced by pipeline/s02_stage1_candidates.py
    evidence/cbsa/concordance_2011_2012_ch30.csv    Canada's own ten-digit concordance
    evidence/cbsa/concordance_2016_2017_ch30.csv
    evidence/cbsa/sched_ch30_<year>.csv             22 tariff vintages, 2005 to 2025
    decisions/official_constraint_sets.csv          the five bounded export answers

Outputs:
    work/stage1_official_{imports,exports}.csv
    A printed summary of what each layer decided and what it left alone.


THE ORDER, AND WHY IT IS THIS ORDER
------------------------------------
The question a crosswalk answers is where Canada recorded the trade after a code retired. The
sources are consulted in the order of how directly they answer that question.

  1. Canada's ten-digit concordance. It names the successor outright, at the same level of
     detail the trade is recorded in, for the country whose trade this is.
  2. The international correlation together with the tariff schedule. The correlation works at
     six digits and the schedule carries it down to ten.
  3. The bounded sets, where the record cannot name a successor but does limit it to a short
     list. These sit above the schedule because naming a set of destinations is a stronger
     statement than ruling one out.
  4. The schedule alone. It cannot name a successor. It can rule one out by showing that the
     whole subheading no longer exists, and only that. See the note on the two numbering
     systems in the schedule loader for why nothing finer is sound.

Nothing below the official record appears in this stage. Meaning checks and text similarity come
afterwards and can only narrow what is left. A layer here can decide, or narrow, or say nothing.
It can never widen what a layer above it decided.


THE SECOND LAYER IS NO LONGER EMPTY, 2026-08-14
------------------------------------------------
It was declared and empty from the day this stage was written, because the correlation tables
existed here only as five PDFs. They are now extracted to evidence/wto/wto_ch30_pairs.csv by
evidence/wto/extract_wto_pairs.py, and this layer reads them. It reaches 25 retirements,
CAD 24,796,853,123: 6 constrained and 4 forced on imports, 4 forced on exports, 5 sent outside
Chapter 30 altogether, and 6 where the record names a subheading no candidate trades under.

WCO OR WTO? BOTH, AND THE DISTINCTION IS NOT PEDANTRY
------------------------------------------------------
The five files are named WTO_*.pdf and the documents are indeed WTO documents: WORLD TRADE
ORGANIZATION mastheads, symbols G/MA/W/26, /76, /105, /122 and /164, circulated by the WTO
Committee on Market Access. But the CONTENT is not the WTO's. Every one of them says the tables
were "drawn up by the World Customs Organization Secretariat in accordance with instructions
received from the Harmonized System Committee", and the 2016 and 2020 files carry "Copyright
World Customs Organization. All rights reserved."

So the correlation tables are WCO work product, circulated by the WTO. The Harmonized System is a
WCO instrument and the HS Committee is a WCO body. In this project's prose and in the manuscript
they are the WCO correlation tables, cited by their WTO document symbol so a reader can find
them. Calling them "the WTO tables" would credit the wrong body; calling the FILES WCO files
would misname the documents actually held here.

THEY HAVE NO LEGAL STATUS, AND THE DOCUMENT SAYS SO IN THOSE WORDS
-------------------------------------------------------------------
Quoted from the 2002-to-2007 file, and repeated in substance in all five:

    "Though these Correlation Tables were examined by the Harmonized System Committee, they are
    not to be regarded as constituting classification decisions taken by that Committee; they
    constitute a guide published by the Secretariat and whose sole purpose is to facilitate
    implementation of the 2007 version of the Harmonized System. They do not have legal status."

This layer is therefore the best available account of where goods went across a revision, and it
is NOT a ruling. That is why it sits below Canada's own ten-digit concordance, which is a
national customs instrument for the very codes this crosswalk is built from, and why it narrows
rather than decides. Any published claim resting on it must carry the caveat in the document's
own words rather than in a paraphrase.

TWO LIMITS ARE STRUCTURAL AND NEITHER IS A DEFECT. The tables map HS6 to HS6, so this layer can
say which subheading received the goods and never which ten-digit line did; no branch of it
returns "decided". And it speaks only where the WHOLE old subheading moved to ONE place, which
is eight subheadings in Chapter 30 across all five boundaries. Where an old code split, the
record bounds neither part, and saying so is more useful than a narrowing it cannot support.

The extractor is deliberately not importable from here. It needs pdfplumber; this module and
everything else under pipeline/ and checks/ is standard library only.


WHAT WOULD MAKE THIS STAGE WRONG
---------------------------------
Stated before the numbers, so the check has something to test:

  - Letting a lower layer overturn a higher one would silently reverse the order that gives the
    official record its authority.
  - Naming a destination that never traded would put a code into the crosswalk that does not
    exist in the delivery.
  - Reporting a decision where the record named several destinations would turn a bounded answer
    into a false certainty.
  - Reading the tariff schedule for a year before the schedules begin would produce an answer
    from the absence of evidence. The schedules start in 2005.
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
CBSA_DIR = PROJECT_ROOT / "evidence" / "cbsa"
DECISIONS_DIR = PROJECT_ROOT / "decisions"

FLOWS = ("imports", "exports")
SCHEDULE_FIRST_YEAR = 2005

# Each concordance covers one boundary, and the two files do not share a schema. The 2011 file
# carries separator-free columns and a page reference; the 2016 file carries only dotted codes.
# Both are reduced to digits here, which is the one internal form Stage 0 established.
CONCORDANCES = (
    ("201112", "concordance_2011_2012_ch30.csv", "obsolete_2011", "new_2012"),
    ("201612", "concordance_2016_2017_ch30.csv", "obsolete_2016", "new_2017"),
)


def digits(text):
    return re.sub(r"\D", "", text or "")


def load_concordances():
    """One entry per retiring code and obsolete YEAR, holding every destination the record names.

    KEYED ON THE YEAR THE RECORD CALLS THE CODE OBSOLETE, NOT ON THE MONTH IT LAST TRADED.
    Those are different facts and only the first is what the concordance asserts. A column headed
    obsolete_2011 says the code was obsolete at the 2011 revision; the delivery separately shows
    when money last moved under it, and money stops first. Codes that went quiet in the run-up to
    a revision therefore had a boundary derived one to four months early and missed the lookup
    entirely, so eight retirements worth CAD 167,730,730 fell through to text similarity while
    Canada's own concordance named their successor. Matching on the year repairs all eight and
    still excludes the two whose last trade is a year or more away from any revision, which are a
    later span of a reused number rather than the retirement the concordance describes.
    """
    named = defaultdict(set)
    for boundary_month, filename, source_col, dest_col in CONCORDANCES:
        path = CBSA_DIR / filename
        if not path.exists():
            raise SystemExit("Stage 1b stopped: %s not found." % path)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                source, dest = digits(row[source_col]), digits(row[dest_col])
                if source and dest:
                    named[(boundary_month[:4], source)].add(dest)
    return named


def load_schedules():
    """The ten-digit codes present in each tariff year.

    Where a year has more than one vintage the later amendment is used, because it is the one in
    force at the end of that year. Reading a year before 2005 returns nothing rather than an
    empty set, so a caller cannot mistake absence of a schedule for absence of a code.
    """
    best = {}
    for path in sorted(CBSA_DIR.glob("sched_ch30_*.csv")):
        match = re.search(r"sched_ch30_(\d{4})(?:-(\d+))?\.csv$", path.name)
        if not match:
            continue
        year, amendment = int(match.group(1)), int(match.group(2) or 0)
        if year not in best or amendment > best[year][0]:
            best[year] = (amendment, path)
    schedules = {}
    for year, (_amendment, path) in best.items():
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        # ONLY the six-digit subheading is comparable, and this was measured rather than assumed.
        #
        # The tariff schedule and the trade data are two different numbering systems below six
        # digits. The tariff lists tariff items; Statistics Canada adds its own statistical
        # breakouts underneath them. Export code 30029020, Saxitoxin, is absent from every
        # schedule not because it never existed but because the tariff enumerates only 30029000.
        # Matching at full length finds 240 of 386 import codes and 51 of 74 export codes. At six
        # digits, where both systems follow the international nomenclature, it finds 54 of 56.
        #
        # Falsifying a candidate on a full-length miss would therefore rule out codes for a
        # bookkeeping reason rather than a factual one. Only the subheading is used.
        subheadings = set()
        for r in rows:
            for value in (digits(r.get("hs10") or ""), digits(r.get("tariff_item8") or "")):
                if len(value) >= 6:
                    subheadings.add(value[:6])
        schedules[year] = subheadings
    return schedules


def load_constraint_sets():
    path = DECISIONS_DIR / "official_constraint_sets.csv"
    sets = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            forward = [d for d in row["forward_destinations"].split(";") if d]
            sets[row["source_code"]] = {
                "forward": forward,
                "action": row["stage1_action"],
                "status": row["source_status"],
            }
    return sets


def load_correlations():
    """(revision month, old HS6) -> the one subheading the WHOLE old code moved to.

    Read from evidence/wto/wto_ch30_pairs.csv, which evidence/wto/extract_wto_pairs.py produces
    from the five WCO boundary PDFs. That script needs pdfplumber; this module does not and must
    not, which is why the CSV and not the PDF is the run-time input.

    ONLY TABLE I IS READ, AND ONLY ITS UNAMBIGUOUS ROWS. Each document states its correlations
    twice, Table I per new code and Table II per old code, and the `ex` marker attaches to
    whichever column its own table describes. The same fact is written `3002.11 -> 3822.11` in
    one and `3002.11 -> ex3822.11` in the other, so a rule keyed on the marker without knowing
    which table produced it reads one fact as two. Table I is the side whose marker describes the
    OLD code, which is what this layer needs to know about.

    An old subheading qualifies when it appears in Table I exactly once and without `ex`: it
    moved entirely, and to one place. Eight subheadings qualify across all five boundaries. An
    old code appearing twice, or marked `ex`, SPLIT, and a split bounds nothing: part of 3004.32
    went to waste pharmaceuticals in 3006.80 while the rest stayed in 3004.32, so the record
    constrains neither part. Reading `ex` loosely would let sixteen more subheadings constrain a
    field they have no authority over.
    """
    path = PROJECT_ROOT / "evidence" / "wto" / "wto_ch30_pairs.csv"
    if not path.exists():
        raise SystemExit("Stage 1b stopped: %s not found. Run evidence/wto/extract_wto_pairs.py "
                         "to rebuild it from the five boundary PDFs." % path)
    seen = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["section"] != "TABLE_I":
                continue
            seen[(row["boundary_to"], digits(row["old_code"]))].append(row)
    # Re-keyed onto the revision MONTH the pipeline works in, so no caller does the arithmetic:
    # a code terminated 2021-12 is governed by the 2017-to-2022 table.
    by_month = {}
    for (effective, old), rows in seen.items():
        if len(rows) == 1 and not rows[0]["old_ex"]:
            by_month[("%d12" % (int(effective) - 1), old)] = digits(rows[0]["new_code"])
    return by_month


def next_month(period):
    year, month = int(period[:4]), int(period[4:])
    return "%04d%02d" % (year + 1, 1) if month == 12 else "%04d%02d" % (year, month + 1)


def schedule_years_for(boundary, classification_end):
    """Every tariff vintage in force while the trade could still have transferred.

    This used to be `int(boundary[:4])`, a single year, and that read the WRONG SIDE of a
    revision. The boundary is the month after the last trade, so a code that went quiet in
    November of a revision year has a boundary in December and was tested against the
    pre-revision schedule. The codes the revision creates the following January are absent
    from it, so the layer vetoed the very successors it exists to leave standing, and wrote a
    note saying they sat in a subheading the schedule "no longer holds" when the truth is the
    schedule did not hold them YET. Two export rows were affected, CAD 1,433,663: 30021100
    lost 30024100, 30024200, 30024900, 30025100 and 30025900, and 30034000 lost 30034100,
    30034200, 30034900 and 30036000. Their siblings whose trade ran to December read the
    correct vintage and kept all of them, so the two flows disagreed on arithmetic alone.

    The window runs from the boundary to the month after the classification ends. Because it
    always CONTAINS the boundary year, and the layer takes the union of the vintages in it, the
    surviving set can only ever grow. A new removal is impossible by construction rather than
    by measurement, which matters for a layer whose only licence is to rule a candidate out.

    The first attempt at this fix read a single later vintage instead of the union, and was
    measured and thrown away: it removed 42 candidates across six 3006 import rows whose trade
    stopped years before their stated termination, codes that demonstrably existed at the
    moment the trade could have moved to them.
    """
    low = int(boundary[:4])
    high = int(next_month(classification_end)[:4])
    return list(range(low, max(low, high) + 1))


def resolve(row, named, schedules, constraint_sets, classification_end, correlations):
    """Consult each layer in order and stop at the first that answers."""
    code = row["retiring_code"]
    boundary = row["boundary"]
    month = row["last_period"]
    candidates = [c for c in row["candidates_narrowest"].split(";") if c]

    # Layer 1. Canada's own ten-digit concordance, matched on the year it calls the code
    # obsolete rather than on the month trade stopped.
    destinations = sorted(named.get((month[:4], code), ()))
    if destinations:
        outcome = "decided" if len(destinations) == 1 else "constrained"
        return {"layer": "cbsa_concordance", "outcome": outcome,
                "destinations": destinations, "surviving": destinations,
                "note": "named by Canada's concordance at %s" % boundary}

    # Layer 2. The international correlation, read from evidence/wto/wto_ch30_pairs.csv.
    #
    # It speaks at an international revision and nowhere else, and it speaks about SUBHEADINGS.
    # The tables map HS6 to HS6, so this layer can say which subheading received the goods and
    # can never say which ten-digit line did. It therefore constrains and does not decide, which
    # is why no branch here returns "decided".
    #
    # AND IT SPEAKS ONLY WHERE THE WHOLE OLD SUBHEADING MOVED TO ONE PLACE. That is the strict
    # reading of the document's own `ex` marker, which means "part of". Table I lists, for each
    # new code, the old codes that fed it; an old code appearing there once and unmarked moved
    # entirely and to one destination. An old code appearing twice, or marked `ex`, SPLIT, and a
    # split cannot bound anything: part of 3004.32 went to waste pharmaceuticals in 3006.80 and
    # the rest stayed in 3004.32, so the table constrains neither part. Eight subheadings in the
    # whole of Chapter 30 pass that test across all five boundaries. Reading `ex` loosely would
    # have let sixteen more constrain a field they have no authority over.
    # The revision the correlation speaks at, named the way the documents name themselves.
    revision_year = int(classification_end[:4]) if classification_end else 0
    boundary_label = "%d to %d" % (revision_year - 4, revision_year + 1) if revision_year else ""
    correlated = correlations.get((classification_end, code[:6]))
    if correlated and correlated != code[:6]:
        if not correlated.startswith("30"):
            # The record says the goods left Chapter 30. This crosswalk covers Chapter 30, so
            # there is no successor to record and no candidate is removed: a person still has to
            # write `none` into the answer sheet, and they are entitled to see what was on offer
            # when they do. The record is reported, not enacted.
            # `destinations` STAYS EMPTY. Its contract, asserted by a control in this stage's
            # check, is "ten-digit codes that traded in this delivery". A correlation names a
            # six-digit SUBHEADING, and one outside Chapter 30 at that, so putting it here broke
            # the contract on five rows and the control caught it within a minute of the layer
            # going live. The destination belongs in the note, where it is prose and claims
            # nothing about the delivery.
            return {"layer": "wco_correlation", "outcome": "correlated_left_chapter",
                    "destinations": [], "surviving": candidates,
                    "note": "the WCO %s correlation sends this subheading to %s, outside "
                            "Chapter 30" % (boundary_label, correlated)}
        survivors = [c for c in candidates if c[:6] == correlated]
        if not survivors:
            # The record names a subheading nothing in the candidate field trades under. That is
            # a disagreement between the record and the narrowing that built the field, not a
            # narrowing of it, and it needs a person. Six rows are here, every one of them a
            # waste-pharmaceutical line the record sends to 3006.92 while the structural field
            # never offered 3006.92.00.00 at all. The analyst reached 3006.92.00.00 by hand on
            # all six, which is the record agreeing with them after the fact.
            return {"layer": "wco_correlation", "outcome": "correlated_no_candidate",
                    "destinations": [], "surviving": candidates,
                    "note": "the WCO %s correlation sends this subheading to %s, which no "
                            "candidate trades under" % (boundary_label, correlated)}
        # `narrowed`, NOT `constrained`, and the distinction is the vocabulary working. This
        # layer removes candidates; it does not name a destination. `constrained` means the
        # record names a short list and puts it in `destinations`, which only the concordance and
        # the bounded sets can do, and a control asserts exactly that. Calling this `constrained`
        # claimed an authority the layer does not have and the control said so.
        outcome = "forced" if len(survivors) == 1 else "narrowed"
        return {"layer": "wco_correlation", "outcome": outcome,
                "destinations": [], "surviving": survivors,
                "note": "the WCO %s correlation sends this subheading to %s, leaving %d of %d "
                        "candidate(s)" % (boundary_label, correlated, len(survivors),
                                          len(candidates))}

    # Layer 3. The bounded sets. Above the schedule, because naming a set of destinations says
    # more than ruling one out. Exports only, which is where the sets were established.
    bounded = constraint_sets.get(code)
    if bounded and row["flow"] == "exports":
        # The recorded action decides the outcome, rather than the size of the set. Removing a
        # retired code from its own set can leave a single destination, and 30049000 is that
        # case: the record bounds it to two codes, one of which is itself. A single survivor
        # looks like a decision and is not one here, because the row carries a required ruling.
        # Letting the count speak instead of the action would settle CAD 62,379,640,484 on a
        # successor holding 0.06 per cent of it, with no person involved.
        outcome = ("bounded_needs_ruling" if bounded["action"] == "constrain_and_rule"
                   else "constrained")
        return {"layer": "constraint_set", "outcome": outcome,
                "destinations": bounded["forward"], "surviving": bounded["forward"],
                "note": "bounded by the official record, action %s" % bounded["action"]}

    # Layer 4. The schedule alone. It cannot name a successor. It can rule out a candidate that
    # did not exist yet, and it can force an answer when only one candidate survives that test.
    base = int(boundary[:4])
    # The base year gates the whole layer, exactly as it did before the window was introduced.
    # Widening the window must never hand a schedule to a row that had none: reading 2005 for a
    # 2004 boundary is the failure this module's own docstring names, an answer produced from
    # the absence of evidence. So the window is only ever a widening of a reading already taken.
    if base >= SCHEDULE_FIRST_YEAR and base in schedules:
        years = [y for y in schedule_years_for(boundary, classification_end)
                 if y >= SCHEDULE_FIRST_YEAR and y in schedules]
        present = set().union(*(schedules[y] for y in years))
        window = str(years[0]) if len(years) == 1 else "%d to %d" % (years[0], years[-1])
        # A candidate survives unless its whole subheading is absent from EVERY schedule in
        # force across the window. That is the only claim the schedule can support for both
        # flows: that the candidate existed at no point when the trade could have reached it.
        survivors = [c for c in candidates if c[:6] in present]
        if not survivors:
            # Every candidate's subheading is absent. That is a contradiction between the tariff
            # and the trade data rather than a narrowing, and it needs a person.
            return {"layer": "tariff_schedule", "outcome": "all_candidates_absent",
                    "destinations": [], "surviving": candidates,
                    "note": "no subheading for any of the %d candidates appears in the %s "
                            "schedule, which needs a ruling" % (len(candidates), window)}
        if len(survivors) < len(candidates):
            outcome = "forced" if len(survivors) == 1 else "narrowed"
            return {"layer": "tariff_schedule", "outcome": outcome,
                    "destinations": [], "surviving": survivors,
                    "note": "%d of %d candidates sit in a subheading absent from every schedule "
                            "in force across %s"
                            % (len(candidates) - len(survivors), len(candidates), window)}
        # The schedule was read and excluded nothing. That is a different statement from having
        # no schedule to read, and collapsing the two would overstate how much evidence is
        # missing. Both leave the answer to the later stages; only one is an absence of source.
        return {"layer": "tariff_schedule", "outcome": "silent_no_effect",
                "destinations": [], "surviving": candidates,
                "note": "the %s schedule holds every candidate, so it excludes none" % window}

    return {"layer": "none", "outcome": "silent_no_source", "destinations": [],
            "surviving": candidates,
            "note": "no official source reaches %s" % boundary}


COLUMNS = ["retiring_code", "flow", "last_period", "boundary", "total_value_cad", "description",
           "deciding_layer", "outcome", "official_destinations", "n_official",
           "candidates_before", "candidates_after", "n_after",
           "official_outside_structural_field", "at_hs_revision_boundary", "note"]


def classification_end_for(row, stated_ends):
    """The month the record says the code stopped being a classification, else its last trade.

    Never earlier than the last trade: a stated termination preceding observed trade would be a
    contradiction in the source, and taking the earlier of the two would discard months the
    delivery actually reports.
    """
    stated = stated_ends.get((row["retiring_code"], row["last_period"]), "")
    return stated if stated and stated >= row["last_period"] else row["last_period"]


def build(flow, named, schedules, constraint_sets, inventory_codes, stated_ends,
          correlations):
    path = WORK_DIR / ("stage1_candidates_%s.csv" % flow)
    if not path.exists():
        raise SystemExit("Stage 1b stopped: %s not found. Run s02_stage1_candidates.py first." % path)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        worklist = list(csv.DictReader(handle))

    rows = []
    for row in worklist:
        before = [c for c in row["candidates_narrowest"].split(";") if c]
        answer = resolve(row, named, schedules, constraint_sets,
                         classification_end_for(row, stated_ends), correlations)
        # A destination the record names but the structural field never offered. Worth counting:
        # it is a case where narrowing by code structure alone would have excluded the right
        # answer, which is the argument for putting the record above structure.
        outside = [d for d in answer["destinations"] if d not in before]
        rows.append({
            "retiring_code": row["retiring_code"],
            "flow": flow,
            "last_period": row["last_period"],
            "boundary": row["boundary"],
            "total_value_cad": row["total_value_cad"],
            "description": row["description"],
            "deciding_layer": answer["layer"],
            "outcome": answer["outcome"],
            "official_destinations": ";".join(answer["destinations"]),
            "n_official": len(answer["destinations"]),
            "candidates_before": len(before),
            "candidates_after": ";".join(answer["surviving"]),
            "n_after": len(answer["surviving"]),
            "official_outside_structural_field": ";".join(sorted(outside)),
            # Carried through so the empty correlation layer can report a measured reach rather
            # than a constant. A correlation table speaks only at an international revision.
            "at_hs_revision_boundary": row["at_hs_revision_boundary"],
            "note": answer["note"],
        })
    return rows


def describe(flow, rows):
    total = len(rows)
    value = sum(float(r["total_value_cad"]) for r in rows)
    print("  retirements considered            : %d, CAD {:,.0f}".format(value) % total)
    by_layer = defaultdict(lambda: [0, 0.0])
    for r in rows:
        entry = by_layer[(r["deciding_layer"], r["outcome"])]
        entry[0] += 1
        entry[1] += float(r["total_value_cad"])
    print("  what each layer did:")
    for (layer, outcome), (n, val) in sorted(by_layer.items(), key=lambda kv: -kv[1][0]):
        print("      {:<20} {:<12} {:>4}  CAD {:>18,.0f}".format(layer, outcome, n, val))
    decided = sum(1 for r in rows if r["outcome"] == "decided")
    no_source = sum(1 for r in rows if r["outcome"] == "silent_no_source")
    no_effect = sum(1 for r in rows if r["outcome"] == "silent_no_effect")
    print("  decided outright by the record    : %d of %d (%.0f%%)" % (decided, total, 100.0*decided/total))
    print("  no official source reaches them   : %d of %d (%.0f%%)"
          % (no_source, total, 100.0*no_source/total))
    print("  a source was read and excluded nothing: %d of %d (%.0f%%)"
          % (no_effect, total, 100.0*no_effect/total))
    # The reach of the layer that is declared and empty, measured rather than asserted. A
    # correlation table speaks only at an international revision, and only where the layer above
    # it stayed silent. Anything the concordance already decided is out of its reach.
    reach = [r for r in rows if r["at_hs_revision_boundary"] == "yes"
             and r["deciding_layer"] != "cbsa_concordance"]
    reach_value = sum(float(r["total_value_cad"]) for r in reach)
    print("  the empty correlation layer decided: 0 of a possible {}, CAD {:,.0f}".format(
        len(reach), reach_value))
    print("      (declared and empty. Nothing has been extracted from the five PDF tables yet,")
    print("       so this is the size of the gap the stage currently runs with)")
    outside = [r for r in rows if r["official_outside_structural_field"]]
    print("  official destinations the structural field would have excluded: %d" % len(outside))
    for r in outside[:5]:
        print("      %s -> %s" % (r["retiring_code"], r["official_outside_structural_field"]))


def main():
    print("Stage 1b. Letting the official record speak, in order.")
    print("A layer can decide, narrow, or say nothing. It can never overturn a layer above it.")
    print()
    named = load_concordances()
    schedules = load_schedules()
    constraint_sets = load_constraint_sets()
    correlations = load_correlations()
    print("sources loaded:")
    print("  ten-digit concordance entries     : %d retiring codes across %d boundaries"
          % (len(named), len(CONCORDANCES)))
    print("  tariff vintages                   : %d, %d to %d"
          % (len(schedules), min(schedules), max(schedules)))
    print("  bounded official sets             : %d" % len(constraint_sets))
    print("  international correlation tables  : 0 extracted, 5 held as PDF only")
    print()
    for flow in FLOWS:
        inventory_codes = set()
        stated_ends = {}
        inv_path = WORK_DIR / ("commodity_inventory_%s.csv" % flow)
        with open(inv_path, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                inventory_codes.add(r["hs_code"])
                stated = (r.get("stated_termination") or "").strip()
                if stated:
                    stated_ends[(r["hs_code"], r["last_period"])] = stated
        print("%s:" % flow)
        rows = build(flow, named, schedules, constraint_sets, inventory_codes,
                     stated_ends, correlations)
        describe(flow, rows)
        destination = WORK_DIR / ("stage1_official_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()
    print("Stage 1b complete. What the record could not settle is untouched and waiting.")


if __name__ == "__main__":
    sys.exit(main() or 0)
