import { execFileSync } from 'node:child_process';
import { copyFile, mkdir, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const frontendAssets = ['index.html', 'styles.css', 'app.js'];
const backendFiles = await readdir(new URL('backend/', root));
const scripts = [
  'frontend/app.js',
  ...backendFiles.filter((name) => name.endsWith('.js')).map((name) => `backend/${name}`),
];
for (const script of scripts) {
  execFileSync(process.execPath, ['--check', fileURLToPath(new URL(script, root))], { stdio: 'inherit' });
}

const output = new URL('dist/', root);
await mkdir(output, { recursive: true });
for (const asset of frontendAssets) {
  await copyFile(new URL(`frontend/${asset}`, root), new URL(asset, output));
}
