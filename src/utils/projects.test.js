/**
 * 本机项目列表测试（F12）。
 *
 * 用可注入的内存 storage 代替真实 localStorage（vitest 跑在 node 环境，没有 DOM）。
 * 重点守：容量降级阶梯（全量 → 砍半 → 只留元信息 → 明确失败）不得静默丢数据，
 * 以及"键相同即覆盖"与筛选排序的边界。
 */

import { describe, expect, it } from 'vitest'

import {
  MAX_PROJECTS,
  clearProjects,
  filterProjects,
  getProject,
  listProjects,
  projectFromCollation,
  removeProject,
  saveProject,
} from './projects'

/** 可限容的内存 storage：超过 limit 字节就抛 QuotaExceededError，模拟配额不足。 */
function fakeStorage(limit = Number.POSITIVE_INFINITY) {
  const map = new Map()
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      const text = String(value)
      if (text.length > limit) {
        const error = new Error('quota exceeded')
        error.name = 'QuotaExceededError'
        throw error
      }
      map.set(key, text)
    },
    removeItem: (key) => {
      map.delete(key)
    },
    size: () => map.size,
  }
}

function collation(overrides = {}) {
  return {
    sourceText: '学而时习之，不亦说乎。',
    items: [
      { id: 1, type: '讹字', status: 'accepted', confidence: 0.95 },
      { id: 2, type: '通假', status: 'pending', confidence: 0.9 },
    ],
    translation: '译文',
    meta: { model: 'mimo-v2.6-pro', referenceEdition: '通行本' },
    ...overrides,
  }
}

function project(overrides = {}) {
  return {
    ...projectFromCollation(collation(), { id: overrides.id || 'p1', now: overrides.now || 1000 }),
    ...overrides,
  }
}

describe('项目记录构造', () => {
  it('从校勘结果算出字数、条目数与三态计数', () => {
    const record = projectFromCollation(collation(), { now: 1234 })
    expect(record.chars).toBe(11)
    expect(record.itemCount).toBe(2)
    expect(record.acceptedCount).toBe(1)
    expect(record.pendingCount).toBe(1)
    expect(record.model).toBe('mimo-v2.6-pro')
    expect(record.createdAt).toBe(1234)
    expect(record.id).toMatch(/^proj_/)
  })

  it('标题取原文首行并截断，空文本给兜底名', () => {
    expect(projectFromCollation(collation()).title).toBe('学而时习之，不亦说乎。')
    expect(projectFromCollation({ sourceText: '', items: [] }).title).toBe('未命名校勘')
    const long = '甲'.repeat(60)
    expect(projectFromCollation({ sourceText: long, items: [] }).title).toHaveLength(24)
  })
})

describe('读写往返', () => {
  it('保存后能读回，且按最近更新在前', () => {
    const storage = fakeStorage()
    saveProject(project({ id: 'p1', updatedAt: 1000 }), storage)
    saveProject(project({ id: 'p2', updatedAt: 2000 }), storage)

    const list = listProjects(storage)
    expect(list.map((entry) => entry.id)).toEqual(['p2', 'p1'])
    expect(getProject('p1', storage).title).toBe('学而时习之，不亦说乎。')
  })

  it('同 id 保存是覆盖而不是新增', () => {
    const storage = fakeStorage()
    saveProject(project({ id: 'p1', title: '旧标题' }), storage)
    saveProject(project({ id: 'p1', title: '新标题' }), storage)
    expect(listProjects(storage)).toHaveLength(1)
    expect(getProject('p1', storage).title).toBe('新标题')
  })

  it('超过上限时丢弃最旧的', () => {
    const storage = fakeStorage()
    for (let index = 0; index < MAX_PROJECTS + 5; index += 1) {
      saveProject(project({ id: `p${index}`, updatedAt: index }), storage)
    }
    const list = listProjects(storage)
    expect(list).toHaveLength(MAX_PROJECTS)
    expect(list[0].id).toBe(`p${MAX_PROJECTS + 4}`)
    expect(list.some((entry) => entry.id === 'p0')).toBe(false)
  })

  it('删除与清空', () => {
    const storage = fakeStorage()
    saveProject(project({ id: 'p1' }), storage)
    saveProject(project({ id: 'p2' }), storage)
    removeProject('p1', storage)
    expect(listProjects(storage).map((entry) => entry.id)).toEqual(['p2'])
    clearProjects(storage)
    expect(listProjects(storage)).toEqual([])
  })

  it('没有可用存储时不炸：读回空列表、写入明确失败', () => {
    expect(listProjects(null)).toEqual([])
    const result = saveProject(project(), null)
    expect(result).toEqual({ ok: false, reason: 'unavailable', stored: 0 })
  })

  it('缓存内容损坏时当作空列表，不影响页面打开', () => {
    const storage = fakeStorage()
    storage.setItem('guji:projects:v1', '{不是 JSON')
    expect(listProjects(storage)).toEqual([])
  })
})

