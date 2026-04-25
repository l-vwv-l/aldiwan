import asyncio
import json
import re
import os
import time
import logging
import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from supabase import create_client, Client
from google import genai
from google.genai import types
from thefuzz import fuzz

# إعداد نظام المراقبة (Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 🚀 إعداد مفاتيح Gemini المباشرة
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("لم يتم العثور على مفتاح Gemini!")
    exit()

client = genai.Client(api_key=GEMINI_API_KEY)

# 🚀 إعداد الاتصال بـ Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("لم يتم العثور على مفاتيح Supabase!")
    exit()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("تم الاتصال بـ Supabase بنجاح! 🚀")
except Exception as e:
    logger.error(f"خطأ في الاتصال بـ Supabase: {e}")
    exit()

# تنظيف الأسماء والمقارنة (Fuzzy Matching)
def clean_company_name(name):
    if not name: return ""
    name = re.sub(r'[^\w\s]', '', name).replace('أ','ا').replace('إ','ا').replace('ة','ه')
    words_to_remove = ['شركة', 'مؤسسة', 'السعودية', 'الوطنية', 'لتقنية', 'المحدودة', 'مجموعة']
    for word in words_to_remove:
        name = name.replace(word, '')
    return name.strip()

def is_duplicate(new_name, existing_companies):
    new_clean = clean_company_name(new_name)
    if not new_clean: return None
    
    for ex in existing_companies:
        ex_clean = clean_company_name(ex.get('t',''))
        if ex_clean and fuzz.partial_ratio(new_clean, ex_clean) > 85:
            return ex
    return None

# 🌟 دالة الاستخراج بنظام التجميع عبر Gemini (المكتبة الجديدة)
async def extract_batch_data_with_ai(batch_items):
    combined_text = ""
    for item in batch_items:
        combined_text += f"\n--- إعلان رقم {item['id']} (الرابط: {item['url']}) ---\n{item['text'][:1200]}\n"
        
    prompt = f"""
    أنت خبير توظيف. اقرأ مجموعة الإعلانات التالية واستخرج البيانات كـ JSON.
    {combined_text}
    
    يجب أن يكون الرد بتنسيق JSON حصراً يحتوي على مفتاح "companies" وقيمته مصفوفة (Array):
    {{
        "companies": [
            {{
                "t": "اسم الشركة",
                "m": "التخصصات المستهدفة",
                "category": "صنف الوظيفة (تقنية، إدارية، هندسية، طبية، أخرى)",
                "b": "المزايا",
                "a": "نبذة قصيرة",
                "endDate": "تاريخ الانتهاء YYYY-MM-DD أو null",
                "email": "الإيميل إن وجد",
                "link": "استخدم (الرابط) المرفق مع عنوان الإعلان، أو استخرجه من النص إن اختلف",
                "icon": "اسم أيقونة FontAwesome"
            }}
        ]
    }}
    إذا لم تجد شركات صالحة، أرجع مصفوفة فارغة [].
    """
    
    try:
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        raw_text = response.text
        return json.loads(raw_text).get("companies", [])
    except Exception as e:
        logger.error(f"خطأ في تحليل Gemini: {e}")
        return []

