// --- Initialization ---
const AppState = {
    currentProject: 'kemi',
    availableProjects: [],
    availableProviders: [],
    providerStatuses: {},
    providerHealthFetchError: false,
    currentProviderId: null,
    currentOperatorMode: 'studio',
    currentPrompts: [],
    referenceAssets: [],
    referenceStatus: null,
    referencePolicy: {},
    selectedReferenceAssets: [],
    sceneTemplates: [],
    activeSceneTemplateId: null,
    currentRunId: null,
    displayedRunId: null,
    displayedRunSummary: null,
    lastPreflight: null,
    lastCodexHandoff: '',
    lastCodexHandoffPayload: null,
    currentRunCodexHandoff: null,
    currentRunCodexHandoffRequestKey: '',
    recentRuns: [],
    retrySuggestion: null,
    retryLineage: null,
    retryFocusRunId: null,
    retrySuggestionRequestKey: '',
    retryLineageRequestKey: '',
    pollIntervalId: null,
    outputsAdvancedVisible: false,
    referenceDefinitions: [],
    lastLogCount: 0,
    lastResultCount: 0,
    lastStatusData: null
};

const STUDIO_STATE_KEY = 'ai_generator_studio_state';
const SCENE_PLANNER_IDS = [
    CONFIG.DOM.SCENE_SITUATION,
    CONFIG.DOM.SCENE_INTERACTION,
    CONFIG.DOM.SCENE_BACKGROUND,
    CONFIG.DOM.SCENE_LOCATION,
    CONFIG.DOM.SCENE_LIGHTING
];

document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    initTabs();
    initEventListeners();
    initGalleryFilters();
    loadAppConfig();
    await loadProjects();
    // loadConfig removed — was dead code (function never existed)
    await checkProviderHealth();
    setInterval(checkProviderHealth, 30000);
    // 페이지 로드 시 기존 배치 상태 복구
    checkExistingBatch();
});

function initEventListeners() {
    // UI Buttons
    Utils.el(CONFIG.DOM.START_BTN)?.addEventListener('click', openConfirmModal);
    Utils.el(CONFIG.DOM.FAB_BTN)?.addEventListener('click', openConfirmModal);
    Utils.el('r2-upload-btn')?.addEventListener('click', uploadToR2);
    Utils.el('cancel-batch-btn')?.addEventListener('click', cancelBatch);
    Utils.el('welcome-go-prompts')?.addEventListener('click', () => {
        setActiveTab('compose');
    });
    Utils.el('welcome-go-references')?.addEventListener('click', () => {
        setActiveTab('compose');
    });
    Utils.el('toggle-style-config')?.addEventListener('click', toggleStyleConfig);
    Utils.el('clear-logs-btn')?.addEventListener('click', () => {
        Utils.el(CONFIG.DOM.LOGS).innerHTML = '';
        AppState.lastLogCount = 0;
    });
    Utils.el('open-help-btn')?.addEventListener('click', openHelpModal);
    Utils.el('clear-prompts-btn')?.addEventListener('click', clearPromptList);
    Utils.el('toggle-custom-form-btn')?.addEventListener('click', toggleCustomPromptForm);
    Utils.el('add-custom-prompt-btn')?.addEventListener('click', addCustomPrompt);
    Utils.el('download-template-btn')?.addEventListener('click', downloadTemplate);
    Utils.el(CONFIG.DOM.PROJECT_SELECTOR)?.addEventListener('change', (e) => switchProject(e.target.value));
    Utils.el(CONFIG.DOM.PROMPT_FILE_SELECTOR)?.addEventListener('change', (e) => loadPromptContent(e.target.value));
    Utils.el(CONFIG.DOM.REFERENCE_UPLOAD_BTN)?.addEventListener('click', uploadReferenceAsset);
    Utils.el(CONFIG.DOM.TEMPLATE_SAVE_BTN)?.addEventListener('click', saveSceneTemplate);
    Utils.el(CONFIG.DOM.TEMPLATE_APPLY_BTN)?.addEventListener('click', applySceneTemplate);
    Utils.el(CONFIG.DOM.TEMPLATE_CLEAR_BTN)?.addEventListener('click', clearSceneTemplateEditor);
    Utils.el(CONFIG.DOM.TEMPLATE_DELETE_BTN)?.addEventListener('click', deleteSceneTemplate);
    Utils.el(CONFIG.DOM.REFRESH_PREFLIGHT_BTN)?.addEventListener('click', refreshConfirmPreflight);
    Utils.el(CONFIG.DOM.OUTPUTS_ADVANCED_TOGGLE)?.addEventListener('click', toggleOutputsAdvanced);
    SCENE_PLANNER_IDS.forEach((id) => {
        Utils.el(id)?.addEventListener('input', async () => {
            saveScenePlannerState();
            updateGenerationModeNote();
            updateCodexHandoffPanel();
            await refreshConfirmPreflight();
        });
    });

    // Settings
    Utils.el('save-settings-btn')?.addEventListener('click', () => { saveAppConfig(); showToast('설정이 저장되었습니다', 'success'); });
    Utils.el('clear-all-data-btn')?.addEventListener('click', () => {
        Utils.el(CONFIG.DOM.LOGS).innerHTML = '';
        Utils.el(CONFIG.DOM.GALLERY).innerHTML = '';
        AppState.lastLogCount = 0;
        AppState.lastResultCount = 0;
    });

    // Modals
    Utils.el('cancel-confirm-btn')?.addEventListener('click', closeConfirmModal);
    Utils.el('start-now-btn')?.addEventListener('click', confirmStartBatch);
    Utils.el(CONFIG.DOM.GENERATION_MODE)?.addEventListener('change', async () => {
        updateOperatorModeAvailability();
        updateGenerationModeNote();
        updateCodexHandoffPanel();
        AppState.lastPreflight = null;
        await refreshConfirmPreflight();
    });
    Utils.el(CONFIG.DOM.PROVIDER_SELECTOR)?.addEventListener('change', async (e) => {
        handleProviderSelectionChange(e.target.value);
        updateCodexHandoffPanel();
        AppState.lastPreflight = null;
        await refreshConfirmPreflight();
    });
    Utils.el(CONFIG.DOM.OPERATOR_MODE)?.addEventListener('change', async (e) => {
        AppState.currentOperatorMode = e.target.value === 'codex-conversation' ? 'codex-conversation' : 'studio';
        saveOperatorMode(AppState.currentProject, AppState.currentOperatorMode);
        updateOperatorModeAvailability();
        updateGenerationModeNote();
        updateCodexHandoffPanel();
        AppState.lastPreflight = null;
        await refreshConfirmPreflight();
    });
    Utils.el(CONFIG.DOM.CODEX_HANDOFF_COPY_BTN)?.addEventListener('click', copyCodexHandoffPayload);
    Utils.el('close-help-btn')?.addEventListener('click', closeHelpModal);
    Utils.el('close-help-footer-btn')?.addEventListener('click', closeHelpModal);
    Utils.el('close-mapping-btn')?.addEventListener('click', () => Utils.el(CONFIG.MODALS.MAPPING).style.display = 'none');
    Utils.el('copy-mapping-btn')?.addEventListener('click', () => {
        const textarea = Utils.el('mapping-json');
        if (textarea) { navigator.clipboard.writeText(textarea.value); showToast('클립보드에 복사되었습니다', 'success'); }
    });
    Utils.el('close-detail-btn')?.addEventListener('click', closeImageDetail);
    Utils.el('btn-approve')?.addEventListener('click', () => reviewCurrentImage('approved'));
    Utils.el('btn-reject')?.addEventListener('click', () => reviewCurrentImage('rejected'));
    Utils.el('btn-save-note')?.addEventListener('click', saveCurrentReviewNote);

    // Inputs & Selects
    Utils.el('style-preset')?.addEventListener('change', applyPreset);
    Utils.el('steps')?.addEventListener('input', (e) => Utils.el('steps-val').innerText = e.target.value);
    Utils.el('toggle-all-checkbox')?.addEventListener('change', (e) => toggleAllPrompts(e.target));
    ['style-prompt', 'negative-prompt', 'default-ar', 'batch-count', 'steps', 'style-preset'].forEach((id) => {
        Utils.el(id)?.addEventListener('change', () => {
            updateCodexHandoffPanel();
            refreshConfirmPreflight();
        });
    });

    // Settings Auto-save
    const settings = Object.values(CONFIG.DOM.SETTINGS);
    settings.forEach(id => Utils.el(id)?.addEventListener('change', saveAppConfig));

    // Keyboard shortcuts for image detail modal
    document.addEventListener('keydown', (e) => {
        const modal = Utils.el('image-detail-modal');
        if (!modal || modal.style.display !== 'flex') return;
        if (e.key === 'Escape') closeImageDetail();
        if (e.key === 'a') reviewCurrentImage('approved');
        if (e.key === 'r') reviewCurrentImage('rejected');
        if (e.key === 'ArrowRight') navigateDetail(1);
        if (e.key === 'ArrowLeft') navigateDetail(-1);
    });
}

// --- Tab Management ---
function initTabs() {
    document.querySelector('.nav-menu')?.addEventListener('click', (e) => {
        const item = e.target.closest('.nav-item');
        if (item) {
            e.preventDefault();
            setActiveTab(item.dataset.tab);
        }
    });
}

function setActiveTab(tab) {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.nav-item[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById(`${tab}-tab`)?.classList.add('active');
    updateTopBarButtons(tab);
}

function updateTopBarButtons(tab) {
    const startBtn = Utils.el(CONFIG.DOM.START_BTN);
    const showStart = (tab === 'dashboard' || tab === 'compose');
    if (startBtn) startBtn.style.display = showStart ? '' : 'none';
}

function getCurrentProjectConfig() {
    return AppState.availableProjects.find((item) => item.id === AppState.currentProject) || null;
}

function getProjectProviderDescriptor(project, providerId) {
    if (!project) return null;
    const normalizedId = String(providerId || project.provider || '').trim().toLowerCase();
    return (project.supportedProviderInfo || []).find((item) => item.id === normalizedId)
        || (AppState.availableProviders || []).find((item) => item.id === normalizedId)
        || project.providerInfo
        || null;
}

function buildEffectiveCapabilities(project, providerInfo) {
    const providerCaps = providerInfo?.capabilities || {};
    const projectCaps = project?.capabilities || {};
    const effective = { ...providerCaps };
    if (Object.prototype.hasOwnProperty.call(effective, 'supportsReferenceAssets')) {
        effective.supportsReferenceAssets = Boolean(
            providerCaps.supportsReferenceAssets && projectCaps.supportsReferenceAssets
        );
    }
    return effective;
}

function getCurrentProviderId() {
    const project = getCurrentProjectConfig();
    return AppState.currentProviderId || project?.provider || 'comfyui';
}

function getOperatorMode() {
    const raw = Utils.val(CONFIG.DOM.OPERATOR_MODE) || AppState.currentOperatorMode || 'studio';
    return raw === 'codex-conversation' ? 'codex-conversation' : 'studio';
}

function getCurrentProviderInfo(project = getCurrentProjectConfig()) {
    return getProjectProviderDescriptor(project, getCurrentProviderId());
}

function getCurrentProviderStatus() {
    return AppState.providerStatuses?.[getCurrentProviderId()] || null;
}

function saveProviderSelection(projectId, providerId) {
    const savedState = loadStudioState();
    saveStudioState({
        providerSelections: {
            ...(savedState.providerSelections || {}),
            [projectId]: providerId
        }
    });
}

function saveOperatorMode(projectId, operatorMode) {
    const savedState = loadStudioState();
    saveStudioState({
        operatorModes: {
            ...(savedState.operatorModes || {}),
            [projectId]: operatorMode
        }
    });
}

function loadOperatorMode(project) {
    const savedState = loadStudioState();
    const savedMode = String(savedState.operatorModes?.[project?.id] || '').trim().toLowerCase();
    const nextMode = savedMode === 'codex-conversation' ? 'codex-conversation' : 'studio';
    AppState.currentOperatorMode = nextMode;
    Utils.setVal(CONFIG.DOM.OPERATOR_MODE, nextMode);
    saveOperatorMode(project?.id || AppState.currentProject, nextMode);
}

function selectProjectProvider(project, options = {}) {
    const { persist = true, keepCurrent = false } = options;
    if (!project) {
        AppState.currentProviderId = null;
        return null;
    }
    const savedState = loadStudioState();
    const supported = (project.supportedProviderInfo || []).map((item) => item.id);
    const current = String(AppState.currentProviderId || '').trim().toLowerCase();
    const preferred = String(savedState.providerSelections?.[project.id] || '').trim().toLowerCase();
    const defaultProvider = String(project.provider || supported[0] || 'comfyui').trim().toLowerCase();
    const available = supported.filter((providerId) => {
        const status = AppState.providerStatuses?.[providerId];
        return !status || (status.configured !== false && status.available !== false);
    });
    const nextProvider = (
        (keepCurrent && current && supported.includes(current) && current)
        || 
        (preferred && supported.includes(preferred) && (!AppState.providerStatuses?.[preferred] || available.includes(preferred)) && preferred)
        || (supported.includes(defaultProvider) && (!AppState.providerStatuses?.[defaultProvider] || available.includes(defaultProvider)) && defaultProvider)
        || available[0]
        || defaultProvider
        || supported[0]
        || 'comfyui'
    );
    AppState.currentProviderId = nextProvider;
    if (persist) {
        saveProviderSelection(project.id, nextProvider);
    }
    return nextProvider;
}

function renderProviderSelector(project = getCurrentProjectConfig()) {
    const select = Utils.el(CONFIG.DOM.PROVIDER_SELECTOR);
    const note = Utils.el(CONFIG.DOM.PROVIDER_NOTE);
    if (!select) return;

    const currentProviderId = getCurrentProviderId();
    const providers = project?.supportedProviderInfo || [];
    select.innerHTML = '';
    if (!providers.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '사용 가능한 렌더러 없음';
        select.appendChild(opt);
    }
    providers.forEach((provider) => {
        const opt = document.createElement('option');
        const status = AppState.providerStatuses?.[provider.id];
        const disabled = Boolean(status && (status.configured === false || status.available === false));
        opt.value = provider.id;
        opt.textContent = disabled ? `${provider.label} (사용 불가)` : provider.label;
        opt.disabled = disabled;
        if (provider.id === currentProviderId) opt.selected = true;
        select.appendChild(opt);
    });
    if (!select.value && providers[0]) {
        select.value = currentProviderId || providers[0].id;
    }

    if (note) {
        const providerInfo = getProjectProviderDescriptor(project, select.value || currentProviderId);
        const status = AppState.providerStatuses?.[providerInfo?.id || ''];
        note.classList.remove('is-warning', 'is-error');
        if (AppState.providerHealthFetchError) {
            note.textContent = '헬스 체크 요청이 실패해서 렌더러 상태를 확인할 수 없습니다.';
            note.classList.add('is-warning');
        } else if (status?.configured === false) {
            note.textContent = status.reason || '렌더 전에 렌더러 설정이 필요합니다.';
            note.classList.add('is-error');
        } else if (status && status.available === false) {
            note.textContent = status.reason || '현재 provider가 오프라인입니다.';
            note.classList.add('is-warning');
        } else {
            note.textContent = providerInfo?.description || '렌더 전에 렌더러 사용 가능 여부를 다시 확인합니다.';
        }
    }
}

function updateOperatorModeAvailability() {
    const select = Utils.el(CONFIG.DOM.OPERATOR_MODE);
    const note = Utils.el(CONFIG.DOM.OPERATOR_NOTE);
    if (!select) return;
    const generationMode = getGenerationMode();
    const codexOption = Array.from(select.options || []).find((option) => option.value === 'codex-conversation');
    if (codexOption) {
        codexOption.disabled = generationMode !== 'assisted';
    }
    if (generationMode !== 'assisted' && select.value === 'codex-conversation') {
        select.value = 'studio';
        AppState.currentOperatorMode = 'studio';
    }
    if (note) {
        note.classList.remove('is-warning');
        if (select.value === 'codex-conversation') {
            note.textContent = 'Codex 대화 연동은 현재 장면, 템플릿, 검수 상태를 채팅 작업과 맞춰 줍니다.';
        } else {
            note.textContent = 'Studio 운영은 생성 흐름을 앱 내부에서 바로 실행합니다.';
        }
        if (generationMode !== 'assisted') {
            note.textContent += ' Codex 대화 연동은 보조 렌더 모드에서만 사용할 수 있습니다.';
            note.classList.add('is-warning');
        }
    }
}

function getSelectedPromptsForGeneration() {
    const selectedIdxs = Array.from(document.querySelectorAll('.prompt-checkbox:checked'))
        .map((cb) => parseInt(cb.dataset.idx, 10))
        .filter((value) => !Number.isNaN(value));
    return AppState.currentPrompts.filter((_, i) => selectedIdxs.includes(i));
}

function buildCodexHandoffPayload(selectedPrompts = getSelectedPromptsForGeneration()) {
    const project = getCurrentProjectConfig();
    const providerInfo = getCurrentProviderInfo(project);
    const payload = buildGenerationPayload(selectedPrompts);
    const activeTemplate = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId) || null;
    const selectedReferences = AppState.selectedReferenceAssets.map((asset) => ({
        id: asset.id || asset.relativePath,
        relativePath: asset.relativePath,
        name: asset.name,
        slot: asset.slot,
        character: asset.character || ''
    }));
    return {
        handoffVersion: 1,
        intent: 'codex-conversation-image-generation',
        project: {
            id: AppState.currentProject,
            name: project?.name || AppState.currentProject,
            workflowMode: project?.workflowMode || 'prompt-first'
        },
        execution: {
            generationMode: payload.mode,
            operatorMode: payload.operator_mode,
            providerId: payload.provider_id,
            providerLabel: providerInfo?.label || payload.provider_id
        },
        template: activeTemplate ? {
            id: activeTemplate.id,
            name: activeTemplate.name,
            composition: activeTemplate.composition,
            description: activeTemplate.description
        } : null,
        sceneDraft: getScenePlannerState(),
        sceneSpec: payload.scene_spec,
        selectedPrompts: selectedPrompts.map((item) => ({
            desc_ko: item.desc_ko || '',
            prompt: item.prompt || '',
            aspect_ratio: item.aspect_ratio || ''
        })),
        selectedReferences,
        generationParams: {
            aspectRatio: payload.global_aspect_ratio,
            steps: payload.steps,
            batchCount: payload.batch_count,
            outputTypes: payload.types,
            stylePrompt: payload.style_prompt,
            negativePrompt: payload.negative_prompt
        },
        runContext: null,
        retryContext: null,
        preflight: AppState.lastPreflight?.summary || null,
        requestPreview: payload,
        codexAsk: payload.mode === 'assisted'
            ? '이 generation request를 사용하면 더 높은 일관성, 장면 선명도, 캐릭터 정확도로 다음 이미지를 만들거나 수정할 수 있습니다. 이 handoff는 요청 전용이며, 검수나 재시도 문맥이 중요하면 Outputs의 run handoff를 사용하세요.'
            : 'Use this direct generation state to refine prompts or propose a better assisted scene setup before rendering.'
    };
}

