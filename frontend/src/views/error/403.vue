<template>
  <div class="err-page">
    <div class="code">403</div>
    <h2>没有访问权限</h2>
    <p>当前账号无权访问该页面，请使用管理员账号登录，或返回首页。</p>
    <div class="actions">
      <el-button type="primary" @click="router.push('/dashboard')">返回首页</el-button>
      <el-button @click="router.push('/login')">切换账号</el-button>
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
  color: #e6a23c;
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

.actions {
  display: flex;
  gap: 10px;
}
</style>
