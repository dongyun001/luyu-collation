<template>
  <div class="guji-upload-box" @dragover.prevent @drop.prevent="handleDrop">
    <input
        type="file"
        ref="fileInput"
        @change="handleFileChange"
        accept=".txt,.jpg,.jpeg,.png"
        style="display: none"
    />

    <div class="upload-content" @click="$refs.fileInput.click()">
      <div class="icon-area">📂</div>
      <p class="main-text">点击或拖拽上传古籍</p>
      <p class="sub-text">支持 JPG/PNG 图片或 TXT 文本</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <span class="ink-spinner"></span>
      <p>正在识别文字...</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const emit = defineEmits(['upload-success']);
const loading = ref(false);

// 处理文件选择
const handleFileChange = (event) => {
  const file = event.target.files[0];
  if (file) processFile(file);
};

// 处理拖拽
const handleDrop = (event) => {
  const file = event.dataTransfer.files[0];
  if (file) processFile(file);
};

// 模拟处理逻辑（后续替换为真实API）
const processFile = (file) => {
  loading.value = true;

  // 模拟延迟，实际这里调用后端接口
  setTimeout(() => {
    loading.value = false;
    console.log(`成功上传文件: ${file.name}`);
    // 通知父组件上传成功
    emit('upload-success', { name: file.name, type: file.type });
  }, 1500);
};
</script>

<style scoped>
.guji-upload-box {
  border: 2px dashed #d1c7b7;
  border-radius: 8px;
  background: #fdfbf7;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  position: relative;
}
.guji-upload-box:hover {
  border-color: #b22222;
  background: #fff;
}
.icon-area { font-size: 40px; margin-bottom: 10px; opacity: 0.6; }
.main-text { font-size: 18px; color: #333; margin: 0; font-weight: bold; }
.sub-text { font-size: 12px; color: #888; margin-top: 5px; }

/* 加载遮罩 */
.loading-overlay {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(253, 251, 247, 0.9);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border-radius: 8px;
}
.ink-spinner {
  width: 30px; height: 30px; border: 3px solid #d1c7b7;
  border-top-color: #b22222; border-radius: 50%;
  animation: spin 1s linear infinite; margin-bottom: 10px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>