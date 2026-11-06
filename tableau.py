"""The independent Tableau Public portfolio view and its supported v3 embed."""

TABLEAU_URL = (
    "https://public.tableau.com/views/InsightAgent-RetailSalesIntelligenceDashboard/"
    "InsightAgent-RetailSalesOverview"
)


def embed_html():
    """Keep the fallback visible if scripts, cookies, or external loading fail."""
    return f'''
    <style>
      body {{ margin: 0; font: 14px Arial, sans-serif; color: #243c44; }}
      a {{ color: #116d63; }}
      tableau-viz {{ display: block; width: 100%; height: 760px; }}
    </style>
    <p id="status" role="status">Loading the Tableau dashboard…
      <a href="{TABLEAU_URL}" target="_blank" rel="noopener noreferrer">Open full dashboard</a>
    </p>
    <tableau-viz id="portfolio-viz" src="{TABLEAU_URL}" toolbar="bottom" hide-tabs>
    </tableau-viz>
    <script type="module">
      const status = document.getElementById('status');
      const fallback = () => {{
        status.firstChild.textContent = 'The embedded view is unavailable or still loading. ';
      }};
      const timer = setTimeout(fallback, 15000);
      try {{
        const {{ TableauEventType }} = await import(
          'https://public.tableau.com/javascripts/api/tableau.embedding.3.latest.min.js'
        );
        const viz = document.getElementById('portfolio-viz');
        viz.addEventListener(TableauEventType.FirstInteractive, () => {{
          clearTimeout(timer);
          status.firstChild.textContent = 'Interactive dashboard loaded. ';
        }});
        viz.addEventListener(TableauEventType.VizLoadError, fallback);
      }} catch (error) {{ fallback(); }}
    </script>
    '''
