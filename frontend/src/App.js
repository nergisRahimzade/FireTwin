/* Flame in Freefall frontend: ported from the single-file prototype artifact (same components,
   written with htm tagged templates instead of JSX). The 3D lab draws frontend/src/lab/core.js
   with React Three Fiber (lab/IssLabScene.jsx). */
import React, { Suspense, lazy, useState, useMemo, useEffect, useRef } from "react";
import htm from "htm";
import FALLBACK from "./data/fallback.json";
import * as LAB from "./lab/config.js";
// three.js and the 3D scene load only when someone opens the 3D ISS Lab tab.
const IssLabScene = lazy(() => import("./lab/IssLabScene.jsx").then(m => ({ default: m.IssLabScene })));
import { askReports } from "./api.js";

// Bundled data: master.csv rows, ranking.csv, and saved search results for the 5 demo questions.
const DATA = FALLBACK;
// htm passes HTML-style attribute names (class, maxlength, stroke-width). React wants camelCase
// names, so translate them once here instead of rewriting every template.
const RENAME = { class: "className", for: "htmlFor", tabindex: "tabIndex", maxlength: "maxLength" };
const camel = k => k.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
function h(type, props, ...children) {
  if (props) {
    const out = {};
    for (const k in props) out[RENAME[k] || (/^(aria|data)-/.test(k) || !k.includes("-") ? k : camel(k))] = props[k];
    props = out;
  }
  return React.createElement(type, props, ...children);
}
const html = htm.bind(h);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

const LAYOUTS = [["d1", "1 · Search-first portal"], ["d2", "2 · Story & lab"], ["d3", "3 · Three cards"]];
const EXPS = ["FLEX", "FLEX-2", "Saffire-II", "BASS-II"];
const EXP_COLOR = { "FLEX": "var(--e-flex)", "FLEX-2": "var(--e-flex2)", "Saffire-II": "var(--e-saf)", "BASS-II": "var(--e-bass)" };
const COLS = DATA.master.cols;
const ROWS = DATA.master.rows.map(r => Object.fromEntries(COLS.map((c, i) => [c, r[i]])));
const O2_MIN = 12, O2_MAX = 34;
const Q = Object.fromEntries(DATA.demo.map(d => [d.src + (d.q.includes("sample") ? "-size" : ""), d.q]));
// Starter tabs: each audience gets three of the five demo questions (the ones search answers well)
// and the view that suits it best.
const AUDIENCES = [
  { id: "edu", name: "For students & educators", view: "answer", qs: [DATA.demo[3].q, DATA.demo[2].q, DATA.demo[0].q] },
  { id: "res", name: "For researchers", view: "table", qs: [DATA.demo[4].q, DATA.demo[1].q, DATA.demo[2].q] },
  { id: "crew", name: "For astronaut fire safety", view: "charts", qs: [DATA.demo[0].q, DATA.demo[3].q, DATA.demo[4].q] },
];
const ATMOS = [["ISS air", 21, "21% O₂"], ["Lunar habitat", 32, "32% O₂"], ["Spacesuit", 100, "100% O₂"]];
const EXP_INFO = {
  "FLEX": { burned: "Heptane and methanol droplets", varied: "Oxygen, pressure and fire-suppressing gases (CO₂, He)", learned: "Flames kept burning more often at higher oxygen and less often with a suppressant." },
  "FLEX-2": { burned: "8 liquid fuels and fuel mixtures as droplets", varied: "Fuel, gas mix, pressure (0.5–3 atm), droplet size and spacing", learned: "Benchmark data for computer models of real, multi-part fuels." },
  "Saffire-II": { burned: "9 solid samples, 5 × 29 cm, on an uncrewed cargo ship", varied: "Material and airflow direction at 20–30 cm/s", learned: "Cotton-fiberglass fabric spread fastest (2.26 mm/s); silicone didn't spread." },
  "BASS-II": { burned: "Solid rods, slabs, films and fabrics in a small wind tunnel", varied: "Airflow up to 40 cm/s and oxygen lowered with nitrogen", learned: "Where flames went out as airflow and oxygen dropped, to test NASA's Earth-based screening." },
};

const STOP = new Set("what were was the in of a and how did does do is to for with each could which why run on by".split(" "));
const words = s => s.toLowerCase().match(/[a-z0-9-]+/g)?.filter(w => !STOP.has(w) && w.length > 2) || [];
const norm = w => w.toLowerCase().replace(/[^a-z0-9-]/g, "").replace(/s$/, "");
const highlight = (text, q) => { const t = new Set(words(q).map(norm)); return text.split(/(\s+)/).map((p, i) => t.has(norm(p)) && norm(p) ? html`<mark key=${i}>${p}</mark>` : p); };
function snippet(text, q, n = 44) {
  const ws = text.split(/\s+/), t = new Set(words(q).map(norm)); let best = 0, bs = -1;
  for (let i = 0; i === 0 || i + n <= ws.length; i++) { const sc = ws.slice(i, i + n).filter(w => t.has(norm(w))).length; if (sc > bs) { bs = sc; best = i; } if (i + n >= ws.length) break; }
  return (best > 0 ? "… " : "") + ws.slice(best, best + n).join(" ") + (best + n < ws.length ? " …" : "");
}
function answer(q) {
  const exact = DATA.demo.find(d => d.q.toLowerCase() === q.trim().toLowerCase()); if (exact) return exact;
  const qw = new Set(words(q)); let best = null, score = 0;
  for (const d of DATA.demo) { const s = words(d.q).filter(w => qw.has(w)).length; if (s > score) { score = s; best = d; } }
  return score >= 2 ? best : null;
}
const filterRows = (f, text = "") => ROWS.filter(r => (!f.exp || r.experiment === f.exp) && (!f.mat || r.material === f.mat) && r.oxygen_pct_max >= f.o2[0] && r.oxygen_pct_min <= f.o2[1]
  && (!text || `${r.experiment} ${r.material} ${r.outcome || ""} ${r.suppressant || ""}`.toLowerCase().includes(text.toLowerCase())));
