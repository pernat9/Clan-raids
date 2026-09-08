"""
Page rendering for the Astral clan raid catalogue.

Design brief: the clan is called Astral and the Discord is a galaxy, so the
page is a star catalogue. Magnitude is the organising idea — in astronomy the
brightest object is rank 1, which is already how a leaderboard works. Each
member is a star sized by clan raids; the hero constellation draws real edges
between members who raid together, taken from the top-partner data.

Palette      void #060916, deep #0B1030, star #EEF2FF, dim #8A93BE,
             gold #F0C674 (starlight, the one accent), link #7FA8FF
Type         Syne for the wordmark, IBM Plex Sans for everything else
Layout       left-aligned, single column, constellation above the catalogue
"""

import math
import random

from graph import graph_block
from datetime import datetime, timezone
from html import escape

# ---------------------------------------------------------------------------
# Background starfield
# ---------------------------------------------------------------------------

def starfield(seed=7, w=1600, h=900):
    """A still field of stars with a denser band across it for the galaxy."""
    rng = random.Random(seed)
    out = []

    # Scattered field
    for _ in range(240):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.choice([0.5, 0.6, 0.7, 0.9, 1.1, 1.4])
        o = rng.uniform(0.15, 0.65)
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" '
                   f'fill="#EEF2FF" opacity="{o:.2f}"/>')

    # Denser band: stars clustered around a line tilted across the page,
    # thinning out with distance from it. This is the galaxy, rather than a
    # blurred gradient blob.
    angle = math.radians(-19)
    cx, cy = w * 0.5, h * 0.52
    for _ in range(260):
        t = rng.uniform(-0.75, 0.75) * w
        off = rng.gauss(0, h * 0.085)
        x = cx + t * math.cos(angle) - off * math.sin(angle)
        y = cy + t * math.sin(angle) + off * math.cos(angle)
        if not (0 <= x <= w and 0 <= y <= h):
            continue
        fade = max(0.0, 1 - abs(off) / (h * 0.22))
        r = rng.choice([0.4, 0.5, 0.6, 0.8])
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" '
                   f'fill="#EEF2FF" opacity="{0.12 + 0.5 * fade * rng.random():.2f}"/>')

    haze = (f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{w*0.62:.0f}" '
            f'ry="{h*0.11:.0f}" transform="rotate(-19 {cx:.0f} {cy:.0f})" '
            f'fill="url(#haze)" opacity="0.34"/>')

    return (f'<svg class="sky" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" '
            f'aria-hidden="true" focusable="false">'
            '<defs><radialGradient id="haze">'
            '<stop offset="0%" stop-color="#33427F" stop-opacity="0.22"/>'
            '<stop offset="60%" stop-color="#232C64" stop-opacity="0.10"/>'
            '<stop offset="100%" stop-color="#0B1030" stop-opacity="0"/>'
            '</radialGradient></defs>'
            + haze + "".join(out) + "</svg>")


# ---------------------------------------------------------------------------
# Constellation of the top members
# ---------------------------------------------------------------------------

