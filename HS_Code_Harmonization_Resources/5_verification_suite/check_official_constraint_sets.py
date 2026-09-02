"""
Check for the official constraint sets. Do they describe the delivery, and can they still fire?


Inputs:
    decisions/official_constraint_sets.csv
    work/commodity_inventory_exports.csv     produced by pipeline/stage0_read_source.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


WHAT A CONSTRAINT SET IS
------------------------
For five export codes the official record cannot name the successor, but it can bound the
answer. 30049000 became one of exactly two codes. Which one is unknown; that it is one of those
two is not. A bound of that kind is worth far more than ranking every candidate by text, and at
these five boundaries it is the only official evidence there is.

Stage 1 uses a set to REJECT candidates outside it, and to force the answer where exactly one
forward destination remains. It never reads membership as proof that a succession happened.


EVERY ROW CARRIES AN INSTRUCTION, NOT ONLY A FACT
--------------------------------------------------
The first version of this file recorded what was true and left every consequence in prose. A
later stage would have had to re-derive each one from a note column, which no code reads. The
`stage1_action` column now states the consequence:

    constrain                 reject any candidate outside the set
    constrain_not_succession  reject outside the set, and do not treat this as a retirement
    constrain_and_rule        reject outside the set, and raise it for a human ruling


WHY THE SET IS NEVER NARROWED TO WHAT THE DATA SHOWS
-----------------------------------------------------
30034300 is an official destination with no Canadian export trade at all between 1988 and 2026.
It is not a phantom: the same code is imported, and appears in the import inventory as
3003430000. Dropping it because nothing was exported would confuse two different statements,
what the tariff permits and what exporters happened to do. The set keeps all four. The absence
is recorded in its own column and asserted below, so it stays visible rather than becoming
folklore.


THE TWO SETS THAT CONTAIN THEIR OWN SOURCE ARE NOT THE SAME CASE
------------------------------------------------------------------
30039000 and 30049000 each list themselves among their destinations, and an earlier version of
this file gave both the same flag. That flag hid the only thing about them that matters.

30039000 is still trading at 2026-06, the last month the delivery covers. It never retired, so
its set bounds where trade may have moved rather than where a dead code went.

30049000 retired at 2017-12 and is the largest object in the export crosswalk at
CAD 62,379,640,484. Removing itself leaves one forward destination, 30046000, which carries
CAD 36,444,266. That is 0.0584 per cent of the source. The gap is asserted below so it cannot
drift unnoticed, and the row is marked as requiring a ruling. It is deliberately not resolved
here, and it must not be resolved by comparing sizes.


WHAT WOULD MAKE THIS FILE WRONG
--------------------------------
Stated before the numbers, so the controls have something to test:

  - A set that quietly loses a destination would let Stage 1 reject a legitimate successor.
  - A source or destination that does not exist in the delivery would be a transcription error
    no later stage could catch.
  - An empty set would silently reject every candidate.
  - A source recorded as retired while it is still trading would turn a live code into a dead
    one, which is the error that produced 30039000's flag in the first place.
  - An action that does not match the row's status would send the wrong instruction downstream.
"""

import csv
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS_FILE = os.path.join(PROJECT, "decisions", "official_constraint_sets.csv")
INVENTORY = os.path.join(PROJECT, "work", "commodity_inventory_exports.csv")

EXPORT_CODE_LENGTH = 8
VALID_ACTIONS = {"constrain", "constrain_not_succession", "constrain_and_rule"}
VALID_STATUS = {"retired", "still_trading"}

# Pinned from the delivery on 2026-08-10. These move only when the delivery or the official
# record moves, never because a run produced something different.
EXPECTED_SOURCES = 5
EXPECTED_DESTINATIONS = 18
EXPECTED_ABSENT = {"30034300"}
EXPECTED_SELF_REFERENTIAL = {"30039000", "30049000"}
EXPECTED_RULINGS = {"30049000"}
# The unexplained gap on the largest object in the export crosswalk, as a percentage.
GAP_SOURCE = "30049000"
# RE-PINNED 2026-08-31 with the export basis. The forward gap on 30049000 is measured
# against a larger denominator now that re-exports are counted, so the percentage moved.
GAP_EXPECTED_PCT = 0.0646
GAP_TOLERANCE_PCT = 0.0001

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  -- " + detail) if detail else ""))


def must_raise(name, function, *args):
    """A guard that cannot fire is not a guard, so each one is provoked."""
    try:
        function(*args)
    except ValueError as error:
        record(name, True, "refused as intended: %s" % error)
        return
    record(name, False, "accepted input it should have refused")


