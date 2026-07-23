"""Reports and dashboard schemas."""

from typing import Dict, List

from pydantic import BaseModel


class SalesDataPoint(BaseModel):
    """Single period sales data."""

    period: str
    revenue: float
    bookings_count: int


class TopTourItem(BaseModel):
    """Top selling tour."""

    tour_id: int
    tour_title: str
    bookings_count: int
    revenue: float


class StatusDistribution(BaseModel):
    """Booking status chart data."""

    pending: int
    confirmed: int
    cancelled: int


class DashboardStats(BaseModel):
    """Admin dashboard KPIs."""

    today_bookings: int
    today_revenue: float
    active_tours: int
    total_customers: int
    pending_bookings: int


class ReportsResponse(BaseModel):
    """Full reports payload."""

    sales: List[SalesDataPoint]
    top_tours: List[TopTourItem]
    status_distribution: StatusDistribution
    dashboard: DashboardStats


class SuperAdminStats(BaseModel):
    """Platform-wide statistics."""

    total_companies: int
    pending_companies: int
    approved_companies: int
    total_users: int
    total_tours: int
    total_bookings: int
    total_revenue: float


class OverviewTrendPoint(BaseModel):
    """Trend grafigining bitta nuqtasi (soat/kun/oy)."""

    label: str
    visits: int
    users: int
    bookings: int
    revenue: float


class OverviewTopItem(BaseModel):
    """Reyting jadvalining bitta qatori (kompaniya yoki tur)."""

    id: int
    name: str
    bookings: int
    revenue: float


class OverviewResponse(BaseModel):
    """Dashboard umumiy ko'rinishi — superadmin yoki bitta firma uchun."""

    scope: str  # "platform" | "company"
    range: str  # 24h | 7d | 28d | 1y | all

    total_visits: int
    total_users: int
    total_bookings: int
    total_revenue: float

    daily_active: int
    monthly_active: int

    # Faqat platforma uchun (firma ko'rinishida 0 bo'ladi).
    total_companies: int = 0
    pending_companies: int = 0
    total_tours: int = 0

    trends: List[OverviewTrendPoint] = []
    top: List[OverviewTopItem] = []
