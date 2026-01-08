# 🔍 Code Changes - Exact Snippets

**Last Updated:** January 7, 2026

---

## 1️⃣ Database Model Change

**File:** `api/models.py`  
**Line:** 163

**What was added:**

```python
# Before (around line 160-162):
    shipping_weight_g: Mapped[float | None] = mapped_column(Float)
    
    # Content & Packaging
    packaging_type = Column(String(50))  # e.g., "USPS Small Priority Box", "Custom"

# After (new lines):
    shipping_weight_g: Mapped[float | None] = mapped_column(Float)
    
    # Carrier scan tracking (immutable once set)
    first_carrier_scan_at = Column(DateTime, nullable=True)  # When UPS first scanned package - hard lock on regeneration
    
    # Content & Packaging
    packaging_type = Column(String(50))  # e.g., "USPS Small Priority Box", "Custom"
```

**Key points:**
- `DateTime` type (timestamp)
- `nullable=True` (starts as NULL)
- Comment explains purpose
- Immutable by application logic (never reset)

---

## 2️⃣ Backend Safety Check

**File:** `api/quote.py`  
**Function:** `create_label_ups`  
**Lines:** 1323-1330

**What was added (right after fetching the order):**

```python
def create_label_ups(order_id: int, label_request: Optional[dict] = None):
    from .models import PrintOrder
    from .database import SessionLocal
    from .ups_service import ups_service
    
    db = SessionLocal()
    try:
        order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # ========================================================================
        # CRITICAL SAFETY CHECK: Prevent regeneration if UPS has scanned package
        # ========================================================================
        if order.ups_tracking_number and order.first_carrier_scan_at:
            raise HTTPException(
                status_code=409,
                detail="Shipment already scanned by UPS. Label cannot be regenerated. "
                       "Contact support if you need to void this shipment."
            )
        
        # Get delivery and shipping info (existing code continues...)
        delivery = {
            "first_name": order.delivery_first_name or "",
            # ... rest of function ...
        }
```

**Key points:**
- Checks TWO conditions: has tracking AND has scan timestamp
- Returns 409 Conflict (not 400 or 500)
- Blocks BEFORE any UPS API call
- Clear error message for customer

---

## 3️⃣ Scan Detection & Persistence

**File:** `api/quote.py`  
**Function:** `track_shipment`  
**Lines:** 1868-1908

**What was added (after getting tracking result):**

```python
@app.get('/api/dashboard/track/{tracking_number}')
async def track_shipment(tracking_number: str):
    """
    Track a UPS shipment using the provided tracking number.
    
    Returns tracking information including current status, location, and activity history.
    Note: UPS retains tracking data for 120 days after shipment pickup.
    
    CRITICAL: Detects and persists first carrier scan to prevent label regeneration.
    """
    try:
        from . import ups_service as ups_module
        from .models import PrintOrder
        from .database import SessionLocal
        
        # Use the UPS service to get tracking information
        result = await ups_module.ups_service.track_shipment(tracking_number)
        
        if result.get('error'):
            raise HTTPException(status_code=400, detail=result.get('message', 'Failed to track shipment'))
        
        # ========================================================================
        # CRITICAL: Detect first carrier scan and persist it
        # ========================================================================
        db = SessionLocal()
        try:
            order = db.query(PrintOrder).filter(
                PrintOrder.ups_tracking_number == tracking_number
            ).first()
            
            if order and order.first_carrier_scan_at is None:
                # Check if any carrier activity (beyond just label creation) exists
                activities = result.get('activities', [])
                has_carrier_scanned = False
                
                # Look for scan events that indicate UPS has physical possession
                SCAN_INDICATORS = {
                    'Pickup Scan', 'Origin Scan', 'Package Received', 
                    'Arrived at Facility', 'In Transit', 'Out for Delivery',
                    'Delivered', 'Delivery Confirmed', 'Package Delivered'
                }
                
                for activity in activities:
                    status = activity.get('status', '').strip()
                    # Check if status contains any scan indicator (case-insensitive)
                    if any(indicator.lower() in status.lower() for indicator in SCAN_INDICATORS):
                        has_carrier_scanned = True
                        break
                
                if has_carrier_scanned:
                    # Persist the scan timestamp and lock the shipment
                    order.first_carrier_scan_at = datetime.utcnow()
                    order.label_status = 'shipped'
                    db.commit()
                    logging.info(
                        f"Carrier scan detected and persisted for order {order.id} "
                        f"(tracking {tracking_number}). Label regeneration now blocked."
                    )
        except Exception as e:
            logging.error(f"Error persisting carrier scan for {tracking_number}: {e}")
        finally:
            db.close()
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error tracking shipment {tracking_number}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track shipment: {str(e)}")
```

