# -*- coding: utf-8 -*-
"""Find places where the crosswalk joined two products across a distinction that the
tariff treats as decisive.


WHAT PROBLEM THIS SOLVES

Successor candidates are ranked by how closely their two descriptions match as text.
That comparison counts shared letters. It cannot read meaning. Two of the sharpest
distinctions in Chapter 30 are nearly invisible to it:

    "frs" means for retail sale          "nfrs" means not for retail sale
    "hum" means for human use            "vet" means for veterinary use

Each pair differs by one or two letters and means the opposite thing. So two
descriptions can score very highly while naming products the tariff deliberately keeps
apart.

This script reads a list of such distinctions from decisive_distinctions.csv and reports
every step in a product's history where the two descriptions fall on opposite sides of
one. It changes nothing. It only reports.

HOW EACH DISTINCTION IS DECIDED

A distinction has two sides, each a list of phrases. For one description, the result is
one of four:

    one side        a phrase from the first side is stated, and none from the other
    other side      the reverse
    both            phrases from both sides are stated, for example "for human or
                    veterinary use". Products genuinely usable both ways exist, so this
                    is treated as compatible with either side and never reported.
    not mentioned   neither side appears

A step is reported only when one description is on one side and the other description is
on the other.

WHY NEGATION IS THE HARD PART

An earlier version of this script reported seven problems, and six of them were wrong.
Every one was a negation it failed to read. It treated "not in doses for retail sale" as
saying doses, and "other than of animal origin" as saying animal origin, which is the
opposite of what those phrases mean. That is the very mistake this script exists to
catch, so the negation handling below is the part that matters most.

A phrase counts as negated when a reversing word appears before it in the same clause,
where clauses are separated by commas and semicolons. A reversing word that is part of
the phrase itself does not count, so "not for retail sale" states itself rather than
cancelling itself.

WHY THERE IS A SELF TEST

A report of zero problems can mean the data is clean, or it can mean the script is
broken. Those look identical from outside. This project has already paid for that
confusion once, with a checksum list that compared files against themselves and so could
never fail. The self test below runs first, on wordings whose right answer is known, and
the script refuses to examine real data if it fails.

HOW TO RUN

    python check_decisive_distinctions.py

Reads only. Exit code 0 means nothing was reported. Exit 1 means something was reported,
which is a prompt to look rather than a proven error. Exit 2 means the self test failed.
Exit 3 means no history file existed, so nothing was examined and the result is not a clean
bill of health. Stages 1 to 6 write those files and none is built yet, so 3 is expected today.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)          # inspire2_v2/
RULES_FILE = os.path.join(PROJECT, "decisions", "decisive_distinctions.csv")

# Descriptions must be expanded from Statistics Canada shorthand before any of this
# means anything: the distinction lives in "veterinary" and "human", not in "vet" and
# "hum".
# The expander is carried inside this project at pipeline/_shorthand.py. It used to be read
# from inspire2/simple, a path that resolved to inspire2_v2/checks/inspire2/simple and has
# never existed here, so this check could not run at all until 2026-08-10. No path may point
# outside this project, which is why the copy travels with it.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
from _shorthand import expand_shorthand  # noqa: E402

# The gate logic moved to pipeline/meaning_gates.py on 2026-08-10, when Stage 1c needed it in
# the pipeline rather than inside a check. It is imported unchanged. The 56 wordings below are
# the independent part: each states an answer a correct reading must give, and they were written
# without reference to how the code arrives at it.
from meaning_gates import (  # noqa: E402
    REVERSING_WORDS, TOO_COMMON_SHARE, KIND_PHRASE_PAIR, KIND_SPECIFIC_VS_RESIDUAL,
    KIND_BASKET_SUBSET, PATTERN_KINDS, RESIDUAL_MARKERS, FILLER_WORDS,
    split_into_clauses, phrase_pattern, is_stated, which_side,
    strip_residual_markers, carries_residual_marker, content_words,
    specific_vs_residual, list_items, basket_subset, swapped_term, load_rules, rule_fires,
)


def load_steps(path):
    """Each step is one move in a product's history: what it was, and what it became."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return [], None
    desc_col = "description" if "description" in rows[0] else None
    by_product = {}
    for r in rows:
        by_product.setdefault(r["uid"], []).append(r)
    steps = []
    for uid, rs in by_product.items():
        rs.sort(key=lambda x: int(x.get("step_number") or 0))
        for before, after in zip(rs, rs[1:]):
            steps.append((uid, before, after))
    return steps, desc_col


