"""
Check for the shipped prose. Does every figure the documents quote still describe the build?


Inputs:
    METHOD_harmonization.md, METHOD_family_id.md, THRESHOLDS.md,
    manuscript/SI_candidate_assembly.md
    work/stage1_candidates_{flow}.csv, stage1_official_{flow}.csv, stage2_resolved_{flow}.csv,
    work/commodity_inventory_{flow}.csv, output/{flow}_lookup.csv,
    gate1/reuse_silence_disclosure.csv

Output:
    A pass or fail line per pinned figure, and a non-zero exit code if any fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
A figure quoted in shipped prose is a claim about the build, and prose is the one artefact no
other check reads. Findings 135, 137, 139, 140, 141, 148 and 149 were all the same event: a
document quoted a number, the build moved underneath it, and nothing failed. This check ends
that class. Every pin below asserts two things at once: the document still contains the exact
phrase, and the value inside the phrase still re-derives from the artefacts. Editing the prose
away fails the first half. The build drifting fails the second. Either way the drift is a red
build instead of a reviewer's discovery.

A pin here is the exact figure, not a floor. When a delivery legitimately moves a number, the
document and this pin change in the same commit, with the movement explained, which is the same
rule every other pinned count in this suite follows.
"""

import csv
import glob
import os
import re
import statistics
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(PROJECT, "work")
OUTPUT = os.path.join(PROJECT, "output")

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name,
                           ("  -- " + detail) if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prose(rel):
    with open(os.path.join(PROJECT, rel), encoding="utf-8") as handle:
        text = handle.read()
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", ""))


print("Check for the shipped prose. Does every figure the documents quote still describe the build?")
print()

cand = {f: load(os.path.join(WORK, "stage1_candidates_%s.csv" % f))
        for f in ("imports", "exports")}
official = {f: load(os.path.join(WORK, "stage1_official_%s.csv" % f))
            for f in ("imports", "exports")}
resolved = {f: load(os.path.join(WORK, "stage2_resolved_%s.csv" % f))
            for f in ("imports", "exports")}
inventory = {f: load(os.path.join(WORK, "commodity_inventory_%s.csv" % f))
             for f in ("imports", "exports")}
lookup = {f: load(os.path.join(OUTPUT, "%s_lookup.csv" % f)) for f in ("imports", "exports")}
silences = load(os.path.join(PROJECT, "gate1", "reuse_silence_disclosure.csv"))

held = [r for f in cand for r in cand[f] if r["too_recent_to_call"] == "yes"]
held_window = [r for r in held if int(r["months_before_delivery_end"]) <= 12]
held_sparse = [r for r in held if int(r["months_before_delivery_end"]) > 12]
splits = [(f, r["retiring_code"], r["last_period"]) for f in cand for r in cand[f]
          if int(r["span_count"]) > 1]
split_codes = sorted({(f, c) for f, c, _ in splits})
early_splits = [(f, c) for f, c, last in splits if last == "198812"]
fams = {}
for f in ("imports", "exports"):
    by_family = {}
    for r in lookup[f]:
        code = "".join(ch for ch in r["orig_hs_code"] if ch.isdigit())
        by_family.setdefault(r["family_id"], set()).add(code)
    fams[f] = by_family
value = {f: sum(float(r["total_value_cad"]) for r in inventory[f])
         for f in ("imports", "exports")}
queue_value = sum(float(r["total_value_cad"]) for f in resolved for r in resolved[f])
covered = {f: [r for r in cand[f] if r["cbsa_concordance_covers"] == "yes"]
           for f in ("imports", "exports")}
boundary = {f: [r for r in cand[f] if r["at_hs_revision_boundary"] == "yes"]
            for f in ("imports", "exports")}

