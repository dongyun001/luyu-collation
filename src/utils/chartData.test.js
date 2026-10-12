/**
 * 图表换算层测试（docs/VISUAL.md）。
 *
 * 这一层的价值就在于"图的坐标是可断言的"：火山图的增减、直方图的分箱边界、
 * 雷达的 missing→0、图谱的悬空边过滤，全部在这里钉死，避免图形悄悄撒谎。
 */

import { describe, expect, it } from 'vitest'

import { LOW_CONFIDENCE_THRESHOLD } from '../stores/collation'
import {
  DEFAULT_CONFIDENCE_THRESHOLD,
  KIND_COLORS,
  TYPE_COLORS,
  TYPE_ORDER,
  collectKnowledgePoints,
  confidenceHistogram,
  confidenceSignificance,
  confidenceThresholdSignificance,
  dimensionRadar,
  editImpact,
  knowledgeGraph,
  levenshtein,
  overallStats,
  positionStrip,
  statusStacked,
  typeDistribution,
  volcanoPoints,
} from './chartData'

/** 造一条校勘条目，只写关心的字段。 */
function 条目(overrides = {}) {
  return {
    id: 1,
    type: '讹字',
    original: '日',
    suggested: '曰',
    reason: '形近而讹',
    confidence: 0.95,
    offset: 3,
    status: 'pending',
    ...overrides,
  }
}

describe('阈值常量', () => {
  it('与 collation store 的低置信阈值同值（防止两处漂移）', () => {
    expect(DEFAULT_CONFIDENCE_THRESHOLD).toBe(LOW_CONFIDENCE_THRESHOLD)
  })
})

describe('levenshtein / editImpact', () => {
  it('相同串距离为 0', () => {
    expect(levenshtein('曰', '曰')).toBe(0)
  })

  it('单字替换距离为 1（讹字类的典型形态）', () => {
    expect(levenshtein('日', '曰')).toBe(1)
    expect(editImpact(条目())).toBe(1)
  })

  it('空串按长度计', () => {
    expect(levenshtein('', '其名为鲲')).toBe(4)
    expect(levenshtein('其名为鲲', '')).toBe(4)
  })

  it('多字删补距离等于改动字数（脱文/衍文的典型形态）', () => {
    expect(editImpact(条目({ type: '脱文', original: '其名鲲', suggested: '其名为鲲' }))).toBe(1)
    expect(editImpact(条目({ type: '衍文', original: '舍舍去', suggested: '舍去' }))).toBe(1)
    expect(editImpact(条目({ type: '异文', original: '豫章故郡', suggested: '南昌故郡' }))).toBe(2)
  })
})

describe('confidenceSignificance', () => {
  it('单调递增，且 0.7 处与参照值一致', () => {
    const low = confidenceSignificance(0.6)
    const mid = confidenceSignificance(0.7)
    const high = confidenceSignificance(0.9)
    expect(low).toBeLessThan(mid)
    expect(mid).toBeLessThan(high)
    expect(mid).toBeCloseTo(0.5229, 3)
    expect(high).toBeCloseTo(1, 5)
  })

  it('confidence=1 不发散（夹到 0.995）', () => {
    expect(Number.isFinite(confidenceSignificance(1))).toBe(true)
    expect(confidenceSignificance(1)).toBeCloseTo(2.301, 3)
  })

  it('非法置信度按 0 处理而不是 NaN', () => {
    expect(Number.isFinite(confidenceSignificance(undefined))).toBe(true)
    expect(Number.isFinite(confidenceSignificance('abc'))).toBe(true)
  })

  it('阈值显著性由同一函数导出，不在视图里写死', () => {
    expect(confidenceThresholdSignificance(0.7)).toBeCloseTo(0.5229, 3)
  })
})

describe('typeDistribution', () => {
  it('固定五类、固定顺序，零计数也保留', () => {
    const result = typeDistribution([条目(), 条目({ type: '通假' })])
    expect(result.map((row) => row.type)).toEqual(TYPE_ORDER)
    expect(result).toHaveLength(5)
    expect(result.find((row) => row.type === '讹字').value).toBe(1)
    expect(result.find((row) => row.type === '衍文').value).toBe(0)
  })

  it('颜色与 theme.css 的类型色同值', () => {
    const result = typeDistribution([])
    for (const row of result) {
      expect(row.color).toBe(TYPE_COLORS[row.type])
    }
  })

  it('忽略类型不在五类内的脏数据', () => {
    const result = typeDistribution([条目({ type: '不存在的类型' })])
    expect(result.reduce((sum, row) => sum + row.value, 0)).toBe(0)
  })
})

