import machine
import time
import dht
import ssd1306
import sys
import select 



# --- Pin Configuration ---
LED_PIN = 25           
LDR_ADC_PIN = 26       
DHT_PIN_NUMBER = 15     
BUTTON_PIN_NUMBER = 14 
BUZZER_PIN_NUMBER = 16 

# OLED I2C configuration
I2C_SCL_PIN = 9        
I2C_SDA_PIN = 8        
I2C_FREQ = 400000      

# --- Thresholds ---
LIGHT_THRESHOLD = 10000  
TEMP_THRESHOLD = 30      

# --- Hardware Initialization ---
led = machine.Pin(LED_PIN, machine.Pin.OUT)
ldr = machine.ADC(LDR_ADC_PIN)
dht_pin = machine.Pin(DHT_PIN_NUMBER)
dht_sensor = dht.DHT11(dht_pin)
button = machine.Pin(BUTTON_PIN_NUMBER, machine.Pin.IN, machine.Pin.PULL_UP)
buzzer = machine.Pin(BUZZER_PIN_NUMBER, machine.Pin.OUT)

# Initialize I2C and SSD1306 OLED display
i2c = machine.I2C(0, scl=machine.Pin(I2C_SCL_PIN), sda=machine.Pin(I2C_SDA_PIN), freq=I2C_FREQ)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# --- Global State ---
mode = "auto"         
last_readings = []    # Stores the most recent 10 sensor readings
last_button_state = button.value()  
last_button_time = 0  
debounce_delay = 300  

# --- Helper Functions ---
def add_reading(temp, ldr_val):
    """Store a new reading, and keep only the last 10."""
    global last_readings
    reading = {"time": time.time(), "temp": temp, "light": ldr_val}
    last_readings.append(reading)
    if len(last_readings) > 10:
        last_readings.pop(0)

def print_readings():
    """Print the stored sensor readings."""
    print("\nLast 10 sensor readings:")
    for r in last_readings:
        print("Time: {} | Temp: {}°C | Light ADC: {}".format(r["time"], r["temp"], r["light"]))
    print()

def read_sensors():
    """Read temperature from the DHT11 sensor and light level from the LDR.
       Returns a tuple: (temperature, light_value)
    """
    temp = None
    ldr_val = None

    # Retry DHT11 reading up to 3 times
    for _ in range(2):
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            break
        except Exception as e:
            print("Error reading DHT11 sensor:", e)
            time.sleep(0.5)  # Wait before retrying

    # Read LDR value
    try:
        ldr_val = ldr.read_u16()
        if ldr_val < 0 or ldr_val > 65535:  # Sanity check
            raise ValueError("Invalid LDR value")
    except Exception as e:
        print("Error reading LDR sensor:", e)

    return temp, ldr_val

def update_oled(temp, ldr_val):
    """Update the OLED display with current temperature and light condition."""
    oled.fill(0)  
    oled.text("Mode: {}".format(mode), 0, 0)
    
    if temp is None:
        oled.text("Temp: -- C", 0, 10)
    else:
        oled.text("Temp: {} C".format(temp), 0, 10)
    
    if ldr_val is None:
        oled.text("Light: --", 0, 20)
    else:
        condition = "Dark" if ldr_val < LIGHT_THRESHOLD else "Bright"
        oled.text("Light: {}".format(condition), 0, 20)
        
    oled.show()
    

# --- Mode Functions ---
def auto_mode():
    """
    Auto Mode:
      - Reads the sensors.
      - Turns on the buzzer if temp > TEMP_THRESHOLD.
      - Turns on the LED if the LDR reading indicates dark conditions.
      - Logs the readings and updates the OLED display.
    """
    temp, ldr_val = read_sensors()
    if temp != None and ldr_val != None:
        print("\n[AUTO MODE] Temp: {}°C, Light ADC: {}".format(temp, ldr_val))
        add_reading(temp, ldr_val)
        
        if temp > TEMP_THRESHOLD:
            buzzer.on()
            print("-> Buzzer ON (Temp above {}°C)".format(TEMP_THRESHOLD))
        else:
            buzzer.off()
        
        if ldr_val < LIGHT_THRESHOLD:
            led.on()
            print("-> LED ON (Dark)")
        else:
            led.off()
    else:
        print("Sensor error: Invalid sensor data received.")
        buzzer.off()
        led.off()
    
    update_oled(temp, ldr_val)

def manual_mode():
    """
    Manual Mode:
      Allows direct control via serial commands:
      - b: Toggle the buzzer.
      - l: Toggle the LED.
      - r: Perform a sensor reading.
      - s: Show the stored last 10 sensor readings.
      - m: Switch back to Auto Mode.
      Automatically switches back to Auto Mode after 10 seconds of inactivity.
    """
    global mode

    temp, ldr_val = read_sensors()
    update_oled(temp, ldr_val)

    print("\n[MANUAL MODE] Commands:")
    print("  b - Toggle buzzer")
    print("  l - Toggle LED")
    print("  r - Read sensors now")
    print("  s - Show last 10 sensor readings")
    print("  m - Switch to Auto Mode")

    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)

    
    start_time = time.ticks_ms()  # Record the start time

    while mode == "manual":
        
        if time.ticks_diff(time.ticks_ms(), start_time) > 10_000:
            print("Timeout: Switching back to Auto Mode")
            mode = "auto"
            return

        # Check for input
        if poll.poll(100):  # Timeout of 100ms for polling
            try:
                cmd = sys.stdin.read(3).strip().lower()  
                start_time = time.ticks_ms()  
            except Exception as e:
                print("Input error:", e)
                oled.fill(0)
                oled.text("Serial Unavailable", 0, 0)
                oled.show()
                continue

            if cmd == "b":
                buzzer.value(not buzzer.value())
                print("Buzzer toggled; new state:", "ON" if buzzer.value() else "OFF")
            elif cmd == "l":
                led.value(not led.value())
                print("LED toggled; new state:", "ON" if led.value() else "OFF")
            elif cmd == "r":
                temp, ldr_val = read_sensors()
                if temp is not None and ldr_val is not None:
                    print("Sensor read: Temp: {}°C, Light ADC: {}".format(temp, ldr_val))
                    add_reading(temp, ldr_val)
                    update_oled(temp, ldr_val)
                else:
                    print("Error reading sensors.")
            elif cmd == "s":
                print_readings()
            elif cmd == "m":
                mode = "auto"
                print("Switching to Auto Mode")
            else:
                print("Unknown command.")

# --- Helper Function to Check Button ---
def check_button():
    """
    Check the button state with debounce logic.
    Returns True if the button was pressed, False otherwise.
    """
    global last_button_state, last_button_time
    current_state = button.value()  
    current_time = time.ticks_ms()  

    if current_state == 0 and last_button_state == 1:  # Button pressed (active low)
        if time.ticks_diff(current_time, last_button_time) > debounce_delay:
            last_button_time = current_time
            last_button_state = current_state
            return True
    elif current_state == 1:  # Button released
        last_button_state = current_state

    return False

# --- Main Execution Loop ---
while True:
    # Check if the button was pressed
    if check_button():
        if mode == "auto":
            mode = "manual"
            print("\n[BUTTON] Switching to Manual Mode")
            led.off()
            buzzer.off()
        else:
            mode = "auto"
            print("\n[BUTTON] Switching to Auto Mode")

    # Execute actions based on the current mode
    if mode == "auto":
        auto_mode()
        time.sleep(1)  # Delay between auto measurements
    else:
        manual_mode()
        time.sleep(0.1)