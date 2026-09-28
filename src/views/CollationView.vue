<template>
  <div class="workspace-container">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="tool-group">
        <span class="label">排版：</span>
        <button class="btn-toggle" :class="{ active: layoutMode === 'vertical' }" @click="layoutMode = 'vertical'">竖排</button>
        <button class="btn-toggle" :class="{ active: layoutMode === 'horizontal' }" @click="layoutMode = 'horizontal'">横排</button>
      </div>
      <div class="tool-group">
        <span class="label">字体：</span>
        <button class="btn-toggle" :class="{ active: charMode === 'simplified' }" @click="switchCharMode('simplified')">简体</button>
        <button class="btn-toggle" :class="{ active: charMode === 'traditional' }" @click="switchCharMode('traditional')">繁体</button>
      </div>
    </div>

    <!-- 核心双栏对照区 -->
    <div class="comparison-grid">
      <!-- 左侧：原文展示区 -->
      <div class="panel source-panel">
        <div class="panel-header">
          <div class="header-left">
            <span class="title-bar"></span>
            <span class="title-text">原文</span>
          </div>
          <span class="tag-ai">OCR识别文本</span>
        </div>

        <div v-if="isConverting" class="loading-placeholder">正在智能转换字体...</div>

        <!-- 文本内容区 (动态绑定 vertical/horizontal 类名) -->
        <div v-else class="text-content" :class="layoutMode">
          <p>
            <template v-for="(item, index) in displayData" :key="index">
              <span v-if="item.type === 'text'" class="plain-text">{{ item.content }}</span>
              <span v-else-if="item.type === 'error'" class="error-word" :title="item.tip">{{ item.content }}</span>
              <span v-else-if="item.type === 'note'" class="note-wrapper" :class="{ 'is-vertical': layoutMode === 'vertical' }">
                {{ item.content }}
                <!-- 气泡内容 -->
                <div class="custom-tooltip">
                  <div class="tooltip-title">📖 典故释义</div>
                  <div class="tooltip-body">{{ item.noteContent }}</div>
                </div>
              </span>
            </template>
          </p>
        </div>
      </div>

      <!-- 右侧：AI校勘结果区 -->
      <div class="panel result-panel">
        <div class="panel-header">
          <div class="header-left">
            <span class="title-bar"></span>
            <span class="title-text">AI校勘结果</span>
            <span class="tag-count">待处理 {{ pendingCount }} 处</span>
          </div>
          <div class="header-actions">
            <button class="btn-outline btn-success" @click="acceptAll">全部采纳</button>
            <button class="btn-outline btn-default" @click="rejectAll">一键还原</button>
          </div>
        </div>

        <div class="collation-list">
          <div v-for="item in processedCollationItems" :key="item.id" class="collation-card" :class="item.status">
            <div class="card-main">
              <div class="text-block original">

                <span class="content">{{ item.original }}</span>
              </div>
              <div class="arrow">➔</div>
              <div class="text-block suggested">

                <span class="content">{{ item.suggested }}</span>
              </div>
            </div>
            <div class="card-footer">
              <div class="reason-box">
                <span class="confidence" :style="{ color: getConfidenceColor(item.confidence) }">
                  置信度 {{ (item.confidence * 100).toFixed(0) }}%
                </span>
                <span class="reason-text">{{ item.reason }}</span>
              </div>
              <div class="action-btns">
                <button class="mini-btn ok" :disabled="item.status === 'accepted'" @click="accept(item)">采纳</button>
                <button class="mini-btn back" :disabled="item.status === 'rejected'" @click="reject(item)">还原</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部功能区 -->
    <div class="bottom-section">
      <div class="tab-header">
        <div class="tab-item" :class="{ active: activeTab === 'translation' }" @click="activeTab = 'translation'">文白对照</div>
        <div class="tab-item" :class="{ active: activeTab === 'timeline' }" @click="activeTab = 'timeline'">修改记录时间线</div>
        <div style="flex: 1"></div>
        <!-- 导出按钮：已添加颜色样式 -->
        <button class="btn-export" @click="exportReport">📥 导出校勘结果</button>
      </div>

      <div class="tab-content">
        <div v-if="activeTab === 'translation'" class="translation-view">
          <h4 class="section-title">白话译文</h4>
          <p class="translation-text">{{ processedTranslation }}</p>
        </div>
        <div v-if="activeTab === 'timeline'" class="timeline-view">
          <div v-if="processedHistory.length === 0" class="empty-tip">暂无修改记录</div>
          <div v-for="(record, index) in processedHistory" :key="index" class="timeline-item">
            <div class="time-badge">{{ record.time }}</div>
            <div class="record-body">
              <span class="user-tag">{{ record.user }}</span>
              <span class="action-text">{{ record.action }}</span>
              <span class="detail-box">“{{ record.oldVal }}” → “{{ record.newVal }}”</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <TranslatorWidget />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import OpenCC from 'opencc-js';
