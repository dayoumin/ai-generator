// --- Initialization ---
const AppState = {
    currentPrompts: [],
    lastLogCount: 0,
    lastResultCount: 0,
    lastStatusData: null
};

document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    initTabs();
    initEventListeners();
    initGalleryFilters();
    loadPromptFiles();
    loadAppConfig();
    // loadConfig removed — was dead code (function never existed)
    checkComfyUIHealth();
    setInterval(checkComfyUIHealth, 30000);
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
        document.querySelector('[data-tab="prompts"]')?.click();
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
    Utils.el(CONFIG.DOM.PROMPT_FILE_SELECTOR)?.addEventListener('change', (e) => loadPromptContent(e.target.value));

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

    // Inputs & Selects
    Utils.el('style-preset')?.addEventListener('change', applyPreset);
    Utils.el('steps')?.addEventListener('input', (e) => Utils.el('steps-val').innerText = e.target.value);
    Utils.el('toggle-all-checkbox')?.addEventListener('change', (e) => toggleAllPrompts(e.target));

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
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            item.classList.add('active');
            document.getElementById(`${item.dataset.tab}-tab`).classList.add('active');
        }
    });
}

// --- ComfyUI Health Check ---
async function checkComfyUIHealth() {
    const dot = document.querySelector('.status-indicator .dot');
    const label = document.querySelector('.status-indicator span:last-child');
    try {
        const resp = await fetch(CONFIG.API.HEALTH);
        const data = await resp.json();
        if (data.comfyui) {
            dot?.classList.add('green');
            dot?.classList.remove('red');
            if (label) label.textContent = 'ComfyUI Live';
        } else {
            dot?.classList.remove('green');
            dot?.classList.add('red');
            if (label) label.textContent = 'ComfyUI Offline';
        }
    } catch {
        dot?.classList.remove('green');
        dot?.classList.add('red');
        if (label) label.textContent = 'Server Error';
    }
}

