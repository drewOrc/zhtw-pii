// Supplementary run for a fifth model added after the main matrix started:
// ckiplab/albert-tiny-chinese-ner turned out to be unsupported by
// transformers.js ("Unsupported model type: albert", see results/s1_results.json
// models["ckip-albert-tiny-ner"].unsupported_error), which left a large gap
// (11 MB to 99 MB) between the two remaining small points and the two large
// ones. Xenova/paraphrase-MiniLM-L3-v2 (16.64 MiB int8) fills that gap. It is
// English-only, not zh-relevant for accuracy, included purely as a
// size/latency curve anchor -- see RESULTS.md.
//
// Same methodology as run_benchmark.mjs (see that file and RESULTS.md
// Methodology), duplicated rather than shared to avoid touching the main
// script while its own run was in flight. Writes results/s1_results_extra.json,
// merged into the final write-up by hand.

import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SPIKE_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MODELS_DIR = path.join(SPIKE_ROOT, "models");
const RESULTS_DIR = path.join(SPIKE_ROOT, "results");
const TESTSET_PATH = path.join(SPIKE_ROOT, "..", "..", "data", "testset", "v0", "test.jsonl");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".onnx": "application/octet-stream",
  ".wasm": "application/wasm",
  ".txt": "text/plain; charset=utf-8",
};

const NETWORKS = {
  "desktop-unthrottled": null,
  "mobile-4g": { offline: false, downloadThroughput: 10_000_000 / 8, uploadThroughput: 5_000_000 / 8, latency: 40 },
  "mobile-fast3g": { offline: false, downloadThroughput: 1_600_000 / 8, uploadThroughput: 750_000 / 8, latency: 150 },
};

const MOBILE_CONTEXT_OPTIONS = {
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  userAgent:
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) " +
    "Chrome/153.0.8010.12 Mobile Safari/537.36",
};

function readSentences(limit) {
  const lines = fs.readFileSync(TESTSET_PATH, "utf-8").trim().split("\n");
  return lines.slice(0, limit).map((line) => JSON.parse(line).text);
}
function fileSizeBytes(...parts) {
  return fs.statSync(path.join(...parts)).size;
}
function median(values) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}
function percentile(values, p) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}
function summarize(runs) {
  const okRuns = runs.filter((r) => !r.error && !r.timed_out);
  if (okRuns.length === 0) return { ok_run_count: 0 };
  const coldLoads = okRuns.map((r) => r.cold_load_ms);
  const firstInferences = okRuns.map((r) => r.first_inference_ms);
  const pooledLatencies = okRuns.flatMap((r) => r.latencies_ms);
  return {
    ok_run_count: okRuns.length,
    cold_load_ms: { median: median(coldLoads), min: Math.min(...coldLoads), max: Math.max(...coldLoads) },
    first_inference_ms: {
      median: median(firstInferences),
      min: Math.min(...firstInferences),
      max: Math.max(...firstInferences),
    },
    per_sentence_latency_ms: {
      p50: percentile(pooledLatencies, 50),
      p95: percentile(pooledLatencies, 95),
      n: pooledLatencies.length,
    },
  };
}

function startServer() {
  const server = http.createServer((req, res) => {
    try {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(SPIKE_ROOT, urlPath);
      const stat = fs.statSync(filePath);
      const ext = path.extname(filePath);
      res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream", "Content-Length": stat.size });
      fs.createReadStream(filePath).pipe(res);
    } catch (err) {
      res.writeHead(404);
      res.end(String(err));
    }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function withTimeout(promise, ms, onTimeoutValue) {
  let timer;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(onTimeoutValue), ms);
  });
  const result = await Promise.race([promise, timeout]);
  clearTimeout(timer);
  return result;
}

async function runOnce({ browser, baseUrl, cfg, networkKey, timeoutMs = 180_000 }) {
  const context = await browser.newContext(MOBILE_CONTEXT_OPTIONS);
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  const netParams = NETWORKS[networkKey];
  if (netParams) await cdp.send("Network.emulateNetworkConditions", netParams);
  await page.goto(`${baseUrl}/web/index.html`);
  await page.waitForFunction(() => window.__harnessReady === true);
  const evalPromise = page.evaluate((c) => window.runBenchmark(c), cfg);
  const outcome = await withTimeout(evalPromise, timeoutMs, { timed_out: true, timeout_ms: timeoutMs });
  await context.close();
  return outcome;
}

