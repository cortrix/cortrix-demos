// This test fixture never opens a socket and cannot be selected by the production launcher.
import { createHash } from 'node:crypto'
import { join } from 'node:path'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { parseConfig, readState } from '../harness/runtime.mjs'
import { toolNames } from '../harness/tools.mjs'

if (process.env.DEMO_UNIT_ONLY !== '1') throw new Error('Synthetic HTTP fixtures require DEMO_UNIT_ONLY=1')
const config = parseConfig()
function observe(name, value) {
  const path = join(config.armRoot, name)
  const rows = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : []
  rows.push(value)
  writeFileSync(path, JSON.stringify(rows), { mode: 0o600 })
}
const fixtureEvidence = [
  { rank: 1, evidence_ref: 'unit-evidence-old', document_id: 'unit-doc-old', version: '1', lifecycle_status: 'superseded', content: 'Synthetic fixture: the former field was fixture_old_field.', content_truncated: false },
  { rank: 2, evidence_ref: 'unit-evidence-current', document_id: 'unit-doc-current', version: '2', lifecycle_status: 'current', content: 'Synthetic fixture: the current field is fixture_current_field.', content_truncated: false },
]
globalThis.fetch = async (input, init) => {
  const url = String(input)
  if (url === `${config.baseUrl}/internal/harness/tool`) {
    const request = JSON.parse(init.body)
    observe('unit-tool-requests.json', request)
    if (request.operation === 'query') {
      if (request.arguments.query !== config.question) return Response.json({ error: { code: 'UNIT_FROZEN_QUESTION_CHANGED' } }, { status: 400 })
      if (process.env.DEMO_UNIT_MODE === 'failed-query') return Response.json({ error: { code: 'UNIT_QUERY_FAILED' } }, { status: 400 })
      return Response.json({ operation: 'query', status: 'ok', returned_count: fixtureEvidence.length, limit: 8, truncated: false, evidence: fixtureEvidence, artifact_ref: 'unit_only/query' })
    }
    return Response.json({ operation: request.operation, status: 'ready', document_count: config.inputIds.length, original_chunk_count: 2, input_manifest_sha256: '0'.repeat(64), artifact_ref: `unit_only/${request.operation}` })
  }
  if (url !== `${config.baseUrl}/internal/model/v1/chat/completions`) throw new Error('UNIT_FIXTURE_NETWORK_DENIED')
  const outbound = JSON.parse(init.body)
  const reservation = readState(config).requests.at(-1)
  const bodySha256 = createHash('sha256').update(init.body).digest('hex')
  if (reservation.body_sha256 !== bodySha256 || (reservation.phase === 'final' ? outbound.response_format?.type !== 'json_object' : Object.hasOwn(outbound, 'response_format'))) throw new Error('UNIT_REQUEST_PHASE_OR_HASH_MISMATCH')
  observe('unit-model-requests.json', { phase: reservation.phase, body_sha256: bodySha256, body: outbound })
  if (process.env.DEMO_UNIT_MODE === 'pause') return Response.json({ error: { code: 'CORTRIX_LIVE_DEMO_BUDGET_PAUSED', message: 'Synthetic unit test pause before provider dispatch' } }, { status: 409 })
  const count = readState(config).requests.filter(item => item.counts_toward_limit).length
  const [ingest, status, query] = toolNames(config.path)
  const tool = process.env.DEMO_UNIT_MODE === 'limit' ? status : count === 1 ? ingest : count === 2 ? query : undefined
  const delta = tool ? { content: 'Intermediate tool planning text must never become the final response.', tool_calls: [{ index: 0, id: `unit-call-${count}`, type: 'function', function: { name: tool, arguments: '{}' } }] } : { content: process.env.DEMO_UNIT_MODE === 'empty-final' ? '' : JSON.stringify(process.env.DEMO_UNIT_MODE === 'failed-query' ? { selected_field: null, document_id: null, evidence_ref: null } : { selected_field: 'fixture_current_field', document_id: 'unit-doc-current', evidence_ref: 'unit-evidence-current' }) }
  const chunk = (change, finish = null) => ({ id: `unit-response-${count}`, object: 'chat.completion.chunk', created: 0, model: 'deepseek-v4-flash', choices: [{ index: 0, delta: change, finish_reason: finish }] })
  const finish = { ...chunk({}, tool ? 'tool_calls' : 'stop'), usage: { prompt_tokens: 30, prompt_cache_hit_tokens: 10, completion_tokens: 20, total_tokens: 50 } }
  const body = `data: ${JSON.stringify(chunk(delta))}\n\ndata: ${JSON.stringify(finish)}\n\ndata: [DONE]\n\n`
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}
