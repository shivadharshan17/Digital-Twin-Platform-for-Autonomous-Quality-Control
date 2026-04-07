let autoTimer = null;
let simulationRunning = false;
let simulationInitialized = false;
const STEP_INTERVAL_MS = 1000;

/*
  Button behavior:
  - Start Simulation  => initialize if needed, then run continuously
  - Single Simulation => initialize if needed, then run exactly one step
  - Stop              => pause the continuous simulation temporarily
*/

async function initializeSimulation(forceReset = false) {
  try {
    if (forceReset) {
      await fetch("/reset_simulation", { method: "POST" });
      simulationInitialized = false;
    }

    if (simulationInitialized) return true;

    const res = await fetch("/start_simulation", { method: "POST" });
    const data = await res.json();

    if (data.status === "error") {
      console.error(data.message);
      return false;
    }

    simulationInitialized = true;
    return true;
  } catch (error) {
    console.error("Initialization failed:", error);
    return false;
  }
}

async function startContinuousSimulation() {
  try {
    const ok = await initializeSimulation(false);
    if (!ok) return;

    if (simulationRunning) return;

    simulationRunning = true;

    if (autoTimer) clearInterval(autoTimer);

    autoTimer = setInterval(async () => {
      if (!simulationRunning) return;
      await runOneStep();
    }, STEP_INTERVAL_MS);

    await runOneStep();
  } catch (error) {
    console.error("Continuous simulation start failed:", error);
  }
}

async function runSingleSimulation() {
  try {
    stopSimulation(false);

    const ok = await initializeSimulation(false);
    if (!ok) return;

    await runOneStep();
  } catch (error) {
    console.error("Single simulation failed:", error);
  }
}

async function runOneStep() {
  try {
    const res = await fetch("/next_step", { method: "POST" });
    const data = await res.json();

    if (data.status === "error") {
      console.error("Step error:", data.message);
      stopSimulation();
      return;
    }

    await refreshDashboard();

    const live = await fetch("/api/live_status");
    const liveData = await live.json();

    if (!liveData.is_running) {
      stopSimulation(false);

      if ((liveData.alerts_count || 0) > 0) {
        alert(liveData.last_event || "Production halted");
      }
    }
  } catch (error) {
    console.error("Next step failed:", error);
    stopSimulation();
  }
}

async function refreshDashboard() {
  try {
    const [liveRes, alertRes] = await Promise.all([
      fetch("/api/live_status"),
      fetch("/api/admin_alerts")
    ]);

    const data = await liveRes.json();
    const alertData = await alertRes.json();
    const alerts = alertData.alerts || [];
    const events = data.events || [];

    const activeProducts = (data.active_products || []).length
      ? data.active_products.join(", ")
      : "-";

    const unresolvedAlerts = alerts.filter(a => !a.resolved);
    const latestEvent = events.length > 0 ? events[0] : (data.last_event || "System idle");

    // KPI cards
    document.getElementById("kpiCurrentProduct").innerText = activeProducts;
    document.getElementById("kpiTotalProducts").innerText = data.total_products || 0;
    document.getElementById("kpiCompleted").innerText = data.completed_count || 0;
    document.getElementById("kpiAlerts").innerText = unresolvedAlerts.length;

    // latest event banner
    document.getElementById("lastEvent").innerText = latestEvent;

    // dynamic top status and banner
    updateTopStatus(latestEvent, data, unresolvedAlerts);

    // render panels
    renderStations(data.station_cards || []);
    renderLatestAlert(alerts);
    renderRootCause(alerts);
    renderEventTimeline(events);
    renderAnalytics(data, alerts);
  } catch (error) {
    console.error("Refresh dashboard failed:", error);
  }
}

