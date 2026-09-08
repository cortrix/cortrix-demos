import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { createTransport, redactResponse } from '../harness/transport.mjs'
import { HARNESS_ROOT, HARNESS_COMMIT, DEMO_BASE_URL, ADAPTER_VERSION, parseConfig, ensureRuntimeDirectory, readState, importHarness, redactPaths } from '../harness/runtime.mjs'
import { buildTools } from '../harness/tools.mjs'
import { initializeState, overlay, checkRuntime } from '../harness/launch.mjs'
import { buildTaskPrompt } from '../harness/driver.mjs'

const sourceRoot = dirname(fileURLToPath(import.meta.url))
if (process.env.DEMO_UNIT_ONLY !== '1') throw new Error('Native fixture tests require DEMO_UNIT_ONLY=1')
const unitRoot = mkdtempSync(join(tmpdir(), 'cortrix-demo-harness-'))
const modelBody = JSON.stringify({ model: 'deepseek-v4-flash', stream: true, stream_options: { include_usage: true }, max_tokens: 2048, thinking: { type: 'disabled' } })

function memoryStore() {
  let state = { adapter_version: ADAPTER_VERSION, session_id: 'session-unit', pause_reason: null, requests: [] }
  return { read: () => structuredClone(state), update: update => { const next = structuredClone(state); update(next); state = next; return next } }
}

test('keyless checks resolve and import the pinned Harness runtime', async () => {
  assert.equal((await checkRuntime()).external_model_requests, 0)
})

test('the task prompt preserves the frozen en-US question and requires a current evidence reference', () => {
  const question = '  Which "ID" is current?\nKeep this punctuation: \\ / :  '
  for (const path of ['pg', 'b']) {
    const prompt = buildTaskPrompt({ path, inputIds: ['unit-input'], question }, false)
    const encoded = prompt.split('\n').find(line => line.startsWith('Business question JSON string: ')).slice('Business question JSON string: '.length)
    assert.equal(JSON.parse(encoded), question)
    assert.match(prompt, /Do not paraphrase, translate, trim, or append text/)
    assert.match(prompt, /lifecycle_status is exactly "current"/)
    assert.match(prompt, /exactly these keys: selected_field, document_id, evidence_ref/)
    assert.match(prompt, /from that same evidence item/)
  }
})

test('the controlled transport denies foreign targets and a fifth request without HTTP dispatch', async () => {
  const store = memoryStore()
  let sent = 0
  const config = { baseUrl: DEMO_BASE_URL, runId: 'unit', path: 'pg' }
  const transport = createTransport(config, 'unit-placeholder-token', async () => { sent += 1; return Response.json({ validation: 'unit_only' }) }, store)
  await assert.rejects(transport('https://example.invalid', { method: 'POST' }), /TARGET_DENIED/)
  for (let index = 0; index < 4; index += 1) await transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody })
  await assert.rejects(transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody }), /TURN_LIMIT/)
  assert.equal(sent, 4)
})

test('a proxy pause is terminal and releases only the undispatched request reservation', async () => {
  const store = memoryStore()
  let sent = 0
  const transport = createTransport({ baseUrl: DEMO_BASE_URL, runId: 'unit', path: 'b' }, 'unit-placeholder-token', async () => { sent += 1; return Response.json({ error: { code: 'CORTRIX_LIVE_DEMO_BUDGET_PAUSED' } }, { status: 409 }) }, store)
  await transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody })
  await assert.rejects(transport(`${DEMO_BASE_URL}/internal/model/v1/chat/completions`, { method: 'POST', body: modelBody }), /RUN_PAUSED/)
  assert.equal(sent, 1)
  assert.equal(store.read().requests[0].counts_toward_limit, false)
})

test('response redaction handles a token split across SSE chunks', async () => {
  const token = 'runtime-unit-token'
  const encoder = new TextEncoder()
  const response = new Response(new ReadableStream({ start(controller) { for (const value of ['prefix runtime-', 'unit-', 'token suffix']) controller.enqueue(encoder.encode(value)); controller.close() } }))
  assert.equal(await redactResponse(response, token).text(), 'prefix [redacted] suffix')
})

test('runtime paths are removed from projected logs', () => {
  assert.equal(redactPaths(`failure at ${HARNESS_ROOT}/module.js`, '', ['configured/runtime']), 'failure at [runtime-path]/module.js')
  assert.equal(redactPaths('failure at configured/runtime/run.json', '', ['configured/runtime']), 'failure at [runtime-path]/run.json')
})

