"""Stage 2. Turn the answers into resolved successions, and say plainly what is still open.


Every stage before this one produced evidence. None of them wrote a link. This is the first stage
that says "this retirement goes there", and it does so from two sources only: what the official
record decided outright, and what the analyst answered in the workbook. It computes nothing about
which successor is right. Where neither source speaks, it says so and refuses to guess.

THE LAYER ORDER, WHICH THIS STAGE ENFORCES RATHER THAN RESTATES
--------------------------------------------------------------
The record decides, a meaning gate may only veto, and text may only rank. So:

  - A retirement Canada's ten-digit concordance NAMED is taken from the record. It never reaches
    the workbook and the analyst is never asked, because asking would invite an answer that
    outranks its own evidence. 89 import retirements are in this position.
  - Every other retirement is the analyst's, and its answer comes from the workbook. 231 rows,
    which read 230 until the sixth span split added a retirement on 2026-08-17.
  - The two sets are disjoint and together they are every retirement. The stage refuses to run
    if that is not exactly true, because a retirement in both would have two answers and a
    retirement in neither would silently vanish from the crosswalk.

WHAT AN ANSWER MEANS
--------------------
The vocabulary is not redefined here. `normalise_decision` is imported from
s05_make_adjudication_queue, which owns it, so a synonym the workbook accepts cannot become a word
this stage rejects. Two files holding the same vocabulary is how they drift.

  approve     the proposed successor is correct           -> that code
  second      the second alternative is correct           -> that code
  reject      the proposal is wrong, another code is right-> the code the analyst named
  reject      with the successor written as `none`        -> the goods left Chapter 30
  none        the same statement, written in the decision -> the goods left Chapter 30
  unresolved  examined, and the answer cannot be reached  -> open, and not a hold
  blank       not answered                                -> held, with the reason stated

One outcome is not an answer at all. Where Stage 1a records that a stoppage is `trade_ceased_only`
-- the delivery declares no termination and the number was never handed on -- no transfer took
place, so the row resolves to `not_a_retirement` and carries no successor whatever the workbook
says. The rule lives in s02_stage1_candidates.py and is pinned by check_stage1_candidates.py. Where an
answer would have named a successor the build refuses, because the record and the answer then
disagree about whether the event happened at all.

A BLANK IS NOT AN ANSWER, AND THAT IS THE POINT
-----------------------------------------------
The released crosswalk read a blank decision as approval. That is defect D1 and it is the reason
this project exists. Here a blank produces `held`, never a link, and the outcome carries the
reason it is held: a correlation table has not been read, or the retirement sits too close to the
end of the delivery to be distinguished from a quiet spell.

The build does NOT refuse on held rows, however many there are; check_stage2_apply_decisions.py
pins the count so it cannot drift unnoticed. The plan's "zero rows left undecided"
is a GATE criterion, not a stage one: the gate refuses to release a crosswalk with open rows,
while this stage's job is to state honestly how many there are and why. Refusing here would mean
no downstream stage could ever be built or tested until the last WCO PDF was extracted.

WHAT IT REFUSES TO DO
---------------------
Each of these is a way the released crosswalk went wrong or could have:

  - name a successor that never traded in the delivery
  - name a code as its own successor
  - read a decision word it does not understand, or treat one as a blank
  - accept `reject` without a successor or an explicit `none`, which is a hole with a tick beside it
  - lose or invent a retirement, or let the value stop reconciling
"""

import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
DECISIONS_DIR = PROJECT_ROOT / "decisions"

sys.path.insert(0, str(Path(__file__).resolve().parent))
# description_shown and span_shown are imported, never re-implemented. They answer "which LIFE of
# this code could receive THIS retirement", and this stage used to answer it with "the last life
# the code ever had", which is a different question. Finding 102.
from s05_make_adjudication_queue import (  # noqa: E402
    description_shown, dotted, normalise_decision, span_shown)
