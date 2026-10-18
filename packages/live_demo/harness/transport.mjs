import { createHash, randomUUID } from 'node:crypto'
import { parseConfig, readState, updateState, MAX_MODEL_REQUESTS, ADAPTER_VERSION } from './runtime.mjs'
import { requestPhase } from './phase.mjs'

const PAUSE_CODES = new Set([
  'CORTRIX_LIVE_DEMO_RUN_NOT_ACTIVE',
  'CORTRIX_LIVE_DEMO_EXTERNAL_CALLS_DISABLED',
  'CORTRIX_LIVE_DEMO_REQUEST_ALREADY_RESERVED',
  'CORTRIX_LIVE_DEMO_INPUT_LIMIT',
  'CORTRIX_LIVE_DEMO_TURN_LIMIT',
  'CORTRIX_LIVE_DEMO_PRICING_REQUIRED',
  'CORTRIX_LIVE_DEMO_BUDGET_PAUSED',
  'DEMO_NO_ACTIVE_RUN',
])

export function pauseCode(body) {
  const code = body?.error?.code ?? body?.code
  return PAUSE_CODES.has(code) ? code : undefined
}

// Redact across chunk boundaries before any provider text can enter the durable session.
export function redactResponse(response, token) {
  if (!response.body || !token) return response
  const decoder = new TextDecoder()
  const encoder = new TextEncoder()
  let pending = ''
  const transform = new TransformStream({
    transform(chunk, controller) {
      pending += decoder.decode(chunk, { stream: true })
      let end = Math.max(0, pending.length - token.length + 1)
      const crossing = pending.lastIndexOf(token, end)
      if (crossing >= 0 && crossing < end && crossing + token.length > end) end = crossing
      controller.enqueue(encoder.encode(pending.slice(0, end).split(token).join('[redacted]')))
      pending = pending.slice(end)
    },
    flush(controller) {
      pending += decoder.decode()
      controller.enqueue(encoder.encode(pending.split(token).join('[redacted]')))
    },
  })
  const headers = new Headers(response.headers)
  headers.delete('content-length')
  return new Response(response.body.pipeThrough(transform), { status: response.status, statusText: response.statusText, headers })
}

export function createTransport(config, token, fetchImpl = globalThis.fetch, store = { read: () => readState(config), update: change => updateState(config, change) }) {
  const modelUrl = `${config.baseUrl}/internal/model/v1/chat/completions`
  const toolUrl = `${config.baseUrl}/internal/harness/tool`
  return async (input, init = {}) => {
    const url = input instanceof Request ? input.url : String(input)
    if (url !== modelUrl && url !== toolUrl) throw new Error('DEMO_NETWORK_TARGET_DENIED')
    if ((init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase() !== 'POST') throw new Error('DEMO_NETWORK_METHOD_DENIED')
    const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined))
    headers.set('Authorization', `Bearer ${token}`)
    headers.set('X-Demo-Run-Id', config.runId)
    headers.set('X-Demo-Path', config.path)
    headers.set('X-Demo-Session-Id', store.read().session_id)
    let requestId
    const outgoing = { ...init, headers, redirect: 'error' }
    if (url === modelUrl) {
      const rawBody = init.body ?? (input instanceof Request ? await input.clone().text() : undefined)
      const body = JSON.parse(rawBody)
      if (body.model !== 'deepseek-v4-flash' || body.stream !== true || body.stream_options?.include_usage !== true || !Number.isInteger(body.max_tokens) || body.max_tokens < 1 || body.max_tokens > 2048 || body.thinking?.type !== 'disabled') throw new Error('DEMO_MODEL_CONTRACT_DENIED')
      const state = store.read()
      if (state.adapter_version !== ADAPTER_VERSION) throw new Error('DEMO_ADAPTER_VERSION_MISMATCH')
      if (state.pause_reason) throw new Error('DEMO_RUN_PAUSED')
      if (state.requests.filter(request => request.counts_toward_limit).length >= MAX_MODEL_REQUESTS) throw new Error('DEMO_TURN_LIMIT')
      const phase = requestPhase(state, config)
      delete body.response_format
      if (phase === 'final') body.response_format = { type: 'json_object' }
      outgoing.body = JSON.stringify(body)
      headers.delete('content-length')
      const bodySha256 = createHash('sha256').update(outgoing.body).digest('hex')
      requestId = randomUUID()
      headers.set('X-Demo-Request-Id', requestId)
      store.update(next => next.requests.push({ request_id: requestId, adapter_version: ADAPTER_VERSION, phase, body_sha256: bodySha256, body_bytes: Buffer.byteLength(outgoing.body), phase_proof: next.phase_proof, started_at: new Date().toISOString(), counts_toward_limit: true, outcome: 'reserved' }))
    }
    let response
    try {
      response = await fetchImpl(input, outgoing)
    } catch {
      if (requestId) store.update(state => { state.requests.find(item => item.request_id === requestId).outcome = 'transport_error_unknown_cost' })
      throw new Error('DEMO_PROXY_TRANSPORT_ERROR')
    }
    let paused
    if (!response.ok) {
      try { paused = pauseCode(await response.clone().json()) } catch { /* The adapter preserves malformed HTTP error status. */ }
    }
    store.update(state => {
      if (paused) state.pause_reason = paused
      if (requestId) {
        const record = state.requests.find(item => item.request_id === requestId)
        record.http_status = response.status
        record.outcome = paused ? 'paused_before_provider' : response.ok ? 'response_started' : 'http_error_unknown_cost'
        if (paused) record.counts_toward_limit = false
      }
    })
    return redactResponse(response, token)
  }
}

if (process.env.DEMO_TRANSPORT_ACTIVE === '1') {
  const token = process.env.DEMO_INTERNAL_TOKEN
  if (!token) throw new Error('DEMO_INTERNAL_TOKEN is required')
  globalThis.fetch = createTransport(parseConfig(), token)
}
