const fs = require("fs");
const path = require("path");

const outDir = __dirname;

function latestRangeFile(prefix) {
  const files = fs
    .readdirSync(outDir)
    .map((name) => {
      const match = name.match(
        new RegExp(`^${prefix}_(\\d{4}-\\d{2}-\\d{2})_(\\d{4}-\\d{2}-\\d{2})_latest\\.json$`)
      );
      return match ? { name, startDate: match[1], latestDate: match[2] } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.latestDate.localeCompare(a.latestDate) || b.name.localeCompare(a.name));
  if (!files.length) {
    throw new Error(`找不到 ${prefix}_*_latest.json`);
  }
  return files[0];
}

const clickRange = latestRangeFile("plg_click_rc");
const startDate = clickRange.startDate;
const latestDate = clickRange.latestDate;
const clickFile = clickRange.name;
const activationFile = `recommendation_click_true_activation_${startDate}_${latestDate}_latest.json`;

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(outDir, name), "utf8"));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
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

function pct(numerator, denominator) {
  if (!denominator) return "0.00%";
  return `${((numerator / denominator) * 100).toFixed(2)}%`;
}

function sessionText(sessions, missing) {
  if (missing) {
    return sessions
      ? `${sessions} 个 session，${missing} 条未传`
      : "未传 session_id";
  }
  return `${sessions} 个 session`;
}

function getBucket(map, key, init) {
  if (!map.has(key)) map.set(key, init());
  return map.get(key);
}

const clicks = readJson(clickFile);
const activations = readJson(activationFile);
const activationBySession = new Map(
  activations.map((row) => [row.resolved_session_id, row])
);

const overall = new Map();
const byDay = new Map();
const trueDetails = [];

clicks.forEach((row, index) => {
  const detail = parseDetail(row.event_detail || "");
  const shareId = detail.share_id || "未传";
  const sessionId = detail.session_id || "";
  const day = beijingDate(row.send_ts);
  const activation = activationBySession.get(sessionId);
  const isTrueActivation =
    activation && String(activation.is_true_activation_session) === "1";

  const baseInit = () => ({
    share_id: shareId,
    pv: 0,
    sessions: new Set(),
    missing: 0,
    uv: new Set(),
    userIds: new Set(),
    trueSessions: new Set(),
    truePv: 0,
    trueUserIds: new Set(),
    days: new Map(),
  });

  const current = getBucket(overall, shareId, baseInit);
  current.pv += 1;
  current.uv.add(effectiveVisitor(row, index));
  const userId = realUserId(row);
  if (userId) current.userIds.add(userId);
  if (sessionId) current.sessions.add(sessionId);
  else current.missing += 1;
  current.days.set(day, (current.days.get(day) || 0) + 1);

  const dayKey = `${day}\t${shareId}`;
  const daily = getBucket(byDay, dayKey, () => ({
    date: day,
    share_id: shareId,
    pv: 0,
    sessions: new Set(),
    missing: 0,
    trueSessions: new Set(),
    truePv: 0,
  }));
  daily.pv += 1;
  if (sessionId) daily.sessions.add(sessionId);
  else daily.missing += 1;

  if (isTrueActivation) {
    current.truePv += 1;
    current.trueSessions.add(sessionId);
    if (userId) current.trueUserIds.add(userId);
    daily.truePv += 1;
    daily.trueSessions.add(sessionId);
    trueDetails.push({
      share_id: shareId,
      click_send_ts: row.send_ts || "",
      beijing_date: day,
      user_id: row.user_id || "",
      btu_id: row.btu_id || "",
      session_id: sessionId,
      first_activation_time: activation.first_activation_time || "",
      first_activation_date: activation.first_activation_date || "",
      query: activation.full_query_with_round || "",
    });
  }
});

const shareRows = [...overall.values()]
  .map((item) => ({
    share_id: item.share_id,
    click_pv: item.pv,
    click_sessions: item.sessions.size,
    uv: item.uv.size,
    user_ids: item.userIds.size,
    missing_session: item.missing,
    true_activation_sessions: item.trueSessions.size,
    true_activation_pv: item.truePv,
    true_activation_users: item.trueUserIds.size,
    true_activation_session_rate: item.sessions.size
      ? item.trueSessions.size / item.sessions.size
      : 0,
    true_activation_pv_rate: item.pv ? item.truePv / item.pv : 0,
    beijing_day_distribution: [...item.days.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, count]) => `${date}:${count}`)
      .join("；"),
  }))
  .sort(
    (a, b) =>
      b.click_pv - a.click_pv ||
      b.true_activation_sessions - a.true_activation_sessions ||
      a.share_id.localeCompare(b.share_id)
  );

const dailyShareRows = [...byDay.values()]
  .map((item) => ({
    date: item.date,
    share_id: item.share_id,
    click_pv: item.pv,
    click_sessions: item.sessions.size,
    missing_session: item.missing,
    true_activation_sessions: item.trueSessions.size,
    true_activation_pv: item.truePv,
    true_activation_session_rate: item.sessions.size
      ? item.trueSessions.size / item.sessions.size
      : 0,
  }))
  .sort(
    (a, b) =>
      a.date.localeCompare(b.date) ||
      b.click_pv - a.click_pv ||
      b.true_activation_sessions - a.true_activation_sessions ||
      a.share_id.localeCompare(b.share_id)
  );

const topShare = shareRows[0];
const trueShareIds = shareRows.filter((row) => row.true_activation_sessions > 0);

