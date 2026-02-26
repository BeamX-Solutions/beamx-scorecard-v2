from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, List, Literal
from dataclasses import dataclass
import datetime
import os
import base64
import io
import re
import logging
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
from supabase import create_client, Client
from anthropic import AsyncAnthropic
import resend

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Beacon Pro SME Assessment API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://beamxsolutions.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
claude_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
resend_api_key = os.getenv("RESEND_API_KEY")
from_email = os.getenv("FROM_EMAIL", "noreply@beamxsolutions.com")
if resend_api_key:
    resend.api_key = resend_api_key


# ─────────────────────────────────────────────
# INPUT SCHEMA (identical to Beacon)
# ─────────────────────────────────────────────

class BeaconProInput(BaseModel):
    fullName: str = Field(min_length=1, max_length=100)
    email: EmailStr
    businessName: str = Field(min_length=1, max_length=150)
    industry: Literal[
        "Retail/Trade", "Food & Beverage", "Professional Services",
        "Beauty & Personal Care", "Logistics & Transportation",
        "Manufacturing/Production", "Hospitality", "Construction/Trades",
        "Healthcare Services", "Education/Training", "Agriculture", "Other"
    ]
    yearsInBusiness: Literal[
        "Less than 1 year", "1-3 years", "3-5 years", "5-10 years", "10+ years"
    ]
    cashFlow: Literal[
        "Consistent surplus", "Breaking even",
        "Unpredictable (some surplus, some deficit)",
        "Burning cash consistently", "Don't know"
    ]
    profitMargin: Literal[
        "30%+", "20-30%", "10-20%", "5-10%",
        "Less than 5% or negative", "Don't know"
    ]
    cashRunway: Literal[
        "6+ months", "3-6 months", "1-3 months",
        "Less than 1 month", "Would close immediately"
    ]
    paymentSpeed: Literal[
        "Same day (cash/instant)", "1-7 days", "8-30 days", "31-60 days", "60+ days"
    ]
    repeatCustomerRate: Literal[
        "70%+ repeat customers", "50-70% repeat", "30-50% repeat",
        "10-30% repeat", "Less than 10% repeat"
    ]
    acquisitionChannel: Literal[
        "Referrals/word-of-mouth", "Walk-ins/location visibility",
        "Organic social media", "Repeat business relationships",
        "Paid advertising", "Cold outreach", "Don't know"
    ]
    pricingPower: Literal[
        "Tested increases successfully", "Most customers would stay",
        "Some would leave but still profitable", "Would lose most customers", "Don't know"
    ]
    founderDependency: Literal[
        "Runs 2+ weeks without me", "Can step away 1 week",
        "2-3 days max", "Can't miss even 1 day", "Must be there daily"
    ]
    processDocumentation: Literal[
        "Comprehensive written processes", "Some key processes documented",
        "Trained others, mostly in my head", "Everything in my head only", "No consistent processes"
    ]
    inventoryTracking: Literal[
        "Digital real-time system", "Regular manual/spreadsheet",
        "Weekly physical count", "Only when running low",
        "Don't track", "Not applicable (service business)"
    ]
    expenseAwareness: Literal[
        "Know exact amounts and percentages", "Know roughly",
        "General idea", "Would have to look up", "No idea"
    ]
    profitPerProduct: Literal[
        "Know margins on each offering", "Good sense of what's profitable",
        "Know revenue only, not profit", "Haven't analyzed", "All seem about the same"
    ]
    pricingStrategy: Literal[
        "Cost + margin + market research", "Match competitors",
        "Cost + markup (no market analysis)", "What feels right", "No strategy"
    ]
    businessTrajectory: Literal[
        "Growing 20%+", "Growing 5-20%", "Stable (±5%)",
        "Declining 5-20%", "Declining 20%+", "Less than 1 year old"
    ]
    revenueDiversification: Literal[
        "4+ streams/customer types", "2-3 streams", "Primary + side income",
        "Single product/customer type", "Dependent on 1-2 major customers"
    ]
    digitalPayments: Literal[
        "80%+ digital", "50-80% digital", "20-50% digital", "Less than 20% digital"
    ]
    formalRegistration: Literal[
        "Fully registered and tax compliant", "Registered, behind on taxes",
        "In process of registering", "Not registered"
    ]
    infrastructure: Literal[
        "Consistent power/internet/supply", "Mostly reliable with backups",
        "Frequent disruptions", "Major challenges daily"
    ]
    bankingRelationship: Literal[
        "Strong, accessed loans/credit", "Accounts but no credit",
        "Minimal interaction", "No bank relationship"
    ]
    primaryPainPoint: Literal[
        "Getting more customers/sales", "Managing cash flow/getting paid",
        "Hiring or managing staff", "Keeping costs under control",
        "Too busy/overwhelmed", "Inconsistent quality/delivery",
        "Don't know where to focus", "Competition/market changes",
        "Actually doing well, want to optimize"
    ]


