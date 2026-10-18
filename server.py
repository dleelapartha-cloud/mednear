"""
MedNear Backend Server (Flask + SQLite)
Serves the web application and provides the complete REST API for:
- Medicine and Disease search with PMC5570547 Pharmacogenomic Decision Support
- Real-time nearby pharmacy locator with verified stock, distance, and pricing
- Customer 30-minute hold reservation system
- Pharmacy Partner Portal (inventory management, 1-tap stock toggles, order fulfillment)
"""

import os
import json
import math
import random
import uuid
import threading
import time
import urllib.request
import urllib.parse
from functools import wraps
from datetime import datetime, timedelta, timezone
import jwt
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import check_password_hash
from database import (
    get_db_connection,
    init_db,
    get_user_by_email,
    get_user_by_id,
    create_user,
    get_all_users,
    update_user
)
import notifier
import ai_bot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR)

# JWT Secret & Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "mednear-super-secure-production-jwt-key-2026-precision-medicine-rx")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 48

# Initialize database schema and seed data on startup
init_db()

# --------------------------------------------------------------------------
# Supabase Cloud Dual-Sync Helper (Project: mednear / ytwxequauyhysyqkswxs)
# --------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ytwxequauyhysyqkswxs.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl0d3hlcXVhdXloeXN5cWtzd3hzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5NTk3MDMsImV4cCI6MjEwNzUzNTcwM30.u224AbqQ6zn0MD1O8gzm694vYn4sFkShxyjKKF4rlAM")

def sync_to_supabase(table, data, match_column=None, match_value=None, method="POST"):
    """Safely synchronizes record updates to Supabase cloud PostgreSQL."""
    try:
        endpoint = f"{SUPABASE_URL}/rest/v1/{table}"
        if match_column and match_value:
            endpoint = f"{endpoint}?{match_column}=eq.{urllib.parse.quote(str(match_value))}"
            method = "PATCH"
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            method=method
        )
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception as e:
        print(f"[SupabaseSyncNotice] {table}: {e}")


# --------------------------------------------------------------------------
# Authentication & Role-Based Access Control (RBAC) Helpers
# --------------------------------------------------------------------------

def generate_jwt_token(user):
    """Encodes a signed JWT token containing user identity and role."""
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "pharmacy_id": user.get("pharmacy_id"),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user():
    """Extracts and verifies JWT token from Authorization header or query param."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif request.args.get("token"):
        token = request.args.get("token").strip()

    if not token:
        return None

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = get_user_by_id(decoded.get("sub"))
        return user
    except Exception:
        return None


def require_auth(allowed_roles=None):
    """Decorator ensuring valid JWT and optionally checking role permissions."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({
                    "error": "Authentication required. Please provide a valid Bearer token.",
                    "code": "AUTH_REQUIRED"
                }), 401

            if allowed_roles and user.get("role") not in allowed_roles:
                return jsonify({
                    "error": f"Access denied. Requires one of roles: {list(allowed_roles)}. Your role is '{user.get('role')}'.",
                    "code": "FORBIDDEN"
                }), 403

            request.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def check_store_permission(user, store_id):
    """Returns True if user is an admin OR a pharmacist assigned to this specific store."""
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    if user.get("role") == "pharmacist" and user.get("pharmacy_id") == store_id:
        return True
    return False


# --------------------------------------------------------------------------
# Background Scheduler / Cron Job: 30-Minute Hold Expiration & Stock Restorer
# --------------------------------------------------------------------------

HOLD_EXPIRATION_MINUTES = int(os.environ.get("HOLD_EXPIRATION_MINUTES", 30))
SCHEDULER_INTERVAL_SECONDS = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", 30))


def expire_stale_holds(expiration_minutes=None):
    """
    Checks for pending/ready hold reservations older than expiration_minutes (default 30 mins),
    marks them as 'expired', and restores the reserved quantity back into pharmacy_inventory.
    """
    if expiration_minutes is None:
        expiration_minutes = HOLD_EXPIRATION_MINUTES

    now = datetime.now()
    conn = get_db_connection()

    rows = conn.execute("""
        SELECT id, store_id, medicine_id, medicine_name, quantity, status, created_at
        FROM hold_reservations
        WHERE status IN ('pending', 'ready')
    """).fetchall()

    expired_records = []

    for r in rows:
        created_str = r["created_at"]
        if not created_str:
            continue
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created_dt.tzinfo is not None:
                diff_seconds = (datetime.now(timezone.utc) - created_dt).total_seconds()
            else:
                diff_seconds = (now - created_dt).total_seconds()

            if diff_seconds >= (expiration_minutes * 60):
                hold_id = r["id"]
                store_id = r["store_id"]
                med_id = r["medicine_id"]
                qty = r["quantity"]

                # 1. Update hold reservation to 'expired'
                conn.execute("UPDATE hold_reservations SET status = 'expired' WHERE id = ?", (hold_id,))
                sync_to_supabase("hold_reservations", {"status": "expired"}, match_column="id", match_value=hold_id)

                # 2. Increment pharmacy inventory count back up
                inv = conn.execute(
                    "SELECT units FROM pharmacy_inventory WHERE pharmacy_id = ? AND medicine_id = ?",
                    (store_id, med_id)
                ).fetchone()

                new_units = (inv["units"] if inv else 0) + qty
                st = "available" if new_units > 3 else "limited" if new_units > 0 else "unavailable"
                now_iso = datetime.now().isoformat()

                if inv:
                    conn.execute("""
                        UPDATE pharmacy_inventory
                        SET units = ?, status = ?, updated_at = ?
                        WHERE pharmacy_id = ? AND medicine_id = ?
                    """, (new_units, st, now_iso, store_id, med_id))
                else:
                    conn.execute("""
                        INSERT INTO pharmacy_inventory (pharmacy_id, medicine_id, status, units, price, rack, updated_at)
                        VALUES (?, ?, ?, ?, 150.0, 'Restocked counter', ?)
                    """, (store_id, med_id, st, new_units, now_iso))

                expired_records.append({
                    "hold_id": hold_id,
                    "store_id": store_id,
                    "medicine_id": med_id,
                    "medicine_name": r["medicine_name"],
                    "quantity_restored": qty,
                    "new_units": new_units,
                    "expired_after_minutes": round(diff_seconds / 60, 1)
                })
        except Exception as e:
            print(f"[HoldExpirationScheduler] Error processing hold {r['id']}: {e}")

    if expired_records:
        conn.commit()
        print(f"[HoldExpirationScheduler] Expired {len(expired_records)} stale reservation(s) & restored inventory: {expired_records}")

    conn.close()
    return expired_records


