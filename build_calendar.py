#!/usr/bin/env python3
"""Fetch the public Google Calendar .ics feed, classify/expand events,
and write a self-contained index.html from src/index.template.html."""

import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

CALENDAR_ID = (
    "d17d283695b8526d94cc74c78d0554050cb70c04f982e4c1dd018668db6d4f2a"
    "%40group.calendar.google.com"
)
ICS_URL = f"https://calendar.google.com/calendar/ical/{CALENDAR_ID}/public/basic.ics"
DEFAULT_TZ = "America/Edmonton"
MIN_YEAR = 2024
MAX_YEAR = 2030
MAX_OCCURRENCES = 5000

TEMPLATE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/index.template.html")
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("index.html")



def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------- ICS parsing ----------

def unfold(lines):
    """Unfold continuation lines."""
    out = []
    for line in lines:
        if line.startswith(" ") or line.startswith("\t"):
            if out:
                out[-1] += line[1:].rstrip("\r\n")
        else:
            out.append(line.rstrip("\r\n"))
    return out


def split_line(line):
    """Return (property, params dict, value)."""
    if ":" not in line:
        return None, {}, ""
    head, value = line.split(":", 1)
    parts = head.split(";")
    prop = parts[0]
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v
    return prop, params, value


def parse_ics(text):
    """Yield event dicts."""
    events = []
    current = None
    for line in unfold(text.splitlines()):
        prop, params, value = split_line(line)
        if prop is None:
            continue
        if prop == "BEGIN" and value == "VEVENT":
            current = {"raw": {}, "params": {}}
        elif prop == "END" and value == "VEVENT":
            if current:
                events.append(current)
            current = None
        elif current is not None:
            current["raw"][prop] = value
            current["params"][prop] = params
    return events


# ---------- Date/time helpers ----------