**Key points:**
- Runs every time tracking is checked
- Looks for real carrier activity indicators
- Only sets timestamp on first detection
- Idempotent (safe to call repeatedly)
- Logs what happened
- Updates label_status to 'shipped'

---

## 4️⃣ Frontend Error Handling

**File:** `src/ShippingDashboard.jsx`  
**Function:** `createUPSLabel`  
**Lines:** 467-499

**What was changed:**

```javascript
// Before:
if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    setActionError(`Failed to create label: ${errorData.detail || response.statusText}`);
    return;
}

// After:
if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    // 409 = Conflict (label already scanned by carrier, cannot regenerate)
    if (response.status === 409) {
        setActionError(`⚠️ Cannot regenerate: ${errorData.detail || 'Label already scanned by UPS. Contact support if voiding is needed.'}`);
    } else {
        setActionError(`Failed to create label: ${errorData.detail || response.statusText}`);
    }
    return;
}
```

**Key points:**
- Detects 409 status specifically
- Shows different message for 409 vs other errors
- User-friendly wording with warning emoji
- Guides user to contact support for special cases

---

## 5️⃣ Frontend Button Logic

**File:** `src/ShippingDashboard.jsx`  
**Lines:** 1140-1215

**What was changed:**

```jsx
// Before:
{!isLabeled && (
    <div className="label-action">
        <button
            onClick={() => createUPSLabel(selectedOrder.id)}
            className="mark-labeled-btn"
            disabled={actionLoading}
        >
            {actionLoading ? '⟳ Creating Label...' : '✓ Create Label and Mark as Labeled'}
        </button>
    </div>
)}

// After:
{/* Label Action Buttons - Safety Aware */}
{!isLabeled && (
    <div className="label-action">
        <button
            onClick={() => createUPSLabel(selectedOrder.id)}
            className="mark-labeled-btn"
            disabled={actionLoading}
        >
            {actionLoading ? '⟳ Creating Label...' : '✅ Create Label'}
        </button>
    </div>
)}

{/* Once labeled: show re-download button */}
{isLabeled && !selectedOrder?.first_carrier_scan_at && (
    <div className="label-action label-controls">
        <button
            onClick={() => {
                // Re-download (show existing label)
                if (selectedOrder?.ups_label_image) {
                    const labelDataUrl = `data:image/${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'};base64,${selectedOrder.ups_label_image}`;
                    const link = document.createElement('a');
                    link.href = labelDataUrl;
                    link.download = `label-${selectedOrder.ups_tracking_number}.${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'}`;
                    link.click();
                }
            }}
            className="re-download-btn secondary"
        >
            📥 Re-download Label
        </button>
        <button
            onClick={() => createUPSLabel(selectedOrder.id)}
            className="void-regenerate-btn warning"
            disabled={actionLoading}
            title="Invalidate the previous label and create a new tracking number"
        >
            {actionLoading ? '⟳ Regenerating...' : '⚠️ Void & Regenerate'}
        </button>
    </div>
)}

