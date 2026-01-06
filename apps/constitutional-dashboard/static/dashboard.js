/* Constitutional Ops Dashboard — CYBERNETIC CONTROLLER */

// Optional auth
const urlParams = new URLSearchParams(window.location.search);
const tokenFromQuery = urlParams.get("token");
if (tokenFromQuery) sessionStorage.setItem("dashboardApiToken", tokenFromQuery);
const apiToken = sessionStorage.getItem("dashboardApiToken");

/* --- API LAYER --- */
const api = {
  async getStats() {
    const res = await fetch("/api/stats", { cache: "no-store" });
    if (!res.ok) throw new Error(`stats ${res.status}`);
    return await res.json();
  },
  async actionRestart() {
    return await postAction("/api/action/restart", "restart");
  },
  async actionFlush() {
    return await postAction("/api/action/flush", "flush");
  },
  async actionPing() {
    return await postAction("/api/action/ping", "ping");
  },
};

async function postAction(url, name) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(apiToken ? { "X-API-Token": apiToken } : {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.message || `${name} ${res.status}`);
  return data;
}

/* --- DOM REFS --- */
const els = {
  // Vitals
  vramFill: document.getElementById("vramFill"),
  vramValue: document.getElementById("vramValue"),
  cpuFill: document.getElementById("cpuFill"),
  cpuValue: document.getElementById("cpuValue"),
  contextFill: document.getElementById("contextFill"),
  contextValue: document.getElementById("contextValue"),

  // Core / Monitor
  statusOrb: document.getElementById("statusOrb"),
  statusLabel: document.getElementById("statusLabel"),
  statusSub: document.getElementById("statusSub"),
  logLines: document.getElementById("logLines"),
  tpsValue: document.getElementById("tpsValue"),

  // Actions
  btnRestart: document.getElementById("btnRestart"),
  btnFlush: document.getElementById("btnFlush"),
  btnPing: document.getElementById("btnPing"),
};

/* --- STATE --- */
const state = {
  log: [],
  offlineCount: 0,
  lastStatus: "offline",
};

