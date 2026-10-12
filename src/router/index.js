import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/collation',
      name: 'collation',
      // 路由懒加载
      component: () => import('../views/CollationView.vue')
    },
    {
      path: '/analysis',
      name: 'analysis',
      // 懒加载：ECharts 只在这个 chunk 里，不进首屏包（docs/VISUAL.md §1）
      component: () => import('../views/AnalysisView.vue')
    },
    {
      path: '/projects',
      name: 'projects',
      // 本机项目列表（F12）：取代原先只有"本次会话"一行的 HistoryView
      component: () => import('../views/ProjectsView.vue')
    },
    {
      // 旧入口保留为重定向，避免收藏/文档里的 /history 变成空白页
      path: '/history',
      redirect: { name: 'projects' }
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('../views/AboutView.vue')
    }
  ]
})

export default router