# Imported, never restated. Stage 1a owns what makes a stoppage a retirement, exactly as
# s05_make_adjudication_queue owns the decision vocabulary above. It also owns which boundaries a
# CBSA concordance covers, which is how a decided row names its edition below.
from s02_stage1_candidates import (  # noqa: E402
    CBSA_COVERED_BOUNDARIES, RETIREMENT_TRADE_CEASED_ONLY)

FLOWS = ("imports", "exports")

COLUMNS = [
    "link_id", "retiring_code", "span_index", "flow", "last_period", "total_value_cad",
    "retiring_description",
    "successor", "successor_description", "successor_first_traded", "successor_last_traded",
    "outcome", "authority", "basis", "detail",
    "decided_by", "decided_on", "reason", "overrode_a_hold",
]

# The five outcomes. Only the first puts a link in the crosswalk.
SUCCEEDED = "succeeded"
LEFT_CHAPTER = "left_chapter"
UNRESOLVED = "unresolved"
HELD = "held"
# Trade stopped and nothing in the record says the classification did. Not an open question and
# not a chapter exit: no transfer took place, so there is nothing to link and nothing to wait for.
# Stage 1a decides this from the delivery's own termination notes; the rule and the era its
# evidence supports are stated there, and check_stage1_candidates.py pins both.
NOT_A_RETIREMENT = "not_a_retirement"


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def link_id_for(flow, code, last_period):
    """Built exactly as s05_make_adjudication_queue builds it, so the two files join."""
    return "%s:%s:%s-%s" % (flow, dotted(code), last_period[:4], last_period[4:])


def stop(message, examples=()):
    print()
    print("Stage 2 STOPPED: %s" % message)
    for item in list(examples)[:8]:
        print("    %s" % (item,))
    raise SystemExit(1)


