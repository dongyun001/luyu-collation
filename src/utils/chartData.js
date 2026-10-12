/**
 * 图表与统计的**纯函数**换算层（docs/VISUAL.md §1 原则 2）。
 *
 * 为什么单独一层：把 "items → 图表配置" 变成可断言的纯函数，
 * Vue 组件只负责把返回值喂给 ECharts，逻辑错误在 `npm test` 就能抓到，
 * 不必靠肉眼看图。
 *
 * 坐标与阈值的定义见 docs/VISUAL.md §2/§3/§4；改口径先改那份文档，再改这里。
 * 本文件**不依赖** Vue/Pinia，保持可在纯 node 环境测试。
 */

/** 五类校勘类型：顺序固定，雷达/图例/堆叠柱都按它排，保证多图之间同序可比。 */
export const TYPE_ORDER = ['讹字', '衍文', '脱文', '通假', '异文']

/** 类型色：与 src/styles/theme.css 的 --type-* 必须同值（徽标与图表共用一套色）。 */
export const TYPE_COLORS = {
  讹字: '#c0392b',
  衍文: '#b7791f',
  脱文: '#2b6cb0',
  通假: '#6b46c1',
  异文: '#2c7a7b',
}

export const STATUS_ORDER = ['pending', 'accepted', 'rejected']

export const STATUS_LABELS = {
  pending: '待处理',
  accepted: '已采纳',
  rejected: '已还原',
}

export const STATUS_COLORS = {
  pending: '#8b1a1a',
  accepted: '#2e8b57',
  rejected: '#9aa0a6',
}

/** 知识图谱节点分类（API.md §6 的 entities[].kind）。 */
export const KIND_ORDER = ['人物', '著作', '学派', '地名', '职官', '年代']

export const KIND_COLORS = {
  人物: '#8b1a1a',
  著作: '#2b6cb0',
  学派: '#6b46c1',
  地名: '#2c7a7b',
  职官: '#b7791f',
  年代: '#8a8a8a',
}

/**
 * 高置信阈值。**必须与 `stores/collation.js` 的 `LOW_CONFIDENCE_THRESHOLD` 同值**，
 * 由 `chartData.test.js` 断言二者相等来防止漂移（这里不复用导入，是为了让本模块
 * 保持零依赖、可在纯 node 下测试）。
 */
export const DEFAULT_CONFIDENCE_THRESHOLD = 0.7

/** 火山图横轴阈值：单字改动(1) vs 多字删补(≥2) 的分界（docs/VISUAL.md §3）。 */
export const VOLCANO_X_THRESHOLD = 1.5

/** 置信度夹取范围：conf=1 会让 -log10(1-conf) 发散，故夹到 0.995 以内。 */
const CONFIDENCE_CLAMP_MIN = 0.01
const CONFIDENCE_CLAMP_MAX = 0.995

// ---------------------------------------------------------------- 基础换算

/**
 * 编辑距离（Levenshtein）：把 a 改成 b 需要的增/删/替换次数。
 * 用于火山图横轴的"改动字符数"。
 */
export function levenshtein(a, b) {
  const s = String(a ?? '')
  const t = String(b ?? '')
  if (s === t) return 0
  if (!s.length) return t.length
  if (!t.length) return s.length

  let prev = Array.from({ length: t.length + 1 }, (_, j) => j)
  for (let i = 1; i <= s.length; i += 1) {
    const curr = [i]
    for (let j = 1; j <= t.length; j += 1) {
      const cost = s[i - 1] === t[j - 1] ? 0 : 1
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
    }
    prev = curr
  }
  return prev[t.length]
}

/** 一条建议的"改动规模"= 原文片段改到建议片段所需的字符数。 */
export function editImpact(item) {
  return levenshtein(item?.original, item?.suggested)
}

/** 置信显著性 y = -log10(1 - clamp(confidence))，单调递增（docs/VISUAL.md §3）。 */
export function confidenceSignificance(confidence) {
  const value = Number(confidence)
  const safe = Number.isFinite(value) ? value : 0
  const clamped = Math.min(CONFIDENCE_CLAMP_MAX, Math.max(CONFIDENCE_CLAMP_MIN, safe))
  return -Math.log10(1 - clamped)
}

