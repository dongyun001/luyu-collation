<template>
  <div class="about-container">
    <div class="card guji-paper guji-paper--fret">
      <h2>关于本项目</h2>
      <p>
        本项目面向古籍数字化整理中的校勘环节：用大语言模型给出<strong>可复核的校勘建议</strong>
        （讹字、衍文、脱文、通假、异文五类，每条附理由与置信度），由人工逐条采纳或还原，
        全程留痕，最后按文献学体例导出校勘记。主链路是"AI 建议 + 人工决策 + 全程留痕"，
        而不是让模型直接改写原文。
      </p>

      <h3>技术栈（与代码一致）</h3>
      <ul>
        <li>前端：Vue 3 + Vite + Pinia + vue-router；繁简转换用 opencc-js；图表用 ECharts（按需引入）</li>
        <li>后端：Python + FastAPI（薄 BFF：校验、Prompt 组装、限流、密钥托管）</li>
        <li>算法：大模型 API（OpenAI 兼容层，可切换供应商）+ 规则引擎（置信度修正、校勘记体例模板）</li>
      </ul>

      <h3>功能范围</h3>
      <ul>
        <li>F1–F5：粘贴/上传 → 智能校勘 → 人工决策 → 导出校勘记 → 文白对照</li>
        <li>F8：繁简与竖横排展示</li>
        <li>F9：多维度文献分析（体裁 / 年代 / 作者 / 学派 / 版本 / 语言 / 校勘七个维度，逐维给依据）</li>
        <li>F10–F11：可视化看板（类型分布、置信度分布、位置分布、校勘火山图、维度雷达）与知识图谱</li>
        <li>F12：条目筛选统计与本机项目列表</li>
      </ul>

      <h3>边界与诚实声明</h3>
      <ul>
        <li>后端<strong>不落盘</strong>用户文本，也<strong>不做服务端持久化</strong>；"项目列表"只存在本机浏览器里。</li>
        <li>多维度分析是 <strong>AI 辅助判断</strong>，仅供参考，请以专业工具书为准；依据不足的维度会标为存疑或未判断。</li>
        <li>模型输出一律先过 schema 校验才进界面，校验失败的条目会被拦截并计数。</li>
      </ul>

      <p class="footnote">
        参赛材料与交付物执行匿名自查：不出现学校名称、标识、指导教师与真实姓名。
      </p>
    </div>
  </div>
</template>

<style scoped>
.about-container {
  display: flex;
  justify-content: center;
  padding-top: 40px;
}
.card {
  background: #fff;
  padding: 40px;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
  max-width: 820px;
  width: 100%;
  border: 1px solid var(--line);
  line-height: 1.9;
}
h2 {
  border-bottom: 2px solid var(--cinnabar);
  padding-bottom: 10px;
  display: inline-block;
  color: var(--ink);
}
h3 {
  margin-top: 28px;
  color: var(--ink-soft);
  font-size: 15px;
}
ul {
  padding-left: 20px;
  color: var(--ink-muted);
  font-size: 13.5px;
}
p {
  font-size: 13.5px;
  color: var(--ink-soft);
}
.footnote {
  margin-top: 26px;
  font-size: 12px;
  color: var(--ink-faint);
  border-top: 1px dashed var(--line);
  padding-top: 12px;
}
</style>
