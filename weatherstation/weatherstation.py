#!/usr/bin/env python3
"""Implements a weather station built with GrovePi.

This module implements the core functionality of a GrovePi weather
station in Python. It tracks ambient temperature and relative humidity
during daylight, displays current conditions to an LCD display, and
writes data to a JSON file for future use.

Classes:
    WeatherStation

Functions:
    load_config(config_path): Load a JSON containing port assignments

Author:
    Sean Gallagher
"""

# stdlib imports
import asyncio
import argparse
from concurrent.futures import CancelledError
import datetime as dt
import json
import logging
import os
import signal
import subprocess
import sys

# third party imports
import requests

# Local module imports
import controls
import data
import displays
import sensors

def init_args():
    """Initializes the program from command line arguments"""
    desc = 'Start the GrovePi weather station program'

    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('-c', '--config',
                        help='Specify a custom config file')

    parser.add_argument('-l', '--log-file',
                        help='Specify a log file')

    parser.add_argument('-d', '--debug', action='store_true', default=False,
                        help='Toggle debug output to console')

    parser.add_argument('-f', '--data-file',
                        help='Specify a JSON weather data log')

    parser.add_argument('-p', '--sampling-period',
                        help='The time between weather measurements in seconds')

    args = parser.parse_args()
    return args

def load_config(args):
    """Attempts to load configuration from JSON and/or fills with defaults

    This function attempts to load port settings from a JSON config
    file. If there are missing values---or the configuration file is
    not found---it populates the config dict with default values

    Args:
        args (dict): The command line arguments to the program

    Returns:
        config (dict): A dictionary of port assignments
    """
    # Originally, I allowed for a config file, command-line overrides, or hard-
    # coded defaults. I've opted for supplying a default config in the install
    # directory instead.
    install_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    default_config_path = install_dir + '/config.json'

    # If we have a config file, load that first
    config_dict = {}
    try:
        with open(default_config_path, 'r') as default_config_file:
            default_config = json.load(default_config_file)
    except FileNotFoundError:
        logging.error('Default config file not found. Aborting')
        sys.exit(1)
    if args.config:
        try:
            with open(args.config, 'r') as config_file:
                config_dict = json.load(config_file)
        except FileNotFoundError:
            logging.info('Config file not found. Using defaults')
    else:
        config_dict = default_config

    # Ensure that the configuration has assignments for all ports
    try:
        # The config has port assignments. Use them, but check for missing ports
        ports = config_dict['ports']
        logging.debug('Port assignments found in config')
        for port in default_config['ports']:
            if port not in ports:
                logging.debug('Port not assigned for %s, using default')
                ports[port] = default_config['ports'][port]
    except KeyError:
        # The config does not have port assignments. Use all of the defaults
        logging.debug('Port assignments not found in config. Using defaults')
        config_dict['ports'] = default_config['ports']

    # Ensure that the other config options are set. If an option is specified at
    # the command line, it overrides config file settings.
    for option in default_config:
        if option != 'ports' and option not in config_dict:
            logging.debug(
                'Option \'%s\' not found in config. Using default',
                option
            )
            config_dict[option] = default_config[option]

    return config_dict

def localize(datetime_to_localize):
    """Gets the system local timezone and returns the localized datetime

    For reasons beyond my understanding, `dateutil.tz.tzlocal()` doesn't
    work on my Pi or my local machine---it complains about `tz` not
    being a real attribute of `dateutil`. So I've implemented this hacky
    workaround that scrapes the UTC offset from the `date` command and
    applies it to the passed `datetime` object using a native
    `timedelta`. It's ugly, but it works.

    Args:
        datetime (datetime): a UTC datetime object

    Returns:
        (datetime): a localized datetime object
    """
    tz_offset = int(subprocess.check_output(['date', '+%z'])) // 100
    tz_delta = dt.timedelta(hours=tz_offset)
    return datetime_to_localize + tz_delta


def server_running():
    """Check if the weather station dashboard server service is running """
    server_process_ok = os.system('systemctl is-active --quiet weatherserver') == 0
    try:
        response = requests.get('http://localhost:3000/test')
        server_response_ok = response.ok
    except requests.exceptions.ConnectionError:
        # if the server isn't responding, we get a ConnectionError. This is ok
        server_response_ok = False

    return server_process_ok and server_response_ok

