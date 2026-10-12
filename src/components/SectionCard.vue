<template>
  <section
    class="guji-section"
    :class="[{ 'guji-paper': pattern }, pattern === 'fret' ? 'guji-paper--fret' : '', pattern === 'slips' ? 'guji-paper--slips' : '']"
  >
    <header v-if="title" class="guji-section__head">
      <div class="head-main">
        <h3 class="guji-section__title">{{ title }}</h3>
        <p v-if="sub" class="guji-section__sub">{{ sub }}</p>
      </div>
      <div class="head-actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>

<script setup>
/**
 * 卷轴式区块外壳（看板每块内容的统一容器）。
 *
 * 样式来自全局 `src/styles/theme.css` 的 `.guji-section`，
 * 这里只负责结构与可选底纹（底纹也用 patterns.css 的全局类，避免重复定义）。
 */
defineProps({
  title: { type: String, default: '' },
  sub: { type: String, default: '' },
  /** '' | 'fret' | 'slips'：是否叠一层自绘纹样 */
  pattern: { type: String, default: '' },
})
</script>

<style scoped>
.head-main {
  min-width: 0;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}
</style>
