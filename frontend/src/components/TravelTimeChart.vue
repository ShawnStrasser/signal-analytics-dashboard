<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
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
  updateChart()
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
  
  // Prepare data for ECharts
  const timeData = props.data.map(d => {
    // Convert timestamp to Date if it's a string
    const timestamp = new Date(d.TIMESTAMP)
    return timestamp.getTime()
  })
  
  const travelTimeData = props.data.map(d => [
    new Date(d.TIMESTAMP).getTime(),
    d.TOTAL_TRAVEL_TIME_SECONDS || 0
  ])
  
  const title = props.selectedSignal 
    ? `Total Travel Time for Signal ${props.selectedSignal}`
    : 'Total Travel Time - All Selected Signals'
  
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
          const travelTime = data.value[1].toFixed(1)
          return `${time}<br/>Total Travel Time: ${travelTime}s`
        }
        return ''
      }
    },
    xAxis: {
      type: 'time',
      name: 'Time',
      nameLocation: 'middle',
      nameGap: 30
    },
    yAxis: {
      type: 'value',
      name: 'Total Travel Time (seconds)',
      nameLocation: 'middle',
      nameGap: 50
    },
    series: [
      {
        name: 'Total Travel Time',
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