const rankRowsHtml = shareRows
  .map((row, index) => {
    const trClass = row.true_activation_sessions ? " class=\"activation-row\"" : "";
    return `<tr${trClass}><td>${index + 1}</td><td><code>${escapeHtml(row.share_id)}</code></td><td>${row.click_pv}</td><td>${row.click_sessions}</td><td>${row.uv}</td><td>${row.user_ids}</td><td>${row.true_activation_sessions}</td><td>${pct(row.true_activation_sessions, row.click_sessions)}</td><td>${row.missing_session}</td><td>${escapeHtml(row.beijing_day_distribution)}</td></tr>`;
  })
  .join("\n");

const dailyRowsHtml = dailyShareRows
  .map((row) => {
    const trClass = row.true_activation_sessions ? " class=\"activation-row\"" : "";
    return `<tr${trClass}><td>${row.date}</td><td><code>${escapeHtml(row.share_id)}</code></td><td>${row.click_pv}</td><td>${sessionText(row.click_sessions, row.missing_session)}</td><td>${row.true_activation_sessions}</td><td>${pct(row.true_activation_sessions, row.click_sessions)}</td></tr>`;
  })
  .join("\n");

const trueDetailsRowsHtml = trueDetails
  .map(
    (row) =>
      `<tr class="activation-row"><td><code>${escapeHtml(row.share_id)}</code></td><td>${escapeHtml(row.click_send_ts)}</td><td>${escapeHtml(row.beijing_date)}</td><td>${escapeHtml(row.user_id)}</td><td>${escapeHtml(row.btu_id)}</td><td>${escapeHtml(row.session_id)}</td><td>${escapeHtml(row.first_activation_time || row.first_activation_date || "-")}</td><td>${escapeHtml(row.query || "-")}</td></tr>`
  )
  .join("\n");

const shareSection = `    <section class="panel section-gap"><h2>share_id 点击与真激活排行</h2><div class="callout">点击 PV 第一的是 <code>${escapeHtml(topShare.share_id)}</code>，共 ${topShare.click_pv} 次点击；它当前真激活 session 为 ${topShare.true_activation_sessions}。真激活命中的 share_id 共 ${trueShareIds.length} 个，合计 ${trueDetails.length} 个点击 session。</div><table class="section-gap"><thead><tr><th>排名</th><th>share_id</th><th>点击PV</th><th>点击session</th><th>UV</th><th>user_id数</th><th>真激活session</th><th>真激活率</th><th>未传session</th><th>点击日期分布（北京时间）</th></tr></thead><tbody>${rankRowsHtml}</tbody></table></section>
    <section class="panel section-gap"><h2>真激活 share_id 明细</h2><table><thead><tr><th>share_id</th><th>click send_ts</th><th>北京时间日</th><th>user_id</th><th>btu_id</th><th>session_id</th><th>激活时间</th><th>query</th></tr></thead><tbody>${trueDetailsRowsHtml}</tbody></table></section>
    <section class="panel section-gap"><h2>share_id 按天汇总</h2><table><thead><tr><th>北京时间日期</th><th>share_id</th><th>点击次数</th><th>session_id 情况</th><th>真激活session</th><th>真激活率</th></tr></thead><tbody>${dailyRowsHtml}</tbody></table></section>
`;

const reportFiles = fs
  .readdirSync(outDir)
  .filter((name) => /^recommendation_guanyuan_report_2026-09-\d{2}\.html$/.test(name));
const updatedReportFiles = [];
const skippedReportFiles = [];

for (const file of reportFiles) {
  const fullPath = path.join(outDir, file);
  const html = fs.readFileSync(fullPath, "utf8");
  const shareSectionPattern =
    /    <section class="panel section-gap"><h2>share_id[\s\S]*?(?=    <section class="panel section-gap"><h2>推荐点击事件明细)/;
  if (!shareSectionPattern.test(html)) {
    skippedReportFiles.push(file);
    continue;
  }
  const next = html.replace(
    shareSectionPattern,
    shareSection
  );
  fs.writeFileSync(fullPath, next);
  updatedReportFiles.push(file);
}

const exportBase = `recommendation_share_id_summary_${startDate}_${latestDate}`;
fs.writeFileSync(
  path.join(outDir, `${exportBase}.json`),
  `${JSON.stringify({ generated_at: new Date().toISOString(), shareRows, dailyShareRows, trueDetails }, null, 2)}\n`
);

const csvHeader = [
  "share_id",
  "click_pv",
  "click_sessions",
  "uv",
  "user_id_count",
  "missing_session",
  "true_activation_sessions",
  "true_activation_pv",
  "true_activation_session_rate",
  "true_activation_pv_rate",
  "beijing_day_distribution",
];
const csvRows = shareRows.map((row) =>
  [
    row.share_id,
    row.click_pv,
    row.click_sessions,
    row.uv,
    row.user_ids,
    row.missing_session,
    row.true_activation_sessions,
    row.true_activation_pv,
    row.true_activation_session_rate.toFixed(4),
    row.true_activation_pv_rate.toFixed(4),
    row.beijing_day_distribution,
  ]
    .map(csvCell)
    .join(",")
);
fs.writeFileSync(
  path.join(outDir, `${exportBase}.csv`),
  `${csvHeader.join(",")}\n${csvRows.join("\n")}\n`
);

console.log(
  JSON.stringify(
    {
      reportFiles,
      updatedReportFiles,
      skippedReportFiles,
      exportBase,
      clickPv: clicks.length,
      shareIds: shareRows.length,
      trueActivationShareIds: trueShareIds.length,
      trueActivationSessions: trueDetails.length,
      topShare,
      trueShareIds: trueShareIds.map((row) => ({
        share_id: row.share_id,
        click_pv: row.click_pv,
        click_sessions: row.click_sessions,
        true_activation_sessions: row.true_activation_sessions,
        true_activation_session_rate: row.true_activation_session_rate,
      })),
    },
    null,
    2
  )
);
