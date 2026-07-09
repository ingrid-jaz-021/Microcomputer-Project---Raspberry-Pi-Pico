# ==============================================================================================================
# Proyecto Final: Integración de periféricos con Raspberry Pi Pico
#
# Descripción: Se implementa un sistema que combina sensores, actuadores y módulos de comunicación mediante
#              el uso de GPIO, PWM, ADC, UART, SPI, I2C y One Wire, reproduciendo las prácticas de laboratorio.
#
# Fecha de realización: 12 de mayo de 2026.
# Fecha de entrega: 21 de mayo de 2026.
# Grupo de laboratorio: 4                             Semestre 2026-2
# ==============================================================================================================

from machine import Pin, I2C, PWM, ADC, SPI, UART
import dht
import time
import utime
from DIYables_MicroPython_LCD_I2C import LCD_I2C
from DIYables_MicroPython_LED_Matrix import Max7219

# --- UART0 para HC-05 ---
uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# --- Potenciómetro en GP26 (ADC0) ---
pot = ADC(Pin(26))

# --- LED en GP13 con PWM ---
led_pwm = PWM(Pin(13))
led_pwm.freq(1000)  # frecuencia de 1 kHz

# --- Configuración de Hardware ---
i2c = I2C(0, scl=Pin(5), sda=Pin(4))
lcd = LCD_I2C(i2c, 0x27, 2, 16)
sensor = dht.DHT22(Pin(15))

# --- Botones con Pull-Up ---
btn_unit = Pin(20, Pin.IN, Pin.PULL_UP)
btn_mode = Pin(16, Pin.IN, Pin.PULL_UP)
btn_read = Pin(21, Pin.IN, Pin.PULL_UP)

# --- Servomotor en GP22 ---
servo = PWM(Pin(22))
servo.freq(50)

# --- DIP switch en GP6–GP9 ---
dip_pins = [Pin(i, Pin.IN, Pin.PULL_DOWN) for i in range(6, 9)]

# Leer potenciómetro
valor_adc = pot.read_u16()  # rango 0–65535

# Ajustar brillo del LED según el potenciómetro
led_pwm.duty_u16(valor_adc)

# Mostrar valor en consola
voltaje = 3.3 * valor_adc / 65535
print("ADC:", valor_adc, "Voltaje:", round(voltaje, 2), "V")

# --- Configuración SPI para matriz ---
spi = SPI(0, baudrate=10000000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(19))
cs_pin = Pin(17, Pin.OUT)

# --- Crear objeto de matriz (4 módulo 8x8 en cascada) ---
display = Max7219(spi, cs_pin, num_matrices=4)
display.set_brightness(4)  # <-- Ajustamos el brillo

# --- Variables de Estado y Banderas ---
usar_fahrenheit = False
modo = 0  # 0=ambos, 1=temp, 2=hum
temperatura = 0
humedad = 0
flag_actualizar_lcd = True
flag_leer_sensor = True
ultimo_tiempo_ms = 0
DEBOUNCE_DELAY = 200
estado_servo = ""  # guarda el último estado mostrado
ultimo_adc = None  # guarda el último valor mostrado

# --- Funciones auxiliares ---
def c_a_f(c):
    return c * 9/5 + 32

def pad16(texto):
    texto = str(texto)
    if len(texto) < 16:
        return texto + " " * (16 - len(texto))
    else:
        return texto[:16]

def mover_servo(grados):
    min_us = 500   # pulso mínimo (~0°)
    max_us = 2400  # pulso máximo (~180°)
    duty = int(((grados/180)*(max_us-min_us) + min_us) / 20000 * 65535)
    servo.duty_u16(duty)

def leer_dip():
    valor = 0
    for i, pin in enumerate(dip_pins):
        if pin.value():
            valor |= (1 << i)
    return valor

def mostrar_estado_matriz(texto, x=0):
    display.clear()                # Borra
    display.print(texto, col=x)    # Imprime texto directo, sin espejado
    display.show()

def controlar_servo(valor):
    global estado_servo
    nuevo_estado = ""

    if valor == 0:
        mover_servo(0) # 0000 → PARO
        nuevo_estado = "PARO"
    elif valor == 1:
        mover_servo(0) # 0001 → SERVO A 0°
        nuevo_estado = "0°"
    elif valor == 2:
        mover_servo(45) # 0010 → SERVO A 45°
        nuevo_estado = "45°"
    elif valor == 3:
        mover_servo(90) # 0011 → SERVO A 90°
        nuevo_estado = "90°"
    elif valor == 4:
        mover_servo(135) # 0100 → SERVO A 135°
        nuevo_estado = "135°"
    elif valor == 5:
        mover_servo(180) # 0101 → SERVO A 180°
        nuevo_estado = "180°"

    # Solo imprime si hay un estado válido y diferente al anterior
    if nuevo_estado and nuevo_estado != estado_servo:
        estado_servo = nuevo_estado
        print("Estado del servomotor:", estado_servo)
        mostrar_estado_matriz(estado_servo, 0)

