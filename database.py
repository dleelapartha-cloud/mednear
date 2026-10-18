"""
Database module for MedNear (SQLite)
Handles schema initialization, seeding with PMC5570547 data, and DB queries.
"""

import sqlite3
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

if os.environ.get("VERCEL"):
    import shutil
    tmp_db = "/tmp/mednear.db"
    orig_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mednear.db")
    if not os.path.exists(tmp_db) and os.path.exists(orig_db):
        try:
            shutil.copyfile(orig_db, tmp_db)
        except Exception:
            pass
    DB_PATH = tmp_db
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mednear.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL journaling + busy timeout prevent 'database is locked' errors when
    # gunicorn runs multiple workers/threads or the hold-expiration cron writes
    # concurrently with request handlers.
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS medicines (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        generic_name TEXT NOT NULL,
        form TEXT,
        category TEXT,
        schedule TEXT,
        avg_price REAL,
        usage TEXT,
        safety TEXT,
        pgx_gene TEXT,
        pgx_status TEXT,
        pgx_status_label TEXT,
        pgx_evidence TEXT,
        pgx_advice TEXT,
        keywords TEXT
    );

    CREATE TABLE IF NOT EXISTS generic_substitutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_id TEXT NOT NULL,
        name TEXT NOT NULL,
        company TEXT,
        price REAL,
        savings TEXT,
        FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS diseases (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        synonyms TEXT,
        primary_gene TEXT,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS disease_drugs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        disease_id TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        gene TEXT,
        status_label TEXT,
        guidance TEXT,
        evidence TEXT,
        med_key TEXT,
        FOREIGN KEY (disease_id) REFERENCES diseases(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS pharmacies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        address TEXT NOT NULL,
        phone TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        open_time TEXT,
        close_time TEXT,
        hours_label TEXT,
        is_24_hours INTEGER DEFAULT 0,
        rating REAL DEFAULT 4.8,
        reviews_count INTEGER DEFAULT 100
    );

    CREATE TABLE IF NOT EXISTS pharmacy_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pharmacy_id TEXT NOT NULL,
        medicine_id TEXT NOT NULL,
        status TEXT NOT NULL,
        units INTEGER DEFAULT 0,
        price REAL NOT NULL,
        rack TEXT,
        updated_at TEXT,
        UNIQUE(pharmacy_id, medicine_id),
        FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id) ON DELETE CASCADE,
        FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS hold_reservations (
        id TEXT PRIMARY KEY,
        store_id TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        medicine_id TEXT NOT NULL,
        medicine_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        total_price REAL NOT NULL,
        eta TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        FOREIGN KEY (store_id) REFERENCES pharmacies(id) ON DELETE CASCADE,
        FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS demand_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_name TEXT NOT NULL,
        searches INTEGER NOT NULL,
        time_window TEXT NOT NULL,
        status TEXT NOT NULL,
        stock_note TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL CHECK(role IN ('patient', 'pharmacist', 'admin')),
        pharmacy_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT
    );

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
    );
    """)

    # Ensure required columns exist in hold_reservations if migrating
    cursor.execute("PRAGMA table_info(hold_reservations)")
    columns = [col[1] for col in cursor.fetchall()]
    if "patient_id" not in columns:
        cursor.execute("ALTER TABLE hold_reservations ADD COLUMN patient_id TEXT")
    if "otp" not in columns:
        cursor.execute("ALTER TABLE hold_reservations ADD COLUMN otp TEXT")
    if "otp_verified" not in columns:
        cursor.execute("ALTER TABLE hold_reservations ADD COLUMN otp_verified INTEGER DEFAULT 0")
    if "directions_url" not in columns:
        cursor.execute("ALTER TABLE hold_reservations ADD COLUMN directions_url TEXT")
    if "notification_status" not in columns:
        cursor.execute("ALTER TABLE hold_reservations ADD COLUMN notification_status TEXT DEFAULT 'pending'")

    # Seed initial data if tables are empty
    cursor.execute("SELECT COUNT(*) FROM medicines")
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)

    # Seed users if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        seed_users(cursor)

    conn.commit()
    conn.close()


def seed_data(cursor):
    # 1. Medicines & PMC5570547 annotations
    medicines = [
        (
            "pantoprazole",
            "Pan 40 (Pantoprazole 40mg)",
            "Pantoprazole Gastro-Resistant (40mg)",
            "Tablet (Strip of 15)",
            "Proton Pump Inhibitor (PPI) / Antacid",
            "Schedule H",
            155.0,
            "Treatment of GERD, acid reflux, heartburn, and peptic ulcers.",
            "Best taken in morning 30–60 minutes before food on an empty stomach.",
            "CYP2C19",
            "yellow",
            "🟡 Caution / Dose Adjustment",
            "CPIC-A · FDA PGx Biomarker · GPS Level 1",
            "Extensive/rapid metabolizers may experience subtherapeutic acid suppression. Consider doubling dose to 80mg or switching to Rabeprazole.",
            json.dumps(["pan 40", "pantoprazole", "pantocid", "pantosec", "acidity", "gas", "gerd", "ulcer", "heartburn", "omeprazole", "rabeprazole"])
        ),
        (
            "clopidogrel",
            "Plavix 75mg (Clopidogrel)",
            "Clopidogrel Bisulfate (75mg)",
            "Tablet (Strip of 10)",
            "Antiplatelet / Thienopyridine Class",
            "Schedule H (Prescription Required)",
            165.0,
            "Prevention of vascular ischemia, myocardial infarction, and stent thrombosis.",
            "Must be taken consistently daily. Strictly monitor for unexplained bruising or bleeding.",
            "CYP2C19 (*2, *3 loss-of-function)",
            "red",
            "🔴 High Risk / FDA Black Box Warning",
            "CPIC-A Level 1 · FDA Boxed Warning · GPS Level 1 (PMC5570547)",
            "BLACK BOX WARNING: CYP2C19 loss-of-function allele carriers cannot convert prodrug to active form. Severe risk of stent thrombosis and death. Switch to Ticagrelor or Prasugrel.",
            json.dumps(["clopidogrel", "plavix", "clavix", "deplatt", "stent", "blood thinner", "cad", "heart", "aspirin"])
        ),
        (
            "simvastatin",
            "Zocor 40mg (Simvastatin)",
            "Simvastatin (40mg)",
            "Tablet (Strip of 10)",
            "HMG-CoA Reductase Inhibitor (Statin)",
            "Schedule H",
            135.0,
            "Lowering LDL cholesterol and reducing risk of stroke and myocardial infarction.",
            "Take in the evening. Report unexplained muscle aches or weakness immediately.",
            "SLCO1B1 (Solute Carrier Organic Anion Transporter)",
            "red",
            "🔴 High Risk / Muscle Toxicity Alert",
            "CPIC-A Level 1 · FDA PGx Label · GPS Level 1 (PMC5570547)",
            "HIGH RISK: SLCO1B1 c.521T>C carriers have impaired hepatic clearance, causing toxic serum accumulation and severe rhabdomyolysis / muscle tears. Switch to Rosuvastatin or Pravastatin.",
            json.dumps(["simvastatin", "zocor", "simvotin", "cholesterol", "statin", "rosuvastatin", "atorvastatin", "hyperlipidemia"])
        ),
        (
            "augmentin",
            "Augmentin 625 Duo",
            "Amoxicillin (500mg) + Clavulanic Acid (125mg)",
            "Tablet (Strip of 10)",
            "Antibacterial / Penicillin Class",
            "Schedule H (Prescription Required)",
            182.0,
            "Bacterial infections of the respiratory tract, lungs, ears, sinuses, and urinary tract.",
            "Take immediately before or with a meal. Complete full 5–7 day prescribed course.",
            "Minimal Germline Variation",
            "green",
            "🟢 Favorable Response",
            "Standard Antimicrobial Formulary · PMC5570547",
            "Standard therapeutic response. Confirm patient has no medical history of severe penicillin allergies.",
            json.dumps(["amoxicillin", "clavulanic", "augmentin", "moxikind", "novamox", "antibiotic", "amox", "bacterial"])
        ),
        (
            "dolo",
            "Dolo 650",
            "Paracetamol / Acetaminophen (650mg)",
            "Tablet (Strip of 15)",
            "Analgesic & Antipyretic",
            "OTC (Over-The-Counter)",
            34.0,
            "Relief of mild to moderate fever, headaches, body ache, and muscle soreness.",
            "Do not exceed 4000mg/day. Maintain at least 4–6 hours between doses.",
            "Minimal Germline Variation",
            "green",
            "🟢 Favorable Response",
            "CPIC Analgesic Standard · PMC5570547",
            "Favorable first-line non-opioid analgesic without high-risk germline genetic variants like those affecting codeine/tramadol.",
            json.dumps(["dolo", "dolo 650", "paracetamol", "calpol", "crocin", "pacimol", "acetaminophen", "fever", "headache", "tylenol"])
        ),
        (
            "metformin",
            "Glycomet 500 SR",
            "Metformin Hydrochloride Sustained Release (500mg)",
            "Tablet (Strip of 20)",
            "Antidiabetic / Biguanide",
            "Schedule H",
            48.0,
            "Management of Type 2 Diabetes Mellitus to lower blood glucose levels.",
            "Take with or right after dinner. Swallow whole, do not crush sustained-release tablets.",
            "SLC22A1 (OCT1 Transporter)",
            "green",
            "🟢 Favorable Response",
            "FDA PGx Biomarker · GPS Level 1",
            "Favorable first-line oral antidiabetic. Minor OCT1 variants may alter gastrointestinal tolerance; monitor HbA1c.",
            json.dumps(["metformin", "glycomet", "okamet", "sugar", "diabetes", "diabetic", "glucophage"])
        ),
        (
            "cetirizine",
            "Alerid 10mg",
            "Cetirizine Hydrochloride (10mg)",
            "Tablet (Strip of 10)",
            "Antihistamine / Anti-Allergic",
            "OTC / Schedule H",
            22.0,
            "Treatment of allergic rhinitis, hay fever, sneezing, runny nose, and hives.",
            "May induce mild drowsiness. Avoid driving or operating machinery immediately after taking.",
            "Minimal Germline Variation",
            "green",
            "🟢 Favorable Response",
            "Standard Formulary",
            "Favorable. Does not rely on polymorphic CYP2D6 or CYP2C19 enzymes.",
            json.dumps(["cetirizine", "alerid", "cetzine", "zyrtec", "allergy", "cold", "sneeze", "hives"])
        ),
        (
            "azithromycin",
            "Azithral 500",
            "Azithromycin (500mg)",
            "Tablet (Strip of 5)",
            "Macrolide Antibiotic",
            "Schedule H",
            122.0,
            "Throat infections, tonsillitis, bronchitis, community-acquired pneumonia, and bacterial skin infections.",
            "Usually taken once daily at the same time, either 1 hour before or 2 hours after a meal.",
            "Minimal Germline Variation",
            "green",
            "🟢 Favorable Response",
            "Antimicrobial Standard",
            "Favorable macrolide coverage without high-risk germline metabolic variation.",
            json.dumps(["azithral", "azithromycin", "azee", "zady", "antibiotic", "throat", "cough"])
        )
    ]

    cursor.executemany("""
    INSERT INTO medicines (
        id, name, generic_name, form, category, schedule, avg_price, usage, safety,
        pgx_gene, pgx_status, pgx_status_label, pgx_evidence, pgx_advice, keywords
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, medicines)

    # 2. Generic Substitutes
    substitutes = [
        ("pantoprazole", "Pantocid 40", "Sun Pharma", 125.0, "19% Cheaper"),
        ("pantoprazole", "Razo 20 (Rabeprazole - PGx Safer)", "Dr. Reddy's", 110.0, "29% Cheaper"),
        ("pantoprazole", "Pantoprazole 40 Generic", "Jan Aushadhi", 42.0, "73% Cheaper"),

        ("clopidogrel", "Clavix 75", "Intas Pharma", 115.0, "30% Cheaper"),
        ("clopidogrel", "Deplatt 75", "Torrent Pharma", 108.0, "34% Cheaper"),
        ("clopidogrel", "Ticagrelor 90 (PGx Favorable)", "AstraZeneca", 195.0, "CPIC Preferred"),

        ("simvastatin", "Simvotin 40", "Sun Pharma", 110.0, "18% Cheaper"),
        ("simvastatin", "Rosuvas 10 (Rosuvastatin - PGx Safer)", "Sun Pharma", 145.0, "CPIC Preferred"),
        ("simvastatin", "Simvastatin 20 Generic", "Jan Aushadhi", 35.0, "74% Cheaper"),

        ("augmentin", "Moxikind-CV 625", "Mankind Pharma", 112.0, "38% Cheaper"),
        ("augmentin", "Novamox-CV 625", "Cipla", 118.0, "35% Cheaper"),
        ("augmentin", "Amoxyclav 625 Generic", "Jan Aushadhi", 68.0, "62% Cheaper"),

        ("dolo", "Calpol 650", "GSK", 31.0, "9% Cheaper"),
        ("dolo", "Pacimol 650", "Ipca", 28.0, "18% Cheaper"),
        ("dolo", "Paracetamol 650 Generic", "Jan Aushadhi", 14.0, "58% Cheaper"),

        ("metformin", "Okamet 500", "Cipla", 36.0, "25% Cheaper"),
        ("metformin", "Metfor 500 SR", "Sun Pharma", 38.0, "21% Cheaper"),
        ("metformin", "Metformin 500 Generic", "Jan Aushadhi", 16.0, "66% Cheaper"),

        ("cetirizine", "Cetzine 10mg", "GSK", 19.0, "14% Cheaper"),
        ("cetirizine", "Zyrtec 10mg", "Dr. Reddy's", 21.0, "5% Cheaper"),
        ("cetirizine", "Cetirizine 10 Generic", "Jan Aushadhi", 8.0, "64% Cheaper"),

        ("azithromycin", "Zady 500", "Mankind", 89.0, "27% Cheaper"),
        ("azithromycin", "Azee 500", "Cipla", 95.0, "22% Cheaper"),
        ("azithromycin", "Azithromycin 500 Generic", "Jan Aushadhi", 45.0, "63% Cheaper")
    ]

    cursor.executemany("""
    INSERT INTO generic_substitutes (medicine_id, name, company, price, savings)
    VALUES (?, ?, ?, ?, ?)
    """, substitutes)

    # 3. Diseases (PMC5570547)
    diseases = [
        (
            "gerd",
            "Gastroesophageal Reflux Disease (GERD) & Acid Peptic Disorders",
            json.dumps(["gerd", "acid reflux", "acidity", "heartburn", "gastritis", "peptic ulcer", "stomach ulcer"]),
            "CYP2C19 (Cytochrome P450 2C19)",
            "CYP2C19 extensive/rapid metabolizers clear standard PPIs too fast, causing persistent acid secretion and ulcer failure."
        ),
        (
            "cad",
            "Coronary Artery Disease (CAD), Thrombosis & Post-Stent Care",
            json.dumps(["cad", "coronary artery disease", "heart disease", "angina", "stent", "thrombosis", "heart attack", "myocardial infarction"]),
            "CYP2C19, CYP2C9, VKORC1, CYP2D6",
            "Crucial antiplatelet & cardiovascular genetics: impaired CYP2C19 bioactivation of clopidogrel leads to catastrophic stent thrombosis."
        ),
        (
            "hyperlipidemia",
            "Hyperlipidemia (High Cholesterol & Atherosclerosis Prevention)",
            json.dumps(["hyperlipidemia", "high cholesterol", "cholesterol", "dyslipidemia", "triglycerides", "statin"]),
            "SLCO1B1 (Solute Carrier Organic Anion Transporter 1B1)",
            "Hepatic transporter genetics: impaired SLCO1B1 function prevents statin clearance into hepatocytes, creating muscle toxicity."
        ),
        (
            "pain",
            "Pain Management & Musculoskeletal Disorders",
            json.dumps(["pain", "musculoskeletal", "back pain", "arthritis", "joint pain", "headache", "analgesic"]),
            "CYP2D6, CYP2C9",
            "Opioid and NSAID pharmacogenetics: variable metabolic activation risks either fatal respiratory depression or complete lack of analgesia."
        ),
        (
            "depression",
            "Major Depressive Disorder & Anxiety",
            json.dumps(["depression", "anxiety", "antidepressant", "mental health", "stress"]),
            "CYP2C19, CYP2D6",
            "SSRI and TCA metabolism: poor metabolizers suffer severe QTc cardiac prolongation and adverse toxicity."
        )
    ]

    cursor.executemany("""
    INSERT INTO diseases (id, title, synonyms, primary_gene, description)
    VALUES (?, ?, ?, ?, ?)
    """, diseases)

    # 4. Disease Drugs (PMC5570547)
    disease_drugs = [
        ("gerd", "Rabeprazole (Pariet / Razo 20)", "green", "CYP2C19", "🟢 Favorable Response", "Preferred choice. Metabolized predominantly via non-enzymatic reduction; acid suppression is stable and independent of CYP2C19 genotype.", "CPIC / FDA Level 1", "pantoprazole"),
        ("gerd", "Esomeprazole (Nexium 40)", "green", "CYP2C19", "🟢 Favorable Response", "Favorable. S-isomer has higher intrinsic bioavailability and greater therapeutic plasma area than racemic omeprazole.", "CPIC / GPS Level 1", "pantoprazole"),
        ("gerd", "Pantoprazole (Pan 40)", "yellow", "CYP2C19", "🟡 Caution / Dose Adjustment", "Caution: CYP2C19 rapid metabolizers have subtherapeutic acid suppression. Consider doubling dose to 80mg/day or switching to rabeprazole.", "CPIC-A / FDA Biomarker", "pantoprazole"),
        ("gerd", "Lansoprazole (Prevacid 30)", "yellow", "CYP2C19", "🟡 Caution / Dose Adjustment", "Caution: Higher clearance in rapid metabolizers reduces esophageal mucosal healing rates.", "FDA PGx Label", "pantoprazole"),
        ("gerd", "Omeprazole (Prilosec / Omez 20)", "red", "CYP2C19", "🔴 High Genetic Risk", "Extensive metabolizers have 80% lower plasma concentration; high risk of treatment failure in severe erosive esophagitis and H. pylori.", "CPIC-A / FDA Boxed Warning", "pantoprazole"),

        ("cad", "Ticagrelor (Brilinta 90mg)", "green", "None (Direct P2Y12)", "🟢 Favorable Response", "Preferred alternative. Direct-acting P2Y12 inhibitor that does NOT require hepatic CYP2C19 bioactivation.", "CPIC-A Preferred Guideline", "clopidogrel"),
        ("cad", "Prasugrel (Effient 10mg)", "green", "Esterase / CYP3A4", "🟢 Favorable Response", "Favorable. Efficient bioactivation without reliance on CYP2C19; overcomes clopidogrel genetic resistance.", "CPIC-A Level 1", "clopidogrel"),
        ("cad", "Aspirin (Ecosprin 75mg)", "green", "COX-1", "🟢 Favorable Response", "Favorable frontline antiplatelet without actionable high-risk germline metabolic variation.", "GPS Level 1", "clopidogrel"),
        ("cad", "Metoprolol (Betaloc 50mg)", "yellow", "CYP2D6", "🟡 Caution / Dose Adjustment", "Caution: CYP2D6 poor metabolizers experience 3–5x higher drug concentration with risk of marked bradycardia.", "FDA PGx Label", "metformin"),
        ("cad", "Warfarin (Coumadin 5mg)", "yellow", "CYP2C9 / VKORC1", "🟡 Caution / Genotype Guided", "Caution: Variants cause dramatic sensitivity; requires algorithmic genotype-guided initial dose reduction to prevent bleeding.", "CPIC-A / FDA Boxed Warning", "clopidogrel"),
        ("cad", "Clopidogrel (Plavix 75mg)", "red", "CYP2C19 (*2, *3 alleles)", "🔴 High Risk / Black Box Warning", "BLACK BOX WARNING: CYP2C19 loss-of-function allele carriers cannot convert prodrug to active form. Severe risk of stent thrombosis and death.", "CPIC-A Level 1 / FDA Black Box / GPS Level 1", "clopidogrel"),

        ("hyperlipidemia", "Rosuvastatin (Crestor 10mg / Rosuvas)", "green", "Minimal SLCO1B1 dependency", "🟢 Favorable Response", "Favorable. Much lower reliance on SLCO1B1 transporter; significantly lower risk of myopathy / rhabdomyolysis.", "CPIC-A Preferred Choice", "simvastatin"),
        ("hyperlipidemia", "Pravastatin (Pravachol 20mg)", "green", "Hydrophilic Statin", "🟢 Favorable Response", "Favorable. Hydrophilic statin profile with minimal systemic muscle tissue penetration.", "CPIC Guideline", "simvastatin"),
        ("hyperlipidemia", "Atorvastatin (Lipitor 20mg / Atorva)", "yellow", "SLCO1B1", "🟡 Caution / Moderate Risk", "Caution: At doses >=40mg in SLCO1B1 521C carriers, plasma concentrations rise, raising mild myalgia incidence.", "CPIC-A / FDA PGx Label", "simvastatin"),
        ("hyperlipidemia", "Simvastatin (Zocor 40mg / Simvotin)", "red", "SLCO1B1 (521T>C variant)", "🔴 High Risk / Muscle Toxicity", "HIGH RISK: SLCO1B1 c.521T>C carriers have impaired hepatic uptake, causing 200% higher systemic drug exposure and severe rhabdomyolysis / muscle tear.", "CPIC-A Level 1 / FDA Boxed Label", "simvastatin"),

        ("pain", "Paracetamol / Acetaminophen (Dolo 650)", "green", "Minimal Germline PGx", "🟢 Favorable Response", "Favorable first-line analgesic. Safe standard non-opioid without major germline metabolic variations.", "Standard Formulary / GPS", "dolo"),
        ("pain", "Celecoxib (Celebrex 100mg)", "yellow", "CYP2C9", "🟡 Caution / Dose Adjustment", "Caution: CYP2C9 poor metabolizers accumulate 2x higher plasma levels; initiate treatment at 50% lowest dose.", "FDA PGx Label", "dolo"),
        ("pain", "Tramadol (Ultram 50mg)", "yellow", "CYP2D6", "🟡 Caution / Altered Response", "Caution: Variable prodrug conversion into active analgesic M1 metabolite; watch for poor analgesia or toxicity.", "CPIC-A", "dolo"),
        ("pain", "Codeine (Tylenol #3 / 30mg)", "red", "CYP2D6 (*1xN, *2xN alleles)", "🔴 High Risk / Fatal Toxicity", "HIGH RISK / FATAL ARREST: Ultra-rapid metabolizers rapidly convert codeine to toxic morphine surges, causing fatal respiratory depression. Poor metabolizers gain 0% pain relief.", "CPIC-A Level 1 / FDA Boxed Warning", "dolo"),

        ("depression", "Sertraline (Zoloft 50mg / Daxid)", "green", "CYP2C19", "🟢 Favorable Response", "Favorable profile. Broader therapeutic index with lower vulnerability to CYP2C19 polymorphic variation.", "CPIC Guideline", "cetirizine"),
        ("depression", "Escitalopram / Citalopram (Nexito 10mg)", "yellow", "CYP2C19", "🟡 Caution / Dose Cap", "Caution: Poor metabolizers accumulate high drug concentrations with elevated QTc cardiac prolongation risk. Max 20mg/day.", "CPIC-A / FDA Label", "cetirizine"),
        ("depression", "Amitriptyline (Elavil 25mg)", "red", "CYP2D6 & CYP2C19", "🔴 High Risk / Toxic Levels", "High Risk: Dual metabolic pathway; poor metabolizers risk toxic cardiac arrhythmias and severe anticholinergic toxicity. Titrate by 50%.", "CPIC-A Level 1", "cetirizine")
    ]

    cursor.executemany("""
    INSERT INTO disease_drugs (disease_id, name, status, gene, status_label, guidance, evidence, med_key)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, disease_drugs)

    # 5. Pharmacies
    pharmacies = [
        ("green-cross", "Green Cross Pharmacy", "Retail Chemist & Druggist", "12, MG Road, Bengaluru Central", "+91 80 4000 1101", 12.9754, 77.6080, "08:00", "23:00", "8:00 AM – 11:00 PM", 0, 4.8, 320),
        ("city-care", "City Care Medicals & Surgical", "Retail Chemist", "48, Residency Road, Bengaluru Central", "+91 80 4000 1102", 12.9712, 77.6015, "07:30", "23:30", "7:30 AM – 11:30 PM", 0, 4.7, 198),
        ("st-marys", "St. Mary’s Hospital 24/7 Pharmacy", "Hospital Pharmacy", "21, Richmond Town, Bengaluru Central", "+91 80 4000 1103", 12.9644, 77.6033, "00:00", "23:59", "Open 24 Hours (Night Emergency)", 1, 4.9, 840),
        ("wellness-ulsoor", "Wellness Pharmacy", "Chain Pharmacy", "5, Ulsoor Road, Bengaluru", "+91 80 4000 1104", 12.9782, 77.6200, "08:30", "22:00", "8:30 AM – 10:00 PM", 0, 4.6, 142),
        ("apollo-lavelle", "Apollo Pharmacy 24/7", "Chain Pharmacy", "77, Lavelle Road, Bengaluru", "+91 80 4000 1105", 12.9698, 77.5992, "00:00", "23:59", "Open 24 Hours", 1, 4.8, 512),
        ("medplus-infantry", "MedPlus Pharmacy", "Chain Pharmacy", "31, Infantry Road, Bengaluru", "+91 80 4000 1106", 12.9811, 77.6050, "08:00", "22:30", "8:00 AM – 10:30 PM", 0, 4.5, 230)
    ]

    cursor.executemany("""
    INSERT INTO pharmacies (id, name, type, address, phone, lat, lng, open_time, close_time, hours_label, is_24_hours, rating, reviews_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, pharmacies)

    # 6. Pharmacy Inventory
    inventory = [
        # Green Cross Pharmacy
        ("green-cross", "pantoprazole", "available", 30, 150.0, "Rack B-4"),
        ("green-cross", "clopidogrel", "available", 14, 165.0, "Rack D-1"),
        ("green-cross", "simvastatin", "available", 20, 135.0, "Rack D-3"),
        ("green-cross", "augmentin", "available", 24, 182.0, "Rack A-2"),
        ("green-cross", "dolo", "available", 65, 34.0, "Counter Front"),
        ("green-cross", "metformin", "available", 18, 48.0, "Rack B-1"),
        ("green-cross", "cetirizine", "limited", 3, 22.0, "Rack C-3"),
        ("green-cross", "azithromycin", "available", 15, 120.0, "Rack A-4"),

        # City Care
        ("city-care", "pantoprazole", "available", 12, 152.0, "Shelf 2"),
        ("city-care", "clopidogrel", "available", 8, 162.0, "Shelf 5"),
        ("city-care", "simvastatin", "limited", 3, 130.0, "Shelf 5"),
        ("city-care", "augmentin", "limited", 2, 180.0, "Shelf 3"),
        ("city-care", "dolo", "available", 45, 33.0, "Shelf 1"),
        ("city-care", "metformin", "available", 22, 46.0, "Shelf 4"),
        ("city-care", "cetirizine", "available", 35, 20.0, "Shelf 2"),
        ("city-care", "azithromycin", "unavailable", 0, 122.0, "Shelf 3"),

        # St Marys
        ("st-marys", "pantoprazole", "limited", 4, 155.0, "Dispensary Central"),
        ("st-marys", "clopidogrel", "available", 35, 165.0, "Dispensary Central"),
        ("st-marys", "simvastatin", "available", 25, 138.0, "Dispensary Central"),
        ("st-marys", "augmentin", "available", 80, 185.0, "Dispensary Central"),
        ("st-marys", "dolo", "available", 120, 34.0, "Dispensary Central"),
        ("st-marys", "metformin", "unavailable", 0, 48.0, "Dispensary Central"),
        ("st-marys", "cetirizine", "available", 50, 22.0, "Dispensary Central"),
        ("st-marys", "azithromycin", "available", 40, 124.0, "Dispensary Central"),

        # Wellness
        ("wellness-ulsoor", "pantoprazole", "available", 28, 148.0, "Section 5"),
        ("wellness-ulsoor", "clopidogrel", "unavailable", 0, 160.0, "Section 6"),
        ("wellness-ulsoor", "simvastatin", "available", 15, 132.0, "Section 6"),
        ("wellness-ulsoor", "augmentin", "unavailable", 0, 180.0, "Section 1"),
        ("wellness-ulsoor", "dolo", "available", 50, 33.0, "Section 2"),
        ("wellness-ulsoor", "metformin", "limited", 4, 47.0, "Section 4"),
        ("wellness-ulsoor", "cetirizine", "available", 25, 21.0, "Section 3"),
        ("wellness-ulsoor", "azithromycin", "available", 18, 125.0, "Section 1"),

        # Apollo
        ("apollo-lavelle", "pantoprazole", "available", 40, 154.0, "Apollo G-1"),
        ("apollo-lavelle", "clopidogrel", "available", 22, 168.0, "Apollo C-1"),
        ("apollo-lavelle", "simvastatin", "available", 18, 136.0, "Apollo C-4"),
        ("apollo-lavelle", "augmentin", "available", 45, 184.0, "Apollo A-1"),
        ("apollo-lavelle", "dolo", "available", 90, 34.0, "Apollo OTC"),
        ("apollo-lavelle", "metformin", "available", 35, 48.0, "Apollo D-1"),
        ("apollo-lavelle", "cetirizine", "unavailable", 0, 22.0, "Apollo C-2"),
        ("apollo-lavelle", "azithromycin", "limited", 3, 126.0, "Apollo A-3"),

        # MedPlus
        ("medplus-infantry", "pantoprazole", "limited", 2, 150.0, "Aisle 5"),
        ("medplus-infantry", "clopidogrel", "limited", 3, 162.0, "Aisle 6"),
        ("medplus-infantry", "simvastatin", "available", 10, 130.0, "Aisle 6"),
        ("medplus-infantry", "augmentin", "available", 16, 179.0, "Aisle 2"),
        ("medplus-infantry", "dolo", "available", 40, 33.0, "Front Rack"),
        ("medplus-infantry", "metformin", "available", 20, 46.0, "Aisle 4"),
        ("medplus-infantry", "cetirizine", "available", 18, 20.0, "Aisle 3"),
        ("medplus-infantry", "azithromycin", "available", 12, 120.0, "Aisle 2")
    ]

    now = datetime.now().isoformat()
    cursor.executemany("""
    INSERT INTO pharmacy_inventory (pharmacy_id, medicine_id, status, units, price, rack, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, '""" + now + """')
    """, inventory)

    # 7. Initial Customer Hold Reservations
    holds = [
        ("HLD-9102", "green-cross", "Leela Sharma", "+91 98450 12345", "pantoprazole", "Pan 40 (Pantoprazole 40mg)", 1, 150.0, "Within 15 minutes", "ready", now),
        ("HLD-9104", "green-cross", "Dr. Arvind Rao", "+91 97412 88990", "clopidogrel", "Plavix 75mg (Clopidogrel)", 2, 330.0, "Within 30 minutes", "pending", now)
    ]

    cursor.executemany("""
    INSERT INTO hold_reservations (id, store_id, patient_name, phone, medicine_id, medicine_name, quantity, total_price, eta, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, holds)

    # 8. Demand Alerts
    alerts = [
        ("Augmentin 625 Duo", 48, "last 2 hours", "safe", "Stock Good (24 units)"),
        ("Cetirizine 10mg", 32, "last 2 hours", "warning", "Only 3 left in stock"),
        ("Budecort Inhaler 200", 29, "last 2 hours", "danger", "Out of stock! Restock advised.")
    ]

    cursor.executemany("""
    INSERT INTO demand_alerts (medicine_name, searches, time_window, status, stock_note)
    VALUES (?, ?, ?, ?, ?)
    """, alerts)


def seed_users(cursor):
    """Seed demonstration accounts for Patient, Pharmacist, and Admin roles."""
    now = datetime.now().isoformat()
    default_users = [
        (
            "usr-patient-1",
            "patient@mednear.org",
            generate_password_hash("Password123!", method="pbkdf2:sha256"),
            "Priya Sharma",
            "+91 98450 12345",
            "patient",
            None,
            now
        ),
        (
            "usr-pharm-1",
            "pharmacist@greencross.com",
            generate_password_hash("Password123!", method="pbkdf2:sha256"),
            "Rajesh Kumar (Green Cross)",
            "+91 80 4000 1101",
            "pharmacist",
            "green-cross",
            now
        ),
        (
            "usr-pharm-2",
            "pharmacist@apollo.com",
            generate_password_hash("Password123!", method="pbkdf2:sha256"),
            "Suresh Nair (Apollo Lead)",
            "+91 80 4000 1105",
            "pharmacist",
            "apollo-lavelle",
            now
        ),
        (
            "usr-admin-1",
            "admin@mednear.org",
            generate_password_hash("AdminPassword123!", method="pbkdf2:sha256"),
            "Dr. Leela (Medical Admin)",
            "+91 80 5555 0000",
            "admin",
            None,
            now
        )
    ]
    cursor.executemany("""
    INSERT INTO users (id, email, password_hash, name, phone, role, pharmacy_id, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, default_users)


def get_user_by_email(email):
    """Retrieve user dictionary by case-insensitive email."""
    if not email:
        return None
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Retrieve user dictionary by ID."""
    if not user_id:
        return None
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(user_id, email, password, name, role="patient", phone=None, pharmacy_id=None):
    """Create a new user with secure password hash."""
    conn = get_db_connection()
    hashed = generate_password_hash(password, method="pbkdf2:sha256")
    now = datetime.now().isoformat()
    conn.execute("""
    INSERT INTO users (id, email, password_hash, name, phone, role, pharmacy_id, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, email.strip().lower(), hashed, name.strip(), phone, role, pharmacy_id, now))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)


def get_all_users():
    """Retrieve all users without password hashes for admin view."""
    conn = get_db_connection()
    rows = conn.execute("SELECT id, email, name, phone, role, pharmacy_id, created_at FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user(user_id, name=None, phone=None):
    """Update user profile info (name, phone)."""
    conn = get_db_connection()
    if name is not None and phone is not None:
        conn.execute("UPDATE users SET name = ?, phone = ? WHERE id = ?", (name.strip(), phone.strip(), user_id))
    elif name is not None:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name.strip(), user_id))
    elif phone is not None:
        conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone.strip(), user_id))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)


if __name__ == "__main__":
    init_db()
    print("MedNear Database initialized successfully at:", DB_PATH)