function updateTopStatus(latestEvent, data, unresolvedAlerts) {
  const lineStatusEl = document.getElementById("lineStatus");
  const haltBanner = document.getElementById("haltBanner");
  const msg = String(latestEvent || "").toLowerCase();

  let status = "IDLE";

  if (msg.includes("halted") || msg.includes("defect detected") || msg.includes("critical risk detected")) {
    status = "HALTED";
  } else if (
    msg.includes("autonomous healing applied") ||
    msg.includes("healing applied") ||
    msg.includes("production resumed") ||
    msg.includes("healed")
  ) {
    status = "RECOVERED";
  } else if (msg.includes("completed") && !data.is_running) {
    status = "COMPLETED";
  } else if (data.is_running) {
    status = "RUNNING";
  }

  lineStatusEl.innerText = status;

  if (status === "HALTED") {
    haltBanner.classList.remove("hidden");
    haltBanner.innerText = "🚨 PRODUCTION HALTED — DEFECT DETECTED";
  } else if (status === "RECOVERED") {
    haltBanner.classList.remove("hidden");
    haltBanner.innerText = "🛠 ISSUE DETECTED — AUTONOMOUS HEALING APPLIED — PRODUCTION RESUMED";
  } else if (status === "COMPLETED") {
    haltBanner.classList.remove("hidden");
    haltBanner.innerText = "✅ PRODUCTION COMPLETED SUCCESSFULLY";
  } else {
    haltBanner.classList.add("hidden");
  }

  const alertValue = document.getElementById("kpiAlerts");
  if (alertValue) {
    alertValue.style.color = unresolvedAlerts.length > 0 ? "#ff8a8a" : "#f3f7ff";
  }
}

function renderStations(cards) {
  const grid = document.getElementById("stationGrid");
  if (!grid) return;

  grid.innerHTML = "";

  cards.forEach(card => {
    const div = document.createElement("div");

    let statusClass = "idle";
    let badgeClass = "badge-idle";

    if (card.status === "Normal") {
      statusClass = "normal";
      badgeClass = "badge-normal";
    } else if (card.status === "Warning") {
      statusClass = "warning";
      badgeClass = "badge-warning";
    } else if (card.status === "Critical") {
      statusClass = "critical";
      badgeClass = "badge-critical";
    } else if (card.status === "Corrected") {
      statusClass = "normal";
      badgeClass = "badge-normal";
    }

    const imgPath = `/static/assets/s${card.station_id}.png`;

    div.className = `station-card ${statusClass}`;
    div.innerHTML = `
      <div class="station-header">
        <div class="station-title">S${card.station_id}</div>
        <div class="station-name">${card.station_name}</div>
      </div>

      <div class="station-image-wrap">
        <img
          src="${imgPath}"
          alt="Station ${card.station_id}"
          class="station-image"
          onerror="this.style.display='none'"
        >
      </div>

      <div class="product-badge ${badgeClass}">
        ${card.product_id || "-"}
      </div>

      <div class="station-status">Status: ${card.status || "Idle"}</div>

      <div class="station-metrics">
        <div><span>Temp</span><strong>${card.temperature ?? "-"}</strong></div>
        <div><span>Pressure</span><strong>${card.pressure ?? "-"}</strong></div>
        <div><span>Vibration</span><strong>${card.vibration ?? "-"}</strong></div>
        <div><span>Speed</span><strong>${card.speed ?? "-"}</strong></div>
        <div><span>Cycle Time</span><strong>${card.cycle_time ?? "-"}</strong></div>
      </div>
    `;

    grid.appendChild(div);
  });
}

function renderLatestAlert(alerts) {
  const latestAlert = document.getElementById("latestAlert");
  if (!latestAlert) return;

  if (!alerts.length) {
    latestAlert.innerHTML = "No alerts";
    return;
  }

  const a = alerts[0];
  latestAlert.innerHTML = `
    <div><strong>Product:</strong> ${a.product_id}</div>
    <div><strong>Station:</strong> S${a.current_station} - ${a.station_name}</div>
    <div><strong>Risk Score:</strong> ${(Number(a.risk_score || 0) * 100).toFixed(1)}%</div>
    <div><strong>Risk Level:</strong> ${a.risk_level || "-"}</div>
    <div><strong>Predicted Failure:</strong> ${formatLabel(a.predicted_failure || "-")}</div>
    <div><strong>Confidence:</strong> ${a.confidence != null ? (Number(a.confidence) * 100).toFixed(1) + "%" : "-"}</div>
    <div><strong>Resolved:</strong> ${a.resolved ? "Yes" : "No"}</div>
    <div><strong>Message:</strong> ${a.message || "-"}</div>
    <div><strong>Recommended Action:</strong> ${a.recommended_action || "-"}</div>
    <div><strong>Time:</strong> ${a.timestamp || "-"}</div>
  `;
}

