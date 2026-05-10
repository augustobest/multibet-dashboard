# dashboard_meta.py — Multibet Meta Ads + Smartico Dashboard

import math
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from collections import defaultdict

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

st.set_page_config(
    page_title="Multibet — Meta Ads Dashboard",
    page_icon="🎯",
    layout="wide",
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
SMARTICO_URL  = "https://boapi3.smartico.ai"
SMARTICO_KEY  = st.secrets.get("SMARTICO_KEY", "60d30870-42fa-11f1-85e6-027e66b7665d-12072")
AFFILIATE_ID  = 464673

META_ACCESS_TOKEN = st.secrets.get("META_ACCESS_TOKEN", "EAASFqlKv054BRQredZAPZBOVxA3ztZBZC8C8ZB5oV0ZC1G9qGZB3YzFRZAXWnW6WtwhjYne3bdoO8Afo19en1tMrijMwF6h1mzwplbWwn6R0etsboWyJHqdeUzlWBS09DQjXQd6ttSJ6SW9wTCSK60ZCXnwa3vvhNaBmUKTy30XciUOg6EsrgTGrMayz6AgignNfondWM")
META_AD_ACCOUNT_IDS = [
    "act_1418521646228655",   # Multibet
    "act_3506962756106082",   # Multibet
    "act_1531679918112645",   # Multibet Verified
    "act_1282215803969842",   # Multibet Verified 3
    "act_4397365763819913",   # Multibet Verified 4
    "act_26153688877615850",  # Multibet Verified 5
]
META_API_VERSION = "v19.0"
REFRESH_MIN  = 30
DEFAULT_DAYS = 15

# Campanha Meta → UTMs no Smartico
META_CAMPAIGN_UTM_MAP: dict[str, list[str]] = {
    "Deposite e ganhe ROAS":                          ["modal-dep-100"],
    "Deposite e ganhe Motions":                       ["modal-dep-100-motion"],
    "Mini Games Motion":                              ["caixas", "raspadinha"],
    "Mini Games Roleta estáticos":                    ["roleta-dep-50"],
    "Mini Games Roleta estáticos — Cópia":            ["roleta-dep-50"],
    "Mini Games Roleta estáticos — Cópia — Cópia":    ["roleta-dep-50"],
    "Mini Games":                                     ["roleta-dep-50"],
    "Mini Game":                                      ["roleta-dep-50"],
    "Mini games 2":                                   ["roleta-dep-50"],
    "Mini games Raspadinha":                          ["raspadinha"],
    "Mini games Raspadinha — Cópia":                  ["raspadinha"],
    "Mini Games caixa":                               ["caixas"],
    "Mini Games Videos Lara":                         ["Lara5reais"],
    "Thiago ODD Domingo":                             ["AD1_ThiagoVascoagama", "AD1_ThiagoPalmeirasvsAthet"],
    "Estático Vasco":                                 ["estaticocaiovasco"],
    "CBO - ROLETA - MINI GAMES 08/07":                ["roleta-dep-50"],
    "Ale Sports":                                     ["AD1_Ale1005"],
    "CBO - ASSINATURA - RMKT":                        [],
    "Josiasbr":                                       ["AD1_JosiasGaloodd13", "AD2_JosiasAlemanha",
                                                       "AD1_JosiasAlemanha1"],
    "RMK Meta Sport":                                 [],
    "Remarketing Google":                             [],
    "Venda Sports ODD10 Cruxcat":                     ["AD1_Estaticocaiocru"],
    "Ale Galo ODD 13":                                [],
    "Ale":                                            ["AD1_Ale0605", "AD1_Ale1005"],
    "Brabo+Multi Odds":                               ["Braboflaodd10", "brabocru", "brabovasco"],
    "Lead AFF — Cópia":                               [],
}

# UTMs do Smartico que devem ser mescladas sob uma chave canônica
SM_AGGREGATE: dict[str, list[str]] = {
    "modal-dep-100": ["modal-dep-100", "modal-dep-100-roas"],
    "raspadinha":    ["raspadinha-dep-100", "raspadinha-dep-50"],
    "caixas":        ["caixas-dep-50"],
}

# Ações já resolvidas (não re-alertar)
RESOLVED_ACTIONS: list[dict] = []

# ─────────────────────────────────────────────
# CSS BRAND
# ─────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@300;400;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Montserrat', sans-serif !important;
    background-color: #160d30;
    color: #ffffff;
}
h1 { font-family: 'Anton', sans-serif !important; text-transform: uppercase; color: #f7f716 !important; }
h2, h3 { font-family: 'Montserrat', sans-serif !important; font-weight: 700; color: #d4b8ff !important; }

.metric-card {
    background: #2d1a6e;
    border: 1px solid #5f12ff;
    border-radius: 10px;
    padding: 14px 10px;
    text-align: center;
    margin-bottom: 8px;
}
.metric-label {
    color: #d4b8ff;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}
.metric-value {
    color: #f7f716;
    font-size: 1.35rem;
    font-weight: 900;
}

section[data-testid="stSidebar"] {
    background-color: #201148 !important;
    border-right: 1px solid #5f12ff;
}

[data-testid="stExpander"] {
    border: 1px solid #5f12ff !important;
    background: #2d1a6e !important;
    border-radius: 8px;
}
hr { border-color: #5f12ff !important; }

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #d4b8ff;
    font-weight: 700;
}
.stTabs [aria-selected="true"] {
    background: rgba(95,18,255,0.2) !important;
    border-bottom: 3px solid #f7f716 !important;
    color: #f7f716 !important;
}
div[data-testid="metric-container"] {
    background: #2d1a6e;
    border: 1px solid #5f12ff;
    border-radius: 10px;
    padding: 12px;
}
div[data-testid="metric-container"] label { color: #d4b8ff; }
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #f7f716;
    font-weight: 900;
}

/* Dataframe / tabela */
[data-testid="stDataFrame"] iframe {
    background-color: #160d30 !important;
}
[data-testid="stDataFrame"] > div {
    background-color: #160d30 !important;
}
.stDataFrame, .stDataFrame > div, .stDataFrame iframe {
    background-color: #160d30 !important;
}
</style>
"""

PLOTLY_LAYOUT = dict(
    plot_bgcolor="#201148",
    paper_bgcolor="#201148",
    font=dict(color="#ffffff", family="Montserrat"),
    xaxis=dict(gridcolor="#2d1a6e", linecolor="#5f12ff"),
    yaxis=dict(gridcolor="#2d1a6e", linecolor="#5f12ff"),
    legend=dict(bgcolor="#2d1a6e", bordercolor="#5f12ff"),
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def brl(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def pct(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "—"
    return f"{v:.2f}%"

def _sm_num(row, key):
    return float(row.get(key) or 0)

# ─────────────────────────────────────────────
# SMARTICO FETCH
# ─────────────────────────────────────────────
@st.cache_data(ttl=REFRESH_MIN * 60)
def _smartico_get(url: str) -> list:
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"authorization": SMARTICO_KEY}, timeout=60)
            return r.json().get("data") or []
        except Exception as e:
            if attempt == 2:
                st.error(f"Erro Smartico: {e}")
                return []


def fetch_smartico(date_from_str: str, date_to_str: str) -> dict:
    dt_to = (datetime.strptime(date_to_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"{SMARTICO_URL}/api/af2_media_report_op"
        f"?aggregation_period=DAY"
        f"&date_from={date_from_str}"
        f"&date_to={dt_to}"
        f"&affiliate_id={AFFILIATE_ID}"
        f"&group_by=utm_campaign"
    )
    data = _smartico_get(url)
    if data is None:
        return {}

    result: dict = defaultdict(lambda: defaultdict(float))
    for row in data:
        utm = row.get("utm_campaign") or "(sem_utm)"
        for canon, variants in SM_AGGREGATE.items():
            if utm in variants:
                utm = canon
                break
        for key in ["registration_count", "ftd_count", "ftd_total", "deposit_count",
                    "deposit_total", "net_deposits", "net_pl", "net_pl_casino",
                    "net_pl_sport", "withdrawal_count", "withdrawal_total",
                    "bonus_amount", "volume", "commissions_total", "visit_count"]:
            result[utm][key] += _sm_num(row, key)
    return dict(result)


@st.cache_data(ttl=REFRESH_MIN * 60)
def fetch_smartico_daily(date_from_str: str, date_to_str: str) -> pd.DataFrame:
    dt_to = (datetime.strptime(date_to_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"{SMARTICO_URL}/api/af2_media_report_op"
        f"?aggregation_period=DAY"
        f"&date_from={date_from_str}"
        f"&date_to={dt_to}"
        f"&affiliate_id={AFFILIATE_ID}"
        f"&group_by=utm_campaign"
    )
    data = _smartico_get(url)
    if not data:
        return pd.DataFrame()

    rows = []
    for row in data:
        utm = row.get("utm_campaign") or "(sem_utm)"
        for canon, variants in SM_AGGREGATE.items():
            if utm in variants:
                utm = canon
                break
        rows.append({
            "data":        row.get("dt", "")[:10],
            "utm":         utm,
            "ftds":        _sm_num(row, "ftd_count"),
            "regs":        _sm_num(row, "registration_count"),
            "net_pl":      _sm_num(row, "net_pl"),
            "net_deposits":_sm_num(row, "net_deposits"),
            "deposits":    _sm_num(row, "deposit_total"),
            "comm_total":  _sm_num(row, "commissions_total"),
            "bonus":       _sm_num(row, "bonus_amount"),
            "ftd_total":   _sm_num(row, "ftd_total"),
        })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["data"] = pd.to_datetime(df["data"])
    return df.groupby(["data", "utm"], as_index=False).sum(numeric_only=True)


@st.cache_data(ttl=REFRESH_MIN * 60)
def fetch_utm_activity_monitor(lookback_days: int = 90) -> pd.DataFrame:
    dt_from = (datetime.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    dt_to   = datetime.today().strftime("%Y-%m-%d")
    return fetch_smartico_daily(dt_from, dt_to)


# ─────────────────────────────────────────────
# META FETCH
# ─────────────────────────────────────────────
def _meta_get(path: str, params: dict) -> list[dict]:
    base = f"https://graph.facebook.com/{META_API_VERSION}/{path}"
    params = dict(params)
    params["access_token"] = META_ACCESS_TOKEN
    params["limit"] = 500
    results = []
    url: str | None = base
    first = True
    while url:
        try:
            r = requests.get(url, params=params if first else None, timeout=30)
            body = r.json()
        except Exception as e:
            st.error(f"Erro Meta API: {e}")
            break
        results.extend(body.get("data") or [])
        url = body.get("paging", {}).get("next")
        first = False
    return results


@st.cache_data(ttl=REFRESH_MIN * 60)
def fetch_meta_insights(date_from_str: str, date_to_str: str) -> list[dict]:
    all_rows = []
    for account_id in META_AD_ACCOUNT_IDS:
        rows = _meta_get(
            f"{account_id}/insights",
            {
                "fields": "campaign_name,adset_name,impressions,clicks,spend,ctr,cpc,reach,frequency,actions",
                "time_range": f'{{"since":"{date_from_str}","until":"{date_to_str}"}}',
                "level": "adset",
            },
        )
        all_rows.extend(rows)
    return all_rows


@st.cache_data(ttl=REFRESH_MIN * 60)
def fetch_meta_campaigns() -> dict[str, dict]:
    result = {}
    for account_id in META_AD_ACCOUNT_IDS:
        rows = _meta_get(
            f"{account_id}/campaigns",
            {
                "fields": "name,status,daily_budget,lifetime_budget,objective",
                "effective_status": '["ACTIVE","PAUSED"]',
            },
        )
        for c in rows:
            budget = None
            if c.get("daily_budget"):
                budget = float(c["daily_budget"]) / 100
            elif c.get("lifetime_budget"):
                budget = float(c["lifetime_budget"]) / 100
            result[c["name"]] = {
                "budget": budget,
                "status": "Ativa" if c.get("status") == "ACTIVE" else "Pausada",
                "objective": c.get("objective", ""),
            }
    return result


@st.cache_data(ttl=REFRESH_MIN * 60)
def fetch_meta_daily(date_from_str: str, date_to_str: str) -> pd.DataFrame:
    all_rows = []
    for account_id in META_AD_ACCOUNT_IDS:
        rows = _meta_get(
            f"{account_id}/insights",
            {
                "fields": "campaign_name,spend,clicks,date_start",
                "time_range": f'{{"since":"{date_from_str}","until":"{date_to_str}"}}',
                "level": "campaign",
                "time_increment": "1",
            },
        )
        all_rows.extend(rows)
    if not all_rows:
        return pd.DataFrame()
    rows_clean = []
    for row in all_rows:
        camp = row.get("campaign_name", "")
        utm_list = META_CAMPAIGN_UTM_MAP.get(camp, [camp])
        utm = utm_list[0] if utm_list else camp
        rows_clean.append({
            "data":    pd.to_datetime(row.get("date_start", "")),
            "utm":     utm,
            "custo":   float(row.get("spend") or 0),
            "cliques": int(row.get("clicks") or 0),
        })
    df = pd.DataFrame(rows_clean)
    return df.groupby(["data", "utm"], as_index=False).sum(numeric_only=True)


# ─────────────────────────────────────────────
# RECONCILIATION
# ─────────────────────────────────────────────
def reconcile(sm: dict, meta: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Agrupa por UTM individual. Cada campanha aporta gasto INTEIRO em todas
    # as UTMs que ela mapeia. Quando várias campanhas compartilham uma UTM,
    # o gasto soma. FTDs vêm da Smartico (uma vez por UTM, sem dupla contagem).
    # Primeiro acumula por campanha (insights vêm a nível de adset)
    camp_agg: dict[str, dict] = defaultdict(lambda: {
        "spend": 0.0, "impressions": 0, "clicks": 0, "reach": 0,
        "frequency_sum": 0.0, "frequency_count": 0,
    })
    for row in meta:
        camp = row.get("campaign_name", "")
        c = camp_agg[camp]
        c["spend"]       += float(row.get("spend") or 0)
        c["impressions"] += int(row.get("impressions") or 0)
        c["clicks"]      += int(row.get("clicks") or 0)
        c["reach"]       += int(row.get("reach") or 0)
        if row.get("frequency"):
            c["frequency_sum"]   += float(row["frequency"])
            c["frequency_count"] += 1

    # Agora distribui gasto INTEIRO de cada campanha pra cada UTM mapeada
    utm_agg: dict[str, dict] = defaultdict(lambda: {
        "spend": 0.0, "impressions": 0, "clicks": 0, "reach": 0,
        "frequency_sum": 0.0, "frequency_count": 0,
        "campaigns": set(),
    })
    for camp, c in camp_agg.items():
        utms = META_CAMPAIGN_UTM_MAP.get(camp, [camp])
        if not utms:
            utms = ["(sem_utm)"]
        for u in utms:
            agg = utm_agg[u]
            agg["campaigns"].add(camp)
            agg["spend"]       += c["spend"]
            agg["impressions"] += c["impressions"]
            agg["clicks"]      += c["clicks"]
            agg["reach"]       += c["reach"]
            agg["frequency_sum"]   += c["frequency_sum"]
            agg["frequency_count"] += c["frequency_count"]

    matched_utms: set[str] = set()
    rows_main = []

    for utm, agg in utm_agg.items():
        if utm == "(sem_utm)": continue
        camps_list = sorted(agg["campaigns"])
        if len(camps_list) == 1:
            camp = camps_list[0]
        else:
            camp = f"{camps_list[0]} (+{len(camps_list)-1})"

        spend = agg["spend"]
        # UTM mapeada mas sem gasto Meta no período = atribuição residual
        # (anúncio pausado/deletado, FTD atrasado). Pula a tabela principal
        # e deixa cair na seção "sem match Meta" abaixo, junto das outras
        # UTMs sem custo — assim o CPA da tabela principal fica limpo.
        if spend <= 0:
            continue

        matched_utms.add(utm)

        smd = sm.get(utm, {})
        sm_ftds          = smd.get("ftd_count", 0)
        sm_regs          = smd.get("registration_count", 0)
        sm_ftd_total     = smd.get("ftd_total", 0)
        sm_net_pl        = smd.get("net_pl", 0)
        sm_net_pl_casino = smd.get("net_pl_casino", 0)
        sm_net_pl_sport  = smd.get("net_pl_sport", 0)
        sm_net_deposits  = smd.get("net_deposits", 0)
        sm_deposits      = smd.get("deposit_total", 0)
        sm_bonus         = smd.get("bonus_amount", 0)
        sm_comm          = smd.get("commissions_total", 0)

        impr  = int(agg["impressions"])
        clicks = int(agg["clicks"])
        freq  = agg["frequency_sum"] / agg["frequency_count"] if agg["frequency_count"] > 0 else None

        cpa_real    = spend / sm_ftds if sm_ftds > 0 and spend > 0 else None
        roas_net_pl = sm_net_pl / spend if spend > 0 else None
        roas_dep    = sm_deposits / spend if spend > 0 else None
        ctr         = clicks / impr * 100 if impr > 0 else None
        cpc         = spend / clicks if clicks > 0 else None

        rows_main.append({
            "Campanha Meta":        camp,
            "UTM Campaign":         utm,
            "Investido (R$)":       spend,
            "Impressões":           impr,
            "Cliques":              clicks,
            "CTR (%)":              ctr,
            "CPC (R$)":             cpc,
            "Alcance":              int(agg["reach"]),
            "Frequência":           freq,
            "Registros":            int(sm_regs),
            "FTDs":                 int(sm_ftds),
            "FTD Valor (R$)":       sm_ftd_total,
            "Net Deposits (R$)":    sm_net_deposits,
            "Net PL (R$)":          sm_net_pl,
            "Net PL Casino (R$)":   sm_net_pl_casino,
            "Net PL Sport (R$)":    sm_net_pl_sport,
            "Depósitos Bruto (R$)": sm_deposits,
            "Bônus (R$)":           sm_bonus,
            "Comissão (R$)":        sm_comm,
            "CPA Real (R$)":        cpa_real,
            "ROAS Net PL":          roas_net_pl,
            "ROAS Dep Amount":      roas_dep,
            "ROI":                  roas_net_pl,
        })

    unmatched = []
    for utm, data in sm.items():
        if utm not in matched_utms and utm != "(sem_utm)":
            sm_ftds      = int(data.get("ftd_count", 0))
            sm_net_pl    = data.get("net_pl", 0)
            sm_deposits  = data.get("deposit_total", 0)
            rows_main.append({
                "Campanha Meta":        "— (sem match Meta)",
                "UTM Campaign":         utm,
                "Investido (R$)":       0.0,
                "Impressões":           0,
                "Cliques":              0,
                "CTR (%)":              None,
                "CPC (R$)":             None,
                "Alcance":              0,
                "Frequência":           None,
                "Registros":            int(data.get("registration_count", 0)),
                "FTDs":                 sm_ftds,
                "FTD Valor (R$)":       data.get("ftd_total", 0),
                "Net Deposits (R$)":    data.get("net_deposits", 0),
                "Net PL (R$)":          sm_net_pl,
                "Net PL Casino (R$)":   data.get("net_pl_casino", 0),
                "Net PL Sport (R$)":    data.get("net_pl_sport", 0),
                "Depósitos Bruto (R$)": sm_deposits,
                "Bônus (R$)":           data.get("bonus_amount", 0),
                "Comissão (R$)":        data.get("commissions_total", 0),
                "CPA Real (R$)":        None,
                "ROAS Net PL":          None,
                "ROAS Dep Amount":      None,
                "ROI":                  None,
            })
            unmatched.append({
                "UTM Smartico":   utm,
                "Registros":      int(data.get("registration_count", 0)),
                "FTDs":           sm_ftds,
                "Net PL (R$)":    sm_net_pl,
                "Depósitos (R$)": sm_deposits,
            })

    df_main = pd.DataFrame(rows_main) if rows_main else pd.DataFrame()
    df_unm  = pd.DataFrame(unmatched) if unmatched else pd.DataFrame()
    return df_main, df_unm


def build_unified_utm_table(df: pd.DataFrame, budgets: dict) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    def _status(row):
        camp = row["Campanha Meta"]
        spend = row.get("Investido (R$)", 0) or 0
        # Campanhas agrupadas (com "(+N)") ou que tiveram gasto no período → Ativa
        if "(+" in str(camp) or spend > 0:
            return "Ativa"
        return budgets.get(camp, {}).get("status", "—")

    df["Status"]           = df.apply(_status, axis=1)
    df["Orçamento Diário"] = df["Campanha Meta"].map(lambda c: budgets.get(c, {}).get("budget"))
    df["Status"] = df["Status"].fillna("—")
    return df


def build_utm_monitor(df_activity: pd.DataFrame, active_utms: set, lookback_days: int) -> pd.DataFrame:
    today = datetime.today().date()
    all_utms = active_utms | (set(df_activity["utm"].unique()) if not df_activity.empty else set())
    all_utms.discard("(sem_utm)")
    rows = []

    for utm in sorted(all_utms):
        df_utm = df_activity[df_activity["utm"] == utm] if not df_activity.empty else pd.DataFrame()
        has_regs = not df_utm.empty and df_utm["regs"].sum() > 0

        if has_regs:
            last_seen = pd.to_datetime(df_utm[df_utm["regs"] > 0]["data"].max()).date()
            days_silent = (today - last_seen).days
        else:
            last_seen = None
            days_silent = lookback_days + 1

        if days_silent == 0:
            status = "🟢 Ativa hoje"
        elif days_silent <= 7:
            status = "🟢 Ativa"
        elif days_silent <= 14:
            status = "🟡 Monitorar"
        elif days_silent <= 30:
            status = "🟠 Em Risco"
        elif last_seen:
            status = "🔴 Parada"
        else:
            status = "⚫ Nunca recebeu"

        def sum_regs(days):
            if df_utm.empty:
                return 0
            return int(df_utm[df_utm["data"] >= pd.Timestamp(today - timedelta(days=days))]["regs"].sum())

        def sum_ftds(days):
            if df_utm.empty:
                return 0
            return int(df_utm[df_utm["data"] >= pd.Timestamp(today - timedelta(days=days))]["ftds"].sum())

        rows.append({
            "UTM":               utm,
            "Status":            status,
            "Último Cadastro":   last_seen.strftime("%d/%m/%Y") if last_seen else "—",
            "Dias sem cadastro": str(days_silent) if has_regs else "—",
            "Cadastros 7d":      sum_regs(7),
            "Cadastros 30d":     sum_regs(30),
            "FTDs 30d":          sum_ftds(30),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def generate_conclusions(df: pd.DataFrame) -> tuple[list, list]:
    conclusions, actions = [], []
    if df.empty:
        return conclusions, actions

    total_spend  = df["Investido (R$)"].sum()
    total_net_pl = df["Net PL (R$)"].sum()
    total_ftds   = df["FTDs"].sum()
    total_roas   = total_net_pl / total_spend if total_spend > 0 else 0

    if total_roas >= 1.0:
        conclusions.append(("✅", f"Conta lucrativa no período — ROAS geral {total_roas:.2f}x"))
    elif total_roas >= 0.4:
        conclusions.append(("🟡", f"Abaixo do break-even — ROAS geral {total_roas:.2f}x"))
    else:
        conclusions.append(("🔴", f"Operando no prejuízo — ROAS geral {total_roas:.2f}x"))

    for _, row in df.iterrows():
        spend  = row["Investido (R$)"]
        ftds   = row["FTDs"]
        net_pl = row["Net PL (R$)"]
        cpa    = row["CPA Real (R$)"]
        roas   = row["ROAS Net PL"]
        camp   = row["Campanha Meta"]

        if spend > 3000 and ftds == 0:
            conclusions.append(("🔴", f"Tracking possivelmente quebrado em **{camp}** — {brl(spend)} sem FTDs"))
            actions.append(("🔴 Urgente", f"Verificar pixel/tracking de **{camp}**"))
        elif net_pl is not None and net_pl < -1000 and spend > 3000:
            conclusions.append(("🔴", f"Prejuízo em **{camp}** — Net PL {brl(net_pl)}"))
            actions.append(("🟠 Alta", f"Revisar criativos e segmentação de **{camp}**"))
        elif cpa is not None and cpa > 3000:
            conclusions.append(("🟡", f"CPA alto em **{camp}** — CPA {brl(cpa)}"))
            actions.append(("🟡 Média", f"Otimizar audiência de **{camp}** (CPA {brl(cpa)})"))
        elif roas is not None and roas >= 1.0 and spend > 0:
            conclusions.append(("✅", f"Oportunidade de escala em **{camp}** — ROAS {roas:.2f}x"))
            actions.append(("🟢 Oportunidade", f"Aumentar budget de **{camp}** — ROAS {roas:.2f}x"))

    return conclusions, actions


# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
def main():
    st.markdown(CSS, unsafe_allow_html=True)

    if HAS_AUTOREFRESH:
        st_autorefresh(interval=REFRESH_MIN * 60 * 1000)

    # ── HEADER ──────────────────────────────────
    st.markdown("<h1>Multibet — Meta Ads Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#d4b8ff;margin-top:-12px;margin-bottom:8px'>Meta Ads + Smartico | Análise de Performance</p>", unsafe_allow_html=True)
    st.divider()

    # ── SIDEBAR ──────────────────────────────────
    with st.sidebar:
        st.markdown("<h2 style='color:#f7f716'>⚙️ Filtros</h2>", unsafe_allow_html=True)
        today = datetime.today().date()
        default_from = today

        date_range = st.date_input("Período", value=(default_from, today), max_value=today)
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            date_from, date_to = date_range
        else:
            date_from, date_to = default_from, today

        st.caption(f"🔄 Auto-refresh a cada {REFRESH_MIN} min")
        st.divider()
        if st.button("🔄 Forçar atualização"):
            st.cache_data.clear()
            st.rerun()

    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str   = date_to.strftime("%Y-%m-%d")
    date_label    = f"{date_from.strftime('%d/%m/%Y')} → {date_to.strftime('%d/%m/%Y')}"

    # ── FETCH DATA ──────────────────────────────
    with st.spinner("Carregando dados..."):
        sm_data          = fetch_smartico(date_from_str, date_to_str)
        meta_insights    = fetch_meta_insights(date_from_str, date_to_str)
        campaign_budgets = fetch_meta_campaigns()
        df_main, df_unmatched = reconcile(sm_data, meta_insights)
        df_unified = build_unified_utm_table(df_main, campaign_budgets)

    # ── KPIs ──────────────────────────────────
    # Custo Total = soma direta dos insights Meta (sem inflar por UTMs duplicadas)
    total_spend = sum(float(r.get("spend") or 0) for r in meta_insights)
    # Net PL e depósitos = soma direta do Smartico (sem inflar)
    total_net_pl   = sum(v.get("net_pl", 0) for v in sm_data.values())
    total_net_dep  = sum(v.get("net_deposits", 0) for v in sm_data.values())
    total_deposits = sum(v.get("deposit_total", 0) for v in sm_data.values())
    total_regs     = sum(v.get("registration_count", 0) for v in sm_data.values())
    total_ftds     = df_unified["FTDs"].sum() if not df_unified.empty else 0
    cpa_real       = total_spend / total_ftds if total_ftds > 0 and total_spend > 0 else None
    roas_val       = total_net_pl / total_spend if total_spend > 0 else None

    # FTDs totais direto do Smartico (todas as UTMs, sem filtro Meta)
    sm_total_ftds  = int(sum(v.get("ftd_count", 0) for v in sm_data.values()))
    sm_total_regs  = int(sum(v.get("registration_count", 0) for v in sm_data.values()))
    sm_cpa_real    = total_spend / sm_total_ftds if sm_total_ftds > 0 and total_spend > 0 else None

    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
    for col, label, value in [
        (c1, "💰 Custo Total",        brl(total_spend)),
        (c2, "📋 Registros (SM)",     f"{sm_total_regs:,}"),
        (c3, "🎯 FTDs (SM Total)",    f"{sm_total_ftds:,}"),
        (c4, "💵 CPA Real (SM)",      brl(sm_cpa_real)),
        (c5, "💳 Net Deposits",       brl(total_net_dep)),
        (c6, "📈 Net PL",             brl(total_net_pl)),
        (c7, "🚀 ROAS Net PL",        f"{roas_val:.2f}x" if roas_val is not None else "—"),
        (c8, "🎯 FTDs (Meta match)",  f"{int(total_ftds):,}"),
    ]:
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── ALERTAS ──────────────────────────────────
    alertas_erro, alertas_ok = [], []
    if not df_unified.empty:
        for _, row in df_unified.iterrows():
            camp   = row["Campanha Meta"]
            status = row.get("Status", "")
            spend  = row["Investido (R$)"]
            ftds   = row["FTDs"]
            net_pl = row["Net PL (R$)"]
            cpa    = row["CPA Real (R$)"]
            roas   = row["ROAS Net PL"]

            if spend > 3000 and ftds == 0 and status == "Ativa":
                alertas_erro.append(("🔴 Tracking Quebrado", f"**{camp}** — {brl(spend)} sem FTDs"))
            if net_pl is not None and net_pl < -1000 and spend > 3000 and status == "Ativa":
                alertas_erro.append(("🔴 Net PL Negativo", f"**{camp}** — Net PL {brl(net_pl)}"))
            if cpa is not None and cpa > 3000 and status == "Ativa" and ftds > 0:
                alertas_erro.append(("🟡 CPA Alto", f"**{camp}** — CPA {brl(cpa)}"))
            if roas is not None and roas >= 1.0 and status == "Ativa":
                alertas_ok.append(("✅ Lucrativo", f"**{camp}** — ROAS {roas:.2f}x"))

    for ra in RESOLVED_ACTIONS:
        alertas_ok.append(("✅ Resolvido", f"[{ra['data']}] {ra['titulo']} — {ra['detalhe']}"))

    n_alertas = len(alertas_erro)
    with st.expander(f"⚠️ {n_alertas} alerta(s) ativo(s)" if n_alertas else "✅ Nenhum alerta crítico"):
        for tipo, msg in alertas_erro:
            st.markdown(f"**{tipo}**: {msg}")
        if alertas_ok:
            st.markdown("---")
            for tipo, msg in alertas_ok:
                st.markdown(f"{tipo}: {msg}")
        if not alertas_erro and not alertas_ok:
            st.markdown("Nenhum alerta no período selecionado.")

    st.divider()

    # ── ANÁLISE POR UTM ──────────────────────────────────
    st.subheader(f"Análise por UTM Campaign — {date_label}")

    if not df_unified.empty:
        kc = st.columns(8)
        roas_dep_val = total_deposits / total_spend if total_spend > 0 else None
        for col, label, value in [
            (kc[0], "Investido",   brl(total_spend)),
            (kc[1], "Net P&L",     brl(total_net_pl)),
            (kc[2], "ROI",         f"{roas_val:.2f}x" if roas_val is not None else "—"),
            (kc[3], "FTDs (SM)",    f"{sm_total_ftds:,}"),
            (kc[4], "CPA (SM)",    brl(sm_cpa_real)),
            (kc[5], "Dep Amount",  brl(total_deposits)),
            (kc[6], "ROAS Dep",    f"{roas_dep_val:.2f}x" if roas_dep_val is not None else "—"),
            (kc[7], "Registros",   f"{int(total_regs):,}"),
        ]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value" style="font-size:1.05rem">{value}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        tipo_filter = st.radio("Filtrar", ["Todos", "Só ativas", "Só pausadas"], horizontal=True)
        df_show = df_unified.copy()
        if tipo_filter == "Só ativas":
            df_show = df_show[df_show["Status"] == "Ativa"]
        elif tipo_filter == "Só pausadas":
            df_show = df_show[df_show["Status"] == "Pausada"]

        # Colunas essenciais para mobile
        cols_main = ["UTM Campaign", "Status", "FTDs", "FTD Valor (R$)", "CPA Real (R$)", "Investido (R$)", "Net Deposits (R$)", "Depósitos Bruto (R$)", "Net PL (R$)", "ROAS Net PL"]
        df_display = df_show[[c for c in cols_main if c in df_show.columns]].copy()

        def _color_roi(val):
            if val is None or not isinstance(val, (int, float)) or math.isnan(val):
                return "color: #888"
            if val >= 1.0:
                return "background-color: rgba(0,200,100,0.15); color: #00ff88"
            if val >= 0.3:
                return "background-color: rgba(255,165,0,0.15); color: #ffa500"
            return "background-color: rgba(255,50,50,0.15); color: #ff4b4b"

        def _color_status(val):
            return "color: #00ff88; font-weight:bold" if val == "Ativa" else "color: #888"

        fmt = {}
        for col in ["Investido (R$)", "Net PL (R$)", "Net Deposits (R$)", "Depósitos Bruto (R$)", "FTD Valor (R$)"]:
            if col in df_display.columns:
                fmt[col] = lambda v: brl(v)
        if "CPA Real (R$)" in df_display.columns:
            fmt["CPA Real (R$)"] = lambda v: brl(v) if v is not None else "—"
        if "ROAS Net PL" in df_display.columns:
            fmt["ROAS Net PL"] = lambda v: f"{v:.2f}x" if v is not None else "—"

        styled = df_display.style
        if "ROAS Net PL" in df_display.columns:
            styled = styled.map(_color_roi, subset=["ROAS Net PL"])
        if "Status" in df_display.columns:
            styled = styled.map(_color_status, subset=["Status"])
        styled = styled.format(fmt, na_rep="—")

        st.dataframe(styled, use_container_width=True, hide_index=True)
        csv = df_show.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Exportar CSV completo", csv, "multibet_utm_analysis.csv", "text/csv")

    else:
        st.info("Sem dados Meta para o período selecionado.")


    # ── UNMATCHED UTMs ──────────────────────────────────
    if not df_unmatched.empty:
        with st.expander(f"Outros UTMs sem match no Meta ({len(df_unmatched)})"):
            df_unm_show = df_unmatched[df_unmatched["FTDs"] > 0].sort_values("FTDs", ascending=False)
            if not df_unm_show.empty:
                st.dataframe(df_unm_show.style.format({
                    "Net PL (R$)":    lambda v: brl(v),
                    "Depósitos (R$)": lambda v: brl(v),
                }), use_container_width=True, hide_index=True)
            else:
                st.markdown("Nenhuma UTM sem match com FTDs no período.")


if __name__ == "__main__":
    main()
