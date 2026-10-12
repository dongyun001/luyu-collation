/**
 * 项目载入（restoreProject）测试（F12）。
 *
 * 这条路径不调模型，是"从本机项目列表把当时的结果装回工作台"。
 * 要守住三件事：① 条目是**深拷贝**（改工作台不会回写项目库里的那份）；
 * ② 三态决策被完整带回来（不是全 pending）；③ 载入后能正常导出校勘记。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useCollationStore } from './collation'

function record(overrides = {}) {
  return {
    id: 'proj_1',
    title: '论语选段',
    sourceText: '子曰：日学而时习之。',
    items: [
      { id: 1, type: '讹字', original: '日学而时习之', suggested: '学而时习之', reason: '形近而讹', confidence: 0.95, offset: 3, status: 'accepted' },
      { id: 2, type: '通假', original: '说', suggested: '悦', reason: '音近相通', confidence: 0.9, offset: 14, status: 'pending' },
    ],
    translation: '孔子说……',
    meta: { model: 'mimo-v2.6-pro', referenceEdition: '通行本', chunkCount: 1 },
    ...overrides,
  }
}

describe('restoreProject', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
  })

  it('把原文、条目、译文、meta 装回工作台并进入 ready', () => {
    const ok = store.restoreProject(record())
    expect(ok).toBe(true)
    expect(store.status).toBe('ready')
    expect(store.sourceText).toBe('子曰：日学而时习之。')
    expect(store.items).toHaveLength(2)
    expect(store.translation).toBe('孔子说……')
    expect(store.meta.model).toBe('mimo-v2.6-pro')
    // meta 里没给的字段回落到默认值，而不是 undefined
    expect(store.meta.produceTranslation).toBe(true)
    expect(store.meta.droppedCount).toBe(0)
  })

  it('原样带回三态决策（已采纳的不被重置为待处理）', () => {
    store.restoreProject(record())
    expect(store.acceptedItems.map((item) => item.id)).toEqual([1])
    expect(store.pendingItems.map((item) => item.id)).toEqual([2])
    expect(store.canExport).toBe(true)
  })

  it('条目是深拷贝：在工作台改状态不会污染传进来的记录', () => {
    const source = record()
    store.restoreProject(source)
    store.reject(2)
    expect(source.items[1].status).toBe('pending')
    expect(store.items[1].status).toBe('rejected')
  })

  it('载入写一条时间线，且把上一次的筛选清掉', () => {
    store.setFilters({ keyword: '其名' })
    store.restoreProject(record())
    expect(store.hasActiveFilters).toBe(false)
    expect(store.timeline[0].action).toBe('载入本机项目')
  })

  it('记录里没有原文时拒绝载入，且不改动当前状态', () => {
    store.restoreProject(record())
    const ok = store.restoreProject({ id: 'x', items: [] })
    expect(ok).toBe(false)
    expect(store.sourceText).toBe('子曰：日学而时习之。')
  })

  it('载入后能被 reset 清干净', () => {
    store.restoreProject(record())
    store.reset()
    expect(store.sourceText).toBe('')
    expect(store.items).toEqual([])
    expect(store.status).toBe('idle')
  })
})
