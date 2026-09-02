"""Rebuild this distribution set into a runnable tree, then run the whole build and its checks.

Inputs:  the folders beside this script, and the two Statistics Canada extracts
Outputs: a working tree, and the verification suite's verdict

WHAT THIS IS FOR
----------------
The folders here are numbered for reading, not for running. The stages carry an s01 to s10
prefix so a reader meets them in order, the checks sit in their own folder, and the working
tables and the decisions share one folder. The build expects a different shape: stages in
pipeline/, checks in checks/, tables in work/ and decisions/, databases in source/.

This script writes that shape into a new directory, using each folder's LAYOUT.txt to place
every file where the build expects it. Nothing here is guessed: LAYOUT.txt is written by the
same script that built these folders, so the two cannot fall out of step.

THE TWO DATABASES ARE NOT IN THIS PACKAGE
-----------------------------------------
They come to 650 MB, and they are public. Statistics Canada's Canadian International
Merchandise Trade tables for Chapter 30 are the source; PROVENANCE.md in folder 4 names
the datasets and the extraction exactly. Point --source at a directory holding the two
databases this package names, or place them in the new tree's source/ directly. Which two they
are is read from the shipped stage 0, never restated here, so it cannot go out of date.

    python REPRODUCE.py --source PATH_TO_THE_DATABASES
    python REPRODUCE.py --into ../rebuild --source PATH_TO_THE_DATABASES
    python REPRODUCE.py --prepare-only          # build the tree, do not run

Exit code 0 means the suite ran and reported SOUND.
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Folder 1 carries the published tables and, beside them, the two identifier crosswalks and
# the two disclosure tables. Stage 6 reads the identifier crosswalks, so folder 1 is an
# input to the build and not only its result.
FOLDERS = ["1_outputs_for_pharmatrace", "2_official_record", "3_crosswalk_code",
           "4_candidates_and_decisions", "5_verification_suite"]
def needed_databases():
    """The databases the pipeline actually opens, READ FROM THE SHIPPED STAGE 0 rather than
    restated here.

    This was a hardcoded pair until 2026-08-31, and on that day the export flow moved from
    domestic_exports.db to exports.db. The pair was not updated with it, so REPRODUCE.py went on
    demanding the domestic extract, copying it into source/, and leaving the tree without the
    exports.db that stage 0 opens. The rebuild then failed at the first stage. Nothing caught it:
    the end-to-end suite runs the stages straight from the delivery and never calls this script,
    so the one command a reader is given was the only thing broken, and it is the command the
    reproducibility claim rests on. Deriving the names means the two cannot disagree again.
    """
    stage0 = os.path.join(HERE, "3_crosswalk_code", "s01_stage0_read_source.py")
    if not os.path.exists(stage0):
        raise SystemExit("3_crosswalk_code/s01_stage0_read_source.py is missing, so the "
                         "databases the build needs cannot be read. This package is incomplete.")
    found = re.findall(r'SOURCE_DIR\s*/\s*"([^"]+\.db)"',
                       io.open(stage0, encoding="utf-8").read())
    ordered = []
    for name in found:
        if name not in ordered:
            ordered.append(name)
    if not ordered:
        raise SystemExit("no database name could be read out of s01_stage0_read_source.py, so "
                         "there is nothing to check --source against.")
    return tuple(ordered)


def read_layout(folder):
    """The shipped-name to repository-path pairs the build script recorded."""
    path = os.path.join(HERE, folder, "LAYOUT.txt")
    if not os.path.exists(path):
        raise SystemExit("%s has no LAYOUT.txt; this package is incomplete." % folder)
    pairs = []
    for line in io.open(path, encoding="utf-8").read().splitlines():
        # Split on the run of spaces between the columns, not on every space: a shipped name
        # may contain spaces, and splitting on all of them drops the file silently.
        parts = [c for c in re.split(r"\s{2,}", line.strip()) if c]
        # Two tokens is a mapping. A file that lands at the tree root, THRESHOLDS.md
        # among them, carries no slash and must not be filtered out by looking for one.
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    if not pairs:
        raise SystemExit("%s/LAYOUT.txt names no files." % folder)
    return pairs


def unprefix(name):
    """s06_stage2_apply_decisions.py -> stage2_apply_decisions.py"""
    return re.sub(r"^s\d\d_", "", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--into", default=os.path.join(HERE, "_reproduce"))
    ap.add_argument("--source", default=None,
                    help="a directory holding the databases named in PROVENANCE.md")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--link", action="store_true",
                    help="hard link the databases instead of copying. Faster, but one "
                         "stage opens them writable, so the originals are exposed.")
    args = ap.parse_args()
    root = os.path.abspath(args.into)
    NEEDED = needed_databases()
    print("databases this build reads, from the shipped stage 0: %s"
          % ", ".join(NEEDED))

    stage_names = {}
    for folder in FOLDERS:
        for shipped, repo_path in read_layout(folder):
            target = os.path.join(root, repo_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            # The shipped name may carry a subfolder: folder 2 groups its files into
            # source_documents/, extracts/ and transcription/. The separator in LAYOUT.txt is
            # always a forward slash, whatever platform wrote it.
            source = os.path.join(HERE, folder, shipped.replace("/", os.sep))
            shutil.copyfile(source, target)
            if folder == "3_crosswalk_code" and shipped.endswith(".py"):
                stage_names[shipped[:-3]] = unprefix(shipped)[:-3]

    # The stage copies import each other by their prefixed names. Put the repository names back,
    # because the checks and the runner call the stages by those.
    pipeline = os.path.join(root, "pipeline")
    for name in sorted(os.listdir(pipeline)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(pipeline, name)
        text = io.open(path, encoding="utf-8").read()
        for prefixed, plain in stage_names.items():
            text = re.sub(r"\b%s\b" % re.escape(prefixed), plain, text)
        io.open(path, "w", encoding="utf-8", newline="\n").write(text)

    for folder in ("source", "output"):
        os.makedirs(os.path.join(root, folder), exist_ok=True)

    if args.source:
        for name in NEEDED:
            src = os.path.join(os.path.abspath(args.source), name)
            if not os.path.exists(src):
                raise SystemExit("%s is not in %s" % (name, args.source))
            dst = os.path.join(root, "source", name)
            if os.path.exists(dst):
                continue
            # Copy, never link. One stage opens the database without the read-only flag, so a
            # hard link would put the reader's own extracts at risk of being written through.
            if args.link:
                os.link(src, dst)
            else:
                print("  copying %s (%.0f MB)" % (name, os.path.getsize(src) / 1e6))
                shutil.copyfile(src, dst)

    missing = [n for n in NEEDED if not os.path.exists(os.path.join(root, "source", n))]
    print("tree written to %s" % root)
    if missing:
        print("\nstill needed in %s:" % os.path.join(root, "source"))
        for n in missing:
            print("    %s" % n)
        print("\nThey are the Statistics Canada Chapter 30 extracts named exactly in\n"
              "    %s\n" % os.path.join(root, "source", "PROVENANCE.md"))
        return 1
    if args.prepare_only:
        print("prepared, not run")
        return 0

    print("running: python checks/run_pipeline_end_to_end.py\n")
    return subprocess.call([sys.executable, os.path.join("checks", "run_pipeline_end_to_end.py")],
                           cwd=root)


if __name__ == "__main__":
    sys.exit(main())
