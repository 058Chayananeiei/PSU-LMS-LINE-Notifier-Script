import os
import requests

# 🟢 ดึง Token จากระบบ (Environment Variable)
LINE_TOKEN = os.environ.get('LINE_NOTIFY_TOKEN') 
# หรือถ้านามเดิมใช้ LINE_CHANNEL_ACCESS_TOKEN ให้ใช้ os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

def send_line_notify(message):
    if not LINE_TOKEN:
        print("Error: ไม่พบ LINE_TOKEN ในระบบ Secrets")
        return

    url = 'https://notify-api.line.me/api/notify'
    headers = {
        'Authorization': f'Bearer {LINE_TOKEN}'
    }
    data = {'message': message}
    
    response = requests.post(url, headers=headers, data=data)
    print(f"Status Code: {response.status_code}")

if __name__ == '__main__':
    send_line_notify("ทดสอบส่งข้อความแจ้งเตือน")
