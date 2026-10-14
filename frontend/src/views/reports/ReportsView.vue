<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  downloadBlob,
  exportReport,
  fetchAccommodationLedger,
  fetchCheckinCheckoutReport,
  fetchDepartmentStats,
  fetchExceptionReport,
  fetchTransferReport,
  fetchVacantBeds,
} from '@/api/reports'
import type {
  AccommodationLedgerRow,
  CheckinCheckoutEventRow,
  DepartmentStatRow,
  ExceptionReportRow,
  TransferReportRow,
  VacantBedRow,
} from '@/types'

const auth = useAuthStore()
const activeTab = ref('accommodations')
const loading = ref(false)
const exporting = ref(false)

const filters = reactive({
  keyword: '',
  date_from: '',
  date_to: '',
  event_type: '',
  status: 'active',
})

const page = reactive({ page: 1, page_size: 20, total: 0 })

const accommodations = ref<AccommodationLedgerRow[]>([])
const vacantBeds = ref<VacantBedRow[]>([])
const departments = ref<DepartmentStatRow[]>([])
const events = ref<CheckinCheckoutEventRow[]>([])
const transfers = ref<TransferReportRow[]>([])
const exceptions = ref<ExceptionReportRow[]>([])

const canExport = computed(() => auth.hasPermission('report:export'))

const tableData = computed(() => {
  switch (activeTab.value) {
    case 'accommodations':
      return accommodations.value
    case 'vacant-beds':
      return vacantBeds.value
    case 'departments':
      return departments.value
    case 'checkin-checkout':
      return events.value
    case 'transfers':
      return transfers.value
    case 'exceptions':
      return exceptions.value
    default:
      return []
  }
})

async function load() {
  loading.value = true
  try {
    const p = { page: page.page, page_size: page.page_size }
    if (activeTab.value === 'accommodations') {
      const data = await fetchAccommodationLedger({
        ...p,
        keyword: filters.keyword || undefined,
      })
      accommodations.value = data.items
      page.total = data.total
    } else if (activeTab.value === 'vacant-beds') {
      const data = await fetchVacantBeds(p)
      vacantBeds.value = data.items
      page.total = data.total
    } else if (activeTab.value === 'departments') {
      const data = await fetchDepartmentStats({ ...p, page_size: 100 })
      departments.value = data.items
      page.total = data.total
    } else if (activeTab.value === 'checkin-checkout') {
      const data = await fetchCheckinCheckoutReport({
        ...p,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
        event_type: filters.event_type || undefined,
      })
      events.value = data.items
      page.total = data.total
    } else if (activeTab.value === 'transfers') {
      const data = await fetchTransferReport({ ...p })
      transfers.value = data.items
      page.total = data.total
    } else if (activeTab.value === 'exceptions') {
      const data = await fetchExceptionReport({
        ...p,
        status: filters.status || undefined,
      })
      exceptions.value = data.items
      page.total = data.total
    }
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '加载报表失败')
  } finally {
    loading.value = false
  }
}

