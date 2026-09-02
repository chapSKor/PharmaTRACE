"""
Check for Stage 0. Does the commodity inventory faithfully describe the delivery?


Inputs:
    work/commodity_inventory_imports.csv     produced by pipeline/stage0_read_source.py
    work/commodity_inventory_exports.csv
    source/imports.db, source/domestic_exports.db
    baseline_v1/source/Chapter30_IMPORTS_1988-2026_byMonth.csv    an independent witness
    baseline_v1/source/Chapter30_EXPORT_2000-2026_byMonth.csv

Output:
    A pass or fail line for each control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Does the commodity inventory list every commodity in the delivery, exactly once, with the
correct first month, last month and value?


WHY IT IS BUILT THE WAY IT IS
-----------------------------
A check that compares an artefact against the same data that built it proves only that the code
ran without crashing. This project has twice had a check report problems that did not exist,
and in both cases the check confirmed that the code did what it was told rather than that what
it was told was right.

So this check does three separate things:

  1. It rebuilds the totals from the raw database rows in Python, without the SQL grouping the
     stage relies on. If the two disagree, the grouping is wrong.

  2. It compares the commodity universe against the frozen extracts in baseline_v1. Those are a
     genuinely independent witness: different files, different format, extracted on a different
     date by a different process. They are read here and only here, for comparison, never as an
     input to a build.

  3. It feeds deliberately broken input to the stage's own guards and requires each one to
     refuse. A guard that has never been observed to fire is not known to work.

Controls that must flag are listed as MUST FAIL. Controls that must stay silent are listed as
MUST PASS. A control that cannot reach a verdict is reported as a failure, because a check that
errs toward reassurance costs a defect reaching a reviewer while one that errs toward suspicion
costs a few minutes.
"""

import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

import stage0_read_source as stage0  # noqa: E402

WORK_DIR = PROJECT_ROOT / "work"
BASELINE_SOURCE = PROJECT_ROOT / "baseline_v1" / "source"

results = []
notes = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def disclose(name, detail=""):
    """State something that could not be tested on this copy, and keep it out of the count.

    A control that cannot run must not be written as a control that passed. These print as NOTE
    and are tallied apart, so "N of N controls passed" stays a claim about N falsifiable things.
    """
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, ("  -- " + detail) if detail else ""))


def must_raise(name, function, *args, **kwargs):
    """A guard that never fires is not known to work. Require it to fire."""
    try:
        function(*args, **kwargs)
    except stage0.SourceError as error:
        record(name, True, "refused as intended: %s" % str(error).split(".")[0])
        return
    except Exception as error:  # noqa: BLE001
        record(name, False, "raised the wrong error type: %r" % error)
        return
    record(name, False, "did NOT refuse, so this guard does not work")


def load_inventory(flow):
    path = WORK_DIR / ("commodity_inventory_%s.csv" % flow)
    if not path.exists():
        record("inventory file exists for %s" % flow, False, "missing %s" % path)
        return None
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
print("Check for Stage 0. Does the commodity inventory faithfully describe the delivery?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")

# The frozen extracts must be refused as a build input. This is the guard that stops a release
# being built from the truncated 2000-01 export data.
must_raise(
    "reading a file under baseline_v1 is refused",
    stage0.refuse_forbidden_input,
    BASELINE_SOURCE / "Chapter30_EXPORT_2000-2026_byMonth.csv",
)

# A SOURCE THAT STOPS BEFORE IT SAYS IT DOES. The start of the delivery has been guarded since
# this stage was written, because truncating the START is the defect that cost the previous
# release twelve years of export history. Truncating the END is the same defect from the other
# side and nothing looked for it until 2026-08-16: a source cut to 2025-12 passed every control
# in this file while losing CAD 18,085,120,609, because each one recomputes from the same
# truncated database and therefore agrees with it.
#
# Provoked on a real copy rather than a synthetic one, because the fact being read -- the
# `metadata` table the extract ships with -- only exists on the real thing.
import os as _os                                                             # noqa: E402
import shutil as _shutil                                                     # noqa: E402
import tempfile as _tempfile                                                 # noqa: E402