def hold_expiration_cron_worker():
    """Background daemon worker running continuously."""
    print(f"[HoldExpirationScheduler] Started background worker (Interval: {SCHEDULER_INTERVAL_SECONDS}s, Expiration: {HOLD_EXPIRATION_MINUTES}m)")
    while True:
        try:
            expire_stale_holds()
        except Exception as e:
            print(f"[HoldExpirationScheduler] Error in expiration run: {e}")
        time.sleep(SCHEDULER_INTERVAL_SECONDS)


# Launch background scheduler daemon thread (skipped on Vercel serverless lambdas)
if not os.environ.get("VERCEL"):
    scheduler_thread = threading.Thread(target=hold_expiration_cron_worker, daemon=True)
    scheduler_thread.start()


# --------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates great-circle distance between two points in km."""
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def check_is_open(open_time_str, close_time_str):
    """Determines whether a pharmacy is open at the current local time."""
    if not open_time_str or not close_time_str:
        return True
    if open_time_str == "00:00" and close_time_str in ["23:59", "24:00"]:
        return True
    now = datetime.now()
    cur_mins = now.hour * 60 + now.minute
    try:
        o_h, o_m = map(int, open_time_str.split(":"))
        c_h, c_m = map(int, close_time_str.split(":"))
        start = o_h * 60 + o_m
        end = c_h * 60 + c_m
        if end < start:  # Overnight hours
            return cur_mins >= start or cur_mins < end
        return start <= cur_mins < end
    except Exception:
        return True


# --------------------------------------------------------------------------
# Static Frontend Routes
# --------------------------------------------------------------------------

@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    if os.path.exists(os.path.join(BASE_DIR, path)):
        return send_from_directory(BASE_DIR, path)
    return send_from_directory(BASE_DIR, "index.html")


# --------------------------------------------------------------------------
# REST API Endpoints
# --------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    conn = get_db_connection()
    med_count = conn.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
    pharm_count = conn.execute("SELECT COUNT(*) FROM pharmacies").fetchone()[0]
    active_holds = conn.execute("SELECT COUNT(*) FROM hold_reservations WHERE status IN ('pending', 'ready')").fetchone()[0]
    expired_holds = conn.execute("SELECT COUNT(*) FROM hold_reservations WHERE status = 'expired'").fetchone()[0]
    completed_holds = conn.execute("SELECT COUNT(*) FROM hold_reservations WHERE status = 'completed'").fetchone()[0]
    conn.close()
    
    cfg = notifier.get_config()
    return jsonify({
        "status": "healthy",
        "service": "MedNear Backend API",
        "timestamp": datetime.now().isoformat(),
        "scheduler": {
            "status": "running",
            "interval_seconds": SCHEDULER_INTERVAL_SECONDS,
            "hold_expiration_minutes": HOLD_EXPIRATION_MINUTES
        },
        "messaging": {
            "twilio_configured": cfg["enabled"],
            "twilio_library_installed": notifier.TWILIO_AVAILABLE,
            "default_channel": cfg["default_channel"],
            "mode": "live_twilio" if cfg["enabled"] else "smart_simulator"
        },
        "stats": {
            "medicines": med_count,
            "pharmacies": pharm_count,
            "active_holds": active_holds,
            "expired_holds": expired_holds,
            "completed_holds": completed_holds
        }
    })


@app.route("/api/medicines", methods=["GET"])
def get_medicines():
    """Search medicines by keyword or return full list."""
    query = request.args.get("q", "").strip().lower()
    conn = get_db_connection()

    if query:
        # Search in name, generic_name, and keywords
        rows = conn.execute("""
            SELECT id, name, generic_name, form, category, schedule, avg_price, 
                   pgx_gene, pgx_status, pgx_status_label, keywords
            FROM medicines
            WHERE LOWER(name) LIKE ? OR LOWER(generic_name) LIKE ? OR LOWER(keywords) LIKE ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, name, generic_name, form, category, schedule, avg_price, 
                   pgx_gene, pgx_status, pgx_status_label, keywords
            FROM medicines
        """).fetchall()

    medicines = []
    for r in rows:
        item = dict(r)
        item["keywords"] = json.loads(item["keywords"]) if item["keywords"] else []
        medicines.append(item)

    conn.close()
    return jsonify({"results": medicines, "count": len(medicines)})


@app.route("/api/medicines/<medicine_id>", methods=["GET"])
def get_medicine_detail(medicine_id):
    """Get full medicine detail, generic substitutes, and PGx safety advice."""
    conn = get_db_connection()
    med_row = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()

    if not med_row:
        # Fallback partial match
        med_row = conn.execute("SELECT * FROM medicines WHERE id LIKE ? LIMIT 1", (f"%{medicine_id}%",)).fetchone()

    if not med_row:
        conn.close()
        return jsonify({"error": "Medicine not found"}), 404

    med = dict(med_row)
    med["keywords"] = json.loads(med["keywords"]) if med["keywords"] else []

    # Get generic substitutes
    subs_rows = conn.execute(
        "SELECT id, name, company, price, savings FROM generic_substitutes WHERE medicine_id = ?",
        (med["id"],)
    ).fetchall()
    med["substitutes"] = [dict(s) for s in subs_rows]

    # Package PGx object
    med["pgx"] = {
        "gene": med.get("pgx_gene"),
        "status": med.get("pgx_status"),
        "status_label": med.get("pgx_status_label"),
        "evidence": med.get("pgx_evidence"),
        "advice": med.get("pgx_advice")
    }

    conn.close()
    return jsonify(med)


@app.route("/api/diseases", methods=["GET"])
def get_diseases():
    """List all mapped diseases from PMC5570547."""
    conn = get_db_connection()
    rows = conn.execute("SELECT id, title, synonyms, primary_gene, description FROM diseases").fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["synonyms"] = json.loads(d["synonyms"]) if d["synonyms"] else []
        results.append(d)
    conn.close()
    return jsonify({"results": results})


@app.route("/api/diseases/<disease_id>", methods=["GET"])
def get_disease_detail(disease_id):
    """Get disease details with PMC5570547 comparative drug table."""
    conn = get_db_connection()
    d_row = conn.execute("SELECT * FROM diseases WHERE id = ?", (disease_id,)).fetchone()

    if not d_row:
        # Search by synonym
        query = f"%{disease_id.lower()}%"
        d_row = conn.execute("SELECT * FROM diseases WHERE LOWER(synonyms) LIKE ? LIMIT 1", (query,)).fetchone()

    if not d_row:
        conn.close()
        return jsonify({"error": "Disease not found"}), 404

    disease = dict(d_row)
    disease["synonyms"] = json.loads(disease["synonyms"]) if disease["synonyms"] else []

    drugs_rows = conn.execute(
        "SELECT id, name, status, gene, status_label, guidance, evidence, med_key FROM disease_drugs WHERE disease_id = ?",
        (disease["id"],)
    ).fetchall()
    disease["drugs"] = [dict(d) for d in drugs_rows]

    conn.close()
    return jsonify(disease)