import TranslatorWidget from '@/components/TranslatorWidget.vue';
// --- 状态与数据 ---
const layoutMode = ref('vertical'); // 默认竖排
const charMode = ref('traditional'); // 默认繁体
const isConverting = ref(false);
const activeTab = ref('translation');

const converter = OpenCC.Converter({ from: 'cn', to: 'tw' });
const convert = (text) => charMode.value === 'simplified' ? text : converter(text);

const originalData = ref([
  { type: 'text', content: '子曰：' },
  { type: 'error', content: '日', tip: 'OCR误识：应为“曰”' },
  { type: 'text', content: '学而时习之，不亦' },
  { type: 'note', content: '说', noteContent: '通假字：同“悦”，指内心高兴、愉快。' },
  { type: 'text', content: '乎？有朋自远方来，不亦乐乎？人不知而不愠，不亦君子乎？' }
]);

const collationItems = ref([
  { id: 1, original: '日学而时习之', suggested: '学而时习之', confidence: 0.95, reason: '形近字误识，据《论语》通行本还原', status: 'pending' },
  { id: 2, original: '木交', suggested: '人不知而不愠', confidence: 0.88, reason: 'OCR 乱码，语义不通，还原文本', status: 'pending' },
  { id: 3, original: '不亦说乎', suggested: '不亦悦乎', confidence: 1.0, reason: '“说”通“悦”，建议保留原字并加注', status: 'pending' }
]);

const historyRecords = ref([
  { time: '10:23:45', user: 'AI助手', action: '自动校勘', oldVal: '日', newVal: '曰' },
]);
const translationText = ref('孔子说：“学习并时常温习，不是很愉快吗？有志同道合的人从远方来，不是很快乐吗？人家不了解我，我却不怨恨，不也是君子吗？”');

// --- 计算属性 ---
const displayData = computed(() => originalData.value.map(item => ({ ...item, content: convert(item.content), noteContent: item.noteContent ? convert(item.noteContent) : '' })));
const processedCollationItems = computed(() => collationItems.value.map(item => ({ ...item, original: convert(item.original), suggested: convert(item.suggested), reason: convert(item.reason) })));
const processedTranslation = computed(() => convert(translationText.value));
const processedHistory = computed(() => historyRecords.value.map(r => ({ ...r, oldVal: convert(r.oldVal), newVal: convert(r.newVal) })));
const pendingCount = computed(() => collationItems.value.filter(i => i.status === 'pending').length);

