import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import re
import json

# ==================== CONFIGURATION ====================
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

def clean_ical_url(url):
    """ลบอักขระส่วนเกินที่อาจติดมาจาก Secret"""
    if not url:
        return ""
    url = url.strip()
    match = re.search(r'https?://[^\s\]\)\>\"\']+', url)
    if match:
        return match.group(0)
    return url

def unfold_ical(text):
    """ปลดการตัดบรรทัด (Line Folding) ตามมาตรฐาน RFC 5545"""
    return re.sub(r'\r?\n[ \t]', '', text)

def unescape_ical(text):
    """แปลงตัวอักษรพิเศษใน iCal กลับเป็นข้อความปกติ"""
    if not text:
        return ""
    return text.replace('\\,', ',').replace('\\;', ';').replace('\\n', '\n').replace('\\N', '\n').replace('\\\\', '\\')

def parse_ical_datetime(dt_line):
    """
    แปลงวันที่เวลาจาก iCal อย่างแม่นยำ
    - ถ้าเป็น UTC (มี Z ลงท้าย) -> บวก 7 ชั่วโมงเปลี่ยนเป็นเวลาไทย
    - ถ้าเป็นเวลาท้องถิ่นแล้ว -> คงเวลาเดิมไว้ ไม่บวกซ้ำ
    """
    parts = dt_line.split(':')
    dt_val = parts[-1].strip()
    is_utc = dt_val.endswith('Z')
    
    clean_val = dt_val.rstrip('Z')
    if 'T' in clean_val:
        try:
            dt = datetime.strptime(clean_val, "%Y%m%dT%H%M%S")
        except ValueError:
            dt = datetime.strptime(clean_val[:15], "%Y%m%dT%H%M%S")
        
        if is_utc:
            return dt + TZ_OFFSET
        else:
            return dt
    else:
        return datetime.strptime(clean_val[:8], "%Y%m%d")

