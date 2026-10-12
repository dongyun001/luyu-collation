<template>
  <div class="analysis-view">
    <!-- 顶部：标题与操作 -->
    <header class="view-head">
      <div class="head-main">
        <h1 class="view-title">分析看板</h1>
        <p class="view-sub">
          基于本次校勘结果的统计图表、多维度文献判断与知识图谱；所有数据来自真实调用结果。
        </p>
      </div>
      <div class="head-actions">
        <button class="guji-btn" :disabled="!canAnalyze || analysis.isLoading" @click="startAnalyze">
          {{ analysis.isLoading ? '正在分析…' : analysis.hasResult ? '重新分析' : '生成多维度分析' }}
        </button>
        <button
          v-if="analysis.hasResult || analysis.status === 'error'"
          class="guji-btn guji-btn--ghost"
          :disabled="analysis.isLoading"
          @click="clearAnalysis"
        >
          清除分析
        </button>
      </div>
    </header>

    <!-- 无校勘结果：整页空态，引导回主链路 -->
    <SectionCard v-if="!store.items.length && !store.sourceText" title="还没有可分析的内容">
      <div class="guji-empty">
        <span class="guji-empty__icon">📄</span>
        请在首页粘贴古籍原文并完成一次校勘，本页会据此生成统计图表与多维分析。
      </div>
      <div class="empty-action">
        <button class="guji-btn" @click="goHome">去首页粘贴原文</button>
      </div>
    </SectionCard>

    <template v-else>
      <!-- 文献画像 -->
      <SectionCard title="本次校勘概况">
        <div class="profile">
          <div class="profile-item">
            <span class="profile-label">原文</span>
            <span class="profile-value guji-num">{{ store.sourceText.length }} 字</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">分段</span>
            <span class="profile-value guji-num">{{ store.meta.chunkCount || 1 }} 段</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">校勘点</span>
            <span class="profile-value guji-num">{{ store.items.length }} 条</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">模型</span>
            <span class="profile-value">{{ store.meta.model || '未知' }}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">参校本</span>
            <span class="profile-value">{{ store.meta.referenceEdition }}</span>
          </div>
          <div v-if="store.meta.droppedCount" class="profile-item is-warn">
            <span class="profile-label">契约拦截</span>
            <span class="profile-value guji-num">{{ store.meta.droppedCount }} 条</span>
          </div>
        </div>
      </SectionCard>

      <!-- 统计卡：始终按**全部**条目计算（图与统计要能反映整篇面貌），
           筛选只作用于最下面的条目表，所以这里不传 filtered，避免标签与数值错位 -->
      <SectionCard title="校勘统计" :sub="`口径：全部 ${store.items.length} 条；下表筛选中 ${store.filterStats.matched} 条`">
        <StatsCards :stats="stats" />
      </SectionCard>

      <!-- 多维度文献分析（F9） -->
      <SectionCard title="多维度文献分析">
        <template #actions>
          <span v-if="analysis.meta.sampled" class="head-tag">基于节选</span>
          <span v-if="analysis.meta.elapsedMs" class="head-tag guji-num">
            {{ (analysis.meta.elapsedMs / 1000).toFixed(1) }}s
          </span>
        </template>

        <!-- 分析完成时落一枚章（一次性动效） -->
        <SealStamp v-if="analysis.isReady" text="析" :size="30" placement="header" />

        <p class="guji-disclaimer">
          AI 辅助判断，仅供参考，请以专业工具书为准。核验口径见 <code>docs/EVAL.md</code> §10；
          维度判断不计入检出/分类指标。
        </p>

        <!-- 未生成 -->
        <div v-if="!analysis.hasResult && !analysis.isLoading" class="guji-empty">
          <span class="guji-empty__icon">🧭</span>
          <template v-if="analysis.status === 'error'">
            分析未完成：{{ analysis.error.message }}
            <br />
            <span class="error-hint">{{ analysis.error.hint }}</span>
          </template>
          <template v-else>
            尚未生成多维度分析。点击右上角「生成多维度分析」，
            系统会从 体裁 / 年代 / 作者 / 学派 / 版本 / 语言 / 校勘 七个维度给出判断与依据。
          </template>
        </div>

        <div v-else-if="analysis.isLoading" class="analysis-loading">
          <p class="analysis-loading__title">
            <span class="spinner">⏳</span> 正在调用模型做多维度判断…
          </p>
          <!-- 单次调用拿不到真实进度，条宽按已用时间预估；秒数与"七个维度逐一判断"是如实的 -->
          <ProgressMeter
            aria-label="多维度分析进度"
            :percent="analysis.progressPercent"
            :seconds="analysis.elapsedSeconds"
            label="七个维度逐一判断中"
            hint="内容较长或上游繁忙时会久一些；与校勘相互独立，失败不影响上方结果。"
          />
        </div>

        <template v-else>
          <p v-if="staleAnalysis" class="stale-hint">
            ⚠️ 原文在本页生成分析之后发生了变化，下方判断对应的是<strong>之前那一篇</strong>，请点击「重新分析」。
          </p>
          <p v-if="analysis.meta.droppedCount" class="drop-hint">
            有 {{ analysis.meta.droppedCount }} 条模型输出未通过契约校验（不合 schema / 悬空关系），已拦截未渲染。
          </p>

          <div class="analysis-grid">
            <div class="radar-col">
              <DimensionRadar :dimensions="analysis.dimensions" />
            </div>
            <div class="cards-col">
              <DimensionCard
                v-for="dimension in analysis.dimensions"
                :key="dimension.key"
                :dimension="dimension"
              />
            </div>
          </div>

          <div v-if="analysis.knowledgePoints.length" class="knowledge-block">
            <div class="block-label">相关知识点</div>
            <ul class="knowledge-list">
              <li v-for="point in analysis.knowledgePoints" :key="point.text">
                <span class="knowledge-text">{{ point.text }}</span>
                <span class="knowledge-source">{{ point.dimension }}</span>
              </li>
            </ul>
          </div>
        </template>
      </SectionCard>

      <!-- 知识图谱（F11） -->
      <SectionCard title="知识图谱" sub="人物 / 著作 / 学派 / 地名 / 职官 / 年代之间的关系网络">
        <KnowledgeGraph :entities="analysis.entities" :relations="analysis.relations" />
      </SectionCard>

      <!-- 图表（F10） -->
      <SectionCard title="可视化图表" sub="坐标与阈值定义见 docs/VISUAL.md；图例固定五色">
        <TypeLegend class="legend-line" :counts="stats.typeCounts" />
        <div class="chart-grid">
          <div class="chart-cell">
            <h4 class="chart-title">类型分布</h4>
            <TypeDistributionChart :items="store.items" />
          </div>
          <div class="chart-cell">
            <h4 class="chart-title">置信度分布</h4>
            <ConfidenceHistogram :items="store.items" />
          </div>
          <div class="chart-cell">
            <h4 class="chart-title">位置分布</h4>
            <PositionStrip :items="store.items" :text-length="store.sourceText.length" />
          </div>
          <div class="chart-cell">
            <h4 class="chart-title">类型 × 决策状态</h4>
            <StatusStackedBar :items="store.items" />
          </div>
          <div class="chart-cell is-wide">
            <h4 class="chart-title">校勘火山图</h4>
            <VolcanoChart :items="store.items" />
          </div>
        </div>
      </SectionCard>

      <!-- 条目筛选（F12） -->
      <SectionCard
        title="校勘条目"
        :sub="`筛选只作用于下表（图表与统计卡按全部 ${store.items.length} 条计算）；采纳与还原请到「校勘工作台」进行`"
      >
        <FilterBar class="filter-line" />
        <div class="table-wrap">
          <table class="item-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>原文 → 建议</th>
                <th>理由</th>
                <th class="num">置信度</th>
                <th>状态</th>
                <th class="num">位置</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in store.filteredItems" :key="item.id">
                <td>
                  <span class="type-cell" :style="{ color: TYPE_COLORS[item.type] }">{{ item.type }}</span>
                </td>
                <td class="pair">{{ item.original }} <span class="arrow">→</span> {{ item.suggested }}</td>
                <td class="reason">{{ item.reason }}</td>
                <td class="num guji-num">{{ Math.round(item.confidence * 100) }}%</td>
                <td>{{ STATUS_LABELS[item.status] || item.status }}</td>
                <td class="num guji-num">{{ item.offset + 1 }}</td>
              </tr>
              <tr v-if="!store.filteredItems.length">
                <td colspan="6" class="empty-row">当前筛选条件下没有匹配的条目。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>
    </template>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

