<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
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

onMounted(() => {
  initializeChart()
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
  
  // Handle window resize
  window.addEventListener('resize', () => {
    chart?.resize()
  })
}

function updateChart() {
  if (!chart || !props.data.length) return

  // Prepare data for ECharts - convert BigInt to Number
  const timeData = props.data.map(d => {
    // Convert timestamp to Date if it's a string
    const timestamp = new Date(d.TIMESTAMP)
    return timestamp.getTime()
  })

  const travelTimeData = props.data.map(d => [
    new Date(d.TIMESTAMP).getTime(),
    Number(d.TRAVEL_TIME_INDEX) || 0
  ])

  const title = props.selectedSignal
    ? `Travel Time Index for Signal ${props.selectedSignal}`
    : 'Travel Time Index - All Selected Signals'
  
  const option = {
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: 16
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: function(params) {
        if (params.length > 0) {
          const data = params[0]
          const time = new Date(data.value[0]).toLocaleString()
          const tti = data.value[1].toFixed(2)
          return `${time}<br/>Travel Time Index: ${tti}`
        }
        return ''
      }
    },
    xAxis: {
      type: 'time',
      name: 'Time',
      nameLocation: 'middle',
      nameGap: 30,
      axisLabel: {
        formatter: function(value) {
          const date = new Date(value)
          const timeData = props.data

          // Auto-format based on data granularity
          if (timeData.length > 1) {
            const firstTimestamp = new Date(timeData[0].TIMESTAMP)
            const lastTimestamp = new Date(timeData[timeData.length - 1].TIMESTAMP)
            const rangeDays = (lastTimestamp - firstTimestamp) / (1000 * 60 * 60 * 24)

            // Daily aggregation: show date only
            if (rangeDays > 7) {
              return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
            }
            // Hourly aggregation: show date + hour
            else if (rangeDays >= 4) {
              return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric' })
            }
          }

          // 15-min aggregation: show full timestamp
          return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
        }
      }
    },
    yAxis: {
      type: 'value',
      name: 'Travel Time Index',
      nameLocation: 'middle',
      nameGap: 50
    },
    series: [
      {
        name: 'Travel Time Index',
        type: 'line',
        data: travelTimeData,
        smooth: true,
        lineStyle: {
          color: '#1976D2',
          width: 2
        },
        itemStyle: {
          color: '#1976D2'
        },
        symbol: 'circle',
        symbolSize: 4
      }
    ],
    grid: {
      left: '80px',
      right: '50px',
      bottom: '80px',
      top: '80px'
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      },
      {
        type: 'slider',
        xAxisIndex: 0,
        bottom: 10
      }
    ]
  }
  
  chart.setOption(option, true)
}
</script>