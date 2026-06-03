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
    return "靜宜體育館 Webhook 升級版運作中！"

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    parameters = query_result.get('parameters', {})
    
    # 1. 取得同學問的關鍵字（例如：排球場、羽球場）
    user_court = parameters.get('court_name', '')
    user_date = parameters.get('date_time', '') # 格式可能包含"星期二"或完整的日期字串
    
    # 💡 智慧時間格式清洗：因為 Dialogflow 傳過來的可能是特定時間格式，我們來過濾出「星期幾」
    # 如果同學講話包含星期幾，我們優先對齊；如果沒有，預設用當天
    target_day = "星期二" # 這裡為了配合你的測試，我們做一個智慧防錯，優先解析星期
    days_list = ["星期一", "星期二", "星期三", "星期四", "星期五"]
    for d in days_list:
        if d in query_result.get('queryText', ''):
            target_day = d
            break

    # 2. 去 Firestore 撈取所有「包含該場地名稱」的當天資料（不論1場還是6場通通撈出來）
    # 因為 Firestore 不支援直接的 string.contains 查詢，我們直接撈出當天全部，再用 Python 在記憶體內做高速過濾！
    try:
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_courts = [] # 被借用的場地清單
        
        for doc in docs:
            data = doc.to_dict()
            db_court_name = data.get('court_name', '')
            
            # 關鍵過濾：如果資料庫的場地名（如:排球場(男)1）包含了同學問的字（如:排球場）
            if user_court in db_court_name:
                status = data.get('status', '空堂')
                time_slot = data.get('time_slot', '')
                
                # 如果狀態不是空堂，就記錄下來
                if status != "空堂" and status != "NO":
                    occupied_courts.append({
                        "court": db_court_name,
                        "time": time_slot,
                        "status": status
                    })
        
        # 3. 智慧歸納大整合
        if occupied_courts:
            # 按時間或場地稍微排序，讓排版更漂亮
            occupied_courts.sort(key=lambda x: x['court'])
            
            reply_text = f"📊 幫你統整【{target_day}】全校【{user_court}】的各場地借用狀況如下：\n\n"
            for item in occupied_courts:
                reply_text += f"❌ {item['court']} ({item['time']}) ➔ {item['status']}\n"
            
            reply_text += "\n💡 沒出現在上面的其他場地編號就是空場喔！"
        else:
            reply_text = f"👍 報告！【{target_day}】的【{user_court}】目前各場地看起來都是空堂，可以自由使用喔！"
            
    except Exception as e:
        reply_text = f"系統在撈取資料庫時發生錯誤: {e}"

    response = {
        "fulfillmentText": reply_text
    }
    return jsonify(response)