"""Implements data logging functionality for the weather station

Since we use basic logging config for runtime logging, we're only using
this component to provide JSON data logging for the actual weather data.
"""
import datetime as dt
import json
import logging

class WeatherLogger:
    """Implements a JSON logger for weather data"""
    def __init__(self, path):
        self.log_path = path
        try:
            with open(self.log_path) as log_file:
                self.log_data = json.load(log_file)
            logging.debug('Weather log file loaded successfully')
        except FileNotFoundError:
            self.log_data = []
            self.write_log()
            logging.debug('New weather log created at %s', self.log_path)

    @property
    def last_record(self):
        """Return the last data record in the log data"""
        if len(self.log_data) > 0:
            return self.log_data[-1]

        # If we don't have a record, return a null record with min datetime
        return {
            'time': dt.datetime.min.isoformat(),
            'temp': None,
            'humidity': None
        }

    def append(self, temp, humidity, interval):
        """Append a record to the weather log

        This function ensures that a minimum of one half-hour elapses
        between data points, to eliminate light-sensor induced dithering
        during dawn and dusk periods (or, more accurately, to compensate
        for the tendency of my indoor lighting to magically nail the
        threshold, no matter where I set it...)
        """
        current_time = dt.datetime.now(dt.timezone.utc)
        last_time = dt.datetime.fromisoformat(self.last_record['time'])
        delta_t = current_time - last_time

        # Only append if the specified interval has passed since last data point
        if delta_t.total_seconds() >= interval:
            self.log_data.append(
                {
                    'time': current_time.isoformat(),
                    'temp': temp,
                    'humidity': humidity
                }
            )
            self.write_log()
            return True
        return False

    def write_log(self):
        """Write the log to the specified file"""
        with open(self.log_path, 'w') as log_file:
            json.dump(self.log_data, log_file, indent=4)
