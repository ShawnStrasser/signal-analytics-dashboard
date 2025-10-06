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
  const watchStart = performance.now()
  console.log('📊 CHART WATCH: data changed, deferring to nextTick', {
    dataLength: props.data?.length
  })
  // Defer chart update to next tick to avoid updating during render
  nextTick(() => {
    const tickStart = performance.now()
    console.log(`📊 CHART: nextTick triggered, delay from watch: ${(tickStart - watchStart).toFixed(2)}ms`)
    updateChart()
    const tickEnd = performance.now()
    console.log(`📊 CHART: updateChart complete, took ${(tickEnd - tickStart).toFixed(2)}ms`)
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
  const t0 = performance.now()
  if (!chart || !props.data.length) {
    console.log('📊 CHART: updateChart skipped (no chart or data)')
    return
  }
  console.log('📊 CHART: updateChart START', { dataPoints: props.data.length })

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
      nameGap: 30
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
  
  const setOptionStart = performance.now()
  chart.setOption(option, true)
  const t1 = performance.now()
  console.log(`📊 CHART: setOption took ${(t1 - setOptionStart).toFixed(2)}ms`)
  console.log(`📊 CHART: updateChart COMPLETE, total ${(t1 - t0).toFixed(2)}ms`)
}
</script>