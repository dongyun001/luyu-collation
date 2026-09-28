<template>
  <div class="home-wrapper">
    <!-- 头部标语 -->
    <div class="hero-section">
      <h1 class="hero-title">让古籍数字化更简单</h1>
      <p class="hero-subtitle">基于大模型的古籍自动校勘、异文识别与文白对照系统</p>
    </div>

    <!-- 核心操作区 (重构部分) -->
    <div class="action-card-container">
      <div class="action-card">

        <!-- 顶部 Tab 切换 -->
        <div class="card-tabs">
          <div
              class="tab-item"
              :class="{ active: uploadMode === 'file' }"
              @click="uploadMode = 'file'"
          >
            📂 上传古籍
          </div>
          <div
              class="tab-item"
              :class="{ active: uploadMode === 'text' }"
              @click="uploadMode = 'text'"
          >
            📝 粘贴原文
          </div>
        </div>

        <!-- 内容区域 -->
        <div class="card-content">

          <!-- 模式 A：文件上传 -->
          <div v-if="uploadMode === 'file'" class="upload-area" @dragover.prevent @drop.prevent="handleDrop">
            <input type="file" ref="fileInput" @change="handleFileSelect" style="display: none" accept=".txt,.jpg,.png,.pdf" />

            <div class="icon-placeholder">📄</div>
            <p class="main-text">点击或拖拽上传古籍图片 / 文本文件</p>
            <p class="sub-text">支持 .jpg, .png, .txt, .pdf</p>

            <button class="btn-select" @click="$refs.fileInput.click()">选择文件</button>
            <div v-if="selectedFileName" class="file-selected-tip">已选择: {{ selectedFileName }}</div>
          </div>

          <!-- 模式 B：文本粘贴 -->
          <div v-else class="paste-area">
            <textarea
                v-model="pastedText"
                placeholder="请在此处粘贴古籍原文（支持繁体/简体）..."
                class="custom-textarea"
            ></textarea>
            <div class="char-count">{{ pastedText.length }} 字</div>
          </div>

        </div>

        <!-- 底部统一按钮 -->
        <div class="card-footer">
          <button class="btn-start" @click="startCollation">开始校勘</button>
        </div>

      </div>
    </div>

    <!-- 底部特性展示 (保持不变) -->
    <div class="features-row">
      <div class="feature-item">
        <h4>智能校勘</h4>
        <p>识别异文并标注差异</p>
      </div>
      <div class="feature-item">
        <h4>文白对照</h4>
        <p>原文与译文分层展示</p>
      </div>
      <div class="feature-item">
        <h4>注释参考</h4>
        <p>悬停查看字词释义</p>
      </div>
    </div>

    <div class="footer-note">AI辅助校勘 · 人机协同 · 可追溯修改</div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const uploadMode = ref('file'); // 'file' 或 'text'
const fileInput = ref(null);
const selectedFileName = ref('');
const pastedText = ref(''); // 存储粘贴的文本

// 处理文件选择
const handleFileSelect = (e) => {
  const file = e.target.files[0];
  if (file) {
    selectedFileName.value = file.name;
    console.log('文件已就绪:', file.name);
  }
};

// 处理拖拽
const handleDrop = (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    selectedFileName.value = file.name;
    console.log('文件拖入:', file.name);
  }
};

// 开始校勘逻辑
const startCollation = () => {
  if (uploadMode.value === 'file') {
    if (!selectedFileName.value) {
      alert('请先选择或拖拽一个文件！');
      return;
    }
    console.log('提交任务：文件校勘', selectedFileName.value);
    // TODO: 这里调用后端 API 上传文件
  } else {
    if (!pastedText.value.trim()) {
      alert('请先粘贴古籍原文！');
      return;
    }
    console.log('提交任务：文本校勘', pastedText.value.substring(0, 20) + '...');
    // TODO: 这里调用后端 API 发送文本
  }

  // 模拟跳转
  router.push('/collation');
};
</script>

