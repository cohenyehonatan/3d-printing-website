# Database Models Overhaul Summary

## Overview
The `api/models.py` file has been completely overhauled to be specific to the 3D printing business, removing all automotive service-related tables and fields from the original project.

## Changes Made

### ✅ Removed Models
- **Vehicle** - Not needed for 3D printing
- **Booking** - Replaced with `PrintOrder` (specific to print orders)
- **ServiceHistory** - Not applicable to printing service
- **LineItem** - Not needed (no complex line item tracking required)
- **InvoiceAuditLog** - Can be added later if audit tracking becomes necessary
- **CreditMemo** - Can be added later if refund management needed
- **WorkOrderSignature** - Replaced with more generic e-signature models

### ✅ Kept & Updated Models
- **Customer** - Retained with all fields (email, phone, Stripe ID, GDPR/marketing consent)
- **WaiverSignature** - Retained for legal compliance signatures
- **ESignConsent** - Updated to reference `print_order_id` instead of `booking_id`

### ✅ New Models Created

#### 1. **Material**
Catalog of available 3D printing filaments
- `name` - Material type (e.g., "PLA Basic", "PETG HF")
- `description` - Material description
- `density_g_per_cm3` - For weight calculations
- `price_per_kg` - Cost per kilogram
- `is_active` - Whether material is available for ordering

#### 2. **Quote**
Saved quotes for reference and conversion to orders
- Model details: filename, volume (cm³), weight (g)
- Material and options: material type, quantity, rush order, zip code
- Cost breakdown: base cost, material cost, shipping, tax, total
- Status tracking: is_used, expires_at

#### 3. **PrintOrder**
Main order model for 3D print jobs
- Order identifiers: order_number, customer_id, material_id
- Model specs: volume, weight, quantity
- Options: rush_order flag
- Delivery: address, zip code
- Pricing: subtotal, tax, total (in cents)
- Payment: payment_status, Stripe intent ID, payment link
- Order status: pending, confirmed, printing, completed, cancelled
- Timestamps: created_at, scheduled_print_date, estimated_completion_date, completed_at

#### 4. **PrintJob**
Tracks printing progress in the queue
- Status: queued, printing, paused, completed, failed, cancelled
- Printer assignment: printer_name (e.g., "Bambu Lab X1 #1")
- Timing: queued_at, started_at, completed_at, estimated_duration_minutes
- Progress: progress_percent (0-100), notes, failed_reason

#### 5. **Invoice**
Order invoices (generated after completion)
- Invoice number and date
- Order summary: filename, material, quantity, volume, weight
- Pricing: subtotal, tax, total
- Status: is_finalized, pdf_generated, pdf_path
- Stripe tracking: stripe_invoice_id
- Audit trail: created_by, last_modified_by

### ✅ Pydantic Models (Request/Response Validation)
- **SignatureData** - Updated to use `print_order_id` instead of `booking_id`
- **MaterialResponse** - New response model for material listings
- **QuoteResponse** - Already existed, kept as-is
- **PrintOrderResponse** - New response for order creation/confirmation
- **PrintJobStatusResponse** - New response for job status queries

## Database Schema Relationships

```
Customer (1) ──────→ (∞) PrintOrder
    ├─→ (∞) Quote
    ├─→ (∞) WaiverSignature
    └─→ (∞) ESignConsent

Material (1) ──────→ (∞) PrintOrder
Material (1) ──────→ (∞) Quote

Quote (0..1) ──────→ (1) PrintOrder

PrintOrder (1) ──────→ (1) PrintJob
PrintOrder (1) ──────→ (1) Invoice

ESignConsent → references print_order_id
```

## Migration Notes

If you have an existing database, you'll need to:

1. **Create new tables**: `materials`, `quotes`, `print_orders`, `print_jobs`, `invoices`, `waiver_signatures`, `esign_consents`
2. **Remove old tables**: `vehicles`, `bookings`, `service_history`, `line_items`, `invoice_audit_log`, `credit_memos`
3. **Update Customer table**: Remove irrelevant fields (if any were added for automotive business)

## API Integration Compatibility

The new models align with your existing implementation:
- ✅ `POST /api/checkout` creates a `PrintOrder`
- ✅ `POST /api/quote` calculates quotes (can now save as `Quote` model)
- ✅ Stripe integration uses `Customer` + `PrintOrder` (replaces `Customer` + `Booking`)
- ✅ E-signature flows work with `WaiverSignature` + `ESignConsent`

## Future Enhancements

Consider adding later as needed:
- Printer management/scheduling system (link to `PrintJob`)
- Material inventory tracking
- Customer print history and favorites
- Order tracking/notification system
- Advanced reporting and analytics
