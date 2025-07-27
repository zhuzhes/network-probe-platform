import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref([])
  const loading = ref(false)
  const currentAgent = ref(null)

  const fetchAgents = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.get('/agents', { params })
      agents.value = response.data.agents || response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取代理列表失败' 
      }
    } finally {
      loading.value = false
    }
  }

  const fetchAgent = async (agentId) => {
    try {
      const response = await api.get(`/agents/${agentId}`)
      currentAgent.value = response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取代理详情失败' 
      }
    }
  }

  const createAgent = async (agentData) => {
    try {
      const response = await api.post('/agents', agentData)
      agents.value.unshift(response.data)
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '创建代理失败' 
      }
    }
  }

  const updateAgent = async (agentId, agentData) => {
    try {
      const response = await api.put(`/agents/${agentId}`, agentData)
      const index = agents.value.findIndex(a => a.id === agentId)
      if (index !== -1) {
        agents.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '更新代理失败' 
      }
    }
  }

  const deleteAgent = async (agentId) => {
    try {
      await api.delete(`/agents/${agentId}`)
      agents.value = agents.value.filter(a => a.id !== agentId)
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '删除代理失败' 
      }
    }
  }

  const enableAgent = async (agentId) => {
    try {
      const response = await api.post(`/agents/${agentId}/enable`)
      const index = agents.value.findIndex(a => a.id === agentId)
      if (index !== -1) {
        agents.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '启用代理失败' 
      }
    }
  }

  const disableAgent = async (agentId) => {
    try {
      const response = await api.post(`/agents/${agentId}/disable`)
      const index = agents.value.findIndex(a => a.id === agentId)
      if (index !== -1) {
        agents.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '禁用代理失败' 
      }
    }
  }

  const setMaintenance = async (agentId) => {
    try {
      const response = await api.post(`/agents/${agentId}/maintenance`)
      const index = agents.value.findIndex(a => a.id === agentId)
      if (index !== -1) {
        agents.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '设置维护状态失败' 
      }
    }
  }

  const fetchAgentResources = async (agentId, params = {}) => {
    try {
      const response = await api.get(`/agents/${agentId}/resources`, { params })
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取代理资源失败' 
      }
    }
  }

  const fetchAgentStatistics = async (agentId, days = 30) => {
    try {
      const response = await api.get(`/agents/${agentId}/statistics`, { 
        params: { days } 
      })
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取代理统计失败' 
      }
    }
  }

  const fetchAgentHealth = async (agentId) => {
    try {
      const response = await api.get(`/agents/${agentId}/health`)
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取代理健康状态失败' 
      }
    }
  }

  return {
    agents,
    loading,
    currentAgent,
    fetchAgents,
    fetchAgent,
    createAgent,
    updateAgent,
    deleteAgent,
    enableAgent,
    disableAgent,
    setMaintenance,
    fetchAgentResources,
    fetchAgentStatistics,
    fetchAgentHealth
  }
})