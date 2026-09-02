# The adjudication queue, and how to fill it in

`stage2_adjudication_queue.csv` holds every retired commodity code whose successor the official
record could not settle. One row is one decision.

Everything needed to decide a row is in the row itself. The code, the tariff schedules
and every other file are unnecessary.

## Fill in these five columns

| Column | What to put |
|---|---|
| `decision` | `approve` if the proposed successor is right, `reject` if it is not, `none` if the goods left Chapter 30 entirely |
| `correct_successor_if_rejected` | the code held to be right, where one is known; left blank otherwise |
| `reason` | why. Required on every reject; welcome on any row |
| `decided_by` | the name of whoever ruled |
| `decided_on` | the date |

**A blank decision means undecided, and the next stage refuses to build until none are left.**
That is deliberate. In the released crosswalk an unmarked row was read as an approval, and links
entered the data that nobody had decided.

## The dates, and why they often decide a row on their own

`proposed_successor_first_traded` and `..._last_traded` say when the proposed successor actually
traded, and the runner-up carries the same two columns.

`successor_began_at_the_boundary` is `yes` when the successor first appears the month after the
retirement. That is the strongest structural evidence available and it holds for 159 of the 231
rows. Where it is `no`, the successor already existed and absorbed the trade, which is a real
outcome but deserves more scrutiny.

The dates frequently settle a row by themselves. In row 1 the runner-up did not begin trading
until 2018-01, thirty years after the code retired, so it was never a possible successor.

## When the successor is a broader bucket, not an equivalent

`successor_is_more_aggregate` is `yes` when the proposed successor covers more than the retired
code did, and the two descriptions in the row show what changed.

Two signals set it. The structural one: the last two digits are the statistical breakout and `00` is the parent, so
a code ending `10` succeeded by one ending `00` has been folded into the bucket above it.

The wording one: the successor states strictly fewer things. `Medicaments nes, in dosage, for
human use` succeeded by `Medicaments nes, in dosage` drops the human qualifier, so the successor
also carries veterinary trade the predecessor never did.

**This is far more common on exports, and the reason is structural.** Domestic exports are
recorded at eight digits and imports at ten, so exports have much less room for statistical
breakouts. When an export breakout retires, its trade usually collapses into the parent. On this
delivery the flag fires on 16 export rows and 7 import rows, and the export cases cluster at
December 1988, which was an aggregation of the export nomenclature rather than a renumbering.

**A flagged link is not wrong.** The trade really did move there. What is lost is resolution: a
series traced across such a boundary stops distinguishing what the predecessor distinguished.
Approving one of these is approving a real succession with a real loss of detail, and it is
worth noting in the reason so the limitation is recorded rather than inferred later.

## Reading the evidence columns

`wording_match` is how similar the two descriptions are as text, from 0 to 1. It is the published
similarity score. It counts shared letters and cannot read meaning, so a high number is not proof.

`shared_meaning_words` is how much of their meaning the two descriptions share, after shorthand
is expanded and filler words are dropped. **It is not a score and no threshold uses it.** It is
there because wording and meaning can disagree: two descriptions can share nine tenths of their
characters while the part that decides the code is a heading reference occupying a fraction of
the string.

`official_record` says what the documents settled before anyone was asked. Where it says no
official source reaches the boundary, the analyst's judgement is the only thing available.

`candidates_removed_on_meaning` lists codes already ruled out, with the reason. They are shown
so the ranking can be disagreed with.

**The removals are proposals too, and they can be overturned.** Where a code was removed
wrongly, the row is marked `reject`, that code is named in `correct_successor_if_rejected`, and
a reason is given. The software removed it; the ruling belongs to the analyst.

`closest_removed_candidate` gives the best of those in full, with its description, the months it
traded, its wording match and why it went. It carries the same evidence as the proposal so the
two can be weighed against each other. A row where everything was ruled out would otherwise arrive with an
empty proposal and no way to see what was rejected, and a rejection that cannot be read cannot
be disagreed with. It is labelled removed, never proposed, so nothing about it reads as a
recommendation.

Two reasons appear there that are not about meaning. `continuity` means the code had not begun
trading when the retirement happened, allowing a year of grace for the lag between a code
coming into force and its first shipment. `use`, `mixing`, `origin` and the rest are the
tariff distinctions.

## How the two numbers are computed

Stated so the figures can be reproduced or challenged without reading the code.

**`wording_match`** is `difflib.SequenceMatcher(None, a, b).ratio()` from the Python standard
library. It reports twice the number of matching characters divided by the total length of both
strings, so 1.0 means the two strings are identical. The comparison is a gestalt pattern match
of the Ratcliff and Obershelp kind: it finds the longest matching run, then recurses either side
of it.

Both descriptions are prepared the same way before the comparison, and only this way: lowercase,
then every character other than a letter, a digit or a space becomes a space, then repeated
spaces are collapsed. **Shorthand is not expanded.** "vet" is compared as the three letters
"vet", not as "veterinary". That is deliberate. It is the preparation every published figure in
this project already rests on, and changing it would make the new numbers incomparable with the
old ones.

**`shared_meaning_words`** is the Jaccard similarity coefficient, the size of the intersection
divided by the size of the union, computed over the two sets of meaning words. A word set is
built by expanding shorthand through this project's own lookup table, applying the same
preparation as above, then dropping twenty filler words: not, elsewhere, specified, nes, other,
than, whether, or, for, of, the, and, in, to, a, an, with, on, o, t.

A set comparison, and not a second run of the sequence matcher. Running the matcher over
expanded text was tried and rejected: expanding "nes" to "not elsewhere specified" injects a
long shared phrase, which the matcher rewards when both descriptions carry it and penalises when
only one does. That moved 843 of 3,699 candidate pairs by more than 0.10 in a direction which
tracked boilerplate rather than meaning. A set has no order and no length, so it is immune to
both effects.

**Tools.** Python 3, standard library only. `difflib` for the wording comparison, `re` for text
preparation, `csv` for every file, `sqlite3` to read the trade databases, `hashlib` for the
reproducibility hashes. There are no third-party packages anywhere in the pipeline or its
checks, verified by parsing every source file rather than by searching the text. Nothing needs
installing beyond Python itself.

## The order

Rows are ordered by how likely they are to be wrong, not by how close the wording is. The first
rows are the ones where the evidence conflicts. The long tail marked *please spot check* is
where wording and meaning both agree, and those need confirming rather than deciding.

## The rows marked HELD

Twenty-one rows say `HELD, do not decide yet`. An international correlation table could answer
them and it has not been extracted yet. Deciding them now risks a document overruling the ruling
later, which would reopen a decision already signed. They are shown rather than hidden so that nothing
is missing from the count.
