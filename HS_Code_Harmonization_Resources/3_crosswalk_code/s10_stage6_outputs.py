"""Stage 6. Publish the crosswalk in the four shapes a reader uses, and decide nothing.


Inputs:
    work/stage2_resolved_{imports,exports}.csv      what each retirement resolved to
    work/stage3_routed_{imports,exports}.csv        the whole journey per commodity string
    work/stage4_families_{imports,exports}.csv      the family each commodity belongs to
    work/stage5_lineage_{imports,exports}.csv       one row per step of every journey
    work/stage1_official_{imports,exports}.csv      which layer of the record answered
    work/commodity_inventory_{imports,exports}.csv  one row per LIFE of every code
    gate1/v1_to_v2_identifiers_{imports,exports}.csv   the released identifiers, joined by hand

Outputs:
    output/{flow}_lookup.csv              one row per commodity string: what it is, what it became
    output/{flow}_commodity_journeys.csv  one row per commodity string: the whole path as a string
    output/{flow}_lineage_timeline.csv    one row per STEP, the readable form of the same path
    output/{flow}_provenance.csv          one row per commodity string: what settled it, and how


THIS STAGE DECIDES NOTHING, AND THAT IS THE ONLY CLAIM IT MAKES
---------------------------------------------------------------
Every value written here is copied or joined from a stage that already published it. Stage 6 adds
no rule, resolves no ambiguity and reads no evidence. A control requires that the set of record
identifiers, family identifiers and journeys it emits is EXACTLY Stage 4's and Stage 5's, so a
value that appears here and nowhere upstream fails the build rather than reaching a reader.

The one thing it does that no earlier stage does is JOIN: it puts the released v1 identifiers
beside the v2 ones, so a reader holding the submitted manuscript can find their row without a
second file.


WHY THE SHAPES ARE v1's SHAPES
-------------------------------
Four files with these column names were released with the manuscript. Anyone who built a script
against them should not have to rewrite it to read the corrected data, so the columns keep their
names and their order even where this project would now name them differently. Two departures are
deliberate and both add rather than rename:

  - `lookup` gains `v1_uid` and `v1_family_id` at the END, as reference columns. Nothing joins on
    them. They are there to be looked up. METHOD_family_id.md says this belongs to Stage 6 and not
    to Stage 4, and the direction is the reason: gate1 READS Stage 4's output, so Stage 4 reading
    gate1's would close a cycle.
  - `lineage_timeline` gains `step_first_period` and `step_last_period`. v1 folded the month into
    the status as `ended_2006-12`, which puts two facts in one string and forces every reader to
    parse it. The status vocabulary is NOT v1's spelling: v1 wrote `active` or `ended_YYYY-MM`,
    and these files write the four words below. The old form derives from the new columns, as
    `ended_` plus `step_last_period` wherever the status is not `active`, and not the other way
    round. This paragraph claimed the v1 spelling was kept until 2026-08-19; it never was.
    Finding 145.

The CONTENT of four column families is part of the contract, not only the names. The commodity
columns (`orig_commodity`, `latest_commodity`) carry the full source string with the code
dotted, which is what a reader joins their monthly data on; see `source_string` below. The
description columns carry the raw wording passed through the 67-entry customs-abbreviation
table, which is that table's one published purpose. Until 2026-08-20 this stage wrote bare
codes into the former and raw shorthand into the latter, and both known consumers' joins and
displays broke silently. Findings 152 and 153.


WHAT A STATUS MEANS, AND WHICH COLUMN CARRIES WHOSE
------------------------------------------------------------
  active             the code is still trading in the delivery's last month
  succeeded          it ended and the trade transferred to a successor
  left_chapter       the goods left Chapter 30 and this crosswalk has no successor to record
  not_a_retirement   trade stopped while the classification stood, so nothing was withdrawn

Three columns share that vocabulary and they answer about different codes:

  step_status        the fate of the code at that step; any of the four values
  orig_status        the fate of the ORIGINAL commodity, which is step 1 of its chain, so it
                     reads `succeeded` on every chain that moved on
  latest_status,     the standing of the code the chain ends at. A terminal that succeeded
  final_status       would have a next step, so `succeeded` cannot occur here and the three
                     possible values are the other three

Until 2026-08-19 this docstring defined `latest_status` with a `succeeded` value that occurred
zero times in 572 rows, and said nothing about the other two columns. Finding 145.

`left_chapter` and `not_a_retirement` carry no successor and that is the answer, not a gap. A file
that filled them in would be inventing links, which is the one failure this project cannot afford.
"""

import csv
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
GATE1_DIR = PROJECT_ROOT / "gate1"
OUTPUT_DIR = PROJECT_ROOT / "output"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shorthand import expand_shorthand  # noqa: E402
from s05_make_adjudication_queue import dotted, month  # noqa: E402

