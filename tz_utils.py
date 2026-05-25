# tz_utils.py — helpers de data/hora em horário de Brasília
# Streamlit Cloud roda em UTC; pra não bugar o "hoje" quando vira 21h BR (= 00h UTC),
# todo cálculo de "hoje" no dashboard deve usar essas funções.

from datetime import datetime, date
from zoneinfo import ZoneInfo

BR = ZoneInfo("America/Sao_Paulo")


def now_br() -> datetime:
    """Datetime agora em horário de Brasília (naive, sem tzinfo)."""
    return datetime.now(BR).replace(tzinfo=None)


def today_br() -> date:
    """Data de hoje em horário de Brasília."""
    return now_br().date()
