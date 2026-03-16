from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Tool

router = APIRouter(tags=["tools"])


class ToolItem(BaseModel):
    slug: str
    name: str
    description: str | None


class ToolsResponse(BaseModel):
    tools: list[ToolItem]


@router.get("/tools", response_model=ToolsResponse)
async def list_tools(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolsResponse:
    """Return all active tools."""
    result = await db.execute(
        select(Tool)
        .where(Tool.is_active.is_(True))
    )
    tools = result.scalars().all()
    return ToolsResponse(
        tools=[
            ToolItem(slug=t.slug, name=t.name, description=t.description)
            for t in tools
        ]
    )
