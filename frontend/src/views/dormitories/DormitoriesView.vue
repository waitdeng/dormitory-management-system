<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { notifyError } from '@/api/client'
import {
  commitRoomImport,
  createArea,
  createBed,
  createBuilding,
  createFloor,
  createRoom,
  createRoomType,
  deleteDormResource,
  disableRoomType,
  downloadRoomImportTemplate,
  fetchDormTree,
  fetchRoom,
  listRoomBeds,
  listRooms,
  listRoomTypes,
  previewRoomImport,
  revealRoomAccessCode,
  setRoomAccessCode,
  setBedStatus,
  updateBed,
  deleteRoomType,
  updateArea,
  updateBuilding,
  updateFloor,
  updateRoom,
  updateRoomType,
} from '@/api/dormitories'
import type { BedOut, DormTreeNode, RoomOut } from '@/types'

type RoomTypeRow = {
  id: number
  type_code: string
  type_name: string
  default_capacity: number
  description: string | null
  status: string
}

type ImportRow = {
  row: number
  action: string
  message: string | null
  data: Record<string, unknown>
}

const auth = useAuthStore()
const treeData = ref<DormTreeNode[]>([])
const treeLoading = ref(false)
const selectedNode = ref<DormTreeNode | null>(null)

const rooms = ref<RoomOut[]>([])
const roomsLoading = ref(false)
const roomTotal = ref(0)
const roomPage = ref(1)
const roomPageSize = ref(20)
const roomKeyword = ref('')

const beds = ref<BedOut[]>([])
const bedsLoading = ref(false)
const bedRoom = ref<RoomOut | null>(null)
const bedDialogVisible = ref(false)

const areaDialogVisible = ref(false)
const buildingDialogVisible = ref(false)
const floorDialogVisible = ref(false)
const roomDialogVisible = ref(false)
const bedCreateDialogVisible = ref(false)

const areaFormRef = ref<FormInstance>()
const buildingFormRef = ref<FormInstance>()
const floorFormRef = ref<FormInstance>()
const roomFormRef = ref<FormInstance>()
const bedFormRef = ref<FormInstance>()

const areaEditingId = ref<number | null>(null)
const buildingEditingId = ref<number | null>(null)
const floorEditingId = ref<number | null>(null)
const roomEditingId = ref<number | null>(null)

const areaForm = reactive({
  area_code: '',
  area_name: '',
  address: '',
  status: 'active',
})
const buildingForm = reactive({
  area_id: undefined as number | undefined,
  building_code: '',
  building_name: '',
  total_floors: undefined as number | undefined,
  gender_policy: 'any',
  status: 'active',
})
const floorForm = reactive({
  building_id: undefined as number | undefined,
  floor_no: 1,
  floor_name: '',
  gender_policy: 'any',
  status: 'active',
})
const roomForm = reactive({
  floor_id: undefined as number | undefined,
  room_no: '',
  room_type: 'standard',
  capacity: 4,
  gender_policy: 'any',
  status: 'active',
  bed_count: 4,
  bed_no_prefix: 'B',
})
const bedForm = reactive({
  bed_no: '',
  operational_status: 'active',
  description: '',
})

const areaRules: FormRules = {
  area_code: [{ required: true, message: '请输入区域编码', trigger: 'blur' }],
  area_name: [{ required: true, message: '请输入区域名称', trigger: 'blur' }],
}
const buildingRules: FormRules = {
  area_id: [{ required: true, message: '请选择区域', trigger: 'change' }],
  building_code: [{ required: true, message: '请输入楼栋编码', trigger: 'blur' }],
  building_name: [{ required: true, message: '请输入楼栋名称', trigger: 'blur' }],
}
const floorRules: FormRules = {
  building_id: [{ required: true, message: '请选择楼栋', trigger: 'change' }],
  floor_no: [{ required: true, message: '请输入楼层号', trigger: 'blur' }],
}
const roomRules: FormRules = {
  floor_id: [{ required: true, message: '请选择楼层', trigger: 'change' }],
  room_no: [{ required: true, message: '请输入房间号', trigger: 'blur' }],
  capacity: [{ required: true, message: '请输入容量', trigger: 'blur' }],
}
const bedRules: FormRules = {
  bed_no: [{ required: true, message: '请输入床位号', trigger: 'blur' }],
}

const genderOptions = [
  { label: '不限', value: 'any' },
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
]
const bedStatusMap: Record<string, { label: string; type: 'success' | 'warning' | 'info' | 'danger' }> = {
  active: { label: '可用', type: 'success' },
  maintenance: { label: '维修', type: 'warning' },
  disabled: { label: '停用', type: 'info' },
}

async function loadTree(): Promise<void> {
  treeLoading.value = true
  try {
    treeData.value = await fetchDormTree(true)
  } catch (error) {
    notifyError(error)
  } finally {
    treeLoading.value = false
  }
}

function nodeLabel(node: DormTreeNode): string {
  const badge = node.status === 'active' ? '' : '（停用）'
  return `${node.name}${badge}`
}

