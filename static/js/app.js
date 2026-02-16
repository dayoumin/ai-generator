
// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    initTabs();

    // Bind global events
    window.openHelpModal = openHelpModal;
    window.closeHelpModal = closeHelpModal;
    window.openConfirmModal = openConfirmModal;
    window.closeConfirmModal = closeConfirmModal;
    window.confirmStartBatch = confirmStartBatch;
    window.loadAppConfig = loadAppConfig;
    window.saveAppConfig = saveAppConfig;
    window.toggleCustomPromptForm = toggleCustomPromptForm;
    window.clearPromptList = clearPromptList;
    window.addCustomPrompt = addCustomPrompt;
    window.applyPreset = applyPreset;
    window.downloadTemplate = downloadTemplate;
    window.toggleAllPrompts = toggleAllPrompts;
    window.clearLogs = () => document.getElementById(CONFIG.DOM.LOGS).innerHTML = '';
    window.closeModal = () => document.getElementById(CONFIG.MODALS.MAPPING).style.display = 'none';

    // Init Data
    loadPromptFiles();
    loadAppConfig();
    try { loadConfig(); } catch (e) { }
    pollStatus();
});

// --- Tab Management ---
function initTabs() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.onclick = (e) => {
            e.preventDefault();
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

            item.classList.add('active');
            document.getElementById(`${item.dataset.tab}-tab`).classList.add('active');
        };
    });
}

// --- Global Data ---
let currentPrompts = [];


// --- UI Helpers ---
function openHelpModal() {
    document.getElementById(CONFIG.MODALS.HELP).style.display = 'flex';
}

function closeHelpModal() {
    document.getElementById(CONFIG.MODALS.HELP).style.display = 'none';
}

function downloadTemplate() {
    const csvContent = "\uFEFFdesc_ko,prompt,aspect_ratio,seed,extra_positive,extra_negative\n예시_용,A majestic blue dragon,16:9,,highly detailed,watermark";
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "kemi_prompt_template.csv");
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// --- Settings & Persistence ---
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
        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, ctx.currentTime);
        osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.15);

        gain.gain.setValueAtTime(0.1, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.1, ctx.currentTime + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

        osc.start();
        osc.stop(ctx.currentTime + 0.6);
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

    // Sync active AR selector
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

            // Apply Defaults to Main UI
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

        select.innerHTML = '';
        data.files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.innerText = f;
            if (f === 'thumbnail-prompts.csv') opt.selected = true;
            select.appendChild(opt);
        });

        loadPromptContent(select.value);
        select.onchange = () => loadPromptContent(select.value);
    } catch (e) {
        console.error("Failed to load files", e);
    }
}