def constellation(rows, n=8, w=1000, h=480, font=14, cls="wide", short=False):
    """Top n members as stars, joined where one is the other's top partner."""
    top = [r for r in rows if r["count"] > 0][:n]
    if len(top) < 2:
        return ""

    names = {r["name"] for r in top}
    peak = max(r["count"] for r in top)
    idx = {r["name"]: i for i, r in enumerate(top)}

    pairs = []
    seen = set()
    for r in top:
        partner = r.get("partner_name")
        if partner in names and partner != r["name"]:
            key = tuple(sorted((r["name"], partner)))
            if key not in seen:
                seen.add(key)
                pairs.append((idx[key[0]], idx[key[1]], r.get("partner_count", 0)))

    # Deterministic start, then relax: partners pull together, everyone pushes
    # apart. Gives a readable shape instead of a random scatter, and keeps the
    # same shape on every rebuild.
    rng = random.Random(sum(ord(c) for c in "".join(sorted(names))))
    pts = [[rng.uniform(w * 0.2, w * 0.8), rng.uniform(h * 0.2, h * 0.8)]
           for _ in top]
    for step in range(500):
        cool = 1 - step / 500
        for i in range(len(pts)):
            fx = fy = 0.0
            for j in range(len(pts)):
                if i == j:
                    continue
                dx, dy = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
                d2 = max(dx * dx + dy * dy, 400)
                f = 165000 / d2
                fx += dx / math.sqrt(d2) * f
                fy += dy / math.sqrt(d2) * f
            pts[i][0] += fx * cool * 0.08
            pts[i][1] += fy * cool * 0.08
        for a, b, _ in pairs:
            dx, dy = pts[b][0] - pts[a][0], pts[b][1] - pts[a][1]
            d = max(math.hypot(dx, dy), 1)
            pull = (d - 235) * 0.012 * cool
            pts[a][0] += dx / d * pull; pts[a][1] += dy / d * pull
            pts[b][0] -= dx / d * pull; pts[b][1] -= dy / d * pull
        for q in pts:
            q[0] = min(max(q[0], 150), w - 150)
            q[1] = min(max(q[1], 58), h - 48)

    heaviest = max((e[2] for e in pairs), default=1) or 1
    radii = []

    svg = [f'<svg class="constellation {cls}" viewBox="0 0 {w} {h}" role="img" '
           f'aria-label="The {len(top)} members with the most clan raids, drawn '
           f'as stars sized by raid count and joined where they raid together.">',
           f'<defs><radialGradient id="glow-{cls}">'
           '<stop offset="0%" stop-color="#F7E3B5" stop-opacity="0.20"/>'
           '<stop offset="55%" stop-color="#F0C674" stop-opacity="0.04"/>'
           '<stop offset="100%" stop-color="#F0C674" stop-opacity="0"/>'
           '</radialGradient></defs>']

    for a, b, weight in pairs:
        (x1, y1), (x2, y2) = pts[a], pts[b]
        svg.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                   f'stroke="#7FA8FF" '
                   f'stroke-opacity="{0.16 + 0.34 * weight / heaviest:.2f}" '
                   f'stroke-width="{0.5 + 1.4 * (weight / heaviest):.2f}"/>')

    for i, r in enumerate(top):
        x, y = pts[i]
        mag = r["count"] / peak
        rad = 2.6 + 8.4 * math.sqrt(mag)
        svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{9 + 21 * mag:.0f}" '
                   f'fill="url(#glow-{cls})"/>')
        if mag > 0.55:
            sp = 11 + 17 * mag
            svg.append(f'<path d="M{x-sp:.0f} {y:.0f}H{x+sp:.0f}M{x:.0f} '
                       f'{y-sp:.0f}V{y+sp:.0f}" stroke="#F7E3B5" '
                       f'stroke-opacity="0.30" stroke-width="0.7"/>')
        svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rad:.1f}" fill="#FFFBF0"/>')

        radii.append(rad)

    # Labels: try each side in turn, take the first spot that hits nothing.
    # Brightest stars choose first, so the important names get the best places.
    placed = []
    blockers = [(pts[i][0], pts[i][1], radii[i] + 10) for i in range(len(top))]
    labels = []
    for i, r in enumerate(top):
        x, y = pts[i]
        rad = radii[i]
        label = r["name"].rsplit("#", 1)[0] if short else r["name"]
        tw = 0.512 * font * len(label) + 6
        th = 2.45 * font
        # Four sides, each also tried nudged up and down, so a crowded
        # corner still has somewhere to put the name.
        options = []
        for dy in (0, -1.9 * font, 1.9 * font, -3.6 * font, 3.6 * font):
            yy = y + dy
            options.extend([
                (x + rad + 13, yy - 1, "start", x + rad + 13, yy - font - 2),
                (x - rad - 13, yy - 1, "end", x - rad - 13 - tw, yy - font - 2),
                (x, yy - rad - 20, "middle", x - tw / 2, yy - rad - 20 - font - 2),
                (x, yy + rad + font + 18, "middle", x - tw / 2, yy + rad + 16),
            ])
        chosen = None
        for lx, ly, anchor, bx, by in options:
            shift = min(max(bx, 4), w - tw - 4) - bx   # keep it inside the frame
            bx += shift
            lx += shift
            if by < 2 or by + th > h - 2:
                continue
            if any(bx < px + pw and bx + tw > px and by < py + ph and by + th > py
                   for px, py, pw, ph in placed):
                continue
            if any(bx - 4 < cx < bx + tw + 4 and by - 4 < cy < by + th + 4
                   for cx, cy, _ in blockers):
                continue
            chosen = (lx, ly, anchor, bx, by)
            break
        if chosen is None:
            lx, ly, anchor, bx, by = options[0]
            shift = min(max(bx, 4), w - tw - 4) - bx
            bx += shift
            lx += shift
        else:
            lx, ly, anchor, bx, by = chosen
        placed.append((bx, by, tw, th))
        labels.append((lx, ly, anchor, r, label))

    for lx, ly, anchor, r, label in labels:
        svg.append(
            f'<text class="cn" x="{lx:.0f}" y="{ly:.0f}" text-anchor="{anchor}">'
            f'{escape(label)}</text>'
            f'<text class="cv" x="{lx:.0f}" y="{ly + font + 3:.0f}" text-anchor="{anchor}">'
            f'{r["count"]}</text>')

    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

