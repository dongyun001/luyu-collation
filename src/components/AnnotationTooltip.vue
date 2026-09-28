<template>
  <Teleport to="body">
    <transition name="fade">
      <div
          v-if="visible"
          class="annotation-popup"
          :style="{ top: y + 'px', left: x + 'px' }"
          @mouseenter="handlePopupEnter"
          @mouseleave="handlePopupLeave"
      >
        <div class="popup-header">📖 典故/释义</div>
        <div class="popup-body">{{ content }}</div>

        <!-- 纯 CSS 绘制的小箭头 -->
        <div class="popup-arrow"></div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  visible: Boolean,
  content: String,
  x: Number,
  y: Number
});

const emit = defineEmits(['update:visible']);

// 内部状态，用于处理延迟关闭
let closeTimer = null;

// 当鼠标进入弹窗时，清除关闭定时器（保持显示）
const handlePopupEnter = () => {
  if (closeTimer) clearTimeout(closeTimer);
};

// 当鼠标离开弹窗时，通知父组件关闭
const handlePopupLeave = () => {
  emit('update:visible', false);
};

// 监听父组件传来的 visible 变化
watch(() => props.visible, (newVal) => {
  if (!newVal && closeTimer) clearTimeout(closeTimer);
});

// 暴露一个方法给父组件调用，用于“取消关闭”
defineExpose({
  cancelClose: () => {
    if (closeTimer) clearTimeout(closeTimer);
  },
  triggerClose: (delay = 200) => {
    closeTimer = setTimeout(() => {
      emit('update:visible', false);
    }, delay);
  }
});
</script>

<style scoped>
.annotation-popup {
  position: fixed;
  z-index: 9999;
  background: #fffdf5; /* 米色背景 */
  border: 1px solid #dcbfbf; /* 淡红边框 */
  padding: 15px;
  border-radius: 4px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
  width: 240px;
  font-family: 'Noto Serif SC', serif;
  /* 关键3：防止内容过多时溢出 */
  white-space: nowrap;
  pointer-events: none; /* 防止气泡挡住鼠标导致闪烁 */
}

.popup-header {
  font-size: 13px;
  color: #8b1a1a; /* 朱红标题 */
  border-bottom: 1px dashed #e6e2d8;
  margin-bottom: 8px;
  padding-bottom: 6px;
  font-weight: bold;
  display: flex;
  align-items: center;
  gap: 5px;
}

.popup-body {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}

/* 小箭头指向左上方 */
.popup-arrow {
  position: absolute;
  /* 默认横排模式：箭头在顶部，指向上方 */
  top: -6px;
  left: 20px;
  width: 10px;
  height: 10px;
  background: #fffdf5;
  border-left: 1px solid #dcbfbf;
  border-top: 1px solid #dcbfbf;
  transform: rotate(45deg);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>