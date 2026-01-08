# item_ipad_pro.py - Emergency Cart Checklist + Equipment Daily Check (iPad-friendly UI)
# Notes:
# - Emergency Cart: Uses CSV/SQLite as source
# - Equipment Check: Uses separate SQLite tables
# - iPad-friendly: bigger typography, forms, sticky sidebar
# Version: 2.0 - Added Equipment Daily Check System

import os
import io
import hmac
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

# ==============================
#  CARD: BUNDLE STATUS BLOCK
# ==============================
def bundle_status_block(df: pd.DataFrame, warn_days: int = 30) -> None:
    st.markdown("### 🏥 สถานะความพร้อมชุดอุปกรณ์ (Bundle)")

    # ---------- Guards ----------
    if "Bundle" not in df.columns:
        st.info("ยังไม่มีคอลัมน์ Bundle ในไฟล์")
        return

    # ต้องมีคอลัมน์พื้นฐาน
    needed = ["Item_Name", "Current_Stock", "Days_to_Expire"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        st.warning(f"คอลัมน์ไม่ครบสำหรับทำ Bundle dashboard: {missing}")
        return

    df_bundle = df[df["Bundle"].notna()].copy()
    # normalize types for stable grouping
    df_bundle["Bundle"] = df_bundle["Bundle"].astype(str).str.strip().str.lower()
    df_bundle["Current_Stock"] = pd.to_numeric(df_bundle["Current_Stock"], errors="coerce").fillna(0)
    df_bundle["Days_to_Expire"] = pd.to_numeric(df_bundle["Days_to_Expire"], errors="coerce").fillna(999999)
    if df_bundle.empty:
        st.info("ยังไม่มีการกำหนด Bundle")
        return

    # ---------- Bundle config ----------
    bundles = {
        "airway": {"icon": "🫁", "name": "Airway Management"},
        "iv":     {"icon": "💧", "name": "Fluid Management"},
        "cpr":    {"icon": "❤️‍🩹", "name": "CPR Kit"},
    }

    # ---------- Styling ----------
    st.markdown(
        """
        <style>
        .bundle-card {
            border-radius: 16px;
            padding: 16px 16px;
            border: 1px solid rgba(0,0,0,0.08);
            box-shadow: 0 6px 18px rgba(0,0,0,0.06);
            margin-bottom: 12px;
        }
        .bundle-title {
            font-size: 18px; font-weight: 800;
            display:flex; align-items:center; gap:10px;
            margin-bottom: 4px;
        }
        .bundle-sub {
            font-size: 13px; opacity: 0.85; margin-bottom: 10px;
        }
        .pill {
            display:inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            font-weight: 800;
            font-size: 12px;
            margin-right: 8px;
        }
        .pill-ready { background: rgba(81, 207, 102, 0.18); color: #2b8a3e; }
        .pill-not   { background: rgba(255, 107, 107, 0.18); color: #c92a2a; }
        .mini {
            font-size: 12px; opacity: 0.9;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- Helper: find problems ----------
    def classify_problems(g: pd.DataFrame) -> dict:
        # หมดอายุ
        expired = g[g["Days_to_Expire"].fillna(999999) <= 0]
        # ใกล้หมดอายุ
        exp_soon = g[
            (g["Days_to_Expire"].fillna(999999) > 0) &
            (g["Days_to_Expire"].fillna(999999) <= warn_days)
        ]
        # stock หมด
        out_stock = g[g["Current_Stock"].fillna(0) <= 0]

        # รวม "รายการมีปัญหา" (unique ตามชื่อ)
        problem = pd.concat([expired, exp_soon, out_stock], ignore_index=True)
        problem = problem.drop_duplicates(subset=["Item_Name"])

        return {
            "expired": expired,
            "exp_soon": exp_soon,
            "out_stock": out_stock,
            "problem": problem
        }

    # ---------- Layout: responsive columns ----------
    cols = st.columns(2)

    # group ตาม Bundle
    grouped = list(df_bundle.groupby("Bundle"))
    if not grouped:
        st.info("ยังไม่มีรายการใน Bundle")
        return

    for i, (bundle_key, g) in enumerate(grouped):
        meta = bundles.get(bundle_key, {"icon": "📦", "name": str(bundle_key)})

        probs = classify_problems(g)
        problem_df = probs["problem"]
        is_ready = problem_df.empty

        total_items = len(g)
        problem_count = len(problem_df)

        # สีพื้นตามสถานะ
        bg = "rgba(81, 207, 102, 0.10)" if is_ready else "rgba(255, 107, 107, 0.10)"
        pill = "pill-ready" if is_ready else "pill-not"
        pill_text = "✅ READY" if is_ready else "❌ NOT READY"

        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="bundle-card" style="background:{bg}">
                  <div class="bundle-title">{meta["icon"]} {meta["name"]}</div>
                  <div class="bundle-sub">
                    <span class="pill {pill}">{pill_text}</span>
                    <span class="mini">ทั้งหมด {total_items} รายการ • มีปัญหา {problem_count} รายการ</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # รายละเอียด (กดดูเมื่อจำเป็น)
            with st.expander("ดูรายละเอียดรายการที่มีปัญหา"):
                if is_ready:
                    st.success("ไม่มีรายการมีปัญหา 🎉")
                else:
                    # ทำตารางแบบกระชับ (iPad friendly)
                    show_cols = [c for c in ["Item_Name", "Current_Stock", "Days_to_Expire", "EXP_Date"] if c in g.columns]
                    detail = problem_df.copy()

                    # เพิ่ม reason column อ่านง่าย
                    def reason(row):
                        reasons = []
                        if row.get("Current_Stock", 0) <= 0:
                            reasons.append("Stock หมด")
                        d = row.get("Days_to_Expire", 999999)
                        if pd.notna(d) and d <= 0:
                            reasons.append("หมดอายุ")
                        elif pd.notna(d) and d <= warn_days:
                            reasons.append(f"ใกล้หมด ({warn_days} วัน)")
                        return ", ".join(reasons) if reasons else "-"

                    detail["Reason"] = detail.apply(reason, axis=1)
                    show_cols2 = ["Reason"] + show_cols

                    st.dataframe(
                        detail[show_cols2].sort_values(["Days_to_Expire"], ascending=True),
                        use_container_width=True,
                        hide_index=True
                    )

# ==============================
# 0) APP CONFIG + STYLE
# ==============================
st.set_page_config(
    page_title="Emergency Cart & Equipment Check",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
/* ----- iPad friendly typography ----- */
html, body, [class*="css"]  { font-size: 18px !important; }
h1 { font-size: 2.0rem !important; }
h2 { font-size: 1.5rem !important; }
h3 { font-size: 1.25rem !important; }

/* Reduce wasted space */
.block-container { padding-top: 1.3rem; padding-bottom: 2.2rem; }

/* Sidebar look */
section[data-testid="stSidebar"] { width: 360px !important; }
section[data-testid="stSidebar"] .stMarkdown { font-size: 0.98rem; }

/* Buttons bigger */
.stButton>button, .stDownloadButton>button {
  padding: 0.55rem 0.9rem;
  border-radius: 12px;
  font-weight: 700;
}

/* Card-ish containers */
.card {
  background: #ffffff;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.85rem;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(0,0,0,0.02);
}
.badge.red { background:#ffe5e5; border-color:#ffb3b3; }
.badge.yellow { background:#fff7d6; border-color:#ffe08a; }
.badge.green { background:#e7ffe7; border-color:#b7f0b7; }
.badge.gray { background:#f3f4f6; border-color:#e5e7eb; }

/* Equipment status badges */
.status-badge {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.9rem;
    margin: 4px;
}
.badge-ready { background: #d3f9d8; color: #2b8a3e; border: 2px solid #51cf66; }
.badge-not-ready { background: #ffe0e0; color: #c92a2a; border: 2px solid #ff6b6b; }
.badge-borrowed { background: #e0f2ff; color: #1971c2; border: 2px solid #4dabf7; }
.badge-maintenance { background: #fff3bf; color: #e67700; border: 2px solid #fab005; }

/* Metric cards for equipment */
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 20px;
    color: white;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.metric-card h3 { color: white; margin: 0; font-size: 2.5rem; }
.metric-card p { margin: 4px 0 0 0; opacity: 0.95; font-size: 0.95rem; }

.metric-card.green {
    background: linear-gradient(135deg, #51cf66 0%, #2b8a3e 100%);
}
.metric-card.blue {
    background: linear-gradient(135deg, #4dabf7 0%, #1971c2 100%);
}
.metric-card.red {
    background: linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%);
}

/* Equipment card styling */
.equipment-card {
    background: white;
    border: 1px solid #e9ecef;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    transition: all 0.3s;
}
.equipment-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    transform: translateY(-2px);
}

/* Dataframe header sticky-ish (best effort) */
div[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }

/* Make sidebar radio compact */
div[role="radiogroup"] label { padding: 0.2rem 0.2rem; }

/* Hide Streamlit footer */
footer {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)
# ==============================
# 1) SIMPLE PASSWORD GATE
# ==============================
def check_password() -> None:
    """Sidebar password gate with customizable password"""
    if "auth" not in st.session_state:
        st.session_state["auth"] = False

    if st.session_state["auth"]:
        return

    st.sidebar.header("🔐 Login")
    pw = st.sidebar.text_input("Password", type="password")
    
    # 🔑 เปลี่ยนรหัสผ่านตรงนี้
    YOUR_PASSWORD = "muke"  # ⬅️ เปลี่ยนรหัสตรงนี้

    if st.sidebar.button("Login"):
        # ลองอ่าน password จาก secrets ก่อน (สำหรับ Streamlit Cloud)
        try:
            secret = st.secrets.get("APP_PASSWORD", YOUR_PASSWORD)
        except:
            secret = YOUR_PASSWORD  # ใช้รหัสที่ตั้งไว้
        
        if hmac.compare_digest(pw, secret):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.sidebar.error("รหัสไม่ถูกต้อง")

    st.stop()

check_password()

# ==============================
# 2) LOAD + SAVE HELPERS (SQLite) - EMERGENCY CART
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_db_file(filename: str) -> str:
    """Resolve DB path deterministically to avoid accidentally creating/using the wrong DB.

    Priority:
    1) Streamlit secrets: st.secrets["EMERGENCY_CART_DB_PATH"] (best for Streamlit Cloud)
    2) Environment variable: EMERGENCY_CART_DB_PATH
    3) Same folder as this script (BASE_DIR)

    Notes:
    - We intentionally DO NOT fall back to os.getcwd() or parent folders because that can
      silently point to a different DB and then trigger demo seeding / wrong data.
    - If the resolved file does not exist yet, SQLite will create it at that path.
    """
    # 1) Streamlit secrets (Streamlit Cloud-friendly)
    try:
        secret = st.secrets.get("EMERGENCY_CART_DB_PATH", "")
        if isinstance(secret, str) and secret.strip():
            return secret.strip()
    except Exception:
        pass

    # 2) Environment variable
    env = os.environ.get("EMERGENCY_CART_DB_PATH", "").strip()
    if env:
        return env

    # 3) Default: same folder as this script (repo folder on Streamlit Cloud: /mount/src/<repo>/)
    return os.path.join(BASE_DIR, filename)


DB_FILE = _resolve_db_file("item_orm.db")
LEGACY_CSV = os.path.join(BASE_DIR, "item_ORM.csv")


def _get_conn() -> sqlite3.Connection:
    # check_same_thread=False for Streamlit (single-process) convenience
    # timeout=30.0 to handle concurrent access better
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")  # better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                item_name TEXT PRIMARY KEY,
                stock INTEGER NOT NULL DEFAULT 0,
                current_stock INTEGER NOT NULL DEFAULT 0,
                exp_date TEXT,        -- ISO 'YYYY-MM-DD' (NULL allowed)
                bundle TEXT
            )
            """
        )
        conn.commit()


