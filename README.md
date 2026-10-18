# ✚ MedNear — Precision Medicine & Real-Time Pharmacy Stock Locator

MedNear is a healthcare web platform connecting patients with local partner pharmacies. It features PMC5570547 pharmacogenomic risk alerts, real-time inventory tracking, customer 30-minute hold reservations with OTP verification, turn-by-turn navigation, and Twilio SMS / WhatsApp notifications.

---

## 🌟 Key Features

1. **Precision Medicine & Pharmacogenomic Decision Support (PMC5570547)**
   - Live germline allele annotations for `CYP2C19`, `SLCO1B1`, and other clinical markers.
   - Real-time clinical actionability badges (🟢 Favorable, 🟡 Caution / Dose Adjustment, 🔴 High Risk / Black Box Warning).
   - Cost-effective generic substitute recommendations with calculated patient savings.

2. **OpenStreetMap Nominatim Geocoding & Leaflet Map**
   - Autocomplete search translating neighborhood names, landmarks, or PIN codes into exact GPS coordinates.
   - Interactive map with dynamic store markers, stock status badges, and route distance calculation.

3. **30-Minute Medicine Hold Reservation System**
   - Real-time stock reservation: immediately deducts shelf units behind the pharmacy counter.
   - Secure 4-digit counter pickup OTP generation to prevent fraudulent claims.
   - Interactive Google Maps turn-by-turn directions link.

4. **Twilio SMS & WhatsApp Business API Integration**
   - Instant confirmation dispatched to patient with reservation code, verification OTP, and directions link.
   - Instant urgent alert dispatched to pharmacist with patient details, requested units, and shelf/rack location.
   - Graceful smart simulator mode for offline/test environments.

5. **JWT Authentication & Role-Based Access Control (RBAC)**
   - Secure role separation: `patient`, `pharmacist`, `admin`.
   - Chemist portal for 1-tap stock adjustments and customer reservation fulfillment.
   - Admin audit panel for registered accounts and roles.

6. **Automated Background Scheduler / Expiration Cron**
   - Continuously inspects active reservations.
   - Holds unclaimed after 30 minutes are transitioned to `expired` and inventory is restored automatically.

---

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Application Server
```bash
python server.py
```
Open [http://localhost:3000](http://localhost:3000) in your web browser.

---

## 🛡️ Production Deployment (Gunicorn + Nginx + HTTPS)

MedNear includes production-ready WSGI configuration:

- **WSGI Entry Point**: `wsgi.py`
- **Gunicorn Cluster**: `gunicorn -c gunicorn.conf.py wsgi:application`
- **Nginx Reverse Proxy**: `nginx -c nginx.conf`
- **One-Click Deploy**:
  ```bash
  chmod +x deploy_production.sh stop_production.sh
  ./deploy_production.sh
  ```

---

## ☁️ Deploying to Vercel (GitHub to Vercel)

This repository includes native Vercel configuration (`vercel.json` and `api/index.py`).

### Step 1: Push Code to Your GitHub
```bash
git remote add origin https://github.com/<your-username>/mednear.git
git branch -M main
git push -u origin main
```

### Step 2: Import into Vercel
1. Go to [https://vercel.com](https://vercel.com) and log in with your GitHub account.
2. Click **"Add New..."** $\rightarrow$ **"Project"**.
3. Select your `mednear` repository.
4. Leave Framework Preset as **Other** (Vercel automatically detects `vercel.json` and `api/index.py`).
5. (Optional) Under **Environment Variables**, add your Twilio credentials if using live SMS/WhatsApp:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
   - `TWILIO_WHATSAPP_NUMBER`
6. Click **Deploy**. Vercel will build and assign you a global `https://<your-project>.vercel.app` domain within seconds!

---

## 📁 Project Structure

```
├── api/
│   └── index.py            # Vercel serverless function entry point
├── app.js                  # Frontend client application logic & Leaflet controller
├── database.py             # SQLite schema, seed data, and user authentication
├── deploy_production.sh    # Production deployment runner (Gunicorn + Nginx)
├── gunicorn.conf.py        # Production WSGI multi-threading worker config
├── index.html              # Main single-page application UI
├── mednear.db              # Pre-seeded SQLite database (medicines, stores, users)
├── nginx.conf              # Nginx reverse proxy configuration (HTTP + HTTPS)
├── notifier.py             # Twilio SMS & WhatsApp Business messaging engine
├── Procfile                # Heroku / Render / Railway process declaration
├── requirements.txt        # Python package dependencies
├── server.py               # Flask REST API, geocoder, JWT auth, and cron scheduler
├── stop_production.sh      # Graceful production server stop script
├── styles.css              # Custom responsive stylesheet & UI theme
├── vercel.json             # Vercel deployment routes and build specifications
└── wsgi.py                 # WSGI application callable
```