// --- 方法 ---
const switchCharMode = (mode) => { isConverting.value = true; charMode.value = mode; setTimeout(() => isConverting.value = false, 100); };
const accept = (item) => { item.status = 'accepted'; addHistory('采纳修改', item.original, item.suggested); };
const reject = (item) => { item.status = 'rejected'; addHistory('还原原文', item.suggested, item.original); };
const acceptAll = () => collationItems.value.forEach(i => { if(i.status !== 'accepted') accept(i); });
const rejectAll = () => collationItems.value.forEach(i => { if(i.status !== 'rejected') reject(i); });
const addHistory = (action, oldVal, newVal) => {
  const now = new Date();
  historyRecords.value.unshift({ time: `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`, user: '当前用户', action, oldVal, newVal });
};
const exportReport = () => {
  const reportContent = `校勘报告\n生成时间：${new Date().toLocaleString()}\n\n` + collationItems.value.map(i => `[${i.status}] ${i.original} -> ${i.suggested} (${i.reason})`).join('\n');
  const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = '古籍校勘报告.txt'; a.click(); URL.revokeObjectURL(url);
};
const getConfidenceColor = (score) => score >= 0.9 ? '#2e8b57' : '#daa520';
</script>


<style scoped>
/* ================= 全局布局 ================= */
.workspace-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f7f7f7;
}

.toolbar {
  padding: 10px 20px;
  background: #fff;
  border-bottom: 1px solid #eee;
  display: flex;
  gap: 20px;
  align-items: center;
  z-index: 20;
}

