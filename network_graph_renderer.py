import streamlit as st
import streamlit.components.v1 as components
from typing import List, Dict, Any, Tuple

def extract_nodes_and_edges(
    entity_name: str,
    entity_type: str,
    query_results: List[Dict[str, Any]]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract nodes and edges from Neo4j query results.
    
    Returns: (nodes, edges)
    """
    nodes = []
    edges = []
    node_ids = set()
    
    # Add primary node
    primary_node = {
        "id": entity_name,
        "label": entity_name,
        "title": f"{entity_type}: {entity_name}",
        "color": "#FF6B6B",
        "size": 40,
        "font": {"size": 16, "color": "white"}
    }
    nodes.append(primary_node)
    node_ids.add(entity_name)
    
    # Extract relationships from results
    for result in query_results:
        if isinstance(result, dict):
            # Look for source/target patterns
            source = result.get("source") or result.get("source_name") or result.get("from_node")
            target = result.get("target") or result.get("target_name") or result.get("to_node")
            rel_type = result.get("relationship_type") or result.get("type") or "RELATED"
            
            if source and target:
                # Add source node
                if source not in node_ids:
                    nodes.append({
                        "id": source,
                        "label": source,
                        "title": f"{source}",
                        "color": "#4ECDC4",
                        "size": 30,
                        "font": {"size": 14}
                    })
                    node_ids.add(source)
                
                # Add target node
                if target not in node_ids:
                    nodes.append({
                        "id": target,
                        "label": target,
                        "title": f"{target}",
                        "color": "#FFE66D",
                        "size": 30,
                        "font": {"size": 14}
                    })
                    node_ids.add(target)
                
                # Add edge
                edges.append({
                    "from": source,
                    "to": target,
                    "label": rel_type,
                    "title": rel_type,
                    "font": {"size": 12},
                    "arrows": "to"
                })
    
    # Fallback: if no edges found, add some context nodes
    if not edges and len(nodes) == 1:
        context_nodes = [
            {"id": "ctx1", "label": "No relationships", "color": "#CCCCCC", "size": 20},
            {"id": "ctx2", "label": "found", "color": "#CCCCCC", "size": 20},
            {"id": "ctx3", "label": "in database", "color": "#CCCCCC", "size": 20},
        ]
        nodes.extend(context_nodes)
        edges = [
            {"from": entity_name, "to": "ctx1", "label": "...", "dashes": True},
            {"from": "ctx1", "to": "ctx2", "label": "...", "dashes": True},
            {"from": "ctx2", "to": "ctx3", "label": "...", "dashes": True},
        ]
    
    return nodes, edges


def render_network_graph(
    nodes: List[Dict],
    edges: List[Dict],
    height: int = 700,
    title: str = "Network Graph"
):
    """
    Render interactive network graph using vis.js.
    """
    import json
    
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    
    html_code = f"""
    <html>
    <head>
        <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>
            #network {{
                width: 100%;
                height: {height}px;
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: #161b22;
            }}
            .vis-network {{
                background-color: #161b22;
            }}
            .vis-label {{
                color: white;
            }}
        </style>
    </head>
    <body>
        <div id="network"></div>
        <script type="text/javascript">
            var nodes = new vis.DataSet({nodes_json});
            var edges = new vis.DataSet({edges_json});
            
            var container = document.getElementById('network');
            var data = {{
                nodes: nodes,
                edges: edges
            }};
            
            var options = {{
                physics: {{
                    enabled: true,
                    barnesHut: {{
                        gravitationalConstant: -26000,
                        centralGravity: 0.005,
                        springLength: 200,
                        springConstant: 0.04
                    }},
                    maxVelocity: 50,
                    stabilization: {{iterations: 200}}
                }},
                interaction: {{
                    navigationButtons: true,
                    keyboard: true,
                    zoomView: true,
                    dragView: true
                }},
                nodes: {{
                    font: {{
                        size: 16,
                        color: "white"
                    }},
                    borderWidth: 2,
                    borderWidthSelected: 4,
                    shadow: {{
                        enabled: true,
                        color: 'rgba(0,0,0,0.5)',
                        size: 10,
                        x: 5,
                        y: 5
                    }}
                }},
                edges: {{
                    font: {{size: 12, color: "white", align: "middle"}},
                    color: {{color: '#4ECDC4', highlight: '#FF6B6B'}},
                    arrows: {{to: {{enabled: true, scaleFactor: 0.5}}}},
                    smooth: {{type: 'continuous'}},
                    shadow: {{
                        enabled: true,
                        color: 'rgba(0,0,0,0.3)',
                        size: 5
                    }}
                }}
            }};
            
            var network = new vis.Network(container, data, options);
            network.fit();
        </script>
    </body>
    </html>
    """
    
    components.html(html_code, height=height + 50, scrolling=False)