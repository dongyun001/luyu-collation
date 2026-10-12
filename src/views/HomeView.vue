<template>
  <div class="home-wrapper">
    <!-- 头部标语（竹简纹打底 + 上下的回纹细线，做出卷首的观感） -->
    <div class="hero-section guji-paper guji-paper--slips">
      <div class="hero-eyebrow">中国古典文献学 · 人机协同</div>
      <h1 class="hero-title">让古籍数字化更简单</h1>
      <p class="hero-subtitle">基于大模型的古籍自动校勘、异文识别与文白对照系统</p>
      <div class="hero-actions">
        <router-link class="hero-link" to="/analysis">查看分析看板 →</router-link>
        <router-link class="hero-link" to="/projects">项目列表 →</router-link>
      </div>
    </div>

    <!-- 核心操作区 -->
    <div class="action-card-container">
      <div class="action-card">

        <!-- 顶部 Tab 切换 -->
        <div class="card-tabs">
          <div
              class="tab-item"
              :class="{ active: uploadMode === 'file' }"
              @click="switchMode('file')"
          >
            📂 上传文本
          </div>
          <div
              class="tab-item"
              :class="{ active: uploadMode === 'text' }"
              @click="switchMode('text')"
          >
            📝 粘贴原文
          </div>
        </div>

        <!-- 内容区域 -->
        <div class="card-content">

          <!-- 模式 A：文件上传（当前仅 .txt 走真实链路） -->
          <div v-if="uploadMode === 'file'" class="upload-area" @dragover.prevent @drop.prevent="handleDrop">
            <input type="file" ref="fileInput" @change="handleFileSelect" style="display: none" accept=".txt,.md" />

            <div class="icon-placeholder">📄</div>
            <p class="main-text">点击或拖拽上传文本文件</p>
            <p class="sub-text">当前支持 .txt / .md；图片与 PDF 的 OCR 识别尚未启用，请改用粘贴原文</p>

            <button class="btn-select" @click="$refs.fileInput.click()">选择文件</button>
            <div v-if="selectedFileName" class="file-selected-tip">已选择: {{ selectedFileName }}</div>
          </div>

          <!-- 模式 B：文本粘贴（P0 主链路） -->
          <div v-else class="paste-area">
            <textarea
                v-model="pastedText"
                placeholder="请在此处粘贴古籍原文（支持繁体/简体）..."
                class="custom-textarea"
            ></textarea>
            <div class="char-count">{{ pastedText.length }} 字 / 上限 {{ maxTextLength }}</div>
          </div>

        </div>

        <!-- 提示：本地输入问题 or 后端调用失败 -->
        <div v-if="notice" class="notice-box" :class="notice.level">
          <div class="notice-title">{{ notice.message }}</div>
          <div v-if="notice.hint" class="notice-hint">{{ notice.hint }}</div>
        </div>

        <!-- 底部统一按钮 -->
        <div class="card-footer">
          <button class="btn-start" :disabled="isSubmitting" @click="startCollation">
            {{ isSubmitting ? '正在校勘…' : '开始校勘' }}
          </button>
        </div>

      </div>
    </div>

    <!-- 底部特性展示：新增能力也在这里如实列出，评委一眼看到产品全貌 -->
    <div class="features-row">
      <div class="feature-item">
        <h4>智能校勘</h4>
        <p>识别讹字、衍文、脱文、通假、异文五类，逐条给出理由与置信度</p>
      </div>
      <div class="feature-item">
        <h4>人机协同</h4>
        <p>逐条采纳/还原，全程留痕，可随时导出规范校勘记</p>
      </div>
      <div class="feature-item">
        <h4>文白对照</h4>
        <p>原文与白话译文分层展示，支持繁简与竖横排切换</p>
      </div>
      <router-link class="feature-item is-link" to="/analysis">
        <h4>多维度文献分析</h4>
        <p>体裁·年代·作者·学派·版本·语言·校勘七个文献学维度，逐维给依据</p>
      </router-link>
      <router-link class="feature-item is-link" to="/analysis">
        <h4>可视化看板</h4>
        <p>类型分布、置信度分布、位置分布、校勘火山图与维度雷达</p>
      </router-link>
      <router-link class="feature-item is-link" to="/analysis">
        <h4>知识图谱</h4>
        <p>人物·著作·学派·地名之间的关系网络，点选即看释义</p>
      </router-link>
    </div>

    <div class="footer-note">AI辅助校勘 · 人机协同 · 可追溯修改</div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { MAX_TEXT_LENGTH, useCollationStore } from '@/stores/collation'

