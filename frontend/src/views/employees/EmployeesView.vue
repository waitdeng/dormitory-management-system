<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type UploadFile } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { notifyError } from '@/api/client'
import {
  commitEmployeeImport,
  createEmployee,
  downloadImportTemplate,
  exportEmployees,
  listEmployees,
  previewEmployeeImport,
  updateEmployee,
} from '@/api/employees'
import { startOffboarding, terminateEmployee } from '@/api/workflow'
import {
  createDepartment,
  fetchDepartmentTree,
  listDepartments,
  updateDepartment,
} from '@/api/departments'
import type {
  DepartmentOut,
  DepartmentTreeNode,
  EmployeeImportPreviewOut,
  EmployeeOut,
} from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const departmentId = ref<number | undefined>()
const employmentStatus = ref('')
const rows = ref<EmployeeOut[]>([])

const departments = ref<DepartmentOut[]>([])
const deptTree = ref<DepartmentTreeNode[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  employee_no: '',
  full_name: '',
  gender: '' as string,
  department_id: undefined as number | undefined,
  position: '',
  employment_type: '' as string,
  phone: '',
  join_date: '',
  employment_status: 'active',
  accommodation_required: true,
  shift_type: '' as string,
  notes: '',
})

const rules: FormRules = {
  employee_no: [
    { required: true, message: '请输入员工工号', trigger: 'blur' },
    { min: 1, max: 64, message: '长度 1-64', trigger: 'blur' },
  ],
  full_name: [{ required: true, message: '请输入员工姓名', trigger: 'blur' }],
  employment_status: [{ required: true, message: '请选择人事状态', trigger: 'change' }],
}

// Department management dialog
const deptListVisible = ref(false)
const deptFormVisible = ref(false)
const deptEditingId = ref<number | null>(null)
const deptFormRef = ref<FormInstance>()
const deptForm = reactive({
  department_code: '',
  department_name: '',
  parent_id: undefined as number | undefined,
  status: 'active',
})
const deptRules: FormRules = {
  department_code: [{ required: true, message: '请输入部门编码', trigger: 'blur' }],
  department_name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
}
const deptRows = ref<DepartmentOut[]>([])
const deptLoading = ref(false)

// Import dialog
const importDialogVisible = ref(false)
const importPreview = ref<EmployeeImportPreviewOut | null>(null)
const importFile = ref<File | null>(null)
const importSubmitting = ref(false)
const importLoading = ref(false)

const genderOptions = [
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
  { label: '其他', value: 'other' },
]
const employmentTypeOptions = [
  { label: '正式', value: 'full_time' },
  { label: '兼职', value: 'part_time' },
  { label: '合同', value: 'contract' },
  { label: '实习', value: 'intern' },
  { label: '外包', value: 'outsourced' },
]
const shiftOptions = [
  { label: '白班', value: 'day' },
  { label: '夜班', value: 'night' },
  { label: '轮班', value: 'rotating' },
  { label: '无', value: 'none' },
]
const statusOptions = [
  { label: '待入职', value: 'pending' },
  { label: '在职', value: 'active' },
  { label: '试用期', value: 'probation' },
  { label: '离职办理中', value: 'offboarding' },
  { label: '已离职', value: 'terminated' },
  { label: '已离职', value: 'resigned' },
  { label: '停职', value: 'suspended' },
]

const statusLabel: Record<string, string> = {
  pending: '待入职',
  active: '在职',
  probation: '试用期',
  offboarding: '离职办理中',
  terminated: '已离职',
  resigned: '已离职',
  suspended: '停职',
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listEmployees({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      department_id: departmentId.value,
      employment_status: employmentStatus.value || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    notifyError(error)
  } finally {
    loading.value = false
  }
}

async function loadDepartments(): Promise<void> {
  try {
    const data = await listDepartments({ page: 1, page_size: 100, status: 'active' })
    departments.value = data.items
    deptTree.value = await fetchDepartmentTree(false)
  } catch {
    departments.value = []
  }
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    employee_no: '',
    full_name: '',
    gender: '',
    department_id: undefined,
    position: '',
    employment_type: '',
    phone: '',
    join_date: '',
    employment_status: 'active',
    accommodation_required: true,
    shift_type: '',
    notes: '',
  })
  dialogVisible.value = true
}