CSS = """
html{color-scheme:dark; scrollbar-color:#242C50 var(--void); scrollbar-width:thin}
::-webkit-scrollbar{width:11px; height:11px}
::-webkit-scrollbar-track{background:var(--void)}
::-webkit-scrollbar-thumb{background:#242C50; border:3px solid var(--void); border-radius:99px}
::-webkit-scrollbar-thumb:hover{background:#33406E}
:root{
  --void:#060916; --deep:#0B1030; --star:#EEF2FF; --dim:#8A93BE;
  --gold:#F0C674; --link:#7FA8FF; --rule:rgba(138,147,190,.22);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--void); color:var(--star);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px; line-height:1.55; font-feature-settings:"tnum" 1;
  overflow-x:hidden;
}
.sky{position:fixed; inset:0; width:100%; height:100%; z-index:-1}
.page{max-width:74rem; margin:0 auto; padding:clamp(2rem,6vw,5rem) clamp(1rem,4vw,3rem) 5rem}

.mark{
  font-family:Syne,"IBM Plex Sans",sans-serif; font-weight:800;
  font-size:clamp(3rem,11vw,7rem); line-height:.92; letter-spacing:-.03em;
  margin:0; color:var(--star);
}
.lede{max-width:34rem; color:var(--dim); margin:1rem 0 0; font-size:1.0625rem}
.lede b{color:var(--star); font-weight:600}

.constellation{width:100%; height:auto; margin:clamp(1rem,4vw,2.5rem) 0 0}
.map{display:block; width:100%; height:520px; touch-action:pan-y}
.constellation.wide{display:block}
.constellation.narrow{display:none}
.cn{font-family:"IBM Plex Sans",sans-serif; font-size:14px; font-weight:500; fill:var(--star)}
.cv{font-family:"IBM Plex Sans",sans-serif; font-size:13px; fill:var(--gold)}
.constellation.narrow .cn{font-size:22px}
.constellation.narrow .cv{font-size:20px}
.caption{color:var(--dim); font-size:.875rem; max-width:38rem; margin:.5rem 0 0}
p.caption.narrow{display:none}

.catalogue{width:100%; border-collapse:collapse; margin-top:clamp(2rem,6vw,3.5rem)}
.catalogue caption{text-align:left; color:var(--dim); font-size:.9375rem; padding-bottom:.75rem}
.catalogue th{
  font-weight:500; font-size:.875rem; color:var(--dim); text-align:left;
  padding:.5rem .75rem; border-bottom:1px solid var(--rule); white-space:nowrap;
}
.catalogue th button{
  all:unset; cursor:pointer; color:inherit; font:inherit;
}
.catalogue th button:focus-visible{outline:2px solid var(--link); outline-offset:3px}
.catalogue th[aria-sort] button::after{content:"\\2009\\25B4"; color:var(--gold)}
.catalogue th[aria-sort="descending"] button::after{content:"\\2009\\25BE"}
.catalogue td{padding:.7rem .75rem; border-bottom:1px solid rgba(138,147,190,.10); vertical-align:baseline}
.catalogue tbody tr:hover td{background:rgba(127,168,255,.06)}
.num{text-align:right; font-variant-numeric:tabular-nums}
.rank{color:var(--dim); width:2.5rem}
.who{font-weight:500}
.lede-row td{color:var(--star)}
.raids{color:var(--gold); font-weight:600}
.dot{display:inline-block; border-radius:50%; background:#FFF6E0; vertical-align:middle;
     margin-right:.55rem}
.soft{color:var(--dim)}
.nowrap{white-space:nowrap}
.hidden-row{opacity:.4}

.note{margin-top:2.5rem; color:var(--dim); font-size:.875rem; max-width:44rem}
a{color:var(--link)}

@media (max-width:720px){
  .map{display:none}
  p.caption.wide{display:none}
  p.caption.narrow{display:block}
  .constellation.wide{display:none}
  .constellation.narrow{display:block}

  .catalogue thead{position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0)}
  .catalogue tr{display:block; border-bottom:1px solid var(--rule); padding:.85rem 0}
  .catalogue td{display:block; border:0; padding:.1rem 0}
  .catalogue td.num{text-align:left}
  .catalogue td[data-label]::before{content:attr(data-label) " "; color:var(--dim)}
  .catalogue td.rank{display:inline-block; margin-right:.5rem}
  .catalogue td.who{display:inline-block; font-size:1.0625rem}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
"""

