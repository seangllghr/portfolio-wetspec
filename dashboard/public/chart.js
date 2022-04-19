/**
 * @fileoverview This file provides the scripting logic for the SysTech WetSpec
 * web dashboard, including a CanvasJS chart for displaying station data and
 * controls for managing the hardware.
 */

// Declare sampleInterval and chart globally so we can stop passing them
// everywhere. Is there a better way to do this? Almost certainly. But I'm
// definitively outside the scope of this course already, so I'm declaring
// victory. I'm also using mixed jQuery and ES 6/7.

const sampleInterval = (30 * 60) // 30 minutes converted to seconds
let chart // We have to actually initialize this after the page loads

/**
 * Generate a simple moving average dataset for the given raw dataset
 *
 * @param {Object[]} dataset an array of x,y data point objects
 * @returns {Object[]} an array of simple moving average x,y data point objects
 */
function calculateSMADataset(dataset) {
  let datasetSMA = []
  dataset.forEach((datum, index) => {
    if (index === 0) {
      datasetSMA.push(datum)
    } else if (index < 12) {
      datasetSMA.push({
        x: datum.x,
        y: simpleMovingAverage(dataset, index, index)
      })
    } else {
      datasetSMA.push({
        x: datum.x,
        y: simpleMovingAverage(dataset, index, 12)
      })
    }
  })
  return datasetSMA
}

/**
 * Wait for the server to respond after restart
 */
async function fetchRetry(url, options, n=10) {
  try {
    return await fetch(url, options)
  } catch(err) {
    if (n === 1) throw err
    await sleep(5000)
    return await fetchRetry(url, options, n - 1)
  }
}

/**
 * Find appropriate locations for x-axis breaks in a list of datapoints plotted
 * against datetime on the x axis. For our final half-hour sampling interval,
 * we've stuck with scale breaks on intervals greater than 10 sample periods.
 * This condenses overnight periods, where the system gathers no data, assuming
 * the system is installed in a locale where night lasts more than five hours
 * (Arctic summers, I'm looking at you).
 *
 * @param {Array} data: An array containing data points of the form
 *     {x: Date, y: float}
 * @param {int} sampleInterval: The interval between readings, in seconds
 *
 * @returns: an array of custom break objects suitable for use with CanvasJS
 */
function getXBreaks(data) {
  const maxInterval = 10 * sampleInterval * 1000
  let customBreaks = []
  let nextDatum

  data.forEach((datum, index) => {
    if (index != data.length - 1) {
      nextDatum = data[index + 1]
      if (nextDatum.x.getTime() - datum.x.getTime() > maxInterval) {
        // The interval between these points exceeds the max. Make a scale break
        customBreaks.push({
          startValue: new Date(datum.x.getTime() + (3 * sampleInterval * 1000)),
          endValue: new Date(nextDatum.x.getTime() - (3 * sampleInterval * 1000)),
          type: "wavy",
          spacing: 1
        })
      }
    }
  })

  return customBreaks
}

/**
 * Hide the chart and display an explanatory message
 */
function hideDashboard(message) {
  $('#chartContainer').css('display', 'none')
  $('.control-button').css('display', 'none')
  $('.title').css('display', 'none')

  // unlike the display function, this message does not time out
  $('#message').html(`<p>${message}</p>`)
}

/**
 * Restart the weather station and wait for response
 */
async function restartHandler() {
  response = await fetch('restart')
  message = await response.text()
  hideDashboard(message)
  await sleep(3000) // Make sure we wait for the system to go down
  try {
    response = await fetchRetry('test')
    message = await response.text()
  } catch(err) {
    message = `
Something went wrong while restarting the WetSpec device. You may need to
manually reset it, then reload this page.
`
    hideDashboard(message)
    return
  }
  showDashboard(message)
}

/**
 * Show the data chart, and update it once per update interval
 */
async function showDashboard(message='') {
  updateChart(chart, sampleInterval)
  $('#chartContainer').css('display', 'block')
  $('.control-button').css('display', 'block')
  $('.title').css('display', 'block')

  // Since the Pi is configured with a long sample interval, our refresh timing
  // could differ from the Pi's by a significant amount if we only refreshed
  // once per interval. This compromises by updating the chart four times per
  // sample period.
  setInterval(
    () => { updateChart(chart, sampleInterval) },
    (Math.round(sampleInterval / 4) * 1000)
  )

  // If we have a message, display it for a beat, then clear it out
  if (message !== '') {
    $('#message').html(`<p>${message}</p>`)
    await sleep(3000)
    $('#message').html('')
  }
}

/**
 * Shut down the WetSpec device
 */
async function shutdownHandler() {
  response = await fetch('shutdown')
  message = await response.text()
  hideDashboard(message)
}

