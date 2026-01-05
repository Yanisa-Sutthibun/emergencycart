import streamlit as st
import pandas as pd
import os
from io import BytesIO
import io
import hmac

def check_password():
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

# -----------------------------
# ตั้งค่าหน้า Streamlit
# -----------------------------
st.set_page_config(page_title="รายการ Check ของ", layout="wide")

# -----------------------------
# 1) หาโฟลเดอร์ที่ไฟล์ item.py อยู่
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# 2) กำหนดไฟล์ CSV ให้อยู่โฟลเดอร์เดียวกับ item.py
# -----------------------------
DATA_FILE = os.path.join(BASE_DIR, "item_ORM.csv")

# -----------------------------
# 3) ตรวจว่าไฟล์มีอยู่จริงหรือไม่
# -----------------------------
if not os.path.exists(DATA_FILE):
    st.error("❌ ไม่พบไฟล์ item_ORM.csv กรุณาวางไฟล์ไว้ในโฟลเดอร์เดียวกับ item.py")
    st.stop()

# -----------------------------
# 4) โหลดข้อมูลจาก CSV (รองรับภาษาไทย)
# -----------------------------
df_items = pd.read_csv(DATA_FILE, encoding="utf-8-sig")

# -----------------------------
# 5) แปลงวันที่ + คำนวณ Days_to_Expire
#    + เพิ่ม "วันส่งแลก" สำหรับ Endotracheal Tube (ETT)
#      กติกา: ต้องส่งแลกก่อนวันหมดอายุ 24 เดือน
#      และแจ้งเตือนล่วงหน้า 30 วันก่อนวันส่งแลก
# -----------------------------
df_items["EXP_Date_ts"] = pd.to_datetime(
    df_items["EXP_Date"],
    format="%d/%m/%Y",   # ถ้าใน CSV เป็น 2025-11-01 ให้ลบบรรทัด format ออก
    errors="coerce"
)

today = pd.Timestamp.today().normalize()
df_items["Days_to_Expire"] = (df_items["EXP_Date_ts"] - today).dt.days

# ระบุ ETT ด้วยชื่อ (ปรับ regex ได้ตามชื่อที่คุณใช้จริงในไฟล์)
df_items["Is_ETT"] = df_items["Item_Name"].astype(str).str.contains(r"\bETT\b|endotracheal", case=False, na=False)

# คำนวณวัน "ส่งแลก" = EXP - 24 เดือน (เฉพาะ ETT)
# ใช้ DateOffset เพื่อจัดการเดือน/ปีให้ถูกต้อง
df_items["Exchange_Due_ts"] = pd.NaT
df_items.loc[df_items["Is_ETT"] & df_items["EXP_Date_ts"].notna(), "Exchange_Due_ts"] = (
    df_items.loc[df_items["Is_ETT"] & df_items["EXP_Date_ts"].notna(), "EXP_Date_ts"] - pd.DateOffset(months=24)
)

df_items["Days_to_Exchange"] = (df_items["Exchange_Due_ts"] - today).dt.days
# ===============================
# เตรียม DataFrame แจ้งเตือน (GLOBAL)
# ===============================

df_expired = pd.DataFrame()
df_expiring30 = pd.DataFrame()
df_ett_due = pd.DataFrame()
df_ett_soon = pd.DataFrame()

if not df_items.empty:
    df_expired = df_items[df_items["Days_to_Expire"] <= 0]

    df_expiring30 = df_items[
        (df_items["Days_to_Expire"] > 0) &
        (df_items["Days_to_Expire"] <= 30)
    ]

    if "Is_ETT" in df_items.columns:
        df_ett_due = df_items[
            (df_items["Is_ETT"]) &
            (df_items["Days_to_Exchange"] <= 0)
        ]

        df_ett_soon = df_items[
            (df_items["Is_ETT"]) &
            (df_items["Days_to_Exchange"] > 0) &
            (df_items["Days_to_Exchange"] <= 30)
        ]

# ทำคอลัมน์วันที่สำหรับแสดงผล (date) แยกจาก *_ts
df_items["EXP_Date"] = df_items["EXP_Date_ts"].dt.date
df_items["Exchange_Due"] = df_items["Exchange_Due_ts"].dt.date

