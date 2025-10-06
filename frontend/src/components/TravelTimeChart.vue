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
  },
  isTimeOfDay: {
    type: Boolean,
    default: false
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

watch(() => [props.data, props.selectedSignal, props.isTimeOfDay], () => {
  const watchStart = performance.now()
  console.log('📊 CHART WATCH: data changed, deferring to nextTick', {
    dataLength: props.data?.length,
    isTimeOfDay: props.isTimeOfDay
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
  console.log('📊 CHART: updateChart START', { dataPoints: props.data.length, isTimeOfDay: props.isTimeOfDay })

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const lineColor = isDark ? '#90CAF9' : '#1976D2'
  const backgroundColor = isDark ? 'transparent' : 'transparent'

  let travelTimeData, xAxisConfig, tooltipFormatter, title

  if (props.isTimeOfDay) {
    // Time-of-day mode: use TIME_OF_DAY field
    // Check if data actually has TIME_OF_DAY field
    if (!props.data[0]?.TIME_OF_DAY) {
      console.warn('📊 CHART: isTimeOfDay=true but data missing TIME_OF_DAY field, skipping render')
      return
    }

    travelTimeData = props.data.map((d, idx) => {
      let hours, minutes

      // Handle different TIME formats from Snowflake
      if (typeof d.TIME_OF_DAY === 'string') {
        // String format: "HH:MM:SS"
        const timeParts = d.TIME_OF_DAY.split(':')
        hours = parseInt(timeParts[0])
        minutes = parseInt(timeParts[1])
      } else if (d.TIME_OF_DAY instanceof Date) {
        // Date object
        hours = d.TIME_OF_DAY.getHours()
        minutes = d.TIME_OF_DAY.getMinutes()
      } else if (typeof d.TIME_OF_DAY === 'number') {
        // Snowflake TIME type comes as microseconds since midnight via Arrow
        // Convert microseconds to seconds: divide by 1,000,000
        const totalSeconds = d.TIME_OF_DAY / 1000000
        hours = Math.floor(totalSeconds / 3600)
        minutes = Math.floor((totalSeconds % 3600) / 60)
      } else {
        console.warn('Unexpected TIME_OF_DAY format:', d.TIME_OF_DAY, typeof d.TIME_OF_DAY)
        hours = 0
        minutes = 0
      }

      const totalMinutes = hours * 60 + minutes
      return [totalMinutes, Number(d.TRAVEL_TIME_INDEX) || 0]
    })

    // Calculate min/max for x-axis range
    const allMinutes = travelTimeData.map(d => d[0])
    const minMinutes = Math.min(...allMinutes)
    const maxMinutes = Math.max(...allMinutes)

    title = props.selectedSignal
      ? `Travel Time Index by Time of Day for Signal ${props.selectedSignal}`
      : 'Travel Time Index by Time of Day - All Selected Signals'

    // Determine appropriate interval for x-axis labels based on data range
    const rangeMinutes = maxMinutes - minMinutes
    let labelInterval
    if (rangeMinutes <= 120) { // 2 hours or less
      labelInterval = 15 // Every 15 minutes
    } else if (rangeMinutes <= 360) { // 6 hours or less
      labelInterval = 30 // Every 30 minutes
    } else if (rangeMinutes <= 720) { // 12 hours or less
      labelInterval = 60 // Every hour
    } else {
      labelInterval = 120 // Every 2 hours
    }

    xAxisConfig = {
      type: 'value',
      name: 'Time of Day',
      nameLocation: 'middle',
      nameGap: 30,
      min: minMinutes,
      max: maxMinutes,
      interval: labelInterval,
      axisLabel: {
        color: textColor,
        formatter: function(value) {
          const hours = Math.floor(value / 60)
          const minutes = value % 60
          return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
        }
      },
      nameTextStyle: {
        color: textColor
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
        const tti = data.value[1].toFixed(2)
        return `${time}<br/>Travel Time Index: ${tti}`
      }
      return ''
    }
  } else {
    // Regular timestamp mode
    travelTimeData = props.data.map(d => [
      new Date(d.TIMESTAMP).getTime(),
      Number(d.TRAVEL_TIME_INDEX) || 0
    ])

    title = props.selectedSignal
      ? `Travel Time Index for Signal ${props.selectedSignal}`
      : 'Travel Time Index - All Selected Signals'

    xAxisConfig = {
      type: 'time',
      name: 'Time',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: {
        color: textColor
      },
      axisLabel: {
        color: textColor
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
        const time = new Date(data.value[0]).toLocaleString()
        const tti = data.value[1].toFixed(2)
        return `${time}<br/>Travel Time Index: ${tti}`
      }
      return ''
    }
  }

  const option = {
    backgroundColor: backgroundColor,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: 16,
        color: textColor
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: tooltipFormatter
    },
    xAxis: xAxisConfig,
    yAxis: {
      type: 'value',
      name: 'Travel Time Index',
      nameLocation: 'middle',
      nameGap: 50,
      nameTextStyle: {
        color: textColor
      },
      axisLabel: {
        color: textColor
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
        name: 'Travel Time Index',
        type: 'line',
        data: travelTimeData,
        smooth: true,
        lineStyle: {
          color: lineColor,
          width: 2
        },
        itemStyle: {
          color: lineColor
        },
        symbol: 'circle',
        symbolSize: 4
      }
    ],
    grid: {
      left: '80px',
      right: '50px',
      bottom: '60px',
      top: '80px'
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
  console.log(`📊 CHART: setOption took ${(t1 - setOptionStart).toFixed(2)}ms`)
  console.log(`📊 CHART: updateChart COMPLETE, total ${(t1 - t0).toFixed(2)}ms`)
}
</script>