<template>
  <ChartBox :option="option" :empty="empty" height="260px" empty-text="还没有校勘结果，先完成一次校勘" empty-icon="🍩" />
</template>

<script setup>
/**
 * 类型分布环形图（docs/VISUAL.md §2）：这篇主要错在哪一类。
 * 数据换算在 utils/chartData.js 的 typeDistribution（纯函数、有测试），这里只画。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { typeDistribution } from '@/utils/chartData'
import { FONT_FAMILY, LEGEND_BASE, TOOLTIP_BASE } from '@/utils/chartTheme'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const empty = computed(() => props.items.length === 0)

const option = computed(() => ({
  tooltip: { ...TOOLTIP_BASE, trigger: 'item', formatter: '{b}：{c} 条（{d}%）' },
  legend: { ...LEGEND_BASE },
  series: [
    {
      type: 'pie',
      radius: ['45%', '68%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fffdfa', borderWidth: 2 },
      label: {
        show: true,
        formatter: '{b} {c}',
        color: '#555',
        fontSize: 11,
        fontFamily: FONT_FAMILY,
      },
      labelLine: { length: 8, length2: 8 },
      data: typeDistribution(props.items).map((row) => ({
        name: row.label,
        value: row.value,
        itemStyle: { color: row.color },
      })),
    },
  ],
}))
</script>
