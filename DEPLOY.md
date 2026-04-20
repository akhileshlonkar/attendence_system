# Deploying the Attendance System to AWS EC2

This guide walks you through deploying the Flask + Gunicorn + Nginx stack
to a single EC2 instance. Estimated time: **~10 minutes**.

Repo: `https://github.com/akhileshlonkar/attendence_system`

---

## 1. Launch an EC2 instance

1. Sign in to the [AWS Console](https://console.aws.amazon.com/ec2/).
2. Click **Launch instance** and fill in:
   - **Name:** `attendance-system`
   - **AMI:** Ubuntu Server 24.04 LTS (free-tier eligible)
   - **Instance type:** `t2.micro` or `t3.micro` (free-tier eligible)
   - **Key pair:** create a new one (e.g. `attendance-key`) and download the `.pem` file — keep it safe.
   - **Network settings → Security group:** create a new one and allow:
     - **SSH** (port 22) from *My IP*
     - **HTTP** (port 80) from *Anywhere (0.0.0.0/0)*
     - *(Optional)* **HTTPS** (port 443) from Anywhere
   - **Storage:** 8 GiB (default) is fine.
3. Click **Launch instance**.
4. Once running, copy the instance's **Public IPv4 address** (e.g. `3.110.45.12`).

## 2. SSH into the instance

From PowerShell on your Windows machine (in the folder where you saved the `.pem` file):

```powershell
# Restrict key permissions (Windows requires this)
icacls .\attendance-key.pem /inheritance:r
icacls .\attendance-key.pem /grant:r "$($env:USERNAME):(R)"

# Connect
ssh -i .\attendance-key.pem ubuntu@<EC2_PUBLIC_IP>
```

If this is your first connection, type `yes` to accept the host key.

## 3. Run the one-shot setup script

Paste this **single command** on the EC2 shell — it installs everything,
clones the repo, sets up Gunicorn as a systemd service, and configures Nginx:

```bash
curl -fsSL https://raw.githubusercontent.com/akhileshlonkar/attendence_system/main/deploy/setup_ec2.sh | bash
```

When it finishes you should see:

```
Deployed!  Visit:  http://<EC2_PUBLIC_IP>/
Health:          http://<EC2_PUBLIC_IP>/api/health
```

Open that URL in your browser — you should see the attendance dashboard.

## 4. (Optional) Seed sample data

Still on the EC2 shell:

```bash
cd /home/ubuntu/attendance-system
source .venv/bin/activate
# seed.py posts to localhost:5000 by default — override via env if needed
python seed.py
```

Or just use the web form on the dashboard.

## 5. Updating after new commits

Whenever you `git push` changes from your laptop, redeploy on EC2 with:

```bash
bash /home/ubuntu/attendance-system/deploy/update.sh
```

## 6. Useful operational commands

```bash
# Tail the app logs
sudo journalctl -u attendance -f

# Restart app
sudo systemctl restart attendance

# Restart nginx
sudo systemctl restart nginx

# Check service status
sudo systemctl status attendance
```

## 7. (Optional) HTTPS with a free Let's Encrypt certificate

Only works if you point a domain name at the EC2 public IP (via an A-record).
Then on the EC2 instance:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

## Architecture overview

```
          Internet (port 80)
                 │
         ┌───────▼───────┐
         │    Nginx      │   reverse proxy, static files
         └───────┬───────┘
                 │  127.0.0.1:8000
         ┌───────▼───────┐
         │   Gunicorn    │   3 workers, systemd-managed
         └───────┬───────┘
                 │
         ┌───────▼───────┐
         │  Flask app.py │   SQLite + hdfs_store + cloud_store
         └───────────────┘
```

## Troubleshooting

- **502 Bad Gateway** → Gunicorn isn't running. `sudo journalctl -u attendance -n 50` to see why.
- **Cannot connect at all** → Security group is blocking port 80. Edit the SG in AWS Console.
- **Permission denied (publickey) on SSH** → wrong key, or the key file permissions are too open (run the `icacls` commands above).
- **Uploads > 1 MB fail** → already handled via `client_max_body_size 100M` in `deploy/nginx.conf`.
