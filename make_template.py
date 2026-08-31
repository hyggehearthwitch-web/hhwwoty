import sys
from pathlib import Path

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("index_v4.html")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("src/index.template.html")

if not src.exists():
    print(f"Source file not found: {src}", file=sys.stderr)
    print("Run this from the repo root and point it at the current standalone HTML file.", file=sys.stderr)
    sys.exit(1)

lines = src.read_text(encoding="utf8").splitlines(keepends=True)

snapshot_block = r'''  // ---------- calendar data ----------
  function classify(title) {
    var t = String(title || "").trim();
    if (/^[\u2764\uFE0F\u{1F49B}\u{1F49A}\u{1F499}\u{1F49C}\u{1F5A4}\u{1F90D}\u{1F9E1}\u{1F496}\u{1F49C}\s]+$/u.test(t) && t.length <= 6)
      return "correspondence";
    if (/\bfeast\b/i.test(t) || /\bst\.?\s/i.test(t)) return "feast";
    if (/\b(retrograde|direct)\b/i.test(t)) return "retrograde";
    if (/^moon\s+(conjunction|opposition|sextile|square|trine|quincunx|semisextile)\b/i.test(t))
      return "aspect";
    if (/moon/i.test(t)) return "moon";
    if (
      /(solstice|equinox|imbolc|beltane|lughnasadh|samhain|yule|eostre|ostara|litha|mabon)/i.test(t)
    )
      return "sabbat";
    if (/^sun enters\b/i.test(t)) return "zodiac";
    return "other";
  }

  function normalize(list) {
    return (list || []).map(function (e) {
      if (e.category === "correspondence") {
        var copy = Object.assign({}, e);
        copy.emoji = e.title;
        copy.title = String(e.description || "").split("\\n")[0] + " correspondences";
        return copy;
      }
      return e;
    });
  }

  var DATA = JSON.parse(document.getElementById("wheel-data").textContent);
  var META = DATA.meta || { name: "Witch's Wheel of the Year", timezone: DEFAULT_TZ };
  var EVENTS = normalize(DATA.events);
  var liveStatus = {
    state: "snapshot",
    message:
      "Calendar snapshot updated " +
      (META.syncedAt
        ? new Date(META.syncedAt).toLocaleString("en-US", {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })
        : "by GitHub Actions"),
  };
'''

def find_line(predicate, start=0):
    for i in range(start, len(lines)):
        if predicate(lines[i]):
            return i
    raise ValueError("Marker not found")

# 1. Replace the embedded events JSON with a build-time placeholder.
data_idx = find_line(lambda ln: 'id="wheel-data"' in ln and "application/json" in ln)
lines[data_idx] = '    <script id="wheel-data" type="application/json">{{EVENTS_JSON}}</script>\n'

# 2. Replace the live-sync block (from its comment through the closing of startLiveSync).
live_start = find_line(lambda ln: "// ---------- live Google Calendar connection ----------" in ln)
start_live_idx = find_line(lambda ln: "function startLiveSync()" in ln, start=live_start)
balance = 0
live_end = None
for i in range(start_live_idx, len(lines)):
    balance += lines[i].count("{")
    balance -= lines[i].count("}")
    if balance == 0:
        live_end = i
        break
if live_end is None:
    raise ValueError("Could not find the closing brace of startLiveSync()")
lines[live_start:live_end + 1] = [snapshot_block]

# 3. Remove the "Refresh calendar" button block.
refresh_start = find_line(lambda ln: '"Refresh calendar"' in ln)
button_start = None
for i in range(refresh_start, -1, -1):
    if 'el("button", {' in lines[i]:
        button_start = i
        break
if button_start is None:
    raise ValueError("Could not find the start of the Refresh calendar button")
balance = 0
refresh_end = None
for i in range(button_start, len(lines)):
    balance += lines[i].count("{")
    balance -= lines[i].count("}")
    if balance == 0:
        refresh_end = i
        break
if refresh_end is None:
    raise ValueError("Could not find the closing of the Refresh calendar button")
lines[button_start:refresh_end + 1] = []

# 4. Remove any standalone startLiveSync() call.
lines = [ln for ln in lines if "startLiveSync();" not in ln]

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("".join(lines), encoding="utf8")
print(f"Wrote template to {out}")
