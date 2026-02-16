import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../');
const COMFYUI_URL = 'http://127.0.0.1:8188';

// Configuration
const CONFIG = {
    thumb: { width: 512, height: 512, prefix: 'thumb' },
    hero: { width: 1024, height: 512, prefix: 'hero' }
};

async function main() {
    const args = process.argv.slice(2);
    const type = args.find(a => a.startsWith('--type='))?.split('=')[1] || 'thumb';
    const filterStr = args.find(a => a.startsWith('--filter='))?.split('=')[1] || '';
    const filters = filterStr ? filterStr.split(',') : [];

    console.log(`🚀 Starting generation for type: ${type}`);
    if (filters.length > 0) console.log(`🔍 Filters applied: ${filters.join(', ')}`);

    const workflowPath = path.join(PROJECT_ROOT, 'workflow_api.json');
    const csvPath = path.join(PROJECT_ROOT, 'kemi/prompts/thumbnail-prompts.csv');
    const outputDir = path.join(PROJECT_ROOT, 'outputs/kemi', filters.length > 0 ? 'tests' : type);

    if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

    const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf-8'));
    const csvContent = fs.readFileSync(csvPath, 'utf-8');
    const lines = csvContent.split('\n').filter(l => l.trim().length > 0);
    const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
    const rows = lines.slice(1);

    for (const row of rows) {
        // Simple CSV parse (doesn't handle commas in quotes perfectly, but enough for this)
        const columns = row.match(/("(?:[^"]|"")*"|[^,]+)/g).map(c => c.trim().replace(/"/g, ''));
        const promptData = {
            prompt: columns[0],
            desc_ko: columns[1],
            extra_positive: columns[2] || '',
            extra_negative: columns[3] || ''
        };

        // Apply filter if specified
        if (filters.length > 0) {
            const matches = filters.some(f => 
                promptData.prompt.toLowerCase().includes(f.toLowerCase()) || 
                promptData.desc_ko.toLowerCase().includes(f.toLowerCase())
            );
            if (!matches) continue;
        }

        const fileName = `${promptData.prompt.split(' ').slice(-1)[0]}-${type}.png`;
        const targetPath = path.join(outputDir, fileName);

        console.log(`🖌️ Generating: ${promptData.desc_ko} (${fileName})`);

        try {
            const currentWorkflow = JSON.parse(JSON.stringify(workflow));
            
            // Adjust dimensions
            currentWorkflow["5"].inputs.width = CONFIG[type].width;
            currentWorkflow["5"].inputs.height = CONFIG[type].height;

            // Adjust positive prompt
            const fullPositive = `cute kawaii flat illustration, bright pastel colors, soft rounded shapes, ${promptData.prompt}, ${promptData.extra_positive}`;
            currentWorkflow["6"].inputs.text = fullPositive;

            // Adjust negative prompt
            const fullNegative = `text, watermark, ugly, blurry, nsfw, dark, scary, realistic photo, ${promptData.extra_negative}`;
            currentWorkflow["7"].inputs.text = fullNegative;

            // Random seed
            currentWorkflow["13"].inputs.seed = Math.floor(Math.random() * 1000000);

            // Queue prompt
            const response = await fetch(`${COMFYUI_URL}/prompt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: currentWorkflow })
            });
            const { prompt_id } = await response.json();

            // Wait for completion
            let completed = false;
            while (!completed) {
                const historyResp = await fetch(`${COMFYUI_URL}/history/${prompt_id}`);
                const history = await historyResp.json();
                if (history[prompt_id]) {
                    completed = true;
                    const images = history[prompt_id].outputs["9"].images;
                    const imgInfo = images[0];
                    
                    // Download image
                    const imgUrl = `${COMFYUI_URL}/view?filename=${imgInfo.filename}&subfolder=${imgInfo.subfolder}&type=${imgInfo.type}`;
                    const imgData = await fetch(imgUrl);
                    const buffer = await imgData.arrayBuffer();
                    fs.writeFileSync(targetPath, Buffer.from(buffer));
                    console.log(`✅ Saved: ${targetPath}`);
                } else {
                    await new Promise(r => setTimeout(r, 1000));
                }
            }
        } catch (err) {
            console.error(`❌ Failed to generate ${promptData.desc_ko}:`, err.message);
        }
    }

    console.log('✨ All tasks completed.');
}

main().catch(console.error);
