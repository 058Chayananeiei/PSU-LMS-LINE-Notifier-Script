import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import re

# ระบบจะดึงจาก GitHub Secrets ก่อน หากไม่มีจะใช้ค่าที่คุณใส่ไว้ตรงนี้
ICAL_URL = os.environ.get(
    "LMS_ICAL_URL",
    "https://lms.psu.ac.th/calendar/export_execute.php?userid=56828&authtoken=3463a3bce6ca9586ecb1a5abf0d4757ebf314808&preset_what=all&preset_time=recentupcoming"
)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "OhLplD8z1jYvO/ir9OArpa1ypVBp0bC/1tP8q59oJ4C5n4Etwfx+VVAZfzgedK7T5MXr3Ydz38MzzhhDlysQg6oO6p5IdyKVaCxRxBpxPWqGMhRvp0jILd6+u3BWfRKqWFhthZh6G/yqsjV3LeJfbwdB04t89/1O/w1cDnyilFU="
)
LINE_USER_ID = os.environ.get(
    "LINE_USER_ID",
    "U497c7511a9cda8f1568f5be06da7ccc7"
)

# ปรับโซนเวลา (ประเทศไทย UTC+7)
TZ_OFFSET = timedelta(hours=7)

# ===== การตั้งค่าระบบแจ้งเตือนงานใกล้หมดเวลา =====
URGENT_HOURS = 3          # แจ้งเตือนด่วนเมื่อเหลือเวลาน้อยกว่านี้ (ชั่วโมง)
DIGEST_HOURS = (6, 7, 8)  # ช่วงเวลา (ตามชั่วโมงไทย) ที่ถือว่าเป็น "รอบสรุปประจำวัน"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notified_state.json")
STATE_RETENTION_DAYS = 3  # เก็บ record เก่าไว้กี่วันก่อนล้างทิ้ง (กันไฟล์บวม)


def parse_ical_datetime(dt_str):
    """แปลงรูปแบบวันที่เวลาจาก iCal ให้เป็นวัตถุ datetime"""
    clean_str = dt_str.split(':')[-1].strip()
    if 'T' in clean_str:
        if clean_str.endswith('Z'):
            clean_str = clean_str[:-1]
            return datetime.strptime(clean_str, "%Y%m%dT%H%M%S")
        else:
            return datetime.strptime(clean_str, "%Y%m%dT%H%M%S")
    else:
        return datetime.strptime(clean_str, "%Y%m%d")