def _migrate_csv_to_db_if_needed() -> None:
    """One-way import from legacy CSV into SQLite (first run only)."""
    if not os.path.exists(LEGACY_CSV):
        return

    with _get_conn() as conn:
        # If DB already has data, don't re-import
        n = conn.execute("SELECT COUNT(1) FROM items").fetchone()[0]
        if n and n > 0:
            return

    try:
        df = pd.read_csv(LEGACY_CSV, encoding="utf-8-sig")
    except Exception:
        # If CSV can't be read, skip migration and let app run with empty DB
        return

    # Normalize expected columns
    for col in ["Item_Name", "Stock", "Current_Stock", "EXP_Date"]:
        if col not in df.columns:
            return

    # Optional columns
    if "Bundle" not in df.columns:
        df["Bundle"] = None

    df["Item_Name"] = df["Item_Name"].astype(str).str.strip()
    df["Stock"] = pd.to_numeric(df["Stock"], errors="coerce").fillna(0).astype(int)
    df["Current_Stock"] = pd.to_numeric(df["Current_Stock"], errors="coerce")
    df["Current_Stock"] = df["Current_Stock"].fillna(df["Stock"]).astype(int)

    # Parse EXP_Date (accept dd/mm/YYYY or YYYY-mm-dd) -> ISO
    exp_ts = pd.to_datetime(df["EXP_Date"], errors="coerce", dayfirst=True)
    df["exp_iso"] = exp_ts.dt.strftime("%Y-%m-%d")

    with _get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO items (item_name, stock, current_stock, exp_date, bundle)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_name) DO UPDATE SET
                stock=excluded.stock,
                current_stock=excluded.current_stock,
                exp_date=excluded.exp_date,
                bundle=excluded.bundle
            """,
            [
                (
                    r["Item_Name"],
                    int(r["Stock"]),
                    int(r["Current_Stock"]),
                    (r["exp_iso"] if isinstance(r["exp_iso"], str) else None),
                    (None if pd.isna(r["Bundle"]) else str(r["Bundle"]).strip()),
                )
                for _, r in df.iterrows()
            ],
        )
        conn.commit()

def _seed_emergency_cart_if_empty_if_enabled() -> None:
    """OPTIONAL demo data seeding (disabled by default).

    To enable (ONLY for local demo/testing), set either:
    - st.secrets["ALLOW_DEMO_SEED"] = "true"
    - or environment variable ALLOW_DEMO_SEED=true
    """
    allow = False
    try:
        allow = str(st.secrets.get("ALLOW_DEMO_SEED", "")).strip().lower() in ("1", "true", "yes", "y")
    except Exception:
        pass
    if not allow:
        allow = os.environ.get("ALLOW_DEMO_SEED", "").strip().lower() in ("1", "true", "yes", "y")
    if not allow:
        return

    with _get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if count > 0:
            return

        demo_items = [
            ("Adrenaline 1mg/ml 1ml", 10, 10, "2026-12-31", "cpr"),
            ("Atropine 0.6mg/ml 1ml", 10, 9, "2026-08-15", "cpr"),
            ("Amiodarone 150mg/3ml", 5, 5, "2026-10-20", "cpr"),
            ("Lidocaine 100mg/5ml", 5, 4, "2026-11-30", "cpr"),
            ("ETT 6.5", 2, 2, "2027-03-15", "airway"),
            ("ETT 7.0", 2, 2, "2027-03-15", "airway"),
            ("ETT 7.5", 2, 1, "2027-03-15", "airway"),
            ("ETT 8.0", 2, 2, "2027-03-15", "airway"),
            ("Laryngoscope blade", 3, 3, "2028-01-01", "airway"),
            ("NSS 1000ml", 20, 18, "2026-09-30", "iv"),
            ("NSS 500ml", 10, 8, "2026-09-30", "iv"),
            ("RL 1000ml", 10, 10, "2026-11-20", "iv"),
            ("D5W 1000ml", 5, 5, "2026-07-15", "iv"),
            ("IV Cannula 18G", 20, 15, "2027-06-30", "iv"),
            ("IV Cannula 20G", 20, 18, "2027-06-30", "iv"),
        ]

        conn.executemany(
            """
            INSERT INTO items (item_name, stock, current_stock, exp_date, bundle)
            VALUES (?, ?, ?, ?, ?)
            """,
            demo_items,
        )
        conn.commit()

def load_items() -> pd.DataFrame:
    _init_db()
    _migrate_csv_to_db_if_needed()
    _seed_emergency_cart_if_empty_if_enabled()
    with _get_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                item_name AS Item_Name,
                stock AS Stock,
                current_stock AS Current_Stock,
                exp_date AS EXP_Date,
                bundle AS Bundle
            FROM items
            ORDER BY item_name
            """,
            conn,
        )

    # Clean types
    if not df.empty:
        df["Item_Name"] = df["Item_Name"].astype(str).str.strip()
        df["Stock"] = pd.to_numeric(df["Stock"], errors="coerce").fillna(0).astype(int)
        df["Current_Stock"] = pd.to_numeric(df["Current_Stock"], errors="coerce").fillna(df["Stock"]).astype(int)

    return df


