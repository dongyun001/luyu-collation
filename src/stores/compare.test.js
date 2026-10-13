/**
 * 版本对勘仓库测试（F13）。
 *
 * 重点不在"能拿到数据"，而在几处**容易做错**的地方：
 *  ① 对勘不出差异 ≠ 失败（要有 `identical` 这种明确结论，而不是空白页）；
 *  ② 参照本为空的那一条不应发给后端（后端会因空 text 之外的原因误判，
 *     而"只填了一个参照本"是正常用法）；
 *  ③ 导出体例不重复（对校条目自带 source，不能套异文体例拼出重复句）；
 *  ④ 连点两次对勘时，迟到的响应不得覆盖后一次的结果。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual('@/api/client')
  return { ...actual, compare: vi.fn() }
})

vi.mock('@/utils/collationNote', async () => {
  const actual = await vi.importActual('@/utils/collationNote')
  return {
    ...actual,
    downloadTextFile: vi.fn(),
    noteFilename: vi.fn(() => '版本对勘记_20261013-1200.txt'),
  }
})

import { ApiError, compare } from '@/api/client'
import { downloadTextFile } from '@/utils/collationNote'
import { MAX_REFERENCES, useCompareStore } from '@/stores/compare'

const BASE = '豫章故郡，洪都新府。'
const OTHER = '南昌故郡，洪都新府。'

describe('compare store', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCompareStore()
    vi.clearAllMocks()
  })

  function fillBaseAndReference(name = '甲本', text = OTHER) {
    store.setBaseText(BASE)
    store.updateReference(0, { name, text })
  }

  it('初始状态只有一个空参照本，且没有预填任何演示数据', () => {
    expect(store.references).toHaveLength(1)
    expect(store.references[0]).toEqual({ name: '', text: '' })
    expect(store.baseText).toBe('')
    expect(store.canRun).toBe(false)
  })

  it('参照本最多 3 个，且至少保留 1 个', () => {
    expect(store.addReference()).toBe(true)
    expect(store.addReference()).toBe(true)
    expect(store.addReference()).toBe(false)
    expect(store.references).toHaveLength(MAX_REFERENCES)

    expect(store.removeReference(0)).toBe(true)
    expect(store.references).toHaveLength(2)
    store.removeReference(0)
    expect(store.removeReference(0)).toBe(false)
    expect(store.references).toHaveLength(1)
  })

  it('底本或参照本为空时不发请求', async () => {
    expect(await store.run()).toBe(false)
    expect(compare).not.toHaveBeenCalled()
    expect(store.error.code).toBe('INVALID_REQUEST')

    store.setBaseText(BASE)
    expect(await store.run()).toBe(false)
    expect(compare).not.toHaveBeenCalled()
  })

  it('只把填了文本的参照本发出去，空名称按位置补默认名', async () => {
    compare.mockResolvedValue({ requestId: 'req_1', elapsedMs: 3, items: [], presenceDiffs: [] })
    store.setBaseText(BASE)
    store.addReference()
    store.updateReference(0, { name: '', text: OTHER }) // 第一个留空名
    store.updateReference(1, { name: '乙本', text: BASE })

    await store.run()

    expect(compare).toHaveBeenCalledWith(BASE, [
      { name: '参照本1', text: OTHER },
      { name: '乙本', text: BASE },
    ])
  })

  it('成功时写入 items / presenceDiffs / meta，状态为 ready', async () => {
    compare.mockResolvedValue({
      requestId: 'req_abc',
      elapsedMs: 7,
      items: [
        { id: 1, type: '异文', original: '豫章', suggested: '南昌', reason: '「甲本」作「南昌」', offset: 0, confidence: 1.0, source: '甲本' },
      ],
      presenceDiffs: [{ source: '甲本', kind: 'reference-extra', text: '，龙光射斗', offset: 9 }],
      droppedCount: 0,
    })
    fillBaseAndReference()

    expect(await store.run()).toBe(true)
    expect(store.isReady).toBe(true)
    expect(store.itemCount).toBe(1)
    expect(store.presenceCount).toBe(1)
    expect(store.meta.requestId).toBe('req_abc')
    expect(store.error).toBeNull()
  })

  it('两本一致时是「有结论」而不是空状态', async () => {
    compare.mockResolvedValue({ requestId: 'req_same', elapsedMs: 1, items: [], presenceDiffs: [] })
    fillBaseAndReference('甲本', BASE)

    await store.run()

    expect(store.isReady).toBe(true)
    expect(store.hasResult).toBe(false)
    expect(store.identical).toBe(true)
    expect(store.canExport).toBe(false) // 没有异文就没有校勘记可写
  })

  it('失败时带上处理建议，且不保留半截结果', async () => {
    compare.mockRejectedValue(new ApiError('TEXT_TOO_LONG', '底本超过 5000 字', 413))
    fillBaseAndReference()

    expect(await store.run()).toBe(false)
    expect(store.status).toBe('error')
    expect(store.error.code).toBe('TEXT_TOO_LONG')
    expect(store.error.hint).toContain('5000 字')
    expect(store.items).toEqual([])
    expect(store.canExport).toBe(false)
  })

  it('连点两次对勘：迟到的响应不覆盖后一次结果', async () => {
    let resolveFirst
    compare.mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveFirst = resolve
      }),
    )
    fillBaseAndReference()
    const first = store.run()

    compare.mockResolvedValueOnce({
      requestId: 'req_second',
      elapsedMs: 2,
      items: [
        { id: 1, type: '异文', original: '甲', suggested: '乙', reason: '「乙本」作「乙」', offset: 0, confidence: 1.0, source: '乙本' },
      ],
      presenceDiffs: [],
    })
    const second = store.run()
    await second

    // 后一次已经完成，此时第一次的响应才到
    resolveFirst({ requestId: 'req_first', elapsedMs: 9, items: [], presenceDiffs: [] })
    expect(await first).toBe(false)

    expect(store.meta.requestId).toBe('req_second')
    expect(store.itemCount).toBe(1)
  })

  it('导出对勘记用对校体例，别本名进句子且不重复', () => {
    store.items = [
      { id: 1, type: '异文', original: '豫章', suggested: '南昌', reason: '「甲本」作「南昌」', offset: 0, confidence: 1, source: '甲本' },
    ]
    const result = store.exportNote('底本对勘 · 甲本')

    expect(result.ok).toBe(true)
    expect(result.noteText).toContain('校勘记——底本对勘 · 甲本')
    expect(result.noteText).toContain('「豫章」，甲本作「南昌」。')
    // 不能出现「一作「南昌」，「甲本」作「南昌」」这种重复句
    expect(result.noteText).not.toContain('一作')
    expect(downloadTextFile).toHaveBeenCalledWith('版本对勘记_20261013-1200.txt', result.noteText)
  })

  it('没有异文时导出给出可读的原因', () => {
    const result = store.exportNote()
    expect(result.ok).toBe(false)
    expect(result.message).toContain('无异文')
    expect(downloadTextFile).not.toHaveBeenCalled()
  })

  it('reset 清空输入与结果，并作废在途响应', async () => {
    let resolveRun
    compare.mockImplementation(
      () => new Promise((resolve) => {
        resolveRun = resolve
      }),
    )
    fillBaseAndReference()
    const pending = store.run()

    store.reset()
    resolveRun({ requestId: 'req_late', elapsedMs: 1, items: [], presenceDiffs: [] })

    expect(await pending).toBe(false)
    expect(store.status).toBe('idle')
    expect(store.baseText).toBe('')
    expect(store.references).toEqual([{ name: '', text: '' }])
    expect(store.meta.requestId).toBe('')
  })
})
