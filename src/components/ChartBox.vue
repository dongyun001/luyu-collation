<template>
  <div class="chart-box">
    <div v-if="empty" class="guji-empty">
      <span class="guji-empty__icon">{{ emptyIcon }}</span>
      {{ emptyText }}
    </div>
    <div v-else ref="host" class="chart-box__canvas" :style="{ height }"></div>
  </div>
</template>

<script setup>
/**
 * ECharts 通用封装（docs/TECH_DESIGN.md §3）。
 *
 * 只做四件事：init / 换 option / 跟随容器尺寸 / 卸载时销毁。
 * 空态由 `empty` 控制——**这是"不渲染假数据"红线的落点**：
 * 没数据时显示空态文案，而不是画一张全是 0 的图让人误以为算过了。
 *
 * 无障碍：系统的"减少动态效果"偏好也要管住 ECharts——它的入场动画（柱子长出来、饼图扫开、
 * 力导向图收敛）走的是 canvas 自绘，**不吃 CSS 的 animation**，所以必须在 option 上关。
 * 全站 6 张图 + 知识图谱都经由本组件渲染，因此这一处就够，不必逐个图去写。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts from '@/utils/echarts'

const props = defineProps({
  /** 直接喂给 ECharts 的 option（由 utils/chartData.js 的纯函数生成） */
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  empty: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无可视化数据' },
  emptyIcon: { type: String, default: '📊' },
})

const host = ref(null)
let chart = null
let observer = null

/** 是否偏好减少动态效果（SSR/旧浏览器拿不到 matchMedia 时按"不减少"处理）。 */
function prefersReducedMotion() {
  return Boolean(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)
}

function dispose() {
  if (observer) {
    observer.disconnect()
    observer = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
}

function render() {
  if (props.empty || !host.value) return
  if (!chart) {
    chart = echarts.init(host.value)
    // 跟随容器尺寸：看板是响应式布局，侧栏折叠/窗口缩放都要重排
    observer = new ResizeObserver(() => {
      chart?.resize()
    })
    observer.observe(host.value)
  }
  // notMerge=true：切换数据源（如"全部/筛选结果"）时清掉上一份系列，避免残留。
  // animation 由偏好决定，写在 option 之后，避免被图表自己的设置覆盖。
  chart.setOption({ ...props.option, animation: !prefersReducedMotion() }, true)
}

onMounted(() => nextTick(render))

watch(
  () => props.empty,
  (isEmpty) => {
    if (isEmpty) dispose()
    else nextTick(render)
  },
)

watch(
  () => props.option,
  () => nextTick(render),
  { deep: true },
)

onBeforeUnmount(dispose)
</script>

<style scoped>
.chart-box {
  width: 100%;
}

.chart-box__canvas {
  width: 100%;
  min-height: 120px;
}
</style>
