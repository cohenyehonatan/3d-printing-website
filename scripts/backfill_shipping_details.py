#!/usr/bin/env python3
"""
Backfill shipping-related fields on PrintOrder rows.
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from api.database import SessionLocal
from api.models import PrintOrder
from api.quote import (
    MINIMUM_WEIGHT_G,
    base_cost,
    calculate_distance_between_zips,
    calculate_usps_shipping,
    calculate_total_with_tax,
    filament_prices,
    get_usps_zone_from_distance,
    material_densities,
    sales_tax_rates,
    get_state_from_zip,
)


def resolve_density(order: PrintOrder) -> Optional[float]:
    if order.material and order.material.name in material_densities:
        return material_densities[order.material.name]
    if order.model_filename in material_densities:
        return material_densities[order.model_filename]
    return None


def compute_base_weight_g(order: PrintOrder, density: Optional[float]) -> Optional[float]:
    if order.weight_g and order.weight_g > 0:
        return order.weight_g
    if order.volume_cm3 and density:
        return max(order.volume_cm3 * density, MINIMUM_WEIGHT_G)
    return None


def compute_material_cost(order: PrintOrder, density: Optional[float]) -> Optional[float]:
    if density is None:
        return None
    quantity = order.quantity or 1
    if order.weight_g and order.weight_g > 0:
        weight_g = order.weight_g
    elif order.volume_cm3:
        weight_g = max(order.volume_cm3 * density, MINIMUM_WEIGHT_G)
    else:
        return None

    material_name = None
    if order.material and order.material.name in filament_prices:
        material_name = order.material.name
    elif order.model_filename in filament_prices:
        material_name = order.model_filename

    if not material_name:
        return None

    total_weight_kg = weight_g / 1000
    return total_weight_kg * filament_prices[material_name] * quantity


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill shipping cost/zone/weight on existing print orders."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Recompute for all orders (not just ones missing fields).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned updates without writing to the database.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of orders.")
    args = parser.parse_args()

    db = SessionLocal()
    updated = 0
    skipped = 0
    try:
        orders = db.query(PrintOrder).order_by(PrintOrder.id.asc())
        if args.limit:
            orders = orders.limit(args.limit)

        for order in orders:
            if not args.all:
                if (
                    order.shipping_cost_cents is not None
                    and order.shipping_zone is not None
                    and order.shipping_weight_g is not None
                ):
                    # Still allow total recalculation if totals are missing.
                    if (
                        order.subtotal_cents is not None
                        and order.tax_cents is not None
                        and order.total_cents is not None
                        and order.package_value_cents is not None
                    ):
                        skipped += 1
                        continue

            if not order.delivery_zip_code:
                skipped += 1
                continue

            density = resolve_density(order)
            base_weight_g = compute_base_weight_g(order, density)
            if base_weight_g is None:
                skipped += 1
                continue

            quantity = order.quantity or 1
            shipping_weight_g = (base_weight_g * quantity) * 1.15
            shipping_cost = calculate_usps_shipping(
                order.delivery_zip_code, shipping_weight_g / 1000
            )
            shipping_cost_cents = int(round(shipping_cost * 100))

            origin_zip = os.getenv("ZIP_CODE", "10001")
            distance_miles = calculate_distance_between_zips(
                origin_zip, order.delivery_zip_code
            )
            shipping_zone = get_usps_zone_from_distance(distance_miles)

            if args.dry_run:
                print(
                    f"[DRY RUN] order={order.id} "
                    f"shipping_weight_g={shipping_weight_g:.2f} "
                    f"shipping_cost_cents={shipping_cost_cents} "
                    f"shipping_zone={shipping_zone}"
                )
            else:
                order.shipping_weight_g = shipping_weight_g
                order.shipping_cost_cents = shipping_cost_cents
                order.shipping_zone = shipping_zone

            material_cost = compute_material_cost(order, density)
            if material_cost is None:
                updated += 1
                continue

            rush_surcharge = 20 if order.rush_order else 0
            total_before_tax = base_cost + material_cost + shipping_cost + rush_surcharge
            total_with_tax, sales_tax = calculate_total_with_tax(
                order.delivery_zip_code,
                total_before_tax,
                sales_tax_rates,
                get_state_from_zip,
            )
            subtotal_cents = int(round(total_before_tax * 100))
            tax_cents = int(round(sales_tax * 100))
            total_cents = int(round(total_with_tax * 100))

            if args.dry_run:
                print(
                    f"[DRY RUN] order={order.id} "
                    f"subtotal_cents={subtotal_cents} tax_cents={tax_cents} "
                    f"total_cents={total_cents}"
                )
            else:
                order.subtotal_cents = subtotal_cents
                order.tax_cents = tax_cents
                order.total_cents = total_cents
                if order.package_value_cents is None:
                    order.package_value_cents = total_cents

            updated += 1

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

        print(f"Updated {updated} orders, skipped {skipped}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
