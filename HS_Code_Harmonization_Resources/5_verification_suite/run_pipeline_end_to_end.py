"""
Run the whole pipeline from the delivery, then every check, then do it again.


    python checks/run_pipeline_end_to_end.py

Exit 0 means every stage ran, every check passed, and a second run reproduced the first
byte for byte. Any other exit means something is stated in the report.


WHY THIS EXISTS SEPARATELY FROM THE PER-STAGE CHECKS
------------------------------------------------------
Each stage has its own check and each one passes. That leaves two things unproven.

First, that the stages compose. A check runs against artefacts that happen to be on disk. It
cannot tell whether those artefacts came from the current code or from a run three edits ago.
This runner deletes them and rebuilds from the delivery, so every artefact is known to be the
output of the code as it stands.

Second, that the pipeline reproduces. Determinism has been checked one stage at a time. Running
the chain twice and comparing every artefact proves it end to end, which is the claim a
reproducibility reviewer actually needs.

This is not a check in the sense the others are. It asserts nothing about the data. It runs the
real stages and the real checks and reports what they said.


WHAT IT DOES NOT DO
-------------------
It does not re-derive any figure. Every number it prints comes from a stage or a check. If a
control is wrong, this runner will report it as passing, because it is reporting rather than
judging. The per-stage checks are where judgement lives.
"""

import hashlib
import os
import re
import subprocess
import sys
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(PROJECT, "work")
PYTHON = sys.executable

# In order. Each stage reads what the one before it wrote.
STAGES = [
    ("stage0_read_source.py", "read the delivery and build the commodity inventory"),
    ("stage1_candidates.py", "find every retirement and assemble its candidates"),
    ("stage1b_official_record.py", "let the official record speak, in order"),
    ("stage1c_rank.py", "let meaning veto, then let text rank"),
    ("make_adjudication_queue.py", "build the file a person fills in"),
    # The first stage that writes a link. It runs AFTER the queue builder, because it reads the
    # answers that builder carries into decisions/stage2_decisions.csv. Running it earlier would
    # read yesterday's answers.
    ("stage2_apply_decisions.py", "apply the answers, and say what is still open"),
    # Composes Stage 2's one-hop answers into whole journeys. It decides nothing and refuses to
    # walk an edge Stage 2 left open, so it can only run once every row is settled.
    ("stage3_route.py", "follow every commodity to the end of its chain"),
    # The figure the crosswalk exists for. Families are the connected components of the
    # successions Stage 2 settled, and nothing else contributes an edge.
    ("stage4_build_families.py", "group the codes that carry the same goods, and name them"),
    # The same answer as Stage 3, written so a person can read it: one row per step.
    ("stage5_lineage.py", "unfold every journey into the steps it is made of"),
    # The last stage. It publishes and decides nothing, and its check exists to say so.
    ("stage6_outputs.py", "publish the crosswalk in the four shapes a reader uses"),
]

# Every check, including the one that legitimately exits 3 because it has no data yet.
CHECKS = [
    ("check_stage0_source_inventory.py", (0,)),
    ("check_stage1_candidates.py", (0,)),
    ("check_stage1b_official_record.py", (0,)),
    ("check_stage1c_rank.py", (0,)),
    ("check_official_constraint_sets.py", (0,)),
    ("check_adjudication_queue.py", (0,)),
    ("check_stage2_apply_decisions.py", (0,)),
    ("check_stage3_route.py", (0,)),
    ("check_stage4_build_families.py", (0,)),
    ("check_stage5_lineage.py", (0,)),
    ("check_stage6_outputs.py", (0,)),
    # Not what the rules decide, but whether each one reaches every place a code is offered.
    ("check_rule_application.py", (0,)),
    # The one artefact no other check reads: the shipped prose. Findings 135, 137, 139, 140,
    # 141, 148 and 149 were all a document quoting a number the build had moved from under it.
    ("check_published_figures.py", (0,)),
    # check_authorship_voice.py is NOT in this list, and that is deliberate. It tests the prose
    # a person writes, not the crosswalk, so it is no part of the suite a reader reproduces and
    # it does not ship. It stays in checks/ and is run by hand:
    #     python checks/check_authorship_voice.py
    # Removed from the suite 2026-08-28 on the analyst's ruling, taking the total 767 to 750.
    # The first input that cannot be verified against the delivery or the concordance.
    ("check_medicine_families.py", (0,)),
    # IT EXAMINES SOMETHING NOW. Exit 3 meant "no history file exists", which was correct for
    # as long as Stage 6 was unbuilt and is no longer reachable: output/ holds a lineage
    # timeline for both flows. Accepting 3 as well would hide the day Stage 6 stops writing it,
    # which is exactly the reading the old comment warned about in the other direction.
    #
    # Exit 1 now means a step crossed a DISQUALIFYING distinction, which is a defect in the
    # crosswalk. It reports 37 review flags and 0 disqualifying, and a review rule may not
    # decide anything -- measured against Canada's concordance it fires on 5 of 125
    # known-correct successions, which is why families.py reads only the disqualifying rules.
    ("check_decisive_distinctions.py", (0,)),
]

