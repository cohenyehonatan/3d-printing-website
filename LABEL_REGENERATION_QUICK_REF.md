# ⚡ Label Regeneration Safety - Quick Reference

**Last Updated:** January 7, 2026

---

## 🎯 The Problem (Solved)

**Before:** Someone could click "Create Label" twice → 2 valid UPS shipments → Charged twice

**After:** Once UPS picks up the package, label regeneration is **permanently blocked**

---

## 🔒 What Changed

### Database
- Added `first_carrier_scan_at` timestamp column to track when UPS first scanned the package

### Backend (`api/quote.py`)
- Label creation now checks: "Has UPS already scanned this package?"
- If YES → Returns 409 Conflict (denied)
- If NO → Creates new label (allowed)

### Tracking Detection (`api/quote.py`)
- When you call `GET /api/dashboard/track/{tracking_number}`
- System automatically detects first carrier scan and locks the shipment
- Sets `first_carrier_scan_at` timestamp (never changes again)

### Frontend (`src/ShippingDashboard.jsx`)
- Shows different buttons based on shipment state:
  - **Before label created:** Only "✅ Create Label"
  - **After label created, before scan:** "📥 Re-download" + "⚠️ Void & Regenerate"
  - **After UPS scan:** Only "📥 Re-download" + 🔒 Locked notice

---

## 📋 Button States

| Order State | Buttons | Notes |
|---|---|---|
| No label | ✅ Create Label | One shot—label will be created |
| Label created, not scanned | 📥 Re-download<br>⚠️ Void & Regen | Can still change mind before pickup |
| UPS has picked up | 🔒 LOCKED<br>📥 Re-download | Cannot regenerate—already on truck |

---

## ✅ Safety Guarantees

✅ **Before UPS Picks Up:**
- You can void and regenerate the label
- Two tracking numbers may exist briefly, but only one is valid
- No double charges

✅ **After UPS Picks Up:**
- Label regeneration button disappears
- Backend actively rejects regeneration requests (409 Conflict)
- Even if customer manually calls API, it fails

✅ **Immutable Lock:**
- Once first_carrier_scan_at is set, it never changes
- Persists beyond UPS's 120-day tracking window
- Acts as permanent "shipment locked" flag

---

## 🧪 How to Verify It Works

### Test 1: Regenerate Before Scan
1. Create label → Tracking **ABC123**
2. Click "⚠️ Void & Regenerate"
3. New label created → Tracking **DEF456**
4. UPS picks up DEF456
5. ✅ Expected: Only DEF456 is valid

### Test 2: Block Regeneration After Scan
1. Create label → Tracking **ABC123**
2. Wait for UPS to scan it (or simulate in CIE environment)
3. Click "⚠️ Void & Regenerate"
4. ❌ Button disabled or shows error
5. Try `curl -X POST /api/dashboard/shipping-labels/123/create-label-ups`
6. ❌ Returns: `409 Conflict: "Shipment already scanned by UPS..."`

### Test 3: Scan Detection
1. Create label → Tracking **ABC123**
2. Manually call `GET /api/dashboard/track/ABC123`
3. Look at database: `first_carrier_scan_at` should be NULL
4. Simulate UPS scan in the CIE environment
5. Call `GET /api/dashboard/track/ABC123` again
6. ✅ Database now has timestamp in `first_carrier_scan_at`
7. ✅ Button changes to "🔒 LOCKED"

---

## 🚨 If Something Goes Wrong

### Button Still Shows "Void & Regenerate" After Scan
**Likely cause:** Tracking not refreshed or scan not detected
**Fix:** 
1. Check database: `SELECT first_carrier_scan_at FROM print_orders WHERE id = ?`
2. If NULL, manually click "Track Shipment" button to refresh
3. If still NULL after multiple refreshes, check UPS API response for activity events

### "409 Conflict" Error When It Shouldn't Appear
**Likely cause:** `first_carrier_scan_at` was set incorrectly
**Fix:**
1. Check: `SELECT ups_tracking_number, first_carrier_scan_at FROM print_orders WHERE id = ?`
2. If incorrect timestamp, contact engineering to review UPS activity parsing

### Customer Says "I Need to Regenerate"
**What to do:**
1. Check: Is the package actually picked up yet?
   - If NOT picked up: Tell them to use "⚠️ Void & Regenerate" button (still available)
   - If picked up: Tell them they need to contact UPS to void the label (out of system's hands)
2. Do NOT manually reset `first_carrier_scan_at` (it breaks the safety mechanism)
3. If legitimate, UPS can void and we can create fresh label

---

## 📊 Monitoring Dashboard (Recommended)

Track these metrics:
- `label_regenerations_before_scan` (should be small number)
- `label_regenerations_blocked_after_scan` (should be increasing, shows system working)
- `avg_time_to_first_scan` (how fast does UPS pick up?)
- `orders_with_null_first_carrier_scan_at` (orders still in "can regenerate" state)

---

## 🎓 For Customer Support

**Customer:** "Why can't I regenerate my label?"

**You:** 
> UPS has already scanned your package, so we've locked the label to prevent accidental double-charging. This is a safety feature. If you absolutely need to change something, you'll need to contact UPS directly to discuss voiding the shipment.

**Customer:** "But I made a mistake with the address!"

**You:** 
> Unfortunately, once UPS scans a package, you can't change it. Best option: Contact UPS immediately about voiding it. They can sometimes fix routing issues before delivery. We're sorry about this—next time, double-check the address before hitting "Create Label."

**Customer:** "Can you override the lock?"

**You:** 
> No, the lock is permanent once UPS has touched the package. This is by design to protect both you and us from accidental double-charges. UPS must handle any changes at that point.

---

## 🔧 Deployment Checklist

- [ ] Database schema updated (`first_carrier_scan_at` column added)
- [ ] Backend code deployed (`api/quote.py`)
- [ ] Frontend code deployed (`src/ShippingDashboard.jsx`, CSS)
- [ ] Test in staging: Button states work correctly
- [ ] Test in staging: 409 error returned when blocking regeneration
- [ ] Inform support team of new error message
- [ ] Announce in changelog: "Label regeneration now blocked after carrier pickup"
- [ ] Update user docs if public-facing

---

## 📞 Escalation Path

**Issue:** Label regeneration not working as expected

1. **Level 1 (Support):** Check button state and error message
2. **Level 2 (Ops):** Check database values and UPS tracking response
3. **Level 3 (Engineering):** Check logs in tracking endpoint, verify scan detection logic

---

## ✨ The Win

**Before this system:**
- Manual checking every order
- Risk of double-charges
- Customers angry about surprise bills

**After this system:**
- Automatic, fail-safe
- Impossible to double-charge once carrier scans
- Clear, idiot-proof UX
- Audit trail for disputes

---

**Questions?** See `LABEL_REGENERATION_SAFETY.md` for the full technical doc.