# ─────────────────────────────────────────────
# SCORING MAPS (identical to Beacon)
# ─────────────────────────────────────────────

CASH_FLOW_MAP = {"Consistent surplus": 5, "Breaking even": 3, "Unpredictable (some surplus, some deficit)": 2, "Burning cash consistently": 0, "Don't know": 0}
PROFIT_MARGIN_MAP = {"30%+": 5, "20-30%": 4, "10-20%": 3, "5-10%": 2, "Less than 5% or negative": 1, "Don't know": 0}
CASH_RUNWAY_MAP = {"6+ months": 5, "3-6 months": 4, "1-3 months": 2, "Less than 1 month": 1, "Would close immediately": 0}
PAYMENT_SPEED_MAP = {"Same day (cash/instant)": 5, "1-7 days": 4, "8-30 days": 3, "31-60 days": 1, "60+ days": 0}
REPEAT_RATE_MAP = {"70%+ repeat customers": 5, "50-70% repeat": 4, "30-50% repeat": 3, "10-30% repeat": 2, "Less than 10% repeat": 0}
ACQUISITION_MAP = {"Referrals/word-of-mouth": 5, "Repeat business relationships": 5, "Walk-ins/location visibility": 3, "Organic social media": 3, "Paid advertising": 2, "Cold outreach": 1, "Don't know": 0}
PRICING_POWER_MAP = {"Tested increases successfully": 5, "Most customers would stay": 4, "Some would leave but still profitable": 3, "Would lose most customers": 1, "Don't know": 1}
FOUNDER_DEPENDENCY_MAP = {"Runs 2+ weeks without me": 5, "Can step away 1 week": 4, "2-3 days max": 3, "Can't miss even 1 day": 1, "Must be there daily": 0}
PROCESS_DOC_MAP = {"Comprehensive written processes": 5, "Some key processes documented": 4, "Trained others, mostly in my head": 2, "Everything in my head only": 1, "No consistent processes": 0}
INVENTORY_MAP = {"Digital real-time system": 5, "Regular manual/spreadsheet": 4, "Weekly physical count": 3, "Only when running low": 1, "Don't track": 0, "Not applicable (service business)": 4}
EXPENSE_AWARENESS_MAP = {"Know exact amounts and percentages": 5, "Know roughly": 4, "General idea": 3, "Would have to look up": 1, "No idea": 0}
PROFIT_PER_PRODUCT_MAP = {"Know margins on each offering": 5, "Good sense of what's profitable": 4, "Know revenue only, not profit": 2, "Haven't analyzed": 1, "All seem about the same": 1}
PRICING_STRATEGY_MAP = {"Cost + margin + market research": 5, "Match competitors": 3, "Cost + markup (no market analysis)": 2, "What feels right": 1, "No strategy": 0}
TRAJECTORY_MAP = {"Growing 20%+": 5, "Growing 5-20%": 4, "Stable (±5%)": 3, "Declining 5-20%": 1, "Declining 20%+": 0, "Less than 1 year old": 2}
DIVERSIFICATION_MAP = {"4+ streams/customer types": 5, "2-3 streams": 4, "Primary + side income": 3, "Single product/customer type": 2, "Dependent on 1-2 major customers": 0}
DIGITAL_PAYMENTS_MAP = {"80%+ digital": 5, "50-80% digital": 4, "20-50% digital": 2, "Less than 20% digital": 1}
FORMALIZATION_MAP = {"Fully registered and tax compliant": 5, "Registered, behind on taxes": 3, "In process of registering": 2, "Not registered": 0}
INFRASTRUCTURE_MAP = {"Consistent power/internet/supply": 5, "Mostly reliable with backups": 4, "Frequent disruptions": 2, "Major challenges daily": 0}
BANKING_MAP = {"Strong, accessed loans/credit": 5, "Accounts but no credit": 3, "Minimal interaction": 1, "No bank relationship": 0}


# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class CategoryScore:
    name: str
    score: float
    max_score: float
    percentage: float
    grade: str

@dataclass
class BeaconProScore:
    total_score: float
    readiness_level: str
    financial_health: CategoryScore
    customer_strength: CategoryScore
    operational_maturity: CategoryScore
    financial_intelligence: CategoryScore
    growth_resilience: CategoryScore
    primary_pain_point: str
    industry: str
    years_in_business: str
    critical_flags: List[str]
    opportunity_flags: List[str]


# ─────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────