def parse_datetime(value, params):
    """Return a naive datetime (wall-clock) and an allDay flag."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        y, m, d = int(value[0:4]), int(value[4:6]), int(value[6:8])
        return datetime(y, m, d, 0, 0, 0), True
    # Floating local time or UTC time (we keep wall-clock components)
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", value)
    if m:
        y, mo, d, h, mi, s = map(int, m.groups())
        return datetime(y, mo, d, h, mi, s), False
    raise ValueError(f"Cannot parse datetime: {value}")


def format_date(dt):
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def format_time(dt):
    return f"{dt.hour:02d}:{dt.minute:02d}"


# ---------- Recurrence ----------

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def parse_rrule(rrule):
    parts = {}
    for piece in rrule.split(";"):
        if "=" in piece:
            k, v = piece.split("=", 1)
            parts[k.upper()] = v
    return parts


def parse_until(value):
    value = value.strip()
    if len(value) == 8:
        return datetime(int(value[0:4]), int(value[4:6]), int(value[6:8]), 23, 59, 59)
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", value)
    if m:
        return datetime(*map(int, m.groups()))
    return None


def byday_set(byday):
    days = set()
    for token in byday.split(","):
        token = re.sub(r"^[-+]?\d+", "", token).strip().upper()
        if token in WEEKDAYS:
            days.add(WEEKDAYS[token])
    return days


def add_years(dt, years):
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Feb 29 on a non-leap year
        return None


def expand_event(ev):
    """Yield occurrence dicts {date, time, allDay}."""
    start_dt, all_day = ev["start"]
    end_dt = ev.get("end", (start_dt, all_day))[0]
    rrule = ev.get("rrule")

    exdates = set()
    for ex in ev.get("exdate", []):
        exdates.add(format_date(ex))

    occurrences = []

    def emit(dt):
        if format_date(dt) in exdates:
            return
        occurrences.append({"date": format_date(dt), "time": None if all_day else format_time(dt), "allDay": all_day})

    if not rrule:
        emit(start_dt)
        for rdate in ev.get("rdate", []):
            emit(rdate)
        return occurrences

    rule = parse_rrule(rrule)
    freq = rule.get("FREQ", "DAILY").upper()
    interval = int(rule.get("INTERVAL", "1"))
    until = parse_until(rule["UNTIL"]) if "UNTIL" in rule else None
    count_limit = int(rule["COUNT"]) if "COUNT" in rule else MAX_OCCURRENCES
    byday = byday_set(rule["BYDAY"]) if "BYDAY" in rule else None

    cursor = start_dt
    emitted = 0

    if freq == "YEARLY":
        while cursor.year <= MAX_YEAR and emitted < count_limit:
            if until and cursor > until:
                break
            candidate = add_years(cursor, 0)
            if candidate:
                emit(candidate)
                emitted += 1
            cursor = add_years(cursor, interval)
    elif freq == "WEEKLY":
        while cursor.year <= MAX_YEAR and emitted < count_limit:
            if until and cursor > until:
                break
            if byday:
                if cursor.weekday() in byday:
                    emit(cursor)
                    emitted += 1
                    cursor += timedelta(days=7 * interval)
                else:
                    cursor += timedelta(days=1)
            else:
                emit(cursor)
                emitted += 1
                cursor += timedelta(days=7 * interval)
    else:
        # For other frequencies, just emit the original instance.
        emit(start_dt)

    for rdate in ev.get("rdate", []):
        emit(rdate)

    return occurrences


# ---------- Classification ----------

HEART_RE = re.compile(
    r"^[\u2764\uFE0F\U0001F49B\U0001F49A\U0001F499\U0001F49C\U0001F5A4\U0001F90D\U0001F9E1\U0001F496\U0001F49C\s]+$",
    re.UNICODE,
)


def classify(title: str) -> str:
    t = (title or "").strip()
    if HEART_RE.match(t) and len(t) <= 6:
        return "correspondence"
    if re.search(r"\bfeast\b", t, re.I) or re.search(r"\bst\.?\s", t, re.I):
        return "feast"
    if re.search(r"\b(retrograde|direct)\b", t, re.I):
        return "retrograde"
    if re.match(r"^moon\s+(conjunction|opposition|sextile|square|trine|quincunx|semisextile)\b", t, re.I):
        return "aspect"
    if re.search(r"moon", t, re.I):
        return "moon"
    if re.search(r"(solstice|equinox|imbolc|beltane|lughnasadh|samhain|yule|eostre|ostara|litha|mabon)", t, re.I):
        return "sabbat"
    if re.match(r"^sun enters\b", t, re.I):
        return "zodiac"
    return "other"


# ---------- Build events ----------

def unescape_ics(value: str) -> str:
    r"""Reverse iCalendar TEXT escaping (RFC 5545): \n \N -> newline,
    \, -> comma, \; -> semicolon, \\ -> backslash."""
    if not value:
        return ""
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt in ("n", "N"):
                out.append("\n")
            elif nxt == ",":
                out.append(",")
            elif nxt == ";":
                out.append(";")
            elif nxt == "\\":
                out.append("\\")
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def build_event(raw, params):
    summary = unescape_ics(raw.get("SUMMARY", ""))
    description = unescape_ics(raw.get("DESCRIPTION", ""))
    url = raw.get("URL", "")
    start_dt, all_day = parse_datetime(raw["DTSTART"], params.get("DTSTART", {}))
    ev = {
        "title": summary,
        "description": description,
        "url": url,
        "start": (start_dt, all_day),
        "category": classify(summary),
    }
    if "DTEND" in raw:
        ev["end"] = parse_datetime(raw["DTEND"], params.get("DTEND", {}))
    if "RRULE" in raw:
        ev["rrule"] = raw["RRULE"]
    if "RDATE" in raw:
        ev["rdate"] = [parse_datetime(v, {})[0] for v in raw["RDATE"].split(",")]
    if "EXDATE" in raw:
        ev["exdate"] = [parse_datetime(v, {})[0] for v in raw["EXDATE"].split(",")]
    return ev


def main():
    log(f"Fetching {ICS_URL}")
    req = urllib.request.Request(
        ICS_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; HHWWOTY calendar sync)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    log(f"Downloaded {len(text):,} characters")

    raw_events = parse_ics(text)
    log(f"Found {len(raw_events)} VEVENT blocks")

    built = []
    seen = set()
    for raw in raw_events:
        if "DTSTART" not in raw["raw"]:
            continue
        ev = build_event(raw["raw"], raw["params"])
        for occ in expand_event(ev):
            key = (occ["date"], ev["title"], occ["time"])
            if key in seen:
                continue
            seen.add(key)
            built.append({
                "id": f"g{len(built)}",
                "date": occ["date"],
                "time": occ["time"],
                "allDay": occ["allDay"],
                "title": ev["title"],
                "description": ev["description"],
                "url": ev["url"],
                "category": ev["category"],
            })

    # Sort by date, then put correspondence first within a day for a stable look.
    category_order = {
        "correspondence": 0,
        "sabbat": 1,
        "moon": 2,
        "aspect": 3,
        "zodiac": 4,
        "retrograde": 5,
        "feast": 6,
        "other": 7,
    }
    built.sort(key=lambda e: (e["date"], category_order.get(e["category"], 99), e["title"]))

    data = {
        "meta": {
            "name": "Witch's Wheel of the Year",
            "timezone": DEFAULT_TZ,
            "syncedAt": datetime.now().isoformat(),
            "source": ICS_URL,
        },
        "events": built,
    }

    log(f"Built {len(built)} event occurrences")
    for cat in category_order:
        n = sum(1 for e in built if e["category"] == cat)
        if n:
            log(f"  {cat}: {n}")

    if not TEMPLATE.exists():
        log(f"Template not found: {TEMPLATE}")
        sys.exit(1)

    html = TEMPLATE.read_text(encoding="utf8")
    if "{{EVENTS_JSON}}" not in html:
        log("Template is missing the {{EVENTS_JSON}} placeholder")
        sys.exit(1)

    json_blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    html = html.replace("{{EVENTS_JSON}}", json_blob)

    OUTPUT.write_text(html, encoding="utf8")
    log(f"Wrote {OUTPUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