JS = """
document.querySelectorAll('.catalogue th button').forEach(function(btn){
  btn.addEventListener('click', function(){
    var th = btn.closest('th'), table = th.closest('table'),
        i = Array.prototype.indexOf.call(th.parentNode.children, th),
        body = table.tBodies[0], rows = Array.prototype.slice.call(body.rows),
        desc = th.getAttribute('aria-sort') !== 'descending',
        numeric = th.classList.contains('num') || i === 0;
    table.querySelectorAll('th').forEach(function(o){ o.removeAttribute('aria-sort'); });
    th.setAttribute('aria-sort', desc ? 'descending' : 'ascending');
    rows.sort(function(a, b){
      var x = a.cells[i].dataset.sort || a.cells[i].textContent,
          y = b.cells[i].dataset.sort || b.cells[i].textContent;
      var r = numeric ? (parseFloat(x)||0) - (parseFloat(y)||0) : x.localeCompare(y);
      return desc ? -r : r;
    });
    rows.forEach(function(r){ body.appendChild(r); });
  });
});
"""

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'"
    "%3E%3Crect width='32' height='32' fill='%23060916'/%3E%3Cpath d='M16 4l2.6 8.9"
    "L27 16l-8.4 3.1L16 28l-2.6-8.9L5 16l8.4-3.1z' fill='%23F0C674'/%3E%3C/svg%3E"
)


def ordinal_date(dt):
    return f"{dt.day} {dt.strftime('%B %Y')}"


