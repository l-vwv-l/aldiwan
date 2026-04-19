import json
import re
import os
import time
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.sync_api import sync_playwright
import firebase_admin
from firebase_admin import credentials, firestore

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    print("❌ خطأ: لم يتم العثور على مفتاح OpenRouter!")
    exit()

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=API_KEY,
)

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

# دالة ذكية لتنظيف أسماء الشركات لمنع التكرار
def clean_company_name(name):
    name = re.sub(r'[^\w\s]', '', name).replace('أ','ا').replace('إ','ا').replace('ة','ه')
    words_to_remove = ['شركة', 'مؤسسة', 'السعودية', 'الوطنية', 'لتقنية', 'المحدودة', 'مجموعة']
    for word in words_to_remove:
        name = name.replace(word, '')
    return name.strip()

def scrape_and_upload():
    sources = [
        {"url": "https://go.3atabah.com/dl/a400f7", "type": "site"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "site"},
        {"url": "https://t.me/s/cooptraning_inksa", "type": "telegram"},
        {"url": "https://t.me/s/nobthacv1", "type": "telegram"}
    ]
    
    existing_companies = []
    max_id = 0
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
                    أنت خبير توظيف. اقرأ الإعلان التالي:
                    {raw_content[:1500]}
                    
                    استخرج البيانات كـ JSON فقط:
                    {{
                        "t": "اسم الشركة فقط",
                        "m": "التخصصات المستهدفة",
                        "b": "المزايا",
                        "a": "نبذة قصيرة عن الشركة",
                        "endDate": "تاريخ انتهاء التقديم بصيغة YYYY-MM-DD. إذا لم يُذكر اكتب null",
                        "email": "الإيميل إن وجد",
                        "link": "رابط التقديم إن وجد",
                        "icon": "اسم أيقونة FontAwesome (مثال: fa-building للشركات، fa-hospital للطب، fa-laptop-code للتقنية، fa-oil-well للبترول، fa-money-bill للبنوك)"
                    }}
                    """
                    
                    ai_data = None
                    models_to_try = [
                        "nvidia/nemotron-3-super-120b-a12b:free",
                        "google/gemma-2-9b-it:free"
                    ]
                    
                    time.sleep(5)
                    
                    for current_model in models_to_try:
                        try:
                            response = client.chat.completions.create(
                                model=current_model,
                                messages=[{"role": "user", "content": prompt}]
                            )
                            raw_text = response.choices[0].message.content.strip()
                            clean_txt = raw_text.replace("```json", "").replace("```", "").strip()
                            match = re.search(r'\{.*\}', clean_txt, re.DOTALL)
                            if match: clean_txt = match.group(0)
                                
                            ai_data = json.loads(clean_txt)
                            print(f"🤖 نجح الذكاء الاصطناعي ({current_model.split('/')[1]}) في قراءة النص.")
                            break 
                        except Exception as ai_error:
                            print(f"⏳ خطأ من الموديل {current_model.split('/')[1]}: {ai_error}")
                            time.sleep(3)
                    
                    # 🌟 هنا نظام الحماية والفضح!
                    if not ai_data or not isinstance(ai_data, dict) or "t" not in ai_data or not ai_data["t"] or ai_data["t"] == "غير محدد":
                        print(f"⚠️ تم تخطي هذا العنصر لأن الذكاء الاصطناعي لم يجد بيانات شركة صالحة فيه.")
                        continue
                        
                    new_name = ai_data["t"]
                    email_ext = ai_data.get("email", "")
                    if email_ext and "@" not in email_ext: email_ext = ""
                    ai_link = ai_data.get("link", "")
                    
                    final_link = apply_link
                    if not item.get("is_link") and ai_link and ai_link.startswith("http"): final_link = ai_link
                    
                    # نظام فلترة قوي جداً لمنع التكرار
                    matched_ex = None
                    new_clean = clean_company_name(new_name)
                    for ex in existing_companies:
                        ex_clean = clean_company_name(ex.get('t',''))
                        # مقارنة ذكية (لو تشابهوا بنسبة كبيرة يتجاهلها)
                        if new_clean and ex_clean and (new_clean in ex_clean or ex_clean in new_clean):
                            matched_ex = ex
                            break
                    
                    if matched_ex:
                        updates = {}
                        if not matched_ex.get("email") and email_ext: updates["email"] = email_ext
                        if (not matched_ex.get("e") or matched_ex.get("e") == "#") and final_link and final_link.startswith("http"): updates["e"] = final_link
                        
                        # تحديث التاريخ لو كان موجود في الجديد
                        if ai_data.get("endDate") and ai_data.get("endDate") != "null":
                            updates["endDate"] = ai_data.get("endDate")
                            
                        if updates:
                            db.collection('companies').document(str(matched_ex['id'])).update(updates)
                            print(f"🔄 تم تحديث وإكمال نواقص: {new_name}")
                        else:
                            print(f"⏩ مكرر/مكتمل فتجاهلناه: {new_name}")
                        continue
                    
                    new_doc = {
                        "id": next_id,
                        "t": new_name,
                        "c": "company",
                        "l": "السعودية",
                        "e": final_link,
                        "email": email_ext,
                        "m": ai_data.get("m", ""),
                        "b": ai_data.get("b", ""),
                        "a": ai_data.get("a", ""),
                        "endDate": ai_data.get("endDate", "null"),
                        "isLive": True,
                        "timestamp": int(time.time()), # العداد الزمني (3 أيام)
                        "i": ai_data.get("icon", "fa-building")
                    }
                    
                    db.collection('companies').document(str(next_id)).set(new_doc)
                    print(f"✨ تم إضافة شركة جديدة للموقع: {new_name}")
                    existing_companies.append(new_doc)
                    next_id += 1

            except Exception as e:
                print(f"❌ خطأ غير متوقع: {e}")
                continue
                
        browser.close()
        print("\n✅ تم التحديث بنجاح!")

if __name__ == "__main__":
    scrape_and_upload()