const ALL_FILTERS = { exp: null, mat: null, o2: [O2_MIN, O2_MAX] };
const describe = f => [f.exp || "All experiments", f.mat || "all materials", `${f.o2[0]}–${f.o2[1]}% O₂`].join(" · ");

/* ---------------- background stars (static, quiet) ---------------- */
function Stars() {
  const ref = useRef();
  useEffect(() => { const c = ref.current, x = c.getContext("2d"), d = Math.min(devicePixelRatio || 1, 2);
    const draw = () => { c.width = innerWidth * d; c.height = innerHeight * d; x.scale(d, d); let s = 11; const r = () => (s = (s * 9301 + 49297) % 233280) / 233280;
      for (let i = 0; i < 110; i++) { x.globalAlpha = r() * .45 + .08; x.fillStyle = "#fff"; x.beginPath(); x.arc(r() * innerWidth, r() * innerHeight, r() * .9 + .2, 0, 6.283); x.fill(); } };
    draw(); addEventListener("resize", draw); return () => removeEventListener("resize", draw); }, []);
  return html`<canvas class="stars" ref=${ref} aria-hidden="true"></canvas>`;
}

/* ---------------- the blue diffusion flame ----------------
   An illustration, not a simulation of our data. g blends 0 g (sphere) and 1 g (teardrop);
   oxygen sets size and brightness. At most three labels. */
