<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { extractError } from '@/api/client'
import {
  alertsSummary,
  cancelTodo,
  completeTodo,
  listAlerts,
  listTodos,
  resolveAlert,
  runScanner,
  todosSummary,
} from '@/api/workflow'
import type { WorkflowAlertOut, WorkflowSummary, WorkflowTodoOut } from '@/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const activeTab = ref('todos')

const todoLoading = ref(false)
const todoRows = ref<WorkflowTodoOut[]>([])
const todoTotal = ref(0)
const todoPage = ref(1)
const todoPageSize = ref(20)
const todoStatus = ref('pending')
const todoSummary = ref<WorkflowSummary>({ by_type: {} })

const alertLoading = ref(false)
const alertRows = ref<WorkflowAlertOut[]>([])
const alertTotal = ref(0)
const alertPage = ref(1)
const alertPageSize = ref(20)
const alertStatus = ref('active')
const alertSummary = ref<WorkflowSummary>({ by_type: {} })

const scanning = ref(false)

const todoStatusLabel: Record<string, string> = {
  pending: '待处理',
  completed: '已完成',
  cancelled: '已取消',
}
const alertStatusLabel: Record<string, string> = {
  active: '生效中',
  resolved: '已解除',
}
const alertTypeLabel: Record<string, string> = {
  terminated_still_housed: '离职未退宿',
  reservation_overdue: '预留过期',
  reservation_expired: '预留已释放',
  overdue_checkin: '超期未入住',
  overdue_checkout: '待退宿超期',
  disabled_bed_occupied: '停用床位仍有住户',
}
const todoTypeLabel: Record<string, string> = {
  checkout_offboarding: '离职退宿',
  overdue_checkin: '超期未入住',
  reservation_release: '预留释放',
  manual: '手工待办',
}
const severityLabel: Record<string, string> = {
  info: '提示',
  warning: '警告',
  critical: '严重',
}
const priorityLabel: Record<string, string> = {
  low: '低',
  normal: '普通',
  high: '高',
  urgent: '紧急',
}

function severityTag(severity: string): 'info' | 'warning' | 'danger' {
  if (severity === 'critical') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function statusTag(status: string): 'success' | 'info' | 'warning' | 'danger' {
  if (status === 'completed' || status === 'resolved') return 'success'
  if (status === 'cancelled') return 'info'
  if (status === 'pending' || status === 'active') return 'warning'
  return 'info'
}

async function loadTodos(): Promise<void> {
  todoLoading.value = true
  try {
    const [list, summary] = await Promise.all([
      listTodos({
        page: todoPage.value,
        page_size: todoPageSize.value,
        status: todoStatus.value || undefined,
      }),
      todosSummary(),
    ])
    todoRows.value = list.items
    todoTotal.value = list.total
    todoSummary.value = summary
  } catch (error) {
    ElMessage.error(extractError(error))
  } finally {
    todoLoading.value = false
  }
}

async function loadAlerts(): Promise<void> {
  alertLoading.value = true
  try {
    const [list, summary] = await Promise.all([
      listAlerts({
        page: alertPage.value,
        page_size: alertPageSize.value,
        status: alertStatus.value || undefined,
      }),
      alertsSummary(),
    ])
    alertRows.value = list.items
    alertTotal.value = list.total
    alertSummary.value = summary
  } catch (error) {
    ElMessage.error(extractError(error))
  } finally {
    alertLoading.value = false
  }
}

async function loadAll(): Promise<void> {
  await Promise.all([loadTodos(), loadAlerts()])
}

function onTabChange(): void {
  void loadAll()
}

async function onCompleteTodo(row: WorkflowTodoOut): Promise<void> {
  try {
    await completeTodo(row.id)
    ElMessage.success('待办已完成')
    await loadTodos()
  } catch (error) {
    ElMessage.error(extractError(error))
  }
}

async function onCancelTodo(row: WorkflowTodoOut): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入取消原因', '取消待办', {
      inputPlaceholder: '可选',
    })
    await cancelTodo(row.id, value || undefined)
    ElMessage.success('待办已取消')
    await loadTodos()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(extractError(error))
  }
}

async function onResolveAlert(row: WorkflowAlertOut): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入解除原因', '解除预警', {
      inputPlaceholder: '可选',
    })
    await resolveAlert(row.id, value || undefined)
    ElMessage.success('预警已解除')
    await loadAlerts()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(extractError(error))
  }
}

