/**
 * 多维度分析仓库测试（F9）。
 *
 * 重点守三条：① 失败不抛出、只落 error（视图据此单独提示，不连坐校勘结果）；
 * ② 换文本/重置后在途响应被作废（否则上一篇的判断会挂到下一篇上）；
 * ③ getters 对 missing / uncertain 的统计口径与 docs/VISUAL.md §4 一致。
 */

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { analyzeTextMock } = vi.hoisted(() => ({ analyzeTextMock: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, analyzeText: analyzeTextMock }
})

const { useAnalysisStore } = await import('./analysis')
const { ApiError } = await import('@/api/client')

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function response(overrides = {}) {
  return {
    requestId: 'req_test',
    model: 'fake-model',
    elapsedMs: 1200,
    analyzedChars: 44,
    sampled: false,
    dimensions: [
      {
        key: 'authorship',
        label: '作者与编纂',
        judgment: '孔子弟子及再传弟子纂辑。',
        evidence: ['《汉书·艺文志》著录为孔子弟子所记'],
        confidence: 0.88,
        uncertain: false,
        missing: false,
        knowledgePoints: ['四书之一'],
      },
      {
        key: 'edition',
        label: '版本与流传',
        judgment: '本段文本信息不足，未能判断',
        evidence: [],
        confidence: 0,
        uncertain: true,
        missing: true,
        knowledgePoints: [],
      },
    ],
    entities: [{ name: '孔子', kind: '人物', note: '儒家创始人' }],
    relations: [],
    droppedCount: 2,
    ...overrides,
  }
}

describe('成功路径', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAnalysisStore()
    analyzeTextMock.mockReset()
  })

  it('写入四个结果块并保留 meta 的可信度信息', async () => {
    analyzeTextMock.mockResolvedValue(response())
    const ok = await store.analyze('子曰：学而时习之。')

    expect(ok).toBe(true)
    expect(store.isReady).toBe(true)
    expect(store.dimensions).toHaveLength(2)
    expect(store.entities).toHaveLength(1)
    expect(store.meta).toEqual({
      requestId: 'req_test',
      model: 'fake-model',
      elapsedMs: 1200,
      analyzedChars: 44,
      sampled: false,
      droppedCount: 2,
    })
    // 空文本以外，参数原样透传
    expect(analyzeTextMock).toHaveBeenCalledWith('子曰：学而时习之。', undefined)
  })

  it('dimensions 子集会被透传（只分析感兴趣的维度）', async () => {
    analyzeTextMock.mockResolvedValue(response())
    await store.analyze('文本', { dimensions: ['authorship'] })
    expect(analyzeTextMock).toHaveBeenCalledWith('文本', ['authorship'])
  })

  it('getters 区分「已判断 / 未判断 / 存疑」', async () => {
    analyzeTextMock.mockResolvedValue(response())
    await store.analyze('文本')
    expect(store.judgedDimensions.map((d) => d.key)).toEqual(['authorship'])
    expect(store.missingDimensions.map((d) => d.key)).toEqual(['edition'])
    expect(store.uncertainDimensions).toHaveLength(0)
    expect(store.hasResult).toBe(true)
    expect(store.hasGraph).toBe(true)
  })

  it('知识点按维度汇总且去重', async () => {
    analyzeTextMock.mockResolvedValue(
      response({
        dimensions: [
          { key: 'a', label: '作者与编纂', judgment: 'x', evidence: ['e'], confidence: 0.9, missing: false, knowledgePoints: ['四书之一'] },
          { key: 'c', label: '学派与思想', judgment: 'y', evidence: ['e'], confidence: 0.9, missing: false, knowledgePoints: ['四书之一', '儒家典籍'] },
        ],
      }),
    )
    await store.analyze('文本')
    expect(store.knowledgePoints.map((row) => row.text)).toEqual(['四书之一', '儒家典籍'])
  })

  it('空文本不调接口，直接落错误', async () => {
    const ok = await store.analyze('   ')
    expect(ok).toBe(false)
    expect(analyzeTextMock).not.toHaveBeenCalled()
    expect(store.status).toBe('error')
    expect(store.error.code).toBe('INVALID_REQUEST')
  })
})

