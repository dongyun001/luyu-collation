/**
 * 条目筛选与统计测试（F12）。
 *
 * 筛选是"用户看到的"与"数据实际有的"之间的唯一口径，所以边界要钉死：
 * 白名单语义（全不选=零结果，不隐式回落全选）、置信度区间闭合、
 * 关键词跨三字段、以及"采纳筛选中"仍守低置信不参与的规则。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { ALL_CHECK_TYPES, LOW_CONFIDENCE_THRESHOLD, useCollationStore } from './collation'

function item(overrides) {
  return {
    id: 1,
    type: '讹字',
    original: '日',
    suggested: '曰',
    reason: '形近而讹',
    confidence: 0.95,
    offset: 2,
    status: 'pending',
    ...overrides,
  }
}

function seed(store, items) {
  store.sourceText = '学而时习之，不亦说乎。'
  store.items = items.map((entry) => ({ ...entry }))
  store.status = 'ready'
  store.history = []
}

const 样本 = [
  item({ id: 1, type: '讹字', original: '日', suggested: '曰', reason: '形近而讹', confidence: 0.95, status: 'pending' }),
  item({ id: 2, type: '通假', original: '说', suggested: '悦', reason: '音近相通', confidence: 0.9, status: 'pending' }),
  item({ id: 3, type: '衍文', original: '舍舍去', suggested: '舍去', reason: '误重一字', confidence: 0.62, status: 'pending' }),
  item({ id: 4, type: '异文', original: '豫章', suggested: '南昌', reason: '别本作「南昌」', confidence: 0.8, status: 'accepted' }),
  item({ id: 5, type: '脱文', original: '其名鲲', suggested: '其名为鲲', reason: '据对文补', confidence: 0.55, status: 'rejected' }),
]

describe('筛选：默认不筛', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    seed(store, 样本)
  })

  it('默认全选，filteredItems 等于 items', () => {
    expect(store.hasActiveFilters).toBe(false)
    expect(store.filteredItems).toHaveLength(样本.length)
    expect(store.filterStats).toEqual({ matched: 5, total: 5, active: false })
  })

  it('类型白名单保持 ALL_CHECK_TYPES 的顺序', () => {
    expect(store.filters.types).toEqual(ALL_CHECK_TYPES)
  })
})

describe('筛选：类型与状态', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    seed(store, 样本)
  })

  it('取消某类型即把它排除', () => {
    store.toggleTypeFilter('讹字')
    expect(store.filteredItems.map((entry) => entry.id)).not.toContain(1)
    expect(store.filterStats.matched).toBe(4)
  })

  it('全部取消勾选时零结果（如实反馈，不隐式回落成全选）', () => {
    for (const type of ALL_CHECK_TYPES) store.toggleTypeFilter(type)
    expect(store.filterStats.matched).toBe(0)
    expect(store.hasActiveFilters).toBe(true)
  })

  it('按状态筛选：只看待处理', () => {
    store.toggleStatusFilter('accepted')
    store.toggleStatusFilter('rejected')
    expect(store.filteredItems.every((entry) => entry.status === 'pending')).toBe(true)
    expect(store.filterStats.matched).toBe(3)
  })
})

describe('筛选：置信度区间与关键词', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    seed(store, 样本)
  })

  it('置信度下限把低置信挡在外面（区间闭合：等于下限算命中）', () => {
    store.setFilters({ confidenceMin: LOW_CONFIDENCE_THRESHOLD })
    expect(store.filteredItems.map((entry) => entry.id).sort()).toEqual([1, 2, 4])
  })

  it('置信度上下限同时生效', () => {
    store.setFilters({ confidenceMin: 0.6, confidenceMax: 0.85 })
    expect(store.filteredItems.map((entry) => entry.id).sort()).toEqual([3, 4])
  })

  it('关键词跨原文/建议/理由三处匹配', () => {
    store.setFilters({ keyword: '其名' })
    expect(store.filteredItems.map((entry) => entry.id)).toEqual([5])
    store.setFilters({ keyword: '形近' })
    expect(store.filteredItems.map((entry) => entry.id)).toEqual([1])
    store.setFilters({ keyword: '悦' })
    expect(store.filteredItems.map((entry) => entry.id)).toEqual([2])
  })

  it('纯空白关键词视同未填', () => {
    store.setFilters({ keyword: '   ' })
    expect(store.hasActiveFilters).toBe(false)
    expect(store.filterStats.matched).toBe(5)
  })
})

describe('筛选预设与复位', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    seed(store, 样本)
  })

  it('high-pending：只看高置信且待处理', () => {
    store.applyFilterPreset('high-pending')
    expect(store.filteredItems.map((entry) => entry.id).sort()).toEqual([1, 2])
  })

  it('notes-only：只看通假与异文', () => {
    store.applyFilterPreset('notes-only')
    expect(store.filteredItems.map((entry) => entry.id).sort()).toEqual([2, 4])
  })

  it('reset 预设与 resetFilters 都回到默认', () => {
    store.applyFilterPreset('notes-only')
    expect(store.hasActiveFilters).toBe(true)
    store.applyFilterPreset('reset')
    expect(store.hasActiveFilters).toBe(false)
    store.setFilters({ keyword: 'x' })
    store.resetFilters()
    expect(store.filterStats.matched).toBe(5)
  })

  it('store.reset() 会把筛选一并复位（不留上一个文档的筛选条件）', () => {
    store.setFilters({ keyword: '其名' })
    store.reset()
    expect(store.hasActiveFilters).toBe(false)
  })
})

describe('采纳筛选中：仍守低置信不参与的规则', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useCollationStore()
    seed(store, 样本)
  })

  it('只采纳筛选结果里的高置信条目', () => {
    store.applyFilterPreset('high-pending') // 命中 id 1(0.95) 与 id 2(0.9)
    store.acceptFiltered()
    const byId = Object.fromEntries(store.items.map((entry) => [entry.id, entry.status]))
    expect(byId[1]).toBe('accepted')
    expect(byId[2]).toBe('accepted')
    expect(byId[3]).toBe('pending') // 低置信，未参与
    expect(byId[5]).toBe('rejected') // 不在筛选结果里，不受影响
    expect(store.timeline[0].action).toBe('采纳筛选中（高置信）')
  })

  it('筛选结果里没有高置信条目时不动任何东西、不写时间线', () => {
    store.setFilters({ confidenceMax: 0.6 })
    const before = store.items.map((entry) => entry.status)
    store.acceptFiltered()
    expect(store.items.map((entry) => entry.status)).toEqual(before)
    expect(store.history).toHaveLength(0)
  })
})
