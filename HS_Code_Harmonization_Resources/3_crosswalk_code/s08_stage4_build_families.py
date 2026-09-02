"""Stage 4. Group the codes that carry the same goods, and give every family and record a name.


This is the figure the whole crosswalk exists for. Stage 3 gave each commodity string the path it
travelled; this asks which strings are the SAME goods under different numbers, and names the set.

It decides nothing either. A family is the connected component of the successions Stage 2 settled,
and an identifier is a function of the members. Both are built to `METHOD_family_id.md`, which
settles the schemes and is the only place either is stated.

WHAT A FAMILY IS BUILT FROM, AND WHAT IT IS NOT
------------------------------------------------
Resolved successions ONLY. A held row, an unresolved row, a row that left the chapter and a row
that was never a retirement all contribute NO edge. That is defect D1, the reason this rebuild
exists: the released crosswalk read a blank decision as approval and linked on it. Stage 2 leaves
no blanks today, and this stage still refuses to read anything but `succeeded`, because the
protection has to survive the next delivery rather than today's tidy one.

THE TWO IDENTIFIERS, AND WHY NEITHER IS A COUNTER
--------------------------------------------------
    family_id   IM-3002901010          the family's earliest-trading member
    record_id   IM-3002190000-201701   the code, and the month that string first traded

Both are functions of a fixed property, so a rebuild on another machine in another order produces
the same names. `METHOD_family_id.md` carries the argument and the measurements; it is not
restated here, because a second copy drifts and the drifted copy reads as authoritative.

A SEQUENTIAL LABEL IS EMITTED AND IT IS NOT A KEY. `family_display_number` orders families by
their anchor's first month and numbers them, because a table of 117 families wants a short column.
It is named so it cannot be mistaken for an identifier and nothing may join on it. The moment a
display number is joined on, it acquires every problem the method document describes.

WHY record_id AND span_id BOTH APPEAR
--------------------------------------
Stage 3 keys a commodity string as `imports:3002.19.00.00:2017-01`, the shape `link_id` uses.
The published identifier is `IM-3002190000-201701`, the shape `family_id` uses. They are two
renderings of ONE fact, the code and its first month, and both are carried so the files join
without anyone re-deriving anything. A control asserts the mapping is one-to-one in both
directions, so the two renderings cannot come apart.

WHAT IT REFUSES TO DO
---------------------
  - put a code in a family when the inventory does not hold that code
  - build a family from anything but a settled succession
  - emit two families under one identifier
  - lose a commodity string, invent one, or let the value stop reconciling
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s05_make_adjudication_queue import dotted  # noqa: E402
from s07_stage3_route import span_id_for  # noqa: E402
# WHERE ONE COMMODITY ENDS AND THE NEXT BEGINS. Owned by Stage 1a and CALLED, not restated: this
# file used to import the threshold and rebuild the rule around it, which is sharing the number
# and copying the logic. The day Stage 1a learned that a relabel can end a span with no gap, this
# copy kept the old answer and refused to place a settled succession on any span.
from s02_stage1_candidates import span_runs  # noqa: E402

FLOWS = (("imports", "IM"), ("exports", "EX"))

COLUMNS = [
    "record_id", "span_id", "flow", "hs_code", "description",
    "first_period", "last_period", "value_cad",
    "family_id", "family_anchor_code", "family_anchor_first_traded", "family_size",
    "family_commodities", "family_display_number", "family_codes",
]


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def record_id_for(prefix, code, first_period):
    """The published name of one commodity string. The same fact as Stage 3's span_id.

    THE `R` IS LOAD-BEARING AND IT WAS MISSING FOR A DAY. Without it a record read `IM-30062000-
    198801` while its family read `IM-30062000`, which is the same string plus a month. That is not
    a rare coincidence: a record whose code IS its family's anchor is in exactly that position, and
    182 of the 572 commodity strings, 32 per cent, are. Two different kinds of key separated only
    by a suffix is how a wrong join survives review.

    v1 had this right and v2 dropped it. `IMR_0264` was a record and `IM_0154` was a family, and
    the R was doing the work. It is restored:

        IMR-3004500040-199801   the record        IM-3004509920   its family
        EXR-30062000-198801     the record        EX-30062000     its family

    `METHOD_family_id.md` settles the form. It is derived here rather than reformatted from the
    span_id, so the two renderings are computed independently from the same two fields and a
    control can prove they agree instead of one being assumed from the other.
    """
    return "%sR-%s-%s" % (prefix, digits(code), first_period)


def duplicate_identifiers(rows):
    """Record identifiers naming more than one commodity string, if any.

    LIFTED OUT OF main() SO A CONTROL CAN REACH IT. The check used to assert that a synthetic pair
    of identical strings PRODUCED a duplicate, which passes precisely when the defect is present
    and would have gone on passing after any fix. The refusal itself was never exercised and
    deleting it changed nothing. Finding 104.
    """
    counted = Counter(r["record_id"] for r in rows)
    return sorted(identifier for identifier, n in counted.items() if n > 1)


def stop(message, examples=()):
    print()
    print("Stage 4 STOPPED: %s" % message)
    for item in list(examples)[:8]:
        print("    %s" % (item,))
    raise SystemExit(1)


def first_traded(inventory):
    """The month each code first appears, read from Stage 0 rather than recomputed elsewhere.

    WRITTEN WITH min() RATHER THAN A RUNNING COMPARISON, and the first version was the other way
    round. `check_stage1c_rank.py` refuses any module that compares `first_period` while writing
    into a map keyed on the code, because three separate readers of an earliest-WORDING map were
    found one at a time and the shape itself was made the thing to forbid. This map holds months
    and not wordings, so it was a false positive of that rule, but the rule is deliberately blunt
    and the right answer to a blunt guard is to stop matching it rather than to soften it.

    min() is also the better statement of what this is: a value that cannot depend on the order
    the records arrive in, which is the property METHOD_family_id.md requires of the anchor.
    """
    months = defaultdict(list)
    for record in inventory:
        months[record["hs_code"]].append(record["first_period"])
    return {code: min(seen) for code, seen in months.items()}


def components(codes, edges):
    """Connected components over the settled successions. Union-find, so the answer cannot depend
    on which end of an edge is read first or on the order edges arrive in."""
    parent = {code: code for code in codes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in edges:
        a, b = find(left), find(right)
        if a != b:
            # The smaller code always becomes the root, so the SHAPE of the tree does not depend
            # on the order the edges were read. The anchor is chosen from the members afterwards
            # and never from the root, but a deterministic tree makes the whole build easier to
            # reason about and costs nothing.
            parent[max(a, b)] = min(a, b)
    grouped = defaultdict(list)
    for code in codes:
        grouped[find(code)].append(code)
    return grouped


def trading_spans_of(inventory):
    """Group each code's lives into trading spans, splitting where the number was handed on.

    THE NODE OF A FAMILY IS A SPAN, NOT A CODE NUMBER, and it was a code number until 2026-08-16.
    Stage 1a splits a recycled number at REUSE_GAP_MONTHS, and Stage 3 and Stage 5 both refuse to
    route across that gap; Stage 4 was the only stage that collapsed the two sides back together,
    so five recycled numbers welded unrelated lineages into one family. `EX-30049010` held
    "Medicaments nes, in dosage, for human use", which ended in 1988-12, in the same family as
    cannabis, which began in 2018-02. A family is "the set of commodity codes that carry the same
    goods", and those are not the same goods. Finding 103.

    The threshold is imported from Stage 1a, never restated, so the three stages cannot disagree
    about where one commodity ends and the next begins.
    """
    lives = defaultdict(list)
    for record in inventory:
        lives[record["hs_code"]].append(record)
    spans, span_of_life = {}, {}
    for code, entries in lives.items():
        for run in span_runs(entries):
            key = (code, run[0]["first_period"])
            spans[key] = {"first": run[0]["first_period"],
                          "last": max(r["last_period"] for r in run)}
            for life in run:
                span_of_life[(code, life["first_period"])] = key
    return spans, span_of_life


def build(flow, prefix, inventory, resolved):
    spans, span_of_life = trading_spans_of(inventory)
    known = {code for code, _first in spans}

    edges, missing = [], []
    for answer in resolved:
        if answer["outcome"] != "succeeded":
            continue
        left, right = digits(answer["retiring_code"]), digits(answer["successor"])
        if left not in known or right not in known:
            missing.append("%s names %s" % (answer["link_id"], answer["successor"]))
            continue
        # The span that ended here, and the span that could receive what it carried. Same rule as
        # Stage 3's receiving_span: the earliest span still open after the predecessor stopped.
        leaving = next((k for k in spans
                        if k[0] == left and spans[k]["last"] == answer["last_period"]), None)
        open_after = [k for k in spans
                      if k[0] == right and spans[k]["last"] > answer["last_period"]]
        landing = min(open_after, key=lambda k: spans[k]["first"]) if open_after else None
        if leaving is None or landing is None:
            missing.append("%s cannot be placed on a span" % answer["link_id"])
            continue
        edges.append((leaving, landing))

    grouped = components(sorted(spans), edges)
    family_of, anchors = {}, {}
    for members in grouped.values():
        # Earliest trading month, ties broken by the smaller code. Both read from Stage 0.
        anchor = min(members, key=lambda k: (spans[k]["first"], k[0]))
        # THE ANCHOR'S OWN MONTH IS PART OF THE NAME. Once a family is a set of spans, two
        # families can each be anchored on a different life of the SAME number: 30029010,
        # 30033100 and 30049010 all do on exports. Naming a family after the code alone would
        # give one identifier to two sets, which is the failure this whole scheme exists to stop.
        identifier = "%s-%s-%s" % (prefix, anchor[0], spans[anchor]["first"])
        if identifier in anchors:
            # Two distinct span-sets producing one name. Cannot happen while the anchor is a
            # span, because a span belongs to exactly one family, but the assertion is what makes
            # that a fact rather than a belief.
            missing.append("%s names two different families" % identifier)
        anchors[identifier] = (anchor[0], spans[anchor]["first"], sorted(members))
        for member in members:
            family_of[member] = identifier

    # A display label, ordered by when each family's anchor first traded. Never a key.
    order = sorted(anchors, key=lambda fid: (anchors[fid][1], anchors[fid][0]))
    display = {fid: n for n, fid in enumerate(order, start=1)}

    rows = []
    for record in inventory:
        code = record["hs_code"]
        identifier = family_of[span_of_life[(code, record["first_period"])]]
        anchor, anchor_first, members = anchors[identifier]
        codes_in_family = sorted({c for c, _f in members})
        rows.append({
            "record_id": record_id_for(prefix, code, record["first_period"]),
            "span_id": span_id_for(flow, code, record["first_period"]),
            "flow": flow,
            "hs_code": dotted(code),
            "description": record["description"],
            "first_period": record["first_period"],
            "last_period": record["last_period"],
            "value_cad": record["total_value_cad"],
            "family_id": identifier,
            "family_anchor_code": dotted(anchor),
            "family_anchor_first_traded": anchor_first,
            "family_size": len(codes_in_family),
            "family_commodities": len(members),
            "family_display_number": display[identifier],
            "family_codes": ";".join(dotted(c) for c in codes_in_family),
        })
    return rows, anchors, missing, len(edges)


def describe(flow, rows, anchors, edges):
    print("%s:" % flow)
    print("  commodity strings                 : %d" % len(rows))
    print("  distinct codes                    : %d" % len({r["hs_code"] for r in rows}))
    print("  successions used                  : %d" % edges)
    print("  FAMILIES                          : %d" % len(anchors))
    # COUNTED IN CODES, and the first version of this counted SPANS while printing the word
    # "codes". The two differ wherever a number was recycled, and it made the stage and its check
    # name different largest families. A family holds N codes across M commodities and M >= N; the
    # published `family_size` is the code count, so the summary says the same thing.
    codes_in = {fid: len({c for c, _f in members}) for fid, (_a, _f, members) in anchors.items()}
    sizes = Counter(codes_in.values())
    print("      singletons, one code that never changed identity : %d" % sizes.get(1, 0))
    print("      largest family                                   : %d codes" % max(sizes))
    print("  value carried                     : CAD {:,.0f}".format(
        sum(float(r["value_cad"]) for r in rows)))
    biggest = max(sorted(codes_in), key=lambda fid: codes_in[fid])
    print("  the largest family is %s, %d codes over %d commodit%s, anchored on %s from %s"
          % (biggest, codes_in[biggest], len(anchors[biggest][2]),
             "y" if len(anchors[biggest][2]) == 1 else "ies",
             dotted(anchors[biggest][0]), anchors[biggest][1]))


def main():
    print("Stage 4: group the codes that carry the same goods. This stage decides nothing.")
    print()
    for flow, prefix in FLOWS:
        inventory_path = WORK_DIR / ("commodity_inventory_%s.csv" % flow)
        resolved_path = WORK_DIR / ("stage2_resolved_%s.csv" % flow)
        for path, owner in ((inventory_path, "s01_stage0_read_source.py"),
                            (resolved_path, "s06_stage2_apply_decisions.py")):
            if not path.exists():
                stop("%s not found. Run %s first." % (path, owner))
        inventory = load(inventory_path)
        resolved = load(resolved_path)

        rows, anchors, missing, edges = build(flow, prefix, inventory, resolved)

        if missing:
            stop("%d settled succession(s) name a code this delivery does not hold. A family "
                 "cannot contain a code the inventory has never seen." % len(missing), missing)
        if len(rows) != len(inventory):
            stop("%d commodity string(s) in, %d out. Nothing may be lost or invented here."
                 % (len(inventory), len(rows)))
        duplicated = duplicate_identifiers(rows)
        if duplicated:
            stop("%d record identifier(s) name more than one commodity string."
                 % len(duplicated), duplicated)
        # NOT "two families share an anchor CODE" any more, which is now legitimate: 30029010,
        # 30033100 and 30049010 each anchor two families, one per life of the number. What may
        # never repeat is the identifier, which carries the anchor's month as well.
        if len({(a, f) for a, f, _m in anchors.values()}) != len(anchors):
            stop("two families share an anchor span, so one identifier names two sets.")
        expected = sum(float(r["total_value_cad"]) for r in inventory)
        got = sum(float(r["value_cad"]) for r in rows)
        if abs(expected - got) > 0.005:
            stop("value does not reconcile: CAD %.2f in, CAD %.2f out" % (expected, got))

        describe(flow, rows, anchors, edges)
        destination = WORK_DIR / ("stage4_families_%s.csv" % flow)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print("  written: %s" % destination.relative_to(PROJECT_ROOT))
        print()

    print("Stage 4 complete. Every commodity string belongs to exactly one named family.")


if __name__ == "__main__":
    main()
