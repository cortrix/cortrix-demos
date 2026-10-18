import { importHarness, redact, readState, ADAPTER_VERSION } from './runtime.mjs'
import { successfulReceipts, toolNames } from './phase.mjs'
export { toolNames } from './phase.mjs'

export function buildTools(defineTool, config, token, fetchImpl = globalThis.fetch) {
  const operations = ['ingest', 'status', 'query']
  return toolNames(config.path).map((name, index) => {
    const operation = operations[index]
    const definition = defineTool({
      name,
      description: operation === 'ingest'
        ? 'Write all approved input documents into this experiment arm. Call this before querying. The service returns actual write receipts.'
        : operation === 'status'
          ? 'Read the actual ingestion and processing status for this experiment arm.'
          : 'Query the already frozen business question for this experiment arm after ingestion. Call with an empty object and no arguments; the adapter forwards the original question unchanged. The service waits for actual readiness and returns evidence.',
      parameters: {},
      output: {
        schema: { type: 'object', additionalProperties: false, properties: { response_json: { type: 'string', required: true }, operation: { type: 'string', required: true }, call_id: { type: 'string', required: true }, session_id: { type: 'string', required: true } } },
        render: (_args, value) => [{ type: 'text', text: value.response_json }],
        presentationMeta: (_args, value) => ({ schema: 'cortrix_live_demo_tool_receipt/v1', adapter_version: ADAPTER_VERSION, run_id: config.runId, path: config.path, operation: value.operation, call_id: value.call_id, session_id: value.session_id, response: JSON.parse(value.response_json) }),
      },
      timeoutMs: 180000,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        if (exec.parent !== undefined || exec.agent === undefined) throw new Error('DEMO_NATIVE_AGENT_REQUIRED')
        if (args === null || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).length !== 0) throw new Error('DEMO_EXTRA_ARGUMENTS_DENIED')
        const session = exec.agent.session
        const ingested = successfulReceipts({ meta: session.header || { id: String(session.id) }, events: session.events }, config, String(session.id)).some(receipt => receipt.operation === 'ingest')
        if (operation === 'query' && !ingested) throw new Error('DEMO_INGEST_RECEIPT_REQUIRED')
        if (operation === 'ingest' && ingested) throw new Error('DEMO_INGEST_ALREADY_RECORDED')
        if (operation === 'query' && typeof config.question !== 'string') throw new Error('DEMO_QUERY_INVALID')
        const argumentsValue = operation === 'ingest' ? { input_ids: config.inputIds } : operation === 'query' ? { query: config.question } : {}
        const response = await fetchImpl(`${config.baseUrl}/internal/harness/tool`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'X-Demo-Tool-Call-Id': String(exec.callId), 'X-Demo-Session-Id': String(exec.agent.session.id) },
          body: JSON.stringify({ run_id: config.runId, path: config.path, operation, arguments: argumentsValue }),
          signal: exec.signal,
          redirect: 'error',
        })
        const text = await response.text()
        if (Buffer.byteLength(text) > 1000000) throw new Error('DEMO_TOOL_RESPONSE_TOO_LARGE')
        let body
        try { body = JSON.parse(text) } catch { throw new Error('DEMO_TOOL_RESPONSE_INVALID') }
        if (!response.ok) {
          const code = body?.error?.code ?? body?.code
          throw new Error(typeof code === 'string' && /^[A-Za-z0-9_]{1,80}$/.test(code) ? code : `DEMO_TOOL_HTTP_${response.status}`)
        }
        return { response_json: redact(JSON.stringify(body), token), operation, call_id: String(exec.callId), session_id: String(exec.agent.session.id) }
      },
    })
    if (definition.parameters?.type === 'object') definition.parameters.additionalProperties = false
    return definition
  })
}

export async function registerTools(agentCtx, config) {
  const { defineTool } = await importHarness('@deepseek-ai/dsh-tools')
  agentCtx.tools.restrict({ allow: [] })
  agentCtx.tools.presentAs('native')
  for (const tool of buildTools(defineTool, config, process.env.DEMO_INTERNAL_TOKEN)) agentCtx.tools.register(tool)
  const names = toolNames(config.path)
  const sessionId = readState(config).session_id
  agentCtx.tools.guard(exec => exec.parent !== undefined || !names.includes(exec.name) || String(exec.agent?.session.id) !== sessionId ? 'DEMO_TOOL_SCOPE_DENIED' : undefined)
}