def resolve(flow, official, answers, spans, lives, retirement_bases):
    """One row per retirement. Nothing here chooses a successor; it reads which one was chosen."""
    rows, problems = [], {
        "both": [], "neither": [], "unreadable": [], "no_target": [], "unreal": [], "self": [],
        "would_link": [], "empty_target": [],
    }
    seen_links = set()

    for entry in official:
        code, last = entry["retiring_code"], entry["last_period"]
        link = link_id_for(flow, code, last)
        seen_links.add(link)
        answer = answers.get(link)
        record_decided = entry["outcome"] == "decided"

        if record_decided and answer is not None:
            problems["both"].append(link)
            continue
        if not record_decided and answer is None:
            problems["neither"].append(link)
            continue

        successor = ""
        overrode = "no"
        decided_by = decided_on = reason = ""

        if record_decided:
            destinations = [d for d in entry["official_destinations"].split(";") if d]
            successor = destinations[0]
            outcome, authority, basis = SUCCEEDED, "official_record", "decided"
            # NAME THE EDITION, NOT THE HOP MONTH. This read "at %s" with the row's boundary
            # month, so a code that went quiet early printed "concordance at 201610", citing a
            # concordance that does not exist. The concordance is matched on the year the record
            # calls the code obsolete, and that year names which of the two editions spoke.
            # Finding 151.
            editions = [b for b in CBSA_COVERED_BOUNDARIES
                        if b[:4] == entry["last_period"][:4]]
            if len(editions) != 1:
                stop("a concordance decided %s but no single covered boundary shares its "
                     "year %s. A third concordance needs its edition named here."
                     % (link, entry["last_period"][:4]))
            detail = ("named outright by Canada's ten-digit concordance, %s to %d"
                      % (editions[0][:4], int(editions[0][:4]) + 1))
        else:
            written = (answer.get("decision") or "").strip()
            word = normalise_decision(written)
            decided_by = (answer.get("decided_by") or "").strip()
            decided_on = (answer.get("decided_on") or "").strip()
            reason = (answer.get("reason") or "").strip()
            verdict = (answer.get("verdict") or "")
            if verdict.startswith("DO NOT DECIDE") and written:
                overrode = "yes"

            if written and not word:
                # Written, and not a word the workbook's own vocabulary can read. Treating this as
                # a blank would file an opinion as an absence, which is the D1 shape again.
                problems["unreadable"].append("%s wrote %r" % (link, written))
                continue

            if not word:
                outcome, authority, basis = HELD, "none_yet", "not_answered"
                detail = verdict.split("-", 1)[-1].strip() if "-" in verdict else "not answered"
            elif word == "approve":
                successor = (answer.get("proposed_successor") or "").strip()
                if not successor:
                    problems["empty_target"].append("%s: `approve` but no proposal is offered" % link)
                    continue
                outcome, authority, basis = SUCCEEDED, "analyst", "approve"
                detail = "the analyst accepted the proposal"
            elif word == "second":
                successor = (answer.get("second_alternative") or "").strip()
                # AN ANSWER THAT NAMES NOTHING IS NOT AN ANSWER. This used to produce
                # outcome=succeeded carrying an empty successor, which reads as a settled link and
                # is a hole. It went unnoticed while no row was in that position; finding 106 put
                # one there, because correcting the era a candidate is read in withdrew the second
                # alternative from a row already answered `second`. The analyst's decision is not
                # overwritten and not guessed at: the build stops and says which row needs them.
                if not successor:
                    problems["empty_target"].append(
                        "%s: `second` but no second alternative is offered" % link)
                    continue
                outcome, authority, basis = SUCCEEDED, "analyst", "second"
                detail = "the analyst preferred the second alternative to the proposal"
            elif word == "reject":
                named = (answer.get("correct_successor_if_rejected") or "").strip()
                if not named:
                    # A reject records only that the proposal is wrong. Without a successor or an
                    # explicit `none` it is a hole in the crosswalk wearing a decision's clothes.
                    problems["no_target"].append(link)
                    continue
                if named.lower() == "none":
                    outcome, authority, basis = LEFT_CHAPTER, "analyst", "reject_none"
                    detail = "the analyst rejected the proposal and recorded no successor in this chapter"
                else:
                    successor = named
                    outcome, authority, basis = SUCCEEDED, "analyst", "reject_named"
                    detail = "the analyst rejected the proposal and named %s instead" % named
            elif word == "none":
                outcome, authority, basis = LEFT_CHAPTER, "analyst", "none"
                detail = "the analyst recorded no successor inside this chapter"
            elif word == "unresolved":
                outcome, authority, basis = UNRESOLVED, "analyst", "unresolved"
                detail = "the analyst examined it and the answer could not be reached"
            else:
                problems["unreadable"].append("%s normalised to %r" % (link, word))
                continue

        # The record outranks both sources above, and here it speaks by declaring nothing: no
        # termination, and the number never handed on. A stoppage that is not a retirement cannot
        # have a successor, so this replaces the outcome rather than competing with it.
        #
        # It never silently overwrites a link. Where an answer would have named one, the two
        # genuinely disagree about whether an event happened at all, and that is for a person.
        # Today no row is in that position: all five answered rows read `reject -> none`, which
        # is the same crosswalk this produces. The analyst's cells are carried either way.
        if retirement_bases.get((code, last)) == RETIREMENT_TRADE_CEASED_ONLY:
            if successor:
                problems["would_link"].append("%s -> %s" % (link, successor))
                continue
            outcome, authority, basis = NOT_A_RETIREMENT, "delivery", "no_termination_declared"
            detail = ("the delivery declares no termination for this line and the number was "
                      "never reused, so trade ceased without the classification ending")
            # Not an override, and recording one here would be a libel on the record. These rows
            # carry "DO NOT DECIDE" only because this rule now puts it there; when the five
            # answered rows were answered the queue was asking for a decision. An override means
            # the analyst went ahead of the evidence, and none of them did.
            overrode = "no"

        if successor:
            bare = digits(successor)
            if bare not in lives:
                problems["unreal"].append("%s -> %s, which never traded" % (link, successor))
                continue
            if bare == digits(code):
                problems["self"].append("%s -> itself" % link)
                continue

        # The life that could receive THIS retirement, read the way the queue builder reads it.
        first_shown, last_shown, wording = ("", "", "")
        if successor:
            bare = digits(successor)
            first_shown, last_shown = span_shown(
                {c: [(a, b) for a, b, _t in v] for c, v in lives.items()}, bare, last)[:2]
            wording = description_shown(lives, bare, last)
        rows.append({
            "link_id": link,
            "retiring_code": dotted(code),
            "span_index": spans.get((code, last), ""),
            "flow": flow,
            "last_period": last,
            "total_value_cad": entry["total_value_cad"],
            "retiring_description": entry["description"],
            "successor": dotted(digits(successor)) if successor else "",
            "successor_description": wording,
            "successor_first_traded": first_shown,
            "successor_last_traded": last_shown,
            "outcome": outcome,
            "authority": authority,
            "basis": basis,
            "detail": detail,
            "decided_by": decided_by,
            "decided_on": decided_on,
            "reason": reason,
            "overrode_a_hold": overrode,
        })

    stray = [link for link in answers if link not in seen_links and link.startswith(flow + ":")]
    if stray:
        problems.setdefault("stray", []).extend(stray)
    return rows, problems


