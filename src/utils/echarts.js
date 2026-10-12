/**
 * ECharts 按需注册（docs/TECH_DESIGN.md §2）。
 *
 * 只注册本项目真正用到的图表与组件：这样 ECharts 的体积才能压住，
 * 且因为它只被 `/analysis` 路由（懒加载）引用，不进入首屏包。
 * 新增图表类型时**在这里登记**，而不是在组件里 import 整个 echarts。
 */

import * as echarts from 'echarts/core'
import { BarChart, GraphChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart,
  GraphChart,
  PieChart,
  RadarChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
])

export default echarts
