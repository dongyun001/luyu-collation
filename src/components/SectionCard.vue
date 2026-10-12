<template>
  <section class="guji-section guji-scroll-frame guji-texture">
    <!-- 天头朱红细线：真实元素而非 ::before，避免与底纹抢同一个伪元素（见 theme.css 注释） -->
    <span class="guji-section__rule" aria-hidden="true"></span>

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
 * 这里只负责结构与可选底纹（底纹用 patterns.css 的全局类，避免重复定义）。
 *
 * 装饰各占一个位子，互不争抢：
 *   面纹理 → `::before`（`.guji-texture`）｜天头朱红细线 → 真实元素 `.guji-section__rule`
 *   ｜四角卷轴角饰 → `::after`（`.guji-scroll-frame`）
 *
 * 2026-10-12 第二轮：原来只有 `pattern="slips"` 的区块才有底纹，其余是纯白面，
 * 于是"整片界面只有白"。现在**每一块都是暖纸色 + 面纹理**，不再传 pattern。
 */
defineProps({
  title: { type: String, default: '' },
  sub: { type: String, default: '' },
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
