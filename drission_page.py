import re
import time
import random
import urllib.parse
import pandas as pd
from DrissionPage import ChromiumPage, ChromiumOptions
from dataclasses import dataclass

import config

@dataclass
class Row:
    article: str
    seller: str
    ozon_card_price: str

def random_sleep(min_s=1.5, max_s=4.0):
    time.sleep(random.uniform(min_s, max_s))

def norm_text(text):
    if not text: return ""
    return re.sub(r"\s+", " ", text).strip()

def get_page_instance():
    # Настройка браузера
    co = ChromiumOptions()
    # co.incognito() # Лучше НЕ использовать инкогнито для Озона, чтобы сохранять куки
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    
    # DrissionPage сам находит Chrome, но можно указать путь:
    # co.set_browser_path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    
    page = ChromiumPage(co)
    return page

def set_pvz(page, url):
    page.get(url)
    random_sleep(2, 3)
    
    # DrissionPage ищет элементы очень просто
    # Попытка закрыть куки/попапы
    for txt in ['Принять', 'Понятно', 'Закрыть']:
        btn = page.ele(f'text:{txt}', timeout=1)
        if btn: btn.click()
    
    # Выбор ПВЗ
    for txt in ['Выбрать', 'Заберу отсюда', 'Подтвердить']:
        btn = page.ele(f'text:{txt}', timeout=2)
        if btn:
            btn.click()
            break
    
    page.get(config.BASE_URL)

def parse_card(page, url):
    page.get(url)
    random_sleep(2, 4)
    
    # Проверка на капчу
    if "captcha" in page.title.lower() or "доступ ограничен" in page.html:
        print("Обнаружена капча! Решите её вручную в браузере.")
        time.sleep(15) # Даем время решить
    
    # Парсинг продавца
    seller = ""
    try:
        # Ищем блок продавца. Логика: найти текст "Продавец", взять родителя, найти ссылку
        seller_ele = page.ele('text:Продавец', timeout=2)
        if seller_ele:
            parent = seller_ele.parent(2) # Поднимаемся на пару уровней вверх
            seller = parent.text
            # Очистка текста
            seller = seller.replace("Продавец", "").strip()
    except:
        pass

    # Парсинг цены
    price = ""
    try:
        # Ищем цену по Ozon карте
        # В DrissionPage мощный поиск по тексту
        ozon_card_ele = page.ele('text:Ozon Карт', timeout=2)
        if ozon_card_ele:
            # Обычно цена находится в блоке рядом или в родителе
            container = ozon_card_ele.parent(3)
            text = container.text
            # Ищем цену регуляркой в тексте контейнера
            m = re.search(r'(\d[\d\s]*)\s?₽', text)
            if m:
                price = m.group(1)
    except:
        pass
        
    return norm_text(seller), norm_text(price)

def main():
    # Чтение Excel
    df = pd.read_excel(config.INPUT_XLSX, header=None)
    articles = df.iloc[:, 0].dropna().astype(str).tolist()
    
    page = get_page_instance()
    
    # 1. Установка ПВЗ
    try:
        set_pvz(page, config.PVZ_URL)
    except Exception as e:
        print(f"Ошибка ПВЗ: {e}")

    results = []

    # 2. Поиск и парсинг
    for art in articles:
        print(f"Обработка: {art}")
        # Формируем ссылку поиска
        search_url = f"{config.BASE_URL}search/?text={art}&from_global=true"
        
        page.get(search_url)
        random_sleep(2, 3)
        
        # Ищем ссылку на первый товар
        # Ссылка должна содержать /product/ и не быть рекламой
        links = page.eles('tag:a@@href:/product/')
        
        product_url = None
        for link in links:
            href = link.attr('href')
            if href and 'ozon.ru/product/' in href:
                product_url = href.split('?')[0]
                break
        
        if product_url:
            seller, price = parse_card(page, product_url)
            results.append({"Артикул": art, "Селлер": seller, "Цена": price})
            print(f"Найдено: {seller} - {price}")
        else:
            print("Товар не найден в поиске")
            results.append({"Артикул": art, "Селлер": "Нет в поиске", "Цена": ""})

    # Сохранение
    pd.DataFrame(results).to_excel(config.OUTPUT_XLSX, index=False)
    print("Готово")

if __name__ == "__main__":
    main()