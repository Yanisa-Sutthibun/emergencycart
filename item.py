# item_ipad_pro.py - Emergency Cart Checklist (iPad-friendly UI)
# Notes:
# - Uses CSV as the single source of truth (writes back to item_ORM.csv in the same folder).
# - Adds EXP alerts (≤30d) + ETT exchange alerts (Exchange due = EXP - 24 months; alert 30d before due).
# - iPad-friendly: fewer columns, bigger typography, sticky-ish sidebar summary, forms to avoid multi-click.

import os
import io
import hmac
from datetime import date

import pandas as pd
import streamlit as st


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
# 2) LOAD + SAVE HELPERS (CSV)
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "item_ORM.csv")


def save_csv(df: pd.DataFrame) -> None:
    """Atomic-ish save: write temp then replace."""
    df_out = df.copy()

    # Ensure EXP_Date saved as dd/mm/YYYY string (keep blank if NaT)
    if "EXP_Date" in df_out.columns:
        exp_dt = pd.to_datetime(df_out["EXP_Date"], errors="coerce")
        df_out["EXP_Date"] = exp_dt.dt.strftime("%d/%m/%Y")

    temp_file = DATA_FILE.replace(".csv", "_temp.csv")
    df_out.to_csv(temp_file, index=False, encoding="utf-8-sig")
    os.replace(temp_file, DATA_FILE)


def load_csv() -> pd.DataFrame:
    if not os.path.exists(DATA_FILE):
        st.error("❌ ไม่พบไฟล์ item_ORM.csv กรุณาวางไฟล์ไว้โฟลเดอร์เดียวกับไฟล์ .py")
        st.stop()
    return pd.read_csv(DATA_FILE, encoding="utf-8-sig")


# ==============================
# 3) PREPARE DATA
# ==============================
df_items = load_csv()

# Defensive: ensure expected columns exist
for col in ["Item_Name", "Stock", "Current_Stock", "EXP_Date"]:
    if col not in df_items.columns:
        st.error(f"❌ CSV ขาดคอลัมน์ที่จำเป็น: {col}")
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
            df_items.loc[df_items["Item_Name"] == selected_item, "EXP_Date"] = pd.to_datetime(new_exp).strftime("%d/%m/%Y")
            save_csv(df_items)
            st.success("✅ บันทึกวันหมดอายุเรียบร้อยแล้ว")
            st.rerun()

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
            if cur_stock <= 0:
                st.error("❌ ของชิ้นนี้ Stock หมดแล้ว")
            elif qty_use > cur_stock:
                st.error("❌ จำนวนที่ใช้มากกว่า Stock ปัจจุบัน")
            else:
                df_items.loc[df_items["Item_Name"] == selected_item, "Current_Stock"] = cur_stock - int(qty_use)
                save_csv(df_items)
                st.success(f"✅ ตัด Stock แล้ว | คงเหลือ {cur_stock - int(qty_use)}")
                st.rerun()

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
            df_items.loc[df_items["Item_Name"] == selected_item, "Current_Stock"] = base_stock
            save_csv(df_items)
            st.success(f"✅ รีเซ็ตแล้ว (Current_Stock = {base_stock})")
            st.rerun()


# ==============================
# 6) MAIN PAGES
# ==============================
def bundle_status_block(df: pd.DataFrame) -> None:
    st.markdown("### สถานะความพร้อมของชุดอุปกรณ์")

    if "Bundle" not in df.columns:
        st.info("ยังไม่มีคอลัมน์ Bundle ในไฟล์")
        return

    df_bundle = df[df["Bundle"].notna()].copy()
    if df_bundle.empty:
        st.info("ยังไม่มีการกำหนด Bundle ในรายการอุปกรณ์")
        return

    # Friendly labels (optional)
    bundle_labels = {
        "airway": "Airway management",
        "IV": "Fluid management",
        "cpr": "CPR",
    }

    # Problem definition: stock out OR expired already
    df_bundle["is_problem"] = (df_bundle["Current_Stock"].fillna(0) <= 0) | (df_bundle["Days_to_Expire"].fillna(999999) <= 0)

    for bundle_name, group in df_bundle.groupby("Bundle"):
        label = bundle_labels.get(str(bundle_name), str(bundle_name))
        problem_items = group[group["is_problem"]]

        if problem_items.empty:
            st.success(f"✅ {label} พร้อมใช้งาน")
        else:
            names = problem_items["Item_Name"].astype(str).tolist()
            st.error(
                f"❌ {label} ไม่พร้อมใช้งาน\n\n"
                f"รายการที่มีปัญหา:\n- " + "\n- ".join(names)
            )


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


if page == "Dashboard":
    dashboard_page()
else:
    alerts_page()
