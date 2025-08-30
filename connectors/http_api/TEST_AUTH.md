# Quick auth test commands

Create a test user (run from repository root):

```bash
PYTHONPATH=. python connectors/http_api/add_user.py testuser testpass
```

Start the FastAPI server (use your env or uvicorn directly):

```bash
uvicorn connectors.http_api.app:app --reload --port 8001
```

Request a token and call protected endpoint:

```bash
# get token
TOKEN=$(curl -s -X POST -F "username=testuser" -F "password=testpass" http://127.0.0.1:8001/login | jq -r .access_token)
# call protected
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8001/protected
```

Streamlit dev UI (example):

```bash
streamlit run connectors/http_api/streamlit_auth.py
```

Revoke a refresh token (requires authentication):

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
	-d '{"refresh_token":"'$REFRESH'"}' http://127.0.0.1:8001/revoke
```