def parse_row(row):
    """Validate one row and return its parts, or raise. This is the guard the controls provoke."""
    source = (row.get("source_code") or "").strip()
    dests = [d.strip() for d in (row.get("official_destinations") or "").split(";") if d.strip()]
    forward = [d.strip() for d in (row.get("forward_destinations") or "").split(";") if d.strip()]
    status = (row.get("source_status") or "").strip()
    action = (row.get("stage1_action") or "").strip()
    if len(source) != EXPORT_CODE_LENGTH or not source.isdigit():
        raise ValueError("source code %r is not %d digits" % (source, EXPORT_CODE_LENGTH))
    if not dests:
        raise ValueError("source %s has an empty destination set, which would reject everything" % source)
    for d in dests:
        if len(d) != EXPORT_CODE_LENGTH or not d.isdigit():
            raise ValueError("destination %r of source %s is not %d digits" % (d, source, EXPORT_CODE_LENGTH))
    if int(row.get("official_count") or 0) != len(dests):
        raise ValueError("source %s states a count of %s but lists %d destinations"
                         % (source, row.get("official_count"), len(dests)))
    if status not in VALID_STATUS:
        raise ValueError("source %s has status %r, which is not one of %s"
                         % (source, status, sorted(VALID_STATUS)))
    if action not in VALID_ACTIONS:
        raise ValueError("source %s has action %r, which is not one of %s"
                         % (source, action, sorted(VALID_ACTIONS)))
    if sorted(forward) != sorted(d for d in dests if d != source):
        raise ValueError("source %s lists forward destinations that are not its set minus itself" % source)
    return source, dests, forward, status, action


