<template>
  <div class="agents-page">
    <div class="page-header">
      <h1>代理管理</h1>
      <p>监控和管理您的拨测代理</p>
    </div>

    <!-- 操作栏 -->
    <el-card class="operation-bar">
      <div class="operation-content">
        <div class="search-filters">
          <el-input
            v-model="searchQuery"
            placeholder="搜索代理名称、IP或位置"
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
            <el-option label="在线" value="online" />
            <el-option label="离线" value="offline" />
            <el-option label="忙碌" value="busy" />
            <el-option label="维护" value="maintenance" />
          </el-select>

          <el-select
            v-model="enabledFilter"
            placeholder="启用状态"
            style="width: 120px; margin-right: 16px"
            clearable
            @change="handleFilter"
          >
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
        </div>

        <div class="operation-buttons">
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon>
            注册代理
          </el-button>
          <el-button @click="refreshAgents">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 代理列表 -->
    <el-card class="agent-list-card">
      <el-table
        v-loading="loading"
        :data="filteredAgents"
        style="width: 100%"
        @row-click="handleRowClick"
      >
        <el-table-column prop="name" label="代理名称" min-width="150">
          <template #default="{ row }">
            <div class="agent-name">
              <span>{{ row.name }}</span>
              <div class="agent-tags">
                <el-tag
                  :type="getStatusTagType(row.status)"
                  size="small"
                  style="margin-left: 8px"
                >
                  {{ getStatusText(row.status) }}
                </el-tag>
                <el-tag
                  v-if="!row.enabled"
                  type="danger"
                  size="small"
                  style="margin-left: 4px"
                >
                  已禁用
                </el-tag>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="ip_address" label="IP地址" width="140" />

        <el-table-column prop="location" label="位置" min-width="150">
          <template #default="{ row }">
            {{ getLocationText(row) }}
          </template>
        </el-table-column>

        <el-table-column prop="isp" label="运营商" width="100">
          <template #default="{ row }">
            {{ row.isp || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="version" label="版本" width="100" />

        <el-table-column label="资源状态" width="120">
          <template #default="{ row }">
            <div class="resource-status">
              <el-progress
                :percentage="row.current_cpu_usage || 0"
                :color="getResourceColor(row.current_cpu_usage)"
                :stroke-width="4"
                :show-text="false"
                style="margin-bottom: 2px"
              />
              <span class="resource-text">CPU: {{ (row.current_cpu_usage || 0).toFixed(1) }}%</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="性能指标" width="120">
          <template #default="{ row }">
            <div class="performance-metrics">
              <div>可用率: {{ (row.availability * 100).toFixed(1) }}%</div>
              <div>成功率: {{ (row.success_rate * 100).toFixed(1) }}%</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="last_heartbeat" label="最后心跳" width="180">
          <template #default="{ row }">
            {{ row.last_heartbeat ? formatDateTime(row.last_heartbeat) : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              @click.stop="viewAgentDetails(row)"
            >
              详情
            </el-button>
            <el-button
              size="small"
              @click.stop="editAgent(row)"
            >
              编辑
            </el-button>
            <el-dropdown @command="handleAgentAction">
              <el-button size="small">
                更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :command="{ action: 'enable', agent: row }" v-if="!row.enabled">
                    启用代理
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'disable', agent: row }" v-if="row.enabled">
                    禁用代理
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'maintenance', agent: row }" v-if="row.status !== 'maintenance'">
                    设为维护
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'resources', agent: row }">
                    资源监控
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'statistics', agent: row }">
                    统计信息
                  </el-dropdown-item>
                  <el-dropdown-item :command="{ action: 'delete', agent: row }" divided>
                    <span style="color: #f56c6c">删除代理</span>
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
          :total="totalAgents"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 创建/编辑代理对话框 -->
    <el-dialog
      v-model="agentDialogVisible"
      :title="isEditing ? '编辑代理' : '注册代理'"
      width="600px"
      @close="resetAgentForm"
    >
      <el-form
        ref="agentFormRef"
        :model="agentForm"
        :rules="agentFormRules"
        label-width="100px"
      >
        <el-form-item label="代理名称" prop="name">
          <el-input v-model="agentForm.name" placeholder="请输入代理名称" />
        </el-form-item>

        <el-form-item label="IP地址" prop="ip_address" v-if="!isEditing">
          <el-input v-model="agentForm.ip_address" placeholder="请输入IP地址" />
        </el-form-item>

        <el-form-item label="版本" prop="version">
          <el-input v-model="agentForm.version" placeholder="请输入版本号" />
        </el-form-item>

        <!-- 位置信息 -->
        <el-collapse v-model="locationConfigOpen">
          <el-collapse-item title="位置信息" name="location">
            <el-form-item label="国家" prop="location.country">
              <el-input v-model="agentForm.location.country" placeholder="如：中国" />
            </el-form-item>

            <el-form-item label="城市" prop="location.city">
              <el-input v-model="agentForm.location.city" placeholder="如：北京" />
            </el-form-item>

            <el-form-item label="运营商" prop="location.isp">
              <el-input v-model="agentForm.location.isp" placeholder="如：电信、联通、移动" />
            </el-form-item>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="纬度" prop="location.latitude">
                  <el-input-number
                    v-model="agentForm.location.latitude"
                    :precision="6"
                    :min="-90"
                    :max="90"
                    placeholder="纬度"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="经度" prop="location.longitude">
                  <el-input-number
                    v-model="agentForm.location.longitude"
                    :precision="6"
                    :min="-180"
                    :max="180"
                    placeholder="经度"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>

        <!-- 能力配置 -->
        <el-collapse v-model="capabilitiesConfigOpen">
          <el-collapse-item title="能力配置" name="capabilities">
            <el-form-item label="支持协议">
              <el-checkbox-group v-model="agentForm.capabilities.protocols">
                <el-checkbox label="icmp">ICMP</el-checkbox>
                <el-checkbox label="tcp">TCP</el-checkbox>
                <el-checkbox label="udp">UDP</el-checkbox>
                <el-checkbox label="http">HTTP</el-checkbox>
                <el-checkbox label="https">HTTPS</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-form-item label="最大并发任务">
              <el-input-number
                v-model="agentForm.capabilities.max_concurrent_tasks"
                :min="1"
                :max="100"
                placeholder="最大并发任务数"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>

        <el-form-item label="启用状态" v-if="isEditing">
          <el-switch v-model="agentForm.enabled" />
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="agentDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitAgentForm" :loading="submitting">
            {{ isEditing ? '更新' : '注册' }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 代理详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="代理详情"
      width="800px"
    >
      <div v-if="selectedAgent" class="agent-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="代理名称">{{ selectedAgent.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(selectedAgent.status)">
              {{ getStatusText(selectedAgent.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="IP地址">{{ selectedAgent.ip_address }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ selectedAgent.version }}</el-descriptions-item>
          <el-descriptions-item label="位置">{{ getLocationText(selectedAgent) }}</el-descriptions-item>
          <el-descriptions-item label="运营商">{{ selectedAgent.isp || '-' }}</el-descriptions-item>
          <el-descriptions-item label="可用率">{{ (selectedAgent.availability * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="成功率">{{ (selectedAgent.success_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="平均响应时间">
            {{ selectedAgent.avg_response_time ? selectedAgent.avg_response_time.toFixed(2) + 'ms' : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="最大并发任务">{{ selectedAgent.max_concurrent_tasks || '-' }}</el-descriptions-item>
          <el-descriptions-item label="注册时间">{{ formatDateTime(selectedAgent.registered_at) }}</el-descriptions-item>
          <el-descriptions-item label="最后心跳">
            {{ selectedAgent.last_heartbeat ? formatDateTime(selectedAgent.last_heartbeat) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="启用状态">
            <el-tag :type="selectedAgent.enabled ? 'success' : 'danger'">
              {{ selectedAgent.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 当前资源状态 -->
        <div style="margin-top: 20px">
          <h4>当前资源状态</h4>
          <el-row :gutter="16">
            <el-col :span="6">
              <el-card class="resource-card">
                <div class="resource-item">
                  <div class="resource-label">CPU使用率</div>
                  <el-progress
                    :percentage="selectedAgent.current_cpu_usage || 0"
                    :color="getResourceColor(selectedAgent.current_cpu_usage)"
                  />
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="resource-card">
                <div class="resource-item">
                  <div class="resource-label">内存使用率</div>
                  <el-progress
                    :percentage="selectedAgent.current_memory_usage || 0"
                    :color="getResourceColor(selectedAgent.current_memory_usage)"
                  />
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="resource-card">
                <div class="resource-item">
                  <div class="resource-label">磁盘使用率</div>
                  <el-progress
                    :percentage="selectedAgent.current_disk_usage || 0"
                    :color="getResourceColor(selectedAgent.current_disk_usage)"
                  />
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="resource-card">
                <div class="resource-item">
                  <div class="resource-label">系统负载</div>
                  <div class="load-value">
                    {{ selectedAgent.current_load_average ? selectedAgent.current_load_average.toFixed(2) : '-' }}
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- 支持的协议 -->
        <div v-if="selectedAgent.capabilities && selectedAgent.capabilities.protocols" style="margin-top: 20px">
          <h4>支持的协议</h4>
          <div class="protocol-tags">
            <el-tag
              v-for="protocol in selectedAgent.capabilities.protocols"
              :key="protocol"
              :type="getProtocolTagType(protocol)"
              style="margin-right: 8px; margin-bottom: 8px"
            >
              {{ protocol.toUpperCase() }}
            </el-tag>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 资源监控对话框 -->
    <el-dialog
      v-model="resourcesDialogVisible"
      title="资源监控"
      width="1000px"
      top="5vh"
    >
      <div v-if="selectedAgent" class="agent-resources">
        <!-- 时间范围选择 -->
        <div class="time-range-selector">
          <el-date-picker
            v-model="resourcesTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            @change="fetchAgentResources"
          />
          <el-button @click="fetchAgentResources" style="margin-left: 16px">刷新</el-button>
        </div>

        <!-- 资源使用历史 -->
        <el-table
          v-loading="resourcesLoading"
          :data="agentResources"
          style="width: 100%; margin-top: 16px"
        >
          <el-table-column prop="timestamp" label="时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.timestamp) }}
            </template>
          </el-table-column>

          <el-table-column prop="cpu_usage" label="CPU使用率" width="120">
            <template #default="{ row }">
              <el-progress
                :percentage="row.cpu_usage"
                :color="getResourceColor(row.cpu_usage)"
                :stroke-width="6"
              />
            </template>
          </el-table-column>

          <el-table-column prop="memory_usage" label="内存使用率" width="120">
            <template #default="{ row }">
              <el-progress
                :percentage="row.memory_usage"
                :color="getResourceColor(row.memory_usage)"
                :stroke-width="6"
              />
            </template>
          </el-table-column>

          <el-table-column prop="disk_usage" label="磁盘使用率" width="120">
            <template #default="{ row }">
              <el-progress
                :percentage="row.disk_usage"
                :color="getResourceColor(row.disk_usage)"
                :stroke-width="6"
              />
            </template>
          </el-table-column>

          <el-table-column prop="load_average" label="系统负载" width="100">
            <template #default="{ row }">
              {{ row.load_average ? row.load_average.toFixed(2) : '-' }}
            </template>
          </el-table-column>

          <el-table-column prop="network_in" label="网络入流量" width="120">
            <template #default="{ row }">
              {{ formatBytes(row.network_in) }}
            </template>
          </el-table-column>

          <el-table-column prop="network_out" label="网络出流量" width="120">
            <template #default="{ row }">
              {{ formatBytes(row.network_out) }}
            </template>
          </el-table-column>
        </el-table>

        <!-- 资源分页 -->
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="resourcesCurrentPage"
            v-model:page-size="resourcesPageSize"
            :page-sizes="[20, 50, 100]"
            :total="resourcesTotalCount"
            layout="total, sizes, prev, pager, next"
            @size-change="handleResourcesSizeChange"
            @current-change="handleResourcesCurrentChange"
          />
        </div>
      </div>
    </el-dialog>

    <!-- 统计信息对话框 -->
    <el-dialog
      v-model="statisticsDialogVisible"
      title="统计信息"
      width="600px"
    >
      <div v-if="selectedAgent && agentStatistics" class="agent-statistics">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-statistic title="总执行任务数" :value="agentStatistics.total_tasks_executed" />
          </el-col>
          <el-col :span="12">
            <el-statistic title="成功任务数" :value="agentStatistics.successful_tasks" />
          </el-col>
        </el-row>

        <el-row :gutter="16" style="margin-top: 20px">
          <el-col :span="12">
            <el-statistic title="失败任务数" :value="agentStatistics.failed_tasks" />
          </el-col>
          <el-col :span="12">
            <el-statistic 
              title="平均执行时间" 
              :value="agentStatistics.avg_execution_time || 0" 
              suffix="ms" 
            />
          </el-col>
        </el-row>

        <el-row :gutter="16" style="margin-top: 20px">
          <el-col :span="12">
            <el-statistic 
              title="运行时间百分比" 
              :value="(agentStatistics.uptime_percentage * 100).toFixed(1)" 
              suffix="%" 
            />
          </el-col>
          <el-col :span="12">
            <el-statistic title="资源警报数" :value="agentStatistics.resource_alerts_count" />
          </el-col>
        </el-row>

        <div style="margin-top: 20px">
          <h4>最近24小时</h4>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-statistic title="执行任务数" :value="agentStatistics.last_24h_tasks" />
            </el-col>
            <el-col :span="12">
              <el-statistic 
                title="成功率" 
                :value="(agentStatistics.last_24h_success_rate * 100).toFixed(1)" 
                suffix="%" 
              />
            </el-col>
          </el-row>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAgentsStore } from '@/stores/agents'
import {
  Search, Plus, Refresh, ArrowDown, Monitor
} from '@element-plus/icons-vue'

// Store
const agentsStore = useAgentsStore()

// 响应式数据
const loading = ref(false)
const searchQuery = ref('')
const statusFilter = ref('')
const enabledFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalAgents = ref(0)

// 对话框状态
const agentDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const resourcesDialogVisible = ref(false)
const statisticsDialogVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)

// 选中的代理
const selectedAgent = ref(null)

// 配置展开状态
const locationConfigOpen = ref([])
const capabilitiesConfigOpen = ref([])

// 代理表单
const agentFormRef = ref()
const agentForm = reactive({
  name: '',
  ip_address: '',
  version: '',
  enabled: true,
  location: {
    country: '',
    city: '',
    isp: '',
    latitude: null,
    longitude: null
  },
  capabilities: {
    protocols: ['icmp', 'tcp', 'udp', 'http', 'https'],
    max_concurrent_tasks: 10
  }
})

// 代理表单验证规则
const agentFormRules = {
  name: [
    { required: true, message: '请输入代理名称', trigger: 'blur' },
    { min: 1, max: 255, message: '代理名称长度在1到255个字符', trigger: 'blur' }
  ],
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    { pattern: /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/, message: '请输入有效的IP地址', trigger: 'blur' }
  ],
  version: [
    { required: true, message: '请输入版本号', trigger: 'blur' }
  ]
}

// 资源监控相关
const agentResources = ref([])
const resourcesLoading = ref(false)
const resourcesCurrentPage = ref(1)
const resourcesPageSize = ref(20)
const resourcesTotalCount = ref(0)
const resourcesTimeRange = ref([])

// 统计信息
const agentStatistics = ref(null)

// 计算属性
const filteredAgents = computed(() => {
  let agents = agentsStore.agents
  
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    agents = agents.filter(agent => 
      agent.name.toLowerCase().includes(query) || 
      agent.ip_address.toLowerCase().includes(query) ||
      getLocationText(agent).toLowerCase().includes(query) ||
      (agent.isp && agent.isp.toLowerCase().includes(query))
    )
  }
  
  if (statusFilter.value) {
    agents = agents.filter(agent => agent.status === statusFilter.value)
  }
  
  if (enabledFilter.value !== '') {
    agents = agents.filter(agent => agent.enabled === enabledFilter.value)
  }
  
  return agents
})

// 方法
const refreshAgents = async () => {
  loading.value = true
  const result = await agentsStore.fetchAgents({
    page: currentPage.value,
    size: pageSize.value
  })
  
  if (!result.success) {
    ElMessage.error(result.message)
  } else {
    totalAgents.value = result.data.total || agentsStore.agents.length
  }
  
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
  refreshAgents()
}

const handleCurrentChange = (page) => {
  currentPage.value = page
  refreshAgents()
}

const handleRowClick = (row) => {
  viewAgentDetails(row)
}

const showCreateDialog = () => {
  isEditing.value = false
  agentDialogVisible.value = true
}

const editAgent = (agent) => {
  isEditing.value = true
  selectedAgent.value = agent
  
  // 填充表单
  Object.assign(agentForm, {
    name: agent.name,
    ip_address: agent.ip_address,
    version: agent.version,
    enabled: agent.enabled,
    location: {
      country: agent.country || '',
      city: agent.city || '',
      isp: agent.isp || '',
      latitude: agent.latitude,
      longitude: agent.longitude
    },
    capabilities: {
      protocols: agent.capabilities?.protocols || ['icmp', 'tcp', 'udp', 'http', 'https'],
      max_concurrent_tasks: agent.max_concurrent_tasks || 10
    }
  })
  
  agentDialogVisible.value = true
}

const viewAgentDetails = (agent) => {
  selectedAgent.value = agent
  detailDialogVisible.value = true
}

const handleAgentAction = async ({ action, agent }) => {
  switch (action) {
    case 'enable':
      await enableAgent(agent)
      break
    case 'disable':
      await disableAgent(agent)
      break
    case 'maintenance':
      await setMaintenance(agent)
      break
    case 'resources':
      await showAgentResources(agent)
      break
    case 'statistics':
      await showAgentStatistics(agent)
      break
    case 'delete':
      await deleteAgent(agent)
      break
  }
}

const enableAgent = async (agent) => {
  const result = await agentsStore.enableAgent(agent.id)
  if (result.success) {
    ElMessage.success('代理已启用')
    refreshAgents()
  } else {
    ElMessage.error(result.message)
  }
}

const disableAgent = async (agent) => {
  const result = await agentsStore.disableAgent(agent.id)
  if (result.success) {
    ElMessage.success('代理已禁用')
    refreshAgents()
  } else {
    ElMessage.error(result.message)
  }
}

const setMaintenance = async (agent) => {
  const result = await agentsStore.setMaintenance(agent.id)
  if (result.success) {
    ElMessage.success('代理已设为维护状态')
    refreshAgents()
  } else {
    ElMessage.error(result.message)
  }
}

const deleteAgent = async (agent) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除代理"${agent.name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    const result = await agentsStore.deleteAgent(agent.id)
    if (result.success) {
      ElMessage.success('代理已删除')
      refreshAgents()
    } else {
      ElMessage.error(result.message)
    }
  } catch {
    // 用户取消删除
  }
}

const submitAgentForm = async () => {
  if (!agentFormRef.value) return
  
  try {
    await agentFormRef.value.validate()
    
    submitting.value = true
    
    // 准备代理数据
    const agentData = {
      name: agentForm.name,
      version: agentForm.version,
      location: agentForm.location.country || agentForm.location.city ? {
        country: agentForm.location.country,
        city: agentForm.location.city,
        isp: agentForm.location.isp,
        latitude: agentForm.location.latitude,
        longitude: agentForm.location.longitude
      } : null,
      capabilities: {
        protocols: agentForm.capabilities.protocols,
        max_concurrent_tasks: agentForm.capabilities.max_concurrent_tasks
      }
    }
    
    if (!isEditing.value) {
      agentData.ip_address = agentForm.ip_address
    } else {
      agentData.enabled = agentForm.enabled
    }
    
    let result
    if (isEditing.value) {
      result = await agentsStore.updateAgent(selectedAgent.value.id, agentData)
    } else {
      result = await agentsStore.createAgent(agentData)
    }
    
    if (result.success) {
      ElMessage.success(isEditing.value ? '代理更新成功' : '代理注册成功')
      agentDialogVisible.value = false
      refreshAgents()
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    submitting.value = false
  }
}

const resetAgentForm = () => {
  if (agentFormRef.value) {
    agentFormRef.value.resetFields()
  }
  
  Object.assign(agentForm, {
    name: '',
    ip_address: '',
    version: '',
    enabled: true,
    location: {
      country: '',
      city: '',
      isp: '',
      latitude: null,
      longitude: null
    },
    capabilities: {
      protocols: ['icmp', 'tcp', 'udp', 'http', 'https'],
      max_concurrent_tasks: 10
    }
  })
  
  locationConfigOpen.value = []
  capabilitiesConfigOpen.value = []
}

const showAgentResources = async (agent) => {
  selectedAgent.value = agent
  resourcesDialogVisible.value = true
  await fetchAgentResources()
}

const fetchAgentResources = async () => {
  if (!selectedAgent.value) return
  
  resourcesLoading.value = true
  
  const params = {
    page: resourcesCurrentPage.value,
    size: resourcesPageSize.value
  }
  
  if (resourcesTimeRange.value && resourcesTimeRange.value.length === 2) {
    params.start_time = resourcesTimeRange.value[0].toISOString()
    params.end_time = resourcesTimeRange.value[1].toISOString()
  }
  
  const result = await agentsStore.fetchAgentResources(selectedAgent.value.id, params)
  
  if (result.success) {
    agentResources.value = result.data.resources || result.data
    resourcesTotalCount.value = result.data.total || agentResources.value.length
  } else {
    ElMessage.error(result.message)
  }
  
  resourcesLoading.value = false
}

const handleResourcesSizeChange = (size) => {
  resourcesPageSize.value = size
  fetchAgentResources()
}

const handleResourcesCurrentChange = (page) => {
  resourcesCurrentPage.value = page
  fetchAgentResources()
}

const showAgentStatistics = async (agent) => {
  selectedAgent.value = agent
  
  const result = await agentsStore.fetchAgentStatistics(agent.id, 30)
  if (result.success) {
    agentStatistics.value = result.data
    statisticsDialogVisible.value = true
  } else {
    ElMessage.error(result.message)
  }
}

// 辅助方法
const getStatusTagType = (status) => {
  const types = {
    online: 'success',
    offline: 'danger',
    busy: 'warning',
    maintenance: 'info'
  }
  return types[status] || 'info'
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

const getLocationText = (agent) => {
  const parts = []
  if (agent.country) parts.push(agent.country)
  if (agent.city) parts.push(agent.city)
  return parts.length > 0 ? parts.join(', ') : '-'
}

const getResourceColor = (percentage) => {
  if (percentage >= 90) return '#f56c6c'
  if (percentage >= 70) return '#e6a23c'
  return '#67c23a'
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

const formatBytes = (bytes) => {
  if (!bytes) return '-'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  if (bytes === 0) return '0 B'
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i]
}

// 生命周期
onMounted(() => {
  refreshAgents()
})

// 监听器
watch([searchQuery, statusFilter, enabledFilter], () => {
  // 筛选变化时重置到第一页
  currentPage.value = 1
})
</script>

<style scoped>
.agents-page {
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

.agent-list-card {
  margin-bottom: 16px;
}

.agent-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-tags {
  display: flex;
  gap: 4px;
}

.resource-status {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.resource-text {
  font-size: 12px;
  color: #606266;
}

.performance-metrics {
  font-size: 12px;
  color: #606266;
}

.performance-metrics div {
  margin-bottom: 2px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.agent-detail .resource-card {
  margin-bottom: 16px;
}

.resource-item {
  text-align: center;
}

.resource-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.load-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin-top: 8px;
}

.protocol-tags {
  display: flex;
  flex-wrap: wrap;
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