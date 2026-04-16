import json
from playwright.sync_api import sync_playwright

def scrape_data():
    data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # الدخول للموقع
            page.goto("https://go.3atabah.com/dl/a400f7", timeout=60000)
            page.wait_for_timeout(8000) # انتظار عشان الموقع يكتمل تحميله
            
            # صيد الروابط الذكي: نبحث عن أي رابط فيه نصوص تدل على التدريب
            links = page.locator('a').all()
            
            for link in links:
                try:
                    text = link.inner_text().strip()
                    href = link.get_attribute('href')
                    
                    # فلترة: نأخذ بس الروابط اللي فيها كلمات معينة وما تكون فاضية
                    if text and href and not href.startswith('javascript'):
                        if 'تدريب' in text or 'تعاوني' in text or 'شركة' in text or 'هيئة' in text or 'برنامج' in text or 'بنك' in text:
                            
                            # تنظيف العنوان
                            clean_title = text.split('\n')[0][:50]
                            
                            # التأكد من صحة الرابط
                            final_link = href if href.startswith('http') else f"https://go.3atabah.com{href}"
                            
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
                    
            # إزالة الفرص المكررة إذا الموقع كررها
            unique_data = []
            seen_titles = set()
            for d in data:
                if d['t'] not in seen_titles:
                    unique_data.append(d)
                    seen_titles.add(d['t'])
            data = unique_data

        except Exception as e:
            print(f"حدث خطأ أثناء السحب: {e}")
        finally:
            browser.close()
    
    # حفظ البيانات. إذا ما لقى شيء، يحفظ ملف فارغ عشان ما تطلع إعلانات
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
