# supabase_client.py — cliente Supabase compartilhado entre auth e dashboard

import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://jjygbxojkbxjctflblji.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "sb_publishable_Vhi8qaq-iGLZj3ngtFFDOg_YdI9C5dP")


@st.cache_resource
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_authed_client() -> Client:
    """Cliente com a sessão do usuário logado (necessário pra RLS authenticated)."""
    sb = get_client()
    sess = st.session_state.get("sb_session")
    if sess:
        try:
            sb.auth.set_session(sess["access_token"], sess["refresh_token"])
        except Exception:
            pass
    return sb