_probe_dir = Path(_tempfile.mkdtemp(prefix="stage0_end_probe_"))
try:
    _probe_db = _probe_dir / "domestic_exports.db"
    _shutil.copy(PROJECT_ROOT / "source" / "domestic_exports.db", _probe_db)
    _cut = sqlite3.connect(_probe_db)
    _cut.execute("delete from domestic_exports where period > '202512'")
    _cut.commit()
    _cut.close()
    _probe_records = stage0.read_commodity_records(
        "exports", {"database": _probe_db, "table": "domestic_exports",
                    "code_length": 8, "description": "a six-month truncation"})
    must_raise(
        "a source that stops before its own metadata says it does is refused",
        stage0.describe_inventory,
        "exports", _probe_records, _probe_db, "domestic_exports",
    )
finally:
    _shutil.rmtree(_probe_dir, ignore_errors=True)

# A commodity string that cannot be split must stop the run rather than produce a mangled code.
must_raise(
    "a commodity string with no separator is refused",
    stage0.split_commodity_string,
    "3001100090 Glands and other organs",
)
must_raise(
    "a commodity string with no digits in the code is refused",
    stage0.split_commodity_string,
    "not-a-code - Glands and other organs",
)

# A source whose earliest period is later than the delivery start means truncation, which is
# exactly the defect that removed twelve years of export history from the previous release.
must_raise(
    "an inventory starting later than the delivery is refused",
    stage0.describe_inventory,
    "test",
    [
        {
            "hs_code": "3001100090",
            "description": "test",
            "heading": "3001",
            "subheading": "300110",
            "first_period": "200001",
            "last_period": "202606",
            "months_with_trade": 1,
            "source_rows": 1,
            "total_value_cad": 1.0,
        }
    ],
)

must_raise(
    "a commodity whose description is only a status note is refused",
    stage0.split_commodity_string,
    "3001100090 - (Terminated 2006-12)",
)

print()
print("Controls that MUST PASS (correct input must not be flagged):")

# A path outside the frozen directory must be allowed, otherwise the guard blocks everything.
try:
    stage0.refuse_forbidden_input(PROJECT_ROOT / "source" / "imports.db")
    record("reading a file under source is allowed", True)
except stage0.SourceError as error:
    record("reading a file under source is allowed", False, str(error))

# A well-formed commodity string must split into the digits-only code and the description.
code, description, stated_end, stated_start = stage0.split_commodity_string(
    "3001100090 - Glands, nes, and other organs, dried, powdered or not, for therapeutic uses"
)
record(
    "a well-formed commodity string splits correctly",
    code == "3001100090" and description.startswith("Glands, nes,") and stated_end == "" and stated_start == "",
    "code=%s, no status note as expected" % code,
)

# The status note must leave the description and land in its own field. This is the control
# for the defect found on 2026-08-07: a note left in place drops an otherwise exact match from
# 1.0000 to 0.7397, which is below the threshold for linking without a person.
code, description, stated_end, stated_start = stage0.split_commodity_string(
    "30022000 - Vaccines for human medicine (Terminated 2021-12)"
)
record(
    "a status note is removed from the description and kept separately",
    description == "Vaccines for human medicine" and stated_end == "202112",
    "description=%r stated_termination=%s" % (description, stated_end),
)

# The separator-free internal form must give the correct heading and subheading. This is the
# comparison that silently degenerated in the previous pipeline.
record(
    "heading and subheading are derived from the separator-free code",
    stage0.heading_of("3001100090") == "3001" and stage0.subheading_of("3001100090") == "300110",
    "heading=%s subheading=%s" % (stage0.heading_of("3001100090"), stage0.subheading_of("3001100090")),
)

print()
print("Rebuilding the totals in Python, without the grouping the stage relies on:")

# These two helpers deliberately do not call the stage. A check that reuses the code it is
# testing proves only that the code is self-consistent.
digits_only = lambda text: re.sub(r"\D", "", str(text).split(" - ")[0])


