# 🎓 PSU LMS Calendar & LINE Notifier Dashboard

[![PSU Brand Logo](psu_logo.svg)](https://lms.psu.ac.th)

**PSU LMS Calendar & LINE Notifier** เป็นระบบบริหารจัดการการบ้าน ปฏิทินกำหนดส่งงาน และส่งการ์ดแจ้งเตือนเข้า LINE Official Account แบบอัตโนมัติ สำหรับนักศึกษามหาวิทยาลัยสงขลานครินทร์ (Prince of Songkla University)

---

## 🌟 ฟีเจอร์หลัก (Core Features)

1. **🗓️ ปฏิทินและรายการภาระงาน (Calendar & Task List)**:
   - แสดงผลกำหนดส่งงานจาก PSU LMS iCal แบบเรียลไทม์
   - รองรับการค้นหางาน (Live Search) และกรองรายวิชา
   - เพิ่มงานส่วนตัว/งานนอกระบบเพิ่มเติมได้ตามต้องการ
   - ส่งออกปฏิทิน iCal (`.ics`) สำหรับ Apple Calendar / Google Calendar / Outlook
2. **🌙 Focus Mode (โหมดอ่านหนังสือ/ปิดเสียงเตือน)**:
   - ปิดเสียงแจ้งเตือนชั่วคราว (1 ชม., 3 ชม., ตลอดคืน)
   - **Smart Emergency Bypass**: อนุญาตเฉพาะงานด่วนเร่งด่วน (< 2 ชม.) ให้ส่งเตือนได้
3. **🎮 Gamification & XP Progress**:
   - ระบบสะสมพลัง `+150 XP` เมื่อส่งงานทันกำหนด
   - นับวันส่งงานต่อเนื่อง `🔥 5-Day Streak`
   - ปลดล็อกเหรียญรางวัล (e.g. `🏆 Early Bird Slayer`) และแสดงผลหลอดพลัง `[████████░░] 75%`
4. **📱 LINE Flex Studio & Micro-copy Generator**:
   - จำลองการ์ด Flex Message 5 สไตล์บนหน้าเว็บ
   - ปุ่มคัดลอกโค้ด LINE Flex JSON 1-Click สำหรับ LINE Flex Message Simulator
   - คลังข้อความคำพูดแจ้งเตือน (Micro-copy) 5 สไตล์ สำหรับส่งหาเพื่อนใน LINE Chat

---

## 🔒 ขั้นตอนการอัปโหลดขึ้น GitHub อย่างปลอดภัย (Secure GitHub Setup)

เนื่องจากระบบมีการใช้ **LINE Messaging API Channel Access Token**, **User ID** และ **iCal URL**  
**ห้ามฮาร์ดโค้ด (Hardcode) รหัสลับลงในไฟล์โค้ดโดยเด็ดขาด** ให้ปฏิบัติตามขั้นตอนดังนี้:

### Step 1: ตรวจสอบความปลอดภัยก่อน Push โค้ด
โปรเจกต์นี้ได้รับการตั้งค่าไฟล์ `.gitignore` และ `.env.example` เรียบร้อยแล้ว  
ไฟล์รหัสลับ เช่น `.env`, `psu_github_pat`, `notified_state.json` จะไม่ถูกส่งขึ้น GitHub

### Step 2: Push โค้ดขึ้น GitHub
```bash
git add .
git commit -m "feat: upgrade PSU LMS Dashboard & LINE Notifier Studio"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/PSU-LMS-LINE-Notifier-Script.git
git push -u origin main
```

### Step 3: ตั้งค่า Secrets ใน GitHub Repository (สำคัญมาก ⚠️)
1. ไปที่ GitHub Repository ของคุณ ➔ **Settings** ➔ **Secrets and variables** ➔ **Actions**
2. กดปุ่ม **New repository secret** และเพิ่มตัวแปรต่อไปนี้:

| Secret Name | รายละเอียด / วิธีการเอาค่า |
| :--- | :--- |
| `LMS_ICAL_URL` | ลิงก์ iCal Export จาก PSU LMS (`https://lms.psu.ac.th`) |
| `LINE_CHANNEL_ACCESS_TOKEN` | Channel Access Token จาก [LINE Developers Console](https://developers.line.biz) |
| `LINE_USER_ID` | Your User ID จาก LINE Developers Console |
| `LINE_NOTIFY_TOKEN` | *(Optional)* Token สำหรับ LINE Notify เดิม |

---

## 🤖 ระบบอัตโนมัติ GitHub Actions

ระบบตั้งค่า Workflow อัตโนมัติไว้ใน `.github/workflows/daily_notify.yml`:
* **รันอัตโนมัติทุกๆ 2 ชั่วโมง**: ดึงข้อมูล iCal ล่าสุดจาก PSU LMS และยิงแจ้งเตือนการ์ดด่วนเข้า LINE
* **Manual Dispatch**: สามารถกดปุ่ม `Run workflow` บนหน้าเว็บ GitHub เพื่อสั่งรันได้ทันที

---

## 💻 การรันโปรเจกต์บนเครื่องตนเอง (Local Development)

1. ติดตั้ง Dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. สร้างไฟล์ `.env` จากตัวอย่าง:
   ```bash
   cp .env.example .env
   ```
3. กรอกข้อมูล credentials ในไฟล์ `.env`
4. ทดสอบรันสคริปต์ Python:
   ```bash
   python main.py
   ```
5. ดับเบิลคลิกไฟล์ `index.html` เพื่อเปิดใช้งาน Web Dashboard ในเบราว์เซอร์

---

## 📄 License & Attribution

พัฒนาโดยความร่วมมือสำหรับนักศึกษามหาวิทยาลัยสงขลานครินทร์ (Prince of Songkla University)  
**Logo Attribution:** Official Brand Assets of Prince of Songkla University (PSU)