def calculate_score(data: BeaconProInput) -> BeaconProScore:
    def get_grade(pct: float) -> str:
        if pct >= 90: return "A"
        elif pct >= 80: return "B+"
        elif pct >= 70: return "B"
        elif pct >= 60: return "C+"
        elif pct >= 50: return "C"
        else: return "D"

    fh_raw = CASH_FLOW_MAP[data.cashFlow] + PROFIT_MARGIN_MAP[data.profitMargin] + CASH_RUNWAY_MAP[data.cashRunway] + PAYMENT_SPEED_MAP[data.paymentSpeed]
    fh_score = (fh_raw / 20) * 20

    cs_raw = REPEAT_RATE_MAP[data.repeatCustomerRate] + ACQUISITION_MAP[data.acquisitionChannel] + PRICING_POWER_MAP[data.pricingPower]
    cs_score = (cs_raw / 15) * 20

    om_raw = FOUNDER_DEPENDENCY_MAP[data.founderDependency] + PROCESS_DOC_MAP[data.processDocumentation] + INVENTORY_MAP[data.inventoryTracking]
    om_score = (om_raw / 15) * 20

    fi_raw = EXPENSE_AWARENESS_MAP[data.expenseAwareness] + PROFIT_PER_PRODUCT_MAP[data.profitPerProduct] + PRICING_STRATEGY_MAP[data.pricingStrategy]
    fi_score = (fi_raw / 15) * 20

    gr_base = TRAJECTORY_MAP[data.businessTrajectory] + DIVERSIFICATION_MAP[data.revenueDiversification]
    gr_base_score = (gr_base / 10) * 12
    context_raw = (
        (DIGITAL_PAYMENTS_MAP[data.digitalPayments] / 5 * 2) +
        (FORMALIZATION_MAP[data.formalRegistration] / 5 * 3) +
        (INFRASTRUCTURE_MAP[data.infrastructure] / 5 * 2) +
        (BANKING_MAP[data.bankingRelationship] / 5 * 1)
    )
    gr_score = gr_base_score + context_raw
    total = fh_score + cs_score + om_score + fi_score + gr_score

    if total >= 85:   level = "🏆 Scale-Ready"
    elif total >= 70: level = "💪 Stable Foundation"
    elif total >= 50: level = "🔨 Building Blocks"
    elif total >= 30: level = "⚠️ Survival Mode"
    else:             level = "🚨 Red Alert"

    critical_flags = []
    if data.cashFlow in ["Burning cash consistently", "Don't know"]: critical_flags.append("CASH_CRISIS")
    if data.cashRunway in ["Less than 1 month", "Would close immediately"]: critical_flags.append("RUNWAY_CRITICAL")
    if data.profitMargin in ["Less than 5% or negative", "Don't know"]: critical_flags.append("NO_PROFIT_VISIBILITY")
    if data.founderDependency == "Must be there daily": critical_flags.append("FOUNDER_BURNOUT_RISK")
    if data.formalRegistration == "Not registered": critical_flags.append("INFORMAL_OPERATIONS")
    if data.repeatCustomerRate == "Less than 10% repeat": critical_flags.append("NO_CUSTOMER_LOYALTY")

    opportunity_flags = []
    if data.pricingPower in ["Tested increases successfully", "Most customers would stay"]: opportunity_flags.append("PRICING_POWER")
    if data.repeatCustomerRate == "70%+ repeat customers": opportunity_flags.append("STRONG_RETENTION")
    if data.acquisitionChannel in ["Referrals/word-of-mouth", "Repeat business relationships"]: opportunity_flags.append("ORGANIC_GROWTH")
    if data.processDocumentation == "Comprehensive written processes": opportunity_flags.append("SYSTEMS_READY")
    if fh_score >= 16: opportunity_flags.append("FINANCIAL_DISCIPLINE")

    def make_cat(name, score, max_s):
        pct = round((score / max_s) * 100, 1)
        return CategoryScore(name=name, score=round(score, 1), max_score=max_s, percentage=pct, grade=get_grade(pct))

    return BeaconProScore(
        total_score=round(total, 1),
        readiness_level=level,
        financial_health=make_cat("Financial Health", fh_score, 20),
        customer_strength=make_cat("Customer Strength", cs_score, 20),
        operational_maturity=make_cat("Operational Maturity", om_score, 20),
        financial_intelligence=make_cat("Financial Intelligence", fi_score, 20),
        growth_resilience=make_cat("Growth & Resilience", gr_score, 20),
        primary_pain_point=data.primaryPainPoint,
        industry=data.industry,
        years_in_business=data.yearsInBusiness,
        critical_flags=critical_flags,
        opportunity_flags=opportunity_flags,
    )


# ─────────────────────────────────────────────
# LLM PROMPTS
# ─────────────────────────────────────────────

