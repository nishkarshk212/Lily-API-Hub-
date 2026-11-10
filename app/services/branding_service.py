"""Runtime site branding resolution combining DB admin overrides with .env defaults."""

from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.gateway import SiteBrandingConfig


def get_effective_branding(db: Optional[Session] = None, settings: Optional[Settings] = None) -> Dict[str, str]:
    cfg = settings or get_settings()
    row = None
    if db is not None:
        try:
            row = db.get(SiteBrandingConfig, 1)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            row = None

    app_name = (row.app_name.strip() if row and row.app_name.strip() else cfg.APP_NAME)
    company_name = (row.company_name.strip() if row and row.company_name.strip() else cfg.COMPANY_NAME)
    raw_letter = (
        row.brand_badge_letter.strip()
        if row and row.brand_badge_letter.strip()
        else (cfg.BRAND_BADGE_LETTER.strip() or app_name[:1] or "A")
    )
    brand_letter = raw_letter[:1].upper()
    support_email = (row.support_email.strip() if row and row.support_email.strip() else cfg.SUPPORT_EMAIL)
    site_description = (
        row.site_description.strip()
        if row and row.site_description.strip()
        else cfg.SITE_META_DESCRIPTION
    )
    key_prefix_live = (
        row.api_key_prefix_live.strip()
        if row and row.api_key_prefix_live.strip()
        else cfg.API_KEY_PREFIX_LIVE
    )
    key_prefix_test = (
        row.api_key_prefix_test.strip()
        if row and row.api_key_prefix_test.strip()
        else cfg.API_KEY_PREFIX_TEST
    )
    receipt_prefix = (
        row.receipt_prefix.strip().upper()
        if row and row.receipt_prefix.strip()
        else (cfg.RECEIPT_PREFIX or "API").strip().upper()
    )

    return {
        "app_name": app_name,
        "company_name": company_name,
        "brand_letter": brand_letter,
        "support_email": support_email,
        "site_description": site_description,
        "api_key_prefix_live": key_prefix_live,
        "api_key_prefix_test": key_prefix_test,
        "receipt_prefix": receipt_prefix,
        "updated_by_email": row.updated_by_email if row else None,
        "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
        "has_db_override": bool(row and any([
            row.app_name.strip(),
            row.company_name.strip(),
            row.brand_badge_letter.strip(),
            row.support_email.strip(),
            row.site_description.strip(),
            row.api_key_prefix_live.strip(),
            row.api_key_prefix_test.strip(),
            row.receipt_prefix.strip(),
        ])),
    }

