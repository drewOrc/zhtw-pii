// Corrected re-measurement of xenova-paraphrase-minilm-l3 on mobile-fast3g.
// scripts/run_benchmark_extra.mjs used a uniform 180s timeout across all
// three network conditions; for this model that undercounts the WASM
// runtime download the same way it did for ckip-bert-tiny-ner in the main
// run (see RESULTS.md "A timeout that needed correcting mid-run"), and all
// 3 fast3g reps in that run came back as errors rather than real numbers.
// This script reruns just that one (model, network condition) cell with a
// 300s timeout. Writes results/s1_results_minilm_fast3g_fixup.json, merged
// into the final results/s1_results.json by scripts/merge_results.mjs.
//
// Run with: node scripts/run_minilm_fast3g_fixup.mjs

import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SPIKE_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
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

const FAST3G = { offline: false, downloadThroughput: 1_600_000 / 8, uploadThroughput: 750_000 / 8, latency: 150 };

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

async function main() {
  const sentences = readSentences(100);
  const server = await startServer();
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;
  console.log(`Static server on ${baseUrl}`);

  const browser = await chromium.launch();
  console.log(`Chromium launched: ${browser.version()}`);

  const cfg = {
    modelId: "xenova-paraphrase-minilm-l3",
    task: "feature-extraction",
    dtype: "q8",
    source: "local",
    sentences,
  };

  const runs = [];
  for (let i = 0; i < 3; i++) {
    const context = await browser.newContext(MOBILE_CONTEXT_OPTIONS);
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", FAST3G);
    await page.goto(`${baseUrl}/web/index.html`);
    await page.waitForFunction(() => window.__harnessReady === true);
    const evalPromise = page.evaluate((c) => window.runBenchmark(c), cfg);
    const r = await withTimeout(evalPromise, 300_000, { timed_out: true, timeout_ms: 300_000 });
    await context.close();
    runs.push(r);
    const label = r.timed_out ? `TIMED OUT at ${r.timeout_ms}ms` : `cold_load_ms=${r.cold_load_ms?.toFixed(1)}`;
    console.log(`  mobile-fast3g (corrected timeout) rep ${i + 1}/3: ${label}`);
  }

  await browser.close();
  server.close();

  const out = {
    models: {
      "xenova-paraphrase-minilm-l3": {
        runs: { local: { "mobile-fast3g": { raw: runs } } },
      },
    },
  };
  fs.writeFileSync(path.join(RESULTS_DIR, "s1_results_minilm_fast3g_fixup.json"), JSON.stringify(out, null, 2));
  console.log("Wrote results/s1_results_minilm_fast3g_fixup.json");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
