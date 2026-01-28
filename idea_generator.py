from dotenv import load_dotenv
import os
import json
import re
import pandas as pd

import config
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


load_dotenv()

SYSTEM = """Ты помощник по продуктовым идеям для маркетплейсов РФ.
Верни результат СТРОГО в формате JSON без markdown и без пояснений.

На вход: исходный материал/предмет и его цена (себестоимость).
На выход: список товарных идей, которые реально продаются на Ozon.

Каждая идея:
- title: краткое название товара
- query: поисковый запрос для Ozon (по-русски, максимально практичный)
- description: 1-2 предложения
- material_cost_rub: себестоимость (число, рубли). Если на входе задана цена — используй её,
  иначе оцени разумно исходя из материала/комплектации.

Формат ответа:
{
  "items": [
    {"title":"...", "query":"...", "description":"...", "material_cost_rub": 123},
    ...
  ]
}
"""

def extract_json_object(text: str) -> str:
    """Пытается вырезать первый JSON-объект из ответа."""
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        return t
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end+1]
    return t

def generate_ideas(llm: ChatOpenAI, seed_text: str, seed_material_cost: float | None, n: int):
    prompt = f"""Вход:
seed: {seed_text}
material_cost_rub: {seed_material_cost if seed_material_cost is not None else "не задано"}

Сгенерируй {n} идей.
Верни только JSON-объект, как в формате выше.
"""
    resp = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=prompt)
    ])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    json_text = extract_json_object(content)
    data = json.loads(json_text)
    return data["items"]

def main():
    # 1) Инициализация LLM
    # Если в другом проекте у вас прокси “заводится” через env — оставьте так же.
    # Модель/температуру можете менять.
    
    llm = ChatOpenAI(
            base_url=os.getenv("OPENAI_API_URL"),
            model=os.getenv("OPENAI_MODEL"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7,
        )

    # 2) Ваши seeds (+ себестоимость материала на входе)
    seeds = [
        {"seed": "коробка из прозрачного пластика", "material_cost_rub": 40},
        {"seed": "металлический крючок для ванной", "material_cost_rub": 25},
    ]

    rows = []
    idea_id = 1

    for s in seeds:
        seed_text = s["seed"]
        seed_cost = s.get("material_cost_rub")

        items = generate_ideas(llm, seed_text, seed_cost, n=config.IDEAS_PER_SEED)

        # небольшая валидация
        for it in items:
            title = str(it.get("title", "")).strip()
            query = str(it.get("query", "")).strip()
            desc = str(it.get("description", "")).strip()
            cost = it.get("material_cost_rub", seed_cost)

            if not title or not query:
                continue

            try:
                cost = float(cost) if cost is not None else None
            except:
                cost = None

            rows.append({
                "idea_id": idea_id,
                "seed": seed_text,
                "title": title,
                "query": query,
                "description": desc,
                "material_cost_rub": cost,
            })
            idea_id += 1

    df = pd.DataFrame(rows)
    df.to_excel(config.INPUT_XLSX, index=False)
    print(f"Saved {config.INPUT_XLSX} rows={len(df)}")

if __name__ == "__main__":
    main()