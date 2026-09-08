"""
The interactive raid map: every member who has cleared a clan raid, drawn as a
star, joined to everyone they've raided with. Drag anyone.

Written as a small hand-rolled force simulation on a 2D canvas rather than
pulling in d3 — 55 nodes is well under the size where a library earns its
weight, and the drawing has to match the star field around it anyway.
"""

import json

GRAPH_JS = r"""
(function () {
  var canvas = document.getElementById('map');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var N = __NODES__, E = __EDGES__;
  if (!N.length) return;

  var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = 0, H = 520, dpr = Math.min(window.devicePixelRatio || 1, 2);
  var peak = N.reduce(function (m, n) { return Math.max(m, n.c); }, 1);
  var heaviest = E.reduce(function (m, e) { return Math.max(m, e[2]); }, 1);

  // Deterministic start, so the map opens the same way every time.
  function rand(a) { return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    var t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }; }
  var rng = rand(20260908);

  N.forEach(function (n, i) {
    var a = i / N.length * Math.PI * 2;
    n.x = 500 + Math.cos(a) * (150 + rng() * 90);
    n.y = 260 + Math.sin(a) * (110 + rng() * 70);
    n.vx = n.vy = 0;
    n.r = 3 + 8.5 * Math.sqrt(n.c / peak);
    n.deg = 0;
  });
  E.forEach(function (e) { N[e[0]].deg += e[2]; N[e[1]].deg += e[2]; });

  var alpha = 1, held = null, hover = null, pointer = { x: 0, y: 0 };

  function step() {
    for (var i = 0; i < N.length; i++) {
      var a = N[i], fx = 0, fy = 0;
      for (var j = 0; j < N.length; j++) {
        if (i === j) continue;
        var b = N[j], dx = a.x - b.x, dy = a.y - b.y;
        var d2 = dx * dx + dy * dy; if (d2 < 25) d2 = 25;
        var f = 11000 / d2, d = Math.sqrt(d2);
        fx += dx / d * f; fy += dy / d * f;
      }
      fx += (W / 2 - a.x) * 0.0016;
      fy += (H / 2 - a.y) * 0.0034;
      a.vx = (a.vx + fx * alpha) * 0.86;
      a.vy = (a.vy + fy * alpha) * 0.86;
    }
    for (var k = 0; k < E.length; k++) {
      var e = E[k], p = N[e[0]], q = N[e[1]];
      var dx = q.x - p.x, dy = q.y - p.y, d = Math.hypot(dx, dy) || 1;
      var rest = 210 - 95 * Math.sqrt(e[2] / heaviest);
      var f = (d - rest) * 0.013 * alpha * Math.min(1, e[2] / 3 + 0.35);
      p.vx += dx / d * f; p.vy += dy / d * f;
      q.vx -= dx / d * f; q.vy -= dy / d * f;
    }
    for (var m = 0; m < N.length; m++) {
      var n = N[m];
      if (n === held) continue;
      n.x += n.vx; n.y += n.vy;
      var pad = n.r + 8;
      n.x = Math.max(pad, Math.min(W - pad, n.x));
      n.y = Math.max(pad, Math.min(H - pad, n.y));
    }
    alpha *= 0.994;
  }

  var LABEL = 5;  // always-labelled: the brightest few
  function draw() {
    ctx.clearRect(0, 0, W, H);
    var lit = hover || held;
    var near = null;
    if (lit) { near = {}; near[N.indexOf(lit)] = 1; }

    for (var k = 0; k < E.length; k++) {
      var e = E[k], p = N[e[0]], q = N[e[1]];
      var w = Math.sqrt(e[2] / heaviest);
      var on = lit && (p === lit || q === lit);
      if (lit && !on) ctx.strokeStyle = 'rgba(127,168,255,' + (0.03 + 0.04 * w) + ')';
      else if (on) {
        ctx.strokeStyle = 'rgba(160,196,255,' + (0.35 + 0.45 * w) + ')';
        near[e[0]] = 1; near[e[1]] = 1;
      } else ctx.strokeStyle = 'rgba(127,168,255,' + (0.10 + 0.42 * w) + ')';
      ctx.lineWidth = 0.4 + 1.5 * w;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
    }

    for (var i = 0; i < N.length; i++) {
      var n = N[i];
      var dim = lit && !near[i];
      var halo = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 3.2);
      halo.addColorStop(0, 'rgba(247,227,181,' + (dim ? 0.05 : 0.16) + ')');
      halo.addColorStop(1, 'rgba(240,198,116,0)');
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 3.2, 0, 6.2832); ctx.fill();
      ctx.fillStyle = dim ? 'rgba(255,251,240,.28)' : '#FFFBF0';
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 6.2832); ctx.fill();
    }

    ctx.font = '500 13px "IBM Plex Sans", system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    var boxes = [];
    for (var i = 0; i < N.length; i++) {
      var n = N[i];
      var show = n === lit || (!lit && i < LABEL) || (lit && near[i]);
      if (!show) continue;
      var tw = ctx.measureText(n.n).width;
      var opts = [], dys = [0, -26, 26, -50, 50, -78, 78];
      for (var v = 0; v < dys.length; v++) {
        var yy = n.y + dys[v];
        opts.push([n.x + n.r + 9, yy, 0], [n.x - n.r - 9, yy, 1]);
      }
      var pick = null;
      for (var v = 0; v < opts.length; v++) {
        var o = opts[v], flipv = o[2] === 1;
        var bx0 = flipv ? o[0] - tw : o[0], by0 = o[1] - 15;
        if (bx0 < 2 || bx0 + tw > W - 2 || by0 < 2 || by0 + 30 > H - 2) continue;
        var bad = false;
        for (var q = 0; q < boxes.length && !bad; q++) {
          var c = boxes[q];
          bad = bx0 < c[0] + c[2] && bx0 + tw > c[0] &&
                by0 < c[1] + c[3] && by0 + 30 > c[1];
        }
        for (var z = 0; z < N.length && !bad; z++) {
          var o2 = N[z];
          if (o2 === n) continue;
          bad = o2.x + o2.r + 2 > bx0 && o2.x - o2.r - 2 < bx0 + tw &&
                o2.y + o2.r + 2 > by0 && o2.y - o2.r - 2 < by0 + 30;
        }
        if (!bad) { pick = [o[0], o[1], flipv, bx0, by0]; break; }
      }
      // Ranks 1-5 and whatever is lit always get drawn, even if crowded.
      var mustShow = n === lit || (!lit && i < LABEL);
      if (!pick && !mustShow) continue;
      if (!pick) {
        var flipf = n.x + n.r + 12 + tw > W - 4;
        pick = [flipf ? n.x - n.r - 9 : n.x + n.r + 9, n.y, flipf,
                flipf ? n.x - n.r - 9 - tw : n.x + n.r + 9, n.y - 15];
      }
      var lx = pick[0], flip = pick[2];
      var ly = pick[1];
      boxes.push([pick[3], pick[4], tw, 30]);
      ctx.textAlign = flip ? 'right' : 'left';
      ctx.fillStyle = n === lit ? '#FFFBF0' : 'rgba(238,242,255,.82)';
      ctx.fillText(n.n, lx, ly - 6);
      ctx.fillStyle = 'rgba(240,198,116,' + (n === lit ? 1 : .72) + ')';
      ctx.fillText(n.c, lx, ly + 9);
    }
  }

  function frame() {
    if (alpha > 0.004 || held) { step(); draw(); }
    requestAnimationFrame(frame);
  }

  function resize() {
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    alpha = Math.max(alpha, 0.35);
    draw();
  }

  function at(ev) {
    var b = canvas.getBoundingClientRect();
    pointer.x = ev.clientX - b.left; pointer.y = ev.clientY - b.top;
    var best = null, bd = 1e9;
    for (var i = 0; i < N.length; i++) {
      var n = N[i], d = Math.hypot(n.x - pointer.x, n.y - pointer.y);
      if (d < Math.max(n.r + 9, 14) && d < bd) { bd = d; best = n; }
    }
    return best;
  }

  canvas.addEventListener('pointermove', function (ev) {
    if (held) {
      var b = canvas.getBoundingClientRect();
      held.x = ev.clientX - b.left; held.y = ev.clientY - b.top;
      held.vx = held.vy = 0; alpha = Math.max(alpha, 0.55);
      return;
    }
    var was = hover; hover = at(ev);
    canvas.style.cursor = hover ? 'grab' : 'default';
    if (was !== hover) draw();
  });
  canvas.addEventListener('pointerdown', function (ev) {
    held = at(ev);
    if (held) {
      canvas.setPointerCapture(ev.pointerId);
      canvas.style.cursor = 'grabbing';
      alpha = Math.max(alpha, 0.55);
      ev.preventDefault();
    }
  });
  function release() {
    if (held) { held = null; canvas.style.cursor = 'default'; alpha = Math.max(alpha, 0.4); }
  }
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('pointerleave', function () {
    if (hover) { hover = null; draw(); }
  });

  window.addEventListener('resize', resize);
  resize();
  if (still) { for (var t = 0; t < 400; t++) step(); alpha = 0; draw(); }
  else frame();
})();
"""


def graph_block(rows, pairs, limit=60):
    """Canvas plus the data it draws. Members with no clan raids are left out."""
    ranked = [r for r in rows if r["count"] > 0][:limit]
    if len(ranked) < 3 or not pairs:
        return "", ""

    index = {r["name"]: i for i, r in enumerate(ranked)}
    nodes = [{"n": r["name"], "c": r["count"]} for r in ranked]
    edges = [[index[a], index[b], w] for a, b, w in pairs
             if a in index and b in index and w > 0]
    if not edges:
        return "", ""

    js = (GRAPH_JS
          .replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
          .replace("__EDGES__", json.dumps(edges)))
    html = ('<canvas id="map" class="map" width="1000" height="520" '
            'aria-label="A map of who has raided with whom. Each star is a '
            'member; lines join people who have cleared a raid together."'
            '></canvas>')
    return html, js