function Flame({ g, o2, labels = true, round = false }) {
  const ref = useRef(), st = useRef({});
  useEffect(() => { st.current.tg = g; st.current.to2 = o2; }, [g, o2]);
  useEffect(() => {
    const c = ref.current, ctx = c.getContext("2d"), dpr = Math.min(devicePixelRatio || 1, 2); let raf, w = 0, h = 0, t = 0;
    const ro = new ResizeObserver(() => { w = c.clientWidth; h = c.clientHeight; c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }); ro.observe(c);
    const s = st.current; s.g = s.tg; s.o2 = s.to2;
    const sparks = Array.from({ length: 30 }, () => ({ p: Math.random(), a: Math.random() * 6.28, r: Math.random() }));
    const pin = (x1, y1, x2, y2, text) => {
      const fs = w < 360 ? 12 : 12.5; ctx.font = `600 ${fs}px DM Sans, system-ui, sans-serif`; const right = x2 >= x1; ctx.textAlign = right ? "left" : "right";
      // Keep the label pill inside the canvas. In the round Design 1 stage, clamp to the
      // circle's chord at the pill's height so the corners never clip.
      const tw = ctx.measureText(text).width, bw = tw + 16; let lo = 10, hi = w - 10;
      if (round) { const r = Math.min(w, h) / 2, ccy = h / 2; y2 = Math.max(ccy - r * .78, Math.min(ccy + r * .78, y2));
        const dy = Math.max(Math.abs(y2 - 12 - ccy), Math.abs(y2 + 12 - ccy)), half = Math.sqrt(Math.max(0, r * r - dy * dy)) - 10; lo = w / 2 - half; hi = w / 2 + half; }
      let bx = right ? x2 + 6 : x2 - 6 - bw; bx = Math.max(lo, Math.min(hi - bw, bx));
      const ex = Math.max(bx, Math.min(bx + bw, x2));
      ctx.strokeStyle = "rgba(238,244,255,.55)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(ex, y2); ctx.stroke();
      ctx.fillStyle = "#EEF4FF"; ctx.beginPath(); ctx.arc(x1, y1, 3, 0, 6.283); ctx.fill();
      ctx.fillStyle = "rgba(3,5,10,.78)"; ctx.beginPath(); ctx.roundRect(bx, y2 - 12, bw, 24, 12); ctx.fill();
      ctx.textAlign = "left"; ctx.fillStyle = "#EEF4FF"; ctx.fillText(text, bx + 8, y2 + 4.5);
    };
    const draw = () => {
      t += REDUCED ? 0 : 1 / 60; s.g += (s.tg - s.g) * .07; s.o2 += (s.to2 - s.o2) * .07;
      if (!w) { raf = requestAnimationFrame(draw); return; }
      const G = s.g, k = Math.max(0, Math.min(1, (s.o2 - 12) / (55 - 12)));
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2, cy = h * (.5 + G * .12), base = Math.min(w, h) * (.2 + k * .1), R = base * (1 + Math.sin(t * 1.2) * .015), W2 = base * .62;
      ctx.globalCompositeOperation = "lighter";
      const sA = 1 - G;
      if (sA > .01) {
        let gr = ctx.createRadialGradient(cx, cy, R * .3, cx, cy, R * 2);
        gr.addColorStop(0, "rgba(60,140,255,0)"); gr.addColorStop(.5, `rgba(70,150,255,${(.14 + k * .12) * sA})`); gr.addColorStop(1, "rgba(110,80,255,0)");
        ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(cx, cy, R * 2, 0, 6.283); ctx.fill();
        gr = ctx.createRadialGradient(cx, cy, R * .78, cx, cy, R * 1.08);
        gr.addColorStop(0, "rgba(80,160,255,0)"); gr.addColorStop(.72, `rgba(120,200,255,${(.6 + k * .3) * sA})`); gr.addColorStop(1, "rgba(80,140,255,0)");
        ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(cx, cy, R * 1.08, 0, 6.283); ctx.fill();
        gr = ctx.createRadialGradient(cx, cy, R * .42, cx, cy, R * .62);
        gr.addColorStop(0, "rgba(255,140,60,0)"); gr.addColorStop(.6, `rgba(255,150,70,${(.1 + k * .4) * sA})`); gr.addColorStop(1, "rgba(255,120,40,0)");
        ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(cx, cy, R * .62, 0, 6.283); ctx.fill();
      }
      if (G > .01) {
        const H = base * 3.1, wob = (Math.sin(t * 9) * 3 + Math.sin(t * 5.3) * 2) * G;
        const layer = (sc, col, a) => { ctx.beginPath(); ctx.moveTo(cx, cy + base * .45 * sc);
          ctx.bezierCurveTo(cx - W2 * sc, cy + base * .35 * sc, cx - W2 * .8 * sc, cy - H * .35 * sc, cx + wob * sc, cy - H * sc);
          ctx.bezierCurveTo(cx + W2 * .8 * sc, cy - H * .35 * sc, cx + W2 * sc, cy + base * .35 * sc, cx, cy + base * .45 * sc);
          const lg = ctx.createLinearGradient(cx, cy + base * .45, cx, cy - H * sc); lg.addColorStop(0, `rgba(70,120,255,${a * .8})`); lg.addColorStop(.18, col.replace("A", a)); lg.addColorStop(1, col.replace("A", 0));
          ctx.fillStyle = lg; ctx.fill(); };
        layer(1.15, "rgba(255,110,30,A)", .45 * G); layer(.9, "rgba(255,170,60,A)", .7 * G); layer(.55, "rgba(255,240,190,A)", .85 * G);
        for (const sp of sparks) { sp.p = (sp.p + (REDUCED ? 0 : .004 + sp.r * .004)) % 1; const y = cy - sp.p * H * 1.4, x = cx + Math.sin(sp.a + sp.p * 6) * W2 * .6 * sp.p;
          ctx.fillStyle = `rgba(255,${150 + sp.r * 80},80,${(1 - sp.p) * .6 * G})`; ctx.beginPath(); ctx.arc(x, y, 1 + sp.r, 0, 6.283); ctx.fill(); }
      }
      ctx.globalCompositeOperation = "source-over";
      const dr = base * .11, dg = ctx.createRadialGradient(cx - dr * .3, cy - dr * .3, dr * .1, cx, cy, dr);
      dg.addColorStop(0, "#FFFFFF"); dg.addColorStop(.6, "#D7DDE8"); dg.addColorStop(1, "#7E8798");
      ctx.fillStyle = dg; ctx.shadowColor = "rgba(255,255,255,.7)"; ctx.shadowBlur = 14; ctx.beginPath(); ctx.arc(cx, cy, dr, 0, 6.283); ctx.fill(); ctx.shadowBlur = 0;
      if (labels && w >= 260) {
        if (G < .5) { pin(cx + R * .74, cy - R * .74, cx + R * 1.1, cy - R * 1.12, "Diffusion flame"); pin(cx - dr * .7, cy + dr * .7, cx - R * .9, cy + R * 1.0, "Fuel droplet"); }
        else { pin(cx + W2 * .2, cy - base * 1.7, cx + W2 * 1.1, cy - base * 2.2, "Hot gas rises"); pin(cx - dr * .7, cy + dr * .7, cx - base * .9, cy + base * .8, "Fuel droplet"); }
      }
      if (!REDUCED || Math.abs(s.g - s.tg) > .002 || Math.abs(s.o2 - s.to2) > .05) raf = requestAnimationFrame(draw);
    };
    draw(); return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [REDUCED ? `${g}-${o2}` : 0, labels, round]);
  return html`<canvas ref=${ref} role="img" aria-label=${`Illustration of a fuel droplet flame at ${o2}% oxygen in ${g === 0 ? "microgravity" : "Earth gravity"}`}></canvas>`;
}
function GravitySwitch({ g, setG }) {
  return html`<div class="seg" role="group" aria-label="Gravity"><button aria-pressed=${g === 0} onClick=${() => setG(0)}>0 g · ISS</button><button aria-pressed=${g === 1} onClick=${() => setG(1)}>1 g · Earth</button></div>`;
}
const flameLine = (g, o2) => g === 1 ? "On Earth, hot gas rises and pulls fresh air in, so the flame points up." : o2 > 34
  ? `At ${o2}% oxygen the flame grows bigger and brighter. Our data stops at 34%.`
  : "In orbit nothing rises, so oxygen drifts in from all sides and the flame becomes a dim blue sphere.";

/* ---------------- filter bar (collapsed by default) ---------------- */
function FilterBar({ f, setF, count }) {
  const [open, setOpen] = useState(false);
  const mats = useMemo(() => [...new Set(ROWS.filter(r => !f.exp || r.experiment === f.exp).map(r => r.material))].sort(), [f.exp]);
  const pct = v => (v - O2_MIN) / (O2_MAX - O2_MIN) * 100;
  const changed = f.exp || f.mat || f.o2[0] !== O2_MIN || f.o2[1] !== O2_MAX;
  return html`<div class="filterbar">
    <div class="summary"><button class="toggle-filters" aria-expanded=${open} aria-controls="fp" onClick=${() => setOpen(!open)}>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 3h12M3 7h8M5 11h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>Filter data</button>
      <span class="note">${describe(f)} · <b class="mono" style=${{ color: "var(--fg)" }}>${count}</b> of 419 records</span>
      ${changed && html`<button class="textbtn" onClick=${() => setF(ALL_FILTERS)}>Clear</button>`}</div>
    ${open && html`<div class="filter-panel" id="fp">
      <label class="field"><span class="label">Experiment</span><select class="sel" value=${f.exp || ""} onChange=${e => setF({ ...f, exp: e.target.value || null, mat: null })}>
        <option value="">All experiments</option>${EXPS.map(e => html`<option key=${e} value=${e}>${e}</option>`)}</select></label>
      <label class="field"><span class="label">Material</span><select class="sel" value=${f.mat || ""} onChange=${e => setF({ ...f, mat: e.target.value || null })}>
        <option value="">All materials</option>${mats.map(m => html`<option key=${m} value=${m}>${m}</option>`)}</select></label>
      <div class="field"><span class="label">Oxygen ${f.o2[0]}–${f.o2[1]}%</span><div class="range"><div class="track"><i style=${{ left: pct(f.o2[0]) + "%", right: 100 - pct(f.o2[1]) + "%" }}></i></div>
        <input type="range" min=${O2_MIN} max=${O2_MAX} step="0.5" value=${f.o2[0]} aria-label="Lowest oxygen" onInput=${e => setF({ ...f, o2: [Math.min(+e.target.value, f.o2[1]), f.o2[1]] })} />
        <input type="range" min=${O2_MIN} max=${O2_MAX} step="0.5" value=${f.o2[1]} aria-label="Highest oxygen" onInput=${e => setF({ ...f, o2: [f.o2[0], Math.max(+e.target.value, f.o2[0])] })} /></div></div>
      <button class="textbtn" onClick=${() => setOpen(false)}>Done</button></div>`}
  </div>`;
}

/* ---------------- search: box, chips, audience tabs ---------------- */
// Local answer from the bundled data: {q, src, results, summary} or null.
function localHit(q) { const h = answer(q); return h ? { ...h, summary: DATA.summary[h.q] } : null; }
function useAsk(initial) {
  const [asked, setAsked] = useState(initial), [hit, setHit] = useState(() => localHit(initial)), [loading, setLoading] = useState(false), seq = useRef(0);
  const ask = q => {
    if (!q.trim()) return;
    const n = ++seq.current; setLoading(true);
    askReports(q, localHit).then(h => { if (n !== seq.current) return; setAsked(q); setHit(h); setLoading(false); });
  };
  return { asked, hit, loading, ask };
}
function SearchBox({ s, aud, setAud, onAudience, label = "Ask the NASA reports" }) {
  const [q, setQ] = useState(s.asked);
  useEffect(() => setQ(s.asked), [s.asked]);
  const a = AUDIENCES.find(x => x.id === aud);
  return html`<div class="starters">
    <form class="search" role="search" onSubmit=${e => { e.preventDefault(); s.ask(q); }}>
      <input value=${q} onInput=${e => setQ(e.target.value)} aria-label=${label} placeholder=${label + "…"} maxlength="300" /><button type="submit">Ask</button></form>
    <div class="tabs small" role="tablist" aria-label="Start here">${AUDIENCES.map(x => html`<button key=${x.id} role="tab" aria-selected=${aud === x.id} onClick=${() => { setAud(x.id); onAudience && onAudience(x); s.ask(x.qs[0]); }}>${x.name}</button>`)}</div>
    <div class="chips">${a.qs.map(qq => html`<button key=${qq} class="chip" aria-current=${s.asked === qq} onClick=${() => s.ask(qq)}>${qq}</button>`)}</div>
  </div>`;
}
function Answer({ s, f, compact }) {
  const hit = s.hit, filtered = hit && f.exp && hit.src !== f.exp;
  const results = hit ? hit.results.filter(r => !f.exp || r.exp === f.exp) : [];
  if (s.loading) return html`<div><div class="skel" style=${{ width: "90%" }}></div><div class="skel" style=${{ width: "70%" }}></div><div class="skel" style=${{ width: "80%" }}></div></div>`;
  if (!hit || filtered || !results.length) return html`<div class="empty"><strong>Not found in the reports.</strong>The passages don't answer this${filtered ? ` within ${f.exp}` : ""}. Try one of the starter questions${f.exp ? ", or clear the experiment filter" : ""}.</div>`;
  const sum = hit.summary;
  if (compact) { const [t, src] = sum[0]; return html`<div style=${{ display: "grid", gap: "10px" }}><p class="big-takeaway">${t}</p>
    <span class="note">Quoted from the <b style=${{ color: "var(--fg)" }}>${src}</b> report, page 1 · match ${results[0].score.toFixed(2)}</span></div>`; }
  return html`<div class="answer">
    <div class="takeaways"><span class="label">Plain-English takeaways</span><ul>${sum.map(([t, src, p], i) => html`<li key=${i}>${t}<span class="cite">${src} · p.${p}</span></li>`)}</ul>
      <p class="note">Quoted word for word from the passages. With a Gemini key, the live app writes these as AI summaries.</p></div>
    <div class="evidence"><span class="label">Evidence · ${results.length} passage${results.length > 1 ? "s" : ""}</span>
      ${results.map(r => html`<article class="ev" key=${r.id}><header><span class="dot" style=${{ background: EXP_COLOR[r.exp] }}></span><b>${r.exp}</b> report · page 1 · match ${r.score.toFixed(2)}</header><p>${highlight(snippet(r.text, s.asked), s.asked)}</p></article>`)}</div>
  </div>`;
}

/* ---------------- charts + table ---------------- */
// Charts draw at their real pixel width (one SVG unit = one pixel), so text stays 11px on phones.
function useWidth(max) {
  const [el, setEl] = useState(null), [w, setW] = useState(max);
  useEffect(() => { if (!el) return; const ro = new ResizeObserver(() => setW(Math.round(Math.max(280, Math.min(max, el.clientWidth || max))))); ro.observe(el); return () => ro.disconnect(); }, [el, max]);
  return [setEl, w];
}
function Survival({ f }) {
  const [tip, setTip] = useState(null), ok = !f.exp || f.exp === "FLEX", [box, BW] = useWidth(560);
  const pts = DATA.ranking.filter(r => r.experiment === "FLEX" && (!f.mat || r.material === f.mat) && r.oxygen_pct >= f.o2[0] && r.oxygen_pct <= f.o2[1]);
  const W = BW, H = BW < 420 ? 250 : 300, L = 44, R = 14, T = 12, B = 40, x = v => L + (v - 12) / 22 * (W - L - R), y = v => T + (1 - v) * (H - T - B);
  const fuels = [["Heptane", "var(--accent)"], ["Methanol", "var(--accent-2)"]];
  if (!ok) return html`<div class="empty"><strong>Only FLEX recorded how each flame ended.</strong>Clear the experiment filter or choose FLEX to see this chart.</div>`;
  return html`<div style=${{ display: "grid", gap: "12px" }}>
    <div class="legend">${fuels.map(([n, c], i) => html`<span key=${n}><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke=${c} stroke-width="2" stroke-dasharray=${i ? "4 3" : "0"} /></svg>${n}</span>`)}<span>Dot size = number of tests</span></div>
    <div class="chart-box" ref=${box}><div style=${{ position: "relative" }}><svg class="chart" viewBox=${`0 0 ${W} ${H}`} role="img" aria-label="Share of FLEX tests where the flame kept burning, by oxygen level">
      ${[0, .5, 1].map(v => html`<g key=${v}><line class="grid" x1=${L} x2=${W - R} y1=${y(v)} y2=${y(v)} /><text x=${L - 8} y=${y(v) + 4} text-anchor="end">${v * 100}%</text></g>`)}
      ${[12, 16, 20, 24, 28, 32].map(v => html`<text key=${v} x=${x(v)} y=${H - B + 18} text-anchor="middle">${v}%</text>`)}
      <text x=${(L + W - R) / 2} y=${H - 4} text-anchor="middle">Oxygen</text>
      <line x1=${x(21)} x2=${x(21)} y1=${T} y2=${H - B} stroke="var(--faint)" stroke-dasharray="3 4" /><text x=${x(21) + 6} y=${T + 11}>Earth air</text>
      ${fuels.map(([n, c], i) => { const s = pts.filter(p => p.material === n).sort((a, b) => a.oxygen_pct - b.oxygen_pct); if (!s.length) return null;
        return html`<g key=${n}><polyline fill="none" stroke=${c} stroke-width="1.8" stroke-dasharray=${i ? "5 4" : "0"} opacity=".7" points=${s.map(p => `${x(p.oxygen_pct)},${y(p.risk_value)}`).join(" ")} />
          ${s.map(p => html`<circle key=${p.oxygen_pct} cx=${x(p.oxygen_pct)} cy=${y(p.risk_value)} r=${3 + Math.sqrt(p.tests) * 1.3} fill=${c} stroke="var(--bg)" stroke-width="1.5"
            onMouseEnter=${() => setTip({ x: x(p.oxygen_pct) / W * 100, y: y(p.risk_value) / H * 100, t: `${n} · ${p.oxygen_pct}% O₂ · kept burning ${Math.round(p.risk_value * 100)}% · ${p.tests} tests` })} onMouseLeave=${() => setTip(null)} />`)}</g>`; })}
    </svg>${tip && html`<div class="tip" style=${{ left: `clamp(110px, ${tip.x}%, calc(100% - 110px))`, top: tip.y + "%" }}>${tip.t}</div>`}</div></div>
    ${!pts.length && html`<div class="empty">No FLEX tests in this oxygen range.</div>`}
    <p class="note">FLEX droplets: share of finished tests where the flame burned until the fuel was gone.</p></div>`;
}
function Spread({ f }) {
  const ok = !f.exp || f.exp === "Saffire-II", bars = DATA.ranking.filter(r => r.experiment === "Saffire-II" && (!f.mat || r.material === f.mat)).sort((a, b) => b.risk_value - a.risk_value);
  const [box, BW] = useWidth(520);
  if (!ok || !bars.length) return html`<div class="empty" ref=${box}><strong>No spread ranking for this filter.</strong>Saffire-II's four solids are the only ranked materials.</div>`;
  // Narrow screens: material name sits above its bar instead of beside it
  const W = BW, narrow = W < 440, L = narrow ? 0 : 168, RR = 90, rowH = narrow ? 62 : 52, H = bars.length * rowH + 8, x = v => v / 2.5 * (W - L - RR), by = narrow ? 24 : 6;
  return html`<div style=${{ display: "grid", gap: "12px" }}><div class="chart-box" ref=${box}><svg class="chart" viewBox=${`0 0 ${W} ${H}`} role="img" aria-label="Average flame spread by Saffire-II material">
    ${bars.map((b, i) => { const yy = i * rowH + 6, w = Math.max(x(b.risk_value), 3); return html`<g key=${b.material}>
      <text x=${narrow ? 0 : L - 12} y=${narrow ? yy + 12 : yy + 21} text-anchor=${narrow ? "start" : "end"} style=${{ fill: "var(--fg)", fontFamily: "var(--f-body)", fontSize: "13px" }}>${b.material}</text>
      <rect x=${L} y=${yy + by} width=${w} height="22" rx="11" fill=${i === 0 ? "var(--risk)" : "var(--accent)"} opacity=${i === 0 ? 1 : .55} />
      <text x=${L + w + 10} y=${yy + by + 15} style=${{ fill: "var(--fg)" }}>${b.risk_value.toFixed(2)} mm/s</text></g>`; })}
  </svg></div><p class="note">Saffire-II solids, average flame spread at about 22% oxygen and 20 cm/s airflow.</p></div>`;
}
function Table({ rows }) {
  const [sort, setSort] = useState({ k: null, d: 1 });
  const shown = useMemo(() => (sort.k ? [...rows].sort((a, b) => { const p = a[sort.k], q = b[sort.k]; if (p == null) return 1; if (q == null) return -1; return (p > q ? 1 : p < q ? -1 : 0) * sort.d; }) : rows).slice(0, 100), [rows, sort]);
  const head = [["experiment", "Experiment"], ["material", "Material"], ["oxygen_pct_min", "O₂ %"], ["pressure_kpa_min", "kPa"], ["flow_cm_s_max", "Airflow cm/s"], ["suppressant", "Suppressant"], ["outcome", "Outcome"]];
  const num = k => ["oxygen_pct_min", "pressure_kpa_min", "flow_cm_s_max"].includes(k);
  const cell = (r, k) => { const v = r[k];
    if (v == null) return html`<td key=${k} class=${num(k) ? "num na" : "na"}>—</td>`;
    if (k === "experiment") return html`<td key=${k}><span class="dot" style=${{ background: EXP_COLOR[v], marginRight: "8px" }}></span>${v}</td>`;
    if (k === "oxygen_pct_min" && r.oxygen_pct_max !== v) return html`<td key=${k} class="num">${v}–${r.oxygen_pct_max}</td>`;
    if (k === "pressure_kpa_min" && r.pressure_kpa_max != null && r.pressure_kpa_max !== v) return html`<td key=${k} class="num">${v}–${r.pressure_kpa_max}</td>`;
    if (k === "flow_cm_s_max" && r.flow_cm_s_min != null && r.flow_cm_s_min !== v) return html`<td key=${k} class="num">${r.flow_cm_s_min}–${v}</td>`;
    return html`<td key=${k} class=${num(k) ? "num" : ""}>${v}</td>`; };
  if (!rows.length) return html`<div class="empty"><strong>No records match.</strong>Clear the filters to see all 419.</div>`;
  return html`<${React.Fragment}><div class="table-wrap" tabindex="0" aria-label="Experiment records"><table>
    <thead><tr>${head.map(([k, l]) => html`<th key=${k} aria-sort=${sort.k === k ? (sort.d > 0 ? "ascending" : "descending") : "none"}><button onClick=${() => setSort({ k, d: sort.k === k ? -sort.d : 1 })}>${l}${sort.k === k ? (sort.d > 0 ? " ↑" : " ↓") : ""}</button></th>`)}</tr></thead>
    <tbody>${shown.map((r, i) => html`<tr key=${i}>${head.map(([k]) => cell(r, k))}</tr>`)}</tbody></table></div>
    ${rows.length > 100 && html`<p class="note" style=${{ marginTop: "10px" }}>Showing the first 100 of ${rows.length}. Sort a column or filter to narrow it down.</p>`}</${React.Fragment}>`;
}

/* ---------------- 3D ISS lab ---------------- */
// Burn probability from our data: share of FLEX tests near this oxygen level where the flame kept burning.
function burnFromData(o2) {
  if (o2 < O2_MIN - 0.5 || o2 > O2_MAX + 0.5) return null;
  const pts = DATA.ranking.filter(r => r.experiment === "FLEX" && Math.abs(r.oxygen_pct - o2) <= 1.5);
  const n = pts.reduce((s, p) => s + p.tests, 0);
  return n ? { p: pts.reduce((s, p) => s + p.risk_value * p.tests, 0) / n, tests: n } : null;
}
function Lab() {
  const clockEl = useRef(), api = useRef(null);
  const [status, setStatus] = useState("loading"), [g, setG] = useState(0), [o2, setO2] = useState(21), [flow, setFlow] = useState("fore"), [manual, setManual] = useState(null);
  const [phase, setPhase] = useState("idle"), [hits, setHits] = useState({});
  const est = useMemo(() => burnFromData(o2), [o2]), burnP = manual != null ? manual : est ? est.p : 0.5;
  // React state changes only on lab events (ignite, out, detect), never per frame.
  const onEvent = useMemo(() => ev => {
    if (ev.type === "ignite") setPhase("burning");
    else if (ev.type === "out") setPhase("out");
    else if (ev.type === "detect") setHits(hh => ({ ...hh, [ev.id]: ev.t }));
  }, []);
  const params = useMemo(() => ({ g, o2, flow, burnP }), [g, o2, flow, burnP]);
  const reset = () => { if (api.current) api.current.reset(); setPhase("idle"); setHits({}); };
  const fl = LAB.AIRFLOW.find(a => a.id === flow), first = Object.entries(hits).sort((a, b) => a[1] - b[1])[0];
  const line = phase === "idle" ? "Press Ignite to light a sample at the fire source, then watch where the smoke goes."
    : phase === "out" ? "The flame went out on its own (extinction). Its smoke keeps drifting."
    : `Burning at ${o2}% oxygen in ${g ? "Earth gravity" : "microgravity"}.`;
  const why = !fl.fans ? (g ? " With the fans off, hot smoke still rises to the overhead." : " With the fans off nothing moves the smoke in 0 g, so it hangs around the fire and no vent may ever see it.")
    : first ? ` ${first[0]} detected smoke first, ${first[1].toFixed(1)} s after ignition.`
    : g && flow === "aft" && phase !== "idle" ? " In 1 g hot smoke rises, away from the deck vent, so vent_2 may never see it." : "";
  return html`<div class="glass lab3d">
    <div class="lab3d-view">
      <div class="lab3d-canvas"><${Suspense} fallback=${null}><${IssLabScene} params=${params} api=${api} clockEl=${clockEl} onEvent=${onEvent} onReady=${() => setStatus("ready")} /></${Suspense}></div>
      <div class="lab3d-hud">
        <button class="btn-primary" disabled=${status !== "ready" || phase === "burning"} onClick=${() => api.current && api.current.ignite()}>${phase === "out" ? "Re-ignite" : "Ignite"}</button>
        <button class="btn-ghost" disabled=${status !== "ready" || phase === "idle"} onClick=${reset}>Reset</button>
        <span class="clock mono">t = <span ref=${clockEl}>0.0</span> s</span>
      </div>
      ${status !== "ready" && html`<div class="lab3d-msg">${status === "fail" ? "The 3D view couldn't start here (WebGL is off). Everything else on the page still works." : "Loading the ISS module…"}</div>`}
    </div>
    <div class="lab3d-controls">
      <div class="field"><span class="label">Gravity</span><${GravitySwitch} g=${g} setG=${setG} /></div>
      <label class="field"><span class="label">Oxygen ${o2}%${o2 === 21 ? " · ISS air" : ""}</span>
        <div class="range single"><div class="track"><i style=${{ left: 0, right: 100 - ((o2 - 12) / 43) * 100 + "%" }}></i></div>
          <input type="range" min="12" max="55" step="1" value=${o2} aria-label="Oxygen percent" onInput=${e => { setO2(+e.target.value); setManual(null); }} /></div></label>
      <label class="field"><span class="label">Airflow direction</span>
        <select class="sel" value=${flow} onChange=${e => setFlow(e.target.value)}>${LAB.AIRFLOW.map(a => html`<option key=${a.id} value=${a.id}>${a.label}</option>`)}</select></label>
      <div class="field"><span class="label">Burn probability ${Math.round(burnP * 100)}%</span>
        <div class="range single"><div class="track"><i style=${{ left: 0, right: 100 - burnP * 100 + "%" }}></i></div>
          <input type="range" min="0" max="100" step="1" value=${Math.round(burnP * 100)} aria-label="Burn probability percent" onInput=${e => setManual(+e.target.value / 100)} /></div>
        <span class="note">${manual != null ? html`<span>Set by hand. ${est ? html`<button class="textbtn" onClick=${() => setManual(null)}>Use our data</button>` : ""}</span>` : est ? `From FLEX: flames kept burning in ${Math.round(est.p * 100)}% of ${est.tests} tests near ${o2}% O₂.` : "No FLEX tests at this oxygen level, so this is a guess. Drag to set it."}</span></div>
    </div>
    <div class="lab3d-status">
      <p class="line">${line}${why}</p>
      <div class="detectors">${LAB.VENTS.map(v => html`<span key=${v.id} class=${"det" + (hits[v.id] != null ? " hit" : "")}><span class="dot"></span><b class="mono">${v.id}</b>${v.where} · ${hits[v.id] != null ? `smoke at ${hits[v.id].toFixed(1)} s` : "clear"}</span>`)}</div>
      <p class="note">Drag to look around, scroll or pinch to zoom. Module ${LAB.MODULE.length} m × ${LAB.MODULE.diameter} m, origin at its center, vents at ${LAB.VENTS.map(v => `${v.id} [${v.pos.join(", ")}]`).join(", ")}. An illustration with a simple airflow model, not a fire simulation; the clock runs ${LAB.TIME_SCALE}× real time.</p>
    </div>
  </div>`;
}

/* ---------------- Design 1: search-first portal ---------------- */
function D1() {
  const [g, setG] = useState(0), [aud, setAud] = useState("edu"), [tab, setTab] = useState("answer"), [f, setF] = useState(ALL_FILTERS);
  const s = useAsk(AUDIENCES[0].qs[0]); const rows = useMemo(() => filterRows(f), [f]);
  return html`<main class="page">
    <section class="d1-hero">
      <div class="d1-left">
        <span class="label">NASA PSI · Microgravity combustion</span>
        <h1>When fire floats, what keeps it <em>burning?</em></h1>
        <p class="lede">Ask the experiment reports in plain English, then check the answer against 419 real test records.</p>
        <${SearchBox} s=${s} aud=${aud} setAud=${setAud} onAudience=${x => setTab(x.view)} label="Ask the NASA reports" />
      </div>
      <div class="d1-flame-wrap"><div class="glass stage d1-flame"><${Flame} g=${g} o2=${21} round=${true} /></div><div class="grav"><${GravitySwitch} g=${g} setG=${setG} /></div></div>
    </section>
    <section style=${{ display: "grid", gap: "20px" }}>
      <div class="tabs" role="tablist" aria-label="Results view">
        ${[["answer", "AI summary & evidence"], ["charts", "Visual charts"], ["table", `Data table (${rows.length})`], ["lab", "3D ISS Lab"]].map(([id, l]) => html`<button key=${id} role="tab" aria-selected=${tab === id} onClick=${() => setTab(id)}>${l}</button>`)}</div>
      ${(tab === "charts" || tab === "table") && html`<${FilterBar} f=${f} setF=${setF} count=${rows.length} />`}
      ${tab === "answer" && html`<${Answer} s=${s} f=${f} />`}
      ${tab === "charts" && html`<div class="two"><div><h3 style=${{ fontSize: "1.1rem", marginBottom: "12px" }}>Does more oxygen keep flames alive?</h3><${Survival} f=${f} /></div>
        <div><h3 style=${{ fontSize: "1.1rem", marginBottom: "12px" }}>Which materials spread fire fastest?</h3><${Spread} f=${f} /></div></div>`}
      ${tab === "table" && html`<${Table} rows=${rows} />`}
      ${tab === "lab" && html`<${Lab} />`}
    </section>
  </main>`;
}

/* ---------------- Design 2: story & lab ---------------- */
function D2() {
  const [g, setG] = useState(0), [o2, setO2] = useState(21), [f, setF] = useState(ALL_FILTERS), [text, setText] = useState("");
  const rows = useMemo(() => filterRows(f, text), [f, text]);
  const counts = useMemo(() => Object.fromEntries(EXPS.map(e => [e, ROWS.filter(r => r.experiment === e).length])), []);
  const show = e => { setF({ ...ALL_FILTERS, exp: e }); document.getElementById("d2-data")?.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth" }); };
  return html`<main class="page narrow">
    <header class="d2-intro"><span class="label">NASA PSI · Microgravity combustion</span><h1>Fire behaves differently in space.</h1>
      <p>Start with one flame, see what four ISS experiments changed, then explore the 419 records they produced.</p></header>
    <section><div class="section-head"><span class="step">Step 1 · The lab</span><h2>Play with a flame</h2><p>Switch gravity off and change the oxygen. Watch the shape and brightness.</p></div>
      <div class="glass lab"><div class="stage"><${Flame} g=${g} o2=${o2} /></div>
        <div class="controls">
          <label class="field"><span class="label">Oxygen ${o2}%${o2 === 21 ? " · Earth air" : ""}</span>
            <div class="range single"><div class="track"><i style=${{ left: 0, right: 100 - (o2 - 12) / 43 * 100 + "%" }}></i></div>
              <input type="range" min="12" max="55" step="1" value=${o2} aria-label="Oxygen percent" onInput=${e => setO2(+e.target.value)} /></div></label>
          <${GravitySwitch} g=${g} setG=${setG} /></div>
        <p class="explain">${flameLine(g, o2)}</p></div></section>
    <section><div class="section-head"><span class="step">Step 2 · The experiments</span><h2>What each one changed</h2><p>Four investigations, each testing a different piece of the puzzle.</p></div>
      <div class="compare">${EXPS.map(e => html`<article key=${e} class="glass ccard"><h3><span class="dot" style=${{ background: EXP_COLOR[e], width: "10px", height: "10px" }}></span>${e}</h3>
        <dl><dt>Burned</dt><dd>${EXP_INFO[e].burned}</dd><dt>Changed</dt><dd>${EXP_INFO[e].varied}</dd><dt>Showed</dt><dd>${EXP_INFO[e].learned}</dd></dl>
        <button class="textbtn" style=${{ justifySelf: "start" }} onClick=${() => show(e)}>See its ${counts[e]} records →</button></article>`)}</div></section>
    <section id="d2-data"><div class="section-head"><span class="step">Step 3 · The data</span><h2>Look at the results</h2></div>
      <div class="glass" style=${{ padding: "26px", display: "grid", gap: "22px" }}>
        <div><h3 style=${{ fontSize: "1.1rem", marginBottom: "12px" }}>Does more oxygen keep flames alive?</h3><${Survival} f=${f} /></div>
        <div style=${{ display: "grid", gap: "14px" }}>
          <div class="search" style=${{ maxWidth: "460px" }}><input value=${text} onInput=${e => setText(e.target.value)} aria-label="Search records" placeholder="Search records, e.g. PMMA" /></div>
          <${FilterBar} f=${f} setF=${setF} count=${rows.length} />
          <${Table} rows=${rows} /></div></div></section>
  </main>`;
}

/* ---------------- Design 3: three cards ---------------- */
function D3() {
  const [g, setG] = useState(0), [atm, setAtm] = useState(0), [aud, setAud] = useState("edu"), [view, setView] = useState("chart"), [f, setF] = useState(ALL_FILTERS);
  const s = useAsk(AUDIENCES[0].qs[0]); const rows = useMemo(() => filterRows(f), [f]);
  const [name, o2, lab] = ATMOS[atm];
  return html`<main class="page">
    <header class="d3-head"><div style=${{ display: "grid", gap: "8px" }}><span class="label">NASA PSI · Microgravity combustion</span><h1>When fire floats, what keeps it burning?</h1></div></header>
    <section class="bento">
      <article class="glass c1"><div class="stage"><${Flame} g=${g} o2=${o2} /></div>
        <div class="foot"><div style=${{ display: "flex", flexWrap: "wrap", gap: "10px", justifyContent: "space-between", alignItems: "center" }}>
            <div class="seg full" role="group" aria-label="Atmosphere">${ATMOS.map(([n], i) => html`<button key=${n} aria-pressed=${atm === i} onClick=${() => setAtm(i)}>${n}</button>`)}</div>
            <${GravitySwitch} g=${g} setG=${setG} /></div>
          <p class="note">${name} · ${lab}. ${flameLine(g, o2)}</p></div></article>
      <article class="glass c2"><h2 style=${{ fontSize: "1.25rem" }}>Ask the reports</h2>
        <${SearchBox} s=${s} aud=${aud} setAud=${setAud} label="Ask a question" />
        <${Answer} s=${s} f=${ALL_FILTERS} compact=${true} /></article>
      <article class="glass c3"><div style=${{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "12px" }}>
          <h2 style=${{ fontSize: "1.25rem" }}>${view === "chart" ? "Flame survival vs. oxygen" : "All records"}</h2>
          <div class="seg" role="group" aria-label="View"><button aria-pressed=${view === "chart"} onClick=${() => setView("chart")}>Chart</button><button aria-pressed=${view === "table"} onClick=${() => setView("table")}>Table</button></div></div>
        ${view === "chart" ? html`<${Survival} f=${ALL_FILTERS} />` : html`<${React.Fragment}><${FilterBar} f=${f} setF=${setF} count=${rows.length} /><${Table} rows=${rows} /></${React.Fragment}>`}</article>
    </section>
  </main>`;
}

/* ---------------- app ---------------- */
function App() {
  const read = () => { try { return localStorage.getItem("fif-layout") || "d1"; } catch { return "d1"; } };
  const [lay, setLay] = useState(LAYOUTS.some(([id]) => id === read()) ? read() : "d1");
  useEffect(() => { try { localStorage.setItem("fif-layout", lay); } catch {} window.scrollTo(0, 0); }, [lay]);
  return html`<${React.Fragment}><${Stars} />
    <nav class="topbar" aria-label="Layout"><div class="switch">${LAYOUTS.map(([id, l]) => html`<button key=${id} aria-pressed=${lay === id} onClick=${() => setLay(id)}>${l}</button>`)}</div></nav>
    ${lay === "d1" ? html`<${D1} />` : lay === "d2" ? html`<${D2} />` : html`<${D3} />`}
    <p class="foot-note" style=${{ margin: "-60px auto 48px", padding: "0 max(20px, env(safe-area-inset-left, 0px))", maxWidth: "1120px" }}>Prototype. Records, rankings and passages are real (master.csv data v1.0, ranking.csv, and saved search results for the 5 demo questions; typed questions match the closest one). The flame is an illustration of the physics, not a simulation of our data. Atmosphere values come from the team brief and need checking against a NASA source.</p>
  </${React.Fragment}>`;
}
export default App;
