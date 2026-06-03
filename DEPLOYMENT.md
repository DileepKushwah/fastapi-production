# Production Deployment Guide: FastAPI AI/Backend Application

This document provides a comprehensive blueprint and step-by-step instructions for deploying, securing, monitoring, and maintaining the FastAPI application in a production environment using Docker, Nginx, PostgreSQL, Redis, and GitHub Actions.

---

## 1. System Architecture

The following diagram illustrates the production traffic flow and monitoring structure:

```mermaid
graph TD
    User([User / Client]) -->|HTTPS: 443| Cloudflare[Cloudflare CDN / DNS]
    Cloudflare -->|HTTPS: 443| Nginx[NGINX Reverse Proxy (Gateway)]
    
    subgraph Docker Bridge Network
        Nginx -->|HTTP: 8000| FastAPI[FastAPI Application (API)]
        FastAPI -->|PostgreSQL Protocol| Postgres[(PostgreSQL Database)]
        FastAPI -->|Redis Protocol| Redis[(Redis Cache)]
        
        Prometheus[Prometheus Server] -->|Scrapes /metrics| FastAPI
        Grafana[Grafana Dashboard] -->|Queries| Prometheus
    end

    subgraph Host System / Backups
        Cron[Cron Daemon] -->|Triggers backup.sh| Postgres
        Postgres -->|Generates sql.gz| BackupsDir[Local Backups Directory]
    end

    classDef external fill:#f9f,stroke:#333,stroke-width:2px;
    classDef network fill:#bbf,stroke:#333,stroke-width:2px;
    classDef storage fill:#ffb,stroke:#333,stroke-width:2px;
    classDef monitoring fill:#fbb,stroke:#333,stroke-width:2px;

    class User,Cloudflare external;
    class Nginx,FastAPI network;
    class Postgres,Redis,BackupsDir storage;
    class Prometheus,Grafana monitoring;
```

---

## 2. Server Provisioning & Hardening

Before deploying the Docker stack, configure the host server (Ubuntu 22.04 LTS recommended) with basic security measures.

### Step 2.1: Add a Deploy User
Do not deploy services as root. Create a dedicated `deploy` user:
```bash
# Add user
sudo adduser deploy

# Grant sudo permissions
sudo usermod -aG sudo deploy

# Add deploy user to docker group (assumes Docker is installed)
sudo usermod -aG docker deploy
```

### Step 2.2: Harden SSH Configuration
Configure SSH key authentication and disable password logins:
1. Copy your SSH public key to `/home/deploy/.ssh/authorized_keys`.
2. Edit `/etc/ssh/sshd_config` and set the following parameters:
   ```text
   PasswordAuthentication no
   PermitRootLogin no
   X11Forwarding no
   MaxAuthTries 3
   ```
3. Restart SSH:
   ```bash
   sudo systemctl restart ssh
   ```

### Step 2.3: Configure UFW Firewall
Allow only Nginx web traffic and SSH:
```bash
# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH and Web Ports
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'

# Enable firewall
sudo ufw enable
```

### Step 2.4: Install and Setup Fail2ban
Fail2ban dynamically bans malicious IP addresses targeting SSH:
```bash
sudo apt-get update && sudo apt-get install -y fail2ban

# Create local configuration file
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Enable SSH jail
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 3. SSL Setup Approach & Certbot Configuration

To secure public endpoints, configure SSL certificates via Let's Encrypt (Certbot) or Cloudflare.

### Option A: Let's Encrypt / Certbot (Recommended for Standalone Domain)

If you have a domain (e.g. `api.yourdomain.com`), automate SSL certificates using the following steps:

1. **Install Certbot** on the host server:
   ```bash
   sudo apt-get install -y certbot
   ```

2. **Deploy the application in HTTP bootstrap mode**:
   Make sure the project is checked out at `/opt/fastapi-production`. Run:
   ```bash
   docker compose up -d
   ```
   *Note: In this state, Nginx is listening on port 80 and forwarding requests to FastAPI. The ACME challenge directory `/var/www/certbot` is mounted.*

3. **Request the Let's Encrypt SSL certificate**:
   ```bash
   sudo certbot certonly --webroot -w /opt/fastapi-production/nginx/certbot_www -d api.yourdomain.com --email admin@yourdomain.com --agree-tos --no-eff-email
   ```

4. **Verify Certificate Generation**:
   Certificates are saved in `/etc/letsencrypt/live/api.yourdomain.com/`.

5. **Transition Nginx to HTTPS**:
   - Open `/opt/fastapi-production/nginx/nginx.conf`.
   - Comment out the port 80 proxy block.
   - Uncomment the HTTP-to-HTTPS redirect and the HTTPS (443) blocks. Replace `api.yourdomain.com` with your domain.
   - Restart Nginx:
     ```bash
     docker compose restart nginx
     ```

6. **Automate Certificate Renewal**:
   Add a renewal cron job or let systemd certbot timers handle it. After renewal, reload Nginx:
   ```bash
   echo "0 12 * * * root certbot renew --quiet && docker kill -s HUP nginx_proxy" | sudo tee -a /etc/crontab
   ```

### Option B: Cloudflare SSL (Alternative Approach)

If you manage DNS through Cloudflare:
1. Set Cloudflare SSL/TLS mode to **Full** or **Full (Strict)**.
2. In Cloudflare, download an **Origin CA certificate** and private key.
3. Place them on your server in `/opt/fastapi-production/nginx/certs/`.
4. Mount them in `docker-compose.yml` and configure Nginx to read them directly, bypassing Let's Encrypt.

---

## 4. Environment Variables Configuration

Create a production `.env` file at the root of `/opt/fastapi-production/` containing:

```env
# Database Settings
POSTGRES_DB=appdb_prod
POSTGRES_USER=dbdeployer
POSTGRES_PASSWORD=YOUR_STRONG_RANDOM_POSTGRES_PASSWORD

