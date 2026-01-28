import re
import time
import random
import pandas as pd
from datetime import date
from dataclasses import dataclass

from DrissionPage import ChromiumPage, ChromiumOptions

import config


@dataclass
class Row:
    article: str
    seller: str
    ozon_card_price: str


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
    # co.incognito()  # Лучше НЕ использовать инкогнито для Озона, чтобы сохранять куки
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    page = ChromiumPage(co)
    return page


def set_pvz(page, url):
    page.get(url)
    random_sleep(2, 3)

    for txt in ['Принять', 'Понятно', 'Закрыть']:
        btn = page.ele(f'text:{txt}', timeout=1)
        if btn:
            try:
                btn.click()
            except:
                pass

    for txt in ['Сохранить адрес', 'Заберу отсюда', 'Подтвердить']:
        btn = page.ele(f'text:{txt}', timeout=2)
        if btn:
            try:
                btn.click()
            except:
                pass
            break

    page.get(config.BASE_URL)


# ---------- helpers ----------

def parse_price_rub(text: str) -> int | None:
    if not text:
        return None
    t = text.replace('\u2009', ' ').replace('\xa0', ' ')
    m = re.search(r'(\d[\d\s]*)\s*₽', t)
    if not m:
        return None
    return int(m.group(1).replace(' ', ''))


def delivery_days_from_text(text: str) -> int | None:
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


# ---------- seller on card ----------

def parse_seller_from_card(page) -> str:
    """
    В новых карточках Ozon продавец в секции "Магазин",
    и имя магазина лежит в span.b35_3_18-b6 (в вашем HTML это "TopBra").
    Делает несколько попыток:
      1) в блоке с заголовком "Магазин" найти span.b35_3_18-b6
      2) fallback: найти "Магазин" и взять ближайшую ссылку
      3) fallback: старое "Продавец"
    """
    # 1) "Магазин" -> span.b35_3_18-b6
    try:
        shop_title = page.ele('text:Магазин', timeout=2)
        if shop_title:
            root = shop_title.parent(6)  # поднимаемся к секции
            if root:
                name_span = root.ele('css:span.b35_3_18-b6', timeout=1)
                if name_span and norm_text(name_span.text):
                    return norm_text(name_span.text)

                # иногда имя может быть в ссылке/спане рядом
                name_link = root.ele('css:a', timeout=0.5)
                if name_link and norm_text(name_link.text) and "ozon.ru/seller/" in (name_link.attr('href') or ""):
                    return norm_text(name_link.text)
    except:
        pass

    # 2) fallback: попробовать найти ссылку на seller в пределах страницы
    try:
        a = page.ele('css:a[href*="/seller/"]', timeout=1)
        if a and norm_text(a.text):
            return norm_text(a.text)
    except:
        pass

    # 3) fallback: старая разметка "Продавец"
    try:
        seller_ele = page.ele('text:Продавец', timeout=1)
        if seller_ele:
            parent = seller_ele.parent(2)
            return norm_text((parent.text or "").replace("Продавец", ""))
    except:
        pass

    return ""


# ---------- "Есть дешевле" modal ----------

def open_cheaper_modal(page) -> bool:
    btn = page.ele('text:Есть дешевле', timeout=2)
    if not btn:
        return False
    try:
        btn.click()
    except:
        try:
            btn.parent().click()
        except:
            return False

    return bool(page.ele('css:div[data-widget="webSellerList"]', timeout=4))