function buildCodexHandoffMessage(handoff) {
    const execution = handoff.execution || {};
    const template = handoff.template || null;
    const runContext = handoff.runContext || {};
    const retryContext = handoff.retryContext || {};
    const retrySuggestion = retryContext.suggestion || null;
    const retryLineage = retryContext.lineage || null;
    const promptCount = (handoff.selectedPrompts || []).length;
    const referenceCount = (handoff.selectedReferences || []).length;
    const outputTypes = (handoff.generationParams?.outputTypes || []).join(', ') || 'thumb, hero';
    const sceneCue = handoff.sceneDraft?.situation
        || handoff.sceneSpec?.scene?.situation
        || handoff.sceneSpec?.scene?.background
        || 'none';
    const reviewSummary = runContext.reviewSummary || null;
    const reviewNotes = runContext.reviewNotes || [];
    const reviewSummaryText = reviewSummary
        ? `A${reviewSummary.approved || 0} / R${reviewSummary.rejected || 0} / N${reviewSummary.noted || 0}`
        : '없음';
    const reviewNotesText = reviewNotes.length
        ? reviewNotes.map((item) => `${item.status}: ${item.note}`).join(' | ')
        : '없음';
    const retryPatchEntries = Object.entries(retrySuggestion?.sceneDraftPatch || {})
        .filter(([, value]) => value)
        .map(([key, value]) => `${key}=${value}`);
    const retryHintsText = (retrySuggestion?.promptHints || []).join(' | ') || '없음';
    const retryStyleText = (retrySuggestion?.stylePromptAdditions || []).join(' | ') || '없음';
    const retryNegativeText = (retrySuggestion?.negativePromptAdditions || []).join(' | ') || '없음';
    const retryLineageText = retryLineage
        ? `${retryLineage.runCount || 0}개 run, 최신 결과: ${retryLineage.latestOutcome || '없음'}`
        : '없음';
    const lines = [
        '아래 studio 상태를 기준 정보로 사용하세요.',
        `프로젝트: ${handoff.project?.name || handoff.project?.id || '알 수 없음'}`,
        `생성 모드: ${execution.generationMode === 'direct' ? '직접 렌더' : '보조 렌더'}`,
        `운영 방식: ${execution.operatorMode === 'codex-conversation' ? 'Codex 대화 연동' : 'Studio 운영'}`,
        `렌더러: ${execution.providerLabel || execution.providerId || '알 수 없는 렌더러'}`,
        `템플릿: ${template ? `${template.name} (${template.composition || '사용자 지정'})` : '선택 없음'}`,
        `장면 요약: ${sceneCue}`,
        `선택된 프롬프트: ${promptCount}`,
        `선택된 레퍼런스: ${referenceCount}`,
        `출력 타입: ${outputTypes}`,
        `Run 문맥: ${runContext.runId ? `${String(runContext.runId).slice(0, 8)} (${runContext.mode === 'direct' ? '직접 렌더' : '보조 렌더'})` : '없음'}`,
        `검수 요약: ${reviewSummaryText}`,
        `검수 메모: ${reviewNotesText}`,
        `재시도 제안: ${retrySuggestion?.summary || '없음'}`,
        `재시도 장면 패치: ${retryPatchEntries.join(' | ') || '없음'}`,
        `재시도 프롬프트 힌트: ${retryHintsText}`,
        `재시도 스타일 추가: ${retryStyleText}`,
        `재시도 네거티브 추가: ${retryNegativeText}`,
        `재시도 이력: ${retryLineageText}`,
        '',
        '작업 요청:',
        handoff.codexAsk || '이 상태를 기준으로 이미지 생성 결과를 만들거나 보정하세요.',
        '',
        '응답할 때 아래 JSON을 정확한 handoff payload로 사용하세요.',
        '',
        JSON.stringify(handoff, null, 2)
    ];
    return lines.join('\n');
}

function updateCodexHandoffPanel(selectedPrompts = getSelectedPromptsForGeneration()) {
    const panel = Utils.el(CONFIG.DOM.CODEX_HANDOFF_PANEL);
    const summary = Utils.el(CONFIG.DOM.CODEX_HANDOFF_SUMMARY);
    const textarea = Utils.el(CONFIG.DOM.CODEX_HANDOFF_TEXT);
    if (!panel || !summary || !textarea) return;

    if (getOperatorMode() !== 'codex-conversation') {
        panel.style.display = 'none';
        textarea.value = '';
        AppState.lastCodexHandoff = '';
        AppState.lastCodexHandoffPayload = null;
        return;
    }

    const handoff = buildCodexHandoffPayload(selectedPrompts);
    AppState.lastCodexHandoffPayload = handoff;
    AppState.lastCodexHandoff = buildCodexHandoffMessage(handoff);
    summary.textContent = `같은 프로젝트, 템플릿, 장면, 레퍼런스, 생성 설정을 Codex와 맞추려면 이 요청을 복사하세요. 검수나 재시도 문맥이 중요하면 Outputs의 Run Handoff를 사용하세요.`;
    textarea.value = AppState.lastCodexHandoff;
    panel.style.display = '';
}

async function copyCodexHandoffPayload() {
    if (!AppState.lastCodexHandoff) {
        updateCodexHandoffPanel();
    }
    if (!AppState.lastCodexHandoff) {
        showToast('복사할 Codex handoff가 없습니다', 'warning');
        return;
    }
    try {
        await navigator.clipboard.writeText(AppState.lastCodexHandoff);
        showToast('Codex handoff를 복사했습니다', 'success');
    } catch (e) {
        showToast(`Codex handoff 복사 실패: ${e.message}`, 'error');
    }
}

async function fetchRunCodexHandoff(runId) {
    if (!runId) {
        throw new Error('Codex handoff를 불러올 run이 없습니다');
    }
    const resp = await fetch(`${CONFIG.API.RUN_CODEX_HANDOFF}/${encodeURIComponent(runId)}/codex-handoff?project=${encodeURIComponent(AppState.currentProject)}`);
    const data = await resp.json();
    if (!resp.ok || data.detail) {
        throw new Error(data.detail || 'Run Codex handoff를 불러오지 못했습니다');
    }
    return data;
}

function buildRunHandoffRequestKey(projectId, runId) {
    return `${projectId || ''}:${runId || ''}:codex-handoff`;
}

async function loadRunCodexHandoff(runId, shouldRender = true) {
    if (!runId) {
        AppState.currentRunCodexHandoff = null;
        AppState.currentRunCodexHandoffRequestKey = '';
        if (shouldRender) renderRunCodexHandoffPreview();
        return;
    }
    const requestKey = buildRunHandoffRequestKey(AppState.currentProject, runId);
    AppState.currentRunCodexHandoffRequestKey = requestKey;
    AppState.currentRunCodexHandoff = null;
    if (shouldRender) renderRunCodexHandoffPreview();
    try {
        const handoff = await fetchRunCodexHandoff(runId);
        if (AppState.currentRunCodexHandoffRequestKey === requestKey) {
            AppState.currentRunCodexHandoff = handoff;
        }
    } catch (e) {
        console.error('Run Codex handoff 불러오기 실패', e);
        if (AppState.currentRunCodexHandoffRequestKey === requestKey) {
            AppState.currentRunCodexHandoff = null;
        }
    }
    if (shouldRender) renderRunCodexHandoffPreview();
}

async function copyFocusedRunCodexHandoff() {
    const runId = AppState.retryFocusRunId || AppState.displayedRunId || AppState.currentRunId || null;
    if (!runId) {
        showToast('Codex handoff를 복사할 run이 없습니다', 'warning');
        return;
    }
    try {
        const handoff = await fetchRunCodexHandoff(runId);
        AppState.lastCodexHandoffPayload = handoff.payload || null;
        AppState.lastCodexHandoff = handoff.message || '';
        AppState.currentRunCodexHandoff = handoff;
        AppState.currentRunCodexHandoffRequestKey = buildRunHandoffRequestKey(AppState.currentProject, runId);
        renderRunCodexHandoffPreview();
        await navigator.clipboard.writeText(AppState.lastCodexHandoff);
        showToast('Run용 Codex handoff를 복사했습니다', 'success');
    } catch (e) {
        showToast(`Run용 Codex handoff 복사 실패: ${e.message}`, 'error');
    }
}

function renderRunCodexHandoffPreview() {
    const container = Utils.el(CONFIG.DOM.RUN_CODEX_HANDOFF_PREVIEW);
    if (!container) return;

    const displayedSummary = AppState.displayedRunSummary
        || AppState.recentRuns.find((item) => item.runId === AppState.displayedRunId)
        || null;
    if (!displayedSummary || displayedSummary.mode !== 'assisted') {
        container.innerHTML = '';
        return;
    }

    const handoff = AppState.currentRunCodexHandoff;
    const displayedRunId = displayedSummary.runId || AppState.displayedRunId || null;
    const handoffRunId = handoff?.payload?.runContext?.runId || null;
    if (!handoff || !handoff.payload || (displayedRunId && handoffRunId && handoffRunId !== displayedRunId)) {
        container.innerHTML = `
            <div class="run-empty">
                선택한 assisted run의 Codex handoff 미리보기를 불러오는 중입니다.
            </div>
        `;
        return;
    }

    const payload = handoff.payload || {};
    const runContext = payload.runContext || {};
    const retrySuggestion = payload.retryContext?.suggestion || null;
    const retryLineage = payload.retryContext?.lineage || null;
    const reviewSummary = runContext.reviewSummary || {};
    const messagePreview = String(handoff.message || '').split('\n').slice(0, 18).join('\n');

    container.innerHTML = `
        <div class="run-handoff-header">
            <div>
                <strong>Codex handoff 미리보기</strong>
                <div class="run-handoff-sub">Run ${String(runContext.runId || '').slice(0, 8)} / ${payload.execution?.providerLabel || payload.execution?.providerId || '알 수 없는 렌더러'}</div>
            </div>
            <button class="btn btn-secondary" id="copy-run-codex-handoff-inline-btn">전체 handoff 복사</button>
        </div>
        <div class="run-handoff-grid">
            <div class="run-handoff-card">
                <label>검수 문맥</label>
                <div class="run-handoff-meta">A${reviewSummary.approved || 0} / R${reviewSummary.rejected || 0} / N${reviewSummary.noted || 0}</div>
                <div class="run-handoff-notes">
                    ${(runContext.reviewNotes || []).length
                        ? (runContext.reviewNotes || []).map((item) => `<div class="run-handoff-note"><strong>${escapeHtml(item.status)}</strong><span>${escapeHtml(item.note)}</span></div>`).join('')
                        : '<div class="run-empty">이 run에는 저장된 검수 메모가 없습니다.</div>'}
                </div>
            </div>
            <div class="run-handoff-card">
                <label>재시도 문맥</label>
                <div class="run-handoff-meta">${escapeHtml(retrySuggestion?.summary || '아직 재시도 제안 요약이 없습니다.')}</div>
                <div class="retry-chip-row">
                    ${(retrySuggestion?.promptHints || []).map((item) => `<span class="retry-chip">${escapeHtml(item)}</span>`).join('')}
                </div>
                <div class="run-handoff-meta">${retryLineage ? `재시도 이력에 ${retryLineage.runCount || 0}개 run` : '아직 재시도 이력이 없습니다.'}</div>
            </div>
        </div>
        <label class="run-handoff-label">메시지 미리보기</label>
        <textarea class="handoff-textarea run-handoff-textarea" readonly>${messagePreview}</textarea>
    `;
    Utils.el('copy-run-codex-handoff-inline-btn')?.addEventListener('click', copyFocusedRunCodexHandoff);
}

function updateProviderStatusChrome() {
    const project = getCurrentProjectConfig();
    const providerId = getCurrentProviderId();
    const providerInfo = getProjectProviderDescriptor(project, providerId) || { id: providerId, label: providerId };
    const status = AppState.providerStatuses?.[providerId] || null;
    const dot = Utils.el(CONFIG.DOM.PROVIDER_STATUS_DOT);
    const label = Utils.el(CONFIG.DOM.PROVIDER_STATUS_LABEL);
    const detail = Utils.el(CONFIG.DOM.PROVIDER_STATUS_DETAIL);
    const chip = Utils.el(CONFIG.DOM.ACTIVE_PROVIDER_CHIP);

    if (dot) {
        dot.classList.remove('green', 'red', 'amber');
        if (AppState.providerHealthFetchError) dot.classList.add('red');
        else if (status?.configured === false) dot.classList.add('amber');
        else if (status && status.available === false) dot.classList.add('red');
        else dot.classList.add('green');
    }

    if (label) {
        if (AppState.providerHealthFetchError) label.textContent = `${providerInfo.label} 상태 확인 불가`;
        else if (status?.configured === false) label.textContent = `${providerInfo.label} 설정 필요`;
        else if (status && status.available === false) label.textContent = `${providerInfo.label} 오프라인`;
        else label.textContent = `${providerInfo.label} 준비됨`;
    }

    if (detail) {
        detail.textContent = (AppState.providerHealthFetchError ? '헬스 체크 요청이 실패했습니다.' : '')
            || status?.reason
            || providerInfo.description
            || '렌더러 상태가 준비되었습니다.';
    }

    if (chip) {
        const statusText = AppState.providerHealthFetchError
            ? '상태 확인 불가'
            : status?.configured === false
                ? '설정 필요'
                : status && status.available === false
                    ? '오프라인'
                    : '준비됨';
        chip.textContent = `렌더러: ${providerInfo.label} - ${statusText}`;
    }
}

function handleProviderSelectionChange(providerId) {
    const project = getCurrentProjectConfig();
    if (!project || !providerId) return;
    AppState.currentProviderId = providerId;
    saveProviderSelection(project.id, providerId);
    updateProjectChrome(project);
    renderProviderSelector(project);
    updateProviderStatusChrome();
    updateGenerationModeNote();
}

function buildStatusUrl() {
    const params = new URLSearchParams();
    params.set('project', AppState.currentProject);
    if (AppState.currentRunId) params.set('run_id', AppState.currentRunId);
    return `${CONFIG.API.STATUS}?${params.toString()}`;
}

function getDisplayedRunId() {
    return AppState.displayedRunId || AppState.currentRunId || null;
}

function getReviewTargetRunId() {
    return getDisplayedRunId();
}

function buildRetryRequestKey(projectId, runId) {
    return `${projectId || ''}:${runId || ''}`;
}

function summarizeRunForCompare(data) {
    if (!data) return null;
    const request = data.request || {};
    const metadata = request.metadata || {};
    const sceneSpec = request.sceneSpec || {};
    const scene = sceneSpec.scene || {};
    const results = data.results || [];
    const retryFromRunId = String(metadata.retry_from_run_id || metadata.retryFromRunId || '').trim();
    const retrySource = String(metadata.retry_source || metadata.retrySource || '').trim();
    const approved = results.filter((item) => item.review_status === 'approved').length;
    const rejected = results.filter((item) => item.review_status === 'rejected').length;
    const noted = results.filter((item) => (item.review_note || '').trim()).length;
    const noteHighlights = [];
    for (const item of results) {
        const note = (item.review_note || '').trim();
        if (note && !noteHighlights.includes(note)) noteHighlights.push(note);
        if (noteHighlights.length >= 2) break;
    }
    return {
        runId: data.run_id || data.runId || null,
        projectId: data.project || data.projectId || AppState.currentProject,
        mode: data.mode || 'direct',
        providerId: data.provider_id || data.providerId || 'comfyui',
        operatorMode: request.operatorMode || 'studio',
        templateId: request.templateId || null,
        promptCount: (request.prompts || []).length,
        referenceCount: (data.reference_assets || data.referenceAssets || []).length,
        outputTypes: request.outputTypes || [],
        finishStatus: data.finish_status || data.finishStatus || null,
        isRunning: Boolean(data.is_running || data.isRunning),
        completed: data.completed || 0,
        total: data.total || 0,
        succeeded: data.succeeded || 0,
        createdAt: data.createdAt || null,
        updatedAt: data.updatedAt || null,
        sceneSummary: scene.situation || scene.background || '',
        retry: retryFromRunId ? {
            isRetry: true,
            fromRunId: retryFromRunId,
            source: retrySource || null
        } : { isRetry: false, fromRunId: null, source: null },
        reviewSummary: {
            approved,
            rejected,
            pending: results.filter((item) => (item.review_status || 'pending') === 'pending').length,
            noted,
            noteHighlights
        }
    };
}

