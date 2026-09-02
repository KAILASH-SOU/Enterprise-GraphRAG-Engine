from pydantic import BaseModel, Field
from typing import List, Dict, Any

class Node(BaseModel):
    id: str = Field(description="Unique identifier for the node (e.g., entity name)")
    label: str = Field(description="Type of entity (e.g., PERSON, ORGANIZATION, CONCEPT)")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional properties of the entity")

class Edge(BaseModel):
    source_id: str = Field(description="ID of the source node")
    target_id: str = Field(description="ID of the target node")
    relation_type: str = Field(description="Type of relationship (e.g., WORKS_FOR, LOCATED_IN)")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional properties of the relationship")

class GraphExtraction(BaseModel):
    nodes: List[Node] = Field(description="List of extracted entities")
    edges: List[Edge] = Field(description="List of extracted relationships")