describe('confidenceHistogram', () => {
  it('分箱默认 0.50–1.00、步长 0.05、共 10 箱', () => {
    const { bins, threshold } = confidenceHistogram([])
    expect(bins).toHaveLength(10)
    expect(bins[0].label).toBe('0.50–0.55')
    expect(bins[9].label).toBe('0.95–1.00')
    expect(threshold).toBe(DEFAULT_CONFIDENCE_THRESHOLD)
  })

  it('低于起点并入首箱、超出末端的并入末箱（不丢样本）', () => {
    const { bins } = confidenceHistogram([
      条目({ confidence: 0.1 }),
      条目({ confidence: 0.5 }),
      条目({ confidence: 0.999 }),
    ])
    expect(bins[0].count).toBe(2)
    expect(bins[9].count).toBe(1)
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(3)
  })

  it('按箱边界正确落位', () => {
    const { bins } = confidenceHistogram([条目({ confidence: 0.72 }), 条目({ confidence: 0.75 })])
    // 0.70–0.75 是第 5 箱（index 4）；0.75 归入 0.75–0.80（index 5）
    expect(bins[4].count).toBe(1)
    expect(bins[5].count).toBe(1)
  })

  it('非法置信度不计入任何箱', () => {
    const { bins } = confidenceHistogram([条目({ confidence: undefined })])
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(0)
  })
})

describe('statusStacked', () => {
  it('每个类型一根柱、三个状态段', () => {
    const items = [
      条目({ type: '讹字', status: 'accepted' }),
      条目({ type: '讹字', status: 'pending' }),
      条目({ type: '脱文', status: 'rejected' }),
    ]
    const { categories, series } = statusStacked(items)
    expect(categories).toEqual(TYPE_ORDER)
    expect(series.map((s) => s.key)).toEqual(['pending', 'accepted', 'rejected'])
    const accepted = series.find((s) => s.key === 'accepted')
    expect(accepted.data[TYPE_ORDER.indexOf('讹字')]).toBe(1)
    expect(accepted.data[TYPE_ORDER.indexOf('脱文')]).toBe(0)
  })
})

describe('positionStrip', () => {
  it('按类型映射泳道、保留 offset', () => {
    const { lanes, points } = positionStrip([条目({ offset: 12, type: '脱文' })], 100)
    expect(lanes).toEqual(TYPE_ORDER)
    expect(points[0].value).toEqual([12, TYPE_ORDER.indexOf('脱文')])
  })

  it('过滤没有合法 offset 的条目', () => {
    const { points } = positionStrip([条目({ offset: undefined }), 条目({ offset: 3 })], 100)
    expect(points).toHaveLength(1)
  })

  it('xMax 至少为 1，且取文本长度与最大 offset 的较大者', () => {
    expect(positionStrip([], 0).xMax).toBe(1)
    expect(positionStrip([条目({ offset: 500 })], 100).xMax).toBe(500)
  })
})

describe('volcanoPoints', () => {
  it('x 为改动字符数、y 为置信显著性，并给出两条阈值线', () => {
    const { points, thresholds, xMax } = volcanoPoints([
      条目({ original: '日', suggested: '曰', confidence: 0.7 }),
    ])
    expect(points[0].value[0]).toBe(1)
    expect(points[0].value[1]).toBeCloseTo(0.5229, 3)
    expect(thresholds.x).toBe(1.5)
    expect(thresholds.y).toBeCloseTo(0.5229, 3)
    expect(thresholds.confidence).toBe(DEFAULT_CONFIDENCE_THRESHOLD)
    expect(xMax).toBe(2) // 全是单字改动时也要留出"单字/多字"分界的显示空间
  })

  it('多字改动落在阈值线右侧', () => {
    const { points } = volcanoPoints([
      条目({ original: '其名鲲', suggested: '其名为鲲', confidence: 0.9 }),
    ])
    expect(points[0].value[0]).toBe(1)
    const { points: 多字 } = volcanoPoints([
      条目({ original: '豫章故郡', suggested: '南昌故郡', confidence: 0.9 }),
    ])
    expect(多字[0].value[0]).toBe(2)
  })

  it('空数据不报错，阈值仍可用', () => {
    const { points, xMax } = volcanoPoints([])
    expect(points).toEqual([])
    expect(xMax).toBe(2)
  })
})

