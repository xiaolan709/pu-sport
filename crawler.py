import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
import urllib3

# 停用因為忽略 SSL 憑證而產生的警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 初始化 Firebase 連線
# ==========================================
try:
    cred = credentials.Certificate("pusport-firebase-key.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("🔥 Firebase 雲端資料庫連線成功！")
except Exception as e:
    print(f"❌ Firebase 連線失敗: {e}")

# ==========================================
# 2. 定義多個場地的爬取網址與名稱
# ==========================================
target_urls = [
    {
        "name": "室內體育館",
        "url": "https://b023.pu.edu.tw/p/404-1049-20393.php?Lang=zh-tw"
    },
    {
        "name": "室外運動場",
        "url": "https://b023.pu.edu.tw/p/404-1049-20394.php?Lang=zh-tw" # 這是室外場地的網址
    }
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

total_success_count = 0

# ==========================================
# 3. 開始迴圈爬取每個網頁
# ==========================================
for target in target_urls:
    print(f"\n🌐 正在爬取【{target['name']}】即時課表...")
    
    try:
        response = requests.get(target["url"], headers=headers, verify=False)
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 找到網頁中的課表表格
        table = soup.find("table")
        if not table:
            print(f"⚠️ 在【{target['name']}】網頁中找不到表格，跳過。")
            continue
            
        rows = table.find_all("tr")
        if not rows:
            continue
            
        # 抓取第一行表頭（場地名稱）
        headers_list = [th.text.strip() for th in rows[0].find_all(["th", "td"])]
        print(f"📋 偵測到場地欄位: {headers_list}")

        # 逐行解析課表時段與場地狀態
        for row in rows[1:]:
            cols = row.find_all("td")
            if not cols:
                continue
                
            # 第一欄通常是時間/時段
            time_slot = cols[0].text.strip()
            
            # 依序抓取各場地的借用狀態
            for index, col in enumerate(cols[1:], start=1):
                if index < len(headers_list):
                    court_name = headers_list[index]  # 取得精準場地名稱（例如：羽球場、室外排球場）
                    status_text = col.text.strip()     # 取得狀態
                    
                    # 如果有人借用，我們就把他存進 Firebase
                    if status_text and status_text != "-" and status_text != "空堂":
                        court_data = {
                            "area_type": target["name"],  # 室內體育館 或 室外運動場
                            "court_name": court_name,     # 具體場地（如：羽球場、桌球教室）
                            "time_slot": time_slot,       # 時段
                            "status": status_text,        # 借用單位（如：資管男排）
                            "note": "來自靜宜體育室多網址爬蟲"
                        }
                        
                        # 存入 Firebase
                        db.collection("pu_real_schedule").add(court_data)
                        total_success_count += 1

    except Exception as e:
        print(f"❌ 爬取【{target['name']}】時發生錯誤: {e}")

print(f"\n🚀 【全數大成功】總共將 {total_success_count} 筆完整課表資料同步至 Firebase！")