test('Native tools preserve fixed input routing and return only mock service values', async () => {
  const [{ Context }, { default: SystemPrompt }, tools] = await Promise.all([importHarness('@deepseek-ai/cordis'), importHarness('@deepseek-ai/dsh-system-prompt', 'packages/core/tools'), importHarness('@deepseek-ai/dsh-tools')])
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(tools.default)
  const requests = []
  const config = { baseUrl: DEMO_BASE_URL, runId: 'unit', path: 'pg', inputIds: ['approved-input'], question: 'Frozen unit question' }
  const token = 'unit-placeholder-token'
  const dispose = buildTools(tools.defineTool, config, token, async (_url, options) => {
    requests.push(JSON.parse(options.body))
    return Response.json({ validation: 'unit_only', record_id: 'fixture-1' })
  }).map(tool => { assert.equal(tool.parameters.additionalProperties, false); return ctx.tools.register(tool) })
  try {
    const result = await ctx.tools.execute({ name: 'pg_ingest_documents', arguments: {}, callId: 'unit-call', agent: { session: { id: 'session-unit', events: [] } }, signal: new AbortController().signal })
    assert.equal(result.isError, false)
    assert.deepEqual(requests[0], { run_id: 'unit', path: 'pg', operation: 'ingest', arguments: { input_ids: ['approved-input'] } })
    assert.equal(result.meta.call_id, 'unit-call')
    assert.equal(result.meta.response.record_id, 'fixture-1')
    const extra = await ctx.tools.execute({ name: 'pg_query_evidence', arguments: { query: config.question }, callId: 'extra-call', agent: { session: { id: 'session-unit', events: [] } }, signal: new AbortController().signal })
    assert.equal(extra.isError, true)
    assert.match(JSON.stringify(extra), /INVALID_ARGS|additionalProperties|DEMO_EXTRA_ARGUMENTS_DENIED/)
    assert.equal(requests.length, 1)
  } finally {
    for (const unregister of dispose) unregister()
    await ctx.fiber.dispose()
  }
})

async function nativeFixture(mode, existing, path = 'pg', question = 'What does the fixture say?') {
  const sessionRoot = existing?.sessionRoot ?? mkdtempSync(join(unitRoot, 'native-'))
  const config = parseConfig({ DEMO_RUN_ID: 'unit-native', DEMO_PATH: path, DEMO_INPUT_IDS: '["unit-input"]', DEMO_QUESTION: question, DEMO_SESSION_ROOT: sessionRoot, ...(existing ? { DEMO_RESUME_SESSION_ID: existing.sessionId } : {}) })
  for (const directory of [join(sessionRoot, config.runId), config.armRoot, join(config.armRoot, 'home')]) ensureRuntimeDirectory(directory)
  const state = initializeState(config)
  const patch = join(config.armRoot, 'unit.patch.yml')
  writeFileSync(patch, overlay(), { mode: 0o600 })
  const environment = { PATH: process.env.PATH, LANG: 'en_US.UTF-8', DSH_HOME: join(config.armRoot, 'home'), DSH_PERMISSION_MODE: 'read-only', DSH_TELEMETRY_DISABLED: '1', DEMO_BASE_URL, DEMO_HARNESS_ROOT: HARNESS_ROOT, DEMO_HARNESS_COMMIT: HARNESS_COMMIT, DEMO_RUN_ID: config.runId, DEMO_PATH: config.path, DEMO_INPUT_IDS: JSON.stringify(config.inputIds), DEMO_QUESTION: config.question, DEMO_SESSION_ROOT: config.sessionRoot, DEMO_INTERNAL_TOKEN: `unit-only-${randomUUID()}`, DEMO_TRANSPORT_ACTIVE: '1', DEMO_UNIT_ONLY: '1', DEMO_UNIT_MODE: mode, ...(existing ? { DEMO_RESUME_SESSION_ID: state.session_id } : {}) }
  const child = spawn(process.execPath, ['--import', join(sourceRoot, 'harness-fixtures-http.mjs'), '--import', join(sourceRoot, '../harness/transport.mjs'), join(HARNESS_ROOT, 'apps/cli/lib/bin.js'), '--profile', 'headless', '--patch', patch], { cwd: config.armRoot, env: environment, stdio: ['ignore', 'pipe', 'pipe'] })
  let stderr = ''
  child.stdout.resume()
  child.stderr.on('data', chunk => { stderr += chunk })
  const timer = setTimeout(() => child.kill('SIGTERM'), 25000)
  const code = await new Promise((resolve, reject) => { child.once('error', reject); child.once('close', resolve) })
  clearTimeout(timer)
  let receipt
  try { receipt = JSON.parse(readFileSync(join(config.armRoot, 'receipt.json'), 'utf8')) } catch { throw new Error(`Native unit fixture has no receipt (exit ${code}): ${stderr}`) }
  assert.equal(JSON.stringify(receipt).includes(environment.DEMO_INTERNAL_TOKEN), false)
  return { receipt, code, sessionRoot, sessionId: state.session_id, state: readState(config), modelRequests: JSON.parse(readFileSync(join(config.armRoot, 'unit-model-requests.json'), 'utf8')), toolRequests: mode === 'pause' ? [] : JSON.parse(readFileSync(join(config.armRoot, 'unit-tool-requests.json'), 'utf8')) }
}

