// Downloads the speech-recognition runtime into src/vendor/transformers/.
// It's third-party code (and a 27 MB wasm binary), so it isn't committed.
// Run `npm run vendor` once before loading the extension or building the zip.
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PACKAGES = {
  '@huggingface/transformers@4.3.1': {
    'dist/transformers.min.js': 'transformers.min.js',
    LICENSE: 'transformers.LICENSE',
  },
  // The exact onnxruntime-web build Transformers.js 4.3.1 was compiled against.
  'onnxruntime-web@1.31.0-dev.20260914-8d85527a0': {
    'dist/ort-wasm-simd-threaded.asyncify.mjs': 'ort-wasm-simd-threaded.asyncify.mjs',
    'dist/ort-wasm-simd-threaded.asyncify.wasm': 'ort-wasm-simd-threaded.asyncify.wasm',
  },
};

const out = path.join(__dirname, '..', 'src', 'vendor', 'transformers');
fs.mkdirSync(out, { recursive: true });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dualsubs-vendor-'));
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

for (const [spec, files] of Object.entries(PACKAGES)) {
  const tgz = execFileSync(npm, ['pack', spec, '--silent', '--pack-destination', tmp], { encoding: 'utf8', shell: process.platform === 'win32' })
    .trim()
    .split('\n')
    .pop();
  const dir = path.join(tmp, spec.replace(/[@/]/g, '_'));
  fs.mkdirSync(dir);
  execFileSync('tar', ['xzf', path.join(tmp, tgz), '-C', dir]);
  for (const [from, to] of Object.entries(files)) {
    fs.copyFileSync(path.join(dir, 'package', from), path.join(out, to));
    console.log('vendor/transformers/' + to);
  }
}
fs.rmSync(tmp, { recursive: true, force: true });
