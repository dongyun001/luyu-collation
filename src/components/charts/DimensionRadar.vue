<template>
  <div class="radar">
    <ChartBox
      :option="option"
      :empty="empty"
      height="300px"
      empty-text="尚未生成多维度分析"
      empty-icon="🧭"
    />
    <p v-if="!empty" class="radar-note">
      轴值为该维度的判断置信度；<strong>0 表示「未能判断」，不是「判断为否」</strong>。
      <template v-if="missingLabels.length">
        未判断：{{ missingLabels.join('、') }}。
      </template>
      <template v-if="uncertainLabels.length">
        存疑：{{ uncertainLabels.join('、') }}。
      </template>
      具体判断与依据见下方维度卡片。
    </p>
  </div>
</template>

<script setup>
/**
 * 七维雷达（docs/VISUAL.md §4.1）：一眼看"这篇文献画像"。
 *
 * 轴固定 7 根、顺序恒定（不随数据变），missing 的维度记 0 并在注文里点名——
 * 否则读图人会把"没判断"误读成"判断为否"。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { dimensionRadar } from '@/utils/chartData'
import { FONT_FAMILY, TOOLTIP_BASE } from '@/utils/chartTheme'

const props = defineProps({
  dimensions: { type: Array, default: () => [] },
})

const empty = computed(() => props.dimensions.length === 0)

const computedRadar = computed(() => dimensionRadar(props.dimensions))
const missingLabels = computed(() => computedRadar.value.missingLabels)
const uncertainLabels = computed(() => computedRadar.value.uncertainLabels)

const option = computed(() => {
  const { indicators, values } = computedRadar.value
  return {
    tooltip: { ...TOOLTIP_BASE },
    radar: {
      indicator: indicators,
      radius: '64%',
      center: ['50%', '52%'],
      axisName: { color: '#555', fontSize: 11, fontFamily: FONT_FAMILY },
      splitLine: { lineStyle: { color: '#e6e2d8' } },
      splitArea: {
        areaStyle: { color: ['rgba(253,251,247,0.7)', 'rgba(255,255,255,0.7)'] },
      },
      axisLine: { lineStyle: { color: '#e6e2d8' } },
    },
    series: [
      {
        type: 'radar',
        symbolSize: 5,
        data: [
          {
            value: values,
            name: '判断置信度',
            areaStyle: { color: 'rgba(139, 26, 26, 0.16)' },
            lineStyle: { color: '#8b1a1a', width: 2 },
            itemStyle: { color: '#8b1a1a' },
          },
        ],
      },
    ],
  }
})
</script>

<style scoped>
.radar-note {
  margin: 0;
  font-size: 12px;
  color: var(--ink-muted);
  line-height: 1.8;
}
.radar-note strong {
  color: var(--ink-soft);
}
</style>
