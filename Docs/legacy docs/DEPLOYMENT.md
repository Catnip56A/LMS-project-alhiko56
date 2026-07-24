# VPS Deployment Guide

This guide will help you deploy the LMS Flask application to a VPS (Virtual Private Server).

## Prerequisites

- A VPS with Ubuntu 20.04+ (recommended: 2GB RAM, 1 CPU)
- A domain name pointing to your VPS IP
- SSH access to your VPS

## Recommended VPS Providers

- **DigitalOcean** ($6/month droplet)
- **Linode** ($5/month VPS)
- **Vultr** ($2.50/month VPS)
- **AWS Lightsail** ($3.50/month)

## Step 1: VPS Setup

### 1.1 Create VPS Instance
1. Sign up for a VPS provider
2. Create a new Ubuntu 20.04/22.04 instance
3. Note down the IP address and SSH credentials

### 1.2 Initial Server Setup
```bash
# Connect to your VPS
ssh root@your-vps-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib caddy ufw

# Configure firewall
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable
```

## Step 2: Database Setup

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE lms_db;
CREATE USER lms_user WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE lms_db TO lms_user;
\q
```

## Step 3: Application Deployment

### 3.1 Upload Code
```bash
# Create application directory
sudo mkdir -p /var/www/lms
sudo chown -R $USER:www-data /var/www/lms

# Upload your code (replace with your method)
# Option 1: Git clone
git clone https://github.com/yourusername/lms.git /var/www/lms

# Option 2: SCP from local machine
# scp -r /path/to/lms user@your-vps-ip:/var/www/
```

### 3.2 Setup Python Environment
```bash
cd /var/www/lms

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-prod.txt
```

### 3.3 Configure Environment
```bash
# Create .env file
nano .env

# Add the following content:
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this-make-it-long-and-random
DATABASE_URL=postgresql://lms_user:your_secure_password_here@localhost:5432/lms_db
```

### 3.4 Database Migration
```bash
# Run database migrations
flask db upgrade
```

## Step 4: Web Server Setup

### 4.1 Gunicorn (WSGI Server)
```bash
# Copy systemd service file
sudo cp deploy/lms.service /etc/systemd/system/

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable lms
sudo systemctl start lms
```

### 4.2 Caddy (Web Server & Reverse Proxy)
```bash
# Copy Caddyfile configuration
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile

# Update domain name in Caddyfile
sudo nano /etc/caddy/Caddyfile
# Change: your-domain.com to your actual domain

# Enable and start Caddy
sudo systemctl enable caddy
sudo systemctl start caddy

# Caddy will automatically obtain SSL certificates from Let's Encrypt
```

## Step 5: SSL Certificate (HTTPS)

Caddy automatically handles SSL certificate issuance and renewal from Let's Encrypt. No additional configuration is required - SSL certificates will be obtained automatically when you access your domain.

```bash
# Check Caddy status
sudo systemctl status caddy

# View Caddy logs
sudo journalctl -u caddy -f
```

## Step 6: Final Checks

### 6.1 Test Application
```bash
# Check if service is running
sudo systemctl status lms

# Check logs
sudo journalctl -u lms -f

# Test Caddy
curl http://localhost
```

### 6.2 Update DNS
- Point your domain A record to the VPS IP address
- Wait for DNS propagation (can take up to 24 hours)

## Troubleshooting

### Common Issues

1. **Application not starting**
   ```bash
   sudo journalctl -u lms -n 50
   ```

2. **Database connection issues**
   - Check DATABASE_URL in .env
   - Verify PostgreSQL is running: `sudo systemctl status postgresql`

3. **Static files not loading**
   - Check Caddy configuration in /etc/caddy/Caddyfile
   - Verify static folder permissions
   - Check Caddy logs: `sudo journalctl -u caddy -f`

4. **Permission issues**
   ```bash
   sudo chown -R $USER:www-data /var/www/lms
   sudo chmod -R 755 /var/www/lms
   ```

## Maintenance

### Updates
```bash
# Pull latest code
cd /var/www/lms
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements-prod.txt

# Run migrations if needed
flask db upgrade

# Restart service
sudo systemctl restart lms
```

### Backups
```bash
# Database backup
sudo -u postgres pg_dump lms_db > lms_backup_$(date +%Y%m%d).sql

# File backup
tar -czf lms_files_$(date +%Y%m%d).tar.gz /var/www/lms
```

## Security Checklist

- [ ] Changed default SSH port (optional)
- [ ] Disabled root login via SSH
- [ ] Configured UFW firewall
- [ ] SSL certificate installed
- [ ] Strong database password
- [ ] SECRET_KEY is long and random
- [ ] File permissions are correct
- [ ] Regular backups configured