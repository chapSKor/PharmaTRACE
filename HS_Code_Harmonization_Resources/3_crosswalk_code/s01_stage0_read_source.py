"""
Stage 0. Read the trade delivery and build the commodity inventory.


Inputs:
    source/imports.db            Statistics Canada CIMT imports, 1988-01 to 2026-06, ten-digit codes
    source/exports.db            Statistics Canada CIMT total exports, re-exports included, same period, eight-digit codes

Outputs:
    work/commodity_inventory_imports.csv
    work/commodity_inventory_exports.csv
    A printed summary of what was read, and the range of every field derived from it.


WHAT THIS STAGE DOES, IN PLAIN LANGUAGE
---------------------------------------
The trade databases hold one row for every combination of month, commodity, province, country
and state. That is roughly 1.8 million rows across the two flows, and almost none of it is
relevant to tracing how a commodity code changed over time.

What the rest of the pipeline needs is far smaller: a list of every commodity that has ever
traded, with the month it first appeared and the month it last appeared. That list is the
commodity inventory, and building it is all this stage does.

Nothing here decides anything. No commodity is linked to any other, no code is judged to have
succeeded another. This stage only reads and counts. Every later stage works from the inventory
rather than from the raw database, so the expensive read happens once.


WHY A COMMODITY IS NOT THE SAME THING AS AN HS CODE
---------------------------------------------------
Statistics Canada publishes a commodity as a single string that joins two different things:

    3001100090 - Glands, nes, and other organs, dried, powdered or not, for therapeutic uses

The number is the HS code. The text after it is the description. They are separable and they
change independently. A code can keep its number while its description is rewritten, and
Statistics Canada does rewrite descriptions without any change to the goods.

That is why the inventory carries one record per code AND description pair, not one per code.
A code whose description changed is two records, because the two periods may need to be traced
separately. Whether they are in fact the same commodity is a question for a later stage. This
stage only records that both exist.


THE FORMATTING TRAP THIS STAGE EXISTS TO CLOSE
-----------------------------------------------
The delivery writes HS codes without separators, as 3001100090. Earlier work in this project
wrote them with separators, as 3001.10.00.90. The two forms look alike to a reader and are
completely different to a computer.

Five places in the previous pipeline assumed separators were present. Four of them failed
silently: a comparison simply never matched, and the code carried on with an empty result and
no error. The most damaging example took the first two dot-separated parts of a code to obtain
its subheading. Given 3001.10.00.90 that yields 3001.10, which is correct. Given 3001100090 it
yields the entire code, so a check meant to confirm that two commodities sat under the same
subheading compared a full code against a full code and passed nothing.

This stage therefore converts every code to one internal form and refuses to continue if any
code fails to convert. The internal form is digits only, with no separators, because that is
what the source provides and it needs no interpretation. Separators are a presentation choice
and are added once, at the final stage that writes the released files.


WHAT WOULD MAKE THIS STAGE WRONG
--------------------------------
Stated before the numbers are reported, so that the check has something to test:

  - A commodity string that does not split cleanly into a number and a description would be
    dropped or mangled. The split is asserted rather than assumed.
  - A source that begins later than it should would silently truncate history. The export
    crosswalk released in 2026 was built from an extract beginning in 2000-01 while trade
    exists from 1988-01, and twelve years of history went missing without any error. The
    earliest period is therefore asserted against the expected start.
  - Reading the wrong file would reproduce that same truncation. The frozen extracts kept for
    regression sit in baseline_v1, so this stage refuses any path inside that directory.
"""

import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# The project root is the directory above this file's parent, so the pipeline can be run from
# anywhere without depending on the working directory or on any user-specific location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = PROJECT_ROOT / "source"
WORK_DIR = PROJECT_ROOT / "work"

# The frozen copies of the extracts the previous release was built from. They are kept so that
# the new pipeline can be run against the old data as a diagnostic, which isolates a change in
# the code from a change in the data. They must never be an input to a release build: the
# export extract begins in 2000-01 and building from it would reimpose the truncation this
# rebuild exists to remove.
FORBIDDEN_INPUT_DIR = PROJECT_ROOT / "baseline_v1"

