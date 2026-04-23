"""
Psynex Grant Research Bot
Щодня о 09:00 шукає гранти по всій Європі через Claude web search
та надсилає знахідки в Telegram.
"""

import os
import json
import hashlib
import requests
import anthropic
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
SEEN_FILE      = "seen_grants.json"
MIN_SCORE      = 6

PSYNEX_PROFILE = """
КОМПАНІЯ:
- Назва: ТОВ «ПСАЙНЕКС» (бренд: Psynex), сайт: psynex.app
- Країна: Україна, Київ. Diia.City резидент. ЄДРПОУ: 46150138
- Дата реєстрації: 12.11.2025
- EU Funding Portal PIC: 864846957
- Horizon Europe: eligible (Україна — асоційована країна)

ПРОДУКТ:
- AI-платформа самопізнання та свідомої побудови стосунків
- КАТЕГОРІЯ: dating через self-discovery (НЕ mental health, НЕ therapy)
- Аналоги: Hinge, Bumble, So Syncd
- 5 модулів: Explorer, MindID, Match, Insight, Connect
- 6 наукових фреймворків: теорія прив'язаності, MBTI, Big Five, Еннеаграма, Соціоніка, нейронаука
- TRL 7, MVP живий

СТАДІЯ:
- Pre-seed, bridge $50K → full $250K, post-money cap $2.5M
- Тракшн: 208 beta users, 64% completion rate
- Команда: 5 співзасновників, <10 осіб (SME eligible)

ВЖЕ ОТРИМАНІ (не шукати повторно):
- Anthropic for Startups: $1,500 credits
- AWS Activate: ~$25,100 credits
- ElevenLabs: 33M characters
- Mixpanel: 1 рік безкоштовно
- PostHog: $50,000 credits
- Sentry: $5,000 credits
- Microsoft for Startups: $1,000

ВІДХИЛЕНІ (не подавати повторно):
- Google for Startups Cloud (31.03.2026)
- Vercel for Startups (30.03.2026)

ВЖЕ В ПАЙПЛАЙНІ (не дублювати):
USF EDGE, EIT Jumpstarter, YC W27, NVIDIA Inception, Cloudflare, EIC Accelerator, Win-Win EDIH

ВИМОГИ ДО НОВОГО ГРАНТУ:
- Грошовий грант або безкоштовні startup credits (не консультації, не loans)
- Startup/SME eligible
- Відкритий дедлайн у майбутньому
- Сума від €5K або credits від $10K
- НЕ вимагати >12 місяців існування компанії
"""

