import fs from 'node:fs';
import path from 'node:path';
import { JSDOM } from './node_modules/jsdom/lib/api.js';

const workspace = path.resolve(process.argv[2]);
const topology = path.join(workspace, 'docs/module-1-topology.md');
const content = fs.readFileSync(topology, 'utf8');
// Current dashboard implementation is Perses; immutable pre-WO-07 revisions retain Grafana.
const dashboard = fs.existsSync(path.join(workspace, 'tools/perses.py')) ? 'PERSES' : 'GRAFANA';
const diagrams = [...content.matchAll(/```mermaid\r?\n([\s\S]*?)```/g)].map(match => match[1]);
if (diagrams.length !== 1) throw new Error(`Expected 1 diagram, got ${diagrams.length}`);
const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const { default: mermaid } = await import('./node_modules/mermaid/dist/mermaid.core.mjs');
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
const inventory = [];
for (const diagram of diagrams) {
  await mermaid.parse(diagram);
  const parsed = await mermaid.mermaidAPI.getDiagramFromText(diagram);
  const vertices = parsed.db.getVertices();
  const ids = vertices instanceof Map ? [...vertices.keys()] : Object.keys(vertices);
  const edges = parsed.db.getEdges();
  for (const required of ['APISIX', 'KOURIER', 'QP', 'RAG', 'EMBED', 'PG', 'GEN', 'SPINIFEX', 'TEKTON', 'ARGO', 'KEYCLOAK', 'BAO', 'PROM', dashboard, 'OTEL', 'KAFKA', 'STRIMZI', 'CNPG', 'KNCTRL', 'API']) {
    if (!ids.includes(required)) throw new Error(`Missing node ${required}`);
  }
  const hasEdge = (start, end) => edges.some(edge => edge.start === start && edge.end === end);
  for (const [start, end] of [['APISIX','KOURIER'], ['KOURIER','QP'], ['QP','RAG'], ['RAG','EMBED'], ['RAG','PG'], ['RAG','GEN'], ['GEN','RAG'], ['ADAPTER','PROVISION'], ['PROVISION','SPINIFEX']]) {
    if (!hasEdge(start, end)) throw new Error(`Missing flow ${start} -> ${end}`);
  }
  if (hasEdge('GEN','PG') || hasEdge('EMBED','PG')) throw new Error('Inference must not directly query PostgreSQL');
  inventory.push({type: parsed.type, nodes: ids.length, edges: edges.length, requiredFlowChecks: 'passed'});
}
const report = {status: 'passed', parser: 'mermaid', version: '11.12.0', diagramCount: diagrams.length, inventory};
fs.writeFileSync(path.resolve(process.argv[3]), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report));
