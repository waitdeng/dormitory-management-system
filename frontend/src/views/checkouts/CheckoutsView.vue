<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { extractError } from '@/api/client'
import {
  cancelCheckout,
  completeCheckout,
  createCheckout,
  listCheckouts,
  recordCheckoutInspection,
} from '@/api/accommodations'
import { listEmployees } from '@/api/employees'
import type { CheckoutRecordOut, EmployeeOut } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const keyword = ref('')
const rows = ref<CheckoutRecordOut[]>([])

const createVisible = ref(false)
const formRef = ref<FormInstance>()
const employees = ref<EmployeeOut[]>([])
const form = reactive({
  employee_id: undefined as number | undefined,
  checkout_type: 'normal',
  reason: '',
  expected_checkout_date: '',
})

const rules: FormRules = {
  employee_id: [{ required: true, message: '请选择员工', trigger: 'change' }],
}

const inspectVisible = ref(false)
const inspectId = ref<number | null>(null)
const inspectForm = reactive({
  key_returned: false,
  access_card_returned: false,
  belongings_cleared: false,
  room_inspected: false,
  inspection_notes: '',
})

const statusLabel: Record<string, string> = {
  pending: '待检查',
  inspection: '检查中',
  completed: '已完成',
  cancelled: '已取消',
}

const typeLabel: Record<string, string> = {
  normal: '正常退宿',
  offboarding: '离职退宿',
  other: '其他',
}

function canInspect(row: CheckoutRecordOut): boolean {
  return ['pending', 'inspection'].includes(row.status) && auth.hasPermission('checkout:inspect')
}
function canComplete(row: CheckoutRecordOut): boolean {
  return ['pending', 'inspection'].includes(row.status) && auth.hasPermission('checkout:complete')
}
function canCancel(row: CheckoutRecordOut): boolean {
  return ['pending', 'inspection'].includes(row.status) && auth.hasPermission('checkout:complete')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listCheckouts({
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value || undefined,
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
  form.employee_id = undefined
  form.checkout_type = 'normal'
  form.reason = ''
  form.expected_checkout_date = ''
  createVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid || !form.employee_id) return
    try {
      await createCheckout({
        employee_id: form.employee_id,
        checkout_type: form.checkout_type,
        reason: form.reason || null,
        expected_checkout_date: form.expected_checkout_date || null,
      })
      ElMessage.success('退宿申请已创建')
      createVisible.value = false
      await load()
    } catch (error) {
      ElMessage.error(extractError(error))
    }
  })
}

function openInspect(row: CheckoutRecordOut): void {
  inspectId.value = row.id
  inspectForm.key_returned = row.key_returned
  inspectForm.access_card_returned = row.access_card_returned
  inspectForm.belongings_cleared = row.belongings_cleared
  inspectForm.room_inspected = row.room_inspected
  inspectForm.inspection_notes = row.inspection_notes || ''
  inspectVisible.value = true
}

async function onInspect(): Promise<void> {
  if (!inspectId.value) return
  try {
    await recordCheckoutInspection(inspectId.value, { ...inspectForm })
    ElMessage.success('检查信息已保存')
    inspectVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(extractError(error))
  }
}

async function onComplete(row: CheckoutRecordOut): Promise<void> {
  try {
    await completeCheckout(row.id)
    ElMessage.success('退宿已完成，床位已释放')
    await load()
  } catch (error) {
    ElMessage.error(extractError(error))
  }
}

async function onCancel(row: CheckoutRecordOut): Promise<void> {
  try {
    await cancelCheckout(row.id, '管理员取消')
    ElMessage.success('已取消')
    await load()
  } catch (error) {
    ElMessage.error(extractError(error))
  }
}

onMounted(async () => {
  await load()
  try {
    const data = await listEmployees({ page: 1, page_size: 100 })
    employees.value = data.items
  } catch {
    employees.value = []
  }
})
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="statusFilter" clearable placeholder="状态" style="width: 140px" @change="load">
        <el-option v-for="(label, key) in statusLabel" :key="key" :label="label" :value="key" />
      </el-select>
      <el-input
        v-model="keyword"
        placeholder="退宿单号 / 工号 / 姓名"
        clearable
        style="width: 220px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button v-if="auth.hasPermission('checkout:create')" type="success" @click="openCreate">
        新建退宿
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="checkout_no" label="退宿单号" min-width="160" />
      <el-table-column label="员工" min-width="130">
        <template #default="{ row }">
          {{ row.employee_name || row.employee_id }}
          <span class="muted">{{ row.employee_no }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          {{ typeLabel[row.checkout_type] || row.checkout_type }}
        </template>
      </el-table-column>
      <el-table-column label="床位" min-width="130">
        <template #default="{ row }">
          <span v-if="row.accommodation">
            {{ row.accommodation.building_name }}/{{ row.accommodation.room_no }}/{{ row.accommodation.bed_no }}
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="检查" width="160">
        <template #default="{ row }">
          <el-tag v-if="row.room_inspected" type="success" size="small">已检查</el-tag>
          <el-tag v-else type="info" size="small">未检查</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag
            :type="row.status === 'completed' ? 'success' : row.status === 'cancelled' ? 'info' : 'warning'"
          >
            {{ statusLabel[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canInspect(row)" size="small" type="primary" @click="openInspect(row)">录入检查</el-button>
          <el-button v-if="canComplete(row)" size="small" type="success" @click="onComplete(row)">完成退宿</el-button>
          <el-button v-if="canCancel(row)" size="small" type="danger" @click="onCancel(row)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(p: number) => { page = p; load() }"
    />

    <el-dialog v-model="createVisible" title="新建退宿申请" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="员工" prop="employee_id">
          <el-select v-model="form.employee_id" filterable placeholder="选择在住员工" style="width: 100%">
            <el-option
              v-for="e in employees"
              :key="e.id"
              :label="`${e.full_name} (${e.employee_no})`"
              :value="e.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="退宿类型">
          <el-select v-model="form.checkout_type" style="width: 100%">
            <el-option label="正常退宿" value="normal" />
            <el-option label="离职退宿" value="offboarding" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计退宿日">
          <el-date-picker
            v-model="form.expected_checkout_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="form.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="inspectVisible" title="房间检查" width="480px">
      <el-form label-width="120px">
        <el-form-item label="钥匙已归还">
          <el-switch v-model="inspectForm.key_returned" />
        </el-form-item>
        <el-form-item label="门禁卡已归还">
          <el-switch v-model="inspectForm.access_card_returned" />
        </el-form-item>
        <el-form-item label="物品已清空">
          <el-switch v-model="inspectForm.belongings_cleared" />
        </el-form-item>
        <el-form-item label="房间已检查">
          <el-switch v-model="inspectForm.room_inspected" />
        </el-form-item>
        <el-form-item label="检查备注">
          <el-input v-model="inspectForm.inspection_notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inspectVisible = false">取消</el-button>
        <el-button type="primary" @click="onInspect">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  padding: 16px;
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.muted {
  color: #909399;
  margin-left: 6px;
  font-size: 12px;
}
</style>
