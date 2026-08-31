#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Данные, которых нет в основном прогоне: остатки на своих складах и воронка.

Два метода WB, на которые легко напороться:
  * `/api/v1/supplier/stocks` закрыт как устаревший (404). Остатки FBS берутся
    через список складов продавца и `POST /api/v3/stocks/{id}` со списком
    баркодов — те, что встречались в заказах окна.
  * `/api/v2/nm-report/detail` удалён. Воронка живёт по адресу
    `POST /api/analytics/v3/sales-funnel/products`: не больше 30 карточек за
    запрос и восстановление лимита почти полчаса, поэтому берётся одна
    страница топа по выручке — так и подписано на странице.

Запуск:  python3 collect_extra.py [stocks|funnel|all]
Токены — из .env рядом, как и у основного прогона.
"""
import os, sys, json, gzip, time, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wb_client import call, log
import collect                                   # кабинеты, пути, константы

BASE = collect.BASE
DATA = collect.DATA
H_MP = collect.H_MP
H_ANL = collect.H_ANL
FBS = collect.FBS


def save(name, obj):
    with gzip.open(os.path.join(DATA, name + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def load(name, default=None):
    p = os.path.join(DATA, name + ".json.gz")
    if not os.path.exists(p):
        return default
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def stocks(key, title, token):
    orders = load(f"orders_{key}")
    if not orders:
        log(f"  [{title}] заказов ещё нет — сначала прогоните collect.py")
        return
    fbs = [r for r in orders if r.get("warehouseType") == FBS]
    meta, order = {}, []
    for r in fbs:
        b = r.get("barcode")
        if b and b not in meta:
            meta[b] = dict(nmId=r.get("nmId"), art=r.get("supplierArticle"),
                           size=r.get("techSize"), subject=r.get("subject"))
            order.append(b)
    log(f"  [{title}] баркодов FBS: {len(order)}")
    whs = call(token, H_MP, "/api/v3/warehouses", timeout=120) or []
    log(f"    складов продавца: {len(whs)}")
    out = {}
    for w in whs:
        got = {}
        for i in range(0, len(order), 1000):
            r = call(token, H_MP, f"/api/v3/stocks/{w['id']}", method="POST",
                     body={"skus": order[i:i + 1000]}, timeout=180) or {}
            for s in r.get("stocks") or []:
                got[s["sku"]] = s.get("amount") or 0
            time.sleep(0.5)
        out[str(w["id"])] = dict(name=w.get("name"), stocks=got)
        log(f"    склад {w.get('name')}: позиций с остатком "
            f"{sum(1 for v in got.values() if v)}")
    save(f"stocks_{key}", dict(warehouses=out, meta=meta,
                               at=datetime.datetime.now().isoformat(timespec="seconds")))


def funnel(key, title, token):
    days = int(os.environ.get("FUNNEL_DAYS", "14"))
    end = datetime.date.today() - datetime.timedelta(days=1)
    beg = end - datetime.timedelta(days=days - 1)
    pend = beg - datetime.timedelta(days=1)
    pbeg = pend - datetime.timedelta(days=days - 1)
    body = {"selectedPeriod": {"start": beg.isoformat(), "end": end.isoformat()},
            "pastPeriod": {"start": pbeg.isoformat(), "end": pend.isoformat()},
            "orderBy": {"field": "orderSum", "mode": "desc"},
            "page": 1, "limit": int(os.environ.get("FUNNEL_LIMIT", "30"))}
    try:
        # лимит метода — один запрос примерно раз в полчаса, ждать честно
        r = call(token, H_ANL, "/api/analytics/v3/sales-funnel/products",
                 method="POST", body=body, timeout=300, max_wait=2000) or {}
    except Exception as e:
        log(f"  [{title}] воронка недоступна: {e}")
        return
    prods = ((r.get("data") or {}).get("products")) or []
    log(f"  [{title}] воронка: {len(prods)} карточек, период {beg}—{end}")
    save(f"funnel_{key}", dict(products=prods,
                               selected=[beg.isoformat(), end.isoformat()],
                               past=[pbeg.isoformat(), pend.isoformat()]))


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if os.environ.get("FAST") == "1" and what == "all":
        # остатки списываются с каждым заказом — их тянем всегда;
        # воронка суточная и с получасовым лимитом на запрос — только ночью
        what = "stocks"
        log("быстрый прогон: беру только остатки, воронка остаётся вчерашней")
    if not collect.CABS:
        sys.exit("не задан ни один токен: нужна переменная WB_TOKEN_<КЛЮЧ> на каждый кабинет")
    for key, title, token in collect.CABS:
        if what in ("all", "stocks"):
            try:
                stocks(key, title, token)
            except Exception as e:
                log(f"  [{title}] остатки не собраны: {e}")
        if what in ("all", "funnel"):
            funnel(key, title, token)
    log("готово")


if __name__ == "__main__":
    main()
