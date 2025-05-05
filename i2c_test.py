from machine import Pin, I2C
i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400000)
devices = i2c.scan()
print("I2C devices found:", devices)