function onNodeClick(node: DormTreeNode): void {
  selectedNode.value = node
  if (node.node_type === 'floor') {
    void loadRooms({ floor_id: node.id })
  } else if (node.node_type === 'building') {
    void loadRooms({ building_id: node.id })
  } else if (node.node_type === 'area') {
    void loadRooms({})
  } else if (node.node_type === 'room') {
    // BUG-003: fetch the real room then open beds. Never send floor_id=0
    // (backend Query ge=1 rejects it with 422 "Request validation failed").
    void openBedsForNode(node)
  }
}

async function loadRooms(params: {
  floor_id?: number
  building_id?: number
}): Promise<void> {
  roomsLoading.value = true
  try {
    const data = await listRooms({
      page: roomPage.value,
      page_size: roomPageSize.value,
      keyword: roomKeyword.value || undefined,
      ...params,
    })
    rooms.value = data.items
    roomTotal.value = data.total
  } catch (error) {
    notifyError(error)
  } finally {
    roomsLoading.value = false
  }
}

function openAreaCreate(): void {
  areaEditingId.value = null
  Object.assign(areaForm, { area_code: '', area_name: '', address: '', status: 'active' })
  areaDialogVisible.value = true
}

function openAreaEdit(node: DormTreeNode): void {
  areaEditingId.value = node.id
  Object.assign(areaForm, {
    area_code: node.code,
    area_name: node.name,
    address: String(node.extra.address ?? ''),
    status: node.status,
  })
  areaDialogVisible.value = true
}

async function onAreaSubmit(): Promise<void> {
  if (!areaFormRef.value) return
  await areaFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload = {
        area_code: areaForm.area_code,
        area_name: areaForm.area_name,
        address: areaForm.address || null,
        status: areaForm.status,
      }
      if (areaEditingId.value == null) {
        await createArea(payload)
        ElMessage.success('区域已创建')
      } else {
        await updateArea(areaEditingId.value, payload)
        ElMessage.success('区域已更新')
      }
      areaDialogVisible.value = false
      await loadTree()
    } catch (error) {
      notifyError(error)
    }
  })
}

function resolveAreaIdForBuilding(): number | undefined {
  if (selectedNode.value?.node_type === 'area') return selectedNode.value.id
  return undefined
}

function openBuildingCreate(): void {
  buildingEditingId.value = null
  Object.assign(buildingForm, {
    area_id: resolveAreaIdForBuilding(),
    building_code: '',
    building_name: '',
    total_floors: undefined,
    gender_policy: 'any',
    status: 'active',
  })
  buildingDialogVisible.value = true
}

function openBuildingEditFromSelected(): void {
  if (!selectedNode.value || selectedNode.value.node_type !== 'building') return
  const areaId = resolveAreaIdForBuilding()
  if (areaId == null) {
    // selected building's area: walk tree
    for (const area of treeData.value) {
      if (area.children.some((b) => b.id === selectedNode.value!.id)) {
        openBuildingEdit(selectedNode.value, area.id)
        return
      }
    }
    ElMessage.warning('无法确定楼栋所属区域')
    return
  }
  openBuildingEdit(selectedNode.value, areaId)
}

function openBuildingEdit(node: DormTreeNode, areaId: number): void {
  buildingEditingId.value = node.id
  Object.assign(buildingForm, {
    area_id: areaId,
    building_code: node.code,
    building_name: node.name,
    total_floors: (node.extra.total_floors as number) ?? undefined,
    gender_policy: String(node.extra.gender_policy ?? 'any'),
    status: node.status,
  })
  buildingDialogVisible.value = true
}

async function onBuildingSubmit(): Promise<void> {
  if (!buildingFormRef.value) return
  await buildingFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload = {
        area_id: buildingForm.area_id!,
        building_code: buildingForm.building_code,
        building_name: buildingForm.building_name,
        total_floors: buildingForm.total_floors ?? null,
        gender_policy: buildingForm.gender_policy,
        status: buildingForm.status,
      }
      if (buildingEditingId.value == null) {
        await createBuilding(payload)
        ElMessage.success('楼栋已创建')
      } else {
        await updateBuilding(buildingEditingId.value, payload)
        ElMessage.success('楼栋已更新')
      }
      buildingDialogVisible.value = false
      await loadTree()
    } catch (error) {
      notifyError(error)
    }
  })
}

function openFloorEdit(node: DormTreeNode): void {
  floorEditingId.value = node.id
  Object.assign(floorForm, {
    building_id: undefined, // keep existing building; not editable here
    floor_no: Number(node.code) || 1,
    floor_name: node.name,
    gender_policy: String(node.extra.gender_policy ?? 'any'),
    status: node.status,
  })
  floorDialogVisible.value = true
}

function openFloorCreate(): void {
  floorEditingId.value = null
  Object.assign(floorForm, {
    building_id: selectedNode.value?.node_type === 'building' ? selectedNode.value.id : undefined,
    floor_no: 1,
    floor_name: '',
    gender_policy: 'any',
    status: 'active',
  })
  floorDialogVisible.value = true
}

