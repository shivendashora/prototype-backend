"""Carousel generation pipeline.

Raw idea -> research & structure -> headlines + slide copy -> visual direction.

If ANTHROPIC_API_KEY is set, Claude does all four steps in one structured-output
call. Otherwise (or if the call fails) a deterministic template engine produces a
usable draft so the studio always works offline.
"""
import json
import logging
import os
import re

from ..schemas import Carousel, CarouselRequest, Slide, VisualDirection

log = logging.getLogger(__name__)

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

THEMES = {
    "educational": VisualDirection(palette=["#0F3D3E", "#F4EFE6", "#F2A65A", "#1B1B1B"], heading_font="Fraunces", body_font="Inter",
                                   layout="Big serif headline top-left, body below, slide counter bottom-right", imagery="Flat line illustrations of pets and vets"),
    "bold": VisualDirection(palette=["#111827", "#FDE047", "#EF4444", "#111827"], heading_font="Archivo Black", body_font="Inter",
                            layout="Oversized headline, high-contrast colour blocks, one idea per slide", imagery="Cut-out pet photos on solid colour"),
    "friendly": VisualDirection(palette=["#EA580C", "#FFF7ED", "#FDBA74", "#1F2937"], heading_font="Baloo 2", body_font="Nunito",
                                layout="Rounded cards, emoji accents, centred text", imagery="Warm hand-drawn doodles"),
    "professional": VisualDirection(palette=["#0B1F3A", "#FFFFFF", "#3B82F6", "#0F172A"], heading_font="Plus Jakarta Sans", body_font="Inter",
                                    layout="Clean grid, left-aligned text, thin accent rule", imagery="Minimal icons and data charts"),
}

SYSTEM_PROMPT = """You are the content engine for a solo founder who runs Practo for Animals \
(an animal-care discovery platform in India) and an AI-skills education brand. You turn a raw \
idea into a ready-to-design social carousel.

Work through four steps internally: (1) research the topic and note 3-5 accurate, useful facts \
or angles (no invented statistics; if you cite a number, it must be widely documented, otherwise \
phrase it qualitatively); (2) structure a narrative: hook -> problem -> insights -> proof -> CTA; \
(3) write tight slide copy: headlines max 8 words, body max 30 words, plain language, no hashtags \
in slides; (4) choose a visual direction that fits the tone and platform.

The first slide must be kind "cover" and the last kind "cta". LinkedIn: more insight, professional \
voice. Instagram: punchier, more emotional, emoji allowed sparingly. Palette: 4 hex colours, \
[background, surface/text-contrast, accent, ink]."""


def _schema() -> dict:
    slide = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "eyebrow", "headline", "body", "visual_hint"],
        "properties": {
            "kind": {"type": "string", "enum": ["cover", "content", "stat", "quote", "cta"]},
            "eyebrow": {"type": "string"},
            "headline": {"type": "string"},
            "body": {"type": "string"},
            "visual_hint": {"type": "string"},
        },
    }
    visual = {
        "type": "object",
        "additionalProperties": False,
        "required": ["palette", "heading_font", "body_font", "layout", "imagery"],
        "properties": {
            "palette": {"type": "array", "items": {"type": "string"}},
            "heading_font": {"type": "string"},
            "body_font": {"type": "string"},
            "layout": {"type": "string"},
            "imagery": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "hook_options", "caption", "hashtags", "slides", "visual", "research_notes"],
        "properties": {
            "title": {"type": "string"},
            "hook_options": {"type": "array", "items": {"type": "string"}},
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "slides": {"type": "array", "items": slide},
            "visual": visual,
            "research_notes": {"type": "array", "items": {"type": "string"}},
        },
    }


def ai_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


_client = None


