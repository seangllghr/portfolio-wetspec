#!/usr/bin/env node
// This is a basic web server to serve up our dashboard
const { spawn } = require('child_process')
const express = require('express')
const app = express()
const port = 3000

app.use(express.static('/home/pi/bin/dashboard/public'))

app.get('/test', (req, res) => {
  res.send('Welcome to WetSpec.')
})
app.get('/restart', (req, res) => {
  res.send('WetSpec is restarting. Please wait...')
  spawn('shutdown', ['-r', 'now'])
})
app.get('/shutdown', (req, res) => {
  res.send('WetSpec is shutting down. Goodbye!')
  spawn('shutdown', ['-h', 'now'])
})
app.listen(port, () => {
  console.log(`Server listening on port ${port}.`)
})
