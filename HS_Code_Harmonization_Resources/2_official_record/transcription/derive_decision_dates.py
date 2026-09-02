"""
When each decision first entered the record, read off the repository's own history.


    python evidence/provenance/derive_decision_dates.py

Writes evidence/provenance/decision_dates.csv. Run it by hand after committing decisions, the
same way evidence/wto/extract_wto_pairs.py is run by hand. The release build reads the CSV and
never runs this.


WHY THIS IS EVIDENCE AND NOT A STAGE
------------------------------------
`decided_on` was empty on all 203 decided rows. The plan requires every decision to carry "who
decided it, when, and on what basis", so this is a gap in the record rather than a missing
convenience.

The obvious fix is to have the pipeline stamp the date when it first sees a decision. That fix
is wrong here, and the reason is worth stating. **Nothing in pipeline/ or checks/ reads the
clock. Not once.** That is what lets the end-to-end runner delete thirteen artefacts, rebuild
them twice and compare them byte for byte. A single call to date.today() inside the build would
make the artefacts a function of when they were built, and the reproducibility proof would be
worth nothing. So the date is derived out here, committed as data, and read by the build as data.

It also happens to be the more honest answer. A clock inside the build records when the build
ran. Git records when the decision was written down, which is a fact about the decision.


WHAT THE DATE MEANS, EXACTLY
----------------------------
For each link_id, the author date of the FIRST commit whose decisions/stage2_decisions.csv
carries a non-empty `decision` for that row, or whose decision differs from the commit before
it. That is the day the decision entered the record.

It is NOT necessarily the day the author made up their mind. A decision taken on a Tuesday and
committed on a Wednesday reads as Wednesday. The basis column says so on every row rather than
leaving a reader to assume otherwise, and `decided_on_source` names the commit so any row can be
checked. Where a decision was later changed, the date is the change, because the earlier value
is not the decision the crosswalk carries.
"""

import csv
import io
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHEET = "decisions/stage2_decisions.csv"
OUT = HERE / "decision_dates.csv"

COLUMNS = ("link_id", "decision", "decided_on", "decided_on_basis",
           "decided_on_source", "changed_after_first_entry")

BASIS = ("the author date of the first commit recording this decision in inspire2_v2; "
         "the day it entered the record, not necessarily the day it was taken")
BASIS_CHANGED = ("the author date of the commit that last CHANGED this decision; the earlier "
                 "value is not the decision the crosswalk carries")


def git(args):
    result = subprocess.run(["git", "-C", str(REPO)] + args, capture_output=True)
    if result.returncode:
        raise SystemExit("git %s failed: %s"
                         % (" ".join(args), result.stderr.decode("utf-8", "replace")))
    return result.stdout


def decisions_at(sha):
    """link_id -> decision, as the sheet stood at that commit."""
    raw = git(["show", "%s:%s" % (sha, SHEET)]).decode("utf-8-sig", "replace")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        value = (row.get("decision") or "").strip()
        if value:
            out[row["link_id"]] = value
    return out


def main():
    history = [line.split("|", 1) for line in
               git(["log", "--reverse", "--format=%H|%ad", "--date=short", "--", SHEET])
               .decode().splitlines() if line.strip()]
    if not history:
        raise SystemExit("no history for %s" % SHEET)

    first, changed, previous = {}, set(), {}
    for sha, date in history:
        current = decisions_at(sha)
        for link_id, value in current.items():
            if link_id not in previous:
                first[link_id] = (date, sha)
            elif previous[link_id] != value:
                first[link_id] = (date, sha)
                changed.add(link_id)
        previous = current

    live_path = REPO / SHEET
    with open(live_path, newline="", encoding="utf-8-sig") as handle:
        live = [r for r in csv.DictReader(handle) if (r.get("decision") or "").strip()]

    rows, missing = [], []
    for row in live:
        link_id = row["link_id"]
        if link_id not in first:
            missing.append(link_id)
            continue
        date, sha = first[link_id]
        rows.append({
            "link_id": link_id,
            "decision": (row.get("decision") or "").strip(),
            "decided_on": date,
            "decided_on_basis": BASIS_CHANGED if link_id in changed else BASIS,
            "decided_on_source": sha[:9],
            "changed_after_first_entry": "yes" if link_id in changed else "no",
        })

    rows.sort(key=lambda r: (r["decided_on"], r["link_id"]))
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    print("commits touching the sheet : %d" % len(history))
    print("decisions on the sheet now : %d" % len(live))
    print("dated from history         : %d" % len(rows))
    print("undatable                  : %d" % len(missing))
    for link_id in missing[:10]:
        print("   %s" % link_id)
    if missing:
        print("   An undatable row is one whose decision is on the sheet and in no commit, which")
        print("   means it was entered and not yet committed. Commit it, then run this again.")
    counts = {}
    for row in rows:
        counts[row["decided_on"]] = counts.get(row["decided_on"], 0) + 1
    print()
    print("when the decisions were recorded:")
    for date in sorted(counts):
        print("   %s  %3d" % (date, counts[date]))
    print()
    print("later changed than first entered : %d" % len(changed))
    print("written: %s" % os.path.relpath(OUT, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
