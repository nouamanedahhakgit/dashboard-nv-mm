# Nevis Vessel Statistics Dashboard

A Streamlit dashboard for vessel-visit operations, shift performance, container
flow, terminal profiles, stops, GMPH, and detailed unit inspection.

## Security

This repository intentionally contains **no operational data and no credentials**.

- `nevis_api.ini` is ignored by Git.
- `data/` is ignored by Git.
- Excel, CSV, pickle, runtime cache, and virtual-environment files are ignored.
- `nevis_api.example.ini` contains placeholders only.

Never put a real username, password, API token, or production host configuration
inside `dashboard.py` or `nevis_api.example.ini`.

## Configure

Create the private configuration file:

```bat
copy nevis_api.example.ini nevis_api.ini
notepad nevis_api.ini
```

Set the real Nevis URLs and Basic Auth credentials only in `nevis_api.ini`:

```ini
[app]
mode = live

[auth]
username = YOUR_USERNAME
password = YOUR_PASSWORD
```

The private file remains local because `.gitignore` excludes it.

## Run on Windows

Install Python 3.12 (64-bit), then run:

```bat
start_dashboard.bat
```

Or run manually:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run dashboard.py
```

Open [http://localhost:8501](http://localhost:8501).

## Optional offline testing

Offline API XML and Excel samples are not committed. Store them locally under
`data/` and select the appropriate private mode in `nevis_api.ini`:

```ini
[app]
mode = api_test
```

or:

```ini
[app]
mode = test
```
