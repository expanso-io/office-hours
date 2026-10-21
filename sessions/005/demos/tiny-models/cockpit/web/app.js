// Cockpit page: polls /api/state once a second and renders the latest record,
// the recent records and the per-model numbers. Built with textContent only.

const THEME_KEY = "oh5-theme";

const POLL_MS = 1000;

const MODELS = ["python", "ollama", "direct"];

const SEVERITIES = new Set(["low", "medium", "high"]);

const els = {
  where: document.getElementById("where"),
  latest: document.getElementById("latest"),
  rows: document.getElementById("rows"),
  models: document.getElementById("models"),
  theme: document.getElementById("theme"),
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

function readings(record) {
  return `${record.temp_c} °C · ${record.vibration_mm_s} mm/s · ${record.current_a} A`;
}

function answerText(key, answer) {
  if (answer.error) return { text: "call failed", cls: "flag" };

  if (answer.unparsed !== undefined) return { text: `off-format: ${answer.unparsed}`, cls: "off" };

  if (key === "python") {
    return answer.anomaly
      ? { text: `anomaly, score ${answer.score}`, cls: "flag" }
      : { text: `normal, score ${answer.score}`, cls: "" };
  }

  if (key === "ollama") {
    const severity = answer.severity;

    if (!SEVERITIES.has(severity)) {
      return { text: `off-format: ${JSON.stringify(answer)}`, cls: "off" };
    }

    return { text: `severity ${severity}`, cls: severity === "high" ? "flag" : "" };
  }

  return { text: `part: ${answer.part}`, cls: "" };
}

function modelCell(key, record, label) {
  const td = el("td");
  td.dataset.label = label;
  const answer = record[key];

  if (!answer) {
    td.append(el("span", "off", "not in this stage"));

    return td;
  }

  const shown = answerText(key, answer);
  const wrap = el("span");
  wrap.append(el("span", shown.cls, shown.text), el("span", "ms", ms(answer.call_ms)));
  td.append(wrap);

  return td;
}

function recordRow(record) {
  const tr = el("tr");
  const idCell = el("td");
  idCell.dataset.label = "Record";
  idCell.append(el("span", "rid", record.id), el("span", "sub", record.asset));
  const readCell = el("td", "mono", readings(record));
  readCell.dataset.label = "Readings";
  const noteCell = el("td", "", record.note);
  noteCell.dataset.label = "Note";
  tr.append(
    idCell,
    readCell,
    noteCell,
    modelCell("python", record, "Python"),
    modelCell("ollama", record, "Ollama"),
    modelCell("direct", record, "Direct call"),
  );

  return tr;
}

function skeletonRows() {
  const rows = [];

  for (let i = 0; i < 3; i += 1) {
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

function answersText(answers) {
  const parts = Object.entries(answers || {}).map(([label, count]) => `${label} ${count}`);

  return parts.length ? parts.join(", ") : "none yet";
}

function callsText(model) {
  const failed = model.failed ? `, ${model.failed} failed or off-format` : "";

  return `${model.calls ?? 0}${failed}`;
}

const MODEL_ROWS = [
  ["Model", (m) => m.name || "not reported", ""],
  ["Called through", (m) => m.runtime || "", ""],
  ["Size on disk", (m) => bytes(m.bytes), "num"],
  ["Shape", (m) => m.shape || "not reported", ""],
  ["Calls this run", callsText, "num"],
  ["First call", (m) => ms(m.first_ms) || "none yet", "num"],
  ["Median call", (m) => ms(m.p50_ms) || "none yet", "num"],
  ["95th percentile", (m) => ms(m.p95_ms) || "none yet", "num"],
  ["Slowest call", (m) => ms(m.max_ms) || "none yet", "num"],
  ["Answers", (m) => answersText(m.answers), ""],
];

function rowHeader(label) {
  const th = el("th", "", label);
  th.setAttribute("scope", "row");

  return th;
}

function memoryText(models) {
  const until = models.ollama?.in_memory_until;

  return until ? `until ${until.slice(11, 19)}` : "not loaded";
}

function renderModels(models) {
  const rows = MODEL_ROWS.map(([label, value, cls]) => {
    const tr = el("tr");
    tr.append(rowHeader(label));

    for (const key of MODELS) tr.append(el("td", cls, value(models[key] || {})));

    return tr;
  });

  const memory = el("tr");
  memory.append(
    rowHeader("In memory"),
    el("td", "", "for the life of the pipeline"),
    el("td", "", memoryText(models)),
    el("td", "", "while llama-server runs"),
  );
  rows.push(memory);
  els.models.replaceChildren(...rows);
}

function laneText(lane) {
  if (lane === "cloud") return "deployed through Expanso Cloud";

  if (lane === "local") return "local-mode Expanso Edge node, offline";

  return "not running";
}

function render(state) {
  els.where.textContent = `${laneText(state.lane)} · stage ${state.stage || "none"} · ${state.records_total} records this run`;

  if (state.records.length) {
    els.latest.textContent = JSON.stringify(state.records[0], null, 2);
    els.rows.replaceChildren(...state.records.map(recordRow));
  } else {
    els.latest.replaceChildren(el("span", "waiting", "Waiting for the first record from the pipeline."));
    els.rows.replaceChildren(...skeletonRows());
  }

  renderModels(state.models || {});
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

els.rows.replaceChildren(...skeletonRows());

poll();
