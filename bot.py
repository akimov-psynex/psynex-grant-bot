"""
Psynex Grant Research Bot v2.0
==============================
Точний пошук грантів під специфіку Psynex з Лев-інспектором валідацією.

Ключові покращення v2.0 (на основі аналізу 16 програм перевірених вручну):
1. Лев-інспектор як SYSTEM PROMPT валідація — бот відсікає погані програми
   ДО повернення result, не після.
2. MIN_SCORE підвищено з 6 до 8 — зменшує false positives.
3. Розширений EXCLUSION список — 16+ програм перевірено і відкинуто.
4. Hard structural blockers — Delaware C-Corp, Web3, geopolitics, no VC funding.
5. Peer group definition — Consumer B2C dating app, НЕ AI infra/enterprise/deep tech.
6. Verification URL обов'язковий — підтвердження що програма ВІДКРИТА в 2026.
7. Менше запитів (12 замість 35), точніших, з negative keywords.
8. Output schema розширений — peer_group_fit, structural_blockers, stack_compatibility,
   real_value_estimate, lev_notes.
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
MIN_SCORE      = 8  # Підвищено з 6 до 8 — суворіша фільтрація

# ============================================================
# PROFILE — повний контекст для Claude
# ============================================================

PSYNEX_PROFILE = """
КОМПАНІЯ:
- ТОВ «ПСАЙНЕКС» (бренд: Psynex), сайт: psynex.app
- Юрисдикція: Україна (Київ), Diia.City резидент
- ЄДРПОУ: 46150138, реєстрація: 12.11.2025
- EU Funding Portal PIC: 864846957
- Horizon Europe: eligible (Україна — асоційована країна)

ПРОДУКТ — КАТЕГОРІЯ:
- AI dating app — Consumer B2C
- Helping people build lasting relationships through behavioral pattern analysis
- 4 модулі: Explorer, MindID, Match, Insight (Connect — Phase 2)
- 6 наукових фреймворків: Rosenzweig, Leary, Beck, Bowlby/Ainsworth,
  Thomas-Kilmann, Lazarus-Folkman
- Web MVP live, App Store + Google Play launch July 2026

ПРОФІЛЬ ПРОДУКТУ:
- Consumer mobile/web application (B2C)
- AI as application layer (using LLMs as service: Claude API)
- Dating / Self-discovery / Behavioral psychology
- Multilingual AI pipeline — глобальна аудиторія

NOT профіль (КРИТИЧНО для фільтрації):
- НЕ AI infrastructure / foundation models / inference platforms
- НЕ Enterprise B2B SaaS
- НЕ Web3 / Blockchain / Crypto
- НЕ Deep tech (biotech, robotics, quantum, hardware)
- НЕ Healthcare / Medical / MedTech regulated
- НЕ Mental health / Therapy / Wellness platform

СТАДІЯ:
- Pre-seed, $0 raised externally
- SAFE round in progress: $250K @ $2.5M post-money cap
- Founders' capital: $109,966
- Команда: 3 core + 4 equity participants (<10 employees)

СТЕК:
- Frontend: Next.js на Vercel (Frankfurt)
- Backend: Supabase (PostgreSQL)
- AI: Claude API через AWS Bedrock + Anthropic direct
- Voice: ElevenLabs
- Analytics: PostHog + Mixpanel + Sentry
"""

# ============================================================
# EXCLUSION LIST — повний список програм які НЕ пропонувати
# ============================================================

EXCLUSION_LIST = """
========== ВЖЕ ОТРИМАНІ — НЕ ПРОПОНУВАТИ ПОВТОРНО: ==========
- Anthropic for Startups ($1,500 credits)
- AWS Activate ($25,100 credits)
- ElevenLabs (33M characters)
- Mixpanel (1 рік безкоштовно)
- PostHog ($50,000 credits)
- Sentry ($5,000 credits)
- Microsoft for Startups ($1K small + $150K Azure tier pending verification)
- NVIDIA Inception (approved 30.04.2026 — DGX Cloud, DLI, hardware discounts)

========== ВІДХИЛЕНІ — НЕ ПРОПОНУВАТИ БЕЗ ЗМІНИ ОБСТАВИН: ==========
- Google for Startups Cloud (rejected 31.03.2026)
- Vercel for Startups (rejected 30.03.2026)

========== В ПАЙПЛАЙНІ — НЕ ДУБЛЮВАТИ: ==========
- USF EDGE (Ukrainian Startup Fund) — pending
- EIT Jumpstarter — pending
- Cloudflare for Startups — pending (status check sent 30.04.2026)
- Intercom Early Stage Program — signup blocked, retry pending
- Startup World Cup Ukraine 2026 — pitch deck v17 in preparation
- Entrepreneurship World Cup 2026 — secondary, deadline 31.05.2026

