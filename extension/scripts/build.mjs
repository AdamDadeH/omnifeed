import * as esbuild from 'esbuild';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// Parse CLI arguments
const args = process.argv.slice(2);
const watch = args.includes('--watch');
const browser = args.includes('--browser')
  ? args[args.indexOf('--browser') + 1]
  : 'chrome';

if (!['chrome', 'firefox'].includes(browser)) {
  console.error('Invalid browser. Use --browser chrome or --browser firefox');
  process.exit(1);
}

const outdir = path.join(ROOT, 'dist', browser);

// Ensure output directory exists
fs.mkdirSync(outdir, { recursive: true });

// Copy manifest
function copyManifest() {
  const manifestSrc = path.join(ROOT, 'manifest', `${browser}.manifest.json`);
  const manifestDest = path.join(outdir, 'manifest.json');

  if (fs.existsSync(manifestSrc)) {
    fs.copyFileSync(manifestSrc, manifestDest);
    console.log(`Copied ${browser} manifest`);
  } else {
    console.warn(`Manifest not found: ${manifestSrc}`);
  }
}

// Copy static assets
function copyAssets() {
  const publicDir = path.join(ROOT, 'public');
  if (fs.existsSync(publicDir)) {
    copyDir(publicDir, outdir);
    console.log('Copied public assets');
  }
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

// Build configuration
const commonConfig = {
  bundle: true,
  minify: !watch,
  sourcemap: watch ? 'inline' : false,
  target: 'es2020',
  define: {
    'process.env.BROWSER': JSON.stringify(browser),
    'process.env.NODE_ENV': JSON.stringify(watch ? 'development' : 'production'),
  },
  loader: {
    '.tsx': 'tsx',
    '.ts': 'ts',
  },
};

// Entry points
const entryPoints = [
  { in: 'src/content/main.ts', out: 'content/main' },
  { in: 'src/background/service-worker.ts', out: 'background/service-worker' },
  { in: 'src/popup/index.tsx', out: 'popup/index' },
];

// Create popup HTML
function createPopupHtml() {
  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OmniFeed</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div id="root"></div>
  <script src="index.js"></script>
</body>
</html>`;

  const popupDir = path.join(outdir, 'popup');
  fs.mkdirSync(popupDir, { recursive: true });
  fs.writeFileSync(path.join(popupDir, 'index.html'), html);
}

// Create basic styles
function createStyles() {
  const css = `
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: #1a1a1a;
  background: #fff;
  width: 360px;
  min-height: 400px;
}

.popup-container {
  padding: 16px;
}

.popup-nav {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  border-bottom: 1px solid #e5e5e5;
  padding-bottom: 8px;
}

.popup-nav button {
  background: none;
  border: none;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
  color: #666;
}

.popup-nav button.active {
  background: #f0f0f0;
  color: #1a1a1a;
  font-weight: 500;
}

.popup-nav button:hover {
  background: #f5f5f5;
}

.content-preview {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f8f8;
  border-radius: 8px;
}

.content-preview .thumbnail {
  width: 80px;
  height: 45px;
  object-fit: cover;
  border-radius: 4px;
}

.content-preview .title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.content-preview .creator {
  font-size: 12px;
  color: #666;
}

.content-preview .platform {
  font-size: 11px;
  color: #999;
}

.score-section {
  margin-bottom: 16px;
}

.score-section label {
  display: block;
  font-weight: 500;
  margin-bottom: 8px;
}

.score-slider {
  width: 100%;
  margin-bottom: 4px;
}

.score-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #999;
}

.dimension-section {
  margin-bottom: 16px;
}

.dimension-section label {
  display: block;
  font-weight: 500;
  margin-bottom: 8px;
}

.option-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option-button {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 16px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.option-button:hover {
  border-color: #999;
}

.option-button.selected {
  background: #e8f4ff;
  border-color: #0066cc;
  color: #0066cc;
}

.submit-button {
  width: 100%;
  padding: 12px;
  background: #0066cc;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  margin-top: 16px;
}

.submit-button:hover {
  background: #0052a3;
}

.submit-button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.form-field {
  margin-bottom: 12px;
}

.form-field label {
  display: block;
  font-weight: 500;
  margin-bottom: 4px;
  font-size: 13px;
}

.form-field input,
.form-field select,
.form-field textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.form-field input:focus,
.form-field select:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #0066cc;
}

.error-message {
  color: #cc0000;
  text-align: center;
  padding: 20px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #f0f0f0;
  border-top-color: #0066cc;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.settings-section {
  margin-bottom: 20px;
}

.settings-section h3 {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.setting-row label {
  font-size: 14px;
}

.toggle {
  position: relative;
  width: 44px;
  height: 24px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  border-radius: 24px;
  transition: 0.2s;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle input:checked + .toggle-slider {
  background-color: #0066cc;
}

.toggle input:checked + .toggle-slider:before {
  transform: translateX(20px);
}
`;

  const popupDir = path.join(outdir, 'popup');
  fs.mkdirSync(popupDir, { recursive: true });
  fs.writeFileSync(path.join(popupDir, 'styles.css'), css);
}

async function build() {
  console.log(`Building for ${browser}...`);

  // Copy static files
  copyManifest();
  copyAssets();
  createPopupHtml();
  createStyles();

  // Filter entry points that exist
  const existingEntryPoints = entryPoints.filter(ep => {
    const fullPath = path.join(ROOT, ep.in);
    return fs.existsSync(fullPath);
  });

  if (existingEntryPoints.length === 0) {
    console.log('No entry points found yet. Skipping esbuild.');
    return;
  }

  const buildOptions = {
    ...commonConfig,
    entryPoints: existingEntryPoints.map(ep => ({
      in: path.join(ROOT, ep.in),
      out: ep.out,
    })),
    outdir,
    format: 'esm',
  };

  if (watch) {
    const ctx = await esbuild.context(buildOptions);
    await ctx.watch();
    console.log('Watching for changes...');
  } else {
    await esbuild.build(buildOptions);
    console.log('Build complete!');
  }
}

build().catch(err => {
  console.error(err);
  process.exit(1);
});