import DimensionCard from '@/components/DimensionCard.vue'
import FilterBar from '@/components/FilterBar.vue'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'
import ProgressMeter from '@/components/ProgressMeter.vue'
import SealStamp from '@/components/SealStamp.vue'
import SectionCard from '@/components/SectionCard.vue'
import StatsCards from '@/components/StatsCards.vue'
import TypeLegend from '@/components/TypeLegend.vue'
import ConfidenceHistogram from '@/components/charts/ConfidenceHistogram.vue'
import DimensionRadar from '@/components/charts/DimensionRadar.vue'
import PositionStrip from '@/components/charts/PositionStrip.vue'
import StatusStackedBar from '@/components/charts/StatusStackedBar.vue'
import TypeDistributionChart from '@/components/charts/TypeDistributionChart.vue'
import VolcanoChart from '@/components/charts/VolcanoChart.vue'
import { LOW_CONFIDENCE_THRESHOLD, useCollationStore } from '@/stores/collation'
import { useAnalysisStore } from '@/stores/analysis'
import { STATUS_LABELS, TYPE_COLORS, overallStats } from '@/utils/chartData'

const router = useRouter()
const store = useCollationStore()
const analysis = useAnalysisStore()

const stats = computed(() => overallStats(store.items, LOW_CONFIDENCE_THRESHOLD))
const canAnalyze = computed(() => Boolean(store.sourceText.trim()))

