/**
 * 校勘状态仓库（TECH_DESIGN §3）。
 *
 * 主链路的唯一数据来源：原文、AI 建议、译文、决策状态、修改时间线全部在这里，
 * 组件只读这里的数据，不再自带任何演示数据。
 *
 * 长文本走**分段流水线**（PRD §4）：按句读切段、限量并发、每段返回即刷新 items，
 * 于是"校勘一部分就出来一部分"。接口契约不变，仍是多次普通 /collate 调用。
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiError, NETWORK_ERROR, collate as collateRequest } from '@/api/client'
import { buildCollationNote, downloadTextFile, noteFilename } from '@/utils/collationNote'
import {
  PROGRESS_EXPECTED_S,
  asymptoticPercent,
  createElapsedTicker,
} from '@/utils/progressMeter'
import {
  MAX_CONCURRENCY,
  mergeCollationItems,
  rebaseItems,
  splitTextIntoChunks,
} from '@/utils/textChunks'

/** 置信度低于此值的建议折叠为「低置信建议」，且不参与「全部采纳」（API.md §2）。 */
export const LOW_CONFIDENCE_THRESHOLD = 0.7

/** 单次**调用**的文本上限（PRD §5），与后端 MAX_TEXT_LEN 一致。 */
export const MAX_TEXT_LENGTH = 5000

/**
 * 读秒进度条的时间基准（口径见 utils/progressMeter.js）。
 * 从本模块**再导出一份**是为兼容既有导入方（collationProgress.test.js 直接从 './collation' 取它）。
 */
export { PROGRESS_EXPECTED_S }

export const ALL_CHECK_TYPES = ['讹字', '衍文', '脱文', '通假', '异文']

/** 决策状态全集（与 utils/chartData.js 的 STATUS_ORDER 同序） */
export const ALL_DECISION_STATUSES = ['pending', 'accepted', 'rejected']

export const DEFAULT_REFERENCE_EDITION = '通行本'

/** 草稿键：仅存浏览器本地，刷新/切页不丢工作；不是服务端持久化（PRD §4「明确不做」）。 */
const DRAFT_KEY = 'guji:collation-draft:v1'

/** 一份干净的 meta（初始态、reset、载入项目三处共用，避免三份字面量各写一遍）。 */
function makeDefaultMeta() {
  return {
    requestId: '',
    model: '',
    elapsedMs: 0,
    droppedCount: 0,
    referenceEdition: DEFAULT_REFERENCE_EDITION,
    checkTypes: [...ALL_CHECK_TYPES],
    produceTranslation: true,
    chunkCount: 0,
  }
}

/** 错误码 -> 给用户的处理建议（message 用后端返回的那条，这里只补「怎么办」）。 */
const ERROR_HINTS = {
  // 这个码同时覆盖「缺密钥」与「上游不可用（密钥无效/余额不足/5xx）」，
  // 所以建议要把两种情况都点到，不能只说「去填密钥」——否则余额不足时用户会白找一遍
  PROVIDER_MISCONFIGURED: '请确认 .env 中的 LLM_API_KEY 已填写且有效，并确认模型账号的余额或额度充足（可参考 .env.example）。',
  LLM_TIMEOUT: '上游长时间没有新内容产出，已自动重试仍未成功。请稍后重试，或缩短待校勘文本。',
  LLM_BAD_JSON: '大模型输出未通过契约校验，已整条拦截、未渲染脏数据。请重试。',
  RATE_LIMITED: '请稍候再试。',
  [NETWORK_ERROR]: '请确认后端已启动，且 VITE_API_BASE 指向正确的地址。',
  TEXT_TOO_LONG: '请分段提交。',
  INVALID_REQUEST: '请检查输入后重试。',
  INTERNAL_ERROR: '请查看后端日志定位原因。',
}

function nowTime(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function toErrorInfo(error) {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      message: error.message,
      hint: ERROR_HINTS[error.code] || '',
    }
  }
  return {
    code: 'UNKNOWN',
    message: error?.message || '发生未知错误',
    hint: '',
  }
}

/** 读本地草稿；任何异常都当作没有草稿，不能因为缓存坏了就打不开页面。 */
function readDraft() {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const draft = JSON.parse(raw)
    return draft && typeof draft.sourceText === 'string' ? draft : null
  } catch {
    return null
  }
}

