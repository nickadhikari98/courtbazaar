# CourtBazaar PRD

## Original Problem Statement
Build a complete enterprise-grade Legal Operations & Court Services Marketplace Web Application for India — multi-vendor marketplace like Zepto/Blinkit/Uber/Urban Company/IndiaMART but for advocates, law firms, court vendors. Nationwide network of verified court-area service providers. Lawyer uploads docs, picks court, orders services → routed to vendor at destination court → tracked end-to-end.

## Architecture
- **Frontend**: React 19 + Tailwind + shadcn/ui (Cabinet Grotesk + Manrope fonts, Deep Navy + Warm Ochre palette)
- **Backend**: FastAPI + Motor (async MongoDB)
- **Storage**: Emergent Object Storage (uploads, KYC docs)
- **AI**: Emergent LLM Key (Claude Sonnet 4.6) for AI Assistant
- **Payments**: Stripe test mode (sk_test_emergent)
- **Auth**: JWT email/password + Mock OTP + Emergent Google OAuth

## Implemented (v1, 2026-02-XX)

### Backend (server.py + court_seed.py)
- Multi-role auth (advocate, law_firm, vendor, e-filing agent, legal typist, notary, stamp vendor, delivery, franchise, admin) via JWT
- Email/password login, mock phone OTP (`123456`), Emergent Google OAuth session exchange
- Court database: 8 states, 30+ courts (SC, HCs, district, NCLT, DRT)
- Service catalog: 44 services across 8 categories (Document, Binding, E-Filing, Typing, Affidavit, Notary, Stamp, Court Support)
- Vendor onboarding + KYC workflow + admin approval
- File upload to Emergent object storage with DB references
- Order lifecycle (10 statuses with timeline), auto vendor matching by court+rating
- Dynamic pricing engine (subtotal, delivery fee, urgent surcharge, convenience, GST 18%, vendor payout, platform commission)
- Stripe checkout integration with status polling + webhook
- Wallet (top-up, transactions)
- AI Chat (Claude Sonnet 4.6) + Filing Checklist generation
- Admin analytics (revenue, commission, top services, court demand)
- Admin vendor approval, pricing controls, user management
- Subscription plans (Free, Advocate Pro, Law Firm, Enterprise)

### Frontend
- Premium landing page (hero, bento services, how-it-works, court coverage, testimonials, CTA)
- Vendor onboarding landing (`/vendor-signup`)
- Login (email/password + phone OTP + Google) with demo credentials hint
- Registration with role selection
- Dashboard (Zepto-style quick services grid, active orders, stats, AI/upgrade promo cards)
- 5-step Smart Order Wizard (Upload → Services → Court → Delivery → Review & Pay)
- Order detail with live 9-step timeline, vendor info, invoice, payment polling, rating
- Orders list with active/completed/all tabs
- Marketplace browse with category chips and search
- Court Directory (state-wise browse)
- AI Assistant chat (with suggestions, Claude-powered)
- Wallet + transactions
- Subscription plans
- Profile editor (Bar Council ID, chamber, GST)
- Vendor Dashboard (queue, earnings, KYC status)
- Vendor onboarding form (shop, KYC, courts, services)
- Admin Dashboard (revenue, charts via recharts, top services, court demand)
- Admin Vendors (pending/approved tabs + approve action)
- Admin Pricing (inline editing for base price + commission)
- Admin Users (search + list)

### Demo credentials (seeded)
- Advocate: `advocate@demo.in` / `Advocate@123`
- Vendor: `vendor@demo.in` / `Vendor@123`
- Admin: `admin@courtbazaar.in` / `Admin@123`

## Deferred / Next Action Items (P1, P2)
- Real SMS/WhatsApp/Email notifications (Twilio, SendGrid) — currently mock
- Multi-user law firm seats with role-permission grid
- Delivery partner workflow + live map tracking
- Hyperlocal courier integration (Dunzo, Borzo)
- Document Intelligence (OCR scoring UI, auto-pagination preview, defect detection inline)
- Franchise Partner dashboard (territory mgmt, revenue split)
- Razorpay gateway (alongside Stripe) for INR-native UX
- Aadhaar/PAN verification API integration
- Court hierarchy expansion (28 states, 500+ courts)
- Mobile PWA + push notifications
- Audit log + GDPR/DPDP compliance reports

## Tech & Testing
- Test credentials at `/app/memory/test_credentials.md`
- Use REACT_APP_BACKEND_URL for all frontend API calls
- All backend routes prefixed with `/api`

## Iteration 2 — P1 Features Shipped (2026-02-XX)

