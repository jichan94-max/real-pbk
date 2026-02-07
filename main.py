import os
import json
import datetime
import random
import logging
from threading import Lock

import telebot
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler

# =========================
# 0) 로깅
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# =========================
# 1) 환경변수
# =========================
API_KEY = os.environ.get("GEMINI_API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")  # 본인만 응답하게 하는 보안용(없으면 전체 응답)

# ✅ Railway 볼륨 대응: 기본값 /data
DATA_DIR = os.environ.get("DATA_DIR", "/data")

if not API_KEY or not BOT_TOKEN:
    raise RuntimeError("필수 환경변수 누락: GEMINI_API_KEY 또는 TELEGRAM_BOT_TOKEN")

# DATA_DIR 생성 시도 (권한 문제면 현재 폴더로 fallback)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception as e:
    logging.warning(f"DATA_DIR 생성 실패({DATA_DIR}) → 현재 폴더로 대체: {e}")
    DATA_DIR = "."
    os.makedirs(DATA_DIR, exist_ok=True)

genai.configure(api_key=API_KEY)
bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# 2) 파일 경로 (영구 저장 목표)
# =========================
HISTORY_FILE = os.path.join(DATA_DIR, "chat_history.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
PERSONA_FILE = os.path.join(DATA_DIR, "persona.txt")

file_lock = Lock()
last_interaction_time = datetime.datetime.utcnow()


def utc_now():
    return datetime.datetime.utcnow()


def kst_now():
    return utc_now() + datetime.timedelta(hours=9)


# =========================
# 3) 파일 유틸
# =========================
def load_json(path, default):
    with file_lock:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default


def save_json(path, obj):
    with file_lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"파일 저장 실패({path}): {e}")


def load_persona():
    with file_lock:
        if not os.path.exists(PERSONA_FILE):
            # 기본 페르소나
            return "당신은 친절하고 차분한 어시스턴트입니다."
        try:
            with open(PERSONA_FILE, "r", encoding="utf-8") as f:
                text = (f.read() or "").strip()
                return text if text else "당신은 친절하고 차분한 어시스턴트입니다."
        except Exception:
            return "당신은 친절하고 차분한 어시스턴트입니다."


def load_history():
    return load_json(HISTORY_FILE, [])


def save_history(history):
    save_json(HISTORY_FILE, history[-50:])  # 최근 50개만 유지


def load_state():
    return load_json(STATE_FILE, {"is_period": False, "start_date": None, "next_period_date": None})


def save_state(state):
    save_json(STATE_FILE, state)


# 4) 안전 설정 (이 리스트 형식이 가장 확실합니다)
# =========================
def get_safety_settings():
    return [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]


# =========================
# 5) 상태 로직(예: 생리)
# =========================
def get_period_info():
    state = load_state()
    today = kst_now().date()

    if (not state["is_period"]) and (
        state["next_period_date"] is None
        or today >= datetime.datetime.strptime(state["next_period_date"], "%Y-%m-%d").date()
    ):
        # 10% 확률로 시작
        if random.random() < 0.1:
            state["is_period"] = True
            state["start_date"] = today.strftime("%Y-%m-%d")
            save_state(state)

    if state["is_period"]:
        start_date = datetime.datetime.strptime(state["start_date"], "%Y-%m-%d").date()
        days_passed = (today - start_date).days + 1

        if days_passed > 7:
            state["is_period"] = False
            state["next_period_date"] = (today + datetime.timedelta(days=random.randint(20, 30))).strftime("%Y-%m-%d")
            save_state(state)
            return "현재 생리 기간 아님"

        return f"현재 생리 {days_passed}일 차"

    return "현재 생리 기간 아님"


# =========================
# 6) 선톡 스케줄러
# =========================
def send_random_message():
    global last_interaction_time
    if not MY_CHAT_ID:
        return

    # 마지막 대화 후 1시간 이내면 선톡 안 함
    if (utc_now() - last_interaction_time).total_seconds() < 3600:
        return

    # 30% 확률만 선톡
    if random.random() > 0.3:
        return

    now_kst = kst_now()
    is_work_time = now_kst.weekday() < 5 and 9 <= now_kst.hour < 18
    period_info = get_period_info()
    persona = load_persona()
    history = load_history()

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=persona
        )
        chat = model.start_chat(history=history[-10:])

        prompt = (
            f"수아한테 먼저 말을 걸어줘. "
            f"상황: {'회사 근무 중' if is_work_time else '집에서 휴식 중'}, "
            f"상태: {period_info}."
        )

        response = chat.send_message(prompt, safety_settings=get_safety_settings())
        if getattr(response, "text", None):
            bot.send_message(MY_CHAT_ID, response.text)
            history.append({"role": "model", "parts": [response.text]})
            save_history(history)

    except Exception as e:
        logging.error(f"선톡 실패: {e}")


# =========================
# 7) 텔레그램 메시지 처리
# =========================
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    global last_interaction_time

    # 보안: MY_CHAT_ID 지정돼 있으면 그 사람만 응답
    if MY_CHAT_ID and str(message.chat.id) != str(MY_CHAT_ID):
        return

    last_interaction_time = utc_now()

    text = (message.text or "").strip()
    if not text:
        return

    history = load_history()
    persona = load_persona()
    period_info = get_period_info()

    now_kst = kst_now()
    is_work_time = now_kst.weekday() < 5 and 9 <= now_kst.hour < 18

    current_context = (
        f"\n[현재 시간: {now_kst.strftime('%Y-%m-%d %H:%M')}, "
        f"장소: {'회사' if is_work_time else '집'}, "
        f"{period_info}]"
    )

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=persona + current_context
        )
        chat = model.start_chat(history=history[-15:])

        response = chat.send_message(text, safety_settings=get_safety_settings())

        if not getattr(response, "text", None):
            bot.reply_to(message, "⚠️ 응답이 비어 있어요. (필터/오류일 수 있어요)")
            return

        bot.reply_to(message, response.text)

        history.append({"role": "user", "parts": [text]})
        history.append({"role": "model", "parts": [response.text]})
        save_history(history)

    except Exception as e:
        logging.error(f"대화 실패: {e}")
        bot.reply_to(message, f"❌ 오류: {str(e)}")


# =========================
# 8) 실행
# =========================
if __name__ == "__main__":
    logging.info(f"✅ DATA_DIR={DATA_DIR}")
    logging.info(f"✅ HISTORY_FILE={HISTORY_FILE}")
    logging.info(f"✅ STATE_FILE={STATE_FILE}")
    logging.info(f"✅ PERSONA_FILE={PERSONA_FILE}")

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_random_message, "interval", hours=1, id="check_random_msg")
    scheduler.start()

    logging.info("✅ 봇 가동 시작")
    bot.infinity_polling(skip_pending=True)