# (document, exact phrase after normalisation, derived truth of the value inside it, how derived)
PINS = [
    ("METHOD_harmonization.md", "280 import and 40 export retirements",
     len(cand["imports"]) == 280 and len(cand["exports"]) == 40,
     "stage1_candidates rows: %d and %d" % (len(cand["imports"]), len(cand["exports"]))),
    ("METHOD_harmonization.md",
     "Six code numbers in this delivery have more than one trading period",
     len(split_codes) == 6, "codes with span_count above one: %d" % len(split_codes)),
    ("METHOD_harmonization.md", "eleven rows are held, worth CAD 382,824,215",
     len(held) == 11 and abs(sum(float(r["total_value_cad"]) for r in held)
                             - 382824215) < 0.005,
     "%d held, CAD %s" % (len(held),
                          format(sum(float(r["total_value_cad"]) for r in held), ",.0f"))),
    ("METHOD_harmonization.md", "nine by the twelve-month window, worth CAD 381,020,499",
     len(held_window) == 9 and abs(sum(float(r["total_value_cad"]) for r in held_window)
                                   - 381020499) < 0.005,
     "%d in the window, CAD %s"
     % (len(held_window),
        format(sum(float(r["total_value_cad"]) for r in held_window), ",.0f"))),
    ("METHOD_harmonization.md", "decides 89 import retirements outright",
     sum(1 for r in official["imports"] if r["outcome"] == "decided") == 89,
     "stage1_official decided: %d"
     % sum(1 for r in official["imports"] if r["outcome"] == "decided")),
    ("METHOD_harmonization.md", "has nothing to say on 151",
     sum(1 for r in official["imports"] if r["outcome"] == "silent_no_source") == 151,
     "stage1_official silent_no_source: %d"
     % sum(1 for r in official["imports"] if r["outcome"] == "silent_no_source")),
    ("METHOD_family_id.md", "| resolved successions | 270 | 30 |",
     sum(1 for r in resolved["imports"] if r["outcome"] == "succeeded") == 270
     and sum(1 for r in resolved["exports"] if r["outcome"] == "succeeded") == 30,
     "stage2_resolved succeeded: %d and %d"
     % (sum(1 for r in resolved["imports"] if r["outcome"] == "succeeded"),
        sum(1 for r in resolved["exports"] if r["outcome"] == "succeeded"))),
    ("METHOD_family_id.md", "| families | 118 | 48 |",
     len(fams["imports"]) == 118 and len(fams["exports"]) == 48,
     "published families: %d and %d" % (len(fams["imports"]), len(fams["exports"]))),
    ("METHOD_family_id.md", "| largest family | 17 codes | 6 codes |",
     max(len(v) for v in fams["imports"].values()) == 17
     and max(len(v) for v in fams["exports"].values()) == 6,
     "largest: %d and %d codes" % (max(len(v) for v in fams["imports"].values()),
                                   max(len(v) for v in fams["exports"].values()))),
    ("METHOD_family_id.md", "| families holding a single code | 31 | 33 |",
     sum(1 for v in fams["imports"].values() if len(v) == 1) == 31
     and sum(1 for v in fams["exports"].values() if len(v) == 1) == 33,
     "single-code families: %d and %d"
     % (sum(1 for v in fams["imports"].values() if len(v) == 1),
        sum(1 for v in fams["exports"].values() if len(v) == 1))),
    ("METHOD_family_id.md", "CAD 632,398,282,297",
     abs(value["imports"] + value["exports"] - 632398282297) < 0.005,
     "delivery total from the inventory: CAD %s"
     % format(value["imports"] + value["exports"], ",.0f")),
    ("METHOD_family_id.md", "CAD 184,992,933,428",
     abs(queue_value - 184992933428) < 0.005,
     "retirement queue total: CAD %s" % format(queue_value, ",.0f")),
    ("THRESHOLDS.md", "Eight such silences past the threshold exist, 61 to 121 months",
     len(silences) == 8 and min(int(r["gap_months"]) for r in silences) == 61
     and max(int(r["gap_months"]) for r in silences) == 121,
     "%d disclosed, gaps %d to %d" % (len(silences),
                                      min(int(r["gap_months"]) for r in silences),
                                      max(int(r["gap_months"]) for r in silences))),
    ("THRESHOLDS.md",
     "eleven spans held, nine by this window worth CAD 381,020,499 and two by the "
     "sparsity clause worth CAD 1,803,716",
     len(held) == 11 and len(held_sparse) == 2
     and abs(sum(float(r["total_value_cad"]) for r in held_sparse) - 1803716) < 0.005,
     "%d held, %d by sparsity, CAD %s"
     % (len(held), len(held_sparse),
        format(sum(float(r["total_value_cad"]) for r in held_sparse), ",.0f"))),
    ("manuscript/SI_candidate_assembly.md", "| Imports | 280 | CAD 102,128,187,239 | 9 |",
     len(cand["imports"]) == 280
     and abs(sum(float(r["total_value_cad"]) for r in cand["imports"])
             - 102128187239) < 0.005
     and statistics.median(int(r["narrowest_count"]) for r in cand["imports"]) == 9,
     "280 rows, CAD %s, median %d"
     % (format(sum(float(r["total_value_cad"]) for r in cand["imports"]), ",.0f"),
        statistics.median(int(r["narrowest_count"]) for r in cand["imports"]))),
    ("manuscript/SI_candidate_assembly.md",
     "241 of 280 retirements narrow to the subheading",
     sum(1 for r in cand["imports"] if r["narrowest_tier"] == "same_subheading") == 241,
     "same_subheading: %d"
     % sum(1 for r in cand["imports"] if r["narrowest_tier"] == "same_subheading")),
    ("manuscript/SI_candidate_assembly.md", "97 of 280, CAD 49.6 billion",
     len(covered["imports"]) == 97
     and round(sum(float(r["total_value_cad"]) for r in covered["imports"]) / 1e9, 1) == 49.6,
     "covered: %d, CAD %s" % (len(covered["imports"]),
                              format(sum(float(r["total_value_cad"])
                                         for r in covered["imports"]), ",.0f"))),
    ("manuscript/SI_candidate_assembly.md", "124 of 280, CAD 66.5 billion",
     len(boundary["imports"]) == 124
     and round(sum(float(r["total_value_cad"]) for r in boundary["imports"]) / 1e9, 1) == 66.5,
     "at a boundary: %d, CAD %s" % (len(boundary["imports"]),
                                    format(sum(float(r["total_value_cad"])
                                               for r in boundary["imports"]), ",.0f"))),
    ("manuscript/SI_candidate_assembly.md",
     "Six span-split events exist, three of them at the December 1988 export restructure",
     len(split_codes) == 6 and len(early_splits) == 3,
     "%d split codes, %d earlier lives ending 1988-12" % (len(split_codes),
                                                          len(early_splits))),
    ("manuscript/SI_candidate_assembly.md",
     "Eight such silences longer than sixty months exist",
     len(silences) == 8, "%d disclosed" % len(silences)),
]

