"""
Psynex Grant Bot v4
Кожен запит = окремий Claude API виклик.
Природні запити без site: операторів.
"""

import os
import json
import hashlib
import requests
import anthropic
from datetime import datetime, timedelta
import time

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
SEEN_FILE      = "seen_grants.json"
MIN_SCORE      = 6

TODAY    = datetime.now()
DATE_STR = TODAY.strftime("%d.%m.%Y")

PSYNEX_PROFILE = """
КОМПАНІЯ: ТОВ «ПСАЙНЕКС» (Psynex), psynex.app, Київ, Diia.City, ЄДРПОУ 46150138
РЕЄСТРАЦІЯ: 12.11.2025
EU Funding Portal PIC: 864846957
Horizon Europe: eligible (Україна — асоційована країна)
ПРОДУКТ: AI-платформа самопізнання та свідомої побудови стосунків (dating через self-discovery)
СТАДІЯ: Pre-seed, bridge $50K → $250K, post-money cap $2.5M, TRL 7, 208 beta users
КОМАНДА: 5 співзасновників, <10 осіб

ВЖЕ ОТРИМАНІ: Anthropic $1.5K, AWS $25.1K, ElevenLabs 33M chars, Mixpanel 1 рік, PostHog $50K, Sentry $5K, Microsoft $1K
ВІДХИЛЕНІ: Google for Startups, Vercel
ПАЙПЛАЙН: USF EDGE, EIT Jumpstarter, YC W27, NVIDIA Inception, Cloudflare, EIC Accelerator, Win-Win EDIH

ВИМОГИ: грошовий грант або безкоштовні startup credits, startup/SME eligible, відкритий дедлайн, сума від €5K, не вимагати >12 міс існування
"""

SEARCH_QUERIES = [
    # UA
    "Ukrainian startup grant program open applications 2026",
    "Ukraine tech startup funding opportunity 2026",
    "USF Ukrainian Startup Fund new cohort open 2026",
    "USAID Ukraine startup grant open call 2026",
    "EBRD Ukraine startup program 2026",
    "1991 Accelerator Ukraine open batch 2026",
    # EU основні
    "EIC Accelerator open call AI startup 2026",
    "Horizon Europe AI startup grant open 2026",
    "EIT Digital startup funding open call 2026",
    "EIC Pre-Accelerator Ukraine eligible open 2026",
    "Eurostars startup grant open application 2026",
    "Digital Europe Programme SME grant open 2026",
    "EU startup grant non-dilutive open 2026",
    "European Innovation Council startup funding 2026",
    # UK
    "Innovate UK Smart Grant open call 2026",
    "UKRI AI startup grant open application 2026",
    "UK startup grant AI technology open 2026",
    # Молдова
    "Moldova startup grant program open 2026",
    "Moldova Innovation Technology Park grant 2026",
    # Кіпр
    "Cyprus startup grant RIF INNOVATE open 2026",
    "Cyprus Digital Ministry startup grant 2026",
    # Міжнародні акселератори
    "MassChallenge open applications AI startup 2026",
    "Plug and Play accelerator open batch 2026",
    "Seedstars startup competition open 2026",
    "Startup Wise Guys open application 2026",
    "Nordic startup grant AI open 2026",
    "Visegrad Fund startup grant Ukraine 2026",
    # Нові корпоративні програми
    "new startup program free credits AI tools 2026",
    "tech company startup program launch 2026",
    "free startup credits program AI SaaS 2026",
]

def load_seen() -> set:
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)

def grant_id(title: str) -> str:
    return hashlib.md5(title.lower().strip()[:80].encode()).hexdigest()[:12]

def single_search(query: str, client: anthropic.Anthropic) -> list[dict]:
    prompt = f"""
Виконай веб-пошук за запитом: "{query}"

Сьогодні: {DATE_STR}

Знайди реальні відкриті гранти або безкоштовні startup programs.

Профіль стартапу для оцінки:
{PSYNEX_PROFILE}

Відповідай ЛИШЕ JSON (без markdown):
[
  {{
    "title": "Назва програми мовою оригіналу",
    "url": "https://реальне посилання",
    "deadline": "ДД.ММ.РРРР або Rolling або Невідомо",
    "amount": "сума або credits",
    "type": "grant або credits або accelerator",
    "country": "EU або UK або UA або CY або MD або Global",
    "score": 7,
    "reason": "чому підходить або не підходить Psynex — одне речення англійською"
  }}
]

ПРАВИЛА:
- Тільки реальні програми з реальними URL
- НЕ включай: {', '.join(['USF EDGE', 'EIT Jumpstarter', 'YC', 'NVIDIA Inception', 'Cloudflare', 'EIC Accelerator', 'Win-Win EDIH', 'Google for Startups', 'Vercel', 'AWS', 'PostHog', 'Sentry', 'Mixpanel', 'Anthropic', 'Microsoft'])}
- НЕ включай програми що вимагають >12 місяців існування
- Тільки score >= 5
- Максимум 2 результати
- Якщо нічого — поверни []
"""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        return json.loads(text) if text else []
    except Exception as e:
        print(f"    ⚠ {e}")
        return []

