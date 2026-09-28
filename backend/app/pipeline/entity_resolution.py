import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from openai import OpenAI
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.config import settings

logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
neo4j_driver = GraphDatabase.driver(
    settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
)
qdrant_sync = QdrantClient(url=settings.QDRANT_URL)


@dataclass
class EntityCandidate:
    id: str
    label: str
    properties: Dict[str, Any]
    embedding: List[float]
    tenant_id: str


@dataclass
class MergeDecision:
    canonical_id: str
    duplicate_ids: List[str]
    confidence: float
    reasoning: str


class EntityResolver:
    def __init__(self, tenant_id: str, similarity_threshold: float = 0.85):
        self.tenant_id = tenant_id
        self.similarity_threshold = similarity_threshold

    def get_entity_embedding(self, entity_text: str) -> List[float]:
        if not settings.OPENAI_API_KEY:
            return [0.0] * 1536
        try:
            emb_res = openai_client.embeddings.create(
                input=entity_text, model="text-embedding-3-small"
            )
            return emb_res.data[0].embedding
        except Exception as e:
            logger.error(f"Entity embedding failed: {e}")
            return [0.0] * 1536

    def fetch_existing_entities(self, label: Optional[str] = None) -> List[EntityCandidate]:
        candidates = []
        with neo4j_driver.session() as session:
            query = """
            MATCH (n:Entity {tenant_id: $tenant_id})
            """
            params = {"tenant_id": self.tenant_id}
            if label:
                query += " WHERE n.label = $label"
                params["label"] = label
            query += " RETURN n.id as id, n.label as label, properties(n) as props"
            
            result = session.run(query, params)
            for record in result:
                entity_text = f"{record['label']}: {record['id']}"
                embedding = self.get_entity_embedding(entity_text)
                candidates.append(EntityCandidate(
                    id=record["id"],
                    label=record["label"],
                    properties=record["props"],
                    embedding=embedding,
                    tenant_id=self.tenant_id
                ))
        return candidates

    def find_similar_entities(self, new_entity: EntityCandidate, 
                               existing: List[EntityCandidate],
                               top_k: int = 5) -> List[Tuple[EntityCandidate, float]]:
        if not existing:
            return []
        
        new_emb = np.array(new_entity.embedding).reshape(1, -1)
        existing_embs = np.array([e.embedding for e in existing])
        
        similarities = cosine_similarity(new_emb, existing_embs)[0]
        
        scored = [(existing[i], float(similarities[i])) for i in range(len(existing))]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [(e, s) for e, s in scored[:top_k] if s >= self.similarity_threshold]

    def llm_judge_merge(self, new_entity: EntityCandidate, 
                        candidate: EntityCandidate) -> MergeDecision:
        if not settings.OPENAI_API_KEY:
            return MergeDecision(
                canonical_id=candidate.id,
                duplicate_ids=[new_entity.id],
                confidence=0.0,
                reasoning="Mock LLM - no API key"
            )

        prompt = f"""
        Determine if these two entities refer to the same real-world entity.
        
        Entity A (existing): 
        - ID: {candidate.id}
        - Label: {candidate.label}
        - Properties: {candidate.properties}
        
        Entity B (new):
        - ID: {new_entity.id}
        - Label: {new_entity.label}
        - Properties: {new_entity.properties}
        
        Respond with JSON:
        {{
            "same_entity": true/false,
            "confidence": 0.0-1.0,
            "reasoning": "explanation",
            "canonical_name": "preferred canonical name"
        }}
        """

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an entity resolution expert. Determine if two entity references refer to the same real-world entity."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            import json
            result = json.loads(response.choices[0].message.content)
            
            if result.get("same_entity", False):
                return MergeDecision(
                    canonical_id=candidate.id,
                    duplicate_ids=[new_entity.id],
                    confidence=result.get("confidence", 0.0),
                    reasoning=result.get("reasoning", "")
                )
        except Exception as e:
            logger.error(f"LLM merge judgment failed: {e}")
        
        return MergeDecision(
            canonical_id=new_entity.id,
            duplicate_ids=[],
            confidence=0.0,
            reasoning="LLM judgment failed or entities are different"
        )

    def merge_entities(self, decision: MergeDecision) -> bool:
        if not decision.duplicate_ids:
            return False
        
        try:
            with neo4j_driver.session() as session:
                for dup_id in decision.duplicate_ids:
                    query = """
                    MATCH (dup:Entity {id: $dup_id, tenant_id: $tenant_id})
                    MATCH (canon:Entity {id: $canon_id, tenant_id: $tenant_id})
                    CALL apoc.refactor.mergeNodes([dup, canon], {properties: "combine"}) 
                    YIELD node
                    RETURN node
                    """
                    try:
                        session.run(query, {
                            "dup_id": dup_id,
                            "canon_id": decision.canonical_id,
                            "tenant_id": self.tenant_id
                        })
                    except Exception:
                        manual_merge = """
                        MATCH (dup:Entity {id: $dup_id, tenant_id: $tenant_id})-[r]-()
                        MATCH (canon:Entity {id: $canon_id, tenant_id: $tenant_id})
                        WHERE dup <> canon
                        MERGE (canon)-[r2:RELATION {type: type(r)}]->(endNode(r))
                        SET r2 += properties(r)
                        WITH dup, canon
                        MATCH (dup)-[r3]-()
                        DELETE r3
                        DETACH DELETE dup
                        """
                        session.run(manual_merge, {
                            "dup_id": dup_id,
                            "canon_id": decision.canonical_id,
                            "tenant_id": self.tenant_id
                        })
            logger.info(f"Merged entities: {decision.duplicate_ids} -> {decision.canonical_id}")
            return True
        except Exception as e:
            logger.error(f"Entity merge failed: {e}")
            return False

    def resolve_new_entity(self, entity_id: str, label: str, 
                           properties: Dict[str, Any]) -> str:
        new_entity = EntityCandidate(
            id=entity_id,
            label=label,
            properties=properties,
            embedding=self.get_entity_embedding(f"{label}: {entity_id}"),
            tenant_id=self.tenant_id
        )
        
        existing = self.fetch_existing_entities(label)
        similar = self.find_similar_entities(new_entity, existing)
        
        for candidate, similarity in similar:
            decision = self.llm_judge_merge(new_entity, candidate)
            if decision.confidence >= 0.8:
                self.merge_entities(decision)
                logger.info(f"Resolved {entity_id} -> {decision.canonical_id} (confidence: {decision.confidence})")
                return decision.canonical_id
        
        return entity_id


def resolve_entities_in_extraction(tenant_id: str, extraction) -> Any:
    resolver = EntityResolver(tenant_id)
    
    entity_map = {}
    for node in extraction.nodes:
        canonical_id = resolver.resolve_new_entity(node.id, node.label, node.properties)
        entity_map[node.id] = canonical_id
    
    for node in extraction.nodes:
        node.id = entity_map.get(node.id, node.id)
    
    for edge in extraction.edges:
        edge.source_id = entity_map.get(edge.source_id, edge.source_id)
        edge.target_id = entity_map.get(edge.target_id, edge.target_id)
    
    return extraction