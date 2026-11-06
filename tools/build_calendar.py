"""Build calendar.html (month grids) and unlovely-plan.ics from the plan doc XML.

Usage: python3 build_calendar.py doc.xml OUT_DIR
Reads the "Rehearsal checkpoints" table: Date | Do together | Due by.
"""
import sys, re, html, json, datetime as dt, calendar, os
import xml.etree.ElementTree as ET

src, out_dir = sys.argv[1], sys.argv[2]
root = ET.fromstring(open(src).read())
here = os.path.dirname(os.path.abspath(__file__))

MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

def dates_in(label):
    out = []
    for m in re.finditer(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2})", label):
        mon = MON[m.group(1)]
        out.append(dt.date(2026 if mon >= 10 else 2027, mon, int(m.group(2))))
    return out

def plain(el):
    return "".join(el.itertext()).strip()

def clean(s):
    s = s.strip()
    return "" if s in ("", "—", "-") else s

# Find the checkpoints table: first table after the "Rehearsal checkpoints" heading.
events, section = [], None
for el in root:
    if el.tag == "paragraph" and el.get("heading") == "2":
        section = plain(el)
    elif el.tag == "table" and section and section.startswith("Rehearsal"):
        for r in [r for r in el if r.tag == "row"][1:]:
            cells = [c for c in r if c.tag == "cell"]
            label, do, due = (plain(c) for c in cells[:3])
            is_release = cells[0].find(".//bold") is not None
            for d in dates_in(label):
                events.append({"date": d, "label": label, "do": clean(do), "due": clean(due),
                               "kind": ("show" if "show" in do.lower() else "release") if is_release else "checkpoint"})
        break

def short(e):
    if e["kind"] in ("release", "show"):
        return e["do"]
    if e["do"]:
        first = e["do"].split(";")[0].strip()
        return first.split(":")[0] if "kickoff" in first.lower() else first
    return "Due: " + e["due"].split(";")[0].strip()

def esc(s):
    return html.escape(s, quote=True)

by_date = {}
for e in events:
    by_date.setdefault(e["date"], []).append(e)

first = min(by_date).replace(day=1)
last = max(by_date)
months = []
y, m = first.year, first.month
while (y, m) <= (last.year, last.month):
    months.append((y, m))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)

cal = calendar.Calendar(firstweekday=6)  # weeks start Sunday
blocks, nav = [], []
for (y, m) in months:
    mid = f"m-{y}-{m:02d}"
    name = dt.date(y, m, 1).strftime("%B %Y")
    nav.append(f'<a href="#{mid}">{dt.date(y, m, 1).strftime("%b")}</a>')
    cells = []
    for d in cal.itermonthdates(y, m):
        if d.month != m:
            cells.append('<div class="day out"></div>')
            continue
        evs = by_date.get(d, [])
        cls = ["day"]
        if d.weekday() in (2, 6):
            cls.append("reh")
        chips = "".join(
            f'<a class="chip {e["kind"]}" href="#e-{d.isoformat()}">{esc(short(e))}</a>' for e in evs)
        cells.append(f'<div class="{" ".join(cls)}" data-date="{d.isoformat()}">'
                     f'<span class="num">{d.day}</span>{chips}</div>')
    agenda = []
    for d in sorted(k for k in by_date if k.year == y and k.month == m):
        for e in by_date[d]:
            rows = []
            if e["do"] and e["kind"] not in ("release", "show"):
                rows.append(f'<div class="row"><span class="k">Do together</span><span>{esc(e["do"])}</span></div>')
            if e["due"]:
                rows.append(f'<div class="row"><span class="k">Due by then</span><span>{esc(e["due"])}</span></div>')
            title = esc(e["do"]) if e["kind"] in ("release", "show") else "Rehearsal checkpoint"
            agenda.append(
                f'<li id="e-{d.isoformat()}" class="{e["kind"]}" data-date="{d.isoformat()}">'
                f'<div class="when">{d.strftime("%a %b")} {d.day}</div>'
                f'<div><div class="what">{title}</div>{"".join(rows)}</div></li>')
    head = "".join(f"<div class='dow'>{d}</div>" for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    blocks.append(
        f'<section class="month" id="{mid}"><h2>{name}</h2><div class="mwrap">'
        f'<div class="grid">{head}{"".join(cells)}</div>'
        f'<ol class="agenda">{"".join(agenda) or "<li class=empty>No checkpoints this month.</li>"}</ol>'
        f'</div></section>')

# iCalendar feed
def fold(line):
    b, out = line.encode("utf-8"), []
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)

def ics_text(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//unlovely//EP Cycle Plan//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:unlovely EP cycle"]
for i, e in enumerate(events):
    d = e["date"]
    summary = ("unlovely: " + e["do"]) if e["kind"] in ("release", "show") else ("unlovely checkpoint: " + short(e))
    desc = []
    if e["do"] and e["kind"] not in ("release", "show"):
        desc.append("Do together: " + e["do"])
    if e["due"]:
        desc.append("Due by then: " + e["due"])
    desc.append("Full plan: https://jonah-haber.github.io/unlovely-plan/")
    lines += ["BEGIN:VEVENT", f"UID:unlovely-{d.isoformat()}-{i}@jonah-haber.github.io", f"DTSTAMP:{stamp}",
              f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
              f"DTEND;VALUE=DATE:{(d + dt.timedelta(days=1)).strftime('%Y%m%d')}",
              fold("SUMMARY:" + ics_text(summary)), fold("DESCRIPTION:" + ics_text("\n".join(desc))),
              "TRANSP:TRANSPARENT", "END:VEVENT"]
lines.append("END:VCALENDAR")
open(os.path.join(out_dir, "unlovely-plan.ics"), "w", newline="").write("\r\n".join(lines) + "\r\n")

page = open(os.path.join(here, "calendar_template.html")).read()
page = (page.replace("{{MONTHNAV}}", "".join(nav)).replace("{{MONTHS}}", "".join(blocks))
            .replace("{{UPDATED}}", dt.date.today().strftime("%B %-d, %Y")))
open(os.path.join(out_dir, "calendar.html"), "w").write(page)
print("events", len(events), "months", len(months))
