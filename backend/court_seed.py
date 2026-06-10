"""Court hierarchy and service catalog seed data for CourtBazaar India."""

COURT_DATA = [
    {
        "state_id": "state_delhi", "name": "Delhi", "code": "DL",
        "courts": [
            {"court_id": "court_sc_india", "name": "Supreme Court of India", "type": "supreme", "address": "Tilak Marg, New Delhi"},
            {"court_id": "court_delhi_hc", "name": "Delhi High Court", "type": "high_court", "address": "Sher Shah Road, New Delhi"},
            {"court_id": "court_tishazari", "name": "Tis Hazari Court Complex", "type": "district", "district": "Central", "address": "Tis Hazari, Delhi"},
            {"court_id": "court_patiala_house", "name": "Patiala House Court", "type": "district", "district": "New Delhi", "address": "Bhagwan Das Road, New Delhi"},
            {"court_id": "court_karkardooma", "name": "Karkardooma Court", "type": "district", "district": "East", "address": "Karkardooma, Delhi"},
            {"court_id": "court_saket", "name": "Saket District Court", "type": "district", "district": "South", "address": "Saket, New Delhi"},
            {"court_id": "court_rohini", "name": "Rohini District Court", "type": "district", "district": "North", "address": "Rohini, Delhi"},
            {"court_id": "court_dwarka", "name": "Dwarka District Court", "type": "district", "district": "South West", "address": "Dwarka, Delhi"},
            {"court_id": "court_nclt_delhi", "name": "NCLT Delhi Bench", "type": "tribunal", "address": "CGO Complex, Delhi"},
            {"court_id": "court_drt_delhi", "name": "DRT Delhi", "type": "tribunal", "address": "Jeevan Tara Building, New Delhi"},
        ],
    },
    {
        "state_id": "state_mh", "name": "Maharashtra", "code": "MH",
        "courts": [
            {"court_id": "court_bombay_hc", "name": "Bombay High Court", "type": "high_court", "address": "Fort, Mumbai"},
            {"court_id": "court_bombay_hc_nagpur", "name": "Bombay HC Nagpur Bench", "type": "high_court", "address": "Civil Lines, Nagpur"},
            {"court_id": "court_mumbai_city", "name": "Mumbai City Civil Court", "type": "district", "district": "Mumbai", "address": "Fort, Mumbai"},
            {"court_id": "court_pune", "name": "Pune District Court", "type": "district", "district": "Pune", "address": "Shivajinagar, Pune"},
            {"court_id": "court_nclt_mumbai", "name": "NCLT Mumbai Bench", "type": "tribunal", "address": "MTNL Building, Mumbai"},
        ],
    },
    {
        "state_id": "state_ka", "name": "Karnataka", "code": "KA",
        "courts": [
            {"court_id": "court_karnataka_hc", "name": "Karnataka High Court", "type": "high_court", "address": "Bengaluru"},
            {"court_id": "court_bangalore_city", "name": "Bengaluru City Civil Court", "type": "district", "district": "Bengaluru Urban", "address": "Mayo Hall, Bengaluru"},
            {"court_id": "court_mysuru", "name": "Mysuru District Court", "type": "district", "district": "Mysuru", "address": "Mysuru"},
            {"court_id": "court_nclt_bengaluru", "name": "NCLT Bengaluru Bench", "type": "tribunal", "address": "Kendriya Sadan, Bengaluru"},
        ],
    },
    {
        "state_id": "state_tn", "name": "Tamil Nadu", "code": "TN",
        "courts": [
            {"court_id": "court_madras_hc", "name": "Madras High Court", "type": "high_court", "address": "Parry's Corner, Chennai"},
            {"court_id": "court_madras_city", "name": "Madras City Civil Court", "type": "district", "district": "Chennai", "address": "Chennai"},
            {"court_id": "court_coimbatore", "name": "Coimbatore District Court", "type": "district", "district": "Coimbatore", "address": "Coimbatore"},
            {"court_id": "court_nclt_chennai", "name": "NCLT Chennai Bench", "type": "tribunal", "address": "Corporate Bhawan, Chennai"},
        ],
    },
    {
        "state_id": "state_up", "name": "Uttar Pradesh", "code": "UP",
        "courts": [
            {"court_id": "court_allahabad_hc", "name": "Allahabad High Court", "type": "high_court", "address": "Prayagraj"},
            {"court_id": "court_allahabad_hc_lko", "name": "Allahabad HC Lucknow Bench", "type": "high_court", "address": "Lucknow"},
            {"court_id": "court_lucknow_dist", "name": "Lucknow District Court", "type": "district", "district": "Lucknow", "address": "Lucknow"},
            {"court_id": "court_noida", "name": "Gautam Budh Nagar District Court", "type": "district", "district": "Gautam Budh Nagar", "address": "Surajpur, Noida"},
        ],
    },
    {
        "state_id": "state_gj", "name": "Gujarat", "code": "GJ",
        "courts": [
            {"court_id": "court_gujarat_hc", "name": "Gujarat High Court", "type": "high_court", "address": "Sola, Ahmedabad"},
            {"court_id": "court_ahmedabad_city", "name": "Ahmedabad City Civil Court", "type": "district", "district": "Ahmedabad", "address": "Bhadra, Ahmedabad"},
        ],
    },
    {
        "state_id": "state_wb", "name": "West Bengal", "code": "WB",
        "courts": [
            {"court_id": "court_calcutta_hc", "name": "Calcutta High Court", "type": "high_court", "address": "Esplanade, Kolkata"},
            {"court_id": "court_alipore", "name": "Alipore District Court", "type": "district", "district": "South 24 Parganas", "address": "Alipore, Kolkata"},
        ],
    },
    {
        "state_id": "state_tg", "name": "Telangana", "code": "TG",
        "courts": [
            {"court_id": "court_telangana_hc", "name": "Telangana High Court", "type": "high_court", "address": "Hyderabad"},
            {"court_id": "court_hyderabad_city", "name": "Hyderabad City Civil Court", "type": "district", "district": "Hyderabad", "address": "Nampally, Hyderabad"},
        ],
    },
]

