"""
MedNear Clinical AI Health & Medicine Assistant (ai_bot.py)
Provides public health awareness, live tablet stock queries,
pharmacogenomic precision guidance (PMC5570547), drug interactions,
and affordable generic alternatives.
"""

import os
import re
import json
import math
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mednear.db")

# Optional external LLM API keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# -----------------------------------------------------------------------------
# Clinical Medicine Knowledge Base (Indications, Dosage, Precautions, PGx)
# -----------------------------------------------------------------------------
MEDICINE_KNOWLEDGE = {
    "pantoprazole": {
        "name": "Pan 40 (Pantoprazole 40mg)",
        "generic": "Pantoprazole Gastro-Resistant (40mg)",
        "class": "Proton Pump Inhibitor (PPI) / Antacid",
        "uses": "Treatment of acid reflux (GERD), heartburn, gastric ulcers, Zollinger-Ellison syndrome, and prevention of NSAID-induced ulcers.",
        "how_to_take": "Take 1 tablet once daily in the morning, 30 to 60 minutes before breakfast with a glass of water. Swallow whole; do not chew or crush.",
        "common_side_effects": "Headache, mild diarrhea or constipation, nausea, flatulence, abdominal discomfort.",
        "pgx_gene": "CYP2C19 (Cytochrome P450 2C19)",
        "pgx_insight": "YELLOW CAUTION (CPIC-A): People who are CYP2C19 'Rapid' or 'Ultrarapid' metabolizers break down pantoprazole too quickly, resulting in subtherapeutic acid control and lingering ulcers. For these patients, doctors may double the dose to 80mg/day or switch to Rabeprazole (Razo 20), which is cleared via non-enzymatic pathways and is unaffected by CYP2C19 genetics.",
        "interactions": "Reduces absorption of Ketoconazole, Iron supplements, and Atazanavir. Can interact with Methotrexate and Warfarin.",
        "precautions": "Long-term usage (>1 year) may lower magnesium, vitamin B12 levels, and slightly increase bone fracture risk. Consult your physician for courses longer than 8 weeks.",
        "cheaper_generics": ["Pantoprazole 40 Generic (Jan Aushadhi) @ ₹42 (73% savings)", "Pantocid 40 (Sun Pharma) @ ₹125 (19% savings)", "Razo 20 (Rabeprazole - PGx safer) @ ₹110"]
    },
    "clopidogrel": {
        "name": "Plavix 75mg (Clopidogrel)",
        "generic": "Clopidogrel Bisulfate (75mg)",
        "class": "Antiplatelet / Thienopyridine Class",
        "uses": "Prevents blood clots after heart attack, stroke, coronary stent placement, or peripheral arterial disease.",
        "how_to_take": "Take 75mg once daily at the same time every day, with or without food. Take it strictly without skipping doses.",
        "common_side_effects": "Easy bruising, bleeding gums, nosebleeds, slight prolonged bleeding from minor cuts.",
        "pgx_gene": "CYP2C19 (*2, *3 loss-of-function alleles)",
        "pgx_insight": "RED ALERT / FDA BLACK BOX WARNING (CPIC-A, PMC5570547): Clopidogrel is an inactive prodrug that requires the CYP2C19 liver enzyme to become active. Roughly 15–30% of Asian and global populations carry CYP2C19 *2 or *3 loss-of-function mutations and cannot activate the drug. In these patients, clopidogrel fails, leading to catastrophic stent thrombosis and recurrent heart attacks. CPIC guidelines strongly recommend switching to Ticagrelor (Brilinta 90mg) or Prasugrel (Effient 10mg), which do not depend on CYP2C19.",
        "interactions": "CRITICAL: Do NOT take with Omeprazole or Esomeprazole because they block CYP2C19 and stop clopidogrel from working! If an antacid is needed, Pantoprazole or Rabeprazole is safer. Avoid combining with NSAIDs (Ibuprofen) without medical supervision due to bleeding risk.",
        "precautions": "Inform all surgeons and dentists that you take clopidogrel at least 5 to 7 days before any surgical procedure. Seek immediate emergency care for dark black stools, coughing blood, or severe dizziness.",
        "cheaper_generics": ["Deplatt 75 (Torrent Pharma) @ ₹108 (34% savings)", "Clavix 75 (Intas Pharma) @ ₹115 (30% savings)", "Ticagrelor 90 (CPIC-Preferred Genetic Alternative) @ ₹195"]
    },
    "simvastatin": {
        "name": "Zocor 40mg (Simvastatin)",
        "generic": "Simvastatin (40mg)",
        "class": "HMG-CoA Reductase Inhibitor (Statin / Cholesterol Lowering)",
        "uses": "Lowers LDL ('bad') cholesterol and triglycerides, raises HDL ('good') cholesterol, and reduces risks of heart disease, stroke, and angina.",
        "how_to_take": "Take 1 tablet once daily at night / evening, because the liver synthesizes the majority of cholesterol during sleep. Can be taken with or without food.",
        "common_side_effects": "Mild headache, nausea, mild joint pain, digestive upset.",
        "pgx_gene": "SLCO1B1 (Solute Carrier Organic Anion Transporter 1B1)",
        "pgx_insight": "RED ALERT / MUSCLE TOXICITY (CPIC-A, PMC5570547): The SLCO1B1 gene encodes the OATP1B1 transporter that transports statins into liver cells. People carrying the SLCO1B1 c.521T>C variant have impaired clearance, causing simvastatin to back up into the bloodstream. This leads to severe statin-induced myopathy, excruciating muscle pain, and dangerous rhabdomyolysis (kidney-damaging muscle breakdown). CPIC guidelines recommend switching to Rosuvastatin (Rosuvas 10) or Pravastatin, which have lower dependency on SLCO1B1.",
        "interactions": "NEVER consume large amounts of Grapefruit or grapefruit juice, as it blocks CYP3A4 metabolism and spikes simvastatin blood levels 5-fold! Interacts with Amlodipine (limit simvastatin to 20mg max), Diltiazem, Verapamil, and Clarithromycin.",
        "precautions": "Contact your doctor immediately if you notice unexplained muscle soreness, muscle tenderness, or dark tea-colored urine.",
        "cheaper_generics": ["Simvastatin 20 Generic (Jan Aushadhi) @ ₹35 (74% savings)", "Simvotin 40 (Sun Pharma) @ ₹110 (18% savings)", "Rosuvas 10 (Rosuvastatin - CPIC safer) @ ₹145"]
    },
    "augmentin": {
        "name": "Augmentin 625 Duo",
        "generic": "Amoxicillin (500mg) + Clavulanic Acid (125mg)",
        "class": "Antibacterial / Penicillin Class",
        "uses": "Treats bacterial infections of the respiratory tract, lungs (pneumonia), ear/sinus infections, urinary tract (UTIs), and skin/soft tissue infections.",
        "how_to_take": "Take 1 tablet every 12 hours (twice daily) at the start of a meal or with a light snack to maximize absorption and reduce stomach upset. Complete the full prescribed course (usually 5–7 days).",
        "common_side_effects": "Loose stools/diarrhea, mild nausea, skin rash, oral thrush (fungal overgrowth).",
        "pgx_gene": "Minimal Germline Variation (Green / Standard Formulary)",
        "pgx_insight": "GREEN / FAVORABLE: Augmentin has standard therapeutic efficacy without high-risk germline genetic metabolic roadblocks. However, verify the patient has NO history of severe Penicillin or Beta-lactam allergies.",
        "interactions": "Can decrease the efficacy of oral contraceptives. May interact with Allopurinol (increasing skin rash risk) and Methotrexate.",
        "precautions": "NEVER stop taking the antibiotic early when feeling better; finishing the full course prevents bacterial resistance. Take probiotics or yogurt 2 hours apart to maintain healthy gut flora.",
        "cheaper_generics": ["Moxikind-CV 625 (Mankind Pharma) @ ₹112 (38% savings)", "Amoxyclav 625 Generic (Jan Aushadhi) @ ₹55 (70% savings)"]
    },
    "dolo": {
        "name": "Dolo 650",
        "generic": "Paracetamol / Acetaminophen (650mg)",
        "class": "Analgesic & Antipyretic (Pain & Fever Reducer)",
        "uses": "Relief of mild to moderate fever, headaches, body aches, muscle soreness, dental pain, and cold symptoms.",
        "how_to_take": "Take 1 tablet every 4 to 6 hours as needed. Do NOT exceed 4 tablets (2600mg) in 24 hours without a doctor's direction. Maximum absolute clinical limit for healthy adults is 4000mg/day.",
        "common_side_effects": "Generally very well tolerated. Rare: mild allergic rash, nausea.",
        "pgx_gene": "Minimal Germline Variation (Green / Standard Formulary)",
        "pgx_insight": "GREEN / FAVORABLE (CPIC Non-Opioid Standard): Paracetamol is safe and does not carry the high-risk polymorphic genetic enzyme issues that plague opioid analgesics like Codeine and Tramadol (which depend on CYP2D6 and can cause fatal respiratory arrest in ultra-rapid metabolizers).",
        "interactions": "Avoid excessive alcohol consumption while taking paracetamol, as combined alcohol and paracetamol drastically elevates liver toxicity risk.",
        "precautions": "Do not combine with other cold/cough syrups or pain tablets that also contain paracetamol/acetaminophen to prevent accidental overdose. Patients with chronic liver disease must consult their doctor.",
        "cheaper_generics": ["Paracetamol 650 Generic (Jan Aushadhi) @ ₹12 (65% savings)", "Calpol 650 (GSK) @ ₹32", "Crocin 650 @ ₹33"]
    },
    "metformin": {
        "name": "Glycomet 500 SR",
        "generic": "Metformin Hydrochloride Sustained Release (500mg)",
        "class": "Antidiabetic / Biguanide",
        "uses": "First-line medication for the treatment and management of Type 2 Diabetes Mellitus to lower blood glucose and improve insulin sensitivity.",
        "how_to_take": "Take 1 tablet with or immediately after your evening meal with water. Swallow the sustained-release tablet whole; do not bite, crush, or chew it.",
        "common_side_effects": "Metallic taste, mild stomach bloating, gas, nausea, loose stools (usually subsides after the first 2 weeks).",
        "pgx_gene": "SLC22A1 (OCT1 Transporter)",
        "pgx_insight": "GREEN / FAVORABLE (FDA PGx Biomarker): Excellent first-line profile. Minor polymorphisms in the OCT1 transporter gene (SLC22A1) can influence how much metformin reaches the liver, occasionally affecting gastrointestinal tolerance, but therapy remains universally recommended.",
        "interactions": "Contrast dyes used in CT scans or X-rays can interact with metformin; inform your radiology doctor before imaging procedures. Alcohol increases the risk of lactic acidosis.",
        "precautions": "Regularly monitor renal function (creatinine/eGFR). Not recommended in severe kidney impairment (eGFR < 30 mL/min). Supplement with Vitamin B12 if on long-term therapy (>2 years).",
        "cheaper_generics": ["Metformin 500 SR Generic (Jan Aushadhi) @ ₹15 (68% savings)", "Okamet 500 SR (Cipla) @ ₹38", "Bigomet 500 @ ₹36"]
    },
    "cetirizine": {
        "name": "Alerid 10mg",
        "generic": "Cetirizine Hydrochloride (10mg)",
        "class": "Second-Generation Antihistamine / Anti-Allergic",
        "uses": "Relief of allergic rhinitis (sneezing, runny nose, itchy/watery eyes), seasonal hay fever, hives (urticaria), and skin allergic reactions.",
        "how_to_take": "Take 1 tablet (10mg) once daily, preferably in the evening before bedtime because it can cause mild drowsiness in some individuals.",
        "common_side_effects": "Mild drowsiness, dry mouth, tiredness, mild headache.",
        "pgx_gene": "Minimal Germline Variation (Green / Standard Formulary)",
        "pgx_insight": "GREEN / FAVORABLE: Cetirizine is excreted largely unchanged by the kidneys (80%) and does not rely on polymorphic hepatic CYP enzymes, ensuring predictable efficacy across all genotypes.",
        "interactions": "Avoid alcohol and sedative medications (sleeping pills, muscle relaxants), as they compound drowsiness.",
        "precautions": "Use caution when driving or operating heavy equipment until you know how the medication affects you. Drink plenty of water to counter dry mouth.",
        "cheaper_generics": ["Cetirizine 10 Generic (Jan Aushadhi) @ ₹8 (64% savings)", "Cetzine 10 (Dr. Reddy's) @ ₹18", "Zyrtec 10 @ ₹25"]
    },
    "azithromycin": {
        "name": "Azithral 500",
        "generic": "Azithromycin (500mg)",
        "class": "Macrolide Antibiotic",
        "uses": "Bacterial respiratory infections, strep throat, tonsillitis, sinus infections, community-acquired bronchitis/pneumonia, and bacterial skin infections.",
        "how_to_take": "Take 1 tablet once daily at the same time for 3 or 5 days as prescribed. Best taken on an empty stomach (1 hour before or 2 hours after a meal) with plenty of water.",
        "common_side_effects": "Mild stomach cramping, nausea, diarrhea, loss of appetite.",
        "pgx_gene": "Minimal Germline Variation (Green / Standard Formulary)",
        "pgx_insight": "GREEN / FAVORABLE: Standard macrolide with high tissue penetration and long half-life. No actionable CPIC germline gene variations affect basic metabolism.",
        "interactions": "Do NOT take antacids containing aluminum or magnesium at the same time, as they reduce azithromycin absorption; separate by at least 2 hours. Use caution with other drugs that prolong QT interval.",
        "precautions": "Patients with preexisting cardiac rhythm disorders or history of arrhythmias should consult their cardiologist. Complete the full 3-day or 5-day course without stopping.",
        "cheaper_generics": ["Azithromycin 500 Generic (Jan Aushadhi) @ ₹45 (63% savings)", "Azee 500 (Cipla) @ ₹98", "Zady 500 (Mankind) @ ₹92"]
    }
}

