import os
import requests
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import re
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==================== CONFIGURATION ====================
ICAL_URL = os.environ.get("LMS_ICAL_URL", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN", "")

# 📌 รายการงานที่ส่ง/ทำเสร็จแล้ว ให้ข้ามการแจ้งเตือน
IGNORED_KEYWORDS = [
    # "ชื่องานหรือคีย์เวิร์ดที่ทำเสร็จแล้ว"
]

# ➕ งานส่วนตัว/งานนอกระบบ LMS ที่ต้องการบันทึกเพิ่มให้เตือนใน LINE
# ใส่รูปแบบ: {"title": "ชื่องาน", "due": "YYYY-MM-DD HH:MM"}
CUSTOM_TASKS = [
    # {"title": "เตรียมสไลด์นำเสนอโปรเจกต์กลุ่ม", "due": "2026-07-28 13:30"},
]

TZ_OFFSET = timedelta(hours=7)

def clean_ical_url(url):
    if not url: return ""
    url = url.strip()
    match = re.search(r'https?://[^\s\]\)\>\"\']+', url)
    return match.group(0) if match else url

def unfold_ical(text):
    return re.sub(r'\r?\n[ \t]', '', text)

def unescape_ical(text):
    if not text: return ""
    return text.replace('\\,', ',').replace('\\;', ';').replace('\\n', '\n').replace('\\N', '\n').replace('\\\\', '\\')

def parse_ical_datetime(dt_line):
    parts = dt_line.split(':')
    dt_val = parts[-1].strip()
    is_utc = dt_val.endswith('Z')
    clean_val = dt_val.rstrip('Z')
    if 'T' in clean_val:
        try:
            dt = datetime.strptime(clean_val, "%Y%m%dT%H%M%S")
        except ValueError:
            dt = datetime.strptime(clean_val[:15], "%Y%m%dT%H%M%S")
        return dt + TZ_OFFSET if is_utc else dt
    else:
        return datetime.strptime(clean_val[:8], "%Y%m%d")

def fetch_lms_events(ical_url):
    req = urllib.request.Request(ical_url, headers={'User-Agent': 'Mozilla/5.0'})
    events = []
    now_local = datetime.utcnow() + TZ_OFFSET

    # 1. อ่านงานจาก PSU LMS iCal
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
        content = unfold_ical(content)
        raw_events = content.split('BEGIN:VEVENT')

        for raw_event in raw_events[1:]:
            summary_match = re.search(r'SUMMARY:(.*)', raw_event)
            dtend_match = re.search(r'DTEND[^\n]*:(.*)', raw_event)
            dtstart_match = re.search(r'DTSTART[^\n]*:(.*)', raw_event)
            desc_match = re.search(r'DESCRIPTION:(.*)', raw_event)

            if not summary_match: continue
            title = unescape_ical(summary_match.group(1).strip())

            if any(kw.strip().lower() in title.lower() for kw in IGNORED_KEYWORDS if kw.strip()):
                continue

            dt_target = dtend_match.group(0) if dtend_match else (dtstart_match.group(0) if dtstart_match else None)
            if not dt_target: continue

            try:
                due_date = parse_ical_datetime(dt_target)
            except Exception:
                continue

            description = unescape_ical(desc_match.group(1).strip()) if desc_match else ""

            if due_date >= now_local:
                events.append({
                    'title': title,
                    'due_date': due_date,
                    'due_date_iso': due_date.isoformat(),
                    'description': description,
                    'is_custom': False
                })
    except Exception as e:
        print(f"⚠️ ดึงข้อมูล iCal ไม่สำเร็จ: {e}")

    # 2. อ่านงานส่วนตัวเพิ่ม (CUSTOM_TASKS)
    for task in CUSTOM_TASKS:
        try:
            due_date = datetime.strptime(task['due'], "%Y-%m-%d %H:%M")
            if due_date >= now_local:
                events.append({
                    'title': f"📌 {task['title']}",
                    'due_date': due_date,
                    'due_date_iso': due_date.isoformat(),
                    'description': "งานส่วนตัวเพิ่มนอกระบบ LMS",
                    'is_custom': True
                })
        except Exception as e:
            print(f"Error parsing custom task {task}: {e}")

    events.sort(key=lambda x: x['due_date'])
    return events

def create_urgent_tasks_flex(events, now):
    today_str = now.strftime("%d/%m/%Y")
    urgent_events = [item for item in events if (item['due_date'] - now).days <= 3]

    if not urgent_events:
        return {
            "type": "flex",
            "altText": f"✅ PSU LMS: ไม่มีงานเร่งด่วนภายใน 3 วันนี้ ({today_str})",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical", "backgroundColor": "#198754",
                    "contents": [
                        {"type": "text", "text": "PSU LMS URGENT ALERT", "weight": "bold", "color": "#A3E635", "size": "xs"},
                        {"type": "text", "text": "🚨 งานที่ใกล้หมดเวลาส่ง", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                        {"type": "text", "text": f"ประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎉 ชิลๆ ได้เลย!", "size": "xl", "weight": "bold", "align": "center", "color": "#198754"},
                        {"type": "text", "text": "ไม่มีงานที่มีกำหนดส่งภายใน 3 วันนี้ครับ", "size": "sm", "align": "center", "color": "#666666", "margin": "md"}
                    ]
                }
            }
        }

    task_contents = []
    for idx, item in enumerate(urgent_events[:5], 1):
        due = item['due_date']
        time_left = due - now
        days_left = time_left.days
        hours_left = int(time_left.seconds // 3600)
        badge_color = "#DC3545" if days_left < 1 else "#FD7E14"
        badge_text = f"🚨 เหลือ {hours_left} ชม." if days_left < 1 else f"⚠️ เหลือ {days_left} วัน {hours_left} ชม."
        due_fmt = due.strftime("%d/%m/%Y %H:%M น.")

        task_contents.append({
            "type": "box", "layout": "vertical", "margin": "lg" if idx > 1 else "none",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"{idx}. {item['title']}", "weight": "bold", "size": "sm", "color": "#111111", "flex": 4, "wrap": True},
                        {
                            "type": "box", "layout": "vertical", "backgroundColor": badge_color, "cornerRadius": "md", "paddingAll": "xs",
                            "contents": [{"type": "text", "text": badge_text, "color": "#FFFFFF", "size": "xxs", "weight": "bold", "align": "center"}],
                            "flex": 3
                        }
                    ]
                },
                {"type": "text", "text": f"• กำหนดส่ง: {due_fmt}", "size": "xs", "color": "#D63384", "weight": "bold", "margin": "xs"},
                {"type": "separator", "margin": "md"}
            ]
        })

    return {
        "type": "flex",
        "altText": f"🚨 [ด่วน] PSU LMS: งานใกล้หมดเวลา {len(urgent_events)} รายการ ({today_str})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": "#DC3545",
                "contents": [
                    {"type": "text", "text": "PSU LMS URGENT ALERT", "weight": "bold", "color": "#FFC107", "size": "xs"},
                    {"type": "text", "text": f"🚨 งานใกล้หมดเวลา ({len(urgent_events)} รายการ)", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                    {"type": "text", "text": f"ข้อมูลประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                ]
            },
            "body": {"type": "box", "layout": "vertical", "contents": task_contents}
        }
    }

def create_weekly_summary_flex(events, now):
    """สร้าง Flex Card ใบที่ 3: สรุปภาระงานประจำสัปดาห์ (Weekly Workload)"""
    today_str = now.strftime("%d/%m/%Y")
    end_of_week = now + timedelta(days=7)
    weekly_events = [e for e in events if now <= e['due_date'] <= end_of_week]

    # นับจำนวนงานรายวันในสัปดาห์นี้
    day_counts = {}
    for e in weekly_events:
        day_name = e['due_date'].strftime("%A (%d/%m)")
        day_counts[day_name] = day_counts.get(day_name, 0) + 1

    busiest_day = max(day_counts, key=day_counts.get) if day_counts else "ไม่มี"

    return {
        "type": "flex",
        "altText": f"📊 PSU LMS: สรุปภาระงานประจำสัปดาห์ ({len(weekly_events)} รายการ)",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": "#6f42c1",
                "contents": [
                    {"type": "text", "text": "WEEKLY WORKLOAD SUMMARY", "weight": "bold", "color": "#E0C6FF", "size": "xs"},
                    {"type": "text", "text": "📊 สรุปภาระงานประจำสัปดาห์", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                    {"type": "text", "text": f"สัปดาห์วันที่ {today_str} - {end_of_week.strftime('%d/%m/%Y')}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "backgroundColor": "#F3E8FF", "cornerRadius": "md", "paddingAll": "md",
                        "contents": [
                            {"type": "text", "text": f"งานสัปดาห์นี้: {len(weekly_events)} รายการ", "weight": "bold", "color": "#6f42c1", "size": "sm"},
                            {"type": "text", "text": f"วันหนาแน่น: {busiest_day}", "size": "xs", "color": "#555555", "align": "end"}
                        ]
                    }
                ]
            }
        }
    }

