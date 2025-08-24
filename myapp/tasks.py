import requests
from decimal import Decimal
from django.utils.timezone import now
from .models import Currency, PriceHistory

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"


ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

def fetch_and_update_prices():
    ids = ",".join(ID_MAP.values())
    params = {"ids": ids, "vs_currencies": "usd"}
    r = requests.get(COINGECKO_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    for symbol, coingecko_id in ID_MAP.items():
        if coingecko_id not in data:
            continue
        price = Decimal(str(data[coingecko_id]["usd"]))
        pair, _ = Currency.objects.get_or_create(base_currency=symbol, quote_currency="USD")
        pair.current_rate = price
        pair.save(update_fields=["current_rate"])
        PriceHistory.objects.create(currency_pair=pair, price=price)
