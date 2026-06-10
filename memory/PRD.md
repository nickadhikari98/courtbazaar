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
