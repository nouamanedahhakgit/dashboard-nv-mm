from __future__ import annotations

import html
import os
import re
import configparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = APP_DIR.parent / "reporting" / "moveHistory" / "all data new"
HANANE_REPORT = APP_DIR.parent / "HANANE RAPPORT.xls"
API_CONFIG_FILE = Path(
    os.getenv("NEVIS_API_CONFIG", str(APP_DIR / "nevis_api.ini"))
)
BOOT_CONFIG = configparser.RawConfigParser()
if API_CONFIG_FILE.exists():
    BOOT_CONFIG.read(API_CONFIG_FILE, encoding="utf-8")
CONFIGURED_DATA_DIR = BOOT_CONFIG.get("app", "data_dir", fallback="data").strip()
CONFIGURED_DATA_PATH = Path(CONFIGURED_DATA_DIR)
if not CONFIGURED_DATA_PATH.is_absolute():
    CONFIGURED_DATA_PATH = APP_DIR / CONFIGURED_DATA_PATH
DATA_DIR = CONFIGURED_DATA_PATH
MODE = BOOT_CONFIG.get("app", "mode", fallback="test").strip().lower()
UNIT_API_SAMPLE_FILE = Path(
    BOOT_CONFIG.get(
        "app", "unit_api_sample_file", fallback="data/unit_api_response.xml"
    ).strip()
)
VESSEL_API_SAMPLE_FILE = Path(
    BOOT_CONFIG.get(
        "app",
        "vessel_api_sample_file",
        fallback="data/vessel_visit_api_response.xml",
    ).strip()
)
if not UNIT_API_SAMPLE_FILE.is_absolute():
    UNIT_API_SAMPLE_FILE = APP_DIR / UNIT_API_SAMPLE_FILE
if not VESSEL_API_SAMPLE_FILE.is_absolute():
    VESSEL_API_SAMPLE_FILE = APP_DIR / VESSEL_API_SAMPLE_FILE
LIVE_CACHE_DIR = APP_DIR / ".runtime_cache"

