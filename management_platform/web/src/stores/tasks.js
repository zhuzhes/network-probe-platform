import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref([])
  const loading = ref(false)
  const currentTask = ref(null)

  const fetchTasks = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.get('/tasks', { params })
      tasks.value = response.data.items || response.data
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取任务列表失败' 
      }
    } finally {
      loading.value = false
    }
  }

  const fetchTask = async (taskId) => {
    try {
      const response = await api.get(`/tasks/${taskId}`)
      currentTask.value = response.data
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取任务详情失败' 
      }
    }
  }

  const createTask = async (taskData) => {
    try {
      const response = await api.post('/tasks', taskData)
      tasks.value.unshift(response.data)
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '创建任务失败' 
      }
    }
  }

  const updateTask = async (taskId, taskData) => {
    try {
      const response = await api.put(`/tasks/${taskId}`, taskData)
      const index = tasks.value.findIndex(t => t.id === taskId)
      if (index !== -1) {
        tasks.value[index] = response.data
      }
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '更新任务失败' 
      }
    }
  }

  const deleteTask = async (taskId) => {
    try {
      await api.delete(`/tasks/${taskId}`)
      tasks.value = tasks.value.filter(t => t.id !== taskId)
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '删除任务失败' 
      }
    }
  }

  const fetchTaskResults = async (taskId, params = {}) => {
    try {
      const response = await api.get(`/tasks/${taskId}/results`, { params })
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取任务结果失败' 
      }
    }
  }

  return {
    tasks,
    loading,
    currentTask,
    fetchTasks,
    fetchTask,
    createTask,
    updateTask,
    deleteTask,
    fetchTaskResults
  }
})