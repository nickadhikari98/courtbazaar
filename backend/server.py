"""
CourtBazaar - Legal Operations & Court Services Marketplace
Main FastAPI application
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Header, Query, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import hashlib
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict, Any
import uuid
import secrets
import asyncio
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'courtbazaar')
client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=3000)
db = client[db_name]

# Config
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required and must not be empty. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
APP_NAME = os.environ.get('APP_NAME', 'courtbazaar')
# Google Identity Services — the frontend runs the real Google sign-in button
# with this Client ID and hands us back a signed ID token, verified below in
# /auth/google/session. No third-party broker sits in between, so the only
# domain a user ever sees on Google's own "Choose an account" screen is
# whatever app name/domain this Client ID's OAuth consent screen is
# configured with in Google Cloud Console — never a domain of ours.
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_OAUTH_ENABLED = os.environ.get('GOOGLE_OAUTH_ENABLED', 'false').lower() == 'true' and bool(GOOGLE_CLIENT_ID)
CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(',')
MAX_UPLOAD_SIZE_BYTES = int(os.environ.get('MAX_UPLOAD_SIZE_BYTES', str(10 * 1024 * 1024)))  # 10MB default
ALLOWED_UPLOAD_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
ALLOWED_UPLOAD_CONTENT_TYPES = {
    'application/pdf', 'image/jpeg', 'image/jpg', 'image/png',
}
# Image-only subset for review photos — KYC lead documents (validate_upload
# above) legitimately need 'pdf'; a review's profile photo never does.
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
ALLOWED_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png'}

app = FastAPI(title="CourtBazaar API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def ensure_db_ready() -> bool:
    try:
        await client.admin.command('ping')
        return True
    except Exception as exc:
        logger.warning("MongoDB unavailable at startup: %s", exc)
        return False

# ===== Storage =====
# S3-compatible (Cloudflare R2 by default, swappable to AWS S3 via env vars) —
# see storage.py. Replaces the old Emergent-platform-specific object store.
from storage import put_object, get_object, delete_object, presigned_download_url


async def delete_order_files(order_id: str) -> dict:
    """Delete all files attached to an order (DPDP compliance - wipe after job done)."""
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        return {"deleted": 0}
    file_ids = order.get("file_ids", [])
    if not file_ids:
        return {"deleted": 0}
    deleted = 0
    for fid in file_ids:
        rec = await db.files.find_one({"file_id": fid, "is_deleted": False}, {"_id": 0})
        if not rec:
            continue
        ok = delete_object(rec["storage_path"])
        await db.files.update_one({"file_id": fid}, {"$set": {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_reason": f"order_completed:{order_id}",
            "storage_purged": ok,
        }})
        deleted += 1
    logger.info(f"DPDP: purged {deleted} files for order {order_id}")
    return {"deleted": deleted, "order_id": order_id}


def validate_upload(filename: str, content_type: Optional[str], size: int) -> None:
    """Shared guard for every file-upload endpoint. Raises HTTPException on rejection."""
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")
    if content_type and content_type.lower() not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported content type '{content_type}'")
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(400, f"File too large. Max size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")
    if size == 0:
        raise HTTPException(400, "Uploaded file is empty")


def validate_image_upload(filename: str, content_type: Optional[str], size: int) -> None:
    """Same shape as validate_upload, but image-only (no 'pdf') — for review
    photos, which unlike KYC documents are always meant to be a picture."""
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")
    if content_type and content_type.lower() not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported content type '{content_type}'")
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(400, f"File too large. Max size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")
    if size == 0:
        raise HTTPException(400, "Uploaded file is empty")

# ===== Auth helpers =====
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def make_jwt(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

# Default capability bundle granted by each profile type / legacy role. Purely
# additive to the existing single-`role` authorization system — nothing reads
# these yet (Phase 1 of the role-based-dashboard rollout), they exist so
# `active_roles`/`capabilities` are correct on `/auth/me` from day one and new
# endpoints in later phases have something real to check against instead of
# introducing yet another ad-hoc permission scheme per feature.
ROLE_CAPABILITIES: Dict[str, List[str]] = {
    "vendor": ["can_earn", "can_manage_shop"],
    "delivery_partner": ["can_earn"],
    "efiling_agent": ["can_earn"],
    "legal_typist": ["can_earn"],
    "notary": ["can_earn"],
    "stamp_vendor": ["can_earn"],
    "franchise": ["can_earn"],
    "law_firm": ["can_manage_firm", "can_hire_proxy_counsel"],
    "proxy_counsel": ["can_earn", "can_practice_proxy_counsel", "can_hire_proxy_counsel"],
    "advocate": ["can_hire_proxy_counsel"],
    # Bug fix: every plain sign-up (email/password, Google, OTP) used to
    # default straight to "advocate" — a non-lawyer just hiring a proxy
    # counsel or ordering a print job ended up with their account, profile
    # badge, and "I am a..." label literally reading "Advocate". "client" is
    # the correct default for anyone who hasn't gone through an actual
    # professional application (Join as Counsel/Proxy Counsel/Vendor/... —
    # see leads.py's LEAD_ROLE_TO_ACCOUNT_ROLE and _activate_professional).
    # Same capability as "advocate" since that's the one real thing a plain
    # requester needs — nothing here was ever advocate-specific to begin
    # with (bar_council fields etc. are just a frontend Profile.jsx display
    # gate on role=="advocate", never enforced as a capability).
    "client": ["can_hire_proxy_counsel"],
    "admin": ["is_admin"],
}


def _enrich_user_with_roles_and_capabilities(user: dict) -> dict:
    """Merges `active_roles`/`capabilities` into a user doc — computed fresh
    per request from fields already on the doc (no extra query), never
    persisted. `active_roles` is a one-line projection kept only for the
    existing ~30 `user["role"] == ...` / `ProtectedRoute roles={[...]}` checks
    to keep working untouched; new code should check `capabilities` instead."""
    profile_types = user.get("professional_profile_types") or [user.get("role")]
    active_roles = sorted(set(filter(None, [*profile_types, user.get("role")])))
    capabilities = sorted(set(
        cap for role in active_roles for cap in ROLE_CAPABILITIES.get(role, [])
    ))
    return {**user, "active_roles": active_roles, "capabilities": capabilities}


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        # Legacy session-store token (pre-dates the direct Google Identity
        # Services integration below, which now just issues a JWT like every
        # other login path) — kept only so sessions issued before that
        # switch don't get force-logged-out; nothing writes new rows here.
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            exp = sess.get("expires_at")
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                raise HTTPException(401, "Session expired")
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
            if not user:
                raise HTTPException(401, "User not found")
            if user.get("deleted"):
                raise HTTPException(401, "Your account has been deactivated. Please contact the administrator.")
            return _enrich_user_with_roles_and_capabilities(user)
        try:
            payload = decode_jwt(token)
            user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
            if not user:
                raise HTTPException(401, "User not found")
            if user.get("deleted"):
                raise HTTPException(401, "Your account has been deactivated. Please contact the administrator.")
            return _enrich_user_with_roles_and_capabilities(user)
        except jwt.PyJWTError:
            raise HTTPException(401, "Invalid token")
    raise HTTPException(401, "Not authenticated")

# ===== Models =====
# "client" is the generic default for anyone signing up without going
# through a professional application (see ROLE_CAPABILITIES above) — kept
# in this list (not just used as a bare default value) so RegisterRequest's
# `role not in ROLES` check and admin user-listing filters both recognize it.
ROLES = ["client", "advocate", "law_firm", "vendor", "efiling_agent", "legal_typist", "notary", "stamp_vendor", "delivery_partner", "franchise", "admin"]

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    role: str = "client"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class OtpRequest(BaseModel):
    phone: str

class OtpVerify(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None
    role: str = "client"

class SetPasswordRequest(BaseModel):
    token: str
    password: str

class UserProfile(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    bar_council_id: Optional[str] = None
    chamber_address: Optional[str] = None
    chamber_court: Optional[str] = None
    gst_number: Optional[str] = None
    avatar_url: Optional[str] = None

class OrderCreate(BaseModel):
    services: List[Dict[str, Any]]
    state_id: str
    court_id: str
    delivery_option: Literal["pickup", "chamber", "court", "digital"]
    delivery_address: Optional[str] = None
    file_ids: List[str] = []
    urgent: bool = False
    notes: Optional[str] = None
    matter_id: Optional[str] = None  # forward-ready: no Matter UI yet, always null until it ships

class VendorOnboard(BaseModel):
    shop_name: str
    owner_name: str
    phone: str
    address: str
    court_ids: List[str]
    service_ids: List[str]
    vendor_category: str = "photocopy"  # photocopy, typist, efiling_agent, notary, stamp_vendor, stenographer, delivery_partner
    has_gst: bool = False
    pan: Optional[str] = None
    gst: Optional[str] = None
    aadhaar: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bio: Optional[str] = None
    hourly_rate: Optional[float] = None  # For stenographers + court runners

class PricingUpdate(BaseModel):
    service_id: str
    base_price: float
    platform_commission_pct: Optional[float] = None
    convenience_fee: Optional[float] = None
    active: Optional[bool] = None
    visibility: Optional[Dict[str, bool]] = None  # partial — merged per-surface, not replaced (see handler)

class ChatMessage(BaseModel):
    session_id: str
    message: str

class RatingCreate(BaseModel):
    order_id: str
    rating: int
    review: Optional[str] = None

class LeadDraftCreate(BaseModel):
    role_applied_for: str
    form_data: Dict[str, Any] = {}
    current_step: int = 0
    captcha_token: Optional[str] = None  # only checked if CAPTCHA_PROVIDER is configured — see captcha.py

class LeadDraftUpdate(BaseModel):
    draft_token: str
    form_data: Dict[str, Any]
    current_step: Optional[int] = None

class LeadSubmit(BaseModel):
    draft_token: str

class LeadStatusChange(BaseModel):
    status: str
    remark: Optional[str] = None

class LeadNote(BaseModel):
    note: str

class ReviewUpdate(BaseModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    organization: Optional[str] = None
    rating: Optional[int] = None
    review: Optional[str] = None
    featured: Optional[bool] = None
    display_order: Optional[int] = None

class ReviewStatusChange(BaseModel):
    status: str

class ReviewBulkAction(BaseModel):
    review_ids: List[str]
    action: str  # approve | reject | delete | feature | unfeature

class ReviewReorder(BaseModel):
    review_ids: List[str]  # full ordered list; position = display_order

class CalendarEventCreate(BaseModel):
    title: str
    date: str  # ISO date (YYYY-MM-DD)
    kind: str = "meeting"  # meeting | deadline | other

class MatterCreate(BaseModel):
    title: str
    description: Optional[str] = None
    court_id: Optional[str] = None

class MatterUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    court_id: Optional[str] = None
    status: Optional[str] = None

MATTER_STATUSES = ("open", "closed", "archived")

class ProxyCounselProfileUpdate(BaseModel):
    state_bar_council: Optional[str] = None
    bar_council_number: Optional[str] = None
    practice_areas: Optional[List[str]] = None
    courts: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    experience_years: Optional[int] = None
    # Bug fix: these two were editable per practice.PROFILE_EDITABLE_FIELDS
    # and sent by Practice.jsx's save() on every submit, but were missing
    # from this request model — Pydantic silently drops fields it doesn't
    # declare, so every save looked successful (no error, "Profile saved"
    # toast) while experience_bracket/pricing were never actually persisted.
    # The next time the profile loaded fresh (component remount / re-login),
    # those two appeared to have been "cleared".
    experience_bracket: Optional[str] = None
    pricing: Optional[Dict[str, Dict[str, float]]] = None
    # Every field below must stay in lockstep with practice.PROFILE_EDITABLE_FIELDS
    # — see the bug fix above, same silent-drop failure mode.
    professional_status: Optional[str] = None
    max_travel_distance: Optional[str] = None
    schedule_type: Optional[str] = None
    matters_handled: Optional[int] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    office_address: Optional[str] = None
    fee_structure: Optional[str] = None
    availability_mode: Optional[bool] = None
    instant_booking: Optional[bool] = None

class AvailabilitySlotCreate(BaseModel):
    kind: str
    day_of_week: Optional[int] = None  # 0=Monday..6=Sunday, for recurring_weekly
    date: Optional[str] = None  # ISO date, for custom_date/holiday_block/emergency_unavailable
    court_id: Optional[str] = None
    start_time: Optional[str] = None  # "HH:MM"
    end_time: Optional[str] = None

class HearingRequestCreate(BaseModel):
    court_id: str
    hearing_date: str
    case_details: str
    fee: Optional[float] = Field(default=None, gt=0)
    matter_id: Optional[str] = None
    # Integration point for a separate advocate search/select workstream —
    # set -> request is addressed to one advocate; omitted -> today's
    # broadcast-to-all behavior, unchanged. See hearings.py's module docstring.
    target_advocate_id: Optional[str] = None
    # Generic Legal Service Request architecture (frontend LegalServiceRequestForm
    # + config/serviceRequestFields.js) — service_type discriminates which
    # SERVICE_CONFIGS entry built the request; request_details is a free-form,
    # frontend-structured bag ({common: {...}, service_specific: {...}}) the
    # backend stores as-is and never branches on. Additive only — every
    # existing hearing-lifecycle/escrow/payment code path is unaffected.
    service_type: str = "proxy_counsel"
    request_details: Optional[dict] = None

# BlaBlaCar-style flow (founder direction): the case brief is submitted
# separately from creation, once payment is confirmed — see
# hearings.submit_case_details. case_details is the only required field
# (mirrors HearingRequestCreate); everything else is optional so a partial
# save (e.g. correcting just the case title later) doesn't need to resend
# the whole brief.
class HearingCaseDetailsUpdate(BaseModel):
    case_details: str
    case_title: Optional[str] = None
    case_number: Optional[str] = None
    case_type: Optional[str] = None
    case_stage: Optional[str] = None
    hearing_time: Optional[str] = None
    priority: Optional[str] = None
    work_required: Optional[List[str]] = None
    work_required_notes: Optional[str] = None

class HearingDisputeResolve(BaseModel):
    action: str  # "resubmit" | "refund"
    remark: Optional[str] = None

class HearingVerificationReject(BaseModel):
    remark: Optional[str] = None

class AdminAssignCounsel(BaseModel):
    counsel_user_id: str

class HearingNoteCreate(BaseModel):
    note: str

class HearingMessageCreate(BaseModel):
    text: str

class NegotiationOfferCreate(BaseModel):
    amount: float = Field(gt=0)
    note: Optional[str] = None

class HearingRatingCreate(BaseModel):
    rating: int
    review: Optional[str] = None

class WithdrawRequest(BaseModel):
    amount: float
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None

# ===== Startup: seed data =====
@app.on_event("startup")
async def startup():
    if not await ensure_db_ready():
        logger.warning("Continuing without database seeding because MongoDB is not reachable. Start MongoDB to enable full functionality.")
        return
    try:
        await seed_initial_data()
    except Exception as exc:
        logger.warning("Database seeding skipped due to startup error: %s", exc)

async def seed_initial_data():
    if not await ensure_db_ready():
        return
    import leads as leads_svc
    import reviews as reviews_svc
    import hearings as hearings_svc
    import escrow as escrow_svc
    import counsel_matching as counsel_matching_svc
    import negotiation as negotiation_svc
    import notifications as notifications_svc
    await leads_svc.ensure_indexes(db)
    await reviews_svc.ensure_indexes(db)
    await hearings_svc.ensure_indexes(db)
    await escrow_svc.ensure_indexes(db)
    await counsel_matching_svc.ensure_indexes(db)
    await negotiation_svc.ensure_indexes(db)
    await notifications_svc.ensure_indexes(db)
    # Re-seed states/courts from expanded dataset (idempotent: upserts; preserves serviceable flag)
    from court_seed_expanded import COURT_DATA
    from court_seed import SERVICE_CATALOG
    for state in COURT_DATA:
        await db.states.update_one(
            {"state_id": state["state_id"]},
            {"$set": {"state_id": state["state_id"], "name": state["name"], "code": state["code"]}},
            upsert=True,
        )
        for court in state["courts"]:
            court_doc = {**court, "state_id": state["state_id"], "state_name": state["name"]}
            await db.courts.update_one({"court_id": court["court_id"]}, {"$set": court_doc}, upsert=True)
    if await db.services.count_documents({}) == 0 or await db.services.count_documents({"category": "Stenographer Services"}) == 0 \
            or await db.services.count_documents({"visibility": {"$exists": False}}) > 0:
        for svc in SERVICE_CATALOG:
            await db.services.update_one({"service_id": svc["service_id"]}, {"$set": svc}, upsert=True)
        # Unified 20% commission for all services
        await db.services.update_many({}, {"$set": {"platform_commission_pct": 0.20}})
        logger.info("Seeded/updated services (unified 20% commission)")
    # No demo/admin accounts are seeded here by design — production must never boot with
    # known hardcoded credentials. Use scripts/create_admin.py once, on a real deployment,
    # to bootstrap the first admin account interactively.

# ===== Routes =====
@api_router.get("/")
async def root():
    return {"message": "CourtBazaar API - India's Legal Marketplace", "version": "1.0"}

# Unauthenticated, deliberately tiny — just enough for the frontend to know
# whether to render the "Continue with Google" button on Login/Register at
# all, rather than showing it in every environment and having it fail with a
# 501 wherever GOOGLE_OAUTH_ENABLED isn't set (e.g. local dev).
@api_router.get("/config/public")
async def public_config():
    return {
        "google_oauth_enabled": GOOGLE_OAUTH_ENABLED,
        "google_client_id": GOOGLE_CLIENT_ID if GOOGLE_OAUTH_ENABLED else None,
    }

# ---------- AUTH ----------
# Roles that must never be created by any self-service signup path
# (/auth/register, /auth/otp/verify) — checked centrally here rather than
# per-endpoint so a future signup path can't reintroduce this gap by
# forgetting the check.
#   - "vendor": goes through the admin-vetted Leads pipeline instead
#     (leads.py's "Join as..." forms), which KYC-reviews the applicant
#     before an account (and its login credentials) ever exists.
#     partner/agent/counsel/proxy_counsel were never reachable from these
#     endpoints' role vocabulary to begin with, so only "vendor" needs an
#     explicit block — it's a real ROLES value also used post-registration
#     (vendor_onboard, etc.), so it can't just be absent from ROLES.
#   - "admin": must only ever be created by scripts/create_admin.py (run
#     manually, once, directly against the database) — self-service signup
#     must never be able to mint an admin account, at all, for any role
#     string a client sends.
SELF_REGISTER_BLOCKED_ROLES = {
    "vendor": (
        "Vendor accounts are created only after our team reviews your application. "
        "Please apply via the vendor application form on the homepage — you'll receive "
        "login details by email once approved."
    ),
    "admin": "Admin accounts cannot be created through sign-up. Contact an existing administrator.",
}

def _reject_self_register_blocked_role(role: str) -> None:
    if role in SELF_REGISTER_BLOCKED_ROLES:
        raise HTTPException(400, SELF_REGISTER_BLOCKED_ROLES[role])

@api_router.post("/auth/register")
async def register(req: RegisterRequest):
    if req.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    _reject_self_register_blocked_role(req.role)
    existing = await db.users.find_one({"email": req.email})
    # A deactivated account (admin "Delete User", i.e. audit_log.deactivate_user)
    # is a soft delete — it sets `deleted: True` and wipes password_hash, but
    # deliberately keeps the email on the record (see that function's
    # docstring). Without this check, that email is permanently stuck: this
    # endpoint always refuses it as "already registered", and login always
    # fails since there's no password to check against — with no way back in
    # short of an admin manually editing the database. Reusing the same
    # user_id (rather than minting a second row for the same email) means the
    # account genuinely starts fresh while any existing orders/audit history
    # for that user_id still attribute correctly.
    if existing and not existing.get("deleted"):
        raise HTTPException(400, "Email already registered")
    user_id = existing["user_id"] if existing else f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": req.email,
        "name": req.name,
        "phone": req.phone,
        "role": req.role,
        "password_hash": hash_password(req.password),
        "verified": False,
        "wallet_balance": 0.0,
        "subscription": "free",
        # Which typed professional-profile collections this account has a row in
        # (vendors, proxy_counsel_profiles, ...) — seeded with the base role so no
        # history is lost even where `role` itself later gets overwritten by
        # vendor/firm onboarding (see server.py:583,1431). Source of truth for
        # active_roles/capabilities computed in get_current_user(), not `role` alone.
        "professional_profile_types": [req.role],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        # replace_one with no "_id" in the replacement keeps Mongo's original
        # _id automatically — this is a genuine reset of the row, not a patch,
        # so every deactivation-era field (deleted, deleted_at, deactivated_by,
        # set_password_token_hash, ...) is dropped rather than lingering.
        await db.users.replace_one({"user_id": user_id}, user_doc)
    else:
        await db.users.insert_one(user_doc)
    token = make_jwt(user_id, req.role)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    return {"token": token, "user": _enrich_user_with_roles_and_capabilities(user_doc)}

@api_router.post("/auth/login")
async def login(req: LoginRequest, request: Request):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    # Checked ahead of the password comparison (not folded into the generic
    # "Invalid credentials" branch below): a deactivated account's
    # password_hash is cleared (see audit_log.deactivate_user), so the
    # comparison would always fail anyway — but a deactivated user deserves
    # the actual reason, not a misleading "wrong password".
    if user and user.get("deleted"):
        raise HTTPException(401, "Your account has been deactivated. Please contact the administrator.")
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")
    token = make_jwt(user["user_id"], user["role"])
    user.pop("password_hash", None)
    try:
        from audit_log import log_audit
        await log_audit(db, "auth.login", user, {}, request)
    except Exception:
        pass
    return {"token": token, "user": _enrich_user_with_roles_and_capabilities(user)}

OTP_TTL_SECONDS = 300
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5

@api_router.post("/auth/otp/request")
async def otp_request(req: OtpRequest):
    now = datetime.now(timezone.utc)
    recent = await db.otp_codes.find_one(
        {"phone": req.phone}, sort=[("created_at", -1)]
    )
    if recent:
        created_at = datetime.fromisoformat(recent["created_at"])
        if (now - created_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
            raise HTTPException(429, "Please wait before requesting another OTP")
    code = f"{secrets.randbelow(900000) + 100000}"
    await db.otp_codes.delete_many({"phone": req.phone, "used": False})
    await db.otp_codes.insert_one({
        "phone": req.phone,
        "otp_hash": hash_password(code),
        "expires_at": (now + timedelta(seconds=OTP_TTL_SECONDS)).isoformat(),
        "attempts": 0,
        "used": False,
        "created_at": now.isoformat(),
    })
    from notifications import notify
    existing = await db.users.find_one(
        {"$or": [{"phone": req.phone}, {"alt_phones": req.phone}]}, {"_id": 0, "email": 1}
    )
    notify(
        {"phone": req.phone, "email": existing.get("email") if existing else None,
         "notif_prefs": {"sms": True, "whatsapp": True, "email": True}},
        "otp", {"otp": code},
    )
    return {"ok": True, "message": "OTP sent", "phone": req.phone}

@api_router.post("/auth/otp/verify")
async def otp_verify(req: OtpVerify):
    rec = await db.otp_codes.find_one({"phone": req.phone, "used": False}, sort=[("created_at", -1)])
    if not rec:
        raise HTTPException(400, "Invalid or expired OTP")
    if rec["attempts"] >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Request a new OTP.")
    expires_at = datetime.fromisoformat(rec["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(400, "OTP has expired")
    if not verify_password(req.otp, rec["otp_hash"]):
        await db.otp_codes.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Invalid OTP")
    await db.otp_codes.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    user = await db.users.find_one(
        {"$or": [{"phone": req.phone}, {"alt_phones": req.phone}]}, {"_id": 0}
    )
    # Same guard login() already applies — without it, a deactivated account
    # (password_hash cleared, `deleted: True`) could still get back in
    # through phone OTP, silently bypassing the deactivation entirely.
    if user and user.get("deleted"):
        raise HTTPException(401, "Your account has been deactivated. Please contact the administrator.")
    if not user:
        if req.role not in ROLES:
            raise HTTPException(400, "Invalid role")
        _reject_self_register_blocked_role(req.role)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": f"{req.phone}@phone.courtbazaar.com",
            "name": req.name or f"User {req.phone[-4:]}",
            "phone": req.phone,
            "role": req.role,
            "verified": True,
            "wallet_balance": 0.0,
            "subscription": "free",
            "professional_profile_types": [req.role],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    token = make_jwt(user["user_id"], user["role"])
    user.pop("password_hash", None)
    user.pop("_id", None)
    return {"token": token, "user": _enrich_user_with_roles_and_capabilities(user)}

def _frontend_base_url() -> str:
    """Same convention leads.py's set-password emails use — first configured
    CORS origin, falling back to the production domain."""
    return (os.environ.get("CORS_ORIGINS", "").split(",")[0] or "").strip() or "https://courtbazaar.com"


@api_router.post("/auth/google/callback")
async def google_callback(
    request: Request,
    credential: str = Form(...),
    g_csrf_token: Optional[str] = Form(None),
    role: str = "client",
):
    """Google Identity Services posts the credential straight here as a real
    top-level browser navigation (ux_mode: 'redirect' in GoogleAuthButton.jsx)
    rather than via window.open — GIS's default popup mode turned out to get
    silently blocked by Chrome's popup blocker on a real click (confirmed via
    its own console error, "Failed to open popup window ... Maybe blocked by
    the browser"), which is a known reliability issue with that mode. Redirect
    mode has no popup to block: straight client-to-Google-to-us, still no
    third-party broker, so the only branding a user ever sees on Google's own
    consent screen is this Client ID's own OAuth consent screen.

    `role` rides along as a query param on login_uri itself (GIS preserves it
    verbatim since it's just part of the URL it POSTs to) — the only way to
    thread Register.jsx's role picker through a flow that's now a real page
    navigation instead of a JS callback.

    CSRF: GIS also sets a same-site `g_csrf_token` cookie on the page that
    rendered the button and repeats it as a form field here — checked below
    when both are present. It's only present when login_uri shares an exact
    domain with the frontend (true in production, where /api is reverse-
    proxied under the same domain — see nginx.conf); in local dev, frontend
    and backend are different origins/ports so the cookie never arrives, and
    the check is skipped rather than hard-failing dev. Either way, credential
    forgery itself is already ruled out by verify_oauth2_token below — this
    is defense-in-depth against a real page tricking a signed-in browser into
    replaying someone else's credential, not the primary trust boundary."""
    frontend_base = _frontend_base_url()
    if not GOOGLE_OAUTH_ENABLED:
        return RedirectResponse(f"{frontend_base}/login?error=google_auth_unavailable", status_code=302)
    cookie_csrf = request.cookies.get("g_csrf_token")
    if cookie_csrf and g_csrf_token and cookie_csrf != g_csrf_token:
        return RedirectResponse(f"{frontend_base}/login?error=google_auth_failed", status_code=302)
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_auth_requests
        idinfo = google_id_token.verify_oauth2_token(credential, google_auth_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo["email"]
    except Exception:
        return RedirectResponse(f"{frontend_base}/login?error=google_auth_failed", status_code=302)
    name = idinfo.get("name")
    picture = idinfo.get("picture")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name or existing["name"], "avatar_url": picture}},
        )
        account_role = existing["role"]
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        # Security fix: `role` is a bare query param on a public redirect
        # URL — unlike /auth/register's `req.role not in ROLES` 400 and
        # _reject_self_register_blocked_role guard, this path never
        # validated it at all, so anyone could complete a real Google
        # sign-in against ?role=admin (or "vendor", already gated behind
        # admin-only lead approval everywhere else) and mint themselves
        # that account type outright on first login. Same validation as
        # self-register, just falling back to "client" instead of a JSON
        # 400 — this is a redirect flow with no request body to reject.
        account_role = role if role in ROLES and role not in SELF_REGISTER_BLOCKED_ROLES else "client"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name or email.split("@")[0],
            "avatar_url": picture,
            "role": account_role,
            "verified": True,
            "wallet_balance": 0.0,
            "subscription": "free",
            "professional_profile_types": [account_role],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    token = make_jwt(user_id, account_role)
    # Fragment, not a query param — never sent to any server on the follow-up
    # navigation (the browser strips it before the request line), so the JWT
    # never lands in this redirect's own access logs or Referer headers.
    return RedirectResponse(f"{frontend_base}/auth/google/complete#token={token}", status_code=302)

