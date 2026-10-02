"""
Database configuration and initialization for TATKAL RUSH.
Uses SQLite with SQLAlchemy in WAL mode for optimal concurrent reads and atomic writes.
"""

import os
import datetime
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'tatkal_rush.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    pool_pre_ping=True,
    echo=False,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.models import Base, Train, Seat, User
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if DEMO EXPRESS with 99999 exists
        demo = db.query(Train).filter(Train.train_number == "99999").first()
        if not demo:
            # Clear old structure if any to re-seed cleanly
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            _seed_data(db)
    finally:
        db.close()


def reset_demo_seats(db):
    """
    Reset Tatkal seats to AVAILABLE for a fresh simulation or test.
    Preserves coach structure: 5 Tatkal seats AVAILABLE (12A..12E), general seats BOOKED.
    """
    from backend.models import Seat, Train, Booking, Request, Payment, BookingSession
    trains = db.query(Train).all()
    tatkal_seats = ["12A", "12B", "12C", "12D", "12E"]

    for train in trains:
        seat_ids = [s.id for s in db.query(Seat).filter(Seat.train_id == train.id).all()]
        if seat_ids:
            booking_ids = [b.id for b in db.query(Booking).filter(Booking.seat_id.in_(seat_ids)).all()]
            if booking_ids:
                db.query(Payment).filter(Payment.booking_id.in_(booking_ids)).delete(synchronize_session=False)
                db.query(Request).filter(Request.booking_id.in_(booking_ids)).delete(synchronize_session=False)
            db.query(Request).filter(Request.train_id == train.id).delete(synchronize_session=False)
            db.query(Booking).filter(Booking.train_id == train.id).delete(synchronize_session=False)
        db.query(BookingSession).filter(BookingSession.train_id == train.id).delete(synchronize_session=False)

        # Reset 12A..12E to AVAILABLE
        db.query(Seat).filter(
            Seat.train_id == train.id,
            Seat.seat_number.in_(tatkal_seats)
        ).update({
            "status": "AVAILABLE",
            "held_by": None,
            "held_by_name": None,
            "held_pnr": None,
            "hold_expires_at": None,
            "version": 0,
        }, synchronize_session=False)

        # Keep other seats BOOKED
        db.query(Seat).filter(
            Seat.train_id == train.id,
            ~Seat.seat_number.in_(tatkal_seats)
        ).update({
            "status": "BOOKED",
            "held_by": None,
            "held_by_name": None,
            "held_pnr": None,
            "hold_expires_at": None,
        }, synchronize_session=False)

    db.commit()