describe('overallStats', () => {
  it('三态计数、高置信率与均值', () => {
    const stats = overallStats([
      条目({ status: 'accepted', confidence: 0.9 }),
      条目({ status: 'pending', confidence: 0.5 }),
      条目({ status: 'rejected', confidence: 0.8 }),
    ])
    expect(stats.total).toBe(3)
    expect(stats.accepted).toBe(1)
    expect(stats.pending).toBe(1)
    expect(stats.rejected).toBe(1)
    expect(stats.highConfidence).toBe(2)
    expect(stats.lowConfidence).toBe(1)
    expect(stats.highConfidenceRate).toBe(67)
    expect(stats.meanConfidence).toBeCloseTo(0.733, 3)
  })

  it('空集合不除零', () => {
    const stats = overallStats([])
    expect(stats.total).toBe(0)
    expect(stats.highConfidenceRate).toBe(0)
    expect(stats.meanConfidence).toBe(0)
  })

  it('类型计数固定五类', () => {
    const stats = overallStats([条目({ type: '衍文' })])
    expect(Object.keys(stats.typeCounts)).toEqual(TYPE_ORDER)
    expect(stats.typeCounts.衍文).toBe(1)
  })
})

describe('dimensionRadar', () => {
  it('missing 的维度记 0 并单独标出（0 表示未能判断，不是判断为否）', () => {
    const { indicators, values, missingLabels, uncertainLabels } = dimensionRadar([
      { key: 'authorship', label: '作者与编纂', confidence: 0.88 },
      { key: 'dating', label: '成书年代', confidence: 0, missing: true, uncertain: true },
      { key: 'edition', label: '版本与流传', confidence: 0.4, uncertain: true },
    ])
    expect(indicators.map((i) => i.name)).toEqual(['作者与编纂', '成书年代', '版本与流传'])
    expect(values).toEqual([0.88, 0, 0.4])
    expect(missingLabels).toEqual(['成书年代'])
    // 未判断的维度不再重复出现在"存疑"里：后端补 missing 时也会置 uncertain=true，
    // 不排掉的话同一根轴会被两句各点一次名
    expect(uncertainLabels).toEqual(['版本与流传'])
  })

  it('置信度越界会被夹到 [0,1]', () => {
    const { values } = dimensionRadar([{ label: 'X', confidence: 3 }])
    expect(values).toEqual([1])
  })

  it('非数组入参不报错', () => {
    expect(dimensionRadar(undefined).indicators).toEqual([])
  })
})

describe('knowledgeGraph', () => {
  it('悬空边（端点不在实体里）与自环被丢弃', () => {
    const { nodes, links } = knowledgeGraph(
      [
        { name: '孔子', kind: '人物', note: '儒家创始人' },
        { name: '《论语》', kind: '著作', note: '语录体' },
      ],
      [
        { source: '孔子', target: '《论语》', relation: '言论被辑录于' },
        { source: '孔子', target: '不存在的人', relation: '无依据' },
        { source: '孔子', target: '孔子', relation: '自指' },
      ],
    )
    expect(nodes).toHaveLength(2)
    expect(links).toHaveLength(1)
    expect(links[0].relation).toBe('言论被辑录于')
  })

  it('节点分类与配色按 kind 映射，未知 kind 归为人物', () => {
    const { nodes, categories } = knowledgeGraph([{ name: 'X', kind: '莫名其妙' }], [])
    expect(nodes[0].kind).toBe('人物')
    expect(nodes[0].itemStyle.color).toBe(KIND_COLORS['人物'])
    expect(categories.length).toBeGreaterThanOrEqual(6)
  })

  it('连接度越大节点越大（枢纽实体一眼可见）', () => {
    const { nodes } = knowledgeGraph(
      [
        { name: '孔子', kind: '人物' },
        { name: '《论语》', kind: '著作' },
        { name: '儒家', kind: '学派' },
      ],
      [
        { source: '孔子', target: '《论语》', relation: 'r' },
        { source: '孔子', target: '儒家', relation: 'r' },
      ],
    )
    const 孔子 = nodes.find((n) => n.name === '孔子')
    const 论语 = nodes.find((n) => n.name === '《论语》')
    expect(孔子.symbolSize).toBeGreaterThan(论语.symbolSize)
  })

  it('缺 name 的实体被过滤', () => {
    const { nodes } = knowledgeGraph([{ kind: '人物' }, { name: '孔子', kind: '人物' }], [])
    expect(nodes).toHaveLength(1)
  })
})

describe('collectKnowledgePoints', () => {
  it('跨维度去重并带上来源维度', () => {
    const result = collectKnowledgePoints([
      { label: '作者与编纂', knowledgePoints: ['四书之一', '「论」读 lún'] },
      { label: '学派与思想', knowledgePoints: ['四书之一', '儒家核心典籍'] },
    ])
    expect(result.map((row) => row.text)).toEqual(['四书之一', '「论」读 lún', '儒家核心典籍'])
    expect(result[0].dimension).toBe('作者与编纂')
  })

  it('空/非数组不报错', () => {
    expect(collectKnowledgePoints(undefined)).toEqual([])
    expect(collectKnowledgePoints([{ label: 'X' }])).toEqual([])
  })
})