@api_router.post("/auth/set-password")
async def set_password(req: SetPasswordRequest):
    """One-time link, emailed by leads.py's Lead->Professional bridge when an
    approved proxy_counsel/counsel lead creates a brand-new account (no
    existing account matched by email). Mirrors leads.py's own
    email_verify_token pattern — hashed token, expiring, single-use."""
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    user = await db.users.find_one({"set_password_token_hash": token_hash})
    if not user:
        raise HTTPException(400, "Invalid or expired link")
    expires_at = user.get("set_password_token_expires_at")
    if expires_at and datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
        raise HTTPException(400, "This link has expired")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(req.password)},
         "$unset": {"set_password_token_hash": "", "set_password_token_expires_at": ""}},
    )
    token = make_jwt(user["user_id"], user["role"])
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"token": token, "user": _enrich_user_with_roles_and_capabilities(fresh)}

@api_router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    user.pop("password_hash", None)
    return user

@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}

@api_router.put("/auth/profile")
async def update_profile(profile: UserProfile, user=Depends(get_current_user)):
    update = {k: v for k, v in profile.model_dump().items() if v is not None}
    if update:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    refreshed = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return refreshed

# ---------- COURTS ----------
@api_router.get("/states")
async def list_states():
    states = await db.states.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    return states

@api_router.get("/courts")
async def list_courts(state_id: Optional[str] = None, q: Optional[str] = None, serviceable_only: bool = False, has_coordinates: bool = False):
    query: Dict[str, Any] = {}
    if state_id:
        query["state_id"] = state_id
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    if serviceable_only:
        query["serviceable"] = True
    if has_coordinates:
        query["latitude"] = {"$ne": None}
        query["longitude"] = {"$ne": None}
    courts = await db.courts.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    return courts

@api_router.get("/courts/{court_id}")
async def get_court(court_id: str):
    court = await db.courts.find_one({"court_id": court_id}, {"_id": 0})
    if not court:
        raise HTTPException(404, "Court not found")
    vendor_count = await db.vendors.count_documents({"court_ids": court_id, "kyc_status": "approved"})
    return {**court, "vendor_count": vendor_count}

# ---------- SERVICES ----------
# One backend-driven catalog feeds every surface (Marketplace, Landing,
# MegaMenu, Dashboard quick-tiles, Pricing) — each surface just asks for its
# own visibility flag instead of maintaining its own hardcoded list. See
# court_seed.py's `_apply_service_visibility` for what seeds each flag.
@api_router.get("/services")
async def list_services(category: Optional[str] = None, include_hidden: bool = False):
    query: Dict[str, Any] = {"active": {"$ne": False}}
    if not include_hidden:
        query["visibility.marketplace"] = {"$ne": False}
    if category:
        query["category"] = category
    services = await db.services.find(query, {"_id": 0}).to_list(500)
    return services

@api_router.get("/services/categories")
async def service_categories(include_hidden: bool = False):
    match: Dict[str, Any] = {"active": {"$ne": False}}
    if not include_hidden:
        match["visibility.marketplace"] = {"$ne": False}
    pipeline = [{"$match": match}, {"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    cats = []
    async for doc in db.services.aggregate(pipeline):
        if doc["_id"]:
            cats.append({"category": doc["_id"], "count": doc["count"]})
    return cats

@api_router.get("/services/public")
async def list_public_services(surface: str):
    """No-auth read path for marketing/quick-access surfaces (Landing,
    MegaMenu, Dashboard quick-tiles, Pricing) — replaces what used to be a
    separate hardcoded array per surface. `surface` is a visibility key
    (landing|marketplace|sidebar), not a page name."""
    if surface not in ("landing", "marketplace", "sidebar"):
        raise HTTPException(400, "Invalid surface")
    query = {"active": {"$ne": False}, f"visibility.{surface}": {"$ne": False}}
    services = await db.services.find(query, {"_id": 0}).sort("display_order", 1).to_list(500)
    return services

@api_router.get("/services/{service_id}")
async def get_service(service_id: str):
    # Deliberately unfiltered by visibility — a deep link (e.g. /order/new?service=X
    # from an existing order, or a Dashboard quick-tile) must keep resolving
    # even when the service isn't on a discovery surface; visibility gates
    # *listing*, not direct access.
    svc = await db.services.find_one({"service_id": service_id}, {"_id": 0})
    if not svc:
        raise HTTPException(404, "Service not found")
    return svc

# ---------- VENDORS ----------
@api_router.post("/vendors/onboard")
async def vendor_onboard(payload: VendorOnboard, user=Depends(get_current_user)):
    existing = await db.vendors.find_one({"user_id": user["user_id"]})
    doc = {
        "vendor_id": existing["vendor_id"] if existing else user["user_id"],
        "user_id": user["user_id"],
        **payload.model_dump(),
        "rating": existing.get("rating", 0) if existing else 0,
        "total_orders": existing.get("total_orders", 0) if existing else 0,
        "kyc_status": "pending",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.vendors.update_one({"user_id": user["user_id"]}, {"$set": doc})
    else:
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.vendors.insert_one(doc)
    # $addToSet (not just $set role) so onboarding as a vendor doesn't erase
    # whatever professional profile types this account already had — `role`
    # itself is still overwritten for backward compat with existing
    # `user["role"] == "vendor"` checks scattered across this file; fully
    # retiring that overwrite is a followup once those checks read
    # active_roles/capabilities instead (see get_current_user).
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"role": "vendor"}, "$addToSet": {"professional_profile_types": "vendor"}},
    )
    doc.pop("_id", None)
    return doc

@api_router.get("/vendors")
async def list_vendors(court_id: Optional[str] = None, service_id: Optional[str] = None):
    query: Dict[str, Any] = {"kyc_status": "approved"}
    if court_id:
        query["court_ids"] = court_id
    if service_id:
        query["service_ids"] = service_id
    vendors = await db.vendors.find(query, {"_id": 0}).sort("rating", -1).to_list(200)
    return vendors

@api_router.get("/vendors/me")
async def my_vendor(user=Depends(get_current_user)):
    v = await db.vendors.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not v:
        return {"onboarded": False}
    return {"onboarded": True, **v}