def describe(flow, rows, official):
    total = sum(float(r["total_value_cad"]) for r in rows)
    print("%s:" % flow)
    print("  retirements resolved              : %d, CAD {:,.0f}".format(total) % len(rows))
    by_outcome = Counter(r["outcome"] for r in rows)
    values = {}
    for r in rows:
        values[r["outcome"]] = values.get(r["outcome"], 0.0) + float(r["total_value_cad"])
    for outcome in (SUCCEEDED, LEFT_CHAPTER, NOT_A_RETIREMENT, UNRESOLVED, HELD):
        if by_outcome.get(outcome):
            print("      %-14s %4d  CAD {:>18,.0f}".format(values[outcome]) % (outcome,
                                                                              by_outcome[outcome]))
    print("  who answered each one:")
    for authority, n in sorted(Counter(r["authority"] for r in rows).items(), key=lambda kv: -kv[1]):
        print("      %-16s %4d" % (authority, n))
    print("  on what basis:")
    for basis, n in sorted(Counter(r["basis"] for r in rows).items(), key=lambda kv: -kv[1]):
        print("      %-16s %4d" % (basis, n))
    overrode = [r for r in rows if r["overrode_a_hold"] == "yes"]
    if overrode:
        print("  answered while HELD               : %d, CAD {:,.0f}".format(
            sum(float(r["total_value_cad"]) for r in overrode)) % len(overrode))
        print("      the answers stand; the hold says the record has not spoken yet, not that")
        print("      the analyst is wrong. The workbook warns beside each one.")
    open_rows = [r for r in rows if r["outcome"] in (HELD, UNRESOLVED)]
    print("  STILL OPEN                        : %d, CAD {:,.0f}".format(
        sum(float(r["total_value_cad"]) for r in open_rows)) % len(open_rows))
    if open_rows:
        print("      Not a defect and not a failure. No crosswalk may be RELEASED while any")
        print("      remain, which is a gate's job; stating the number is this stage's.")


