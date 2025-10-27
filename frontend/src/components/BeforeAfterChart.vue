<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  isTimeOfDay: {
    type: Boolean,
    default: false
  },
  legendBy: {
    type: String,
    default: 'none'
  }
})

const chartContainer = ref(null)
let chart = null
const theme = useTheme()
const themeStore = useThemeStore()

// Before/After colors (colorblind-safe when enabled)
const BEFORE_COLOR = computed(() => {
  // Blue is already colorblind-safe, keep consistent
  return '#1976D2'
})

const AFTER_COLOR = computed(() => {
  if (themeStore.colorblindMode) {
    return '#E69F00' // Colorblind-safe orange
  } else {
    return '#F57C00'  // Standard orange
  }
})

onMounted(() => {
  initializeChart()
  updateChart()
})

// Watch for theme changes
watch(() => theme.global.current.value.dark, () => {
  updateChart()
})

// Watch for colorblind mode changes
watch(() => themeStore.colorblindMode, () => {
  updateChart()
})

onUnmounted(() => {
  if (chart) {
    chart.dispose()
  }
})

watch(() => [props.data, props.isTimeOfDay, props.legendBy], () => {
  nextTick(() => {
    updateChart()
  })
}, { deep: true })

function initializeChart() {
  chart = echarts.init(chartContainer.value)

  // Handle window resize
  window.addEventListener('resize', () => {
    chart?.resize()
    updateChart()
  })
}

