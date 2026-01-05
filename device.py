import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
import shutil

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="OR-Minor Equipment Check", layout="wide")

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
BACKUP_DIR = APP_DIR / "backup"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "or_equipment.db"
RETENTION_DAYS = 31

# =========================
# DB HELPERS
# =========================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        asset_code TEXT,
        serial_no TEXT,
        or_room TEXT,
        location_note TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_check (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_date TEXT NOT NULL,
        equipment_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        maintenance_date TEXT,
        damage_reason TEXT,
        remark TEXT,
        checked_by TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(check_date, equipment_id),
        FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_meta (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    """)

    conn.commit()
    conn.close()

def upsert_meta(k, v):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, v)
    )
    conn.commit()
    conn.close()

def get_meta(k):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT v FROM app_meta WHERE k=?", (k,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else None

# =========================
# BACKUP
# =========================
def backup_db(reason="auto"):
    if not DB_PATH.exists():
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB_PATH, BACKUP_DIR / f"or_equipment_{reason}_{ts}.db")

    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for f in BACKUP_DIR.glob("or_equipment_*.db"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink(missing_ok=True)

def auto_backup_once_per_day():
    today = date.today().isoformat()
    if get_meta("last_backup_date") != today:
        backup_db("auto")
        upsert_meta("last_backup_date", today)

# =========================
# DATA ACCESS
# =========================
def fetch_equipment(active_only=True):
    conn = get_conn()
    q = "SELECT * FROM equipment"
    if active_only:
        q += " WHERE active=1"
    df = pd.read_sql_query(q + " ORDER BY name", conn)
    conn.close()
    return df

def insert_equipment(name, asset, sn, room, loc):
    conn = get_conn()
    conn.execute("""
        INSERT INTO equipment(name, asset_code, serial_no, or_room, location_note, active, created_at)
        VALUES (?,?,?,?,?,1,?)
    """, (name, asset, sn, room, loc, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_equipment(eid, name, asset, sn, room, loc, active):
    conn = get_conn()
    conn.execute("""
        UPDATE equipment
        SET name=?, asset_code=?, serial_no=?, or_room=?, location_note=?, active=?
        WHERE id=?
    """, (name, asset, sn, room, loc, 1 if active else 0, eid))
    conn.commit()
    conn.close()

def upsert_daily_check(d, eid, status, mdate, reason, remark, by):
    conn = get_conn()
    conn.execute("""
        INSERT INTO daily_check
        (check_date,equipment_id,status,maintenance_date,damage_reason,remark,checked_by,updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(check_date,equipment_id) DO UPDATE SET
            status=excluded.status,
            maintenance_date=excluded.maintenance_date,
            damage_reason=excluded.damage_reason,
            remark=excluded.remark,
            checked_by=excluded.checked_by,
            updated_at=excluded.updated_at
    """, (d, eid, status, mdate, reason, remark, by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def fetch_daily_checks(d):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            e.id AS equipment_id,
            e.or_room,
            e.name,
            e.asset_code,
            e.serial_no,
            dc.status,
            dc.maintenance_date,
            dc.damage_reason,
            dc.remark,
            dc.checked_by
        FROM equipment e
        LEFT JOIN daily_check dc
          ON dc.equipment_id=e.id AND dc.check_date=?
        WHERE e.active=1
        ORDER BY e.or_room, e.name
    """, conn, params=(d,))
    conn.close()
    return df

# =========================
# INIT
# =========================
init_db()
auto_backup_once_per_day()

# =========================
# UI
# =========================
st.title("OR-Minor Equipment Check")

page = st.sidebar.radio("เมนู", ["เช็คประจำวัน", "รายการเครื่องมือ"])

# =========================
# PAGE: DAILY CHECK
# =========================
if page == "เช็คประจำวัน":
    d = st.date_input("วันที่ตรวจเช็ค", value=date.today())
    by = st.text_input("ผู้ตรวจเช็ค", key="checker")

    df = fetch_daily_checks(d.isoformat())
    df["status"] = df["status"].fillna("OK")
    df[["maintenance_date","damage_reason","remark","checked_by"]] = \
        df[["maintenance_date","damage_reason","remark","checked_by"]].fillna("")

    df = df.set_index("equipment_id")

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        key="editor",
        column_config={
            "status": st.column_config.SelectboxColumn("Status", options=["OK","NOT_OK","N/A"]),
        }
    )

    if st.button("บันทึก"):
        for eid, r in edited.iterrows():
            upsert_daily_check(
                d.isoformat(),
                int(eid),
                r["status"],
                r["maintenance_date"] or None,
                r["damage_reason"],
                r["remark"],
                r["checked_by"] or by
            )
        st.success("บันทึกเรียบร้อย")
        st.rerun()

# =========================
# PAGE: MASTER
# =========================
else:
    df = fetch_equipment(False)
    st.dataframe(df, use_container_width=True)

    st.subheader("เพิ่มเครื่องมือ")
    name = st.text_input("ชื่อ")
    asset = st.text_input("Asset")
    sn = st.text_input("Serial")
    room = st.text_input("OR ห้อง")
    loc = st.text_input("Location")

    if st.button("เพิ่ม"):
        insert_equipment(name, asset, sn, room, loc)
        st.success("เพิ่มแล้ว")
        st.rerun()
