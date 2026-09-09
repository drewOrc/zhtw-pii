// One-time merge, run after the main matrix, the supplementary
// paraphrase-MiniLM-L3 run, and the corrected ckip-bert-tiny-ner
// mobile-fast3g re-measurement (see RESULTS.md Methodology) all finished.
// Combines them into a single results/s1_results.json so the repo has one
// raw-data source of truth, per this spike's own README. Idempotent: rerun
// it and it produces the same merged file from the same three inputs.
//
// Run with: node scripts/merge_results.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SPIKE_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const RESULTS_DIR = path.join(SPIKE_ROOT, "results");

function load(name) {
  const p = path.join(RESULTS_DIR, name);
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf-8")) : null;
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

const main = load("s1_results.json");
if (!main) {
  console.error("results/s1_results.json not found; run scripts/run_benchmark.mjs first");
  process.exit(1);
}

const extra = load("s1_results_extra.json");
if (extra) {
  for (const [key, model] of Object.entries(extra.models)) {
    main.models[key] = model;
  }
  main.metadata.extra_run_note = extra.metadata_note;
  console.log(`Merged ${Object.keys(extra.models).length} model(s) from s1_results_extra.json`);
} else {
  console.log("No s1_results_extra.json found, skipping that merge");
}

function mergeFast3gFixup(fixupFilename, key) {
  const fixup = load(fixupFilename);
  if (!fixup) {
    console.log(`No ${fixupFilename} found, skipping that merge`);
    return;
  }
  const cell = main.models[key].runs.local["mobile-fast3g"];
  const originalRuns = cell.raw;
  const correctedRuns = fixup.models[key].runs.local["mobile-fast3g"].raw;
  const combinedRaw = [...originalRuns, ...correctedRuns];
  main.models[key].runs.local["mobile-fast3g"] = {
    raw: combinedRaw,
    summary: summarize(combinedRaw),
    capped: false,
    note:
      `First ${originalRuns.length} attempts used a timeout that undercounted the WASM ` +
      "runtime download (see RESULTS.md); they are kept in `raw` for an honest record but " +
      "excluded from `summary` since summarize() only aggregates non-timed-out/non-error runs. " +
      `The remaining ${correctedRuns.length} runs used the corrected 300s timeout and completed.`,
  };
  console.log(`Merged corrected ${key} mobile-fast3g re-measurement (${correctedRuns.length} runs)`);
}

mergeFast3gFixup("s1_results_bert_tiny_fast3g_fixup.json", "ckip-bert-tiny-ner");
mergeFast3gFixup("s1_results_minilm_fast3g_fixup.json", "xenova-paraphrase-minilm-l3");

fs.writeFileSync(path.join(RESULTS_DIR, "s1_results.json"), JSON.stringify(main, null, 2));
console.log("Wrote merged results/s1_results.json");