def main():
    answers = {}
    for row in load(DECISIONS_DIR / "stage2_decisions.csv"):
        answers[row["link_id"]] = row

    print("Stage 2: apply the answers. This stage writes links and computes none.")
    print("  answers read from decisions/stage2_decisions.csv : %d row(s)" % len(answers))
    print()

    grand = 0.0
    for flow in FLOWS:
        official_path = WORK_DIR / ("stage1_official_%s.csv" % flow)
        if not official_path.exists():
            stop("%s not found. Run s03_stage1b_official_record.py first." % official_path)
        official = load(official_path)

        spans = {}
        retirement_bases = {}
        for row in load(WORK_DIR / ("stage1_candidates_%s.csv" % flow)):
            spans[(row["retiring_code"], row["last_period"])] = row["span_index"]
            retirement_bases[(row["retiring_code"], row["last_period"])] = row["retirement_basis"]

        # ONE ENTRY PER LIFE, NOT ONE PER CODE. This map used to keep only the life with the
        # latest end, so a successor with two lives was described by its final one whatever era
        # the trade actually transferred in. 107 of 299 links carried a span from a closed life
        # and 89 also carried its wording, CAD 14,210,417,105 of retirement value, including
        # 3001.90.00.90 shown as "Heparin & its salts" against a 1997-12 retirement when the life
        # that receives the trade reads "Other human or animal subs prepared ... nes". That is the
        # exact misreading the analyst had to refute by hand at rows 223 and 225. Finding 102.
        lives = {}
        for row in load(WORK_DIR / ("commodity_inventory_%s.csv" % flow)):
            lives.setdefault(row["hs_code"], []).append(
                (row["first_period"], row["last_period"], row["description"]))
        for entries in lives.values():
            entries.sort()

        rows, problems = resolve(flow, official, answers, spans, lives, retirement_bases)

        if problems["both"]:
            stop("%d retirement(s) are both settled by the record and answered in the workbook. "
                 "One of them would have to lose." % len(problems["both"]), problems["both"])
        if problems["neither"]:
            stop("%d retirement(s) reach neither the record nor the workbook, so they would "
                 "vanish from the crosswalk without anything saying so." % len(problems["neither"]),
                 problems["neither"])
        if problems["unreadable"]:
            stop("%d decision(s) are written in words the workbook's vocabulary cannot read. A "
                 "misspelling looks decided and reads as blank." % len(problems["unreadable"]),
                 problems["unreadable"])
        if problems["no_target"]:
            stop("%d rejected row(s) name no successor and no explicit `none`. A reject records "
                 "only that the proposal is wrong." % len(problems["no_target"]),
                 problems["no_target"])
        if problems["unreal"]:
            stop("%d successor(s) never traded in this delivery." % len(problems["unreal"]),
                 problems["unreal"])
        if problems["self"]:
            stop("%d row(s) name the retiring code as its own successor." % len(problems["self"]),
                 problems["self"])
        if problems["empty_target"]:
            stop("%d answered row(s) name a target the sheet no longer offers. The decision stands"
                 " and cannot be applied; it needs the analyst, not a guess."
                 % len(problems["empty_target"]), problems["empty_target"])
        if problems["would_link"]:
            stop("%d row(s) name a successor for a stoppage the delivery does not record as a "
                 "termination. The record and the answer disagree about whether the "
                 "classification ended at all, which is a person's to settle."
                 % len(problems["would_link"]), problems["would_link"])
        if problems.get("stray"):
            stop("%d workbook row(s) describe a retirement this delivery does not hold."
                 % len(problems["stray"]), problems["stray"])

        if len(rows) != len(official):
            stop("%d retirement(s) in, %d out. Nothing may be lost or invented here."
                 % (len(official), len(rows)))
        expected = sum(float(r["total_value_cad"]) for r in official)
        got = sum(float(r["total_value_cad"]) for r in rows)
        if abs(expected - got) > 0.005:
            stop("value does not reconcile: CAD %.2f in, CAD %.2f out" % (expected, got))
        grand += got

        describe(flow, rows, official)
        destination = WORK_DIR / ("stage2_resolved_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()

    print("Stage 2 complete. CAD {:,.0f} of retirement accounted for, every row carrying who "
          "answered it.".format(grand))


if __name__ == "__main__":
    main()
