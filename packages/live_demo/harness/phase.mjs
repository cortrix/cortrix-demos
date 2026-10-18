import { createHash } from 'node:crypto'
import { ADAPTER_VERSION, contractHash } from './runtime.mjs'

export function toolNames(path) {
  const prefix = path === 'pg' ? 'pg' : 'cortrix'
  return [`${prefix}_ingest_documents`, `${prefix}_get_status`, `${prefix}_query_evidence`]
}

function emptyArguments(value) {
  try {
    const args = typeof value === 'string' ? JSON.parse(value) : value
    return args !== null && typeof args === 'object' && !Array.isArray(args) && Object.keys(args).length === 0
  } catch { return false }
}

export function successfulReceipts(snapshot, config, sessionId) {
  if (String(snapshot?.meta?.id) !== sessionId || !Array.isArray(snapshot?.events)) return []
  const floor = snapshot.meta.parentSession ? snapshot.meta.seedLength : 0
  if (!Number.isSafeInteger(floor) || floor < 0) return []
  const [ingest, , query] = toolNames(config.path)
  const operations = new Map([[ingest, 'ingest'], [query, 'query']])
  const calls = new Map()
  const receipts = []
  let lastSeq = -1
  for (const event of snapshot.events) {
    if (!Number.isSafeInteger(event.seq) || event.seq <= lastSeq) return []
    lastSeq = event.seq
    if (event.seq < floor) continue
    if (event.type === 'tool/call') {
      const call = event.data
      if (operations.has(call.name) && typeof call.callId === 'string' && emptyArguments(call.arguments)) {
        if (calls.has(call.callId)) return []
        calls.set(call.callId, { ...call, seq: event.seq, operation: operations.get(call.name), settled: false })
      }
    }
    if (event.type !== 'tool/result') continue
    const data = event.data
    const blocks = data?.message?.content?.filter(block => block.type === 'tool-result') || []
    if (blocks.length !== 1) continue
    const block = blocks[0]
    const call = calls.get(block.toolCallId)
    if (!call || call.settled || call.seq >= event.seq) continue
    call.settled = true
    const meta = data.meta
    if (block.isError === true || data.error !== undefined || data.turn !== call.turn || data.step !== call.step) continue
    if (meta?.schema !== 'cortrix_live_demo_tool_receipt/v1' || meta.adapter_version !== ADAPTER_VERSION || meta.run_id !== config.runId || meta.path !== config.path || meta.session_id !== sessionId || meta.call_id !== call.callId || meta.operation !== call.operation) continue
    const response = meta.response
    if (response?.operation !== call.operation || response.status !== (call.operation === 'ingest' ? 'ready' : 'ok') || typeof response.artifact_ref !== 'string' || response.artifact_ref.length === 0) continue
    if (call.operation === 'query' && !receipts.some(receipt => receipt.operation === 'ingest' && receipt.result_seq < call.seq)) continue
    receipts.push({ operation: call.operation, call_id: call.callId, call_seq: call.seq, result_seq: event.seq, artifact_ref: response.artifact_ref })
  }
  return receipts
}

export function derivePhase(snapshot, config, sessionId, requestIndex) {
  const receipts = successfulReceipts(snapshot, config, sessionId)
  return {
    adapter_version: ADAPTER_VERSION,
    run_id: config.runId,
    path: config.path,
    session_id: sessionId,
    contract_sha256: contractHash(config),
    phase: receipts.some(receipt => receipt.operation === 'query') ? 'final' : 'tools',
    source: 'native_persisted_session_events',
    request_index: requestIndex,
    last_event_seq: snapshot?.events?.at(-1)?.seq ?? null,
    events_sha256: createHash('sha256').update(JSON.stringify(snapshot?.events || [])).digest('hex'),
    receipts,
  }
}

export function requestPhase(state, config) {
  const proof = state.phase_proof
  if (!proof) return 'tools'
  if (proof.adapter_version !== ADAPTER_VERSION || proof.run_id !== config.runId || proof.path !== config.path || proof.session_id !== state.session_id || proof.contract_sha256 !== contractHash(config) || proof.source !== 'native_persisted_session_events' || proof.request_index !== state.requests.length) throw new Error('DEMO_PHASE_PROOF_INVALID')
  if (proof.phase === 'final' && (!proof.receipts?.some(receipt => receipt.operation === 'ingest') || !proof.receipts.some(receipt => receipt.operation === 'query'))) throw new Error('DEMO_FINAL_RECEIPTS_REQUIRED')
  if (!['tools', 'final'].includes(proof.phase)) throw new Error('DEMO_PHASE_INVALID')
  return proof.phase
}
