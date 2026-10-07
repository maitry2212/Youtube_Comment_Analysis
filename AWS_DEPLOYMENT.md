# 🚀 AWS Deployment Guide — YouTube Comment Analysis API

A **complete, step-by-step** guide to deploy the FastAPI sentiment analysis backend on an AWS **EC2 Instance** (Ubuntu), wire up a **CI/CD pipeline** via GitHub Actions, and finally point your **Chrome Extension** at the live server.

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
                                 │ SSH into EC2
  Chrome Extension  ──HTTPS──►  ┌▼──────────────────────────┐
  (popup.js)                    │  AWS EC2 (Ubuntu 22.04)   │
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
| Server | AWS EC2 — Ubuntu 22.04 LTS |
| Reverse Proxy | Nginx + SSL (Let's Encrypt) |
| CI/CD | GitHub Actions |
| Client | Chrome Extension |

---

## 📋 Pre-Deployment Checklist

Before touching AWS, confirm these on your **local machine**:

- [ ] `lgbm_model.pkl` and `tfidf_vectorizer.pkl` exist in the project root
- [ ] `docker build -t yt-analysis .` succeeds locally
- [ ] `docker run -p 8000:8000 yt-analysis` — `GET http://localhost:8000/` returns `{"message":"Welcome to FastAPI Sentiment API"}`
- [ ] You have a [DockerHub](https://hub.docker.com) account (`kartik87580`)
- [ ] You have an [AWS account](https://console.aws.amazon.com) with an active subscription
- [ ] You have a GitHub repo with Actions enabled

---

## PHASE 1 — Create the AWS EC2 Instance

### Step 1.1 — Log in to AWS Console

1. Go to [https://console.aws.amazon.com](https://console.aws.amazon.com)
2. Sign in with your AWS account.

---

### Step 1.2 — Navigate to EC2

1. In the search bar, type **"EC2"** → Click **EC2**
2. In the left sidebar, click **Instances** → **Launch instances**

---

### Step 1.3 — Launch the EC2 Instance

Fill in the launch wizard:

| Field | Value |
|---|---|
| **Name** | `yt-sentiment-vm` |
| **AMI (Image)** | `Ubuntu Server 22.04 LTS (HVM), SSD Volume Type` — 64-bit (x86) |
| **Instance type** | `t3.small` (2 vCPU, 2 GB RAM) — recommended |
| **Key pair** | Click **Create new key pair** → Name: `yt-sentiment-key` → Type: RSA → Format: `.pem` → **Create** |
| **Storage** | 20 GB `gp3` (default) |

> **💡 Instance Type Note:** `t3.small` costs ~$15/month and handles LightGBM inference + matplotlib chart generation. `t3.micro` (1 GB RAM) is too small for this workload (Free Tier eligible but will cause OOM).

**Network Settings** (click **Edit**):

| Setting | Value |
|---|---|
| **VPC** | Default VPC |
| **Auto-assign public IP** | Enable |
| **Security group name** | `yt-sentiment-sg` |
| **Inbound rules** | Add: SSH (22), HTTP (80), HTTPS (443) |

> We do **NOT** open port `8000` publicly — Nginx will proxy it.

Click **Launch instance**. Wait ~1 minute.

After launch, go to **Instances** → click your instance → note the **Public IPv4 address** (e.g., `54.123.45.67`). This is your `<YOUR_EC2_PUBLIC_IP>`.

---

### Step 1.4 — Connect to the EC2 Instance via SSH

On your **local machine** (Windows PowerShell):

```powershell
# Fix permissions on the key file (Windows equivalent)
icacls "C:\path\to\yt-sentiment-key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"

# SSH into the EC2 instance
ssh -i "C:\path\to\yt-sentiment-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP>
```

> **Note:** AWS Ubuntu AMIs use `ubuntu` as the default username (not `azureuser`).

You should see a `ubuntu@ip-xxx-xxx-xxx-xxx:~$` prompt. All remaining commands in **Phase 2** run inside this SSH session.

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
sudo usermod -aG docker ubuntu
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

Paste the following (replace `YOUR_EC2_PUBLIC_IP` with your actual EC2 public IP or domain):

```nginx
server {
    listen 80;
    server_name <YOUR_EC2_PUBLIC_IP>;

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

If you have a domain name (e.g., from Namecheap/Cloudflare), point an **A record** to your EC2 IP, then:

```bash
sudo certbot --nginx -d yourdomain.com
# Follow prompts: enter email, agree to TOS, choose to redirect HTTP → HTTPS
```

> **No domain?** You can skip this and use `http://<EC2_PUBLIC_IP>` directly. The Chrome Extension will still work.

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

At this point your API is live at `http://<EC2_IP>/` through Nginx. ✅

---

## PHASE 3 — CI/CD Pipeline (GitHub Actions)

The goal: every `git push` to `main` automatically:
1. Runs syntax checks
2. Builds and pushes the Docker image to DockerHub
3. SSHes into the AWS EC2 instance and restarts the container with the new image

### Step 3.1 — Add GitHub Repository Secrets

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

Add these secrets:

| Secret Name | Value | Where to get it |
|---|---|---|
| `DOCKER_USERNAME` | `kartik87580` | Your DockerHub username |
| `DOCKER_PASSWORD` | Your DockerHub password or [Access Token](https://hub.docker.com/settings/security) | DockerHub → Account Settings → Security |
| `AWS_EC2_HOST` | `54.123.45.67` | EC2 Public IP from AWS Console |
| `AWS_EC2_USER` | `ubuntu` | Default Ubuntu AMI username |
| `AWS_EC2_SSH_KEY` | The **full contents** of `yt-sentiment-key.pem` | Open the `.pem` file in a text editor, copy everything |

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
  # JOB 3: SSH into AWS EC2 and deploy
  # ──────────────────────────────────────────────
  deploy:
    name: 🚀 Deploy to AWS EC2
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.AWS_EC2_HOST }}
          username: ${{ secrets.AWS_EC2_USER }}
          key: ${{ secrets.AWS_EC2_SSH_KEY }}
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
git commit -m "ci: add full AWS EC2 deployment pipeline"
git push origin main
```

---

### Step 3.3 — Verify the Pipeline Runs

1. In GitHub → **Actions** tab — you should see the workflow running.
2. All 3 jobs should turn green ✅.
3. After the `deploy` job completes, verify on the EC2 instance:

```bash
# SSH into EC2
ssh -i "yt-sentiment-key.pem" ubuntu@<YOUR_EC2_IP>

# Check the container is running
docker ps

# Test the endpoint
curl http://localhost:8000/
```

---

## PHASE 4 — Connect the Chrome Extension

The Chrome Extension currently points to `http://localhost:8000`. You need to update it to point to your live AWS EC2 instance.

### Step 4.1 — Update `popup.js`

Open `crome_extension/popup.js` and change **line 1**:

```javascript
// BEFORE (local development):
const API_BASE_URL = "http://localhost:8000";

// AFTER (production — choose one of these):
// Option A: If you set up a domain with SSL:
const API_BASE_URL = "https://yourdomain.com";

// Option B: If using just the EC2 IP (no SSL):
const API_BASE_URL = "http://54.123.45.67";  // replace with your actual EC2 IP
```

> **⚠️ Important:** If you use `http://` (no SSL), Chrome may block requests from the extension as "mixed content" on some pages. Setting up a domain + SSL via Let's Encrypt (Step 2.5) is strongly recommended for a production extension.

---

### Step 4.2 — Update `manifest.json` Host Permissions

Open `crome_extension/manifest.json` and update the `host_permissions` (or `permissions`) to include your AWS URL:

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
    "http://54.123.45.67/*"
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
# SSH into EC2
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
| `docker: permission denied` | User not in docker group | `sudo usermod -aG docker ubuntu && newgrp docker` |
| `502 Bad Gateway` from Nginx | Container not running | `docker ps` → if empty, `docker run ...` again |
| `curl: (7) Failed to connect` | Port 80/443 not open in Security Group | Go to EC2 → Security Groups → Edit inbound rules → Add HTTP & HTTPS |
| GitHub Actions SSH fails | Wrong key format in secret | The secret must start with `-----BEGIN ...` |
| Extension shows "Backend failed" | CORS or wrong URL | Check `API_BASE_URL` in `popup.js` & `allow_origins` in `main.py` |
| Container exits immediately | Model files not in image | Verify `lgbm_model.pkl` is committed and not in `.dockerignore` |
| `OOM Killed` (out of memory) | VM too small | Upgrade from `t3.micro` to `t3.small` or `t3.medium` |
| Can't SSH into instance | Key permissions too open | Run `chmod 400 yt-sentiment-key.pem` (Linux/Mac) or `icacls` fix (Windows) |

---

## 💰 Estimated Monthly Cost

| Resource | Tier | Estimated Cost |
|---|---|---|
| EC2 `t3.small` | On-Demand | ~$15/month |
| EBS Storage (20 GB gp3) | | ~$1.6/month |
| Outbound bandwidth | First 100 GB free | ~$0/month |
| Elastic IP (static IP) | Free when attached to running instance | ~$0–3.6/month |
| **Total** | | **~$17–20/month** |

> **Cost Tip:** Stop the EC2 instance (`Instance state → Stop`) when not in use to pause compute charges. Storage and Elastic IP may still incur small costs.
> **Free Tier:** New AWS accounts get 750 hrs/month of `t2.micro` or `t3.micro` free for 12 months — but these are too small for this workload.

---

## 🔄 Key Differences from Azure Deployment

| | Azure | AWS |
|---|---|---|
| **VM Service** | Virtual Machines | EC2 (Elastic Compute Cloud) |
| **Resource grouping** | Resource Group | No equivalent needed (default VPC) |
| **Default SSH user** | `azureuser` | `ubuntu` |
| **Firewall rules** | Network Security Group (NSG) | Security Group |
| **Instance type** | `Standard_B2s` | `t3.small` |
| **GitHub Secret: Host** | `AZURE_VM_HOST` | `AWS_EC2_HOST` |
| **GitHub Secret: User** | `AZURE_VM_USER` | `AWS_EC2_USER` |
| **GitHub Secret: Key** | `AZURE_VM_SSH_KEY` | `AWS_EC2_SSH_KEY` |
| **Est. monthly cost** | ~$35–45/month | ~$17–20/month |

---

## 📁 Final File Changes Summary

| File | Change |
|---|---|
| `.github/workflows/ci-cd.yml` | Updated secrets from `AZURE_VM_*` → `AWS_EC2_*` |
| `crome_extension/popup.js` | `API_BASE_URL` updated to AWS EC2 domain/IP |
| `crome_extension/manifest.json` | `host_permissions` updated with AWS URL |

---

*Last updated: June 2026*
