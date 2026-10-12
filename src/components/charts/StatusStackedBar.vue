<template>
  <ChartBox :option="option" :empty="empty" height="260px" empty-text="还没有校勘结果，先完成一次校勘" empty-icon="🧱" />
</template>

<script setup>
/**
 * 状态堆叠柱（docs/VISUAL.md §2）：哪一类最容易采纳、哪一类争议最大。
 *
 * 每类一根柱，段为 待处理 / 已采纳 / 已还原。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { STATUS_LABELS, statusStacked } from '@/utils/chartData'
import { AXIS_LABEL, FONT_FAMILY, LEGEND_BASE, SPLIT_LINE, TOOLTIP_BASE, grid } from '@/utils/chartTheme'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const empty = computed(() => props.items.length === 0)

const option = computed(() => {
  const { categories, series } = statusStacked(props.items)
  return {
    tooltip: {
      ...TOOLTIP_BASE,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const total = params.reduce((sum, point) => sum + point.value, 0)
        const lines = params.map((point) => `${point.marker}${point.seriesName}：${point.value}`)
        return [`${params[0].name}（共 ${total} 条）`, ...lines].join('<br/>')
      },
    },
    legend: { ...LEGEND_BASE },
    grid: grid({ left: 36, right: 20, top: 20, bottom: 56 }),
    xAxis: {
      type: 'category',
      data: categories,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e6e2d8' } },
      axisLabel: { color: '#6b6b6b', fontSize: 12, fontFamily: FONT_FAMILY },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      name: '条数',
      nameTextStyle: { color: '#9a9a9a', fontSize: 11 },
      axisLabel: AXIS_LABEL,
      splitLine: SPLIT_LINE,
    },
    series: series.map((entry) => ({
      name: STATUS_LABELS[entry.key] || entry.name,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 36,
      data: entry.data,
      itemStyle: { color: entry.color },
      emphasis: { focus: 'series' },
    })),
  }
})
</script>
