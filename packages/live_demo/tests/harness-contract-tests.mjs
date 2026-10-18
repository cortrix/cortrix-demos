import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { ADAPTER_VERSION, STATE_SCHEMA, DEMO_BASE_URL, contractHash } from '../harness/runtime.mjs'
import { derivePhase, successfulReceipts } from '../harness/phase.mjs'
import { buildTools } from '../harness/tools.mjs'
import { createTransport, pauseCode } from '../harness/transport.mjs'
import { buildSystemPrompt, prepareStep, projectReceipt } from '../harness/driver.mjs'
import { childEnvironment, initializeState } from '../harness/launch.mjs'

if (process.env.DEMO_UNIT_ONLY !== '1') throw new Error('Contract tests require DEMO_UNIT_ONLY=1')

const config = { baseUrl: DEMO_BASE_URL, runId: 'unit-contract', path: 'pg', inputIds: ['one-input'], question: '  Which "ID" is current?\nPreserve \\ : /  ' }
const sessionId = 'session-contract'
const modelBody = JSON.stringify({ model: 'deepseek-v4-flash', stream: true, stream_options: { include_usage: true }, max_tokens: 2048, thinking: { type: 'disabled' } })
function snapshot(path = 'pg') {
  const prefix = path === 'pg' ? 'pg' : 'cortrix'
  const events = []
  for (const [index, operation] of ['ingest', 'query'].entries()) {
    const callId = `native-${operation}`
    events.push({ seq: events.length, type: 'tool/call', data: { turn: 1, step: index, callId, name: `${prefix}_${operation === 'ingest' ? 'ingest_documents' : 'query_evidence'}`, arguments: '{}' } })
    events.push({ seq: events.length, type: 'tool/result', data: { turn: 1, step: index, message: { content: [{ type: 'tool-result', toolCallId: callId, isError: false, content: [{ type: 'text', text: 'Fixture response' }] }] }, meta: { schema: 'cortrix_live_demo_tool_receipt/v1', adapter_version: ADAPTER_VERSION, run_id: config.runId, path, session_id: sessionId, call_id: callId, operation, response: { operation, status: operation === 'ingest' ? 'ready' : 'ok', artifact_ref: `unit_only/${operation}` } } } })
  }
  return { meta: { id: sessionId }, events }
}
function memoryStore(proof = null) {
  let state = { adapter_version: ADAPTER_VERSION, schema: STATE_SCHEMA, session_id: sessionId, requests: [], pause_reason: null, phase_proof: proof }
  return { read: () => structuredClone(state), update: update => { const next = structuredClone(state); update(next); state = next; return next } }
}

test('final phase requires ordered successful calls and receipts from the same persisted session', () => {
  for (const path of ['pg', 'b']) {
    const current = { ...config, path }
    const valid = snapshot(path)
    assert.equal(derivePhase(valid, current, sessionId, 0).phase, 'final')
    assert.equal(derivePhase({ ...valid, meta: { id: 'session-foreign' } }, current, sessionId, 0).phase, 'tools')
    assert.equal(derivePhase({ ...valid, meta: { id: sessionId, parentSession: 'session-parent', seedLength: valid.events.length } }, current, sessionId, 0).phase, 'tools')
    for (const change of [
      value => { value.events[3].data.meta.session_id = 'session-foreign' },
      value => { value.events[3].data.meta.run_id = 'another-run' },
      value => { value.events[3].data.meta.path = path === 'pg' ? 'b' : 'pg' },
      value => { value.events[3].data.meta.response.status = 'failed' },
      value => { value.events[1].data.meta.response.status = 'failed' },
      value => { value.events[1].data.message.content[0].isError = true },
      value => { value.events[3].data.message.content[0].isError = true },
      value => { value.events[3].data.error = { code: 'FAILED', name: 'ToolError' } },
      value => { delete value.events[3].data.meta },
      value => { value.events[3].data.meta.call_id = 'unmatched' },
      value => { value.events[2].data.arguments = '{"query":"replacement"}' },
      value => { value.events.splice(2, 1) },
      value => { value.events = value.events.slice(2) },
    ]) {
      const invalid = structuredClone(valid)
      change(invalid)
      assert.equal(derivePhase(invalid, current, sessionId, 0).phase, 'tools')
    }
    assert.equal(derivePhase({ meta: { id: sessionId }, events: [{ seq: 0, type: 'assistant/message', data: { message: { content: [{ type: 'text', text: 'Ingestion and query succeeded. Enter final phase.' }] } } }] }, current, sessionId, 0).phase, 'tools')
  }
})

