"""Print the Day 1 retail sales report."""

import argparse

from generate_data import DATA_PATH
from tools import category_sales, load_sales, monthly_revenue, top_products, total_revenue


def print_table(title, table):
    """Print a table with revenue formatted as US dollars."""
    print(f"\n{title}")
    print(table.to_string(index=False, formatters={"revenue": "${:,.2f}".format}))


def main():
    """Load the bundled data and display each sales metric."""
    parser = argparse.ArgumentParser(description="Analyze fictional retail sales.")
    parser.add_argument("--ask", help="Ask the OpenAI sales analyst a question.")
    args = parser.parse_args()
    try:
        sales = load_sales(DATA_PATH)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not load sales: {error}") from error

    if args.ask is not None:
        from agent import AgentError, run_agent

        try:
            print(run_agent(args.ask, sales))
        except AgentError as error:
            raise SystemExit(str(error)) from error
        return

    print(f"Retail sales report ({len(sales)} transactions)")
    print(f"Total revenue: ${total_revenue(sales):,.2f}")
    print_table("Category sales", category_sales(sales))
    print_table("Monthly revenue", monthly_revenue(sales))
    print_table("Top five products by revenue", top_products(sales))


if __name__ == "__main__":
    main()
