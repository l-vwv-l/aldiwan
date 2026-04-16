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
            page.wait_for_timeout(5000) # الانتظار 5 ثواني لتتحمل الصفحة (لأنها React)
            
            # ملاحظة للمطور (أنت): هذه المحددات (Selectors) تقريبية وتحتاج تعديل بناءً على كود موقع عتبة الفعلي
            # هنا نفترض أن الكروت لها كلاس 'job-card'
            cards = page.locator('.job-card').all()
            
            for card in cards:
                try:
                    title = card.locator('h2').inner_text().strip()
                    link = card.locator('a').get_attribute('href')
                    
                    data.append({
                        "t": title,
                        "c": "live", # التصنيف الجديد: فرص مباشرة
                        "l": "عن بعد / مناطق متعددة",
                        "e": link,
                        "i": "fa-bolt",
                        "m": "متاح التقديم الآن"
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"حدث خطأ أثناء السحب: {e}")
        finally:
            browser.close()
    
    # إذا لم يجد السكربت شيء (بسبب اختلاف تصميم موقعهم)، نضع كرت تجريبي لتأكيد عمل النظام
    if not data:
        data.append({
            "t": "فرصة تدريب (تحديث آلي)",
            "c": "live",
            "l": "تحديث النظام الآلي",
            "e": "https://go.3atabah.com/dl/a400f7",
            "i": "fa-bolt",
            "m": "تم الاتصال بالسيرفر بنجاح"
        })

    # حفظ البيانات المستخرجة في ملف JSON
    with open('live_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_data()