========== ПЕРЕВІРЕНО І ВІДКИНУТО ЛЕВ-ІНСПЕКТОРОМ — НЕ ПОВТОРЮВАТИ: ==========
ЗАКРИТІ ПРОГРАМИ (final cohort/concluded/no longer offered):
- Google for Startups Ukraine Support Fund (final cohort June 2025)
- Twilio Segment Startup Program ("we do not offer additional credits")
- Seeds of Bravery (project complete March 2026)
- AI Grant Batch 4 (closed)

STRUCTURAL BLOCKERS:
- AI Grant — Delaware C-Corp required (breaks Diia.City)
- YC Summer 2026 — Delaware C-Corp blocker

NOT PEER GROUP / NOT STACK:
- IBM GEP — watsonx vs Claude conflict, B2B/enterprise focus
- Oracle for Startups — OCI vs AWS/Vercel/Supabase, AI infra focus
- Alibaba Cloud — geopolitical risk
- AITECH AI Grants — Web3/crypto exclusivity
- Google Cloud Scale Tier — institutional VC funding required ($0 raised)

PREMATURE / TIMING WRONG:
- Retool for Startups — premature for our stage
- Eurostars EUREKA — 12-18 months away, requires consortium
- SpinLab Accelerator — too early for us
- Freshworks for Startups — credits expiration uncertain

ALREADY SCREENED EARLIER:
- DigitalOcean Hatch (marginal)
- OVHcloud for Startups (marginal)
- Open Horizons
- EIC Pre-Accelerator 2027
- EIC Accelerator Step 1 (paused 21.04.2026)
"""

# ============================================================
# LEV INSPECTOR — система валідації
# ============================================================

LEV_INSPECTOR_RULES = """
🔍 ЛЕВ-ІНСПЕКТОР — ОБОВ'ЯЗКОВІ ПРАВИЛА ВАЛІДАЦІЇ

ПЕРЕД ВКЛЮЧЕННЯМ ПРОГРАМИ В РЕЗУЛЬТАТ — ПРОЙДИ ВСІ 7 ПЕРЕВІРОК:

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 1: АКТИВНІСТЬ (CRITICAL)
═══════════════════════════════════════════════════════════
- Знайди ПУБЛІЧНЕ ПІДТВЕРДЖЕННЯ що applications ВІДКРИТІ зараз (2026 H2)
- Шукай останні news про програму за last 6 months
- TRIGGER WORDS для виключення (якщо знайдеш — ВИКЛЮЧИ):
  * "final cohort"
  * "closed"
  * "complete" / "completed"
  * "concluded"
  * "no longer offered"
  * "project ended"
  * "applications are closed"
  * "we do not offer additional credits"
- Дата ОСТАННЬОГО оголошення нової cohort/batch має бути ≥ 2025 H2

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 2: PEER GROUP FIT
═══════════════════════════════════════════════════════════
Psynex = Consumer B2C dating app
ВИКЛЮЧАЙ якщо програма exclusively для:
- AI infrastructure / foundation models / inference platforms
- Enterprise B2B SaaS
- Deep tech (biotech, robotics, quantum, hardware)
- Healthcare/Medical regulated
- FinTech regulated
- Web3/Blockchain/Crypto
ПРИЙМАЙ якщо програма open для:
- Consumer apps / B2C
- Loose-criteria SaaS / mobile apps
- Cross-industry "all startups welcome"

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 3: STRUCTURAL BLOCKERS
═══════════════════════════════════════════════════════════
ВИКЛЮЧАЙ якщо вимагається:
- Delaware C-Corp (ламає наш Diia.City status)
- Реєстрація в US specifically
- Web3/blockchain/crypto exclusivity
- Institutional VC funding committed (ми ще $0 raised externally)
- China/Russia/Iran/N.Korea-affiliated
- >12 months company age (нам 5.5 місяців)
- >50 employees (нам <10)
- Already-relocated до EU (ми Ukraine-based)

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 4: STACK COMPATIBILITY
═══════════════════════════════════════════════════════════
- Якщо credits можна освоїти ТІЛЬКИ через міграцію стеку
  (Oracle OCI, IBM watsonx, китайські cloud) → знизь score до 4/10 max
- Програми сумісні з нашим стеком (AWS Bedrock, Vercel, Supabase, Claude API,
  PostHog, Mixpanel, Sentry, ElevenLabs) → prioritize