async function onRunScanner(): Promise<void> {
  scanning.value = true
  try {
    await runScanner()
    ElMessage.success('扫描任务已执行')
    await loadAll()
  } catch (error) {
    ElMessage.error(extractError(error))
  } finally {
    scanning.value = false
  }
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>待办中心</h2>
        <p class="muted">离职退宿待办、异常预警与站内通知</p>
      </div>
      <el-button
        v-if="auth.hasPermission('employee:offboard') || auth.hasPermission('bed:manage')"
        type="primary"
        :loading="scanning"
        @click="onRunScanner"
      >
        执行扫描任务
      </el-button>
    </div>

    <el-tabs v-model="activeTab" class="tabs" @tab-change="onTabChange">
      <el-tab-pane name="todos">
        <template #label>
          待办
          <el-badge
            v-if="todoSummary.pending"
            :value="todoSummary.pending"
            class="tab-badge"
          />
        </template>
        <div class="summary-row">
          <el-tag type="warning">待处理 {{ todoSummary.pending ?? 0 }}</el-tag>
          <el-tag type="success">已完成 {{ todoSummary.completed ?? 0 }}</el-tag>
          <el-tag type="info">已取消 {{ todoSummary.cancelled ?? 0 }}</el-tag>
        </div>
        <div class="filter-row">
          <el-select v-model="todoStatus" clearable placeholder="状态" style="width: 140px">
            <el-option label="待处理" value="pending" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
            <el-option label="全部" value="" />
          </el-select>
          <el-button @click="loadTodos">刷新</el-button>
        </div>
        <el-table v-loading="todoLoading" :data="todoRows" stripe>
          <el-table-column prop="title" label="标题" min-width="220" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              {{ todoTypeLabel[row.todo_type] || row.todo_type }}
            </template>
          </el-table-column>
          <el-table-column prop="employee_name" label="员工" width="120">
            <template #default="{ row }">
              {{ row.employee_name || '—' }}
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">
              {{ priorityLabel[row.priority] || row.priority }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)">
                {{ todoStatusLabel[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button link type="primary" @click="onCompleteTodo(row)">完成</el-button>
                <el-button link type="info" @click="onCancelTodo(row)">取消</el-button>
              </template>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="todoPage"
          v-model:page-size="todoPageSize"
          :total="todoTotal"
          layout="total, prev, pager, next"
          class="pager"
          @current-change="loadTodos"
        />
      </el-tab-pane>

      <el-tab-pane name="alerts">
        <template #label>
          异常预警
          <el-badge
            v-if="alertSummary.active"
            :value="alertSummary.active"
            class="tab-badge"
          />
        </template>
        <div class="summary-row">
          <el-tag type="danger">生效中 {{ alertSummary.active ?? 0 }}</el-tag>
          <el-tag type="success">已解除 {{ alertSummary.resolved ?? 0 }}</el-tag>
          <el-tag
            v-for="(cnt, type) in alertSummary.by_type"
            :key="type"
            type="warning"
          >
            {{ alertTypeLabel[type] || type }} {{ cnt }}
          </el-tag>
        </div>
        <div class="filter-row">
          <el-select v-model="alertStatus" clearable placeholder="状态" style="width: 140px">
            <el-option label="生效中" value="active" />
            <el-option label="已解除" value="resolved" />
            <el-option label="全部" value="" />
          </el-select>
          <el-button @click="loadAlerts">刷新</el-button>
        </div>
        <el-table v-loading="alertLoading" :data="alertRows" stripe>
          <el-table-column prop="title" label="标题" min-width="220" />
          <el-table-column label="类型" width="140">
            <template #default="{ row }">
              {{ alertTypeLabel[row.alert_type] || row.alert_type }}
            </template>
          </el-table-column>
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag :type="severityTag(row.severity)">
                {{ severityLabel[row.severity] || row.severity }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="employee_name" label="员工" width="120">
            <template #default="{ row }">
              {{ row.employee_name || '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)">
                {{ alertStatusLabel[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'active'"
                link
                type="primary"
                @click="onResolveAlert(row)"
              >
                解除
              </el-button>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="alertPage"
          v-model:page-size="alertPageSize"
          :total="alertTotal"
          layout="total, prev, pager, next"
          class="pager"
          @current-change="loadAlerts"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.page {
  padding: 8px 0;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.muted {
  color: #909399;
  margin: 0;
}
.summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.tab-badge {
  margin-left: 6px;
}
</style>