FLOWS = ("imports", "exports")

ACTIVE = "active"
SUCCEEDED = "succeeded"

LOOKUP_COLUMNS = [
    "uid", "orig_commodity", "orig_hs_code", "orig_description",
    "orig_first_period", "orig_last_period", "family_id",
    "latest_commodity", "latest_hs_code", "latest_description", "latest_status",
    "v1_uid", "v1_family_id",
]
JOURNEY_COLUMNS = [
    "uid", "orig_commodity", "orig_first_period", "orig_last_period", "orig_status",
    "n_steps_in_chain", "journey", "family_id", "latest_commodity", "final_status",
]
TIMELINE_COLUMNS = [
    "uid", "orig_commodity", "family_id", "step_number", "hs_code", "description",
    "orig_first_period", "orig_last_period", "step_status", "next_hs_code",
    "step_first_period", "step_last_period",
]
PROVENANCE_COLUMNS = [
    "uid", "orig_hs_code", "family_id", "resolution_source", "resolution_detail",
    "official_adjudicated", "official_agrees", "boundary_crossed", "confidence_tier",
    "departure_from_official",
]


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def stop(message, examples=()):
    print()
    print("Stage 6 STOPPED: %s" % message)
    for item in list(examples)[:8]:
        print("    %s" % (item,))
    raise SystemExit(1)


def resolution_of(answer):
    """Which kind of evidence settled a retirement, in the vocabulary v1's provenance used.

    Read off the columns Stage 2 published rather than re-derived, because Stage 2 owns this and a
    second derivation here would be a second answer that can drift from it.
    """
    if not answer:
        return "", ""
    return answer["authority"], answer["detail"]


def source_string(code_dotted, inv_row):
    """The commodity string as the delivery publishes it, with the code dotted.

    THIS IS THE COLUMN A READER JOINS ON, AND IT IS NOT A CODE. v1 published `orig_commodity`
    and `latest_commodity` as the full source string: the dotted code, ' - ', the raw StatCan
    wording, and the '(Terminated YYYY-MM)' note wherever the source string carries one. Both
    known consumers join their monthly data's Commodity field against it. Until 2026-08-20 this
    stage wrote the bare code into both columns, on a comment claiming v1 had done the same,
    and the join broke on every row. The note is included whenever the record carries one, even
    where Stage 1a attributes it to a later life of a reused number, because this column
    reproduces the string as the source publishes it, not the pipeline's reading of it.
    Finding 152.
    """
    note = inv_row.get("stated_termination") or ""
    return ("%s - %s" % (code_dotted, inv_row["description"])
            + (" (Terminated %s)" % month(note) if note else ""))