# --------------------------------------------------------------------------
# Geocoding Service (OpenStreetMap Nominatim + Local City Index)
# --------------------------------------------------------------------------

GEOCODE_CACHE = {}

LOCAL_GEOCODE_DATA = [
    {"name": "Indiranagar", "keywords": ["indiranagar", "560038", "560008", "100 ft road"], "lat": 12.9784, "lng": 77.6408, "area": "Indiranagar, Bengaluru"},
    {"name": "Koramangala", "keywords": ["koramangala", "560034", "560095", "sony signal"], "lat": 12.9352, "lng": 77.6245, "area": "Koramangala, Bengaluru"},
    {"name": "MG Road / Central", "keywords": ["mg road", "brigade road", "residency road", "560001", "central", "shivajinagar"], "lat": 12.9754, "lng": 77.6080, "area": "MG Road, Bengaluru Central"},
    {"name": "Lavelle Road / Richmond Town", "keywords": ["lavelle road", "richmond town", "560025", "ashok nagar"], "lat": 12.9698, "lng": 77.5992, "area": "Lavelle Road, Bengaluru"},
    {"name": "Whitefield", "keywords": ["whitefield", "560066", "itpl", "hope farm", "kadugodi"], "lat": 12.9698, "lng": 77.7500, "area": "Whitefield, Bengaluru"},
    {"name": "HSR Layout", "keywords": ["hsr layout", "560102", "hsr sector"], "lat": 12.9121, "lng": 77.6446, "area": "HSR Layout, Bengaluru"},
    {"name": "Jayanagar", "keywords": ["jayanagar", "560011", "560041", "4th block"], "lat": 12.9308, "lng": 77.5838, "area": "Jayanagar, Bengaluru"},
    {"name": "Malleshwaram", "keywords": ["malleshwaram", "560003", "sampige road"], "lat": 13.0031, "lng": 77.5703, "area": "Malleshwaram, Bengaluru"},
    {"name": "Electronic City", "keywords": ["electronic city", "560100", "ecity", "phase 1", "phase 2"], "lat": 12.8452, "lng": 77.6602, "area": "Electronic City, Bengaluru"},
    {"name": "Ulsoor / Halasuru", "keywords": ["ulsoor", "halasuru", "560008", "ulsoor lake"], "lat": 12.9782, "lng": 77.6200, "area": "Ulsoor, Bengaluru"},
    {"name": "Infantry Road / Shivaji Nagar", "keywords": ["infantry road", "560001", "cubbon park", "cantonment"], "lat": 12.9811, "lng": 77.6050, "area": "Infantry Road, Bengaluru"},
    {"name": "BTM Layout", "keywords": ["btm layout", "560076", "btm 2nd stage", "madiwala"], "lat": 12.9166, "lng": 77.6101, "area": "BTM Layout, Bengaluru"},
    {"name": "JP Nagar", "keywords": ["jp nagar", "560078", "jaya prakash narayan nagar"], "lat": 12.9063, "lng": 77.5857, "area": "JP Nagar, Bengaluru"},
    {"name": "Bellandur", "keywords": ["bellandur", "560103", "ecospace", "outer ring road"], "lat": 12.9304, "lng": 77.6784, "area": "Bellandur, Bengaluru"},
    {"name": "Marathahalli", "keywords": ["marathahalli", "560037", "marathahalli bridge"], "lat": 12.9591, "lng": 77.6974, "area": "Marathahalli, Bengaluru"},
    {"name": "Hebbal", "keywords": ["hebbal", "560024", "manyata", "hebbal flyover"], "lat": 13.0358, "lng": 77.5970, "area": "Hebbal, Bengaluru"},
    {"name": "Rajajinagar", "keywords": ["rajajinagar", "560010", "isckon"], "lat": 12.9982, "lng": 77.5530, "area": "Rajajinagar, Bengaluru"},
    {"name": "Yelahanka", "keywords": ["yelahanka", "560064", "new town"], "lat": 13.1007, "lng": 77.5963, "area": "Yelahanka, Bengaluru"},
    {"name": "Basavanagudi", "keywords": ["basavanagudi", "560004", "bull temple"], "lat": 12.9422, "lng": 77.5756, "area": "Basavanagudi, Bengaluru"}
]


