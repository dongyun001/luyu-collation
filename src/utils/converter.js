// src/utils/converter.js
import * as OpenCC from 'opencc-js';

/**
 * 繁简转换函数
 * @param {string} text - 需要转换的文本
 * @param {string} mode - 'simplified' (转简体) | 'traditional' (转繁体)
 * @returns {Promise<string>} 转换后的文本
 */
export const convertText = async (text, mode) => {
  if (!text) return '';

  try {
    // 定义转换器配置
    // s2t: 简体转繁体 (Simplified to Traditional)
    // t2s: 繁体转简体 (Traditional to Simplified)
    const converterName = mode === 'traditional' ? 's2t' : 't2s';

    // 创建转换器实例
    const converter = OpenCC.Converter({ from: 'cn', to: mode === 'traditional' ? 'tw' : 'cn' });

    // 执行转换并返回结果
    return await converter(text);
  } catch (error) {
    console.error('繁简转换失败:', error);
    return text; // 出错时返回原文本，防止页面崩溃
  }
};