@api_router.put("/vendors/{vendor_id}/approve")
async def approve_vendor(vendor_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    await db.vendors.update_one({"vendor_id": vendor_id}, {"$set": {"kyc_status": "approved"}})
    return {"ok": True}

# ---------- FILES ----------
@api_router.post("/files/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    validate_upload(file.filename, content_type, len(data))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/uploads/{user['user_id']}/{file_id}.{ext}"
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {e}")

    # Auto-detect page count
    page_count = 1
    try:
        fn = (file.filename or "").lower()
        ct = (content_type or "").lower()
        if "pdf" in ct or fn.endswith(".pdf"):
            import io as _io
            page_count = 0
            # 1) Try PyPDF2 (works for normal PDFs with structure intact)
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(_io.BytesIO(data))
                page_count = len(reader.pages)
            except Exception as e:
                logger.warning(f"PyPDF2 page count failed: {e}")
            # 2) Fallback to pdfinfo / pdf2image for scanned or malformed PDFs
            if page_count == 0:
                try:
                    from pdf2image.pdf2image import pdfinfo_from_bytes
                    info = pdfinfo_from_bytes(data, userpw=None)
                    page_count = int(info.get("Pages", 0))
                except Exception as e:
                    logger.warning(f"pdfinfo fallback failed: {e}")
            # 3) Last-resort: count "/Type /Page" markers in raw bytes
            if page_count == 0:
                try:
                    page_count = max(1, data.count(b"/Type /Page") - data.count(b"/Type /Pages"))
                except Exception:
                    page_count = 1
            page_count = max(1, page_count)
        elif "tiff" in ct or fn.endswith((".tif", ".tiff")):
            # Multi-page TIFF support
            try:
                from PIL import Image
                import io as _io
                img = Image.open(_io.BytesIO(data))
                page_count = getattr(img, "n_frames", 1) or 1
            except Exception:
                page_count = 1
        elif "image" in ct or any(fn.endswith(e) for e in [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"]):
            page_count = 1
        elif "officedocument" in ct or fn.endswith((".docx", ".doc")):
            try:
                from docx import Document
                import io as _io
                doc = Document(_io.BytesIO(data))
                total_chars = sum(len(p.text) for p in doc.paragraphs)
                page_count = max(1, total_chars // 3000)
            except Exception:
                page_count = max(1, len(data) // 50000)
    except Exception as e:
        logger.error(f"Page count detection failed: {e}")
        page_count = 1

    record = {
        "file_id": file_id,
        "user_id": user["user_id"],
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "page_count": page_count,
        "is_deleted": False,
        "matter_id": None,  # forward-ready: no Matter UI yet, always null until it ships
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.files.insert_one(record)
    record.pop("_id", None)
    return record

@api_router.get("/files/{file_id}/download")
async def download_file(file_id: str, user=Depends(get_current_user)):
    rec = await db.files.find_one({"file_id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "File not found")
    is_owner = rec["user_id"] == user["user_id"]
    is_admin = user["role"] == "admin"
    is_assigned_vendor = False
    if not is_owner and not is_admin and user["role"] == "vendor":
        is_assigned_vendor = await db.orders.find_one({"vendor_id": user["user_id"], "file_ids": file_id}) is not None
    if not (is_owner or is_admin or is_assigned_vendor):
        raise HTTPException(403, "Forbidden")
    url = presigned_download_url(rec["storage_path"], filename=rec.get("original_filename"))
    return {"url": url, "filename": rec.get("original_filename")}

@api_router.get("/files/mine")
async def my_files(user=Depends(get_current_user)):
    files = await db.files.find({"user_id": user["user_id"], "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return files

# ---------- LEADS (public: landing-page "Join as..." applications) ----------
import leads as leads_svc
from fastapi.responses import HTMLResponse
from captcha import verify_captcha

# request.client.host is the real visitor IP, not nginx's, only because
# uvicorn is launched with --proxy-headers (deploy/courtbazaar.service) and
# trusts nginx's loopback connection to rewrite it from X-Forwarded-For
# (see FORWARDED_ALLOW_IPS in .env.example). Without that flag this would
# silently be "127.0.0.1" for every request.
@api_router.post("/leads/draft")
async def leads_create_draft(payload: LeadDraftCreate, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    verify_captcha(payload.captcha_token, client_ip)
    leads_svc.check_draft_rate_limit(client_ip)
    return await leads_svc.create_draft(db, payload.role_applied_for, payload.form_data, payload.current_step, client_ip=client_ip)

@api_router.put("/leads/{lead_id}/draft")
async def leads_update_draft(lead_id: str, payload: LeadDraftUpdate):
    return await leads_svc.update_draft(db, lead_id, payload.draft_token, payload.form_data, payload.current_step)

@api_router.post("/leads/{lead_id}/documents")
async def leads_add_document(
    lead_id: str,
    draft_token: str = Form(...),
    field_key: str = Form(...),
    file: UploadFile = File(...),
):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    return await leads_svc.add_document(
        db, put_object, validate_upload, lead_id, draft_token, field_key, file.filename, content_type, data,
    )

@api_router.delete("/leads/{lead_id}/documents/{doc_id}")
async def leads_remove_document(lead_id: str, doc_id: str, draft_token: str = Query(...)):
    return await leads_svc.remove_document(db, delete_object, lead_id, draft_token, doc_id)

@api_router.post("/leads/{lead_id}/submit")
async def leads_submit(lead_id: str, payload: LeadSubmit, request: Request):
    from notifications import send_email
    verify_base_url = f"{str(request.base_url).rstrip('/')}/api/leads/verify-email"
    return await leads_svc.submit_lead(db, send_email, verify_base_url, lead_id, payload.draft_token)

@api_router.get("/leads/verify-email")
async def leads_verify_email(token: str):
    try:
        await leads_svc.verify_email(db, token)
        body = "<h2>Email verified</h2><p>Thanks — your email address has been confirmed. You can close this tab.</p>"
    except HTTPException as e:
        body = f"<h2>Verification failed</h2><p>{e.detail}</p>"
    return HTMLResponse(f"<html><body style='font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;'>{body}</body></html>")

# ---------- ADMIN: LEADS ----------
@api_router.get("/admin/leads/stats")
async def admin_leads_stats(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await leads_svc.lead_stats(db)

@api_router.get("/admin/leads")
async def admin_leads_list(
    user=Depends(get_current_user),
    status: Optional[str] = None,
    role: Optional[str] = None,
    q: Optional[str] = None,
):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await leads_svc.list_leads(db, status, role, q)

@api_router.get("/admin/leads/{lead_id}")
async def admin_leads_detail(lead_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await leads_svc.get_lead_detail(db, lead_id)

@api_router.put("/admin/leads/{lead_id}/status")
async def admin_leads_status(lead_id: str, payload: LeadStatusChange, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from notifications import send_email
    return await leads_svc.admin_change_status(db, send_email, lead_id, payload.status, payload.remark, user)

@api_router.post("/admin/leads/{lead_id}/resend-welcome-email")
async def admin_leads_resend_welcome_email(lead_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from notifications import send_email
    return await leads_svc.resend_set_password_email(db, send_email, lead_id)

@api_router.post("/admin/leads/{lead_id}/notes")
async def admin_leads_add_note(lead_id: str, payload: LeadNote, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await leads_svc.add_note(db, lead_id, payload.note, user)

@api_router.delete("/admin/leads/{lead_id}")
async def admin_leads_delete(lead_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await leads_svc.delete_lead(db, delete_object, lead_id, user)

@api_router.get("/admin/leads/{lead_id}/documents/{doc_id}/download-url")
async def admin_leads_document_url(lead_id: str, doc_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    rec = await db.lead_documents.find_one({"doc_id": doc_id, "lead_id": lead_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Document not found")
    url = presigned_download_url(rec["storage_path"], filename=rec.get("original_filename"))
    return {"url": url, "filename": rec.get("original_filename")}

# ---------- REVIEWS (public: landing-page "Write a Review") ----------
import reviews as reviews_svc

REVIEW_PHOTO_URL_TTL_SECONDS = 24 * 60 * 60  # public listing is fetched live on each page load, so a
                                              # day-long signed URL comfortably outlives one visit/cache cycle

def _review_photo_url(storage_path: str) -> str:
    return presigned_download_url(storage_path, expires_in=REVIEW_PHOTO_URL_TTL_SECONDS)

@api_router.post("/reviews")
async def reviews_create(
    request: Request,
    name: str = Form(...),
    rating: int = Form(...),
    review: str = Form(...),
    designation: Optional[str] = Form(None),
    organization: Optional[str] = Form(None),
    captcha_token: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
):
    # See the comment on leads_create_draft above re: --proxy-headers.
    client_ip = request.client.host if request.client else "unknown"
    verify_captcha(captcha_token, client_ip)
    reviews_svc.check_review_rate_limit(client_ip)
    photo_file = None
    if photo is not None and photo.filename:
        data = await photo.read()
        photo_file = {"filename": photo.filename, "content_type": photo.content_type or "application/octet-stream", "data": data}
    result = await reviews_svc.create_review(
        db, put_object, validate_image_upload, name, designation, organization, rating, review, photo_file, client_ip,
    )
    return {**result, "message": "Thank you. Your review has been submitted for approval."}

@api_router.get("/reviews")
async def reviews_list_public():
    return await reviews_svc.list_public_reviews(db, _review_photo_url)

# ---------- ADMIN: REVIEWS ----------
@api_router.get("/admin/reviews/stats")
async def admin_reviews_stats(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.review_stats(db)

@api_router.get("/admin/reviews")
async def admin_reviews_list(user=Depends(get_current_user), status: Optional[str] = None, q: Optional[str] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_list_reviews(db, status, q)

@api_router.get("/admin/reviews/{review_id}")
async def admin_reviews_detail(review_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_get_review(db, review_id)

@api_router.put("/admin/reviews/{review_id}")
async def admin_reviews_update(review_id: str, payload: ReviewUpdate, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_update_review(db, review_id, payload.model_dump(exclude_unset=True))

@api_router.put("/admin/reviews/{review_id}/status")
async def admin_reviews_status(review_id: str, payload: ReviewStatusChange, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_change_status(db, review_id, payload.status, user)

@api_router.delete("/admin/reviews/{review_id}")
async def admin_reviews_delete(review_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_delete_review(db, review_id, delete_object, user)

@api_router.post("/admin/reviews/bulk")
async def admin_reviews_bulk(payload: ReviewBulkAction, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_bulk_action(db, payload.review_ids, payload.action, delete_object, user)

@api_router.post("/admin/reviews/reorder")
async def admin_reviews_reorder(payload: ReviewReorder, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return await reviews_svc.admin_reorder(db, payload.review_ids)

# ---------- ORDERS ----------
ORDER_STATUSES = ["placed", "matched", "accepted", "processing", "quality_check", "ready", "out_for_delivery", "delivered", "completed", "cancelled"]

# Unified platform economics (applies to ALL vendor categories)
PLATFORM_COMMISSION_PCT = 0.20      # Platform retains 20% of vendor's service earnings
DELIVERY_SHARE_VENDOR_PCT = 0.50    # 50% of delivery fee goes to vendor
CONVENIENCE_FEE_FLAT = 10.0          # Pure platform revenue
GST_PCT = 0.18

async def calculate_pricing(services: List[Dict], court_id: str, delivery: str, urgent: bool):
    subtotal = 0.0
    vendor_service_share = 0.0
    breakdown = []
    for item in services:
        svc = await db.services.find_one({"service_id": item["service_id"]}, {"_id": 0})
        if not svc:
            continue
        qty = item.get("qty", 1)
        unit = float(svc.get("base_price", 0))
        # For hourly services (stenographer), qty represents hours
        line = unit * qty
        subtotal += line
        breakdown.append({"service_id": svc["service_id"], "name": svc["name"], "unit_price": unit, "qty": qty, "line_total": line, "unit": svc.get("unit", "per item")})
    # Unified 20% commission for ALL services
    vendor_service_share = subtotal * (1 - PLATFORM_COMMISSION_PCT)
    platform_service_commission = subtotal * PLATFORM_COMMISSION_PCT

    delivery_fee = {"pickup": 0, "chamber": 79, "court": 49, "digital": 0}.get(delivery, 0)
    # 50/50 delivery split
    vendor_delivery_share = delivery_fee * DELIVERY_SHARE_VENDOR_PCT
    platform_delivery_share = delivery_fee * (1 - DELIVERY_SHARE_VENDOR_PCT)

    urgent_fee = round(subtotal * 0.25, 2) if urgent else 0
    # Urgent surcharge: vendor takes 80%, platform 20% (consistent with service split)
    vendor_urgent_share = urgent_fee * (1 - PLATFORM_COMMISSION_PCT)
    platform_urgent_share = urgent_fee * PLATFORM_COMMISSION_PCT

    convenience = CONVENIENCE_FEE_FLAT  # Pure platform revenue
    gst = round((subtotal + delivery_fee + urgent_fee + convenience) * GST_PCT, 2)
    total = round(subtotal + delivery_fee + urgent_fee + convenience + gst, 2)

    vendor_payout = round(vendor_service_share + vendor_delivery_share + vendor_urgent_share, 2)
    platform_revenue = round(platform_service_commission + platform_delivery_share + platform_urgent_share + convenience, 2)

    return {
        "breakdown": breakdown,
        "subtotal": round(subtotal, 2),
        "delivery_fee": delivery_fee,
        "urgent_fee": urgent_fee,
        "convenience_fee": convenience,
        "gst": gst,
        "total": total,
        # Revenue split (excl. GST which is government's)
        "vendor_payout": vendor_payout,
        "platform_revenue": platform_revenue,
        "platform_commission": round(platform_service_commission, 2),  # Backward-compat alias
        "split_details": {
            "service_subtotal": round(subtotal, 2),
            "vendor_service_share_80pct": round(vendor_service_share, 2),
            "platform_commission_20pct": round(platform_service_commission, 2),
            "delivery_fee": delivery_fee,
            "vendor_delivery_share_50pct": round(vendor_delivery_share, 2),
            "platform_delivery_share_50pct": round(platform_delivery_share, 2),
            "convenience_fee_platform": convenience,
            "urgent_fee": urgent_fee,
            "vendor_urgent_share_80pct": round(vendor_urgent_share, 2),
            "platform_urgent_share_20pct": round(platform_urgent_share, 2),
        },
    }

@api_router.post("/orders/quote")
async def order_quote(req: OrderCreate, user=Depends(get_current_user)):
    return await calculate_pricing(req.services, req.court_id, req.delivery_option, req.urgent)

@api_router.post("/orders")
async def create_order(req: OrderCreate, user=Depends(get_current_user)):
    court_info = await db.courts.find_one({"court_id": req.court_id}, {"_id": 0})
    if not court_info:
        raise HTTPException(404, "Court not found")
    if court_info.get("serviceable") is False:
        raise HTTPException(400, "This court is not yet serviceable. Currently we operate in Delhi only.")
    pricing = await calculate_pricing(req.services, req.court_id, req.delivery_option, req.urgent)
    # Auto-match: sponsored vendors first (sponsored=True), then by rating
    candidates = await db.vendors.find(
        {"court_ids": req.court_id, "kyc_status": "approved"}, {"_id": 0},
    ).to_list(20)
    candidates.sort(key=lambda v: (not v.get("sponsored", False), -float(v.get("rating", 0))))
    vendor = candidates[0] if candidates else None
    order_id = f"ORD{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    order = {
        "order_id": order_id,
        "user_id": user["user_id"],
        "user_name": user.get("name"),
        "user_phone": user.get("phone"),
        "firm_id": user.get("firm_id"),
        "services": req.services,
        "state_id": req.state_id,
        "court_id": req.court_id,
        "court_name": court_info["name"],
        "state_name": court_info.get("state_name"),
        "delivery_option": req.delivery_option,
        "delivery_address": req.delivery_address,
        "file_ids": req.file_ids,
        "urgent": req.urgent,
        "notes": req.notes,
        "matter_id": req.matter_id,
        "pricing": pricing,
        "vendor_id": vendor["vendor_id"] if vendor else None,
        "vendor_name": vendor["shop_name"] if vendor else None,
        "vendor_sponsored": vendor.get("sponsored", False) if vendor else False,
        "status": "placed",
        "payment_status": "pending",
        "timeline": [{"status": "placed", "at": datetime.now(timezone.utc).isoformat(), "note": "Order placed"}],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.insert_one(order)
    order.pop("_id", None)
    # Notify
    try:
        from notifications import notify, record_notification_event
        notify(user, "order_placed", {"order": order})
        await record_notification_event(db, user["user_id"], "order_placed",
                                         "Order placed", f"Order {order_id} has been placed.",
                                         "order", order_id)
    except Exception as e:
        logger.error(f"notify error: {e}")
    try:
        from audit_log import log_audit
        await log_audit(db, "order.create", user, {"order_id": order_id, "total": pricing["total"], "court_id": req.court_id})
    except Exception:
        pass
    return order

@api_router.get("/orders")
async def list_orders(user=Depends(get_current_user), status: Optional[str] = None):
    query: Dict[str, Any] = {}
    if user["role"] in ("advocate", "law_firm"):
        query["user_id"] = user["user_id"]
    elif user["role"] == "vendor":
        query["vendor_id"] = user["user_id"]
    elif user["role"] != "admin":
        query["user_id"] = user["user_id"]
    if status:
        query["status"] = status
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if user["role"] not in ("admin",) and order["user_id"] != user["user_id"] and order.get("vendor_id") != user["user_id"]:
        raise HTTPException(403, "Forbidden")
    return order

@api_router.post("/orders/{order_id}/status")
async def update_order_status(order_id: str, payload: dict, user=Depends(get_current_user)):
    new_status = payload.get("status")
    if new_status not in ORDER_STATUSES:
        raise HTTPException(400, "Invalid status")
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    if user["role"] not in ("admin", "vendor") and order.get("vendor_id") != user["user_id"]:
        raise HTTPException(403, "Forbidden")
    timeline_entry = {"status": new_status, "at": datetime.now(timezone.utc).isoformat(), "note": payload.get("note", "")}
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": new_status}, "$push": {"timeline": timeline_entry}},
    )
    # DPDP auto-purge: delete attached files when order is completed
    if new_status == "completed":
        try:
            purge = await delete_order_files(order_id)
            await db.orders.update_one({"order_id": order_id}, {"$set": {"files_purged": purge}})
            from audit_log import log_audit
            await log_audit(db, "file.auto_delete", user, {"order_id": order_id, **purge})
        except Exception as e:
            logger.error(f"auto purge files error: {e}")
    # Notify customer
    try:
        customer = await db.users.find_one({"user_id": order["user_id"]}, {"_id": 0})
        if customer:
            from notifications import notify, record_notification_event
            notify(customer, "order_status", {"order": {**order, "status": new_status}, "status": new_status})
            await record_notification_event(db, customer["user_id"], "order_status",
                                             f"Order {new_status.replace('_', ' ')}",
                                             f"Order {order_id} is now {new_status.replace('_', ' ')}.",
                                             "order", order_id)
    except Exception as e:
        logger.error(f"notify status error: {e}")
    return {"ok": True, "status": new_status}

@api_router.post("/orders/{order_id}/rate")
async def rate_order(order_id: str, payload: RatingCreate, user=Depends(get_current_user)):
    order = await db.orders.find_one({"order_id": order_id})
    if not order or order["user_id"] != user["user_id"]:
        raise HTTPException(403, "Forbidden")
    await db.orders.update_one({"order_id": order_id}, {"$set": {"rating": payload.rating, "review": payload.review}})
    if order.get("vendor_id"):
        cursor = db.orders.find({"vendor_id": order["vendor_id"], "rating": {"$exists": True}}, {"rating": 1})
        ratings = [d["rating"] async for d in cursor]
        if ratings:
            avg = sum(ratings) / len(ratings)
            await db.vendors.update_one({"vendor_id": order["vendor_id"]}, {"$set": {"rating": round(avg, 2)}})
    return {"ok": True}

# ---------- WALLET ----------
@api_router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    txns = await db.wallet_transactions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"balance": user.get("wallet_balance", 0.0), "transactions": txns}

@api_router.post("/wallet/add")
async def wallet_add(payload: dict, user=Depends(get_current_user)):
    amt = float(payload.get("amount", 0))
    if amt <= 0:
        raise HTTPException(400, "Invalid amount")
    new_balance = user.get("wallet_balance", 0) + amt
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    await db.wallet_transactions.insert_one({
        "user_id": user["user_id"], "amount": amt, "type": "credit",
        "description": payload.get("description", "Wallet top-up"),
        "matter_id": None,  # forward-ready: no Matter UI yet, always null until it ships
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"balance": new_balance}


# ============================================================================
# EARNINGS — the single earnings engine every capability="can_earn" role
# plugs into. Wallet (available balance) is already unified across every
# role (users.wallet_balance); what was missing was a way to convert that
# balance into an actual bank payout — withdraw() creates a db.settlements
# row (settlement_type="withdrawal") and reuses the exact same queued/paid/
# failed pipeline vendor payouts already go through (see settlements.py).
# ============================================================================
@api_router.get("/earnings/me")
async def get_earnings_me(user=Depends(get_current_user)):
    _require_capability(user, "can_earn")
    txns = await db.wallet_transactions.find({"user_id": user["user_id"]}, {"_id": 0, "amount": 1, "type": 1, "created_at": 1}).to_list(5000)
    lifetime = sum(t["amount"] for t in txns if t["type"] == "credit")
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    monthly = sum(t["amount"] for t in txns if t["type"] == "credit" and (t.get("created_at") or "").startswith(month_prefix))
    pending_settlements = await db.settlements.find(
        {"payee_id": user["user_id"], "status": "queued"}, {"amount": 1},
    ).to_list(500)
    pending = sum(s["amount"] for s in pending_settlements)
    return {
        "available": round(user.get("wallet_balance", 0), 2),
        "pending": round(pending, 2),
        "lifetime": round(lifetime, 2),
        "monthly": round(monthly, 2),
    }

@api_router.post("/earnings/withdraw")
async def withdraw_earnings(payload: WithdrawRequest, user=Depends(get_current_user)):
    _require_capability(user, "can_earn")
    if payload.amount <= 0:
        raise HTTPException(400, "Invalid amount")
    if payload.amount > user.get("wallet_balance", 0):
        raise HTTPException(400, "Insufficient wallet balance")
    new_balance = user.get("wallet_balance", 0) - payload.amount
    now = datetime.now(timezone.utc)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    await db.wallet_transactions.insert_one({
        "user_id": user["user_id"], "amount": payload.amount, "type": "debit",
        "description": "Withdrawal requested", "context_type": "withdrawal_request",
        "created_at": now.isoformat(),
    })
    settlement_id = f"STL{now.strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    await db.settlements.insert_one({
        "settlement_id": settlement_id,
        "settlement_type": "withdrawal",
        "payee_type": user["role"],
        "payee_id": user["user_id"],
        "vendor_id": None,
        "shop_name": user.get("name"),
        "bank_account": payload.bank_account,
        "bank_ifsc": payload.bank_ifsc,
        "has_gst": False,
        "gst_number": None,
        "cycle_date": now.date().isoformat(),
        "order_ids": [],
        "order_count": 0,
        "amount": round(payload.amount, 2),
        "payment_mode": "NEFT" if payload.bank_account else "UPI",
        "status": "queued",
        "created_at": now.isoformat(),
    })
    return {"ok": True, "settlement_id": settlement_id, "balance": round(new_balance, 2)}

@api_router.get("/earnings/settlements")
async def get_earnings_settlements(user=Depends(get_current_user)):
    _require_capability(user, "can_earn")
    return await db.settlements.find(
        {"$or": [{"payee_id": user["user_id"]}, {"vendor_id": user["user_id"]}]}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)

# ---------- AI ASSISTANT ----------
# Not wired to a real LLM provider yet (the previous integration depended on an
# uninstalled package). /ai/chat is a clear stub rather than a 500; the filing
# checklist still returns a useful deterministic answer.
@api_router.post("/ai/chat")
async def ai_chat(req: ChatMessage, user=Depends(get_current_user)):
    raise HTTPException(503, "AI Assistant chat is not yet available.")

@api_router.get("/ai/history/{session_id}")
async def ai_history(session_id: str, user=Depends(get_current_user)):
    msgs = await db.ai_messages.find({"session_id": session_id, "user_id": user["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(100)
    return msgs

@api_router.post("/ai/filing-checklist")
async def filing_checklist(payload: dict, user=Depends(get_current_user)):
    court = payload.get("court", "")
    case_type = payload.get("case_type", "")
    checklist = (
        f"Filing checklist for {case_type or 'matter'} at {court or 'court'}:\n"
        "1. Vakalatnama (signed by client, notarised) - 2 copies\n"
        "2. Plaint / Petition - original + 2 copies, signed and verified\n"
        "3. Statement of Truth / Affidavit - notarised\n"
        "4. List of documents (Order VII Rule 14 CPC) with copies\n"
        "5. Court fee stamps as per applicable Court Fees Act\n"
        "6. Process fee (PF) and summons fee\n"
        "7. Index, synopsis, list of dates\n"
        "8. Spiral / cloth binding as per court rules\n"
        "9. ID proof of advocate (Bar Council ID copy)\n"
        "10. E-filing acknowledgement (if applicable)"
    )
    return {"checklist": checklist}

# ---------- ADMIN ----------
@api_router.get("/admin/analytics")
async def admin_analytics(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    total_orders = await db.orders.count_documents({})
    total_users = await db.users.count_documents({})
    total_vendors = await db.vendors.count_documents({"kyc_status": "approved"})
    pending_vendors = await db.vendors.count_documents({"kyc_status": "pending"})
    revenue = 0
    commission = 0
    async for order in db.orders.find({"payment_status": "paid"}, {"pricing": 1}):
        revenue += order.get("pricing", {}).get("total", 0)
        commission += order.get("pricing", {}).get("platform_commission", 0)
    pipeline = [
        {"$unwind": "$services"},
        {"$group": {"_id": "$services.service_id", "count": {"$sum": "$services.qty"}}},
        {"$sort": {"count": -1}}, {"$limit": 5},
    ]
    top_services = []
    async for d in db.orders.aggregate(pipeline):
        svc = await db.services.find_one({"service_id": d["_id"]}, {"_id": 0, "name": 1})
        top_services.append({"service_id": d["_id"], "name": svc["name"] if svc else d["_id"], "count": d["count"]})
    pipeline2 = [
        {"$group": {"_id": "$court_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 5},
    ]
    court_demand = []
    async for d in db.orders.aggregate(pipeline2):
        c = await db.courts.find_one({"court_id": d["_id"]}, {"_id": 0, "name": 1})
        court_demand.append({"court_id": d["_id"], "name": c["name"] if c else d["_id"], "count": d["count"]})
    return {
        "total_orders": total_orders, "total_users": total_users,
        "total_vendors": total_vendors, "pending_kyc": pending_vendors,
        "revenue": round(revenue, 2), "platform_commission": round(commission, 2),
        "top_services": top_services, "court_demand": court_demand,
    }

@api_router.get("/admin/escrow-transactions")
async def admin_escrow_transactions(user=Depends(get_current_user), context_type: Optional[str] = None, status: Optional[str] = None):
    """Read-only reporting/finance path over every escrow-held payment on the
    platform — not hearing-specific, so any future escrow-using service is
    visible here without new code (see escrow.py's module docstring)."""
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    import escrow as escrow_svc
    return await escrow_svc.list_transactions(db, context_type=context_type, status=status)

@api_router.get("/admin/vendors")
async def admin_vendors(user=Depends(get_current_user), status: Optional[str] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    q: Dict[str, Any] = {}
    if status:
        q["kyc_status"] = status
    return await db.vendors.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)

@api_router.put("/admin/services/{service_id}/pricing")
async def update_service_pricing(service_id: str, payload: PricingUpdate, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    data = payload.model_dump(exclude={"service_id", "visibility"})
    update = {k: v for k, v in data.items() if v is not None}
    if payload.visibility:
        # Dotted-path $set so toggling one surface (e.g. visibility.landing)
        # never clobbers the others — this is the "founder can flip
        # Marketplace/Landing/Sidebar independently" admin control point.
        for surface, value in payload.visibility.items():
            update[f"visibility.{surface}"] = value
    await db.services.update_one({"service_id": service_id}, {"$set": update})
    return {"ok": True}

@api_router.get("/admin/users")
async def admin_users(user=Depends(get_current_user), role: Optional[str] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    q: Dict[str, Any] = {}
    if role:
        q["role"] = role
    return await db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(200)

@api_router.put("/admin/users/{user_id}/deactivate")
async def admin_deactivate_user(user_id: str, user=Depends(get_current_user), request: Request = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    if user_id == user["user_id"]:
        raise HTTPException(400, "You cannot deactivate your own account")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("role") == "admin":
        raise HTTPException(400, "Admin accounts cannot be deactivated from this screen")
    if target.get("deleted"):
        return {"ok": True, "already_deactivated": True}
    from audit_log import deactivate_user, log_audit
    try:
        await deactivate_user(db, user_id, user["user_id"])
    except Exception as e:
        logger.error(f"admin.user_deactivated FAILED: admin={user['user_id']} target={user_id} error={e}")
        await log_audit(db, "admin.user_deactivated", user, {
            "target_user_id": user_id, "target_email": target.get("email"), "result": "failure", "error": str(e),
        }, request)
        raise HTTPException(500, "Could not deactivate this user")
    logger.info(f"admin.user_deactivated: admin={user['user_id']} target={user_id} email={target.get('email')}")
    await log_audit(db, "admin.user_deactivated", user, {
        "target_user_id": user_id, "target_email": target.get("email"),
        "target_role": target.get("role"), "result": "success",
    }, request)
    return {"ok": True}

@api_router.put("/admin/users/{user_id}/reactivate")
async def admin_reactivate_user(user_id: str, user=Depends(get_current_user), request: Request = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, "User not found")
    if not target.get("deleted"):
        return {"ok": True, "already_active": True}
    from audit_log import reactivate_user, log_audit
    try:
        await reactivate_user(db, user_id, user["user_id"])
    except Exception as e:
        logger.error(f"admin.user_reactivated FAILED: admin={user['user_id']} target={user_id} error={e}")
        await log_audit(db, "admin.user_reactivated", user, {
            "target_user_id": user_id, "target_email": target.get("email"), "result": "failure", "error": str(e),
        }, request)
        raise HTTPException(500, "Could not reactivate this user")
    logger.info(f"admin.user_reactivated: admin={user['user_id']} target={user_id} email={target.get('email')}")
    await log_audit(db, "admin.user_reactivated", user, {
        "target_user_id": user_id, "target_email": target.get("email"),
        "target_role": target.get("role"), "result": "success",
    }, request)
    return {"ok": True}

# ---------- SUBSCRIPTION ----------
SUBSCRIPTION_PLANS = {
    "free": {"name": "Free", "price": 0, "features": ["Basic services", "Standard pricing"]},
    "advocate_pro": {"name": "Advocate Pro", "price": 499, "features": ["10% discount", "Priority support", "Faster turnaround"]},
    "law_firm": {"name": "Law Firm", "price": 2499, "features": ["Multi-user (5 seats)", "Central billing", "Bulk orders", "15% discount"]},
    "enterprise": {"name": "Enterprise", "price": 9999, "features": ["Unlimited seats", "Dedicated manager", "Custom SLA", "25% discount"]},
}

@api_router.get("/subscriptions/plans")
async def subscription_plans():
    return SUBSCRIPTION_PLANS

@api_router.post("/subscriptions/activate")
async def activate_subscription(payload: dict, user=Depends(get_current_user)):
    plan = payload.get("plan")
    if plan not in SUBSCRIPTION_PLANS:
        raise HTTPException(400, "Invalid plan")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"subscription": plan}})
    return {"ok": True, "plan": plan}

# ============================================================================
# RAZORPAY (alongside Stripe)
# ============================================================================
@api_router.post("/payments/razorpay/create-order")
async def rzp_create_order(payload: dict, user=Depends(get_current_user)):
    import razorpay_svc
    order_id = payload.get("order_id")
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order or order["user_id"] != user["user_id"]:
        raise HTTPException(404, "Order not found")
    amount = float(order["pricing"]["total"])
    rzp = razorpay_svc.create_order(amount, order_id, notes={"order_id": order_id, "user_id": user["user_id"]})
    await db.payment_transactions.insert_one({
        "session_id": rzp["razorpay_order_id"],
        "razorpay_order_id": rzp["razorpay_order_id"],
        "order_id": order_id,
        "user_id": user["user_id"],
        "amount": amount,
        "currency": "INR",
        "gateway": "razorpay",
        "status": "initiated",
        "payment_status": "pending",
        "simulated": rzp.get("simulated", False),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return rzp

@api_router.post("/payments/razorpay/verify")
async def rzp_verify(payload: dict, user=Depends(get_current_user)):
    import razorpay_svc
    rzp_order_id = payload.get("razorpay_order_id")
    rzp_payment_id = payload.get("razorpay_payment_id") or f"pay_sim_{uuid.uuid4().hex[:14]}"
    rzp_signature = payload.get("razorpay_signature") or "simulated"
    ok = razorpay_svc.verify_payment(rzp_order_id, rzp_payment_id, rzp_signature)
    if not ok:
        raise HTTPException(400, "Payment verification failed")
    tx = await db.payment_transactions.find_one({"razorpay_order_id": rzp_order_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    await db.payment_transactions.update_one(
        {"razorpay_order_id": rzp_order_id},
        {"$set": {"payment_status": "paid", "status": "complete", "razorpay_payment_id": rzp_payment_id}},
    )
    await db.orders.update_one(
        {"order_id": tx["order_id"]},
        {"$set": {"payment_status": "paid", "status": "matched"},
         "$push": {"timeline": {"status": "matched", "at": datetime.now(timezone.utc).isoformat(), "note": "Payment successful via Razorpay"}}},
    )
    return {"ok": True, "payment_id": rzp_payment_id}

@api_router.get("/payments/methods")
async def payment_methods():
    import razorpay_svc
    return {
        "razorpay": razorpay_svc.is_enabled(),
        "razorpay_simulated": not razorpay_svc.is_enabled(),
    }

# ============================================================================
# LAW FIRM Multi-User Seats + Roles
# ============================================================================
FIRM_ROLES = ["owner", "partner", "associate", "paralegal"]

class FirmCreate(BaseModel):
    name: str
    gst: Optional[str] = None
    address: Optional[str] = None

class FirmInvite(BaseModel):
    firm_id: str
    email: EmailStr
    name: str
    role: str = "associate"

@api_router.post("/firms")
async def create_firm(payload: FirmCreate, user=Depends(get_current_user)):
    firm_id = f"firm_{uuid.uuid4().hex[:10]}"
    doc = {
        "firm_id": firm_id, "name": payload.name, "gst": payload.gst, "address": payload.address,
        "owner_id": user["user_id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.firms.insert_one(doc)
    await db.users.update_one({"user_id": user["user_id"]},
        {"$set": {"firm_id": firm_id, "firm_role": "owner", "role": "law_firm"},
         "$addToSet": {"professional_profile_types": "law_firm"}})
    await db.firm_members.insert_one({
        "firm_id": firm_id, "user_id": user["user_id"], "name": user["name"], "email": user["email"],
        "role": "owner", "status": "active", "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    doc.pop("_id", None)
    return doc

@api_router.get("/firms/me")
async def my_firm(user=Depends(get_current_user)):
    firm_id = user.get("firm_id")
    if not firm_id:
        return {"onboarded": False}
    firm = await db.firms.find_one({"firm_id": firm_id}, {"_id": 0})
    members = await db.firm_members.find({"firm_id": firm_id}, {"_id": 0}).to_list(100)
    return {"onboarded": True, "firm": firm, "members": members, "my_role": user.get("firm_role", "associate")}

@api_router.post("/firms/invite")
async def invite_member(payload: FirmInvite, user=Depends(get_current_user)):
    if payload.role not in FIRM_ROLES:
        raise HTTPException(400, "Invalid role")
    if user.get("firm_id") != payload.firm_id or user.get("firm_role") not in ("owner", "partner"):
        raise HTTPException(403, "Only firm owner/partner can invite")
    invite_id = f"inv_{uuid.uuid4().hex[:10]}"
    invite_token = uuid.uuid4().hex
    await db.firm_invites.insert_one({
        "invite_id": invite_id, "firm_id": payload.firm_id, "email": payload.email,
        "name": payload.name, "role": payload.role, "token": invite_token, "status": "pending",
        "invited_by": user["user_id"], "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Send email invite
    firm = await db.firms.find_one({"firm_id": payload.firm_id}, {"_id": 0})
    try:
        from notifications import send_email
        send_email(
            payload.email,
            f"You're invited to join {firm['name']} on CourtBazaar",
            f"<p>Hi {payload.name},</p><p>{user['name']} invited you to join <b>{firm['name']}</b> on CourtBazaar as <b>{payload.role}</b>.</p><p>Token: <code>{invite_token}</code></p><p>Visit courtbazaar.com to accept.</p>",
        )
    except Exception as e:
        logger.error(f"invite email error: {e}")
    return {"invite_id": invite_id, "token": invite_token}

@api_router.post("/firms/accept-invite")
async def accept_invite(payload: dict, user=Depends(get_current_user)):
    token = payload.get("token")
    inv = await db.firm_invites.find_one({"token": token, "status": "pending"}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invite not found or expired")
    await db.users.update_one({"user_id": user["user_id"]},
        {"$set": {"firm_id": inv["firm_id"], "firm_role": inv["role"], "role": "law_firm"},
         "$addToSet": {"professional_profile_types": "law_firm"}})
    await db.firm_members.insert_one({
        "firm_id": inv["firm_id"], "user_id": user["user_id"], "name": user["name"], "email": user["email"],
        "role": inv["role"], "status": "active", "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.firm_invites.update_one({"invite_id": inv["invite_id"]}, {"$set": {"status": "accepted"}})
    return {"ok": True, "firm_id": inv["firm_id"]}

@api_router.delete("/firms/{firm_id}/members/{member_id}")
async def remove_member(firm_id: str, member_id: str, user=Depends(get_current_user)):
    if user.get("firm_id") != firm_id or user.get("firm_role") != "owner":
        raise HTTPException(403, "Only owner can remove")
    await db.firm_members.delete_one({"firm_id": firm_id, "user_id": member_id})
    await db.users.update_one({"user_id": member_id}, {"$unset": {"firm_id": "", "firm_role": ""}})
    return {"ok": True}

@api_router.get("/firms/{firm_id}/orders")
async def firm_orders(firm_id: str, user=Depends(get_current_user)):
    if user.get("firm_id") != firm_id:
        raise HTTPException(403, "Forbidden")
    orders = await db.orders.find({"firm_id": firm_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return orders

# ============================================================================
# DELIVERY PARTNER WORKFLOW
# ============================================================================
class DeliveryUpdate(BaseModel):
    lat: float
    lng: float
    note: Optional[str] = None

@api_router.get("/delivery/queue")
async def delivery_queue(user=Depends(get_current_user)):
    if user["role"] not in ("delivery_partner", "admin"):
        raise HTTPException(403, "Forbidden")
    q = {"status": {"$in": ["ready", "out_for_delivery"]}, "delivery_option": {"$in": ["chamber", "court"]}}
    if user["role"] == "delivery_partner":
        # Show orders assigned to this partner OR unassigned ready ones
        q = {"$or": [{"delivery_partner_id": user["user_id"]}, {"delivery_partner_id": None, "status": "ready"}]}
    orders = await db.orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
    return orders

@api_router.post("/delivery/{order_id}/accept")
async def accept_delivery(order_id: str, user=Depends(get_current_user)):
    if user["role"] != "delivery_partner":
        raise HTTPException(403, "Delivery partner only")
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"delivery_partner_id": user["user_id"], "delivery_partner_name": user["name"], "status": "out_for_delivery"},
         "$push": {"timeline": {"status": "out_for_delivery", "at": datetime.now(timezone.utc).isoformat(), "note": f"Delivery partner {user['name']} en route"}}},
    )
    return {"ok": True}

@api_router.post("/delivery/{order_id}/location")
async def update_location(order_id: str, loc: DeliveryUpdate, user=Depends(get_current_user)):
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"delivery_location": {"lat": loc.lat, "lng": loc.lng, "updated_at": datetime.now(timezone.utc).isoformat(), "note": loc.note}}},
    )
    return {"ok": True}

@api_router.post("/delivery/{order_id}/complete")
async def complete_delivery(order_id: str, payload: dict, user=Depends(get_current_user)):
    otp_provided = payload.get("otp")
    if otp_provided != "123456":  # Mock delivery OTP
        raise HTTPException(400, "Invalid delivery OTP. Use 123456 for demo.")
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": "delivered", "delivered_at": datetime.now(timezone.utc).isoformat()},
         "$push": {"timeline": {"status": "delivered", "at": datetime.now(timezone.utc).isoformat(), "note": "Delivered with OTP confirmation"}}},
    )
    return {"ok": True}

@api_router.get("/delivery/integrations")
async def delivery_integrations():
    return {
        "dunzo_enabled": bool(os.environ.get("DUNZO_API_KEY")),
        "borzo_enabled": bool(os.environ.get("BORZO_API_KEY")),
        "own_network": True,
    }

# ============================================================================
# DOCUMENT INTELLIGENCE (AI-powered)
# ============================================================================
class DocAnalyzeRequest(BaseModel):
    file_ids: List[str]
    target_court: Optional[str] = None
    case_type: Optional[str] = None

@api_router.post("/doc-intel/analyze")
async def doc_intel_analyze(req: DocAnalyzeRequest, user=Depends(get_current_user)):
    from ocr_engine import analyze_document
    import json as _json
    files = await db.files.find({"file_id": {"$in": req.file_ids}, "user_id": user["user_id"]}, {"_id": 0}).to_list(50)
    if not files:
        raise HTTPException(404, "Files not found")
    court = await db.courts.find_one({"court_id": req.target_court}, {"_id": 0}) if req.target_court else None

    # REAL OCR / PDF analysis
    analyses = []
    combined_text_chunks = []
    total_pages = 0
    any_ocr = False
    text_layer_count = 0
    page_numbers_detected = 0
    for f in files:
        try:
            data, ct = get_object(f["storage_path"])
        except Exception as e:
            logger.error(f"download for analysis failed: {e}")
            continue
        a = analyze_document(data, ct, f.get("original_filename", ""))
        analyses.append({"filename": f["original_filename"], **{k: a[k] for k in a if k != "text"}})
        if a["text"]:
            combined_text_chunks.append(f"=== {f['original_filename']} ===\n{a['text']}")
        total_pages += a["page_count"]
        if a["ocr_used"]:
            any_ocr = True
        if a["has_text_layer"]:
            text_layer_count += 1
        page_numbers_detected += a["page_numbers_detected"]

    combined_text = "\n\n".join(combined_text_chunks)[:12000]
    files_summary = "\n".join([f"- {a['filename']}: pages={a['page_count']}, chars={a['char_count']}, ocr_used={a['ocr_used']}, has_text_layer={a['has_text_layer']}, page_numbers_seen={a['page_numbers_detected']}" for a in analyses])

    prompt = f"File metadata:\n{files_summary}\n\nExtracted text (truncated):\n{combined_text or '[no text extracted]'}\n\n"
    if court:
        prompt += f"Target court: {court['name']} ({court.get('type')}).\n"
    if req.case_type:
        prompt += f"Case type: {req.case_type}.\n"
    prompt += "Return the JSON object only."

    raw = ""
    try:
        # Not wired to a real LLM provider yet (the previous integration depended on
        # an uninstalled package) — falls straight through to the heuristic report below.
        from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"docint_{user['user_id']}_{uuid.uuid4().hex[:8]}",
            system_message=(
                "You are CourtBazaar's Document Intelligence engine for Indian courts. "
                "Analyze the extracted text + metadata and return ONLY a single JSON object (no markdown, no prose) with: "
                '{"filing_readiness_score": int 0-100, "ocr_quality_score": int 0-100, "pagination_score": int 0-100, '
                '"missing_documents": [str], "defects": [{"severity": "high|medium|low", "issue": str, "fix": str}], '
                '"recommended_services": [{"service_name": str, "reason": str}], '
                '"summary": str}. Use Indian legal terminology. Keep arrays small (max 5 each). '
                "Base scores on the actual extracted content, not just the filenames."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                raw += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.error(f"doc-intel AI error: {e}")

    raw_strip = raw.strip()
    if raw_strip.startswith("```"):
        raw_strip = raw_strip.split("```", 2)[1]
        if raw_strip.startswith("json"):
            raw_strip = raw_strip[4:]
        raw_strip = raw_strip.strip("` \n")
    try:
        report = _json.loads(raw_strip)
    except Exception:
        # Heuristic fallback from OCR analysis
        text_layer_ratio = (text_layer_count / len(analyses)) if analyses else 0
        ocr_score = 90 if not any_ocr else (75 if combined_text else 40)
        pagination_score = 85 if page_numbers_detected >= total_pages * 0.7 else (60 if page_numbers_detected > 0 else 35)
        readiness = int((ocr_score + pagination_score + text_layer_ratio * 100) / 3)
        report = {
            "filing_readiness_score": readiness, "ocr_quality_score": ocr_score, "pagination_score": pagination_score,
            "missing_documents": [], "defects": [],
            "recommended_services": ([{"service_name": "Pagination", "reason": "Page numbers not consistently detected"}] if pagination_score < 70 else []) + ([{"service_name": "OCR Conversion", "reason": "Document appears to be scanned without text layer"}] if any_ocr else []),
            "summary": f"{len(analyses)} file(s), {total_pages} page(s). OCR used: {any_ocr}. Text layer present: {text_layer_count}/{len(analyses)}.",
        }

    record = {
        "report_id": f"docint_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "file_ids": req.file_ids, "target_court": req.target_court, "case_type": req.case_type,
        "report": report,
        "extracted": {
            "total_pages": total_pages, "ocr_used": any_ocr,
            "text_layer_count": text_layer_count, "page_numbers_detected": page_numbers_detected,
            "files": analyses,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.doc_intel_reports.insert_one(record)
    record.pop("_id", None)
    return record

# ============================================================================
# SPONSORED VENDOR LISTINGS
# ============================================================================
SPONSORED_PLAN = {"price": 999, "duration_days": 30, "benefits": ["Top priority in auto-matching", "Highlighted in court directory", "Sponsored badge"]}

@api_router.get("/vendors/sponsored/plan")
async def sponsored_plan():
    return SPONSORED_PLAN

@api_router.post("/vendors/sponsored/activate")
async def activate_sponsored(user=Depends(get_current_user)):
    v = await db.vendors.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Vendor profile not found")
    expires = datetime.now(timezone.utc) + timedelta(days=SPONSORED_PLAN["duration_days"])
    await db.vendors.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"sponsored": True, "sponsored_until": expires.isoformat(),
                  "sponsored_started_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "sponsored_until": expires.isoformat(), "amount": SPONSORED_PLAN["price"]}

# ============================================================================
# NOTIFICATIONS
# ============================================================================
@api_router.get("/notifications/status")
async def notifications_status():
    from notifications import status
    return status()

@api_router.put("/notifications/prefs")
async def update_notif_prefs(payload: dict, user=Depends(get_current_user)):
    prefs = {k: bool(v) for k, v in payload.items() if k in ("sms", "whatsapp", "email")}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"notif_prefs": prefs}})
    return {"ok": True, "notif_prefs": prefs}

@api_router.get("/notifications")
async def list_notifications(user=Depends(get_current_user), unread_only: bool = False):
    """The in-app Notification Center feed — every hearing/order/payment/
    document/AI/support event fans out here via notifications.record_notification_event,
    alongside whatever SMS/WhatsApp/email channels notify() already dispatches to."""
    query: Dict[str, Any] = {"user_id": user["user_id"]}
    if unread_only:
        query["read_at"] = None
    return await db.notification_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

@api_router.put("/notifications/read-all")
async def mark_all_notifications_read(user=Depends(get_current_user)):
    """Marks every currently-unread notification for this user as read in one
    call — backs the dashboard's "View All Notifications" seen-effect and the
    Notifications page's "Mark all read". Only touches unread rows so read_at
    keeps the timestamp of when each was actually first seen."""
    result = await db.notification_events.update_many(
        {"user_id": user["user_id"], "read_at": None},
        {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "marked_read": result.modified_count}

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user=Depends(get_current_user)):
    result = await db.notification_events.update_one(
        {"notification_id": notification_id, "user_id": user["user_id"]},
        {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


# ============================================================================
# CALENDAR — aggregation view (hearings once they exist, orders, manual
# entries, court holidays). Not a new data owner beyond calendar_events/
# court_holidays; recent orders are surfaced by created_at as reference
# context, not plotted as "scheduled" dates — orders don't carry a real
# scheduled date today, so labeling them that way on a calendar would be
# dishonest about what the data actually means.
# ============================================================================
@api_router.post("/calendar/events")
async def create_calendar_event(req: CalendarEventCreate, user=Depends(get_current_user)):
    event = {
        "event_id": f"cal_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "title": req.title,
        "date": req.date,
        "kind": req.kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_events.insert_one(event)
    event.pop("_id", None)
    return event

@api_router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: str, user=Depends(get_current_user)):
    result = await db.calendar_events.delete_one({"event_id": event_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Event not found")
    return {"ok": True}

@api_router.get("/calendar")
async def get_calendar(user=Depends(get_current_user)):
    events = await db.calendar_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("date", 1).to_list(200)
    holidays = await db.court_holidays.find({}, {"_id": 0}).to_list(200)
    recent_orders = await db.orders.find(
        {"user_id": user["user_id"]}, {"_id": 0, "order_id": 1, "court_name": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(20)
    return {"events": events, "holidays": holidays, "recent_orders": recent_orders}


# ============================================================================
# MATTERS — schema-ready for the future "everything belongs to a Matter"
# model (hearings, orders, documents, payments). No workspace/UI ships with
# this phase; basic CRUD exists now purely so those entities have somewhere
# real to point their nullable matter_id at, instead of a backfill later.
# ============================================================================
@api_router.post("/matters")
async def create_matter(req: MatterCreate, user=Depends(get_current_user)):
    matter_id = f"matter_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "matter_id": matter_id,
        "owner_user_id": user["user_id"],
        "firm_id": user.get("firm_id"),
        "title": req.title,
        "description": req.description,
        "court_id": req.court_id,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    await db.matters.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/matters")
async def list_matters(user=Depends(get_current_user)):
    query: Dict[str, Any] = {"owner_user_id": user["user_id"]}
    if user.get("firm_id"):
        query = {"$or": [{"owner_user_id": user["user_id"]}, {"firm_id": user["firm_id"]}]}
    return await db.matters.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)

@api_router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, user=Depends(get_current_user)):
    matter = await db.matters.find_one({"matter_id": matter_id}, {"_id": 0})
    if not matter:
        raise HTTPException(404, "Matter not found")
    if matter["owner_user_id"] != user["user_id"] and matter.get("firm_id") != user.get("firm_id") and user["role"] != "admin":
        raise HTTPException(403, "Forbidden")
    return matter

@api_router.put("/matters/{matter_id}")
async def update_matter(matter_id: str, req: MatterUpdate, user=Depends(get_current_user)):
    matter = await db.matters.find_one({"matter_id": matter_id})
    if not matter:
        raise HTTPException(404, "Matter not found")
    if matter["owner_user_id"] != user["user_id"] and user["role"] != "admin":
        raise HTTPException(403, "Forbidden")
    update = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if "status" in update and update["status"] not in MATTER_STATUSES:
        raise HTTPException(400, "Invalid status")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.matters.update_one({"matter_id": matter_id}, {"$set": update})
    return {"ok": True}


# ============================================================================
# MY PRACTICE (Proxy Counsel) — profile + availability. Gated by capability,
# not role string, so a future practice-type profile (e.g. E-Filing Partner)
# can reuse the same route shape without a ProtectedRoute rewrite.
# ============================================================================
import practice as practice_svc

def _require_capability(user: dict, capability: str) -> None:
    if capability not in (user.get("capabilities") or []):
        raise HTTPException(403, "Not available for this account")

@api_router.get("/practice/profile")
async def get_practice_profile(user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.get_or_create_profile(db, user["user_id"])

@api_router.put("/practice/profile")
async def put_practice_profile(payload: ProxyCounselProfileUpdate, user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.update_profile(db, user["user_id"], payload.model_dump(exclude_unset=True))

@api_router.get("/practice/availability")
async def get_practice_availability(user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.list_slots(db, user["user_id"])

@api_router.post("/practice/availability")
async def post_practice_availability(payload: AvailabilitySlotCreate, user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.add_slot(db, user["user_id"], payload.kind, payload.day_of_week,
                                        payload.date, payload.court_id, payload.start_time, payload.end_time)

@api_router.delete("/practice/availability/{slot_id}")
async def delete_practice_availability(slot_id: str, user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.remove_slot(db, user["user_id"], slot_id)

@api_router.get("/practice/performance")
async def get_practice_performance(user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await practice_svc.performance(db, user["user_id"])


# ---------- ADMIN: proxy counsel verification (Counsel Matching Agent
# eligibility prerequisite — see practice.approve_kyc/verify_bar_council) ----
@api_router.put("/admin/practice/{user_id}/approve-kyc")
async def admin_approve_practice_kyc(user_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    profile = await practice_svc.approve_kyc(db, user_id)
    try:
        from audit_log import log_audit
        await log_audit(db, "practice.approve_kyc", user, {"target_user_id": user_id})
    except Exception:
        pass
    return profile

@api_router.put("/admin/practice/{user_id}/verify-bar-council")
async def admin_verify_practice_bar_council(user_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    profile = await practice_svc.verify_bar_council(db, user_id)
    try:
        from audit_log import log_audit
        await log_audit(db, "practice.verify_bar_council", user, {"target_user_id": user_id})
    except Exception:
        pass
    return profile


# ---------- Proxy Counsel Page: AI Recommendations + Filters (founder
# follow-up request, post-roadmap). Backs the Proxy Counsel request flow's
# CounselDiscoveryPanel and ManualCounselSearch (both call this through
# frontend/src/lib/advocateRecommendationsApi.js's getAvailableAdvocates) —
# reuses counsel_matching.list_and_recommend, which itself reuses the same
# verified_counsel_query/score_candidates the hearing-time matching pipeline
# (M5/M6) already uses, rather than a separate recommendation engine. ----
async def _advocate_cards_for(ranked: list) -> list:
    """Shared card-building for a ranked candidate list — used by
    /recommendations/advocates (full, authenticated), /public/proxy-counsels
    (trimmed, anonymous — see counsel_matching.public_advocate_card), and
    nothing else, so the names/court lookups live in exactly one place."""
    if not ranked:
        return []
    import counsel_matching
    user_ids = [c["user_id"] for c in ranked]
    names_by_id = {
        u["user_id"]: u.get("name")
        for u in await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1}).to_list(len(user_ids))
    }
    court_ids = sorted({cid for c in ranked for cid in (c.get("courts") or [])})
    court_names_by_id = {
        c["court_id"]: c["name"]
        for c in (await db.courts.find({"court_id": {"$in": court_ids}}, {"_id": 0, "court_id": 1, "name": 1}).to_list(len(court_ids)) if court_ids else [])
    }
    # list_and_recommend only ever returns verified_counsel_query() matches,
    # so every result here has already passed KYC + bar council verification
    # — this is what CounselCard/CounselProfileDialog's "Verified" badge reads.
    return [counsel_matching.build_advocate_card(c, names_by_id.get(c["user_id"]), court_names_by_id) for c in ranked]


@api_router.get("/recommendations/advocates")
async def recommendations_advocates(
    court_id: Optional[str] = None, state_id: Optional[str] = None, district: Optional[str] = None,
    specialization: Optional[str] = None, min_experience_years: Optional[float] = None,
    experience_bracket: Optional[str] = None,
    min_rating: Optional[float] = None, fee_min: Optional[float] = None, fee_max: Optional[float] = None,
    time_slot: Optional[str] = None,
    available_only: bool = False, limit: int = 20,
    user=Depends(get_current_user),
):
    _require_capability(user, "can_hire_proxy_counsel")
    import counsel_matching
    ranked, total = await counsel_matching.list_and_recommend(
        db, court_id=court_id, state_id=state_id, district=district, specialization=specialization,
        min_experience_years=min_experience_years, experience_bracket=experience_bracket,
        min_rating=min_rating, fee_min=fee_min, fee_max=fee_max, time_slot=time_slot,
        available_only=available_only, limit=limit,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    advocates = await _advocate_cards_for(ranked)
    return {
        "source": "live",
        "metadata": {"total_candidates": total, "returned": len(advocates), "generated_at": generated_at},
        "advocates": advocates,
    }


@api_router.get("/public/proxy-counsels")
async def public_proxy_counsels(
    request: Request,
    court_id: Optional[str] = None, state_id: Optional[str] = None, district: Optional[str] = None,
    specialization: Optional[str] = None, min_experience_years: Optional[float] = None,
    experience_bracket: Optional[str] = None,
    min_rating: Optional[float] = None, fee_min: Optional[float] = None, fee_max: Optional[float] = None,
    time_slot: Optional[str] = None,
    available_only: bool = False, hearing_date: Optional[str] = None, limit: int = 20,
):
    """Public, unauthenticated counterpart to /recommendations/advocates —
    the founder's direction is that the counsel browse grid itself is
    public (no login wall), only viewing a full profile or booking one
    requires an account (see /advocates/{id}/profile and
    POST /hearing-requests). Returns counsel_matching.public_advocate_card's
    trimmed shape only — never bio/education/languages/full court list.

    time_slot/experience_bracket back the browse page's own filters (founder
    follow-up, 2026-08) — see counsel_matching.list_and_recommend for what
    each one matches against."""
    import counsel_matching
    client_ip = request.client.host if request.client else "unknown"
    counsel_matching.check_public_list_rate_limit(client_ip)
    ranked, total = await counsel_matching.list_and_recommend(
        db, court_id=court_id, state_id=state_id, district=district, specialization=specialization,
        min_experience_years=min_experience_years, experience_bracket=experience_bracket,
        min_rating=min_rating, fee_min=fee_min, fee_max=fee_max, time_slot=time_slot,
        available_only=available_only, hearing_date=hearing_date, limit=limit,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    cards = await _advocate_cards_for(ranked)
    advocates = [counsel_matching.public_advocate_card(c) for c in cards]
    return {
        "metadata": {"total_candidates": total, "returned": len(advocates), "generated_at": generated_at},
        "advocates": advocates,
    }


async def _advocate_profile_or_404(advocate_id: str) -> dict:
    """Shared lookup for the full profile-detail shape — only ever returns a
    verified_counsel_query() match, same trust gate as the browse list."""
    import counsel_matching
    profile = await db.proxy_counsel_profiles.find_one(
        {"user_id": advocate_id, **counsel_matching.verified_counsel_query()}, {"_id": 0},
    )
    if not profile:
        raise HTTPException(404, "Counsel profile not found")
    name_doc = await db.users.find_one({"user_id": advocate_id}, {"_id": 0, "name": 1})
    court_ids = profile.get("courts") or []
    court_names_by_id = {
        c["court_id"]: c["name"]
        for c in (await db.courts.find({"court_id": {"$in": court_ids}}, {"_id": 0, "court_id": 1, "name": 1}).to_list(len(court_ids)) if court_ids else [])
    }
    return counsel_matching.build_advocate_card(profile, name_doc.get("name") if name_doc else None, court_names_by_id)


@api_router.get("/public/proxy-counsels/{advocate_id}/profile")
async def get_public_advocate_profile(advocate_id: str, request: Request):
    """Anonymous counterpart to /advocates/{id}/profile — founder direction
    (2026-08) is that a full counsel profile is viewable by anyone, logged in
    or not; only booking (POST /hearing-requests) needs an account. Same
    per-IP ceiling as /public/proxy-counsels, since this is reachable with no
    login either."""
    import counsel_matching
    client_ip = request.client.host if request.client else "unknown"
    counsel_matching.check_public_list_rate_limit(client_ip)
    return await _advocate_profile_or_404(advocate_id)


@api_router.get("/advocates/{advocate_id}/profile")
async def get_advocate_profile(advocate_id: str, user=Depends(get_current_user)):
    """Authenticated profile lookup — kept for any logged-in caller with
    can_hire_proxy_counsel; anonymous visitors use /public/proxy-counsels/
    {id}/profile above instead, which returns the same shape."""
    _require_capability(user, "can_hire_proxy_counsel")
    return await _advocate_profile_or_404(advocate_id)


# ============================================================================
# HEARING REQUESTS — the "Hire Proxy Counsel" marketplace. First-class
# entity (see hearings.py's module docstring for why it doesn't reuse orders).
# Payment/escrow is a separate concern (escrow.py) — endpoints below call
# both modules but neither module reaches into the other's state.
# ============================================================================
import hearings as hearings_svc
import escrow as escrow_svc

async def _notify_hearing_event(user_id: str, title: str, body: str, hearing_id: str) -> None:
    """Fire-and-forget in-app + SMS/WhatsApp/email notification for a hearing
    lifecycle event — same try/except-log, non-fatal pattern as every other
    notify() call site in this file."""
    try:
        from notifications import notify, record_notification_event, get_hearing_email_thread
        recipient = await db.users.find_one({"user_id": user_id})
        if not recipient:
            return
        ctx = {"title": title, "body": body}
        if recipient.get("email"):
            ctx["hearing_thread"] = await get_hearing_email_thread(
                db, hearing_id, recipient["email"], f"CourtBazaar — Your Proxy Counsel Hearing (Ref: {hearing_id})",
            )
        notify(recipient, "hearing_event", ctx)
        await record_notification_event(db, user_id, "hearing_event", title, body, "hearing", hearing_id)
    except Exception as e:
        logger.error(f"hearing notify error: {e}")

@api_router.post("/hearing-requests")
async def create_hearing_request(payload: HearingRequestCreate, user=Depends(get_current_user)):
    _require_capability(user, "can_hire_proxy_counsel")
    hearing = await hearings_svc.create_hearing_request(
        db, user["user_id"], payload.court_id, payload.hearing_date, payload.case_details, payload.fee,
        payload.matter_id, payload.target_advocate_id, payload.service_type, payload.request_details,
    )
    if hearing.get("target_advocate_id"):
        if payload.fee:
            # Hiring-flow simplification: a fee typed on the intake form used
            # to just sit on the hearing record — the requester still had to
            # separately open Negotiation and click "Propose Offer" for that
            # same number before the counsel could act on anything. Auto-
            # creating that first offer here (reusing propose_offer verbatim,
            # no new negotiation logic) means the counsel always has a real,
            # respondable offer the moment they open the request. Its own
            # "New offer" notification is the only ping for this — deliberately
            # not ALSO sending "New hearing request" below for the same event.
            import negotiation as negotiation_svc
            await negotiation_svc.propose_offer(db, hearing["hearing_id"], user, payload.fee, None)
        else:
            await _notify_hearing_event(hearing["target_advocate_id"], "New hearing request",
                                         f"You've been requested for a hearing at {hearing['court_id']}. Open Negotiation to respond.",
                                         hearing["hearing_id"])
    return hearing

@api_router.get("/hearing-requests")
async def list_hearing_requests(user=Depends(get_current_user)):
    return await hearings_svc.list_hearing_requests(db, user)

@api_router.get("/hearing-requests/{hearing_id}")
async def get_hearing_request(hearing_id: str, user=Depends(get_current_user)):
    return await hearings_svc.get_hearing_request(db, hearing_id, user)

@api_router.put("/hearing-requests/{hearing_id}/accept")
async def accept_hearing_request(hearing_id: str, user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    hearing = await hearings_svc.accept_hearing_request(db, hearing_id, user)
    # M6 reorder: payment already happened before acceptance now — no more
    # "proceed to payment" prompt.
    await _notify_hearing_event(hearing["requesting_user_id"], "Request accepted",
                                 f"Your hearing request for {hearing['court_id']} was accepted.",
                                 hearing_id)
    return hearing

@api_router.put("/hearing-requests/{hearing_id}/case-details")
async def submit_hearing_case_details(hearing_id: str, payload: HearingCaseDetailsUpdate, user=Depends(get_current_user)):
    """BlaBlaCar-style flow: the requester fills this in once payment is
    confirmed — see hearings.submit_case_details for the gate."""
    return await hearings_svc.submit_case_details(db, hearing_id, user, payload.model_dump(exclude_none=True))

@api_router.put("/hearing-requests/{hearing_id}/decline")
async def decline_hearing_request(hearing_id: str, user=Depends(get_current_user)):
    _require_capability(user, "can_practice_proxy_counsel")
    return await hearings_svc.decline_hearing_request(db, hearing_id, user)

@api_router.put("/hearing-requests/{hearing_id}/reject")
async def reject_hearing_request(hearing_id: str, user=Depends(get_current_user)):
    """Targeted requests only — a global, terminal reject. Broadcast requests
    use /decline (personal, non-terminal) instead — see hearings.py."""
    _require_capability(user, "can_practice_proxy_counsel")
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.reject_hearing_request(db, hearing_id, user)
    await _notify_hearing_event(hearing["requesting_user_id"], "Request declined",
                                 f"Your hearing request for {hearing['court_id']} was declined by the advocate.",
                                 hearing_id)
    return result

@api_router.put("/hearing-requests/{hearing_id}/cancel")
async def cancel_hearing_request(hearing_id: str, user=Depends(get_current_user)):
    # Notification audit (production readiness pass): the counter-party
    # (whoever isn't the one cancelling) previously learned about a
    # cancelled hearing only by noticing it themselves — no notify call
    # existed here at all. `hearing` here is the pre-cancel snapshot, so its
    # `status` is exactly what hearings.cancel_hearing_request's own
    # _CANCEL_REQUIRES_REFUND check uses to decide whether escrow gets
    # refunded — reusing that same set rather than guessing separately.
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.cancel_hearing_request(db, hearing_id, user)
    recipient_id = hearing.get("proxy_counsel_user_id") or hearing.get("target_advocate_id")
    if recipient_id:
        refunded = hearing["status"] in hearings_svc.CANCEL_REQUIRES_REFUND
        await _notify_hearing_event(
            recipient_id, "Hearing cancelled",
            f"The hearing at {hearing['court_id']} was cancelled by the requester."
            + (" Any escrow held has been refunded." if refunded else ""),
            hearing_id,
        )
    return result

@api_router.post("/hearing-requests/{hearing_id}/payment/create-order")
async def create_hearing_payment_order(hearing_id: str, user=Depends(get_current_user)):
    import razorpay_svc
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    await hearings_svc.initiate_payment(db, hearing_id, user)
    rzp = razorpay_svc.create_order(hearing["fee"], hearing_id, notes={"hearing_id": hearing_id, "user_id": user["user_id"]})
    await db.payment_transactions.insert_one({
        "session_id": rzp["razorpay_order_id"],
        "razorpay_order_id": rzp["razorpay_order_id"],
        "context_type": "hearing", "context_id": hearing_id,
        "user_id": user["user_id"],
        "amount": hearing["fee"],
        "currency": "INR",
        "gateway": "razorpay",
        "status": "initiated",
        "payment_status": "pending",
        "simulated": rzp.get("simulated", False),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return rzp

@api_router.post("/hearing-requests/{hearing_id}/payment/verify")
async def verify_hearing_payment(hearing_id: str, payload: dict, user=Depends(get_current_user)):
    import razorpay_svc
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    if hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester can verify payment for this hearing")
    rzp_order_id = payload.get("razorpay_order_id")
    rzp_payment_id = payload.get("razorpay_payment_id") or f"pay_sim_{uuid.uuid4().hex[:14]}"
    rzp_signature = payload.get("razorpay_signature") or "simulated"
    if not razorpay_svc.verify_payment(rzp_order_id, rzp_payment_id, rzp_signature):
        raise HTTPException(400, "Payment verification failed")
    tx = await db.payment_transactions.find_one({"razorpay_order_id": rzp_order_id, "context_type": "hearing", "context_id": hearing_id})
    if not tx:
        raise HTTPException(404, "Payment transaction not found")
    await db.payment_transactions.update_one(
        {"razorpay_order_id": rzp_order_id},
        {"$set": {"payment_status": "paid", "status": "complete", "razorpay_payment_id": rzp_payment_id}},
    )
    # M6 reorder: payment now happens before anyone accepts, so
    # proxy_counsel_user_id is still None here — escrow.create_and_hold's
    # deferred-payee path (M2) holds the funds unassigned; M12's
    # accept_hearing_request extension is what calls assign_payee later.
    await escrow_svc.create_and_hold(
        db, context_type="hearing", context_id=hearing_id, service_id=hearings_svc.ESCROW_SERVICE_ID,
        matter_id=hearing.get("matter_id"), payer_user_id=user["user_id"], payee_user_id=hearing["proxy_counsel_user_id"],
        amount=hearing["fee"], platform_commission_pct=PLATFORM_COMMISSION_PCT,
        razorpay_order_id=rzp_order_id, razorpay_payment_id=rzp_payment_id,
    )
    await hearings_svc.mark_payment_confirmed(db, hearing_id, user)
    # Targeted advocate is now notified at request-creation time (see
    # create_hearing_request above) — by the time payment is verified here,
    # negotiation has already been agreed, so this is a payment-confirmation
    # notice, not the first the advocate hears of the request. Broadcast-to-
    # all requests have no single recipient to notify at this point (same as
    # before) — that's the Counsel Matching Agent's job (M11, not built yet).
    if hearing.get("target_advocate_id"):
        await _notify_hearing_event(hearing["target_advocate_id"], "Payment received",
                                     f"Payment for your hearing at {hearing['court_id']} is confirmed and held in escrow.",
                                     hearing_id)
    # Notification audit (production readiness pass): the requester who just
    # paid previously got nothing durable — only an ephemeral client-side
    # toast, lost on refresh/different device. They get their own receipt too.
    await _notify_hearing_event(user["user_id"], "Payment successful",
                                 f"Your payment for the hearing at {hearing['court_id']} is confirmed and held securely in escrow.",
                                 hearing_id)
    return {"ok": True, "payment_id": rzp_payment_id, "status": "broadcast"}

@api_router.get("/hearing-requests/{hearing_id}/escrow")
async def get_hearing_escrow(hearing_id: str, user=Depends(get_current_user)):
    """Read-only — escrow amount/commission/payout for one hearing, used by
    the requester/advocate's own detail view and the admin verification
    queue (see escrow_svc.get_for_context)."""
    await hearings_svc.get_hearing_request(db, hearing_id, user)  # visibility check
    return await escrow_svc.get_for_context(db, "hearing", hearing_id)

@api_router.put("/hearing-requests/{hearing_id}/mark-conducted")
async def mark_hearing_conducted(hearing_id: str, user=Depends(get_current_user)):
    return await hearings_svc.mark_hearing_conducted(db, hearing_id, user)

@api_router.post("/hearing-requests/{hearing_id}/rate")
async def rate_hearing_request(hearing_id: str, payload: HearingRatingCreate, user=Depends(get_current_user)):
    # Notification audit (production readiness pass): the rated party
    # previously had no way to learn a rating landed except by opening the
    # hearing themselves.
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.rate_hearing_request(db, hearing_id, user, payload.rating, payload.review)
    is_requester = user["user_id"] == hearing["requesting_user_id"]
    rated_user_id = hearing.get("proxy_counsel_user_id") if is_requester else hearing["requesting_user_id"]
    if rated_user_id:
        await _notify_hearing_event(rated_user_id, "Rating received",
                                     f"You received a {payload.rating}-star rating for the hearing at {hearing['court_id']}.",
                                     hearing_id)
    return result

@api_router.post("/hearing-requests/{hearing_id}/notes")
async def add_hearing_note(hearing_id: str, payload: HearingNoteCreate, user=Depends(get_current_user)):
    return await hearings_svc.add_note(db, hearing_id, user, payload.note)

@api_router.get("/hearing-requests/{hearing_id}/messages")
async def list_hearing_messages(hearing_id: str, user=Depends(get_current_user)):
    await hearings_svc.get_hearing_request(db, hearing_id, user)  # visibility check
    return await hearings_svc.list_messages(db, hearing_id)

@api_router.post("/hearing-requests/{hearing_id}/messages")
async def post_hearing_message(hearing_id: str, payload: HearingMessageCreate, user=Depends(get_current_user)):
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)  # visibility check
    message = await hearings_svc.add_message(db, hearing_id, user, payload.text)
    preview = payload.text if len(payload.text) <= 120 else f"{payload.text[:117]}..."
    for recipient_id in hearings_svc.other_participant_ids(hearing, user["user_id"]):
        await _notify_hearing_event(recipient_id, f"New message from {user.get('name') or 'a participant'}",
                                     preview, hearing_id)
    return message

# ----------------------------------------------------------------------
# Negotiation Module — offer/counter-offer/agreement state (negotiation.py).
# Chat itself is the messages endpoints above, unchanged; the frontend
# merges the two into one feed. See negotiation.py's module docstring.
# ----------------------------------------------------------------------
@api_router.get("/hearing-requests/{hearing_id}/negotiation")
async def get_negotiation(hearing_id: str, user=Depends(get_current_user)):
    import negotiation as negotiation_svc
    return await negotiation_svc.get_negotiation_for_user(db, hearing_id, user)

@api_router.post("/hearing-requests/{hearing_id}/negotiation/offers")
async def propose_negotiation_offer(hearing_id: str, payload: NegotiationOfferCreate, user=Depends(get_current_user)):
    import negotiation as negotiation_svc
    return await negotiation_svc.propose_offer(db, hearing_id, user, payload.amount, payload.note)

@api_router.post("/hearing-requests/{hearing_id}/negotiation/offers/{offer_id}/accept")
async def accept_negotiation_offer(hearing_id: str, offer_id: str, user=Depends(get_current_user)):
    import negotiation as negotiation_svc
    return await negotiation_svc.accept_offer(db, hearing_id, offer_id, user)

@api_router.put("/hearing-requests/{hearing_id}/end-negotiation")
async def end_hearing_negotiation(hearing_id: str, user=Depends(get_current_user)):
    """Distinct from /cancel — closes the negotiation with the current
    targeted advocate without the requester meaning to abandon the request
    itself (see hearings.end_negotiation's docstring for why this can't just
    retarget the same hearing_id)."""
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.end_negotiation(db, hearing_id, user)
    await _notify_hearing_event(hearing["target_advocate_id"], "Negotiation ended",
                                 f"The requester ended negotiation for the hearing at {hearing['court_id']} and is selecting a different counsel.",
                                 hearing_id)
    return result

@api_router.get("/hearing-requests/{hearing_id}/counsel-profile")
async def get_hearing_counsel_profile(hearing_id: str, user=Depends(get_current_user)):
    """Fallback for NegotiationModule.jsx when location.state?.counsel is
    absent (page refresh, direct/shared link) — same card shape
    recommendations_advocates returns, built for the one advocate targeted
    on this hearing rather than a ranked list."""
    import negotiation as negotiation_svc
    import counsel_matching
    hearing = await db.hearing_requests.find_one({"hearing_id": hearing_id}, {"_id": 0})
    if not hearing:
        raise HTTPException(404, "Hearing request not found")
    negotiation_svc._check_negotiation_participant(hearing, user)
    advocate_id = hearing.get("target_advocate_id")
    if not advocate_id:
        raise HTTPException(404, "This hearing has no targeted advocate")
    profile = await db.proxy_counsel_profiles.find_one({"user_id": advocate_id}, {"_id": 0})
    if not profile:
        raise HTTPException(404, "Counsel profile not found")
    name_doc = await db.users.find_one({"user_id": advocate_id}, {"_id": 0, "name": 1})
    court_ids = profile.get("courts") or []
    court_names_by_id = {
        c["court_id"]: c["name"]
        for c in (await db.courts.find({"court_id": {"$in": court_ids}}, {"_id": 0, "court_id": 1, "name": 1}).to_list(len(court_ids)) if court_ids else [])
    }
    return counsel_matching.build_advocate_card(profile, name_doc.get("name") if name_doc else None, court_names_by_id)

@api_router.get("/hearing-requests/{hearing_id}/documents")
async def get_hearing_documents(hearing_id: str, user=Depends(get_current_user)):
    await hearings_svc.get_hearing_request(db, hearing_id, user)  # visibility check
    return await hearings_svc.list_documents(db, hearing_id)

@api_router.post("/hearing-requests/{hearing_id}/documents")
async def upload_hearing_document(
    hearing_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.add_document(
        db, put_object, validate_upload, hearing_id, user, kind, file.filename, content_type, data,
    )
    # Notification audit (production readiness pass): an uploaded order
    # sheet used to notify nobody — the requester only found out a
    # submission was waiting by opening the hearing themselves (or, after
    # 3 days of *not* uploading, the reminder scheduler — the opposite
    # event). Case-document shares aren't in scope here; only the order
    # sheet transition (hearing_completed -> verification_pending) needs
    # the requester's attention.
    if kind == "order_sheet":
        await _notify_hearing_event(hearing["requesting_user_id"], "Order sheet uploaded",
                                     f"The Court Order Sheet for your hearing at {hearing['court_id']} was uploaded and is awaiting your verification.",
                                     hearing_id)
    return result

@api_router.get("/hearing-requests/{hearing_id}/documents/{doc_id}/download-url")
async def get_hearing_document_url(hearing_id: str, doc_id: str, inline: bool = False, user=Depends(get_current_user)):
    await hearings_svc.get_hearing_request(db, hearing_id, user)  # visibility check
    rec = await db.hearing_documents.find_one({"doc_id": doc_id, "hearing_id": hearing_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Document not found")
    # inline=true (Preview button): browser renders the file in-tab instead
    # of prompting a download — see storage.presigned_download_url.
    url = presigned_download_url(rec["storage_path"], filename=rec.get("original_filename"), inline=inline)
    return {"url": url, "filename": rec.get("original_filename")}


# ----------------------------------------------------------------------
# Admin hearing verification — Verify and Release Payout are always two
# separate, explicitly-triggered endpoints (never bundled into one call),
# per the founder's ask to reduce operational mistakes.
# ----------------------------------------------------------------------
@api_router.get("/admin/hearing-requests")
async def admin_list_hearing_requests(user=Depends(get_current_user), status: Optional[str] = None,
                                       escalated: Optional[bool] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    if escalated:
        # Escalation lives on counsel_matching_log.status, not hearing_requests.status
        # (see counsel_matching.escalate_to_admin) — cross-reference the two collections
        # rather than adding a query hearings_svc.list_hearings_for_admin doesn't support.
        escalated_sessions = await db.counsel_matching_log.find({"status": "escalated"}, {"_id": 0}).to_list(500)
        hearings_by_id = {
            h["hearing_id"]: h for h in await db.hearing_requests.find(
                {"hearing_id": {"$in": [s["hearing_id"] for s in escalated_sessions]}}, {"_id": 0},
            ).to_list(500)
        }
        results = []
        for session in escalated_sessions:
            hearing = hearings_by_id.get(session["hearing_id"])
            if hearing:
                results.append({**hearing, "escalation_reason": session.get("final_decision")})
        return results
    return await hearings_svc.list_hearings_for_admin(db, status)

@api_router.post("/admin/hearing-requests/{hearing_id}/assign")
async def admin_assign_hearing_counsel(hearing_id: str, payload: AdminAssignCounsel, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    import counsel_matching
    return await counsel_matching.admin_assign_counsel(db, hearing_id, payload.counsel_user_id, user)

@api_router.put("/hearing-requests/{hearing_id}/verify")
async def verify_hearing_order_sheet(hearing_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.verify_order_sheet(db, hearing_id, user)
    await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Order sheet verified",
                                 f"Your order sheet for the {hearing['court_id']} hearing was verified. Payout release is next.",
                                 hearing_id)
    return result

@api_router.put("/hearing-requests/{hearing_id}/verify-and-release")
async def verify_and_release_hearing_payout(hearing_id: str, user=Depends(get_current_user)):
    """Escrow Module: the Hiring Advocate's one-click "Verify Hearing" —
    founder's explicit call (rule 8) that verify+release happen as a single
    action for this actor, unlike admin's own /verify and /release-payout
    above, which stay deliberately separate and untouched. Requester-only;
    see hearings.verify_and_release_payout's own guard for the 403."""
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.verify_and_release_payout(db, hearing_id, user)
    await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Payout released",
                                 f"Your hearing at {hearing['court_id']} was verified and your payout has been released to your wallet.",
                                 hearing_id)
    # Notification audit (production readiness pass): a durable receipt for
    # the requester's own action, same reasoning as "Payment successful"
    # above — they know they just clicked Verify, but nothing durable
    # confirmed the escrow actually released until now.
    await _notify_hearing_event(hearing["requesting_user_id"], "Escrow released",
                                 f"You verified the hearing at {hearing['court_id']} and escrow has been released to the Proxy Counsel.",
                                 hearing_id)
    return result

@api_router.put("/hearing-requests/{hearing_id}/reject-verification")
async def reject_hearing_order_sheet(hearing_id: str, payload: HearingVerificationReject, user=Depends(get_current_user)):
    # Escrow Module: disputes are now initiated by the Hiring Advocate
    # ("Raise Dispute" on the Negotiation page), not just admin — the only
    # change from before. Once disputed, routing is unchanged: it lands in
    # the same admin dispute queue (resolve_dispute below), same
    # resubmit/refund outcomes, no new admin surface.
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    if user["role"] != "admin" and hearing["requesting_user_id"] != user["user_id"]:
        raise HTTPException(403, "Only the requester or an admin can dispute this hearing's order sheet")
    result = await hearings_svc.reject_order_sheet(db, hearing_id, user, payload.remark)
    await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Order sheet disputed",
                                 f"Your order sheet for the {hearing['court_id']} hearing was disputed and is now under admin review.",
                                 hearing_id)
    return result

@api_router.put("/hearing-requests/{hearing_id}/resolve-dispute")
async def resolve_hearing_dispute(hearing_id: str, payload: HearingDisputeResolve, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    # Notification audit (production readiness pass): neither outcome
    # notified anyone — a resubmission request left the counsel unaware they
    # needed to re-upload, and a refund left the requester unaware their
    # money was back and the counsel unaware why no payout is coming.
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.resolve_dispute(db, hearing_id, user, payload.action, payload.remark)
    if payload.action == "resubmit":
        await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Resubmission requested",
                                     f"Admin has asked for a corrected Court Order Sheet for the hearing at {hearing['court_id']}. Please re-upload."
                                     + (f" Note: {payload.remark}" if payload.remark else ""),
                                     hearing_id)
    else:
        await _notify_hearing_event(hearing["requesting_user_id"], "Refund issued",
                                     f"Your dispute for the hearing at {hearing['court_id']} was resolved with a refund."
                                     + (f" Note: {payload.remark}" if payload.remark else ""),
                                     hearing_id)
        await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Dispute resolved — no payout",
                                     f"The dispute for the hearing at {hearing['court_id']} was resolved in the requester's favor; the escrowed amount was refunded to them.",
                                     hearing_id)
    return result

@api_router.put("/hearing-requests/{hearing_id}/release-payout")
async def release_hearing_payout(hearing_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    hearing = await hearings_svc.get_hearing_request(db, hearing_id, user)
    result = await hearings_svc.release_hearing_payout(db, hearing_id, user)
    await _notify_hearing_event(hearing["proxy_counsel_user_id"], "Payout released",
                                 f"Your payout for the {hearing['court_id']} hearing has been released to your wallet.",
                                 hearing_id)
    # Notification audit (production readiness pass): the requester's hearing
    # is now fully complete — they get their own closing confirmation too,
    # same as the requester-triggered verify-and-release path already does.
    await _notify_hearing_event(hearing["requesting_user_id"], "Escrow released",
                                 f"Escrow for your hearing at {hearing['court_id']} has been released to the Proxy Counsel. This request is now complete.",
                                 hearing_id)
    return result


# ============================================================================
# ADMIN: PAYMENT RECONCILIATION (Stripe ↔ Razorpay)
# ============================================================================
@api_router.get("/admin/reconciliation")
async def admin_reconciliation(
    user=Depends(get_current_user),
    gateway: Optional[str] = None,
    status_filter: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    q: Dict[str, Any] = {}
    if gateway:
        q["gateway"] = gateway
    if status_filter:
        q["payment_status"] = status_filter
    if from_date or to_date:
        q["created_at"] = {}
        if from_date:
            q["created_at"]["$gte"] = from_date
        if to_date:
            q["created_at"]["$lte"] = to_date

    txns = await db.payment_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    order_ids = list({t.get("order_id") for t in txns if t.get("order_id")})
    orders_map = {}
    if order_ids:
        async for o in db.orders.find({"order_id": {"$in": order_ids}}, {"_id": 0, "order_id": 1, "payment_status": 1, "pricing.total": 1, "status": 1}):
            orders_map[o["order_id"]] = o

    rows = []
    stripe_paid = stripe_pending = stripe_failed = 0
    rzp_paid = rzp_pending = rzp_failed = 0
    stripe_paid_amt = rzp_paid_amt = 0.0
    mismatches = []

    for t in txns:
        gw = t.get("gateway") or ("razorpay" if t.get("razorpay_order_id") else "stripe")
        amt = float(t.get("amount", 0))
        pstatus = t.get("payment_status", "pending")
        order = orders_map.get(t.get("order_id"))
        order_pstatus = order.get("payment_status") if order else None
        mismatch = False
        mismatch_reason = None
        if order and order_pstatus and pstatus != order_pstatus:
            mismatch = True
            mismatch_reason = f"Txn={pstatus}, Order={order_pstatus}"
            mismatches.append({"session_id": t.get("session_id"), "order_id": t.get("order_id"), "reason": mismatch_reason})
        if gw == "stripe":
            if pstatus == "paid":
                stripe_paid += 1
                stripe_paid_amt += amt
            elif pstatus == "pending":
                stripe_pending += 1
            else:
                stripe_failed += 1
        else:
            if pstatus == "paid":
                rzp_paid += 1
                rzp_paid_amt += amt
            elif pstatus == "pending":
                rzp_pending += 1
            else:
                rzp_failed += 1
        rows.append({
            "session_id": t.get("session_id"),
            "razorpay_order_id": t.get("razorpay_order_id"),
            "razorpay_payment_id": t.get("razorpay_payment_id"),
            "gateway": gw,
            "order_id": t.get("order_id"),
            "user_id": t.get("user_id"),
            "amount": amt,
            "currency": t.get("currency", "inr"),
            "payment_status": pstatus,
            "order_payment_status": order_pstatus,
            "order_status": order.get("status") if order else None,
            "simulated": t.get("simulated", False),
            "created_at": t.get("created_at"),
            "mismatch": mismatch,
            "mismatch_reason": mismatch_reason,
        })

    return {
        "rows": rows,
        "totals": {
            "stripe": {"paid": stripe_paid, "pending": stripe_pending, "failed": stripe_failed, "paid_amount": round(stripe_paid_amt, 2)},
            "razorpay": {"paid": rzp_paid, "pending": rzp_pending, "failed": rzp_failed, "paid_amount": round(rzp_paid_amt, 2)},
            "grand_total_paid": round(stripe_paid_amt + rzp_paid_amt, 2),
            "transaction_count": len(rows),
        },
        "mismatches": mismatches,
    }


@api_router.get("/admin/reconciliation/export")
async def admin_reconciliation_csv(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    import csv
    import io as _io
    txns = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["session_id", "gateway", "order_id", "user_id", "amount", "currency", "payment_status", "simulated", "created_at"])
    for t in txns:
        gw = t.get("gateway") or ("razorpay" if t.get("razorpay_order_id") else "stripe")
        w.writerow([t.get("session_id"), gw, t.get("order_id"), t.get("user_id"), t.get("amount"), t.get("currency", "inr"), t.get("payment_status"), t.get("simulated", False), t.get("created_at")])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=courtbazaar-reconciliation.csv"})


# ============================================================================
# ADMIN: WHATSAPP TEMPLATE APPROVAL WORKFLOW
# ============================================================================
class WhatsAppTemplate(BaseModel):
    name: str
    category: Literal["transactional", "marketing", "otp", "utility"]
    language: str = "en"
    body: str
    variables: List[str] = []
    description: Optional[str] = None


@api_router.get("/admin/whatsapp-templates")
async def list_wa_templates(user=Depends(get_current_user), status_filter: Optional[str] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    if await db.whatsapp_templates.count_documents({}) == 0:
        defaults = [
            {"template_id": f"wat_{uuid.uuid4().hex[:10]}", "name": "order_placed_v1", "category": "transactional", "language": "en", "body": "Hi {{1}}, your CourtBazaar order {{2}} for {{3}} has been placed. Total Rs.{{4}}. Track at courtbazaar.com", "variables": ["name", "order_id", "court", "amount"], "status": "approved", "twilio_sid": None, "description": "Order placement confirmation", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user["user_id"], "history": []},
            {"template_id": f"wat_{uuid.uuid4().hex[:10]}", "name": "order_status_v1", "category": "transactional", "language": "en", "body": "Hi {{1}}, order {{2}} is now {{3}}. Vendor: {{4}}. Track live at courtbazaar.com", "variables": ["name", "order_id", "status", "vendor"], "status": "approved", "twilio_sid": None, "description": "Order status change", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user["user_id"], "history": []},
            {"template_id": f"wat_{uuid.uuid4().hex[:10]}", "name": "otp_login_v1", "category": "otp", "language": "en", "body": "Your CourtBazaar OTP is {{1}}. Valid for 5 minutes. Do not share.", "variables": ["otp"], "status": "pending", "twilio_sid": None, "description": "Login OTP", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user["user_id"], "history": []},
            {"template_id": f"wat_{uuid.uuid4().hex[:10]}", "name": "delivery_otp_v1", "category": "transactional", "language": "en", "body": "Delivery OTP for order {{1}} is {{2}}. Share only with the delivery partner.", "variables": ["order_id", "otp"], "status": "draft", "twilio_sid": None, "description": "Delivery confirmation OTP", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user["user_id"], "history": []},
        ]
        for t in defaults:
            await db.whatsapp_templates.insert_one(t)
    q = {}
    if status_filter:
        q["status"] = status_filter
    tmpls = await db.whatsapp_templates.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return tmpls


@api_router.post("/admin/whatsapp-templates")
async def create_wa_template(payload: WhatsAppTemplate, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    doc = {
        "template_id": f"wat_{uuid.uuid4().hex[:10]}",
        **payload.model_dump(),
        "status": "draft",
        "twilio_sid": None,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "history": [{"action": "created", "by": user["name"], "at": datetime.now(timezone.utc).isoformat()}],
    }
    await db.whatsapp_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/admin/whatsapp-templates/{template_id}/submit")
async def submit_wa_template(template_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    t = await db.whatsapp_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    if t["status"] != "draft":
        raise HTTPException(400, f"Template already {t['status']}")
    twilio_sid = None
    try:
        from notifications import is_whatsapp_enabled
        if is_whatsapp_enabled():
            twilio_sid = f"HX_pending_{uuid.uuid4().hex[:14]}"
    except Exception:
        pass
    await db.whatsapp_templates.update_one(
        {"template_id": template_id},
        {"$set": {"status": "pending", "twilio_sid": twilio_sid, "submitted_at": datetime.now(timezone.utc).isoformat()},
         "$push": {"history": {"action": "submitted_for_approval", "by": user["name"], "at": datetime.now(timezone.utc).isoformat()}}},
    )
    return {"ok": True, "status": "pending", "twilio_sid": twilio_sid}


@api_router.post("/admin/whatsapp-templates/{template_id}/approve")
async def approve_wa_template(template_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    await db.whatsapp_templates.update_one(
        {"template_id": template_id},
        {"$set": {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "approved_by": user["name"]},
         "$push": {"history": {"action": "approved", "by": user["name"], "at": datetime.now(timezone.utc).isoformat()}}},
    )
    return {"ok": True, "status": "approved"}


@api_router.post("/admin/whatsapp-templates/{template_id}/reject")
async def reject_wa_template(template_id: str, payload: dict, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    reason = payload.get("reason", "Not specified")
    await db.whatsapp_templates.update_one(
        {"template_id": template_id},
        {"$set": {"status": "rejected", "rejection_reason": reason},
         "$push": {"history": {"action": "rejected", "reason": reason, "by": user["name"], "at": datetime.now(timezone.utc).isoformat()}}},
    )
    return {"ok": True, "status": "rejected"}


@api_router.delete("/admin/whatsapp-templates/{template_id}")
async def delete_wa_template(template_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    await db.whatsapp_templates.delete_one({"template_id": template_id})
    return {"ok": True}



# ============================================================================
# BULK ORDER CSV IMPORT (for Law Firms - matter-wise batching)
# ============================================================================
@api_router.get("/firms/bulk-import/template")
async def bulk_import_template(user=Depends(get_current_user)):
    """Return CSV template for bulk order import."""
    import csv
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["matter_name", "service_ids", "qty_each", "court_id", "delivery_option", "urgent", "delivery_address", "notes"])
    w.writerow(["Sharma v. State - WP 1234/2026", "svc_bw_photocopy;svc_spiral_binding", "200;1", "court_delhi_hc", "chamber", "false", "Chamber 42, Delhi HC", "Court bundle for hearing 15 Mar"])
    w.writerow(["Mehta Properties - LPA 567/2026", "svc_efile_hc;svc_court_bundle;svc_hard_binding", "1;1;3", "court_delhi_hc", "court", "true", "", "Urgent - file before 11 AM"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=courtbazaar-bulk-template.csv"},
    )


@api_router.post("/firms/bulk-import")
async def firm_bulk_import(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload CSV -> create one order per row (matter), all tagged with same firm_id."""

    if not user.get("firm_id"):
        raise HTTPException(400, "Bulk import is available for law-firm accounts only. Create or join a firm first.")
    if user.get("firm_role") not in ("owner", "partner"):
        raise HTTPException(403, "Only firm owner/partner can bulk-import orders")
    import csv
    import io as _io
    raw = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(_io.StringIO(raw))
    success, errors = [], []
    for idx, row in enumerate(reader, start=2):
        try:
            matter = (row.get("matter_name") or "").strip()
            court_id = (row.get("court_id") or "").strip()
            delivery = (row.get("delivery_option") or "chamber").strip().lower()
            urgent = (row.get("urgent") or "").strip().lower() in ("true", "yes", "1", "y")
            svc_ids = [s.strip() for s in (row.get("service_ids") or "").split(";") if s.strip()]
            qtys = [int(q.strip()) for q in (row.get("qty_each") or "").split(";") if q.strip()]
            if not svc_ids or not court_id:
                errors.append({"row": idx, "matter": matter, "error": "service_ids and court_id required"})
                continue
            if len(qtys) != len(svc_ids):
                qtys = [1] * len(svc_ids)
            court_info = await db.courts.find_one({"court_id": court_id}, {"_id": 0})
            if not court_info:
                errors.append({"row": idx, "matter": matter, "error": f"court_id '{court_id}' not found"})
                continue
            if court_info.get("serviceable") is False:
                errors.append({"row": idx, "matter": matter, "error": f"court '{court_info['name']}' not yet serviceable"})
                continue
            services = [{"service_id": s, "qty": qtys[i]} for i, s in enumerate(svc_ids)]
            pricing = await calculate_pricing(services, court_id, delivery, urgent)
            candidates = await db.vendors.find({"court_ids": court_id, "kyc_status": "approved"}, {"_id": 0}).to_list(20)
            candidates.sort(key=lambda v: (not v.get("sponsored", False), -float(v.get("rating", 0))))
            vendor = candidates[0] if candidates else None
            order_id = f"ORD{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"
            order = {
                "order_id": order_id, "user_id": user["user_id"], "user_name": user.get("name"),
                "user_phone": user.get("phone"), "firm_id": user["firm_id"],
                "matter_id": f"matter_{uuid.uuid4().hex[:8]}", "matter_name": matter,
                "services": services, "state_id": court_info.get("state_id"), "court_id": court_id,
                "court_name": court_info["name"], "state_name": court_info.get("state_name"),
                "delivery_option": delivery, "delivery_address": (row.get("delivery_address") or "").strip(),
                "file_ids": [], "urgent": urgent, "notes": (row.get("notes") or "").strip(),
                "pricing": pricing,
                "vendor_id": vendor["vendor_id"] if vendor else None,
                "vendor_name": vendor["shop_name"] if vendor else None,
                "vendor_sponsored": vendor.get("sponsored", False) if vendor else False,
                "status": "placed", "payment_status": "pending", "source": "bulk_csv",
                "timeline": [{"status": "placed", "at": datetime.now(timezone.utc).isoformat(), "note": f"Bulk import (matter: {matter})"}],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.orders.insert_one(order)
            success.append({"row": idx, "order_id": order_id, "matter": matter, "total": pricing["total"]})
        except Exception as e:
            errors.append({"row": idx, "matter": row.get("matter_name", ""), "error": str(e)})
    try:
        from audit_log import log_audit
        await log_audit(db, "order.bulk_import", user, {"success_count": len(success), "error_count": len(errors), "firm_id": user["firm_id"]})
    except Exception:
        pass
    return {"success": success, "errors": errors, "total_rows": len(success) + len(errors),
            "total_amount": round(sum(s["total"] for s in success), 2)}


# ============================================================================
# AUDIT LOG + DPDP COMPLIANCE
# ============================================================================
@api_router.get("/admin/audit-log")
async def admin_audit_log(user=Depends(get_current_user), action: Optional[str] = None,
                          user_id: Optional[str] = None, limit: int = 200):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    q: Dict[str, Any] = {}
    if action:
        q["action"] = action
    if user_id:
        q["user_id"] = user_id
    entries = await db.audit_log.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    # Distinct actions for filter
    actions = await db.audit_log.distinct("action")
    return {"entries": entries, "actions": sorted(actions)}


@api_router.get("/dpdp/my-data")
async def dpdp_my_data(user=Depends(get_current_user), request: Request = None):
    from audit_log import export_user_data, log_audit
    data = await export_user_data(db, user["user_id"])
    await log_audit(db, "dpdp.data_export", user, {"records": {k: (len(v) if isinstance(v, list) else 1) for k, v in data.items() if k != "exported_at"}}, request)
    return data


@api_router.get("/dpdp/my-data/download")
async def dpdp_my_data_download(user=Depends(get_current_user)):
    import json as _json
    from audit_log import export_user_data
    data = await export_user_data(db, user["user_id"])
    return Response(
        content=_json.dumps(data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=courtbazaar-my-data-{user['user_id']}.json"},
    )


@api_router.post("/dpdp/request-deletion")
async def dpdp_request_deletion(payload: dict, user=Depends(get_current_user), request: Request = None):
    """Request account deletion (DPDP right to erasure)."""
    from audit_log import log_audit
    reason = payload.get("reason", "")
    req_id = f"del_{uuid.uuid4().hex[:12]}"
    await db.dpdp_requests.insert_one({
        "request_id": req_id, "user_id": user["user_id"], "user_email": user["email"],
        "reason": reason, "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await log_audit(db, "dpdp.data_deletion_request", user, {"request_id": req_id, "reason": reason}, request)
    return {"request_id": req_id, "status": "pending",
            "message": "Your deletion request has been recorded. Our team will process within 30 days as per DPDP Act."}


@api_router.get("/admin/dpdp/requests")
async def admin_dpdp_requests(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    reqs = await db.dpdp_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return reqs


@api_router.post("/admin/dpdp/requests/{request_id}/execute")
async def admin_execute_deletion(request_id: str, user=Depends(get_current_user), request: Request = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from audit_log import delete_user_data, log_audit
    req = await db.dpdp_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    result = await delete_user_data(db, req["user_id"])
    await db.dpdp_requests.update_one({"request_id": request_id}, {"$set": {
        "status": "executed", "executed_at": datetime.now(timezone.utc).isoformat(),
        "executed_by": user["user_id"], "result": result,
    }})
    await log_audit(db, "dpdp.data_deletion_executed", user, {"request_id": request_id, "target_user_id": req["user_id"], "result": result}, request)
    return {"ok": True, **result}


@api_router.get("/admin/compliance-report")
async def admin_compliance_report(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    audit_count = await db.audit_log.count_documents({})
    pending_deletions = await db.dpdp_requests.count_documents({"status": "pending"})
    executed_deletions = await db.dpdp_requests.count_documents({"status": "executed"})
    total_users = await db.users.count_documents({})
    deleted_users = await db.users.count_documents({"deleted": True})
    pipeline = [{"$group": {"_id": "$action", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 10}]
    top_actions = []
    async for d in db.audit_log.aggregate(pipeline):
        top_actions.append({"action": d["_id"], "count": d["count"]})
    return {
        "audit_log_entries": audit_count,
        "total_users": total_users,
        "deleted_users": deleted_users,
        "pending_deletion_requests": pending_deletions,
        "executed_deletions": executed_deletions,
        "top_actions": top_actions,
        "dpdp_compliant": True,
        "data_retention_policy_days": 1825,  # 5 years for legal records
    }


# ============================================================================
# VENDOR PERFORMANCE LEADERBOARD + SLA
# ============================================================================
@api_router.get("/admin/leaderboard")
async def admin_leaderboard(user=Depends(get_current_user), limit: int = 50):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from vendor_sla import leaderboard
    return await leaderboard(db, limit)


@api_router.get("/vendors/me/sla")
async def my_vendor_sla(user=Depends(get_current_user)):
    if user["role"] != "vendor":
        raise HTTPException(403, "Vendor only")
    from vendor_sla import compute_vendor_sla, sla_grade
    sla = await compute_vendor_sla(db, user["user_id"])
    sla["grade"] = sla_grade(sla["sla_score"])
    return sla


@api_router.get("/vendors/{vendor_id}/sla")
async def vendor_sla(vendor_id: str, user=Depends(get_current_user)):
    if user["role"] not in ("admin", "vendor") or (user["role"] == "vendor" and user["user_id"] != vendor_id):
        raise HTTPException(403, "Forbidden")
    from vendor_sla import compute_vendor_sla, sla_grade
    sla = await compute_vendor_sla(db, vendor_id)
    sla["grade"] = sla_grade(sla["sla_score"])
    return sla



# ============================================================================
# SUPER ADMIN COMMAND CENTER (consolidated)
# ============================================================================
@api_router.get("/admin/command-center")
async def admin_command_center(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")

    # Revenue split (new schema)
    platform_commission = 0.0
    platform_delivery = 0.0
    platform_convenience = 0.0
    platform_urgent = 0.0
    platform_total = 0.0
    vendor_payout_total = 0.0
    gst_collected = 0.0
    paid_count = 0
    async for o in db.orders.find({"payment_status": "paid"}, {"_id": 0, "pricing": 1}):
        p = o.get("pricing", {})
        sd = p.get("split_details", {})
        platform_commission += sd.get("platform_commission_20pct", p.get("platform_commission", 0))
        platform_delivery += sd.get("platform_delivery_share_50pct", 0)
        platform_convenience += sd.get("convenience_fee_platform", p.get("convenience_fee", 0))
        platform_urgent += sd.get("platform_urgent_share_20pct", 0)
        vendor_payout_total += p.get("vendor_payout", 0)
        gst_collected += p.get("gst", 0)
        paid_count += 1
    platform_total = platform_commission + platform_delivery + platform_convenience + platform_urgent

    # Vendor breakdown by category
    vendor_pipeline = [{"$group": {"_id": "$vendor_category", "count": {"$sum": 1}}}]
    vendor_by_cat = []
    async for d in db.vendors.aggregate(vendor_pipeline):
        vendor_by_cat.append({"category": d["_id"] or "uncategorized", "count": d["count"]})

    # Order pulse - by status
    status_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    status_pulse = []
    async for d in db.orders.aggregate(status_pipeline):
        status_pulse.append({"status": d["_id"], "count": d["count"]})

    # Last 7 days orders
    from datetime import timedelta as _td
    seven_days_ago = (datetime.now(timezone.utc) - _td(days=7)).isoformat()
    recent_orders = await db.orders.count_documents({"created_at": {"$gte": seven_days_ago}})
    recent_paid = await db.orders.count_documents({"created_at": {"$gte": seven_days_ago}, "payment_status": "paid"})

    # User breakdown
    user_pipeline = [{"$group": {"_id": "$role", "count": {"$sum": 1}}}]
    users_by_role = []
    async for d in db.users.aggregate(user_pipeline):
        users_by_role.append({"role": d["_id"], "count": d["count"]})

    # Top sponsored vendors
    sponsored_count = await db.vendors.count_documents({"sponsored": True})
    pending_kyc = await db.vendors.count_documents({"kyc_status": "pending"})
    gst_vendors = await db.vendors.count_documents({"has_gst": True})
    non_gst_vendors = await db.vendors.count_documents({"$or": [{"has_gst": False}, {"has_gst": {"$exists": False}}, {"gst": None}, {"gst": ""}]})

    return {
        "revenue": {
            "platform_total": round(platform_total, 2),
            "platform_commission_20pct": round(platform_commission, 2),
            "platform_delivery_share_50pct": round(platform_delivery, 2),
            "platform_convenience_fee": round(platform_convenience, 2),
            "platform_urgent_share_20pct": round(platform_urgent, 2),
            "vendor_payout_total": round(vendor_payout_total, 2),
            "gst_collected": round(gst_collected, 2),
            "paid_orders": paid_count,
        },
        "orders": {
            "last_7_days": recent_orders,
            "last_7_days_paid": recent_paid,
            "by_status": status_pulse,
            "total": await db.orders.count_documents({}),
        },
        "vendors": {
            "total": await db.vendors.count_documents({}),
            "approved": await db.vendors.count_documents({"kyc_status": "approved"}),
            "pending_kyc": pending_kyc,
            "sponsored": sponsored_count,
            "with_gst": gst_vendors,
            "without_gst": non_gst_vendors,
            "by_category": vendor_by_cat,
        },
        "users": {
            "total": await db.users.count_documents({}),
            "by_role": users_by_role,
        },
        "compliance": {
            "audit_entries": await db.audit_log.count_documents({}),
            "pending_deletions": await db.dpdp_requests.count_documents({"status": "pending"}),
            "deleted_users": await db.users.count_documents({"deleted": True}),
            "files_purged": await db.files.count_documents({"is_deleted": True}),
        },
        "revenue_model": {
            "platform_commission_pct": PLATFORM_COMMISSION_PCT * 100,
            "delivery_split_vendor_pct": DELIVERY_SHARE_VENDOR_PCT * 100,
            "delivery_split_platform_pct": (1 - DELIVERY_SHARE_VENDOR_PCT) * 100,
            "convenience_fee_inr": CONVENIENCE_FEE_FLAT,
            "gst_pct": GST_PCT * 100,
        },
    }


# ============================================================================
# STENOGRAPHER BOOKING (hourly slots)
# ============================================================================
class StenoBooking(BaseModel):
    service_id: str
    stenographer_id: Optional[str] = None  # If null, auto-match
    court_id: str
    state_id: str
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM 24h
    hours: int
    delivery_option: Literal["pickup", "chamber", "court", "digital"] = "court"
    delivery_address: Optional[str] = None
    notes: Optional[str] = None


@api_router.get("/stenographers")
async def list_stenographers(court_id: Optional[str] = None):
    q = {"vendor_category": "stenographer", "kyc_status": "approved"}
    if court_id:
        q["court_ids"] = court_id
    return await db.vendors.find(q, {"_id": 0}).sort("rating", -1).to_list(100)


@api_router.post("/stenographers/book")
async def book_stenographer(req: StenoBooking, user=Depends(get_current_user)):
    svc = await db.services.find_one({"service_id": req.service_id}, {"_id": 0})
    if not svc or svc.get("category") != "Stenographer Services":
        raise HTTPException(400, "Invalid stenographer service")
    min_hours = svc.get("min_hours", 1)
    if req.hours < min_hours:
        raise HTTPException(400, f"Minimum {min_hours} hour(s) required")
    court_info = await db.courts.find_one({"court_id": req.court_id}, {"_id": 0})
    if not court_info:
        raise HTTPException(404, "Court not found")
    if court_info.get("serviceable") is False:
        raise HTTPException(400, "This court is not yet serviceable")

    # Pricing (qty = hours)
    pricing = await calculate_pricing(
        [{"service_id": req.service_id, "qty": req.hours}],
        req.court_id, req.delivery_option, urgent=False,
    )

    # Auto-match a stenographer
    candidates_q = {"vendor_category": "stenographer", "kyc_status": "approved", "court_ids": req.court_id}
    if req.stenographer_id:
        candidates_q["vendor_id"] = req.stenographer_id
    candidates = await db.vendors.find(candidates_q, {"_id": 0}).to_list(20)
    candidates.sort(key=lambda v: (not v.get("sponsored", False), -float(v.get("rating", 0))))
    vendor = candidates[0] if candidates else None

    order_id = f"STN{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    booking = {
        "order_id": order_id,
        "user_id": user["user_id"], "user_name": user.get("name"), "user_phone": user.get("phone"),
        "firm_id": user.get("firm_id"),
        "services": [{"service_id": req.service_id, "qty": req.hours, "hours": req.hours}],
        "state_id": req.state_id, "court_id": req.court_id,
        "court_name": court_info["name"], "state_name": court_info.get("state_name"),
        "delivery_option": req.delivery_option, "delivery_address": req.delivery_address,
        "file_ids": [], "urgent": False, "notes": req.notes,
        "pricing": pricing,
        "vendor_id": vendor["vendor_id"] if vendor else None,
        "vendor_name": vendor["shop_name"] if vendor else None,
        "vendor_sponsored": vendor.get("sponsored", False) if vendor else False,
        "booking": {"date": req.date, "start_time": req.start_time, "hours": req.hours, "service_name": svc["name"]},
        "order_type": "stenographer_booking",
        "status": "placed", "payment_status": "pending",
        "timeline": [{"status": "placed", "at": datetime.now(timezone.utc).isoformat(), "note": f"Stenographer booking: {req.date} {req.start_time} for {req.hours}h"}],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.insert_one(booking)
    booking.pop("_id", None)
    try:
        from notifications import notify, record_notification_event
        notify(user, "order_placed", {"order": booking})
        await record_notification_event(db, user["user_id"], "order_placed",
                                         "Stenographer booking placed", f"Booking {order_id} has been placed.",
                                         "order", order_id)
    except Exception:
        pass
    try:
        from audit_log import log_audit
        await log_audit(db, "order.create", user, {"order_id": order_id, "type": "stenographer", "hours": req.hours})
    except Exception:
        pass
    return booking


@api_router.get("/vendor-categories")
async def vendor_categories():
    """List of vendor categories with their typical services."""
    return [
        {"id": "photocopy", "name": "Photocopy & Print Shop", "icon": "Printer", "service_categories": ["Document Services", "Binding Services"]},
        {"id": "typist", "name": "Legal Typist", "icon": "Type", "service_categories": ["Legal Typing"]},
        {"id": "efiling_agent", "name": "E-Filing Agent", "icon": "Gavel", "service_categories": ["E-Filing Services"]},
        {"id": "notary", "name": "Notary Partner", "icon": "Stamp", "service_categories": ["Notary Services", "Affidavit Services"]},
        {"id": "stamp_vendor", "name": "Stamp Vendor", "icon": "Receipt", "service_categories": ["Stamp Services"]},
        {"id": "stenographer", "name": "Stenographer", "icon": "Mic", "service_categories": ["Stenographer Services"]},
        {"id": "court_runner", "name": "Court Runner / Clerk", "icon": "Footprints", "service_categories": ["Court Support"]},
        {"id": "delivery_partner", "name": "Delivery Partner", "icon": "Truck", "service_categories": []},
    ]


# ============================================================================
# VENDOR PAYOUT SETTLEMENTS (T+1, NEFT/UPI batch)
# ============================================================================
@api_router.post("/admin/settlements/run")
async def run_settlements(payload: dict = None, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from settlements import run_settlement_cycle
    payload = payload or {}
    result = await run_settlement_cycle(
        db,
        cycle_date=payload.get("cycle_date"),
        dry_run=bool(payload.get("dry_run", False)),
    )
    try:
        from audit_log import log_audit
        await log_audit(db, "admin.settlement_run", user, {"cycle_date": result["cycle_date"], "created": result["settlements_created"], "amount": result["total_amount"], "dry_run": result["dry_run"]})
    except Exception:
        pass
    return result


@api_router.get("/admin/settlements")
async def admin_list_settlements(user=Depends(get_current_user), status_filter: Optional[str] = None, cycle_date: Optional[str] = None):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    q: Dict[str, Any] = {}
    if status_filter:
        q["status"] = status_filter
    if cycle_date:
        q["cycle_date"] = cycle_date
    items = await db.settlements.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    summary = {
        "total_count": len(items),
        "total_amount": round(sum(s.get("amount", 0) for s in items), 2),
        "queued": sum(1 for s in items if s.get("status") == "queued"),
        "paid": sum(1 for s in items if s.get("status") == "paid"),
        "failed": sum(1 for s in items if s.get("status") == "failed"),
    }
    return {"summary": summary, "settlements": items}


@api_router.post("/admin/settlements/{settlement_id}/mark-paid")
async def mark_settlement_paid(settlement_id: str, payload: dict = None, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    payload = payload or {}
    ref = payload.get("utr") or payload.get("reference", "")
    from settlements import change_settlement_status
    from notifications import send_email
    result = await change_settlement_status(db, send_email, settlement_id, "mark_paid", user, utr=ref)
    try:
        from audit_log import log_audit
        await log_audit(db, "admin.settlement_paid", user, {"settlement_id": settlement_id, "utr": ref})
    except Exception:
        pass
    return result


@api_router.post("/admin/settlements/{settlement_id}/mark-failed")
async def mark_settlement_failed(settlement_id: str, payload: dict = None, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    payload = payload or {}
    from settlements import change_settlement_status
    from notifications import send_email
    result = await change_settlement_status(db, send_email, settlement_id, "mark_failed", user, reason=payload.get("reason", "Unknown"))
    try:
        from audit_log import log_audit
        await log_audit(db, "admin.settlement_failed", user, {"settlement_id": settlement_id, "reason": payload.get("reason", "Unknown")})
    except Exception:
        pass
    return result


@api_router.get("/admin/settlements/export")
async def export_settlements_csv(
    user=Depends(get_current_user),
    status_filter: Optional[str] = "queued",
    format: Optional[str] = "h2h",
):
    """Export settlements as bank-ready CSV.
    format=h2h (default) - NPCI/H2H bulk-upload compatible (SBI Connect / HDFC ENet / ICICI iBizz)
    format=legacy -> simple flat format
    """
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    from settlements import neft_csv_for_settlements, neft_csv_legacy
    q = {"status": status_filter} if status_filter and status_filter != "all" else {}
    items = await db.settlements.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # Enrich with vendor contact info for narration/email/mobile columns
    for it in items:
        vu = await db.users.find_one({"user_id": it.get("vendor_id")}, {"_id": 0, "email": 1, "phone": 1})
        if vu:
            it["email"] = vu.get("email", "")
            it["mobile"] = vu.get("phone", "")
    source_acc = os.environ.get("COURTBAZAAR_DEBIT_ACCOUNT", "")
    source_ifsc = os.environ.get("COURTBAZAAR_DEBIT_IFSC", "")
    if (format or "").lower() == "legacy":
        csv_data = neft_csv_legacy(items)
        fname = "courtbazaar-settlements.csv"
    else:
        csv_data = neft_csv_for_settlements(items, source_account=source_acc, source_ifsc=source_ifsc)
        fname = f"courtbazaar-neft-h2h-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    try:
        from audit_log import log_audit
        await log_audit(db, "admin.settlement_export", user, {"format": format or "h2h", "count": len(items)})
    except Exception:
        pass
    return Response(
        content=csv_data, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@api_router.get("/vendors/me/settlements")
async def my_settlements(user=Depends(get_current_user)):
    if user["role"] != "vendor":
        raise HTTPException(403, "Vendor only")
    items = await db.settlements.find({"vendor_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    paid_total = sum(s["amount"] for s in items if s.get("status") == "paid")
    pending_total = sum(s["amount"] for s in items if s.get("status") == "queued")
    return {
        "settlements": items,
        "paid_lifetime": round(paid_total, 2),
        "pending": round(pending_total, 2),
    }


@app.on_event("startup")
async def schedule_daily_settlements():
    """Schedule daily T+1 settlement run at 2:00 UTC."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from settlements import run_settlement_cycle as _run
        async def _job():
            try:
                result = await _run(db)
                logger.info(f"Daily settlement: {result['settlements_created']} created, ₹{result['total_amount']}")
            except Exception as e:
                logger.error(f"Scheduled settlement error: {e}")
        sched = AsyncIOScheduler()
        sched.add_job(_job, CronTrigger(hour=2, minute=0))
        sched.start()
        logger.info("T+1 settlement scheduler started (daily 02:00 UTC)")
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")


@app.on_event("startup")
async def schedule_matching_waterfall():
    """Poll for hearings past their current tier's deadline and advance/
    escalate them (Counsel Matching Agent roadmap M13) — same registration
    pattern as schedule_daily_settlements above; IntervalTrigger instead of
    CronTrigger since this needs to run continuously rather than once a day,
    and max_instances=1 so a slow poll never overlaps itself."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import counsel_matching
        async def _job():
            try:
                await counsel_matching.check_stalled_matches(db)
            except Exception as e:
                logger.error(f"Scheduled matching waterfall error: {e}")
        sched = AsyncIOScheduler()
        sched.add_job(_job, IntervalTrigger(seconds=10), max_instances=1)
        sched.start()
        logger.info("Matching waterfall scheduler started (poll every 10s)")
    except Exception as e:
        logger.warning(f"Matching waterfall scheduler not started: {e}")


@app.on_event("startup")
async def schedule_order_sheet_reminders():
    """Escrow Module (founder's rule 6): remind the assigned proxy counsel to
    upload the Court Order Sheet if escrow has been held 3+ days with none
    uploaded yet. Same registration pattern as the two schedulers above;
    hourly poll is plenty for a multi-day deadline (unlike the 10s waterfall
    poll above, which is gating a live matching race)."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        async def _job():
            try:
                count = await hearings_svc.check_pending_order_sheets(db)
                if count:
                    logger.info(f"Order sheet reminders sent: {count}")
            except Exception as e:
                logger.error(f"Scheduled order sheet reminder error: {e}")
        sched = AsyncIOScheduler()
        sched.add_job(_job, IntervalTrigger(hours=1), max_instances=1)
        sched.start()
        logger.info("Order sheet reminder scheduler started (poll every 1h)")
    except Exception as e:
        logger.warning(f"Order sheet reminder scheduler not started: {e}")


@app.on_event("startup")
async def schedule_auto_release_verifications():
    """Escrow Module (3-day auto-release rule): if the requester neither
    verifies nor disputes an uploaded order sheet within 3 days, auto-release
    escrow to the proxy counsel. Same registration pattern as the schedulers
    above; hourly poll is plenty for a multi-day deadline."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        async def _job():
            try:
                count = await hearings_svc.auto_release_stale_verifications(db)
                if count:
                    logger.info(f"Auto-released stale verifications: {count}")
            except Exception as e:
                logger.error(f"Scheduled auto-release error: {e}")
        sched = AsyncIOScheduler()
        sched.add_job(_job, IntervalTrigger(hours=1), max_instances=1)
        sched.start()
        logger.info("Auto-release verification scheduler started (poll every 1h)")
    except Exception as e:
        logger.warning(f"Auto-release verification scheduler not started: {e}")


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

