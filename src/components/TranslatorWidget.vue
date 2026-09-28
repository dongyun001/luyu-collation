<template>
  <div>
    <!-- 1. 悬浮开关球 -->
    <div
      class="floating-ball"
      :class="{ active: isTranslateMode }"
      @click="toggleMode"
      title="点击开启古文翻译模式"
    >
      <span v-if="!isTranslateMode">译</span>
      <span v-else>✕</span>
    </div>

    <!-- 2. 翻译结果弹窗 (跟随鼠标) -->
    <div
      v-if="showResult"
      class="translation-popover"
      :style="{ left: popoverPos.x + 'px', top: popoverPos.y + 'px' }"
    >
      <div class="popover-header">
        <span class="title">📖 智能释义</span>
        <span class="close-btn" @click="closePopover">×</span>
      </div>
      <div class="popover-body">
        <div class="original-text">原文：{{ selectedText }}</div>
        <div class="loading" v-if="isLoading">正在查阅典籍...</div>
        <div class="translated-text" v-else>
          {{ translationResult || '暂无相关释义' }}
        </div>
      </div>
      <!-- 小三角箭头 -->
      <div class="arrow"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

// --- 状态定义 ---
const isTranslateMode = ref(false); // 是否开启翻译模式
const showResult = ref(false);      // 是否显示结果弹窗
const selectedText = ref('');       // 选中的文本
const translationResult = ref('');  // 翻译结果
const isLoading = ref(false);       // 加载状态
const popoverPos = ref({ x: 0, y: 0 }); // 弹窗位置

// --- 长按逻辑变量 ---
let pressTimer = null;
const LONG_PRESS_DURATION = 600; // 长按阈值：600毫秒

// --- 方法 ---

// 切换模式
const toggleMode = () => {
  isTranslateMode.value = !isTranslateMode.value;
  if (!isTranslateMode.value) {
    closePopover();
  }
};

// 关闭弹窗
const closePopover = () => {
  showResult.value = false;
  selectedText.value = '';
};

// 模拟翻译 API (实际开发请替换为真实接口)
const fetchTranslation = async (text) => {
  isLoading.value = true;
  // 模拟网络延迟
  await new Promise(resolve => setTimeout(resolve, 800));
  
  // 简单的模拟字典
  const mockDict = {
    '子曰': '孔子说。',
    '学而时习之': '学习了知识然后按时温习它。',
    '不亦说乎': '不也是很高兴的吗？（“说”通“悦”）',
    '有朋自远方来': '有志同道合的朋友从远方来。',
    '君子': '指道德修养高尚的人。'
  };
  
  translationResult.value = mockDict[text] || `【模拟翻译】这是对“${text}”的古文解释。在实际系统中，这里会调用大模型或字典API返回详细注释。`;
  isLoading.value = false;
};

// --- 事件监听逻辑 ---

const handleMouseDown = (e) => {
  if (!isTranslateMode.value) return;
  
  // 如果点击的是弹窗内部，不触发翻译
  if (e.target.closest('.translation-popover') || e.target.closest('.floating-ball')) return;

  // 记录按下位置，作为弹窗显示的基准点
  const startX = e.clientX;
  const startY = e.clientY;

  // 开始计时
  pressTimer = setTimeout(() => {
    // 1. 获取选中文本
    const selection = window.getSelection();
    const text = selection.toString().trim();
    
    if (text) {
      selectedText.value = text;
      // 2. 设置弹窗位置 (稍微偏移一点，避免挡住鼠标)
      popoverPos.value = { x: startX + 15, y: startY + 15 };
      // 3. 显示弹窗并开始加载
      showResult.value = true;
      translationResult.value = ''; // 清空旧结果
      fetchTranslation(text);
      
      // 防止触发浏览器的右键菜单或默认选择行为（可选）
      // e.preventDefault(); 
    }
  }, LONG_PRESS_DURATION);
};

const handleMouseUp = () => {
  if (pressTimer) {
    clearTimeout(pressTimer);
    pressTimer = null;
  }
};

// 挂载和卸载监听器
onMounted(() => {
  document.addEventListener('mousedown', handleMouseDown);
  document.addEventListener('mouseup', handleMouseUp);
});

onUnmounted(() => {
  document.removeEventListener('mousedown', handleMouseDown);
  document.removeEventListener('mouseup', handleMouseUp);
});
</script>

<style scoped>
/* 悬浮球样式 */
.floating-ball {
  position: fixed;
  bottom: 240px; /* 避开底部 Tab 栏 */
  right: 30px;
  width: 50px;
  height: 50px;
  background: #8b1a1a; /* 朱砂红 */
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(139, 26, 26, 0.4);
  cursor: pointer;
  z-index: 9999;
  transition: all 0.3s ease;
  user-select: none;
}

.floating-ball:hover {
  transform: scale(1.1);
}

/* 激活状态：变色提示 */
.floating-ball.active {
  background: #d9534f;
  box-shadow: 0 0 0 4px rgba(217, 83, 79, 0.2);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(217, 83, 79, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(217, 83, 79, 0); }
  100% { box-shadow: 0 0 0 0 rgba(217, 83, 79, 0); }
}

/* 翻译弹窗样式 */
.translation-popover {
  position: fixed;
  width: 280px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  z-index: 10000;
  font-family: "KaiTi", serif;
  overflow: hidden;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

.popover-header {
  background: #f9f9f9;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: #666;
}

.close-btn {
  cursor: pointer;
  font-size: 18px;
  color: #999;
}
.close-btn:hover { color: #333; }

.popover-body {
  padding: 12px;
  font-size: 15px;
  line-height: 1.6;
  color: #333;
}

.original-text {
  font-weight: bold;
  color: #8b1a1a;
  margin-bottom: 8px;
  border-bottom: 1px dashed #eee;
  padding-bottom: 4px;
}

.loading {
  color: #999;
  font-style: italic;
}

.translated-text {
  color: #444;
}

/* 小箭头 */
.arrow {
  position: absolute;
  top: -6px;
  left: 20px;
  width: 10px;
  height: 10px;
  background: #fff;
  border-left: 1px solid #e0e0e0;
  border-top: 1px solid #e0e0e0;
  transform: rotate(45deg);
}
</style>