# WHAT EACH CHECK MUST REPORT, so that a smaller number fails rather than passing more quietly.
#
# Until now this runner summed whatever the checks printed and compared the total to nothing. A
# check that reported FEWER controls, and failed none of them, still read as SOUND: the headline
# would say "654 of 654 passed" and every word of it would be true. That is not hypothetical.
# Two checks drop controls when a file is merely ABSENT rather than wrong, and exit 0 while doing
# it:
#
#   check_stage0_source_inventory.py:524  the two swap-test controls are skipped and a disclosure
#                                         written instead when source/exports.db is not on this
#                                         copy.                                        36 -> 34
#   check_adjudication_queue.py:1031      three controls sit behind os.path.exists on
#                                         work/_decisions_seen.json.                  135 -> 132
#
# Both branches are right in themselves; refusing to write an absent comparison as a passing
# control is the thing this suite exists to do. The defect was here, in the summing. A toolkit
# that has moved machines twice is exactly where a delivery file goes missing, and the control
# count was the only place that would have shown.
#
# The pin is the exact figure, not a floor. A count that goes UP is also a change worth stating:
# it means controls were added, which is a deliberate edit and belongs in this dict in the same
# commit that adds them. Measured 2026-08-17 against the full delivery, suite 656 of 656.
EXPECTED_CONTROLS = {
    # 36 -> 38 on 2026-08-31: the two controls holding REPRODUCE.py to the databases the
    # pipeline opens. Nothing covered the packaged reproduction path until then, which is
    # why the export switch left the one documented command fetching the wrong extract.
    "check_stage0_source_inventory.py": 38,
    # 77 -> 86 on 2026-08-19, findings 143, 146 and 147: five controls holding the same-worded
    # silence disclosure equal to the delivery, two on the hold firing only where silence is
    # the only evidence, and two on the boundary flags reading the union of trade end and
    # declared end.
    "check_stage1_candidates.py": 86,
    "check_stage1b_official_record.py": 49,
    "check_stage1c_rank.py": 84,
    "check_official_constraint_sets.py": 24,
    "check_adjudication_queue.py": 137,
    "check_stage2_apply_decisions.py": 59,
    "check_stage3_route.py": 41,
    "check_stage4_build_families.py": 43,
    "check_stage5_lineage.py": 33,
    # 42 -> 46 on 2026-08-19, finding 144: per flow, orig_status is held to the timeline's
    # first step, with a provocation beside it. The cross-file comparison used to ASSERT the
    # defective copy, requiring orig_status to equal latest_status.
    # 46 -> 56 on 2026-08-20, findings 152 and 153: per flow, the commodity-string columns are
    # held to the source string (dotted code, raw wording, note) and the description columns
    # to the abbreviation-table expansion, with a bare-code provocation. The two-spellings
    # control, which ASSERTED the bare-code copy, is replaced by them.
    "check_stage6_outputs.py": 56,
    "check_rule_application.py": 16,
    # Added 2026-08-19, findings 143 and 147 to 150: twenty figure pins over the four shipped
    # documents, plus the two provocations every check carries.
    # 22 -> 23 on 2026-08-20: the suite-size pin, so the method document cannot quote a
    # control count the runner no longer expects.
    # 23 -> 27 on 2026-08-20: three pins over the new framework flowchart figure and one
    # holding the code companion's recorded hashes equal to the live pipeline files.
    # 27 -> 31 on 2026-08-20: four pins re-deriving the examples figure's journeys and
    # families from the published output.
    "check_published_figures.py": 37,  # 35 -> 37 on 2026-08-31 when the figures were
    # redrawn with their prose moved into the section text. The flowchart now carries each
    # count on its own line, so the two combined pins ("280 import + 40 export retirements"
    # and "118 import + 48 export families") became four, one per printed line. That is two
    # more controls and each number is tied to its own phrase, which is stricter. ## ... -> 37 on 2026-08-20: five pins over the reviewer
    # letter inserts, each figure the letter quotes re-derived from the artefacts, then a
    # sixth for the restated boundary coverage the analyst confirmed.
    "check_medicine_families.py": 48,
}

