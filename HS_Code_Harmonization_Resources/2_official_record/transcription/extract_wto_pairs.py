"""Extract the WCO correlation pairs that touch Chapter 30 from the five boundary PDFs.


    python evidence/wto/extract_wto_pairs.py

Writes evidence/wto/wto_ch30_pairs.csv, and evidence/wto/wto_ch30_extraction_report.txt.


THIS IS NOT A PIPELINE STAGE, AND THE RELEASE BUILD MUST NEVER IMPORT IT
------------------------------------------------------------------------
It needs `pdfplumber`. Nothing under pipeline/ or checks/ imports a third-party package and
nothing may start: the release build is standard library only, and a control asserts it. This
script sits beside the documents it reads, is run by hand when the evidence changes, and its
OUTPUT is the checked-in artefact. That is exactly how evidence/cbsa/*.csv already works: a PDF
extracted once, the CSV committed, the pipeline reading only the CSV.


WHY THIS EXISTS WHEN TWO EXTRACTIONS ALREADY DID
-------------------------------------------------
`inspire2/work/wto_ch30_pairs.csv` and `pharma/bridge/wto_all_pairs.csv` both exist and they
DISAGREE, on four of the five boundaries. Reconciled on 2026-08-14 for 2017 to 2022: the v1 file
is a strict subset, 24 pairs against 39, missing 15 and holding none the other lacks. Every
missing pair is cross-chapter, because v1 filtered by Chapter-30 PAGES rather than by code, so a
pair sitting on a chapter-38 page was discarded at parse time.

That filter threw away the most consequential evidence in the document. Among the 15 lost pairs
are 3002.11, 3002.13, 3002.14 and 3002.15 correlating with 3822.11, 3822.12 and 3822.19, which
is HS2022 moving diagnostic goods OUT of Chapter 30 under new exclusion Note 1 (ij). A crosswalk
that cannot see goods leaving the chapter cannot say a code has no successor in it.

The pharma file is sound on that boundary but is not this project's evidence: it lives in another
repository, its extractor carries a path that no longer exists, and its `remarks` column is
mis-attributed (see below). Principle 7 says a run-time input belongs inside inspire2_v2.


HOW THE DOCUMENTS ARE STRUCTURED, MEASURED RATHER THAN ASSUMED
---------------------------------------------------------------
Each PDF holds two tables and they say the same thing twice, in opposite directions:

    TABLE I    left column = the NEW version, middle = the OLD version, right = Remarks
    TABLE II   left column = the OLD version, right = the NEW version, no remarks

Both are extracted and normalised to old -> new, so every pair should appear from both tables.
Where they disagree, that is reported rather than silently merged: the document contradicting
itself is a finding, not a parsing detail to smooth over.

The section headers are NOT consistent across the five documents and matching on them
under-counts. 2012-to-2017 writes its Table II header `HS2012 HS2017` with no "Version", and
1996-to-2002 writes `1996 VERSION 2002 VERSION` in capitals. A first attempt keyed on the word
"Version" found no Table II at all in 2012-to-2017, which is 16 pages and 6 held rows. So the
sections are segmented on the standalone `TABLE I` / `TABLE II` markers, which every document
carries, and the per-page column header is used only to locate the columns on the page.

2012-to-2017 additionally carries `TABLE I - ANNEX` and `TABLE II - ANNEX`. They are captured
under their own section names and are not mixed into the main tables.


WHY THE REMARKS ARE ATTACHED TO A BLOCK AND NOT TO A ROW
---------------------------------------------------------
The Remarks column is a flowing paragraph beside a group of codes, not a cell per row. Attaching
it per row is what makes pharma's file read "3001.10 -> 3001.10, Waste pharmaceuticals have been
defined in", which is a sentence about 3006.80 stapled to an unrelated pair. Here a remark is
recorded against the BLOCK it sits beside, and the column is named so, because a block is the
finest unit the document actually supports.
"""

