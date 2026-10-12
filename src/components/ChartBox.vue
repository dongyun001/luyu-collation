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
  // notMerge=true：切换数据源（如"全部/筛选结果"）时清掉上一份系列，避免残留
  chart.setOption(props.option, true)
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
