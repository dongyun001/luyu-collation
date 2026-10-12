/**
 * 读秒进度条测试。
 *
 * 为什么要单独测：进度条是"预估"而不是真实进度，容易出现两种问题——
 * 时间在停（看着像卡死）或条宽满格（暗示已完成却还没结束）。
 * 这里把这两条边界钉住，顺带钉住"结束后秒表必须停"。
 */

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { collateMock } = vi.hoisted(() => ({ collateMock: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, collate: collateMock }
})

const { useCollationStore, PROGRESS_EXPECTED_S } = await import('./collation')
const { splitTextIntoChunks } = await import('@/utils/textChunks')

/** 约 400 字，必然切成多段。 */
const 长文 = '十年春，齐师伐我。'.repeat(40)

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

function deferred() {
  let resolve
  const promise = new Promise((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('读秒进度条', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    collateMock.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('加载期间按秒自增，结束后停表', async () => {
    const pending = deferred()
    collateMock.mockReturnValue(pending.promise)

    const done = store.submitText('十年春，齐师伐我。')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.status).toBe('loading')
    expect(store.elapsedSeconds).toBe(0)

    await vi.advanceTimersByTimeAsync(3000)
    expect(store.elapsedSeconds).toBe(3)

    pending.resolve(response([]))
    await done
    expect(store.status).toBe('ready')

    // 关键：请求结束后秒表不能继续跑，否则用户会看到一个永远在涨的数字
    await vi.advanceTimersByTimeAsync(5000)
    expect(store.elapsedSeconds).toBe(3)
  })

  it('进度条随秒数推进，但永不满格', async () => {
    const pending = deferred()
    collateMock.mockReturnValue(pending.promise)
    const done = store.submitText('十年春，齐师伐我。')
    await vi.advanceTimersByTimeAsync(0)

    await vi.advanceTimersByTimeAsync(PROGRESS_EXPECTED_S * 1000)
    const 很久之后 = store.progressPercent
    expect(很久之后).toBeGreaterThan(50)
    expect(很久之后).toBeLessThanOrEqual(95)

    pending.resolve(response([]))
    await done
  })

  it('长文本下进度条至少反映已到货段数', async () => {
    const chunks = splitTextIntoChunks(长文)
    const pending = chunks.map(() => deferred())
    let call = 0
    collateMock.mockImplementation(() => {
      const promise = pending[call].promise
      call += 1
      return promise
    })

    const done = store.submitText(长文)
    await vi.advanceTimersByTimeAsync(0)
    // 一段都没到、时间也没走 → 条宽接近 0
    expect(store.progressPercent).toBeLessThan(5)

    pending[0].resolve(response([]))
    await vi.advanceTimersByTimeAsync(0)
    // 只放了 1 段回来：段数占比应立刻把条宽抬起来，不用等时间
    expect(store.progressPercent).toBeGreaterThanOrEqual(
      Math.floor((1 / chunks.length) * 95) - 1,
    )

    pending.slice(1).forEach((entry) => entry.resolve(response([])))
    await done
  })

  it('reset 把秒表归零并停表', async () => {
    const pending = deferred()
    collateMock.mockReturnValue(pending.promise)
    const done = store.submitText('十年春，齐师伐我。')
    await vi.advanceTimersByTimeAsync(2000)
    expect(store.elapsedSeconds).toBe(2)

    store.reset()
    expect(store.elapsedSeconds).toBe(0)

    await vi.advanceTimersByTimeAsync(5000)
    expect(store.elapsedSeconds).toBe(0)

    pending.resolve(response([]))
    await done
  })
})
