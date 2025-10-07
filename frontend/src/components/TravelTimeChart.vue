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
  },
  legendBy: {
    type: String,
    default: 'none'
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

watch(() => [props.data, props.selectedSignal, props.isTimeOfDay, props.legendBy], () => {
  const watchStart = performance.now()
  console.log('📊 CHART WATCH: data changed, deferring to nextTick', {
    dataLength: props.data?.length,
    isTimeOfDay: props.isTimeOfDay,
    legendBy: props.legendBy
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
  console.log('📊 CHART: updateChart START', { dataPoints: props.data.length, isTimeOfDay: props.isTimeOfDay, legendBy: props.legendBy })

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const backgroundColor = isDark ? 'transparent' : 'transparent'

  // Check if data has LEGEND_GROUP column
  const hasLegend = props.data.length > 0 && props.data[0].LEGEND_GROUP !== undefined

  let xAxisConfig, tooltipFormatter, title
  let seriesData = []

  if (props.isTimeOfDay) {
    // Time-of-day mode: use TIME_OF_DAY field
    // Check if data actually has TIME_OF_DAY field
    if (!props.data[0]?.TIME_OF_DAY) {
      console.warn('📊 CHART: isTimeOfDay=true but data missing TIME_OF_DAY field, skipping render')
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
        color: textColor,
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
  // Use different color palettes for light and dark mode
  const lightModePalette = [
    '#1976D2', '#388E3C', '#F57C00', '#D32F2F', '#7B1FA2',
    '#00796B', '#C2185B', '#5D4037', '#455A64', '#0097A7'
  ]

  const darkModePalette = [
    '#64B5F6', '#81C784', '#FFB74D', '#E57373', '#BA68C8',
    '#4DB6AC', '#F06292', '#A1887F', '#90A4AE', '#4DD0E1'
  ]

  const colorPalette = isDark ? darkModePalette : lightModePalette

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
    legend: hasLegend ? {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 'center',
      textStyle: {
        color: textColor
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
    series: series,
    grid: {
      left: '80px',
      right: hasLegend ? '200px' : '50px',
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