/** 阈值对应的显著性，供火山图横线取值（不在视图里写死数字）。 */
export function confidenceThresholdSignificance(threshold = DEFAULT_CONFIDENCE_THRESHOLD) {
  return confidenceSignificance(threshold)
}

// ---------------------------------------------------------------- 图表数据

/** 类型分布：固定五类、固定顺序，计数为 0 也保留（保证环形图图例稳定）。 */
export function typeDistribution(items = []) {
  const counts = Object.fromEntries(TYPE_ORDER.map((type) => [type, 0]))
  for (const item of items) {
    if (item && Object.hasOwn(counts, item.type)) counts[item.type] += 1
  }
  return TYPE_ORDER.map((type) => ({
    type,
    label: type,
    value: counts[type],
    color: TYPE_COLORS[type],
  }))
}

/**
 * 置信度直方图：从 binStart 起按 binSize 分箱（默认 0.50–1.00，步长 0.05，共 10 箱）。
 * 低于 binStart 的并入第一箱，超出末端的并入最后一箱（不丢样本，也不虚增箱数）。
 */
export function confidenceHistogram(
  items = [],
  { binStart = 0.5, binSize = 0.05, binCount = 10, threshold = DEFAULT_CONFIDENCE_THRESHOLD } = {},
) {
  const bins = Array.from({ length: binCount }, (_, index) => {
    const start = binStart + index * binSize
    const end = start + binSize
    return {
      start,
      end,
      label: `${start.toFixed(2)}–${end.toFixed(2)}`,
      count: 0,
    }
  })
  for (const item of items) {
    const raw = Number(item?.confidence)
    if (!Number.isFinite(raw)) continue
    const index = Math.floor((raw - binStart) / binSize)
    const clamped = Math.min(binCount - 1, Math.max(0, index))
    bins[clamped].count += 1
  }
  return { bins, threshold }
}

/** 状态堆叠：每个类型一根柱，段为三态计数（读"哪类最容易采纳/争议最大"）。 */
export function statusStacked(items = []) {
  const series = STATUS_ORDER.map((status) => ({
    key: status,
    name: STATUS_LABELS[status],
    color: STATUS_COLORS[status],
    data: TYPE_ORDER.map(
      (type) => items.filter((item) => item.type === type && item.status === status).length,
    ),
  }))
  return { categories: [...TYPE_ORDER], series }
}

/** 位置分布：x=字符位置，y=类型泳道（同位置多点时由渲染层错开）。 */
export function positionStrip(items = [], textLength = 0) {
  const laneOf = new Map(TYPE_ORDER.map((type, index) => [type, index]))
  const points = items
    .filter((item) => Number.isFinite(item?.offset) && laneOf.has(item.type))
    .map((item) => ({
      value: [item.offset, laneOf.get(item.type)],
      name: `${item.type}：${item.original} → ${item.suggested}`,
      type: item.type,
      status: item.status,
      original: item.original,
      suggested: item.suggested,
      offset: item.offset,
    }))
  const maxOffset = items.reduce(
    (max, item) => (Number.isFinite(item?.offset) ? Math.max(max, item.offset) : max),
    0,
  )
  return {
    lanes: [...TYPE_ORDER],
    points,
    // 末位留一点余量，避免最后一个点贴在右边界上
    xMax: Math.max(textLength || 0, maxOffset, 1),
  }
}

/**
 * 火山图（校勘显著性图，docs/VISUAL.md §3）。
 * x = 改动字符数；y = 置信显著性；四象限对应四种处理动作。
 */
export function volcanoPoints(items = [], threshold = DEFAULT_CONFIDENCE_THRESHOLD) {
  const points = items.map((item) => {
    const impact = editImpact(item)
    const significance = confidenceSignificance(item.confidence)
    return {
      value: [impact, Number(significance.toFixed(4))],
      impact,
      significance,
      confidence: Number(item.confidence),
      name: `${item.type}：${item.original} → ${item.suggested}`,
      type: item.type,
      status: item.status,
      original: item.original,
      suggested: item.suggested,
      reason: item.reason,
    }
  })
  const maxImpact = points.reduce((max, point) => Math.max(max, point.impact), 0)
  return {
    points,
    // x 轴至少留到 2，否则全是单字改动时看不出"单字/多字"分界
    xMax: Math.max(2, maxImpact + 0.5),
    thresholds: {
      x: VOLCANO_X_THRESHOLD,
      y: Number(confidenceThresholdSignificance(threshold).toFixed(4)),
      confidence: threshold,
    },
  }
}

