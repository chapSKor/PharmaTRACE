"""
Check for Stage 3. Does every commodity carry the whole path it travelled, and only that path?


Inputs:
    work/stage3_routed_{imports,exports}.csv        produced by pipeline/stage3_route.py
    work/commodity_inventory_{imports,exports}.csv  produced by pipeline/stage0_read_source.py
    work/stage2_resolved_{imports,exports}.csv      produced by pipeline/stage2_apply_decisions.py

Output:
    A pass or fail line per control, and a non-zero exit code if any control fails.


THE ONE QUESTION THIS CHECK ANSWERS
-----------------------------------
Is every journey composed only of edges Stage 2 settled, and does every commodity string in the
delivery have exactly one journey that terminates?

It does NOT ask whether a successor is the right one. Stage 2 owns that and records it; walking a
wrong edge correctly is still walking a wrong edge, and no control here can tell the difference.


WHY THE EDGES ARE RE-DERIVED FROM THE WRITTEN JOURNEY
-----------------------------------------------------
Convention 10. The journey is a string, and the next stage will read it as one. So the controls
below split that string back into hops and check each hop against Stage 2, rather than trusting
the counters the stage wrote beside it. A row whose `journey` and whose `succession_hops`
disagree is exactly the shape that made `review_flag` unusable in Stage 1c while thirteen
controls passed.
"""

import csv
import os
import sys
from collections import Counter, defaultdict

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage3_route as stage  # noqa: E402

FLOWS = ("imports", "exports")
WORK = os.path.join(PROJECT, "work")

# Measured 2026-08-15 on the first build of this stage, reconciled before being pinned. The
# imports "1 code" figure of 160 is worth keeping in view: the v1 released journeys report the
# same 160, and those are the strings that never moved, which no adjudication can change. It is
# the one number here that agrees with the release by construction rather than by luck.
EXPECTED = {
    # rewordings 209 -> 208 on 2026-08-17, and the direction is the point. Stage 1a now ends a
    # span where a relabel crosses a decisive distinction, so imports 3004.50.99.30's move from
    # "for vet use" to "for human use" is no longer a re-wording the journey walks through. It is
    # a boundary the journey stops at, and the veterinary record stops inheriting the human
    # terminal it used to reach. One re-wording became one succession.
    "imports": {"rows": 475, "value": 415669236806.0,
                "active": 453, "left_chapter": 8, "not_a_retirement": 14,
                "single_code": 160, "rewordings": 208},
    # RE-PINNED 2026-08-31 when the export flow moved from domestic_exports.db to exports.db
    # on the analyst's instruction. The figure moved because re-exports are now counted;
    # it did not break. Imports are untouched and their pins did not move.
    "exports": {"rows": 97, "value": 216729045491.0,
                "active": 86, "left_chapter": 2, "not_a_retirement": 9,
                "single_code": 64, "rewordings": 47},
}

results = []
notes = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, "  -- " + detail if detail else ""))


def disclose(name, detail=""):
    """Something stated rather than tested, printed and counted apart so the control total
    means what it says. Convention 8."""
    notes.append((name, detail))
    print("  [NOTE] %s%s" % (name, "  -- " + detail if detail else ""))


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digits(text):
    return "".join(c for c in (text or "") if c.isdigit())


print("Check for Stage 3. Does every commodity carry the whole path it travelled?")
print()
print("Controls that MUST FAIL (a guard that cannot fire is not a guard):")

# Synthetic, because the delivery contains none of these shapes. A refusal never exercised is an
# assumption wearing a function's clothes.
def span(code, first, last, value="100.00", description="a commodity"):
    return {"hs_code": code, "first_period": first, "last_period": last,
            "total_value_cad": value, "description": description}


def resolved_row(flow, code, last, outcome="succeeded", successor=""):
    return {"link_id": stage.link_id_for(flow, code, last), "outcome": outcome,
            "successor": successor}


# 1. An edge Stage 2 left open. The delivery has none, because Stage 2 now closes every row, and
#    that is exactly why this must be provoked rather than observed.
_inv = [span("3002190000", "201701", "202112"), span("3002900090", "202201", "202606")]
_res = {}
_rows, _problems = stage.route("imports", _inv, _res, "202606")
record("a stoppage Stage 2 never settled is refused",
       bool(_problems["unsettled"]) and len(_rows) == 1,
       "a chain cannot be walked through a row that is still open")

