"""
Backfill model dimensions for past orders.

This script helps populate missing dimension data for past orders. Since the dimension
fields (model_length_mm, model_width_mm, model_height_mm) were added after orders 5 and 6
were created, they need to be populated manually.

The script can:
1. List orders missing dimensions
2. Estimate dimensions from volume (rough approximation)
3. Allow manual input of actual dimensions
4. Update the database

Usage:
    python scripts/backfill_model_dimensions.py list
    python scripts/backfill_model_dimensions.py list --status pending
    python scripts/backfill_model_dimensions.py estimate
    python scripts/backfill_model_dimensions.py manual --order-id 5
    python scripts/backfill_model_dimensions.py manual --order-id 6
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import SessionLocal
from api.models import PrintOrder
import math


def list_orders_missing_dimensions(status_filter=None):
    """List all orders with missing dimension data."""
    db = SessionLocal()
    try:
        # Find all print orders with NULL dimensions
        query = db.query(PrintOrder).filter(
            (PrintOrder.model_length_mm.is_(None) |
             PrintOrder.model_width_mm.is_(None) |
             PrintOrder.model_height_mm.is_(None))
        )
        
        if status_filter:
            query = query.filter(PrintOrder.order_status == status_filter)
        
        orders = query.all()
        
        if not orders:
            print("✓ No orders missing dimensions!")
            return 0
        
        print(f"\n{'Order #':<15} {'Status':<20} {'Volume (cm³)':<15} {'Weight (g)':<12} {'Label Status':<15}")
        print("-" * 85)
        
        for order in orders:
            print(f"{order.order_number:<15} {order.order_status:<20} "
                  f"{order.volume_cm3:<15.2f} {order.weight_g:<12.2f} {order.label_status:<15}")
        
        print(f"\nTotal: {len(orders)} orders")
        
        db.close()
        return len(orders)
        
    except Exception as e:
        print(f"✗ Error listing orders: {e}")
        db.close()
        return -1


def estimate_dimensions(volume_cm3):
    """
    Estimate dimensions from volume using a cube assumption.
    This is a rough estimate - actual dimensions may vary.
    
    Args:
        volume_cm3: Volume in cubic centimeters
    
    Returns:
        tuple: (length_mm, width_mm, height_mm) assuming cubic shape
    """
    # Assuming cubic shape: volume = side³
    side_cm = volume_cm3 ** (1/3)
    side_mm = side_cm * 10  # Convert cm to mm
    
    return round(side_mm, 2), round(side_mm, 2), round(side_mm, 2)


def estimate_for_all(dry_run=False, verbose=False):
    """
    Estimate dimensions for all orders with missing data.
    
    Args:
        dry_run: If True, only show what would be updated
        verbose: If True, print detailed information
    """
    db = SessionLocal()
    try:
        orders = db.query(PrintOrder).filter(
            (PrintOrder.model_length_mm.is_(None) |
             PrintOrder.model_width_mm.is_(None) |
             PrintOrder.model_height_mm.is_(None))
        ).all()
        
        if not orders:
            print("✓ No orders need dimension estimation!")
            db.close()
            return 0
        
        updated = 0
        
        for order in orders:
            if order.volume_cm3 is None:
                if verbose:
                    print(f"⊘ Order {order.order_number}: No volume data - skipping")
                continue
            
            # Estimate dimensions from volume
            length, width, height = estimate_dimensions(order.volume_cm3)
            
            if verbose:
                print(f"Order {order.order_number}:")
                print(f"  Volume: {order.volume_cm3} cm³")
                print(f"  Estimated dimensions: {length}mm × {width}mm × {height}mm")
            
            if not dry_run:
                order.model_length_mm = length
                order.model_width_mm = width
                order.model_height_mm = height
                updated += 1
        
        if not dry_run:
            db.commit()
            print(f"\n✓ Updated {updated} orders with estimated dimensions")
        else:
            print(f"\n[DRY RUN] Would update {updated} orders with estimated dimensions")
        
        db.close()
        return updated
        
    except Exception as e:
        print(f"✗ Error during estimation: {e}")
        db.close()
        return -1


def manual_input(order_id):
    """
    Manually input dimensions for a specific order.
    
    Args:
        order_id: ID of the PrintOrder to update
    """
    db = SessionLocal()
    try:
        order = db.query(PrintOrder).filter(PrintOrder.id == order_id).first()
        
        if not order:
            print(f"✗ Order with ID {order_id} not found")
            db.close()
            return -1
        
        print(f"\nUpdating dimensions for Order {getattr(order, 'order_number', 'N/A')}")
        print(f"Current: volume={getattr(order, 'volume_cm3', 'N/A')}cm³, weight={getattr(order, 'weight_g', 'N/A')}g")
        
        # Get estimated dimensions as suggestion
        if getattr(order, 'volume_cm3', None):
            est_l, est_w, est_h = estimate_dimensions(getattr(order, 'volume_cm3', None))
            print(f"Estimated from volume: {est_l}mm × {est_w}mm × {est_h}mm\n")
        
        try:
            length = float(input("Enter length (mm): "))
            width = float(input("Enter width (mm): "))
            height = float(input("Enter height (mm): "))
            
            # Confirm
            print(f"\nWill set: {length}mm × {width}mm × {height}mm")
            confirm = input("Confirm? (y/n): ").lower()
            
            if confirm == 'y':
                setattr(order, 'model_length_mm', length)
                setattr(order, 'model_width_mm', width)
                setattr(order, 'model_height_mm', height)
                db.commit()
                print("✓ Order updated successfully!")
                db.close()
                return 1
            else:
                print("Cancelled.")
                db.close()
                return 0
        
        except ValueError:
            print("✗ Invalid input - please enter numbers")
            db.close()
            return -1
            
    except Exception as e:
        print(f"✗ Error: {e}")
        db.close()
        return -1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill model dimensions for past orders"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List orders missing dimensions')
    list_parser.add_argument('--status', help='Filter by order status (pending, payment_received, etc.)')
    
    # Estimate command
    estimate_parser = subparsers.add_parser('estimate', help='Estimate dimensions from volume')
    estimate_parser.add_argument('--dry-run', action='store_true', help='Show what would be updated')
    estimate_parser.add_argument('--verbose', action='store_true', help='Print detailed info')
    
    # Manual command
    manual_parser = subparsers.add_parser('manual', help='Manually input dimensions')
    manual_parser.add_argument('--order-id', type=int, required=True, help='PrintOrder ID to update')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        list_orders_missing_dimensions(status_filter=args.status)
    elif args.command == 'estimate':
        print("🔄 Estimating dimensions from volume...\n")
        estimate_for_all(dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == 'manual':
        manual_input(args.order_id)
    else:
        parser.print_help()
        print("\n📋 Quick start:")
        print("  1. List orders missing dimensions:")
        print("     python scripts/backfill_model_dimensions.py list")
        print("\n  2. Estimate dimensions (rough approximation):")
        print("     python scripts/backfill_model_dimensions.py estimate --dry-run")
        print("     python scripts/backfill_model_dimensions.py estimate")
        print("\n  3. Manually input dimensions for order 5:")
        print("     python scripts/backfill_model_dimensions.py manual --order-id 5")
