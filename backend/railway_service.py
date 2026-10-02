"""
Railway Data Service for TATKAL RUSH.
Clean architectural service layer interfacing between FastAPI and the railway data source.
Defaults automatically to DemoRailwayDataService when no external authorized API is configured.

NOTE: All data is clearly labeled as simulated/demo train data.
DO NOT use, store, scrape, or hard-code any real IRCTC credentials, OTP, CAPTCHA, or private account data.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from backend.models import Train, Station, TrainRoute, Seat


class DemoRailwayDataService:
    """Authoritative Demo Data Service providing realistic train search, schedules, and fare lookups."""

    @staticmethod
    def search_stations(query: str, db: Session) -> List[Dict[str, Any]]:
        """Search stations by name, city, or station code with fuzzy autocomplete matching."""
        if not query or len(query.strip()) < 1:
            stations = db.query(Station).limit(10).all()
        else:
            q = query.strip()
            stations = db.query(Station).filter(
                or_(
                    Station.name.ilike(f"%{q}%"),
                    Station.code.ilike(f"%{q}%"),
                    Station.city.ilike(f"%{q}%")
                )
            ).limit(12).all()

        return [
            {
                "id": s.id,
                "name": s.name,
                "code": s.code,
                "city": s.city,
                "state": s.state,
                "display": f"{s.name} ({s.code})",
            }
            for s in stations
        ]

    @staticmethod
    def search_trains(
        source: str,
        destination: str,
        journey_date: str = "02 October 2026",
        quota: str = "Tatkal",
        seat_class: str = "3A",
        filters: Optional[Dict[str, Any]] = None,
        db: Session = None,
    ) -> Dict[str, Any]:
        """Search trains with multi-parameter filtering and Tatkal quota inventory lookup."""
        filters = filters or {}
        source_clean = source.strip()
        dest_clean = destination.strip()

        # Handle station codes in parentheses like "Chennai Central (MAS)"
        if "(" in source_clean and ")" in source_clean:
            source_clean = source_clean.split("(")[-1].replace(")", "").strip()
        if "(" in dest_clean and ")" in dest_clean:
            dest_clean = dest_clean.split("(")[-1].replace(")", "").strip()

        query = db.query(Train).filter(Train.is_active == True)

        # Flexible matching across name or code
        if source_clean:
            query = query.filter(
                or_(
                    Train.source.ilike(f"%{source_clean}%"),
                    Train.source_code.ilike(f"%{source_clean}%")
                )
            )
        if dest_clean:
            query = query.filter(
                or_(
                    Train.destination.ilike(f"%{dest_clean}%"),
                    Train.destination_code.ilike(f"%{dest_clean}%")
                )
            )

        trains = query.all()

        # Fallback to all trains if specific query yielded 0 results in demo mode
        if not trains and db:
            trains = db.query(Train).filter(Train.is_active == True).all()

        results = []
        for t in trains:
            # Query seats for this train
            seats = db.query(Seat).filter(Seat.train_id == t.id).all()
            tatkal_seats = [s for s in seats if s.is_tatkal]
            available_tatkal = sum(1 for s in tatkal_seats if s.status == "AVAILABLE")
            total_tatkal = len(tatkal_seats) if tatkal_seats else 5

            # Calculate fare multiplier based on class and quota
            base = t.base_fare or 1245.0
            fare_calc = base
            if seat_class == "SL":
                fare_calc = round(base * 0.45, 0)
            elif seat_class == "2A":
                fare_calc = round(base * 1.55, 0)
            elif seat_class == "1A":
                fare_calc = round(base * 2.30, 0)
            elif seat_class == "CC":
                fare_calc = round(base * 0.75, 0)
            elif seat_class == "EC":
                fare_calc = round(base * 1.80, 0)

            if quota in ["Tatkal", "Premium Tatkal"]:
                fare_calc = round(fare_calc * 1.15, 0)

            # Apply filters
            if filters.get("ac_only") and seat_class == "SL":
                continue
            if filters.get("sleeper_only") and seat_class != "SL":
                continue
            if filters.get("available_only") and available_tatkal == 0:
                continue

            results.append({
                "id": t.id,
                "train_number": t.train_number,
                "name": t.name,
                "train_type": t.train_type or "Superfast Express",
                "source": t.source,
                "source_code": t.source_code or "MAS",
                "destination": t.destination,
                "destination_code": t.destination_code or "SBC",
                "departure_time": t.departure_time,
                "arrival_time": t.arrival_time,
                "duration": t.duration or "5h 00m",
                "distance_km": t.distance_km or 362,
                "running_days": t.running_days or "M, T, W, T, F, S, S",
                "classes_available": t.classes_available or "SL, 3A, 2A",
                "coach": "B1",
                "seat_class": seat_class,
                "quota": quota,
                "fare": fare_calc,
                "available_tatkal": available_tatkal,
                "total_tatkal": total_tatkal,
                "is_demo": t.train_number in ["99999", "DEMO-99"],
                "availability_label": f"AVAILABLE ({available_tatkal})" if available_tatkal > 0 else "WAITLIST",
                "status_badge": "🟢 AVAILABLE" if available_tatkal > 0 else "🔴 REGRET / WL",
            })

        return {
            "trains": results,
            "journey_date": journey_date,
            "quota": quota,
            "seat_class": seat_class,
            "disclaimer": "Demo train data – availability and fares are simulated for demonstration.",
        }

    @staticmethod
    def get_train_details(train_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive train details, coach layout, classes, and schedule timeline."""
        train = db.query(Train).filter(Train.id == train_id).first()
        if not train:
            return None

        # Route schedule
        routes = db.query(TrainRoute).filter(TrainRoute.train_id == train.id).order_by(TrainRoute.stop_number).all()
        schedule = [
            {
                "stop_number": r.stop_number,
                "station_code": r.station_code,
                "station_name": r.station_name,
                "arrival_time": r.arrival_time,
                "departure_time": r.departure_time,
                "day_number": r.day_number,
                "distance_km": r.distance_from_source_km,
                "halt_duration_min": r.halt_duration_min,
            }
            for r in routes
        ]

        # If no routes stored in DB yet, return standard route
        if not schedule:
            schedule = [
                {"stop_number": 1, "station_code": train.source_code, "station_name": train.source, "arrival_time": "--", "departure_time": train.departure_time, "day_number": 1, "distance_km": 0, "halt_duration_min": 0},
                {"stop_number": 2, "station_code": "KPD", "station_name": "Katpadi Jn", "arrival_time": "11:45 AM", "departure_time": "11:50 AM", "day_number": 1, "distance_km": 130, "halt_duration_min": 5},
                {"stop_number": 3, "station_code": "JTJ", "station_name": "Jolarpettai Jn", "arrival_time": "12:50 PM", "departure_time": "12:55 PM", "day_number": 1, "distance_km": 214, "halt_duration_min": 5},
                {"stop_number": 4, "station_code": "BWT", "station_name": "Bangarapet", "arrival_time": "01:55 PM", "departure_time": "01:57 PM", "day_number": 1, "distance_km": 289, "halt_duration_min": 2},
                {"stop_number": 5, "station_code": "KJM", "station_name": "Krishnarajapuram", "arrival_time": "02:35 PM", "departure_time": "02:37 PM", "day_number": 1, "distance_km": 348, "halt_duration_min": 2},
                {"stop_number": 6, "station_code": train.destination_code, "station_name": train.destination, "arrival_time": train.arrival_time, "departure_time": "--", "day_number": 1, "distance_km": train.distance_km or 362, "halt_duration_min": 0},
            ]

        # Seat inventory stats
        seats = db.query(Seat).filter(Seat.train_id == train.id).all()
        tatkal_seats = [s for s in seats if s.is_tatkal]
        available_tatkal = sum(1 for s in tatkal_seats if s.status == "AVAILABLE")
        held_tatkal = sum(1 for s in tatkal_seats if s.status == "HELD")
        booked_tatkal = sum(1 for s in tatkal_seats if s.status == "BOOKED")

        # Classes & Fares breakdown
        classes_info = [
            {"class_code": "3A", "class_name": "AC 3 Tier", "fare": train.base_fare or 1245.0, "tatkal_available": available_tatkal, "total": 20, "status": "AVAILABLE" if available_tatkal > 0 else "WAITLIST"},
            {"class_code": "2A", "class_name": "AC 2 Tier", "fare": round((train.base_fare or 1245.0) * 1.55, 0), "tatkal_available": 2, "total": 30, "status": "AVAILABLE"},
            {"class_code": "SL", "class_name": "Sleeper", "fare": round((train.base_fare or 1245.0) * 0.45, 0), "tatkal_available": 12, "total": 120, "status": "AVAILABLE"},
            {"class_code": "1A", "class_name": "AC First Class", "fare": round((train.base_fare or 1245.0) * 2.30, 0), "tatkal_available": 1, "total": 10, "status": "AVAILABLE"},
        ]

        return {
            "id": train.id,
            "train_number": train.train_number,
            "name": train.name,
            "train_type": train.train_type or "Superfast Express",
            "source": train.source,
            "source_code": train.source_code or "MAS",
            "destination": train.destination,
            "destination_code": train.destination_code or "SBC",
            "departure_time": train.departure_time,
            "arrival_time": train.arrival_time,
            "duration": train.duration or "5h 00m",
            "distance_km": train.distance_km or 362,
            "running_days": train.running_days or "M, T, W, T, F, S, S",
            "coach_composition": train.coach_composition or "LOCO-SLR-GS-S1-S2-S3-B1-B2-A1-GS-SLR",
            "total_halts": len(schedule) - 2 if len(schedule) >= 2 else 4,
            "tatkal_stats": {
                "available": available_tatkal,
                "held": held_tatkal,
                "booked": booked_tatkal,
                "total": len(tatkal_seats) if tatkal_seats else 5,
            },
            "classes": classes_info,
            "schedule": schedule,
            "disclaimer": "Demo train schedule and halts for demonstration.",
        }


# Global service instance
RailwayDataService = DemoRailwayDataService