describe('容量降级阶梯', () => {
  it('超大单篇只存元信息，并如实告知', () => {
    const storage = fakeStorage()
    // 用 projectFromCollation 构造，保证 chars 与真实文本一致（元信息要留在库里）
    const huge = projectFromCollation(collation({ sourceText: '甲'.repeat(25000) }), {
      id: 'big',
      now: 1000,
    })
    const result = saveProject(huge, storage)

    expect(result.ok).toBe(true)
    expect(result.reason).toBe('metadata-only')
    const stored = getProject('big', storage)
    expect(stored.contentStripped).toBe(true)
    expect(stored.sourceText).toBeUndefined()
    expect(stored.chars).toBe(25000) // 元信息仍然准确
  })

  it('配额不足时砍掉最旧的再试，而不是整体失败', () => {
    const storage = fakeStorage(4000)
    const result = saveProject(project({ id: 'p1' }), storage)
    expect(result.ok).toBe(true)
    // 再塞若干条，触发"砍半"路径
    for (let index = 2; index <= 10; index += 1) {
      saveProject(project({ id: `p${index}`, updatedAt: index }), storage)
    }
    expect(listProjects(storage).length).toBeLessThan(10)
    expect(listProjects(storage).length).toBeGreaterThan(0)
  })

  it('连元信息都写不下时返回 quota-exceeded，不静默丢数据', () => {
    const storage = fakeStorage(10)
    const result = saveProject(project({ id: 'p1' }), storage)
    expect(result).toEqual({ ok: false, reason: 'quota-exceeded', stored: 0 })
  })
})

describe('筛选与排序', () => {
  const projects = [
    project({ id: 'a', title: '论语选段', chars: 300, itemCount: 5, createdAt: 100, updatedAt: 500 }),
    project({ id: 'b', title: '庄子逍遥游', chars: 1200, itemCount: 2, createdAt: 200, updatedAt: 400 }),
    project({ id: 'c', title: '史记项羽本纪', chars: 800, itemCount: 9, createdAt: 300, updatedAt: 300 }),
  ]

  it('关键词匹配标题与模型名', () => {
    expect(filterProjects(projects, { keyword: '庄' }).map((p) => p.id)).toEqual(['b'])
    expect(filterProjects(projects, { keyword: 'mimo' })).toHaveLength(3)
    expect(filterProjects(projects, { keyword: '不存在' })).toHaveLength(0)
  })

  it('按字数与条目数下限过滤', () => {
    expect(filterProjects(projects, { minChars: 800 }).map((p) => p.id).sort()).toEqual(['b', 'c'])
    expect(filterProjects(projects, { minItems: 5 }).map((p) => p.id).sort()).toEqual(['a', 'c'])
  })

  it('四种排序', () => {
    expect(filterProjects(projects, { sort: 'recent' }).map((p) => p.id)).toEqual(['a', 'b', 'c'])
    expect(filterProjects(projects, { sort: 'oldest' }).map((p) => p.id)).toEqual(['a', 'b', 'c'])
    expect(filterProjects(projects, { sort: 'items' }).map((p) => p.id)).toEqual(['c', 'a', 'b'])
    expect(filterProjects(projects, { sort: 'chars' }).map((p) => p.id)).toEqual(['b', 'c', 'a'])
  })

  it('空入参不报错', () => {
    expect(filterProjects()).toEqual([])
  })
})