SERVICE_CATALOG = [
    # Document Services
    {"service_id": "svc_bw_photocopy", "name": "Black & White Photocopy", "category": "Document Services", "base_price": 1.0, "unit": "per page", "platform_commission_pct": 0.20, "icon": "Printer", "turnaround_hours": 2},
    {"service_id": "svc_color_photocopy", "name": "Color Photocopy", "category": "Document Services", "base_price": 8.0, "unit": "per page", "platform_commission_pct": 0.20, "icon": "Printer", "turnaround_hours": 2},
    {"service_id": "svc_bw_print", "name": "Black & White Printing", "category": "Document Services", "base_price": 2.0, "unit": "per page", "platform_commission_pct": 0.20, "icon": "Printer", "turnaround_hours": 2},
    {"service_id": "svc_color_print", "name": "Color Printing", "category": "Document Services", "base_price": 10.0, "unit": "per page", "platform_commission_pct": 0.20, "icon": "Printer", "turnaround_hours": 2},
    {"service_id": "svc_scanning", "name": "Document Scanning", "category": "Document Services", "base_price": 3.0, "unit": "per page", "platform_commission_pct": 0.20, "icon": "Scan", "turnaround_hours": 4},
    {"service_id": "svc_ocr", "name": "OCR Conversion", "category": "Document Services", "base_price": 5.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "FileText", "turnaround_hours": 6},
    {"service_id": "svc_pdf_merge", "name": "PDF Merge", "category": "Document Services", "base_price": 50.0, "unit": "per file", "platform_commission_pct": 0.30, "icon": "FileStack", "turnaround_hours": 1},
    {"service_id": "svc_pdf_compress", "name": "PDF Compression", "category": "Document Services", "base_price": 30.0, "unit": "per file", "platform_commission_pct": 0.30, "icon": "FileArchive", "turnaround_hours": 1},
    {"service_id": "svc_pagination", "name": "Pagination", "category": "Document Services", "base_price": 2.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "ListOrdered", "turnaround_hours": 4},
    {"service_id": "svc_bookmarking", "name": "Bookmarking", "category": "Document Services", "base_price": 3.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "Bookmark", "turnaround_hours": 4},
    {"service_id": "svc_indexing", "name": "Indexing", "category": "Document Services", "base_price": 200.0, "unit": "per file", "platform_commission_pct": 0.25, "icon": "ListChecks", "turnaround_hours": 6},
    {"service_id": "svc_court_bundle", "name": "Court Bundle Preparation", "category": "Document Services", "base_price": 500.0, "unit": "per bundle", "platform_commission_pct": 0.25, "icon": "Package", "turnaround_hours": 8},
    {"service_id": "svc_paper_book", "name": "Paper Book Preparation", "category": "Document Services", "base_price": 1500.0, "unit": "per book", "platform_commission_pct": 0.25, "icon": "BookOpen", "turnaround_hours": 24},

    # Binding Services
    {"service_id": "svc_spiral_binding", "name": "Spiral Binding", "category": "Binding Services", "base_price": 40.0, "unit": "per file", "platform_commission_pct": 0.25, "icon": "Binary", "turnaround_hours": 2},
    {"service_id": "svc_hard_binding", "name": "Hard Binding", "category": "Binding Services", "base_price": 250.0, "unit": "per file", "platform_commission_pct": 0.25, "icon": "BookMarked", "turnaround_hours": 24},
    {"service_id": "svc_soft_binding", "name": "Soft Binding", "category": "Binding Services", "base_price": 80.0, "unit": "per file", "platform_commission_pct": 0.25, "icon": "Book", "turnaround_hours": 4},
    {"service_id": "svc_file_prep", "name": "File Preparation", "category": "Binding Services", "base_price": 150.0, "unit": "per file", "platform_commission_pct": 0.25, "icon": "Files", "turnaround_hours": 4},
    {"service_id": "svc_court_set", "name": "Court Set Preparation", "category": "Binding Services", "base_price": 600.0, "unit": "per set", "platform_commission_pct": 0.25, "icon": "Layers", "turnaround_hours": 8},

    # E-Filing
    {"service_id": "svc_efile_sc", "name": "Supreme Court E-Filing", "category": "E-Filing Services", "base_price": 1500.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "Gavel", "turnaround_hours": 24},
    {"service_id": "svc_efile_hc", "name": "High Court E-Filing", "category": "E-Filing Services", "base_price": 900.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "Scale", "turnaround_hours": 12},
    {"service_id": "svc_efile_district", "name": "District Court E-Filing", "category": "E-Filing Services", "base_price": 500.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "Building2", "turnaround_hours": 12},
    {"service_id": "svc_efile_consumer", "name": "Consumer Court E-Filing", "category": "E-Filing Services", "base_price": 600.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "ShoppingBag", "turnaround_hours": 12},
    {"service_id": "svc_efile_nclt", "name": "NCLT E-Filing", "category": "E-Filing Services", "base_price": 1200.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "Briefcase", "turnaround_hours": 24},
    {"service_id": "svc_efile_drt", "name": "DRT E-Filing", "category": "E-Filing Services", "base_price": 1000.0, "unit": "per filing", "platform_commission_pct": 0.20, "icon": "Landmark", "turnaround_hours": 24},
    {"service_id": "svc_defect_removal", "name": "Defect Removal Assistance", "category": "E-Filing Services", "base_price": 400.0, "unit": "per defect", "platform_commission_pct": 0.25, "icon": "AlertCircle", "turnaround_hours": 12},

    # Legal Typing
    {"service_id": "svc_typing_petition", "name": "Petition Typing", "category": "Legal Typing", "base_price": 15.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "Type", "turnaround_hours": 6},
    {"service_id": "svc_typing_written", "name": "Written Statement Typing", "category": "Legal Typing", "base_price": 15.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "PenTool", "turnaround_hours": 6},
    {"service_id": "svc_typing_affidavit", "name": "Affidavit Typing", "category": "Legal Typing", "base_price": 12.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "FileSignature", "turnaround_hours": 4},
    {"service_id": "svc_typing_appeal", "name": "Appeal Typing", "category": "Legal Typing", "base_price": 18.0, "unit": "per page", "platform_commission_pct": 0.25, "icon": "Reply", "turnaround_hours": 8},

    # Affidavit Services
    {"service_id": "svc_affidavit_draft", "name": "Affidavit Drafting", "category": "Affidavit Services", "base_price": 300.0, "unit": "per affidavit", "platform_commission_pct": 0.25, "icon": "FileSignature", "turnaround_hours": 6},
    {"service_id": "svc_affidavit_print", "name": "Affidavit Printing", "category": "Affidavit Services", "base_price": 50.0, "unit": "per affidavit", "platform_commission_pct": 0.25, "icon": "Printer", "turnaround_hours": 2},
    {"service_id": "svc_affidavit_exec", "name": "Affidavit Execution", "category": "Affidavit Services", "base_price": 200.0, "unit": "per affidavit", "platform_commission_pct": 0.25, "icon": "CheckCircle2", "turnaround_hours": 6},

    # Notary
    {"service_id": "svc_notary_doc", "name": "Document Notarization", "category": "Notary Services", "base_price": 100.0, "unit": "per document", "platform_commission_pct": 0.25, "icon": "Stamp", "turnaround_hours": 4},
    {"service_id": "svc_notary_affidavit", "name": "Affidavit Notarization", "category": "Notary Services", "base_price": 150.0, "unit": "per affidavit", "platform_commission_pct": 0.25, "icon": "Stamp", "turnaround_hours": 4},
    {"service_id": "svc_notary_verify", "name": "Verification Services", "category": "Notary Services", "base_price": 250.0, "unit": "per verification", "platform_commission_pct": 0.25, "icon": "ShieldCheck", "turnaround_hours": 8},

    # Stamp
    {"service_id": "svc_estamp", "name": "E-Stamp Assistance", "category": "Stamp Services", "base_price": 50.0, "unit": "per stamp", "platform_commission_pct": 0.20, "icon": "Stamp", "turnaround_hours": 4},
    {"service_id": "svc_stamp_duty", "name": "Stamp Duty Assistance", "category": "Stamp Services", "base_price": 200.0, "unit": "per assistance", "platform_commission_pct": 0.20, "icon": "Receipt", "turnaround_hours": 6},
    {"service_id": "svc_court_fee_stamp", "name": "Court Fee Stamp", "category": "Stamp Services", "base_price": 50.0, "unit": "per stamp", "platform_commission_pct": 0.20, "icon": "Ticket", "turnaround_hours": 4},
    {"service_id": "svc_nj_stamp", "name": "Non-Judicial Stamp Paper", "category": "Stamp Services", "base_price": 100.0, "unit": "per stamp paper", "platform_commission_pct": 0.20, "icon": "Newspaper", "turnaround_hours": 4},

    # Court Support
    {"service_id": "svc_certified_copy", "name": "Certified Copy Application", "category": "Court Support", "base_price": 400.0, "unit": "per application", "platform_commission_pct": 0.25, "icon": "FileCheck", "turnaround_hours": 24},
    {"service_id": "svc_cause_list", "name": "Cause List Printing", "category": "Court Support", "base_price": 100.0, "unit": "per list", "platform_commission_pct": 0.25, "icon": "ListTodo", "turnaround_hours": 2},
    {"service_id": "svc_court_runner", "name": "Court Runner Services", "category": "Court Support", "base_price": 500.0, "unit": "per visit", "platform_commission_pct": 0.20, "icon": "Footprints", "turnaround_hours": 4},
    {"service_id": "svc_court_clerk", "name": "Court Clerk Services", "category": "Court Support", "base_price": 800.0, "unit": "per day", "platform_commission_pct": 0.20, "icon": "Users", "turnaround_hours": 8},
    {"service_id": "svc_doc_delivery", "name": "Document Delivery", "category": "Court Support", "base_price": 150.0, "unit": "per delivery", "platform_commission_pct": 0.25, "icon": "Truck", "turnaround_hours": 4},
]