function setDisplayedRun(recordOrStatus) {
    AppState.lastStatusData = recordOrStatus;
    AppState.displayedRunId = recordOrStatus?.run_id || recordOrStatus?.runId || null;
    AppState.displayedRunSummary = summarizeRunForCompare(recordOrStatus);
}

async function followLiveRun() {
    if (!AppState.currentRunId) {
        showToast('추적 중인 live run이 없습니다', 'warning');
        return;
    }
    try {
        const resp = await fetch(buildStatusUrl());
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || 'Live run을 불러오지 못했습니다');
        }
        resetRunViewState();
        updateUI(data, { syncCurrentRun: true, syncDisplayedRun: true });
        if ((data.mode || '').toLowerCase() === 'assisted' && data.run_id) {
            AppState.retryFocusRunId = data.run_id;
            await Promise.all([
                loadRunCodexHandoff(data.run_id, false),
                loadRetrySuggestion(data.run_id, false),
                loadRetryLineage(data.run_id, false)
            ]);
        } else {
            AppState.currentRunCodexHandoff = null;
            AppState.currentRunCodexHandoffRequestKey = '';
        }
        renderRunComparePanel();
        setActiveTab('outputs');
    } catch (e) {
        showToast(`Live run 불러오기 실패: ${e.message}`, 'error');
    }
}

// --- Provider Health Check ---
async function checkProviderHealth() {
    const previousProviderId = AppState.currentProviderId;
    try {
        const resp = await fetch(CONFIG.API.HEALTH);
        const data = await resp.json();
        AppState.providerStatuses = data.providers || {};
        AppState.providerHealthFetchError = false;
    } catch {
        AppState.providerStatuses = {};
        AppState.providerHealthFetchError = true;
    }
    const project = getCurrentProjectConfig();
    selectProjectProvider(project, { persist: false, keepCurrent: true });
    renderProviderSelector(project);
    updateProviderStatusChrome();
    const providerChanged = previousProviderId !== AppState.currentProviderId;
    if (providerChanged) {
        updateGenerationModeNote();
        AppState.lastPreflight = null;
    }
    await refreshConfirmPreflight();
}

// --- Check Existing Batch on Load ---
async function checkExistingBatch() {
    try {
        const resp = await fetch(buildStatusUrl());
        const data = await resp.json();
        const matchesCurrentProject = !data.project || data.project === AppState.currentProject;
        AppState.currentRunId = (matchesCurrentProject && data.is_running && data.run_id) ? data.run_id : null;
        if (matchesCurrentProject && (data.total > 0 || data.is_running || data.finish_status)) {
            updateUI(data, { syncCurrentRun: true });
            if (data.is_running) {
                setBusy(true);
                pollStatus();
            }
        }
    } catch (e) { /* server not ready yet */ }
}

// --- R2 Upload ---
async function uploadToR2() {
    const btn = Utils.el('r2-upload-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="spinner"></i> Uploading...'; }
    try {
        const resp = await fetch(`${CONFIG.API.UPLOAD_R2}?project=${encodeURIComponent(AppState.currentProject)}`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            showToast('업로드 실패: ' + data.error, 'error');
        } else {
            showToast(`업로드 완료! ${Object.keys(data.mappings || {}).length}개 파일`, 'success');
            const textarea = Utils.el('mapping-json');
            const modal = Utils.el(CONFIG.MODALS.MAPPING);
            if (textarea && modal) {
                textarea.value = JSON.stringify(data.mappings, null, 2);
                modal.style.display = 'flex';
            }
        }
    } catch (e) {
        showToast('업로드 실패: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i data-lucide="cloud-upload"></i> 클라우드 업로드'; }
        lucide.createIcons();
    }
}

// --- UI Helpers ---
function openHelpModal() { document.getElementById(CONFIG.MODALS.HELP).style.display = 'flex'; }
function closeHelpModal() { document.getElementById(CONFIG.MODALS.HELP).style.display = 'none'; }

function downloadTemplate() {
    const csvContent = "\uFEFFdesc_ko,prompt,aspect_ratio,seed,extra_positive,extra_negative\n예시_용,A majestic blue dragon,16:9,,highly detailed,watermark";
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "kemi_prompt_template.csv";
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    setTimeout(() => { document.body.removeChild(link); URL.revokeObjectURL(link.href); }, 100);
}

// --- Settings ---
function toggleTooltips(enabled) {
    if (enabled) document.body.classList.add('tooltips-enabled');
    else document.body.classList.remove('tooltips-enabled');
}

function playNotificationSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        if (ctx.state === 'suspended') ctx.resume();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, ctx.currentTime);
        osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.1, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.1, ctx.currentTime + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
        osc.start(); osc.stop(ctx.currentTime + 0.6);
    } catch (e) { }
}

function saveAppConfig() {
    const config = {
        showTooltips: Utils.isChecked(CONFIG.DOM.SETTINGS.TOOLTIPS),
        defaultSteps: Utils.val(CONFIG.DOM.SETTINGS.STEPS),
        defaultRepeat: Utils.val(CONFIG.DOM.SETTINGS.REPEAT),
        defaultAr: Utils.val(CONFIG.DOM.SETTINGS.AR),
        autoClear: Utils.isChecked(CONFIG.DOM.SETTINGS.AUTOCLEAR),
        taskSound: Utils.isChecked(CONFIG.DOM.SETTINGS.SOUND)
    };
    localStorage.setItem('kemi_config', JSON.stringify(config));
    toggleTooltips(config.showTooltips);
    const defAr = document.getElementById('default-ar');
    if (defAr && defAr.value !== config.defaultAr) defAr.value = config.defaultAr;
}

function loadAppConfig() {
    const saved = localStorage.getItem('kemi_config');
    if (saved) {
        try {
            const config = JSON.parse(saved);
            Utils.setVal(CONFIG.DOM.SETTINGS.TOOLTIPS, config.showTooltips);
            Utils.setVal(CONFIG.DOM.SETTINGS.STEPS, config.defaultSteps || CONFIG.DEFAULTS.STEPS);
            Utils.setVal(CONFIG.DOM.SETTINGS.REPEAT, config.defaultRepeat || CONFIG.DEFAULTS.REPEAT);
            Utils.setVal(CONFIG.DOM.SETTINGS.AR, config.defaultAr || CONFIG.DEFAULTS.AR);
            Utils.setVal(CONFIG.DOM.SETTINGS.AUTOCLEAR, config.autoClear);
            Utils.setVal(CONFIG.DOM.SETTINGS.SOUND, config.taskSound !== false);
            toggleTooltips(config.showTooltips);
            Utils.setVal('steps', config.defaultSteps || CONFIG.DEFAULTS.STEPS);
            const stepsVal = document.getElementById('steps-val');
            if (stepsVal) stepsVal.innerText = config.defaultSteps || CONFIG.DEFAULTS.STEPS;
            Utils.setVal('batch-count', config.defaultRepeat || CONFIG.DEFAULTS.REPEAT);
            Utils.setVal('default-ar', config.defaultAr || CONFIG.DEFAULTS.AR);
        } catch (e) { console.error("Config load failed", e); }
    } else {
        toggleTooltips(true);
    }
}

function loadStudioState() {
    try {
        return JSON.parse(localStorage.getItem(STUDIO_STATE_KEY) || '{}');
    } catch (e) {
        console.error('Studio state load failed', e);
        return {};
    }
}

function saveStudioState(patch = {}) {
    const prev = loadStudioState();
    const next = {
        currentProject: prev.currentProject || 'kemi',
        promptFiles: prev.promptFiles || {},
        selectedReferenceAssets: prev.selectedReferenceAssets || {},
        scenePlanner: prev.scenePlanner || {},
        providerSelections: prev.providerSelections || {},
        operatorModes: prev.operatorModes || {},
        ...patch
    };
    localStorage.setItem(STUDIO_STATE_KEY, JSON.stringify(next));
    return next;
}

function getScenePlannerState() {
    return {
        situation: Utils.val(CONFIG.DOM.SCENE_SITUATION).trim(),
        interaction: Utils.val(CONFIG.DOM.SCENE_INTERACTION).trim(),
        background: Utils.val(CONFIG.DOM.SCENE_BACKGROUND).trim(),
        location: Utils.val(CONFIG.DOM.SCENE_LOCATION).trim(),
        lighting: Utils.val(CONFIG.DOM.SCENE_LIGHTING).trim()
    };
}

function setScenePlannerState(state = {}) {
    Utils.setVal(CONFIG.DOM.SCENE_SITUATION, state.situation || '');
    Utils.setVal(CONFIG.DOM.SCENE_INTERACTION, state.interaction || '');
    Utils.setVal(CONFIG.DOM.SCENE_BACKGROUND, state.background || '');
    Utils.setVal(CONFIG.DOM.SCENE_LOCATION, state.location || '');
    Utils.setVal(CONFIG.DOM.SCENE_LIGHTING, state.lighting || '');
}

function saveScenePlannerState() {
    const savedState = loadStudioState();
    saveStudioState({
        scenePlanner: {
            ...(savedState.scenePlanner || {}),
            [AppState.currentProject]: getScenePlannerState()
        }
    });
}

function loadScenePlannerState() {
    const savedState = loadStudioState();
    const scenePlanner = savedState.scenePlanner?.[AppState.currentProject] || {};
    setScenePlannerState(scenePlanner);
}

async function loadProjects() {
    try {
        const resp = await fetch(CONFIG.API.PROJECTS);
        const data = await resp.json();
        const projects = data.projects || [];
        AppState.availableProviders = data.providers || [];
        AppState.availableProjects = projects;
        const savedState = loadStudioState();

        const select = Utils.el(CONFIG.DOM.PROJECT_SELECTOR);
        if (select) {
            select.innerHTML = '';
            projects.forEach((project) => {
                const opt = document.createElement('option');
                opt.value = project.id;
                opt.innerText = project.name || project.id;
                select.appendChild(opt);
            });
        }

        const hasMbti = projects.some((project) => project.id === 'mbti');
        const savedProject = savedState.currentProject;
        const currentProject = AppState.currentProject;

        let preferredProject = 'kemi';
        if (savedProject && projects.some((project) => project.id === savedProject) && savedProject !== 'kemi') {
            preferredProject = savedProject;
        } else if (currentProject && projects.some((project) => project.id === currentProject) && currentProject !== 'kemi') {
            preferredProject = currentProject;
        } else if (hasMbti) {
            preferredProject = 'mbti';
        } else if (projects.some((project) => project.id === savedProject)) {
            preferredProject = savedProject;
        } else if (projects.some((project) => project.id === currentProject)) {
            preferredProject = currentProject;
        } else {
            preferredProject = projects[0]?.id || 'kemi';
        }

        await switchProject(preferredProject, { updateSelect: true });
    } catch (e) {
        console.error("Failed to load projects", e);
        loadPromptFiles();
    }
}

function resetProjectWorkspace() {
    AppState.currentProviderId = null;
    AppState.currentOperatorMode = 'studio';
    AppState.currentPrompts = [];
    AppState.referenceAssets = [];
    AppState.referenceStatus = null;
    AppState.referencePolicy = {};
    AppState.selectedReferenceAssets = [];
    AppState.sceneTemplates = [];
    AppState.activeSceneTemplateId = null;
    AppState.currentRunId = null;
    AppState.displayedRunId = null;
    AppState.displayedRunSummary = null;
    AppState.lastPreflight = null;
    AppState.recentRuns = [];
    AppState.retrySuggestion = null;
    AppState.retryLineage = null;
    AppState.retryFocusRunId = null;
    AppState.retrySuggestionRequestKey = '';
    AppState.retryLineageRequestKey = '';
    AppState.referenceDefinitions = [];
    AppState.lastLogCount = 0;
    AppState.lastResultCount = 0;
    AppState.lastStatusData = null;
    if (AppState.pollIntervalId) {
        clearInterval(AppState.pollIntervalId);
        AppState.pollIntervalId = null;
    }
    setScenePlannerState({});

    renderPromptTable(AppState.currentPrompts);

    const logContainer = Utils.el(CONFIG.DOM.LOGS);
    if (logContainer) {
        logContainer.innerHTML = '';
    }

    const gallery = Utils.el(CONFIG.DOM.GALLERY);
    if (gallery) {
        gallery.innerHTML = '';
    }

    const previewEl = Utils.el(CONFIG.DOM.PREVIEW);
    if (previewEl) {
        previewEl.innerHTML = `
            <div class="preview-placeholder">
                <i data-lucide="camera"></i>
                <p>생성된 이미지가 여기에 표시됩니다</p>
            </div>
        `;
    }

    const welcomeEl = Utils.el('welcome-state');
    const batchEl = Utils.el('batch-state');
    if (welcomeEl) welcomeEl.style.display = '';
    if (batchEl) batchEl.style.display = 'none';

    const totalEl = Utils.el(CONFIG.DOM.TOTAL_TASKS);
    if (totalEl) totalEl.innerText = '0 / 0';
    const progEl = Utils.el(CONFIG.DOM.PROGRESS_TEXT);
    if (progEl) progEl.innerText = '0%';
    const barEl = Utils.el(CONFIG.DOM.PROGRESS_BAR);
    if (barEl) barEl.style.width = '0%';
    const statusEl = Utils.el(CONFIG.DOM.STATUS_TEXT);
    if (statusEl) statusEl.innerText = '대기 중';

    renderReferenceAssets();
    renderSceneTemplates();
    renderRunComparePanel();
    clearSceneTemplateEditor({ preserveSelection: false });
    updateGalleryCounts();
    lucide.createIcons();
}

function updateProjectChrome(project) {
    const label = project?.name || project?.id || 'AI Generator';
    const appTitle = Utils.el(CONFIG.DOM.APP_TITLE);
    const breadcrumb = Utils.el(CONFIG.DOM.PROJECT_BREADCRUMB);
    const capabilityNote = Utils.el(CONFIG.DOM.REFERENCE_CAPABILITY_NOTE);
    const welcomeBadge = Utils.el(CONFIG.DOM.WELCOME_PROJECT_BADGE);
    const welcomeTitle = Utils.el(CONFIG.DOM.WELCOME_TITLE);
    const welcomeDescription = Utils.el(CONFIG.DOM.WELCOME_DESCRIPTION);
    const welcomeChecklist = Utils.el(CONFIG.DOM.WELCOME_CHECKLIST);
    const welcomeReferenceBtn = Utils.el('welcome-go-references');
    const titleText = `${label} <span>Studio</span>`;
    const workflowMode = project?.workflowMode || 'prompt-first';
    const isReferenceProject = workflowMode === 'reference-first';
    const providerInfo = getProjectProviderDescriptor(project, AppState.currentProviderId || project?.provider);
    const effectiveCapabilities = buildEffectiveCapabilities(project, providerInfo);
    const providerLabel = providerInfo?.label || project?.provider || 'provider';
    const providerSupportsReferences = !!providerInfo?.capabilities?.supportsReferenceAssets;
    const supportsReferenceAssets = !!(effectiveCapabilities?.supportsReferenceAssets ?? project?.capabilities?.supportsReferenceAssets);

    if (appTitle) appTitle.innerHTML = titleText;
    if (breadcrumb) breadcrumb.innerHTML = titleText;
    document.title = `${label} Studio`;

    if (capabilityNote) {
        if (supportsReferenceAssets) {
            capabilityNote.textContent = `${providerLabel}는 선택된 레퍼런스를 렌더 과정에 직접 사용할 수 있습니다.`;
        } else if (!providerSupportsReferences) {
            capabilityNote.textContent = `${providerLabel}는 현재 이 adapter에서 직접 레퍼런스 conditioning을 지원하지 않습니다. 대신 레퍼런스는 장면 설계와 검수 기준에 반영됩니다.`;
        } else if (isReferenceProject) {
            capabilityNote.textContent = `${providerLabel}는 이 프로젝트를 planning-first 방식으로 처리합니다. 직접 주입되지 않아도 레퍼런스는 장면 구성과 검수에 반영됩니다.`;
        } else {
            capabilityNote.textContent = `${providerLabel}는 레퍼런스 라이브러리를 배치 구성에는 사용하지만, 이 워크플로우에서는 직접 conditioning이 아직 활성화되어 있지 않습니다.`;
        }
        capabilityNote.style.display = '';
    }

    if (welcomeBadge) {
        welcomeBadge.textContent = isReferenceProject ? `${label} Character Workflow` : `${label} Batch Workflow`;
    }

    if (welcomeTitle) {
        welcomeTitle.textContent = isReferenceProject ? '캐릭터 기준 장면을 준비하세요' : '이미지 생성을 시작하세요';
    }

    if (welcomeDescription) {
        welcomeDescription.textContent = isReferenceProject
            ? `${label} 프로젝트는 재사용 가능한 캐릭터 레퍼런스에서 시작합니다. Compose에서 장면을 정리한 뒤 ${providerLabel}로 렌더하세요.`
            : `Compose에서 프롬프트, 템플릿, 레퍼런스를 정리하고 ${providerLabel} 설정을 확인한 뒤 실행하세요.`;
    }

    if (welcomeChecklist) {
        welcomeChecklist.innerHTML = isReferenceProject
            ? `
                <div class="welcome-check-item">1. 프로젝트 레퍼런스 라이브러리를 확인하세요</div>
                <div class="welcome-check-item">2. Compose에서 레퍼런스, 템플릿, 장면 메모를 정리하세요</div>
                <div class="welcome-check-item">3. 실행 설정을 확인한 뒤 필요한 자산만 시작하세요</div>
            `
            : `
                <div class="welcome-check-item">1. 프로젝트를 선택하세요</div>
                <div class="welcome-check-item">2. Compose에서 장면을 구성하세요</div>
                <div class="welcome-check-item">3. 실행 설정을 확인하고 시작하세요</div>
            `;
    }

    if (welcomeReferenceBtn) {
        welcomeReferenceBtn.style.display = isReferenceProject ? '' : 'none';
    }

    const referenceNav = document.querySelector('.nav-item[data-tab="references"]');
    if (referenceNav) {
        referenceNav.style.display = 'none';
    }

    const referencesTab = Utils.el('references-tab');
    if (referencesTab) {
        referencesTab.style.display = 'none';
    }

    updateProviderStatusChrome();
    updateComposeSelectionSummary();
}

