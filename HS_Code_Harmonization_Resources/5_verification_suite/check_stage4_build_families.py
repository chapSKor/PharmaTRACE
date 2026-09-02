"""
Check for Stage 4. Is every family the closure of settled successions, and is every name earned?


Inputs:
    work/stage4_families_{imports,exports}.csv     produced by pipeline/stage4_build_families.py
    work/commodity_inventory_{imports,exports}.csv produced by pipeline/stage0_read_source.py
    work/stage2_resolved_{imports,exports}.csv     produced by pipeline/stage2_apply_decisions.py
    work/stage3_routed_{imports,exports}.csv       produced by pipeline/stage3_route.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Is a family exactly the connected component of the successions Stage 2 settled, and is every
identifier a function of the members alone?

It does NOT ask whether two codes SHOULD be one family. That is the crosswalk's whole claim and it
was settled row by row in Stage 2; grouping a wrong link correctly still groups a wrong link.


WHY THE COMPONENTS ARE REBUILT WITH A DIFFERENT ALGORITHM
----------------------------------------------------------
Convention 2. The stage uses union-find. This check uses breadth-first search over an adjacency
map, written here, sharing no code with the stage. Comparing union-find against union-find agrees
when both are wrong, which is how Stage 0 under-reported CAD 11,472,590,012 while 25 controls
passed.

`METHOD_family_id.md` requires one control by name: recompute every identifier from the member
sets in a shuffled order and require the same answer, "because a function of the member set alone
is the whole claim and an untested claim is an assertion". That control is below, and it is run
over the record identifiers too.
"""

import csv
import os
import sys
from collections import Counter, defaultdict, deque

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage4_build_families as stage  # noqa: E402
# The threshold that separates a re-wording from a reuse. Owned by Stage 1a; the merge itself is
# written out below rather than imported, so this check can still disagree with the stage.
from stage1_candidates import REUSE_GAP_MONTHS, period_to_months  # noqa: E402
import meaning_gates as _gates  # noqa: E402

# A span also ends where a relabel crosses a decisive distinction, with no gap at all. Added
# 2026-08-17 with the stage-side rule. The RULES are shared, because they are the published
# specification and live in decisions/decisive_distinctions.csv; the composition below is written
# out here rather than imported, for the same reason the merge is. Importing
# stage1_candidates.continues_the_span would make this control compare the stage's answer with
# itself, which is finding 108 exactly.
_DISQUALIFYING = [r for r in _gates.load_rules(
    os.path.join(PROJECT, "decisions", "decisive_distinctions.csv"))
    if str(r.get("action", "")).strip() == "disqualify"]


def _relabelled(before_text, after_text):
    return any(_gates.rule_fires(rule, before_text, after_text) for rule in _DISQUALIFYING)

FLOWS = (("imports", "IM"), ("exports", "EX"))
WORK = os.path.join(PROJECT, "work")

# Re-measured 2026-08-16 after finding 103, and reconciled before being changed. A family is a set
# of trading SPANS and not of code numbers, so five recycled numbers stopped welding unrelated
# lineages together: imports 117 -> 118 families and exports 45 -> 48. The largest import family
# falls 21 -> 17 codes because butter-making ferment cultures left the toxoid family it had never
# belonged to. Both anchors now carry the anchor's own month, because two families can be anchored
# on different lives of one number and three export numbers are.
#
# METHOD_family_id.md projected 124 import families with 27 rows open and 108 once they resolved.
# Neither figure is reached, and the reason is recorded rather than smoothed: those 27 did not all
# become successions. Fifteen were never retirements and contribute no edge at all.
EXPECTED = {
    # successions 269 -> 270 on 2026-08-17: the veterinary life of 3004.50.99.30, which Stage 1a
    # now retires in its own right and which the analysts settled onto 3004.50.99.50.
    # FAMILIES DOES NOT MOVE, and that is worth stating rather than passing over. The new span
    # joins the veterinary family its successor already belonged to instead of founding one, so
    # the partition changes and the count does not. The same is true of every other figure here:
    # strings, codes, singletons, largest and value are all untouched, because splitting a span
    # moves a record between families and neither creates nor destroys one.
    "imports": {"strings": 475, "codes": 386, "families": 118, "successions": 270,
                # singletons 32 -> 31 on 2026-08-18, finding 122. IM-3002490010-202201 and
    # IM-3002490020-202201 stopped being singletons because the two 2021-12 lines now reach
    # them, and IM-3002900020-202201 became one because the toxin chain no longer ends there.
    # Two lost, one gained. Families, codes, largest and value are all unchanged.
    "singletons": 31, "largest": 17, "value": 415669236806.0,
                "anchor": "IM-3004409019-198801"},
    "exports": {"strings": 97, "codes": 74, "families": 48, "successions": 30,
                "singletons": 33, "largest": 6, "value": 216729045491.0,
                "anchor": "EX-30023100-198801"},
}

