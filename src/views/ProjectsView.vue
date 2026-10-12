<template>
  <div class="projects-view">
    <header class="view-head">
      <div>
        <h1 class="view-title">项目列表</h1>
        <p class="view-sub">
          保存过的校勘结果都<strong>存在这台机器的浏览器里</strong>（localStorage），不上传服务器；
          换设备或清空浏览器数据就看不到。后端仍是无状态的。
        </p>
      </div>
      <button
        class="guji-btn"
        :disabled="!canSave"
        :title="canSave ? '把当前校勘结果存进本机项目列表' : '还没有可保存的校勘结果'"
        @click="saveCurrent"
      >
        保存当前校勘
      </button>
    </header>

    <div v-if="notice" class="notice" :class="notice.level">
      {{ notice.message }}
    </div>

    <SectionCard :title="`本机项目（${filtered.length} / ${projects.length}）`">
      <template #actions>
        <span class="head-tag">仅本机可见</span>
      </template>

      <!-- 筛选 -->
      <div class="filters">
        <label class="field">
          <span>关键词</span>
          <input v-model="keyword" type="search" placeholder="标题 / 模型名" />
        </label>
        <label class="field">
          <span>字数 ≥</span>
          <input v-model.number="minChars" type="number" min="0" step="100" />
        </label>
        <label class="field">
          <span>校勘点 ≥</span>
          <input v-model.number="minItems" type="number" min="0" step="1" />
        </label>
        <label class="field">
          <span>排序</span>
          <select v-model="sort">
            <option v-for="option in SORT_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <button class="reset" :disabled="!hasFilters" @click="resetFilters">清空筛选</button>
      </div>

      <!-- 列表 -->
      <ul v-if="filtered.length" class="project-list">
        <li v-for="project in filtered" :key="project.id" class="project-item">
          <div class="item-main">
            <div class="item-title">
              {{ project.title }}
              <span v-if="project.contentStripped" class="tag-stripped" title="项目过大，只存了摘要，正文未入库">
                仅摘要
              </span>
            </div>
            <div class="item-meta guji-num">
              <span>{{ formatTime(project.updatedAt) }}</span>
              <span>{{ project.chars }} 字</span>
              <span>{{ project.itemCount }} 条校勘点</span>
              <span>已采纳 {{ project.acceptedCount }}</span>
              <span>待处理 {{ project.pendingCount }}</span>
              <span v-if="project.model">模型 {{ project.model }}</span>
            </div>
          </div>
          <div class="item-actions">
            <button class="mini" :disabled="project.contentStripped" @click="load(project)">载入</button>
            <button class="mini danger" @click="remove(project)">删除</button>
          </div>
        </li>
      </ul>

      <div v-else class="guji-empty">
        <span class="guji-empty__icon">🗂️</span>
        <template v-if="projects.length">
          没有符合当前筛选条件的项目。
        </template>
        <template v-else>
          还没有保存过项目。完成一次校勘后，点上方的「保存当前校勘」即可存到本机。
        </template>
      </div>
    </SectionCard>

    <SectionCard title="说明" sub="为什么不做服务端历史记录">
      <ul class="notes">
        <li>阶段一定位是<strong>无状态后端</strong>：不落盘用户文本，隐私与合规上更干净（PRD §4）。</li>
        <li>因此"项目列表"是浏览器本地暂存，与工作台的草稿缓存同一性质，不是数据库。</li>
        <li>跨会话、跨设备的版本库与版本对勘属阶段二范围（见 <code>docs/ROADMAP.md</code>）。</li>
      </ul>
    </SectionCard>
  </div>
</template>

