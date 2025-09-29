# 🚀 Quick Start Guide

## 📦 Install Dependencies

### Backend (Python)
```bash
pip install -r requirements.txt
```

### Frontend (Node.js)
```bash
cd frontend
npm install
cd ..
```

## 🔧 Development Mode

### Option 1: Automated Start
```bash
# Windows
start-dev.bat
```

### Option 2: Manual Start
```bash
# Terminal 1 - Flask Backend
python app.py

# Terminal 2 - Vue Frontend
cd frontend
npm run dev
```

**Access:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:5000/api

## 🏗️ Production Mode

### Build & Deploy
```bash
# Windows
build-prod.bat

# Linux/Mac
./build-prod.sh
```

### Start Production Server
```bash
python app.py
```

**Access:**
- Application: http://localhost:5000

## 🔗 Environment Setup

Set Snowflake connection:
```bash
export SNOWFLAKE_CONNECTION='{"account":"...","user":"...","password":"..."}'
```

---
**That's it!** 🎉