// Observe the exact Vite graph, including CSS and font imports, without changing output.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [webArgument, outputArgument, projectArgument] = process.argv.slice(2);
if (!webArgument || !outputArgument || !projectArgument) {
  throw new Error('Usage: frontend-notices.mjs WEB_DIRECTORY OUTPUT_DIRECTORY PROJECT_DIRECTORY');
}
const web = fs.realpathSync(webArgument);
const output = path.resolve(outputArgument);
const project = path.resolve(projectArgument);
const overrides = JSON.parse(fs.readFileSync(path.join(project, 'licenses/overrides.json')));
const sha256 = data => crypto.createHash('sha256').update(data).digest('hex');
const noticeName = name => /(?:licen[cs]e|copying|copyright|notice|patents|unlicense)/i.test(name);
const licenseName = name => /(?:licen[cs]e|copying|unlicense)/i.test(name);
process.chdir(web);
const {build} = await import(pathToFileURL(path.join(web, 'node_modules/vite/dist/node/index.js')));
const modules = new Set();
const result = await build({
  configFile: path.join(web, 'vite.config.ts'),
  build: {write: false},
  plugins: [{name: 'distribution-inventory', generateBundle() {
    for (const id of this.getModuleIds()) modules.add(id);
    // CSS @import dependencies can be consumed by PostCSS without Rollup modules.
    for (const file of this.getWatchFiles()) modules.add(file);
  }}],
});
const assets = {};
for (const item of result.output) {
  const bytes = item.type === 'chunk' ? item.code : item.source;
  assets[item.fileName] = sha256(bytes);
  const installed = path.join(web, 'build', item.fileName);
  if (!fs.existsSync(installed) || sha256(fs.readFileSync(installed)) !== assets[item.fileName]) {
    throw new Error(`Inventory build differs from the normal build: ${item.fileName}`);
  }
}
const packages = new Map();
for (const id of modules) {
  if (!id.includes('/node_modules/')) continue;
  let folder = path.dirname(id.replace(/^\0/, '').split('?')[0]);
  while (folder.startsWith(web + path.sep)) {
    const file = path.join(folder, 'package.json');
    if (fs.existsSync(file)) {
      const bytes = fs.readFileSync(file);
      const meta = JSON.parse(bytes);
      if (meta.name && meta.version) {
        packages.set(`${meta.name}@${meta.version}`, {folder, meta, manifest_sha256: sha256(bytes)});
        break;
      }
    }
    folder = path.dirname(folder);
  }
}
fs.mkdirSync(output, {recursive: true});
const records = [];
for (const [identity, item] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
  const notices = [];
  const destination = path.join(output, 'notices', sha256(identity).slice(0, 20));
  const copy = (relative, bytes, source) => {
    const target = path.join(destination, relative);
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.writeFileSync(target, bytes);
    notices.push({path: path.relative(output, target), sha256: sha256(bytes), source});
  };
  function walk(folder) {
    for (const entry of fs.readdirSync(folder, {withFileTypes: true})) {
      const file = path.join(folder, entry.name);
      if (entry.isDirectory() && !['node_modules', '.git'].includes(entry.name)) walk(file);
      else if (entry.isFile() && noticeName(entry.name)) {
        copy(path.relative(item.folder, file), fs.readFileSync(file), 'Installed npm archive');
      }
    }
  }
  walk(item.folder);
  for (const replacement of overrides[`npm:${identity}`]?.files ?? []) {
    const bytes = fs.readFileSync(path.join(project, replacement.path));
    if (sha256(bytes) !== replacement.sha256) throw new Error(`Recovered notice checksum mismatch: ${identity}`);
    copy(path.join('recovered', path.basename(replacement.path)), bytes, replacement.source);
  }
  records.push({name: item.meta.name, version: item.meta.version, declared_license: item.meta.license,
    manifest_sha256: item.manifest_sha256, notices,
    has_license_text: notices.some(n => licenseName(path.basename(n.path)))});
}
const publicAssets = [];
function staticAssets(folder) {
  for (const entry of fs.readdirSync(folder, {withFileTypes: true})) {
    const file = path.join(folder, entry.name);
    if (entry.isDirectory()) staticAssets(file);
    else if (entry.isFile()) publicAssets.push({path: path.relative(web, file), sha256: sha256(fs.readFileSync(file))});
  }
}
staticAssets(path.join(web, 'public'));
const report = {scope: 'Vite reachable module graph, including CSS and fonts; conservative package notice inventory',
  generated_assets_match_normal_build: true, module_count: modules.size, packages: records,
  missing_license_text: records.filter(p => !p.has_license_text).map(p => `${p.name}@${p.version}`),
  generated_assets: assets, static_public_assets: publicAssets};
fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(report, null, 2) + '\n');
console.log(`Inventoried ${records.length} frontend packages; ${report.missing_license_text.length} missing license texts`);
