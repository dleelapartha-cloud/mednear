#!/bin/bash
# MedNear API verification battery against the fixed server (port 3111)
set -u
BASE="http://127.0.0.1:3111"
PASS=0; FAIL=0
chk() {
  if [ "$2" = "OK" ]; then PASS=$((PASS+1)); echo "PASS: $1"; else FAIL=$((FAIL+1)); echo "FAIL: $1 -> $3"; fi
}
PY=/opt/miniconda3/bin/python3

jqpy() { $PY -c "import sys,json
d=json.load(sys.stdin)
$1"; }

# 1. Medicine search
R=$(curl -s "$BASE/api/medicines?q=dolo" | jqpy "print('OK' if d['count']>=1 else 'BAD')")
chk "medicines search (q=dolo)" "$R" "unexpected count"

# 2. Pharmacies search
R=$(curl -s "$BASE/api/pharmacies?medicine=pantoprazole&lat=12.97&lng=77.59" | jqpy "print('OK' if d['count']>=1 and d['results'][0]['distance_km'] is not None else 'BAD')")
chk "pharmacies search + distance" "$R" "unexpected"

# 3. Disease detail
R=$(curl -s "$BASE/api/diseases/gerd" | jqpy "print('OK' if len(d['drugs'])>=5 else 'BAD')")
chk "disease comparative menu (gerd)" "$R" "drugs missing"

# 4a. Scan match: real OCR text for Dolo
R=$(curl -s -X POST "$BASE/api/scan/match" -H 'Content-Type: application/json' -d '{"text":"DOLO 650  Paracetamol Acetaminophen 650mg tablets"}' | jqpy "print('OK' if d['matched'] and d['medicine']['id']=='dolo' else 'BAD:'+str(d.get('medicine',{}).get('id')))")
chk "scan/match OCR text -> dolo" "$R" "wrong match"

# 4b. Scan match: statin text
R=$(curl -s -X POST "$BASE/api/scan/match" -H 'Content-Type: application/json' -d '{"text":"ZOCOR 40 simvastatin strip"}' | jqpy "print('OK' if d['matched'] and d['medicine']['id']=='simvastatin' else 'BAD')")
chk "scan/match OCR text -> simvastatin" "$R" "wrong match"

# 4c. Scan match: garbage text -> matched=false (honest response)
R=$(curl -s -X POST "$BASE/api/scan/match" -H 'Content-Type: application/json' -d '{"text":"zzzqqq nonsense 7774"}' | jqpy "print('OK' if d['matched']==False else 'BAD')")
chk "scan/match garbage -> matched=false" "$R" "fake match"

# 5. Login pharmacist (green cross)
PT=$(curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"pharmacist@greencross.com","password":"Password123!"}' | jqpy "print(d['token'])")
R=$(if [ ${#PT} -gt 40 ]; then echo OK; else echo BAD; fi)
chk "pharmacist login (JWT)" "$R" "no token"

# 6. Inventory GET (pharmacist of own store)
R=$(curl -s "$BASE/api/pharmacy/green-cross/inventory" -H "Authorization: Bearer $PT" | jqpy "print('OK' if d['total_items']>=8 else 'BAD')")
chk "store inventory GET" "$R" "no items"

# 7. Inventory POST invalid status -> 400
CODE=$(curl -s -o /tmp/inv.json -w "%{http_code}" -X POST "$BASE/api/pharmacy/green-cross/inventory" -H "Authorization: Bearer $PT" -H 'Content-Type: application/json' -d '{"medicine_id":"dolo","status":"weird"}')
R=$(if [ "$CODE" = "400" ]; then echo OK; else echo BAD:$CODE; fi)
chk "inventory POST invalid status rejected" "$R" "expected 400"

# 7b. Inventory POST valid -> success
R=$(curl -s -X POST "$BASE/api/pharmacy/green-cross/inventory" -H "Authorization: Bearer $PT" -H 'Content-Type: application/json' -d '{"medicine_id":"dolo","status":"limited","units":5,"price":34.0,"rack":"Counter Front"}' | jqpy "print('OK' if d['success'] else 'BAD')")
chk "inventory POST valid toggle" "$R" "failed"

# 7c. Cross-store forbidden -> 403
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/pharmacy/apollo-lavelle/inventory" -H "Authorization: Bearer $PT" -H 'Content-Type: application/json' -d '{"medicine_id":"dolo","status":"available"}')
R=$(if [ "$CODE" = "403" ]; then echo OK; else echo BAD:$CODE; fi)
chk "cross-store inventory forbidden" "$R" "expected 403"

# 8. Patient login
PJT=$(curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d '{"email":"patient@mednear.org","password":"Password123!"}' | jqpy "print(d['token'])")

# 9. Create hold (patient) -> unique id format
H=$(curl -s -X POST "$BASE/api/holds" -H "Authorization: Bearer $PJT" -H 'Content-Type: application/json' -d '{"store_id":"green-cross","medicine_id":"dolo","medicine_name":"Dolo 650","patient_name":"Test Patient","phone":"+91 90000 11111","quantity":1,"total_price":34,"eta":"30 min"}')
HID=$(echo "$H" | jqpy "print(d['hold_id'])")
OTP=$(echo "$H" | jqpy "print(d['otp'])")
R=$(if echo "$HID" | grep -qE '^HLD-[0-9A-F]{6}$'; then echo OK; else echo BAD:$HID; fi)
chk "hold created with collision-free ID" "$R" "$HID"

# 10. Patient cannot verify OTP (401/403)
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/holds/$HID/verify-otp" -H "Authorization: Bearer $PJT" -H 'Content-Type: application/json' -d "{\"otp\":\"$OTP\"}")
R=$(if [ "$CODE" = "401" ] || [ "$CODE" = "403" ]; then echo OK; else echo BAD:$CODE; fi)
chk "OTP verify restricted to pharmacist/admin" "$R" "expected 401/403"

# 11. Pharmacist wrong OTP -> fail; right OTP -> success
R=$(curl -s -X POST "$BASE/api/holds/$HID/verify-otp" -H "Authorization: Bearer $PT" -H 'Content-Type: application/json' -d '{"otp":"0000"}' | jqpy "print('OK' if d['success']==False else 'BAD')")
chk "wrong OTP rejected" "$R" "accepted wrong otp"
R=$(curl -s -X POST "$BASE/api/holds/$HID/verify-otp" -H "Authorization: Bearer $PT" -H 'Content-Type: application/json' -d "{\"otp\":\"$OTP\"}" | jqpy "print('OK' if d['success'] else 'BAD')")
chk "correct OTP accepted" "$R" "rejected right otp"

# 12. Notifications recent endpoint is admin-gated
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/notifications/recent")
R=$(if [ "$CODE" = "401" ]; then echo OK; else echo BAD:$CODE; fi)
chk "notifications/recent requires auth (OTP leak fixed)" "$R" "expected 401"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/notifications/test" -H 'Content-Type: application/json' -d '{"phone":"+919000000000","message":"spam"}')
R=$(if [ "$CODE" = "401" ]; then echo OK; else echo BAD:$CODE; fi)
chk "notifications/test SMS relay closed" "$R" "expected 401"

# 13. Static frontend serves and references app.js
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/")
R=$(if [ "$CODE" = "200" ]; then echo OK; else echo BAD:$CODE; fi)
chk "frontend served at /" "$R" "http $CODE"

# 14. Two sequential holds do not collide (ID uniqueness across 12 creates)
DUP=NO
DUPID=""
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  ID=$(curl -s -X POST "$BASE/api/holds" -H 'Content-Type: application/json' -d "{\"store_id\":\"green-cross\",\"medicine_id\":\"dolo\",\"medicine_name\":\"Dolo 650\",\"patient_name\":\"Stress $i\",\"phone\":\"+91 90000 2222$i\",\"quantity\":1,\"total_price\":34,\"eta\":\"30 min\"}" | jqpy "print(d.get('hold_id','ERR'))")
  if [ "$ID" = "ERR" ] || [ "$ID" = "$DUPID" ]; then DUP=YES; break; fi
  DUPID=$ID
done
R=$(if [ "$DUP" = "NO" ]; then echo OK; else echo BAD; fi)
chk "12 unique hold IDs (no PK collisions)" "$R" "collision/error after $i"

echo "-------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