# Wordings whose right answer is known. Six of these are the exact phrases that fooled
# the first version of this script.
STATED_CASES = [
    ("Insulin, prepared for parenteral administration in humans, in bulk", "bulk", True),
    ("Medicaments, containing insulin, mixed, not in doses or forms for retail sale", "doses", False),
    ("Medicaments, containing insulin, mixed, not in doses or forms for retail sale", "for retail sale", False),
    ("Blood-grouping reagents, other than of animal origin, not elsewhere specified", "animal origin", False),
    ("Dried blood of animal origin", "animal origin", True),
    ("Dried blood of human origin", "human origin", True),
    ("Antibiotics, not elsewhere specified, for veterinary use, in dosage", "veterinary", True),
    ("Medicaments containing penicillins, for human use, in doses for retail sale", "for retail sale", True),
    ("Medicaments not put up for retail sale", "for retail sale", False),
    ("Medicaments, not for retail sale", "not for retail sale", True),
    # Added 2026-08-10 with the six new distinctions. The first two are why is_stated
    # gained word boundaries: a substring search reads each denial as the assertion.
    ("Vitamins, unmixed, for human use, in bulk", "mixed", False),
    ("Vitamins, mixed, for human use, in bulk", "mixed", True),
    ("Medicaments containing pseudoephedrine, in dosage", "ephedrine", False),
    ("Medicaments containing norephedrine, in dosage", "ephedrine", False),
    ("Medicaments containing ephedrine, in dosage", "ephedrine", True),
    ("Medicaments not containing antibiotics, in dosage", "containing antibiotics", False),
    ("Medicaments containing antibiotics, in dosage", "containing antibiotics", True),
    ("Dressings of woven fab o/t of cotton, nes", "of cotton", False),
    ("Dressings of woven fabric solely of cotton, nes", "of cotton", True),
    # The hyphenated negator the boundary fix could not reach, and the guard proving the
    # cure did not over-reach: "non-sterile" denies sterile, "sterile-packed" states it.
    ("Dressings, non-sterile, of paper", "sterile", False),
    ("Sterile-packed surgical catgut, for wound closure", "sterile", True),
]