.btn-toggle {
  padding: 4px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-toggle.active {
  background: #8b1a1a;
  color: #fff;
  border-color: #8b1a1a;
}

.comparison-grid {
  display: flex;
  flex: 1;
  overflow: hidden; /* 防止外层出现滚动条 */
  gap: 1px;
  background: #e0e0e0;
}

.panel {
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 关键：让内部元素控制滚动 */
  position: relative;
}

.source-panel { flex: 1; }
.result-panel { flex: 1; min-width: 400px; }

.panel-header {
  padding: 15px 20px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  z-index: 10;
  flex-shrink: 0; /* 防止头部被压缩 */
}

.title-bar {
  width: 4px;
  height: 16px;
  background: #8b1a1a;
  display: inline-block;
  margin-right: 8px;
  vertical-align: middle;
}

/* ================= 原文区 (核心修改：滑动条逻辑) ================= */
.text-content {
  flex: 1;
  padding: 40px;
  font-family: "KaiTi", "STKaiti", serif;
  font-size: 24px;
  line-height: 2;
  position: relative;
  /* 基础滚动设置 */
  overflow: auto;
  height: 100%; /* 确保高度填满 */
}

/* --- 竖排模式 (Vertical) --- */
.text-content.vertical {
  writing-mode: vertical-rl; /* 文字从上到下，列从右到左 */
  text-orientation: upright;

  /* 关键：强制横向滚动 */
  overflow-x: auto;
  overflow-y: hidden;

  /* 关键：强制不换行，让内容向右无限延伸，从而出现横向滚动条 */
  white-space: normal;

  max-height: 100%;
  text-align: left; /* 配合 vertical-rl，让第一列靠右对齐 */
}
/* 确保内部段落也遵循高度限制 */
.text-content.vertical .main-text {
  height: 100%;
  margin: 0;
}
/* --- 横排模式 (Horizontal) --- */
.text-content.horizontal {
  writing-mode: horizontal-tb;

  /* 关键：开启竖向滚动 */
  overflow-y: auto;
  overflow-x: hidden;

  /* 允许自动换行 */
  white-space: normal;
}

/* 错误与注释样式 */
.error-word { color: #d9534f; border-bottom: 2px dashed #d9534f; cursor: help; }
.note-wrapper { position: relative; color: #1e90ff; border-bottom: 1px dashed #1e90ff; cursor: help; display: inline-block; }

/* 气泡通用样式 */
.custom-tooltip {
  display: none;
  position: absolute;
  z-index: 100;
  background: #fff;
  border: 1px solid #eee;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  padding: 10px;
  font-size: 14px;
  line-height: 1.5;
  white-space: normal;
  min-width: 100px;
  max-width: 300px;
}

.note-wrapper:hover .custom-tooltip { display: block; }

/* 竖排时气泡：文字竖排，位于左侧 */
.text-content.vertical .note-wrapper.is-vertical .custom-tooltip {
  right: 100%;
  top: 50%;
  transform: translateY(-50%);
  margin-right: 15px;
  writing-mode: vertical-rl;
  text-orientation: upright;
}

/* 横排时气泡：文字横排，位于下方 */
.text-content.horizontal .note-wrapper .custom-tooltip {
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 8px;
  writing-mode: horizontal-tb;
}
/* ================= 滚动条美化 (深色细条) ================= */
/* 针对 Webkit 内核浏览器 (Chrome, Edge, Safari) */
.text-content::-webkit-scrollbar {
  width: 6px;  /* 竖向滚动条宽度 */
  height: 6px; /* 横向滚动条高度 */
}

.text-content::-webkit-scrollbar-track {
  background: transparent;
}

.text-content::-webkit-scrollbar-thumb {
  background: #555; /* 深灰色滑块 */
  border-radius: 3px;
}

.text-content::-webkit-scrollbar-thumb:hover {
  background: #888;
}
/* ================= 校勘结果区 ================= */
.header-actions { display: flex; gap: 10px; }

.btn-outline {
  padding: 6px 16px;
  border-radius: 4px;
  border: 1px solid #ddd;
  cursor: pointer;
  background: #fff;
  transition: all 0.2s;
}

.btn-success { border-color: #2e8b57; color: #2e8b57; }
.btn-success:hover { background: #2e8b57; color: #fff; }

.btn-default { border-color: #999; color: #666; }
.btn-default:hover { background: #999; color: #fff; }

.collation-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.collation-card {
  border: 1px solid #e6e2d8;
  border-radius: 6px;
  padding: 15px;
  background: #fffcfc;
}

.collation-card.accepted {
  border-color: #b7d4b0;
  background: #f3f9f1;
  opacity: 0.8;
}

.card-main {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 12px;
  font-family: "KaiTi", serif;
  font-size: 20px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px dashed #eee;
  padding-top: 10px;
}

.confidence { font-size: 12px; font-weight: bold; color: #2e8b57; }
.reason-text { font-size: 13px; color: #666; display: block; margin-top: 4px; }

.mini-btn {
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid #ddd;
  background: #fff;
  cursor: pointer;
  margin-left: 8px;
  font-size: 12px;
}

.mini-btn.ok { color: #2e8b57; border-color: #2e8b57; }
.mini-btn.ok:hover { background: #2e8b57; color: #fff; }
.mini-btn.back { color: #666; }
.mini-btn.back:hover { background: #eee; }

/* ================= 底部功能区 ================= */
.bottom-section {
  height: 220px;
  background: #fff;
  border-top: 1px solid #eee;
  flex-shrink: 0;
}

.tab-header {
  display: flex;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}

.tab-item {
  padding: 12px 20px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-item.active {
  color: #8b1a1a;
  font-weight: bold;
  border-bottom-color: #8b1a1a;
  background: #fff;
}

.tab-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.btn-export {
  padding: 6px 15px;
  background: #fff;
  border: 1px solid #8b1a1a;
  color: #8b1a1a;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.btn-export:hover {
  background: #8b1a1a;
  color: #fff;
}

.timeline-item {
  display: flex;
  gap: 15px;
  margin-bottom: 12px;
  font-size: 13px;
  align-items: center;
  border-left: 2px solid #eee;
  padding-left: 15px;
}

.time-badge {
  color: #999;
  font-family: monospace;
  width: 70px;
}

.user-tag {
  color: #8b1a1a;
  font-weight: bold;
  margin-right: 5px;
}

.detail-box {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
  color: #555;
  margin-left: 5px;
}

.translation-text {
  line-height: 1.8;
  color: #444;
  font-size: 15px;
}
</style>