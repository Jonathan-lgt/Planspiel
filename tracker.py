#!/usr/bin/env python3
"""Berechnet den Depotwert und pflegt data/history.json.

  python tracker.py            einmal messen und speichern
  python tracker.py --check    Yahoo-Kurse mit den Planspiel-Boerse-Kursen vergleichen
  python tracker.py --rebuild  Kalibrierung und Historie komplett neu aufbauen

Beim ersten Lauf (oder wenn sich psb_referenz / psb_kurs / die Symbole in
portfolio.json aendern) passiert automatisch Folgendes:
  1. Kalibrierung: Fuer jede Aktie wird ein Faktor berechnet, damit der Yahoo-Kurs
     zum Referenzzeitpunkt exakt dem Planspiel-Kurs entspricht (data/calibration.json).
  2. Historie: Die letzten ca. 60 Tage werden aus Yahoo rueckwirkend berechnet
     (5-Minuten-Daten, die letzten 3 Tage minuetlich), mit den heutigen Bestaenden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent
PORTFOLIO = ROOT / "portfolio.json"
HISTORY = ROOT / "data" / "history.json"
CALIB = ROOT / "data" / "calibration.json"

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # z. B. Windows ohne tzdata
    BERLIN = timezone(timedelta(hours=2))


# ---------------------------------------------------------------- Kursabruf --

def last_price(symbol: str) -> float | None:
    """Letzter verfuegbarer Kurs (fast_info, sonst 1-Minuten-Historie)."""
    try:
        price = yf.Ticker(symbol).fast_info["last_price"]
        if price and price > 0:
            return float(price)
    except Exception:
        pass
    s = hist(symbol, "1d", "1m")
    return float(s.iloc[-1]) if s is not None and len(s) else None


def hist(symbol: str, period: str, interval: str):
    """Schlusskurse als pandas-Serie mit UTC-Zeitindex, oder None."""
    try:
        h = yf.Ticker(symbol).history(period=period, interval=interval)
        if h is None or h.empty:
            return None
        s = h["Close"].dropna()
        s.index = s.index.tz_localize("UTC") if s.index.tz is None else s.index.tz_convert("UTC")
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as e:
        print(f"  ({symbol} {interval}: {e})", file=sys.stderr)
        return None


def uses_usd(pf: dict) -> bool:
    return any(p.get("currency", "EUR") == "USD" for p in pf["positions"])


def measure(pf: dict, faktoren: dict) -> list[dict] | None:
    """Aktuelle Werte aller Positionen in EUR. None, wenn irgendein Kurs fehlt."""
    eurusd = None
    if uses_usd(pf):
        eurusd = last_price("EURUSD=X")  # USD pro 1 EUR
        if not eurusd:
            print("Kein EUR/USD-Kurs - Lauf abgebrochen.", file=sys.stderr)
            return None
    rows = []
    for pos in pf["positions"]:
        raw = last_price(pos["symbol"])
        if raw is None:
            print(f"Kein Kurs fuer {pos['symbol']} - Lauf abgebrochen.", file=sys.stderr)
            return None
        raw_eur = raw / eurusd if pos.get("currency", "EUR") == "USD" else raw
        f = faktoren.get(pos["symbol"], 1.0)
        rows.append({**pos, "raw_eur": raw_eur, "faktor": f,
                     "price_eur": raw_eur * f, "value": raw_eur * f * pos["shares"]})
    return rows


# -------------------------------------------------------------- Kalibrierung --

def signature(pf: dict) -> str:
    """Aendert sich nur, wenn Referenzwerte oder Symbole geaendert werden."""
    basis = {
        "ref": pf.get("psb_referenz"),
        "pos": sorted((p["symbol"], p.get("psb_kurs"), p.get("currency", "EUR")) for p in pf["positions"]),
    }
    return hashlib.sha1(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:12]


def calibrate(pf: dict) -> dict:
    """Faktor je Symbol = Planspiel-Kurs / Yahoo-Kurs (in EUR) zum Referenzzeitpunkt."""
    ref = pf.get("psb_referenz") or {}
    zeit = ref.get("zeit")
    if not zeit:
        return {}
    when = datetime.strptime(zeit, "%Y-%m-%d %H:%M").replace(tzinfo=BERLIN).astimezone(timezone.utc)

    fx = hist("EURUSD=X", "60d", "5m") if uses_usd(pf) else None
    fx_at = None
    if fx is not None and len(fx[fx.index <= when]):
        fx_at = float(fx[fx.index <= when].iloc[-1])

    out = {}
    for pos in pf["positions"]:
        want = pos.get("psb_kurs")
        if not want:
            continue
        s = hist(pos["symbol"], "60d", "5m")
        if s is None or not len(s[s.index <= when]):
            print(f"  Kalibrierung {pos['symbol']}: kein Kurs zum Referenzzeitpunkt", file=sys.stderr)
            continue
        p = float(s[s.index <= when].iloc[-1])
        if pos.get("currency", "EUR") == "USD":
            if not fx_at:
                continue
            p /= fx_at
        out[pos["symbol"]] = round(want / p, 6)
        flag = "   <-- Symbol pruefen!" if abs(want / p - 1) > 0.10 else ""
        print(f"  {pos['name']:<16} Yahoo {p:>9.2f}  Planspiel {want:>9.2f}  Faktor {want / p:.4f}{flag}")
    return out


# ------------------------------------------------------------------ Historie --

def build_history(pf: dict, faktoren: dict) -> list[dict]:
    """Depotwert der letzten ca. 60 Tage aus Yahoo-Daten, mit heutigen Bestaenden."""
    import pandas as pd

    fx = None
    if uses_usd(pf):
        fx = hist("EURUSD=X", "60d", "5m")
        fx1 = hist("EURUSD=X", "3d", "1m")
        if fx is None:
            return []
        if fx1 is not None and len(fx1):
            fx = pd.concat([fx[fx.index < fx1.index[0]], fx1])

    cols = {}
    for pos in pf["positions"]:
        s5, s1 = hist(pos["symbol"], "60d", "5m"), hist(pos["symbol"], "3d", "1m")
        if s5 is None:
            print(f"  Keine Historie fuer {pos['symbol']} - Historie wird uebersprungen.", file=sys.stderr)
            return []
        s = pd.concat([s5[s5.index < s1.index[0]], s1]) if s1 is not None and len(s1) else s5
        if pos.get("currency", "EUR") == "USD":
            f = fx.reindex(fx.index.union(s.index)).ffill().reindex(s.index)
            s = s / f
        cols[pos["symbol"]] = s * faktoren.get(pos["symbol"], 1.0) * pos["shares"]

    df = pd.DataFrame(cols).sort_index().ffill().dropna()
    if df.empty:
        return []
    total = (df.sum(axis=1) + float(pf.get("cash", 0))).round(2)
    total = total[total != total.shift()]  # nur Aenderungen speichern
    return [{"t": t.isoformat(timespec="seconds"), "v": float(v)} for t, v in total.items()]


# ------------------------------------------------------------------- Dateien --

def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")  # atomar, damit die Seite nie eine halbe Datei liest
    tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ Befehle --

def run_once(force_rebuild: bool = False) -> int:
    pf = read_json(PORTFOLIO, None)
    if pf is None:
        print("portfolio.json fehlt oder ist kaputt.", file=sys.stderr)
        return 1
    calib = read_json(CALIB, {})
    history = read_json(HISTORY, [])
    faktoren = calib.get("faktor", {})

    wants_calib = bool(pf.get("psb_referenz"))
    if force_rebuild or not history or calib.get("sig") != signature(pf):
        print("Kalibrierung und Historie werden neu aufgebaut ...")
        neu_f = calibrate(pf) if wants_calib else {}
        neu_h = build_history(pf, neu_f)
        if neu_h and (neu_f or not wants_calib):
            faktoren, history = neu_f, neu_h
            write_json(CALIB, {"sig": signature(pf), "faktor": faktoren,
                               "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            print(f"  {len(history)} Historienpunkte, {len(faktoren)} Faktoren gespeichert.")
        else:
            print("  Aufbau nicht moeglich (Yahoo liefert keine Daten). Naechster Lauf versucht es erneut.",
                  file=sys.stderr)

    rows = measure(pf, faktoren)
    if rows is None:
        if history:
            write_json(HISTORY, history)
        return 1

    invested = sum(r["value"] for r in rows)
    point = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "v": round(float(pf.get("cash", 0)) + invested, 2),
        "inv": round(invested, 2),
        "pos": {r["symbol"]: round(r["value"], 2) for r in rows},
    }
    if history and history[-1]["v"] == point["v"]:
        # Wert gleich: nur Positionsdetails des letzten Punkts auffrischen
        history[-1].update({"inv": point["inv"], "pos": point["pos"]})
        print("Wert unveraendert.")
    else:
        history.append(point)
        print(f"Gespeichert: {point['v']:.2f} EUR")
    write_json(HISTORY, history)
    return 0


def check() -> int:
    """Yahoo-Kurse gegen die Kurse aus dem Planspiel vergleichen (speichert nichts)."""
    pf = read_json(PORTFOLIO, None)
    if pf is None:
        return 1
    faktoren = read_json(CALIB, {}).get("faktor", {})
    rows = measure(pf, faktoren)
    if rows is None:
        return 1
    print(f"{'Position':<18}{'Symbol':<9}{'Yahoo':>10}{'Faktor':>9}{'Berechnet':>11}{'Planspiel':>11}")
    for r in rows:
        ref = r.get("psb_kurs")
        print(f"{r['name']:<18}{r['symbol']:<9}{r['raw_eur']:>10.2f}{r['faktor']:>9.4f}"
              f"{r['price_eur']:>11.2f}{(f'{ref:.2f}' if ref else '-'):>11}")
    total = float(pf.get("cash", 0)) + sum(r["value"] for r in rows)
    print(f"\nDepotwert jetzt: {total:,.2f} EUR")
    ref = pf.get("psb_referenz") or {}
    if ref.get("gesamtdepotwert"):
        print(f"Planspiel ({ref.get('zeit', '?')}): {ref['gesamtdepotwert']:,.2f} EUR")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="Kurse vergleichen, nichts speichern")
    ap.add_argument("--rebuild", action="store_true", help="Kalibrierung und Historie neu aufbauen")
    args = ap.parse_args()
    sys.exit(check() if args.check else run_once(force_rebuild=args.rebuild))
