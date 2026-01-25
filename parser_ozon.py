import re
import time
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple
import urllib.parse

import pandas as pd
from playwright.sync_api import sync_playwright, Page, BrowserContext

import config


def random_sleep(min_s=1.0, max_s=3.0):
    """Случайная задержка для имитации человека"""
    time.sleep(random.uniform(min_s, max_s))


def inject_stealth(context: BrowserContext):
    """
    Внедряем JS-скрипты, скрывающие признаки автоматизации.
    Заменяет библиотеку playwright-stealth.
    """
    # 1. Скрываем navigator.webdriver
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # 2. Подделываем navigator.plugins (у роботов он часто пустой)
    context.add_init_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """)

    # 3. Добавляем window.chrome (есть в обычном Chrome, нет в чистом Playwright)
    context.add_init_script("""
        window.chrome = { runtime: {} };
    """)

    # 4. Подделываем разрешения
    context.add_init_script("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: 'granted', onchange: null }) :
            originalQuery(parameters)
        );
    """)


def norm_price(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def safe_text(page: Page, selector: str) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        if loc.count() == 0:
            return None
        t = loc.inner_text(timeout=1500)
        return re.sub(r"\s+", " ", t).strip()
    except Exception:
        return None


def click_if_exists(page: Page, selector: str) -> bool:
    try:
        loc = page.locator(selector).first
        if loc.count() == 0:
            return False
        # Имитация наведения перед кликом
        loc.hover(timeout=1000)
        time.sleep(random.uniform(0.2, 0.5))
        loc.click(timeout=2000)
        return True
    except Exception:
        return False


def set_pvz(page: Page, pvz_url: str) -> None:
    page.goto(pvz_url, wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
    random_sleep(1.5, 2.5)

    for sel in [
        "button:has-text('Принять')",
        "button:has-text('Согласен')",
        "button:has-text('Понятно')",
        "button:has-text('Закрыть')",
        "[aria-label='Закрыть']",
    ]:
        click_if_exists(page, sel)

    for sel in [
        "button:has-text('Выбрать')",
        "button:has-text('Выбрать этот пункт')",
        "button:has-text('Подтвердить')",
        "button:has-text('Заберу отсюда')",
        "button:has-text('Сделать основным')",
    ]:
        if click_if_exists(page, sel):
            random_sleep(1.5, 2.0)
            break

    page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
    random_sleep(1.5, 2.5)


def collect_search_product_links(page: Page, query: str, limit: int) -> List[str]:
    search_url = f"{config.BASE_URL}search/?text={urllib.parse.urlencode({'': query})[1:]}"
    print(f"Search_url : {search_url}")
    
    page.goto(search_url, wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
    random_sleep(2.0, 3.5)

    # Движение мышью
    try:
        page.mouse.move(random.randint(100, 500), random.randint(100, 500))
    except Exception:
        pass

    for sel in [
        "button:has-text('Принять')",
        "[aria-label='Закрыть']",
        "button:has-text('Закрыть')",
    ]:
        click_if_exists(page, sel)

    links = []
    seen = set()
    product_link_locator = page.locator("a[href*='/product/']")

    stable_rounds = 0
    last_count = 0

    while len(links) < limit and stable_rounds < 4:
        random_sleep(config.SCROLL_PAUSE_SEC, config.SCROLL_PAUSE_SEC + 1.5)

        try:
            cnt = product_link_locator.count()
            print(f"cnt : {cnt}")
        except Exception:
            cnt = 0

        for i in range(min(cnt, 300)):
            try:
                href = product_link_locator.nth(i).get_attribute("href")
            except Exception:
                continue
            if not href:
                continue
            if href.startswith("/"):
                href = config.BASE_URL.rstrip("/") + href
            href = href.split("?")[0]
            if "/product/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            links.append(href)
            if len(links) >= limit:
                break

        # Скролл
        scroll_y = random.randint(700, 1200)
        page.mouse.wheel(0, scroll_y)
        
        if len(links) == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = len(links)

    return links[:limit]


def extract_seller_default(page: Page) -> Optional[str]:
    try:
        anchor = page.locator("text=Продавец").first
        if anchor.count() > 0:
            parent = anchor.locator("xpath=ancestor::*[self::div or self::section][1]")
            txt = parent.inner_text(timeout=2000)
            txt = re.sub(r"\s+", " ", txt).strip()
            m = re.search(r"Продавец\s*[:\-]?\s*(.+?)(?:\s{2,}|$)", txt)
            if m:
                cand = m.group(1).strip()
                if 2 <= len(cand) <= 120:
                    return cand
    except Exception:
        pass

    for sel in [
        "a[href*='/seller/']",
        "a[href*='/shop/']",
    ]:
        t = safe_text(page, sel)
        if t and len(t) <= 120:
            return t

    return None


def extract_ozon_card_price(page: Page) -> Optional[str]:
    patterns = [
        "text=/по\\s+ozon\\s*карте/i",
        "text=/ozon\\s*карте/i",
        "text=/ozon\\s*карта/i",
        "text=/по\\s+карте/i",
    ]
    rub_price_re = re.compile(r"(\d[\d\s]*)(?:\s*₽|₽)")

    for p in patterns:
        try:
            anchor = page.locator(p).first
            if anchor.count() == 0:
                continue

            for xp in [
                "xpath=ancestor::div[1]",
                "xpath=ancestor::div[2]",
                "xpath=ancestor::section[1]",
                "xpath=ancestor::div[contains(@class,'price')][1]",
            ]:
                try:
                    box = anchor.locator(xp)
                    txt = box.inner_text(timeout=2000)
                    txt = re.sub(r"\s+", " ", txt).strip()
                    m = rub_price_re.search(txt)
                    if m:
                        return norm_price(m.group(0))
                except Exception:
                    continue
            
            body = page.locator("body").inner_text(timeout=3000)
            body = re.sub(r"\s+", " ", body)
            idx = body.lower().find("ozon")
            if idx != -1:
                window = body[max(0, idx - 200): idx + 400]
                m = rub_price_re.search(window)
                if m:
                    return norm_price(m.group(0))
        except Exception:
            continue

    return None


@dataclass
class Row:
    article: str
    seller: str
    ozon_card_price: str


def parse_product(page: Page, url: str) -> Tuple[Optional[str], Optional[str]]:
    page.goto(url, wait_until="domcontentloaded", timeout=config.NAV_TIMEOUT_MS)
    random_sleep(2.0, 4.0)

    for sel in [
        "button:has-text('Принять')",
        "[aria-label='Закрыть']",
        "button:has-text('Закрыть')",
    ]:
        click_if_exists(page, sel)

    seller = extract_seller_default(page)
    price = extract_ozon_card_price(page)
    return seller, price


def read_articles_xlsx(path: str) -> List[str]:
    df = pd.read_excel(path, header=None)
    col = df.iloc[:, 0].dropna().astype(str).map(lambda x: x.strip()).tolist()
    return [x for x in col if x]


def main():
    articles = read_articles_xlsx(config.INPUT_XLSX)
    out_rows: List[Row] = []

    with sync_playwright() as p:
        # Запуск браузера с отключением флагов автоматизации
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",  # Используем обычный Chrome
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        
        context = browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        
        # Внедряем защиту от обнаружения (вместо библиотеки)
        inject_stealth(context)

        context.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)
        context.set_default_timeout(config.ACTION_TIMEOUT_MS)

        page = context.new_page()
        
        try:
            set_pvz(page, config.PVZ_URL)
        except Exception as e:
            print(f"Ошибка установки ПВЗ: {e}")

        for article in articles:
            try:
                links = collect_search_product_links(page, article, config.MAX_PRODUCTS_PER_QUERY)
                
                if not links:
                    print(f"Не найдено товаров по артикулу {article}")
                    random_sleep(5, 10)

                for url in links:
                    try:
                        seller, price = parse_product(page, url)
                    except Exception:
                        seller, price = None, None

                    out_rows.append(
                        Row(
                            article=article,
                            seller=seller or "",
                            ozon_card_price=price or "",
                        )
                    )
                    random_sleep(1.0, 3.0)
            except Exception as e:
                print(f"Ошибка при обработке {article}: {e}")
                continue

        out_df = pd.DataFrame([r.__dict__ for r in out_rows])
        out_df.rename(
            columns={
                "article": "Артикул",
                "seller": "Селлер",
                "ozon_card_price": "Цена_по_карте_Ozon",
            },
            inplace=True,
        )
        out_df.to_excel(config.OUTPUT_XLSX, index=False)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()