# Redis Settings
REDIS_PASSWORD=YOUR_STRONG_RANDOM_REDIS_PASSWORD

# Application Settings
SECRET_KEY=GENERATE_A_64_CHAR_HEX_KEY_FOR_JWT_AND_SIGNING
DEBUG=false
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
DOCKER_IMAGE_NAME=yourdockerusername/fastapi-production

# Monitoring (Grafana Administrator Credentials)
GRAFANA_ADMIN_PASSWORD=YOUR_GRAFANA_PASSWORD
```

---

## 5. CI/CD Pipeline (GitHub Actions)

The pipeline defined in `.github/workflows/deploy.yml` manages continuous integration and delivery.

### How to configure GitHub Repository Secrets:
Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions** and add:
- `DOCKER_USERNAME`: Your Docker Hub username.
- `DOCKER_PASSWORD`: Your Docker Hub Personal Access Token (PAT) or password.
- `SERVER_IP`: The public IP address of your VPS.
- `SERVER_USER`: `deploy` (the user created in Step 2.1).
- `SSH_PRIVATE_KEY`: Paste the raw SSH private key (`id_rsa` or `id_ed25519`) corresponding to the public key authorized on the VPS.

### Pipeline Stages:
1. **Test Phase**: Sets up ephemeral Postgres and Redis service containers in the GitHub Action runner. Runs unit and integration tests (`pytest`).
2. **Build Phase**: Builds the production Docker image using Docker Buildx and pushes it to Docker Hub with tags: `latest` and the unique `commit-sha`.
3. **Deploy Phase**: Establishes an SSH connection to the server, navigates to `/opt/fastapi-production/`, pulls the latest images, and performs a zero-downtime rolling update of the API container.

---

## 6. Zero-Downtime Deployment Details

Zero-downtime deployment is achieved natively through Nginx and Docker Compose:
1. The `api` service configuration in `docker-compose.yml` has a `healthcheck` defined in the Dockerfile, and `order: start-first` under `deploy.update_config`.
2. When the deployment script calls `docker compose up -d --no-deps api`, Docker Compose starts the *new* container first.
3. The *old* container continues serving requests via Nginx.
4. Nginx resolves requests dynamically. Once the new container passes its health checks, Docker Compose cleanly terminates the old container.

---

## 7. Monitoring Setup (Prometheus & Grafana)

Prometheus collects metrics, which are visualized in Grafana.

### Step 7.1: Exposing Metrics
FastAPI is preconfigured with the Prometheus instrumentator which exposes raw metrics on `/metrics`. This endpoint is scraped by the Prometheus container every 5 seconds.

### Step 7.2: Accessing Grafana Securely
To protect system statistics, Grafana is bound to `127.0.0.1:3000` inside `docker-compose.yml`, which prevents public internet access.

To access Grafana from your local machine:
1. Open a secure SSH tunnel from your computer:
   ```bash
   ssh -L 3000:localhost:3000 deploy@YOUR_SERVER_IP
   ```
2. Open your browser and navigate to: `http://localhost:3000`
3. Log in with:
   - **Username**: `admin`
   - **Password**: The password you set for `GRAFANA_ADMIN_PASSWORD` in `.env`.
4. In Grafana:
   - Add a Data Source of type **Prometheus**.
   - Set the URL to: `http://prometheus:9090`
   - Import standard dashboards (e.g. FastAPI dashboard or Node Exporter dashboard).

---

## 8. Backup & Restore Strategy

### Step 8.1: Automated Backups via Cron
Schedule database backups to run automatically every night.

1. Give the script executable permissions:
   ```bash
   chmod +x /opt/fastapi-production/scripts/backup.sh
   ```
2. Edit the crontab for root or deploy user:
   ```bash
   sudo crontab -e
   ```
3. Add the following line to schedule the backup at 2:00 AM daily:
   ```text
   0 2 * * * /opt/fastapi-production/scripts/backup.sh >> /var/log/db_backups.log 2>&1
   ```

### Step 8.2: Database Restore
To restore database data from a `.sql.gz` backup file:
```bash
# 1. Unzip the backup file
gunzip /opt/fastapi-production/backups/backup_appdb_YYYYMMDD_HHMMSS.sql.gz

# 2. Copy the SQL script into the postgres container or feed it directly:
docker exec -i postgres_db psql -U dbdeployer -d appdb_prod < /opt/fastapi-production/backups/backup_appdb_YYYYMMDD_HHMMSS.sql
```

---

## 9. Operations & Troubleshooting

### Check Service Status
```bash
docker compose ps
```

### Read Logs
To tail logs for all services or specific service:
```bash
# All logs
docker compose logs -f

# Just Nginx logs
docker compose logs -f nginx

# Just FastAPI API logs (displays structured JSON logs)
docker compose logs -f api
```

### Inspect Container Health
```bash
docker inspect --format='{{json .State.Health}}' fastapi_app | jq
```