def description_without_status_note(commodity):
    """
    Remove the status note and nothing else.

    Punctuation is preserved deliberately. Statistics Canada records commodity 3004500069 under
    two strings that differ only by a comma before the note, and splits its periods between them
    at 2002-01. Tidying that comma away merges two source records into one and changes the
    import commodity count from 475 to 474. Whether they are one commodity is a judgement, and
    neither the stage nor this check is entitled to make it.
    """
    text = str(commodity).split(" - ", 1)[1]
    text = re.sub(r"\(Terminated\s+\d{4}-\d{2}\)", "", text)
    text = re.sub(r"\(Introduced\s+\d{4}-\d{2}\)", "", text)
    return re.sub(r"\s+", " ", text).strip()

for flow, settings in stage0.FLOWS.items():
    inventory = load_inventory(flow)
    if inventory is None:
        continue

    connection = sqlite3.connect(str(settings["database"]))
    rebuilt_value = defaultdict(float)
    rebuilt_first = {}
    rebuilt_last = {}
    row_total = 0
    for commodity, period, value in connection.execute(
        "select commodity, period, value from %s" % settings["table"]
    ):
        key = (digits_only(commodity), description_without_status_note(commodity))
        rebuilt_value[key] += value or 0
        if key not in rebuilt_first or period < rebuilt_first[key]:
            rebuilt_first[key] = period
        if key not in rebuilt_last or period > rebuilt_last[key]:
            rebuilt_last[key] = period
        row_total += 1
    connection.close()

    inventory_keys = {(r["hs_code"], r["description"]) for r in inventory}
    record(
        "%s: same commodity set when rebuilt row by row" % flow,
        inventory_keys == set(rebuilt_value),
        "inventory %d, rebuilt %d" % (len(inventory_keys), len(rebuilt_value)),
    )

    value_mismatches = [
        k for k in inventory_keys & set(rebuilt_value)
        if abs(float(next(r["total_value_cad"] for r in inventory if (r["hs_code"], r["description"]) == k))
               - rebuilt_value[k]) > 0.01
    ]
    record("%s: every commodity value matches to the cent" % flow, not value_mismatches,
           "%d mismatched" % len(value_mismatches))

    period_mismatches = [
        r for r in inventory
        if rebuilt_first.get((r["hs_code"], r["description"])) != r["first_period"]
        or rebuilt_last.get((r["hs_code"], r["description"])) != r["last_period"]
    ]
    record("%s: every first and last period matches" % flow, not period_mismatches,
           "%d mismatched" % len(period_mismatches))

    still_tagged = [r for r in inventory if "(Terminated" in r["description"] or "(Introduced" in r["description"]]
    record(
        "%s: no description still carries a status note" % flow,
        not still_tagged,
        "%d still tagged" % len(still_tagged),
    )

    noted = [r for r in inventory if r["stated_termination"]]
    disagreeing = [r for r in noted if r["stated_termination_matches_data"] == "no"]
    # RE-DERIVED, NOT TYPE-CHECKED. This control used to assert only that the column held "yes"
    # or "no" on every row that carries a note, which is true by construction of the writer: it
    # passed on a column recomputed against first_period, which is the M4/M6 wrong-month class,
    # and on a column hard-coded to "yes". The arithmetic is now rebuilt from the two fields it
    # is a function of, per rule 10. Finding 107.
    miscompared = [r["hs_code"] for r in inventory
                   if r["stated_termination_matches_data"]
                   != ("" if not r["stated_termination"]
                       else ("yes" if r["stated_termination"] == r["last_period"] else "no"))]
    record(
        "%s: every stated termination is compared against the data, re-derived" % flow,
        not miscompared,
        "%d note(s), %d disagreeing with the observed last month, all re-derived from the "
        "written file" % (len(noted), len(disagreeing))
        if not miscompared else "%d wrong: %s" % (len(miscompared), miscompared[:3]),
    )
    # And the companion column finding 105 added: whose life the note describes. Rebuilt the same
    # way, because a note landing at or after a LATER life's first month belongs to that life.
    lives_of = defaultdict(list)
    for r in inventory:
        lives_of[r["hs_code"]].append(r["first_period"])
    misattributed = [r["hs_code"] for r in inventory
                     if r["stated_termination_is_this_life"]
                     != ("" if not r["stated_termination"]
                         else ("no" if [f for f in lives_of[r["hs_code"]] if f > r["last_period"]]
                               and r["stated_termination"] >= min(
                                   f for f in lives_of[r["hs_code"]] if f > r["last_period"])
                               else "yes"))]
    record(
        "%s: whose life each termination note describes is re-derived and agrees" % flow,
        not misattributed,
        "%d note(s) on a life that is not the one they describe"
        % sum(1 for r in inventory if r["stated_termination_is_this_life"] == "no")
        if not misattributed else "%d wrong: %s" % (len(misattributed), misattributed[:3]),
    )

    record(
        "%s: source row count matches" % flow,
        sum(int(r["source_rows"]) for r in inventory) == row_total,
        "inventory {:,}, database {:,}".format(sum(int(r["source_rows"]) for r in inventory), row_total),
    )

