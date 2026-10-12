<template>
  <ul class="type-legend">
    <li v-for="entry in list" :key="entry.type" class="legend-item">
      <span class="legend-dot" :style="{ background: entry.color }" aria-hidden="true"></span>
      <span class="legend-label">{{ entry.type }}</span>
      <span v-if="entry.count !== undefined" class="legend-count guji-num">{{ entry.count }}</span>
    </li>
  </ul>
</template>

<script setup>
/**
 * 统一图例：五类校勘类型 + 计数。
 *
 * 存在的意义是"图例只写一次"——类型色与顺序来自 utils/chartData.js，
 * 图表里画的和这里显示的必然一致（改色只改 chartData + theme.css 两处）。
 */
import { computed } from 'vue'

import { TYPE_COLORS, TYPE_ORDER } from '@/utils/chartData'

const props = defineProps({
  /** 类型 → 计数；不传则不显示数字。 */
  counts: { type: Object, default: () => ({}) },
  /** 只想显示部分类型时传；默认全部五类、固定顺序。 */
  types: { type: Array, default: null },
  showCount: { type: Boolean, default: true },
})

const list = computed(() =>
  (props.types || TYPE_ORDER).map((type) => ({
    type,
    color: TYPE_COLORS[type] || '#999',
    count: props.showCount ? (props.counts[type] ?? 0) : undefined,
  })),
)
</script>

<style scoped>
.type-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--ink-soft);
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-count {
  color: var(--ink-muted);
  font-size: 12px;
}
</style>
