const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const source = fs.readFileSync(appJsPath, 'utf8');

const match = source.match(
  /function syncCurrentRunIdFromStatus\(data, syncCurrentRun = true\) \{[\s\S]*?\n\}/
);

if (!match) {
  throw new Error('Could not locate syncCurrentRunIdFromStatus in app.js');
}

const context = {
  AppState: { currentRunId: 'live-run' },
};

vm.createContext(context);
vm.runInContext(`${match[0]}\nthis.syncCurrentRunIdFromStatus = syncCurrentRunIdFromStatus;`, context);

const syncCurrentRunIdFromStatus = context.syncCurrentRunIdFromStatus;

assert.equal(
  syncCurrentRunIdFromStatus({ run_id: 'history-run', is_running: false }, false),
  'live-run'
);

assert.equal(
  syncCurrentRunIdFromStatus({ run_id: 'live-run', is_running: true }, true),
  'live-run'
);

assert.equal(
  syncCurrentRunIdFromStatus({ run_id: 'finished-run', is_running: false }, true),
  null
);

console.log('frontend live run sync ok');
