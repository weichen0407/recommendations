const fs = require("fs");
const path = require("path");

const outDir = __dirname;
const dates = ["2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12"];
const latestDate = dates[dates.length - 1];
const reportFiles = [
  `recommendation_guanyuan_report_${latestDate}.html`,
  "recommendation_guanyuan_report_2026-09-11.html",
  "recommendation_guanyuan_report_2026-09-10.html",
];

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(outDir, name), "utf8"));
}

function readText(name) {
  return fs.readFileSync(path.join(outDir, name), "utf8");
}

function extractUpdateTime(name) {
  const text = readText(name);
  const match = text.match(/- 更新: ([^\n]+)/);
  return match ? match[1].trim() : "未知";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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

function effectiveVisitor(row, index) {
  const parsed = parseDetail(row.event_detail || "");
  const candidates = [
    row.user_id,
    row.btu_id,
    parsed.session_id,
    row.raw_session_id,
    row.resolved_session_id,
  ];
  for (const value of candidates) {
    const normalized = String(value || "").trim();
    if (normalized && normalized !== "0000000000000000") return normalized;
  }
  return `row:${index}`;
}

function pct(numerator, denominator) {
  if (!denominator) return "0.00%";
  return `${((numerator / denominator) * 100).toFixed(2)}%`;
}

function hourDistribution(rows) {
  const counts = new Map();
  for (const row of rows) {
    const hour = (row.send_ts || "").slice(11, 13) || "??";
    counts.set(hour, (counts.get(hour) || 0) + 1);
  }
  if (!counts.size) return "无";
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([hour, count]) => `${hour} 点 ${count}`)
    .join("；");
}

function statusCell(click, activation) {
  if (!click.session_id) {
    return {
      label: "无法匹配",
      cls: "unknown",
      activationDate: "-",
      rowClass: "",
    };
  }
  if (activation && String(activation.is_true_activation_session) === "1") {
    return {
      label: "是",
      cls: "true",
      activationDate: activation.first_activation_date || "-",
      rowClass: " class=\"activation-row\"",
    };
  }
  return {
    label: "否",
    cls: "false",
    activationDate: "-",
    rowClass: "",
  };
}

function compactDate(date) {
  return date.replace("2026-09-", "9/");
}

const sourceRows = {};
for (const date of dates) {
  sourceRows[date] = {
    show: readJson(`plg_show_rc_${date}.json`),
    click: readJson(`plg_click_rc_${date}.json`),
  };
}

const eventDatasetUpdatedAt = extractUpdateTime("recommendation_events_dataset_latest.txt");
const activationDatasetUpdatedAt = extractUpdateTime("true_activation_dataset_latest.txt");
const activationRows = readJson(`recommendation_click_true_activation_2026-09-09_${latestDate}.json`);
const activationBySession = new Map(
  activationRows.map((row) => [row.resolved_session_id, row])
);

const daily = dates.map((date) => {
  const show = sourceRows[date].show;
  const click = sourceRows[date].click;
  const clickDetails = click.map((row) => parseDetail(row.event_detail || ""));
  const trueActivationSessions = new Set();
  for (const detail of clickDetails) {
    const session = detail.session_id;
    const activation = activationBySession.get(session);
    if (activation && String(activation.is_true_activation_session) === "1") {
      trueActivationSessions.add(session);
    }
  }
  return {
    date,
    showPv: show.length,
    showUv: new Set(show.map(effectiveVisitor)).size,
    clickPv: click.length,
    clickUv: new Set(click.map(effectiveVisitor)).size,
    shareIds: new Set(clickDetails.map((item) => item.share_id).filter(Boolean)).size,
    sessions: new Set(clickDetails.map((item) => item.session_id).filter(Boolean)).size,
    missingSessions: clickDetails.filter((item) => !item.session_id).length,
    trueActivationSessions: trueActivationSessions.size,
    showHours: hourDistribution(show),
    clickHours: hourDistribution(click),
  };
});

const totalShowVisitors = new Set();
const totalClickVisitors = new Set();
let totalShowPv = 0;
let totalClickPv = 0;
for (const date of dates) {
  const show = sourceRows[date].show;
  const click = sourceRows[date].click;
  totalShowPv += show.length;
  totalClickPv += click.length;
  show.forEach((row, index) => totalShowVisitors.add(effectiveVisitor(row, index)));
  click.forEach((row, index) => totalClickVisitors.add(effectiveVisitor(row, index)));
}

