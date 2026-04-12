const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const source = fs.readFileSync(appJsPath, 'utf8');

const match = source.match(
  /function summarizeRunForCompare\(data\) \{[\s\S]*?\r?\n\}\r?\n\r?\nfunction setDisplayedRun/
);

if (!match) {
  throw new Error('Could not locate summarizeRunForCompare in app.js');
}

const functionSource = match[0].replace(/\r?\n\r?\nfunction setDisplayedRun$/, '');

const context = {
  AppState: { currentProject: 'kemi' },
};

vm.createContext(context);
vm.runInContext(`${functionSource}\nthis.summarizeRunForCompare = summarizeRunForCompare;`, context);

const summarizeRunForCompare = context.summarizeRunForCompare;

function buildRun(metadata) {
  return {
    runId: 'run-1',
    projectId: 'kemi',
    mode: 'assisted',
    providerId: 'comfyui',
    request: {
      metadata,
      sceneSpec: {
        scene: {
          situation: 'coffee spill',
        },
      },
      prompts: [{ prompt: 'test prompt' }],
      outputTypes: ['thumb'],
    },
    results: [],
  };
}

const camelCaseSummary = summarizeRunForCompare(
  buildRun({
    retryFromRunId: 'parent-camel',
    retrySource: 'review-suggestion',
  })
);

assert.equal(camelCaseSummary.retry.isRetry, true);
assert.equal(camelCaseSummary.retry.fromRunId, 'parent-camel');
assert.equal(camelCaseSummary.retry.source, 'review-suggestion');

const snakeCaseSummary = summarizeRunForCompare(
  buildRun({
    retry_from_run_id: 'parent-snake',
    retry_source: 'manual',
  })
);

assert.equal(snakeCaseSummary.retry.isRetry, true);
assert.equal(snakeCaseSummary.retry.fromRunId, 'parent-snake');
assert.equal(snakeCaseSummary.retry.source, 'manual');

const rootSummary = summarizeRunForCompare(buildRun({}));
assert.equal(rootSummary.retry.isRetry, false);
assert.equal(rootSummary.retry.fromRunId, null);
assert.equal(rootSummary.retry.source, null);

console.log('frontend retry metadata normalization ok');
