import json
import re
import os
import google.generativeai as genai
from playwright.sync_api import sync_playwright
import firebase_admin
from firebase_admin import credentials, firestore

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ خطأ: لم يتم العثور على مفتاح الذكاء الاصطناعي!")
    exit()

genai.configure(api_key=API_KEY)

firebase_secret = os.environ.get("FIREBASE_CREDENTIALS")
if not firebase_secret:
    print("❌ خطأ: لم يتم العثور على مفتاح فايربيس السري!")
    exit()

try:
    cred_dict = json.loads(firebase_secret)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح!")
except Exception as e:
    print(f"❌ خطأ في الاتصال بـ Firebase: {e}")
    exit()

def scrape_and_upload():
    sources = [
        {"url": "https://go.3atabah.com/dl/a400f7", "type": "3atabah"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "ewdifh"}
    ]
    
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
        job_links = []
        
        print("🔍 جاري البحث عن الفرص الجديدة...")
        for source in sources:
            try:
                page.goto(source["url"], timeout=60000)
                page.wait_for_timeout(5000)
                links = page.locator('a').all()
                bad_words = ['تواصل', 'الأسئلة', 'تسجيل', 'دخول', 'شروط', 'سياسة']
                
                for link in links:
                    try:
                        text = link.inner_text().strip()
                        href = link.get_attribute('href')
                        is_bad = any(bw in text.lower() for bw in bad_words)
                        
                        if text and href and not href.startswith('javascript') and not is_bad and len(text) > 5:
                            final_link = href if href.startswith('http') else f"https://www.ewdifh.com{href}"
                            if any(vw in text.lower() for vw in ['تدريب', 'تعاوني', 'coop', 'تمهير', 'صيفي', 'خريج']):
                                job_links.append({"url": final_link})
                    except:
                        continue
            except Exception as e:
                print(f"⚠️ خطأ في المصدر: {e}")
                
        unique_jobs = []
        seen = set()
        for job in job_links:
            if job['url'] not in seen:
                unique_jobs.append(job)
                seen.add(job['url'])
                
        unique_jobs = unique_jobs[:10] 
        
        for job in unique_jobs:
            try:
                page.goto(job['url'], timeout=60000)
                page.wait_for_timeout(3000)
                content = page.inner_text('body')
                
                apply_link = job['url']
                for l in page.locator('a').all():
                    hrf = l.get_attribute('href')
                    txt = l.inner_text()
                    if hrf and hrf.startswith('http') and not any(x in hrf for x in ['ewdifh', '3atabah', 'twitter']):
                        if 'تقديم' in txt or 'اضغط' in txt or 'رابط' in txt or 'apply' in hrf.lower() or 'careers' in hrf.lower():
                            apply_link = hrf
                            break

                # العقل الجديد: يجلب الروابط المخفية ويكتب لك تفاصيل الشركة!
                prompt = f"""
                أنت خبير توظيف لطلاب الجامعات ولديك معرفة واسعة بالشركات السعودية والعالمية. اقرأ هذا الإعلان بدقة:
                {content[:3500]}
                
                هل يحتوي الإعلان على فرص "تدريب تعاوني" أو "تدريب ميداني" أو "تمهير" للطلاب؟ 
                إذا نعم، استخرج البيانات كـ JSON بالصيغة التالية:
                {{
                    "t": "اسم الشركة بدقة",
                    "m": "التخصصات المستهدفة",
                    "b": "المزايا",
                    "a": "نبذة عن الشركة ومجال عملها (ماذا تفعل هذه الشركة؟ استخدم معرفتك العامة لكتابة نبذة واضحة واحترافية من سطرين)",
                    "s": "مفتوح أو ينتهي قريباً (اتركها فارغة '' إذا لم يكن هناك طريقة تقديم واضحة)",
                    "email": "الإيميل (إذا لم يُذكر في النص، استخدم معرفتك لاستنتاج إيميل التوظيف لهذه الشركة إن أمكن، وإلا اتركه فارغاً)",
                    "link": "رابط التقديم (إذا لم يُذكر في النص، استخدم معرفتك لوضع الرابط الرسمي لصفحة التوظيف Careers الخاصة بهذه الشركة)"
                }}
                إذا كان لوظائف المحترفين فقط، أرجع [].
                """
                
                response = model.generate_content(prompt)
                clean_response = response.text.replace("```json", "").replace("```", "").strip()
                ai_data = json.loads(clean_response)
                
                if isinstance(ai_data, dict) and "t" in ai_data:
                    new_name = ai_data.get("t", "")
                    
                    is_duplicate = False
                    new_clean = re.sub(r'[^\w\s]', '', new_name).replace('أ','ا').replace('إ','ا').replace('ة','ه')
                    for ex in existing_companies:
                        ex_clean = re.sub(r'[^\w\s]', '', ex.get('t','')).replace('أ','ا').replace('إ','ا').replace('ة','ه')
                        if new_clean in ex_clean or ex_clean in new_clean:
                            is_duplicate = True
                            break
                    
                    if is_duplicate:
                        print(f"⏩ تم التخطي (موجودة مسبقاً): {new_name}")
                        continue
                    
                    email_extracted = ai_data.get("email", "")
                    if email_extracted and "@" not in email_extracted: email_extracted = ""
                    
                    # أخذ الرابط من الذكاء الاصطناعي إذا ما لقينا رابط في الإعلان
                    ai_link = ai_data.get("link", "")
                    final_link = apply_link
                    if ai_link and ai_link.startswith("http") and ("ewdifh" not in apply_link and "3atabah" not in apply_link):
                        final_link = ai_link

                    new_doc = {
                        "id": next_id,
                        "t": new_name,
                        "c": "live",
                        "l": "السعودية",
                        "e": final_link,
                        "email": email_extracted,
                        "m": ai_data.get("m", ""),
                        "b": ai_data.get("b", ""),
                        "a": ai_data.get("a", ""),
                        "s": ai_data.get("s", ""),
                        "isLive": True,
                        "i": "fa-bolt"
                    }
                    
                    db.collection('companies').document(str(next_id)).set(new_doc)
                    print(f"☁️ تم رفع الفرصة للسحابة بنجاح: {new_name}")
                    
                    existing_companies.append(new_doc)
                    next_id += 1

            except Exception as e:
                print(f"⚠️ تجاوز بسبب خطأ في الذكاء الاصطناعي: {e}")
                continue
                
        browser.close()
        print("✅ اكتملت المهمة!")

if __name__ == "__main__":
    scrape_and_upload()