/** 统计卡数据：看板顶部与工作台筛选栏共用。 */
export function overallStats(items = [], threshold = DEFAULT_CONFIDENCE_THRESHOLD) {
  const total = items.length
  const count = (status) => items.filter((item) => item.status === status).length
  const high = items.filter((item) => Number(item.confidence) >= threshold).length
  const confidenceSum = items.reduce((sum, item) => {
    const value = Number(item.confidence)
    return sum + (Number.isFinite(value) ? value : 0)
  }, 0)
  const typeCounts = Object.fromEntries(TYPE_ORDER.map((type) => [type, 0]))
  for (const item of items) {
    if (item && Object.hasOwn(typeCounts, item.type)) typeCounts[item.type] += 1
  }
  return {
    total,
    pending: count('pending'),
    accepted: count('accepted'),
    rejected: count('rejected'),
    highConfidence: high,
    lowConfidence: total - high,
    highConfidenceRate: total ? Math.round((high / total) * 100) : 0,
    meanConfidence: total ? Number((confidenceSum / total).toFixed(3)) : 0,
    typeCounts,
  }
}

/** 七维雷达：轴固定顺序，`missing` 记 0 并单独标出（0 表示"未能判断"，不是"判断为否"）。 */
export function dimensionRadar(dimensions = []) {
  const list = Array.isArray(dimensions) ? dimensions : []
  const indicators = list.map((dimension) => ({ name: dimension.label || dimension.key, max: 1 }))
  const values = list.map((dimension) =>
    dimension.missing ? 0 : Math.max(0, Math.min(1, Number(dimension.confidence) || 0)),
  )
  const isMissing = (dimension) => Boolean(dimension.missing)
  return {
    indicators,
    values,
    missingLabels: list.filter(isMissing).map((d) => d.label || d.key),
    // 未判断的维度不算"存疑"：它的 uncertain 只是占位语义（后端补 missing 时一并置 true）。
    // 不排掉的话，同一根轴会同时出现在"未判断"和"存疑"两句里，读起来像两个问题。
    uncertainLabels: list
      .filter((dimension) => dimension.uncertain && !isMissing(dimension))
      .map((d) => d.label || d.key),
  }
}

/**
 * 知识图谱：实体 → 节点、关系 → 边。
 * 端点必须能在实体中找到，找不到的边丢弃（后端已校验过，这里再兜一层防止脏数据进图）。
 * 节点大小按连接度给出，让"枢纽实体"一眼可见。
 */
export function knowledgeGraph(entities = [], relations = []) {
  const list = Array.isArray(entities) ? entities : []
  const names = new Set(list.map((entity) => entity?.name).filter(Boolean))
  const edges = (Array.isArray(relations) ? relations : []).filter(
    (relation) =>
      relation && names.has(relation.source) && names.has(relation.target) && relation.source !== relation.target,
  )

  const degree = new Map()
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
  }

  const nodes = list
    .filter((entity) => entity?.name)
    .map((entity) => {
      const kind = KIND_ORDER.includes(entity.kind) ? entity.kind : '人物'
      return {
        name: entity.name,
        note: entity.note || '',
        kind,
        category: KIND_ORDER.indexOf(kind),
        symbolSize: 24 + Math.min(degree.get(entity.name) || 0, 6) * 5,
        itemStyle: { color: KIND_COLORS[kind] },
      }
    })

  return {
    nodes,
    links: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      label: edge.relation || '',
      relation: edge.relation || '',
    })),
    categories: KIND_ORDER.map((kind) => ({ name: kind, itemStyle: { color: KIND_COLORS[kind] } })),
  }
}

/** 知识点汇总：把各维度的 knowledgePoints 去重后摊平，供看板"知识点"区块展示。 */
export function collectKnowledgePoints(dimensions = []) {
  const list = Array.isArray(dimensions) ? dimensions : []
  const seen = new Set()
  const result = []
  for (const dimension of list) {
    const points = Array.isArray(dimension?.knowledgePoints) ? dimension.knowledgePoints : []
    for (const point of points) {
      const text = String(point ?? '').trim()
      if (!text || seen.has(text)) continue
      seen.add(text)
      result.push({ text, dimension: dimension.label || dimension.key })
    }
  }
  return result
}
