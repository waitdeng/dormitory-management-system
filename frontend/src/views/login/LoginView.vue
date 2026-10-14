<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { extractError } from '@/api/client'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const loading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await auth.login({ username: form.username, password: form.password })
      ElMessage.success('登录成功')
      const redirect = (route.query.redirect as string) || '/dashboard'
      router.push(redirect)
    } catch (error) {
      ElMessage.error(extractError(error))
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <el-icon :size="28" color="#409eff"><OfficeBuilding /></el-icon>
        <div>
          <h1>公司宿舍入住管理系统</h1>
          <p>Dormitory Management System · V1.0</p>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @keyup.enter="onSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="'User'"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="'Lock'"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="onSubmit">
          登 录
        </el-button>
      </el-form>

      <div class="login-footer">仅限公司内部行政 / 人事管理人员使用</div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 20% 20%, rgba(64, 158, 255, 0.18), transparent 45%),
    radial-gradient(circle at 80% 80%, rgba(103, 194, 58, 0.12), transparent 40%),
    #f0f2f5;
}

.login-card {
  width: 420px;
  background: #fff;
  border-radius: 12px;
  padding: 36px 36px 24px;
  box-shadow: 0 12px 40px rgba(31, 45, 61, 0.12);
}

.login-brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 28px;
}

.login-brand h1 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.login-brand p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
}

.login-footer {
  margin-top: 20px;
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