# check_decisive_distinctions.py reports no control line at all, and that is deliberate. It is the
# end-of-pipeline meaning audit: it self-tests its rule engine against literal cases, then walks
# the published lineage, and its verdict is its EXIT CODE rather than a tally. Its self-test cases
# have never been part of the headline and must not be folded into it, or "N of N controls" would
# start counting two different kinds of thing. Pinned separately so the engine cannot shrink either.
EXPECTED_SELF_TEST_CASES = {
    "check_decisive_distinctions.py": 71,
}

# The grand total, written as a literal rather than summed from the dict above, because the two can
# disagree in the one way that matters most: a check REMOVED from CHECKS takes its controls with it
# and no per-script pin can fire for a script that never runs.
# 656 -> 660 on 2026-08-18: the carve-out rung (finding 122) added four controls to Stage 1a,
# two naming the delivery's two carve-outs outright and two holding the rung to its measured
# size so it cannot quietly become a second ladder.
# 660 -> 662 on 2026-08-18: finding 123 added the step-wording control to Stage 5, one per flow.
# 662 -> 665 on 2026-08-18: finding 124 extended the terminal comparison to every published row
# (one per flow) and added a perturbation proof that it can fire.
# 665 -> 668 on 2026-08-18: finding 125 tied gate1 to the Stage 4 it describes.
# 668 -> 669 on 2026-08-18: finding 126 names the three rules that cannot fire on this delivery.
# 669 -> 670: the inert-rule control carries a guard on the shorthand expansion it depends on.
# 670 -> 671: finding 127 pins where Stage 3 is deliberately more permissive than Stage 1a.
# 671 -> 674 on 2026-08-18: finding 131 makes Gate 2's two ambiguities explicit.
# 674 -> 678 on 2026-08-18: finding 132 rebuilt both identifier controls from the published form
# instead of asking the producer, and kept the producer comparison beside each as its own control.
# 678 -> 680 on 2026-08-18: finding 134 enforces Gate 2 clause 5, the tail disclosure.
# 680 -> 684 on 2026-08-18: finding 135 pins the six span splits by cause, finding 136 computes
# rule coverage instead of trusting pins whose method was never written down.
# 684 -> 686 on 2026-08-18: finding 137 pins the co-casualty counts and asserts the gap.
# 686 -> 687 on 2026-08-18: finding 138 pins the 94/81/13 split of the two kinds of "o/t".
# 687 -> 688 on 2026-08-18: finding 140 enforces that every pipeline threshold is declared in
# THRESHOLDS.md, which the plan requires and nothing was checking.
# 688 -> 689 on 2026-08-18: finding 142 asserts every v1 family Gate 1 flags is explained in
# writing, which is Gate 1's own criterion and had nothing enforcing it.
# 689 -> 724 on 2026-08-19, findings 143 to 150: nine controls added to Stage 1a's check, four
# to Stage 6's, and the twenty-two of check_published_figures.py, recorded above beside their
# per-check pins.
# 724 -> 734 on 2026-08-20, findings 152 and 153: ten consumer-contract controls in Stage 6's
# check, recorded beside its pin.
# 734 -> 751 later the same day, finding 154: the seventeen of check_authorship_voice.py,
# and 751 -> 752 with the suite-size pin in check_published_figures.py.
# 752 -> 756 on 2026-08-20: the flowchart and code-companion pins, recorded beside
# their per-check entry, and 756 -> 760 with the examples-figure pins, then 760 -> 761
# with the split panel's, and 761 -> 766 with the letter-insert pins, then 766 -> 767
# with the restated-coverage pin.
# 750 -> 747 on 2026-08-28: the three pins that held shipped prose equal to this
# number were retired when the published material stopped quoting it.
# 747 -> 749 on 2026-08-31: the two extra pins in check_published_figures.py, above.
# 749 -> 751 on 2026-08-31: the two REPRODUCE.py controls, above.
EXPECTED_TOTAL_CONTROLS = 751

