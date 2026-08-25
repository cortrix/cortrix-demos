#!/usr/bin/env node
/** Execute the real Cortrix plugin through Harness ToolRuntime and persist a replayable projection. */

import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { dirname, resolve, join } from 'node:path'
import { readFile, writeFile, mkdir } from 'node:fs/promises'

function parseArgs(argv) {
  const values = {}
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || value === undefined) throw new Error('arguments must be --name value pairs')
    values[key.slice(2)] = value
  }
  for (const required of ['plugin-root', 'query-file', 'namespace', 'output']) {
    if (!values[required]) throw new Error(`missing --${required}`)
  }
  return values
}

async function loadRuntime(pluginRoot) {
  const requireFromPlugin = createRequire(join(pluginRoot, 'package.json'))
  const load = async (name) => import(pathToFileURL(requireFromPlugin.resolve(name)).href)
  return {
    cordis: await load('@deepseek-ai/cordis'),
    systemPrompt: await load('@deepseek-ai/dsh-system-prompt'),
    tools: await load('@deepseek-ai/dsh-tools'),
    plugin: await import(pathToFileURL(join(pluginRoot, 'dist', 'index.mjs')).href),
  }
}

function textBody(result) {
  const block = result.content.find((item) => item?.type === 'text')
  if (!block || typeof block.text !== 'string') throw new Error('tool result has no JSON text block')
  return JSON.parse(block.text)
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const pluginRoot = resolve(args['plugin-root'])
  const query = (await readFile(resolve(args['query-file']), 'utf8')).trim()
  const { cordis, systemPrompt, tools, plugin } = await loadRuntime(pluginRoot)
  const ctx = new cordis.Context()
  await ctx.plugin(systemPrompt.default)
  await ctx.plugin(tools.default)
  const wrapper = Object.assign((inner, config) => {
    const runtime = plugin.createRuntime(config)
    inner.systemPrompt.section({ name: 'tool:cortrix-evidence', order: 114, text: plugin.SAFETY_PROMPT })
    inner.tools.register(plugin.searchEvidenceTool(runtime))
    inner.tools.register(plugin.getSourceTool(runtime))
  }, { inject: plugin.inject })
  const fiber = await ctx.plugin(wrapper, {
    baseUrl: args['base-url'] ?? 'http://127.0.0.1:8420',
    namespace: args.namespace,
    defaultMaxResults: Number(args['max-results'] ?? '8'),
    maxResultsCap: Number(args['max-results'] ?? '8'),
    retryTransientOnce: false,
  })
  try {
    const registered = ctx.tools.schemas().map((schema) => schema.name)
    if (JSON.stringify(registered) !== JSON.stringify(['cortrix_search_evidence', 'cortrix_get_source'])) {
      throw new Error(`unexpected model tool surface: ${JSON.stringify(registered)}`)
    }
    const events = []
    const sessionId = args['session-id'] ?? `harness-${Date.now()}`
    const agent = { id: sessionId, session: { id: sessionId, events } }
    const searchCallId = 'cortrix-search-1'
    const search = await ctx.tools.execute({
      signal: new AbortController().signal,
      callId: searchCallId,
      name: 'cortrix_search_evidence',
      arguments: { query, purpose: 'verification', max_results: Number(args['max-results'] ?? '8') },
      agent,
    })
    if (search.isError) throw new Error('cortrix_search_evidence returned an error')
    const searchBody = textBody(search)
    events.push(
      { type: 'tool/call', data: { callId: searchCallId, name: 'cortrix_search_evidence' } },
      { type: 'tool/result', data: { message: { content: [{ type: 'tool-result', toolCallId: searchCallId }] }, meta: search.meta } },
    )
    const sourceLedger = {}
    const trace = [{ name: 'cortrix_search_evidence', call_id: searchCallId, status: 'ok' }]
    for (const [index, item] of searchBody.evidence.entries()) {
      const callId = `cortrix-source-${index + 1}`
      const source = await ctx.tools.execute({
        signal: new AbortController().signal,
        callId,
        name: 'cortrix_get_source',
        arguments: { evidence_ref: item.evidence_ref },
        agent,
      })
      if (source.isError) throw new Error(`cortrix_get_source returned an error for result ${index + 1}`)
      const body = textBody(source)
      sourceLedger[item.evidence_ref] = body.source.content
      trace.push({ name: 'cortrix_get_source', call_id: callId, evidence_ref: item.evidence_ref, status: 'ok' })
      events.push(
        { type: 'tool/call', data: { callId, name: 'cortrix_get_source' } },
        { type: 'tool/result', data: { message: { content: [{ type: 'tool-result', toolCallId: callId }] } } },
      )
    }
    const output = {
      schema_version: 1,
      session_id: sessionId,
      registered_tools: registered,
      search_result: searchBody,
      source_ledger: sourceLedger,
      tool_trace: trace,
      durable_session_events: events,
      plugin_external_http_calls: 1,
      external_llm_calls: 0,
      ...(args['position-variant'] ? { position_variant: args['position-variant'] } : {}),
    }
    const outputPath = resolve(args.output)
    await mkdir(dirname(outputPath), { recursive: true })
    await writeFile(outputPath, JSON.stringify(output, null, 2) + '\n', 'utf8')
    process.stdout.write(JSON.stringify({ status: 'pass', registered_tools: registered, evidence_count: searchBody.evidence.length, external_llm_calls: 0 }) + '\n')
  } finally {
    await fiber.dispose()
    if (ctx.tools.schemas().length !== 0) throw new Error('plugin tools remained registered after unload')
  }
}

main().catch((error) => {
  process.stderr.write(JSON.stringify({ error: { code: 'CX_DEMO_HARNESS_PLUGIN_QUERY_FAILED', category: 'permanent', retryable: false, message: error instanceof Error ? error.message : String(error) } }) + '\n')
  process.exitCode = 1
})
