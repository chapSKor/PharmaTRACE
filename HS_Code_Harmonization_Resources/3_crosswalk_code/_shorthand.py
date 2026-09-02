"""
Canadian Customs description shorthand → full-word expander.


Statistics Canada uses heavy abbreviation in chapter-30 sub-code
descriptions. This module exposes one function, expand_shorthand(s),
that rewrites those abbreviations into their full forms so the
description columns in the lookup / lineage / journey CSVs read in
plain English.

The list below mirrors the table in HS_Crosswalk_3Stage_Methodology.md
and is expanded with abbreviations we've observed in the actual
chapter-30 data. All matches are word-bounded so substrings inside
other words don't get clobbered (e.g. "or" is not matched by the
single-letter rule \\bo\\b → "other").

Another abbreviation, once spotted, belongs in the ABBREV map below; keep
multi-character rules ahead of single-letter rules so the longer
patterns match first.
"""
from __future__ import annotations

import re


# Order matters: multi-character / structural rules first, single-letter
# rules last. Patterns are case-insensitive but the replacement preserves
# the case of the first letter when it was originally capitalised.

# Special structural rules (regex pattern, replacement template).
# Run before the simple word-boundary rules.
_STRUCTURAL_RULES: list[tuple[re.Pattern, str]] = [
    # "o/t No 30.02/05/06"  ->  "other than products of headings 30.02, 30.05, 30.06"
    (re.compile(r"\bo/t\s+No\s+(\d+)\.(\d+)/(\d+)/(\d+)\b", re.IGNORECASE),
     r"other than products of headings \1.\2, \1.\3, \1.\4"),
    # Numeric heading shorthand without preceding "o/t No": pass through.
]

# Word-bounded simple replacements. The dictionary is iterated in order;
# CPython 3.7+ preserves dict insertion order. Place compound or
# disambiguating rules above looser ones.
_ABBREV: dict[str, str] = {
    # Added 2026-08-12. swapped_term reported "formltd hormone" against "formulated hormones" as
    # a substituted term when the corpus had simply written one word two ways.
    "formltd": "formulated",
    "formltn": "formulation",
    # Added 2026-08-13. The origin gate is a phrase pair on "human origin" against "animal
    # origin", and two import codes write the first as "human orig": 3002.10.00.29 and
    # 3002.10.10.29. The gate could not see its own case on them. The natural experiment is on one
    # commodity pair: 3002.10.10.10 "human origin" against 3002.10.00.42 is vetoed origin, while
    # 3002.10.10.29 "human orig" against that same code was not vetoed at all. Measured effect of
    # this line: 4 candidate pairs newly vetoed and 6 ranked rows touched, all on imports, no
    # proposal moved, and 0 contradictions against Canada's 2011-2012 and 2016-2017 concordances.
    # Three other unvetoed origin pairs stay unvetoed and should: their wording is "except of
    # human or animal origin", a negation rather than a claim to either side.
    "orig": "origin",
    # Multi-char compound shorthand
    r"o/t":       "other than",
    r"w/n":       "whether or not",
    r"t/o":       "thereof",
    r"o/w":       "otherwise",
    r"b/m":       "by means",

    # Two-to-four-letter abbreviations of common pharma / customs terms.
    r"nes":       "not elsewhere specified",
    r"nfrs":      "not for retail sale",
    r"frs":       "for retail sale",
    r"nfr":       "not for retail",
    r"Medi":      "Medicaments",
    r"Med":       "Medicaments",
    r"medi":      "medicaments",
    r"cont":      "containing",
    r"mix":       "mixed",
    r"therap":    "therapeutic",
    r"prophltc":  "prophylactic",
    r"prophtc":   "prophylactic",
    r"deriv":     "derivative",
    r"derivs":    "derivatives",
    r"hum":       "human",
    r"vet":       "veterinary",
    r"horm":      "hormone",
    r"prep":      "preparation",
    r"preps":     "preparations",
    r"sim":       "similar",
    r"mfd":       "manufactured",
    r"bld":       "blood",
    r"fract":     "fractions",
    r"parentl":   "parenteral",
    r"anml":      "animal",
    r"aml":       "animal",
    r"narc":      "narcotic",
    r"subs":      "substances",
    r"substnces": "substances",
    r"substnce":  "substance",
    r"diag":      "diagnostic",
    r"diagnstc":  "diagnostic",
    r"immn":      "immunological",
    r"btech":     "biotechnological",
    r"proc":      "process",
    r"cult":      "culture",
    r"prepr":     "prepared",
    r"obt":       "obtained",
    r"struct":    "structure",
    r"ana":       "analog",
    r"dos":       "dosage",
    r"n-wov":     "non-woven",
    r"fab":       "fabric",
    r"impreg":    "impregnated",
    r"micro-orga": "micro-organism",
    r"surg":      "surgical",
    r"art":       "article",
    r"arts":      "articles",
    r"prim":      "primarily",
    r"admin":     "administration",
    r"sterie":    "sterile",   # observed typo of 'sterile'
    r"mat":       "material",
    r"absorb":    "absorbable",
    r"Mx":        "Mixtures",
    r"Mixt":      "Mixtures",
    r"caloric":   "caloric",   # already a full word; passthrough

    # Single-letter abbreviations, last because they are the most ambiguous.
    r"w":         "with",
    r"f":         "for",
    r"o":         "other",
}


def _replace_one(pattern: str, repl: str, text: str) -> str:
    """Word-bounded, case-insensitive replacement that preserves the
    capitalisation of the first matched character."""
    rx = re.compile(rf"\b{re.escape(pattern)}\b", re.IGNORECASE)

    def _sub(m: re.Match) -> str:
        original = m.group(0)
        # If the original starts with an upper-case letter, capitalise
        # the first letter of the replacement.
        if original[:1].isupper():
            return repl[:1].upper() + repl[1:]
        return repl

    return rx.sub(_sub, text)


def expand_shorthand(text: str) -> str:
    """Return *text* with Canadian Customs chapter-30 shorthand expanded
    to full words. Word-bounded so substrings inside other words are
    untouched. Idempotent (running it twice produces the same output
    as running it once)."""
    if not text:
        return text
    s = text
    # Apply structural multi-token rules first.
    for rx, repl in _STRUCTURAL_RULES:
        s = rx.sub(repl, s)
    # Apply simple word-bounded replacements.
    for pat, repl in _ABBREV.items():
        s = _replace_one(pat, repl, s)
    # Collapse any double spaces introduced by chained substitutions.
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


if __name__ == "__main__":
    # Quick self-test
    samples = [
        "Heparin & its salts;human or animal substnces for therap or prophltc uses, nes",
        "Medi,cont penicillins/deriv w penicillanic acid struct, streptomycins/deriv,nfrs",
        "Medi,cont alkaloids/deriv t/o,nes,therap/prophltc,doses/frs,o/t No 30.02/05/06",
        "Antibiotics, nes, for vet use, in dosage",
        "Other human or animal subs prepared for therapeutic or prophylactic uses, nes",
    ]
    for s in samples:
        print(s)
        print("  =>", expand_shorthand(s))
        print()
