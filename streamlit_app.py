from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

import visualize_street_lights as vsl


st.set_page_config(page_title="Street Light Views", layout="wide")
st.markdown(
        """
        <style>
            #MainMenu, footer, header { visibility: hidden; }
            html, body, .stApp { height: 100%; }
            div[data-testid="stAppViewContainer"] { height: 100vh; overflow: hidden; }
            div[data-testid="stAppViewContainer"] > .main { height: 100vh; }
            div[data-testid="stAppViewContainer"] > .main > div { height: 100%; }
            div.block-container { padding: 0; max-width: 100%; }
            div[data-testid="stHtml"] iframe,
            div[data-testid="stIFrame"] iframe,
            iframe[title="streamlit-component"] {
                width: 100% !important;
                height: calc(100vh - 1px) !important;
                border: 0;
            }
        </style>
        """,
        unsafe_allow_html=True,
)


@st.cache_data(show_spinner=True)
def build_html() -> str:
    payload = vsl.load_payload()
    data = vsl.normalize_payload(payload)
    stable_html = vsl.inject_data(vsl.load_template(), data)
    heatmap_html = vsl.render_folium_map(data)
    return vsl.build_tabbed_html(stable_html, heatmap_html)


try:
    html = build_html()
except FileNotFoundError as exc:
    st.error(f"Missing file: {exc}")
    st.stop()
except ModuleNotFoundError as exc:
    st.error("Missing dependency. Install: pip install folium")
    st.stop()
except Exception as exc:  # pragma: no cover - safety net for Streamlit display
    st.exception(exc)
    st.stop()

components.html(html, height=1000, scrolling=False)