/**
 * Pause execution for a specified period (in milliseconds)
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/**
 * Calculate simple moving average from a dataset at a point
 *
 * @param {Object[]} dataset an array of x,y data point objects
 * @param {int} point the index of the point to calculate
 * @param {int} numPoints the number of points to average (default: 5)
 */
function simpleMovingAverage(dataset, point, numPoints=5) {
  let sum = 0
  for (let i = 0; i < numPoints; i++) {
    sum += dataset[point - i]['y']
  }
  return sum / numPoints
}

/**
 * Handles the custom data processing for my weather station's JSON output.
 * Since we went through the effort of including the time, temp, and humidity,
 * we get to plot temp and humidity against time.
 *
 * @param {Chart} chart: a CanvasJS chart object
 * @param {int} sampleInterval: the interval between readings, in seconds
 */
function updateChart() {
  let tempData = []
  let humidityData = []

  $.getJSON("data.json", (data) => {
    $.each(data, (key, value) => {
      tempData.push({
        x: new Date(value.time),
        y: parseFloat(value.temp)
      })
      humidityData.push({
        x: new Date(value.time),
        y: parseInt(value.humidity)
      })
    })

    let tempSMA = calculateSMADataset(tempData)
    let humiditySMA = calculateSMADataset(humidityData)

    // compress the x axis whenever there's a sufficient gap in data
    chart.options.axisX.scaleBreaks.customBreaks =
      getXBreaks(tempData, sampleInterval)

    // Push our updated data to the chart and render it
    chart.options.data[0].dataPoints = tempData
    chart.options.data[1].dataPoints = humidityData
    chart.options.data[2].dataPoints = tempSMA
    chart.options.data[3].dataPoints = humiditySMA
    chart.render()
  })
}

window.onload = function () {
  chart = new CanvasJS.Chart("chartContainer", {
    animationEnabled: true,
    theme: "dark1",
    zoomEnabled: true,
    toolTip: {
      shared: true
    },
    axisX: {
      intervalType: "hour",
      labelAngle: -45,
      valueFormatString: "DD MMM HH:mm K",
      crosshair: {
        enabled: true
      },
      scaleBreaks: {
        customBreaks: null
      }
    },
    axisY: {
      title: "Temperature (°F)",
      suffix: " °F",
      titleFontColor: "#C0504E",
      labelFontColor: "#C0504E",
      lineColor: "#C0504E",
      tickColor: "#C0504E",
      crosshair: {
        enabled: true,
        labelBackgroundColor: "#C0504E",
        labelFontColor: "#FFF",
        valueFormatString: "#0.# °F"
      }
    },
    axisY2: {
      title: "Humidity (%)",
      suffix: "%",
      titleFontColor: "#4F81BC",
      labelFontColor: "#4F81BC",
      lineColor: "#4F81BC",
      tickColor: "#4F81BC",
      crosshair: {
        enabled: true,
        labelBackgroundColor: "#4F81BC",
        labelFontColor: "#FFF",
        valueFormatString: "#0'%'"
      }
    },
    legend: {
      cursor: "pointer",
      itemclick: (e) => {
        if (typeof (e.dataSeries.visible) === "undefined" ||
            e.dataSeries.visible) {
          e.dataSeries.visible = false
        } else {
          e.dataSeries.visible = true
        }
        e.chart.render()
      }
    },
    data: [
      {
        name: "Temperature",
        xValueFormatString: "MM-DD|HH:mm",
        yValueFormatString: "#0.## °F",
        type: "line",
        markerType: "none",
        color: "#C0504E",
        visible: false,
        showInLegend: true,
        dataPoints: null
      },
      {
        name: "Humidity",
        xValueFormatString: "MM-DD|HH:mm",
        yValueFormatString: "#0'%'",
        axisYType: "secondary",
        type: "line",
        markerType: "none",
        color: "#4F81BC",
        visible: false,
        showInLegend: true,
        dataPoints: null
      },
      {
        name: "Temperature 6-Hour Average",
        xValueFormatString: "MM-DD|HH:mm",
        yValueFormatString: "#0.## °F",
        type: "spline",
        markerType: "none",
        color: "#F0807E",
        visible: true,
        showInLegend: true,
        dataPoints: null
      },
      {
        name: "Humidity 6-Hour Average",
        xValueFormatString: "MM-DD|HH:mm",
        yValueFormatString: "#0'%'",
        axisYType: "secondary",
        type: "spline",
        markerType: "none",
        color: "#7FB1EC",
        visible: true,
        showInLegend: true,
        dataPoints: null
      }
    ]
  })

  // Render the dashboard on load
  showDashboard('Welcome to WetSpec')

  // Set handlers for restart and shutdown events
  $('#restart').click(restartHandler)
  $('#shutdown').click(shutdownHandler)
}