async function switchProject(projectId, options = {}) {
    const { updateSelect = false } = options;
    AppState.currentProject = projectId || 'kemi';
    saveStudioState({ currentProject: AppState.currentProject });
    resetProjectWorkspace();

    if (updateSelect) {
        const select = Utils.el(CONFIG.DOM.PROJECT_SELECTOR);
        if (select) select.value = AppState.currentProject;
    }

    const project = AppState.availableProjects.find((item) => item.id === AppState.currentProject);
    selectProjectProvider(project);
    loadOperatorMode(project);
    renderProviderSelector(project);
    updateOperatorModeAvailability();
    updateProjectChrome(project);
    setActiveTab('compose');

    const styleInput = Utils.el('style-prompt');
    if (styleInput) styleInput.value = project?.generation?.style || '';

    if (project?.generation?.aspectRatio) {
        const arSelect = Utils.el('default-ar');
        if (arSelect) arSelect.value = project.generation.aspectRatio;
    }

    loadScenePlannerState();

    await loadPromptFiles();
    await loadReferenceAssets();
    await loadSceneTemplates();
    await loadRecentRuns();
    await checkExistingBatch();
}

// --- Prompt Management ---
async function loadPromptFiles() {
    try {
        const resp = await fetch(`${CONFIG.API.PROMPT_FILES}?project=${encodeURIComponent(AppState.currentProject)}`);
        const data = await resp.json();
        const select = document.getElementById(CONFIG.DOM.PROMPT_FILE_SELECTOR);
        if (!select || !data.files) return;
        const savedState = loadStudioState();
        const preferredFile = savedState.promptFiles?.[AppState.currentProject];
        select.innerHTML = '';
        data.files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f; opt.innerText = f;
            if (f === preferredFile || (!preferredFile && f === data.defaultFile) || (!preferredFile && !data.defaultFile && f === 'thumbnail-prompts.csv')) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
        if (select.value) {
            await loadPromptContent(select.value);
        } else {
            renderPromptTable([]);
        }
    } catch (e) { console.error("Failed to load files", e); }
}

async function loadPromptContent(filename) {
    try {
        const resp = await fetch(`${CONFIG.API.PROMPT_CONTENT}?project=${encodeURIComponent(AppState.currentProject)}&filename=${encodeURIComponent(filename)}`);
        const data = await resp.json();
        if (data.prompts) {
            const savedState = loadStudioState();
            saveStudioState({
                currentProject: AppState.currentProject,
                promptFiles: {
                    ...(savedState.promptFiles || {}),
                    [AppState.currentProject]: filename
                }
            });
            AppState.currentPrompts = data.prompts;
            renderPromptTable(AppState.currentPrompts);
        }
    } catch (e) { console.error("Failed to load content", e); }
}

async function loadReferenceAssets() {
    try {
        const resp = await fetch(`${CONFIG.API.REFERENCE_ASSETS}?project=${encodeURIComponent(AppState.currentProject)}`);
        const data = await resp.json();
        AppState.referenceAssets = data.assets || [];
        AppState.referenceStatus = data.status || null;
        AppState.referencePolicy = data.referencePolicy || {};
        AppState.referenceDefinitions = data.definitionFiles || [];

        const rootEl = Utils.el(CONFIG.DOM.REFERENCE_ROOT);
        if (rootEl) rootEl.textContent = data.rootDir || '';
        const libraryCountEl = Utils.el(CONFIG.DOM.REFERENCE_LIBRARY_COUNT);
        if (libraryCountEl) libraryCountEl.textContent = `${data.status?.libraryAssets || 0}`;
        const tempCountEl = Utils.el(CONFIG.DOM.REFERENCE_TEMP_COUNT);
        if (tempCountEl) tempCountEl.textContent = `${data.status?.temporaryAssets || 0}`;

        const savedState = loadStudioState();
        const selectedPaths = new Set(savedState.selectedReferenceAssets?.[AppState.currentProject] || []);
        AppState.selectedReferenceAssets = AppState.referenceAssets.filter((asset) => selectedPaths.has(asset.relativePath));
        renderReferenceAssets();
    } catch (e) {
        console.error('Failed to load reference assets', e);
        AppState.referenceAssets = [];
        AppState.referenceStatus = null;
        AppState.referencePolicy = {};
        AppState.selectedReferenceAssets = [];
        AppState.referenceDefinitions = [];
        renderReferenceAssets();
    }
}

function getSceneTemplateCompositionLabel(value) {
    const labels = {
        single: '1인',
        duo: '2인',
        group: '그룹',
        custom: '사용자 지정'
    };
    return labels[value] || value || '사용자 지정';
}

function summarizeTemplateAssets(template) {
    const assets = template?.referenceAssetPaths || [];
    if (!assets.length) return '저장된 레퍼런스 자산 없음';
    const names = assets
        .map((path) => path.split('/').pop() || path)
        .slice(0, 3)
        .join(', ');
    const remaining = assets.length > 3 ? ` +${assets.length - 3}` : '';
    return `${names}${remaining}`;
}

function summarizeTemplateSceneDraft(template) {
    const draft = template?.sceneDraft || template?.meta?.sceneDraft || {};
    const parts = [
        draft.situation,
        draft.interaction,
        draft.background,
        draft.location
    ].filter(Boolean);
    return parts.length ? parts.slice(0, 2).join(' | ') : 'No scene planner draft';
}

function getSceneTemplateEditorState() {
    return {
        id: AppState.activeSceneTemplateId,
        name: Utils.val(CONFIG.DOM.TEMPLATE_NAME).trim(),
        composition: Utils.val(CONFIG.DOM.TEMPLATE_COMPOSITION) || 'single',
        description: Utils.val(CONFIG.DOM.TEMPLATE_DESCRIPTION).trim(),
        reference_asset_paths: AppState.selectedReferenceAssets.map((asset) => asset.relativePath),
        style_prompt: Utils.val('style-prompt'),
        negative_prompt: Utils.val('negative-prompt'),
        global_aspect_ratio: Utils.val('default-ar') || CONFIG.DEFAULTS.AR,
        batch_count: parseInt(Utils.val('batch-count'), 10) || CONFIG.DEFAULTS.REPEAT,
        steps: parseInt(Utils.val('steps'), 10) || CONFIG.DEFAULTS.STEPS,
        types: ['thumb', 'hero'],
        scene_draft: getScenePlannerState(),
        meta: {
            projectName: AppState.availableProjects.find((item) => item.id === AppState.currentProject)?.name || AppState.currentProject
        }
    };
}

function fillSceneTemplateEditor(template = null) {
    Utils.setVal(CONFIG.DOM.TEMPLATE_NAME, template?.name || '');
    Utils.setVal(CONFIG.DOM.TEMPLATE_COMPOSITION, template?.composition || 'single');
    Utils.setVal(CONFIG.DOM.TEMPLATE_DESCRIPTION, template?.description || '');
}

function clearSceneTemplateEditor(options = {}) {
    const { preserveSelection = false } = options;
    AppState.activeSceneTemplateId = null;
    fillSceneTemplateEditor(null);
    renderSceneTemplates();
    if (!preserveSelection) {
        lucide.createIcons();
    }
}

async function loadSceneTemplates() {
    try {
        const resp = await fetch(`${CONFIG.API.TEMPLATES}?project=${encodeURIComponent(AppState.currentProject)}`);
        const data = await resp.json();
        AppState.sceneTemplates = data.templates || [];
    } catch (e) {
        console.error('Failed to load scene templates', e);
        AppState.sceneTemplates = [];
    }
    if (AppState.activeSceneTemplateId && !AppState.sceneTemplates.some((item) => item.id === AppState.activeSceneTemplateId)) {
        AppState.activeSceneTemplateId = null;
    }
    renderSceneTemplates();
}

async function loadRecentRuns() {
    try {
        const resp = await fetch(`${CONFIG.API.RUNS}?project=${encodeURIComponent(AppState.currentProject)}&limit=12`);
        const data = await resp.json();
        AppState.recentRuns = data.runs || [];
    } catch (e) {
        console.error('Failed to load recent runs', e);
        AppState.recentRuns = [];
    }
    const displayedSummary = AppState.displayedRunSummary;
    const displayedRun = AppState.recentRuns.find((item) => item.runId === AppState.displayedRunId)
        || (displayedSummary && displayedSummary.projectId === AppState.currentProject ? displayedSummary : null);
    const assistedRun = displayedRun
        ? (displayedRun.mode === 'assisted' ? displayedRun : null)
        : AppState.recentRuns.find((item) => item.mode === 'assisted');
    if (assistedRun?.runId) {
        AppState.retryFocusRunId = assistedRun.runId;
        await Promise.all([
            loadRunCodexHandoff(assistedRun.runId, false),
            loadRetrySuggestion(assistedRun.runId, false),
            loadRetryLineage(assistedRun.runId, false)
        ]);
    } else {
        AppState.retrySuggestion = null;
        AppState.retryLineage = null;
        AppState.retryFocusRunId = null;
        AppState.currentRunCodexHandoff = null;
        AppState.currentRunCodexHandoffRequestKey = '';
    }
    renderRunComparePanel();
}

async function loadRetrySuggestion(runId, shouldRender = true) {
    if (!runId) {
        AppState.retrySuggestion = null;
        if (shouldRender) renderRunComparePanel();
        return;
    }
    const requestKey = buildRetryRequestKey(AppState.currentProject, runId);
    AppState.retrySuggestionRequestKey = requestKey;
    try {
        const resp = await fetch(`${CONFIG.API.RUNS}/${encodeURIComponent(runId)}/retry-suggestion?project=${encodeURIComponent(AppState.currentProject)}`);
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || 'Failed to load retry suggestion');
        }
        if (AppState.retrySuggestionRequestKey === requestKey) {
            AppState.retrySuggestion = data;
        }
    } catch (e) {
        console.error('Failed to load retry suggestion', e);
        if (AppState.retrySuggestionRequestKey === requestKey) {
            AppState.retrySuggestion = null;
        }
    }
    if (shouldRender) renderRunComparePanel();
}

async function loadRetryLineage(runId, shouldRender = true) {
    if (!runId) {
        AppState.retryLineage = null;
        if (shouldRender) renderRunComparePanel();
        return;
    }
    const requestKey = buildRetryRequestKey(AppState.currentProject, runId);
    AppState.retryLineageRequestKey = requestKey;
    try {
        const resp = await fetch(`${CONFIG.API.RUNS}/${encodeURIComponent(runId)}/lineage?project=${encodeURIComponent(AppState.currentProject)}`);
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || 'Failed to load retry lineage');
        }
        if (AppState.retryLineageRequestKey === requestKey) {
            AppState.retryLineage = data;
        }
    } catch (e) {
        console.error('Failed to load retry lineage', e);
        if (AppState.retryLineageRequestKey === requestKey) {
            AppState.retryLineage = null;
        }
    }
    if (shouldRender) renderRunComparePanel();
}

function formatRunTimestamp(value) {
    if (!value) return '시간 정보 없음';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
}

function formatFinishStatus(value) {
    const map = {
        ready: '준비됨',
        running: '실행 중',
        completed: '완료',
        failed: '실패',
        cancelled: '취소됨',
        unknown: '상태 미상'
    };
    return map[value] || value || '상태 미상';
}

function getCompareRunBuckets() {
    const displayedRun = AppState.recentRuns.find((item) => item.runId === AppState.displayedRunId)
        || AppState.displayedRunSummary;
    let direct = AppState.recentRuns.find((item) => item.mode === 'direct') || null;
    let assisted = AppState.recentRuns.find((item) => item.mode === 'assisted') || null;
    if (displayedRun?.mode === 'direct') {
        direct = displayedRun;
    } else if (displayedRun?.mode === 'assisted') {
        assisted = displayedRun;
    }
    return [
        { key: 'direct', title: '직접 렌더 Run', run: direct },
        { key: 'assisted', title: '보조 렌더 Run', run: assisted }
    ];
}

function normalizeCompareValue(value) {
    if (Array.isArray(value)) {
        return value.join(', ') || '-';
    }
    if (value === null || value === undefined || value === '') {
        return '-';
    }
    return String(value);
}

function compareRunField(directRun, assistedRun, label, getValue) {
    const directValue = normalizeCompareValue(getValue(directRun));
    const assistedValue = normalizeCompareValue(getValue(assistedRun));
    return {
        label,
        directValue,
        assistedValue,
        same: directValue === assistedValue
    };
}

function buildRunDiffItems(directRun, assistedRun) {
    return [
        compareRunField(directRun, assistedRun, 'Provider', (run) => run.providerId),
        compareRunField(directRun, assistedRun, '운영 방식', (run) => run.operatorMode || 'studio'),
        compareRunField(directRun, assistedRun, '템플릿', (run) => run.templateId || '없음'),
        compareRunField(directRun, assistedRun, '재시도 시작점', (run) => run.retry?.fromRunId || 'root'),
        compareRunField(directRun, assistedRun, '장면', (run) => run.sceneSummary || ''),
        compareRunField(directRun, assistedRun, '레퍼런스', (run) => run.referenceCount || 0),
        compareRunField(directRun, assistedRun, '프롬프트', (run) => run.promptCount || 0),
        compareRunField(directRun, assistedRun, '출력 타입', (run) => run.outputTypes || []),
        compareRunField(directRun, assistedRun, '상태', (run) => run.isRunning ? '실행 중' : (run.finishStatus || 'unknown')),
        compareRunField(directRun, assistedRun, '성공', (run) => `${run.succeeded || 0}/${run.total || 0}`),
        compareRunField(directRun, assistedRun, '검수 범위', (run) => {
            const review = run.reviewSummary || {};
            return `A${review.approved || 0} / R${review.rejected || 0} / N${review.noted || 0}`;
        }),
        compareRunField(directRun, assistedRun, '검수 메모', (run) => {
            const highlights = run.reviewSummary?.noteHighlights || [];
            return highlights.length ? highlights.join(' | ') : '';
        })
    ];
}

