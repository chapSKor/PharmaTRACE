"""Which published columns can be overwritten with the whole check suite still passing?


Every column of the four newest artefacts is overwritten on every row, first with a garbage
token and then with blank, the suite is run after each, and the file is restored byte-identically
before the next column. A column that survives BOTH modes is read by no control anywhere.

Run from the inspire2_v2 root. It writes nothing outside work/ and restores what it touches.
"""
import csv, hashlib, os, shutil, subprocess, sys, tempfile

ARTEFACTS = [
    "stage2_resolved_%s.csv",
    "stage3_routed_%s.csv",
    "stage4_families_%s.csv",
    "stage5_lineage_%s.csv",
]
# The four Stage 6 shapes live in output/, not work/, and they are the files a reader outside this
# project actually opens. Finding 114 was measured on work/ alone because output/ did not exist.
PUBLISHED = [
    "lookup_%s.csv", "commodity_journeys_%s.csv", "lineage_timeline_%s.csv", "provenance_%s.csv",
]
CHECKS = [
    "check_stage2_apply_decisions.py", "check_stage3_route.py",
    "check_stage4_build_families.py", "check_stage5_lineage.py",
    "check_stage6_outputs.py", "check_decisive_distinctions.py",
    "check_rule_application.py", "check_medicine_families.py",
    "check_adjudication_queue.py",
]
FLOW = sys.argv[1] if len(sys.argv) > 1 else "imports"
WORK = "work"
GARBAGE = "CORRUPTED9999"


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def suite_passes():
    for name in CHECKS:
        r = subprocess.run([sys.executable, os.path.join("checks", name)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, name
    return True, ""


def overwrite(path, column, value):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)
    for r in rows:
        r[column] = value
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    # Prove nothing was lost by the rewrite itself.
    with open(path, encoding="utf-8-sig", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == len(rows), "row count moved on %s" % column
    return fields, len(rows)


backup = tempfile.mkdtemp(prefix="sweep_")
paths = [os.path.join(WORK, a % FLOW) for a in ARTEFACTS]
paths += [os.path.join("output", "%s_%s" % (FLOW, p % "")).replace("_.csv", ".csv")
          for p in PUBLISHED]
for p in paths:
    shutil.copy2(p, backup)
before = {p: digest(p) for p in paths}

ok, who = suite_passes()
assert ok, "the suite must be green BEFORE the sweep, but %s failed" % who
print("baseline: the suite is green\n")

unguarded, guarded, onesided, total = [], [], [], 0
try:
    for path in paths:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            columns = csv.DictReader(fh).fieldnames
        print("== %s: %d columns ==" % (os.path.basename(path), len(columns)))
        for column in columns:
            total += 1
            caught = {}
            for label, value in (("garbled", GARBAGE), ("blanked", "")):
                overwrite(path, column, value)
                passed, _ = suite_passes()
                caught[label] = not passed
                shutil.copy2(os.path.join(backup, os.path.basename(path)), path)
                assert digest(path) == before[path], "restore of %s was not byte-identical" % path
            key = (os.path.basename(path), column)
            if not any(caught.values()):
                unguarded.append(key)
                print("   UNGUARDED  %-26s survives both garbling and blanking" % column)
            elif all(caught.values()):
                guarded.append(key)
            else:
                mode = "garbled" if caught["garbled"] else "blanked"
                onesided.append((key, mode))
                print("   ONE-SIDED  %-26s caught only when %s" % (column, mode))
finally:
    for p in paths:
        shutil.copy2(os.path.join(backup, os.path.basename(p)), p)
        assert digest(p) == before[p], "final restore of %s was not byte-identical" % p
    print("\nall four artefacts restored byte-identically")

print("\n%d columns swept: %d guarded, %d one-sided, %d unguarded"
      % (total, len(guarded), len(onesided), len(unguarded)))
print("\nUNGUARDED:")
for f, c in unguarded:
    print("   %-28s %s" % (f, c))
print("\nONE-SIDED:")
for (f, c), mode in onesided:
    print("   %-28s %-26s caught only when %s" % (f, c, mode))
