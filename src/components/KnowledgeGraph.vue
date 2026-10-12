<template>
  <div class="graph">
    <ChartBox
      :option="option"
      :empty="empty"
      height="420px"
      empty-text="尚未生成知识图谱 —— 点击「生成多维度分析」后出现"
      empty-icon="🕸"
    />
    <p v-if="!empty" class="graph-note">
      节点为实体、连线为关系；点选节点即高亮其直接关联（其余淡出），悬浮查看释义。
      节点大小反映连接度，图例按实体类别着色。数据来自模型输出并已过滤悬空关系。
    </p>
  </div>
</template>

<script setup>
/**
 * 知识图谱（F11，docs/VISUAL.md §4.3）。
 *
 * 力导向布局，**关闭任何自动旋转/动画循环**——旋转会让评委看不清标签。
 * 悬空边（端点不在实体表里）在后端就被丢弃（API.md §6），前端只负责画。
 */
import { computed } from 'vue'

import ChartBox from '@/components/ChartBox.vue'
import { knowledgeGraph } from '@/utils/chartData'
import { FONT_FAMILY, LEGEND_BASE, TOOLTIP_BASE } from '@/utils/chartTheme'

const props = defineProps({
  entities: { type: Array, default: () => [] },
  relations: { type: Array, default: () => [] },
})

const empty = computed(() => props.entities.length === 0)

const option = computed(() => {
  const { nodes, links, categories } = knowledgeGraph(props.entities, props.relations)
  return {
    tooltip: {
      ...TOOLTIP_BASE,
      formatter: (params) => {
        if (params.dataType === 'edge') {
          return `${params.data.source} → ${params.data.target}<br/>${params.data.relation || '（未命名关系）'}`
        }
        const note = params.data.note
        return [`<strong>${params.data.name}</strong>`, params.data.kind, note]
          .filter(Boolean)
          .join('<br/>')
      },
    },
    legend: {
      ...LEGEND_BASE,
      data: categories.map((category) => category.name),
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: { repulsion: 180, edgeLength: 100, gravity: 0.08 },
        label: {
          show: true,
          position: 'right',
          fontSize: 12,
          color: '#333',
          fontFamily: FONT_FAMILY,
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 7,
        lineStyle: { color: '#c9c2b4', width: 1.2, curveness: 0.08 },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 2.4, color: '#8b1a1a' },
          label: { fontWeight: 'bold' },
        },
        categories,
        data: nodes,
        links,
      },
    ],
  }
})
</script>

<style scoped>
.graph-note {
  margin: 0;
  font-size: 12px;
  color: var(--ink-muted);
  line-height: 1.8;
}
</style>
