// S1 spike: browser model size budget, measured with Playwright + transformers.js.
//
// Run with: node scripts/run_benchmark.mjs
// (from spikes/s1_browser_budget/; requires `npm install` and
// `npx playwright install chromium` first, see README.md)
//
// Serves this directory over a local static HTTP server (so the page can
// load /models/<name>/... the same way transformers.js would from any
// static host), drives headless Chromium through Playwright with CDP
// network-condition emulation, and writes results/s1_results.json.

import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

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

// CDP Network.emulateNetworkConditions parameters. Throughput is in
// bytes/sec (CDP), the task brief gives bits/sec, hence the /8. null means
// "do not call emulateNetworkConditions at all" (desktop-unthrottled).
const NETWORKS = {
  "desktop-unthrottled": null,
  "mobile-4g": {
    offline: false,
    downloadThroughput: (10_000_000 / 8), // 10 Mbps
    uploadThroughput: (5_000_000 / 8), // 5 Mbps
    latency: 40, // ms RTT
  },
  "mobile-fast3g": {
    offline: false,
    downloadThroughput: (1_600_000 / 8), // 1.6 Mbps
    uploadThroughput: (750_000 / 8), // 750 kbps
    latency: 150, // ms RTT
  },
};

// iPhone-shaped viewport per the task brief (390x844 @3x), rendered on the
// Chromium/WASM engine actually under test (not real WebKit/Safari -- see
// RESULTS.md Limitations). UA reports Chromium's real major version so the
// numbers are not attributed to an engine we did not run.
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

