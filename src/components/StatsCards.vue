<template>
  <!-- 紧凑模式：工作台顶部一行放得下，不挤压双栏正文 -->
  <div v-if="compact" class="stats-inline">
    <span v-for="card in compactCards" :key="card.key" class="stats-inline__item">
      <span class="stats-inline__label">{{ card.label }}</span>
      <strong class="guji-num" :class="`is-${card.tone}`">{{ card.value }}</strong>
    </span>
  </div>

  <div v-else class="stats-cards">
    <div v-for="card in cards" :key="card.key" class="stat-card" :class="`is-${card.tone}`">
      <div class="stat-value guji-num">{{ card.value }}</div>
      <div class="stat-label">{{ card.label }}</div>
      <div v-if="card.hint" class="stat-hint">{{ card.hint }}</div>
    </div>

    <div class="stat-card is-wide">
      <div class="stat-label">类型分布</div>
      <div class="type-bars">
        <div v-for="row in typeRows" :key="row.type" class="type-bar">
          <span class="type-bar__name" :style="{ color: row.color }">{{ row.type }}</span>
          <span class="type-bar__track">
            <span
              class="type-bar__fill"
              :style="{ width: row.percent + '%', background: row.color }"
            ></span>
          </span>
          <span class="type-bar__count guji-num">{{ row.count }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 统计卡：把"这一篇校勘了什么"一眼说完。
 *
 * 数据由 `utils/chartData.js` 的 `overallStats()` 算出后传入（纯展示组件），
 * 这样同一个组件既能显示"全部结果"也能显示"筛选结果"。
 */
import { computed } from 'vue'

import { TYPE_COLORS, TYPE_ORDER } from '@/utils/chartData'

const props = defineProps({
  /** overallStats() 的返回值 */
  stats: { type: Object, required: true },
  /** 是否处于筛选态（决定文案是"全部"还是"筛选中"） */
  filtered: { type: Boolean, default: false },
  /** 紧凑模式：工作台顶部只占一行 */
  compact: { type: Boolean, default: false },
})

const cards = computed(() => {
  const s = props.stats
  const scope = props.filtered ? '筛选中' : '全部'
  return [
    { key: 'total', label: `${scope}校勘点`, value: s.total, tone: 'default' },
    { key: 'pending', label: '待处理', value: s.pending, tone: 'pending' },
    { key: 'accepted', label: '已采纳', value: s.accepted, tone: 'accepted' },
    { key: 'rejected', label: '已还原', value: s.rejected, tone: 'default' },
    {
      key: 'high',
      label: '高置信',
      value: s.highConfidence,
      tone: 'high',
      hint: `占比 ${s.highConfidenceRate}% · 均值 ${s.meanConfidence}`,
    },
  ]
})

/** 紧凑模式只留最常看的四项，避免把工作台顶栏撑高 */
const compactCards = computed(() =>
  cards.value.filter((card) => ['total', 'pending', 'accepted', 'high'].includes(card.key)),
)

const typeRows = computed(() => {
  const counts = props.stats.typeCounts || {}
  const max = Math.max(1, ...TYPE_ORDER.map((type) => counts[type] || 0))
  return TYPE_ORDER.map((type) => ({
    type,
    color: TYPE_COLORS[type],
    count: counts[type] || 0,
    percent: Math.round(((counts[type] || 0) / max) * 100),
  }))
})
</script>

<style scoped>
/* --- 紧凑模式 --- */
.stats-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 12px;
  color: var(--ink-muted);
}

.stats-inline__item {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}

.stats-inline__label {
  color: var(--ink-faint);
}

.stats-inline .is-pending {
  color: var(--cinnabar);
}
.stats-inline .is-accepted {
  color: var(--success);
}
.stats-inline .is-high {
  color: #b7791f;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-3);
  align-items: stretch;
}

.stat-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 14px;
  min-width: 0;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--ink);
  line-height: 1.3;
}

.stat-label {
  font-size: 12px;
  color: var(--ink-muted);
  margin-top: 2px;
}

.stat-hint {
  font-size: 11px;
  color: var(--ink-faint);
  margin-top: 4px;
}

.stat-card.is-pending .stat-value {
  color: var(--cinnabar);
}
.stat-card.is-accepted .stat-value {
  color: var(--success);
}
.stat-card.is-high .stat-value {
  color: #b7791f;
}

.stat-card.is-wide {
  grid-column: 1 / -1;
}

.type-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.type-bar {
  display: grid;
  grid-template-columns: 44px 1fr 32px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.type-bar__name {
  font-weight: bold;
}

.type-bar__track {
  height: 8px;
  border-radius: 4px;
  background: #efece5;
  overflow: hidden;
}

.type-bar__fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.type-bar__count {
  text-align: right;
  color: var(--ink-muted);
}
</style>
