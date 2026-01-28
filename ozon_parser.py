import re
import time
import random
import pandas as pd
from datetime import date
from DrissionPage import ChromiumPage, ChromiumOptions
import config

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}

def random_sleep(min_s=1.5, max_s=4.0):
    time.sleep(random.uniform(min_s, max_s))

def norm_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()

def get_page_instance():
    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    return ChromiumPage(co)

def set_pvz(page, url):
    page.get(url)
    random_sleep(2, 3)

    for txt in ['Принять', 'Понятно', 'Закрыть']:
        btn = page.ele(f'text:{txt}', timeout=1)
        if btn:
            try: btn.click()
            except: pass

    for txt in ['Сохранить адрес', 'Заберу отсюда', 'Подтвердить']:
        btn = page.ele(f'text:{txt}', timeout=2)
        if btn:
            try: btn.click()
            except: pass
            break

    page.get(config.BASE_URL)

def parse_price_rub(text: str):
    if not text:
        return None
    t = text.replace('\u2009', ' ').replace('\xa0', ' ')
    m = re.search(r'(\d[\d\s]*)\s*₽', t)
    if not m:
        return None
    return int(m.group(1).replace(' ', ''))

def delivery_days_from_text(text: str):
    if not text:
        return None
    t = text.lower().replace('\xa0', ' ').strip()
    today = date.today()

    if "сегодня" in t:
        return 0
    if "завтра" in t:
        return 1

    m = re.search(r'(\d{1,2})\s+([а-я]+)', t)
    if not m:
        return None

    day = int(m.group(1))
    mon = RU_MONTHS.get(m.group(2))
    if not mon:
        return None

    y = today.year
    d = date(y, mon, day)
    if d < today:
        d = date(y + 1, mon, day)
    return (d - today).days

def parse_seller_from_card(page) -> str:
    try:
        shop_title = page.ele('text:Магазин', timeout=2)
        if shop_title:
            root = shop_title.parent(6)
            if root:
                name_span = root.ele('css:span.b35_3_18-b6', timeout=1)
                if name_span and norm_text(name_span.text):
                    return norm_text(name_span.text)
    except:
        pass

    try:
        a = page.ele('css:a[href*="/seller/"]', timeout=1)
        if a and norm_text(a.text):
            return norm_text(a.text)
    except:
        pass

    return ""

def open_cheaper_modal(page) -> bool:
    btn = page.ele('text:Есть дешевле', timeout=2)
    if not btn:
        return False
    try:
        btn.click()
    except:
        try: btn.parent().click()
        except: return False

    return bool(page.ele('css:div[data-widget="webSellerList"]', timeout=4))

def close_modal(page):
    try:
        close_btn = page.ele('css:div.b65_4_14-a5 button', timeout=1)
        if close_btn:
            close_btn.click()
    except:
        pass

def collect_cheaper_offers(page, max_more_clicks=30):
    offers = []
    seen = set()

    root = page.ele('css:div[data-widget="webSellerList"]', timeout=4)
    if not root:
        return offers

    for _ in range(max_more_clicks):
        cards = root.eles('css:div.pdp_mb0') or []
        for card in cards:
            try:
                shop_a = card.ele('css:a.pdp_ea6', timeout=0.1)
                offer_shop = norm_text(shop_a.text) if shop_a else ""
                offer_shop_url = shop_a.attr('href') if shop_a else ""

                price_div = card.ele('css:div.pdp_l9b', timeout=0.1)
                offer_price_rub = parse_price_rub(price_div.text if price_div else "")

                del_ele = card.ele('text:Доставим', timeout=0.1)
                offer_delivery_text = norm_text(del_ele.text) if del_ele else ""
                offer_delivery_days = delivery_days_from_text(offer_delivery_text)

                key = (offer_shop, offer_price_rub, offer_delivery_text, offer_shop_url)
                if offer_shop and key not in seen:
                    seen.add(key)
                    offers.append({
                        "offer_shop": offer_shop,
                        "offer_shop_url": offer_shop_url,
                        "offer_price_rub": offer_price_rub,
                        "offer_delivery_text": offer_delivery_text,
                        "offer_delivery_days": offer_delivery_days
                    })
            except:
                continue

        more_btn = root.ele('css:button.b25_5_2-b7', timeout=1)
        if not more_btn:
            break
        try:
            more_btn.click()
            random_sleep(0.8, 1.5)
        except:
            break

    return offers

