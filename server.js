const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { loadDashboardData } = require("./visualization/dashboard_data");

const PORT = Number(process.env.PORT || 31084);
const HOST = process.env.HOST || "0.0.0.0";
const ROOT = __dirname;
let updateProcess = null;

function send(res, status, body, headers = {}) {
  res.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    ...headers,
  });
  res.end(body);
}

function sendJson(res, status, payload) {
  send(res, status, JSON.stringify(payload, null, 2), {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
}

function dashboardMeta(req) {
  const hostHeader =
    req.headers["x-forwarded-host"] || req.headers.host || `127.0.0.1:${PORT}`;
  const protoHeader = req.headers["x-forwarded-proto"] || "http";
  const host = String(hostHeader).split(",")[0].trim();
  const proto = String(protoHeader).split(",")[0].trim();
  const baseUrl = `${proto}://${host}`;
  return {
    id: "recommendation-guanyuan",
    title: "推荐系统 Guanyuan 数据",
    url: `${baseUrl}/`,
    iframe_url: `${baseUrl}/`,
    api_url: `${baseUrl}/api/dashboard`,
    update_url: `${baseUrl}/api/update`,
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function serveStatic(req, res, url) {
  const relative = decodeURIComponent(url.pathname.replace(/^\/visualization\//, ""));
  const fullPath = path.join(ROOT, "visualization", relative);
  if (!fullPath.startsWith(path.join(ROOT, "visualization"))) {
    send(res, 403, "Forbidden", { "Content-Type": "text/plain; charset=utf-8" });
    return;
  }
  fs.readFile(fullPath, (error, buffer) => {
    if (error) {
      send(res, 404, "Not found", { "Content-Type": "text/plain; charset=utf-8" });
      return;
    }
    const ext = path.extname(fullPath);
    const contentType =
      ext === ".json"
        ? "application/json; charset=utf-8"
        : ext === ".csv"
          ? "text/csv; charset=utf-8"
          : ext === ".html"
            ? "text/html; charset=utf-8"
            : "application/octet-stream";
    send(res, 200, buffer, { "Content-Type": contentType });
  });
}

function runUpdate(req, res) {
  if (updateProcess) {
    sendJson(res, 202, {
      ok: true,
      status: "running",
      message: "update already running",
      dashboard: dashboardMeta(req),
    });
    return;
  }

  const startedAt = new Date().toISOString();
  let stdout = "";
  let stderr = "";
  updateProcess = spawn(process.execPath, ["visualization/update_all.js"], {
    cwd: ROOT,
    env: process.env,
  });
  updateProcess.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  updateProcess.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  updateProcess.on("close", (code) => {
    updateProcess = null;
    let payload = null;
    try {
      payload = JSON.parse(
        fs.readFileSync(path.join(ROOT, "visualization", "last_update.json"), "utf8")
      );
    } catch {
      try {
        payload = JSON.parse(stdout.trim());
      } catch {
        payload = null;
      }
    }
    if (!payload) {
      payload = {
        ok: code === 0,
        status: code === 0 ? "updated" : "failed",
        source: process.env.RECOMMENDATION_UPDATE_COMMAND ? "external-command" : "local-cache",
        started_at: startedAt,
        finished_at: new Date().toISOString(),
        stdout,
        stderr,
      };
    }
    payload.dashboard = { ...(payload.dashboard || {}), ...dashboardMeta(req) };
    sendJson(res, code === 0 ? 200 : 500, payload);
  });
}

function renderHtml(data) {
  const dataJson = JSON.stringify(data).replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(data.title)}</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16202a;
      --muted: #667382;
      --line: #d7dde4;
      --bg: #f6f8fa;
      --panel: #ffffff;
      --blue: #2563eb;
      --teal: #0f766e;
      --amber: #b45309;
      --rose: #be123c;
      --green: #15803d;
      --shadow: 0 8px 24px rgba(21, 32, 43, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }
    .page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 40px; }
    header { display: grid; gap: 10px; padding: 8px 0 18px; }
    .topbar { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; flex-wrap: wrap; }
    .eyebrow { color: var(--teal); font-size: 13px; font-weight: 700; }
    h1 { margin: 0; font-size: clamp(28px, 5vw, 44px); line-height: 1.08; letter-spacing: 0; }
    h2 { margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }
    .meta, .subline { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 12px 0 18px; }
    .day-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 8px;
      min-height: 36px;
      padding: 7px 11px;
      font: inherit;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }
    button[aria-pressed="true"], .primary {
      background: var(--ink);
      border-color: var(--ink);
      color: #fff;
    }
    button:disabled { cursor: wait; opacity: 0.66; }
    .grid { display: grid; gap: 16px; }
    .cards { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin: 18px 0; }
    .card, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }
    .card { min-height: 134px; padding: 18px; display: grid; align-content: space-between; gap: 12px; }
    .panel { padding: 20px; overflow: hidden; }
    .label { color: var(--muted); font-size: 13px; font-weight: 700; }
    .metric { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
    .number { font-size: 36px; line-height: 1; font-weight: 780; letter-spacing: 0; }
    .unit { color: var(--muted); font-size: 13px; font-weight: 650; }
    .section-gap { margin-top: 16px; }
    .callout {
      border-left: 4px solid var(--green);
      padding: 12px 14px;
      background: #f0fdf4;
      color: #14532d;
      border-radius: 0 8px 8px 0;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .note {
      margin-top: 14px;
      padding: 12px 14px;
      border: 1px solid #f7d48a;
      background: #fffbeb;
      color: #7c4a03;
      border-radius: 8px;
      font-size: 13px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
    th, td { padding: 11px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; font-weight: 750; background: #f8fafc; }
    td { word-break: break-word; }
    tbody tr:last-child td { border-bottom: 0; }
    code {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 12px;
      background: #eef2f7;
      color: #233244;
      padding: 2px 5px;
      border-radius: 5px;
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }
    .status.true { background: #dcfce7; border: 1px solid #86efac; color: #166534; }
    .status.false { background: #f1f5f9; border: 1px solid #cbd5e1; color: #475569; }
    .status.unknown { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; }
    .activation-row td { background: #f7fef9; }
    .update-status { min-height: 20px; color: var(--muted); font-size: 13px; }
    .table-wrap { overflow-x: auto; }
    @media (max-width: 620px) {
      .page { width: min(100% - 20px, 1180px); padding-top: 18px; }
      .cards { grid-template-columns: 1fr; }
      .number { font-size: 31px; }
      th, td { padding: 9px 8px; }
    }
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div class="topbar">
        <div>
          <div class="eyebrow">Guanyuan 小看板</div>
          <h1>${escapeHtml(data.title)}</h1>
        </div>
        <button id="update-button" class="primary" type="button">更新数据</button>
      </div>
      <div class="meta">
        日期：${escapeHtml((data.date_range || []).join(" 至 "))}。按 ${escapeHtml(data.day_bucket)} 切分。<br>
        推荐事件数据集更新至 <code>${escapeHtml(data.dataset_updated_at || "未知")}</code>；真激活数据集更新至 <code>${escapeHtml(data.activation_dataset_updated_at || "未知")}</code>。
      </div>
      <div class="toolbar">
        <div id="day-tabs" class="day-tabs" aria-label="按天筛选"></div>
        <div id="update-status" class="update-status" aria-live="polite"></div>
      </div>
    </header>

    <section class="grid cards" aria-label="指标卡片">
      <article class="card"><div><div class="label">推荐展开</div><div class="metric"><span id="show-pv" class="number">0</span><span class="unit">PV</span></div></div><div id="show-uv" class="subline">UV 0</div></article>
      <article class="card"><div><div class="label">推荐点击</div><div class="metric"><span id="click-pv" class="number">0</span><span class="unit">PV</span></div></div><div id="click-uv" class="subline">UV 0</div></article>
      <article class="card"><div><div class="label">点击转化率</div><div class="metric"><span id="pv-rate" class="number">0.00%</span><span class="unit">PV</span></div></div><div id="uv-rate" class="subline">UV 转化 0.00%</div></article>
      <article class="card"><div><div class="label">真激活率</div><div class="metric"><span id="activation-rate" class="number">0.00%</span><span class="unit">session</span></div></div><div id="activation-count" class="subline">真激活 session 0</div></article>
    </section>

    <section class="panel">
      <h2>每日总览</h2>
      <div class="table-wrap"><table><thead><tr><th>日期</th><th>展开PV</th><th>展开UV</th><th>点击PV</th><th>点击UV</th><th>PV转化</th><th>UV转化</th><th>点击session</th><th>真激活session</th><th>真激活率</th><th>未传session</th></tr></thead><tbody id="daily-body"></tbody></table></div>
      <div id="daily-note" class="note"></div>
    </section>

    <section class="panel section-gap">
      <h2>share_id 点击与真激活排行</h2>
      <div id="share-callout" class="callout"></div>
      <div class="table-wrap section-gap"><table><thead><tr><th>排名</th><th>share_id</th><th>点击PV</th><th>点击session</th><th>UV</th><th>user_id数</th><th>真激活session</th><th>真激活率</th><th>未传session</th><th>点击日期分布</th></tr></thead><tbody id="share-body"></tbody></table></div>
    </section>

    <section class="panel section-gap">
      <h2>真激活 share_id 明细</h2>
      <div class="table-wrap"><table><thead><tr><th>share_id</th><th>click send_ts</th><th>北京时间日</th><th>user_id</th><th>btu_id</th><th>session_id</th><th>激活时间</th><th>query</th></tr></thead><tbody id="true-body"></tbody></table></div>
    </section>

    <section class="panel section-gap">
      <h2>推荐点击事件明细</h2>
      <div class="table-wrap"><table><thead><tr><th>send_ts</th><th>北京时间日</th><th>user_id</th><th>btu_id</th><th>share_id</th><th>session_id</th><th>真激活</th><th>激活日期</th></tr></thead><tbody id="click-body"></tbody></table></div>
    </section>
  </main>
  <script id="dashboard-data" type="application/json">${dataJson}</script>
  <script>
    const dashboardData = JSON.parse(document.getElementById("dashboard-data").textContent);
    let selectedDay = "all";

    const fmtInt = new Intl.NumberFormat("zh-CN");
    function text(value) { return String(value ?? ""); }
    function html(value) {
      return text(value).replace(/[&<>"]/g, function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
      });
    }
    function pct(value) {
      const numeric = Number(value || 0);
      return (numeric * 100).toFixed(2) + "%";
    }
    function pctParts(n, d) {
      return d ? ((n / d) * 100).toFixed(2) + "%" : "0.00%";
    }
    function sessionRate(row) {
      return pctParts(row.true_activation_sessions || 0, row.click_sessions || 0);
    }
    function rowStatus(click) {
      if (!click.session_id) return '<span class="status unknown">无法匹配</span>';
      return click.true_activation
        ? '<span class="status true">是</span>'
        : '<span class="status false">否</span>';
    }
    function currentSummary() {
      if (selectedDay === "all") return dashboardData.total || {};
      return (dashboardData.daily || []).find((row) => row.date === selectedDay) || {};
    }
    function updateCards() {
      const row = currentSummary();
      document.getElementById("show-pv").textContent = fmtInt.format(row.show_pv || 0);
      document.getElementById("show-uv").textContent = "UV " + fmtInt.format(row.show_uv || 0);
      document.getElementById("click-pv").textContent = fmtInt.format(row.click_pv || 0);
      document.getElementById("click-uv").textContent = "UV " + fmtInt.format(row.click_uv || 0);
      document.getElementById("pv-rate").textContent = pct(row.pv_conversion_rate || 0);
      document.getElementById("uv-rate").textContent = "UV 转化 " + pct(row.uv_conversion_rate || 0);
      document.getElementById("activation-rate").textContent = pct(row.true_activation_rate || 0);
      document.getElementById("activation-count").textContent =
        "真激活 session " + fmtInt.format(row.true_activation_sessions || 0) +
        " / 点击 session " + fmtInt.format(row.click_sessions || 0);
    }
    function renderTabs() {
      const root = document.getElementById("day-tabs");
      const items = ["all"].concat(dashboardData.dates || []);
      root.innerHTML = items.map(function (day) {
        const label = day === "all" ? "全部" : day.slice(5);
        return '<button type="button" data-day="' + html(day) + '" aria-pressed="' + (day === selectedDay) + '">' + html(label) + '</button>';
      }).join("");
      root.querySelectorAll("button").forEach(function (button) {
        button.addEventListener("click", function () {
          selectedDay = button.dataset.day;
          render();
        });
      });
    }
    function renderDaily() {
      const rows = selectedDay === "all"
        ? dashboardData.daily || []
        : (dashboardData.daily || []).filter((row) => row.date === selectedDay);
      document.getElementById("daily-body").innerHTML = rows.map(function (row) {
        return '<tr><td>' + html(row.date) + '</td><td>' + fmtInt.format(row.show_pv || 0) + '</td><td>' + fmtInt.format(row.show_uv || 0) + '</td><td>' + fmtInt.format(row.click_pv || 0) + '</td><td>' + fmtInt.format(row.click_uv || 0) + '</td><td>' + pct(row.pv_conversion_rate || 0) + '</td><td>' + pct(row.uv_conversion_rate || 0) + '</td><td>' + fmtInt.format(row.click_sessions || 0) + '</td><td>' + fmtInt.format(row.true_activation_sessions || 0) + '</td><td>' + pct(row.true_activation_rate || 0) + '</td><td>' + fmtInt.format(row.missing_session || 0) + '</td></tr>';
      }).join("");
      const row = currentSummary();
      const label = selectedDay === "all" ? "整体" : selectedDay;
      document.getElementById("daily-note").textContent =
        label + "点击转化率 " + pct(row.pv_conversion_rate || 0) +
        "，真激活率 " + pct(row.true_activation_rate || 0) +
        "，未传 session " + fmtInt.format(row.missing_session || 0) + " 条。";
    }
    function renderShare() {
      const rows = selectedDay === "all"
        ? dashboardData.shareRows || []
        : (dashboardData.dailyShareRows || [])
            .filter((row) => row.date === selectedDay)
            .map((row) => ({
              share_id: row.share_id,
              click_pv: row.click_pv,
              click_sessions: row.click_sessions,
              uv: "",
              user_ids: "",
              missing_session: row.missing_session,
              true_activation_sessions: row.true_activation_sessions,
              true_activation_session_rate: row.true_activation_session_rate || 0,
              beijing_day_distribution: row.date + ":" + row.click_pv,
            }))
            .sort((a, b) => (b.click_pv || 0) - (a.click_pv || 0) || (b.true_activation_sessions || 0) - (a.true_activation_sessions || 0));
      const top = rows[0];
      const trueCount = rows.filter((row) => (row.true_activation_sessions || 0) > 0).length;
      document.getElementById("share-callout").innerHTML = top
        ? '当前筛选下点击 PV 第一的是 <code>' + html(top.share_id) + '</code>，共 ' + fmtInt.format(top.click_pv || 0) + ' 次点击；真激活 session 为 ' + fmtInt.format(top.true_activation_sessions || 0) + '。命中真激活的 share_id 共 ' + fmtInt.format(trueCount) + ' 个。'
        : "当前筛选下没有推荐点击。";
      document.getElementById("share-body").innerHTML = rows.map(function (row, index) {
        const active = (row.true_activation_sessions || 0) > 0 ? ' class="activation-row"' : "";
        return '<tr' + active + '><td>' + (index + 1) + '</td><td><code>' + html(row.share_id) + '</code></td><td>' + fmtInt.format(row.click_pv || 0) + '</td><td>' + fmtInt.format(row.click_sessions || 0) + '</td><td>' + html(row.uv) + '</td><td>' + html(row.user_ids) + '</td><td>' + fmtInt.format(row.true_activation_sessions || 0) + '</td><td>' + sessionRate(row) + '</td><td>' + fmtInt.format(row.missing_session || 0) + '</td><td>' + html(row.beijing_day_distribution || "") + '</td></tr>';
      }).join("");
    }
    function renderTrueDetails() {
      const rows = (dashboardData.trueDetails || []).filter((row) => selectedDay === "all" || row.beijing_date === selectedDay);
      document.getElementById("true-body").innerHTML = rows.map(function (row) {
        return '<tr class="activation-row"><td><code>' + html(row.share_id) + '</code></td><td>' + html(row.click_send_ts) + '</td><td>' + html(row.beijing_date) + '</td><td>' + html(row.user_id) + '</td><td>' + html(row.btu_id) + '</td><td>' + html(row.session_id) + '</td><td>' + html(row.first_activation_time || row.first_activation_date || "-") + '</td><td>' + html(row.query || "-") + '</td></tr>';
      }).join("") || '<tr><td colspan="8">当前筛选下没有真激活明细。</td></tr>';
    }
    function renderClicks() {
      const rows = (dashboardData.clickDetails || []).filter((row) => selectedDay === "all" || row.beijing_date === selectedDay);
      document.getElementById("click-body").innerHTML = rows.map(function (row) {
        const active = row.true_activation ? ' class="activation-row"' : "";
        return '<tr' + active + '><td>' + html(row.send_ts) + '</td><td>' + html(row.beijing_date) + '</td><td>' + html(row.user_id) + '</td><td>' + html(row.btu_id) + '</td><td>' + html(row.share_id) + '</td><td>' + html(row.session_id || "未传") + '</td><td>' + rowStatus(row) + '</td><td>' + html(row.activation_date || "-") + '</td></tr>';
      }).join("") || '<tr><td colspan="8">当前筛选下没有推荐点击。</td></tr>';
    }
    function render() {
      renderTabs();
      updateCards();
      renderDaily();
      renderShare();
      renderTrueDetails();
      renderClicks();
    }
    async function updateDashboard() {
      const button = document.getElementById("update-button");
      const status = document.getElementById("update-status");
      button.disabled = true;
      status.textContent = "正在更新...";
      try {
        const response = await fetch("/api/update", { method: "POST" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || payload.status || "update failed");
        status.textContent = "更新完成，正在刷新页面";
        location.reload();
      } catch (error) {
        status.textContent = "更新失败：" + error.message;
        button.disabled = false;
      }
    }
    function trackBuildHubHomepage() {
      const payload = JSON.stringify({
        host: location.hostname,
        path: location.pathname || "/",
        referrer: document.referrer || "",
        title: document.title || "",
        screen: screen.width + "x" + screen.height
      });
      const url = "https://build.patsnap.info/api/v1/analytics/homepage";
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([payload], { type: "text/plain;charset=UTF-8" }));
      } else {
        fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(function () {});
      }
    }
    document.getElementById("update-button").addEventListener("click", updateDashboard);
    render();
    trackBuildHubHomepage();
  </script>
</body>
</html>`;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  if (req.method === "OPTIONS") {
    send(res, 204, "");
    return;
  }
  try {
    if (req.method === "HEAD" && url.pathname === "/") {
      send(res, 200, "", { "Content-Type": "text/html; charset=utf-8" });
      return;
    }
    if (req.method === "GET" && url.pathname === "/") {
      send(res, 200, renderHtml(loadDashboardData()), {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      });
      return;
    }
    if (req.method === "GET" && url.pathname === "/api/health") {
      sendJson(res, 200, { ok: true, status: "healthy", id: "recommendation-guanyuan" });
      return;
    }
    if (req.method === "GET" && url.pathname === "/api/dashboard") {
      const data = loadDashboardData();
      sendJson(res, 200, {
        ok: true,
        dashboard: dashboardMeta(req),
        data,
      });
      return;
    }
    if ((req.method === "POST" || req.method === "GET") && url.pathname === "/api/update") {
      runUpdate(req, res);
      return;
    }
    if (req.method === "GET" && url.pathname.startsWith("/visualization/")) {
      serveStatic(req, res, url);
      return;
    }
    sendJson(res, 404, { ok: false, error: "not found" });
  } catch (error) {
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`recommendation dashboard listening on http://${HOST}:${PORT}`);
});
