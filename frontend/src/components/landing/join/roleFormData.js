/* Field/section definitions for each "Join as..." form.
   Consumed by RoleForm via FieldKit's renderField(). UI only — no backend submission yet. */

const genders = ["Male", "Female", "Other"];

const stateBarCouncils = [
  "Bar Council of Delhi",
  "Bar Council of Uttar Pradesh",
  "Bar Council of Maharashtra & Goa",
  "Bar Council of West Bengal",
  "Bar Council of Tamil Nadu",
  "Bar Council of Karnataka",
  "Bar Council of Kerala",
  "Bar Council of Gujarat",
  "Bar Council of Rajasthan",
  "Bar Council of Madhya Pradesh",
  "Bar Council of Punjab & Haryana",
  "Bar Council of Bihar",
  "Bar Council of Odisha",
  "Bar Council of Andhra Pradesh",
  "Bar Council of Telangana",
  "Bar Council of Chhattisgarh",
  "Bar Council of Jharkhand",
  "Bar Council of Uttarakhand",
  "Bar Council of Himachal Pradesh",
  "Bar Council of Assam, Nagaland, Meghalaya, Manipur, Tripura, Mizoram & Arunachal Pradesh",
  "Bar Council of Sikkim",
  "Bar Council of Jammu & Kashmir and Ladakh",
  "Other",
];

const languageOptions = ["Hindi", "English", "Both", "Hindi & Other (Specify)", "English & Other (Specify)", "Other (Specify)"];
const languageOtherTriggerValues = ["Hindi & Other (Specify)", "English & Other (Specify)", "Other (Specify)"];