export const useCollationStore = defineStore('collation', () => {
  const draft = readDraft()

  /** 运行代次号：并发分段与「重新开始/再次提交」之间的竞态保护（见 runChunks）。 */
  let activeRun = 0

  // --- state ---
  const sourceText = ref(draft?.sourceText ?? '')
  /** 每条：{ id, type, original, suggested, reason, confidence, offset, status } */
  const items = ref(draft?.items ?? [])
  const translation = ref(draft?.translation ?? '')
  const meta = ref(draft?.meta ?? makeDefaultMeta())
  /** 修改时间线：按时间正序存放，展示时倒序。 */
  const history = ref(draft?.history ?? [])
  /** idle | loading | ready | error */
  const status = ref(draft ? 'ready' : 'idle')
  const error = ref(null)
  /** 分段进度：{ done, total }，total<=1 时视图不显示进度条 */
  const progress = ref({ done: 0, total: 0 })
  /**
   * 失败的段：[{ index, code, message }]。
   *
   * 分段彼此独立，所以某段失败不该让整次校勘判死——已到货的结果照常可用，
   * 失败段进这个列表，由视图给出「重试失败段」。
   */
  const failures = ref([])
  /** 失败段重试进行中（按钮置灰用）。 */
  const retryingFailure = ref(false)
  /**
   * 条目筛选条件（F12，2026-10-12 增补）。
   *
   * 放在 collation store 而不是另开 store：筛选对象就是 `items`，同一份数据两处真相
   * 必然漂移（TECH_DESIGN §3）。语义：`types` / `statuses` 是**白名单**、默认全选；
   * 全部取消勾选即"一条都不匹配"，如实反馈，不隐式回落成"全选"。
   */
  const filters = ref({
    types: [...ALL_CHECK_TYPES],
    statuses: [...ALL_DECISION_STATUSES],
    confidenceMin: 0,
    confidenceMax: 1,
    keyword: '',
  })
  /** 本轮的分段计划与选项：重试失败段时要知道每段的文本与全文起点。 */
  let chunkPlan = []
  let lastOptions = null
  /**
   * 正在途中的分段数（已发出请求、还没拿到回复的段）。
   *
   * 为什么要有它：并发 3 而真实上游每段要几十秒时，"已完成 0/6"会在很长时间里纹丝不动，
   * 用户会以为卡死了。把"进行中 3"一起显示出来，才能如实说明"在动"。
   */
  const inFlight = ref(0)
  /** 本次校勘已等待的秒数。status==='loading' 期间按秒自增，供「读秒进度条」显示。 */
  const { seconds: elapsedSeconds, start: startTicking, stop: stopTicking } = createElapsedTicker()

  // --- getters ---
  const pendingItems = computed(() => items.value.filter((item) => item.status === 'pending'))
  const acceptedItems = computed(() => items.value.filter((item) => item.status === 'accepted'))
  const highConfidenceItems = computed(
    () => items.value.filter((item) => item.confidence >= LOW_CONFIDENCE_THRESHOLD),
  )
  const lowConfidenceItems = computed(
    () => items.value.filter((item) => item.confidence < LOW_CONFIDENCE_THRESHOLD),
  )
  /** 高置信建议里还有多少条没被采纳 —— 决定「全部采纳」按钮是否可用。 */
  const acceptableCount = computed(
    () => highConfidenceItems.value.filter((item) => item.status !== 'accepted').length,
  )
  /**
   * 还能被"一键还原"处理掉的条目数 —— 决定「一键还原」按钮是否可用。
   *
   * **必须与 `rejectAll()` 的操作对象同一个集合**（`status !== 'rejected'`）。
   * 旧实现用 `pendingItems.length`（只看 pending），于是出现过这个 bug：
   * 一键还原后再采纳一条，那条是 accepted 而非 pending，按钮就永久禁用了。
   */
  const rejectableCount = computed(
    () => items.value.filter((item) => item.status !== 'rejected').length,
  )
  const isReady = computed(() => status.value === 'ready')
  const isLoading = computed(() => status.value === 'loading')
  const canExport = computed(() => acceptedItems.value.length > 0)
  /** 时间线倒序（最新在前），供视图直接渲染。 */
  const timeline = computed(() => [...history.value].reverse())
  /** 分段进行中已有部分结果 —— 视图据此从「加载屏」切到「部分结果」。
   *  这是「校勘一部分就出来一部分」的开关。 */
  const hasPartialResult = computed(() => isLoading.value && items.value.length > 0)
  /** 是否应展示工作台（而不是加载/错误/空态整屏）。 */
  const showsWorkspace = computed(() => isReady.value || items.value.length > 0)
  /**
   * 分段进度文案。除了"已完成 x/y 段"，还在有在途请求时补"进行中 n"——
   * 并发 3 + 真实上游几十秒/段时，"已完成"会长时间不动，光看它像卡死（见 inFlight 注释）。
   */
  const progressText = computed(() => {
    if (progress.value.total <= 1) return ''
    const base = `已完成 ${progress.value.done}/${progress.value.total} 段`
    return inFlight.value > 0 ? `${base} · 进行中 ${inFlight.value}` : base
  })
  /** 是否有段失败（工作台横条据此显示「重试失败段」）。 */
  const hasFailures = computed(() => failures.value.length > 0)
  /** 失败段里第一段的处理建议，贴在横条上（与整页错误用的是同一套措辞）。 */
  const failureHint = computed(() =>
    failures.value.length ? ERROR_HINTS[failures.value[0].code] || '' : '',
  )
  /**
   * 进度条宽度（百分比）。取「按时间渐近」与「已到货段数占比」的较大者：
   * 前者让单段调用也有可见的推进，后者让长文本的真实进展说话。
   * 算式本身在 utils/progressMeter.js（校勘与分析共用一份）。
   */
  const progressPercent = computed(() => {
    const ratio = progress.value.total > 1 ? progress.value.done / progress.value.total : 0
    return asymptoticPercent(elapsedSeconds.value, ratio, PROGRESS_EXPECTED_S)
  })

  /**
   * 一条条目是否通过当前筛选（F12）。
   * 关键词匹配原文/建议/理由三处——用户找"这个字改了什么"时不一定记得是哪个字段。
   */
  function itemMatchesFilters(item, current) {
    if (!current.types.includes(item.type)) return false
    if (!current.statuses.includes(item.status)) return false
    const confidence = Number(item.confidence)
    if (Number.isFinite(confidence)) {
      if (confidence < Number(current.confidenceMin)) return false
      if (confidence > Number(current.confidenceMax)) return false
    }
    const keyword = String(current.keyword ?? '').trim()
    if (keyword) {
      const haystack = `${item.original ?? ''}${item.suggested ?? ''}${item.reason ?? ''}`
      if (!haystack.includes(keyword)) return false
    }
    return true
  }

  /** 筛选后的条目（工作台列表与看板表格共用同一份口径）。 */
  const filteredItems = computed(() =>
    items.value.filter((item) => itemMatchesFilters(item, filters.value)),
  )

  /** 是否存在"非默认"的筛选条件（供 UI 显示"筛选中"与"清空"按钮）。 */
  const hasActiveFilters = computed(() => {
    const current = filters.value
    return (
      current.types.length !== ALL_CHECK_TYPES.length ||
      current.statuses.length !== ALL_DECISION_STATUSES.length ||
      Number(current.confidenceMin) > 0 ||
      Number(current.confidenceMax) < 1 ||
      String(current.keyword ?? '').trim() !== ''
    )
  })

  const filterStats = computed(() => ({
    matched: filteredItems.value.length,
    total: items.value.length,
    active: hasActiveFilters.value,
  }))

  // --- internals ---
  function pushHistory({ action, from = '', to = '', type = '' }) {
    history.value.push({ time: nowTime(), actor: '当前用户', action, from, to, type })
    saveDraft()
  }

  /** 落草稿。只在有内容时写，避免把空态也存下来。 */
  function saveDraft() {
    try {
      if (!sourceText.value) {
        sessionStorage.removeItem(DRAFT_KEY)
        return
      }
      sessionStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          sourceText: sourceText.value,
          items: items.value,
          translation: translation.value,
          meta: meta.value,
          history: history.value,
        }),
      )
    } catch {
      // 存不下（隐私模式/超额）也不能影响主流程，静默降级
    }
  }

  function clearDraft() {
    try {
      sessionStorage.removeItem(DRAFT_KEY)
    } catch {
      /* 忽略 */
    }
  }

  function validate(text) {
    if (!text.trim()) {
      return { code: 'INVALID_REQUEST', message: '请先粘贴古籍原文', hint: '' }
    }
    if (text.length > MAX_TEXT_LENGTH) {
      return {
        code: 'TEXT_TOO_LONG',
        message: `文本 ${text.length} 字，超过单次上限 ${MAX_TEXT_LENGTH} 字`,
        hint: ERROR_HINTS.TEXT_TOO_LONG,
      }
    }
    return null
  }

  function buildOptions(options) {
    return {
      checkTypes: options.checkTypes ? [...options.checkTypes] : [...ALL_CHECK_TYPES],
      produceTranslation: options.produceTranslation !== false,
      referenceEdition: options.referenceEdition || DEFAULT_REFERENCE_EDITION,
    }
  }

  function applyResult(text, options, chunkCount) {
    sourceText.value = text
    meta.value = { ...meta.value, referenceEdition: options.referenceEdition, checkTypes: options.checkTypes, produceTranslation: options.produceTranslation, chunkCount }
    history.value = []
    pushHistory({
      action: 'AI 自动校勘',
      from: `${text.length} 字原文${chunkCount > 1 ? `（${chunkCount} 段）` : ''}`,
      to: `返回 ${items.value.length} 条建议`,
    })
    if (meta.value.droppedCount > 0) {
      pushHistory({
        action: '输出可靠性控制',
        from: `${meta.value.droppedCount} 条模型建议`,
        to: '不合契约，已丢弃',
      })
    }
    status.value = 'ready'
    error.value = null
    saveDraft()
  }

  /**
   * 逐段跑完所有分段，限量并发；**每段到货就刷新 items**（这就是"一部分就出来一部分"）。
   *
   * 某段失败时**不停下其余段**：分段彼此独立，让用户拿到尽可能多的结果；
   * 失败段收进 `failures`，由视图给「重试失败段」。唯一例外是命中限流——
   * 继续发只会让限流更严重，此时停止派新段。
   *
   * runId 用来作废过期结果：分段是并发的，用户中途「重新开始」或再次提交时，
   * 上一轮迟到的响应不能再写回 store，否则会把已清空的工作台又填上旧建议。
   */
  async function runChunks(chunks, options, runId) {
    const groups = new Array(chunks.length)
    const elapsed = []
    const caught = []
    let nextIndex = 0
    let done = 0
    let stopDispatching = false

    const isStale = () => runId !== activeRun
    progress.value = { done: 0, total: chunks.length }

    const publish = () => {
      if (isStale()) return
      // 传上一版 items：把用户已经做过的采纳/还原决定带过去，避免被本段结果重置
      items.value = mergeCollationItems(groups.filter(Boolean), items.value)
    }

    const worker = async () => {
      while (!stopDispatching && nextIndex < chunks.length && !isStale()) {
        const index = nextIndex
        nextIndex += 1
        const chunk = chunks[index]
        inFlight.value += 1
        try {
          const response = await collateRequest(chunk.text, options)
          if (isStale()) return // 这一轮已被作废，丢弃响应
          groups[index] = rebaseItems(response.items, chunk.start)
          elapsed.push(response.elapsedMs ?? 0)
          if (!meta.value.requestId) meta.value.requestId = response.requestId ?? ''
          meta.value.model = response.model || meta.value.model
          meta.value.droppedCount += response.droppedCount ?? 0
          if (response.translation) {
            translation.value = translation.value ? `${translation.value}\n${response.translation}` : response.translation
          }
          done += 1
          progress.value = { done, total: chunks.length }
          publish() // 每段到货即渲染
        } catch (error) {
          if (isStale()) return
          const info = toErrorInfo(error)
          caught.push({ index, code: info.code, message: info.message })
          if (info.code === 'RATE_LIMITED') stopDispatching = true
        } finally {
          // 无论成功、失败还是提前 return，都要把在途计数还回去，
          // 否则"进行中 n"会永远挂着一个不会减少的数字
          inFlight.value = Math.max(0, inFlight.value - 1)
        }
      }
    }

    await Promise.all(
      Array.from({ length: Math.min(MAX_CONCURRENCY, chunks.length) }, () => worker()),
    )

    if (isStale()) return { done, total: chunks.length, failures: [], stale: true }

    publish()
    meta.value.elapsedMs = elapsed.reduce((sum, value) => sum + value, 0)
    return {
      done,
      total: chunks.length,
      failures: caught.sort((a, b) => a.index - b.index),
      stale: false,
    }
  }

  /**
   * 只重跑失败的段，结果并入现有 items（按「类型+原文+建议」去重、按全文位置排序）。
   *
   * 顺序重跑而不是并发：失败段通常没几条，而它们往往正是因为上游吃紧才失败的，
   * 再并发去撞只会重蹈覆辙。
   */
  async function retryFailedChunks() {
    if (retryingFailure.value || !failures.value.length || !chunkPlan.length) return false
    const runId = activeRun
    const pending = failures.value.map((entry) => entry.index)
    const stillFailed = []
    retryingFailure.value = true
    try {
      for (const index of pending) {
        if (runId !== activeRun) return false // 期间「重新开始」了，丢弃本次重试
        const chunk = chunkPlan[index]
        inFlight.value += 1
        try {
          const response = await collateRequest(chunk.text, lastOptions)
          if (runId !== activeRun) return false
          // 第二参数传上一版：重试期间用户已做的采纳/还原决定同样不能被重置
          items.value = mergeCollationItems(
            [items.value, rebaseItems(response.items, chunk.start)],
            items.value,
          )
          meta.value.droppedCount += response.droppedCount ?? 0
          meta.value.elapsedMs += response.elapsedMs ?? 0
          if (response.translation) {
            translation.value = translation.value
              ? `${translation.value}\n${response.translation}`
              : response.translation
          }
        } catch (error) {
          if (runId !== activeRun) return false
          const info = toErrorInfo(error)
          stillFailed.push({ index, code: info.code, message: info.message })
        } finally {
          inFlight.value = Math.max(0, inFlight.value - 1)
        }
      }
    } finally {
      retryingFailure.value = false
    }
    if (stillFailed.length < pending.length) {
      pushHistory({
        action: '重试未完成的段',
        from: `${pending.length} 段`,
        to: stillFailed.length ? `${stillFailed.length} 段仍失败` : '已全部补齐',
      })
    }
    failures.value = stillFailed
    progress.value = { done: progress.value.total - stillFailed.length, total: progress.value.total }
    saveDraft()
    return stillFailed.length === 0
  }

  // --- actions ---
  /**
   * 提交原文去校勘。
   * @returns {Promise<boolean>} 是否**全部**成功（部分成功时返回 false，但结果已进 store）
   */
  async function submitText(rawText, options = {}) {
    const text = String(rawText ?? '')
    const invalid = validate(text)
    if (invalid) {
      error.value = invalid
      status.value = 'error'
      return false
    }

    const resolvedOptions = buildOptions(options)
    const chunks = splitTextIntoChunks(text)
    activeRun += 1
    const runId = activeRun

    // 重新开始一次校勘：清掉上一轮结果，避免新旧混在一起
    items.value = []
    translation.value = ''
    history.value = []
    // 在途计数按轮清零：上一轮若还有迟到的响应，它只会在自己的 finally 里减，
    // 这里用 Math.max(0, …) 兜住，不让显示层出现负数
    inFlight.value = 0
    meta.value = {
      requestId: '',
      model: '',
      elapsedMs: 0,
      droppedCount: 0,
      referenceEdition: resolvedOptions.referenceEdition,
      checkTypes: resolvedOptions.checkTypes,
      produceTranslation: resolvedOptions.produceTranslation,
      chunkCount: chunks.length,
    }
    sourceText.value = text
    status.value = 'loading'
    error.value = null
    failures.value = []
    // 记下本轮的分段计划与选项：重试失败段要按同样的切分与选项重跑
    chunkPlan = chunks
    lastOptions = resolvedOptions
    // 秒表与 loading 同生共死：无论成功、失败还是被判过期，都在 finally 里收掉
    startTicking()
    let result
    try {
      result = await runChunks(chunks, resolvedOptions, runId)
    } finally {
      stopTicking()
    }
    const { done, failures: chunkFailures, total, stale } = result

    if (stale) return false // 这一轮已被「重新开始」或新提交取代，不要回写任何状态

    // 失败段一律登记：即使"一段都没成功"走整页错误，也要留下可重试的清单
    failures.value = chunkFailures

    // 只有**一段都没成功**才算整次失败（整页错误）。判据必须是「成功的段数」而不是
    // 「建议条数」——干净文本本来就常常 0 条建议，那样会被误判成全部失败。
    if (done === 0 && chunkFailures.length) {
      const first = chunkFailures[0]
      error.value = {
        code: first.code,
        message:
          total > 1
            ? `已完成 0/${total} 段，全部分段失败：${first.message}`
            : first.message,
        hint: ERROR_HINTS[first.code] || '',
      }
      status.value = 'error'
      saveDraft() // 保持既有行为：即使没结果也存一次，草稿里至少有原文
      return false
    }

    // 只要有段成功就进工作台：失败段交给横条 + 「重试失败段」，不盖住已到货的部分
    applyResult(text, resolvedOptions, chunks.length)
    if (chunkFailures.length) {
      // 留痕：部分失败也如实记一笔，别让时间线上看不出这次只跑了一部分
      pushHistory({
        action: '分段校勘部分失败',
        from: `${chunks.length} 段`,
        to: `${chunkFailures.length} 段未完成，可重试`,
      })
    }
    return chunkFailures.length === 0
  }

  function accept(id) {
    const item = items.value.find((entry) => entry.id === id)
    if (!item || item.status === 'accepted') return
    item.status = 'accepted'
    pushHistory({ action: '采纳建议', from: item.original, to: item.suggested, type: item.type })
  }

  function reject(id) {
    const item = items.value.find((entry) => entry.id === id)
    if (!item || item.status === 'rejected') return
    item.status = 'rejected'
    pushHistory({ action: '还原原文', from: item.suggested, to: item.original, type: item.type })
  }

  /** 全部采纳：只覆盖高置信建议，低置信条目不参与（API.md §2）。 */
  function acceptAll() {
    const targets = highConfidenceItems.value.filter((item) => item.status !== 'accepted')
    if (!targets.length) return
    targets.forEach((item) => {
      item.status = 'accepted'
    })
    pushHistory({ action: '全部采纳（高置信）', from: '待处理建议', to: `${targets.length} 条` })
  }

  /** 一键还原：所有条目回到「未采纳」语义下的原文状态。 */
  function rejectAll() {
    const targets = items.value.filter((item) => item.status !== 'rejected')
    if (!targets.length) return
    targets.forEach((item) => {
      item.status = 'rejected'
    })
    pushHistory({ action: '一键还原', from: '全部建议', to: '回到原文' })
  }

  // --- 筛选与统计（F12，纯前端，不调接口） ---

  /** 合并式更新筛选条件（关键词输入、置信度滑块等用）。 */
  function setFilters(patch) {
    filters.value = { ...filters.value, ...patch }
  }

  /** 勾选/取消一个类型；保持与 ALL_CHECK_TYPES 同序，便于比对与测试。 */
  function toggleTypeFilter(type) {
    const set = new Set(filters.value.types)
    if (set.has(type)) set.delete(type)
    else set.add(type)
    filters.value = { ...filters.value, types: ALL_CHECK_TYPES.filter((entry) => set.has(entry)) }
  }

  /** 勾选/取消一个决策状态。 */
  function toggleStatusFilter(status) {
    const set = new Set(filters.value.statuses)
    if (set.has(status)) set.delete(status)
    else set.add(status)
    filters.value = {
      ...filters.value,
      statuses: ALL_DECISION_STATUSES.filter((entry) => set.has(entry)),
    }
  }

  function resetFilters() {
    filters.value = {
      types: [...ALL_CHECK_TYPES],
      statuses: [...ALL_DECISION_STATUSES],
      confidenceMin: 0,
      confidenceMax: 1,
      keyword: '',
    }
  }

  /**
   * 常用预设。`high-pending` 回答"有哪些我可以直接采纳的"，
   * `notes-only` 只看通假/异文（只标注不替换的那两类）。
   */
  function applyFilterPreset(preset) {
    if (preset === 'high-pending') {
      filters.value = {
        ...filters.value,
        statuses: ['pending'],
        confidenceMin: LOW_CONFIDENCE_THRESHOLD,
        confidenceMax: 1,
      }
      return
    }
    if (preset === 'notes-only') {
      filters.value = { ...filters.value, types: ['通假', '异文'] }
      return
    }
    resetFilters()
  }

  /**
   * 采纳"当前筛选结果里的高置信条目"。
   * 与 `acceptAll` 同一条规则（低置信不参与），只是范围收窄到筛选结果——
   * 用户筛出"待处理 + 高置信"后一键处理，不必再被全表牵制。
   */
  function acceptFiltered() {
    const targets = filteredItems.value.filter(
      (item) => item.confidence >= LOW_CONFIDENCE_THRESHOLD && item.status !== 'accepted',
    )
    if (!targets.length) return
    targets.forEach((item) => {
      item.status = 'accepted'
    })
    pushHistory({ action: '采纳筛选中（高置信）', from: '筛选结果', to: `${targets.length} 条` })
  }

  /**
   * 导出规范校勘记（F4）：纯规则生成，不调模型。
   * @returns {{ok: boolean, message?: string, noteText?: string, filename?: string}}
   */
  function exportNote(title = '') {
    if (!canExport.value) {
      return { ok: false, message: '尚无采纳的校勘建议，请先采纳需要写入校勘记的条目。' }
    }
    const accepted = [...acceptedItems.value].sort((a, b) => a.offset - b.offset)
    const noteText = buildCollationNote({
      items: accepted,
      referenceEdition: meta.value.referenceEdition,
      title,
    })
    const filename = noteFilename('校勘记')
    downloadTextFile(filename, noteText)
    pushHistory({ action: '导出校勘记', from: '—', to: filename })
    return { ok: true, noteText, filename }
  }

  /** 清空错误状态（用户重新提交或切回首页时调用）。 */
  function clearError() {
    error.value = null
    if (status.value === 'error') status.value = 'idle'
  }

  /** 清空全部状态（首页重新开始时调用），同时丢弃本地草稿并作废在途分段。 */
  function reset() {
    activeRun += 1 // 让并发中的分段结果失效，否则迟到的响应会把工作台又填上
    stopTicking()
    sourceText.value = ''
    items.value = []
    translation.value = ''
    history.value = []
    status.value = 'idle'
    error.value = null
    progress.value = { done: 0, total: 0 }
    inFlight.value = 0
    elapsedSeconds.value = 0
    failures.value = []
    retryingFailure.value = false
    resetFilters()
    chunkPlan = []
    lastOptions = null
    meta.value = makeDefaultMeta()
    clearDraft()
  }

  /**
   * 从本机项目记录恢复一次校勘结果（F12，**不调模型**）。
   *
   * 用途：项目列表里点「载入」，把当时的结果（原文 + 条目 + 决策状态 + 译文）装回工作台，
   * 继续采纳/导出。恢复后同样落草稿，刷新不丢。
   * 先作废在途分段：否则上一轮迟到的响应会把刚装回来的结果又覆盖掉。
   *
   * @returns {boolean} 是否恢复成功（记录里没有原文就返回 false）
   */
  function restoreProject(record) {
    if (!record || typeof record.sourceText !== 'string' || !record.sourceText) return false
    activeRun += 1
    stopTicking()
    sourceText.value = record.sourceText
    items.value = Array.isArray(record.items) ? record.items.map((item) => ({ ...item })) : []
    translation.value = record.translation ?? ''
    meta.value = { ...makeDefaultMeta(), ...(record.meta ?? {}) }
    history.value = []
    status.value = 'ready'
    error.value = null
    progress.value = { done: 0, total: 0 }
    inFlight.value = 0
    elapsedSeconds.value = 0
    failures.value = []
    retryingFailure.value = false
    resetFilters()
    chunkPlan = []
    lastOptions = null
    pushHistory({
      action: '载入本机项目',
      from: record.title || '未命名校勘',
      to: `${items.value.length} 条建议`,
    })
    return true
  }

  return {
    // state
    sourceText,
    items,
    translation,
    meta,
    history,
    status,
    error,
    progress,
    elapsedSeconds,
    inFlight,
    failures,
    retryingFailure,
    filters,
    // getters
    pendingItems,
    acceptedItems,
    highConfidenceItems,
    lowConfidenceItems,
    acceptableCount,
    rejectableCount,
    isReady,
    isLoading,
    canExport,
    timeline,
    hasPartialResult,
    showsWorkspace,
    progressText,
    progressPercent,
    hasFailures,
    failureHint,
    filteredItems,
    hasActiveFilters,
    filterStats,
    // actions
    submitText,
    retryFailedChunks,
    accept,
    reject,
    acceptAll,
    rejectAll,
    setFilters,
    toggleTypeFilter,
    toggleStatusFilter,
    resetFilters,
    applyFilterPreset,
    acceptFiltered,
    exportNote,
    clearError,
    reset,
    restoreProject,
  }
})
