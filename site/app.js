/* scrapeboard dashboard.
 *
 * Plain browser JavaScript, no build step. The page loads five small JSON files
 * from ./data/ (written by `scrapeboard build`), keeps them in `state`, and
 * re-renders everything from state whenever the time-range filter, the theme,
 * or a background refresh changes something. Plotly.js draws the charts.
 */
"use strict";

const SOURCES = ["open_meteo", "hackernews", "github"];
const REFRESH_MS = 5 * 60 * 1000;        // re-fetch data every 5 minutes
const STALE_AFTER_H = 14;                // two missed 6-hour runs → warn
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];

const state = {
  manifest: null, runs: [], feeds: {},   // data
  rangeDays: "all",                       // filter
  colors: {},                             // entity → fixed hex, assigned once
};

const fmtInt = new Intl.NumberFormat("en-US");
const fmtTime = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" });
const $ = (sel) => document.querySelector(sel);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ── data ─────────────────────────────────────────────────────────────────────

async function fetchJSON(name) {
  const r = await fetch(`data/${name}.json?t=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${name}.json → HTTP ${r.status}`);
  return r.json();
}

async function loadAll() {
  const manifest = await fetchJSON("manifest");
  if (state.manifest && manifest.built_at === state.manifest.built_at) return false;
  const [runs, ...feeds] = await Promise.all([
    fetchJSON("runs"),
    ...SOURCES.map((s) => (manifest.sources[s] ? fetchJSON(s) : Promise.resolve(null))),
  ]);
  state.manifest = manifest;
  state.runs = runs;
  SOURCES.forEach((s, i) => {
    const feed = feeds[i];
    if (feed) feed.rows.forEach((row) => { row.t = new Date(row.observed_at); });
    state.feeds[s] = feed;
  });
  return true;
}

function rows(source) {
  const feed = state.feeds[source];
  return feed ? feed.rows : [];
}

function inRange(rowList) {
  if (state.rangeDays === "all" || rowList.length === 0) return rowList;
  const max = rowList.reduce((m, r) => (r.t > m ? r.t : m), rowList[0].t);
  const cutoff = new Date(max.getTime() - state.rangeDays * 86400e3);
  return rowList.filter((r) => r.t >= cutoff);
}

function latestRun(rowList) {
  if (rowList.length === 0) return [];
  const max = rowList.reduce((m, r) => (r.t > m ? r.t : m), rowList[0].t);
  return rowList.filter((r) => r.t.getTime() === max.getTime());
}

/** Colour follows the entity, never its rank: assign once, alphabetically, keep forever. */
function colorFor(entity) {
  if (!(entity in state.colors)) {
    const known = Object.keys(state.colors);
    state.colors[entity] = SERIES[known.length % SERIES.length];
  }
  return cssVar(state.colors[entity]);
}
function assignColors(entities) {
  [...new Set(entities)].sort().forEach(colorFor);
}

// ── chart chrome ─────────────────────────────────────────────────────────────

function baseLayout(extra) {
  const font = { family: cssVar("--font"), color: cssVar("--ink-2"), size: 13 };
  const axis = {
    gridcolor: cssVar("--grid"), zerolinecolor: cssVar("--axis"), linecolor: cssVar("--axis"),
    tickfont: { color: cssVar("--muted") }, tickcolor: cssVar("--axis"), ticklen: 4, automargin: true,
  };
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font,
    margin: { l: 8, r: 16, t: 8, b: 8 },
    xaxis: { ...axis }, yaxis: { ...axis },
    legend: { orientation: "h", y: 1.08, x: 0, font: { color: cssVar("--ink-2") } },
    hoverlabel: { bgcolor: cssVar("--surface"), bordercolor: cssVar("--axis"), font: { color: cssVar("--ink"), family: font.family } },
    ...extra,
  };
}
const CONFIG = { displayModeBar: false, responsive: true };

function empty(el, message) {
  el.innerHTML = "";
  const p = document.createElement("p");
  p.className = "empty";
  p.textContent = message;
  el.appendChild(p);
}

