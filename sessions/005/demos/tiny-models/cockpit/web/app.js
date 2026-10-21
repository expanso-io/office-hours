// Cockpit page: polls /api/state once a second. Built with textContent only.

const THEME_KEY = "oh5-theme";

const POLL_MS = 1000;

const MODELS = ["python", "ollama", "direct"];

const els = {
  where: document.getElementById("where"),
  theme: document.getElementById("theme"),
  tail: document.getElementById("tail"),
  models: document.getElementById("models"),
  note: document.getElementById("note"),
  alert: document.getElementById("alert"),
  inRate: document.getElementById("in-rate"),
  outRate: document.getElementById("out-rate"),
  kept: document.getElementById("kept"),
  inBytes: document.getElementById("in-bytes"),
  outBytes: document.getElementById("out-bytes"),
  degraded: document.getElementById("degraded"),
  dead: document.getElementById("dead"),
};

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  els.theme.textContent = theme === "dark" ? "Light theme" : "Dark theme";
  els.theme.setAttribute("aria-pressed", String(theme === "dark"));
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";

  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    // Private windows can refuse storage; the toggle still works for this visit.
  }

  setTheme(next);
}

function el(tag, className, text) {
  const node = document.createElement(tag);

  if (className) node.className = className;

  if (text !== undefined && text !== null) node.textContent = String(text);

  return node;
}

function ms(value) {
  if (!Number.isFinite(value)) return "";

  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;

  return `${value.toFixed(value < 10 ? 1 : 0)} ms`;
}

