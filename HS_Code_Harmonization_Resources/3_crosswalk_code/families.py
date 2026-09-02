"""
What kind of medicine each commodity is, and where that knowledge came from.


Reads:  decisions/medicine_families.csv


WHY THIS EXISTS
---------------
Every defect found while adjudicating traced to one cause: the pipeline compares descriptions as
text, and pharmaceutical classification is about what a substance IS. Quinidine sulphate was
offered Vincristine's successor because both read "X, for human use, in dosage" and only the
first word differs, which is the word that matters. Polymyxins was offered Vancomycin. Kanamycins
was offered Gentamycins.

This supplies the missing fact, and it records where each fact came from, because two thirds of
it cannot be checked against anything in this project.


TWO DIFFERENT QUESTIONS
-----------------------
**family_name** answers "where does the trade go". It is the leftover line that covers a
substance, and for 109 of the 178 entries it is DERIVED from the tariff's own block structure: a
code at .X1 to .X8 sits with the leftover line at .X9, so Kanamycins and Gentamycins are both
aminoglycosides because "Aminoglycoside antibiotics, nes" is the .49 of their block. That is
evidence, and a reader can check it against the schedule.

**therapeutic_class** answers "are these interchangeable". Quinidine and Vincristine share a
family_name, because the Harmonized System groups vegetable alkaloids by whether they are
narcotic and not by what they treat. They are an antiarrhythmic and a chemotherapy agent. No
part of this delivery records that, so it is ASSERTED.


THE THREE CONSTRAINTS THIS OBEYS
--------------------------------
1. **It may only withhold a recommendation. It may never create a link.** Nothing here changes
   proposed_successor. A wrong entry therefore costs one withheld row, which the person
   adjudicating will see and can dismiss. It cannot put a false link into a published crosswalk.

2. **Every entry carries its source.** "derived from the tariff block" or "asserted, unsourced",
   with a confidence and a reason. The manuscript can state exactly how much of the crosswalk
   rests on evidence and how much on assertion, and the asserted half can be reviewed by someone
   qualified to review it.

3. **It covers what the queue needs and no more.** 178 entries rather than all 572 commodity
   strings, and 178 rather than 177 because a code with two lives now needs an entry per life.
   A document nobody reviews is worse than a shorter one that is read.


WHAT IT WILL NOT SAY, AND THAT IS DELIBERATE
--------------------------------------------
80 of the 178 entries name no leftover line. 69 are asserted class-only entries that never had
one. The other 11 lost theirs on 2026-08-16, because each named a line that had already closed
before the code began trading and no leftover in that code's own block could have received it.
A line that died in 2011 cannot take trade from a code that opened in 2018.

Naming nothing there is the point rather than a gap. An absent entry reads as "unknown", and a
withheld recommendation costs one row a person will see. A named line that never existed reads as
knowledge and cannot be told apart from the real thing.

WHAT IT DOES NOT DO
-------------------
It has no authority. It is not the ATC classification, not the WHO INN list, not a
pharmacopoeia; none of those was reachable offline. Where it says "asserted, unsourced" the only
warrant is that someone wrote it down and someone else can check it.
"""

import csv
import os
import re

import meaning_gates as _gates

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(PROJECT, "decisions", "medicine_families.csv")

OWN_LINE = "its own leftover line"
CATCH_ALL = "a catch-all line that may cover it"
SAME_COMMODITY = "the same commodity under a new number"
DERIVED = "derived from the tariff block"
ASSERTED = "asserted, unsourced"


