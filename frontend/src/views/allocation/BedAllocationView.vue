<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { notifyError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { fetchDormTree, fetchFloorRoomCards, listRoomTypes } from '@/api/dormitories'
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
const selectedRoomId = ref<number | null>(null)
const rooms = ref<RoomCardOut[]>([])
const loading = ref(false)

// ---- UX-012: click bed → pick employee → confirm allocate ----
const targetBed = ref<BedCardOut | null>(null)
const employeeDialog = ref(false)
const employees = ref<EmployeeOut[]>([])
const selectedEmployee = ref<EmployeeOut | null>(null)
const employeeKeyword = ref('')
const allocating = ref(false)
const pendingLoad = ref(false)

// ---- UX-011: filters ----
const filters = reactive({
  areaId: null as number | null,
  buildingId: null as number | null,
  floorId: null as number | null,
  roomKeyword: '',
  bedStatus: '' as '' | 'all' | 'available' | 'reserved' | 'occupied' | 'maintenance' | 'disabled',
  genderPolicy: '' as '' | 'any' | 'male' | 'female',
  roomType: '',
})
const roomTypes = ref<Array<{ type_code: string; type_name: string }>>([])

const canAllocate = computed(() => auth.hasPermission('checkin:allocate'))

const floorLabel = computed(() => {
  if (selectedFloorId.value) {
    const found = findNode(tree.value, selectedFloorId.value)
    return found ? found.name : `楼层 ${selectedFloorId.value}`
  }
  return '请选择楼层或使用筛选'
})

const targetBedPath = computed(() => {
  const b = targetBed.value
  if (!b) return ''
  return (
    (b as { bed_path?: string }).bed_path ||
    [b.area_name, b.building_name, b.floor_no != null ? `${b.floor_no}F` : null, b.room_no, b.bed_no]
      .filter(Boolean)
      .join('/')
  )
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

function bedMatchesFilter(bed: BedCardOut): boolean {
  const s = filters.bedStatus
  if (!s || s === 'all') {
    /* no status filter */
  } else if (s === 'available' && !bed.available) return false
  else if (s === 'reserved' && !bed.reserved) return false
  else if (s === 'occupied' && !bed.occupied) return false
  else if (s === 'maintenance' && bed.operational_status !== 'maintenance') return false
  else if (s === 'disabled' && bed.operational_status !== 'disabled') return false

  return true
}

function roomMatchesFilter(room: RoomCardOut): boolean {
  if (filters.roomType && (room as { room_type?: string }).room_type !== filters.roomType) {
    return false
  }
  if (filters.genderPolicy) {
    const gp = (room as { gender_policy?: string }).gender_policy || 'any'
    if (filters.genderPolicy !== 'any' && gp !== 'any' && gp !== filters.genderPolicy) {
      return false
    }
  }
  const kw = filters.roomKeyword.trim().toLowerCase()
  if (kw && filters.bedStatus === '') {
    // keyword may match room even if no bed match — keep room if any bed or room_no matches
    const roomHit = String(room.room_no ?? '').toLowerCase().includes(kw)
    const bedHit = (room.beds || []).some((b) =>
      String(b.bed_no ?? '').toLowerCase().includes(kw)
    )
    if (!roomHit && !bedHit) return false
  }
  return true
}

const filteredRooms = computed(() => {
  const kw = filters.roomKeyword.trim().toLowerCase()
  return rooms.value
    .filter(roomMatchesFilter)
    .map((room) => {
      const roomNo = String(room.room_no ?? '').toLowerCase()
      const roomKwHit = !kw || roomNo.includes(kw)
      const beds = (room.beds || []).filter((bed) => {
        if (!bedMatchesFilter(bed)) return false
        if (kw && !roomKwHit) {
          // room_no didn't match — require bed_no match
          return String(bed.bed_no ?? '').toLowerCase().includes(kw)
        }
        return true
      })
      return {
        ...room,
        beds,
        available_count: beds.filter((b) => b.available).length,
        occupied_count: beds.filter((b) => b.occupied).length,
        reserved_count: beds.filter((b) => b.reserved).length,
      }
    })
    .filter((room) => room.beds.length > 0)
})

const totalBeds = computed(() =>
  filteredRooms.value.reduce((n, r) => n + (r.beds?.length || 0), 0)
)
const availableBeds = computed(() =>
  filteredRooms.value.reduce(
    (n, r) => n + (r.beds || []).filter((b) => b.available).length,
    0
  )
)

async function loadRooms() {
  if (!selectedFloorId.value) {
    rooms.value = []
    return
  }
  loading.value = true
  try {
    const cards = await fetchFloorRoomCards(selectedFloorId.value)
    rooms.value =
      selectedRoomId.value != null ? cards.filter((r) => r.id === selectedRoomId.value) : cards
  } catch (e: unknown) {
    notifyError(e, '加载房间失败')
  } finally {
    loading.value = false
  }
}

function findRoomFloorId(roomId: number): number | null {
  const fromExtra = (nodes: DormTreeNode[]): number | null => {
    for (const n of nodes) {
      if (n.node_type === 'room' && n.id === roomId) {
        const floorId = Number(n.extra?.floor_id ?? 0)
        return floorId > 0 ? floorId : null
      }
      const hit = fromExtra(n.children || [])
      if (hit != null) return hit
    }
    return null
  }
  const fromParent = (nodes: DormTreeNode[], floorId: number | null): number | null => {
    for (const n of nodes) {
      const currentFloor = n.node_type === 'floor' ? n.id : floorId
      if (n.node_type === 'room' && n.id === roomId) return currentFloor
      const hit = fromParent(n.children || [], currentFloor)
      if (hit != null) return hit
    }
    return null
  }
  return fromExtra(tree.value) ?? fromParent(tree.value, null)
}

function onTreeSelect(node: unknown) {
  const n = node as DormTreeNode
  if (!n) return
  if (n.node_type === 'floor') {
    selectedRoomId.value = null
    filters.floorId = n.id
    filters.buildingId = null
    filters.areaId = null
    selectedFloorId.value = n.id
  } else if (n.node_type === 'room') {
    selectedRoomId.value = n.id
    const floorId = findRoomFloorId(n.id)
    filters.floorId = floorId
    if (floorId != null && floorId !== selectedFloorId.value) {
      selectedFloorId.value = floorId
    } else {
      void loadRooms()
    }
  } else if (n.node_type === 'building') {
    selectedRoomId.value = null
    selectedFloorId.value = null
    filters.buildingId = n.id
    filters.areaId = null
    filters.floorId = null
    rooms.value = []
  } else if (n.node_type === 'area') {
    selectedRoomId.value = null
    selectedFloorId.value = null
    filters.areaId = n.id
    filters.buildingId = null
    filters.floorId = null
    rooms.value = []
  }
}

function resetFilters() {
  filters.areaId = null
  filters.buildingId = null
  filters.floorId = null
  filters.roomKeyword = ''
  filters.bedStatus = ''
  filters.genderPolicy = ''
  filters.roomType = ''
  selectedRoomId.value = null
  selectedFloorId.value = null
  rooms.value = []
}

function bedStatusTag(bed: BedCardOut): { label: string; type: string } {
  if (bed.operational_status === 'disabled') return { label: '停用', type: 'info' }
  if (bed.operational_status === 'maintenance') return { label: '维修', type: 'warning' }
  if (bed.occupied) return { label: '已入住', type: 'danger' }
  if (bed.reserved) return { label: '已预留', type: 'warning' }
  return { label: '空闲', type: 'success' }
}

async function searchEmployees() {
  if (pendingLoad.value) return
  pendingLoad.value = true
  try {
    // BUG-014: candidate set = employment_status active + needs housing +
    // no active accommodation + no active reservation (backend enforces too)
    const page = await listEmployees({
      page: 1,
      page_size: 50,
      keyword: employeeKeyword.value || undefined,
      accommodation_status: 'allocatable',
      employment_status: 'active',
      accommodation_required: true,
    })
    employees.value = page.items
  } catch (e) {
    notifyError(e, '加载员工失败')
  } finally {
    pendingLoad.value = false
  }
}

async function openEmployeeDialog() {
  employeeDialog.value = true
  await searchEmployees()
}

/** UX-012 step 1: click available bed → open picker with target bed recorded. */
async function onBedClick(bed: BedCardOut) {
  if (!canAllocate.value) {
    ElMessage.warning('没有分配床位权限')
    return
  }
  if (!bed.available) {
    ElMessage.warning('该床位当前不可分配')
    return
  }
  targetBed.value = bed
  selectedEmployee.value = null
  employeeDialog.value = true
  await searchEmployees()
}

function pickEmployee(emp: EmployeeOut) {
  selectedEmployee.value = emp
}

async function confirmAllocate() {
  const bed = targetBed.value
  const emp = selectedEmployee.value
  if (!bed || !emp || allocating.value) return
  allocating.value = true
  try {
    const app = await createCheckinApplication({
      employee_id: emp.id,
      application_type: 'new',
    })
    await approveCheckinApplication(app.id)
    try {
      await reserveCheckinBed(app.id, bed.id)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : ''
      if (isConflict(msg)) {
        ElMessage.error('床位冲突：其他管理员可能已分配该床位，已刷新状态')
      } else {
        ElMessage.error(msg || '预留床位失败')
      }
      await loadRooms()
      return // keep dialog + selected employee
    }
    await confirmCheckin(app.id)
    ElMessage.success('分配成功')
    employeeDialog.value = false
    targetBed.value = null
    selectedEmployee.value = null
    await loadRooms()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '分配失败'
    if (isConflict(msg)) {
      ElMessage.error('床位冲突（409）：该床位已被抢占，已刷新状态')
      await loadRooms()
    } else {
      notifyError(e, msg)
    }
    // keep target bed + selected employee for retry
  } finally {
    allocating.value = false
  }
}

function isConflict(msg: string): boolean {
  return msg.includes('409') || msg.includes('冲突') || msg.toLowerCase().includes('conflict')
}

function bedTooltip(bed: BedCardOut): string {
  if (bed.occupant) return `住户：${bed.occupant.full_name}（${bed.occupant.employee_no}）`
  if (bed.reserved_for) return `预留：${bed.reserved_for.full_name}（${bed.reserved_for.employee_no}）`
  return bedStatusTag(bed).label
}

watch(selectedFloorId, () => void loadRooms())

onMounted(async () => {
  await loadTree()
  try {
    roomTypes.value = await listRoomTypes()
  } catch {
    roomTypes.value = []
  }
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
              <span class="stats">
                房间 {{ filteredRooms.length }} · 床位 {{ totalBeds }} · 空闲 {{ availableBeds }}
              </span>
              <el-button size="small" :loading="loading" @click="loadRooms">刷新状态</el-button>
            </div>
          </template>

          <div class="filter-bar">
            <el-select v-model="filters.bedStatus" placeholder="床位状态" clearable style="width: 120px">
              <el-option label="全部" value="" />
              <el-option label="空闲" value="available" />
              <el-option label="预留" value="reserved" />
              <el-option label="已入住" value="occupied" />
              <el-option label="维修" value="maintenance" />
              <el-option label="停用" value="disabled" />
            </el-select>
            <el-select v-model="filters.genderPolicy" placeholder="性别政策" clearable style="width: 110px">
              <el-option label="不限" value="any" />
              <el-option label="男" value="male" />
              <el-option label="女" value="female" />
            </el-select>
            <el-select v-model="filters.roomType" placeholder="房型" clearable style="width: 120px">
              <el-option
                v-for="t in roomTypes"
                :key="t.type_code"
                :label="t.type_name"
                :value="t.type_code"
              />
            </el-select>
            <el-input
              v-model="filters.roomKeyword"
              placeholder="房间号 / 床位号"
              clearable
              style="width: 150px"
            />
            <el-button size="small" @click="resetFilters">重置</el-button>
          </div>
          <div v-loading="loading">
            <el-empty v-if="!filteredRooms.length" description="请选择楼层或调整筛选条件" />
            <div v-else class="room-grid">
              <div v-for="room in filteredRooms" :key="room.id" class="room-card">
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
                      @click="onBedClick(bed)"
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

    <el-dialog
    v-model="employeeDialog"
    title="选择待入住员工"
    width="720px"
    :close-on-click-modal="false"
  >
    <template #header>
      <div class="dlg-header">
        <div>
          <div class="dlg-title">选择待入住员工</div>
          <div class="dlg-sub">目标床位：{{ targetBedPath || '—' }}</div>
        </div>
      </div>
    </template>
    <el-input
      v-model="employeeKeyword"
      placeholder="姓名 / 工号 / 部门搜索"
      clearable
      @keyup.enter="searchEmployees"
      @clear="searchEmployees"
    />
    <el-button size="small" style="margin: 8px 0" :loading="pendingLoad" @click="searchEmployees">
      搜索
    </el-button>
    <el-table
      :data="employees"
      height="320"
      highlight-current-row
      style="margin-top: 4px"
      @row-click="pickEmployee"
    >
      <el-table-column width="40">
        <template #default="{ row }">
          <el-radio :model-value="selectedEmployee?.id" :value="row.id" @change="pickEmployee(row)">
            {{ '' }}
          </el-radio>
        </template>
      </el-table-column>
      <el-table-column prop="employee_no" label="工号" width="130" />
      <el-table-column prop="full_name" label="姓名" width="110" />
      <el-table-column prop="department_name" label="部门" min-width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          {{ row.employment_status === 'active' ? '在职' : row.employment_status }}
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="employeeDialog = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!selectedEmployee || allocating"
        :loading="allocating"
        @click="confirmAllocate"
      >
        确认分配
      </el-button>
    </template>
  </el-dialog>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.stats {
  margin-left: 12px;
  color: #666;
  font-size: 12px;
}
.dlg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.dlg-title {
  font-weight: 600;
}
.dlg-sub {
  font-size: 12px;
  color: #888;
  margin-top: 4px;
}

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
