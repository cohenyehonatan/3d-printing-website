"""
Packing Optimizer - Calculates efficient packing strategies for orders
based on model dimensions, quantity, and shipping method restrictions.
"""

from typing import Optional, List, Dict
from dataclasses import dataclass
import math

@dataclass
class PackingResult:
    """Result of packing calculation"""
    strategy: str  # e.g., "single_box", "multiple_boxes", "custom_crate"
    recommendation: str  # Human-readable packing advice
    estimated_package_dimensions: Dict[str, float]  # in inches (L x W x H)
    estimated_total_weight_lbs: float
    estimated_cost_per_box: float
    number_of_packages: int
    notes: List[str]  # Additional notes/warnings


# ============================================================================
# SHIPPING METHOD RESTRICTIONS & OPTIMAL BOX SIZES
# ============================================================================

SHIPPING_METHOD_SPECS = {
    "USPS Ground Advantage": {
        "max_length_inches": 130,  # 108" length + 2*(width + height)
        "max_girth_inches": 130,   # 2*(width + height) when length > width+height
        "max_weight_lbs": 70,
        "optimal_boxes": [
            {"name": "Small Priority Box", "length": 5.5, "width": 8.625, "height": 1.625, "max_weight_lbs": 70},
            {"name": "Medium Flat-Rate Box", "length": 11, "width": 8.5, "height": 5.5, "max_weight_lbs": 70},
            {"name": "Large Priority Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 70},
        ]
    },
    "USPS Priority Mail": {
        "max_length_inches": 130,
        "max_girth_inches": 130,
        "max_weight_lbs": 70,
        "optimal_boxes": [
            {"name": "Small Priority Box", "length": 5.5, "width": 8.625, "height": 1.625, "max_weight_lbs": 70},
            {"name": "Medium Flat-Rate Box", "length": 11, "width": 8.5, "height": 5.5, "max_weight_lbs": 70},
            {"name": "Large Priority Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 70},
        ]
    },
    "USPS Priority Mail Express": {
        "max_length_inches": 130,
        "max_girth_inches": 130,
        "max_weight_lbs": 70,
        "optimal_boxes": [
            {"name": "Small Priority Box", "length": 5.5, "width": 8.625, "height": 1.625, "max_weight_lbs": 70},
            {"name": "Medium Flat-Rate Box", "length": 11, "width": 8.5, "height": 5.5, "max_weight_lbs": 70},
            {"name": "Large Priority Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 70},
        ]
    },
    "UPS Ground": {
        "max_length_inches": 165,
        "max_girth_inches": 300,  # Sum of 2*(width+height)
        "max_weight_lbs": 150,
        "optimal_boxes": [
            {"name": "Small Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 150},
            {"name": "Medium Box", "length": 18, "width": 12, "height": 10, "max_weight_lbs": 150},
            {"name": "Large Box", "length": 24, "width": 18, "height": 12, "max_weight_lbs": 150},
            {"name": "Extra Large Box", "length": 30, "width": 24, "height": 18, "max_weight_lbs": 150},
        ]
    },
    "UPS 2nd Day Air": {
        "max_length_inches": 165,
        "max_girth_inches": 300,
        "max_weight_lbs": 150,
        "optimal_boxes": [
            {"name": "Small Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 150},
            {"name": "Medium Box", "length": 18, "width": 12, "height": 10, "max_weight_lbs": 150},
            {"name": "Large Box", "length": 24, "width": 18, "height": 12, "max_weight_lbs": 150},
        ]
    },
    "UPS Next Day Air": {
        "max_length_inches": 165,
        "max_girth_inches": 300,
        "max_weight_lbs": 150,
        "optimal_boxes": [
            {"name": "Small Box", "length": 12, "width": 12, "height": 8, "max_weight_lbs": 150},
            {"name": "Medium Box", "length": 18, "width": 12, "height": 10, "max_weight_lbs": 150},
            {"name": "Large Box", "length": 24, "width": 18, "height": 12, "max_weight_lbs": 150},
        ]
    },
}

PADDING_MM = 10  # 10mm padding on all sides per item for safety


def mm_to_inches(mm: float) -> float:
    """Convert millimeters to inches"""
    return mm / 25.4


def calculate_girth(width_inches: float, height_inches: float) -> float:
    """Calculate package girth (2*(width + height))"""
    return 2 * (width_inches + height_inches)


def fits_in_box(
    model_length_mm: Optional[float],
    model_width_mm: Optional[float],
    model_height_mm: Optional[float],
    quantity: int,
    box_length: float,
    box_width: float,
    box_height: float,
) -> tuple[bool, str]:
    """
    Check if items fit in a box and return whether they fit plus arrangement info.
    Returns: (fits: bool, arrangement: str)
    """
    if not all([model_length_mm, model_width_mm, model_height_mm]):
        return False, "Missing dimension data"
    
    # Type narrowing: at this point, all dimensions are guaranteed to be non-None
    assert model_length_mm is not None
    assert model_width_mm is not None
    assert model_height_mm is not None
    
    # Convert to inches and add padding
    item_l = mm_to_inches(model_length_mm) + (2 * mm_to_inches(PADDING_MM))
    item_w = mm_to_inches(model_width_mm) + (2 * mm_to_inches(PADDING_MM))
    item_h = mm_to_inches(model_height_mm) + (2 * mm_to_inches(PADDING_MM))
    
    # Try different orientations
    orientations = [
        (item_l, item_w, item_h),
        (item_l, item_h, item_w),
        (item_w, item_l, item_h),
        (item_w, item_h, item_l),
        (item_h, item_l, item_w),
        (item_h, item_w, item_l),
    ]
    
    best_arrangement = None
    min_waste = float('inf')
    
    for orient_l, orient_w, orient_h in orientations:
        # Calculate how many items fit along each dimension
        items_along_l = int(box_length / orient_l)
        items_along_w = int(box_width / orient_w)
        items_along_h = int(box_height / orient_h)
        
        total_items = items_along_l * items_along_w * items_along_h
        
        if total_items >= quantity:
            # Calculate volume waste
            used_volume = (orient_l * items_along_l) * (orient_w * items_along_w) * (orient_h * items_along_h)
            box_volume = box_length * box_width * box_height
            waste = box_volume - used_volume
            
            if waste < min_waste:
                min_waste = waste
                best_arrangement = (items_along_l, items_along_w, items_along_h)
    
    if best_arrangement:
        items_l, items_w, items_h = best_arrangement
        arrangement_str = f"{items_l}×{items_w}×{items_h} grid"
        return True, arrangement_str
    
    return False, "Does not fit"


def calculate_packing(
    model_length_mm: Optional[float],
    model_width_mm: Optional[float],
    model_height_mm: Optional[float],
    quantity: int,
    weight_per_unit_g: float,
    shipping_method: str,
    packaging_padding_g: float = 50,  # Padding/packaging weight per unit
) -> PackingResult:
    """
    Calculate optimal packing strategy for an order.
    
    Parameters:
    - model_length_mm, model_width_mm, model_height_mm: model dimensions in mm
    - quantity: number of items to pack
    - weight_per_unit_g: weight of a single item in grams
    - shipping_method: selected shipping method (e.g., "USPS Ground Advantage")
    - packaging_padding_g: estimated packaging weight per item
    
    Returns: PackingResult with recommendations
    """
    
    if shipping_method not in SHIPPING_METHOD_SPECS:
        return _default_packing_result(shipping_method)
    
    specs = SHIPPING_METHOD_SPECS[shipping_method]
    boxes = specs["optimal_boxes"]
    max_weight_lbs = specs["max_weight_lbs"]
    
    # If no dimensions provided, return generic recommendation
    if not all([model_length_mm, model_width_mm, model_height_mm]):
        return _generic_packing_result(quantity, weight_per_unit_g, shipping_method)
    
    # Calculate total weight per unit
    weight_per_unit_lbs = (weight_per_unit_g + packaging_padding_g) / 453.592
    max_items_per_weight = int(max_weight_lbs / weight_per_unit_lbs) if weight_per_unit_lbs > 0 else quantity
    
    # Find best box option
    best_box = None
    best_count = 0
    best_arrangement = ""
    total_packages = 1
    items_packed = 0
    
    for box in boxes:
        fits, arrangement = fits_in_box(
            model_length_mm, model_width_mm, model_height_mm,
            min(quantity - items_packed, max_items_per_weight),
            box["length"], box["width"], box["height"]
        )
        
        if fits:
            if best_box is None:
                best_box = box
                best_arrangement = arrangement
                items_packed = min(quantity, max_items_per_weight)
                if items_packed < quantity:
                    total_packages = math.ceil(quantity / items_packed)
            break
    
    if best_box is None:
        # Fall back to largest available box
        best_box = boxes[-1]
        best_arrangement = f"Stacked (qty: {quantity})"
        total_packages = math.ceil(quantity / max_items_per_weight)
    
    # Calculate estimated package dimensions (with some buffer)
    package_length = best_box["length"] + 0.5
    package_width = best_box["width"] + 0.5
    package_height = best_box["height"] + 0.5
    
    # Calculate total weight per package
    items_per_package = max(1, int(quantity / total_packages))
    weight_per_package_lbs = items_per_package * weight_per_unit_lbs
    
    # Build recommendation
    strategy = best_box["name"]
    
    if total_packages == 1:
        recommendation = (
            f"Pack all {quantity} items in a single {best_box['name']} "
            f"({best_box['length']}\" × {best_box['width']}\" × {best_box['height']}\")"
        )
    else:
        items_per_pkg = max(1, quantity // total_packages)
        recommendation = (
            f"Split across {total_packages} boxes ({best_box['name']}). "
            f"Pack ~{items_per_pkg} items per box with protective padding."
        )
    
    notes = [
        f"Arrangement: {best_arrangement}",
        f"Weight per package: ~{weight_per_package_lbs:.1f} lbs",
    ]
    
    # Add specific warnings/tips based on shipping method
    if "USPS" in shipping_method:
        notes.append("USPS flat-rate boxes have fixed pricing regardless of weight")
        if total_packages > 1:
            notes.append("Each package will be charged separately")
    elif "UPS" in shipping_method:
        girth = calculate_girth(package_width, package_height)
        length_plus_girth = package_length + girth
        notes.append(f"UPS Dimensional Weight Formula: {package_length:.1f}\" + {girth:.1f}\" girth = {length_plus_girth:.1f}\"")
        if length_plus_girth > 300:
            notes.append("⚠️ WARNING: Package may be oversized for standard shipping")
    
    return PackingResult(
        strategy=strategy,
        recommendation=recommendation,
        estimated_package_dimensions={
            "length_inches": package_length,
            "width_inches": package_width,
            "height_inches": package_height,
        },
        estimated_total_weight_lbs=weight_per_package_lbs * total_packages,
        estimated_cost_per_box=best_box.get("estimated_cost", 0),
        number_of_packages=total_packages,
        notes=notes,
    )


def _generic_packing_result(quantity: int, weight_per_unit_g: float, shipping_method: str) -> PackingResult:
    """Return a generic packing result when dimensions are not available"""
    
    weight_per_unit_lbs = weight_per_unit_g / 453.592
    total_weight_lbs = weight_per_unit_lbs * quantity
    
    recommendation = (
        f"Dimension data not available. Recommend packing {quantity} items "
        "with adequate protective padding. Use the smallest available box that accommodates all items."
    )
    
    notes = [
        "To optimize packing, model dimensions (length, width, height) should be captured during quote creation",
        f"Estimated total weight: {total_weight_lbs:.1f} lbs",
    ]
    
    return PackingResult(
        strategy="Generic - Dimensions Not Available",
        recommendation=recommendation,
        estimated_package_dimensions={
            "length_inches": 0,
            "width_inches": 0,
            "height_inches": 0,
        },
        estimated_total_weight_lbs=total_weight_lbs,
        estimated_cost_per_box=0,
        number_of_packages=1,
        notes=notes,
    )


def _default_packing_result(shipping_method: str) -> PackingResult:
    """Return a default packing result for unknown shipping methods"""
    
    return PackingResult(
        strategy="Custom Packaging",
        recommendation=f"Unknown shipping method: {shipping_method}. Use standard boxes with adequate protective packaging.",
        estimated_package_dimensions={
            "length_inches": 0,
            "width_inches": 0,
            "height_inches": 0,
        },
        estimated_total_weight_lbs=0,
        estimated_cost_per_box=0,
        number_of_packages=1,
        notes=["Contact support for specific packing recommendations for this shipping method"],
    )