test('both native arms carry projected evidence and an exact final JSON reference in synthetic unit runs', { timeout: 30000 }, async () => {
  for (const path of ['pg', 'b']) {
    const frozenQuestion = '  Which "ID" is current?\nPreserve: \\ / :  '
    const { receipt, code, modelRequests, toolRequests } = await nativeFixture('normal', undefined, path, frozenQuestion)
    assert.equal(code, 0)
    assert.equal(receipt.status, 'completed')
    assert.equal(receipt.provider_request_reservations, 3)
    const prefix = path === 'pg' ? 'pg' : 'cortrix'
    assert.deepEqual(receipt.tool_calls.map(call => call.name), [`${prefix}_ingest_documents`, `${prefix}_query_evidence`])
    assert.equal(receipt.usage.cache_read_tokens, 30)
    assert.ok(receipt.tool_calls.every(call => call.result.meta.response.artifact_ref.startsWith('unit_only/')))
    const queryArguments = typeof receipt.tool_calls[1].arguments === 'string' ? JSON.parse(receipt.tool_calls[1].arguments) : receipt.tool_calls[1].arguments
    assert.deepEqual(queryArguments, {})
    assert.equal(toolRequests.find(request => request.operation === 'query').arguments.query, frozenQuestion)
    assert.deepEqual(modelRequests.map(request => request.phase), ['tools', 'tools', 'final'])
    assert.equal(Object.hasOwn(modelRequests[0].body, 'response_format'), false)
    assert.deepEqual(modelRequests[2].body.response_format, { type: 'json_object' })
    assert.ok(modelRequests[2].body.messages.some(message => message.role === 'system' && JSON.stringify(message.content).includes('Live demo evidence contract')))
    assert.ok(receipt.requests.every((request, index) => request.body_sha256 === modelRequests[index].body_sha256))
    const query = receipt.tool_calls[1].result.meta.response
    assert.equal(Object.hasOwn(query, 'resolver'), false)
    assert.equal(Object.hasOwn(query, 'selected_field'), false)
    const answer = JSON.parse(receipt.final_response)
    assert.deepEqual(Object.keys(answer).sort(), ['document_id', 'evidence_ref', 'selected_field'])
    const cited = query.evidence.find(item => item.evidence_ref === answer.evidence_ref)
    assert.equal(cited.document_id, answer.document_id)
    assert.equal(cited.lifecycle_status, 'current')
    assert.ok(cited.content.includes(answer.selected_field))
  }
})

test('an empty final native message never falls back to earlier planning text', { timeout: 30000 }, async () => {
  const { receipt, modelRequests } = await nativeFixture('empty-final')
  assert.equal(receipt.final_response, '')
  assert.equal(receipt.final_response_state, 'empty')
  assert.equal(receipt.provider_request_reservations, 3)
  assert.equal(modelRequests.at(-1).phase, 'final')
})

test('a failed native query result does not authorize final JSON mode', { timeout: 30000 }, async () => {
  const { receipt, modelRequests } = await nativeFixture('failed-query')
  assert.equal(receipt.provider_request_reservations, 3)
  assert.equal(receipt.tool_calls[1].result.message.content[0].isError, true)
  assert.deepEqual(modelRequests.map(request => request.phase), ['tools', 'tools', 'tools'])
  assert.ok(modelRequests.every(request => !Object.hasOwn(request.body, 'response_format')))
})

test('the real Harness loop stops before a fifth provider request', { timeout: 30000 }, async () => {
  const { receipt } = await nativeFixture('limit')
  assert.equal(receipt.status, 'turn_limit')
  assert.equal(receipt.provider_request_reservations, 4)
  assert.equal(receipt.tool_calls.length, 4)
})

test('a paused native session resumes under its original identity without an automatic retry', { timeout: 60000 }, async () => {
  const paused = await nativeFixture('pause')
  assert.equal(paused.receipt.status, 'paused')
  assert.equal(paused.receipt.request_attempts, 1)
  assert.equal(paused.receipt.provider_request_reservations, 0)
  const resumed = await nativeFixture('normal', paused)
  assert.equal(resumed.sessionId, paused.sessionId)
  assert.equal(resumed.receipt.status, 'completed')
  assert.equal(resumed.receipt.provider_request_reservations, 3)
  assert.equal(resumed.receipt.request_attempts, 4)
})
