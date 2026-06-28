# Deployment Guide

This guide covers deploying EduSphere to production environments, with a focus on Render.com as the primary deployment platform.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Render Deployment](#render-deployment)
- [Manual Deployment (VPS)](#manual-deployment-vps)
- [Docker Deployment](#docker-deployment)
- [Environment Configuration](#environment-configuration)
- [Security Best Practices](#security-best-practices)
- [Post-Deployment Checklist](#post-deployment-checklist)

## Prerequisites

Before deploying to production, ensure you have:

- A GitHub repository with the EduSphere code
- A Render.com account (free tier available)
- Basic knowledge of Git and command line
- A domain name (optional, for custom domain)

## Render Deployment

Render is a cloud platform that makes deploying Flask applications simple and free for small projects.

### Step 1: Push to GitHub

1. Initialize Git in your project (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. Create a new repository on GitHub
3. Add the remote and push:
   ```bash
   git remote add origin https://github.com/yourusername/EduSphere.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Create Render Account

1. Sign up at [render.com](https://render.com)
2. Connect your GitHub account
3. Authorize Render to access your repository

### Step 3: Create Web Service

1. Click **"New +"** in Render dashboard
2. Select **"Web Service"**
3. Connect your GitHub repository
4. Configure the service:

   **Name:** `edusphere` (or your preferred name)

   **Region:** Choose the region closest to your users

   **Branch:** `main`

   **Runtime:** `Python 3`

   **Build Command:**
   ```bash
   pip install -r requirements.txt
   ```

   **Start Command:**
   ```bash
   python app.py
   ```

5. Click **"Advanced"** and add environment variables:

   ```env
   SECRET_KEY=your-secure-random-secret-key
   FLASK_ENV=production
   FLASK_DEBUG=0
   DATABASE_URL=sqlite:///instance/database.db
   SESSION_TIMEOUT=3600
   MAX_CONTENT_LENGTH=16777216
   UPLOAD_FOLDER=static/uploads/profiles
   APP_NAME=EduSphere
   APP_URL=https://your-app-name.onrender.com
   ```

6. Click **"Create Web Service"**

### Step 4: Wait for Deployment

Render will automatically:
- Clone your repository
- Install dependencies
- Start the application
- Provide a public URL

The deployment typically takes 2-5 minutes.

### Step 5: Access Your Application

Once deployed, you'll receive a URL like:
```
https://edusphere-xxxx.onrender.com
```

Access this URL in your browser to verify the deployment.

### Step 6: Configure Custom Domain (Optional)

1. Purchase a domain from a registrar (e.g., Namecheap, GoDaddy)
2. In Render, go to your web service settings
3. Click **"Domains"** → **"Add Domain”**
4. Enter your domain name
5. Follow the DNS instructions provided by Render
6. Enable SSL certificate (automatic on Render)

## Manual Deployment (VPS)

For more control, you can deploy to a VPS (Virtual Private Server) like DigitalOcean, Linode, or AWS EC2.

### Step 1: Server Setup

Connect to your VPS via SSH:
```bash
ssh user@your-server-ip
```

Update the system:
```bash
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
```

Install required packages:
```bash
sudo apt install python3 python3-pip python3-venv nginx -y
```

### Step 2: Clone the Repository

```bash
cd /var/www
sudo git clone https://github.com/yourusername/EduSphere.git
sudo chown -R $USER:$USER EduSphere
cd EduSphere
```

### Step 3: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### Step 4: Configure Environment

```bash
cp .env.example .env
nano .env
```

Set production values:
```env
SECRET_KEY=your-secure-random-secret-key
FLASK_ENV=production
FLASK_DEBUG=0
APP_URL=https://your-domain.com
```

### Step 5: Create Systemd Service

Create a service file:
```bash
sudo nano /etc/systemd/system/edusphere.service
```

Add the following:
```ini
[Unit]
Description=EduSphere Flask Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/EduSphere
Environment="PATH=/var/www/EduSphere/venv/bin"
ExecStart=/var/www/EduSphere/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Start and enable the service:
```bash
sudo systemctl start edusphere
sudo systemctl enable edusphere
sudo systemctl status edusphere
```

### Step 6: Configure Nginx

Create Nginx configuration:
```bash
sudo nano /etc/nginx/sites-available/edusphere
```

Add the following:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /var/www/EduSphere/static;
    }

    location /uploads {
        alias /var/www/EduSphere/static/uploads;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/edusphere /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 7: Configure SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## Docker Deployment

For containerized deployment, use Docker.

### Step 1: Create Dockerfile

Create a `Dockerfile` in the project root:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static/uploads/profiles

EXPOSE 5000

CMD ["python", "app.py"]
```

### Step 2: Create .dockerignore

Create a `.dockerignore` file:

```
venv/
__pycache__/
*.pyc
.env
instance/
.git
.gitignore
```

### Step 3: Build and Run

Build the image:
```bash
docker build -t edusphere .
```

Run the container:
```bash
docker run -p 5000:5000 \
  -e SECRET_KEY=your-secret-key \
  -e FLASK_ENV=production \
  -e FLASK_DEBUG=0 \
  edusphere
```

### Step 4: Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - FLASK_ENV=production
      - FLASK_DEBUG=0
    volumes:
      - ./instance:/app/instance
      - ./static/uploads:/app/static/uploads
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

## Environment Configuration

### Production Environment Variables

Always set these in production:

```env
# Security
SECRET_KEY=use-a-strong-random-key-at-least-32-characters
FLASK_ENV=production
FLASK_DEBUG=0

# Database (consider PostgreSQL for production)
DATABASE_URL=postgresql://user:password@host:port/database

# Session
SESSION_TIMEOUT=3600

# Uploads
MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=static/uploads/profiles

# Application
APP_NAME=EduSphere
APP_URL=https://your-production-domain.com
```

### Generating a Secure Secret Key

Use Python to generate a secure key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Security Best Practices

### 1. Use HTTPS

Always use HTTPS in production. Render provides free SSL certificates. For manual deployment, use Let's Encrypt.

### 2. Secure Secret Key

- Never commit `.env` to version control
- Use a strong, randomly generated secret key
- Rotate the secret key periodically

### 3. Database Security

- Use a production-grade database (PostgreSQL recommended)
- Never commit database files to version control
- Use environment variables for database credentials
- Enable database backups

### 4. File Uploads

- Validate file types and sizes
- Scan uploaded files for malware
- Store uploads outside the web root if possible
- Use cloud storage (S3, etc.) for production

### 5. Dependencies

- Keep dependencies updated
- Use `pip-audit` to check for vulnerabilities:
  ```bash
  pip install pip-audit
  pip-audit
  ```

### 6. Logging

- Enable proper logging in production
- Monitor logs for suspicious activity
- Set up log rotation

### 7. Rate Limiting

Consider implementing rate limiting to prevent abuse:
```bash
pip install flask-limiter
```

## Post-Deployment Checklist

After deploying, verify the following:

- [ ] Application loads correctly in browser
- [ ] All pages are accessible
- [ ] User registration and login work
- [ ] File uploads function properly
- [ ] Database operations work correctly
- [ ] SSL certificate is valid (HTTPS works)
- [ ] Environment variables are set correctly
- [ ] Logs are being generated
- [ ] Error pages display correctly
- [ ] Static files load properly
- [ ] Session management works
- [ ] Default admin password is changed

## Monitoring and Maintenance

### Health Checks

Set up health checks to monitor application uptime:

```python
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200
```

### Backup Strategy

- Regular database backups
- Backup uploaded files
- Document recovery procedures

### Updates

- Update dependencies regularly
- Test updates in staging first
- Keep the application updated with security patches

## Troubleshooting

### Application Won't Start

1. Check logs: `journalctl -u edusphere -f` (systemd) or Render logs
2. Verify environment variables are set
3. Check port availability
4. Verify dependencies are installed

### Database Connection Errors

1. Verify database URL is correct
2. Check database credentials
3. Ensure database server is running
4. Check network connectivity

### Static Files Not Loading

1. Verify static file paths
2. Check Nginx configuration
3. Ensure files exist in the correct location
4. Check file permissions

## Scaling Considerations

For high-traffic deployments:

1. **Database:** Use PostgreSQL or MySQL instead of SQLite
2. **Caching:** Implement Redis for session storage and caching
3. **Load Balancing:** Use multiple load-balanced instances
4. **CDN:** Use a CDN for static assets
5. **Monitoring:** Implement application monitoring (Sentry, New Relic)

## Support

For deployment issues:

1. Check Render documentation: [docs.render.com](https://docs.render.com)
2. Review Flask deployment guide: [flask.palletsprojects.com](https://flask.palletsprojects.com)
3. Open an issue on GitHub

## Cost Considerations

### Render Free Tier

- Free web service with 512MB RAM
- Sleeps after 15 minutes of inactivity
- Cold starts may take 30-60 seconds
- Suitable for development and small projects

### Render Paid Plans

- Starting at $7/month for 512MB RAM
- No sleep time
- Faster cold starts
- Better for production

### VPS Costs

- DigitalOcean: $4-6/month for basic droplet
- Linode: $5/month for basic instance
- AWS EC2: Free tier available, then ~$8/month

Choose the option that fits your budget and requirements.