/** Lines + a text trace that labels each series at its last point (direct labels). */
function lineTraces(groups, yKey, hover) {
  const traces = [];
  for (const [name, pts] of groups) {
    const color = colorFor(name);
    traces.push({
      type: "scatter", mode: pts.length > 1 ? "lines+markers" : "markers", name,
      x: pts.map((p) => p.t), y: pts.map((p) => p[yKey]),
      line: { color, width: 2, shape: "linear" }, marker: { color, size: 7 },
      hovertemplate: hover,
    });
  }
  traces.push({
    type: "scatter", mode: "text", showlegend: false, hoverinfo: "skip",
    x: [...groups].map(([, pts]) => pts[pts.length - 1].t),
    y: [...groups].map(([, pts]) => pts[pts.length - 1][yKey]),
    text: [...groups].map(([name]) => name),
    textposition: "middle right", textfont: { color: cssVar("--ink-2"), size: 12 },
    cliponaxis: false,
  });
  return traces;
}

/** With one run the time axis would zoom to milliseconds; pad it to ±6 h. */
function timeRange(list) {
  if (list.length === 0) return undefined;
  let lo = list[0].t, hi = list[0].t;
  for (const r of list) { if (r.t < lo) lo = r.t; if (r.t > hi) hi = r.t; }
  if (hi - lo < 3600e3) return [new Date(lo - 6 * 3600e3), new Date(hi.getTime() + 6 * 3600e3)];
  return undefined;
}

function groupBy(list, key) {
  const m = new Map();
  for (const r of list) { if (!m.has(r[key])) m.set(r[key], []); m.get(r[key]).push(r); }
  for (const pts of m.values()) pts.sort((a, b) => a.t - b.t);
  return m;
}

// ── tables ───────────────────────────────────────────────────────────────────

function renderTable(table, columns, rowList) {
  table.innerHTML = "";
  const thead = table.createTHead().insertRow();
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c.label;
    if (c.num) th.className = "num";
    thead.appendChild(th);
  }
  const tbody = table.createTBody();
  for (const r of rowList) {
    const tr = tbody.insertRow();
    for (const c of columns) {
      const td = tr.insertCell();
      if (c.num) td.className = "num";
      if (c.swatch) {
        const s = document.createElement("span");
        s.className = "swatch";
        s.style.background = colorFor(r[c.swatch]);
        td.appendChild(s);
      }
      if (c.href) {
        const a = document.createElement("a");
        a.href = r[c.href]; a.textContent = c.value(r); a.rel = "noopener";
        td.appendChild(a);
      } else {
        td.appendChild(document.createTextNode(c.value(r)));
      }
    }
  }
}

// ── the pipeline hero ────────────────────────────────────────────────────────

function renderPipeline() {
  const bySource = {};
  for (const run of state.runs) (bySource[run.source] ??= []).push(run);

  for (const stage of document.querySelectorAll(".stage")) {
    const name = stage.dataset.source;
    const runs = (bySource[name] || []).slice(-20);
    const last = runs[runs.length - 1];
    const meta = state.manifest.sources[name];

    const body = stage.querySelector(".stage-body");
    body.innerHTML = "";
    const dl = document.createElement("dl");
    dl.className = "stage-body";
    const add = (k, v, cls) => {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v; if (cls) dd.className = cls;
      body.append(dt, dd);
    };
    if (!last) { add("status", "never run"); }
    else {
      add("last run", last.ok ? `ok, ${last.rows} rows in ${last.duration_s}s` : "failed", last.ok ? "ok" : "fail");
      if (!last.ok) add("error", last.error);
    }
    if (meta) {
      add("rows kept", fmtInt.format(meta.rows_total));
      add("runs", fmtInt.format(meta.runs));
      add("since", fmtTime.format(new Date(meta.first_observed)));
    }

    const strip = stage.querySelector(".runs");
    strip.innerHTML = "";
    for (let i = 0; i < 20; i++) {
      const cell = document.createElement("span");
      const run = runs[i - (20 - runs.length)];
      if (run) {
        cell.className = run.ok ? "ok" : "fail";
        cell.title = `${fmtTime.format(new Date(run.run_at))}: ${run.ok ? `${run.rows} rows, ${run.duration_s}s` : run.error}`;
      }
      strip.appendChild(cell);
    }
  }
}

