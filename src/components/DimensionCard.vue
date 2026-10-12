<template>
  <article class="dimension-card" :class="{ 'is-missing': dimension.missing, 'is-uncertain': dimension.uncertain }">
    <header class="card-head">
      <h4 class="card-title">{{ dimension.label }}</h4>
      <div class="card-tags">
        <span v-if="dimension.missing" class="tag tag-missing">未判断</span>
        <span v-else-if="dimension.uncertain" class="tag tag-uncertain">存疑</span>
        <span v-if="!dimension.missing" class="tag tag-confidence guji-num">
          置信 {{ Math.round(dimension.confidence * 100) }}%
        </span>
      </div>
    </header>

    <p class="judgment">{{ dimension.judgment }}</p>

    <div v-if="dimension.evidence.length" class="evidence">
      <div class="block-label">依据</div>
      <ul>
        <li v-for="(item, index) in dimension.evidence" :key="index">{{ item }}</li>
      </ul>
    </div>

    <div v-if="!dimension.missing" class="confidence-track" role="img" :aria-label="`置信度 ${Math.round(dimension.confidence * 100)}%`">
      <div class="confidence-fill" :style="{ width: `${Math.round(dimension.confidence * 100)}%` }"></div>
    </div>

    <div v-if="dimension.knowledgePoints.length" class="knowledge">
      <div class="block-label">知识点</div>
      <div class="chips">
        <span v-for="(point, index) in dimension.knowledgePoints" :key="index" class="guji-chip">
          {{ point }}
        </span>
      </div>
    </div>
  </article>
</template>

<script setup>
/**
 * 维度卡片（docs/VISUAL.md §4.2）：**事实载体**，雷达图只是它的索引。
 *
 * 因此这里必须把 `judgment` 与 `evidence` 都如实铺开——依据是这一屏可信度的来源，
 * 不允许留空当"判断"展示（后端的归一化已保证：无依据必标存疑）。
 */
defineProps({
  /** API.md §6 的 dimensions[] 单项 */
  dimension: { type: Object, required: true },
})
</script>

<style scoped>
.dimension-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.dimension-card.is-missing {
  background: #fbfbf9;
  border-style: dashed;
}

.dimension-card.is-uncertain {
  border-left: 3px solid var(--warn);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.card-title {
  margin: 0;
  font-size: 14px;
  color: var(--ink);
  letter-spacing: 0.5px;
}

.card-tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.tag {
  font-size: 11px;
  border-radius: 9px;
  padding: 1px 8px;
  line-height: 1.7;
}

.tag-confidence {
  color: var(--cinnabar);
  background: var(--cinnabar-wash);
}

.tag-uncertain {
  color: #8a6d3b;
  background: #fffbf0;
  border: 1px solid #f0e6cf;
}

.tag-missing {
  color: var(--ink-faint);
  background: #f2f2f0;
}

.judgment {
  margin: 0;
  font-size: 13px;
  color: var(--ink-soft);
  line-height: 1.8;
  font-family: var(--font-kai);
}

.block-label {
  font-size: 11px;
  color: var(--ink-faint);
  margin-bottom: 4px;
}

.evidence ul {
  margin: 0;
  padding-left: 18px;
}

.evidence li {
  font-size: 12px;
  color: var(--ink-muted);
  line-height: 1.75;
}

.confidence-track {
  height: 4px;
  border-radius: 2px;
  background: #efece5;
  overflow: hidden;
}

.confidence-fill {
  height: 100%;
  background: var(--cinnabar);
  border-radius: 2px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
</style>