const clicks = [];
for (const date of dates) {
  for (const row of sourceRows[date].click) {
    const detail = parseDetail(row.event_detail || "");
    clicks.push({
      date,
      send_ts: row.send_ts || "",
      user_id: row.user_id || "",
      btu_id: row.btu_id || "",
      share_id: detail.share_id || "",
      session_id: detail.session_id || "",
    });
  }
}
clicks.sort((a, b) => a.send_ts.localeCompare(b.send_ts));

const distinctShareIds = new Set(clicks.map((item) => item.share_id).filter(Boolean));
const distinctSessions = new Set(clicks.map((item) => item.session_id).filter(Boolean));
const missingSessionEvents = clicks.filter((item) => !item.session_id).length;
const trueActivationClicks = clicks.filter((click) => {
  const activation = activationBySession.get(click.session_id);
  return activation && String(activation.is_true_activation_session) === "1";
});
const trueActivationSessions = new Set(trueActivationClicks.map((item) => item.session_id));

const shareSummary = new Map();
for (const click of clicks) {
  const key = `${click.date}\t${click.share_id || "未传"}`;
  if (!shareSummary.has(key)) {
    shareSummary.set(key, {
      date: click.date,
      share_id: click.share_id || "未传",
      pv: 0,
      sessions: new Set(),
      missing: 0,
    });
  }
  const current = shareSummary.get(key);
  current.pv += 1;
  if (click.session_id) current.sessions.add(click.session_id);
  else current.missing += 1;
}

const maxShowPv = Math.max(1, ...daily.map((item) => item.showPv));
const styleMatch = readText("recommendation_guanyuan_report_2026-09-11.html").match(
  /<style>[\s\S]*?<\/style>/
);
const style = styleMatch ? styleMatch[0] : "<style></style>";

const dailyRows = daily
  .map(
    (item) => `
          <tr>
            <td>${item.date}</td>
            <td>${item.showPv}</td>
            <td>${item.showUv}</td>
            <td>${item.clickPv}</td>
            <td>${item.clickUv}</td>
            <td>${pct(item.clickPv, item.showPv)}</td>
            <td>${item.shareIds}</td>
            <td>${item.sessions}</td>
            <td>${item.trueActivationSessions}</td>
            <td>${item.missingSessions}</td>
          </tr>`
  )
  .join("");

const pvUvRows = daily
  .flatMap((item) => [
    `<tr><td>${item.date}</td><td>推荐板块展开</td><td>${item.showPv}</td><td>${item.showUv}</td><td><code>source_type=plg_show_rc</code></td></tr>`,
    `<tr><td>${item.date}</td><td>RD Home 触发对话</td><td>${item.clickPv}</td><td>${item.clickUv}</td><td><code>source_type=plg_click_rc</code></td></tr>`,
  ])
  .join("\n");

const funnelRows = daily
  .flatMap((item) => {
    const showWidth = ((item.showPv / maxShowPv) * 100).toFixed(1);
    const clickWidth = ((item.clickPv / maxShowPv) * 100).toFixed(1);
    return [
      `<div class="funnel-row">
            <div><strong>${compactDate(item.date)} 展开</strong><br><span class="subline">plg_show_rc</span></div>
            <div class="bar-track"><div class="bar" style="width: ${showWidth}%"></div></div>
            <div class="right">${item.showPv}</div>
          </div>`,
      `<div class="funnel-row">
            <div><strong>${compactDate(item.date)} 触发</strong><br><span class="subline">plg_click_rc</span></div>
            <div class="bar-track"><div class="bar click" style="width: ${clickWidth}%"></div></div>
            <div class="right">${item.clickPv}</div>
          </div>`,
    ];
  })
  .join("\n");

const hourRows = daily
  .map(
    (item) =>
      `<tr><td>${item.date}</td><td>${escapeHtml(item.showHours)}</td><td>${escapeHtml(item.clickHours)}</td></tr>`
  )
  .join("\n");

