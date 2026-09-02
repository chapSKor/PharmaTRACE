"""
The meaning gates. Do two descriptions fall on opposite sides of a distinction the tariff
treats as decisive?


This is the production implementation, used by Stage 1c to VETO a candidate successor. It never
proposes one. A gate can remove a candidate from a field; it can never add one, and it can never
rank what remains.

It was extracted from checks/check_decisive_distinctions.py on 2026-08-10, unchanged, when
Stage 1c needed it. The check now imports it and tests it against 56 wordings whose right answer
is known and was written independently of this code. That satisfies the rule against testing code
with the code under test: the expectations are independent even though the implementation is
shared.

Read decisions/decisive_distinctions.csv for the thirteen contrasts and two relationship rules,
and manuscript/SI_meaning_checks.md for the plain-language account, including the two faults that
left four rules silently inert until 2026-08-10.

The word boundary below is the load-bearing part. A bare substring search reads "unmixed" as
stating "mixed" and "pseudoephedrine" as stating "ephedrine", and a hyphen defeats a boundary
defined on alphanumerics, which is why "non" is a reversing word rather than a spelling case.
"""

import csv
import re

# and read as stating it. The sterility rule, one of the original seven, was therefore inert
# from the day it was written until this line was added. Widening the boundary to swallow the
# hyphen was the wrong fix: it would also reject "sterile-packed", which does state sterile.
REVERSING_WORDS = ["not", "non", "other than", "except", "excluding", "without", "o/t"]

# A rule that fires on a large share of steps is not a decisive distinction, it is a
# common word. Anything above this share is flagged as probably set up wrongly.
TOO_COMMON_SHARE = 0.10
# THIS GUARD BELONGS TO THE AUDIT, NOT TO THE FILTER. Settled 2026-08-10 after the rules were
# run against real descriptions for the first time.
#
# The same rules serve two different jobs, and the same firing rate means opposite things in
# each.
#
#   As an AUDIT, over the steps of a finished lineage, the question is "did the crosswalk join
#   two products across a decisive distinction?" A correct crosswalk answers almost never, so a
#   rule firing on more than a tenth of steps is far more likely to be a common word than a
#   distinction. The guard is right here, and it stays here.
#
#   As a FILTER, over the candidate pairs a retirement starts with, the question is "which of
#   these candidates is impossible?" A useful gate removes a fair share of them. Measured on the
#   delivery, the human against veterinary contrast fires on 387 of 3,488 import candidate
#   pairs, 11.1 per cent, which is roughly one impossible candidate in a field of twelve. That
#   is the gate working, not failing.
#
# Applying the guard to the filter would flag the single most useful gate in the list as broken.
# Stage 1c must not apply it. Nothing below reads it; both meanings are recorded here so the
# next reader does not have to rediscover the difference.


def split_into_clauses(text):
    """Split a description at commas and semicolons. A reversing word does not reach
    past punctuation, so "Vaccines, human use, not sterile" does not negate "human"."""
    return [c for c in re.split(r"[,;]", text) if c.strip()]


def phrase_pattern(phrase):
    """A phrase must match on word boundaries, not as a bare substring.

    Written 2026-08-10, when the list grew from seven distinctions to thirteen. Two of the
    six new ones are unusable without it, because a substring search reads the denial as
    the assertion:

        "unmixed"         contains "mixed"
        "pseudoephedrine" contains "ephedrine"

    Both would have been reported as stating the very thing they deny. The boundary is
    written as a lookaround on alphanumerics rather than \\b so it also holds for phrases
    carrying punctuation, such as "o/t" and "n.e.s.", where \\b sits in the wrong place.
    """
    return re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(phrase))


def is_stated(text, phrase):
    """True when the description says the phrase, rather than denying it.

    Every occurrence is examined. If any one of them has no reversing word before it in
    its own clause, the phrase counts as stated.
    """
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    pattern = phrase_pattern(phrase)
    for clause in split_into_clauses(text.lower()):
        for match in pattern.finditer(clause):
            before = clause[:match.start()]
            # Only text BEFORE the phrase can reverse it. This is what allows
            # "not for retail sale" to state itself: its own "not" is inside the
            # phrase, not before it.
            reversed_here = any(re.search(r"\b%s\b" % re.escape(w), before)
                                for w in REVERSING_WORDS)
            if not reversed_here:
                return True
    return False