def parse_card(page, product_url):
    page.get(product_url)
    random_sleep(2, 4)

    card_shop = parse_seller_from_card(page)

    # цена карточки нам не нужна для RMS, но полезно сохранить
    card_price = None
    try:
        ozon_card_ele = page.ele('text:Ozon Банк', timeout=2)
        if ozon_card_ele:
            container = ozon_card_ele.parent(3)
            text = (container.text or "").replace('\u2009', ' ').replace('\xa0', ' ')
            m = re.search(r'(\d[\d\s]*)\s?₽', text)
            if m:
                card_price = int(m.group(1).replace(' ', ''))
    except:
        pass

    offers = []
    try:
        if open_cheaper_modal(page):
            random_sleep(1.0, 1.8)
            offers = collect_cheaper_offers(page)
            close_modal(page)
    except:
        pass

    return card_shop, card_price, offers

def find_top_product_urls(page, query: str, top_n: int):
    search_url = f"{config.BASE_URL}search/?text={query}&from_global=true"
    page.get(search_url)
    random_sleep(2, 3)

    urls = []
    seen = set()

    links = page.eles('tag:a@@href:/product/')
    for link in links:
        href = link.attr('href')
        if not href:
            continue
        if 'ozon.ru/product/' not in href:
            continue
        u = href.split('?')[0]
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= top_n:
            break

    return urls

def main():
    inp = pd.read_excel(config.INPUT_XLSX)
    page = get_page_instance()

    try:
        set_pvz(page, config.PVZ_URL)
    except Exception as e:
        print(f"Ошибка ПВЗ: {e}")

    out_rows = []

    for _, r in inp.iterrows():
        idea_id = int(r["idea_id"])
        query = str(r["query"])

        print(f"[{idea_id}] query={query}")

        product_urls = find_top_product_urls(page, query, top_n=config.TOP_N_PRODUCTS)
        if not product_urls:
            out_rows.append({
                "idea_id": idea_id,
                "query": query,
                "product_url": "",
                "card_shop": "",
                "card_price_ozon_bank": None,
                "offer_shop": "",
                "offer_shop_url": "",
                "offer_price_rub": None,
                "offer_delivery_days": None,
            })
            continue

        for product_url in product_urls:
            card_shop, card_price, offers = parse_card(page, product_url)

            if offers:
                for off in offers:
                    out_rows.append({
                        "idea_id": idea_id,
                        "query": query,
                        "product_url": product_url,
                        "card_shop": card_shop,
                        "card_price_ozon_bank": card_price,
                        "offer_shop": off["offer_shop"],
                        "offer_shop_url": off["offer_shop_url"],
                        "offer_price_rub": off["offer_price_rub"],
                        "offer_delivery_days": off["offer_delivery_days"],
                    })
            else:
                out_rows.append({
                    "idea_id": idea_id,
                    "query": query,
                    "product_url": product_url,
                    "card_shop": card_shop,
                    "card_price_ozon_bank": card_price,
                    "offer_shop": "",
                    "offer_shop_url": "",
                    "offer_price_rub": None,
                    "offer_delivery_days": None,
                })

    pd.DataFrame(out_rows).to_excel(config.OUTPUT_OFFERS_XLSX, index=False)
    print(f"Saved {config.OUTPUT_OFFERS_XLSX}")

if __name__ == "__main__":
    main()