# General Disease & Symptom Awareness
DISEASE_KNOWLEDGE = {
    "gerd": {
        "title": "GERD / Acidity & Acid Peptic Disorders",
        "symptoms": "Heartburn, acid regurgitation, sour burps, burning chest discomfort after eating or lying down.",
        "lifestyle": "Eat smaller frequent meals, avoid spicy/fried foods, do not lie down within 2 hours of eating, elevate the head of your bed by 6 inches, avoid smoking and caffeine.",
        "medications": "Pantoprazole (Pan 40), Rabeprazole (Razo 20 - PGx preferred), Esomeprazole (Nexium). Antacids for immediate symptom relief.",
        "warning": "Seek emergency care if chest burning radiates to the left arm, jaw, or is accompanied by cold sweating, as these can be signs of a heart attack."
    },
    "cad": {
        "title": "Coronary Artery Disease & Heart Stent Protection",
        "symptoms": "Chest tightness on exertion, shortness of breath, fatigue.",
        "pgx_alert": "Critical: Clopidogrel (Plavix) fails in patients with CYP2C19 *2 or *3 loss-of-function variants. If you or a family member have had a cardiac stent, ask your cardiologist about CYP2C19 testing or Ticagrelor (Brilinta).",
        "lifestyle": "Strict low-sodium diet, smoking cessation, regular cardiologist follow-up, daily blood pressure monitoring."
    },
    "cholesterol": {
        "title": "Hyperlipidemia (High Cholesterol)",
        "symptoms": "Usually silent without symptoms until a cardiovascular event occurs. Detected via Lipid Profile blood test.",
        "pgx_alert": "Simvastatin has an FDA alert for SLCO1B1 gene variants that cause severe muscle breakdown. Rosuvastatin or Atorvastatin are modern alternatives.",
        "lifestyle": "Limit trans fats and red meats; increase soluble fiber (oats, flaxseeds, beans); engage in 30 minutes of aerobic exercise daily."
    },
    "diabetes": {
        "title": "Type 2 Diabetes Mellitus",
        "symptoms": "Frequent urination, excessive thirst, increased hunger, unexplained weight loss, blurry vision, slow-healing cuts.",
        "medications": "Metformin (Glycomet 500 SR), Glimepiride, Teneligliptin, SGLT2 inhibitors (Dapagliflozin).",
        "lifestyle": "Regular HbA1c testing every 3 months, low glycemic index diet, foot care inspection daily."
    },
    "hypertension": {
        "title": "Hypertension (High Blood Pressure)",
        "symptoms": "Often known as the 'silent killer' because it has no overt symptoms until complications arise. Severe cases may cause morning headaches, dizziness, nosebleeds.",
        "medications": "Telmisartan, Amlodipine, Enalapril, Atenolol.",
        "lifestyle": "DASH diet, reduce sodium intake to under 2 grams/day, stress management, regular blood pressure logs."
    }
}

