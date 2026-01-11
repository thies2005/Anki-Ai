# Cloudflare Tunnel Setup Guide

This guide walks you through setting up a persistent Cloudflare Tunnel for Anki AI.

## Prerequisites

- A domain managed by Cloudflare
- `cloudflared` installed on your local machine

Install cloudflared:
```bash
# macOS (Homebrew)
brew install cloudflare/cloudflare/cloudflared

# Linux
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Windows (using winget)
winget install --id Cloudflare.cloudflared
```

## Step 1: Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will open a browser. Select your domain and authorize.

## Step 2: Create a Tunnel

```bash
cloudflared tunnel create anki-ai
```

You'll get output like:
```
Tunnel credentials written to /path/to/.cloudflared/UUID.json
Tunnel ID: <UUID>
```

Copy the `<UUID>` - you'll need it.

## Step 3: Configure the Tunnel

Create `./cloudflared/config.yml`:

```yaml
tunnel: <YOUR_TUNNEL_UUID>
credentials-file: /home/cloudflared/.cloudflared/<YOUR_TUNNEL_UUID>.json

ingress:
  - hostname: anki.yourdomain.com
    service: http://anki-ai:8501
  - service: http_status:404
```

Replace:
- `<YOUR_TUNNEL_UUID>` with your tunnel ID from Step 2
- `anki.yourdomain.com` with your desired subdomain

## Step 4: Copy Tunnel Credentials

```bash
# Create the cloudflared directory
mkdir -p cloudflared

# Copy the certificate and credentials
cp ~/.cloudflared/*.cert cloudflared/
cp ~/.cloudflared/<TUNNEL_UUID>.json cloudflared/
```

## Step 5: Add DNS Record

```bash
cloudflared tunnel route dns anki-ai anki.yourdomain.com
```

## Step 6: Start Your Services

```bash
docker-compose up -d
```

Your app will now be accessible at: `https://anki.yourdomain.com`

---

## Alternative: Using Tunnel Token (Simpler)

If you prefer not to mount credentials, you can use a tunnel token:

1. Get your tunnel token from the Cloudflare Dashboard (Zero Trust > Networks > Tunnels)
2. Add it to your `.env` file:
   ```
   TUNNEL_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```
3. Restart with `docker-compose up -d`

---

## Troubleshooting

**Tunnel won't start:**
- Check the tunnel UUID matches in both `config.yml` and the JSON filename
- Ensure the `cloudflared/` directory contains both `.cert` and `.json` files

**502 errors:**
- Verify the `anki-ai` container is healthy: `docker ps`
- Check logs: `docker logs anki-ai`

**DNS not resolving:**
- Verify DNS was added: `cloudflared tunnel route dns anki-ai anki.yourdomain.com`
- May take a few minutes to propagate
