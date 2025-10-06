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
  
  window.addEventListener('resize', () => {
    chart?.resize()
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
      top: 30
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
        name: 'Actual Travel Time',
        type: 'line',
        data: actualData,
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
      },
      {
        name: 'Predicted Travel Time',
        type: 'line',
        data: predictedData,
        smooth: true,
        lineStyle: {
          color: '#4CAF50',
          width: 2,
          type: 'dashed'
        },
        itemStyle: {
          color: '#4CAF50'
        },
        symbol: 'circle',
        symbolSize: 4
      }
    ],
    grid: {
      left: '80px',
      right: '50px',
      bottom: '80px',
      top: '100px'
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