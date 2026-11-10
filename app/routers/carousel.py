"""AI-powered content creation — carousel generator API."""
from fastapi import APIRouter

from ..db import SessionDep
from ..models import Carousel as CarouselRow
from ..schemas import Carousel, CarouselRequest
from ..services.carousel_ai import ai_enabled, generate_carousel

router = APIRouter(prefix="/api/carousel", tags=["Carousel Studio"])


@router.get("/status")
async def status():
    return {"ai_enabled": ai_enabled()}


@router.post("/generate", response_model=Carousel)
async def generate(body: CarouselRequest, session: SessionDep):
    carousel = await generate_carousel(body)
    session.add(CarouselRow(idea=body.idea, source=carousel.source, payload=carousel.model_dump(mode="json")))
    await session.commit()
    return carousel