# The punctuation twins are Stage 0's third finding, and until 2026-08-10 no control tested
# them. The stage under-reported them for as long as the finding existed. Its grouping key
# removed punctuation but kept the spaces around it, so a pair differing in where a space sits
# read as two different wordings. It reported 22 groups where 25 exist, and left out
# CAD 11,472,590,012 across 3 groups, while all 25 controls passed.
#
# Three counts must agree here, not two, and each catches something the others cannot.
#
# The pinned figures describe the delivery and move only when the delivery moves. The
# independent count is written out below and shares no code with the stage. The stage's own
# function is called last and compared against both.
#
# Checking only the independent count against the pinned figures would pass while the stage
# still printed 22 groups, because the stage's report is not the inventory. Checking only the
# stage against an independent count that mirrors it would agree with the stage even when the
# stage is wrong, which is precisely how the drift survived 25 passing controls.
EXPECTED_TWINS = {
    "imports": {"groups": 25, "records": 50, "value": 42982705212},
    "exports": {"groups": 0, "records": 0, "value": 0},
}

ALPHANUMERIC = "abcdefghijklmnopqrstuvwxyz0123456789"


def twin_totals(groups):
    return {
        "groups": len(groups),
        "records": sum(len(group) for group in groups.values()),
        "value": round(sum(float(r["total_value_cad"]) for group in groups.values() for r in group)),
    }


independent_twins = {}
stage_twins = {}
for flow in stage0.FLOWS:
    inventory = load_inventory(flow) or []

    # Spelled out with no regular expression and no shared helper, so one fault cannot hide in
    # both this count and the stage's.
    grouped = defaultdict(list)
    for r in inventory:
        signature = "".join(ch for ch in r["description"].lower() if ch in ALPHANUMERIC)
        grouped[(r["hs_code"], signature)].append(r)
    independent_twins[flow] = twin_totals({k: v for k, v in grouped.items() if len(v) > 1})

    stage_twins[flow] = twin_totals(stage0.punctuation_twin_groups(inventory))

record(
    "punctuation twins agree: stage, independent count and pinned figures",
    independent_twins == EXPECTED_TWINS and stage_twins == EXPECTED_TWINS,
    "imports {groups} groups / {records} records / CAD {value:,}".format(**independent_twins["imports"])
    + ", exports {groups} groups".format(**independent_twins["exports"])
    + (", stage agrees" if stage_twins == independent_twins
       else ", STAGE DISAGREES %r" % (stage_twins,)),
)

print()
print("Probes: branches this delivery never reaches, exercised on input it does not contain.")
# Statistics Canada writes "(Introduced YYYY-MM)" as well as "(Terminated YYYY-MM)". The parser
# handles both, and not one of the 572 descriptions in this delivery carries an introduction
# note, so that half has never run on real data. A later extract may well carry one.
try:
    code, desc, term, intro = stage0.split_commodity_string(
        "3002150000 - Immunological products, put up in measured doses (Introduced 2022-01)")
    record("probe: an introduction note is parsed out of the description",
           intro == "202201" and "Introduced" not in desc and term == "",
           "introduced=%s, description=%r" % (intro, desc))
