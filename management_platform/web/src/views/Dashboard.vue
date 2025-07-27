<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h1>仪表板</h1>
      <p>欢迎使用网络拨测平台</p>
      
      <!-- 时间范围选择器 -->
      <div class="time-range-selector">
        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          @change="handleTimeRangeChange"
          style="margin-right: 16px"
        />
        <el-button @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
        <el-button @click="showExportDialog">
          <el-icon><Download /></el-icon>
          导出数据
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row" v-loading="loading">
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-icon">
              <el-icon color="#409EFF"><List /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-number">{{ summaryStats.total_tasks || 0 }}</div>
              <div class="stats-label">总任务数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-icon">
              <el-icon color="#67C23A"><Monitor /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-number">{{ summaryStats.online_agents || 0 }}</div>
              <div class="stats-label">在线代理</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-icon">
              <el-icon color="#E6A23C"><TrendCharts /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-number">{{ (summaryStats.success_rate * 100).toFixed(1) || 0 }}%</div>
              <div class="stats-label">成功率</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-icon">
              <el-icon color="#F56C6C"><Coin /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-number">{{ authStore.user?.credits || 0 }}</div>
              <div class="stats-label">剩余点数</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表行 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>任务执行趋势</span>
              <el-select v-model="trendChartType" size="small" style="width: 120px">
                <el-option label="执行次数" value="executions" />
                <el-option label="成功率" value="success_rate" />
                <el-option label="平均响应时间" value="avg_duration" />
              </el-select>
            </div>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="trendChartData.length > 0"
              :option="trendChartOption"
              :loading="loading"
              autoresize
            />
            <div v-else class="chart-placeholder">
              <el-icon size="48" color="#C0C4CC"><TrendCharts /></el-icon>
              <p>暂无数据</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>协议分布</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="protocolChartData.length > 0"
              :option="protocolChartOption"
              :loading="loading"
              autoresize
            />
            <div v-else class="chart-placeholder">
              <el-icon size="48" color="#C0C4CC"><PieChart /></el-icon>
              <p>暂无数据</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第二行图表 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>代理状态分布</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="agentStatusChartData.length > 0"
              :option="agentStatusChartOption"
              :loading="loading"
              autoresize
            />
            <div v-else class="chart-placeholder">
              <el-icon size="48" color="#C0C4CC"><PieChart /></el-icon>
              <p>暂无数据</p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>响应时间分布</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="responseTimeChartData.length > 0"
              :option="responseTimeChartOption"
              :loading="loading"
              autoresize
            />
            <div v-else class="chart-placeholder">
              <el-icon size="48" color="#C0C4CC"><BarChart /></el-icon>
              <p>暂无数据</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务状态概览 -->
    <el-row :gutter="20" class="overview-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>任务状态概览</span>
          </template>
          <div class="task-overview">
            <el-row :gutter="16">
              <el-col :span="6" v-for="(item, key) in taskStatusStats" :key="key">
                <div class="overview-item">
                  <div class="overview-number" :style="{ color: getTaskStatusColor(key) }">
                    {{ item.count || 0 }}
                  </div>
                  <div class="overview-label">{{ getTaskStatusText(key) }}</div>
                  <div class="overview-percentage">
                    {{ item.percentage ? item.percentage.toFixed(1) : 0 }}%
                  </div>
                </div>
              </el-col>
            </el-row>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>代理性能排行</span>
          </template>
          <div class="agent-ranking">
            <el-table :data="topAgents" size="small" :show-header="false">
              <el-table-column width="40">
                <template #default="{ $index }">
                  <div class="rank-number" :class="getRankClass($index)">
                    {{ $index + 1 }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="代理名称" />
              <el-table-column prop="success_rate" label="成功率" width="80">
                <template #default="{ row }">
                  {{ (row.success_rate * 100).toFixed(1) }}%
                </template>
              </el-table-column>
              <el-table-column prop="avg_response_time" label="响应时间" width="100">
                <template #default="{ row }">
                  {{ row.avg_response_time ? row.avg_response_time.toFixed(0) + 'ms' : '-' }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近活动 -->
    <el-row>
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近执行结果</span>
              <el-button size="small" @click="viewAllResults">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recentResults" style="width: 100%" v-loading="loading">
            <el-table-column prop="execution_time" label="执行时间" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.execution_time) }}
              </template>
            </el-table-column>
            <el-table-column prop="task_info.name" label="任务名称" min-width="150" />
            <el-table-column prop="task_info.protocol" label="协议" width="80">
              <template #default="{ row }">
                <el-tag :type="getProtocolTagType(row.task_info?.protocol)" size="small">
                  {{ row.task_info?.protocol?.toUpperCase() || '-' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="task_info.target" label="目标" min-width="150" />
            <el-table-column prop="agent_info.name" label="执行代理" width="120" />
            <el-table-column prop="duration" label="响应时间" width="100">
              <template #default="{ row }">
                {{ row.duration ? row.duration.toFixed(2) + 'ms' : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="getResultStatusTagType(row.status)" size="small">
                  {{ getResultStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 导出对话框 -->
    <el-dialog
      v-model="exportDialogVisible"
      title="导出数据"
      width="500px"
    >
      <el-form :model="exportForm" label-width="100px">
        <el-form-item label="导出格式">
          <el-radio-group v-model="exportForm.format">
            <el-radio label="csv">CSV格式</el-radio>
            <el-radio label="json">JSON格式</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="exportForm.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="协议过滤">
          <el-checkbox-group v-model="exportForm.protocols">
            <el-checkbox label="icmp">ICMP</el-checkbox>
            <el-checkbox label="tcp">TCP</el-checkbox>
            <el-checkbox label="udp">UDP</el-checkbox>
            <el-checkbox label="http">HTTP</el-checkbox>
            <el-checkbox label="https">HTTPS</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="状态过滤">
          <el-checkbox-group v-model="exportForm.statusFilter">
            <el-checkbox label="success">成功</el-checkbox>
            <el-checkbox label="timeout">超时</el-checkbox>
            <el-checkbox label="error">错误</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="exportDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleExport" :loading="exporting">
            导出
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAnalyticsStore } from '@/stores/analytics'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import {
  CanvasRenderer
} from 'echarts/renderers'
import {
  LineChart,
  PieChart,
  BarChart
} from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import {
  List, Monitor, TrendCharts, Coin, Refresh, Download, PieChart, BarChart
} from '@element-plus/icons-vue'

// 注册ECharts组件
use([
  CanvasRenderer,
  LineChart,
  PieChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const router = useRouter()
const authStore = useAuthStore()
const analyticsStore = useAnalyticsStore()

// 响应式数据
const loading = ref(false)
const timeRange = ref([])
const trendChartType = ref('executions')
const exportDialogVisible = ref(false)
const exporting = ref(false)

// 导出表单
const exportForm = reactive({
  format: 'csv',
  timeRange: [],
  protocols: [],
  statusFilter: []
})

// 统计数据
const summaryStats = ref({})
const taskStatusStats = ref({})
const protocolStats = ref({})
const agentStats = ref({})
const recentResults = ref([])

// 图表数据
const trendChartData = ref([])
const protocolChartData = ref([])
const agentStatusChartData = ref([])
const responseTimeChartData = ref([])

// 计算属性
const topAgents = computed(() => {
  if (!agentStats.value.agents) return []
  return agentStats.value.agents
    .sort((a, b) => b.success_rate - a.success_rate)
    .slice(0, 5)
})

// 图表配置
const trendChartOption = computed(() => {
  const data = trendChartData.value
  if (!data.length) return {}

  let yAxisName = '执行次数'
  let seriesName = '执行次数'
  
  if (trendChartType.value === 'success_rate') {
    yAxisName = '成功率 (%)'
    seriesName = '成功率'
  } else if (trendChartType.value === 'avg_duration') {
    yAxisName = '平均响应时间 (ms)'
    seriesName = '平均响应时间'
  }

  return {
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.time)
    },
    yAxis: {
      type: 'value',
      name: yAxisName
    },
    series: [{
      name: seriesName,
      type: 'line',
      data: data.map(item => item[trendChartType.value]),
      smooth: true,
      itemStyle: {
        color: '#409EFF'
      }
    }]
  }
})

const protocolChartOption = computed(() => {
  const data = protocolChartData.value
  if (!data.length) return {}

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [{
      name: '协议分布',
      type: 'pie',
      radius: '50%',
      data: data,
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  }
})

const agentStatusChartOption = computed(() => {
  const data = agentStatusChartData.value
  if (!data.length) return {}

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [{
      name: '代理状态',
      type: 'pie',
      radius: '50%',
      data: data,
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  }
})

const responseTimeChartOption = computed(() => {
  const data = responseTimeChartData.value
  if (!data.length) return {}

  return {
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.range)
    },
    yAxis: {
      type: 'value',
      name: '任务数量'
    },
    series: [{
      name: '响应时间分布',
      type: 'bar',
      data: data.map(item => item.count),
      itemStyle: {
        color: '#67C23A'
      }
    }]
  }
})

// 方法
const refreshData = async () => {
  loading.value = true
  
  try {
    const params = {}
    if (timeRange.value && timeRange.value.length === 2) {
      params.start_time = timeRange.value[0].toISOString()
      params.end_time = timeRange.value[1].toISOString()
    }

    // 获取统计数据
    const statsResult = await analyticsStore.fetchStatistics(params)
    if (statsResult.success) {
      const data = statsResult.data
      summaryStats.value = data.summary || {}
      taskStatusStats.value = data.task_statistics || {}
      protocolStats.value = data.protocol_statistics || {}
      agentStats.value = data.agent_statistics || {}
      
      // 处理图表数据
      processChartData(data)
    }

    // 获取最近结果
    const resultsResult = await analyticsStore.fetchResults({
      page: 1,
      size: 10,
      ...params
    })
    if (resultsResult.success) {
      recentResults.value = resultsResult.data.results || []
    }

  } catch (error) {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const processChartData = (data) => {
  // 处理趋势图数据
  if (data.summary && data.summary.trend_data) {
    trendChartData.value = data.summary.trend_data
  }

  // 处理协议分布数据
  if (data.protocol_statistics) {
    protocolChartData.value = Object.entries(data.protocol_statistics).map(([protocol, stats]) => ({
      name: protocol.toUpperCase(),
      value: stats.count || 0
    }))
  }

  // 处理代理状态分布数据
  if (data.agent_statistics && data.agent_statistics.status_distribution) {
    agentStatusChartData.value = Object.entries(data.agent_statistics.status_distribution).map(([status, count]) => ({
      name: getStatusText(status),
      value: count
    }))
  }

  // 处理响应时间分布数据
  if (data.summary && data.summary.response_time_distribution) {
    responseTimeChartData.value = data.summary.response_time_distribution
  }
}

const handleTimeRangeChange = () => {
  refreshData()
}

const showExportDialog = () => {
  exportForm.timeRange = timeRange.value
  exportDialogVisible.value = true
}

const handleExport = async () => {
  exporting.value = true
  
  try {
    const params = {
      format: exportForm.format
    }
    
    if (exportForm.timeRange && exportForm.timeRange.length === 2) {
      params.start_time = exportForm.timeRange[0]
      params.end_time = exportForm.timeRange[1]
    }
    
    if (exportForm.protocols.length > 0) {
      params.protocols = exportForm.protocols
    }
    
    if (exportForm.statusFilter.length > 0) {
      params.status_filter = exportForm.statusFilter
    }
    
    const result = await analyticsStore.exportData(params)
    if (result.success) {
      ElMessage.success('数据导出成功')
      exportDialogVisible.value = false
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const viewAllResults = () => {
  router.push('/analytics')
}

// 辅助方法
const getTaskStatusColor = (status) => {
  const colors = {
    active: '#67C23A',
    paused: '#E6A23C',
    completed: '#909399',
    failed: '#F56C6C'
  }
  return colors[status] || '#909399'
}

const getTaskStatusText = (status) => {
  const texts = {
    active: '活跃',
    paused: '暂停',
    completed: '已完成',
    failed: '失败'
  }
  return texts[status] || status
}

const getStatusText = (status) => {
  const texts = {
    online: '在线',
    offline: '离线',
    busy: '忙碌',
    maintenance: '维护'
  }
  return texts[status] || status
}

const getProtocolTagType = (protocol) => {
  const types = {
    icmp: 'primary',
    tcp: 'success',
    udp: 'warning',
    http: 'info',
    https: 'danger'
  }
  return types[protocol] || 'info'
}

const getResultStatusTagType = (status) => {
  const types = {
    success: 'success',
    timeout: 'warning',
    error: 'danger'
  }
  return types[status] || 'info'
}

const getResultStatusText = (status) => {
  const texts = {
    success: '成功',
    timeout: '超时',
    error: '错误'
  }
  return texts[status] || status
}

const getRankClass = (index) => {
  if (index === 0) return 'rank-gold'
  if (index === 1) return 'rank-silver'
  if (index === 2) return 'rank-bronze'
  return ''
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

// 监听器
watch(trendChartType, () => {
  // 趋势图类型变化时重新处理数据
})

// 生命周期
onMounted(() => {
  // 设置默认时间范围为最近7天
  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  timeRange.value = [sevenDaysAgo, now]
  
  refreshData()
})
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.dashboard-header {
  margin-bottom: 20px;
}

.dashboard-header h1 {
  margin: 0 0 8px 0;
  color: #303133;
}

.dashboard-header p {
  margin: 0 0 16px 0;
  color: #909399;
}

.time-range-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stats-row {
  margin-bottom: 20px;
}

.stats-card {
  height: 100px;
}

.stats-content {
  display: flex;
  align-items: center;
  height: 100%;
}

.stats-icon {
  font-size: 32px;
  margin-right: 16px;
}

.stats-info {
  flex: 1;
}

.stats-number {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  line-height: 1;
  margin-bottom: 4px;
}

.stats-label {
  font-size: 14px;
  color: #909399;
}

.charts-row {
  margin-bottom: 20px;
}

.overview-row {
  margin-bottom: 20px;
}

.chart-container {
  height: 300px;
}

.chart-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #C0C4CC;
}

.chart-placeholder p {
  margin-top: 12px;
  font-size: 14px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.task-overview {
  padding: 16px 0;
}

.overview-item {
  text-align: center;
}

.overview-number {
  font-size: 28px;
  font-weight: bold;
  line-height: 1;
  margin-bottom: 8px;
}

.overview-label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 4px;
}

.overview-percentage {
  font-size: 12px;
  color: #909399;
}

.agent-ranking {
  padding: 8px 0;
}

.rank-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  color: white;
  background-color: #C0C4CC;
}

.rank-gold {
  background-color: #FFD700;
}

.rank-silver {
  background-color: #C0C0C0;
}

.rank-bronze {
  background-color: #CD7F32;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>