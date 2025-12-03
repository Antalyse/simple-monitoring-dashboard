Simple Monitoring Dashboard
==================

A lightweight, Python-based monitoring dashboard designed for Small and Medium Enterprises (SMEs). It uses **FastAPI** and **AsyncIO** to provide real-time status checks, dashboard visualization, and instant alerts via visual indicators.

This tool is designed to be "config-first," meaning all systems, thresholds, and groups are managed via a simple `config.yaml` file that supports **Hot Reloading** (changes apply instantly without restarting the server).

Features
--------

-   **Real-time Monitoring:** Asynchronous non-blocking HTTP/Ping checks.

-   **YAML Configuration:** Manage all hosts, groups, and docs in one file.

-   **Hot Reloading:** Modify `config.yaml` and the system updates instantly.

-   **Status prioritization:**

    -   🔴 **Critical (DOWN):** HTTP Error or Connection Refused.

    -   🟣 **Unknown (TIMEOUT):** Request exceeded `timeout` threshold.

    -   🟡 **Warning (SLOW):** Request succeeded but exceeded `warning` threshold.

    -   🟢 **OK (UP):** System healthy and fast.

    -   ⚪ **Disabled:** System set to `active: false`.

-   **Auto-Refreshing Dashboard:** Frontend updates status every 5 seconds without full page reloads.

-   **API Endpoints:** Trigger checks manually via API (Single host, Group, or All).

Installation
------------

1.  Clone the repository

    git clone https://github.com/yourusername/sme-monitor.git

    cd sme-monitor

2.  Install Dependencies

    pip install fastapi uvicorn pyyaml aiohttp jinja2



Configuration (`config.yaml`)
-----------------------------

Define your systems in `config.yaml`. You do not need to restart the application when you change this file.

YAML

```
systems:
  # Standard Healthy Host
  production_api:
    name: Production API
    description: Main Gateway
    docs: https://wiki.mycompany.com/api
    host: api.mycompany.com
    interval: 60           # Seconds between checks
    check: default
    group: production
    active: true

  # Host with Custom Thresholds
  legacy_db:
    name: Legacy Database
    description: Old SQL Server
    host: 192.168.1.50
    interval: 30
    warning: 2.0           # Yellow if response > 2 seconds
    timeout: 5.0           # Purple if response > 5 seconds
    active: true

  # Disabled Host (Will appear Grey at bottom)
  archived_server:
    name: Old File Server
    host: 10.0.0.5
    active: false          # Skips checks, shows as DISABLED

```

### Configuration Fields

| **Field** | **Description** | **Default** |
| --- | --- | --- |
| `name` | Display name on the dashboard. | Required |
| `description` | Subtitle text for context. | Required |
| `docs` | Link to internal wiki/troubleshooting docs. | Optional |
| `host` | URL or IP to check. (Auto-prefixes `http://` if missing). | Required |
| `interval` | How often (in seconds) to check this host. | `60` |
| `warning` | Time (in seconds) before status turns **Yellow**. | `30` |
| `timeout` | Time (in seconds) before request aborts and turns **Purple**. | `60` |
| `active` | If `false`, stops checking and moves to bottom (Grey). | `true` |
| `group` | Used for grouping and API batch checks. | Optional |

Usage
-----

Start the server using Uvicorn:

uvicorn main:app --reload --host 0.0.0.0 --port 8000

-   **Dashboard:** Open `http://localhost:8000` in your browser.


API Endpoints
-------------

You can trigger immediate checks without waiting for the scheduled interval.

-   Check All Hosts:

    GET /check/now?target=all&type=all

-   Check Specific Group:

    GET /check/now?target=production&type=group

-   Check Single Host:

    GET /check/now?target=production_api&type=single



License
-------

Apache 2.0 License