results, notes = [], []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, "  -- " + detail if detail else ""))


def disclose(name, detail=""):
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, "  -- " + detail if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


def by_search(codes, edges):
    """Connected components by breadth-first search. Written here, sharing nothing with the
    stage's union-find, so the two can disagree."""
    neighbours = defaultdict(set)
    for left, right in edges:
        neighbours[left].add(right)
        neighbours[right].add(left)
    seen, groups = set(), []
    for code in sorted(codes):
        if code in seen:
            continue
        group, queue = set(), deque([code])
        while queue:
            node = queue.popleft()
            if node in group:
                continue
            group.add(node)
            queue.extend(n for n in neighbours[node] if n not in group)
        seen |= group
        groups.append(sorted(group))
    return groups


print("Check for Stage 4. Is every family the closure of settled successions?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")


def inventory_row(code, first, last="202606", value="100.00", description="a commodity"):
    return {"hs_code": code, "first_period": first, "last_period": last,
            "total_value_cad": value, "description": description}


def resolved_row(flow, code, last, outcome="succeeded", successor=""):
    return {"link_id": "%s:%s:%s-%s" % (flow, code, last[:4], last[4:]),
            "retiring_code": code, "successor": successor, "outcome": outcome}


# 1. A succession naming a code the delivery does not hold.
_inv = [inventory_row("3002190000", "201701", "202112")]
_res = [resolved_row("imports", "3002190000", "202112", successor="9999.99.99.99")]
_, _, _missing, _ = stage.build("imports", "IM", _inv, _res)
record("a succession naming a code the delivery does not hold is refused", bool(_missing),
       "a family cannot contain a code the inventory has never seen")

# 2. Two commodity strings that would carry the same identifier.
_dupe = [inventory_row("3002190000", "201701", "202112"),
         inventory_row("3002190000", "201701", "202606", description="a different wording")]
_rows, _, _, _ = stage.build("imports", "IM", _dupe, [])
# THE REFUSAL ITSELF, not the defect that would trigger it. This control used to assert that two
# identical strings PRODUCE a duplicate identifier, which passes exactly when the stage is broken
# and would keep passing after any fix; the refusal in main() was never reached and deleting it
# changed nothing. Finding 104. duplicate_identifiers() is now lifted out so it can be provoked.
record("a duplicate record identifier is detected",
       stage.duplicate_identifiers(_rows) == ["IMR-3002190000-201701"],
       "the refusal fires on the synthetic pair: %s" % stage.duplicate_identifiers(_rows))
record("and it stays silent on the real delivery",
       not stage.duplicate_identifiers(
           load(os.path.join(WORK, "stage4_families_imports.csv"))
           + load(os.path.join(WORK, "stage4_families_exports.csv"))),
       "572 commodity strings, no identifier naming two of them")