describe('失败与降级', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAnalysisStore()
    analyzeTextMock.mockReset()
  })

  it('失败不抛出，只把错误落进 error 并附处理建议', async () => {
    analyzeTextMock.mockRejectedValue(new ApiError('LLM_BAD_JSON', '模型输出未通过契约校验'))
    const ok = await store.analyze('文本')

    expect(ok).toBe(false)
    expect(store.status).toBe('error')
    expect(store.error.code).toBe('LLM_BAD_JSON')
    expect(store.error.hint).toContain('重试')
    // 失败时不保留旧结果，避免"上一篇的判断 + 这一篇的报错"混在一起
    expect(store.dimensions).toEqual([])
  })

  it('网络层失败映射成 NETWORK_ERROR 提示起后端', async () => {
    analyzeTextMock.mockRejectedValue(new ApiError('NETWORK_ERROR', '连不上'))
    await store.analyze('文本')
    expect(store.error.hint).toContain('后端')
  })

  it('clearError 把 error 状态复位为 idle，便于重试', async () => {
    analyzeTextMock.mockRejectedValue(new ApiError('LLM_TIMEOUT', '停滞'))
    await store.analyze('文本')
    store.clearError()
    expect(store.error).toBeNull()
    expect(store.status).toBe('idle')
  })
})

describe('作废在途响应', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAnalysisStore()
    analyzeTextMock.mockReset()
  })

  it('重置之后迟到的响应不得写回（避免把上一篇的判断挂到下一篇上）', async () => {
    const pending = deferred()
    analyzeTextMock.mockReturnValue(pending.promise)

    const promise = store.analyze('第一篇')
    store.reset()
    pending.resolve(response())
    await promise
    await tick()

    expect(store.dimensions).toEqual([])
    expect(store.status).toBe('idle')
  })

  it('后一次分析的结果覆盖前一次的在途结果', async () => {
    const first = deferred()
    analyzeTextMock.mockReturnValueOnce(first.promise)
    const firstPromise = store.analyze('第一篇')

    analyzeTextMock.mockReturnValueOnce(Promise.resolve(response({ requestId: 'req_second' })))
    await store.analyze('第二篇')

    first.resolve(response({ requestId: 'req_first' }))
    await firstPromise
    await tick()

    expect(store.meta.requestId).toBe('req_second')
    expect(store.analyzedText).toBe('第二篇')
  })
})

describe('读秒进度（F9 分析也要给用户看得见的在动）', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAnalysisStore()
    analyzeTextMock.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('加载期间按秒自增，结束后停表', async () => {
    const pending = deferred()
    analyzeTextMock.mockReturnValue(pending.promise)

    const done = store.analyze('文本')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.isLoading).toBe(true)
    expect(store.elapsedSeconds).toBe(0)

    await vi.advanceTimersByTimeAsync(3000)
    expect(store.elapsedSeconds).toBe(3)

    pending.resolve(response())
    await done
    expect(store.status).toBe('ready')

    // 关键：结束后秒表必须停，否则用户看到一个永远在涨的数字
    await vi.advanceTimersByTimeAsync(5000)
    expect(store.elapsedSeconds).toBe(3)
  })

  it('条宽随秒数推进，但永不满格', async () => {
    const pending = deferred()
    analyzeTextMock.mockReturnValue(pending.promise)
    const done = store.analyze('文本')
    await vi.advanceTimersByTimeAsync(0)

    const 起初 = store.progressPercent
    await vi.advanceTimersByTimeAsync(30_000)
    const 之后 = store.progressPercent
    expect(之后).toBeGreaterThan(起初)
    expect(之后).toBeLessThanOrEqual(95)

    await vi.advanceTimersByTimeAsync(600_000)
    expect(store.progressPercent).toBe(95) // 封顶

    pending.resolve(response())
    await done
  })

  it('失败也要停表（否则报错后秒数还在涨）', async () => {
    analyzeTextMock.mockRejectedValue(new ApiError('LLM_TIMEOUT', '停滞'))
    await store.analyze('文本')
    expect(store.status).toBe('error')

    // 要守的性质是"不再涨"，而不是某个具体秒数——拒绝是即时发生的，
    // 具体值取决于微任务与定时器的先后，断言它反而脆
    const 失败时 = store.elapsedSeconds
    await vi.advanceTimersByTimeAsync(5000)
    expect(store.elapsedSeconds).toBe(失败时)
  })

  it('reset 把秒表归零', async () => {
    const pending = deferred()
    analyzeTextMock.mockReturnValue(pending.promise)
    const done = store.analyze('文本')
    await vi.advanceTimersByTimeAsync(4000)
    expect(store.elapsedSeconds).toBe(4)

    store.reset()
    expect(store.elapsedSeconds).toBe(0)
    expect(store.progressPercent).toBe(0)

    pending.resolve(response())
    await done
  })
})
