import yaml
import asyncio
import aiohttp
import time
import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="SME Monitor")
templates = Jinja2Templates(directory="templates")

# --- GLOBAL STATE ---
CONFIG = {}
SYSTEM_STATUS = {} 
CONFIG_FILE = "config/config.yaml"
LAST_CONFIG_TIME = 0
LOG_FILE = "logs.txt"

# Sort Order: Critical (0) -> Unknown (1) -> Warning (2) -> OK (3)
STATUS_PRIORITY = {
    "DOWN": 0,
    "UNKNOWN": 1,
    "WARNING": 2,
    "UP": 3,
    "PENDING": 4,
    "DISABLED": 5  # <--- New Lowest Priority
}

def log(message: str):
    with open(LOG_FILE, "a") as f:
        f.write(message + '\n')

def load_config():
    """Loads config and preserves status for existing hosts"""
    global CONFIG, SYSTEM_STATUS, LAST_CONFIG_TIME
    try:
        mtime = os.path.getmtime(CONFIG_FILE)
        if mtime <= LAST_CONFIG_TIME:
            return False 
        
        print(f"Loading configuration from {CONFIG_FILE}...")
        with open(CONFIG_FILE, "r") as f:
            new_config = yaml.safe_load(f) or {}

        new_status = {}
        systems = new_config.get('systems', {})

        for key in systems:
            if key in SYSTEM_STATUS:
                new_status[key] = SYSTEM_STATUS[key]
            else:
                new_status[key] = {
                    "status": "PENDING",
                    "last_check": None,
                    "latency": 0,
                    "message": "Initializing..."
                }
        
        CONFIG = new_config
        SYSTEM_STATUS = new_status
        LAST_CONFIG_TIME = mtime
        return True
    except Exception as e:
        print(f"Error loading config: {e}")
        return False

# --- CHECK LOGIC ---

async def check_default(host: str, warning_threshold: float, timeout_threshold: float):
    target = host
    if not target.startswith("http"):
        target = f"http://{target}"
        
    # Prepare timeout object
    timeout_config = aiohttp.ClientTimeout(total=timeout_threshold)

    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        start = time.time()
        try:
            async with session.get(target) as response:
                duration = round((time.time() - start) * 1000, 2)
                
                # 1. Check HTTP Errors first
                if response.status < 200 or response.status >= 400:
                    return False, "DOWN", f"ERR ({response.status})", duration

                # 2. Check Warning Threshold (duration is in ms, config is in seconds)
                if duration > (warning_threshold * 1000):
                    return True, "WARNING", f"SLOW ({duration}ms)", duration
                
                # 3. Everything OK
                return True, "UP", f"UP ({response.status})", duration

        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
            # 4. Handle Timeout -> Unknown/Purple
            return False, "UNKNOWN", "TIMEOUT", 0
            
        except Exception as e:
            # 5. Connection failures -> Down
            return False, "DOWN", "Connection Error", 0

CHECK_FUNCTIONS = {
    "default": check_default
}

async def perform_check(sys_id: str):
    if sys_id not in CONFIG.get('systems', {}):
        return

    sys_conf = CONFIG['systems'][sys_id]
    check_type = sys_conf.get('check', 'default')
    check_func = CHECK_FUNCTIONS.get(check_type, check_default)
    
    # Get thresholds with defaults (Warning: 30s, Timeout: 60s)
    warn_sec = float(sys_conf.get('warning', 30))
    timeout_sec = float(sys_conf.get('timeout', 60))

    # Determine status
    is_up, status_text, msg, latency = await check_func(sys_conf['host'], warn_sec, timeout_sec)
    
    last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not is_up:
        log(f"{last_check};{status_text};{sys_conf['host']};{msg}")
    
    if sys_id in SYSTEM_STATUS:
        SYSTEM_STATUS[sys_id].update({
            "status": status_text, # UP, DOWN, WARNING, UNKNOWN
            "last_check": last_check,
            "latency": latency,
            "message": msg
        })

# --- BACKGROUND LOOP ---
async def monitoring_loop():
    while True:
        # 1. Hot Reload Check
        load_config()

        # 2. Monitoring Logic
        if 'systems' in CONFIG:
            for sys_id, conf in CONFIG['systems'].items():
                if sys_id not in SYSTEM_STATUS: continue

                # --- NEW LOGIC: Check Active State ---
                is_active = conf.get('active', True) # Default to True if missing
                
                if not is_active:
                    # If inactive, force status to DISABLED and skip the network check
                    SYSTEM_STATUS[sys_id].update({
                        "status": "DISABLED",
                        "message": "Monitoring Paused",
                        # We keep previous latency/checks for history or reset them
                    })
                    continue 
                # -------------------------------------

                last_check_str = SYSTEM_STATUS[sys_id].get("last_check")
                interval = conf.get("interval", 60)
                
                should_run = False
                if not last_check_str:
                    should_run = True
                else:
                    try:
                        last_check = datetime.strptime(last_check_str, "%Y-%m-%d %H:%M:%S")
                        if (datetime.now() - last_check).total_seconds() > interval:
                            should_run = True
                    except ValueError:
                        should_run = True
                
                # Only run check if active AND time is up
                if should_run and is_active:
                    asyncio.create_task(perform_check(sys_id))
        
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    global LAST_CONFIG_TIME
    LAST_CONFIG_TIME = 0 
    load_config()
    asyncio.create_task(monitoring_loop())

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, content_only: bool = False):
    data = []
    current_systems = CONFIG.get('systems', {})
    
    # SORTING LOGIC: Uses STATUS_PRIORITY dict
    sorted_keys = sorted(
        current_systems.keys(), 
        key=lambda k: STATUS_PRIORITY.get(SYSTEM_STATUS.get(k, {}).get('status', 'PENDING'), 99)
    )

    for k in sorted_keys:
        if k not in SYSTEM_STATUS: continue
        item = current_systems[k].copy()
        stats = SYSTEM_STATUS[k]
        item['id'] = k
        item.update(stats)
        data.append(item)
    
    context = {"request": request, "systems": data}
    
    if content_only:
        return templates.TemplateResponse("partials/grid.html", context)

    return templates.TemplateResponse("dashboard.html", context)

@app.get("/check/now")
async def check_now(target: str, type: str = 'single'):
    tasks = []
    if 'systems' not in CONFIG: return RedirectResponse(url="/")

    if type == 'all':
        for sys_id in CONFIG['systems']:
            tasks.append(perform_check(sys_id))
    elif type == 'group':
        for sys_id, conf in CONFIG['systems'].items():
            if conf.get('group') == target:
                tasks.append(perform_check(sys_id))
    elif type == 'single':
        if target in CONFIG['systems']:
            tasks.append(perform_check(target))
    
    if tasks:
        await asyncio.gather(*tasks)
    return RedirectResponse(url="/")