### Backend
- **Expanded court hierarchy**: 36 states/UTs (28 + 8 UTs), 426 courts total (25 HCs + benches, 350+ district courts, 50+ tribunals + quasi-judicial bodies). Only Delhi flagged `serviceable: true` (35 courts: SC, Delhi HC, all 11 district courts, NCLT/NCLAT/DRT/DRAT/CAT/ITAT/CESTAT/NGT/TDSAT/AFT, CCI/SEBI/RERA, all 5 District Consumer Forums, Lokpal, ECI).
- **Order serviceability enforcement**: `/api/orders` returns 400 if `court.serviceable=false`.
- **Razorpay integration** (`/app/backend/razorpay_svc.py`): `/api/payments/razorpay/create-order` + `/api/payments/razorpay/verify`. Simulated mode without keys (auto-verifies for sandbox); real Razorpay activates when `RAZORPAY_KEY_ID` + `RAZORPAY_KEY_SECRET` added.
- **Notifications module** (`/app/backend/notifications.py`): Twilio SMS, Twilio WhatsApp Business templates, SendGrid email. Templates: order_placed, order_status, otp. Fail-soft mock mode logs to console; real wires up when `TWILIO_*` / `SENDGRID_*` env vars set. Auto-fired on order create + status update.
- **Notification prefs**: `PUT /api/notifications/prefs` for per-user sms/whatsapp/email toggles.
- **Law-firm multi-user seats**: `/api/firms` (create), `/api/firms/me`, `/api/firms/invite` (email via SendGrid), `/api/firms/accept-invite`, `/api/firms/{id}/members/{id}` (remove), `/api/firms/{id}/orders`. Roles: owner, partner, associate, paralegal — permission gates enforced.
- **Delivery partner workflow**: `/api/delivery/queue`, `/api/delivery/{id}/accept`, `/api/delivery/{id}/location` (lat/lng ping), `/api/delivery/{id}/complete` (OTP `123456` confirmation). Stubs for Dunzo/Borzo via env vars.
- **Document Intelligence**: `/api/doc-intel/analyze` — Claude Sonnet 4.6 returns JSON report with filing_readiness_score, ocr_quality_score, pagination_score, missing_documents[], defects[{severity, issue, fix}], recommended_services[], summary. Stored in `doc_intel_reports`.
- **Sponsored Vendor Listings**: `/api/vendors/sponsored/plan` (₹999/30 days), `/api/vendors/sponsored/activate`. Sponsored vendors get priority in `create_order` auto-matching algorithm.

### Frontend
- **OrderWizard**: defaults state to Delhi; unserviceable courts shown disabled "(Coming soon)" in Select with explanatory pill; new Doc Intelligence panel with "Analyze" CTA — shows 3 score gauges (filing/OCR/pagination), summary, defects with severity icons, missing docs list, AI-recommended services chips.
- **OrderDetail**: dual payment buttons (Stripe + Razorpay), Razorpay SDK loaded via CDN, simulated mode notice; supports real Razorpay popup when keys are configured.
- **CourtDirectory**: Serviceable/Coming Soon badges per court, defaults to Delhi.
- **VendorDashboard**: Sponsored Listing promo card (CTA: activate ₹999/mo) or active-status gradient card with expiry; Sponsored badge in header.
- **New pages**: `FirmManagement.jsx` (create firm + invite members + roles), `DeliveryHub.jsx` (queue + accept + location ping + OTP complete), `NotificationPrefs.jsx` (channel toggles with LIVE/MOCK status badges).
- **AppLayout nav**: added Law Firm, Notifications nav items for advocate role; Delivery for delivery_partner role.
- **Razorpay checkout script** loaded in `public/index.html`.

### Testing
- **57/58 backend tests passed** (1 failure was pre-existing AI streaming timeout, unrelated).
- New tests added to `/app/backend/tests/test_courtbazaar_api.py`.

## Deferred (Future P2)
- Real OCR (currently AI-simulated via Claude). Add tesseract + PyPDF2 + pdf2image if needed.
- Real map embed for delivery tracking (currently lat/lng text display)
- WhatsApp template approval flow in admin console
- Stripe ↔ Razorpay reconciliation reports

## Iteration 3 — P2 Polish (2026-02-XX)

### Backend
- **Real OCR pipeline** (`/app/backend/ocr_engine.py`): Tesseract 5.3.0 + PyPDF2 + pdf2image + Pillow. `analyze_document()` extracts text layer from PDFs (PyPDF2), falls back to Tesseract OCR on scanned PDFs (pdf2image @ 150dpi, max 5 pages), and runs Tesseract directly on images. Returns text, page_count, has_text_layer, char_count, ocr_used, page_numbers_detected (regex heuristic).
- **Doc Intelligence v2** (`/api/doc-intel/analyze`): now runs real OCR first, feeds extracted text + metadata into Claude for scoring. Heuristic fallback computes filing_readiness/OCR quality/pagination scores from OCR metrics when Claude fails. Response includes `extracted.{total_pages, ocr_used, text_layer_count, page_numbers_detected, files[]}`.
- **Reconciliation report**: `GET /api/admin/reconciliation` returns rows[], totals (Stripe/Razorpay paid+pending+failed counts + amounts), mismatches (txn vs order payment_status). Filters: `gateway`, `status_filter`, `from_date`, `to_date`. `GET /api/admin/reconciliation/export` returns CSV download.
- **WhatsApp template approval workflow**: `GET/POST/DELETE /api/admin/whatsapp-templates`. Status lifecycle: draft → submit → pending → approved/rejected. History array tracks every action with timestamp + user. Seeds 4 defaults (order_placed_v1, order_status_v1, otp_login_v1, delivery_otp_v1). Twilio SID populated when real keys exist.

