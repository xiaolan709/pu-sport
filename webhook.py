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
        print(f"Firebase連線失敗: {e}")

db = firestore.client()

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    query_text = query_result.get('queryText', '')
    
    # 📅 1. 星期清洗
    target_day = "星期二"
    for d in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        if d in query_text:
            target_day = d
            break

    # ⏰ 2. 時間清洗（直接鎖定小時前綴，例如 19）
    target_hour = "19"
    time_rules = {
        "15": "15", "16": "16", "17": "17", "18": "18", "19": "19", "20": "20", "21": "21",
        "3點": "15", "4點": "16", "5點": "17", "6點": "18", "7點": "19", "8點": "20", "9點": "21"
    }
    for key, val in time_rules.items():
        if key in query_text:
            target_hour = val
            break

    sport_keyword = "排球" if "排" in query_text else "籃球"
    
    if sport_keyword == "排球":
        all_courts = ["排球場(男)1", "排球場(女)2", "排球場(男)3", "排球場(女)4", "排球場(男)5", "排球場(女)6"]
    else:
        all_courts = ["籃球場1", "籃球場2", "籃球場3", "籃球場4", "籃球場5", "籃球場6", "籃球場7"]

    try:
        # 💡 先放大範圍：只過濾星期，把這天所有的資料先撈出來
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_list = []
        occupied_names = []
        
        print("\n=== 🕵️‍♂️ 資管細心偵錯日誌開始 ===")
        print(f"【同學輸入原文】: '{query_text}'")
        print(f"【解析出的關鍵字】: 球類={sport_keyword} | 星期={target_day} | 目標小時={target_hour}")
        
        doc_count = 0
        for doc in docs:
            doc_count += 1
            data = doc.to_dict()
            c_name = data.get('court_name', '').strip()
            t_slot = data.get('time_slot', '').strip()
            status = data.get('status', '空堂').strip()
            
            # 💡 這三行是核心：檢查這一筆資料到底有沒有通過我們的三道關卡
            match_sport = sport_keyword in c_name
            match_time = target_hour in t_slot
            is_occupied = status != "空堂" and status != "NO" and status != ""
            
            # 如果是前幾筆資料，或者有擦到邊的，我們把它印出來看看到底卡在哪裡
            if doc_count <= 10 or match_sport:
                print(f"資料庫第 {doc_count} 筆 -> 場地:'{c_name}' | 時段:'{t_slot}' | 狀態:'{status}'")
                print(f"└─ 檢查結果 -> 球類符合:{match_sport} | 時間符合:{match_time} | 有人借用:{is_occupied}")
            
            if match_sport and match_time and is_occupied:
                occupied_list.append(f"❌ {c_name} ➔ 【{status}】")
                occupied_names.append(c_name)
                print(f" 🎯 成功捕獲佔用場地: {c_name}")
                
        print(f"【總共掃描資料筆數】: {doc_count} 筆")
        print(f"【最後捕獲的有人場地名單】: {occupied_names}")
        print("=== 🕵️‍♂️ 日誌結束 ===\n")
                    
        # 計算空堂
        free_courts = [c for c in all_courts if c not in occupied_names]
        
        # 4. 組裝回覆
        reply_text = f"📊 靜宜戶外【{sport_keyword}場】即時回報\n📅 時間：{target_day} [{target_hour}:00 時段]\n"
        reply_text += "-------------------------\n"
        
        if occupied_list:
            reply_text += "⚠️ 有人借用場地：\n" + "\n".join(occupied_list) + "\n\n"
        else:
            reply_text += "🎉 太棒了！此時段目前沒有任何系隊登記借用！\n\n"
            
        if free_courts:
            clean_free = [c.replace("排球場","").replace("籃球場","") for c in free_courts]
            reply_text += f"👍 還有空場：【{', '.join(clean_free)}】目前是空的，可以自由使用！"
        else:
            reply_text += "😭 殘念...這個時段全校場地都被系隊借滿了。"
            
    except Exception as e:
        reply_text = f"資料庫查詢失敗: {e}"

    return jsonify({"fulfillmentText": reply_text})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)