SIDE_CASES = [
    ("Vaccines for human or veterinary use", ["human"], ["veterinary"], "both"),
    ("Vaccines, human use", ["human"], ["veterinary"], "one side"),
    ("Vaccines, veterinary use, not elsewhere specified", ["human"], ["veterinary"], "other side"),
    ("Heparin and its salts", ["human"], ["veterinary"], "not mentioned"),
    # The remaining five of the original seven, added 2026-08-10. Only "use" and "packing"
    # had side cases before, which is exactly how the sterility rule stayed inert unnoticed:
    # a rule with no both-directions case cannot be shown to fire at all.
    ("Insulin, in dosage", ["in measured doses", "doses", "dosage"], ["in bulk", "bulk"], "one side"),
    ("Insulin, in bulk", ["in measured doses", "doses", "dosage"], ["in bulk", "bulk"], "other side"),
    ("Dried blood of human origin", ["human origin"], ["animal origin"], "one side"),
    ("Dried blood of animal origin", ["human origin"], ["animal origin"], "other side"),
    ("Immunological products, modified", ["modified"], ["unmodified", "not modified"], "one side"),
    ("Immunological products, unmodified", ["modified"], ["unmodified", "not modified"], "other side"),
    ("Heparin, obtained by biotechnological processes",
     ["obtained by biotechnological processes"], ["not obtained by biotechnological processes"], "one side"),
    ("Heparin, not obtained by biotechnological processes",
     ["obtained by biotechnological processes"], ["not obtained by biotechnological processes"], "other side"),
    # All three spellings of the denial, added 2026-08-10. Until then the list held only
    # "non-sterile", so "not sterile" and "other than sterile" returned not mentioned and the
    # rule stayed silent instead of firing. No description in this delivery uses any of them,
    # which is exactly why nothing would have revealed the gap.
    ("Sterile surgical catgut, for wound closure",
     ["sterile"], ["non-sterile", "not sterile", "other than sterile"], "one side"),
    ("Dressings, non-sterile, of paper",
     ["sterile"], ["non-sterile", "not sterile", "other than sterile"], "other side"),
    ("Dressings, not sterile, of paper",
     ["sterile"], ["non-sterile", "not sterile", "other than sterile"], "other side"),
    ("Dressings, other than sterile, of paper",
     ["sterile"], ["non-sterile", "not sterile", "other than sterile"], "other side"),
    # The six distinctions added 2026-08-10, each proved in both directions.
    ("Medicaments containing antibiotics, in dosage",
     ["containing antibiotics"], ["not containing antibiotics"], "one side"),
    ("Medicaments not containing antibiotics, in dosage",
     ["containing antibiotics"], ["not containing antibiotics"], "other side"),
    ("Vitamins, mixed, for human use", ["mixed"], ["unmixed", "not mixed"], "one side"),
    ("Vitamins, unmixed, for human use", ["mixed"], ["unmixed", "not mixed"], "other side"),
    ("Prophylactic preparations for human use", ["prophylactic"], ["diagnostic"], "one side"),
    ("Diagnostic reagents for laboratory use", ["prophylactic"], ["diagnostic"], "other side"),
    # Corrected 2026-08-10 after the rules were run against the delivery for the first time.
    # These three contrasts were written from imagined wordings and matched nothing real. The
    # phrase lists below now mirror decisive_distinctions.csv, and the wordings are taken from
    # the delivery after shorthand expansion rather than invented.
    ("Dressings and sim articles, of woven fabric solely of cotton, nes",
     ["of cotton"], ["other than cotton", "other than of cotton", "o/t of cotton"], "one side"),
    ("Dressings/similar article of woven fabric other than of cotton",
     ["of cotton"], ["other than cotton", "other than of cotton", "o/t of cotton"], "other side"),
    ("Dressings and sim articles, of woven fabric solely of cotton, nes",
     ["woven"], ["knit", "knitted"], "one side"),
    ("Dressings of knit fabric, non-woven or felts, nes", ["woven"], ["knit", "knitted"], "other side"),
    ("Medicaments,containing pseudoephedrine/salts,in doses/for retail sale",
     ["pseudoephedrine"], ["norephedrine"], "one side"),
    ("Medicaments,containing norephedrine/salts,in doses/for retail sale",
     ["pseudoephedrine"], ["norephedrine"], "other side"),
    # A description naming both sides of the fabric contrast is compatible with either and must
    # never be reported. The delivery carries exactly this shape.
    ("Dressings/similar article of woven fabric other than of cotton; of knit fabric, non-woven",
     ["woven"], ["knit", "knitted"], "both"),
]

