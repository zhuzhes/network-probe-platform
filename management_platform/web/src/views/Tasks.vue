<template>
  <div class="tasks-page">
    <div class="page-header">
      <h1>任务管理</h1>
      <p>管理和监控您的拨测任务</p>
    </div>

    <!-- 操作栏 -->
    <el-card class="operation-bar">
      <div class="operation-content">
        <div class="search-filters">
          <el-input
            v-model="searchQuery"
            placeholder="搜索任务名称或目标地址"
            style="width: 300px; margin-right: 16px"
            clearable
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          
          <el-select
            v-model="statusFilter"
            placeholder="状态筛选"
            style="width: 120px; margin-right: 16px"
            clearable
            @change="handleFilter"
          >
            <el-option label="活跃" value="active" />
            <el-option label="暂停" value="paused" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>

          <el-select
            v-model="protocolFilter"
            placeholder="协议筛选"
            style="width: 120px; margin-right: 16px"
            clearable
            @change="handleFilter"
          >
            <el-option label="ICMP" value="icmp" />
            <el-option label="TCP" value="tcp" />
            <el-option label="UDP" value="udp" />
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
          </el-select>
        </div>

        <div class="operation-buttons">
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon>
            创建任务
          </el-button>
          <el-button @click="refreshTasks">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 任务列表 -->
    <el-card class="task-list-card">
      <el-table
        v-loading="loading"
        :data="filteredTasks"
        style="width: 100%"
        @row-click="handleRowClick"
      >
        <el-table-column prop="name" label="任务名称" min-width="150">
          <template #default="{ row }">
            <div class="task-name">
              <span>{{ row.name }}</span>
              <el-tag
                :type="getStatusTagType(row.status)"
                size="small"
                style="margin-left: 8px"
              >
                {{ getStatusText(row.status) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="protocol" label="协议" width="80">
          <template #default="{ row }">
            <el-tag :type="getProtocolTagType(row.protocol)" size="small">
              {{ row.protocol.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="target" label="目标地址" min-width="200" />

        <el-table-column prop="frequency" label="频率" width="100">
          <template #default="{ row }">
            {{ formatFrequency(row.frequency) }}
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column prop="next_run" label="下次执行" width="180">
          <template #default="{ row }">
            {{ row.next_run ? formatDateTime(row.next_run) : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              @click.stop="viewTaskDetails(row)"
            >
              详情
            </el-button>
            <el-button
              size="small"
              @click.stop="editTask(row)"
            >
              编辑
            </el-button>
            <el-dropdown @command="handleTaskAction">
              <el-button size="small">
                更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :command="{ action: 'pause', task: row }" v-if="row.status === 'active'">
                    暂停任务
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'resume', task: row }" v-if="row.status === 'paused'">
                    恢复任务
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'results', task: row }">
                    查看结果
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'delete', task: row }" divided>
                    <span style="color: #f56c6c">删除任务</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="totalTasks"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 创建/编辑任务对话框 -->
    <el-dialog
      v-model="taskDialogVisible"
      :title="isEditing ? '编辑任务' : '创建任务'"
      width="600px"
      @close="resetTaskForm"
    >
      <el-form
        ref="taskFormRef"
        :model="taskForm"
        :rules="taskFormRules"
        label-width="100px"
      >
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="taskForm.name" placeholder="请输入任务名称" />
        </el-form-item>

        <el-form-item label="描述" prop="description">
          <el-input
            v-model="taskForm.description"
            type="textarea"
            :rows="3"
            placeholder="请输入任务描述（可选）"
          />
        </el-form-item>

        <el-form-item label="协议类型" prop="protocol">
          <el-select v-model="taskForm.protocol" placeholder="请选择协议" @change="handleProtocolChange">
            <el-option label="ICMP (Ping)" value="icmp" />
            <el-option label="TCP" value="tcp" />
            <el-option label="UDP" value="udp" />
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
          </el-select>
        </el-form-item>

        <el-form-item label="目标地址" prop="target">
          <el-input v-model="taskForm.target" placeholder="请输入目标地址或域名" />
        </el-form-item>

        <el-form-item
          v-if="['tcp', 'udp', 'http', 'https'].includes(taskForm.protocol)"
          label="端口"
          prop="port"
        >
          <el-input-number
            v-model="taskForm.port"
            :min="1"
            :max="65535"
            placeholder="请输入端口号"
          />
        </el-form-item>

        <el-form-item label="执行频率" prop="frequency">
          <el-input-number
            v-model="taskForm.frequency"
            :min="10"
            :max="86400"
            placeholder="秒"
          />
          <span style="margin-left: 8px; color: #909399">秒（10秒-24小时）</span>
        </el-form-item>

        <el-form-item label="超时时间" prop="timeout">
          <el-input-number
            v-model="taskForm.timeout"
            :min="1"
            :max="300"
            placeholder="秒"
          />
          <span style="margin-left: 8px; color: #909399">秒（1-300秒）</span>
        </el-form-item>

        <el-form-item label="优先级" prop="priority">
          <el-select v-model="taskForm.priority" placeholder="请选择优先级">
            <el-option label="低" :value="0" />
            <el-option label="普通" :value="1" />
            <el-option label="高" :value="2" />
            <el-option label="紧急" :value="3" />
          </el-select>
        </el-form-item>

        <!-- 高级配置 -->
        <el-collapse v-model="advancedConfigOpen">
          <el-collapse-item title="高级配置" name="advanced">
            <el-form-item label="首选位置" prop="preferred_location">
              <el-input v-model="taskForm.preferred_location" placeholder="如：北京、上海" />
            </el-form-item>

            <el-form-item label="首选运营商" prop="preferred_isp">
              <el-input v-model="taskForm.preferred_isp" placeholder="如：电信、联通、移动" />
            </el-form-item>

            <!-- HTTP/HTTPS 特定参数 -->
            <div v-if="['http', 'https'].includes(taskForm.protocol)">
              <el-form-item label="请求方法">
                <el-select v-model="httpParams.method" placeholder="请求方法">
                  <el-option label="GET" value="GET" />
                  <el-option label="POST" value="POST" />
                  <el-option label="PUT" value="PUT" />
                  <el-option label="DELETE" value="DELETE" />
                  <el-option label="HEAD" value="HEAD" />
                </el-select>
              </el-form-item>

              <el-form-item label="请求头">
                <el-input
                  v-model="httpParams.headers"
                  type="textarea"
                  :rows="3"
                  placeholder='{"Content-Type": "application/json"}'
                />
              </el-form-item>

              <el-form-item label="请求体" v-if="['POST', 'PUT'].includes(httpParams.method)">
                <el-input
                  v-model="httpParams.body"
                  type="textarea"
                  :rows="3"
                  placeholder="请求体内容"
                />
              </el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="taskDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitTaskForm" :loading="submitting">
            {{ isEditing ? '更新' : '创建' }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 任务详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="任务详情"
      width="800px"
    >
      <div v-if="selectedTask" class="task-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务名称">{{ selectedTask.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(selectedTask.status)">
              {{ getStatusText(selectedTask.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="协议">
            <el-tag :type="getProtocolTagType(selectedTask.protocol)">
              {{ selectedTask.protocol.toUpperCase() }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="目标地址">{{ selectedTask.target }}</el-descriptions-item>
          <el-descriptions-item label="端口" v-if="selectedTask.port">{{ selectedTask.port }}</el-descriptions-item>
          <el-descriptions-item label="执行频率">{{ formatFrequency(selectedTask.frequency) }}</el-descriptions-item>
          <el-descriptions-item label="超时时间">{{ selectedTask.timeout }}秒</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ getPriorityText(selectedTask.priority) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(selectedTask.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(selectedTask.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="下次执行" v-if="selectedTask.next_run">
            {{ formatDateTime(selectedTask.next_run) }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedTask.description" style="margin-top: 16px">
          <h4>描述</h4>
          <p>{{ selectedTask.description }}</p>
        </div>

        <div v-if="selectedTask.parameters" style="margin-top: 16px">
          <h4>协议参数</h4>
          <pre>{{ JSON.stringify(selectedTask.parameters, null, 2) }}</pre>
        </div>
      </div>
    </el-dialog>

    <!-- 任务结果对话框 -->
    <el-dialog
      v-model="resultsDialogVisible"
      title="任务结果分析"
      width="1000px"
      top="5vh"
    >
      <div v-if="selectedTask" class="task-results">
        <!-- 结果统计 -->
        <el-row :gutter="16" class="stats-row">
          <el-col :span="6">
            <el-statistic title="总执行次数" :value="resultStats.total" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="成功次数" :value="resultStats.success" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="成功率" :value="resultStats.successRate" suffix="%" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="平均响应时间" :value="resultStats.avgDuration" suffix="ms" />
          </el-col>
        </el-row>

        <!-- 时间范围选择 -->
        <div class="time-range-selector">
          <el-date-picker
            v-model="resultsTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            @change="fetchTaskResults"
          />
          <el-button @click="fetchTaskResults" style="margin-left: 16px">刷新</el-button>
        </div>

        <!-- 结果列表 -->
        <el-table
          v-loading="resultsLoading"
          :data="taskResults"
          style="width: 100%; margin-top: 16px"
        >
          <el-table-column prop="execution_time" label="执行时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.execution_time) }}
            </template>
          </el-table-column>

          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getResultStatusTagType(row.status)" size="small">
                {{ getResultStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="duration" label="响应时间" width="120">
            <template #default="{ row }">
              {{ row.duration ? row.duration.toFixed(2) + 'ms' : '-' }}
            </template>
          </el-table-column>

          <el-table-column prop="agent_id" label="执行代理" width="120">
            <template #default="{ row }">
              {{ row.agent_name || row.agent_id?.substring(0, 8) || '-' }}
            </template>
          </el-table-column>

          <el-table-column prop="error_message" label="错误信息" min-width="200">
            <template #default="{ row }">
              {{ row.error_message || '-' }}
            </template>
          </el-table-column>

          <el-table-column label="详细指标" width="100">
            <template #default="{ row }">
              <el-button
                size="small"
                @click="showResultMetrics(row)"
                v-if="row.metrics"
              >
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 结果分页 -->
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="resultsCurrentPage"
            v-model:page-size="resultsPageSize"
            :page-sizes="[20, 50, 100]"
            :total="resultsTotalCount"
            layout="total, sizes, prev, pager, next"
            @size-change="handleResultsSizeChange"
            @current-change="handleResultsCurrentChange"
          />
        </div>
      </div>
    </el-dialog>

    <!-- 结果指标详情对话框 -->
    <el-dialog
      v-model="metricsDialogVisible"
      title="详细指标"
      width="600px"
    >
      <div v-if="selectedResult">
        <pre>{{ JSON.stringify(selectedResult.metrics, null, 2) }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTasksStore } from '@/stores/tasks'
import {
  Search, Plus, Refresh, ArrowDown
} from '@element-plus/icons-vue'

// Store
const tasksStore = useTasksStore()

// 响应式数据
const loading = ref(false)
const searchQuery = ref('')
const statusFilter = ref('')
const protocolFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalTasks = ref(0)

// 对话框状态
const taskDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const resultsDialogVisible = ref(false)
const metricsDialogVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)

// 选中的任务和结果
const selectedTask = ref(null)
const selectedResult = ref(null)

// 高级配置展开状态
const advancedConfigOpen = ref([])

// 任务表单
const taskFormRef = ref()
const taskForm = reactive({
  name: '',
  description: '',
  protocol: '',
  target: '',
  port: null,
  frequency: 60,
  timeout: 30,
  priority: 0,
  preferred_location: '',
  preferred_isp: '',
  parameters: {}
})

// HTTP参数
const httpParams = reactive({
  method: 'GET',
  headers: '',
  body: ''
})

// 任务表单验证规则
const taskFormRules = {
  name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 255, message: '任务名称长度在1到255个字符', trigger: 'blur' }
  ],
  protocol: [
    { required: true, message: '请选择协议类型', trigger: 'change' }
  ],
  target: [
    { required: true, message: '请输入目标地址', trigger: 'blur' }
  ],
  port: [
    { type: 'number', min: 1, max: 65535, message: '端口号必须在1-65535之间', trigger: 'blur' }
  ],
  frequency: [
    { required: true, message: '请输入执行频率', trigger: 'blur' },
    { type: 'number', min: 10, max: 86400, message: '执行频率必须在10秒到24小时之间', trigger: 'blur' }
  ],
  timeout: [
    { required: true, message: '请输入超时时间', trigger: 'blur' },
    { type: 'number', min: 1, max: 300, message: '超时时间必须在1到300秒之间', trigger: 'blur' }
  ]
}

// 任务结果相关
const taskResults = ref([])
const resultsLoading = ref(false)
const resultsCurrentPage = ref(1)
const resultsPageSize = ref(20)
const resultsTotalCount = ref(0)
const resultsTimeRange = ref([])

// 结果统计
const resultStats = reactive({
  total: 0,
  success: 0,
  successRate: 0,
  avgDuration: 0
})

// 计算属性
const filteredTasks = computed(() => {
  let tasks = tasksStore.tasks
  
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    tasks = tasks.filter(task => 
      task.name.toLowerCase().includes(query) || 
      task.target.toLowerCase().includes(query)
    )
  }
  
  if (statusFilter.value) {
    tasks = tasks.filter(task => task.status === statusFilter.value)
  }
  
  if (protocolFilter.value) {
    tasks = tasks.filter(task => task.protocol === protocolFilter.value)
  }
  
  return tasks
})

// 方法
const refreshTasks = async () => {
  loading.value = true
  const result = await tasksStore.fetchTasks({
    page: currentPage.value,
    size: pageSize.value
  })
  
  if (!result.success) {
    ElMessage.error(result.message)
  }
  
  totalTasks.value = tasksStore.tasks.length
  loading.value = false
}

const handleSearch = () => {
  // 搜索逻辑已在计算属性中处理
}

const handleFilter = () => {
  // 筛选逻辑已在计算属性中处理
}

const handleSizeChange = (size) => {
  pageSize.value = size
  refreshTasks()
}

const handleCurrentChange = (page) => {
  currentPage.value = page
  refreshTasks()
}

const handleRowClick = (row) => {
  viewTaskDetails(row)
}

const showCreateDialog = () => {
  isEditing.value = false
  taskDialogVisible.value = true
}

const editTask = (task) => {
  isEditing.value = true
  selectedTask.value = task
  
  // 填充表单
  Object.assign(taskForm, {
    name: task.name,
    description: task.description || '',
    protocol: task.protocol,
    target: task.target,
    port: task.port,
    frequency: task.frequency,
    timeout: task.timeout,
    priority: task.priority || 0,
    preferred_location: task.preferred_location || '',
    preferred_isp: task.preferred_isp || '',
    parameters: task.parameters || {}
  })
  
  // 如果是HTTP/HTTPS，填充HTTP参数
  if (['http', 'https'].includes(task.protocol) && task.parameters) {
    Object.assign(httpParams, {
      method: task.parameters.method || 'GET',
      headers: task.parameters.headers ? JSON.stringify(task.parameters.headers, null, 2) : '',
      body: task.parameters.body || ''
    })
  }
  
  taskDialogVisible.value = true
}

const viewTaskDetails = (task) => {
  selectedTask.value = task
  detailDialogVisible.value = true
}

const handleTaskAction = async ({ action, task }) => {
  switch (action) {
    case 'pause':
      await updateTaskStatus(task, 'paused')
      break
    case 'resume':
      await updateTaskStatus(task, 'active')
      break
    case 'results':
      showTaskResults(task)
      break
    case 'delete':
      await deleteTask(task)
      break
  }
}

const updateTaskStatus = async (task, status) => {
  const result = await tasksStore.updateTask(task.id, { status })
  if (result.success) {
    ElMessage.success(`任务已${status === 'paused' ? '暂停' : '恢复'}`)
    refreshTasks()
  } else {
    ElMessage.error(result.message)
  }
}

const deleteTask = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务"${task.name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    const result = await tasksStore.deleteTask(task.id)
    if (result.success) {
      ElMessage.success('任务已删除')
      refreshTasks()
    } else {
      ElMessage.error(result.message)
    }
  } catch {
    // 用户取消删除
  }
}

const handleProtocolChange = (protocol) => {
  // 根据协议设置默认端口
  if (protocol === 'http') {
    taskForm.port = 80
  } else if (protocol === 'https') {
    taskForm.port = 443
  } else if (protocol === 'tcp' || protocol === 'udp') {
    taskForm.port = null
  } else {
    taskForm.port = null
  }
  
  // 重置HTTP参数
  if (['http', 'https'].includes(protocol)) {
    Object.assign(httpParams, {
      method: 'GET',
      headers: '',
      body: ''
    })
  }
}

const submitTaskForm = async () => {
  if (!taskFormRef.value) return
  
  try {
    await taskFormRef.value.validate()
    
    submitting.value = true
    
    // 准备任务数据
    const taskData = { ...taskForm }
    
    // 处理HTTP参数
    if (['http', 'https'].includes(taskForm.protocol)) {
      taskData.parameters = {
        method: httpParams.method,
        headers: httpParams.headers ? JSON.parse(httpParams.headers) : {},
        body: httpParams.body
      }
    }
    
    let result
    if (isEditing.value) {
      result = await tasksStore.updateTask(selectedTask.value.id, taskData)
    } else {
      result = await tasksStore.createTask(taskData)
    }
    
    if (result.success) {
      ElMessage.success(isEditing.value ? '任务更新成功' : '任务创建成功')
      taskDialogVisible.value = false
      refreshTasks()
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    submitting.value = false
  }
}

const resetTaskForm = () => {
  if (taskFormRef.value) {
    taskFormRef.value.resetFields()
  }
  
  Object.assign(taskForm, {
    name: '',
    description: '',
    protocol: '',
    target: '',
    port: null,
    frequency: 60,
    timeout: 30,
    priority: 0,
    preferred_location: '',
    preferred_isp: '',
    parameters: {}
  })
  
  Object.assign(httpParams, {
    method: 'GET',
    headers: '',
    body: ''
  })
  
  advancedConfigOpen.value = []
}

const showTaskResults = async (task) => {
  selectedTask.value = task
  resultsDialogVisible.value = true
  await fetchTaskResults()
}

const fetchTaskResults = async () => {
  if (!selectedTask.value) return
  
  resultsLoading.value = true
  
  const params = {
    page: resultsCurrentPage.value,
    size: resultsPageSize.value
  }
  
  if (resultsTimeRange.value && resultsTimeRange.value.length === 2) {
    params.start_time = resultsTimeRange.value[0].toISOString()
    params.end_time = resultsTimeRange.value[1].toISOString()
  }
  
  const result = await tasksStore.fetchTaskResults(selectedTask.value.id, params)
  
  if (result.success) {
    taskResults.value = result.data.results || result.data
    resultsTotalCount.value = result.data.total || taskResults.value.length
    
    // 计算统计数据
    calculateResultStats()
  } else {
    ElMessage.error(result.message)
  }
  
  resultsLoading.value = false
}

const calculateResultStats = () => {
  const results = taskResults.value
  resultStats.total = results.length
  resultStats.success = results.filter(r => r.status === 'success').length
  resultStats.successRate = resultStats.total > 0 ? 
    ((resultStats.success / resultStats.total) * 100).toFixed(1) : 0
  
  const successResults = results.filter(r => r.status === 'success' && r.duration)
  resultStats.avgDuration = successResults.length > 0 ?
    (successResults.reduce((sum, r) => sum + r.duration, 0) / successResults.length).toFixed(2) : 0
}

const handleResultsSizeChange = (size) => {
  resultsPageSize.value = size
  fetchTaskResults()
}

const handleResultsCurrentChange = (page) => {
  resultsCurrentPage.value = page
  fetchTaskResults()
}

const showResultMetrics = (result) => {
  selectedResult.value = result
  metricsDialogVisible.value = true
}

// 辅助方法
const getStatusTagType = (status) => {
  const types = {
    active: 'success',
    paused: 'warning',
    completed: 'info',
    failed: 'danger'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    active: '活跃',
    paused: '暂停',
    completed: '已完成',
    failed: '失败'
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

const getPriorityText = (priority) => {
  const texts = {
    0: '低',
    1: '普通',
    2: '高',
    3: '紧急'
  }
  return texts[priority] || '普通'
}

const formatFrequency = (seconds) => {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}分钟`
  } else {
    return `${Math.floor(seconds / 3600)}小时`
  }
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  refreshTasks()
})

// 监听器
watch([searchQuery, statusFilter, protocolFilter], () => {
  // 筛选变化时重置到第一页
  currentPage.value = 1
})
</script>

<style scoped>
.tasks-page {
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

.operation-bar {
  margin-bottom: 16px;
}

.operation-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.search-filters {
  display: flex;
  align-items: center;
}

.operation-buttons {
  display: flex;
  gap: 8px;
}

.task-list-card {
  margin-bottom: 16px;
}

.task-name {
  display: flex;
  align-items: center;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.task-detail pre {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}

.task-results .stats-row {
  margin-bottom: 20px;
}

.time-range-selector {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>