"""
Migration Script: Import data from item_ORM.csv to Turso Database
รันสคริปต์นี้ครั้งเดียวเพื่อ import ข้อมูลทั้งหมดไป Turso
"""

import pandas as pd
from turso_wrapper import create_turso_connection
from datetime import datetime

# ==============================
# TURSO DATABASE CONFIGURATION
# ==============================

EMERGENCY_CART_URL = "libsql://emergency-cart-db-yanisa-sutthibun.aws-ap-northeast-1.turso.io"
EMERGENCY_CART_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3Njc4NTQ1NzEsImlkIjoiYzY1YmJhYWMtNzg0Zi00NDljLWEzZTMtY2MxYzg0N2U1OThhIiwicmlkIjoiNjNlNTQxZjMtNzE5OS00ODAwLWJlNWItN2YxODZiYWYxM2EzIn0.gqXzxSsozlwAHiIPv8czFuDL4zNKzMc3rqBtyYL86XG93V-gJZDxD3mwG8GTuBpSLzBR7Hpnml1QuDBt3BYrAg"

CSV_FILE = r"C:\Users\user\OneDrive - Chulalongkorn University\growth\item_ORM.csv"

def parse_date(date_str):
    """Convert DD/MM/YYYY to YYYY-MM-DD"""
    if pd.isna(date_str) or not date_str:
        return None
    try:
        # Parse DD/MM/YYYY format
        dt = datetime.strptime(str(date_str).strip(), "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        return None

def migrate_to_turso():
    """Migrate data from CSV to Turso"""
    
    print("🚀 Starting migration...")
    
    # 1. Read CSV
    print(f"📂 Reading CSV from: {CSV_FILE}")
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    except:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    
    print(f"✅ Found {len(df)} items in CSV")
    
    # 2. Connect to Turso
    print("🔗 Connecting to Turso...")
    conn = create_turso_connection(EMERGENCY_CART_URL, EMERGENCY_CART_TOKEN)
    
    # 3. Create table
    print("📊 Creating table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_name TEXT PRIMARY KEY,
            stock INTEGER NOT NULL DEFAULT 0,
            current_stock INTEGER NOT NULL DEFAULT 0,
            exp_date TEXT,
            bundle TEXT
        )
    """)
    
    # 4. Clear existing data (optional - comment out if you want to keep)
    print("🗑️  Clearing old data...")
    conn.execute("DELETE FROM items")
    
    # 5. Insert data
    print("💾 Inserting data...")
    success_count = 0
    error_count = 0
    
    for idx, row in df.iterrows():
        try:
            item_name = str(row.get('Item_Name', '')).strip()
            stock = int(row.get('Stock', 0))
            current_stock = int(row.get('Current_Stock', stock))
            exp_date = parse_date(row.get('EXP_Date', ''))
            bundle = str(row.get('Bundle', '')).strip().lower() if pd.notna(row.get('Bundle')) else ''
            
            if not item_name:
                print(f"⚠️  Skipping row {idx}: No item name")
                continue
            
            # Insert or replace
            conn.execute("""
                INSERT OR REPLACE INTO items 
                (item_name, stock, current_stock, exp_date, bundle)
                VALUES (?, ?, ?, ?, ?)
            """, (item_name, stock, current_stock, exp_date, bundle))
            
            success_count += 1
            if (success_count % 10 == 0):
                print(f"   ✓ Inserted {success_count} items...")
                
        except Exception as e:
            error_count += 1
            print(f"❌ Error on row {idx} ({item_name}): {e}")
    
    # 6. Verify
    print("\n🔍 Verifying...")
    result = conn.execute("SELECT COUNT(*) FROM items")
    count = result.fetchone()[0]
    
    conn.close()
    
    print("\n" + "="*50)
    print("✅ MIGRATION COMPLETED!")
    print("="*50)
    print(f"📊 Total items in CSV: {len(df)}")
    print(f"✅ Successfully migrated: {success_count}")
    print(f"❌ Errors: {error_count}")
    print(f"💾 Items in Turso: {count}")
    print("="*50)
    
    if count == success_count:
        print("🎉 Perfect! All data migrated successfully!")
    else:
        print(f"⚠️  Warning: Expected {success_count} items, but found {count} in database")
    
    return success_count, error_count

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║          TURSO MIGRATION SCRIPT                          ║
║   Import data from CSV to Turso Cloud Database          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    try:
        migrate_to_turso()
        print("\n✅ Ready to use! You can now run: streamlit run item.py")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\nPlease check:")
        print("1. CSV file exists at the specified path")
        print("2. Turso URL and token are correct")
        print("3. Internet connection is working")
        print("4. turso_wrapper.py is in the same folder")
