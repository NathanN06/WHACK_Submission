"""Render both SQLite star schemas as an offline SVG and interactive HTML plot.

Run: python docs/render_schema.py
Uses only the standard library; reads SQL definitions without importing loaders.
"""

import ast
import csv
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET


DIRECTORY = Path(__file__).resolve().parent


def _constants(filename, shared=None):
    values = dict(shared or {})

    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return resolve(node.left) + resolve(node.right)
        raise ValueError("Schema must be a string or a concatenation of known strings.")

    for statement in ast.parse((DIRECTORY / filename).read_text(encoding="utf-8-sig")).body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in ("DIMENSION_SCHEMA", "SCHEMA"):
                    values[target.id] = resolve(statement.value)
    return values


def _tables(sql):
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sql)
        result = {}
        for (name,) in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'"):
            foreign = {row[3] for row in connection.execute(
                "SELECT * FROM pragma_foreign_key_list(?)", (name,)
            )}
            result[name] = [
                {"name": row[1], "type": row[2], "pk": row[5], "fk": row[1] in foreign}
                for row in connection.execute("SELECT * FROM pragma_table_info(?)", (name,))
            ]
        return result
    finally:
        connection.close()


def _counts(folder):
    path = DIRECTORY / "files_csv" / folder / "health_measurements.csv"
    if not path.exists():
        return "All available participants and dates"
    people = set()
    count = 0
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            people.add(row["participant_id"])
            count += 1
    return f"{len(people)} participants  /  {count:,} rows"


def _element(parent, tag, text=None, **attributes):
    node = ET.SubElement(parent, tag, {key.replace("_", "-"): str(value) for key, value in attributes.items()})
    if text is not None:
        node.text = text
    return node


def _text(parent, x, y, text, size=13, color="#475569", weight=400, **attributes):
    return _element(parent, "text", text, x=x, y=y, font_size=size, fill=color,
                    font_weight=weight, **attributes)


def _card(svg, x, y, width, name, columns, accent, role, grain):
    height = 96 + len(columns) * 25
    _element(svg, "rect", x=x, y=y, width=width, height=height, rx=14,
             fill="#ffffff", stroke="#dbe3ee", filter="url(#shadow)")
    _element(svg, "rect", x=x, y=y, width=width, height=5, rx=2, fill=accent)
    _text(svg, x + 18, y + 28, role.upper(), 10, accent, 750, letter_spacing=1.5)
    _text(svg, x + 18, y + 54, name, 20, "#0f172a", 700)
    _text(svg, x + 18, y + 76, grain, 11, "#64748b")
    for index, column in enumerate(columns):
        row_y = y + 90 + index * 25
        if index % 2 == 0:
            _element(svg, "rect", x=x + 1, y=row_y - 6, width=width - 2, height=25, fill="#f6f8fc")
        _text(svg, x + 18, row_y + 10, column["name"], 12, "#1e293b", font_family="Consolas, monospace")
        _text(svg, x + width - 76, row_y + 10, column["type"], 10, "#94a3b8", text_anchor="end")
        flags = "/".join(key for key, enabled in (("PK", column["pk"]), ("FK", column["fk"])) if enabled)
        _text(svg, x + width - 16, row_y + 10, flags, 10, accent, 700, text_anchor="end")
    return height


