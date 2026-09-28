import logging
import json
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

import igraph as ig
import leidenalg as la
import networkx as nx
from neo4j import GraphDatabase

from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
neo4j_driver = GraphDatabase.driver(
    settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
)


@dataclass
class CommunitySummary:
    community_id: int
    level: int
    member_nodes: List[str]
    summary: str
    keywords: List[str]
    parent_community: Optional[int] = None
    child_communities: List[int] = field(default_factory=list)
    size: int = 0


class LeidenCommunityDetector:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.graph: Optional[ig.Graph] = None
        self.node_id_to_idx: Dict[str, int] = {}
        self.idx_to_node_id: Dict[int, str] = {}
        self.communities: Dict[int, CommunitySummary] = {}

    def build_igraph_from_neo4j(self) -> ig.Graph:
        with neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (n:Entity {tenant_id: $tenant_id})
                OPTIONAL MATCH (n)-[r:RELATION]-(m:Entity {tenant_id: $tenant_id})
                RETURN n.id as source, m.id as target, type(r) as rel_type
                """,
                tenant_id=self.tenant_id
            )
            
            edges = []
            nodes = set()
            for record in result:
                source = record["source"]
                target = record["target"]
                if source and target:
                    edges.append((source, target))
                    nodes.add(source)
                    nodes.add(target)
                elif source:
                    nodes.add(source)
            
            self.node_id_to_idx = {node_id: idx for idx, node_id in enumerate(nodes)}
            self.idx_to_node_id = {idx: node_id for node_id, idx in self.node_id_to_idx.items()}
            
            g = ig.Graph()
            g.add_vertices(len(nodes))
            
            for source, target in edges:
                if source in self.node_id_to_idx and target in self.node_id_to_idx:
                    g.add_edge(self.node_id_to_idx[source], self.node_id_to_idx[target])
            
            self.graph = g
            logger.info(f"Built iGraph with {g.vcount()} nodes and {g.ecount()} edges for tenant {self.tenant_id}")
            return g

    def detect_communities(self, resolution: float = 1.0) -> Dict[int, int]:
        if self.graph is None:
            self.build_igraph_from_neo4j()
        
        if self.graph.vcount() == 0:
            return {}
        
        partition = la.find_partition(
            self.graph, 
            la.RBConfigurationVertexPartition,
            resolution_parameter=resolution
        )
        
        membership = partition.membership
        node_to_community = {}
        for idx, comm_id in enumerate(membership):
            node_id = self.idx_to_node_id[idx]
            node_to_community[node_id] = comm_id
        
        logger.info(f"Detected {len(set(membership))} communities at resolution {resolution}")
        return node_to_community

    def detect_hierarchical_communities(self, resolutions: List[float] = None) -> Dict[int, Dict[str, int]]:
        if resolutions is None:
            resolutions = [0.5, 1.0, 1.5, 2.0]
        
        hierarchical = {}
        for level, resolution in enumerate(resolutions):
            comm_map = self.detect_communities(resolution)
            hierarchical[level] = comm_map
        
        return hierarchical

    def generate_community_summaries(self, node_to_community: Dict[str, int], level: int) -> Dict[int, CommunitySummary]:
        comm_members = defaultdict(list)
        for node_id, comm_id in node_to_community.items():
            comm_members[comm_id].append(node_id)
        
        summaries = {}
        for comm_id, members in comm_members.items():
            if len(members) < 2:
                continue
            
            summary = self._summarize_community(members)
            keywords = self._extract_keywords(members)
            
            summaries[comm_id] = CommunitySummary(
                community_id=comm_id,
                level=level,
                member_nodes=members,
                summary=summary,
                keywords=keywords,
                size=len(members)
            )
        
        return summaries

    def _summarize_community(self, member_nodes: List[str]) -> str:
        if not settings.OPENAI_API_KEY:
            return f"Community with {len(member_nodes)} entities: {', '.join(member_nodes[:10])}"
        
        with neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (n:Entity {tenant_id: $tenant_id})
                WHERE n.id IN $members
                OPTIONAL MATCH (n)-[r:RELATION]-(m:Entity {tenant_id: $tenant_id})
                WHERE m.id IN $members
                RETURN n.id as id, n.label as label, collect({rel: type(r), target: m.id, target_label: m.label}) as relations
                """,
                tenant_id=self.tenant_id,
                members=member_nodes[:50]
            )
            
            context_parts = []
            for record in result:
                relations = [f"{r['rel']} {r['target_label']}:{r['target']}" for r in record["relations"] if r["target"]]
                context_parts.append(f"{record['label']}:{record['id']} -> {', '.join(relations[:5])}")
        
        prompt = f"""
        Summarize this graph community in 2-3 sentences. Focus on the key entities and their relationships.
        
        Community members and relations:
        {chr(10).join(context_parts[:20])}
        """
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a knowledge graph analyst. Provide concise summaries of graph communities."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Community summary generation failed: {e}")
            return f"Community with {len(member_nodes)} entities"

    def _extract_keywords(self, member_nodes: List[str]) -> List[str]:
        with neo4j_driver.session() as session:
            result = session.run(
                """
                MATCH (n:Entity {tenant_id: $tenant_id})
                WHERE n.id IN $members
                RETURN n.label as label, count(*) as cnt
                ORDER BY cnt DESC
                LIMIT 10
                """,
                tenant_id=self.tenant_id,
                members=member_nodes
            )
            return [record["label"] for record in result]

    def build_hierarchy(self, hierarchical_communities: Dict[int, Dict[str, int]]) -> Dict[int, CommunitySummary]:
        all_summaries = {}
        
        for level, comm_map in hierarchical_communities.items():
            summaries = self.generate_community_summaries(comm_map, level)
            for comm_id, summary in summaries.items():
                global_comm_id = level * 10000 + comm_id
                summary.community_id = global_comm_id
                all_summaries[global_comm_id] = summary
        
        sorted_levels = sorted(hierarchical_communities.keys())
        for i in range(len(sorted_levels) - 1):
            lower_level = sorted_levels[i]
            higher_level = sorted_levels[i + 1]
            
            lower_map = hierarchical_communities[lower_level]
            higher_map = hierarchical_communities[higher_level]
            
            for node_id, lower_comm in lower_map.items():
                higher_comm = higher_map.get(node_id)
                if higher_comm is not None:
                    lower_global = lower_level * 10000 + lower_comm
                    higher_global = higher_level * 10000 + higher_comm
                    
                    if lower_global in all_summaries and higher_global in all_summaries:
                        all_summaries[lower_global].parent_community = higher_global
                        all_summaries[higher_global].child_communities.append(lower_global)
        
        self.communities = all_summaries
        return all_summaries

    def store_summaries_in_neo4j(self):
        with neo4j_driver.session() as session:
            for comm_id, summary in self.communities.items():
                query = """
                MERGE (c:Community {community_id: $comm_id, tenant_id: $tenant_id})
                SET c.level = $level,
                    c.summary = $summary,
                    c.keywords = $keywords,
                    c.size = $size,
                    c.parent_community = $parent,
                    c.child_communities = $children,
                    c.updated_at = datetime()
                """
                session.run(query, {
                    "comm_id": comm_id,
                    "tenant_id": self.tenant_id,
                    "level": summary.level,
                    "summary": summary.summary,
                    "keywords": summary.keywords,
                    "size": summary.size,
                    "parent": summary.parent_community,
                    "children": summary.child_communities
                })
            
            for comm_id, summary in self.communities.items():
                if summary.member_nodes:
                    query = """
                    UNWIND $members as member_id
                    MATCH (n:Entity {id: member_id, tenant_id: $tenant_id})
                    MATCH (c:Community {community_id: $comm_id, tenant_id: $tenant_id})
                    MERGE (n)-[:BELONGS_TO]->(c)
                    """
                    session.run(query, {
                        "members": summary.member_nodes,
                        "tenant_id": self.tenant_id,
                        "comm_id": comm_id
                    })
        
        logger.info(f"Stored {len(self.communities)} community summaries in Neo4j")

    def get_community_context_for_query(self, query: str, max_communities: int = 5) -> str:
        if not self.communities:
            return ""
        
        query_embedding = self._get_query_embedding(query)
        if not query_embedding:
            return ""
        
        comm_texts = []
        for comm in self.communities.values():
            comm_texts.append(f"Community {comm.community_id}: {comm.summary} | Keywords: {', '.join(comm.keywords)}")
        
        if not comm_texts:
            return ""
        
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        
        comm_embeddings = []
        for text in comm_texts:
            emb = self._get_text_embedding(text)
            comm_embeddings.append(emb)
        
        if not comm_embeddings:
            return ""
        
        query_emb = np.array(query_embedding).reshape(1, -1)
        comm_embs = np.array(comm_embeddings)
        similarities = cosine_similarity(query_emb, comm_embs)[0]
        
        top_indices = similarities.argsort()[-max_communities:][::-1]
        selected = [comm_texts[i] for i in top_indices if similarities[i] > 0.3]
        
        return "\n".join(selected)

    def _get_query_embedding(self, query: str) -> List[float]:
        if not settings.OPENAI_API_KEY:
            return [0.0] * 1536
        try:
            emb_res = openai_client.embeddings.create(
                input=query, model="text-embedding-3-small"
            )
            return emb_res.data[0].embedding
        except Exception:
            return [0.0] * 1536

    def _get_text_embedding(self, text: str) -> List[float]:
        if not settings.OPENAI_API_KEY:
            return [0.0] * 1536
        try:
            emb_res = openai_client.embeddings.create(
                input=text, model="text-embedding-3-small"
            )
            return emb_res.data[0].embedding
        except Exception:
            return [0.0] * 1536


def run_community_detection(tenant_id: str) -> Dict[int, CommunitySummary]:
    detector = LeidenCommunityDetector(tenant_id)
    hierarchical = detector.detect_hierarchical_communities()
    detector.build_hierarchy(hierarchical)
    detector.store_summaries_in_neo4j()
    return detector.communities


def get_community_summaries_for_query(tenant_id: str, query: str) -> str:
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (c:Community {tenant_id: $tenant_id})
            RETURN c.community_id as id, c.summary as summary, c.keywords as keywords, c.level as level
            ORDER BY c.level, c.size DESC
            LIMIT 20
            """,
            tenant_id=tenant_id
        )
        communities = []
        for record in result:
            communities.append(f"Community {record['id']} (L{record['level']}): {record['summary']} | Keywords: {', '.join(record['keywords'])}")
        
        if not communities:
            return ""
        
        return "\n".join(communities)