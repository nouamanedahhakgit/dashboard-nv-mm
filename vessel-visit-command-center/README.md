# Nevis Vessel Command Center

One dashboard, one Python file. The app reads the final Excel exports in test
mode and keeps a dedicated function ready for a future API.

## Run

```powershell
pip install -r requirements.txt
streamlit run dashboard.py
```

By default the app reads `../reporting/moveHistory/all data new`. Override it
with `VESSEL_DATA_DIR`. Keep `VESSEL_DATA_MODE=test` until the live API is
available.
# Nevis Vessel Command Center

## Live API configuration

Edit `nevis_api.ini` and enter the Nevis Basic Auth username and password:

```ini
[auth]
username = YOUR_USERNAME
password = YOUR_PASSWORD
```

The dashboard starts in `live` mode by default.

- Vessel visits are fetched from the `vesselVisits` query.
- Only units linked to the returned working visits are fetched from `units_1`.
- Unit queries run concurrently with bounded timeouts and retries.
- Successful responses are cached for 30 seconds.
- A local safety snapshot is used temporarily if Nevis becomes unavailable.
- If no live snapshot exists yet, the Excel test snapshot keeps the interface open.

Configuration values can be overridden with environment variables such as
`NEVIS_API_USERNAME`, `NEVIS_API_PASSWORD`, `NEVIS_UNIT_API_URL`, and
`NEVIS_VESSEL_VISIT_API_URL`.

Set `VESSEL_DATA_MODE=test` to force the Excel test data.
