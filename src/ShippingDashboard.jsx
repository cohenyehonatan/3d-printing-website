import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import GlobalHeader from './GlobalHeader';
import './ShippingDashboard.css';
import { apiFetch } from './api.js';

// UPS Tracking Status Mappings
const UPS_STATUS_CODES = {
  // Label Creation
  'P4': { label: 'Package Received', icon: '📦', category: 'created' },
  '9D': { label: 'Label Printed', icon: '🏷️', category: 'created' },
  '9J': { label: 'Label Applied', icon: '🏷️', category: 'created' },
  '9K': { label: 'Label Applied', icon: '🏷️', category: 'created' },
  
  // In Transit
  'F3': { label: 'Departed Facility', icon: '🚚', category: 'in_transit' },
  'F0': { label: 'Arrived at Facility', icon: '📍', category: 'in_transit' },
  'GD': { label: 'Arrived at Facility', icon: '📍', category: 'in_transit' },
  'I8': { label: 'In Transit', icon: '📬', category: 'in_transit' },
  'SX': { label: 'In Transit', icon: '📬', category: 'in_transit' },
  'RK': { label: 'Out for Delivery Today', icon: '🚗', category: 'in_transit' },
  'RL': { label: 'Out for Delivery', icon: '🚗', category: 'in_transit' },
  '4F': { label: 'In Transit; Delivery Scheduled', icon: '📬', category: 'in_transit' },
  'LY': { label: 'In Transit for Final Delivery', icon: '📬', category: 'in_transit' },
  '1P': { label: 'In Transit, Scheduling Delivery', icon: '📬', category: 'in_transit' },
  
  // Delivered
  'F4': { label: 'Delivered', icon: '✓', category: 'delivered' },
  'FT': { label: 'Picked Up', icon: '✓', category: 'delivered' },
  'KM': { label: 'Delivered', icon: '✓', category: 'delivered' },
  'FN': { label: 'Delivery Confirmed', icon: '✓', category: 'delivered' },
  'F7': { label: 'Delivered to Agent', icon: '✓', category: 'delivered' },
  'ZP': { label: 'Awaiting Pickup', icon: '📍', category: 'delivered' },
  'I5': { label: 'Awaiting Pickup', icon: '📍', category: 'delivered' },
  
  // Delayed/Exception
  '1B': { label: 'Delayed in Transit', icon: '⚠️', category: 'delayed' },
  'GB': { label: 'Delivery Attempted', icon: '⚠️', category: 'delayed' },
  'HA': { label: 'Delayed - Check Back', icon: '⏳', category: 'delayed' },
  'TN': { label: 'Unable to Deliver On Schedule', icon: '⏳', category: 'delayed' },
  '2O': { label: 'Departed from Facility', icon: '🚚', category: 'in_transit' },
  
  // Return/Exception
  'DL': { label: 'Being Returned to Sender', icon: '↩️', category: 'return' },
  'KP': { label: 'Return in Progress', icon: '↩️', category: 'return' },
  'O4': { label: 'Return in Progress', icon: '↩️', category: 'return' },
  'KT': { label: 'Delivery Refused', icon: '✗', category: 'exception' },
};

const UPS_GENERIC_STATUS_BUCKETS = [
  {
    label: 'Delay: Weather',
    icon: '🌧️',
    category: 'delayed',
    codes: new Set([
      '2A', '3D', '6D', '7V', '7W', '7X', 'DJ', 'DF', 'PZ', 'CR', 'EJ', 'EA', 'C5',
      '51', '52', '53'
    ])
  },
  {
    label: 'Delay: Conditions',
    icon: '⚠️',
    category: 'delayed',
    codes: new Set([
      '8', '31', '2H', '2Y', '2Z', '3A', '3B', '3C', '7Y', '8K', '8L', '8Y', '8Z',
      '9M', '9N', '9O', '9P', '9Q', '9R', '9S', '9T', '9U', '9V', '9X', '9Y', '9Z',
      'DU', 'EH', 'EN', 'NW', 'CC', '3T', '7Z'
    ])
  },
  {
    label: 'Delay: Govt Hold',
    icon: '🛃',
    category: 'delayed',
    codes: new Set([
      '5', '1U', '2N', '2T', '2U', '4C', '4T', '7I', '7M', '7P', '7T', '7U', '29',
      '40', '43', '71', '92', 'AO', 'BA', 'BG', 'BH', 'BJ', 'BK', 'BP', 'CE', 'CF', 'CN',
      'CP', 'CX', 'CZ', 'D0', 'D5', 'DN', 'DT', 'E4', 'E8', 'E9', 'ER', 'ES', 'EU',
      'EV', 'EW', 'FE', 'FF', 'GF', 'GZ', 'HW', 'L2', 'L3', 'L5', 'MI', 'OB', 'OI',
      'OQ', 'OT', 'R1', 'R4', 'R5', 'R6', 'R7', 'RA', 'RD', 'RE', 'RM', 'RP', 'RR',
      'RS', 'RU', 'SF', 'SI', 'SJ', 'SL', 'SN', 'SP', 'SS', 'SV', 'SY', 'X2', 'X3',
      'X4', 'X5', 'X6', 'X7', 'X8', 'X9', 'XA', 'XB', 'XC', 'XD', 'XE', 'XG', 'XJ',
      'XK', 'XL', 'XN', 'XO', 'XV', 'XW', 'XY', 'Y1', 'Y2', 'Y3', 'Y4', 'Y5', 'Z1',
      'Z3'
    ])
  }
];