def db_update_exp(item_name: str, new_exp: date) -> None:
    exp_iso = pd.to_datetime(new_exp).strftime("%Y-%m-%d")
    with _get_conn() as conn:
        conn.execute(
            "UPDATE items SET exp_date=? WHERE item_name=?",
            (exp_iso, item_name),
        )
        conn.commit()


def db_cut_stock(item_name: str, qty_use: int) -> None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT current_stock FROM items WHERE item_name=?",
            (item_name,),
        ).fetchone()

        cur = int(row[0]) if row and row[0] is not None else 0
        if cur <= 0:
            raise ValueError("Stock หมดแล้ว")
        if qty_use > cur:
            raise ValueError("จำนวนที่ใช้มากกว่า Stock ปัจจุบัน")

        conn.execute(
            "UPDATE items SET current_stock=? WHERE item_name=?",
            (cur - int(qty_use), item_name),
        )
        conn.commit()


def db_reset_stock(item_name: str) -> int:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT stock FROM items WHERE item_name=?",
            (item_name,),
        ).fetchone()
        base = int(row[0]) if row and row[0] is not None else 0

        conn.execute(
            "UPDATE items SET current_stock=? WHERE item_name=?",
            (base, item_name),
        )
        conn.commit()

    return base


# ==============================
# 3) EQUIPMENT DAILY CHECK - DATABASE FUNCTIONS
# ==============================
# ใช้ _resolve_db_file() เหมือน Emergency Cart เพื่อความมั่นคง
EQUIPMENT_DB = _resolve_db_file("equipment_daily.db")

def get_equipment_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(EQUIPMENT_DB, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_equipment_db() -> None:
    with get_equipment_conn() as conn:
        # เปิด foreign key support
        conn.execute("PRAGMA foreign_keys = ON;")
        
        # ตารางเครื่องมือหลัก
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                pgh_code TEXT,
                serial_number TEXT,
                last_maintenance_date TEXT,
                maintenance_note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # ตารางบันทึกการตรวจสอบรายวัน - ไม่ใช้ FOREIGN KEY
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id INTEGER NOT NULL,
                check_date TEXT NOT NULL,
                check_time TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('พร้อมใช้', 'ไม่พร้อมใช้', 'วอร์ดอื่นยืม', 'รอซ่อม')),
                borrowed_to TEXT,
                remark TEXT,
                checked_by TEXT
            )
            """
        )
        
        conn.commit()

def seed_initial_equipment() -> None:
    """เพิ่มรายการเครื่องมืออุปกรณ์เริ่มต้นถ้ายังไม่มีข้อมูล"""
    init_equipment_db()
    
    with get_equipment_conn() as conn:
        # ตรวจสอบว่ามีข้อมูลแล้วหรือยัง
        count = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
        if count > 0:
            return  # มีข้อมูลแล้ว ไม่ต้อง seed
        
        # รายการเครื่องมือทั้งหมด (ปรับชื่อให้ไม่ซ้ำกัน)
        equipment_list = [
            ("Enerjet", "pgh0853", "AD0115154"),
            ("CO2 laser Sharplan", "pgh0882", "33-121"),
            ("Q-switch laser", "pgh0883", "LO-3ND"),
            ("Smaz", "pgh0884", "MAZ 0360012954"),
            ("Scarlet", "pgh0885", "SLSNC 00547 H"),
            ("เครื่องดูดควัน Ellman (pgh0888)", "pgh0888", "01453597"),
            ("Koolio", "pgh5519", "KOO-210034"),
            ("CO2 laser Uti", "pgh5520", "1N140331-01"),
            ("Emsculpt", "pgh5521", "799028002935"),
            ("Cooltech", "pgh5522", "2000000399-10018"),
            ("Morpheus pro", "-", "R10420307"),
            ("Primaled", "pgh3057", "1683"),
            ("Siui cts-415a", "pgh5525", "ไม่สามารถระบุได้"),
            ("Sonoscope", "pgh5526", "0261017160"),
            ("Gomco", "pgh2386", "1115"),
            ("Covidien", "pgh0821", "S4J15048AX"),
            ("เครื่องดูดควัน Ellman (pgh4748)", "pgh4748", "04153495"),
            ("Erbe", "pgh2386", "11418045"),
            ("Valleylab", "pgh0818", "FOF10138T"),
            ("Old Ellman surgitron", "pgh0819", "166979"),
            ("New Ellman surgitron", "pgh0822", "2915WA"),
            ("เครื่องดูดควัน Ellman (pgh0847)", "pgh0847", "04153493"),
        ]
        
        # Insert ทั้งหมด
        conn.executemany(
            "INSERT INTO equipment (name, pgh_code, serial_number) VALUES (?, ?, ?)",
            equipment_list
        )
        conn.commit()

def load_equipment() -> pd.DataFrame:
    init_equipment_db()
    seed_initial_equipment()  # เพิ่มบรรทัดนี้ - จะ seed ครั้งเดียวถ้ายังไม่มีข้อมูล
    with get_equipment_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                id,
                name,
                pgh_code,
                serial_number,
                last_maintenance_date,
                maintenance_note
            FROM equipment
            ORDER BY name
            """,
            conn,
        )
    return df

