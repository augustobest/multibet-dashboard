"""Ingestão Smartico + Meta → Supabase Postgres.

Uso:
    python ingest.py                   # últimos 2 dias (default cron)
    python ingest.py --days 90         # backfill 90 dias
    python ingest.py --from 2026-05-01 --to 2026-05-15

Lê config de variáveis de ambiente:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SMARTICO_KEY, META_ACCESS_TOKEN
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from supabase import create_client

SMARTICO_URL = "https://boapi3.smartico.ai"
AFFILIATE_ID = 464673
META_ACCOUNTS = [
    "act_1418521646228655",
    "act_3506962756106082",
    "act_1531679918112645",
    "act_1282215803969842",
    "act_26153688877615850",
]
META_API_VERSION = "v19.0"

UPSERT_CHUNK_SIZE = 500


def env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"ERRO: variável {key} não definida", file=sys.stderr)
        sys.exit(1)
    return val


def num(row: dict, key: str) -> float:
    v = row.get(key)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def fetch_smartico_rows(date_from: str, date_to: str) -> list[dict]:
    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"{SMARTICO_URL}/api/af2_media_report_op"
        f"?aggregation_period=DAY&date_from={date_from}&date_to={dt_to}"
        f"&affiliate_id={AFFILIATE_ID}&group_by=utm_campaign"
    )
    r = requests.get(url, headers={"authorization": env("SMARTICO_KEY")}, timeout=120)
    r.raise_for_status()
    data = r.json().get("data") or []

    # Smartico devolve uma linha por (dia, utm). Agregamos pra garantir unicidade
    # do PK (date, utm_campaign) e somar caso venha duplicado.
    grouped: dict[tuple[str, str], dict] = {}
    for row in data:
        date = (row.get("dt") or "")[:10]
        utm = row.get("utm_campaign") or "(sem_utm)"
        if not date:
            continue
        key = (date, utm)
        agg = grouped.setdefault(key, {
            "date": date,
            "utm_campaign": utm,
            "registrations": 0,
            "ftd_count": 0,
            "ftd_total": 0.0,
            "deposit_count": 0,
            "deposit_total": 0.0,
            "net_deposits": 0.0,
            "net_pl": 0.0,
            "net_pl_casino": 0.0,
            "net_pl_sport": 0.0,
            "withdrawal_total": 0.0,
            "bonus_amount": 0.0,
            "commissions_total": 0.0,
        })
        agg["registrations"]     += int(num(row, "registration_count"))
        agg["ftd_count"]         += int(num(row, "ftd_count"))
        agg["ftd_total"]         += num(row, "ftd_total")
        agg["deposit_count"]     += int(num(row, "deposit_count"))
        agg["deposit_total"]     += num(row, "deposit_total")
        agg["net_deposits"]      += num(row, "net_deposits")
        agg["net_pl"]            += num(row, "net_pl")
        agg["net_pl_casino"]     += num(row, "net_pl_casino")
        agg["net_pl_sport"]      += num(row, "net_pl_sport")
        agg["withdrawal_total"]  += num(row, "withdrawal_total")
        agg["bonus_amount"]      += num(row, "bonus_amount")
        agg["commissions_total"] += num(row, "commissions_total")
    return list(grouped.values())


def fetch_meta_rows(date_from: str, date_to: str) -> list[dict]:
    token = env("META_ACCESS_TOKEN")
    grouped: dict[tuple, dict] = {}

    for acct in META_ACCOUNTS:
        url = f"https://graph.facebook.com/{META_API_VERSION}/{acct}/insights"
        params = {
            "access_token": token,
            "time_range": f'{{"since":"{date_from}","until":"{date_to}"}}',
            "time_increment": 1,
            "level": "campaign",
            "fields": "campaign_id,campaign_name,spend,impressions,clicks,reach,frequency",
            "limit": 500,
        }
        next_url = url
        first = True
        while next_url:
            try:
                r = requests.get(next_url, params=params if first else None, timeout=120)
                r.raise_for_status()
                body = r.json()
            except Exception as e:
                print(f"  Meta {acct}: erro {e}", file=sys.stderr)
                break
            for row in body.get("data", []):
                date = row.get("date_start")
                campaign_id = row.get("campaign_id")
                if not date or not campaign_id:
                    continue
                key = (date, acct, campaign_id)
                grouped.setdefault(key, {
                    "date": date,
                    "account_id": acct,
                    "campaign_id": campaign_id,
                    "campaign_name": row.get("campaign_name", ""),
                    "spend": float(row.get("spend") or 0),
                    "impressions": int(num(row, "impressions")),
                    "clicks": int(num(row, "clicks")),
                    "reach": int(num(row, "reach")),
                    "frequency": float(row.get("frequency") or 0) or None,
                })
            next_url = body.get("paging", {}).get("next")
            first = False
    return list(grouped.values())


def upsert(sb, table: str, rows: list[dict], pk: list[str]):
    if not rows:
        return
    for i in range(0, len(rows), UPSERT_CHUNK_SIZE):
        chunk = rows[i:i + UPSERT_CHUNK_SIZE]
        sb.table(table).upsert(chunk, on_conflict=",".join(pk)).execute()


def main():
    parser = argparse.ArgumentParser(description="Ingestão Smartico+Meta → Supabase")
    parser.add_argument("--days", type=int, default=2,
                        help="Quantos dias para trás (default 2, pega ontem+hoje)")
    parser.add_argument("--from", dest="date_from",
                        help="Data inicial YYYY-MM-DD (sobrepõe --days)")
    parser.add_argument("--to", dest="date_to",
                        help="Data final YYYY-MM-DD (default hoje)")
    args = parser.parse_args()

    today = datetime.today()
    date_to = args.date_to or today.strftime("%Y-%m-%d")
    if args.date_from:
        date_from = args.date_from
    else:
        date_from = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Período: {date_from} → {date_to}")

    sb = create_client(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))

    print("Buscando Smartico...")
    sm_rows = fetch_smartico_rows(date_from, date_to)
    print(f"  {len(sm_rows)} linhas")
    upsert(sb, "smartico_daily", sm_rows, ["date", "utm_campaign"])

    print("Buscando Meta...")
    meta_rows = fetch_meta_rows(date_from, date_to)
    print(f"  {len(meta_rows)} linhas")
    upsert(sb, "meta_daily", meta_rows, ["date", "account_id", "campaign_id"])

    print("Concluído.")


if __name__ == "__main__":
    main()