- Cash grants (без stack lock-in) → завжди prioritize над credits

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 5: HISTORICAL CHECK
═══════════════════════════════════════════════════════════
Програма НЕ повинна бути в списку EXCLUSION_LIST вище.
Якщо знайдеш дублікат або похідну — ВИКЛЮЧИ.

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 6: REAL VALUE CHECK
═══════════════════════════════════════════════════════════
- "До $X" credits — це top tier, дається тільки highly selected startups
- Реалістично оцінюй TYPICAL/MEDIAN value, не MAX
- Приклад: Oracle "до $100K" → typical $300 (Free Tier)
- Якщо реалістичний value < $5K cash або < $10K credits — знизь score

═══════════════════════════════════════════════════════════
ПЕРЕВІРКА 7: SCORE CALIBRATION (СТРОГО)
═══════════════════════════════════════════════════════════
- 9-10/10 = Critical fit, real cash, easy apply, high probability of approval
- 8/10 = Strong fit, real value, reasonable probability
- 7/10 і нижче = НЕ ВКЛЮЧАТИ В РЕЗУЛЬТАТ
- Без anchor benchmarks (типу "як AWS Activate" або "як Microsoft for Startups")
  не давай 8+

═══════════════════════════════════════════════════════════
ПРИНЦИП ЛЕВА:
═══════════════════════════════════════════════════════════
Помилкове включення програми = втрата 30+ хвилин часу засновників
на верифікацію. КРАЩЕ повернути [] ніж включити сумнівну програму.
КРАЩЕ 0 програм за день ніж 5 програм де 4 застаріли.
"""

# ============================================================
# SEARCH QUERIES — менше, точніше, з negative keywords
# ============================================================

SEARCH_QUERIES = [
    # === EU programs відкриті 2026 для consumer/SaaS ===
    "Horizon Europe open call 2026 SME consumer app eligible Ukraine",
    "Digital Europe Programme 2026 SME open call AI consumer",

    # === UK programs ===
    "Innovate UK Smart Grant 2026 open SME consumer software AI",

    # === Ukraine-specific 2026 ===
    "Ukrainian startup grant 2026 open consumer tech AI new program",
    "USF Ukrainian Startup Fund нова когорта 2026 consumer app",

    # === Eastern EU friendly jurisdictions ===
    "Cyprus RIF INNOVATE 2026 consumer SaaS startup grant",
    "Moldova MITP startup grant 2026 consumer tech",
    "Visegrad Fund startup grant Ukraine 2026 open",

    # === Global accelerators (excluding Delaware-required) ===
    "MassChallenge 2026 consumer B2C startup application Europe",
    "Plug and Play Europe 2026 consumer dating app batch",

    # === Specific niche ===
    "dating app startup grant 2026 Europe equity-free",
    "consumer mobile app grant 2026 Ukrainian startup eligible new",
]

# ============================================================
# HELPERS
# ============================================================

def load_seen() -> set:
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)

def grant_id(title: str, url: str = "") -> str:
    """Хешуємо по URL — URL унікальний, назва може варіюватись."""
    key = url.strip().rstrip("/").lower() if url else title.lower().strip()[:80]
    return hashlib.md5(key.encode()).hexdigest()[:12]

# ============================================================
# CORE RESEARCH — з Лев-інспектором
# ============================================================

def research_grants(query: str, client: anthropic.Anthropic) -> list[dict]:
    prompt = f"""
Ти — грант-аналітик з СУВОРОЮ Лев-інспектор валідацією для українського
consumer AI стартапу Psynex.

{PSYNEX_PROFILE}

{EXCLUSION_LIST}

{LEV_INSPECTOR_RULES}

ПОТОЧНИЙ ПОШУК: "{query}"
СЬОГОДНІ: {datetime.now().strftime('%d.%m.%Y')}

ЗАВДАННЯ:
1. Знайди РЕАЛЬНІ програми через web search
2. ДЛЯ КОЖНОЇ — застосуй ВСІ 7 правил Лев-інспектора (вище)
3. Відсікай програми BEFORE returning result, не після
4. Цитуй verification URL з останньою новиною про програму

ВКЛЮЧАЙ ТІЛЬКИ ЯКЩО:
✓ Знайшов public verification що applications відкриті в 2026 H2
✓ verification_url містить новину/announcement за останні 6 місяців
✓ Програма НЕ в EXCLUSION_LIST
✓ Peer group fit перевірений (consumer B2C, не AI infra/enterprise)
✓ Structural blockers відсутні
✓ Stack compatibility OK або acceptable trade-off
✓ Real value реалістичний для нашої стадії (≥$5K cash або ≥$10K credits typical)
✓ Score ≥ 8/10 (інакше — виключай з результату)

