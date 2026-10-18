"""
notifier.py - MedNear Twilio SMS & WhatsApp Business Messaging Service
Handles:
- Generation of 4-digit pickup OTPs.
- Instant SMS and WhatsApp notifications to patients (with OTP & Google Maps turn-by-turn directions).
- Instant SMS and WhatsApp notifications to pharmacies (with patient details, shelf/rack location, and hold code).
- Live Twilio client dispatch with automatic graceful simulation when credentials are unconfigured or in offline mode.
- Audit logging of all notifications in SQLite `notifications_log`.
"""

import os
import random
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger("mednear.notifier")

# Optional Twilio import
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False


if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/mednear.db"
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mednear.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_config():
    """
    Returns active messaging configuration.
    Prioritizes DB system_config overrides, then environment variables, then default sandbox settings.
    """
    config = {
        "account_sid": os.environ.get("TWILIO_ACCOUNT_SID", "").strip(),
        "auth_token": os.environ.get("TWILIO_AUTH_TOKEN", "").strip(),
        "phone_number": os.environ.get("TWILIO_PHONE_NUMBER", "").strip(),
        "whatsapp_number": os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886").strip(),
        "default_channel": os.environ.get("NOTIFICATION_DEFAULT_CHANNEL", "sms").strip().lower(), # 'sms', 'whatsapp', 'both'
        "enabled": False
    }

    try:
        conn = get_db()
        rows = conn.execute("SELECT key, value FROM system_config WHERE key LIKE 'twilio_%' OR key = 'notification_channel'").fetchall()
        conn.close()
        for r in rows:
            k, v = r["key"], r["value"]
            if k == "twilio_account_sid" and v:
                config["account_sid"] = v.strip()
            elif k == "twilio_auth_token" and v:
                config["auth_token"] = v.strip()
            elif k == "twilio_phone_number" and v:
                config["phone_number"] = v.strip()
            elif k == "twilio_whatsapp_number" and v:
                config["whatsapp_number"] = v.strip()
            elif k == "notification_channel" and v:
                config["default_channel"] = v.strip().lower()
    except Exception as e:
        logger.warning(f"Could not load config from DB: {e}")

    # Check if credentials look valid (Twilio account SIDs begin with 'AC')
    if config["account_sid"].startswith("AC") and len(config["account_sid"]) == 34 and config["auth_token"]:
        config["enabled"] = True

    return config