def add_equipment(name: str, pgh: str, sn: str) -> None:
    init_equipment_db()  # เพิ่มบรรทัดนี้
    with get_equipment_conn() as conn:
        conn.execute(
            "INSERT INTO equipment (name, pgh_code, serial_number) VALUES (?, ?, ?)",
            (name.strip(), pgh.strip(), sn.strip()),
        )
        conn.commit()

def delete_equipment(equipment_id: int) -> None:
    init_equipment_db()  # เพิ่มบรรทัดนี้
    with get_equipment_conn() as conn:
        conn.execute("DELETE FROM equipment WHERE id=?", (equipment_id,))
        conn.commit()

def update_maintenance(equipment_id: int, maint_date: date, note: str) -> None:
    init_equipment_db()  # เพิ่มบรรทัดนี้
    with get_equipment_conn() as conn:
        conn.execute(
            "UPDATE equipment SET last_maintenance_date=?, maintenance_note=? WHERE id=?",
            (maint_date.isoformat(), note.strip() if note else None, equipment_id),
        )
        conn.commit()

def add_daily_check(equipment_id: int, status: str, borrowed_to: str, remark: str, checked_by: str) -> None:
    init_equipment_db()  # เพิ่มบรรทัดนี้
    now = datetime.now()
    check_date = now.date().isoformat()
    check_time = now.strftime("%H:%M:%S")
    
    with get_equipment_conn() as conn:
        conn.execute(
            """
            INSERT INTO daily_checks 
            (equipment_id, check_date, check_time, status, borrowed_to, remark, checked_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                equipment_id,
                check_date,
                check_time,
                status,
                borrowed_to.strip() if borrowed_to else None,
                remark.strip() if remark else None,
                checked_by.strip() if checked_by else None,
            ),
        )
        conn.commit()

def get_daily_checks(start_date: date, end_date: date) -> pd.DataFrame:
    init_equipment_db()  # เพิ่มบรรทัดนี้
    with get_equipment_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                e.name as equipment_name,
                e.pgh_code,
                e.serial_number,
                dc.check_date,
                dc.check_time,
                dc.status,
                dc.borrowed_to,
                dc.remark,
                dc.checked_by
            FROM daily_checks dc
            JOIN equipment e ON dc.equipment_id = e.id
            WHERE dc.check_date BETWEEN ? AND ?
            ORDER BY dc.check_date DESC, dc.check_time DESC
            """,
            conn,
            params=(start_date.isoformat(), end_date.isoformat()),
        )
    return df