def render():
    daily_constants = _constants("database.py")
    raw_constants = _constants("raw_database.py", daily_constants)
    stars = [
        ("01", "Daily summaries", "daily_connection", "daily_mean", "fact_daily_health",
         "Key: username + date", "#0f8b83", _tables(daily_constants["SCHEMA"])),
        ("02", "Every original reading", "raw_connection", "all_values", "fact_health_reading",
         "Key: username + timestamp", "#7756cc", _tables(raw_constants["SCHEMA"])),
    ]
    panel_heights = [96 + len(tables[fact]) * 25 + 130 for _, _, _, _, fact, _, _, tables in stars]
    height = 150 + sum(panel_heights) + 30 + 80
    svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": f"0 0 1360 {height}",
                             "role": "img", "aria-labelledby": "title description"})
    _element(svg, "title", "CGMacros: two independent star databases", id="title")
    _element(svg, "desc", "Daily summaries and original timestamped readings, each connected directly to user and date dimensions.", id="description")
    defs = _element(svg, "defs")
    shadow = _element(defs, "filter", id="shadow", x="-10%", y="-10%", width="120%", height="130%")
    _element(shadow, "feDropShadow", dx=0, dy=3, stdDeviation=5, flood_color="#0f172a", flood_opacity="0.06")
    _element(svg, "style", "text {font-family: Segoe UI, Arial, sans-serif;} text[font-family] {font-family: Consolas, monospace;}")
    _element(svg, "rect", width=1360, height=height, fill="#edf2f8")
    _text(svg, 48, 56, "CGMacros / two star databases", 30, "#0f172a", 750)
    _text(svg, 48, 87, "Same people. Same dates. Separate time scales.", 16, "#64748b")
    _text(svg, 48, 116, "Each fact table links directly to its own user and date dimensions. No fact-to-fact joins.", 13)
    top = 150
    for (number, title, connection, folder, fact, grain, accent, tables), panel_height in zip(stars, panel_heights):
        _element(svg, "rect", x=24, y=top, width=1312, height=panel_height, rx=20, fill="#ffffff", stroke="#dbe3ee")
        _text(svg, 48, top + 34, f"{number}  {title}", 21, accent, 750)
        _text(svg, 48, top + 58, f"{connection}  |  CSV: files_csv/{folder}/", 12)
        _text(svg, 1308, top + 36, _counts(folder), 13, "#64748b", text_anchor="end")
        fact_y = top + 90
        fact_height = 96 + len(tables[fact]) * 25
        center = fact_y + fact_height / 2
        user_y = center - (96 + len(tables["dim_user"]) * 25) / 2
        date_y = center - (96 + len(tables["dim_date"]) * 25) / 2
        for start, end in ((360, 420), (940, 990)):
            _element(svg, "path", d=f"M {start} {center} L {end} {center}", stroke=accent, stroke_width=2.5, fill="none")
        _text(svg, 370, center - 12, "1", 11, accent, 700)
        _text(svg, 412, center - 12, "many", 10, accent, 700, text_anchor="end")
        _text(svg, 948, center - 12, "many", 10, accent, 700)
        _text(svg, 982, center - 12, "1", 11, accent, 700)
        _card(svg, 48, user_y, 312, "dim_user", tables["dim_user"], "#336cb0", "User dimension", "Key: username; participant_id is unique")
        _card(svg, 420, fact_y, 520, fact, tables[fact], accent, "Fact table", grain)
        _card(svg, 990, date_y, 322, "dim_date", tables["dim_date"], "#336cb0", "Date dimension", "Key: date")
        top += panel_height + 30
    _text(svg, 48, top + 10, "PK = primary key  |  FK = foreign key  |  Composite PK columns form one key together.", 12)
    _text(svg, 48, top + 33, "Daily sensors use means; calories and nutrients use recorded totals. Original readings stay unchanged.", 12)
    markup = ET.tostring(svg, encoding="unicode")
    (DIRECTORY / "database_schema.svg").write_text(markup, encoding="utf-8")
    html = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CGMacros star databases</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf2f8;color:#0f172a;font-family:Segoe UI,Arial,sans-serif}
header{position:sticky;top:0;z-index:1;background:#ffffffed;backdrop-filter:blur(10px);border-bottom:1px solid #dbe3ee;padding:16px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
header strong{margin-right:auto}button,a{font:inherit;font-size:13px;color:#334155;border:1px solid #cbd5e1;border-radius:8px;background:white;padding:8px 12px;text-decoration:none;cursor:pointer}
button:hover,a:hover{background:#f1f5f9}main{overflow:auto;padding:12px;min-height:80vh}svg{display:block;width:100%;min-width:700px;height:auto;margin:auto}footer{padding:16px 24px;font-size:13px;color:#64748b}
</style>
<header><strong>CGMacros / database architecture</strong><button id="out" aria-label="Zoom out">−</button><button id="fit">Fit</button><button id="in" aria-label="Zoom in">+</button><a href="database_schema.svg" download>Download SVG</a><a href="database_schema.md">Mermaid source</a></header>
<main>""" + markup + """</main>
<footer>Generated from database.py and raw_database.py. Open locally; no internet connection required. Ctrl/Cmd + P to print.</footer>
<script>let scale=1;const diagram=document.querySelector('svg');function zoom(value){scale=Math.max(.5,Math.min(3,value));diagram.style.width=(100*scale)+'%'}document.querySelector('#in').onclick=()=>zoom(scale+.25);document.querySelector('#out').onclick=()=>zoom(scale-.25);document.querySelector('#fit').onclick=()=>zoom(1);</script>
</html>"""
    (DIRECTORY / "database_schema.html").write_text(html, encoding="utf-8")
    print("Rendered docs/database_schema.svg and docs/database_schema.html from both SQLite schemas.")


if __name__ == "__main__":
    render()
