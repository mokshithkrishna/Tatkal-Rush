"""
SQLAlchemy ORM models for TATKAL RUSH.
Authoritative schema supporting single and multi-seat bookings (1 to 3 seats per transaction),
atomic conditional updates, idempotency keys, Coach B1 layout, Station routes, and concurrency state tracking.
"""

import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean,
    ForeignKey, Text, Float
)
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=True, index=True)
    password_hash = Column(String(200), nullable=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    phone = Column(String(15))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")
    requests = relationship("Request", back_populates="user")


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), default="India")


class Train(Base):
    __tablename__ = "trains"

    id = Column(Integer, primary_key=True, index=True)
    train_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    train_type = Column(String(50), default="Superfast Express")
    source = Column(String(100), nullable=False)
    source_code = Column(String(10), default="MAS")
    destination = Column(String(100), nullable=False)
    destination_code = Column(String(10), default="SBC")
    departure_time = Column(String(20), nullable=False)
    arrival_time = Column(String(20), nullable=False)
    duration = Column(String(20), default="5h 00m")
    distance_km = Column(Integer, default=362)
    running_days = Column(String(50), default="M, T, W, T, F, S, S")
    classes_available = Column(String(50), default="SL, 3A, 2A")
    coach_composition = Column(String(200), default="LOCO-SLR-GS-S1-S2-S3-B1-B2-A1-GS-SLR")
    base_fare = Column(Float, default=1245.0)
    total_seats_sl = Column(Integer, default=120)
    total_seats_3a = Column(Integer, default=20)
    total_seats_2a = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)

    seats = relationship("Seat", back_populates="train")
    bookings = relationship("Booking", back_populates="train")
    routes = relationship("TrainRoute", back_populates="train", order_by="TrainRoute.stop_number")


class TrainRoute(Base):
    __tablename__ = "train_routes"

    id = Column(Integer, primary_key=True, index=True)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    station_code = Column(String(10), nullable=False)
    station_name = Column(String(100), nullable=False)
    stop_number = Column(Integer, default=1)
    arrival_time = Column(String(20), default="--")
    departure_time = Column(String(20), default="--")
    day_number = Column(Integer, default=1)
    distance_from_source_km = Column(Integer, default=0)
    halt_duration_min = Column(Integer, default=2)

    train = relationship("Train", back_populates="routes")


class Seat(Base):
    __tablename__ = "seats"

    id = Column(Integer, primary_key=True, index=True)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    coach = Column(String(10), default="B1")
    seat_number = Column(String(10), nullable=False, index=True)   # "12A", "12B", "12C", "12D", "12E", "1A"..
    berth_type = Column(String(30), default="Lower")              # Lower, Middle, Upper, Tatkal Side, etc.
    seat_class = Column(String(5), default="3A")                  # 3A
    is_tatkal = Column(Boolean, default=True)
    quota = Column(String(20), default="Tatkal")
    price = Column(Float, default=1245.0)


    # Concurrency-critical state: AVAILABLE | SELECTED | HELD | BOOKED
    status = Column(String(20), default="AVAILABLE", index=True)
    version = Column(Integer, default=0)
    held_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    held_by_name = Column(String(100), nullable=True)
    held_pnr = Column(String(20), nullable=True, index=True)      # Associated PNR session
    hold_expires_at = Column(DateTime, nullable=True)

    train = relationship("Train", back_populates="seats")
    bookings = relationship("Booking", back_populates="seat")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    pnr = Column(String(20), nullable=False, index=True)
    booking_ref = Column(String(20), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=False)
    coach = Column(String(10), default="B1")
    seat_number = Column(String(10), nullable=False)

    # Passenger Details
    passenger_index = Column(Integer, default=1)
    passenger_name = Column(String(100), nullable=False)
    passenger_age = Column(Integer, default=28)
    passenger_gender = Column(String(20), default="Male")
    passenger_phone = Column(String(20), default="9876543210")

    seat_class = Column(String(5), default="3A")
    quota = Column(String(20), default="TATKAL")
    fare = Column(Float, default=1245.0)

    # Status: PENDING | CONFIRMED | CANCELLED | EXPIRED
    status = Column(String(20), default="PENDING")
    payment_status = Column(String(20), default="UNPAID") # UNPAID | PAID | REFUNDED
    payment_method = Column(String(50), nullable=True)

    journey_date = Column(String(30), default="02 October 2026")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="bookings")
    train = relationship("Train", back_populates="bookings")
    seat = relationship("Seat", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class BookingSession(Base):
    __tablename__ = "booking_sessions"

    id = Column(Integer, primary_key=True, index=True)
    pnr = Column(String(20), unique=True, nullable=False, index=True)
    idempotency_key = Column(String(64), unique=True, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    coach = Column(String(10), default="B1")
    seat_class = Column(String(5), default="3A")
    seats_list = Column(String(100), nullable=False)     # "12A,12C,12E"
    passenger_count = Column(Integer, default=1)
    fare_per_seat = Column(Float, default=1245.0)
    total_fare = Column(Float, default=1245.0)
    journey_date = Column(String(30), default="02 October 2026")
    status = Column(String(20), default="HELD")          # HELD | CONFIRMED | EXPIRED | CANCELLED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)
    request_ref = Column(String(20), unique=True, nullable=False)
    idempotency_key = Column(String(64), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=True)
    seat_number = Column(String(10), nullable=True)
    seat_class = Column(String(5), default="3A")
    passenger_count = Column(Integer, default=1)

    queue_position = Column(Integer, nullable=True)
    status = Column(String(20), default="QUEUED")
    failure_reason = Column(String(200), nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Float, nullable=True)

    user = relationship("User", back_populates="requests")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_ref = Column(String(20), unique=True, nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    pnr = Column(String(20), nullable=True, index=True)
    amount = Column(Float, default=1245.0)
    method = Column(String(50), default="UPI")

    status = Column(String(20), default="PENDING")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    booking = relationship("Booking", back_populates="payment")


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    event_type = Column(String(50))
    user_ref = Column(String(50))
    seat_ref = Column(String(50))
    message = Column(Text)
    severity = Column(String(10), default="INFO")

    @property
    def timestamp_str(self):
        return self.timestamp.strftime("%H:%M:%S.%f")[:-3]
