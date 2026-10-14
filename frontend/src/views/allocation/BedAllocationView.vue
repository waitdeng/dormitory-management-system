<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { fetchDormTree, fetchFloorRoomCards } from '@/api/dormitories'
import { listEmployees } from '@/api/employees'
import {
  createCheckinApplication,
  approveCheckinApplication,
  reserveCheckinBed,
  confirmCheckin,
} from '@/api/accommodations'
import type { BedCardOut, DormTreeNode, EmployeeOut, RoomCardOut } from '@/types'

const auth = useAuthStore()
const tree = ref<DormTreeNode[]>([])
const selectedFloorId = ref<number | null>(null)
const rooms = ref<RoomCardOut[]>([])
const loading = ref(false)
const employees = ref<EmployeeOut[]>([])
const selectedEmployee = ref<EmployeeOut | null>(null)
const employeeDialog = ref(false)
const employeeKeyword = ref('')
const allocating = ref(false)

const canAllocate = computed(() => auth.hasPermission('checkin:allocate'))

const floorLabel = computed(() => {
  if (!selectedFloorId.value) return '请选择楼层'
  const found = findNode(tree.value, selectedFloorId.value)
  return found ? `${found.name}` : `楼层 ${selectedFloorId.value}`
})

function findNode(nodes: DormTreeNode[], id: number): DormTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const child = findNode(n.children || [], id)
    if (child) return child
  }
  return null
}

async function loadTree() {
  tree.value = await fetchDormTree(false)
}

async function loadRooms() {
  if (!selectedFloorId.value) {
    rooms.value = []
    return
  }
  loading.value = true
  try {
    rooms.value = await fetchFloorRoomCards(selectedFloorId.value)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '加载房间失败')
  } finally {
    loading.value = false
  }
}

function onTreeSelect(node: unknown) {
  const n = node as DormTreeNode
  if (n?.node_type === 'floor') {
    selectedFloorId.value = n.id
    void loadRooms()
  }
}

function bedStatusTag(bed: BedCardOut): { label: string; type: string } {
  if (bed.operational_status === 'disabled') return { label: '停用', type: 'info' }
  if (bed.operational_status === 'maintenance') return { label: '维修', type: 'warning' }
  if (bed.occupied) return { label: '已入住', type: 'danger' }
  if (bed.reserved) return { label: '已预留', type: 'warning' }
  return { label: '空闲', type: 'success' }
}

async function openEmployeeDialog() {
  employeeDialog.value = true
  await searchEmployees()
}

async function searchEmployees() {
  const page = await listEmployees({
    page: 1,
    page_size: 50,
    keyword: employeeKeyword.value || undefined,
    accommodation_status: 'not_in_dorm',
  })
  employees.value = page.items
}

function pickEmployee(emp: EmployeeOut) {
  selectedEmployee.value = emp
  employeeDialog.value = false
}

