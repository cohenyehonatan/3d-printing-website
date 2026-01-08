# Backfilling Model Dimensions for Past Orders

## Problem
Orders 5 and 6 (and all other past orders) were created before the dimension fields were added to the `PrintOrder` database table. While the dimensions were captured during STL file analysis, they weren't persisted to the database.

## Solution Options

The `scripts/backfill_model_dimensions.py` script provides three ways to populate missing dimensions:

### Option 1: List Orders Missing Dimensions
See which orders need dimension data:

```bash
python scripts/backfill_model_dimensions.py list
```

Shows all 6 orders with their volume and weight (which we have).

**Output:**
```
Order #         Status               Volume (cm³)    Weight (g)    Label Status
ORD-20260103-001   pending_payment     686.57         851.35       not_created
ORD-20260103-002   pending_payment     2655.56        3292.90      not_created
ORD-20260106-003   pending_payment     4574.13        5671.93      not_created
ORD-20260107-004   pending_payment     4574.13        5671.93      not_created
ORD-20260107-005   pending_payment     14353.51       17798.35     not_created
ORD-20260107-006   pending_payment     7813.59        9688.86      not_created
```

### Option 2: Auto-Estimate from Volume (Quick)
Estimate dimensions assuming a cubic shape based on volume:

```bash
# Preview what would be updated (dry-run)
python scripts/backfill_model_dimensions.py estimate --dry-run

# Actually apply the estimates
python scripts/backfill_model_dimensions.py estimate
```

**How it works:**
- Assumes the 3D models are approximately cube-shaped
- Calculates: dimension = (volume)^(1/3) in millimeters
- Example: 686.57 cm³ volume → ~88.4mm × 88.4mm × 88.4mm

**Pros:**
- Quick, one command
- Reasonable approximation for many models

**Cons:**
- Only accurate if models are approximately cube-shaped
- Not suitable for long, thin, or flat models

### Option 3: Manual Input (Accurate)
For each order, manually enter the actual dimensions:

```bash
python scripts/backfill_model_dimensions.py manual --order-id 5
python scripts/backfill_model_dimensions.py manual --order-id 6
```

**Interactive example:**
```
Updating dimensions for Order ORD-20260107-005
Current: volume=14353.51cm³, weight=17798.36g
Estimated from volume: 243.58mm × 243.58mm × 243.58mm

Enter length (mm): 300
Enter width (mm): 250
Enter height (mm): 200

Will set: 300.0mm × 250.0mm × 200.0mm
Confirm? (y/n): y
✓ Order updated successfully!
```

**Pros:**
- Accurate dimensions
- Perfect for packing optimization

**Cons:**
- Manual work for each order
- Need to know actual dimensions

## Recommended Approach

1. **For orders still in pending/not-labeled status:**
   - If you have access to the 3D model files: Use **Option 3 (Manual)** for accuracy
   - If you don't have the files: Use **Option 2 (Estimate)** as a placeholder

2. **After Orders are Labeled/Shipped:**
   - Consider estimated dimensions acceptable (they're just for warehouse reference)
   - Priority is current and future orders

## Getting Actual Dimensions

If you need actual dimensions for manual entry, you can:

1. **From the STL files:** 
   - Use the `/api/verify-file` endpoint (upload the STL file again)
   - Returns bounding box dimensions with the file verification

2. **From customer records:**
   - Check if customer provided dimensions with their order
   - Check email confirmations or order notes

3. **Estimate from what you know:**
   - Volume of 14,353 cm³ with weight 17,798g suggests larger print
   - Typical 3D printers can handle dimensions up to 300×300×300mm
   - Estimate reasonable proportions

## Quick Start

```bash
# 1. See what needs updating
python scripts/backfill_model_dimensions.py list

# 2. Try the estimate (shows what would change, no actual changes)
python scripts/backfill_model_dimensions.py estimate --dry-run --verbose

# 3. If estimates look reasonable, apply them
python scripts/backfill_model_dimensions.py estimate

# 4. For specific orders, refine with manual input
python scripts/backfill_model_dimensions.py manual --order-id 5
python scripts/backfill_model_dimensions.py manual --order-id 6
```

## After Backfill

Once dimensions are populated:
- ✅ Packing optimizer will have actual data instead of fallback
- ✅ Dashboard will show specific packing recommendations
- ✅ Warehouse team will see model dimensions in shipping details
- ✅ Future orders automatically capture dimensions

## Future Prevention

To ensure this doesn't happen again for new orders:

1. **Update CheckoutRequest** to include dimension fields (in `api/quote.py`)
2. **Update STL verification** to include dimensions in request
3. **Capture dimensions during checkout** before creating PrintOrder

See `API_PARAMETER_ALIGNMENT.md` for frontend/backend integration details.

## Technical Details

### Data Flow (Current)
```
STL Upload → Verify File (gets dimensions) → Quote Created (volume/weight) 
→ Checkout → PrintOrder Created (missing dimensions!)
```

### Data Flow (Should Be)
```
STL Upload → Verify File (gets dimensions) → Quote Created 
→ Checkout (includes dimensions) → PrintOrder Created (✅ has dimensions!)
```

### Database Fields
```python
model_length_mm: Column(Float)   # X dimension in millimeters
model_width_mm: Column(Float)    # Y dimension in millimeters  
model_height_mm: Column(Float)   # Z dimension in millimeters
```

### API Response
The GET `/api/dashboard/shipping-labels` endpoint now includes:
```json
{
  "model_dimensions": {
    "length_mm": 100.5,
    "width_mm": 95.2,
    "height_mm": 87.3
  }
}
```

## Troubleshooting

**Q: Estimates seem way off?**
- A: The cubic assumption only works for approximately cube-shaped models
- Solution: Use manual input with actual dimensions

**Q: Can I undo changes?**
- A: Yes, set the fields back to NULL in the database:
  ```sql
  UPDATE print_orders SET model_length_mm = NULL, model_width_mm = NULL, model_height_mm = NULL WHERE id = 5;
  ```

**Q: Script won't run?**
- A: Make sure you're in the project directory and Python environment:
  ```bash
  cd /Users/jonathancohen/3d-printing-website
  source venv/bin/activate
  python scripts/backfill_model_dimensions.py list
  ```

## Next Steps

1. **Backfill existing orders** (this guide)
2. **Update checkout flow** to capture dimensions from STL verification (in API)
3. **Verify packing optimizer** works with real dimensions
4. **Test warehouse workflow** with actual packing recommendations

---

**Created:** January 7, 2026  
**Related Files:** `scripts/backfill_model_dimensions.py`, `api/packing_optimizer.py`, `api/quote.py`
