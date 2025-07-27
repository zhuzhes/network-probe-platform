import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useUsersStore = defineStore('users', () => {
  const users = ref([])
  const loading = ref(false)
  const currentUser = ref(null)

  const fetchUsers = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.get('/users', { params })
      users.value = response.data.users || response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取用户列表失败' 
      }
    } finally {
      loading.value = false
    }
  }

  const fetchUser = async (userId) => {
    try {
      const response = await api.get(`/users/${userId}`)
      currentUser.value = response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取用户信息失败' 
      }
    }
  }

  const updateUser = async (userId, userData) => {
    try {
      const response = await api.put(`/users/${userId}`, userData)
      const index = users.value.findIndex(u => u.id === userId)
      if (index !== -1) {
        users.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '更新用户信息失败' 
      }
    }
  }

  const changePassword = async (userId, passwordData) => {
    try {
      await api.post(`/users/${userId}/change-password`, passwordData)
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '修改密码失败' 
      }
    }
  }

  const rechargeCredits = async (userId, rechargeData) => {
    try {
      const response = await api.post(`/users/${userId}/recharge`, rechargeData)
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '充值失败' 
      }
    }
  }

  const fetchTransactions = async (userId, params = {}) => {
    try {
      const response = await api.get(`/users/${userId}/transactions`, { params })
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取交易记录失败' 
      }
    }
  }

  const generateApiKey = async (userId) => {
    try {
      const response = await api.post(`/users/${userId}/api-key`)
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '生成API密钥失败' 
      }
    }
  }

  const revokeApiKey = async (userId) => {
    try {
      await api.delete(`/users/${userId}/api-key`)
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '撤销API密钥失败' 
      }
    }
  }

  return {
    users,
    loading,
    currentUser,
    fetchUsers,
    fetchUser,
    updateUser,
    changePassword,
    rechargeCredits,
    fetchTransactions,
    generateApiKey,
    revokeApiKey
  }
})