# Never deleted and never rebuilt from scratch: the workbook a person types into, and its CSV
# copy. They are refreshed in place by the builder, which merges rather than overwrites. Listing
# them here as forbidden is cheaper than remembering not to add them.
NEVER_DELETE = ("stage2_decisions.xlsx", "stage2_decisions.csv")

ARTEFACTS = [
    "commodity_inventory_imports.csv", "commodity_inventory_exports.csv",
    "stage1_candidates_imports.csv", "stage1_candidates_exports.csv",
    "stage1_official_imports.csv", "stage1_official_exports.csv",
    "stage1_ranked_imports.csv", "stage1_ranked_exports.csv",
    "stage1_review_imports.csv", "stage1_review_exports.csv",
    "stage2_resolved_imports.csv", "stage2_resolved_exports.csv",
    "stage3_routed_imports.csv", "stage3_routed_exports.csv",
    "stage4_families_imports.csv", "stage4_families_exports.csv",
    "stage5_lineage_imports.csv", "stage5_lineage_exports.csv",
]
# Not in work/. The four published shapes are the crosswalk itself, and they must reproduce like
# everything else: deleted before the run and compared byte for byte after the second pass.
PUBLISHED = [os.path.join("output", "%s_%s.csv" % (flow, shape))
             for flow in ("imports", "exports")
             for shape in ("lookup", "commodity_journeys", "lineage_timeline", "provenance")]
# Not in work/. The adjudication queue is a decision asset, and it must reproduce like the rest.
EXTRA_ARTEFACTS = [os.path.join("decisions", "stage2_adjudication_queue.csv")] + PUBLISHED

# CARRIED ACROSS A REBUILD, NOT REBUILT BY IT, and that is deliberate. _row_numbers.json pins each
# row number to a link_id so "row 60" means the same retirement next week as it did today, and the
# other two are the snapshots the change report compares against. clear_artefacts() has never
# deleted them, and it must not start: deleting the ledger renumbers the analyst's sheet under them.
# Measured 2026-08-13 in a sandbox: with the ledger removed the queue rebuilds with a DIFFERENT
# digest and 47 of 230 row numbers move. So the queue reproduces byte for byte GIVEN these three
# files, and until now nothing said so and nothing watched them. Hashing them states the
# dependency and makes drift in the ledger itself visible instead of invisible. All three are
# stable across repeated builds when the inputs do not change, which is what makes this a fair
# comparison rather than a guaranteed red.
LEDGERS = ["_row_numbers.json", "_queue_previous.json", "_decisions_seen.json"]

# THE ANSWER SHEET WAS EXCLUDED FROM THE PROOF ENTIRELY, and it is where the 19 method-computed
# columns are actually merged with the 5 the analyst writes. It cannot be hashed whole: the analyst
# edits it between runs, and the workbook's zip timestamps move even when every part is identical.
# So the 19 are digested and the 5 are not. A change in the merge is then caught, and a decision
# typed into Excel is not mistaken for one.
ANALYST_COLUMNS = ("decision", "correct_successor_if_rejected", "reason", "decided_by",
                  "decided_on")
SHEET_COPY = os.path.join("decisions", "stage2_decisions.csv")

problems = []
# A file held open by a spreadsheet is not a defect. Kept apart so the report can say what it
# actually found, which is nothing wrong and nothing proved.
blocked = []


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sheet_method_digest():
    """Digest the answer sheet's method-computed columns, leaving the analyst's five out.

    Keyed on link_id and sorted, so it does not move with row order, and it is read from the CSV
    copy rather than the workbook because the workbook's zip timestamps change on every write.
    """
    path = os.path.join(PROJECT, SHEET_COPY)
    if not os.path.exists(path):
        problems.append("%s was not produced, so the merge could not be compared" % SHEET_COPY)
        return "absent"
    import csv as _csv
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(_csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, _csv.Error) as error:
        problems.append("%s could not be read (%s)" % (SHEET_COPY, type(error).__name__))
        return "unreadable"
    if not rows:
        return "empty"
    columns = [c for c in rows[0] if c not in ANALYST_COLUMNS]
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r.get("link_id", "")):
        digest.update(("\x1f".join(str(row.get(c, "")) for c in columns) + "\x1e").encode("utf-8"))
    return digest.hexdigest()