def fetch_lms_events(ical_url):
    """ดาวน์โหลดและอ่านรายการการบ้านจาก iCal URL"""
    # ป้องกันกรณีค่า secret ถูก copy มาแบบมีวงเล็บ/เครื่องหมายคำพูด/ช่องว่างติดมาด้วย
    cleaned_url = ical_url.strip().strip('[]<>"\'').strip()
    if not cleaned_url.startswith(('http://', 'https://')):
        raise ValueError(
            f"LMS_ICAL_URL ดูไม่ถูกต้อง: {cleaned_url!r} "
            "กรุณาตรวจสอบค่าใน GitHub Secrets ว่าเป็น URL ล้วนๆ "
            "ไม่มีวงเล็บ [ ], เครื่องหมายคำพูด, หรือช่องว่างครอบอยู่"
        )

    req = urllib.request.Request(
        cleaned_url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')

    events = []
    raw_events = content.split('BEGIN:VEVENT')
    now_local = datetime.utcnow() + TZ_OFFSET

    for raw_event in raw_events[1:]:
        summary_match = re.search(r'SUMMARY:(.*)', raw_event)
        dtend_match = re.search(r'DTEND.*:(.*)', raw_event)
        dtstart_match = re.search(r'DTSTART.*:(.*)', raw_event)
        desc_match = re.search(r'DESCRIPTION:(.*)', raw_event)

        if not summary_match:
            continue

        title = summary_match.group(1).strip().replace('\\', '')
        dt_target = dtend_match.group(1) if dtend_match else (dtstart_match.group(1) if dtstart_match else None)

        if not dt_target:
            continue

        try:
            due_date = parse_ical_datetime(dt_target) + TZ_OFFSET
        except Exception:
            continue

        description = desc_match.group(1).strip() if desc_match else ""

        # กรองเฉพาะงานที่ยังไม่หมดเวลาส่ง (ย้อนหลังไม่เกิน 2 ชม.)
        if due_date >= now_local - timedelta(hours=2):
            events.append({
                'title': title,
                'due_date': due_date,
                'description': description
            })

    # เรียงลำดับงานตามวันส่งใกล้วันที่สุดขึ้นก่อน
    events.sort(key=lambda x: x['due_date'])
    return events


def generate_plain_message(events):
    """สร้างข้อความสรุปงานประจำวัน (รูปแบบเดิม)"""
    now = datetime.utcnow() + TZ_OFFSET
    today_str = now.strftime("%d/%m/%Y")

    if not events:
        return f"\n🎉 รายงานประจำวันที่ {today_str}\nขณะนี้ไม่มีงานค้างในระบบ LMS PSU ครับ!"

    msg = f"\n🔔 รายงานการบ้าน/งาน LMS PSU ({today_str})\n"
    msg += f"พบงานค้างทั้งหมด {len(events)} รายการ\n"
    msg += "-----------------------------------\n"

    for idx, item in enumerate(events[:10], 1):
        due = item['due_date']
        time_left = due - now
        days_left = time_left.days
        hours_left = int(time_left.seconds // 3600)

        if days_left < 1:
            urgency = "🚨 [ส่งวันนี้/พรุ่งนี้]"
        elif days_left <= 3:
            urgency = "⚠️ [เหลือ 2-3 วัน]"
        else:
            urgency = "📌 [มีเวลา]"

        due_fmt = due.strftime("%d/%m/%Y %H:%M น.")

        msg += f"\n{idx}. {item['title']}\n"
        msg += f"   • สถานะ: {urgency}\n"
        msg += f"   • กำหนดส่ง: {due_fmt}\n"
        msg += f"   • คงเหลือ: {days_left} วัน {hours_left} ชม.\n"

    msg += "\n👉 ทางเข้า LMS: https://lms2.psu.ac.th"
    return msg


def generate_urgent_message(urgent_events, now):
    """สร้างข้อความแจ้งเตือนด่วน (งานใกล้หมดเวลา)"""
    now_str = now.strftime("%d/%m/%Y %H:%M น.")
    msg = f"\n⏰ แจ้งเตือนด่วน! งานใกล้หมดเวลาแล้ว ({now_str})\n"
    msg += "-----------------------------------\n"

    for idx, item in enumerate(urgent_events, 1):
        due = item['due_date']
        time_left = due - now
        total_minutes = int(time_left.total_seconds() // 60)
        hours_left = total_minutes // 60
        minutes_left = total_minutes % 60
        due_fmt = due.strftime("%d/%m/%Y %H:%M น.")

        msg += f"\n{idx}. 🚨 {item['title']}\n"
        msg += f"   • กำหนดส่ง: {due_fmt}\n"
        msg += f"   • เหลือเวลาอีก: {hours_left} ชม. {minutes_left} นาที!\n"

    msg += "\n👉 รีบส่งงานด่วน: https://lms2.psu.ac.th"
    return msg


def event_key(item):
    """สร้าง key ที่ไม่ซ้ำสำหรับงานแต่ละชิ้น เพื่อใช้เช็คว่าเคยแจ้งเตือนด่วนไปแล้วหรือยัง"""
    return f"{item['title']}|{item['due_date'].isoformat()}"


def load_notified_state(path):
    """โหลดรายการงานที่เคยส่งแจ้งเตือนด่วนไปแล้ว"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("notified", {})
    except Exception:
        return {}


def save_notified_state(path, notified_dict):
    """บันทึกรายการงานที่แจ้งเตือนด่วนไปแล้วลงไฟล์"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"notified": notified_dict}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ บันทึกสถานะไม่สำเร็จ: {e}")


def cleanup_old_state(notified_dict, now):
    """ล้าง record เก่าที่หมดเวลาไปนานแล้ว กันไฟล์บวมไม่รู้จบ"""
    cutoff = now - timedelta(days=STATE_RETENTION_DAYS)
    cleaned = {}
    for key, notified_at_str in notified_dict.items():
        try:
            due_str = key.split('|', 1)[1]
            due_dt = datetime.fromisoformat(due_str)
            if due_dt >= cutoff:
                cleaned[key] = notified_at_str
        except Exception:
            # ถ้า parse ไม่ได้ ก็เก็บไว้ก่อนเผื่อพลาด
            cleaned[key] = notified_at_str
    return cleaned


def send_line_messaging_api(access_token, to_id, message):
    """ส่งข้อความผ่าน LINE Messaging API (Bot)"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = json.dumps({
        "to": to_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            print("✅ ส่งการแจ้งเตือนเข้า LINE สำเร็จแล้ว!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่ง LINE Messaging API: {e}")


if __name__ == "__main__":
    print("🚀 เริ่มต้นระบบแจ้งเตือน PSU LMS...")

    if not ICAL_URL:
        print("ข้อผิดพลาด: ไม่พบค่า LMS_ICAL_URL")
        exit(1)

    print("📥 กำลังดาวน์โหลดข้อมูลงานจาก PSU LMS...")
    events = fetch_lms_events(ICAL_URL)

    now_local = datetime.utcnow() + TZ_OFFSET
    is_digest_run = now_local.hour in DIGEST_HOURS

    notified = load_notified_state(STATE_FILE)
    notified = cleanup_old_state(notified, now_local)

    message_to_send = None

    if is_digest_run:
        # รอบเช้า -> ส่งสรุปประจำวันตามเดิม
        print("🗒️ รอบนี้เป็นรอบสรุปประจำวัน")
        message_to_send = generate_plain_message(events)
    else:
        # รอบอื่น -> เช็คเฉพาะงานที่ใกล้หมดเวลา (และยังไม่เคยแจ้งเตือนด่วนมาก่อน)
        print(f"⏱️ รอบนี้เป็นรอบเช็คงานด่วน (เหลือน้อยกว่า {URGENT_HOURS} ชม.)")
        urgent_events = []
        for item in events:
            time_left = item['due_date'] - now_local
            if timedelta(0) <= time_left <= timedelta(hours=URGENT_HOURS):
                key = event_key(item)
                if key not in notified:
                    urgent_events.append(item)

        if urgent_events:
            message_to_send = generate_urgent_message(urgent_events, now_local)
            for item in urgent_events:
                notified[event_key(item)] = now_local.isoformat()
        else:
            print("✅ ไม่มีงานใกล้หมดเวลาในตอนนี้ ไม่ส่งการแจ้งเตือน")

    save_notified_state(STATE_FILE, notified)

    if message_to_send:
        if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
            print("📤 กำลังส่งการแจ้งเตือนไปยัง LINE...")
            send_line_messaging_api(LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, message_to_send)
        else:
            print("❌ ข้อผิดพลาด: ไม่พบ LINE_CHANNEL_ACCESS_TOKEN หรือ LINE_USER_ID")
    else:
        print("ℹ️ ไม่มีข้อความที่ต้องส่งในรอบนี้")
