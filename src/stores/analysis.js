/**
 * 多维度文献分析仓库（F9，契约见 API.md §6）。
 *
 * 为什么独立于 collation store：
 *  ① 分析是**用户显式触发**的一次额外模型调用（不挂在主链路上），有自己的 loading/error，
 *     失败时只在看板上提示，不能污染校勘结果；
 *  ② 它的生命周期与"一次校勘"不同——可以只重新分析、不动校勘结果。
 *
 * 幻觉与作废控制：
 *  - 结果一律带 `sampled` 与 `droppedCount`，由视图如实展示（"基于节选""丢弃 N 条"）；
 *  - 用户换了一篇原文后再触发分析时，用运行代次号作废在途响应，避免把上一篇的判断
 *    挂到下一篇上（与 collation store 的 activeRun 同一手法）。
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiError, NETWORK_ERROR, analyzeText } from '@/api/client'
import { collectKnowledgePoints } from '@/utils/chartData'

/** 错误码 -> 给用户的处理建议（与 collation store 同一套措辞，只留本端点会用到的几个）。 */
const ERROR_HINTS = {
  PROVIDER_MISCONFIGURED:
    '请确认 .env 中的 LLM_API_KEY 已填写且有效，并确认模型账号的余额或额度充足。',
  LLM_TIMEOUT: '上游长时间没有新内容产出，已自动重试仍未成功。请稍后重试。',
  LLM_BAD_JSON: '模型输出未通过契约校验，已整条拦截、未渲染脏数据。请重试。',
  RATE_LIMITED: '请稍候再试。',
  [NETWORK_ERROR]: '请确认后端已启动，且 VITE_API_BASE 指向正确的地址。',
  INVALID_REQUEST: '请检查输入后重试。',
  TEXT_TOO_LONG: '文本过长，请缩短后重试。',
  INTERNAL_ERROR: '请查看后端日志定位原因。',
}

function toErrorInfo(error) {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message, hint: ERROR_HINTS[error.code] || '' }
  }
  return { code: 'UNKNOWN', message: error?.message || '发生未知错误', hint: '' }
}

const EMPTY_META = {
  requestId: '',
  model: '',
  elapsedMs: 0,
  analyzedChars: 0,
  sampled: false,
  droppedCount: 0,
}

export const useAnalysisStore = defineStore('analysis', () => {
  /** 运行代次号：作废过期的在途响应（见文件头说明）。 */
  let activeRun = 0

  /** idle | loading | ready | error */
  const status = ref('idle')
  const dimensions = ref([])
  const entities = ref([])
  const relations = ref([])
  const meta = ref({ ...EMPTY_META })
  const error = ref(null)
  /** 本次分析对应的原文内容（视图据此判断"分析结果是不是当前这篇的"）。 */
  const analyzedText = ref('')

  // --- getters ---
  const isLoading = computed(() => status.value === 'loading')
  const isReady = computed(() => status.value === 'ready')
  const hasResult = computed(() => dimensions.value.length > 0)
  /** 作出判断的维度（missing=false）；雷达与卡片都按它统计"判了几个" */
  const judgedDimensions = computed(() => dimensions.value.filter((dimension) => !dimension.missing))
  const missingDimensions = computed(() => dimensions.value.filter((dimension) => dimension.missing))
  const uncertainDimensions = computed(() =>
    dimensions.value.filter((dimension) => !dimension.missing && dimension.uncertain),
  )
  /** 是否有可画的实体—关系图（只有实体也算有图，只是没有边）。 */
  const hasGraph = computed(() => entities.value.length > 0)
  /** 各维度知识点汇总（去重后摊平，按维度分组展示）。 */
  const knowledgePoints = computed(() => collectKnowledgePoints(dimensions.value))

  // --- actions ---
  /**
   * 触发一次分析。
   * @param {string} text 原文
   * @param {{dimensions?: string[]}} [options]
   * @returns {Promise<boolean>} 是否成功
   */
  async function analyze(text, options = {}) {
    const source = String(text ?? '')
    if (!source.trim()) {
      error.value = { code: 'INVALID_REQUEST', message: '请先完成一次校勘，或提供待分析文本', hint: '' }
      status.value = 'error'
      return false
    }

    activeRun += 1
    const runId = activeRun
    status.value = 'loading'
    error.value = null

    try {
      const response = await analyzeText(source, options.dimensions)
      if (runId !== activeRun) return false // 期间又被重新分析/被重置，丢弃这次响应
      dimensions.value = response.dimensions ?? []
      entities.value = response.entities ?? []
      relations.value = response.relations ?? []
      meta.value = {
        requestId: response.requestId ?? '',
        model: response.model ?? '',
        elapsedMs: response.elapsedMs ?? 0,
        analyzedChars: response.analyzedChars ?? 0,
        sampled: Boolean(response.sampled),
        droppedCount: response.droppedCount ?? 0,
      }
      analyzedText.value = source
      status.value = 'ready'
      return true
    } catch (err) {
      if (runId !== activeRun) return false
      error.value = toErrorInfo(err)
      status.value = 'error'
      return false
    }
  }

  /** 清空错误（用户重试前调用）。 */
  function clearError() {
    error.value = null
    if (status.value === 'error') status.value = 'idle'
  }

  /** 清空全部状态（重新开始一次校勘时调用），并作废在途分析。 */
  function reset() {
    activeRun += 1
    status.value = 'idle'
    dimensions.value = []
    entities.value = []
    relations.value = []
    meta.value = { ...EMPTY_META }
    error.value = null
    analyzedText.value = ''
  }

  return {
    // state
    status,
    dimensions,
    entities,
    relations,
    meta,
    error,
    analyzedText,
    // getters
    isLoading,
    isReady,
    hasResult,
    judgedDimensions,
    missingDimensions,
    uncertainDimensions,
    hasGraph,
    knowledgePoints,
    // actions
    analyze,
    clearError,
    reset,
  }
})
