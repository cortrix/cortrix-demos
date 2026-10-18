import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join, isAbsolute, resolve } from 'node:path'
import { existsSync, lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

const MODULE_ROOT = dirname(fileURLToPath(import.meta.url))
export const FROZEN_HARNESS_COMMIT = '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca'
export const HARNESS_ROOT = resolve(process.env.DEMO_HARNESS_ROOT ?? join(MODULE_ROOT, '..', 'runtime-support', 'harness'))
export const HARNESS_COMMIT = process.env.DEMO_HARNESS_COMMIT ?? FROZEN_HARNESS_COMMIT
export const DEMO_BASE_URL = 'http://127.0.0.1:4186'
export const MODEL = 'deepseek-v4-flash'
export const MAX_MODEL_REQUESTS = 4
export const ADAPTER_VERSION = 'cortrix_live_demo_harness_v1'
export const STATE_SCHEMA = 'cortrix_live_demo_harness_state/v1'

export function resolveHarness(name, owner = 'apps/cli') {
  return createRequire(join(HARNESS_ROOT, owner, 'package.json')).resolve(name)
}

export function importHarness(name, owner) {
  return import(pathToFileURL(resolveHarness(name, owner)).href)
}

export function parseConfig(environment = process.env) {
  const baseUrl = environment.DEMO_BASE_URL ?? DEMO_BASE_URL
  let parsedBase
  try { parsedBase = new URL(baseUrl) } catch { throw new Error('DEMO_BASE_URL must be a valid URL') }
  if (parsedBase.protocol !== 'http:' || parsedBase.hostname !== '127.0.0.1' || !parsedBase.port || parsedBase.pathname !== '/' || parsedBase.username || parsedBase.password || parsedBase.search || parsedBase.hash) throw new Error('DEMO_BASE_URL must identify the configured loopback controller origin')
  if (HARNESS_COMMIT !== FROZEN_HARNESS_COMMIT) throw new Error('DEMO_HARNESS_COMMIT must match the frozen Harness revision')
  if (!isAbsolute(HARNESS_ROOT) || HARNESS_ROOT === '/') throw new Error('DEMO_HARNESS_ROOT must be an absolute scoped path')
  const runId = environment.DEMO_RUN_ID
  const path = environment.DEMO_PATH
  const inputIds = JSON.parse(environment.DEMO_INPUT_IDS ?? 'null')
  const question = environment.DEMO_QUESTION
  const sessionRoot = environment.DEMO_SESSION_ROOT
  const resumeSessionId = environment.DEMO_RESUME_SESSION_ID || undefined
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$/.test(runId ?? '')) throw new Error('DEMO_RUN_ID is invalid')
  if (!['pg', 'b'].includes(path)) throw new Error('DEMO_PATH must be pg or b')
  if (!Array.isArray(inputIds) || inputIds.length === 0 || inputIds.length > 24 || inputIds.some(id => typeof id !== 'string' || id.length === 0 || id.length > 256) || new Set(inputIds).size !== inputIds.length) throw new Error('DEMO_INPUT_IDS must contain distinct approved input identifiers')
  if (typeof question !== 'string' || question.trim().length === 0 || Buffer.byteLength(question) > 12000) throw new Error('DEMO_QUESTION is missing or too large')
  if (!isAbsolute(sessionRoot ?? '')) throw new Error('DEMO_SESSION_ROOT must be absolute')
  if (resumeSessionId !== undefined && !/^session-[A-Za-z0-9_-]{1,180}$/.test(resumeSessionId)) throw new Error('DEMO_RESUME_SESSION_ID is invalid')
  return { baseUrl: baseUrl.replace(/\/$/, ''), runId, path, inputIds, question, sessionRoot, resumeSessionId, armRoot: join(sessionRoot, runId, path) }
}

export function ensureRuntimeDirectory(path) {
  mkdirSync(path, { recursive: true, mode: 0o700 })
  const stat = lstatSync(path)
  if (!stat.isDirectory() || stat.isSymbolicLink() || (stat.mode & 0o077) !== 0 || (process.getuid && stat.uid !== process.getuid())) throw new Error('Runtime directories must be owned by the current user with mode 0700')
}

export function writeRuntimeJson(path, value) {
  const temporary = `${path}.next-${process.pid}`
  writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'w' })
  renameSync(temporary, path)
}

export function readState(config) {
  const state = JSON.parse(readFileSync(join(config.armRoot, 'driver-state.json'), 'utf8'))
  if (state.schema !== STATE_SCHEMA || state.adapter_version !== ADAPTER_VERSION) throw new Error('DEMO_ADAPTER_VERSION_MISMATCH: existing sessions require their original adapter')
  return state
}

export function updateState(config, mutate) {
  const state = readState(config)
  mutate(state)
  writeRuntimeJson(join(config.armRoot, 'driver-state.json'), state)
  return state
}

export function contractHash(config) {
  return createHash('sha256').update(JSON.stringify({ adapter_version: ADAPTER_VERSION, run_id: config.runId, path: config.path, input_ids: config.inputIds, question: config.question, model: MODEL, harness_commit: HARNESS_COMMIT })).digest('hex')
}

export function redact(value, token = process.env.DEMO_INTERNAL_TOKEN ?? '') {
  return token ? String(value).split(token).join('[redacted]') : String(value)
}

export function redactPaths(value, token = process.env.DEMO_INTERNAL_TOKEN ?? '', paths = []) {
  let result = redact(value, token)
  for (const path of [HARNESS_ROOT, ...paths]) if (path) result = result.split(String(path)).join('[runtime-path]')
  return result
}

export function checkDependencies() {
  const modules = ['@deepseek-ai/cordis', '@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless', '@deepseek-ai/dsh-agent', '@deepseek-ai/dsh-llm', '@deepseek-ai/dsh-tools', '@deepseek-ai/dsh-session']
  return modules.map(name => {
    const path = resolveHarness(name)
    if (!existsSync(path)) throw new Error(`Harness runtime is missing: ${name}`)
    return { package: name, present: true }
  })
}