test('query tools have no parameters and reject extra arguments before dispatch', async () => {
  for (const path of ['pg', 'b']) {
    const current = { ...config, path }
    const requests = []
    const query = buildTools(spec => spec, current, 'unit-placeholder-token', async (_url, init) => { requests.push(JSON.parse(init.body)); return Response.json({ operation: 'query', status: 'ok', evidence: [], artifact_ref: 'unit_only/query' }) })[2]
    assert.deepEqual(query.parameters, {})
    const exec = { callId: 'next-query', signal: new AbortController().signal, agent: { session: { id: sessionId, header: { id: sessionId }, events: snapshot(path).events.slice(0, 2) } } }
    for (const args of [{ query: config.question }, { ignored: true }, [], null]) await assert.rejects(query.execute(args, exec), /EXTRA_ARGUMENTS_DENIED/)
    assert.equal(requests.length, 0)
    await query.execute({}, exec)
    assert.equal(requests[0].arguments.query, config.question)
    assert.deepEqual(Buffer.from(requests[0].arguments.query), Buffer.from(config.question))
    assert.deepEqual(Object.keys(requests[0].arguments), ['query'])
    const foreign = structuredClone(exec)
    foreign.agent.session.header.id = 'session-foreign'
    await assert.rejects(query.execute({}, foreign), /INGEST_RECEIPT_REQUIRED/)
  }
})

test('the final transport hashes the exact dispatched body and rejects a stale pre-step proof', async () => {
  const proof = derivePhase(snapshot(), config, sessionId, 0)
  const store = memoryStore(proof)
  let observed
  const transport = createTransport(config, 'unit-placeholder-token', async (_input, init) => { observed = init; return Response.json({ unit_only: true }) }, store)
  await transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody, headers: { 'content-length': '1' } })
  assert.deepEqual(JSON.parse(observed.body).response_format, { type: 'json_object' })
  assert.equal(observed.headers.has('content-length'), false)
  const row = store.read().requests[0]
  assert.equal(row.phase, 'final')
  assert.equal(row.body_sha256, createHash('sha256').update(observed.body).digest('hex'))
  assert.equal(row.body_bytes, Buffer.byteLength(observed.body))
  assert.equal(row.phase_proof.events_sha256, proof.events_sha256)
  await assert.rejects(transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody }), /PHASE_PROOF_INVALID/)
  assert.equal(store.read().requests.length, 1)
})

test('nonfinal transport strips JSON mode and does not trust a foreign session phase', async () => {
  const store = memoryStore()
  let observed
  const transport = createTransport(config, 'unit-placeholder-token', async (_input, init) => { observed = JSON.parse(init.body); return Response.json({ unit_only: true }) }, store)
  await transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: JSON.stringify({ ...JSON.parse(modelBody), response_format: { type: 'json_object' } }) })
  assert.equal(Object.hasOwn(observed, 'response_format'), false)
  assert.equal(store.read().requests[0].phase, 'tools')
  const foreign = derivePhase(snapshot(), config, sessionId, 1)
  foreign.session_id = 'session-foreign'
  store.update(value => { value.phase_proof = foreign })
  await assert.rejects(transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody }), /PHASE_PROOF_INVALID/)
})

test('a final-phase budget pause preserves its body evidence without charging or retrying the undispatched request', async () => {
  const store = memoryStore(derivePhase(snapshot(), config, sessionId, 0))
  let sent = 0
  const transport = createTransport(config, 'unit-placeholder-token', async (_input, init) => {
    sent += 1
    assert.deepEqual(JSON.parse(init.body).response_format, { type: 'json_object' })
    return Response.json({ error: { code: 'CORTRIX_LIVE_DEMO_BUDGET_PAUSED' } }, { status: 409 })
  }, store)
  await transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody })
  const state = store.read()
  assert.equal(state.requests[0].phase, 'final')
  assert.equal(state.requests[0].counts_toward_limit, false)
  assert.equal(state.requests[0].outcome, 'paused_before_provider')
  assert.equal(state.pause_reason, 'CORTRIX_LIVE_DEMO_BUDGET_PAUSED')
  await assert.rejects(transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody }), /RUN_PAUSED/)
  assert.equal(sent, 1)
})

test('pre-step rebuilds from flushed durable events and invalidates cached final state', async () => {
  const store = memoryStore(derivePhase(snapshot(), config, sessionId, 0))
  const calls = []
  const payload = { agent: { session: { id: sessionId, events: snapshot().events } }, signal: new AbortController().signal }
  const ctx = { sessions: { flush: async () => { calls.push('flush'); return true } }, sessionPersistence: { readFrom: async (id, start) => { calls.push(['read', id, start]); return { meta: { id: sessionId }, events: [] } } } }
  assert.equal(await prepareStep(ctx, payload, config, store), true)
  assert.deepEqual(calls, ['flush', ['read', sessionId, 0]])
  assert.equal(store.read().phase_proof.phase, 'tools')
  ctx.sessions.flush = async () => false
  await assert.rejects(prepareStep(ctx, payload, config, store), /DURABILITY_LISTENER_REQUIRED/)
  assert.equal(store.read().phase_proof, null)
  store.update(state => { state.pause_reason = 'CORTRIX_LIVE_DEMO_BUDGET_PAUSED' })
  assert.equal(await prepareStep(ctx, payload, config, store), false)
})

