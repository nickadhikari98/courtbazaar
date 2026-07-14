import { makeDoc } from "./_shared";

export default makeDoc({
  slug: "confidentiality",
  title: "Confidentiality & Document Handling Policy",
  summary:
    "This Confidentiality & Document Handling Policy governs the collection, handling, access, use, storage, sharing, retention, and deletion of documents uploaded, transmitted, processed, or shared through the CourtBazaar Platform.",
  version: "1.0",
  effectiveDate: "2026-06-01",
  lastUpdated: "2026-06-01",
  relatedSlugs: ["privacy", "data-retention", "vendor-terms"],
  sections: [
    {
      id: "purpose-of-policy",
      title: "1. Purpose of Policy",
      body: [
        { type: "p", text: "This Confidentiality & Document Handling Policy (\"Policy\") governs the collection, handling, access, use, storage, sharing, retention, and deletion of documents uploaded, transmitted, processed, or shared through the CourtBazaar Platform." },
        { type: "p", text: "By using the Platform, you agree to this Policy." },
        { type: "p", text: "CourtBazaar recognises that users may upload:" },
        { type: "list", items: ["court records;", "pleadings;", "affidavits;", "evidence;", "identity documents;", "contracts;", "legal notices;", "confidential communications;", "commercially sensitive information."] },
        { type: "p", text: "This Policy seeks to establish reasonable safeguards for the handling of such information." },
      ],
    },
    {
      id: "ownership-of-documents",
      title: "2. Ownership of Documents",
      body: [
        { type: "p", text: "All documents uploaded to the Platform shall remain the sole property of:" },
        { type: "list", items: ["the user;", "the advocate;", "the client; or", "the lawful owner of such documents."] },
        { type: "p", text: "Uploading documents to the Platform does not transfer:" },
        { type: "list", items: ["ownership;", "intellectual property rights;", "confidentiality rights"] },
        { type: "p", text: "to CourtBazaar." },
        { type: "callout", variant: "info", text: "CourtBazaar receives only a limited, non-exclusive permission to process and store documents solely for the purpose of providing the requested services." },
      ],
    },
    {
      id: "confidential-information",
      title: "3. Confidential Information",
      body: [
        { type: "p", text: "For the purpose of this Policy, Confidential Information includes:" },
        { type: "list", items: ["court records;", "pleadings;", "legal strategies;", "evidence;", "personal information;", "identity documents;", "commercial information;", "communications;", "any information designated as confidential."] },
      ],
    },
    {
      id: "platform-role",
      title: "4. Platform Role",
      body: [
        { type: "p", text: "CourtBazaar acts solely as:" },
        { type: "list", items: ["a technology intermediary;", "workflow platform;", "professional discovery platform."] },
        { type: "p", text: "CourtBazaar is not:" },
        { type: "list", items: ["a law firm;", "legal representative;", "attorney;", "fiduciary."] },
        { type: "p", text: "Nothing in this Policy creates duties equivalent to advocate-client privilege except to the extent required by law." },
      ],
    },
    {
      id: "access-to-documents",
      title: "5. Access to Documents",
      body: [
        { type: "p", text: "Access to documents shall be restricted on a need-to-know basis." },
        { type: "p", text: "Documents may be accessed only by:" },
        { type: "list", items: ["authorised employees;", "authorised interns;", "authorised consultants;", "vendors selected by the user;", "proxy counsels selected by the user;", "service providers engaged for providing requested services."] },
      ],
    },
    {
      id: "no-unauthorised-disclosure",
      title: "6. No Unauthorised Disclosure",
      body: [
        { type: "p", text: "No person accessing documents through the Platform shall:" },
        { type: "list", items: ["disclose information without authority;", "use documents for personal purposes;", "share documents with unauthorised persons;", "publish documents;", "sell documents;", "exploit documents."] },
      ],
    },
    {
      id: "no-unauthorised-copies",
      title: "7. No Unauthorised Copies",
      body: [
        { type: "p", text: "No person shall:" },
        { type: "list", items: ["make unnecessary copies;", "retain copies beyond operational necessity;", "reproduce documents without authorisation;", "create backups for personal use."] },
        { type: "p", text: "Temporary operational copies may be created where reasonably necessary to facilitate services." },
      ],
    },
    {
      id: "document-use-restrictions",
      title: "8. Document Use Restrictions",
      body: [
        { type: "p", text: "Documents may be used solely for:" },
        { type: "list", items: ["Printing;", "photocopy", "scanning;", "OCR processing;", "bookmarking;", "e-filing;", "proxy appearances;", "other services requested by users."] },
        { type: "callout", variant: "warning", text: "Any other use is strictly prohibited." },
      ],
    },
    {
      id: "data-security-measures",
      title: "9. Data Security Measures",
      body: [
        { type: "p", text: "CourtBazaar may implement commercially reasonable safeguards, including:" },
        { type: "list", items: ["access controls;", "password protection;", "encryption in transit;", "encryption at rest;", "audit logs;", "restricted permissions;", "secure storage practices."] },
        { type: "p", text: "However, no system is completely secure and CourtBazaar does not guarantee absolute security." },
      ],
    },
    {
      id: "vendor-confidentiality-obligations",
      title: "10. Vendor Confidentiality Obligations",
      body: [
        { type: "p", text: "All vendors, including:" },
        { type: "list", items: ["Print Vendors;", "Document Processing Vendor;", "E-Filing Agents;", "Delivery Partners;", "Counsel/Proxy Counsels;", "Service Providers;"] },
        { type: "p", text: "may be required to execute:" },
        { type: "list", items: ["Confidentiality Undertakings;", "Non-Disclosure Agreements;", "Data Processing Agreements."] },
      ],
    },
    {
      id: "employee-confidentiality-obligations",
      title: "11. Employee Confidentiality Obligations",
      body: [
        { type: "p", text: "Employees, interns, consultants, and contractors may be required to execute:" },
        { type: "list", items: ["Confidentiality Agreements;", "Non-Disclosure Agreements;", "Information Security Undertakings."] },
      ],
    },
    {
      id: "user-responsibility",
      title: "12. User Responsibility",
      body: [
        { type: "p", text: "Users are solely responsible for:" },
        { type: "list", items: ["ensuring that they possess authority to upload documents;", "maintaining backups;", "redacting sensitive information where necessary."] },
      ],
    },
    {
      id: "document-retention",
      title: "13. Document Retention",
      body: [
        { type: "p", text: "Documents shall be retained only:" },
        { type: "list", items: ["for operational purposes;", "to provide services;", "for legal compliance;", "for dispute resolution;", "for legitimate business requirements."] },
        { type: "p", text: "CourtBazaar reserves the right to determine reasonable retention periods." },
      ],
    },
    {
      id: "secure-deletion-policy",
      title: "14. Secure Deletion Policy",
      body: [
        { type: "p", text: "Upon expiry of retention requirements, documents may be:" },
        { type: "list", items: ["deleted;", "anonymised;", "archived;", "destroyed."] },
        { type: "p", text: "Reasonable efforts shall be made to securely delete documents from active systems." },
        { type: "p", text: "However, residual copies may continue to exist in:" },
        { type: "list", items: ["backups;", "disaster recovery systems;", "logs;", "archived systems"] },
        { type: "p", text: "for a reasonable period." },
      ],
    },
    {
      id: "return-of-documents",
      title: "15. Return of Documents",
      body: [
        { type: "p", text: "Where operationally feasible, users may request:" },
        { type: "list", items: ["copies of documents;", "deletion of documents;", "account closure."] },
        { type: "p", text: "Such requests shall remain subject to:" },
        { type: "list", items: ["legal obligations;", "technical feasibility;", "business requirements."] },
      ],
    },
    {
      id: "data-breaches",
      title: "16. Data Breaches",
      body: [
        { type: "p", text: "In the event of a suspected security incident, CourtBazaar may:" },
        { type: "list", items: ["investigate the incident;", "mitigate the impact;", "notify affected users where required by applicable law."] },
        { type: "p", text: "CourtBazaar shall not be liable for incidents beyond its reasonable control." },
      ],
    },
    {
      id: "limitation-of-liability",
      title: "17. Limitation of Liability",
      body: [
        { type: "p", text: "To the maximum extent permitted by law, CourtBazaar shall not be liable for:" },
        { type: "list", items: ["unauthorised access;", "cyber incidents;", "data breaches;", "vendor misconduct;", "loss of documents;", "corruption of files;", "consequential damages."] },
        { type: "p", text: "CourtBazaar acts solely as a technology intermediary." },
      ],
    },
    {
      id: "indemnity",
      title: "18. Indemnity",
      body: [
        { type: "p", text: "Users and service providers agree to indemnify and hold harmless CourtBazaar from all claims arising out of:" },
        { type: "list", items: ["unauthorised disclosure;", "misuse of documents;", "breach of confidentiality obligations;", "unlawful uploads."] },
      ],
    },
    {
      id: "governing-law",
      title: "19. Governing Law",
      body: [{ type: "p", text: "This Policy shall be governed by the laws of India." }],
    },
    {
      id: "dispute-resolution",
      title: "20. Dispute Resolution",
      body: [
        { type: "p", text: "Disputes arising under this Policy shall first be attempted to be resolved amicably." },
        { type: "p", text: "Failing such resolution, disputes shall be referred to arbitration under the Arbitration and Conciliation Act, 1996." },
        { type: "p", text: "Seat and Venue: Delhi, India." },
        { type: "p", text: "Courts at Delhi shall have exclusive jurisdiction." },
      ],
    },
    {
      id: "contact-details",
      title: "21. Contact Details",
      body: [
        { type: "p", text: "CourtBazaar" },
        { type: "p", text: "Email: courtbazaar@gmail.com" },
        { type: "callout", variant: "info", text: "By using the Platform, you acknowledge that you have read, understood, and agreed to this Confidentiality & Document Handling Policy." },
      ],
    },
  ],
});
