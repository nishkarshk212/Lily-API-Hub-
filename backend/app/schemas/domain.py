"""Plan, Subscription, API Key, Payment, Gateway, and Admin schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlanBase(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    tagline: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=2000)
    price_paise: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=8)
    billing_cycle_days: int = Field(ge=1, le=3650)
    daily_request_limit: int = Field(ge=1)
    monthly_request_limit: int = Field(ge=1)
    rate_limit_per_minute: int = Field(ge=1)
    max_api_keys: int = Field(ge=1, le=100)
    allowed_methods: str = Field(default="GET,POST", max_length=80)
    allowed_endpoints: str = Field(default="*", max_length=2000)
    features_json: List[str] = Field(default_factory=list)
    badge: Optional[str] = Field(default=None, max_length=40)
    is_active: bool = True
    is_featured: bool = False
    sort_order: int = 0


class PlanCreateRequest(PlanBase):
    pass


class PlanUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    tagline: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    price_paise: Optional[int] = Field(default=None, ge=0)
    billing_cycle_days: Optional[int] = Field(default=None, ge=1, le=3650)
    daily_request_limit: Optional[int] = Field(default=None, ge=1)
    monthly_request_limit: Optional[int] = Field(default=None, ge=1)
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=1)
    max_api_keys: Optional[int] = Field(default=None, ge=1, le=100)
    allowed_methods: Optional[str] = Field(default=None, max_length=80)
    allowed_endpoints: Optional[str] = Field(default=None, max_length=2000)
    features_json: Optional[List[str]] = None
    badge: Optional[str] = Field(default=None, max_length=40)
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None


class PlanOut(PlanBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    masked_key: str
    key_prefix: str
    key_last4: str
    status: str
    master_link_tag: str
    total_requests: int
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    subscription_id: str


class CreateOrderRequest(BaseModel):
    plan_id: str
    action: str = Field(default="new", pattern=r"^(new|renew|upgrade)$")


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=4, max_length=120)
    razorpay_payment_id: str = Field(min_length=4, max_length=120)
    razorpay_signature: str = Field(min_length=16, max_length=256)


class CancelOrderRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=4, max_length=120)
    reason: str = Field(default="Checkout dismissed by user", max_length=255)


class MarkFailedRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=4, max_length=120)
    razorpay_payment_id: Optional[str] = Field(default=None, max_length=120)
    reason: str = Field(default="Payment failed at gateway", max_length=500)


class PlaygroundExecuteRequest(BaseModel):
    api_key_id: Optional[str] = None
    raw_api_key: Optional[str] = None
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    endpoint: str = Field(default="/v1/status", min_length=1, max_length=300)
    auth_mode: str = Field(default="x_api_key", pattern=r"^(x_api_key|bearer)$")
    query_params: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None


class AdminUserUpdateRequest(BaseModel):
    is_suspended: Optional[bool] = None
    suspension_reason: Optional[str] = Field(default=None, max_length=500)
    role: Optional[str] = Field(default=None, pattern=r"^(user|admin)$")
    is_email_verified: Optional[bool] = None
    is_active: Optional[bool] = None


class AdminMasterConfigUpdateRequest(BaseModel):
    gateway_mode: str = Field(pattern=r"^(hybrid|proxy|builtin)$")
    upstream_base_url: str = Field(default="", max_length=500)
    master_api_key: Optional[str] = Field(default=None, max_length=1000)
    auth_header_name: str = Field(default="Authorization", min_length=1, max_length=64)
    auth_scheme: str = Field(default="Bearer", max_length=32)
    timeout_ms: int = Field(default=10000, ge=500, le=60000)
    forward_user_context_headers: bool = True


class AdminBrandingUpdateRequest(BaseModel):
    app_name: str = Field(min_length=2, max_length=80)
    company_name: str = Field(min_length=2, max_length=80)
    brand_badge_letter: str = Field(default="", max_length=4)
    support_email: str = Field(min_length=3, max_length=255)
    site_description: str = Field(default="", max_length=500)
    api_key_prefix_live: str = Field(default="beta_live_", min_length=2, max_length=24, pattern=r"^[a-zA-Z0-9_-]+$")
    api_key_prefix_test: str = Field(default="beta_test_", min_length=2, max_length=24, pattern=r"^[a-zA-Z0-9_-]+$")
    receipt_prefix: str = Field(default="BETA", min_length=2, max_length=16, pattern=r"^[a-zA-Z0-9_-]+$")


class TelegramBotConnectRequest(BaseModel):
    bot_token: str = Field(min_length=20, max_length=200)
    bot_name: Optional[str] = Field(default=None, max_length=120)
    api_key_id: Optional[str] = None
    access_mode: str = Field(default="owner_only", pattern=r"^(owner_only|public_gateway)$")
    connection_mode: Optional[str] = Field(default=None, pattern=r"^(webhook|polling)$")
    welcome_message: str = Field(default="", max_length=2000)
    custom_proxy_path: str = Field(default="", max_length=200)
    custom_proxy_method: str = Field(default="POST", pattern=r"^(GET|POST)$")
    forward_plain_text: bool = False
    notify_owner_alerts: bool = True


class TelegramBotUpdateRequest(BaseModel):
    bot_token: Optional[str] = Field(default=None, min_length=20, max_length=200)
    bot_name: Optional[str] = Field(default=None, max_length=120)
    api_key_id: Optional[str] = None
    access_mode: Optional[str] = Field(default=None, pattern=r"^(owner_only|public_gateway)$")
    connection_mode: Optional[str] = Field(default=None, pattern=r"^(webhook|polling)$")
    is_active: Optional[bool] = None
    welcome_message: Optional[str] = Field(default=None, max_length=2000)
    custom_proxy_path: Optional[str] = Field(default=None, max_length=200)
    custom_proxy_method: Optional[str] = Field(default=None, pattern=r"^(GET|POST)$")
    forward_plain_text: Optional[bool] = None
    notify_owner_alerts: Optional[bool] = None


class TelegramUserPreferencesRequest(BaseModel):
    notify_quota_alerts: Optional[bool] = None
    notify_security_alerts: Optional[bool] = None
    notify_payment_alerts: Optional[bool] = None
    notify_gateway_errors: Optional[bool] = None


class TelegramSimulateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    as_owner: bool = True


class AdminPlatformTelegramRequest(BaseModel):
    bot_token: Optional[str] = Field(default=None, min_length=20, max_length=200)
    bot_name: Optional[str] = Field(default=None, max_length=120)
    connection_mode: Optional[str] = Field(default=None, pattern=r"^(webhook|polling)$")
    is_active: bool = True
    welcome_message: str = Field(default="", max_length=2000)
    custom_proxy_path: str = Field(default="", max_length=200)
    custom_proxy_method: str = Field(default="POST", pattern=r"^(GET|POST)$")
    forward_plain_text: bool = False


class AdminTelegramBroadcastRequest(BaseModel):
    message: str = Field(min_length=2, max_length=3500)
    test_only: bool = False

