"""
Read and rewrite a single-sheet workbook using nothing but the standard library.


WHY THIS EXISTS
---------------
The answer sheet is filled in by a person, and that person highlights rows as they work. A CSV
cannot hold a highlight, so the workbook became the file being worked in and the CSV became a
copy of it. Nothing in this project may depend on a third-party package, so the workbook is read
and written here directly. An .xlsx is a zip of XML documents, which is enough.

WHAT IT PROTECTS
----------------
**Highlights travel with the retirement, not with the row.** A rebuild reorders rows, so copying
cell formatting back by sheet position would move every highlight onto whichever retirement had
landed in that position. That is exactly the failure the link_id join was introduced to end, and
it would be worse here because a highlight is silent: nothing would report that it had moved.
So formatting is captured against link_id and reapplied against link_id.

**Everything not understood is preserved untouched.** styles.xml holds the fill definitions, the
theme holds the palette, and the sheet's own view settings hold frozen panes and column widths.
None of it is rewritten. Only the cell values are, and only in the one sheet.

WHAT IT DOES NOT DO
-------------------
It writes one sheet of text and numbers. No formulas, no merged cells, no charts, no second
sheet. If the workbook ever grows any of those they will be lost on the next rebuild, so a check
asserts the workbook still holds exactly one sheet and no formulas.
"""

import re
import shutil
import zipfile
from xml.etree import ElementTree as ET

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"m": MAIN}
SHEET = "xl/worksheets/sheet1.xml"


def _column_index(reference):
    letters = re.match(r"([A-Z]+)", reference).group(1)
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number - 1


def _column_letters(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _drop_foreign_attributes(node):
    """Strip attributes belonging to any namespace but the spreadsheet one, in place.

    Excel writes x14ac:dyDescent on sheetFormatPr and declares that prefix at the worksheet root
    behind mc:Ignorable. Carrying the attribute over without the declaration leaves a prefix
    nothing binds. It is a row-height hint and nothing reads it, so it goes rather than dragging
    two more namespace declarations into the sheet.
    """
    for name in [n for n in node.attrib if n.startswith("{") and not n.startswith("{%s}" % MAIN)]:
        del node.attrib[name]
    for child in node:
        _drop_foreign_attributes(child)


def read(path):
    """Every row of the first sheet, with the style id of each cell.

    Returns (columns, rows) where each row is a dict of column name to (value, style id). A cell
    the person never touched has a style id of None, which is preserved as such so an untouched
    cell is not given a style it never had.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in item.iter("{%s}t" % MAIN)))
        sheet = ET.fromstring(archive.read(SHEET))

    grid = {}
    for row in sheet.iter("{%s}row" % MAIN):
        cells = {}
        for cell in row.findall("m:c", NS):
            kind, value_node = cell.get("t"), cell.find("m:v", NS)
            if value_node is None:
                inline = cell.find("m:is", NS)
                value = ("".join(t.text or "" for t in inline.iter("{%s}t" % MAIN))
                         if inline is not None else "")
            elif kind == "s":
                value = shared[int(value_node.text)]
            else:
                value = value_node.text or ""
            cells[_column_index(cell.get("r"))] = (value, cell.get("s"))
        grid[int(row.get("r"))] = cells

    if not grid:
        return [], []
    header = grid[min(grid)]
    columns = [header.get(i, ("", None))[0] for i in range(max(header) + 1)]
    rows = []
    for number in sorted(grid)[1:]:
        cells = grid[number]
        rows.append({name: cells.get(index, ("", None))
                     for index, name in enumerate(columns)})
    return columns, rows


def coloured_rows(path, key_column="link_id"):
    """The keys of rows carrying a real fill colour, as opposed to merely carrying a style id.

    Excel writes an explicit style on every cell of the used range when it saves, so counting
    style ids reported that 230 rows kept their highlighting on a workbook holding three marks.
    A count that says everything survived is worse than no count, because it is read as
    reassurance. This resolves each cell's style to its fill and ignores the two Excel reserves
    for "no fill" and "grey125".
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "xl/styles.xml" not in names:
            return set()
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        sheet = ET.fromstring(archive.read(SHEET))
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in item.iter("{%s}t" % MAIN)))

    formats = styles.find("m:cellXfs", NS)
    fill_of = [int(xf.get("fillId", "0")) for xf in formats] if formats is not None else []

    keys, marked, header = {}, set(), None
    for row in sheet.iter("{%s}row" % MAIN):
        number, coloured = int(row.get("r")), False
        for cell in row.findall("m:c", NS):
            style = cell.get("s")
            # 0 is "no fill" and 1 is the grey125 pattern Excel always reserves. Neither is a mark.
            if style is not None and int(style) < len(fill_of) and fill_of[int(style)] > 1:
                coloured = True
            node = cell.find("m:v", NS)
            if node is None:
                inline = cell.find("m:is", NS)
                value = ("".join(t.text or "" for t in inline.iter("{%s}t" % MAIN))
                         if inline is not None else "")
            elif cell.get("t") == "s":
                value = shared[int(node.text)]
            else:
                value = node.text or ""
            index = _column_index(cell.get("r"))
            if header is None:
                if value == key_column:
                    keys["column"] = index
            elif index == keys.get("column"):
                keys[number] = value
        if header is None:
            header = number
        elif coloured:
            marked.add(number)
    return {keys[n] for n in marked if n in keys}


