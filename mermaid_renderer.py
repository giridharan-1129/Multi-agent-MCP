"""
Mermaid diagram rendering utilities for Streamlit.

Provides multiple rendering strategies for maximum compatibility across Streamlit versions.
Based on Mermaid.js documentation: https://mermaid.js.org/intro/
"""

import streamlit as st
import streamlit.components.v1 as components


def render_mermaid_diagram(mermaid_code: str, height: int = 600, diagram_title: str = "📊 Diagram"):
    """
    Render a Mermaid diagram using the most compatible method available.
    
    This function tries multiple rendering strategies:
    1. Try st.mermaid() if available (Streamlit >= 1.28)
    2. Fall back to components.html() with proper Mermaid.js CDN integration
    3. Last resort: Display code in expandable section
    
    Args:
        mermaid_code: Mermaid diagram code (e.g., "graph LR ...")
        height: Height of the rendering container in pixels
        diagram_title: Title for the diagram section
    """
    
    st.markdown(f"### {diagram_title}")
    
    # Strategy 1: Try native st.mermaid() (Streamlit >= 1.28)
    if hasattr(st, 'mermaid'):
        try:
            st.mermaid(mermaid_code)
            return
        except Exception as e:
            st.warning(f"⚠️ Native Mermaid rendering failed: {str(e)[:50]}... Trying alternative method...")
    
    # Strategy 2: Use components.html() with Mermaid.js from CDN
    try:
        html_content = _generate_mermaid_html(mermaid_code)
        components.html(html_content, height=height, scrolling=False)
        return
    except Exception as e:
        st.error(f"❌ HTML component rendering failed: {str(e)}")
    
    # Strategy 3: Last resort - show code
    st.warning("Could not render Mermaid diagram. Showing code instead:")
    st.code(mermaid_code, language="mermaid")


def _generate_mermaid_html(mermaid_code: str) -> str:
    """
    Generate complete HTML with Mermaid.js integration.
    
    Uses the approach from Mermaid documentation:
    - Embeds Mermaid code in <pre class="mermaid"> tags
    - Imports Mermaid from CDN using proper ES module syntax
    - Initializes with appropriate configuration
    - Spacious layout with generous padding and margins
    """
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
            }}
            
            body {{
                background-color: #0e1117;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                padding: 40px;
                display: flex;
                justify-content: center;
                align-items: flex-start;
                min-height: 100vh;
            }}
            
            .mermaid-container {{
                background-color: #161b22;
                border-radius: 16px;
                padding: 50px;
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.5);
                max-width: 95%;
                overflow-x: auto;
                overflow-y: auto;
                border: 1px solid #30363d;
            }}
            
            .mermaid {{
                display: flex;
                justify-content: center;
                align-items: flex-start;
                background-color: transparent;
                min-height: 400px;
            }}
            
            .mermaid svg {{
                max-width: 100%;
                height: auto;
                margin: 20px auto;
            }}
            
            pre.mermaid {{
                display: none;
            }}
            
            .error-message {{
                color: #f85149;
                padding: 30px;
                background-color: #161b22;
                border-radius: 12px;
                border-left: 5px solid #f85149;
                font-family: monospace;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid-container">
            <div id="mermaid-content">
                <pre class="mermaid">
{mermaid_code}
                </pre>
            </div>
        </div>

        <script type="module">
            // Import Mermaid from CDN as ES module
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
            
            (async () => {{
                try {{
                    // Configure Mermaid with spacious settings
                    mermaid.initialize({{
                        startOnLoad: false,
                        theme: 'dark',
                        securityLevel: 'loose',
                        flowchart: {{
                            useMaxWidth: true,
                            htmlLabels: true,
                            curve: 'linear',
                            padding: '30px',
                            nodeSpacing: 80,
                            rankSpacing: 100,
                            diagramMarginX: 40,
                            diagramMarginY: 40
                        }},
                        graph: {{
                            useMaxWidth: true,
                            htmlLabels: true,
                            curve: 'linear',
                            padding: '30px',
                            nodeSpacing: 80,
                            rankSpacing: 100,
                            diagramMarginX: 40,
                            diagramMarginY: 40
                        }},
                        logLevel: 'debug'
                    }});
                    
                    // Render the diagram
                    await mermaid.contentLoaded();
                    
                }} catch (error) {{
                    console.error('Mermaid rendering error:', error);
                    const container = document.getElementById('mermaid-content');
                    container.innerHTML = '<div class="error-message">⚠️ Rendering Error: ' + error.message + '</div>';
                }}
            }})();
        </script>
    </body>
    </html>
    """
    
    return html_template


def display_cypher_queries(queries: list, title: str = "🔍 Cypher Queries"):
    """
    Display Cypher queries in an expandable section.
    
    Args:
        queries: List of Cypher query strings
        title: Title for the expander
    """
    with st.expander(title):
        for idx, query in enumerate(queries, 1):
            st.write(f"**Query {idx}:**")
            st.code(query, language="cypher")
            st.divider()


def display_query_results(results: list, title: str = "📊 Query Results"):
    """
    Display query results in a formatted table.
    
    Args:
        results: List of result dictionaries
        title: Title for the section
    """
    if not results:
        st.warning("No results returned from query")
        return
    
    st.write(f"### {title}")
    st.write(f"Found **{len(results)}** results")
    
    # Display as table
    import pandas as pd
    try:
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)
    except:
        # Fallback to JSON display
        st.json(results)