async function onFloorSubmit(): Promise<void> {
  if (!floorFormRef.value) return
  await floorFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (floorEditingId.value == null) {
        await createFloor({
          building_id: floorForm.building_id!,
          floor_no: floorForm.floor_no,
          floor_name: floorForm.floor_name || null,
          gender_policy: floorForm.gender_policy,
          status: floorForm.status,
        })
        ElMessage.success('楼层已创建')
      } else {
        await updateFloor(floorEditingId.value, {
          floor_no: floorForm.floor_no,
          floor_name: floorForm.floor_name || null,
          gender_policy: floorForm.gender_policy,
          status: floorForm.status,
        })
        ElMessage.success('楼层已更新')
      }
      floorDialogVisible.value = false
      await loadTree()
    } catch (error) {
      notifyError(error)
    }
  })
}

function openRoomCreate(): void {
  roomEditingId.value = null
  Object.assign(roomForm, {
    floor_id: selectedNode.value?.node_type === 'floor' ? selectedNode.value.id : undefined,
    room_no: '',
    room_type: 'standard',
    capacity: 4,
    gender_policy: 'any',
    status: 'active',
    bed_count: 4,
    bed_no_prefix: 'B',
  })
  roomDialogVisible.value = true
}

async function openRoomEditFromNode(node: DormTreeNode): Promise<void> {
  try {
    const room = await fetchRoom(node.id)
    openRoomEdit(room)
  } catch (error) {
    notifyError(error, '加载房间详情失败')
  }
}

function openRoomEdit(row: RoomOut): void {
  roomEditingId.value = row.id
  Object.assign(roomForm, {
    floor_id: row.floor_id,
    room_no: row.room_no,
    room_type: row.room_type,
    capacity: row.capacity,
    gender_policy: row.gender_policy,
    status: row.status,
    bed_count: row.bed_count,
    bed_no_prefix: 'B',
  })
  roomDialogVisible.value = true
}

async function onRoomSubmit(): Promise<void> {
  if (!roomFormRef.value) return
  await roomFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (roomEditingId.value == null) {
        await createRoom({
          floor_id: roomForm.floor_id!,
          room_no: roomForm.room_no,
          room_type: roomForm.room_type,
          capacity: roomForm.capacity,
          gender_policy: roomForm.gender_policy,
          status: roomForm.status,
          bed_count: roomForm.bed_count,
          bed_no_prefix: roomForm.bed_no_prefix,
        })
        ElMessage.success('房间已创建')
      } else {
        await updateRoom(roomEditingId.value, {
          room_no: roomForm.room_no,
          room_type: roomForm.room_type,
          capacity: roomForm.capacity,
          gender_policy: roomForm.gender_policy,
          status: roomForm.status,
        })
        ElMessage.success('房间已更新')
      }
      roomDialogVisible.value = false
      await loadTree()
      if (selectedNode.value?.node_type === 'floor') {
        await loadRooms({ floor_id: selectedNode.value.id })
      }
    } catch (error) {
      notifyError(error)
    }
  })
}

async function openBedsForNode(node: DormTreeNode): Promise<void> {
  try {
    const room = await fetchRoom(node.id)
    await openBeds(room)
  } catch (error) {
    notifyError(error, '加载房间详情失败')
  }
}

async function openBeds(row: RoomOut): Promise<void> {
  bedRoom.value = row
  bedDialogVisible.value = true
  bedsLoading.value = true
  try {
    beds.value = await listRoomBeds(row.id)
  } catch (error) {
    notifyError(error)
  } finally {
    bedsLoading.value = false
  }
}

const bedEditingId = ref<number | null>(null)

function openBedEdit(row: BedOut): void {
  bedEditingId.value = row.id
  Object.assign(bedForm, {
    bed_no: row.bed_no,
    operational_status: row.operational_status,
    description: row.description ?? '',
  })
  bedCreateDialogVisible.value = true
}