const shareRows = [...shareSummary.values()]
  .sort((a, b) => a.date.localeCompare(b.date) || b.pv - a.pv || a.share_id.localeCompare(b.share_id))
  .map((item) => {
    const sessionText = item.missing
      ? item.sessions.size
        ? `${item.sessions.size} 个 session，${item.missing} 条未传`
        : "未传 session_id"
      : `${item.sessions.size} 个 session`;
    return `<tr><td>${item.date}</td><td>${escapeHtml(item.share_id)}</td><td>${item.pv}</td><td>${sessionText}</td></tr>`;
  })
  .join("\n");

const clickRows = clicks
  .map((click) => {
    const activation = activationBySession.get(click.session_id);
    const status = statusCell(click, activation);
    return `<tr${status.rowClass}><td>${escapeHtml(click.send_ts)}</td><td>${escapeHtml(click.user_id)}</td><td>${escapeHtml(click.btu_id)}</td><td>${escapeHtml(click.share_id)}</td><td>${escapeHtml(click.session_id || "未传")}</td><td><span class="status ${status.cls}">${status.label}</span></td><td>${status.activationDate}</td></tr>`;
  })
  .join("\n");

const metrics = [];
for (const item of daily) {
  metrics.push({
    scope: "recommendation_events",
    date: item.date,
    metric: "plg_show_rc",
    label: "推荐板块展开",
    pv: item.showPv,
    uv: item.showUv,
  });
  metrics.push({
    scope: "recommendation_events",
    date: item.date,
    metric: "plg_click_rc",
    label: "RD Home 触发对话",
    pv: item.clickPv,
    uv: item.clickUv,
  });
}
metrics.push({
  scope: "recommendation_events",
  date: "total",
  metric: "plg_show_rc",
  label: "推荐板块展开",
  pv: totalShowPv,
  uv: totalShowVisitors.size,
});
metrics.push({
  scope: "recommendation_events",
  date: "total",
  metric: "plg_click_rc",
  label: "RD Home 触发对话",
  pv: totalClickPv,
  uv: totalClickVisitors.size,
});

const trueActivationMatches = trueActivationClicks.map((click) => {
  const activation = activationBySession.get(click.session_id);
  return {
    click_send_ts: click.send_ts,
    share_id: click.share_id,
    user_id: click.user_id,
    btu_id: click.btu_id,
    session_id: click.session_id,
    first_activation_date: activation.first_activation_date || "",
  };
});

const summary = {
  generated_at: latestDate,
  dataset_updated_at: eventDatasetUpdatedAt,
  activation_dataset_updated_at: activationDatasetUpdatedAt,
  date_range: [dates[0], latestDate],
  metrics,
  click_summary: {
    total_click_pv: totalClickPv,
    distinct_share_id: distinctShareIds.size,
    distinct_session_id: distinctSessions.size,
    missing_session_id_events: missingSessionEvents,
    true_activation_click_sessions: trueActivationSessions.size,
    true_activation_click_events: trueActivationClicks.length,
    true_activation_session_rate: Number((trueActivationSessions.size / Math.max(1, distinctSessions.size)).toFixed(4)),
    pv_conversion_rate: Number((totalClickPv / Math.max(1, totalShowPv)).toFixed(4)),
    uv_conversion_rate: Number((totalClickVisitors.size / Math.max(1, totalShowVisitors.size)).toFixed(4)),
  },
  true_activation_matches: trueActivationMatches,
  notes: {
    recommendation_uv:
      "有效访客口径：优先 user_id，其次 btu_id、event_detail.session_id、raw_session_id，最后 resolved_session_id 行级兜底。",
    true_activation:
      "按推荐点击事件里的 session_id 精确匹配真激活表 resolved_session_id，且 is_true_activation_session=1。",
    latest_data: `${latestDate} 数据截至推荐事件数据集更新 ${eventDatasetUpdatedAt}；当前 ${latestDate} 未查询到 plg_show_rc/plg_click_rc。`,
  },
};

const latestEmptyNote =
  daily[daily.length - 1].showPv === 0 && daily[daily.length - 1].clickPv === 0
    ? `${latestDate} 暂无推荐展开或推荐点击记录。`
    : `${latestDate} 已有推荐事件入库。`;

const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>推荐系统 Guanyuan 数据 - ${dates[0]} 至 ${latestDate}</title>
  ${style}
