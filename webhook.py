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
            cred = credentials.Certificate(json.loads(os.environ.get("FIREBASE_KEY_JSON")))
        else:
            cred = credentials.Certificate("pusport-firebase-key.json")
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Firebase initialization failed: {e}")

db = firestore.client()

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    query_text = query_result.get('queryText', '')
    
    # 📅 1. 智慧星期清洗
    target_day = "星期二"
    for d in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        if d in query_text:
            target_day = d
            break

    # ⏰ 2. 智慧時段清洗
    target_time = "19:00"
    time_rules = {"15": "15:00", "16": "16:00", "17": "17:00", "18": "18:00", "19": "19:00", "20": "20:00", "21": "21:00",
                  "3點": "15:00", "4點": "16:00", "5點": "17:00", "6點": "18:00", "7點": "19:00", "8點": "20:00", "9點": "21:00"}
    for key, val in time_rules.items():
        if key in query_text:
            target_time = val
            break

    # 🏀 3. 判斷球類
    sport_keyword = "排球" if "排" in query_text else "籃球"
    # 定義該球類的總場地列表
    all_courts = ["排球場(男)1", "排球場(女)2", "排球場(男)3", "排球場(女)4", "排球場(男)5", "排球場(女)6"] if sport_keyword == "排球" else ["籃球場1", "籃球場2", "籃球場3", "籃球場4", "籃球場5", "籃球場6", "籃球場7"]

    try:
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_list = []
        occupied_names = []
        
        for doc in docs:
            data = doc.to_dict()
            c_name = data.get('court_name', '')
            t_slot = data.get('time_slot', '')
            status = data.get('status', '空堂')
            
            # 進行精準時段與球場模糊包含比對
            if sport_keyword in c_name and target_time in t_slot:
                if status != "空堂":
                    occupied_list.append(f"❌ {c_name} ➔ 【{status}】")
                    occupied_names.append(c_name)
                    
        # 計算空堂場地
        free_courts = [c for c in all_courts if c not in occupied_names]
        
        # 4. 組裝完美回覆
        reply_text = f"📊 靜宜戶外【{sport_keyword}場】即時回報\n📅 時間：{target_day} [{target_time} 開始的時段]\n"
        reply_text += "-------------------------\n"
        
        if occupied_list:
            reply_text += "⚠️ 有人借用場地：\n" + "\n".join(occupied_list) + "\n\n"
        else:
            reply_text += "🎉 太棒了！此時段目前沒有任何系隊登記借用！\n\n"
            
        if free_courts:
            clean_free = [c.replace("排球場","").replace("籃球場","") for c in free_courts]
            reply_text += f"👍 還有空場：【{', '.join(clean_free)}】目前是空的，可以自由使用！"
        else:
            reply_text += "😭 殘念...這個時段全部場地都被借滿了。"
            
    except Exception as e:
        reply_text = f"資料庫查詢失敗: {e}"

    return jsonify({"fulfillmentText": reply_text})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)