/* --- LOGIC --- */
function nowTime() {
  const d = new Date();
  return d.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function addLog(line, level = "info") {
  const prefix = level === "error" ? "[ERR]" : level === "warn" ? "[WRN]" : "[INF]";
  // Keep only the last message for the "Data Stream" look, or maybe a scrolling line
  // Ideally, we just show the most recent "Action" or system message
  const msg = `${prefix} ${line}`;
  els.logLines.textContent = msg; // Just show one line for the "Stream" aesthetic

  // Console backup
  console.log(`[${nowTime()}] ${msg}`);
}

function updateLogs(logs) {
  if (!els.logLines || !logs || !Array.isArray(logs) || logs.length === 0) {
    return;
  }

  // Display the most recent log line, or combine multiple if short
  if (logs.length === 1) {
    els.logLines.textContent = logs[0];
  } else {
    // Show last 2-3 lines separated by " | "
    const displayLogs = logs.slice(-2).join(" | ");
    els.logLines.textContent = displayLogs;
  }
}

function updateBar(fillEl, textEl, value, max, unit, isPercent = false) {
  if (!fillEl || !textEl) return;
  if (value === null || value === undefined) {
    textEl.textContent = "—";
    fillEl.style.width = "0%";
    return;
  }

  let percent = 0;
  if (isPercent) {
    percent = Math.min(100, Math.max(0, value));
    textEl.textContent = `${value.toFixed(0)}%`;
  } else {
    percent = Math.min(100, Math.max(0, (value / max) * 100));
    textEl.textContent = `${value.toFixed(1)} ${unit}`;
  }

  fillEl.style.width = `${percent}%`;

  // Color logic
  fillEl.classList.remove("fill-warn", "fill-crit");
  if (percent > 90) fillEl.classList.add("fill-crit");
  else if (percent > 75) fillEl.classList.add("fill-warn");
}

function updateCore(status) {
  if (!els.statusOrb || !els.statusLabel || !els.statusSub) return;

  // Map API status to visual themes
  // Statuses: 'idle', 'generating', 'searching', 'offline'

  const s = status || "offline";
  state.lastStatus = s;

  els.statusOrb.setAttribute("data-status", s);

  let mainText = "SYSTEM OFFLINE";
  let subText = "Connection lost";

  if (s === "idle") {
    mainText = "SYSTEM ONLINE";
    subText = "Ready for query";
  } else if (s === "generating") {
    mainText = "GENERATING";
    subText = "Processing token stream...";
  } else if (s === "searching") {
    mainText = "SEARCHING";
    subText = "Retrieving vector contexts...";
  }

  els.statusLabel.textContent = mainText;
  els.statusSub.textContent = subText;
}

function updateTPS(tps) {
  if (!els.tpsValue) return;

  if (tps === null || tps === undefined) {
    els.tpsValue.textContent = "—";
  } else {
    els.tpsValue.textContent = tps.toFixed(1);
    // Add glow effect if high TPS
    if (tps > 10) els.tpsValue.style.textShadow = "0 0 15px var(--neon-cyan)";
    else els.tpsValue.style.textShadow = "none";
  }
}

/* --- BUTTONS --- */
function setBtnBusy(btn, isBusy) {
  if (isBusy) btn.classList.add("busy");
  else btn.classList.remove("busy");
}

async function runAction(btn, apiCall, label) {
  setBtnBusy(btn, true);
  addLog(`${label} initiated...`, "warn");

  try {
    const res = await apiCall();
    addLog(res?.message || `${label} COMPLETE`, "info");
  } catch (err) {
    addLog(`${label} FAILED: ${err.message}`, "error");
  } finally {
    setTimeout(() => setBtnBusy(btn, false), 1000);
  }
}

function initButtons() {
  // Touch-friendly event handlers for Nest Hub
  const addTouchHandler = (btn, handler) => {
    btn.addEventListener("click", handler);
    btn.addEventListener("touchend", (e) => {
      e.preventDefault();
      handler(e);
    });
  };

  addTouchHandler(els.btnRestart, () => runAction(els.btnRestart, api.actionRestart, "REBOOT"));
  addTouchHandler(els.btnFlush, () => runAction(els.btnFlush, api.actionFlush, "FLUSH"));
  addTouchHandler(els.btnPing, () => runAction(els.btnPing, api.actionPing, "PING"));
}

/* --- LOOP --- */
async function tick() {
  try {
    const stats = await api.getStats();
    state.offlineCount = 0;

    updateBar(els.vramFill, els.vramValue, stats.vram_used, 12.0, "GB"); // 12GB max (roughly) for typical GPUs
    updateBar(els.cpuFill, els.cpuValue, stats.cpu, 100, "", true);
    updateBar(els.contextFill, els.contextValue, stats.context_usage, 100, "", true);

    updateCore(stats.status);
    updateTPS(stats.tps_current);

    // Update log stream from backend logs
    if (stats.logs) {
      updateLogs(stats.logs);
    }

  } catch (err) {
    state.offlineCount++;
    if (state.offlineCount > 5) updateCore("offline");
    // Don't spam log on every tick error
    if (state.offlineCount % 5 === 0) addLog("Telemetry Signal Lost", "error");
  }
}

/* --- NEST HUB OPTIMIZATION --- */
// Prevent zoom on double-tap (Nest Hub)
let lastTouchEnd = 0;
document.addEventListener("touchend", (e) => {
  const now = Date.now();
  if (now - lastTouchEnd <= 300) {
    e.preventDefault();
  }
  lastTouchEnd = now;
}, false);

// Optimize for Nest Hub display
if (window.matchMedia) {
  const mediaQuery = window.matchMedia("(max-width: 1024px) and (max-height: 600px)");
  if (mediaQuery.matches) {
    document.documentElement.style.setProperty("--nest-hub-optimized", "1");
  }
}

/* --- BOOT --- */
function boot() {
  initButtons();
  setInterval(tick, 1000);
  tick(); // Initial call
  addLog("Dashboard Interface Loaded");
}

boot();