# เรียงตามวันหมดอายุจากใกล้สุดไปไกลสุด
df_sorted = df_items.sort_values("EXP_Date")

# -----------------------------
# 6) ฟังก์ชัน simple rule สำหรับไฮไลต์สี
#    Rule:
#    - ถ้า Stock == 1 และ Current_Stock == 1 → เช็คสีจากวันหมดอายุเท่านั้น
#    - ถ้าอย่างอื่น → ใช้ rule เดิม
# -----------------------------
def highlight_row(row):
    days = row["Days_to_Expire"]
    stock = row["Stock"]
    current = row["Current_Stock"]

    # handle NaN ป้องกัน error
    if pd.isna(days):
        days = 999999
    if pd.isna(stock):
        stock = 0
    if pd.isna(current):
        current = 0

    # เริ่มต้นไม่มีสี
    color = ""

    # กรณีของที่โดยระบบมีแค่ 1 ชิ้นอยู่แล้ว (stock=1 และ current=1)
    # → ใช้ rule เฉพาะวันหมดอายุ
    if (stock == 1) and (current == 1):
        if days <= 0:
            color = "#ffcccc"   # แดง: หมดอายุแล้ว
        elif days <= 30:
            color = "#fff3cd"   # เหลือง: ใกล้หมดอายุ

    else:
        # กรณีทั่วไป
        # 🔴 แดง: หมดอายุ หรือของหมด
        if (days <= 0) or (current <= 0):
            color = "#ffcccc"
        # 🟡 เหลือง: ใกล้หมดอายุ หรือ เหลือ 1 ชิ้น
        elif (days <= 30) or (current == 1):
            color = "#fff3cd"

    if color:
        return [f"background-color: {color}"] * len(row)
    else:
        return [""] * len(row)

# -----------------------------
# 7) UI หน้าเว็บ
# -----------------------------
# เมนูนำทาง (ง่าย ๆ ไฟล์เดียว)
st.sidebar.title("📌 เมนู")
page = st.sidebar.radio("ไปที่หน้า", ["Dashboard", "⏰ EXP ภายใน 30 วัน"], index=0)