def which_side(text, one_side, other_side):
    """Return 'one side', 'other side', 'both' or 'not mentioned'."""
    a = any(is_stated(text, p) for p in one_side)
    b = any(is_stated(text, p) for p in other_side)
    if a and b:
        return "both"
    if a:
        return "one side"
    if b:
        return "other side"
    return "not mentioned"


# Two contrasts in the 1988-2026 descriptions cannot be written as a pair of phrase lists,
# because what fires them is a relationship between the two descriptions rather than a word
# in either one. They are carried as rule kinds instead.
#
# The `action` column says what Stage 1 should DO with a hit. This check still only reports;
# it prints the action so the intent is visible, and applies nothing.
KIND_PHRASE_PAIR = "phrase_pair"
KIND_SPECIFIC_VS_RESIDUAL = "specific_vs_residual"
KIND_BASKET_SUBSET = "basket_subset"
KIND_SWAPPED_TERM = "swapped_term"
PATTERN_KINDS = (KIND_SPECIFIC_VS_RESIDUAL, KIND_BASKET_SUBSET, KIND_SWAPPED_TERM)

# How much of two descriptions must coincide before the remainder counts as "one term swapped",
# and how many words that remainder may hold. Both measured against the corpus rather than
# chosen: below three shared words there is no common frame, and above four unique words the
# descriptions are being restyled rather than having a term substituted.
SWAP_FRAME_WORDS = 3
SWAP_UNIQUE_WORDS = 4

# Residual markers come in two kinds that mean opposite things, and treating them alike is
# what made this rule remove correct successors.
#
# EXCLUSIONARY says "everything but the named thing". "Vaccines o/t against influenza" and
# "Vaccines against influenza" name mutually exclusive sets, so neither can succeed the other.
#
# CATCH-ALL says "the named thing, where no finer line applies". "Anti-infective agents, in
# dosage, nes" is the bucket that RECEIVES anti-infective agents when a specific line closes.
# It is the destination, not the complement, and it is the ordinary shape of an HS renumbering.
#
# Measured 2026-08-11: all 9 firings of specific_vs_residual were catch-all, none exclusionary,
# every one at wording 0.90 or better, and every one removed the best-matching candidate. Not a
# single exclusionary pair exists among the 3,699 candidate pairs in this delivery, so the rule
# had never once met the case it was written for.
EXCLUSIONARY_MARKERS = ["o/t", "other than", "excluding", "except"]
CATCHALL_MARKERS = ["not elsewhere specified", "nes", "n.e.s."]

# "OTHER THAN HEADING 30.02" IS NOT AN EXCLUSION OF GOODS. It says which heading a line sits
# under, and every Chapter 30 residual has carried it since the 2017-2018 revision:
# "Mixtures amino acids,nes,in doses/packings for retail sale,o/t No 30.02/05". That line is a
# leftover with a scope note, and is_a_catch_all read the scope note as the exclusion and
# answered no on the strength of it -- on a line that says "nes" in its own wording.
#
# The two kinds separate cleanly in this delivery and were counted rather than assumed: 94 lives
# carry o/t, and on 81 it introduces a heading NUMBER while on 13 it excludes goods, as in
# "Vaccines, o/t for against influenza virus" and "Dressings/sim art of woven fab o/t of cotton".
# Only the second kind can make a line the complement of what it names.
#
# 27 lives carrying CAD 134,080,082,251 were denied on this ground, 18 of them beginning 2017-01
# or later, which is why the modern leftover lines were invisible to every rule that asks whether
# a candidate is a residual.
#
# THE 94 / 81 / 13 SPLIT IS NOW PINNED and the three figures in the paragraph above are not.
# Finding 138, 2026-08-18. The split is a fact about this delivery and is asserted in
# check_rule_application.py, because if it moves this expression has started answering a
# different question and every leftover-line rule changes subject with it. The 27, the
# CAD 134,080,082,251 and the 18 describe behaviour the code no longer has; they are the
# reason the fix exists rather than a claim about it, and they cannot be recomputed from the
# current code. They are left as history and deliberately not asserted.
HEADING_SCOPE = re.compile(r"(?<![a-z0-9])o/t\s*(?:no\.?|heading)?\s*\d[\d./]*", re.I)


