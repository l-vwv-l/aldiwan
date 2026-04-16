import json
from playwright.sync_api import sync_playwright

def scrape_data():
    data = []
    
    # قائمة المواقع اللي بنصيد منها (عتبة + أي وظيفة)
    sources = [
        {"url": "https://go.3atabah.com/dl/a400f7", "type": "3atabah"},
        {"url": "https://www.ewdifh.com", "type": "ewdifh"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "ewdifh"}
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for source in sources:
            try:
                page = browser.new_page()
                page.goto(source["url"], timeout=60000)
                page.wait_for_timeout(6000) # انتظار عشان الموقع يكتمل تحميله
                
                links = page.locator('a').all()
                
                # كلمات نستبعدها عشان ما نسحب روابط قوائم الموقع
                bad_words = ['تواصل', 'عن الموقع', 'الأسئلة', 'تطوير', 'تسجيل', 'دخول', 'home', 'login', 'شروط', 'سياسة', 'حول']
                
                for link in links:
                    try:
                        text = link.inner_text().strip()
                        href = link.get_attribute('href')
                        
                        is_bad = any(bw in text.lower() for bw in bad_words)
                        
                        if text and href and not href.startswith('javascript') and not is_bad and len(text) > 3:
                            
                            is_valid = False
                            clean_title = text.split('\n')[0].strip()
                            
                            if source["type"] == "3atabah":
                                # موقع عتبة (مخصص للتدريب، نأخذ كل الروابط تقريباً)
                                if ' | ' in clean_title:
                                    clean_title = clean_title.split(' | ')[0].strip()
                                is_valid = True
                                
                            elif source["type"] == "ewdifh":
                                # موقع أي وظيفة (نأخذ بس اللي يخص التدريب والخريجين)
                                valid_words = ['تدريب', 'تعاوني', 'تمهير', 'صيفي', 'خريج', 'حديثي التخرج']
                                if any(vw in text for vw in valid_words):
                                    is_valid = True
                            
                            if is_valid:
                                # تضبيط الرابط لو كان ناقص (Relative URL)
                                final_link = href
                                if href.startswith('/'):
                                    domain = "https://go.3atabah.com" if source["type"] == "3atabah" else "https://www.ewdifh.com"
                                    final_link = f"{domain}{href}"
                                
                                data.append({
                                    "t": clean_title,
                                    "c": "live",
                                    "l": "التقديم متاح حالياً",
                                    "e": final_link,
                                    "i": "fa-bolt",
                                    "m": "تم التحديث آلياً ⚡"
                                })
                    except Exception:
                        continue
                page.close()
            except Exception as e:
                print(f"Error scraping {source['url']}: {e}")
                
        browser.close()
        
    # تنظيف التكرارات (لو نفس الفرصة نازلة في الموقعين، ندمجها عشان ما يزعج الطالب)
    unique_data = []
    seen_titles = set()
    for d in data:
        # نعتمد على أول 3 كلمات كمفتاح لمنع التكرار
        key = " ".join(d['t'].split()[:3]) 
        if key not in seen_titles:
            unique_data.append(d)
            seen_titles.add(key)
            
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
