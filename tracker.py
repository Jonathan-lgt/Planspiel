#!/usr/bin/env python3
"""Berechnet den aktuellen Depotwert und haengt ihn an data/history.json an."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent
PORTFOLIO = ROOT / "portfolio.json"
HISTORY = ROOT / "data" / "history.json"


def last_price(symbol: str) -> float | None:
    """Letzter verfuegbarer Kurs (fast_info, sonst 1-Minuten-Historie)."""
    try:
        price = yf.Ticker(symbol).fast_info["last_price"]
        if price and price > 0:
            return float(price)
    except Exception:
        pass
    try:
        hist = yf.Ticker(symbol).history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def main() -> int:
    pf = json.loads(PORTFOLIO.read_text(encoding="utf-8"))

    eurusd = last_price("EURUSD=X")  # USD pro 1 EUR
    total = float(pf.get("cash", 0))
    invested = 0.0
    details = {}

    for pos in pf["positions"]:
        price = last_price(pos["symbol"])
        if price is None:
            print(f"Kein Kurs fuer {pos['symbol']} - Lauf abgebrochen.", file=sys.stderr)
            return 1
        if pos.get("currency", "EUR") == "USD":
            if not eurusd:
                print("Kein EUR/USD-Kurs - Lauf abgebrochen.", file=sys.stderr)
                return 1
            price_eur = price / eurusd
        else:
            price_eur = price
        value = price_eur * pos["shares"]
        invested += value
        details[pos["symbol"]] = round(value, 2)

    total += invested
    point = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "v": round(total, 2),
        "inv": round(invested, 2),
        "pos": details,
    }

    HISTORY.parent.mkdir(exist_ok=True)
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []

    # Nur speichern, wenn sich der Wert geaendert hat (haelt die Datei klein)
    if history and history[-1]["v"] == point["v"]:
        print("Wert unveraendert - nichts zu speichern.")
        return 0

    history.append(point)
    HISTORY.write_text(json.dumps(history, separators=(",", ":")), encoding="utf-8")
    print(f"Gespeichert: {point['v']:.2f} EUR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
