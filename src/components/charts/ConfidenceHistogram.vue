<template>
  <ChartBox :option="option" :empty="empty" height="260px" empty-text="还没有校勘结果，先完成一次校勘" empty-icon="📊" />
</template>

<script setup>
/**
 * 置信度分布直方图（docs/VISUAL.md §2）：有多少建议是模型有把握的。
 *
 * 阈值线（默认 0.70）右侧即"参与一键采纳"的高置信组。
 * 分箱阈值与「高置信」判定同源：chartData 的 DEFAULT_CONFIDENCE_THRESHOLD。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { confidenceHistogram } from '@/utils/chartData'
import { AXIS_LABEL, FONT_FAMILY, SPLIT_LINE, TOOLTIP_BASE, grid } from '@/utils/chartTheme'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const empty = computed(() => props.items.length === 0)

const option = computed(() => {
  const { bins, threshold } = confidenceHistogram(props.items)
  // 第一根"高置信"柱的下标：阈值线画在这里，线上方即参与一键采纳的那批
  const firstHigh = Math.max(
    0,
    bins.findIndex((bin) => bin.start >= threshold - 1e-9),
  )
  const hasHigh = bins[firstHigh] !== undefined

  return {
    tooltip: {
      ...TOOLTIP_BASE,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const point = params[0]
        return `置信度 ${point.name}<br/>${point.value} 条`
      },
    },
    grid: grid({ left: 36, right: 20, top: 26, bottom: 58 }),
    xAxis: {
      type: 'category',
      data: bins.map((bin) => bin.label),
      axisLabel: { ...AXIS_LABEL, rotate: 42, fontSize: 10 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e6e2d8' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      name: '条数',
      nameTextStyle: { color: '#9a9a9a', fontSize: 11 },
      axisLabel: AXIS_LABEL,
      splitLine: SPLIT_LINE,
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 26,
        // 高置信柱用朱红、低置信柱用浅色：一眼看出"哪半边可以一键采纳"
        data: bins.map((bin, index) => ({
          value: bin.count,
          itemStyle: {
            color: index >= firstHigh ? '#8b1a1a' : '#e0b9b6',
            borderRadius: [3, 3, 0, 0],
          },
        })),
        markLine: hasHigh
          ? {
              silent: true,
              symbol: 'none',
              lineStyle: { color: '#daa520', type: 'dashed', width: 1.2 },
              label: {
                formatter: `≥ ${threshold.toFixed(2)} 参与一键采纳`,
                position: 'insideEndTop',
                // 竖线上的 markLine 标签默认跟着线一起旋转成竖排文字，可读性很差，强制水平
                rotate: 0,
                fontSize: 10,
                color: '#8a6d3b',
                fontFamily: FONT_FAMILY,
              },
              data: [{ xAxis: firstHigh }],
            }
          : undefined,
      },
    ],
  }
})
</script>
