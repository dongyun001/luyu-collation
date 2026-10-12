<template>
  <div class="filter-bar">
    <!-- 类型 -->
    <div class="filter-row">
      <span class="filter-label">类型</span>
      <button
        v-for="type in ALL_CHECK_TYPES"
        :key="type"
        class="chip"
        :class="{ active: store.filters.types.includes(type) }"
        :style="typeChipStyle(type)"
        :aria-pressed="store.filters.types.includes(type)"
        @click="store.toggleTypeFilter(type)"
      >
        {{ type }}
      </button>
    </div>

    <!-- 状态 + 置信度 -->
    <div class="filter-row">
      <span class="filter-label">状态</span>
      <button
        v-for="status in ALL_DECISION_STATUSES"
        :key="status"
        class="chip"
        :class="{ active: store.filters.statuses.includes(status) }"
        :aria-pressed="store.filters.statuses.includes(status)"
        @click="store.toggleStatusFilter(status)"
      >
        {{ STATUS_LABELS[status] }}
      </button>

      <span class="filter-label gap">置信度</span>
      <input
        class="range"
        type="range"
        min="0"
        max="1"
        step="0.05"
        :value="store.filters.confidenceMin"
        aria-label="置信度下限"
        @input="onConfidenceMin"
      />
      <span class="range-readout guji-num">≥ {{ Number(store.filters.confidenceMin).toFixed(2) }}</span>
      <input
        class="range"
        type="range"
        min="0"
        max="1"
        step="0.05"
        :value="store.filters.confidenceMax"
        aria-label="置信度上限"
        @input="onConfidenceMax"
      />
      <span class="range-readout guji-num">≤ {{ Number(store.filters.confidenceMax).toFixed(2) }}</span>
    </div>

    <!-- 关键词 + 预设 + 计数 -->
    <div class="filter-row">
      <span class="filter-label">关键词</span>
      <input
        class="keyword"
        type="search"
        placeholder="原文 / 建议 / 理由"
        :value="store.filters.keyword"
        @input="onKeyword"
      />
      <button class="preset" @click="store.applyFilterPreset('high-pending')">高置信待处理</button>
      <button class="preset" @click="store.applyFilterPreset('notes-only')">只看通假/异文</button>
      <button class="preset" :disabled="!store.hasActiveFilters" @click="store.resetFilters()">
        清空筛选
      </button>

      <span class="match guji-num" :class="{ emphasis: store.hasActiveFilters }">
        命中 {{ store.filterStats.matched }} / {{ store.filterStats.total }} 条
      </span>

      <button
        class="accept"
        :disabled="!acceptCount"
        :title="acceptCount ? '采纳筛选结果中的高置信条目' : '筛选结果中没有可采纳的高置信条目'"
        @click="store.acceptFiltered()"
      >
        采纳筛选中（{{ acceptCount }}）
      </button>
    </div>
  </div>
</template>

<script setup>
/**
 * 条目筛选栏（F12，纯前端）。
 *
 * 直接读写 collation store 的 `filters`——筛选对象就是 `items`，
 * 放同一 store 才能保证工作台与看板看到的是**同一套筛选**（TECH_DESIGN §3）。
 *
 * 语义提醒：类型/状态都是白名单，默认全选；全不选 = 零结果（如实反馈）。
 */
import { computed } from 'vue'

import { ALL_CHECK_TYPES, ALL_DECISION_STATUSES, LOW_CONFIDENCE_THRESHOLD, useCollationStore } from '@/stores/collation'
import { STATUS_LABELS, TYPE_COLORS } from '@/utils/chartData'

const store = useCollationStore()

/** 筛选结果里"还能被采纳"的高置信条目数（低置信不参与，与 acceptAll 同规则）。 */
const acceptCount = computed(
  () =>
    store.filteredItems.filter(
      (item) => item.confidence >= LOW_CONFIDENCE_THRESHOLD && item.status !== 'accepted',
    ).length,
)

function typeChipStyle(type) {
  const active = store.filters.types.includes(type)
  const color = TYPE_COLORS[type] || '#777'
  return active
    ? { borderColor: color, color, background: 'var(--paper)' }
    : { borderColor: 'var(--line)', color: 'var(--ink-faint)' }
}

function onConfidenceMin(event) {
  const value = Number(event.target.value)
  store.setFilters({ confidenceMin: Math.min(value, Number(store.filters.confidenceMax)) })
}

function onConfidenceMax(event) {
  const value = Number(event.target.value)
  store.setFilters({ confidenceMax: Math.max(value, Number(store.filters.confidenceMin)) })
}

function onKeyword(event) {
  store.setFilters({ keyword: event.target.value })
}
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

.filter-label {
  color: var(--ink-muted);
  flex-shrink: 0;
}

.filter-label.gap {
  margin-left: var(--space-4);
}

.chip {
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 11px;
  padding: 1px 10px;
  font-size: 12px;
  color: var(--ink-faint);
  cursor: pointer;
  line-height: 1.8;
  transition: all 0.15s;
}

.chip.active {
  font-weight: bold;
}

.chip:hover {
  background: var(--cinnabar-wash);
}

.range {
  width: 90px;
  accent-color: var(--cinnabar);
}

.range-readout {
  color: var(--ink-muted);
  min-width: 44px;
}

.keyword {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  font-size: 12px;
  width: 170px;
  background: #fff;
  outline: none;
}

.keyword:focus {
  border-color: var(--cinnabar);
}

.preset {
  border: 1px dashed var(--line);
  background: transparent;
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  font-size: 12px;
  color: var(--ink-soft);
  cursor: pointer;
}

.preset:hover:not(:disabled) {
  border-color: var(--cinnabar);
  color: var(--cinnabar);
}

.preset:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.match {
  margin-left: auto;
  color: var(--ink-muted);
}

.match.emphasis {
  color: var(--cinnabar);
  font-weight: bold;
}

.accept {
  border: 1px solid var(--success);
  background: #fff;
  color: var(--success);
  border-radius: var(--radius-sm);
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
}

.accept:hover:not(:disabled) {
  background: var(--success);
  color: #fff;
}

.accept:disabled {
  border-color: var(--line);
  color: var(--ink-faint);
  cursor: not-allowed;
}
</style>
