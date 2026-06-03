from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import urllib3
import os
import json

# 停用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==========================================
# 1. 初始化 Firebase 連線（安全防重複機制）
# ==========================================
if not firebase_admin._apps:
    try:
        if os.environ.get("FIREBASE_KEY_JSON"):
            key_dict = json.loads(os.environ.get("FIREBASE_KEY_JSON"))
            cred = credentials.Certificate(key_dict)
        else:
            cred = credentials.Certificate("pusport-firebase-key.json")
            
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase 連線成功！")
    except Exception as e:
        print(f"❌ Firebase 連線失敗: {e}")

db = firestore.client()

@app.route('/')
def home():
    return "靜宜體育館 Webhook 智慧大整合版運作中！"

# ==========================================
# 2. 接收 Dialogflow 訊息的核心 API 路由
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    parameters = query_result.get('parameters', {})
    
    # 取得同學問的欄位關鍵字與對話原文
    user_court = parameters.get('court_name', '')
    query_text = query_result.get('queryText', '')
    
    # 📅 智慧星期清洗：從對話原文撈出「星期幾」
    target_day = "星期二"  # 預設星期二（配合測試）
    days_list = ["星期一", "星期二", "星期三", "星期四", "星期五"]
    for d in days_list:
        if d in query_text:
            target_day = d
            break

    try:
        # 從 Firestore 撈出當天所有的課表資料
        docs = db.collection("pu_real_schedule").where("date_day", "==", target_day).stream()
        
        occupied_courts = []
        
        print(f"=== 🔍 Vercel 後台抓漏日誌 ===")
        print(f"使用者輸入的場地關鍵字 (user_court): '{user_court}'")
        print(f"使用者對話原文 (query_text): '{query_text}'")
        print(f"最後鎖定的星期 (target_day): '{target_day}'")
        
        for doc in docs:
            data = doc.to_dict()
            db_court_name = data.get('court_name', '')
            db_status = data.get('status', '空堂')
            db_time = data.get('time_slot', '')
            
            # 💡 終極模糊攔截：
            # 只要對話原文或資料庫名稱有「排球」兩個字，或是有互相包含，就強制判定命中！
            is_match = False
            if (user_court and user_court in db_court_name) or (db_court_name in user_court):
                is_match = True
            elif "排球" in query_text and "排球" in db_court_name:
                is_match = True
            elif "籃球" in query_text and "籃球" in db_court_name:
                is_match = True

            if is_match:
                # 過濾掉沒有人借用的空場狀態
                if db_status != "空堂" and db_status != "NO" and db_status != "":
                    occupied_courts.append({
                        "court": db_court_name,
                        "time": db_time,
                        "status": db_status
                    })
        
        # ==========================================
        # 3. 智慧歸納輸出結果
        # ==========================================
        if occupied_courts:
            # 依照場地名稱排序（1場、2場、3場...）
            occupied_courts.sort(key=lambda x: x['court'])
            
            reply_text = f"📊 幫你統整【{target_day}】全校【{user_court if user_court else '球場'}】的各場地借用狀況如下：\n\n"
            for item in occupied_courts:
                reply_text += f"❌ {item['court']} ({item['time']}) ➔ {item['status']}\n"
            
            reply_text += "\n💡 沒出現在上面的其他場地編號就是空場喔！"
        else:
            reply_text = f"👍 報告！【{target_day}】的【{user_court if user_court else '球場'}】目前各場地看起來都是空堂，可以自由使用喔！"
            
    except Exception as e:
        reply_text = f"系統在撈取資料庫時發生錯誤: {e}"

    response = {
        "fulfillmentText": reply_text
    }
    return jsonify(response)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)