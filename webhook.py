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
# 1. 初始化 Firebase 連線（防止在 Serverless 環境重複初始化）
# ==========================================
if not firebase_admin._apps:
    try:
        # 優先讀取環境變數（為了 Vercel 安全性），如果沒有就讀取本地檔案
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
    return "靜宜體育館 Webhook 運作中！"

# ==========================================
# 2. 接收 Dialogflow 訊息的 API 路由
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    query_result = req.get('queryResult')
    parameters = query_result.get('parameters', {})
    
    court_name = parameters.get('court_name')
    date_time = parameters.get('date_time')

    reply_text = f"關於你查詢的【{court_name}】"
    
    try:
        # 去 Firestore 搜尋對應場地的資料
        docs = db.collection("pu_real_schedule").where("court_name", "==", court_name).stream()
        
        schedule_list = []
        for doc in docs:
            data = doc.to_dict()
            schedule_list.append(f"⏰ 時段: {data['time_slot']} -> 借用單位: {data['status']}")
        
        if schedule_list:
            reply_text += "，目前的課表與借用狀況如下：\n" + "\n".join(schedule_list)
        else:
            reply_text += "，目前在學校課表上看起來是空堂喔！可以安心使用。 👍"
            
    except Exception as e:
        reply_text = f"系統在撈取資料庫時發生錯誤: {e}"

    response = {
        "fulfillmentText": reply_text
    }
    return jsonify(response)