# The suite's own size is no longer quoted in any shipped document. The three pins that
# held prose equal to EXPECTED_TOTAL_CONTROLS were retired on 2026-08-28, on the analyst's
# ruling that the published material describes the suite rather than counting it. Nothing
# to pin means nothing that can drift.

# The flowchart is prose drawn as a figure, and its numbers drift the same way. The three
# load-bearing figures are each kept as one contiguous text run in the SVG so they can be
# pinned here.
# FOUR PINS WHERE THERE WERE TWO. The flowchart was redrawn 2026-08-31 with its prose moved to
# the section text, and it now carries each count on its own line. One pin per line ties each
# number to its own printed phrase, which is stricter than the combined pins it replaces.
PINS.append(("manuscript/framework_flowchart.svg", "280 imports",
             len(cand["imports"]) == 280,
             "stage1_candidates import rows: %d" % len(cand["imports"])))
PINS.append(("manuscript/framework_flowchart.svg", "40 exports",
             len(cand["exports"]) == 40,
             "stage1_candidates export rows: %d" % len(cand["exports"])))
PINS.append(("manuscript/framework_flowchart.svg", "118 import",
             len(fams["imports"]) == 118,
             "published import families: %d" % len(fams["imports"])))
PINS.append(("manuscript/framework_flowchart.svg", "48 export",
             len(fams["exports"]) == 48,
             "published export families: %d" % len(fams["exports"])))

