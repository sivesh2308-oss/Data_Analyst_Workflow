"""
ui_theme.py
-------------
Shared visual identity for all three apps: a consistent color system, custom
metric cards (more control than Streamlit's default st.metric), and a chart
color palette used meaningfully (not randomly) across every chart.

Palette (paper background, ink text, one confident primary + 3 meaningful
accents -- not the generic "SaaS card kit" look):
  paper   #FAFAF8   page background
  ink     #161B22   primary text
  muted   #5B6472   secondary text
  indigo  #4F46E5   primary metric (totals, revenue)
  teal    #0EA5A5   positive / growth
  coral   #F2545B   warnings / negative values / outliers
  amber   #F5A623   category breakdowns / highlights
"""

import streamlit as st

COLORS = {
    "paper": "#FAFAF8",
    "surface": "#FFFFFF",
    "ink": "#161B22",
    "muted": "#5B6472",
    "border": "#E7E5DE",
    "indigo": "#4F46E5",
    "teal": "#0EA5A5",
    "coral": "#F2545B",
    "amber": "#F5A623",
}

# Cycled across multi-bar/category charts so each chart has a coherent,
# deliberate palette instead of one flat color or random matplotlib defaults.
CHART_PALETTE = [COLORS["indigo"], COLORS["teal"], COLORS["amber"], COLORS["coral"],
                  "#8B7FE8", "#5FC9C9", "#F7C766", "#F58A90"]


def apply_theme():
    """Inject font + component styling. Call once near the top of each app."""
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}
    h1, h2, h3 {{
        font-family: 'Sora', sans-serif !important;
        letter-spacing: -0.01em;
    }}
    h1 {{ color: {COLORS['ink']}; }}

    .metric-card {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-left: 4px solid var(--accent, {COLORS['indigo']});
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
    }}
    .metric-label {{
        font-size: 12.5px;
        color: {COLORS['muted']};
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
    }}
    .metric-value {{
        font-family: 'Sora', sans-serif;
        font-size: 24px;
        font-weight: 700;
        color: {COLORS['ink']};
    }}
    .metric-delta-up {{ color: {COLORS['teal']}; font-size: 13px; font-weight: 600; }}
    .metric-delta-down {{ color: {COLORS['coral']}; font-size: 13px; font-weight: 600; }}

    div[data-testid="stExpander"] {{
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
    }}
    </style>
    """, unsafe_allow_html=True)


def metric_card(label, value, accent="indigo", delta=None, delta_good="up"):
    """
    Render a styled metric card instead of the plain st.metric default.
    accent: key into COLORS for the left border ("indigo", "teal", "coral", "amber")
    delta: optional string like "+12.4%" -- colored teal/coral based on delta_good
    """
    color = COLORS.get(accent, COLORS["indigo"])
    delta_html = ""
    if delta is not None:
        is_up = str(delta).strip().startswith("+")
        cls = "metric-delta-up" if (is_up == (delta_good == "up")) else "metric-delta-down"
        delta_html = f'<div class="{cls}">{delta}</div>'
    st.markdown(f"""
    <div class="metric-card" style="--accent: {color}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def style_axes(ax):
    """Consistent, cleaner chart styling: no top/right spines, light gridlines."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["border"])
    ax.spines["bottom"].set_color(COLORS["border"])
    ax.grid(axis="y", color=COLORS["border"], linewidth=0.8, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=COLORS["muted"], labelsize=9)
    ax.title.set_color(COLORS["ink"])
    ax.title.set_fontsize(12)
    ax.title.set_fontweight("bold")
    return ax
