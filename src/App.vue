<template>
  <div class="app-container">
    <!-- 纸纹层：固定在底层，只做"纸感"，不参与交互（样式见 src/styles/patterns.css） -->
    <div class="paper-layer" aria-hidden="true"></div>

    <!-- 顶部导航 -->
    <header class="main-header">
      <div class="logo-area">
        <!-- 自绘印章：不用任何外部图片，避免版权与匿名红线问题 -->
        <svg class="logo-seal" viewBox="0 0 40 40" role="img" aria-label="古籍智能校勘">
          <rect x="1.5" y="1.5" width="37" height="37" rx="5" fill="#8b1a1a" />
          <rect
            x="5.5"
            y="5.5"
            width="29"
            height="29"
            rx="3"
            fill="none"
            stroke="#ffffff"
            stroke-width="1.1"
            opacity="0.8"
          />
          <text
            x="20"
            y="27.5"
            text-anchor="middle"
            font-size="20"
            font-family="'Noto Serif SC', 'KaiTi', serif"
            fill="#ffffff"
          >
            籍
          </text>
        </svg>
        <span class="logo-text">古籍智能校勘</span>
      </div>
      <nav class="nav-links">
        <router-link to="/">上传古籍</router-link>
        <router-link to="/collation">校勘工作台</router-link>
        <router-link to="/analysis">分析看板</router-link>
        <router-link to="/compare">版本对勘</router-link>
        <router-link to="/projects">项目列表</router-link>
        <router-link to="/about">关于项目</router-link>
      </nav>
    </header>

    <!-- 页面内容 -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
// 无需逻辑
</script>

<style>
/* 全局重置与字体 */
body {
  margin: 0;
  font-family: 'Noto Serif SC', 'SimSun', serif; /* 宋体 */
  background-color: var(--paper); /* 宣纸底色 */
  color: #333;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

/* 纸纹层：整页的云纹底，固定在视口，深浅由 token 统一控制（见 styles/patterns.css :root） */
.paper-layer {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: var(--pattern-cloud, none);
  background-size: 96px 48px;
  opacity: var(--pattern-opacity-page, 0.06);
}

@media print {
  .paper-layer {
    display: none;
  }
}

/* 顶部导航样式 */
.main-header {
  height: 70px;
  background: rgba(252, 248, 238, 0.94);
  backdrop-filter: blur(2px);
  border-bottom: 1px solid #e6e2d8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 50px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
  position: relative;
  z-index: 20;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-seal {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  filter: drop-shadow(0 1px 2px rgba(139, 26, 26, 0.25));
}

.logo-text {
  font-size: 20px;
  font-weight: bold;
  color: #2b2b2b;
  letter-spacing: 1px;
}

.nav-links a {
  text-decoration: none;
  color: #555;
  margin-left: 28px;
  font-size: 15px;
  position: relative;
  padding-bottom: 5px;
  transition: color 0.2s;
}

.nav-links a:hover {
  color: #8b1a1a;
}

.nav-links a.router-link-active {
  color: #8b1a1a;
  font-weight: bold;
}

.nav-links a.router-link-active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: #8b1a1a;
}

.main-content {
  flex: 1;
  padding: 40px 50px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  /* 必须显式抬到纸纹层之上：纸纹层是 position:fixed，不这样做它会盖住正文文字 */
  position: relative;
  z-index: 1;
}
</style>
