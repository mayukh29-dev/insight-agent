"""Adapt existing agent text for the UI and prepare credential-free demo answers."""

from dataclasses import dataclass, field
import re

from tools import category_sales, monthly_revenue, top_products, total_revenue

SAMPLE_QUESTIONS = (
    "Which category generated the most revenue?",
    "Show monthly revenue trends.",
    "What are the top five products by revenue?",
    "What is total revenue?",
)
HEADINGS = ("Tools executed", "Key metrics", "Business insights", "Recommendations", "Limitations")


@dataclass
class Report:
    """Presentation values contain only the agent's text or calculated demo facts."""

    question: str
    tools: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def summary(self):
        for entries in (self.insights, self.limitations, self.metrics):
            if entries:
                return entries[0]
        return "No summary was returned. Review the original report below."

    @property
    def additional_insights(self):
        """Show the summary once and keep other distinct insights in order."""
        return list(dict.fromkeys(insight for insight in self.insights if insight != self.summary))


def parse_report(text, question):
    """Split the CLI report at its existing section boundaries without rewriting claims."""
    sections = re.split(r"\n\n(" + "|".join(HEADINGS) + r")\n", text)
    values = dict(zip(sections[1::2], sections[2::2]))

    def lines(heading):
        return [line.removeprefix("- ").strip() for line in values.get(heading, "").splitlines()
                if line.strip()]

    tools = [item.strip() for item in values.get("Tools executed", "").strip().split(",")
             if item.strip() and item.strip() != "None"]
    return Report(question=question, tools=tools, metrics=lines("Key metrics"),
                  insights=lines("Business insights"), recommendations=lines("Recommendations"),
                  limitations=lines("Limitations"), raw=text)


def build_demo_reports(sales):
    """Precompute curated answers from validated data, without an LLM or credentials."""
    if sales.empty:
        raise ValueError("Demo mode requires a nonempty validated dataset.")
    categories = category_sales(sales)
    months = monthly_revenue(sales)
    products = top_products(sales)
    leader = categories.iloc[0]
    peak = months.loc[months["revenue"].idxmax()]
    limitations = [
        "Demo Mode uses precomputed templates and actual calculations. No AI request was made.",
        "Fictional sales data describes revenue only. Causes, profit, and forecasts are unavailable.",
    ]
    reports = [
        Report(SAMPLE_QUESTIONS[0], ["category_sales"],
               [f"{row.category} revenue: ${row.revenue:,.2f}; units sold: {row.units_sold}"
                for row in categories.itertuples()],
               [f"{leader['category']} generated the most revenue at ${leader['revenue']:,.2f}."],
               ["Review the category breakdown before choosing a product-level investigation."],
               list(limitations)),
        Report(SAMPLE_QUESTIONS[1], ["monthly_revenue"],
               [f"{row.month} revenue: ${row.revenue:,.2f}" for row in months.itertuples()],
               [f"{peak['month']} has the highest monthly revenue at ${peak['revenue']:,.2f}."],
               ["Investigate the month-to-month differences using additional operational evidence."],
               list(limitations)),
        Report(SAMPLE_QUESTIONS[2], ["top_products"],
               [f"{row.product} revenue: ${row.revenue:,.2f}" for row in products.itertuples()],
               [f"{products.iloc[0]['product']} leads product revenue at ${products.iloc[0]['revenue']:,.2f}."],
               ["Review availability and costs before making merchandising decisions."],
               list(limitations)),
        Report(SAMPLE_QUESTIONS[3], ["total_revenue"],
               [f"Total revenue: ${total_revenue(sales):,.2f}"],
               [f"Total revenue across the dataset is ${total_revenue(sales):,.2f}."],
               [], list(limitations)),
    ]
    return {report.question: report for report in reports}


def answer_question(question, sales, mode, demo_reports, live_runner=None):
    """Route modes explicitly. Tests can inject a live runner without network access."""
    if not question.strip():
        raise ValueError("Enter a business question before running analysis.")
    if mode == "Demo Mode":
        if question not in demo_reports:
            return Report(question, limitations=[
                "This question has no precomputed demo answer. Choose a suggested question or use Live Mode."
            ])
        return demo_reports[question]
    if mode != "Live Mode":
        raise ValueError("Choose Demo Mode or Live Mode.")
    if live_runner is None:
        from agent import run_agent

        live_runner = run_agent
    return parse_report(live_runner(question, sales), question)