async function onDeleteBed(row: BedOut): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除床位 ${row.bed_no} 吗？存在业务关联时将无法删除。`, '二次确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteDormResource('bed', row.id)
    ElMessage.success('床位已删除')
    if (bedRoom.value) beds.value = await listRoomBeds(bedRoom.value.id)
    await loadTree()
  } catch (error) {
    notifyError(error)
  }
}

function openBedCreate(): void {
  bedEditingId.value = null
  Object.assign(bedForm, { bed_no: '', operational_status: 'active', description: '' })
  bedCreateDialogVisible.value = true
}

async function onBedSubmit(): Promise<void> {
  if (!bedFormRef.value || !bedRoom.value) return
  await bedFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (bedEditingId.value == null) {
        await createBed(bedRoom.value!.id, {
          bed_no: bedForm.bed_no,
          operational_status: bedForm.operational_status,
          description: bedForm.description || null,
        })
        ElMessage.success('床位已创建')
      } else {
        await updateBed(bedEditingId.value, {
          bed_no: bedForm.bed_no,
          description: bedForm.description || null,
        })
        ElMessage.success('床位已更新')
      }
      bedCreateDialogVisible.value = false
      beds.value = await listRoomBeds(bedRoom.value!.id)
      await loadTree()
    } catch (error) {
      notifyError(error)
    }
  })
}

async function onBedAction(bed: BedOut, action: 'enable' | 'disable' | 'maintenance'): Promise<void> {
  try {
    await setBedStatus(bed.id, action)
    ElMessage.success('床位状态已更新')
    if (bedRoom.value) {
      beds.value = await listRoomBeds(bedRoom.value.id)
    }
    await loadTree()
  } catch (error) {
    notifyError(error)
  }
}

async function onDeleteNode(node: DormTreeNode): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除「${node.name}」吗？存在业务关联时将无法删除。`,
      '二次确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await deleteDormResource(node.node_type as 'area' | 'building' | 'floor' | 'room', node.id)
    ElMessage.success('已删除')
    selectedNode.value = null
    await loadTree()
    await loadRooms({})
  } catch (error) {
    notifyError(error)
  }
}

async function onDeleteRoom(row: RoomOut): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除房间 ${row.room_no} 吗？`, '二次确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteDormResource('room', row.id)
    ElMessage.success('已删除')
    await loadRooms(
      selectedNode.value?.node_type === 'floor'
        ? { floor_id: selectedNode.value.id }
        : {}
    )
  } catch (error) {
    notifyError(error)
  }
}

async function onRevealAccessCode(room: RoomOut): Promise<void> {
  try {
    const data = await revealRoomAccessCode(room.id)
    if (data.access_code == null) {
      ElMessage.info('该房间未设置门禁密码')
      return
    }
    await ElMessageBox.alert(`门禁密码：${data.access_code}`, '门禁密码（请勿外传）', {
      confirmButtonText: '关闭',
    })
  } catch (error) {
    notifyError(error)
  }
}

async function onEditAccessCode(room: RoomOut): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入门禁密码（字符串，可含前导零；留空表示清除）',
      `设置门禁密码 - ${room.room_no}`,
      {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputType: 'password',
        inputValue: '',
      }
    )
    await setRoomAccessCode(room.id, value === '' ? null : value)
    ElMessage.success('门禁密码已更新')
    await loadRooms(
      selectedNode.value?.node_type === 'floor'
        ? { floor_id: selectedNode.value.id }
        : {}
    )
  } catch (error) {
    if (error !== 'cancel') notifyError(error)
  }
}

// ---- FEAT-002 remediation: room type dictionary + room Excel import UI ----
const roomTypes = ref<RoomTypeRow[]>([])
const roomTypesDialogVisible = ref(false)
const roomTypesLoading = ref(false)
const roomTypeDialogVisible = ref(false)
const roomTypeEditingId = ref<number | null>(null)
const roomTypeForm = reactive({
  type_code: '',
  type_name: '',
  default_capacity: 4,
  description: '',
  status: 'active',
})

const roomImportDialogVisible = ref(false)
const roomImportFile = ref<File | null>(null)
const roomImportRows = ref<ImportRow[]>([])
const roomImportSummary = ref<{ total?: number; create?: number; error?: number; created?: number; failed?: number } | null>(null)
const roomImportLoading = ref(false)
const roomImportPhase = ref<'idle' | 'preview' | 'done'>('idle')

async function loadRoomTypes(): Promise<void> {
  roomTypesLoading.value = true
  try {
    roomTypes.value = (await listRoomTypes()) as RoomTypeRow[]
  } catch (error) {
    notifyError(error)
  } finally {
    roomTypesLoading.value = false
  }
}

function openRoomTypes(): void {
  roomTypesDialogVisible.value = true
  void loadRoomTypes()
}

function openRoomTypeCreate(): void {
  roomTypeEditingId.value = null
  Object.assign(roomTypeForm, {
    type_code: '',
    type_name: '',
    default_capacity: 4,
    description: '',
    status: 'active',
  })
  roomTypeDialogVisible.value = true
}

function openRoomTypeEdit(row: RoomTypeRow): void {
  roomTypeEditingId.value = row.id
  Object.assign(roomTypeForm, {
    type_code: row.type_code,
    type_name: row.type_name,
    default_capacity: row.default_capacity,
    description: row.description ?? '',
    status: row.status,
  })
  roomTypeDialogVisible.value = true
}

async function onRoomTypeSubmit(): Promise<void> {
  if (!roomTypeForm.type_code.trim() || !roomTypeForm.type_name.trim()) {
    ElMessage.warning('请填写类型编码和名称')
    return
  }
  try {
    if (roomTypeEditingId.value == null) {
      await createRoomType({
        type_code: roomTypeForm.type_code.trim(),
        type_name: roomTypeForm.type_name.trim(),
        default_capacity: roomTypeForm.default_capacity,
        description: roomTypeForm.description || null,
        status: roomTypeForm.status,
      })
      ElMessage.success('房型已创建')
    } else {
      await updateRoomType(roomTypeEditingId.value, {
        type_name: roomTypeForm.type_name.trim(),
        default_capacity: roomTypeForm.default_capacity,
        description: roomTypeForm.description || null,
        status: roomTypeForm.status,
      })
      ElMessage.success('房型已更新（不会自动修改已有房间容量）')
    }
    roomTypeDialogVisible.value = false
    await loadRoomTypes()
  } catch (error) {
    notifyError(error)
  }
}

async function onRoomTypeDelete(row: RoomTypeRow): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除房型「${row.type_name}」吗？已被房间引用时只能停用。`,
      '二次确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await deleteRoomType(row.id)
    ElMessage.success('房型已删除')
    await loadRoomTypes()
  } catch (error) {
    notifyError(error)
  }
}