<style scoped>
/* 保持原有的 Home 布局样式 */
.home-wrapper {
  display: flex; flex-direction: column; align-items: center; padding-top: 40px;
}
.hero-section { text-align: center; margin-bottom: 40px; }
.hero-title { font-size: 36px; color: #2b2b2b; margin-bottom: 10px; letter-spacing: 2px; }
.hero-subtitle { font-size: 16px; color: #666; }

/* --- 核心卡片样式重构 --- */
.action-card-container {
  width: 100%; max-width: 650px; margin-bottom: 50px;
}

.action-card {
  background: #fff;
  border: 1px solid #e6e2d8;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(139, 26, 26, 0.05);
  overflow: hidden; /* 防止圆角溢出 */
}

/* Tab 切换栏 */
.card-tabs {
  display: flex;
  border-bottom: 1px solid #eee;
  background: #fcfcfc;
}

.tab-item {
  flex: 1;
  text-align: center;
  padding: 15px 0;
  cursor: pointer;
  font-size: 16px;
  color: #666;
  transition: all 0.3s;
  border-bottom: 2px solid transparent;
}

.tab-item:hover { background: #f5f5f5; }

.tab-item.active {
  color: #8b1a1a; /* 朱红 */
  font-weight: bold;
  background: #fff;
  border-bottom-color: #8b1a1a;
}

/* 内容区域 */
.card-content { padding: 40px; min-height: 200px; display: flex; flex-direction: column; align-items: center; justify-content: center; }

/* 上传区域样式 */
.upload-area { text-align: center; width: 100%; border: 2px dashed #dcdcdc; border-radius: 6px; padding: 30px; transition: all 0.3s; cursor: pointer; }
.upload-area:hover { border-color: #8b1a1a; background: #fffcfc; }
.icon-placeholder { font-size: 40px; margin-bottom: 15px; opacity: 0.7; }
.main-text { font-size: 16px; color: #333; margin: 0 0 5px 0; }
.sub-text { font-size: 12px; color: #999; margin: 0 0 20px 0; }
.btn-select {
  background: transparent; border: 1px solid #8b1a1a; color: #8b1a1a;
  padding: 6px 20px; border-radius: 20px; cursor: pointer; transition: 0.3s;
}
.btn-select:hover { background: #8b1a1a; color: #fff; }
.file-selected-tip { margin-top: 15px; font-size: 13px; color: #2e8b57; }

/* 粘贴区域样式 */
.paste-area { width: 100%; position: relative; }
.custom-textarea {
  width: 100%; height: 180px;
  border: 1px solid #dcdcdc; border-radius: 4px;
  padding: 15px; font-family: 'KaiTi', serif; font-size: 16px;
  resize: none; outline: none; box-sizing: border-box;
  background: #fdfbf7; /* 淡淡的米色背景 */
}
.custom-textarea:focus { border-color: #8b1a1a; background: #fff; }
.char-count {
  position: absolute; bottom: 10px; right: 15px;
  font-size: 12px; color: #999; pointer-events: none;
}

/* 底部按钮 */
.card-footer { padding: 0 40px 30px 40px; text-align: center; }
.btn-start {
  background: #8b1a1a; color: #fff; border: none;
  padding: 12px 50px; font-size: 16px; border-radius: 25px;
  cursor: pointer; box-shadow: 0 4px 10px rgba(139, 26, 26, 0.3);
  transition: transform 0.2s;
}
.btn-start:hover { transform: translateY(-2px); background: #6d1414; }

/* 底部特性 (保持原样) */
.features-row { display: flex; gap: 20px; width: 100%; max-width: 900px; justify-content: space-between; }
.feature-item { flex: 1; background: #fff; padding: 20px; text-align: center; border: 1px solid #eee; border-radius: 6px; }
.feature-item h4 { margin: 0 0 8px 0; color: #333; }
.feature-item p { margin: 0; color: #888; font-size: 13px; }
.footer-note { margin-top: 40px; color: #aaa; font-size: 12px; }
</style>