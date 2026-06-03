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
        print(f"Firebase initialization failed: {e}")

db = firestore.client()

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    query_text = query_result.get('queryText', '').strip()
    
    # 📅 1. 星期清洗
    target_day = "星期二"
    for d in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        if d in query_text:
            target_day = d
            break

    # ⏰ 2. 【最細心的時間抽取邏輯】
    # 直接用正規表達式把對話裡的數字全部挖出來（例如「晚上7點」➔ 抓出 7；「19點」➔ 抓出 19）
    digits = re.findall(r'\d+', query_text)
    user_hour = 19 # 預設 19 點
    
    if digits:
        first_num = int(digits[0])
        # 如果同學打 1~11，代表是下午/晚上時段，自動幫他轉成 24 小時制 (例如 7 點 ➔ 19 點)
        if 1 <= first_num <= 11:
            user_hour = first_num + 12
        elif 12 <= first_num <= 23:
            user_hour = first_num

    # 將數字轉成資料庫對齊用的字串（例如 19 -> "19:00"）
    target_time_str = f"{user_hour}:00"

    # 🏀 3. 判斷球類
    sport_keyword = "排球" if "排" in query_text else "籃球"
    
    if sport_keyword == "排球":
        all_courts = ["排球場(男)1", "排球場(女)2", "排球場(男)3", "排球場(女)4", "排球場(男)5", "排球場(女)6"]
    else:
        all_courts = ["籃球場1", "籃球場2", "籃球場3", "籃球場4", "籃球場5", "籃球場6", "籃球場7"]

    try:
        # 去 Firestore 撈取當天所有資料
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_list = []
        occupied_names = []
        
        for doc in docs:
            data = doc.to_dict()
            c_name = data.get('court_name', '').strip()
            t_slot = data.get('time_slot', '').strip()
            status = data.get('status', '空堂').strip()
            
            # 💡 檢查球類有沒有對上，且資料庫的 time_slot 是不是包含了我們要的時段（例如 "19:00"）
            if sport_keyword in c_name and target_time_str in t_slot:
                if status != "空堂" and status != "NO" and status != "" and "開放" not in status:
                    # 簡化名字（例如 1142學期戶外排球場(男)1 ➔ 排球場(男)1）
                    short_name = c_name.replace("1142學期戶外球場協調-", "").replace("1142學期戶外", "")
                    occupied_list.append(f"❌ {short_name} ➔ 【{status}】")
                    occupied_names.append(c_name)
                    
        # 計算有哪些場地是空的
        free_courts = [c for c in all_courts if c not in occupied_names]
        
        # 4. 組裝回覆
        reply_text = f"📊 靜宜戶外【{sport_keyword}場】即時回報\n📅 時間：{target_day} [{target_time_str} 開始的時段]\n"
        reply_text += "-------------------------\n"
        
        if occupied_list:
            occupied_list.sort() # 讓 1場、2場、3場 乖乖排好隊
            reply_text += "⚠️ 有人借用場地：\n" + "\n".join(occupied_list) + "\n\n"
        else:
            reply_text += "🎉 太棒了！此時段目前沒有任何系隊登記借用！\n\n"
            
        if free_courts:
            # 清洗空場的名字，只留 (男)1、(女)2
            clean_free = [c.replace("排球場","").replace("籃球場","") for c in free_courts]
            clean_free.sort()
            reply_text += f"👍 還有空場：【{', '.join(clean_free)}】目前是空的，可以自由使用！"
        else:
            reply_text += "😭 殘念...這個時段全校場地都被系隊借滿了。"
            
    except Exception as e:
        reply_text = f"資料庫查詢失敗: {e}"

    return jsonify({"fulfillmentText": reply_text})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)