async function allocateBed(bed: BedCardOut) {
  if (!canAllocate.value) {
    ElMessage.warning('没有分配床位权限')
    return
  }
  if (!selectedEmployee.value) {
    ElMessage.warning('请先选择待入住员工')
    await openEmployeeDialog()
    return
  }
  if (!bed.available) {
    ElMessage.warning('该床位当前不可分配')
    await loadRooms()
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将床位 ${bed.bed_no} 分配给 ${selectedEmployee.value.full_name}（${selectedEmployee.value.employee_no}）？`,
      '确认分床',
      { type: 'warning' }
    )
  } catch {
    return
  }
  allocating.value = true
  try {
    const app = await createCheckinApplication({
      employee_id: selectedEmployee.value.id,
      application_type: 'new',
    })
    await approveCheckinApplication(app.id)
    try {
      await reserveCheckinBed(app.id, bed.id)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : ''
      if (msg.includes('409') || msg.toLowerCase().includes('conflict') || msg.includes('冲突')) {
        ElMessage.error('该床位已被其他管理员分配，请刷新后重试')
      } else {
        ElMessage.error(msg || '预留床位失败')
      }
      await loadRooms()
      return
    }
    await confirmCheckin(app.id)
    ElMessage.success('分配成功')
    selectedEmployee.value = null
    await loadRooms()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '分配失败'
    if (msg.includes('409') || msg.includes('冲突') || msg.toLowerCase().includes('conflict')) {
      ElMessage.error('床位冲突：其他管理员可能已分配该床位，已刷新状态')
    } else {
      ElMessage.error(msg)
    }
    await loadRooms()
  } finally {
    allocating.value = false
  }
}

function bedTooltip(bed: BedCardOut): string {
  if (bed.occupant) return `住户：${bed.occupant.full_name}（${bed.occupant.employee_no}）`
  if (bed.reserved_for) return `预留：${bed.reserved_for.full_name}（${bed.reserved_for.employee_no}）`
  return bedStatusTag(bed).label
}

watch(selectedFloorId, () => void loadRooms())

onMounted(async () => {
  await loadTree()
})
</script>

<template>
  <div class="allocation-page">
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>宿舍导航</span>
              <el-button size="small" @click="loadTree">刷新</el-button>
            </div>
          </template>
          <el-tree
            :data="tree"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            highlight-current
            @node-click="onTreeSelect"
          >
            <template #default="{ data }">
              <span>
                <el-tag v-if="data.node_type === 'floor'" size="small" type="info">楼层</el-tag>
                <el-tag v-else-if="data.node_type === 'building'" size="small">楼栋</el-tag>
                <el-tag v-else-if="data.node_type === 'area'" size="small" type="warning">区域</el-tag>
                <el-tag v-else size="small" type="success">房间</el-tag>
                {{ data.name }}
              </span>
            </template>
          </el-tree>
        </el-card>

        <el-card shadow="never" class="employee-card">
          <template #header>待入住员工</template>
          <template v-if="selectedEmployee">
            <div class="emp-line">{{ selectedEmployee.full_name }}</div>
            <div class="emp-sub">{{ selectedEmployee.employee_no }}</div>
            <div class="emp-sub">{{ selectedEmployee.department_name || '—' }}</div>
            <el-button size="small" style="margin-top: 8px" @click="openEmployeeDialog">
              更换员工
            </el-button>
          </template>
          <template v-else>
            <el-empty description="尚未选择员工" :image-size="60" />
            <el-button type="primary" size="small" @click="openEmployeeDialog">选择员工</el-button>
          </template>
        </el-card>
      </el-col>

      <el-col :span="18">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ floorLabel }} · 房间床位</span>
              <el-button size="small" :loading="loading" @click="loadRooms">刷新状态</el-button>
            </div>
          </template>
          <div v-loading="loading">
            <el-empty v-if="!rooms.length" description="请选择左侧楼层查看房间" />
            <div v-else class="room-grid">
              <div v-for="room in rooms" :key="room.id" class="room-card">
                <div class="room-head">
                  <strong>{{ room.room_no }}</strong>
                  <span class="room-meta">
                    核定 {{ room.capacity }} · 入住 {{ room.occupied_count }} ·
                    预留 {{ room.reserved_count }} · 可分配 {{ room.available_count }}
                  </span>
                </div>
                <div class="bed-row">
                  <el-tooltip
                    v-for="bed in room.beds"
                    :key="bed.id"
                    :content="bedTooltip(bed)"
                    placement="top"
                  >
                    <el-button
                      size="small"
                      :type="(bedStatusTag(bed).type as 'success'|'warning'|'danger'|'info')"
                      :disabled="!bed.available || !canAllocate || allocating"
                      @click="allocateBed(bed)"
                    >
                      {{ bed.bed_no }} · {{ bedStatusTag(bed).label }}
                    </el-button>
                  </el-tooltip>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="employeeDialog" title="选择待入住员工" width="640px">
      <el-input
        v-model="employeeKeyword"
        placeholder="工号 / 姓名"
        clearable
        @keyup.enter="searchEmployees"
      />
      <el-table :data="employees" height="320" style="margin-top: 12px" @row-click="pickEmployee">
        <el-table-column prop="employee_no" label="工号" width="140" />
        <el-table-column prop="full_name" label="姓名" width="120" />
        <el-table-column prop="department_name" label="部门" />
        <el-table-column prop="accommodation_status" label="住宿状态" width="110" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.employee-card {
  margin-top: 12px;
}
.emp-line {
  font-size: 16px;
  font-weight: 600;
}
.emp-sub {
  color: #666;
  font-size: 13px;
}
.room-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.room-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
}
.room-head {
  margin-bottom: 8px;
}
.room-meta {
  display: block;
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
.bed-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