function openEdit(row: EmployeeOut): void {
  editingId.value = row.id
  Object.assign(form, {
    employee_no: row.employee_no,
    full_name: row.full_name,
    gender: row.gender || '',
    department_id: row.department_id ?? undefined,
    position: row.position || '',
    employment_type: row.employment_type || '',
    phone: row.phone || '',
    join_date: row.join_date || '',
    employment_status: row.employment_status,
    accommodation_required: row.accommodation_required,
    shift_type: row.shift_type || '',
    notes: row.notes || '',
  })
  dialogVisible.value = true
}

async function onOffboard(row: EmployeeOut): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定对 ${row.full_name}（${row.employee_no}）发起离职办理吗？` +
        '系统会生成行政退宿待办，不会自动释放床位。',
      '发起离职',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
    const result = await startOffboarding(row.id, {})
    ElMessage.success(
      result.side_effects && (result.side_effects as { todo_id?: number }).todo_id
        ? '已发起离职，并生成退宿待办'
        : '已发起离职'
    )
    await load()
  } catch (error) {
    if (error !== 'cancel') notifyError(error)
  }
}

async function onTerminate(row: EmployeeOut): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定将 ${row.full_name}（${row.employee_no}）标记为已离职吗？` +
        '若尚未退宿，系统会产生“离职未退宿”预警，床位仍保持占用。',
      '确认离职',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
    const result = await terminateEmployee(row.id, {})
    ElMessage.success(
      result.alert_id ? '已确认离职，并产生离职未退宿预警' : '已确认离职'
    )
    await load()
  } catch (error) {
    if (error !== 'cancel') notifyError(error)
  }
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload = {
        employee_no: form.employee_no,
        full_name: form.full_name,
        gender: form.gender || null,
        department_id: form.department_id ?? null,
        position: form.position || null,
        employment_type: form.employment_type || null,
        phone: form.phone || null,
        join_date: form.join_date || null,
        employment_status: form.employment_status,
        accommodation_required: form.accommodation_required,
        shift_type: form.shift_type || null,
        notes: form.notes || null,
      }
      if (editingId.value == null) {
        await createEmployee(payload)
        ElMessage.success('员工已创建')
      } else {
        await updateEmployee(editingId.value, payload)
        ElMessage.success('员工已更新')
      }
      dialogVisible.value = false
      await load()
    } catch (error) {
      notifyError(error)
    }
  })
}

async function onExport(): Promise<void> {
  try {
    const blob = await exportEmployees({
      keyword: keyword.value || undefined,
      department_id: departmentId.value,
      employment_status: employmentStatus.value || undefined,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'employees_export.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    notifyError(error)
  }
}

async function onDownloadTemplate(): Promise<void> {
  try {
    const blob = await downloadImportTemplate()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'employee_import_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    notifyError(error)
  }
}

function onImportFileChange(file: UploadFile): void {
  importFile.value = file.raw ?? null
}

async function onImportPreview(): Promise<void> {
  if (!importFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }
  importLoading.value = true
  try {
    importPreview.value = await previewEmployeeImport(importFile.value)
  } catch (error) {
    importPreview.value = null
    notifyError(error)
  } finally {
    importLoading.value = false
  }
}

async function onImportCommit(): Promise<void> {
  if (!importPreview.value) return
  importSubmitting.value = true
  try {
    const result = await commitEmployeeImport(importPreview.value.import_job_id)
    ElMessage.success(
      `导入完成：新增 ${result.created_count}，更新 ${result.updated_count}，失败 ${result.failed_rows}`
    )
    importDialogVisible.value = false
    importPreview.value = null
    importFile.value = null
    await load()
  } catch (error) {
    notifyError(error)
  } finally {
    importSubmitting.value = false
  }
}

function openImportDialog(): void {
  importPreview.value = null
  importFile.value = null
  importDialogVisible.value = true
}

async function loadDeptList(): Promise<void> {
  deptLoading.value = true
  try {
    const data = await listDepartments({ page: 1, page_size: 100 })
    deptRows.value = data.items
  } catch (error) {
    notifyError(error)
  } finally {
    deptLoading.value = false
  }
}

function openDeptCreate(): void {
  deptEditingId.value = null
  Object.assign(deptForm, {
    department_code: '',
    department_name: '',
    parent_id: undefined,
    status: 'active',
  })
  deptFormVisible.value = true
}

function openDeptEdit(row: DepartmentOut): void {
  deptEditingId.value = row.id
  Object.assign(deptForm, {
    department_code: row.department_code,
    department_name: row.department_name,
    parent_id: row.parent_id ?? undefined,
    status: row.status,
  })
  deptFormVisible.value = true
}

async function onDeptSubmit(): Promise<void> {
  if (!deptFormRef.value) return
  await deptFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload = {
        department_code: deptForm.department_code,
        department_name: deptForm.department_name,
        parent_id: deptForm.parent_id ?? null,
        status: deptForm.status,
      }
      if (deptEditingId.value == null) {
        await createDepartment(payload)
        ElMessage.success('部门已创建')
      } else {
        await updateDepartment(deptEditingId.value, payload)
        ElMessage.success('部门已更新')
      }
      deptFormVisible.value = false
      await loadDeptList()
      await loadDepartments()
    } catch (error) {
      notifyError(error)
    }
  })
}

