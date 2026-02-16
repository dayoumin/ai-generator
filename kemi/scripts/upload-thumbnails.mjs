import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import dotenv from 'dotenv';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../');

const {
  CLOUDFLARE_ACCOUNT_ID,
  R2_ACCESS_KEY_ID,
  R2_SECRET_ACCESS_KEY,
  R2_BUCKET_NAME
} = process.env;

async function main() {
  const isDryRun = process.argv.includes('--dry-run');

  if (!isDryRun && (!R2_ACCESS_KEY_ID || !R2_SECRET_ACCESS_KEY)) {
    console.error('❌ Missing R2 credentials in .env');
    process.exit(1);
  }

  console.log(`🚀 Starting ${isDryRun ? 'DRY RUN ' : ''}upload to R2...`);

  const s3 = new S3Client({
    region: "auto",
    endpoint: `https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: R2_ACCESS_KEY_ID,
      secretAccessKey: R2_SECRET_ACCESS_KEY,
    },
  });

  const folders = ['thumb', 'hero'];
  const mappings = {};

  for (const folder of folders) {
    const dirPath = path.join(PROJECT_ROOT, 'outputs/kemi', folder);
    if (!fs.existsSync(dirPath)) continue;

    const files = fs.readdirSync(dirPath).filter(f => f.endsWith('.png') || f.endsWith('.webp'));

    for (const file of files) {
      const filePath = path.join(dirPath, file);
      const key = `kemi/${folder}/${file}`;
      const url = `https://${R2_BUCKET_NAME}.r2.dev/${key}`;

      console.log(`📤 Uploading: ${file} -> ${key}`);

      if (!isDryRun) {
        const body = fs.readFileSync(filePath);
        await s3.send(new PutObjectCommand({
          Bucket: R2_BUCKET_NAME,
          Key: key,
          Body: body,
          ContentType: 'image/webp'
        }));
      }

      mappings[file] = url;
    }
  }

  console.log('\n🔗 URL Mappings (Add to config.ts):');
  console.log(JSON.stringify(mappings, null, 2));
  console.log(`\n✨ Total ${Object.keys(mappings).length} files processed.`);
}

main().catch(console.error);
