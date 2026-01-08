# Packing Optimization Quick Reference

## What This Feature Does

📦 **Smart Box Recommendations** - When shipping orders, the system analyzes model dimensions + quantity to recommend:
- Exact box type to use (Small, Medium, Large, etc.)
- How many items fit per box  
- Total number of packages needed
- Shipping cost optimization insights

## For Warehouse Team

### Quick Steps:
1. Open Shipping Dashboard → Select an order
2. Scroll to "Section 5: Packing & Box Optimization"
3. Click **"📦 Get Packing Recommendation"**
4. Read the recommendation and follow the packing advice

### Example Result:
```
Strategy: Large Box
Recommendation: Pack all 3 items in a single Large Box (24"×18"×12")
Arrangement: 2×1×1 grid
Weight per package: ~2.5 lbs
Note: Use adequate protective padding between items
```

## Supported Shipping Methods

### USPS Methods:
- Ground Advantage (70 lbs max, flat-rate boxes)
- Priority Mail (70 lbs max, flat-rate boxes)
- Priority Mail Express (70 lbs max, flat-rate boxes)

### UPS Methods:
- UPS Ground (150 lbs max, multiple box sizes)
- UPS 2nd Day Air (150 lbs max)
- UPS Next Day Air (150 lbs max)

## Key Features

✅ **Automatic Box Selection** - Picks the most efficient box for your items  
✅ **Quantity Optimization** - Calculates items per box automatically  
✅ **Carrier Restrictions** - Respects weight limits and dimension rules  
✅ **Cost Insights** - Helps minimize shipping costs through smart packing  
✅ **Weight Estimates** - Calculates total weight for rate calculations  
✅ **Protective Warnings** - Alerts for oversized items or special handling needs  

## Behind the Scenes

The system uses the order's:
- **Model dimensions** (length, width, height in mm)
- **Quantity** (how many items to pack)
- **Weight** (per single item)
- **Shipping method** (carrier selection)

Then applies a smart algorithm that:
1. Tests all possible box orientations
2. Calculates how many items fit in each arrangement
3. Picks the box with minimum wasted space
4. Returns optimized packing instructions

## API Endpoint

**For Developers:** `POST /api/packing-recommendation`

Request:
```json
{
  "model_length_mm": 100,
  "model_width_mm": 75,
  "model_height_mm": 50,
  "quantity": 5,
  "weight_g": 250,
  "shipping_method": "UPS Ground"
}
```

Response includes strategy, box type, arrangement, weight, and method-specific notes.

## FAQ

**Q: What if dimensions aren't available?**
A: The system provides generic guidance. Dimensions are captured during quote creation.

**Q: Can I override the recommendation?**
A: Yes! These are suggestions. You can always use a different box if needed.

**Q: Does this affect shipping cost?**
A: Indirectly - choosing the right box can help minimize dimensional weight charges.

**Q: What if an item doesn't fit in any box?**
A: The system alerts you and recommends using a custom crate or splitting the order.

**Q: How accurate are the weight estimates?**
A: Estimates include 50g padding per item. Actual weights may vary.

## Related Features

- **Address Validation** - Validate shipping addresses with carriers
- **Shipping Rates** - Get real-time rate quotes
- **Label Creation** - Generate shipping labels
- **Tracking** - Monitor shipment progress

## Support

- Check model dimensions are captured in quote
- Verify shipping method name is correct
- Clear browser cache if experiencing issues
- Check browser console for error details
