# Installation Guide

This guide will help you install and set up EduSphere on your local machine or development environment.

## Prerequisites

Before installing EduSphere, ensure you have the following installed:

- **Python 3.8 or higher** - [Download Python](https://www.python.org/downloads/)
- **pip** (Python package manager) - Usually included with Python
- **Git** (optional, for cloning the repository) - [Download Git](https://git-scm.com/downloads)

## Installation Steps

### 1. Clone the Repository

If you have Git installed, clone the repository:

```bash
git clone https://github.com/yourusername/EduSphere.git
cd EduSphere
```

Alternatively, download the ZIP file from GitHub and extract it to your desired location.

### 2. Create a Virtual Environment (Recommended)

Creating a virtual environment isolates your project dependencies from your system Python.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your command prompt, indicating the virtual environment is active.

### 3. Install Dependencies

Install all required Python packages using the requirements.txt file:

```bash
pip install -r requirements.txt
```

This will install:
- Flask 3.0.0
- python-dotenv 1.0.0
- Werkzeug 3.0.1
- fpdf2 2.8.7
- reportlab 4.0.7

### 4. Configure Environment Variables

Copy the example environment file and customize it:

**Windows:**
```bash
copy .env.example .env
```

**macOS/Linux:**
```bash
cp .env.example .env
```

Edit the `.env` file with your preferred text editor and set the following variables:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here-change-in-production
FLASK_ENV=development
FLASK_DEBUG=1

# Database Configuration
DATABASE_URL=sqlite:///instance/database.db

# Session Configuration
SESSION_TIMEOUT=3600

# Upload Configuration
MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=static/uploads/profiles

# Application Configuration
APP_NAME=EduSphere
APP_URL=http://localhost:5000
```

**Important:** Generate a secure `SECRET_KEY` for production. You can use Python to generate one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Initialize the Database

The database will be automatically created on first run. No manual initialization is required.

The database file will be created in the `instance/` directory as `database.db`.

### 6. Run the Application

Start the Flask development server:

```bash
python app.py
```

You should see output similar to:

```
 * Running on http://127.0.0.1:5000
 * Running on http://localhost:5000
```

### 7. Access the Application

Open your web browser and navigate to:

```
http://localhost:5000
```

## Default Login Credentials

### Admin Account

- **Email:** `admin@mail.com`
- **Password:** `admin`

⚠️ **Security Warning:** Change the default admin password immediately after first login!

## Troubleshooting

### Port Already in Use

If you see an error that port 5000 is already in use, you can either:

1. Stop the process using port 5000, or
2. Run the app on a different port:

```bash
python app.py -p 5001
```

### Module Not Found Errors

If you encounter "ModuleNotFoundError", ensure you've activated your virtual environment and installed dependencies:

```bash
# Activate virtual environment (if not already active)
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

### Database Errors

If you encounter database-related errors:

1. Delete the `instance/database.db` file
2. Restart the application
3. The database will be recreated automatically

### Permission Errors

If you encounter permission errors when creating files:

**Windows:** Run your terminal/command prompt as Administrator

**macOS/Linux:** Use `sudo` for commands that require elevated permissions (not recommended for development)

## Development Setup

For development, you may want to enable additional debugging features:

1. Set `FLASK_DEBUG=1` in your `.env` file
2. The application will automatically reload on code changes
3. Detailed error messages will be displayed in the browser

## Production Setup

For production deployment, refer to the [Deployment Guide](DEPLOYMENT.md).

Key differences for production:

- Set `FLASK_DEBUG=0`
- Use a strong, randomly generated `SECRET_KEY`
- Use a production-grade WSGI server (e.g., Gunicorn)
- Configure proper logging
- Set up HTTPS/SSL
- Use a production database (e.g., PostgreSQL)

## Next Steps

After installation:

1. Log in as the default admin
2. Change the admin password
3. Add faculty accounts
4. Create classrooms
5. Create exams
6. Add students to classrooms

For detailed guides on using EduSphere, see:
- [Admin Guide](ADMIN_GUIDE.md)
- [Faculty Guide](FACULTY_GUIDE.md)
- [Student Guide](STUDENT_GUIDE.md)

## Support

If you encounter issues not covered in this guide:

1. Check the [GitHub Issues](https://github.com/yourusername/EduSphere/issues)
2. Review the [API Documentation](API_DOCUMENTATION.md)
3. Check the [Database Schema](DATABASE_SCHEMA.md)

## Uninstallation

To completely remove EduSphere from your system:

1. Deactivate the virtual environment:
   ```bash
   deactivate
   ```

2. Delete the project directory:
   ```bash
   # Windows
   rmdir /s EduSphere
   
   # macOS/Linux
   rm -rf EduSphere
   ```

3. Delete the virtual environment (if it's outside the project directory)
