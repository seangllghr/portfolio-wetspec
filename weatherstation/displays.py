"""Implements display devices for the weather station

This module provides two display output devices for the GrovePi
WeatherStation.

Classes:
    LedBar
    Screen
"""

import asyncio
import logging
import grovepi #pylint: disable=import-error
import grove_rgb_lcd #pylint: disable=import-error

class LedBar:
    """Implements a display interface for the GrovePi LED bar """
    def __init__(self, port):
        self.__port = port
        self.__value = 0
        logging.debug('LED bar initialized on port %s', self.__port)

    @property
    def value(self):
        """Returns the current value displayed on the LED bar"""
        return self.__value

    @value.setter
    def value(self, value):
        if value != self.__value: # Only change display if new val is different
            if value < 0:
                self.__value = 0
            elif value > 10:
                self.__value = 10
            else:
                self.__value = int(value)
            logging.debug('LED bar updated: %d', self.__value)
        grovepi.ledBar_setLevel(self.__port, self.__value)

    def light_led(self, led_number):
        """Toggle a single LED on or off"""
        grovepi.ledBar_setLevel(self.__port, 0) # Blank the LED bar first
        grovepi.ledBar_toggleLed(self.__port, led_number)

    async def start(self):
        """Runs a startup sequence on the LED bar

        This function sets the pin mode and initializes the LED bar. It
        also runs a purely-ornamental startup animation on the LED bar.
        """
        logging.info('LED bar started')
        grovepi.pinMode(self.__port, "OUTPUT")
        grovepi.ledBar_init(self.__port, 1)

        # Ornamental startup animation
        for i in range(0, 11):
            self.value = i
            await asyncio.sleep(0.01)

    async def stop(self):
        """Runs a shutdown sequence to blank the LED bar

        Shuts the LED bar down by animating a countdown from its current
        value to zero/off. The animation is nothing but fluff; it would
        be enough to simply set the value to zero, but this is more fun.
        """
        logging.info('Stopping LED bar')
        for i in range(self.value, -1, -1):
            self.value = i
            await asyncio.sleep(0.01)

class Screen:
    """Wraps around `grove_rgb_lcd` to interface with the Grove screen

    This interface simplifies setting color and brightness values for
    the screen, and provides functions to manage text refreshing.
    """
    def __init__(self):
        self.__backlight = {
            'brightness': 0,
            'color': {
                'red'  : 1.0,
                'green': 1.0,
                'blue' : 1.0
            }
        }
        self.__monitor_stopped = False
        self.__monitor = None
        self.__text = ''
        self.__new_text = ''
        self.__color = (1.0, 1.0, 1.0)

    @property
    def brightness(self):
        """Returns the current backlight brightness level"""
        return self.__backlight['brightness']

    @brightness.setter
    def brightness(self, level):
        self.__backlight['brightness'] = level * 16
        grove_rgb_lcd.setRGB(
            int(self.__backlight['brightness'] * self.__backlight['color']['red']),
            int(self.__backlight['brightness'] * self.__backlight['color']['green']),
            int(self.__backlight['brightness'] * self.__backlight['color']['blue'])
        )

    @property
    def color(self):
        """Returns the current screen color as an OpenGL-style RGB triple"""
        return (
            self.__backlight['color']['red'],
            self.__backlight['color']['green'],
            self.__backlight['color']['blue']
        )

    @color.setter
    def color(self, new_color):
        """Sets the backlight color from an OpenGL-style RGB triple

        This function uses decimal RGB triples, similar to how OpenGL
        handles color values.

        Args:
            new_color (tuple): a triple containing a decimal Red, Green,
                and Blue color component, in that order
        """
        self.__backlight['color']['red'] = new_color[0]
        self.__backlight['color']['green'] = new_color[1]
        self.__backlight['color']['blue'] = new_color[2]

    @property
    def text(self):
        """Returns the text currently displayed on the screen"""
        return self.__text

    @text.setter
    def text(self, text):
        """Sets the text to be displayed on the screen on refresh"""
        if self.text != str(text):
            if self.brightness > 0:
                self.__new_text = str(text)
                logging.debug('New text queued for next refresh: %s', self.__new_text)
            elif self.text != '':
                self.__new_text = ''
                logging.debug('Brightness is zero. Queued screen blank')

    async def monitor(self):
        """Refresh the screen text when new text is supplied

        We run a number of different refresh rates on a variety of
        synchronous and asynchronous loops. Rather than updating the
        text on-screen every time it is set, update it only if it has
        changed, to prevent flickering.
        """
        while not self.__monitor_stopped:
            try:
                if self.brightness == 0 and self.text != '':
                    self.text = ''
                if self.__new_text != self.text:
                    logging.debug('New text in queue. Updating text')
                    self.__text = self.__new_text
                    grove_rgb_lcd.setText(self.__text)
                await asyncio.sleep(0.05)
            except IOError:
                # Very occasionally, setText will spit out an IOError that
                # breaks the refresh loop. It appears to happen most regularly
                # when the brightness setting is changed rapidly to or from 0,
                # and the loop can't acquire a mutex lock to write to the
                # display. This is fine; we'll warn about it, but there's no
                # reason to bring down the refresh loop.
                logging.exception('Caught IOError in refresh loop.')

    async def start(self, brightness, message='Hello!'):
        """Runs a startup sequence on the screen

        This method initializes the screen's refresh loop, then runs a
        brief startup animation, incrementing the LCD's backlight
        brightness to the provided value.
        """
        self.__monitor = asyncio.create_task(self.monitor())

        # Startup animation. Leave it to the user to replace initial text
        logging.info('Screen started')
        self.text = message
        grove_rgb_lcd.setText(message)
        for i in range(0, brightness):
            self.brightness = i
            await asyncio.sleep(0.025)

    async def stop(self, brightness):
        """Runs a shutdown sequence to blank the display and cut backlight"""
        logging.info('Stopping screen')
        self.text = 'Goodbye!'

        # run a shutdown animation, stepping back through brightness levels
        for i in range(brightness, -1, -1):
            self.brightness = i
            await asyncio.sleep(0.025)

        # Blank the screen
        self.text = ''
        await asyncio.sleep(0.2) # wait a beat to make sure it happens

        # cancel screen refresh and catch the expected CancelledError
        self.__monitor_stopped = True
        await self.__monitor
