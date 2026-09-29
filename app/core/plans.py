from app.models.organization import PlanTier

PLANS: dict[PlanTier, dict] = {
    PlanTier.free:       {"price_usd": 0,  "max_members": 5,    "max_projects": 3},
    PlanTier.pro:        {"price_usd": 12, "max_members": None, "max_projects": None},
    PlanTier.enterprise: {"price_usd": 20, "max_members": None, "max_projects": None},
}


class PlanLimitError(Exception):
    """Raised when an org has reached its plan limit."""

    def __init__(self, plan_tier: PlanTier, resource: str, limit: int):
        self.plan_tier = plan_tier
        self.resource = resource
        self.limit = limit
        super().__init__(
            f"plan '{plan_tier.value}' allows at most {limit} {resource}"
        )


def get_plan(plan_tier: PlanTier) -> dict:
    return PLANS[plan_tier]


def can_add_member(plan_tier: PlanTier, current_count: int) -> bool:
    limit = PLANS[plan_tier]["max_members"]
    return limit is None or current_count < limit


def can_add_project(plan_tier: PlanTier, current_count: int) -> bool:
    limit = PLANS[plan_tier]["max_projects"]
    return limit is None or current_count < limit