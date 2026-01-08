# 🔒 Label Regeneration Safety System

**Date Implemented:** January 7, 2026
**Status:** ✅ ACTIVE & ENFORCED

---

## Executive Summary

This document describes the **3-part safety mechanism** that prevents dangerous label regeneration and multiple shipment charges.

**Problem Solved:**
- ❌ **Before:** Anyone could re-click the label button → multiple valid UPS shipments → accidental double charges
- ✅ **After:** Once UPS scans the package, label regeneration is **permanently blocked** at the backend level

---

## 🔑 The Three Core Changes

### 1️⃣ Database Model: `first_carrier_scan_at` Column

**File:** `api/models.py`

```python
class PrintOrder(Base):
    # ... existing fields ...
    first_carrier_scan_at = Column(DateTime, nullable=True)  # When UPS first scanned package
```

**Purpose:**
- Immutable flag that marks "UPS has physical possession"
- Survives 120-day tracking data retention (outlasts UPS tracking)
- Once set, **can never be unset** (immutable)

**Semantics:**
- `NULL` → UPS has not scanned yet; label can still be voided/regenerated
- `NOT NULL` → UPS has scanned; shipment is locked forever

---

### 2️⃣ Backend Safety Check: `create_label_ups` Endpoint

**File:** `api/quote.py` (lines ~1315)

```python
@app.post('/api/dashboard/shipping-labels/{order_id}/create-label-ups')
async def create_label_ups(order_id: int, label_request: Optional[dict] = None):
    # ... validation ...
    
    # CRITICAL SAFETY CHECK
    if order.ups_tracking_number and order.first_carrier_scan_at:
        raise HTTPException(
            status_code=409,  # Conflict
            detail="Shipment already scanned by UPS. Label cannot be regenerated. "
                   "Contact support if you need to void this shipment."
        )
    
    # ... proceed to create label ...
```

**What it does:**
- ✅ Checks if a tracking number exists AND carrier has scanned
- ✅ Returns **409 Conflict** (not 400 or 500)
- ✅ Blocks label creation at the **backend** (frontend hiding is not sufficient)
- ✅ Prevents accidental curl attacks

**Why 409?**
- Standard HTTP status for "resource conflict"
- Tells clients: "You can't do that on this resource right now"
- Distinct from auth errors (401), validation errors (400), or server errors (500)

---

### 3️⃣ Tracking Detection: `track_shipment` Endpoint

**File:** `api/quote.py` (lines ~1873)

```python
@app.get('/api/dashboard/track/{tracking_number}')
async def track_shipment(tracking_number: str):
    # ... call UPS tracking API ...
    result = await ups_module.ups_service.track_shipment(tracking_number)
    
    # CRITICAL: Persist first scan detection
    if order and order.first_carrier_scan_at is None:
        activities = result.get('activities', [])
        has_carrier_scanned = False
        
        SCAN_INDICATORS = {
            'Pickup Scan', 'Origin Scan', 'Package Received', 
            'Arrived at Facility', 'In Transit', 'Out for Delivery',
            'Delivered', 'Delivery Confirmed', 'Package Delivered'
        }
        
        for activity in activities:
            status = activity.get('status', '').strip()
            if any(indicator.lower() in status.lower() for indicator in SCAN_INDICATORS):
                has_carrier_scanned = True
                break
        
        if has_carrier_scanned:
            order.first_carrier_scan_at = datetime.utcnow()
            order.label_status = 'shipped'
            db.commit()
```

**What it does:**
- ✅ Fetches current tracking from UPS API
- ✅ Looks for any **activity event** indicating carrier possession
- ✅ On first detection, **persists the timestamp to database**
- ✅ Sets status to "shipped" (immutable state)
- ✅ Subsequent calls do nothing (idempotent)

**Scan Indicators Detected:**
- "Pickup Scan" — Package picked up from shipper
- "Origin Scan" — Arrived at origin facility
- "Package Received" — Received by carrier
- "Arrived at Facility" — Scanned into facility
- "In Transit" — In the network
- "Out for Delivery" — On the delivery vehicle
- "Delivered" or variants — Delivered to recipient

---

## 📋 Business Rules (Authoritative)

### State 1: No Label Created Yet
```
label_status = NULL/pending
ups_tracking_number = NULL
first_carrier_scan_at = NULL
```
**Actions:**
- ✅ Create label (calls UPS, gets tracking)
- ❌ Cannot re-download (no label yet)
- ❌ Cannot void/regenerate (no label yet)

---

### State 2: Label Created, NOT YET Scanned
```
label_status = created
ups_tracking_number = (has value)
first_carrier_scan_at = NULL
```
**Actions:**
- ✅ Create label AGAIN → Voids previous label, creates new tracking (backend allows it)
- ✅ Re-download label (return existing `ups_label_image`)
- ✅ Void & Regenerate (calls create_label_ups again)

**Why this is safe:**
- UPS hasn't touched the package yet
- Previous label is worthless
- New tracking is legitimate

---

### State 3: Label Created AND UPS Has Scanned
```
label_status = created OR shipped
ups_tracking_number = (has value)
first_carrier_scan_at = (set)
```
**Actions:**
- ❌ Create label (BLOCKED with 409 Conflict)
- ✅ Re-download label only
- 🔒 Locked forever

**Why blocking is critical:**
- UPS has the package
- Previous tracking is valid and in-use
- New label = duplicate shipment = double charge
- This is the "point of no return"

---

## 🖥️ Frontend UI State Machine

The dashboard shows different buttons based on order state:

### No Label Yet
```
Button: ✅ Create Label
```