# The two rules that compare the descriptions against each other rather than looking for a
# word in either. Each is proved to fire AND proved not to fire, because a pattern rule that
# fires on everything is as useless as one that never fires.
PATTERN_CASES = [
    ("Vaccines against influenza virus", "Vaccines o/t against influenza virus",
     specific_vs_residual, True, "explicit complements, one side residual"),
    ("Vaccines o/t against influenza virus", "Vaccines against influenza virus",
     specific_vs_residual, True, "same pair, other direction"),
    ("Vaccines against influenza virus", "Vaccines against measles virus",
     specific_vs_residual, False, "different goods, neither residual"),
    # Corrected 2026-08-11. This expected False on the reasoning that two residual markers
    # cannot be complements, which was true only while "o/t" and "nes" were treated as one kind
    # of thing. They are opposites. "Vaccines o/t against influenza" is everything EXCEPT
    # influenza vaccines; "Vaccines nes against influenza" IS influenza vaccines, catch-all.
    # Those sets are disjoint, so this is a complement pair and firing is right.
    ("Vaccines o/t against influenza virus", "Vaccines nes against influenza virus",
     specific_vs_residual, True, "one excludes the named goods, the other IS them"),
    # The original rationale still holds where both markers are of the SAME kind.
    ("Vaccines o/t against influenza virus", "Vaccines o/t against influenza virus",
     specific_vs_residual, False, "two exclusions of the same thing are not complements"),
    ("Vaccines nes against influenza virus", "Vaccines nes against influenza virus",
     specific_vs_residual, False, "two catch-alls for the same thing are not complements"),
    # swapped_term. Same frame, one distinguishing word substituted. FLAGS, never removes.
    ("Anti-infective agents, for human use, in dosage",
     "Antineoplastic agents, for human use, in dosage",
     swapped_term, True, "the score measures the boilerplate, not the drug class"),
    ("Waste pharmaceuticals of the goods of heading 30.03",
     "Waste pharmaceuticals of the goods of heading 30.01",
     swapped_term, True, "0.9804 on text, and different headings entirely"),
    ("Lincomycin, for human use, in dosage", "Vancomycin, for human use, in dosage",
     swapped_term, True, "different antibiotics behind identical scaffolding"),
    ("Anti-infective agents, for human use, in dosage",
     "Anti-infective agents, for human use, in dosage, nes",
     swapped_term, False, "a catch-all succession swaps nothing"),
    ("Antibiotics nes, in dosage",
     "Medicaments,cont antibiotics,f therap/prophltc,in doses/frs,o/t No 30.02/05/06",
     swapped_term, False, "too little shared frame; this is a restyling, not a swap"),
    ("Antibiotics nes, in dosage, for veterinary use", "Antibiotics nes, in dosage",
     swapped_term, False, "the 1989 merge drops a term rather than swapping one"),
    ("Vaccines", "Antibiotics",
     swapped_term, False, "no shared frame at all, so the rule cannot speak"),
    # The fix itself: a specific line and its catch-all are a succession, not a complement.
    ("Anti-infective agents, for human use, in dosage",
     "Anti-infective agents, for human use, in dosage, nes",
     specific_vs_residual, False, "the nes bucket RECEIVES these goods when the line closes"),
    ("Mx of amino acids & protein hydrolysates, etc, in dosage",
     "Mx of amino acids & protein hydrolysates, etc, in dosage, nes",
     specific_vs_residual, False, "same, at the 1998 renumbering"),
    ("Vaccines against influenza virus", "Vaccines o/t against measles virus",
     specific_vs_residual, False, "residual, but of something else"),
    ("Toxins, toxoids, antitoxins", "Toxoids, antitoxins",
     basket_subset, True, "proper subset, workbook row 16"),
    ("Toxoids, antitoxins", "Toxins, toxoids, antitoxins",
     basket_subset, True, "same pair, other direction"),
    ("Vaccines, human use, in dosage", "Vaccines, veterinary use, in dosage",
     basket_subset, False, "same length, neither a subset"),
    ("Toxins, toxoids, antitoxins", "Toxins, toxoids, antitoxins",
     basket_subset, False, "identical lists are not a subset relation"),
    ("Insulin in bulk", "Insulin, in dosage",
     basket_subset, False, "too few items to be a list"),
]


def self_test():
    problems = []
    for text, phrase, expected in STATED_CASES:
        got = is_stated(text.lower(), phrase)
        if got != expected:
            problems.append("  %r in %r gave %s, expected %s" % (phrase, text[:52], got, expected))
    for text, one, other, expected in SIDE_CASES:
        got = which_side(text.lower(), one, other)
        if got != expected:
            problems.append("  %r gave %r, expected %r" % (text[:52], got, expected))
    for before, after, rule_fn, expected, why in PATTERN_CASES:
        got = rule_fn(before.lower(), after.lower())
        if got != expected:
            problems.append("  %s(%r, %r) gave %s, expected %s  [%s]"
                            % (rule_fn.__name__, before[:34], after[:34], got, expected, why))
    total = len(STATED_CASES) + len(SIDE_CASES) + len(PATTERN_CASES)
    if problems:
        print("SELF TEST: %d cases, FAILED" % total)
        for p in problems:
            print(p)
        return False
    print("SELF TEST: %d cases, all pass." % total)
    print("           The script can tell a stated phrase from a denied one, so a clean")
    print("           result below means the data is clean rather than the check inert.")
    return True


