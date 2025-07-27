<template>
  <div class="analytics-page">
    <div class="page-header">
      <h1>数据分析</h1>
      <p>查看拨测数据的统计和分析</p>
    </div>

    <!-- 筛选条件 -->
    <el-card class="filter-card">
      <el-form :model="filterForm" inline>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 300px"
          />
        </el-form-item>

        <el-form-item label="任务">
          <el-select
            v-model="filterForm.taskId"
            placeholder="选择任务"
            clearable
            style="width: 200px"
          >
            <el-option
              v-for="task in availableTasks"
              :key="task.id"
              :label="task.name"
              :value="task.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="代理">
          <el-select
            v-model="filterForm.agentId"
            placeholder="选择代理"
            clearable
            style="width: 200px"
          >
            <el-option
              v-for="agent in availableAgents"
              :key="agent.id"
              :label="agent.name"
              :value="agent.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="协议">
          <el-select
            v-model="filterForm.protocol"
            placeholder="选择协议"
            clearable
            style="width: 120px"
          >
            <el-option label="ICMP" value="icmp" />
            <el-option label="TCP" value="tcp" />
            <el-option label="UDP" value="udp" />
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="选择状态"
            clearable
            style="width: 120px"
          >
            <el-option label="成功" value="success" />
            <el-option label="超时" value="timeout" />
            <el-option label="错误" value="error" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="applyFilters" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
          <el-button @click="exportData">
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计概览 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总执行次数" :value="statistics.total_executions || 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="成功次数" :value="statistics.successful_executions || 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic 
            title="成功率" 
            :value="statistics.success_rate ? (statistics.success_rate * 100).toFixed(1) : 0" 
            suffix="%" 
          />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic 
            title="平均响应时间" 
            :value="statistics.avg_response_time ? statistics.avg_response_time.toFixed(2) : 0" 
            suffix="ms" 
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表分析 -->
    <el-row :gutter="20" class="charts-row">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>执行趋势分析</span>
              <div class="chart-controls">
                <el-radio-group v-model="trendMetric" size="small">
                  <el-radio-button label="count">执行次数</el-radio-button>
                  <el-radio-button label="success_rate">成功率</el-radio-button>
                  <el-radio-button label="avg_duration">平均响应时间</el-radio-button>
                </el-radio-group>
                <el-select v-model="trendInterval" size="small" style="width: 100px; margin-left: 16px">
                  <el-option label="小时" value="hour" />
                  <el-option label="天" value="day" />
                  <el-option label="周" value="week" />
                </el-select>
              </div>
            </div>
          </template>
          <div class="chart-container large">
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
    </el-row>

    <el-row :gutter="20" class="charts-row">
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
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>状态分布</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="statusChartData.length > 0"
              :option="statusChartOption"
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

    <el-row :gutter="20" class="charts-row">
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
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>代理性能对比</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="agentPerformanceChartData.length > 0"
              :option="agentPerformanceChartOption"
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

    <!-- 详细数据表格 -->
    <el-card class="data-table-card">
      <template #header>
        <div class="card-header">
          <span>详细数据</span>
          <div class="table-controls">
            <el-input
              v-model="searchQuery"
              placeholder="搜索..."
              style="width: 200px; margin-right: 16px"
              clearable
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button @click="refreshData">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="filteredResults"
        style="width: 100%"
        @sort-change="handleSortChange"
      >
        <el-table-column prop="execution_time" label="执行时间" width="180" sortable="custom">
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

        <el-table-column prop="duration" label="响应时间" width="100" sortable="custom">
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

        <el-table-column prop="error_message" label="错误信息" min-width="200">
          <template #default="{ row }">
            {{ row.error_message || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              size="small"
              @click="viewResultDetails(row)"
              v-if="row.metrics"
            >
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="totalResults"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 结果详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="执行结果详情"
      width="600px"
    >
      <div v-if="selectedResult">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="执行时间">
            {{ formatDateTime(selectedResult.execution_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="任务名称">
            {{ selectedResult.task_info?.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="协议">
            {{ selectedResult.task_info?.protocol?.toUpperCase() || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="目标">
            {{ selectedResult.task_info?.target || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="端口">
            {{ selectedResult.task_info?.port || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="执行代理">
            {{ selectedResult.agent_info?.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="响应时间">
            {{ selectedResult.duration ? selectedResult.duration.toFixed(2) + 'ms' : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getResultStatusTagType(selectedResult.status)">
              {{ getResultStatusText(selectedResult.status) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedResult.error_message" style="margin-top: 16px">
          <h4>错误信息</h4>
          <el-alert :title="selectedResult.error_message" type="error" :closable="false" />
        </div>

        <div v-if="selectedResult.metrics" style="margin-top: 16px">
          <h4>详细指标</h4>
          <pre class="metrics-data">{{ JSON.stringify(selectedResult.metrics, null, 2) }}</pre>
        </div>

        <div v-if="selectedResult.raw_data" style="margin-top: 16px">
          <h4>原始数据</h4>
          <pre class="raw-data">{{ JSON.stringify(selectedResult.raw_data, null, 2) }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAnalyticsStore } from '@/stores/analytics'
import { useTasksStore } from '@/stores/tasks'
import { useAgentsStore } from '@/stores/agents'
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
  Search, Refresh, Download, TrendCharts, PieChart, BarChart
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

const analyticsStore = useAnalyticsStore()
const tasksStore = useTasksStore()
const agentsStore = useAgentsStore()

// 响应式数据
const loading = ref(false)
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalResults = ref(0)
const detailDialogVisible = ref(false)
const selectedResult = ref(null)

// 筛选表单
const filterForm = reactive({
  timeRange: [],
  taskId: '',
  agentId: '',
  protocol: '',
  status: ''
})

// 图表控制
const trendMetric = ref('count')
const trendInterval = ref('day')

// 数据
const statistics = ref({})
const results = ref([])
const availableTasks = ref([])
const availableAgents = ref([])

// 图表数据
const trendChartData = ref([])
const protocolChartData = ref([])
const statusChartData = ref([])
const responseTimeChartData = ref([])
const agentPerformanceChartData = ref([])

// 计算属性
const filteredResults = computed(() => {
  let filtered = results.value
  
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(result => 
      (result.task_info?.name && result.task_info.name.toLowerCase().includes(query)) ||
      (result.task_info?.target && result.task_info.target.toLowerCase().includes(query)) ||
      (result.agent_info?.name && result.agent_info.name.toLowerCase().includes(query)) ||
      (result.error_message && result.error_message.toLowerCase().includes(query))
    )
  }
  
  return filtered
})

// 图表配置
const trendChartOption = computed(() => {
  const data = trendChartData.value
  if (!data.length) return {}

  let yAxisName = '执行次数'
  let seriesName = '执行次数'
  
  if (trendMetric.value === 'success_rate') {
    yAxisName = '成功率 (%)'
    seriesName = '成功率'
  } else if (trendMetric.value === 'avg_duration') {
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
      data: data.map(item => item[trendMetric.value]),
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

const statusChartOption = computed(() => {
  const data = statusChartData.value
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
      name: '状态分布',
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

const agentPerformanceChartOption = computed(() => {
  const data = agentPerformanceChartData.value
  if (!data.length) return {}

  return {
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.name)
    },
    yAxis: [
      {
        type: 'value',
        name: '成功率 (%)',
        position: 'left'
      },
      {
        type: 'value',
        name: '平均响应时间 (ms)',
        position: 'right'
      }
    ],
    series: [
      {
        name: '成功率',
        type: 'bar',
        data: data.map(item => (item.success_rate * 100).toFixed(1)),
        itemStyle: {
          color: '#67C23A'
        }
      },
      {
        name: '平均响应时间',
        type: 'line',
        yAxisIndex: 1,
        data: data.map(item => item.avg_response_time),
        itemStyle: {
          color: '#E6A23C'
        }
      }
    ]
  }
})

// 方法
const applyFilters = async () => {
  await fetchData()
}

const resetFilters = () => {
  Object.assign(filterForm, {
    timeRange: [],
    taskId: '',
    agentId: '',
    protocol: '',
    status: ''
  })
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  
  try {
    const params = {
      page: currentPage.value,
      size: pageSize.value
    }
    
    // 添加筛选条件
    if (filterForm.timeRange && filterForm.timeRange.length === 2) {
      params.start_time = filterForm.timeRange[0].toISOString()
      params.end_time = filterForm.timeRange[1].toISOString()
    }
    
    if (filterForm.taskId) params.task_id = filterForm.taskId
    if (filterForm.agentId) params.agent_id = filterForm.agentId
    if (filterForm.protocol) params.protocol = filterForm.protocol
    if (filterForm.status) params.status = filterForm.status
    
    // 获取结果数据
    const resultsResponse = await analyticsStore.fetchResults(params)
    if (resultsResponse.success) {
      results.value = resultsResponse.data.results || []
      totalResults.value = resultsResponse.data.total || 0
    }
    
    // 获取统计数据
    const statsParams = {}
    if (filterForm.timeRange && filterForm.timeRange.length === 2) {
      statsParams.start_time = filterForm.timeRange[0].toISOString()
      statsParams.end_time = filterForm.timeRange[1].toISOString()
    }
    
    const statsResponse = await analyticsStore.fetchStatistics(statsParams)
    if (statsResponse.success) {
      statistics.value = statsResponse.data.summary || {}
      processChartData(statsResponse.data)
    }
    
  } catch (error) {
    ElMessage.error('获取数据失败')
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

  // 处理状态分布数据
  if (data.summary && data.summary.status_distribution) {
    statusChartData.value = Object.entries(data.summary.status_distribution).map(([status, count]) => ({
      name: getResultStatusText(status),
      value: count
    }))
  }

  // 处理响应时间分布数据
  if (data.summary && data.summary.response_time_distribution) {
    responseTimeChartData.value = data.summary.response_time_distribution
  }

  // 处理代理性能数据
  if (data.agent_statistics && data.agent_statistics.agents) {
    agentPerformanceChartData.value = data.agent_statistics.agents.slice(0, 10) // 取前10个代理
  }
}

const refreshData = () => {
  fetchData()
}

const exportData = async () => {
  const params = {
    format: 'csv'
  }
  
  if (filterForm.timeRange && filterForm.timeRange.length === 2) {
    params.start_time = filterForm.timeRange[0]
    params.end_time = filterForm.timeRange[1]
  }
  
  if (filterForm.protocol) params.protocols = [filterForm.protocol]
  if (filterForm.status) params.status_filter = [filterForm.status]
  
  const result = await analyticsStore.exportData(params)
  if (result.success) {
    ElMessage.success('数据导出成功')
  } else {
    ElMessage.error(result.message)
  }
}

const handleSizeChange = (size) => {
  pageSize.value = size
  fetchData()
}

const handleCurrentChange = (page) => {
  currentPage.value = page
  fetchData()
}

const handleSortChange = ({ prop, order }) => {
  // 实现排序逻辑
  if (order === 'ascending') {
    results.value.sort((a, b) => {
      if (prop === 'execution_time') {
        return new Date(a.execution_time) - new Date(b.execution_time)
      } else if (prop === 'duration') {
        return (a.duration || 0) - (b.duration || 0)
      }
      return 0
    })
  } else if (order === 'descending') {
    results.value.sort((a, b) => {
      if (prop === 'execution_time') {
        return new Date(b.execution_time) - new Date(a.execution_time)
      } else if (prop === 'duration') {
        return (b.duration || 0) - (a.duration || 0)
      }
      return 0
    })
  }
}

const viewResultDetails = (result) => {
  selectedResult.value = result
  detailDialogVisible.value = true
}

const loadAvailableOptions = async () => {
  // 加载可用的任务和代理选项
  const tasksResult = await tasksStore.fetchTasks({ page: 1, size: 1000 })
  if (tasksResult.success) {
    availableTasks.value = tasksStore.tasks
  }
  
  const agentsResult = await agentsStore.fetchAgents({ page: 1, size: 1000 })
  if (agentsResult.success) {
    availableAgents.value = agentsStore.agents
  }
}

// 辅助方法
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

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

// 监听器
watch([trendMetric, trendInterval], () => {
  // 重新获取趋势数据
  fetchData()
})

// 生命周期
onMounted(() => {
  // 设置默认时间范围为最近7天
  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  filterForm.timeRange = [sevenDaysAgo, now]
  
  loadAvailableOptions()
  fetchData()
})
</script>

<style scoped>
.analytics-page {
  padding: 0;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  color: #303133;
}

.page-header p {
  margin: 0;
  color: #909399;
}

.filter-card {
  margin-bottom: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 16px;
}

.charts-row {
  margin-bottom: 20px;
}

.data-table-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-controls {
  display: flex;
  align-items: center;
}

.table-controls {
  display: flex;
  align-items: center;
}

.chart-container {
  height: 300px;
}

.chart-container.large {
  height: 400px;
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

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.metrics-data,
.raw-data {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}
</style>