function bytes(value) {
  if (!Number.isFinite(value)) return "not reported";

  if (value >= 1e9) return `${(value / 1e9).toFixed(2)} GB`;

  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MB`;

  return `${(value / 1e3).toFixed(1)} kB`;
}

function rate(value, unit) {
  return Number.isFinite(value) ? `${value.toFixed(1)} ${unit}` : "–";
}

function byteRate(value) {
  if (!Number.isFinite(value)) return "–";

  return value >= 1000 ? `${(value / 1000).toFixed(1)} kB/s` : `${Math.round(value)} B/s`;
}

function clock(ts) {
  return ts ? String(ts).slice(11, 23) : "";
}

function readingText(record) {
  return `${record.temp_c} °C · ${record.vibration_mm_s} mm/s · ${record.current_a} A`;
}

function answer(key, value) {
  if (!value) return null;

  if (value.error) return { text: "call failed", cls: "flag", ms: "" };

  if (value.unparsed !== undefined) return { text: `off-format: ${value.unparsed}`, cls: "off", ms: ms(value.call_ms) };

  if (key === "python") {
    const text = value.anomaly ? `anomaly ${value.score}` : `normal ${value.score}`;

    return { text, cls: value.anomaly ? "flag" : "", ms: ms(value.call_ms) };
  }

  if (key === "ollama") {
    const symptom = value.symptom ? `, ${value.symptom}` : "";

    return { text: `${value.part}${symptom}`, cls: "", ms: ms(value.call_ms) };
  }

  const problem = value.problem_reported === undefined ? "" : `, problem ${value.problem_reported}`;

  return { text: `${value.part}${problem}`, cls: "", ms: ms(value.call_ms) };
}

function modelCell(key, record, label) {
  const td = el("td");
  td.dataset.label = label;
  let shown = answer(key, record[key]);
  let fromNote = false;

  if (!shown && record.last_note) {
    shown = answer(key, record.last_note[key]);
    fromNote = Boolean(shown);
  }

  if (!shown) {
    td.append(el("span", "off", "–"));

    return td;
  }

  td.title = shown.text;
  td.append(el("span", shown.cls, shown.text));

  if (shown.ms) td.append(" ", el("span", "ms", shown.ms));

  if (fromNote) td.append(" ", el("span", "from-note", "last note"));

  return td;
}

function tailRow(record) {
  const tr = el("tr");
  const time = el("td", "num", clock(record.ts));
  time.dataset.label = "Time";
  const asset = el("td", "", record.asset);
  asset.dataset.label = "Pump";
  const what = record.kind === "note" ? el("td", "", record.text) : el("td", "num", readingText(record));
  what.dataset.label = record.kind === "note" ? "Note" : "Reading";
  what.title = what.textContent;
  tr.append(
    time,
    asset,
    what,
    modelCell("python", record, "Python"),
    modelCell("ollama", record, "Ollama"),
    modelCell("direct", record, "Direct call"),
  );

  return tr;
}

function skeletonRows(count) {
  const rows = [];

  for (let i = 0; i < count; i += 1) {
    const tr = el("tr");

    for (let c = 0; c < 6; c += 1) {
      const td = el("td");
      td.append(el("span", "skeleton-cell"));
      tr.append(td);
    }

    rows.push(tr);
  }

  return rows;
}

function rowHeader(label) {
  const th = el("th", "", label);
  th.setAttribute("scope", "row");

  return th;
}

function share(value) {
  return Number.isFinite(value) ? `${value.toFixed(1)}%` : "–";
}

function memory(model, key) {
  if (key === "python") return "inside the pipeline's process";

  if (key === "direct") return "while llama-server runs";

  if (model.in_memory === null || model.in_memory === undefined) return "Ollama not answering";

  return model.in_memory ? "loaded" : "not loaded";
}

const MODEL_ROWS = [
  ["Model", (m) => m.name || "not reported", ""],
  ["Wired with", (m) => (m.wiring ? `${m.wiring} processor` : ""), "num"],
  ["Size on disk", (m) => bytes(m.bytes), "num"],
  ["Shape", (m) => m.shape || "not reported", ""],
  ["Median call", (m) => ms(m.p50_ms) || "–", "num"],
  ["95th percentile", (m) => ms(m.p95_ms) || "–", "num"],
  ["Calls, last 60 s", (m) => String(m.calls ?? 0), "num"],
  ["Share of records in", (m) => share(m.share_pct), "num"],
  ["In memory", memory, ""],
];

function renderModels(models) {
  const rows = MODEL_ROWS.map(([label, value, cls]) => {
    const tr = el("tr");
    tr.append(rowHeader(label));

    for (const key of MODELS) tr.append(el("td", cls, value(models[key] || {}, key)));

    return tr;
  });

  els.models.replaceChildren(...rows);
}

function laneText(job) {
  const where = job.lane === "cloud" ? "Expanso Cloud" : job.lane === "local" ? "local-mode node, offline" : "not running";
  const version = job.version ? ` · version ${job.version}` : "";

  return `${where} · ${job.name || "office-hours-005-models"}${version}`;
}

function showJson(target, record, waitingText) {
  if (record) {
    target.textContent = JSON.stringify(record, null, 2);

    return;
  }

  target.replaceChildren(el("span", "waiting", waitingText));
}

function render(state) {
  const rates = state.rates || {};
  els.where.textContent = laneText(state.job || {});
  els.inRate.textContent = rate(rates.in_per_s, "/s");
  els.outRate.textContent = rate(rates.out_per_s, "/s");
  els.kept.textContent = Number.isFinite(rates.kept_pct) ? `${rates.kept_pct.toFixed(1)}%` : "–";
  els.inBytes.textContent = byteRate(rates.in_bytes_per_s);
  els.outBytes.textContent = byteRate(rates.out_bytes_per_s);
  els.degraded.textContent = String(state.degraded ?? 0);
  els.dead.textContent = String(state.dead_letters ?? 0);
  const tail = state.tail || [];
  els.tail.replaceChildren(...(tail.length ? tail.map(tailRow) : skeletonRows(4)));
  renderModels(state.models || {});
  showJson(els.note, state.latest_note, "No note has left the node yet.");
  showJson(els.alert, state.latest_alert, "No anomaly has left the node yet. Readings carry a score after change 1.");
}

async function poll() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    render(await response.json());
  } catch (error) {
    els.where.textContent = `Cockpit server not answering (${error.message}). Is the demo up?`;
  }

  setTimeout(poll, POLL_MS);
}

setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");

els.theme.addEventListener("click", toggleTheme);

els.tail.replaceChildren(...skeletonRows(4));

poll();
