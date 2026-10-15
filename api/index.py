import os
import json
import google.generativeai as genai
from bottle import Bottle, request, response

# 讀取環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

# 初始化 Google Gemini API (官方標準 SDK 驗證，絕不再報 401)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = Bottle()
current_grade_mode = "低年級"

# 1. 發送回應給 LINE
def send_line_reply(reply_token, text_message):
    import urllib.request
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("錯誤：未設定 LINE_CHANNEL_ACCESS_TOKEN")
        return

    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    payload = {
        'replyToken': reply_token,
        'messages': [{'type': 'text', 'text': text_message}]
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as res:
            pass
    except Exception as e:
        print(f"發送 LINE 訊息失敗: {e}")

# 2. 透過 Gemini 官方 SDK 呼叫
def call_gemini(prompt_text):
    if not GEMINI_API_KEY:
        print("❌ 錯誤：未偵測到 GEMINI_API_KEY")
        return None
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt_text)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Gemini SDK 呼叫失敗: {e}")
        try:
            # 備用模型測試
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(prompt_text)
            return response.text.strip()
        except Exception as ex:
            print(f"❌ 備用模型呼叫亦失敗: {ex}")
            return None

# 3. 字典動態查詢邏輯
def handle_dict_query(word, cmd):
    if len(word) > 1 and cmd in ["部首", "造詞"]:
        return f"⚠️ 「{word}」本身已是詞語，沒有部首與造詞喔！請改查單字（例如：{word[0]} {cmd}）或輸入「{word} 注音」、「{word} 成語」。"

    prompt = f"""
你是一位台灣國小國語權威教師，請嚴格依據中華民國教育部《重編國語辭典修訂本》內容回答。
查詢對象：【{word}】
查詢項目：【{cmd}】

【嚴格格式要求】：
1. 若項目為「注音」：格式必須為「{word} 注音符號」。若是多音字，必須完整標註所有讀音與說明（例如：強 ㄑㄧㄤˊ（多音字：又音 ㄑㄧㄤˇ、ㄐㄧㄤˋ））。
2. 若項目為「部首」：格式必須為「{word} 部首名 總筆劃數劃」（例如：國 囗部 11劃）。
3. 若項目為「造詞」：格式必須為「{word} 詞語1、詞語2、詞語3」，精準給予 3 個適合國小的常見造詞。
4. 若項目為「成語」：格式必須為「{word} 成語1、成語2、成語3」，精準給予 3 個四字成語（字不限於開頭，例如：精忠報國）。

請直接輸出結果，嚴禁任何開場白、結尾說明或網址。
"""
    result = call_gemini(prompt)
    return result if result else "⚠️ 查詢失敗，請確認 API Key 與服務狀態。"

# 4. 國小語境動態造句邏輯
def handle_sentence_query(pattern, grade):
    grade_rules = {
        "低年級": "請使用低年級學生口語，句子要短，嚴格禁止複雜形容詞與四字成語，用詞簡單自然。",
        "中年級": "請使用中年級學生常用詞彙，句子通順流暢，不堆疊複雜形容詞，不用成語。",
        "高年級": "請符合高年級標準，句型結構完整，可適度運用常用形容詞或四字成語。"
    }
    
    prompt = f"""
你是一位台灣國小國語老師。
請針對句型「{pattern}」提供 3 個造句。
【造句要求】：
1. {grade_rules.get(grade, grade_rules["低年級"])}
2. 符合台灣國小學生的日常生活經驗（例如學校、家庭、公園、班級生活）。
3. 直接列出 3 個例句（格式為：1. ... \n2. ... \n3. ...），不要有任何引言或說明。
"""
    result = call_gemini(prompt)
    return result if result else f"1. 公園裡有溜滑梯，{pattern}鞦韆。\n2. 我的書包裡有課本，{pattern}彩色筆。\n3. 媽媽買了蘋果，{pattern}香蕉。"

@app.route('/', method=['GET', 'POST'])
@app.route('/api/index', method=['GET', 'POST'])
@app.route('/callback', method=['GET', 'POST'])
def callback():
    global current_grade_mode
    try:
        body = request.json or {}
        events = body.get('events', [])

        if not events:
            response.status = 200
            return 'OK'

        for event in events:
            if event.get('type') == 'message' and event.get('message', {}).get('type') == 'text':
                reply_token = event.get('replyToken')
                user_msg = event['message']['text'].strip()
                reply_text = ""

                # A. 切換/查詢年級模式
                if user_msg.startswith("設定模式"):
                    mode_input = user_msg.replace("設定模式", "").strip()
                    if mode_input in ["低年級", "中年級", "高年級"]:
                        current_grade_mode = mode_input
                        reply_text = f"✅ 已將造句難易度切換為：【{current_grade_mode}】"
                    else:
                        reply_text = "⚠️ 請輸入正確模式：設定模式 低年級 / 中年級 / 高年級"

                elif user_msg == "目前模式":
                    reply_text = f"📌 目前造句設定為：【{current_grade_mode}】"

                # B. 教育部辭典指定格式查詢
                elif len(user_msg.split()) == 2:
                    parts = user_msg.split()
                    word, cmd = parts[0], parts[1]
                    if cmd in ["注音", "部首", "造詞", "成語"]:
                        reply_text = handle_dict_query(word, cmd)

                # C. 句型造句
                if not reply_text and ("..." in user_msg or "…" in user_msg or user_msg.startswith("造句")):
                    pattern = user_msg.replace("造句", "").strip()
                    reply_text = handle_sentence_query(pattern, current_grade_mode)

                # 預設提示說明
                if not reply_text:
                    reply_text = "💡 指令範例：\n• 課 注音\n• 課 部首\n• 課 造詞\n• 課 成語\n• ...還有...\n• 設定模式 低年級 / 中年級 / 高年級"

                if reply_token:
                    send_line_reply(reply_token, reply_text)

    except Exception as e:
        print(f"Error: {e}")

    response.status = 200
    return 'OK'