# 2. Held, unresolved: settled in the sheet but not into a link. Same refusal, different cause,
#    and worth its own provocation because the outcome word differs.
_res = {stage.link_id_for("imports", "3002190000", "202112"):
        resolved_row("imports", "3002190000", "202112", outcome="held")}
record("a stoppage that resolved to `held` is refused",
       bool(stage.route("imports", _inv, _res, "202606")[1]["unsettled"]),
       "held is not an answer and cannot be an edge")

# 3. A successor whose only life closed before the predecessor stopped.
_inv3 = [span("3002190000", "201701", "202112"), span("3002150000", "199801", "201612")]
_res3 = {stage.link_id_for("imports", "3002190000", "202112"):
         resolved_row("imports", "3002190000", "202112", successor="3002.15.00.00")}
record("a successor with no life open after the predecessor stopped is refused",
       bool(stage.route("imports", _inv3, _res3, "202606")[1]["stranded"]),
       "the trade would have nowhere to land")

# 4. THE CYCLE REFUSAL CANNOT BE PROVOKED, AND SAYING SO IS THE POINT.
#
# Two codes naming each other is the obvious attempt and it does not reach the loop: `route` only
# ever lands on a span still open AFTER the predecessor stopped, so every hop moves strictly
# forward in time and a walk cannot return to where it has been. Giving each of two codes the
# other as successor produces `stranded`, not `cycle`, because neither outlives the other.
#
# Convention 1 says a guard that cannot fire is not a guard, and the honest response is to state
# the property that makes it unreachable rather than to keep a control that will pass forever.
# The refusal stays in the stage as a backstop costing nothing, and the monotonic rule it depends
# on is ASSERTED below, over the whole delivery. If a later change ever lets a hop land on a span
# that closed earlier, that control fails and the cycle becomes reachable in the same moment.
_inv4 = [span("3002190000", "201701", "202112"), span("3002150000", "201701", "202112")]
_res4 = {stage.link_id_for("imports", "3002190000", "202112"):
         resolved_row("imports", "3002190000", "202112", successor="3002.15.00.00"),
         stage.link_id_for("imports", "3002150000", "202112"):
         resolved_row("imports", "3002150000", "202112", successor="3002.19.00.00")}
_mutual = stage.route("imports", _inv4, _res4, "202606")[1]
disclose("the cycle refusal cannot be provoked and is a backstop, not a control",
         "two codes naming each other resolve to `stranded` rather than `cycle`, because a hop "
         "only ever lands on a span open after the predecessor stopped: %s"
         % ("stranded" if _mutual["stranded"] else "NOT stranded, which would be a finding"))

# And the converse, so the guards are not simply refusing everything put to them.
_inv5 = [span("3002190000", "201701", "202112"), span("3002900090", "202201", "202606")]
_res5 = {stage.link_id_for("imports", "3002190000", "202112"):
         resolved_row("imports", "3002190000", "202112", successor="3002.90.00.90")}
_good, _clean = stage.route("imports", _inv5, _res5, "202606")
record("a settled one-hop succession routes without complaint",
       not any(_clean.values()) and len(_good) == 2
       and _good[0]["journey"] == "3002.19.00.00 -> 3002.90.00.90"
       and _good[0]["terminal_status"] == stage.ACTIVE,
       "journey=%r" % _good[0]["journey"])

print()
print("Controls that MUST PASS (correct input must not be flagged):")