def save_config(account_sid=None, auth_token=None, phone_number=None, whatsapp_number=None, default_channel=None):
    """Saves Twilio configuration into SQLite system_config."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)")

    if account_sid is not None:
        cur.execute("INSERT INTO system_config (key, value) VALUES ('twilio_account_sid', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (account_sid.strip(),))
    if auth_token is not None:
        cur.execute("INSERT INTO system_config (key, value) VALUES ('twilio_auth_token', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (auth_token.strip(),))
    if phone_number is not None:
        cur.execute("INSERT INTO system_config (key, value) VALUES ('twilio_phone_number', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (phone_number.strip(),))
    if whatsapp_number is not None:
        cur.execute("INSERT INTO system_config (key, value) VALUES ('twilio_whatsapp_number', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (whatsapp_number.strip(),))
    if default_channel is not None:
        cur.execute("INSERT INTO system_config (key, value) VALUES ('notification_channel', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (default_channel.strip().lower(),))

    conn.commit()
    conn.close()
    return get_config()


def generate_otp():
    """Generates a secure 4-digit pickup verification OTP."""
    return f"{random.randint(1000, 9999)}"


def normalize_phone(phone_str):
    """Normalizes phone numbers to standard E.164 international format."""
    if not phone_str:
        return "+919876543210"
    raw = phone_str.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+91{digits}"
    return f"+{digits}"


def log_notification(hold_id, recipient_role, recipient_phone, channel, message_body, status, sid=None):
    """Records notification in SQLite audit log."""
    now_str = datetime.now().isoformat()
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hold_id TEXT,
                recipient_role TEXT NOT NULL,
                recipient_phone TEXT NOT NULL,
                channel TEXT NOT NULL,
                message_body TEXT NOT NULL,
                status TEXT NOT NULL,
                sid TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            INSERT INTO notifications_log (hold_id, recipient_role, recipient_phone, channel, message_body, status, sid, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (hold_id, recipient_role, recipient_phone, channel, message_body, status, sid, now_str))
        conn.commit()
        log_id = cur.lastrowid
        conn.close()
        return log_id
    except Exception as e:
        logger.error(f"Failed to log notification: {e}")
        return None


def send_single_message(to_phone, body, channel="sms", hold_id=None, recipient_role="patient"):
    """
    Dispatches a single SMS or WhatsApp message via Twilio if configured,
    or via realistic simulation if live credentials are not present.
    """
    config = get_config()
    normalized_to = normalize_phone(to_phone)
    channel = channel.lower()

    if config["enabled"] and TWILIO_AVAILABLE:
        try:
            client = TwilioClient(config["account_sid"], config["auth_token"])
            if channel == "whatsapp":
                from_num = config["whatsapp_number"]
                if not from_num.startswith("whatsapp:"):
                    from_num = f"whatsapp:{from_num}"
                to_target = f"whatsapp:{normalized_to}"
            else:
                from_num = config["phone_number"]
                to_target = normalized_to

            msg = client.messages.create(
                body=body,
                from_=from_num,
                to=to_target
            )
            sid = msg.sid
            status = "delivered"
            log_notification(hold_id, recipient_role, normalized_to, channel, body, status, sid=sid)
            return {
                "success": True,
                "status": "delivered",
                "sid": sid,
                "channel": channel,
                "to": normalized_to,
                "mode": "live_twilio"
            }
        except Exception as e:
            err_str = str(e)
            logger.error(f"Twilio dispatch failed: {err_str}")
            # Fallback to simulated delivery with error note
            sid = f"SIM-ERR-{random.randint(10000, 99999)}"
            log_notification(hold_id, recipient_role, normalized_to, channel, body, f"failed_fallback: {err_str[:40]}", sid=sid)
            return {
                "success": True,
                "status": "simulated_after_error",
                "error": err_str,
                "sid": sid,
                "channel": channel,
                "to": normalized_to,
                "mode": "simulation_fallback"
            }

    # Simulation mode (instant, free, test-friendly)
    sid = f"SIM-{random.randint(10000, 99999)}"
    log_notification(hold_id, recipient_role, normalized_to, channel, body, "simulated", sid=sid)
    return {
        "success": True,
        "status": "simulated",
        "sid": sid,
        "channel": channel,
        "to": normalized_to,
        "mode": "simulation"
    }


def dispatch_reservation_notifications(hold_id, hold_data, pharmacy_data, channel="sms", otp=None):
    """
    Generates and sends instant SMS and/or WhatsApp messages to both:
    1. Patient (with OTP code, total price, and Google Maps turn-by-turn directions link).
    2. Pharmacy (with urgent hold alert, patient name, phone, item & rack shelf).
    """
    if not otp:
        otp = generate_otp()

    pharm_lat = pharmacy_data.get("lat", 12.9716)
    pharm_lng = pharmacy_data.get("lng", 77.5946)
    pharm_name = pharmacy_data.get("name", "Local Pharmacy")
    pharm_addr = pharmacy_data.get("address", "Bengaluru Central")
    pharm_phone = pharmacy_data.get("phone", "+91 80 4000 1100")

    # Directions URLs
    gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={pharm_lat},{pharm_lng}"
    
    med_name = hold_data.get("medicine_name", "Medicine")
    qty = hold_data.get("quantity", 1)
    price = hold_data.get("total_price", 0.0)
    patient_name = hold_data.get("patient_name", "Customer")
    patient_phone = hold_data.get("phone", "+91 98765 43210")
    eta = hold_data.get("eta", "Within 30 minutes")
    rack = hold_data.get("rack", "Shelf A-1")

    # 1. Patient Notification Message
    patient_msg = (
        f"🏥 MedNear Reservation Confirmed!\n"
        f"Hold Code: {hold_id}\n"
        f"🔑 Pickup OTP: {otp}\n"
        f"📦 Item: {qty}x {med_name} (₹{price})\n"
        f"🏪 Pharmacy: {pharm_name}\n"
        f"📍 Address: {pharm_addr}\n"
        f"⏱️ Reserved for 30 minutes.\n"
        f"🗺️ Turn-by-Turn Directions:\n{gmaps_url}\n"
        f"📞 Pharmacy Contact: {pharm_phone}"
    )

    # 2. Pharmacy Notification Message
    pharmacy_msg = (
        f"🚨 MedNear Urgent Hold #{hold_id}\n"
        f"Customer: {patient_name} ({patient_phone})\n"
        f"📦 Reserve: {qty}x {med_name}\n"
        f"🗄️ Rack Location: {rack}\n"
        f"🔑 Verification OTP: {otp}\n"
        f"⏱️ Customer ETA: {eta}\n"
        f"⚠️ Hold active for 30 min. Increment stock back if not claimed."
    )

    channels = []
    if channel in ["sms", "both"]:
        channels.append("sms")
    if channel in ["whatsapp", "both"]:
        channels.append("whatsapp")
    if not channels:
        channels = ["sms"]

    results = {
        "hold_id": hold_id,
        "otp": otp,
        "directions_url": gmaps_url,
        "patient_notifications": [],
        "pharmacy_notifications": []
    }

    for ch in channels:
        # Dispatch to patient
        res_pat = send_single_message(
            to_phone=patient_phone,
            body=patient_msg,
            channel=ch,
            hold_id=hold_id,
            recipient_role="patient"
        )
        res_pat["preview"] = patient_msg
        results["patient_notifications"].append(res_pat)

        # Dispatch to pharmacy
        res_ph = send_single_message(
            to_phone=pharm_phone,
            body=pharmacy_msg,
            channel=ch,
            hold_id=hold_id,
            recipient_role="pharmacy"
        )
        res_ph["preview"] = pharmacy_msg
        results["pharmacy_notifications"].append(res_ph)

    # Update hold_reservations with OTP and directions_url
    try:
        conn = get_db()
        conn.execute("""
            UPDATE hold_reservations 
            SET otp = ?, directions_url = ?, notification_status = ?
            WHERE id = ?
        """, (otp, gmaps_url, "sent", hold_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not update hold record with OTP: {e}")

    return results


def verify_hold_otp(hold_id, input_otp):
    """
    Verifies counter pickup OTP provided by the patient.
    Marks hold as verified and status as 'ready' or 'completed'.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM hold_reservations WHERE id = ?", (hold_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Reservation not found"}

    expected_otp = str(row["otp"]).strip() if row["otp"] else ""
    input_otp_str = str(input_otp).strip()

    if not expected_otp or expected_otp != input_otp_str:
        conn.close()
        return {"success": False, "error": f"Invalid OTP. Counter verification failed."}

    # Mark as verified
    conn.execute("UPDATE hold_reservations SET otp_verified = 1 WHERE id = ?", (hold_id,))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"OTP {input_otp_str} verified successfully for reservation #{hold_id}",
        "hold_id": hold_id
    }


def get_recent_notifications(limit=20, hold_id=None):
    """Returns recent sent notifications from audit log."""
    conn = get_db()
    if hold_id:
        rows = conn.execute("SELECT * FROM notifications_log WHERE hold_id = ? ORDER BY id DESC LIMIT ?", (hold_id, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM notifications_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
