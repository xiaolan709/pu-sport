from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import urllib3
import os
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

if not firebase_admin._apps:
    try:
        if os.environ.get("FIREBASE_KEY_JSON"):
            key_dict = json.loads(os.environ.get("FIREBASE_KEY_JSON"))
            cred = credentials.Certificate(key_dict)
        else:
            cred = credentials.Certificate("pusport-firebase-key.json")
            
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"❌ Firebase 連線失敗: {e}")

db = firestore.client()

@app.route('/')
def home():
    return "靜宜體育館 Webhook 欄位完美對齊版運作中！"

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    parameters = query_result.get('parameters', {})
    
    # 1. 取得對話框資訊
    user_court = parameters.get('court_name', '') # 可能是 "排球場"、"籃球場"
    query_text = query_result.get('queryText', '')
    
    # 📅 智慧星期清洗
    target_day = "星期二" 
    days_list = ["星期一", "星期二", "星期三", "星期四", "星期五"]
    for d in days_list:
        if d in query_text:
            target_day = d
            break

    try:
        # 💡 關鍵修正：集合名稱改成你圖片上的 "school_schedule"，星期欄位改成 "day_of_week"
        docs = db.collection("school_schedule").where("day_of_week", "==", target_day).stream()
        
        occupied_courts = []
        
        for doc in docs:
            data = doc.to_dict()
            
            # 💡 關鍵修正：配合你資料庫的欄位名稱抓取
            db_court_type = data.get('court_type', '')   # 例如："室外排球場"
            db_court_num = data.get('court_number', '')  # 例如："3"
            db_status = data.get('status', '空堂')
            db_time = data.get('time_slot', '')          # 例如："19:00-21:00"
            
            # 組合出完整的場地名稱，方便後面比對（例如："室外排球場(3號場)"）
            full_court_name = f"{db_court_type}({db_court_num}號場)"
            
            # 智慧模糊攔截：不論問"排球場"還是"籃球場"，只要對話中提到且資料庫有符合就抓
            is_match = False
            if user_court and (user_court in db_court_type or db_court_type in user_court):
                is_match = True
            elif "排球" in query_text and "排球" in db_court_type:
                is_match = True
            elif "籃球" in query_text and "籃球" in db_court_type:
                is_match = True

            if is_match:
                if db_status != "空堂" and db_status != "NO" and db_status != "":
                    occupied_courts.append({
                        "court": full_court_name,
                        "time": db_time,
                        "status": db_status
                    })
        
        # 3. 智慧整合輸出
        if occupied_courts:
            occupied_courts.sort(key=lambda x: x['court'])
            reply_text = f"📊 幫你統整【{target_day}】全校【{user_court if user_court else '球場'}】的借用狀況如下：\n\n"
            for item in occupied_courts:
                reply_text += f"❌ {item['court']} 時段 [{item['time']}] ➔ {item['status']}\n"
            reply_text += "\n💡 沒出現在上面的其他場地編號就是空場喔！"
        else:
            reply_text = f"👍 報告！【{target_day}】的【{user_court if user_court else '球場'}】目前看起來都是空堂，可以自由使用喔！"
            
    except Exception as e:
        reply_text = f"系統在撈取資料庫時發生錯誤: {e}"

    response = {
        "fulfillmentText": reply_text
    }
    return jsonify(response)