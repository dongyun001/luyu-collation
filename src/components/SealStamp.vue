<template>
  <!-- 外层负责定位（用 transform 居中），内层负责动画（也吃 transform），
       两者分开才不会互相覆盖 -->
  <span class="seal-slot" :class="`seal-slot--${placement}`" aria-hidden="true">
    <svg class="seal-stamp" :width="size" :height="size" viewBox="0 0 40 40">
      <rect x="1.5" y="1.5" width="37" height="37" rx="5" fill="#8b1a1a" />
      <rect
        x="5.5"
        y="5.5"
        width="29"
        height="29"
        rx="3"
        fill="none"
        stroke="#ffffff"
        stroke-width="1.1"
        opacity="0.8"
      />
      <text
        x="20"
        y="27.5"
        text-anchor="middle"
        font-size="20"
        font-family="'Noto Serif SC', 'KaiTi', serif"
        fill="#ffffff"
      >
        {{ text }}
      </text>
    </svg>
  </span>
</template>

<script setup>
/**
 * 「印章落章」——**一次性**的完成动效（不是循环动画）。
 *
 * 触发方式：调用方用 `v-if` 挂在"完成"状态上，元素挂载即播放一次；
 * 重置后重跑会重新挂载，于是自然重播一次。比手动加 class/去 class 稳。
 *
 * 无障碍：`theme.css` 末尾的全局 `prefers-reduced-motion` 规则（`*` 选择器）
 * 会把这里的动画压成 0.01ms/单次并清掉延迟，因此不需要在本组件里重复接线。
 *
 * 纯装饰：`aria-hidden`，且 `pointer-events: none`，不参与交互也不被读屏播报。
 */
defineProps({
  /** 印章上的字，与页面上的信息对应（如「校」「析」） */
  text: { type: String, default: '校' },
  /** 边长（px） */
  size: { type: Number, default: 30 },
  /** header=落在标题栏中部的空位；corner=落在容器右上角；toolbar=作为行内元素落在工具栏空白处 */
  placement: { type: String, default: 'header' },
})
</script>

<style scoped>
.seal-slot {
  position: absolute;
  z-index: 30;
  pointer-events: none;
}

/* 落在标题栏中部的空位：不与左侧标题、右侧按钮打架 */
.seal-slot--header {
  top: 9px;
  left: 50%;
  transform: translateX(-50%);
}

.seal-slot--corner {
  top: 14px;
  right: 18px;
}

/* 行内落在工具栏的空白处（那里有 flex:1 的 spacer）。
   为什么需要这个模式：工作台的结果面板天头是 `z-index:10`，绝对定位的印章（z-index 较小）
   会被它盖住——实测就是这样"什么也看不到"，动效等于白做。 */
.seal-slot--toolbar {
  position: static;
  flex-shrink: 0;
}

.seal-stamp {
  display: block;
  filter: drop-shadow(0 2px 5px rgba(139, 26, 26, 0.28));
  animation: sealDrop 0.52s cubic-bezier(0.22, 1.2, 0.36, 1) both;
}

/* 从上方落下、微微压印回弹，落定后留一点手盖的倾斜角 */
@keyframes sealDrop {
  0% {
    opacity: 0;
    transform: translateY(-18px) scale(1.4) rotate(-10deg);
  }
  60% {
    opacity: 1;
    transform: translateY(1px) scale(0.97) rotate(-4deg);
  }
  100% {
    opacity: 0.92;
    transform: translateY(0) scale(1) rotate(-4deg);
  }
}
</style>