def create_all_tasks_flex(events, now):
    today_str = now.strftime("%d/%m/%Y")
    if not events:
        return {
            "type": "flex", "altText": f"🎉 PSU LMS: ไม่มีงานค้างในระบบ ({today_str})",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical", "backgroundColor": "#003366",
                    "contents": [
                        {"type": "text", "text": "PSU LMS ALL TASKS", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                        {"type": "text", "text": "📚 รายงานภาระงานทั้งหมด", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                        {"type": "text", "text": f"ประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎉 ไม่พบงานค้าง!", "size": "xl", "weight": "bold", "align": "center", "color": "#28A745"},
                        {"type": "text", "text": "ขณะนี้ส่งงานครบทุกวิชาแล้วครับ", "size": "sm", "align": "center", "color": "#666666", "margin": "md"}
                    ]
                }
            }
        }

    task_contents = []
    for idx, item in enumerate(events[:6], 1):
        due = item['due_date']
        days_left = (due - now).days
        due_fmt = due.strftime("%d/%m/%Y %H:%M น.")

        task_contents.append({
            "type": "box", "layout": "vertical", "margin": "lg" if idx > 1 else "none",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"{idx}. {item['title']}", "weight": "bold", "size": "sm", "color": "#111111", "flex": 4, "wrap": True},
                        {"type": "text", "text": f"อีก {days_left} วัน", "size": "xs", "color": "#0055a5", "weight": "bold", "align": "end", "flex": 1}
                    ]
                },
                {"type": "text", "text": f"• กำหนดส่ง: {due_fmt}", "size": "xs", "color": "#666666", "margin": "xs"},
                {"type": "separator", "margin": "md"}
            ]
        })

    return {
        "type": "flex", "altText": f"📚 PSU LMS: สรุปงานค้างทั้งหมด {len(events)} รายการ ({today_str})",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": "#003366",
                "contents": [
                    {"type": "text", "text": "PSU LMS ALL TASKS", "weight": "bold", "color": "#80BFFF", "size": "xs"},
                    {"type": "text", "text": f"📚 สรุปงานค้างทั้งหมด ({len(events)} รายการ)", "weight": "bold", "color": "#FFFFFF", "size": "lg", "margin": "xs"},
                    {"type": "text", "text": f"ข้อมูลประจำวันที่ {today_str}", "color": "#E0E0E0", "size": "xs", "margin": "xs"}
                ]
            },
            "body": {"type": "box", "layout": "vertical", "contents": task_contents},
            "footer": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "button", "action": {"type": "uri", "label": "เข้าสู่ระบบ PSU LMS2", "uri": "https://lms2.psu.ac.th"}, "style": "primary", "color": "#003366"}
                ]
            }
        }
    }

def send_line_flex_messages(access_token, to_id, flex_messages):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}
    payload = json.dumps({"to": to_id, "messages": flex_messages}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            print("✅ ส่งแจ้งเตือนเข้า LINE สำเร็จแล้ว!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่ง LINE: {e}")

def save_data_json(events):
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
    print("📁 บันทึกไฟล์ data.json สำเร็จแล้ว!")

if __name__ == "__main__":
    print("🚀 เริ่มต้นระบบแจ้งเตือน PSU LMS...")
    clean_url = clean_ical_url(ICAL_URL)
    events = fetch_lms_events(clean_url)
    now_local = datetime.utcnow() + TZ_OFFSET

    save_data_json(events)

    urgent_flex = create_urgent_tasks_flex(events, now_local)
    weekly_flex = create_weekly_summary_flex(events, now_local)
    all_flex = create_all_tasks_flex(events, now_local)

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        # หากเป็นวันจันทร์ หรือสั่งรันระบบ จะส่งการ์ดสรุปประจำสัปดาห์ด้วย
        messages = [urgent_flex, weekly_flex, all_flex]
        send_line_flex_messages(LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, messages)