import csv
import os
import re
import sys
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    raise SystemExit("This evidence script needs pdfplumber. The pipeline does not, and must "
                     "not: install it here, run this by hand, and commit the CSV.")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "wto_ch30_pairs.csv")
OUT_REPORT = os.path.join(HERE, "wto_ch30_extraction_report.txt")
# Kept in its own file rather than as rows in the pairs CSV. A statement has no counterpart, so
# it would have to sit there with an empty destination column, and load_correlations() in
# stage1b counts how many times an old subheading appears to decide whether it moved WHOLLY to
# one place. An empty-destination row would make a clean correlation look like a split.
OUT_STATEMENTS = os.path.join(HERE, "wto_ch30_statements.csv")

PDFS = [
    ("WTO_HSCodes_1996_to_2002.pdf", "1996", "2002"),
    ("WTO_HSCodes_2002_to_2007.pdf", "2002", "2007"),
    ("WTO_HSCodes_2007_to_2012.pdf", "2007", "2012"),
    ("WTO_HSCodes_2012_to_2017.pdf", "2012", "2017"),
    ("WTO_HSCodes_2017_to_2022.pdf", "2017", "2022"),
]

CODE = re.compile(r"^(ex)?(\d{4}\.\d{2})$", re.I)

# A subheading the document addresses in PROSE, with no counterpart in the other column. Table I
# prints it in brackets, "(3002.19)"; Table II prints it bare and lets the remark run on. Both
# mean the same thing: this subheading was deleted and the correlation names nothing it went to.
# Kept apart from CODE so a bracketed entry can never be read as half of a pair.
STATEMENT_CODE = re.compile(r"^\(?(\d{4}\.\d{2})\)?$")
# ANYTHING that looks like a heading or a subheading, however it is marked. Used ONLY to stop a
# wrapped statement, and deliberately looser than both patterns above: "30.04" is a heading and
# "ex3006.93" carries a prefix, so neither matches those, and a continuation rule keyed on them
# ran straight through the next data block and filed "30.04 ex3006.93 Applicable subheadings" as
# part of what the HS Committee said about 3002.19.
ANY_CODEISH = re.compile(r"\d{2,4}\.\d{2}")
# Trailing punctuation, stripped before a token is tested. Where several old codes share one
# line Table I separates them with commas, so the first token reads "ex1704.90," and an anchored
# match rejects it. That silently dropped the entire origin list of new subheading 3006.93,
# which is where placebos and blinded clinical trial kits come from, including 3002.19.
TRAILING = ",.;:"


def as_code(text):
    return CODE.match((text or "").strip().rstrip(TRAILING))
# A SECTION MARKER IS "TABLE I" ENDING THERE, OR FOLLOWED BY A DASHED SUBTITLE. Nothing else.
# The first version required the line to end at the numeral, which matched the bare "TABLE I"
# headings in three documents and MISSED both markers in the other two, where they read
# "Table I - Correlating the 2002 version" and "TABLE II - CORRELATING THE 2002 VERSION".
# Those two PDFs then produced no sections and no rows at all, silently. Requiring a dash also
# keeps the prose out: the introductions say "Table I establishes...", "Table II contains...",
# "Table I comprises...", "Table I, i.e., to indicate...", none of which is a heading.
SECTION = re.compile(r"^TABLE\s+(I{1,2})\s*(?:[-–—]\s*(?P<subtitle>.*))?$", re.I)
ANNEX = re.compile(r"ANNEX", re.I)
CHAPTER_30 = "30"

STATEMENT_COLUMNS = ["boundary_from", "boundary_to", "section", "page_index", "page_label",
                     "code", "code_is", "statement", "source_pdf"]

COLUMNS = ["boundary_from", "boundary_to", "section", "page_index", "page_label",
           "block", "old_code", "old_ex", "new_code", "new_ex", "block_remark",
           "source_pdf"]


