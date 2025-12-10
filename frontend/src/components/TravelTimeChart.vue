<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, onActivated } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  selectedSignal: {
    type: [String, Number, null],
    default: null
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
let windowResizeHandler = null
let needsResizeAfterShow = false
const theme = useTheme()
const themeStore = useThemeStore()

onMounted(() => {
  initializeChart()
  updateChart()
})

onActivated(() => {
  // When returning from keep-alive, ensure the chart fills the container
  nextTick(() => {
    requestChartResize(true)
    if (needsResizeAfterShow) {
      requestAnimationFrame(() => requestChartResize(true))
    }
  })
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
  if (windowResizeHandler) {
    window.removeEventListener('resize', windowResizeHandler)
    windowResizeHandler = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
  needsResizeAfterShow = false
})

watch(() => [props.data, props.selectedSignal, props.isTimeOfDay, props.legendBy], () => {
  const watchStart = performance.now()
  // Defer chart update to next tick to avoid updating during render
  nextTick(() => {
    const tickStart = performance.now()
    updateChart()
    const tickEnd = performance.now()
  })
}, { deep: true })

function initializeChart() {
  if (!chartContainer.value || chart) {
    return
  }

  chart = echarts.init(chartContainer.value)

  // Handle window resize
  windowResizeHandler = () => {
    requestChartResize()
    // Re-render chart with updated responsive settings
    updateChart()
  }
  window.addEventListener('resize', windowResizeHandler)
}

function requestChartResize(immediate = false) {
  const resizeAction = () => {
    if (!chart || !chartContainer.value) {
      return
    }

    const { offsetWidth, offsetHeight } = chartContainer.value
    if (!offsetWidth || !offsetHeight) {
      needsResizeAfterShow = true
      return
    }

    chart.resize()
    needsResizeAfterShow = false
  }

  if (immediate) {
    resizeAction()
  } else {
    nextTick(resizeAction)
  }
}

function updateChart() {
  const t0 = performance.now()
  if (!chart || !props.data.length) {
    chart?.clear()
    return
  }

  // Use nextTick to ensure chart resize happens after DOM updates
  requestChartResize()

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const backgroundColor = isDark ? 'transparent' : 'transparent'

  // Check if data has LEGEND_GROUP column
  const hasLegend = props.data.length > 0 && props.data[0].LEGEND_GROUP !== undefined

  // Detect mobile screen size
  const isMobile = window.innerWidth < 600

  let xAxisConfig, tooltipFormatter
  let seriesData = []

  if (props.isTimeOfDay) {
    // Time-of-day mode: use TIME_OF_DAY field
    // Check if data actually has TIME_OF_DAY field
    const hasTimeOfDay = props.data.some(d => {
      const value = d?.TIME_OF_DAY
      return value !== null && value !== undefined && value !== ''
    })
    if (!hasTimeOfDay) {
      console.warn('📊 CHART: isTimeOfDay=true but data missing TIME_OF_DAY field, skipping render')
      chart?.clear()
      return
    }

    // Group data by LEGEND_GROUP if present
    if (hasLegend) {
      const groupedData = {}
      props.data.forEach(d => {
        const group = String(d.LEGEND_GROUP || 'Unknown')
        if (!groupedData[group]) {
          groupedData[group] = []
        }

        let hours, minutes
        if (typeof d.TIME_OF_DAY === 'string') {
          const timeParts = d.TIME_OF_DAY.split(':')
          hours = parseInt(timeParts[0])
          minutes = parseInt(timeParts[1])
        } else if (d.TIME_OF_DAY instanceof Date) {
          hours = d.TIME_OF_DAY.getHours()
          minutes = d.TIME_OF_DAY.getMinutes()
        } else if (typeof d.TIME_OF_DAY === 'number') {
          const totalSeconds = d.TIME_OF_DAY / 1000000
          hours = Math.floor(totalSeconds / 3600)
          minutes = Math.floor((totalSeconds % 3600) / 60)
        } else {
          hours = 0
          minutes = 0
        }

        const totalMinutes = hours * 60 + minutes
        groupedData[group].push([totalMinutes, Number(d.TRAVEL_TIME_INDEX) || 0])
      })

      seriesData = Object.entries(groupedData)
    } else {
      // Single series
      const singleSeriesData = props.data.map(d => {
        let hours, minutes
        if (typeof d.TIME_OF_DAY === 'string') {
          const timeParts = d.TIME_OF_DAY.split(':')
          hours = parseInt(timeParts[0])
          minutes = parseInt(timeParts[1])
        } else if (d.TIME_OF_DAY instanceof Date) {
          hours = d.TIME_OF_DAY.getHours()
          minutes = d.TIME_OF_DAY.getMinutes()
        } else if (typeof d.TIME_OF_DAY === 'number') {
          const totalSeconds = d.TIME_OF_DAY / 1000000
          hours = Math.floor(totalSeconds / 3600)
          minutes = Math.floor((totalSeconds % 3600) / 60)
        } else {
          hours = 0
          minutes = 0
        }
        const totalMinutes = hours * 60 + minutes
        return [totalMinutes, Number(d.TRAVEL_TIME_INDEX) || 0]
      })
      seriesData = [['All Data', singleSeriesData]]
    }

    // Calculate min/max for x-axis range from all series
    const allMinutes = seriesData.flatMap(([_, data]) => data.map(d => d[0]))
    const minMinutes = Math.min(...allMinutes)
    const maxMinutes = Math.max(...allMinutes)

    // Determine appropriate interval for x-axis labels based on data range
    const rangeMinutes = maxMinutes - minMinutes
    let labelInterval
    if (isMobile) {
      // Fewer labels on mobile
      if (rangeMinutes <= 120) {
        labelInterval = 30 // Every 30 minutes
      } else if (rangeMinutes <= 360) {
        labelInterval = 60 // Every hour
      } else if (rangeMinutes <= 720) {
        labelInterval = 120 // Every 2 hours
      } else {
        labelInterval = 240 // Every 4 hours
      }
    } else {
      // Desktop
      if (rangeMinutes <= 120) {
        labelInterval = 15 // Every 15 minutes
      } else if (rangeMinutes <= 360) {
        labelInterval = 30 // Every 30 minutes
      } else if (rangeMinutes <= 720) {
        labelInterval = 60 // Every hour
      } else {
        labelInterval = 120 // Every 2 hours
      }
    }

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
        formatter: function(value) {
          const hours = Math.floor(value / 60)
          const minutes = value % 60
          return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
        }
      },
      nameTextStyle: {
        color: textColor,
        fontSize: isMobile ? 12 : 13,
        fontWeight: 'bold'
      },
      axisLine: {
        lineStyle: {
          color: textColor
        }
      },
      splitLine: {
        show: false  // Remove vertical grid lines to match date/time chart
      }
    }

    tooltipFormatter = function(params) {
      if (params.length > 0) {
        const data = params[0]
        const totalMinutes = data.value[0]
        const hours = Math.floor(totalMinutes / 60)
        const minutes = totalMinutes % 60
        const time = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`

        // Build tooltip with all series at this time point
        let tooltip = `<strong>${time}</strong><br/>`
        params.forEach(param => {
          const seriesName = param.seriesName
          const tti = param.value[1].toFixed(2)
          const color = param.color
          tooltip += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${color};margin-right:5px;"></span>${seriesName}: ${tti}<br/>`
        })
        return tooltip
      }
      return ''
    }
  } else {
    // Regular timestamp mode
    if (hasLegend) {
      const groupedData = {}
      props.data.forEach(d => {
        const group = String(d.LEGEND_GROUP || 'Unknown')
        if (!groupedData[group]) {
          groupedData[group] = []
        }
        groupedData[group].push([
          new Date(d.TIMESTAMP).getTime(),
          Number(d.TRAVEL_TIME_INDEX) || 0
        ])
      })
      seriesData = Object.entries(groupedData)
    } else {
      // Single series
      const singleSeriesData = props.data.map(d => [
        new Date(d.TIMESTAMP).getTime(),
        Number(d.TRAVEL_TIME_INDEX) || 0
      ])
      seriesData = [['All Data', singleSeriesData]]
    }

    // Determine aggregation level from data timestamps
    let xAxisName = 'Time'
    if (props.data.length >= 2) {
      const timestamps = props.data.slice(0, 10).map(d => new Date(d.TIMESTAMP).getTime())
      const intervals = []
      for (let i = 1; i < timestamps.length; i++) {
        intervals.push(timestamps[i] - timestamps[i - 1])
      }
      const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length
      const avgMinutes = avgInterval / (1000 * 60)

      // Determine aggregation level based on average interval
      if (avgMinutes < 30) {
        xAxisName = 'Date & Time (15-minute)'
      } else if (avgMinutes < 90) {
        xAxisName = 'Date & Time (Hourly)'
      } else if (avgMinutes < 1440) {
        xAxisName = 'Date & Time'
      } else {
        xAxisName = 'Date'
      }
    }

    xAxisConfig = {
      type: 'time',
      name: xAxisName,
      nameLocation: 'middle',
      nameGap: isMobile ? 40 : 35,
      nameTextStyle: {
        color: textColor,
        fontSize: isMobile ? 12 : 13,
        fontWeight: 'bold'
      },
      axisLabel: {
        color: textColor,
        rotate: isMobile ? 45 : 0,
        fontSize: isMobile ? 10 : 12,
        formatter: function(value) {
          const date = new Date(value)
          const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
          const dayOfWeek = dayNames[date.getDay()]
          const month = String(date.getMonth() + 1).padStart(2, '0')
          const day = String(date.getDate()).padStart(2, '0')
          const hours = String(date.getHours()).padStart(2, '0')
          const minutes = String(date.getMinutes()).padStart(2, '0')

          // Show date with day-of-week when day changes (midnight)
          if (date.getHours() === 0 && date.getMinutes() === 0) {
            if (isMobile) {
              // Compact format for mobile
              return `${month}/${day}\n${hours}:${minutes}`
            }
            return `${dayOfWeek} ${month}/${day}\n${hours}:${minutes}`
          }

          return `${hours}:${minutes}`
        }
      },
      axisLine: {
        lineStyle: {
          color: textColor
        }
      }
    }

    tooltipFormatter = function(params) {
      if (params.length > 0) {
        const data = params[0]
        const date = new Date(data.value[0])
        const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        const dayOfWeek = dayNames[date.getDay()]
        const time = date.toLocaleString()

        // Build tooltip with all series at this timestamp
        let tooltip = `<strong>${dayOfWeek} ${time}</strong><br/>`
        params.forEach(param => {
          const seriesName = param.seriesName
          const tti = param.value[1].toFixed(2)
          const color = param.color
          tooltip += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${color};margin-right:5px;"></span>${seriesName}: ${tti}<br/>`
        })
        return tooltip
      }
      return ''
    }
  }

  // Build series array with appropriate colors
  // Use different color palettes for light/dark mode and colorblind mode
  const lightModePalette = [
    '#1976D2', '#388E3C', '#F57C00', '#D32F2F', '#7B1FA2',
    '#00796B', '#C2185B', '#5D4037', '#455A64', '#0097A7'
  ]

  const darkModePalette = [
    '#64B5F6', '#81C784', '#FFB74D', '#E57373', '#BA68C8',
    '#4DB6AC', '#F06292', '#A1887F', '#90A4AE', '#4DD0E1'
  ]

  // Colorblind-friendly palettes (based on Wong 2011 / IBM Design / Okabe Ito)
  const lightModeColorblindPalette = [
    '#0072B2', '#E69F00', '#009E73', '#D55E00', '#CC79A7',
    '#56B4E9', '#F0E442', '#999999', '#000000', '#882255'
  ]

  const darkModeColorblindPalette = [
    '#56B4E9', '#F0E442', '#009E73', '#E69F00', '#CC79A7',
    '#0072B2', '#D55E00', '#CCCCCC', '#999999', '#882255'
  ]

  let colorPalette
  if (themeStore.colorblindMode) {
    colorPalette = isDark ? darkModeColorblindPalette : lightModeColorblindPalette
  } else {
    colorPalette = isDark ? darkModePalette : lightModePalette
  }

  const series = seriesData.map(([groupName, data], index) => {
    const color = colorPalette[index % colorPalette.length]
    return {
      name: groupName,
      type: 'line',
      data: data,
      smooth: true,
      lineStyle: {
        color: color,
        width: 2
      },
      itemStyle: {
        color: color
      },
      symbol: 'circle',
      symbolSize: hasLegend ? 3 : 4
    }
  })

  // Calculate dynamic y-axis range for more exaggerated display
  const allTTI = seriesData.flatMap(([_, data]) => data.map(d => d[1]))

  const minTTI = Math.min(...allTTI)
  const maxTTI = Math.max(...allTTI)
  const ttiRange = maxTTI - minTTI

  // Safety check: ensure values are valid numbers
  if (!isFinite(minTTI) || !isFinite(maxTTI) || allTTI.length === 0) {
    console.error('📊 CHART ERROR: Invalid y-axis data', { minTTI, maxTTI, allTTILength: allTTI.length })
    chart?.clear()
    return
  }

  // Set min/max with 2% padding, but round to nice intervals
  const rawMin = Math.max(0, minTTI - (ttiRange * 0.02))
  const rawMax = maxTTI + (ttiRange * 0.02)

  // Determine appropriate interval based on range
  const paddedRange = rawMax - rawMin
  let interval
  if (paddedRange < 0.5) {
    interval = 0.05  // Small range: 0.05 intervals (e.g., 1.00, 1.05, 1.10)
  } else if (paddedRange < 1) {
    interval = 0.1   // Medium range: 0.1 intervals (e.g., 1.0, 1.1, 1.2)
  } else if (paddedRange < 2) {
    interval = 0.2   // Larger range: 0.2 intervals
  } else {
    interval = 0.5   // Very large range: 0.5 intervals
  }

  // Round min down and max up to nearest interval
  const yAxisMin = Math.floor(rawMin / interval) * interval
  const yAxisMax = Math.ceil(rawMax / interval) * interval

  const gridTop = hasLegend
    ? (isMobile ? '80px' : '65px')
    : (isMobile ? '45px' : '55px')

  const option = {
    backgroundColor: backgroundColor,
    tooltip: {
      trigger: 'axis',
      formatter: tooltipFormatter
    },
    legend: hasLegend ? {
      type: 'scroll',
      orient: isMobile ? 'horizontal' : 'vertical',
      right: isMobile ? 'auto' : 10,
      left: isMobile ? 'center' : 'auto',
      top: isMobile ? 35 : 'center',
      textStyle: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
      },
      pageTextStyle: {
        color: textColor
      }
    } : undefined,
    xAxis: xAxisConfig,
    yAxis: {
      type: 'value',
      name: 'Travel Time Index',
      nameLocation: 'middle',
      nameGap: isMobile ? 45 : 55,
      min: yAxisMin,
      max: yAxisMax,
      interval: interval,
      nameTextStyle: {
        color: textColor,
        fontSize: isMobile ? 12 : 13,
        fontWeight: 'bold'
      },
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        formatter: function(value) {
          return value.toFixed(2)
        }
      },
      axisLine: {
        lineStyle: {
          color: textColor
        }
      },
      splitLine: {
        lineStyle: {
          color: isDark ? '#424242' : '#E0E0E0'
        }
      }
    },
    series: series,
    grid: {
      left: isMobile ? '60px' : '80px',
      right: hasLegend ? (isMobile ? '20px' : '200px') : (isMobile ? '20px' : '50px'),
      bottom: isMobile ? '70px' : '60px',
      top: gridTop
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      }
    ]
  }

  const setOptionStart = performance.now()
  chart.setOption(option, true)
  const t1 = performance.now()
}
</script>
