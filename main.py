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
    """ลบอักขระส่วนเกินที่อาจติดมาจาก Secret หรือการ Copy"""
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
    """แปลงวันที่เวลาจาก iCal อย่างแม่นยำ"""
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

        # กรองเฉพาะงานที่ยังไม่หมดเวลาส่งจริง ๆ (ตัดงานที่ครบกำหนดไปแล้วออกทันที
        # เพื่อไม่ให้เหลืองานค้างที่แสดงผลเป็น "เหลือ -1 วัน" ทั้งในเว็บและ LINE)
        if due_date >= now_local:
            events.append({
                'title': title,
                'due_date': due_date,
                'due_date_iso': due_date.isoformat(),
                'description': description
            })

    events.sort(key=lambda x: x['due_date'])
    return events

def create_urgent_tasks_flex(events, now):
    """สร้าง Flex Card ใบที่ 1: เน้นเฉพาะงานที่ใกล้หมดเวลาส่ง (ส่งภายใน 3 วัน)"""
    today_str = now.strftime("%d/%m/%Y")
    
    # กรองเฉพาะงานที่เหลือเวลา <= 3 วัน
    urgent_events = []
    for item in events:
        time_left = item['due_date'] - now
        if time_left.days <= 3:
            urgent_events.append(item)

    if not urgent_events:
        # การ์ดเมื่อไม่มีงานเร่งด่วน
        return {
            "type": "flex",
            "altText": f"✅ PSU LMS: ไม่มีงานเร่งด่วนภายใน 3 วันนี้ ({today_str})",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#198754", # สีเขียว
                    "contents": [
                        {"type": "text", "text": "PSU LMS URGENT ALERT", "weight": "bold", "color": "#A3E635", "size": "xs"},
                        {"type": "text", "text": "🚨 งานที่ใกล้หมดเวลาส่ง", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                        {"type": "text", "text": f"ประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎉 ชิลๆ ได้เลย!", "size": "xl", "weight": "bold", "align": "center", "color": "#198754"},
                        {"type": "text", "text": "ไม่มีงานที่มีกำหนดส่งภายใน 3 วันนี้ครับ", "size": "sm", "align": "center", "color": "#666666", "margin": "md"}
                    ]
                }
            }
        }

    # สร้างรายการงานเร่งด่วนในการ์ด
    task_contents = []
    for idx, item in enumerate(urgent_events[:5], 1):
        due = item['due_date']
        time_left = due - now
        days_left = time_left.days
        hours_left = int(time_left.seconds // 3600)

        if days_left < 1:
            badge_color = "#DC3545"  # แดงเข้ม
            badge_text = f"🚨 ด่วนมาก! เหลือ {hours_left} ชม."
        else:
            badge_color = "#FD7E14"  # ส้ม
            badge_text = f"⚠️ เหลือ {days_left} วัน {hours_left} ชม."

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
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "sm",
                    "contents": [
                        {"type": "text", "text": f"• กำหนดส่ง: {due_fmt}", "size": "xs", "color": "#D63384", "weight": "bold"},
                    ]
                },
                {"type": "separator", "margin": "md"}
            ]
        }
        task_contents.append(task_box)

    return {
        "type": "flex",
        "altText": f"🚨 [ด่วน] PSU LMS: งานใกล้หมดเวลา {len(urgent_events)} รายการ ({today_str})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#DC3545", # สีแดงเตือนภัย
                "contents": [
                    {"type": "text", "text": "PSU LMS URGENT ALERT", "weight": "bold", "color": "#FFC107", "size": "xs"},
                    {"type": "text", "text": f"🚨 งานใกล้หมดเวลา ({len(urgent_events)} รายการ)", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                    {"type": "text", "text": f"ข้อมูลประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": task_contents
            }
        }
    }

def create_all_tasks_flex(events, now):
    """สร้าง Flex Card ใบที่ 2: สรุปรายการงานค้างทั้งหมด"""
    today_str = now.strftime("%d/%m/%Y")

    if not events:
        return {
            "type": "flex",
            "altText": f"🎉 PSU LMS: ไม่มีงานค้างในระบบ ({today_str})",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#003366",
                    "contents": [
                        {"type": "text", "text": "PSU LMS ALL TASKS", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                        {"type": "text", "text": "📚 รายงานภาระงานทั้งหมด", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                        {"type": "text", "text": f"ประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎉 ไม่พบงานค้าง!", "size": "xl", "weight": "bold", "align": "center", "color": "#28A745"},
                        {"type": "text", "text": "ขณะนี้ส่งงานครบทุกวิชาแล้วครับ", "size": "sm", "align": "center", "color": "#666666", "margin": "md"}
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

    task_contents = []
    for idx, item in enumerate(events[:6], 1):
        due = item['due_date']
        time_left = due - now
        days_left = time_left.days

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
                        {"type": "text", "text": f"อีก {days_left} วัน", "size": "xs", "color": "#0055a5", "weight": "bold", "align": "end", "flex": 1}
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"• กำหนดส่ง: {due_fmt}", "size": "xs", "color": "#666666"}
                    ]
                },
                {"type": "separator", "margin": "md"}
            ]
        }
        task_contents.append(task_box)

    return {
        "type": "flex",
        "altText": f"📚 PSU LMS: สรุปงานค้างทั้งหมด {len(events)} รายการ ({today_str})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#003366",
                "contents": [
                    {"type": "text", "text": "PSU LMS ALL TASKS", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                    {"type": "text", "text": f"📚 สรุปงานค้างทั้งหมด ({len(events)} รายการ)", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
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

def send_line_flex_messages(access_token, to_id, flex_messages):
    """ส่งข้อความรูปแบบ Flex Messages หลายใบเข้า LINE พร้อมกันในครั้งเดียว"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    payload = json.dumps({
        "to": to_id,
        "messages": flex_messages
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            print("✅ ส่งแจ้งเตือน (งานเร่งด่วน + งานทั้งหมด) เข้า LINE สำเร็จแล้ว!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่ง LINE Messaging API: {e}")

def save_data_json(events):
    """ส่งออกไฟล์ data.json เพื่อให้หน้าเว็บ index.html แสดงผลข้อมูลตรงกัน 100%"""
    now = datetime.utcnow() + TZ_OFFSET
    json_data = {
        "last_updated": now.strftime("%d/%m/%Y %H:%M:%S"),
        "total_tasks": len(events),
        "events": [
            {
                "title": item["title"],
                "due_date": item["due_date_iso"],
                "description": item["description"]
            }
            for item in events
        ]
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print("📁 สร้างไฟล์ data.json สำเร็จแล้ว!")

if __name__ == "__main__":
    print("🚀 เริ่มต้นระบบแจ้งเตือน PSU LMS (โหมดแยกแจ้งเตือนด่วน + สรุปทั้งหมด)...")
    
    clean_url = clean_ical_url(ICAL_URL)
    if not clean_url:
        print("❌ ข้อผิดพลาด: ไม่พบค่า LMS_ICAL_URL")
        exit(1)

    print("📥 กำลังดาวน์โหลดข้อมูลงานจาก PSU LMS...")
    events = fetch_lms_events(clean_url)
    now_local = datetime.utcnow() + TZ_OFFSET

    # บันทึกไฟล์ data.json สำหรับหน้าเว็บ
    save_data_json(events)

    # สร้างการ์ด 2 ใบ (1. งานด่วน + 2. งานทั้งหมด)
    urgent_flex = create_urgent_tasks_flex(events, now_local)
    all_flex = create_all_tasks_flex(events, now_local)

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        print("📤 กำลังส่งการแจ้งเตือน 2 ข้อความแยกกันไปยัง LINE...")
        send_line_flex_messages(LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, [urgent_flex, all_flex])
    else:
        print("❌ ข้อผิดพลาด: ไม่พบ LINE_CHANNEL_ACCESS_TOKEN หรือ LINE_USER_ID")
