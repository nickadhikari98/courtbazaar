import { makeDoc } from "./_shared";

export default makeDoc({
  slug: "data-retention",
  title: "Data Retention & Deletion Policy",
  summary: "This Data Retention & Deletion Policy explains how we retain, archive, and securely delete personal information, documents, and other data collected through the CourtBazaar Platform.",
  version: "1.0",
  effectiveDate: "2026-06-01",
  lastUpdated: "2026-06-01",
  relatedSlugs: ["privacy", "confidentiality"],
  sections: [
    {
      id: "purpose",
      title: "1. Purpose",
      body: [
        { type: "p", text: 'Welcome to CourtBazaar, a brand operated by LexOrbit Technologies ("CourtBazaar", "we", "our", or "us"). This Data Retention & Deletion Policy explains how we retain, archive, and securely delete personal information, documents, and other data collected through the CourtBazaar Platform.' },
        { type: "p", text: "By using the Platform, you acknowledge that your information may be retained and deleted in accordance with this Policy and applicable law." },
        { type: "p", text: "The purpose of this Policy is to:" },
        { type: "list", items: ["Explain how long information is retained.", "Describe when data is deleted or anonymized.", "Comply with applicable legal and regulatory obligations.", "Protect user privacy while maintaining operational and legal records."] },
      ],
    },
    {
      id: "scope",
      title: "2. Scope",
      body: [
        { type: "p", text: "This Policy applies to all information processed through the CourtBazaar Platform, including:" },
        { type: "list", items: ["User account information", "Identity and contact details", "Uploaded legal and non-legal documents", "Print and photocopy orders", "Scanned documents", "OCR and bookmarked PDF files", "Delivery and pickup information", "Payment-related records", "Customer support communications", "Vendor and advocate information", "Technical logs and security records"] },
      ],
    },
    {
      id: "data-retention-principles",
      title: "3. Data Retention Principles",
      body: [
        { type: "p", text: "CourtBazaar retains information only for as long as it is:" },
        { type: "list", items: ["Necessary to provide requested services.", "Required for customer support.", "Needed to resolve disputes.", "Required to comply with applicable laws.", "Necessary for fraud prevention and security.", "Required for accounting, taxation, or audit purposes.", "Required to establish, exercise, or defend legal claims."] },
        { type: "callout", variant: "info", text: "When data is no longer required, it will be securely deleted or irreversibly anonymized, unless retention is required by law." },
      ],
    },
    {
      id: "categories-of-data-and-retention",
      title: "4. Categories of Data and Retention",
      body: [
        { type: "p", text: "The exact retention period may vary depending on the nature of the service, legal requirements, and operational needs." },
        { type: "p", text: "Examples include:" },
        { type: "list", items: ["Account information", "Order history", "Uploaded documents", "Scanned files", "OCR outputs", "Bookmarked PDFs", "Customer support records", "Payment transaction information", "Delivery records", "Security logs", "Vendor records"] },
        { type: "p", text: "Certain categories of information may be retained longer where required by law or for legitimate business purposes." },
      ],
    },
    {
      id: "uploaded-documents",
      title: "5. Uploaded Documents",
      body: [
        { type: "p", text: "Documents uploaded for services such as:" },
        { type: "list", items: ["Printing", "Photocopying", "Scanning", "OCR", "PDF Bookmarking", "Filing-ready document preparation"] },
        { type: "p", text: "will generally be retained only for the period reasonably necessary to:" },
        { type: "list", items: ["Complete the requested service.", "Deliver the completed work.", "Handle customer queries.", "Resolve disputes.", "Meet applicable legal obligations."] },
        { type: "p", text: "Where operationally feasible, users may be provided with options to delete eligible uploaded files from their accounts." },
        { type: "p", text: "CourtBazaar reserves the right to retain copies where required by law, court order, regulatory requirement, or for the establishment, exercise, or defence of legal claims." },
      ],
    },
    {
      id: "account-deletion",
      title: "6. Account Deletion",
      body: [
        { type: "p", text: "Users may request deletion of their CourtBazaar account, subject to applicable laws and operational requirements." },
        { type: "p", text: "Upon approval of a deletion request:" },
        { type: "list", items: ["Access to the account may be disabled.", "Personal information may be deleted or anonymized.", "Certain records may continue to be retained where legally required or necessary for legitimate business purposes."] },
        { type: "p", text: "Deletion of an account does not necessarily result in immediate deletion of all associated records." },
      ],
    },
    {
      id: "backup-copies",
      title: "7. Backup Copies",
      body: [
        { type: "p", text: "Information may continue to exist in encrypted backup systems for a limited period following deletion." },
        { type: "p", text: "Backup copies are maintained for:" },
        { type: "list", items: ["Disaster recovery", "Business continuity", "Security", "System restoration"] },
        { type: "p", text: "Such backup data will not ordinarily be used for operational purposes unless restoration becomes necessary." },
      ],
    },
    {
      id: "legal-holds",
      title: "8. Legal Holds",
      body: [
        { type: "p", text: "CourtBazaar may suspend deletion of information where necessary to:" },
        { type: "list", items: ["Comply with applicable law.", "Respond to lawful requests from competent authorities.", "Comply with court orders.", "Investigate fraud or misuse.", "Resolve disputes.", "Protect legal rights and interests."] },
        { type: "p", text: "Such information will be retained until the legal or regulatory requirement no longer applies." },
      ],
    },
    {
      id: "secure-deletion",
      title: "9. Secure Deletion",
      body: [
        { type: "p", text: "CourtBazaar uses reasonable technical and organizational measures to securely delete or anonymize information when it is no longer required." },
        { type: "p", text: "Deletion methods may include:" },
        { type: "list", items: ["Secure electronic deletion.", "Overwriting of storage media where appropriate.", "Cryptographic erasure where applicable.", "Anonymization of datasets used for analytics."] },
      ],
    },
    {
      id: "user-responsibilities",
      title: "10. User Responsibilities",
      body: [
        { type: "p", text: "Users are encouraged to:" },
        { type: "list", items: ["Download important documents before requesting account deletion.", "Maintain their own copies of legal or business documents.", "Verify that required files have been received before requesting deletion."] },
        { type: "p", text: "CourtBazaar is not responsible for documents that users fail to download before eligible deletion." },
      ],
    },
    {
      id: "exceptions",
      title: "11. Exceptions",
      body: [
        { type: "p", text: "CourtBazaar may retain information beyond normal retention periods where necessary for:" },
        { type: "list", items: ["Legal compliance.", "Regulatory obligations.", "Taxation and accounting.", "Fraud prevention.", "Security investigations.", "Enforcement of contractual rights.", "Protection of users or the Platform."] },
      ],
    },
    {
      id: "changes-to-this-policy",
      title: "12. Changes to This Policy",
      body: [
        { type: "p", text: "CourtBazaar may amend this Data Retention & Deletion Policy from time to time." },
        { type: "p", text: "The revised Policy will become effective upon publication on the Platform." },
      ],
    },
    {
      id: "contact-us",
      title: "13. Contact Us",
      body: [
        { type: "p", text: "If you have questions about this Policy or wish to request deletion of eligible personal information, please contact:" },
        { type: "p", text: "CourtBazaar — A Brand of LexOrbit Technologies" },
        { type: "p", text: "Website: www.courtbazaar.com" },
        { type: "p", text: "Grievance Officer: [Insert Name and Official Email]" },
        { type: "callout", variant: "notice", text: "This contact detail has not yet been filled in within the approved document — Configuration Required." },
      ],
    },
  ],
});