<script setup>
/**
 * 本机项目列表（F12）。
 *
 * 数据全部来自 `utils/projects.js`（localStorage，纯函数逻辑带测试），
 * 本视图只管筛选交互与"载入 → 跳工作台"。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import SectionCard from '@/components/SectionCard.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useCollationStore } from '@/stores/collation'
import {
  SORT_OPTIONS,
  filterProjects,
  getProject,
  listProjects,
  projectFromCollation,
  removeProject,
  saveProject,
} from '@/utils/projects'

const router = useRouter()
const store = useCollationStore()
const analysis = useAnalysisStore()

const projects = ref([])
const keyword = ref('')
const minChars = ref(0)
const minItems = ref(0)
const sort = ref('recent')
const notice = ref(null)

const canSave = computed(() => store.sourceText.trim().length > 0)
const hasFilters = computed(
  () => keyword.value.trim() !== '' || Number(minChars.value) > 0 || Number(minItems.value) > 0,
)

const filtered = computed(() =>
  filterProjects(projects.value, {
    keyword: keyword.value,
    minChars: minChars.value,
    minItems: minItems.value,
    sort: sort.value,
  }),
)

function refresh() {
  projects.value = listProjects()
}

function resetFilters() {
  keyword.value = ''
  minChars.value = 0
  minItems.value = 0
  sort.value = 'recent'
}

function formatTime(timestamp) {
  if (!timestamp) return '—'
  const date = new Date(timestamp)
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function saveCurrent() {
  const record = projectFromCollation({
    sourceText: store.sourceText,
    items: store.items,
    translation: store.translation,
    meta: store.meta,
  })
  const result = saveProject(record)

  if (!result.ok) {
    notice.value = {
      level: 'warn',
      message:
        result.reason === 'unavailable'
          ? '当前浏览器不允许本地存储（隐私模式？），无法保存项目。'
          : '本机存储空间不足，保存失败。可先删除一些旧项目再试。',
    }
    return
  }
  notice.value =
    result.reason === 'metadata-only'
      ? { level: 'warn', message: `已保存「${record.title}」的摘要（篇幅较大，正文未入库，无法载入）。` }
      : { level: 'ok', message: `已保存「${record.title}」到本机项目列表。` }
  refresh()
}

function load(project) {
  // 从库里取完整记录（列表项可能只有元信息）
  const full = getProject(project.id)
  if (!full || full.contentStripped) {
    notice.value = { level: 'warn', message: '该项目只保存了摘要，正文未入库，无法载入。' }
    return
  }
  if (!store.restoreProject(full)) {
    notice.value = { level: 'warn', message: '载入失败：项目记录缺少原文。' }
    return
  }
  // 换了一篇：把上一轮的多维度分析一并清掉，避免张冠李戴
  analysis.reset()
  router.push('/collation')
}

function remove(project) {
  removeProject(project.id)
  notice.value = { level: 'ok', message: `已删除「${project.title}」。` }
  refresh()
}

onMounted(refresh)
</script>

<style scoped>
.view-head {
  display: flex;
  align-items: flex-start;
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
  line-height: 1.8;
  max-width: 720px;
}

.head-tag {
  font-size: 11px;
  color: var(--ink-muted);
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1px 8px;
}

.notice {
  border-radius: var(--radius-sm);
  padding: 9px 14px;
  font-size: 13px;
  margin-bottom: var(--space-4);
  border-left: 3px solid var(--success);
  background: #f3f9f1;
  color: #2e5b41;
}

.notice.warn {
  border-left-color: var(--warn);
  background: #fffbf0;
  color: #8a6d3b;
}

.filters {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px dashed var(--line);
  margin-bottom: var(--space-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: var(--ink-muted);
}

.field input,
.field select {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  font-size: 12px;
  background: #fff;
  outline: none;
  min-width: 120px;
}

.field input:focus,
.field select:focus {
  border-color: var(--cinnabar);
}

.field input[type='number'] {
  min-width: 90px;
}

.reset {
  border: 1px dashed var(--line);
  background: transparent;
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font-size: 12px;
  color: var(--ink-soft);
  cursor: pointer;
}

.reset:hover:not(:disabled) {
  border-color: var(--cinnabar);
  color: var(--cinnabar);
}

.reset:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.project-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.project-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  padding: 10px 14px;
  background: var(--surface);
}

.project-item:hover {
  border-color: var(--line);
  box-shadow: var(--shadow-card);
}

.item-main {
  min-width: 0;
}

.item-title {
  font-size: 14px;
  color: var(--ink);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-stripped {
  font-size: 11px;
  color: #8a6d3b;
  background: #fffbf0;
  border: 1px solid #f0e6cf;
  border-radius: 9px;
  padding: 0 6px;
  margin-left: 6px;
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--ink-faint);
}

.item-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.mini {
  border: 1px solid var(--cinnabar);
  background: #fff;
  color: var(--cinnabar);
  border-radius: var(--radius-sm);
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
}

.mini:hover:not(:disabled) {
  background: var(--cinnabar);
  color: #fff;
}

.mini:disabled {
  border-color: var(--line);
  color: var(--ink-faint);
  cursor: not-allowed;
}

.mini.danger {
  border-color: var(--line);
  color: var(--ink-muted);
}

.mini.danger:hover {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}

.notes {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--ink-muted);
  line-height: 2;
}

.notes code {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 0 4px;
  font-size: 12px;
}
</style>
