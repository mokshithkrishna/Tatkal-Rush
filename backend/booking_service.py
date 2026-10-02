"""
Core booking service for TATKAL RUSH.
Implements atomic multi-seat check-and-hold (1 to 5 seats per PNR), all-or-nothing transaction guarantees,
session persistence, payment processing, multi-passenger E-Ticket issuance, and concurrency testing.
"""

import asyncio
import datetime
import random
import string
import time
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.database import SessionLocal
from backend.models import User, Train, Seat, Booking, BookingSession, Request, Payment, EventLog

booking_queue: asyncio.Queue = asyncio.Queue()

_metrics: Dict[str, Any] = {
    "total_requests": 0,
    "active_requests": 0,
    "successful_bookings": 0,
    "failed_requests": 0,
    "double_booking_attempts_prevented": 0,
    "queue_length": 0,
    "requests_per_sec": 0,
    "avg_processing_ms": 0,
    "processing_times": [],
    "simulation_running": False,
}

_event_log: List[Dict] = []
_ws_connections = set()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def generate_pnr() -> str:
    """Generate a realistic 10-character alphanumeric PNR starting with TR."""
    digits = "".join(random.choices(string.digits, k=10))
    return f"TR{digits}"


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _log_event(event_type: str, user_ref: str, seat_ref: str, message: str,
               severity: str = "INFO", db: Optional[Session] = None):
    entry = {
        "timestamp": _now().strftime("%H:%M:%S.%f")[:-3],
        "event_type": event_type,
        "user_ref": user_ref,
        "seat_ref": seat_ref,
        "message": message,
        "severity": severity,
    }
    _event_log.append(entry)
    if len(_event_log) > 500:
        _event_log.pop(0)

    if db:
        try:
            db.add(EventLog(
                event_type=event_type,
                user_ref=user_ref,
                seat_ref=seat_ref,
                message=message,
                severity=severity,
            ))
            db.flush()
        except Exception:
            pass