async function main() {
  const sentences = readSentences(100);
  const model = {
    key: "xenova-paraphrase-minilm-l3",
    hfRepoId: "Xenova/paraphrase-MiniLM-L3-v2",
    task: "feature-extraction",
    sizeBytes: {
      fp32: fileSizeBytes(MODELS_DIR, "xenova-paraphrase-minilm-l3", "onnx", "model.onnx"),
      q8: fileSizeBytes(MODELS_DIR, "xenova-paraphrase-minilm-l3", "onnx", "model_quantized.onnx"),
    },
  };

  const server = await startServer();
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;
  console.log(`Static server on ${baseUrl}`);

  const browser = await chromium.launch();
  console.log(`Chromium launched: ${browser.version()}`);

  const cfg = { modelId: model.key, task: model.task, dtype: "q8", source: "local", sentences };
  const out = { models: { [model.key]: { hfRepoId: model.hfRepoId, task: model.task, sizeBytes: model.sizeBytes, runs: { local: {}, remote: {} } } } };

  // mobile-fast3g needs a longer timeout than the other two conditions: the
  // ~22.5 MiB WASM runtime is fetched fresh every cold run on top of the
  // model (see RESULTS.md "WASM runtime is not free" and "A timeout that
  // needed correcting mid-run"). The first version of this script used 180s
  // uniformly and every fast3g rep timed out; fixed here so a fresh
  // reproduction does not need scripts/run_minilm_fast3g_fixup.mjs at all.
  const TIMEOUTS_MS = { "desktop-unthrottled": 60_000, "mobile-4g": 180_000, "mobile-fast3g": 300_000 };
  for (const networkKey of ["desktop-unthrottled", "mobile-4g", "mobile-fast3g"]) {
    const runs = [];
    for (let i = 0; i < 3; i++) {
      const r = await runOnce({ browser, baseUrl, cfg, networkKey, timeoutMs: TIMEOUTS_MS[networkKey] });
      runs.push(r);
      console.log(`  ${networkKey} rep ${i + 1}/3: cold_load_ms=${r.cold_load_ms?.toFixed(1) ?? "ERROR"}`);
    }
    out.models[model.key].runs.local[networkKey] = { raw: runs, summary: summarize(runs) };
  }

  // fp32 anchor on mobile-4g, 1 rep, matching the "tiny tier" treatment in the main run.
  const fp32Cfg = { ...cfg, dtype: "fp32" };
  const fp32Run = await runOnce({ browser, baseUrl, cfg: fp32Cfg, networkKey: "mobile-4g", timeoutMs: 180_000 });
  out.models[model.key].fp32_anchor = fp32Run;
  console.log(`  fp32 anchor (mobile-4g): cold_load_ms=${fp32Run.cold_load_ms?.toFixed(1)}`);

  // Real-world HF Hub direct load, 1 rep, no CDP throttle (matches main run's remote methodology).
  const remoteCfg = { ...cfg, modelId: model.hfRepoId, source: "remote" };
  const remoteRun = await runOnce({ browser, baseUrl, cfg: remoteCfg, networkKey: "desktop-unthrottled", timeoutMs: 120_000 });
  out.models[model.key].runs.remote["hf-hub-direct"] = { raw: [remoteRun], summary: summarize([remoteRun]) };
  console.log(`  HF Hub direct: cold_load_ms=${remoteRun.cold_load_ms?.toFixed(1) ?? "ERROR"}`);

  const chromiumVersion = browser.version();
  await browser.close();
  server.close();

  out.metadata_note =
    "Supplementary run, added after ckip-albert-tiny-ner was found unsupported. " +
    "Uses the same methodology, network condition values, and mobile context options as " +
    "results/s1_results.json's top-level metadata block (chromium " + chromiumVersion + "); see RESULTS.md.";

  fs.writeFileSync(path.join(RESULTS_DIR, "s1_results_extra.json"), JSON.stringify(out, null, 2));
  console.log("Wrote results/s1_results_extra.json");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