def strip_heading_scope(text):
    """Remove `o/t No 30.02/05/06` and its spellings, leaving any goods-level exclusion in place."""
    return HEADING_SCOPE.sub(" ", text or "")

# Both kinds are stripped before two descriptions are compared as goods, because neither marker
# is part of what the goods ARE. Only the exclusionary kind decides complementarity.
RESIDUAL_MARKERS = EXCLUSIONARY_MARKERS + CATCHALL_MARKERS

# Words carrying no distinguishing weight when two descriptions are compared as word sets.
FILLER_WORDS = {"for", "of", "the", "and", "or", "in", "to", "a", "an", "with", "on"}


def strip_residual_markers(text):
    out = text.lower()
    for marker in RESIDUAL_MARKERS:
        out = phrase_pattern(marker).sub(" ", out)
    return out


def carries_residual_marker(text):
    return strip_residual_markers(text) != text.lower()


def carries_exclusionary_marker(text):
    """Only 'other than' and its kin make a description the complement of another."""
    out = text.lower()
    for marker in EXCLUSIONARY_MARKERS:
        out = phrase_pattern(marker).sub(" ", out)
    return out != text.lower()


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in FILLER_WORDS}


def specific_vs_residual(before_text, after_text):
    """One description is the explicit complement of the other, so they cannot be the same goods.

    Exactly one side carries a residual marker, and once that marker is removed the two name
    the same goods word for word. "Vaccines against influenza virus" against "Vaccines o/t
    against influenza virus" score 0.922 as text while describing mutually exclusive sets.

    Both sides carrying a marker is NOT a hit: two residual baskets are not complements.

    Only an EXCLUSIONARY marker counts. A catch-all "nes" is where the goods go when a specific
    line closes, so "X" against "X, nes" is a succession and not a complement. Reading it as one
    removed the correct successor on 5 retirements worth CAD 118,352,487, including two the
    analyst found by reading the queue.
    """
    if carries_exclusionary_marker(before_text) == carries_exclusionary_marker(after_text):
        return False
    a = content_words(strip_residual_markers(before_text))
    b = content_words(strip_residual_markers(after_text))
    return bool(a) and a == b


def list_items(text):
    """The set of items a list-shaped description names, each as its own word set."""
    items = set()
    for chunk in re.split(r"[,;]", text):
        words = content_words(chunk)
        if words:
            items.add(frozenset(words))
    return items


def basket_subset(before_text, after_text):
    """Both descriptions are lists and one item set is a proper subset of the other.

    "Toxins, toxoids, antitoxins" against "Toxoids, antitoxins". Losing an item from a list
    does not make the lineage wrong, so the action is review rather than disqualify. This is
    the rule that workbook row 16 exists for.
    """
    a, b = list_items(before_text), list_items(after_text)
    if len(a) < 2 or len(b) < 2 or a == b:
        return False
    return a < b or b < a


def load_rules(path):
    rules = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("status") or "").strip().lower() != "active":
                continue
            rules.append({
                "name": row["distinction"].strip(),
                # Rules written before the kind column existed are phrase pairs.
                "kind": (row.get("kind") or KIND_PHRASE_PAIR).strip() or KIND_PHRASE_PAIR,
                "action": (row.get("action") or "disqualify").strip() or "disqualify",
                "one": [p.strip() for p in (row.get("one_side") or "").split(";") if p.strip()],
                "other": [p.strip() for p in (row.get("other_side") or "").split(";") if p.strip()],
                "exceptions": (row.get("known_exceptions") or "").strip(),
            })
    return rules