def fetch_lms_events(ical_url):
    """ดาวน์โหลดและอ่านรายการการบ้านจาก iCal URL"""
    req = urllib.request.Request(
        ical_url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')

    # ปลด Line Folding
    content = unfold_ical(content)

    events = []
    raw_events = content.split('BEGIN:VEVENT')
    now_local = datetime.utcnow() + TZ_OFFSET

    for raw_event in raw_events[1:]:
        summary_match = re.search(r'SUMMARY:(.*)', raw_event)
        dtend_match = re.search(r'DTEND[^\n]*:(.*)', raw_event)
        dtstart_match = re.search(r'DTSTART[^\n]*:(.*)', raw_event)
        desc_match = re.search(r'DESCRIPTION:(.*)', raw_event)

        if not summary_match:
            continue

        title = unescape_ical(summary_match.group(1).strip())
        dt_target = dtend_match.group(0) if dtend_match else (dtstart_match.group(0) if dtstart_match else None)
        
        if not dt_target:
            continue

        try:
            due_date = parse_ical_datetime(dt_target)
        except Exception as e:
            print(f"Error parsing date {dt_target}: {e}")
            continue

        description = unescape_ical(desc_match.group(1).strip()) if desc_match else ""

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

def create_flex_message(events):
    """สร้าง LINE Flex Message สวยงามพร้อมสีสันและปุ่มกด"""
    now = datetime.utcnow() + TZ_OFFSET
    today_str = now.strftime("%d/%m/%Y")

    if not events:
        # Flex Card เมื่อไม่มีงานค้าง
        return {
            "type": "flex",
            "altText": f"🎉 PSU LMS: ไม่มีงานค้างประจำวันที่ {today_str}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#003366",
                    "contents": [
                        {"type": "text", "text": "PSU LMS NOTIFIER", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                        {"type": "text", "text": "รายงานภาระงานค้าง", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                        {"type": "text", "text": f"ประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎉 ยินดีด้วย!", "size": "xl", "weight": "bold", "align": "center", "color": "#28A745"},
                        {"type": "text", "text": "ขณะนี้ไม่มีงานค้างในระบบ PSU LMS", "size": "sm", "align": "center", "color": "#666666", "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "action": {"type": "uri", "label": "เข้าสู่ระบบ PSU LMS", "uri": "https://lms2.psu.ac.th"},
                            "style": "primary",
                            "color": "#003366"
                        }
                    ]
                }
            }
        }

    # สร้างรายการงานในการ์ด (สูงสุด 6 รายการ)
    task_contents = []
    for idx, item in enumerate(events[:6], 1):
        due = item['due_date']
        time_left = due - now
        days_left = time_left.days
        hours_left = int(time_left.seconds // 3600)

        # กำหนดป้ายสีและความเร่งด่วน
        if days_left < 1:
            badge_color = "#DC3545"  # แดง
            badge_text = "🚨 ส่งวันนี้/พรุ่งนี้"
        elif days_left <= 3:
            badge_color = "#FD7E14"  # ส้ม
            badge_text = f"⚠️ เหลือ {days_left} วัน"
        else:
            badge_color = "#20C997"  # เขียวอมฟ้า
            badge_text = f"📌 เหลือ {days_left} วัน"

        due_fmt = due.strftime("%d/%m/%Y %H:%M น.")

        task_box = {
            "type": "box",
            "layout": "vertical",
            "margin": "lg" if idx > 1 else "none",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"{idx}. {item['title']}", "weight": "bold", "size": "sm", "color": "#111111", "flex": 4, "wrap": True},
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": badge_color,
                            "cornerRadius": "md",
                            "paddingAll": "xs",
                            "contents": [
                                {"type": "text", "text": badge_text, "color": "#FFFFFF", "size": "xxs", "weight": "bold", "align": "center"}
                            ],
                            "flex": 2
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "sm",
                    "contents": [
                        {"type": "text", "text": f"• กำหนดส่ง: {due_fmt}", "size": "xs", "color": "#666666"},
                        {"type": "text", "text": f"• คงเหลือ: {days_left} วัน {hours_left} ชั่วโมง", "size": "xs", "color": "#666666"}
                    ]
                },
                {"type": "separator", "margin": "md"}
            ]
        }
        task_contents.append(task_box)

    return {
        "type": "flex",
        "altText": f"🔔 PSU LMS: มีงานค้างทั้งหมด {len(events)} รายการ ({today_str})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#003366",
                "contents": [
                    {"type": "text", "text": "PSU LMS NOTIFIER", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                    {"type": "text", "text": f"งานค้างทั้งหมด {len(events)} รายการ", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                    {"type": "text", "text": f"ข้อมูลประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": task_contents
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {"type": "uri", "label": "เข้าสู่ระบบ PSU LMS2", "uri": "https://lms2.psu.ac.th"},
                        "style": "primary",
                        "color": "#003366"
                    }
                ]
            }
        }
    }

def send_line_flex_message(access_token, to_id, flex_payload):
    """ส่งข้อความรูปแบบ Flex Message ผ่าน LINE Messaging API"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = json.dumps({
        "to": to_id,
        "messages": [flex_payload]
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            print("✅ ส่ง Flex Message แจ้งเตือนเข้า LINE สำเร็จแล้ว!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่ง LINE Messaging API: {e}")

if __name__ == "__main__":
    print("🚀 เริ่มต้นระบบแจ้งเตือน PSU LMS (Flex Design Mode)...")
    
    clean_url = clean_ical_url(ICAL_URL)
    if not clean_url:
        print("❌ ข้อผิดพลาด: ไม่พบค่า LMS_ICAL_URL")
        exit(1)

    print(f"📥 กำลังดาวน์โหลดข้อมูลงานจาก PSU LMS...")
    events = fetch_lms_events(clean_url)
    flex_payload = create_flex_message(events)

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        print("📤 กำลังส่งการแจ้งเตือนรูปแบบ Flex Card ไปยัง LINE...")
        send_line_flex_message(LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, flex_payload)
    else:
        print("❌ ข้อผิดพลาด: ไม่พบ LINE_CHANNEL_ACCESS_TOKEN หรือ LINE_USER_ID")
