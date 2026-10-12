import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// 全局样式：设计 token 与自绘纹样（docs/VISUAL.md §5/§6）。
// 必须在使用组件前引入，否则新组件的 var(--paper) 等变量拿不到值。
import './styles/theme.css'
import './styles/patterns.css'

const app = createApp(App)

// Pinia 在校勘链路里承担跨页状态传递（首页提交 -> 校勘页渲染），必须在使用前装上
app.use(createPinia())
app.use(router)

app.mount('#app')