def page_label(page):
    """The document's own page number, e.g. '- 30 -' or 'Page 35'. Recorded, not computed."""
    for line in (page.extract_text() or "").splitlines()[:3]:
        found = re.search(r"^[-–]\s*(\d+)\s*[-–]$|^Page\s+(\d+)$", line.strip())
        if found:
            return found.group(1) or found.group(2)
    return ""


def sections_of(pdf):
    """Map every page index to the table section it belongs to, by the standalone markers."""
    marks = []
    for index, page in enumerate(pdf.pages):
        for line in (page.extract_text() or "").splitlines():
            text = re.sub(r"\s+", " ", line.strip())
            match = SECTION.match(text)
            if match:
                name = "TABLE_%s%s" % (match.group(1).upper(),
                                       "_ANNEX" if ANNEX.search(text) else "")
                marks.append((index, name))
    marks.sort()
    assigned = {}
    for position, (index, name) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(pdf.pages)
        for page_index in range(index, end):
            assigned[page_index] = name
    return assigned


def lines_of(page):
    """Words grouped into visual lines, each word keeping its x position."""
    rows = defaultdict(list)
    for word in page.extract_words():
        rows[round(word["top"] / 3.0)].append(word)
    return [sorted(words, key=lambda w: w["x0"]) for _key, words in sorted(rows.items())]


def column_anchors(page, section):
    """Where the two code columns sit on THIS page, and where the remarks begin.

    DERIVED FROM THE CODE TOKENS, NOT FROM THE COLUMN HEADER, and that distinction is the whole
    reason this function is long. The header word "Remarks" is set at x=365 on a page whose
    remarks PARAGRAPH begins at x=255. Anchoring the boundary on the header therefore left a
    110pt strip of prose on the code side, and the prose is full of code-shaped tokens: the
    remark beside 3002.11 names 3002.10, 3002.12 and 3002.15 in a sentence. Those were being
    read as correlation entries, which produced impossible pairs such as 3002.15 -> 3002.12 at a
    boundary where 3002.15 did not yet exist.

    The columns are the two LEFTMOST clusters of code tokens, which is a property of the layout
    rather than of the typography. Everything right of the second cluster is remarks.
    """
    codes = sorted(round(w["x0"]) for words in lines_of(page) for w in words
                   if as_code(w["text"]))
    if not codes:
        return []
    clusters, current = [], [codes[0]]
    for value in codes[1:]:
        if value - current[-1] < 30:
            current.append(value)
        else:
            clusters.append(current)
            current = [value]
    clusters.append(current)
    if len(clusters) < 2:
        return []
    left, right = clusters[0], clusters[1]
    # A margin past the right-hand column's widest token, so a code sitting in prose cannot be
    # mistaken for one sitting in the column. Table II has no remarks and simply never uses it.
    remark_x = max(right) + 25
    return [min(left), min(right), remark_x]


