from typing import Dict, List, Optional

RAW_TAXONOMY = {
  "Academic Subjects": [
    "Mathematics",
    "Biology",
    "Chemistry",
    "Physics",
    "Astronomy",
    "Earth Sciences",
    "Environmental Science",
    "Literature",
    "History",
    "Philosophy",
    "Sociology",
    "Anthropology",
    "Economics",
    "Political Science",
    "Geography"
  ],
  "Agriculture & Horticulture": [
    "Farming Techniques",
    "Permaculture",
    "Landscaping",
    "Sustainable Agriculture",
    "Crop & Livestock Management",
    "Urban Farming"
  ],
  "Arts & Crafts": [
    "Drawing",
    "Painting",
    "Sculpture",
    "Pottery",
    "Knitting",
    "Sewing",
    "Jewelry Making",
    "Calligraphy",
    "DIY Projects",
    "Textile Arts",
    "Paper Crafts",
    "Scrapbooking"
  ],
  "Business Operations": [
    "Supply Chain Management",
    "Logistics",
    "Operations Management",
    "Quality Management",
    "Lean Six Sigma",
    "Franchising",
    "Business Process Management",
    "Business Analysis",
    "Environmental, Social & Governance (ESG)"
  ],
  "Career Development & Job Search": [
    "Resume Building",
    "Interview Skills",
    "Networking",
    "Career Planning",
    "Personal Branding",
    "Job Transition",
    "LinkedIn Optimization"
  ],
  "Cloud Computing": [
    "AWS",
    "Azure",
    "Google Cloud Platform",
    "Cloud Certifications",
    "Cloud Security",
    "Cloud Migration",
    "Cloud Development"
  ],
  "Communication Skills": [
    "Public Speaking",
    "Interpersonal Communication",
    "Business Communication",
    "Conflict Resolution",
    "Negotiation",
    "Persuasion",
    "Active Listening"
  ],
  "Cosmetology & Barbering": [
    "Hair Styling",
    "Nail Care",
    "Skincare",
    "Makeup Artistry",
    "Esthetics",
    "Professional Licensing",
    "Hair Removal",
    "Salon Management"
  ],
  "Creative Writing": [
    "Fiction",
    "Non-Fiction",
    "Poetry",
    "Screenwriting",
    "Playwriting",
    "Copywriting",
    "Technical Writing",
    "Journalism",
    "Blogging"
  ],
  "Culinary Arts": [
    "Cooking Techniques",
    "Baking",
    "Pastry",
    "Mixology",
    "Food Science",
    "Restaurant Management",
    "Specific Cuisines",
    "Bartending",
    "Food Photography"
  ],
  "Cybersecurity": [
    "Network Security",
    "Ethical Hacking",
    "Digital Forensics",
    "Information Security Management",
    "Governance, Risk & Compliance (GRC)",
    "Incident Response",
    "Security Operations",
    "Penetration Testing",
    "Cybersecurity Certifications"
  ],
  "Data Science": [
    "Big Data",
    "Machine Learning",
    "Deep Learning",
    "Artificial Intelligence",
    "Business Intelligence",
    "Data Visualization",
    "Data Engineering",
    "Data Analytics",
    "Statistical Modeling",
    "Statistical Analysis",
    "Predictive Analytics",
    "Natural Language Processing",
    "Computer Vision"
  ],
  "Design": [
    "Graphic Design",
    "UI/UX Design",
    "Web Design",
    "Interior Design",
    "Fashion Design",
    "Product Design",
    "Industrial Design",
    "Motion Graphics",
    "Animation",
    "Game Design",
    "Architectural Design",
    "CAD/CAM",
    "Graphic Design & Illustration",
    "3D & Animation",
    "Design Tools",
    "Mobile Design"
  ],
  "Development": [
    "Web Development",
    "Mobile App Development",
    "Game Development",
    "Software Engineering",
    "Programming Languages",
    "Database Design & Development",
    "DevOps",
    "Software Testing",
    "API Development",
    "No Code/Low Code Development",
    "Vibecoding"
  ],
  "E-commerce & Online Business": [
    "Online Store Management",
    "Dropshipping",
    "Affiliate Marketing",
    "Digital Product Creation",
    "Business Automation",
    "Online Retail Strategy",
    "SEO for E-commerce"
  ],
  "Finance & Accounting": [
    "Accounting",
    "Accounting Software",
    "Corporate Finance",
    "Personal Finance",
    "Financial Modeling & Analysis",
    "Investing & Trading",
    "Fintech",
    "Blockchain in Finance"
  ],
  "Education & Pedagogy": [
    "Teaching Methods",
    "Curriculum Development",
    "Educational Psychology",
    "Special Education",
    "Online Course Creation",
    "Classroom Management"
  ],
  "Emerging Technologies": [
    "Blockchain",
    "Quantum Computing",
    "Internet of Things (IoT)",
    "Augmented Reality (AR)",
    "Virtual Reality (VR)",
    "Robotics",
    "Drones",
    "Nanotechnology",
    "Generative AI"
  ],
  "Engineering": [
    "Civil Engineering",
    "Mechanical Engineering",
    "Electrical Engineering",
    "Electronics Engineering",
    "Telecoms Engineering",
    "Industrial Engineering",
    "Petroleum Engineering",
    "Chemical Engineering",
    "Aerospace Engineering",
    "Biomedical Engineering",
    "Environmental Engineering",
    "Structural Engineering"
  ],
  "Environmental Studies & Sustainability": [
    "Ecology",
    "Conservation",
    "Renewable Energy",
    "Climate Change",
    "Sustainable Development",
    "Environmental Policy",
    "Waste Management"
  ],
  "Marketing": [
    "Digital Marketing",
    "Content Marketing",
    "Search Engine Optimization (SEO)",
    "Social Media Marketing",
    "Email Marketing",
    "Brand Management",
    "Product Marketing",
    "Market Research",
    "Paid Advertising",
    "Public Relations",
    "Growth Hacking",
    "Marketing Analytics & Automation",
    "Marketing Strategy"
  ],
  "Project & Product Management": [
    "Agile & Scrum",
    "PMP Certification Prep",
    "Product Ownership",
    "Requirements Gathering",
    "Kanban",
    "Lean Product Development",
    "Project Management",
    "Project Management Tools"
  ],
  "Sales": [
    "Sales Techniques",
    "CRM Software",
    "Negotiation",
    "Lead Generation",
    "Account Management",
    "Cold Calling",
    "B2B Sales",
    "Retail Sales",
    "Customer Success & Customer Service"
  ],
  "Volunteering & Community Engagement": [
    "Non-profit Operations",
    "Fundraising",
    "Volunteer Management"
  ]
}


# 1. Liste plate de toutes les catégories pour le Prompt
ALL_CATEGORIES_FLAT = [cat for categories in RAW_TAXONOMY.values() for cat in categories]
ALL_CATEGORIES_STR = ", ".join([f'"{c}"' for c in ALL_CATEGORIES_FLAT])

# 2. Dictionnaire inversé : Category -> Domain
# Complexité de recherche : O(1) (Instantané)
CATEGORY_TO_DOMAIN: Dict[str, str] = {}
for domain, categories in RAW_TAXONOMY.items():
    for cat in categories:
        CATEGORY_TO_DOMAIN[cat] = domain

def get_domain_from_category(category: str) -> str:
    """Retourne le domaine associé ou 'General' si non trouvé."""
    return CATEGORY_TO_DOMAIN.get(category)