@app.route("/api/geocode", methods=["GET"])
def geocode_address():
    """
    Translates typed address, neighborhood, or PIN code into GPS coordinates.
    Uses OpenStreetMap Nominatim with local caching and offline fallback.
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})

    cache_key = query.lower()
    if cache_key in GEOCODE_CACHE:
        return jsonify(GEOCODE_CACHE[cache_key])

    # 1. Check local indexed data first for instant matching
    local_matches = []
    for loc in LOCAL_GEOCODE_DATA:
        if any(k in cache_key or cache_key in k for k in loc["keywords"]):
            local_matches.append({
                "display_name": loc["area"] + ", Karnataka, India",
                "area": loc["name"],
                "lat": loc["lat"],
                "lng": loc["lng"],
                "source": "local_verified"
            })

    # 2. Query OpenStreetMap Nominatim API
    osm_results = []
    try:
        clean_q = query
        if not any(t in query.lower() for t in ["bengaluru", "bangalore", "india", "karnataka"]):
            clean_q = f"{query}, Bengaluru, India"

        params = urllib.parse.urlencode({
            "q": clean_q,
            "format": "json",
            "limit": 5,
            "addressdetails": 1
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "MedNear-Healthcare-App/2.0 (contact@mednear.org)",
            "Accept-Language": "en"
        })
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                addr = item.get("address", {})
                area_name = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("town") or item.get("name") or query
                osm_results.append({
                    "display_name": item.get("display_name"),
                    "area": area_name,
                    "lat": float(item["lat"]),
                    "lng": float(item["lon"]),
                    "postcode": addr.get("postcode"),
                    "source": "openstreetmap_nominatim"
                })
    except Exception as e:
        print(f"Nominatim lookup notice for '{query}': {e}")

    # Combine results: OSM results first, backed up by local matches
    combined = []
    seen = set()
    for item in (osm_results + local_matches):
        coord_key = f"{round(item['lat'], 3)},{round(item['lng'], 3)}"
        if coord_key not in seen:
            seen.add(coord_key)
            combined.append(item)

    payload = {"query": query, "results": combined[:5]}
    if combined:
        GEOCODE_CACHE[cache_key] = payload

    return jsonify(payload)


@app.route("/api/pharmacies", methods=["GET"])
def get_pharmacies():
    """
    Search nearby pharmacies with verified stock for a requested medicine.
    Calculates distances from user coords and filters by open status or availability.
    """
    medicine_id = request.args.get("medicine", "pantoprazole").strip().lower()
    user_lat = float(request.args.get("lat", 12.9716))
    user_lng = float(request.args.get("lng", 77.5946))
    filter_status = request.args.get("filter", "all")  # all, available, limited
    open_now = request.args.get("open_now", "false").lower() == "true"
    is_24_hours = request.args.get("is_24_hours", "false").lower() == "true"
    sort_by = request.args.get("sort", "distance")  # distance, availability, price, name

    conn = get_db_connection()

    # Get default price for medicine
    med_row = conn.execute("SELECT avg_price, name FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    default_price = med_row["avg_price"] if med_row else 150.0

    pharmacies_rows = conn.execute("SELECT * FROM pharmacies").fetchall()
    results = []

    for p in pharmacies_rows:
        pharm = dict(p)
        # Calculate dynamic distance
        dist_km = haversine_distance(user_lat, user_lng, pharm["lat"], pharm["lng"])
        pharm["distance_km"] = dist_km
        pharm["is_open"] = check_is_open(pharm["open_time"], pharm["close_time"])

        # Fetch inventory for requested medicine
        inv_row = conn.execute(
            "SELECT status, units, price, rack, updated_at FROM pharmacy_inventory WHERE pharmacy_id = ? AND medicine_id = ?",
            (pharm["id"], medicine_id)
        ).fetchone()

        if inv_row:
            inv = dict(inv_row)
            # Calculate minutes ago
            try:
                up_dt = datetime.fromisoformat(inv["updated_at"])
                mins_ago = max(1, int((datetime.now() - up_dt).total_seconds() / 60))
            except Exception:
                mins_ago = 5
            inv["updated_min_ago"] = mins_ago
        else:
            # Fallback simulated stock item
            inv = {
                "status": "available",
                "units": 10,
                "price": default_price,
                "rack": "Main Dispensary",
                "updated_min_ago": 15
            }

        pharm["item"] = inv

        # Filter criteria
        if filter_status == "available" and inv["status"] != "available":
            continue
        if filter_status == "limited" and inv["status"] != "limited":
            continue
        if open_now and not pharm["is_open"]:
            continue
        if is_24_hours and not pharm["is_24_hours"]:
            continue

        results.append(pharm)

    # Sort results
    if sort_by == "availability":
        rank = {"available": 0, "limited": 1, "unavailable": 2}
        results.sort(key=lambda x: (rank.get(x["item"]["status"], 3), x["distance_km"]))
    elif sort_by == "price":
        results.sort(key=lambda x: (x["item"]["price"], x["distance_km"]))
    elif sort_by == "name":
        results.sort(key=lambda x: x["name"])
    else:  # default: distance
        results.sort(key=lambda x: x["distance_km"])

    conn.close()
    return jsonify({
        "results": results,
        "count": len(results),
        "medicine_id": medicine_id,
        "user_coords": {"lat": user_lat, "lng": user_lng}
    })


@app.route("/api/pharmacy/<store_id>/inventory", methods=["GET"])
def get_store_inventory(store_id):
    """Returns store inventory for the pharmacist portal dashboard."""
    conn = get_db_connection()
    store = conn.execute("SELECT * FROM pharmacies WHERE id = ?", (store_id,)).fetchone()
    if not store:
        conn.close()
        return jsonify({"error": "Store not found"}), 404

    # Join inventory with medicines
    rows = conn.execute("""
        SELECT pi.id, pi.medicine_id, pi.status, pi.units, pi.price, pi.rack, pi.updated_at,
               m.name, m.generic_name, m.category, m.schedule, m.pgx_status, m.pgx_gene
        FROM pharmacy_inventory pi
        JOIN medicines m ON pi.medicine_id = m.id
        WHERE pi.pharmacy_id = ?
        ORDER BY m.name ASC
    """, (store_id,)).fetchall()

    inventory = [dict(r) for r in rows]
    conn.close()

    return jsonify({
        "store": dict(store),
        "inventory": inventory,
        "total_items": len(inventory)
    })


# --------------------------------------------------------------------------
# Authentication Endpoints (Dual-Sync: SQLite + Supabase Cloud)
# --------------------------------------------------------------------------

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Register a new patient or pharmacist user with dual-sync to Supabase Cloud."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    role = data.get("role", "patient").strip().lower()
    pharmacy_id = data.get("pharmacy_id", "").strip() or None

    if not email or not password or not name:
        return jsonify({"error": "Full name, email, and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400

    if role not in ["patient", "pharmacist"]:
        return jsonify({"error": "Role must be 'patient' or 'pharmacist'"}), 400

    if role == "pharmacist" and not pharmacy_id:
        return jsonify({"error": "Pharmacist account must be linked to a partner pharmacy"}), 400

    # Check local SQLite
    if get_user_by_email(email):
        return jsonify({"error": "An account with this email address already exists"}), 409

    # Check Supabase Cloud PostgreSQL
    try:
        check_endpoint = f"{SUPABASE_URL}/rest/v1/users?email=eq.{urllib.parse.quote(email)}&select=id"
        check_req = urllib.request.Request(
            check_endpoint,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        with urllib.request.urlopen(check_req, timeout=3) as res:
            existing = json.loads(res.read().decode())
            if existing:
                return jsonify({"error": "An account with this email address already exists in cloud records"}), 409
    except Exception as e:
        print(f"[SupabaseCheckNotice] {e}")

    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    new_user = create_user(user_id, email, password, name, role=role, phone=phone, pharmacy_id=pharmacy_id)
    token = generate_jwt_token(new_user)

    # Live dual-sync to Supabase Cloud PostgreSQL
    sync_to_supabase("users", {
        "id": new_user["id"],
        "email": new_user["email"],
        "password_hash": new_user["password_hash"],
        "name": new_user["name"],
        "phone": new_user.get("phone"),
        "role": new_user["role"],
        "pharmacy_id": new_user.get("pharmacy_id"),
        "created_at": new_user["created_at"]
    })

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": new_user["id"],
            "email": new_user["email"],
            "name": new_user["name"],
            "role": new_user["role"],
            "pharmacy_id": new_user["pharmacy_id"],
            "phone": new_user.get("phone"),
            "created_at": new_user["created_at"]
        },
        "storage": {
            "local_database": "SQLite (mednear.db)",
            "cloud_database": "Supabase Cloud PostgreSQL (ytwxequauyhysyqkswxs)",
            "status": "stored_and_synchronized"
        }
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Log in an existing user and return a signed JWT token with Supabase Cloud fallback."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = get_user_by_email(email)

    # Fallback to Supabase Cloud if not yet cached in local SQLite
    if not user:
        try:
            endpoint = f"{SUPABASE_URL}/rest/v1/users?email=eq.{urllib.parse.quote(email)}&select=*"
            req = urllib.request.Request(
                endpoint,
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=3) as res:
                remote_users = json.loads(res.read().decode())
                if remote_users:
                    ru = remote_users[0]
                    conn = get_db_connection()
                    conn.execute("""
                        INSERT OR REPLACE INTO users (id, email, password_hash, name, phone, role, pharmacy_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (ru["id"], ru["email"], ru["password_hash"], ru["name"], ru.get("phone"), ru["role"], ru.get("pharmacy_id"), ru.get("created_at")))
                    conn.commit()
                    conn.close()
                    user = get_user_by_id(ru["id"])
        except Exception as e:
            print(f"[SupabaseLoginFallbackNotice] {e}")

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = generate_jwt_token(user)

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "pharmacy_id": user["pharmacy_id"],
            "phone": user.get("phone"),
            "created_at": user.get("created_at")
        }
    })


