"""
Streamlit UI renderers for Mermaid diagrams and relationship graphs.
"""

import streamlit as st
import streamlit.components.v1 as components
import json
from typing import List, Dict, Any


def render_mermaid_diagram(mermaid_code: str, height: int = 600, diagram_title: str = "📊 Diagram"):
    """
    Render a Mermaid diagram using HTML components.
    
    Args:
        mermaid_code: Mermaid diagram code
        height: Height in pixels
        diagram_title: Title to display
    """
    st.markdown(f"### {diagram_title}")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
        <style>
            body {{
                background-color: #0e1117;
                margin: 0;
                padding: 20px;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: {height}px;
            }}
            .mermaid {{
                background-color: #161b22;
                border-radius: 8px;
                padding: 20px;
                border: 1px solid #30363d;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid">
{mermaid_code}
        </div>
        <script>
            mermaid.initialize({{startOnLoad: true, theme: 'dark'}});
            mermaid.contentLoaded();
        </script>
    </body>
    </html>
    """
    
    components.html(html_content, height=height + 50, scrolling=False)


def render_relationship_graph(
    entity_name: str,
    entity_type: str,
    relationships: Dict[str, Any],
    height: int = 700,
    title: str = "📊 Relationship Graph"
):
    """
    Render an interactive relationship graph using vis.js.
    
    Args:
        entity_name: Name of central entity
        entity_type: Type of entity (Class, Function, etc.)
        relationships: Dict with "outgoing" and "incoming" relationships
        height: Height in pixels
        title: Title to display
    """
    
    st.markdown(f"### {title}")
    
    if not relationships:
        st.warning("No relationship data provided")
        return
    
    outgoing = relationships.get("outgoing", [])
    incoming = relationships.get("incoming", [])
    
    html_content = _generate_vis_html(
        entity_name=entity_name,
        entity_type=entity_type,
        outgoing=outgoing,
        incoming=incoming,
        height=height
    )
    
    try:
        components.html(html_content, height=height, scrolling=False)
    except Exception as e:
        st.error(f"Failed to render graph: {str(e)}")


def _generate_vis_html(
    entity_name: str,
    entity_type: str,
    outgoing: List[Dict[str, str]],
    incoming: List[Dict[str, str]],
    height: int = 700
) -> str:
    """Generate HTML with vis.js interactive graph."""
    
    nodes = []
    edges = []
    node_ids = set()
    
    # Central node
    nodes.append({
        "id": entity_name,
        "label": entity_name,
        "title": f"{entity_name} ({entity_type})",
        "color": {
            "background": "#FF6B6B",
            "border": "#FF5252",
        },
        "font": {"size": 18, "bold": {"color": "#FFFFFF"}},
        "size": 35,
        "shape": "dot"
    })
    node_ids.add(entity_name)
    
    # Outgoing
    for rel in outgoing:
        target = rel.get("target", "Unknown")
        rel_type = rel.get("type", "CONNECTS")
        
        if target not in node_ids:
            nodes.append({
                "id": target,
                "label": target,
                "color": {"background": "#4ECDC4", "border": "#3DB8AF"},
                "font": {"size": 14, "color": "#FFFFFF"},
                "size": 25,
                "shape": "dot"
            })
            node_ids.add(target)
        
        edges.append({
            "from": entity_name,
            "to": target,
            "label": rel_type,
            "color": {"color": "#4ECDC4"},
            "arrows": "to",
            "font": {"size": 12, "align": "middle"},
            "smooth": {"type": "continuous"}
        })
    
    # Incoming
    for rel in incoming:
        source = rel.get("source", "Unknown")
        rel_type = rel.get("type", "CONNECTS")
        
        if source not in node_ids:
            nodes.append({
                "id": source,
                "label": source,
                "color": {"background": "#FFE66D", "border": "#FFC944"},
                "font": {"size": 14, "color": "#000000"},
                "size": 25,
                "shape": "dot"
            })
            node_ids.add(source)
        
        edges.append({
            "from": source,
            "to": entity_name,
            "label": rel_type,
            "color": {"color": "#FFE66D"},
            "arrows": "to",
            "font": {"size": 12, "align": "middle"},
            "smooth": {"type": "continuous"}
        })
    
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet" />
        <style>
            * {{ margin: 0; padding: 0; }}
            html, body {{ width: 100%; height: 100%; font-family: Arial, sans-serif; }}
            #network {{
                width: 100%;
                height: 100%;
                background-color: #0e1117;
                border: 1px solid #30363d;
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <div id="network"></div>
        <script>
            var nodes = new vis.DataSet({json.dumps(nodes)});
            var edges = new vis.DataSet({json.dumps(edges)});
            var data = {{ nodes: nodes, edges: edges }};
            var options = {{
                physics: {{
                    enabled: true,
                    barnesHut: {{
                        gravitationalConstant: -20000,
                        centralGravity: 0.3,
                        springLength: 200
                    }}
                }},
                interaction: {{navigationButtons: true, keyboard: true}},
                edges: {{arrows: {{to: {{enabled: true}}}}, smooth: {{type: 'continuous'}}}},
                nodes: {{shadow: {{enabled: true, color: 'rgba(0,0,0,0.5)', size: 10}}}}
            }};
            var network = new vis.Network(
                document.getElementById('network'),
                data,
                options
            );
            network.fit();
        </script>
    </body>
    </html>
    """
    
    return html_template


def extract_relationships_from_results(query_results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Extract relationship data from Neo4j query results.
    """
    outgoing = []
    incoming = []
    seen = set()
    
    for result in query_results:
        if not isinstance(result, dict):
            continue
        
        if "target" in result and "relationship_type" in result:
            key = (result.get("target"), result.get("relationship_type"))
            if key not in seen:
                seen.add(key)
                outgoing.append({
                    "target": result.get("target", "Unknown"),
                    "type": result.get("relationship_type", "CONNECTS")
                })
        
        if "source" in result and "relationship_type" in result:
            key = (result.get("source"), result.get("relationship_type"))
            if key not in seen:
                seen.add(key)
                incoming.append({
                    "source": result.get("source", "Unknown"),
                    "type": result.get("relationship_type", "CONNECTS")
                })
    
    return {"outgoing": outgoing, "incoming": incoming}