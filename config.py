BASE_URL = "https://www.ozon.ru/"
PVZ_URL = "https://www.ozon.ru/geo/himki/387923/"

INPUT_XLSX = "input.xlsx"
OUTPUT_OFFERS_XLSX = "output_offers.xlsx"
OUTPUT_STATS_XLSX = "output_stats.xlsx"

TOP_N_PRODUCTS = 5   # топ-N товаров из поиска
IDEAS_PER_SEED = 20  # вы просили 20


# Паузы/таймауты (можно подкрутить при блокировках/медленной сети)
NAV_TIMEOUT_MS = 45000
ACTION_TIMEOUT_MS = 15000
SCROLL_PAUSE_SEC = 0.9