function renderFreshness() {
  const el = $("#freshness");
  const times = Object.values(state.manifest.sources).map((s) => new Date(s.last_observed));
  if (times.length === 0) { el.textContent = "no data yet"; return; }
  const last = new Date(Math.max(...times));
  const mins = Math.round((Date.now() - last) / 60000);
  const rel = mins < 1 ? "just now" : mins < 60 ? `${mins} min ago` : mins < 2880 ? `${Math.round(mins / 60)} h ago` : `${Math.round(mins / 1440)} days ago`;
  el.textContent = `last scraped ${rel}`;
  el.title = fmtTime.format(last);
  el.classList.toggle("stale", mins > STALE_AFTER_H * 60);
  $("#built-at").textContent = fmtTime.format(new Date(state.manifest.built_at));
}

// ── weather ──────────────────────────────────────────────────────────────────

function renderWeather() {
  const el = $("#chart-weather");
  const all = rows("open_meteo");
  if (all.length === 0) return empty(el, "No weather data yet. Run `pixi run pipeline`.");
  assignColors(all.map((r) => r.city));
  const visible = inRange(all);
  const groups = groupBy(visible, "city");
  const traces = lineTraces(groups, "temperature_c", "%{y:.1f} °C<extra>%{fullData.name}</extra>");
  Plotly.react(el, traces, baseLayout({
    hovermode: "x unified",
    xaxis: { ...baseLayout().xaxis, range: timeRange(visible) },
    yaxis: { ...baseLayout().yaxis, ticksuffix: " °C" },
    margin: { l: 8, r: 72, t: 8, b: 8 },
  }), CONFIG);

  renderTable($("#table-weather"), [
    { label: "City", value: (r) => r.city, swatch: "city" },
    { label: "Temp °C", value: (r) => r.temperature_c.toFixed(1), num: true },
    { label: "Humidity %", value: (r) => String(r.humidity_pct), num: true },
    { label: "Wind km/h", value: (r) => r.wind_kmh.toFixed(1), num: true },
    { label: "Sky", value: (r) => r.weather },
    { label: "Observed", value: (r) => fmtTime.format(r.t) },
  ], latestRun(all).sort((a, b) => b.temperature_c - a.temperature_c));
}

// ── hacker news ──────────────────────────────────────────────────────────────

function renderHN() {
  const el = $("#chart-hn");
  const all = rows("hackernews");
  if (all.length === 0) return empty(el, "No Hacker News data yet. Run `pixi run pipeline`.");
  const latest = latestRun(all).sort((a, b) => a.rank - b.rank);
  const top = latest.slice(0, 20).reverse();   // reverse so rank 1 draws at the top
  const short = (s) => (s.length > 58 ? s.slice(0, 56).trimEnd() + "…" : s);
  const trace = {
    type: "bar", orientation: "h",
    x: top.map((r) => r.points), y: top.map((r) => `${r.rank}. ${short(r.title)}`),
    marker: { color: cssVar("--s1") },
    customdata: top.map((r) => [r.domain, r.comments, r.author, r.url, r.title]),
    hovertemplate: "<b>%{x} points</b><br>%{customdata[4]}<br>%{customdata[0]} · %{customdata[1]} comments · by %{customdata[2]}<extra></extra>",
  };
  const layout = baseLayout({
    bargap: 0.3, margin: { l: 8, r: 16, t: 8, b: 8 },
    yaxis: { ...baseLayout().yaxis, automargin: true, tickfont: { color: cssVar("--ink-2"), size: 12 } },
    xaxis: { ...baseLayout().xaxis, title: { text: "points", font: { color: cssVar("--muted") } } },
  });
  Plotly.react(el, [trace], layout, CONFIG).then((gd) => {
    gd.removeAllListeners?.("plotly_click");
    gd.on("plotly_click", (ev) => { const url = ev.points[0]?.customdata?.[3]; if (url) window.open(url, "_blank", "noopener"); });
  });

  renderTable($("#table-hn"), [
    { label: "#", value: (r) => String(r.rank), num: true },
    { label: "Title", value: (r) => r.title, href: "url" },
    { label: "Domain", value: (r) => r.domain },
    { label: "Points", value: (r) => String(r.points), num: true },
    { label: "Comments", value: (r) => String(r.comments), num: true },
    { label: "By", value: (r) => r.author },
  ], latest);
}