print("Check for the official constraint sets. Do they describe the delivery?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
GOOD = {"source_code": "30021000", "official_destinations": "30021100;30021200",
        "forward_destinations": "30021100;30021200", "official_count": "2",
        "source_status": "retired", "stage1_action": "constrain"}


def variant(**changes):
    row = dict(GOOD)
    row.update(changes)
    return row


must_raise("a source code of the wrong length is refused", parse_row, variant(source_code="300210"))
must_raise("a destination of the wrong length is refused", parse_row,
           variant(official_destinations="3002110000", forward_destinations="3002110000", official_count="1"))
must_raise("an empty destination set is refused", parse_row,
           variant(official_destinations="", forward_destinations="", official_count="0"))
must_raise("a stated count that disagrees with the list is refused", parse_row, variant(official_count="6"))
must_raise("an unknown source status is refused", parse_row, variant(source_status="dead"))
must_raise("an unknown stage 1 action is refused", parse_row, variant(stage1_action="ignore"))
must_raise("forward destinations that are not the set minus the source are refused", parse_row,
           variant(forward_destinations="30021100"))

print()
print("Controls that MUST PASS (correct input must not be flagged):")
try:
    parse_row(GOOD)
    record("a well-formed row is accepted", True, "30021000 -> 2 destinations")
except ValueError as error:
    record("a well-formed row is accepted", False, str(error))

rows = []
try:
    with open(SETS_FILE, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    record("the constraint file reads", True, "%d row(s)" % len(rows))
except OSError as error:
    record("the constraint file reads", False, str(error))

parsed, parse_errors = {}, []
for row in rows:
    try:
        source, dests, forward, status, action = parse_row(row)
        parsed[source] = {"dests": dests, "forward": forward, "status": status, "action": action,
                          "ruling": (row.get("ruling_required") or "").strip().lower(),
                          "value": float(row.get("source_total_value_cad") or 0),
                          "last_period": (row.get("source_last_period") or "").strip()}
    except ValueError as error:
        # Collected, not broken out of. Stopping at the first failure hides how many there are,
        # and one bad row and every row bad call for very different responses.
        parse_errors.append(str(error))
record("every row passes the guards above", not parse_errors,
       "%d source(s) parsed" % len(parsed) if not parse_errors
       else "%d of %d row(s) failed. First: %s" % (len(parse_errors), len(rows), parse_errors[0]))
record("no source code appears twice", len(parsed) == len(rows),
       "%d distinct source(s) from %d row(s)" % (len(parsed), len(rows)))

print()
print("Pinned against the official record:")
all_dests = [d for v in parsed.values() for d in v["dests"]]
record("the number of constrained sources is unchanged", len(parsed) == EXPECTED_SOURCES,
       "%d, expected %d" % (len(parsed), EXPECTED_SOURCES))
record("the number of official destinations is unchanged", len(all_dests) == EXPECTED_DESTINATIONS,
       "%d, expected %d" % (len(all_dests), EXPECTED_DESTINATIONS))
record("no destination is listed twice within one set",
       all(len(v["dests"]) == len(set(v["dests"])) for v in parsed.values()),
       "checked %d set(s)" % len(parsed))

print()
print("Reconciled against the commodity inventory, which is built from the delivery:")
inventory_codes, code_value = set(), {}
try:
    with open(INVENTORY, encoding="utf-8-sig", newline="") as handle:
        for r in csv.DictReader(handle):
            inventory_codes.add(r["hs_code"])
            code_value[r["hs_code"]] = code_value.get(r["hs_code"], 0.0) + float(r["total_value_cad"])
        delivery_end = None
    with open(INVENTORY, encoding="utf-8-sig", newline="") as handle:
        delivery_end = max(r["last_period"] for r in csv.DictReader(handle))
    record("the export inventory reads", True,
           "%d distinct code(s), delivery ends %s" % (len(inventory_codes), delivery_end))
except OSError as error:
    delivery_end = None
    record("the export inventory reads", False, str(error))

missing = sorted(s for s in parsed if s not in inventory_codes)
record("every constrained source exists in the delivery", not missing,
       "0 missing" if not missing else "missing %s" % missing)

observed_absent = {d for d in all_dests if d not in inventory_codes}
record("destinations absent from the data are exactly the declared ones",
       observed_absent == EXPECTED_ABSENT,
       "found %s, declared %s" % (sorted(observed_absent) or "none", sorted(EXPECTED_ABSENT)))

declared_absent = {d.strip() for row in rows
                   for d in (row.get("destinations_absent_from_data") or "").split(";") if d.strip()}
record("the absent column agrees with the inventory", declared_absent == observed_absent,
       "column says %s, inventory says %s" % (sorted(declared_absent) or "none",
                                              sorted(observed_absent) or "none"))

print()
print("Status and action, the three findings that used to live only in prose:")
self_referential = {s for s, v in parsed.items() if s in v["dests"]}
record("the self-referential sets are the two already known",
       self_referential == EXPECTED_SELF_REFERENTIAL,
       "%s, expected %s" % (sorted(self_referential), sorted(EXPECTED_SELF_REFERENTIAL)))

# The error that produced the original flag: a source still trading at the delivery's last month
# has not retired, and calling it retired would turn a live code into a dead one.
status_wrong = [s for s, v in parsed.items()
                if v["status"] != ("still_trading" if v["last_period"] == delivery_end else "retired")]
record("every source status agrees with its last traded month", not status_wrong,
       "0 disagree" if not status_wrong else "disagree: %s" % status_wrong)

mislabelled = [s for s, v in parsed.items()
               if v["status"] == "still_trading" and v["action"] != "constrain_not_succession"]
record("a source still trading is never treated as a succession", not mislabelled,
       "0 mislabelled" if not mislabelled else "mislabelled: %s" % mislabelled)

rulings = {s for s, v in parsed.items() if v["ruling"] == "yes"}
record("the rows requiring a ruling are the ones already known", rulings == EXPECTED_RULINGS,
       "%s, expected %s" % (sorted(rulings), sorted(EXPECTED_RULINGS)))
action_mismatch = [s for s, v in parsed.items()
                   if (v["ruling"] == "yes") != (v["action"] == "constrain_and_rule")]
record("every row needing a ruling carries the matching action", not action_mismatch,
       "0 mismatched" if not action_mismatch else "mismatched: %s" % action_mismatch)

# The largest object in the export crosswalk, pinned so it cannot drift on a later extract.
gap = parsed.get(GAP_SOURCE)
if gap and gap["value"]:
    forward_value = sum(code_value.get(d, 0.0) for d in gap["forward"])
    pct = 100 * forward_value / gap["value"]
    record("the unexplained gap on %s is unchanged" % GAP_SOURCE,
           abs(pct - GAP_EXPECTED_PCT) < GAP_TOLERANCE_PCT,
           "forward CAD {:,.0f} of CAD {:,.0f} = {:.4f} per cent, expected {:.4f}".format(
               forward_value, gap["value"], pct, GAP_EXPECTED_PCT))
else:
    record("the unexplained gap on %s is unchanged" % GAP_SOURCE, False, "row not found")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if failed:
    print()
    print("The constraint sets are NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("The constraint sets are validated. They describe the delivery and every guard can fire.")