for flow in FLOWS:
    expect = EXPECTED[flow]
    routed = load(os.path.join(WORK, "stage3_routed_%s.csv" % flow))
    inventory = load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow))
    resolved = {r["link_id"]: r for r in load(os.path.join(WORK, "stage2_resolved_%s.csv" % flow))}
    delivery_end = max(r["last_period"] for r in inventory)

    # Rebuilt from the inventory, per rule 2, without calling the stage.
    expected_ids = {stage.span_id_for(flow, r["hs_code"], r["first_period"])
                    for r in inventory}
    got_ids = {r["span_id"] for r in routed}
    record("%s: every commodity string is routed exactly once" % flow,
           got_ids == expected_ids and len(routed) == len(expected_ids) == expect["rows"],
           "%d routed, %d in the inventory, %d differing"
           % (len(routed), len(expected_ids), len(got_ids ^ expected_ids)))

    # THE FIVE COLUMNS NO CONTROL READ. Finding 114. Overwriting flow, description, last_period,
    # terminal_description or terminal_first_period on every row of this artefact, with garbage or
    # with blank, left the whole suite green. Each is rebuilt here from the inventory, which is the
    # only place any of them can be checked against: the stage copies them across and a copy is not
    # evidence. terminal_* are read from the life the journey actually ends in, not from the code's
    # last life, because that distinction is finding 102 and it must not be reintroduced here.
    lives_by_code = defaultdict(list)
    for r in inventory:
        lives_by_code[digits(r["hs_code"])].append(r)
    for held in lives_by_code.values():
        held.sort(key=lambda s: s["first_period"])

    def life_at(code, month):
        """The life of `code` that is open in `month`, or the last one that closed before it."""
        held = lives_by_code.get(digits(code)) or []
        open_then = [s for s in held if s["first_period"] <= month <= s["last_period"]]
        if open_then:
            return open_then[0]
        earlier = [s for s in held if s["first_period"] <= month]
        return earlier[-1] if earlier else None

    wrong_flow, wrong_start, wrong_terminal = [], [], []
    for r in routed:
        if r["flow"] != flow:
            wrong_flow.append(r["span_id"])
        start = life_at(r["hs_code"], r["first_period"])
        if (start is None or r["description"] != start["description"]
                or r["last_period"] != start["last_period"]):
            wrong_start.append(r["span_id"])
        end = life_at(r["terminal_code"], r["terminal_last_period"])
        if (end is None or r["terminal_description"] != end["description"]
                or r["terminal_first_period"] != end["first_period"]):
            wrong_terminal.append(r["span_id"])
    record("%s: every row names the flow of the file it is written to" % flow, not wrong_flow,
           "%d row(s) disagree" % len(wrong_flow))
    record("%s: the starting life's wording and last month are the inventory's" % flow,
           not wrong_start, "%d row(s) rebuilt, %d disagree"
           % (len(routed), len(wrong_start)))
    record("%s: the terminal life's wording and first month are the inventory's" % flow,
           not wrong_terminal, "%d row(s) rebuilt, %d disagree"
           % (len(routed), len(wrong_terminal)))

    value = sum(float(r["value_cad"]) for r in routed)
    independent = sum(float(r["total_value_cad"]) for r in inventory)
    record("%s: the value reconciles to the cent" % flow,
           abs(value - expect["value"]) < 0.005 and abs(value - independent) < 0.005,
           "CAD {:,.2f}".format(value))

    ends = Counter(r["terminal_status"] for r in routed)
    record("%s: the journeys end where they are expected to" % flow,
           all(ends.get(k, 0) == expect[k]
               for k in (stage.ACTIVE, stage.LEFT_CHAPTER, stage.NOT_A_RETIREMENT))
           and sum(ends.values()) == expect["rows"],
           "%s" % dict(ends))

    # RULE 10. The journey string is what the next stage reads, so every claim is re-derived from
    # it rather than from the counters written beside it.
    bad_shape, bad_edge, revisits, bad_ends = [], [], [], []
    for r in routed:
        codes = [digits(c) for c in r["journey"].split(" -> ")]
        if (codes[0] != digits(r["hs_code"]) or codes[-1] != digits(r["terminal_code"])
                or len(codes) != int(r["codes_in_journey"])
                or len(codes) != int(r["succession_hops"]) + 1):
            bad_shape.append(r["span_id"])
        if len(set(codes)) != len(codes):
            revisits.append(r["span_id"])
        for step in range(len(codes) - 1):
            edges = [a for a in resolved.values()
                     if digits(a["retiring_code"]) == codes[step]
                     and digits(a["successor"]) == codes[step + 1]
                     and a["outcome"] == "succeeded"]
            if not edges:
                bad_edge.append("%s: %s -> %s" % (r["span_id"], codes[step], codes[step + 1]))
        if r["terminal_status"] == stage.ACTIVE and r["terminal_last_period"] != delivery_end:
            bad_ends.append(r["span_id"])
    record("%s: the journey string agrees with every count beside it" % flow, not bad_shape,
           "first code, last code, length and hop count all re-derived from the string"
           if not bad_shape else "%d disagree: %s" % (len(bad_shape), bad_shape[:3]))
    record("%s: no journey passes through a code twice" % flow, not revisits,
           "%d row(s) revisit" % len(revisits))
    record("%s: every hop in every journey is a succession Stage 2 settled" % flow, not bad_edge,
           "%d hop(s) rebuilt against stage2_resolved_%s.csv, none unmatched"
           % (sum(int(r["succession_hops"]) for r in routed), flow)
           if not bad_edge else "%d unmatched: %s" % (len(bad_edge), bad_edge[:3]))
    record("%s: a journey called active really ends in the delivery's last month" % flow,
           not bad_ends, "delivery ends %s" % delivery_end)

    # Nothing Stage 2 decided may go unused. A link nobody travels is a link that changes no
    # family, and would mean an answer was written and then quietly dropped.
    travelled = set()
    for r in routed:
        codes = [digits(c) for c in r["journey"].split(" -> ")]
        travelled.update(zip(codes, codes[1:]))
    settled = {(digits(a["retiring_code"]), digits(a["successor"]))
               for a in resolved.values() if a["outcome"] == "succeeded"}
    record("%s: every succession Stage 2 settled is travelled by some journey" % flow,
           not (settled - travelled),
           "%d settled succession(s), all reached"
           % len(settled) if not (settled - travelled)
           else "%d never travelled: %s" % (len(settled - travelled),
                                            sorted(settled - travelled)[:3]))

    # THE PROPERTY THAT MAKES A CYCLE IMPOSSIBLE, asserted over the whole delivery rather than
    # provoked, because it cannot be provoked. Rebuilt from the inventory without calling the
    # stage: for every settled succession, the life the trade lands in must close strictly LATER
    # than the one it left. Monotonic time is the whole of the argument.
    lives = defaultdict(list)
    for r in inventory:
        lives[r["hs_code"]].append(r)
    backwards = []
    for answer in resolved.values():
        if answer["outcome"] != "succeeded":
            continue
        stopped = answer["last_period"]
        landing = [s for s in lives.get(digits(answer["successor"]), [])
                   if s["last_period"] > stopped]
        if not landing:
            backwards.append(answer["link_id"])
        elif min(landing, key=lambda s: s["first_period"])["last_period"] <= stopped:
            backwards.append(answer["link_id"])
    record("%s: every hop lands on a life that closes later than the one it left" % flow,
           not backwards,
           "%d succession(s) checked; monotonic time is why no journey can loop"
           % sum(1 for a in resolved.values() if a["outcome"] == "succeeded")
           if not backwards else "%d go backwards: %s" % (len(backwards), backwards[:3]))

    # THE IDENTIFIER IS A FUNCTION OF THE COMMODITY STRING ALONE. `METHOD_family_id.md` requires
    # this of every identifier the crosswalk publishes, and an untested claim is an assertion.
    # Re-derived from the three fields it is allowed to depend on, read back off the written file.
    # SPELLED OUT HERE RATHER THAN ASKED OF THE PRODUCER. Finding 132, 2026-08-18.
    #
    # This used to call stage.span_id_for, the same function Stage 3 used to write the file, so a
    # wrong constructor agreed with itself and the control passed. It proved only that nobody had
    # edited the file after the stage ran, which is not what its name claims. The form is written
    # out from METHOD_family_id.md instead: flow, colon, the dotted code, colon, the first month
    # as YYYY-MM. If the constructor is changed, this has to be changed deliberately beside it.
    def _span_id_independently(row):
        code = digits(row["hs_code"])
        dotted = row["hs_code"]
        first = row["first_period"]
        return "%s:%s:%s-%s" % (row["flow"], dotted, first[:4], first[4:])
    forged = [r["span_id"] for r in routed if r["span_id"] != _span_id_independently(r)]
    _agrees_with_producer = [r["span_id"] for r in routed
                             if r["span_id"] != stage.span_id_for(flow, digits(r["hs_code"]),
                                                                  r["first_period"])]
    record("%s: every identifier re-derives from the code and the month it first traded" % flow,
           not forged, "%d identifier(s), rebuilt from the fields rather than from the producer"
           % len(routed) if not forged else "%d disagree: %s" % (len(forged), forged[:3]))
    record("%s: the independent rebuild and the producer still agree" % flow,
           not _agrees_with_producer,
           "if this ever parts from the control above, one of the two definitions moved alone")
    # Two deliberately different input orders, neither of them the file's own. Random would make
    # the control unreproducible, which is a worse fault than the one it guards.
    stable = True
    for reordering in (lambda rs: list(reversed(rs)),
                       lambda rs: sorted(rs, key=lambda r: (r["description"], r["hs_code"]))):
        shuffled, _ = stage.route(flow, reordering(inventory), resolved, delivery_end)
        if ({r["span_id"]: r["journey"] for r in shuffled}
                != {r["span_id"]: r["journey"] for r in routed}):
            stable = False
    record("%s: shuffling the input changes no identifier and no journey" % flow, stable,
           "routed again from reversed order and from description order, both identical")
    # The defect this replaced, kept as a control so it cannot come back: a delivery-end month in
    # the key renumbered 26 per cent of the crosswalk every time the data was extended.
    moving = [r["span_id"] for r in routed
              if r["span_id"].endswith(delivery_end[:4] + "-" + delivery_end[4:])
              and r["first_period"] != delivery_end]
    record("%s: no identifier carries a month that moves when the delivery grows" % flow,
           not moving, "the key holds the FIRST month, which the delivery fixes")

    record("%s: the strings that never moved are unchanged" % flow,
           sum(1 for r in routed if int(r["codes_in_journey"]) == 1) == expect["single_code"],
           "%d string(s) route to themselves, expected %d"
           % (sum(1 for r in routed if int(r["codes_in_journey"]) == 1), expect["single_code"]))
    record("%s: re-wordings are passed through and never counted as successions" % flow,
           sum(int(r["rewordings_passed"]) for r in routed) == expect["rewordings"],
           "%d re-wording(s) crossed, adding no code to any journey"
           % sum(int(r["rewordings_passed"]) for r in routed))

