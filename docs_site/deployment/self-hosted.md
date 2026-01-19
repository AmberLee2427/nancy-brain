# Self-Hosting Nancy Brain

This guide covers deploying Nancy Brain on a self-hosted server using Docker and exposing it securely via Cloudflare Tunnels.

## Prerequisites

*   **Hardware**: A machine with at least 16GB RAM is recommended if using local LLM summarization.
*   **OS**: Linux, macOS, or Windows (WSL2) capable of running Docker.
*   **Docker**: Docker Engine and Docker Compose installed.

## Directory Setup

1.  Clone the repository to your server:
    ```bash
    git clone https://github.com/AmberLee2427/nancy-brain.git
    cd nancy-brain
    ```

2.  Copy the example deployment configuration:
    ```bash
    cp examples/docker-compose.self-hosted.yml docker-compose.yml
    ```

3.  Create an `.env` file with your secrets:
    ```bash
    # .env
    MCP_API_KEY=your-secure-random-string
    NB_SECRET_KEY=another-secure-random-string
    TUNNEL_TOKEN=ey...  # Optional: see Cloudflare section below
    ```

## Cloudflare Tunnel Setup (Recommended)

Using a Cloudflare Tunnel is the safest way to expose your Nancy Brain instance to the internet without opening ports on your router.

1.  **Create a Tunnel**:
    *   Go to the [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/).
    *   Navigate to **Access** > **Tunnels**.
    *   Click **Create a Tunnel**.
    *   Name it (e.g., `nancy-brain`).
    *   Select **Cloudflared** as the connector.

2.  **Get the Token**:
    *   Cloudflare will show you installation commands.
    *   Look for the token string (starts with `ey...`) in the command.
    *   Copy this token to your `.env` file as `TUNNEL_TOKEN`.

3.  **Configure Public Hostnames**:
    *   In the Tunnel configuration "Public Hostname" tab, add a public hostname so you can access the UI.
    *   **Subdomain**: `nancy-admin` (or similar).
    *   **Domain**: `your-domain.com`.
    *   **Service**: `http://nancy-ui:8501` (Note: Use the Docker service name, not localhost).

    *   (Optional) If you want to access the API remotely:
    *   **Subdomain**: `nancy-api`.
    *   **Service**: `http://nancy-brain:8000`.

## Deployment

Start the services:

```bash
docker compose up -d
```

Check logs to verify the tunnel connected:

```bash
docker compose logs -f tunnel
```

You should see `INF Registered tunnel connection`. You can now access the Admin UI at `https://nancy-admin.your-domain.com`.

### Legacy: CLI/File-Based Tunnel

If you prefer managing tunnels via the `cloudflared` CLI and config files (instead of the dashboard), you can mount your credentials directly.

1.  **Prepare Files**: Ensure you have your `cert.pem` and `config.yml` on the host.
2.  **Permissions**: Ensure the files are readable by the container user (User 65532).
    ```bash
    chown -R 65532:65532 /path/to/.cloudflared
    ```
3.  **Update Compose**:
    Uncomment the `volumes` section in the `tunnel` service in `docker-compose.self-hosted.yml` and map your local directory:
    ```yaml
        volumes:
          - /home/user/.cloudflared:/home/nonroot/.cloudflared
    ```
4.  **Config**: In your `config.yml`, reference services by their Docker container name and port (e.g., `http://nancy-ui:8501`), NOT `localhost`.

## Alternative: Ngrok

If you don't use Cloudflare, you can use [ngrok](https://ngrok.com/) to expose the ports.

```yaml
  ngrok:
    image: ngrok/ngrok:latest
    command: "http --domain=your-domain.ngrok-free.app 8501"
    environment:
      - NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN}
```

However, Cloudflare Tunnels are generally preferred for permanent self-hosted deployments.
