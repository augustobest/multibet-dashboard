# auth.py — gate de autenticação Supabase para a Multibet Dashboard

import streamlit as st

from supabase_client import get_client as _client


def _render_login():
    st.markdown(
        """
        <style>
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 4rem; max-width: 420px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("# 🎯 Multibet Dashboard")
    st.markdown("##### Acesso restrito")
    st.markdown("&nbsp;")

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", key="login_email", autocomplete="username")
        password = st.text_input("Senha", type="password", key="login_password", autocomplete="current-password")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Preencha email e senha.")
            return
        try:
            res = _client().auth.sign_in_with_password({"email": email, "password": password})
            if res and res.user:
                st.session_state["sb_user"] = {
                    "id": res.user.id,
                    "email": res.user.email,
                }
                st.session_state["sb_session"] = {
                    "access_token": res.session.access_token,
                    "refresh_token": res.session.refresh_token,
                }
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
        except Exception as e:
            msg = str(e).lower()
            if "invalid login" in msg or "invalid credentials" in msg:
                st.error("Email ou senha incorretos.")
            else:
                st.error(f"Erro ao autenticar: {e}")


def _load_user_client() -> dict | None:
    """Carrega o(s) cliente(s) que o usuário logado pertence.
    Por enquanto pega o primeiro (sem seletor multi-tenant na UI ainda)."""
    if "sb_client" in st.session_state:
        return st.session_state["sb_client"]
    try:
        from supabase_client import get_authed_client
        sb = get_authed_client()
        res = sb.table("user_clients").select("client_id, role, clients(id, name, slug)").limit(1).execute()
        rows = res.data or []
        if not rows:
            return None
        row = rows[0]
        client = row.get("clients") or {}
        info = {
            "id":   client.get("id") or row.get("client_id"),
            "name": client.get("name"),
            "slug": client.get("slug"),
            "role": row.get("role"),
        }
        st.session_state["sb_client"] = info
        return info
    except Exception as e:
        st.error(f"Erro ao carregar cliente: {e}")
        return None


def require_login() -> dict:
    """Bloqueia a renderização da dashboard até o usuário logar.
    Retorna dict do user logado quando autenticado."""
    user = st.session_state.get("sb_user")
    if user:
        client = _load_user_client()
        if not client:
            st.error("Sua conta não está vinculada a nenhum cliente. Contate o admin.")
            st.stop()
        return user
    _render_login()
    st.stop()


def current_client_id() -> str | None:
    info = st.session_state.get("sb_client")
    return info.get("id") if info else None


def current_client() -> dict | None:
    return st.session_state.get("sb_client")


def logout_button(location=st.sidebar):
    user = st.session_state.get("sb_user")
    if not user:
        return
    with location:
        st.markdown(f"**👤 {user.get('email','')}**")
        if st.button("Sair", use_container_width=True):
            try:
                _client().auth.sign_out()
            except Exception:
                pass
            for k in ("sb_user", "sb_session", "sb_client"):
                st.session_state.pop(k, None)
            st.rerun()
