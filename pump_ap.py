# main.py — Pico W : AP Wi-Fi + pompe + capteur humidité (AJAX refresh 1s)
import network, socket, time, ure
from machine import Pin, ADC

# ---------- CONFIG ----------
SSID_AP = "Autowalter"           # SSID du point d'accès
PASSWORD_AP = "WelcomeHome"      # ≥ 8 caractères
PORT = 80

RELAY_PIN = 2
ACTIVE_LOW = False

MOISTURE_ADC_PIN = 26   # GP26 / ADC0
SAMPLES = 16

# Calibrations (à ajuster après mesure DRY/WET)
ADC_DRY  = 44000
ADC_WET  = 19500

AUTO_MODE = False
THRESHOLD_PERCENT = 35
WATER_SECONDS = 1
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
pump_on = False

# Capteur humidité
adc = ADC(MOISTURE_ADC_PIN)
def read_adc_avg(n=SAMPLES):
    s = 0
    for _ in range(n):
        s += adc.read_u16()
        time.sleep_ms(2)
    return s // n

def adc_to_percent(val):
    if ADC_DRY == ADC_WET:
        return 0
    pct = (ADC_DRY - val) * 100 / (ADC_DRY - ADC_WET)  # plus humide → ADC plus bas
    if pct < 0: pct = 0
    if pct > 100: pct = 100
    return int(pct)

# ---------- MODE POINT D'ACCÈS (AP) ----------
ap = network.WLAN(network.AP_IF)
ap.config(essid=SSID_AP, password=PASSWORD_AP)  # <-- enlever authmode
ap.active(True)
while not ap.active():
    time.sleep_ms(100)
ip = ap.ifconfig()[0]   # typiquement 192.168.4.1
print("Point d'accès actif")
print("SSID:", SSID_AP, " Password:", PASSWORD_AP)
print("IP Pico:", ip)
# --------------------------------------------

# HTML avec JS qui rafraîchit /status chaque seconde
def html(p_on, percent, auto_on, threshold):
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
small{{color:#666}}
.badge{{padding:.2rem .5rem;border-radius:.5rem;background:#eee}}
</style></head><body>
<div class="card">
  <h2>Pico W — Arrosage</h2>
  <p>Humidité sol : <b id="hum">{percent}%</b>
     <small>(seuil <span id="th">{threshold}</span>%)</small></p>

  <div class="row">
    <form action="{'/off' if p_on else '/on'}" method="get">
      <button class="{ 'stop' if p_on else 'start' }" id="btnPump">{'Stop' if p_on else 'Start'}</button>
    </form>
    <form action="{'/auto_off' if auto_on else '/auto_on'}" method="get">
      <button class="auto" id="btnAuto">{'Désactiver auto' if auto_on else 'Activer auto'}</button>
    </form>
    <span class="badge">Pompe: <span id="pstate">{'ON' if p_on else 'OFF'}</span></span>
    <span class="badge">Auto: <span id="astate">{'ON' if auto_on else 'OFF'}</span></span>
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
</div>

<script>
async function refresh() {{
  try {{
    const r = await fetch('/status?ts=' + Date.now(), {{cache:'no-store'}});
    const j = await r.json();
    document.getElementById('hum').textContent = j.moisture + '%';
    document.getElementById('th').textContent  = j.threshold;
    document.getElementById('pstate').textContent = j.pump ? 'ON' : 'OFF';
    document.getElementById('astate').textContent = j.auto ? 'ON' : 'OFF';
    const btnPump = document.getElementById('btnPump');
    if (btnPump) {{
      btnPump.textContent = j.pump ? 'Stop' : 'Start';
      btnPump.className = j.pump ? 'stop' : 'start';
      btnPump.parentElement.action = j.pump ? '/off' : '/on';
    }}
    const btnAuto = document.getElementById('btnAuto');
    if (btnAuto) {{
      btnAuto.textContent = j.auto ? 'Désactiver auto' : 'Activer auto';
      btnAuto.parentElement.action = j.auto ? '/auto_off' : '/auto_on';
    }}
  }} catch(e) {{}}
}}
refresh();
setInterval(refresh, 1000);
</script>
</body></html>"""

# Contrôle pompe
def pump(state_bool):
    global pump_on
    pump_on = bool(state_bool)
    set_pump(pump_on)

# Serveur HTTP
def serve():
    global AUTO_MODE, THRESHOLD_PERCENT, WATER_SECONDS, pump_on
    addr = socket.getaddrinfo("0.0.0.0", PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr); s.listen(2)
    print(f"Web: http://{ip}:{PORT}")

    last_auto = time.ticks_ms()

    while True:
        # --- boucle auto (toutes ~7 s)
        if AUTO_MODE:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_auto) > 7000:
                last_auto = now
                val = read_adc_avg()
                pct = adc_to_percent(val)
                low  = THRESHOLD_PERCENT - 2
                high = THRESHOLD_PERCENT + 2
                if pct < low and not pump_on:
                    pump(True)
                    t0 = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), t0) < WATER_SECONDS*1000:
                        time.sleep_ms(1000)
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

            if path == b"/":
                val = read_adc_avg()
                pct = adc_to_percent(val)
                page = html(pump_on, pct, AUTO_MODE, THRESHOLD_PERCENT)
                cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
                cl.send(page); cl.close(); continue

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
                cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n")
                cl.send(body); cl.close(); continue
            elif path.startswith(b"/favicon.ico"):
                cl.send(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                cl.close(); continue

            # fallback
            val = read_adc_avg()
            pct = adc_to_percent(val)
            page = html(pump_on, pct, AUTO_MODE, THRESHOLD_PERCENT)
            cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
            cl.send(page)
            cl.close()
        except Exception as e:
            try: cl.close()
            except: pass
            print("HTTP err:", e)

serve()

