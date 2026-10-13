<template>
  <div class="compare-view">
    <SectionCard
      title="版本对勘"
      sub="底本 × 参照本逐字对齐，列出两本写法不同之处。纯规则计算，不调用大模型，断网可用。"
    >
      <div class="intro">
        <p class="intro-line">
          这是<b>四法引擎</b>里的<b>对校</b>：与理校（大模型）不同，它给的是确定性结论——
          同样的两段文本，永远得到同一份异文清单，可直接核对。
          察出的是<b>版本差异</b>，不是"该改成什么"的建议。
        </p>
      </div>

      <div class="input-grid">
        <label class="field">
          <span class="field-label">
            底本
            <em class="field-hint">{{ baseText.length }} / 5000 字</em>
          </span>
          <textarea
            v-model="baseText"
            class="field-input"
            rows="7"
            placeholder="粘贴底本文本（≤5000 字）"
          ></textarea>
        </label>

        <div class="reference-column">
          <div class="field-label reference-head">
            <span>参照本（1–3 个）</span>
            <button
              type="button"
              class="guji-btn guji-btn--ghost"
              :disabled="!store.canAddReference"
              @click="store.addReference()"
            >
              + 添加参照本
            </button>
          </div>

          <div v-for="(reference, index) in references" :key="index" class="reference">
            <div class="reference-top">
              <input
                :value="reference.name"
                class="reference-name"
                type="text"
                maxlength="20"
                :placeholder="`参照本名称，如「甲本」（留空按「参照本${index + 1}」计）`"
                @input="store.updateReference(index, { name: $event.target.value })"
              />
              <button
                type="button"
                class="guji-btn guji-btn--ghost remove"
                :disabled="references.length <= 1"
                title="移除这个参照本"
                @click="store.removeReference(index)"
              >
                移除
              </button>
            </div>
            <textarea
              :value="reference.text"
              class="field-input"
              rows="5"
              :placeholder="`粘贴${reference.name.trim() || `参照本${index + 1}`}的文本`"
              @input="store.updateReference(index, { text: $event.target.value })"
            ></textarea>
          </div>
        </div>
      </div>

      <div class="toolbar">
        <button type="button" class="guji-btn primary" :disabled="!store.canRun || store.isRunning" @click="onRun">
          {{ store.isRunning ? '对勘中…' : '开始对勘' }}
        </button>
        <button type="button" class="guji-btn guji-btn--ghost" :disabled="store.isRunning" @click="store.reset()">
          清空
        </button>
        <span class="tool-spacer"></span>
        <button
          type="button"
          class="guji-btn guji-btn--ghost"
          :disabled="!store.canExport"
          :title="store.canExport ? '' : '两本一致或尚未对勘时没有校勘记可写'"
          @click="onExport"
        >
          导出对勘记
        </button>
      </div>

      <p v-if="exportMessage" class="export-message">{{ exportMessage }}</p>

      <div v-if="store.error" class="error-box">
        <strong>{{ store.error.message }}</strong>
        <span v-if="store.error.hint" class="error-hint">{{ store.error.hint }}</span>
      </div>
    </SectionCard>

    <!-- 结果 -->
    <SectionCard
      v-if="store.isReady"
      title="对勘结果"
      :sub="resultSub"
    >
      <template #actions>
        <span v-if="store.itemCount" class="guji-chip">异文 {{ store.itemCount }} 处</span>
        <span v-if="store.presenceCount" class="guji-chip">版本存缺 {{ store.presenceCount }} 处</span>
      </template>

      <p v-if="store.identical" class="identical">
        参照本与底本在此范围内<b>逐字一致</b>，没有异文。这也是一个有效结论：说明这几处不必再查别本。
      </p>

      <ol v-if="store.itemCount" class="item-list">
        <li v-for="item in store.items" :key="`${item.offset}-${item.source}`" class="item">
          <span class="guji-num">{{ item.id }}</span>
          <div class="item-body">
            <div class="item-pair">
              <span class="fragment original">{{ item.original }}</span>
              <span class="arrow" aria-hidden="true">→</span>
              <span class="fragment suggested">{{ item.suggested }}</span>
              <span class="guji-chip source">{{ item.source }}</span>
              <span class="guji-chip deterministic" title="字符级对齐是确定性的，不存在模型置信度">确定性</span>
            </div>
            <p class="item-reason">{{ item.reason }}</p>
            <p class="item-locator">底本第 {{ item.offset + 1 }} 字起</p>
          </div>
        </li>
      </ol>

      <div v-if="store.presenceCount" class="presence">
        <h4 class="presence-title">版本存缺（<b>不计入</b>校勘五类）</h4>
        <p class="presence-note">
          一方有一方无的片段。脱/衍是有方向的（"谁相对谁是脱"），而对校只说得清"两本不一致"，
          硬归入五类会误读，所以单列在此。
        </p>
        <ul class="presence-list">
          <li v-for="(diff, index) in store.presenceDiffs" :key="`${diff.offset}-${diff.source}-${index}`" class="presence-item">
            <span class="guji-chip source">{{ diff.source }}</span>
            <span class="presence-kind">{{ KIND_LABELS[diff.kind] || diff.kind }}</span>
            <span class="fragment">{{ diff.text }}</span>
            <span class="item-locator">底本第 {{ diff.offset + 1 }} 字处</span>
          </li>
        </ul>
      </div>
    </SectionCard>
  </div>
