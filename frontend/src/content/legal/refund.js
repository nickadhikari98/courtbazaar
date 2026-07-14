import { makeDoc } from "./_shared";

function serviceRefundBlock(cancelPermitted, refund, cancelNotPermitted, refundNot) {
  return [
    { type: "definition", term: "Cancellation Permitted", text: cancelPermitted },
    { type: "p", text: `Refund — ${refund}` },
    { type: "definition", term: "Cancellation Not Permitted", text: cancelNotPermitted },
    { type: "p", text: `Refund — ${refundNot}` },
  ];
}

export default makeDoc({
  slug: "refund",
  title: "Refund & Cancellation Policy",
  summary:
    "This Refund & Cancellation Policy governs cancellations, refunds, and related matters concerning services facilitated through the CourtBazaar Platform.",
  version: "1.0",
  effectiveDate: "2026-06-01",
  lastUpdated: "2026-06-01",
  relatedSlugs: ["terms", "delivery"],
  sections: [
    {
      id: "nature-of-the-platform",
      title: "1. Nature of the Platform",
      body: [
        { type: "p", text: "This Refund & Cancellation Policy (\"Policy\") governs cancellations, refunds, and related matters concerning services facilitated through the CourtBazaar Platform." },
        { type: "p", text: "By using the Platform, you agree to this Policy." },
        { type: "p", text: "CourtBazaar is a technology-enabled intermediary platform that facilitates access to independent vendors, proxy counsels, and service providers." },
        { type: "p", text: "CourtBazaar itself does not provide legal services, documents processing services, e-filing services, or professional services." },
        { type: "p", text: "Refunds and cancellations may depend on the stage of completion of the requested service and the policies of independent service providers." },
      ],
    },
    {
      id: "general-principles",
      title: "2. General Principles",
      body: [
        { type: "p", text: "Refunds are determined based on:" },
        { type: "list", items: ["whether the service request has been accepted;", "whether resources have been allocated;", "whether work has commenced;", "whether the service has been completed."] },
        { type: "callout", variant: "notice", text: "Once irreversible work has begun, refunds may not be available." },
      ],
    },
    {
      id: "cancellation-by-user",
      title: "3. Cancellation by User",
      body: [
        { type: "p", text: "Users may cancel service requests before the commencement of work, subject to the specific service conditions below." },
        { type: "p", text: "CourtBazaar reserves the right to deduct applicable:" },
        { type: "list", items: ["platform charges;", "payment gateway charges;", "taxes;", "third-party costs;", "administrative expenses."] },
      ],
    },
    {
      id: "printing-services",
      title: "4. Printing Services",
      body: serviceRefundBlock(
        "Before acceptance of the order by the vendor.",
        "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
        "After acceptance of the order by the vendor.",
        "No refund shall be available."
      ),
    },
    {
      id: "photocopy-services",
      title: "5. Photocopy Services",
      body: serviceRefundBlock(
        "Before acceptance of the order by the vendor.",
        "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
        "After acceptance of the order by the vendor.",
        "No refund shall be available."
      ),
    },
    {
      id: "scanning-services",
      title: "6. Scanning Services",
      body: serviceRefundBlock(
        "Before acceptance of the order by the vendor.",
        "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
        "After acceptance of the order by the vendor.",
        "No refund shall be available."
      ),
    },
    {
      id: "ocr-bookmarking-services",
      title: "7. OCR & Bookmarking Services",
      body: serviceRefundBlock(
        "Before acceptance of the order by the vendor.",
        "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
        "After acceptance of the order by the vendor.",
        "No refund shall be available."
      ),
    },
    {
      id: "e-filing-services",
      title: "8. E-Filing Services",
      body: serviceRefundBlock(
        "Before acceptance of the order by the vendor.",
        "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
        "After acceptance of the order by the vendor.",
        "No refund shall be available."
      ),
    },
    {
      id: "package-services",
      title: "9. Package Services",
      body: [
        { type: "p", text: "Package services may consist of multiple services." },
        ...serviceRefundBlock(
          "Before acceptance of the order by the vendor.",
          "Full refund, subject to deduction of payment gateway charges and applicable taxes.",
          "After acceptance of the order by the vendor.",
          "No refund shall be available."
        ),
      ],
    },
    {
      id: "counsel-proxy-counsel-services",
      title: "10. Counsel/Proxy Counsel Services",
      body: [
        { type: "definition", term: "Cancellation Permitted", text: "Before acceptance of the assignment by the Counsel/Proxy Counsel engaged/hired." },
        { type: "p", text: "Refund — Full refund, subject to deduction of payment gateway charges and applicable taxes." },
        { type: "p", text: "Cancellation Not Permitted — Once:" },
        { type: "list", items: ["a proxy counsel has accepted the assignment;", "counsel has been assigned;", "counsel has commenced preparation;", "counsel has appeared before the court."] },
        { type: "p", text: "Refund — No refund." },
      ],
    },
    {
      id: "vendor-no-show-or-service-failure",
      title: "11. Vendor No-Show or Service Failure",
      body: [
        { type: "p", text: "If an independent vendor or service provider:" },
        { type: "list", items: ["fails to perform;", "cancels without cause;", "becomes unavailable,"] },
        { type: "p", text: "CourtBazaar may, at its sole discretion:" },
        { type: "list", items: ["facilitate replacement;", "assist in resolving the issue;", "process a partial or full refund where appropriate."] },
        { type: "p", text: "CourtBazaar is under no obligation to provide refunds and shall not be liable for acts or omissions of independent third-party service providers." },
      ],
    },
    {
      id: "incorrect-documents-or-user-error",
      title: "12. Incorrect Documents or User Error",
      body: [
        { type: "p", text: "No refunds shall be provided where:" },
        { type: "list", items: ["incorrect files are uploaded;", "wrong instructions are provided;", "user errors result in service deficiencies;", "users fail to respond within reasonable time."] },
      ],
    },
    {
      id: "delays-caused-by-third-parties",
      title: "13. Delays Caused by Third Parties",
      body: [
        { type: "p", text: "CourtBazaar shall not be liable for delays arising due to:" },
        { type: "list", items: ["courts;", "government authorities;", "internet failures;", "technical failures;", "payment gateway issues;", "acts of vendors;", "force majeure events."] },
        { type: "p", text: "Refunds in such situations shall be determined solely by CourtBazaar on a case-by-case basis." },
      ],
    },
    {
      id: "refund-process",
      title: "14. Refund Process",
      body: [
        { type: "p", text: "Approved refunds, if any, shall generally be processed within 7–15 business days depending upon:" },
        { type: "list", items: ["payment method;", "banking systems;", "third-party payment service providers."] },
        { type: "p", text: "CourtBazaar shall not be responsible for delays caused by banks or payment gateways." },
      ],
    },
    {
      id: "payment-gateway-charges",
      title: "15. Payment Gateway Charges",
      body: [{ type: "p", text: "Payment gateway charges, convenience fees, taxes, and other third-party charges may be non-refundable." }],
    },
    {
      id: "platform-charges",
      title: "16. Platform Charges",
      body: [{ type: "p", text: "Any platform fee, convenience fee, or administrative fee charged by CourtBazaar may be non-refundable." }],
    },
    {
      id: "fraudulent-or-abusive-claims",
      title: "17. Fraudulent or Abusive Claims",
      body: [
        { type: "p", text: "CourtBazaar reserves the right to:" },
        { type: "list", items: ["reject refund requests;", "suspend accounts;", "initiate appropriate legal action"] },
        { type: "p", text: "where refund claims are found to be fraudulent, abusive, or made in bad faith." },
      ],
    },
    {
      id: "force-majeure",
      title: "18. Force Majeure",
      body: [
        { type: "p", text: "CourtBazaar shall not be liable for any delay, failure, cancellation, or refund arising from circumstances beyond its reasonable control, including:" },
        { type: "list", items: ["natural disasters;", "government actions;", "strikes;", "internet outages;", "court closures;", "cyber incidents;", "war;", "pandemics."] },
      ],
    },
    {
      id: "final-decision",
      title: "19. Final Decision",
      body: [{ type: "p", text: "To the extent permitted by law, CourtBazaar's determination regarding refund eligibility and cancellation requests shall be final and binding." }],
    },
    {
      id: "contact-us",
      title: "20. Contact Us",
      body: [
        { type: "p", text: "For refund and cancellation requests:" },
        { type: "p", text: "Email: info@courtbazaar.com" },
        { type: "callout", variant: "info", text: "By using the Platform, you acknowledge that you have read, understood, and agreed to this Refund & Cancellation Policy." },
      ],
    },
  ],
});