/** 分析结果是否对应"当前这篇原文"：换过文本就要提示重新分析，免得张冠李戴。 */
const staleAnalysis = computed(
  () => analysis.hasResult && analysis.analyzedText !== store.sourceText,
)

function startAnalyze() {
  analysis.analyze(store.sourceText)
}

function clearAnalysis() {
  analysis.reset()
}

function goHome() {
  router.push('/')
}

// 主链路被重置（重新开始 / 清空原文）时，分析结果一并撤掉——
// 否则看板上会留着上一篇文章的判断。
watch(
  () => store.sourceText,
  (value) => {
    if (!value) analysis.reset()
  },
)
</script>

<style scoped>
.view-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}

.view-title {
  margin: 0 0 6px;
  font-size: 24px;
  color: var(--ink);
  letter-spacing: 2px;
}

.view-sub {
  margin: 0;
  font-size: 13px;
  color: var(--ink-muted);
  line-height: 1.7;
}

.head-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.head-tag {
  font-size: 11px;
  color: var(--ink-muted);
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1px 8px;
}

.empty-action {
  text-align: center;
  margin-top: var(--space-2);
}

/* 文献画像 */
.profile {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-6);
}

.profile-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.profile-label {
  font-size: 11px;
  color: var(--ink-faint);
}

.profile-value {
  font-size: 15px;
  color: var(--ink);
}

.profile-item.is-warn .profile-value {
  color: #b06a2c;
}

/* 多维度区 */
.drop-hint,
.stale-hint {
  font-size: 12px;
  line-height: 1.8;
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin: 0 0 var(--space-3);
}

.drop-hint {
  color: #8a6d3b;
  background: #fffbf0;
  border-left: 3px solid var(--warn);
}

.stale-hint {
  color: #8a2b22;
  background: #fdf3f2;
  border-left: 3px solid var(--danger);
}

.error-hint {
  color: var(--ink-muted);
  font-size: 12px;
}

.spinner {
  animation: pulse 1.6s ease-in-out infinite;
}

/* 分析加载态：与校勘加载屏同一套观感（进度条样式在 styles/theme.css） */
.analysis-loading {
  padding: var(--space-4) 0 var(--space-2);
  text-align: center;
}

.analysis-loading__title {
  margin: 0;
  font-size: 14px;
  color: var(--ink-soft);
}

.analysis-loading .progress-track {
  margin-left: auto;
  margin-right: auto;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.analysis-grid {
  display: grid;
  grid-template-columns: minmax(280px, 380px) 1fr;
  gap: var(--space-5);
  align-items: start;
  margin-top: var(--space-4);
}

@media (max-width: 1000px) {
  .analysis-grid {
    grid-template-columns: 1fr;
  }
}

.cards-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--space-3);
}

.knowledge-block {
  margin-top: var(--space-5);
}

.block-label {
  font-size: 12px;
  color: var(--ink-faint);
  margin-bottom: 6px;
}

.knowledge-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 6px var(--space-4);
}

.knowledge-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-soft);
  line-height: 1.7;
  border-bottom: 1px dashed var(--line-soft);
  padding-bottom: 4px;
}

.knowledge-source {
  font-size: 11px;
  color: var(--ink-faint);
  flex-shrink: 0;
}

/* 图表区 */
.legend-line {
  margin-bottom: var(--space-4);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--space-4);
}

.chart-cell {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  padding: var(--space-3);
  background: var(--surface);
}

.chart-cell.is-wide {
  grid-column: 1 / -1;
}

.chart-title {
  margin: 0 0 var(--space-2);
  font-size: 13px;
  color: var(--ink-soft);
  font-weight: normal;
}

/* 条目表 */
.filter-line {
  margin-bottom: var(--space-3);
}

.table-wrap {
  overflow-x: auto;
}

.item-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.item-table th {
  text-align: left;
  font-weight: normal;
  color: var(--ink-faint);
  border-bottom: 1px solid var(--line);
  padding: 6px 8px;
  white-space: nowrap;
}

.item-table td {
  border-bottom: 1px solid var(--line-soft);
  padding: 6px 8px;
  color: var(--ink-soft);
  vertical-align: top;
}

.item-table .num {
  text-align: right;
  white-space: nowrap;
}

.type-cell {
  font-weight: bold;
  white-space: nowrap;
}

.pair {
  font-family: var(--font-kai);
  font-size: 15px;
  white-space: nowrap;
}

.pair .arrow {
  color: var(--ink-faint);
}

.reason {
  min-width: 200px;
  line-height: 1.7;
}

.empty-row {
  text-align: center;
  color: var(--ink-faint);
  padding: var(--space-5) 0;
}
</style>