# 3. THE D1 GUARD. Anything but `succeeded` must contribute no edge whatsoever.
_two = [inventory_row("3002190000", "201701", "202112"),
        inventory_row("3002150000", "201701", "202606")]
for _outcome in ("held", "unresolved", "left_chapter", "not_a_retirement"):
    _built, _anchors, _, _edges = stage.build(
        "imports", "IM", _two,
        [resolved_row("imports", "3002190000", "202112", outcome=_outcome,
                      successor="3002.15.00.00")])
    record("a `%s` row builds no family edge" % _outcome,
           _edges == 0 and len(_anchors) == 2,
           "two codes, two families; the released crosswalk linked on a blank and that is defect D1")

print()
print("Controls that MUST PASS (correct input must not be flagged):")

for flow, prefix in FLOWS:
    expect = EXPECTED[flow]
    built = load(os.path.join(WORK, "stage4_families_%s.csv" % flow))
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    resolved = load(os.path.join(WORK, "stage2_resolved_%s.csv" % flow))
    routed = load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))

    record("%s: every commodity string belongs to exactly one family" % flow,
           len(built) == expect["strings"]
           and len({r["record_id"] for r in built}) == len(built)
           and all(r["family_id"] for r in built),
           "%d string(s), %d distinct identifier(s)"
           % (len(built), len({r["record_id"] for r in built})))

    value = sum(float(r["value_cad"]) for r in built)
    independent = sum(float(r["total_value_cad"]) for r in inventory)
    record("%s: the value reconciles to the cent" % flow,
           abs(value - expect["value"]) < 0.005 and abs(value - independent) < 0.005,
           "CAD {:,.2f}".format(value))

    # RULE 2. Rebuilt by breadth-first search, sharing no code with the stage's union-find.
    codes = sorted({digits(r["hs_code"]) for r in built})
    # The lives merged into trading spans HERE, written out rather than imported, so this check
    # can disagree with the stage about where one commodity ends and the next begins.
    lives = defaultdict(list)
    for r in inventory:
        lives[r["hs_code"]].append(r)
    bounds, span_of_life = {}, {}
    for code, entries in lives.items():
        entries.sort(key=lambda r: r["first_period"])
        current = [entries[0]]
        runs = [current]
        for before, after in zip(entries, entries[1:]):
            if ((period_to_months(after["first_period"])
                    - period_to_months(before["last_period"])) > REUSE_GAP_MONTHS
                    or _relabelled(before["description"], after["description"])):
                current = [after]
                runs.append(current)
            else:
                current.append(after)
        for run in runs:
            key = (code, run[0]["first_period"])
            bounds[key] = (run[0]["first_period"], run[-1]["last_period"])
            for life in run:
                span_of_life[(code, life["first_period"])] = key
    settled_pairs, settled = [], []
    for a in resolved:
        if a["outcome"] != "succeeded":
            continue
        settled_pairs.append(a)
        left, right = digits(a["retiring_code"]), digits(a["successor"])
        leaving = next((k for k in bounds if k[0] == left and bounds[k][1] == a["last_period"]),
                       None)
        after = [k for k in bounds if k[0] == right and bounds[k][1] > a["last_period"]]
        landing = min(after, key=lambda k: bounds[k][0]) if after else None
        if leaving and landing:
            settled.append((leaving, landing))
    groups = by_search(sorted(bounds), settled)
    rebuilt = {}
    for members in groups:
        anchor = min(members, key=lambda k: (bounds[k][0], k[0]))
        for member in members:
            rebuilt[member] = "%s-%s-%s" % (prefix, anchor[0], bounds[anchor][0])
    written = {span_of_life[(digits(r["hs_code"]), r["first_period"])]: r["family_id"]
               for r in built}
    record("%s: the families rebuilt by a different algorithm agree exactly" % flow,
           rebuilt == written and len(groups) == expect["families"],
           "%d families by breadth-first search over spans, %d written, %d span(s) disagree"
           % (len(groups), len(set(written.values())),
              sum(1 for k in written if rebuilt.get(k) != written[k])))

    # THE WELD FINDING 103 REMOVED, kept so it cannot come back. Stage 1a splits a recycled number
    # and Stages 3 and 5 refuse to route across the split; a family that holds both sides puts
    # cannabis and 1988 general medicaments in one set, which is what EX-30049010 did.
    # Named by case rather than by rule, and the first attempt at this control was wrong. "No
    # family holds two lives of one number" fails on exports 30029020, where the 1988 blood line
    # and the Saxitoxin line BOTH reach 30029090 through settled successions. That is an ordinary
    # transitive closure into a residual and it is correct; a family may legitimately hold two
    # lives of a number when the record joins them. What must never happen is co-membership by
    # code identity ALONE, which is what the pre-2026-08-16 stage produced, so the three welds
    # finding 103 removed are pinned individually.
    SEPARATED = {
        "exports": [("30049010", "198801", "201802", "1988 general medicaments against cannabis"),
                    ("30029010", "198801", "199712", "1988 human blood against Ricin")],
        "imports": [("3002900020", "199801", "202201",
                     "butter-making ferment cultures against toxoids and antitoxins")],
    }
    rejoined = []
    for code, one, two, why in SEPARATED[flow]:
        a = written.get((code, one))
        b = written.get((code, two))
        if a is None or b is None or a == b:
            rejoined.append("%s: %s and %s both in %s (%s)" % (code, one, two, a, why))
    record("%s: the lives finding 103 separated have not rejoined" % flow, not rejoined,
           "%d recycled number(s) still split, each life in its own family"
           % len(SEPARATED[flow]) if not rejoined else "%s" % rejoined)

    record("%s: only settled successions were used" % flow,
           len(settled) == expect["successions"],
           "%d succession(s); held, unresolved, left_chapter and not_a_retirement contribute none"
           % len(settled))

    # THE CONTROL METHOD_family_id.md ASKS FOR BY NAME. Two deliberate reorderings rather than a
    # random one, because an unreproducible control is a worse fault than the one it guards.
    stable = True
    for reorder in (lambda rs: list(reversed(rs)),
                    lambda rs: sorted(rs, key=lambda r: (r.get("description", ""),
                                                         r.get("hs_code", "")))):
        again, _a, _m, _e = stage.build(flow, prefix, reorder(inventory), reorder(resolved))
        if ({r["record_id"]: r["family_id"] for r in again}
                != {r["record_id"]: r["family_id"] for r in built}):
            stable = False
    record("%s: shuffling the input changes no family and no identifier" % flow, stable,
           "rebuilt from reversed order and from description order, both identical")

    # Read back, per rule 10, and re-derived from the columns the file itself carries.
    forged, misanchored = [], []
    for r in built:
        members = [digits(c) for c in r["family_codes"].split(";") if c]
        if (r["family_id"] != "%s-%s-%s" % (prefix, digits(r["family_anchor_code"]),
                                            r["family_anchor_first_traded"])
                or int(r["family_size"]) != len(members)
                or digits(r["hs_code"]) not in members):
            forged.append(r["record_id"])
        # And the anchor really is the family's earliest span, checked against the spans this
        # file rebuilt rather than against the stage's own choice.
        mine = [k for k, fid in written.items() if fid == r["family_id"]]
        if mine:
            truth = min(mine, key=lambda k: (bounds[k][0], k[0]))
            if (digits(r["family_anchor_code"]) != truth[0]
                    or r["family_anchor_first_traded"] != bounds[truth][0]):
                misanchored.append(r["family_id"])
    record("%s: every family identifier re-derives from the columns beside it" % flow,
           not forged, "%d row(s) checked against their own member list" % len(built)
           if not forged else "%d disagree: %s" % (len(forged), forged[:3]))
    record("%s: every anchor is its family's earliest span, rebuilt independently" % flow,
           not misanchored, "%d families" % len(set(written.values()))
           if not misanchored else "%d misanchored: %s" % (len(set(misanchored)),
                                                           sorted(set(misanchored))[:3]))

    # THE FOUR COLUMNS NO CONTROL READ. Finding 114. flow, description, last_period and
    # family_commodities could each be overwritten on every row of this artefact, with garbage or
    # with blank, and the whole suite stayed green. The first three are copied from the inventory
    # life the row is about, so the inventory is where they are checked; family_commodities is
    # counted from the spans this file rebuilt for itself, never from the stage's own tally.
    #
    # family_size and family_commodities are DIFFERENT numbers and the difference is the point: a
    # family of four codes can hold five spans, because a recycled number contributes two. Reading
    # one as the other is finding 103 in a new place.
    lives_of = {(digits(r["hs_code"]), r["first_period"]): r for r in inventory}
    spans_per_family = Counter(written.values())
    wrong_flow, wrong_life, wrong_count = [], [], []
    for r in built:
        if r["flow"] != flow:
            wrong_flow.append(r["record_id"])
        life = lives_of.get((digits(r["hs_code"]), r["first_period"]))
        if (life is None or r["description"] != life["description"]
                or r["last_period"] != life["last_period"]):
            wrong_life.append(r["record_id"])
        if int(r["family_commodities"] or -1) != spans_per_family[r["family_id"]]:
            wrong_count.append(r["family_id"])
    record("%s: every row names the flow of the file it is written to" % flow, not wrong_flow,
           "%d row(s) disagree" % len(wrong_flow))
    record("%s: each row's wording and last month are the inventory life's" % flow,
           not wrong_life, "%d row(s) rebuilt from the inventory, %d disagree"
           % (len(built), len(wrong_life)))
    record("%s: family_commodities counts the spans this check rebuilt, not the codes" % flow,
           not wrong_count,
           "%d families; %d hold more spans than codes"
           % (len(spans_per_family),
              sum(1 for r in built
                  if int(r["family_commodities"]) > int(r["family_size"])))
           if not wrong_count else "%d disagree: %s" % (len(set(wrong_count)),
                                                        sorted(set(wrong_count))[:3]))

    # The record identifier and Stage 3's key are two renderings of one fact and must stay so.
    pairs = {(r["record_id"], r["span_id"]) for r in built}
    record("%s: the record identifier and Stage 3's key are one-to-one" % flow,
           len({p[0] for p in pairs}) == len(pairs) == len({p[1] for p in pairs})
           and {r["span_id"] for r in built} == {r["span_id"] for r in routed},
           "%d pair(s), and the span_ids are exactly Stage 3's" % len(pairs))
    # SPELLED OUT HERE RATHER THAN ASKED OF THE PRODUCER. Finding 132, 2026-08-18. The R suffix is
    # the load-bearing part and was missing for a day; a control that asks the constructor whether
    # the constructor is right would not have noticed, because both sides would have dropped it
    # together. Written out from METHOD_family_id.md: the flow prefix, R, the bare code, the first
    # month as YYYYMM, joined by hyphens.
    def _record_id_independently(row):
        return "%s-%s-%s" % (prefix + "R", digits(row["hs_code"]), row["first_period"])
    mismatched = [r["record_id"] for r in built if r["record_id"] != _record_id_independently(r)]
    _producer_agrees = [r["record_id"] for r in built
                        if r["record_id"] != stage.record_id_for(prefix, digits(r["hs_code"]),
                                                                 r["first_period"])]
    record("%s: the independent rebuild and the producer still agree" % flow,
           not _producer_agrees,
           "if this ever parts from the control below, one of the two definitions moved alone")
    record("%s: the record identifier re-derives from the code and its first month" % flow,
           not mismatched, "%d identifier(s), none depending on anything else" % len(built))

    # A RECORD IDENTIFIER AND A FAMILY IDENTIFIER MUST NEVER BE MISTAKEABLE FOR EACH OTHER.
    # They were, for one day. Without the `R` a record read `IM-30062000-198801` while its family
    # read `IM-30062000`, and that is not a corner case: a record whose own code is its family's
    # anchor sits in exactly that position, and 183 of 572 strings across the delivery do, which
    # is 127 imports plus 56 exports. It was 182 at commit 46adf21, 126 plus 56, under the
    # earlier scheme, and has been 183 at every commit since a8996cf. Re-measured 2026-08-18,
    # finding 139, together with the same figure in METHOD_family_id.md. Two
    # kinds of key separated only by a suffix is how a wrong join survives review. Asserted three
    # ways because the failure is a near-miss rather than a collision, and equality alone would
    # not have caught it.
    families = {r["family_id"] for r in built}
    records = {r["record_id"] for r in built}
    prefixed = [r["record_id"] for r in built if r["record_id"].startswith(r["family_id"] + "-")]
    record("%s: no record identifier can be read as its family's, plus a suffix" % flow,
           not (families & records) and not prefixed
           and all(r["record_id"].split("-")[0] != r["family_id"].split("-")[0] for r in built),
           "%d record and %d family identifier(s), disjoint, and neither prefixes the other"
           % (len(records), len(families))
           if not prefixed else "%d look like their own family: %s" % (len(prefixed), prefixed[:3]))

    # The display label. Emitted for tables, and nothing may join on it.
    numbers = {r["family_id"]: int(r["family_display_number"]) for r in built}
    ordered = sorted(numbers, key=lambda fid: numbers[fid])
    keyed = sorted(numbers, key=lambda fid: (
        [r for r in built if r["family_id"] == fid][0]["family_anchor_first_traded"],
        digits([r for r in built if r["family_id"] == fid][0]["family_anchor_code"])))
    record("%s: the display number is a clean 1..N ordered by the anchor's first month" % flow,
           sorted(numbers.values()) == list(range(1, len(numbers) + 1)) and ordered == keyed,
           "%d families numbered 1..%d" % (len(numbers), len(numbers)))

    sizes = Counter(int(r["family_size"]) for r in
                    {r["family_id"]: r for r in built}.values())
    record("%s: the family shape is unchanged" % flow,
           len(set(r["family_id"] for r in built)) == expect["families"]
           and sizes.get(1, 0) == expect["singletons"] and max(sizes) == expect["largest"]
           and len({digits(r["hs_code"]) for r in built}) == expect["codes"],
           "%d families over %d codes, %d singleton(s), largest %d"
           % (len(set(r["family_id"] for r in built)),
              len({digits(r["hs_code"]) for r in built}), sizes.get(1, 0), max(sizes)))
    biggest = max(({r["family_id"]: int(r["family_size"]) for r in built}).items(),
                  key=lambda kv: kv[1])
    # TIE-AWARE, because on exports it IS a tie. EX-30023100-198801 and EX-30029010-198801 both
    # hold 6 codes, and `max()` picked different ones in the stage and in this check purely on
    # iteration order. Asserting one name would have pinned an arbitrary winner, which is the
    # positional-identifier mistake in miniature.
    largest = {fid: n for fid, n in
               {r["family_id"]: int(r["family_size"]) for r in built}.items()
               if n == biggest[1]}
    record("%s: the largest family is the size and one of the names expected" % flow,
           biggest[1] == expect["largest"] and expect["anchor"] in largest,
           "%d code(s), largest famil%s %s"
           % (biggest[1], "y is" if len(largest) == 1 else "ies are", sorted(largest)))

# Rule 8: what this check cannot do, said rather than implied.
disclose("this check cannot judge whether two codes belong together",
         "that is the crosswalk's claim and Stage 2 settled it row by row; grouping a wrong link "
         "correctly still groups a wrong link")

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if notes:
    print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("Stage 4 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 4 is validated. Every family is a closure of settled links, and every name is earned.")
