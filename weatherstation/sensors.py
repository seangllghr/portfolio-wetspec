"""Implements the primary input sensors for the weather station

This module provides classes for interaction with the two sensor devices
on the GrovePi weather station, the light sensor and the Digital
Humidity and Temperature (DHT) sensor.

Classes:
    LightSensor
    DHTSensor
"""
import logging
import grovepi #pylint: disable=import-error

class LightSensor:
    """Implements the light sensor interface"""
    def __init__(self, port, threshold=20):
        self.__port = port
        self.__light_threshold = threshold
        grovepi.pinMode(self.__port, "INPUT")

    @property
    def over_threshold(self):
        """Returns true if sensor value is greater than set threshold"""
        return grovepi.analogRead(self.__port) > self.__light_threshold

    @property
    def tenths_value(self):
        """Generate a value between 1 and 10 within the sensor response range"""
        sensor_value = self.value
        if sensor_value > 650:
            tenths_value = 10
        else:
            tenths_value = int(sensor_value / 65)
        return tenths_value

    @property
    def value(self):
        """Return the current raw light sensor reading"""
        return grovepi.analogRead(self.__port)

class DHTSensor:
    """Implements the DHT sensor interface

    Args:
        port (int): The port connected to the sensor
        sensor_color (str): Either ``'blue'`` or ``'white'``
    """
    def __init__(self, port, sensor_color='blue'):
        self.__port = port
        # Apparently grove makes two DHT sensors. Mine is blue.
        if sensor_color == 'white':
            self.__sensor_color = 1
        elif sensor_color == 'blue':
            self.__sensor_color = 0
        else:
            # Whine in the logs about a bogus sensor color being passed
            logging.error('Invalid sensor color \'%s\'. Assuming blue',
                          sensor_color)
            self.__sensor_color = 0
        self.read_both()

    def temp(self, unit='c'):
        """Return just the current temperature"""
        temp_c = self.read_both()[0]
        if unit == 'c':
            return temp_c
        if unit == 'f':
            return (temp_c * (9/5)) + 32
        if unit == 'k':
            return temp_c + 273.15
        # Whine in the log and return temp in Celsius
        logging.error('Unrecognized temperature unit \'%s\'', unit)
        return temp_c

    @property
    def humidity(self):
        """Return just the current humidity"""
        return self.read_both()[1]

    def read_both(self):
        """Record and set both temperature and humidity values"""
        [temp, humidity] = grovepi.dht(
            self.__port,
            self.__sensor_color
        )
        return (temp, humidity)
