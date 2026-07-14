import { makeDoc } from "./_shared";

export default makeDoc({
  slug: "delivery",
  title: "Delivery Policy",
  summary: "This Delivery Policy explains how documents, printed materials, and other eligible services are delivered through the CourtBazaar Platform.",
  version: "1.0",
  effectiveDate: "2026-06-01",
  lastUpdated: "2026-06-01",
  relatedSlugs: ["refund", "confidentiality"],
  sections: [
    {
      id: "scope",
      title: "1. Scope",
      body: [
        { type: "p", text: 'Welcome to CourtBazaar, a brand operated by LexOrbit Technologies ("CourtBazaar", "we", "our", or "us"). This Delivery Policy explains how documents, printed materials, and other eligible services are delivered through the CourtBazaar Platform.' },
        { type: "p", text: "This Delivery Policy applies to all delivery-related services offered through the CourtBazaar Platform, including but not limited to:" },
        { type: "list", items: ["Printing Services", "Photocopying Services", "Document Scanning", "OCR & PDF Bookmarking", "Document Pickup", "Document Delivery", "Legal Document Logistics", "Court Filing Support (where available)", "Other document handling services introduced by CourtBazaar from time to time"] },
      ],
    },
    {
      id: "delivery-areas",
      title: "2. Delivery Areas",
      body: [
        { type: "p", text: "CourtBazaar currently provides services only in locations where delivery partners or authorized service providers are available." },
        { type: "p", text: "Service availability may vary depending on:" },
        { type: "list", items: ["City", "Court Complex", "Locality", "Delivery partner availability", "Weather conditions", "Government restrictions", "Operational constraints"] },
      ],
    },
    {
      id: "delivery-time",
      title: "3. Delivery Time",
      body: [
        { type: "p", text: "Estimated delivery times are displayed during the order process." },
        { type: "p", text: "Delivery timelines may vary depending on:" },
        { type: "list", items: ["Type of service", "Number of pages", "Printing specifications", "Order volume", "Pickup location", "Delivery address", "Vendor processing time", "Court working hours", "Traffic conditions", "Public holidays"] },
        { type: "p", text: "Estimated timelines are indicative only and are not guaranteed unless expressly stated." },
      ],
    },
    {
      id: "same-day-delivery",
      title: "4. Same-Day Delivery",
      body: [
        { type: "p", text: "Where available, eligible orders may qualify for Same-Day Delivery." },
        { type: "p", text: "Availability depends on:" },
        { type: "list", items: ["Order placement time", "Vendor acceptance", "Printing completion", "Delivery partner availability", "Distance from the service provider"] },
        { type: "p", text: "CourtBazaar reserves the right to decline Same-Day Delivery if operationally impractical." },
      ],
    },
    {
      id: "pickup-and-delivery-workflow",
      title: "5. Pickup and Delivery Workflow",
      body: [
        { type: "p", text: "Depending on the selected service:" },
        { type: "list", items: ["Customer places an order.", "Payment is completed (unless another payment option is offered).", "The order is assigned to an authorized vendor.", "Documents are processed.", "Pickup or delivery is arranged.", "The customer receives order updates through the Platform."] },
        { type: "p", text: "Certain services may require OTP verification or other identity confirmation before handover." },
      ],
    },
    {
      id: "delivery-charges",
      title: "6. Delivery Charges",
      body: [
        { type: "p", text: "Delivery charges, if applicable, will be displayed before payment." },
        { type: "p", text: "Charges may depend on:" },
        { type: "list", items: ["Distance", "Delivery location", "Service type", "Order size", "Weight or volume", "Urgent delivery requests"] },
        { type: "p", text: "Delivery charges are generally non-refundable once delivery has commenced, except where required by applicable law or where CourtBazaar determines otherwise." },
      ],
    },
    {
      id: "delivery-attempts",
      title: "7. Delivery Attempts",
      body: [
        { type: "p", text: "If the recipient is unavailable:" },
        { type: "list", items: ["Our delivery partner may attempt redelivery where feasible.", "The customer may be contacted by phone, SMS, email, or through the Platform.", "Additional delivery charges may apply for repeated delivery attempts."] },
        { type: "p", text: "If delivery cannot be completed after reasonable attempts, the order may be returned to the vendor or held for customer collection, subject to operational policies." },
      ],
    },
    {
      id: "customer-responsibilities",
      title: "8. Customer Responsibilities",
      body: [
        { type: "p", text: "Customers are responsible for:" },
        { type: "list", items: ["Providing an accurate delivery address.", "Providing a valid mobile number.", "Ensuring someone is available to receive the delivery where required.", "Reviewing the order details before confirming the order.", "Promptly reporting any delivery issues."] },
        { type: "p", text: "CourtBazaar is not responsible for delays or failures caused by incorrect or incomplete information provided by the customer." },
      ],
    },
    {
      id: "digital-deliveries",
      title: "9. Digital Deliveries",
      body: [
        { type: "p", text: "For digital services such as:" },
        { type: "list", items: ["OCR", "Searchable PDFs", "Bookmarked PDFs", "Scanned documents", "Filing-ready documents"] },
        { type: "p", text: "Delivery may be made through:" },
        { type: "list", items: ["Customer Dashboard", "Secure download link", "Registered email address", "Other secure electronic means made available through the Platform"] },
        { type: "p", text: "Customers are responsible for downloading and securely storing delivered digital files." },
      ],
    },
    {
      id: "order-tracking",
      title: "10. Order Tracking",
      body: [
        { type: "p", text: "Where available, customers may track the status of their orders through the CourtBazaar Platform." },
        { type: "p", text: "Tracking information is provided for convenience and may be subject to delays or technical issues." },
      ],
    },
    {
      id: "delays",
      title: "11. Delays",
      body: [
        { type: "p", text: "Delivery may be delayed due to circumstances beyond our reasonable control, including:" },
        { type: "list", items: ["Extreme weather", "Traffic disruptions", "Public holidays", "Natural disasters", "Technical failures", "Court closures", "Law and order situations", "Government restrictions", "Vendor operational issues", "Force majeure events"] },
        { type: "p", text: "CourtBazaar will make reasonable efforts to keep customers informed of significant delays." },
      ],
    },
    {
      id: "inspection-at-delivery",
      title: "12. Inspection at Delivery",
      body: [
        { type: "p", text: "Customers should inspect physical deliveries upon receipt." },
        { type: "p", text: "Any apparent issues, such as:" },
        { type: "list", items: ["Wrong documents", "Missing pages", "Damaged printouts", "Incorrect quantities"] },
        { type: "p", text: "should be reported to CourtBazaar as soon as reasonably possible." },
      ],
    },
    {
      id: "failed-delivery",
      title: "13. Failed Delivery",
      body: [
        { type: "p", text: "An order may be considered undeliverable if:" },
        { type: "list", items: ["The delivery address is incorrect.", "The recipient cannot be contacted after reasonable attempts.", "Access to the location is denied.", "Delivery is refused without valid reason."] },
        { type: "p", text: "Additional charges may apply for rescheduling or reattempting delivery." },
      ],
    },
    {
      id: "limitation-of-liability",
      title: "14. Limitation of Liability",
      body: [
        { type: "p", text: "CourtBazaar acts as a technology platform connecting customers with authorized service providers and delivery partners." },
        { type: "p", text: "While we strive to facilitate timely and secure delivery, we do not guarantee delivery within any specific timeframe unless expressly agreed." },
        { type: "p", text: "To the maximum extent permitted by applicable law, CourtBazaar shall not be liable for delays, interruptions, or delivery failures arising from circumstances beyond its reasonable control." },
      ],
    },
    {
      id: "changes-to-this-delivery-policy",
      title: "15. Changes to This Delivery Policy",
      body: [
        { type: "p", text: "CourtBazaar may modify this Delivery Policy from time to time. The updated version will become effective upon publication on the Platform." },
      ],
    },
    {
      id: "contact-us",
      title: "16. Contact Us",
      body: [
        { type: "p", text: "For any delivery-related queries, please contact:" },
        { type: "p", text: "CourtBazaar — A Brand of LexOrbit Technologies" },
        { type: "p", text: "Website: www.courtbazaar.com" },
        { type: "p", text: "Email: [Insert Official Support Email]" },
        { type: "callout", variant: "notice", text: "This contact email has not yet been filled in within the approved document — Configuration Required." },
      ],
    },
  ],
});
