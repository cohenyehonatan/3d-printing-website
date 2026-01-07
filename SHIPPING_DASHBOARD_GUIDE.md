# Shipping Label Dashboard - Setup & Usage Guide

## Overview

The Shipping Label Dashboard is an internal tool that collects all customer shipping data during checkout and presents it in a Click-N-Ship ready format. This eliminates manual data entry and reduces errors when creating shipping labels.

## What's New

### 1. **Enhanced Customer Checkout Form**
The checkout form now collects:
- **Contact Information**: Email, Full Name, Phone
- **Shipping Address**: First/Middle/Last Name, Company, Street, Apt/Suite, City, State, ZIP
- **Contents Declarations**: Hazmat, Live Animals, Perishable, Cremated Remains flags
- **Shipping Data**: Weight, Volume, Quantity (auto-calculated)

### 2. **Shipping Dashboard Backend**
New database model fields in `PrintOrder`:
- Detailed shipping address fields (split name, street, city, state, ZIP)
- Ship date and reference numbers (2x, max 30 chars each)
- Contents flags (hazmat, perishable, etc.)
- Packaging type
- Package value for insurance
- Label status tracking (pending, created, printed, shipped)
- USPS tracking number storage

### 3. **Shipping Dashboard UI Component**
New React component: `ShippingDashboard.jsx`
- Left panel: List of pending orders (status, location)
- Right panel: Click-N-Ship formatted data view organized by section:
  - **Section 1: Shipping Information** - all recipient details
  - **Section 2: Content & Packaging** - contents flags, package type, value
  - **Section 3: Shipping Options** - weight, cost summary, service selection, tracking

## Implementation Status

✅ **Completed:**
- Extended `PrintOrder` model with 20+ new shipping fields
- Updated `CheckoutRequest` to accept shipping address fields
- Created `/api/dashboard/shipping-labels` endpoints (skeleton)
- Built `ShippingDashboard.jsx` React component
- Enhanced customer checkout form with full address collection
- Added contents declaration checkboxes

⏳ **Still Needed:**
- Database connection for endpoints (SQLAlchemy integration)
- API implementation to fetch/update orders from DB
- State management selection (which return address to use)

## How It Works

### Step 1: Customer Places Order
Customer fills out checkout form:
1. Upload STL model
2. Select material, quantity, rush order
3. **NEW**: Fill shipping address (Click-N-Ship format)
4. **NEW**: Check contents declarations
5. Pay via Stripe

### Step 2: Admin Views Dashboard
1. Go to internal dashboard
2. See list of pending orders sorted by status/location
3. Click an order to view all data in Click-N-Ship format
4. Copy address fields (click to copy)
5. Manually paste into Click-N-Ship

### Step 3: Use Data in Click-N-Ship
1. Open USPS Click-N-Ship
2. Enter "Ship From" (your return address - manual entry)
3. Paste customer data into "Ship To" fields from dashboard
4. Select packaging type shown in dashboard
5. Review contents flags for special handling
6. Select shipping service and generate label

## Database Model Addition

```python
class PrintOrder(Base):
    # ... existing fields ...
    
    # Delivery Address (for Click-N-Ship)
    delivery_first_name = Column(String(100))
    delivery_middle_initial = Column(String(2))
    delivery_last_name = Column(String(100))
    delivery_company = Column(String(100))
    delivery_street = Column(String(255))
    delivery_apt_suite = Column(String(100))
    delivery_city = Column(String(100))
    delivery_state = Column(String(2))
    delivery_country = Column(String(100), default='United States of America')
    delivery_email = Column(String(255))
    delivery_phone = Column(String(20))
    
    # Shipping Label Info
    ship_date = Column(DateTime)
    reference_number_1 = Column(String(30))  # Will show on label
    reference_number_2 = Column(String(30))  # Will show on label
    
    # Content & Packaging
    packaging_type = Column(String(50))
    contains_hazmat = Column(Boolean, default=False)
    contains_live_animals = Column(Boolean, default=False)
    contains_perishable = Column(Boolean, default=False)
    contains_cremated_remains = Column(Boolean, default=False)
    package_value_cents = Column(Integer)
    
    # Shipping Options Selected
    selected_service = Column(String(100))
    label_status = Column(String(50), default='pending')
    usps_tracking_number = Column(String(100))
    label_created_at = Column(DateTime)
```

## API Endpoints