except Exception as error:
    record("probe: an introduction note is parsed out of the description", False, str(error))
try:
    code, desc, term, intro = stage0.split_commodity_string(
        "3002150000 - Vaccines (Introduced 2017-01) (Terminated 2021-12)")
    record("probe: both notes on one description are parsed and both removed",
           intro == "201701" and term == "202112" and "(" not in desc,
           "introduced=%s terminated=%s description=%r" % (intro, term, desc))
except Exception as error:
    record("probe: both notes on one description are parsed and both removed", False, str(error))

print()
print("Comparing against the frozen extracts, an independent witness:")

WITNESSES = {
    "imports": (BASELINE_SOURCE / "Chapter30_IMPORTS_1988-2026_byMonth.csv", None),
    "exports": (BASELINE_SOURCE / "Chapter30_EXPORT_2000-2026_byMonth.csv", "200001"),
}

for flow, (witness_path, witness_starts) in WITNESSES.items():
    inventory = load_inventory(flow)
    if inventory is None or not witness_path.exists():
        record("%s: frozen extract available" % flow, False, "missing %s" % witness_path)
        continue

    witness_keys = set()
    with open(witness_path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            commodity = row.get("Commodity")
            if not commodity or " - " not in commodity:
                continue  # the file carries a trailer row holding a source URL
            code = digits_only(commodity)
            text = re.sub(r"\s*\(Terminated[^)]*\)", "", commodity.split(" - ", 1)[1])
            witness_keys.add((code, re.sub(r"\s+", " ", text).strip().lower()))

    inventory_keys = {
        (r["hs_code"], re.sub(r"\s*\(Terminated[^)]*\)", "", r["description"]).strip().lower())
        for r in inventory
    }

    # The witness cannot contain anything the delivery lacks. If it does, the delivery is
    # missing a commodity that was previously published, which would be serious.
    only_in_witness = witness_keys - inventory_keys
    record(
        "%s: nothing in the frozen extract is missing from the inventory" % flow,
        not only_in_witness,
        "%d only in the frozen extract" % len(only_in_witness),
    )

    # The reverse is expected for exports and not for imports, and the expectation is stated
    # rather than discovered: the frozen export extract begins in 2000-01, so commodities that
    # retired before then are legitimately absent from it.
    only_in_inventory = inventory_keys - witness_keys
    if witness_starts:
        record(
            "%s: extra commodities in the inventory all retired before the frozen extract begins" % flow,
            len(only_in_inventory) == 19,
            "%d extra, expected 19 pre-%s retirements" % (len(only_in_inventory), witness_starts),
        )
    else:
        record(
            "%s: inventory and frozen extract hold the same commodity set" % flow,
            not only_in_inventory,
            "%d only in the inventory" % len(only_in_inventory),
        )

print()
print("The export flow reads the TOTAL-EXPORTS extract, and a swap would fail on a number:")
# WHY THIS EXISTS. Two export extracts sit in source/ and they differ by CAD 25.8 billion, which
# is the re-exports. Nothing that could fail said which one the export flow reads: substituting
# the other passed all 28 stage-0 controls, because the only pinned figure in this file is the
# one from finding 3 and it does not move with the source. A comment naming the right file is
# not a control.
#
# THE DIRECTION OF THIS TEST WAS REVERSED ON 2026-08-31, on the analyst's instruction that the
# analysis cover all trade crossing the border rather than only goods made in Canada. It read
# domestic_exports.db until then. The reversal is deliberate; if a future reader finds the
# inventory totalling the domestic extract, that is the regression this control now catches.
#
# The second control below is the one that matters. It recomputes both totals from the databases
# rather than pinning a literal, so it cannot go stale, and it fails in both directions: the
# inventory must match the total-exports extract AND must not match the domestic extract.
_export_db = stage0.FLOWS["exports"]["database"]
record("the export flow is configured to read exports.db, re-exports included",
       _export_db.name == "exports.db",
       "reads %s" % _export_db.name)
record("the import flow is configured to read imports.db",
       stage0.FLOWS["imports"]["database"].name == "imports.db",
       "reads %s" % stage0.FLOWS["imports"]["database"].name)

def _sum_value(path, table):
    with sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True) as conn:
        return conn.execute("select sum(value) from %s" % table).fetchone()[0] or 0


