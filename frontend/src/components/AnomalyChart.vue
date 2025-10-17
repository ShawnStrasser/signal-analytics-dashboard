<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useTheme } from 'vuetify'
import * as echarts from 'echarts'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  selectedSignal: {
    type: [String, Number, null],
    default: null
  }
})

const chartContainer = ref(null)
let chart = null
const theme = useTheme()

onMounted(() => {
  initializeChart()
  updateChart()
})

// Watch for theme changes
watch(() => theme.global.current.value.dark, () => {
  updateChart()
})

onUnmounted(() => {
  if (chart) {
    chart.dispose()
  }
})

watch(() => [props.data, props.selectedSignal], () => {
  // Defer chart update to next tick to avoid updating during render
  nextTick(() => {
    updateChart()
  })
}, { deep: true })

function initializeChart() {
  chart = echarts.init(chartContainer.value)

  window.addEventListener('resize', () => {
    chart?.resize()
    // Re-render chart with updated responsive settings
    updateChart()
  })
}

function updateChart() {
  if (!chart || !props.data.length) return

  // Use nextTick to ensure chart resize happens after DOM updates
  nextTick(() => {
    chart?.resize()
  })

  // Prepare data for dual series chart - convert BigInt to Number
  const actualData = props.data.map(d => [
    new Date(d.TIMESTAMP).getTime(),
    Number(d.TOTAL_ACTUAL_TRAVEL_TIME) || 0
  ])

  const predictedData = props.data.map(d => [
    new Date(d.TIMESTAMP).getTime(),
    Number(d.TOTAL_PREDICTION) || 0
  ])

  const title = props.selectedSignal
    ? `Total Travel Time vs Prediction - Signal ${props.selectedSignal}`
    : 'Total Travel Time vs Prediction - All Selected Signals'

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const actualLineColor = isDark ? '#90CAF9' : '#1976D2'
  const predictedLineColor = isDark ? '#81C784' : '#4CAF50'
  const backgroundColor = isDark ? 'transparent' : 'transparent'

  // Detect mobile screen size
  const isMobile = window.innerWidth < 600

  // Determine aggregation level from data timestamps (matching TTI pattern)
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

  // Calculate dynamic y-axis range (matching TTI pattern)
  const allValues = [...actualData, ...predictedData].map(d => d[1])
  const minValue = Math.min(...allValues)
  const maxValue = Math.max(...allValues)
  const valueRange = maxValue - minValue

  // Safety check: ensure values are valid numbers
  if (!isFinite(minValue) || !isFinite(maxValue) || allValues.length === 0) {
    console.error('📊 ANOMALY CHART ERROR: Invalid y-axis data', { minValue, maxValue })
    return
  }

  // Set min/max with 2% padding, but round to nice intervals
  const rawMin = Math.max(0, minValue - (valueRange * 0.02))
  const rawMax = maxValue + (valueRange * 0.02)

  // Determine appropriate interval based on range (use much larger intervals to reduce label density)
  // Target: ~5-8 labels on the y-axis for readability
  const paddedRange = rawMax - rawMin
  let interval
  if (paddedRange < 10) {
    interval = 2
  } else if (paddedRange < 50) {
    interval = 10
  } else if (paddedRange < 100) {
    interval = 20
  } else if (paddedRange < 500) {
    interval = 100
  } else if (paddedRange < 1000) {
    interval = 200
  } else if (paddedRange < 5000) {
    interval = 1000
  } else if (paddedRange < 10000) {
    interval = 2000
  } else if (paddedRange < 50000) {
    interval = 10000
  } else if (paddedRange < 100000) {
    interval = 20000
  } else if (paddedRange < 500000) {
    interval = 50000
  } else {
    interval = 100000
  }

  // Round min down and max up to nearest interval
  const yAxisMin = Math.floor(rawMin / interval) * interval
  const yAxisMax = Math.ceil(rawMax / interval) * interval

  const option = {
    backgroundColor: backgroundColor,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: isMobile ? 13 : 16,
        color: textColor
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: function(params) {
        if (params.length > 0) {
          const date = new Date(params[0].value[0])
          const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
          const dayOfWeek = dayNames[date.getDay()]
          const time = date.toLocaleString()

          // Build tooltip with day-of-week prefix (matching TTI pattern)
          let tooltip = `<strong>${dayOfWeek} ${time}</strong><br/>`
          params.forEach(param => {
            const value = param.value[1].toFixed(1)
            const color = param.color
            tooltip += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${color};margin-right:5px;"></span>${param.seriesName}: ${value}s<br/>`
          })
          return tooltip
        }
        return ''
      }
    },
    legend: {
      data: ['Actual Travel Time', 'Predicted Travel Time'],
      top: isMobile ? 30 : 30,
      textStyle: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
      }
    },
    xAxis: {
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
    },
    yAxis: {
      type: 'value',
      name: 'Total Travel Time (seconds)',
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
          // Format with appropriate precision based on interval
          if (interval < 1) {
            return value.toFixed(2)
          } else if (interval < 10) {
            return value.toFixed(1)
          } else {
            return value.toFixed(0)
          }
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
    series: [
      {
        name: 'Actual Travel Time',
        type: 'line',
        data: actualData,
        smooth: true,
        lineStyle: {
          color: actualLineColor,
          width: 2
        },
        itemStyle: {
          color: actualLineColor
        },
        symbol: 'circle',
        symbolSize: 4
      },
      {
        name: 'Predicted Travel Time',
        type: 'line',
        data: predictedData,
        smooth: true,
        lineStyle: {
          color: predictedLineColor,
          width: 2,
          type: 'dashed'
        },
        itemStyle: {
          color: predictedLineColor
        },
        symbol: 'circle',
        symbolSize: 4
      }
    ],
    grid: {
      left: isMobile ? '60px' : '80px',
      right: isMobile ? '20px' : '50px',
      bottom: isMobile ? '70px' : '60px',
      top: isMobile ? '80px' : '100px'
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      }
    ]
  }
  
  chart.setOption(option, true)
}
</script>