def _build_pro_system_prompt() -> str:
    return """You are a senior business advisor at BeamX Solutions — sharp, direct, and deeply experienced with SMEs in emerging markets, particularly Nigeria and West Africa.

You are writing a premium, personalised advisory report for a business owner who just completed a diagnostic assessment. This is NOT a template fill-in — you are writing from scratch, as a real advisor would after reviewing their data.

YOUR VOICE:
- Talk directly to the owner by first name (use it 2-3 times per section, naturally)
- Be honest, warm, and specific — no generic advice that could apply to anyone
- Reference their actual answers, scores, and flags throughout
- Sound like a trusted advisor who has studied their business, not an AI filling in blanks
- Use Nigerian business context where relevant (naira, CAC, NEPA/power issues, etc.)

REPORT STRUCTURE (follow exactly, use these markdown headers):
## Executive Summary
## 🚨 Critical Priorities (Next 30 Days)   ← only if critical_flags exist
## Strategic Recommendations
## Growth Opportunities   ← only if opportunity_flags exist
## Your Next Steps

SCORING RULES (never change these):
- Total score: as provided — never modify
- Category scores and grades: as provided — never modify
- Critical flags: as provided — address each one specifically
- Opportunity flags: as provided — leverage each one specifically

ADVISORY QUALITY STANDARDS:
- Every recommendation must be specific and actionable (not "improve your finances" but "call every customer with invoices >15 days outstanding this week")
- For each critical flag, give a 30-day plan with Week 1 / Week 2-3 / Month 1 milestones
- For the weakest 1-2 categories, give a concrete 90-day improvement plan
- For the primary pain point, give a sequenced, prioritized tactical plan
- Include industry-specific metrics and benchmarks where relevant
- Close with a clear 30-day focus goal and BeamX CTA

LENGTH: This is a premium report. Write 900-1200 words of substantive advisory content."""


def _build_pro_user_prompt(data: BeaconProInput, score: BeaconProScore) -> str:
    first_name = data.fullName.split()[0]
    critical = ", ".join(score.critical_flags) if score.critical_flags else "None"
    opportunities = ", ".join(score.opportunity_flags) if score.opportunity_flags else "None"

    return f"""Write the Beacon Pro advisory report for this business owner.

OWNER: {first_name} (full name: {data.fullName})
BUSINESS: {data.businessName}
INDUSTRY: {data.industry}
YEARS IN BUSINESS: {data.yearsInBusiness}
PRIMARY PAIN POINT: {data.primaryPainPoint}

OVERALL SCORE: {score.total_score}/100
READINESS LEVEL: {score.readiness_level}

CATEGORY SCORES:
- Financial Health: {score.financial_health.score}/20 ({score.financial_health.percentage}%) — Grade: {score.financial_health.grade}
  Answers: Cash Flow={data.cashFlow} | Profit Margin={data.profitMargin} | Cash Runway={data.cashRunway} | Payment Speed={data.paymentSpeed}

- Customer Strength: {score.customer_strength.score}/20 ({score.customer_strength.percentage}%) — Grade: {score.customer_strength.grade}
  Answers: Repeat Rate={data.repeatCustomerRate} | Acquisition={data.acquisitionChannel} | Pricing Power={data.pricingPower}

- Operational Maturity: {score.operational_maturity.score}/20 ({score.operational_maturity.percentage}%) — Grade: {score.operational_maturity.grade}
  Answers: Founder Dependency={data.founderDependency} | Process Docs={data.processDocumentation} | Inventory={data.inventoryTracking}

- Financial Intelligence: {score.financial_intelligence.score}/20 ({score.financial_intelligence.percentage}%) — Grade: {score.financial_intelligence.grade}
  Answers: Expense Awareness={data.expenseAwareness} | Profit Per Product={data.profitPerProduct} | Pricing Strategy={data.pricingStrategy}

- Growth & Resilience: {score.growth_resilience.score}/20 ({score.growth_resilience.percentage}%) — Grade: {score.growth_resilience.grade}
  Answers: Trajectory={data.businessTrajectory} | Diversification={data.revenueDiversification} | Digital Payments={data.digitalPayments} | Registration={data.formalRegistration} | Infrastructure={data.infrastructure} | Banking={data.bankingRelationship}

CRITICAL FLAGS: {critical}
OPPORTUNITY FLAGS: {opportunities}

Write the full advisory now. Address {first_name} directly. Quote their actual answers back to them. Make every recommendation concrete and actionable. Include {data.industry} industry context relevant to Nigeria/West Africa."""


# ─────────────────────────────────────────────
# STREAMING ENDPOINT
# ─────────────────────────────────────────────

