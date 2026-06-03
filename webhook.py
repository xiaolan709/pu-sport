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
    return "靜宜體育館 Webhook 終極完成版運作中！"

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    parameters = query_result.get('parameters', {})
    
    # 1. 取得使用者對話
    query_text = query_result.get('queryText', '')
    
    # 📅 智慧星期清洗：從對話中精準判斷星期幾
    target_day = "星期二" 
    days_list = ["星期一", "星期二", "星期三", "星期四", "星期五"]
    for d in days_list:
        if d in query_text:
            target_day = d
            break

    try:
        # 💡 鎖定你剛剛重新爬好、最乾淨的 pu_real_schedule 集合！
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_courts = []
        
        for doc in docs:
            data = doc.to_dict()
            
            db_court_name = data.get('court_name', '') # 例如: "1142學期戶外籃排球場1"
            db_status = data.get('status', '空堂')
            db_time = data.get('time_slot', '')        # 例如: "15:00~16:00"
            
            # 💡 終極關鍵字雙向過濾：
            is_match = False
            
            # 如果同學問的是排球，且該資料跟排球有關（或是名字本身包含排球）
            if "排球" in query_text and "排球" in db_court_name:
                is_match = True
            # 如果同學問的是籃球，且該資料跟籃球有關
            elif "籃球" in query_text and "籃球" in db_court_name:
                is_match = True
            # 保險防禦：如果名字裡都有提到
            elif "球場" in query_text:
                is_match = True

            if is_match:
                # 過濾學校備註或空堂雜訊
                if db_status != "空堂" and db_status != "NO" and db_status != "" and "開放" not in db_status:
                    # 簡化一下場地名稱，讓 LINE 顯示得更精簡好看
                    display_name = db_court_name.replace("1142學期", "")
                    
                    occupied_courts.append({
                        "court": display_name,
                        "time": db_time,
                        "status": db_status
                    })
        
        # 3. 歸納結果
        if occupied_courts:
            # 依場地名稱排序
            occupied_courts.sort(key=lambda x: x['court'])
            
            reply_text = f"📊 幫你統整【{target_day}】全校球場的系隊佔用狀況如下：\n\n"
            for item in occupied_courts:
                reply_text += f"❌ {item['court']} ({item['time']}) ➔ {item['status']}\n"
            reply_text += "\n💡 沒出現在上面的其他場地編號就是空場喔！"
        else:
            reply_text = f"👍 報告！【{target_day}】你查詢的球場目前看起來都是空堂，可以自由使用喔！"
            
    except Exception as e:
        reply_text = f"系統在撈取資料庫時發生錯誤: {e}"

    response = {
        "fulfillmentText": reply_text
    }
    return jsonify(response)