def singular(word):
    """A crude plural strip, enough to stop "use" and "uses" reading as different goods.

    Applied only inside swapped_term. It fired on "use" against "uses" and on "formltd hormone"
    against "formulated hormones", reporting a substitution where the corpus had simply written
    the same word twice over. Deliberately shallow: no stemmer, no word list, just a trailing s
    on a word long enough that dropping it cannot create a different word in this vocabulary.
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def is_a_catch_all(text):
    """True when a description is the leftover line for its class, and not an exclusion.

    "Penicillins or their derivatives nes" is where a penicillin goes once its own line closes.
    "Vaccines o/t against influenza" is the opposite: everything EXCEPT the named goods. Both
    carry a residual marker and only the first can receive what the other names, so the two must
    not be treated alike.
    """
    lowered = (text or "").lower()
    catch_all = any(phrase_pattern(m).search(lowered) for m in CATCHALL_MARKERS)
    exclusion = any(phrase_pattern(m).search(strip_heading_scope(lowered))
                    for m in EXCLUSIONARY_MARKERS)
    return catch_all and not exclusion


def swapped_term(before_text, after_text):
    """Same frame, one distinguishing term substituted. FLAGS ONLY. NEVER REMOVES.

    difflib scores on characters, so two descriptions built from the same boilerplate score high
    even when the single word carrying the meaning is different. Measured on this delivery:
    "Waste pharmaceuticals of the goods of heading 30.03" against "...heading 30.01" scores
    0.9804; "Lincomycin, for human use, in dosage" against "Vancomycin, ..." scores 0.9412;
    "Anti-infective agents, for human use, in dosage" against "Antineoplastic agents, ..."
    scores 0.8667, high enough to be labelled a strong match. In each pair the score is measuring
    the scaffolding and not the goods.

    THE ACTION IS REVIEW, AND THAT IS NOT TIMIDITY. Tested against Canada's own concordance this
    shape fires on 5 of 125 known-correct successions, and four of those are ordinary restylings:
    "Anaesthetic, for veterinary use, in dosage" really does become "Other medicaments, for
    veterinary use, in dosage, nes". A rule that removes candidates at a 4 percent error rate
    against the official record would repeat exactly the mistake specific_vs_residual made. So
    this one flags the row, withholds the recommendation, and leaves the judgement to a person.
    """
    # A CATCH-ALL IS NOT A SUBSTITUTED TERM. This rule asks whether two specific descriptions
    # name different things. A leftover line is not a specific thing: it necessarily describes a
    # broader class in different words, which reads as a substitution and is an absorption.
    # "Amoxycillin" against "Penicillins or their derivs nes" fired here, and an amoxycillin is a
    # penicillin. Measured against Canada's concordance the exemption takes this rule's false
    # positives from 6 of 125 to 4, and it changes no proposal: only which alternatives can be
    # offered beside one.
    if is_a_catch_all(after_text):
        return False
    before = {singular(w) for w in content_words(strip_residual_markers(before_text))}
    after = {singular(w) for w in content_words(strip_residual_markers(after_text))}
    shared, only_before, only_after = before & after, before - after, after - before
    if len(shared) < SWAP_FRAME_WORDS:
        return False
    if not only_before or not only_after:
        return False
    return len(only_before) + len(only_after) <= SWAP_UNIQUE_WORDS


def swapped_terms_named(before_text, after_text):
    """The differing words, for the artefact to print. Empty when the rule does not fire."""
    if not swapped_term(before_text, after_text):
        return "", ""
    before = {singular(w) for w in content_words(strip_residual_markers(before_text))}
    after = {singular(w) for w in content_words(strip_residual_markers(after_text))}
    return " ".join(sorted(before - after)), " ".join(sorted(after - before))


def rule_fires(rule, before_text, after_text):
    """True when this rule says the two descriptions are not the same goods."""
    if rule["kind"] == KIND_SPECIFIC_VS_RESIDUAL:
        return specific_vs_residual(before_text, after_text)
    if rule["kind"] == KIND_BASKET_SUBSET:
        return basket_subset(before_text, after_text)
    if rule["kind"] == KIND_SWAPPED_TERM:
        return swapped_term(before_text, after_text)
    sides = {which_side(before_text, rule["one"], rule["other"]),
             which_side(after_text, rule["one"], rule["other"])}
    return sides == {"one side", "other side"}

