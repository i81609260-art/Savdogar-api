"""Pagination helpers for list endpoints."""

from math import ceil
from typing import Generic, List, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated API response."""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(items: List[T], total: int, page: int, page_size: int) -> PaginatedResponse[T]:
    """Build a paginated response from items and metadata."""
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size > 0 else 0,
    )
