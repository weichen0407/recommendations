const fs = require("fs");
const path = require("path");

const VIS_DIR = __dirname;
const NO_FALLBACK = Symbol("NO_FALLBACK");

function readJson(filePath, fallback = NO_FALLBACK) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    if (fallback !== NO_FALLBACK) return fallback;
    throw error;
  }
}

function latestFile(regex) {
  const files = fs
    .readdirSync(VIS_DIR)
    .map((name) => {
      const match = name.match(regex);
      return match ? { name, match, fullPath: path.join(VIS_DIR, name) } : null;
    })
    .filter(Boolean)
    .sort((a, b) => {
      const endA = a.match[2] || a.match[1] || "";
      const endB = b.match[2] || b.match[1] || "";
      return endB.localeCompare(endA) || b.name.localeCompare(a.name);
    });
  return files[0] || null;
}

function parseDetail(detail = "") {
  const start = detail.indexOf("{");
  if (start < 0) return {};
  try {
    return JSON.parse(detail.slice(start));
  } catch {
    return {};
  }
}

function realUserId(row) {
  const value = String(row.user_id || "").trim();
  return value && value !== "0000000000000000" ? value : "";
}

function effectiveVisitor(row, index) {
  const detail = parseDetail(row.event_detail || "");
  const candidates = [
    realUserId(row),
    row.btu_id,
    detail.session_id,
    row.raw_session_id,
    row.resolved_session_id,
  ];
  for (const value of candidates) {
    const normalized = String(value || "").trim();
    if (normalized && normalized !== "0000000000000000") return normalized;
  }
  return `row:${index}`;
}

function beijingDate(sendTs) {
  const normalized = String(sendTs || "").trim();
  if (!normalized) return "";
  const time = Date.parse(`${normalized.replace(" ", "T")}Z`);
  if (Number.isNaN(time)) return normalized.slice(0, 10);
  return new Date(time + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function activationMap() {
  const file = latestFile(
    /^recommendation_click_true_activation_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_latest\.json$/
  );
  if (!file) return new Map();
  const rows = readJson(file.fullPath, []);
  return new Map(rows.map((row) => [row.resolved_session_id, row]));
}

function loadClickDetails() {
  const file = latestFile(/^plg_click_rc_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_latest\.json$/);
  if (!file) return [];
  const rows = readJson(file.fullPath, []);
  const activations = activationMap();
  return rows
    .map((row, index) => {
      const detail = parseDetail(row.event_detail || "");
      const sessionId = detail.session_id || "";
      const activation = activations.get(sessionId);
      const isTrueActivation =
        activation && String(activation.is_true_activation_session) === "1";
      return {
        send_ts: row.send_ts || "",
        beijing_date: beijingDate(row.send_ts),
        user_id: row.user_id || "",
        btu_id: row.btu_id || "",
        visitor_id: effectiveVisitor(row, index),
        share_id: detail.share_id || "",
        session_id: sessionId,
        true_activation: Boolean(isTrueActivation),
        activation_date: isTrueActivation ? activation.first_activation_date || "" : "",
        activation_time: isTrueActivation ? activation.first_activation_time || "" : "",
        query: isTrueActivation ? activation.full_query_with_round || "" : "",
      };
    })
    .sort((a, b) => a.send_ts.localeCompare(b.send_ts));
}

function loadDashboardData() {
  const dailyFile = latestFile(
    /^recommendation_daily_summary_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$/
  );
  const shareFile = latestFile(
    /^recommendation_share_id_summary_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$/
  );
  const daily = dailyFile ? readJson(dailyFile.fullPath, {}) : {};
  const share = shareFile ? readJson(shareFile.fullPath, {}) : {};
  const clickDetails = loadClickDetails();
  const lastUpdate = readJson(path.join(VIS_DIR, "last_update.json"), null);

  const dates = Array.from(
    new Set([
      ...(daily.daily || []).map((row) => row.date),
      ...(share.dailyShareRows || []).map((row) => row.date),
      ...clickDetails.map((row) => row.beijing_date),
    ].filter(Boolean))
  ).sort();

  return {
    id: "recommendation-guanyuan",
    title: "推荐系统 Guanyuan 数据",
    timezone: daily.timezone || "Asia/Shanghai",
    day_bucket: daily.day_bucket || "send_ts 北京时间日",
    generated_at: daily.generated_at || share.generated_at || "",
    dataset_updated_at: daily.dataset_updated_at || "",
    activation_dataset_updated_at: daily.activation_dataset_updated_at || "",
    date_range: daily.date_range || [dates[0] || "", dates[dates.length - 1] || ""],
    dates,
    daily: daily.daily || [],
    total: daily.total || {},
    shareRows: share.shareRows || [],
    dailyShareRows: share.dailyShareRows || [],
    trueDetails: share.trueDetails || [],
    clickDetails,
    files: {
      daily_summary: dailyFile ? dailyFile.name : "",
      share_summary: shareFile ? shareFile.name : "",
    },
    last_update: lastUpdate,
    endpoints: {
      dashboard: "/api/dashboard",
      update: "/api/update",
      health: "/api/health",
    },
  };
}

module.exports = {
  loadDashboardData,
};
