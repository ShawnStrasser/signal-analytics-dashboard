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
          const time = new Date(params[0].value[0]).toLocaleString()
          let tooltip = `${time}<br/>`
          params.forEach(param => {
            const value = param.value[1].toFixed(1)
            tooltip += `${param.seriesName}: ${value}s<br/>`
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
      name: 'Time',
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
          const month = String(date.getMonth() + 1).padStart(2, '0')
          const day = String(date.getDate()).padStart(2, '0')
          const hours = String(date.getHours()).padStart(2, '0')
          const minutes = String(date.getMinutes()).padStart(2, '0')

          // Show date when day changes (midnight)
          if (date.getHours() === 0 && date.getMinutes() === 0) {
            return `${month}/${day}\n${hours}:${minutes}`
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
      nameTextStyle: {
        color: textColor,
        fontSize: isMobile ? 12 : 13,
        fontWeight: 'bold'
      },
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
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
      bottom: isMobile ? '80px' : '80px',
      top: isMobile ? '80px' : '100px'
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      },
      {
        type: 'slider',
        xAxisIndex: 0,
        bottom: 10,
        height: isMobile ? 15 : 20
      }
    ]
  }
  
  chart.setOption(option, true)
}
</script>