def build(flow, families, lineage, routed, resolved, official, inventory, v1):
    """The four shapes, joined. Nothing here computes a link, a family or a journey."""
    by_record = {r["record_id"]: r for r in families}
    by_span = {r["span_id"]: r for r in routed}
    span_of = {r["record_id"]: r["span_id"] for r in families}
    official_by_link = {(digits(r["retiring_code"]), r["last_period"]): r for r in official}
    v1_by_record = {r["v2_record_id"]: r for r in v1}

    # The life each code was in at the end of its journey, so `latest_description` is the wording
    # the goods carry NOW and not the one they carried when they left. Rule 13: a question about a
    # code is a question about one of its lives.
    lives = defaultdict(list)
    for record in inventory:
        lives[digits(record["hs_code"])].append(record)
    for held in lives.values():
        held.sort(key=lambda s: s["first_period"])

    # The inventory record behind each published row, so the commodity-string columns can
    # reproduce the source string and the description columns can expand it. Keyed two ways:
    # a record's own identity is (code, first month), and a terminal is named by Stage 3 with
    # its wording and last month.
    inv_by_first = {(digits(r["hs_code"]), r["first_period"]): r for r in inventory}
    inv_by_last = {(digits(r["hs_code"]), r["description"], r["last_period"]): r
                   for r in inventory}

    steps_by_record = defaultdict(list)
    for step in lineage:
        steps_by_record[step["record_id"]].append(step)
    for held in steps_by_record.values():
        held.sort(key=lambda s: int(s["step_number"]))

    lookup, journeys, timeline, provenance = [], [], [], []
    problems = defaultdict(list)

    for record in sorted(families, key=lambda r: r["record_id"]):
        uid = record["record_id"]
        journey = by_span.get(span_of[uid])
        if journey is None:
            problems["no journey"].append(uid)
            continue
        steps = steps_by_record.get(uid) or []
        if not steps:
            problems["no steps"].append(uid)
            continue
        last_step = steps[-1]
        status = last_step["step_status"]

        # WHERE IT ENDED UP. For a journey that succeeded onward this is the terminal code; for one
        # that never moved it is the commodity itself. Taken from Stage 3, which walked it.
        terminal = journey["terminal_code"]
        terminal_desc = journey["terminal_description"]
        if status in ("left_chapter", "not_a_retirement"):
            # Nothing received the trade. Naming the code it stopped at is not naming a successor,
            # and the status column is what says which of the two a reader is looking at.
            terminal, terminal_desc = journey["terminal_code"], journey["terminal_description"]

        # PROVENANCE IS ABOUT THE WHOLE CHAIN, NOT THE LAST STEP. A journey of three codes crossed
        # two retirements and each was settled by its own evidence; the last step of an ACTIVE
        # journey is a code that never retired at all, so keying on it reported "the record said
        # nothing" for all 475 import commodities on the first run. Every hop is walked here and
        # the answers are combined.
        hops = []
        for earlier, later in zip(steps, steps[1:]):
            key = (digits(earlier["hs_code"]), earlier["step_last_period"])
            hops.append((key, resolved.get(key), official_by_link.get(key)))
        if last_step["step_status"] in ("left_chapter", "not_a_retirement"):
            key = (digits(last_step["hs_code"]), last_step["step_last_period"])
            hops.append((key, resolved.get(key), official_by_link.get(key)))

        # The record's own inventory row and the terminal's. Refused rather than defaulted:
        # a published string this stage cannot trace to the delivery would be an invention.
        own_inv = inv_by_first.get((digits(record["hs_code"]), record["first_period"]))
        term_inv = inv_by_last.get((digits(terminal), journey["terminal_description"],
                                    journey["terminal_last_period"]))
        if own_inv is None or term_inv is None:
            problems["no inventory record for the commodity string"].append(uid)
            continue
        orig_full = source_string(record["hs_code"], own_inv)
        terminal_full = source_string(terminal, term_inv)

        v1row = v1_by_record.get(uid, {})
        lookup.append({
            "uid": uid,
            "orig_commodity": orig_full,
            "orig_hs_code": record["hs_code"],
            # The description columns pass the raw wording through the 67-entry customs-
            # abbreviation table, exactly as v1 released them and as the method documents
            # the table's one purpose. Raw shorthand shipped here until 2026-08-20; the raw
            # form stays recoverable from the commodity-string columns. Finding 153.
            "orig_description": expand_shorthand(record["description"]),
            "orig_first_period": month(record["first_period"]),
            "orig_last_period": month(record["last_period"]),
            "family_id": record["family_id"],
            "latest_commodity": terminal_full,
            "latest_hs_code": terminal,
            "latest_description": expand_shorthand(terminal_desc),
            "latest_status": status,
            "v1_uid": v1row.get("v1_uid", ""),
            "v1_family_id": v1row.get("v1_family_id", ""),
        })
        journeys.append({
            "uid": uid,
            "orig_commodity": orig_full,
            "orig_first_period": month(record["first_period"]),
            "orig_last_period": month(record["last_period"]),
            # THE ORIGINAL COMMODITY'S OWN FATE, which is step 1 of its chain. v1 published this
            # column that way: 357 of its 475 import rows read ended_YYYY-MM while final_status
            # read active. Copying the terminal's status here instead made the column a duplicate
            # of final_status on every row and flipped its answer on every multi-step chain, a
            # silent third departure from the released shapes. Finding 144.
            "orig_status": steps[0]["step_status"],
            "n_steps_in_chain": journey["codes_in_journey"],
            "journey": journey["journey"],
            "family_id": record["family_id"],
            "latest_commodity": terminal_full,
            "final_status": journey["terminal_status"],
        })
        for step in steps:
            timeline.append({
                "uid": uid,
                "orig_commodity": orig_full,
                "family_id": record["family_id"],
                "step_number": step["step_number"],
                "hs_code": step["hs_code"],
                "description": expand_shorthand(step["description"]),
                "orig_first_period": month(record["first_period"]),
                "orig_last_period": month(record["last_period"]),
                "step_status": step["step_status"],
                "next_hs_code": step["next_hs_code"],
                "step_first_period": month(step["step_first_period"]),
                "step_last_period": month(step["step_last_period"]),
            })
        # WHETHER THE OFFICIAL RECORD SPOKE, AND WHETHER IT AGREED. Both read off Stage 1b, which
        # is the only place that knows. `official_agrees` stays blank where the record said
        # nothing, because "no" would claim a disagreement that never happened.
        spoke, agreed, departed, boundaries = [], [], [], []
        sources, details, tiers = [], [], []
        for key, answer, entry in hops:
            source, detail = resolution_of(answer)
            if source:
                sources.append(source)
            if detail:
                details.append(detail)
            if answer and answer["basis"]:
                tiers.append(answer["basis"])
            if (entry or {}).get("at_hs_revision_boundary") == "yes":
                boundaries.append(key[0])
            named = {digits(d) for d in (entry or {}).get("official_destinations", "").split(";")
                     if d}
            if not named:
                continue
            spoke.append(key[0])
            if digits((answer or {}).get("successor", "")) in named:
                agreed.append(key[0])
            else:
                departed.append(key[0])

        if not hops:
            # It never retired. Saying "the record did not adjudicate it" would be true and
            # misleading; there was nothing to adjudicate.
            resolution = "never_retired"
        else:
            resolution = ";".join(sorted(set(sources))) or "unsettled"
        provenance.append({
            "uid": uid,
            "orig_hs_code": record["hs_code"],
            "family_id": record["family_id"],
            "resolution_source": resolution,
            "resolution_detail": " | ".join(details),
            "official_adjudicated": "yes" if spoke else ("no" if hops else "not_applicable"),
            "official_agrees": ("" if not spoke else
                                "yes" if not departed else
                                "no" if not agreed else "partly"),
            "boundary_crossed": "yes" if boundaries else ("no" if hops else "not_applicable"),
            "confidence_tier": ";".join(sorted(set(tiers))),
            "departure_from_official": ";".join(dotted(c) for c in departed),
        })
    return lookup, journeys, timeline, provenance, problems