</template>

<script setup>
/**
 * 版本对勘页（F13 对校引擎）。
 *
 * 三点刻意的设计：
 *  ① **不显示置信度百分比**。后端的 `confidence` 恒为 1.0，只为复用数据结构；
 *     把它画成"100% 可信"是误导，所以这里显示的是「确定性」徽标。
 *  ② **不做三栏对照 UI**。v1 只交"底本 + 参照本 → 异文清单 + 导出"（计划里的明确收口），
 *     完整的三栏版本对勘留给阶段二，避免把页面做复杂却没人验证。
 *  ③ 空态照实说。两本一致时明确写出"逐字一致，没有异文"——这是结论，不是失败。
 */
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import SectionCard from '@/components/SectionCard.vue'
import { useCompareStore } from '@/stores/compare'

const store = useCompareStore()
// 必须走 storeToRefs：直接从 store 解构拿到的是**当时的取值**，v-model 会写不回去
const { baseText, references } = storeToRefs(store)
const exportMessage = ref('')

const KIND_LABELS = {
  'reference-missing': '参照本缺',
  'reference-extra': '参照本多',
}

const resultSub = computed(() => {
  const elapsed = store.meta.elapsedMs
  const names = store.referenceNames
  const against = names.length ? `与 ${names.join('、')} 比对` : '与参照本比对'
  return `${against} · 耗时 ${elapsed} 毫秒 · ${store.meta.requestId}`
})

async function onRun() {
  exportMessage.value = ''
  await store.run()
}

function onExport() {
  const result = store.exportNote(`底本对勘 · ${store.referenceNames.join('、') || '参照本'}`)
  exportMessage.value = result.ok ? `已导出 ${result.filename}` : result.message
}
</script>

<style scoped>
.compare-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.intro-line {
  margin: 0 0 var(--space-4);
  color: var(--ink-soft);
  line-height: 1.8;
}

.input-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-4);
}

@media (max-width: 900px) {
  .input-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--cinnabar);
}

.field-hint {
  font-style: normal;
  font-weight: 400;
  font-size: 12px;
  color: var(--ink-muted);
}

.field-input {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface-veil);
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 14px;
  line-height: 1.8;
  resize: vertical;
}

.field-input:focus {
  outline: none;
  border-color: var(--cinnabar);
}

.reference-column {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.reference-head {
  gap: var(--space-2);
}

.reference {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  background: var(--surface-sunken);
}

.reference-top {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.reference-name {
  flex: 1;
  min-width: 0;
  padding: 6px var(--space-2);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--ink);
  font-family: var(--font-sans);
  font-size: 13px;
}

.reference-name:focus {
  outline: none;
  border-color: var(--cinnabar);
}

.remove {
  flex-shrink: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius);
  background: var(--surface-sunken);
}

.tool-spacer {
  flex: 1;
}

.toolbar .guji-btn.primary {
  background: var(--cinnabar);
  color: #fff;
  border-color: var(--cinnabar);
  font-weight: 600;
}

.toolbar .guji-btn.primary:hover:not(:disabled) {
  background: var(--cinnabar-dark);
}

.toolbar .guji-btn {
  white-space: nowrap;
}

.export-message {
  margin: var(--space-2) 0 0;
  font-size: 13px;
  color: var(--success);
}

.error-box {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-top: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--danger);
  border-radius: var(--radius);
  background: var(--cinnabar-wash);
  color: var(--danger);
  font-size: 13px;
}

.error-hint {
  color: var(--ink-soft);
}

.identical {
  margin: 0;
  padding: var(--space-4);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  background: var(--surface-veil);
  color: var(--ink-soft);
  line-height: 1.8;
}

.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--line-soft);
  border-left: 3px solid var(--type-yiwen);
  border-radius: var(--radius);
  background: var(--surface-veil);
}

.item-body {
  min-width: 0;
  flex: 1;
}

.item-pair {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.fragment {
  font-family: var(--font-serif);
  font-size: 15px;
}

.original {
  color: var(--ink-muted);
  text-decoration: line-through;
}

.suggested {
  color: var(--cinnabar);
  font-weight: 600;
}

.arrow {
  color: var(--ink-faint);
}

.guji-chip.source {
  background: var(--cinnabar-wash);
  color: var(--cinnabar);
}

.guji-chip.deterministic {
  background: var(--surface-sunken);
  color: var(--ink-muted);
}

.item-reason {
  margin: var(--space-2) 0 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.7;
}

.item-locator {
  margin: var(--space-1) 0 0;
  color: var(--ink-faint);
  font-size: 12px;
}

.presence {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px dashed var(--line);
}

.presence-title {
  margin: 0;
  font-size: 14px;
  color: var(--ink);
}

.presence-note {
  margin: var(--space-2) 0 var(--space-3);
  color: var(--ink-muted);
  font-size: 12px;
  line-height: 1.7;
}

.presence-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.presence-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  background: var(--surface-sunken);
}

.presence-kind {
  font-size: 13px;
  color: var(--type-yanwen);
}
</style>
