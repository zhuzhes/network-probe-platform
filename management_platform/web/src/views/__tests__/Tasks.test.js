import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Tasks from '../Tasks.vue'
import { useTasksStore } from '@/stores/tasks'

// Mock Element Plus components
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn()
  }
}))

// Mock the tasks store
vi.mock('@/stores/tasks', () => ({
  useTasksStore: vi.fn()
}))

describe('Tasks.vue', () => {
  let wrapper
  let mockTasksStore

  beforeEach(() => {
    setActivePinia(createPinia())
    
    mockTasksStore = {
      tasks: [
        {
          id: '1',
          name: 'Test Task 1',
          protocol: 'http',
          target: 'example.com',
          status: 'active',
          frequency: 60,
          timeout: 30,
          priority: 1,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
          next_run: '2024-01-01T01:00:00Z'
        },
        {
          id: '2',
          name: 'Test Task 2',
          protocol: 'icmp',
          target: 'google.com',
          status: 'paused',
          frequency: 120,
          timeout: 10,
          priority: 0,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z'
        }
      ],
      loading: false,
      currentTask: null,
      fetchTasks: vi.fn().mockResolvedValue({ success: true }),
      fetchTask: vi.fn().mockResolvedValue({ success: true }),
      createTask: vi.fn().mockResolvedValue({ success: true }),
      updateTask: vi.fn().mockResolvedValue({ success: true }),
      deleteTask: vi.fn().mockResolvedValue({ success: true }),
      fetchTaskResults: vi.fn().mockResolvedValue({ 
        success: true, 
        data: { results: [], total: 0 } 
      })
    }

    useTasksStore.mockReturnValue(mockTasksStore)

    wrapper = mount(Tasks, {
      global: {
        stubs: {
          'el-card': true,
          'el-input': true,
          'el-select': true,
          'el-option': true,
          'el-button': true,
          'el-table': true,
          'el-table-column': true,
          'el-tag': true,
          'el-dropdown': true,
          'el-dropdown-menu': true,
          'el-dropdown-item': true,
          'el-pagination': true,
          'el-dialog': true,
          'el-form': true,
          'el-form-item': true,
          'el-input-number': true,
          'el-collapse': true,
          'el-collapse-item': true,
          'el-descriptions': true,
          'el-descriptions-item': true,
          'el-statistic': true,
          'el-date-picker': true,
          'el-row': true,
          'el-col': true,
          'el-icon': true
        }
      }
    })
  })

  it('renders the page header correctly', () => {
    expect(wrapper.find('h1').text()).toBe('任务管理')
    expect(wrapper.find('.page-header p').text()).toBe('管理和监控您的拨测任务')
  })

  it('displays tasks in the table', () => {
    expect(wrapper.vm.filteredTasks).toHaveLength(2)
    expect(wrapper.vm.filteredTasks[0].name).toBe('Test Task 1')
    expect(wrapper.vm.filteredTasks[1].name).toBe('Test Task 2')
  })

  it('filters tasks by search query', async () => {
    wrapper.vm.searchQuery = 'Test Task 1'
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredTasks).toHaveLength(1)
    expect(wrapper.vm.filteredTasks[0].name).toBe('Test Task 1')
  })

  it('filters tasks by status', async () => {
    wrapper.vm.statusFilter = 'active'
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredTasks).toHaveLength(1)
    expect(wrapper.vm.filteredTasks[0].status).toBe('active')
  })

  it('filters tasks by protocol', async () => {
    wrapper.vm.protocolFilter = 'http'
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.filteredTasks).toHaveLength(1)
    expect(wrapper.vm.filteredTasks[0].protocol).toBe('http')
  })

  it('formats frequency correctly', () => {
    expect(wrapper.vm.formatFrequency(30)).toBe('30秒')
    expect(wrapper.vm.formatFrequency(120)).toBe('2分钟')
    expect(wrapper.vm.formatFrequency(3600)).toBe('1小时')
  })

  it('gets correct status tag type', () => {
    expect(wrapper.vm.getStatusTagType('active')).toBe('success')
    expect(wrapper.vm.getStatusTagType('paused')).toBe('warning')
    expect(wrapper.vm.getStatusTagType('completed')).toBe('info')
    expect(wrapper.vm.getStatusTagType('failed')).toBe('danger')
  })

  it('gets correct protocol tag type', () => {
    expect(wrapper.vm.getProtocolTagType('icmp')).toBe('primary')
    expect(wrapper.vm.getProtocolTagType('tcp')).toBe('success')
    expect(wrapper.vm.getProtocolTagType('udp')).toBe('warning')
    expect(wrapper.vm.getProtocolTagType('http')).toBe('info')
    expect(wrapper.vm.getProtocolTagType('https')).toBe('danger')
  })

  it('calls fetchTasks on mount', () => {
    expect(mockTasksStore.fetchTasks).toHaveBeenCalled()
  })

  it('handles protocol change correctly', async () => {
    await wrapper.vm.handleProtocolChange('http')
    expect(wrapper.vm.taskForm.port).toBe(80)

    await wrapper.vm.handleProtocolChange('https')
    expect(wrapper.vm.taskForm.port).toBe(443)

    await wrapper.vm.handleProtocolChange('icmp')
    expect(wrapper.vm.taskForm.port).toBe(null)
  })

  it('calculates result stats correctly', () => {
    const mockResults = [
      { status: 'success', duration: 100 },
      { status: 'success', duration: 200 },
      { status: 'error', duration: null },
      { status: 'timeout', duration: null }
    ]
    
    wrapper.vm.taskResults = mockResults
    wrapper.vm.calculateResultStats()
    
    expect(wrapper.vm.resultStats.total).toBe(4)
    expect(wrapper.vm.resultStats.success).toBe(2)
    expect(wrapper.vm.resultStats.successRate).toBe('50.0')
    expect(wrapper.vm.resultStats.avgDuration).toBe('150.00')
  })
})