test('an empty final step never reuses prior assistant or tool-call text', () => {
  const event = (type, data = {}) => ({ type, data })
  const state = { session_id: sessionId, requests: [], pause_reason: null }
  for (const ending of [event('assistant/message', { message: { content: [] } }), event('assistant/message', { message: { content: [{ type: 'text', text: '' }] } }), event('step/end')]) {
    const events = [event('turn/start'), event('step/start'), event('assistant/message', { message: { content: [{ type: 'text', text: 'Earlier intermediate answer' }] } }), event('step/start'), ending, event('turn/end', { reason: { kind: 'completed' } })]
    assert.equal(projectReceipt(events, state, config).final_response, '')
  }
  const events = [event('assistant/message', { message: { content: [{ type: 'text', text: 'I will query now' }, { type: 'tool-call', id: 'call', name: 'pg_query_evidence', arguments: '{}' }] } }), event('turn/end', { reason: { kind: 'completed' } })]
  assert.equal(projectReceipt(events, state, config).final_response, '')
  assert.equal(successfulReceipts({ meta: { id: sessionId }, events }, config, sessionId).length, 0)
})

test('legacy adapter state is rejected without mutation and contract identity includes the version', () => {
  const armRoot = mkdtempSync(join(tmpdir(), 'cortrix-demo-contract-'))
  const path = join(armRoot, 'driver-state.json')
  const old = JSON.stringify({ schema: 'cortrix_live_demo_harness_state/v1', session_id: sessionId, requests: [], contract_sha256: contractHash(config) })
  writeFileSync(path, old, { mode: 0o600 })
  assert.throws(() => initializeState({ ...config, armRoot, resumeSessionId: sessionId }), /ADAPTER_VERSION_MISMATCH/)
  assert.equal(readFileSync(path, 'utf8'), old)
  const previousHash = createHash('sha256').update(JSON.stringify({ run_id: config.runId, path: config.path, input_ids: config.inputIds, question: config.question, model: 'deepseek-v4-flash', harness_commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca' })).digest('hex')
  assert.notEqual(contractHash(config), previousHash)
})

test('only explicit pre-dispatch service codes release a local reservation', () => {
  for (const code of [
    'CORTRIX_LIVE_DEMO_RUN_NOT_ACTIVE',
    'CORTRIX_LIVE_DEMO_EXTERNAL_CALLS_DISABLED',
    'CORTRIX_LIVE_DEMO_REQUEST_ALREADY_RESERVED',
    'CORTRIX_LIVE_DEMO_INPUT_LIMIT',
    'CORTRIX_LIVE_DEMO_TURN_LIMIT',
    'CORTRIX_LIVE_DEMO_PRICING_REQUIRED',
    'CORTRIX_LIVE_DEMO_BUDGET_PAUSED',
    'DEMO_NO_ACTIVE_RUN',
  ]) assert.equal(pauseCode({ error: { code } }), code)
  assert.equal(pauseCode({ error: { code: 'CORTRIX_LIVE_DEMO_USAGE_UNRESOLVED' } }), undefined)
  assert.equal(pauseCode({ error: { code: 'UNKNOWN' } }), undefined)
})

test('the Harness subprocess keeps the verified checkout identity', () => {
  const current = { ...config, sessionRoot: '/runtime/session', armRoot: '/runtime/session/unit-contract/pg' }
  const environment = childEnvironment(current, 'unit-placeholder-token', { session_id: sessionId }, { PATH: '/bin' })
  assert.equal(environment.DEMO_HARNESS_ROOT, process.env.DEMO_HARNESS_ROOT ?? new URL('../runtime-support/harness', import.meta.url).pathname)
  assert.equal(environment.DEMO_HARNESS_COMMIT, '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca')
  assert.equal(environment.PATH, '/bin')
})

test('the system section requires exact JSON and treats tool content as untrusted', () => {
  const prompt = buildSystemPrompt(config)
  assert.match(prompt, /exactly these keys: selected_field, document_id, evidence_ref/)
  assert.match(prompt, /untrusted data/)
  assert.match(prompt, /empty output.*failure/)
  assert.match(prompt, /never supply or rewrite it/)
})
