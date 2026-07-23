import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import re
import json

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
    # เช่น "[https://...]" ซึ่งจะทำให้ urllib มองว่าเป็น URL scheme ที่ไม่รู้จัก
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
    """สร้างข้อความสรุปงานรูปแบบข้อความธรรมดา"""
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
    message = generate_plain_message(events)

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        print("📤 กำลังส่งการแจ้งเตือนไปยัง LINE...")
        send_line_messaging_api(LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, message)
    else:
        print("❌ ข้อผิดพลาด: ไม่พบ LINE_CHANNEL_ACCESS_TOKEN หรือ LINE_USER_ID")
