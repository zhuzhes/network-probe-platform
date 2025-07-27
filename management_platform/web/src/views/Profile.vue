<template>
  <div class="profile-page">
    <div class="page-header">
      <h1>账户管理</h1>
      <p>管理您的个人资料和账户设置</p>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：个人信息 -->
      <el-col :span="12">
        <el-card class="profile-card">
          <template #header>
            <div class="card-header">
              <span>个人信息</span>
              <el-button size="small" @click="editProfile">
                <el-icon><Edit /></el-icon>
                编辑
              </el-button>
            </div>
          </template>

          <div v-if="userInfo" class="profile-info">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="用户名">{{ userInfo.username }}</el-descriptions-item>
              <el-descriptions-item label="邮箱">{{ userInfo.email }}</el-descriptions-item>
              <el-descriptions-item label="公司名称">{{ userInfo.company_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="用户角色">
                <el-tag :type="userInfo.role === 'admin' ? 'danger' : 'primary'">
                  {{ userInfo.role === 'admin' ? '管理员' : '企业用户' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="账户状态">
                <el-tag :type="userInfo.status === 'active' ? 'success' : 'danger'">
                  {{ userInfo.status === 'active' ? '正常' : '禁用' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="注册时间">{{ formatDateTime(userInfo.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="最后登录">
                {{ userInfo.last_login ? formatDateTime(userInfo.last_login) : '从未登录' }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>

        <!-- 密码修改 -->
        <el-card class="password-card">
          <template #header>
            <span>密码管理</span>
          </template>

          <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="100px">
            <el-form-item label="当前密码" prop="oldPassword">
              <el-input
                v-model="passwordForm.oldPassword"
                type="password"
                placeholder="请输入当前密码"
                show-password
              />
            </el-form-item>

            <el-form-item label="新密码" prop="newPassword">
              <el-input
                v-model="passwordForm.newPassword"
                type="password"
                placeholder="请输入新密码"
                show-password
              />
            </el-form-item>

            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="passwordForm.confirmPassword"
                type="password"
                placeholder="请再次输入新密码"
                show-password
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="changePassword" :loading="passwordChanging">
                修改密码
              </el-button>
              <el-button @click="resetPasswordForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：账户余额和API密钥 -->
      <el-col :span="12">
        <!-- 账户余额 -->
        <el-card class="credits-card">
          <template #header>
            <div class="card-header">
              <span>账户余额</span>
              <el-button size="small" type="primary" @click="showRechargeDialog">
                <el-icon><Plus /></el-icon>
                充值
              </el-button>
            </div>
          </template>

          <div class="credits-info">
            <div class="credits-display">
              <div class="credits-amount">{{ userInfo?.credits || 0 }}</div>
              <div class="credits-label">可用点数</div>
            </div>

            <div class="credits-actions">
              <el-button @click="showTransactionHistory">
                <el-icon><List /></el-icon>
                交易记录
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- API密钥管理 -->
        <el-card class="api-key-card">
          <template #header>
            <span>API密钥管理</span>
          </template>

          <div class="api-key-info">
            <div v-if="userInfo?.has_api_key" class="api-key-exists">
              <el-alert
                title="您已拥有API密钥"
                type="success"
                :closable="false"
                show-icon
              />
              <div class="api-key-actions">
                <el-button @click="regenerateApiKey" :loading="apiKeyGenerating">
                  <el-icon><Refresh /></el-icon>
                  重新生成
                </el-button>
                <el-button type="danger" @click="revokeApiKey" :loading="apiKeyRevoking">
                  <el-icon><Delete /></el-icon>
                  撤销密钥
                </el-button>
              </div>
            </div>

            <div v-else class="api-key-none">
              <el-alert
                title="您还没有API密钥"
                type="info"
                :closable="false"
                show-icon
              />
              <div class="api-key-actions">
                <el-button type="primary" @click="generateApiKey" :loading="apiKeyGenerating">
                  <el-icon><Key /></el-icon>
                  生成API密钥
                </el-button>
              </div>
            </div>

            <div class="api-key-usage">
              <h4>API使用说明</h4>
              <p>API密钥用于程序化访问拨测服务，请妥善保管您的密钥。</p>
              <ul>
                <li>在HTTP请求头中添加：<code>Authorization: Bearer YOUR_API_KEY</code></li>
                <li>API文档地址：<a href="/docs" target="_blank">/docs</a></li>
                <li>如果密钥泄露，请立即重新生成或撤销</li>
              </ul>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 编辑个人信息对话框 -->
    <el-dialog
      v-model="profileDialogVisible"
      title="编辑个人信息"
      width="500px"
    >
      <el-form :model="profileForm" :rules="profileRules" ref="profileFormRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="profileForm.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="profileForm.email" placeholder="请输入邮箱地址" />
        </el-form-item>

        <el-form-item label="公司名称" prop="company_name">
          <el-input v-model="profileForm.company_name" placeholder="请输入公司名称（可选）" />
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="profileDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="updateProfile" :loading="profileUpdating">
            保存
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 充值对话框 -->
    <el-dialog
      v-model="rechargeDialogVisible"
      title="账户充值"
      width="500px"
    >
      <el-form :model="rechargeForm" :rules="rechargeRules" ref="rechargeFormRef" label-width="100px">
        <el-form-item label="充值金额" prop="amount">
          <el-input-number
            v-model="rechargeForm.amount"
            :min="1"
            :max="10000"
            :precision="2"
            placeholder="请输入充值金额"
            style="width: 100%"
          />
          <div class="amount-tips">
            <span>最小充值金额：1点数，最大充值金额：10000点数</span>
          </div>
        </el-form-item>

        <el-form-item label="支付方式" prop="payment_method">
          <el-radio-group v-model="rechargeForm.payment_method">
            <el-radio label="alipay">支付宝</el-radio>
            <el-radio label="wechat">微信支付</el-radio>
            <el-radio label="bank">银行转账</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="rechargeForm.description"
            type="textarea"
            :rows="3"
            placeholder="充值备注（可选）"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="rechargeDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitRecharge" :loading="recharging">
            确认充值
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 交易记录对话框 -->
    <el-dialog
      v-model="transactionDialogVisible"
      title="交易记录"
      width="800px"
      top="5vh"
    >
      <el-table
        v-loading="transactionLoading"
        :data="transactions"
        style="width: 100%"
      >
        <el-table-column prop="created_at" label="交易时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column prop="type" label="交易类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTransactionTagType(row.type)">
              {{ getTransactionTypeText(row.type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="amount" label="金额" width="100">
          <template #default="{ row }">
            <span :class="{ 'amount-positive': row.amount > 0, 'amount-negative': row.amount < 0 }">
              {{ row.amount > 0 ? '+' : '' }}{{ row.amount }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="描述" min-width="200" />

        <el-table-column prop="reference_id" label="交易单号" width="150" />
      </el-table>

      <!-- 交易记录分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="transactionCurrentPage"
          v-model:page-size="transactionPageSize"
          :page-sizes="[10, 20, 50]"
          :total="transactionTotalCount"
          layout="total, sizes, prev, pager, next"
          @size-change="handleTransactionSizeChange"
          @current-change="handleTransactionCurrentChange"
        />
      </div>
    </el-dialog>

    <!-- API密钥显示对话框 -->
    <el-dialog
      v-model="apiKeyDialogVisible"
      title="API密钥"
      width="600px"
    >
      <div class="api-key-display">
        <el-alert
          title="请妥善保管您的API密钥，此密钥只会显示一次！"
          type="warning"
          :closable="false"
          show-icon
        />

        <div class="api-key-content">
          <el-input
            v-model="generatedApiKey"
            readonly
            type="textarea"
            :rows="3"
            placeholder="API密钥将在这里显示"
          >
            <template #append>
              <el-button @click="copyApiKey">
                <el-icon><CopyDocument /></el-icon>
                复制
              </el-button>
            </template>
          </el-input>
        </div>

        <div class="api-key-info">
          <p><strong>生成时间：</strong>{{ apiKeyCreatedAt ? formatDateTime(apiKeyCreatedAt) : '-' }}</p>
          <p><strong>使用方法：</strong>在HTTP请求头中添加 <code>Authorization: Bearer YOUR_API_KEY</code></p>
        </div>
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button type="primary" @click="apiKeyDialogVisible = false">
            我已保存密钥
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'
import {
  User, Edit, Plus, List, Refresh, Delete, Key, CopyDocument
} from '@element-plus/icons-vue'

const authStore = useAuthStore()
const usersStore = useUsersStore()

// 响应式数据
const userInfo = ref(null)
const profileDialogVisible = ref(false)
const rechargeDialogVisible = ref(false)
const transactionDialogVisible = ref(false)
const apiKeyDialogVisible = ref(false)

// 加载状态
const profileUpdating = ref(false)
const passwordChanging = ref(false)
const recharging = ref(false)
const transactionLoading = ref(false)
const apiKeyGenerating = ref(false)
const apiKeyRevoking = ref(false)

// 表单引用
const profileFormRef = ref()
const passwordFormRef = ref()
const rechargeFormRef = ref()

// 个人信息表单
const profileForm = reactive({
  username: '',
  email: '',
  company_name: ''
})

const profileRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在3到50个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
  ]
}

// 密码修改表单
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const passwordRules = {
  oldPassword: [
    { required: true, message: '请输入当前密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码长度至少8位', trigger: 'blur' },
    { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/, message: '密码必须包含大小写字母和数字', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.newPassword) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

// 充值表单
const rechargeForm = reactive({
  amount: 100,
  payment_method: 'alipay',
  description: ''
})

const rechargeRules = {
  amount: [
    { required: true, message: '请输入充值金额', trigger: 'blur' },
    { type: 'number', min: 1, max: 10000, message: '充值金额必须在1-10000之间', trigger: 'blur' }
  ],
  payment_method: [
    { required: true, message: '请选择支付方式', trigger: 'change' }
  ]
}

// 交易记录
const transactions = ref([])
const transactionCurrentPage = ref(1)
const transactionPageSize = ref(20)
const transactionTotalCount = ref(0)

// API密钥
const generatedApiKey = ref('')
const apiKeyCreatedAt = ref(null)

// 方法
const loadUserInfo = async () => {
  if (!authStore.user) return
  
  const result = await usersStore.fetchUser(authStore.user.id)
  if (result.success) {
    userInfo.value = result.data
  } else {
    ElMessage.error(result.message)
  }
}

const editProfile = () => {
  if (!userInfo.value) return
  
  Object.assign(profileForm, {
    username: userInfo.value.username,
    email: userInfo.value.email,
    company_name: userInfo.value.company_name || ''
  })
  
  profileDialogVisible.value = true
}

const updateProfile = async () => {
  if (!profileFormRef.value) return
  
  try {
    await profileFormRef.value.validate()
    
    profileUpdating.value = true
    
    const result = await usersStore.updateUser(authStore.user.id, profileForm)
    if (result.success) {
      ElMessage.success('个人信息更新成功')
      profileDialogVisible.value = false
      await loadUserInfo()
      // 更新auth store中的用户信息
      authStore.user = { ...authStore.user, ...result.data }
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    profileUpdating.value = false
  }
}

const changePassword = async () => {
  if (!passwordFormRef.value) return
  
  try {
    await passwordFormRef.value.validate()
    
    passwordChanging.value = true
    
    const result = await usersStore.changePassword(authStore.user.id, {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword
    })
    
    if (result.success) {
      ElMessage.success('密码修改成功')
      resetPasswordForm()
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    passwordChanging.value = false
  }
}

const resetPasswordForm = () => {
  if (passwordFormRef.value) {
    passwordFormRef.value.resetFields()
  }
  
  Object.assign(passwordForm, {
    oldPassword: '',
    newPassword: '',
    confirmPassword: ''
  })
}

const showRechargeDialog = () => {
  rechargeDialogVisible.value = true
}

const submitRecharge = async () => {
  if (!rechargeFormRef.value) return
  
  try {
    await rechargeFormRef.value.validate()
    
    recharging.value = true
    
    const result = await usersStore.rechargeCredits(authStore.user.id, rechargeForm)
    if (result.success) {
      ElMessage.success('充值成功')
      rechargeDialogVisible.value = false
      await loadUserInfo()
      // 更新auth store中的用户余额
      authStore.user.credits = userInfo.value.credits
    } else {
      ElMessage.error(result.message)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    recharging.value = false
  }
}

const showTransactionHistory = async () => {
  transactionDialogVisible.value = true
  await fetchTransactions()
}

const fetchTransactions = async () => {
  transactionLoading.value = true
  
  const result = await usersStore.fetchTransactions(authStore.user.id, {
    page: transactionCurrentPage.value,
    size: transactionPageSize.value
  })
  
  if (result.success) {
    transactions.value = result.data.transactions || []
    transactionTotalCount.value = result.data.total || 0
  } else {
    ElMessage.error(result.message)
  }
  
  transactionLoading.value = false
}

const handleTransactionSizeChange = (size) => {
  transactionPageSize.value = size
  fetchTransactions()
}

const handleTransactionCurrentChange = (page) => {
  transactionCurrentPage.value = page
  fetchTransactions()
}

const generateApiKey = async () => {
  apiKeyGenerating.value = true
  
  const result = await usersStore.generateApiKey(authStore.user.id)
  if (result.success) {
    generatedApiKey.value = result.data.api_key
    apiKeyCreatedAt.value = result.data.created_at
    apiKeyDialogVisible.value = true
    await loadUserInfo()
  } else {
    ElMessage.error(result.message)
  }
  
  apiKeyGenerating.value = false
}

const regenerateApiKey = async () => {
  try {
    await ElMessageBox.confirm(
      '重新生成API密钥将使旧密钥失效，确定要继续吗？',
      '确认重新生成',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await generateApiKey()
  } catch {
    // 用户取消
  }
}

const revokeApiKey = async () => {
  try {
    await ElMessageBox.confirm(
      '撤销API密钥后将无法恢复，确定要继续吗？',
      '确认撤销',
      {
        confirmButtonText: '撤销',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    apiKeyRevoking.value = true
    
    const result = await usersStore.revokeApiKey(authStore.user.id)
    if (result.success) {
      ElMessage.success('API密钥已撤销')
      await loadUserInfo()
    } else {
      ElMessage.error(result.message)
    }
    
    apiKeyRevoking.value = false
  } catch {
    // 用户取消
  }
}

const copyApiKey = async () => {
  try {
    await navigator.clipboard.writeText(generatedApiKey.value)
    ElMessage.success('API密钥已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败，请手动复制')
  }
}

// 辅助方法
const getTransactionTagType = (type) => {
  const types = {
    recharge: 'success',
    consumption: 'warning',
    refund: 'info',
    voucher: 'primary'
  }
  return types[type] || 'info'
}

const getTransactionTypeText = (type) => {
  const texts = {
    recharge: '充值',
    consumption: '消费',
    refund: '退款',
    voucher: '抵用券'
  }
  return texts[type] || type
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  loadUserInfo()
})
</script>

<style scoped>
.profile-page {
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

.profile-card,
.password-card,
.credits-card,
.api-key-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.profile-info {
  padding: 16px 0;
}

.credits-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
}

.credits-display {
  text-align: center;
}

.credits-amount {
  font-size: 36px;
  font-weight: bold;
  color: #409EFF;
  line-height: 1;
  margin-bottom: 8px;
}

.credits-label {
  font-size: 14px;
  color: #909399;
}

.api-key-info {
  padding: 16px 0;
}

.api-key-exists,
.api-key-none {
  margin-bottom: 20px;
}

.api-key-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}

.api-key-usage {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #EBEEF5;
}

.api-key-usage h4 {
  margin: 0 0 12px 0;
  color: #303133;
}

.api-key-usage p {
  margin: 0 0 12px 0;
  color: #606266;
}

.api-key-usage ul {
  margin: 0;
  padding-left: 20px;
  color: #606266;
}

.api-key-usage li {
  margin-bottom: 8px;
}

.api-key-usage code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.amount-tips {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.amount-positive {
  color: #67C23A;
}

.amount-negative {
  color: #F56C6C;
}

.api-key-display {
  padding: 16px 0;
}

.api-key-content {
  margin: 20px 0;
}

.api-key-info {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #EBEEF5;
}

.api-key-info p {
  margin: 8px 0;
  color: #606266;
}

.api-key-info code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>