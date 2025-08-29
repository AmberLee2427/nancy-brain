import streamlit as st
import requests

API_URL = st.secrets.get("API_URL", "http://127.0.0.1:8000")

st.title("Nancy Brain Admin — Login")

if "token" not in st.session_state:
    st.session_state.token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

with st.form("login_form"):
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Login")
    if submitted:
        try:
            resp = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.token = data.get("access_token")
                st.session_state.refresh_token = data.get("refresh_token")
                st.success("Logged in")
            else:
                st.error(f"Login failed: {resp.text}")
        except Exception as e:
            st.error(f"Request error: {e}")

if st.session_state.token:
    st.write("You are logged in.")
    col1, col2 = st.columns(2)
    if col1.button("Call protected endpoint"):
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        r = requests.get(f"{API_URL}/protected", headers=headers)
        st.write(r.status_code, r.text)
    if col2.button("Refresh access token"):
        r = requests.post(f"{API_URL}/refresh", json={"refresh_token": st.session_state.refresh_token})
        if r.status_code == 200:
            st.session_state.token = r.json().get("access_token")
            st.success("Access token refreshed")
        else:
            st.error("Refresh failed")
