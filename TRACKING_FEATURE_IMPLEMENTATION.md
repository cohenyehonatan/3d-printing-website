# UPS Shipment Tracking Feature Implementation

## Overview
Added a "Track Shipment" button to the Shipping Dashboard that integrates with the UPS Track API to fetch real-time tracking information, including a 120-day data retention period warning system.

## Components Modified

### 1. Backend - `api/ups_service.py`
**Added:** `track_shipment()` method to the `UPSService` class
- Authenticates with UPS OAuth2 using cached tokens
- Calls the UPS Track API v1 endpoint (`/track/v1/details/{inquiryNumber}`)
- Extracts and parses tracking data including:
  - Current status code and description
  - Current location (city, state, zip)
  - Expected delivery date
  - Complete activity history (up to 10 most recent activities)
  - Shipment details (shipper, recipient, service)
- Handles errors gracefully (404s, rate limiting, timeouts)
- Returns structured JSON response with error flags

### 2. Backend - `api/quote.py`
**Added:** `GET /api/dashboard/track/{tracking_number}` endpoint
- Leverages existing UPS service authentication
- Accepts UPS tracking numbers
- Delegates to `ups_service.track_shipment()`
- Returns formatted tracking data to frontend

### 3. Frontend - `static/ShippingDashboard.jsx`
**Added Components:**
- `trackShipment()` function - Fetches tracking data via API
- `calculateDaysInRetentionPeriod()` - Calculates days since label creation
- `isTrackingDataExpired()` - Checks if 120 days have passed

**Added State:**
- `trackingData` - Stores tracking response
- `trackingLoading` - Loading state for tracking requests
- `trackingError` - Error messages
- `showTrackingDetails` - Toggle for tracking details display

**Added UI Elements:**
- "📍 Track Shipment" button (disabled when tracking data expired)
- Retention period warning banners:
  - Red "Tracking Data Expired" banner when > 120 days
  - Yellow "Tracking Data Expiring Soon" banner when > 100 days
- Tracking details panel with:
  - Current status badge (with code and description)
  - Current location information
  - Expected delivery date
  - Activity timeline with complete history

### 4. Frontend - `static/ShippingDashboard.css`
**Added Styles:**
- `.track-shipment-btn` - Button styling with gradient
- `.tracking-section` - Container styling
- `.tracking-details` - Details panel styling
- `.tracking-error` - Error message styling
- `.warning-banner` - Warning banner styling (retention-expired, retention-warning)
- `.status-badge` - Status display styling
- `.timeline` and `.timeline-item` - Activity history timeline
- `.location-info`, `.delivery-date` - Information box styling
- Responsive mobile adjustments

## Key Features

### 1. Real-Time Tracking
- Fetches current shipment status directly from UPS
- Shows location, delivery date, and activity history
- Updates on demand with "Track Shipment" button

### 2. 120-Day Retention Period
As per UPS Track API documentation:
- Displays "Tracking Data Expired" banner after 120 days from label creation
- Displays "Tracking Data Expiring Soon" warning after 100 days
- Disables "Track Shipment" button when data is expired
- Displays remaining days count in warning message

### 3. Error Handling
- Graceful error messages for missing tracking numbers
- API error handling (404s, rate limits, timeouts)
- User-friendly error displays in the UI
- Detailed console logging for debugging

### 4. Activity Timeline
- Displays up to 10 most recent tracking activities
- Shows date, status, and location for each activity
- Visual timeline design with connecting line and circle markers

## API Endpoints

### UPS Track API Integration
**Endpoint:** `GET /api/dashboard/track/{tracking_number}`
**Query Parameters:**
- `locale` - Language/country code (default: en_US)
- `returnSignature` - Include signature images (false)
- `returnMilestones` - Include milestone data (true)
- `returnPOD` - Include proof of delivery (false)

**Required Headers:**
- `Authorization` - Bearer token (OAuth2)
- `x-merchant-id` - UPS account number
- `transId` - Transaction ID
- `transactionSrc` - Source identifier

## Configuration
Uses existing UPS credentials from `.env`:
- `UPS_CLIENT_ID`
- `UPS_CLIENT_SECRET`
- `UPS_ACCOUNT_NUMBER`
- `UPS_ENVIRONMENT` (cie or production)

## Data Retention Policy
The implementation follows UPS's 120-day retention policy:
- Tracking data is available for 120 days from shipment pickup
- After 120 days, historical data cannot be retrieved
- The banner warns users approaching this limit
- Button is disabled when data expires

## Error Scenarios Handled
1. Missing tracking number - Shows error message
2. Invalid tracking number (404) - Shows "not found" message
3. Rate limiting (429) - Shows "too many requests" message
4. Authentication errors - Shows "authentication failed" message
5. Timeout errors - Shows "request timed out" message
6. Data expiration (>120 days) - Disables button and shows banner

## Future Enhancements
- Support for USPS tracking (currently UPS only)
- Tracking number validation before API call
- Auto-refresh of tracking data at intervals
- Email notifications for delivery updates
- SMS delivery notifications
- Multiple shipment tracking
