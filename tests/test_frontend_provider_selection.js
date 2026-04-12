const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const appJsPath = path.join(__dirname, '..', 'static', 'js', 'app.js');
const source = fs.readFileSync(appJsPath, 'utf8');

const match = source.match(
  /function selectProjectProvider\(project, options = \{\}\) \{[\s\S]*?\n\}/
);

if (!match) {
  throw new Error('Could not locate selectProjectProvider in app.js');
}

const saved = {};
const context = {
  AppState: {
    currentProviderId: 'api-image',
    providerStatuses: {
      'api-image': { configured: true, available: false },
      comfyui: { configured: true, available: true },
    },
  },
  loadStudioState() {
    return {
      providerSelections: {
        kemi: saved.kemi || 'api-image',
      },
    };
  },
  saveProviderSelection(projectId, providerId) {
    saved[projectId] = providerId;
  },
};

vm.createContext(context);
vm.runInContext(`${match[0]}\nthis.selectProjectProvider = selectProjectProvider;`, context);

const selectProjectProvider = context.selectProjectProvider;
const project = {
  id: 'kemi',
  provider: 'comfyui',
  supportedProviderInfo: [{ id: 'comfyui' }, { id: 'api-image' }],
};

const kept = selectProjectProvider(project, { persist: false, keepCurrent: true });
assert.equal(kept, 'api-image');
assert.equal(context.AppState.currentProviderId, 'api-image');
assert.equal(saved.kemi, undefined);

const resolved = selectProjectProvider(project);
assert.equal(resolved, 'comfyui');
assert.equal(saved.kemi, 'comfyui');

console.log('frontend provider selection persistence ok');