async function doExport() {
  if (!canExport.value) {
    ElMessage.warning('没有报表导出权限')
    return
  }
  exporting.value = true
  try {
    const blob = await exportReport(activeTab.value, {
      keyword: filters.keyword || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      event_type: filters.event_type || undefined,
      status: filters.status || undefined,
    })
    downloadBlob(blob, `dms_${activeTab.value}_export.xlsx`)
    ElMessage.success('导出成功')
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

function fmtLoc(loc: Record<string, string | number | null> | null | undefined): string {
  if (!loc) return '—'
  return `${loc.building_name || ''}/${loc.room_no || ''}/${loc.bed_no || ''}`
}

watch(activeTab, () => {
  page.page = 1
  void load()
})

onMounted(() => void load())
</script>

<template>
  <div class="reports-page">
    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="activeTab">
          <el-radio-button value="accommodations">住宿台账</el-radio-button>
          <el-radio-button value="vacant-beds">空床统计</el-radio-button>
          <el-radio-button value="departments">部门住宿</el-radio-button>
          <el-radio-button value="checkin-checkout">入退宿明细</el-radio-button>
          <el-radio-button value="transfers">调宿明细</el-radio-button>
          <el-radio-button value="exceptions">异常报表</el-radio-button>
        </el-radio-group>
        <div class="actions">
          <el-button :loading="loading" @click="load">刷新</el-button>
          <el-button
            type="primary"
            :loading="exporting"
            :disabled="!canExport"
            @click="doExport"
          >
            导出 Excel
          </el-button>
        </div>
      </div>

      <div class="filters" v-if="activeTab === 'accommodations'">
        <el-input
          v-model="filters.keyword"
          placeholder="工号 / 姓名"
          clearable
          style="width: 220px"
          @keyup.enter="load"
        />
      </div>
      <div class="filters" v-else-if="activeTab === 'checkin-checkout'">
        <el-date-picker
          v-model="filters.date_from"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="开始日期"
        />
        <el-date-picker
          v-model="filters.date_to"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="结束日期"
        />
        <el-select v-model="filters.event_type" clearable placeholder="事件类型" style="width: 140px">
          <el-option label="入住" value="checkin" />
          <el-option label="退宿" value="checkout" />
        </el-select>
        <el-button @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="tableData" stripe>
        <template v-if="activeTab === 'accommodations'">
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="employee_name" label="姓名" width="110" />
          <el-table-column prop="department_name" label="部门" width="140" />
          <el-table-column prop="employment_status" label="人事状态" width="110" />
          <el-table-column prop="building_name" label="楼栋" width="120" />
          <el-table-column prop="room_no" label="房间" width="90" />
          <el-table-column prop="bed_no" label="床位" width="90" />
          <el-table-column prop="checkin_at" label="入住时间" min-width="160">
            <template #default="{ row }">{{ (row.checkin_at || '').replace('T', ' ') }}</template>
          </el-table-column>
        </template>
        <template v-else-if="activeTab === 'vacant-beds'">
          <el-table-column prop="area_name" label="区域" width="120" />
          <el-table-column prop="building_name" label="楼栋" width="140" />
          <el-table-column prop="floor_no" label="楼层" width="80" />
          <el-table-column prop="room_no" label="房间" width="100" />
          <el-table-column prop="bed_no" label="床位" width="100" />
          <el-table-column prop="operational_status" label="状态" width="100" />
        </template>
        <template v-else-if="activeTab === 'departments'">
          <el-table-column prop="department_code" label="部门编码" width="140" />
          <el-table-column prop="department_name" label="部门名称" min-width="160" />
          <el-table-column prop="employee_count" label="员工数" width="100" />
          <el-table-column prop="housed_count" label="在住人数" width="100" />
          <el-table-column prop="reserved_count" label="已预留" width="100" />
        </template>
        <template v-else-if="activeTab === 'checkin-checkout'">
          <el-table-column prop="event_type" label="事件" width="90">
            <template #default="{ row }">{{ row.event_type === 'checkin' ? '入住' : '退宿' }}</template>
          </el-table-column>
          <el-table-column prop="event_at" label="时间" min-width="160">
            <template #default="{ row }">{{ (row.event_at || '').replace('T', ' ') }}</template>
          </el-table-column>
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="employee_name" label="姓名" width="110" />
          <el-table-column prop="building_name" label="楼栋" width="120" />
          <el-table-column prop="room_no" label="房间" width="90" />
          <el-table-column prop="bed_no" label="床位" width="90" />
          <el-table-column prop="reason" label="原因" min-width="120" />
        </template>
        <template v-else-if="activeTab === 'transfers'">
          <el-table-column prop="transfer_no" label="调宿单号" width="150" />
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="employee_name" label="姓名" width="110" />
          <el-table-column label="原床位" min-width="160">
            <template #default="{ row }">{{ fmtLoc(row.old_location) }}</template>
          </el-table-column>
          <el-table-column label="新床位" min-width="160">
            <template #default="{ row }">{{ fmtLoc(row.new_location) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="reason" label="原因" min-width="120" />
        </template>
        <template v-else>
          <el-table-column prop="alert_type" label="类型" width="150" />
          <el-table-column prop="severity" label="级别" width="90" />
          <el-table-column prop="employee_no" label="工号" width="120" />
          <el-table-column prop="employee_name" label="姓名" width="110" />
          <el-table-column prop="title" label="标题" min-width="180" />
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column prop="detected_at" label="发现时间" min-width="160">
            <template #default="{ row }">{{ (row.detected_at || '').replace('T', ' ') }}</template>
          </el-table-column>
        </template>
      </el-table>

      <el-pagination
        v-if="activeTab !== 'departments'"
        v-model:current-page="page.page"
        v-model:page-size="page.page_size"
        :total="page.total"
        layout="total, prev, pager, next"
        style="margin-top: 12px; justify-content: flex-end"
        @current-change="load"
      />
    </el-card>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.filters {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
</style>
