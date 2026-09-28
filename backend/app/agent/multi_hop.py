import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio

from openai import OpenAI
from app.core.config import settings
from app.core.cypher_middleware import CypherASTMiddleware, get_safe_neo4j_session

logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


@dataclass
class HopResult:
    path: List[Dict[str, Any]]
    score: float
    reasoning: str
    entities: List[str]
    relationships: List[str]


@dataclass
class MultiHopContext:
    query: str
    tenant_id: str
    initial_entities: List[str]
    hop_results: List[HopResult] = field(default_factory=list)
    visited_entities: Set[str] = field(default_factory=set)
    max_hops: int = 3
    max_paths_per_hop: int = 10


class MultiHopReasoner:
    def __init__(self, tenant_id: str, max_hops: int = 3, max_paths_per_hop: int = 10):
        self.tenant_id = tenant_id
        self.max_hops = max_hops
        self.max_paths_per_hop = max_paths_per_hop
        self.middleware = CypherASTMiddleware(tenant_id)

    async def find_seed_entities(self, query: str, limit: int = 5) -> List[str]:
        from app.core.database import qdrant_client
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        if not settings.OPENAI_API_KEY:
            return []
        
        try:
            emb_res = openai_client.embeddings.create(
                input=query, model="text-embedding-3-small"
            )
            query_vector = emb_res.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return []
        
        search_result = await qdrant_client.search(
            collection_name="chunks",
            query_vector=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=self.tenant_id))]
            ),
            limit=limit,
        )
        
        entities = set()
        for hit in search_result:
            payload = hit.payload
            if "extracted_nodes" in payload:
                entities.update(payload["extracted_nodes"])
        
        return list(entities)[:limit]

    async def execute_hop(self, context: MultiHopContext, hop: int, 
                          seed_entities: List[str]) -> List[HopResult]:
        if not seed_entities:
            return []
        
        placeholders = ", ".join([f"${i}" for i in range(len(seed_entities))])
        
        cypher = f"""
        MATCH path = (start:Entity {{tenant_id: $tenant_id}})-[:RELATION*1..{hop}]-(end:Entity {{tenant_id: $tenant_id}})
        WHERE start.id IN [{placeholders}]
        WITH path, 
             [node in nodes(path) | node.id] as entity_ids,
             [rel in relationships(path) | type(rel)] as rel_types,
             length(path) as path_len
        RETURN path, entity_ids, rel_types, path_len
        ORDER BY path_len, rand()
        LIMIT $limit
        """
        
        params = {"tenant_id": self.tenant_id, "limit": self.max_paths_per_hop}
        for i, entity in enumerate(seed_entities):
            params[str(i)] = entity
        
        results = []
        try:
            safe_session_factory = get_safe_neo4j_session(self.tenant_id)
            async for session in safe_session_factory():
                result = await session.run(cypher, **params)
                records = await result.data()
                
                for record in records:
                    path_data = record["path"]
                    entity_ids = record["entity_ids"]
                    rel_types = record["rel_types"]
                    path_len = record["path_len"]
                    
                    new_entities = [e for e in entity_ids if e not in context.visited_entities]
                    if not new_entities and hop > 1:
                        continue
                    
                    reasoning = await self._score_path(query=context.query, 
                                                      entities=entity_ids, 
                                                      relations=rel_types,
                                                      path_length=path_len)
                    
                    hop_result = HopResult(
                        path=entity_ids,
                        score=reasoning.get("score", 0.5),
                        reasoning=reasoning.get("reasoning", ""),
                        entities=entity_ids,
                        relationships=rel_types
                    )
                    results.append(hop_result)
                    
                    context.visited_entities.update(entity_ids)
                    
        except Exception as e:
            logger.error(f"Hop {hop} execution failed: {e}")
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:self.max_paths_per_hop]

    async def _score_path(self, query: str, entities: List[str], 
                          relations: List[str], path_length: int) -> Dict[str, Any]:
        if not settings.OPENAI_API_KEY:
            return {"score": 1.0 / path_length, "reasoning": "Mock scoring"}
        
        path_desc = " -> ".join([f"{e} ({r})" for e, r in zip(entities[:-1], relations)]) + f" -> {entities[-1]}"
        
        prompt = f"""
        Score this graph path's relevance to the query on a scale of 0.0 to 1.0.
        
        Query: {query}
        Path: {path_desc}
        Path length: {path_length}
        
        Consider:
        - Semantic relevance of entities to query
        - Relationship types relevance
        - Path conciseness (shorter paths preferred for direct answers)
        
        Respond with JSON:
        {{"score": 0.0-1.0, "reasoning": "brief explanation"}}
        """
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a graph path relevance scorer. Output only JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=150
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Path scoring failed: {e}")
            return {"score": 0.5, "reasoning": "Scoring failed"}

    async def cross_document_search(self, query: str, entities: List[str]) -> List[Dict[str, Any]]:
        from app.core.database import qdrant_client
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        if not entities or not settings.OPENAI_API_KEY:
            return []
        
        try:
            emb_res = openai_client.embeddings.create(
                input=query, model="text-embedding-3-small"
            )
            query_vector = emb_res.data[0].embedding
        except Exception:
            return []
        
        entity_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=self.tenant_id)),
                FieldCondition(key="extracted_nodes", match=MatchValue(value=entities[0]))
            ]
        )
        
        try:
            search_result = await qdrant_client.search(
                collection_name="chunks",
                query_vector=query_vector,
                query_filter=entity_filter,
                limit=5,
            )
            return [hit.payload for hit in search_result]
        except Exception as e:
            logger.error(f"Cross-document search failed: {e}")
            return []

    async def reason(self, query: str) -> MultiHopContext:
        context = MultiHopContext(
            query=query,
            tenant_id=self.tenant_id,
            initial_entities=[],
            max_hops=self.max_hops,
            max_paths_per_hop=self.max_paths_per_hop
        )
        
        seed_entities = await self.find_seed_entities(query)
        context.initial_entities = seed_entities
        context.visited_entities.update(seed_entities)
        
        logger.info(f"Multi-hop reasoning started for tenant {self.tenant_id}, seeds: {seed_entities}")
        
        for hop in range(1, self.max_hops + 1):
            current_seeds = list(context.visited_entities)[-self.max_paths_per_hop:]
            hop_results = await self.execute_hop(context, hop, current_seeds)
            
            if not hop_results:
                logger.info(f"No more paths found at hop {hop}")
                break
            
            context.hop_results.extend(hop_results)
            
            new_seeds = set()
            for result in hop_results[:3]:
                new_seeds.update(result.entities[-2:])
            
            if not new_seeds - context.visited_entities:
                break
        
        cross_doc_results = await self.cross_document_search(query, list(context.visited_entities))
        context.cross_document_chunks = cross_doc_results
        
        return context

    def build_context_string(self, context: MultiHopContext) -> str:
        parts = []
        
        if context.initial_entities:
            parts.append(f"Seed Entities: {', '.join(context.initial_entities)}")
        
        if context.hop_results:
            parts.append("Graph Paths Found:")
            for i, hop in enumerate(context.hop_results):
                path_str = " -> ".join(hop.entities)
                rel_str = " | ".join(hop.relationships)
                parts.append(f"  Path {i+1} (score: {hop.score:.2f}): {path_str} [{rel_str}]")
                parts.append(f"    Reasoning: {hop.reasoning}")
        
        if hasattr(context, 'cross_document_chunks') and context.cross_document_chunks:
            parts.append("Cross-Document Context:")
            for chunk in context.cross_document_chunks[:3]:
                parts.append(f"  - {chunk.get('text', '')[:200]}...")
        
        return "\n".join(parts)


async def enhanced_graph_traversal(tenant_id: str, query: str, max_hops: int = 3) -> Dict[str, Any]:
    reasoner = MultiHopReasoner(tenant_id, max_hops=max_hops)
    context = await reasoner.reason(query)
    return {
        "graph_paths": [r.path for r in context.hop_results],
        "path_scores": [r.score for r in context.hop_results],
        "path_reasoning": [r.reasoning for r in context.hop_results],
        "cross_document_chunks": getattr(context, 'cross_document_chunks', []),
        "context_string": reasoner.build_context_string(context),
        "visited_entities": list(context.visited_entities)
    }