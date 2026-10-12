/**
 * 图表通用样式片段（ECharts option 的公共部分）。
 *
 * 抽出来的理由：六张图如果各自写一遍字体/网格/提示框，改一次配色要改六处；
 * 这里保证「图与图之间长得像一套」。
 * 语义色仍然只来自 utils/chartData.js（TYPE_COLORS / STATUS_COLORS / KIND_COLORS）。
 */

export const FONT_FAMILY = "'Noto Serif SC', 'SimSun', 'PingFang SC', sans-serif"

export const AXIS_LABEL = { color: '#6b6b6b', fontSize: 11, fontFamily: FONT_FAMILY }

export const AXIS_NAME = { color: '#9a9a9a', fontSize: 11, fontFamily: FONT_FAMILY }

export const SPLIT_LINE = { lineStyle: { color: '#f0ece3' } }

export const TOOLTIP_BASE = {
  backgroundColor: 'rgba(255,255,255,0.97)',
  borderColor: '#e6e2d8',
  borderWidth: 1,
  textStyle: { color: '#333', fontSize: 12, fontFamily: FONT_FAMILY },
  extraCssText: 'box-shadow: 0 4px 14px rgba(43,43,43,0.12); border-radius: 6px;',
}

export const LEGEND_BASE = {
  bottom: 0,
  icon: 'circle',
  itemWidth: 9,
  itemHeight: 9,
  textStyle: { color: '#6b6b6b', fontSize: 12, fontFamily: FONT_FAMILY },
}

export const TITLE_BASE = {
  textStyle: { color: '#2b2b2b', fontSize: 13, fontWeight: 'normal', fontFamily: FONT_FAMILY },
}

/** 常用网格：给坐标轴留出轴名与图例的空间 */
export function grid(overrides = {}) {
  return { left: 44, right: 20, top: 24, bottom: 44, containLabel: false, ...overrides }
}
