import pandas as pd
import os

# -----------------------------------
# กำหนดพาธปลายทางให้ตรงเครื่องคุณ
# -----------------------------------
DATA_FILE = r"C:\Users\user\OneDrive - Chulalongkorn University\growth\item_ORM.csv"

# -----------------------------------
# ข้อมูลตั้งต้น (คุณสามารถเพิ่มให้ครบทั้งหมดได้ภายหลัง)
# -----------------------------------
items = [
    {"ID":1,"Item_ID":"EMB001","Item_Name":"emergency box","Item_Category":"Medicine","Unit_of_Measure":"กล่อง","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"31/03/2026","brand":"เภสัช","Bundle":"","QR code":""},
    {"ID":2,"Item_ID":"SYR003","Item_Name":"syringe 3 ml","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"24/03/2026","brand":"terumo","Bundle":"","QR code":""},
    {"ID":3,"Item_ID":"SYR005","Item_Name":"syringe 5 ml","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"13/11/2026","brand":"terumo","Bundle":"","QR code":""},
    {"ID":4,"Item_ID":"SYR010","Item_Name":"syringe 10 ml","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"24/07/2027","brand":"terumo","Bundle":"","QR code":""},
    {"ID":5,"Item_ID":"SYR120","Item_Name":"syringe 20 ml","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"01/11/2025","brand":"terumo","Bundle":"","QR code":""},
    {"ID":10,"Item_ID":"SYR150","Item_Name":"syringe 50 ml","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":3,"MinStock":1,"Current_Stock":3,"EXP_Date":"01/11/2026","brand":"terumo","Bundle":"","QR code":""},
    {"ID":13,"Item_ID":"IVC118","Item_Name":"IV cath No. 18 green","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"30/09/2027","brand":"terumo","Bundle":"","QR code":""},
    {"ID":18,"Item_ID":"IVC120","Item_Name":"IV cath No. 20 pink","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"30/11/2025","brand":"terumo","Bundle":"","QR code":""},
    {"ID":23,"Item_ID":"IVC122","Item_Name":"IV cath No. 22 blue","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"28/02/2030","brand":"terumo","Bundle":"","QR code":""},
    {"ID":28,"Item_ID":"IVC124","Item_Name":"IV cath No. 24 yellow","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"31/05/2026","brand":"terumo","Bundle":"","QR code":""},
    {"ID":33,"Item_ID":"NEEDLE20","Item_Name":"needle No. 20 yellow","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":10,"MinStock":1,"Current_Stock":10,"EXP_Date":"01/06/2027","brand":"agani","Bundle":"","QR code":""},
    {"ID":34,"Item_ID":"NEEDLE21","Item_Name":"needle No. 21 green","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":10,"MinStock":1,"Current_Stock":10,"EXP_Date":"31/07/2027","brand":"nipro","Bundle":"","QR code":""},
    {"ID":35,"Item_ID":"NEEDLE23","Item_Name":"needle No. 23 blue","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":10,"MinStock":1,"Current_Stock":10,"EXP_Date":"01/04/2027","brand":"agani","Bundle":"","QR code":""},
    {"ID":36,"Item_ID":"NSS005","Item_Name":"NSS 5 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":10,"MinStock":1,"Current_Stock":10,"EXP_Date":"01/04/2026","brand":"thai nakorn","Bundle":"","QR code":""},
    {"ID":37,"Item_ID":"STW10","Item_Name":"Sterile water 10 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":10,"MinStock":1,"Current_Stock":10,"EXP_Date":"15/01/2028","brand":"thai nakorn","Bundle":"","QR code":""},
    {"ID":38,"Item_ID":"ALCPAD","Item_Name":"alcohol pad","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":20,"MinStock":1,"Current_Stock":20,"EXP_Date":"10/07/2026","brand":"pose","Bundle":"","QR code":""},
    {"ID":39,"Item_ID":"TG6X7","Item_Name":"tegaderm 6*7","Item_Category":"Wound Care","Unit_of_Measure":"แผ่น","Stock":5,"MinStock":1,"Current_Stock":4,"EXP_Date":"10/09/2026","brand":"terumo","Bundle":"","QR code":""},
    {"ID":40,"Item_ID":"AMBUBAG","Item_Name":"Ambu bag","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"02/12/2025","brand":"ศูนย์เครื่องมือแพทย์","Bundle":"airway","QR code":""},
    {"ID":41,"Item_ID":"ADULTMASK","Item_Name":"adult mask","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"02/12/2025","brand":"pgh","Bundle":"airway","QR code":""},
    {"ID":42,"Item_ID":"NPOPWA","Item_Name":"nasopharyngeal airway","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"08/04/2026","brand":"pgh","Bundle":"airway","QR code":""},
    {"ID":43,"Item_ID":"OROPWA","Item_Name":"oropharyngeal airway","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"08/04/2026","brand":"pgh","Bundle":"airway","QR code":""},
    {"ID":44,"Item_ID":"NONSTERGLOVE","Item_Name":"non-sterile glove","Item_Category":"PPE","Unit_of_Measure":"กล่อง","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"01/06/2027","brand":"pgh","Bundle":"","QR code":""},
    {"ID":45,"Item_ID":"KIDTRAYM","Item_Name":"kidney tray (medium)","Item_Category":"General Supplies","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"04/04/2026","brand":"Orm","Bundle":"","QR code":""},
    {"ID":46,"Item_ID":"SCATH112","Item_Name":"suction cath No. 12","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":3,"MinStock":1,"Current_Stock":2,"EXP_Date":"19/08/2026","brand":"Tg","Bundle":"","QR code":""},
    {"ID":49,"Item_ID":"SCATH114","Item_Name":"suction cath No. 14","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":3,"MinStock":1,"Current_Stock":4,"EXP_Date":"08/02/2027","brand":"pgh","Bundle":"","QR code":""},
    {"ID":52,"Item_ID":"LABLADE2","Item_Name":"laryngo blade No. 2","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"07/12/2025","brand":"Cssd","Bundle":"airway","QR code":""},
    {"ID":53,"Item_ID":"LABLADE3","Item_Name":"laryngo blade No. 3","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"06/04/2026","brand":"Cssd","Bundle":"airway","QR code":""},
    {"ID":54,"Item_ID":"LABLADE4","Item_Name":"laryngo blade No.4","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"06/04/2026","brand":"Cssd","Bundle":"airway","QR code":""},
    {"ID":55,"Item_ID":"KYJELLY","Item_Name":"KY jelly","Item_Category":"Medical Consumables","Unit_of_Measure":"หลอด","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"01/01/2026","brand":"pgh","Bundle":"airway","QR code":""},
    {"ID":56,"Item_ID":"STERGLOVE65","Item_Name":"Sterile grove No. 6.5","Item_Category":"PPE","Unit_of_Measure":"คู่","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"01/06/2026","brand":"pgh","Bundle":"","QR code":""},
    {"ID":57,"Item_ID":"STERGLOVE70","Item_Name":"Sterile grove No. 7.0","Item_Category":"PPE","Unit_of_Measure":"คู่","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"01/06/2026","brand":"pgh","Bundle":"","QR code":""},
    {"ID":58,"Item_ID":"STERGLOVE75","Item_Name":"Sterile grove No. 7.5","Item_Category":"PPE","Unit_of_Measure":"คู่","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"01/01/2027","brand":"pgh","Bundle":"","QR code":""},
    {"ID":59,"Item_ID":"HOLESHEET","Item_Name":"hole sheet","Item_Category":"Draping & Covers","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"28/03/2027","brand":"TG","Bundle":"","QR code":""},
    {"ID":60,"Item_ID":"ETUBE160","Item_Name":"Endotracheal tube No. 6.0","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"01/08/2027","brand":"portex","Bundle":"airway","QR code":""},
    {"ID":62,"Item_ID":"ETUBE165","Item_Name":"Endotracheal tube No. 6.5","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"06/07/2027","brand":"portex","Bundle":"airway","QR code":""},
    {"ID":64,"Item_ID":"ETUBE170","Item_Name":"Endotracheal tube No. 7","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"14/04/2027","brand":"portex","Bundle":"airway","QR code":""},
    {"ID":66,"Item_ID":"ETUBE175","Item_Name":"Endotracheal tube No. 7.5","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"18/06/2027","brand":"portex","Bundle":"airway","QR code":""},
    {"ID":68,"Item_ID":"ETUBE180","Item_Name":"Endotracheal tube No. 8","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"03/07/2027","brand":"portex","Bundle":"airway","QR code":""},
    {"ID":70,"Item_ID":"STYL011","Item_Name":"stylet","Item_Category":"Respiratory","Unit_of_Measure":"ชิ้น","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"07/12/2025","brand":"pgh","Bundle":"airway","QR code":""},
    {"ID":73,"Item_ID":"NSS11000","Item_Name":"NaCl 1000 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"04/05/2028","brand":"Thai ossuka","Bundle":"IV","QR code":""},
    {"ID":75,"Item_ID":"D5W1500","Item_Name":"5% DW 500 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"13/01/2028","brand":"thai nakorn","Bundle":"IV","QR code":""},
    {"ID":77,"Item_ID":"D5W1250","Item_Name":"5% DW 250ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"24/11/2027","brand":"Ghp","Bundle":"IV","QR code":""},
    {"ID":79,"Item_ID":"D5W1100","Item_Name":"5% DW 100 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"25/04/2027","brand":"thai nakorn","Bundle":"IV","QR code":""},
    {"ID":81,"Item_ID":"NSS100","Item_Name":"NaCl 100 ml","Item_Category":"Solution & Fluid","Unit_of_Measure":"ขวด/ml","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"10/07/2027","brand":"thai nakorn","Bundle":"IV","QR code":""},
    {"ID":82,"Item_ID":"EXTSHORT1","Item_Name":"extension tube สั้น","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":3,"EXP_Date":"25/07/2027","brand":"pps","Bundle":"","QR code":""},
    {"ID":84,"Item_ID":"EXTLONG1","Item_Name":"extension tube ยาว","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":5,"EXP_Date":"27/07/2027","brand":"pps","Bundle":"","QR code":""},
    {"ID":86,"Item_ID":"THREEWAY1","Item_Name":"three-way","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"29/07/2027","brand":"bd","Bundle":"","QR code":""},
    {"ID":88,"Item_ID":"IVSET1","Item_Name":"IV set","Item_Category":"IV & Infusion","Unit_of_Measure":"ชุด","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"31/07/2027","brand":"meditek","Bundle":"","QR code":""},
    {"ID":90,"Item_ID":"MICRODRIP","Item_Name":"microdrip","Item_Category":"IV & Infusion","Unit_of_Measure":"ชิ้น","Stock":2,"MinStock":1,"Current_Stock":2,"EXP_Date":"02/08/2027","brand":"meditek","Bundle":"","QR code":""},
    {"ID":91,"Item_ID":"STERILECAP1","Item_Name":"sterile cap","Item_Category":"Medical Consumables","Unit_of_Measure":"ชิ้น","Stock":5,"MinStock":1,"Current_Stock":5,"EXP_Date":"03/08/2027","brand":"tm","Bundle":"","QR code":""},
    {"ID":96,"Item_ID":"DEFIBGEL","Item_Name":"Defib Gel","Item_Category":"Cardiac","Unit_of_Measure":"หลอด","Stock":1,"MinStock":1,"Current_Stock":1,"EXP_Date":"08/08/2027","brand":"nihon","Bundle":"CPR","QR code":""}
]

# -----------------------------------
# สร้างโฟลเดอร์ถ้ายังไม่มี (กัน error)
# -----------------------------------
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

# -----------------------------------
# สร้าง DataFrame และบันทึกเป็น CSV (UTF-8-SIG)
# -----------------------------------
df = pd.DataFrame(items)

df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

print("สร้างไฟล์ item_ORM.csv สำเร็จแล้วที่พาธ:")
print(DATA_FILE)
