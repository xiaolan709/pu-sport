from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import urllib3
import os
import json
import re

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
        print(f"Firebase連線失敗: {e}")

db = firestore.client()

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    query_text = query_result.get('queryText', '').strip()
    
    # 📅 1. 智慧星期清洗 ➔ 對齊資料庫的 day_of_week
    target_day = "星期二"
    for d in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        if d in query_text:
            target_day = d
            break

    # ⏰ 2. 正規表達式時間抽取
    digits = re.findall(r'\d+', query_text)
    user_hour = 19
    if digits:
        first_num = int(digits[0])
        if 1 <= first_num <= 11:
            user_hour = first_num + 12
        elif 12 <= first_num <= 23:
            user_hour = first_num

    target_time_prefix = f"{user_hour}:"
    sport_keyword = "排球" if "排" in query_text else "籃球"
    db_sport_type = "室外排球場" if sport_keyword == "排球" else "室外籃球場"
    
    # 預設各場地的編號列表
    all_court_numbers = ["1", "2", "3", "4", "5", "6"] if sport_keyword == "排球" else ["1", "2", "3", "4", "5", "6", "7"]

    try:
        # 💡 精準鎖定：去 school_schedule 撈取符合 day_of_week 與 court_type 的資料
        docs = db.collection("school_schedule") \
                 .where("day_of_week", "==", target_day) \
                 .where("court_type", "==", db_sport_type).stream()
        
        occupied_list = []
        occupied_numbers = []
        
        for doc in docs:
            data = doc.to_dict()
            c_num = data.get('court_number', '').strip()
            t_slot = data.get('time_slot', '').strip()
            status = data.get('status', '空堂').strip()
            
            # 💡 檢查時間前綴（例如 "19:" 有沒有在 "19:00-21:00" 裡面）
            if target_time_prefix in t_slot:
                if status != "空堂" and status != "NO" and status != "" and "開放" not in status:
                    # 依格式組合出佔用訊息：例如 ❌ 第3場 ➔ 【資管男排】
                    occupied_list.append(f"❌ 第 {c_num} 場 ➔ 【{status}】")
                    occupied_numbers.append(c_num)
                    
        # 計算有哪些場地是空場
        free_courts = [num for num in all_court_numbers if num not in occupied_numbers]
        free_courts.sort()
        
        # 4. 組織精緻的回覆
        reply_text = f"📊 靜宜{db_sport_type}即時回報\n📅 時間：{target_day} [{user_hour}:00 時段]\n"
        reply_text += "-------------------------\n"
        
        if occupied_list:
            occupied_list.sort()
            reply_text += "⚠️ 有人借用場地：\n" + "\n".join(occupied_list) + "\n\n"
        else:
            reply_text += "🎉 太棒了！此時段目前沒有任何系隊登記借用！\n\n"
            
        if free_courts:
            # 依照你的期待，清晰指出哪些場次有空
            reply_text += f"👍 檢查完畢：【第 {', '.join(free_courts)} 場】目前是空場，可以自由去打球喔！"
        else:
            reply_text += "😭 殘念...這個時段全校場地都被系隊借滿了。"
            
    except Exception as e:
        reply_text = f"資料庫查詢失敗: {e}"

    return jsonify({"fulfillmentText": reply_text})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)