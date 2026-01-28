import math
import pandas as pd
import config

def rms(series: pd.Series) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if len(s) == 0:
        return None
    return math.sqrt((s * s).mean())

def main():
    ideas = pd.read_excel(config.INPUT_XLSX)
    offers = pd.read_excel(config.OUTPUT_OFFERS_XLSX)

    offers["offer_price_rub"] = pd.to_numeric(offers["offer_price_rub"], errors="coerce")
    offers["offer_delivery_days"] = pd.to_numeric(offers["offer_delivery_days"], errors="coerce")

    g = offers.groupby("idea_id", dropna=False)

    stats = g.agg(
        offers_count=("offer_price_rub", lambda x: int(pd.to_numeric(x, errors="coerce").dropna().shape[0])),
        min_price=("offer_price_rub", "min"),
        max_price=("offer_price_rub", "max"),
        mean_price=("offer_price_rub", "mean"),
        min_delivery_days=("offer_delivery_days", "min"),
        max_delivery_days=("offer_delivery_days", "max"),
    ).reset_index()

    stats["rms_price"] = stats["idea_id"].apply(
        lambda iid: rms(offers.loc[offers["idea_id"] == iid, "offer_price_rub"])
    )

    out = ideas.merge(stats, on="idea_id", how="left")

    # прибыль (как "цена - себестоимость")
    out["material_cost_rub"] = pd.to_numeric(out["material_cost_rub"], errors="coerce")

    out["profit_min"] = out["min_price"] - out["material_cost_rub"]
    out["profit_rms"] = out["rms_price"] - out["material_cost_rub"]
    out["profit_max"] = out["max_price"] - out["material_cost_rub"]

    out.to_excel(config.OUTPUT_STATS_XLSX, index=False)
    print(f"Saved {config.OUTPUT_STATS_XLSX}")

if __name__ == "__main__":
    main()