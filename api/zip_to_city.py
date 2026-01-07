import csv
from pathlib import Path

# Function to load the ZIP code data from CSV using built-in csv module
def load_zip_data():
    zip_data = {}
    # Use absolute path relative to this module
    csv_path = Path(__file__).parent.parent / 'uszips.csv'
    with open(csv_path, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            zip_data[row['zip']] = row['city']
    return zip_data

# Store the loaded ZIP data in memory
zip_data = load_zip_data()

# Function to get city from ZIP code
def get_city_from_zip(zip_code):
    return zip_data.get(str(zip_code), None)  # Convert to string for consistency