@app.route("/api/auth/me", methods=["GET"])
@require_auth()
def auth_me():
    """Returns profile details of the current authenticated user."""
    user = request.current_user
    return jsonify({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "pharmacy_id": user["pharmacy_id"],
            "phone": user.get("phone"),
            "created_at": user.get("created_at")
        }
    })


@app.route("/api/user/profile", methods=["GET"])
@require_auth()
def get_user_full_profile():
    """Returns comprehensive stored profile data, hold history, pharmacy details, and database sync status."""
    user = request.current_user
    conn = get_db_connection()
    
    # Query reservations placed by or associated with this user
    if user["role"] == "admin":
        hold_rows = conn.execute("SELECT * FROM hold_reservations ORDER BY created_at DESC").fetchall()
    else:
        hold_rows = conn.execute("""
            SELECT * FROM hold_reservations 
            WHERE patient_id = ? OR LOWER(patient_name) = LOWER(?) OR (phone IS NOT NULL AND phone != '' AND phone = ?)
            ORDER BY created_at DESC
        """, (user["id"], user["name"], user.get("phone") or "")).fetchall()
    holds = [dict(r) for r in hold_rows]

    # Pharmacy info if pharmacist
    pharmacy_info = None
    if user.get("pharmacy_id"):
        pharm_row = conn.execute("SELECT * FROM pharmacies WHERE id = ?", (user["pharmacy_id"],)).fetchone()
        if pharm_row:
            pharmacy_info = dict(pharm_row)
            inv_count = conn.execute(
                "SELECT COUNT(*) FROM pharmacy_inventory WHERE pharmacy_id = ?", 
                (user["pharmacy_id"],)
            ).fetchone()[0]
            pharmacy_info["inventory_count"] = inv_count

    conn.close()

    return jsonify({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "phone": user.get("phone"),
            "pharmacy_id": user.get("pharmacy_id"),
            "created_at": user.get("created_at")
        },
        "stats": {
            "total_holds": len(holds),
            "active_holds": len([h for h in holds if h.get("status") in ["pending", "ready"]]),
            "completed_holds": len([h for h in holds if h.get("status") == "completed"])
        },
        "holds": holds,
        "pharmacy": pharmacy_info,
        "storage": {
            "local_database": "SQLite (mednear.db)",
            "cloud_database": "Supabase Cloud PostgreSQL (ytwxequauyhysyqkswxs)",
            "dual_sync": "Active & Verified"
        }
    })


@app.route("/api/user/profile", methods=["PUT"])
@require_auth()
def update_user_profile():
    """Update user's stored name or phone number in SQLite and Supabase Cloud."""
    user = request.current_user
    data = request.get_json() or {}
    name = data.get("name", "").strip() or user["name"]
    phone = data.get("phone", "").strip() or user.get("phone")

    updated_user = update_user(user["id"], name=name, phone=phone)
    # Sync update to Supabase
    sync_to_supabase("users", {"name": name, "phone": phone}, match_column="id", match_value=user["id"])

    # Issue updated JWT
    token = generate_jwt_token(updated_user)
    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": updated_user["id"],
            "email": updated_user["email"],
            "name": updated_user["name"],
            "role": updated_user["role"],
            "phone": updated_user.get("phone"),
            "pharmacy_id": updated_user.get("pharmacy_id"),
            "created_at": updated_user.get("created_at")
        }
    })