const router = useRouter()
const store = useCollationStore()

const uploadMode = ref('text') // 'file' | 'text'；粘贴是 P0 主链路，默认停在这里
const fileInput = ref(null)
const selectedFileName = ref('')
const selectedFile = ref(null)
const pastedText = ref('')
/** 本地层面的问题（选错格式等），与后端返回的 error 分开展示 */
const localNotice = ref(null)

const maxTextLength = MAX_TEXT_LENGTH
const isSubmitting = computed(() => store.isLoading)

const notice = computed(() => {
  if (localNotice.value) return localNotice.value
  if (store.error) {
    return {
      level: 'error',
      message: store.error.message || '校勘失败',
      hint: store.error.hint || '',
    }
  }
  return null
})

function switchMode(mode) {
  uploadMode.value = mode
  localNotice.value = null
}

function resetNotices() {
  localNotice.value = null
  store.clearError()
}

function acceptFile(file) {
  selectedFile.value = file
  selectedFileName.value = file.name
  const isPlainText = /\.(txt|md)$/i.test(file.name) || file.type === 'text/plain'
  if (!isPlainText) {
    selectedFile.value = null
    localNotice.value = {
      level: 'warn',
      message: `暂不支持「${file.name}」的格式`,
      hint: '图片与 PDF 的文字识别（OCR）尚未接入，请改用「粘贴原文」，或上传 .txt 文件。',
    }
    return
  }
  localNotice.value = null
}

const handleFileSelect = (event) => {
  const file = event.target.files?.[0]
  if (file) acceptFile(file)
}

const handleDrop = (event) => {
  const file = event.dataTransfer?.files?.[0]
  if (file) acceptFile(file)
}

function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(new Error('文件读取失败，请重试或改用粘贴原文'))
    reader.readAsText(file, 'utf-8')
  })
}

const startCollation = async () => {
  resetNotices()

  let text = ''
  if (uploadMode.value === 'file') {
    if (!selectedFile.value) {
      localNotice.value = {
        level: 'warn',
        message: '请先选择一个 .txt 文本文件',
        hint: '也可以切到「粘贴原文」直接贴入正文。',
      }
      return
    }
    try {
      text = await readTextFile(selectedFile.value)
    } catch (error) {
      localNotice.value = { level: 'error', message: error.message, hint: '' }
      return
    }
  } else {
    text = pastedText.value
  }

  if (!text.trim()) {
    localNotice.value = { level: 'warn', message: '请先粘贴古籍原文', hint: '' }
    return
  }
  if (text.length > maxTextLength) {
    localNotice.value = {
      level: 'error',
      message: `文本 ${text.length} 字，超过单次上限 ${maxTextLength} 字`,
      hint: '请分段提交。',
    }
    return
  }

  // 真实调用 POST /api/v1/collate（长文本会按句读分段、并发提交）。
  // 这里**不 await 再跳转**：分段校勘是个持续几十秒到数分钟的过程，
  // 结果是逐段到货的，必须让用户在校勘台上看着它一段段出来，
  // 而不是停在首页干等全部算完（那样渐进呈现就白做了）。
  // submitText 内部已捕获所有异常并写入 store.error，故不会抛出未处理的 rejection。
  store.submitText(text, { produceTranslation: true })
  router.push('/collation')
}
</script>

<style scoped>
.home-wrapper {
  display: flex; flex-direction: column; align-items: center; padding-top: 28px;
}

