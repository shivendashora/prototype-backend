"""AI Education — courses + lead capture API."""
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from ..db import SessionDep
from ..data import load
from ..models import Lead
from ..schemas import Ack, LeadIn

router = APIRouter(prefix="/api/edu", tags=["AI Education"])

MESSAGES = {
    "register": "Seat reserved! Check your email for the payment link and batch details.",
    "enquiry": "Got it — a programme advisor will reply within 24 hours.",
    "brochure": "Brochure sent to your inbox. Happy reading!",
    "callback": "We'll call you within one working day.",
}


@router.get("/courses")
async def list_courses():
    return load("courses")


@router.get("/courses/{course_id}")
async def get_course(course_id: str):
    for c in load("courses"):
        if c["id"] == course_id:
            return c
    raise HTTPException(404, "Course not found")


@router.post("/leads", response_model=Ack, status_code=201)
async def capture_lead(body: LeadIn, session: SessionDep):
    if body.course_id:
        await get_course(body.course_id)
    lead = Lead(
        course_id=body.course_id, kind=body.kind, name=body.name,
        email=str(body.email), phone=body.phone, payload=body.model_dump(mode="json"),
    )
    session.add(lead)
    await session.commit()
    # Hook point: push to CRM / WhatsApp / email sequence (n8n webhook) here.
    return Ack(id=lead.id, message=MESSAGES[body.kind])


@router.get("/stats")
async def stats(session: SessionDep):
    return {"leads": await session.scalar(select(func.count()).select_from(Lead))}
