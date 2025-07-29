from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal, Dict, Any
from anthropic import Anthropic, AnthropicError
from weasyprint import HTML
import os
import tempfile
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Universal Business Assessment API")

# CORS configuration
origins = [
    "https://beamxsolutions.com",  # frontend on Netlify
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Anthropic client with API key from environment variable
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# --- Universal Business Assessment Input Schema ---
class UniversalScorecardInput(BaseModel):
    # FINANCIAL HEALTH
    revenue: Literal["Under $10K", "$10K–$50K", "$50K–$250K", "$250K–$1M", "$1M–$5M", "Over $5M"]
    revenue_trend: Literal["Declining", "Flat", "Growing slowly (<10%)", "Growing moderately (10-25%)", "Growing rapidly (>25%)"]
    profit_margin_known: Literal["Yes, I track it closely", "Roughly know it", "No idea"]
    profit_margin: Literal["N/A", "Breaking even/Loss", "1-10%", "10-20%", "20-30%", "30%+"]
    cash_flow: Literal["Negative (spending savings)", "Break-even", "Positive but tight", "Healthy buffer", "Strong reserves"]
    financial_planning: Literal["No formal planning", "Basic budgeting", "Monthly financial reviews", "Detailed forecasting"]

    # GROWTH & MARKETING
    customer_acquisition: Literal["Word of mouth only", "Some marketing efforts", "Consistent marketing", "Multi-channel strategy"]
    customer_cost_awareness: Literal["No idea", "Rough estimate", "Track precisely"]
    customer_retention: Literal["Don't track", "High turnover", "Average retention", "Strong retention", "Excellent loyalty"]
    repeat_business: Literal["Rarely", "Occasionally", "Frequently", "Majority of revenue"]
    marketing_budget: Literal["No budget", "Under 5% of revenue", "5-10% of revenue", "Over 10% of revenue"]
    online_presence: Literal["No website/social", "Basic website", "Active online presence", "Strong digital brand"]
    customer_feedback: Literal["Don't collect", "Informal feedback", "Surveys/reviews", "Systematic feedback loops"]

    # OPERATIONS & SYSTEMS
    record_keeping: Literal["Paper/scattered files", "Basic digital files", "Accounting software", "Integrated business software"]
    inventory_management: Literal["N/A", "Manual tracking", "Basic systems", "Automated systems"]
    scheduling_systems: Literal["Paper calendar", "Basic digital calendar", "Scheduling software", "Integrated workflow"]
    quality_control: Literal["No formal process", "Basic checks", "Standard procedures", "Systematic quality management"]
    supplier_relationships: Literal["N/A", "Transactional only", "Good relationships", "Strategic partnerships"]

    # TEAM & MANAGEMENT
    team_size: Literal["Solo operation", "2-5 people", "6-15 people", "16-50 people", "50+ people"]
    hiring_process: Literal["N/A", "Informal hiring", "Basic process", "Structured interviews", "Comprehensive system"]
    employee_training: Literal["N/A", "On-the-job learning", "Basic training", "Formal programs"]
    delegation: Literal["Do everything myself", "Delegate basic tasks", "Delegate important work", "Team runs independently"]
    performance_tracking: Literal["No tracking", "Informal feedback", "Regular check-ins", "Formal performance reviews"]

    # DIGITAL ADOPTION
    payment_systems: Literal["Cash/check only", "Basic card processing", "Multiple payment options", "Advanced payment tech"]
    data_backup: Literal["No system", "Manual backups", "Cloud storage", "Automated backup systems"]
    communication_tools: Literal["Phone/email only", "Basic messaging", "Team communication apps", "Integrated communication"]
    website_functionality: Literal["No website", "Basic info site", "Interactive features", "E-commerce/booking enabled"]
    social_media_use: Literal["No presence", "Occasional posts", "Regular updates", "Strategic content marketing"]

    # STRATEGIC POSITION
    market_knowledge: Literal["Limited knowledge", "Basic awareness", "Good understanding", "Deep market insights"]
    competitive_advantage: Literal["Not sure", "Price/cost", "Quality/service", "Unique offering", "Market position"]
    customer_segments: Literal["Serve everyone", "1-2 main types", "Well-defined segments", "Specialized niches"]
    pricing_strategy: Literal["Match competitors", "Cost-plus margin", "Value-based pricing", "Dynamic/strategic pricing"]
    growth_planning: Literal["No plans", "Vague goals", "Basic plan", "Detailed strategy"]

    # BUSINESS CONTEXT
    business_type: Literal[
        "Retail/E-commerce", "Service Business", "Restaurant/Food", "Healthcare/Medical",
        "Construction/Trades", "Professional Services", "Manufacturing",
        "Technology/Software", "Consulting", "Other"
    ]
    business_age: Literal["Less than 1 year", "1-3 years", "3-10 years", "10+ years"]
    primary_challenge: Literal[
        "Not enough customers", "Too busy to grow systematically", "Inconsistent revenue",
        "Managing costs/expenses", "Finding good employees",
        "Competition/pricing pressure", "Keeping up with technology", "Time management/work-life balance"
    ]
    main_goal: Literal[
        "Increase revenue/sales", "Improve profitability", "Scale the business",
        "Reduce time commitment", "Build systems/processes", "Expand to new markets",
        "Improve quality/service", "Prepare for succession/sale"
    ]
    location_importance: Literal["Fully location-dependent", "Mostly local", "Regional reach", "National/global"]

    # NEW FIELDS FOR PDF REPORT
    full_name: str
    company_name: str
    email: str

# --- Complete Scoring Configuration ---
SCORING_CONFIG: Dict[str, Dict[str, Any]] = {
    'financial': {
        'fields': {
            'revenue': {
                'map': {"Under $10K": 1, "$10K–$50K": 2, "$50K–$250K": 3, "$250K–$1M": 4, "$1M–$5M": 5, "Over $5M": 6},
                'weight': 1.0
            },
            'revenue_trend': {
                'map': {"Declining": 1, "Flat": 2, "Growing slowly (<10%)": 3, "Growing moderately (10-25%)": 4, "Growing rapidly (>25%)": 5},
                'weight': 1.5
            },
            'profit_margin_known': {
                'map': {"No idea": 0, "Roughly know it": 1, "Yes, I track it closely": 2},
                'weight': 1.0
            },
            'profit_margin': {
                'map': {"N/A": 0, "Breaking even/Loss": 1, "1-10%": 2, "10-20%": 3, "20-30%": 4, "30%+": 5},
                'weight': 1.0
            },
            'cash_flow': {
                'map': {"Negative (spending savings)": 1, "Break-even": 2, "Positive but tight": 3, "Healthy buffer": 4, "Strong reserves": 5},
                'weight': 1.0
            },
            'financial_planning': {
                'map': {"No formal planning": 1, "Basic budgeting": 2, "Monthly financial reviews": 4, "Detailed forecasting": 5},
                'weight': 1.2
            }
        }
    },
    'growth': {
        'fields': {
            'customer_acquisition': {
                'map': {"Word of mouth only": 1, "Some marketing efforts": 2, "Consistent marketing": 4, "Multi-channel strategy": 5},
                'weight': 1.0
            },
            'customer_cost_awareness': {
                'map': {"No idea": 0, "Rough estimate": 2, "Track precisely": 4},
                'weight': 1.0
            },
            'customer_retention': {
                'map': {"Don't track": 0, "High turnover": 1, "Average retention": 3, "Strong retention": 4, "Excellent loyalty": 5},
                'weight': 1.3
            },
            'repeat_business': {
                'map': {"Rarely": 1, "Occasionally": 2, "Frequently": 4, "Majority of revenue": 5},
                'weight': 1.2
            },
            'marketing_budget': {
                'map': {"No budget": 1, "Under 5% of revenue": 2, "5-10% of revenue": 4, "Over 10% of revenue": 5},
                'weight': 1.0
            },
            'online_presence': {
                'map': {"No website/social": 1, "Basic website": 2, "Active online presence": 4, "Strong digital brand": 5},
                'weight': 1.1
            },
            'customer_feedback': {
                'map': {"Don't collect": 1, "Informal feedback": 2, "Surveys/reviews": 4, "Systematic feedback loops": 5},
                'weight': 1.0
            }
        }
    },
    'operations': {
        'fields': {
            'record_keeping': {
                'map': {"Paper/scattered files": 1, "Basic digital files": 2, "Accounting software": 4, "Integrated business software": 5},
                'weight': 1.3
            },
            'inventory_management': {
                'map': {"N/A": 3, "Manual tracking": 1, "Basic systems": 3, "Automated systems": 5},
                'weight': 1.0
            },
            'scheduling_systems': {
                'map': {"Paper calendar": 1, "Basic digital calendar": 2, "Scheduling software": 4, "Integrated workflow": 5},
                'weight': 1.0
            },
            'quality_control': {
                'map': {"No formal process": 1, "Basic checks": 2, "Standard procedures": 4, "Systematic quality management": 5},
                'weight': 1.2
            },
            'supplier_relationships': {
                'map': {"N/A": 3, "Transactional only": 2, "Good relationships": 4, "Strategic partnerships": 5},
                'weight': 1.0
            }
        }
    },
    'team': {
        'fields': {
            'team_size': {
                'map': {"Solo operation": 2, "2-5 people": 3, "6-15 people": 4, "16-50 people": 5, "50+ people": 6},
                'weight': 1.0
            },
            'hiring_process': {
                'map': {"N/A": 0, "Informal hiring": 2, "Basic process": 3, "Structured interviews": 4, "Comprehensive system": 5},
                'weight': 1.0
            },
            'employee_training': {
                'map': {"N/A": 0, "On-the-job learning": 2, "Basic training": 3, "Formal programs": 5},
                'weight': 1.1
            },
            'delegation': {
                'map': {"Do everything myself": 1, "Delegate basic tasks": 2, "Delegate important work": 4, "Team runs independently": 5},
                'weight': 1.4
            },
            'performance_tracking': {
                'map': {"No tracking": 1, "Informal feedback": 2, "Regular check-ins": 4, "Formal performance reviews": 5},
                'weight': 1.0
            }
        }
    },
    'digital': {
        'fields': {
            'payment_systems': {
                'map': {"Cash/check only": 1, "Basic card processing": 2, "Multiple payment options": 4, "Advanced payment tech": 5},
                'weight': 1.0
            },
            'data_backup': {
                'map': {"No system": 1, "Manual backups": 2, "Cloud storage": 4, "Automated backup systems": 5},
                'weight': 1.2
            },
            'communication_tools': {
                'map': {"Phone/email only": 1, "Basic messaging": 2, "Team communication apps": 4, "Integrated communication": 5},
                'weight': 1.0
            },
            'website_functionality': {
                'map': {"No website": 1, "Basic info site": 2, "Interactive features": 4, "E-commerce/booking enabled": 5},
                'weight': 1.3
            },
            'social_media_use': {
                'map': {"No presence": 1, "Occasional posts": 2, "Regular updates": 4, "Strategic content marketing": 5},
                'weight': 1.0
            }
        }
    },
    'strategic': {
        'fields': {
            'market_knowledge': {
                'map': {"Limited knowledge": 1, "Basic awareness": 2, "Good understanding": 4, "Deep market insights": 5},
                'weight': 1.3
            },
            'competitive_advantage': {
                'map': {"Not sure": 1, "Price/cost": 2, "Quality/service": 4, "Unique offering": 5, "Market position": 5},
                'weight': 1.2
            },
            'customer_segments': {
                'map': {"Serve everyone": 1, "1-2 main types": 3, "Well-defined segments": 4, "Specialized niches": 5},
                'weight': 1.1
            },
            'pricing_strategy': {
                'map': {"Match competitors": 2, "Cost-plus margin": 3, "Value-based pricing": 4, "Dynamic/strategic pricing": 5},
                'weight': 1.0
            },
            'growth_planning': {
                'map': {"No plans": 1, "Vague goals": 2, "Basic plan": 4, "Detailed strategy": 5},
                'weight': 1.4
            }
        }
    }
}

# Calculate max scores for each pillar
def _calculate_max_raw_score(pillar: str) -> float:
    """Calculate the maximum possible raw score for a pillar"""
    config = SCORING_CONFIG[pillar]
    max_score = 0.0
    for field_name, field_config in config['fields'].items():
        max_value = max(field_config['map'].values())
        max_score += max_value * field_config['weight']
    return max_score

# Pre-calculate max scores
for pillar in SCORING_CONFIG:
    SCORING_CONFIG[pillar]['max_raw'] = _calculate_max_raw_score(pillar)

# --- Scoring Functions ---
def _score_pillar(data: UniversalScorecardInput, pillar: str) -> int:
    """Generic pillar scorer using configuration"""
    config = SCORING_CONFIG[pillar]
    raw_score = 0.0

    for field_name, field_config in config['fields'].items():
        field_value = getattr(data, field_name)
        field_score = field_config['map'][field_value]
        weighted_score = field_score * field_config['weight']
        raw_score += weighted_score

    # Normalize to 25 points
    normalized_score = (raw_score / config['max_raw']) * 25
    return min(round(normalized_score), 25)

def score_financial(data: UniversalScorecardInput) -> int:
    """Score financial health pillar"""
    return _score_pillar(data, 'financial')

def score_growth(data: UniversalScorecardInput) -> int:
    """Score growth & marketing pillar"""
    return _score_pillar(data, 'growth')

def score_operations(data: UniversalScorecardInput) -> int:
    """Score operations & systems pillar"""
    return _score_pillar(data, 'operations')

def score_team(data: UniversalScorecardInput) -> int:
    """Score team & management pillar with special solo handling"""
    if data.team_size == "Solo operation":
        # For solo operations, focus primarily on delegation and systems
        delegation_config = SCORING_CONFIG['team']['fields']['delegation']
        delegation_score = delegation_config['map'][data.delegation]
        base_solo_score = 3.0
        total_score = (delegation_score * delegation_config['weight']) + base_solo_score
        max_solo_score = (5 * delegation_config['weight']) + base_solo_score
        normalized_score = (total_score / max_solo_score) * 25
        return min(round(normalized_score), 25)
    return _score_pillar(data, 'team')

def score_digital(data: UniversalScorecardInput) -> int:
    """Score digital adoption pillar"""
    return _score_pillar(data, 'digital')

def score_strategic(data: UniversalScorecardInput) -> int:
    """Score strategic position pillar"""
    return _score_pillar(data, 'strategic')

# --- Enhanced Insight Generator ---
def generate_universal_insight(data: UniversalScorecardInput, scores: Dict[str, int]) -> str:
    """Generate comprehensive business insights with BeamX recommendations"""
    if not anthropic_client.api_key:
        logger.error("Anthropic API key is not configured")
        raise HTTPException(status_code=500, detail="Anthropic API key is not configured")

    f, g, o, t, d, s = scores['financial'], scores['growth'], scores['operations'], scores['team'], scores['digital'], scores['strategic']

    # Create detailed context from responses
    context_details = f"""
    BUSINESS PROFILE:
    - Business Type: {data.business_type}
    - Business Age: {data.business_age}
    - Team Size: {data.team_size}
    - Location Importance: {data.location_importance}

    FINANCIAL SITUATION:
    - Revenue: {data.revenue} (Trend: {data.revenue_trend})
    - Profit Margin: {data.profit_margin} (Awareness: {data.profit_margin_known})
    - Cash Flow: {data.cash_flow}
    - Financial Planning: {data.financial_planning}

    GROWTH & MARKETING:
    - Customer Acquisition: {data.customer_acquisition}
    - Cost Awareness: {data.customer_cost_awareness}
    - Customer Retention: {data.customer_retention}
    - Repeat Business: {data.repeat_business}
    - Marketing Budget: {data.marketing_budget}
    - Online Presence: {data.online_presence}
    - Customer Feedback: {data.customer_feedback}

    OPERATIONS & SYSTEMS:
    - Record Keeping: {data.record_keeping}
    - Inventory Management: {data.inventory_management}
    - Scheduling Systems: {data.scheduling_systems}
    - Quality Control: {data.quality_control}
    - Supplier Relationships: {data.supplier_relationships}

    TEAM & MANAGEMENT:
    - Hiring Process: {data.hiring_process}
    - Employee Training: {data.employee_training}
    - Delegation: {data.delegation}
    - Performance Tracking: {data.performance_tracking}

    DIGITAL ADOPTION:
    - Payment Systems: {data.payment_systems}
    - Data Backup: {data.data_backup}
    - Communication Tools: {data.communication_tools}
    - Website Functionality: {data.website_functionality}
    - Social Media Use: {data.social_media_use}

    STRATEGIC POSITION:
    - Market Knowledge: {data.market_knowledge}
    - Competitive Advantage: {data.competitive_advantage}
    - Customer Segments: {data.customer_segments}
    - Pricing Strategy: {data.pricing_strategy}
    - Growth Planning: {data.growth_planning}

    CURRENT SITUATION:
    - Primary Challenge: {data.primary_challenge}
    - Main Goal: {data.main_goal}
    """

    # Determine business maturity level
    maturity_indicators = {
        'startup': data.business_age in ["Less than 1 year", "1-3 years"] and data.team_size in ["Solo operation", "2-5 people"],
        'growing': data.business_age in ["1-3 years", "3-10 years"] and data.revenue in ["$50K–$250K", "$250K–$1M"],
        'established': data.business_age == "10+ years" or data.revenue in ["$1M–$5M", "Over $5M"],
        'solo_professional': data.team_size == "Solo operation" and data.business_type in ["Professional Services", "Consulting"]
    }

    business_context = "startup" if maturity_indicators['startup'] else "established business" if maturity_indicators['established'] else "growing business"
    if maturity_indicators['solo_professional']:
        business_context = "solo professional practice"

    # BeamX services context
    beamx_services_context = f"""
    BEAMX SOLUTIONS AVAILABLE:
    1. **Managed Intelligence Services** – Business intelligence reports & dashboards for key metrics and data-driven decisions
    2. **Web & Workflow Engineering** – High-converting websites and automated workflows to save time
    3. **Data Infrastructure & Automation** – Clean databases, smooth APIs, and integrated systems
    4. **AI & Machine Learning** – Predictive models for customer behavior, fraud detection, and opportunity identification
    5. **Custom AI Agents** – Digital employees for support tickets, lead qualification, data analysis, and operations
    """

    prompt = f"""
    You are a business consultant specializing in {data.business_type} businesses. Analyze this {business_context}:

    ASSESSMENT SCORES:
    • Financial Health: {f}/25
    • Growth & Marketing: {g}/25
    • Operations & Systems: {o}/25
    • Team & Management: {t}/25
    • Digital Adoption: {d}/25
    • Strategic Position: {s}/25
    • Overall Score: {f+g+o+t+d+s}/150

    {context_details}

    {beamx_services_context}

    ANALYSIS REQUIREMENTS:
    1. **Business Health Summary** (2-3 sentences): Assess their current position as a {data.business_age} {data.business_type} business.
    2. **Key Strengths**: Identify 2-3 areas where they're performing well, considering their business type and size.
    3. **Priority Improvements**: Highlight the 2-3 most critical areas for improvement that would directly impact their stated goal: "{data.main_goal}".
    4. **Actionable Recommendations**: Provide 4-6 specific recommendations that are:
       - Appropriate for a {data.business_type} business of their size
       - Directly address their challenge: "{data.primary_challenge}"
       - Realistic given their current systems and resources
       - Include both immediate (30 days) and medium-term (3-6 months) actions
    5. **Implementation Priority**: Rank your recommendations by impact vs. effort, focusing on what will move the needle most for their revenue/profitability.
    6. **Success Metrics**: Suggest 3-4 practical metrics they should track, appropriate for their business type and current sophistication level.
    7. **How BeamX Can Accelerate Your Growth**: Based on their specific assessment results, identify 2-3 BeamX services that would have the highest impact on their business. Be specific about:
       - Which gaps these services address from their assessment
       - Expected business outcomes (time saved, revenue increase, efficiency gains)
       - Why these solutions fit their current stage and challenges
       - Concrete examples relevant to their business type

    Tailor advice specifically for {data.business_type} businesses. Avoid startup/tech jargon if this is a traditional business. Focus on practical, implementable advice that fits their business model and current capabilities.
    """

    try:
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except AnthropicError as e:
        logger.error(f"Anthropic API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}")

# --- Complete Assessment Function ---
def run_universal_assessment(data: UniversalScorecardInput) -> Dict[str, Any]:
    """Run complete business assessment and generate insights"""
    try:
        scores = {
            'financial': score_financial(data),
            'growth': score_growth(data),
            'operations': score_operations(data),
            'team': score_team(data),
            'digital': score_digital(data),
            'strategic': score_strategic(data)
        }

        insight = generate_universal_insight(data, scores)
        return {
            'scores': scores,
            'total_score': sum(scores.values()),
            'max_score': 150,
            'insight': insight,
            'assessment_data': data.dict()
        }
    except Exception as e:
        logger.error(f"Assessment error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing assessment: {str(e)}")

# --- PDF Report Generator ---
def generate_pdf_report(data: UniversalScorecardInput, result: Dict[str, Any]) -> str:
    """Generate a PDF report using WeasyPrint"""
    logger.info("Starting PDF report generation with WeasyPrint")

    # Sanitizing input to prevent HTML injection
    def sanitize_html(text: str) -> str:
        if not isinstance(text, str):
            text = str(text)
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    # Extracting scores and insight
    scores = result['scores']
    insight = result['insight']
    total_score = result['total_score']
    max_score = result['max_score']

    # Sanitize all input fields
    try:
        sanitized_full_name = sanitize_html(data.full_name)
        sanitized_company_name = sanitize_html(data.company_name)
        sanitized_email = sanitize_html(data.email)
        sanitized_insight = sanitize_html(insight.replace('**', '<strong>').replace('**', '</strong>'))
        sanitized_business_type = sanitize_html(data.business_type)
        sanitized_business_age = sanitize_html(data.business_age)
        sanitized_team_size = sanitize_html(data.team_size)
        sanitized_location_importance = sanitize_html(data.location_importance)
        sanitized_primary_challenge = sanitize_html(data.primary_challenge)
        sanitized_main_goal = sanitize_html(data.main_goal)
    except Exception as e:
        logger.error(f"Sanitization error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sanitizing input: {str(e)}")

    # Preparing HTML content for PDF
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                margin: 2cm;
                color: #333;
            }}
            h1 {{
                color: #0066cc;
                text-align: center;
                font-size: 24pt;
            }}
            h2 {{
                color: #0066cc;
                font-size: 18pt;
                margin-top: 20px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
            }}
            .header p {{
                margin: 5px 0;
                font-size: 12pt;
            }}
            .score-box {{
                border: 2px solid #0066cc;
                padding: 15px;
                background-color: #f0f8ff;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .score-box ul {{
                list-style-type: none;
                padding: 0;
                column-count: 2;
                column-gap: 20px;
            }}
            .score-box li {{
                margin-bottom: 10px;
                font-size: 12pt;
            }}
            .profile-box {{
                margin: 20px 0;
            }}
            .profile-box dt {{
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .profile-box dd {{
                margin-bottom: 10px;
                margin-left: 20px;
            }}
            .insights-box {{
                border: 2px solid #0066cc;
                padding: 15px;
                background-color: #f0f8ff;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .insights-box p {{
                font-size: 12pt;
                line-height: 1.5;
            }}
            .next-steps {{
                margin-top: 20px;
            }}
            .next-steps p {{
                font-size: 12pt;
                line-height: 1.5;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Universal Business Assessment Report</h1>
            <p><strong>BeamX Solutions</strong></p>
            <p>Prepared for: {sanitized_full_name}</p>
            <p>Company: {sanitized_company_name}</p>
            <p>Email: {sanitized_email}</p>
            <p>Date: July 29, 2025</p>
        </div>

        <h2>Assessment Overview</h2>
        <p>This report provides a comprehensive evaluation of {sanitized_company_name}'s business performance across six key pillars: Financial Health, Growth & Marketing, Operations & Systems, Team & Management, Digital Adoption, and Strategic Position. The assessment yields a total score of {total_score} out of {max_score}, reflecting the business's current strengths and areas for improvement.</p>

        <div class="score-box">
            <h2>Assessment Scores</h2>
            <ul>
                <li>Financial Health: {scores['financial']}/25</li>
                <li>Growth & Marketing: {scores['growth']}/25</li>
                <li>Operations & Systems: {scores['operations']}/25</li>
                <li>Team & Management: {scores['team']}/25</li>
                <li>Digital Adoption: {scores['digital']}/25</li>
                <li>Strategic Position: {scores['strategic']}/25</li>
            </ul>
            <p><strong>Total Score: {total_score}/{max_score}</strong></p>
        </div>

        <div class="profile-box">
            <h2>Business Profile</h2>
            <dl>
                <dt>Business Type:</dt><dd>{sanitized_business_type}</dd>
                <dt>Business Age:</dt><dd>{sanitized_business_age}</dd>
                <dt>Team Size:</dt><dd>{sanitized_team_size}</dd>
                <dt>Location Importance:</dt><dd>{sanitized_location_importance}</dd>
                <dt>Primary Challenge:</dt><dd>{sanitized_primary_challenge}</dd>
                <dt>Main Goal:</dt><dd>{sanitized_main_goal}</dd>
            </dl>
        </div>

        <div class="insights-box">
            <h2>Insights and Recommendations</h2>
            <p>{sanitized_insight.replace('\n', '<br>')}</p>
        </div>

        <div class="next-steps">
            <h2>Next Steps</h2>
            <p>To implement the recommendations provided in this report, contact BeamX Solutions at <strong>info@beamxsolutions.com</strong> or visit <strong>https://beamxsolutions.com</strong> to schedule a consultation. Our team is ready to help you achieve your business goals with tailored solutions.</p>
        </div>
    </body>
    </html>
    """

    # Creating a temporary directory for PDF processing
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Created temporary directory: {temp_dir}")
            pdf_path = os.path.join(temp_dir, "report.pdf")

            # Generating PDF with WeasyPrint
            logger.info(f"Generating PDF at {pdf_path}")
            HTML(string=html_content).write_pdf(pdf_path)

            # Checking if PDF was generated
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found at {pdf_path}")
                raise HTTPException(status_code=500, detail="PDF generation failed: Output file not found")

            logger.info(f"PDF generated successfully at {pdf_path}")
            return pdf_path
    except Exception as e:
        logger.error(f"PDF generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")

# --- API Endpoints ---
@app.post("/assess", response_model=dict)
async def assess_business(data: UniversalScorecardInput):
    """Run business assessment based on input data"""
    try:
        result = run_universal_assessment(data)
        return result
    except HTTPException as e:
        logger.error(f"Assessment endpoint error: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Assessment endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing assessment: {str(e)}")

@app.post("/download-report")
async def download_report(data: UniversalScorecardInput):
    """Generate and download PDF report"""
    logger.info("Received request to generate PDF report")
    try:
        # Running assessment to get results
        result = run_universal_assessment(data)
        # Generating PDF
        pdf_path = generate_pdf_report(data, result)
        # Returning the file for download
        logger.info(f"Sending PDF file: {pdf_path}")
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"{sanitize_html(data.company_name)}_Assessment_Report.pdf"
        )
    except HTTPException as e:
        logger.error(f"Download report endpoint error: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Download report endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating PDF report: {str(e)}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Universal Business Assessment API is running"}