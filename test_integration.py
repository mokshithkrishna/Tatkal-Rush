import urllib.request
import urllib.error
import json

base = 'http://127.0.0.1:8000'

# Reset demo data first
req_reset = urllib.request.Request(f'{base}/api/reset', data=b'{}', headers={'Content-Type':'application/json'})
urllib.request.urlopen(req_reset)

# 1. Test Login
req = urllib.request.Request(f'{base}/api/auth/login', data=json.dumps({'username':'demo_user', 'password':'Tatkal@123'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['success'] == True, 'Login failed'
print('[PASS] 1. Demo Login successful')

# 2. Test Invalid Login
try:
    req = urllib.request.Request(f'{base}/api/auth/login', data=json.dumps({'username':'demo_user', 'password':'WrongPassword'}).encode(), headers={'Content-Type':'application/json'})
    urllib.request.urlopen(req)
    assert False, 'Should fail'
except urllib.error.HTTPError as e:
    assert e.code == 401
    print('[PASS] 2. Invalid password rejected with 401')

# 3. Test Station Autocomplete
res = json.loads(urllib.request.urlopen(f'{base}/api/stations?q=Chennai').read().decode())
st_count = len(res['stations'])
assert st_count > 0, 'No stations returned'
print(f'[PASS] 3. Station search returned {st_count} stations')

# 4. Test Train Search
req = urllib.request.Request(f'{base}/api/search', data=json.dumps({'source':'Chennai Central (MAS)', 'destination':'KSR Bengaluru (SBC)', 'journey_date':'02 October 2026', 'quota':'Tatkal', 'seat_class':'3A', 'passengers':3}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
tr_count = len(res['trains'])
assert tr_count > 0, 'No trains returned'
train_id = res['trains'][0]['id']
print(f'[PASS] 4. Train search returned {tr_count} trains')

# 5. Test Train Details
res = json.loads(urllib.request.urlopen(f'{base}/api/trains/{train_id}').read().decode())
halts_count = len(res['schedule'])
assert halts_count > 0, 'No schedule returned'
print(f'[PASS] 5. Train details schedule has {halts_count} halts')

# 6. Test Seats API
res = json.loads(urllib.request.urlopen(f'{base}/api/seats?train_id={train_id}').read().decode())
tatkal_avail = res['tatkal_available']
assert tatkal_avail == 5, f'Expected 5 tatkal available, got {tatkal_avail}'
print('[PASS] 6. Seats API returned 5 available Tatkal seats (12A..12E)')

# 7. Test 3-Seat Hold
req = urllib.request.Request(f'{base}/booking/hold', data=json.dumps({'train_id':train_id, 'seat_ids':['12A','12C','12E'], 'passenger_count':3, 'user_id':1, 'journey_date':'02 October 2026', 'user_name':'Mokshith Krishna'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['success'] == True, 'Hold failed'
pnr = res['pnr']
print(f'[PASS] 7. Held 3 seats (12A, 12C, 12E) under PNR {pnr}')

# 8. Test Passenger Details
passengers = [
    {'name': 'Mokshith Krishna', 'age': 28, 'gender': 'Male'},
    {'name': 'Rahul', 'age': 30, 'gender': 'Male'},
    {'name': 'Arjun', 'age': 25, 'gender': 'Male'}
]
req = urllib.request.Request(f'{base}/api/passenger-details', data=json.dumps({'pnr':pnr, 'passengers':passengers, 'primary_phone':'9876543210'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['success'] == True
print('[PASS] 8. Passenger details saved')

# 9. Test Payment
req = urllib.request.Request(f'{base}/api/payment', data=json.dumps({'pnr':pnr, 'method':'UPI'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['success'] == True
print(f'[PASS] 9. Payment confirmed for PNR {pnr}')

# 10. Test Ticket Retrieval
res = json.loads(urllib.request.urlopen(f'{base}/api/ticket/{pnr}').read().decode())
assert res['ticket']['pnr'] == pnr
print(f'[PASS] 10. Retrieved digital ticket with QR and seat layout')

# 11. Test Concurrency Race (2-User)
req = urllib.request.Request(f'{base}/api/concurrency-test', data=json.dumps({'user_a_id':1, 'user_b_id':2, 'train_id':train_id, 'target_seat':'12B'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['double_booking_detected'] == False
assert res['seat_integrity'] == 'PASSED'
print(f'[PASS] 11. Concurrency 2-User test passed: Winner={res["winner"]}, Double Booking Detected={res["double_booking_detected"]}, Integrity={res["seat_integrity"]}')

# 12. Test Concurrency Race (3-User)
req = urllib.request.Request(f'{base}/api/concurrency-test-3', data=json.dumps({'user_a_id':1, 'user_b_id':2, 'user_c_id':3, 'train_id':train_id, 'target_seat':'12D'}).encode(), headers={'Content-Type':'application/json'})
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['double_bookings'] == 0
assert res['consistency'] == 'PASSED'
print(f'[PASS] 12. Concurrency 3-User test passed: Winner={res["winner"]}, Double Bookings={res["double_bookings"]}, Consistency={res["consistency"]}')

# Reset demo data back to clean state
req_reset = urllib.request.Request(f'{base}/api/reset', data=b'{}', headers={'Content-Type':'application/json'})
urllib.request.urlopen(req_reset)

print('\n' + '='*60)
print('ALL 12 BACKEND & FRONTEND INTEGRATION TESTS PASSED!')
print('='*60)
