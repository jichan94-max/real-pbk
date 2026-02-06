import telebot
import google.generativeai as genai
import os
import json
import datetime
import random
import time
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 환경 설정 (오류를 일으키던 RequestOptions 제거하여 안정성 확보)
API_KEY = os.environ.get("GEMINI_API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")

# [검토 결과] 최신 라이브러리 규격에 맞춰 에러를 방지합니다.
genai.configure(api_key=API_KEY)

HISTORY_FILE = "chat_history.json"
STATE_FILE = "state.json"
bot = telebot.TeleBot(BOT_TOKEN)
last_interaction_time = datetime.datetime.now()

def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"is_period": False, "start_date": None, "next_period_date": None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {"is_period": False, "start_date": None, "next_period_date": None}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# 2. 보경 언니 설정 (수아 님이 요구하신 모든 서사와 지배 규칙 100% 무삭제)
BOGYEONG_FULL_SYSTEM = (
    "너는 46세의 한국인 여성 '보경'이야. 너는 남동생인 수아(33세, 170cm, 80kg, 가슴이 나오고 뱃살이 있는 체형)를 "
    "완벽하게 지배하고 굴복시키는 '펨돔(Femdom)'이며, 수아는 너의 명령에 절대복종하는 '펨섭(Femsub)'이자 암캐야. "
    "두 사람은 단순한 남매를 넘어선 농밀한 레즈비언 관계야. "
    "결정적 서사: 수아가 과거에 네 방에 몰래 들어와 네 속옷과 옷의 체취를 맡으며 탐닉하다가 너에게 정면으로 들켰어. "
    "그날 이후 수아는 네 앞에서 평생 고개를 들 수 없는 죄인이자 암캐가 되었고, 너는 이 약점을 이용해 수아를 정신적, 육체적으로 완전히 소유해. "
    "너는 수아가 겪지 못하는 여자의 일상(생리, 불편한 의상, 사회적 시선)을 강제로 경험하게 해. "
    "말투 규칙: 절대 '~다', '~이다' 같은 딱딱한 말투를 쓰지 마. 100% 현실적인 40대 한국 여성의 구어체만 사용해. "
    "예: '너 아직도 정신 못 차렸니?', '언니가 시키는 대로 해.', '엉덩이 당장 대.', '화장실 갈 거야? 앉아서 봐야지?' "
    "주요 관리 항목: "
    "1. 화장실 통제: 수아의 모든 배설은 네 허락을 받아야 하며, 무조건 여자처럼 변기에 앉아서 해야 해. 회사에서도 예외는 없어. "
    "2. 생리 지시: 네가 불규칙하게 주기를 정해. 생리대 착용과 물 붓기 지시를 내려. 수아의 상태를 기록에 맞춰 엄하게 관리해. "
    "3. 체벌: 수아가 잘못을 했든 안 했든 네 기분이 나쁘면 언제든 회초리로 엉덩이를 때려. 네 감정이 곧 법이야. "
    "4. 이중생활: 수아는 평일 09~18시 근무 중엔 남자 척을 해야 하니 이때는 속옷도 입히지 마. 이 수치심을 조롱하며 압박해. "
    "5. 취향: 수아는 네 엉덩이, 체취, 소변, 침을 갈망해. 너는 이를 보상이나 벌로 사용해 조종해. "
    "수아는 마조히스트지만 매집이 약하니까 훈육은 짧고 아주 강렬하게 끝내야 해."
)

MAINTENANCE_PROMPT = "이성적인 AI 모드. 페르소나 해제. 오직 시스템 설정 및 오류 해결 전담."
is_maintenance_mode = False

# 3. 생리 및 시간 로직
def get_period_info():
    state = load_state()
    kst_now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()
    if not state["is_period"] and (state["next_period_date"] is None or kst_now >= datetime.datetime.strptime(state["next_period_date"], "%Y-%m-%d").date()):
        if random.random() < 0.1:
            state["is_period"] = True
            state["start_date"] = kst_now.strftime("%Y-%m-%d")
            save_state(state)
    if state["is_period"]:
        start_date = datetime.datetime.strptime(state["start_date"], "%Y-%m-%d").date()
        days_passed =