/* 卷首：竹简纹打底，上下各一道回纹细线 */
.hero-section {
  text-align: center;
  margin-bottom: 36px;
  padding: 26px 44px 22px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  position: relative;
}
.hero-eyebrow {
  font-size: 12px; letter-spacing: 3px; color: var(--cinnabar);
  margin-bottom: 10px; opacity: 0.85;
}
.hero-title { font-size: 36px; color: var(--ink); margin: 0 0 10px; letter-spacing: 2px; }
.hero-subtitle { font-size: 16px; color: #666; margin: 0; }
.hero-actions { margin-top: 16px; display: flex; gap: 20px; justify-content: center; }
.hero-link {
  font-size: 13px; color: var(--cinnabar); text-decoration: none;
  border-bottom: 1px dashed rgba(139, 26, 26, 0.5); padding-bottom: 2px;
}
.hero-link:hover { border-bottom-style: solid; }

.action-card-container {
  width: 100%; max-width: 650px; margin-bottom: 40px;
}

.action-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(139, 26, 26, 0.05);
  overflow: hidden;
}

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
  color: #8b1a1a;
  font-weight: bold;
  background: #fff;
  border-bottom-color: #8b1a1a;
}

.card-content { padding: 40px; min-height: 200px; display: flex; flex-direction: column; align-items: center; justify-content: center; }

.upload-area { text-align: center; width: 100%; border: 2px dashed #dcdcdc; border-radius: 6px; padding: 30px; transition: all 0.3s; cursor: pointer; }
.upload-area:hover { border-color: #8b1a1a; background: #fffcfc; }
.icon-placeholder { font-size: 40px; margin-bottom: 15px; opacity: 0.7; }
.main-text { font-size: 16px; color: #333; margin: 0 0 5px 0; }
.sub-text { font-size: 12px; color: #999; margin: 0 0 20px 0; line-height: 1.6; }
.btn-select {
  background: transparent; border: 1px solid #8b1a1a; color: #8b1a1a;
  padding: 6px 20px; border-radius: 20px; cursor: pointer; transition: 0.3s;
}
.btn-select:hover { background: #8b1a1a; color: #fff; }
.file-selected-tip { margin-top: 15px; font-size: 13px; color: #2e8b57; }

.paste-area { width: 100%; position: relative; }
.custom-textarea {
  width: 100%; height: 180px;
  border: 1px solid #dcdcdc; border-radius: 4px;
  padding: 15px; font-family: 'KaiTi', serif; font-size: 16px;
  resize: none; outline: none; box-sizing: border-box;
  background: #fdfbf7;
}
.custom-textarea:focus { border-color: #8b1a1a; background: #fff; }
.char-count {
  position: absolute; bottom: 10px; right: 15px;
  font-size: 12px; color: #999; pointer-events: none;
}

/* 提示区：本地输入问题 / 后端调用失败 */
.notice-box {
  margin: 0 40px 16px 40px;
  padding: 12px 14px;
  border-radius: 6px;
  border-left: 3px solid #daa520;
  background: #fffbf0;
  text-align: left;
}
.notice-box.error { border-left-color: #c0392b; background: #fdf3f2; }
.notice-title { font-size: 14px; color: #333; line-height: 1.6; }
.notice-hint { font-size: 13px; color: #666; margin-top: 6px; line-height: 1.6; }

.card-footer { padding: 0 40px 30px 40px; text-align: center; }
.btn-start {
  background: #8b1a1a; color: #fff; border: none;
  padding: 12px 50px; font-size: 16px; border-radius: 25px;
  cursor: pointer; box-shadow: 0 4px 10px rgba(139, 26, 26, 0.3);
  transition: background 0.2s, box-shadow 0.2s;
}
.btn-start:hover:not(:disabled) { background: #6d1414; box-shadow: 0 6px 16px rgba(139, 26, 26, 0.38); }
.btn-start:disabled { background: #b98a8a; cursor: progress; box-shadow: none; }

/* 特性卡：三列两行；可点的那三张给描边与箭头感 */
.features-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  width: 100%;
  max-width: 1000px;
}
.feature-item {
  background: #fff;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  text-decoration: none;
  color: inherit;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.feature-item h4 { margin: 0 0 8px 0; color: var(--ink); font-size: 15px; }
.feature-item p { margin: 0; color: var(--ink-muted); font-size: 12.5px; line-height: 1.7; }
.feature-item.is-link { cursor: pointer; }
.feature-item.is-link:hover {
  border-color: var(--cinnabar);
  box-shadow: 0 6px 18px rgba(139, 26, 26, 0.09);
}
.feature-item.is-link h4::after { content: ' →'; color: var(--cinnabar); }

.footer-note { margin: 32px 0 20px; color: #aaa; font-size: 12px; }

@media (max-width: 900px) {
  .features-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
