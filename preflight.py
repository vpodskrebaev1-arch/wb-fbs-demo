#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка контура безопасности: что наружу не уедет ничего лишнего.

Гоняйте перед первой публикацией и после любой правки кода. Скрипт ничего не
исправляет молча — он показывает, что не так, и возвращает ненулевой код.

Запуск:  python3 preflight.py
"""
import json, os, re, subprocess, sys, gzip

BASE = os.path.dirname(os.path.abspath(__file__))
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
# ИНН: ровно 10 или 12 цифр, не часть дробного числа — иначе ловятся суммы вида 117811.07
INN = re.compile(r"(?<![\d.])\d{10}(?:\d{2})?(?![\d.])")
# юрлицо: «ООО «Ромашка»» или «ИП Иванов», но не родовая подпись «Кабинет ИП»
ORG = re.compile(r"(?:ООО|АО|ЗАО|ПАО|ОАО)\s*[«\"\u0022]|ИП\s+[А-ЯЁ][а-яё]{2,}")
bad, warn = [], []


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  !!   ") + name + (("  — " + detail) if detail else ""))
    if not ok:
        bad.append(name)


def soft(name, ok, detail=""):
    print(("  OK   " if ok else "  ~    ") + name + (("  — " + detail) if detail else ""))
    if not ok:
        warn.append(name)


def read(p):
    try:
        return open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


print("Контур безопасности\n")

# 1. Токены лежат только в .env и только там
env = os.path.join(BASE, ".env")
if os.path.exists(env):
    mode = oct(os.stat(env).st_mode & 0o777)[-3:]
    check(".env закрыт от чужих (права 600)", mode == "600", f"сейчас {mode}")
else:
    soft(".env на месте", False, "токенов нет — выгрузка не пойдёт")

gi = read(os.path.join(BASE, ".gitignore"))
for must in (".env", "data/", "dist/", "cost.json", "dashboard_data.json"):
    check(f"{must} не уедет в репозиторий", must in gi)

# 2. Токен не просочился в код, конфиг и готовую страницу
leaked = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "data")]
    for f in files:
        if f == ".env" or f.endswith((".gz", ".woff2")):
            continue
        p = os.path.join(root, f)
        if os.path.getsize(p) > 8_000_000:
            continue
        if JWT.search(read(p)):
            leaked.append(os.path.relpath(p, BASE))
check("токена нет ни в одном файле проекта", not leaked, ", ".join(leaked[:4]))

# 3. Что уезжает в публичный репозиторий: только коэффициенты, без сумм
rates = os.path.join(BASE, "state", "rates.json")
if os.path.exists(rates):
    txt = read(rates)
    money = [k for k in ("retail", "customer", "forpay", "logistics", "avg_order_price")
             if f'"{k}"' in txt]
    check("в state/rates.json нет абсолютных сумм", not money, ", ".join(money))
    check("в state/rates.json нет токена", not JWT.search(txt))

# 4. Готовая страница: нет токена; при анонимном режиме нет и опознавательных данных
cfg = {}
cp = os.path.join(BASE, "config.json")
if os.path.exists(cp):
    try:
        cfg = json.load(open(cp, encoding="utf-8"))
    except Exception:
        pass
check("в config.json нет токена", not JWT.search(read(cp)))

page = os.path.join(BASE, "dist", "index.html")
if os.path.exists(page):
    html = read(page)
    check("на странице нет токена", not JWT.search(html))
    if cfg.get("anonymize"):
        hits = []
        m = ORG.search(html)
        if m:
            hits.append("название юрлица: " + m.group(0)[:24])
        m = INN.search(html)
        if m:
            hits.append("похоже на ИНН: " + m.group(0))
        check("анонимный режим: юрлиц и ИНН на странице нет", not hits, ", ".join(hits))
    else:
        soft("анонимный режим выключен — на странице видны свои названия и артикулы", True,
             "так и задумано для работы со своим кабинетом")

# 5. Если это git-репозиторий — .env не должен быть в индексе
if os.path.isdir(os.path.join(BASE, ".git")):
    try:
        out = subprocess.run(["git", "-C", BASE, "ls-files"], capture_output=True,
                             text=True, timeout=30).stdout.split("\n")
        check(".env не добавлен в git", ".env" not in out)
        check("cost.json не добавлен в git", "cost.json" not in out)
    except Exception:
        pass

print()
if bad:
    print(f"НЕ ГОТОВО: {len(bad)} проверок не прошли. Публиковать нельзя, пока не исправите.")
    sys.exit(1)
print("Всё чисто" + (f", но обратите внимание: {len(warn)}" if warn else "") + ".")