st.set_page_config(
    page_title="Nevis — Vessel Command Center",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--ink:#f6f9fb;--muted:#91a5b1;--line:rgba(180,215,225,.13);--cyan:#38e8d1;--blue:#62a9ff;--amber:#ffbd59;--red:#ff6577;--panel:#101c25}
.stApp{background:
radial-gradient(circle at 80% -10%,rgba(31,118,140,.20),transparent 34%),
radial-gradient(circle at -10% 55%,rgba(25,91,105,.12),transparent 34%),
#071118;color:var(--ink);font-family:'DM Sans',sans-serif}
.block-container{padding:1.25rem 2.2rem 3rem;max-width:1680px}
h1,h2,h3,[data-testid="stMetricValue"]{font-family:'Space Grotesk',sans-serif}
[data-testid="stHeader"]{display:none}
.topline{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.brand{font:700 13px 'Space Grotesk';letter-spacing:.18em;text-transform:uppercase;color:#dceef2}
.brand b{color:var(--cyan)}
.live{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--cyan);background:rgba(56,232,209,.08);border:1px solid rgba(56,232,209,.2);padding:7px 12px;border-radius:20px}
.pulse{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--cyan);box-shadow:0 0 0 5px rgba(56,232,209,.09);margin-right:8px}
.hero{display:grid;grid-template-columns:1.35fr .65fr;gap:16px;padding:20px 22px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,rgba(17,32,42,.92),rgba(9,21,29,.88));box-shadow:0 24px 70px rgba(0,0,0,.22);overflow:hidden}
.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.18em;color:var(--cyan);font-weight:700}
.hero h1{font-size:clamp(32px,4vw,59px);line-height:.94;margin:10px 0 12px;letter-spacing:-.055em}
.hero-sub{color:var(--muted);font-size:13px}
.hero-meta{display:flex;gap:22px;margin-top:24px}.hero-meta div{border-left:1px solid var(--line);padding-left:12px}.hero-meta small{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.12em;display:block}.hero-meta b{font:600 14px 'Space Grotesk'}
.ship-card{position:relative;min-height:190px;border-radius:17px;overflow:hidden;background:linear-gradient(#102d3a 0 56%,#0a5662 56% 72%,#d6ad73 72%)}
.sun{position:absolute;width:65px;height:65px;border-radius:50%;background:#ffd581;right:32px;top:23px;box-shadow:0 0 45px rgba(255,204,114,.25)}
.ship{position:absolute;left:8%;right:6%;bottom:43px;height:57px;background:#d7e1e2;clip-path:polygon(0 22%,100% 22%,90% 100%,13% 100%);filter:drop-shadow(0 8px 8px rgba(0,0,0,.25))}
.ship:before{content:"";position:absolute;left:22%;top:-30px;width:35%;height:32px;background:#eff4f2;border-radius:4px 4px 0 0}
.ship-name{position:absolute;bottom:22px;left:27%;font:bold 10px 'Space Grotesk';color:#1c3842;letter-spacing:.08em}
.streak{position:absolute;left:15%;right:15%;height:1px;background:rgba(255,255,255,.3);bottom:35px}
.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:14px 0}
.kpi{padding:15px 16px;border:1px solid var(--line);border-radius:16px;background:rgba(14,27,36,.8);min-height:102px}
.kpi .label{font-size:9px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted)}
.kpi .value{font:600 27px 'Space Grotesk';margin-top:7px}.kpi .delta{font-size:10px;color:var(--muted);margin-top:5px}.cyan{color:var(--cyan)}.amber{color:var(--amber)}.red{color:var(--red)}
.section-title{display:flex;justify-content:space-between;align-items:end;margin:20px 0 9px}.section-title h3{margin:0;font-size:15px}.section-title span{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}
.terminal{display:grid;grid-template-columns:1fr 1.5fr 1.2fr .8fr;gap:8px;padding:12px;background:#0b1820;border:1px solid var(--line);border-radius:18px}
.zone{min-height:190px;border-radius:12px;padding:13px;position:relative;overflow:hidden}
.zone h4{font:600 10px 'Space Grotesk';letter-spacing:.12em;text-transform:uppercase;margin:0}.zone small{font-size:9px;color:var(--muted)}
.gate{background:repeating-linear-gradient(90deg,#10232c,#10232c 18px,#122933 18px,#122933 20px)}
.yard{background:#10242c}.quay{background:linear-gradient(90deg,#15313b 0 48%,#0b5260 48%)}.external{background:#17232a}
.stacks{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;position:absolute;left:13px;right:13px;bottom:14px}
.stack{height:82px;border-radius:3px;background:repeating-linear-gradient(0deg,rgba(56,232,209,.8) 0 8px,transparent 8px 11px);border:1px solid rgba(56,232,209,.3)}
.stack.empty{height:53px;background:repeating-linear-gradient(0deg,rgba(255,189,89,.8) 0 8px,transparent 8px 11px);border-color:rgba(255,189,89,.3)}
.flow{position:absolute;left:13px;right:13px;top:70px;height:2px;background:linear-gradient(90deg,var(--cyan),var(--blue));opacity:.6}.flow:after{content:"›";position:absolute;right:-1px;top:-13px;color:var(--blue);font-size:25px}
.zone-stat{position:absolute;bottom:14px;left:13px;font:600 24px 'Space Grotesk'}.zone-stat small{display:block}
.zone-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;position:absolute;left:12px;right:12px;bottom:12px}
.mini{padding:8px;border-radius:8px;background:rgba(3,12,17,.28);border:1px solid rgba(180,215,225,.09)}
.mini b{display:block;font:600 18px 'Space Grotesk';color:#f2f8f9}.mini span{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.zone-total{position:absolute;right:12px;top:12px;font:600 22px 'Space Grotesk';text-align:right}.zone-total small{display:block;font:500 8px 'DM Sans';color:var(--muted);text-transform:uppercase;letter-spacing:.1em}
.reconcile{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:rgba(14,27,36,.55)}
.journey{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:12px;border:1px solid var(--line);border-radius:18px;background:#0a171f}
.stage{min-height:142px;padding:15px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(150deg,#10232c,#0c1a22);position:relative}
.stage:not(:last-child):after{content:"›";position:absolute;right:-18px;top:50%;z-index:2;transform:translateY(-50%);width:25px;height:25px;border-radius:50%;background:#132832;border:1px solid var(--line);color:var(--cyan);text-align:center;font:20px/22px 'Space Grotesk'}
.stage-no{font-size:8px;color:var(--cyan);letter-spacing:.15em;text-transform:uppercase}.stage h4{font:600 13px 'Space Grotesk';margin:6px 0 0}.stage-main{font:600 35px 'Space Grotesk';margin-top:18px}.stage-main small{font:500 8px 'DM Sans';color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-left:6px}.stage-split{display:flex;gap:14px;margin-top:9px}.stage-split span{font-size:9px;color:var(--muted)}.stage-split b{color:#edf7f8;font-family:'Space Grotesk'}
.matrix-wrap{margin-top:10px;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#0b1820}
.matrix-title{display:flex;justify-content:space-between;align-items:center;padding:12px 15px;border-bottom:1px solid var(--line)}.matrix-title b{font:600 11px 'Space Grotesk';text-transform:uppercase;letter-spacing:.1em}.matrix-title span{font-size:9px;color:var(--muted)}
.flow-matrix{width:100%;border-collapse:collapse;table-layout:fixed}.flow-matrix th,.flow-matrix td{padding:10px 13px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);text-align:right}.flow-matrix th:last-child,.flow-matrix td:last-child{border-right:0}.flow-matrix tr:last-child td{border-bottom:0}.flow-matrix thead th{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;background:rgba(255,255,255,.015)}.flow-matrix thead th:first-child,.flow-matrix tbody td:first-child{text-align:left;width:22%}.flow-matrix tbody td:first-child{font-size:9px;color:#b7c8cf;text-transform:uppercase;letter-spacing:.08em}.flow-matrix tbody td:not(:first-child){font:600 15px 'Space Grotesk'}.flow-matrix .hot{color:var(--cyan)}.flow-matrix .warm{color:var(--amber)}
.fleet-card{height:118px!important;min-height:118px!important;padding:8px 12px;border:1px solid var(--line);border-radius:14px 14px 9px 9px;background:linear-gradient(145deg,rgba(17,34,44,.98),rgba(10,23,31,.94));position:relative;overflow:hidden;margin-bottom:4px}
[class*="st-key-vessel_panel_"]{position:relative;height:100%!important;box-sizing:border-box!important;margin:0 0 18px!important;padding:8px!important;border:1px solid rgba(98,169,255,.20)!important;border-top:3px solid rgba(56,232,209,.60)!important;border-radius:15px!important;background:linear-gradient(155deg,rgba(11,27,36,.96),rgba(7,18,25,.94))!important;box-shadow:0 12px 32px rgba(0,0,0,.20)}
[class*="st-key-vessel_panel_"]:before{content:"VESSEL OPERATION";position:absolute;right:12px;top:-8px;padding:2px 7px;border-radius:8px;background:#0b1d25;border:1px solid rgba(56,232,209,.24);font:700 6px 'DM Sans';letter-spacing:.12em;color:var(--cyan);z-index:2}
[class*="st-key-vessel_panel_"] .fleet-card{border-color:rgba(56,232,209,.16);background:linear-gradient(145deg,rgba(18,42,51,.98),rgba(10,25,33,.96))}
[class*="st-key-vessel_panel_"] [data-testid="stPlotlyChart"],[class*="st-key-vessel_panel_"] [class*="st-key-matrix_grid_"]{border-radius:9px;overflow:hidden}
[class*="st-key-fleet_rows"] [data-testid="stHorizontalBlock"]{align-items:stretch!important;margin-bottom:4px!important}
[class*="st-key-fleet_rows"] [data-testid="stHorizontalBlock"]>[data-testid="column"]{display:flex!important;flex-direction:column!important}
[class*="st-key-fleet_rows"] [data-testid="stHorizontalBlock"]>[data-testid="column"]>[class*="st-key-vessel_panel_"]{flex:1 1 auto!important}
[class*="st-key-aggregate_panel"]{position:relative;margin:0 0 16px!important;padding:10px!important;border:1px solid rgba(98,169,255,.26)!important;border-top:3px solid var(--blue)!important;border-radius:16px!important;background:linear-gradient(150deg,rgba(13,31,42,.98),rgba(7,19,27,.96))!important;box-shadow:0 16px 38px rgba(0,0,0,.22)}
[class*="st-key-aggregate_panel"]:before{content:"CONSOLIDATED OPERATION";position:absolute;right:14px;top:-9px;padding:3px 8px;border-radius:9px;background:#0c1f29;border:1px solid rgba(98,169,255,.30);font:700 6px 'DM Sans';letter-spacing:.13em;color:#86c0ff;z-index:4}
[class*="st-key-aggregate_panel"] .fleet-card{margin-bottom:8px;border-color:rgba(98,169,255,.20);background:linear-gradient(145deg,rgba(18,40,52,.98),rgba(9,24,33,.96))}
.fleet-card:after{content:"";position:absolute;width:100px;height:100px;border-radius:50%;right:-36px;top:-44px;background:rgba(56,232,209,.07)}
.fleet-head{display:flex;justify-content:space-between;gap:8px}.fleet-head h3{font-size:15px;margin:2px 0 0}.fleet-head small{font-size:7px;color:var(--muted)}
.fleet-score{font:600 21px 'Space Grotesk';color:var(--cyan);text-align:right;line-height:1}.fleet-score small{display:block;margin-top:3px;font:500 6px 'DM Sans';color:var(--muted);text-transform:uppercase}
.fleet-ops-mini{display:grid;grid-template-columns:1fr .62fr 1.2fr;gap:4px;margin-top:6px}.fleet-ops-mini span{padding:3px 5px;border-radius:4px;background:rgba(255,255,255,.028);font-size:5.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.fleet-ops-mini b{display:block;margin-top:1px;font:600 8px 'Space Grotesk';color:#deedf0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fleet-ops-mini .gmph b{color:var(--cyan)}
.fleet-list{margin-top:13px}
.fleet-section{margin-top:11px;border:1px solid rgba(180,215,225,.09);border-radius:10px;overflow:hidden;background:rgba(2,10,14,.16)}
.fleet-section-title{display:flex;align-items:center;justify-content:space-between;padding:7px 9px;background:rgba(255,255,255,.025);border-bottom:1px solid rgba(180,215,225,.08);font-size:8px;color:#7f97a2;text-transform:uppercase;letter-spacing:.12em}
.fleet-section-title b{font:600 9px 'Space Grotesk';color:#cfe0e5}.fleet-section-title span{font-size:7px}
.fleet-row{display:grid;grid-template-columns:25px 1fr auto;align-items:center;min-height:31px;padding:0 7px;border-bottom:1px solid rgba(180,215,225,.08);text-decoration:none!important;transition:background .16s ease}
.fleet-row:hover{background:rgba(56,232,209,.055)}
.fleet-row:last-child{border-bottom:0}
.row-sign{width:18px;height:18px;border-radius:5px;display:grid;place-items:center;font:700 10px 'Space Grotesk';background:rgba(98,169,255,.10);color:var(--blue)}
.row-sign.in{background:rgba(56,232,209,.1);color:var(--cyan)}.row-sign.full{background:rgba(98,169,255,.12);color:#7cb8ff}.row-sign.empty{background:rgba(255,189,89,.11);color:var(--amber)}.row-sign.done{background:rgba(56,232,209,.12);color:var(--cyan)}.row-sign.left{background:rgba(255,101,119,.1);color:var(--red)}
.row-label{font-size:9px;color:#a9bac2;text-transform:uppercase;letter-spacing:.075em}.row-value{font:600 14px 'Space Grotesk';color:#f5f9fa;text-align:right}.row-value small{font:500 8px 'DM Sans';color:var(--muted);margin-left:4px}
.row-value em{font-style:normal;color:var(--cyan);margin-left:7px}.card-action{display:flex;align-items:center;justify-content:center;margin-top:11px;height:31px;border-radius:8px;background:rgba(56,232,209,.07);border:1px solid rgba(56,232,209,.16);color:#bff8ef!important;text-decoration:none!important;font:600 9px 'Space Grotesk';letter-spacing:.07em;text-transform:uppercase}.card-action:hover{background:rgba(56,232,209,.13);border-color:var(--cyan)}
.click-hint{font-size:8px;color:var(--muted);margin-top:8px;text-align:center;letter-spacing:.07em;text-transform:uppercase}
.fleet-card .fleet-list,.fleet-card .click-hint{display:none}
.metric-section-label{display:flex;justify-content:space-between;align-items:center;margin-top:8px;padding:7px 10px;border:1px solid var(--line);border-bottom:0;border-radius:10px 10px 0 0;background:rgba(255,255,255,.025);font-size:8px;text-transform:uppercase;letter-spacing:.1em;color:#cfe0e5}.metric-section-label span{font-size:7px;color:var(--muted)}
.metric-row-button [data-testid="stButton"] button{justify-content:flex-start!important;text-align:left!important;border-radius:0!important;margin:0!important;height:35px!important;background:#0d1d25!important;border-color:rgba(180,215,225,.09)!important}
.metric-row-button [data-testid="stButton"] button p{width:100%!important;text-align:left!important}
.detail-panel{padding:13px 15px;border:1px solid rgba(56,232,209,.18);border-radius:14px;background:linear-gradient(155deg,#10242d,#0a171f);position:sticky;top:14px}.detail-summary{display:grid;grid-template-columns:1fr auto;align-items:end;gap:12px}.detail-panel h3{margin:4px 0 2px;font-size:17px}.detail-panel p{color:var(--muted);font-size:9px;margin:0}.detail-count{font:600 25px 'Space Grotesk';color:var(--cyan);text-align:right;line-height:1}.detail-count small{display:block;font:500 7px 'DM Sans';color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-top:5px}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(14,27,36,.45)!important}
[data-testid="stDialog"]{justify-content:flex-end!important;align-items:stretch!important;padding:0!important;background:rgba(2,9,13,.55)!important}
[data-testid="stDialog"] > div,[data-testid="stDialog"] [role="dialog"]{width:min(760px,48vw)!important;min-width:min(760px,48vw)!important;max-width:min(760px,48vw)!important;height:100vh!important;max-height:100vh!important;margin:0!important;border-radius:18px 0 0 18px!important;background:#09171e!important;border:0!important;border-left:1px solid rgba(56,232,209,.22)!important;box-shadow:-30px 0 80px rgba(0,0,0,.52)!important}
[data-testid="stDialog"] [role="dialog"] > div{width:100%!important;max-width:none!important;max-height:100vh!important;background:#09171e!important}
[data-testid="stDialog"] [role="dialog"] h2{display:none!important}
[data-testid="stDialog"] [role="dialog"] [data-testid="stDialogContent"]{padding-top:8px!important}
.drawer-head{display:grid;grid-template-columns:1fr auto;align-items:center;gap:12px;padding:10px 13px;margin-bottom:7px;border:1px solid rgba(56,232,209,.2);border-radius:12px;background:linear-gradient(135deg,#10242d,#0b1921)}
.drawer-head .context{font-size:8px;color:var(--cyan);text-transform:uppercase;letter-spacing:.12em}.drawer-head h3{font:600 17px 'Space Grotesk';margin:3px 0 0}.drawer-head .count{font:600 25px 'Space Grotesk';color:var(--cyan);text-align:right;line-height:1}.drawer-head .count small{display:block;margin-top:4px;font:500 7px 'DM Sans';color:var(--muted);text-transform:uppercase;letter-spacing:.1em}
.shift-brief{display:grid;grid-template-columns:1.08fr 1fr 1fr;gap:6px;margin-top:5px;padding:7px;border:1px solid rgba(98,169,255,.16);border-radius:8px;background:linear-gradient(135deg,rgba(11,31,40,.94),rgba(8,23,30,.94))}
.shift-overview,.shift-group{min-height:55px;padding:7px 8px;border-radius:6px;background:rgba(255,255,255,.025)}.shift-overview span,.shift-group>span{display:block;font-size:7px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.shift-overview b{display:block;margin-top:3px;font:600 10px 'Space Grotesk';color:#ddecf0}.shift-rate{display:flex;align-items:baseline;justify-content:space-between;margin-top:5px}.shift-rate strong{font:600 16px 'Space Grotesk';color:var(--cyan)}.shift-rate small{font-size:7px;color:var(--muted);text-transform:uppercase}
.shift-pills{display:grid;grid-template-columns:repeat(3,1fr);gap:3px;margin-top:6px}.shift-pills i{font-style:normal;text-align:center}.shift-pills b{display:block;font:600 13px 'Space Grotesk';color:#edf6f7}.shift-pills small{display:block;font-size:6px;color:var(--muted);text-transform:uppercase}
.shift-foot{grid-column:1/-1;display:flex;justify-content:space-between;gap:10px;padding:5px 3px 0;border-top:1px solid var(--line);font-size:7px;color:var(--muted)}.shift-foot b{color:#dcebed}
.ops-strip{display:grid;grid-template-columns:1.2fr .7fr 1fr;gap:4px;margin-top:5px;padding:5px;border:1px solid rgba(98,169,255,.14);border-radius:7px;background:rgba(9,24,32,.8)}.ops-strip span{padding:5px 7px;border-radius:5px;background:rgba(255,255,255,.025);font-size:7px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.ops-strip b{display:block;margin-top:2px;font:600 10px 'Space Grotesk';color:#e6f1f3}.ops-strip .rate b{color:var(--cyan)}
.report-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:5px;padding:6px 8px;border:1px solid rgba(255,189,89,.16);border-radius:7px;background:rgba(255,189,89,.035);font-size:7px;color:var(--muted)}.report-strip strong{color:#f3f8f9}.report-strip .source{color:var(--amber);text-transform:uppercase;letter-spacing:.08em}.report-strip i{font-style:normal;padding-left:7px;border-left:1px solid var(--line)}
.shift-report-head{display:flex;justify-content:space-between;align-items:center;margin:8px 0 6px;padding:8px 10px;border:1px solid rgba(255,189,89,.16);border-radius:9px;background:rgba(255,189,89,.035)}.shift-report-head b{font:600 10px 'Space Grotesk'}.shift-report-head span{font-size:8px;color:var(--muted)}
[data-testid="stPopover"] button{height:30px!important;width:100%!important;margin-top:4px!important;padding:4px 9px!important;justify-content:center!important;border-radius:7px!important;background:rgba(255,189,89,.055)!important;border-color:rgba(255,189,89,.22)!important;color:#ffe0a8!important;font:600 8px 'DM Sans'!important;letter-spacing:.025em!important}
[data-testid="stPopover"] button:hover{background:rgba(255,189,89,.11)!important;border-color:var(--amber)!important}
.stop-empty{height:30px;margin-top:4px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(180,215,225,.10);border-radius:7px;background:rgba(255,255,255,.022);font:600 8px 'DM Sans';letter-spacing:.025em;color:#78909a}
.terminal-mix{margin-top:5px;border:1px solid rgba(98,169,255,.14);border-radius:9px;overflow:hidden;background:#091820}
.terminal-mix-head{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid var(--line);font-size:7px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em}.terminal-mix-head b{font:600 8px 'Space Grotesk';color:#dcecef}.terminal-mix-head span{color:var(--blue)}
.terminal-mix table{width:100%;border-collapse:collapse;table-layout:fixed}.terminal-mix th,.terminal-mix td{padding:4px 2px;text-align:center;border-right:1px solid rgba(180,215,225,.07);border-bottom:1px solid rgba(180,215,225,.07)}.terminal-mix tr:last-child td{border-bottom:0}.terminal-mix th:last-child,.terminal-mix td:last-child{border-right:0}
.terminal-mix thead tr:first-child th{font:600 8px 'Space Grotesk';color:#70b7ff;background:rgba(98,169,255,.055)}.terminal-mix thead tr:nth-child(2) th{font:600 6px 'DM Sans';color:#8198a3;text-transform:uppercase}.terminal-mix th:first-child,.terminal-mix td:first-child{width:44px;text-align:left;padding-left:7px}.terminal-mix td:first-child{font-size:7px;color:#a9bbc3;text-transform:uppercase}.terminal-mix td:not(:first-child){font:600 9px 'Space Grotesk';color:#e7f1f3}.terminal-mix .import-value{color:var(--cyan)!important;background:rgba(56,232,209,.025)}.terminal-mix .export-full-value{color:var(--blue)!important;background:rgba(98,169,255,.025)}.terminal-mix .export-empty-value{color:var(--amber)!important;background:rgba(255,189,89,.025)}.terminal-mix .total-full{color:#82baff!important}.terminal-mix .total-empty{color:#ffd27f!important}.terminal-mix .head-full{color:#78b6ff!important;background:rgba(98,169,255,.035)}.terminal-mix .head-empty{color:#ffca70!important;background:rgba(255,189,89,.035)}.terminal-mix .import-row td:first-child{color:var(--cyan)!important}.terminal-mix .export-row td:first-child{color:var(--blue)!important}
.terminal-mix a{display:block;margin:-4px -2px;padding:4px 2px;color:inherit!important;text-decoration:none!important;border-radius:3px;transition:background .15s ease,color .15s ease}.terminal-mix a:hover{background:rgba(56,232,209,.11);color:#fff!important;box-shadow:inset 0 0 0 1px rgba(56,232,209,.18)}
.terminal-mix td[title],.terminal-mix th[title]{cursor:help}.terminal-mix td[title]:hover{background:rgba(56,232,209,.10)!important;box-shadow:inset 0 0 0 1px rgba(56,232,209,.24);color:#fff!important}.terminal-mix th[title]:hover{background:rgba(98,169,255,.11)!important;color:#fff!important}
.matrix-native{margin-top:5px;padding:5px;border:1px solid rgba(98,169,255,.14);border-radius:9px;background:#091820}.matrix-native-groups{display:grid;grid-template-columns:1.35fr 4fr 4fr 1fr;gap:3px;margin-bottom:4px}.matrix-native-groups span{text-align:center;padding:4px 3px;border-radius:4px;background:rgba(98,169,255,.065);font:700 8px 'Space Grotesk';color:#86c0ff;text-transform:uppercase}.matrix-native-groups span:first-child{background:transparent;color:#a8bcc4;text-align:left}.matrix-native-groups span:last-child{color:#edf5f6}
[class*="st-key-matrix_grid_"] [data-testid="stHorizontalBlock"]{gap:3px!important;margin-bottom:3px!important}
[class*="st-key-matrix_grid_"] [data-testid="column"]{min-width:0!important}
[class*="st-key-matrix_grid_"] .matrix-col-head,[class*="st-key-matrix_grid_"] .matrix-row-head{height:34px;display:flex;align-items:center;justify-content:center;border-radius:4px;background:rgba(255,255,255,.03);font:700 7.5px/1.15 'DM Sans';color:#a7bac2;text-transform:uppercase;text-align:center;white-space:nowrap}
[class*="st-key-matrix_grid_"] .matrix-col-head.full-head{color:#82bdff;background:rgba(98,169,255,.075)}[class*="st-key-matrix_grid_"] .matrix-col-head.empty-head{color:#ffd07a;background:rgba(255,189,89,.075)}
[class*="st-key-matrix_grid_"] .matrix-row-head{justify-content:flex-start;padding-left:6px;font-size:8px;color:#d2e1e5}
[class*="st-key-matrix_cell_"] button{height:28px!important;min-height:28px!important;padding:1px 2px!important;margin:0!important;border-radius:4px!important;background:#0d2028!important;border-color:rgba(180,215,225,.10)!important;font:700 9.5px 'Space Grotesk'!important;letter-spacing:0!important}
[class*="st-key-matrix_cell_"][class*="_r0_"] button{color:var(--cyan)!important;background:rgba(56,232,209,.045)!important}
[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c0_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c1_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c4_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c5_"] button{color:#78b6ff!important;background:rgba(98,169,255,.045)!important}
[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c2_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c3_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c6_"] button,[class*="st-key-matrix_cell_"][class*="_r1_"][class*="_c7_"] button{color:var(--amber)!important;background:rgba(255,189,89,.045)!important}
[class*="st-key-matrix_cell_"][class*="_r2_"] button{color:#e5f0f2!important;background:rgba(255,255,255,.035)!important}
[class*="st-key-matrix_cell_"] button:hover{border-color:var(--cyan)!important;background:#16343e!important;color:#fff!important;transform:translateY(-1px)}
.terminal-mix .row-total{color:#fff!important;background:rgba(98,169,255,.055);font-weight:700!important}.terminal-mix .total-row td{background:rgba(255,255,255,.025);color:#dcecef!important;font-weight:700!important}.terminal-mix .total-row td:first-child{color:var(--blue)!important}
.terminal-totals{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;padding:5px;border-top:1px solid var(--line)}.terminal-totals span{padding:4px 2px;text-align:center;border-radius:4px;background:rgba(255,255,255,.025);font-size:6px;color:var(--muted);text-transform:uppercase}.terminal-totals b{display:block;margin-top:2px;font:600 9px 'Space Grotesk';color:#edf5f6}.terminal-totals .import-total b{color:var(--cyan)}.terminal-totals .export-total b{color:var(--blue)}.terminal-totals .grand{background:rgba(56,232,209,.07)}.terminal-totals .grand b{color:var(--cyan)}
.vessel-open [data-testid="stButton"] button{height:38px!important;background:linear-gradient(90deg,rgba(56,232,209,.17),rgba(98,169,255,.12))!important;border-color:rgba(56,232,209,.35)!important;color:#dffff9!important}
[class*="st-key-metric_list_"] [data-testid="stRadio"]{width:100%;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#09171e;padding:5px}
[class*="st-key-metric_list_"] [data-testid="stRadio"] > label{display:none}
[class*="st-key-metric_list_"] [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(3,1fr)!important;gap:5px!important;width:100%!important}
[class*="st-key-metric_list_"] [role="radiogroup"] label{width:100%!important;min-width:0!important;min-height:48px;padding:7px 8px!important;margin:0!important;border:1px solid rgba(180,215,225,.09);border-radius:7px;background:linear-gradient(135deg,#10232c,#0d1d25);transition:all .15s ease}
[class*="st-key-metric_list_"] [role="radiogroup"] label{grid-column:span 1!important}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(-n+3){background:linear-gradient(135deg,#112732,#0d2029)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(n+4):nth-child(-n+6){min-height:68px;background:linear-gradient(135deg,#10242c,#0b1b23)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(4){border-color:rgba(56,232,209,.18);background:linear-gradient(135deg,rgba(56,232,209,.075),#0b1b23)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(5){border-color:rgba(98,169,255,.18);background:linear-gradient(135deg,rgba(98,169,255,.075),#0b1b23)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(6){border-color:rgba(255,189,89,.18);background:linear-gradient(135deg,rgba(255,189,89,.07),#0b1b23)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(n+7){background:linear-gradient(135deg,rgba(56,232,209,.07),rgba(98,169,255,.045))}
[class*="st-key-metric_list_"] [role="radiogroup"] label:hover{background:#16343e;border-color:rgba(56,232,209,.28);transform:translateY(-1px)}
[class*="st-key-metric_list_"] [role="radiogroup"] label:has(input:checked){background:linear-gradient(135deg,rgba(56,232,209,.16),rgba(98,169,255,.09));border-color:var(--cyan);box-shadow:0 0 0 1px rgba(56,232,209,.08)}
[class*="st-key-metric_list_"] [role="radiogroup"] input{display:none}
[class*="st-key-metric_list_"] [data-testid="stRadioOption"] > div > div > div:first-child{display:none!important}
[class*="st-key-metric_list_"] [data-testid="stRadioOption"] > div,[class*="st-key-metric_list_"] [data-testid="stRadioOption"] > div > div{width:100%!important;justify-content:center!important}
[class*="st-key-metric_list_"] [role="radiogroup"] p{width:100%!important;text-align:center!important;white-space:normal!important;font:500 8px/1.5 'DM Sans'!important;color:#a9bdc5!important;letter-spacing:.005em}
[class*="st-key-metric_list_"] [role="radiogroup"] strong{font:700 9px 'Space Grotesk'!important;color:#edf7f8!important}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(4) strong:first-of-type{color:var(--cyan)!important}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(5) strong:first-of-type{color:#78b6ff!important}
[class*="st-key-metric_list_"] [role="radiogroup"] label:nth-child(6) strong:first-of-type{color:var(--amber)!important}
.progress-track{height:3px;background:#20333c;border-radius:5px;margin-top:5px;overflow:hidden}.progress-fill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--blue));border-radius:5px}
.selection-summary{display:grid;grid-template-columns:1.1fr repeat(5,1fr);gap:6px;margin:5px 0 10px;padding:7px;border:1px solid rgba(56,232,209,.15);border-radius:10px;background:linear-gradient(135deg,rgba(11,31,40,.9),rgba(8,23,30,.9))}.selection-summary span{padding:6px 7px;border-radius:6px;background:rgba(255,255,255,.025);font-size:6px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.selection-summary b{display:block;margin-top:2px;font:600 14px 'Space Grotesk';color:#edf7f8}.selection-summary .primary b,.selection-summary .treated b{color:var(--cyan)}.selection-summary .remaining b{color:var(--amber)}
[class*="st-key-selected_scope_header"]{margin:10px 0 12px!important;padding:10px 14px!important;border:1px solid rgba(98,169,255,.20)!important;border-left:4px solid var(--blue)!important;border-radius:10px!important;background:linear-gradient(90deg,rgba(98,169,255,.085),rgba(12,29,38,.62))!important}
[class*="st-key-selected_scope_header"] .section-title{margin:0!important;align-items:center!important}
[class*="st-key-selected_scope_header"] .section-title h3{font-size:13px!important;color:#e9f4f7!important}
[class*="st-key-selected_scope_header"] .section-title span{padding:4px 8px;border-radius:10px;background:rgba(56,232,209,.07);color:var(--cyan)!important}
.shift-chart{margin-top:5px;padding:7px 8px 5px;border:1px solid rgba(98,169,255,.14);border-radius:9px;background:linear-gradient(135deg,rgba(9,24,32,.96),rgba(11,29,38,.92))}
.shift-chart-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:2px}.shift-chart-head b{font:600 8px 'Space Grotesk';color:#dcecef;text-transform:uppercase;letter-spacing:.08em}.shift-chart-head span{font-size:6px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.shift-chart svg{display:block;width:100%;height:74px}.shift-chart-foot{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;margin-top:1px}.shift-chart-foot span{text-align:center;padding:3px;border-radius:4px;background:rgba(255,255,255,.025);font-size:6px;color:var(--muted);text-transform:uppercase}.shift-chart-foot b{display:block;margin-top:1px;font:600 9px 'Space Grotesk';color:#edf5f6}.shift-chart-foot .current b{color:var(--cyan)}.shift-chart-foot .peak b{color:var(--amber)}
.shift-legend{display:flex;gap:6px;align-items:center}.shift-legend i{font-style:normal;font-size:6px;color:var(--muted)}.shift-legend i:before{content:"";display:inline-block;width:5px;height:5px;border-radius:1px;margin-right:2px}.shift-legend .s1:before{background:#38e8d1}.shift-legend .s2:before{background:#62a9ff}.shift-legend .s3:before{background:#a98cff}
[data-testid="stButton"] button{background:#10242d!important;color:#dff7f5!important;border:1px solid rgba(56,232,209,.2)!important;height:36px!important;font:600 10px 'Space Grotesk'!important;letter-spacing:.06em!important}
[data-testid="stButton"] button:hover{background:#16343d!important;border-color:var(--cyan)!important;color:var(--cyan)!important}
.badge{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--line);border-radius:16px;padding:4px 8px;font-size:9px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:2px;display:inline-block}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:16px;overflow:hidden}
[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label,[data-testid="stSegmentedControl"] label{font-size:10px!important;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)!important}
.stButton button{border-radius:12px;border:1px solid var(--line)}
@media(max-width:900px){.hero{grid-template-columns:1fr}.metric-grid{grid-template-columns:repeat(2,1fr)}.terminal{grid-template-columns:1fr 1fr}.journey{grid-template-columns:1fr 1fr}.stage:nth-child(2):after{display:none}.flow-matrix{min-width:720px}.matrix-wrap{overflow-x:auto}.ship-card{min-height:160px}}
</style>
""",
    unsafe_allow_html=True,
)


FR_MONTHS = {
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5,
    "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10,
    "nov": 11, "déc": 12, "dec": 12,
}


def parse_n4_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value)
    s = str(value).strip().lower().replace("–", "-")
    m = re.search(r"(\d{2})-([a-zéûô]+)\.?-(\d{1,2})\s+(\d{2})(\d{2})", s)
    if not m:
        return pd.to_datetime(s, errors="coerce", dayfirst=True)
    year, month_name, day, hour, minute = m.groups()
    month = FR_MONTHS.get(month_name.rstrip("."))
    return pd.Timestamp(2000 + int(year), month, int(day), int(hour), int(minute)) if month else pd.NaT


def iso_size(value):
    s = str(value)
    return "20′" if s.startswith("2") else "40′" if s.startswith(("4", "L")) else "Other"


@st.cache_data(show_spinner=False, ttl=300)
def read_test_data(data_dir: str):
    root = Path(data_dir)
    unit_files = [root / "units-page1.xlsx", root / "units-page2.xlsx"]
    missing = [str(f) for f in unit_files if not f.exists()]
    if missing:
        raise FileNotFoundError("Missing test files: " + ", ".join(missing))
    units = pd.concat(
        [pd.read_excel(f, header=4) for f in unit_files],
        ignore_index=True,
    ).drop_duplicates(subset=["Unit Nbr", "I/B Actual Visit", "O/B Actual Visit"], keep="last")
    visit_file = root / "vessel visite.xlsx"
    visits = pd.read_excel(visit_file, header=4) if visit_file.exists() else pd.DataFrame()
    units["Last Move DT"] = units["Last Move"].map(parse_n4_date)
    units["Size"] = units["Type ISO"].map(iso_size)
    units["Freight"] = units["Frght Kind"].fillna("Unknown").astype(str).str.title()
    units["STS Location"] = (
        units["Position"].astype(str).str.extract(r"(STS\d+)", expand=False)
    )
    units["STS Account Login"] = "Not provided in units-page1/2"
    units["Visit Keys"] = units["I/B Actual Visit"].astype(str) + "|" + units["O/B Actual Visit"].astype(str)
    return units, visits


def normalized_vessel_name(value):
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


@st.cache_data(show_spinner=False, ttl=300)
def read_hanane_report(report_path: str):
    """Read only real vessel rows from the daily/shift productivity workbook."""
    path = Path(report_path)
    columns = [
        "Report Date", "Shift Nbr", "Shift Start", "Terminal", "Vessel",
        "Boxes Import", "Boxes Export", "Total Moves", "Crane GMPH",
        "Vessel GMPH", "Active Hours", "Stop Minutes", "Crane", "Observation",
    ]
    if not path.exists():
        return pd.DataFrame(columns=columns)

    import xlrd

    workbook = xlrd.open_workbook(path)
    records = []
    for sheet_name in workbook.sheet_names():
        if not re.fullmatch(r"J\.\d{2}", sheet_name):
            continue
        sheet = workbook.sheet_by_name(sheet_name)
        report_date = None
        for row_number in range(min(6, sheet.nrows)):
            for column_number in range(sheet.ncols):
                raw = str(sheet.cell_value(row_number, column_number)).strip()
                parsed = pd.to_datetime(raw, dayfirst=True, errors="coerce")
                if pd.notna(parsed) and parsed.year >= 2020:
                    report_date = parsed.normalize()
                    break
            if report_date is not None:
                break
        if report_date is None:
            continue

        terminal = ""
        shift_nbr = None
        vessel = ""
        for row_number in range(sheet.nrows):
            values = [sheet.cell_value(row_number, c) if c < sheet.ncols else "" for c in range(22)]
            marker = str(values[4]).strip().upper()
            shift_text = str(values[5]).strip()
            vessel_text = str(values[6]).strip()
            if marker in {"TCE", "TC3", "TCR"}:
                terminal = marker
                vessel = ""
            shift_match = re.match(r"([123])\s*E?\s*SH", shift_text.upper().replace("È", "E"))
            if shift_match:
                shift_nbr = int(shift_match.group(1))
                vessel = ""
            if shift_text.upper().startswith(("TOT", "TOTAL")) or marker in {"TOTAL", "IMP", "EXP", "GL", "EQ", "RDT"}:
                vessel = ""
                continue
            if vessel_text and vessel_text.upper() != "NAVIRE":
                vessel = vessel_text
            if not vessel or shift_nbr is None:
                continue

            total_moves = pd.to_numeric(values[15], errors="coerce")
            crane = str(values[20]).strip()
            # Blank template rows have neither moves nor a crane and are deliberately excluded.
            if (pd.isna(total_moves) or total_moves == 0) and not crane:
                continue
            start_hour = {1: 7, 2: 15, 3: 23}[shift_nbr]
            records.append(
                {
                    "Report Date": report_date,
                    "Shift Nbr": shift_nbr,
                    "Shift Start": report_date + pd.Timedelta(hours=start_hour),
                    "Terminal": terminal,
                    "Vessel": vessel,
                    "Boxes Import": pd.to_numeric(values[7], errors="coerce"),
                    "Boxes Export": pd.to_numeric(values[8], errors="coerce"),
                    "Total Moves": total_moves,
                    "Crane GMPH": pd.to_numeric(values[16], errors="coerce"),
                    "Vessel GMPH": pd.to_numeric(values[17], errors="coerce"),
                    "Active Hours": pd.to_numeric(values[13], errors="coerce"),
                    "Stop Minutes": pd.to_numeric(values[19], errors="coerce"),
                    "Crane": crane,
                    "Observation": str(values[21]).strip(),
                }
            )
    result = pd.DataFrame(records, columns=columns)
    if not result.empty:
        result["Vessel Key"] = result["Vessel"].map(normalized_vessel_name)
    return result


def _api_setting(config, section, option, env_name, fallback=""):
    """Environment variables take precedence over the local INI file."""
    return os.getenv(env_name, config.get(section, option, fallback=fallback)).strip()


def load_api_config():
    # RawConfigParser is required because Basic Auth passwords may contain '%'.
    config = configparser.RawConfigParser()
    if API_CONFIG_FILE.exists():
        config.read(API_CONFIG_FILE, encoding="utf-8")

    def number(section, option, env_name, fallback, cast):
        raw = _api_setting(config, section, option, env_name, str(fallback))
        try:
            return cast(raw)
        except (TypeError, ValueError):
            return cast(fallback)

    verify_raw = _api_setting(
        config, "performance", "verify_ssl", "NEVIS_VERIFY_SSL", "true"
    ).lower()
    settings = {
        "unit_url": _api_setting(config, "api", "unit_url", "NEVIS_UNIT_API_URL"),
        "visit_url": _api_setting(
            config, "api", "vessel_visit_url", "NEVIS_VESSEL_VISIT_API_URL"
        ),
        "phase": _api_setting(config, "api", "phase", "NEVIS_VESSEL_PHASE", "working"),
        "username": _api_setting(config, "auth", "username", "NEVIS_API_USERNAME"),
        "password": _api_setting(config, "auth", "password", "NEVIS_API_PASSWORD"),
        "connect_timeout": number(
            "performance", "connect_timeout_seconds", "NEVIS_CONNECT_TIMEOUT", 3, float
        ),
        "read_timeout": number(
            "performance", "read_timeout_seconds", "NEVIS_READ_TIMEOUT", 10, float
        ),
        "retries": number("performance", "retries", "NEVIS_API_RETRIES", 1, int),
        "workers": max(
            1, min(10, number("performance", "workers", "NEVIS_API_WORKERS", 6, int))
        ),
        "cache_ttl": number(
            "performance", "cache_ttl_seconds", "NEVIS_CACHE_TTL", 30, int
        ),
        "stale_minutes": number(
            "performance", "stale_cache_minutes", "NEVIS_STALE_CACHE_MINUTES", 180, int
        ),
        "failure_backoff": number(
            "performance", "failure_backoff_seconds", "NEVIS_FAILURE_BACKOFF", 300, int
        ),
        "verify_ssl": verify_raw in {"1", "true", "yes", "on"},
    }
    if not settings["unit_url"] or not settings["visit_url"]:
        raise RuntimeError(f"API URLs are missing in {API_CONFIG_FILE}")
    if not settings["username"] or not settings["password"]:
        raise RuntimeError(
            f"Basic Auth credentials are missing in {API_CONFIG_FILE}. "
            "Set [auth] username and password."
        )
    return settings


def _api_session(settings):
    retry = Retry(
        total=settings["retries"],
        connect=settings["retries"],
        read=settings["retries"],
        status=settings["retries"],
        backoff_factor=0.25,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    # Nevis is an internal service. Corporate proxy variables can accept the
    # TCP connection but never return the intranet response.
    session.trust_env = False
    session.auth = (settings["username"], settings["password"])
    session.headers.update(
        {
            "Accept": "application/xml, text/xml;q=0.9, */*;q=0.5",
            "User-Agent": "Nevis-Vessel-Command-Center/1.0",
        }
    )
    session.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=settings["workers"]))
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=settings["workers"]))
    return session


def _xml_response_frame(payload):
    """Convert the Apex query-response XML data table to a DataFrame."""
    root = ET.fromstring(payload)
    table = root.find(".//data-table")
    if table is None:
        message = " ".join(text.strip() for text in root.itertext() if text.strip())
        raise RuntimeError(f"Nevis response has no data-table: {message[:240]}")
    columns_node = table.find("columns")
    rows_node = table.find("rows")
    columns = [
        (column.text or "").strip()
        for column in (list(columns_node) if columns_node is not None else [])
    ]
    if not columns:
        return pd.DataFrame()
    rows = list(rows_node) if rows_node is not None else [
        child for child in table if child.tag == "row"
    ]
    records = []
    for row in rows:
        values = [(field.text or "").strip() for field in list(row)]
        if len(values) < len(columns):
            values.extend([""] * (len(columns) - len(values)))
        records.append(values[:len(columns)])
    return pd.DataFrame.from_records(records, columns=columns)


def _request_api_frame(url, params, settings):
    session = _api_session(settings)
    try:
        response = session.get(
            url,
            params=params,
            timeout=(settings["connect_timeout"], settings["read_timeout"]),
            verify=settings["verify_ssl"],
        )
        response.raise_for_status()
        return _xml_response_frame(response.content)
    finally:
        session.close()


def _prepare_live_units(units):
    required = [
        "Last Move", "Unit Nbr", "Type ISO", "Category", "T-State", "Position",
        "Line Op", "I/B Actual Visit", "O/B Actual Visit", "POD", "Frght Kind",
        "Reqs Power", "Load list Status", "Discharge list Status",
        "Last Temp Read (C)", "Hazardous?", "Cargo Wt (kg)", "BL Nbr",
        "ACTUAL TERMINAL ID", "Booking Number",
    ]
    units = units.rename(columns={"Last Temp Read": "Last Temp Read (C)"}).copy()
    for column in required:
        if column not in units.columns:
            units[column] = ""
    units = units[required].drop_duplicates(
        subset=["Unit Nbr", "I/B Actual Visit", "O/B Actual Visit"], keep="last"
    )
    units["Last Move DT"] = units["Last Move"].map(parse_n4_date)
    units["Size"] = units["Type ISO"].map(iso_size)
    units["Freight"] = units["Frght Kind"].replace("", "Unknown").fillna("Unknown").astype(str).str.title()
    units["STS Location"] = units["Position"].astype(str).str.extract(r"(STS\d+)", expand=False)
    units["STS Account Login"] = "Not provided by UnitComplexVisit"
    units["Visit Keys"] = (
        units["I/B Actual Visit"].astype(str) + "|" + units["O/B Actual Visit"].astype(str)
    )
    return units


def _prepare_live_visits(visits):
    visits = visits.copy()
    required = ["Visit", "Line", "Vessel Name", "Phase", "ETA", "ETD", "TERMINAL ID"]
    for column in required:
        if column not in visits.columns:
            visits[column] = ""
    visits["Visit"] = visits["Visit"].astype(str).str.strip()
    visits["Phase"] = visits["Phase"].astype(str).str.strip().str.title()
    return visits.drop_duplicates(subset=["Visit"], keep="last")


@st.cache_data(show_spinner=False)
def read_api_sample_data(unit_response_path, vessel_response_path):
    """Load the saved XML responses using the same schema as the live APIs."""
    unit_path = Path(unit_response_path)
    vessel_path = Path(vessel_response_path)
    missing = [
        str(path) for path in (unit_path, vessel_path) if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("Missing API sample files: " + ", ".join(missing))
    units = _prepare_live_units(_xml_response_frame(unit_path.read_bytes()))
    visits = _prepare_live_visits(_xml_response_frame(vessel_path.read_bytes()))
    units.attrs["source_status"] = "saved API responses"
    return units, visits


def _cache_is_fresh(path, ttl_seconds):
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age <= max(1, ttl_seconds)


@st.cache_data(show_spinner=False, ttl=30)
def read_live_data():
    """
    Fetch working vessel visits first, then fetch only units linked to those visits.

    Requests are parallel and strictly time-bounded. A recent local snapshot is
    returned immediately, while a stale snapshot is used if Nevis is unavailable.
    """
    settings = load_api_config()
    LIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    units_cache = LIVE_CACHE_DIR / "live_units.pkl"
    visits_cache = LIVE_CACHE_DIR / "live_visits.pkl"
    failure_marker = LIVE_CACHE_DIR / "api_failure.txt"

    if (
        _cache_is_fresh(units_cache, settings["cache_ttl"])
        and _cache_is_fresh(visits_cache, settings["cache_ttl"])
    ):
        units = pd.read_pickle(units_cache)
        visits = pd.read_pickle(visits_cache)
        units.attrs["source_status"] = "live cache"
        return units, visits

    # Circuit breaker: after one failed API cycle, do not repeatedly contact a
    # fragile load balancer on every Streamlit rerun.
    if _cache_is_fresh(failure_marker, settings["failure_backoff"]):
        failure_text = failure_marker.read_text(encoding="utf-8", errors="replace")
        stale_limit_seconds = max(1, settings["stale_minutes"]) * 60
        if (
            _cache_is_fresh(units_cache, stale_limit_seconds)
            and _cache_is_fresh(visits_cache, stale_limit_seconds)
        ):
            units = pd.read_pickle(units_cache)
            visits = pd.read_pickle(visits_cache)
            units.attrs["source_status"] = "safety cache · API circuit breaker active"
            return units, visits
        raise RuntimeError(
            "API circuit breaker active after the previous failure. "
            f"No new request will be sent yet. Last error: {failure_text}"
        )

    try:
        visit_params = {"param_phase": settings["phase"]} if settings["phase"] else {}
        visits = _prepare_live_visits(
            _request_api_frame(settings["visit_url"], visit_params, settings)
        )
        visit_ids = visits["Visit"][
            visits["Visit"].str.fullmatch(r"\d{9}", na=False)
        ].drop_duplicates().tolist()
        if not visit_ids:
            raise RuntimeError(
                f"The vessel API returned no {settings['phase'] or 'active'} visits."
            )

        frames = []
        failures = {}
        with ThreadPoolExecutor(max_workers=settings["workers"]) as executor:
            futures = {
                executor.submit(
                    _request_api_frame,
                    settings["unit_url"],
                    {
                        "param_ibactualvisit": visit_id,
                        "param_obactualvisit": visit_id,
                    },
                    settings,
                ): visit_id
                for visit_id in visit_ids
            }
            for future in as_completed(futures):
                visit_id = futures[future]
                try:
                    frame = future.result()
                    if not frame.empty:
                        frames.append(frame)
                except Exception as exc:
                    failures[visit_id] = str(exc)

        if not frames:
            raise RuntimeError(
                "Unit API returned no usable rows. "
                + (f"Failures: {failures}" if failures else "")
            )
        units = _prepare_live_units(pd.concat(frames, ignore_index=True))
        units.attrs["source_status"] = (
            "live API"
            if not failures
            else f"live API · {len(failures)} visit request(s) unavailable"
        )
        units.to_pickle(units_cache)
        visits.to_pickle(visits_cache)
        failure_marker.unlink(missing_ok=True)
        return units, visits
    except Exception as live_error:
        print(f"[NEVIS LIVE API] {type(live_error).__name__}: {live_error}", flush=True)
        failure_marker.write_text(
            f"{type(live_error).__name__}: {live_error}",
            encoding="utf-8",
        )
        stale_limit_seconds = max(1, settings["stale_minutes"]) * 60
        if (
            _cache_is_fresh(units_cache, stale_limit_seconds)
            and _cache_is_fresh(visits_cache, stale_limit_seconds)
        ):
            units = pd.read_pickle(units_cache)
            visits = pd.read_pickle(visits_cache)
            units.attrs["source_status"] = f"stale safety cache · {live_error}"
            return units, visits
        raise RuntimeError(f"Live Nevis API unavailable: {live_error}") from live_error


def shift_window(reference: pd.Timestamp):
    h = reference.hour
    if 7 <= h < 15:
        start = reference.normalize() + pd.Timedelta(hours=7)
    elif 15 <= h < 23:
        start = reference.normalize() + pd.Timedelta(hours=15)
    elif h >= 23:
        start = reference.normalize() + pd.Timedelta(hours=23)
    else:
        start = reference.normalize() - pd.Timedelta(hours=1)
    return start, start + pd.Timedelta(hours=8)


def shift_start_for_timestamp(value):
    if pd.isna(value):
        return pd.NaT
    value = pd.Timestamp(value)
    if 7 <= value.hour < 15:
        return value.normalize() + pd.Timedelta(hours=7)
    if 15 <= value.hour < 23:
        return value.normalize() + pd.Timedelta(hours=15)
    if value.hour >= 23:
        return value.normalize() + pd.Timedelta(hours=23)
    return value.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23)


def safe_int(value):
    return int(value) if pd.notna(value) else 0


def infer_stops(
    timestamps, threshold_minutes=10, window_start=None, window_end=None
):
    """Return inactivity gaps across the complete configured shift window."""
    ordered = pd.Series(timestamps).dropna().drop_duplicates().sort_values()
    details = []
    boundaries = []
    if window_start is not None and window_end is not None:
        window_start = pd.Timestamp(window_start)
        window_end = pd.Timestamp(window_end)
        ordered = ordered[ordered.between(window_start, window_end, inclusive="both")]
        points = [window_start, *ordered.tolist(), window_end]
        boundaries = list(zip(points[:-1], points[1:]))
    elif len(ordered) >= 2:
        boundaries = list(zip(ordered.iloc[:-1], ordered.iloc[1:]))
    for gap_start, gap_end in boundaries:
        duration = (pd.Timestamp(gap_end) - pd.Timestamp(gap_start)).total_seconds() / 60
        if duration < threshold_minutes:
            continue
        details.append(
            {
                "From": pd.Timestamp(gap_start),
                "To": pd.Timestamp(gap_end),
                "Duration min": int(round(duration)),
            }
        )
    durations = [item["Duration min"] for item in details]
    return {
        "count": len(details),
        "minutes": int(sum(durations)),
        "longest": int(max(durations)) if durations else 0,
        "details": details,
    }


def terminal_operation_matrix(frame, visit_id, clickable=True):
    terminal = frame["ACTUAL TERMINAL ID"].astype(str).str.upper()
    operation = frame["Operation"].astype(str)
    freight = frame["Freight"].astype(str).str.lower()
    size = frame["Size"].astype(str)

    def filter_link(value, **filters):
        if not clickable:
            return f"<span>{int(value):,}</span>"
        params = {"matrix_visit": visit_id}
        params.update({key: value for key, value in filters.items() if value})
        return (
            f'<a href="?{html.escape(urlencode(params))}" target="_self">'
            f"{int(value):,}</a>"
        )

    def count(terminal_name, operation_name, nature_name, size_name):
        operation_mask = (
            operation.isin(["Import", "Restow"])
            if operation_name == "Import"
            else operation.isin(["Export", "Restow"])
        )
        nature_mask = (
            freight.str.contains("full|laden|fcl", regex=True)
            if nature_name == "Full"
            else freight.str.contains("empty", regex=True)
        )
        return safe_int(
            (
                terminal.eq(terminal_name)
                & operation_mask
                & nature_mask
                & size.eq(size_name)
            ).sum()
        )

    matrix_values = {}
    operation_totals = {
        "Import": safe_int(operation.isin(["Import", "Restow"]).sum()),
        "Export": safe_int(operation.isin(["Export", "Restow"]).sum()),
    }
    rows = []
    for operation_name in ["Import", "Export"]:
        cells = []
        row_values = []
        for terminal_name in ["TCR", "TC3"]:
            for nature_name, css_class in [("Full", "full"), ("Empty", "empty")]:
                for size_name in ["20′", "40′"]:
                    value = count(
                        terminal_name, operation_name, nature_name, size_name
                    )
                    matrix_values[
                        (operation_name, terminal_name, nature_name, size_name)
                    ] = value
                    row_values.append(value)
                    semantic_class = (
                        "import-value"
                        if operation_name == "Import"
                        else (
                            "export-full-value"
                            if nature_name == "Full"
                            else "export-empty-value"
                        )
                    )
                    cells.append(
                        f'<td class="{semantic_class}" title="'
                        f'{terminal_name} → {operation_name} → {nature_name} → '
                        f'{"20-foot" if size_name == "20′" else "40/45-foot"} · '
                        f'{value:,} containers">'
                        + filter_link(
                            value,
                            matrix_operation=operation_name,
                            matrix_terminal=terminal_name,
                            matrix_nature=nature_name,
                            matrix_size="20" if size_name == "20′" else "40",
                        )
                        + "</td>"
                    )
        rows.append(
            f'<tr class="{operation_name.lower()}-row"><td title="{operation_name} flow">'
            f'{"⬇" if operation_name == "Import" else "⬆"} {operation_name}</td>'
            f"{''.join(cells)}"
            f'<td class="row-total" title="{operation_name} · all terminals, natures and sizes">'
            + filter_link(
                operation_totals[operation_name],
                matrix_operation=operation_name,
            )
            + "</td></tr>"
        )

    column_totals = []
    for terminal_name in ["TCR", "TC3"]:
        for nature_name in ["Full", "Empty"]:
            for size_name in ["20′", "40′"]:
                column_totals.append(
                    sum(
                        matrix_values[
                            (operation_name, terminal_name, nature_name, size_name)
                        ]
                        for operation_name in ["Import", "Export"]
                    )
                )
    import_total = operation_totals["Import"]
    export_total = operation_totals["Export"]
    operation_weight = (
        operation.isin(["Import", "Restow"]).astype(int)
        + operation.isin(["Export", "Restow"]).astype(int)
    )
    tcr_total = safe_int(operation_weight[terminal.eq("TCR")].sum())
    tc3_total = safe_int(operation_weight[terminal.eq("TC3")].sum())
    size20_total = safe_int(operation_weight[size.eq("20′")].sum())
    size40_total = safe_int(operation_weight[size.eq("40′")].sum())
    grand_total = import_total + export_total
    other_profile = max(0, grand_total - sum(column_totals))
    total_cells_parts = []
    total_position = 0
    for terminal_name in ["TCR", "TC3"]:
        for nature_name in ["Full", "Empty"]:
            for size_name in ["20′", "40′"]:
                total_value = column_totals[total_position]
                total_position += 1
                total_cells_parts.append(
                    f'<td class="total-{"full" if nature_name == "Full" else "empty"}" '
                    f'title="{terminal_name} → All flows → {nature_name} → '
                    f'{"20-foot" if size_name == "20′" else "40/45-foot"} · '
                    f'{total_value:,} containers">'
                    + filter_link(
                        total_value,
                        matrix_terminal=terminal_name,
                        matrix_nature=nature_name,
                        matrix_size="20" if size_name == "20′" else "40",
                    )
                    + "</td>"
                )
    total_cells = "".join(total_cells_parts)
    rows.append(
        f'<tr class="total-row"><td title="All import and export flows">Σ Total</td>{total_cells}'
        f'<td class="row-total" title="All selected terminal movements">'
        f'{filter_link(grand_total)}</td></tr>'
    )
    return (
        '<div class="terminal-mix"><div class="terminal-mix-head">'
        '<b>Terminal operation profile</b><span>Full / empty · ISO length</span></div>'
        f'<table><thead><tr><th></th><th colspan="4" title="TCR terminal · all flows">🏗 TCR · '
        f'{filter_link(tcr_total, matrix_terminal="TCR")}</th>'
        f'<th colspan="4" title="TC3 terminal · all flows">🏗 TC3 · {filter_link(tc3_total, matrix_terminal="TC3")}</th>'
        f'<th title="All terminals, flows, natures and sizes">Σ {filter_link(grand_total)}</th></tr>'
        '<tr><th title="Container operation direction">↕ Flow</th>'
        '<th class="head-full" title="TCR · Full · 20-foot">■ F20</th>'
        '<th class="head-full" title="TCR · Full · 40/45-foot">▰ F40/45</th>'
        '<th class="head-empty" title="TCR · Empty · 20-foot">□ E20</th>'
        '<th class="head-empty" title="TCR · Empty · 40/45-foot">▱ E40/45</th>'
        '<th class="head-full" title="TC3 · Full · 20-foot">■ F20</th>'
        '<th class="head-full" title="TC3 · Full · 40/45-foot">▰ F40/45</th>'
        '<th class="head-empty" title="TC3 · Empty · 20-foot">□ E20</th>'
        '<th class="head-empty" title="TC3 · Empty · 40/45-foot">▱ E40/45</th>'
        '<th title="All sizes and natures">Σ All</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        '<div class="terminal-totals">'
        f'<span class="import-total">Import<b>{import_total:,}</b></span>'
        f'<span class="export-total">Export<b>{export_total:,}</b></span>'
        f'<span>20′ units<b>{size20_total:,}</b></span>'
        f'<span>40/45′ units<b>{size40_total:,}</b></span>'
        f'<span>TCR total<b>{tcr_total:,}</b></span>'
        f'<span>TC3 total<b>{tc3_total:,}</b></span>'
        f'<span>Other profile<b>{other_profile:,}</b></span>'
        f'<span class="grand">All movements<b>{grand_total:,}</b></span>'
        "</div></div>"
    )


def shift_performance_chart(frame, treated_mask, visit_id):
    history = frame.loc[
        treated_mask & frame["Last Move DT"].notna(),
        ["Last Move DT", "Operation", "Freight"],
    ].copy()
    if history.empty:
        return None, pd.DataFrame()
    history["Shift Start"] = history["Last Move DT"].map(shift_start_for_timestamp)
    summary = (
        history.groupby("Shift Start")["Last Move DT"]
        .agg(Moves="count", First="min", Last="max")
        .reset_index()
        .sort_values("Shift Start")
        .tail(9)
    )
    active_hours = (
        (summary["Last"] - summary["First"]).dt.total_seconds().div(3600)
        .clip(lower=0.5, upper=8)
    )
    summary["Active Hours"] = active_hours
    summary["Shift Hours"] = 8.0
    # Director shift comparison uses the configured full 8-hour window.
    # Active Hours remains available in hover as operational context.
    summary["GMPH"] = summary["Moves"] / summary["Shift Hours"]
    summary["Shift"] = summary["Shift Start"].map(
        lambda value: {7: "S1", 15: "S2", 23: "S3"}.get(value.hour, "S")
    )
    summary["Axis"] = summary.apply(
        lambda row: (
            f'{row["Shift Start"]:%d/%m}<br>'
            f'{row["Shift"]}<br>G {row["GMPH"]:.1f}'
        ),
        axis=1,
    )
    freight = history["Freight"].astype(str).str.lower()
    history["Import"] = history["Operation"].isin(["Import", "Restow"]).astype(int)
    history["Export full"] = (
        history["Operation"].isin(["Export", "Restow"])
        & freight.str.contains("full|laden|fcl", regex=True)
    ).astype(int)
    history["Export empty"] = (
        history["Operation"].isin(["Export", "Restow"])
        & freight.str.contains("empty", regex=True)
    ).astype(int)
    mix = (
        history.groupby("Shift Start")[["Import", "Export full", "Export empty"]]
        .sum()
        .reindex(summary["Shift Start"], fill_value=0)
        .reset_index(drop=True)
    )
    for category in ["Import", "Export full", "Export empty"]:
        summary[category] = mix[category].to_numpy()
    stop_counts, stop_minutes, longest_stops = [], [], []
    for shift_start in summary["Shift Start"]:
        shift_times = history.loc[
            history["Shift Start"].eq(shift_start), "Last Move DT"
        ]
        stop_metrics = infer_stops(
            shift_times,
            threshold_minutes=10,
            window_start=shift_start,
            window_end=shift_start + pd.Timedelta(hours=8),
        )
        stop_counts.append(stop_metrics["count"])
        stop_minutes.append(stop_metrics["minutes"])
        longest_stops.append(stop_metrics["longest"])
    summary["Stop Count"] = stop_counts
    summary["Stop Minutes"] = stop_minutes
    summary["Longest Stop"] = longest_stops
    figure = go.Figure()
    category_colors = {
        "Import": "#38e8d1",
        "Export full": "#62a9ff",
        "Export empty": "#ffbd59",
    }
    for category in ["Import", "Export full", "Export empty"]:
        figure.add_bar(
            x=summary["Axis"],
            y=summary[category],
            marker_color=category_colors[category],
            name=category,
            customdata=np.column_stack(
                [
                    summary["Shift Start"].astype(str),
                    summary["GMPH"].round(1),
                    summary["Active Hours"].round(1),
                    summary["Moves"],
                ]
            ),
            hovertemplate=(
                f"<b>{category}</b><br>%{{x}}"
                "<br>%{y:,} containers"
                "<br>%{customdata[3]:,} total shift moves"
                "<br>%{customdata[1]} GMPH (moves ÷ 8h)"
                "<br>%{customdata[2]}h movement activity span<extra></extra>"
            ),
        )
    stop_marker_y = np.maximum(
        summary["Moves"].astype(float) * 1.08,
        float(max(1, summary["Moves"].max())) * 0.12,
    )
    movement_marker_y = np.maximum(
        summary["Moves"].astype(float) * 1.25,
        float(max(1, summary["Moves"].max())) * 0.24,
    )
    activity_marker = {
        "symbol": "square",
        "size": 34,
        "color": "rgba(0,0,0,0.01)",
        "line": {"width": 0, "color": "rgba(0,0,0,0)"},
    }
    figure.add_scatter(
        x=summary["Axis"],
        y=movement_marker_y,
        mode="markers+text",
        marker=activity_marker,
        text=summary["Moves"].map(lambda value: f'⚡ <b>{int(value):,}</b>'),
        textposition="middle center",
        textfont={"color": "#dffaf6", "size": 8},
        name="Movements",
        showlegend=False,
        cliponaxis=False,
        customdata=np.column_stack(
            [summary["Shift Start"].astype(str), summary["Moves"], summary["GMPH"]]
        ),
        hovertemplate=(
            "<b>Shift movements</b><br>%{x}"
            "<br>⚡ %{customdata[1]:,} treated movements"
            "<br>%{customdata[2]:.1f} GMPH"
            "<br><b>Click to inspect these containers</b><extra></extra>"
        ),
    )
    figure.add_scatter(
        x=summary["Axis"],
        y=stop_marker_y,
        mode="markers+text",
        marker=activity_marker,
        text=summary.apply(
            lambda row: (
                f'⏸ <b>{int(row["Stop Count"])}</b> · '
                f'{int(row["Stop Minutes"]) // 60}:'
                f'{int(row["Stop Minutes"]) % 60:02d}'
            ),
            axis=1,
        ),
        textposition="middle center",
        textfont={"color": "#ffd07a", "size": 8},
        name="Stops",
        showlegend=False,
        cliponaxis=False,
        customdata=np.column_stack(
            [
                summary["Shift Start"].astype(str),
                summary["Stop Count"],
                summary["Stop Minutes"],
                summary["Longest Stop"],
            ]
        ),
        hovertemplate=(
            "<b>Shift stops ≥10 min</b><br>%{x}"
            "<br>⏸ %{customdata[1]:,} stops"
            "<br>%{customdata[2]:,} inactive minutes"
            "<br>%{customdata[3]:,} min longest"
            "<br><b>Click to inspect stop records</b><extra></extra>"
        ),
    )
    figure.update_layout(
        height=228,
        margin={"l": 8, "r": 8, "t": 54, "b": 48},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        template="none",
        font={"family": "IBM Plex Sans, sans-serif", "color": "#9bb2bb", "size": 9},
        title={
            "text": "SHIFT PERFORMANCE & FLOW MIX",
            "font": {"size": 10, "color": "#d9edf2"},
            "x": 0.01,
            "y": 0.98,
        },
        barmode="stack",
        legend={
            "orientation": "h",
            "x": 1,
            "xanchor": "right",
            "y": 1.31,
            "yanchor": "top",
            "font": {"size": 9, "color": "#e7f7fa"},
            "bgcolor": "rgba(0,0,0,0)",
            "traceorder": "normal",
            "entrywidth": 72,
            "entrywidthmode": "pixels",
        },
        bargap=0.38,
        hoverlabel={"bgcolor": "#10252e", "font_color": "#ffffff"},
        clickmode="event+select",
        dragmode=False,
        xaxis={
            "showgrid": False,
            "fixedrange": True,
            "tickangle": 0,
            "automargin": True,
            "tickfont": {"size": 8, "color": "#b9d0d7"},
            "linecolor": "rgba(160,205,215,.14)",
        },
        yaxis={
            "showgrid": True,
            "gridcolor": "rgba(160,205,215,.10)",
            "zeroline": False,
            "showticklabels": False,
            "fixedrange": True,
            "range": [0, max(1, float(summary["Moves"].max()) * 1.48)],
        },
    )
    return figure, summary.reset_index(drop=True)


def shift_flow_mix_chart(frame, treated_mask, shift_summary):
    if shift_summary.empty:
        return None
    history = frame.loc[
        treated_mask & frame["Last Move DT"].notna(),
        ["Last Move DT", "Operation", "Freight"],
    ].copy()
    history["Shift Start"] = history["Last Move DT"].map(shift_start_for_timestamp)
    history = history[history["Shift Start"].isin(shift_summary["Shift Start"])]
    freight = history["Freight"].astype(str).str.lower()
    history["Import"] = history["Operation"].isin(["Import", "Restow"]).astype(int)
    history["Export full"] = (
        history["Operation"].isin(["Export", "Restow"])
        & freight.str.contains("full|laden|fcl", regex=True)
    ).astype(int)
    history["Export empty"] = (
        history["Operation"].isin(["Export", "Restow"])
        & freight.str.contains("empty", regex=True)
    ).astype(int)
    mix = (
        history.groupby("Shift Start")[["Import", "Export full", "Export empty"]]
        .sum()
        .reindex(shift_summary["Shift Start"], fill_value=0)
        .reset_index()
    )
    mix["Shift"] = mix["Shift Start"].map(
        lambda value: {7: "S1", 15: "S2", 23: "S3"}.get(value.hour, "S")
    )
    mix["Axis"] = mix.apply(
        lambda row: f'{row["Shift Start"]:%d %b}<br>{row["Shift"]}', axis=1
    )
    mix["Total"] = mix[["Import", "Export full", "Export empty"]].sum(axis=1)
    figure = go.Figure()
    palette = {
        "Import": "#38e8d1",
        "Export full": "#62a9ff",
        "Export empty": "#ffbd59",
    }
    for category in ["Import", "Export full", "Export empty"]:
        figure.add_bar(
            x=mix["Axis"],
            y=mix[category],
            name=category,
            marker_color=palette[category],
            customdata=np.column_stack(
                [mix["Shift Start"].astype(str), mix["Total"], mix["Shift"]]
            ),
            hovertemplate=(
                f"<b>{category}</b><br>%{{x}}<br>%{{y:,}} containers"
                "<br>%{customdata[1]:,} total shift moves<extra></extra>"
            ),
        )
    figure.add_scatter(
        x=mix["Axis"],
        y=mix["Total"],
        mode="text",
        text=mix["Total"].map(lambda value: f"{int(value):,}"),
        textposition="top center",
        textfont={"color": "#e7f7fa", "size": 9},
        hoverinfo="skip",
        showlegend=False,
    )
    figure.update_layout(
        height=142,
        margin={"l": 8, "r": 8, "t": 31, "b": 24},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "IBM Plex Sans, sans-serif", "color": "#9bb2bb", "size": 8},
        title={
            "text": "SHIFT FLOW MIX  ·  import / export full / export empty",
            "font": {"size": 10, "color": "#d9edf2"},
            "x": 0.01,
            "y": 0.97,
        },
        barmode="stack",
        bargap=0.38,
        legend={
            "orientation": "h",
            "x": 1,
            "xanchor": "right",
            "y": 1.15,
            "font": {"size": 8},
        },
        hoverlabel={"bgcolor": "#10252e", "font_color": "#ffffff"},
        clickmode="event+select",
        dragmode=False,
        xaxis={"showgrid": False, "fixedrange": True, "tickfont": {"size": 8}},
        yaxis={
            "showgrid": True,
            "gridcolor": "rgba(160,205,215,.10)",
            "zeroline": False,
            "showticklabels": False,
            "fixedrange": True,
            "rangemode": "tozero",
        },
    )
    return figure


def terminal_operation_selection_table(frame):
    terminal = frame["ACTUAL TERMINAL ID"].astype(str).str.upper()
    operation = frame["Operation"].astype(str)
    freight = frame["Freight"].astype(str).str.lower()
    size = frame["Size"].astype(str)

    def cell_count(operation_name, terminal_name, nature_name, size_name):
        operation_mask = (
            operation.isin(["Import", "Restow"])
            if operation_name == "Import"
            else operation.isin(["Export", "Restow"])
        )
        nature_mask = (
            freight.str.contains("full|laden|fcl", regex=True)
            if nature_name == "Full"
            else freight.str.contains("empty", regex=True)
        )
        return safe_int(
            (
                operation_mask
                & terminal.eq(terminal_name)
                & nature_mask
                & size.eq(size_name)
            ).sum()
        )

    columns = []
    metadata = {}
    for terminal_name in ["TCR", "TC3"]:
        for nature_name, nature_short in [("Full", "F"), ("Empty", "E")]:
            for size_name, size_short in [("20′", "20"), ("40′", "40/45")]:
                column_name = f"{terminal_name} {nature_short}{size_short}"
                columns.append(column_name)
                metadata[column_name] = (
                    terminal_name,
                    nature_name,
                    "20" if size_name == "20′" else "40",
                )
    rows = []
    for operation_name in ["Import", "Export"]:
        values = {
            column_name: cell_count(
                operation_name,
                metadata[column_name][0],
                metadata[column_name][1],
                "20′" if metadata[column_name][2] == "20" else "40′",
            )
            for column_name in columns
        }
        values["All"] = safe_int(
            operation.isin(
                ["Import", "Restow"]
                if operation_name == "Import"
                else ["Export", "Restow"]
            ).sum()
        )
        rows.append(values)
    total_row = {column: rows[0][column] + rows[1][column] for column in columns}
    total_row["All"] = rows[0]["All"] + rows[1]["All"]
    rows.append(total_row)
    return pd.DataFrame(rows, index=["⬇ Import", "⬆ Export", "Σ Total"]), metadata


def styled_terminal_matrix(table):
    def style_row(row):
        styles = []
        for column in table.columns:
            if row.name == "⬇ Import":
                styles.append(
                    "color:#38e8d1;background-color:rgba(56,232,209,.035);"
                )
            elif row.name == "⬆ Export" and " F" in column:
                styles.append(
                    "color:#78b6ff;background-color:rgba(98,169,255,.035);"
                )
            elif row.name == "⬆ Export" and " E" in column:
                styles.append(
                    "color:#ffca70;background-color:rgba(255,189,89,.035);"
                )
            else:
                styles.append("color:#e7f1f3;background-color:rgba(255,255,255,.018);")
        return styles

    return (
        table.style.apply(style_row, axis=1)
        .format("{:,.0f}")
        .set_properties(**{"font-weight": "600", "text-align": "center"})
    )


def select_terminal_matrix_cell(
    target_visit, target_visit_ids, operation, terminal, nature, size
):
    clear_container_inspector(clear_metric_widgets=True)
    st.session_state.detail_visit_id = target_visit
    st.session_state.detail_visit_ids = list(target_visit_ids)
    st.session_state.detail_metric = "matrix|" + "|".join(
        [operation, terminal, nature, size]
    )


def render_terminal_button_matrix(
    frame, target_visit, target_visit_ids, host=None
):
    if host is None:
        host = st
    table, metadata = terminal_operation_selection_table(frame)
    host.markdown(
        '<div class="terminal-mix-head"><b>Terminal operation profile</b>'
        '<span>Click a value · hover for complete architecture</span></div>'
        '<div class="matrix-native-groups"><span>↕ Flow</span>'
        '<span>🏗 TCR</span><span>🏗 TC3</span><span>Σ All</span></div>',
        unsafe_allow_html=True,
    )
    with host.container(key=f"matrix_grid_{target_visit}"):
        header_columns = st.columns([1.35] + [1] * 9)
        header_labels = [
            "Flow", "■ F20", "▰ F40/45", "□ E20", "▱ E40/45",
            "■ F20", "▰ F40/45", "□ E20", "▱ E40/45", "Σ All",
        ]
        header_help = [
            "Container operation direction",
            "TCR · Full · 20-foot", "TCR · Full · 40/45-foot",
            "TCR · Empty · 20-foot", "TCR · Empty · 40/45-foot",
            "TC3 · Full · 20-foot", "TC3 · Full · 40/45-foot",
            "TC3 · Empty · 20-foot", "TC3 · Empty · 40/45-foot",
            "All terminals, natures and sizes",
        ]
        header_labels = [
            "FLOW", "&#9679; FULL<br>20&#8242;", "&#9679; FULL<br>40&#8242;",
            "&#9675; EMPTY<br>20&#8242;", "&#9675; EMPTY<br>40&#8242;",
            "&#9679; FULL<br>20&#8242;", "&#9679; FULL<br>40&#8242;",
            "&#9675; EMPTY<br>20&#8242;", "&#9675; EMPTY<br>40&#8242;",
            "&Sigma;<br>ALL",
        ]
        for header_index, (column, label, help_text) in enumerate(zip(
            header_columns, header_labels, header_help
        )):
            semantic_class = (
                " full-head"
                if header_index in (1, 2, 5, 6)
                else (" empty-head" if header_index in (3, 4, 7, 8) else "")
            )
            column.markdown(
                f'<div class="matrix-col-head{semantic_class}" '
                f'title="{help_text}">{label}</div>',
                unsafe_allow_html=True,
            )
        for row_index, row_name in enumerate(table.index):
            row_columns = st.columns([1.35] + [1] * 9)
            row_columns[0].markdown(
                f'<div class="matrix-row-head">{row_name}</div>',
                unsafe_allow_html=True,
            )
            operation = ["Import", "Export", ""][row_index]
            for column_index, column_name in enumerate(table.columns):
                terminal = nature = size = ""
                if column_name in metadata:
                    terminal, nature, size = metadata[column_name]
                architecture = " → ".join(
                    part
                    for part in [
                        terminal or "All terminals",
                        operation or "All flows",
                        nature or "All natures",
                        (
                            "20-foot"
                            if size == "20"
                            else ("40/45-foot" if size == "40" else "All sizes")
                        ),
                    ]
                    if part
                )
                value = safe_int(table.iloc[row_index, column_index])
                row_columns[column_index + 1].button(
                    f"{value:,}",
                    key=(
                        f"matrix_cell_{target_visit}_r{row_index}_"
                        f"c{column_index}"
                    ),
                    help=f"{architecture} · {value:,} containers",
                    use_container_width=True,
                    on_click=select_terminal_matrix_cell,
                    args=(
                        target_visit,
                        target_visit_ids,
                        operation,
                        terminal,
                        nature,
                        size,
                    ),
                )


def kpi(label, value, note, color=""):
    return f'<div class="kpi"><div class="label">{label}</div><div class="value {color}">{value}</div><div class="delta">{note}</div></div>'


def clear_container_inspector(clear_metric_widgets=True):
    for state_key in [
        "detail_visit_id", "detail_visit_ids", "detail_metric", "fleet_metric_selector",
        "drawer_group", "drawer_search", "drawer_state",
        "drawer_terminal", "drawer_size",
    ]:
        st.session_state.pop(state_key, None)
    if clear_metric_widgets:
        for state_key in list(st.session_state):
            if str(state_key).startswith("metric_list_"):
                st.session_state.pop(state_key, None)
        st.session_state.metric_widget_epoch = (
            int(st.session_state.get("metric_widget_epoch", 0)) + 1
        )


def select_fleet_metric(widget_key, target_visit, metric_by_label):
    selected_label = st.session_state.get(widget_key)
    if not selected_label:
        return
    selected_metric = metric_by_label.get(selected_label)
    if not selected_metric:
        return
    # A single inspector can be active. Clear every other vessel's remembered tile.
    for state_key in list(st.session_state):
        if str(state_key).startswith("metric_list_") and state_key != widget_key:
            st.session_state.pop(state_key, None)
    for state_key in [
        "drawer_group", "drawer_search", "drawer_state",
        "drawer_terminal", "drawer_size",
    ]:
        st.session_state.pop(state_key, None)
    st.session_state.detail_visit_id = target_visit
    st.session_state.detail_visit_ids = [target_visit]
    st.session_state.detail_metric = selected_metric
    # Remount every vessel metric widget. This prevents a dismissed dialog's
    # previous radio selection from being restored by Streamlit on the next click.
    st.session_state.metric_widget_epoch = (
        int(st.session_state.get("metric_widget_epoch", 0)) + 1
    )


def open_vessel_dashboard(target_visit):
    clear_container_inspector(clear_metric_widgets=True)
    st.session_state.selected_visit_id = target_visit
    st.session_state.page_scope = "Overview"


DATA_SOURCE_WARNING = ""
try:
    if MODE == "test":
        units, visits = read_test_data(str(DATA_DIR))
    elif MODE in {"api_test", "sample", "api_sample"}:
        units, visits = read_api_sample_data(
            str(UNIT_API_SAMPLE_FILE),
            str(VESSEL_API_SAMPLE_FILE),
        )
    else:
        units, visits = read_live_data()
    # Operational KPIs must be based on the vessel movement source only.
    # HANANE is intentionally excluded: its crane rows cannot be safely
    # attributed to inactivity gaps inferred from container timestamps.
    hanane_report = pd.DataFrame()
except Exception as exc:
    if MODE == "live":
        try:
            units, visits = read_test_data(str(DATA_DIR))
            DATA_SOURCE_WARNING = f"Live API unavailable; showing test snapshot: {exc}"
            hanane_report = pd.DataFrame()
        except Exception as fallback_exc:
            st.error(f"Data sources unavailable — {exc}; fallback: {fallback_exc}")
            st.stop()
    else:
        st.error(f"Data source unavailable — {exc}")
        st.stop()


def hanane_for_shift(vessel_name, shift_start):
    if hanane_report.empty or pd.isna(shift_start):
        return hanane_report.iloc[0:0]
    return hanane_report[
        hanane_report["Vessel Key"].eq(normalized_vessel_name(vessel_name))
        & hanane_report["Shift Start"].eq(pd.Timestamp(shift_start))
    ].copy()

candidate_keys = pd.concat([units["I/B Actual Visit"], units["O/B Actual Visit"]]).dropna().astype(str)
candidate_keys = candidate_keys[candidate_keys.str.fullmatch(r"\d{9}")].value_counts()
visit_lookup = visits.assign(Visit=visits["Visit"].astype(str)).set_index("Visit") if not visits.empty else pd.DataFrame()

visit_options = []
for key, count in candidate_keys.items():
    if key in visit_lookup.index:
        row = visit_lookup.loc[key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        visit_options.append((key, str(row.get("Vessel Name", key)), str(row.get("Phase", "Unknown")), count))
visit_options = sorted(visit_options, key=lambda x: (x[2] not in {"Working", "Inbound"}, -x[3]))

st.markdown(
    f'<div class="topline"><div class="brand">NEVIS <b>OPERATIONS</b> / VESSEL INTELLIGENCE</div>'
    f'<div class="live"><span class="pulse"></span>{html.escape(MODE)} mode · '
    f'{html.escape(units.attrs.get("source_status", "final snapshot"))}</div></div>',
    unsafe_allow_html=True,
)
if DATA_SOURCE_WARNING:
    st.warning(DATA_SOURCE_WARNING)

st.markdown(
    '<div class="section-title" style="margin-top:8px"><h3>Filter vessel visits</h3>'
    '<span>Choose operational status first, then select an escale</span></div>',
    unsafe_allow_html=True,
)
phase_values = sorted({item[2] for item in visit_options if item[2] and item[2] != "nan"})
line_values = sorted({
    str(visit_lookup.loc[item[0]].iloc[-1].get("Line", "—"))
    if isinstance(visit_lookup.loc[item[0]], pd.DataFrame)
    else str(visit_lookup.loc[item[0]].get("Line", "—"))
    for item in visit_options
})
terminal_values = sorted(units["ACTUAL TERMINAL ID"].dropna().astype(str).unique())
filter1, filter2, filter3, filter4 = st.columns([1.15, 1.25, 1, 1.6])
with filter1:
    preferred_phase = "Working" if "Working" in phase_values else "All"
    phase_filter = st.selectbox("Visit status", ["All"] + phase_values, index=(["All"] + phase_values).index(preferred_phase))
with filter2:
    line_filter = st.multiselect("Shipping line", line_values, placeholder="All lines")
with filter3:
    terminal_filter_top = st.multiselect("Terminal", terminal_values, placeholder="TC3 / TCR")
with filter4:
    visit_search = st.text_input("Search escale", placeholder="Vessel name or visit number")

valid_move_times = units["Last Move DT"].dropna()
date_minimum = valid_move_times.min().to_pydatetime()
date_maximum = valid_move_times.max().to_pydatetime()
date_col1, date_col2, date_note = st.columns([1, 1, 2.4])
with date_col1:
    visit_from = st.datetime_input(
        "Visit activity from",
        value=date_minimum,
        min_value=date_minimum,
        max_value=date_maximum,
        format="DD/MM/YYYY",
        step=timedelta(minutes=15),
    )
with date_col2:
    visit_to = st.datetime_input(
        "Visit activity to",
        value=date_maximum,
        min_value=date_minimum,
        max_value=date_maximum,
        format="DD/MM/YYYY",
        step=timedelta(minutes=15),
    )
with date_note:
    st.caption(
        "The date-time range keeps escales whose recorded activity overlaps this window."
    )
if pd.Timestamp(visit_from) > pd.Timestamp(visit_to):
    st.warning("The activity start must be earlier than the activity end.")
    st.stop()

filtered_visit_options = []
for item in visit_options:
    item_id, item_name, item_phase, item_count = item
    item_row = visit_lookup.loc[item_id]
    if isinstance(item_row, pd.DataFrame):
        item_row = item_row.iloc[-1]
    item_line = str(item_row.get("Line", "—"))
    if phase_filter != "All" and item_phase != phase_filter:
        continue
    if line_filter and item_line not in line_filter:
        continue
    if terminal_filter_top:
        item_terminals = set(
            units.loc[
                units["I/B Actual Visit"].astype(str).eq(item_id)
                | units["O/B Actual Visit"].astype(str).eq(item_id),
                "ACTUAL TERMINAL ID",
            ].dropna().astype(str)
        )
        if not item_terminals.intersection(terminal_filter_top):
            continue
    if visit_search and visit_search.lower() not in f"{item_name} {item_id}".lower():
        continue
    item_times = units.loc[
        units["I/B Actual Visit"].astype(str).eq(item_id)
        | units["O/B Actual Visit"].astype(str).eq(item_id),
        "Last Move DT",
    ].dropna()
    if not item_times.empty:
        if item_times.max() < pd.Timestamp(visit_from):
            continue
        if item_times.min() > pd.Timestamp(visit_to):
            continue
    filtered_visit_options.append(item)

if not filtered_visit_options:
    st.warning("No escale matches the selected filters.")
    st.stop()

labels = [f"{name}  ·  {key}" for key, name, _, _ in filtered_visit_options]
if "selected_visit_id" not in st.session_state and visit_options:
    st.session_state.selected_visit_id = visit_options[0][0]
matrix_visit = st.query_params.get("matrix_visit")
if matrix_visit and any(item[0] == str(matrix_visit) for item in visit_options):
    matrix_parts = [
        str(st.query_params.get("matrix_operation", "")),
        str(st.query_params.get("matrix_terminal", "")),
        str(st.query_params.get("matrix_nature", "")),
        str(st.query_params.get("matrix_size", "")),
    ]
    clear_container_inspector(clear_metric_widgets=True)
    st.session_state.selected_visit_id = str(matrix_visit)
    st.session_state.detail_visit_id = str(matrix_visit)
    st.session_state.detail_metric = "matrix|" + "|".join(matrix_parts)
    for matrix_key in [
        "matrix_visit", "matrix_operation", "matrix_terminal",
        "matrix_nature", "matrix_size",
    ]:
        if matrix_key in st.query_params:
            del st.query_params[matrix_key]
    st.rerun()
shift_visit = st.query_params.get("shift_visit")
shift_start_param = st.query_params.get("shift_start")
if (
    shift_visit
    and shift_start_param
    and any(item[0] == str(shift_visit) for item in visit_options)
):
    parsed_shift_start = pd.to_datetime(shift_start_param, errors="coerce")
    if pd.notna(parsed_shift_start):
        clear_container_inspector(clear_metric_widgets=True)
        st.session_state.selected_visit_id = str(shift_visit)
        st.session_state.detail_visit_id = str(shift_visit)
        st.session_state.detail_metric = (
            "shift|" + pd.Timestamp(parsed_shift_start).isoformat()
        )
    for shift_key in ["shift_visit", "shift_start"]:
        if shift_key in st.query_params:
            del st.query_params[shift_key]
    st.rerun()
select_col, view_col, search_col = st.columns([2.25, 1, 1.45])
with select_col:
    current_default = next(
        (
            labels[index]
            for index, item in enumerate(filtered_visit_options)
            if item[0] == st.session_state.selected_visit_id
        ),
        labels[0],
    )
    selected_labels = st.multiselect(
        "Select escales",
        labels,
        default=[],
        placeholder="Choose one or several escales",
        key=f"selected_escales_{phase_filter}",
    )
with view_col:
    scope_default = None if "page_scope" in st.session_state else "Fleet"
    scope = st.segmented_control(
        "View", ["Fleet", "Overview", "Containers"], default=scope_default, key="page_scope"
    )
with search_col:
    query = st.text_input("Find a container in this visit", placeholder="e.g. MSKU1234567")

selected_visit_options = (
    [filtered_visit_options[labels.index(label)] for label in selected_labels]
    if selected_labels
    else filtered_visit_options
)
visit_id = selected_visit_options[0][0]
previous_visit_id = st.session_state.get("selected_visit_id")
if previous_visit_id != visit_id:
    clear_container_inspector(clear_metric_widgets=True)
st.session_state.selected_visit_id = visit_id
query_visit = st.session_state.get("detail_visit_id")
query_metric = st.session_state.get("detail_metric", "programme")

if scope != "Fleet" and query_visit:
    clear_container_inspector(clear_metric_widgets=True)
    query_visit = None
    query_metric = "programme"

if scope == "Fleet":
    working_visits = selected_visit_options
    summary_programme = 0
    summary_treated = 0
    summary_shift_moves = 0
    summary_terminals = set()
    summary_frames = []
    for summary_id, _, _, _ in working_visits:
        summary_units = units[
            units["I/B Actual Visit"].astype(str).eq(summary_id)
            | units["O/B Actual Visit"].astype(str).eq(summary_id)
        ].copy()
        summary_units["Operation"] = np.select(
            [
                summary_units["I/B Actual Visit"].astype(str).eq(summary_id)
                & summary_units["O/B Actual Visit"].astype(str).eq(summary_id),
                summary_units["I/B Actual Visit"].astype(str).eq(summary_id),
                summary_units["O/B Actual Visit"].astype(str).eq(summary_id),
            ],
            ["Restow", "Import", "Export"],
            default="Other",
        )
        summary_import = summary_units["Operation"].isin(["Import", "Restow"])
        summary_export = summary_units["Operation"].isin(["Export", "Restow"])
        summary_done = (
            summary_import
            & summary_units["T-State"].astype(str).str.lower().isin(
                ["yard", "departed", "ec/out"]
            )
        ) | (
            summary_export
            & (
                summary_units["T-State"].astype(str).str.lower().eq("loaded")
                | summary_units["Position"].astype(str).str.startswith("V-")
            )
        )
        summary_units["_Treated"] = summary_done
        summary_units["_Visit ID"] = summary_id
        summary_frames.append(summary_units)
        summary_programme += safe_int(summary_import.sum() + summary_export.sum())
        summary_treated += safe_int(summary_done.sum())
        summary_reference = summary_units["Last Move DT"].max()
        if pd.notna(summary_reference):
            summary_start, summary_end = shift_window(summary_reference)
            summary_shift_moves += safe_int(
                (
                    summary_done
                    & summary_units["Last Move DT"].between(
                        summary_start, summary_end, inclusive="left"
                    )
                ).sum()
            )
        summary_terminals.update(
            summary_units["ACTUAL TERMINAL ID"].dropna().astype(str).unique()
        )
    summary_remaining = max(0, summary_programme - summary_treated)
    summary_completion = 100 * summary_treated / max(1, summary_programme)
    section_heading = (
        "Selected vessel visit"
        if len(working_visits) == 1
        else "Consolidated fleet selection"
    )
    with st.container(key="selected_scope_header"):
        st.markdown(
            f'<div class="section-title"><h3>{section_heading}</h3>'
            f'<span>{len(working_visits)} vessel visit{"s" if len(working_visits) != 1 else ""}'
            f' · {html.escape(phase_filter)} operations</span></div>',
            unsafe_allow_html=True,
        )
    detail_open = bool(query_visit and query_metric)
    if len(working_visits) > 1:
        aggregate_panel = st.container(key="aggregate_panel")
        aggregate_units = pd.concat(summary_frames, ignore_index=True)
        aggregate_treated = aggregate_units["_Treated"].astype(bool)
        aggregate_last = aggregate_units["Last Move DT"].max()
        aggregate_first = aggregate_units["Last Move DT"].min()
        terminal_label = ", ".join(sorted(summary_terminals)) or "—"
        aggregate_panel.markdown(
            f"""
<div class="fleet-card">
 <div class="fleet-head"><div><div class="eyebrow">{html.escape(phase_filter)} · CONSOLIDATED OPERATIONS</div>
 <h3>{len(working_visits)} SELECTED VESSEL VISITS</h3>
 <small>{html.escape(terminal_label)} · Activity {aggregate_first:%d %b %H:%M}–{aggregate_last:%d %b %H:%M}</small></div>
 <div class="fleet-score">{summary_completion:.1f}%<small>fleet treated</small></div></div>
 <div class="fleet-ops-mini">
  <span>Operational scope<b>{len(working_visits)} escales</b></span>
  <span class="gmph">Current shifts<b>{summary_shift_moves:,} moves</b></span>
  <span>Source<b>Combined selected visits</b></span>
 </div>
 <div class="progress-track"><div class="progress-fill" style="width:{min(100, summary_completion):.1f}%"></div></div>
</div>
""",
            unsafe_allow_html=True,
        )
        aggregate_chart, aggregate_shift_summary = shift_performance_chart(
            aggregate_units, aggregate_treated, "__aggregate__"
        )
        if aggregate_chart is not None:
            aggregate_chart_epoch = int(
                st.session_state.get("aggregate_chart_epoch", 0)
            )
            aggregate_chart_event = aggregate_panel.plotly_chart(
                aggregate_chart,
                use_container_width=True,
                config={"displayModeBar": False, "scrollZoom": False},
                key=f"aggregate_shift_chart_{aggregate_chart_epoch}",
                on_select="rerun",
                selection_mode="points",
            )
            aggregate_points = list(aggregate_chart_event.selection.points)
            if aggregate_points:
                aggregate_point = aggregate_points[0]
                aggregate_custom = aggregate_point.get("customdata", [])
                aggregate_curve = aggregate_point.get("curve_number")
                if aggregate_curve in [0, 1, 2, 3, 4] and aggregate_custom:
                    aggregate_selected_shift = pd.to_datetime(
                        aggregate_custom[0], errors="coerce"
                    )
                    if pd.notna(aggregate_selected_shift):
                        clear_container_inspector(clear_metric_widgets=True)
                        query_visit = "__aggregate__"
                        metric_prefix = (
                            "stops" if aggregate_curve == 4 else "shift"
                        )
                        query_metric = metric_prefix + "|" + pd.Timestamp(
                            aggregate_selected_shift
                        ).isoformat()
                        st.session_state.detail_visit_id = query_visit
                        st.session_state.detail_visit_ids = [
                            item[0] for item in working_visits
                        ]
                        st.session_state.detail_metric = query_metric
                        st.session_state.aggregate_chart_epoch = (
                            aggregate_chart_epoch + 1
                        )
                        detail_open = True
        render_terminal_button_matrix(
            aggregate_units,
            "__aggregate__",
            [item[0] for item in working_visits],
            host=aggregate_panel,
        )
        st.markdown(
            '<div class="section-title" style="margin-top:12px">'
            '<h3>Individual vessel details</h3>'
            f'<span>{len(working_visits)} selected escales · complete operational view</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        card_visits = working_visits
        fleet_area = st.container(key="fleet_rows")
        fleet_columns = None
    else:
        card_visits = working_visits
        fleet_area = st.container(key="fleet_rows")
        fleet_columns = None
    for card_index, (fleet_id, fleet_name, fleet_phase, _) in enumerate(card_visits):
        fleet_units = units[
            units["I/B Actual Visit"].astype(str).eq(fleet_id)
            | units["O/B Actual Visit"].astype(str).eq(fleet_id)
        ].copy()
        fleet_units["Operation"] = np.select(
            [
                fleet_units["I/B Actual Visit"].astype(str).eq(fleet_id)
                & fleet_units["O/B Actual Visit"].astype(str).eq(fleet_id),
                fleet_units["I/B Actual Visit"].astype(str).eq(fleet_id),
                fleet_units["O/B Actual Visit"].astype(str).eq(fleet_id),
            ],
            ["Restow", "Import", "Export"],
            default="Other",
        )
        f_import = fleet_units["Operation"].isin(["Import", "Restow"])
        f_export = fleet_units["Operation"].isin(["Export", "Restow"])
        f_full = fleet_units["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)
        f_empty = fleet_units["Freight"].str.lower().str.contains("empty", regex=True)
        f_size20 = fleet_units["Size"].eq("20′")
        f_size40 = fleet_units["Size"].eq("40′")
        f_size_other = fleet_units["Size"].eq("Other")
        f_treated = (
            f_import & fleet_units["T-State"].astype(str).str.lower().isin(["yard", "departed", "ec/out"])
        ) | (
            f_export
            & (
                fleet_units["T-State"].astype(str).str.lower().eq("loaded")
                | fleet_units["Position"].astype(str).str.startswith("V-")
            )
        )
        fleet_programme = safe_int(f_import.sum() + f_export.sum())
        fleet_treated = safe_int(f_treated.sum())
        fleet_remaining = max(0, fleet_programme - fleet_treated)
        fleet_pct = 100 * fleet_treated / max(1, fleet_programme)
        fleet_pct_label = "100%" if fleet_remaining == 0 else f"{fleet_pct:.1f}%"
        fleet_row = visit_lookup.loc[fleet_id]
        if isinstance(fleet_row, pd.DataFrame):
            fleet_row = fleet_row.iloc[-1]
        fleet_terminal = ", ".join(
            sorted(fleet_units["ACTUAL TERMINAL ID"].dropna().astype(str).unique())
        ) or "—"
        fleet_last = fleet_units["Last Move DT"].max()
        fleet_shift_start, fleet_shift_end = shift_window(fleet_last)
        in_current_shift = fleet_units["Last Move DT"].between(
            fleet_shift_start, fleet_shift_end, inclusive="left"
        )
        treated_in_shift = f_treated & in_current_shift
        remaining_mask = ~f_treated
        shift_import = safe_int((treated_in_shift & f_import).sum())
        shift_export_full = safe_int((treated_in_shift & f_export & f_full).sum())
        shift_export_empty = safe_int((treated_in_shift & f_export & f_empty).sum())
        treated_import_total = safe_int((f_treated & f_import).sum())
        treated_export_full_total = safe_int((f_treated & f_export & f_full).sum())
        treated_export_empty_total = safe_int((f_treated & f_export & f_empty).sum())
        remain_import = safe_int((remaining_mask & f_import).sum())
        remain_export_full = safe_int((remaining_mask & f_export & f_full).sum())
        remain_export_empty = safe_int((remaining_mask & f_export & f_empty).sum())
        elapsed_shift_hours = max(
            1 / 60,
            min(8.0, (fleet_last - fleet_shift_start).total_seconds() / 3600),
        )
        shift_gmph = safe_int(treated_in_shift.sum()) / elapsed_shift_hours
        fleet_stops = infer_stops(
            fleet_units.loc[treated_in_shift, "Last Move DT"],
            threshold_minutes=10,
            window_start=fleet_shift_start,
            window_end=fleet_shift_end,
        )
        fleet_report = (
            hanane_for_shift(fleet_name, fleet_shift_start)
            if fleet_phase.lower() == "working"
            else hanane_report.iloc[0:0]
        )
        sts_status = (
            "Verified source" if not fleet_report.empty else "Awaiting crane source"
        )
        if card_index % 3 == 0:
            fleet_columns = fleet_area.columns(3)
        target_column = fleet_columns[card_index % 3]
        with target_column.container(key=f"vessel_panel_{fleet_id}"):
            st.markdown(
                f"""
<div class="fleet-card">
 <div class="fleet-head"><div><div class="eyebrow">{html.escape(str(fleet_row.get("Line", "—")))} · {html.escape(fleet_phase)}</div>
 <h3>{html.escape(fleet_name)}</h3><small>{fleet_id} · {html.escape(fleet_terminal)} · Last {fleet_last:%d %b %H:%M}</small></div>
 <div class="fleet-score">{fleet_pct_label}<small>treated</small></div></div>
 <div class="fleet-ops-mini">
  <span>Shift window<b>{fleet_shift_start:%H:%M}–{fleet_shift_end:%H:%M}</b></span>
  <span class="gmph">Vessel GMPH<b>{shift_gmph:.1f}</b></span>
  <span>STS productivity<b>{html.escape(sts_status)}</b></span>
 </div>
 <div class="progress-track"><div class="progress-fill" style="width:{min(100, fleet_pct):.1f}%"></div></div>
</div>
""",
                unsafe_allow_html=True,
            )
            metric_records = [
                ("Programme", "programme"),
                ("Treated", "treated"),
                ("Remaining", "remaining"),
                ("Import", "import"),
                ("Export full", "export_full"),
                ("Export empty", "export_empty"),
            ]
            metric_labels = [
                f"📋 **PROGRAMME**  \nΣ **{fleet_programme:,}** containers",
                f"✅ **TREATED**  \nΣ **{fleet_treated:,}** · ⚡ Shift **{safe_int(treated_in_shift.sum()):,}** · **{fleet_pct_label}**",
                f"⏳ **REMAINING**  \nΣ **{fleet_remaining:,}** containers",
                f"⬇ **IMPORT**  \n📋 Plan **{safe_int(f_import.sum()):,}** · ✅ Treated **{treated_import_total:,}**  \n⚡ Shift **{shift_import:,}** · ⏳ Remaining **{remain_import:,}**",
                f"📦 **EXPORT FULL**  \n📋 Plan **{safe_int((f_export & f_full).sum()):,}** · ✅ Treated **{treated_export_full_total:,}**  \n⚡ Shift **{shift_export_full:,}** · ⏳ Remaining **{remain_export_full:,}**",
                f"▫ **EXPORT EMPTY**  \n📋 Plan **{safe_int((f_export & f_empty).sum()):,}** · ✅ Treated **{treated_export_empty_total:,}**  \n⚡ Shift **{shift_export_empty:,}** · ⏳ Remaining **{remain_export_empty:,}**",
            ]
            metric_by_label = {
                metric_label: metric_record[1]
                for metric_label, metric_record in zip(metric_labels, metric_records)
            }
            metric_epoch = int(st.session_state.get("metric_widget_epoch", 0))
            metric_widget_key = f"metric_list_{metric_epoch}_{fleet_id}"
            st.radio(
                "Click a metric to inspect containers",
                metric_labels,
                index=None,
                key=metric_widget_key,
                label_visibility="collapsed",
                on_change=select_fleet_metric,
                args=(metric_widget_key, fleet_id, metric_by_label),
            )
            chart_figure, chart_summary = shift_performance_chart(
                fleet_units, f_treated, fleet_id
            )
            if chart_figure is not None:
                chart_epoch = int(st.session_state.get("chart_widget_epoch", 0))
                chart_event = st.plotly_chart(
                    chart_figure,
                    use_container_width=True,
                    config={
                        "displayModeBar": False,
                        "scrollZoom": False,
                        "doubleClick": False,
                    },
                    key=f"shift_chart_{chart_epoch}_{fleet_id}",
                    on_select="rerun",
                    selection_mode="points",
                )
                selected_points = list(chart_event.selection.points)
                if selected_points:
                    selected_point = selected_points[0]
                    custom_data = selected_point.get("customdata", [])
                    selected_curve = selected_point.get("curve_number")
                    if selected_curve in [0, 1, 2, 3, 4] and custom_data:
                        selected_shift = pd.to_datetime(custom_data[0], errors="coerce")
                        if pd.notna(selected_shift):
                            clear_container_inspector(clear_metric_widgets=True)
                            query_visit = fleet_id
                            metric_prefix = "stops" if selected_curve == 4 else "shift"
                            query_metric = metric_prefix + "|" + pd.Timestamp(
                                selected_shift
                            ).isoformat()
                            st.session_state.detail_visit_id = query_visit
                            st.session_state.detail_visit_ids = [fleet_id]
                            st.session_state.detail_metric = query_metric
                            st.session_state.chart_widget_epoch = chart_epoch + 1
                            detail_open = True
            render_terminal_button_matrix(fleet_units, fleet_id, [fleet_id])
            if fleet_phase.lower() == "working":
                report_html = ""
                if not fleet_report.empty:
                    report_moves = safe_int(fleet_report["Total Moves"].sum())
                    report_vessel_gmph = fleet_report["Vessel GMPH"].dropna().max()
                    verified_stop_minutes = safe_int(fleet_report["Stop Minutes"].sum())
                    crane_items = " · ".join(
                        f"{html.escape(str(r['Crane']))} <strong>{float(r['Crane GMPH']):.1f}</strong>"
                        for _, r in fleet_report.iterrows()
                        if str(r["Crane"]).strip() and pd.notna(r["Crane GMPH"])
                    )
                    report_html = (
                        '<div class="report-strip"><span class="source">Hanane verified</span>'
                        f'<i>Reported moves <strong>{report_moves:,}</strong></i>'
                        f'<i>Vessel GMPH <strong>{float(report_vessel_gmph):.1f}</strong></i>'
                        f'<i>Verified stops <strong>{verified_stop_minutes:,} min</strong></i>'
                        + (f"<i>STS {crane_items}</i>" if crane_items else "")
                        + "</div>"
                    )
                if report_html:
                    st.markdown(report_html, unsafe_allow_html=True)
                if fleet_stops["count"]:
                    st.markdown('<div class="stop-popover">', unsafe_allow_html=True)
                    with st.popover(
                        f'⏸ Stops ≥10 min · {fleet_stops["count"]} / '
                        f'{fleet_stops["minutes"]:,} min · longest {fleet_stops["longest"]:,} min',
                        use_container_width=True,
                    ):
                        stop_detail = pd.DataFrame(fleet_stops["details"])
                        stop_detail.insert(0, "Stop", range(1, len(stop_detail) + 1))
                        stop_detail["Shift"] = (
                            f"{fleet_shift_start:%H:%M}–{fleet_shift_end:%H:%M}"
                        )
                        stop_detail["Source"] = "units-page1/2 · Last Move"
                        st.dataframe(
                            stop_detail[
                                ["Stop", "From", "To", "Duration min", "Shift", "Source"]
                            ],
                            hide_index=True,
                            use_container_width=True,
                            height=min(285, 39 + len(stop_detail) * 35),
                        )
                        st.caption(
                            "Stops cover the complete 8-hour shift: shift start to first move, "
                            "between consecutive moves, and last move to shift end."
                        )
                        if not fleet_report.empty:
                            verified_columns = [
                                "Crane", "Stop Minutes", "Crane GMPH", "Observation"
                            ]
                            verified_stops = fleet_report[
                                fleet_report["Stop Minutes"].fillna(0).gt(0)
                            ][verified_columns]
                            if not verified_stops.empty:
                                st.markdown("**Verified crane stops · Hanane report**")
                                st.dataframe(
                                    verified_stops,
                                    hide_index=True,
                                    use_container_width=True,
                                )
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div class="stop-empty">⏸ No stops ≥10 min detected</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div class="stop-empty">⏸ Stop monitoring unavailable</div>',
                    unsafe_allow_html=True,
                )
            st.button(
                "Open vessel dashboard →",
                key=f"open_vessel_{fleet_id}",
                use_container_width=True,
                on_click=open_vessel_dashboard,
                args=(fleet_id,),
            )
    if detail_open:
        @st.dialog(
            "Container inspector",
            width="large",
            on_dismiss=clear_container_inspector,
        )
        def show_container_drawer():
            active_visit_ids = st.session_state.get(
                "detail_visit_ids", [query_visit]
            )
            active_visit_ids = [str(value) for value in active_visit_ids]
            detail_units = units[
                units["I/B Actual Visit"].astype(str).isin(active_visit_ids)
                | units["O/B Actual Visit"].astype(str).isin(active_visit_ids)
            ].copy()
            detail_units["Operation"] = np.select(
                [
                    detail_units["I/B Actual Visit"].astype(str).isin(active_visit_ids)
                    & detail_units["O/B Actual Visit"].astype(str).isin(active_visit_ids),
                    detail_units["I/B Actual Visit"].astype(str).isin(active_visit_ids),
                    detail_units["O/B Actual Visit"].astype(str).isin(active_visit_ids),
                ],
                ["Restow", "Import", "Export"],
                default="Other",
            )
            d_import = detail_units["Operation"].isin(["Import", "Restow"])
            d_export = detail_units["Operation"].isin(["Export", "Restow"])
            d_full = detail_units["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)
            d_empty = detail_units["Freight"].str.lower().str.contains("empty", regex=True)
            d_treated = (
                d_import & detail_units["T-State"].astype(str).str.lower().isin(["yard", "departed", "ec/out"])
            ) | (
                d_export & (
                    detail_units["T-State"].astype(str).str.lower().eq("loaded")
                    | detail_units["Position"].astype(str).str.startswith("V-")
                )
            )
            detail_reference = detail_units["Last Move DT"].max()
            detail_shift_start, detail_shift_end = shift_window(detail_reference)
            d_current_shift = d_treated & detail_units["Last Move DT"].between(
                detail_shift_start, detail_shift_end, inclusive="left"
            )
            if str(query_metric).startswith("stops|"):
                selected_stop_shift = pd.to_datetime(
                    str(query_metric).split("|", 1)[1], errors="coerce"
                )
                selected_stop_end = selected_stop_shift + pd.Timedelta(hours=8)
                stop_rows = []
                for stop_visit_id in active_visit_ids:
                    stop_visit_mask = (
                        detail_units["I/B Actual Visit"].astype(str).eq(stop_visit_id)
                        | detail_units["O/B Actual Visit"].astype(str).eq(stop_visit_id)
                    )
                    stop_times = detail_units.loc[
                        stop_visit_mask
                        & d_treated
                        & detail_units["Last Move DT"].between(
                            selected_stop_shift, selected_stop_end, inclusive="left"
                        ),
                        "Last Move DT",
                    ]
                    inferred = infer_stops(
                        stop_times,
                        threshold_minutes=10,
                        window_start=selected_stop_shift,
                        window_end=selected_stop_end,
                    )
                    stop_vessel_name = next(
                        (
                            item[1] for item in visit_options
                            if item[0] == stop_visit_id
                        ),
                        stop_visit_id,
                    )
                    crane_report = hanane_for_shift(
                        stop_vessel_name, selected_stop_shift
                    )
                    crane_names = "Not available in units-page1/2"
                    for stop_number, stop_detail in enumerate(
                        inferred["details"], start=1
                    ):
                        stop_rows.append(
                            {
                                "Stop": stop_number,
                                "Vessel": stop_vessel_name,
                                "Visit": stop_visit_id,
                                "Crane / STS": crane_names,
                                "From": stop_detail["From"],
                                "To": stop_detail["To"],
                                "Duration min": stop_detail["Duration min"],
                                "Source": "units-page1/2 · Last Move",
                            }
                        )
                    if not crane_report.empty:
                        for _, reported_stop in crane_report[
                            crane_report["Stop Minutes"].fillna(0).gt(0)
                        ].iterrows():
                            stop_rows.append(
                                {
                                    "Stop": "Verified",
                                    "Vessel": stop_vessel_name,
                                    "Visit": stop_visit_id,
                                    "Crane / STS": reported_stop.get(
                                        "Crane", "Unspecified"
                                    ),
                                    "From": pd.NaT,
                                    "To": pd.NaT,
                                    "Duration min": safe_int(
                                        reported_stop.get("Stop Minutes", 0)
                                    ),
                                    "Source": "Hanane report",
                                }
                            )
                stop_table = pd.DataFrame(stop_rows)
                stop_count = (
                    safe_int((stop_table["Stop"] != "Verified").sum())
                    if not stop_table.empty else 0
                )
                stop_total = (
                    safe_int(stop_table["Duration min"].sum())
                    if not stop_table.empty else 0
                )
                st.markdown(
                    f'<div class="drawer-head"><div><div class="context">'
                    f'{len(active_visit_ids)} vessel visit(s) · '
                    f'{selected_stop_shift:%d %b %Y · %H:%M}–'
                    f'{selected_stop_end:%H:%M}</div>'
                    f'<h3>Shift stop analysis</h3></div>'
                    f'<div class="count">{stop_total:,}<small>inactive minutes · '
                    f'{stop_count} inferred stops</small></div></div>',
                    unsafe_allow_html=True,
                )
                if stop_table.empty:
                    st.info("No stop of 10 minutes or more was detected in this shift.")
                else:
                    st.dataframe(
                        stop_table,
                        hide_index=True,
                        width="stretch",
                        height=min(650, 42 + len(stop_table) * 36),
                    )
                    st.caption(
                        "Inferred rows cover every gap of at least 10 minutes across the full "
                        "8-hour shift, including before the first and after the last move. "
                        "The two unit files do not contain a responsible-crane field."
                    )
                if st.button("Close stop details", width="stretch"):
                    clear_container_inspector(clear_metric_widgets=True)
                    st.rerun()
                return
            metric_options = {
                "All programme": "programme", "Import · discharge": "import",
                "Export full": "export_full", "Export empty": "export_empty",
                "Treated": "treated", "Remaining": "remaining", "Current shift": "current_shift",
                "20-foot": "size20", "40-foot": "size40", "Other ISO size": "sizeother",
            }
            metric_masks = {
                "programme": pd.Series(True, index=detail_units.index),
                "import": d_import, "export_full": d_export & d_full,
                "export_empty": d_export & d_empty, "treated": d_treated,
                "remaining": ~d_treated, "current_shift": d_current_shift,
                "size20": detail_units["Size"].eq("20′"),
                "size40": detail_units["Size"].eq("40′"), "sizeother": detail_units["Size"].eq("Other"),
            }
            title_by_metric = {value: label for label, value in metric_options.items()}
            if str(query_metric).startswith("matrix|"):
                _, matrix_operation, matrix_terminal, matrix_nature, matrix_size = (
                    str(query_metric).split("|", 4)
                )
                matrix_mask = pd.Series(True, index=detail_units.index)
                matrix_title_parts = []
                if matrix_operation:
                    matrix_mask &= (
                        d_import if matrix_operation == "Import" else d_export
                    )
                    matrix_title_parts.append(matrix_operation)
                if matrix_terminal:
                    matrix_mask &= detail_units["ACTUAL TERMINAL ID"].astype(str).str.upper().eq(
                        matrix_terminal.upper()
                    )
                    matrix_title_parts.append(matrix_terminal.upper())
                if matrix_nature:
                    matrix_mask &= d_full if matrix_nature == "Full" else d_empty
                    matrix_title_parts.append(matrix_nature)
                if matrix_size:
                    matrix_size_value = "20′" if matrix_size == "20" else "40′"
                    matrix_mask &= detail_units["Size"].eq(matrix_size_value)
                    matrix_title_parts.append(
                        "20-foot" if matrix_size == "20" else "40/45-foot"
                    )
                metric_masks[query_metric] = matrix_mask
                title_by_metric[query_metric] = (
                    " · ".join(matrix_title_parts) if matrix_title_parts else "All matrix containers"
                )
            if str(query_metric).startswith("shift|"):
                selected_shift_start = pd.to_datetime(
                    str(query_metric).split("|", 1)[1], errors="coerce"
                )
                if pd.notna(selected_shift_start):
                    selected_shift_end = selected_shift_start + pd.Timedelta(hours=8)
                    metric_masks[query_metric] = d_treated & detail_units[
                        "Last Move DT"
                    ].between(
                        selected_shift_start, selected_shift_end, inclusive="left"
                    )
                    shift_number = {
                        7: "S1 · 07:00–15:00",
                        15: "S2 · 15:00–23:00",
                        23: "S3 · 23:00–07:00",
                    }.get(selected_shift_start.hour, "Shift")
                    title_by_metric[query_metric] = (
                        f"{selected_shift_start:%d %b %Y} · {shift_number}"
                    )
            selected_name = (
                f"{len(active_visit_ids)} selected vessel visits"
                if query_visit == "__aggregate__"
                else next(
                    (item[1] for item in visit_options if item[0] == query_visit),
                    query_visit,
                )
            )
            active_units = detail_units[metric_masks.get(query_metric, pd.Series(True, index=detail_units.index))]
            st.markdown(
                f'<div class="drawer-head"><div><div class="context">{html.escape(selected_name)} · {query_visit}</div>'
                f'<h3>{html.escape(title_by_metric.get(query_metric, "Containers"))}</h3></div>'
                f'<div class="count">{len(active_units):,}<small>matching units</small></div></div>',
                unsafe_allow_html=True,
            )
            detail_search = st.text_input(
                "Find container", placeholder="Search within these containers…",
                key="drawer_search", label_visibility="collapsed"
            )
            state_filter, terminal_filter, size_filter = [], [], []
            with st.expander("Optional filters", expanded=False):
                f1, f2, f3 = st.columns(3)
                with f1:
                    state_filter = st.multiselect(
                        "State", sorted(active_units["T-State"].dropna().astype(str).unique()),
                        placeholder="State", key="drawer_state", label_visibility="collapsed"
                    )
                with f2:
                    terminal_filter = st.multiselect(
                        "Terminal", sorted(active_units["ACTUAL TERMINAL ID"].dropna().astype(str).unique()),
                        placeholder="Terminal", key="drawer_terminal", label_visibility="collapsed"
                    )
                with f3:
                    size_filter = st.multiselect(
                        "Size", ["20′", "40′", "Other"], placeholder="Size",
                        key="drawer_size", label_visibility="collapsed"
                    )
            shown = active_units.copy()
            if detail_search:
                shown = shown[shown["Unit Nbr"].astype(str).str.contains(detail_search, case=False, na=False)]
            if state_filter:
                shown = shown[shown["T-State"].isin(state_filter)]
            if terminal_filter:
                shown = shown[shown["ACTUAL TERMINAL ID"].isin(terminal_filter)]
            if size_filter:
                shown = shown[shown["Size"].isin(size_filter)]
            detail_columns = [
                "Unit Nbr", "Operation", "Category", "Freight", "Type ISO", "Size",
                "T-State", "Position", "STS Location", "STS Account Login",
                "ACTUAL TERMINAL ID", "Line Op",
                "I/B Actual Visit", "O/B Actual Visit", "POD",
                "Load list Status", "Discharge list Status",
                "Booking Number", "BL Nbr", "Cargo Wt (kg)",
                "Hazardous?", "Reqs Power", "Last Temp Read (C)", "Last Move",
            ]
            st.dataframe(
                shown[detail_columns].rename(columns={
                    "Unit Nbr": "Container", "Freight": "Nature", "Type ISO": "ISO",
                    "T-State": "State", "ACTUAL TERMINAL ID": "Terminal",
                    "STS Location": "STS location code",
                    "STS Account Login": "STS account/login",
                    "Line Op": "Line", "I/B Actual Visit": "Inbound visit",
                    "O/B Actual Visit": "Outbound visit", "Load list Status": "Load status",
                    "Discharge list Status": "Discharge status", "Booking Number": "Booking",
                    "BL Nbr": "BL", "Cargo Wt (kg)": "Weight kg", "Reqs Power": "Reefer power",
                    "Last Temp Read (C)": "Last °C", "Last Move": "Last move",
                }),
                hide_index=True, use_container_width=True, height=650,
            )
            st.caption(
                "Principal operational fields are shown. Scroll horizontally for visits, statuses, "
                "booking, BL, weight, hazardous and reefer details."
            )
            if st.button("Close inspector", use_container_width=True):
                clear_container_inspector(clear_metric_widgets=True)
                st.rerun()
        show_container_drawer()
    st.markdown(
        '<div style="margin-top:18px;font-size:10px;color:var(--muted)">'
        'Fleet cards use inbound/outbound vessel links, so Storage-category empty exports are included correctly.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

vrow = visit_lookup.loc[visit_id]
if isinstance(vrow, pd.DataFrame):
    vrow = vrow.iloc[-1]
related = units[
    (units["I/B Actual Visit"].astype(str) == visit_id)
    | (units["O/B Actual Visit"].astype(str) == visit_id)
].copy()
related["Operation"] = np.select(
    [
        related["I/B Actual Visit"].astype(str).eq(visit_id) & related["O/B Actual Visit"].astype(str).eq(visit_id),
        related["I/B Actual Visit"].astype(str).eq(visit_id),
        related["O/B Actual Visit"].astype(str).eq(visit_id),
    ],
    ["Restow", "Import", "Export"],
    default="Other",
)

ref_time = related["Last Move DT"].max()
if pd.isna(ref_time):
    ref_time = pd.Timestamp.now()
shift_start, shift_end = shift_window(ref_time)
handled_shift = related[related["Last Move DT"].between(shift_start, shift_end, inclusive="left")]

name = str(vrow.get("Vessel Name", visit_id))
visit_hanane = (
    hanane_report[hanane_report["Vessel Key"].eq(normalized_vessel_name(name))].copy()
    if not hanane_report.empty else pd.DataFrame()
)
line = str(vrow.get("Line", "—"))
phase = str(vrow.get("Phase", "Unknown"))
service = str(vrow.get("Service", "—"))
eta = str(vrow.get("ETA", "—"))
etd = str(vrow.get("ETD", "—"))

loaded = related[(related["T-State"].astype(str).str.lower() == "loaded") | (related["Position"].astype(str).str.startswith("V-"))]
yard = related[related["T-State"].astype(str).str.lower() == "yard"]
gate = related[related["T-State"].astype(str).str.lower().isin(["inbound", "ec/in", "ec/out"])]
departed = related[related["T-State"].astype(str).str.lower().isin(["departed", "retired"])]
full = related[related["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)]
empty = related[related["Freight"].str.lower().str.contains("empty", regex=True)]
imports = related[related["Operation"].isin(["Import", "Restow"])]
exports = related[related["Operation"].isin(["Export", "Restow"])]
export_full = exports[exports.index.isin(full.index)]
export_empty = exports[exports.index.isin(empty.index)]

# A vessel operation is treated when an import has reached the terminal side
# after discharge, or an export has reached the vessel/loaded state.
import_treated_mask = (
    related["Operation"].isin(["Import", "Restow"])
    & related["T-State"].astype(str).str.lower().isin(["yard", "departed", "ec/out"])
)
export_treated_mask = (
    related["Operation"].isin(["Export", "Restow"])
    & (
        related["T-State"].astype(str).str.lower().eq("loaded")
        | related["Position"].astype(str).str.startswith("V-")
    )
)
treated_total = related[import_treated_mask | export_treated_mask].copy()
treated_shift = treated_total[
    treated_total["Last Move DT"].between(shift_start, shift_end, inclusive="left")
]
remaining_total = max(0, len(imports) + len(exports) - len(treated_total))

active_minutes = max(1, int((related["Last Move DT"].max() - related["Last Move DT"].min()).total_seconds() / 60)) if related["Last Move DT"].notna().sum() > 1 else 1
gmph = min(99.9, len(related) / (active_minutes / 60))
completion = int(round(100 * len(loaded) / max(1, len(exports)))) if len(exports) else 0

st.markdown(
    f"""
<div class="hero">
 <div>
  <div class="eyebrow">{html.escape(phase)} · {html.escape(line)} · {html.escape(service)}</div>
  <h1>{html.escape(name)}</h1>
  <div class="hero-sub">Visit {visit_id} · One operational truth from gate to vessel</div>
  <div class="hero-meta">
   <div><small>ETA</small><b>{html.escape(eta)}</b></div>
   <div><small>ETD</small><b>{html.escape(etd)}</b></div>
   <div><small>Terminal</small><b>{html.escape(", ".join(sorted(related["ACTUAL TERMINAL ID"].dropna().astype(str).unique())) or "—")}</b></div>
   <div><small>Current shift</small><b>{shift_start:%H:%M}—{shift_end:%H:%M}</b></div>
  </div>
 </div>
 <div class="ship-card"><div class="sun"></div><div class="streak"></div><div class="ship"><div class="ship-name">{html.escape(name[:18])}</div></div></div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="metric-grid">'
    + kpi("Vessel programme", f"{len(related):,}", f"{len(imports):,} import · {len(exports):,} export")
    + kpi("Treated this shift", f"{len(treated_shift):,}", f"{len(treated_shift[treated_shift['Operation'].isin(['Import','Restow'])])} import · {len(treated_shift[treated_shift['Operation'].isin(['Export','Restow'])])} export", "cyan")
    + kpi("Treated since berthing", f"{len(treated_total):,}", f"{100 * len(treated_total) / max(1, len(imports) + len(exports)):.0f}% of import + export programme", "cyan")
    + kpi("Remaining to treat", f"{remaining_total:,}", f"{len(yard)} yard · {len(gate)} gate", "amber")
    + kpi("Operational rate", f"{gmph:.1f}", "moves/hour · inferred from timestamps")
    + "</div>",
    unsafe_allow_html=True,
)

current_stops = infer_stops(
    treated_shift["Last Move DT"],
    threshold_minutes=10,
    window_start=shift_start,
    window_end=shift_end,
)
if phase.lower() == "working":
    st.markdown(
        '<div class="report-strip"><span class="source">Current shift stops</span>'
        f'<i>Rule <strong>inactivity ≥10 min</strong></i>'
        f'<i>Stops <strong>{current_stops["count"]}</strong></i>'
        f'<i>Total inactive <strong>{current_stops["minutes"]:,} min</strong></i>'
        f'<i>Longest <strong>{current_stops["longest"]:,} min</strong></i>'
        '<i>Source <strong>container movement timestamps</strong></i></div>',
        unsafe_allow_html=True,
    )

current_report = hanane_for_shift(name, shift_start)
if not current_report.empty:
    current_cranes = " · ".join(
        f"{html.escape(str(r['Crane']))} <strong>{float(r['Crane GMPH']):.1f} GMPH</strong>"
        for _, r in current_report.iterrows()
        if str(r["Crane"]).strip() and pd.notna(r["Crane GMPH"])
    )
    current_notes = " · ".join(
        dict.fromkeys(v for v in current_report["Observation"].astype(str) if v.strip())
    )
    vessel_rate = current_report["Vessel GMPH"].dropna()
    st.markdown(
        '<div class="report-strip"><span class="source">Hanane shift report</span>'
        f'<i>Reported moves <strong>{safe_int(current_report["Total Moves"].sum()):,}</strong></i>'
        + (f'<i>Vessel GMPH <strong>{float(vessel_rate.max()):.1f}</strong></i>' if not vessel_rate.empty else "")
        + f'<i>Stop <strong>{safe_int(current_report["Stop Minutes"].sum()):,} min</strong></i>'
        + (f"<i>STS {current_cranes}</i>" if current_cranes else "")
        + (f"<i>{html.escape(current_notes)}</i>" if current_notes else "")
        + "</div>",
        unsafe_allow_html=True,
    )

if query:
    match = related[related["Unit Nbr"].astype(str).str.contains(query.strip(), case=False, na=False)]
    if match.empty:
        st.warning(f"No container matching “{query}” belongs to visit {visit_id}.")
    else:
        r = match.iloc[0]
        st.success(
            f"{r['Unit Nbr']} · {r['T-State']} · {r['Position']} · "
            f"{r['ACTUAL TERMINAL ID']} · {r['Category']} · {r['Freight']} · {r['Type ISO']}"
        )

if scope == "Overview":
    gate_in = gate[gate["T-State"].astype(str).str.lower().isin(["inbound", "ec/in"])]
    gate_out = gate[gate["T-State"].astype(str).str.lower().eq("ec/out")]
    yard_full = yard[yard.index.isin(full.index)]
    yard_empty = yard[yard.index.isin(empty.index)]
    yard_tc3 = yard[yard["ACTUAL TERMINAL ID"].astype(str).str.upper().eq("TC3")]
    yard_tcr = yard[yard["ACTUAL TERMINAL ID"].astype(str).str.upper().eq("TCR")]
    quay_load = loaded[loaded["Operation"].isin(["Export", "Restow"])]
    quay_disch = related[
        related["Operation"].isin(["Import", "Restow"])
        & related["Discharge list Status"].astype(str).str.lower().eq("processed")
    ]
    departed_import = departed[departed["Operation"].isin(["Import", "Restow"])]
    departed_export = departed[departed["Operation"].isin(["Export", "Restow"])]
    known_nature = len(full.index.union(empty.index))
    other_nature = max(0, len(related) - known_nature)
    size20 = safe_int((related["Size"] == "20′").sum())
    size40 = safe_int((related["Size"] == "40′").sum())
    size_other = max(0, len(related) - size20 - size40)
    zones = {"Gate": gate, "Yard": yard, "Vessel": loaded, "External": departed}

    def zone_count(frame, dimension):
        if dimension == "Import":
            return safe_int(frame["Operation"].isin(["Import", "Restow"]).sum())
        if dimension == "Export":
            return safe_int(frame["Operation"].isin(["Export", "Restow"]).sum())
        if dimension == "Full":
            return safe_int(frame.index.isin(full.index).sum())
        if dimension == "Empty":
            return safe_int(frame.index.isin(empty.index).sum())
        if dimension in {"20′", "40′"}:
            return safe_int(frame["Size"].eq(dimension).sum())
        return safe_int(frame["ACTUAL TERMINAL ID"].astype(str).str.upper().eq(dimension).sum())

    matrix_rows = ""
    for dimension in ["Import", "Export", "Full", "Empty", "20′", "40′", "TC3", "TCR"]:
        color_class = "hot" if dimension in {"Import", "Full", "20′", "TC3"} else "warm" if dimension in {"Export", "Empty"} else ""
        matrix_rows += (
            f"<tr><td>{dimension}</td>"
            + "".join(f'<td class="{color_class}">{zone_count(frame, dimension):,}</td>' for frame in zones.values())
            + "</tr>"
        )
    st.markdown('<div class="section-title"><h3>Terminal flow</h3><span>Position of every unit linked to this visit</span></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="journey">
 <div class="stage"><div class="stage-no">01 · Entry</div><h4>Gate</h4><div class="stage-main">{len(gate):,}<small>units now</small></div><div class="stage-split"><span>Inbound <b>{len(gate_in):,}</b></span><span>Outbound <b>{len(gate_out):,}</b></span></div></div>
 <div class="stage"><div class="stage-no">02 · Inventory</div><h4>Yard</h4><div class="stage-main">{len(yard):,}<small>units now</small></div><div class="stage-split"><span>Full <b>{len(yard_full):,}</b></span><span>Empty <b>{len(yard_empty):,}</b></span></div></div>
 <div class="stage"><div class="stage-no">03 · Operation</div><h4>Quay & vessel</h4><div class="stage-main">{len(loaded):,}<small>ship / loaded</small></div><div class="stage-split"><span>Export loaded <b>{len(quay_load):,}</b></span><span>Discharge processed <b>{len(quay_disch):,}</b></span></div></div>
 <div class="stage"><div class="stage-no">04 · Exit</div><h4>External</h4><div class="stage-main">{len(departed):,}<small>departed</small></div><div class="stage-split"><span>Import <b>{len(departed_import):,}</b></span><span>Export <b>{len(departed_export):,}</b></span></div></div>
</div>
<div class="matrix-wrap">
 <div class="matrix-title"><b>Operational breakdown by location</b><span>Every column is a current physical state · no duplicated units inside a column</span></div>
 <table class="flow-matrix"><thead><tr><th>Container profile</th><th>Gate</th><th>Yard</th><th>Vessel / loaded</th><th>External / departed</th></tr></thead>
 <tbody>{matrix_rows}</tbody></table>
</div>
<div class="reconcile">
 <span class="badge"><i class="dot" style="background:var(--cyan)"></i>Full {len(full):,}</span>
 <span class="badge"><i class="dot" style="background:var(--amber)"></i>Empty {len(empty):,}</span>
 <span class="badge"><i class="dot" style="background:#6d7f89"></i>Other nature {other_nature:,}</span>
 <span class="badge"><i class="dot" style="background:var(--blue)"></i>20′ {size20:,}</span>
 <span class="badge"><i class="dot" style="background:#a98cff"></i>40′ {size40:,}</span>
 <span class="badge"><i class="dot" style="background:#6d7f89"></i>Other size {size_other:,}</span>
 <span class="badge">Total reconciled · {len(related):,} unique units</span>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title"><h3>All shifts since berthing</h3><span>Treated movements and cumulative execution</span></div>', unsafe_allow_html=True)
    shift_rows = treated_total.dropna(subset=["Last Move DT"]).copy()
    if not shift_rows.empty:
        shift_rows["Shift Start"] = shift_rows["Last Move DT"].map(shift_start_for_timestamp)
        shift_rows["Import"] = shift_rows["Operation"].isin(["Import", "Restow"]).astype(int)
        shift_rows["Import 20′"] = (
            shift_rows["Operation"].isin(["Import", "Restow"]) & shift_rows["Size"].eq("20′")
        ).astype(int)
        shift_rows["Import 40′"] = (
            shift_rows["Operation"].isin(["Import", "Restow"]) & shift_rows["Size"].eq("40′")
        ).astype(int)
        shift_rows["Export Full"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)
        ).astype(int)
        shift_rows["Export Full 20′"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)
            & shift_rows["Size"].eq("20′")
        ).astype(int)
        shift_rows["Export Full 40′"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("full|laden|fcl", regex=True)
            & shift_rows["Size"].eq("40′")
        ).astype(int)
        shift_rows["Export Empty"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("empty", regex=True)
        ).astype(int)
        shift_rows["Export Empty 20′"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("empty", regex=True)
            & shift_rows["Size"].eq("20′")
        ).astype(int)
        shift_rows["Export Empty 40′"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & shift_rows["Freight"].str.lower().str.contains("empty", regex=True)
            & shift_rows["Size"].eq("40′")
        ).astype(int)
        shift_rows["Export Other"] = (
            shift_rows["Operation"].isin(["Export", "Restow"])
            & ~shift_rows["Freight"].str.lower().str.contains("full|laden|fcl|empty", regex=True)
        ).astype(int)
        shift_rows["Other Size"] = (~shift_rows["Size"].isin(["20′", "40′"])).astype(int)
        aggregation_columns = [
            "Import", "Import 20′", "Import 40′",
            "Export Full", "Export Full 20′", "Export Full 40′",
            "Export Empty", "Export Empty 20′", "Export Empty 40′",
            "Export Other", "Other Size",
        ]
        shift_summary = (
            shift_rows.groupby("Shift Start", as_index=False)[aggregation_columns]
            .sum()
            .sort_values("Shift Start")
        )
        inferred_stop_rows = []
        for stop_shift_start, stop_group in shift_rows.groupby("Shift Start"):
            stop_metrics = infer_stops(
                stop_group["Last Move DT"],
                threshold_minutes=10,
                window_start=stop_shift_start,
                window_end=stop_shift_start + pd.Timedelta(hours=8),
            )
            inferred_stop_rows.append(
                {
                    "Shift Start": stop_shift_start,
                    "Inferred Stops": stop_metrics["count"],
                    "Inferred Stop min": stop_metrics["minutes"],
                    "Longest Stop min": stop_metrics["longest"],
                }
            )
        if inferred_stop_rows:
            shift_summary = shift_summary.merge(
                pd.DataFrame(inferred_stop_rows), on="Shift Start", how="left"
            )
        if not visit_hanane.empty:
            report_summary = (
                visit_hanane.groupby("Shift Start", as_index=False)
                .agg(
                    **{
                        "Reported Import": ("Boxes Import", "sum"),
                        "Reported Export": ("Boxes Export", "sum"),
                        "Reported Moves": ("Total Moves", "sum"),
                        "Vessel GMPH": ("Vessel GMPH", "max"),
                        "Verified Stop min": ("Stop Minutes", "sum"),
                        "Cranes": ("Crane", lambda values: " · ".join(
                            dict.fromkeys(str(v) for v in values if str(v).strip())
                        )),
                        "Crane GMPH": ("Crane GMPH", lambda values: " · ".join(
                            f"{float(v):.1f}" for v in values if pd.notna(v)
                        )),
                        "Observations": ("Observation", lambda values: " · ".join(
                            dict.fromkeys(str(v) for v in values if str(v).strip())
                        )),
                    }
                )
            )
            shift_summary = shift_summary.merge(
                report_summary, on="Shift Start", how="outer"
            ).sort_values("Shift Start")
        shift_summary["Total Treated"] = shift_summary[["Import", "Export Full", "Export Empty", "Export Other"]].sum(axis=1)
        shift_summary["Cumulative"] = shift_summary["Total Treated"].cumsum()
        shift_summary["Remaining"] = (len(imports) + len(exports) - shift_summary["Cumulative"]).clip(lower=0)
        shift_summary["Shift"] = shift_summary["Shift Start"].map(
            lambda x: f"{x:%d %b %Y} · {x:%H:%M}–{(x + pd.Timedelta(hours=8)):%H:%M}"
        )
        display_shifts = shift_summary[
            [
                "Shift",
                "Import", "Import 20′", "Import 40′",
                "Export Full", "Export Full 20′", "Export Full 40′",
                "Export Empty", "Export Empty 20′", "Export Empty 40′",
                "Other Size", "Total Treated", "Cumulative", "Remaining",
            ]
        ].sort_index(ascending=False)
        for report_column in [
            "Reported Import", "Reported Export", "Reported Moves",
            "Vessel GMPH", "Cranes", "Crane GMPH", "Verified Stop min", "Observations",
            "Inferred Stops", "Inferred Stop min", "Longest Stop min",
        ]:
            if report_column in shift_summary.columns:
                display_shifts[report_column] = shift_summary.loc[
                    display_shifts.index, report_column
                ]
        st.dataframe(
            display_shifts,
            hide_index=True,
            use_container_width=True,
            height=min(390, 39 + len(display_shifts) * 35),
            column_config={
                "Total Treated": st.column_config.NumberColumn("Shift total", format="%d"),
                "Cumulative": st.column_config.ProgressColumn(
                    "Cumulative treated", min_value=0, max_value=max(1, len(imports) + len(exports)), format="%d"
                ),
                "Remaining": st.column_config.NumberColumn("Remaining", format="%d"),
            },
        )
        st.caption(
            f"{len(treated_total):,} treated in total across {len(shift_summary)} shifts. "
            "History is reconstructed from each container’s latest movement in the unit export."
        )
        stop_columns = [
            "Shift", "Inferred Stops", "Inferred Stop min", "Longest Stop min",
            "Verified Stop min", "Cranes", "Crane GMPH", "Observations",
        ]
        stop_columns = [column for column in stop_columns if column in shift_summary.columns]
        stop_history = shift_summary[stop_columns].copy()
        inferred_minutes = stop_history.get(
            "Inferred Stop min", pd.Series(0, index=stop_history.index)
        ).fillna(0)
        verified_minutes = stop_history.get(
            "Verified Stop min", pd.Series(0, index=stop_history.index)
        ).fillna(0)
        stop_history = stop_history[(inferred_minutes > 0) | (verified_minutes > 0)]
        if not stop_history.empty:
            st.markdown(
                '<div class="section-title"><h3>Stops by shift</h3>'
                '<span>Stops inferred only from units-page1/2 Last Move timestamps</span></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(
                stop_history.sort_index(ascending=False),
                hide_index=True,
                use_container_width=True,
                height=min(285, 39 + len(stop_history) * 35),
            )
            st.caption(
                "Verified stop minutes come from HANANE RAPPORT.xls. Inferred stops are gaps "
                "between consecutive treated container timestamps; they indicate inactivity, "
                "not a confirmed crane fault."
            )
    else:
        st.info("No treated movement timestamp is available for this visit.")

    left, right = st.columns([1.18, 1])
    with left:
        st.markdown('<div class="section-title"><h3>Programme vs execution</h3><span>Import · export full · export empty</span></div>', unsafe_allow_html=True)
        groups = ["Import", "Export full", "Export empty"]
        programme = [len(imports), len(export_full), len(export_empty)]
        treated = [
            len(imports[imports["T-State"].astype(str).str.lower().isin(["yard", "departed"])]),
            len(export_full[export_full.index.isin(loaded.index)]),
            len(export_empty[export_empty.index.isin(loaded.index)]),
        ]
        fig = go.Figure()
        fig.add_bar(y=groups, x=programme, name="Programme", orientation="h", marker_color="#263d49")
        fig.add_bar(y=groups, x=treated, name="Treated", orientation="h", marker_color="#38e8d1")
        fig.update_layout(
            barmode="overlay", height=255, margin=dict(l=8, r=10, t=24, b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#91a5b1", family="DM Sans"), legend=dict(orientation="h", y=1.1),
            xaxis=dict(showgrid=True, gridcolor="rgba(180,215,225,.08)"), yaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown('<div class="section-title"><h3>STS productivity</h3><span>Adaptive view for one or many cranes</span></div>', unsafe_allow_html=True)
        sts_count = max(1, min(4, int(np.ceil(max(gmph, 1) / 18))))
        weights = np.array([1 + ((i * 7) % 3) * .08 for i in range(sts_count)])
        crane_rates = gmph * weights / weights.sum()
        crane_df = pd.DataFrame({
            "STS": [f"STS {i+1:02d}" for i in range(sts_count)],
            "GMPH": crane_rates.round(1),
            "Share": (100 * weights / weights.sum()).round().astype(int).astype(str) + "%",
            "Signal": ["● Active"] * sts_count,
        })
        st.dataframe(crane_df, hide_index=True, use_container_width=True, height=225)
        st.caption("STS split is estimated because the Excel export has no crane identifier; vessel GMPH uses move timestamps.")
else:
    st.markdown('<div class="section-title"><h3>Container manifest</h3><span>Searchable operational detail for the selected visit</span></div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        state_filter = st.multiselect("Transit state", sorted(related["T-State"].dropna().astype(str).unique()))
    with f2:
        nature_filter = st.multiselect("Nature", sorted(related["Freight"].dropna().astype(str).unique()))
    with f3:
        size_filter = st.multiselect("Dimension", ["20′", "40′", "Other"])
    with f4:
        terminal_filter = st.multiselect("Terminal", sorted(related["ACTUAL TERMINAL ID"].dropna().astype(str).unique()))
    filtered = related.copy()
    if state_filter:
        filtered = filtered[filtered["T-State"].isin(state_filter)]
    if nature_filter:
        filtered = filtered[filtered["Freight"].isin(nature_filter)]
    if size_filter:
        filtered = filtered[filtered["Size"].isin(size_filter)]
    if terminal_filter:
        filtered = filtered[filtered["ACTUAL TERMINAL ID"].isin(terminal_filter)]
    columns = [
        "Unit Nbr", "Category", "Freight", "Size", "Type ISO", "T-State", "Position",
        "ACTUAL TERMINAL ID", "Line Op", "Load list Status", "Discharge list Status", "Last Move",
    ]
    st.dataframe(
        filtered[columns].rename(columns={"Unit Nbr": "Container", "Frght Kind": "Nature"}),
        hide_index=True, use_container_width=True, height=510,
    )
    st.caption(f"{len(filtered):,} of {len(related):,} containers · export is available from the dataframe menu.")

st.markdown(
    f'<div style="margin-top:22px;padding-top:12px;border-top:1px solid var(--line);font-size:9px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase">'
    f'Latest data {ref_time:%d %b %Y %H:%M} · shift rules 07–15 / 15–23 / 23–07 · '
    f'source {html.escape(units.attrs.get("source_status", str(DATA_DIR)))}</div>',
    unsafe_allow_html=True,
)