def translate_grant(items: list[dict], client: anthropic.Anthropic) -> list[dict]:
    if not items:
        return []
    items_str = json.dumps(items, ensure_ascii=False, indent=2)
    prompt = f"""
Ось гранти:
{items_str}

Для кожного:
1. title — переклади назву українською
2. reason_ua — переклади reason українською, розшир до 2-3 речень: що це за програма, чому підходить Psynex
3. Всі інші поля залиш без змін

Відповідай ЛИШЕ JSON (без markdown):
[
  {{
    "title": "Назва українською",
    "url": "...",
    "deadline": "...",
    "amount": "...",
    "type": "...",
    "country": "...",
    "score": 7,
    "reason_ua": "2-3 речення українською..."
  }}
]
"""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        return json.loads(text) if text else items
    except Exception as e:
        print(f"    ⚠ translate error: {e}")
        return items

def send_telegram(text: str):
    if len(text) > 4096:
        text = text[:4090] + "..."
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
        timeout=15
    ).raise_for_status()

def format_grant(g: dict) -> str:
    score = g.get("score", 0)
    emoji = "🔥" if score >= 9 else "✅" if score >= 7 else "🟡"
    flag = {"EU":"🇪🇺","UK":"🇬🇧","UA":"🇺🇦","CY":"🇨🇾","MD":"🇲🇩","Global":"🌍"}.get(g.get("country",""),"🌐")
    gtype = {"grant":"💵 Грант","credits":"💳 Credits","accelerator":"🚀 Акселератор"}.get(g.get("type",""),"💰")
    reason = g.get("reason_ua") or g.get("reason","")
    return (
        f"{emoji} {flag} <b>{g['title']}</b> [{score}/10]\n\n"
        f"{gtype}\n"
        f"💰 <b>Сума:</b> {g.get('amount','?')}\n"
        f"📅 <b>Дедлайн:</b> {g.get('deadline','?')}\n"
        f"🎯 {reason}\n\n"
        f"🔗 {g.get('url','')}"
    )

def main():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"\n{'='*50}\nPsynex Grant Bot v4 | {now}\n{'='*50}")

    seen = load_seen()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    all_raw = []
    seen_urls = set()

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{len(SEARCH_QUERIES)}] {query[:55]}...")
        results = single_search(query, client)
        for r in results:
            url = r.get("url","")
            title = r.get("title","")
            if url and url not in seen_urls and title:
                seen_urls.add(url)
                all_raw.append(r)
        time.sleep(1)

    print(f"\nЗнайдено сирих: {len(all_raw)}")

    new_raw = [
        r for r in all_raw
        if grant_id(r.get("title","")) not in seen
        and r.get("score",0) >= MIN_SCORE
    ]
    new_raw.sort(key=lambda x: x.get("score",0), reverse=True)

    print(f"Нових релевантних: {len(new_raw)}")

    if not new_raw:
        send_telegram(
            f"📭 <b>Psynex Grant Bot — {now}</b>\n"
            f"Нових грантів сьогодні: 0\n"
            f"Перевірено запитів: {len(SEARCH_QUERIES)}"
        )
        save_seen(seen)
        return

    translated = translate_grant(new_raw[:5], client)

    sent = 0
    for g in translated:
        gid = grant_id(g.get("title",""))
        try:
            send_telegram(format_grant(g))
            seen.add(gid)
            sent += 1
        except Exception as e:
            print(f"  ❌ {e}")

    send_telegram(
        f"📊 <b>Psynex Grant Bot — {now}</b>\n"
        f"Запитів: {len(SEARCH_QUERIES)} | Надіслано: {sent}"
    )

    save_seen(seen)
    print(f"\n✅ Надіслано: {sent}")

if __name__ == "__main__":
    main()
