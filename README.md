# Interiérové sluneční hodiny

Bakalářská práce – Raspberry Pi zařízení simulující sluneční hodiny pomocí LED pásku s 24 LED diodami. Čas je zobrazován jako pozice svítící LED na kruhu, barvu světla lze nastavit fyzicky pomocí RGB potenciometru nebo vzdáleně přes webové rozhraní. Zařízení je napojeno na Azure Functions pro cloudovou synchronizaci stavu.

---

## Obsah

- [Funkce](#funkce)
- [Architektura](#architektura)
- [Hardware](#hardware)
- [Struktura projektu](#struktura-projektu)
- [Instalace](#instalace)
- [Konfigurace](#konfigurace)
- [Spuštění](#spuštění)
- [Webové rozhraní](#webové-rozhraní)
- [Azure backend](#azure-backend)
- [Nasazení Azure infrastruktury](#nasazení-azure-infrastruktury)

---

## Funkce

- **Analogový displej času** – jedna LED na kruhu 24 diod zobrazuje aktuální čas v 30minutových krocích
- **RGB barva** – uživatel volí barvu svítící LED; výchozí je teplá bílá (255, 140, 0)
- **E-paper displej** – 2,13" Waveshare displej zobrazuje digitální čas (HH:MM); při nastavování barvy zobrazuje název kanálu a aktuální hodnotu
- **RGB potenciometr** – fyzické nastavení barvy přímo na zařízení; krokem přes tlačítko se přepíná kanál R → G → B → uložit
- **PIR senzor** – pohybový senzor HC-SR501 automaticky zhasíná hodiny při nepřítomnosti; chování lze vypnout přes webové rozhraní
- **Lokální web** – Flask webserver dostupný v lokální síti na portu 5000 s plnohodnotným UI (slidery, color picker, stav PIR)
- **Azure synchronizace** – každých 5 s stahuje konfiguraci (RGB, enabled, use_pir) z Azure; každých 10 s pushuje živý stav (čas zařízení, pohyb)
- **Synchronizace času** – při startu se čas synchronizuje z timeapi.io přes HTTPS s až 10 pokusy

---

## Architektura

```
┌─────────────────────────────────────────────┐
│              Raspberry Pi                   │
│                                             │
│  main.py ──► controller.py (sdílený stav)   │
│      │                                      │
│      ├──► led_strip.py   (WS2812B, 24 LED)  │
│      ├──► epaper_display.py (2.13" V4)      │
│      ├──► rgb_pot.py     (PIM523 přes I2C)  │
│      ├──► pir_sensor.py  (HC-SR501)         │
│      ├──► time_sync.py   (timeapi.io)       │
│      ├──► webapp.py      (Flask :5000)      │
│      └──► azure_sync.py  (polling vlákno)   │
└──────────────────┬──────────────────────────┘
                   │ HTTPS REST
┌──────────────────▼──────────────────────────┐
│           Azure Functions                   │
│                                             │
│  GET  /api/state   – stažení konfigurace    │
│  POST /api/state   – push živého stavu      │
│  POST /api/rgb     – nastavení barvy        │
│  POST /api/enabled – zapnout / vypnout      │
│  POST /api/pir     – PIR režim on/off       │
│                                             │
│  Stav uložen v Azure Table Storage          │
└─────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────┐
│  Statický frontend (Azure Blob Storage)     │
│  sundial-azure/frontend/                    │
└─────────────────────────────────────────────┘
```

---

## Hardware

| Komponenta | Popis | GPIO / rozhraní |
|---|---|---|
| Raspberry Pi 4 | Hlavní řídící jednotka | – |
| WS2812B LED pásek | 24 LED diod, kruhové uspořádání | GPIO 18 (PWM) |
| Waveshare 2.13" e-paper V4 | Digitální displej času | SPI |
| Pimoroni RGB Encoder (PIM523) | Potenciometr + RGB LED v knoflíku | I2C (0x0E) |
| HC-SR501 PIR senzor | Detekce přítomnosti | GPIO 16 |
| Tlačítko | Přepínání kanálů R/G/B při konfiguraci | GPIO 20 |

### Zapojení tlačítka

Jedna nožka na GPIO 20, druhá na GND (pin 39). Interní pull-up rezistor je aktivován v kódu.

### LED pásek

Pásek má celkem 24 LED (indexy 0–23). Všechny jsou aktivní a mapují se na 12 hodin × 2 půlhodinové kroky. Přepínání nastává v minutě 15 (přechod na danou hodinu) a minutě 45 (přechod na půl hodiny vpřed).

---

## Struktura projektu

```
.
├── sundial/                    # Hlavní Python balíček (kód pro RPi)
│   ├── main.py                 # Vstupní bod, hlavní smyčka
│   ├── config.py               # Konstanty a konfigurace pinů
│   ├── controller.py           # Sdílený stav (RGB, PIR, enabled) s zámkem
│   ├── led_strip.py            # Ovládání WS2812B pásku
│   ├── epaper_display.py       # Waveshare 2.13" e-paper
│   ├── rgb_pot.py              # RGB potenciometr PIM523 přes ioexpander
│   ├── pir_sensor.py           # HC-SR501 pohybový senzor
│   ├── time_sync.py            # Synchronizace času z timeapi.io
│   ├── azure_sync.py           # Polling / push do Azure Functions
│   ├── webapp.py               # Lokální Flask webserver
│   ├── templates/
│   │   └── index.html          # Hlavní šablona lokálního webu
│   └── static/
│       ├── app.js              # Frontend logika lokálního webu
│       └── style.css           # Styly lokálního webu
│
├── sundial-azure/              # Azure infrastruktura a cloudový backend
│   ├── api/
│   │   ├── function_app.py     # Azure Functions (REST API)
│   │   ├── host.json
│   │   └── requirements.txt
│   ├── frontend/               # Statický web pro Azure (identický s local)
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   ├── infra/
│   │   ├── main.bicep          # IaC: Storage, Function App, statický web
│   │   └── main.parameters.json
│   └── azure.yaml              # azd konfigurace
│
├── sundial_pot.py              # Spouštěcí skript (volá sundial.main.main)
├── test_web.py                 # Testovací spuštění webserveru bez hardware
├── LEGACY_sundial_pot.py       # Starší verze s potenciometrem (archiv)
├── LEGACY_sundial_touch.py     # Starší verze s touch displayem (archiv)
└── .gitignore
```

---

## Instalace

### Požadavky

- Raspberry Pi OS (Bullseye nebo novější)
- Python 3.10+
- Povolená rozhraní: SPI, I2C, a jednodrátová sběrnice pro LED (`dtoverlay=pwm` v `/boot/config.txt`)

### Systémové závislosti

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv \
    fonts-dejavu-core libjpeg-dev zlib1g-dev
```

### Python závislosti

```bash
cd /home/jakub/sundial   # kořenový adresář repozitáře
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Obsah `requirements.txt`:

```
RPi.GPIO
rpi-ws281x
Pillow
pimoroni-ioexpander
requests
flask
smbus2
```

### TP_lib (e-paper knihovna od Waveshare)

Knihovna není součástí balíčku PyPI. Je třeba ji naklonovat ručně:

```bash
git clone https://github.com/waveshare/Touch_e-Paper_HAT.git \
    /home/jakub/Touch_e-Paper_Code
```

Cesta `/home/jakub/Touch_e-Paper_Code/python/lib` je přidána na `sys.path` automaticky při startu.

---

## Konfigurace

Veškerá konfigurace se nachází v souboru `sundial/config.py`:

```python
# Časová zóna
TZ = ZoneInfo("Europe/Prague")

# LED pásek
TOTAL_LED_COUNT = 24      # počet LED na pásku
LED_PIN = 18              # GPIO pin datového signálu
ACTIVE_LED_START = 0      # první LED pro hodiny
ACTIVE_LED_END = 23       # poslední LED pro hodiny (musí být 24 pozic celkem)

# GPIO piny
BUTTON_PIN = 20           # tlačítko pro nastavení barvy
PIR_PIN = 16              # výstup PIR senzoru HC-SR501

# RGB potenciometr (I2C adresa PIM523)
I2C_ADDR = 0x0E
```

URL Azure Functions API se nastavuje přes proměnnou prostředí:

```bash
export SUNDIAL_API_URL="https://func-sundial-xxxx.azurewebsites.net"
```

Výchozí hodnota je napevno zakódována v `azure_sync.py`.

---

## Spuštění

### Na Raspberry Pi (produkce)

```bash
source .venv/bin/activate
sudo -E python3 sundial_pot.py
```

> `sudo` je vyžadováno pro přístup k GPIO a LED pásku (rpi-ws281x potřebuje root).  
> `-E` zachová proměnné prostředí (včetně `SUNDIAL_API_URL`).

### Jako systemd služba

```ini
# /etc/systemd/system/sundial.service
[Unit]
Description=Interiérové sluneční hodiny
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/jakub/sundial/.venv/bin/python3 /home/jakub/sundial/sundial_pot.py
WorkingDirectory=/home/jakub/sundial
Environment=SUNDIAL_API_URL=https://func-sundial-xxxx.azurewebsites.net
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable sundial
sudo systemctl start sundial
```

### Testování webového rozhraní bez hardware

```bash
python3 test_web.py
# → http://localhost:5000
```

---

## Webové rozhraní

Lokální Flask webserver je dostupný na `http://<IP-raspberry>:5000`.

**Dostupné funkce:**

- Zobrazení aktuálního stavu zařízení (čas, zapnuto, PIR, pohyb)
- Zapnutí / vypnutí celého zařízení
- Přepnutí PIR režimu (hodiny svítí vždy × pouze při detekci pohybu)
- Nastavení barvy LED pomocí RGB sliderů, číselných vstupů nebo interaktivního color pickeru (knihovna Pickr)

**API endpointy (lokální):**

| Metoda | URL | Popis |
|---|---|---|
| GET | `/api/state` | Vrátí celý stav jako JSON |
| POST | `/api/enabled` | `{ "enabled": true/false }` |
| POST | `/api/pir` | `{ "use_pir": true/false }` |
| POST | `/api/rgb` | `{ "r": 0–255, "g": 0–255, "b": 0–255 }` |

---

## Azure backend

Cloudový backend slouží k ovládání zařízení na dálku (mimo lokální síť).

**Technologie:**
- Azure Functions (Python 3.11, Consumption plán)
- Azure Table Storage (tabulka `sundial`, partition key `config`, row key `state`)

**API endpointy (cloud):**

| Metoda | URL | Popis |
|---|---|---|
| GET | `/api/state` | Celý stav uložený v Table Storage |
| POST | `/api/state` | Aktualizace `device_time`, `last_motion`, `last_motion_text` |
| POST | `/api/rgb` | Nastavení barvy (RPi přečte při příštím pollu) |
| POST | `/api/enabled` | Zapnutí / vypnutí |
| POST | `/api/pir` | PIR režim on/off |

Raspberry Pi stahuje stav každých **5 sekund** a pushuje živá data každých **10 sekund**. HTTP volání běží vždy ve vlákně na pozadí, aby neblokovala hlavní smyčku hodin.

---

## Nasazení Azure infrastruktury

Infrastruktura je definována v Bicep šablonách a nasazuje se pomocí [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/).

```bash
cd sundial-azure

# Přihlásit se do Azure
az login
azd auth login

# Inicializovat prostředí
azd env new sundial

# Nasadit vše (infrastruktura + Function App + statický web)
azd up
```

Po úspěšném nasazení vypíše azd URL Function App, kterou je třeba nastavit jako `SUNDIAL_API_URL`.

Statické soubory frontendu (`sundial-azure/frontend/`) je třeba nahrát do Blob Storage kontejneru `$web` ručně nebo přes Azure CLI:

```bash
az storage blob upload-batch \
    --account-name <STORAGE_NAME> \
    --destination '$web' \
    --source sundial-azure/frontend/
```

---

## Licence

Projekt vznikl jako bakalářská práce. Veškerý kód je dostupný pro studijní účely.