def close_modal(page):
    try:
        close_btn = page.ele('css:div.b65_4_14-a5 button', timeout=1)
        if close_btn:
            close_btn.click()
            return
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
                shop = norm_text(shop_a.text) if shop_a else ""
                shop_url = shop_a.attr('href') if shop_a else ""

                price_div = card.ele('css:div.pdp_l9b', timeout=0.1)
                price_rub = parse_price_rub(price_div.text if price_div else "")

                del_ele = card.ele('text:Доставим', timeout=0.1)
                delivery_text = norm_text(del_ele.text) if del_ele else ""
                delivery_days = delivery_days_from_text(delivery_text)

                key = (shop, price_rub, delivery_text, shop_url)
                if shop and key not in seen:
                    seen.add(key)
                    offers.append({
                        "shop": shop,
                        "shop_url": shop_url,
                        "price_rub": price_rub,
                        "delivery_text": delivery_text,
                        "delivery_days": delivery_days
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


# ---------- card parsing ----------

def parse_card(page, url):
    page.get(url)
    random_sleep(2, 4)

    if "captcha" in page.title.lower() or "доступ ограничен" in page.html:
        print("Обнаружена капча! Решите её вручную в браузере.")
        time.sleep(15)

    seller = parse_seller_from_card(page)

    price = ""
    try:
        ozon_card_ele = page.ele('text:Ozon Банк', timeout=2)
        if ozon_card_ele:
            container = ozon_card_ele.parent(3)
            text = (container.text or "").replace('\u2009', ' ').replace('\xa0', ' ')
            m = re.search(r'(\d[\d\s]*)\s?₽', text)
            if m:
                price = m.group(1).strip()
    except:
        pass

    cheaper_offers = []
    try:
        if open_cheaper_modal(page):
            random_sleep(1.0, 1.8)
            cheaper_offers = collect_cheaper_offers(page)
            close_modal(page)
    except:
        pass

    return norm_text(seller), norm_text(price), cheaper_offers


def main():
    df = pd.read_excel(config.INPUT_XLSX, header=None)
    articles = df.iloc[:, 0].dropna().astype(str).tolist()

    page = get_page_instance()

    try:
        set_pvz(page, config.PVZ_URL)
    except Exception as e:
        print(f"Ошибка ПВЗ: {e}")

    results = []

    for art in articles:
        print(f"Обработка: {art}")

        search_url = f"{config.BASE_URL}search/?text={art}&from_global=true"
        page.get(search_url)
        random_sleep(2, 3)

        links = page.eles('tag:a@@href:/product/')
        product_url = None

        for link in links:
            href = link.attr('href')
            if href and 'ozon.ru/product/' in href:
                product_url = href.split('?')[0]
                break

        if product_url:
            seller, price, offers = parse_card(page, product_url)

            if offers:
                for off in offers:
                    results.append({
                        "Артикул": art,
                        "URL_товара": product_url,
                        "Магазин_на_карточке": seller,
                        "Цена_Ozon_банк_на_карточке": price,
                        "Магазин_в_Есть_дешевле": off["shop"],
                        "URL_магазина": off["shop_url"],
                        "Цена_в_Есть_дешевле_руб": off["price_rub"],
                        "Доставка_текст": off["delivery_text"],
                        "Дней_до_доставки": off["delivery_days"],
                    })
            else:
                results.append({
                    "Артикул": art,
                    "URL_товара": product_url,
                    "Магазин_на_карточке": seller,
                    "Цена_Ozon_банк_на_карточке": price,
                    "Магазин_в_Есть_дешевле": "",
                    "URL_магазина": "",
                    "Цена_в_Есть_дешевле_руб": "",
                    "Доставка_текст": "",
                    "Дней_до_доставки": "",
                })
        else:
            print("Товар не найден в поиске")
            results.append({
                "Артикул": art,
                "URL_товара": "",
                "Магазин_на_карточке": "Нет в поиске",
                "Цена_Ozon_банк_на_карточке": "",
                "Магазин_в_Есть_дешевле": "",
                "URL_магазина": "",
                "Цена_в_Есть_дешевле_руб": "",
                "Доставка_текст": "",
                "Дней_до_доставки": "",
            })

    pd.DataFrame(results).to_excel(config.OUTPUT_XLSX, index=False)
    print("Готово")


if __name__ == "__main__":
    main()