_inventory_total = 0.0
with open(WORK_DIR / "commodity_inventory_exports.csv", encoding="utf-8-sig",
          newline="") as _handle:
    for _row in csv.DictReader(_handle):
        _inventory_total += float(_row["total_value_cad"] or 0)
_total_total = _sum_value(_export_db, stage0.FLOWS["exports"]["table"])
# The half that must run on every copy. It recomputes both sides rather than pinning a literal,
# so it cannot go stale, and it fails on any swap to a source that does not total the same.
record("the export inventory totals the total-exports extract exactly",
       abs(_inventory_total - _total_total) < 1,
       "inventory CAD %s against total-exports CAD %s"
       % (format(int(_inventory_total), ","), format(int(_total_total), ",")))

# The second half needs the rival file to compare against. Where it is absent the comparison
# cannot be made, and saying so is the honest report; an earlier version wrote that absence as a
# passing control, which is the thing this file exists to stop.
_domestic_db = _export_db.parent / "domestic_exports.db"
if not _domestic_db.exists():
    disclose("the domestic extract is not on this copy, so the swap test could not run",
             "source/domestic_exports.db is absent. The control above still pins the inventory "
             "to %s, but nothing here proves the two extracts differ." % _export_db.name)
else:
    _domestic_total = _sum_value(_domestic_db, "domestic_exports")
    record("the export inventory does NOT total the domestic extract",
           abs(_inventory_total - _domestic_total) >= 1,
           "inventory CAD %s against domestic CAD %s"
           % (format(int(_inventory_total), ","), format(int(_domestic_total), ",")))
    record("the two export extracts are far enough apart for that test to mean something",
           abs(_domestic_total - _total_total) > 1_000_000,
           "they differ by CAD %s, which is the re-exports"
           % format(int(abs(_domestic_total - _total_total)), ","))

# ── THE PACKAGED REPRODUCTION PATH MUST ASK FOR THE DATABASES THE PIPELINE OPENS ──────────
# The stage-0 controls above prove the BUILD reads exports.db. They say nothing about the one
# command a reader is actually given, REPRODUCE.py, which copies the databases into the tree
# before any stage runs. Those were two separate lists until 2026-08-31, and the switch to
# exports.db moved only one of them: REPRODUCE.py went on demanding domestic_exports.db and
# copying it in, so the rebuild died at stage 0 looking for a file the runner had not brought.
# The end-to-end suite never caught it because it runs the stages straight from the delivery and
# does not call REPRODUCE.py at all. The template now derives the names; this holds it to that.
_template = PROJECT_ROOT / "gate1" / "reproduce_template.py"
if not _template.exists():
    disclose("the REPRODUCE.py template is not on this copy, so its source list is unchecked",
             "gate1/reproduce_template.py is absent.")
else:
    _tpl = _template.read_text(encoding="utf-8")
    _flow_dbs = [_spec["database"].name for _spec in stage0.FLOWS.values()]
    _derived = []
    for _n in re.findall(r'SOURCE_DIR\s*/\s*"([^"]+\.db)"',
                         (PROJECT_ROOT / "pipeline" / "stage0_read_source.py")
                         .read_text(encoding="utf-8")):
        if _n not in _derived:
            _derived.append(_n)
    record("REPRODUCE.py reads its database list from stage 0 rather than restating it",
           "def needed_databases" in _tpl and 'NEEDED = ("imports.db"' not in _tpl,
           "derives" if "def needed_databases" in _tpl else "carries a hardcoded list")
    record("the list REPRODUCE.py derives is exactly what the pipeline opens",
           _derived == _flow_dbs,
           "REPRODUCE.py would fetch %s; the pipeline opens %s"
           % (", ".join(_derived) or "nothing", ", ".join(_flow_dbs)))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("Stage 0 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 0 is validated. The commodity inventory faithfully describes the delivery.")