const getGenericStatusFromCode = (code) => {
  if (!code) return null;
  for (const bucket of UPS_GENERIC_STATUS_BUCKETS) {
    if (bucket.codes.has(code)) {
      return {
        icon: bucket.icon,
        label: bucket.label,
        category: bucket.category
      };
    }
  }
  return null;
};

const ShippingDashboard = () => {
  const [orders, setOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [labelStatus, setLabelStatus] = useState({});
  const [editFields, setEditFields] = useState(null);
  
  // Address validation state
  const [validationLoading, setValidationLoading] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [validationSuccess, setValidationSuccess] = useState(false);
  const [validatedAddress, setValidatedAddress] = useState(null);
  const [multipleMatches, setMultipleMatches] = useState(null);
  const [showMatchModal, setShowMatchModal] = useState(false);
  const [validationCarrier, setValidationCarrier] = useState(null);
  
  // Rate limiting state
  const [rateLimitCountdown, setRateLimitCountdown] = useState(0);
  const [rateLimitRetryAttempt, setRateLimitRetryAttempt] = useState(0);
  
  // Tracking state
  const [trackingData, setTrackingData] = useState(null);
  const [trackingLoading, setTrackingLoading] = useState(false);
  const [trackingError, setTrackingError] = useState(null);
  const [showTrackingDetails, setShowTrackingDetails] = useState(false);
  
  // Packing recommendation state
  const [packingRecommendation, setPackingRecommendation] = useState(null);
  const [packingLoading, setPackingLoading] = useState(false);
  const [packingError, setPackingError] = useState(null);

  // Define getStatusDisplay BEFORE using it
  const getStatusDisplay = (order) => {
    // If we have a tracking status code, use it
    if (order.tracking_status && UPS_STATUS_CODES[order.tracking_status]) {
      const statusInfo = UPS_STATUS_CODES[order.tracking_status];
      return {
        icon: statusInfo.icon,
        label: statusInfo.label,
        category: statusInfo.category
      };
    }

    const genericStatus = getGenericStatusFromCode(order.tracking_status);
    if (genericStatus) {
      return genericStatus;
    }
    
    // Fallback to label_created status
    if (order.label_created) {
      return {
        icon: '✓',
        label: 'Labeled',
        category: 'created'
      };
    }
    
    return {
      icon: '⏳',
      label: 'Pending',
      category: 'pending'
    };
  };

  // Now safe to use getStatusDisplay
  const isLabeled = selectedOrder?.label_created;
  const selectedStatus = selectedOrder ? getStatusDisplay(selectedOrder) : null;
  const labelImageFormat = selectedOrder?.ups_label_image_format || 'PNG';
  const labelImageMime = labelImageFormat.toUpperCase() === 'GIF' ? 'image/gif' : 'image/png';
  const labelDataUrl = selectedOrder?.ups_label_image
    ? `data:${labelImageMime};base64,${selectedOrder.ups_label_image}`
    : null;

  console.log('ShippingDashboard component rendered');

  useEffect(() => {
    fetchOrders();
  }, []);

  useEffect(() => {
    if (!selectedOrder) {
      setEditFields(null);
      return;
    }

    const shipDate = selectedOrder.ship_date
      ? selectedOrder.ship_date.slice(0, 10)
      : '';

    setEditFields({
      ship_date: shipDate,
      reference_number_1: selectedOrder.reference_number_1 || (selectedOrder.label_created ? '' : `${selectedOrder.id}`),
      reference_number_2: selectedOrder.reference_number_2 || '',
      packaging_type: selectedOrder.packaging_type || '',
      contains_hazmat: Boolean(selectedOrder.contains_hazmat),
      contains_live_animals: Boolean(selectedOrder.contains_live_animals),
      contains_perishable: Boolean(selectedOrder.contains_perishable),
      contains_cremated_remains: Boolean(selectedOrder.contains_cremated_remains),
      package_value: selectedOrder.package_value || (selectedOrder.label_created ? '' : '0.00'),
      billing_option: selectedOrder.billing_option || (selectedOrder.label_created ? '' : '03')
    });
    
    // Clear validation state when order changes
    setValidationError(null);
    setValidationSuccess(false);
    setValidatedAddress(null);
    setMultipleMatches(null);
    setShowMatchModal(false);
    setRateLimitCountdown(0);
    setValidationCarrier(null);
    setActionError(null);
    
    // If order is labeled and we don't have tracking status yet, fetch it
    if (selectedOrder.label_created && selectedOrder.tracking_number && !selectedOrder.tracking_status) {
      console.log(`Fetching tracking status for order ${selectedOrder.id}`);
      apiFetch(`/api/dashboard/track/${selectedOrder.tracking_number}`)
        .then(res => res.json())
        .then(data => {
          if (!data.error && data.statusCode) {
            console.log(`Got tracking status for order ${selectedOrder.id}: ${data.statusCode}`);
            // Update the selected order with tracking status
            setSelectedOrder(prev => ({
              ...prev,
              tracking_status: data.statusCode
            }));
            // Also update it in the orders list
            setOrders(prev => prev.map(order => 
              order.id === selectedOrder.id 
                ? { ...order, tracking_status: data.statusCode }
                : order
            ));
          }
        })
        .catch(err => console.error('Error fetching tracking status:', err));
    }
  }, [selectedOrder?.id]);  // Changed dependency to selectedOrder?.id to avoid infinite loops

  // Rate limit countdown timer
  useEffect(() => {
    if (rateLimitCountdown <= 0) return;
    
    const timer = setTimeout(() => {
      setRateLimitCountdown(rateLimitCountdown - 1);
    }, 1000);
    
    return () => clearTimeout(timer);
  }, [rateLimitCountdown]);

  const fetchOrders = async () => {
    try {
      setListLoading(true);
      setFetchError(null);
      console.log('Fetching orders from /api/dashboard/shipping-labels');
      const response = await apiFetch('/api/dashboard/shipping-labels');
      console.log('Response status:', response.status);
      if (!response.ok) throw new Error(`Failed to fetch orders: ${response.status} ${response.statusText}`);
      const data = await response.json();
      console.log('Orders fetched successfully:', data);
      const normalizedOrders = (data.orders || []).map((order) => {
        const delivery = order.delivery_address || {};
        const shipping = order.shipping_details || {};
        const packaging = order.packaging || {};
        const dimensions = order.model_dimensions || {};
        const shippingCost = shipping.shipping_cost_cents != null
          ? (shipping.shipping_cost_cents / 100).toFixed(2)
          : '0.00';
        const weightValue = shipping.shipping_weight_g ?? shipping.weight_g;
        const totalWeight = weightValue != null ? Number(weightValue).toFixed(2) : null;
        const packageValueCents = order.package_value_cents ?? order.total_cost_cents;
        return {
          id: order.id,
          order_number: order.order_number,
          ship_date: order.ship_date,
          reference_number_1: order.reference_number_1,
          reference_number_2: order.reference_number_2,
          label_status: order.label_status,
          label_created_at: order.label_created_at,
          label_created: ['created', 'printed', 'shipped'].includes(order.label_status),
          tracking_number: order.ups_tracking_number || order.tracking_number,
          tracking_status: order.tracking_status,  // Will be fetched on demand when order is selected
          ups_tracking_number: order.ups_tracking_number,
          ups_shipment_id: order.ups_shipment_id,
          ups_label_image: order.ups_label_image,
          ups_label_image_format: order.ups_label_image_format,
          first_name: delivery.first_name || '',
          middle_initial: delivery.middle_initial || '',
          last_name: delivery.last_name || '',
          company: delivery.company || '',
          street_address: delivery.street || '',
          apt_suite: delivery.apt_suite || '',
          city: delivery.city || '',
          state: delivery.state || '',
          zip_code: delivery.zip || '',
          email: delivery.email || order.customer_email || '',
          phone: delivery.phone || '',
          contains_hazmat: Boolean(packaging.contains_hazmat),
          contains_live_animals: Boolean(packaging.contains_live_animals),
          contains_perishable: Boolean(packaging.contains_perishable),
          contains_cremated_remains: Boolean(packaging.contains_cremated_remains),
          packaging_type: packaging.type || '',
          package_value: packageValueCents ? (packageValueCents / 100).toFixed(2) : '0.00',
          total_weight: totalWeight,
          shipping_cost: shippingCost,
          shipping_zone: shipping.shipping_zone ? `Zone ${shipping.shipping_zone}` : 'N/A',
          quantity: shipping.quantity || 1,
          shipping_service: order.selected_service || 'UPS Ground',
          model_length_mm: dimensions.length_mm,
          model_width_mm: dimensions.width_mm,
          model_height_mm: dimensions.height_mm,
        };
      });
      setOrders(normalizedOrders);
      setActionError(null);
      if (normalizedOrders.length > 0) {
        setSelectedOrder(normalizedOrders[0]);
      }
    } catch (err) {
      console.error('Error fetching orders:', err);
      setFetchError(err.message);
    } finally {
      setListLoading(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  const validateAddressWithBackoff = async (carrier = 'USPS', retryAttempt = 0) => {
    if (!selectedOrder || !editFields) return;

    const maxRetries = 3;
    const backoffDelays = [2000, 5000, 10000]; // milliseconds for exponential backoff

    setValidationLoading(true);
    setValidationError(null);
    setValidationSuccess(false);
    setValidatedAddress(null);
    setMultipleMatches(null);
    setValidationCarrier(carrier);

    try {
      const addressPayload = {
        streetAddress: selectedOrder.street_address,
        secondaryAddress: selectedOrder.apt_suite || undefined,
        city: selectedOrder.city,
        state: selectedOrder.state,
        zipCode: selectedOrder.zip_code,
      };

      const endpoint = carrier === 'UPS' ? '/api/validate-address-ups' : '/api/validate-address';
      const response = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(addressPayload),
      });

      const result = await response.json();

      if (result.error && result.code === 'RATE_LIMITED') {
        // Handle rate limiting with exponential backoff
        const retryAfter = result.retry_after_seconds || 30;
        
        if (retryAttempt < maxRetries) {
          const waitTime = Math.max(retryAfter * 1000, backoffDelays[retryAttempt] || 10000);
          setRateLimitCountdown(Math.ceil(waitTime / 1000));
          setValidationError(
            `Rate limited by ${carrier} API. Retrying in ${Math.ceil(waitTime / 1000)} seconds (attempt ${retryAttempt + 1}/${maxRetries})...`
          );

          // Auto-retry after backoff
          await new Promise(resolve => setTimeout(resolve, waitTime));
          setRateLimitRetryAttempt(retryAttempt + 1);
          await validateAddressWithBackoff(carrier, retryAttempt + 1);
          return;
        } else {
          setValidationError(`Rate limited after ${maxRetries} retry attempts. Please try again later.`);
          setRateLimitCountdown(0);
          setValidationLoading(false);
          return;
        }
      }

      if (result.error) {
        setValidationError(result.message || 'Address validation failed');
        setValidationLoading(false);
        return;
      }

      // Success
      const validatedAddr = result.address || {};
      setValidatedAddress(validatedAddr);
      setValidationSuccess(true);
      setRateLimitRetryAttempt(0);

      // Check if there are multiple address matches
      if (result.hasMultipleMatches && result.matches && result.matches.length > 0) {
        setMultipleMatches(result.matches);
        setShowMatchModal(true);
      }

      // Show success message
      if (result.corrections && result.corrections.length === 0) {
        setValidationError(null);
      }
    } catch (err) {
      setValidationError(`Error validating address: ${err.message}`);
    } finally {
      setValidationLoading(false);
    }
  };

  const applyValidatedAddress = (addressData = null) => {
    const addr = addressData || validatedAddress;
    if (!addr) return;

    setEditFields(prev => ({
      ...prev,
      street_address: addr.streetAddress || addr.street || prev.street_address,
      apt_suite: addr.secondaryAddress || prev.apt_suite,
      city: addr.city || prev.city,
      state: addr.state || prev.state,
      zip_code: addr.ZIPCode || addr.zip || prev.zip_code,
    }));

    // Update the order display
    if (selectedOrder) {
      setSelectedOrder(prev => ({
        ...prev,
        street_address: addr.streetAddress || addr.street || prev.street_address,
        apt_suite: addr.secondaryAddress || prev.apt_suite,
        city: addr.city || prev.city,
        state: addr.state || prev.state,
        zip_code: addr.ZIPCode || addr.zip || prev.zip_code,
      }));
    }

    setShowMatchModal(false);
    setValidationSuccess(true);
  };

  const updateLabelStatus = async (orderId, trackingNumber) => {
    try {
      const response = await apiFetch(`/api/dashboard/shipping-labels/${orderId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label_status: 'created',
          usps_tracking_number: trackingNumber || null,
          label_created_at: new Date().toISOString()
        })
      });
      if (!response.ok) throw new Error('Failed to update label');
      alert('Label status updated!');
      setActionError(null);
      fetchOrders();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const createUPSLabel = async (orderId) => {
    try {
      setActionLoading(true);
      setActionError(null);
      const response = await apiFetch(`/api/dashboard/shipping-labels/${orderId}/create-label-ups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        // 409 = Conflict (label already scanned by carrier, cannot regenerate)
        if (response.status === 409) {
          setActionError(`⚠️ Cannot regenerate: ${errorData.detail || 'Label already scanned by UPS. Contact support if voiding is needed.'}`);
        } else {
          setActionError(`Failed to create label: ${errorData.detail || response.statusText}`);
        }
        return;
      }
      
      const result = await response.json();
      
      if (result.error) {
        setActionError(`Failed to create label: ${result.message}`);
        return;
      }
      
      alert(`Label created successfully!\nTracking: ${result.tracking_number}`);
      setActionError(null);
      fetchOrders();
    } catch (err) {
      setActionError(`Error creating label: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const updateShippingDetails = async () => {
    if (!selectedOrder || !editFields) return;

    try {
      const packageValueCents = editFields.package_value
        ? Math.round(parseFloat(editFields.package_value) * 100)
        : null;

      const response = await apiFetch(`/api/dashboard/shipping-labels/${selectedOrder.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ship_date: editFields.ship_date || null,
          reference_number_1: editFields.reference_number_1 || null,
          reference_number_2: editFields.reference_number_2 || null,
          packaging_type: editFields.packaging_type || null,
          contains_hazmat: editFields.contains_hazmat,
          contains_live_animals: editFields.contains_live_animals,
          contains_perishable: editFields.contains_perishable,
          contains_cremated_remains: editFields.contains_cremated_remains,
          package_value_cents: Number.isNaN(packageValueCents) ? null : packageValueCents,
          billing_option: editFields.billing_option || '03'
        })
      });

      if (!response.ok) throw new Error('Failed to update shipping details');
      alert('Shipping details updated!');
      setActionError(null);
      fetchOrders();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const trackShipment = async () => {
    if (!selectedOrder || !selectedOrder.tracking_number) {
      setTrackingError('No tracking number available');
      return;
    }

    try {
      setTrackingLoading(true);
      setTrackingError(null);
      setTrackingData(null);

      const response = await apiFetch(`/api/dashboard/track/${selectedOrder.tracking_number}`);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to track shipment: ${response.status}`);
      }

      const data = await response.json();
      if (data.error) {
        throw new Error(data.message || 'Failed to track shipment');
      }

      setTrackingData(data);
      setShowTrackingDetails(true);
    } catch (err) {
      setTrackingError(err.message);
      console.error('Tracking error:', err);
    } finally {
      setTrackingLoading(false);
    }
  };

  const calculateDaysInRetentionPeriod = () => {
    if (!selectedOrder?.label_created_at) return 0;
    const labelDate = new Date(selectedOrder.label_created_at);
    const now = new Date();
    const daysDiff = Math.floor((now - labelDate) / (1000 * 60 * 60 * 24));
    return daysDiff;
  };

  const isTrackingDataExpired = () => {
    const daysInPeriod = calculateDaysInRetentionPeriod();
    return daysInPeriod > 120;
  };

  const formatTrackingDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return 'N/A';
      return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return 'N/A';
    }
  };

  const getPackingRecommendation = async () => {
    if (!selectedOrder) {
      setPackingError('No order selected');
      return;
    }

    try {
      setPackingLoading(true);
      setPackingError(null);
      setPackingRecommendation(null);

      const response = await apiFetch('/api/packing-recommendation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_length_mm: selectedOrder.model_length_mm,
          model_width_mm: selectedOrder.model_width_mm,
          model_height_mm: selectedOrder.model_height_mm,
          quantity: selectedOrder.quantity || 1,
          weight_g: selectedOrder.total_weight ? Number(selectedOrder.total_weight) : 0,
          shipping_method: selectedOrder.shipping_service || 'UPS Ground'
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to get packing recommendation: ${response.status}`);
      }

      const data = await response.json();
      setPackingRecommendation(data);
    } catch (err) {
      setPackingError(err.message);
      console.error('Packing recommendation error:', err);
    } finally {
      setPackingLoading(false);
    }
  };

  if (listLoading && orders.length === 0) return <div className="dashboard-container"><GlobalHeader showBackButton={true} /><div className="dashboard-content"><p>Loading orders...</p></div></div>;
  if (fetchError && orders.length === 0) return <div className="dashboard-container"><GlobalHeader showBackButton={true} /><div className="dashboard-content"><p className="error">Error: {fetchError}</p></div></div>;
  if (orders.length === 0) return <div className="dashboard-container"><GlobalHeader showBackButton={true} /><div className="dashboard-content"><p className="no-orders">No pending orders</p></div></div>;

  return (
    <div className="dashboard-container">
      <GlobalHeader showBackButton={true} />
      <div className="dashboard-layout">
        {/* Left Panel: Order List */}
        <div className="order-list-panel">
          <div className="order-list-header">
            <h2>Pending Orders</h2>
            <button onClick={fetchOrders} className="refresh-btn-small">⟳</button>
          </div>
          <div className="orders-scroll">
            {orders.filter(order => !order.label_created).map((order) => (
              <div
                key={order.id}
                className={`order-item ${selectedOrder?.id === order.id ? 'active' : ''}`}
                onClick={() => setSelectedOrder(order)}
              >
                <div className="order-item-header">Order #{order.id}</div>
                <div className="order-item-details">
                  <span>{order.city}, {order.state}</span>
                  {(() => {
                    const status = getStatusDisplay(order);
                    return (
                      <span className={`status ${status.category}`}>
                        {status.icon} {status.label}
                      </span>
                    );
                  })()}
                </div>
              </div>
            ))}
          </div>
          <div className="order-list-header">
            <h2>Labeled Orders</h2>
            <button onClick={fetchOrders} className="refresh-btn-small">⟳</button>
          </div>
          <div className="orders-scroll">
            {orders.filter(order => order.label_created).map((order) => (
              <div
                key={order.id}
                className={`order-item ${selectedOrder?.id === order.id ? 'active' : ''}`}
                onClick={() => setSelectedOrder(order)}
              >
                <div className="order-item-header">Order #{order.id}</div>
                <div className="order-item-details">
                  <span>{order.city}, {order.state}</span>
                  {(() => {
                    const status = getStatusDisplay(order);
                    return (
                      <span className={`status ${status.category}`}>
                        {status.icon} {status.label}
                      </span>
                    );
                  })()}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel: Order Details */}
        {selectedOrder && (
          <div className="order-details-panel">
            {actionError && (
              <div className="validation-error-banner">
                {actionError}
              </div>
            )}
            <div className="section shipping-info">
              <h2>1. Shipping Information</h2>
              
              {/* Address Validation Section */}
              {validationSuccess && validationCarrier && (
                <div className="validation-success-banner">
                  ✓ Address validated and standardized by {validationCarrier}
                </div>
              )}
              
              {validationError && (
                <div className="validation-error-banner">
                  {validationError}
                </div>
              )}
              
              {showMatchModal && multipleMatches && (
                <div className="modal-overlay">
                  <div className="modal-content">
                    <h3>Multiple Address Matches Found</h3>
                    <p>The address matched multiple possibilities. Please select the correct one:</p>
                    <div className="matches-list">
                      {multipleMatches.map((match, idx) => (
                        <div key={idx} className="match-option">
                          <input
                            type="radio"
                            id={`match-${idx}`}
                            name="address-match"
                            onChange={() => applyValidatedAddress(match.address || match)}
                          />
                          <label htmlFor={`match-${idx}`}>
                            {match.address?.streetAddress || match.streetAddress} {match.address?.city || match.city}, {match.address?.state || match.state} {match.address?.ZIPCode || match.ZIPCode}
                          </label>
                        </div>
                      ))}
                    </div>
                    <div className="modal-buttons">
                      <button onClick={() => setShowMatchModal(false)} className="cancel-btn">Cancel</button>
                      <button onClick={() => applyValidatedAddress()} className="confirm-btn">Apply Selected Address</button>
                    </div>
                  </div>
                </div>
              )}
              
              <div className="info-grid">
                <div className="info-field">
                  <label>Ship Date</label>
                  <div className="field-value">
                    {isLabeled ? (
                      <span>{selectedOrder.ship_date ? selectedOrder.ship_date.slice(0, 10) : 'N/A'}</span>
                    ) : (
                      <input
                        type="date"
                        value={editFields?.ship_date || ''}
                        onChange={(e) => setEditFields(prev => ({ ...prev, ship_date: e.target.value }))}
                        className="tracking-input"
                      />
                    )}
                  </div>
                </div>

                {!isLabeled && (
                  <div className="info-field full-width">
                    <label>Validate Address</label>
                    <div className="field-value validation-buttons">
                      <button
                        onClick={() => validateAddressWithBackoff('USPS')}
                        disabled={validationLoading || rateLimitCountdown > 0}
                        className={`validate-address-btn usps-btn ${validationLoading && validationCarrier === 'USPS' ? 'loading' : ''} ${rateLimitCountdown > 0 && validationCarrier === 'USPS' ? 'disabled' : ''}`}
                      >
                        {validationLoading && validationCarrier === 'USPS' ? '⟳ Validating...' : rateLimitCountdown > 0 && validationCarrier === 'USPS' ? `⏳ Retry in ${rateLimitCountdown}s` : '✓ USPS'}
                      </button>
                      <button
                        onClick={() => validateAddressWithBackoff('UPS')}
                        disabled={validationLoading || rateLimitCountdown > 0}
                        className={`validate-address-btn ups-btn ${validationLoading && validationCarrier === 'UPS' ? 'loading' : ''} ${rateLimitCountdown > 0 && validationCarrier === 'UPS' ? 'disabled' : ''}`}
                      >
                        {validationLoading && validationCarrier === 'UPS' ? '⟳ Validating...' : rateLimitCountdown > 0 && validationCarrier === 'UPS' ? `⏳ Retry in ${rateLimitCountdown}s` : '✓ UPS'}
                      </button>
                    </div>
                  </div>
                )}

                <div className="info-field full-width">
                  <label>Ship To - First Name</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.first_name}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.first_name)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field">
                  <label>MI</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.middle_initial || '-'}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.middle_initial || '')} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field">
                  <label>Last Name</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.last_name}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.last_name)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Company</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.company || '(none)'}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.company || '')} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Street Address</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.street_address}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.street_address)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Apt/Suite/Other</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.apt_suite || '(none)'}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.apt_suite || '')} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field">
                  <label>City</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.city}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.city)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field">
                  <label>State</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.state}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.state)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field">
                  <label>ZIP Code</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.zip_code}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.zip_code)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Email</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.email}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.email)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Phone Number</label>
                  <div className="field-value-with-copy">
                    <div className="field-value">{selectedOrder.phone}</div>
                    <button onClick={() => copyToClipboard(selectedOrder.phone)} className="copy-btn">📋</button>
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Reference Number / Note 1</label>
                  <div className="field-value">
                    {isLabeled ? (
                      <span>{selectedOrder.reference_number_1 || '(none)'}</span>
                    ) : (
                      <input
                        type="text"
                        value={editFields?.reference_number_1 || ''}
                        onChange={(e) => setEditFields(prev => ({ ...prev, reference_number_1: e.target.value }))}
                        className="tracking-input"
                      />
                    )}
                  </div>
                </div>

                <div className="info-field full-width">
                  <label>Reference Number / Note 2</label>
                  <div className="field-value">
                    {isLabeled ? (
                      <span>{selectedOrder.reference_number_2 || '(none)'}</span>
                    ) : (
                      <input
                        type="text"
                        value={editFields?.reference_number_2 || ''}
                        onChange={(e) => setEditFields(prev => ({ ...prev, reference_number_2: e.target.value }))}
                        className="tracking-input"
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="section content-packaging">
              <h2>2. Content & Packaging Information</h2>
              <div className="info-grid">
                <div className="info-field full-width">
                  <label>Contents</label>
                  <div className="flags">
                    <label className="flag">
                      <input
                        type="checkbox"
                        checked={editFields?.contains_hazmat || false}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, contains_hazmat: e.target.checked }))}
                      />
                      ⚠️ Hazardous Material
                    </label>
                    <label className="flag">
                      <input
                        type="checkbox"
                        checked={editFields?.contains_live_animals || false}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, contains_live_animals: e.target.checked }))}
                      />
                      🐾 Live Animals
                    </label>
                    <label className="flag">
                      <input
                        type="checkbox"
                        checked={editFields?.contains_perishable || false}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, contains_perishable: e.target.checked }))}
                      />
                      ❄️ Perishable Goods
                    </label>
                    <label className="flag">
                      <input
                        type="checkbox"
                        checked={editFields?.contains_cremated_remains || false}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, contains_cremated_remains: e.target.checked }))}
                      />
                      ⚱️ Cremated Remains
                    </label>
                  </div>
                </div>

                <div className="info-field">
                  <label>Packaging Type</label>
                  <div className="field-value">
                    {isLabeled ? (
                      <span>{selectedOrder.packaging_type || '(none)'}</span>
                    ) : (
                      <input
                        type="text"
                        value={editFields?.packaging_type || ''}
                        onChange={(e) => setEditFields(prev => ({ ...prev, packaging_type: e.target.value }))}
                        className="tracking-input"
                      />
                    )}
                  </div>
                </div>

                <div className="info-field">
                  <label>Package Value</label>
                  <div className="field-value">
                    {isLabeled ? (
                      <span>{selectedOrder.package_value || '0.00'}</span>
                    ) : (
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={editFields?.package_value || ''}
                        onChange={(e) => setEditFields(prev => ({ ...prev, package_value: e.target.value }))}
                        className="tracking-input"
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="section billing-options">
              <h2>3. Billing Options</h2>
              <div className="info-grid">
                <div className="info-field full-width">
                  <label>Who pays for shipping?</label>
                  <div className="flags">
                    <label className="flag">
                      <input
                        type="radio"
                        name="billing-option"
                        value="01"
                        checked={editFields?.billing_option === '01'}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, billing_option: e.target.value }))}
                      />
                      💳 Bill to Shipper (Prepaid)
                    </label>
                    <label className="flag">
                      <input
                        type="radio"
                        name="billing-option"
                        value="02"
                        checked={editFields?.billing_option === '02'}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, billing_option: e.target.value }))}
                      />
                      📦 Bill to Receiver (COD)
                    </label>
                    <label className="flag">
                      <input
                        type="radio"
                        name="billing-option"
                        value="03"
                        checked={editFields?.billing_option === '03'}
                        disabled={isLabeled}
                        onChange={(e) => setEditFields(prev => ({ ...prev, billing_option: e.target.value }))}
                      />
                      🏢 Bill to Third Party
                    </label>
                  </div>
                </div>
                {!isLabeled && (
                  <div className="info-field full-width">
                    <button onClick={updateShippingDetails} className="mark-labeled-btn">
                      Save Shipping Details
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="section shipping-options">
              <h2>4. Shipping Options</h2>
              <div className="info-grid">
                <div className="info-field">
                  <label>Weight</label>
                  <div className="field-value">{selectedOrder.total_weight || 'N/A'} g</div>
                </div>

                <div className="info-field">
                  <label>Shipping Cost</label>
                  <div className="field-value">${selectedOrder.shipping_cost || '0.00'}</div>
                </div>

                <div className="info-field">
                  <label>USPS Shipping Zone</label>
                  <div className="field-value">{selectedOrder.shipping_zone || 'N/A'}</div>
                </div>
              </div>
            </div>

            <div className="section packing-optimization">
              <h2>5. Packing & Box Optimization</h2>
              <p className="section-description">Get AI-powered packing recommendations based on model dimensions, quantity, and shipping method to optimize costs and ensure safe delivery.</p>
              
              {packingError && (
                <div className="validation-error-banner">
                  {packingError}
                </div>
              )}

              {!packingRecommendation ? (
                <div className="packing-action">
                  <button 
                    onClick={getPackingRecommendation} 
                    disabled={packingLoading}
                    className="packing-recommendation-btn"
                  >
                    {packingLoading ? '⟳ Calculating...' : '📦 Get Packing Recommendation'}
                  </button>
                </div>
              ) : (
                <div className="packing-result">
                  <div className="packing-header">
                    <h3>📦 {packingRecommendation.strategy}</h3>
                    <button 
                      onClick={() => setPackingRecommendation(null)}
                      className="close-packing-btn"
                    >
                      ✕
                    </button>
                  </div>

                  <div className="packing-recommendation-text">
                    <p>{packingRecommendation.recommendation}</p>
                  </div>

                  <div className="packing-details">
                    <div className="packing-detail-item">
                      <label>Estimated Package Dimensions</label>
                      <div className="detail-value">
                        {packingRecommendation.estimated_package_dimensions.length_inches > 0
                          ? `${packingRecommendation.estimated_package_dimensions.length_inches.toFixed(1)}" × ${packingRecommendation.estimated_package_dimensions.width_inches.toFixed(1)}" × ${packingRecommendation.estimated_package_dimensions.height_inches.toFixed(1)}"`
                          : 'Dimensions not available'}
                      </div>
                    </div>

                    <div className="packing-detail-item">
                      <label>Number of Packages</label>
                      <div className="detail-value">{packingRecommendation.number_of_packages}</div>
                    </div>

                    <div className="packing-detail-item">
                      <label>Estimated Total Weight</label>
                      <div className="detail-value">{packingRecommendation.estimated_total_weight_lbs.toFixed(2)} lbs</div>
                    </div>
                  </div>

                  {packingRecommendation.notes && packingRecommendation.notes.length > 0 && (
                    <div className="packing-notes">
                      <h4>📌 Important Notes:</h4>
                      <ul>
                        {packingRecommendation.notes.map((note, idx) => (
                          <li key={idx}>{note}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="packing-action">
                    <button 
                      onClick={getPackingRecommendation} 
                      disabled={packingLoading}
                      className="packing-recommendation-btn secondary"
                    >
                      {packingLoading ? '⟳ Recalculating...' : '🔄 Recalculate'}
                    </button>
                  </div>
                </div>
              )}
            </div>
            
            {/* Label Action Buttons - Safety Aware */}
            {!isLabeled && (
              <div className="label-action">
                <button
                  onClick={() => createUPSLabel(selectedOrder.id)}
                  className="mark-labeled-btn"
                  disabled={actionLoading}
                >
                  {actionLoading ? '⟳ Creating Label...' : '✅ Create Label'}
                </button>
              </div>
            )}

            {/* Once labeled: show re-download button */}
            {isLabeled && !selectedOrder?.first_carrier_scan_at && (
              <div className="label-action label-controls">
                <button
                  onClick={() => {
                    // Re-download (show existing label)
                    if (selectedOrder?.ups_label_image) {
                      const labelDataUrl = `data:image/${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'};base64,${selectedOrder.ups_label_image}`;
                      const link = document.createElement('a');
                      link.href = labelDataUrl;
                      link.download = `label-${selectedOrder.ups_tracking_number}.${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'}`;
                      link.click();
                    }
                  }}
                  className="re-download-btn secondary"
                >
                  📥 Re-download Label
                </button>
                <button
                  onClick={() => createUPSLabel(selectedOrder.id)}
                  className="void-regenerate-btn warning"
                  disabled={actionLoading}
                  title="Invalidate the previous label and create a new tracking number"
                >
                  {actionLoading ? '⟳ Regenerating...' : '⚠️ Void & Regenerate'}
                </button>
              </div>
            )}

            {/* After carrier scan: locked state */}
            {isLabeled && selectedOrder?.first_carrier_scan_at && (
              <div className="label-action">
                <div className="locked-shipment-notice">
                  <strong>🔒 Shipment Locked</strong>
                  <p>UPS has already scanned this package. Label regeneration is no longer allowed.</p>
                  <p className="scan-timestamp">Scanned: {new Date(selectedOrder.first_carrier_scan_at).toLocaleString()}</p>
                  <button
                    onClick={() => {
                      // Re-download only
                      if (selectedOrder?.ups_label_image) {
                        const labelDataUrl = `data:image/${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'};base64,${selectedOrder.ups_label_image}`;
                        const link = document.createElement('a');
                        link.href = labelDataUrl;
                        link.download = `label-${selectedOrder.ups_tracking_number}.${selectedOrder.ups_label_image_format?.toLowerCase() === 'gif' ? 'gif' : 'png'}`;
                        link.click();
                      }
                    }}
                    className="re-download-btn secondary"
                  >
                    📥 Re-download Label
                  </button>
                </div>
              </div>
            )}

              {/* Legacy USPS label marking (for backwards compatibility) */}
              {/* <div className="label-action">
                <input
                  type="text"
                  placeholder="USPS Tracking Number"
                  id={`tracking-${selectedOrder.id}`}
                  className="tracking-input"
                />
                <button
                  onClick={() => {
                    const trackingNum = document.getElementById(`tracking-${selectedOrder.id}`).value;
                    updateLabelStatus(selectedOrder.id, trackingNum);
                  }}
                  className="mark-labeled-btn"
                >
                  ✓ Mark as Labeled (USPS)
                </button>
              </div>
            </div> */}

            {isLabeled && (
              <div className="section shipment-details">
                <h2>5. Shipment Details</h2>
                
                {/* 120-Day Retention Period Warning Banner */}
                {isTrackingDataExpired() && (
                  <div className="warning-banner retention-expired">
                    <span>⚠️</span>
                    <div>
                      <strong>Tracking Data Expired</strong>
                      <p>UPS retains tracking data for 120 days from label creation. This shipment's tracking data is no longer available.</p>
                    </div>
                  </div>
                )}
                
                {/* Retention Period Warning Banner */}
                {!isTrackingDataExpired() && calculateDaysInRetentionPeriod() > 100 && (
                  <div className="warning-banner retention-warning">
                    <span>ℹ️</span>
                    <div>
                      <strong>Tracking Data Expiring Soon</strong>
                      <p>UPS retains tracking data for 120 days from label creation. {120 - calculateDaysInRetentionPeriod()} days remaining.</p>
                    </div>
                  </div>
                )}
                
                <div className="info-grid">
                  <div className="info-field">
                    <label>Tracking Number</label>
                    <div className="field-value">{selectedOrder.tracking_number || 'N/A'}</div>
                  </div>

                  <div className="info-field">
                    <label>Shipment ID</label>
                    <div className="field-value">{selectedOrder.ups_shipment_id || 'N/A'}</div>
                  </div>

                  <div className="info-field">
                    <label>Label Status</label>
                    <div className="field-value">{selectedOrder.label_status || 'N/A'}</div>
                  </div>

                  <div className="info-field">
                    <label>Label Created At</label>
                    <div className="field-value">
                      {selectedOrder.label_created_at
                        ? new Date(selectedOrder.label_created_at).toLocaleString()
                        : 'N/A'}
                    </div>
                  </div>

                  <div className="info-field">
                    <label>Shipment Status</label>
                    <div className="field-value">
                      {selectedStatus ? `${selectedStatus.icon} ${selectedStatus.label}` : 'N/A'}
                    </div>
                  </div>

                  <div className="info-field full-width">
                    <label>Label</label>
                    <div className="field-value">
                      {labelDataUrl ? (
                        <iframe
                          src={labelDataUrl}
                          style={{ width: '100%', height: '600px', border: '1px solid #ccc', borderRadius: '4px' }}
                          title={`ups-label-${selectedOrder.id}`}
                        />
                      ) : (
                        'Not stored'
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Track Shipment Button */}
                {!isTrackingDataExpired() && selectedOrder.tracking_number && (
                  <div className="tracking-section">
                    <button
                      onClick={trackShipment}
                      disabled={trackingLoading}
                      className="track-shipment-btn"
                    >
                      {trackingLoading ? '⟳ Fetching Tracking...' : '📍 Track Shipment'}
                    </button>
                    
                    {trackingError && (
                      <div className="error-message tracking-error">
                        <strong>⚠️ Tracking Error:</strong> {trackingError}
                      </div>
                    )}
                    
                    {showTrackingDetails && trackingData && !trackingData.error && (
                      <div className="tracking-details">
                        <h3>Tracking Information</h3>
                        
                        <div className="tracking-status">
                          <div className="status-badge">
                            <strong>Current Status:</strong>
                            <span className="status-code">{trackingData.statusCode}</span>
                            <span className="status-description">{trackingData.statusDescription}</span>
                          </div>
                        </div>
                        
                        {trackingData.currentLocation && (
                          <div className="location-info">
                            <strong>📍 Current Location:</strong>
                            <div>
                              {trackingData.currentLocation.city && trackingData.currentLocation.state
                                ? `${trackingData.currentLocation.city}, ${trackingData.currentLocation.state} ${trackingData.currentLocation.zip || ''}`
                                : 'Location not available'}
                            </div>
                          </div>
                        )}
                        
                        {trackingData.deliveryDate && (
                          <div className="delivery-date">
                            <strong>📦 Expected Delivery:</strong>
                            <div>{formatTrackingDate(trackingData.deliveryDate)}</div>
                          </div>
                        )}
                        
                        {trackingData.activities && trackingData.activities.length > 0 && (
                          <div className="activity-timeline">
                            <strong>📋 Activity History:</strong>
                            <div className="timeline">
                              {trackingData.activities.map((activity, index) => (
                                <div key={index} className="timeline-item">
                                  <div className="timeline-date">
                                    {formatTrackingDate(activity.date)}
                                  </div>
                                  <div className="timeline-content">
                                    <div className="timeline-status">{activity.status}</div>
                                    {activity.location && activity.location.city && (
                                      <div className="timeline-location">
                                        {activity.location.city}{activity.location.state ? ', ' + activity.location.state : ''} {activity.location.zip || ''}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ShippingDashboard;
