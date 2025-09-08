# main.py — Pico W : pompe + capteur humidité (ADC) + web UI
import network, socket, time, ure
from machine import Pin, ADC

# ---------- CONFIG ----------
SSID = ""
PASSWORD = ""

RELAY_PIN = 2           # IN du module relais
ACTIVE_LOW = False      # True si relais actif à 0

MOISTURE_ADC_PIN = 26   # GP26 / ADC0
SAMPLES = 16            # moyennage pour stabiliser

# Calibrations (à ajuster après mesure DRY/WET)
ADC_DRY  = 60000        # valeur lue sol très sec (à mesurer)
ADC_WET  = 25000        # valeur lue sol humide (à mesurer)

AUTO_MODE = False
THRESHOLD_PERCENT = 35  # en-dessous de ce % → arroser
WATER_SECONDS = 4       # durée d’arrosage en mode auto
# ---------------------------

# LED intégrée
try:
    led = Pin("LED", Pin.OUT)
except:
    led = None

# Relais / pompe
relay = Pin(RELAY_PIN, Pin.OUT)

def set_pump(on: bool):
    if ACTIVE_LOW:
        relay.value(0 if on else 1)
    else:
        relay.value(1 if on else 0)
    if led:
        led.value(1 if on else 0)

set_pump(False)

# Capteur humidité
adc = ADC(MOISTURE_ADC_PIN)

def read_adc_avg(n=SAMPLES):
    s = 0
    for _ in range(n):
        s += adc.read_u16()
        time.sleep_ms(2)
    return s // n

def adc_to_percent(val):
    # mappe ADC_DRY→0% et ADC_WET→100% (borné 0..100)
    if ADC_DRY == ADC_WET:
        return 0
    pct = (ADC_DRY - val) * 100 / (ADC_DRY - ADC_WET)  # plus humide → valeur ADC plus basse
    if pct < 0: pct = 0
    if pct > 100: pct = 100
    return int(pct)

# Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(pm = 0xa11140)
wlan.connect(SSID, PASSWORD)
print("Connexion Wi-Fi…")
t0 = time.ticks_ms()
while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15000:
    time.sleep(0.2)
ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
print("IP =", ip)

# HTML
def html(pump_on, percent, auto_on, threshold):
    btn_text = "Stop" if pump_on else "Start"
    btn_path = "/off" if pump_on else "/on"
    auto_btn = "/auto_off" if auto_on else "/auto_on"
    auto_txt = "Désactiver auto" if auto_on else "Activer auto"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pico Arrosage</title>
<style>
body{{font-family:system-ui,Arial;margin:1.5rem}}
.card{{max-width:520px;padding:1rem 1.2rem;border:1px solid #ddd;border-radius:12px}}
.row{{display:flex;gap:.6rem;flex-wrap:wrap;margin:.6rem 0}}
button{{padding:.7rem 1rem;border-radius:10px;border:0;cursor:pointer}}
.start{{background:#16a34a;color:#fff}}
.stop{{background:#dc2626;color:#fff}}
.auto{{background:#2563eb;color:#fff}}
label,input{{font-size:1rem}}
</style></head><body>
<div class="card">
  <h2>Pico W — Arrosage</h2>
  <p>Humidité sol : <b>{percent}%</b> (seuil {threshold}%)</p>
  <div class="row">
    <form action="{btn_path}" method="get"><button class="{ 'stop' if pump_on else 'start' }">{btn_text}</button></form>
    <form action="{auto_btn}" method="get"><button class="auto">{auto_txt}</button></form>
  </div>
  <form action="/set_threshold" method="get" class="row">
    <label for="v">Seuil&nbsp;%</label>
    <input id="v" name="v" type="number" min="0" max="100" value="{threshold}">
    <button type="submit">OK</button>
  </form>
  <form action="/water_once" method="get" class="row">
    <label for="s">Arroser (s)</label>
    <input id="s" name="s" type="number" min="1" max="30" value="{WATER_SECONDS}">
    <button type="submit">Lancer</button>
  </form>
  <p><small>IP: {ip} • Relais GP{RELAY_PIN} • ADC GP{MOISTURE_ADC_PIN}</small></p>
</div></body></html>"""

# État pompe
pump_on = False
def pump(state):
    global pump_on
    pump_on = bool(state)
    set_pump(pump_on)

# Serveur HTTP
def serve():
    # <-- déplacer les globals ici, tout en haut de la fonction
    global AUTO_MODE, THRESHOLD_PERCENT, WATER_SECONDS, pump_on

    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr); s.listen(2)
    print(f"Web: http://{ip}")

    last_auto = time.ticks_ms()

    while True:
        # --- boucle auto ~1 s
        if AUTO_MODE:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_auto) > 1000:
                last_auto = now
                val = read_adc_avg()
                pct = adc_to_percent(val)
                low  = THRESHOLD_PERCENT - 2
                high = THRESHOLD_PERCENT + 2
                if pct < low and not pump_on:
                    pump(True)
                    t0 = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), t0) < WATER_SECONDS*1000:
                        time.sleep_ms(50)
                    pump(False)
                elif pct > high and pump_on:
                    pump(False)

        # --- HTTP
        try:
            s.settimeout(0.5)
            cl, _ = s.accept()
        except OSError:
            continue

        try:
            req = cl.recv(1024) or b""
            line = req.split(b"\r\n",1)[0]
            path = b"/"
            if line.startswith(b"GET "):
                path = line.split(b" ")[1]

            if path.startswith(b"/on"):
                pump(True)
            elif path.startswith(b"/off"):
                pump(False)
            elif path.startswith(b"/auto_on"):
                AUTO_MODE = True
            elif path.startswith(b"/auto_off"):
                AUTO_MODE = False
            elif path.startswith(b"/water_once"):
                m = ure.search(br"[?&]s=(\d+)", path)
                secs = int(m.group(1)) if m else WATER_SECONDS
                if secs < 1: secs = 1
                if secs > 30: secs = 30
                pump(True); time.sleep(secs); pump(False)
                WATER_SECONDS = secs
            elif path.startswith(b"/set_threshold"):
                m = ure.search(br"[?&]v=(\d+)", path)
                if m:
                    v = int(m.group(1))
                    if v < 0: v = 0
                    if v > 100: v = 100
                    THRESHOLD_PERCENT = v
            elif path.startswith(b"/status"):
                val = read_adc_avg()
                pct = adc_to_percent(val)
                body = '{{"pump":{},"moisture":{},"threshold":{},"auto":{}}}'.format(
                    str(pump_on).lower(), pct, THRESHOLD_PERCENT, str(AUTO_MODE).lower())
                cl.send("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
                cl.send(body); cl.close(); continue

            # Page
            val = read_adc_avg()
            pct = adc_to_percent(val)
            page = html(pump_on, pct, AUTO_MODE, THRESHOLD_PERCENT)
            cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
            cl.send(page)
            cl.close()
        except Exception as e:
            try: cl.close()
            except: pass
            print("HTTP err:", e)

serve()

