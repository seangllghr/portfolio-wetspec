"""Implements the physical controls for the weather station

This module provides the two physical control devices for the GrovePi
WeatherStation.

Classes:
    Button
    RotaryDial
"""

import asyncio
import logging
import grovepi #pylint: disable=import-error

class Button:
    """Implements a button control

    The button control offers both instant-read and asynchronous watch
    capabilities.
    """
    def __init__(self, port):
        """Init the button on the provided port"""
        self.__port = port
        self.__pressed = False
        self.monitor = None
        grovepi.pinMode(self.__port, "INPUT")
        logging.debug('Button initialized on port %s', self.__port)

    @property
    def pressed(self):
        """Returns ``True`` if the button has been pressed

        The button is "sticky"---i.e. if it has been pressed at any
        point in the past and not been reset, it will return ``True``.
        If the button has not yet been pressed, this function will check
        to see if it is currently pressed.
        """
        if not self.__pressed:
            self.__pressed = grovepi.digitalRead(self.__port)
        return self.__pressed

    async def start_monitor(self):
        """Starts a monitor to watch for button presses"""
        self.monitor = asyncio.create_task(self.watch())
        logging.info('Started button monitor')

    def press_button(self):
        """Programmatically "press" the button"""
        if not self.__pressed:
            self.__pressed = True
            logging.debug('Program pressed the button')
        else:
            logging.debug('Program tried to press the button (already pressed)')

    def reset_button(self):
        """Resets the button state so it can receive future presses"""
        if self.__pressed:
            self.__pressed = False
            logging.debug('Program reset the button')
        else:
            logging.debug('Program tried to reset the button (not yet pressed)')

    async def watch(self):
        """Watches asynchronously for a button press"""
        while not self.pressed:
            await asyncio.sleep(0.05)
        logging.info('Stopped button monitor')

class RotaryDial:
    """Implements a rotary dial with variable partitioning

    This class implements a rotary dial control with a user-specified
    partitioning value. Defaults to 16 partitions (0--15)

    Attributes:
        num_partitions (int): The number of discrete values to produce
    """
    def __init__(self, port, num_partitions=16):
        self.__port = port
        self.__num_partitions = num_partitions
        grovepi.pinMode(self.__port, "INPUT")
        logging.debug('Dial initialized with %s partitions on port %s',
                      self.__num_partitions, self.__port)

    @property
    def num_partitions(self):
        """Gets the current number of dial partitions"""
        return self.__num_partitions

    @num_partitions.setter
    def num_partitions(self, new_num_partitions):
        if isinstance(new_num_partitions, int):
            self.__num_partitions = new_num_partitions
        logging.debug('Number of dial partitions set to %s',
                      self.__num_partitions)

    @property
    def value(self):
        """Returns the current dial value based on the number of partitions"""
        partition_size = int(1024 / self.num_partitions)
        return int(grovepi.analogRead(self.__port) / partition_size)

    @property
    def raw_value(self):
        """Returns the raw dial value"""
        return grovepi.analogRead(self.__port)
