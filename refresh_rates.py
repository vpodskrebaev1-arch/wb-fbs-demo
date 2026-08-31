#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пересобирает только ставки из финотчёта, не трогая выгруженную статистику.

Нужен, когда суточный прогон упал на финотчёте: заказы и продажи уже лежат
в data/, повторять их выгрузку незачем — это ещё двадцать минут и лимиты WB.

Запуск:  python3 refresh_rates.py
"""
import os, sys, json, gzip

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wb_client import log
import collect

STATE = collect.STATE
DATA = collect.DATA


def load(name):
    p = os.path.join(DATA, name + ".json.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not collect.CABS:
        sys.exit("не задан ни один токен: нужна переменная WB_TOKEN_<КЛЮЧ> на каждый кабинет")
    path = os.path.join(STATE, "rates.json")
    state = {}
    if os.path.exists(path):
        try:
            state = json.load(open(path, encoding="utf-8"))
        except Exception:
            state = {}
    for key, title, token in collect.CABS:
        orders, sales = load(f"orders_{key}"), load(f"sales_{key}")
        if not orders or not sales:
            log(f"  [{title}] нет выгрузки заказов или продаж — сначала collect.py")
            continue
        log(f"  [{title}] заказов {len(orders)}, продаж {len(sales)}")
        keep = {r.get("srid") for r in orders if r.get("srid")}
        keep |= {r.get("srid") for r in sales if r.get("srid")}
        acc = collect.WholeAcc()
        fin = collect.pull_finance(token, keep, acc)
        log(f"    финотчёт: {acc.rows} строк всего, наших {len(fin)}, "
            f"закрыт по {acc.covered_to}")
        state[key] = collect.rates_from_finance(fin, orders, sales, acc)
        log(f"    ставки: доходит {state[key]['payout_share']}, "
            f"логистика/заказ {state[key]['logistics_per_order']}, "
            f"выкуп {state[key]['buyout_of_raw']}, источник — {state[key]['source']}")
        del fin, keep, acc
    with open(path, "w", encoding="utf-8") as f:
        json.dump(collect.strip_money(state), f, ensure_ascii=False, indent=1)
    log("готово")


if __name__ == "__main__":
    main()
