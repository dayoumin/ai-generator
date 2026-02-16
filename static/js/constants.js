const CONFIG = {
    APP_NAME: "Kemi AI Studio",
    API: {
        START_BATCH: '/api/batch/start',
        STATUS: '/api/batch/status',
        PROMPT_FILES: '/api/prompts/files',
        PROMPT_CONTENT: '/api/prompts/content'
    },
    DEFAULTS: {
        AR: "16:9",
        STEPS: 20,
        REPEAT: 1,
        AUTO_CLEAR: false,
        SOUND: true
    },
    STYLE_PRESETS: {
        "custom": { p: "", n: "" },
        "3d": {
            p: "3d render, cute character, blind box style, clay texture, blender, soft lighting, 8k, colorful, ambient occlusion",
            n: "2d, flat, sketch, watermark, text, low quality, ugly, noise, blurry"
        },
        "photo": {
            p: "cinematic photo, highly detailed, 8k, depth of field, natural lighting, shot on 35mm, realistic texture, hdr",
            n: "drawing, painting, illustration, anime, cartoon, 3d render, watermark, text"
        },
        "anime": {
            p: "anime style, flat color, cel shading, vibrant, studio ghibli style, clean lines, high quality illustration",
            n: "3d, photorealistic, noise, grainy, watermark, text, ugly, messy lines"
        },
        "icon": {
            p: "vector icon, minimal, flat, white background, app icon style, simple shapes, ui element, svg style",
            n: "complex, detailed, photo, 3d, shadow, gradient, noise"
        }
    },
    MODALS: {
        CONFIRM: 'confirm-modal',
        MAPPING: 'mapping-modal',
        HELP: 'help-modal'
    },
    DOM: {
        START_BTN: 'start-batch-btn',
        FAB_BTN: 'fab-generate',
        GALLERY: 'gallery-grid',
        LOGS: 'log-container',
        PROMPT_FILE_SELECTOR: 'prompt-file-selector',
        SELECTION_COUNT: 'selection-count',
        TOTAL_TASKS: 'total-count',
        PROGRESS_BAR: 'main-progress-bar',
        PROGRESS_TEXT: 'progress-percent',
        STATUS_TEXT: 'current-status',
        PREVIEW: 'live-preview-display',
        SETTINGS: {
            TOOLTIPS: 'setting-tooltips',
            STEPS: 'setting-steps',
            REPEAT: 'setting-repeat',
            AR: 'setting-ar',
            AUTOCLEAR: 'setting-autoclear',
            SOUND: 'setting-sound'
        }
    }
};

const Utils = {
    // Utility to get element safely
    el: (id) => document.getElementById(id),

    // Checkbox helper
    isChecked: (id) => {
        const el = document.getElementById(id);
        return el ? el.checked : false;
    },

    // Value helper
    val: (id) => {
        const el = document.getElementById(id);
        return el ? el.value : '';
    },

    // Set Value helper
    setVal: (id, val) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.type === 'checkbox') el.checked = !!val;
        else el.value = val;
    }
};
