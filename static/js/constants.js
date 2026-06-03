const CONFIG = {
    APP_NAME: "Kemi AI Studio",
    API: {
        PROJECTS: '/api/projects',
        START_BATCH: '/api/batch/start',
        VALIDATE_GENERATION: '/api/generation/validate',
        CANCEL_BATCH: '/api/batch/cancel',
        RUNS: '/api/runs',
        RUN_CODEX_HANDOFF: '/api/runs', // + /{runId}/codex-handoff
        STATUS: '/api/batch/status',
        HEALTH: '/api/health',
        CODEX_IMPORT: '/api/codex-import',
        UPSCALE: '/api/upscale',
        UPSCALE_JOBS: '/api/upscale/jobs',
        UPSCALE_CLEANUP: '/api/upscale/cleanup',
        UPSCALE_UPLOAD: '/api/upscale/upload',
        UPSCALE_UPLOAD_JOBS: '/api/upscale/upload/jobs',
        UPLOAD_R2: '/api/upload',
        REVIEW: '/api/results',  // + /{index}/review
        PROMPT_FILES: '/api/prompts/files',
        PROMPT_CONTENT: '/api/prompts/content',
        REFERENCE_ASSETS: '/api/reference-assets',
        REFERENCE_ASSET_UPLOAD: '/api/reference-assets/upload',
        TEMPLATES: '/api/templates'
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
        },
        "kemi-everyday-webtoon": {
            p: "Korean mobile webtoon inspired everyday scene, emotionally relatable candid moment, natural facial expression, small real-life gesture, warm but restrained color palette, soft clean linework, semi-flat editorial illustration, simple lived-in background, mobile card friendly composition, no text in image",
            n: "generic AI illustration, plastic 3d render, overly cute mascot, exaggerated anime face, fantasy scene, luxury ad mood, perfect stock-photo smile, text, letters, logo, watermark, phone frame, app screenshot, crowded background, distorted hands"
        },
        "kemi-soft-snapshot": {
            p: "soft illustrated lifestyle snapshot, realistic posture and spacing, quiet relatable emotion, gentle natural light, subtle texture, approachable Korean app visual mood, modern casual clothing, simple background, crop-safe composition, no text in image",
            n: "photorealistic celebrity, fashion editorial pose, brand logo, written text, speech bubble, harsh neon, over-saturated colors, glossy 3d, childish sticker, distorted anatomy, busy background"
        },
        "kemi-result-mood": {
            p: "shareable test result artwork, human-centered symbolic scene, reflective but optimistic mood, clear emotional metaphor, soft natural expression, refined mobile illustration, safe empty space for UI overlay, balanced composition, no text in image",
            n: "dramatic fantasy, tarot card, horoscope poster, generic business illustration, text, letters, logo, watermark, crowded symbols, harsh contrast, distorted anatomy, childish mascot"
        }
    },
    MODALS: {
        CONFIRM: 'confirm-modal',
        MAPPING: 'mapping-modal',
        HELP: 'help-modal',
        IMAGE_DETAIL: 'image-detail-modal'
    },
    DOM: {
        APP_TITLE: 'app-title',
        PROJECT_BREADCRUMB: 'project-breadcrumb',
        WELCOME_PROJECT_BADGE: 'welcome-project-badge',
        WELCOME_TITLE: 'welcome-title',
        WELCOME_DESCRIPTION: 'welcome-description',
        WELCOME_CHECKLIST: 'welcome-checklist',
        START_BTN: 'start-batch-btn',
        CANCEL_BTN: 'cancel-batch-btn',
        FAB_BTN: 'fab-generate',
        GALLERY: 'gallery-grid',
        GALLERY_EMPTY: 'gallery-empty',
        GALLERY_SUMMARY: 'gallery-summary',
        LOGS: 'log-container',
        PROJECT_SELECTOR: 'project-selector',
        ACTIVE_PROVIDER_CHIP: 'active-provider-chip',
        ACTIVE_UPSCALE_CHIP: 'active-upscale-chip',
        PROVIDER_STATUS_DOT: 'provider-status-dot',
        PROVIDER_STATUS_LABEL: 'provider-status-label',
        PROVIDER_STATUS_DETAIL: 'provider-status-detail',
        UPSCALE_STATUS_DOT: 'upscale-status-dot',
        UPSCALE_STATUS_LABEL: 'upscale-status-label',
        UPSCALE_STATUS_DETAIL: 'upscale-status-detail',
        PROMPT_FILE_SELECTOR: 'prompt-file-selector',
        REFERENCE_ROOT: 'reference-assets-root',
        REFERENCE_STATUS_GRID: 'reference-status-grid',
        REFERENCE_LIBRARY_COUNT: 'reference-library-count',
        REFERENCE_TEMP_COUNT: 'reference-temp-count',
        REFERENCE_DEFINITIONS: 'reference-definition-files',
        REFERENCE_GRID: 'reference-assets-grid',
        REFERENCE_EMPTY: 'reference-assets-empty',
        REFERENCE_SELECTION_COUNT: 'reference-selection-count',
        REFERENCE_SELECTION_PREVIEW: 'reference-selection-preview',
        REFERENCE_CAPABILITY_NOTE: 'reference-capability-note',
        REFERENCE_TARGET_DIR: 'reference-target-dir',
        REFERENCE_PRESET_GROUP: 'reference-preset-group',
        REFERENCE_UPLOAD_INPUT: 'reference-upload-input',
        REFERENCE_UPLOAD_BTN: 'upload-reference-btn',
        TEMPLATE_NAME: 'scene-template-name',
        TEMPLATE_COMPOSITION: 'scene-template-composition',
        TEMPLATE_DESCRIPTION: 'scene-template-description',
        TEMPLATE_LIST: 'scene-template-list',
        TEMPLATE_EMPTY: 'scene-template-empty',
        TEMPLATE_SAVE_BTN: 'save-scene-template-btn',
        TEMPLATE_APPLY_BTN: 'apply-scene-template-btn',
        TEMPLATE_CLEAR_BTN: 'clear-scene-template-btn',
        TEMPLATE_DELETE_BTN: 'delete-scene-template-btn',
        GENERATION_MODE: 'generation-mode',
        PROVIDER_SELECTOR: 'provider-selector',
        PROVIDER_NOTE: 'provider-note',
        OPERATOR_MODE: 'operator-mode',
        OPERATOR_NOTE: 'operator-note',
        GENERATION_MODE_NOTE: 'generation-mode-note',
        CODEX_HANDOFF_PANEL: 'codex-handoff-panel',
        CODEX_HANDOFF_SUMMARY: 'codex-handoff-summary',
        CODEX_HANDOFF_TEXT: 'codex-handoff-text',
        CODEX_HANDOFF_COPY_BTN: 'codex-handoff-copy-btn',
        REFRESH_PREFLIGHT_BTN: 'refresh-preflight-btn',
        SCENE_SITUATION: 'scene-situation',
        SCENE_INTERACTION: 'scene-interaction',
        SCENE_BACKGROUND: 'scene-background',
        SCENE_LOCATION: 'scene-location',
        SCENE_LIGHTING: 'scene-lighting',
        PREFLIGHT_PANEL: 'preflight-panel',
        PREFLIGHT_SUMMARY: 'preflight-summary',
        PREFLIGHT_ERRORS: 'preflight-errors',
        PREFLIGHT_WARNINGS: 'preflight-warnings',
        RUN_COMPARE_PANEL: 'run-compare-panel',
        RUN_VIEW_STATE: 'run-view-state',
        RUN_CODEX_HANDOFF_PREVIEW: 'run-codex-handoff-preview',
        RUN_COMPARE_GRID: 'run-compare-grid',
        RUN_COMPARE_DIFF: 'run-compare-diff',
        RUN_RETRY_SUGGESTION: 'run-retry-suggestion',
        RUN_RETRY_LINEAGE: 'run-retry-lineage',
        OUTPUTS_ADVANCED_TOGGLE: 'toggle-outputs-advanced-btn',
        OUTPUTS_ADVANCED_SECTION: 'outputs-advanced-section',
        SELECTION_COUNT: 'selection-count',
        TOTAL_TASKS: 'total-count',
        PROGRESS_BAR: 'main-progress-bar',
        PROGRESS_TEXT: 'progress-percent',
        STATUS_TEXT: 'current-status',
        PREVIEW: 'live-preview-display',
        WELCOME: 'welcome-state',
        BATCH_STATE: 'batch-state',
        TOAST: 'toast-container',
        UPLOAD_BTN: 'r2-upload-btn',
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
