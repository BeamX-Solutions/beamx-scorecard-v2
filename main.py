from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Dict, Any, Optional
from anthropic import Anthropic, AnthropicError
from supabase import create_client, Client
import os
from datetime import datetime
import json

app = FastAPI(title="Advanced Business Assessment API")

# CORS configuration
origins = ["https://beamxsolutions.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# --- Advanced Business Assessment Input Schema ---
class AdvancedScorecardInput(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    revenue: Literal["Under $10K", "$10K–$50K", "$50K–$250K", "$250K–$1M", "$1M–$5M", "Over $5M"]
    revenue_trend: Literal["Declining", "Flat", "Growing slowly (<10%)", "Growing moderately (10-25%)", "Growing rapidly (>25%)"]
    profit_margin_known: Literal["Yes, I track it closely", "Roughly know it", "No idea"]
    profit_margin: Literal["N/A", "Breaking even/Loss", "1-10%", "10-20%", "20-30%", "30%+"]
    cash_flow: Literal["Negative (spending savings)", "Break-even", "Positive but tight", "Healthy buffer", "Strong reserves"]
    financial_planning: Literal["No formal planning", "Basic budgeting", "Monthly financial reviews", "Detailed forecasting"]
    customer_acquisition: Literal["Word of mouth only", "Some marketing efforts", "Consistent marketing", "Multi-channel strategy"]
    customer_cost_awareness: Literal["No idea", "Rough estimate", "Track precisely"]
    customer_retention: Literal["Don't track", "High turnover", "Average retention", "Strong retention", "Excellent loyalty"]
    repeat_business: Literal["Rarely", "Occasionally", "Frequently", "Majority of revenue"]
    marketing_budget: Literal["No budget", "Under 5% of revenue", "5-10% of revenue", "Over 10% of revenue"]
    online_presence: Literal["No website/social", "Basic website", "Active online presence", "Strong digital brand"]
    customer_feedback: Literal["Don't collect", "Informal feedback", "Surveys/reviews", "Systematic feedback loops"]
    record_keeping: Literal["Paper/scattered files", "Basic digital files", "Accounting software", "Integrated business software"]
    inventory_management: Literal["N/A", "Manual tracking", "Basic systems", "Automated systems"]
    scheduling_systems: Literal["Paper calendar", "Basic digital calendar", "Scheduling software", "Integrated workflow"]
    quality_control: Literal["No formal process", "Basic checks", "Standard procedures", "Systematic quality management"]
    supplier_relationships: Literal["N/A", "Transactional only", "Good relationships", "Strategic partnerships"]
    team_size: Literal["Solo operation", "2-5 people", "6-15 people", "16-50 people", "50+ people"]
    hiring_process: Literal["N/A", "Informal hiring", "Basic process", "Structured interviews", "Comprehensive system"]
    employee_training: Literal["N/A", "On-the-job learning", "Basic training", "Formal programs"]
    delegation: Literal["Do everything myself", "Delegate basic tasks", "Delegate important work", "Team runs independently"]
    performance_tracking: Literal["No tracking", "Informal feedback", "Regular check-ins", "Formal performance reviews"]
    payment_systems: Literal["Cash/check only", "Basic card processing", "Multiple payment options", "Advanced payment tech"]
    data_backup: Literal["No system", "Manual backups", "Cloud storage", "Automated backup systems"]
    communication_tools: Literal["Phone/email only", "Basic messaging", "Team communication apps", "Integrated communication"]
    website_functionality: Literal["No website", "Basic info site", "Interactive features", "E-commerce/booking enabled"]
    social_media_use: Literal["No presence", "Occasional posts", "Regular updates", "Strategic content marketing"]
    market_knowledge: Literal["Limited knowledge", "Basic awareness", "Good understanding", "Deep market insights"]
    competitive_advantage: Literal["Not sure", "Price/cost", "Quality/service", "Unique offering", "Market position"]
    customer_segments: Literal["Serve everyone", "1-2 main types", "Well-defined segments", "Specialized niches"]
    pricing_strategy: Literal["Match competitors", "Cost-plus margin", "Value-based pricing", "Dynamic/strategic pricing"]
    growth_planning: Literal["No plans", "Vague goals", "Basic plan", "Detailed strategy"]
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
def _score_pillar(data: AdvancedScorecardInput, pillar: str) -> int:
    """Generic pillar scorer using configuration"""
    config = SCORING_CONFIG[pillar]
    raw_score = 0.0

    for field_name, field_config in config['fields'].items():
        field_value = getattr(data, field_name)
        field_score = field_config['map'][field_value]
        weighted_score = field_score * field_config['weight']
        raw_score += weighted_score

    normalized_score = (raw_score / config['max_raw']) * 25
    return min(round(normalized_score), 25)

def score_financial(data: AdvancedScorecardInput) -> int:
    return _score_pillar(data, 'financial')

def score_growth(data: AdvancedScorecardInput) -> int:
    return _score_pillar(data, 'growth')

def score_operations(data: AdvancedScorecardInput) -> int:
    return _score_pillar(data, 'operations')

def score_team(data: AdvancedScorecardInput) -> int:
    if data.team_size == "Solo operation":
        delegation_config = SCORING_CONFIG['team']['fields']['delegation']
        delegation_score = delegation_config['map'][data.delegation]
        base_solo_score = 3.0
        total_score = (delegation_score * delegation_config['weight']) + base_solo_score
        max_solo_score = (5 * delegation_config['weight']) + base_solo_score
        normalized_score = (total_score / max_solo_score) * 25
        return min(round(normalized_score), 25)
    return _score_pillar(data, 'team')

def score_digital(data: AdvancedScorecardInput) -> int:
    return _score_pillar(data, 'digital')

def score_strategic(data: AdvancedScorecardInput) -> int:
    return _score_pillar(data, 'strategic')

# --- Enhanced Insight Generator ---
def generate_Advanced_insight(data: AdvancedScorecardInput, scores: Dict[str, int]) -> str:
    if not anthropic_client.api_key:
        raise HTTPException(status_code=500, detail="Anthropic API key is not configured")

    f, g, o, t, d, s = scores['financial'], scores['growth'], scores['operations'], scores['team'], scores['digital'], scores['strategic']

    context_details = f"""
    BUSINESS PROFILE:
    - Business Type: {data.business_type}
    - Business Age: {data.business_age}
    - Team Size: {data.team_size}
    - Location Importance: {data.location_importance}
    - Company Name: {data.company_name or 'Not provided'}
    - Contact: {data.full_name or 'Not provided'} ({data.email or 'Not provided'})

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

    maturity_indicators = {
        'startup': data.business_age in ["Less than 1 year", "1-3 years"] and data.team_size in ["Solo operation", "2-5 people"],
        'growing': data.business_age in ["1-3 years", "3-10 years"] and data.revenue in ["$50K–$250K", "$250K–$1M"],
        'established': data.business_age == "10+ years" or data.revenue in ["$1M–$5M", "Over $5M"],
        'solo_professional': data.team_size == "Solo operation" and data.business_type in ["Professional Services", "Consulting"]
    }

    business_context = "startup" if maturity_indicators['startup'] else "established business" if maturity_indicators['established'] else "growing business"
    if maturity_indicators['solo_professional']:
        business_context = "solo professional practice"

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
        raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}")

# --- Complete Assessment Function ---
def run_Advanced_assessment(data: AdvancedScorecardInput) -> Dict[str, Any]:
    """Run complete business assessment and generate insights"""
    scores = {
        'financial': score_financial(data),
        'growth': score_growth(data),
        'operations': score_operations(data),
        'team': score_team(data),
        'digital': score_digital(data),
        'strategic': score_strategic(data)
    }

    insight = generate_Advanced_insight(data, scores)

    # Save to Supabase advanced_assessments table
    try:
        # Prepare data for insertion, including all input fields, scores, and insight
        insert_data = {
            "full_name": data.full_name,
            "company_name": data.company_name,
            "email": data.email,
            "revenue": data.revenue,
            "revenue_trend": data.revenue_trend,
            "profit_margin_known": data.profit_margin_known,
            "profit_margin": data.profit_margin,
            "cash_flow": data.cash_flow,
            "financial_planning": data.financial_planning,
            "customer_acquisition": data.customer_acquisition,
            "customer_cost_awareness": data.customer_cost_awareness,
            "customer_retention": data.customer_retention,
            "repeat_business": data.repeat_business,
            "marketing_budget": data.marketing_budget,
            "online_presence": data.online_presence,
            "customer_feedback": data.customer_feedback,
            "record_keeping": data.record_keeping,
            "inventory_management": data.inventory_management,
            "scheduling_systems": data.scheduling_systems,
            "quality_control": data.quality_control,
            "supplier_relationships": data.supplier_relationships,
            "team_size": data.team_size,
            "hiring_process": data.hiring_process,
            "employee_training": data.employee_training,
            "delegation": data.delegation,
            "performance_tracking": data.performance_tracking,
            "payment_systems": data.payment_systems,
            "data_backup": data.data_backup,
            "communication_tools": data.communication_tools,
            "website_functionality": data.website_functionality,
            "social_media_use": data.social_media_use,
            "market_knowledge": data.market_knowledge,
            "competitive_advantage": data.competitive_advantage,
            "customer_segments": data.customer_segments,
            "pricing_strategy": data.pricing_strategy,
            "growth_planning": data.growth_planning,
            "business_type": data.business_type,
            "business_age": data.business_age,
            "primary_challenge": data.primary_challenge,
            "main_goal": data.main_goal,
            "location_importance": data.location_importance,
            "financial_score": scores['financial'],
            "growth_score": scores['growth'],
            "operations_score": scores['operations'],
            "team_score": scores['team'],
            "digital_score": scores['digital'],
            "strategic_score": scores['strategic'],
            "total_score": sum(scores.values()),
            "insight": insight,
            "created_at": datetime.now().isoformat()
        }
        response = supabase.table("advanced_assessments").insert(insert_data).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving to Supabase: {str(e)}")

    return {
        'scores': scores,
        'total_score': sum(scores.values()),
        'max_score': 150,
        'insight': insight,
        'assessment_data': insert_data  # Return the same data structure for consistency
    }

# --- API Endpoints ---
@app.post("/assess", response_model=dict)
async def assess_business(data: AdvancedScorecardInput):
    """Run business assessment based on input data"""
    try:
        result = run_Advanced_assessment(data)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing assessment: {str(e)}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Advanced Business Assessment API is running"}