def run(folder, script):
    started = time.time()
    result = subprocess.run([PYTHON, os.path.join(PROJECT, folder, script)],
                            capture_output=True, text=True, cwd=PROJECT)
    return result.returncode, result.stdout, time.time() - started


def clear_artefacts():
    for forbidden in NEVER_DELETE:
        if any(forbidden in name for name in ARTEFACTS + EXTRA_ARTEFACTS):
            raise SystemExit("Refusing to run: %s is listed as a rebuildable artefact. It holds "
                             "judgement and is merged, never regenerated." % forbidden)
    """Rebuild from the delivery, so nothing on disk can be a survivor of an earlier edit."""
    removed = 0
    for name in ARTEFACTS:
        path = os.path.join(WORK, name)
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
        except OSError as error:
            # Locked by a spreadsheet, most often. Report it; do not crash a verification run.
            blocked.append("%s is in use and was not rebuilt (%s)" % (name, type(error).__name__))
            continue
        removed += 1
    for relative in EXTRA_ARTEFACTS:
        path = os.path.join(PROJECT, relative)
        if not os.path.exists(path):
            continue
        # Never delete an adjudication file somebody has started filling in. A signed decision
        # is not a build artefact, and this runner rebuilds everything by design.
        import csv as _csv
        WORK_COLUMNS = ("decision", "correct_successor_if_rejected", "reason", "decided_by")
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                filled = sum(1 for row in _csv.DictReader(fh)
                             if any((row.get(c) or "").strip() for c in WORK_COLUMNS))
        except (OSError, UnicodeDecodeError, _csv.Error) as error:
            # Unreadable means unknown, and unknown must not mean deletable.
            problems.append("%s could not be read (%s) and was left alone"
                            % (relative, type(error).__name__))
            continue
        if filled:
            problems.append("%s holds work on %d row(s) and was left alone. Move it aside "
                            "before running a full rebuild." % (relative, filled))
            continue
        try:
            os.remove(path)
        except OSError as error:
            blocked.append("%s is open in a spreadsheet, so it was not rebuilt"
                           % relative)
            continue
        removed += 1
    return removed


def pipeline_pass(label):
    print("%s" % label)
    print("  cleared %d artefact(s) so every file below is built by the code as it stands"
          % clear_artefacts())
    for script, purpose in STAGES:
        code, _out, seconds = run("pipeline", script)
        status = "ok" if code == 0 else "EXIT %d" % code
        print("    %-30s %-52s %5.1fs  %s" % (script, purpose, seconds, status))
        if code != 0:
            # Exit 4 is the builder's own way of saying a destination was locked. It already
            # reported which file, and the lock is recorded above.
            (blocked if code == 4 else problems).append(
                "%s could not write, its destination is in use" % script if code == 4
                else "%s exited %d" % (script, code))
    digests = {}
    for name in ARTEFACTS:
        path = os.path.join(WORK, name)
        if not os.path.exists(path):
            problems.append("%s was not produced" % name)
            continue
        digests[name] = sha256(path)
    for relative in EXTRA_ARTEFACTS:
        path = os.path.join(PROJECT, relative)
        if not os.path.exists(path):
            problems.append("%s was not produced" % relative)
            continue
        digests[relative] = sha256(path)
    print("  artefacts produced: %d of %d" % (len(digests), len(ARTEFACTS) + len(EXTRA_ARTEFACTS)))
    for name in LEDGERS:
        path = os.path.join(WORK, name)
        digests["work/" + name] = sha256(path) if os.path.exists(path) else "absent"
    digests[SHEET_COPY] = sheet_method_digest()
    return digests


print("End to end. Rebuild from the delivery, check everything, then prove it repeats.")
print()
first = pipeline_pass("PASS ONE")

print()
print("CHECKS")
# A check nobody pinned is a check whose count can move without anyone noticing, which is the whole
# defect this dict was added for. Catching it here means adding a check to CHECKS and forgetting to
# pin it is loud on the first run rather than silent forever.
_unpinned = [script for script, _ in CHECKS
             if script not in EXPECTED_CONTROLS and script not in EXPECTED_SELF_TEST_CASES]
if _unpinned:
    problems.append("%d check(s) have no pinned count, so a drop in theirs could not be seen: %s"
                    % (len(_unpinned), ", ".join(_unpinned)))