# --- Rutinas de Interrupción ---
def FuncISR1(pin):
    global usar_fahrenheit, flag_actualizar_lcd, ultimo_tiempo_ms
    if utime.ticks_diff(utime.ticks_ms(), ultimo_tiempo_ms) > DEBOUNCE_DELAY:
        usar_fahrenheit = not usar_fahrenheit
        print("Unidad cambiada!")
        flag_actualizar_lcd = True
        ultimo_tiempo_ms = utime.ticks_ms()

def FuncISR2(pin):
    global modo, flag_actualizar_lcd, ultimo_tiempo_ms
    if utime.ticks_diff(utime.ticks_ms(), ultimo_tiempo_ms) > DEBOUNCE_DELAY:
        modo = (modo + 1) % 3
        print("Modo cambiado!")
        flag_actualizar_lcd = True
        ultimo_tiempo_ms = utime.ticks_ms()

def FuncISR3(pin):
    global flag_leer_sensor, ultimo_tiempo_ms
    if utime.ticks_diff(utime.ticks_ms(), ultimo_tiempo_ms) > DEBOUNCE_DELAY:
        flag_leer_sensor = True
        ultimo_tiempo_ms = utime.ticks_ms()

# --- Configuración de IRQ ---
btn_unit.irq(trigger=Pin.IRQ_FALLING, handler=FuncISR1)
btn_mode.irq(trigger=Pin.IRQ_FALLING, handler=FuncISR2)
btn_read.irq(trigger=Pin.IRQ_FALLING, handler=FuncISR3)

# --- Bucle Principal ---
print("Sistema listo. Esperando interrupciones...")
print("Sistema listo. Enviando datos por Bluetooth...")

while True:
    # Leer sensor
    if flag_leer_sensor:
        try:
            sensor.measure()
            temperatura = sensor.temperature()
            humedad = sensor.humidity()
            print("Temp:", temperatura, "C  Hum:", humedad, "%")
            flag_actualizar_lcd = True
        except Exception as e:
            print("Error sensor:", e)
        flag_leer_sensor = False

    # Actualizar LCD
    if flag_actualizar_lcd:
        if usar_fahrenheit:
            temp_mostrar = c_a_f(temperatura)
            unidad = "F"
        else:
            temp_mostrar = temperatura
            unidad = "C"

        if modo == 0:
            linea1 = "Temp: {:.1f}\xdf{}".format(temp_mostrar, unidad)
            linea2 = "Hum: {:.1f}%".format(humedad)
        elif modo == 1:
            linea1 = "Temperatura"
            linea2 = "{:.1f}\xdf{}".format(temp_mostrar, unidad)
        else:
            linea1 = "Humedad"
            linea2 = "{:.1f}%".format(humedad)

        lcd.set_cursor(0, 0)
        lcd.print(pad16(linea1))
        lcd.set_cursor(0, 1)
        lcd.print(pad16(linea2))
        flag_actualizar_lcd = False

    # Controlar servo según DIP
    valor_dip = leer_dip()
    controlar_servo(valor_dip)

    # Controlar LED con potenciómetro
    valor_adc = pot.read_u16()
    led_pwm.duty_u16(valor_adc)
    voltaje = 3.3 * valor_adc / 65535
    # Solo imprime si cambió significativamente
    if ultimo_adc is None or abs(valor_adc - ultimo_adc) > 500:  
        print("ADC:", valor_adc, "Voltaje:", round(voltaje, 2), "V")
        ultimo_adc = valor_adc
    
    # Leer ADC
    valor_adc = pot.read_u16()
    led_pwm.duty_u16(valor_adc)
    voltaje = 3.3 * valor_adc / 65535

    # Solo enviar si cambió significativamente
    if ultimo_adc is None or abs(valor_adc - ultimo_adc) > 500:
        # Mostrar en consola
        print("ADC:", valor_adc, "Voltaje:", round(voltaje, 2), "V")

        # Convertir a hexadecimal y enviar por UART
        hex_str = "{:04X}".format(valor_adc)   # ejemplo: '3FA2'
        uart.write("ADC HEX: " + hex_str + "\n")

        ultimo_adc = valor_adc

    time.sleep_ms(200)