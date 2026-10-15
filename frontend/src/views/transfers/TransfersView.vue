<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { notifyError } from '@/api/client'
import {
  cancelTransfer,
  completeTransfer,
  createTransfer,
  listTransfers,
  reserveTransferTarget,
} from '@/api/accommodations'
import { listAvailableBeds } from '@/api/dormitories'
import { listEmployees } from '@/api/employees'
import type { BedOut, EmployeeOut, TransferRecordOut } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const keyword = ref('')
const rows = ref<TransferRecordOut[]>([])

const createVisible = ref(false)
const formRef = ref<FormInstance>()
const employees = ref<EmployeeOut[]>([])
const beds = ref<BedOut[]>([])
const form = reactive({
  employee_id: undefined as number | undefined,
  target_bed_id: undefined as number | undefined,
  reason: '',
})

const rules: FormRules = {
  employee_id: [{ required: true, message: '请选择员工', trigger: 'change' }],
  target_bed_id: [{ required: true, message: '请选择目标床位', trigger: 'change' }],
}

const statusLabel: Record<string, string> = {
  pending: '待处理',
  reserved: '已预留目标床',
  completed: '已完成',
  cancelled: '已取消',
}

function formatBedPath(bed: {
  area_name?: string | null
  building_name?: string | null
  floor_no?: number | null
  room_no?: string | null
  bed_no: string
}): string {
  return [
    bed.area_name,
    bed.building_name,
    bed.floor_no != null ? `${bed.floor_no}F` : null,
    bed.room_no,
    bed.bed_no,
  ]
    .filter((p): p is string => p != null && p !== '')
    .join('/')
}

function canReserve(row: TransferRecordOut): boolean {
  return ['pending', 'reserved'].includes(row.status) && auth.hasPermission('transfer:create')
}
function canComplete(row: TransferRecordOut): boolean {
  return row.status === 'reserved' && auth.hasPermission('transfer:complete')
}
function canCancel(row: TransferRecordOut): boolean {
  return ['pending', 'reserved'].includes(row.status) && auth.hasPermission('transfer:complete')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listTransfers({
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value || undefined,
      keyword: keyword.value || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.employee_id = undefined
  form.target_bed_id = undefined
  form.reason = ''
  createVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid || !form.employee_id || !form.target_bed_id) return
    try {
      await createTransfer({
        employee_id: form.employee_id,
        target_bed_id: form.target_bed_id,
        reason: form.reason || null,
      })
      ElMessage.success('调宿申请已创建')
      createVisible.value = false
      await load()
    } catch (error) {
      notifyError(error)
    }
  })
}

async function onReserve(row: TransferRecordOut): Promise<void> {
  try {
    await reserveTransferTarget(row.id)
    ElMessage.success('目标床位已预留')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function onComplete(row: TransferRecordOut): Promise<void> {
  try {
    await completeTransfer(row.id)
    ElMessage.success('调宿已完成')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function onCancel(row: TransferRecordOut): Promise<void> {
  try {
    await cancelTransfer(row.id, '管理员取消')
    ElMessage.success('已取消')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

onMounted(async () => {
  await load()
  try {
    // only currently housed employees can transfer
    const data = await listEmployees({
      page: 1,
      page_size: 100,
      accommodation_status: 'in_dorm',
    })
    employees.value = data.items
    beds.value = await listAvailableBeds({ limit: 200 })
  } catch {
    employees.value = []
    beds.value = []
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
        placeholder="调宿单号 / 工号 / 姓名"
        clearable
        style="width: 220px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button v-if="auth.hasPermission('transfer:create')" type="success" @click="openCreate">
        新建调宿
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="transfer_no" label="调宿单号" min-width="160" />
      <el-table-column label="员工" min-width="130">
        <template #default="{ row }">
          {{ row.employee_name || row.employee_id }}
          <span class="muted">{{ row.employee_no }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原床位" min-width="130">
        <template #default="{ row }">
          <span v-if="row.source_bed">
            {{ formatBedPath(row.source_bed) }}
          </span>
          <span v-else>{{ row.source_bed_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="目标床位" min-width="130">
        <template #default="{ row }">
          <span v-if="row.target_bed">
            {{ formatBedPath(row.target_bed) }}
          </span>
          <span v-else>{{ row.target_bed_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag
            :type="row.status === 'completed' ? 'success' : row.status === 'cancelled' ? 'info' : 'warning'"
          >
            {{ statusLabel[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canReserve(row)" size="small" type="primary" @click="onReserve(row)">预留目标床</el-button>
          <el-button v-if="canComplete(row)" size="small" type="success" @click="onComplete(row)">确认调宿</el-button>
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

    <el-dialog v-model="createVisible" title="新建调宿申请" width="500px">
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
        <el-form-item label="目标床位" prop="target_bed_id">
          <el-select v-model="form.target_bed_id" filterable placeholder="选择空闲床位" style="width: 100%">
            <el-option
              v-for="b in beds"
              :key="b.id"
              :label="b.bed_path || [b.area_name, b.building_name, b.floor_no != null ? `${b.floor_no}F` : null, b.room_no, b.bed_no].filter(Boolean).join('/')"
              :value="b.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="调宿原因">
          <el-input v-model="form.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">提交</el-button>
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
