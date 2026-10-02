import re
import unittest
import requests

BASE_URL = "http://127.0.0.1:8000"

class TestBookingNavigationAndScroll(unittest.TestCase):
    def test_frontend_codebase_integrity(self):
        """Verify no button lacks type, no unhandled href='#', no window.scrollTo(0,0) in stage updates"""
        frontend_files = [
            'frontend/index.html',
            'frontend/app.js',
            'frontend/login.html',
            'frontend/booking.html',
            'frontend/dashboard.html'
        ]

        for path in frontend_files:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. No button without type
            missing_types = [b for b in re.findall(r'<button\b[^>]*>', content) if 'type=' not in b]
            self.assertEqual(len(missing_types), 0, f"Found buttons missing type in {path}: {missing_types}")

            # 2. No unhandled hash hrefs
            hash_hrefs = re.findall(r'<a\b[^>]*href=["\']#[^"\']*["\'][^>]*>', content)
            self.assertEqual(len(hash_hrefs), 0, f"Found unhandled hash href in {path}: {hash_hrefs}")

            # 3. No window.scrollTo(0,0) or { top: 0 }
            self.assertNotIn("window.scrollTo(0, 0)", content, f"Found window.scrollTo(0,0) in {path}")
            self.assertNotIn("window.scrollTo(0,0)", content, f"Found window.scrollTo(0,0) in {path}")
            self.assertNotIn("window.scrollTo({ top: 0", content, f"Found window.scrollTo({ top: 0 }) in {path}")

    def test_full_booking_flow_api(self):
        """Test the complete multi-step booking state cycle without losing data"""
        session = requests.Session()

        # Step 1: Login
        res_login = session.post(f"{BASE_URL}/api/auth/login", json={"username": "demo_user", "password": "Tatkal@123"})
        self.assertEqual(res_login.status_code, 200)

        # Step 2: Search trains
        res_search = session.post(f"{BASE_URL}/api/search", json={
            "source": "Chennai Central (MAS)",
            "destination": "KSR Bengaluru (SBC)",
            "journey_date": "15 October 2026",
            "quota": "Tatkal",
            "seat_class": "3A",
            "passengers": 3,
            "filters": {"available_only": False, "flexible_date": False, "ac_only": False, "sleeper_only": False}
        })
        self.assertEqual(res_search.status_code, 200)
        trains = res_search.json().get("trains", [])
        self.assertGreater(len(trains), 0)
        target_train = trains[0]

        # Step 3: View train details
        res_details = session.get(f"{BASE_URL}/api/trains/{target_train['id']}")
        self.assertEqual(res_details.status_code, 200)
        self.assertIn("schedule", res_details.json())

        # Step 4: Seat map
        res_seats = session.get(f"{BASE_URL}/api/seats?train_id={target_train['id']}")
        self.assertEqual(res_seats.status_code, 200)
        seats = [s["seat_number"] for s in res_seats.json().get("seats", []) if s.get("status") == "AVAILABLE"]
        self.assertTrue(len(seats) >= 3, f"Available seats: {seats}")
        selected_seats = ["12A", "12C", "12E"]

        # Step 5: Hold seats
        import uuid
        res_hold = session.post(f"{BASE_URL}/booking/hold", json={
            "train_id": target_train["id"],
            "seat_ids": selected_seats,
            "passenger_count": 3,
            "idempotency_key": f"test-nav-{uuid.uuid4()}",
            "user_id": 1,
            "journey_date": "15 October 2026",
            "user_name": "Demo Family"
        })
        self.assertEqual(res_hold.status_code, 200)
        pnr = res_hold.json()["pnr"]

        # Step 6: Passenger details
        res_passengers = session.post(f"{BASE_URL}/api/passenger-details", json={
            "pnr": pnr,
            "passengers": [
                {"name": "Mokshith Krishna", "age": 28, "gender": "Male"},
                {"name": "Rahul Sharma", "age": 31, "gender": "Male"},
                {"name": "Ananya Iyer", "age": 26, "gender": "Female"}
            ],
            "primary_phone": "9876543210"
        })
        self.assertEqual(res_passengers.status_code, 200)

        # Step 7: Payment
        res_pay = session.post(f"{BASE_URL}/api/payment", json={"pnr": pnr, "method": "UPI"})
        self.assertEqual(res_pay.status_code, 200)
        ticket = res_pay.json()["ticket"]
        self.assertEqual(ticket["pnr"], pnr)
        self.assertEqual(ticket["status"], "CONFIRMED")
        self.assertEqual(len(ticket["passengers"]), 3)

        # Step 8: View ticket
        res_ticket = session.get(f"{BASE_URL}/api/ticket/{pnr}")
        self.assertEqual(res_ticket.status_code, 200)
        self.assertEqual(res_ticket.json()["ticket"]["pnr"], pnr)
        print(f"[TEST PASS] Successfully verified full 8-stage booking lifecycle for PNR {pnr}")

if __name__ == "__main__":
    unittest.main()
