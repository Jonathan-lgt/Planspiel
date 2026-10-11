import json
from datetime import datetime
import os
import yfinance as yf

# Absolute Pfade relativ zum Speicherort des Skripts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_PATH = os.path.join(BASE_DIR, 'portfolio.json')
HISTORY_PATH = os.path.join(BASE_DIR, 'data', 'history.json')

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_tracker():
    portfolio = load_json(PORTFOLIO_PATH)
    history = load_json(HISTORY_PATH)
    
    if not isinstance(history, list):
        history = []

    total_stocks_value = 0.0
    cash = portfolio.get('cash', 0.0)
    stocks = portfolio.get('stocks', {})

    for ticker, details in stocks.items():
        shares = details.get('shares', 0)
        current_price = details.get('last_price', 0.0)
        
        try:
            # Letzte 5 Tage abrufen, falls heute Feiertag/Wochenende ist
            stock = yf.Ticker(ticker)
            todays_data = stock.history(period='5d')
            if not todays_data.empty:
                current_price = float(todays_data['Close'].iloc[-1])
        except Exception as e:
            print(f"Fehler beim Laden von {ticker}: {e}")
        
        details['last_price'] = round(current_price, 2)
        total_stocks_value += shares * current_price

    total_portfolio_value = cash + total_stocks_value
    
    # Heutiges Datum im UTC-Format (YYYY-MM-DD)
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Prüfen, ob für heute bereits ein Eintrag existiert (verhindert Duplikate)
    existing_entry = next((item for item in history if item.get('date') == today_str), None)
    
    new_entry = {
        "date": today_str,
        "total": round(total_portfolio_value, 2),
        "cash": round(cash, 2),
        "stocks_value": round(total_stocks_value, 2)
    }
    
    if existing_entry:
        existing_entry.update(new_entry)
    else:
        history.append(new_entry)
        
    # Historie chronologisch nach Datum sortieren
    history = sorted(history, key=lambda x: x['date'])

    save_json(PORTFOLIO_PATH, portfolio)
    save_json(HISTORY_PATH, history)
    print(f"Erfolgreich aktualisiert ({today_str}): Gesamtwert = {total_portfolio_value:.2f} EUR")

if __name__ == '__main__':
    update_tracker()
