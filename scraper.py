import json
import re
import os
import time
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from playwright.sync_api import sync_playwright
import firebase_admin
from firebase_admin import credentials, firestore

# 1. إعداد المفاتيح
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ خطأ: لم يتم العثور على مفتاح الذكاء الاصطناعي!")
    exit()

genai.configure(api_key=API_KEY)

firebase_secret = os.environ.get("FIREBASE_CREDENTIALS")
if not firebase_secret:
    print("❌ خطأ: لم يتم العثور على مفتاح فايربيس!")
    exit()

try:
    cred_dict = json.loads(firebase_secret)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ تم الاتصال بـ Firebase بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بـ Firebase: {e}")
    exit()

def scrape_and_upload():
    sources = [
        {"url": "https://go.3atabah.com/dl/a400f7", "type": "site"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "site"},
        {"url": "https://t.me/s/cooptraning_inksa", "type": "telegram"},
        {"url": "https://t.me/s/nobthacv1", "type": "telegram"}
    ]
    
    # تم التعديل هنا إلى الموديل الأساسي المستقر
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
    
    existing_companies = []
    max_id = 141
    companies_ref = db.collection('companies').stream()
    for doc in companies_ref:
        comp = doc.to_dict()
        existing_companies.append(comp)
        if int(comp.get('id', 0)) > max_id:
            max_id = int(comp.get('id', 0))
            
    next_id = max_id + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for source in sources:
            print(f"\n🔍 جاري فحص المصدر: {source['url']}")
            try:
                content_list = []
                
                if source["type"] == "telegram":
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    res = requests.get(source["url"], headers=headers, timeout=15)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    messages = soup.find_all('div', class_='tgme_widget_message_text')
                    
                    for msg in messages[-15:]: 
                        txt = msg.get_text(separator='\n').strip()
                        if len(txt) > 50: 
                            content_list.append({"text": txt, "is_link": False, "url": source["url"]})
                else:
                    page.goto(source["url"], timeout=60000)
                    page.wait_for_timeout(5000)
                    links = page.locator('a').all()
                    for link in links:
                        text = link.inner_text().strip()
                        href = link.get_attribute('href')
                        if text and href and any(vw in text.lower() for vw in ['تدريب', 'تعاوني', 'coop', 'تمهير']):
                            final_link = href if href.startswith('http') else f"https://www.ewdifh.com{href}"
                            content_list.append({"url": final_link, "is_link": True})

                unique_content = []
                seen_urls = set()
                for item in content_list:
                    if item.get("is_link"):
                        if item["url"] not in seen_urls:
                            unique_content.append(item)
                            seen_urls.add(item["url"])
                    else:
                        unique_content.append(item)
                        
                if source["type"] == "site":
                    unique_content = unique_content[:10]

                print(f"📊 النتيجة: تم العثور على ({len(unique_content)}) عنصر. جاري تحليلها...")

                for item in unique_content:
                    raw_content = ""
                    apply_link = item.get("url", "")
                    
                    if item.get("is_link"):
                        page.goto(item["url"], timeout=60000)
                        page.wait_for_timeout(3000)
                        raw_content = page.inner_text('body')
                        for l in page.locator('a').all():
                            hrf = l.get_attribute('href')
                            txt = l.inner_text()
                            if hrf and hrf.startswith('http') and not any(x in hrf for x in ['ewdifh', '3atabah', 'twitter']):
                                if any(k in txt for k in ['تقديم', 'اضغط', 'رابط', 'Apply', 'careers']):
                                    apply_link = hrf; break
                    else:
                        raw_content = item["text"]

                    prompt = f"""
                    أنت خبير توظيف. اقرأ هذا المحتوى بدقة:
                    {raw_content[:1500]}
                    
                    إذا كان يخص "تدريب تعاوني" أو "تمهير" للطلاب، استخرج JSON:
                    {{
                        "t": "اسم الشركة",
                        "m": "التخصصات المستهدفة (استنتجها من نشاط الشركة لو لم تذكر)",
                        "b": "المزايا",
                        "a": "نبذة عن الشركة ومجال عملها (اكتبها من معرفتك العامة إذا لم يذكر الإعلان)",
                        "s": "مفتوح أو ينتهي قريباً (فارغة إذا التقديم إيميل فقط)",
                        "email": "الإيميل إن وجد",
                        "link": "رابط التقديم المباشر إن وجد"
                    }}
                    لو وظيفة للمحترفين، أرجع [].
                    """
                    
                    time.sleep(7) 
                    
                    try:
                        response = model.generate_content(prompt)
                        clean_txt = response.text.replace("```json", "").replace("```", "").strip()
                        ai_data = json.loads(clean_txt)
                    except Exception as ai_error:
                        err_str = str(ai_error)
                        # هنا غيرنا الاستراتيجية: إذا الرصيد خلص، نوقف السكربت بكرامته!
                        if "429" in err_str or "Quota" in err_str:
                            print("\n🛑 لقد استنفدت باقة جوجل المجانية اليومية! سيتم إيقاف السحب التلقائي، حاول غداً.")
                            browser.close()
                            exit()
                        else:
                            print(f"⚠️ خطأ وتخطي: {err_str}")
                            continue
                    
                    if not isinstance(ai_data, dict) or "t" not in ai_data:
                        continue
                        
                    new_name = ai_data["t"]
                    email_ext = ai_data.get("email", "")
                    if email_ext and "@" not in email_ext: email_ext = ""
                    ai_link = ai_data.get("link", "")
                    
                    final_link = apply_link
                    if not item.get("is_link") and ai_link and ai_link.startswith("http"):
                        final_link = ai_link
                    elif ai_link and ai_link.startswith("http") and ("ewdifh" not in apply_link and "3atabah" not in apply_link):
                        final_link = ai_link
                    
                    matched_ex = None
                    new_clean = re.sub(r'[^\w\s]', '', new_name).replace('أ','ا').replace('إ','ا').replace('ة','ه')
                    for ex in existing_companies:
                        ex_clean = re.sub(r'[^\w\s]', '', ex.get('t','')).replace('أ','ا').replace('إ','ا').replace('ة','ه')
                        if new_clean in ex_clean or ex_clean in new_clean:
                            matched_ex = ex
                            break
                    
                    if matched_ex:
                        updates = {}
                        if not matched_ex.get("email") and email_ext:
                            updates["email"] = email_ext
                        if (not matched_ex.get("e") or matched_ex.get("e") == "#" or "t.me" in matched_ex.get("e")) and final_link and final_link.startswith("http") and "t.me" not in final_link:
                            updates["e"] = final_link
                        if not matched_ex.get("b") and ai_data.get("b"):
                            updates["b"] = ai_data.get("b")
                            
                        if updates:
                            db.collection('companies').document(str(matched_ex['id'])).update(updates)
                            print(f"🔄 تم تحديث (إكمال نواقص): {new_name}")
                            matched_ex.update(updates) 
                        else:
                            print(f"⏩ تخطي (مكتملة 100%): {new_name}")
                        continue
                    
                    new_doc = {
                        "id": next_id,
                        "t": new_name,
                        "c": "live",
                        "l": "السعودية",
                        "e": final_link,
                        "email": email_ext,
                        "m": ai_data.get("m", ""),
                        "b": ai_data.get("b", ""),
                        "a": ai_data.get("a", ""),
                        "s": ai_data.get("s", ""),
                        "isLive": True,
                        "i": "fa-bolt"
                    }
                    
                    db.collection('companies').document(str(next_id)).set(new_doc)
                    print(f"☁️ تم الرفع للسحابة بنجاح: {new_name}")
                    existing_companies.append(new_doc)
                    next_id += 1

            except Exception as e:
                print(f"⚠️ خطأ في فحص المصدر: {e}")
                continue
                
        browser.close()
        print("\n✅ اكتملت المهمة وصارت قاعدة بياناتك محدثة وذكية!")

if __name__ == "__main__":
    scrape_and_upload()
