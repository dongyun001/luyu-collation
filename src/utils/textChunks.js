/**
 * 把待校勘文本按句读边界切成若干段，供前端逐段提交、逐段渲染。
 *
 * 为什么需要：模型单次调用的耗时随文本长度**超线性增长**（实测 `mimo-v2.6-pro`：
 * 55 字 8.9s / 158 字 17.8s / 367 字 938.8s 超时）。一次吃下长文既慢又容易撞超时，
 * 切段之后每段都是一次**普通调用**，接口契约完全不变：
 * 响应里的 `offset` 是该段内的偏移，合并时加上该段在全文中的起点即可。
 *
 * 取舍（见 PRD §4）：
 * - 不重叠，所以跨句的对文证据可能看不全（同句/同段内不受影响）；
 * - 每段都会重发一次 Prompt，故设下限而非切得更碎。
 */

/**
 * 每段目标字数（下限）。
 *
 * 由实测反推，但**不是**用来卡单次调用的时限：上游延迟波动极大（同一段 100 字文本三次
 * 尝试 10.1s / 36.8s / 60.4s，极端到 253s），靠调小分块治不了超时——那由后端的
 * 停滞看门狗与段级重试负责（见 server/config.py、PRD §4）。
 * 取 100 字的目的是让**首段结果尽快到货**（用户等的就是这个），
 * 同时不让 Prompt 重发的开销占比过高。
 */
export const DEFAULT_TARGET = 100

/** 段数上限。按 100 字/段覆盖 PRD 允许的 5000 字（50 段），
 *  并发 3 跑完约 3~5 分钟，折算约 10~17 req/min，与后端 30 req/min 限流相容。 */
export const MAX_CHUNKS = 50

/** 同时在跑的段数。太大则后端限流吃紧，太小则总耗时线性偏长。 */
export const MAX_CONCURRENCY = 3

const PRIMARY_BREAK = /[。！？；!?;\n]/
const SECONDARY_BREAK = /[，、）」』】,)]/

/** 按「遇到断句字符就在其后切开」切成 [start, end) 区间。 */
function splitSpans(text, isBreak) {
  const spans = []
  let start = 0
  for (let index = 0; index < text.length; index += 1) {
    if (isBreak(text[index])) {
      spans.push([start, index + 1])
      start = index + 1
    }
  }
  if (start < text.length) spans.push([start, text.length])
  return spans
}

/**
 * 切分文本。
 * @param {string} rawText 原文（保留原样，不做 trim，以免打乱偏移）
 * @param {{target?: number, maxChunks?: number}} [options]
 * @returns {Array<{text: string, start: number, end: number}>} 按原文顺序排列，首尾相接、无重叠
 */
export function splitTextIntoChunks(rawText, options = {}) {
  const text = String(rawText ?? '')
  if (!text.trim()) return []

  const target = options.target ?? DEFAULT_TARGET
  const maxChunks = options.maxChunks ?? MAX_CHUNKS
  // 目标值与「按段数上限均分」取大者，保证段数不超上限
  const size = Math.max(target, Math.ceil(text.length / maxChunks))

  // 一级：按句读切。某个「句子」本身就超长（如无标点的长段）时，退到二级（逗号/顿号）
  const sentences = splitSpans(text, (char) => PRIMARY_BREAK.test(char))
  const spans = sentences.flatMap(([start, end]) => {
    if (end - start <= size * 1.6) return [[start, end]]
    return splitSpans(text.slice(start, end), (char) => SECONDARY_BREAK.test(char)).map(
      ([offsetStart, offsetEnd]) => [start + offsetStart, start + offsetEnd],
    )
  })

  // 贪心合并小句，直到达到 size
  const chunks = []
  let from = spans[0][0]
  let to = spans[0][1]
  for (let index = 1; index < spans.length; index += 1) {
    if (to - from < size) {
      to = spans[index][1]
      continue
    }
    chunks.push({ text: text.slice(from, to), start: from, end: to })
    from = spans[index][0]
    to = spans[index][1]
  }
  chunks.push({ text: text.slice(from, to), start: from, end: to })
  return chunks
}

/**
 * 把某段返回的条目偏移搬到全文坐标系。
 * 响应的 `offset` 是相对该段文本的，直接拿去标记原文会错位到文首。
 */
export function rebaseItems(items, chunkStart) {
  return (items ?? []).map((item) => ({
    ...item,
    offset: (Number.isInteger(item?.offset) ? item.offset : 0) + chunkStart,
  }))
}

/**
 * 跨段合并条目：按全文偏移排序、按「类型 + 原文 + 建议」去重、重新编号。
 *
 * 这里有四件事必须做对（否则界面会出 bug）：
 * 1. **每条都要有 status**，默认 'pending'（未处理）。没有它，`pendingItems` 永远为空，
 *    于是「待处理 N 处」恒为 0、「一键还原」按钮永远禁用。
 * 2. **沿用上一版同一条目的决定**：分段是边走边渲染的（`publish()` 每次都从模型原始返回
 *    重建整张列表），用户在等待期间采纳/还原过的条目不能被后续段的合并结果重置，
 *    否则表现为"采纳了又自己变回未处理"。所以决定要按内容键带过来。
 * 3. **重新编号**：后端返回的 `id` 是「该次调用内部」的序号，每段都从 1 开始
 *    （`server/routers/collate.py` 的 `enumerate(accepted, start=1)`），两段合并后会出现
 *    重复 id —— 会让 `accept(id)` 采纳到错误的条目（`find` 永远命中第一条）、
 *    也会让 v-for 的 `:key` 重复。这里按合并后的顺序统一重编号，保证全表唯一。
 * 4. 去重键是**四元组**：类型 + 原文 + 建议 + **offset**。带上位置才分得清两种情况——
 *    同一个字在文中两处各有一条同类建议（该留两条），与同一次建议被模型重复报（该去重）。
 *    分段**不重叠**，两段不可能产出同一个全局 offset，所以"同内容同 offset"只可能是后者，
 *    去重不会误伤真正的两处线索。（旧实现不带 offset，会把第二处当重复吞掉。）
 *
 * @param {Array<Array<object>>} groups 各段（已 rebase 到全文坐标系）的条目
 * @param {Array<object>} [previous] 上一版 `items`，用来把用户已做的决定带过来
 */
export function mergeCollationItems(groups, previous = []) {
  const keyOf = (item) => `${item.type}|${item.original}|${item.suggested}|${item.offset}`
  // 上一版已有决定（accepted / rejected）的条目，按内容键记住它的状态
  const decided = new Map((previous ?? []).map((item) => [keyOf(item), item.status]))

  const seen = new Set()
  const merged = []
  for (const group of groups ?? []) {
    for (const item of group ?? []) {
      const key = keyOf(item)
      if (seen.has(key)) continue
      seen.add(key)
      merged.push({ ...item, status: decided.get(key) ?? item.status ?? 'pending' })
    }
  }
  return merged
    .sort((a, b) => (a.offset ?? 0) - (b.offset ?? 0))
    .map((item, index) => ({ ...item, id: index + 1 }))
}
