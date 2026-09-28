<template>
  <div class="app-container">
    <!-- 顶部导航 -->
    <header class="main-header">
      <div class="logo-area">
        <div class="logo-icon">籍</div>
        <span class="logo-text">古籍智能校勘</span>
      </div>
      <nav class="nav-links">
        <router-link to="/">上传古籍</router-link>
        <router-link to="/collation">校勘工作台</router-link>
        <router-link to="/history">历史记录</router-link>
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
  background-color: #fdfbf7; /* 宣纸底色 */
  color: #333;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 顶部导航样式 */
.main-header {
  height: 70px;
  background: #fff;
  border-bottom: 1px solid #e6e2d8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 50px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.02);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  background: #8b1a1a; /* 朱红 */
  color: #fff;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: bold;
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
  margin-left: 40px;
  font-size: 16px;
  position: relative;
  padding-bottom: 5px;
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
}
</style>