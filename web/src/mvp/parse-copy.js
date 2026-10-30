// Parse docs/mvp/layer-panels.md (the single source of the MVP layer wording and glossary) into copy.json.
// Format: "## L<n> Name" headings with optional **Question**/**Tech**/**Status**/**Label**/**Chip** key lines, then body
// paragraphs and bullets; one "## Glossary" section of "**Term**: definition" lines. Other ## sections are ignored.
'use strict';
const KEYS = { Question: 'question', Tech: 'tech', Status: 'status', Label: 'label', Chip: 'chip' };

function parseCopy(md) {
  const layers = [], glossary = [];
  let cur = null, mode = null, para = [];
  const flush = () => {
    if (cur && para.length) cur.body.push(para.join(' ').trim());
    para = [];
  };
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const h = line.match(/^##\s+(.*)$/);
    if (h) {
      flush();
      const lm = h[1].match(/^L(\d)\s+(.+)$/);
      if (lm) { cur = { id: 'L' + lm[1], n: +lm[1], name: lm[2].trim(), body: [], bullets: [] }; layers.push(cur); mode = 'layer'; }
      else if (/^Glossary\b/i.test(h[1])) { cur = null; mode = 'glossary'; }
      else { cur = null; mode = null; }
      continue;
    }
    if (mode === 'glossary') {
      const g = line.match(/^\*\*(.+?)\*\*:\s*(.+)$/);
      if (g) glossary.push({ term: g[1].trim(), definition: g[2].trim() });
      continue;
    }
    if (mode !== 'layer') continue;
    const k = line.match(/^\*\*(Question|Tech|Status|Label|Chip)\*\*:\s*(.+)$/);
    if (k) { flush(); cur[KEYS[k[1]]] = k[2].trim(); continue; }
    const b = line.match(/^\s*[-*]\s+(.*)$/);
    if (b) {
      flush();
      const kv = b[1].match(/^\*\*(.+?):\*\*\s*(.*)$/);
      cur.bullets.push(kv ? { key: kv[1].trim(), text: kv[2].trim() } : { key: null, text: b[1].trim() });
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    para.push(line.trim());
  }
  flush();
  for (const l of layers) { l.label = l.label || l.tech || ''; l.chip = l.chip || l.name; }
  layers.sort((a, b) => a.n - b.n);
  return { source: 'docs/mvp/layer-panels.md', layers, glossary };
}

module.exports = { parseCopy };
