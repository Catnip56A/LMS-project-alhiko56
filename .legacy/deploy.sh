#!/bin/bash

# Yonca Flask App Deployment Script
# Run this script on your Ubuntu VPS

set -e

echo "🚀 Starting Yonca deployment..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required packages
echo "📦 Installing required packages..."
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx certbot python3-certbot-nginx

# Create database and user
echo "🗄️ Setting up PostgreSQL..."

# Check and create database if it doesn't exist
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='yonca_db'" 2>/dev/null || echo "0")
if [ "$DB_EXISTS" != "1" ]; then
    sudo -u postgres psql -c "CREATE DATABASE yonca_db;"
    echo "Database yonca_db created."
else
    echo "Database yonca_db already exists, skipping creation."
fi

# Check and create user if it doesn't exist
USER_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='yonca_user'" 2>/dev/null || echo "0")
if [ "$USER_EXISTS" != "1" ]; then
    sudo -u postgres psql -c "CREATE USER yonca_user WITH PASSWORD 'ALHIKO3325!56Catnip?!';"
    echo "User yonca_user created."
else
    echo "User yonca_user already exists, skipping creation."
fi

# Grant privileges (safe to run even if already granted)
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE yonca_db TO yonca_user;"
sudo -u postgres psql -d yonca_db -c "GRANT ALL ON SCHEMA public TO yonca_user;"

# Temporarily grant superuser privileges to allow altering existing tables
sudo -u postgres psql -c "ALTER USER yonca_user SUPERUSER;"

# Reset migration state if needed
sudo -u postgres psql -d yonca_db -c "DROP TABLE IF EXISTS alembic_version;"

# Create application directory
echo "📁 Creating application directory..."
sudo mkdir -p /home/magsud/work/Yonca
sudo chown -R magsud:magsud /home/magsud/work/Yonca

# Clone or copy your application code here
echo "📋 Your Yonca application code should be in /home/magsud/work/Yonca"
echo "Since you mentioned the files are already there, we'll proceed..."
# read -p "Press Enter after you've copied the code..."

# Set up Python virtual environment
echo "🐍 Setting up Python virtual environment..."
cd /home/magsud/work/Yonca
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt

# Set up environment variables
echo "🔧 Creating environment configuration..."
cat > .env << EOF
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this-in-production
DATABASE_URL=postgresql://yonca_user:ALHIKO3325Catnip21@localhost:5432/yonca_db
EOF

# Run database migrations
echo "🗃️ Running database migrations..."
flask db stamp head

# Revoke superuser privileges
sudo -u postgres psql -c "ALTER USER yonca_user NOSUPERUSER;"

# Copy systemd service file
echo "⚙️ Setting up systemd service..."
sudo cp deploy/yonca.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable yonca

# Copy nginx configuration
echo "🌐 Setting up nginx..."
sudo cp deploy/yonca.nginx /etc/nginx/sites-available/yonca
sudo ln -sf /etc/nginx/sites-available/yonca /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# Start the application
echo "▶️ Starting the application..."
sudo systemctl start yonca

echo "✅ Deployment completed!"
echo ""
echo "Next steps:"
echo "1. Update your domain DNS to point to this VPS IP"
echo "2. Run: sudo certbot --nginx -d your-domain.com"
echo "3. Check logs: sudo journalctl -u yonca -f"
echo "4. Visit your domain to test the application"