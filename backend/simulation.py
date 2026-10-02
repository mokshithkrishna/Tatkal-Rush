"""
simulation.py — Simulation utilities and Judge Demo scenarios for TATKAL RUSH.
Supports 2-user race, 3-user race, 1000-user stress test, and full 12-step guided story.
"""

from typing import List, Dict, Any

JUDGE_DEMO_STEPS = [
    {"step": 1, "title": "Train Search", "description": "Search for Chennai → Bengaluru, Quota: Tatkal, Class: 3A. Select DEMO EXPRESS (99999)."},
    {"step": 2, "title": "Coach B1 Seat Map", "description": "View Coach B1 layout: 15 seats booked, exactly 5 Tatkal seats (12A..12E) available."},
    {"step": 3, "title": "User A Selects Seat 12A", "description": "User A selects available Seat 12A and initiates booking."},
    {"step": 4, "title": "Two Users Race for Seat 12A", "description": "User A & User B both compete for Seat 12A simultaneously. Backend serializes via FIFO queue."},
    {"step": 5, "title": "Atomic Seat Allocation", "description": "User A wins Seat 12A (HELD). User B gets 'Sorry! Seat 12A was just taken by another user.'"},
    {"step": 6, "title": "Temporary Hold & Countdown", "description": "Seat 12A is locked for User A with 5-minute countdown (04:59..)."},
    {"step": 7, "title": "Passenger Details Entry", "description": "User enters Name, Age, Gender, Mobile Number and proceeds to Payment."},
    {"step": 8, "title": "Payment Simulation", "description": "User selects UPI / Card / Net Banking and confirms payment of ₹1,245."},
    {"step": 9, "title": "Digital E-Ticket Issued", "description": "Seat 12A → BOOKED. Unique PNR (TR8264917352) generated with QR code & confirmed E-Ticket."},
    {"step": 10, "title": "Payment Timeout Auto-Release", "description": "Background task monitors uncompleted holds and automatically releases expired seats."},
    {"step": 11, "title": "1000 Users Concurrency Rush", "description": "1000 users compete for remaining Tatkal inventory. Exactly 5 allocated, 995 rejected, 0 double bookings."},
    {"step": 12, "title": "Final Consistency Verified", "description": "Zero double bookings, database consistency PASSED, inventory integrity 100%."},
]

def get_judge_steps() -> List[Dict]:
    return JUDGE_DEMO_STEPS
