"""Static registry of popular G2 software categories."""

G2_CATEGORIES = [
    # Sales
    {"slug": "sales-intelligence", "name": "Sales Intelligence", "parent": "Sales", "estimated_products": 250},
    {"slug": "crm", "name": "CRM", "parent": "Sales", "estimated_products": 300},
    {"slug": "sales-engagement", "name": "Sales Engagement", "parent": "Sales", "estimated_products": 180},
    {"slug": "sales-enablement", "name": "Sales Enablement", "parent": "Sales", "estimated_products": 150},
    {"slug": "lead-intelligence", "name": "Lead Intelligence", "parent": "Sales", "estimated_products": 120},
    {"slug": "configure-price-quote-cpq", "name": "Configure, Price, Quote (CPQ)", "parent": "Sales", "estimated_products": 80},
    {"slug": "sales-analytics", "name": "Sales Analytics", "parent": "Sales", "estimated_products": 100},
    {"slug": "sales-coaching", "name": "Sales Coaching", "parent": "Sales", "estimated_products": 70},
    {"slug": "conversation-intelligence", "name": "Conversation Intelligence", "parent": "Sales", "estimated_products": 90},
    {"slug": "outbound-call-tracking", "name": "Outbound Call Tracking", "parent": "Sales", "estimated_products": 60},
    {"slug": "lead-capture", "name": "Lead Capture", "parent": "Sales", "estimated_products": 140},
    {"slug": "lead-scoring", "name": "Lead Scoring", "parent": "Sales", "estimated_products": 75},
    {"slug": "sales-compensation", "name": "Sales Compensation", "parent": "Sales", "estimated_products": 50},
    {"slug": "proposal", "name": "Proposal", "parent": "Sales", "estimated_products": 90},
    {"slug": "contract-management", "name": "Contract Management", "parent": "Sales", "estimated_products": 110},
    {"slug": "e-signature", "name": "E-Signature", "parent": "Sales", "estimated_products": 85},
    {"slug": "sales-acceleration", "name": "Sales Acceleration", "parent": "Sales", "estimated_products": 65},
    {"slug": "buyer-intent-data-tools", "name": "Buyer Intent Data Tools", "parent": "Sales", "estimated_products": 55},
    {"slug": "linkedin-automation", "name": "LinkedIn Automation", "parent": "Sales", "estimated_products": 40},
    {"slug": "social-selling", "name": "Social Selling", "parent": "Sales", "estimated_products": 50},

    # Marketing
    {"slug": "marketing-automation", "name": "Marketing Automation", "parent": "Marketing", "estimated_products": 180},
    {"slug": "email-marketing", "name": "Email Marketing", "parent": "Marketing", "estimated_products": 250},
    {"slug": "social-media-management", "name": "Social Media Management", "parent": "Marketing", "estimated_products": 200},
    {"slug": "seo-tools", "name": "SEO Tools", "parent": "Marketing", "estimated_products": 160},
    {"slug": "content-marketing", "name": "Content Marketing", "parent": "Marketing", "estimated_products": 130},
    {"slug": "marketing-analytics", "name": "Marketing Analytics", "parent": "Marketing", "estimated_products": 120},
    {"slug": "account-based-marketing", "name": "Account-Based Marketing", "parent": "Marketing", "estimated_products": 80},
    {"slug": "advertising", "name": "Advertising", "parent": "Marketing", "estimated_products": 110},
    {"slug": "demand-generation", "name": "Demand Generation", "parent": "Marketing", "estimated_products": 70},
    {"slug": "affiliate-marketing", "name": "Affiliate Marketing", "parent": "Marketing", "estimated_products": 90},
    {"slug": "landing-page-builders", "name": "Landing Page Builders", "parent": "Marketing", "estimated_products": 75},
    {"slug": "webinar", "name": "Webinar", "parent": "Marketing", "estimated_products": 60},
    {"slug": "influencer-marketing", "name": "Influencer Marketing", "parent": "Marketing", "estimated_products": 85},
    {"slug": "video-marketing", "name": "Video Marketing", "parent": "Marketing", "estimated_products": 70},
    {"slug": "public-relations", "name": "Public Relations", "parent": "Marketing", "estimated_products": 50},
    {"slug": "brand-management", "name": "Brand Management", "parent": "Marketing", "estimated_products": 55},
    {"slug": "marketing-resource-management", "name": "Marketing Resource Management", "parent": "Marketing", "estimated_products": 40},
    {"slug": "push-notification", "name": "Push Notification", "parent": "Marketing", "estimated_products": 45},
    {"slug": "sms-marketing", "name": "SMS Marketing", "parent": "Marketing", "estimated_products": 65},

    # Customer Service
    {"slug": "help-desk", "name": "Help Desk", "parent": "Customer Service", "estimated_products": 200},
    {"slug": "live-chat", "name": "Live Chat", "parent": "Customer Service", "estimated_products": 180},
    {"slug": "customer-success", "name": "Customer Success", "parent": "Customer Service", "estimated_products": 100},
    {"slug": "customer-experience", "name": "Customer Experience", "parent": "Customer Service", "estimated_products": 90},
    {"slug": "chatbots", "name": "Chatbots", "parent": "Customer Service", "estimated_products": 150},
    {"slug": "knowledge-management", "name": "Knowledge Management", "parent": "Customer Service", "estimated_products": 80},
    {"slug": "customer-self-service", "name": "Customer Self-Service", "parent": "Customer Service", "estimated_products": 60},
    {"slug": "customer-communications-management", "name": "Customer Communications Management", "parent": "Customer Service", "estimated_products": 50},
    {"slug": "complaint-management", "name": "Complaint Management", "parent": "Customer Service", "estimated_products": 40},

    # HR
    {"slug": "hr-management-suites", "name": "HR Management Suites", "parent": "HR", "estimated_products": 150},
    {"slug": "applicant-tracking-systems-ats", "name": "Applicant Tracking Systems (ATS)", "parent": "HR", "estimated_products": 200},
    {"slug": "payroll", "name": "Payroll", "parent": "HR", "estimated_products": 120},
    {"slug": "employee-engagement", "name": "Employee Engagement", "parent": "HR", "estimated_products": 110},
    {"slug": "performance-management", "name": "Performance Management", "parent": "HR", "estimated_products": 100},
    {"slug": "learning-management-system-lms", "name": "Learning Management System (LMS)", "parent": "HR", "estimated_products": 180},
    {"slug": "recruiting", "name": "Recruiting", "parent": "HR", "estimated_products": 160},
    {"slug": "employee-recognition", "name": "Employee Recognition", "parent": "HR", "estimated_products": 70},
    {"slug": "benefits-administration", "name": "Benefits Administration", "parent": "HR", "estimated_products": 60},
    {"slug": "onboarding", "name": "Onboarding", "parent": "HR", "estimated_products": 90},
    {"slug": "time-tracking", "name": "Time Tracking", "parent": "HR", "estimated_products": 130},
    {"slug": "workforce-management", "name": "Workforce Management", "parent": "HR", "estimated_products": 80},
    {"slug": "employee-scheduling", "name": "Employee Scheduling", "parent": "HR", "estimated_products": 65},
    {"slug": "corporate-wellness", "name": "Corporate Wellness", "parent": "HR", "estimated_products": 50},

    # IT & Security
    {"slug": "it-service-management-itsm", "name": "IT Service Management (ITSM)", "parent": "IT & Security", "estimated_products": 120},
    {"slug": "endpoint-protection", "name": "Endpoint Protection", "parent": "IT & Security", "estimated_products": 100},
    {"slug": "network-monitoring", "name": "Network Monitoring", "parent": "IT & Security", "estimated_products": 80},
    {"slug": "identity-management", "name": "Identity Management", "parent": "IT & Security", "estimated_products": 90},
    {"slug": "vulnerability-management", "name": "Vulnerability Management", "parent": "IT & Security", "estimated_products": 70},
    {"slug": "siem", "name": "SIEM", "parent": "IT & Security", "estimated_products": 60},
    {"slug": "cloud-security", "name": "Cloud Security", "parent": "IT & Security", "estimated_products": 110},
    {"slug": "backup", "name": "Backup", "parent": "IT & Security", "estimated_products": 100},
    {"slug": "password-manager", "name": "Password Manager", "parent": "IT & Security", "estimated_products": 50},
    {"slug": "vpn", "name": "VPN", "parent": "IT & Security", "estimated_products": 45},
    {"slug": "mdm", "name": "Mobile Device Management (MDM)", "parent": "IT & Security", "estimated_products": 55},
    {"slug": "remote-desktop", "name": "Remote Desktop", "parent": "IT & Security", "estimated_products": 60},
    {"slug": "it-asset-management", "name": "IT Asset Management", "parent": "IT & Security", "estimated_products": 75},
    {"slug": "penetration-testing", "name": "Penetration Testing", "parent": "IT & Security", "estimated_products": 40},
    {"slug": "privileged-access-management", "name": "Privileged Access Management", "parent": "IT & Security", "estimated_products": 35},

    # Development
    {"slug": "integrated-development-environment-ide", "name": "Integrated Development Environment (IDE)", "parent": "Development", "estimated_products": 80},
    {"slug": "application-performance-monitoring-apm", "name": "Application Performance Monitoring (APM)", "parent": "Development", "estimated_products": 70},
    {"slug": "bug-tracking", "name": "Bug Tracking", "parent": "Development", "estimated_products": 90},
    {"slug": "source-code-management", "name": "Source Code Management", "parent": "Development", "estimated_products": 50},
    {"slug": "continuous-integration", "name": "Continuous Integration", "parent": "Development", "estimated_products": 60},
    {"slug": "continuous-delivery", "name": "Continuous Delivery", "parent": "Development", "estimated_products": 55},
    {"slug": "api-management", "name": "API Management", "parent": "Development", "estimated_products": 80},
    {"slug": "low-code-development-platforms", "name": "Low-Code Development Platforms", "parent": "Development", "estimated_products": 110},
    {"slug": "no-code-development-platforms", "name": "No-Code Development Platforms", "parent": "Development", "estimated_products": 100},
    {"slug": "web-hosting", "name": "Web Hosting", "parent": "Development", "estimated_products": 120},
    {"slug": "containerization", "name": "Containerization", "parent": "Development", "estimated_products": 40},
    {"slug": "infrastructure-as-a-service-iaas", "name": "Infrastructure as a Service (IaaS)", "parent": "Development", "estimated_products": 35},
    {"slug": "platform-as-a-service-paas", "name": "Platform as a Service (PaaS)", "parent": "Development", "estimated_products": 45},
    {"slug": "static-application-security-testing-sast", "name": "Static Application Security Testing (SAST)", "parent": "Development", "estimated_products": 30},

    # Finance & Accounting
    {"slug": "accounting", "name": "Accounting", "parent": "Finance", "estimated_products": 200},
    {"slug": "expense-management", "name": "Expense Management", "parent": "Finance", "estimated_products": 100},
    {"slug": "invoicing", "name": "Invoicing", "parent": "Finance", "estimated_products": 120},
    {"slug": "billing", "name": "Billing", "parent": "Finance", "estimated_products": 90},
    {"slug": "subscription-management", "name": "Subscription Management", "parent": "Finance", "estimated_products": 70},
    {"slug": "financial-close", "name": "Financial Close", "parent": "Finance", "estimated_products": 40},
    {"slug": "corporate-tax", "name": "Corporate Tax", "parent": "Finance", "estimated_products": 35},
    {"slug": "budgeting-and-forecasting", "name": "Budgeting and Forecasting", "parent": "Finance", "estimated_products": 60},
    {"slug": "accounts-payable", "name": "Accounts Payable", "parent": "Finance", "estimated_products": 55},
    {"slug": "accounts-receivable", "name": "Accounts Receivable", "parent": "Finance", "estimated_products": 45},
    {"slug": "procurement", "name": "Procurement", "parent": "Finance", "estimated_products": 80},
    {"slug": "spend-management", "name": "Spend Management", "parent": "Finance", "estimated_products": 50},
    {"slug": "payment-processing", "name": "Payment Processing", "parent": "Finance", "estimated_products": 110},

    # Collaboration & Productivity
    {"slug": "project-management", "name": "Project Management", "parent": "Collaboration", "estimated_products": 250},
    {"slug": "video-conferencing", "name": "Video Conferencing", "parent": "Collaboration", "estimated_products": 100},
    {"slug": "team-collaboration", "name": "Team Collaboration", "parent": "Collaboration", "estimated_products": 130},
    {"slug": "document-management", "name": "Document Management", "parent": "Collaboration", "estimated_products": 120},
    {"slug": "task-management", "name": "Task Management", "parent": "Collaboration", "estimated_products": 110},
    {"slug": "business-instant-messaging", "name": "Business Instant Messaging", "parent": "Collaboration", "estimated_products": 60},
    {"slug": "whiteboard", "name": "Whiteboard", "parent": "Collaboration", "estimated_products": 40},
    {"slug": "note-taking-management", "name": "Note-Taking Management", "parent": "Collaboration", "estimated_products": 50},
    {"slug": "screen-sharing", "name": "Screen Sharing", "parent": "Collaboration", "estimated_products": 35},
    {"slug": "cloud-storage", "name": "Cloud Storage", "parent": "Collaboration", "estimated_products": 80},
    {"slug": "online-form-builder", "name": "Online Form Builder", "parent": "Collaboration", "estimated_products": 75},
    {"slug": "survey", "name": "Survey", "parent": "Collaboration", "estimated_products": 90},
    {"slug": "digital-signature", "name": "Digital Signature", "parent": "Collaboration", "estimated_products": 55},
    {"slug": "mind-mapping", "name": "Mind Mapping", "parent": "Collaboration", "estimated_products": 30},
    {"slug": "presentation", "name": "Presentation", "parent": "Collaboration", "estimated_products": 50},
    {"slug": "work-management", "name": "Work Management", "parent": "Collaboration", "estimated_products": 70},

    # Analytics & BI
    {"slug": "business-intelligence-bi", "name": "Business Intelligence (BI)", "parent": "Analytics", "estimated_products": 150},
    {"slug": "data-visualization", "name": "Data Visualization", "parent": "Analytics", "estimated_products": 80},
    {"slug": "embedded-analytics", "name": "Embedded Analytics", "parent": "Analytics", "estimated_products": 60},
    {"slug": "data-integration", "name": "Data Integration", "parent": "Analytics", "estimated_products": 90},
    {"slug": "etl-tools", "name": "ETL Tools", "parent": "Analytics", "estimated_products": 70},
    {"slug": "data-warehouse", "name": "Data Warehouse", "parent": "Analytics", "estimated_products": 50},
    {"slug": "data-quality", "name": "Data Quality", "parent": "Analytics", "estimated_products": 40},
    {"slug": "data-catalog", "name": "Data Catalog", "parent": "Analytics", "estimated_products": 35},
    {"slug": "predictive-analytics", "name": "Predictive Analytics", "parent": "Analytics", "estimated_products": 45},
    {"slug": "web-analytics", "name": "Web Analytics", "parent": "Analytics", "estimated_products": 100},
    {"slug": "product-analytics", "name": "Product Analytics", "parent": "Analytics", "estimated_products": 55},
    {"slug": "customer-data-platform-cdp", "name": "Customer Data Platform (CDP)", "parent": "Analytics", "estimated_products": 65},

    # AI & Automation
    {"slug": "ai-writing-assistant", "name": "AI Writing Assistant", "parent": "AI", "estimated_products": 120},
    {"slug": "ai-chatbots", "name": "AI Chatbots", "parent": "AI", "estimated_products": 100},
    {"slug": "ai-code-assistants", "name": "AI Code Assistants", "parent": "AI", "estimated_products": 50},
    {"slug": "machine-learning", "name": "Machine Learning", "parent": "AI", "estimated_products": 80},
    {"slug": "robotic-process-automation-rpa", "name": "Robotic Process Automation (RPA)", "parent": "AI", "estimated_products": 70},
    {"slug": "intelligent-document-processing-idp", "name": "Intelligent Document Processing (IDP)", "parent": "AI", "estimated_products": 40},
    {"slug": "text-analysis", "name": "Text Analysis", "parent": "AI", "estimated_products": 35},
    {"slug": "speech-analytics", "name": "Speech Analytics", "parent": "AI", "estimated_products": 30},
    {"slug": "ai-meeting-assistants", "name": "AI Meeting Assistants", "parent": "AI", "estimated_products": 45},
    {"slug": "generative-ai-tools", "name": "Generative AI Tools", "parent": "AI", "estimated_products": 90},

    # E-Commerce
    {"slug": "e-commerce-platforms", "name": "E-Commerce Platforms", "parent": "E-Commerce", "estimated_products": 150},
    {"slug": "shopping-cart", "name": "Shopping Cart", "parent": "E-Commerce", "estimated_products": 60},
    {"slug": "order-management", "name": "Order Management", "parent": "E-Commerce", "estimated_products": 70},
    {"slug": "product-information-management-pim", "name": "Product Information Management (PIM)", "parent": "E-Commerce", "estimated_products": 40},
    {"slug": "personalization", "name": "Personalization", "parent": "E-Commerce", "estimated_products": 55},
    {"slug": "shipping", "name": "Shipping", "parent": "E-Commerce", "estimated_products": 65},

    # Design & Creative
    {"slug": "graphic-design", "name": "Graphic Design", "parent": "Design", "estimated_products": 80},
    {"slug": "video-editing", "name": "Video Editing", "parent": "Design", "estimated_products": 70},
    {"slug": "screen-recording", "name": "Screen Recording", "parent": "Design", "estimated_products": 40},
    {"slug": "digital-asset-management", "name": "Digital Asset Management", "parent": "Design", "estimated_products": 60},
    {"slug": "prototyping", "name": "Prototyping", "parent": "Design", "estimated_products": 35},
    {"slug": "website-builder", "name": "Website Builder", "parent": "Design", "estimated_products": 100},
    {"slug": "photo-editing", "name": "Photo Editing", "parent": "Design", "estimated_products": 50},

    # Legal & Compliance
    {"slug": "legal-practice-management", "name": "Legal Practice Management", "parent": "Legal", "estimated_products": 50},
    {"slug": "data-privacy", "name": "Data Privacy", "parent": "Legal", "estimated_products": 60},
    {"slug": "governance-risk-compliance", "name": "Governance, Risk & Compliance", "parent": "Legal", "estimated_products": 70},
    {"slug": "contract-lifecycle-management-clm", "name": "Contract Lifecycle Management (CLM)", "parent": "Legal", "estimated_products": 55},

    # ERP & Operations
    {"slug": "erp-systems", "name": "ERP Systems", "parent": "Operations", "estimated_products": 100},
    {"slug": "supply-chain-management", "name": "Supply Chain Management", "parent": "Operations", "estimated_products": 60},
    {"slug": "inventory-management", "name": "Inventory Management", "parent": "Operations", "estimated_products": 90},
    {"slug": "warehouse-management", "name": "Warehouse Management", "parent": "Operations", "estimated_products": 50},
    {"slug": "fleet-management", "name": "Fleet Management", "parent": "Operations", "estimated_products": 40},
    {"slug": "field-service-management", "name": "Field Service Management", "parent": "Operations", "estimated_products": 55},

    # Healthcare
    {"slug": "electronic-health-records-ehr", "name": "Electronic Health Records (EHR)", "parent": "Healthcare", "estimated_products": 80},
    {"slug": "practice-management", "name": "Practice Management", "parent": "Healthcare", "estimated_products": 60},
    {"slug": "telehealth", "name": "Telehealth", "parent": "Healthcare", "estimated_products": 70},
    {"slug": "medical-billing", "name": "Medical Billing", "parent": "Healthcare", "estimated_products": 45},

    # Real Estate & Construction
    {"slug": "real-estate-crm", "name": "Real Estate CRM", "parent": "Real Estate", "estimated_products": 40},
    {"slug": "property-management", "name": "Property Management", "parent": "Real Estate", "estimated_products": 60},
    {"slug": "construction-management", "name": "Construction Management", "parent": "Real Estate", "estimated_products": 50},

    # Education
    {"slug": "course-authoring", "name": "Course Authoring", "parent": "Education", "estimated_products": 50},
    {"slug": "student-information-system-sis", "name": "Student Information System (SIS)", "parent": "Education", "estimated_products": 35},
    {"slug": "online-tutoring", "name": "Online Tutoring", "parent": "Education", "estimated_products": 30},
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
