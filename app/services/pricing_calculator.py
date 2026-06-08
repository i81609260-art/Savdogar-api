"""Pricing calculator for tour requests based on parameters."""

from typing import Optional


class PricingCalculator:
    """Calculate tour pricing based on request parameters."""

    BASE_PRICE = 500  # Base price per person per day

    DESTINATION_MULTIPLIERS = {
        "Turkiya": 1.0,
        "Dubay": 1.5,
        "Misr": 1.2,
        "Saudiya Arabistoni": 1.3,
        "Boshqa": 1.1,
    }

    HOTEL_RATING_MULTIPLIERS = {
        "3⭐": 1.0,
        "4⭐": 1.3,
        "5⭐": 1.8,
        "Farqi yo'q": 1.1,
    }

    MEAL_PLAN_MULTIPLIERS = {
        "Faqat nonushta": 1.0,
        "2 mahal": 1.3,
        "3 mahal": 1.6,
        "All Inclusive": 2.0,
    }

    TOUR_TYPE_MULTIPLIERS = {
        "Faqat mehmonxona": 1.0,
        "Standart": 1.5,
        "To'liq paket": 2.2,
        "VIP": 3.0,
    }

    @staticmethod
    def calculate_duration(start_date: Optional[str], end_date: Optional[str]) -> int:
        """Calculate duration in days from dates."""
        if not start_date or not end_date:
            return 5  # Default 5 days

        try:
            from datetime import datetime
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            duration = (end - start).days
            return max(duration, 1)  # Minimum 1 day
        except (ValueError, TypeError):
            return 5

    @classmethod
    def calculate_price(
        cls,
        destination: Optional[str] = None,
        group_size: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        hotel_rating: Optional[str] = None,
        meal_plan: Optional[str] = None,
        tour_type: Optional[str] = None,
        budget: Optional[float] = None,
    ) -> dict:
        """
        Calculate tour pricing.
        Returns dict with:
        - min_price: Minimum total price
        - max_price: Maximum total price
        - per_person_min: Minimum per-person price
        - per_person_max: Maximum per-person price
        - duration: Tour duration in days
        - group_size: Number of people
        """
        # Validate and set defaults
        group_size = group_size or 2
        duration = cls.calculate_duration(start_date, end_date)

        # Get multipliers
        dest_mult = cls.DESTINATION_MULTIPLIERS.get(destination or "Boshqa", 1.1)
        hotel_mult = cls.HOTEL_RATING_MULTIPLIERS.get(hotel_rating or "3⭐", 1.0)
        meal_mult = cls.MEAL_PLAN_MULTIPLIERS.get(meal_plan or "Faqat nonushta", 1.0)
        tour_mult = cls.TOUR_TYPE_MULTIPLIERS.get(tour_type or "Standart", 1.5)

        # Calculate base price per person
        base_per_person = cls.BASE_PRICE * duration
        calculated_per_person = base_per_person * dest_mult * hotel_mult * meal_mult * tour_mult

        # Add variance (hotels might have different prices)
        per_person_min = calculated_per_person * 0.9
        per_person_max = calculated_per_person * 1.2

        # Total for group
        total_min = per_person_min * group_size
        total_max = per_person_max * group_size

        # If user provided a budget, compare
        budget_match = None
        if budget:
            if total_min <= budget <= total_max:
                budget_match = "exact"
            elif budget < total_min:
                budget_match = "below"
            else:
                budget_match = "above"

        return {
            "min_price": round(total_min, 2),
            "max_price": round(total_max, 2),
            "per_person_min": round(per_person_min, 2),
            "per_person_max": round(per_person_max, 2),
            "average_price": round((total_min + total_max) / 2, 2),
            "duration": duration,
            "group_size": group_size,
            "user_budget": budget,
            "budget_match": budget_match,
            "recommendation": cls.get_recommendation(total_min, total_max, budget),
        }

    @staticmethod
    def get_recommendation(
        min_price: float, max_price: float, user_budget: Optional[float]
    ) -> str:
        """Get recommendation based on budget and calculated price."""
        if not user_budget:
            return f"Taxminiy narx ${min_price:.0f} - ${max_price:.0f}"

        if user_budget < min_price:
            shortage = min_price - user_budget
            return f"Budjet kam, hech bo'lmaganda ${shortage:.0f} ko'proq kerak"
        elif user_budget > max_price:
            extra = user_budget - max_price
            return f"Budjet yetarli! Qo'shimcha ${extra:.0f} mavjud"
        else:
            return "Budjet mos keladi! ✓"
