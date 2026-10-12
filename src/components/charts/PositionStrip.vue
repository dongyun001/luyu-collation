<template>
  <ChartBox :option="option" :empty="empty" height="280px" empty-text="还没有校勘结果，先完成一次校勘" empty-icon="📍" />
</template>

<script setup>
/**
 * 位置分布条带图（docs/VISUAL.md §2）：错误是均匀分布，还是集中在某几段。
 *
 * x = 字符位置，y = 类型泳道；颜色 = 决策状态。
 * 同一泳道里位置相近的点会纵向错开（strip plot 的常规做法，避免点叠成一个）——
 * 这是**展示层**的抖动，不改 offset 的真实值，提示框里给的仍是精确位置。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { STATUS_COLORS, STATUS_LABELS, positionStrip } from '@/utils/chartData'
import { AXIS_LABEL, AXIS_NAME, FONT_FAMILY, SPLIT_LINE, TOOLTIP_BASE, grid } from '@/utils/chartTheme'

const props = defineProps({
  items: { type: Array, default: () => [] },
  textLength: { type: Number, default: 0 },
})

const empty = computed(() => props.items.length === 0)

const JITTER_OFFSETS = [-0.24, 0.24, -0.12, 0.12, 0]

const option = computed(() => {
  const { lanes, points, xMax } = positionStrip(props.items, props.textLength)
  const laneOf = new Map(lanes.map((lane, index) => [lane, index]))
  // 同一泳道内的点按序错开，保证重叠的点都能看见
  const seenPerLane = new Map()

  return {
    tooltip: {
      ...TOOLTIP_BASE,
      trigger: 'item',
      formatter: (params) => {
        const point = params.data
        return [
          point.name,
          `位置：第 ${point.offset + 1} 字`,
          `状态：${STATUS_LABELS[point.status] || point.status}`,
        ].join('<br/>')
      },
    },
    grid: grid({ left: 24, right: 24, top: 20, bottom: 52 }),
    xAxis: {
      type: 'value',
      min: 0,
      max: xMax,
      name: '原文位置（字）',
      nameLocation: 'middle',
      nameGap: 26,
      nameTextStyle: AXIS_NAME,
      axisLabel: { ...AXIS_LABEL, fontSize: 10 },
      splitLine: SPLIT_LINE,
    },
    yAxis: {
      type: 'category',
      data: lanes,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e6e2d8' } },
      axisLabel: { color: '#6b6b6b', fontSize: 12, fontFamily: FONT_FAMILY },
    },
    series: [
      {
        type: 'scatter',
        symbolSize: 11,
        data: points.map((point) => {
          const lane = laneOf.get(point.type)
          const index = seenPerLane.get(lane) || 0
          seenPerLane.set(lane, index + 1)
          return {
            value: [point.offset, lane + JITTER_OFFSETS[index % JITTER_OFFSETS.length]],
            name: point.name,
            offset: point.offset,
            status: point.status,
            itemStyle: { color: STATUS_COLORS[point.status] || '#8b1a1a', opacity: 0.9 },
          }
        }),
      },
    ],
  }
})
</script>
