import csv
from pathlib import Path

# Function to load sales tax rates from the CSV using built-in csv module
def load_sales_tax_rates():
    tax_rates = {}
    # Use absolute path relative to this module
    csv_path = Path(__file__).parent.parent / 'stateSalesTax.csv'
    with open(csv_path, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Remove the '%' and convert to a decimal
            combined_rate = float(row['Combined Rate'].strip('%')) / 100
            state_name = row['State']
            # Remove footnote markers like (a), (b), (c) etc
            state_name = state_name.split('(')[0].strip()
            tax_rates[state_name] = combined_rate
    return tax_rates

# Store the sales tax rates in memory
sales_tax_rates = load_sales_tax_rates()

# Function to get sales tax by state
def get_sales_tax_rate(state):
    return sales_tax_rates.get(state, 0)