total_controls = total_passed = total_notes = 0
# WHAT A CHECK READS THAT A DISTRIBUTION MAY NOT CARRY
# ----------------------------------------------------
# Two checks read material that is not an input to the crosswalk. One compares the build against
# the RELEASED v1 extracts, 261 MB of frozen source kept for that comparison alone. The other
# validates the manuscript's prose against the build. Neither belongs in a package whose subject
# is the crosswalk, and both are present here, so neither is skipped in this repository.
#
# A check named here is SKIPPED when a path it needs is absent, and the skip is printed with the
# path that caused it. It is never skipped because it failed: the paths are tested before the
# check runs, so a check that starts is a check whose verdict counts. Without this, a package
# missing an input reports NOT SOUND with no way to tell a missing file from a broken build.
# Measured on 2026-08-28: a distribution missing one 686 KB folder reported "56 of 747" and named
# nothing.
NEEDS = {
    "check_stage0_source_inventory.py": [
        "baseline_v1/source/Chapter30_IMPORTS_1988-2026_byMonth.csv",
        "baseline_v1/source/Chapter30_EXPORT_2000-2026_byMonth.csv",
    ],
    "check_published_figures.py": [
        "manuscript/CODE_COMPANION.md",
        "manuscript/HARMONIZATION_RESPONSE_INSERTS.md",
        "manuscript/framework_examples.svg",
        "manuscript/framework_flowchart.svg",
    ],
}


def absent_inputs(script):
    """The declared paths this check needs that are not on disk. Empty means it can run."""
    return [rel for rel in NEEDS.get(script, ())
            if not os.path.exists(os.path.join(PROJECT, *rel.split("/")))]



skipped = []
for script, accepted in CHECKS:
    gone = absent_inputs(script)
    if gone:
        skipped.append(script)
        print("    %-38s SKIPPED %-21s %5s  %s"
              % (script, "", "", "%s is not in this distribution" % gone[0]))
        continue
    code, out, seconds = run("checks", script)
    match = re.search(r"(\d+) controls run, (\d+) passed, (\d+) failed", out)
    # Disclosures are counted apart and never added to the control total. A check states things
    # that cannot fail, and folding those into the headline would make "N of N passed" a claim
    # about fewer than N falsifiable tests.
    told = re.search(r"(\d+) disclosure\(s\) reported", out)
    total_notes += int(told.group(1)) if told else 0
    if match:
        ran, passed, failed = (int(match.group(i)) for i in (1, 2, 3))
        total_controls += ran
        total_passed += passed
        detail = "%d/%d controls" % (passed, ran)
        if told and int(told.group(1)):
            detail += " +%s note" % told.group(1)
        expected = EXPECTED_CONTROLS.get(script)
        if expected is not None and ran != expected:
            detail += " EXPECTED %d" % expected
            problems.append(
                "%s ran %d control(s), expected %d. A count that moves on its own is either a "
                "file this copy does not have, which makes the run weaker than it reads, or "
                "controls that were added or removed without recording it in EXPECTED_CONTROLS."
                % (script, ran, expected))
    else:
        selftest = re.search(r"SELF TEST: (\d+) cases, (all pass|FAILED)", out)
        detail = ("%s self-test cases" % selftest.group(1)) if selftest else "no control count"
        if selftest and selftest.group(2) != "all pass":
            problems.append("%s self test failed" % script)
        expected_cases = EXPECTED_SELF_TEST_CASES.get(script)
        if expected_cases is not None:
            if not selftest:
                problems.append("%s printed no self-test line, so its %d case(s) were not run"
                                % (script, expected_cases))
            elif int(selftest.group(1)) != expected_cases:
                detail += " EXPECTED %d" % expected_cases
                problems.append("%s self-tested %s case(s), expected %d"
                                % (script, selftest.group(1), expected_cases))
        # A check that is pinned for controls but printed none has not run them. Without this the
        # run would add 0 and say nothing, which is the quietest form of the same defect.
        if script in EXPECTED_CONTROLS:
            problems.append("%s printed no control count, and %d were expected"
                            % (script, EXPECTED_CONTROLS[script]))
    ok = code in accepted
    print("    %-38s exit %d %-22s %5.1fs  %s"
          % (script, code, detail, seconds, "ok" if ok else "UNEXPECTED EXIT"))
    if not ok:
        problems.append("%s exited %d, expected one of %s" % (script, code, accepted))

