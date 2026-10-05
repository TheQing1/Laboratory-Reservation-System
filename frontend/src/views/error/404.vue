<template>
  <div class="err-page">
    <div class="code">404</div>
    <h2>页面不存在</h2>
    <p>你访问的页面已被移除或地址有误。</p>
    <div class="actions">
      <el-button type="primary" @click="router.push('/dashboard')">返回首页</el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<style scoped>
.err-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: #f7f9fc;
  text-align: center;
  padding: 20px;
}

.code {
  font-size: 88px;
  font-weight: 800;
  color: #409eff;
  line-height: 1;
}

h2 {
  margin: 10px 0 4px;
  color: #1f2d3d;
}

p {
  color: #909399;
  font-size: 13px;
  margin: 0 0 18px;
}
</style>