# -----------------------------------------------------------------------------
# Haversine Distance Calculator
# -----------------------------------------------------------------------------
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates distance between two GPS coordinates in kilometers."""
    try:
        r = 6371.0  # Earth's radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r * c, 2)
    except Exception:
        return 1.5


# -----------------------------------------------------------------------------
# Live Database Query Helpers
# -----------------------------------------------------------------------------
def get_live_stock_for_medicine(med_id, user_lat=12.9716, user_lng=77.5946):
    """
    Queries real-time stock across all 6 partner pharmacies for a specific medicine.
    Returns sorted list of pharmacy stock cards.
    """
    if not os.path.exists(DB_PATH):
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Query stock joining pharmacies and inventory
        query = """
        SELECT 
            p.id as pharmacy_id,
            p.name as pharmacy_name,
            p.type as pharmacy_type,
            p.address,
            p.phone,
            p.lat,
            p.lng,
            p.hours_label,
            p.is_24_hours,
            p.rating,
            inv.status,
            inv.units,
            inv.price,
            inv.rack
        FROM pharmacy_inventory inv
        JOIN pharmacies p ON inv.pharmacy_id = p.id
        WHERE inv.medicine_id = ?
        """
        rows = cur.execute(query, (med_id,)).fetchall()
        conn.close()

        cards = []
        for r in rows:
            dist = calculate_distance(user_lat, user_lng, r["lat"], r["lng"])
            status = r["status"]
            units = r["units"]
            price = r["price"]

            cards.append({
                "pharmacy_id": r["pharmacy_id"],
                "pharmacy_name": r["pharmacy_name"],
                "address": r["address"],
                "phone": r["phone"],
                "distance_km": dist,
                "is_24_hours": bool(r["is_24_hours"]),
                "hours_label": r["hours_label"] or ("24/7 Open" if r["is_24_hours"] else "8:00 AM - 10:30 PM"),
                "rating": r["rating"],
                "status": status,  # "available", "limited", "unavailable"
                "units": units,
                "price": price,
                "rack": r["rack"] or "Main Dispensing Counter"
            })

        # Sort: available first, then limited, then unavailable, and within by distance
        status_rank = {"available": 0, "limited": 1, "unavailable": 2}
        cards.sort(key=lambda x: (status_rank.get(x["status"], 3), x["distance_km"]))
        return cards
    except Exception as e:
        print(f"[AIBotLiveQueryError] {e}")
        return []


def match_medicine_entity(text):
    """
    Identifies if a user question refers to any of the 8 catalog medicines or synonyms.
    """
    t = text.lower()
    
    # Direct alias matching
    alias_map = {
        "pantoprazole": ["pantoprazole", "pan 40", "pan40", "pantocid", "pantosec", "acidity", "gerd", "heartburn", "acid reflux", "stomach burn"],
        "clopidogrel": ["clopidogrel", "plavix", "clavix", "deplatt", "blood thinner", "stent", "cad", "heart attack", "antiplatelet", "thrombosis"],
        "simvastatin": ["simvastatin", "zocor", "simvotin", "cholesterol", "statin", "ldl", "hyperlipidemia"],
        "augmentin": ["augmentin", "amoxicillin", "amox", "moxikind", "novamox", "antibiotic", "bacterial infection"],
        "dolo": ["dolo", "dolo 650", "dolo650", "paracetamol", "calpol", "crocin", "pacimol", "acetaminophen", "fever", "headache", "body ache"],
        "metformin": ["metformin", "glycomet", "okamet", "diabetes", "diabetic", "blood sugar", "glucose"],
        "cetirizine": ["cetirizine", "alerid", "cetzine", "zyrtec", "allergy", "cold", "runny nose", "sneeze", "hives", "antihistamine"],
        "azithromycin": ["azithromycin", "azithral", "azee", "zady", "throat infection", "tonsil", "cough antibiotic"]
    }

    for med_id, aliases in alias_map.items():
        for a in aliases:
            # Word boundary check or substring match for multi-word
            if " " in a:
                if a in t:
                    return med_id
            else:
                if re.search(r"\b" + re.escape(a) + r"\b", t):
                    return med_id

    return None


# -----------------------------------------------------------------------------
# Intent Detection & Response Engine
# -----------------------------------------------------------------------------
def analyze_intent(text):
    """
    Classifies user message intent into distinct clinical & operational categories.
    """
    t = text.lower()

    # Emergency check
    if any(k in t for k in ["chest pain", "can't breathe", "cannot breathe", "choking", "unconscious", "stroke", "paralysis", "coughing blood", "severe bleeding"]):
        return "emergency"

    # Drug-drug interaction check (e.g., take with, mix, interact)
    if any(k in t for k in ["interaction", "together with", "take with", "mix with", "combine with", "take together", "can i take"]):
        return "drug_interaction"

    # Cheaper generic / substitutes inquiry
    if any(k in t for k in ["generic", "substitute", "alternative", "cheaper", "save money", "jan aushadhi", "discount"]):
        return "generic_substitutes"

    # Genetic / PGx query
    if any(k in t for k in ["gene", "genetics", "genetic", "pgx", "cyp2c19", "slco1b1", "cyp2d6", "pmc5570547", "dna", "metabolizer", "black box", "cpic"]):
        return "pgx_guidance"

    # Availability / stock inquiry
    if any(k in t for k in ["available", "in stock", "stock", "availability", "buy", "store", "chemist", "pharmacy near", "where to get", "where can i find", "who has", "price", "how much is", "units left", "24/7"]):
        return "stock_query"

    # Usage / dosage inquiry
    if any(k in t for k in ["how to take", "dosage", "dose", "when to take", "morning", "night", "empty stomach", "before food", "after food", "side effect"]):
        return "dosage_usage"

    # Reservation / hold feature query
    if any(k in t for k in ["hold", "reserve", "reservation", "30 min", "30-minute", "otp", "pickup"]):
        return "hold_reservation_info"

    # General medicine / tablet overview
    return "general_medicine"


def generate_response(user_message, history=None, user_lat=12.9716, user_lng=77.5946):
    """
    Main entry point for AI chatbot.
    Returns: {
        "reply": str (markdown formatted),
        "intent": str,
        "matched_medicine": dict or None,
        "stock_cards": list,
        "suggestions": list
    }
    """
    msg = user_message.strip()
    intent = analyze_intent(msg)
    matched_id = match_medicine_entity(msg)
    
    reply = ""
    stock_cards = []
    suggestions = []
    med_info = MEDICINE_KNOWLEDGE.get(matched_id) if matched_id else None

    # Handle EMERGENCY intent first
    if intent == "emergency":
        reply = (
            "### 🚨 URGENT MEDICAL EMERGENCY NOTICE\n\n"
            "If you or someone nearby is experiencing acute symptoms such as **severe chest pain**, "
            "**difficulty breathing**, **sudden weakness/speech difficulty**, or **heavy bleeding**, "
            "please take immediate emergency action:\n\n"
            "* 🚑 **Call National Emergency Ambulance**: **108** or **112** (India) / **911** (US)\n"
            "* 🏥 **Nearest 24/7 Hospital Emergency**: Visit your closest hospital emergency casualty department immediately.\n\n"
            "Do not wait for medication to arrive or attempt self-medication during a critical emergency."
        )
        suggestions = ["Find 24/7 Hospital Pharmacies", "Check Plavix availability", "Return to main menu"]
        return {
            "reply": reply,
            "intent": intent,
            "matched_medicine": None,
            "stock_cards": [],
            "suggestions": suggestions
        }

    # Handle 30-MINUTE HOLD RESERVATION query
    if intent == "hold_reservation_info":
        reply = (
            "### 📦 How MedNear 30-Minute Hold Reservation Works\n\n"
            "MedNear offers a **free, 0-prepayment 30-minute reservation** to guarantee your medicine isn't sold to someone else while you travel to the pharmacy:\n\n"
            "1. **Select Medicine & Partner Pharmacy**: Search your medicine and tap **'Reserve 30-Min Hold'**.\n"
            "2. **Instant Hold Lock**: The pharmacy's local stock is temporarily decremented so the shelf item is locked exclusively for you.\n"
            "3. **SMS & WhatsApp OTP**: You immediately receive a 6-digit pickup OTP and Google Maps turn-by-turn navigation link on your phone.\n"
            "4. **Walk In & Collect**: Present your OTP to the chemist within 30 minutes, pay at the counter, and collect your medication!\n\n"
            "💡 *If you cannot arrive within 30 minutes, the hold automatically expires and releases the unit back into public pharmacy inventory.*"
        )
        suggestions = ["Check Pan 40 availability", "Find 24/7 pharmacies", "Check Dolo 650 stock"]
        return {
            "reply": reply,
            "intent": intent,
            "matched_medicine": None,
            "stock_cards": [],
            "suggestions": suggestions
        }

    # If user asked about generic substitutes / Jan Aushadhi
    if intent == "generic_substitutes" and med_info:
        gens = "\n".join([f"* 🏷️ **{g}**" for g in med_info.get("cheaper_generics", [])])
        reply = (
            f"### 🏷️ Affordable Generic Alternatives for **{med_info['name']}**\n\n"
            f"The active therapeutic ingredient is **{med_info['generic']}** ({med_info['class']}).\n\n"
            f"You do not have to pay high brand-name prices for the exact same clinical efficacy. Here are verified alternatives and Jan Aushadhi generic options:\n\n"
            f"{gens}\n\n"
            f"**Pharmacist Tip:** Ask your local chemist for the **Jan Aushadhi** generic formulation or equivalent WHO-GMP certified brand. Always confirm the exact dosage strength before switching."
        )
        stock_cards = get_live_stock_for_medicine(matched_id, user_lat, user_lng)
        suggestions = [f"Check stock for {med_info['name']}", f"How to take {med_info['name']} safely", "Is this safe with my genetics?"]
        return {
            "reply": reply,
            "intent": intent,
            "matched_medicine": {"id": matched_id, "name": med_info["name"]},
            "stock_cards": stock_cards,
            "suggestions": suggestions
        }

    # If user asked about Pharmacogenomics / Genetics
    if intent == "pgx_guidance" or (med_info and any(k in msg.lower() for k in ["gene", "genetics", "pgx", "cyp2c19", "slco1b1"])):
        if med_info:
            reply = (
                f"### 🧬 Pharmacogenomic (PGx) Precision Awareness: **{med_info['name']}**\n\n"
                f"**Associated Gene:** `{med_info['pgx_gene']}`\n\n"
                f"{med_info['pgx_insight']}\n\n"
                f"#### 📚 Scientific Evidence & Background (PMC5570547)\n"
                f"Under clinical pharmacogenomic standards (Clinical Pharmacogenetics Implementation Consortium - CPIC):\n"
                f"* Human germline genetic variations alter liver enzyme metabolism.\n"
                f"* Prescribing the wrong drug without genetic awareness can lead to severe adverse drug reactions (ADRs) or total therapy failure.\n"
                f"* **What you should do:** If you are prescribed this medication for chronic conditions, consider discussing **CYP2C19** or **SLCO1B1** pre-prescription testing with your physician."
            )
            stock_cards = get_live_stock_for_medicine(matched_id, user_lat, user_lng)
            suggestions = [f"Find nearby stock of {med_info['name']}", f"Generic alternatives for {med_info['name']}", "How to take this tablet safely"]
            return {
                "reply": reply,
                "intent": "pgx_guidance",
                "matched_medicine": {"id": matched_id, "name": med_info["name"]},
                "stock_cards": stock_cards,
                "suggestions": suggestions
            }
        else:
            reply = (
                "### 🧬 What is Pharmacogenomics (PGx)?\n\n"
                "Pharmacogenomics is the study of how your unique DNA and genetic makeup affect how your body responds to medications:\n\n"
                "* **CYP2C19 Gene:** Controls antiplatelet drugs like **Clopidogrel (Plavix)** and antacids like **Pantoprazole (Pan 40)**. Poor metabolizers have an FDA Black Box Warning for clot risks.\n"
                "* **SLCO1B1 Gene:** Controls statin transport. Patients with the c.521T>C variant taking **Simvastatin (Zocor)** suffer severe toxic muscle pain (myopathy).\n"
                "* **CYP2D6 Gene:** Regulates painkillers like Codeine and Tramadol. Ultra-rapid metabolizers can face life-threatening toxicity.\n\n"
                "MedNear integrates the **PMC5570547 precision database** with traffic light clinical decision support (🟢 Green / 🟡 Caution / 🔴 High Genetic Alert) to protect patients."
            )
            suggestions = ["Explain Clopidogrel genetic risk", "Explain Simvastatin muscle warning", "Check tablet stock near me"]
            return {
                "reply": reply,
                "intent": "pgx_guidance",
                "matched_medicine": None,
                "stock_cards": [],
                "suggestions": suggestions
            }

    # If user asked about Drug-Drug Interactions
    if intent == "drug_interaction":
        if "clopidogrel" in msg.lower() and ("omeprazole" in msg.lower() or "pan 40" in msg.lower() or "pantoprazole" in msg.lower() or "antacid" in msg.lower()):
            reply = (
                "### ⚠️ Critical Drug Interaction Alert: Clopidogrel + PPI Antacids\n\n"
                "* **🔴 Omeprazole / Esomeprazole + Clopidogrel (Plavix):** **DO NOT COMBINE!** Omeprazole strongly inhibits the CYP2C19 enzyme, preventing clopidogrel from turning into its active clot-preventing form. This significantly spikes your risk of heart attack and stent thrombosis.\n"
                "* **🟡 Pantoprazole (Pan 40) or Rabeprazole (Razo 20):** These PPIs have significantly lower affinity for CYP2C19 and are clinically preferred if you require stomach acid protection while on antiplatelet therapy.\n"
                "* **Recommendation:** Talk to your cardiologist before starting any over-the-counter antacid while on blood thinners."
            )
        elif med_info:
            reply = (
                f"### ⚠️ Drug Interactions & Safety for **{med_info['name']}**\n\n"
                f"**Key Known Interactions:**\n{med_info['interactions']}\n\n"
                f"**Precautions & Red Flags:**\n{med_info['precautions']}\n\n"
                f"**Rule of Thumb:** Always inform your pharmacist and doctor about ALL supplements, over-the-counter tablets, and herbal medicines you are currently taking."
            )
        else:
            reply = (
                "### ⚠️ Drug Interaction Checker\n\n"
                "Certain tablets cannot be taken together because one drug can block, amplify, or cause dangerous side effects with another.\n\n"
                "**Common dangerous pairs to avoid:**\n"
                "* 🚫 **Clopidogrel (Plavix) + Omeprazole**: Omeprazole blocks blood thinner activation.\n"
                "* 🚫 **Simvastatin + Grapefruit Juice**: Grapefruit causes statin blood levels to spike dangerously.\n"
                "* 🚫 **Paracetamol + Alcohol**: Severe combined liver toxicity.\n"
                "* 🚫 **Antibiotics (Augmentin) + Oral Contraceptives**: May reduce birth control efficacy.\n\n"
                "Please tell me the exact names of the tablets you want to check!"
            )
        suggestions = ["Check Pan 40 stock", "Check Plavix stock", "Ask about generic alternatives"]
        return {
            "reply": reply,
            "intent": "drug_interaction",
            "matched_medicine": {"id": matched_id, "name": med_info["name"]} if med_info else None,
            "stock_cards": get_live_stock_for_medicine(matched_id, user_lat, user_lng) if matched_id else [],
            "suggestions": suggestions
        }

    # If matched a specific medicine (Stock query OR General Medicine info)
    if matched_id and med_info:
        stock_cards = get_live_stock_for_medicine(matched_id, user_lat, user_lng)
        in_stock_count = sum(1 for c in stock_cards if c["status"] == "available")
        limited_count = sum(1 for c in stock_cards if c["status"] == "limited")

        # Build stock status summary
        if in_stock_count > 0:
            stock_summary = f"🟢 **In Stock Now:** Available at **{in_stock_count} partner pharmacies** near you (plus {limited_count} with limited units)."
        elif limited_count > 0:
            stock_summary = f"🟡 **Limited Stock:** Available in limited quantities at {limited_count} partner pharmacies."
        else:
            stock_summary = "🔴 **Currently Out of Stock** in primary partner locations, but generic substitutes are available."

        reply = (
            f"### 💊 **{med_info['name']}**\n\n"
            f"**Generic Active Salt:** {med_info['generic']}  \n"
            f"**Therapeutic Class:** {med_info['class']}  \n\n"
            f"{stock_summary}\n\n"
            f"#### 📋 Key Medical Knowledge & Safe Usage:\n"
            f"* **Primary Uses:** {med_info['uses']}\n"
            f"* **How to Take:** {med_info['how_to_take']}\n"
            f"* **Common Side Effects:** {med_info['common_side_effects']}\n"
            f"* **🧬 Precision Genetics ({med_info['pgx_gene']}):** {med_info['pgx_insight'][:180]}...\n\n"
            f"👇 **See live pharmacy stock, distances, and prices below. Tap 'Reserve 30-Min Hold' to secure your strip instantly with 0 prepayment!**"
        )
        suggestions = [
            f"Cheaper generic options for {med_info['name']}",
            f"Explain {med_info['pgx_gene']} genetic risk in detail",
            f"Can I take {med_info['name']} with other medicines?",
            "How does 30-min hold work?"
        ]
        return {
            "reply": reply,
            "intent": "stock_query",
            "matched_medicine": {"id": matched_id, "name": med_info["name"], "generic": med_info["generic"]},
            "stock_cards": stock_cards,
            "suggestions": suggestions
        }

    # General overview or query when no medicine name was matched
    # Check if user asked about all available tablets
    if any(k in msg.lower() for k in ["what tablets", "all tablets", "list of medicines", "what medicines", "available tablets", "catalog"]):
        reply = (
            "### 💊 MedNear Verified Tablet Catalog & Stock Overview\n\n"
            "Here are the active medicines tracked in real time across our 6 partner pharmacies with precision pharmacogenomics:\n\n"
            "1. **Pan 40 (Pantoprazole 40mg)** — Acidity, GERD & heartburn relief (CYP2C19 Caution)\n"
            "2. **Plavix 75mg (Clopidogrel)** — Blood thinner & heart stent care (CYP2C19 High Risk)\n"
            "3. **Zocor 40mg (Simvastatin)** — Cholesterol lowering (SLCO1B1 Muscle Alert)\n"
            "4. **Augmentin 625 Duo** — Broad-spectrum bacterial antibiotic\n"
            "5. **Dolo 650 (Paracetamol)** — Fever, headache & body ache relief (OTC)\n"
            "6. **Glycomet 500 SR (Metformin)** — Type 2 Diabetes blood sugar control\n"
            "7. **Alerid 10mg (Cetirizine)** — Allergy, sneezing, hives & rhinitis\n"
            "8. **Azithral 500 (Azithromycin)** — Macrolide respiratory & throat antibiotic\n\n"
            "💬 *Ask me about any tablet above (e.g., 'Is Dolo 650 in stock?' or 'What are the risks of Plavix?') to see live shelf inventory, prices, and directions!*"
        )
        suggestions = ["Is Pan 40 available?", "Check Plavix heart risk", "Find Dolo 650 near me", "Show 24/7 pharmacies"]
        return {
            "reply": reply,
            "intent": "catalog_overview",
            "matched_medicine": None,
            "stock_cards": [],
            "suggestions": suggestions
        }

    # Default friendly greeting / awareness prompt
    reply = (
        "### 👋 Hello! I am MedNear AI Clinical Assistant\n\n"
        "I am here to help you make informed, safe, and cost-effective medication decisions:\n\n"
        "* 🔍 **Check Live Stock**: Ask if any tablet is in stock across nearby partner pharmacies.\n"
        "* 📖 **Medicine Awareness**: Learn what your tablets do, correct dosages, and whether to take them before or after food.\n"
        "* 🧬 **Pharmacogenomic (PGx) Safety**: Check whether your genetics (CYP2C19, SLCO1B1) put you at risk for drug resistance or toxicity.\n"
        "* 🏷️ **Generic Alternatives**: Discover Jan Aushadhi and generic tablets that save up to 70% on prescription costs.\n"
        "* ⚡ **30-Min Hold**: Lock your medication for 30 minutes with a 6-digit pickup OTP so it won't sell out while you travel.\n\n"
        "**Try asking one of the popular questions below:**"
    )
    suggestions = [
        "Is Pan 40 available near me?",
        "What are the genetic risks of Plavix?",
        "Where can I buy Dolo 650 right now?",
        "Which pharmacies are open 24/7?",
        "Show cheaper generic alternatives"
    ]
    return {
        "reply": reply,
        "intent": "general_greeting",
        "matched_medicine": None,
        "stock_cards": [],
        "suggestions": suggestions
    }