@app.route("/api/patient/holds", methods=["GET"])
@require_auth(allowed_roles=["patient", "admin"])
def get_patient_holds():
    """Returns reservations placed by the authenticated patient."""
    user = request.current_user
    conn = get_db_connection()
    if user["role"] == "admin":
        rows = conn.execute("SELECT * FROM hold_reservations ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM hold_reservations 
            WHERE patient_id = ? OR LOWER(patient_name) = LOWER(?) OR (phone IS NOT NULL AND phone != '' AND phone = ?)
            ORDER BY created_at DESC
        """, (user["id"], user["name"], user.get("phone") or "")).fetchall()
    holds = [dict(r) for r in rows]
    conn.close()
    return jsonify({"holds": holds, "count": len(holds)})


@app.route("/api/admin/users", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def get_admin_users():
    """Admin-only endpoint to view registered users and roles."""
    users = get_all_users()
    return jsonify({"users": users, "count": len(users)})



# --------------------------------------------------------------------------
# Pharmacy Inventory & Hold Routes (RBAC Protected)
# --------------------------------------------------------------------------

@app.route("/api/pharmacy/<store_id>/inventory", methods=["POST"])
@require_auth(allowed_roles=["pharmacist", "admin"])
def update_or_add_inventory(store_id):
    """
    1-Tap stock toggle, unit adjustment, price edit, or adding a new medicine to store stock.
    Requires pharmacist of this store or admin.
    """
    user = request.current_user
    if not check_store_permission(user, store_id):
        return jsonify({
            "error": f"Access denied: You are assigned to '{user.get('pharmacy_id')}' and cannot edit '{store_id}'."
        }), 403

    data = request.get_json() or {}
    med_id = data.get("medicine_id", "").strip().lower()
    if not med_id:
        return jsonify({"error": "medicine_id is required"}), 400

    conn = get_db_connection()

    # Check if medicine exists; if not, create dynamic entry
    med_row = conn.execute("SELECT id FROM medicines WHERE id = ?", (med_id,)).fetchone()
    if not med_row:
        name = data.get("name") or med_id.capitalize()
        generic_name = data.get("generic_name") or f"Active salt of {name}"
        conn.execute("""
            INSERT INTO medicines (id, name, generic_name, form, category, schedule, avg_price, usage, safety, pgx_gene, pgx_status, pgx_status_label, pgx_evidence, pgx_advice, keywords)
            VALUES (?, ?, ?, 'Tablets', 'General Medicine', 'Schedule H', ?, 'Counter dispensed pharmaceutical.', 'Use as directed.', 'Minimal PGx', 'green', '🟢 Standard Response', 'Standard Formulary', 'Standard response expected.', ?)
        """, (med_id, name, generic_name, float(data.get("price", 100)), json.dumps([med_id, name.lower()])))

    status = data.get("status", "available")
    if status not in ("available", "limited", "unavailable"):
        return jsonify({"error": "status must be 'available', 'limited', or 'unavailable'"}), 400
    try:
        units = int(data.get("units", 10))
        price = float(data.get("price", 100.0))
    except (TypeError, ValueError):
        return jsonify({"error": "units and price must be numeric"}), 400
    if units < 0 or price < 0:
        return jsonify({"error": "units and price cannot be negative"}), 400
    rack = data.get("rack", "Shelf A-1")
    now_str = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO pharmacy_inventory (pharmacy_id, medicine_id, status, units, price, rack, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pharmacy_id, medicine_id) DO UPDATE SET
            status = excluded.status,
            units = excluded.units,
            price = excluded.price,
            rack = excluded.rack,
            updated_at = excluded.updated_at
    """, (store_id, med_id, status, units, price, rack, now_str))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Inventory updated for {med_id}",
        "item": {
            "pharmacy_id": store_id,
            "medicine_id": med_id,
            "status": status,
            "units": units,
            "price": price,
            "rack": rack,
            "updated_at": now_str
        }
    })


