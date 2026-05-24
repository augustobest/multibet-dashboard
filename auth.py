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


def require_login() -> dict:
    """Bloqueia a renderização da dashboard até o usuário logar.
    Retorna dict do user logado quando autenticado."""
    user = st.session_state.get("sb_user")
    if user:
        return user
    _render_login()
    st.stop()


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
            for k in ("sb_user", "sb_session"):
                st.session_state.pop(k, None)
            st.rerun()