function renderRootCause(alerts) {
  const rootCause = document.getElementById("rootCause");
  if (!rootCause) return;

  if (!alerts.length) {
    rootCause.innerHTML = "-";
    return;
  }

  const a = alerts[0];
  rootCause.innerHTML = `
    <div><strong>Source Station:</strong> S${a.root_cause_station || "-"}</div>
    <div><strong>Parameter:</strong> ${a.root_parameter || "-"}</div>
    <div><strong>Predicted Failure:</strong> ${formatLabel(a.predicted_failure || "-")}</div>
    <div><strong>Confidence:</strong> ${a.confidence != null ? (Number(a.confidence) * 100).toFixed(1) + "%" : "-"}</div>
    <div><strong>Interpretation:</strong> ${a.message || "-"}</div>
    <div><strong>Action:</strong> ${a.recommended_action || "-"}</div>
  `;
}

function renderEventTimeline(events) {
  const log = document.getElementById("eventLog");
  if (!log) return;

  log.innerHTML = "";

  if (!events.length) {
    log.innerHTML = `<div class="event-item">No events yet</div>`;
    return;
  }

  events.forEach(message => {
    const item = document.createElement("div");
    item.className = "event-item";

    const msg = String(message).toLowerCase();
    if (msg.includes("halted") || msg.includes("critical")) {
      item.style.borderColor = "#ef4444";
    } else if (msg.includes("healing applied") || msg.includes("resumed") || msg.includes("healed")) {
      item.style.borderColor = "#22c55e";
    } else if (msg.includes("warning")) {
      item.style.borderColor = "#f59e0b";
    }

    item.innerText = message;
    log.appendChild(item);
  });
}

function formatLabel(value) {
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, ch => ch.toUpperCase());
}

function renderAnalytics(data, alerts) {
  const stationHealth = document.getElementById("stationHealth");
  const riskTrend = document.getElementById("riskTrend");
  const alertsSummary = document.getElementById("alertsSummary");

  if (!stationHealth || !riskTrend || !alertsSummary) return;

  const cards = data.station_cards || [];
  const activeStations = cards.filter(c => c.product_id && c.product_id !== "-").length;
  const criticalStations = cards.filter(c => c.status === "Critical").length;
  const warningStations = cards.filter(c => c.status === "Warning").length;
  const correctedStations = cards.filter(c => c.status === "Corrected").length;
  const normalStations = cards.filter(c => c.status === "Normal").length;

  stationHealth.innerHTML = `
    <div>Active Stations: <strong>${activeStations}</strong></div>
    <div>Normal: <strong>${normalStations}</strong></div>
    <div>Warning: <strong>${warningStations}</strong></div>
    <div>Corrected: <strong>${correctedStations}</strong></div>
    <div>Critical: <strong>${criticalStations}</strong></div>
  `;

  let highestRisk = 0;
  let highestConfidence = 0;

  if (alerts.length) {
    highestRisk = Math.max(...alerts.map(a => Number(a.risk_score || 0)));
    highestConfidence = Math.max(...alerts.map(a => Number(a.confidence || 0)));
  }

  riskTrend.innerHTML = `
    <div>Current State: <strong>${data.is_running ? "Monitoring" : "Stopped"}</strong></div>
    <div>Highest Risk Seen: <strong>${(highestRisk * 100).toFixed(1)}%</strong></div>
    <div>Highest Confidence: <strong>${(highestConfidence * 100).toFixed(1)}%</strong></div>
    <div>Last Step: <strong>${data.step_count || 0}</strong></div>
  `;

  const resolvedCount = alerts.filter(a => a.resolved).length;

  alertsSummary.innerHTML = `
    <div>Total Alerts: <strong>${alerts.length}</strong></div>
    <div>Resolved Alerts: <strong>${resolvedCount}</strong></div>
    <div>Healed Events: <strong>${data.healed_count || 0}</strong></div>
    <div>Completed Products: <strong>${data.completed_count || 0}</strong></div>
    <div>Total Products: <strong>${data.total_products || 0}</strong></div>
  `;
}

function stopSimulation(showLog = false) {
  simulationRunning = false;

  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
  }

  if (showLog) {
    console.log("Simulation paused");
  }
}

document.getElementById("startBtn").addEventListener("click", startContinuousSimulation);
document.getElementById("stepBtn").addEventListener("click", runSingleSimulation);
document.getElementById("stopBtn").addEventListener("click", () => stopSimulation());

refreshDashboard();