Відповідай ЛИШЕ JSON (без markdown):
[
  {{
    "title": "Назва програми",
    "url": "https://официальна-сторінка/apply",
    "verification_url": "https://підтвердження-active-2026/news",
    "last_verified_date": "ДД.ММ.РРРР",
    "deadline": "ДД.ММ.РРРР або Rolling",
    "amount": "конкретна сума або credits",
    "type": "grant або credits або accelerator",
    "country": "EU або UK або UA або CY або MD або Global",
    "score": 8,
    "peer_group_fit": "так — програма приймає consumer B2C",
    "structural_blockers": "немає",
    "stack_compatibility": "сумісна з AWS/Vercel/Supabase",
    "real_value_estimate": "$X typical (не максимум)",
    "lev_notes": "ключове застереження або 'без застережень'",
    "reason": "одне речення — чому fit для Psynex"
  }}
]

ОБМЕЖЕННЯ:
- Тільки score >= 8
- Максимум 3 програми за один search query
- Якщо НІЧОГО не fits — поверни []

КРАЩЕ повернути [] ніж включити сумнівну програму.
"""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3500,
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
        return json.loads(text) if text and text != "[]" else []
    except Exception as e:
        print(f"  ⚠ {e}")
        return []

# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text: str):
    if len(text) > 4096:
        text = text[:4090] + "..."
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
        timeout=10
    ).raise_for_status()

def format_grant(g: dict) -> str:
    score = g.get("score", 0)
    emoji = "🔥" if score >= 9 else "✅"
    flag = {
        "EU": "🇪🇺", "UK": "🇬🇧", "UA": "🇺🇦",
        "CY": "🇨🇾", "MD": "🇲🇩", "Global": "🌍"
    }.get(g.get("country", ""), "🌐")
    gtype = {
        "grant": "💵 Грант",
        "credits": "💳 Credits",
        "accelerator": "🚀 Акселератор"
    }.get(g.get("type", ""), "💰")

    return (
        f"{emoji} {flag} <b>{g['title']}</b> [{score}/10]\n\n"
        f"{gtype}\n"
        f"💰 <b>Сума:</b> {g.get('amount','?')}\n"
        f"💎 <b>Реалістично:</b> {g.get('real_value_estimate','?')}\n"
        f"📅 <b>Дедлайн:</b> {g.get('deadline','?')}\n"
        f"🎯 {g.get('reason','—')}\n\n"
        f"<b>🔍 Лев-інспектор:</b>\n"
        f"• Peer group: {g.get('peer_group_fit','?')}\n"
        f"• Blockers: {g.get('structural_blockers','?')}\n"
        f"• Stack: {g.get('stack_compatibility','?')}\n"
        f"• Notes: {g.get('lev_notes','—')}\n\n"
        f"🔗 <b>Apply:</b> {g.get('url','')}\n"
        f"✓ <b>Verify ({g.get('last_verified_date','?')}):</b> "
        f"{g.get('verification_url','—')}"
    )

# ============================================================
# MAIN
# ============================================================

def main():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"\n{'='*60}")
    print(f"Psynex Grant Bot v2.0 | {now}")
    print(f"MIN_SCORE: {MIN_SCORE} | Queries: {len(SEARCH_QUERIES)}")
    print(f"Лев-інспектор: 7 правил валідації активні")
    print(f"{'='*60}\n")

    seen = load_seen()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    all_grants, seen_urls = [], set()

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{len(SEARCH_QUERIES)}] {query[:55]}...")
        for g in research_grants(query, client):
            url = g.get("url", "").strip().rstrip("/").lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_grants.append(g)

    # Фільтр по seen + MIN_SCORE
    new_grants = [
        (grant_id(g.get("title", ""), g.get("url", "")), g)
        for g in all_grants
        if grant_id(g.get("title", ""), g.get("url", "")) not in seen
        and g.get("score", 0) >= MIN_SCORE
    ]
    new_grants.sort(key=lambda x: x[1].get("score", 0), reverse=True)

    print(f"\n🆕 Нових програм (score ≥ {MIN_SCORE}): {len(new_grants)}")

    if not new_grants:
        send_telegram(
            f"📭 <b>Psynex Grant Bot v2.0 — {now}</b>\n"
            f"Нових програм сьогодні: 0\n"
            f"Перевірено запитів: {len(SEARCH_QUERIES)}\n"
            f"MIN_SCORE: {MIN_SCORE} (Лев-інспектор активний)"
        )
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
        f"📊 <b>Psynex Grant Bot v2.0 — {now}</b>\n"
        f"Запитів: {len(SEARCH_QUERIES)} | Надіслано: {sent}\n"
        f"Лев-інспектор: всі програми пройшли 7 правил валідації"
    )
    save_seen(seen)
    print(f"✅ Надіслано: {sent}")

if __name__ == "__main__":
    main()