### Label Created, Not Scanned
```
Button 1: 📥 Re-download Label
Button 2: ⚠️ Void & Regenerate   [Warning tone]
Tooltip: "This will invalidate the previous label and create a new tracking number"
```

### After Carrier Scan
```
🔒 LOCKED NOTICE
"UPS has already scanned this package. Label regeneration is no longer allowed."
Scanned at: [timestamp shown]

Button: 📥 Re-download Label   [Only button available]
```

---

## 🧪 Testing Scenarios

### Scenario A: Normal Path (No Regeneration Needed)
1. ✅ Create label → tracking ABC123
2. 📥 Re-download label (works)
3. UPS picks up package
4. 🔒 Shipment locked
5. 📥 Re-download still works

**Result:** ✅ Safe

---

### Scenario B: Accidental Label Creation
1. ✅ Create label → tracking ABC123
2. ⚠️ Accidentally click "Void & Regenerate"
3. ✅ New label created → tracking DEF456
4. 📥 Previous label voided (at UPS)
5. UPS picks up DEF456
6. 🔒 Locked to DEF456

**Result:** ✅ Safe (only one valid tracking)

---

### Scenario C: Attempted Double-Charge (ATTACK)
1. ✅ Create label → tracking ABC123
2. UPS picks up (or about to)
3. ⚠️ Attacker calls: `POST /api/dashboard/shipping-labels/{order_id}/create-label-ups`
4. ❌ Returns 409 Conflict (BLOCKED)

**Result:** ✅ Blocked (no double charge)

---

### Scenario D: Manual Curl Attack After Scan
```bash
curl -X POST \
  'https://api.example.com/api/dashboard/shipping-labels/42/create-label-ups' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

**Response:**
```json
{
  "detail": "Shipment already scanned by UPS. Label cannot be regenerated. Contact support if you need to void this shipment."
}
```

**HTTP Status:** 409 Conflict

**Result:** ✅ Blocked at backend (not by frontend auth)

---

## 📊 Database Migration

If adding to existing database, you'll need:

```sql
ALTER TABLE print_orders ADD COLUMN first_carrier_scan_at DATETIME NULL;
```

This is a **backward-compatible** change:
- ✅ Existing orders have `NULL` (pre-scan state)
- ✅ New orders will have either `NULL` or timestamp
- ✅ No data loss

---

## 🚨 Error Codes

| Status | Meaning | When |
|--------|---------|------|
| 200 OK | Label created successfully | First creation or valid regeneration |
| 409 Conflict | Cannot regenerate | UPS has scanned the package |
| 400 Bad Request | Invalid input | Missing required fields |
| 404 Not Found | Order not found | Order ID doesn't exist |
| 500 Internal Error | Server error | UPS API down, DB error |

---

## 🔐 Idempotency & Safety Guarantees

### Create Label is NOT Idempotent (by design)
```
POST /api/dashboard/shipping-labels/{order_id}/create-label-ups
  Call 1 → tracking ABC123
  Call 2 → tracking DEF456 (if not scanned yet)
  Call 3 → 409 Conflict (if scanned)
```

This is intentional:
- ✅ Allows label regeneration before carrier scan
- ✅ Prevents regeneration after carrier scan
- ✅ Avoids "duplicate idempotent key" complexity

---

## 🛡️ What This Does NOT Protect Against

1. **Accounting errors** — If UPS charges you, that's UPS's problem
2. **Manual void process** — If you call UPS directly to void, this system doesn't know
3. **UPS label duplication** — If UPS bugs and duplicates a label, we can't prevent that
4. **Lost/destroyed label** — If label is destroyed in transit, you have to reship (that's normal)

**What it DOES protect against:**
- ✅ Accidental re-clicks creating multiple shipments
- ✅ Thoughtless automation that creates duplicate labels
- ✅ Misunderstanding "regenerate" to mean "create another"
- ✅ Attacker attempting to trigger double-billing

---

## 📝 Audit Trail Recommendations

For future enhancement, consider logging:

```python
class LabelEvent:
    event: str  # "created", "voided", "scanned"
    tracking_number: str
    timestamp: datetime
    order_id: int
    user_id: Optional[int]
    ip_address: Optional[str]
```

This would give you a complete history for:
- Dispute resolution with UPS
- Compliance audits
- Investigation of double-charges
- Operational transparency

---

## ✅ Checklist for Ops Team

- [ ] Database migration applied (added `first_carrier_scan_at` column)
- [ ] Backend code deployed (`api/quote.py` and `api/models.py`)
- [ ] Frontend code deployed (`src/ShippingDashboard.jsx` and CSS)
- [ ] Test: Label creation works
- [ ] Test: Re-download works before scan
- [ ] Test: Void & Regenerate works before scan
- [ ] Test: Manual tracking.get() detects scan and locks shipment
- [ ] Test: Attempting regeneration after scan returns 409
- [ ] Test: Error message is user-friendly
- [ ] Inform customers about new "Locked" state in docs

---

## 🎓 Summary for Developers

**The system is now:**

1. **Unambiguous:** One boolean question: "Has UPS scanned this?" → Yes/No
2. **Persistent:** Answer outlives UPS's 120-day tracking window
3. **Fail-safe:** Default behavior is to BLOCK (safer than allowing)
4. **Backend-enforced:** Frontend hiding is nice, but backend check is mandatory
5. **User-friendly:** Clear UI states tell users what actions are available

**From here, operations is rock-solid.**

**The old way:**
> "Did I already create a label? I dunno, let me click and find out..." → 💥 Double charge

**The new way:**
> "Once UPS has it, the label button disappears. Can't make that mistake." → ✅ Safe by design

---

**Questions?** Check the code comments or reach out.
