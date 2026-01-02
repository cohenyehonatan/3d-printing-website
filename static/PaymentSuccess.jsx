import React, { useEffect, useState } from 'react';
import { CheckCircle, Download, Home } from 'lucide-react';

const PaymentSuccess = ({ bookingId, customerId }) => {
  const [orderDetails, setOrderDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Fetch order details if IDs are provided
    if (bookingId && customerId) {
      fetchOrderDetails();
    } else {
      setLoading(false);
    }
  }, [bookingId, customerId]);

  const fetchOrderDetails = async () => {
    try {
      const response = await fetch(`/api/order-details?booking_id=${bookingId}&customer_id=${customerId}`);
      if (response.ok) {
        const data = await response.json();
        setOrderDetails(data);
      }
    } catch (err) {
      console.error('Failed to fetch order details:', err);
      // Don't set error state - still show success page even if we can't fetch details
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <CheckCircle className="w-8 h-8 text-green-600" />
              <h1 className="text-2xl font-bold text-gray-900">Payment Successful</h1>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-2xl mx-auto px-4 py-12 sm:px-6 lg:px-8">
        <div className="bg-white rounded-lg shadow-lg p-8">
          {/* Success Icon */}
          <div className="text-center mb-8">
            <div className="inline-block">
              <CheckCircle className="w-20 h-20 text-green-600 mx-auto" />
            </div>
            <h2 className="text-3xl font-bold text-gray-900 mt-4">Order Confirmed!</h2>
            <p className="text-gray-600 mt-2">Your payment has been processed successfully.</p>
          </div>

          {/* Order Details */}
          {!loading && (orderDetails || (bookingId && customerId)) && (
            <div className="bg-gray-50 rounded-lg p-6 mb-8">
              <h3 className="font-semibold text-lg text-gray-900 mb-4">Order Details</h3>
              
              {orderDetails && (
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Order Number:</span>
                    <span className="font-medium">{orderDetails.booking_id}</span>
                  </div>
                  {orderDetails.order_date && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Order Date:</span>
                      <span className="font-medium">{new Date(orderDetails.order_date).toLocaleDateString()}</span>
                    </div>
                  )}
                  {orderDetails.estimated_delivery && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Estimated Delivery:</span>
                      <span className="font-medium">{new Date(orderDetails.estimated_delivery).toLocaleDateString()}</span>
                    </div>
                  )}
                  {orderDetails.total_amount && (
                    <div className="flex justify-between border-t pt-3">
                      <span className="text-gray-600">Total Paid:</span>
                      <span className="font-bold text-green-600">{orderDetails.total_amount}</span>
                    </div>
                  )}
                </div>
              )}

              {!orderDetails && bookingId && customerId && (
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Booking ID:</span>
                    <span className="font-medium">{bookingId}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Customer ID:</span>
                    <span className="font-medium">{customerId}</span>
                  </div>
                  <p className="text-gray-600 text-xs mt-4">
                    You will receive a confirmation email shortly with your order details and tracking information.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Next Steps */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
            <h3 className="font-semibold text-gray-900 mb-3">What's Next?</h3>
            <ul className="space-y-2 text-sm text-gray-700">
              <li className="flex items-start">
                <span className="text-blue-600 mr-3 font-bold">1.</span>
                <span>Check your email for an order confirmation and receipt</span>
              </li>
              <li className="flex items-start">
                <span className="text-blue-600 mr-3 font-bold">2.</span>
                <span>We'll start printing your order immediately</span>
              </li>
              <li className="flex items-start">
                <span className="text-blue-600 mr-3 font-bold">3.</span>
                <span>You'll receive tracking information when your package ships</span>
              </li>
              <li className="flex items-start">
                <span className="text-blue-600 mr-3 font-bold">4.</span>
                <span>Delivery typically takes 3-5 business days</span>
              </li>
            </ul>
          </div>

          {/* FAQ Section */}
          <div className="mb-8">
            <h3 className="font-semibold text-gray-900 mb-3">Frequently Asked Questions</h3>
            <div className="space-y-3 text-sm">
              <details className="bg-gray-50 rounded p-3 cursor-pointer">
                <summary className="font-medium text-gray-900">Can I modify my order?</summary>
                <p className="text-gray-600 mt-2">
                  Orders begin printing immediately after confirmation. Please contact us within 1 hour if you need to make changes.
                </p>
              </details>
              <details className="bg-gray-50 rounded p-3 cursor-pointer">
                <summary className="font-medium text-gray-900">What if there's an issue with my print?</summary>
                <p className="text-gray-600 mt-2">
                  We stand behind the quality of our prints. If there's any defect, contact us and we'll reprint or refund you.
                </p>
              </details>
              <details className="bg-gray-50 rounded p-3 cursor-pointer">
                <summary className="font-medium text-gray-900">Can I track my order?</summary>
                <p className="text-gray-600 mt-2">
                  Yes! You'll receive a tracking number via email once your order ships. Track it through the carrier's website.
                </p>
              </details>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-4">
            <a
              href="/"
              className="flex-1 flex items-center justify-center px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition"
            >
              <Home className="w-5 h-5 mr-2" />
              Back to Home
            </a>
            <button
              onClick={() => window.print()}
              className="flex-1 flex items-center justify-center px-6 py-3 border-2 border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition"
            >
              <Download className="w-5 h-5 mr-2" />
              Print Receipt
            </button>
          </div>
        </div>

        {/* Contact Info */}
        <div className="text-center mt-8 text-sm text-gray-600">
          <p>Have questions? <a href="mailto:support@print3dpro.com" className="text-indigo-600 hover:underline">Contact our support team</a></p>
        </div>
      </div>
    </div>
  );
};

export default PaymentSuccess;