</head>
<body>
  <main class="page">
    <header>
      <div class="eyebrow">Guanyuan 数据快看</div>
      <h1>推荐展开与推荐点击</h1>
      <div class="meta">
        日期：${dates[0]} 至 ${latestDate}。<br>
        只看推荐板块展开 <code>plg_show_rc</code>，以及推荐点击 / 触发对话 <code>plg_click_rc</code>。<br>
        推荐事件数据集更新至 <code>${eventDatasetUpdatedAt}</code>；真激活数据集更新至 <code>${activationDatasetUpdatedAt}</code>。
      </div>
    </header>

    <section class="grid cards" aria-label="四日合计指标">
      <article class="card">
        <div>
          <div class="label">推荐板块展开，四日合计</div>
          <div class="metric"><span class="number">${totalShowPv}</span><span class="unit">PV</span></div>
        </div>
        <div class="subline"><span class="tag">plg_show_rc</span> 有效 UV ${totalShowVisitors.size}</div>
      </article>

      <article class="card">
        <div>
          <div class="label">RD Home 触发对话，四日合计</div>
          <div class="metric"><span class="number">${totalClickPv}</span><span class="unit">PV</span></div>
        </div>
        <div class="subline"><span class="tag">plg_click_rc</span> 有效 UV ${totalClickVisitors.size}</div>
      </article>

      <article class="card">
        <div>
          <div class="label">点击 / 展开转化</div>
          <div class="metric"><span class="number">${pct(totalClickPv, totalShowPv)}</span><span class="unit">PV</span></div>
        </div>
        <div class="subline">有效 UV 转化 ${pct(totalClickVisitors.size, totalShowVisitors.size)}</div>
      </article>

      <article class="card">
        <div>
          <div class="label">点击事件 share_id</div>
          <div class="metric"><span class="number">${distinctShareIds.size}</span><span class="unit">share_id</span></div>
        </div>
        <div class="subline">共 ${totalClickPv} 次点击，${distinctSessions.size} 个 session_id；真激活 session ${trueActivationSessions.size} 个</div>
      </article>
    </section>

    <section class="panel">
      <h2>推荐展开 / 点击总览</h2>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>展开 PV</th>
            <th>展开 UV</th>
            <th>触发 PV</th>
            <th>触发 UV</th>
            <th>PV 转化</th>
            <th>share_id</th>
            <th>session_id</th>
            <th>真激活 session</th>
            <th>未传 session</th>
          </tr>
        </thead>
        <tbody>${dailyRows}
          <tr>
            <td><strong>合计</strong></td>
            <td><strong>${totalShowPv}</strong></td>
            <td><strong>${totalShowVisitors.size}</strong></td>
            <td><strong>${totalClickPv}</strong></td>
            <td><strong>${totalClickVisitors.size}</strong></td>
            <td><strong>${pct(totalClickPv, totalShowPv)}</strong></td>
            <td><strong>${distinctShareIds.size}</strong></td>
            <td><strong>${distinctSessions.size}</strong></td>
            <td><strong>${trueActivationSessions.size}</strong></td>
            <td><strong>${missingSessionEvents}</strong></td>
          </tr>
        </tbody>
      </table>
      <div class="note">
        ${latestEmptyNote} 当前 ${distinctSessions.size} 个已传 session_id 中有 ${trueActivationSessions.size} 个命中真激活，真激活 session 率 ${pct(trueActivationSessions.size, distinctSessions.size)}。
      </div>
    </section>

    <section class="panel section-gap">
      <h2>PV / UV 记录</h2>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>指标</th>
            <th>PV</th>
            <th>UV</th>
            <th>口径</th>
          </tr>
        </thead>
        <tbody>