async def broadcast(data: dict):
    """Push real-time updates to all connected WebSocket clients."""
    global _ws_connections
    if not _ws_connections:
        return
    import json
    msg = json.dumps(data)
    dead = set()
    for ws in list(_ws_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_connections.discard(ws)


def get_metrics() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        demo_train = db.query(Train).filter(Train.train_number.in_(["99999", "DEMO-99"])).first()
        seat_stats = {"AVAILABLE": 0, "HELD": 0, "BOOKED": 0}
        if demo_train:
            for seat in db.query(Seat).filter(Seat.train_id == demo_train.id, Seat.is_tatkal == True).all():
                seat_stats[seat.status] = seat_stats.get(seat.status, 0) + 1
        return {
            **_metrics,
            "queue_length": booking_queue.qsize(),
            "available_seats": seat_stats.get("AVAILABLE", 0),
            "held_seats": seat_stats.get("HELD", 0),
            "booked_seats": seat_stats.get("BOOKED", 0),
            "event_log": _event_log[-50:],
        }
    finally:
        db.close()


# ─── Atomic Multi-Seat Hold (All-or-Nothing Transaction) ─────────────────────

def atomic_hold_seats(
    db: Session,
    train_id: int,
    seat_numbers: List[str],
    user_id: int = 1,
    passenger_count: Optional[int] = None,
    journey_date: str = "02 October 2026",
    user_name: str = "Mokshith Krishna",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    All-or-Nothing Atomic Multi-Seat Hold.
    Enforces maximum 3 tickets per booking (1 to 3 seats).
    Uses SQL atomic conditional update (UPDATE ... WHERE status = 'AVAILABLE').
    Either ALL requested seats are successfully held, or NONE are held.
    Supports idempotency keys to prevent duplicate booking transactions.
    """
    # Normalize seat numbers
    seat_numbers = [str(s).strip().upper() for s in seat_numbers if str(s).strip()]
    count = passenger_count if passenger_count is not None else len(seat_numbers)

    # 1. Strict Max 3 Seats Check
    if len(seat_numbers) == 0:
        return {
            "success": False,
            "reason": "Please select at least 1 seat.",
            "pnr": None,
            "seats": [],
            "seat_ids": [],
        }

    if len(seat_numbers) > 3 or count > 3:
        return {
            "success": False,
            "reason": "Maximum 3 seats allowed per booking transaction.",
            "pnr": None,
            "seats": [],
            "seat_ids": [],
        }

    if len(seat_numbers) != count:
        return {
            "success": False,
            "reason": f"Seat selection count ({len(seat_numbers)}) does not match passenger count ({count}).",
            "pnr": None,
            "seats": [],
            "seat_ids": [],
        }

    now = _now()

    # 2. Idempotency Key Check
    if idempotency_key:
        existing_session = (
            db.query(BookingSession)
            .filter(BookingSession.idempotency_key == idempotency_key)
            .first()
        )
        if existing_session and existing_session.status in ["HELD", "CONFIRMED"]:
            remaining_secs = max(0, int((existing_session.expires_at - now).total_seconds()))
            if existing_session.status == "HELD" and remaining_secs <= 0:
                pass  # Expired, proceed to re-hold
            else:
                held_seats = existing_session.seats_list.split(",")
                return {
                    "success": True,
                    "pnr": existing_session.pnr,
                    "train_id": existing_session.train_id,
                    "coach": existing_session.coach,
                    "seat_class": existing_session.seat_class,
                    "seats": held_seats,
                    "seat_ids": held_seats,
                    "passenger_count": existing_session.passenger_count,
                    "fare_per_seat": existing_session.fare_per_seat,
                    "total_fare": existing_session.total_fare,
                    "journey_date": existing_session.journey_date,
                    "hold_expires_in": remaining_secs,
                    "expires_at": existing_session.expires_at.isoformat(),
                    "idempotency_hit": True,
                    "reason": "Retrieved existing active seat reservation.",
                }

    try:
        # 3. Verify that all requested seats exist on this train
        target_seats = (
            db.query(Seat)
            .filter(
                Seat.train_id == train_id,
                Seat.seat_number.in_(seat_numbers),
            )
            .all()
        )
        found_map = {s.seat_number: s for s in target_seats}

        for s_num in seat_numbers:
            if s_num not in found_map:
                _metrics["double_booking_attempts_prevented"] += 1
                return {
                    "success": False,
                    "reason": f"Seat {s_num} does not exist on this train.",
                    "pnr": None,
                    "seats": [],
                    "seat_ids": [],
                }

        # 4. Atomic SQL Conditional Update: UPDATE seats SET status='HELD' WHERE status='AVAILABLE'
        pnr = generate_pnr()
        hold_expiry = now + datetime.timedelta(minutes=5)
        fare_per_seat = 1245.0
        total_fare = fare_per_seat * count
        train = db.query(Train).filter(Train.id == train_id).first()
        coach = "B1"

        updated_seats = []
        for s_num in seat_numbers:
            result = db.execute(
                text("""
                    UPDATE seats
                    SET status = 'HELD',
                        held_by = :user_id,
                        held_by_name = :user_name,
                        held_pnr = :pnr,
                        hold_expires_at = :hold_expiry,
                        version = version + 1
                    WHERE train_id = :train_id
                      AND seat_number = :seat_number
                      AND (
                          status = 'AVAILABLE'
                          OR (status = 'HELD' AND hold_expires_at < :now)
                      )
                """),
                {
                    "user_id": user_id,
                    "user_name": user_name,
                    "pnr": pnr,
                    "hold_expiry": hold_expiry,
                    "train_id": train_id,
                    "seat_number": s_num,
                    "now": now,
                },
            )

            if result.rowcount != 1:
                # Rowcount == 0 means seat is already HELD or BOOKED by another user!
                # Immediately rollback all changes in this transaction
                db.rollback()
                _metrics["double_booking_attempts_prevented"] += 1
                return {
                    "success": False,
                    "reason": f"Sorry! Seat {s_num} was just taken by another user.",
                    "pnr": None,
                    "seats": [],
                    "seat_ids": [],
                }
            updated_seats.append(s_num)

        # 5. Create BookingSession record
        session_obj = BookingSession(
            pnr=pnr,
            idempotency_key=idempotency_key,
            user_id=user_id,
            train_id=train_id,
            coach=coach,
            seat_class="3A",
            seats_list=",".join(seat_numbers),
            passenger_count=count,
            fare_per_seat=fare_per_seat,
            total_fare=total_fare,
            journey_date=journey_date,
            status="HELD",
            expires_at=hold_expiry,
        )
        db.add(session_obj)
        db.commit()

        _log_event(
            "SEATS_HELD", f"User #{user_id:04d}", ",".join(seat_numbers),
            f"Successfully held {count} seat(s) ({','.join(seat_numbers)}) for {user_name} — PNR: {pnr}",
            "SUCCESS", db
        )
        db.commit()

        # Broadcast update to connected clients
        asyncio.create_task(broadcast({
            "type": "seat_update",
            "seats": seat_numbers,
            "status": "HELD",
            "metrics": get_metrics(),
        }))

        return {
            "success": True,
            "pnr": pnr,
            "train_id": train_id,
            "train_number": train.train_number if train else "99999",
            "train_name": train.name if train else "DEMO EXPRESS",
            "coach": coach,
            "seat_class": "3A",
            "seats": seat_numbers,
            "seat_ids": seat_numbers,
            "passenger_count": count,
            "fare_per_seat": fare_per_seat,
            "total_fare": total_fare,
            "journey_date": journey_date,
            "hold_expires_in": 300,
            "expires_at": hold_expiry.isoformat(),
            "reason": f"Successfully secured {count} seat(s). Complete passenger details within 5 minutes.",
        }

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "success": False,
            "reason": f"Transaction error securing seats: {str(e)}",
            "pnr": None,
            "seats": [],
            "seat_ids": [],
        }


# ─── Booking Worker Queue ───────────────────────────────────────────────────

async def booking_worker():
    """Single worker processing all booking requests serially to preserve strict FIFO order."""
    print("[Worker] Booking worker started.")
    while True:
        try:
            item = await asyncio.wait_for(booking_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        future: asyncio.Future = item["future"]
        train_id: int = item["train_id"]
        user_id: int = item["user_id"]
        seat_numbers: List[str] = item.get("seat_numbers") or [item.get("specific_seat", "12A")]
        passenger_count: int = item.get("passenger_count", len(seat_numbers))
        journey_date: str = item.get("journey_date", "02 October 2026")
        user_name: str = item.get("user_name", f"User #{user_id:04d}")
        idempotency_key: Optional[str] = item.get("idempotency_key")

        start_ts = time.perf_counter()
        _metrics["active_requests"] = max(0, _metrics["active_requests"] - 1)

        db = SessionLocal()
        try:
            result = atomic_hold_seats(
                db=db,
                train_id=train_id,
                seat_numbers=seat_numbers,
                user_id=user_id,
                passenger_count=passenger_count,
                journey_date=journey_date,
                user_name=user_name,
                idempotency_key=idempotency_key,
            )

            elapsed_ms = (time.perf_counter() - start_ts) * 1000
            _metrics["processing_times"].append(elapsed_ms)
            if len(_metrics["processing_times"]) > 1000:
                _metrics["processing_times"].pop(0)
            _metrics["avg_processing_ms"] = round(
                sum(_metrics["processing_times"]) / len(_metrics["processing_times"]), 2
            )

            if result["success"]:
                _metrics["successful_bookings"] += 1
            else:
                _metrics["failed_requests"] += 1

            result["processing_time_ms"] = round(elapsed_ms, 2)
            if not future.done():
                future.set_result(result)

        except Exception as e:
            if not future.done():
                future.set_exception(e)
        finally:
            db.close()
            booking_queue.task_done()


async def submit_hold_request(
    train_id: int,
    seat_numbers: List[str],
    user_id: int = 1,
    passenger_count: Optional[int] = None,
    journey_date: str = "02 October 2026",
    user_name: str = "Mokshith Krishna",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Enqueue seat hold request into FIFO queue and await atomic result."""
    _metrics["total_requests"] += 1
    _metrics["active_requests"] += 1

    count = passenger_count if passenger_count is not None else len(seat_numbers)

    loop = asyncio.get_event_loop()
    future = loop.create_future()

    await booking_queue.put({
        "future": future,
        "train_id": train_id,
        "user_id": user_id,
        "seat_numbers": seat_numbers,
        "passenger_count": count,
        "journey_date": journey_date,
        "user_name": user_name,
        "idempotency_key": idempotency_key,
    })

    return await future


# ─── Save Passenger Details for PNR ─────────────────────────────────────────

def save_passenger_details(
    pnr: str,
    passengers: List[Dict[str, Any]],
    primary_phone: str = "9876543210",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Link passenger details (Name, Age, Gender) to the held seats under this PNR."""
    close_db = False
    if not db:
        db = SessionLocal()
        close_db = True

    try:
        session = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()
        if not session:
            return {"success": False, "reason": f"Active booking session for PNR {pnr} not found."}

        if session.status == "EXPIRED" or _now() > session.expires_at:
            return {"success": False, "reason": "Your seat reservation expired. Please select seats again."}

        seat_nums = session.seats_list.split(",")
        if len(passengers) != len(seat_nums):
            return {"success": False, "reason": f"Expected details for {len(seat_nums)} passenger(s), received {len(passengers)}."}

        # Clear any existing pending bookings for this PNR to prevent duplicates on back navigation
        db.query(Booking).filter(Booking.pnr == pnr).delete(synchronize_session=False)

        train = db.query(Train).filter(Train.id == session.train_id).first()

        created_bookings = []
        for idx, (p_data, s_num) in enumerate(zip(passengers, seat_nums), start=1):
            seat = db.query(Seat).filter(Seat.train_id == session.train_id, Seat.seat_number == s_num).first()
            booking = Booking(
                pnr=pnr,
                booking_ref=pnr,
                user_id=session.user_id,
                train_id=session.train_id,
                seat_id=seat.id if seat else 1,
                coach=session.coach,
                seat_number=s_num,
                passenger_index=idx,
                passenger_name=p_data.get("name") or f"Passenger {idx}",
                passenger_age=int(p_data.get("age") or 28),
                passenger_gender=p_data.get("gender") or "Male",
                passenger_phone=primary_phone,
                seat_class="3A",
                quota="TATKAL",
                fare=session.fare_per_seat,
                status="PENDING",
                payment_status="UNPAID",
                journey_date=session.journey_date,
                expires_at=session.expires_at,
            )
            db.add(booking)
            created_bookings.append(booking)

        db.commit()

        return {
            "success": True,
            "pnr": pnr,
            "passenger_count": len(passengers),
            "total_fare": session.total_fare,
            "expires_at": session.expires_at.isoformat(),
            "reason": "Passenger details saved successfully.",
        }
    finally:
        if close_db:
            db.close()


# ─── Payment Processing & Multi-Passenger Digital Ticket ────────────────────

def process_payment(pnr: str, method: str = "UPI", db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Confirm payment for the PNR.
    Validates hold expiry, sets status to CONFIRMED, marks seats BOOKED,
    and returns the unified digital E-Ticket.
    """
    close_db = False
    if not db:
        db = SessionLocal()
        close_db = True

    try:
        session = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()
        bookings = db.query(Booking).filter(Booking.pnr == pnr).all()

        if not session and not bookings:
            return {"success": False, "reason": f"No booking found for PNR {pnr}."}

        # Check expiry
        now = _now()
        expiry = session.expires_at if session else (bookings[0].expires_at if bookings else None)
        if expiry and now > expiry:
            # Release all seats
            if session:
                session.status = "EXPIRED"
                seat_nums = session.seats_list.split(",")
                db.query(Seat).filter(Seat.train_id == session.train_id, Seat.seat_number.in_(seat_nums)).update({
                    "status": "AVAILABLE",
                    "held_by": None,
                    "held_by_name": None,
                    "held_pnr": None,
                    "hold_expires_at": None,
                }, synchronize_session=False)
            db.commit()
            return {"success": False, "reason": "Your reservation expired because payment was not completed in time."}

        # If bookings weren't explicitly saved before payment, auto-create default passenger rows
        if not bookings and session:
            seat_nums = session.seats_list.split(",")
            for idx, s_num in enumerate(seat_nums, start=1):
                seat = db.query(Seat).filter(Seat.train_id == session.train_id, Seat.seat_number == s_num).first()
                b = Booking(
                    pnr=pnr,
                    booking_ref=pnr,
                    user_id=session.user_id,
                    train_id=session.train_id,
                    seat_id=seat.id if seat else 1,
                    coach=session.coach,
                    seat_number=s_num,
                    passenger_index=idx,
                    passenger_name=f"Passenger {idx}",
                    passenger_age=28,
                    passenger_gender="Male",
                    passenger_phone="9876543210",
                    seat_class="3A",
                    quota="TATKAL",
                    fare=session.fare_per_seat,
                    status="PENDING",
                    payment_status="UNPAID",
                    journey_date=session.journey_date,
                    expires_at=session.expires_at,
                )
                db.add(b)
            db.commit()
            bookings = db.query(Booking).filter(Booking.pnr == pnr).all()

        # Update all booking rows to CONFIRMED
        pay_ref = f"PAY{random.randint(10000000, 99999999)}"
        for b in bookings:
            b.status = "CONFIRMED"
            b.payment_status = "PAID"
            b.payment_method = method
            b.confirmed_at = now

        # Update all seats to BOOKED
        seat_ids = [b.seat_id for b in bookings]
        db.query(Seat).filter(Seat.id.in_(seat_ids)).update({
            "status": "BOOKED",
            "hold_expires_at": None,
        }, synchronize_session=False)

        if session:
            session.status = "CONFIRMED"

        # Create Payment record
        total_fare = sum(b.fare for b in bookings)
        pay_obj = Payment(
            payment_ref=pay_ref,
            booking_id=bookings[0].id if bookings else 1,
            pnr=pnr,
            amount=total_fare,
            method=method,
            status="SUCCESS",
            completed_at=now,
        )
        db.add(pay_obj)
        db.commit()

        _log_event(
            "PAYMENT_SUCCESS", f"PNR {pnr}", f"{len(bookings)} Seats",
            f"Payment of ₹{total_fare:,.0f} confirmed for PNR {pnr} ({len(bookings)} tickets)",
            "SUCCESS", db
        )
        db.commit()

        # Broadcast update
        asyncio.create_task(broadcast({
            "type": "seat_update",
            "pnr": pnr,
            "status": "BOOKED",
            "metrics": get_metrics(),
        }))

        ticket = format_unified_ticket(pnr, db)
        return {
            "success": True,
            "pnr": pnr,
            "payment_ref": pay_ref,
            "reason": f"Booking confirmed! Your PNR is {pnr}.",
            "ticket": ticket,
        }
    finally:
        if close_db:
            db.close()


def format_unified_ticket(pnr: str, db: Session) -> Dict[str, Any]:
    """Produce the unified E-Ticket JSON containing all passengers on this PNR."""
    session = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()
    bookings = db.query(Booking).filter(Booking.pnr == pnr).order_by(Booking.passenger_index).all()

    if not bookings and session:
        # Fallback ticket representation
        train = db.query(Train).filter(Train.id == session.train_id).first()
        return {
            "pnr": pnr,
            "status": session.status,
            "train_number": train.train_number if train else "99999",
            "train_name": train.name if train else "DEMO EXPRESS",
            "source": train.source if train else "Chennai",
            "destination": train.destination if train else "Bengaluru",
            "departure_time": train.departure_time if train else "10:00 AM",
            "arrival_time": train.arrival_time if train else "03:00 PM",
            "journey_date": session.journey_date,
            "seat_class": session.seat_class,
            "quota": "TATKAL",
            "total_passengers": session.passenger_count,
            "total_fare": session.total_fare,
            "payment_status": "PAID" if session.status == "CONFIRMED" else "UNPAID",
            "payment_method": "UPI",
            "payment_ref": f"PAY{pnr[2:]}",
            "booking_time": _now().strftime("%I:%M:%S %p"),
            "passengers": [
                {
                    "index": i + 1,
                    "name": f"Passenger {i + 1}",
                    "age": 28,
                    "gender": "Male",
                    "coach": session.coach,
                    "seat_number": s,
                    "fare": session.fare_per_seat,
                }
                for i, s in enumerate(session.seats_list.split(","))
            ],
        }

    b0 = bookings[0]
    train = db.query(Train).filter(Train.id == b0.train_id).first()
    pay = db.query(Payment).filter(Payment.pnr == pnr).first()
    pay_ref = pay.payment_ref if pay else f"PAY{pnr[2:]}"
    total_fare = sum(b.fare for b in bookings)

    confirmed_str = (
        b0.confirmed_at.strftime("%I:%M:%S %p")
        if b0.confirmed_at
        else _now().strftime("%I:%M:%S %p")
    )

    return {
        "pnr": pnr,
        "status": b0.status,
        "train_number": train.train_number if train else "99999",
        "train_name": train.name if train else "DEMO EXPRESS",
        "source": train.source if train else "Chennai",
        "destination": train.destination if train else "Bengaluru",
        "departure_time": train.departure_time if train else "10:00 AM",
        "arrival_time": train.arrival_time if train else "03:00 PM",
        "journey_date": b0.journey_date,
        "seat_class": b0.seat_class or "3A",
        "quota": b0.quota or "TATKAL",
        "total_passengers": len(bookings),
        "total_fare": total_fare,
        "payment_status": b0.payment_status,
        "payment_method": b0.payment_method or "UPI",
        "payment_ref": pay_ref,
        "booking_time": confirmed_str,
        "passengers": [
            {
                "index": b.passenger_index,
                "name": b.passenger_name,
                "age": b.passenger_age,
                "gender": b.passenger_gender,
                "coach": b.coach or "B1",
                "seat_number": b.seat_number,
                "fare": b.fare,
            }
            for b in bookings
        ],
    }


# ─── Release Hold / Cancellation ────────────────────────────────────────────

def release_seats_by_pnr(pnr: str, db: Session) -> Dict[str, Any]:
    """Release all held seats for an abandoned or cancelled booking session."""
    session = db.query(BookingSession).filter(BookingSession.pnr == pnr).first()
    bookings = db.query(Booking).filter(Booking.pnr == pnr).all()

    train_id = session.train_id if session else (bookings[0].train_id if bookings else 1)
    seat_nums = session.seats_list.split(",") if session else [b.seat_number for b in bookings]

    db.query(Seat).filter(Seat.train_id == train_id, Seat.seat_number.in_(seat_nums)).update({
        "status": "AVAILABLE",
        "held_by": None,
        "held_by_name": None,
        "held_pnr": None,
        "hold_expires_at": None,
    }, synchronize_session=False)

    if session:
        session.status = "CANCELLED"

    for b in bookings:
        b.status = "CANCELLED"
        b.payment_status = "REFUNDED"

    db.commit()

    asyncio.create_task(broadcast({
        "type": "seat_update",
        "seats": seat_nums,
        "status": "AVAILABLE",
        "metrics": get_metrics(),
    }))

    return {"success": True, "pnr": pnr, "seats_released": seat_nums}


# ─── Background Worker: Release Expired Multi-Seat Holds ─────────────────────

async def expire_holds_worker():
    """Periodically scans for expired seat holds and atomically frees the entire group."""
    print("[Worker] Expiry worker started.")
    while True:
        await asyncio.sleep(10)
        db = SessionLocal()
        try:
            now = _now()
            # 1. Expire BookingSessions
            expired_sessions = (
                db.query(BookingSession)
                .filter(BookingSession.status == "HELD", BookingSession.expires_at < now)
                .all()
            )
            for sess in expired_sessions:
                sess.status = "EXPIRED"
                seat_nums = sess.seats_list.split(",")
                db.query(Seat).filter(Seat.train_id == sess.train_id, Seat.seat_number.in_(seat_nums)).update({
                    "status": "AVAILABLE",
                    "held_by": None,
                    "held_by_name": None,
                    "held_pnr": None,
                    "hold_expires_at": None,
                }, synchronize_session=False)

                db.query(Booking).filter(Booking.pnr == sess.pnr, Booking.status == "PENDING").update({
                    "status": "EXPIRED"
                }, synchronize_session=False)

                _log_event(
                    "SEATS_RELEASED", f"PNR {sess.pnr}", sess.seats_list,
                    f"Hold on {sess.seats_list} expired — all seats released to AVAILABLE",
                    "WARNING", db
                )

            # 2. Safety catch for any loose held seats
            loose_expired = db.query(Seat).filter(Seat.status == "HELD", Seat.hold_expires_at < now).all()
            for s in loose_expired:
                s.status = "AVAILABLE"
                s.held_by = None
                s.held_by_name = None
                s.held_pnr = None
                s.hold_expires_at = None

            if expired_sessions or loose_expired:
                db.commit()
                asyncio.create_task(broadcast({
                    "type": "seat_update",
                    "status": "AVAILABLE",
                    "metrics": get_metrics(),
                }))
        except Exception as e:
            print(f"Expiry worker error: {e}")
        finally:
            db.close()


# ─── Concurrency Tests ───────────────────────────────────────────────────────

async def run_concurrency_test(user_a_id: int, user_b_id: int,
                               train_id: int, seat_class: str = "3A",
                               target_seat: str = "12A") -> Dict[str, Any]:
    """Race User A and User B for Seat 12A simultaneously."""
    db = SessionLocal()
    try:
        from backend.database import reset_demo_seats
        reset_demo_seats(db)
    finally:
        db.close()

    _log_event("CONCURRENCY_TEST_2", "SYSTEM", target_seat,
               f"Two-User Race for Seat {target_seat}: User #{user_a_id:04d} vs User #{user_b_id:04d}", "INFO")

    task_a = asyncio.create_task(submit_hold_request(
        train_id=train_id, seat_numbers=[target_seat], user_id=user_a_id, passenger_count=1,
        user_name="User A (Mokshith)"
    ))
    task_b = asyncio.create_task(submit_hold_request(
        train_id=train_id, seat_numbers=[target_seat], user_id=user_b_id, passenger_count=1,
        user_name="User B (Ananya)"
    ))

    result_a, result_b = await asyncio.gather(task_a, task_b)

    winner = "A" if result_a.get("success") else ("B" if result_b.get("success") else None)
    double_booking = result_a.get("success") and result_b.get("success")

    return {
        "target_seat": target_seat,
        "coach": "B1",
        "user_a": {
            "name": "User A",
            "success": result_a.get("success", False),
            "seat_number": target_seat,
            "pnr": result_a.get("pnr"),
            "reason": result_a.get("reason"),
        },
        "user_b": {
            "name": "User B",
            "success": result_b.get("success", False),
            "seat_number": target_seat,
            "pnr": result_b.get("pnr"),
            "reason": result_b.get("reason"),
        },
        "winner": winner,
        "double_booking_detected": double_booking,
        "seat_integrity": "PASSED" if not double_booking else "FAILED",
    }


async def run_three_user_test(user_a_id: int, user_b_id: int, user_c_id: int,
                              train_id: int, seat_class: str = "3A",
                              target_seat: str = "12A") -> Dict[str, Any]:
    """Race User A, User B, and User C for Seat 12A simultaneously."""
    db = SessionLocal()
    try:
        from backend.database import reset_demo_seats
        reset_demo_seats(db)
    finally:
        db.close()

    _log_event("CONCURRENCY_TEST_3", "SYSTEM", target_seat,
               f"Three-User Race for Seat {target_seat}: User #{user_a_id:04d}, #{user_b_id:04d}, #{user_c_id:04d}", "INFO")

    task_a = asyncio.create_task(submit_hold_request(
        train_id=train_id, seat_numbers=[target_seat], user_id=user_a_id, passenger_count=1, user_name="User A"
    ))
    task_b = asyncio.create_task(submit_hold_request(
        train_id=train_id, seat_numbers=[target_seat], user_id=user_b_id, passenger_count=1, user_name="User B"
    ))
    task_c = asyncio.create_task(submit_hold_request(
        train_id=train_id, seat_numbers=[target_seat], user_id=user_c_id, passenger_count=1, user_name="User C"
    ))

    result_a, result_b, result_c = await asyncio.gather(task_a, task_b, task_c)

    results = [("A", result_a), ("B", result_b), ("C", result_c)]
    winners = [name for name, r in results if r.get("success")]
    double_booking = len(winners) > 1

    return {
        "target_seat": target_seat,
        "coach": "B1",
        "concurrent_requests": 3,
        "available_seats": 1,
        "successful_holds": len(winners),
        "rejected_requests": 3 - len(winners),
        "double_bookings": 1 if double_booking else 0,
        "winner": winners[0] if winners else None,
        "user_a": {"success": result_a.get("success", False), "reason": result_a.get("reason"), "pnr": result_a.get("pnr")},
        "user_b": {"success": result_b.get("success", False), "reason": result_b.get("reason"), "pnr": result_b.get("pnr")},
        "user_c": {"success": result_c.get("success", False), "reason": result_c.get("reason"), "pnr": result_c.get("pnr")},
        "consistency": "PASSED" if not double_booking and len(winners) == 1 else "FAILED",
    }


async def run_simulation(num_users: int, train_id: int, seat_class: str = "3A") -> Dict[str, Any]:
    """1000 simulated users competing for the 5 Tatkal seats."""
    _metrics["simulation_running"] = True
    _metrics["total_requests"] = 0
    _metrics["active_requests"] = 0
    _metrics["successful_bookings"] = 0
    _metrics["failed_requests"] = 0
    _metrics["double_booking_attempts_prevented"] = 0
    _metrics["processing_times"] = []

    db = SessionLocal()
    try:
        from backend.database import reset_demo_seats
        reset_demo_seats(db)
    finally:
        db.close()

    sim_start = time.perf_counter()
    tatkal_pool = ["12A", "12B", "12C", "12D", "12E"]
    tasks = []

    for i in range(num_users):
        user_id = (i % 5000) + 1
        # Each user picks a seat from the tatkal pool
        desired_seat = tatkal_pool[i % len(tatkal_pool)]
        tasks.append(asyncio.create_task(
            submit_hold_request(
                train_id=train_id,
                seat_numbers=[desired_seat],
                user_id=user_id,
                passenger_count=1,
                user_name=f"User #{user_id:04d}",
            )
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - sim_start

    successes = [r for r in results if isinstance(r, dict) and r.get("success")]
    failures = [r for r in results if isinstance(r, dict) and not r.get("success")]

    seat_allocations = {}
    for s in successes:
        s_num = s.get("seats", ["12A"])[0]
        seat_allocations[s_num] = {
            "seat_number": s_num,
            "coach": "B1",
            "pnr": s.get("pnr"),
            "fare": 1245.0,
        }

    double_bookings = len(successes) - len(seat_allocations)
    _metrics["simulation_running"] = False

    return {
        "concurrent_requests": num_users,
        "available_seats": 5,
        "successful_bookings": len(successes),
        "failed_rejected": len(failures),
        "double_bookings": double_bookings,
        "elapsed_sec": round(elapsed, 2),
        "seat_allocations": seat_allocations,
        "consistency": "PASSED" if double_bookings == 0 else "FAILED",
        "no_double_booking": "PASSED" if double_bookings == 0 else "FAILED",
    }