# Every commodity in Chapter 30 trade should exist from the first month the delivery covers,
# or later if the code was introduced later. No commodity may appear to start before this.
DELIVERY_FIRST_PERIOD = "198801"

FLOWS = {
    "imports": {
        "database": SOURCE_DIR / "imports.db",
        "table": "imports",
        "code_length": 10,
        "description": "Statistics Canada CIMT imports, ten-digit commodity codes",
    },
    # TOTAL EXPORTS, re-exports included, on the analyst's instruction of 2026-08-31. The
    # analysis is to cover all trade that crosses the border, not only goods made in Canada.
    #
    # What this costs, recorded because it is not visible from here. exports.db carries NO
    # provincial data at all: province is 0 of 240,550 rows, against 100% and 15 provinces in
    # domestic_exports.db. Nothing in the crosswalk reads province, so no stage or check is
    # affected, but a province-level export view cannot be built from this extract.
    #
    # It also moves the published total, and THREE figures are needed to see how, not two.
    # CAD 179,100,857,500 in the manuscript reconciles to the dollar against the domestic basis
    # over 2000-01 to 2026-02, the period the released extract covered (see
    # reports/FINDINGS_export_rescope_2026-08-07.md section 4). This delivery is longer, 1988-01
    # to 2026-06, and on the domestic basis it totals CAD 190,906,721,014. Total exports give
    # CAD 216,729,045,491 over that same delivery. The re-export difference is therefore
    # 216,729,045,491 - 190,906,721,014 = CAD 25,822,324,477. Subtracting from the manuscript's
    # 179.1 billion instead gives 37.6 billion and mixes a period change into a basis change;
    # an earlier version of this comment invited exactly that by naming only 179.1 and 25.8.
    "exports": {
        "database": SOURCE_DIR / "exports.db",
        "table": "exports",
        "code_length": 8,
        "description": "Statistics Canada CIMT total exports, re-exports included, "
                       "eight-digit commodity codes",
    },
}


class SourceError(Exception):
    """Raised when a source file is unusable or is not the file this stage should read."""


def refuse_forbidden_input(path):
    """
    Stop the run if the path sits inside the frozen regression directory.

    This is deliberately a hard failure rather than a warning. A release build that quietly
    read the frozen 2000-01 export extract would produce a complete-looking crosswalk missing
    twelve years of history, and would report success while doing it.
    """
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(FORBIDDEN_INPUT_DIR.resolve())
    except ValueError:
        return  # Not inside the frozen directory, which is what we want.
    raise SourceError(
        "Refusing to read %s. Files under baseline_v1 are the frozen extracts the previous "
        "release was built from. They are kept for regression comparison only and must never "
        "be an input to a release build." % resolved
    )


# Statistics Canada appends a status note to the description of a code that has been retired or
# introduced, for example "Vaccines for human medicine (Terminated 2021-12)". The note states
# what happened to the code. It does not describe the goods.
#
# Keeping it inside the description would corrupt every later comparison. A retired code whose
# description is otherwise word for word identical to its successor scores 0.7397 against that
# successor with the note attached, and 1.0000 without it. The first figure sits below the
# threshold at which a link is made automatically, so a perfect match would be demoted to
# manual review by a note about the code's status. Three hundred and eighteen of the four
# hundred and seventy-five import descriptions carry such a note.
#
# The note is therefore removed from the description and kept in its own field, because what it
# claims is worth having. Statistics Canada's stated termination month can disagree with the
# month trade actually stops, and a disagreement is a fact about the source worth surfacing
# rather than quietly resolving.
STATED_TERMINATION = re.compile(r"\(Terminated\s+(\d{4})-(\d{2})\)")
STATED_INTRODUCTION = re.compile(r"\(Introduced\s+(\d{4})-(\d{2})\)")


