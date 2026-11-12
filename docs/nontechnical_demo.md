# InsightAgent · Three-minute demo

## 0:00–0:35 · The idea

Imagine a shop manager opening a box of receipts. Each receipt says what sold,
when it sold, how many items were purchased, and the price. The manager wants to
understand the shop without adding every receipt by hand.

InsightAgent is like a helpful colleague sitting beside a calculator. The calculator
does the arithmetic. The colleague chooses which calculation to ask for and explains
the result. This project uses fictional receipts so we can demonstrate the workflow
without using anyone's private business data.

## 0:35–1:15 · Explore the sales

Open **Sales Dashboard**. With every category and the full date range selected,
we see **$12,951.00 in revenue, 240 transactions, and 717 units sold**.

Hover over a monthly point to inspect the exact amount. Then compare the category
bars and the leading products. Every chart comes from the same receipts as the
headline numbers.

Select **Home** in the category filter. Revenue changes to **$3,882.50**. The charts
also change. We are now looking at one part of the shop. Clear every category to
show the empty-state message, then restore them. This helps explain why an empty
selection should never quietly show the entire business.

## 1:15–2:00 · Ask the analyst

Open **AI Analyst** in **Demo Mode**. Choose “Which category generated the most
revenue?” and press **Run Analysis**. The answer identifies Electronics, with
**$4,196.50** in revenue.

Demo Mode uses prepared explanations and real calculations. It works without an
API key and makes no AI request. Open “Underlying tools used” to see the calculation
behind the answer. Open the metrics and limitations to inspect the evidence.

In **Live Mode**, a language model chooses from the same trusted calculation tools
and writes an explanation. It also gets a chance to revise statements that fail
verification. Each question uses the complete dataset. The dashboard filters belong
only to the dashboard, and each question starts a fresh analysis.

## 2:00–2:35 · A second way to explore

Open **Tableau Intelligence**. This is my independently published Tableau dashboard,
presented alongside the Python application. It keeps its own controls and data.
If the embedded dashboard cannot load, use **Open full Tableau dashboard**.
The local demo can work offline, while Tableau needs an internet connection.

## 2:35–3:00 · What the answer means

Revenue tells us what sold, but it cannot tell us profit without costs. It also
cannot explain why sales changed or predict the future. Recommendations are prompts
for investigation. A person still decides what action makes sense.

The portfolio demonstrates how to connect questions, dependable arithmetic, and
clear visual evidence in one small application.

## Optional historical Olist walkthrough

After preparing the three derived files with [these instructions](historical_dashboard.md),
open **Olist historical forecasts**. This is a separate public historical dataset,
in BRL, not the fictional USD shop or today's Olist business.

Compare recorded weekly values with predictions made using only earlier weeks.
Change the chart dates and methods; the global error comparison stays fixed.
Read MAE as average money missed and WAPE as an error percentage, not accuracy.
Explain honestly if the simple baseline beats ridge. Open the chart evidence to
inspect exact target-week values.

If the illustration is **Unavailable**, explain why no amount is shown: a partial
boundary or suspicious source tail can make a zero misleading. Open the quality
evidence and distinguish calendar bounds from actual source coverage. The business
lesson is to check the evidence before trusting a prediction. This page works
without an OpenAI key and makes no model-training or AI request.
