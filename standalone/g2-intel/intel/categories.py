"""Static registry of popular G2 software categories."""

G2_CATEGORIES = [
    # Sales
    {"slug": "sales-intelligence", "name": "Sales Intelligence", "parent": "Sales"},
    {"slug": "crm", "name": "CRM", "parent": "Sales"},
    {"slug": "sales-engagement", "name": "Sales Engagement", "parent": "Sales"},
    {"slug": "sales-enablement", "name": "Sales Enablement", "parent": "Sales"},
    {"slug": "lead-intelligence", "name": "Lead Intelligence", "parent": "Sales"},
    {"slug": "configure-price-quote-cpq", "name": "Configure, Price, Quote (CPQ)", "parent": "Sales"},
    {"slug": "sales-analytics", "name": "Sales Analytics", "parent": "Sales"},
    {"slug": "sales-coaching", "name": "Sales Coaching", "parent": "Sales"},
    {"slug": "conversation-intelligence", "name": "Conversation Intelligence", "parent": "Sales"},
    {"slug": "outbound-call-tracking", "name": "Outbound Call Tracking", "parent": "Sales"},
    {"slug": "lead-capture", "name": "Lead Capture", "parent": "Sales"},
    {"slug": "lead-scoring", "name": "Lead Scoring", "parent": "Sales"},
    {"slug": "sales-compensation", "name": "Sales Compensation", "parent": "Sales"},
    {"slug": "proposal", "name": "Proposal", "parent": "Sales"},
    {"slug": "contract-management", "name": "Contract Management", "parent": "Sales"},
    {"slug": "e-signature", "name": "E-Signature", "parent": "Sales"},
    {"slug": "sales-acceleration", "name": "Sales Acceleration", "parent": "Sales"},
    {"slug": "buyer-intent-data-tools", "name": "Buyer Intent Data Tools", "parent": "Sales"},
    {"slug": "linkedin-automation", "name": "LinkedIn Automation", "parent": "Sales"},
    {"slug": "social-selling", "name": "Social Selling", "parent": "Sales"},

    # Marketing
    {"slug": "marketing-automation", "name": "Marketing Automation", "parent": "Marketing"},
    {"slug": "email-marketing", "name": "Email Marketing", "parent": "Marketing"},
    {"slug": "social-media-management", "name": "Social Media Management", "parent": "Marketing"},
    {"slug": "seo-tools", "name": "SEO Tools", "parent": "Marketing"},
    {"slug": "content-marketing", "name": "Content Marketing", "parent": "Marketing"},
    {"slug": "marketing-analytics", "name": "Marketing Analytics", "parent": "Marketing"},
    {"slug": "account-based-marketing", "name": "Account-Based Marketing", "parent": "Marketing"},
    {"slug": "advertising", "name": "Advertising", "parent": "Marketing"},
    {"slug": "demand-generation", "name": "Demand Generation", "parent": "Marketing"},
    {"slug": "affiliate-marketing", "name": "Affiliate Marketing", "parent": "Marketing"},
    {"slug": "landing-page-builders", "name": "Landing Page Builders", "parent": "Marketing"},
    {"slug": "webinar", "name": "Webinar", "parent": "Marketing"},
    {"slug": "influencer-marketing", "name": "Influencer Marketing", "parent": "Marketing"},
    {"slug": "video-marketing", "name": "Video Marketing", "parent": "Marketing"},
    {"slug": "public-relations", "name": "Public Relations", "parent": "Marketing"},
    {"slug": "brand-management", "name": "Brand Management", "parent": "Marketing"},
    {"slug": "marketing-resource-management", "name": "Marketing Resource Management", "parent": "Marketing"},
    {"slug": "push-notification", "name": "Push Notification", "parent": "Marketing"},
    {"slug": "sms-marketing", "name": "SMS Marketing", "parent": "Marketing"},

    # Customer Service
    {"slug": "help-desk", "name": "Help Desk", "parent": "Customer Service"},
    {"slug": "live-chat", "name": "Live Chat", "parent": "Customer Service"},
    {"slug": "customer-success", "name": "Customer Success", "parent": "Customer Service"},
    {"slug": "customer-experience", "name": "Customer Experience", "parent": "Customer Service"},
    {"slug": "chatbots", "name": "Chatbots", "parent": "Customer Service"},
    {"slug": "knowledge-management", "name": "Knowledge Management", "parent": "Customer Service"},
    {"slug": "customer-self-service", "name": "Customer Self-Service", "parent": "Customer Service"},
    {"slug": "customer-communications-management", "name": "Customer Communications Management", "parent": "Customer Service"},
    {"slug": "complaint-management", "name": "Complaint Management", "parent": "Customer Service"},

    # HR
    {"slug": "hr-management-suites", "name": "HR Management Suites", "parent": "HR"},
    {"slug": "applicant-tracking-systems-ats", "name": "Applicant Tracking Systems (ATS)", "parent": "HR"},
    {"slug": "payroll", "name": "Payroll", "parent": "HR"},
    {"slug": "employee-engagement", "name": "Employee Engagement", "parent": "HR"},
    {"slug": "performance-management", "name": "Performance Management", "parent": "HR"},
    {"slug": "learning-management-system-lms", "name": "Learning Management System (LMS)", "parent": "HR"},
    {"slug": "recruiting", "name": "Recruiting", "parent": "HR"},
    {"slug": "employee-recognition", "name": "Employee Recognition", "parent": "HR"},
    {"slug": "benefits-administration", "name": "Benefits Administration", "parent": "HR"},
    {"slug": "onboarding", "name": "Onboarding", "parent": "HR"},
    {"slug": "time-tracking", "name": "Time Tracking", "parent": "HR"},
    {"slug": "workforce-management", "name": "Workforce Management", "parent": "HR"},
    {"slug": "employee-scheduling", "name": "Employee Scheduling", "parent": "HR"},
    {"slug": "corporate-wellness", "name": "Corporate Wellness", "parent": "HR"},

    # IT & Security
    {"slug": "it-service-management-itsm", "name": "IT Service Management (ITSM)", "parent": "IT & Security"},
    {"slug": "endpoint-protection", "name": "Endpoint Protection", "parent": "IT & Security"},
    {"slug": "network-monitoring", "name": "Network Monitoring", "parent": "IT & Security"},
    {"slug": "identity-management", "name": "Identity Management", "parent": "IT & Security"},
    {"slug": "vulnerability-management", "name": "Vulnerability Management", "parent": "IT & Security"},
    {"slug": "siem", "name": "SIEM", "parent": "IT & Security"},
    {"slug": "cloud-security", "name": "Cloud Security", "parent": "IT & Security"},
    {"slug": "backup", "name": "Backup", "parent": "IT & Security"},
    {"slug": "password-manager", "name": "Password Manager", "parent": "IT & Security"},
    {"slug": "vpn", "name": "VPN", "parent": "IT & Security"},
    {"slug": "mdm", "name": "Mobile Device Management (MDM)", "parent": "IT & Security"},
    {"slug": "remote-desktop", "name": "Remote Desktop", "parent": "IT & Security"},
    {"slug": "it-asset-management", "name": "IT Asset Management", "parent": "IT & Security"},
    {"slug": "penetration-testing", "name": "Penetration Testing", "parent": "IT & Security"},
    {"slug": "privileged-access-management", "name": "Privileged Access Management", "parent": "IT & Security"},

    # Development
    {"slug": "integrated-development-environment-ide", "name": "Integrated Development Environment (IDE)", "parent": "Development"},
    {"slug": "application-performance-monitoring-apm", "name": "Application Performance Monitoring (APM)", "parent": "Development"},
    {"slug": "bug-tracking", "name": "Bug Tracking", "parent": "Development"},
    {"slug": "source-code-management", "name": "Source Code Management", "parent": "Development"},
    {"slug": "continuous-integration", "name": "Continuous Integration", "parent": "Development"},
    {"slug": "continuous-delivery", "name": "Continuous Delivery", "parent": "Development"},
    {"slug": "api-management", "name": "API Management", "parent": "Development"},
    {"slug": "low-code-development-platforms", "name": "Low-Code Development Platforms", "parent": "Development"},
    {"slug": "no-code-development-platforms", "name": "No-Code Development Platforms", "parent": "Development"},
    {"slug": "web-hosting", "name": "Web Hosting", "parent": "Development"},
    {"slug": "containerization", "name": "Containerization", "parent": "Development"},
    {"slug": "infrastructure-as-a-service-iaas", "name": "Infrastructure as a Service (IaaS)", "parent": "Development"},
    {"slug": "platform-as-a-service-paas", "name": "Platform as a Service (PaaS)", "parent": "Development"},
    {"slug": "static-application-security-testing-sast", "name": "Static Application Security Testing (SAST)", "parent": "Development"},

    # Finance & Accounting
    {"slug": "accounting", "name": "Accounting", "parent": "Finance"},
    {"slug": "expense-management", "name": "Expense Management", "parent": "Finance"},
    {"slug": "invoicing", "name": "Invoicing", "parent": "Finance"},
    {"slug": "billing", "name": "Billing", "parent": "Finance"},
    {"slug": "subscription-management", "name": "Subscription Management", "parent": "Finance"},
    {"slug": "financial-close", "name": "Financial Close", "parent": "Finance"},
    {"slug": "corporate-tax", "name": "Corporate Tax", "parent": "Finance"},
    {"slug": "budgeting-and-forecasting", "name": "Budgeting and Forecasting", "parent": "Finance"},
    {"slug": "accounts-payable", "name": "Accounts Payable", "parent": "Finance"},
    {"slug": "accounts-receivable", "name": "Accounts Receivable", "parent": "Finance"},
    {"slug": "procurement", "name": "Procurement", "parent": "Finance"},
    {"slug": "spend-management", "name": "Spend Management", "parent": "Finance"},
    {"slug": "payment-processing", "name": "Payment Processing", "parent": "Finance"},

    # Collaboration & Productivity
    {"slug": "project-management", "name": "Project Management", "parent": "Collaboration"},
    {"slug": "video-conferencing", "name": "Video Conferencing", "parent": "Collaboration"},
    {"slug": "team-collaboration", "name": "Team Collaboration", "parent": "Collaboration"},
    {"slug": "document-management", "name": "Document Management", "parent": "Collaboration"},
    {"slug": "task-management", "name": "Task Management", "parent": "Collaboration"},
    {"slug": "business-instant-messaging", "name": "Business Instant Messaging", "parent": "Collaboration"},
    {"slug": "whiteboard", "name": "Whiteboard", "parent": "Collaboration"},
    {"slug": "note-taking-management", "name": "Note-Taking Management", "parent": "Collaboration"},
    {"slug": "screen-sharing", "name": "Screen Sharing", "parent": "Collaboration"},
    {"slug": "cloud-storage", "name": "Cloud Storage", "parent": "Collaboration"},
    {"slug": "online-form-builder", "name": "Online Form Builder", "parent": "Collaboration"},
    {"slug": "survey", "name": "Survey", "parent": "Collaboration"},
    {"slug": "digital-signature", "name": "Digital Signature", "parent": "Collaboration"},
    {"slug": "mind-mapping", "name": "Mind Mapping", "parent": "Collaboration"},
    {"slug": "presentation", "name": "Presentation", "parent": "Collaboration"},
    {"slug": "work-management", "name": "Work Management", "parent": "Collaboration"},

    # Analytics & BI
    {"slug": "business-intelligence-bi", "name": "Business Intelligence (BI)", "parent": "Analytics"},
    {"slug": "data-visualization", "name": "Data Visualization", "parent": "Analytics"},
    {"slug": "embedded-analytics", "name": "Embedded Analytics", "parent": "Analytics"},
    {"slug": "data-integration", "name": "Data Integration", "parent": "Analytics"},
    {"slug": "etl-tools", "name": "ETL Tools", "parent": "Analytics"},
    {"slug": "data-warehouse", "name": "Data Warehouse", "parent": "Analytics"},
    {"slug": "data-quality", "name": "Data Quality", "parent": "Analytics"},
    {"slug": "data-catalog", "name": "Data Catalog", "parent": "Analytics"},
    {"slug": "predictive-analytics", "name": "Predictive Analytics", "parent": "Analytics"},
    {"slug": "web-analytics", "name": "Web Analytics", "parent": "Analytics"},
    {"slug": "product-analytics", "name": "Product Analytics", "parent": "Analytics"},
    {"slug": "customer-data-platform-cdp", "name": "Customer Data Platform (CDP)", "parent": "Analytics"},

    # AI & Automation
    {"slug": "ai-writing-assistant", "name": "AI Writing Assistant", "parent": "AI"},
    {"slug": "ai-chatbots", "name": "AI Chatbots", "parent": "AI"},
    {"slug": "ai-code-assistants", "name": "AI Code Assistants", "parent": "AI"},
    {"slug": "machine-learning", "name": "Machine Learning", "parent": "AI"},
    {"slug": "robotic-process-automation-rpa", "name": "Robotic Process Automation (RPA)", "parent": "AI"},
    {"slug": "intelligent-document-processing-idp", "name": "Intelligent Document Processing (IDP)", "parent": "AI"},
    {"slug": "text-analysis", "name": "Text Analysis", "parent": "AI"},
    {"slug": "speech-analytics", "name": "Speech Analytics", "parent": "AI"},
    {"slug": "ai-meeting-assistants", "name": "AI Meeting Assistants", "parent": "AI"},
    {"slug": "generative-ai-tools", "name": "Generative AI Tools", "parent": "AI"},

    # E-Commerce
    {"slug": "e-commerce-platforms", "name": "E-Commerce Platforms", "parent": "E-Commerce"},
    {"slug": "shopping-cart", "name": "Shopping Cart", "parent": "E-Commerce"},
    {"slug": "order-management", "name": "Order Management", "parent": "E-Commerce"},
    {"slug": "product-information-management-pim", "name": "Product Information Management (PIM)", "parent": "E-Commerce"},
    {"slug": "personalization", "name": "Personalization", "parent": "E-Commerce"},
    {"slug": "shipping", "name": "Shipping", "parent": "E-Commerce"},

    # Design & Creative
    {"slug": "graphic-design", "name": "Graphic Design", "parent": "Design"},
    {"slug": "video-editing", "name": "Video Editing", "parent": "Design"},
    {"slug": "screen-recording", "name": "Screen Recording", "parent": "Design"},
    {"slug": "digital-asset-management", "name": "Digital Asset Management", "parent": "Design"},
    {"slug": "prototyping", "name": "Prototyping", "parent": "Design"},
    {"slug": "website-builder", "name": "Website Builder", "parent": "Design"},
    {"slug": "photo-editing", "name": "Photo Editing", "parent": "Design"},

    # Legal & Compliance
    {"slug": "legal-practice-management", "name": "Legal Practice Management", "parent": "Legal"},
    {"slug": "data-privacy", "name": "Data Privacy", "parent": "Legal"},
    {"slug": "governance-risk-compliance", "name": "Governance, Risk & Compliance", "parent": "Legal"},
    {"slug": "contract-lifecycle-management-clm", "name": "Contract Lifecycle Management (CLM)", "parent": "Legal"},

    # ERP & Operations
    {"slug": "erp-systems", "name": "ERP Systems", "parent": "Operations"},
    {"slug": "supply-chain-management", "name": "Supply Chain Management", "parent": "Operations"},
    {"slug": "inventory-management", "name": "Inventory Management", "parent": "Operations"},
    {"slug": "warehouse-management", "name": "Warehouse Management", "parent": "Operations"},
    {"slug": "fleet-management", "name": "Fleet Management", "parent": "Operations"},
    {"slug": "field-service-management", "name": "Field Service Management", "parent": "Operations"},

    # Healthcare
    {"slug": "electronic-health-records-ehr", "name": "Electronic Health Records (EHR)", "parent": "Healthcare"},
    {"slug": "practice-management", "name": "Practice Management", "parent": "Healthcare"},
    {"slug": "telehealth", "name": "Telehealth", "parent": "Healthcare"},
    {"slug": "medical-billing", "name": "Medical Billing", "parent": "Healthcare"},

    # Real Estate & Construction
    {"slug": "real-estate-crm", "name": "Real Estate CRM", "parent": "Real Estate"},
    {"slug": "property-management", "name": "Property Management", "parent": "Real Estate"},
    {"slug": "construction-management", "name": "Construction Management", "parent": "Real Estate"},

    # Education
    {"slug": "course-authoring", "name": "Course Authoring", "parent": "Education"},
    {"slug": "student-information-system-sis", "name": "Student Information System (SIS)", "parent": "Education"},
    {"slug": "online-tutoring", "name": "Online Tutoring", "parent": "Education"},
]

# Build indexes for fast lookups
_BY_SLUG: dict[str, dict] = {c["slug"]: c for c in G2_CATEGORIES}
_BY_PARENT: dict[str, list[dict]] = {}
for _cat in G2_CATEGORIES:
    _BY_PARENT.setdefault(_cat["parent"], []).append(_cat)


def get_all_categories() -> list[dict]:
    return G2_CATEGORIES


def get_category_by_slug(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)


def get_categories_by_parent(parent: str) -> list[dict]:
    return _BY_PARENT.get(parent, [])


def get_all_parents() -> list[str]:
    return sorted(_BY_PARENT.keys())


def search_categories(query: str) -> list[dict]:
    if not query or not query.strip():
        return G2_CATEGORIES
    q = query.lower().strip()
    return [
        c for c in G2_CATEGORIES
        if q in c["name"].lower() or q in c["slug"] or q in c["parent"].lower()
    ]
