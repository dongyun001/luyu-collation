<template>
  <div class="about-container">
    <div class="card">
      <h2>关于本项目</h2>
      <p>本项目致力于利用人工智能技术解决古籍数字化过程中的痛点。通过深度学习模型进行文字识别与校勘，结合大语言模型进行文白翻译，旨在为历史研究者提供一个高效、准确的辅助工具。</p>
      
      <h3>技术栈</h3>
      <ul>
        <li>前端：Vue 3 + Vite + Tailwind CSS</li>
        <li>后端：Python FastAPI + PyTorch</li>
        <li>算法：BERT-based Diff Algorithm</li>
      </ul>

      <h3>团队成员</h3>
      <p>项目负责人：XXX | 前端开发：XXX | 算法工程师：XXX</p>
    </div>
  </div>
</template>

<style scoped>
.about-container { display: flex; justify-content: center; padding-top: 60px; }
.card {
  background: #fff; padding: 40px; border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.05); max-width: 800px; width: 100%;
  border: 1px solid #eee; line-height: 1.8;
}
h2 { border-bottom: 2px solid #b22222; padding-bottom: 10px; display: inline-block; }
h3 { margin-top: 30px; color: #555; }
ul { padding-left: 20px; color: #666; }
</style>