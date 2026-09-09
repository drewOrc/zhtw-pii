// Tokenize the test set and adversarial set with transformers.js's AutoTokenizer,
// loading the *same* tokenizer.json bytes the Python side loads (see
// scripts/download_models.py). Dumps input_ids / content token strings to
// results/raw/node_<name>.json for scripts/compare_and_report.py to diff
// against the Python-side dump.
//
// transformers.js does not expose character offsets from either
// AutoTokenizer.from_pretrained() or the token-classification pipeline (see
// RESULTS.md "Offsets investigation" -- confirmed both empirically here and by
// reading node_modules/@huggingface/transformers/src/pipelines/token-classification.js,
// which has a literal `// TODO: Add support for start and end` on the object it
// returns). So this script only collects ids and token strings; span
// reconstruction happens as a separate step in Python
// (scripts/reconstruct_offsets.py) using these token strings.
//
// Usage:
//   npm install
//   node scripts/run_node_side.mjs

import { AutoTokenizer, env } from '@huggingface/transformers';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SPIKE_ROOT = join(__dirname, '..');
const REPO_ROOT = join(SPIKE_ROOT, '..', '..');
const RAW_DIR = join(SPIKE_ROOT, 'results', 'raw');

env.allowLocalModels = true;
env.allowRemoteModels = false;
env.useBrowserCache = false;
env.localModelPath = join(SPIKE_ROOT, 'models') + '/';

const TOKENIZER_NAMES = [
  'bert-base-chinese',
  'ckiplab-bert-tiny-chinese-ner',
  'bert-base-multilingual-cased',
  'distilbert-base-multilingual-cased',
  'xlm-roberta-base',
];

function readJsonl(path, source) {
  const text = readFileSync(path, 'utf-8');
  const rows = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    const row = JSON.parse(line);
    row.source = source;
    rows.push(row);
  }
  return rows;
}

function loadExamples() {
  const testRows = readJsonl(join(REPO_ROOT, 'data', 'testset', 'v0', 'test.jsonl'), 'test');
  const advRows = readJsonl(join(SPIKE_ROOT, 'data', 'adversarial.jsonl'), 'adversarial');
  return [...testRows, ...advRows];
}

async function main() {
  if (!existsSync(RAW_DIR)) mkdirSync(RAW_DIR, { recursive: true });
  const examples = loadExamples();
  console.log(`loaded ${examples.length} examples (test + adversarial)`);

  for (const name of TOKENIZER_NAMES) {
    const tokenizer = await AutoTokenizer.from_pretrained(name);
    const results = [];

    for (const ex of examples) {
      // encode(): plain number array, mirrors tokenizers.Tokenizer.encode(text).ids
      // in Python -- both apply the post_processor embedded in tokenizer.json, so
      // both include special tokens (e.g. [CLS]/[SEP]) by default.
      const inputIds = tokenizer.encode(ex.text);
      // tokenize(): content token strings, no special tokens (verified in the
      // API exploration this script's sibling investigation ran first).
      const contentTokens = tokenizer.tokenize(ex.text);

      results.push({
        id: ex.id,
        source: ex.source,
        tier: ex.tier,
        input_ids: inputIds,
        content_tokens: contentTokens,
        num_ids: inputIds.length,
      });
    }

    const outPath = join(RAW_DIR, `node_${name}.json`);
    writeFileSync(outPath, JSON.stringify(results));
    const maxIds = Math.max(...results.map((r) => r.num_ids));
    console.log(`${name}: max_ids=${maxIds} -> results/raw/node_${name}.json`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