async function onRoomTypeDisable(row: RoomTypeRow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定停用房型「${row.type_name}」吗？已有房间容量不受影响。`, '停用房型', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await disableRoomType(row.id)
    ElMessage.success('房型已停用')
    await loadRoomTypes()
  } catch (error) {
    notifyError(error)
  }
}

function openRoomImport(): void {
  roomImportDialogVisible.value = true
  roomImportFile.value = null
  roomImportRows.value = []
  roomImportSummary.value = null
  roomImportPhase.value = 'idle'
}

function onRoomImportUploadChange(uploadFile: { raw?: File }): void {
  if (uploadFile?.raw) onRoomImportFileChange(uploadFile.raw)
}

function onRoomImportFileChange(file: File): void {
  roomImportFile.value = file
  roomImportRows.value = []
  roomImportSummary.value = null
  roomImportPhase.value = 'idle'
}

async function onDownloadRoomTemplate(): Promise<void> {
  try {
    const blob = await downloadRoomImportTemplate()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'room_import_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    notifyError(error)
  }
}

async function onRoomImportPreview(): Promise<void> {
  if (!roomImportFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }
  roomImportLoading.value = true
  try {
    const data = (await previewRoomImport(roomImportFile.value)) as {
      rows: ImportRow[]
      summary: Record<string, number>
    }
    roomImportRows.value = data.rows
    roomImportSummary.value = data.summary
    roomImportPhase.value = 'preview'
  } catch (error) {
    notifyError(error)
  } finally {
    roomImportLoading.value = false
  }
}

async function onRoomImportCommit(): Promise<void> {
  if (!roomImportFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }
  try {
    await ElMessageBox.confirm('确认提交房间导入吗？已存在房间不会被覆盖。', '确认导入', {
      type: 'warning',
    })
  } catch {
    return
  }
  roomImportLoading.value = true
  try {
    const data = (await commitRoomImport(roomImportFile.value)) as {
      rows: ImportRow[]
      summary: { created: number; failed: number; total: number }
    }
    roomImportRows.value = data.rows
    roomImportSummary.value = data.summary
    roomImportPhase.value = 'done'
    ElMessage.success(`导入完成：成功 ${data.summary.created}，失败 ${data.summary.failed}`)
    await loadTree()
  } catch (error) {
    notifyError(error)
  } finally {
    roomImportLoading.value = false
  }
}

onMounted(async () => {
  await loadTree()
  await loadRooms({})
  await loadRoomTypes()
})
</script>

<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card shadow="never" class="tree-card">
        <div class="toolbar">
          <span class="title">宿舍层级</span>
          <div class="spacer" />
          <el-button
            v-if="auth.hasPermission('dorm:create')"
            size="small"
            @click="openAreaCreate"
          >
            新建区域
          </el-button>
        </div>
        <el-tree
          v-loading="treeLoading"
          :data="treeData"
          node-key="id"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <el-tag size="small" :type="data.node_type === 'area' ? 'primary' : data.node_type === 'building' ? 'success' : data.node_type === 'floor' ? 'warning' : 'info'" effect="plain">
                {{ data.node_type === 'area' ? '区域' : data.node_type === 'building' ? '楼' : data.node_type === 'floor' ? '层' : '房' }}
              </el-tag>
              <span class="node-name">{{ nodeLabel(data) }}</span>
              <span v-if="data.node_type === 'room'" class="node-meta">
                {{ data.extra.bed_count }}床
              </span>
            </span>
          </template>
        </el-tree>
        <div class="tree-actions">
          <el-button
            v-if="auth.hasPermission('dorm:create') && selectedNode?.node_type === 'area'"
            size="small"
            @click="openBuildingCreate"
          >
            新建楼栋
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:create') && selectedNode?.node_type === 'building'"
            size="small"
            @click="openFloorCreate"
          >
            新建楼层
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:create') && selectedNode?.node_type === 'floor'"
            size="small"
            type="primary"
            @click="openRoomCreate"
          >
            新建房间
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update') && selectedNode?.node_type === 'area'"
            size="small"
            @click="selectedNode && openAreaEdit(selectedNode)"
          >
            编辑区域
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update') && selectedNode?.node_type === 'building'"
            size="small"
            @click="openBuildingEditFromSelected"
          >
            编辑楼栋
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update') && selectedNode?.node_type === 'floor'"
            size="small"
            @click="selectedNode && openFloorEdit(selectedNode)"
          >
            编辑楼层
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update') && selectedNode?.node_type === 'room'"
            size="small"
            @click="selectedNode && openRoomEditFromNode(selectedNode)"
          >
            编辑房间
          </el-button>

            <el-button
              v-if="auth.hasPermission('dorm:update') && selectedNode"
              type="danger"
              size="small"
              @click="onDeleteNode(selectedNode)"
            >
              删除节点
            </el-button>
        </div>
      </el-card>
    </el-col>

    <el-col :span="16">
      <el-card shadow="never">
        <div class="toolbar">
          <el-input
            v-model="roomKeyword"
            placeholder="搜索房间号"
            clearable
            style="width: 180px"
            @keyup.enter="selectedNode?.node_type === 'floor' ? loadRooms({ floor_id: selectedNode.id }) : loadRooms({})"
            @clear="selectedNode?.node_type === 'floor' ? loadRooms({ floor_id: selectedNode.id }) : loadRooms({})"
          />
          <el-button
            type="primary"
            @click="selectedNode?.node_type === 'floor' ? loadRooms({ floor_id: selectedNode.id }) : selectedNode?.node_type === 'building' ? loadRooms({ building_id: selectedNode.id }) : loadRooms({})"
          >
            查询
          </el-button>
          <div class="spacer" />
          <el-button
            v-if="auth.hasPermission('dorm:view')"
            @click="openRoomTypes"
          >
            房型维护
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:create')"
            @click="openRoomImport"
          >
            批量导入
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:create')"
            type="primary"
            @click="openRoomCreate"
          >
            新建房间
          </el-button>
        </div>

        <el-table :data="rooms" v-loading="roomsLoading" stripe>
          <el-table-column prop="room_no" label="房间号" width="100" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              {{ roomTypes.find((t) => t.type_code === row.room_type)?.type_name || row.room_type }}
            </template>
          </el-table-column>
          <el-table-column label="容量" width="80">
            <template #default="{ row }">{{ row.capacity }}</template>
          </el-table-column>
          <el-table-column label="床位" width="100">
            <template #default="{ row }">
              {{ row.active_bed_count }}/{{ row.bed_count }}
            </template>
          </el-table-column>
          <el-table-column label="性别政策" width="100">
            <template #default="{ row }">
              {{ row.gender_policy === 'male' ? '男' : row.gender_policy === 'female' ? '女' : '不限' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                {{ row.status === 'active' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openBeds(row)">床位</el-button>
              <el-button
                v-if="auth.hasPermission('dorm:update')"
                link
                type="primary"
                @click="openRoomEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="auth.hasPermission('dorm:access_code:view')"
                link
                type="warning"
                @click="onRevealAccessCode(row)"
              >
                门禁
              </el-button>
              <el-button
                v-if="auth.hasPermission('dorm:access_code:update')"
                link
                type="warning"
                @click="onEditAccessCode(row)"
              >
                设密
              </el-button>
              <el-button
                v-if="auth.hasPermission('dorm:update')"
                link
                type="danger"
                @click="onDeleteRoom(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          class="pager"
          layout="total, prev, pager, next"
          :total="roomTotal"
          v-model:current-page="roomPage"
          v-model:page-size="roomPageSize"
          @current-change="loadRooms({})"
        />
      </el-card>
    </el-col>
  </el-row>

  <!-- Area -->
  <el-dialog v-model="areaDialogVisible" :title="areaEditingId == null ? '新建区域' : '编辑区域'" width="480px">
    <el-form ref="areaFormRef" :model="areaForm" :rules="areaRules" label-width="96px">
      <el-form-item label="区域编码" prop="area_code">
        <el-input v-model="areaForm.area_code" />
      </el-form-item>
      <el-form-item label="区域名称" prop="area_name">
        <el-input v-model="areaForm.area_name" />
      </el-form-item>
      <el-form-item label="地址">
        <el-input v-model="areaForm.address" />
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="areaForm.status" active-value="active" inactive-value="disabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="areaDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onAreaSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- Building -->
  <el-dialog v-model="buildingDialogVisible" :title="buildingEditingId == null ? '新建楼栋' : '编辑楼栋'" width="480px">
    <el-form ref="buildingFormRef" :model="buildingForm" :rules="buildingRules" label-width="96px">
      <el-form-item label="所属区域" prop="area_id">
        <el-select v-model="buildingForm.area_id" style="width: 100%">
          <el-option
            v-for="area in treeData"
            :key="area.id"
            :label="area.name"
            :value="area.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="楼栋编码" prop="building_code">
        <el-input v-model="buildingForm.building_code" />
      </el-form-item>
      <el-form-item label="楼栋名称" prop="building_name">
        <el-input v-model="buildingForm.building_name" />
      </el-form-item>
      <el-form-item label="总楼层">
        <el-input-number v-model="buildingForm.total_floors" :min="1" :max="200" />
      </el-form-item>
      <el-form-item label="性别政策">
        <el-select v-model="buildingForm.gender_policy" style="width: 100%">
          <el-option v-for="g in genderOptions" :key="g.value" :label="g.label" :value="g.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="buildingForm.status" active-value="active" inactive-value="disabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="buildingDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onBuildingSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- Floor -->
  <el-dialog v-model="floorDialogVisible" :title="floorEditingId == null ? '新建楼层' : '编辑楼层'" width="480px">
    <el-form ref="floorFormRef" :model="floorForm" :rules="floorRules" label-width="96px">
      <el-form-item label="楼层号" prop="floor_no">
        <el-input-number v-model="floorForm.floor_no" :min="-5" :max="200" />
      </el-form-item>
      <el-form-item label="楼层名称">
        <el-input v-model="floorForm.floor_name" placeholder="如：一层" />
      </el-form-item>
      <el-form-item label="性别政策">
        <el-select v-model="floorForm.gender_policy" style="width: 100%">
          <el-option v-for="g in genderOptions" :key="g.value" :label="g.label" :value="g.value" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="floorDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onFloorSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- Room -->
  <el-dialog v-model="roomDialogVisible" :title="roomEditingId == null ? '新建房间' : '编辑房间'" width="520px">
    <el-form ref="roomFormRef" :model="roomForm" :rules="roomRules" label-width="110px">
      <el-form-item label="房间号" prop="room_no">
        <el-input v-model="roomForm.room_no" />
      </el-form-item>
      <el-form-item label="房间类型">
        <el-select v-model="roomForm.room_type" style="width: 100%">
          <el-option
            v-for="t in roomTypes.filter((x) => x.status === 'active')"
            :key="t.type_code"
            :label="t.type_name"
            :value="t.type_code"
          />
          <el-option
            v-if="!roomTypes.some((x) => x.type_code === roomForm.room_type)"
            :label="roomForm.room_type"
            :value="roomForm.room_type"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="核定容量" prop="capacity">
        <el-input-number v-model="roomForm.capacity" :min="1" :max="20" />
      </el-form-item>
      <el-form-item v-if="roomEditingId == null" label="初始床位数">
        <el-input-number v-model="roomForm.bed_count" :min="0" :max="20" />
      </el-form-item>
      <el-form-item v-if="roomEditingId == null" label="床位号前缀">
        <el-input v-model="roomForm.bed_no_prefix" maxlength="8" />
      </el-form-item>
      <el-form-item label="性别政策">
        <el-select v-model="roomForm.gender_policy" style="width: 100%">
          <el-option v-for="g in genderOptions" :key="g.value" :label="g.label" :value="g.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="roomForm.status" active-value="active" inactive-value="disabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="roomDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onRoomSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- Beds -->
  <el-dialog v-model="bedDialogVisible" :title="`房间 ${bedRoom?.room_no ?? ''} 床位`" width="720px">
    <div class="toolbar">
      <el-button
        v-if="auth.hasPermission('bed:manage')"
        type="primary"
        size="small"
        @click="openBedCreate"
      >
        新增床位
      </el-button>
    </div>
    <el-table :data="beds" v-loading="bedsLoading" size="small" stripe>
      <el-table-column prop="bed_no" label="床位号" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="bedStatusMap[row.operational_status]?.type || 'info'">
            {{ bedStatusMap[row.operational_status]?.label || row.operational_status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="占用" width="120">
        <template #default="{ row }">
          {{ row.occupied ? '已入住' : row.reserved ? '已预留' : '空闲' }}
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="70" />
      <el-table-column prop="description" label="备注" min-width="120">
        <template #default="{ row }">{{ row.description || '—' }}</template>
      </el-table-column>
      <el-table-column v-if="auth.hasPermission('bed:manage')" label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openBedEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="onDeleteBed(row)">删除</el-button>
          <el-button
            v-if="row.operational_status !== 'active'"
            link
            type="success"
            @click="onBedAction(row, 'enable')"
          >
            启用
          </el-button>
          <el-button
            v-if="row.operational_status !== 'maintenance'"
            link
            type="warning"
            @click="onBedAction(row, 'maintenance')"
          >
            维修
          </el-button>
          <el-button
            v-if="row.operational_status !== 'disabled'"
            link
            type="info"
            @click="onBedAction(row, 'disable')"
          >
            停用
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>

  <!-- Bed create -->
  <el-dialog v-model="bedCreateDialogVisible" :title="bedEditingId == null ? '新增床位' : '编辑床位'" width="420px" append-to-body>
    <el-form ref="bedFormRef" :model="bedForm" :rules="bedRules" label-width="96px">
      <el-form-item label="床位号" prop="bed_no">
        <el-input v-model="bedForm.bed_no" />
      </el-form-item>
      <el-form-item label="初始状态">
        <el-select v-model="bedForm.operational_status" style="width: 100%">
          <el-option label="可用" value="active" />
          <el-option label="维修" value="maintenance" />
          <el-option label="停用" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="bedForm.description" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="bedCreateDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onBedSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- FEAT-002: room type dictionary -->
  <el-dialog v-model="roomTypesDialogVisible" title="房型维护" width="720px">
    <div class="toolbar">
      <el-button
        v-if="auth.hasPermission('dorm:create')"
        type="primary"
        size="small"
        @click="openRoomTypeCreate"
      >
        新建房型
      </el-button>
    </div>
    <el-table :data="roomTypes" v-loading="roomTypesLoading" stripe>
      <el-table-column prop="type_code" label="编码" width="120" />
      <el-table-column prop="type_name" label="名称" width="140" />
      <el-table-column prop="default_capacity" label="默认容量" width="100" />
      <el-table-column prop="description" label="备注" min-width="140" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button
            v-if="auth.hasPermission('dorm:update')"
            link
            type="primary"
            @click="openRoomTypeEdit(row)"
          >
            编辑
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update') && row.status === 'active'"
            link
            type="danger"
            @click="onRoomTypeDisable(row)"
          >
            停用
          </el-button>
          <el-button
            v-if="auth.hasPermission('dorm:update')"
            link
            type="danger"
            @click="onRoomTypeDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>

  <el-dialog v-model="roomTypeDialogVisible" :title="roomTypeEditingId == null ? '新建房型' : '编辑房型'" width="480px">
    <el-form label-width="110px">
      <el-form-item label="类型编码" required>
        <el-input v-model="roomTypeForm.type_code" :disabled="roomTypeEditingId != null" maxlength="32" />
      </el-form-item>
      <el-form-item label="类型名称" required>
        <el-input v-model="roomTypeForm.type_name" maxlength="64" />
      </el-form-item>
      <el-form-item label="默认容量">
        <el-input-number v-model="roomTypeForm.default_capacity" :min="1" :max="20" />
        <div class="form-tip">仅用于新建房间预填，不会自动修改已有房间容量</div>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="roomTypeForm.description" type="textarea" :rows="2" maxlength="2000" />
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="roomTypeForm.status" active-value="active" inactive-value="disabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="roomTypeDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="onRoomTypeSubmit">保存</el-button>
    </template>
  </el-dialog>

  <!-- FEAT-002: room Excel import -->
  <el-dialog v-model="roomImportDialogVisible" title="房间批量导入" width="860px">
    <div class="toolbar">
      <el-button size="small" @click="onDownloadRoomTemplate">下载模板</el-button>
      <el-upload
        :auto-upload="false"
        :limit="1"
        :on-change="onRoomImportUploadChange"
        :show-file-list="false"
        accept=".xlsx,.xlsm"
      >
        <el-button size="small">选择 Excel</el-button>
      </el-upload>
      <el-button
        type="primary"
        size="small"
        :loading="roomImportLoading"
        :disabled="!roomImportFile"
        @click="onRoomImportPreview"
      >
        上传预览
      </el-button>
      <el-button
        type="success"
        size="small"
        :loading="roomImportLoading"
        :disabled="roomImportPhase !== 'preview'"
        @click="onRoomImportCommit"
      >
        确认提交
      </el-button>
    </div>
    <el-alert
      v-if="roomImportSummary"
      type="info"
      :closable="false"
      style="margin-bottom: 12px"
      :title="`总计 ${roomImportSummary.total ?? 0} 行 · 待创建 ${roomImportSummary.create ?? 0} · 错误 ${roomImportSummary.error ?? 0}` + (roomImportPhase === 'done' ? ` · 已创建 ${roomImportSummary.created ?? 0} · 失败 ${roomImportSummary.failed ?? 0}` : '')"
    />
    <el-table :data="roomImportRows" stripe max-height="360">
      <el-table-column prop="row" label="行号" width="70" />
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.action === 'create' ? 'success' : row.action === 'error' ? 'danger' : 'info'">
            {{ row.action === 'create' ? '待创建' : row.action === 'error' ? '错误' : row.action }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="说明" min-width="220" />
      <el-table-column label="房间号" width="100">
        <template #default="{ row }">{{ (row.data as Record<string, unknown>)?.room_no }}</template>
      </el-table-column>
      <el-table-column label="容量" width="80">
        <template #default="{ row }">{{ (row.data as Record<string, unknown>)?.capacity }}</template>
      </el-table-column>
      <el-table-column label="门禁密码" width="110">
        <template #default="{ row }">
          {{ (row.data as Record<string, unknown>)?.access_code ? '已填写' : '—' }}
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<style scoped>
.tree-card {
  min-height: 480px;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.title {
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.node-name {
  font-size: 13px;
}
.node-meta {
  color: #909399;
  font-size: 12px;
}
.tree-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