# سحب التليجرام
async def fetch_telegram(url):
    async with aiohttp.ClientSession() as session:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        try:
            async with session.get(url, headers=headers, timeout=15) as res:
                text = await res.text()
                soup = BeautifulSoup(text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                return [{"text": msg.get_text(separator='\n').strip(), "is_link": False, "url": url} 
                        for msg in messages[-10:] if len(msg.get_text(separator='\n').strip()) > 50]
        except Exception as e:
            logger.error(f"خطأ في سحب التليجرام {url}: {e}")
            return []

# الدالة الرئيسية
async def main_scraper():
    sources = [
        {"url": "https://www.wadhefa.com/", "type": "site"},
        {"url": "https://www.ewdifh.com/category/corporate-jobs", "type": "site"},
        {"url": "https://t.me/s/cooptraning_inksa", "type": "telegram"},
        {"url": "https://t.me/s/ewdifh", "type": "telegram"}
    ]
    
    existing_companies = []
    max_id = 0
    try:
        response = supabase.table('companies').select('*').execute()
        existing_companies = response.data
        for comp in existing_companies:
            max_id = max(max_id, int(comp.get('id', 0)))
    except Exception as e:
        logger.error(f"خطأ في جلب البيانات من Supabase: {e}")

    next_id = max_id + 1
    content_list = []

    tg_tasks = [fetch_telegram(s['url']) for s in sources if s['type'] == 'telegram']
    tg_results = await asyncio.gather(*tg_tasks)
    for res in tg_results: content_list.extend(res)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        for source in [s for s in sources if s['type'] == 'site']:
            logger.info(f"فحص الموقع: {source['url']}")
            page = await context.new_page()
            try:
                await page.goto(source['url'], timeout=60000)
                await page.wait_for_timeout(3000)
                links = await page.locator('a').all()
                for link in links:
                    text = await link.inner_text()
                    href = await link.get_attribute('href')
                    if text and href and any(vw in text.lower() for vw in ['تدريب', 'تعاوني', 'coop', 'تمهير']):
                        final_link = href if href.startswith('http') else f"https://www.ewdifh.com{href}"
                        content_list.append({"url": final_link, "is_link": True})
            except Exception as e:
                logger.error(f"خطأ في الموقع {source['url']}: {e}")
            finally:
                await page.close()

        unique_content = list({v['url']:v for v in content_list if 'url' in v}.values())
        logger.info(f"تم العثور على ({len(unique_content)}) رابط/رسالة. جاري جمع النصوص...")

        raw_items = []
        item_counter = 1
        for item in unique_content:
            raw_content = ""
            apply_link = item.get("url", "")
            
            if item.get("is_link"):
                page = await context.new_page()
                try:
                    await page.goto(item["url"], timeout=60000)
                    raw_content = await page.inner_text('body')
                    for l in await page.locator('a').all():
                        hrf = await l.get_attribute('href')
                        txt = await l.inner_text()
                        if hrf and hrf.startswith('http') and not any(x in hrf for x in ['ewdifh', 'twitter']):
                            if any(k in txt for k in ['تقديم', 'رابط', 'Apply']):
                                apply_link = hrf; break
                except Exception:
                    pass
                finally:
                    await page.close()
            else:
                raw_content = item.get("text", "")

            if len(raw_content) > 50:
                raw_items.append({"id": item_counter, "url": apply_link, "text": raw_content})
                item_counter += 1

        logger.info("جاري تحليل النصوص بالذكاء الاصطناعي المباشر (Gemini)... 🤖")
        
        batch_size = 5
        for i in range(0, len(raw_items), batch_size):
            batch = raw_items[i:i+batch_size]
            logger.info(f"إرسال الدفعة ({i//batch_size + 1}) للذكاء الاصطناعي...")
            
            extracted_companies = await extract_batch_data_with_ai(batch)
            
            for comp in extracted_companies:
                if not comp.get("t") or comp.get("t") == "غير محدد": continue
                
                new_name = comp["t"]
                matched_ex = is_duplicate(new_name, existing_companies)
                
                if matched_ex:
                    updates = {}
                    if comp.get("email") and not matched_ex.get("email"): updates["email"] = comp["email"]
                    if comp.get("endDate") and comp["endDate"] != "null": updates["endDate"] = comp["endDate"]
                    if comp.get("link") and matched_ex.get("e") == "#": updates["e"] = comp["link"]
                    
                    if updates:
                        try:
                            supabase.table('companies').update(updates).eq('id', matched_ex['id']).execute()
                            logger.info(f"🔄 تم تحديث: {new_name}")
                        except Exception as e:
                            logger.error(f"خطأ أثناء تحديث {new_name}: {e}")
                else:
                    new_doc = {
                        "id": next_id,
                        "t": new_name,
                        "c": "company",
                        "l": "السعودية",
                        "tags": comp.get("category", "أخرى"),
                        "e": comp.get("link", "#"),
                        "email": comp.get("email", ""),
                        "m": comp.get("m", ""),
                        "b": comp.get("b", ""),
                        "a": comp.get("a", ""),
                        "endDate": comp.get("endDate", "null"),
                        "isLive": True,
                        "timestamp": int(time.time()),
                        "i": comp.get("icon", "fa-building")
                    }
                    try:
                        supabase.table('companies').insert(new_doc).execute()
                        existing_companies.append(new_doc)
                        next_id += 1
                        logger.info(f"✨ تم إضافة: {new_name}")
                    except Exception as e:
                        logger.error(f"خطأ أثناء إضافة {new_name}: {e}")

        await browser.close()
        logger.info("✅ اكتملت العملية بنجاح!")

if __name__ == "__main__":
    asyncio.run(main_scraper())
