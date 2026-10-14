<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  fetchDashboardOccupancy,
  fetchDashboardSummary,
  fetchDashboardTrends,
} from '@/api/reports'
import { useAuthStore } from '@/stores/auth'
import type { DashboardSummary } from '@/types'

const auth = useAuthStore()
const summary = ref<DashboardSummary | null>(null)
const loading = ref(false)

const kpiCards = computed(() => {
  const s = summary.value
  return [
    { label: '楼栋', value: s?.building_total ?? '—' },
    { label: '房间', value: s?.room_total ?? '—' },
    { label: '可用床位', value: s?.bed_total ?? '—' },
    { label: '已入住', value: s?.occupied_beds ?? '—' },
    { label: '已预留', value: s?.reserved_beds ?? '—' },
    { label: '可分配空床', value: s?.vacant_beds ?? '—' },
    { label: '入住率', value: s ? `${s.occupancy_rate}%` : '—' },
    { label: '今日入住', value: s?.today_checkin ?? '—' },
    { label: '今日退宿', value: s?.today_checkout ?? '—' },
    { label: '在住员工', value: s?.housed_employees ?? '—' },
    { label: '维修床位', value: s?.bed_maintenance ?? '—' },
    { label: '停用床位', value: s?.bed_disabled ?? '—' },
  ]
})

const trendEl = ref<HTMLDivElement | null>(null)
const occEl = ref<HTMLDivElement | null>(null)
let trendChart: echarts.ECharts | null = null
let occChart: echarts.ECharts | null = null

async function load() {
  loading.value = true
  try {
    const [s, t, o] = await Promise.all([
      fetchDashboardSummary(),
      fetchDashboardTrends(14),
      fetchDashboardOccupancy(),
    ])
    summary.value = s
    renderTrend(t.items)
    renderOcc(o.items)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '加载首页指标失败')
  } finally {
    loading.value = false
  }
}

function renderTrend(points: Array<{ date: string; checkin: number; checkout: number }>) {
  if (!trendEl.value) return
  if (!trendChart) trendChart = echarts.init(trendEl.value)
  trendChart.setOption({
    title: { text: '入退宿趋势（近 14 天）', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, data: ['入住', '退宿'] },
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: points.map((p) => p.date.slice(5)),
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '入住', type: 'line', smooth: true, data: points.map((p) => p.checkin) },
      { name: '退宿', type: 'line', smooth: true, data: points.map((p) => p.checkout) },
    ],
  })
}

function renderOcc(items: Array<{ building_name: string; bed_total: number; occupied: number }>) {
  if (!occEl.value) return
  if (!occChart) occChart = echarts.init(occEl.value)
  occChart.setOption({
    title: { text: '楼栋入住情况', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, data: ['已入住', '床位总数'] },
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: items.map((i) => i.building_name) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '已入住', type: 'bar', data: items.map((i) => i.occupied) },
      { name: '床位总数', type: 'bar', data: items.map((i) => i.bed_total) },
    ],
  })
}

function onResize() {
  trendChart?.resize()
  occChart?.resize()
}

onMounted(() => {
  void load()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
  occChart?.dispose()
})
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <el-row :gutter="12">
      <el-col :span="4" v-for="card in kpiCards" :key="card.label">
        <el-card shadow="hover" class="kpi">
          <div class="kpi-label">{{ card.label }}</div>
          <div class="kpi-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>当前登录</template>
          <div class="stat"><div class="label">用户</div><div class="value">{{ auth.displayName || auth.username }}</div></div>
          <div class="stat"><div class="label">角色</div><div class="value">{{ auth.roles.join('、') || '—' }}</div></div>
        </el-card>
        <el-card shadow="hover" style="margin-top: 12px">
          <template #header>离职未退宿 / 异常</template>
          <div class="stat">
            <div class="label">离职未退宿</div>
            <div class="value warn">{{ summary?.terminated_still_housed ?? '—' }}</div>
          </div>
          <div class="stat">
            <div class="label">活动预警</div>
            <div class="value warn">{{ summary?.active_alerts ?? '—' }}</div>
          </div>
          <div class="stat">
            <div class="label">待办</div>
            <div class="value">{{ summary?.pending_todos ?? '—' }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="9">
        <el-card shadow="hover">
          <div ref="trendEl" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="9">
        <el-card shadow="hover">
          <div ref="occEl" class="chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" style="margin-top: 12px">
      <template #header>部门住宿人数</template>
      <el-table :data="summary?.department_housed || []" size="small">
        <el-table-column prop="department_name" label="部门" />
        <el-table-column prop="housed_count" label="在住人数" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.kpi {
  text-align: center;
}
.kpi-label {
  color: #909399;
  font-size: 12px;
}
.kpi-value {
  font-size: 22px;
  font-weight: 700;
  margin-top: 6px;
}
.stat {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}
.label {
  color: #909399;
}
.value {
  font-weight: 600;
}
.value.warn {
  color: #e6a23c;
}
.chart {
  height: 280px;
}
</style>
