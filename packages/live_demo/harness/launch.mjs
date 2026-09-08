import { spawn, spawnSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { closeSync, existsSync, openSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { HARNESS_ROOT, HARNESS_COMMIT, FROZEN_HARNESS_COMMIT, DEMO_BASE_URL, MODEL, MAX_MODEL_REQUESTS, ADAPTER_VERSION, STATE_SCHEMA, parseConfig, contractHash, ensureRuntimeDirectory, writeRuntimeJson, readState, updateState, redactPaths, checkDependencies, importHarness } from './runtime.mjs'

const SOURCE_ROOT = dirname(fileURLToPath(import.meta.url))

export function initializeState(config) {
  const statePath = join(config.armRoot, 'driver-state.json')
  if (existsSync(statePath)) {
    const previous = readState(config)
    if (!config.resumeSessionId || previous.session_id !== config.resumeSessionId) throw new Error('Existing experiment requires its exact DEMO_RESUME_SESSION_ID')
    if (previous.contract_sha256 !== contractHash(config)) throw new Error('Resume must preserve the original experiment inputs and question')
    if (previous.requests.filter(request => request.counts_toward_limit).length >= MAX_MODEL_REQUESTS) throw new Error('DEMO_TURN_LIMIT')
    return updateState(config, state => { state.pause_reason = null; state.phase_proof = null; state.resume_count += 1 })
  }
  if (config.resumeSessionId) throw new Error('Cannot resume without the original driver state')
  const state = { schema: STATE_SCHEMA, adapter_version: ADAPTER_VERSION, session_id: `session-${randomUUID()}`, contract_sha256: contractHash(config), run_id: config.runId, path: config.path, created_at: new Date().toISOString(), resume_count: 0, pause_reason: null, phase_proof: null, requests: [] }
  writeRuntimeJson(statePath, state)
  return state
}

export function overlay() {
  const baseUrl = process.env.DEMO_BASE_URL ?? DEMO_BASE_URL
  return [
    '- id: headless-startup', '  disabled: true',
    '- id: headless-runner', '  disabled: true',
    '- id: session-title-llm', '  disabled: true',
    '- id: llm-retry', '  disabled: true',
    '- id: llm-pi-ai', '  disabled: true',
    '- id: tools', '  config:', '    mode: native',
    '- id: llm-deepseek', '  config:', '    apiKeyEnv: DEMO_INTERNAL_TOKEN', `    baseURL: ${baseUrl}/internal/model/v1`, '    thinking: disabled', '    reasoningEffort: off', '    maxTokens: 2048', '    streamIdleTimeoutMs: 120000', '    retryPolicy:', '      mode: normal', '      maxRetries: 0',
    '- id: session-persistence-jsonl', '  config:', "    root: !!js dshHomePath('sessions')", '    compression: none', '    packChunks: false',
    '- id: system-prompt', '  config:', "    persona: 'You are a document evidence assistant. Use only the approved experiment tools and report observed results.'",
    '- insert:', '    - id: cortrix-live-demo-driver', `      name: ${JSON.stringify(join(SOURCE_ROOT, 'driver.mjs'))}`,
    '',
  ].join('\n')
}

export async function checkRuntime() {
  if (HARNESS_COMMIT !== FROZEN_HARNESS_COMMIT) throw new Error('Harness commit configuration does not match the frozen commit')
  const identity = spawnSync('git', ['-C', HARNESS_ROOT, 'rev-parse', 'HEAD'], { encoding: 'utf8' })
  if (identity.status !== 0 || identity.stdout.trim() !== HARNESS_COMMIT) throw new Error('Harness checkout does not match the frozen commit')
  const dirty = spawnSync('git', ['-C', HARNESS_ROOT, 'status', '--short', '--untracked-files=all'], { encoding: 'utf8' })
  if (dirty.status !== 0 || dirty.stdout.trim()) throw new Error('Harness checkout must remain clean')
  const dependencies = checkDependencies()
  const imported = await importHarness('@deepseek-ai/dsh-tools')
  if (typeof imported.defineTool !== 'function') throw new Error('The built Harness tools interface is unavailable')
  return { status: 'pass', validation: 'keyless_dependency_check', adapter_version: ADAPTER_VERSION, harness_commit: HARNESS_COMMIT, model: MODEL, dependencies, external_model_requests: 0 }
}

export function childEnvironment(config, token, state, source = process.env) {
  const environment = {}
  for (const key of ['PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'TZ']) if (source[key] !== undefined) environment[key] = source[key]
  return Object.assign(environment, {
    DEMO_BASE_URL: config.baseUrl, DEMO_RUN_ID: config.runId, DEMO_PATH: config.path,
    DEMO_INPUT_IDS: JSON.stringify(config.inputIds), DEMO_QUESTION: config.question, DEMO_SESSION_ROOT: config.sessionRoot,
    DEMO_INTERNAL_TOKEN: token, DEMO_TRANSPORT_ACTIVE: '1', DEMO_HARNESS_ROOT: HARNESS_ROOT,
    DEMO_HARNESS_COMMIT: HARNESS_COMMIT,
    DSH_HOME: join(config.armRoot, 'home'), DSH_PERMISSION_MODE: 'read-only', DSH_TELEMETRY_DISABLED: '1', DSH_TOOLS_MODE: 'native',
    ...(config.resumeSessionId ? { DEMO_RESUME_SESSION_ID: state.session_id } : {}),
  })
}

export async function main(argv = process.argv.slice(2)) {
  const check = await checkRuntime()
  if (argv.length === 1 && argv[0] === '--check') { process.stdout.write(JSON.stringify(check) + '\n'); return 0 }
  if (argv.length) throw new Error('Usage: node launch.mjs [--check]')
  const config = parseConfig()
  const token = process.env.DEMO_INTERNAL_TOKEN
  if (!token || token.length < 16) throw new Error('DEMO_INTERNAL_TOKEN must be supplied in the environment')
  process.umask(0o077)
  for (const directory of [config.sessionRoot, join(config.sessionRoot, config.runId), config.armRoot, join(config.armRoot, 'home')]) ensureRuntimeDirectory(directory)
  const lockPath = join(config.armRoot, 'launch.lock')
  const lock = openSync(lockPath, 'wx', 0o600)
  writeFileSync(lock, JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }) + '\n')
  closeSync(lock)
  try {
    const state = initializeState(config)
    const patchPath = join(config.armRoot, 'cordis.patch.yml')
    writeFileSync(patchPath, overlay(), { mode: 0o600 })
    const environment = childEnvironment(config, token, state)
    const child = spawn(process.execPath, ['--import', pathToFileURL(join(SOURCE_ROOT, 'transport.mjs')).href, join(HARNESS_ROOT, 'apps/cli/lib/bin.js'), '--profile', 'headless', '--patch', patchPath], { cwd: config.armRoot, env: environment, stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', chunk => { stdout = (stdout + chunk).slice(-1000000) })
    child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-1000000) })
    const forward = () => child.kill('SIGTERM')
    process.once('SIGINT', forward)
    process.once('SIGTERM', forward)
    const outcome = await new Promise((resolvePromise, reject) => {
      child.once('error', reject)
      child.once('close', (code, signal) => resolvePromise({ code, signal }))
    })
    process.removeListener('SIGINT', forward)
    process.removeListener('SIGTERM', forward)
    const safeStdout = redactPaths(stdout, token, [config.sessionRoot, config.armRoot])
    const safeStderr = redactPaths(stderr, token, [config.sessionRoot, config.armRoot])
    writeFileSync(join(config.armRoot, 'stdout.log'), safeStdout, { mode: 0o600 })
    writeFileSync(join(config.armRoot, 'stderr.log'), safeStderr, { mode: 0o600 })
    writeRuntimeJson(join(config.armRoot, 'launch-result.json'), { schema: 'cortrix_live_demo_harness_launch/v1', adapter_version: ADAPTER_VERSION, run_id: config.runId, path: config.path, session_id: state.session_id, harness_commit: HARNESS_COMMIT, exit_code: outcome.code, signal: outcome.signal, receipt_present: existsSync(join(config.armRoot, 'receipt.json')) })
    process.stdout.write(safeStdout)
    if (stderr) process.stderr.write(safeStderr)
    return outcome.code ?? 1
  } finally {
    unlinkSync(lockPath)
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().then(code => { process.exitCode = code }).catch(error => {
    process.stderr.write(JSON.stringify({ code: 'DEMO_HARNESS_LAUNCH_FAILED', message: redactPaths(error instanceof Error ? error.message : error) }) + '\n')
    process.exitCode = 1
  })
}