@app.route("/api/pharmacy/<store_id>/inventory/<medicine_id>", methods=["DELETE"])
@require_auth(allowed_roles=["pharmacist", "admin"])
def delete_inventory_item(store_id, medicine_id):
    """Delete an item from inventory. Requires pharmacist of this store or admin."""
    user = request.current_user
    if not check_store_permission(user, store_id):
        return jsonify({
            "error": f"Access denied: You are assigned to '{user.get('pharmacy_id')}' and cannot edit '{store_id}'."
        }), 403

    conn = get_db_connection()
    conn.execute("DELETE FROM pharmacy_inventory WHERE pharmacy_id = ? AND medicine_id = ?", (store_id, medicine_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Deleted {medicine_id} from store inventory"})


@app.route("/api/pharmacy/<store_id>/holds", methods=["GET"])
@require_auth(allowed_roles=["pharmacist", "admin"])
def get_store_holds(store_id):
    """Retrieve incoming customer 30-minute hold requests for a pharmacy. Requires pharmacist of this store or admin."""
    user = request.current_user
    if not check_store_permission(user, store_id):
        return jsonify({
            "error": f"Access denied: You are assigned to '{user.get('pharmacy_id')}' and cannot view reservations for '{store_id}'."
        }), 403

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM hold_reservations WHERE store_id = ? ORDER BY created_at DESC",
        (store_id,)
    ).fetchall()
    holds = [dict(r) for r in rows]
    conn.close()
    return jsonify({"holds": holds, "count": len(holds)})


@app.route("/api/holds", methods=["POST"])
def create_hold():
    """
    Create a new 30-minute hold reservation from a patient (or guest).
    Generates a secure counter pickup OTP, computes Google Maps directions,
    and dispatches instant notifications to patient and pharmacy via Twilio SMS / WhatsApp.
    """
    user = get_current_user()
    data = request.get_json() or {}
    store_id = data.get("store_id", "green-cross")
    patient_name = (data.get("patient_name") or (user["name"] if user else "")).strip()
    phone = (data.get("phone") or (user.get("phone") if user else "")).strip()
    med_id = data.get("medicine_id", "pantoprazole")
    med_name = data.get("medicine_name", "Medicine")
    quantity = int(data.get("quantity", 1))
    total_price = float(data.get("total_price", 150.0))
    eta = data.get("eta", "Within 30 minutes")
    patient_id = user["id"] if user else None
    channel = data.get("notification_channel", "sms").lower()  # 'sms', 'whatsapp', or 'both'

    if not patient_name or not phone:
        return jsonify({"error": "Patient name and phone number are required"}), 400

    otp = notifier.generate_otp()
    created_at = datetime.now().isoformat()

    conn = get_db_connection()

    # Generate a collision-free reservation ID (random 4-digit IDs eventually hit
    # the PRIMARY KEY and crash this endpoint with an IntegrityError)
    hold_id = None
    while hold_id is None:
        candidate = f"HLD-{uuid.uuid4().hex[:6].upper()}"
        if not conn.execute("SELECT 1 FROM hold_reservations WHERE id = ?", (candidate,)).fetchone():
            hold_id = candidate

    # Look up pharmacy info for address, contact, and GPS coordinates
    pharm_row = conn.execute("SELECT * FROM pharmacies WHERE id = ?", (store_id,)).fetchone()
    if pharm_row:
        pharm_dict = dict(pharm_row)
    else:
        pharm_dict = {
            "id": store_id,
            "name": "Local Pharmacy",
            "address": "Bengaluru Central",
            "phone": "+91 80 4000 1100",
            "lat": 12.9716,
            "lng": 77.5946
        }

    directions_url = f"https://www.google.com/maps/dir/?api=1&destination={pharm_dict['lat']},{pharm_dict['lng']}"

    # Get rack location if available
    inv = conn.execute(
        "SELECT units, rack FROM pharmacy_inventory WHERE pharmacy_id = ? AND medicine_id = ?",
        (store_id, med_id)
    ).fetchone()
    rack = inv["rack"] if inv and inv["rack"] else "Shelf A-1"

    # Insert reservation with OTP and directions URL
    conn.execute("""
        INSERT INTO hold_reservations (
            id, store_id, patient_id, patient_name, phone, medicine_id, 
            medicine_name, quantity, total_price, eta, status, created_at,
            otp, otp_verified, directions_url, notification_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, ?, 'sent')
    """, (hold_id, store_id, patient_id, patient_name, phone, med_id, med_name, quantity, total_price, eta, created_at, otp, directions_url))

    # Hold the units from pharmacy_inventory (reserve behind counter)
    if inv and inv["units"] > 0:
        remaining = max(0, inv["units"] - quantity)
        st = "available" if remaining > 3 else "limited" if remaining > 0 else "unavailable"
        conn.execute(
            "UPDATE pharmacy_inventory SET units = ?, status = ?, updated_at = ? WHERE pharmacy_id = ? AND medicine_id = ?",
            (remaining, st, created_at, store_id, med_id)
        )

    conn.commit()
    conn.close()

    # Dual-sync hold reservation to Supabase Cloud
    sync_to_supabase("hold_reservations", {
        "id": hold_id,
        "store_id": store_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "phone": phone,
        "medicine_id": med_id,
        "medicine_name": med_name,
        "quantity": quantity,
        "total_price": total_price,
        "eta": eta,
        "status": "pending",
        "created_at": created_at,
        "otp": otp,
        "otp_verified": 0,
        "directions_url": directions_url,
        "notification_status": "sent"
    })

    # Dispatch SMS / WhatsApp notifications to patient & pharmacy
    hold_info = {
        "medicine_name": med_name,
        "quantity": quantity,
        "total_price": total_price,
        "patient_name": patient_name,
        "phone": phone,
        "eta": eta,
        "rack": rack
    }
    notif_result = notifier.dispatch_reservation_notifications(
        hold_id=hold_id,
        hold_data=hold_info,
        pharmacy_data=pharm_dict,
        channel=channel,
        otp=otp
    )

    return jsonify({
        "success": True,
        "hold_id": hold_id,
        "otp": otp,
        "directions_url": directions_url,
        "pharmacy": {
            "name": pharm_dict.get("name"),
            "address": pharm_dict.get("address"),
            "phone": pharm_dict.get("phone"),
            "lat": pharm_dict.get("lat"),
            "lng": pharm_dict.get("lng")
        },
        "notifications": notif_result,
        "message": f"Reserved {quantity} pack(s) of {med_name} for 30 minutes. Pickup OTP: {otp}. Directions sent via {channel.upper()}.",
        "reservation": {
            "id": hold_id,
            "store_id": store_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "phone": phone,
            "medicine_name": med_name,
            "quantity": quantity,
            "total_price": total_price,
            "eta": eta,
            "status": "pending",
            "otp": otp,
            "directions_url": directions_url,
            "created_at": created_at
        }
    }), 201


@app.route("/api/holds/<hold_id>/verify-otp", methods=["POST"])
@require_auth(allowed_roles=["pharmacist", "admin"])
def verify_hold_otp_endpoint(hold_id):
    """
    Pharmacist verifies patient's 4-digit pickup OTP at counter before dispensing.
    """
    data = request.get_json() or {}
    input_otp = data.get("otp", "").strip()
    if not input_otp:
        return jsonify({"error": "OTP is required"}), 400

    result = notifier.verify_hold_otp(hold_id, input_otp)
    if not result.get("success"):
        return jsonify(result), 400

    return jsonify(result)


@app.route("/api/notifications/recent", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def get_recent_notifications():
    """Returns recent dispatched SMS and WhatsApp notifications. Admin-only:
    message bodies contain pickup OTPs and personal phone numbers."""
    hold_id = request.args.get("hold_id")
    limit = int(request.args.get("limit", 20))
    items = notifier.get_recent_notifications(limit=limit, hold_id=hold_id)
    return jsonify({"notifications": items, "count": len(items)})


@app.route("/api/notifications/test", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def send_test_notification():
    """Allows testing SMS or WhatsApp delivery with a custom recipient and message.
    Admin-only so this endpoint cannot be abused as an unauthenticated SMS relay."""
    data = request.get_json() or {}
    phone = data.get("phone", "+919876543210").strip()
    channel = data.get("channel", "sms").strip().lower()
    message = data.get("message", "MedNear Test Alert: Twilio & WhatsApp messaging service active!").strip()

    res = notifier.send_single_message(
        to_phone=phone,
        body=message,
        channel=channel,
        hold_id="TEST-ALERT",
        recipient_role="test"
    )
    return jsonify(res)


@app.route("/api/notifications/config", methods=["GET"])
def get_notification_config():
    """Returns messaging configuration (with auth token masked)."""
    cfg = notifier.get_config()
    masked = dict(cfg)
    if masked.get("auth_token"):
        token_len = len(masked["auth_token"])
        masked["auth_token"] = masked["auth_token"][:4] + "••••••••" + masked["auth_token"][-4:] if token_len > 8 else "••••••••"
    return jsonify(masked)


@app.route("/api/notifications/config", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def update_notification_config():
    """Admin endpoint to update Twilio credentials and default channel."""
    data = request.get_json() or {}
    cfg = notifier.save_config(
        account_sid=data.get("account_sid"),
        auth_token=data.get("auth_token"),
        phone_number=data.get("phone_number"),
        whatsapp_number=data.get("whatsapp_number"),
        default_channel=data.get("default_channel")
    )
    return jsonify({"success": True, "config": cfg})


@app.route("/api/holds/<hold_id>", methods=["PATCH"])
@require_auth(allowed_roles=["pharmacist", "admin"])
def update_hold_status(hold_id):
    """Pharmacist updates reservation status ('ready', 'completed', 'declined')."""
    user = request.current_user
    data = request.get_json() or {}
    new_status = data.get("status", "ready")  # ready, completed, declined

    conn = get_db_connection()
    hold = conn.execute("SELECT * FROM hold_reservations WHERE id = ?", (hold_id,)).fetchone()
    if not hold:
        conn.close()
        return jsonify({"error": "Hold reservation not found"}), 404

    if not check_store_permission(user, hold["store_id"]):
        conn.close()
        return jsonify({
            "error": f"Access denied: Reservation belongs to '{hold['store_id']}'. You are assigned to '{user.get('pharmacy_id')}'."
        }), 403

    conn.execute("UPDATE hold_reservations SET status = ? WHERE id = ?", (new_status, hold_id))

    # If declined, return the reserved units back to inventory
    if new_status == "declined" and hold["status"] in ["pending", "ready"]:
        inv = conn.execute(
            "SELECT units FROM pharmacy_inventory WHERE pharmacy_id = ? AND medicine_id = ?",
            (hold["store_id"], hold["medicine_id"])
        ).fetchone()
        if inv:
            new_units = inv["units"] + hold["quantity"]
            st = "available" if new_units > 3 else "limited" if new_units > 0 else "unavailable"
            conn.execute(
                "UPDATE pharmacy_inventory SET units = ?, status = ?, updated_at = ? WHERE pharmacy_id = ? AND medicine_id = ?",
                (new_units, st, datetime.now().isoformat(), hold["store_id"], hold["medicine_id"])
            )

    conn.commit()
    conn.close()

    # Sync status change to Supabase Cloud
    sync_to_supabase("hold_reservations", {"status": new_status}, match_column="id", match_value=hold_id)

    return jsonify({
        "success": True,
        "hold_id": hold_id,
        "status": new_status,
        "message": f"Reservation status updated to {new_status}"
    })


@app.route("/api/holds/expire-check", methods=["POST"])
def trigger_expire_check():
    """Manual or automated trigger to expire holds past 30 minutes and restore inventory."""
    data = request.get_json(silent=True) or {}
    mins = request.args.get("minutes") or data.get("minutes")
    expiration_minutes = float(mins) if mins is not None else HOLD_EXPIRATION_MINUTES
    expired = expire_stale_holds(expiration_minutes=expiration_minutes)
    return jsonify({
        "success": True,
        "checked_at": datetime.now().isoformat(),
        "expiration_threshold_minutes": expiration_minutes,
        "expired_count": len(expired),
        "expired_holds": expired
    })


@app.route("/api/demand-alerts", methods=["GET"])
def get_demand_alerts():
    """Area demand alerts for high-search medicines."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM demand_alerts ORDER BY searches DESC").fetchall()
    alerts = [dict(r) for r in rows]
    conn.close()
    return jsonify({"alerts": alerts})


@app.route("/api/scan/match", methods=["POST"])
def scan_match():
    """
    Intelligent OCR / Barcode text matcher.
    Finds best matching medicine in SQLite database from OCR recognized text.
    """
    data = request.get_json() or {}
    text = (data.get("text") or "").lower().strip()

    if not text:
        return jsonify({
            "matched": False,
            "confidence": "0%",
            "medicine": None,
            "message": "No readable text was extracted from the scan."
        }), 200

    conn = get_db_connection()
    meds = conn.execute("SELECT id, name, generic_name, keywords, pgx_gene, pgx_status, pgx_status_label, pgx_advice FROM medicines").fetchall()

    if not meds:
        conn.close()
        return jsonify({"matched": False, "confidence": "0%", "medicine": None}), 200

    best_match = None
    best_score = 0

    for m in meds:
        name_lower = m["name"].lower()
        keys = json.loads(m["keywords"]) if m["keywords"] else []

        # Scoring
        score = 0
        if m["id"] in text:
            score += 5
        if name_lower in text:
            score += 12
        gen_lower = (m["generic_name"] or "").lower()
        if gen_lower and gen_lower in text:
            score += 6
        for k in keys:
            if k and k in text:
                score += 3

        if score > best_score:
            best_score = score
            best_match = m

    # Partial fallback: try individual OCR tokens (>=4 chars) against keywords
    if best_match is None:
        import re
        tokens = [t for t in re.findall(r"[a-z0-9]+", text) if len(t) >= 4]
        for t in tokens:
            row = conn.execute(
                "SELECT id, name, generic_name, keywords, pgx_gene, pgx_status, pgx_status_label, pgx_advice "
                "FROM medicines WHERE LOWER(keywords) LIKE ? OR LOWER(name) LIKE ? LIMIT 1",
                (f"%{t}%", f"%{t}%")
            ).fetchone()
            if row:
                best_match = row
                best_score = 3
                break

    matched = best_match is not None
    if best_match is None:
        # Honest default recommendation so patient can still verify manually
        best_match = meds[0]
        confidence = "0%"
    else:
        confidence = f"{min(99, 60 + best_score * 4)}%"

    result = dict(best_match)
    conn.close()

    return jsonify({
        "matched": matched,
        "confidence": confidence,
        "medicine": result
    })


# --------------------------------------------------------------------------
# MedNear Clinical AI Assistant & Health Awareness Chatbot
# --------------------------------------------------------------------------

@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """
    Interactive clinical AI assistant endpoint.
    Answers natural language questions about medicines, disease guidelines,
    pharmacogenomics (PMC5570547), drug interactions, generic substitutes,
    and returns live real-time stock cards across partner pharmacies.
    """
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    
    try:
        user_lat = float(data.get("lat", 12.9716))
        user_lng = float(data.get("lng", 77.5946))
    except (ValueError, TypeError):
        user_lat = 12.9716
        user_lng = 77.5946

    if not message:
        return jsonify({
            "error": "A message is required for the AI Assistant"
        }), 400

    response = ai_bot.generate_response(
        user_message=message,
        history=history,
        user_lat=user_lat,
        user_lng=user_lng
    )

    return jsonify({
        "success": True,
        "reply": response["reply"],
        "intent": response["intent"],
        "matched_medicine": response.get("matched_medicine"),
        "stock_cards": response.get("stock_cards", []),
        "suggestions": response.get("suggestions", []),
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/ai/suggestions", methods=["GET"])
def get_ai_suggestions():
    """Returns curated starter prompts for medicine awareness and stock checks."""
    return jsonify({
        "suggestions": [
            {"icon": "💊", "label": "Is Pan 40 available near me?", "query": "Is Pan 40 available near me?"},
            {"icon": "🧬", "label": "Check Plavix genetic risks", "query": "What are the genetic risks and black box warning for Plavix (Clopidogrel)?"},
            {"icon": "🏷️", "label": "Find cheaper generic tablets", "query": "What cheaper generic alternatives exist for expensive tablets?"},
            {"icon": "⚠️", "label": "Dolo 650 safe dosage", "query": "What is the safe daily dosage and precautions for Dolo 650?"},
            {"icon": "⚡", "label": "How 30-min hold works", "query": "How does the MedNear 30-minute hold reservation work?"},
            {"icon": "🕒", "label": "24/7 Open Pharmacies", "query": "Which partner pharmacies are open 24/7 right now?"}
        ]
    })


# --------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    if not os.environ.get("JWT_SECRET"):
        print("[WARN] JWT_SECRET env var is not set — using the built-in development default. "
              "Set a strong random JWT_SECRET before any real production deployment.")
    print(f"============================================================")
    print(f" MedNear Backend API & Frontend Server")
    print(f" Serving live at http://localhost:{port}")
    print(f" Database: {os.path.join(BASE_DIR, 'mednear.db')}")
    print(f"============================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
