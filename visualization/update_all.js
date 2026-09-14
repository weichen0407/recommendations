const { exec } = require("child_process");
const fs = require("fs");
const path = require("path");

const rootDir = path.resolve(__dirname, "..");
const outFile = path.join(__dirname, "last_update.json");
const command =
  process.env.RECOMMENDATION_UPDATE_COMMAND ||
  process.env.GUANYUAN_UPDATE_COMMAND ||
  "";

function run(commandLine) {
  return new Promise((resolve) => {
    exec(
      commandLine,
      {
        cwd: rootDir,
        timeout: Number(process.env.RECOMMENDATION_UPDATE_TIMEOUT_MS || 120000),
        maxBuffer: 1024 * 1024 * 8,
      },
      (error, stdout, stderr) => {
        resolve({
          ok: !error,
          code: error && typeof error.code === "number" ? error.code : 0,
          signal: error && error.signal ? error.signal : "",
          stdout,
          stderr,
          error: error ? error.message : "",
        });
      }
    );
  });
}

async function main() {
  const startedAt = new Date().toISOString();
  const steps = [];
  let source = "local-cache";
  let ok = true;

  if (command) {
    source = "external-command";
    const external = await run(command);
    steps.push({ name: "external_update", command, ...external });
    ok = ok && external.ok;
  }

  const aggregate = await run("node visualization/update_share_activation_report.js");
  steps.push({
    name: "aggregate_share_activation",
    command: "node visualization/update_share_activation_report.js",
    ...aggregate,
  });
  ok = ok && aggregate.ok;

  const payload = {
    ok,
    status: ok ? "updated" : "failed",
    source,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    dashboard: {
      id: "recommendation-guanyuan",
      title: "推荐系统 Guanyuan 数据",
      url: "/",
      api_url: "/api/dashboard",
      update_url: "/api/update",
    },
    steps,
  };
  fs.writeFileSync(outFile, `${JSON.stringify(payload, null, 2)}\n`);

  if (!ok) {
    console.error(JSON.stringify(payload, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify(payload, null, 2));
}

main().catch((error) => {
  const payload = {
    ok: false,
    status: "failed",
    source: command ? "external-command" : "local-cache",
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    error: error.message,
  };
  fs.writeFileSync(outFile, `${JSON.stringify(payload, null, 2)}\n`);
  console.error(JSON.stringify(payload, null, 2));
  process.exit(1);
});