def _get_client():
    """One shared async client (reuses its HTTP connection pool across requests)."""
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic()
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def _generate_with_claude(req: CarouselRequest) -> Carousel | None:
    import anthropic

    client = _get_client()
    prompt = (
        f"Raw idea from the founder:\n{req.idea}\n\n"
        f"Platform: {req.platform}\nTone: {req.tone}\nBrand: {req.brand}\n"
        f"Number of slides: exactly {req.slides}.\n"
        "Return 3 hook options, a post caption (max 120 words) and 5-8 hashtags."
    )
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _schema()}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError:
        log.warning("Claude rate limited; using template engine")
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; using template engine", e.status_code)
        return None
    except anthropic.APIConnectionError:
        log.warning("Could not reach Claude API; using template engine")
        return None

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("Claude stop_reason=%s; using template engine", response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    data = json.loads(text)
    return Carousel(**data, source="claude")


# ---------------------------------------------------------------- template engine

def _topic(idea: str) -> str:
    first = re.split(r"[.\n!?]", idea.strip())[0]
    first = re.sub(r"^(a |an |the |how to |why |post about |carousel (about|on) )", "", first, flags=re.I).strip()
    return (first[:60] + "…") if len(first) > 60 else first


def _points(idea: str) -> list[str]:
    parts = [p.strip(" -•*") for p in re.split(r"[\n;]|(?<=[.!?])\s+|,\s*(?=[A-Z])", idea) if p.strip(" -•*")]
    return [p for p in parts[1:] if len(p) > 3]


SUPPORT_LINES = [
    "Do it today, not during a crisis. It takes five minutes and saves precious time later.",
    "Small habit, big difference. Your future self (and your pet) will thank you.",
    "When every minute counts, knowing this in advance keeps you calm and quick.",
    "Ask your vet how this applies to your pet's breed, age and health.",
    "Write it down and share it with everyone who cares for your pet.",
]


def _generate_with_template(req: CarouselRequest) -> Carousel:
    topic = _topic(req.idea)
    title_topic = topic[:1].upper() + topic[1:]
    points = _points(req.idea)
    defaults = [
        ("Start with the basics", f"Most people skip the fundamentals of {topic.lower()}. Get these right and everything else gets easier."),
        ("Know the warning signs", "Small changes in behaviour, appetite or energy are often the first signal. Don't wait for it to get worse."),
        ("Plan before you need it", "Save one trusted vet, one 24x7 hospital and one ambulance number today — not during an emergency."),
        ("Use verified sources", "Check reviews, timings and services before you go. Verified listings save you wasted trips."),
        ("Make it a routine", "Put check-ups, vaccinations and deworming on a calendar. Consistency beats intensity."),
        ("Ask the right questions", "Costs, aftercare, follow-ups — ask upfront so there are no surprises later."),
        ("Share what you learn", "Your experience can help another pet parent decide faster. Reviews matter."),
    ]
    content_needed = req.slides - 3  # cover, stat/quote, cta
    body_slides: list[Slide] = []
    for i in range(content_needed):
        if i < len(points):
            pt = points[i]
            head = " ".join(pt.split()[:7]).rstrip(".,")
            body = pt if len(pt.split()) > 7 else SUPPORT_LINES[i % len(SUPPORT_LINES)]
        else:
            head, body = defaults[i % len(defaults)]
        body_slides.append(Slide(kind="content", eyebrow=f"Tip {i + 1:02d}", headline=head, body=body,
                                 visual_hint="Icon or illustration matching the tip, left-aligned text"))

    insight = Slide(kind="quote", eyebrow="Remember", headline="Prepared pet parents panic less.",
                    body="Five minutes of planning today can save precious time when it matters most.",
                    visual_hint="Large pull-quote with accent quotation mark")
    cover = Slide(kind="cover", eyebrow=req.brand, headline=title_topic,
                  body=f"{content_needed} things every pet parent should know →",
                  visual_hint="Hero illustration, oversized headline, swipe arrow")
    cta = Slide(kind="cta", eyebrow="Your next step",
                headline="Find trusted care near you" if req.brand.lower().startswith("practo") else "Start learning today",
                body="Save this post, share it with a fellow pet parent, and follow for weekly tips.",
                visual_hint="Logo, handle and a button-style CTA")

    slides = [cover, *body_slides[:2], insight, *body_slides[2:], cta]
    tag = re.sub(r"[^A-Za-z0-9]", "", title_topic.title())[:28]
    return Carousel(
        title=title_topic,
        hook_options=[
            f"{title_topic}: what nobody tells you",
            f"{content_needed} mistakes to avoid with {topic.lower()}",
            f"Save this before you need it — {topic.lower()}",
        ],
        caption=(f"{title_topic} — a quick guide for pet parents. Swipe through for {content_needed} practical tips, "
                 f"save it for later, and tag someone who needs to see this. 🐾"),
        hashtags=[f"#{tag}", "#PetCare", "#PetParents", "#VetTips", "#AnimalWelfare", "#PractoForAnimals"],
        slides=slides,
        visual=THEMES[req.tone],
        research_notes=[
            "Template mode: connect an ANTHROPIC_API_KEY to enable AI research and copywriting.",
            "Verify any facts or numbers with a vet or trusted source before publishing.",
        ],
        source="template",
    )


async def generate_carousel(req: CarouselRequest) -> Carousel:
    if ai_enabled():
        try:
            result = await _generate_with_claude(req)
            if result:
                return result
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("Could not parse Claude output (%s); using template engine", e)
    return _generate_with_template(req)
