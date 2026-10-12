/**
 * 读秒与"按时间渐近"的进度估算（校勘、多维度分析共用）。
 *
 * 为什么把这两件事抽出来：进度显示曾经被拆成两套、还分裂到两个屏上
 * （条形在一屏、有效计数在另一屏，见 HANDOFF §7「收尾之三」），
 * 同一份逻辑写两遍就是这类问题的温床。现在只有这一份。
 *
 * 口径（沿用 PRD §4 的既有说法，这不是新发明的"假进度"）：
 *  - 真实进度**拿不到**（模型什么时候返回、分几段都无法预知），所以条宽是按已用时间
 *    渐近逼近上限的**预估**，读数里的秒数才是如实的；
 *  - 永不满格（上限 95%），避免在还没结束时暗示"完成了"；
 *  - 有分段可比时（校勘按句读分段），段数占比取 max 参与——让真实进展说话。
 */

import { ref } from 'vue'

/** 进度条上限：永不满格。 */
export const PROGRESS_MAX_PERCENT = 95

/** 时间基准：等待到该秒数时条宽约 63%（1 - 1/e），之后渐近逼近上限。 */
export const PROGRESS_EXPECTED_S = 30

/**
 * 创建一个"已用秒数"秒表。
 *
 * @param {{intervalMs?: number}} [options]
 * @returns {{seconds: import('vue').Ref<number>, start: () => void, stop: () => void}}
 */
export function createElapsedTicker({ intervalMs = 1000 } = {}) {
  const seconds = ref(0)
  let handle = null

  function stop() {
    if (handle !== null) {
      clearInterval(handle)
      handle = null
    }
  }

  function start() {
    stop()
    seconds.value = 0
    const beganAt = Date.now()
    handle = setInterval(() => {
      seconds.value = Math.floor((Date.now() - beganAt) / 1000)
    }, intervalMs)
  }

  return { seconds, start, stop }
}

/**
 * 按"时间渐近"与"已完成占比"取较大者估算条宽（百分比，永不超过 95）。
 *
 * @param {number} seconds 已用秒数
 * @param {number} [ratio] 已完成占比 0..1（无分段时传 0）
 * @param {number} [expectedS] 时间基准秒数
 */
export function asymptoticPercent(seconds, ratio = 0, expectedS = PROGRESS_EXPECTED_S) {
  // 秒数与基准都先兜住异常值：NaN/负数/0 基准都会让算式产出 NaN 或除零
  const secs = Math.max(0, Number(seconds) || 0)
  const expected = Number(expectedS) > 0 ? Number(expectedS) : PROGRESS_EXPECTED_S
  const byTime = PROGRESS_MAX_PERCENT * (1 - Math.exp(-secs / expected))
  const clamped = Math.max(0, Math.min(1, Number(ratio) || 0))
  const byRatio = clamped * PROGRESS_MAX_PERCENT
  return Math.min(PROGRESS_MAX_PERCENT, Math.round(Math.max(byTime, byRatio)))
}