def render(rows, clan_name, total, min_members, page_url="", pairs=()):
    clan = clan_name.strip().strip("\u3164").strip() or "Astral"
    now = datetime.now(timezone.utc)
    ranked = [r for r in rows if r["count"] > 0]
    peak = max((r["count"] for r in ranked), default=1)
    counted = len(ranked)
    people = "two" if min_members == 2 else ("three" if min_members == 3 else str(min_members))

    lede = (f"{total:,} raids cleared with at least {people} of us in the fireteam. "
            f"{counted} members have at least one.")

    body = []
    for i, r in enumerate(rows, 1):
        size = 4 + 9 * math.sqrt(r["count"] / peak) if peak and r["count"] else 4
        hidden = r.get("status") != "ok"
        cls = ' class="hidden-row"' if hidden else ""
        partner = escape(r.get("partner") or "—")
        body.append(
            f"<tr{cls}>"
            f'<td class="rank num" data-sort="{i}">{i}</td>'
            f'<td class="who" data-label="">{escape(r["name"])}</td>'
            f'<td class="num raids" data-label="clan raids" data-sort="{r["count"]}">'
            f'<span class="dot" style="width:{size:.1f}px;height:{size:.1f}px"></span>'
            f'{r["count"]}</td>'
            f'<td class="num soft" data-label="all raids" data-sort="{r["total"]}">{r["total"]}</td>'
            f'<td data-label="most run" class="soft">{escape(r.get("top_raid") or "—")}</td>'
            f'<td data-label="raids most with" class="soft">{partner}</td>'
            f'<td data-label="last" class="soft nowrap" data-sort="{escape(r.get("last") or "")}">'
            f'{escape(r.get("last") or "—")}</td>'
            "</tr>")

    heads = [("rank", "rank num"), ("member", "who"), ("clan raids", "num"),
             ("all raids", "num"), ("most run", ""), ("raids most with", ""),
             ("last", "")]
    thead = "".join(
        f'<th class="{c}"{" aria-sort=ascending" if h == "rank" else ""}>'
        f"<button type=button>{h}</button></th>" for h, c in heads)

    desc = (f"Which members of {clan} have cleared the most Destiny 2 raids "
            f"together — a live catalogue built from Bungie's API.")

    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<meta name="description" content="{{DESC}}">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{DESC}}">
<meta property="og:type" content="website">
{{OGURL}}<link rel="icon" href="{{FAVICON}}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>{{CSS}}</style>
</head>
<body>
{{SKY}}
<main class="page">
  <h1 class="mark">{{CLAN}}</h1>
  <p class="lede">{{LEDE}}</p>

  {{CONSTELLATION}}
  <p class="caption wide">{{CAPTION}}</p>
  <p class="caption narrow">{{CAPTION_N}}</p>

  <table class="catalogue">
    <caption>Every member, brightest first. Sort by any column.</caption>
    <thead><tr>{{THEAD}}</tr></thead>
    <tbody>{{TBODY}}</tbody>
  </table>

  <p class="note">{{NOTE}}</p>
</main>
<script>{{JS}}</script>
</body>
</html>"""

    note = ("Faded names have a private Bungie profile. Their raids don't show "
            "up, and every run they were in counts one short for everyone else "
            "too. Turning on \u201cShow my progression\u201d in Bungie privacy "
            "settings fixes it. Only people currently in the clan are counted. "
            "Built from Bungie's API, " + ordinal_date(now) + ".")

    caption = ("The brightest members, sized by raids cleared together. "
               "A line joins two people when one is the other's most frequent "
               "company in a raid.")
    caption_n = ("The brightest few, sized by raids cleared together. "
                 "A line joins two people who raid together most.")
    map_html, map_js = graph_block(rows, pairs)
    if map_html:
        hero = (map_html + '<noscript>' + constellation(rows) + '</noscript>'
                + constellation(rows, n=5, w=560, h=640, font=22, cls="narrow", short=True))
        caption = ("Everyone with a clan raid to their name, joined to the people "
                   "they cleared them with. Thicker lines mean more raids together. "
                   "Drag anyone; hover to pick out one person's connections.")
    else:
        hero = (constellation(rows)
                + constellation(rows, n=5, w=560, h=640, font=22, cls="narrow", short=True))

    subs = {
        "{{TITLE}}": escape(f"{clan} clan raids"),
        "{{DESC}}": escape(desc),
        "{{OGURL}}": (f'<meta property="og:url" content="{escape(page_url)}">\n'
                      if page_url else ""),
        "{{FAVICON}}": FAVICON,
        "{{CSS}}": CSS,
        "{{JS}}": JS + map_js,
        "{{SKY}}": starfield(),
        "{{CLAN}}": escape(clan),
        "{{LEDE}}": escape(lede),
"{{CONSTELLATION}}": hero,
        "{{CAPTION}}": caption,
        "{{CAPTION_N}}": caption_n,
        "{{THEAD}}": thead,
        "{{TBODY}}": "".join(body),
        "{{NOTE}}": note,
    }
    for k, v in subs.items():
        html = html.replace(k, v)
    return html