function renderRunDiffSummary(directRun, assistedRun) {
    const container = Utils.el(CONFIG.DOM.RUN_COMPARE_DIFF);
    if (!container) return;

    if (!directRun || !assistedRun) {
        container.innerHTML = `
            <div class="run-empty">
                최근 직접 렌더 Run과 보조 렌더 Run이 모두 있을 때 비교 화면이 나타납니다.
            </div>
        `;
        return;
    }

    const diffItems = buildRunDiffItems(directRun, assistedRun);
    const sameCount = diffItems.filter((item) => item.same).length;
    const diffCount = diffItems.length - sameCount;

    container.innerHTML = `
        <div class="run-diff-header">
            <strong>직접 렌더 vs 보조 렌더 비교</strong>
            <span class="run-diff-sub">${sameCount}개 동일 / ${diffCount}개 차이</span>
        </div>
        <div class="run-diff-grid">
            ${diffItems.map((item) => `
                <div class="run-diff-item">
                    <div class="run-diff-label-row">
                        <span class="run-diff-label">${item.label}</span>
                        <span class="run-diff-state ${item.same ? 'same' : 'diff'}">${item.same ? '동일' : '차이'}</span>
                    </div>
                    <div class="run-diff-values">
                        <div class="run-diff-value">
                            <span class="run-diff-mode">직접 렌더</span>
                            <span>${item.directValue}</span>
                        </div>
                        <div class="run-diff-value">
                            <span class="run-diff-mode">보조 렌더</span>
                            <span>${item.assistedValue}</span>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function getRetryOutcomeTone(label) {
    if (label === 'improved') return 'improved';
    if (label === 'worse') return 'worse';
    return 'unchanged';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderRetryLineagePanel() {
    const container = Utils.el(CONFIG.DOM.RUN_RETRY_LINEAGE);
    if (!container) return;

    const lineage = AppState.retryLineage;
    if (!lineage || !(lineage.items || []).length) {
        container.innerHTML = `
            <div class="run-empty">
                검수 제안으로 assisted run을 다시 돌리면 재시도 이력이 여기에 나타납니다.
            </div>
        `;
        return;
    }

    const items = lineage.items || [];
    const currentItem = items.find((item) => item.isCurrent) || items[items.length - 1];
    const summaryText = lineage.hasRetries
        ? `이 재시도 체인에는 ${items.length}개 run이 있습니다. 현재 기준 run: ${String(lineage.currentRunId || '').slice(0, 8)}`
        : '이 assisted run에는 아직 재시도 체인이 없습니다.';

    container.innerHTML = `
        <div class="retry-lineage-header">
            <div>
                <strong>재시도 이력</strong>
                <div class="retry-lineage-summary">${summaryText}</div>
            </div>
            <div class="run-compare-sub">${currentItem?.sceneSummary || '장면 요약 없음'}</div>
        </div>
        <div class="retry-lineage-list">
            ${items.map((item) => {
                const review = item.reviewSummary || {};
                const comparison = item.comparisonToParent || null;
                const changes = item.changesFromParent || null;
                const retry = item.retry || {};
                const outcomeTone = getRetryOutcomeTone(comparison?.label);
                const depthClass = `depth-${Math.min(item.depth || 0, 4)}`;
                const noteText = (review.noteHighlights || []).join(' | ') || '검수 메모 없음';
                const retryMeta = retry.fromRunId
                    ? `Run ${String(retry.fromRunId).slice(0, 8)} 에서 재시도${retry.source ? ` / ${retry.source}` : ''}`
                    : '루트 run';
                return `
                    <div class="retry-lineage-item ${depthClass} ${item.isCurrent ? 'current' : ''}">
                        <div class="retry-lineage-top">
                            <div class="retry-lineage-title">
                                <strong>${item.isCurrent ? '현재 Run' : `Run ${String(item.runId || '').slice(0, 8)}`}</strong>
                                <span class="run-compare-sub">${formatRunTimestamp(item.updatedAt || item.createdAt)}</span>
                            </div>
                            <div class="retry-lineage-badges">
                                <span class="mode-badge ${item.mode}">${item.mode}</span>
                                <span class="run-status-badge">${item.isRunning ? '실행 중' : formatFinishStatus(item.finishStatus || 'unknown')}</span>
                                ${item.isCurrent ? '<span class="run-status-badge">현재</span>' : ''}
                                ${retry.isRetry ? '<span class="run-status-badge">재시도</span>' : '<span class="run-status-badge">루트</span>'}
                            </div>
                        </div>
                        <div class="retry-lineage-meta">
                            <span>${item.succeeded || 0}/${item.total || 0} 성공</span>
                            <span>A${review.approved || 0} / R${review.rejected || 0} / 메모 ${review.noted || 0}</span>
                            <span>${item.templateId || '템플릿 없음'}</span>
                            <span>${retryMeta}</span>
                        </div>
                        ${comparison ? `<div class="retry-lineage-outcome ${outcomeTone}"><strong>${comparison.label}</strong> ${comparison.summary}</div>` : ''}
                        ${changes && changes.count ? `
                            <div class="retry-lineage-change-block">
                                <label>요청 변경점</label>
                                <div class="retry-lineage-change-summary">${escapeHtml(changes.summary || '')}</div>
                                <div class="retry-lineage-change-list">
                                    ${(changes.items || []).map((change) => `<span class="retry-chip">${escapeHtml(change.detail || '')}</span>`).join('')}
                                </div>
                            </div>
                        ` : ''}
                        <div class="run-compare-sub">${noteText}</div>
                        <div class="retry-lineage-actions">
                            <button class="btn btn-secondary lineage-load-btn" data-run-id="${item.runId}">Run 보기</button>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;

    container.querySelectorAll('.lineage-load-btn').forEach((button) => {
        button.addEventListener('click', () => loadRunIntoView(button.dataset.runId));
    });
}

function renderRetrySuggestionPanel() {
    const container = Utils.el(CONFIG.DOM.RUN_RETRY_SUGGESTION);
    if (!container) return;

    const suggestion = AppState.retrySuggestion;
    if (!suggestion) {
        container.innerHTML = `
            <div class="run-empty">
                검수 메모가 쌓이면 최신 assisted run 기준 재시도 제안이 여기에 나타납니다.
            </div>
        `;
        return;
    }

    const scenePatch = suggestion.sceneDraftPatch || {};
    const patchValues = Object.entries(scenePatch).filter(([, value]) => value);
    const styleAdds = suggestion.stylePromptAdditions || [];
    const negativeAdds = suggestion.negativePromptAdditions || [];
    const promptHints = suggestion.promptHints || [];
    const sourceNotes = suggestion.sourceNotes || [];

    container.innerHTML = `
        <div class="retry-suggestion-header">
            <div>
                <strong>보조 렌더 재시도 제안</strong>
                <div class="retry-suggestion-summary">${suggestion.summary || '재시도 요약이 없습니다.'}</div>
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
                <button class="btn btn-secondary" id="apply-retry-suggestion-btn">Planner에 적용</button>
                <button class="btn btn-primary" id="start-retry-suggestion-btn">이 Run 다시 생성</button>
            </div>
        </div>
        <div class="retry-suggestion-grid">
            <div class="retry-suggestion-card">
                <label>Scene Planner 변경안</label>
                ${patchValues.length ? `
                    <div class="retry-note-list">
                        ${patchValues.map(([key, value]) => `<div class="retry-note-item"><strong>${key}</strong>${value}</div>`).join('')}
                    </div>
                ` : '<div class="run-empty">제안된 scene patch가 없습니다.</div>'}
            </div>
            <div class="retry-suggestion-card">
                <label>프롬프트 힌트</label>
                ${promptHints.length ? `<div class="retry-chip-row">${promptHints.map((item) => `<span class="retry-chip">${item}</span>`).join('')}</div>` : '<div class="run-empty">아직 프롬프트 힌트가 없습니다.</div>'}
                <label style="margin-top: 8px;">스타일 추가</label>
                ${styleAdds.length ? `<div class="retry-chip-row">${styleAdds.map((item) => `<span class="retry-chip">${item}</span>`).join('')}</div>` : '<div class="run-empty">스타일 추가 제안이 없습니다.</div>'}
                <label style="margin-top: 8px;">네거티브 추가</label>
                ${negativeAdds.length ? `<div class="retry-chip-row">${negativeAdds.map((item) => `<span class="retry-chip">${item}</span>`).join('')}</div>` : '<div class="run-empty">네거티브 추가 제안이 없습니다.</div>'}
            </div>
        </div>
        <div class="retry-suggestion-card">
            <label>원본 검수 메모</label>
            ${sourceNotes.length ? `
                <div class="retry-note-list">
                    ${sourceNotes.map((item) => `<div class="retry-note-item"><strong>${item.status}</strong>${item.note}</div>`).join('')}
                </div>
            ` : '<div class="run-empty">거부 또는 승인된 결과에 검수 메모를 남기면 더 나은 재시도 제안을 받을 수 있습니다.</div>'}
        </div>
    `;

    Utils.el('apply-retry-suggestion-btn')?.addEventListener('click', applyRetrySuggestionToPlanner);
    Utils.el('start-retry-suggestion-btn')?.addEventListener('click', startRetrySuggestionRun);
}

function mergeTextValue(base, additions) {
    const parts = [base || '', ...(additions || [])].filter(Boolean);
    return parts.join(base ? ', ' : '');
}

function applyRetrySuggestionToPlanner() {
    const suggestion = AppState.retrySuggestion;
    if (!suggestion) return;

    Utils.setVal(CONFIG.DOM.GENERATION_MODE, 'assisted');
    const patch = suggestion.sceneDraftPatch || {};
    const current = getScenePlannerState();
    setScenePlannerState({
        situation: patch.situation || current.situation,
        interaction: patch.interaction || current.interaction,
        background: patch.background || current.background,
        location: patch.location || current.location,
        lighting: patch.lighting || current.lighting,
    });
    saveScenePlannerState();

    const stylePrompt = Utils.val('style-prompt');
    const negativePrompt = Utils.val('negative-prompt');
    Utils.setVal('style-prompt', mergeTextValue(stylePrompt, suggestion.stylePromptAdditions || []));
    Utils.setVal('negative-prompt', mergeTextValue(negativePrompt, suggestion.negativePromptAdditions || []));

    if (suggestion.templateId) {
        const matchingTemplate = AppState.sceneTemplates.find((item) => item.id === suggestion.templateId);
        if (matchingTemplate) {
            AppState.activeSceneTemplateId = matchingTemplate.id;
            fillSceneTemplateEditor(matchingTemplate);
            renderSceneTemplates();
        }
    }

    updateGenerationModeNote();
    setActiveTab('compose');
    showToast('Retry suggestion applied to planner', 'success');
}

function buildRetrySceneSpecFromSuggestion(suggestion) {
    const sourceSceneSpec = suggestion.sceneSpec || {};
    const sourceScene = sourceSceneSpec.scene || {};
    const sourceVisual = sourceSceneSpec.visual || {};
    const patch = suggestion.sceneDraftPatch || {};
    return {
        project_id: AppState.currentProject,
        template_id: suggestion.templateId || sourceSceneSpec.template_id || null,
        actors: sourceSceneSpec.actors || [],
        scene: {
            situation: patch.situation || sourceScene.situation || '',
            interaction: patch.interaction || sourceScene.interaction || '',
            background: patch.background || sourceScene.background || '',
            location: patch.location || sourceScene.location || ''
        },
        props: sourceSceneSpec.props || [],
        visual: {
            framing: sourceVisual.framing || '',
            camera_distance: sourceVisual.camera_distance || '',
            lighting: patch.lighting || sourceVisual.lighting || ''
        },
        style: sourceSceneSpec.style || [],
        outputs: suggestion.outputTypes || sourceSceneSpec.outputs || ['thumb', 'hero'],
        variation: sourceSceneSpec.variation || {}
    };
}

function buildRetryPayloadFromSuggestion() {
    const suggestion = AppState.retrySuggestion;
    if (!suggestion) return null;
    const baseGeneration = suggestion.baseGeneration || {};
    const stylePrompt = mergeTextValue(baseGeneration.stylePrompt || '', suggestion.stylePromptAdditions || []);
    const negativePrompt = mergeTextValue(baseGeneration.negativePrompt || '', suggestion.negativePromptAdditions || []);
    return {
        project: AppState.currentProject,
        mode: 'assisted',
        provider_id: suggestion.providerId || null,
        template_id: suggestion.templateId || null,
        scene_spec: buildRetrySceneSpecFromSuggestion(suggestion),
        prompts: [],
        reference_assets: suggestion.referenceAssets || [],
        types: suggestion.outputTypes || ['thumb', 'hero'],
        style_prompt: stylePrompt,
        negative_prompt: negativePrompt,
        global_aspect_ratio: baseGeneration.aspectRatio || Utils.val('default-ar') || CONFIG.DEFAULTS.AR,
        batch_count: baseGeneration.batchCount || 1,
        steps: baseGeneration.steps || CONFIG.DEFAULTS.STEPS,
        metadata: {
            retry_from_run_id: suggestion.runId,
            retry_source: 'review-suggestion'
        }
    };
}

async function startRetrySuggestionRun() {
    const suggestion = AppState.retrySuggestion;
    if (!suggestion) return;

    applyRetrySuggestionToPlanner();
    const payload = buildRetryPayloadFromSuggestion();
    if (!payload) return;

    try {
        const preflight = await fetchPreflightValidation(payload);
        if ((preflight.errors || []).length > 0) {
            setActiveTab('compose');
            showToast(preflight.errors[0], 'error');
            return;
        }

        setBusy(true);
        const resp = await fetch(CONFIG.API.START_BATCH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || 'Failed to start retry');
        }
        AppState.currentRunId = data.runId || null;
        AppState.displayedRunId = data.runId || null;
        AppState.displayedRunSummary = null;
        await loadRecentRuns();
        setActiveTab('outputs');
        pollStatus();
        showToast('Retry batch started', 'success');
    } catch (e) {
        showToast(`Retry start failed: ${e.message}`, 'error');
        setBusy(false);
    }
}

function resetRunViewState() {
    AppState.displayedRunId = null;
    AppState.displayedRunSummary = null;
    AppState.currentRunCodexHandoff = null;
    AppState.currentRunCodexHandoffRequestKey = '';
    AppState.lastLogCount = 0;
    AppState.lastResultCount = 0;

    const logContainer = Utils.el(CONFIG.DOM.LOGS);
    if (logContainer) logContainer.innerHTML = '';

    const gallery = Utils.el(CONFIG.DOM.GALLERY);
    if (gallery) gallery.innerHTML = '';

    const previewEl = Utils.el(CONFIG.DOM.PREVIEW);
    if (previewEl) {
        previewEl.innerHTML = `
            <div class="preview-placeholder">
                <i data-lucide="camera"></i>
                <p>생성된 이미지가 여기에 표시됩니다</p>
            </div>
        `;
    }
    renderRunCodexHandoffPreview();
}

function renderRunViewState() {
    const container = Utils.el(CONFIG.DOM.RUN_VIEW_STATE);
    if (!container) return;

    const displayedRunId = AppState.displayedRunId;
    const liveRunId = AppState.currentRunId;
    const displayedSummary = AppState.displayedRunSummary
        || AppState.recentRuns.find((item) => item.runId === displayedRunId)
        || null;
    const viewingHistorical = Boolean(
        displayedRunId
        && displayedSummary
        && !displayedSummary.isRunning
        && (!liveRunId || displayedRunId !== liveRunId)
    );
    const hasDisplayed = Boolean(displayedRunId);

    if (!hasDisplayed && !liveRunId) {
        container.innerHTML = '';
        return;
    }

    const copyRunHandoffButton = displayedSummary?.mode === 'assisted'
        ? '<button class="btn btn-secondary" id="copy-run-codex-handoff-btn">Run handoff 복사</button>'
        : '';

    if (viewingHistorical) {
        container.innerHTML = `
            <div class="run-view-banner historical">
                <div class="run-view-copy">
                    <strong>과거 run을 보고 있습니다</strong>
                    <span>${liveRunId
                        ? `현재 Run ${String(displayedRunId || '').slice(0, 8)} 을 보고 있습니다. Live run ${String(liveRunId || '').slice(0, 8)} 은 별도로 계속 추적 중입니다.`
                        : `저장된 Run ${String(displayedRunId || '').slice(0, 8)} 스냅샷을 보고 있습니다.`}</span>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    ${copyRunHandoffButton}
                    ${liveRunId ? '<button class="btn btn-secondary" id="follow-live-run-btn">Live Run으로 돌아가기</button>' : ''}
                </div>
            </div>
        `;
        Utils.el('copy-run-codex-handoff-btn')?.addEventListener('click', copyFocusedRunCodexHandoff);
        Utils.el('follow-live-run-btn')?.addEventListener('click', followLiveRun);
        return;
    }

    const mode = displayedSummary?.mode || 'direct';
    const statusText = displayedSummary?.isRunning ? '실행 중' : formatFinishStatus(displayedSummary?.finishStatus || 'ready');
    container.innerHTML = `
        <div class="run-view-banner live">
            <div class="run-view-copy">
                <strong>${liveRunId ? '실시간 run 추적 중' : 'run 확인 중'}</strong>
                <span>${displayedRunId ? `Run ${String(displayedRunId).slice(0, 8)}` : '선택된 run 없음'} · ${mode === 'direct' ? '직접 렌더' : '보조 렌더'} · ${statusText}</span>
            </div>
            ${copyRunHandoffButton}
        </div>
    `;
    Utils.el('copy-run-codex-handoff-btn')?.addEventListener('click', copyFocusedRunCodexHandoff);
}

async function loadRunIntoView(runId) {
    try {
        const resp = await fetch(`${CONFIG.API.RUNS}/${encodeURIComponent(runId)}?project=${encodeURIComponent(AppState.currentProject)}`);
        const record = await resp.json();
        if (!resp.ok || record.detail) {
            throw new Error(record.detail || 'Failed to load run');
        }
        resetRunViewState();
        const statusRecord = run_record_to_status_client(record);
        setDisplayedRun(statusRecord);
        AppState.currentRunCodexHandoff = record.codexHandoff || null;
        AppState.currentRunCodexHandoffRequestKey = buildRunHandoffRequestKey(AppState.currentProject, record.runId || runId);
        updateUI(statusRecord, { syncCurrentRun: false, syncDisplayedRun: false });
        if ((record.mode || '').toLowerCase() === 'assisted') {
            AppState.retryFocusRunId = record.runId || runId;
            await Promise.all([
                loadRetrySuggestion(record.runId || runId, false),
                loadRetryLineage(record.runId || runId, false)
            ]);
        } else {
            AppState.retryFocusRunId = null;
            AppState.retrySuggestion = null;
            AppState.retryLineage = null;
            AppState.retrySuggestionRequestKey = '';
            AppState.retryLineageRequestKey = '';
            AppState.currentRunCodexHandoff = null;
            AppState.currentRunCodexHandoffRequestKey = '';
        }
        renderRunComparePanel();
        setActiveTab('outputs');
    } catch (e) {
        showToast(`Run load failed: ${e.message}`, 'error');
    }
}

function run_record_to_status_client(record) {
    const status = record.status || {};
    return {
        run_id: record.runId,
        project: record.projectId,
        mode: record.mode,
        provider_id: record.providerId,
        request: record.request || {},
        reference_assets: record.referenceAssets || [],
        is_running: status.is_running || false,
        cancel_requested: status.cancel_requested || false,
        finish_status: status.finish_status || null,
        total: status.total || 0,
        completed: status.completed || 0,
        succeeded: status.succeeded || 0,
        warnings: status.warnings || 0,
        errors: status.errors || 0,
        current_item: status.current_item || '',
        logs: record.logs || [],
        results: record.results || [],
        timing: record.timing || { batch_start: null, image_durations: [], current_start: null }
    };
}

function updateOutputsAdvancedVisibility() {
    const section = Utils.el(CONFIG.DOM.OUTPUTS_ADVANCED_SECTION);
    const button = Utils.el(CONFIG.DOM.OUTPUTS_ADVANCED_TOGGLE);
    if (!section || !button) return;
    section.classList.toggle('is-collapsed', !AppState.outputsAdvancedVisible);
    button.textContent = AppState.outputsAdvancedVisible ? '고급 패널 숨기기' : '고급 보기';
}

function toggleOutputsAdvanced() {
    AppState.outputsAdvancedVisible = !AppState.outputsAdvancedVisible;
    updateOutputsAdvancedVisibility();
}

function renderRunComparePanel() {
    const panel = Utils.el(CONFIG.DOM.RUN_COMPARE_PANEL);
    const grid = Utils.el(CONFIG.DOM.RUN_COMPARE_GRID);
    if (!panel || !grid) return;
    updateOutputsAdvancedVisibility();

    const buckets = getCompareRunBuckets();
    const directRun = buckets.find((item) => item.key === 'direct')?.run || null;
    const assistedRun = buckets.find((item) => item.key === 'assisted')?.run || null;
    const hasAny = buckets.some((item) => item.run);
    if (!hasAny) {
        renderRunViewState();
        renderRunCodexHandoffPreview();
        grid.innerHTML = '<div class="run-empty">최근 직접 렌더 또는 보조 렌더 run이 아직 없습니다.</div>';
        renderRunDiffSummary(null, null);
        renderRetrySuggestionPanel();
        renderRetryLineagePanel();
        panel.style.display = '';
        return;
    }

    grid.innerHTML = buckets.map(({ key, title, run }) => {
        if (!run) {
            return `
                <div class="run-compare-card">
                    <div class="run-compare-top">
                        <div class="run-compare-title">
                            <strong>${title}</strong>
                            <span class="run-compare-sub">최근 ${key === 'direct' ? '직접 렌더' : '보조 렌더'} run이 없습니다</span>
                        </div>
                        <div class="run-compare-badges">
                            <span class="mode-badge ${key}">${key}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        const activeClass = run.runId === AppState.displayedRunId ? 'active' : '';
        const statusText = run.isRunning ? '실행 중' : formatFinishStatus(run.finishStatus || 'unknown');
        const sceneText = run.sceneSummary || '장면 요약 없음';
        const templateText = run.templateId || '템플릿 없음';
        const outputTypes = (run.outputTypes || []).join(', ') || '-';
        const review = run.reviewSummary || {};
        const reviewText = `A${review.approved || 0} / R${review.rejected || 0} / Notes ${review.noted || 0}`;
        const noteText = (review.noteHighlights || []).join(' | ') || '검수 메모 없음';
        const retryText = run.retry?.fromRunId ? `재시도 시작점 ${String(run.retry.fromRunId).slice(0, 8)}` : '루트 run';
        return `
            <div class="run-compare-card ${activeClass}">
                <div class="run-compare-top">
                    <div class="run-compare-title">
                        <strong>${title}</strong>
                        <span class="run-compare-sub">${formatRunTimestamp(run.updatedAt || run.createdAt)}</span>
                    </div>
                    <div class="run-compare-badges">
                        <span class="mode-badge ${run.mode}">${run.mode}</span>
                        <span class="run-status-badge">${statusText}</span>
                    </div>
                </div>
                <div class="run-compare-meta">
                    <span>Run ${String(run.runId || '').slice(0, 8)}</span>
                    <span>${run.succeeded}/${run.total || 0}개 성공</span>
                    <span>레퍼런스 ${run.referenceCount || 0}개</span>
                    <span>프롬프트 ${run.promptCount || 0}개</span>
                    <span>${templateText}</span>
                    <span>${outputTypes}</span>
                    <span>${retryText}</span>
                </div>
                <div class="run-compare-scene">${sceneText}</div>
                <div class="run-compare-sub">${reviewText}</div>
                <div class="run-compare-sub">${noteText}</div>
                <div class="run-compare-actions">
                    <button class="btn btn-secondary run-load-btn" data-run-id="${run.runId}">Run 보기</button>
                </div>
            </div>
        `;
    }).join('');

    grid.querySelectorAll('.run-load-btn').forEach((button) => {
        button.addEventListener('click', () => loadRunIntoView(button.dataset.runId));
    });

    panel.style.display = '';
    renderRunViewState();
    renderRunCodexHandoffPreview();
    renderRunDiffSummary(directRun, assistedRun);
    renderRetrySuggestionPanel();
    renderRetryLineagePanel();
    lucide.createIcons();
}

function renderSceneTemplates() {
    const list = Utils.el(CONFIG.DOM.TEMPLATE_LIST);
    const empty = Utils.el(CONFIG.DOM.TEMPLATE_EMPTY);
    if (!list || !empty) return;

    if (!AppState.sceneTemplates.length) {
        list.innerHTML = '';
        empty.style.display = '';
        updateComposeSelectionSummary();
        lucide.createIcons();
        return;
    }

    empty.style.display = 'none';
    list.innerHTML = AppState.sceneTemplates.map((template) => `
        <button type="button" class="scene-template-card ${template.id === AppState.activeSceneTemplateId ? 'active' : ''}" data-template-id="${template.id}">
            <div class="scene-template-card-top">
                <strong>${template.name}</strong>
                <span class="pill">${getSceneTemplateCompositionLabel(template.composition)}</span>
            </div>
            <p>${template.description || '설명 없음'}</p>
            <div class="scene-template-meta">
                <span>레퍼런스 ${(template.referenceAssetPaths || []).length}개</span>
                <span>${template.globalAspectRatio || CONFIG.DEFAULTS.AR}</span>
                <span>steps ${template.steps || CONFIG.DEFAULTS.STEPS}</span>
            </div>
            <div class="scene-template-assets">${summarizeTemplateSceneDraft(template)}</div>
            <div class="scene-template-assets">${summarizeTemplateAssets(template)}</div>
        </button>
    `).join('');

    list.querySelectorAll('.scene-template-card').forEach((button) => {
        button.addEventListener('click', () => {
            const template = AppState.sceneTemplates.find((item) => item.id === button.dataset.templateId);
            if (!template) return;
            AppState.activeSceneTemplateId = template.id;
            fillSceneTemplateEditor(template);
            renderSceneTemplates();
        });
    });

    updateComposeSelectionSummary();
    lucide.createIcons();
}

async function saveSceneTemplate() {
    const payload = getSceneTemplateEditorState();
    if (!payload.name) {
        showToast('템플릿 이름이 필요합니다', 'error');
        return;
    }

    const saveBtn = Utils.el(CONFIG.DOM.TEMPLATE_SAVE_BTN);
    if (saveBtn) saveBtn.disabled = true;

    try {
        const resp = await fetch(CONFIG.API.TEMPLATES, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project: AppState.currentProject,
                template: payload
            })
        });
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || '템플릿 저장에 실패했습니다');
        }
        AppState.activeSceneTemplateId = data.template?.id || null;
        await loadSceneTemplates();
        fillSceneTemplateEditor(data.template || null);
        showToast('장면 템플릿을 저장했습니다', 'success');
    } catch (e) {
        showToast(`템플릿 저장 실패: ${e.message}`, 'error');
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function applySceneTemplate() {
    const template = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId);
    if (!template) {
        showToast('먼저 장면 템플릿을 선택하세요', 'error');
        return;
    }

    const paths = new Set(template.referenceAssetPaths || []);
    const selectedAssets = AppState.referenceAssets.filter((asset) => paths.has(asset.relativePath));
    AppState.selectedReferenceAssets = selectedAssets;
    saveReferenceAssetSelection();

    Utils.setVal('style-prompt', template.stylePrompt || '');
    Utils.setVal('negative-prompt', template.negativePrompt || '');
    Utils.setVal('default-ar', template.globalAspectRatio || CONFIG.DEFAULTS.AR);
    Utils.setVal('batch-count', template.batchCount || CONFIG.DEFAULTS.REPEAT);
    Utils.setVal('steps', template.steps || CONFIG.DEFAULTS.STEPS);
    const stepsVal = Utils.el('steps-val');
    if (stepsVal) stepsVal.innerText = `${template.steps || CONFIG.DEFAULTS.STEPS}`;
    setScenePlannerState(template.sceneDraft || template.meta?.sceneDraft || {});
    saveScenePlannerState();

    fillSceneTemplateEditor(template);
    renderReferenceAssets();

    const missingCount = (template.referenceAssetPaths || []).length - selectedAssets.length;
    if (missingCount > 0) {
        showToast(`누락된 자산 ${missingCount}개를 제외하고 템플릿을 적용했습니다`, 'warning');
    } else {
        showToast('장면 템플릿을 적용했습니다', 'success');
    }
}

async function deleteSceneTemplate() {
    const template = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId);
    if (!template) {
        showToast('먼저 장면 템플릿을 선택하세요', 'error');
        return;
    }

    const deleteBtn = Utils.el(CONFIG.DOM.TEMPLATE_DELETE_BTN);
    if (deleteBtn) deleteBtn.disabled = true;

    try {
        const resp = await fetch(`${CONFIG.API.TEMPLATES}/${encodeURIComponent(template.id)}?project=${encodeURIComponent(AppState.currentProject)}`, {
            method: 'DELETE'
        });
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || '템플릿 삭제에 실패했습니다');
        }
        AppState.activeSceneTemplateId = null;
        fillSceneTemplateEditor(null);
        await loadSceneTemplates();
        showToast('장면 템플릿을 삭제했습니다', 'success');
    } catch (e) {
        showToast(`템플릿 삭제 실패: ${e.message}`, 'error');
    } finally {
        if (deleteBtn) deleteBtn.disabled = false;
    }
}

function getSingleSelectReferenceSlots() {
    const slots = AppState.referencePolicy?.singleSelectSlots;
    return new Set(Array.isArray(slots) && slots.length > 0 ? slots : ['identity', 'emotion', 'role', 'scene']);
}

function getReferenceSlotLabel(slot) {
    const labels = {
        identity: '정체성',
        emotion: '감정',
        role: '역할',
        scene: '장면',
        style: '스타일',
        prop: '소품',
        extra: '기타'
    };
    return labels[slot] || slot;
}

function getSelectedReferenceAssetsBySlot() {
    return AppState.selectedReferenceAssets.reduce((acc, asset) => {
        const slot = asset.slot || 'extra';
        if (!acc[slot]) acc[slot] = [];
        acc[slot].push(asset);
        return acc;
    }, {});
}

function renderReferenceDefinitionFiles() {
    const container = Utils.el(CONFIG.DOM.REFERENCE_DEFINITIONS);
    if (!container) return;
    if (!AppState.referenceDefinitions.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = `
        <label>정의 파일</label>
        <div class="reference-definition-list">
            ${AppState.referenceDefinitions.map((item) => `<span class="reference-definition-chip">${item.relativePath}</span>`).join('')}
        </div>
    `;
}

function renderReferenceUploadPresets() {
    const container = Utils.el(CONFIG.DOM.REFERENCE_PRESET_GROUP);
    if (!container) return;
    const presets = AppState.referencePolicy?.libraryPresets || [];
    if (!presets.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = `
        <label>빠른 경로</label>
        <div class="reference-preset-chips">
            ${presets.map((preset) => `
                <button type="button" class="reference-preset-chip" data-path="${preset.path}">
                    ${preset.label}
                </button>
            `).join('')}
        </div>
    `;
    container.querySelectorAll('.reference-preset-chip').forEach((button) => {
        button.addEventListener('click', () => {
            const targetDirInput = Utils.el(CONFIG.DOM.REFERENCE_TARGET_DIR);
            if (targetDirInput) targetDirInput.value = button.dataset.path || '';
        });
    });
}

function renderReferenceBlueprintGroup(title, description, presets, emptyMessage) {
    const items = presets || [];
    return `
        <div class="reference-bucket blueprint">
            <div class="reference-bucket-header">
                <div>
                    <strong>${title}</strong>
                    <p>${description}</p>
                </div>
                <span>${items.length}개 경로</span>
            </div>
            ${items.length > 0 ? `
                <div class="reference-blueprint-grid">
                    ${items.map((preset) => `
                        <button type="button" class="reference-blueprint-card" data-path="${preset.path}">
                            <strong>${preset.label}</strong>
                            <span>${preset.path}</span>
                        </button>
                    `).join('')}
                </div>
            ` : `
                <div class="reference-bucket-empty">${emptyMessage}</div>
            `}
        </div>
    `;
}

function saveReferenceAssetSelection() {
    const savedState = loadStudioState();
    saveStudioState({
        currentProject: AppState.currentProject,
        selectedReferenceAssets: {
            ...(savedState.selectedReferenceAssets || {}),
            [AppState.currentProject]: AppState.selectedReferenceAssets.map((asset) => asset.relativePath)
        }
    });
}

function updateReferenceSelectionSummary() {
    const countEl = Utils.el(CONFIG.DOM.REFERENCE_SELECTION_COUNT);
    if (countEl) {
        countEl.textContent = `${AppState.selectedReferenceAssets.length}개 선택됨`;
    }

    const previewEl = Utils.el(CONFIG.DOM.REFERENCE_SELECTION_PREVIEW);
    if (previewEl) {
        const grouped = getSelectedReferenceAssetsBySlot();
        const summary = Object.entries(grouped).map(([slot, items]) => {
            const label = getReferenceSlotLabel(slot);
            const names = items.map((asset) => asset.name).slice(0, 2).join(', ');
            const suffix = items.length > 2 ? ` +${items.length - 2}` : '';
            return `${label}: ${names}${suffix}`;
        });
        previewEl.textContent = summary.length > 0 ? summary.join(' | ') : '선택된 레퍼런스 없음';
    }

    updateComposeSelectionSummary();
}

function toggleReferenceAsset(relativePath, checked) {
    const asset = AppState.referenceAssets.find((item) => item.relativePath === relativePath);
    if (!asset) return;

    if (checked) {
        if (getSingleSelectReferenceSlots().has(asset.slot)) {
            AppState.selectedReferenceAssets = AppState.selectedReferenceAssets.filter((item) => item.slot !== asset.slot);
        }
        if (!AppState.selectedReferenceAssets.some((item) => item.relativePath === relativePath)) {
            AppState.selectedReferenceAssets.push(asset);
        }
    } else {
        AppState.selectedReferenceAssets = AppState.selectedReferenceAssets.filter((item) => item.relativePath !== relativePath);
    }

    saveReferenceAssetSelection();
    renderReferenceAssets();
}

function renderReferenceStatus() {
    const container = Utils.el(CONFIG.DOM.REFERENCE_STATUS_GRID);
    if (!container) return;

    const slotStatus = AppState.referenceStatus?.slotStatus || [];
    if (!slotStatus.length) {
        container.innerHTML = '';
        return;
    }

    const selectedBySlot = getSelectedReferenceAssetsBySlot();
    container.innerHTML = slotStatus.map((item) => {
        const statusClass = item.filled ? 'filled' : (item.required ? 'missing' : 'pending');
        const selectedCount = selectedBySlot[item.slot]?.length || 0;
        const badge = item.required ? '필수' : (item.recommended ? '권장' : '선택');
        return `
            <div class="reference-status-card ${statusClass}">
                <div class="reference-status-top">
                    <strong>${getReferenceSlotLabel(item.slot)}</strong>
                    <span class="reference-status-badge">${badge}</span>
                </div>
                <div class="reference-status-count">${item.count}개 라이브러리</div>
                <div class="reference-status-sub">${selectedCount > 0 ? `이번 배치 ${selectedCount}개 선택` : '이번 배치 선택 없음'}</div>
            </div>
        `;
    }).join('');
}

function renderReferenceSectionGroup(title, description, assets) {
    if (!assets.length) {
        return `
            <div class="reference-bucket">
                <div class="reference-bucket-header">
                    <div>
                        <strong>${title}</strong>
                        <p>${description}</p>
                    </div>
                    <span>0개</span>
                </div>
                <div class="reference-bucket-empty">아직 등록된 자산이 없습니다.</div>
            </div>
        `;
    }

    const sections = assets.reduce((acc, asset) => {
        const key = asset.section || 'misc';
        if (!acc[key]) acc[key] = [];
        acc[key].push(asset);
        return acc;
    }, {});

    return `
        <div class="reference-bucket">
            <div class="reference-bucket-header">
                <div>
                    <strong>${title}</strong>
                    <p>${description}</p>
                </div>
                <span>${assets.length}개</span>
            </div>
            ${Object.entries(sections).map(([section, items]) => `
                <div class="reference-section">
                    <div class="reference-section-header">
                        <span>${section}</span>
                        <span>${items.length}개</span>
                    </div>
                    <div class="reference-card-grid">
                        ${items.map((asset) => `
                            <label class="reference-card ${AppState.selectedReferenceAssets.some((item) => item.relativePath === asset.relativePath) ? 'selected' : ''}">
                                <div class="reference-card-check">
                                    <input type="checkbox" class="reference-checkbox" data-relative-path="${asset.relativePath}" ${AppState.selectedReferenceAssets.some((item) => item.relativePath === asset.relativePath) ? 'checked' : ''}>
                                    <span>${asset.character ? `${asset.character} / ${asset.slot}` : (asset.group || asset.section)}</span>
                                </div>
                                <img src="${asset.previewUrl}" alt="${asset.name}" loading="lazy">
                                <div class="reference-card-body">
                                    <strong>${asset.name}</strong>
                                    <span>${asset.filename}</span>
                                    <span>${getReferenceSlotLabel(asset.slot)}</span>
                                </div>
                            </label>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function renderReferenceAssets() {
    const grid = Utils.el(CONFIG.DOM.REFERENCE_GRID);
    const empty = Utils.el(CONFIG.DOM.REFERENCE_EMPTY);
    if (!grid || !empty) return;

    updateReferenceSelectionSummary();
    renderReferenceDefinitionFiles();
    renderReferenceUploadPresets();
    renderReferenceStatus();

    const targetDirInput = Utils.el(CONFIG.DOM.REFERENCE_TARGET_DIR);
    if (targetDirInput && !targetDirInput.value) {
        const preferredPath = AppState.referencePolicy?.libraryPresets?.[0]?.path || AppState.referencePolicy?.temporaryRoot || 'temp';
        targetDirInput.value = preferredPath;
    }

    if (AppState.referenceAssets.length === 0) {
        empty.style.display = '';
        const hint = AppState.referenceDefinitions.length > 0
            ? `정의 파일 ${AppState.referenceDefinitions.map((item) => item.filename).join(', ')} 는 있지만 실제 이미지 자산은 아직 없습니다.`
            : '기준 캐릭터, 감정 시트, 역할 키트를 먼저 넣어두세요';
        empty.innerHTML = `
            <i data-lucide="folder-search"></i>
            <p>아직 등록된 레퍼런스 이미지가 없습니다</p>
            <p class="empty-hint">${hint}</p>
            <p class="empty-hint">아래 구조 가이드를 보고 바로 어떤 폴더에 무엇을 넣을지 결정할 수 있습니다.</p>
        `;
        const presets = AppState.referencePolicy?.libraryPresets || [];
        const libraryPresets = presets.filter((item) => !(item.path || '').startsWith(`${AppState.referencePolicy?.temporaryRoot || 'temp'}/`));
        const temporaryPresets = presets.filter((item) => (item.path || '').startsWith(`${AppState.referencePolicy?.temporaryRoot || 'temp'}/`));
        grid.innerHTML = [
            renderReferenceBlueprintGroup('프로젝트 라이브러리 구조', '항상 유지되는 기준 자산 경로입니다. 베이스, 감정, 역할, 장면을 먼저 채우면 됩니다.', libraryPresets, '아직 정의된 라이브러리 경로가 없습니다.'),
            renderReferenceBlueprintGroup('임시 레퍼런스 구조', '이번 배치에서만 쓰는 참고 이미지는 임시 경로에 넣고, 가치가 있으면 나중에 라이브러리로 승격합니다.', temporaryPresets, '임시 경로가 아직 정의되지 않았습니다.')
        ].join('');
        grid.querySelectorAll('.reference-blueprint-card').forEach((button) => {
            button.addEventListener('click', () => {
                if (targetDirInput) targetDirInput.value = button.dataset.path || '';
            });
        });
        lucide.createIcons();
        return;
    }

    empty.style.display = 'none';

    const libraryAssets = AppState.referenceAssets.filter((asset) => !asset.isTemporary);
    const temporaryAssets = AppState.referenceAssets.filter((asset) => asset.isTemporary);
    grid.innerHTML = [
        renderReferenceSectionGroup('프로젝트 라이브러리', '반복 배치에 공통으로 쓰는 기준 자산입니다.', libraryAssets),
        renderReferenceSectionGroup('임시 레퍼런스', '이번 배치에서만 쓰는 보조 참고 이미지입니다.', temporaryAssets)
    ].join('');

    document.querySelectorAll('.reference-checkbox').forEach((checkbox) => {
        checkbox.addEventListener('change', (event) => {
            toggleReferenceAsset(event.target.dataset.relativePath, event.target.checked);
        });
    });
    grid.querySelectorAll('.reference-blueprint-card').forEach((button) => {
        button.addEventListener('click', () => {
            if (targetDirInput) targetDirInput.value = button.dataset.path || '';
        });
    });
}

async function uploadReferenceAsset() {
    const fileInput = Utils.el(CONFIG.DOM.REFERENCE_UPLOAD_INPUT);
    const targetDirInput = Utils.el(CONFIG.DOM.REFERENCE_TARGET_DIR);
    const file = fileInput?.files?.[0];
    const targetDir = targetDirInput?.value?.trim() || AppState.referencePolicy?.temporaryRoot || 'temp';

    if (!file) {
        showToast('업로드할 레퍼런스 이미지를 선택하세요', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('project', AppState.currentProject);
    formData.append('target_dir', targetDir);
    formData.append('file', file);

    const uploadBtn = Utils.el(CONFIG.DOM.REFERENCE_UPLOAD_BTN);
    if (uploadBtn) uploadBtn.disabled = true;

    try {
        const resp = await fetch(CONFIG.API.REFERENCE_ASSET_UPLOAD, {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();
        if (!resp.ok || data.detail || data.error) {
            throw new Error(data.detail || data.error || 'Upload failed');
        }
        showToast('레퍼런스 이미지 업로드 완료', 'success');
        if (fileInput) fileInput.value = '';
        await loadReferenceAssets();
    } catch (e) {
        showToast(`레퍼런스 업로드 실패: ${e.message}`, 'error');
    } finally {
        if (uploadBtn) uploadBtn.disabled = false;
    }
}

function renderPromptTable(prompts) {
    const tbody = document.querySelector('#prompt-table tbody');
    tbody.innerHTML = prompts.map((p, idx) => `
        <tr>
            <td class="checkbox-cell">
                <input type="checkbox" class="prompt-checkbox" data-idx="${idx}" checked>
            </td>
            <td>
                <span class="badge ${p.is_manual ? 'manual' : 'kemi'}">${p.is_manual ? 'User' : 'CSV'}</span>
                ${p.aspect_ratio ? `<span class="badge ar-badge">${p.aspect_ratio}</span>` : ''}
            </td>
            <td style="min-width: 150px;">${p.desc_ko}</td>
            <td><code>${p.prompt}</code></td>
        </tr>
    `).join('');
    updateSelectionCounts();
    document.querySelectorAll('.prompt-checkbox').forEach(cb => { cb.onchange = updateSelectionCounts; });
}

function buildComposeSelectionSummary() {
    const checkedPrompts = document.querySelectorAll('.prompt-checkbox:checked').length;
    const referenceCount = AppState.selectedReferenceAssets.length;
    const activeTemplate = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId);
    const templateLabel = activeTemplate ? activeTemplate.name : '템플릿 없음';
    return `${checkedPrompts}개 프롬프트 | ${referenceCount}개 레퍼런스 | ${templateLabel}`;
}

function updateComposeSelectionSummary() {
    const selEl = document.getElementById(CONFIG.DOM.SELECTION_COUNT);
    if (selEl) {
        selEl.innerText = buildComposeSelectionSummary();
    }
}

function updateSelectionCounts() {
    const checked = document.querySelectorAll('.prompt-checkbox:checked').length;
    updateComposeSelectionSummary();
    const btn = document.getElementById(CONFIG.DOM.FAB_BTN);
    if (btn) btn.innerHTML = `<i data-lucide="play"></i> 선택 항목 생성 (${checked})`;
    lucide.createIcons();
    updateCodexHandoffPanel();
    refreshConfirmPreflight();
}

function toggleAllPrompts(source) {
    document.querySelectorAll('.prompt-checkbox').forEach(cb => cb.checked = source.checked);
    updateSelectionCounts();
}

function toggleCustomPromptForm() {
    const form = document.getElementById('custom-prompt-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function clearPromptList() {
    AppState.currentPrompts = [];
    renderPromptTable(AppState.currentPrompts);
    showToast("프롬프트 목록이 초기화되었습니다", "success");
}

function addCustomPrompt() {
    const desc = document.getElementById('custom-desc').value.trim();
    const promptText = document.getElementById('custom-prompt').value.trim();
    const ar = document.getElementById('custom-ar').value;
    if (!desc || !promptText) { showToast("설명과 프롬프트를 모두 입력하세요", "error"); return; }
    AppState.currentPrompts.unshift({ desc_ko: desc, prompt: promptText, aspect_ratio: ar, is_manual: true });
    renderPromptTable(AppState.currentPrompts);
    document.getElementById('custom-desc').value = '';
    document.getElementById('custom-prompt').value = '';
    document.getElementById('custom-desc').focus();
}

function applyPreset() {
    const val = document.getElementById('style-preset').value;
    if (val === 'custom') return;
    const preset = CONFIG.STYLE_PRESETS[val];
    if (preset) {
        document.getElementById('style-prompt').value = preset.p;
        document.getElementById('negative-prompt').value = preset.n;
    }
}

// --- Batch Control ---
function getGenerationMode() {
    const mode = Utils.val(CONFIG.DOM.GENERATION_MODE);
    return mode === 'assisted' ? 'assisted' : 'direct';
}

function updateGenerationModeNote() {
    const noteEl = Utils.el(CONFIG.DOM.GENERATION_MODE_NOTE);
    if (!noteEl) return;
    const providerLabel = getCurrentProviderInfo()?.label || getCurrentProviderId();
    const operatorMode = getOperatorMode();
    const operatorLabel = operatorMode === 'codex-conversation' ? 'Codex 대화 연동' : 'Studio 운영';
    updateOperatorModeAvailability();

    if (getGenerationMode() === 'direct') {
        noteEl.textContent = `직접 렌더는 현재 prompt-first 흐름을 유지하고 ${operatorLabel} 방식으로 ${providerLabel}에 전달합니다.`;
        return;
    }

    const activeTemplate = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId);
    const templateName = activeTemplate?.name || '선택된 템플릿 없음';
    const referenceCount = AppState.selectedReferenceAssets.length;
    const sceneDraft = getScenePlannerState();
    const hasSceneDraft = Object.values(sceneDraft).some(Boolean);
    noteEl.textContent = `보조 렌더는 현재 프롬프트, 레퍼런스 ${referenceCount}개, ${templateName}, ${hasSceneDraft ? 'Scene Planner 입력' : '기본 파생값'}으로 장면 사양을 만든 뒤 ${operatorLabel} 방식으로 ${providerLabel}에 전달합니다${operatorMode === 'codex-conversation' ? ' 그리고 대화용 handoff도 함께 제공합니다.' : '.'}`;
}

function buildSceneActorsFromReferences() {
    const byCharacter = new Map();
    AppState.selectedReferenceAssets.forEach((asset) => {
        if (!asset.character) return;
        const existing = byCharacter.get(asset.character) || {
            character: asset.character,
            emotion: '',
            role: ''
        };
        if (asset.slot === 'emotion' && !existing.emotion) existing.emotion = asset.name;
        if (asset.slot === 'role' && !existing.role) existing.role = asset.name;
        byCharacter.set(asset.character, existing);
    });
    return Array.from(byCharacter.values());
}

function buildAssistedSceneSpec(selectedPrompts) {
    const activeTemplate = AppState.sceneTemplates.find((item) => item.id === AppState.activeSceneTemplateId);
    const actors = buildSceneActorsFromReferences();
    const selectedBySlot = getSelectedReferenceAssetsBySlot();
    const sceneDraft = getScenePlannerState();
    const promptSeeds = selectedPrompts
        .map((item) => item.desc_ko || item.prompt || '')
        .filter(Boolean)
        .slice(0, 3);
    const sceneAssets = (selectedBySlot.scene || []).map((asset) => asset.name);
    const propAssets = (selectedBySlot.prop || []).map((asset) => asset.name);
    const styleAssets = (selectedBySlot.style || []).map((asset) => asset.name);
    const visualFraming = activeTemplate?.composition === 'duo'
        ? 'two-person composition'
        : activeTemplate?.composition === 'group'
            ? 'group composition'
            : 'single-character composition';

    return {
        project_id: AppState.currentProject,
        template_id: activeTemplate?.id || null,
        actors,
        scene: {
            situation: sceneDraft.situation || promptSeeds.join(' | '),
            interaction: sceneDraft.interaction || activeTemplate?.description || '',
            background: sceneDraft.background || sceneAssets[0] || '',
            location: sceneDraft.location || ''
        },
        props: propAssets,
        visual: {
            framing: visualFraming,
            camera_distance: selectedPrompts.length > 1 ? 'varied framing' : 'medium shot',
            lighting: sceneDraft.lighting || ''
        },
        style: Array.from(new Set([
            Utils.val('style-preset'),
            ...styleAssets
        ].filter(Boolean))),
        outputs: ['thumb', 'hero'],
        variation: {
            promptSeeds,
            referencePaths: AppState.selectedReferenceAssets.map((asset) => asset.relativePath),
            templateDescription: activeTemplate?.description || ''
        }
    };
}

function buildGenerationPayload(selectedPrompts) {
    const generationMode = getGenerationMode();
    const sceneSpec = generationMode === 'assisted' ? buildAssistedSceneSpec(selectedPrompts) : null;
    return {
        project: AppState.currentProject,
        mode: generationMode,
        provider_id: getCurrentProviderId(),
        operator_mode: getOperatorMode(),
        template_id: AppState.activeSceneTemplateId,
        scene_spec: sceneSpec,
        prompts: selectedPrompts,
        reference_assets: AppState.selectedReferenceAssets,
        types: ['thumb', 'hero'],
        style_prompt: document.getElementById('style-prompt').value,
        negative_prompt: document.getElementById('negative-prompt').value,
        global_aspect_ratio: document.getElementById('default-ar').value,
        batch_count: parseInt(document.getElementById('batch-count').value),
        steps: parseInt(document.getElementById('steps').value)
    };
}

function renderPreflightValidation(result) {
    const panel = Utils.el(CONFIG.DOM.PREFLIGHT_PANEL);
    const summary = Utils.el(CONFIG.DOM.PREFLIGHT_SUMMARY);
    const errors = Utils.el(CONFIG.DOM.PREFLIGHT_ERRORS);
    const warnings = Utils.el(CONFIG.DOM.PREFLIGHT_WARNINGS);
    if (!panel || !summary || !errors || !warnings) return;

    if (!result) {
        panel.style.display = 'none';
        summary.innerHTML = '';
        errors.innerHTML = '';
        warnings.innerHTML = '';
        return;
    }

    const mode = result.summary?.mode || getGenerationMode();
    const estimatedImages = result.summary?.estimatedImages || 0;
    const referenceCount = result.summary?.referenceCount || 0;
    const providerLabel = result.summary?.providerLabel || getCurrentProviderInfo()?.label || getCurrentProviderId();
    const operatorMode = result.summary?.operatorMode || getOperatorMode();
    const operatorLabel = operatorMode === 'codex-conversation' ? 'Codex 대화 연동' : 'Studio 운영';
    const effectiveCapabilities = result.summary?.effectiveCapabilities || {};
    const capabilityChips = [
        `렌더러: ${providerLabel}`,
        `운영 방식: ${operatorLabel}`,
        effectiveCapabilities.supportsDirectGeneration ? '직접 렌더 가능' : '직접 렌더 제한',
        effectiveCapabilities.supportsAssistedGeneration ? '보조 렌더 가능' : '보조 렌더 제한',
        effectiveCapabilities.supportsSceneSpec ? 'Scene spec 사용 가능' : 'Scene spec 비활성',
        effectiveCapabilities.supportsReferenceAssets ? '레퍼런스 conditioning 가능' : '레퍼런스는 planning 전용'
    ];
    summary.innerHTML = `
        <strong>${mode === 'direct' ? '직접 렌더' : '보조 렌더'}</strong> 모드, 예정 렌더 ${estimatedImages}장, 선택된 레퍼런스 ${referenceCount}개
        <div class="preflight-summary-meta">
            ${capabilityChips.map((item) => `<span class="preflight-meta-chip">${item}</span>`).join('')}
        </div>
    `;
    errors.innerHTML = (result.errors || [])
        .map((item) => `<div class="preflight-item">${item}</div>`)
        .join('');
    warnings.innerHTML = (result.warnings || [])
        .map((item) => `<div class="preflight-item">${item}</div>`)
        .join('');
    panel.style.display = '';
}

async function fetchPreflightValidation(payload) {
    const resp = await fetch(CONFIG.API.VALIDATE_GENERATION, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok) {
        throw new Error(data.detail || 'Preflight validation failed');
    }
    AppState.lastPreflight = data;
    renderPreflightValidation(data);
    updateCodexHandoffPanel();
    return data;
}

async function refreshConfirmPreflight() {
    const selectedIdxs = Array.from(document.querySelectorAll('.prompt-checkbox:checked')).map((cb) => parseInt(cb.dataset.idx, 10));
    const selectedPrompts = AppState.currentPrompts.filter((_, i) => selectedIdxs.includes(i));
    if (!selectedPrompts.length) {
        AppState.lastPreflight = null;
        renderPreflightValidation(null);
        updateCodexHandoffPanel([]);
        return null;
    }
    try {
        return await fetchPreflightValidation(buildGenerationPayload(selectedPrompts));
    } catch (e) {
        renderPreflightValidation({
            summary: {
                mode: getGenerationMode(),
                operatorMode: getOperatorMode(),
                referenceCount: AppState.selectedReferenceAssets.length,
                providerLabel: getCurrentProviderInfo()?.label || getCurrentProviderId(),
                effectiveCapabilities: buildEffectiveCapabilities(getCurrentProjectConfig(), getCurrentProviderInfo())
            },
            errors: [e.message],
            warnings: []
        });
        updateCodexHandoffPanel(selectedPrompts);
        return null;
    }
}

async function openConfirmModal() {
    const checked = document.querySelectorAll('.prompt-checkbox:checked').length;
    if (checked === 0) return showToast("프롬프트를 1개 이상 선택하세요", "error");
    const repeat = parseInt(document.getElementById('batch-count').value) || 1;
    const total = checked * 2 * repeat;
    const timeEst = Math.ceil(total * 12 / 60);
    const referenceCount = AppState.selectedReferenceAssets.length;
    const modal = document.getElementById(CONFIG.MODALS.CONFIRM);
    const p = modal.querySelector('p');
    if (p) p.innerHTML = `<strong>${total}장</strong>의 이미지를 생성합니다<br><span style="font-size:0.9em; opacity:0.8">(${checked}개 프롬프트 x ${repeat} 변형 x 2 크기${referenceCount ? `, 레퍼런스 ${referenceCount}개` : ''})</span>`;
    const sub = modal.querySelector('.sub-text');
    if (sub) sub.innerText = `예상 소요 시간: 약 ${timeEst}분`;
    updateGenerationModeNote();
    AppState.lastPreflight = null;
    renderPreflightValidation(null);
    modal.style.display = 'flex';
    renderProviderSelector(getCurrentProjectConfig());
    updateCodexHandoffPanel();
    await refreshConfirmPreflight();
}

function closeConfirmModal() {
    document.getElementById(CONFIG.MODALS.CONFIRM).style.display = 'none';
}

async function confirmStartBatch() {
    const selectedIdxs = Array.from(document.querySelectorAll('.prompt-checkbox:checked')).map(cb => parseInt(cb.dataset.idx));
    if (selectedIdxs.length === 0) return;
    const selectedPrompts = AppState.currentPrompts.filter((_, i) => selectedIdxs.includes(i));
    const payload = buildGenerationPayload(selectedPrompts);
    const preflight = AppState.lastPreflight || await fetchPreflightValidation(payload);
    if ((preflight.errors || []).length > 0) {
        showToast(preflight.errors[0], 'error');
        return;
    }

    closeConfirmModal();
    if (Utils.isChecked(CONFIG.DOM.SETTINGS.AUTOCLEAR)) {
        const gal = Utils.el(CONFIG.DOM.GALLERY); if (gal) gal.innerHTML = '';
        const logs = Utils.el(CONFIG.DOM.LOGS); if (logs) logs.innerHTML = '';
        AppState.lastLogCount = 0;
        AppState.lastResultCount = 0;
    }
    setBusy(true);
    try {
        const resp = await fetch(CONFIG.API.START_BATCH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!resp.ok || data.detail) {
            throw new Error(data.detail || 'Failed to start batch');
        }
        AppState.currentRunId = data.runId || null;
        AppState.displayedRunId = data.runId || null;
        AppState.displayedRunSummary = null;
        await loadRecentRuns();
        pollStatus();
    } catch (e) {
        showToast("생성 시작 실패: " + e.message, "error");
        setBusy(false);
    }
}

function setBusy(isBusy) {
    const startBtn = Utils.el(CONFIG.DOM.START_BTN);
    const fabBtn = Utils.el(CONFIG.DOM.FAB_BTN);
    if (startBtn) {
        startBtn.disabled = isBusy;
        startBtn.innerHTML = isBusy ? '<i class="spinner"></i> 생성 중...' : '<i data-lucide="play"></i> 이미지 생성';
    }
    if (fabBtn) {
        fabBtn.disabled = isBusy;
        fabBtn.innerHTML = isBusy ? '<i class="spinner"></i> 생성 중...' : '<i data-lucide="play"></i> 선택 항목 생성';
    }
    if (!isBusy) lucide.createIcons();
}

// --- Status Polling ---
async function pollStatus() {
    if (AppState.pollIntervalId) {
        clearInterval(AppState.pollIntervalId);
        AppState.pollIntervalId = null;
    }
    let errorCount = 0;
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(buildStatusUrl());
            const data = await resp.json();
            AppState.currentRunId = (data.is_running && data.run_id) ? data.run_id : null;
            errorCount = 0;
            const shouldRenderLive = !AppState.displayedRunId || AppState.displayedRunId === data.run_id;
            if (shouldRenderLive) {
                updateUI(data, { syncCurrentRun: true, syncDisplayedRun: true });
            } else {
                renderRunComparePanel();
            }

            if (!data.is_running && data.finish_status) {
                clearInterval(interval);
                AppState.pollIntervalId = null;
                setBusy(false);
                loadRecentRuns();
                const statusEl = Utils.el(CONFIG.DOM.STATUS_TEXT);
                if (!statusEl) return;
                if (data.finish_status === "success") {
                    statusEl.innerHTML = `<span style="color:var(--accent)">완료 — ${data.succeeded}/${data.total}장 성공</span>`;
                } else if (data.finish_status === "partial") {
                    statusEl.innerHTML = `<span style="color:#f59e0b">완료 — ${data.succeeded}/${data.total}장 (경고 ${data.warnings}건)</span>`;
                } else if (data.finish_status === "cancelled") {
                    statusEl.innerHTML = `<span style="color:var(--text-muted)">중지됨 — ${data.succeeded}/${data.total}장 완료</span>`;
                } else if (data.finish_status === "error") {
                    statusEl.innerHTML = `<span style="color:var(--danger)">오류 — ${data.succeeded}/${data.total}장 (오류 ${data.errors}건)</span>`;
                }
                if (data.finish_status !== "error" && Utils.isChecked(CONFIG.DOM.SETTINGS.SOUND)) {
                    playNotificationSound();
                }
            }
        } catch (e) {
            errorCount++;
            if (errorCount >= 30) {
                clearInterval(interval);
                AppState.pollIntervalId = null;
                setBusy(false);
                showToast("서버 연결이 끊어졌습니다", "error");
            }
        }
    }, 1000);
    AppState.pollIntervalId = interval;
}

// --- UI Update ---
function updateUI(data, options = {}) {
    const { syncCurrentRun = true, syncDisplayedRun = true } = options;
    if (syncDisplayedRun && data.run_id && AppState.displayedRunId && AppState.displayedRunId !== data.run_id) {
        resetRunViewState();
    }
    if (syncDisplayedRun) {
        setDisplayedRun(data);
    } else {
        AppState.lastStatusData = data;
    }
    AppState.currentRunId = syncCurrentRunIdFromStatus(data, syncCurrentRun);
    if (syncDisplayedRun && data.mode !== 'assisted') {
        AppState.retryFocusRunId = null;
        AppState.retrySuggestion = null;
        AppState.retryLineage = null;
        AppState.retrySuggestionRequestKey = '';
        AppState.retryLineageRequestKey = '';
    }
    renderRunComparePanel();

    // Welcome → Batch state transition
    const welcomeEl = Utils.el('welcome-state');
    const batchEl = Utils.el('batch-state');
    if (welcomeEl && batchEl) {
        if (data.total > 0 || data.is_running || data.finish_status) {
            welcomeEl.style.display = 'none';
            batchEl.style.display = '';
        }
    }

    // Cancel button visibility
    const cancelBtn = Utils.el('cancel-batch-btn');
    if (cancelBtn) cancelBtn.style.display = data.is_running ? '' : 'none';

    // Stats
    const totalEl = Utils.el(CONFIG.DOM.TOTAL_TASKS);
    if (totalEl) totalEl.innerText = `${data.completed} / ${data.total}`;

    const percent = data.total > 0 ? (data.completed / data.total * 100) : 0;
    const progEl = Utils.el(CONFIG.DOM.PROGRESS_TEXT);
    if (progEl) progEl.innerText = `${Math.round(percent)}%`;

    const barEl = Utils.el(CONFIG.DOM.PROGRESS_BAR);
    if (barEl) barEl.style.width = `${percent}%`;

    // Status with ETA
    const statusEl = Utils.el(CONFIG.DOM.STATUS_TEXT);
    if (data.is_running && statusEl) {
        let statusText = data.current_item || 'Processing...';
        const durations = data.timing?.image_durations || [];
        if (durations.length > 0 && data.completed < data.total) {
            const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
            const remaining = data.total - data.completed;
            const etaSec = Math.round(avg * remaining);
            const etaMin = Math.floor(etaSec / 60);
            const etaRemSec = etaSec % 60;
            statusText += ` — ETA: ${etaMin}m ${etaRemSec}s (avg ${avg.toFixed(1)}s/image)`;
        }
        statusEl.innerText = statusText;
    }

    // Logs (incremental)
    const logContainer = Utils.el(CONFIG.DOM.LOGS);
    if (logContainer && data.logs.length > AppState.lastLogCount) {
        const newLogs = data.logs.slice(AppState.lastLogCount);
        newLogs.forEach(log => {
            const isError = log.includes('ERROR') || log.includes('Fatal');
            const isWarning = log.includes('WARN') || log.includes('Timeout');
            const isSuccess = log.includes('OK ');
            const logClass = isError ? 'error' : isWarning ? 'warning' : isSuccess ? 'success' : '';
            logContainer.insertAdjacentHTML('beforeend', `<div class="log-entry ${logClass}">${log}</div>`);
        });
        AppState.lastLogCount = data.logs.length;
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    // Gallery (incremental)
    if (data.results.length > AppState.lastResultCount) {
        const gallery = Utils.el(CONFIG.DOM.GALLERY);
        const newItems = data.results.slice(AppState.lastResultCount);
        newItems.forEach((item, i) => {
            const idx = AppState.lastResultCount + i;
            const div = document.createElement('div');
            div.className = `gallery-item ${item.type} ${item.status || 'success'}`;
            div.dataset.index = idx;

            if (item.url) {
                div.innerHTML = `
                    <img src="${item.url}" alt="${item.name}" loading="lazy">
                    <div class="gallery-overlay">
                        <span class="gallery-name">${item.name}</span>
                        <span class="mode-badge ${data.mode || 'direct'}">${data.mode || 'direct'}</span>
                        <span class="badge ${item.type}">${item.type}</span>
                        ${item.review_status && item.review_status !== 'pending' ? `<span class="review-badge ${item.review_status}">${item.review_status === 'approved' ? 'Approved' : 'Rejected'}</span>` : ''}
                    </div>`;
            } else {
                div.innerHTML = `
                    <div class="gallery-placeholder ${item.status}">
                        <span>${item.status === 'timeout' ? 'Timed Out' : 'Failed'}</span>
                        <span class="mode-badge ${data.mode || 'direct'}">${data.mode || 'direct'}</span>
                        <span class="gallery-name">${item.name} (${item.type})</span>
                    </div>`;
            }
            div.addEventListener('click', () => openImageDetail(idx));
            gallery?.appendChild(div);
        });
        AppState.lastResultCount = data.results.length;

        updateGalleryCounts();

        // Live preview - show latest successful image from new items only
        const lastSuccess = [...newItems].reverse().find(r => r.url);
        if (lastSuccess) {
            const previewEl = Utils.el(CONFIG.DOM.PREVIEW);
            if (previewEl) previewEl.innerHTML = `<img src="${lastSuccess.url}" class="fade-in">`;
        }
    }
}

function syncCurrentRunIdFromStatus(data, syncCurrentRun = true) {
    if (!syncCurrentRun) return AppState.currentRunId;
    if (data.run_id && data.is_running) return data.run_id;
    if (!data.is_running) return null;
    return AppState.currentRunId;
}

// --- Gallery Filters ---
function initGalleryFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const filter = btn.dataset.filter;
            const grid = Utils.el(CONFIG.DOM.GALLERY);
            if (!grid) return;
            // CSS 클래스 기반 필터링 (600개 inline style 대신 1번 클래스 변경)
            grid.className = 'gallery-grid' + (filter !== 'all' ? ` filter-${filter}` : '');
        });
    });
}

// --- Image Detail Modal ---
let currentDetailIndex = -1;

function openImageDetail(index) {
    const data = getStatusData();
    if (!data || index < 0 || index >= data.results.length) return;
    currentDetailIndex = index;
    const item = data.results[index];
    const runMode = data.mode || 'direct';
    const modal = Utils.el('image-detail-modal');
    if (!modal) return;

    Utils.el('detail-name').textContent = `${item.name} (${item.type})`;
    const img = Utils.el('detail-img');
    if (item.url) {
        img.src = item.url;
        img.style.display = 'block';
    } else {
        img.style.display = 'none';
    }

    const meta = Utils.el('detail-meta');
    meta.innerHTML = `
        <div><strong>상태:</strong> <span class="badge ${item.status}">${item.status}</span></div>
        <div><strong>모드:</strong> <span class="mode-badge ${runMode}">${runMode}</span></div>
        <div><strong>타입:</strong> ${item.type} (${item.width}x${item.height})</div>
        <div><strong>소요 시간:</strong> ${item.duration ? item.duration.toFixed(1) + 's' : '없음'}</div>
        <div><strong>검수:</strong> <span class="review-badge ${item.review_status || 'pending'}">${item.review_status || 'pending'}</span></div>
        <div><strong>레퍼런스:</strong> ${(item._reference_assets || []).length}개 선택</div>
    `;

    Utils.el('detail-prompt-text').textContent = item.positive || item.prompt || '';
    Utils.el('detail-negative-text').textContent = item.negative || '';
    const noteInput = Utils.el('detail-review-note');
    if (noteInput) noteInput.value = item.review_note || '';

    // Navigation info
    Utils.el('detail-nav-info').textContent = `${index + 1} / ${data.results.length}`;

    modal.style.display = 'flex';
}

function closeImageDetail() {
    const modal = Utils.el('image-detail-modal');
    if (modal) modal.style.display = 'none';
    currentDetailIndex = -1;
}

function navigateDetail(direction) {
    const data = getStatusData();
    if (!data) return;
    const newIndex = currentDetailIndex + direction;
    if (newIndex >= 0 && newIndex < data.results.length) {
        openImageDetail(newIndex);
    }
}

async function reviewCurrentImage(status) {
    if (currentDetailIndex < 0) return;
    try {
        const note = Utils.el('detail-review-note')?.value?.trim() || '';
        const resp = await fetch(`${CONFIG.API.REVIEW}/${currentDetailIndex}/review?project=${encodeURIComponent(AppState.currentProject)}&run_id=${encodeURIComponent(getReviewTargetRunId() || '')}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status, note })
        });
        const body = await resp.json();
        if (!resp.ok || body.detail) {
            throw new Error(body.detail || 'Review update failed');
        }
        showToast(status === 'approved' ? '승인됨' : '거부됨', status === 'approved' ? 'success' : 'error');
        const data = getStatusData();
        if (data?.results?.[currentDetailIndex]) {
            data.results[currentDetailIndex].review_status = status;
            data.results[currentDetailIndex].review_note = note;
        }
        // Update local display
        const badge = document.querySelector(`#image-detail-modal .review-badge`);
        if (badge) {
            badge.className = `review-badge ${status}`;
            badge.textContent = status;
        }
        // Update gallery item
        const galleryItem = document.querySelector(`.gallery-item[data-index="${currentDetailIndex}"]`);
        if (galleryItem) {
            galleryItem.querySelectorAll('.review-badge').forEach(b => b.remove());
            if (status !== 'pending') {
                const overlay = galleryItem.querySelector('.gallery-overlay');
                if (overlay) overlay.insertAdjacentHTML('beforeend',
                    `<span class="review-badge ${status}">${status === 'approved' ? 'Approved' : 'Rejected'}</span>`);
            }
        }
        await loadRecentRuns();
    } catch (e) {
        console.error('Review failed:', e);
        showToast(`검수 저장 실패: ${e.message}`, 'error');
    }
}

async function saveCurrentReviewNote() {
    if (currentDetailIndex < 0) return;
    const data = getStatusData();
    const currentStatus = data?.results?.[currentDetailIndex]?.review_status || 'pending';
    const note = Utils.el('detail-review-note')?.value?.trim() || '';
    try {
        const resp = await fetch(`${CONFIG.API.REVIEW}/${currentDetailIndex}/review?project=${encodeURIComponent(AppState.currentProject)}&run_id=${encodeURIComponent(getReviewTargetRunId() || '')}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: currentStatus, note })
        });
        const body = await resp.json();
        if (!resp.ok || body.detail) {
            throw new Error(body.detail || 'Review note save failed');
        }
        if (data?.results?.[currentDetailIndex]) {
            data.results[currentDetailIndex].review_note = note;
        }
        showToast('메모 저장됨', 'success');
        await loadRecentRuns();
    } catch (e) {
        console.error('Review note save failed:', e);
        showToast(`메모 저장 실패: ${e.message}`, 'error');
    }
}

function getStatusData() { return AppState.lastStatusData; }

// --- Toast Notification ---
function showToast(message, type = 'info') {
    const container = Utils.el('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

// --- Cancel Batch ---
async function cancelBatch() {
    try {
        await fetch(CONFIG.API.CANCEL_BATCH, { method: 'POST' });
        showToast('생성 중지 요청됨', 'warning');
    } catch (e) { console.error('Cancel failed:', e); }
}

// --- Style Config Toggle ---
function toggleStyleConfig() {
    const panel = Utils.el('style-config-panel');
    if (!panel) return;
    panel.classList.toggle('collapsed');
    const icon = panel.querySelector('.collapse-icon');
    if (icon) {
        icon.setAttribute('data-lucide', panel.classList.contains('collapsed') ? 'chevron-right' : 'chevron-down');
        lucide.createIcons();
    }
}

// --- Gallery Counts ---
function updateGalleryCounts() {
    const grid = Utils.el(CONFIG.DOM.GALLERY);
    if (!grid) return;
    const items = grid.querySelectorAll('.gallery-item');
    const all = items.length;
    let thumb = 0, hero = 0, failed = 0;
    items.forEach(item => {
        if (item.classList.contains('thumb')) thumb++;
        if (item.classList.contains('hero')) hero++;
        if (item.classList.contains('timeout') || item.classList.contains('error')) failed++;
    });

    const setCount = (id, n) => { const el = Utils.el(id); if (el) el.textContent = n; };
    setCount('count-all', all);
    setCount('count-thumb', thumb);
    setCount('count-hero', hero);
    setCount('count-failed', failed);

    // Empty state
    const emptyEl = Utils.el('gallery-empty');
    const gridEl = Utils.el(CONFIG.DOM.GALLERY);
    if (emptyEl) emptyEl.style.display = all > 0 ? 'none' : 'flex';
    if (gridEl) gridEl.style.display = all > 0 ? '' : 'none';

    // Summary
    const summary = Utils.el('gallery-summary');
    if (summary && all > 0) {
        const approved = grid.querySelectorAll('.review-badge.approved').length;
        const rejected = grid.querySelectorAll('.review-badge.rejected').length;
        summary.textContent = `${all}장 | 승인 ${approved} | 거부 ${rejected}`;
    }

    // Show upload button only if images exist
    const uploadBtn = Utils.el('r2-upload-btn');
    if (uploadBtn) uploadBtn.style.display = all > 0 ? '' : 'none';
}
