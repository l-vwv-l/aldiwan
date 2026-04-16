import json
import re
from playwright.sync_api import sync_playwright

def scrape_data():
    data = []
    sources = [
        {"url": "https://go.3atabah.com/dl/a400f7", "type": "3atabah"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "ewdifh"}
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        job_links = []
        
        # المرحلة 1: تجميع الروابط من الصفحات الرئيسية
        for source in sources:
            try:
                page.goto(source["url"], timeout=60000)
                page.wait_for_timeout(5000)
                links = page.locator('a').all()
                bad_words = ['تواصل', 'عن الموقع', 'الأسئلة', 'تطوير', 'تسجيل', 'دخول', 'home', 'login', 'شروط', 'سياسة']
                
                for link in links:
                    try:
                        text = link.inner_text().strip()
                        href = link.get_attribute('href')
                        is_bad = any(bw in text.lower() for bw in bad_words)
                        
                        if text and href and not href.startswith('javascript') and not is_bad and len(text) > 3:
                            is_valid = False
                            clean_title = text.split('\n')[0].strip()
                            
                            if source["type"] == "3atabah":
                                if ' | ' in clean_title:
                                    clean_title = clean_title.split(' | ')[0].strip()
                                is_valid = True
                            elif source["type"] == "ewdifh":
                                valid_words = ['تدريب', 'تعاوني', 'تمهير', 'صيفي', 'خريج', 'حديثي التخرج']
                                if any(vw in text for vw in valid_words):
                                    is_valid = True
                                    clean_title = re.sub(r'(تعلن|يعلن).*', '', clean_title).strip()
                            
                            if is_valid:
                                final_link = href if href.startswith('http') else f"https://www.ewdifh.com{href}"
                                job_links.append({"title": clean_title, "url": final_link})
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
                
        # أخذ أحدث 10 فرص فقط لتسريع العملية ومنع تعليق السيرفر
        unique_jobs = unique_jobs[:10]
        
        # المرحلة 2: الغوص داخل الإعلانات لسحب البيانات الحقيقية
        for job in unique_jobs:
            try:
                page.goto(job['url'], timeout=60000)
                page.wait_for_timeout(3000)
                content = page.inner_text('body')
                
                # 1. صيد الرابط الرسمي للشركة (تجاهل روابط المواقع الإعلانية)
                apply_link = job['url']
                page_links = page.locator('a').all()
                for l in page_links:
                    hrf = l.get_attribute('href')
                    txt = l.inner_text()
                    if hrf and hrf.startswith('http'):
                        if not any(x in hrf for x in ['ewdifh', '3atabah', 'twitter', 'snapchat', 't.me', 'whatsapp', 'linkedin']):
                            if 'تقديم' in txt or 'اضغط' in txt or 'رابط' in txt or 'apply' in hrf.lower() or 'careers' in hrf.lower():
                                apply_link = hrf
                                break
                                
                # 2. استخراج التخصصات الحقيقية
                majors = "كافة التخصصات ذات الصلة (تأكد من التفاصيل)"
                m_match = re.search(r'التخصصات(?: المطلوبة)?[:\n\s]+(.*?)(?:\n\n|\n[أ-ي])', content, re.DOTALL)
                if m_match and len(m_match.group(1).strip()) > 5:
                    majors = m_match.group(1).strip().replace('\n', '، ')[:120] + "..."
                    
                # 3. استخراج المزايا والمكافآت
                benefits = "مكافأة أو تدريب على رأس العمل حسب سياسة الجهة"
                b_match = re.search(r'(?:المزايا|مزايا البرنامج|مميزات|الشروط والمزايا)[:\n\s]+(.*?)(?:\n\n|\n[أ-ي])', content, re.DOTALL)
                if b_match and len(b_match.group(1).strip()) > 5:
                    benefits = b_match.group(1).strip().replace('\n', '، ')[:120] + "..."
                elif "مكافأة" in content:
                    benefits = "يوجد مكافأة مالية خلال فترة التدريب"
                    
                # 4. النبذة التلقائية
                about = "برنامج تدريبي يهدف إلى صقل مهارات الطلاب والخريجين وتأهيلهم لسوق العمل ببيئة احترافية."
                paragraphs = page.locator('p').all()
                for p in paragraphs:
                    p_txt = p.inner_text().strip()
                    if len(p_txt) > 60 and ("تعلن" in p_txt or "برنامج" in p_txt or "يهدف" in p_txt):
                        about = p_txt[:250] + "..."
                        break
                        
                data.append({
                    "t": job['title'].replace("شركة", "").strip(),
                    "c": "live",
                    "l": "متاح التقديم (محدث آلياً)",
                    "e": apply_link,
                    "i": "fa-bolt",
                    "m": majors,
                    "b": benefits,
                    "a": about
                })
            except Exception as e:
                continue
                
        browser.close()
        
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