function openDeptManager(): void {
  deptListVisible.value = true
  void loadDeptList()
}

onMounted(async () => {
  await loadDepartments()
  await load()
})
</script>

<template>
  <div>
    <el-card shadow="never" class="block">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索工号 / 姓名"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-select
          v-model="departmentId"
          placeholder="部门"
          clearable
          style="width: 180px"
          @change="load"
        >
          <el-option
            v-for="d in departments"
            :key="d.id"
            :label="d.department_name"
            :value="d.id"
          />
        </el-select>
        <el-select
          v-model="employmentStatus"
          placeholder="人事状态"
          clearable
          style="width: 140px"
          @change="load"
        >
          <el-option
            v-for="s in statusOptions"
            :key="s.value"
            :label="s.label"
            :value="s.value"
          />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <div class="spacer" />
        <el-button @click="openDeptManager">部门管理</el-button>
        <el-button v-if="auth.hasPermission('employee:export')" @click="onExport">
          导出
        </el-button>
        <el-button
          v-if="auth.hasPermission('employee:import')"
          type="warning"
          @click="openImportDialog"
        >
          Excel 导入
        </el-button>
        <el-button
          v-if="auth.hasPermission('employee:create')"
          type="primary"
          @click="openCreate"
        >
          新建员工
        </el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="employee_no" label="工号" width="120" />
        <el-table-column prop="full_name" label="姓名" min-width="100" />
        <el-table-column label="性别" width="70">
          <template #default="{ row }">
            {{ row.gender === 'male' ? '男' : row.gender === 'female' ? '女' : row.gender === 'other' ? '其他' : '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="department_name" label="部门" min-width="120">
          <template #default="{ row }">{{ row.department_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="position" label="岗位" min-width="100">
          <template #default="{ row }">{{ row.position || '—' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="120">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="人事状态" width="110">
          <template #default="{ row }">
            <el-tag
              :type="
                row.employment_status === 'active'
                  ? 'success'
                  : row.employment_status === 'terminated'
                    ? 'danger'
                    : row.employment_status === 'offboarding'
                      ? 'warning'
                      : 'info'
              "
            >
              {{ statusLabel[row.employment_status] || row.employment_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="住宿" width="90">
          <template #default="{ row }">
            {{ row.accommodation_required ? '需要' : '不需要' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="auth.hasPermission('employee:update')"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="
                auth.hasPermission('employee:offboard') &&
                ['active', 'probation', 'pending'].includes(row.employment_status)
              "
              link
              type="warning"
              @click="onOffboard(row)"
            >
              发起离职
            </el-button>
            <el-button
              v-if="
                auth.hasPermission('employee:offboard') &&
                ['active', 'probation', 'pending', 'offboarding'].includes(row.employment_status)
              "
              link
              type="danger"
              @click="onTerminate(row)"
            >
              确认离职
            </el-button>
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

    <!-- Employee form -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId == null ? '新建员工' : '编辑员工'"
      width="640px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="工号" prop="employee_no">
              <el-input v-model="form.employee_no" :disabled="editingId != null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="full_name">
              <el-input v-model="form.full_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-select v-model="form.gender" clearable style="width: 100%">
                <el-option
                  v-for="g in genderOptions"
                  :key="g.value"
                  :label="g.label"
                  :value="g.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="部门">
              <el-select v-model="form.department_id" clearable style="width: 100%">
                <el-option
                  v-for="d in departments"
                  :key="d.id"
                  :label="d.department_name"
                  :value="d.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位">
              <el-input v-model="form.position" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="电话">
              <el-input v-model="form.phone" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入职日期">
              <el-date-picker
                v-model="form.join_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用工类型">
              <el-select v-model="form.employment_type" clearable style="width: 100%">
                <el-option
                  v-for="t in employmentTypeOptions"
                  :key="t.value"
                  :label="t.label"
                  :value="t.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="班次">
              <el-select v-model="form.shift_type" clearable style="width: 100%">
                <el-option
                  v-for="s in shiftOptions"
                  :key="s.value"
                  :label="s.label"
                  :value="s.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="人事状态" prop="employment_status">
              <el-select v-model="form.employment_status" style="width: 100%">
                <el-option
                  v-for="s in statusOptions"
                  :key="s.value"
                  :label="s.label"
                  :value="s.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="需要住宿">
              <el-switch v-model="form.accommodation_required" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.notes" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Import dialog -->
    <el-dialog v-model="importDialogVisible" title="Excel 导入员工" width="820px">
      <div class="import-actions">
        <el-button @click="onDownloadTemplate">下载模板</el-button>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xlsm"
          :on-change="onImportFileChange"
          :show-file-list="true"
        >
          <el-button type="primary" plain>选择文件</el-button>
        </el-upload>
        <el-button type="warning" :loading="importLoading" @click="onImportPreview">
          预览校验
        </el-button>
      </div>

      <template v-if="importPreview">
        <el-alert
          type="info"
          :closable="false"
          class="import-summary"
          :title="`共 ${importPreview.total_rows} 行：新增 ${importPreview.create_count}，更新 ${importPreview.update_count}，跳过 ${importPreview.skip_count}，错误 ${importPreview.error_count}`"
        />
        <el-table :data="importPreview.rows" size="small" max-height="320" stripe>
          <el-table-column prop="row_no" label="行号" width="70" />
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="full_name" label="姓名" width="100" />
          <el-table-column label="动作" width="90">
            <template #default="{ row }">
              <el-tag
                :type="
                  row.action === 'error'
                    ? 'danger'
                    : row.action === 'create'
                      ? 'success'
                      : row.action === 'update'
                        ? 'warning'
                        : 'info'
                "
              >
                {{
                  row.action === 'create'
                    ? '新增'
                    : row.action === 'update'
                      ? '更新'
                      : row.action === 'skip'
                        ? '跳过'
                        : '错误'
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="180" />
        </el-table>
      </template>

      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="importSubmitting"
          :disabled="!importPreview || importPreview.create_count + importPreview.update_count === 0"
          @click="onImportCommit"
        >
          确认导入
        </el-button>
      </template>
    </el-dialog>

    <!-- Department manager dialog -->
    <el-dialog v-model="deptListVisible" title="部门管理" width="720px">
      <div class="toolbar">
        <el-button
          v-if="auth.hasPermission('employee:create')"
          type="primary"
          @click="openDeptCreate"
        >
          新建部门
        </el-button>
      </div>
      <el-table :data="deptRows" v-loading="deptLoading" size="small" stripe max-height="360">
        <el-table-column prop="department_code" label="编码" width="120" />
        <el-table-column prop="department_name" label="名称" min-width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button
              v-if="auth.hasPermission('employee:update')"
              link
              type="primary"
              @click="openDeptEdit(row)"
            >
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- Department form dialog -->
    <el-dialog
      v-model="deptFormVisible"
      :title="deptEditingId == null ? '新建部门' : '编辑部门'"
      width="480px"
      append-to-body
    >
      <el-form ref="deptFormRef" :model="deptForm" :rules="deptRules" label-width="96px">
        <el-form-item label="部门编码" prop="department_code">
          <el-input v-model="deptForm.department_code" />
        </el-form-item>
        <el-form-item label="部门名称" prop="department_name">
          <el-input v-model="deptForm.department_name" />
        </el-form-item>
        <el-form-item label="上级部门">
          <el-select v-model="deptForm.parent_id" clearable style="width: 100%">
            <el-option
              v-for="d in deptRows"
              :key="d.id"
              :label="d.department_name"
              :value="d.id"
              :disabled="d.id === deptEditingId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="deptForm.status" active-value="active" inactive-value="disabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deptFormVisible = false">取消</el-button>
        <el-button type="primary" @click="onDeptSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.block {
  margin-bottom: 0;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}
.spacer {
  flex: 1;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
.import-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.import-summary {
  margin-bottom: 12px;
}
</style>
