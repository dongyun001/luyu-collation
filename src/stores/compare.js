/**
 * 版本对勘仓库（F13 对校引擎，契约见 API.md §7）。
 *
 * 与 collation/analysis 两个 store 的本质差别：**本 store 不涉及大模型**。
 * 因此没有模型名、没有置信度含义、没有 droppedCount（后端恒 0），
 * 也没有 LLM_* 类错误——错误只有入参、限流与网络三类。
 *
 * 为什么不复用 collation store：
 *  ① 输入形状不同（底本 + 1–3 个参照本，而不是单一文本）；
 *  ② 产出语义不同（版本差异 + 版本存缺，而不是校改建议）；
 *  ③ 生命周期不同（可反复对勘多组本子，不影响主链路的校勘结果）。
 * 它**不参与**演示主链路（粘贴→校勘→采纳/还原→导出），是独立的第二路引擎。
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiError, NETWORK_ERROR, compare } from '@/api/client'
import { buildCollationNote, downloadTextFile, noteFilename } from '@/utils/collationNote'

/** 参照本数量上限，与后端 MAX_REFERENCES 一致（API.md §7）。 */
export const MAX_REFERENCES = 3

/** 错误码 -> 处理建议。这里**不出现** LLM_* / PROVIDER_MISCONFIGURED：对校不调模型。 */
const ERROR_HINTS = {
  INVALID_REQUEST: '请检查底本与每个参照本：底本不能为空、参照本 1–3 个且名称不重复。',
  TEXT_TOO_LONG: '有文本超过 5000 字，请缩短后重试。',
  RATE_LIMITED: '请稍候再试。',
  [NETWORK_ERROR]: '请确认后端已启动，且 VITE_API_BASE 指向正确的地址。',
  INTERNAL_ERROR: '请查看后端日志定位原因。',
}

function toErrorInfo(error) {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message, hint: ERROR_HINTS[error.code] || '' }
  }
  return { code: 'UNKNOWN', message: error?.message || '发生未知错误', hint: '' }
}

/** 一个新的空参照本（`name` 留空由用户填，**不预填演示数据**——质量红线）。 */
function emptyReference() {
  return { name: '', text: '' }
}

export const useCompareStore = defineStore('compare', () => {
  /** 运行代次号：作废过期的在途响应（用户可能连点两次对勘）。 */
  let activeRun = 0

  const baseText = ref('')
  const references = ref([emptyReference()])

  /** idle | running | ready | error */
  const status = ref('idle')
  const items = ref([])
  const presenceDiffs = ref([])
  const meta = ref({ requestId: '', elapsedMs: 0 })
  const error = ref(null)

  // --- getters ---
  const isRunning = computed(() => status.value === 'running')
  const isReady = computed(() => status.value === 'ready')
  const hasResult = computed(() => items.value.length > 0 || presenceDiffs.value.length > 0)
  const itemCount = computed(() => items.value.length)
  const presenceCount = computed(() => presenceDiffs.value.length)
  /** 对勘不出差异也是**有效结论**（"两本此处一致"），界面要能说出这句话 */
  const identical = computed(() => status.value === 'ready' && !hasResult.value)
  const canRun = computed(
    () => baseText.value.trim().length > 0 && references.value.some((ref) => ref.text.trim().length > 0),
  )
  const canAddReference = computed(() => references.value.length < MAX_REFERENCES)
  const canExport = computed(() => items.value.length > 0)
  /** 对勘用到的参照本名（导出的标题与图例都要显示"跟谁比的"）。 */
  const referenceNames = computed(() => references.value.map((ref) => ref.name.trim()).filter(Boolean))

  // --- actions ---
  function setBaseText(value) {
    baseText.value = String(value ?? '')
  }

  function updateReference(index, patch) {
    const target = references.value[index]
    if (!target) return
    references.value[index] = { ...target, ...patch }
  }

  function addReference() {
    if (!canAddReference.value) return false
    references.value.push(emptyReference())
    return true
  }

  function removeReference(index) {
    // 至少留一个：0 个参照本的对勘在契约里就是非法的（API.md §7）
    if (references.value.length <= 1) return false
    references.value.splice(index, 1)
    return true
  }

  /** 触发一次对勘。不调模型，正常在毫秒级返回。 */
  async function run() {
    if (!canRun.value) {
      error.value = {
        code: 'INVALID_REQUEST',
        message: '请填写底本，并至少填写一个参照本',
        hint: ERROR_HINTS.INVALID_REQUEST,
      }
      status.value = 'error'
      return false
    }

    activeRun += 1
    const runId = activeRun
    status.value = 'running'
    error.value = null

    try {
      const payload = references.value
        .map((ref, index) => ({ ref, index }))
        .filter(({ ref }) => ref.text.trim().length > 0)
        .map(({ ref, index }) => ({
          // 未填名称的参照本按**原位置**编号，避免过滤后序号错位
          name: ref.name.trim() || `参照本${index + 1}`,
          text: ref.text,
        }))
      const response = await compare(baseText.value, payload)
      if (runId !== activeRun) return false // 期间又发了一次，丢弃这次响应
      items.value = response.items ?? []
      presenceDiffs.value = response.presenceDiffs ?? []
      meta.value = {
        requestId: response.requestId ?? '',
        elapsedMs: response.elapsedMs ?? 0,
      }
      status.value = 'ready'
      return true
    } catch (err) {
      if (runId !== activeRun) return false
      error.value = toErrorInfo(err)
      status.value = 'error'
      return false
    }
  }

  /**
   * 导出对勘记：纯规则生成，复用主链路的校勘记体例（异文一项已按 `source` 分支渲染）。
   * @returns {{ok: boolean, message?: string, noteText?: string, filename?: string}}
   */
  function exportNote(title = '版本对勘') {
    if (!canExport.value) {
      return { ok: false, message: '尚无异文可导出。两本一致时没有校勘记可写。' }
    }
    const sorted = [...items.value].sort((a, b) => a.offset - b.offset)
    const noteText = buildCollationNote({ items: sorted, title })
    const filename = noteFilename('版本对勘记')
    downloadTextFile(filename, noteText)
    return { ok: true, noteText, filename }
  }

  function clearError() {
    error.value = null
    if (status.value === 'error') status.value = 'idle'
  }

  /** 清空全部状态并作废在途请求。 */
  function reset() {
    activeRun += 1
    baseText.value = ''
    references.value = [emptyReference()]
    items.value = []
    presenceDiffs.value = []
    meta.value = { requestId: '', elapsedMs: 0 }
    error.value = null
    status.value = 'idle'
  }

  return {
    // state
    baseText,
    references,
    status,
    items,
    presenceDiffs,
    meta,
    error,
    // getters
    isRunning,
    isReady,
    hasResult,
    identical,
    itemCount,
    presenceCount,
    canRun,
    canAddReference,
    canExport,
    referenceNames,
    // actions
    setBaseText,
    updateReference,
    addReference,
    removeReference,
    run,
    exportNote,
    clearError,
    reset,
  }
})