def longest_quiet(period_list):
    """The longest run of months with no trade that this code later traded again after.

    Bounded by trade on both sides, so the silence at the end of the delivery is never counted
    as evidence about itself.
    """
    months = sorted({p for p in (period_list or "").split(",") if p})
    worst = 0
    for earlier, later in zip(months, months[1:]):
        apart = ((int(later[:4]) - int(earlier[:4])) * 12
                 + int(later[4:]) - int(earlier[4:]) - 1)
        if apart > worst:
            worst = apart
    return worst


def split_commodity_string(commodity):
    """
    Separate a Statistics Canada commodity string into its parts.

    The published form joins a code and a description with a space, hyphen, space, and the
    description may carry a status note:

        3001100090 - Glands, nes, and other organs, dried, powdered or not (Terminated 2006-12)

    Returns four values: the code as digits only, the description with any status note removed,
    the stated termination month, and the stated introduction month. The two months are empty
    strings when the source states nothing.

    Raises rather than guessing if the string does not contain both a code and a description,
    because a silently mangled code produces a commodity that matches nothing and is very hard
    to notice later.
    """
    if " - " not in commodity:
        raise SourceError(
            "Commodity string does not contain the expected ' - ' separator between the code "
            "and the description: %r" % commodity
        )
    code_part, description = commodity.split(" - ", 1)
    code_digits = re.sub(r"\D", "", code_part)
    if not code_digits:
        raise SourceError("No digits found in the code portion of: %r" % commodity)

    stated_termination = ""
    stated_introduction = ""

    termination_match = STATED_TERMINATION.search(description)
    if termination_match:
        stated_termination = "%s%s" % (termination_match.group(1), termination_match.group(2))
        description = STATED_TERMINATION.sub("", description)

    introduction_match = STATED_INTRODUCTION.search(description)
    if introduction_match:
        stated_introduction = "%s%s" % (introduction_match.group(1), introduction_match.group(2))
        description = STATED_INTRODUCTION.sub("", description)

    # Collapse only the whitespace the removal leaves behind. Punctuation is left exactly as the
    # source wrote it, including a trailing comma.
    #
    # That looks untidy and it is deliberate. Statistics Canada records one commodity under two
    # strings that differ by a single comma before the status note, and it splits the periods
    # between them at 2002-01. Tidying the comma away merges the two into one record, changes
    # the import commodity count from 475 to 474, and breaks agreement with the released
    # crosswalk. Whether those two records describe one commodity or two is a judgement about
    # the goods. This stage reads and counts, so it preserves every distinction the source makes
    # and leaves the judgement to a stage that is allowed to make one.
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        raise SourceError("Commodity string has no description once the status note is removed: %r" % commodity)

    return code_digits, description, stated_termination, stated_introduction


def heading_of(code_digits):
    """
    The four-digit heading a code belongs to. 3001100090 gives 3001, printed as heading 30.01.

    A heading is the broadest grouping used here. All glands and organs for therapeutic use sit
    under heading 3001 regardless of how the ten-digit code beneath it has been renumbered.
    """
    return code_digits[:4]


def subheading_of(code_digits):
    """
    The six-digit subheading a code belongs to. 3001100090 gives 300110.

    Subheadings are set internationally by the World Customs Organization and are the level at
    which its correlation tables state what became what across a revision. The digits beyond
    six are chosen by each country, so they carry no international meaning.
    """
    return code_digits[:6]


