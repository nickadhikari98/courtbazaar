"""
CourtBazaar - Legal Operations & Court Services Marketplace
Main FastAPI application
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Header, Query, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict, Any
import uuid
import jwt
import bcrypt
import requests
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
APP_NAME = os.environ.get('APP_NAME', 'courtbazaar')
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"

app = FastAPI(title="CourtBazaar API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== Storage =====
_storage_key: Optional[str] = None

def init_storage():
    global _storage_key
    if _storage_key:
        return _storage_key
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        logger.info("Object storage initialized")
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(500, "Storage unavailable")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    if not key:
        raise HTTPException(500, "Storage unavailable")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

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

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        # Try Emergent google session token
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
            return user
        try:
            payload = decode_jwt(token)
            user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
            if not user:
                raise HTTPException(401, "User not found")
            return user
        except jwt.PyJWTError:
            raise HTTPException(401, "Invalid token")
    raise HTTPException(401, "Not authenticated")

# ===== Models =====
ROLES = ["advocate", "law_firm", "vendor", "efiling_agent", "legal_typist", "notary", "stamp_vendor", "delivery_partner", "franchise", "admin"]

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    role: str = "advocate"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class OtpRequest(BaseModel):
    phone: str

class OtpVerify(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None
    role: str = "advocate"

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

class VendorOnboard(BaseModel):
    shop_name: str
    owner_name: str
    phone: str
    address: str
    court_ids: List[str]
    service_ids: List[str]
    pan: Optional[str] = None
    gst: Optional[str] = None
    aadhaar: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None

class PricingUpdate(BaseModel):
    service_id: str
    base_price: float
    platform_commission_pct: Optional[float] = None
    convenience_fee: Optional[float] = None

class ChatMessage(BaseModel):
    session_id: str
    message: str

class CheckoutRequest(BaseModel):
    order_id: str
    origin_url: str

class RatingCreate(BaseModel):
    order_id: str
    rating: int
    review: Optional[str] = None

# ===== Startup: seed data =====
@app.on_event("startup")
async def startup():
    init_storage()
    await seed_initial_data()

async def seed_initial_data():
    if await db.courts.count_documents({}) == 0:
        from court_seed import COURT_DATA, SERVICE_CATALOG
        for state in COURT_DATA:
            await db.states.update_one({"state_id": state["state_id"]}, {"$set": state}, upsert=True)
            for court in state["courts"]:
                court_doc = {**court, "state_id": state["state_id"], "state_name": state["name"]}
                await db.courts.update_one({"court_id": court["court_id"]}, {"$set": court_doc}, upsert=True)
        for svc in SERVICE_CATALOG:
            await db.services.update_one({"service_id": svc["service_id"]}, {"$set": svc}, upsert=True)
        logger.info("Seeded states, courts, services")

    if await db.users.count_documents({"role": "admin"}) == 0:
        admin_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": admin_id,
            "email": "admin@courtbazaar.in",
            "name": "Platform Admin",
            "role": "admin",
            "password_hash": hash_password("Admin@123"),
            "phone": "9999999999",
            "verified": True,
            "wallet_balance": 0.0,
            "subscription": "enterprise",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    if not await db.users.find_one({"email": "advocate@demo.in"}):
        adv_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": adv_id,
            "email": "advocate@demo.in",
            "name": "Adv. Priya Sharma",
            "role": "advocate",
            "password_hash": hash_password("Advocate@123"),
            "phone": "9876543210",
            "bar_council_id": "D/1234/2018",
            "chamber_address": "Chamber 42, Tis Hazari Court, Delhi",
            "verified": True,
            "wallet_balance": 2500.0,
            "subscription": "advocate_pro",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    if not await db.users.find_one({"email": "vendor@demo.in"}):
        v_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": v_id,
            "email": "vendor@demo.in",
            "name": "Sharma Xerox & Print Center",
            "role": "vendor",
            "password_hash": hash_password("Vendor@123"),
            "phone": "9876543211",
            "verified": True,
            "kyc_status": "approved",
            "wallet_balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.vendors.insert_one({
            "vendor_id": v_id,
            "user_id": v_id,
            "shop_name": "Sharma Xerox & Print Center",
            "owner_name": "Rakesh Sharma",
            "phone": "9876543211",
            "address": "Shop 12, Tis Hazari Court Complex, Delhi",
            "court_ids": ["court_tishazari", "court_patiala_house", "court_karkardooma"],
            "service_ids": ["svc_bw_photocopy", "svc_color_photocopy", "svc_bw_print", "svc_color_print", "svc_spiral_binding", "svc_hard_binding", "svc_pagination", "svc_bookmarking"],
            "rating": 4.7,
            "total_orders": 1247,
            "kyc_status": "approved",
            "gst": "07AAACS1234A1Z5",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

# ===== Routes =====
@api_router.get("/")
async def root():
    return {"message": "CourtBazaar API - India's Legal Marketplace", "version": "1.0"}

# ---------- AUTH ----------
@api_router.post("/auth/register")
async def register(req: RegisterRequest):
    if req.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    if await db.users.find_one({"email": req.email}):
        raise HTTPException(400, "Email already registered")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    token = make_jwt(user_id, req.role)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    return {"token": token, "user": user_doc}

@api_router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")
    token = make_jwt(user["user_id"], user["role"])
    user.pop("password_hash", None)
    return {"token": token, "user": user}

@api_router.post("/auth/otp/request")
async def otp_request(req: OtpRequest):
    return {"ok": True, "message": "OTP sent (mock). Use 123456", "phone": req.phone}

@api_router.post("/auth/otp/verify")
async def otp_verify(req: OtpVerify):
    if req.otp != "123456":
        raise HTTPException(400, "Invalid OTP")
    user = await db.users.find_one({"phone": req.phone}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": f"{req.phone}@phone.courtbazaar.in",
            "name": req.name or f"User {req.phone[-4:]}",
            "phone": req.phone,
            "role": req.role,
            "verified": True,
            "wallet_balance": 0.0,
            "subscription": "free",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    token = make_jwt(user["user_id"], user["role"])
    user.pop("password_hash", None)
    user.pop("_id", None)
    return {"token": token, "user": user}

@api_router.post("/auth/google/session")
async def google_session(payload: dict, response: Response):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id required")
    try:
        r = requests.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}, timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(401, f"OAuth session invalid: {e}")
    email = data["email"]
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name", existing["name"]), "avatar_url": data.get("picture")}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "avatar_url": data.get("picture"),
            "role": payload.get("role", "advocate"),
            "verified": True,
            "wallet_balance": 0.0,
            "subscription": "free",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    session_token = data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(
        key="session_token", value=session_token, httponly=True,
        secure=True, samesite="none", path="/", max_age=7 * 24 * 3600,
    )
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"token": session_token, "user": user}

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
async def list_courts(state_id: Optional[str] = None, q: Optional[str] = None):
    query: Dict[str, Any] = {}
    if state_id:
        query["state_id"] = state_id
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    courts = await db.courts.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return courts

@api_router.get("/courts/{court_id}")
async def get_court(court_id: str):
    court = await db.courts.find_one({"court_id": court_id}, {"_id": 0})
    if not court:
        raise HTTPException(404, "Court not found")
    vendor_count = await db.vendors.count_documents({"court_ids": court_id, "kyc_status": "approved"})
    return {**court, "vendor_count": vendor_count}

# ---------- SERVICES ----------
@api_router.get("/services")
async def list_services(category: Optional[str] = None):
    query: Dict[str, Any] = {"active": {"$ne": False}}
    if category:
        query["category"] = category
    services = await db.services.find(query, {"_id": 0}).to_list(500)
    return services

@api_router.get("/services/categories")
async def service_categories():
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    cats = []
    async for doc in db.services.aggregate(pipeline):
        if doc["_id"]:
            cats.append({"category": doc["_id"], "count": doc["count"]})
    return cats

@api_router.get("/services/{service_id}")
async def get_service(service_id: str):
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
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "vendor"}})
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
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/uploads/{user['user_id']}/{file_id}.{ext}"
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {e}")
    record = {
        "file_id": file_id,
        "user_id": user["user_id"],
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
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
    if rec["user_id"] != user["user_id"] and user["role"] not in ("admin", "vendor"):
        raise HTTPException(403, "Forbidden")
    data, ct = get_object(rec["storage_path"])
    return Response(content=data, media_type=rec.get("content_type", ct))

@api_router.get("/files/mine")
async def my_files(user=Depends(get_current_user)):
    files = await db.files.find({"user_id": user["user_id"], "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return files

# ---------- ORDERS ----------
ORDER_STATUSES = ["placed", "matched", "accepted", "processing", "quality_check", "ready", "out_for_delivery", "delivered", "completed", "cancelled"]

async def calculate_pricing(services: List[Dict], court_id: str, delivery: str, urgent: bool):
    subtotal = 0.0
    vendor_share = 0.0
    breakdown = []
    for item in services:
        svc = await db.services.find_one({"service_id": item["service_id"]}, {"_id": 0})
        if not svc:
            continue
        qty = item.get("qty", 1)
        unit = float(svc.get("base_price", 0))
        line = unit * qty
        vendor_unit = unit * (1 - float(svc.get("platform_commission_pct", 0.2)))
        subtotal += line
        vendor_share += vendor_unit * qty
        breakdown.append({"service_id": svc["service_id"], "name": svc["name"], "unit_price": unit, "qty": qty, "line_total": line})
    delivery_fee = {"pickup": 0, "chamber": 79, "court": 49, "digital": 0}.get(delivery, 0)
    urgent_fee = round(subtotal * 0.25, 2) if urgent else 0
    convenience = 10.0
    gst = round((subtotal + delivery_fee + urgent_fee + convenience) * 0.18, 2)
    total = round(subtotal + delivery_fee + urgent_fee + convenience + gst, 2)
    platform_commission = round(subtotal - vendor_share, 2)
    return {
        "breakdown": breakdown, "subtotal": round(subtotal, 2),
        "delivery_fee": delivery_fee, "urgent_fee": urgent_fee,
        "convenience_fee": convenience, "gst": gst, "total": total,
        "vendor_payout": round(vendor_share, 2), "platform_commission": platform_commission,
    }

@api_router.post("/orders/quote")
async def order_quote(req: OrderCreate, user=Depends(get_current_user)):
    return await calculate_pricing(req.services, req.court_id, req.delivery_option, req.urgent)

@api_router.post("/orders")
async def create_order(req: OrderCreate, user=Depends(get_current_user)):
    pricing = await calculate_pricing(req.services, req.court_id, req.delivery_option, req.urgent)
    candidates = await db.vendors.find({"court_ids": req.court_id, "kyc_status": "approved"}, {"_id": 0}).sort("rating", -1).to_list(5)
    vendor = candidates[0] if candidates else None
    court_info = await db.courts.find_one({"court_id": req.court_id}, {"_id": 0, "name": 1, "state_name": 1})
    order_id = f"ORD{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    order = {
        "order_id": order_id,
        "user_id": user["user_id"],
        "user_name": user.get("name"),
        "user_phone": user.get("phone"),
        "services": req.services,
        "state_id": req.state_id,
        "court_id": req.court_id,
        "court_name": court_info["name"] if court_info else req.court_id,
        "state_name": court_info.get("state_name") if court_info else None,
        "delivery_option": req.delivery_option,
        "delivery_address": req.delivery_address,
        "file_ids": req.file_ids,
        "urgent": req.urgent,
        "notes": req.notes,
        "pricing": pricing,
        "vendor_id": vendor["vendor_id"] if vendor else None,
        "vendor_name": vendor["shop_name"] if vendor else None,
        "status": "placed",
        "payment_status": "pending",
        "timeline": [{"status": "placed", "at": datetime.now(timezone.utc).isoformat(), "note": "Order placed"}],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.insert_one(order)
    order.pop("_id", None)
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

# ---------- PAYMENTS ----------
@api_router.post("/payments/checkout")
async def create_checkout(req: CheckoutRequest, http_request: Request, user=Depends(get_current_user)):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
    order = await db.orders.find_one({"order_id": req.order_id}, {"_id": 0})
    if not order or order["user_id"] != user["user_id"]:
        raise HTTPException(404, "Order not found")
    amount = float(order["pricing"]["total"])
    host_url = str(http_request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    success_url = f"{req.origin_url}/orders/{req.order_id}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{req.origin_url}/orders/{req.order_id}"
    checkout_req = CheckoutSessionRequest(
        amount=amount, currency="inr",
        success_url=success_url, cancel_url=cancel_url,
        metadata={"order_id": req.order_id, "user_id": user["user_id"]},
    )
    session = await stripe_checkout.create_checkout_session(checkout_req)
    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "order_id": req.order_id,
        "user_id": user["user_id"], "amount": amount, "currency": "inr",
        "status": "initiated", "payment_status": "pending",
        "metadata": {"order_id": req.order_id},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}

@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str, user=Depends(get_current_user)):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if tx.get("payment_status") == "paid":
        return tx
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    status = await stripe_checkout.get_checkout_status(session_id)
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"status": status.status, "payment_status": status.payment_status}},
    )
    if status.payment_status == "paid" and tx.get("payment_status") != "paid":
        await db.orders.update_one(
            {"order_id": tx["order_id"]},
            {"$set": {"payment_status": "paid", "status": "matched"},
             "$push": {"timeline": {"status": "matched", "at": datetime.now(timezone.utc).isoformat(), "note": "Payment successful, vendor matched"}}},
        )
    return await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    try:
        ev = await stripe_checkout.handle_webhook(body, sig)
        if ev.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"session_id": ev.session_id},
                {"$set": {"payment_status": "paid", "status": "complete"}},
            )
            tx = await db.payment_transactions.find_one({"session_id": ev.session_id})
            if tx:
                await db.orders.update_one(
                    {"order_id": tx["order_id"]},
                    {"$set": {"payment_status": "paid", "status": "matched"}},
                )
    except Exception as e:
        logger.error(f"Webhook error: {e}")
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"balance": new_balance}

# ---------- AI ASSISTANT ----------
@api_router.post("/ai/chat")
async def ai_chat(req: ChatMessage, user=Depends(get_current_user)):
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    system_msg = (
        "You are CourtBazaar's AI Legal Assistant for India. Help advocates with: "
        "1) Court selection guidance, 2) Filing checklists, 3) Defect detection, "
        "4) Smart service recommendations (photocopy, e-filing, binding, notary, stamps). "
        "Be concise, use Indian legal terminology (Vakalatnama, Cause List, Paper Book, Affidavit, Court Bundle). "
        "Include INR pricing context when relevant. Keep replies under 200 words."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=req.session_id, system_message=system_msg,
    ).with_model("anthropic", "claude-sonnet-4-6")
    response_text = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=req.message)):
            if isinstance(ev, TextDelta):
                response_text += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(500, f"AI error: {str(e)}")
    await db.ai_messages.insert_one({
        "session_id": req.session_id, "user_id": user["user_id"],
        "user_message": req.message, "ai_response": response_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"reply": response_text}

@api_router.get("/ai/history/{session_id}")
async def ai_history(session_id: str, user=Depends(get_current_user)):
    msgs = await db.ai_messages.find({"session_id": session_id, "user_id": user["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(100)
    return msgs

@api_router.post("/ai/filing-checklist")
async def filing_checklist(payload: dict, user=Depends(get_current_user)):
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
    court = payload.get("court", "")
    case_type = payload.get("case_type", "")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"checklist_{user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message="You are an Indian legal filing expert. Generate a numbered checklist of documents and steps required for filing.",
    ).with_model("anthropic", "claude-sonnet-4-6")
    msg = f"Generate a comprehensive filing checklist for {case_type} at {court}. List exact documents, copies needed, court fees, stamp duty, and binding requirements. Use numbered list."
    out = ""
    async for ev in chat.stream_message(UserMessage(text=msg)):
        if isinstance(ev, TextDelta):
            out += ev.content
        elif isinstance(ev, StreamDone):
            break
    return {"checklist": out}

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
    update = {k: v for k, v in payload.model_dump().items() if v is not None and k != "service_id"}
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

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
