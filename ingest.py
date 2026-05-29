"""Ingestão multi-cliente: Smartico + Meta → Supabase Postgres.

Loop sobre todos os clientes ativos em `clients`. Pra cada um, lê credenciais
de `client_sources` e popula `smartico_daily` / `meta_daily` marcando com client_id.

Uso:
    python ingest.py                   # últimos 2 dias (default cron)
    python ingest.py --days 90         # backfill 90 dias
    python ingest.py --from 2026-05-01 --to 2026-05-15
    python ingest.py --client multibet # roda só pra um cliente (slug)

Env vars:
    SUPABASE_URL, SUPABASE_SERVICE_KEY  (obrigatórios)
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from supabase import create_client
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")

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


# ─────────────────────────────────────────────
# SMARTICO
# ─────────────────────────────────────────────
def fetch_smartico_rows(client_id: str, config: dict, date_from: str, date_to: str) -> list[dict]:
    host = config.get("host", "https://boapi3.smartico.ai")
    api_key = config["api_key"]
    affiliate_id = config["affiliate_id"]

    dt_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"{host}/api/af2_media_report_op"
        f"?aggregation_period=DAY&date_from={date_from}&date_to={dt_to}"
        f"&affiliate_id={affiliate_id}&group_by=utm_campaign"
    )
    r = requests.get(url, headers={"authorization": api_key}, timeout=120)
    r.raise_for_status()
    data = r.json().get("data") or []

    grouped: dict[tuple[str, str], dict] = {}
    for row in data:
        date = (row.get("dt") or "")[:10]
        utm = row.get("utm_campaign") or "(sem_utm)"
        if not date:
            continue
        key = (date, utm)
        agg = grouped.setdefault(key, {
            "client_id": client_id,
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


# ─────────────────────────────────────────────
# META
# ─────────────────────────────────────────────
def fetch_meta_rows(client_id: str, config: dict, date_from: str, date_to: str) -> list[dict]:
    token = config["access_token"]
    accounts = config.get("account_ids", [])
    api_version = config.get("api_version", "v19.0")

    grouped: dict[tuple, dict] = {}
    for acct in accounts:
        url = f"https://graph.facebook.com/{api_version}/{acct}/insights"
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
                    "client_id":   client_id,
                    "date":        date,
                    "account_id":  acct,
                    "campaign_id": campaign_id,
                    "campaign_name": row.get("campaign_name", ""),
                    "spend":         float(row.get("spend") or 0),
                    "impressions":   int(num(row, "impressions")),
                    "clicks":        int(num(row, "clicks")),
                    "reach":         int(num(row, "reach")),
                    "frequency":     float(row.get("frequency") or 0) or None,
                })
            next_url = body.get("paging", {}).get("next")
            first = False
    return list(grouped.values())


# ─────────────────────────────────────────────
# UTM mapping auto-sync
# ─────────────────────────────────────────────
UTM_RE = re.compile(r"utm_campaign=([^&\s\"]+)")


def _clean_utm(value: str | None) -> str | None:
    """Filtra placeholders dinâmicos do Meta (tipo {{campaign.name}})
    e valores vazios/None."""
    if not value:
        return None
    if "{{" in value or "}}" in value:
        return None
    value = value.strip()
    return value or None


def _extract_utm(ad: dict) -> str | None:
    """Extrai utm_campaign de url_tags do ad ou do creative.
    Ignora templates dinâmicos do Meta."""
    for src in [ad.get("url_tags"),
                (ad.get("creative") or {}).get("url_tags")]:
        if src:
            m = UTM_RE.search(src)
            if m:
                utm = _clean_utm(m.group(1))
                if utm:
                    return utm
    oss = (ad.get("creative") or {}).get("object_story_spec") or {}
    link = (oss.get("link_data") or {}).get("link")
    if link:
        m = UTM_RE.search(link)
        if m:
            utm = _clean_utm(m.group(1))
            if utm:
                return utm
    cta = (oss.get("video_data") or {}).get("call_to_action") or {}
    val = (cta.get("value") or {}).get("link")
    if val:
        m = UTM_RE.search(val)
        if m:
            return _clean_utm(m.group(1))
    return None


def sync_utm_mappings(sb, client_id: str, meta_config: dict) -> dict:
    """Lê campanhas + ads ATIVOS no Meta e atualiza utm_mapping
    (apenas linhas com auto_sync=true ou novas).

    Retorna dict com contadores: created, updated, skipped, no_utm.
    """
    token = meta_config["access_token"]
    accounts = meta_config.get("account_ids", [])
    api_version = meta_config.get("api_version", "v19.0")

    # 1. Coleta UTMs ATIVAS por campanha do Meta
    utm_by_campaign: dict[str, set[str]] = defaultdict(set)
    for acct in accounts:
        # Lista campanhas (não-deletadas)
        url = f"https://graph.facebook.com/{api_version}/{acct}/campaigns"
        params = {
            "fields": "id,name,effective_status",
            "effective_status": '["ACTIVE","PAUSED"]',
            "limit": 500,
            "access_token": token,
        }
        next_url = url
        first = True
        camps: list[dict] = []
        while next_url:
            try:
                r = requests.get(next_url, params=params if first else None, timeout=120)
                r.raise_for_status()
                body = r.json()
            except Exception as e:
                print(f"    Meta campaigns {acct}: erro {e}", file=sys.stderr)
                break
            camps.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            first = False

        for camp in camps:
            camp_name = camp.get("name", "").strip()
            if not camp_name:
                continue
            # Lista ads dessa campanha (todos status; filtramos depois)
            ads_url = f"https://graph.facebook.com/{api_version}/{camp['id']}/ads"
            ads_params = {
                "fields": "name,effective_status,url_tags,creative{url_tags,object_story_spec}",
                "limit": 500,
                "access_token": token,
            }
            try:
                r = requests.get(ads_url, params=ads_params, timeout=120)
                r.raise_for_status()
                ads_body = r.json()
            except Exception as e:
                print(f"    Meta ads {camp_name}: erro {e}", file=sys.stderr)
                continue
            for ad in ads_body.get("data", []):
                if ad.get("effective_status") != "ACTIVE":
                    continue
                utm = _extract_utm(ad)
                if utm:
                    utm_by_campaign[camp_name].add(utm)

    # 2. Carrega utm_mapping atual desse cliente
    existing_res = sb.table("utm_mapping").select(
        "campaign_name, utm_campaigns, auto_sync"
    ).eq("client_id", client_id).execute()
    existing = {r["campaign_name"]: r for r in (existing_res.data or [])}

    counts = {"created": 0, "updated": 0, "locked": 0, "no_change": 0, "no_utm": 0}

    # 3. Decide o que fazer por campanha
    for camp_name, utms in utm_by_campaign.items():
        if not utms:
            counts["no_utm"] += 1
            continue
        utm_list = sorted(utms)
        cur = existing.get(camp_name)

        if cur is None:
            # Nova campanha → INSERT auto_sync=true
            sb.table("utm_mapping").insert({
                "client_id": client_id,
                "campaign_name": camp_name,
                "utm_campaigns": utm_list,
                "auto_sync": True,
            }).execute()
            counts["created"] += 1
            print(f"    + criada: {camp_name} -> {utm_list}")
        elif not cur.get("auto_sync", True):
            counts["locked"] += 1  # respeita override manual
        elif set(cur.get("utm_campaigns") or []) == set(utm_list):
            counts["no_change"] += 1
        else:
            sb.table("utm_mapping").update({
                "utm_campaigns": utm_list,
                "updated_at": datetime.now(BR_TZ).isoformat(),
            }).eq("client_id", client_id).eq("campaign_name", camp_name).execute()
            counts["updated"] += 1
            old = cur.get("utm_campaigns") or []
            print(f"    ~ atualizada: {camp_name}  {old} → {utm_list}")

    return counts


# ─────────────────────────────────────────────
# UPSERT
# ─────────────────────────────────────────────
def upsert(sb, table: str, rows: list[dict], pk: list[str]):
    if not rows:
        return
    for i in range(0, len(rows), UPSERT_CHUNK_SIZE):
        chunk = rows[i:i + UPSERT_CHUNK_SIZE]
        sb.table(table).upsert(chunk, on_conflict=",".join(pk)).execute()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ingestão multi-cliente Smartico+Meta → Supabase")
    parser.add_argument("--days", type=int, default=2,
                        help="Quantos dias para trás (default 2, pega ontem+hoje)")
    parser.add_argument("--from", dest="date_from",
                        help="Data inicial YYYY-MM-DD (sobrepõe --days)")
    parser.add_argument("--to", dest="date_to",
                        help="Data final YYYY-MM-DD (default hoje)")
    parser.add_argument("--client", dest="client_slug",
                        help="Roda só pra um cliente (slug). Default: todos ativos.")
    args = parser.parse_args()

    today = datetime.now(BR_TZ).date()
    date_to = args.date_to or today.strftime("%Y-%m-%d")
    if args.date_from:
        date_from = args.date_from
    else:
        date_from = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Período: {date_from} → {date_to}")

    sb = create_client(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))

    # Carrega lista de clientes ativos
    client_q = sb.table("clients").select("id,name,slug").eq("active", True)
    if args.client_slug:
        client_q = client_q.eq("slug", args.client_slug)
    clients = client_q.execute().data or []
    if not clients:
        print("Nenhum cliente ativo encontrado.")
        return

    for client in clients:
        print(f"\n=== Cliente: {client['name']} ({client['slug']}) ===")

        # Carrega configs (smartico + meta) deste cliente
        sources = sb.table("client_sources").select("source_type,config,active").eq("client_id", client["id"]).execute().data or []
        config_by_type = {s["source_type"]: s["config"] for s in sources if s.get("active", True)}

        # Auto-sync utm_mapping a partir das UTMs ATIVAS no Meta
        if "meta" in config_by_type:
            print("  Sincronizando utm_mapping...")
            try:
                stats = sync_utm_mappings(sb, client["id"], config_by_type["meta"])
                print(f"    criadas={stats['created']} atualizadas={stats['updated']} "
                      f"sem_mudança={stats['no_change']} travadas={stats['locked']} "
                      f"sem_utm={stats['no_utm']}")
            except Exception as e:
                print(f"    ERRO sync utm_mapping: {e}", file=sys.stderr)

        # Smartico
        if "smartico" in config_by_type:
            print("  Buscando Smartico...")
            try:
                rows = fetch_smartico_rows(client["id"], config_by_type["smartico"], date_from, date_to)
                print(f"    {len(rows)} linhas")
                upsert(sb, "smartico_daily", rows, ["client_id", "date", "utm_campaign"])
            except Exception as e:
                print(f"    ERRO Smartico: {e}", file=sys.stderr)
        else:
            print("  Smartico: sem config, pulando")

        # Meta
        if "meta" in config_by_type:
            print("  Buscando Meta...")
            try:
                rows = fetch_meta_rows(client["id"], config_by_type["meta"], date_from, date_to)
                print(f"    {len(rows)} linhas")
                upsert(sb, "meta_daily", rows, ["client_id", "date", "account_id", "campaign_id"])
            except Exception as e:
                print(f"    ERRO Meta: {e}", file=sys.stderr)
        else:
            print("  Meta: sem config, pulando")

    print("\nConcluído.")


if __name__ == "__main__":
    main()