function startServer() {
  const server = http.createServer((req, res) => {
    try {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(SPIKE_ROOT, urlPath);
      if (!filePath.startsWith(SPIKE_ROOT)) {
        res.writeHead(403);
        res.end();
        return;
      }
      const stat = fs.statSync(filePath);
      if (stat.isDirectory()) {
        res.writeHead(404);
        res.end();
        return;
      }
      const ext = path.extname(filePath);
      res.writeHead(200, {
        "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
        "Content-Length": stat.size,
      });
      fs.createReadStream(filePath).pipe(res);
    } catch (err) {
      res.writeHead(404);
      res.end(String(err));
    }
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
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
  if (netParams) {
    await cdp.send("Network.emulateNetworkConditions", netParams);
  }

  await page.goto(`${baseUrl}/web/index.html`);
  await page.waitForFunction(() => window.__harnessReady === true);

  const evalPromise = page.evaluate((c) => window.runBenchmark(c), cfg);
  const outcome = await withTimeout(evalPromise, timeoutMs, {
    timed_out: true,
    timeout_ms: timeoutMs,
  });

  await context.close();
  return outcome;
}

function summarize(runs) {
  const okRuns = runs.filter((r) => !r.error && !r.timed_out);
  if (okRuns.length === 0) {
    return { ok_run_count: 0 };
  }
  const coldLoads = okRuns.map((r) => r.cold_load_ms);
  const firstInferences = okRuns.map((r) => r.first_inference_ms);
  const pooledLatencies = okRuns.flatMap((r) => r.latencies_ms);
  return {
    ok_run_count: okRuns.length,
    cold_load_ms: {
      median: median(coldLoads),
      min: Math.min(...coldLoads),
      max: Math.max(...coldLoads),
    },
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

async function main() {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const sentences = readSentences(100);
  console.log(`Loaded ${sentences.length} sentences from ${TESTSET_PATH}`);

  const MODELS = [
    {
      key: "ckip-albert-tiny-ner",
      hfRepoId: null,
      task: "token-classification",
      tier: "tiny",
      sizeBytes: {
        fp32: fileSizeBytes(MODELS_DIR, "ckip-albert-tiny-ner", "onnx", "model.onnx"),
        q8: fileSizeBytes(MODELS_DIR, "ckip-albert-tiny-ner", "onnx", "model_quantized.onnx"),
      },
    },
    {
      key: "ckip-bert-tiny-ner",
      hfRepoId: null,
      task: "token-classification",
      tier: "tiny",
      sizeBytes: {
        fp32: fileSizeBytes(MODELS_DIR, "ckip-bert-tiny-ner", "onnx", "model.onnx"),
        q8: fileSizeBytes(MODELS_DIR, "ckip-bert-tiny-ner", "onnx", "model_quantized.onnx"),
      },
    },
    {
      key: "xenova-bert-base-chinese",
      hfRepoId: "Xenova/bert-base-chinese",
      task: "feature-extraction",
      tier: "large",
      sizeBytes: {
        fp32: fileSizeBytes(MODELS_DIR, "xenova-bert-base-chinese", "onnx", "model.onnx"),
        q8: fileSizeBytes(MODELS_DIR, "xenova-bert-base-chinese", "onnx", "model_quantized.onnx"),
      },
    },
    {
      key: "xenova-mbert-ner-hrl",
      hfRepoId: "Xenova/bert-base-multilingual-cased-ner-hrl",
      task: "token-classification",
      tier: "large",
      sizeBytes: {
        fp32: fileSizeBytes(MODELS_DIR, "xenova-mbert-ner-hrl", "onnx", "model.onnx"),
        q8: fileSizeBytes(MODELS_DIR, "xenova-mbert-ner-hrl", "onnx", "model_quantized.onnx"),
      },
    },
  ];

  const server = await startServer();
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}`;
  console.log(`Static server on ${baseUrl}, root ${SPIKE_ROOT}`);

  const browser = await chromium.launch();
  console.log(`Chromium launched: ${browser.version()}`);

  const output = {
    models: {},
  };

  for (const model of MODELS) {
    console.log(`\n=== ${model.key} (task=${model.task}) ===`);
    output.models[model.key] = {
      hfRepoId: model.hfRepoId,
      task: model.task,
      sizeBytes: model.sizeBytes,
      runs: { local: {}, remote: {} },
      fp32_anchor: null,
      fp32_calculated: null,
    };

    // Phase 0: probe on desktop-unthrottled, q8. Also serves as rep 1/3 for
    // that condition. A failure here (e.g. an unsupported architecture)
    // marks the model unsupported and skips every later phase for it, but
    // the error itself is still recorded, never silently dropped.
    console.log(`  probe: desktop-unthrottled q8 local`);
    const probeCfg = {
      modelId: model.key,
      task: model.task,
      dtype: "q8",
      source: "local",
      sentences,
    };
    const probe = await runOnce({ browser, baseUrl, cfg: probeCfg, networkKey: "desktop-unthrottled" });
    if (probe.error) {
      console.log(`  UNSUPPORTED: ${probe.error.split("\n")[0]}`);
      output.models[model.key].unsupported = true;
      output.models[model.key].unsupported_error = probe.error;
      output.models[model.key].runs.local["desktop-unthrottled"] = { raw: [probe], summary: summarize([probe]) };
      continue;
    }
    console.log(`  probe ok: cold_load_ms=${probe.cold_load_ms.toFixed(1)}`);

    const desktopRuns = [probe];
    for (let i = 0; i < 2; i++) {
      const r = await runOnce({ browser, baseUrl, cfg: probeCfg, networkKey: "desktop-unthrottled" });
      desktopRuns.push(r);
      console.log(`  desktop-unthrottled rep ${i + 2}/3: cold_load_ms=${r.cold_load_ms?.toFixed(1)}`);
    }
    output.models[model.key].runs.local["desktop-unthrottled"] = {
      raw: desktopRuns,
      summary: summarize(desktopRuns),
    };

    // mobile-4g: 3 reps, all models.
    const mobile4gRuns = [];
    for (let i = 0; i < 3; i++) {
      const r = await runOnce({ browser, baseUrl, cfg: probeCfg, networkKey: "mobile-4g" });
      mobile4gRuns.push(r);
      console.log(`  mobile-4g rep ${i + 1}/3: cold_load_ms=${r.cold_load_ms?.toFixed(1)}`);
    }
    output.models[model.key].runs.local["mobile-4g"] = {
      raw: mobile4gRuns,
      summary: summarize(mobile4gRuns),
    };

    // mobile-fast3g: tiny tier gets 3 reps; large tier gets 1 rep capped at
    // 90s (theoretical time is 8-14 minutes; one confirmed-over-budget
    // sample is sufficient, see RESULTS.md Methodology for the reasoning).
    // The tiny-tier timeout must clear (WASM runtime + model) / throughput,
    // not just the model alone: the ~22.5 MiB WASM binary is fetched fresh
    // on every cold load (see RESULTS.md's "WASM runtime is not free"
    // finding), which pushed even the 11 MB ckip-bert-tiny-ner past a first
    // attempt at 180s. 300s clears (22.5 + ~12) MiB at 200 KB/s (~177s)
    // with headroom for per-request RTT overhead on 5 small tokenizer/config
    // files plus WASM compile time.
    const fast3gReps = model.tier === "tiny" ? 3 : 1;
    const fast3gTimeout = model.tier === "tiny" ? 300_000 : 90_000;
    const fast3gRuns = [];
    for (let i = 0; i < fast3gReps; i++) {
      const r = await runOnce({
        browser,
        baseUrl,
        cfg: probeCfg,
        networkKey: "mobile-fast3g",
        timeoutMs: fast3gTimeout,
      });
      fast3gRuns.push(r);
      const label = r.timed_out ? `TIMED OUT at ${r.timeout_ms}ms` : `cold_load_ms=${r.cold_load_ms?.toFixed(1)}`;
      console.log(`  mobile-fast3g rep ${i + 1}/${fast3gReps}: ${label}`);
    }
    output.models[model.key].runs.local["mobile-fast3g"] = {
      raw: fast3gRuns,
      summary: summarize(fast3gRuns),
      capped: model.tier !== "tiny",
    };

    // fp32 anchor: tiny tier only, 1 rep on mobile-4g. Large-tier fp32 is
    // not measured (see RESULTS.md); reported as a calculated estimate
    // below instead.
    if (model.tier === "tiny") {
      const fp32Cfg = { ...probeCfg, dtype: "fp32" };
      const r = await runOnce({ browser, baseUrl, cfg: fp32Cfg, networkKey: "mobile-4g" });
      output.models[model.key].fp32_anchor = r;
      console.log(`  fp32 anchor (mobile-4g): cold_load_ms=${r.cold_load_ms?.toFixed(1)}`);
    } else {
      const q8Summary = output.models[model.key].runs.local["mobile-4g"].summary;
      const q8Bytes = model.sizeBytes.q8;
      const fp32Bytes = model.sizeBytes.fp32;
      const observedMsPerByte = q8Summary.cold_load_ms.median / q8Bytes;
      output.models[model.key].fp32_calculated = {
        method: "observed q8 mobile-4g median cold_load_ms per byte, scaled to fp32 byte count",
        estimated_cold_load_ms: observedMsPerByte * fp32Bytes,
      };
      console.log(
        `  fp32 not measured (large tier); calculated estimate = ${(observedMsPerByte * fp32Bytes).toFixed(0)}ms`
      );
    }

    // Real-world HF Hub direct load: only for models that actually exist as
    // transformers.js-ready repos on the Hub (the two Xenova ones; the CKIP
    // exports are local-only, never uploaded).
    if (model.hfRepoId) {
      const remoteCfg = { ...probeCfg, modelId: model.hfRepoId, source: "remote" };
      const r = await runOnce({
        browser,
        baseUrl,
        cfg: remoteCfg,
        networkKey: "desktop-unthrottled",
        timeoutMs: 120_000,
      });
      output.models[model.key].runs.remote["hf-hub-direct"] = { raw: [r], summary: summarize([r]) };
      console.log(
        `  HF Hub direct (real network, no CDP throttle): cold_load_ms=${r.cold_load_ms?.toFixed(1) ?? "ERROR/" + r.timed_out}`
      );
    }
  }

  const chromiumVersion = browser.version();
  await browser.close();
  server.close();

  output.metadata = {
    generated_at_utc: new Date().toISOString(),
    hardware: "Apple M4, 16 GB RAM (macOS)",
    os: execSync("uname -a").toString().trim(),
    node_version: process.version,
    chromium_version: chromiumVersion,
    network_conditions: NETWORKS,
    mobile_context_options: MOBILE_CONTEXT_OPTIONS,
    sentence_count: sentences.length,
    testset_path: path.relative(SPIKE_ROOT, TESTSET_PATH),
  };

  const outPath = path.join(RESULTS_DIR, "s1_results.json");
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`\nWrote ${outPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