async function loadPromptContent(filename) {
    try {
        const resp = await fetch(`${CONFIG.API.PROMPT_CONTENT}?filename=${filename}`);
        const data = await resp.json();
        if (data.prompts) {
            currentPrompts = data.prompts;
            renderPromptTable(currentPrompts);
        }
    } catch (e) {
        console.error("Failed to load content", e);
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

    document.querySelectorAll('.prompt-checkbox').forEach(cb => {
        cb.onchange = updateSelectionCounts;
    });
}

function updateSelectionCounts() {
    const total = document.querySelectorAll('.prompt-checkbox').length;
    const checked = document.querySelectorAll('.prompt-checkbox:checked').length;

    const selEl = document.getElementById(CONFIG.DOM.SELECTION_COUNT);
    if (selEl) selEl.innerText = `${checked} Selected`;

    const btn = document.getElementById(CONFIG.DOM.FAB_BTN);
    if (btn) btn.innerText = `Generate Selected (${checked})`;
}

function toggleAllPrompts(source) {
    const checkboxes = document.querySelectorAll('.prompt-checkbox');
    checkboxes.forEach(cb => cb.checked = source.checked);
    updateSelectionCounts();
}

// --- Custom Prompts ---
function toggleCustomPromptForm() {
    const form = document.getElementById('custom-prompt-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function clearPromptList() {
    if (confirm("전체 리스트를 삭제하시겠습니까?")) {
        currentPrompts = [];
        renderPromptTable(currentPrompts);
    }
}

function addCustomPrompt() {
    const desc = document.getElementById('custom-desc').value.trim();
    const promptText = document.getElementById('custom-prompt').value.trim();
    const ar = document.getElementById('custom-ar').value;

    if (!desc || !promptText) {
        alert("Please enter both Description and Prompt");
        return;
    }

    const newPrompt = {
        desc_ko: desc,
        prompt: promptText,
        aspect_ratio: ar,
        is_manual: true
    };

    currentPrompts.unshift(newPrompt);
    renderPromptTable(currentPrompts);

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
    if (checked === 0) return alert("Please select at least one prompt!");

    const repeat = parseInt(document.getElementById('batch-count').value) || 1;
    const total = checked * 2 * repeat;
    const timeEst = Math.ceil(total * 4 / 60);

    const modal = document.getElementById(CONFIG.MODALS.CONFIRM);
    const p = modal.querySelector('p');
    if (p) p.innerHTML = `Generate <strong>${total} images</strong>?<br><span style="font-size:0.9em; opacity:0.8">(${checked} prompts × ${repeat} variations × 2 sizes)</span>`;

    const sub = modal.querySelector('.sub-text');
    if (sub) sub.innerText = `Estimated time: ~${timeEst} minutes on RTX 5080`;

    modal.style.display = 'flex';
}

function closeConfirmModal() {
    document.getElementById(CONFIG.MODALS.CONFIRM).style.display = 'none';
}

async function confirmStartBatch() {
    closeConfirmModal();

    // Auto-Clear Logic
    if (Utils.isChecked(CONFIG.DOM.SETTINGS.AUTOCLEAR)) {
        const gal = document.getElementById(CONFIG.DOM.GALLERY);
        if (gal) gal.innerHTML = '';
        const logs = document.getElementById(CONFIG.DOM.LOGS);
        if (logs) logs.innerHTML = '';
    }

    const selectedIdxs = Array.from(document.querySelectorAll('.prompt-checkbox:checked')).map(cb => parseInt(cb.dataset.idx));
    if (selectedIdxs.length === 0) return;

    const selectedPrompts = currentPrompts.filter((_, i) => selectedIdxs.includes(i));

    const startBtn = document.getElementById(CONFIG.DOM.START_BTN);
    const fabBtn = document.getElementById(CONFIG.DOM.FAB_BTN);
    const statusEl = document.getElementById(CONFIG.DOM.STATUS_TEXT);

    const setBusy = (isBusy) => {
        if (startBtn) {
            startBtn.disabled = isBusy;
            startBtn.innerHTML = isBusy ? '<i class="spinner"></i> Generating...' : '<i data-lucide="play"></i> Start Batch';
        }
        if (fabBtn) {
            fabBtn.disabled = isBusy;
            fabBtn.innerHTML = isBusy ? '<i class="spinner"></i> Generating...' : '<i data-lucide="play"></i> Generate Selected';
        }
        if (!isBusy) lucide.createIcons();
    };

    setBusy(true);
    if (statusEl) statusEl.innerText = "🚀 Starting...";

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
        alert("Failed to start: " + e.message);
        setBusy(false);
    }
}

async function pollStatus() {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(CONFIG.API.STATUS);
            const data = await resp.json();

            updateUI(data);

            const isStopped = !data.is_running;
            const isFinished = data.current_item === 'Finished';
            const hasErrors = data.logs.some(l => l.includes('❌') || l.includes('⚠️'));

            if (isStopped && (isFinished || hasErrors || data.completed > 0)) {
                clearInterval(interval);

                const startBtn = document.getElementById(CONFIG.DOM.START_BTN);
                const fabBtn = document.getElementById(CONFIG.DOM.FAB_BTN);
                if (startBtn) {
                    startBtn.disabled = false;
                    startBtn.innerHTML = '<i data-lucide="play"></i> Start Batch';
                }
                if (fabBtn) {
                    fabBtn.disabled = false;
                    fabBtn.innerHTML = '<i data-lucide="play"></i> Generate Selected';
                }
                lucide.createIcons();

                if (isFinished && !hasErrors) {
                    if (Utils.isChecked(CONFIG.DOM.SETTINGS.SOUND)) playNotificationSound();
                } else if (hasErrors && !data.is_running) {
                    const statusEl = document.getElementById(CONFIG.DOM.STATUS_TEXT);
                    if (statusEl) statusEl.innerHTML = '<span style="color:var(--danger)">⚠️ Generation Stopped with Errors</span>';
                }
            }
        } catch (e) { console.error("Poll Error:", e); }
    }, 1000);
}

function updateUI(data) {
    const totalEl = document.getElementById(CONFIG.DOM.TOTAL_TASKS);
    if (totalEl) totalEl.innerText = `${data.completed} / ${data.total}`;

    const percent = data.total > 0 ? (data.completed / data.total * 100) : 0;
    const progEl = document.getElementById(CONFIG.DOM.PROGRESS_TEXT);
    if (progEl) progEl.innerText = `${Math.round(percent)}%`;

    const barEl = document.getElementById(CONFIG.DOM.PROGRESS_BAR);
    if (barEl) barEl.style.width = `${percent}%`;

    const statusEl = document.getElementById(CONFIG.DOM.STATUS_TEXT);
    const hasErrorLog = data.logs.some(log => log.includes('❌') || log.includes('⚠️'));

    if (hasErrorLog && !data.is_running) {
        if (statusEl) statusEl.innerHTML = '<span style="color:var(--danger)">⚠️ Error Occurred</span>';
    } else {
        if (statusEl) statusEl.innerText = data.current_item || 'Idle';
    }

    const logContainer = document.getElementById(CONFIG.DOM.LOGS);
    if (logContainer) {
        logContainer.innerHTML = data.logs.map(log => {
            const isError = log.includes('❌') || log.includes('⚠️');
            return `<div class="log-entry ${isError ? 'error' : ''}">${log}</div>`;
        }).join('');
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    if (data.results.length > 0) {
        const last = data.results[data.results.length - 1];
        const previewDisplay = document.getElementById(CONFIG.DOM.PREVIEW);
        if (previewDisplay) previewDisplay.innerHTML = `<img src="${last.url}" class="fade-in">`;

        const gallery = document.getElementById(CONFIG.DOM.GALLERY);
        if (gallery && data.results.length > gallery.children.length) {
            const newItems = data.results.slice(gallery.children.length);
            newItems.forEach(item => {
                const div = document.createElement('div');
                div.className = `gallery-item ${item.type}`;
                div.innerHTML = `<img src="${item.url}" title="${item.name} (${item.type})">`;
                gallery.appendChild(div);
            });
        }
    }
}