export const proxyCounselSections = [
  {
    title: "Personal Information",
    fields: [
      { label: "Full Name (as per Bar Council Enrollment Certificate)", required: true, span: 2 },
      { label: "Mobile Number", required: true, type: "tel" },
      { label: "Email Address", required: true, type: "email" },
      { label: "Date of Birth", required: true, type: "date", max: "today" },
      { label: "Gender", required: true, type: "select", options: genders },
      { label: "State", required: true, type: "state" },
      { label: "District", required: true, type: "district" },
      { label: "City", type: "text" },
      { label: "Residence Address", required: true, type: "textarea", span: 2 },
      { label: "Current City", type: "text" },
    ],
  },
  {
    title: "Bar Council Information",
    fields: [
      { label: "State Bar Council", required: true, type: "barCouncil", other: true, options: stateBarCouncils, default: "Bar Council of Delhi" },
      { label: "Bar Council Enrollment Number", required: true, type: "text" },
      { label: "Date of Enrollment", required: true, type: "date" },
      { label: "Upload Bar Council Enrollment Certificate", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Advocate ID Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Certificate of Practice", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
    ],
  },
  {
    title: "Identity Information",
    fields: [
      { label: "Aadhaar Number", required: true, type: "text" },
      { label: "PAN Number", type: "text" },
      { label: "Upload Aadhaar Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload PAN Card", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Recent Passport Size Photograph", required: true, type: "file", hint: "JPG/PNG, Max 2MB", span: 2 },
    ],
  },
  {
    title: "Professional Details",
    fields: [
      { label: "Total Years of Practice", required: true, type: "radio", options: ["Less than 1 Year", "1-3 Years", "3-5 Years", "5-10 Years", "More than 10 Years"], span: 2 },
      {
        label: "Primary Area of Practice", required: true, type: "checkboxes", span: 2,
        options: ["Civil Matters", "Criminal Matters", "Family Matters", "Consumer Matters", "Commercial Matters", "Arbitration Matters", "Labour Matters", "Property Matters", "Motor Accident Claims"],
        other: true,
      },
      { label: "Upload Order Sheets (Minimum 5)", type: "file", multiple: true, hint: "PDF/JPG/PNG, Max 10MB each", span: 2 },
      { label: "Language", required: true, type: "radio", options: languageOptions, otherTriggerValues: languageOtherTriggerValues, span: 2 },
      { label: "Approximate Number of Matters Handled", type: "number" },
      { label: "Current Professional Status", required: true, type: "radio", options: ["Independent Practitioner", "Chamber Associate", "Law Firm Associate", "Senior Advocate Chamber"], other: true, span: 2 },
      { label: "Primary Court of Practice", required: true, type: "courtOfPractice" },
      { label: "Maximum Distance You Are Willing to Travel for Appearance", required: true, type: "radio", options: ["Up to 10 KM", "Up to 25 KM", "Up to 50 KM", "Up to 100 KM", "Any Distance"], span: 2 },
      { label: "Availability", required: true, type: "radio", options: ["Full Time", "Part Time", "Weekdays Only", "Weekends Only"], span: 2 },
    ],
  },
  {
    title: "Declaration",
    fields: [
      {
        type: "declaration", span: 2,
        items: [
          "I confirm that I am a duly enrolled Advocate.",
          "I certify that all information provided is true and correct.",
          "I authorize CourtBazaar™ to verify my enrollment and professional credentials.",
          "I agree to receive appearance assignments, notifications and communications from CourtBazaar™.",
        ],
      },
      { type: "file", label: "Digital Signature", required: true, hint: "PDF/JPG/PNG, Max 2MB", span: 2 },
      { label: "Full Name", required: true, type: "text" },
      { label: "Date", required: true, type: "date", default: "today" },
    ],
  },
];

export const counselSections = [
  {
    title: "Personal Information",
    fields: [
      { label: "Full Name (as per Bar Council Enrollment Certificate)", required: true, span: 2 },
      { label: "Mobile Number", required: true, type: "tel" },
      { label: "Email Address", required: true, type: "email" },
      { label: "Date of Birth", required: true, type: "date", max: "today" },
      { label: "Gender", required: true, type: "select", options: genders },
      { label: "State", required: true, type: "state" },
      { label: "District", required: true, type: "district" },
      { label: "City", type: "text" },
      { label: "Residence Address", required: true, type: "textarea", span: 2 },
      { label: "Current City", type: "text" },
    ],
  },
  {
    title: "Bar Council Information",
    fields: [
      { label: "State Bar Council", required: true, type: "barCouncil", other: true, options: stateBarCouncils, default: "Bar Council of Delhi" },
      { label: "Bar Council Enrollment Number", required: true, type: "text" },
      { label: "Date of Enrollment", required: true, type: "date" },
      { label: "Upload Bar Council Enrollment Certificate", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Advocate ID Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Certificate of Practice", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
    ],
  },
  {
    title: "Identity Information",
    fields: [
      { label: "Aadhaar Number", required: true, type: "text" },
      { label: "PAN Number", type: "text" },
      { label: "Upload Aadhaar Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload PAN Card", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Recent Passport Size Photograph", required: true, type: "file", hint: "JPG/PNG, Max 2MB", span: 2 },
    ],
  },
  {
    title: "Professional Details",
    fields: [
      { label: "Total Years of Practice", required: true, type: "radio", options: ["Less than 1 Year", "1-3 Years", "3-5 Years", "5-10 Years", "More than 10 Years"], span: 2 },
      {
        label: "Primary Area of Practice", required: true, type: "checkboxes", span: 2,
        options: ["Civil Matters", "Criminal Matters", "Family Matters", "Consumer Matters", "Commercial Matters", "Arbitration Matters", "Labour Matters", "Property Matters", "Motor Accident Claims"],
        other: true,
      },
      { label: "Upload Order Sheets (Minimum 5)", type: "file", multiple: true, hint: "PDF/JPG/PNG, Max 10MB each", span: 2 },
      { label: "Language", required: true, type: "radio", options: languageOptions, otherTriggerValues: languageOtherTriggerValues, span: 2 },
      { label: "Approximate Number of Matters Handled", type: "number" },
      { label: "Current Professional Status", required: true, type: "radio", options: ["Independent Practitioner", "Chamber Associate", "Law Firm Associate", "Senior Advocate Chamber"], other: true, span: 2 },
      { label: "Primary Court of Practice", required: true, type: "courtOfPractice" },
      { label: "Maximum Distance You Are Willing to Travel for Appearance", required: true, type: "radio", options: ["Up to 10 KM", "Up to 25 KM", "Up to 50 KM", "Up to 100 KM", "Any Distance"], span: 2 },
      { label: "Availability", required: true, type: "radio", options: ["Full Time", "Part Time", "Weekdays Only", "Weekends Only"], span: 2 },
    ],
  },
  {
    title: "Declaration",
    fields: [
      {
        type: "declaration", span: 2,
        items: [
          "I confirm that I am a duly enrolled Advocate.",
          "I certify that all information provided is true and correct.",
          "I authorize CourtBazaar™ to verify my enrollment and professional credentials.",
          "I agree to receive appearance assignments, notifications and communications from CourtBazaar™.",
        ],
      },
      { type: "file", label: "Digital Signature", required: true, hint: "PDF/JPG/PNG, Max 2MB", span: 2 },
      { label: "Full Name", required: true, type: "text" },
      { label: "Date", required: true, type: "date", default: "today" },
    ],
  },
];

export const vendorSections = [
  {
    title: "Business Information",
    fields: [
      { label: "Business / Shop Name (As per MSME)", required: true, type: "text" },
      { label: "Owner / Contact Person Name", required: true, type: "text" },
      { label: "Mobile Number", required: true, type: "tel" },
      { label: "Email Address", required: true, type: "email" },
      { label: "Business Type", required: true, type: "select", options: ["Printout/ Photocopy Shop", "Digital Print Studio", "Other"] },
      { label: "Constitution Type", required: true, type: "select", options: ["Sole Proprietorship", "Partnership", "Private Limited", "LLP"] },
      { label: "GST Number", type: "text" },
      { label: "PAN Number", required: true, type: "text" },
      { label: "Shop / Business Registration Number", type: "text" },
      { label: "Date of Establishment", required: true, type: "date" },
    ],
  },
  {
    title: "Business Address",
    fields: [
      { label: "Shop / Office Address", required: true, type: "textarea", span: 2 },
      { label: "State", required: true, type: "state" },
      { label: "District", required: true, type: "district" },
      { label: "City", type: "text" },
      { label: "Pincode", required: true, type: "text" },
      { label: "Landmark (Optional)", type: "text" },
    ],
  },
  {
    title: "Bank Details",
    fields: [
      { label: "Bank Account Holder Name", required: true, type: "text" },
      { label: "Bank Name", required: true, type: "text" },
      { label: "Account Number", required: true, type: "text" },
      { label: "IFSC Code", required: true, type: "text" },
      { label: "Account Type", required: true, type: "select", options: ["Savings", "Current"] },
    ],
  },
  {
    title: "Business Verification Documents",
    fields: [
      { label: "GST Certificate", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "PAN Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Shop / Business Registration / MSME", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Address Proof", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Bank Cancelled Cheque", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Shop / Office Photo", required: true, type: "file", hint: "JPG/PNG, Max 5MB" },
      { label: "Owner Photo with Shop", required: true, type: "file", hint: "JPG/PNG, Max 5MB", span: 2 },
    ],
  },
  {
    title: "Business Capability",
    fields: [
      {
        label: "Types of Printing Services You Provide", required: true, type: "checkboxes", span: 2,
        options: ["Black & White Printing", "Color Printing", "Photocopy", "Scanning", "Large Format Printing", "Spiral Binding", "Lamination"],
        other: true,
      },
      { label: "Maximum Printing Capacity (Pages per day)", required: true, type: "number" },
      { label: "Working Hours", required: true, type: "select", options: ["9 AM - 6 PM", "9 AM - 9 PM", "24 Hours", "Custom"] },
    ],
  },
  {
    title: "Terms & Declaration",
    fields: [
      {
        type: "declaration", span: 2,
        items: [
          "I hereby declare that all the information provided by me is true and correct. I agree to the terms and conditions of the CourtBazaar™ Vendor Policy and authorize CourtBazaar™ to verify my details and documents.",
        ],
      },
    ],
  },
];

export const partnerSections = [
  {
    title: "Personal Information",
    fields: [
      { label: "Full Name (as per Bar Council Certificate)", required: true, span: 2 },
      { label: "Mobile Number", required: true, type: "tel" },
      { label: "Email Address", required: true, type: "email" },
      { label: "Date of Birth", required: true, type: "date", max: "today" },
      { label: "Gender", required: true, type: "select", options: genders },
      { label: "State", required: true, type: "state" },
      { label: "District", required: true, type: "district" },
      { label: "City", type: "text" },
      { label: "Residence Address", required: true, type: "textarea", span: 2 },
      { label: "Current City", required: true, type: "text" },
      { label: "Pincode", required: true, type: "text" },
    ],
  },
  {
    title: "Professional & Bar Council Details",
    fields: [
      { label: "State Bar Council", required: true, type: "barCouncil", other: true, options: stateBarCouncils },
      { label: "Bar Council Enrollment Number", required: true, type: "text" },
      { label: "Date of Enrollment", required: true, type: "date" },
      { label: "Upload Bar Council Enrollment Certificate", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Advocate ID Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Total Years of Practice", required: true, type: "select", options: ["1-3 Years", "3-5 Years", "5-10 Years", "More than 10 Years"] },
      {
        label: "Primary Area of Practice", required: true, type: "checkboxes", span: 2,
        options: ["Civil Matters", "Criminal Matters", "Family Matters", "Commercial Matters", "Arbitration Matters"],
        other: true,
      },
    ],
  },
  {
    title: "Identity Information",
    fields: [
      { label: "Aadhaar Number", required: true, type: "text" },
      { label: "PAN Number", type: "text" },
      { label: "Upload Aadhaar Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload PAN Card", type: "file", hint: "PDF/JPG/PNG, Max 5MB" },
      { label: "Upload Recent Passport Size Photo", required: true, type: "file", hint: "JPG/PNG, Max 2MB", span: 2 },
    ],
  },
  {
    title: "E-Filing Partner Capability",
    fields: [
      {
        label: "Courts / Tribunals You Can e-File In", required: true, type: "checkboxes", span: 2,
        options: ["Supreme Court", "High Court", "District Court", "NCLT", "DRT", "RERA", "ITAT", "CAT", "Consumer Commission", "CESTAT", "Labour Court / Tribunal"],
        other: true,
      },
      { label: "E-Filing Experience (Years)", required: true, type: "select", options: ["Less than 1 Year", "1-3 Years", "3-5 Years", "More than 5 Years"] },
      { label: "Average e-Filings Per Month", required: true, type: "select", options: ["Less than 10", "10-25", "25-50", "More than 50"] },
      { label: "Do you have Gov. approved e-Filing Vendor Code / Login?", required: true, type: "radio", options: ["Yes", "No"], span: 2 },
    ],
  },
  {
    title: "Service Information",
    fields: [
      { label: "Turnaround Time for e-Filing", required: true, type: "turnaroundTime", options: ["Same Day", "Next Day", "2-3 Days", "Custom Time"] },
      { label: "Availability", required: true, type: "radio", options: ["Full Time", "Part Time", "Weekdays Only", "Weekends Only"] },
      { label: "Do you provide Vakalat / Appearance through e-Filing?", required: true, type: "radio", options: ["Yes", "No"], default: "No", span: 2 },
    ],
  },
  {
    title: "Declaration",
    fields: [
      {
        type: "declaration", span: 2,
        items: [
          "I confirm that I am a duly enrolled Advocate and my enrollment is valid.",
          "I certify that all information provided is true and correct.",
          "I authorize CourtBazaar™ to verify my credentials and bar enrollment details.",
          "I agree to provide e-filing services in a professional and timely manner.",
        ],
      },
      { type: "file", label: "Digital Signature", required: true, hint: "PDF/JPG/PNG, Max 2MB", span: 2 },
      { label: "Full Name", required: true, type: "text" },
      { label: "Date", required: true, type: "date", default: "today" },
    ],
  },
];

export const agentSections = [
  {
    title: "Personal Information",
    fields: [
      { label: "Full Name", required: true, type: "text" },
      { label: "Mobile Number", required: true, type: "tel" },
      { label: "Alternative Mobile Number", type: "tel" },
      { label: "Email Address (Optional)", type: "email" },
      { label: "Date of Birth", required: true, type: "date", max: "today" },
      { label: "Gender", required: true, type: "select", options: genders },
      { label: "Father's / Husband's Name", required: true, type: "text" },
      { label: "State", required: true, type: "state" },
      { label: "District", required: true, type: "district" },
      { label: "City", required: true, type: "text" },
      { label: "Current Address / Residential Address", required: true, type: "textarea", span: 2 },
      { label: "Pincode", required: true, type: "text" },
    ],
  },
  {
    title: "Identity Information",
    fields: [
      { label: "Aadhaar Number", required: true, type: "text" },
      { label: "PAN Number (Optional)", type: "text" },
      { label: "Upload Aadhaar Card", required: true, type: "file", hint: "PDF/JPG/PNG, Max 2MB" },
      { label: "Upload PAN Card (Optional)", type: "file", hint: "PDF/JPG/PNG, Max 2MB" },
      { label: "Upload Recent Photograph", required: true, type: "file", hint: "JPG/PNG, Max 2MB", span: 2 },
    ],
  },
  {
    title: "Professional Information",
    fields: [
      { label: "Have you worked in any court / legal office before?", required: true, type: "radio", options: ["Yes", "No"] },
      { label: "If yes, please specify", type: "text", placeholder: "Court/Office name, Role, Experience" },
      {
        label: "Services You Will Provide (Within Court Premises)", required: true, type: "checkboxes", span: 2,
        options: ["Document Collection","Document Pickup", "Document Delivery", "Order / Certified Copy Collection", "File Movement", "Scanning / Filing Support"],
        other: true,
      },
      { label: "Availability", required: true, type: "checkboxes", options: ["Full Time", "Part Time", "Weekdays Only", "Weekends Only"], span: 2 },
    ],
  },
  {
    title: "Additional Information",
    fields: [
      { label: "Languages Known", required: true, type: "checkboxes", options: ["English", "Hindi", "Both"], other: true },
      { label: "Do you have a valid ID proof?", required: true, type: "radio", options: ["Yes", "No"], span: 2, spacing: "loose" },
      { label: "Are you familiar with court premises layout and procedures?", required: true, type: "radio", options: ["Yes", "No"], span: 2 },
      { label: "Any Additional Information", type: "textarea", span: 2 },
    ],
  },
  {
    title: "Declaration",
    fields: [
      {
        type: "declaration", span: 2,
        items: [
          "I confirm that all the information provided is true and correct.",
          "I understand that I will provide delivery services within the court premises only.",
          "I agree to follow all court rules and maintain professionalism.",
          "I authorize CourtBazaar™ to verify my details and contact me for service assignments.",
        ],
      },
      { type: "file", label: "Digital Signature", required: true, hint: "PDF/JPG/PNG, Max 2MB", span: 2 },
      { label: "Full Name", required: true, type: "text" },
      { label: "Date", required: true, type: "date", default: "today" },
    ],
  },
];
