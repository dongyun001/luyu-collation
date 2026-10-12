/**
 * 后端 API 封装：统一 baseURL、超时与错误结构。
 *
 * 契约见 docs/API.md —— 错误一律是 { error: { code, message } }，
 * 这里把它转成 ApiError（带 code / status），让调用方按码分支而不是解析文案。
 */

const BASE_URL = (import.meta.env.VITE_API_BASE || 'http://localhost:3001').replace(/\/+$/, '')

// 后端单个 /collate 请求的总预算（含段级重试）是 180 秒（server/config.py 的
// REQUEST_BUDGET_S）。前端必须**比它长**，否则浏览器先掐断，用户看到的会是笼统的
// 「请求超时」而不是后端那条明确的「上游停滞」。这里留 15 秒余量。
const COLLATE_TIMEOUT_MS = 195_000
const HEALTH_TIMEOUT_MS = 5_000

/** 前端自定义码（后端错误码之外的网络层失败，同一命名空间便于 UI 统一分支） */
export const NETWORK_ERROR = 'NETWORK_ERROR'

export class ApiError extends Error {
  constructor(code, message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function readJson(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

async function request(path, { method = 'GET', body, timeoutMs = COLLATE_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError('LLM_TIMEOUT', `请求超时（超过 ${Math.round(timeoutMs / 1000)} 秒），请稍后重试或缩短文本`)
    }
    throw new ApiError(NETWORK_ERROR, '无法连接校勘服务：请确认后端已启动（npm run dev:server）')
  } finally {
    clearTimeout(timer)
  }

  const payload = await readJson(response)

  if (!response.ok) {
    const detail = payload?.error
    throw new ApiError(
      detail?.code || 'HTTP_ERROR',
      detail?.message || `服务返回 HTTP ${response.status}`,
      response.status,
    )
  }
  if (payload === null) {
    throw new ApiError('HTTP_ERROR', '服务返回的内容不是 JSON', response.status)
  }
  return payload
}

/**
 * 智能校勘（F2/F5）。
 * @param {string} text 待校勘原文
 * @param {object} [options] 见 API.md §2；省略时由后端取默认值
 */
export function collate(text, options) {
  return request('/api/v1/collate', {
    method: 'POST',
    body: options ? { text, options } : { text },
  })
}

/**
 * 多维度文献分析（F9，契约见 API.md §6）。
 *
 * 与 /collate 相互独立：它可以单独失败，且失败不影响已到货的校勘结果。
 * 超时沿用同一个总预算（后端 /analyze 与 /collate 走同一条 llm 调用路径）。
 *
 * @param {string} text 待分析原文
 * @param {string[]} [dimensions] 七维 key 的子集；省略即全部
 */
export function analyzeText(text, dimensions) {
  return request('/api/v1/analyze', {
    method: 'POST',
    body: dimensions && dimensions.length ? { text, dimensions } : { text },
  })
}

/** 冒烟检查（API.md §5），演示前跑一条。 */
export function health() {
  return request('/api/v1/health', { timeoutMs: HEALTH_TIMEOUT_MS })
}
