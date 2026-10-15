<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { notifyError } from '@/api/client'
import {
  approveCheckinApplication,
  cancelCheckinApplication,
  confirmCheckin,
  createCheckinApplication,
  listCheckinApplications,
  rejectCheckinApplication,
  reserveCheckinBed,
} from '@/api/accommodations'
import { listAvailableBeds } from '@/api/dormitories'
import { listEmployees } from '@/api/employees'
import type { BedOut, CheckinApplicationOut, EmployeeOut } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const keyword = ref('')
const rows = ref<CheckinApplicationOut[]>([])

const createVisible = ref(false)
const formRef = ref<FormInstance>()
const employees = ref<EmployeeOut[]>([])
const form = reactive({
  employee_id: undefined as number | undefined,
  application_type: 'new',
  requested_checkin_date: '',
  reason: '',
})

const rules: FormRules = {
  employee_id: [{ required: true, message: '请选择员工', trigger: 'change' }],
}

const reserveVisible = ref(false)
const reserveAppId = ref<number | null>(null)
const beds = ref<BedOut[]>([])
const selectedBedId = ref<number | null>(null)

const statusLabel: Record<string, string> = {
  pending: '待审批',
  approved: '已批准',
  reserved: '已预留',
  checked_in: '已入住',
  rejected: '已驳回',
  cancelled: '已取消',
  expired: '已过期',
}

function canApprove(row: CheckinApplicationOut): boolean {
  return row.status === 'pending' && auth.hasPermission('checkin:approve')
}
function canReserve(row: CheckinApplicationOut): boolean {
  return row.status === 'approved' && auth.hasPermission('checkin:allocate')
}
function canConfirm(row: CheckinApplicationOut): boolean {
  return row.status === 'reserved' && auth.hasPermission('checkin:confirm')
}
function canCancel(row: CheckinApplicationOut): boolean {
  return ['pending', 'approved', 'reserved'].includes(row.status) && auth.hasPermission('checkin:approve')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listCheckinApplications({
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
  form.application_type = 'new'
  form.requested_checkin_date = ''
  form.reason = ''
  createVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid || !form.employee_id) return
    try {
      await createCheckinApplication({
        employee_id: form.employee_id,
        application_type: form.application_type,
        requested_checkin_date: form.requested_checkin_date || null,
        reason: form.reason || null,
      })
      ElMessage.success('入住申请已创建')
      createVisible.value = false
      await load()
    } catch (error) {
      notifyError(error)
    }
  })
}

async function onApprove(row: CheckinApplicationOut): Promise<void> {
  try {
    await approveCheckinApplication(row.id)
    ElMessage.success('已批准')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function onReject(row: CheckinApplicationOut): Promise<void> {
  try {
    await rejectCheckinApplication(row.id, '不符合入住条件')
    ElMessage.success('已驳回')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function openReserve(row: CheckinApplicationOut): Promise<void> {
  reserveAppId.value = row.id
  selectedBedId.value = row.assigned_bed_id
  reserveVisible.value = true
  try {
    beds.value = await listAvailableBeds({ limit: 200 })
  } catch (error) {
    notifyError(error)
    beds.value = []
  }
}

async function onReserve(): Promise<void> {
  if (!reserveAppId.value || !selectedBedId.value) {
    ElMessage.warning('请选择床位')
    return
  }
  try {
    await reserveCheckinBed(reserveAppId.value, selectedBedId.value)
    ElMessage.success('床位已预留')
    reserveVisible.value = false
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function onConfirm(row: CheckinApplicationOut): Promise<void> {
  try {
    await confirmCheckin(row.id)
    ElMessage.success('已确认入住')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

async function onCancel(row: CheckinApplicationOut): Promise<void> {
  try {
    await cancelCheckinApplication(row.id, '管理员取消')
    ElMessage.success('已取消')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

onMounted(async () => {
  await load()
  try {
    // BUG-007: only employees who require accommodation can apply for check-in
    const data = await listEmployees({
      page: 1,
      page_size: 100,
      accommodation_required: true,
    })
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
        placeholder="申请单号 / 工号 / 姓名"
        clearable
        style="width: 220px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button
        v-if="auth.hasPermission('checkin:create')"
        type="success"
        @click="openCreate"
      >
        新建入住申请
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="application_no" label="申请单号" min-width="160" />
      <el-table-column label="员工" min-width="140">
        <template #default="{ row }">
          {{ row.employee_name || row.employee_id }}
          <span class="muted">{{ row.employee_no }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="application_type" label="类型" width="90" />
      <el-table-column label="床位" min-width="140">
        <template #default="{ row }">
          <span v-if="row.bed">{{ row.bed.bed_path || [row.bed.area_name, row.bed.building_name, row.bed.floor_no != null ? `${row.bed.floor_no}F` : null, row.bed.room_no, row.bed.bed_no].filter(Boolean).join('/') }}</span>
          <span v-else class="muted">未分配</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'checked_in' ? 'success' : row.status === 'pending' ? 'warning' : 'info'">
            {{ statusLabel[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="160">
        <template #default="{ row }">
          {{ row.created_at ? row.created_at.replace('T', ' ').slice(0, 19) : '' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canApprove(row)" size="small" type="success" @click="onApprove(row)">批准</el-button>
          <el-button v-if="canApprove(row)" size="small" type="warning" @click="onReject(row)">驳回</el-button>
          <el-button v-if="canReserve(row)" size="small" type="primary" @click="openReserve(row)">分床</el-button>
          <el-button v-if="canConfirm(row)" size="small" type="success" @click="onConfirm(row)">确认入住</el-button>
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

    <el-dialog v-model="createVisible" title="新建入住申请" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="员工" prop="employee_id">
          <el-select v-model="form.employee_id" filterable placeholder="选择员工" style="width: 100%">
            <el-option
              v-for="e in employees"
              :key="e.id"
              :label="`${e.full_name} (${e.employee_no})`"
              :value="e.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="申请类型">
          <el-select v-model="form.application_type" style="width: 100%">
            <el-option label="新入住" value="new" />
            <el-option label="再入住" value="recheck" />
            <el-option label="临时住宿" value="temporary" />
          </el-select>
        </el-form-item>
        <el-form-item label="期望入住日">
          <el-date-picker
            v-model="form.requested_checkin_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="事由">
          <el-input v-model="form.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reserveVisible" title="分配床位" width="520px">
      <el-table :data="beds" height="320" border @row-click="(row: BedOut) => (selectedBedId = row.id)">
        <el-table-column width="50">
          <template #default="{ row }">
            <el-radio :model-value="selectedBedId" :label="row.id" @change="selectedBedId = row.id" />
          </template>
        </el-table-column>
        <el-table-column prop="bed_no" label="床位号" width="100" />
        <el-table-column prop="room_id" label="房间 ID" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.available" type="success">空闲</el-tag>
            <el-tag v-else type="info">不可用</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="reserveVisible = false">取消</el-button>
        <el-button type="primary" @click="onReserve">确认预留</el-button>
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
