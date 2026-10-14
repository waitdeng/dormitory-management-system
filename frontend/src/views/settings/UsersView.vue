<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  ElMessage,
  type FormInstance,
  type FormRules,
} from 'element-plus'
import { createUser, listRoles, listUsers, setUserRoles, updateUser } from '@/api/users'
import { extractError } from '@/api/client'
import type { RoleOut, UserOut } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const rows = ref<UserOut[]>([])
const roles = ref<RoleOut[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  display_name: '',
  password: '',
  status: 'active',
  role_codes: [] as string[],
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '长度 3-64', trigger: 'blur' },
  ],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码至少 8 位', trigger: 'blur' },
  ],
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listUsers({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(extractError(error))
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingId.value = null
  form.username = ''
  form.display_name = ''
  form.password = ''
  form.status = 'active'
  form.role_codes = []
  dialogVisible.value = true
}

function openEdit(row: UserOut): void {
  editingId.value = row.id
  form.username = row.username
  form.display_name = row.display_name
  form.password = ''
  form.status = row.status
  form.role_codes = [...row.roles]
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (editingId.value == null) {
        await createUser({
          username: form.username,
          display_name: form.display_name,
          password: form.password,
          status: form.status,
          role_codes: form.role_codes,
        })
        ElMessage.success('账号已创建')
      } else {
        await updateUser(editingId.value, {
          display_name: form.display_name,
          status: form.status,
          ...(form.password ? { password: form.password } : {}),
        })
        await setUserRoles(editingId.value, form.role_codes)
        ElMessage.success('账号已更新')
      }
      dialogVisible.value = false
      await load()
    } catch (error) {
      ElMessage.error(extractError(error))
    }
  })
}

onMounted(async () => {
  await load()
  try {
    roles.value = await listRoles()
  } catch {
    roles.value = []
  }
})
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名 / 显示名称"
        clearable
        style="width: 240px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" :icon="'Search'" @click="load">查询</el-button>
      <div class="spacer" />
      <el-button
        v-if="auth.hasPermission('user:manage')"
        type="primary"
        :icon="'Plus'"
        @click="openCreate"
      >
        新建账号
      </el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="display_name" label="显示名称" min-width="120" />
      <el-table-column label="角色" min-width="160">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles" :key="r" size="small" class="role-tag">{{ r }}</el-tag>
          <span v-if="!row.roles?.length" class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" min-width="160">
        <template #default="{ row }">{{ row.last_login_at || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      layout="total, prev, pager, next"
      :total="total"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      @current-change="load"
    />
  </el-card>

  <el-dialog
    v-model="dialogVisible"
    :title="editingId == null ? '新建账号' : '编辑账号'"
    width="520px"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" :disabled="editingId != null" />
      </el-form-item>
      <el-form-item label="显示名称" prop="display_name">
        <el-input v-model="form.display_name" />
      </el-form-item>
      <el-form-item
        :label="editingId == null ? '密码' : '重置密码'"
        :prop="editingId == null ? 'password' : undefined"
      >
        <el-input
          v-model="form.password"
          type="password"
          show-password
          :placeholder="editingId == null ? '至少 8 位' : '留空则不修改'"
        />
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="form.status" active-value="active" inactive-value="disabled" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role_codes" multiple placeholder="选择角色" style="width: 100%">
          <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.spacer {
  flex: 1;
}

.role-tag {
  margin-right: 6px;
}

.muted {
  color: #c0c4cc;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
