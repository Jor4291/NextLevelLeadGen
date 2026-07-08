from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.auth.security import hash_password
from backend.models import User, UserRole
from backend.settings import settings

logger = logging.getLogger(__name__)


def ensure_admin_user(db: Session) -> None:
    """Create or update the bootstrap admin from environment variables."""
    if not settings.admin_email or not settings.admin_password:
        if settings.auth_required:
            logger.warning(
                "AUTH_REQUIRED is true but ADMIN_EMAIL/ADMIN_PASSWORD are not set. "
                "Set them to create the first admin user."
            )
        return

    email = settings.admin_email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.role != UserRole.ADMIN:
            existing.role = UserRole.ADMIN
            db.commit()
        return

    admin = User(
        email=email,
        name=settings.admin_name or "Admin",
        password_hash=hash_password(settings.admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    logger.info("Bootstrap admin user created: %s", email)
