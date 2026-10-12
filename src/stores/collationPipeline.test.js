/**
 * 分段流水线测试：验证「校勘一部分就出来一部分」这个行为本身。
 *
 * 用 mock 精确控制每段何时返回，才能断言"第一段到货时就已经出现在界面上、
 * 而整体仍在 loading"——这正是用户要的渐进呈现，靠真实模型是测不准的。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { collateMock } = vi.hoisted(() => ({ collateMock: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, collate: collateMock }
})

const { useCollationStore } = await import('./collation')
const { splitTextIntoChunks } = await import('@/utils/textChunks')
// 用真实的 ApiError 构造带 code 的失败，才能覆盖「按错误码分支」的逻辑（如限流收手）
const { ApiError } = await import('@/api/client')

/** 约 400 字，超过默认 220 字目标，必然切成两段。 */
const 长文 = '十年春，齐师伐我。'.repeat(40)

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

function response(items, overrides = {}) {
  return {
    requestId: 'req_test',
    model: 'fake-model',
    elapsedMs: 100,
    items,
    translation: '',
    droppedCount: 0,
    ...overrides,
  }
}

function item(overrides = {}) {
  return {
    id: 1,
    type: '讹字',
    original: '代',
    suggested: '伐',
    reason: '形近而讹',
    confidence: 0.95,
    offset: 3,
    ...overrides,
  }
}

