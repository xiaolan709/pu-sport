import os
import requests
from bs4 import BeautifulSoup
import pdfplumber
import firebase_admin
from firebase_admin import credentials, firestore
import urllib3
import re
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 初始化 Firebase 連線
# ==========================================
cred = credentials.Certificate("pusport-firebase-key.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()
print("🔥 Firebase 連線成功！")

os.makedirs("./temp_pdfs", exist_ok=True)

# ==========================================
# 2. 自動下載 PDF 
# ==========================================
def fetch_and_parse_pu_sports():
    url = "https://b023.pu.edu.tw/p/404-1049-20393.php?Lang=zh-tw"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    print("🌐 正在爬取靜宜體育組公告網頁...")
    res = requests.get(url, headers=headers, verify=False)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, "html.parser")
    
    links = soup.find_all("a")
    pdf_tasks = []
    
    for link in links:
        href = link.get("href", "")
        text = link.get_text().strip()
        
        if ".pdf" in href.lower():
            if ("室內" not in text) and ("室內" not in href):
                if any(kw in text or kw in href for kw in ["室外", "戶外", "球場協調", "排球", "籃球"]):
                    if "籃球" in text or "排球" in text or "籃球" in href or "排球" in href:
                        if not href.startswith("http"):
                            href = "https://b023.pu.edu.tw" + href
                        pdf_tasks.append({"name": text if text else "pu_outdoor", "url": href})
            
    unique_tasks = []
    seen_urls = set()
    for task in pdf_tasks:
        if task['url'] not in seen_urls:
            seen_urls.add(task['url'])
            unique_tasks.append(task)
            
    print(f"\n🎯 篩選完畢！共鎖定 {len(unique_tasks)} 個重要課表 PDF。")
    
    for task in unique_tasks:
        print(f"📥 正在下載並精細解析: {task['name']}...")
        try:
            pdf_res = requests.get(task['url'], verify=False)
            clean_name = re.sub(r'[\/:*?"<>|]', '_', task['name'])
            temp_path = os.path.join("./temp_pdfs", f"{clean_name}.pdf")
            with open(temp_path, "wb") as f:
                f.write(pdf_res.content)
                
            parse_pdf_by_table_objects(temp_path, clean_name)
        except Exception as e:
            print(f"❌ 處理 {task['name']} 時發生錯誤: {e}")

# ==========================================
# 3. 🎯 陣列索引映射解析大腦（經 PDF 文字流嚴格對齊修正）
# ==========================================
def parse_pdf_by_table_objects(pdf_path, file_name):
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue

            raw_page_text = page.extract_text() or ""
            page_text_clean = raw_page_text.replace(" ", "").replace("\n", "")

            # 💡 【細心雙重防禦】：利用頁面絕對特徵判斷是排球還是籃球頁
            if "戶外球場協調-排球" in page_text_clean or "排球場(" in page_text_clean:
                court_type = "室外排球場"
                # 🎯 排球場原生偵測順序為極度老實的：1, 2, 3, 4, 5, 6 號場！
                court_mapping = {
                    0: "1",
                    1: "2",
                    2: "3",
                    3: "4",
                    4: "5",
                    5: "6"
                }
            else:
                court_type = "室外籃球場"
                # 🎯 籃球場原生偵測順序為交錯跳號的：1, 5, 2, 6, 3, 7, 4 號場！
                court_mapping = {
                    0: "1",
                    1: "5",
                    2: "2",
                    3: "6",
                    4: "3",
                    5: "7",
                    6: "4"
                }

            print(f"📡 幾何偵測：目前頁面經實體核心鑑定為 ➔ 【{court_type}】，將套用專屬對照表。")

            for idx, table in enumerate(tables):
                if idx not in court_mapping:
                    continue
                court_number = court_mapping[idx]
                process_clean_table(table, court_type, court_number)

# ==========================================
# 4. 🧼 資料清洗
# ==========================================
def process_clean_table(table, court_type, court_number):
    if len(table) < 2:
        return

    days = ["星期一", "星期二", "星期三", "星期四", "星期五"]

    for row in table:
        if not row:
            continue

        time_slot = str(row[0]).strip()
        if ":" not in time_slot:
            continue

        time_slot = (
            time_slot
            .replace("~", "-")
            .replace(" ", "")
        )

        for day_idx in range(5):
            col_idx = day_idx + 1
            if col_idx >= len(row):
                continue

            day = days[day_idx]
            value = row[col_idx]

            if value is None:
                value = ""

            value = (
                str(value)
                .replace("\n", "")
                .replace(" ", "")
                .strip()
            )

            if value == "":
                value = "空堂"

            if value.upper() == "NO":
                value = "禁止預約"

            save_schedule(day, time_slot, court_type, court_number, value)

def split_time_slot(time_slot):
    start_str, end_str = time_slot.split("-")
    start = datetime.strptime(start_str, "%H:%M")
    middle = start + timedelta(minutes=30)
    return (
        f"{start_str}-{middle.strftime('%H:%M')}",
        f"{middle.strftime('%H:%M')}-{end_str}"
    )

def save_schedule(day, time_slot, court_type, court_number, status):
    if "/" in status:
        teams = [
            x.strip()
            for x in status.split("/")
            if x.strip()
        ]

        if len(teams) == 2:
            first_half, second_half = split_time_slot(time_slot)
            save_to_firestore(day, first_half, court_type, court_number, teams[0])
            save_to_firestore(day, second_half, court_type, court_number, teams[1])
            return

    save_to_firestore(day, time_slot, court_type, court_number, status)
    
# ==========================================
# 5. 💾 寫入 Firestore
# ==========================================
def save_to_firestore(day, time, court_type, court_number, status):
    data = {
        "sport": "排球" if "排球" in court_type else "籃球",
        "court_number": court_number,
        "court_type": court_type,
        "day_of_week": day,
        "time_slot": time,
        "team": status,
        "web_title": "靜宜大學戶外球場課表"
    }

    doc_id = (
        f"{court_type}_{court_number}_{day}_{time}_{status}"
        .replace("/", "_")
        .replace(":", "")
        .replace("-", "_")
    )

    db.collection("training_schedule").document(doc_id).set(data)

if __name__ == "__main__":
    fetch_and_parse_pu_sports()
    print("\n🎉 終極修復版大成功！籃球(交錯映射)與排球(順序映射)已完美對齊各就各位！")