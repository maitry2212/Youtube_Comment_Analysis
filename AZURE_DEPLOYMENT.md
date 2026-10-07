# 🚀 Azure Deployment Guide — YouTube Comment Analysis API

A **complete, step-by-step** guide to deploy the FastAPI sentiment analysis backend on an Azure **Virtual Machine** (Ubuntu), wire up a **CI/CD pipeline** via GitHub Actions, and finally point your **Chrome Extension** at the live server.

---

## 📐 Architecture Overview

```
                    ┌─────────────────────────────┐
                    │   GitHub Repository (main)   │
                    └────────────┬────────────────-┘
                                 │ git push triggers
                    ┌────────────▼────────────────-┐
                    │   GitHub Actions CI/CD        │
                    │  (build → push → SSH deploy)  │
                    └────────────┬────────────────-┘
                                 │ SSH into VM
  Chrome Extension  ──HTTPS──►  ┌▼──────────────────────────┐
  (popup.js)                    │  Azure VM (Ubuntu 22.04)  │
                                │  Nginx  :443 → :8000      │
                                │  Docker  → FastAPI App    │
                                │  (lgbm_model + vectorizer)│
                                └───────────────────────────┘
```

**Stack Summary:**
| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (Python 3.11) |
| ML Model | LightGBM + TF-IDF Vectorizer |
| Container | Docker |
| Server | Azure VM — Ubuntu 22.04 LTS |
| Reverse Proxy | Nginx + SSL (Let's Encrypt) |
| CI/CD | GitHub Actions |
| Client | Chrome Extension |

---

## 📋 Pre-Deployment Checklist

Before touching Azure, confirm these on your **local machine**:

- [ ] `lgbm_model.pkl` and `tfidf_vectorizer.pkl` exist in the project root
- [ ] `docker build -t yt-analysis .` succeeds locally
- [ ] `docker run -p 8000:8000 yt-analysis` — `GET http://localhost:8000/` returns `{"message":"Welcome to FastAPI Sentiment API"}`
- [ ] You have a [DockerHub](https://hub.docker.com) account (`kartik87580`)
- [ ] You have an [Azure account](https://portal.azure.com) with an active subscription
- [ ] You have a GitHub repo with Actions enabled

---

## PHASE 1 — Create the Azure Virtual Machine

### Step 1.1 — Log in to Azure Portal

1. Go to [https://portal.azure.com](https://portal.azure.com)
2. Sign in with your Microsoft account.

---

### Step 1.2 — Create a Resource Group

A Resource Group is a logical container for all your Azure resources.

1. In the search bar, type **"Resource groups"** → Click **Create**
2. Fill in:
   - **Subscription:** Your subscription
   - **Resource group name:** `yt-sentiment-rg`
   - **Region:** `East US` (or closest to you)
3. Click **Review + Create** → **Create**

---

### Step 1.3 — Create the Virtual Machine

1. Search for **"Virtual machines"** → Click **Create** → **Azure virtual machine**

2. Fill in the **Basics** tab:

| Field | Value |
|---|---|
| **Subscription** | Your subscription |
| **Resource group** | `yt-sentiment-rg` |
| **VM name** | `yt-sentiment-vm` |
| **Region** | `East US` |
| **Image** | `Ubuntu Server 22.04 LTS - x64 Gen2` |
| **Size** | `Standard_B2s` (2 vCPU, 4 GB RAM) — recommended |
| **Authentication type** | `SSH public key` |
| **Username** | `azureuser` |
| **SSH public key source** | `Generate new key pair` |
| **Key pair name** | `yt-sentiment-key` |

> **💡 Size Note:** `Standard_B2s` costs ~$30/month and handles LightGBM inference + matplotlib chart generation comfortably. `Standard_B1s` (1 vCPU, 1 GB) is too small for this workload.

3. **Disks tab:** Keep default (Standard SSD, 30 GB).

4. **Networking tab:**
   - Allow inbound ports: **SSH (22)**, **HTTP (80)**, **HTTPS (443)**
   - These will be opened now; we lock them down via NSG rules later.

5. Click **Review + Create** → **Create**

6. When prompted, **Download the private key** (`yt-sentiment-key.pem`). **Save it somewhere safe** — you cannot download it again.

7. Wait ~2 minutes for the VM to deploy. Note the **Public IP Address** shown on the VM overview page (e.g., `20.85.123.45`).

---

### Step 1.4 — Open Required Ports (Network Security Group)

1. In your VM resource → Left sidebar → **Networking** → **Network security group**
2. Confirm these inbound rules exist (Azure adds them automatically if you selected the ports above):
   - Port `22` — SSH
   - Port `80` — HTTP
   - Port `443` — HTTPS
3. We do **NOT** open port `8000` publicly — Nginx will proxy it.

---

### Step 1.5 — Connect to the VM via SSH

On your **local machine** (Windows PowerShell):

```powershell
# Fix permissions on the key file (Windows equivalent)
icacls "C:\path\to\yt-sentiment-key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"

# SSH into the VM
ssh -i "C:\path\to\yt-sentiment-key.pem" azureuser@<YOUR_VM_PUBLIC_IP>
```

You should see a `azureuser@yt-sentiment-vm:~$` prompt. All remaining commands in **Phase 2** run inside this SSH session.

---

## PHASE 2 — Configure the Ubuntu Server

### Step 2.1 — System Update & Essential Tools

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git curl wget nginx certbot python3-certbot-nginx ufw
```

---

### Step 2.2 — Install Docker

```bash
# Add Docker's GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Allow your user to run docker without sudo
sudo usermod -aG docker azureuser
newgrp docker

# Verify
docker --version
# Expected: Docker version 26.x.x
```

---

### Step 2.3 — Configure UFW Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow http
sudo ufw allow https
sudo ufw enable
sudo ufw status
```

---

### Step 2.4 — Configure Nginx as Reverse Proxy

Create the Nginx site configuration:

```bash
sudo nano /etc/nginx/sites-available/yt-sentiment
```

Paste the following (replace `YOUR_DOMAIN_OR_IP` with your actual domain or VM public IP):

```nginx
server {
    listen 80;
    server_name your-ip#########;

    # Allow larger request bodies
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;

        proxy_cache_bypass $http_upgrade;
    }
}
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`), then enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/yt-sentiment /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default   # remove default placeholder
sudo nginx -t                               # test config — expect "syntax is ok"
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

### Step 2.5 — (Optional but Recommended) Set Up a Free Domain + SSL

If you have a domain name (e.g., from Namecheap/Cloudflare), point an **A record** to your VM IP, then:

```bash
sudo certbot --nginx -d yourdomain.com
# Follow prompts: enter email, agree to TOS, choose to redirect HTTP → HTTPS
```

> **No domain?** You can skip this and use `http://<VM_PUBLIC_IP>` directly. The Chrome Extension will still work.

---

### Step 2.6 — Pull and Run the Docker Container (First Time — Manual)

```bash
# Pull the image from DockerHub (built by GitHub Actions)
docker pull kartik87580/yt-analysis:latest

# Run the container
docker run -d \
  --name yt-sentiment-api \
  --restart unless-stopped \
  -p 8000:8000 \
  kartik87580/yt-analysis:latest

# Check it's running
docker ps
# Should show: yt-sentiment-api   Up X seconds   0.0.0.0:8000->8000/tcp

# Verify the API responds
curl http://localhost:8000/
# Expected: {"message":"Welcome to FastAPI Sentiment API"}
```

At this point your API is live at `http://<VM_IP>/` through Nginx. ✅

---

## PHASE 3 — CI/CD Pipeline (GitHub Actions)

The goal: every `git push` to `main` automatically:
1. Runs syntax checks
2. Builds and pushes the Docker image to DockerHub
3. SSHes into the Azure VM and restarts the container with the new image

### Step 3.1 — Add GitHub Repository Secrets

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

Add these secrets:

| Secret Name | Value | Where to get it |
|---|---|---|
| `DOCKER_USERNAME` | `kartik87580` | Your DockerHub username |
| `DOCKER_PASSWORD` | Your DockerHub password or [Access Token](https://hub.docker.com/settings/security) | DockerHub → Account Settings → Security |
| `AZURE_VM_HOST` | `20.85.123.45` | VM Public IP from Azure Portal |
| `AZURE_VM_USER` | `azureuser` | The username you created |
| `AZURE_VM_SSH_KEY` | The **full contents** of `yt-sentiment-key.pem` | Open the `.pem` file in a text editor, copy everything |

> **Security tip:** Use a DockerHub **Access Token** (not your password) for `DOCKER_PASSWORD`. Create one at DockerHub → Account Settings → Security → New Access Token.

---

### Step 3.2 — Update the CI/CD Workflow File

Replace `.github/workflows/ci-cd.yml` with the full pipeline below:

```yaml
name: CI/CD — YouTube Sentiment API

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

env:
  IMAGE_NAME: kartik87580/yt-analysis

jobs:
  # ──────────────────────────────────────────────
  # JOB 1: Syntax check & basic validation
  # ──────────────────────────────────────────────
  build-and-test:
    name: 🧪 Lint & Syntax Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run syntax check on all Python files
        run: python -m py_compile $(git ls-files '*.py')

      - name: Verify FastAPI app imports correctly
        run: python -c "import app.main; print('✅ App imports OK')"

  # ──────────────────────────────────────────────
  # JOB 2: Build Docker image & push to DockerHub
  # ──────────────────────────────────────────────
  build-and-push:
    name: 🐳 Build & Push Docker Image
    needs: build-and-test
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to DockerHub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          provenance: false
          tags: |
            ${{ env.IMAGE_NAME }}:latest
            ${{ env.IMAGE_NAME }}:${{ github.sha }}

  # ──────────────────────────────────────────────
  # JOB 3: SSH into Azure VM and deploy
  # ──────────────────────────────────────────────
  deploy:
    name: 🚀 Deploy to Azure VM
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.AZURE_VM_HOST }}
          username: ${{ secrets.AZURE_VM_USER }}
          key: ${{ secrets.AZURE_VM_SSH_KEY }}
          script: |
            echo "🔄 Pulling latest Docker image..."
            docker pull kartik87580/yt-analysis:latest

            echo "🛑 Stopping old container..."
            docker stop yt-sentiment-api || true
            docker rm yt-sentiment-api || true

            echo "▶️ Starting new container..."
            docker run -d \
              --name yt-sentiment-api \
              --restart unless-stopped \
              -p 8000:8000 \
              kartik87580/yt-analysis:latest

            echo "🧹 Cleaning up old images..."
            docker image prune -f

            echo "✅ Deployment complete!"
            docker ps | grep yt-sentiment-api
```

Commit and push this file:

```bash
git add .github/workflows/ci-cd.yml
git commit -m "ci: add full Azure VM deployment pipeline"
git push origin main
```

---

### Step 3.3 — Verify the Pipeline Runs

1. In GitHub → **Actions** tab — you should see the workflow running.
2. All 3 jobs should turn green ✅.
3. After the `deploy` job completes, verify on the VM:

```bash
# SSH into VM
ssh -i "yt-sentiment-key.pem" azureuser@<YOUR_VM_IP>

# Check the container is running
docker ps

# Test the endpoint
curl http://localhost:8000/
```

---

## PHASE 4 — Connect the Chrome Extension

The Chrome Extension currently points to `http://localhost:8000`. You need to update it to point to your live Azure VM.

### Step 4.1 — Update `popup.js`

Open `crome_extension/popup.js` and change **line 1**:

```javascript
// BEFORE (local development):
const API_BASE_URL = "http://localhost:8000";

// AFTER (production — choose one of these):
// Option A: If you set up a domain with SSL:
const API_BASE_URL = "https://yourdomain.com";

// Option B: If using just the VM IP (no SSL):
const API_BASE_URL = "http://20.85.123.45";  // replace with your actual IP
```

> **⚠️ Important:** If you use `http://` (no SSL), Chrome may block requests from the extension as "mixed content" on some pages. Setting up a domain + SSL via Let's Encrypt (Step 2.5) is strongly recommended for a production extension.

---

### Step 4.2 — Update `manifest.json` Host Permissions

Open `crome_extension/manifest.json` and update the `host_permissions` (or `permissions`) to include your Azure URL:

```json
{
  "host_permissions": [
    "https://www.googleapis.com/*",
    "https://yourdomain.com/*"
  ]
}
```

If using IP instead of domain:
```json
{
  "host_permissions": [
    "https://www.googleapis.com/*",
    "http://20.85.123.45/*"
  ]
}
```

---

### Step 4.3 — Reload the Extension in Chrome

1. Open Chrome → Navigate to `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. If already loaded: Click the **🔄 Refresh** icon on the extension card
4. If not yet loaded: Click **Load unpacked** → Select the `crome_extension/` folder
5. Open any YouTube video → Click the extension icon → Click **Analyze** ✅

---

## PHASE 5 — Validate End-to-End

Run these checks after full deployment:

### 5.1 — API Health Check

```bash
# From your local machine (not SSH)
curl https://yourdomain.com/
# Expected: {"message":"Welcome to FastAPI Sentiment API"}
```

### 5.2 — Test Sentiment Prediction Endpoint

```bash
curl -X POST "https://yourdomain.com/predict" \
  -H "Content-Type: application/json" \
  -d '{"comments": ["This video is absolutely amazing!", "I hate this content"]}'
# Expected: [{"comment":"This video is absolutely amazing!","sentiment":1},{"comment":"I hate this content","sentiment":-1}]
```

### 5.3 — Test Chart Generation

```bash
curl -X POST "https://yourdomain.com/generate_chart" \
  -H "Content-Type: application/json" \
  -d '{"sentiment_counts": {"1": 10, "0": 5, "-1": 3}}' \
  --output chart.png && echo "✅ Chart generated"
```

---

## PHASE 6 — Monitoring & Maintenance

### View Live Container Logs

```bash
# SSH into VM
docker logs yt-sentiment-api --follow
# Press Ctrl+C to stop following
```

### Restart the Container Manually

```bash
docker restart yt-sentiment-api
```

### Check Resource Usage

```bash
docker stats yt-sentiment-api
# Shows CPU, Memory, Network IO in real time
```

### Update Nginx Config

```bash
sudo nano /etc/nginx/sites-available/yt-sentiment
sudo nginx -t && sudo systemctl reload nginx
```

### Renew SSL Certificate

Certbot auto-renews, but to do it manually:
```bash
sudo certbot renew --dry-run   # test renewal
sudo certbot renew              # actual renewal
```

---

## 🔧 Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `docker: permission denied` | User not in docker group | `sudo usermod -aG docker azureuser && newgrp docker` |
| `502 Bad Gateway` from Nginx | Container not running | `docker ps` → if empty, `docker run ...` again |
| `curl: (7) Failed to connect` | Port 80/443 not open | Check Azure NSG inbound rules |
| GitHub Actions SSH fails | Wrong key format in secret | The secret must start with `-----BEGIN ...` |
| Extension shows "Backend failed" | CORS or wrong URL | Check `API_BASE_URL` in `popup.js` & `allow_origins` in `main.py` |
| Container exits immediately | Model files not in image | Verify `lgbm_model.pkl` is committed and not in `.dockerignore` |
| `OOM Killed` (out of memory) | VM too small | Upgrade to `Standard_B2s` or `Standard_B2ms` |

---

## 💰 Estimated Monthly Cost

| Resource | Tier | Estimated Cost |
|---|---|---|
| Azure VM `Standard_B2s` | Pay-as-you-go | ~$30–35/month |
| VM OS Disk (Standard SSD, 30 GB) | | ~$2/month |
| Outbound bandwidth | First 5 GB free | ~$0–5/month |
| Static Public IP | | ~$3/month |
| **Total** | | **~$35–45/month** |

> **Cost Tip:** Stop the VM (`az vm stop`) when not in use to stop compute charges. The OS disk and IP still cost a small amount, but compute (the main cost) stops.

---

## 📁 Final File Changes Summary

| File | Change |
|---|---|
| `.github/workflows/ci-cd.yml` | Full pipeline: test → build → push → SSH deploy |
| `crome_extension/popup.js` | `API_BASE_URL` updated to Azure domain/IP |
| `crome_extension/manifest.json` | `host_permissions` updated with Azure URL |

---

*Last updated: May 2026*