def parse_page(page, section, anchors):
    """Blocks of (left codes, right codes, remark), and statements, in page order.

    A STATEMENT IS A SUBHEADING THE DOCUMENT ADDRESSES AND GIVES NO DESTINATION FOR, and it is
    returned separately because it is not half of anything. Finding 101: the guard below correctly
    refuses to let a prose line start a data block, which is what stopped the parser inventing
    `3002.19 -> 3006.93`, but it also discarded the code sitting on that line. The result was a
    pairs file with no trace of 3002.19 at the 2017-to-2022 boundary, while the document says of it,
    on both tables, "This subheading was considered by the HS Committee to be empty and it was
    therefore deleted". Two rows worth CAD 1,636,154,203 turn on that sentence and it was reachable
    only by opening the PDF.
    """
    if len(anchors) < 2:
        return [], []
    left_x, right_x = anchors[0], anchors[1]
    remark_x = anchors[2] if len(anchors) > 2 else None
    midpoint = (left_x + right_x) / 2.0
    blocks, current, statements, open_statement = [], None, [], None

    for words in lines_of(page):
        # A DATA ROW HOLDS NOTHING BUT CODES IN THE COLUMN ZONE. A FOOTNOTE HOLDS PROSE THERE.
        #
        # This is the only reliable separator, and it had to be found the hard way. The font size
        # is identical, 8.04 for both. Without it the footnote on Table II page 29,
        # "3002.19 This subheading was considered by the HS Committee to be empty and it was
        # therefore deleted", started a block, and an ex3006.93 from a later line attached to it.
        # The extraction then asserted, on WCO authority, that 3002.19 correlates to 3006.93.
        # The document says the opposite: the subheading was EMPTY, so it transferred nothing.
        # Two held retirements sit on 3002.19, and a false official answer is far worse for them
        # than no answer at all.
        zone = [w for w in words if remark_x is None or w["x0"] < remark_x - 8]
        if any(not as_code(w["text"]) for w in zone):
            # Rejected as a data row, and rightly. But before dropping it, ask whether the column
            # zone holds a subheading the document is speaking ABOUT. Exactly one code and some
            # prose beside it is the shape of a deletion notice; two codes would be a data row
            # this parser has misread and is not claimed as a statement.
            coded = [w for w in zone if STATEMENT_CODE.match(w["text"])]
            prose = [w["text"] for w in words if not STATEMENT_CODE.match(w["text"])]
            if len(coded) == 1 and prose:
                digits_only = STATEMENT_CODE.match(coded[0]["text"]).group(1)
                if digits_only.startswith(CHAPTER_30):
                    statements.append({
                        "code": digits_only,
                        "side": "left" if coded[0]["x0"] < midpoint else "right",
                        "prose": list(prose),
                    })
                    open_statement = statements[-1]
            elif (open_statement is not None and prose and not coded
                  and not any(ANY_CODEISH.search(w["text"] or "") for w in words)):
                # A SENTENCE THAT WRAPS IS STILL ONE SENTENCE. Table II breaks this remark across
                # two lines and stopping at the first would file "This subheading was considered by
                # the HS" as the document's finding. Continuation is taken only while no line
                # carries a code, so the next data row closes it and no unrelated prose is drawn in.
                open_statement["prose"].extend(prose)
            if remark_x is not None:
                remark_words = [w["text"] for w in words if w["x0"] >= remark_x - 8]
                if current is not None and remark_words:
                    current["remark"].extend(remark_words)
            continue
        open_statement = None
        left, right, remark = [], [], []
        for word in words:
            match = as_code(word["text"])
            if remark_x is not None and word["x0"] >= remark_x - 8:
                remark.append(word["text"])
                continue
            if not match:
                continue
            (left if word["x0"] < midpoint else right).append(
                (match.group(1) or "", match.group(2)))
        if not left and not right and not remark:
            continue
        if left:
            current = {"left": [], "right": [], "remark": []}
            blocks.append(current)
        if current is None:
            continue
        current["left"].extend(left)
        current["right"].extend(right)
        current["remark"].extend(remark)
    return blocks, statements


