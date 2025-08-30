import requests
from unittest.mock import patch, Mock


def test_login_success():
    from connectors.http_api import streamlit_auth

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "atoken", "refresh_token": "rtoken"}

    with patch("requests.post", return_value=mock_resp) as post:
        data = streamlit_auth.login("user", "pass")
        assert data["access_token"] == "atoken"
        assert data["refresh_token"] == "rtoken"
        post.assert_called()


def test_login_failure_raises():
    from connectors.http_api import streamlit_auth

    mock_resp = Mock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = requests.HTTPError("unauthorized")

    with patch("requests.post", return_value=mock_resp):
        try:
            streamlit_auth.login("user", "badpass")
            raised = False
        except requests.HTTPError:
            raised = True

        assert raised


def test_refresh_success():
    from connectors.http_api import streamlit_auth

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "new_atoken"}

    with patch("requests.post", return_value=mock_resp) as post:
        data = streamlit_auth.refresh("rtoken")
        assert data["access_token"] == "new_atoken"
        post.assert_called()