### Get All Pending Shipping Labels
```
GET /api/dashboard/shipping-labels

Response:
{
  "orders": [
    {
      "order_id": 1,
      "order_number": "ORD-20260103-001",
      "ship_to_city": "New York",
      "ship_to_state": "NY",
      "label_status": "pending"
    }
  ],
  "total_pending": 1
}
```

### Get Single Order Shipping Data
```
GET /api/dashboard/shipping-labels/{order_id}

Response:
{
  "order_id": 1,
  "order_number": "ORD-20260103-001",
  "order_created_at": "2026-01-03T10:00:00",
  
  // Section 1: Shipping Information
  "ship_date": "2026-01-03",
  "ship_to_first_name": "John",
  "ship_to_last_name": "Doe",
  "ship_to_street": "123 Main St",
  "ship_to_city": "New York",
  "ship_to_state": "NY",
  "ship_to_zip": "10001",
  "ship_to_email": "john@example.com",
  "ship_to_phone": "(555) 123-4567",
  "reference_1": "ORD-20260103-001",
  "reference_2": null,
  
  // Section 2: Content & Packaging
  "contains_hazmat": false,
  "contains_live_animals": false,
  "contains_perishable": false,
  "contains_cremated_remains": false,
  "packaging_type": "USPS Small Priority Box",
  "package_value_dollars": 89.99,
  
  // Shipping data
  "weight_g": 245.5,
  "volume_cm3": 198.2,
  "quantity": 1,
  
  // Section 3: Options & Cost
  "selected_service": null,
  "shipping_cost_dollars": 12.50,
  "total_order_cost_dollars": 89.99,
  
  // Label status
  "label_status": "pending",
  "usps_tracking_number": null
}
```

### Update Shipping Label Status
```
PATCH /api/dashboard/shipping-labels/{order_id}

Request Body:
{
  "selected_service": "Priority Mail Express",
  "label_status": "created",
  "usps_tracking_number": "9400111899223456789012"
}

Response:
{
  "order_id": 1,
  "status": "updated"
}
```

## Dashboard Component Features

### Order List (Left Panel)
- Shows order number, destination city/state, and label status
- Status colors: yellow (pending), green (created), gray (other)
- Click to select order for detailed view
- Auto-refreshes on mount

### Detail View (Right Panel)
- Organized in Click-N-Ship section structure
- **Copy-to-clipboard**: Click any contact info to copy
- **Color-coded sections**:
  - Blue border = Shipping Information
  - Red border = Recipient address (required)
  - Orange border = Contents & Packaging
  - Blue/gray summary = Cost & status
- **Status indicators**: Visual badge showing label_status
- **Helpful hints**: "Fill manually" for return address section

## Integration Checklist

### Phase 1: Frontend (✅ Complete)
- [x] Extended checkout form with address fields
- [x] Added contents declaration flags
- [x] Built ShippingDashboard component
- [x] Added copy-to-clipboard functionality
- [x] Styled Click-N-Ship format layout

### Phase 2: Backend (⏳ In Progress)
- [ ] Implement `/api/dashboard/shipping-labels` GET endpoint
- [ ] Save shipping address data from checkout to DB
- [ ] Implement `/api/dashboard/shipping-labels/{id}` GET
- [ ] Implement `/api/dashboard/shipping-labels/{id}` PATCH
- [ ] Add order status filtering (pending, completed, etc.)

### Phase 3: Testing & Refinement
- [ ] Test full checkout -> dashboard flow
- [ ] Verify all fields save correctly
- [ ] Test copy-to-clipboard functionality
- [ ] Performance test with 100+ orders
- [ ] Mobile responsiveness (if needed)

## Next Steps

1. **Connect the API endpoints** to your database using your existing SQLAlchemy models
2. **Run database migration** to add new columns to `print_orders` table
3. **Test the flow**: Place an order → View in dashboard → Copy data to Click-N-Ship
4. **Customize**:
   - Add your default return ZIP code
   - Set default packaging types
   - Add business logo/branding

## File Changes Summary

### Modified Files:
- `api/models.py` - Extended PrintOrder with 20 new fields
- `api/quote.py` - Updated CheckoutRequest, added dashboard endpoints
- `static/App.jsx` - Enhanced checkout form, added address fields

### New Files:
- `static/ShippingDashboard.jsx` - New dashboard component

## Notes

- All required fields in Click-N-Ship are marked with asterisks (*) in dashboard
- Reference numbers auto-populate with order number but can be overridden
- Package value defaults to order total but can be adjusted for insurance
- Contents flags alert you to special USPS requirements
- Tracking number field appears after label is created