def main():
    if not self_test():
        print("\nNot examining the data. A broken check reporting nothing would look")
        print("exactly like clean data.")
        return 2
    print()

    rules = load_rules(RULES_FILE)
    print("=" * 92)
    print("DECISIVE DISTINCTION CHECK")
    print("=" * 92)
    print("Reading %d distinctions from %s" % (len(rules), os.path.basename(RULES_FILE)))
    for r in rules:
        if r["kind"] in PATTERN_KINDS:
            print("   %-24s [%s] %s, compares the two descriptions against each other"
                  % (r["name"], r["action"], r["kind"]))
        else:
            print("   %-24s [%s] %s  against  %s"
                  % (r["name"], r["action"], " / ".join(r["one"]), " / ".join(r["other"])))
    print()

    reported = 0
    disqualifying = 0
    examined = 0
    for flow in ("imports", "exports"):
        # Written by a later stage into this project's own output directory. This used to read
        # HERE/inspire2/output, which resolved to inspire2_v2/checks/inspire2/output and has
        # never existed, so the check examined nothing and still reported a clean result.
        path = os.path.join(PROJECT, "output", "%s_lineage_timeline.csv" % flow)
        if not os.path.exists(path):
            print("  %s: no history file found at %s" % (flow, path))
            continue
        steps, desc_col = load_steps(path)
        if not desc_col:
            print("  %s: history file has no description column" % flow)
            continue
        examined += 1

        print("-" * 92)
        print("%s: %d steps" % (flow.upper(), len(steps)))
        print("-" * 92)
        for rule in rules:
            hits = []
            for uid, before, after in steps:
                tb = expand_shorthand(before[desc_col] or "").lower()
                ta = expand_shorthand(after[desc_col] or "").lower()
                if rule_fires(rule, tb, ta):
                    hits.append((uid, before, after, rule["kind"], rule["action"]))

            share = (len(hits) / len(steps)) if steps else 0
            warn = ""
            if share > TOO_COMMON_SHARE:
                warn = ("   <-- fires on %.0f%% of steps, too often for a decisive "
                        "distinction. Check the phrases." % (100 * share))
            print("  %-24s %3d step(s)  [%s]%s"
                  % (rule["name"], len(hits), rule["action"], warn))
            reported += len(hits)
            if str(rule["action"]).strip() == "disqualify":
                disqualifying += len(hits)
            for uid, before, after, _kind, _action in hits[:5]:
                print("      %s   %s becomes %s" % (uid, before.get("hs_code"), after.get("hs_code")))
                print("         was: %s" % expand_shorthand(before[desc_col])[:76])
                print("         now: %s" % expand_shorthand(after[desc_col])[:76])
                if rule["exceptions"]:
                    print("         note: a known exception is recorded for this distinction:")
                    print("               %s" % rule["exceptions"][:76])
            if len(hits) > 5:
                print("      ... %d more" % (len(hits) - 5))
        print()

    print("=" * 92)
    if examined == 0:
        # The whole point of the self test is that a clean result must mean the data is clean.
        # Saying "no step crosses a distinction" after reading no steps would break that promise
        # in the other direction: the rules would be sound, the check would be sound, and the
        # answer would still be worthless. Stages 1 to 6 write these files, and none is built.
        print("NOTHING WAS EXAMINED. No history file exists yet, so this result is not a")
        print("clean bill of health. It says only that the check ran. A history file appears")
        print("once a stage writes a lineage timeline into output/.")
        print("=" * 92)
        return 3
    if reported == 0:
        print("No step crosses a decisive distinction, across %d flow(s) examined." % examined)
    else:
        print("%d step(s) reported, %d of them by a DISQUALIFYING rule." % (reported, disqualifying))
        print()
        print("A review rule may not decide anything, here or anywhere. It was measured against")
        print("Canada's own concordance and fires on 5 of 125 known-correct successions, which is")
        print("why families.py reads only the disqualifying rules and why the ranker flags rather")
        print("than removes on them. A check that failed the build on a review flag would be")
        print("letting a review rule decide, which is the one thing the project has settled that")
        print("it may not do. So they are printed, counted, and not fatal.")
        print()
        print("Each is a prompt to look. A tariff revision can legitimately merge two codes into")
        print("one, in which case the step is correct and the reason belongs in the")
        print("known_exceptions column of the rules file.")
    print("=" * 92)
    # EXIT 3 STILL MEANS "EXAMINED NOTHING", and that branch is above. Exit 1 now means a
    # distinction the project has declared DISQUALIFYING was crossed by a published step, which
    # is a real defect in the crosswalk. Review flags leave the exit code at 0 and are disclosed.
    return 1 if disqualifying else 0


if __name__ == "__main__":
    sys.exit(main())