def main():
    rows, statements, report = [], [], []
    for name, old_year, new_year in PDFS:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            raise SystemExit("missing evidence document: %s" % path)
        with pdfplumber.open(path) as pdf:
            assigned = sections_of(pdf)
            counts = defaultdict(int)
            for index, page in enumerate(pdf.pages):
                section = assigned.get(index)
                if section not in ("TABLE_I", "TABLE_II", "TABLE_I_ANNEX", "TABLE_II_ANNEX"):
                    continue
                anchors = column_anchors(page, section)
                label = page_label(page)
                page_blocks, page_statements = parse_page(page, section, anchors)
                table_one = (section.startswith("TABLE_I")
                             and not section.startswith("TABLE_II"))
                for statement in page_statements:
                    # Which column the code sat in says whether the document is speaking about an
                    # OLD subheading or a new one, and the two tables read in opposite directions.
                    is_old = (statement["side"] == "right") if table_one else (statement["side"] == "left")
                    statements.append({
                        "boundary_from": old_year, "boundary_to": new_year,
                        "section": section, "page_index": index, "page_label": label,
                        "code": statement["code"],
                        "code_is": "old" if is_old else "new",
                        "statement": re.sub(r"\s+", " ", " ".join(statement["prose"])).strip(),
                        "source_pdf": name,
                    })
                for number, block in enumerate(page_blocks, start=1):
                    # TABLE I reads new on the left; TABLE II reads old on the left.
                    if section.startswith("TABLE_I") and not section.startswith("TABLE_II"):
                        new_side, old_side = block["left"], block["right"]
                    else:
                        old_side, new_side = block["left"], block["right"]
                    remark = re.sub(r"\s+", " ", " ".join(block["remark"])).strip()
                    for old_ex, old_code in old_side:
                        for new_ex, new_code in new_side:
                            if not (old_code.startswith(CHAPTER_30)
                                    or new_code.startswith(CHAPTER_30)):
                                continue
                            counts[section] += 1
                            rows.append({
                                "boundary_from": old_year, "boundary_to": new_year,
                                "section": section, "page_index": index, "page_label": label,
                                "block": number,
                                "old_code": old_code, "old_ex": old_ex.lower(),
                                "new_code": new_code, "new_ex": new_ex.lower(),
                                "block_remark": remark, "source_pdf": name,
                            })
            report.append("%s: %s" % (name, dict(counts)))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with open(OUT_STATEMENTS, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATEMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(statements)

    # The two tables say the same thing twice. Compare them, and report rather than reconcile.
    lines = ["WCO correlation pairs touching Chapter 30, extracted %s" % os.path.basename(__file__),
             "", "Per document and section:"]
    lines += ["  " + r for r in report]
    lines += ["", "Table I against Table II, per boundary. Both are normalised to old -> new,",
              "so a pair present in one and absent from the other is the document disagreeing",
              "with itself, or this parser failing on one of the two layouts.", ""]
    # KEYED ON THE CODES, NEVER ON THE `ex` MARKER. `ex` means "part of", and each table prints
    # it on the column it is describing: Table I marks the OLD side partial, Table II marks the
    # NEW side. So the same fact is written `3002.11 -> 3822.11` in one and
    # `3002.11 -> ex3822.11` in the other. Comparing tuples that include the marker made every
    # pair look like a disagreement and reported 3 of 46 agreeing, which is an artefact of the
    # comparison and not of the document. The marker is still recorded per row; it is simply not
    # a join key.
    for _name, old_year, new_year in PDFS:
        def pairs(section_prefix):
            return {(r["old_code"], r["new_code"]) for r in rows
                    if r["boundary_from"] == old_year and r["section"] == section_prefix}
        one, two = pairs("TABLE_I"), pairs("TABLE_II")
        lines.append("  %s -> %s   Table I %3d   Table II %3d   both %3d   only I %2d   only II %2d"
                     % (old_year, new_year, len(one), len(two), len(one & two),
                        len(one - two), len(two - one)))
        for side, label in ((one - two, "only in Table I"), (two - one, "only in Table II")):
            for c1, c2 in sorted(side)[:8]:
                lines.append("        %-16s %-8s -> %s" % (label, c1, c2))
    lines += ["", "Subheadings the documents ADDRESS but give no destination for. These are not",
              "pairs and are written to wto_ch30_statements.csv, never to the pairs file.", ""]
    for st in statements:
        lines.append("  %s -> %s  %-12s %-8s (%s)  %s"
                     % (st["boundary_from"], st["boundary_to"], st["section"], st["code"],
                        st["code_is"], st["statement"][:88]))
    with open(OUT_REPORT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print()
    print("written: %s  (%d row(s))" % (os.path.relpath(OUT_CSV, HERE), len(rows)))
    print("written: %s  (%d statement(s))"
          % (os.path.relpath(OUT_STATEMENTS, HERE), len(statements)))
    print("written: %s" % os.path.relpath(OUT_REPORT, HERE))


if __name__ == "__main__":
    main()