### Frontend
- **AdminReconciliation page** (`/admin/reconciliation`): totals cards (Stripe/Razorpay/combined), filters by gateway + status, mismatch alert card, transaction table with mismatch highlighting (red rows + "⚠ MISMATCH" pill), CSV export button.
- **AdminWhatsAppTemplates page** (`/admin/whatsapp`): tabs (all/draft/pending/approved/rejected), create-template dialog (name, category, language, body with `{{n}}` variables, vars list), per-template actions (Submit/Approve/Reject/Delete), reject-with-reason dialog, variable badges, Twilio SID display, expandable history log.
- **OrderWizard Doc Intel** now shows real OCR scores (filing readiness, OCR quality, pagination) derived from actual document content.
- **AppLayout nav**: added Reconciliation + WhatsApp Templates entries for admin role.

### Testing
- 18/18 new tests pass · 75/76 full backend suite (1 pre-existing AI streaming timeout, unrelated)
- Tests installed reportlab for PDF generation; PIL for image OCR test

## Iteration 4 — Compliance, Performance & Scale (2026-02-XX)

### Backend
- **Bulk Order CSV Import** for law firms (`/api/firms/bulk-import` + `/template`): CSV columns `matter_name, service_ids (semicolon-sep), qty_each (semicolon-sep), court_id, delivery_option, urgent, delivery_address, notes`. Owner/Partner-only. Each row creates one order tagged with same `firm_id` + unique `matter_id` + `matter_name`. Returns per-row success/error summary + total_amount. Auto-matches sponsored vendors. Enforces serviceability.
- **Audit log** (`/app/backend/audit_log.py`): `log_audit()` helper writes to `audit_log` collection with action, user_id, IP, user_agent, details, timestamp. Auto-fired on `auth.login`, `order.create`, `order.bulk_import`, `dpdp.*`. 40+ canonical actions defined.
- **DPDP Act 2023 compliance**:
  - `/api/dpdp/my-data` (preview) + `/my-data/download` (JSON attachment) — full PII bundle: profile + vendor_profile + orders + files + wallet + payments + AI messages + audit log
  - `/api/dpdp/request-deletion` (user) + `/api/admin/dpdp/requests` + `/execute` (admin) — anonymises user (name/email/phone/PII wiped), retains order/payment records for legal compliance (CrPC + GST 5-year retention).
  - `get_current_user` now checks `user.deleted=true` and revokes JWTs immediately (bug fixed in iter 5).
- **Admin compliance report** (`/api/admin/compliance-report`): audit count, total/deleted users, pending/executed deletion requests, top actions, `dpdp_compliant:true`, `data_retention_policy_days:1825`.
- **Vendor SLA + Leaderboard** (`/app/backend/vendor_sla.py`): composite score (on-time 35% + completion 25% + rating 25% + dispute-free 15%), grades A+/A/B/C/D, avg turnaround, on-time rate, dispute rate, revenue.
  - `/api/admin/leaderboard` — sorted ranking
  - `/api/vendors/me/sla` — own SLA card for vendor
  - `/api/vendors/{id}/sla` — admin or self-only

### Frontend
- **BulkImport page** (`/firm/bulk-import`): downloadable CSV template, drag-drop upload, per-row success/error result table with order_id links and total amount summary card.
- **AdminAuditLog page** (`/admin/audit-log`): compliance metrics (audit entries / users / deletions / retention days), DPDP-compliant pill, filters (action + user_id), full audit table with timestamp/action/user/IP/details.
- **MyData page** (`/my-data`): DPDP rights — preview data summary (counts per category), download JSON bundle, request deletion dialog with reason capture.
- **AdminLeaderboard page** (`/admin/leaderboard`): Top-3 podium cards (gold/silver/bronze with Crown/Award/Trophy icons + SLA grade badges), full ranked table with all KPIs, sponsored crown indicator.
- **VendorDashboard SLA scorecard**: top-of-page composite score + grade badge + 4 KPI tiles (on-time/avg TAT/rating/dispute rate).
- **AppLayout nav**: added Bulk Import, My Data for advocates; Leaderboard, Audit Log for admin.

### Testing
- 25/26 iteration-4 tests passed first run + 3/3 iteration-5 bug-fix tests passed
- 1 real bug found by tester: deleted users' JWTs stayed valid — **fixed** in get_current_user (now checks user.deleted)
- Full suite: 103/104 (1 pre-existing AI streaming timeout, unrelated)

### Total iterations
- iter1: 37/38 (MVP) · iter2: 22/22 (P1) · iter3: 18/18 (P2 polish) · iter4+5: 28/29 (compliance/SLA)
- Cumulative: 105/107 backend tests passing across 4 development iterations