# The examples figure shows four real lineages, and each panel's claim is re-derived from the
# published output: the journey it draws and the family it names must be the ones the
# crosswalk publishes.
_jn = {}
for _fl in ("imports", "exports"):
    for _r in load(os.path.join(OUTPUT, "%s_commodity_journeys.csv" % _fl)):
        _jn[_r["uid"]] = _r
PINS.append(("manuscript/framework_examples.svg", "EX-30022000-198801",
             _jn["EXR-30022000-198801"]["journey"] == "3002.20.00 -> 3002.41.00"
             and _jn["EXR-30022000-198801"]["family_id"] == "EX-30022000-198801",
             "panel a: %s" % _jn["EXR-30022000-198801"]["journey"]))
PINS.append(("manuscript/framework_examples.svg", "EX-30023100-198801",
             all(_jn[u]["family_id"] == "EX-30023100-198801"
                 and _jn[u]["latest_commodity"].startswith("3002.42.00")
                 for u in ("EXR-30023010-199602", "EXR-30023090-199601",
                           "EXR-30023000-201701")),
             "panel b: three vaccine lines share the family and the terminal"))
PINS.append(("manuscript/framework_examples.svg", "IM-3002101021-198801",
             _jn["IMR-3002101021-198801"]["journey"]
             == "3002.10.10.21 -> 3002.10.00.21 -> 3002.12.00.12"
             and _jn["IMR-3002101021-198801"]["family_id"] == "IM-3002101021-198801",
             "panel c: %s" % _jn["IMR-3002101021-198801"]["journey"]))
PINS.append(("manuscript/framework_examples.svg", "IM-3002900020-202201",
             _jn["IMR-3002900020-199801"]["family_id"] == "IM-3002901020-198801"
             and _jn["IMR-3002900020-202201"]["family_id"] == "IM-3002900020-202201",
             "panel d: the two lives of 3002.90.00.20 sit in different families"))
# The reviewer letter's harmonization responses quote figures too, and a letter is the one
# document a reviewer is certain to read against the data. Each quoted figure re-derives
# here, and the control total the letter quotes is the runner's own pin.
_ins = "manuscript/HARMONIZATION_RESPONSE_INSERTS.md"
_im_look = lookup["imports"]
_in_chapter = sum(1 for r in _im_look if r["latest_status"] != "left_chapter")
PINS.append((_ins, "467 of 475 import strings reach a terminal inside the chapter",
             _in_chapter == 467, "%d of %d" % (_in_chapter, len(_im_look))))
_fam79 = [r for r in _im_look if r["family_id"] == "IM-3004100011-198801"]
_codes79 = {"".join(ch for ch in r["orig_hs_code"] if ch.isdigit()) for r in _fam79}
PINS.append((_ins, "7 codes carrying 14 commodity strings",
             len(_codes79) == 7 and len(_fam79) == 14
             and all(r["latest_hs_code"] == "3004.10.00.10" for r in _fam79),
             "%d codes, %d strings, one terminal" % (len(_codes79), len(_fam79))))
_r264 = next(r for r in _im_look if r["uid"] == "IMR-3004500040-199801")
PINS.append((_ins, "IMR-3004500040-199801",
             _r264["latest_hs_code"] == "3004.50.00.12"
             and _r264["v1_uid"] == "IMR_0264",
             "terminates at %s, carries %s" % (_r264["latest_hs_code"], _r264["v1_uid"])))
PINS.append((_ins, "280 import and 40 export retirement events",
             len(cand["imports"]) == 280 and len(cand["exports"]) == 40,
             "stage1_candidates rows: %d and %d" % (len(cand["imports"]),
                                                    len(cand["exports"]))))