${pvUvRows}
          <tr><td><strong>合计</strong></td><td><strong>推荐板块展开</strong></td><td><strong>${totalShowPv}</strong></td><td><strong>${totalShowVisitors.size}</strong></td><td>四日合并去重 UV</td></tr>
          <tr><td><strong>合计</strong></td><td><strong>RD Home 触发对话</strong></td><td><strong>${totalClickPv}</strong></td><td><strong>${totalClickVisitors.size}</strong></td><td>四日合并去重 UV</td></tr>
        </tbody>
      </table>
      <div class="note">
        UV 使用有效访客口径：优先非空且非 <code>0000000000000000</code> 的 <code>user_id</code>，其次使用 <code>btu_id</code>、点击里的 <code>session_id</code> 等兜底。
      </div>
    </section>

    <section class="grid two-col section-gap">
      <article class="panel">
        <h2>按天链路漏斗</h2>
        <div class="funnel">
          ${funnelRows}
        </div>
      </article>

      <article class="panel">
        <h2>小时分布</h2>
        <table>
          <thead>
            <tr><th>日期</th><th>展开小时</th><th>点击小时</th></tr>
          </thead>
          <tbody>
${hourRows}
          </tbody>
        </table>
        <div class="section-gap subline">四天导出均未触达 60,000 行预览上限。</div>
      </article>
    </section>

    <section class="panel section-gap">
      <h2>share_id 汇总</h2>
      <table>
        <thead>
          <tr><th>日期</th><th>share_id</th><th>点击次数</th><th>session_id 情况</th></tr>
        </thead>
        <tbody>
${shareRows}
        </tbody>
      </table>
    </section>

    <section class="panel section-gap">
      <h2>推荐点击事件明细</h2>
      <div class="callout">
        这里只展示 <code>plg_click_rc</code> 点击事件，重点看每次点击传入的 <code>share_id</code> 和 <code>user_id</code>。真激活按点击事件的 <code>session_id</code> 精确匹配会话主表。
      </div>
      <table class="section-gap">
        <thead>
          <tr>
            <th>send_ts</th>
            <th>user_id</th>
            <th>btu_id</th>
            <th>share_id</th>
            <th>session_id</th>
            <th>真激活</th>
            <th>激活日期</th>
          </tr>
        </thead>
        <tbody>
${clickRows}
        </tbody>
      </table>
    </section>

    <section class="panel section-gap">
      <h2>口径说明</h2>
      <div class="kv">
        <div>数据日期</div>
        <div>${dates[0]} 至 ${latestDate}；推荐事件数据集更新至 <code>${eventDatasetUpdatedAt}</code>。</div>
        <div>数据集</div>
        <div>推荐事件来自 eureka产品行为数据 - 2025年1月及以后-关联付费属性；真激活来自 RunWise重构验证-会话主表与真激活，更新至 <code>${activationDatasetUpdatedAt}</code>。</div>
        <div>PV</div>
        <div>按过滤后的事件行数计算：<code>source_type=plg_show_rc</code> 为展开，<code>source_type=plg_click_rc</code> 为触发对话。</div>
        <div>有效 UV</div>
        <div>优先使用非空且非 <code>0000000000000000</code> 的 <code>user_id</code>，其次使用 <code>btu_id</code>，再用 <code>event_detail.session_id</code> 或 <code>raw_session_id</code>。如果仍缺失，只能落到 <code>resolved_session_id</code> 的行级兜底。</div>
        <div>真激活</div>
        <div>按推荐点击事件里的 <code>session_id</code> 精确匹配真激活表的 <code>resolved_session_id</code>，且 <code>is_true_activation_session=1</code>。当前命中 ${trueActivationSessions.size} 个点击 session。</div>
        <div>本地文件</div>
        <div>明细导出保存在 <code>plg_show_rc_*.json</code>、<code>plg_click_rc_*.json</code>，真激活匹配保存在 <code>recommendation_click_true_activation_2026-09-09_${latestDate}.json</code>。</div>
      </div>
    </section>
  </main>
</body>
</html>
`;

for (const file of reportFiles) {
  fs.writeFileSync(path.join(outDir, file), html);
}

fs.writeFileSync(
  path.join(outDir, `recommendation_pv_uv_summary_2026-09-09_${latestDate}.json`),
  `${JSON.stringify(summary, null, 2)}\n`
);

console.log(
  JSON.stringify(
    {
      latestDate,
      totalShowPv,
      totalShowUv: totalShowVisitors.size,
      totalClickPv,
      totalClickUv: totalClickVisitors.size,
      distinctShareIds: distinctShareIds.size,
      distinctSessions: distinctSessions.size,
      missingSessionEvents,
      trueActivationSessions: trueActivationSessions.size,
      reportFiles,
    },
    null,
    2
  )
);