# WHERE STAGE 3's receiving_span IS MORE PERMISSIVE THAN STAGE 1a's, NAMED. Finding 127, 2026-08-18.
#
# The two functions share a name and apply different rules: Stage 1a also requires the life to
# have begun within the continuity grace window, Stage 3 does not. That is correct, because Stage
# 3 routes a successor a person already chose and the analyst may knowingly accept a gap the
# heuristic refuses. It is also invisible, and it was documented as the same rule until today.
#
# Every divergence must be a decision a person made. If one ever appears that the software chose
# by itself, the permissiveness has stopped being a deference to the analyst and become a hole.
sys.path.insert(0, os.path.join(PROJECT, "pipeline"))
import stage1_candidates as _s1  # noqa: E402
_diverged = []
for flow in ("imports", "exports"):
    _spans = {}
    for r in load(os.path.join(WORK, "commodity_inventory_%s.csv" % flow)):
        _spans.setdefault(r["hs_code"], []).append(r)
    _runs = {c: _s1.trading_spans(v) for c, v in _spans.items()}
    for r in load(os.path.join(WORK, "stage2_resolved_%s.csv" % flow)):
        if (r.get("outcome") or "") != "succeeded":
            continue
        _code = (r.get("successor") or "").replace(".", "")
        if _code not in _runs:
            continue
        _limit = _s1.add_months(_s1.next_period(r["last_period"]), _s1.CONTINUITY_GRACE_MONTHS)
        _alive = [sp for sp in _runs[_code] if sp[1] > r["last_period"]]
        if (min(_alive) if _alive else None) != _s1.receiving_span(_runs[_code], r["last_period"], _limit):
            _diverged.append((r["link_id"], r.get("authority")))
record("Stage 3 is only more permissive than Stage 1a where a person decided",
       len(_diverged) == 5 and all(a == "analyst" for _l, a in _diverged),
       "%d link(s) diverge, every one authority=analyst" % len(_diverged)
       if len(_diverged) == 5 and all(a == "analyst" for _l, a in _diverged)
       else "%d diverge: %s" % (len(_diverged), _diverged[:4]))

print()
failed = [name for name, passed, _ in results if not passed]
print("%d controls run, %d passed, %d failed." % (len(results), len(results) - len(failed), len(failed)))
if notes:
    print("%d disclosure(s) reported, which are stated rather than tested." % len(notes))
if failed:
    print()
    print("Stage 3 is NOT validated. Failing controls:")
    for name in failed:
        print("  - %s" % name)
    sys.exit(1)
print("Stage 3 is validated. Every commodity terminates, and every hop was settled in Stage 2.")