function updateChart() {
  if (!chart || !props.data.length) {
    chart?.clear()
    return
  }

  nextTick(() => {
    chart?.resize()
  })

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const isMobile = window.innerWidth < 600

  // Check if data has LEGEND_GROUP column
  const hasLegend = props.data.length > 0 && props.data[0].LEGEND_GROUP !== undefined

  // Separate data by PERIOD column
  const beforeData = props.data.filter(d => d.PERIOD === 'Before')
  const afterData = props.data.filter(d => d.PERIOD === 'After')

  let seriesConfig = []

  if (hasLegend) {
    // Group by legend entity
    const beforeGroups = {}
    const afterGroups = {}

    beforeData.forEach(d => {
      const group = String(d.LEGEND_GROUP || 'Unknown')
      if (!beforeGroups[group]) beforeGroups[group] = []
      const xValue = props.isTimeOfDay ? parseTimeOfDay(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
      beforeGroups[group].push([xValue, Number(d.TRAVEL_TIME_INDEX) || 0])
    })

    afterData.forEach(d => {
      const group = String(d.LEGEND_GROUP || 'Unknown')
      if (!afterGroups[group]) afterGroups[group] = []
      const xValue = props.isTimeOfDay ? parseTimeOfDay(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
      afterGroups[group].push([xValue, Number(d.TRAVEL_TIME_INDEX) || 0])
    })

    // Create series for each legend group
    const allGroups = new Set([...Object.keys(beforeGroups), ...Object.keys(afterGroups)])
    allGroups.forEach(group => {
      // Before series for this group
      seriesConfig.push({
        name: `${group} (Before)`,
        type: 'line',
        data: beforeGroups[group] || [],
        smooth: true,
        lineStyle: { color: BEFORE_COLOR.value, width: 2 },
        itemStyle: { color: BEFORE_COLOR.value },
        symbol: 'circle',
        symbolSize: 3
      })

      // After series for this group
      seriesConfig.push({
        name: `${group} (After)`,
        type: 'line',
        data: afterGroups[group] || [],
        smooth: true,
        lineStyle: { color: AFTER_COLOR.value, width: 2 },
        itemStyle: { color: AFTER_COLOR.value },
        symbol: 'circle',
        symbolSize: 3
      })
    })
  } else {
    // Single before/after series
    const beforeSeries = beforeData.map(d => {
      const xValue = props.isTimeOfDay ? parseTimeOfDay(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
      return [xValue, Number(d.TRAVEL_TIME_INDEX) || 0]
    })

    const afterSeries = afterData.map(d => {
      const xValue = props.isTimeOfDay ? parseTimeOfDay(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
      return [xValue, Number(d.TRAVEL_TIME_INDEX) || 0]
    })

    seriesConfig = [
      {
        name: 'Before',
        type: 'line',
        data: beforeSeries,
        smooth: true,
        lineStyle: { color: BEFORE_COLOR.value, width: 2 },
        itemStyle: { color: BEFORE_COLOR.value },
        symbol: 'circle',
        symbolSize: 4
      },
      {
        name: 'After',
        type: 'line',
        data: afterSeries,
        smooth: true,
        lineStyle: { color: AFTER_COLOR.value, width: 2 },
        itemStyle: { color: AFTER_COLOR.value },
        symbol: 'circle',
        symbolSize: 4
      }
    ]
  }

  // Build x-axis config
  let xAxisConfig
  if (props.isTimeOfDay) {
    const allMinutes = seriesConfig.flatMap(s => s.data.map(d => d[0]))
    const minMinutes = Math.min(...allMinutes)
    const maxMinutes = Math.max(...allMinutes)
    const rangeMinutes = maxMinutes - minMinutes
    const labelInterval = isMobile ? (rangeMinutes <= 360 ? 60 : 120) : (rangeMinutes <= 360 ? 30 : 60)

    xAxisConfig = {
      type: 'value',
      name: 'Time of Day',
      nameLocation: 'middle',
      nameGap: isMobile ? 40 : 35,
      min: minMinutes,
      max: maxMinutes,
      interval: labelInterval,
      axisLabel: {
        color: textColor,
        rotate: isMobile ? 45 : 0,
        fontSize: isMobile ? 10 : 12,
        formatter: (value) => {
          const hours = Math.floor(value / 60)
          const minutes = value % 60
          return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
        }
      },
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' },
      axisLine: { lineStyle: { color: textColor } },
      splitLine: { show: false }
    }
  } else {
    xAxisConfig = {
      type: 'time',
      name: 'Date & Time',
      nameLocation: 'middle',
      nameGap: isMobile ? 40 : 35,
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' },
      axisLabel: {
        color: textColor,
        rotate: isMobile ? 45 : 0,
        fontSize: isMobile ? 10 : 12
      },
      axisLine: { lineStyle: { color: textColor } }
    }
  }

  // Calculate y-axis range
  const allTTI = seriesConfig.flatMap(s => s.data.map(d => d[1]))
  const minTTI = Math.min(...allTTI)
  const maxTTI = Math.max(...allTTI)
  const ttiRange = maxTTI - minTTI
  const rawMin = Math.max(0, minTTI - (ttiRange * 0.02))
  const rawMax = maxTTI + (ttiRange * 0.02)
  const paddedRange = rawMax - rawMin
  const interval = paddedRange < 0.5 ? 0.05 : paddedRange < 1 ? 0.1 : paddedRange < 2 ? 0.2 : 0.5
  const yAxisMin = Math.floor(rawMin / interval) * interval
  const yAxisMax = Math.ceil(rawMax / interval) * interval

  const option = {
    title: {
      text: 'Before/After Comparison',
      left: 'center',
      textStyle: { fontSize: isMobile ? 13 : 16, color: textColor }
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        if (!params.length) return ''
        const xValue = params[0].value[0]
        let timeStr
        if (props.isTimeOfDay) {
          const hours = Math.floor(xValue / 60)
          const minutes = xValue % 60
          timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
        } else {
          const date = new Date(xValue)
          timeStr = date.toLocaleString()
        }
        let tooltip = `<strong>${timeStr}</strong><br/>`
        params.forEach(param => {
          tooltip += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${param.color};margin-right:5px;"></span>${param.seriesName}: ${param.value[1].toFixed(2)}<br/>`
        })
        return tooltip
      }
    },
    legend: {
      type: 'scroll',
      orient: isMobile ? 'horizontal' : 'vertical',
      right: isMobile ? 'auto' : 16,
      left: isMobile ? 'center' : 'auto',
      top: isMobile ? 35 : 20,
      bottom: isMobile ? undefined : 20,
      align: isMobile ? 'auto' : 'left',
      backgroundColor: isMobile ? 'transparent' : (isDark ? 'rgba(38,38,38,0.75)' : 'rgba(255,255,255,0.85)'),
      borderRadius: isMobile ? 0 : 8,
      padding: isMobile ? 0 : [8, 12],
      textStyle: { color: textColor, fontSize: isMobile ? 10 : 12 }
    },
    xAxis: xAxisConfig,
    yAxis: {
      type: 'value',
      name: 'Travel Time Index',
      nameLocation: 'middle',
      nameGap: isMobile ? 45 : 55,
      min: yAxisMin,
      max: yAxisMax,
      interval: interval,
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' },
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        formatter: (value) => value.toFixed(2)
      },
      axisLine: { lineStyle: { color: textColor } },
      splitLine: { lineStyle: { color: isDark ? '#424242' : '#E0E0E0' } }
    },
    series: seriesConfig,
    grid: {
      left: isMobile ? '60px' : '80px',
      right: hasLegend ? (isMobile ? '20px' : '200px') : (isMobile ? '20px' : '50px'),
      bottom: isMobile ? '70px' : '60px',
      top: isMobile ? '100px' : '80px'
    },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }]
  }

  chart.setOption(option, true)
}

function parseTimeOfDay(timeValue) {
  if (typeof timeValue === 'string') {
    const parts = timeValue.split(':')
    return parseInt(parts[0]) * 60 + parseInt(parts[1])
  } else if (typeof timeValue === 'number') {
    const totalSeconds = timeValue / 1000000
    return Math.floor(totalSeconds / 3600) * 60 + Math.floor((totalSeconds % 3600) / 60)
  }
  return 0
}
</script>
