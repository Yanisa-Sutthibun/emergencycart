# item_ipad_pro.py - Emergency Cart Checklist (iPad-friendly UI)
# Notes:
# - Uses CSV as the single source of truth (writes back to item_ORM.csv in the same folder).
# - Adds EXP alerts (≤30d) + ETT exchange alerts (Exchange due = EXP - 24 months; alert 30d before due).
# - iPad-friendly: fewer columns, bigger typography, sticky-ish sidebar summary, forms to avoid multi-click.
#fix ipad ui + status badge
#แก้ error ตรงที่ download

import os
import io
import hmac
import sqlite3
from datetime import date

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
        # เพิ่มได้เรื่อยๆ เช่น:
        # "bleeding": {"icon": "🩸", "name": "Bleeding Control"},
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
    # iPad แนวนอน: 2 การ์ด/แถวสวยสุด
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
    page_title="Emergency Cart Checklist",
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
    """Sidebar password gate using st.secrets['APP_PASSWORD']."""
    if "auth" not in st.session_state:
        st.session_state["auth"] = False

    if st.session_state["auth"]:
        return

    st.sidebar.header("🔐 Login")
    pw = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        secret = st.secrets.get("APP_PASSWORD", "")
        if secret and hmac.compare_digest(pw, secret):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.sidebar.error("รหัสไม่ถูกต้อง")

    st.stop()


check_password()



# ==============================
# 2) LOAD + SAVE HELPERS (SQLite)
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "item_orm.db")
LEGACY_CSV = os.path.join(BASE_DIR, "item_ORM.csv")


def _get_conn() -> sqlite3.Connection:
    # check_same_thread=False for Streamlit (single-process) convenience
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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


def load_items() -> pd.DataFrame:
    _init_db()
    _migrate_csv_to_db_if_needed()

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
# 3) PREPARE DATA
# ==============================
df_items = load_items()

# Defensive: ensure expected columns exist
for col in ["Item_Name", "Stock", "Current_Stock", "EXP_Date"]:
    if col not in df_items.columns:
        st.error(f"❌ ข้อมูลขาดคอลัมน์ที่จำเป็น: {col}")
        st.stop()

# Parse EXP_Date (accept both dd/mm/YYYY and YYYY-mm-dd)
exp_ts = pd.to_datetime(df_items["EXP_Date"], errors="coerce", dayfirst=True)
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
# 4) UI HELPERS
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
# 5) SIDEBAR NAV + SINGLE ITEM PANEL
# ==============================
st.sidebar.title("📌 เมนู")
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


# ==============================
# 6) MAIN PAGES
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
        "📥 ดาวน์โหลด Excel แจ้งเตือน",
        data=xlsx,
        file_name="exp_alerts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ===============================
    # 🏥 Bundle Status Dashboard
    # ===============================
    bundle_status_block(df_items, warn_days=30)

if page == "Dashboard":
    dashboard_page()
else:
    alerts_page()
