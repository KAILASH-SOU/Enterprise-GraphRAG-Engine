import logging
from typing import Literal, Dict, Any, List
from openai import OpenAI
from pydantic import BaseModel
from app.core.config import settings
from app.core.database import qdrant_client
from app.core.cypher_middleware import get_safe_neo4j_session
from app.agent.multi_hop import enhanced_graph_traversal, MultiHopReasoner
from app.pipeline.community_detection import get_community_summaries_for_query
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


class RoutingStrategy(BaseModel):
    intent: Literal["VECTOR_SEARCH", "GRAPH_TRAVERSAL", "HYBRID", "COMMUNITY_SUMMARY"]
    reasoning: str


class AgenticRouter:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.multi_hop_reasoner = MultiHopReasoner(tenant_id, max_hops=3, max_paths_per_hop=10)

    async def classify_intent(self, query: str) -> RoutingStrategy:
        if not settings.OPENAI_API_KEY:
            return RoutingStrategy(intent="HYBRID", reasoning="Mock LLM intent")
        
        try:
            response = openai_client.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a query intent classifier. Decide the best search strategy: VECTOR_SEARCH (direct factual lookup), GRAPH_TRAVERSAL (multi-hop relational question), HYBRID (requires both text and relational context), or COMMUNITY_SUMMARY (broad overview/summary questions needing hierarchical graph summaries)."},
                    {"role": "user", "content": query}
                ],
                response_format=RoutingStrategy,
            )
            return response.choices[0].message.parsed
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return RoutingStrategy(intent="HYBRID", reasoning="Fallback due to error")

    async def vector_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not settings.OPENAI_API_KEY:
            return []
            
        try:
            emb_res = openai_client.embeddings.create(input=query, model="text-embedding-3-small")
            query_vector = emb_res.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            query_vector = [0.0] * 1536
            
        search_result = await qdrant_client.search(
            collection_name="chunks",
            query_vector=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=self.tenant_id))]
            ),
            limit=limit,
        )
        return [hit.payload for hit in search_result]

    async def graph_traversal(self, query: str) -> Dict[str, Any]:
        return await enhanced_graph_traversal(self.tenant_id, query, max_hops=3)

    async def community_summary_search(self, query: str) -> Dict[str, Any]:
        community_context = get_community_summaries_for_query(self.tenant_id, query)
        return {"community_context": community_context}

    async def execute(self, query: str) -> str:
        strategy = await self.classify_intent(query)
        logger.info(f"Routing strategy: {strategy.intent} - {strategy.reasoning}")
        
        context_parts = []
        
        if strategy.intent in ["VECTOR_SEARCH", "HYBRID"]:
            vector_results = await self.vector_search(query)
            context_parts.append("Text Context:\n" + "\n".join([v.get("text", "") for v in vector_results]))
            
        if strategy.intent in ["GRAPH_TRAVERSAL", "HYBRID"]:
            graph_results = await self.graph_traversal(query)
            context_parts.append("Graph Context (Multi-hop):\n" + graph_results.get("context_string", ""))
            
        if strategy.intent == "COMMUNITY_SUMMARY":
            comm_results = await self.community_summary_search(query)
            context_parts.append("Community Summaries (Hierarchical):\n" + comm_results.get("community_context", ""))
            vector_results = await self.vector_search(query, limit=3)
            context_parts.append("Supporting Text Context:\n" + "\n".join([v.get("text", "") for v in vector_results]))
        
        combined_context = "\n\n".join(context_parts)
        
        if not settings.OPENAI_API_KEY:
            return f"Mock synthesized response for {strategy.intent}. Context: {combined_context}"
            
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Answer the user query using the provided text, graph paths, and community summaries. Cite your sources and explain your reasoning."},
                    {"role": "user", "content": f"Query: {query}\n\nContext:\n{combined_context}"}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return "Failed to generate response."