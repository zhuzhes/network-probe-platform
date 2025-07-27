import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useAnalyticsStore = defineStore('analytics', () => {
  const loading = ref(false)
  const statistics = ref(null)
  const results = ref([])

  const fetchStatistics = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.get('/analytics/statistics', { params })
      statistics.value = response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取统计数据失败' 
      }
    } finally {
      loading.value = false
    }
  }

  const fetchResults = async (params = {}) => {
    loading.value = true
    try {
      const response = await api.get('/analytics/results', { params })
      results.value = response.data.results || response.data
      return { success: true, data: response.data }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '获取结果数据失败' 
      }
    } finally {
      loading.value = false
    }
  }

  const exportData = async (params = {}) => {
    try {
      const response = await api.post('/analytics/export', params, {
        responseType: 'blob'
      })
      
      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      
      // 从响应头获取文件名
      const contentDisposition = response.headers['content-disposition']
      let filename = 'export.csv'
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=(.+)/)
        if (filenameMatch) {
          filename = filenameMatch[1].replace(/"/g, '')
        }
      }
      
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      
      return { success: true }
    } catch (error) {
      return { 
        success: false, 
        message: error.response?.data?.detail || '导出数据失败' 
      }
    }
  }

  return {
    loading,
    statistics,
    results,
    fetchStatistics,
    fetchResults,
    exportData
  }
})