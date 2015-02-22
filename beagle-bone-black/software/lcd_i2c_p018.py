#! /usr/bin/python
# from Adafruit_I2C import Adafruit_I2C as i2c
from I2C import I2C as i2c
import Queue, threading, time

class lcd:
    columns = 16
    rows =     2
    wait =   .02
    # wait =     0
    reset_wait = .1
    previous_rgb = None

    def __init__(self, i2c_bus = -1):
        self.device = i2c(0x38, i2c_bus)

    def show_rgb(self, message, rgb = None):
        if rgb <> self.previous_rgb and False:
            self.show([" " * self.columns] * self.rows)
            self.set_rgb(0, 0, 0)

        self.show(message)
        self.set_rgb(rgb[0], rgb[1], rgb[2])

    def show(self, message):
        line_cursor_position_index = [128, 192]

        for line_number, this_message in enumerate(message[:self.rows]):
            if this_message <> "":
                byte_list = []
                this_message += (" " * (self.columns - len(this_message)))[0: self.columns]
                for character_index in range(min(len(this_message), self.columns)):
                    byte_list.append(ord(this_message[character_index]))
                byte_list.append(13)

                while True:
                    try:
                        self.device.write8(2, line_cursor_position_index[line_number])
                        time.sleep(self.wait)
                        self.device.writeList(3, byte_list)
                        time.sleep(self.wait)
                        break
                    except IOError as err:
                        print chr(7) + "**** exception caught ****: " + repr(err)
                        time.sleep(self.wait)
                        pass

    def set_rgb(self, red, green, blue):
        rgb = (red, green, blue)
        if rgb <> None:
            self.previous_rgb = rgb
        self.device.writeList(1, [int(x * 10 / 255) for x in rgb])
        time.sleep(self.wait)

    def clear(self):
        self.device.write8(2, 1)
        time.sleep(self.wait)

    def reset(self):
        self.device.write8(0x95, 0)
        time.sleep(self.reset_wait)

    def cursor(self, mode):
        mode_list = { "flashblock": 13, "normal": 14, "block_underline": 15 }
        if mode == True:
            self.device.write8(2, 15)
        else:
            self.device.write8(2, 12)
        time.sleep(self.wait)
