"""
FastAPI application for TATKAL RUSH.
Full realistic railway booking API with 1-5 passenger limits, atomic multi-seat holds,
passenger details binding, payment confirmation, digital E-Tickets, and concurrency testing.
"""

import asyncio
import os
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db, init_db, reset_demo_seats
from backend.models import Train, Station, TrainRoute, Seat, Booking, BookingSession, Request, Payment, User, EventLog
from backend import booking_service as svc
from backend.railway_service import RailwayDataService
import hashlib

app = FastAPI(
    title="TATKAL RUSH — Railway Reservation API",
    description="Concurrency-Safe Tatkal Railway Booking Engine with Zero Double Booking & Max 3 Tickets Limit",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(svc.booking_worker())
    asyncio.create_task(svc.expire_holds_worker())
    print("[OK] TATKAL RUSH backend ready.")


# ─── Frontend Routes ──────────────────────────────────────────────────────────

@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/login", response_class=FileResponse)
async def serve_login():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


@app.get("/booking", response_class=FileResponse)
@app.get("/pnr", response_class=FileResponse)
async def serve_booking():
    return FileResponse(os.path.join(FRONTEND_DIR, "booking.html"))


@app.get("/dashboard", response_class=FileResponse)
async def serve_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


# ─── Pydantic Request Schemas ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = "demo_user"
    password: str = "Tatkal@123"
    remember_me: bool = True


class SearchFilterOptions(BaseModel):
    available_only: bool = False
    flexible_date: bool = False
    ac_only: bool = False
    sleeper_only: bool = False


class SearchRequest(BaseModel):
    source: str = "Chennai Central (MAS)"
    destination: str = "KSR Bengaluru (SBC)"
    journey_date: str = "02 October 2026"
    quota: str = "Tatkal"
    seat_class: str = "3A"
    passengers: int = 1
    filters: Optional[SearchFilterOptions] = None


class HoldSeatsRequest(BaseModel):
    train_id: int = 1
    seat_ids: Optional[List[str]] = None
    seat_numbers: Optional[List[str]] = None
    passenger_count: Optional[int] = None
    idempotency_key: Optional[str] = None
    user_id: int = 1
    journey_date: str = "02 October 2026"
    user_name: str = "Demo Passenger"


class PassengerInfo(BaseModel):
    name: str
    age: int = 28
    gender: str = "Male"


class SavePassengersRequest(BaseModel):
    pnr: str
    passengers: List[PassengerInfo] = Field(..., max_length=5)
    primary_phone: str = "9876543210"


class PaymentRequest(BaseModel):
    pnr: str
    method: str = "UPI"


class CancelRequest(BaseModel):
    pnr: str


class SimulateRequest(BaseModel):
    num_users: int = 1000
    train_id: Optional[int] = None
    seat_class: str = "3A"


class ConcurrencyTestRequest(BaseModel):
    user_a_id: int = 1
    user_b_id: int = 2
    train_id: Optional[int] = None
    seat_class: str = "3A"
    target_seat: str = "12A"


class ConcurrencyTest3Request(BaseModel):
    user_a_id: int = 1
    user_b_id: int = 2
    user_c_id: int = 3
    train_id: Optional[int] = None
    seat_class: str = "3A"
    target_seat: str = "12A"


# ─── API: Authentication (Demo Login System) ──────────────────────────────────

@app.post("/api/auth/login")
async def demo_login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Demo login endpoint verifying credentials against hashed demo accounts.
    DO NOT use or store real IRCTC credentials.
    """
    req_hash = hashlib.sha256(req.password.strip().encode("utf-8")).hexdigest()
    user = db.query(User).filter(User.username == req.username.strip()).first()

    # Fallback to direct check if username is demo_user
    if (user and user.password_hash == req_hash) or (req.username == "demo_user" and req.password == "Tatkal@123"):
        user_name = user.name if user else "Demo Passenger"
        user_email = user.email if user else "demo_user@tatkalrush.demo"
        user_id = user.id if user else 1
        return {
            "success": True,
            "message": "Login successful! Redirecting to Book Ticket page...",
            "token": f"demo_token_{user_id}_jwt_simulation",
            "user": {
                "id": user_id,
                "username": req.username,
                "name": user_name,
                "email": user_email,
            },
            "note": "Demo account for project demonstration only.",
        }

    raise HTTPException(
        status_code=401,
        detail={"success": False, "message": "Invalid username or password."}
    )


@app.get("/api/auth/me")
async def get_current_user(db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == "demo_user").first()
    if not user:
        user = db.query(User).first()
    return {
        "logged_in": True,
        "user": {
            "id": user.id if user else 1,
            "username": user.username if user else "demo_user",
            "name": user.name if user else "Demo Passenger",
            "email": user.email if user else "demo_user@tatkalrush.demo",
        },
        "disclaimer": "Demo account for project demonstration only.",
    }


@app.post("/api/auth/logout")
async def logout():
    return {"success": True, "message": "Logged out successfully."}


# ─── API: Station Search & Autocomplete ───────────────────────────────────────

@app.get("/api/stations")
async def get_stations(q: str = "", db: Session = Depends(get_db)):
    """Fuzzy autocomplete station lookup returning station names and IRCTC station codes."""
    return {"stations": RailwayDataService.search_stations(query=q, db=db)}


# ─── API: Train Search & Details ──────────────────────────────────────────────

@app.post("/api/search")
@app.post("/api/trains/search")
async def search_trains(req: SearchRequest, db: Session = Depends(get_db)):
    """Search trains using RailwayDataService with rich filter support."""
    filter_dict = req.filters.dict() if req.filters else {}
    return RailwayDataService.search_trains(
        source=req.source,
        destination=req.destination,
        journey_date=req.journey_date,
        quota=req.quota,
        seat_class=req.seat_class,
        filters=filter_dict,
        db=db,
    )


@app.get("/api/trains/{train_id}")
async def get_train_details(train_id: int, db: Session = Depends(get_db)):
    """Fetch complete train specifications, classes, route schedule, and halts."""
    details = RailwayDataService.get_train_details(train_id=train_id, db=db)
    if not details:
        raise HTTPException(status_code=404, detail=f"Train ID {train_id} not found.")
    return details


@app.get("/api/trains/{train_id}/schedule")
async def get_train_schedule(train_id: int, db: Session = Depends(get_db)):
    details = RailwayDataService.get_train_details(train_id=train_id, db=db)
    if not details:
        raise HTTPException(status_code=404, detail=f"Train ID {train_id} not found.")
    return {"schedule": details.get("schedule", []), "train_name": details.get("name")}



# ─── API: Seat Map for Coach B1 ───────────────────────────────────────────────

@app.get("/api/seats")
@app.get("/train/{train_id}/seats")
async def get_seats(train_id: Optional[int] = None, db: Session = Depends(get_db)):
    if not train_id:
        demo = db.query(Train).filter(Train.train_number.in_(["99999", "DEMO-99"])).first()
        train_id = demo.id if demo else 1

    train = db.query(Train).filter(Train.id == train_id).first()
    seats = db.query(Seat).filter(Seat.train_id == train_id).all()

    return {
        "train": {
            "id": train.id if train else 1,
            "train_number": train.train_number if train else "99999",
            "name": train.name if train else "DEMO EXPRESS",
            "coach": "B1",
            "seat_class": "3A",
            "fare": 1245.0,
        },
        "seats": [
            {
                "id": s.id,
                "coach": s.coach,
                "seat_number": s.seat_number,
                "seat_id": s.seat_number,
                "berth_type": s.berth_type,
                "seat_class": s.seat_class,
                "quota": s.quota,
                "is_tatkal": s.is_tatkal,
                "status": s.status,
                "held_by": s.held_by,
                "held_by_name": s.held_by_name,
                "held_pnr": s.held_pnr,
                "hold_expires_at": s.hold_expires_at.isoformat() if s.hold_expires_at else None,
                "price": s.price,
                "version": s.version,
            }
            for s in seats
        ],
        "tatkal_available": sum(1 for s in seats if s.is_tatkal and s.status == "AVAILABLE"),
    }


# ─── API: Hold Seats (Backend-First Atomic Check-and-Hold) ───────────────────

@app.post("/booking/hold")
@app.post("/api/hold-seats")
@app.post("/api/hold-seat")
async def hold_seats(req: HoldSeatsRequest, db: Session = Depends(get_db)):
    # Reconcile seat_ids and seat_numbers
    seats = req.seat_ids if req.seat_ids is not None else req.seat_numbers
    if not seats:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "Please specify seat_ids to hold."}
        )

    # 1. Strict Backend 3-Seat Enforcement
    if len(seats) > 3 or (req.passenger_count and req.passenger_count > 3):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "Maximum 3 seats allowed per booking transaction."}
        )

    count = req.passenger_count if req.passenger_count is not None else len(seats)

    result = await svc.submit_hold_request(
        train_id=req.train_id,
        seat_numbers=seats,
        user_id=req.user_id,
        passenger_count=count,
        journey_date=req.journey_date,
        user_name=req.user_name,
        idempotency_key=req.idempotency_key,
    )

    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result)

    return result


# ─── API: Save Passenger Details for PNR ──────────────────────────────────────

@app.post("/api/passenger-details")
async def save_passengers(req: SavePassengersRequest, db: Session = Depends(get_db)):
    if len(req.passengers) > 5:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "Maximum 5 passengers are allowed per booking."}
        )

    result = svc.save_passenger_details(
        pnr=req.pnr,
        passengers=[p.dict() for p in req.passengers],
        primary_phone=req.primary_phone,
        db=db,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)

    return result


# ─── API: Retrieve Active Booking Session by PNR ──────────────────────────────

@app.get("/api/session/{pnr}")
async def get_session(pnr: str, db: Session = Depends(get_db)):
    session = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active booking session not found.")

    return {
        "pnr": session.pnr,
        "train_id": session.train_id,
        "coach": session.coach,
        "seats": session.seats_list.split(","),
        "passenger_count": session.passenger_count,
        "fare_per_seat": session.fare_per_seat,
        "total_fare": session.total_fare,
        "journey_date": session.journey_date,
        "status": session.status,
        "expires_at": session.expires_at.isoformat(),
    }


# ─── API: Payment & Multi-Passenger E-Ticket ─────────────────────────────────

@app.post("/api/payment")
async def pay(req: PaymentRequest, db: Session = Depends(get_db)):
    result = svc.process_payment(pnr=req.pnr, method=req.method, db=db)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


# ─── API: Digital Railway E-Ticket by PNR ────────────────────────────────────

@app.get("/api/ticket/{pnr}")
@app.get("/api/booking/{pnr}")
async def get_ticket(pnr: str, db: Session = Depends(get_db)):
    booking_exists = db.query(Booking).filter(Booking.pnr == pnr).first()
    session_exists = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()

    if not booking_exists and not session_exists:
        raise HTTPException(status_code=404, detail=f"No ticket found for PNR {pnr}")

    ticket = svc.format_unified_ticket(pnr, db)
    return {"success": True, "ticket": ticket}


# ─── API: My Bookings List ────────────────────────────────────────────────────

@app.get("/api/my-bookings")
async def get_my_bookings(db: Session = Depends(get_db)):
    # Group bookings by unique PNR
    pnrs = [
        row[0] for row in db.query(Booking.pnr).distinct().order_by(Booking.created_at.desc()).limit(20).all()
    ]

    tickets = [svc.format_unified_ticket(pnr, db) for pnr in pnrs]
    return {"bookings": tickets}


# ─── API: Cancel Booking / Release Hold ───────────────────────────────────────

@app.post("/api/cancel-booking")
@app.post("/api/release-hold")
@app.post("/api/cancel")
async def cancel(req: CancelRequest, db: Session = Depends(get_db)):
    result = svc.release_seats_by_pnr(pnr=req.pnr, db=db)
    return result


# ─── API: Test 6-Ticket Limit ─────────────────────────────────────────────────

@app.post("/api/test-limit")
async def test_ticket_limit(db: Session = Depends(get_db)):
    """Explicit test endpoint verifying that backend rejects > 5 tickets."""
    test_seats = ["12A", "12B", "12C", "12D", "12E", "1A"]
    res = svc.atomic_hold_seats(
        db=db,
        train_id=1,
        seat_numbers=test_seats,
        passenger_count=6,
    )

    if not res["success"]:
        return {
            "test": "6_TICKET_LIMIT",
            "status": "PASSED",
            "http_code": 400,
            "message": res["reason"],
            "integrity": "VERIFIED ✓",
        }
    else:
        raise HTTPException(status_code=500, detail="Backend failed to reject 6 tickets!")


# ─── API: Concurrency Tests ───────────────────────────────────────────────────

@app.post("/api/concurrency-test")
async def concurrency_test(req: ConcurrencyTestRequest, db: Session = Depends(get_db)):
    train_id = req.train_id
    if not train_id:
        demo = db.query(Train).filter(Train.train_number.in_(["99999", "DEMO-99"])).first()
        train_id = demo.id if demo else 1

    return await svc.run_concurrency_test(
        user_a_id=req.user_a_id,
        user_b_id=req.user_b_id,
        train_id=train_id,
        seat_class=req.seat_class,
        target_seat=req.target_seat or "12A",
    )


@app.post("/api/concurrency-test-3")
async def concurrency_test_3(req: ConcurrencyTest3Request, db: Session = Depends(get_db)):
    train_id = req.train_id
    if not train_id:
        demo = db.query(Train).filter(Train.train_number.in_(["99999", "DEMO-99"])).first()
        train_id = demo.id if demo else 1

    return await svc.run_three_user_test(
        user_a_id=req.user_a_id,
        user_b_id=req.user_b_id,
        user_c_id=req.user_c_id,
        train_id=train_id,
        seat_class=req.seat_class,
        target_seat=req.target_seat or "12A",
    )


@app.post("/api/simulate")
async def simulate(req: SimulateRequest, db: Session = Depends(get_db)):
    if svc._metrics.get("simulation_running"):
        raise HTTPException(status_code=429, detail="Simulation is already running")

    train_id = req.train_id
    if not train_id:
        demo = db.query(Train).filter(Train.train_number.in_(["99999", "DEMO-99"])).first()
        train_id = demo.id if demo else 1

    num_users = min(req.num_users, 5000)
    return await svc.run_simulation(num_users=num_users, train_id=train_id, seat_class=req.seat_class)


@app.post("/api/reset")
async def reset_demo(db: Session = Depends(get_db)):
    reset_demo_seats(db)
    svc._metrics.update({
        "total_requests": 0,
        "active_requests": 0,
        "successful_bookings": 0,
        "failed_requests": 0,
        "double_booking_attempts_prevented": 0,
        "processing_times": [],
        "simulation_running": False,
    })
    svc._event_log.clear()
    await svc.broadcast({"type": "seat_update", "status": "AVAILABLE", "metrics": svc.get_metrics()})
    return {"message": "Demo Tatkal seats restored to AVAILABLE"}


@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    metrics = svc.get_metrics()
    pnrs = [row[0] for row in db.query(Booking.pnr).distinct().order_by(Booking.created_at.desc()).limit(10).all()]
    metrics["recent_bookings"] = [svc.format_unified_ticket(pnr, db) for pnr in pnrs]
    return metrics


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    svc._ws_connections.add(websocket)
    try:
        await websocket.send_json({"type": "metrics", "data": svc.get_metrics()})
        while True:
            await asyncio.sleep(2)
            await websocket.send_json({"type": "metrics", "data": svc.get_metrics()})
    except WebSocketDisconnect:
        svc._ws_connections.discard(websocket)
    except Exception:
        svc._ws_connections.discard(websocket)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "TATKAL RUSH", "version": "2.1.0"}