def read_commodity_records(flow_name, settings):
    """
    Read one flow's database and return one record per commodity code and description pair.

    The database is grouped in SQL rather than in Python because the row counts run to hundreds
    of thousands per flow and the grouping is exactly what a database is for.
    """
    database = settings["database"]
    refuse_forbidden_input(database)
    if not database.exists():
        raise SourceError("Source database not found: %s" % database)

    connection = sqlite3.connect(str(database))
    query = (
        "select commodity, min(period), max(period), count(*), sum(value), "
        "count(distinct period), group_concat(distinct period) from %s "
        "group by commodity" % settings["table"]
    )

    records = []
    for (commodity, first_period, last_period, row_count, total_value, months,
         period_list) in connection.execute(query):
        code_digits, description, stated_termination, stated_introduction = split_commodity_string(commodity)

        # The assertion the plan calls for: every code converts to the one internal form, and
        # that form has the length this flow uses. Imports are ten digits, domestic exports are
        # eight. A code of any other length means the source is not what it is believed to be.
        if len(code_digits) != settings["code_length"]:
            raise SourceError(
                "Commodity %r produced a %d-digit code, but %s codes are %d digits. The source "
                "may not be the file this stage expects."
                % (commodity, len(code_digits), flow_name, settings["code_length"])
            )

        records.append(
            {
                "hs_code": code_digits,
                "description": description,
                "heading": heading_of(code_digits),
                "subheading": subheading_of(code_digits),
                "first_period": first_period,
                "last_period": last_period,
                "months_with_trade": months,
                # THE LONGEST SILENCE THIS CODE HAS ALREADY COME BACK FROM. Recorded here
                # because this is the only stage that reads month-level records; everything
                # downstream sees a summary. Without it a later stage measured gaps between
                # description changes and called a code with 240 unbroken trading months sparse.
                # What silence means depends on how often a code ever traded: 3003.42.00 traded
                # 4 months out of 65 and has survived a 49-month gap, so 21 months of quiet is
                # not a retirement.
                "longest_quiet_months": longest_quiet(period_list),
                "source_rows": row_count,
                "total_value_cad": round(total_value or 0, 2),
                "stated_termination": stated_termination,
                "stated_introduction": stated_introduction,
                # Whether Statistics Canada's stated termination month agrees with the month
                # trade is actually last observed. The two can differ, and which one is right
                # is a question for a later stage. Recording the disagreement here means no
                # later stage has to rediscover it.
                "stated_termination_matches_data": (
                    "" if not stated_termination else ("yes" if stated_termination == last_period else "no")
                ),
            }
        )

    connection.close()
    records.sort(key=lambda r: (r["hs_code"], r["first_period"]))

    # WHOSE TERMINATION IS IT? Statistics Canada attaches "(Terminated YYYY-MM)" to the COMMODITY
    # STRING, and a recycled number carries the note on EVERY life it ever had. Exports 30029020
    # is two commodities: human blood to 1988-12, then Saxitoxin from 2000-10 to 2016-11. Both
    # strings read "(Terminated 2016-12)", so the 1988 life inherits a note describing something
    # twenty-eight years later.
    #
    # Recorded here rather than rediscovered, because three separate stages read this note and one
    # of them decides whether a stoppage is a retirement at all. A note belongs to a later life
    # when it lands at or after that life's first month; anything else is the ordinary case where
    # money stopped a few months before the classification did, which is the M4 pattern and NOT a
    # misattribution. Finding 105.
    later_starts = defaultdict(list)
    for record in records:
        later_starts[record["hs_code"]].append(record["first_period"])
    for record in records:
        note = record["stated_termination"]
        after = [f for f in later_starts[record["hs_code"]] if f > record["last_period"]]
        record["stated_termination_is_this_life"] = (
            "" if not note else ("no" if after and note >= min(after) else "yes"))
    return records


def punctuation_twin_groups(records):
    """
    Group the records that differ from another only in punctuation, and return the groups.

    Two records under one code whose descriptions use the same words in the same order, and
    differ only in the marks between them, are almost certainly one commodity recorded two ways.
    Statistics Canada rewrote punctuation across Chapter 30 without changing the goods, and 21
    of the import pairs split at exactly 2002-01.

    The spaces are removed along with the punctuation. An earlier version of this key kept them,
    so it could see whether a mark was present but not where a space sat. It read
    "eyes,ears & respiratory" and "eyes, ears&respiratory" as two different wordings. That
    under-reported the finding as 22 groups when 25 exist, and left out three groups worth
    CAD 11,472,590,012, while every control in the check suite passed.

    Grouping is not merging. The inventory still holds 475 import records after this runs.
    Whether a pair is one commodity or two is a judgement about the goods, and it belongs to a
    stage that is allowed to make one.

    This is a function rather than inline code so the check can call it and compare what the
    stage reports against its own independent count.
    """
    grouped = defaultdict(list)
    for record in records:
        key = (record["hs_code"], re.sub(r"[^a-z0-9]", "", record["description"].lower()))
        grouped[key].append(record)
    return {key: group for key, group in grouped.items() if len(group) > 1}