def load_families(path=TABLE):
    """Every entry, keyed on flow, code AND the life it describes.

    KEYED ON THE LIFE, AND IT WAS KEYED ON THE NUMBER UNTIL 2026-08-16. Statistics Canada recycles
    a retired number for unrelated goods, so a number can carry two lives and one entry could only
    describe one of them. The other life got that entry anyway. `EX-30049010` is the plainest case:
    the same number is "Medicaments nes, in dosage, for human use", which ended in 1988-12, and
    cannabis preparations, which began in 2018-02, and the 1988 line was shown the cannabis
    family. 31 of 177 entries sat on numbers with more than one life, and 11 of the 100 queue rows
    the table annotates were shown a family recorded about a different life, CAD 13,104,985,488.
    A further 4 rows were shown the wrong life of the SUCCESSOR, CAD 846,785,773.

    This is the same failure class as findings 102, 105, 106 and 113, in the one input the
    manuscript describes as reviewable by a qualified reader.
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return {(r["flow"], r["hs_code"], r["first_period"]): r for r in csv.DictReader(handle)}


def entry_at(table, flow, code, month=""):
    """The entry for the life of `code` that was open in `month`.

    With no month, answers only where the code has exactly ONE life in the table. That default is
    deliberate: a caller that does not say which era it means cannot be given one of several, and
    an absent entry reads as "unknown", which is the safe direction. Guessing would put a fact
    about one commodity against a different commodity that reused its number.
    """
    bare = (code or "").replace(".", "")
    mine = [r for (f, c, _first), r in table.items() if f == flow and c == bare]
    if not mine:
        return None
    if len(mine) == 1 and not month:
        return mine[0]
    if not month:
        return None
    mine.sort(key=lambda r: r["first_period"])
    inside = [r for r in mine
              if r["first_period"] <= month <= (r["last_period"] or r["first_period"])]
    if inside:
        return inside[0]
    earlier = [r for r in mine if r["first_period"] <= month]
    return earlier[-1] if earlier else None


def entry_receiving(table, flow, code, stopped=""):
    """The entry for the life of `code` that could RECEIVE a retirement stopping in `stopped`.

    The mirror of make_adjudication_queue.description_shown and stage1c_rank.wording_at, and the
    same rule they use: the earliest life still open after the trade stopped, falling back to the
    last one. A candidate is judged on the era it would actually receive the goods in, never on
    the era it happened to end in.
    """
    bare = (code or "").replace(".", "")
    mine = sorted([r for (f, c, _first), r in table.items() if f == flow and c == bare],
                  key=lambda r: r["first_period"])
    if not mine:
        return None
    if len(mine) == 1 and not stopped:
        return mine[0]
    if not stopped:
        return None
    alive = [r for r in mine if (r["last_period"] or r["first_period"]) > stopped]
    return alive[0] if alive else mine[-1]


def family_of(table, flow, code, month=""):
    return (entry_at(table, flow, code, month) or {}).get("family_name", "")


def therapeutic_class_of(table, flow, code, month=""):
    return (entry_at(table, flow, code, month) or {}).get("therapeutic_class", "")


def leads_to_own_line(table, flow, retiring, candidate, candidate_text="",
                      retiring_text="", month=""):
    """Is the candidate the very leftover line that this code's trade falls into?

    The leftover line is recorded as a POINTER on each member entry and 37 of the 41 lines have
    no entry of their own, so asking family_of() about one returns nothing. That made the
    strongest relationship the table can express report as "unknown": the reader was pointed at
    a code with the note that nothing was known about it, when what was known was the most
    useful fact available.

    Matched on the code OR on the description. The code alone is not enough: the leftover line
    keeps its wording across HS revisions but not its number, so Betamethasone's recorded family
    code missed the same line carrying a later revision's number. The wording is the
    revision-tolerant form of the same question, and both live here rather than in two places
    that can drift apart.

    THE TARIFF NESTS ITS LEFTOVERS, AND ONE COLUMN CANNOT HOLD TWO LEVELS. Codeine phosphate
    sits in a block whose leftover is "Codeine or its derivs nes", and that line has its own
    leftover one level out, "Narcotic veg alkaloids nes". When the inner line retires too the
    trade goes to the outer one, and the analyst reported the sheet denying that the outer line
    was this code's family line at all. enclosing_family_name records the second level, with its
    own source, and either level answers this question.

    Names are compared on their content words rather than as whole strings. The column was being
    used for two different kinds of value: the leftover line's own wording, which is what a
    candidate description can be matched against, and asserted prose group names such as
    "Narcotic vegetable alkaloids", which no description is ever spelled that way. Morphine and
    Cocaine carry the prose form and Codeine the derived line, three entries in one block written
    three ways, so an exact match answered no for all of them.
    A DISTINCTION THAT DISQUALIFIES A SUCCESSOR ALSO DISQUALIFIES A FAMILY. Epinephrine, whose
    description ends "prepr for parentl admin in hum", was told its own leftover line was
    "Hormones, nes, for vet use", because its recorded family is the single word "Hormones" and
    one word is contained in almost any hormone line. The use distinction has been declared
    decisive and active since 2026-08-05 and this layer had never consulted it. The rules are
    read from decisive_distinctions.csv rather than restated here, so there is one statement of
    what separates two commodities and not two that can drift.

    This does NOT contradict the finding that Canada's concordance contains human-to-veterinary
    successions. Those are one-to-many splits, where a vet line receives the vet share. "This
    candidate may receive some of the trade" and "this candidate IS this code's leftover line"
    are different claims, and only the second is made here.
    """
    entry = entry_at(table, flow, retiring, month)
    if not entry:
        return False
    if retiring_text and candidate_text and _crosses_a_decisive_line(retiring_text,
                                                                    candidate_text):
        return False
    if entry.get("family_code") and entry["family_code"] == (candidate or "").replace(".", ""):
        return True
    # A LEFTOVER LINE IS A RESIDUAL BY DEFINITION, so a candidate that is not one cannot be it.
    # Without this, a recorded family of "Medicaments nes, for human use" reduces to two common
    # words and matched "Medicaments affecting electrolytic, caloric/water balance", a specific
    # named line, on three rows. Matching on wording alone is only safe once the candidate is
    # known to be the sort of line that receives trade rather than names goods. A recorded
    # NUMBER needs no such guard, which is why it is tested above and not here.
    if not _gates.is_a_catch_all(candidate_text or ""):
        return False
    for field in ("family_name", "enclosing_family_name"):
        if _names_the_same_line(entry.get(field), candidate_text):
            return True
    return False


SHORTHAND = {"veg": "vegetable", "derivs": "derivatives", "deriv": "derivatives",
             "narc": "narcotic", "horm": "hormones", "medi": "medicaments",
             "cont": "containing", "hum": "human", "vet": "veterinary"}
NOISE = {"nes", "or", "of", "in", "for", "their", "its", "the", "and", "use", "dosage",
         "n.e.s.", "not", "elsewhere", "specified", "o/t", "other", "than"}


def _content_words(text):
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {SHORTHAND.get(w, w) for w in words} - NOISE


def _names_the_same_line(name, candidate_text):
    """Do these two name the same leftover line, allowing for shorthand and a longer wording."""
    mine, theirs = _content_words(name), _content_words(candidate_text)
    if not mine or not theirs:
        return False
    # Containment, not equality. The recorded name is often the short form of a catalogue
    # description that adds the use and the presentation, and the asserted prose names are
    # shorter still. Requiring every recorded word to appear keeps this from matching a
    # sibling line, which is what would turn a withheld row into a wrong recommendation.
    return mine <= theirs


def basis_of(table, flow, retiring, candidate, candidate_text="", month=""):
    """Which fact the relationship rests on: the asserted class, or the derived family.

    The provenance must follow the fact that was USED. Reading it off the entry's overall source
    labelled Tranquilizers against Anaesthetic as coming from the tariff structure, when the
    family was derived and the therapeutic class that actually separated them was asserted. A
    provenance that reports the wrong origin is worse than none, because the whole point of
    recording it is to let a reader discount what rests on nothing.
    """
    if leads_to_own_line(table, flow, retiring, candidate, candidate_text, month=month):
        return "family"
    # The retiring code is read in the life that STOPS; the candidate in the life that could
    # RECEIVE it. Two different questions about two different codes, and reading either in the
    # other's era is the defect this whole layer was re-keyed to stop.
    ca, cb = (therapeutic_class_of(table, flow, retiring, month),
              class_receiving(table, flow, candidate, month))
    if ca and cb:
        return "class"
    if family_of(table, flow, retiring, month) and family_receiving(table, flow, candidate, month):
        return "family"
    return ""


def family_receiving(table, flow, code, stopped=""):
    return (entry_receiving(table, flow, code, stopped) or {}).get("family_name", "")


def class_receiving(table, flow, code, stopped=""):
    return (entry_receiving(table, flow, code, stopped) or {}).get("therapeutic_class", "")


def relationship(table, flow, retiring, candidate, candidate_text="", retiring_text="", month=""):
    """How two commodities relate, and how confidently.

    Returns one of:
      "the same commodity under a new number"  the two descriptions are identical
      "its own leftover line"  the candidate IS the line this code's trade falls into
      "same family"        their trade lands in the same leftover line
      "different family"   it does not
      "same class"         the same kind of medicine, asserted
      "different class"    a different kind of medicine, asserted
      "a catch-all line that may cover it"  the candidate is a residual, so it is a
                           container rather than a different kind of medicine
      "unknown"            nothing is recorded for one of them

    Deliberately returns unknown rather than guessing. An absent entry is an absence of
    knowledge, and reporting it as sameness would be the one failure this file cannot afford.
    """
    # IDENTICAL WORDING OUTRANKS EVERYTHING THIS TABLE KNOWS. The same description on two codes
    # is the same commodity under a new number, and the tariff moving it to a block with a
    # different leftover line does not make it a different kind of medicine. Ten rows read
    # "different family" while their two descriptions matched character for character.
    if retiring_text and candidate_text and \
            retiring_text.strip().lower() == candidate_text.strip().lower():
        return SAME_COMMODITY
    if leads_to_own_line(table, flow, retiring, candidate, candidate_text, retiring_text, month):
        return OWN_LINE
    # A CATCH-ALL IS A CONTAINER, NOT A KIND OF MEDICINE, so the table cannot say the two are
    # different. Saxitoxin against the blood-and-toxins residual read as a different kind of
    # medicine and the row was advised to reject it. swapped_term already stands down when the
    # target is a catch-all; this is the same rule reaching the same conclusion here, rather
    # than a new one placed against it.
    if candidate_text and _gates.is_a_catch_all(candidate_text) \
            and not _gates.is_a_catch_all(retiring_text):
        return CATCH_ALL
    a, b = (family_of(table, flow, retiring, month),
            family_receiving(table, flow, candidate, month))
    ca, cb = (therapeutic_class_of(table, flow, retiring, month),
              class_receiving(table, flow, candidate, month))
    # Compared on their words, not as raw strings. One entry carried a trailing comma and the
    # two names were otherwise character-identical, which reported Vitamins-iron preparation as
    # a different family from Vitamins-iron preparation. Punctuation must not decide a
    # classification.
    if ca and cb:
        return "same class" if _same_name(ca, cb) else "different class"
    if a and b:
        return "same family" if _same_name(a, b) else "different family"
    return "unknown"


def _same_name(one, other):
    return _content_words(one) == _content_words(other)


_RULES = None


def _crosses_a_decisive_line(before_text, after_text):
    """Does an active, disqualifying distinction separate these two descriptions?

    Read from decisions/decisive_distinctions.csv, so the answer is whatever the project has
    already declared rather than a second opinion written here. Rules whose action is review are
    ignored: they flag a row for a person and were measured against Canada's concordance as too
    noisy to remove anything.
    """
    global _RULES
    if _RULES is None:
        path = os.path.join(PROJECT, "decisions", "decisive_distinctions.csv")
        rules = _gates.load_rules(path) if os.path.exists(path) else []
        # load_rules has already dropped anything not active, and does not carry the status
        # column through, so filtering on it here emptied the list silently.
        _RULES = [r for r in rules if str(r.get("action", "")).strip() == "disqualify"]
    return any(_gates.rule_fires(rule, before_text, after_text) for rule in _RULES)


def source_of(table, flow, code, month=""):
    return (entry_at(table, flow, code, month) or {}).get("source", "")