// ── github ───────────────────────────────────────────────────────────────────

function renderGitHub() {
  const el = $("#chart-gh-delta");
  const all = rows("github");
  if (all.length === 0) return empty(el, "No GitHub data yet. Run `pixi run pipeline`.");
  assignColors(all.map((r) => r.repo));

  // Delta since the first observation ever (not since the range start), so a
  // reader flipping between ranges sees the same numbers, just less of them.
  const first = {};
  for (const r of [...all].sort((a, b) => a.t - b.t)) first[r.repo] ??= r.stars;
  const withDelta = inRange(all).map((r) => ({ ...r, delta: r.stars - first[r.repo] }));
  const runsSeen = new Set(withDelta.map((r) => r.t.getTime())).size;
  if (runsSeen < 2) {
    empty(el, `Change over time needs at least two runs; there ${runsSeen === 1 ? "is one" : "are none"} in this range. The next scheduled scrape adds another.`);
  } else {
    const traces = lineTraces(groupBy(withDelta, "repo"), "delta", "+%{y:,} stars<extra>%{fullData.name}</extra>");
    Plotly.react(el, traces, baseLayout({
      hovermode: "x unified",
      xaxis: { ...baseLayout().xaxis, range: timeRange(withDelta) },
      yaxis: { ...baseLayout().yaxis, title: { text: "stars gained", font: { color: cssVar("--muted") } }, rangemode: "tozero" },
      margin: { l: 8, r: 120, t: 8, b: 8 },
    }), CONFIG);
  }

  const latest = latestRun(all).sort((a, b) => a.stars - b.stars);
  Plotly.react($("#chart-gh-stars"), [{
    type: "bar", orientation: "h",
    x: latest.map((r) => r.stars), y: latest.map((r) => r.repo),
    marker: { color: latest.map((r) => colorFor(r.repo)) },
    hovertemplate: "<b>%{x:,} stars</b><br>%{y}<extra></extra>",
  }], baseLayout({
    bargap: 0.35,
    xaxis: { ...baseLayout().xaxis, title: { text: "stars today", font: { color: cssVar("--muted") } } },
  }), CONFIG);

  renderTable($("#table-gh"), [
    { label: "Repository", value: (r) => r.repo, swatch: "repo" },
    { label: "Stars", value: (r) => fmtInt.format(r.stars), num: true },
    { label: "Forks", value: (r) => fmtInt.format(r.forks), num: true },
    { label: "Open issues", value: (r) => fmtInt.format(r.open_issues), num: true },
    { label: "Language", value: (r) => r.language },
    { label: "Last push", value: (r) => fmtTime.format(new Date(r.pushed_at)) },
  ], [...latest].reverse());
}

// ── glue ─────────────────────────────────────────────────────────────────────

function renderAll() {
  renderFreshness();
  renderPipeline();
  renderWeather();
  renderHN();
  renderGitHub();
}

async function refresh() {
  try {
    const changed = await loadAll();
    if (changed) renderAll();
  } catch (err) {
    $("#freshness").textContent = `couldn't load data: ${err.message}`;
    $("#freshness").classList.add("stale");
  }
}

document.querySelectorAll(".filters button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filters button").forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
    state.rangeDays = btn.dataset.range === "all" ? "all" : Number(btn.dataset.range);
    if (state.manifest) renderAll();
  });
});

$("#theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme === "dark" || (!root.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (_) {}
  if (state.manifest) renderAll();
});

refresh();
setInterval(refresh, REFRESH_MS);
setInterval(() => state.manifest && renderFreshness(), 30_000);
