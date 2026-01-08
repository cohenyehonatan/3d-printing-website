# Packing Optimization - System Architecture

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHIPPING DASHBOARD                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Order Details Panel (Right Side)                        │  │
│  │                                                          │  │
│  │  [Section 1] Shipping Information                       │  │
│  │  [Section 2] Content & Packaging                        │  │
│  │  [Section 3] Billing Options                            │  │
│  │  [Section 4] Shipping Options                           │  │
│  │                                                          │  │
│  │  ╔══════════════════════════════════════════════════╗   │  │
│  │  ║ [Section 5] PACKING & BOX OPTIMIZATION (NEW)    ║   │  │
│  │  ║                                                  ║   │  │
│  │  ║  Get model dimensions, quantity, weight,        ║   │  │
│  │  ║  and shipping method from selected order        ║   │  │
│  │  ║                                                  ║   │  │
│  │  ║  ┌─────────────────────────────────────────┐   ║   │  │
│  │  ║  │ 📦 Get Packing Recommendation [BUTTON] │   ║   │  │
│  │  ║  └──────────────┬──────────────────────────┘   ║   │  │
│  │  ║                 │                               ║   │  │
│  │  ║  Loading? Show spinner                         ║   │  │
│  │  ║  Error? Show error message                     ║   │  │
│  │  ║  Success? Show recommendation card:            ║   │  │
│  │  ║                                                  ║   │  │
│  │  ║  ┌─────────────────────────────────────────┐   ║   │  │
│  │  ║  │ 📦 Large Box                        [✕] │   ║   │  │
│  │  ║  │                                          │   ║   │  │
│  │  ║  │ Pack all 5 items in a single Large Box  │   ║   │  │
│  │  ║  │ (24"×18"×12")                           │   ║   │  │
│  │  ║  │                                          │   ║   │  │
│  │  ║  │ Package Dimensions │ Packages │ Weight   │   ║   │  │
│  │  ║  │ 24.5"×18.5"×12.5" │    1    │ 4.2 lbs  │   ║   │  │
│  │  ║  │                                          │   ║   │  │
│  │  ║  │ 📌 Important Notes:                      │   ║   │  │
│  │  ║  │ ✓ Arrangement: 2×2×1 grid               │   ║   │  │
│  │  ║  │ ✓ Weight per package: ~4.2 lbs          │   ║   │  │
│  │  ║  │ ⚠ Use adequate protective padding       │   ║   │  │
│  │  ║  │                                          │   ║   │  │
│  │  ║  │ [🔄 Recalculate]                        │   ║   │  │
│  │  ║  └─────────────────────────────────────────┘   ║   │  │
│  │  ╚══════════════════════════════════════════════════╝   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │
         │ User clicks "Get Packing Recommendation"
         │ or clicks "Recalculate"
         ▼
┌─────────────────────────────────────────────────────────────────┐
│               FRONTEND (React Component)                        │
│                                                                 │
│  function getPackingRecommendation() {                          │
│    Extract from selectedOrder:                                 │
│    - model_length_mm                                           │
│    - model_width_mm                                            │
│    - model_height_mm                                           │
│    - quantity                                                  │
│    - total_weight (in grams)                                   │
│    - shipping_service (method)                                 │
│                                                                 │
│    POST /api/packing-recommendation                            │
│  }                                                             │
└──────────────┬──────────────────────────────────────────────────┘
               │
               │ Network Request
               │ JSON with order details
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND API (FastAPI)                        │
│                                                                 │
│  @app.post('/api/packing-recommendation')                      │
│  async def get_packing_recommendation(                         │
│      request: PackingRequest                                  │
│  ) -> PackingRecommendation:                                  │
│                                                                 │
│    ┌────────────────────────────────────────────────────┐    │
│    │ PACKING OPTIMIZER ENGINE                           │    │
│    │ (packing_optimizer.py)                             │    │
│    └────────────────────────────────────────────────────┘    │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│            PACKING OPTIMIZER (packing_optimizer.py)             │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 1. VALIDATE INPUT                                     │   │
│  │    - Check all dimensions present or return generic   │   │
│  │    - Validate shipping method exists                  │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 2. SELECT SHIPPING METHOD                             │   │
│  │    - Look up SHIPPING_METHOD_SPECS dictionary         │   │
│  │    - Get list of optimal boxes for this carrier       │   │
│  │    - Get max weight and girth restrictions            │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 3. TEST BOX ARRANGEMENTS                              │   │
│  │                                                        │   │
│  │    For each box in optimal_boxes:                     │   │
│  │      For each of 6 item orientations:                 │   │
│  │        - Convert MM to inches                         │   │
│  │        - Add 10mm padding on all sides                │   │
│  │        - Calculate items along each dimension         │   │
│  │        - Check if fits within max weight              │   │
│  │        - Calculate volume waste                       │   │
│  │        - Store best arrangement (min waste)           │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 4. SELECT BEST BOX                                    │   │
│  │    - First box that fits = best box                   │   │
│  │    - If none fit, use largest available box           │   │
│  │    - Calculate total packages needed                  │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 5. CALCULATE METRICS                                  │   │
│  │    - Estimated package dimensions (with 0.5" buffer) │   │
│  │    - Weight per package                               │   │
│  │    - Total weight across all packages                 │   │
│  │    - Generate human-readable arrangement string       │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 6. GENERATE RECOMMENDATIONS                           │   │
│  │    - Strategy name (box type)                         │   │
│  │    - Human-readable recommendation text               │   │
│  │    - Method-specific notes:                           │   │
│  │      * USPS: Mention flat-rate pricing                │   │
│  │      * UPS: Calculate & display dimensional weight   │   │
│  │    - Add warnings if applicable                       │   │
│  └────────────────────────────────────────────────────────┘   │
│         │                                                      │
│         ▼                                                      │
│  RETURN PackingResult object                                  │
│  └────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               │ JSON Response
               │ {strategy, recommendation, dimensions, 
               │  weight, packages, notes}
               ▼
┌─────────────────────────────────────────────────────────────────┐
│               FRONTEND (React Component)                        │
│                                                                 │
│  setPackingRecommendation(data)  ← Receive response           │
│  setPackingLoading(false)         ← Hide spinner              │
│                                                                 │
│  UI automatically re-renders with recommendation              │
└─────────────────────────────────────────────────────────────────┘
```

## Component Structure

```
ShippingDashboard
├── State Variables
│   ├── orders: Order[]
│   ├── selectedOrder: Order | null
│   ├── packingRecommendation: PackingResult | null (NEW)
│   ├── packingLoading: boolean (NEW)
│   └── packingError: string | null (NEW)
│
├── Functions
│   ├── fetchOrders()
│   ├── updateShippingDetails()
│   ├── validateAddressWithBackoff()
│   ├── getPackingRecommendation() (NEW)
│   └── trackShipment()
│
└── Render
    └── <div className="dashboard-layout">
        ├── <div className="order-list-panel">
        │   └── Order list items
        │
        └── <div className="order-details-panel">
            ├── Section 1: Shipping Info
            ├── Section 2: Content & Packaging
            ├── Section 3: Billing Options
            ├── Section 4: Shipping Options
            └── Section 5: PACKING & BOX OPTIMIZATION (NEW)
                ├── Get Packing Recommendation Button
                ├── [Loading State]
                ├── [Error State]
                └── [Result Card]
                    ├── Strategy Header
                    ├── Recommendation Text
                    ├── Details Grid (Dimensions, Packages, Weight)
                    ├── Notes Section
                    └── Recalculate Button
```

## Algorithm Flowchart

```
START: calculate_packing()
  │
  ├─ Validate all parameters provided?
  │  ├─ NO: Return generic_packing_result()
  │  └─ YES: Continue
  │
  ├─ Shipping method exists in SPECS?
  │  ├─ NO: Return default_packing_result()
  │  └─ YES: Continue
  │
  ├─ Get shipping method specs
  │  └─ max_weight, max_length, max_girth, optimal_boxes
  │
  ├─ FOR EACH box in optimal_boxes:
  │  │
  │  ├─ FOR EACH of 6 orientations:
  │  │  │
  │  │  ├─ Convert dimensions: MM → Inches
  │  │  │
  │  │  ├─ Add padding (10mm on all sides)
  │  │  │
  │  │  ├─ Calculate items per dimension:
  │  │  │  ├─ items_x = box_length ÷ item_length
  │  │  │  ├─ items_y = box_width ÷ item_width
  │  │  │  └─ items_z = box_height ÷ item_height
  │  │  │
  │  │  ├─ Total items = items_x × items_y × items_z
  │  │  │
  │  │  ├─ Check: Total items ≥ quantity?
  │  │  │  ├─ NO: Skip this orientation
  │  │  │  └─ YES: Continue
  │  │  │
  │  │  ├─ Calculate volume waste:
  │  │  │  ├─ Used volume = (length × items_x) × 
  │  │  │  │                 (width × items_y) × 
  │  │  │  │                 (height × items_z)
  │  │  │  ├─ Total volume = box_length × box_width × box_height
  │  │  │  └─ Waste = Total - Used
  │  │  │
  │  │  ├─ Is this the best arrangement so far?
  │  │  │  ├─ YES: Store as best_arrangement, min_waste
  │  │  │  └─ NO: Continue
  │  │
  │  ├─ Any valid arrangement found for this box?
  │  │  ├─ YES: Return this as best_box (first fit)
  │  │  └─ NO: Try next box
  │  │
  │
  ├─ No box fit perfectly?
  │  └─ Use largest available box
  │
  ├─ Calculate total packages needed:
  │  └─ packages = ceil(quantity ÷ items_per_box)
  │
  ├─ Build recommendation string:
  │  ├─ If 1 package: "Pack all X items in single box"
  │  └─ If >1: "Split across N boxes, X items per box"
  │
  ├─ Add method-specific notes:
  │  ├─ If USPS: Mention flat-rate pricing
  │  └─ If UPS: Calculate L + 2(W+H), warn if >300"
  │
  ├─ Create PackingResult object with:
  │  ├─ strategy (box name)
  │  ├─ recommendation (human-readable text)
  │  ├─ estimated_package_dimensions
  │  ├─ estimated_total_weight_lbs
  │  ├─ number_of_packages
  │  └─ notes (list of strings)
  │
  └─ RETURN PackingResult
```

## State Machine Diagram

```
┌─────────────────────┐
│   INITIAL STATE     │
│ (no recommendation) │
└──────────┬──────────┘
           │
           │ User clicks "Get Packing Recommendation"
           ▼
┌─────────────────────┐
│  LOADING STATE      │
│ (calculating...)    │
│ (Show spinner)      │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
    │ (success)   │ (error)
    ▼             ▼
┌─────────────────────┐  ┌──────────────────┐
│  RESULT STATE       │  │  ERROR STATE     │
│ (show card)         │  │ (show error msg) │
│ (show notes)        │  └──────────────────┘
│ (show details)      │        │
└──────────┬──────────┘        │ (dismiss or retry)
           │                   │
           │ (click recalc)    │
           │ or (click close)  │
           │                   │
           └───────┬───────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ INITIAL STATE    │
          │ (reset)          │
          └──────────────────┘
```

## Dimension Orientation Test Sequence

For a model with dimensions 100×75×50 mm in a 12"×10"×8" box:

```
Orientation 1: Length=100, Width=75, Height=50
  → Items fit: 3 × 2 × 1 = 6 items
  → Waste: 45 cubic inches

Orientation 2: Length=100, Width=50, Height=75
  → Items fit: 3 × 2 × 1 = 6 items
  → Waste: 52 cubic inches

Orientation 3: Length=75, Width=100, Height=50
  → Items fit: 2 × 3 × 1 = 6 items
  → Waste: 45 cubic inches (tied with Orientation 1)

Orientation 4: Length=75, Width=50, Height=100
  → Items don't fit: dimensions too large

Orientation 5: Length=50, Width=100, Height=75
  → Items fit: 4 × 2 × 1 = 8 items
  → Waste: 32 cubic inches ✓ BEST

Orientation 6: Length=50, Width=75, Height=100
  → Items don't fit: height too large

WINNER: Orientation 5 (4×2×1 grid arrangement, min waste)
```

## Integration Points

```
Quote System
     │
     ├─ Captures model dimensions during STL analysis
     └─ Stores in Quote and PrintOrder via model_length_mm, etc.
                                        │
                                        ▼
                            Shipping Dashboard
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                    ▼           ▼           ▼
            Address      Packing      Tracking
            Validation   Optimization
                    │           │           │
                    └───────────┼───────────┘
                                ▼
                        Shipping Label
                        Creation & Cost
```
