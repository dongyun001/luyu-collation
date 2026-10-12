<template>
  <div class="volcano">
    <ChartBox
      :option="option"
      :empty="empty"
      height="320px"
      empty-text="还没有校勘结果，先完成一次校勘"
      empty-icon="🌋"
    />
    <!-- 四象限读法必须贴着图：否则这张图会变成"好看但看不懂" -->
    <dl v-if="!empty" class="quadrants">
      <div class="quadrant">
        <dt>左上 · 单字 · 高置信</dt>
        <dd>低风险高把握 → 可批量采纳</dd>
      </div>
      <div class="quadrant">
        <dt>右上 · 多字 · 高置信</dt>
        <dd>大改动但模型有把握 → <strong>重点复核</strong></dd>
      </div>
      <div class="quadrant">
        <dt>左下 · 单字 · 低置信</dt>
        <dd>小改但不确定 → 存疑，人工判断</dd>
      </div>
      <div class="quadrant">
        <dt>右下 · 多字 · 低置信</dt>
        <dd>大改且不确定 → 需版本证据，默认不采纳</dd>
      </div>
    </dl>
  </div>
</template>

<script setup>
/**
 * 校勘火山图（docs/VISUAL.md §3）。
 *
 * x = 改动字符数（1=单字替换，≥2=多字删补）；y = 置信显著性 -log10(1-confidence)。
 * 阈值线与坐标全部由 chartData.volcanoPoints 给出，本组件不写死任何数字——
 * 这样"图上的线"和"文档里写的线"不可能对不上。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { TYPE_COLORS, TYPE_ORDER, volcanoPoints } from '@/utils/chartData'
import { AXIS_LABEL, AXIS_NAME, FONT_FAMILY, LEGEND_BASE, SPLIT_LINE, TOOLTIP_BASE, grid } from '@/utils/chartTheme'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const empty = computed(() => props.items.length === 0)

const option = computed(() => {
  const { points, xMax, thresholds } = volcanoPoints(props.items)
  return {
    tooltip: {
      ...TOOLTIP_BASE,
      trigger: 'item',
      formatter: (params) => {
        const point = params.data
        return [
          point.name,
          `改动 ${point.impact} 字 · 置信度 ${Number(point.confidence).toFixed(2)}`,
          `状态：${point.status}`,
          point.reason ? `<span style="color:#888">${point.reason}</span>` : '',
        ]
          .filter(Boolean)
          .join('<br/>')
      },
    },
    // 图例只列实际出现过的类型，避免五色图例里三色是空的
    legend: {
      ...LEGEND_BASE,
      data: TYPE_ORDER.filter((type) => points.some((point) => point.type === type)),
    },
    grid: grid({ left: 48, right: 24, top: 26, bottom: 60 }),
    xAxis: {
      type: 'value',
      min: 0,
      max: xMax,
      name: '改动字符数（1=单字替换）',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: AXIS_NAME,
      axisLabel: { ...AXIS_LABEL, formatter: (value) => (Number.isInteger(value) ? value : '') },
      splitLine: SPLIT_LINE,
    },
    yAxis: {
      type: 'value',
      min: 0,
      name: '置信显著性',
      nameTextStyle: AXIS_NAME,
      axisLabel: AXIS_LABEL,
      splitLine: SPLIT_LINE,
    },
    series: [
      {
        type: 'scatter',
        symbolSize: 12,
        data: points.map((point) => ({
          ...point,
          itemStyle: { color: TYPE_COLORS[point.type] || '#777', opacity: 0.88 },
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#daa520', type: 'dashed', width: 1.2 },
          label: {
            fontSize: 10,
            color: '#8a6d3b',
            fontFamily: FONT_FAMILY,
            position: 'insideEndTop',
            // 竖线上的标签默认跟着线旋转成竖排，读不了；统一压成水平
            rotate: 0,
          },
          data: [
            { xAxis: thresholds.x, label: { formatter: '单字/多字 分界', position: 'insideStartTop' } },
            { yAxis: thresholds.y, label: { formatter: `高置信 ${thresholds.confidence}` } },
          ],
        },
      },
    ],
  }
})
</script>

<style scoped>
.quadrants {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 6px 16px;
  margin: 4px 0 0;
  font-size: 12px;
}
.quadrant {
  border-left: 2px solid var(--line);
  padding-left: 8px;
}
.quadrant dt {
  color: var(--ink-soft);
  font-weight: bold;
}
.quadrant dd {
  margin: 2px 0 0;
  color: var(--ink-muted);
  line-height: 1.6;
}
</style>