SEARCH_QUERIES = [
    "grant.market нові гранти IT AI стартап 2026 відкрита заявка",
    "grant.market Ukrainian startup fresh grants 2026",
    "EIC Accelerator open call 2026 AI startup new",
    "Horizon Europe open calls AI digital SME 2026",
    "EIT Digital open call 2026 startup funding",
    "EIC Pre-Accelerator 2026 Ukraine eligible open",
    "Eurostars EUREKA open call 2026 grant startup",
    "Digital Europe Programme open call 2026 AI SME",
    "InvestEU SME startup grant 2026 open",
    "Horizon Europe Ukrainian tech SME new call 2026",
    "EU4Business Ukraine startup grant 2026",
    "COSME EU startup grant 2026 open",
    "European Social Fund startup grant digital 2026",
    "Innovate UK Smart Grant open call 2026 AI startup",
    "UKRI startup AI grant 2026 open application",
    "Innovate UK Edge accelerator Ukraine startup 2026",
    "UK startup grant AI digital 2026 new open",
    "USF Ukrainian Startup Fund нова когорта грант 2026",
    "USAID Ukraine tech startup grant 2026 open",
    "EBRD Star Venture Ukraine startup 2026",
    "CRDF Global Ukraine startup grant 2026",
    "1991 Accelerator Ukraine grant 2026 open batch",
    "Moldova Innovation Technology Park MITP grant startup 2026",
    "ODIMM Moldova startup funding 2026",
    "Moldova AI tech startup grant 2026 open call",
    "RIF Cyprus INNOVATE SEED startup grant 2026",
    "Cyprus Digital Modernisation AI startup grant 2026",
    "MassChallenge 2026 open application AI startup",
    "Plug and Play 2026 digital health open batch",
    "Seedstars Eastern Europe startup 2026 open",
    "Startup Wise Guys 2026 AI SaaS open application",
    "Nordic Innovation startup grant 2026 AI",
    "Visegrad Fund startup grant Ukraine 2026",
    "new free startup program AI SaaS 2026 credits",
    "startup credits program AI tools new 2026",
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

def research_grants(query: str, client: anthropic.Anthropic) -> list[dict]:
    prompt = f"""
Ти — грант-аналітик для українського AI стартапу Psynex.

Профіль:
{PSYNEX_PROFILE}

Запит: "{query}"
Сьогодні: {datetime.now().strftime('%d.%m.%Y')}

Знайди РЕАЛЬНІ відкриті гранти та безкоштовні startup programs де Psynex може отримати гроші або безкоштовні credits.
НЕ включай loans, субсидовані позики або платні програми.
НЕ включай програми зі списків "ВЖЕ ОТРИМАНІ", "ВІДХИЛЕНІ", "ВЖЕ В ПАЙПЛАЙНІ".
НЕ включай програми що вимагають >12 місяців існування.

Відповідай ЛИШЕ JSON (без markdown):
[
  {{
    "title": "Назва",
    "url": "https://...",
    "deadline": "ДД.ММ.РРРР або Rolling",
    "amount": "суму або credits",
    "type": "grant або credits або accelerator",
    "country": "EU або UK або UA або CY або MD або Global",
    "score": 8,
    "reason": "чому підходить Psynex — одне речення"
  }}
]
Тільки score >= 5. Максимум 5. Якщо нічого — поверни [].
"""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text) if text and text != "[]" else []
    except Exception as e:
        print(f"  ⚠ {e}")
        return []

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
        timeout=10
    ).raise_for_status()

def format_grant(g: dict) -> str:
    score = g.get("score", 0)
    emoji = "🔥" if score >= 9 else "✅" if score >= 7 else "🟡"
    flag = {"EU":"🇪🇺","UK":"🇬🇧","UA":"🇺🇦","CY":"🇨🇾","MD":"🇲🇩","Global":"🌍"}.get(g.get("country",""),"🌐")
    gtype = {"grant":"💵 Грант","credits":"💳 Credits","accelerator":"🚀 Акселератор"}.get(g.get("type",""),"💰")
    return (
        f"{emoji} {flag} <b>{g['title']}</b> [{score}/10]\n\n"
        f"{gtype}\n"
        f"💰 <b>Сума:</b> {g.get('amount','?')}\n"
        f"📅 <b>Дедлайн:</b> {g.get('deadline','?')}\n"
        f"🎯 {g.get('reason','—')}\n\n"
        f"🔗 {g.get('url','')}"
    )

def main():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"\n{'='*50}\nPsynex Grant Bot | {now}\n{'='*50}")

    seen = load_seen()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    all_grants, seen_titles = [], set()

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{len(SEARCH_QUERIES)}] {query[:55]}...")
        for g in research_grants(query, client):
            t = g.get("title", "")
            if t and t not in seen_titles:
                seen_titles.add(t)
                all_grants.append(g)

    new_grants = [
        (grant_id(g["title"]), g) for g in all_grants
        if grant_id(g.get("title","")) not in seen and g.get("score",0) >= MIN_SCORE
    ]
    new_grants.sort(key=lambda x: x[1].get("score",0), reverse=True)

    print(f"\n🆕 Нових: {len(new_grants)}")
    if not new_grants:
        save_seen(seen)
        return

    sent = 0
    for gid, g in new_grants:
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
    print(f"✅ Надіслано: {sent}")

if __name__ == "__main__":
    main()