class WeatherStation:
    """Implements the core functionality of the weather station

    Attributes:
        ledbar (LedBar): A LedBar object configured to address the port
            connected to the hardware LED bar
        stop_button (Button): A Button object configured to address the
            port connected to the hardware button
        light_sensor (LightSensor): A LightSensor object configured to
            address the port connected to the hardware light sensor
        dial (RotaryDial): A RotaryDial object configured to address the
            port connected to the hardware rotary dial
        screen (Screen): A Screen object. Since the screen uses I2C, it
            requires no special configuration

    """
    def __init__(self, config_dict):
        """Initializes the WeatherStation, optionally from a config file

        Args:
            config_dict (dict) : A config dict containing the sub-dict
                ``'ports'`` with port assignments

        Returns:
            WeatherStation: An initialized WeatherStation object
        """
        self.config = config_dict
        # self.ledbar = displays.LedBar(self.config['ports']['ledbar_port'])
        self.stop_button = controls.Button(self.config['ports']['button_port'])
        self.light_sensor = sensors.LightSensor(
            self.config['ports']['light_port'],
            self.config['light_threshold']
        )
        self.dht = sensors.DHTSensor(self.config['ports']['dht_port'])
        self.dial = controls.RotaryDial(self.config['ports']['dial_port'])
        self.screen = displays.Screen()
        self.data_log = data.WeatherLogger(self.config['data_file'])

    async def run(self):
        """Runs the main weather station loop

        This method defines the main run process for the WeatherStation.
        It runs a weather update task while the light sensor value is
        above the configured threshold, or lights the single red LED at
        the high end of the LED bar when the sensor is below that value.
        This method is called automatically at the end of `start()`.
        """
        signal.signal(signal.SIGTERM, self.signal_handler)
        try:
            weather_update_task = asyncio.create_task(self.weather_update())
            server_status_task = asyncio.create_task(self.watch_server())
            while not self.stop_button.pressed:
                last_brightness = self.dial.value
                self.screen.brightness = last_brightness
                self.weather_display(self.data_log.last_record)
                while (self.light_sensor.over_threshold
                    and not self.stop_button.pressed):
                    # Update the displays until it gets dark
                    new_brightness = self.dial.value
                    self.screen.brightness = new_brightness
                    if last_brightness == 0 and new_brightness != 0:
                        self.weather_display(self.data_log.last_record)
                    last_brightness = new_brightness
                    await asyncio.sleep(0.05)

                # Light the red LED at the end of the LED bar while it's dark
                # self.ledbar.light_led(10)
                self.screen.text = ''
                self.screen.brightness = 0
                while (not self.light_sensor.over_threshold
                    and not self.stop_button.pressed):
                    # Wait for it to get light again.
                    await asyncio.sleep(0.05)

            # Tidy up when we're done
            weather_update_task.cancel()
            server_status_task.cancel()
            await weather_update_task
            await server_status_task
        except CancelledError:
            # I can't find a clear explanation of why I get these, but
            # they're anticipated, and we can safely ignore them.
            pass

    def signal_handler(self, signal_received, frame):
        """Handle SIGTERM gracefully so we can run as a service"""
        self.stop_button.press_button()
        logging.info('Received %s. Shutting down', signal_received)

    async def start(self):
        """Starts the weather station

        This method runs startup tasks for the weather station. It
        asynchronously initializes the various hardware components to
        minimize startup time. Once the system is initialized, `start()`
        executes `run()`, the main run loop.
        """
        # ledbar_start = asyncio.create_task(self.ledbar.start())
        screen_start = asyncio.create_task(self.screen.start(
            self.dial.value,
            '{:^16s}\n{:^16s}'.format('Welcome to', 'WetSpec')
        ))
        # await ledbar_start
        await screen_start
        await self.stop_button.start_monitor()
        # while not server_running():
        #     self.screen.text = 'Waiting for\nserver start...'
        #     await asyncio.sleep(1)
        logging.info('Startup complete')

    async def stop(self):
        """Stops the weather station cleanly and blanks its displays

        This method cleanly shuts down the weather station by
        asynchronously blanking its two displays and terminating any
        asynchronous tasks. It should be fired after the main run loop
        terminates.
        """
        # ledbar_stop = asyncio.create_task(
        #     self.ledbar.stop()
        # )
        screen_stop = asyncio.create_task(
            self.screen.stop(self.dial.value)
        )
        try:
            await screen_stop
            # await ledbar_stop
            if not self.stop_button.pressed:
                self.stop_button.press_button()
            await self.stop_button.monitor
        except CancelledError:
            # Just like in run(), cancelling the screen monitor will
            # occasionally throw a concurrent.futures.CancelledError.
            # We can safely ignore it.
            pass
        logging.info('Shutdown complete')
        logging.info('{:-^39}'.format('-')) # Draw a line to separate runs

    def update_screen_color(self, record):
        """Update the screen backlight color

        I don't have multi-colored LEDs, so I'm going to change the LCD
        backlight color to indicate temperature ranges. This does
        necessitate some creative changes to the colors specified, since
        I can only display one color at a time.
        """
        temp = int(record['temp'])
        humidity = int(record['humidity'])
        if humidity < 80:
            if temp > 95:
                # This one stays red
                new_screen_color = (1.0, 0.3, 0.3)
            elif temp in range(85, 95):
                # We're going to make this orange
                new_screen_color = (1.0, 0.6, 0.2)
            elif temp in range(60, 85):
                # This bracket stays green, as specified
                new_screen_color = (0.5, 1.0, 0.5)
            elif temp < 60:
                # We'll use purple for this
                new_screen_color = (0.5, 0.2, 1.0)
        else:
            # We'll use a blue for this to show that it's humid
            new_screen_color = (0.3, 0.3, 1.0)

        self.screen.color = new_screen_color

    async def watch_server(self):
        """Watch for changes in the dashboard server process status"""
        try:
            last_status = server_running()
            while not self.stop_button.pressed:
                current_status = server_running()
                if current_status != last_status:
                    self.weather_display(self.data_log.last_record)
                    last_status = current_status
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            logging.info('Server monitoring task cancelled')
            return


    def weather_display(self, record):
        """Update the weatherstation display

        The weatherstation display includes a clock, time since last
        reading, temp and humidity at last reading, and server status

        Args:
            record (dict): a weather record logged in the weatherstation, with:
                time (str): an ISO 8061 timestamp from `datetime.isoformat()`
                temp (int): an integer temperature value
                humidity (int): an integer relative humidity value
        """
        temp = int(record['temp'])
        humidity = int(record['humidity'])
        current_time = dt.datetime.now()
        last_time = localize(
            dt.datetime.fromisoformat(self.data_log.last_record['time'])
        )

        new_screen_text = current_time.strftime('%H:%M')
        new_screen_text += '{:>11}'.format(
            'Srv:Up' if server_running() else 'Srv:Down'
        )
        new_screen_text += '\n{:>3d}F {:>3d}% @'.format(temp, humidity)
        new_screen_text += last_time.strftime('%H:%M')
        self.screen.text = new_screen_text

        # # Break temps into a 10-point scale and display on the ledbar
        # if temp < 55:
        #     self.ledbar.value = 1
        # elif temp > 95:
        #     self.ledbar.value = 10
        # else:
        #     self.ledbar.value = (temp - 45) // 5

    async def weather_update(self):
        """Runs the update loop

        This loop updates both the data logged to the JSON file and the
        LCD display. It runs once per minute, but appends data to the
        data log only once per sampling period. If new data is appended
        to the log, the system updates the display with the new data.
        """
        logging.info('Weather update sequence initiated')
        try:
            while True:
                current_temp = self.dht.temp('f')
                current_humidity = self.dht.humidity
                logging.debug('Temperature reading taken: %d', current_temp)
                self.data_log.append(
                    current_temp,
                    current_humidity,
                    self.config['sampling_period']
                )
                self.weather_display(self.data_log.last_record)
                self.update_screen_color(self.data_log.last_record)
                await asyncio.sleep(60) # try to update every minute
        except asyncio.CancelledError:
            logging.info('Weather update sequence cancelled')
            return

async def main(args):
    """This is the main sequence code"""
    # Initialize the command-line arguments and debugging output
    args = init_args()
    config = load_config(args)
    log_format = '%(asctime)s %(levelname)s:%(module)s:%(message)s'
    date_format = '%y-%m-%d %h:%m:%s'

    # For some reason, the logging is broken on my system. It was working with
    # this code, however, so I'm leaving it in.
    if args.debug:
        logging.basicConfig(
            format=log_format,
            datefmt=date_format,
            level=logging.DEBUG
        )
    else:
        logging.basicConfig(
            filename=config['log_file'],
            format=log_format,
            datefmt=date_format,
            level=logging.INFO
        )

    # Initialize the weather station and prepare to receive shutdown signal
    weather_station = WeatherStation(config)

    # Startup and run the weather station
    await weather_station.start()
    await weather_station.run()

    # Shut down the weather station
    await weather_station.stop()

if __name__ == "__main__":
    asyncio.run(main(sys.argv))