// --- Check Existing Batch on Load ---
async function checkExistingBatch() {
    try {
        const resp = await fetch(CONFIG.API.STATUS);
        const data = await resp.json();
        if (data.total > 0 || data.is_running || data.finish_status) {
            updateUI(data);
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
        const resp = await fetch(CONFIG.API.UPLOAD_R2, { method: 'POST' });
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

// --- Prompt Management ---
async function loadPromptFiles() {
    try {
        const resp = await fetch(CONFIG.API.PROMPT_FILES);
        const data = await resp.json();
        const select = document.getElementById(CONFIG.DOM.PROMPT_FILE_SELECTOR);
        if (!select || !data.files) return;
        select.innerHTML = '';
        data.files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f; opt.innerText = f;
            if (f === 'thumbnail-prompts.csv') opt.selected = true;
            select.appendChild(opt);
        });
        loadPromptContent(select.value);
    } catch (e) { console.error("Failed to load files", e); }
}

async function loadPromptContent(filename) {
    try {
        const resp = await fetch(`${CONFIG.API.PROMPT_CONTENT}?filename=${filename}`);
        const data = await resp.json();
        if (data.prompts) {
            AppState.currentPrompts = data.prompts;
            renderPromptTable(AppState.currentPrompts);
        }
    } catch (e) { console.error("Failed to load content", e); }
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

function updateSelectionCounts() {
    const checked = document.querySelectorAll('.prompt-checkbox:checked').length;
    const selEl = document.getElementById(CONFIG.DOM.SELECTION_COUNT);
    if (selEl) selEl.innerText = `${checked}개 선택됨`;
    const btn = document.getElementById(CONFIG.DOM.FAB_BTN);
    if (btn) btn.innerHTML = `<i data-lucide="play"></i> 선택 항목 생성 (${checked})`;
    lucide.createIcons();
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
function openConfirmModal() {
    const checked = document.querySelectorAll('.prompt-checkbox:checked').length;
    if (checked === 0) return showToast("프롬프트를 1개 이상 선택하세요", "error");
    const repeat = parseInt(document.getElementById('batch-count').value) || 1;
    const total = checked * 2 * repeat;
    const timeEst = Math.ceil(total * 12 / 60);
    const modal = document.getElementById(CONFIG.MODALS.CONFIRM);
    const p = modal.querySelector('p');
    if (p) p.innerHTML = `<strong>${total}장</strong>의 이미지를 생성합니다<br><span style="font-size:0.9em; opacity:0.8">(${checked}개 프롬프트 x ${repeat} 변형 x 2 크기)</span>`;
    const sub = modal.querySelector('.sub-text');
    if (sub) sub.innerText = `예상 소요 시간: 약 ${timeEst}분`;
    modal.style.display = 'flex';
}

function closeConfirmModal() { document.getElementById(CONFIG.MODALS.CONFIRM).style.display = 'none'; }

async function confirmStartBatch() {
    closeConfirmModal();
    if (Utils.isChecked(CONFIG.DOM.SETTINGS.AUTOCLEAR)) {
        const gal = Utils.el(CONFIG.DOM.GALLERY); if (gal) gal.innerHTML = '';
        const logs = Utils.el(CONFIG.DOM.LOGS); if (logs) logs.innerHTML = '';
        AppState.lastLogCount = 0;
        AppState.lastResultCount = 0;
    }
    const selectedIdxs = Array.from(document.querySelectorAll('.prompt-checkbox:checked')).map(cb => parseInt(cb.dataset.idx));
    if (selectedIdxs.length === 0) return;
    const selectedPrompts = AppState.currentPrompts.filter((_, i) => selectedIdxs.includes(i));
    setBusy(true);
    try {
        await fetch(CONFIG.API.START_BATCH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompts: selectedPrompts,
                types: ["thumb", "hero"],
                style_prompt: document.getElementById('style-prompt').value,
                negative_prompt: document.getElementById('negative-prompt').value,
                global_aspect_ratio: document.getElementById('default-ar').value,
                batch_count: parseInt(document.getElementById('batch-count').value),
                steps: parseInt(document.getElementById('steps').value)
            })
        });
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
    let errorCount = 0;
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(CONFIG.API.STATUS);
            const data = await resp.json();
            errorCount = 0;
            updateUI(data);

            if (!data.is_running && data.finish_status) {
                clearInterval(interval);
                setBusy(false);
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
                setBusy(false);
                showToast("서버 연결이 끊어졌습니다", "error");
            }
        }
    }, 1000);
}

// --- UI Update ---
function updateUI(data) {
    AppState.lastStatusData = data;

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
                        <span class="badge ${item.type}">${item.type}</span>
                        ${item.review_status && item.review_status !== 'pending' ? `<span class="review-badge ${item.review_status}">${item.review_status === 'approved' ? 'Approved' : 'Rejected'}</span>` : ''}
                    </div>`;
            } else {
                div.innerHTML = `
                    <div class="gallery-placeholder ${item.status}">
                        <span>${item.status === 'timeout' ? 'Timed Out' : 'Failed'}</span>
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
        <div><strong>Status:</strong> <span class="badge ${item.status}">${item.status}</span></div>
        <div><strong>Type:</strong> ${item.type} (${item.width}x${item.height})</div>
        <div><strong>Duration:</strong> ${item.duration ? item.duration.toFixed(1) + 's' : 'N/A'}</div>
        <div><strong>Review:</strong> <span class="review-badge ${item.review_status || 'pending'}">${item.review_status || 'pending'}</span></div>
    `;

    Utils.el('detail-prompt-text').textContent = item.positive || item.prompt || '';
    Utils.el('detail-negative-text').textContent = item.negative || '';

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
        await fetch(`${CONFIG.API.REVIEW}/${currentDetailIndex}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        showToast(status === 'approved' ? '승인됨' : '거부됨', status === 'approved' ? 'success' : 'error');
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
    } catch (e) { console.error('Review failed:', e); }
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
