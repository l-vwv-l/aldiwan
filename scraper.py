import json
from playwright.sync_api import sync_playwright

def scrape_data():
    data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto("https://go.3atabah.com/dl/a400f7", timeout=60000)
            page.wait_for_timeout(8000) # انتظار ليحمل الموقع
            
            # سحب كل الروابط في الصفحة
            links = page.locator('a').all()
            
            bad_words = ['تواصل', 'عن الموقع', 'الأسئلة', 'تطوير', 'تسجيل', 'دخول', 'home', 'login']
            
            for link in links:
                try:
                    text = link.inner_text().strip()
                    href = link.get_attribute('href')
                    
                    # استبعاد الروابط الفارغة أو روابط القائمة العلوية
                    is_bad = any(bw in text.lower() for bw in bad_words)
                    
                    if text and href and not href.startswith('javascript') and not is_bad and len(text) > 3:
                        
                        # تنظيف اسم الشركة (أخذ الجزء العربي لو كان فيه إنجليزي)
                        clean_title = text.split('\n')[0].strip()
                        if ' | ' in clean_title:
                            clean_title = clean_title.split(' | ')[0].strip() # مثل: أرامكو السعودية
                            
                        final_link = href if href.startswith('http') else f"https://go.3atabah.com{href}"
                        
                        data.append({
                            "t": clean_title,
                            "c": "live",
                            "l": "التقديم متاح حالياً (محدث)",
                            "e": final_link,
                            "i": "fa-bolt",
                            "m": "فرصة مسحوبة آلياً ⚡"
                        })
                except Exception:
                    continue
                    
            # إزالة التكرار
            unique_data = []
            seen_titles = set()
            for d in data:
                if d['t'] not in seen_titles:
                    unique_data.append(d)
                    seen_titles.add(d['t'])
            data = unique_data

        except Exception as e:
            print(f"حدث خطأ: {e}")
        finally:
            browser.close()
    
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
