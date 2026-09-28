<template>
  <div class="history-container">
    <h2>📚 校勘历史记录</h2>
    <table class="history-table">
      <thead>
        <tr>
          <th>文件名</th>
          <th>上传时间</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in historyList" :key="index">
          <td>{{ item.name }}</td>
          <td>{{ item.date }}</td>
          <td><span :class="['status', item.status]">{{ item.statusText }}</span></td>
          <td><button class="btn-view">查看报告</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref } from 'vue';
const historyList = ref([
  { name: '论语_学而篇.jpg', date: '2023-10-24 14:30', status: 'done', statusText: '已完成' },
  { name: '孟子_梁惠王上.pdf', date: '2023-10-23 09:15', status: 'processing', statusText: '处理中' },
  { name: '大学_章句.txt', date: '2023-10-22 16:45', status: 'done', statusText: '已完成' },
]);
</script>

<style scoped>
.history-container { padding: 40px; }
.history-table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #fff; }
.history-table th, .history-table td { padding: 15px; text-align: left; border-bottom: 1px solid #eee; }
.history-table th { background: #f4f1e8; color: #555; }
.status.done { color: #2e8b57; }
.status.processing { color: #d93025; }
.btn-view {
  background: transparent; border: 1px solid #b22222; color: #b22222;
  padding: 5px 15px; border-radius: 4px; cursor: pointer;
}
.btn-view:hover { background: #b22222; color: #fff; }
</style>