def describe(flow, lookup, journeys, timeline, provenance):
    print("%s:" % flow)
    print("  commodity strings published        : %d" % len(lookup))
    print("  steps in the timeline              : %d" % len(timeline))
    print("  families                           : %d" % len({r["family_id"] for r in lookup}))
    print("  where each commodity ended:")
    for status, n in sorted(Counter(r["latest_status"] for r in lookup).items(),
                            key=lambda kv: -kv[1]):
        print("      %-18s %5d" % (status, n))
    joined = sum(1 for r in lookup if r["v1_uid"])
    print("  carrying a released v1 identifier  : %d of %d, %d new to v2"
          % (joined, len(lookup), len(lookup) - joined))
    never = sum(1 for r in provenance if r["resolution_source"] == "never_retired")
    spoke = sum(1 for r in provenance if r["official_adjudicated"] == "yes")
    away = sum(1 for r in provenance if r["departure_from_official"])
    print("  never retired, so nothing to settle: %d" % never)
    print("  the record named a destination somewhere along their chain: %d" % spoke)
    print("  where this crosswalk departs from what the record named   : %d" % away)


def write(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print("  written: %s" % path.relative_to(PROJECT_ROOT))


def main():
    print("Stage 6: publish the crosswalk. This stage decides nothing.")
    print()
    OUTPUT_DIR.mkdir(exist_ok=True)
    for flow in FLOWS:
        paths = {name: WORK_DIR / ("%s_%s.csv" % (name, flow))
                 for name in ("stage2_resolved", "stage3_routed", "stage4_families",
                              "s09_stage5_lineage", "stage1_official", "commodity_inventory")}
        for name, path in paths.items():
            if not path.exists():
                stop("%s not found. Run the earlier stages first." % path)
        gate = GATE1_DIR / ("v1_to_v2_identifiers_%s.csv" % flow)
        if not gate.exists():
            stop("%s not found. Run gate1/build_identifier_crosswalk.py first; it is run by hand "
                 "and its output is committed." % gate)

        families = load(paths["stage4_families"])
        lineage = load(paths["s09_stage5_lineage"])
        routed = load(paths["stage3_routed"])
        official = load(paths["stage1_official"])
        inventory = load(paths["commodity_inventory"])
        resolved = {(digits(r["retiring_code"]), r["last_period"]): r
                    for r in load(paths["stage2_resolved"])}
        v1 = load(gate)

        lookup, journeys, timeline, provenance, problems = build(
            flow, families, lineage, routed, resolved, official, inventory, v1)

        for reason, items in problems.items():
            if items:
                stop("%d commodity string(s) could not be published: %s" % (len(items), reason),
                     items)
        if len(lookup) != len(families):
            stop("%d commodity string(s) in, %d published." % (len(families), len(lookup)))
        if len(timeline) != len(lineage):
            stop("%d step(s) in, %d published." % (len(lineage), len(timeline)))

        describe(flow, lookup, journeys, timeline, provenance)
        write(OUTPUT_DIR / ("%s_lookup.csv" % flow), LOOKUP_COLUMNS, lookup)
        write(OUTPUT_DIR / ("%s_commodity_journeys.csv" % flow), JOURNEY_COLUMNS, journeys)
        write(OUTPUT_DIR / ("%s_lineage_timeline.csv" % flow), TIMELINE_COLUMNS, timeline)
        write(OUTPUT_DIR / ("%s_provenance.csv" % flow), PROVENANCE_COLUMNS, provenance)
        print()

    print("Stage 6 complete. The crosswalk is published in the four shapes v1 released.")


if __name__ == "__main__":
    main()