def write(path, columns, rows, template=None):
    """Rewrite the first sheet with these columns and rows, keeping everything else as it was.

    `template` is the workbook whose styles, theme and sheet settings are kept. It defaults to
    `path` itself, which is the ordinary case: refresh the sheet a person is working in without
    disturbing how it looks.

    Each row is a dict of column name to either a plain value or a (value, style id) pair. Where a
    style id is given it is written back, so a highlight the person applied survives.
    """
    template = template or path
    with zipfile.ZipFile(template) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
        original = ET.fromstring(parts[SHEET])

    # Keep the sheet's own settings. These carry frozen panes and column widths, and rebuilding
    # without them would quietly undo how the person set the sheet up to be read.
    #
    # Two details here are load-bearing, and getting either wrong writes a workbook that every
    # reader in this project accepts and Excel refuses outright, not even offering to repair it.
    # The spreadsheet namespace has to be registered as the default, or ElementTree invents an
    # ns0: prefix for elements Excel will only read unprefixed. And these five elements have a
    # fixed order in the schema, so dimension belongs between sheetPr and sheetViews instead of
    # leading. Both faults shipped in the workbook of 2026-08-12 and cost the analyst a day.
    ET.register_namespace("", MAIN)
    kept = {}
    for tag in ("sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols"):
        node = original.find("m:%s" % tag, NS)
        if node is None or tag == "dimension":
            continue
        _drop_foreign_attributes(node)
        kept[tag] = ET.tostring(node, encoding="unicode")

    body = []
    header_cells = []
    for index, name in enumerate(columns):
        header_cells.append(
            '<c r="%s1" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (_column_letters(index), _escape(name)))
    body.append("<row r=\"1\">%s</row>" % "".join(header_cells))

    for offset, row in enumerate(rows, start=2):
        cells = []
        for index, name in enumerate(columns):
            entry = row.get(name, "")
            value, style = entry if isinstance(entry, tuple) else (entry, None)
            if value in (None, ""):
                # An empty cell still carries its formatting, or a highlight on a blank cell
                # would vanish. Written only when it has one.
                if style is not None:
                    cells.append('<c r="%s%d" s="%s"/>' % (_column_letters(index), offset, style))
                continue
            attributes = ' s="%s"' % style if style is not None else ""
            cells.append('<c r="%s%d"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                         % (_column_letters(index), offset, attributes, _escape(value)))
        body.append('<row r="%d">%s</row>' % (offset, "".join(cells)))

    kept["dimension"] = '<dimension ref="A1:%s%d"/>' % (
        _column_letters(max(len(columns) - 1, 0)), len(rows) + 1)
    head = "".join(kept.get(tag, "") for tag in
                   ("sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols"))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="%s">%s<sheetData>%s</sheetData></worksheet>'
        % (MAIN, head, "".join(body))).encode("utf-8")

    # Written beside the target and moved into place, so an interrupted write cannot leave a
    # half-rebuilt workbook where a person's decisions used to be.
    scratch = str(path) + ".rebuilding"
    with zipfile.ZipFile(scratch, "w", zipfile.ZIP_DEFLATED) as out:
        for name, blob in parts.items():
            out.writestr(name, sheet_xml if name == SHEET else blob)
    shutil.move(scratch, path)


def formatting_by_key(columns, rows, key_column):
    """Every cell's style id, keyed on the row's stable identifier rather than its position."""
    keyed = {}
    for row in rows:
        key = row.get(key_column, ("", None))[0]
        if not key:
            continue
        keyed[key] = {name: value[1] for name, value in row.items() if value[1] is not None}
    return keyed
