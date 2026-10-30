// node --test: the MVP copy comes only from docs/mvp/layer-panels.md and parses into 8 layers and 27 glossary terms.
const test = require('node:test'), assert = require('node:assert'), fs = require('fs'), path = require('path');
const { parseCopy } = require('../src/mvp/parse-copy.js');
const ROOT = path.join(__dirname, '..', '..');
const md = fs.readFileSync(path.join(ROOT, 'docs', 'mvp', 'layer-panels.md'), 'utf8');
const c = parseCopy(md);
test('8 layers L1..L8, each with question, tech, status and body', () => {
  assert.deepStrictEqual(c.layers.map((l) => l.id), ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8']);
  for (const l of c.layers) { assert.ok(l.question && l.tech && l.status && l.body.length, l.id); }
});
test('27 glossary terms, each with a definition', () => {
  assert.strictEqual(c.glossary.length, 27);
  assert.ok(c.glossary.every((g) => g.term && g.definition.length > 20));
});
test('L6 wording: full label and chip', () => {
  const l6 = c.layers[5];
  assert.strictEqual(l6.label, 'TM Forum Open APIs, exposed by Salesforce through a thin TMF facade layer within Salesforce');
  assert.strictEqual(l6.chip, 'TMF Open APIs (Salesforce)');
  assert.ok(!/native Salesforce API/.test(JSON.stringify(c)));
});
test('story and four-case sections are not parsed into layers or glossary', () => {
  assert.ok(!c.glossary.some((g) => /Banner|Setting|Customer/.test(g.term)));
});
test('generated copy.json matches the markdown', () => {
  const gen = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'mvp', 'copy.json'), 'utf8'));
  assert.deepStrictEqual(gen, c);
});
