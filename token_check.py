#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Что этот токен умеет и каких блоков дашборда из-за него не будет.

Чаще всего «у меня половина пустая» — это не поломка, а недовыданные категории
при выпуске токена. Скрипт читает категории прямо из токена и говорит заранее,
что соберётся, а что нет, — до того как человек прождёт часовую выгрузку.

Запуск:  python3 token_check.py
"""
import base64, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Номер бита в поле s токена → категория и то, что на ней держится.
# Нумерация из справочника WB: Контент 1, Аналитика 2, …, Финансы 13.
SCOPES = {
    5:  ("Статистика", "заказы и продажи — без них не будет ничего", True),
    13: ("Финансы", "комиссия, логистика, реальные ставки и выкуп", True),
    4:  ("Маркетплейс", "сборка, отгрузка, скорость против порогов, остатки", True),
    6:  ("Продвижение", "реклама в водопаде и ДРР", False),
    2:  ("Аналитика", "воронка продаж и возвраты на ПВЗ", False),
}


def decode(token):
    parts = (token or "").strip().split(".")
    if len(parts) != 3:
        return None, "это не похоже на токен WB: должно быть три части через точку"
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(pad)), None
    except Exception:
        return None, "тело токена не читается — скопировался не целиком?"


def report(title, token):
    body, err = decode(token)
    print(f"\n=== {title} ===")
    if err:
        print("  " + err)
        return False
    mask = int(body.get("s") or 0)
    exp = body.get("exp")
    if exp:
        left = (datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()).days
        print(f"  срок действия: {'истёк' if left < 0 else str(left) + ' дн'}"
              + ("  ← пора выпускать новый" if 0 <= left < 14 else ""))
        if left < 0:
            return False
    if body.get("acc") == 1:
        print("  тип: БАЗОВЫЙ — выгрузка встанет на лимитах, нужен персональный")
    ok = True
    for bit, (name, what, required) in SCOPES.items():
        has = bool(mask >> bit & 1)
        mark = "есть " if has else ("НЕТ  " if required else "нет  ")
        print(f"  {mark} {name:<14} — {what}")
        if not has and required:
            ok = False
    if body.get("t"):
        print("  ВНИМАНИЕ: тестовый контур — боевых данных не будет")
    print("  " + ("токен подходит" if ok else
                  "без обязательных категорий дашборд не соберётся — перевыпустите токен"))
    return ok


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    env = os.path.join(base, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
    toks = {k: v for k, v in os.environ.items() if k.startswith("WB_TOKEN_") and v.strip()}
    if not toks:
        sys.exit("токенов не найдено: нужен .env рядом или переменная WB_TOKEN_<КЛЮЧ>")
    good = all(report(k.replace("WB_TOKEN_", "кабинет "), v) for k, v in sorted(toks.items()))
    print()
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