@app.post("/generate-report-stream")
async def generate_report_stream(input_data: BeaconProInput):
    """
    Two-phase SSE stream:
    1. Emits a 'score' event immediately with the full scorecard JSON
    2. Streams LLM advisory token by token as 'token' events
    3. Emits 'done' event with complete advisory for PDF/email use
    """
    score = calculate_score(input_data)

    async def event_generator():
        import json

        # Phase 1: emit scorecard immediately (renders while LLM writes)
        score_payload = {
            "type": "score",
            "data": {
                "total_score": score.total_score,
                "readiness_level": score.readiness_level,
                "breakdown": {
                    "financial_health": {"score": score.financial_health.score, "max": 20, "grade": score.financial_health.grade, "percentage": score.financial_health.percentage},
                    "customer_strength": {"score": score.customer_strength.score, "max": 20, "grade": score.customer_strength.grade, "percentage": score.customer_strength.percentage},
                    "operational_maturity": {"score": score.operational_maturity.score, "max": 20, "grade": score.operational_maturity.grade, "percentage": score.operational_maturity.percentage},
                    "financial_intelligence": {"score": score.financial_intelligence.score, "max": 20, "grade": score.financial_intelligence.grade, "percentage": score.financial_intelligence.percentage},
                    "growth_resilience": {"score": score.growth_resilience.score, "max": 20, "grade": score.growth_resilience.grade, "percentage": score.growth_resilience.percentage},
                },
                "flags": {"critical": score.critical_flags, "opportunities": score.opportunity_flags},
                "context": {
                    "industry": input_data.industry,
                    "yearsInBusiness": input_data.yearsInBusiness,
                    "primaryPainPoint": input_data.primaryPainPoint,
                    "businessName": input_data.businessName,
                }
            }
        }
        yield f"data: {json.dumps(score_payload)}\n\n"

        # Phase 2: stream LLM advisory
        full_advisory = ""
        try:
            async with claude_client.messages.stream(
                model="claude-sonnet-4-6",
                system=_build_pro_system_prompt(),
                messages=[
                    {"role": "user", "content": _build_pro_user_prompt(input_data, score)},
                ],
                max_tokens=2000,
            ) as stream:
                async for text in stream.text_stream:
                    full_advisory += text
                    yield f"data: {json.dumps({'type': 'token', 'data': text})}\n\n"

        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
            return

        # Save to Supabase (non-blocking, fire-and-forget)
        try:
            supabase.table("beacon_assessments").insert({
                **input_data.model_dump(),
                "total_score": score.total_score,
                "readiness_level": score.readiness_level,
                "critical_flags": score.critical_flags,
                "opportunity_flags": score.opportunity_flags,
                "advisory": full_advisory,
                "tier": "pro",
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).execute()
        except Exception as db_err:
            logger.warning(f"DB insert failed (non-fatal): {db_err}")

        # Phase 3: done — send full advisory for PDF/email
        yield f"data: {json.dumps({'type': 'done', 'data': full_advisory})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ─────────────────────────────────────────────
# PDF GENERATION
# ─────────────────────────────────────────────

def generate_pro_pdf(score: BeaconProScore, data: BeaconProInput, advisory: str) -> io.BytesIO:
    logo_url = 'https://beamxsolutions.com/Beamx-Logo-Colour.png'
    cover_bg_url = 'https://beamxsolutions.com/front-background.PNG'
    cta_img_url = 'https://beamxsolutions.com/cta-image.png'
    generated_date = datetime.datetime.now().strftime('%B %d, %Y')

    def md_to_html(text: str) -> str:
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        lines = text.split('\n')
        html_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('## '):
                html_lines.append(f'<h2 style="color:#B8860B;font-size:17px;margin:16px 0 8px;border-bottom:2px solid #B8860B;padding-bottom:4px;">{line[3:]}</h2>')
            elif line.startswith('### '):
                html_lines.append(f'<h3 style="color:#8B6914;font-size:14px;margin:12px 0 6px;">{line[4:]}</h3>')
            elif line.startswith('- ') or line.startswith('• '):
                html_lines.append(f'<li style="margin:5px 0;line-height:1.5;font-size:12px;">{line[2:]}</li>')
            elif line == '---':
                html_lines.append('<hr style="border:1px solid #d4af37;margin:16px 0;">')
            else:
                html_lines.append(f'<p style="margin:5px 0;line-height:1.5;font-size:12px;">{line}</p>')
        return '\n'.join(html_lines)

    advisory_html = md_to_html(advisory)

    def score_bar(pct):
        color = "#B8860B" if pct >= 70 else "#CC8800" if pct >= 50 else "#cc3300"
        return f'<div style="background:#eee;border-radius:4px;height:10px;width:100%;"><div style="background:{color};width:{pct}%;height:10px;border-radius:4px;"></div></div>'

    categories = [score.financial_health, score.customer_strength, score.operational_maturity, score.financial_intelligence, score.growth_resilience]
    table_rows = "".join([
        f'<tr><td style="padding:10px;border:1px solid #ddd;">{c.name}</td>'
        f'<td style="padding:10px;border:1px solid #ddd;text-align:center;font-weight:bold;">{c.score}</td>'
        f'<td style="padding:10px;border:1px solid #ddd;text-align:center;">20</td>'
        f'<td style="padding:10px;border:1px solid #ddd;text-align:center;font-weight:bold;">{c.grade}</td>'
        f'<td style="padding:10px;border:1px solid #ddd;">{score_bar(c.percentage)}</td></tr>'
        for c in categories
    ])

    circumference = 2 * 3.14159 * 70
    progress = (score.total_score / 100) * circumference

    html_content = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; color: #000; }}
  .page {{ width:8.5in; min-height:11in; background:white; position:relative; page-break-after:always; }}
  .page-cover {{ background-image:url('{cover_bg_url}'); background-size:cover; background-position:center; display:flex; flex-direction:column; justify-content:space-between; height:11in; }}
  .page-content {{ padding:40px 50px 80px; background:#f5f5f5; }}
  .footer {{ background:#1a1a2e; color:#d4af37; padding:12px 50px; display:flex; justify-content:space-between; font-size:11px; position:absolute; bottom:0; left:0; right:0; }}
  table {{ width:100%; border-collapse:collapse; background:white; }}
  th {{ background:#B8860B; color:white; padding:10px; text-align:center; font-size:12px; }}
  .pro-badge {{ background:#B8860B; color:white; padding:3px 10px; border-radius:10px; font-size:11px; font-weight:bold; display:inline-block; margin-left:8px; letter-spacing:1px; }}
</style>
</head><body>

<!-- COVER PAGE -->
<div class="page page-cover">
  <div style="padding:40px 60px;display:flex;align-items:center;gap:12px;">
    <img src="{logo_url}" style="width:160px;" />
    <span class="pro-badge">PRO</span>
  </div>
  <div style="background:rgba(26,26,46,0.95);padding:80px 60px;">
    <h1 style="font-size:54px;font-weight:bold;color:white;line-height:1.1;">Beacon Pro<br>Business<br>Assessment</h1>
    <p style="color:#d4af37;font-size:16px;margin-top:14px;">AI-Powered Deep Diagnostic</p>
  </div>
  <div style="padding:40px 60px;color:white;">
    <p style="font-weight:600;margin-bottom:4px;color:#d4af37;">Prepared For</p>
    <p style="font-size:20px;margin-bottom:4px;">{data.fullName}</p>
    <p style="font-size:13px;margin-bottom:16px;">{data.email}</p>
    <p style="font-weight:600;margin-bottom:4px;color:#d4af37;">Business</p>
    <p style="font-size:16px;margin-bottom:16px;">{data.businessName}</p>
    <p style="font-weight:600;margin-bottom:4px;color:#d4af37;">Generated on</p>
    <p style="font-size:15px;">{generated_date}</p>
  </div>
</div>

<!-- SCORECARD PAGE -->
<div class="page page-content">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
    <h2 style="color:#B8860B;font-size:20px;font-weight:bold;border-bottom:3px solid #B8860B;display:inline-block;padding-bottom:4px;">Overall Assessment</h2>
    <span class="pro-badge">PRO</span>
  </div>
  <div style="display:flex;gap:24px;align-items:center;background:white;padding:20px;margin-bottom:20px;border-left:4px solid #B8860B;">
    <svg width="160" height="160" viewBox="0 0 200 200">
      <circle cx="100" cy="100" r="70" fill="none" stroke="#f0e0a0" stroke-width="28"/>
      <circle cx="100" cy="100" r="70" fill="none" stroke="#B8860B" stroke-width="28"
        stroke-dasharray="{progress:.1f} {circumference:.1f}" transform="rotate(-90 100 100)"/>
      <text x="100" y="94" text-anchor="middle" font-size="20" font-weight="bold" fill="#000">{score.total_score}/100</text>
      <text x="100" y="114" text-anchor="middle" font-size="10" fill="#666">Overall Score</text>
    </svg>
    <div>
      <p style="font-size:18px;font-weight:bold;margin-bottom:6px;">Readiness Level</p>
      <p style="font-size:15px;color:#B8860B;margin-bottom:12px;">{score.readiness_level}</p>
      <p style="font-size:12px;margin-bottom:3px;"><strong>Business:</strong> {data.businessName}</p>
      <p style="font-size:12px;margin-bottom:3px;"><strong>Industry:</strong> {data.industry}</p>
      <p style="font-size:12px;margin-bottom:3px;"><strong>Years in Business:</strong> {data.yearsInBusiness}</p>
      <p style="font-size:12px;"><strong>Primary Challenge:</strong> {data.primaryPainPoint}</p>
    </div>
  </div>
  <h2 style="color:#B8860B;font-size:16px;font-weight:bold;border-bottom:2px solid #B8860B;display:inline-block;padding-bottom:3px;margin-bottom:12px;">Score Breakdown</h2>
  <table style="margin-bottom:20px;"><thead><tr><th>Category</th><th>Score</th><th>Max</th><th>Grade</th><th>Performance</th></tr></thead><tbody>{table_rows}</tbody></table>
  <div style="display:flex;gap:14px;">
    <div style="flex:1;background:#fee;border-left:4px solid #cc3300;padding:14px;border-radius:4px;">
      <p style="font-weight:bold;color:#cc3300;margin-bottom:8px;font-size:12px;">Critical Flags</p>
      {''.join([f'<p style="font-size:11px;margin:3px 0;">⚠ {f.replace("_"," ")}</p>' for f in score.critical_flags]) if score.critical_flags else '<p style="font-size:11px;">None detected</p>'}
    </div>
    <div style="flex:1;background:#fffbee;border-left:4px solid #B8860B;padding:14px;border-radius:4px;">
      <p style="font-weight:bold;color:#B8860B;margin-bottom:8px;font-size:12px;">Opportunity Flags</p>
      {''.join([f'<p style="font-size:11px;margin:3px 0;">✓ {f.replace("_"," ")}</p>' for f in score.opportunity_flags]) if score.opportunity_flags else '<p style="font-size:11px;">None detected</p>'}
    </div>
  </div>
  <div class="footer"><span>Beacon Pro — {data.businessName}</span><span>Copyright © 2025 BeamX Solutions</span></div>
</div>

<!-- ADVISORY PAGE -->
<div class="page page-content">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
    <h2 style="color:#B8860B;font-size:20px;font-weight:bold;border-bottom:3px solid #B8860B;display:inline-block;padding-bottom:4px;">AI-Powered Strategic Advisory</h2>
    <span class="pro-badge">PRO</span>
  </div>
  <div style="background:white;padding:20px;border-left:4px solid #B8860B;">{advisory_html}</div>
  <div class="footer"><span>Beacon Pro — {data.businessName}</span><span>Copyright © 2025 BeamX Solutions</span></div>
</div>

<!-- CTA PAGE -->
<div class="page" style="background:#1a1a2e;padding:60px;color:white;height:11in;">
  <h2 style="font-size:34px;font-weight:bold;border-bottom:4px solid #d4af37;display:inline-block;padding-bottom:8px;margin-bottom:28px;">Ready to Take Action?</h2>
  <div style="background:rgba(212,175,55,0.1);border:1px solid #d4af37;padding:20px;border-radius:8px;margin-bottom:28px;font-size:14px;line-height:1.6;color:white;">
    You've completed the most comprehensive AI-powered business diagnostic available for SMEs. The analysis above was written specifically for {data.businessName}. Now it's time to act.
  </div>
  <img src="{cta_img_url}" style="width:100%;height:320px;object-fit:cover;border-radius:8px;margin-bottom:28px;" />
  <div style="font-size:15px;line-height:2.4;color:#d4af37;">
    <p>🌐 www.beamxsolutions.com</p>
    <p>✉️ info@beamxsolutions.com</p>
    <p>📅 https://calendly.com/beamxsolutions</p>
  </div>
</div>

</body></html>'''

    buffer = io.BytesIO()
    HTML(string=html_content).write_pdf(buffer, font_config=FontConfiguration())
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────

def _build_pro_email_html(data: BeaconProInput, score: BeaconProScore) -> str:
    return f"""<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:0;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 0;">
<table width="600" cellpadding="0" cellspacing="0">
  <tr><td style="background:#1a1a2e;padding:40px 20px;text-align:center;">
    <img src="https://beamxsolutions.com/asset-1-2.png" width="112" height="50" style="display:block;margin:0 auto 12px;" />
    <span style="background:#B8860B;color:white;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:bold;letter-spacing:1px;">PRO</span>
    <h1 style="color:#d4af37;font-size:24px;margin:12px 0 0;">Your Beacon Pro Report</h1>
    <p style="color:#aaa;font-size:13px;margin:6px 0 0;">AI-Powered Deep Diagnostic</p>
  </td></tr>
  <tr><td style="height:20px;background:#f5f5f5;"></td></tr>
  <tr><td style="padding:0 30px;background:#f5f5f5;">
    <p style="font-size:14px;line-height:1.6;">Hello {data.fullName},<br><br>
    Your AI-powered Beacon Pro assessment for <strong>{data.businessName}</strong> is attached. This report was generated specifically for your business — every recommendation and insight is based on your exact answers.</p>
  </td></tr>
  <tr><td style="height:16px;background:#f5f5f5;"></td></tr>
  <tr><td align="center" style="background:#f5f5f5;">
    <table width="380" cellpadding="22" cellspacing="0" style="background:#1a1a2e;border:2px solid #d4af37;border-radius:8px;">
      <tr><td>
        <p style="color:#d4af37;font-size:20px;font-weight:700;margin:0;">Score: {score.total_score}/100</p>
        <p style="color:#fff;font-size:13px;margin:6px 0 0;">{score.readiness_level}</p>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="height:16px;background:#f5f5f5;"></td></tr>
  <tr><td style="padding:0 30px;background:#f5f5f5;">
    <table width="100%" cellpadding="16" cellspacing="0" style="background:white;border-radius:8px;border-top:3px solid #B8860B;">
      <tr><td>
        <h2 style="color:#B8860B;font-size:15px;margin:0 0 14px;">Score Breakdown</h2>
        <p style="font-size:13px;margin:0 0 8px;">💰 Financial Health: <strong>{score.financial_health.score}/20</strong> — {score.financial_health.grade}</p>
        <p style="font-size:13px;margin:0 0 8px;">🤝 Customer Strength: <strong>{score.customer_strength.score}/20</strong> — {score.customer_strength.grade}</p>
        <p style="font-size:13px;margin:0 0 8px;">⚙️ Operational Maturity: <strong>{score.operational_maturity.score}/20</strong> — {score.operational_maturity.grade}</p>
        <p style="font-size:13px;margin:0 0 8px;">📊 Financial Intelligence: <strong>{score.financial_intelligence.score}/20</strong> — {score.financial_intelligence.grade}</p>
        <p style="font-size:13px;margin:0;">📈 Growth & Resilience: <strong>{score.growth_resilience.score}/20</strong> — {score.growth_resilience.grade}</p>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="height:16px;background:#f5f5f5;"></td></tr>
  <tr><td align="center" style="background:#f5f5f5;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="background:#B8860B;border-radius:8px;">
        <a href="https://calendly.com/beamxsolutions" style="display:inline-block;padding:13px 26px;color:white;text-decoration:none;font-size:14px;font-weight:700;">Book Your Free Strategy Call</a>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="height:16px;background:#f5f5f5;"></td></tr>
  <tr><td style="background:#1a1a2e;padding:20px;text-align:center;">
    <p style="color:#d4af37;font-size:12px;margin:0 0 6px;">www.beamxsolutions.com | info@beamxsolutions.com</p>
    <p style="color:#888;font-size:11px;margin:0;">Copyright © 2025 BeamX Solutions</p>
  </td></tr>
</table></td></tr></table>
</body>"""


# ─────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────

@app.post("/download-pdf")
async def download_pdf(payload: dict):
    try:
        form_data = BeaconProInput(**payload["formData"])
        score = calculate_score(form_data)
        advisory = payload.get("result", {}).get("advisory", "")
        pdf_buffer = generate_pro_pdf(score, form_data, advisory)
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Beacon_Pro_{form_data.businessName.replace(' ', '_')}.pdf"}
        )
    except Exception as e:
        logger.error(f"PDF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/email-results")
async def email_results(payload: dict):
    try:
        recipient_email = payload.get("email")
        if not recipient_email:
            raise HTTPException(status_code=400, detail="Email address is required")
        form_data = BeaconProInput(**payload["formData"])
        score = calculate_score(form_data)
        advisory = payload.get("result", {}).get("advisory", "")
        if not advisory:
            raise HTTPException(status_code=400, detail="Advisory not found in payload")
        if not resend_api_key:
            raise HTTPException(status_code=500, detail="Email not configured.")
        form_data_for_email = form_data.model_copy(update={"email": recipient_email})
        pdf_buffer = generate_pro_pdf(score, form_data_for_email, advisory)
        pdf_b64 = base64.b64encode(pdf_buffer.read()).decode()
        resend.Emails.send({
            "from": f"BeamX Solutions <{from_email}>",
            "to": [recipient_email],
            "subject": f"Your Beacon Pro Report: {score.total_score}/100 — {score.readiness_level} | {form_data.businessName}",
            "html": _build_pro_email_html(form_data_for_email, score),
            "attachments": [{"filename": "Beacon_Pro_Assessment_Report.pdf", "content": pdf_b64}]
        })
        return {"status": "success", "message": f"Report sent to {recipient_email}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0", "tool": "Beacon Pro", "architecture": "pure LLM streaming"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8001)))