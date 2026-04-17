import json
import re
import os
import google.generativeai as genai
from playwright.sync_api import sync_playwright

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ خطأ: لم يتم العثور على مفتاح الذكاء الاصطناعي!")
    exit()

genai.configure(api_key=API_KEY)

def scrape_data():
    data = []
    sources = [
        {"url": "[https://go.3atabah.com/dl/a400f7](https://go.3atabah.com/dl/a400f7)", "type": "3atabah"},
        {"url": "[https://www.ewdifh.com/category/corporate-jobs](https://www.ewdifh.com/category/corporate-jobs)", "type": "ewdifh"}
    ]
    
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        job_links = []
        
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
                            final_link = href if href.startswith('http') else f"[https://www.ewdifh.com](https://www.ewdifh.com){href}"
                            
                            # وسعنا نطاق البحث ليلتقط التدريب بشكل أذكى
                            if any(vw in text.lower() for vw in ['تدريب', 'تعاوني', 'coop', 'تمهير']):
                                job_links.append({"url": final_link})
                    except:
                        continue
            except Exception as e:
                print(f"Error source: {e}")
                
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

                # أمر الذكاء الاصطناعي صار أذكى
                prompt = f"""
                أنت خبير توظيف لطلاب الجامعات فقط. اقرأ الإعلان التالي بدقة:
                {content[:3500]}
                
                هل يحتوي الإعلان على فرص "تدريب تعاوني" أو "تدريب ميداني" أو "تمهير" مخصصة للطلاب أو حديثي التخرج؟ 
                إذا كانت الإجابة نعم، استخرج البيانات بدقة كـ JSON بالصيغة التالية:
                {{
                    "t": "اسم الجهة (بدون كلمة يعلن)",
                    "m": "التخصصات المستهدفة",
                    "b": "المزايا",
                    "a": "نبذة عن البرنامج",
                    "s": "مفتوح أو ينتهي قريباً",
                    "email": "الإيميل إن وجد"
                }}
                إذا كان الإعلان لوظائف للمحترفين (أصحاب الخبرة) فقط، أرجع مصفوفة فارغة [].
                لا ترجع أي نص خارج الـ JSON.
                """
                
                response = model.generate_content(prompt)
                
                # تنظيف الكود في حال أرسل الذكاء الاصطناعي علامات Markdown
                clean_response = response.text.replace("```json", "").replace("```", "").strip()
                ai_data = json.loads(clean_response)
                
                if isinstance(ai_data, dict) and "t" in ai_data:
                    email_extracted = ai_data.get("email", "")
                    if email_extracted and "@" not in email_extracted:
                        email_extracted = ""

                    data.append({
                        "t": ai_data.get("t", "غير محدد"),
                        "l": "السعودية",
                        "e": apply_link,
                        "email": email_extracted,
                        "m": ai_data.get("m", ""),
                        "b": ai_data.get("b", ""),
                        "a": ai_data.get("a", ""),
                        "s": ai_data.get("s", "مفتوح")
                    })
            except Exception as e:
                print(f"AI Skip/Error: {e}")
                continue
                
        browser.close()
        
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