def _seed_data(db):
    """Seed authoritative stations, trains, routes, coach seats, and demo_user."""
    import hashlib
    from backend.models import Train, Station, TrainRoute, Seat, User

    # 1. Seed Demo User & Simulated Users
    demo_password_hash = hashlib.sha256("Tatkal@123".encode("utf-8")).hexdigest()
    demo_user = User(
        username="demo_user",
        password_hash=demo_password_hash,
        name="Demo Passenger",
        email="demo_user@tatkalrush.demo",
        phone="9876543210",
    )
    db.add(demo_user)

    for i in range(1, 5001):
        db.add(User(
            username=f"user_{i:04d}",
            password_hash=demo_password_hash,
            name=f"User #{i:04d}",
            email=f"user{i}@tatkalrush.demo",
            phone=f"98{i:08d}",
        ))
    db.flush()

    # 2. Seed Stations (Fuzzy autocomplete stations)
    stations_data = [
        {"code": "MAS", "name": "Chennai Central", "city": "Chennai", "state": "Tamil Nadu"},
        {"code": "MS", "name": "Chennai Egmore", "city": "Chennai", "state": "Tamil Nadu"},
        {"code": "TBM", "name": "Tambaram", "city": "Chennai", "state": "Tamil Nadu"},
        {"code": "SBC", "name": "KSR Bengaluru", "city": "Bengaluru", "state": "Karnataka"},
        {"code": "BNC", "name": "Bengaluru Cantt", "city": "Bengaluru", "state": "Karnataka"},
        {"code": "YNK", "name": "Yelahanka Jn", "city": "Bengaluru", "state": "Karnataka"},
        {"code": "KJM", "name": "Krishnarajapuram", "city": "Bengaluru", "state": "Karnataka"},
        {"code": "KPD", "name": "Katpadi Jn", "city": "Vellore", "state": "Tamil Nadu"},
        {"code": "JTJ", "name": "Jolarpettai Jn", "city": "Tirupattur", "state": "Tamil Nadu"},
        {"code": "BWT", "name": "Bangarapet", "city": "Kolar", "state": "Karnataka"},
        {"code": "NDLS", "name": "New Delhi", "city": "New Delhi", "state": "Delhi"},
        {"code": "NZM", "name": "Hazrat Nizamuddin", "city": "New Delhi", "state": "Delhi"},
        {"code": "CSMT", "name": "Mumbai CSMT", "city": "Mumbai", "state": "Maharashtra"},
        {"code": "MMCT", "name": "Mumbai Central", "city": "Mumbai", "state": "Maharashtra"},
        {"code": "HYB", "name": "Hyderabad Deccan", "city": "Hyderabad", "state": "Telangana"},
        {"code": "SC", "name": "Secunderabad Jn", "city": "Hyderabad", "state": "Telangana"},
    ]
    for s_info in stations_data:
        db.add(Station(**s_info))
    db.flush()

    # 3. Seed Trains
    trains = [
        Train(
            train_number="99999",
            name="DEMO EXPRESS",
            train_type="Tatkal Special SF",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="10:00 AM",
            arrival_time="03:00 PM",
            duration="5h 00m",
            distance_km=362,
            running_days="M, T, W, T, F, S, S",
            classes_available="SL, 3A, 2A, 1A",
            coach_composition="LOCO-SLR-GS-S1-S2-B1-B2-A1-H1-GS-SLR",
            base_fare=1245.0,
            total_seats_sl=120,
            total_seats_3a=20,
            total_seats_2a=30,
        ),
        Train(
            train_number="12608",
            name="Lalbagh SF Express",
            train_type="Superfast Express",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="06:20 AM",
            arrival_time="12:15 PM",
            duration="5h 55m",
            distance_km=362,
            running_days="M, T, W, T, F, S, S",
            classes_available="2S, CC, SL, 3A, 2A",
            coach_composition="LOCO-SLR-GS-D1-D2-C1-C2-B1-B2-A1-GS-SLR",
            base_fare=1180.0,
            total_seats_sl=120,
            total_seats_3a=60,
            total_seats_2a=30,
        ),
        Train(
            train_number="12028",
            name="Shatabdi Express",
            train_type="Shatabdi Express",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="06:00 AM",
            arrival_time="11:00 AM",
            duration="5h 00m",
            distance_km=362,
            running_days="M, W, Th, F, Sa, Su",
            classes_available="CC, EC, 3A, 2A",
            coach_composition="LOCO-EOG-C1-C2-C3-C4-C5-B1-E1-E2-EOG",
            base_fare=1450.0,
            total_seats_sl=0,
            total_seats_3a=50,
            total_seats_2a=20,
        ),
        Train(
            train_number="22625",
            name="Chennai - Bengaluru Double Decker",
            train_type="AC Double Decker SF",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="07:25 AM",
            arrival_time="01:10 PM",
            duration="5h 45m",
            distance_km=362,
            running_days="M, T, W, T, F, S, S",
            classes_available="CC, 3A, 2A",
            coach_composition="LOCO-EOG-C1-C2-C3-C4-C5-B1-C6-C7-EOG",
            base_fare=1290.0,
            total_seats_sl=0,
            total_seats_3a=40,
            total_seats_2a=15,
        ),
        Train(
            train_number="20607",
            name="Vande Bharat Express",
            train_type="Vande Bharat SF",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="05:50 AM",
            arrival_time="10:15 AM",
            duration="4h 25m",
            distance_km=362,
            running_days="M, T, Th, F, Sa, Su",
            classes_available="CC, EC, 3A",
            coach_composition="DTC-NDTC-MC-TC-B1-EC-MC2-DTC2",
            base_fare=1680.0,
            total_seats_sl=0,
            total_seats_3a=60,
            total_seats_2a=0,
        ),
        Train(
            train_number="12639",
            name="Brindavan Express",
            train_type="Superfast Express",
            source="Chennai Central (MAS)",
            source_code="MAS",
            destination="KSR Bengaluru (SBC)",
            destination_code="SBC",
            departure_time="07:40 AM",
            arrival_time="01:40 PM",
            duration="6h 00m",
            distance_km=362,
            running_days="M, T, W, T, F, S, S",
            classes_available="2S, CC, SL, 3A",
            coach_composition="LOCO-SLR-GS-D1-D2-D3-B1-C1-C2-GS-SLR",
            base_fare=950.0,
            total_seats_sl=150,
            total_seats_3a=30,
            total_seats_2a=0,
        ),
    ]
    db.add_all(trains)
    db.flush()

    # 4. Seed Detailed Routes and Halts for Each Train
    sample_routes = [
        {"stop_number": 1, "station_code": "MAS", "station_name": "Chennai Central", "arrival_time": "--", "departure_time": "06:00 AM", "day_number": 1, "distance_from_source_km": 0, "halt_duration_min": 0},
        {"stop_number": 2, "station_code": "AJJ", "station_name": "Arakkonam Jn", "arrival_time": "06:58 AM", "departure_time": "07:00 AM", "day_number": 1, "distance_from_source_km": 69, "halt_duration_min": 2},
        {"stop_number": 3, "station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "07:48 AM", "departure_time": "07:50 AM", "day_number": 1, "distance_from_source_km": 130, "halt_duration_min": 2},
        {"stop_number": 4, "station_code": "JTJ", "station_name": "Jolarpettai Jn", "arrival_time": "08:48 AM", "departure_time": "08:50 AM", "day_number": 1, "distance_from_source_km": 214, "halt_duration_min": 2},
        {"stop_number": 5, "station_code": "BWT", "station_name": "Bangarapet", "arrival_time": "09:48 AM", "departure_time": "09:50 AM", "day_number": 1, "distance_from_source_km": 289, "halt_duration_min": 2},
        {"stop_number": 6, "station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "10:24 AM", "departure_time": "10:25 AM", "day_number": 1, "distance_from_source_km": 348, "halt_duration_min": 1},
        {"stop_number": 7, "station_code": "BNC", "station_name": "Bengaluru Cantt", "arrival_time": "10:40 AM", "departure_time": "10:42 AM", "day_number": 1, "distance_from_source_km": 358, "halt_duration_min": 2},
        {"stop_number": 8, "station_code": "SBC", "station_name": "KSR Bengaluru", "arrival_time": "11:00 AM", "departure_time": "--", "day_number": 1, "distance_from_source_km": 362, "halt_duration_min": 0},
    ]

    for train in trains:
        for r_info in sample_routes:
            db.add(TrainRoute(
                train_id=train.id,
                station_code=r_info["station_code"],
                station_name=r_info["station_name"],
                stop_number=r_info["stop_number"],
                arrival_time=r_info["arrival_time"],
                departure_time=r_info["departure_time"],
                day_number=r_info["day_number"],
                distance_from_source_km=r_info["distance_from_source_km"],
                halt_duration_min=r_info["halt_duration_min"],
            ))

    # 5. Authoritative Coach B1 Layout for EVERY train:
    # Bay 1 (1A..1F) - BOOKED
    # Bay 2 (2A..2F) - BOOKED
    # Bay 3: 12A, 12B, 12C, 12D, 12E - AVAILABLE (Tatkal Special Quota)
    authoritative_coach_seats = [
        # Bay 1 (General Booked)
        ("1A", "Lower", "General", "BOOKED", False),
        ("1B", "Middle", "General", "BOOKED", False),
        ("1C", "Upper", "General", "BOOKED", False),
        ("1D", "Side Lower", "General", "BOOKED", False),
        ("1E", "Side Upper", "General", "BOOKED", False),
        ("1F", "Window", "General", "BOOKED", False),

        # Bay 2 (General Booked)
        ("2A", "Lower", "General", "BOOKED", False),
        ("2B", "Middle", "General", "BOOKED", False),
        ("2C", "Upper", "General", "BOOKED", False),
        ("2D", "Side Lower", "General", "BOOKED", False),
        ("2E", "Side Upper", "General", "BOOKED", False),
        ("2F", "Window", "General", "BOOKED", False),

        # Bay 3 (Tatkal Special Quota — 5 AVAILABLE Seats)
        ("12A", "Lower", "Tatkal", "AVAILABLE", True),
        ("12B", "Middle", "Tatkal", "AVAILABLE", True),
        ("12C", "Upper", "Tatkal", "AVAILABLE", True),
        ("12D", "Side Lower", "Tatkal", "AVAILABLE", True),
        ("12E", "Side Upper", "Tatkal", "AVAILABLE", True),
    ]

    for train in trains:
        for seat_num, berth, quota, status, is_tatkal in authoritative_coach_seats:
            db.add(Seat(
                train_id=train.id,
                coach="B1",
                seat_number=seat_num,
                berth_type=berth,
                seat_class="3A",
                quota=quota,
                is_tatkal=is_tatkal,
                status=status,
                price=train.base_fare or 1245.0,
                version=0,
            ))

    db.commit()
    print("[OK] Authoritative railway database initialized with stations, trains, routes, and seats successfully.")
