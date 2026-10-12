<template>
  <div class="progress-meter" :class="{ 'is-compact': compact }">
    <div
      class="progress-track"
      role="progressbar"
      :aria-label="ariaLabel"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="progress-fill" :style="{ width: `${percent}%` }"></div>
    </div>
    <p class="progress-readout">
      已用时 <strong>{{ seconds }}</strong> 秒<template v-if="label"> · {{ label }}</template>
    </p>
    <p v-if="hint" class="progress-hint">{{ hint }}</p>
  </div>
</template>

<script setup>
/**
 * 读秒进度条（校勘加载屏、校勘工作台横条、多维度分析加载态**共用同一个组件**）。
 *
 * 为什么做成组件：进度显示曾经被拆成两套、还分裂到两个屏上——
 * 条形在一屏（且宽度由时间驱动，done=0 也在涨），会递增的计数在另一屏（那里没有条形），
 * 于是用户在"有条形的那一屏"永远只看到 0（见 HANDOFF §7「收尾之三」）。
 * 合成一个组件后，调用方无法只取其一，结构上就杜绝了这种割裂。
 *
 * 口径：条宽是按已用时间**渐近预估**的，不是真实进度；读数里的秒数是如实的
 * （算式见 utils/progressMeter.js）。
 */
defineProps({
  /** 0..100，由 utils/progressMeter.js 的 asymptoticPercent 算出 */
  percent: { type: Number, required: true },
  seconds: { type: Number, default: 0 },
  /** 追加在秒数后的进度文案，如「已完成 3/6 段 · 进行中 3」 */
  label: { type: String, default: '' },
  /** 口径说明等补充文字（可空） */
  hint: { type: String, default: '' },
  ariaLabel: { type: String, default: '处理进度' },
  /** 紧凑模式：用于工作台横条这类窄条场景 */
  compact: { type: Boolean, default: false },
})
</script>