{/* After carrier scan: locked state */}
{isLabeled && selectedOrder?.first_carrier_scan_at && (
    <div className="label-action">
        <div className="locked-shipment-notice">
            <strong>🔒 Shipment Locked</strong>
            <p>UPS has already scanned this package. Label regeneration is no longer allowed.</p>
            <p className="scan-timestamp">Scanned: {new Date(selectedOrder.first_carrier_scan_at).toLocaleString()}</p>
            <button
                onClick={() => {
                    // Re-download only
                    if (selectedOrder?.ups_label_image) {
                        const labelDataUrl = `data:image/${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'};base64,${selectedOrder.ups_label_image}`;
                        const link = document.createElement('a');
                        link.href = labelDataUrl;
                        link.download = `label-${selectedOrder.ups_tracking_number}.${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'}`;
                        link.click();
                    }
                }}
                className="re-download-btn secondary"
            >
                📥 Re-download Label
            </button>
        </div>
    </div>
)}
```

**Key points:**
- Three separate conditional renders for three states
- Checks for `first_carrier_scan_at` to determine locked state
- Shows appropriate buttons for each state
- Re-download works in both locked and unlocked states
- Void & Regenerate only shows when not locked

---

## 6️⃣ Frontend Styling

**File:** `src/ShippingDashboard.css`  
**Lines:** 363-444

**What was added:**

```css
.label-action.label-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.re-download-btn,
.void-regenerate-btn {
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s ease;
  white-space: nowrap;
  font-size: 14px;
}

.re-download-btn {
  background: #f3f4f6;
  color: #1f2937;
  border: 1px solid #d1d5db;
}

.re-download-btn:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

.void-regenerate-btn {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.void-regenerate-btn:hover:not(:disabled) {
  background: #fee2e2;
  border-color: #f87171;
}

.void-regenerate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Locked Shipment State */
.locked-shipment-notice {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}

.locked-shipment-notice strong {
  display: block;
  color: #92400e;
  font-size: 16px;
  margin-bottom: 8px;
}

.locked-shipment-notice p {
  color: #b45309;
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.5;
}

.locked-shipment-notice .scan-timestamp {
  color: #92400e;
  font-size: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #fcd34d;
}

.locked-shipment-notice .re-download-btn {
  margin-top: 12px;
  width: 100%;
  text-align: center;
}
```

**Key points:**
- Re-download button: gray/neutral style
- Void & Regenerate button: warning/red style
- Locked notice: yellow/amber background for visibility
- All states clearly differentiated by color
- Locked notice is prominent (gradient, border)

---

## 🔍 Key Differences

| Aspect | Before | After |
|--------|--------|-------|
| **Safety Check** | None | 409 if already scanned |
| **Persistence** | No flag | `first_carrier_scan_at` timestamp |
| **Scan Detection** | Not detected | Automatic in track endpoint |
| **Button States** | Always same | Three distinct states |
| **Error Message** | Generic | 409-specific with explanation |
| **Styling** | Single style | Three color-coded states |

---

## ✅ Verification

All changes are **already in place** in the codebase:

```bash
# Verify database model change
grep -n "first_carrier_scan_at" api/models.py
# Output: Line 163

# Verify backend safety check
grep -n "CRITICAL SAFETY CHECK" api/quote.py
# Output: Line 1323

# Verify scan detection
grep -n "CRITICAL: Detect first carrier scan" api/quote.py
# Output: Line 1868

# Verify frontend logic
grep -n "first_carrier_scan_at" src/ShippingDashboard.jsx
# Output: Lines 1158, 1187, 1192

# Verify CSS
grep -n "locked-shipment-notice" src/ShippingDashboard.css
# Output: Line 411
```

---

## 🚀 Ready for Deployment

All code is in place. Next steps:
1. Database migration script
2. Code review
3. QA testing
4. Staging deployment
5. Production rollout

**Status:** ✅ Complete