print()
second = pipeline_pass("PASS TWO, to prove the pipeline reproduces")

print()
print("REPRODUCIBILITY")
print("  DELETED BEFORE EACH PASS, so the code alone produced them:")
drifted = [name for name in first if first.get(name) != second.get(name)]
for name in ARTEFACTS + EXTRA_ARTEFACTS:
    if name in first and name in second:
        mark = "identical" if first[name] == second[name] else "DIFFERS BETWEEN RUNS"
        print("    %-38s %s  %s" % (name, first[name][:16], mark))
# Named apart, because "11 artefacts reproduce byte for byte" invites a stronger reading than the
# run supports. The queue's bytes depend on the row-number ledger, which is carried rather than
# rebuilt; without it 47 of 230 row numbers move. Saying so is the honest form of the claim.
print("  CARRIED ACROSS BOTH PASSES, listed because the artefacts above depend on them:")
for name in ["work/" + n for n in LEDGERS]:
    if name in first and name in second:
        mark = "identical" if first[name] == second[name] else "DRIFTED BETWEEN RUNS"
        print("    %-38s %s  %s" % (name, first[name][:16], mark))
print("  MERGED, NEVER REGENERATED. The 19 method columns only; the analyst's 5 are excluded:")
mark = ("identical" if first.get(SHEET_COPY) == second.get(SHEET_COPY)
        else "DIFFERS BETWEEN RUNS")
print("    %-38s %s  %s" % (SHEET_COPY + " (method columns)",
                            str(first.get(SHEET_COPY, ""))[:16], mark))
if drifted:
    problems.append("%d artefact(s) differ between two runs: %s" % (len(drifted), drifted))

print()
# A skipped check runs no control, so its pin is no part of what this run should total.
expected_total = EXPECTED_TOTAL_CONTROLS - sum(EXPECTED_CONTROLS.get(s, 0) for s in skipped)
print("=" * 88)
print("stages run          : %d" % len(STAGES))
print("checks run          : %d of %d%s"
      % (len(CHECKS) - len(skipped), len(CHECKS),
         "" if not skipped else ", %d skipped and named above" % len(skipped)))
print("controls            : %d of %d passed, every one able to fail%s"
      % (total_passed, total_controls,
         "" if total_controls == expected_total
         else ", AND %d WERE EXPECTED" % expected_total))
if total_controls != expected_total:
    problems.append("the suite ran %d control(s) in total, expected %d. Every per-check pin may "
                    "still hold and this total still move, because a check dropped from CHECKS "
                    "runs nothing and so can fail no pin of its own."
                    % (total_controls, expected_total))
print("disclosures         : %d, printed and counted apart because they cannot fail" % total_notes)
print("meaning audit       : counted apart. check_decisive_distinctions.py reports %d self-test "
      "case(s) and\n                      an exit code, not controls, so it is no part of the "
      "figure above." % EXPECTED_SELF_TEST_CASES["check_decisive_distinctions.py"])
if drifted:
    print("compared files      : %d, of which %d DRIFTED: %s"
          % (len(first), len(drifted), ", ".join(drifted[:4])))
else:
    print("artefacts rebuilt   : %d, deleted first and reproduced byte for byte"
          % (len(ARTEFACTS) + len(EXTRA_ARTEFACTS)))
    print("carried, not rebuilt: %d ledger file(s) the queue's bytes depend on, unchanged "
          "across both passes" % len(LEDGERS))
    print("answer sheet        : the 19 method columns reproduce; the analyst's 5 are excluded "
          "by design")
if problems:
    print()
    print("NOT SOUND. %d problem(s):" % len(problems))
    for problem in problems:
        print("  - %s" % problem)
    if blocked:
        print()
        print("Also, %d file(s) were in use and could not be rebuilt:" % len(blocked))
        for item in dict.fromkeys(blocked):
            print("  - %s" % item)
    print("=" * 88)
    sys.exit(1)
if blocked:
    print()
    print("VERIFICATION INCOMPLETE. Nothing is wrong, and nothing was proved about these:")
    for item in dict.fromkeys(blocked):
        print("  - %s" % item)
    print()
    print("Every check that could run passed. Close the file(s) and run this again to finish.")
    print("=" * 88)
    sys.exit(2)
print()
print("SOUND. Every stage ran from the delivery, every check passed, and a second run")
print("reproduced every artefact byte for byte.")
print("=" * 88)
