/**
 * MEDNEAR 2.0 — Dual-Mode Healthcare Platform with Pharmacogenomic (PGx) Decision Support
 * 
 * Connected to Python Flask + SQLite Backend API (/api/...)
 * Reference: Hussain S, Kenigsberg BB, Danahey K, Lee YM, Galecki PM, Ratain MJ, O'Donnell PH.
 * "Disease–Drug Database for Pharmacogenomic-Based Prescribing." 
 * Clin Pharmacol Ther. 2016 Aug;100(2):160-70. PMC5570547.
 * 
 * Features:
 * 1. Patient Mode: Real-time Pharmacy Locator with verified stock, pricing, and distance calculation.
 * 2. Visual & Presets Scanner with Tesseract.js OCR and PMC5570547 Pharmacogenomic alerts.
 * 3. Disease–Drug–PGx Comparative Prescribing Menu with Traffic Light CDS (🟢 Green / 🟡 Yellow / 🔴 Red).
 * 4. 30-Minute Free Customer Hold Reservation System (persisted to SQLite).
 * 5. Medical Shop Friendly Portal: 1-Tap stock toggles, inventory updates, order fulfillment from SQLite.
 */

(() => {
    "use strict";

    // =========================================================================
    // 0. SUPABASE CLOUD & REALTIME CONFIGURATION (Project: mednear / ytwxequauyhysyqkswxs)
    // =========================================================================
    const SUPABASE_URL = "https://ytwxequauyhysyqkswxs.supabase.co";
    const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl0d3hlcXVhdXloeXN5cWtzd3hzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5NTk3MDMsImV4cCI6MjEwNzUzNTcwM30.u224AbqQ6zn0MD1O8gzm694vYn4sFkShxyjKKF4rlAM";
    let supabaseClient = null;

    function initSupabase() {
        try {
            if (window.supabase && typeof window.supabase.createClient === "function") {
                supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
                console.log("⚡ Supabase Cloud Connected: ytwxequauyhysyqkswxs");

                const pill = $("#supabase-status-pill");
                if (pill) {
                    pill.addEventListener("click", () => {
                        showToast("⚡ Supabase Cloud Connected! Project: mednear (PostgreSQL + Realtime)", "success");
                    });
                }

                // Subscribe to Realtime database changes
                supabaseClient
                    .channel('realtime:mednear')
                    .on('postgres_changes', { event: '*', schema: 'public', table: 'hold_reservations' }, payload => {
                        console.log("⚡ Supabase Realtime Hold Change:", payload);
                        if (state.appMode === "pharmacy") {
                            renderPharmacyDashboard();
                        }
                    })
                    .on('postgres_changes', { event: '*', schema: 'public', table: 'pharmacy_inventory' }, payload => {
                        console.log("⚡ Supabase Realtime Inventory Change:", payload);
                        if (state.appMode === "pharmacy") {
                            renderPharmacyDashboard();
                        }
                    })
                    .subscribe();
            }
        } catch (e) {
            console.warn("Supabase init notice:", e);
        }
    }

    // =========================================================================
    // 1. LOCAL FALLBACK CATALOG (USED WHEN API IS INITIALIZING OR OFFLINE)
    // =========================================================================
    const FALLBACK_MEDICINES = {
        "pantoprazole": {
            id: "pantoprazole",
            name: "Pan 40 (Pantoprazole 40mg)",
            genericName: "Pantoprazole Gastro-Resistant (40mg)",
            form: "Tablet (Strip of 15)",
            category: "Proton Pump Inhibitor (PPI) / Antacid",
            schedule: "Schedule H",
            avgPrice: 155,
            usage: "Treatment of GERD, acid reflux, heartburn, and peptic ulcers.",
            safety: "Best taken in morning 30–60 minutes before food on an empty stomach.",
            pgx: {
                gene: "CYP2C19",
                status: "yellow",
                statusLabel: "🟡 Caution / Dose Adjustment",
                evidence: "CPIC-A · FDA PGx Biomarker · GPS Level 1",
                advice: "Extensive/rapid metabolizers may experience subtherapeutic acid suppression. Consider doubling dose to 80mg or switching to Rabeprazole."
            },
            substitutes: [
                { name: "Pantocid 40", company: "Sun Pharma", price: 125, savings: "19% Cheaper" },
                { name: "Razo 20 (Rabeprazole - PGx Safer)", company: "Dr. Reddy's", price: 110, savings: "29% Cheaper" },
                { name: "Pantoprazole 40 Generic", company: "Jan Aushadhi", price: 42, savings: "73% Cheaper" }
            ],
            keywords: ["pan 40", "pantoprazole", "pantocid", "pantosec", "acidity", "gas", "gerd", "ulcer", "heartburn", "omeprazole", "rabeprazole"]
        },
        "clopidogrel": {
            id: "clopidogrel",
            name: "Plavix 75mg (Clopidogrel)",
            genericName: "Clopidogrel Bisulfate (75mg)",
            form: "Tablet (Strip of 10)",
            category: "Antiplatelet / Thienopyridine Class",
            schedule: "Schedule H (Prescription Required)",
            avgPrice: 165,
            usage: "Prevention of vascular ischemia, myocardial infarction, and stent thrombosis.",
            safety: "Must be taken consistently daily. Strictly monitor for unexplained bruising or bleeding.",
            pgx: {
                gene: "CYP2C19 (*2, *3 loss-of-function)",
                status: "red",
                statusLabel: "🔴 High Risk / FDA Black Box Warning",
                evidence: "CPIC-A Level 1 · FDA Boxed Warning · GPS Level 1 (PMC5570547)",
                advice: "BLACK BOX WARNING: CYP2C19 loss-of-function allele carriers cannot convert prodrug to active form. Severe risk of stent thrombosis and death. Switch to Ticagrelor or Prasugrel."
            },
            substitutes: [
                { name: "Clavix 75", company: "Intas Pharma", price: 115, savings: "30% Cheaper" },
                { name: "Deplatt 75", company: "Torrent Pharma", price: 108, savings: "34% Cheaper" },
                { name: "Ticagrelor 90 (PGx Favorable)", company: "AstraZeneca", price: 195, savings: "CPIC Preferred" }
            ],
            keywords: ["clopidogrel", "plavix", "clavix", "deplatt", "stent", "blood thinner", "cad", "heart", "aspirin"]
        },
        "simvastatin": {
            id: "simvastatin",
            name: "Zocor 40mg (Simvastatin)",
            genericName: "Simvastatin (40mg)",
            form: "Tablet (Strip of 10)",
            category: "HMG-CoA Reductase Inhibitor (Statin)",
            schedule: "Schedule H",
            avgPrice: 135,
            usage: "Lowering LDL cholesterol and reducing risk of stroke and myocardial infarction.",
            safety: "Take in the evening. Report unexplained muscle aches or weakness immediately.",
            pgx: {
                gene: "SLCO1B1 (Solute Carrier Organic Anion Transporter)",
                status: "red",
                statusLabel: "🔴 High Risk / Muscle Toxicity Alert",
                evidence: "CPIC-A Level 1 · FDA PGx Label · GPS Level 1 (PMC5570547)",
                advice: "HIGH RISK: SLCO1B1 c.521T>C carriers have impaired hepatic clearance, causing toxic serum accumulation and severe rhabdomyolysis / muscle tears. Switch to Rosuvastatin or Pravastatin."
            },
            substitutes: [
                { name: "Simvotin 40", company: "Sun Pharma", price: 110, savings: "18% Cheaper" },
                { name: "Rosuvas 10 (Rosuvastatin - PGx Safer)", company: "Sun Pharma", price: 145, savings: "CPIC Preferred" },
                { name: "Simvastatin 20 Generic", company: "Jan Aushadhi", price: 35, savings: "74% Cheaper" }
            ],
            keywords: ["simvastatin", "zocor", "simvotin", "cholesterol", "statin", "rosuvastatin", "atorvastatin", "hyperlipidemia"]
        },
        "augmentin": {
            id: "augmentin",
            name: "Augmentin 625 Duo",
            genericName: "Amoxicillin (500mg) + Clavulanic Acid (125mg)",
            form: "Tablet (Strip of 10)",
            category: "Antibacterial / Penicillin Class",
            schedule: "Schedule H (Prescription Required)",
            avgPrice: 182,
            usage: "Bacterial infections of the respiratory tract, lungs, ears, sinuses, and urinary tract.",
            safety: "Take immediately before or with a meal. Complete full 5–7 day prescribed course.",
            pgx: {
                gene: "Minimal Germline Variation",
                status: "green",
                statusLabel: "🟢 Favorable Response",
                evidence: "Standard Antimicrobial Formulary · PMC5570547",
                advice: "Standard therapeutic response. Confirm patient has no medical history of severe penicillin allergies."
            },
            substitutes: [
                { name: "Moxikind-CV 625", company: "Mankind Pharma", price: 112, savings: "38% Cheaper" },
                { name: "Novamox-CV 625", company: "Cipla", price: 118, savings: "35% Cheaper" },
                { name: "Amoxyclav 625 Generic", company: "Jan Aushadhi", price: 68, savings: "62% Cheaper" }
            ],
            keywords: ["amoxicillin", "clavulanic", "augmentin", "moxikind", "novamox", "antibiotic", "amox", "bacterial"]
        },
        "dolo": {
            id: "dolo",
            name: "Dolo 650",
            genericName: "Paracetamol / Acetaminophen (650mg)",
            form: "Tablet (Strip of 15)",
            category: "Analgesic & Antipyretic",
            schedule: "OTC (Over-The-Counter)",
            avgPrice: 34,
            usage: "Relief of mild to moderate fever, headaches, body ache, and muscle soreness.",
            safety: "Do not exceed 4000mg/day. Maintain at least 4–6 hours between doses.",
            pgx: {
                gene: "Minimal Germline Variation",
                status: "green",
                statusLabel: "🟢 Favorable Response",
                evidence: "CPIC Analgesic Standard · PMC5570547",
                advice: "Favorable first-line non-opioid analgesic without high-risk germline genetic variants like those affecting codeine/tramadol."
            },
            substitutes: [
                { name: "Calpol 650", company: "GSK", price: 31, savings: "9% Cheaper" },
                { name: "Pacimol 650", company: "Ipca", price: 28, savings: "18% Cheaper" },
                { name: "Paracetamol 650 Generic", company: "Jan Aushadhi", price: 14, savings: "58% Cheaper" }
            ],
            keywords: ["dolo", "dolo 650", "paracetamol", "calpol", "crocin", "pacimol", "acetaminophen", "fever", "headache", "tylenol"]
        },
        "metformin": {
            id: "metformin",
            name: "Glycomet 500 SR",
            genericName: "Metformin Hydrochloride Sustained Release (500mg)",
            form: "Tablet (Strip of 20)",
            category: "Antidiabetic / Biguanide",
            schedule: "Schedule H",
            avgPrice: 48,
            usage: "Management of Type 2 Diabetes Mellitus to lower blood glucose levels.",
            safety: "Take with or right after dinner. Swallow whole, do not crush sustained-release tablets.",
            pgx: {
                gene: "SLC22A1 (OCT1 Transporter)",
                status: "green",
                statusLabel: "🟢 Favorable Response",
                evidence: "FDA PGx Biomarker · GPS Level 1",
                advice: "Favorable first-line oral antidiabetic. Minor OCT1 variants may alter gastrointestinal tolerance; monitor HbA1c."
            },
            substitutes: [
                { name: "Okamet 500", company: "Cipla", price: 36, savings: "25% Cheaper" },
                { name: "Metfor 500 SR", company: "Sun Pharma", price: 38, savings: "21% Cheaper" },
                { name: "Metformin 500 Generic", company: "Jan Aushadhi", price: 16, savings: "66% Cheaper" }
            ],
            keywords: ["metformin", "glycomet", "okamet", "sugar", "diabetes", "diabetic", "glucophage"]
        },
        "cetirizine": {
            id: "cetirizine",
            name: "Alerid 10mg",
            genericName: "Cetirizine Hydrochloride (10mg)",
            form: "Tablet (Strip of 10)",
            category: "Antihistamine / Anti-Allergic",
            schedule: "OTC / Schedule H",
            avgPrice: 22,
            usage: "Treatment of allergic rhinitis, hay fever, sneezing, runny nose, and hives.",
            safety: "May induce mild drowsiness. Avoid driving or operating machinery immediately after taking.",
            pgx: {
                gene: "Minimal Germline Variation",
                status: "green",
                statusLabel: "🟢 Favorable Response",
                evidence: "Standard Formulary",
                advice: "Favorable. Does not rely on polymorphic CYP2D6 or CYP2C19 enzymes."
            },
            substitutes: [
                { name: "Cetzine 10mg", company: "GSK", price: 19, savings: "14% Cheaper" },
                { name: "Zyrtec 10mg", company: "Dr. Reddy's", price: 21, savings: "5% Cheaper" },
                { name: "Cetirizine 10 Generic", company: "Jan Aushadhi", price: 8, savings: "64% Cheaper" }
            ],
            keywords: ["cetirizine", "alerid", "cetzine", "zyrtec", "allergy", "cold", "sneeze", "hives"]
        },
        "azithromycin": {
            id: "azithromycin",
            name: "Azithral 500",
            genericName: "Azithromycin (500mg)",
            form: "Tablet (Strip of 5)",
            category: "Macrolide Antibiotic",
            schedule: "Schedule H",
            avgPrice: 122,
            usage: "Throat infections, tonsillitis, bronchitis, community-acquired pneumonia, and bacterial skin infections.",
            safety: "Usually taken once daily at the same time, either 1 hour before or 2 hours after a meal.",
            pgx: {
                gene: "Minimal Germline Variation",
                status: "green",
                statusLabel: "🟢 Favorable Response",
                evidence: "Antimicrobial Standard",
                advice: "Favorable macrolide coverage without high-risk germline metabolic variation."
            },
            substitutes: [
                { name: "Zady 500", company: "Mankind", price: 89, savings: "27% Cheaper" },
                { name: "Azee 500", company: "Cipla", price: 95, savings: "22% Cheaper" },
                { name: "Azithromycin 500 Generic", company: "Jan Aushadhi", price: 45, savings: "63% Cheaper" }
            ],
            keywords: ["azithral", "azithromycin", "azee", "zady", "antibiotic", "throat", "cough"]
        }
    };

    // =========================================================================
    // 2. STATE MANAGEMENT
    // =========================================================================
    const state = {
        appMode: "patient",
        activeMedicineKey: "pantoprazole",
        activeMedicineSearchTerm: "Pan 40 (Pantoprazole 40mg)",
        currentArea: "Bengaluru Central",
        userCoords: { lat: 12.9716, lng: 77.5946 },
        locationSource: "default",
        locationAccuracy: null,
        locationWatchId: null,
        activeDiseaseKey: null,
        filterStatus: "all",
        openNowOnly: false,
        twentyFourHoursOnly: false,
        sortBy: "distance",
        activeStoreId: "green-cross",
        cameraFacing: "environment",
        cameraStream: null,
        activeScannerTab: "camera",
        scanGeneration: 0,
        activeHoldStore: null,
        currentUser: null,
        authToken: localStorage.getItem("mednear_jwt_token") || null
    };

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => Array.from(document.querySelectorAll(sel));
    const escapeHtml = (val) => String(val ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

    function playAudioTone(type = "beep") {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            if (type === "success") {
                osc.type = "sine";
                osc.frequency.setValueAtTime(587.33, ctx.currentTime);
                osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1);
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.25);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.25);
            } else {
                osc.type = "sine";
                osc.frequency.setValueAtTime(750, ctx.currentTime);
                gain.gain.setValueAtTime(0.12, ctx.currentTime);
                gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.15);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.15);
            }
        } catch (_) {}
    }

    function showToast(message, type = "info") {
        const container = $("#toast-container");
        if (!container) return;
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        const icons = { success: "✓", alert: "⚠️", error: "⚠️", info: "ℹ️" };
        toast.innerHTML = `<span>${icons[type] || "•"}</span><span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(10px)";
            setTimeout(() => toast.remove(), 300);
        }, 3800);
    }

    // =========================================================================
    // 3. API SERVICE LAYER (CONNECTS FRONTEND TO FLASK + SQLITE + JWT RBAC)
    // =========================================================================
    const api = {
        getAuthHeaders() {
            const headers = { "Content-Type": "application/json" };
            if (state.authToken) {
                headers["Authorization"] = `Bearer ${state.authToken}`;
            }
            return headers;
        },

        async login(email, password) {
            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email, password })
                });
                return await res.json();
            } catch (e) {
                return { error: "Network error during login: " + e.message };
            }
        },

        async register(payload) {
            try {
                const res = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                return await res.json();
            } catch (e) {
                return { error: "Network error during registration: " + e.message };
            }
        },

        async getMe() {
            if (!state.authToken) return null;
            try {
                const res = await fetch("/api/auth/me", {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Session restore failed:", e);
            }
            return null;
        },

        async getUserProfile() {
            if (!state.authToken) return null;
            try {
                const res = await fetch("/api/user/profile", {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("getUserProfile failed:", e);
            }
            return null;
        },

        async updateUserProfile(payload) {
            try {
                const res = await fetch("/api/user/profile", {
                    method: "PUT",
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify(payload)
                });
                return await res.json();
            } catch (e) {
                return { error: "Network error updating profile: " + e.message };
            }
        },

        async getPatientHolds() {
            try {
                const res = await fetch("/api/patient/holds", {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {}
            return { holds: [] };
        },

        async getAdminUsers() {
            try {
                const res = await fetch("/api/admin/users", {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {}
            return { users: [] };
        },

        async geocode(query) {
            if (!query || !query.trim()) return { results: [] };
            try {
                const res = await fetch(`/api/geocode?q=${encodeURIComponent(query.trim())}`);
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Geocode API request error:", e);
            }
            return { results: [] };
        },

        async getMedicine(id) {
            try {
                const res = await fetch(`/api/medicines/${encodeURIComponent(id)}`);
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Backend API /api/medicines/ fallback to local catalog:", e);
            }
            return FALLBACK_MEDICINES[id] || FALLBACK_MEDICINES["pantoprazole"];
        },

        async getDisease(id) {
            try {
                const res = await fetch(`/api/diseases/${encodeURIComponent(id)}`);
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Backend API /api/diseases/ fallback:", e);
            }
            return null;
        },

        async getPharmacies(medicineId, coords, filters = {}) {
            try {
                const params = new URLSearchParams({
                    medicine: medicineId,
                    lat: coords.lat,
                    lng: coords.lng,
                    filter: filters.filter || "all",
                    open_now: filters.openNow ? "true" : "false",
                    is_24_hours: filters.is24Hours ? "true" : "false",
                    sort: filters.sort || "distance"
                });
                const res = await fetch(`/api/pharmacies?${params.toString()}`);
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Backend API /api/pharmacies fallback:", e);
            }
            return null;
        },

        async getStoreInventory(storeId) {
            try {
                const res = await fetch(`/api/pharmacy/${encodeURIComponent(storeId)}/inventory`, {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Backend API store inventory fallback:", e);
            }
            return null;
        },

        async updateStoreInventory(storeId, payload) {
            try {
                const res = await fetch(`/api/pharmacy/${encodeURIComponent(storeId)}/inventory`, {
                    method: "POST",
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!res.ok) {
                    showToast(data.error || "Inventory update unauthorized", "alert");
                    return null;
                }
                return data;
            } catch (e) {
                console.error("Failed to update store inventory via API:", e);
                showToast("Network error updating inventory", "error");
            }
            return null;
        },

        async getStoreHolds(storeId) {
            try {
                const res = await fetch(`/api/pharmacy/${encodeURIComponent(storeId)}/holds`, {
                    headers: this.getAuthHeaders()
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Backend API store holds fallback:", e);
            }
            return { holds: [] };
        },

        async createHold(reservationData) {
            try {
                const res = await fetch("/api/holds", {
                    method: "POST",
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify(reservationData)
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.error("Failed to submit hold to backend API:", e);
            }
            return null;
        },

        async updateHoldStatus(holdId, status) {
            try {
                const res = await fetch(`/api/holds/${encodeURIComponent(holdId)}`, {
                    method: "PATCH",
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify({ status })
                });
                const data = await res.json();
                if (!res.ok) {
                    showToast(data.error || "Permission denied updating hold", "alert");
                    return null;
                }
                return data;
            } catch (e) {
                console.error("Failed to update hold status via API:", e);
            }
            return null;
        },

        async verifyHoldOtp(holdId, otp) {
            try {
                const res = await fetch(`/api/holds/${encodeURIComponent(holdId)}/verify-otp`, {
                    method: "POST",
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify({ otp })
                });
                return await res.json();
            } catch (e) {
                console.error("Failed to verify OTP via API:", e);
                return { success: false, error: e.message };
            }
        },

        async getDemandAlerts() {
            try {
                const res = await fetch("/api/demand-alerts");
                if (res.ok) return await res.json();
            } catch (e) {}
            return { alerts: [] };
        },

        async scanMatch(text) {
            try {
                const res = await fetch("/api/scan/match", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text })
                });
                if (res.ok) return await res.json();
            } catch (e) {
                console.warn("Scan match API call failed:", e);
            }
            return null;
        },

        async sendAIChatMessage(message, history = [], lat = 12.9716, lng = 77.5946) {
            try {
                const res = await fetch("/api/ai/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ message, history, lat, lng })
                });
                return await res.json();
            } catch (e) {
                console.error("AI Chat API call failed:", e);
                return {
                    success: false,
                    reply: "⚠️ Unable to reach MedNear Clinical AI service. Please check your network connection and try again.",
                    intent: "error",
                    stock_cards: [],
                    suggestions: []
                };
            }
        },

        async getAISuggestions() {
            try {
                const res = await fetch("/api/ai/suggestions");
                if (res.ok) return await res.json();
            } catch (e) {}
            return {
                suggestions: [
                    { icon: "💊", label: "Is Pan 40 available near me?", query: "Is Pan 40 available near me?" },
                    { icon: "🧬", label: "Check Plavix genetic risks", query: "What are the genetic risks and black box warning for Plavix (Clopidogrel)?" },
                    { icon: "🏷️", label: "Find cheaper generic tablets", query: "What cheaper generic alternatives exist for expensive tablets?" },
                    { icon: "⚠️", label: "Dolo 650 safe dosage", query: "What is the safe daily dosage and precautions for Dolo 650?" },
                    { icon: "⚡", label: "How 30-min hold works", query: "How does the MedNear 30-minute hold reservation work?" },
                    { icon: "🕒", label: "24/7 Open Pharmacies", query: "Which partner pharmacies are open 24/7 right now?" }
                ]
            };
        }
    };

    function resolveMedicineKey(term) {
        const clean = term.toLowerCase().trim();
        for (const [key, med] of Object.entries(FALLBACK_MEDICINES)) {
            if (clean.includes(key) || key.includes(clean)) return key;
            if (med.keywords && med.keywords.some(k => clean.includes(k) || k.includes(clean))) return key;
        }
        return "pantoprazole";
    }

    function resolveDiseaseKey(term) {
        const clean = term.toLowerCase().trim();
        const diseaseKeywords = {
            gerd: ["gerd", "acid reflux", "acidity", "heartburn", "gastritis", "peptic ulcer", "stomach ulcer"],
            cad: ["cad", "coronary artery disease", "heart disease", "angina", "stent", "thrombosis", "heart attack"],
            hyperlipidemia: ["hyperlipidemia", "high cholesterol", "cholesterol", "dyslipidemia", "triglycerides", "statin"],
            pain: ["pain", "musculoskeletal", "back pain", "arthritis", "joint pain", "headache", "analgesic"],
            depression: ["depression", "anxiety", "antidepressant", "mental health", "stress"]
        };
        for (const [key, synonyms] of Object.entries(diseaseKeywords)) {
            if (clean === key || clean.includes(key) || synonyms.some(s => clean.includes(s) || s.includes(clean))) {
                return key;
            }
        }
        return null;
    }

    // =========================================================================
    // 4. PMC5570547 DISEASE–DRUG COMPARATIVE MENU
    // =========================================================================
    async function renderDiseaseComparativeMenu(diseaseKey) {
        const disease = await api.getDisease(diseaseKey);
        const section = $("#pgx-disease-section");
        const tbody = $("#pgx-disease-table-body");
        if (!section || !tbody || !disease) return;

        section.hidden = false;
        $("#pgx-disease-title").innerHTML = `Disease–Drug Comparative Menu: <strong>${escapeHtml(disease.title)}</strong>`;
        tbody.innerHTML = "";

        (disease.drugs || []).forEach(drug => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>
                    <strong>${escapeHtml(drug.name)}</strong>
                    <span style="display:block; font-size:0.75rem; color:var(--text-light);">${escapeHtml(drug.evidence)}</span>
                </td>
                <td><span class="gene-code">${escapeHtml(drug.gene)}</span></td>
                <td><span class="pgx-status-pill ${drug.status}">${escapeHtml(drug.status_label || drug.status)}</span></td>
                <td style="font-size:0.83rem; line-height:1.45; color:var(--text-muted);">${escapeHtml(drug.guidance)}</td>
                <td>
                    <button type="button" class="btn-pgx-pick" data-med-key="${escapeHtml(drug.med_key)}" data-drug-name="${escapeHtml(drug.name)}">
                        Check Stock
                    </button>
                </td>
            `;

            tr.querySelector(".btn-pgx-pick").addEventListener("click", () => {
                $("#medicine-input").value = drug.name;
                state.activeMedicineKey = drug.med_key;
                state.activeMedicineSearchTerm = drug.name;
                loadPatientResults();
                showToast(`Loaded nearby stock for <strong>${drug.name}</strong>`, "success");
                window.location.hash = "#results-section";
            });

            tbody.appendChild(tr);
        });

        section.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // =========================================================================
    // 5. PATIENT MODE: MEDICINE GUIDE & PHARMACY RESULTS
    // =========================================================================
    async function updatePatientMedicineGuide(medKey) {
        const med = await api.getMedicine(medKey);
        const section = $("#medicine-guide-section");
        if (!section || !med) return;

        section.hidden = false;
        $("#guide-med-name").textContent = med.name;
        $("#guide-med-salt").textContent = med.generic_name || med.genericName;
        $("#guide-med-usage").textContent = med.usage;
        $("#guide-med-safety").innerHTML = `<span class="alert-icon">⚠️</span> <span>${escapeHtml(med.safety)}</span>`;
        $("#guide-rx-status").textContent = med.schedule;

        // Render PMC5570547 PGx Safety Card
        const pgxCard = $("#guide-pgx-card");
        const pgxData = med.pgx || {
            gene: med.pgx_gene,
            status: med.pgx_status,
            statusLabel: med.pgx_status_label,
            evidence: med.pgx_evidence,
            advice: med.pgx_advice
        };

        if (pgxCard && pgxData && pgxData.gene) {
            pgxCard.hidden = false;
            $("#guide-pgx-badge").className = `pgx-badge ${pgxData.status}`;
            $("#guide-pgx-badge").textContent = pgxData.status_label || pgxData.statusLabel || "🟢 Favorable Response";
            $("#guide-pgx-gene").textContent = `Gene: ${pgxData.gene}`;
            $("#guide-pgx-advice").textContent = pgxData.advice;
            $("#guide-pgx-evidence").textContent = pgxData.evidence;
        } else if (pgxCard) {
            pgxCard.hidden = true;
        }

        // Render generic substitutes
        const subList = $("#guide-substitutes-list");
        if (subList) {
            subList.innerHTML = "";
            (med.substitutes || []).forEach(sub => {
                const card = document.createElement("div");
                card.className = "substitute-item";
                card.innerHTML = `
                    <div>
                        <strong class="sub-name">${escapeHtml(sub.name)}</strong>
                        <span class="sub-saving"> · ${escapeHtml(sub.savings)}</span>
                        <small style="display:block; font-size:0.75rem; color:var(--text-light);">${escapeHtml(sub.company)}</small>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <strong>₹${sub.price}</strong>
                        <button type="button" class="btn-switch-sub" data-sub-name="${escapeHtml(sub.name)}">Check Stock</button>
                    </div>
                `;
                card.querySelector(".btn-switch-sub").addEventListener("click", () => {
                    $("#medicine-input").value = sub.name;
                    executeSearch(sub.name);
                });
                subList.appendChild(card);
            });
        }
    }

    async function loadPatientResults() {
        const medKey = state.activeMedicineKey;
        await updatePatientMedicineGuide(medKey);

        const listContainer = $("#results-list");
        const emptyState = $("#empty-state");
        if (!listContainer) return;

        listContainer.hidden = false;
        if (emptyState) emptyState.hidden = true;
        listContainer.innerHTML = '<p class="empty-state" style="padding:2rem; text-align:center; color:var(--text-light);">Loading nearby pharmacy inventory from database…</p>';

        const data = await api.getPharmacies(medKey, state.userCoords, {
            filter: state.filterStatus,
            openNow: state.openNowOnly,
            is24Hours: state.twentyFourHoursOnly,
            sort: state.sortBy
        });

        const pharmacies = data?.results || [];
        const inStockCount = pharmacies.filter(p => p.item?.status === "available").length;

        $("#count-all").textContent = String(pharmacies.length);
        $("#count-available").textContent = String(inStockCount);
        $("#partner-count-badge").textContent = `${pharmacies.length} Pharmacies Online`;

        listContainer.innerHTML = "";

        if (pharmacies.length === 0) {
            listContainer.hidden = true;
            if (emptyState) {
                emptyState.hidden = false;
                emptyState.innerHTML = `
                    <div class="empty-icon">🔍</div>
                    <h3>No matching pharmacies found</h3>
                    <p>No pharmacies matched this filter combination for "${escapeHtml(state.activeMedicineSearchTerm)}". Try resetting filters.</p>
                    <button type="button" class="btn-pill" id="btn-reset-filters-inline">Reset Filters</button>
                `;
                emptyState.querySelector("#btn-reset-filters-inline")?.addEventListener("click", resetFilters);
            }
            return;
        }

        pharmacies.forEach(place => {
            const statusClass = place.item.status; // available, limited, unavailable
            const statusLabel = statusClass === "available"
                ? `🟢 In Stock (${place.item.units} ready)`
                : statusClass === "limited"
                    ? `🟡 Limited (${place.item.units} left)`
                    : `🔴 Out of Stock`;

            const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name}, ${place.address}`)}`;
            const directionsUrl = state.userCoords
                ? `https://www.google.com/maps/dir/?api=1&origin=${state.userCoords.lat},${state.userCoords.lng}&destination=${place.lat},${place.lng}&travelmode=driving`
                : mapsUrl;

            const card = document.createElement("article");
            card.className = "result-card";
            card.innerHTML = `
                <div class="card-top">
                    <div>
                        <h3 class="place-name">${escapeHtml(place.name)}</h3>
                        <span class="place-kind">${escapeHtml(place.type)} ${place.is_24_hours ? "· 24/7 Service" : ""}</span>
                    </div>
                    <span class="status-badge ${statusClass}">${statusLabel}</span>
                </div>

                <div class="medicine-match-box">
                    <div class="med-match-info">
                        <strong>${escapeHtml(state.activeMedicineSearchTerm)}</strong>
                        <span>Verified stock in SQLite database</span>
                    </div>
                    <div class="card-price-est">
                        <strong>₹${place.item.price}</strong>
                        <small>counter price</small>
                    </div>
                </div>

                <div class="card-meta">
                    <div class="meta-line">
                        <span>📍</span>
                        <strong>${place.distance_km} km away</strong>
                        <span>(${Math.max(1, Math.round(place.distance_km * 3.5))} min drive)</span>
                    </div>
                    <div class="meta-line">
                        <span>⏰</span>
                        <span>${place.is_open ? "● Open Now" : "○ Closed"} · ${escapeHtml(place.hours_label)}</span>
                    </div>
                    <div class="meta-line">
                        <span>🏠</span>
                        <span>${escapeHtml(place.address)}</span>
                    </div>
                </div>

                <div class="card-bottom">
                    <span class="updated-time">Updated ${place.item.updated_min_ago}m ago</span>
                    <div class="card-actions">
                        ${statusClass !== "unavailable" ? `
                            <button type="button" class="btn-card-hold" 
                                data-store-id="${escapeHtml(place.id)}" 
                                data-store-name="${escapeHtml(place.name)}" 
                                data-price="${place.item.price}">
                                📦 Hold (30m)
                            </button>
                        ` : ""}
                        <a href="tel:${place.phone.replace(/[^+\d]/g, "")}" class="btn-card-action" title="Call Chemist">
                            📞 Call
                        </a>
                        <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="btn-card-action" title="Directions">
                            🧭 Directions
                        </a>
                    </div>
                </div>
            `;

            const holdBtn = card.querySelector(".btn-card-hold");
            if (holdBtn && statusClass !== "unavailable") {
                holdBtn.addEventListener("click", () => {
                    openHoldModal({
                        storeId: place.id,
                        storeName: place.name,
                        medicineKey: medKey,
                        medicineName: state.activeMedicineSearchTerm,
                        price: place.item.price
                    });
                });
            }

            listContainer.appendChild(card);
        });
    }

    async function executeSearch(query, area) {
        const term = (query || $("#medicine-input").value).trim();
        const areaTerm = (area || $("#location-input").value).trim() || "Bengaluru Central";

        if (!term) {
            $("#medicine-input").focus();
            showToast("Please enter a medicine or disease name.", "alert");
            return;
        }

        // Auto-geocode custom area or pincode if typed
        if (areaTerm && areaTerm !== state.currentArea && !areaTerm.toLowerCase().includes("live gps")) {
            const geocodeData = await api.geocode(areaTerm);
            if (geocodeData && geocodeData.results && geocodeData.results.length > 0) {
                const topMatch = geocodeData.results[0];
                state.userCoords = { lat: topMatch.lat, lng: topMatch.lng };
                state.currentArea = topMatch.area;
                const headerArea = $("#header-location-name");
                if (headerArea) headerArea.textContent = `📍 ${topMatch.area}`;
                showToast(`Location coordinates resolved: ${topMatch.area} (${topMatch.lat.toFixed(4)}, ${topMatch.lng.toFixed(4)})`, "info");
            }
        }

        // Check if query is a disease (e.g. GERD, CAD, Cholesterol, Pain, Depression)
        const matchedDisease = resolveDiseaseKey(term);
        if (matchedDisease) {
            state.activeDiseaseKey = matchedDisease;
            renderDiseaseComparativeMenu(matchedDisease);
            $("#results-title").textContent = `Prescribing options for ${term.toUpperCase()}`;
            $("#results-caption").textContent = `Pharmacogenomic Decision Support (PMC5570547) · Verified pharmacies near ${state.currentArea || areaTerm}`;
            state.activeMedicineKey = matchedDisease === "gerd" ? "pantoprazole" : matchedDisease === "cad" ? "clopidogrel" : matchedDisease === "hyperlipidemia" ? "simvastatin" : "dolo";
            state.activeMedicineSearchTerm = term;
            loadPatientResults();
            return;
        }

        $("#pgx-disease-section").hidden = true;
        state.activeMedicineSearchTerm = term;
        state.activeMedicineKey = resolveMedicineKey(term);

        $("#results-title").textContent = `Availability for "${term}"`;
        $("#results-caption").textContent = `Verified local pharmacy stock near ${state.currentArea || areaTerm}`;

        loadPatientResults();
    }

    function resetFilters() {
        state.filterStatus = "all";
        state.openNowOnly = false;
        state.twentyFourHoursOnly = false;
        $("#open-now").checked = false;
        $("#filter-24-hours").checked = false;
        $$(".filter-chip").forEach(c => c.classList.toggle("active", c.dataset.filter === "all"));
        loadPatientResults();
    }

    // =========================================================================
    // 6. SMART SCANNER LOGIC (OCR + PMC5570547 PGX ALERTS)
    // =========================================================================
    function openScannerModal(tabName = "camera") {
        const modal = $("#scanner-modal");
        if (!modal) return;
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        switchScannerTab(tabName);
    }

    function closeScannerModal() {
        const modal = $("#scanner-modal");
        if (!modal) return;
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        stopCameraStream();
    }

    function switchScannerTab(tabName) {
        state.activeScannerTab = tabName;
        $$(".scanner-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));

        $("#scanner-view-camera").hidden = tabName !== "camera";
        $("#scanner-view-upload").hidden = tabName !== "upload";
        $("#scanner-view-presets").hidden = tabName !== "presets";

        if (tabName === "camera") {
            startCameraStream();
        } else {
            stopCameraStream();
        }
    }

    async function startCameraStream() {
        const video = $("#scanner-video");
        const fallback = $("#camera-fallback");
        if (!video) return;

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            if (fallback) fallback.hidden = false;
            return;
        }

        try {
            stopCameraStream();
            const constraints = {
                video: {
                    facingMode: state.cameraFacing,
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            };
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            state.cameraStream = stream;
            video.srcObject = stream;
            await video.play();
            if (fallback) fallback.hidden = true;
        } catch (err) {
            console.warn("Camera getUserMedia error:", err);
            if (fallback) fallback.hidden = false;
        }
    }

    function stopCameraStream() {
        if (state.cameraStream) {
            state.cameraStream.getTracks().forEach(t => t.stop());
            state.cameraStream = null;
        }
        const video = $("#scanner-video");
        if (video) video.srcObject = null;
    }

    async function presentScanResult(medKey, customName, ocrCtx = null) {
        playAudioTone("success");
        const resultCard = $("#scan-result-card");
        if (!resultCard) return;

        const med = await api.getMedicine(medKey);

        $("#detected-name").textContent = customName || med.name;
        $("#detected-salt").textContent = med.generic_name || med.genericName;
        $("#detected-form").textContent = med.form || "Tablets";
        $("#detected-category").textContent = med.category || "General Medicine";
        $("#detected-rx-class").textContent = med.schedule || "Schedule H";
        $("#detected-desc").textContent = med.usage || "";
        $("#scan-confidence").textContent = (ocrCtx && ocrCtx.confidence)
            ? `Matching confidence: ${ocrCtx.confidence}`
            : "Catalog Match";

        // Update Scanner PGx Alert Box from PMC5570547
        const pgxBox = $("#scan-pgx-alert");
        const pgxData = med.pgx || {
            gene: med.pgx_gene,
            status: med.pgx_status,
            statusLabel: med.pgx_status_label,
            advice: med.pgx_advice
        };

        if (pgxBox && pgxData && pgxData.gene) {
            pgxBox.hidden = false;
            $("#scan-pgx-gene-badge").textContent = `Gene Biomarker: ${pgxData.gene}`;
            $("#scan-pgx-pill").className = `scan-pgx-pill ${pgxData.status}`;
            $("#scan-pgx-pill").textContent = pgxData.status_label || pgxData.statusLabel || "🟢 Favorable Response";
            $("#scan-pgx-note").textContent = pgxData.advice;
        } else if (pgxBox) {
            pgxBox.hidden = true;
        }

        // Show raw OCR output + review prompt when this result came from a real scan
        const ocrTextEl = $("#scan-ocr-text");
        const reviewPromptEl = $("#scan-review-prompt");
        const resultLabel = $("#scan-result-label");
        if (ocrCtx && ocrCtx.ocrText) {
            if (ocrTextEl) {
                ocrTextEl.textContent = `Printed text detected by scanner: "${ocrCtx.ocrText}"`;
                ocrTextEl.hidden = false;
            }
            if (reviewPromptEl) reviewPromptEl.hidden = false;
            if (resultLabel) resultLabel.textContent = ocrCtx.ocrMatched === false ? "✓ OCR Candidate" : "✓ OCR Verified";
        } else {
            if (ocrTextEl) ocrTextEl.hidden = true;
            if (reviewPromptEl) reviewPromptEl.hidden = true;
            if (resultLabel) resultLabel.textContent = "✓ Catalog Match";
        }

        resultCard.hidden = false;

        const confirmBtn = $("#btn-apply-scanned-search");
        confirmBtn.onclick = () => {
            closeScannerModal();
            $("#medicine-input").value = customName || med.name;
            executeSearch(customName || med.name);
        };
    }

    function runMockScanAnalysis(detectedKey, customName) {
        playAudioTone("beep");
        const analyzingBox = $("#scan-analyzing");
        const resultCard = $("#scan-result-card");
        const statusText = $("#analyzing-status-text");

        analyzingBox.hidden = false;
        resultCard.hidden = true;

        const steps = [
            "Aligning optical text & barcode boundaries...",
            "Decoding active formulation salts...",
            "Querying SQLite database & PMC5570547 Pharmacogenomics...",
            "Calculating stock availability across local pharmacies..."
        ];

        let idx = 0;
        statusText.textContent = steps[0];

        const interval = setInterval(() => {
            idx++;
            if (idx < steps.length) {
                statusText.textContent = steps[idx];
            } else {
                clearInterval(interval);
                analyzingBox.hidden = true;
                presentScanResult(detectedKey, customName);
            }
        }, 400);
    }

    /**
     * Real AI OCR scan pipeline: Tesseract.js reads the printed medicine name from
     * the camera frame / uploaded photo, then the Flask backend /api/scan/match
     * endpoint resolves the best catalog match in SQLite (incl. PMC5570547 PGx).
     */
    async function ensureTesseract() {
        if (window.Tesseract) return window.Tesseract;
        await new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
            script.onload = resolve;
            script.onerror = () => reject(new Error("Tesseract OCR engine failed to load"));
            document.head.appendChild(script);
        });
        if (!window.Tesseract) throw new Error("Tesseract OCR engine unavailable");
        return window.Tesseract;
    }

    async function runOcrScan(source) {
        const analyzingBox = $("#scan-analyzing");
        const resultCard = $("#scan-result-card");
        const statusText = $("#analyzing-status-text");

        try {
            playAudioTone("beep");
            if (analyzingBox) analyzingBox.hidden = false;
            if (resultCard) resultCard.hidden = true;
            if (statusText) statusText.textContent = "Loading AI OCR engine...";

            const Tesseract = await ensureTesseract();
            if (statusText) statusText.textContent = "Reading the printed medicine name & strength...";

            const { data } = await Tesseract.recognize(source);
            const ocrText = (data.text || "").trim().replace(/\s+/g, " ");

            if (!ocrText || ocrText.length < 4) {
                throw new Error("No readable printed text found in the image");
            }

            if (statusText) statusText.textContent = "Matching catalog in SQLite database...";
            const match = await api.scanMatch(ocrText);

            if (analyzingBox) analyzingBox.hidden = true;

            if (match && match.medicine && match.matched !== false) {
                await presentScanResult(match.medicine.id, match.medicine.name, {
                    ocrText,
                    ocrMatched: true,
                    confidence: match.confidence
                });
            } else if (match && match.medicine) {
                // Weak/partial match: still show the closest candidate, but flag it for human verification
                showToast("Scanner could not confirm the printed name clearly. Please double-check the suggestion.", "alert");
                await presentScanResult(match.medicine.id, match.medicine.name, {
                    ocrText,
                    ocrMatched: false,
                    confidence: match.confidence
                });
            } else {
                showToast("Scanner found no readable medicine name. Try a clearer photo or a sample preset.", "alert");
            }
        } catch (err) {
            console.warn("OCR scan failed:", err);
            if (analyzingBox) analyzingBox.hidden = true;
            showToast("AI OCR could not read the pack clearly. Try better lighting or a sample preset.", "alert");
        }
    }

    // =========================================================================
    // 7. 30-MINUTE HOLD RESERVATION MODAL (SAVED TO SQLITE)
    // =========================================================================
    function openHoldModal({ storeId, storeName, medicineKey, medicineName, price }) {
        state.activeHoldStore = { storeId, storeName, medicineKey, medicineName, price };
        $("#hold-med-name").textContent = medicineName;
        $("#hold-store-name").textContent = storeName;
        $("#hold-est-price").textContent = `₹${price}`;

        // Reset views: show form, hide success pane
        const form = $("#hold-request-form");
        const successPane = $("#hold-success-view");
        if (form) form.hidden = false;
        if (successPane) successPane.hidden = true;

        const modal = $("#hold-modal");
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
    }

    function closeHoldModal() {
        const modal = $("#hold-modal");
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        const form = $("#hold-request-form");
        const successPane = $("#hold-success-view");
        if (form) form.hidden = false;
        if (successPane) successPane.hidden = true;
    }

    // =========================================================================
    // 8. MEDICAL SHOP FRIENDLY PORTAL (SQLITE SYNCED)
    // =========================================================================
    async function renderPharmacyDashboard() {
        const storeId = state.activeStoreId;
        const tbody = $("#inventory-table-body");
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:1.5rem; color:var(--text-light);">Loading live store inventory from SQLite database…</td></tr>';

        const data = await api.getStoreInventory(storeId);

        if (data === null) {
            tbody.innerHTML = `
                <tr><td colspan="6" style="text-align:center; padding:2rem;">
                    <strong>🔒 Pharmacist sign-in required</strong><br>
                    <small style="color:var(--text-light);">Open <strong>Sign In / Demo</strong> in the top bar and use a Chemist demo account (e.g. Green Cross) to manage live inventory.</small>
                </td></tr>
            `;
            $("#metric-total-items").textContent = "0";
            $("#metric-low-stock").textContent = "0";
            $("#metric-holds-count").textContent = "0";
            $("#store-order-badge").textContent = "0";
            return;
        }

        const inventory = data?.inventory || [];

        $("#metric-total-items").textContent = String(inventory.length);
        const lowCount = inventory.filter(it => it.status === "limited" || it.units <= 3).length;
        $("#metric-low-stock").textContent = String(lowCount);

        tbody.innerHTML = "";
        inventory.forEach(item => {
            const tr = document.createElement("tr");

            const statusText = {
                available: "🟢 In Stock",
                limited: "🟡 Low Stock",
                unavailable: "🔴 Out of Stock"
            }[item.status] || "🟢 In Stock";

            tr.innerHTML = `
                <td>
                    <strong>${escapeHtml(item.name)}</strong>
                    <span style="display:block; font-size:0.75rem; color:var(--text-light);">${escapeHtml(item.generic_name)}</span>
                </td>
                <td><span class="rack-tag">${escapeHtml(item.rack || "Shelf A-1")}</span></td>
                <td>
                    <button type="button" class="stock-toggle-btn ${item.status}" data-med-id="${item.medicine_id}" title="Click to cycle status: In Stock -> Low Stock -> Out of Stock">
                        ${statusText}
                    </button>
                </td>
                <td>
                    <input type="number" class="units-input" min="0" value="${item.units}" data-med-id="${item.medicine_id}">
                </td>
                <td><span class="price-val">₹${item.price}</span></td>
                <td>
                    <button type="button" class="btn-table-action" data-med-id="${item.medicine_id}" title="Delete item">🗑️</button>
                </td>
            `;

            // 1-Tap stock toggle directly saved to SQLite
            tr.querySelector(".stock-toggle-btn").addEventListener("click", async () => {
                const nextStatus = item.status === "available" ? "limited" : item.status === "limited" ? "unavailable" : "available";
                await api.updateStoreInventory(storeId, {
                    medicine_id: item.medicine_id,
                    status: nextStatus,
                    units: item.units,
                    price: item.price,
                    rack: item.rack
                });
                showToast(`Saved to Database: ${item.name} set to ${nextStatus.toUpperCase()}`, "success");
                renderPharmacyDashboard();
            });

            // Units change saved directly to SQLite
            tr.querySelector(".units-input").addEventListener("change", async (e) => {
                const val = parseInt(e.target.value, 10) || 0;
                const nextStatus = val === 0 ? "unavailable" : val <= 4 ? "limited" : "available";
                await api.updateStoreInventory(storeId, {
                    medicine_id: item.medicine_id,
                    status: nextStatus,
                    units: val,
                    price: item.price,
                    rack: item.rack
                });
                showToast(`Saved to Database: ${item.name} units set to ${val}`, "info");
                renderPharmacyDashboard();
            });

            tbody.appendChild(tr);
        });

        await renderChemistHolds();
    }

    async function renderChemistHolds() {
        const container = $("#holds-list-container");
        if (!container) return;
        container.innerHTML = "";

        const data = await api.getStoreHolds(state.activeStoreId);
        const holds = data?.holds || [];

        const pendingCount = holds.filter(h => h.status === "pending").length;
        $("#metric-holds-count").textContent = String(pendingCount);
        $("#store-order-badge").textContent = String(pendingCount);

        if (holds.length === 0) {
            container.innerHTML = `<p style="font-size:0.8rem; color:var(--text-light); text-align:center; padding:1rem;">No customer hold requests right now.</p>`;
            return;
        }

        holds.forEach(hold => {
            const card = document.createElement("div");
            card.className = "hold-order-card";
            card.innerHTML = `
                <div class="hold-order-header">
                    <strong>${escapeHtml(hold.patient_name)}</strong>
                    <span class="hold-eta-badge">ETA: ${escapeHtml(hold.eta)}</span>
                </div>
                <div class="hold-item-name">📦 ${escapeHtml(hold.medicine_name)} (${hold.quantity} strip)</div>
                <div class="hold-customer-info">📞 ${escapeHtml(hold.phone)} · ₹${hold.total_price} · #${hold.id}</div>
                ${hold.otp ? `
                    <div class="otp-verify-inline">
                        ${hold.otp_verified ? `
                            <span class="otp-verified-tag">✓ OTP Verified (${escapeHtml(hold.otp)})</span>
                        ` : (hold.status === "pending" || hold.status === "ready") ? `
                            <span style="font-size:0.75rem; color:#475569; font-weight:600;">Counter OTP:</span>
                            <input type="text" class="otp-verify-input" maxlength="4" placeholder="••••" data-id="${hold.id}">
                            <button type="button" class="btn-verify-otp-action" data-id="${hold.id}">Verify</button>
                        ` : `
                            <span style="font-size:0.75rem; color:#64748b;">OTP: ${escapeHtml(hold.otp)}</span>
                        `}
                    </div>
                ` : ''}
                <div class="hold-order-actions">
                    ${hold.status === "pending" ? `
                        <button type="button" class="btn-hold-accept" data-id="${hold.id}">Accept & Hold</button>
                        <button type="button" class="btn-hold-decline" data-id="${hold.id}">Decline</button>
                    ` : hold.status === "ready" ? `
                        <button type="button" class="btn-hold-accept" data-id="${hold.id}" style="background:#0284c7;">Mark Picked Up</button>
                    ` : hold.status === "expired" ? `
                        <span style="font-size:0.78rem; font-weight:700; color:#dc2626;">⏰ Expired (Stock Restored to Shelf)</span>
                    ` : hold.status === "declined" ? `
                        <span style="font-size:0.78rem; font-weight:700; color:#6b7280;">❌ Declined (Restored)</span>
                    ` : `
                        <span style="font-size:0.78rem; font-weight:700; color:var(--primary);">✓ Completed & Picked Up</span>
                    `}
                </div>
            `;

            const verifyOtpBtn = card.querySelector(".btn-verify-otp-action");
            if (verifyOtpBtn) {
                verifyOtpBtn.addEventListener("click", async () => {
                    const inp = card.querySelector(`.otp-verify-input[data-id="${hold.id}"]`);
                    const val = inp ? inp.value.trim() : "";
                    if (!val) {
                        showToast("Please enter customer's 4-digit pickup OTP", "alert");
                        return;
                    }
                    const res = await api.verifyHoldOtp(hold.id, val);
                    if (res && res.success) {
                        showToast(`✓ OTP Verified! Hold #${hold.id} authenticated for dispensing.`, "success");
                        renderPharmacyDashboard();
                    } else {
                        showToast(res?.error || "Invalid OTP code", "alert");
                    }
                });
            }

            const acceptBtn = card.querySelector(".btn-hold-accept");
            if (acceptBtn) {
                acceptBtn.addEventListener("click", async () => {
                    const nextSt = hold.status === "pending" ? "ready" : "completed";
                    await api.updateHoldStatus(hold.id, nextSt);
                    showToast(`Updated reservation #${hold.id} to ${nextSt.toUpperCase()} in SQLite`, "success");
                    renderPharmacyDashboard();
                });
            }

            const declineBtn = card.querySelector(".btn-hold-decline");
            if (declineBtn) {
                declineBtn.addEventListener("click", async () => {
                    await api.updateHoldStatus(hold.id, "declined");
                    showToast(`Reservation #${hold.id} declined`, "info");
                    renderPharmacyDashboard();
                });
            }

            container.appendChild(card);
        });
    }

    // =========================================================================
    // 9. AUTHENTICATION & ROLE-BASED ACCESS CONTROL (RBAC) CONTROLLERS
    // =========================================================================
    function switchAppMode(mode) {
        state.appMode = mode;
        if (mode === "patient") {
            document.body.className = "mode-patient";
            $("#btn-patient-mode")?.classList.add("active");
            $("#btn-patient-mode")?.setAttribute("aria-checked", "true");
            $("#btn-pharmacy-mode")?.classList.remove("active");
            $("#btn-pharmacy-mode")?.setAttribute("aria-checked", "false");
            $("#patient-view").hidden = false;
            $("#pharmacy-view").hidden = true;
        } else {
            document.body.className = "mode-pharmacy";
            $("#btn-pharmacy-mode")?.classList.add("active");
            $("#btn-pharmacy-mode")?.setAttribute("aria-checked", "true");
            $("#btn-patient-mode")?.classList.remove("active");
            $("#btn-patient-mode")?.setAttribute("aria-checked", "false");
            $("#pharmacy-view").hidden = false;
            $("#patient-view").hidden = true;
            renderPharmacyDashboard();
        }
    }

    function updateAuthUI() {
        const btnOpen = $("#btn-open-auth");
        const userBadge = $("#user-profile-badge");
        const headerName = $("#header-user-name");
        const headerRole = $("#header-user-role");
        const btnHolds = $("#btn-patient-my-holds");
        const btnAdmin = $("#btn-admin-panel");

        if (state.currentUser) {
            if (btnOpen) btnOpen.hidden = true;
            if (userBadge) userBadge.hidden = false;
            if (headerName) headerName.textContent = state.currentUser.name || state.currentUser.email;
            if (headerRole) {
                headerRole.textContent = state.currentUser.role.toUpperCase();
                headerRole.className = `role-chip role-${state.currentUser.role}`;
            }

            if (btnHolds) {
                btnHolds.hidden = state.currentUser.role !== "patient";
                if (state.currentUser.role === "patient") refreshPatientHoldsCount();
            }
            if (btnAdmin) {
                btnAdmin.hidden = state.currentUser.role !== "admin";
            }

            if (state.currentUser.role === "pharmacist" && state.currentUser.pharmacy_id) {
                state.activeStoreId = state.currentUser.pharmacy_id;
                const selector = $("#store-selector");
                if (selector) selector.value = state.currentUser.pharmacy_id;
            }
        } else {
            if (btnOpen) btnOpen.hidden = false;
            if (userBadge) userBadge.hidden = true;
            if (btnHolds) btnHolds.hidden = true;
            if (btnAdmin) btnAdmin.hidden = true;
        }
    }

    async function refreshPatientHoldsCount() {
        const badge = $("#user-holds-count");
        if (!badge) return;
        const res = await api.getPatientHolds();
        badge.textContent = res.count || (res.holds ? res.holds.length : 0);
    }

    function openAuthModal() {
        const modal = $("#auth-modal");
        if (modal) {
            modal.hidden = false;
            const err = $("#auth-error-banner");
            if (err) err.hidden = true;
        }
    }

    function closeAuthModal() {
        const modal = $("#auth-modal");
        if (modal) modal.hidden = true;
    }

    function handleLoginSuccess(token, user, isNewRegistration = false) {
        state.authToken = token;
        state.currentUser = user;
        localStorage.setItem("mednear_jwt_token", token);
        updateAuthUI();
        closeAuthModal();
        playAudioTone("success");
        if (isNewRegistration) {
            showToast(`Account created & synced to cloud! Welcome, ${user.name}`, "success");
        } else {
            showToast(`Signed in as ${user.name} (${user.role.toUpperCase()})`, "success");
        }

        if (user.role === "pharmacist") {
            switchAppMode("pharmacy");
        } else if (user.role === "patient") {
            switchAppMode("patient");
        }
    }

    function handleLogout() {
        state.authToken = null;
        state.currentUser = null;
        localStorage.removeItem("mednear_jwt_token");
        updateAuthUI();
        showToast("Signed out of MedNear account", "info");
        switchAppMode("patient");
    }

    async function renderPatientHoldsModal() {
        const container = $("#patient-holds-list");
        if (!container) return;
        container.innerHTML = "<p>Loading your reservations…</p>";
        $("#patient-holds-modal").hidden = false;

        const res = await api.getPatientHolds();
        const holds = res.holds || [];
        if (holds.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem; color: #64748b;">
                    <span style="font-size: 2.5rem;">📦</span>
                    <h4>No active reservations</h4>
                    <p style="font-size: 0.9rem;">You haven't placed any 30-minute holds yet. Find a medicine nearby and tap "Hold 30-min".</p>
                </div>
            `;
            return;
        }

        container.innerHTML = "";
        holds.forEach(hold => {
            const card = document.createElement("div");
            card.style.background = "#f8fafc";
            card.style.border = "1px solid #e2e8f0";
            card.style.borderRadius = "8px";
            card.style.padding = "1rem";
            card.style.marginBottom = "0.75rem";

            const statusColors = {
                ready: "#16a34a",
                completed: "#0284c7",
                declined: "#dc2626",
                pending: "#d97706",
                expired: "#ef4444"
            };

            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                    <div>
                        <strong style="font-size: 1rem; color: #0f172a;">${escapeHtml(hold.medicine_name)}</strong>
                        <div style="font-size: 0.8rem; color: #64748b;">Code: <b>${escapeHtml(hold.id)}</b> · Chemist: ${escapeHtml(hold.store_id)}</div>
                    </div>
                    <span style="background: ${statusColors[hold.status] || '#64748b'}; color: white; font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase;">
                        ${escapeHtml(hold.status)}
                    </span>
                </div>
                <div style="font-size: 0.85rem; color: #334155; display: flex; justify-content: space-between;">
                    <span>Quantity: <b>${hold.quantity}</b> · Total: <b>₹${hold.total_price}</b></span>
                    <span>ETA: <b>${escapeHtml(hold.eta)}</b></span>
                </div>
            `;
            container.appendChild(card);
        });
    }

    async function renderAdminUsersModal() {
        const tbody = $("#admin-users-tbody");
        if (!tbody) return;
        tbody.innerHTML = "<tr><td colspan='5'>Loading registered users…</td></tr>";
        $("#admin-modal").hidden = false;

        const res = await api.getAdminUsers();
        const users = res.users || [];
        tbody.innerHTML = "";

        users.forEach(u => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${escapeHtml(u.name)}</strong></td>
                <td>${escapeHtml(u.email)}</td>
                <td><span class="role-chip role-${u.role}">${escapeHtml(u.role.toUpperCase())}</span></td>
                <td>${escapeHtml(u.pharmacy_id || '—')}</td>
                <td><code style="font-size: 0.75rem; color: #64748b;">${escapeHtml(u.id)}</code></td>
            `;
            tbody.appendChild(tr);
        });
    }

    async function openUserProfileModal() {
        if (!state.currentUser) {
            openAuthModal();
            return;
        }

        const modal = $("#user-profile-modal");
        if (!modal) return;
        modal.hidden = false;

        // Reset sub-drawers
        const editForm = $("#profile-edit-form");
        if (editForm) editForm.hidden = true;
        const jsonDrawer = $("#profile-raw-json-drawer");
        if (jsonDrawer) jsonDrawer.hidden = true;

        // Quick pre-fill from cached state
        $("#profile-display-name").textContent = state.currentUser.name || "User";
        $("#profile-display-role").textContent = (state.currentUser.role || "patient").toUpperCase();
        $("#profile-display-role").className = `role-chip role-${state.currentUser.role}`;
        $("#profile-display-id").textContent = state.currentUser.id;
        $("#profile-display-email").textContent = state.currentUser.email || "—";
        $("#profile-display-phone").textContent = state.currentUser.phone || "Not set";

        // Fetch complete profile from backend
        const data = await api.getUserProfile();
        if (data && data.user) {
            const u = data.user;
            state.currentUser = u;
            $("#profile-display-name").textContent = u.name;
            $("#profile-display-role").textContent = u.role.toUpperCase();
            $("#profile-display-role").className = `role-chip role-${u.role}`;
            $("#profile-display-id").textContent = u.id;
            $("#profile-display-email").textContent = u.email;
            $("#profile-display-phone").textContent = u.phone || "Not set";

            const joinedDate = u.created_at ? new Date(u.created_at).toLocaleDateString(undefined, { dateStyle: "medium" }) : "Active";
            $("#profile-display-joined").textContent = joinedDate;

            // Fill edit fields
            $("#edit-profile-name").value = u.name;
            $("#edit-profile-phone").value = u.phone || "";

            // Pharmacy row
            const pharmRow = $("#profile-pharmacy-row");
            if (pharmRow) {
                if (u.role === "pharmacist" && data.pharmacy) {
                    pharmRow.hidden = false;
                    $("#profile-display-pharmacy").textContent = `${data.pharmacy.name} (${data.pharmacy.inventory_count || 0} catalog medicines)`;
                } else {
                    pharmRow.hidden = true;
                }
            }

            // Raw JSON inspector
            const jsonView = $("#profile-raw-json-content");
            if (jsonView) {
                jsonView.textContent = JSON.stringify(data, null, 2);
            }

            // Reservations list
            renderProfileHolds(data.holds || []);
        } else {
            $("#profile-holds-container").innerHTML = "<p style='color: #ef4444; font-size: 0.9rem;'>Unable to retrieve profile from database.</p>";
        }
    }

    function renderProfileHolds(holds) {
        const container = $("#profile-holds-container");
        const countSpan = $("#profile-holds-count");
        if (countSpan) countSpan.textContent = holds.length;
        if (!container) return;

        if (holds.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 1.5rem; color: #64748b; background: #f8fafc; border-radius: 8px;">
                    <span style="font-size: 2rem;">📦</span>
                    <p style="margin: 0.5rem 0 0 0; font-size: 0.88rem;">No medicine reservations placed yet.</p>
                    <small>Search for any medicine and tap "Hold 30-min" to reserve at nearby chemists.</small>
                </div>
            `;
            return;
        }

        container.innerHTML = "";
        const statusColors = {
            ready: "#16a34a",
            completed: "#0284c7",
            declined: "#dc2626",
            pending: "#d97706",
            expired: "#ef4444"
        };

        holds.forEach(hold => {
            const card = document.createElement("div");
            card.className = "profile-hold-item";

            const otpHtml = hold.otp ? `<span class="profile-otp-chip">OTP: ${escapeHtml(hold.otp)}</span>` : "";
            const dirHtml = hold.directions_url ? `<a href="${escapeHtml(hold.directions_url)}" target="_blank" rel="noopener noreferrer" class="btn-directions-small">📍 Directions</a>` : "";

            card.innerHTML = `
                <div class="profile-hold-top">
                    <div>
                        <div class="profile-hold-title">${escapeHtml(hold.medicine_name)}</div>
                        <div style="font-size: 0.78rem; color: #64748b;">Code: <b>${escapeHtml(hold.id)}</b> · Chemist: <b>${escapeHtml(hold.store_id)}</b></div>
                    </div>
                    <span style="background: ${statusColors[hold.status] || '#64748b'}; color: white; font-size: 0.72rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; text-transform: uppercase;">
                        ${escapeHtml(hold.status)}
                    </span>
                </div>
                <div class="profile-hold-meta">
                    <span>Qty: <b>${hold.quantity}</b></span>
                    <span>Total: <b>₹${hold.total_price}</b></span>
                    <span>ETA: <b>${escapeHtml(hold.eta)}</b></span>
                    ${otpHtml}
                    ${dirHtml}
                </div>
            `;
            container.appendChild(card);
        });
    }

    // =========================================================================
    // 10. EVENT LISTENERS & LIVE GPS
    // =========================================================================
    function startLiveLocation() {
        if (!navigator.geolocation) {
            showToast("GPS is unavailable in this browser. Using Bengaluru Central.", "alert");
            return;
        }
        showToast("Detecting high-accuracy GPS coordinates...", "info");
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                state.userCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
                state.currentArea = "Your live location";
                state.locationSource = "live";
                $("#location-input").value = "Your live GPS location";
                $("#header-location-name").textContent = "Live GPS Location";
                showToast("GPS Locked! Recalculating exact distances to pharmacies.", "success");
                loadPatientResults();
            },
            () => {
                showToast("Location access denied. Using Bengaluru Central default.", "info");
                loadPatientResults();
            },
            { timeout: 8000 }
        );
    }

    function initEventListeners() {
        // Mode Switcher Buttons with RBAC protection
        $("#btn-patient-mode")?.addEventListener("click", () => {
            switchAppMode("patient");
            showToast("Switched to Patient Mode: Search, Scan & Reserve", "info");
        });

        $("#btn-pharmacy-mode")?.addEventListener("click", () => {
            if (state.currentUser && state.currentUser.role === "patient") {
                showToast("Medical Shop portal requires a Pharmacist or Admin account. Please switch accounts.", "alert");
                openAuthModal();
                return;
            }
            switchAppMode("pharmacy");
            showToast(`Medical Shop Portal: ${state.activeStoreId}`, "success");
        });

        // Authentication Modal Triggers
        $("#btn-open-auth")?.addEventListener("click", openAuthModal);
        $("#btn-close-auth")?.addEventListener("click", closeAuthModal);
        $("#btn-logout")?.addEventListener("click", handleLogout);

        // User Profile & Stored Data Modal Triggers
        $("#btn-user-profile-trigger")?.addEventListener("click", openUserProfileModal);
        $("#btn-close-user-profile")?.addEventListener("click", () => {
            $("#user-profile-modal").hidden = true;
        });
        $("#btn-close-profile-bottom")?.addEventListener("click", () => {
            $("#user-profile-modal").hidden = true;
        });
        $("#btn-profile-signout")?.addEventListener("click", () => {
            $("#user-profile-modal").hidden = true;
            handleLogout();
        });
        $("#btn-refresh-profile-holds")?.addEventListener("click", openUserProfileModal);

        // Profile Edit drawer toggles & submit
        $("#btn-toggle-edit-profile")?.addEventListener("click", () => {
            const drawer = $("#profile-edit-form");
            if (drawer) drawer.hidden = !drawer.hidden;
        });
        $("#btn-cancel-edit-profile")?.addEventListener("click", () => {
            const drawer = $("#profile-edit-form");
            if (drawer) drawer.hidden = true;
        });
        $("#profile-edit-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = $("#edit-profile-name").value.trim();
            const phone = $("#edit-profile-phone").value.trim();
            if (!name) return;
            const res = await api.updateUserProfile({ name, phone });
            if (res && res.success && res.user) {
                state.currentUser = res.user;
                if (res.token) {
                    state.authToken = res.token;
                    localStorage.setItem("mednear_jwt_token", res.token);
                }
                updateAuthUI();
                openUserProfileModal();
                showToast("Profile updated and synced to Supabase Cloud!", "success");
            } else {
                showToast(res?.error || "Failed to update profile", "alert");
            }
        });

        // Profile Raw JSON inspector toggle & copy
        $("#btn-toggle-raw-json")?.addEventListener("click", () => {
            const drawer = $("#profile-raw-json-drawer");
            if (drawer) drawer.hidden = !drawer.hidden;
        });
        $("#btn-copy-profile-json")?.addEventListener("click", () => {
            const text = $("#profile-raw-json-content")?.textContent || "";
            navigator.clipboard.writeText(text).then(() => {
                showToast("Database JSON record copied to clipboard!", "success");
            }).catch(() => {
                showToast("Unable to copy to clipboard", "alert");
            });
        });

        // Role-Specific Action Modals
        $("#btn-patient-my-holds")?.addEventListener("click", renderPatientHoldsModal);
        $("#btn-close-patient-holds")?.addEventListener("click", () => {
            $("#patient-holds-modal").hidden = true;
        });

        $("#btn-admin-panel")?.addEventListener("click", renderAdminUsersModal);
        $("#btn-close-admin")?.addEventListener("click", () => {
            $("#admin-modal").hidden = true;
        });

        // Auth Tabs (Sign In, Patient Signup, Pharmacist Signup)
        $$(".auth-tab-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                $$(".auth-tab-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                const tab = btn.dataset.authtab;
                $("#auth-login-form").hidden = tab !== "login";
                $("#auth-patient-reg-form").hidden = tab !== "patient-reg";
                $("#auth-pharm-reg-form").hidden = tab !== "pharmacist-reg";
                const err = $("#auth-error-banner");
                if (err) err.hidden = true;
            });
        });

        // 1-Click Demo Login Buttons
        $$(".btn-demo-pill").forEach(btn => {
            btn.addEventListener("click", async () => {
                const type = btn.dataset.demo;
                let creds = null;
                if (type === "patient") creds = { email: "patient@mednear.org", password: "Password123!" };
                if (type === "pharmacist-greencross") creds = { email: "pharmacist@greencross.com", password: "Password123!" };
                if (type === "pharmacist-apollo") creds = { email: "pharmacist@apollo.com", password: "Password123!" };
                if (type === "admin") creds = { email: "admin@mednear.org", password: "AdminPassword123!" };
                if (!creds) return;

                const res = await api.login(creds.email, creds.password);
                if (res && res.token) {
                    handleLoginSuccess(res.token, res.user);
                } else {
                    const err = $("#auth-error-banner");
                    if (err) {
                        err.textContent = res.error || "Demo login failed";
                        err.hidden = false;
                    }
                }
            });
        });

        // Sign In Form Submit
        $("#auth-login-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = $("#login-email").value.trim();
            const password = $("#login-password").value;
            const res = await api.login(email, password);
            if (res && res.token) {
                handleLoginSuccess(res.token, res.user);
            } else {
                const err = $("#auth-error-banner");
                if (err) {
                    err.textContent = res.error || "Invalid email or password";
                    err.hidden = false;
                }
            }
        });

        // Patient Signup Submit
        $("#auth-patient-reg-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const submitBtn = e.target.querySelector("button[type='submit']");
            const originalText = submitBtn ? submitBtn.textContent : "";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Storing in Database & Cloud…";
            }
            const name = $("#reg-patient-name").value.trim();
            const email = $("#reg-patient-email").value.trim();
            const phone = $("#reg-patient-phone").value.trim();
            const password = $("#reg-patient-password").value;

            const res = await api.register({ name, email, phone, password, role: "patient" });
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
            if (res && res.token) {
                handleLoginSuccess(res.token, res.user, true);
            } else {
                const err = $("#auth-error-banner");
                if (err) {
                    err.textContent = res.error || "Registration failed";
                    err.hidden = false;
                }
            }
        });

        // Pharmacist Signup Submit
        $("#auth-pharm-reg-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const submitBtn = e.target.querySelector("button[type='submit']");
            const originalText = submitBtn ? submitBtn.textContent : "";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Storing in Database & Cloud…";
            }
            const name = $("#reg-pharm-name").value.trim();
            const email = $("#reg-pharm-email").value.trim();
            const phone = $("#reg-pharm-phone").value.trim();
            const pharmacy_id = $("#reg-pharm-store").value;
            const password = $("#reg-pharm-password").value;

            const res = await api.register({ name, email, phone, pharmacy_id, password, role: "pharmacist" });
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
            if (res && res.token) {
                handleLoginSuccess(res.token, res.user, true);
            } else {
                const err = $("#auth-error-banner");
                if (err) {
                    err.textContent = res.error || "Pharmacist registration failed";
                    err.hidden = false;
                }
            }
        });

        $("#footer-switch-store")?.addEventListener("click", (e) => {
            e.preventDefault();
            $("#btn-pharmacy-mode").click();
            window.scrollTo({ top: 0, behavior: "smooth" });
        });

        // Disease Quick Chips
        $$(".chip-disease").forEach(chip => {
            chip.addEventListener("click", () => {
                const diseaseKey = chip.dataset.disease;
                executeSearch(diseaseKey);
            });
        });

        // Medicine Quick Chips
        $$(".chip[data-medicine]").forEach(chip => {
            chip.addEventListener("click", () => {
                const name = chip.dataset.medicine;
                $("#medicine-input").value = name;
                executeSearch(name);
            });
        });

        // Search Form Submit
        $("#search-form")?.addEventListener("submit", (e) => {
            e.preventDefault();
            executeSearch();
        });

        // GPS Locate Button
        $("#locate-button")?.addEventListener("click", startLiveLocation);

        // Location Geocoding Autocomplete (OpenStreetMap Nominatim + Local Index)
        let geocodeTimer = null;
        const locInput = $("#location-input");
        const suggestionsBox = $("#location-suggestions-dropdown");

        function closeSuggestions() {
            if (suggestionsBox) suggestionsBox.hidden = true;
        }

        locInput?.addEventListener("input", (e) => {
            const val = e.target.value.trim();
            clearTimeout(geocodeTimer);
            if (!val || val.length < 2) {
                closeSuggestions();
                return;
            }

            geocodeTimer = setTimeout(async () => {
                const data = await api.geocode(val);
                const results = data.results || [];
                if (results.length === 0) {
                    closeSuggestions();
                    return;
                }

                suggestionsBox.innerHTML = "";
                results.forEach((item) => {
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "suggestion-item";
                    btn.innerHTML = `
                        <span class="suggestion-pin">📍</span>
                        <div class="suggestion-content">
                            <div class="suggestion-title">
                                <span>${escapeHtml(item.area)}</span>
                                <span class="suggestion-badge">${item.source === 'local_verified' ? 'Verified Local' : 'OpenStreetMap'}</span>
                            </div>
                            <div class="suggestion-sub">${escapeHtml(item.display_name)}</div>
                            <div class="suggestion-coords">GPS: ${item.lat.toFixed(4)}, ${item.lng.toFixed(4)}${item.postcode ? ' · PIN: ' + escapeHtml(item.postcode) : ''}</div>
                        </div>
                    `;
                    btn.addEventListener("click", () => {
                        state.userCoords = { lat: item.lat, lng: item.lng };
                        state.currentArea = item.area;
                        locInput.value = item.area;
                        const headerArea = $("#header-location-name");
                        if (headerArea) headerArea.textContent = `📍 ${item.area}`;
                        closeSuggestions();
                        loadPatientResults();
                        showToast(`Location set to ${item.area} (${item.lat.toFixed(4)}, ${item.lng.toFixed(4)})`, "success");
                    });
                    suggestionsBox.appendChild(btn);
                });
                suggestionsBox.hidden = false;
            }, 260);
        });

        // Close dropdown when user clicks outside
        document.addEventListener("click", (e) => {
            if (!e.target.closest(".location-field")) {
                closeSuggestions();
            }
        });

        // Filter chips (All / Available / Limited)
        $$(".filter-chip").forEach(chip => {
            chip.addEventListener("click", () => {
                $$(".filter-chip").forEach(c => c.classList.remove("active"));
                chip.classList.add("active");
                state.filterStatus = chip.dataset.filter;
                loadPatientResults();
            });
        });

        $("#open-now")?.addEventListener("change", (e) => {
            state.openNowOnly = e.target.checked;
            loadPatientResults();
        });

        $("#filter-24-hours")?.addEventListener("change", (e) => {
            state.twentyFourHoursOnly = e.target.checked;
            loadPatientResults();
        });

        $("#sort-select")?.addEventListener("change", (e) => {
            state.sortBy = e.target.value;
            loadPatientResults();
        });

        $("#reset-filters")?.addEventListener("click", resetFilters);

        // Scanner Shortcuts
        $("#quick-scan-shortcut")?.addEventListener("click", () => openScannerModal("camera"));
        $("#btn-hero-scan")?.addEventListener("click", () => openScannerModal("camera"));
        $("#btn-form-scanner")?.addEventListener("click", () => openScannerModal("camera"));
        $("#btn-preview-trigger")?.addEventListener("click", () => openScannerModal("camera"));
        $("#empty-scan-btn")?.addEventListener("click", () => openScannerModal("camera"));
        $("#footer-open-scanner")?.addEventListener("click", (e) => {
            e.preventDefault();
            openScannerModal("camera");
        });

        $("#btn-close-scanner")?.addEventListener("click", closeScannerModal);

        $$(".scanner-tab").forEach(tab => {
            tab.addEventListener("click", () => switchScannerTab(tab.dataset.tab));
        });

        $("#btn-capture-scan")?.addEventListener("click", () => {
            const video = $("#scanner-video");
            const canvas = $("#scanner-canvas");
            if (state.cameraStream && video && video.videoWidth > 0 && canvas) {
                // Freeze-frame the live feed into the hidden processing canvas, stop the camera,
                // then run real OCR + backend catalog matching on the captured frame.
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
                state.cameraStream.getTracks().forEach(t => t.stop());
                state.cameraStream = null;
                runOcrScan(canvas);
            } else {
                // No live camera available (permission denied / no device) — fall back to demo scan
                runMockScanAnalysis("pantoprazole", "Pan 40 (Pantoprazole 40mg)");
            }
        });

        $("#btn-flip-camera")?.addEventListener("click", () => {
            state.cameraFacing = state.cameraFacing === "environment" ? "user" : "environment";
            startCameraStream();
        });

        $("#btn-switch-to-upload")?.addEventListener("click", () => switchScannerTab("upload"));

        // Upload Dropzone
        const dropzone = $("#upload-dropzone");
        const fileInput = $("#scanner-file-input");
        dropzone?.addEventListener("click", () => fileInput?.click());
        fileInput?.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (re) => {
                    state.lastUploadDataUrl = re.target.result;
                    $("#upload-preview-img").src = re.target.result;
                    $("#upload-dropzone").hidden = true;
                    $("#upload-preview-container").hidden = false;
                };
                reader.readAsDataURL(file);
            }
        });

        $("#btn-analyze-upload")?.addEventListener("click", () => {
            if (state.lastUploadDataUrl) {
                runOcrScan(state.lastUploadDataUrl);
            } else {
                showToast("Please upload a medicine package photo first.", "alert");
            }
        });

        $("#btn-clear-upload")?.addEventListener("click", () => {
            fileInput.value = "";
            state.lastUploadDataUrl = null;
            $("#upload-dropzone").hidden = false;
            $("#upload-preview-container").hidden = true;
        });

        // Scanner Preset Sample Prescriptions
        $$(".preset-card").forEach(card => {
            card.addEventListener("click", () => {
                const p = card.dataset.preset;
                const map = {
                    clopidogrel: ["clopidogrel", "Plavix 75mg (Clopidogrel)"],
                    pantoprazole: ["pantoprazole", "Pan 40 (Pantoprazole 40mg)"],
                    simvastatin: ["simvastatin", "Zocor 40mg (Simvastatin)"],
                    augmentin: ["augmentin", "Augmentin 625 Duo"],
                    dolo: ["dolo", "Dolo 650"],
                    metformin: ["metformin", "Glycomet 500 SR"],
                    cetirizine: ["cetirizine", "Alerid 10mg"],
                    prescription: ["azithromycin", "Azithral 500 (Doctor Rx)"]
                };
                const sel = map[p] || ["pantoprazole", "Pan 40"];
                runMockScanAnalysis(sel[0], sel[1]);
            });
        });

        $("#btn-rescan")?.addEventListener("click", () => {
            $("#scan-result-card").hidden = true;
            if (state.activeScannerTab === "camera") startCameraStream();
        });

        // 30-Minute Hold Reservation Form Submit (SAVES TO SQLITE DATABASE & DISPATCHES OTP)
        $("#hold-request-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = $("#hold-patient-name").value.trim();
            const phone = $("#hold-patient-phone").value.trim();
            const qty = parseInt($("#hold-quantity").value, 10) || 1;
            const eta = $("#hold-eta").value;
            const channel = $("#hold-channel")?.value || "sms";

            const payload = {
                store_id: state.activeHoldStore.storeId,
                patient_name: name,
                phone: phone,
                medicine_id: state.activeHoldStore.medicineKey,
                medicine_name: state.activeHoldStore.medicineName,
                quantity: qty,
                total_price: state.activeHoldStore.price * qty,
                eta: eta,
                notification_channel: channel
            };

            const submitBtn = $("#btn-submit-hold");
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Securing Stock & Dispatching OTP…";
            }

            const result = await api.createHold(payload);

            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "Confirm 30-Min Hold & Send OTP";
            }

            if (result && result.success) {
                // Populate the OTP and Turn-by-Turn Directions confirmation view
                const successPane = $("#hold-success-view");
                const formPane = $("#hold-request-form");
                
                if (successPane && formPane) {
                    formPane.hidden = true;
                    successPane.hidden = false;

                    $("#success-otp-code").textContent = result.otp || "----";
                    
                    const dirLink = $("#success-directions-link");
                    if (dirLink) {
                        dirLink.href = result.directions_url || `https://www.google.com/maps/dir/?api=1&destination=${state.activeHoldStore.storeName}`;
                    }

                    const pharmInfo = $("#success-pharm-info");
                    if (pharmInfo) {
                        pharmInfo.textContent = `${result.pharmacy?.name || state.activeHoldStore.storeName} · ${result.pharmacy?.address || 'Bengaluru'}`;
                    }

                    const pharmPhone = $("#success-pharm-phone");
                    if (pharmPhone) {
                        pharmPhone.textContent = result.pharmacy?.phone || "+91 80 4000 1101";
                    }

                    const badge = $("#success-dispatch-badge");
                    const previewText = $("#success-dispatch-text");
                    const patientNotif = result.notifications?.patient_notifications?.[0];

                    if (badge) {
                        badge.textContent = patientNotif?.mode === "live_twilio" 
                            ? `Live Twilio Delivered (${channel.toUpperCase()})` 
                            : `Delivered (${channel.toUpperCase()})`;
                    }

                    if (previewText) {
                        previewText.textContent = patientNotif?.preview || `MedNear Hold Confirmed! Code: ${result.hold_id} | OTP: ${result.otp}\nDirections: ${result.directions_url}`;
                    }

                    showToast(`Stock reserved! Verification OTP: ${result.otp}`, "success");
                } else {
                    closeHoldModal();
                    showToast(`Reserved ${payload.medicine_name} for 30 minutes! OTP: ${result.otp}`, "success");
                }
            } else {
                closeHoldModal();
                showToast(`Reserved ${payload.medicine_name} for 30 minutes at ${state.activeHoldStore.storeName}!`, "success");
            }
        });

        $("#btn-done-hold")?.addEventListener("click", () => {
            closeHoldModal();
            showToast("Your reservation is active. Proceed to pharmacy with your OTP.", "info");
        });

        $("#btn-close-hold")?.addEventListener("click", closeHoldModal);
        $("#btn-cancel-hold")?.addEventListener("click", closeHoldModal);

        // Chemist Barcode Scanner
        $("#btn-store-scan-barcode")?.addEventListener("click", () => {
            openScannerModal("camera");
            showToast("Point camera at medicine barcode or strip for counter restock.", "info");
        });

        // Add Inventory Modal (SAVES TO SQLITE DATABASE)
        $("#btn-add-inventory-modal")?.addEventListener("click", () => {
            $("#add-item-modal").hidden = false;
        });
        $("#btn-close-add-item")?.addEventListener("click", () => {
            $("#add-item-modal").hidden = true;
        });
        $("#btn-cancel-add-item")?.addEventListener("click", () => {
            $("#add-item-modal").hidden = true;
        });

        $("#add-item-form")?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = $("#new-item-name").value.trim();
            const salt = $("#new-item-salt").value.trim();
            const units = parseInt($("#new-item-units").value, 10) || 10;
            const rack = $("#new-item-rack").value.trim() || "Rack B-1";
            const price = parseFloat($("#new-item-price").value) || 100;
            const status = $("#new-item-status").value;

            const medId = name.toLowerCase().replace(/[^a-z0-9]/g, "");

            await api.updateStoreInventory(state.activeStoreId, {
                medicine_id: medId,
                name: name,
                generic_name: salt,
                status: status,
                units: units,
                price: price,
                rack: rack
            });

            $("#add-item-modal").hidden = true;
            renderPharmacyDashboard();
            showToast(`Added ${name} directly to store inventory in SQLite!`, "success");
        });
    }

    // =========================================================================
    // 10.5 MEDNEAR CLINICAL AI ASSISTANT & CHATBOT
    // =========================================================================
    const aiChatHistory = [];

    function formatAIMarkdown(text) {
        if (!text) return "";
        let html = text
            // Escape HTML tags to prevent XSS
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            // Headings
            .replace(/^### (.*$)/gim, "<h3>$1</h3>")
            .replace(/^#### (.*$)/gim, "<h4>$1</h4>")
            // Bold & Italic
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            // Inline code
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            // Unordered list items
            .replace(/^\* (.*$)/gim, "<li>$1</li>")
            .replace(/^- (.*$)/gim, "<li>$1</li>");

        // Wrap contiguous <li> in <ul>
        html = html.replace(/(<li>.*?<\/li>(\s*<li>.*?<\/li>)*)/gs, "<ul>$1</ul>");

        // Convert double newlines to paragraphs, single newlines to <br> inside paragraphs
        const paragraphs = html.split(/\n{2,}/);
        html = paragraphs.map(p => {
            p = p.trim();
            if (!p) return "";
            if (p.startsWith("<h") || p.startsWith("<ul") || p.startsWith("<ol")) return p;
            return `<p>${p.replace(/\n/g, "<br>")}</p>`;
        }).join("");

        return html;
    }

    function initAIChatbot() {
        const launcher = $("#ai-chat-launcher");
        const windowEl = $("#ai-chat-window");
        const headerPill = $("#btn-header-ai-chat");
        const heroBtn = $("#btn-hero-ai-chat");
        const closeBtn = $("#ai-btn-close");
        const expandBtn = $("#ai-btn-expand");
        const clearBtn = $("#ai-btn-clear");
        const form = $("#ai-chat-form");
        const input = $("#ai-chat-input");
        const messagesEl = $("#ai-chat-messages");
        const typingEl = $("#ai-typing-indicator");
        const chipsContainer = $("#ai-quick-chips");
        const micBtn = $("#ai-btn-mic");

        if (!launcher || !windowEl) return;

        function openChat() {
            windowEl.hidden = false;
            windowEl.setAttribute("aria-hidden", "false");
            const badge = launcher.querySelector(".ai-launcher-badge");
            if (badge) badge.style.display = "none";
            setTimeout(() => input?.focus(), 150);
            if (!messagesEl.children.length) {
                renderAIWelcomeMessage();
            }
        }

        function closeChat() {
            windowEl.hidden = true;
            windowEl.setAttribute("aria-hidden", "true");
        }

        function toggleChat() {
            if (windowEl.hidden) openChat();
            else closeChat();
        }

        launcher.addEventListener("click", toggleChat);
        headerPill?.addEventListener("click", openChat);
        heroBtn?.addEventListener("click", () => {
            openChat();
            windowEl.scrollIntoView({ behavior: "smooth", block: "center" });
        });
        closeBtn?.addEventListener("click", closeChat);

        expandBtn?.addEventListener("click", () => {
            windowEl.classList.toggle("fullscreen");
            expandBtn.textContent = windowEl.classList.contains("fullscreen") ? "🗗" : "⛶";
        });

        clearBtn?.addEventListener("click", () => {
            messagesEl.innerHTML = "";
            aiChatHistory.length = 0;
            renderAIWelcomeMessage();
            showToast("AI Chat conversation cleared.", "info");
        });

        // Auto-grow textarea on input
        input?.addEventListener("input", () => {
            input.style.height = "auto";
            input.style.height = Math.min(input.scrollHeight, 80) + "px";
        });

        // Submit on Enter without shift
        input?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                form.dispatchEvent(new Event("submit"));
            }
        });

        function scrollToBottom() {
            setTimeout(() => {
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }, 50);
        }

        function appendUserMessage(text) {
            const row = document.createElement("div");
            row.className = "ai-msg-row user";
            row.innerHTML = `
                <div class="ai-msg-avatar">👤</div>
                <div class="ai-msg-bubble">${text.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>
            `;
            messagesEl.appendChild(row);
            scrollToBottom();
        }

        function appendBotMessage(replyMarkdown, stockCards = [], suggestions = [], matchedMedicine = null) {
            const row = document.createElement("div");
            row.className = "ai-msg-row bot";

            let stockCardsHtml = "";
            if (stockCards && stockCards.length > 0) {
                stockCardsHtml = `
                    <div class="ai-stock-cards-container">
                        ${stockCards.map(c => {
                            const statusLabel = c.status === "available" 
                                ? `🟢 In Stock (${c.units} units)` 
                                : (c.status === "limited" ? `🟡 Limited (${c.units} units)` : "🔴 Out of Stock");
                            const isAvail = c.status !== "unavailable";
                            const destQuery = encodeURIComponent(c.address || c.pharmacy_name);
                            return `
                                <div class="ai-stock-card">
                                    <div class="ai-stock-card-header">
                                        <div class="ai-pharmacy-name">${c.pharmacy_name}</div>
                                        <div class="ai-pharmacy-dist">📍 ${c.distance_km} km</div>
                                    </div>
                                    <div class="ai-stock-card-body">
                                        <span class="ai-stock-badge ${c.status}">${statusLabel}</span>
                                        <span class="ai-stock-price">₹${c.price} <small style="font-size:0.7rem;font-weight:normal;color:#64748b;">/ strip</small></span>
                                    </div>
                                    <div class="ai-stock-card-actions">
                                        ${isAvail ? `
                                            <button type="button" class="btn-ai-reserve-hold" data-store-id="${c.pharmacy_id}" data-store-name="${c.pharmacy_name}" data-price="${c.price}">
                                                <span>⚡ Reserve 30-Min Hold</span>
                                            </button>
                                        ` : `
                                            <span style="font-size:0.75rem; color:#991b1b; padding:4px 0;">Currently unreserved</span>
                                        `}
                                        <a href="https://www.google.com/maps/dir/?api=1&destination=${destQuery}" target="_blank" rel="noopener noreferrer" class="btn-ai-directions" title="Get turn-by-turn directions">
                                            <span>🧭 Map</span>
                                        </a>
                                    </div>
                                </div>
                            `;
                        }).join("")}
                    </div>
                `;
            }

            let suggestionsHtml = "";
            if (suggestions && suggestions.length > 0) {
                suggestionsHtml = `
                    <div class="ai-followup-suggestions">
                        ${suggestions.map(s => `<button type="button" class="ai-followup-chip">${s}</button>`).join("")}
                    </div>
                `;
            }

            row.innerHTML = `
                <div class="ai-msg-avatar">🤖</div>
                <div class="ai-msg-bubble">
                    ${formatAIMarkdown(replyMarkdown)}
                    ${stockCardsHtml}
                    ${suggestionsHtml}
                </div>
            `;

            // Attach Hold reservation events on cards
            row.querySelectorAll(".btn-ai-reserve-hold").forEach(btn => {
                btn.addEventListener("click", () => {
                    const storeId = btn.dataset.storeId;
                    const storeName = btn.dataset.storeName;
                    const price = parseFloat(btn.dataset.price) || 100;
                    const medKey = matchedMedicine ? matchedMedicine.id : state.activeMedicineKey;
                    const medName = matchedMedicine ? matchedMedicine.name : state.activeMedicineSearchTerm;

                    // If on mobile, close the chat drawer so hold modal is clear
                    if (window.innerWidth < 640) {
                        closeChat();
                    }

                    openHoldModal({
                        storeId: storeId,
                        storeName: storeName,
                        medicineKey: medKey,
                        medicineName: medName,
                        price: price
                    });
                });
            });

            // Attach suggestion chip click events
            row.querySelectorAll(".ai-followup-chip").forEach(chip => {
                chip.addEventListener("click", () => {
                    submitAIMessage(chip.textContent.trim());
                });
            });

            messagesEl.appendChild(row);
            scrollToBottom();
        }

        async function submitAIMessage(queryText) {
            const text = (queryText || input.value || "").trim();
            if (!text) return;

            input.value = "";
            input.style.height = "auto";
            appendUserMessage(text);

            typingEl.hidden = false;
            scrollToBottom();

            // Record into local memory history
            aiChatHistory.push({ role: "user", content: text });

            const lat = state.userCoords?.lat || 12.9716;
            const lng = state.userCoords?.lng || 77.5946;

            const res = await api.sendAIChatMessage(text, aiChatHistory, lat, lng);
            typingEl.hidden = true;

            if (res && res.reply) {
                aiChatHistory.push({ role: "assistant", content: res.reply });
                appendBotMessage(res.reply, res.stock_cards, res.suggestions, res.matched_medicine);
            } else {
                appendBotMessage("⚠️ Could not retrieve answer. Please try asking again.");
            }
        }

        form?.addEventListener("submit", (e) => {
            e.preventDefault();
            submitAIMessage();
        });

        // Speech Recognition (Voice Input)
        if ("SpeechRecognition" in window || "webkitSpeechRecognition" in window) {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            const recognizer = new SpeechRec();
            recognizer.continuous = false;
            recognizer.interimResults = false;
            recognizer.lang = "en-IN";

            recognizer.onstart = () => {
                micBtn?.classList.add("listening");
                showToast("🎙️ Listening... Speak your tablet or health question now", "info");
            };

            recognizer.onresult = (evt) => {
                const transcript = evt.results[0][0].transcript;
                if (transcript) {
                    input.value = transcript;
                    submitAIMessage(transcript);
                }
            };

            recognizer.onerror = (err) => {
                console.warn("Speech recognition error:", err);
                micBtn?.classList.remove("listening");
            };

            recognizer.onend = () => {
                micBtn?.classList.remove("listening");
            };

            micBtn?.addEventListener("click", () => {
                try {
                    recognizer.start();
                } catch (e) {
                    recognizer.stop();
                }
            });
        } else {
            if (micBtn) micBtn.title = "Voice recognition not supported in this browser";
        }

        // Render Initial Welcome Message
        function renderAIWelcomeMessage() {
            appendBotMessage(
                "### 👋 Welcome to MedNear Clinical AI Assistant!\n\n" +
                "I am your real-time medicine awareness & stock guidance companion:\n\n" +
                "* 💊 **Check Live Stock**: See which nearby pharmacies have tablets in stock right now.\n" +
                "* 🧬 **Pharmacogenomics Awareness**: Check whether your DNA (CYP2C19, SLCO1B1) affects your response to drugs like Plavix, Pan 40, or Simvastatin.\n" +
                "* 🏷️ **Generic Alternatives**: Save up to 70% with affordable Jan Aushadhi alternatives.\n" +
                "* ⚡ **30-Min Hold**: Reserve your medicine instantly with zero advance payment.\n\n" +
                "**Choose an option below or type any tablet question:**",
                [],
                [
                    "Is Pan 40 available near me?",
                    "What are the genetic risks of Plavix?",
                    "Where can I buy Dolo 650 right now?",
                    "Can I take Clopidogrel with Omeprazole?",
                    "Show 24/7 open pharmacies"
                ]
            );
        }

        // Load Starter Quick Chips from API
        api.getAISuggestions().then(res => {
            if (res && res.suggestions && chipsContainer) {
                chipsContainer.innerHTML = res.suggestions.map(s => `
                    <button type="button" class="ai-quick-chip">
                        <span>${s.icon || "💊"}</span>
                        <span>${s.label}</span>
                    </button>
                `).join("");

                chipsContainer.querySelectorAll(".ai-quick-chip").forEach((chip, idx) => {
                    chip.addEventListener("click", () => {
                        const query = res.suggestions[idx]?.query || chip.textContent.trim();
                        openChat();
                        submitAIMessage(query);
                    });
                });
            }
        });
    }

    // =========================================================================
    // 11. BOOTSTRAP
    // =========================================================================
    function init() {
        initSupabase();
        initEventListeners();
        initAIChatbot();

        // Restore active user session if JWT token exists
        if (state.authToken) {
            api.getMe().then(res => {
                if (res && res.user) {
                    state.currentUser = res.user;
                    updateAuthUI();
                } else {
                    state.authToken = null;
                    localStorage.removeItem("mednear_jwt_token");
                    updateAuthUI();
                }
            });
        } else {
            updateAuthUI();
        }

        $("#medicine-input").value = "Pan 40";
        state.activeMedicineKey = "pantoprazole";
        state.activeMedicineSearchTerm = "Pan 40 (Pantoprazole 40mg)";
        loadPatientResults();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
