import os
"""
Throwaway verification script — creates one Organization and one User
so we can test the real login flow (correct password succeeds, wrong
password is rejected with 401) against actual Postgres data.
"""
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from config import DATABASE_URL
from db.models import Organization, User, UserRole, PlanTier

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

sync_url = (DATABASE_URL or "").replace("+asyncpg", "")
engine = create_engine(sync_url)

TEST_EMAIL = "test-admin@example.com"

if "RTAP_ADMIN_PW" not in os.environ:
    raise RuntimeError("RTAP_ADMIN_PW environment variable must be set to run seed_test_user.py")

TEST_PASSWORD = os.environ["RTAP_ADMIN_PW"]

with Session(engine) as db:
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org — Phase 1 Verification",
        plan_tier=PlanTier.trial,
    )
    db.add(org)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email=TEST_EMAIL,
        password_hash=pwd_context.hash(TEST_PASSWORD),
        role=UserRole.org_admin,
    )
    db.add(user)
    db.commit()

    print(f"Created org_id={org.id}")
    print(f"Created user: {TEST_EMAIL} / password: {TEST_PASSWORD}")
    print(f"user_id={user.id}")
