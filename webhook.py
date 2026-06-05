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
    
    # 📅 1. 智慧星期清洗 ➔ 用於對齊資料庫中的 day_of_week
    target_day = "星期二"
    for d in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        if d in query_text:
            target_day = d
            break

    # ⏰ 2. 正規表達式精準抓取對話中的整數小時
    digits = re.findall(r'\d+', query_text)
    user_hour = 19
    if digits:
        first_num = int(digits[0])
        if 1 <= first_num <= 11:
            user_hour = first_num + 12
        elif 12 <= first_num <= 23:
            user_hour = first_num

    sport_keyword = "排球" if "排" in query_text else "籃球"
    db_court_type = "室外排球場" if sport_keyword == "排球" else "室外籃球場"
    
    # 定義該球類在靜宜戶外的所有場地編號清單
    all_court_numbers = ["1", "2", "3", "4", "5", "6"] if sport_keyword == "排球" else ["1", "2", "3", "4", "5", "6", "7"]

    try:
        occupied_list = []
        occupied_numbers = []

        # 💡 修正縮排並精準撈取當天該球類的所有資料
        docs = db.collection("training_schedule") \
                 .where("court_type", "==", db_court_type) \
                 .where("day_of_week", "==", target_day) \
                 .stream()

        for doc in docs:
            data = doc.to_dict()
            court_num = str(data.get("court_number", "")).strip()
            team = str(data.get("team", "空堂")).strip()
            t_slot = str(data.get("time_slot", "")).strip()

            try:
                # 抓出時段開始的小時（例如 "19:00-19:30" ➔ 抓出 19）
                start_hour = int(t_slot.split("-")[0].split(":")[0])
            except:
                continue

            # 如果這筆課表的小時跟使用者要查的時間不相符，直接跳過
            if start_hour != user_hour:
                continue

            # 判定是否真的有人借用
            if team not in ["空堂", "禁止預約", ""]:
                # 建立顯示格式，例如：❌ 第 3 場 ➔ 【資管男排】 (19:00-19:30)
                # 加上括號時間可以讓同學更清楚是前排還是後排練球！
                display_info = f"❌ 第 {court_num} 場 ➔ 【{team}】 ({t_slot})"
                
                # 防止 30 分鐘拆分時，重複加入同一個場地的佔用訊息
                if display_info not in occupied_list:
                    occupied_list.append(display_info)
                
                if court_num not in occupied_numbers:
                    occupied_numbers.append(court_num)

        # 🧮 3. 計算空場
        free_courts = [
            num for num in all_court_numbers
            if num not in occupied_numbers
        ]
        free_courts.sort()

        # 📊 4. 組裝回覆訊息
        reply_text = (
            f"📊 靜宜{db_court_type}即時回報\n"
            f"📅 時間：{target_day} [{user_hour}:00 時段]\n"
        )
        reply_text += "-------------------------\n"

        if occupied_list:
            occupied_list.sort()
            reply_text += (
                "⚠️ 有人借用場地：\n"
                + "\n".join(occupied_list)
                + "\n\n"
            )
        else:
            reply_text += (
                "🎉 太棒了！此時段目前沒有任何系隊登記借用！\n\n"
            )

        if free_courts:
            reply_text += (
                f"👍 檢查完畢：【第 {', '.join(free_courts)} 場】"
                "目前是空場，可以自由去打球喔！"
            )
        else:
            reply_text += (
                "😭 殘念...這個時段所有場地都被系隊借滿了。"
            )

    except Exception as e:
        reply_text = f"資料庫查詢失敗：{str(e)}"

    # 💡 【核心修正】：將最後封裝好的完美 JSON 訊息回傳給 Dialogflow
    return jsonify({"fulfillmentText": reply_text})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)