def get_latest_status() -> pd.DataFrame:
    """ดึงสถานะล่าสุดของแต่ละเครื่อง"""
    init_equipment_db()
    with get_equipment_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                e.id,
                e.name,
                e.pgh_code,
                e.serial_number,
                e.last_maintenance_date,
                dc.check_date,
                dc.status,
                dc.borrowed_to,
                dc.remark
            FROM equipment e
            LEFT JOIN (
                SELECT equipment_id, check_date, status, borrowed_to, remark
                FROM daily_checks
                WHERE id IN (
                    SELECT MAX(id)
                    FROM daily_checks
                    GROUP BY equipment_id
                )
            ) dc ON e.id = dc.equipment_id
            ORDER BY e.name
            """,
            conn,
        )
    return df

# ==============================
# 4) EQUIPMENT UI HELPERS
# ==============================
def status_badge_html(status: str) -> str:
    badges = {
        "พร้อมใช้": "badge-ready",
        "ไม่พร้อมใช้": "badge-not-ready",
        "วอร์ดอื่นยืม": "badge-borrowed",
        "รอซ่อม": "badge-not-ready",
    }
    badge_class = badges.get(status, "")
    icon = "✅" if status == "พร้อมใช้" else "❌" if status == "รอซ่อม" else "📤" if status == "วอร์ดอื่นยืม" else "⚠️"
    return f'<span class="status-badge {badge_class}">{icon} {status}</span>'

# ==============================
# 5) EQUIPMENT PAGES
# ==============================
def equipment_dashboard_page() -> None:
    st.title("📊 Dashboard - เครื่องมืออุปกรณ์")
    
    df_equipment = load_equipment()
    df_status = get_latest_status()
    
    # แสดงข้อความถ้ามีการ import ข้อมูลเริ่มต้น
    if len(df_equipment) == 22 and len(df_status[df_status["status"].notna()]) == 0:
        st.info("✅ โหลดรายการเครื่องมือ 22 รายการเรียบร้อยแล้ว เริ่มตรวจสอบรายวันได้เลย")
    
    # Metrics
    total = len(df_equipment)
    ready = len(df_status[df_status["status"] == "พร้อมใช้"])
    borrowed = len(df_status[df_status["status"] == "วอร์ดอื่นยืม"])
    not_ready = len(df_status[df_status["status"].isin(["ไม่พร้อมใช้", "รอซ่อม"])])
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>{total}</h3>
                <p>เครื่องมือทั้งหมด</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with c2:
        st.markdown(
            f"""
            <div class="metric-card green">
                <h3>{ready}</h3>
                <p>✅ พร้อมใช้</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with c3:
        st.markdown(
            f"""
            <div class="metric-card blue">
                <h3>{borrowed}</h3>
                <p>📤 วอร์ดอื่นยืม</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with c4:
        st.markdown(
            f"""
            <div class="metric-card red">
                <h3>{not_ready}</h3>
                <p>❌ ไม่พร้อมใช้</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    st.divider()
    
    # สถานะปัจจุบัน
    st.subheader("📋 สถานะปัจจุบันของเครื่องมือ")
    
    if df_status.empty:
        st.info("ยังไม่มีข้อมูลการตรวจสอบ")
    else:
        for _, row in df_status.iterrows():
            st.markdown('<div class="equipment-card">', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                st.markdown(f"**{row['name']}**")
                st.caption(f"PGH: {row['pgh_code']} | SN: {row['serial_number']}")
            
            with col2:
                if pd.notna(row['status']):
                    st.markdown(status_badge_html(row['status']), unsafe_allow_html=True)
                    if row['status'] == "วอร์ดอื่นยืม" and pd.notna(row['borrowed_to']):
                        st.caption(f"ยืมไป: {row['borrowed_to']}")
                else:
                    st.markdown('<span class="status-badge badge-gray">ยังไม่ได้ตรวจสอบ</span>', unsafe_allow_html=True)
            
            with col3:
                if pd.notna(row['last_maintenance_date']):
                    maint_date = pd.to_datetime(row['last_maintenance_date']).date()
                    days_since = (date.today() - maint_date).days
                    st.caption(f"🔧 Maintenance ล่าสุด:")
                    st.caption(f"{maint_date.strftime('%d/%m/%Y')} ({days_since} วันที่แล้ว)")
            
            if pd.notna(row['remark']) and row['remark']:
                st.caption(f"💬 หมายเหตุ: {row['remark']}")
            
            st.markdown('</div>', unsafe_allow_html=True)

def equipment_daily_check_page() -> None:
    st.title("✅ ตรวจสอบรายวัน")
    st.caption(f"วันที่: {date.today().strftime('%d/%m/%Y')}")
    
    df_equipment = load_equipment()
    
    if df_equipment.empty:
        st.warning("⚠️ ยังไม่มีเครื่องมือในระบบ กรุณาเพิ่มเครื่องมือในหน้า 'จัดการเครื่องมือ' ก่อน")
        return
    
    st.divider()
    st.info(f"📋 เครื่องมือทั้งหมด {len(df_equipment)} รายการ - เลือกสถานะแล้วกดบันทึกได้เลย")
    
    # แสดงเครื่องมือทั้งหมดพร้อมฟอร์มในหน้าเดียว
    for idx, equipment in df_equipment.iterrows():
        with st.container():
            st.markdown('<div class="equipment-card">', unsafe_allow_html=True)
            
            # Header
            col_name, col_action = st.columns([3, 1])
            with col_name:
                st.markdown(f"### {equipment['name']}")
                st.caption(f"PGH: {equipment['pgh_code']} | SN: {equipment['serial_number']}")
            
            # Form สำหรับเครื่องนี้
            with st.form(key=f"form_{equipment['id']}"):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    status = st.radio(
                        "สถานะ",
                        ["พร้อมใช้", "ไม่พร้อมใช้", "วอร์ดอื่นยืม", "รอซ่อม"],
                        key=f"status_{equipment['id']}",
                        horizontal=True,
                        index=0
                    )
                
                with col2:
                    if status == "วอร์ดอื่นยืม":
                        borrowed_to = st.text_input("ยืมไปที่", key=f"borrowed_{equipment['id']}")
                    else:
                        borrowed_to = ""
                    
                    remark = st.text_input("หมายเหตุ", key=f"remark_{equipment['id']}")
                
                with col3:
                    st.write("")  # spacer
                    st.write("")  # spacer
                    submitted = st.form_submit_button("💾 บันทึก", use_container_width=True, type="primary")
                
                if submitted:
                    try:
                        add_daily_check(int(equipment['id']), status, borrowed_to, remark, "System")
                        st.success(f"✅ บันทึก '{equipment['name']}' เรียบร้อย")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ ผิดพลาด: {e}")
            
            st.markdown('</div>', unsafe_allow_html=True)
            st.divider()

def equipment_manage_page() -> None:
    st.title("⚙️ จัดการเครื่องมือ")
    
    tab1, tab2, tab3 = st.tabs(["📝 เพิ่มเครื่องมือใหม่", "🔧 บันทึก Maintenance", "🗑️ ลบเครื่องมือ"])
    
    with tab1:
        st.subheader("เพิ่มเครื่องมือใหม่")
        
        with st.form("add_equipment_form"):
            name = st.text_input("ชื่อเครื่องมือ *", "")
            pgh = st.text_input("รหัส PGH", "")
            sn = st.text_input("Serial Number", "")
            
            submitted = st.form_submit_button("➕ เพิ่มเครื่องมือ", use_container_width=True)
        
        if submitted:
            if not name.strip():
                st.error("❌ กรุณาระบุชื่อเครื่องมือ")
            else:
                try:
                    add_equipment(name, pgh, sn)
                    st.success(f"✅ เพิ่มเครื่องมือ '{name}' เรียบร้อยแล้ว")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        
        st.divider()
        st.subheader("รายการเครื่องมือทั้งหมด")
        df = load_equipment()
        if not df.empty:
            st.dataframe(
                df[["name", "pgh_code", "serial_number", "last_maintenance_date"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("ยังไม่มีเครื่องมือในระบบ")
    
    with tab2:
        st.subheader("บันทึกวันที่บริษัทมา Maintenance")
        
        df_equipment = load_equipment()
        
        if df_equipment.empty:
            st.info("ยังไม่มีเครื่องมือในระบบ")
        else:
            with st.form("maintenance_form"):
                equipment_options = [f"{row['name']} (PGH: {row['pgh_code']})" for _, row in df_equipment.iterrows()]
                selected_idx = st.selectbox("เลือกเครื่องมือ", range(len(equipment_options)), format_func=lambda x: equipment_options[x])
                
                maint_date = st.date_input("วันที่ Maintenance", date.today())
                maint_note = st.text_area(
                    "หมายเหตุ (บันทึกความผิดปกติหลังช่างมาดู หรือรายละเอียดการซ่อม)",
                    "",
                    height=120,
                )
                
                submitted = st.form_submit_button("💾 บันทึก Maintenance", use_container_width=True)
            
            if submitted:
                try:
                    equipment_id = df_equipment.iloc[selected_idx]["id"]
                    update_maintenance(equipment_id, maint_date, maint_note)
                    st.success(f"✅ บันทึก Maintenance เรียบร้อยแล้ว")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
    
    with tab3:
        st.subheader("ลบเครื่องมือ")
        st.warning("⚠️ การลบจะลบข้อมูลการตรวจสอบทั้งหมดของเครื่องนี้ด้วย")
        
        df_equipment = load_equipment()
        
        if df_equipment.empty:
            st.info("ยังไม่มีเครื่องมือในระบบ")
        else:
            with st.form("delete_equipment_form"):
                equipment_options = [f"{row['name']} (PGH: {row['pgh_code']})" for _, row in df_equipment.iterrows()]
                selected_idx = st.selectbox("เลือกเครื่องมือที่จะลบ", range(len(equipment_options)), format_func=lambda x: equipment_options[x])
                
                confirm = st.checkbox("ยืนยันการลบ")
                submitted = st.form_submit_button("🗑️ ลบเครื่องมือ", use_container_width=True, type="primary")
            
            if submitted:
                if not confirm:
                    st.error("❌ กรุณาเช็คยืนยันการลบ")
                else:
                    try:
                        equipment_id = df_equipment.iloc[selected_idx]["id"]
                        equipment_name = df_equipment.iloc[selected_idx]["name"]
                        delete_equipment(equipment_id)
                        st.success(f"✅ ลบเครื่องมือ '{equipment_name}' เรียบร้อยแล้ว")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาด: {e}")

def equipment_report_page() -> None:
    st.title("📄 รายงาน")
    
    # เลือกช่วงเวลา
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input("วันที่เริ่มต้น", date.today().replace(day=1))
    
    with col2:
        end_date = st.date_input("วันที่สิ้นสุด", date.today())
    
    if start_date > end_date:
        st.error("❌ วันที่เริ่มต้นต้องน้อยกว่าหรือเท่ากับวันที่สิ้นสุด")
        return
    
    df_checks = get_daily_checks(start_date, end_date)
    
    st.divider()
    
    if df_checks.empty:
        st.info(f"ไม่มีข้อมูลการตรวจสอบในช่วง {start_date.strftime('%d/%m/%Y')} ถึง {end_date.strftime('%d/%m/%Y')}")
    else:
        st.subheader(f"📊 สรุปการตรวจสอบ ({start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')})")
        
        # สถิติ
        total_checks = len(df_checks)
        ready_count = len(df_checks[df_checks["status"] == "พร้อมใช้"])
        ready_pct = (ready_count / total_checks * 100) if total_checks > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("จำนวนครั้งที่ตรวจสอบ", total_checks)
        m2.metric("พร้อมใช้", ready_count)
        m3.metric("% พร้อมใช้", f"{ready_pct:.1f}%")
        
        st.divider()
        
        # แสดงตาราง
        st.subheader("📋 รายละเอียดการตรวจสอบ")
        
        # จัดรูปแบบวันที่
        df_display = df_checks.copy()
        df_display["check_date"] = pd.to_datetime(df_display["check_date"]).dt.strftime("%d/%m/%Y")
        
        # ไม่แสดงคอลัมน์ checked_by
        display_cols = [
            "equipment_name",
            "pgh_code",
            "check_date",
            "check_time",
            "status",
            "borrowed_to",
            "remark",
        ]
        
        st.dataframe(
            df_display[display_cols],
            use_container_width=True,
            hide_index=True,
        )
        
        # Export
        st.divider()
        st.subheader("⬇️ ดาวน์โหลดรายงาน")
        
        # สร้าง Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_display[display_cols].to_excel(writer, sheet_name="Daily_Checks", index=False)
        output.seek(0)
        excel_data = output.getvalue()
        
        st.download_button(
            "📥 ดาวน์โหลด Excel",
            data=excel_data,
            file_name=f"รายงานตรวจสอบเครื่องมือ_{start_date}_{end_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ==============================
# 6) PREPARE DATA - EMERGENCY CART
# ==============================
df_items = load_items()

# Defensive: ensure expected columns exist
for col in ["Item_Name", "Stock", "Current_Stock", "EXP_Date"]:
    if col not in df_items.columns:
        st.error(f"❌ ข้อมูลขาดคอลัมน์ที่จำเป็น: {col}")
        st.stop()

# Parse EXP_Date (accept both dd/mm/YYYY and YYYY-mm-dd)
exp_ts = pd.to_datetime(df_items["EXP_Date"], errors="coerce", format="mixed", dayfirst=True)
df_items["EXP_Date_ts"] = exp_ts

today = pd.Timestamp.today().normalize()
df_items["Days_to_Expire"] = (df_items["EXP_Date_ts"] - today).dt.days

# Identify ETT
df_items["Is_ETT"] = df_items["Item_Name"].astype(str).str.contains(
    r"\bETT\b|endotracheal", case=False, na=False
)

# Exchange due for ETT: EXP - 24 months
df_items["Exchange_Due_ts"] = pd.NaT
mask_ett = df_items["Is_ETT"] & df_items["EXP_Date_ts"].notna()
df_items.loc[mask_ett, "Exchange_Due_ts"] = df_items.loc[mask_ett, "EXP_Date_ts"] - pd.DateOffset(months=24)
df_items["Days_to_Exchange"] = (df_items["Exchange_Due_ts"] - today).dt.days

# Friendly display dates
df_items["EXP_Date"] = df_items["EXP_Date_ts"].dt.date
df_items["Exchange_Due"] = df_items["Exchange_Due_ts"].dt.date

# Sort by expiry (NaT at bottom)
df_sorted = df_items.sort_values(["EXP_Date_ts", "Item_Name"], na_position="last").reset_index(drop=True)


# ==============================
# 7) UI HELPERS - EMERGENCY CART
# ==============================
def badge_for_row(row: pd.Series) -> str:
    """Return a compact, iPad-friendly status label (no HTML)."""
    days = row.get("Days_to_Expire", None)
    cur = row.get("Current_Stock", None)

    # Unknown date
    if pd.isna(days):
        return "⚪ No EXP"

    # Stock out has priority if current stock is 0 (even if EXP is far)
    try:
        if float(cur) <= 0:
            return "❌ Out"
    except Exception:
        pass

    # Expired
    if days <= 0:
        return "🔴 EXP"

    # Expiring soon
    if 0 < days <= 30:
        return "🟡 ≤30d"

    # Low stock (optional quick cue)
    try:
        if float(cur) == 1:
            return "⚠️ Low"
    except Exception:
        pass

    return "🟢 OK"




def highlight_row(row: pd.Series):
    # Minimal highlight for readability on iPad
    days = row.get("Days_to_Expire", None)
    cur = row.get("Current_Stock", None)
    if pd.isna(days):
        return [""] * len(row)

    if days <= 0:
        return ["background-color: #ffe5e5"] * len(row)
    if 0 < days <= 30:
        return ["background-color: #fff7d6"] * len(row)

    try:
        if float(cur) <= 0:
            return ["background-color: #ffe5e5"] * len(row)
    except Exception:
        pass

    return [""] * len(row)


def make_alert_excel(sheets: list[tuple[str, pd.DataFrame]]) -> bytes:
    """
    Build an xlsx with at least 1 visible sheet to avoid:
    IndexError: At least one sheet must be visible
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        written = False
        for name, df in sheets:
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=name[:31], index=False)
                written = True

        if not written:
            pd.DataFrame({"message": ["No alerts right now 🎉"]}).to_excel(
                writer, sheet_name="README", index=False
            )

    output.seek(0)
    return output.getvalue()


# ==============================
# 8) SIDEBAR NAV + SINGLE ITEM PANEL - EMERGENCY CART
# ==============================

# 🔥 สำคัญมาก: Initialize ทั้ง 2 databases ตอนเริ่มโปรแกรม
_init_db()  # Emergency Cart DB
init_equipment_db()  # Equipment DB

st.sidebar.title("📌 เมนูหลัก")

st.sidebar.caption(f"🗄️ DB (Emergency Cart): {os.path.basename(DB_FILE)}")
st.sidebar.caption(f"🗄️ DB (Equipment): {os.path.basename(EQUIPMENT_DB)}")

if not os.path.exists(DB_FILE):
    st.sidebar.warning("⚠️ ยังไม่พบไฟล์ Emergency Cart DB (ระบบจะสร้างเมื่อเริ่มบันทึก)")
if not os.path.exists(EQUIPMENT_DB):
    st.sidebar.warning("⚠️ ยังไม่พบไฟล์ Equipment DB (ระบบจะสร้างเมื่อเริ่มบันทึก)")

with st.sidebar.expander("ℹ️ DB paths (สำหรับ debug)", expanded=False):
    st.write("**Emergency Cart DB:**")
    st.code(DB_FILE)
    st.write("มีไฟล์อยู่:", "✅" if os.path.exists(DB_FILE) else "❌")
    
    st.write("**Equipment DB:**")
    st.code(EQUIPMENT_DB)
    st.write("มีไฟล์อยู่:", "✅" if os.path.exists(EQUIPMENT_DB) else "❌")


# Main navigation
main_page = st.sidebar.radio(
    "เลือกระบบ",
    ["🚑 Emergency Cart", "🔧 เครื่องมืออุปกรณ์"],
    index=0,
)

if main_page == "🚑 Emergency Cart":
    st.sidebar.divider()
    page = st.sidebar.radio("ไปที่หน้า", ["Dashboard", "⏰ Alerts (≤30 วัน + ETT)"], index=0)

    st.sidebar.divider()
    st.sidebar.subheader("🎯 เลือกอุปกรณ์ (เลือกครั้งเดียว)")

    item_names = df_sorted["Item_Name"].dropna().astype(str).unique().tolist()
    default_idx = 0 if item_names else None

    selected_item = st.sidebar.selectbox("อุปกรณ์", item_names, index=default_idx)

    sel_row = df_sorted[df_sorted["Item_Name"] == selected_item].iloc[0] if selected_item else None

    if sel_row is not None:
        exp = sel_row.get("EXP_Date", None)
        days = sel_row.get("Days_to_Expire", None)
        stock = sel_row.get("Stock", None)
        cur = sel_row.get("Current_Stock", None)

        st.sidebar.markdown('<div class="card">', unsafe_allow_html=True)
        st.sidebar.markdown("**สรุปข้อมูล**")
        st.sidebar.markdown(f"Item: **{selected_item}**")
        st.sidebar.markdown(f"EXP: **{exp if pd.notna(exp) else '—'}**")
        st.sidebar.markdown(f"Days to expire: **{int(days) if pd.notna(days) else '—'}**")
        st.sidebar.markdown(f"Stock: **{cur} / {stock}**")
        # ETT exchange info
        if bool(sel_row.get("Is_ETT", False)):
            ex_due = sel_row.get("Exchange_Due", None)
            ex_days = sel_row.get("Days_to_Exchange", None)
            st.sidebar.markdown("---")
            st.sidebar.markdown("**ETT Exchange**")
            st.sidebar.markdown(f"Due: **{ex_due if pd.notna(ex_due) else '—'}**")
            st.sidebar.markdown(f"Days to exchange: **{int(ex_days) if pd.notna(ex_days) else '—'}**")
        st.sidebar.markdown('</div>', unsafe_allow_html=True)

    st.sidebar.divider()

    with st.sidebar.expander("🛠 แก้ไขวันหมดอายุ (EXP)", expanded=False):
        if sel_row is None:
            st.info("ยังไม่มีรายการ")
        else:
            old_exp = sel_row.get("EXP_Date", None)
            if pd.isna(old_exp) or old_exp is None:
                old_exp = date.today()

            with st.form("form_edit_exp"):
                new_exp = st.date_input("วันหมดอายุใหม่", value=pd.to_datetime(old_exp).date())
                submitted = st.form_submit_button("💾 บันทึก EXP")

            if submitted:
                try:
                    db_update_exp(selected_item, new_exp)
                    st.success("✅ บันทึกวันหมดอายุเรียบร้อยแล้ว")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ บันทึกไม่สำเร็จ: {e}")


    with st.sidebar.expander("📦 ใช้ของ / ตัด Stock", expanded=False):
        if sel_row is None:
            st.info("ยังไม่มีรายการ")
        else:
            # Re-pull from df_items (raw) to avoid stale value when sorted is old
            row_now = df_items[df_items["Item_Name"] == selected_item].iloc[0]
            base_stock = int(row_now.get("Stock", 0) or 0)
            cur_stock = int(row_now.get("Current_Stock", 0) or 0)
            st.write(f"Stock ปกติ: **{base_stock}** | คงเหลือ: **{cur_stock}**")

            with st.form("form_cut_stock"):
                qty_use = st.number_input("จำนวนที่ใช้", min_value=1, value=1, step=1)
                cut = st.form_submit_button("✅ ตัด Stock")

            if cut:
                try:
                    db_cut_stock(selected_item, int(qty_use))
                    st.success(f"✅ ตัด Stock แล้ว | ใช้ไป {int(qty_use)} ชิ้น")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ ตัด Stock ไม่สำเร็จ: {e}")


    with st.sidebar.expander("🔄 รีเซ็ต Stock", expanded=False):
        if sel_row is None:
            st.info("ยังไม่มีรายการ")
        else:
            row_now = df_items[df_items["Item_Name"] == selected_item].iloc[0]
            base_stock = int(row_now.get("Stock", 0) or 0)
            cur_stock = int(row_now.get("Current_Stock", 0) or 0)
            st.write(f"Stock ปกติ: **{base_stock}** | คงเหลือ: **{cur_stock}**")

            with st.form("form_reset"):
                ok = st.form_submit_button("🔁 รีเซ็ตเป็นค่า Stock ปกติ")
            if ok:
                try:
                    base = db_reset_stock(selected_item)
                    st.success(f"✅ รีเซ็ตแล้ว (Current_Stock = {base})")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ รีเซ็ตไม่สำเร็จ: {e}")

else:  # เครื่องมืออุปกรณ์
    st.sidebar.divider()
    equipment_page = st.sidebar.radio(
        "เลือกหน้า",
        ["📊 Dashboard", "✅ ตรวจสอบรายวัน", "⚙️ จัดการเครื่องมือ", "📄 รายงาน"],
        index=0,
    )


# ==============================
# 9) MAIN PAGES - EMERGENCY CART
# ==============================
def dashboard_page() -> None:
    st.title("📋 Emergency Cart Checklist")
    st.caption("เรียงตามวันใกล้หมดอายุ • iPad-friendly view")

    expired_count = int((df_sorted["Days_to_Expire"].fillna(999999) <= 0).sum())
    near_exp_count = int(((df_sorted["Days_to_Expire"].fillna(999999) > 0) & (df_sorted["Days_to_Expire"] <= 30)).sum())
    zero_stock_count = int((pd.to_numeric(df_sorted["Current_Stock"], errors="coerce").fillna(0) <= 0).sum())
    low_stock_count = int(((pd.to_numeric(df_sorted["Current_Stock"], errors="coerce").fillna(0) == 1) & (pd.to_numeric(df_sorted["Stock"], errors="coerce").fillna(0) > 1)).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🛑 หมดอายุแล้ว", expired_count)
    c2.metric("⏳ ใกล้หมดอายุ (≤30 วัน)", near_exp_count)
    c3.metric("📦 Stock หมด", zero_stock_count)
    c4.metric("⚠️ Stock เหลือ 1 ชิ้น", low_stock_count)

    st.divider()
    bundle_status_block(df_sorted)

    st.divider()
    st.subheader("🔎 ค้นหาอุปกรณ์")
    search_text = st.text_input("พิมพ์บางส่วนของชื่อ (Item_Name)", "")

    if search_text:
        df_view = df_sorted[df_sorted["Item_Name"].astype(str).str.contains(search_text, case=False, na=False)].copy()
    else:
        df_view = df_sorted.copy()

    # Show only essential columns for iPad
    cols = ["Item_Name", "Current_Stock", "Stock", "Days_to_Expire", "EXP_Date"]
    cols = [c for c in cols if c in df_view.columns]

    df_view = df_view[cols].copy()

    # Add status badge column (HTML) for quick scan
    df_view.insert(0, "Status", df_view.apply(badge_for_row, axis=1))

    styled = df_view.style.apply(highlight_row, axis=1).format(na_rep="—")
    st.dataframe(styled, use_container_width=True, hide_index=True, column_config={"Status": st.column_config.Column(help="Status", width="small")})

    # Download current list (minimal columns)
    st.markdown("#### ⬇️ ดาวน์โหลดรายการ (หน้าปัจจุบัน)")
    xlsx = make_alert_excel([("Emergency_Cart", df_view.drop(columns=["Status"], errors="ignore"))])
    st.download_button(
        "ดาวน์โหลด Excel (รายการทั้งหมด)",
        data=xlsx,
        file_name="emergency_cart_check.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def alerts_page() -> None:
    st.title("⏰ Alerts")
    st.caption("หมดอายุ • ใกล้หมดอายุ ≤ 30 วัน • และ ETT ส่งแลก (EXP - 24 เดือน)")

    df_alert = df_sorted.copy()

    df_expired = df_alert[df_alert["Days_to_Expire"].fillna(999999) <= 0].copy()
    df_exp30 = df_alert[(df_alert["Days_to_Expire"].fillna(999999) > 0) & (df_alert["Days_to_Expire"] <= 30)].copy()

    # ETT alerts
    df_ett = df_alert[df_alert["Is_ETT"] == True].copy()
    df_ett = df_ett[df_ett["Exchange_Due_ts"].notna()].copy()
    df_ett_overdue = df_ett[df_ett["Days_to_Exchange"].fillna(999999) <= 0].copy()
    df_ett_30 = df_ett[(df_ett["Days_to_Exchange"].fillna(999999) > 0) & (df_ett["Days_to_Exchange"] <= 30)].copy()

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("🛑 Expired", len(df_expired))
    t2.metric("⚠️ Expiring ≤ 30d", len(df_exp30))
    t3.metric("🛑 ETT Exchange overdue", len(df_ett_overdue))
    t4.metric("⚠️ ETT Exchange ≤ 30d", len(df_ett_30))

    tab1, tab2, tab3 = st.tabs(["🛑 Expired", "⚠️ Expiring ≤30d", "🔁 ETT Exchange"])

    base_cols = ["Item_Name", "Current_Stock", "Stock", "Days_to_Expire", "EXP_Date"]
    base_cols = [c for c in base_cols if c in df_alert.columns]

    with tab1:
        if df_expired.empty:
            st.success("ไม่มีรายการหมดอายุ 🎉")
        else:
            st.dataframe(
                df_expired.sort_values(["Days_to_Expire", "EXP_Date_ts"])[base_cols],
                use_container_width=True,
                hide_index=True,
            )

    with tab2:
        if df_exp30.empty:
            st.success("ไม่มีรายการจะหมดอายุใน 30 วัน 👍")
        else:
            st.dataframe(
                df_exp30.sort_values(["Days_to_Expire", "EXP_Date_ts"])[base_cols],
                use_container_width=True,
                hide_index=True,
            )

    with tab3:
        ett_cols = ["Item_Name", "Current_Stock", "Stock", "Exchange_Due", "Days_to_Exchange", "EXP_Date", "Days_to_Expire"]
        ett_cols = [c for c in ett_cols if c in df_ett.columns]

        st.markdown("**🛑 เกินกำหนดส่งแลกแล้ว**")
        if df_ett_overdue.empty:
            st.success("ไม่มีรายการเกินกำหนดส่งแลก 🎉")
        else:
            st.dataframe(
                df_ett_overdue.sort_values(["Days_to_Exchange", "Exchange_Due_ts"])[ett_cols],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**⚠️ จะถึงกำหนดส่งแลกใน 30 วัน (1–30 วัน)**")
        if df_ett_30.empty:
            st.success("ไม่มีรายการจะถึงกำหนดส่งแลกใน 30 วัน 👍")
        else:
            st.dataframe(
                df_ett_30.sort_values(["Days_to_Exchange", "Exchange_Due_ts"])[ett_cols],
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    st.subheader("⬇️ ดาวน์โหลด Excel (Alerts)")

    xlsx = make_alert_excel(
        [
            ("Expired", df_expired[base_cols] if not df_expired.empty else pd.DataFrame()),
            ("Expiring_30d", df_exp30[base_cols] if not df_exp30.empty else pd.DataFrame()),
            ("ETT_Exchange_Due", df_ett_overdue[ett_cols] if not df_ett_overdue.empty else pd.DataFrame()),
            ("ETT_Exchange_30d", df_ett_30[ett_cols] if not df_ett_30.empty else pd.DataFrame()),
        ]
    )

    st.download_button(
        "🔥 ดาวน์โหลด Excel แจ้งเตือน",
        data=xlsx,
        file_name="exp_alerts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Bundle Status Dashboard
    bundle_status_block(df_items, warn_days=30)


# ==============================
# 10) MAIN ROUTING
# ==============================
if main_page == "🚑 Emergency Cart":
    if page == "Dashboard":
        dashboard_page()
    else:
        alerts_page()
else:  # เครื่องมืออุปกรณ์
    if equipment_page == "📊 Dashboard":
        equipment_dashboard_page()
    elif equipment_page == "✅ ตรวจสอบรายวัน":
        equipment_daily_check_page()
    elif equipment_page == "⚙️ จัดการเครื่องมือ":
        equipment_manage_page()
    elif equipment_page == "📄 รายงาน":
        equipment_report_page()