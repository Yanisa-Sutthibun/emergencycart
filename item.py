# item_cloud_safe.py - Emergency Cart Checklist + Equipment Daily Check (Streamlit Cloud-safe)
# Key changes (Cloud-safe):
# - NO hard-coded secrets/tokens in code (uses st.secrets / env vars)
# - NO network/DB calls before login gate
# - turso_wrapper is imported lazily (after login) to avoid crash-before-login
# - Removes local SQLite path checks that don't apply to Turso

import os
import io
import hmac
from datetime import date, datetime

import pandas as pd
import streamlit as st

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

.metric-card.green { background: linear-gradient(135deg, #51cf66 0%, #2b8a3e 100%); }
.metric-card.blue  { background: linear-gradient(135deg, #4dabf7 0%, #1971c2 100%); }
.metric-card.red   { background: linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%); }

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
# 1) SETTINGS (Cloud-safe)
# ==============================
def _get_setting(key: str, default: str = "", required: bool = False) -> str:
    """
    Priority:
    1) Streamlit secrets
    2) Environment variable
    3) default

    Notes:
    - Treat '', '.', 'none', 'null' as missing (to avoid libsql URL_UNDEFINED)
    """
    def _clean(v: str) -> str:
        v = (v or "").strip()
        if v.lower() in ("", ".", "none", "null"):
            return ""
        return v

    val = ""
    try:
        val = _clean(str(st.secrets.get(key, "")))
    except Exception:
        val = ""

    if not val:
        val = _clean(os.environ.get(key, ""))

    if not val:
        val = _clean(default)

    if required and not val:
        st.error(
            f"❌ Missing required setting: {key}\n\n"
            "Please set it in Streamlit Secrets (Settings → Secrets) "
            "or as an environment variable."
        )
        st.stop()

    return val


# App password (for login gate)
APP_PASSWORD = _get_setting("APP_PASSWORD", default="muke", required=False)

# Turso settings (REQUIRED)
EMERGENCY_CART_URL   = _get_setting("EMERGENCY_CART_URL", required=True)
EMERGENCY_CART_TOKEN = _get_setting("EMERGENCY_CART_TOKEN", required=True)

EQUIPMENT_URL   = _get_setting("EQUIPMENT_URL", required=True)
EQUIPMENT_TOKEN = _get_setting("EQUIPMENT_TOKEN", required=True)

ALLOW_DEMO_SEED = _get_setting("ALLOW_DEMO_SEED", default="false", required=False).lower() in ("1", "true", "yes", "y")

def _mask_url(u: str) -> str:
    # show only host-ish part
    if not u:
        return "—"
    u = u.replace("libsql://", "").replace("https://", "").replace("http://", "")
    return u.split("/")[0][:40] + ("…" if len(u.split("/")[0]) > 40 else "")

# ==============================
# 2) SIMPLE PASSWORD GATE
# ==============================
def check_password() -> None:
    if "auth" not in st.session_state:
        st.session_state["auth"] = False
    if st.session_state["auth"]:
        return

    st.sidebar.header("🔐 Login")
    pw = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        if hmac.compare_digest(pw, APP_PASSWORD):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.sidebar.error("รหัสไม่ถูกต้อง")

    st.stop()

check_password()

# ==============================
# 3) Lazy import Turso wrapper (after login)
# ==============================
@st.cache_resource
def _turso():
    """
    Import turso_wrapper lazily so Streamlit Cloud doesn't crash before login
    if dependency/file is missing.
    """
    try:
        from turso_wrapper import create_turso_connection, turso_read_sql, turso_to_sql  # noqa: F401
        return create_turso_connection, turso_read_sql, turso_to_sql
    except Exception as e:
        st.error(
            "❌ ไม่พบหรือ import 'turso_wrapper' ไม่ได้\n\n"
            "เช็คว่าไฟล์ `turso_wrapper.py` อยู่ใน repo (โฟลเดอร์เดียวกับไฟล์แอป) "
            "และ requirements.txt ติดตั้ง dependency ครบ\n\n"
            f"รายละเอียด: {e}"
        )
        st.stop()

# ==============================
# 4) TURSO CONNECTIONS
# ==============================
def _get_emergency_conn():
    create_turso_connection, _, _ = _turso()
    return create_turso_connection(EMERGENCY_CART_URL, EMERGENCY_CART_TOKEN)

def _get_equipment_conn():
    create_turso_connection, _, _ = _turso()
    return create_turso_connection(EQUIPMENT_URL, EQUIPMENT_TOKEN)

# ==============================
# 5) Emergency Cart DB funcs
# ==============================
def _init_emergency_db() -> None:
    with _get_emergency_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                item_name TEXT PRIMARY KEY,
                stock INTEGER NOT NULL DEFAULT 0,
                current_stock INTEGER NOT NULL DEFAULT 0,
                exp_date TEXT,
                bundle TEXT
            )
            """
        )
        conn.commit()

def _seed_emergency_if_enabled() -> None:
    if not ALLOW_DEMO_SEED:
        return
    with _get_emergency_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if count and count > 0:
            return
        demo_items = [
            ("Adrenaline 1mg/ml 1ml", 10, 10, "2026-12-31", "cpr"),
            ("ETT 7.0", 2, 2, "2027-03-15", "airway"),
            ("NSS 1000ml", 20, 18, "2026-09-30", "iv"),
        ]
        conn.executemany(
            "INSERT INTO items (item_name, stock, current_stock, exp_date, bundle) VALUES (?, ?, ?, ?, ?)",
            demo_items,
        )
        conn.commit()

@st.cache_data(ttl=30)
def load_items() -> pd.DataFrame:
    _init_emergency_db()
    _seed_emergency_if_enabled()

    _, turso_read_sql, _ = _turso()
    with _get_emergency_conn() as conn:
        df = turso_read_sql(
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
    if not df.empty:
        df["Item_Name"] = df["Item_Name"].astype(str).str.strip()
        df["Stock"] = pd.to_numeric(df["Stock"], errors="coerce").fillna(0).astype(int)
        df["Current_Stock"] = pd.to_numeric(df["Current_Stock"], errors="coerce").fillna(df["Stock"]).astype(int)
    return df

def db_update_exp(item_name: str, new_exp: date) -> None:
    exp_iso = pd.to_datetime(new_exp).strftime("%Y-%m-%d")
    with _get_emergency_conn() as conn:
        conn.execute("UPDATE items SET exp_date=? WHERE item_name=?", (exp_iso, item_name))
        conn.commit()

def db_cut_stock(item_name: str, qty_use: int) -> None:
    with _get_emergency_conn() as conn:
        row = conn.execute("SELECT current_stock FROM items WHERE item_name=?", (item_name,)).fetchone()
        cur = int(row[0]) if row and row[0] is not None else 0
        if cur <= 0:
            raise ValueError("Stock หมดแล้ว")
        if qty_use > cur:
            raise ValueError("จำนวนที่ใช้มากกว่า Stock ปัจจุบัน")
        conn.execute("UPDATE items SET current_stock=? WHERE item_name=?", (cur - int(qty_use), item_name))
        conn.commit()

def db_reset_stock(item_name: str) -> int:
    with _get_emergency_conn() as conn:
        row = conn.execute("SELECT stock FROM items WHERE item_name=?", (item_name,)).fetchone()
        base = int(row[0]) if row and row[0] is not None else 0
        conn.execute("UPDATE items SET current_stock=? WHERE item_name=?", (base, item_name))
        conn.commit()
    return base

# ==============================
# 6) Equipment DB funcs
# ==============================
def init_equipment_db() -> None:
    with _get_equipment_conn() as conn:
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
    init_equipment_db()
    with _get_equipment_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
        if count and count > 0:
            return
        equipment_list = [
            ("Enerjet", "pgh0853", "AD0115154"),
            ("CO2 laser Sharplan", "pgh0882", "33-121"),
        ]
        conn.executemany(
            "INSERT INTO equipment (name, pgh_code, serial_number) VALUES (?, ?, ?)",
            equipment_list
        )
        conn.commit()

@st.cache_data(ttl=30)
def load_equipment() -> pd.DataFrame:
    init_equipment_db()
    seed_initial_equipment()

    _, turso_read_sql, _ = _turso()
    with _get_equipment_conn() as conn:
        df = turso_read_sql(
            """
            SELECT
                id, name, pgh_code, serial_number, last_maintenance_date, maintenance_note
            FROM equipment
            ORDER BY name
            """,
            conn,
        )
    return df

def add_daily_check(equipment_id: int, status: str, borrowed_to: str, remark: str, checked_by: str) -> None:
    init_equipment_db()
    now = datetime.now()
    check_date = now.date().isoformat()
    check_time = now.strftime("%H:%M:%S")
    with _get_equipment_conn() as conn:
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
        conn.commit()

def add_equipment(name: str, pgh_code: str, serial_number: str) -> None:
    """เพิ่มอุปกรณ์ใหม่"""
    init_equipment_db()
    with _get_equipment_conn() as conn:
        conn.execute(
            "INSERT INTO equipment (name, pgh_code, serial_number) VALUES (?, ?, ?)",
            (name.strip(), pgh_code.strip(), serial_number.strip())
        )
        conn.commit()

def update_equipment(equipment_id: int, name: str, pgh_code: str, serial_number: str) -> None:
    """แก้ไขข้อมูลอุปกรณ์"""
    init_equipment_db()
    with _get_equipment_conn() as conn:
        conn.execute(
            "UPDATE equipment SET name=?, pgh_code=?, serial_number=? WHERE id=?",
            (name.strip(), pgh_code.strip(), serial_number.strip(), equipment_id)
        )
        conn.commit()

def delete_equipment(equipment_id: int) -> None:
    """ลบอุปกรณ์ (และประวัติการตรวจสอบทั้งหมด)"""
    init_equipment_db()
    with _get_equipment_conn() as conn:
        # ลบประวัติการตรวจสอบก่อน
        conn.execute("DELETE FROM daily_checks WHERE equipment_id=?", (equipment_id,))
        # ลบอุปกรณ์
        conn.execute("DELETE FROM equipment WHERE id=?", (equipment_id,))
        conn.commit()

def get_latest_status() -> pd.DataFrame:
    init_equipment_db()
    _, turso_read_sql, _ = _turso()
    with _get_equipment_conn() as conn:
        df = turso_read_sql(
            """
            SELECT
                e.id, e.name, e.pgh_code, e.serial_number, e.last_maintenance_date,
                dc.check_date, dc.status, dc.borrowed_to, dc.remark
            FROM equipment e
            LEFT JOIN (
                SELECT equipment_id, check_date, status, borrowed_to, remark
                FROM daily_checks
                WHERE id IN (SELECT MAX(id) FROM daily_checks GROUP BY equipment_id)
            ) dc ON e.id = dc.equipment_id
            ORDER BY e.name
            """,
            conn,
        )
    return df

# ==============================
# 7) UI helpers
# ==============================
def status_badge_html(status: str) -> str:
    badges = {
        "พร้อมใช้": "badge-ready",
        "ไม่พร้อมใช้": "badge-not-ready",
        "วอร์ดอื่นยืม": "badge-borrowed",
        "รอซ่อม": "badge-not-ready",
    }
    badge_class = badges.get(status, "")
    icon = "✅" if status == "พร้อมใช้" else "📤" if status == "วอร์ดอื่นยืม" else "❌" if status == "รอซ่อม" else "⚠️"
    return f'<span class="status-badge {badge_class}">{icon} {status}</span>'

def make_alert_excel(sheets: list[tuple[str, pd.DataFrame]]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        written = False
        for name, df in sheets:
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=name[:31], index=False)
                written = True
        if not written:
            pd.DataFrame({"message": ["No alerts right now 🎉"]}).to_excel(writer, sheet_name="README", index=False)
    output.seek(0)
    return output.getvalue()

# ==============================
# 8) Emergency Cart calculations (after login only)
# ==============================
df_items = load_items()

# Defensive
for col in ["Item_Name", "Stock", "Current_Stock", "EXP_Date"]:
    if col not in df_items.columns:
        st.error(f"❌ ข้อมูลขาดคอลัมน์ที่จำเป็น: {col}")
        st.stop()

exp_ts = pd.to_datetime(df_items["EXP_Date"], errors="coerce", format="mixed", dayfirst=True)
df_items["EXP_Date_ts"] = exp_ts
today = pd.Timestamp.today().normalize()
df_items["Days_to_Expire"] = (df_items["EXP_Date_ts"] - today).dt.days

df_items["Is_ETT"] = df_items["Item_Name"].astype(str).str.contains(r"\bETT\b|endotracheal", case=False, na=False)
df_items["Exchange_Due_ts"] = pd.NaT
mask_ett = df_items["Is_ETT"] & df_items["EXP_Date_ts"].notna()
df_items.loc[mask_ett, "Exchange_Due_ts"] = df_items.loc[mask_ett, "EXP_Date_ts"] - pd.DateOffset(months=24)
df_items["Days_to_Exchange"] = (df_items["Exchange_Due_ts"] - today).dt.days

df_items["EXP_Date"] = df_items["EXP_Date_ts"].dt.date
df_items["Exchange_Due"] = df_items["Exchange_Due_ts"].dt.date

df_sorted = df_items.sort_values(["EXP_Date_ts", "Item_Name"], na_position="last").reset_index(drop=True)

def badge_for_row(row: pd.Series) -> str:
    days = row.get("Days_to_Expire", None)
    cur = row.get("Current_Stock", None)
    if pd.isna(days):
        return "⚪ No EXP"
    try:
        if float(cur) <= 0:
            return "❌ Out"
    except Exception:
        pass
    if days <= 0:
        return "🔴 EXP"
    if 0 < days <= 30:
        return "🟡 ≤30d"
    try:
        if float(cur) == 1:
            return "⚠️ Low"
    except Exception:
        pass
    return "🟢 OK"

def highlight_row(row: pd.Series):
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

# ==============================
# 9) PAGES
# ==============================
def emergency_dashboard_page() -> None:
    st.title("📋 Emergency Cart Checklist")
    st.caption("เรียงตามวันใกล้หมดอายุ • iPad-friendly view")

    expired_count = int((df_sorted["Days_to_Expire"].fillna(999999) <= 0).sum())
    near_exp_count = int(((df_sorted["Days_to_Expire"].fillna(999999) > 0) & (df_sorted["Days_to_Expire"] <= 30)).sum())
    zero_stock_count = int((pd.to_numeric(df_sorted["Current_Stock"], errors="coerce").fillna(0) <= 0).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("🛑 หมดอายุแล้ว", expired_count)
    c2.metric("⏳ ใกล้หมดอายุ (≤30 วัน)", near_exp_count)
    c3.metric("📦 Stock หมด", zero_stock_count)

    st.divider()
    st.subheader("🔎 ค้นหาอุปกรณ์")
    search_text = st.text_input("พิมพ์บางส่วนของชื่อ (Item_Name)", "")

    df_view = df_sorted.copy()
    if search_text:
        df_view = df_view[df_view["Item_Name"].astype(str).str.contains(search_text, case=False, na=False)].copy()

    cols = ["Item_Name", "Current_Stock", "Stock", "Days_to_Expire", "EXP_Date"]
    df_view = df_view[[c for c in cols if c in df_view.columns]].copy()
    df_view.insert(0, "Status", df_view.apply(badge_for_row, axis=1))

    styled = df_view.style.apply(highlight_row, axis=1).format(na_rep="—")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("#### ⬇️ ดาวน์โหลดรายการ (หน้าปัจจุบัน)")
    xlsx = make_alert_excel([("Emergency_Cart", df_view.drop(columns=["Status"], errors="ignore"))])
    st.download_button(
        "ดาวน์โหลด Excel (รายการทั้งหมด)",
        data=xlsx,
        file_name="emergency_cart_check.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def emergency_alerts_page() -> None:
    st.title("⏰ Alerts")
    st.caption("หมดอายุ • ใกล้หมดอายุ ≤ 30 วัน • และ ETT ส่งแลก (EXP - 24 เดือน)")

    df_alert = df_sorted.copy()
    df_expired = df_alert[df_alert["Days_to_Expire"].fillna(999999) <= 0].copy()
    df_exp30 = df_alert[(df_alert["Days_to_Expire"].fillna(999999) > 0) & (df_alert["Days_to_Expire"] <= 30)].copy()

    df_ett = df_alert[df_alert["Is_ETT"] == True].copy()
    df_ett = df_ett[df_ett["Exchange_Due_ts"].notna()].copy()
    df_ett_overdue = df_ett[df_ett["Days_to_Exchange"].fillna(999999) <= 0].copy()
    df_ett_30 = df_ett[(df_ett["Days_to_Exchange"].fillna(999999) > 0) & (df_ett["Days_to_Exchange"] <= 30)].copy()

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("🛑 Expired", len(df_expired))
    t2.metric("⚠️ Expiring ≤ 30d", len(df_exp30))
    t3.metric("🛑 ETT Exchange overdue", len(df_ett_overdue))
    t4.metric("⚠️ ETT Exchange ≤ 30d", len(df_ett_30))

    base_cols = [c for c in ["Item_Name", "Current_Stock", "Stock", "Days_to_Expire", "EXP_Date"] if c in df_alert.columns]
    ett_cols = [c for c in ["Item_Name", "Current_Stock", "Stock", "Exchange_Due", "Days_to_Exchange", "EXP_Date"] if c in df_ett.columns]

    tab1, tab2, tab3 = st.tabs(["🛑 Expired", "⚠️ Expiring ≤30d", "🔁 ETT Exchange"])
    with tab1:
        st.dataframe(df_expired[base_cols], use_container_width=True, hide_index=True) if not df_expired.empty else st.success("ไม่มีรายการหมดอายุ 🎉")
    with tab2:
        st.dataframe(df_exp30[base_cols], use_container_width=True, hide_index=True) if not df_exp30.empty else st.success("ไม่มีรายการจะหมดอายุใน 30 วัน 👍")
    with tab3:
        st.markdown("**🛑 เกินกำหนดส่งแลกแล้ว**")
        st.dataframe(df_ett_overdue[ett_cols], use_container_width=True, hide_index=True) if not df_ett_overdue.empty else st.success("ไม่มีรายการเกินกำหนดส่งแลก 🎉")
        st.markdown("**⚠️ จะถึงกำหนดส่งแลกใน 30 วัน**")
        st.dataframe(df_ett_30[ett_cols], use_container_width=True, hide_index=True) if not df_ett_30.empty else st.success("ไม่มีรายการจะถึงกำหนดส่งแลกใน 30 วัน 👍")

def equipment_dashboard_page() -> None:
    st.title("📊 Dashboard - เครื่องมืออุปกรณ์")
    df_equipment = load_equipment()
    df_status = get_latest_status()

    total = len(df_equipment)
    ready = len(df_status[df_status.get("status") == "พร้อมใช้"]) if not df_status.empty else 0
    borrowed = len(df_status[df_status.get("status") == "วอร์ดอื่นยืม"]) if not df_status.empty else 0
    not_ready = len(df_status[df_status.get("status").isin(["ไม่พร้อมใช้", "รอซ่อม"])]) if not df_status.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><h3>{total}</h3><p>เครื่องมือทั้งหมด</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card green"><h3>{ready}</h3><p>✅ พร้อมใช้</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card blue"><h3>{borrowed}</h3><p>📤 วอร์ดอื่นยืม</p></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card red"><h3>{not_ready}</h3><p>❌ ไม่พร้อมใช้</p></div>', unsafe_allow_html=True)


    st.divider()
    
    # ปุ่ม Download Excel
    col_title, col_download = st.columns([3, 1])
    with col_title:
        st.subheader("📋 สถานะปัจจุบันของเครื่องมือ")
    with col_download:
        if not df_status.empty:
            # เตรียมข้อมูลสำหรับ Excel
            df_export = df_status[['name', 'pgh_code', 'serial_number', 'status', 'borrowed_to', 'remark']].copy()
            df_export.columns = ['ชื่อเครื่องมือ', 'รหัส PGH', 'Serial Number', 'สถานะ', 'ยืมไปที่', 'หมายเหตุ']
            
            # แปลงเป็น Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='สถานะอุปกรณ์')
                # Auto-adjust column width
                worksheet = writer.sheets['สถานะอุปกรณ์']
                for idx, col in enumerate(df_export.columns):
                    max_length = max(
                        df_export[col].astype(str).apply(len).max(),
                        len(col)
                    ) + 2
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
            
            buffer.seek(0)
            today_str = date.today().strftime("%Y%m%d")
            st.download_button(
                label="📥 ดาวน์โหลด Excel",
                data=buffer,
                file_name=f"equipment_status_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    st.subheader("📋 สถานะปัจจุบันของเครื่องมือ")

    if df_status.empty:
        st.info("ยังไม่มีข้อมูลการตรวจสอบ")
        return

    for _, row in df_status.iterrows():
        st.markdown('<div class="equipment-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f"**{row.get('name','-')}**")
            st.caption(f"PGH: {row.get('pgh_code','-')} | SN: {row.get('serial_number','-')}")
        with col2:
            if pd.notna(row.get("status")):
                st.markdown(status_badge_html(row["status"]), unsafe_allow_html=True)
                if row["status"] == "วอร์ดอื่นยืม" and pd.notna(row.get("borrowed_to")):
                    st.caption(f"ยืมไป: {row.get('borrowed_to')}")
            else:
                st.markdown('<span class="status-badge badge-gray">ยังไม่ได้ตรวจสอบ</span>', unsafe_allow_html=True)
        if pd.notna(row.get("remark")) and row.get("remark"):
            st.caption(f"💬 หมายเหตุ: {row.get('remark')}")
        st.markdown("</div>", unsafe_allow_html=True)

def equipment_daily_check_page() -> None:
    st.title("✅ ตรวจสอบรายวัน")
    st.caption(f"วันที่: {date.today().strftime('%d/%m/%Y')}")
    df_equipment = load_equipment()
    if df_equipment.empty:
        st.warning("⚠️ ยังไม่มีเครื่องมือในระบบ")
        return

    st.divider()
    st.info(f"📋 เครื่องมือทั้งหมด {len(df_equipment)} รายการ - เลือกสถานะแล้วกดบันทึกได้เลย")

    for _, equipment in df_equipment.iterrows():
        st.markdown('<div class="equipment-card">', unsafe_allow_html=True)
        st.markdown(f"### {equipment['name']}")
        st.caption(f"PGH: {equipment.get('pgh_code','-')} | SN: {equipment.get('serial_number','-')}")

        with st.form(key=f"form_{equipment['id']}"):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                status = st.radio(
                    "สถานะ",
                    ["พร้อมใช้", "ไม่พร้อมใช้", "วอร์ดอื่นยืม", "รอซ่อม"],
                    horizontal=True,
                    index=0,
                )
            with col2:
                borrowed_to = st.text_input("ยืมไปที่ (ถ้ามี)") if status == "วอร์ดอื่นยืม" else ""
                remark = st.text_input("หมายเหตุ")
            with col3:
                st.write("")
                submitted = st.form_submit_button("💾 บันทึก", use_container_width=True, type="primary")

            if submitted:
                try:
                    add_daily_check(int(equipment["id"]), status, borrowed_to, remark, "System")
                    st.success(f"✅ บันทึก '{equipment['name']}' เรียบร้อย")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ ผิดพลาด: {e}")

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def equipment_manage_page() -> None:
    """หน้าจัดการอุปกรณ์ (เพิ่ม/แก้ไข/ลบ)"""
    st.title("🛠️ จัดการอุปกรณ์")
    
    # โหลดข้อมูลอุปกรณ์ก่อน (ใช้ทั้งสองแท็บ)
    df_equipment = load_equipment()
    
    # แท็บสำหรับเพิ่มและแก้ไข
    tab1, tab2 = st.tabs(["➕ เพิ่มอุปกรณ์ใหม่", "📝 แก้ไข/ลบอุปกรณ์"])
    
    # แท็บ 1: เพิ่มอุปกรณ์ใหม่
    with tab1:
        st.subheader("➕ เพิ่มอุปกรณ์ใหม่")
        with st.form("add_equipment_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("ชื่อเครื่องมือ *", placeholder="เช่น BP monitor Vismo")
                new_pgh = st.text_input("รหัส PGH", placeholder="เช่น 2808")
            with col2:
                new_sn = st.text_input("Serial Number", placeholder="เช่น 11288")
            
            submitted = st.form_submit_button("✅ เพิ่มอุปกรณ์", use_container_width=True, type="primary")
            
            if submitted:
                if not new_name or not new_name.strip():
                    st.error("❌ กรุณากรอกชื่อเครื่องมือ")
                else:
                    try:
                        add_equipment(new_name, new_pgh or "", new_sn or "")
                        st.cache_data.clear()
                        st.success(f"✅ เพิ่มอุปกรณ์ '{new_name}' เรียบร้อยแล้ว")
                        st.rerun()
                    except Exception as e:
                        if "UNIQUE constraint failed" in str(e):
                            st.error(f"❌ ชื่อเครื่องมือ '{new_name}' มีอยู่ในระบบแล้ว")
                        else:
                            st.error(f"❌ เกิดข้อผิดพลาด: {e}")
    
    # แท็บ 2: แก้ไข/ลบ
    with tab2:
        st.subheader("📝 แก้ไข/ลบอุปกรณ์")
        
        if df_equipment.empty:
            st.info("ยังไม่มีอุปกรณ์ในระบบ กรุณาเพิ่มอุปกรณ์ในแท็บ 'เพิ่มอุปกรณ์ใหม่' ก่อน")
            return
        
        # แสดงรายการอุปกรณ์
        for _, equip in df_equipment.iterrows():
            with st.expander(f"🔧 {equip['name']}", expanded=False):
                st.markdown(f"**PGH:** {equip.get('pgh_code', '-')} | **SN:** {equip.get('serial_number', '-')}")
                
                # ฟอร์มแก้ไข
                with st.form(f"edit_form_{equip['id']}"):
                    st.markdown("### แก้ไขข้อมูล")
                    col1, col2 = st.columns(2)
                    with col1:
                        edit_name = st.text_input("ชื่อเครื่องมือ", value=equip['name'], key=f"name_{equip['id']}")
                        edit_pgh = st.text_input("รหัส PGH", value=equip.get('pgh_code', ''), key=f"pgh_{equip['id']}")
                    with col2:
                        edit_sn = st.text_input("Serial Number", value=equip.get('serial_number', ''), key=f"sn_{equip['id']}")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        update_btn = st.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True, type="primary")
                    with col_btn2:
                        delete_btn = st.form_submit_button("🗑️ ลบอุปกรณ์", use_container_width=True, type="secondary")
                    
                    if update_btn:
                        if not edit_name or not edit_name.strip():
                            st.error("❌ กรุณากรอกชื่อเครื่องมือ")
                        else:
                            try:
                                update_equipment(int(equip['id']), edit_name, edit_pgh or "", edit_sn or "")
                                st.cache_data.clear()
                                st.success(f"✅ แก้ไข '{edit_name}' เรียบร้อยแล้ว")
                                st.rerun()
                            except Exception as e:
                                if "UNIQUE constraint failed" in str(e):
                                    st.error(f"❌ ชื่อเครื่องมือ '{edit_name}' มีอยู่ในระบบแล้ว")
                                else:
                                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
                    
                    if delete_btn:
                        try:
                            equip_name = equip['name']  # เก็บชื่อก่อนลบ
                            delete_equipment(int(equip['id']))
                            st.cache_data.clear()
                            st.success(f"✅ ลบอุปกรณ์ '{equip_name}' เรียบร้อยแล้ว")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ ลบไม่สำเร็จ: {e}")

# ==============================
# 10) SIDEBAR NAV
# ==============================
st.sidebar.title("📌 เมนูหลัก")
st.sidebar.caption(f"🚑 Turso (Emergency): {_mask_url(EMERGENCY_CART_URL)}")
st.sidebar.caption(f"🔧 Turso (Equipment): {_mask_url(EQUIPMENT_URL)}")
st.sidebar.divider()

main_page = st.sidebar.radio("เลือกระบบ", ["🚑 Emergency Cart", "🔧 เครื่องมืออุปกรณ์"], index=0)

if main_page == "🚑 Emergency Cart":
    page = st.sidebar.radio("ไปที่หน้า", ["Dashboard", "⏰ Alerts"], index=0)

    st.sidebar.divider()
    st.sidebar.subheader("🎯 เลือกอุปกรณ์")

    item_names = df_sorted["Item_Name"].dropna().astype(str).unique().tolist()
    selected_item = st.sidebar.selectbox("อุปกรณ์", item_names, index=0 if item_names else None)

    if selected_item:
        sel_row = df_sorted[df_sorted["Item_Name"] == selected_item].iloc[0]
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
        st.sidebar.markdown("</div>", unsafe_allow_html=True)

        with st.sidebar.expander("🛠 แก้ไขวันหมดอายุ (EXP)", expanded=False):
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
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ บันทึกไม่สำเร็จ: {e}")

        with st.sidebar.expander("📦 ใช้ของ / ตัด Stock", expanded=False):
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
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ ตัด Stock ไม่สำเร็จ: {e}")

        with st.sidebar.expander("🔄 รีเซ็ต Stock", expanded=False):
            with st.form("form_reset"):
                ok = st.form_submit_button("🔁 รีเซ็ตเป็นค่า Stock ปกติ")
            if ok:
                try:
                    base = db_reset_stock(selected_item)
                    st.success(f"✅ รีเซ็ตแล้ว (Current_Stock = {base})")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ รีเซ็ตไม่สำเร็จ: {e}")

else:
    equipment_page = st.sidebar.radio("เลือกหน้า", ["📊 Dashboard", "✅ ตรวจสอบรายวัน", "🛠️ จัดการอุปกรณ์"], index=0)

# ==============================
# 11) MAIN ROUTING
# ==============================
if main_page == "🚑 Emergency Cart":
    if page == "Dashboard":
        emergency_dashboard_page()
    else:
        emergency_alerts_page()
else:
    if equipment_page == "📊 Dashboard":
        equipment_dashboard_page()
    elif equipment_page == "✅ ตรวจสอบรายวัน":
        equipment_daily_check_page()
    else:
        equipment_manage_page()