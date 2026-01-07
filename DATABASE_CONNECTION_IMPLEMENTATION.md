# Database Connection Implementation - Summary

## What Was Created

### 1. **Database Module** (`api/database.py`)
- SQLAlchemy engine and session setup
- Support for SQLite (default) or any DATABASE_URL env variable
- `init_db()` function to create all tables on startup
- `get_db()` dependency for FastAPI endpoints

### 2. **Updated Checkout Endpoint** (`/api/checkout`)
Now saves orders to the database when payment links are created:

**Flow:**
1. User proceeds to checkout with complete order details
2. Endpoint creates a Customer record (if new) or retrieves existing
3. Generates a unique `order_number` (e.g., `ORD-20260103-001`)
4. Creates a `PrintOrder` record with status:
   - `order_status`: `'pending_payment'` → will be `'payment_received'` after payment
   - `payment_status`: `'unpaid'` → will be `'paid'` after Stripe webhook
   - `label_status`: `'not_created'` 
5. Stores Stripe payment link for reference
6. Returns payment URL to frontend

**Important:** Orders are created in `pending_payment` status and only become visible in the shipping dashboard after Stripe confirms payment (status changes to `'paid'`)

### 3. **Shipping Dashboard Endpoints**

#### `GET /api/dashboard/shipping-labels`
Returns all orders ready to ship:
- Filters for: `payment_status == 'paid'` AND `label_status == 'not_created'`
- Returns complete order data with shipping details
- Sorted by creation date (newest first)
- **This is the threshold:** Orders must be PAID before appearing in the dashboard

#### `GET /api/dashboard/shipping-labels/{order_id}`
Retrieves detailed data for a specific order (for Click-N-Ship form prefill)

#### `PATCH /api/dashboard/shipping-labels/{order_id}`
Updates shipping label status and tracking info:
- `label_status` (e.g., 'created', 'printed', 'shipped')
- `usps_tracking_number`
- `selected_service`
- `label_created_at`

## Current Threshold for Display

**An order is displayed in the shipping dashboard when:**
```python
payment_status == 'paid' AND label_status == 'not_created'
```

This means:
- ✅ Payment has been successfully received (Stripe webhook updated this)
- ✅ Shipping label hasn't been created yet

## Next Steps (To Complete Integration)

1. **Stripe Webhook Handler** - Create endpoint to handle `payment_intent.succeeded` event
   - This webhook should update the order's `payment_status` to `'paid'`
   - Mark `paid_at` timestamp
   
2. **Test Payment Flow**
   - Complete checkout
   - Confirm Stripe webhook fires
   - Verify order appears in shipping dashboard
   - Verify address and shipping details are correct

3. **Update Frontend** (if needed)
   - Confirm `ShippingDashboard.jsx` works with the new API response format
   - The response structure has been designed to match what the frontend expects

## Database Tables Created

When the app starts, these tables are automatically created:
- `customers` - Customer information
- `print_orders` - Order details (the main table)
- `materials` - Available filaments
- `quotes` - Saved quotes
- And supporting tables (invoices, print_jobs, waiver_signatures, etc.)

## Database Location

Default: `./3d_printing.db` (SQLite file in workspace root)

To use a different database, set `DATABASE_URL` environment variable:
```bash
DATABASE_URL=postgresql://user:password@localhost/3d_printing
```