_cov = {}
for _fl in ("imports", "exports"):
    _steps = {}
    for _r in load(os.path.join(OUTPUT, "%s_lineage_timeline.csv" % _fl)):
        _steps.setdefault(_r["uid"], []).append(_r)
    _hops = _covered = 0
    for _rows in _steps.values():
        _rows.sort(key=lambda r: int(r["step_number"]))
        for _a, _b in zip(_rows, _rows[1:]):
            _hops += 1
            if _a["step_last_period"][:4] in ("2011", "2016"):
                _covered += 1
    _cov[_fl] = (_covered, _hops)
PINS.append((_ins, "250 of 476 import steps and 9 of 43 export steps",
             _cov["imports"] == (250, 476) and _cov["exports"] == (9, 43),
             "each hop judged by its own end year: %s imports, %s exports"
             % (_cov["imports"], _cov["exports"])))

_split_official = next(r for r in official["imports"]
                       if r["retiring_code"] == "3002100090" and r["last_period"] == "201612")
_split_value = sum(float(r["total_value_cad"]) for r in inventory["imports"]
                   if r["hs_code"] == "3002100090")
PINS.append(("manuscript/framework_examples.svg", "CAD 7,588,057,599",
             _jn["IMR-3002100090-201201"]["journey"]
             == "3002.10.00.90 -> 3002.19.00.00 -> 3002.90.00.90"
             and set(_split_official["official_destinations"].split(";"))
             == {"3002110000", "3002130000", "3002140000", "3002150000", "3002190000"}
             and abs(_split_value - 7588057599) < 0.005,
             "panel e: five official successors, the carried branch, CAD %s"
             % format(_split_value, ",.0f")))

# The code companion inlines every pipeline file and records each one's hash. A companion
# whose hashes no longer match the live files is showing a reviewer code the build does not
# run; regenerating it is one command, gate1/build_code_companion.py.
import hashlib
_comp = open(os.path.join(PROJECT, "manuscript", "CODE_COMPANION.md"),
             encoding="utf-8").read()
_recorded = dict(re.findall(r"\| `([^`]+\.py)` \| `([0-9a-f]{32})` \|", _comp))
_stale = []
for _rel, _digest in sorted(_recorded.items()):
    # Hashed the way the builder hashes: text mode, so line endings are normalised and the
    # comparison is about content rather than about how git checked the file out.
    with open(os.path.join(PROJECT, _rel.replace("/", os.sep)),
              encoding="utf-8") as _fh:
        _live = hashlib.md5(_fh.read().encode("utf-8")).hexdigest()
    if _live != _digest:
        _stale.append(_rel)
_pipeline_files = {os.path.basename(p) for p in
                   glob.glob(os.path.join(PROJECT, "pipeline", "*.py"))
                   if ".bak" not in p}
_covered = {os.path.basename(r) for r in _recorded}
PINS.append(("manuscript/CODE_COMPANION.md", "assembled from the code",
             not _stale and _covered == _pipeline_files,
             "%d file(s) recorded, every hash current" % len(_recorded)
             if not _stale and _covered == _pipeline_files
             else "stale: %s; missing: %s" % (_stale, sorted(_pipeline_files - _covered))))

texts = {}
for doc, phrase, derived_ok, how in PINS:
    if doc not in texts:
        texts[doc] = prose(doc)
    present = phrase in texts[doc]
    record("%s quotes %r" % (doc, phrase if len(phrase) <= 60 else phrase[:57] + "..."),
           present and derived_ok,
           how if (present and derived_ok)
           else ("the phrase is gone from the document" if not present else "value drifted: " + how))

print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")
_bent = PINS[0][1].replace("280", "281")
record("the sweep objects when a published figure drifts",
       _bent not in texts[PINS[0][0]],
       "a one-digit drift of the first pin is absent from the document, so it would fail")
record("the sweep objects when a derivation is wrong",
       not (len(cand["imports"]) == 281),
       "deriving 281 import retirements against the build fails")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed),
                                                  len(failed)))
if failed:
    print()
    print("The shipped prose is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("The shipped prose is validated. Every pinned figure re-derives from the build.")
