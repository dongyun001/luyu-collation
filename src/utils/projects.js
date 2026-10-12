/**
 * 本机项目列表（F12）：把一次校勘的成果存进 `localStorage`，供"项目列表"页检索与重载。
 *
 * 定位（重要）：这是**浏览器本地暂存**，与 sessionStorage 草稿同性质，
 * **不是服务端持久化**——后端仍是无状态的（PRD §4「明确不做」）。
 * 换一台机器/换一个浏览器就看不到，UI 上必须如实这么说。
 *
 * 存储可注入（`storage` 参数）：生产默认用 `localStorage`，
 * 测试传一个内存实现即可，不必依赖浏览器环境。
 *
 * 容量纪律：localStorage 一般只有 5MB 左右。写入失败时按"先丢最旧、再只留元信息"的顺序降级，
 * 并把结果如实返回给调用方（不静默丢数据）。
 */

const STORAGE_KEY = 'guji:projects:v1'

/** 最多保留多少个项目；超出时丢弃最旧的。 */
export const MAX_PROJECTS = 30

/** 明细分片上限：单篇超过这个体量就只存元信息，避免一次写入就顶爆配额。 */
const CONTENT_CHAR_LIMIT = 20000

function defaultStorage() {
  try {
    return globalThis.localStorage ?? null
  } catch {
    // 隐私模式等场景下访问 localStorage 本身就会抛错
    return null
  }
}

function readAll(storage) {
  if (!storage) return []
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((entry) => entry && typeof entry.id === 'string') : []
  } catch {
    return [] // 缓存坏了也不能让页面打不开
  }
}

function writeAll(projects, storage) {
  if (!storage) return { ok: false, reason: 'unavailable', stored: 0 }
  if (!projects.length) {
    try {
      storage.removeItem(STORAGE_KEY)
    } catch {
      /* 忽略 */
    }
    return { ok: true, reason: '', stored: 0 }
  }

  // 降级阶梯：全量 -> 砍一半（丢最旧） -> 只留元信息
  const attempts = [projects, projects.slice(0, Math.max(1, Math.floor(projects.length / 2)))]
  for (const candidate of attempts) {
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(candidate))
      return { ok: true, reason: '', stored: candidate.length }
    } catch {
      /* 配额不足，试下一档 */
    }
  }

  const metadataOnly = projects.map(stripContent)
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(metadataOnly))
    return { ok: true, reason: 'metadata-only', stored: metadataOnly.length }
  } catch {
    return { ok: false, reason: 'quota-exceeded', stored: 0 }
  }
}

/** 去掉正文与条目，只留可列表展示的元信息。 */
function stripContent(project) {
  const { sourceText, items, translation, ...rest } = project
  return { ...rest, contentStripped: true }
}

function makeId() {
  return `proj_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 由一次校勘的结果生成项目记录。
 * @param {{sourceText: string, items: Array, translation?: string, meta?: object}} collation
 * @param {{title?: string, now?: number}} [options]
 */
export function projectFromCollation(collation, options = {}) {
  const sourceText = String(collation?.sourceText ?? '')
  const items = Array.isArray(collation?.items) ? collation.items : []
  const meta = collation?.meta ?? {}
  const firstLine = sourceText.trim().split(/\r?\n/)[0] || '未命名校勘'
  const now = options.now ?? Date.now()

  return {
    id: options.id || makeId(),
    title: options.title || firstLine.slice(0, 24),
    createdAt: now,
    updatedAt: now,
    chars: sourceText.length,
    itemCount: items.length,
    acceptedCount: items.filter((item) => item.status === 'accepted').length,
    pendingCount: items.filter((item) => item.status === 'pending').length,
    model: meta.model || '',
    referenceEdition: meta.referenceEdition || '',
    sourceText,
    items,
    translation: collation?.translation ?? '',
    meta,
  }
}

/** 读取项目列表（按最近更新在前）。 */
export function listProjects(storage = defaultStorage()) {
  return readAll(storage).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
}

/** 取单个项目；内容被降级剥离时 `contentStripped` 为 true。 */
export function getProject(id, storage = defaultStorage()) {
  return readAll(storage).find((project) => project.id === id) || null
}

/**
 * 保存（按 id 覆盖或新增）。
 * @returns {{ok: boolean, reason: string, stored: number}}
 *   reason: '' 正常 | 'metadata-only' 仅存元信息 | 'quota-exceeded' 完全写不下 | 'unavailable' 无存储
 */
export function saveProject(record, storage = defaultStorage()) {
  if (!record || !record.id) return { ok: false, reason: 'invalid', stored: 0 }

  const oversized = String(record.sourceText ?? '').length > CONTENT_CHAR_LIMIT
  const incoming = oversized ? stripContent(record) : record
  const existing = readAll(storage)
  const index = existing.findIndex((project) => project.id === incoming.id)
  const merged =
    index >= 0
      ? existing.map((project, i) => (i === index ? { ...project, ...incoming } : project))
      : [incoming, ...existing]

  const trimmed = merged
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    .slice(0, MAX_PROJECTS)

  const result = writeAll(trimmed, storage)
  if (result.ok && oversized && !result.reason) return { ...result, reason: 'metadata-only' }
  return result
}

/** 删除一个项目。 */
export function removeProject(id, storage = defaultStorage()) {
  const next = readAll(storage).filter((project) => project.id !== id)
  return writeAll(next, storage)
}

/** 清空全部项目。 */
export function clearProjects(storage = defaultStorage()) {
  return writeAll([], storage)
}

export const SORT_OPTIONS = [
  { value: 'recent', label: '最近更新' },
  { value: 'oldest', label: '最早创建' },
  { value: 'items', label: '校勘点最多' },
  { value: 'chars', label: '篇幅最长' },
]

/**
 * 筛选 + 排序。纯函数，便于测试与在视图里自由组合。
 * @param {Array} projects
 * @param {{keyword?: string, minChars?: number, minItems?: number, sort?: string}} filters
 */
export function filterProjects(projects = [], filters = {}) {
  const keyword = String(filters.keyword ?? '').trim()
  const minChars = Number(filters.minChars) || 0
  const minItems = Number(filters.minItems) || 0

  const filtered = projects.filter((project) => {
    if ((project.chars || 0) < minChars) return false
    if ((project.itemCount || 0) < minItems) return false
    if (keyword) {
      const haystack = `${project.title ?? ''}${project.model ?? ''}`
      if (!haystack.includes(keyword)) return false
    }
    return true
  })

  const sort = filters.sort || 'recent'
  const sorted = [...filtered]
  if (sort === 'oldest') sorted.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
  else if (sort === 'items') sorted.sort((a, b) => (b.itemCount || 0) - (a.itemCount || 0))
  else if (sort === 'chars') sorted.sort((a, b) => (b.chars || 0) - (a.chars || 0))
  else sorted.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))

  return sorted
}