def declared_period_range(database, table):
    """What the source says its own coverage is, from the `metadata` table it ships with.

    PRESENT IN ALL THREE DATABASES AND READ BY NOTHING until 2026-08-16. Every derived figure in
    this stage is recomputed FROM the rows, so a truncated extract agrees with itself and every
    control passes on it. This is the one fact in the delivery that does not come from the rows,
    which is exactly why it can catch a source that stops early.

    Returns None where the table is absent, so an older extract still runs rather than failing on
    a fact it never carried; the caller then falls back to asserting only the start.
    """
    connection = sqlite3.connect("file:%s?mode=ro" % database, uri=True)
    try:
        rows = connection.execute(
            "select name from sqlite_master where type='table' and name='metadata'").fetchall()
        if not rows:
            return None
        found = connection.execute("select period_min, period_max from metadata").fetchone()
        return (found[0], found[1]) if found and found[0] and found[1] else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def describe_inventory(flow_name, records, database=None, table=None):
    """
    Print the range of every field derived from the source, and check the ranges are possible.

    Printing the extremes is a deliberate habit rather than decoration. A previous check in this
    project read the earliest year present in a set of tariff schedules as though it were the
    year each code was introduced. The schedules begin in 2005, so every code already in force
    reported 2005 as its birth year, and the check produced 195 findings that were artefacts of
    where the data started rather than facts about the codes.

    The same failure is possible here and in the same direction, which is why the earliest
    period is compared against the period the delivery is known to start.
    """
    first_periods = [r["first_period"] for r in records]
    last_periods = [r["last_period"] for r in records]
    values = [r["total_value_cad"] for r in records]

    earliest = min(first_periods)
    latest = max(last_periods)

    print("  commodity records (code and description pairs) : %d" % len(records))
    print("  distinct HS codes                              : %d" % len({r["hs_code"] for r in records}))
    print("  distinct headings                              : %d" % len({r["heading"] for r in records}))
    print("  distinct subheadings                           : %d" % len({r["subheading"] for r in records}))
    print("  earliest first period                          : %s" % earliest)
    print("  latest last period                             : %s" % latest)
    print("  source rows read                               : {:,}".format(sum(r["source_rows"] for r in records)))
    print("  total value                                    : CAD {:,.0f}".format(sum(values)))
    print("  smallest commodity by value                    : CAD {:,.0f}".format(min(values)))
    print("  largest commodity by value                     : CAD {:,.0f}".format(max(values)))

    if earliest != DELIVERY_FIRST_PERIOD:
        raise SourceError(
            "The earliest commodity in %s begins at %s, but the delivery is expected to begin "
            "at %s. A later start means the source has been truncated, which is the defect that "
            "removed twelve years of export history from the previous release."
            % (flow_name, earliest, DELIVERY_FIRST_PERIOD)
        )

    # AND THE MONTH IT ENDS, which was asserted nowhere until 2026-08-16. The start has been
    # guarded since this stage was written because truncating the START is the defect that cost
    # the previous release twelve years of export history. Truncating the END is the same defect
    # from the other side and nothing looked for it: a source cut to 2025-12 passed every one of
    # this check's controls while losing CAD 18,085,120,609, because every control recomputes
    # from the same truncated database and therefore agrees with it.
    #
    # The answer was present and unread the whole time. All three databases carry a `metadata`
    # table declaring period_min and period_max, and nothing in pipeline/ or checks/ opened it.
    # Reading it makes the source state its own extent and then holds it to that, which no
    # recomputation from the rows can do.
    declared = declared_period_range(database, table) if database else None
    if declared and latest != declared[1]:
        raise SourceError(
            "The latest commodity in %s ends at %s, but %s declares its own coverage as %s to %s. "
            "A source that stops before it says it does has been truncated, and every figure "
            "derived from it will be short without anything failing."
            % (flow_name, latest, Path(database).name, declared[0], declared[1])
        )
    if declared and earliest != declared[0]:
        raise SourceError(
            "The earliest commodity in %s begins at %s, but %s declares its coverage as starting "
            "at %s." % (flow_name, earliest, Path(database).name, declared[0])
        )

    with_note = [r for r in records if r["stated_termination"]]
    disagreeing = [r for r in with_note if r["stated_termination_matches_data"] == "no"]
    print("  descriptions carrying a stated termination     : %d" % len(with_note))
    print("     (the note is removed from the description and kept in its own field, because it")
    print("      states the code's status and does not describe the goods)")
    print("  stated termination disagrees with the data     : %d" % len(disagreeing))
    if disagreeing:
        for r in disagreeing[:5]:
            print("      %s stated %s, trade last seen %s  %s"
                  % (r["hs_code"], r["stated_termination"], r["last_period"], r["description"][:44]))

    # Two records whose descriptions differ only by punctuation are almost certainly one
    # commodity recorded two ways. They are reported, not merged, because merging is a decision.
    # The grouping and the reasoning behind it live in punctuation_twin_groups above.
    punctuation_twins = punctuation_twin_groups(records)
    twin_records = sum(len(v) for v in punctuation_twins.values())
    twin_value = sum(r["total_value_cad"] for group in punctuation_twins.values() for r in group)
    print("  records differing from another only by punctuation: %d in %d groups"
          % (twin_records, len(punctuation_twins)))
    print("  value carried by those records                 : CAD {:,.0f}".format(twin_value))
    for key, group in punctuation_twins.items():
        print("     %s appears %d times with the same words:" % (key[0], len(group)))
        for r in group:
            print("        %s..%s  %r" % (r["first_period"], r["last_period"], r["description"][-46:]))
        print("        (reported only. Merging these is a judgement about the goods and belongs")
        print("         to a stage that is allowed to make one)")

    still_tagged = [r for r in records if "(Terminated" in r["description"] or "(Introduced" in r["description"]]
    if still_tagged:
        raise SourceError(
            "%d descriptions still contain a status note after parsing, for example %r. A note "
            "left inside a description corrupts every later comparison."
            % (len(still_tagged), still_tagged[0]["description"])
        )

    codes_starting_at_edge = sum(1 for r in records if r["first_period"] == earliest)
    print("  commodities present in the first month         : %d" % codes_starting_at_edge)
    print("     (a commodity present in the first month of the data has no observable birth,")
    print("      so no later stage may treat that month as the month it was introduced)")


def write_inventory(flow_name, records):
    WORK_DIR.mkdir(exist_ok=True)
    destination = WORK_DIR / ("commodity_inventory_%s.csv" % flow_name)
    columns = [
        "hs_code",
        "description",
        "heading",
        "subheading",
        "first_period",
        "last_period",
        "months_with_trade",
        "longest_quiet_months",
        "source_rows",
        "total_value_cad",
        "stated_termination",
        "stated_introduction",
        "stated_termination_matches_data",
    "stated_termination_is_this_life",
    ]
    with open(destination, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    return destination


def main():
    print("Stage 0. Reading the trade delivery and building the commodity inventory.")
    print()
    for flow_name, settings in FLOWS.items():
        print("%s: %s" % (flow_name, settings["description"]))
        print("  source: %s" % settings["database"].relative_to(PROJECT_ROOT))
        records = read_commodity_records(flow_name, settings)
        describe_inventory(flow_name, records,
                           settings["database"], settings["table"])
        destination = write_inventory(flow_name, records)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()
    print("Stage 0 complete. No commodity has been linked to any other at this point.")


if __name__ == "__main__":
    try:
        main()
    except SourceError as error:
        print("Stage 0 stopped: %s" % error, file=sys.stderr)
        sys.exit(1)