if page == "Dashboard":
    st.title("📋 รายการ Check ของ")
    st.subheader("Emergency Cart")
    st.caption("เรียงตามวันใกล้หมดอายุ")
    #-------Dashboard สถานะ--------#
    expired_count = (df_sorted["Days_to_Expire"] <= 0).sum()
    near_exp_count = ((df_sorted["Days_to_Expire"] > 0) & (df_sorted["Days_to_Expire"] <= 30)).sum()
    zero_stock_count = (df_sorted["Current_Stock"] <= 0).sum()
    low_stock_count = ((df_sorted["Current_Stock"] == 1) & (df_sorted["Stock"] > 1)).sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🛑 หมดอายุแล้ว", expired_count)
    col2.metric("⏳ ใกล้หมดอายุ (≤30 วัน)", near_exp_count)
    col3.metric("📦 Stock หมด", zero_stock_count)
    col4.metric("⚠️ Stock เหลือ 1 ชิ้น", low_stock_count)
    # -----------------------------
    # สถานะความพร้อมของชุดอุปกรณ์ตาม Bundle
    # -----------------------------
    st.markdown("### สถานะความพร้อมของชุดอุปกรณ์")

    # map ชื่อ bundle -> ข้อความที่อยากแสดง
    # map ชื่อ bundle -> ข้อความที่อยากแสดง
    bundle_labels = {
        "airway": "Airway management",
        "IV": "Fluid management",
    }

    # เลือกเฉพาะแถวที่มีค่า Bundle
    df_bundle = df_items[df_items["Bundle"].notna()].copy()

    if df_bundle.empty:
        st.info("ยังไม่มีการกำหนด Bundle ในรายการอุปกรณ์")
    else:
        # แสดงสถานะทีละ Bundle
        for bundle_name, group in df_bundle.groupby("Bundle"):
            label = bundle_labels.get(bundle_name, bundle_name)

            # ไม่พร้อมใช้งาน ถ้ามีของหมด (Current_Stock<=0) หรือหมดอายุแล้ว (Days_to_Expire<=0)
            problem_items = group[(group["Current_Stock"] <= 0) | (group["Days_to_Expire"] <= 0)].copy()

            if not problem_items.empty:
                item_names = problem_items["Item_Name"].astype(str).tolist()
                st.error(
                    f"❌ {label} ไม่พร้อมใช้งาน\n\nรายการที่มีปัญหา:\n- " + "\n- ".join(item_names)
                )
            else:
                st.success(f"✅ {label} พร้อมใช้งาน")

    search_text = st.text_input("ค้นหาอุปกรณ์ (พิมพ์บางส่วนของชื่อ Item_Name)", "")

    # ถ้าไม่ใส่อะไร แสดงทั้งหมด, ถ้าใส่ให้กรองตาม Item_Name
    if search_text:
        df_display = df_sorted[
            df_sorted["Item_Name"].str.contains(search_text, case=False, na=False)
        ]
    else:
        df_display = df_sorted

    cols_to_show = [
        "Item_Name",
        "Item_Category",
        "EXP_Date",
        "Days_to_Expire",
        "Stock",
        "Current_Stock",
    ]

    styled_df = df_display[cols_to_show].style.apply(
        highlight_row, axis=1
    )
    
    DISPLAY_COLS = [
    "Item_Name",        # รู้ว่าอะไร
    "Current_Stock",    # เหลือกี่ชิ้น (ตัดสินใจทันที)
    "Stock",            # ควรมีเท่าไร
    "Days_to_Expire",  # ใกล้หมดไหม
    "EXP_Date",         # หมดวันไหน
]

    df_show = df_display[DISPLAY_COLS]
    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("**⬇️ ดาวน์โหลดรายการทั้งหมด (หน้า Dashboard)**")
    out_dash = BytesIO()
    with pd.ExcelWriter(out_dash, engine="openpyxl") as writer:
        df_display[cols_to_show].to_excel(writer, index=False, sheet_name="Emergency_Cart")
    st.download_button(
        label="⬇️ ดาวน์โหลด Excel (Dashboard)",
        data=out_dash.getvalue(),
        file_name="emergency_cart_dashboard.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


else:
    st.title("⏰ EXP ภายใน 30 วัน")
    st.caption("รายการที่หมดอายุแล้ว และรายการที่จะหมดอายุภายใน 30 วัน")

    # ใช้ df_items ที่คำนวณ Days_to_Expire แล้ว
    df_alert = df_items.copy()

    # จัดหมวด
    df_expired = df_alert[df_alert["Days_to_Expire"].fillna(999999) <= 0].copy()
    df_exp30 = df_alert[
        (df_alert["Days_to_Expire"].fillna(999999) > 0) &
        (df_alert["Days_to_Expire"].fillna(999999) <= 30)
    ].copy()

    # สรุปตัวเลข
    c1, c2, c3 = st.columns(3)
    c1.metric("🛑 หมดอายุแล้ว", len(df_expired))
    c2.metric("⚠️ จะหมดอายุ ≤ 30 วัน", len(df_exp30))
    c3.metric("📦 รายการทั้งหมด", len(df_alert))

    cols_to_show = ["Item_Name", "Item_Category", "EXP_Date", "Days_to_Expire", "Stock", "Current_Stock"]
    cols_to_show = [c for c in cols_to_show if c in df_alert.columns]

    # แสดงตาราง
    st.subheader("🛑 หมดอายุแล้ว (Days_to_Expire ≤ 0)")
    if df_expired.empty:
        st.success("ไม่มีรายการที่หมดอายุแล้ว 🎉")
    else:
        st.dataframe(
            df_expired.sort_values(["Days_to_Expire", "EXP_Date"])[cols_to_show],
            use_container_width=True,
            hide_index=True
        )

    st.subheader("⚠️ จะหมดอายุภายใน 30 วัน (1–30 วัน)")
    if df_exp30.empty:
        st.success("ไม่มีรายการที่จะหมดอายุใน 30 วัน 👍")
    else:
        st.dataframe(
            df_exp30.sort_values(["Days_to_Expire", "EXP_Date"])[cols_to_show],
            use_container_width=True,
            hide_index=True
        )


    # -----------------------------
    # แจ้งเตือนพิเศษ: ETT ต้อง "ส่งแลก" ก่อนวันหมดอายุ 24 เดือน
    # แจ้งเตือนล่วงหน้า 30 วันก่อนวันส่งแลก
    # -----------------------------
    st.divider()
    st.subheader("🔁 ETT: แจ้งเตือนวันส่งแลก (ก่อน EXP 24 เดือน)")

    # กรองเฉพาะ ETT ที่คำนวณวันส่งแลกได้
    df_ett = df_alert[df_alert.get("Is_ETT", False) == True].copy()
    df_ett = df_ett[df_ett["Exchange_Due"].notna()].copy()

    if df_ett.empty:
        st.info("ไม่พบรายการ ETT หรือยังไม่มีข้อมูลวันหมดอายุที่คำนวณวันส่งแลกได้")
    else:
        df_ett_overdue = df_ett[df_ett["Days_to_Exchange"].fillna(999999) <= 0].copy()
        df_ett_30 = df_ett[
            (df_ett["Days_to_Exchange"].fillna(999999) > 0) &
            (df_ett["Days_to_Exchange"].fillna(999999) <= 30)
        ].copy()

        e1, e2 = st.columns(2)
        e1.metric("🛑 เกินกำหนดส่งแลกแล้ว", int(len(df_ett_overdue)))
        e2.metric("⏳ จะถึงกำหนดส่งแลกใน 30 วัน", int(len(df_ett_30)))

        cols_ett = ["Item_Name", "Item_Category", "Exchange_Due", "Days_to_Exchange", "EXP_Date", "Days_to_Expire", "Stock", "Current_Stock"]
        cols_ett = [c for c in cols_ett if c in df_ett.columns]

        st.markdown("**🛑 เกินกำหนดส่งแลกแล้ว**")
        if df_ett_overdue.empty:
            st.success("ไม่มีรายการเกินกำหนดส่งแลก 🎉")
        else:
            st.dataframe(
                df_ett_overdue.sort_values(["Days_to_Exchange", "Exchange_Due"])[cols_ett],
                use_container_width=True,
                hide_index=True
            )

        st.markdown("**⚠️ จะถึงกำหนดส่งแลกใน 30 วัน (1–30 วัน)**")
        if df_ett_30.empty:
            st.success("ไม่มีรายการที่จะถึงกำหนดส่งแลกใน 30 วัน 👍")
        else:
            st.dataframe(
                df_ett_30.sort_values(["Days_to_Exchange", "Exchange_Due"])[cols_ett],
                use_container_width=True,
                hide_index=True
            )
    # -----------------------------
    # ดาวน์โหลด Excel แจ้งเตือน (เฉพาะหน้า EXP ภายใน 30 วัน)
    # -----------------------------
    dfs_to_export = []

    if not df_expired.empty:
        dfs_to_export.append(("Expired", df_expired))
    if not df_exp30.empty:
        dfs_to_export.append(("Expiring_30d", df_exp30))

    if "df_ett_overdue" in locals() and not df_ett_overdue.empty:
        dfs_to_export.append(("ETT_Exchange_Due", df_ett_overdue))
    if "df_ett_30" in locals() and not df_ett_30.empty:
        dfs_to_export.append(("ETT_Exchange_30d", df_ett_30))

    if len(dfs_to_export) == 0:
        st.caption("✅ ตอนนี้ไม่มีรายการหมดอายุ/ใกล้หมดอายุ/ใกล้ส่งแลก")
    else:
        out_alert = BytesIO()
        with pd.ExcelWriter(out_alert, engine="openpyxl") as writer:
            for name, df in dfs_to_export:
                df.to_excel(writer, sheet_name=name[:31], index=False)
        st.download_button(
            "📥 ดาวน์โหลด Excel แจ้งเตือน",
            data=out_alert.getvalue(),
            file_name="exp_alerts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
st.sidebar.header("🎯 เลือกอุปกรณ์ (เลือกครั้งเดียว)")

# ให้ใช้ df_items ที่คำนวณ Days_to_Expire แล้วจะดีมาก
# ถ้ายังไม่คำนวณ ให้ใช้ df_items / df_sorted ที่คุณมี

# ทำ list สำหรับเลือก
item_list = df_items["Item_Name"].dropna().unique().tolist()
selected_item = st.sidebar.selectbox("เลือกอุปกรณ์", item_list, key="selected_item_main")

# ดึงแถวของ item ที่เลือก (เอาอันแรกก่อน กรณีชื่อซ้ำ)
sel = df_items[df_items["Item_Name"] == selected_item].iloc[0].copy()

# แปลงวันที่ให้ดูง่าย
exp_date = sel.get("EXP_Date")
days_exp = sel.get("Days_to_Expire")

stock = int(sel.get("Stock", 0) if pd.notna(sel.get("Stock")) else 0)
current = int(sel.get("Current_Stock", 0) if pd.notna(sel.get("Current_Stock")) else 0)

st.sidebar.markdown("### 📌 สรุปข้อมูล")
st.sidebar.write(f"**Item:** {selected_item}")
st.sidebar.write(f"**EXP:** {exp_date}")
st.sidebar.write(f"**Days to expire:** {days_exp}")
st.sidebar.write(f"**Stock:** {current} / {stock}")

st.sidebar.divider()
st.sidebar.subheader("🛠 แก้ไขวันหมดอายุ (EXP)")

old_exp = sel.get("EXP_Date")
if pd.isna(old_exp):
    old_exp = pd.Timestamp.today().date()

new_exp = st.sidebar.date_input("วันหมดอายุใหม่", value=pd.to_datetime(old_exp), key="new_exp")

if st.sidebar.button("💾 บันทึกวันหมดอายุ"):
    df_items.loc[df_items["Item_Name"] == selected_item, "EXP_Date"] = pd.to_datetime(new_exp)

    df_out = df_items.copy()
    df_out["EXP_Date"] = pd.to_datetime(df_out["EXP_Date"], errors="coerce").dt.strftime("%d/%m/%Y")

    temp_file = DATA_FILE.replace(".csv", "_temp.csv")
    df_out.to_csv(temp_file, index=False, encoding="utf-8-sig")
    os.replace(temp_file, DATA_FILE)

    st.sidebar.success("✅ บันทึกวันหมดอายุเรียบร้อยแล้ว")
    st.rerun()

    # -----------------------------
# 9) Sidebar: ใช้ของ / ตัด stock
# -----------------------------
st.sidebar.divider()
st.sidebar.subheader("📦 ใช้ของ / ตัด Stock")

qty_use = st.sidebar.number_input("จำนวนที่ใช้", min_value=1, value=1, step=1, key="qty_use")

if st.sidebar.button("✅ ตัด Stock (ใช้ของ)"):
    if current <= 0:
        st.sidebar.error("❌ ของชิ้นนี้ Stock หมดแล้ว")
    elif qty_use > current:
        st.sidebar.error("❌ จำนวนที่ใช้มากกว่า Stock ปัจจุบัน")
    else:
        df_items.loc[df_items["Item_Name"] == selected_item, "Current_Stock"] = current - qty_use

        df_out = df_items.copy()
        df_out["EXP_Date"] = pd.to_datetime(df_out["EXP_Date"], errors="coerce").dt.strftime("%d/%m/%Y")
        temp_file = DATA_FILE.replace(".csv", "_temp.csv")
        df_out.to_csv(temp_file, index=False, encoding="utf-8-sig")
        os.replace(temp_file, DATA_FILE)

        st.sidebar.success(f"✅ ตัดแล้ว เหลือ {current - qty_use}")
        st.rerun()

# -----------------------------#
# Sidebar: 🔄 รีเซ็ต Stock กลับค่าเริ่มต้น
st.sidebar.divider()
st.sidebar.subheader("🔄 รีเซ็ต Stock")

if st.sidebar.button("🔁 รีเซ็ต Stock เป็นค่าเริ่มต้น"):
    df_items.loc[df_items["Item_Name"] == selected_item, "Current_Stock"] = stock

    df_out = df_items.copy()
    df_out["EXP_Date"] = pd.to_datetime(df_out["EXP_Date"], errors="coerce").dt.strftime("%d/%m/%Y")
    temp_file = DATA_FILE.replace(".csv", "_temp.csv")
    df_out.to_csv(temp_file, index=False, encoding="utf-8-sig")
    os.replace(temp_file, DATA_FILE)

    st.sidebar.success(f"✅ รีเซ็ตเป็น {stock} แล้ว")
    st.rerun()


# สร้างไฟล์ Excel ในหน่วยความจำ