describe('分段流水线', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    collateMock.mockReset()
  })

  it('短文本只发一次调用，不显示分段进度', async () => {
    collateMock.mockResolvedValueOnce(response([item()]))
    await store.submitText('十年春，齐师伐我。')

    expect(collateMock).toHaveBeenCalledTimes(1)
    expect(store.status).toBe('ready')
    expect(store.meta.chunkCount).toBe(1)
    expect(store.progressText).toBe('')
  })

  it('长文本切成多段并分别调用', async () => {
    collateMock.mockResolvedValue(response([]))
    await store.submitText(长文)

    expect(collateMock.mock.calls.length).toBeGreaterThan(1)
    expect(store.meta.chunkCount).toBe(collateMock.mock.calls.length)
    // 每段发出去的都是该段文本，而不是整篇
    for (const [chunkText] of collateMock.mock.calls) {
      expect(chunkText.length).toBeLessThan(长文.length)
    }
  })

  it('第一段到货就渲染出结果，此时整体仍在 loading', async () => {
    const chunks = splitTextIntoChunks(长文)
    const pending = chunks.map(() => deferred())
    let call = 0
    collateMock.mockImplementation(() => {
      const promise = pending[call].promise
      call += 1
      return promise
    })

    const done = store.submitText(长文)
    await tick()
    // 并发度取 min(3, 段数)
    expect(collateMock).toHaveBeenCalledTimes(Math.min(3, chunks.length))

    // 只把第一段放回来
    pending[0].resolve(response([item({ offset: 3 })]))
    await tick()

    expect(store.items).toHaveLength(1)
    expect(store.status).toBe('loading')
    expect(store.hasPartialResult).toBe(true)
    expect(store.showsWorkspace).toBe(true) // 视图据此从加载屏切到部分结果
    // 文案除了"已完成"，还要带上"进行中 n"：并发 3 + 真实上游每段几十秒时，
    // 只显示"已完成 1/4"会在很长时间里不动，看起来像卡死（2026-10-12 修订）
    expect(store.progressText).toContain(`已完成 1/${chunks.length} 段`)
    // 第 1 段回来后，它那个 worker 立刻领走了第 4 段，所以 3 个 worker 又都满了
    expect(store.progressText).toContain('进行中 3')

    // 其余段各给一条**不同**的建议，否则会被跨段去重合并掉
    pending.slice(1).forEach((entry, index) => {
      entry.resolve(response([item({ type: '通假', original: `原文${index}`, suggested: `建议${index}`, offset: 5 })]))
    })
    await done

    expect(store.status).toBe('ready')
    expect(store.items).toHaveLength(chunks.length)
    expect(store.hasPartialResult).toBe(false)
  })

  it('合并时把段内偏移搬到全文坐标系并按位置排序', async () => {
    const chunks = splitTextIntoChunks(长文)
    // 按调用顺序编号（不能按段文本查下标：重复文本会让多段内容相同）
    let call = 0
    collateMock.mockImplementation(() => {
      const index = call
      call += 1
      return Promise.resolve(
        response([item({ original: `原文${index}`, suggested: `建议${index}`, offset: 5 })]),
      )
    })
    await store.submitText(长文)

    // 每段段内偏移 5 都要加上该段起点，且整体按全文位置升序
    expect(store.items.map((entry) => entry.offset)).toEqual(chunks.map((entry) => 5 + entry.start))
  })

  it('同一段内模型重复报的同一条建议只留一条', async () => {
    const 同一条 = item({ offset: 2 })
    collateMock.mockResolvedValue(response([同一条, { ...同一条 }]))

    await store.submitText('十年春，齐师伐我。')

    expect(store.items).toHaveLength(1)
  })

  it('各段各报一条同内容建议时按各自位置分别保留（本就是两处线索）', async () => {
    // 段内 offset 都是 2，但 rebase 后各段落点是全文里**不同**的位置，所以不是"同一条"。
    // 旧实现按「类型+原文+建议」去重会把这些并成一条，等于让第二处永远修不到。
    const chunks = splitTextIntoChunks(长文)
    const 同一条 = item({ offset: 2 })
    collateMock.mockResolvedValue(response([同一条]))

    await store.submitText(长文)

    expect(chunks.length).toBeGreaterThan(1)
    expect(store.items).toHaveLength(chunks.length)
    expect(store.items.map((entry) => entry.offset)).toEqual(
      chunks.map((chunk) => chunk.start + 2),
    )
  })

  it('接口来的条目是未处理状态，跨段 id 不撞车（点哪张改哪张）', async () => {
    // 后端每段都从 id=1 开始编号，所以这里刻意让两段都返回 id=1
    const chunks = splitTextIntoChunks(长文)
    let call = 0
    collateMock.mockImplementation(() => {
      call += 1
      const index = call
      return Promise.resolve(
        response([item({ id: 1, original: `原文${index}`, suggested: `建议${index}`, offset: 3 })]),
      )
    })

    await store.submitText(长文)

    expect(store.items).toHaveLength(chunks.length)
    // id 全表唯一，否则 accept(id) 的 find 永远命中第一条
    expect(new Set(store.items.map((entry) => entry.id)).size).toBe(chunks.length)
    // 状态不是 undefined，「待处理 N 处」与「一键还原」才可用
    expect(store.pendingItems).toHaveLength(chunks.length)

    const second = store.items[1]
    store.accept(second.id)
    expect(store.items[1].status).toBe('accepted')
    expect(store.items[0].status).toBe('pending') // 关键：没有连带改到第一张
  })

  it('等待期间采纳过的条目，不被后续段的合并结果重置', async () => {
    const chunks = splitTextIntoChunks(长文)
    const pending = chunks.map(() => deferred())
    let call = 0
    collateMock.mockImplementation(() => {
      const promise = pending[call].promise
      call += 1
      return promise
    })

    const done = store.submitText(长文)
    await tick()

    // 第一段到货，用户在等待期间就采纳它
    pending[0].resolve(response([item({ original: '原文0', suggested: '建议0', offset: 3 })]))
    await tick()
    store.accept(store.items[0].id)
    expect(store.items[0].status).toBe('accepted')

    // 其余段陆续到货，每段都触发一次 publish()（从模型原始返回重建整张列表）
    pending.slice(1).forEach((entry, index) => {
      entry.resolve(
        response([item({ original: `原文${index + 1}`, suggested: `建议${index + 1}`, offset: 5 })]),
      )
    })
    await done

    const accepted = store.items.filter((entry) => entry.status === 'accepted')
    expect(accepted).toHaveLength(1)
    expect(accepted[0].original).toBe('原文0')
  })

  it('译文按段拼接', async () => {
    const chunks = splitTextIntoChunks(长文)
    let call = 0
    collateMock.mockImplementation(() => {
      const index = call
      call += 1
      return Promise.resolve(response([], { translation: `第 ${index + 1} 段译文。` }))
    })
    await store.submitText(长文)

    expect(store.translation).toBe(chunks.map((_, index) => `第 ${index + 1} 段译文。`).join('\n'))
  })

  it('某段失败不停下其余段，已到货结果保留、可继续用', async () => {
    const chunks = splitTextIntoChunks(长文)
    let call = 0
    collateMock.mockImplementation(() => {
      call += 1
      const index = call
      // 第二段失败，其余段照常成功
      return index === 2
        ? Promise.reject(new Error('上游炸了'))
        : Promise.resolve(
            response([item({ original: `原文${index}`, suggested: `建议${index}`, offset: 3 })]),
          )
    })

    const ok = await store.submitText(长文)

    expect(ok).toBe(false) // 不是"全部成功"
    // 关键：有结果就进工作台（status=ready），不整页报错把用户已经拿到的部分盖掉
    expect(store.status).toBe('ready')
    expect(store.showsWorkspace).toBe(true)
    // 关键：失败之后仍然把剩下的段跑完了，而不是就地停下
    expect(collateMock.mock.calls.length).toBe(chunks.length)
    expect(store.items).toHaveLength(chunks.length - 1)
    expect(store.hasFailures).toBe(true)
    expect(store.failures).toHaveLength(1)
  })

  it('干净的段（0 条建议）不算失败：有段成功就进工作台', async () => {
    // 复现过的真实 bug：干净文本本来就常 0 条建议，若按"建议条数"判全会把
    // 「2 段成功、1 段失败」误报成「已完成 0/3 段，全部分段失败」。
    const chunks = splitTextIntoChunks(长文)
    let call = 0
    collateMock.mockImplementation(() => {
      call += 1
      const index = call
      // 每段都成功，但都不报建议；只有最后一段真失败
      return index === chunks.length
        ? Promise.reject(new Error('最后一段炸了'))
        : Promise.resolve(response([]))
    })

    const ok = await store.submitText(长文)

    expect(ok).toBe(false)
    expect(store.status).toBe('ready') // 不是整页错误
    expect(store.items).toHaveLength(0)
    expect(store.hasFailures).toBe(true)
    expect(store.showsWorkspace).toBe(true)
  })

  it('一段都没成功时才整页报错', async () => {
    collateMock.mockRejectedValue(new Error('上游全炸了'))

    const ok = await store.submitText(长文)

    expect(ok).toBe(false)
    expect(store.status).toBe('error')
    expect(store.items).toHaveLength(0)
    expect(store.showsWorkspace).toBe(false)
    expect(store.error.message).toContain('全部分段失败')
  })

  it('命中限流时停止派新段（继续发只会更糟）', async () => {
    const chunks = splitTextIntoChunks(长文)
    const rateLimited = new ApiError('RATE_LIMITED', '请求过于频繁，请约 30 秒后重试')
    collateMock.mockRejectedValue(rateLimited)

    await store.submitText(长文)

    // 首波并发 3 段全部撞限流后就该收手，不再派第 4 段
    expect(collateMock.mock.calls.length).toBeLessThan(chunks.length)
    expect(store.hasFailures).toBe(true)
  })

  it('重试失败段：只重跑失败的那几段，结果并入现有建议', async () => {
    const chunks = splitTextIntoChunks(长文)
    let call = 0
    collateMock.mockImplementation(() => {
      call += 1
      const index = call
      return index === 2
        ? Promise.reject(new Error('偶发失败'))
        : Promise.resolve(
            response([item({ original: `原文${index}`, suggested: `建议${index}`, offset: 3 })]),
          )
    })

    await store.submitText(长文)
    const 失败段数 = store.failures.length
    expect(失败段数).toBe(1)
    const 已有条数 = store.items.length
    const 首轮调用数 = collateMock.mock.calls.length

    // 重试时让失败段成功，并再补一条建议（验证是"并入"而不是"覆盖"）
    collateMock.mockImplementation(() =>
      Promise.resolve(
        response([
          item({ original: '补录原文', suggested: '补录建议', offset: 5 }),
        ]),
      ),
    )
    const ok = await store.retryFailedChunks()

    expect(ok).toBe(true)
    expect(collateMock.mock.calls.length - 首轮调用数).toBe(失败段数) // 只重跑了失败段
    expect(store.hasFailures).toBe(false)
    expect(store.items).toHaveLength(已有条数 + 1)
    expect(store.items.map((entry) => entry.offset)).toEqual(
      [...store.items.map((entry) => entry.offset)].sort((a, b) => a - b),
    )
  })

  it('重试仍失败时保留失败列表，不会把失败悄悄吞掉', async () => {
    collateMock.mockRejectedValue(new Error('一直失败'))
    await store.submitText(长文)
    const 失败段数 = store.failures.length

    const ok = await store.retryFailedChunks()

    expect(ok).toBe(false)
    expect(store.hasFailures).toBe(true)
    expect(store.failures).toHaveLength(失败段数)
  })

  it('累计各段耗时与丢弃条数', async () => {
    collateMock.mockResolvedValue(response([], { elapsedMs: 100, droppedCount: 1 }))
    await store.submitText(长文)

    const 段数 = store.meta.chunkCount
    expect(段数).toBeGreaterThan(1)
    expect(store.meta.elapsedMs).toBe(100 * 段数)
    expect(store.meta.droppedCount).toBe(段数)
  })

  it('重新提交会清掉上一轮结果，不出现新旧混杂', async () => {
    collateMock.mockResolvedValue(response([item()]))
    await store.submitText('十年春，齐师伐我。')
    expect(store.items).toHaveLength(1)

    collateMock.mockResolvedValue(response([]))
    await store.submitText('公将战，曹刿请见。')
    expect(store.items).toHaveLength(0)
    expect(store.sourceText).toBe('公将战，曹刿请见。')
  })
})
