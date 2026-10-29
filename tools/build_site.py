"""Build the band's plan site (index.html) from the Claude Doc XML export.

Usage: python3 build_site.py doc.xml site/index.html
"""
import sys, re, html, datetime
import xml.etree.ElementTree as ET

src, out = sys.argv[1], sys.argv[2]
root = ET.fromstring(open(src).read())

def esc(s):
    return html.escape(s, quote=False)

def inline(el):
    """Render a paragraph's runs to HTML, keeping bold/italic."""
    parts = []
    for t in el:
        if t.tag != "text":
            continue
        if t.text:
            parts.append(esc(t.text))
        for c in t:
            inner = esc("".join(c.itertext()))
            if c.tag == "bold":
                parts.append(f"<strong>{inner}</strong>")
            elif c.tag == "italic":
                parts.append(f"<em>{inner}</em>")
            else:
                parts.append(inner)
            if c.tail:
                parts.append(esc(c.tail))
    s = "".join(parts)
    s = s.replace("(gate)", '<span class="tag gate">gate</span>')
    s = s.replace("<em>(at rehearsal)</em>", '<span class="tag room">at rehearsal</span>')
    s = s.replace("(at rehearsal)", '<span class="tag room">at rehearsal</span>')
    return s

def plain(el):
    return "".join(el.itertext()).strip()

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

def iso_date(label):
    """'Wed Nov 4' -> 2026-11-04; Jan-Jun fall in 2027."""
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2})", label)
    if not m:
        return ""
    mon = MONTHS[m.group(1)]
    year = 2026 if mon >= 10 else 2027
    return f"{year}-{mon:02d}-{int(m.group(2)):02d}"

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

body, nav = [], []
section = None
lead = None
for el in root:
    if el.tag == "paragraph":
        h = el.get("heading")
        txt = plain(el)
        if h == "1":
            continue
        if any(c.tag in ("date", "mention") for c in el):
            continue
        if h == "2":
            section = txt
            sid = slug(txt)
            short = txt.split(":")[0]
            nav.append((sid, short))
            body.append(f'</section><section id="{sid}"><h2>{esc(txt)}</h2>')
            continue
        if not txt:
            continue
        if lead is None and section is None:
            lead = inline(el)
            continue
        # A paragraph that is only bold text acts as a sub-heading.
        runs = [t for t in el if t.tag == "text"]
        if len(runs) == 1 and len(runs[0]) == 1 and runs[0][0].tag == "bold" and not (runs[0].text or "").strip():
            body.append(f"<h3>{esc(txt)}</h3>")
        else:
            body.append(f"<p>{inline(el)}</p>")
    elif el.tag == "list":
        items = []
        for li in el:
            for p in li:
                if p.tag == "paragraph":
                    items.append(f"<li>{inline(p)}</li>")
        body.append("<ul>" + "".join(items) + "</ul>")
    elif el.tag == "table":
        rows = [r for r in el if r.tag == "row"]
        is_ck = section and section.startswith("Rehearsal")
        heads = [plain(c) for c in rows[0]]
        out_rows = []
        for r in rows[1:]:
            cells = [c for c in r if c.tag == "cell"]
            texts = [plain(c) for c in cells]
            first_p = [p for p in cells[0] if p.tag == "paragraph"]
            is_release = bool(first_p) and first_p[0].find(".//bold") is not None and is_ck
            attrs = ""
            if is_ck:
                attrs = f' data-date="{iso_date(texts[0])}"'
            cls = ' class="release"' if is_release else ""
            tds = []
            for i, c in enumerate(cells):
                ps = [p for p in c if p.tag == "paragraph"]
                inner = "<br>".join(inline(p) for p in ps)
                col = slug(heads[i]) if i < len(heads) else ""
                tds.append(f'<td class="c-{col}">{inner}</td>')
            out_rows.append(f"<tr{cls}{attrs}>" + "".join(tds) + "</tr>")
        th = "".join(f'<th class="c-{slug(h)}">{esc(h)}</th>' for h in heads)
        tid = ' id="checkpoints-table"' if is_ck else ""
        body.append(f'<div class="tbl"><table{tid}><thead><tr>{th}</tr></thead><tbody>'
                    + "".join(out_rows) + "</tbody></table></div>")

body_html = "".join(body)
if body_html.startswith("</section>"):
    body_html = body_html[len("</section>"):]
body_html = '<section id="overview">' + body_html + "</section>"
nav_html = "".join(f'<a href="#{sid}">{esc(n)}</a>' for sid, n in nav)
updated = datetime.date.today().strftime("%B %-d, %Y")

page = open(__file__.replace("build_site.py", "site_template.html")).read()
page = (page.replace("{{LEAD}}", lead or "")
            .replace("{{NAV}}", nav_html)
            .replace("{{BODY}}", body_html)
            .replace("{{UPDATED}}", updated))
open(out, "w").write(page)
print("wrote", out, len(page))
