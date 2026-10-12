/**
 * 读秒与进度估算公共件的测试。
 *
 * 这一层被校勘与多维度分析共用，算错了两边一起错，所以边界要钉死：
 * 起始为 0、按时间单调递增、**永不满格**（不满格是刻意的，避免暗示"已完成"）、
 * 占比占优时以占比为准、秒表停表后不再走。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  PROGRESS_EXPECTED_S,
  PROGRESS_MAX_PERCENT,
  asymptoticPercent,
  createElapsedTicker,
} from './progressMeter'

describe('asymptoticPercent', () => {
  it('起点为 0，随秒数单调递增', () => {
    expect(asymptoticPercent(0, 0)).toBe(0)
    expect(asymptoticPercent(5, 0)).toBeLessThan(asymptoticPercent(20, 0))
    expect(asymptoticPercent(20, 0)).toBeLessThan(asymptoticPercent(120, 0))
  })

  it('时间基准处约到 63%（1 - 1/e）', () => {
    expect(asymptoticPercent(PROGRESS_EXPECTED_S, 0)).toBe(Math.round(PROGRESS_MAX_PERCENT * (1 - Math.exp(-1))))
  })

  it('永不满格：无论等多久都封顶在 95%', () => {
    expect(asymptoticPercent(10 ** 6, 0)).toBe(PROGRESS_MAX_PERCENT)
    expect(asymptoticPercent(10 ** 6, 1)).toBe(PROGRESS_MAX_PERCENT)
  })

  it('占比更大时以占比为准（真实进展优先于时间预估）', () => {
    expect(asymptoticPercent(0, 0.5)).toBe(Math.round(PROGRESS_MAX_PERCENT * 0.5))
    // 时间已很久但一段没回来时，仍取较大的那一项（不会因占比小就倒退）
    expect(asymptoticPercent(300, 0.1)).toBeGreaterThanOrEqual(Math.round(PROGRESS_MAX_PERCENT * 0.1))
  })

  it('异常入参不产生负数或 NaN', () => {
    expect(asymptoticPercent(-5, -1)).toBe(0)
    expect(asymptoticPercent(1, 5)).toBeLessThanOrEqual(PROGRESS_MAX_PERCENT)
    expect(Number.isFinite(asymptoticPercent(1, Number.NaN))).toBe(true)
    expect(Number.isFinite(asymptoticPercent(Number.NaN, 0))).toBe(true)
  })
})

describe('createElapsedTicker', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('start 后按秒自增，stop 后不再走', () => {
    const ticker = createElapsedTicker()
    ticker.start()
    expect(ticker.seconds.value).toBe(0)

    vi.advanceTimersByTime(3000)
    expect(ticker.seconds.value).toBe(3)

    ticker.stop()
    vi.advanceTimersByTime(5000)
    expect(ticker.seconds.value).toBe(3) // 停表后不能继续涨
  })

  it('重复 start 会归零并重置基准（不会叠加两个定时器）', () => {
    const ticker = createElapsedTicker()
    ticker.start()
    vi.advanceTimersByTime(4000)
    expect(ticker.seconds.value).toBe(4)

    ticker.start()
    expect(ticker.seconds.value).toBe(0)
    vi.advanceTimersByTime(1000)
    expect(ticker.seconds.value).toBe(1) // 若叠加了定时器会变成 2
  })

  it('未 start 就 stop 不报错', () => {
    const ticker = createElapsedTicker()
    expect(() => ticker.stop()).not.toThrow()
  })
})
