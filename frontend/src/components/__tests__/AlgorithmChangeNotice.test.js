import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import { setupTestPinia } from '@/test-utils'

vi.mock('@/services/api', () => ({
  default: {
    getAlgorithmChanges: vi.fn()
  }
}))

import ApiService from '@/services/api'
import AlgorithmChangeNotice from '@/components/AlgorithmChangeNotice.vue'
import { useAlgorithmChangesStore } from '@/stores/algorithmChanges'

const EVENTS = [
  {
    event_date: '2025-09-30', start_date: '2025-09-30', end_date: '2025-09-30',
    peak_local: '2025-09-30T11:15:00', peak_timestamp: '2025-09-30T11:15:00-07:00', segments: 455
  },
  {
    event_date: '2026-10-22', start_date: '2026-10-21', end_date: '2026-10-22',
    peak_local: '2026-10-22T14:30:00', peak_timestamp: '2026-10-22T14:30:00-07:00', segments: 1099
  }
]

function mountNotice(ranges, pinia) {
  return mount(AlgorithmChangeNotice, {
    props: { ranges },
    global: { plugins: [pinia, createVuetify()] }
  })
}

describe('AlgorithmChangeNotice', () => {
  let pinia

  beforeEach(() => {
    pinia = setupTestPinia()
    ApiService.getAlgorithmChanges.mockReset()
    ApiService.getAlgorithmChanges.mockResolvedValue({ events: EVENTS })
  })

  it('shows a warning when the range includes an event day', async () => {
    const wrapper = mountNotice([{ start: '2026-10-20', end: '2026-10-21' }], pinia)
    await flushPromises()
    const notice = wrapper.find('[data-testid="algorithm-change-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toBe('INRIX algorithm change Oct 21–22, 2026 (~1,100 segments). Data across it may not be comparable.')
  })

  it('lists each event when the range spans several', async () => {
    const wrapper = mountNotice([{ start: '2025-09-01', end: '2026-11-30' }], pinia)
    await flushPromises()
    const items = wrapper.findAll('li')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Sep 30, 2025')
    expect(items[1].text()).toContain('Oct 21–22, 2026')
    expect(wrapper.text()).toContain('Data across them may not be comparable.')
  })

  it('stays hidden when the range does not touch an event', async () => {
    const wrapper = mountNotice([{ start: '2026-11-01', end: '2026-11-20' }], pinia)
    await flushPromises()
    expect(wrapper.find('[data-testid="algorithm-change-notice"]').exists()).toBe(false)
  })

  it('reacts to range changes and loads events only once', async () => {
    const wrapper = mountNotice([{ start: '2026-11-01', end: '2026-11-20' }], pinia)
    mountNotice([{ start: '2026-11-01', end: '2026-11-20' }], pinia)
    await flushPromises()
    expect(wrapper.find('[data-testid="algorithm-change-notice"]').exists()).toBe(false)

    await wrapper.setProps({ ranges: [{ start: '2026-10-22', end: '2026-11-20' }] })
    expect(wrapper.find('[data-testid="algorithm-change-notice"]').exists()).toBe(true)
    expect(ApiService.getAlgorithmChanges).toHaveBeenCalledTimes(1)
  })

  it('stays hidden when the lookup fails', async () => {
    ApiService.getAlgorithmChanges.mockRejectedValue(new Error('502'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mountNotice([{ start: '2026-10-01', end: '2026-10-31' }], pinia)
    await flushPromises()
    expect(wrapper.find('[data-testid="algorithm-change-notice"]').exists()).toBe(false)
    expect(useAlgorithmChangesStore().events).toEqual([])
    warn.mockRestore()
  })
})
