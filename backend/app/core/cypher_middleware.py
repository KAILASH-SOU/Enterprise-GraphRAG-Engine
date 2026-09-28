import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
from contextvars import ContextVar

logger = logging.getLogger(__name__)

tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")


class NodeType(Enum):
    PATTERN = "pattern"
    WHERE = "where"
    RETURN = "return"
    WITH = "with"
    MATCH = "match"
    MERGE = "merge"
    CREATE = "create"
    SET = "set"
    DELETE = "delete"
    CALL = "call"


@dataclass
class CypherPattern:
    variable: str
    labels: List[str]
    properties: Dict[str, Any]
    is_anonymous: bool = False


@dataclass
class ParsedCypher:
    original: str
    patterns: List[CypherPattern]
    where_clauses: List[str]
    return_clause: str
    has_tenant_filter: bool = False
    tenant_id: str = ""


class CypherASTMiddleware:
    NODE_PATTERN = re.compile(
        r'\((?P<var>[a-zA-Z_][a-zA-Z0-9_]*)?'
        r'(?P<labels>(?::[a-zA-Z_][a-zA-Z0-9_]*)*)'
        r'(?P<props>\{[^}]*\})?\)'
    )
    
    MATCH_CLAUSE = re.compile(
        r'\b(MATCH|OPTIONAL MATCH|MERGE|CREATE)\s+',
        re.IGNORECASE
    )
    
    WHERE_CLAUSE = re.compile(
        r'\bWHERE\s+(.+?)(?=\b(?:RETURN|WITH|ORDER BY|LIMIT|SKIP|UNION|$))',
        re.IGNORECASE | re.DOTALL
    )
    
    TENANT_PROP_PATTERN = re.compile(
        r'\btenant_id\s*[=:]',
        re.IGNORECASE
    )

    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or tenant_id_var.get("")

    def set_tenant_id(self, tenant_id: str):
        self.tenant_id = tenant_id
        tenant_id_var.set(tenant_id)

    def parse_patterns(self, query: str) -> List[CypherPattern]:
        patterns = []
        for match in self.NODE_PATTERN.finditer(query):
            var = match.group('var') or f"__anon_{len(patterns)}"
            labels_str = match.group('labels') or ""
            labels = [l[1:] for l in labels_str.split(':') if l]
            props_str = match.group('props') or "{}"
            is_anon = not match.group('var')
            
            props = {}
            try:
                prop_content = props_str[1:-1].strip()
                if prop_content:
                    for prop_match in re.finditer(r'(\w+)\s*:\s*([^,]+)', prop_content):
                        key = prop_match.group(1).strip()
                        val = prop_match.group(2).strip().strip('"\'')
                        props[key] = val
            except Exception:
                pass
            
            patterns.append(CypherPattern(
                variable=var,
                labels=labels,
                properties=props,
                is_anonymous=is_anon
            ))
        
        return patterns

    def has_tenant_filter(self, query: str) -> bool:
        return bool(self.TENANT_PROP_PATTERN.search(query))

    def inject_tenant_constraints(self, query: str, tenant_id: str = None) -> str:
        tenant_id = tenant_id or self.tenant_id
        if not tenant_id:
            logger.warning("No tenant_id set for query injection")
            return query
        
        if self.has_tenant_filter(query):
            logger.debug("Query already has tenant_id filter, skipping injection")
            return query
        
        patterns = self.parse_patterns(query)
        
        entity_labels = {"Entity", "Document", "Chunk", "Community"}
        
        modified_query = query
        offset = 0
        
        for pattern in patterns:
            if not any(label in entity_labels for label in pattern.labels):
                continue
            
            if "tenant_id" in pattern.properties:
                continue
            
            pattern_str = self._reconstruct_pattern(pattern)
            new_pattern_str = self._add_tenant_to_pattern(pattern_str, tenant_id)
            
            start = query.find(pattern_str, offset)
            if start >= 0:
                end = start + len(pattern_str)
                modified_query = (
                    modified_query[:start] + new_pattern_str + modified_query[end:]
                )
                offset = start + len(new_pattern_str)
        
        return modified_query

    def _reconstruct_pattern(self, pattern: CypherPattern) -> str:
        var_part = "" if pattern.is_anonymous else pattern.variable
        labels_part = "".join(f":{label}" for label in pattern.labels)
        props_part = ""
        if pattern.properties:
            props_str = ", ".join(f"{k}: {repr(v)}" for k, v in pattern.properties.items())
            props_part = f" {{{props_str}}}"
        return f"({var_part}{labels_part}{props_part})"

    def _add_tenant_to_pattern(self, pattern_str: str, tenant_id: str) -> str:
        if "{" in pattern_str and "}" in pattern_str:
            before_brace = pattern_str.rfind("{")
            after_brace = pattern_str.rfind("}")
            props_content = pattern_str[before_brace+1:after_brace].strip()
            if props_content:
                new_props = f"{props_content}, tenant_id: {repr(tenant_id)}"
            else:
                new_props = f"tenant_id: {repr(tenant_id)}"
            return pattern_str[:before_brace+1] + " " + new_props + " " + pattern_str[after_brace:]
        else:
            return pattern_str.replace(")", f" {{tenant_id: {repr(tenant_id)}}})")

    def validate_query_safety(self, query: str, tenant_id: str = None) -> Dict[str, Any]:
        tenant_id = tenant_id or self.tenant_id
        issues = []
        
        if not tenant_id:
            issues.append("No tenant_id configured")
        
        dangerous_patterns = [
            (r'\bDETACH\s+DELETE\b', "DETACH DELETE without tenant filter"),
            (r'\bDELETE\b', "DELETE without tenant filter"),
            (r'\bSET\s+\w+\s*=', "Property SET without tenant filter"),
            (r'\bREMOVE\b', "REMOVE without tenant filter"),
            (r'CALL\s+apoc\.', "APOC procedure call - verify tenant isolation"),
        ]
        
        for pattern, message in dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                if not self.has_tenant_filter(query):
                    issues.append(message)
        
        patterns = self.parse_patterns(query)
        entity_labels = {"Entity", "Document", "Chunk", "Community"}
        
        for pattern in patterns:
            if any(label in entity_labels for label in pattern.labels):
                if "tenant_id" not in pattern.properties:
                    issues.append(f"Pattern '{pattern.variable}' missing tenant_id property")
        
        return {
            "safe": len(issues) == 0,
            "issues": issues,
            "tenant_id": tenant_id
        }

    def rewrite_query(self, query: str, tenant_id: str = None) -> str:
        validation = self.validate_query_safety(query, tenant_id)
        if not validation["safe"]:
            logger.warning(f"Query safety issues: {validation['issues']}")
        
        return self.inject_tenant_constraints(query, tenant_id)


class SafeNeo4jSession:
    def __init__(self, session, middleware: CypherASTMiddleware):
        self.session = session
        self.middleware = middleware

    def run(self, query: str, **params):
        tenant_id = params.pop("tenant_id", self.middleware.tenant_id)
        safe_query = self.middleware.rewrite_query(query, tenant_id)
        logger.debug(f"Rewritten query: {safe_query[:200]}...")
        return self.session.run(safe_query, **params)

    def execute_write(self, func, *args, **kwargs):
        def wrapped_func(tx):
            middleware = CypherASTMiddleware(self.middleware.tenant_id)
            safe_tx = SafeTransaction(tx, middleware)
            return func(safe_tx, *args, **kwargs)
        return self.session.execute_write(wrapped_func)

    def __getattr__(self, name):
        return getattr(self.session, name)


class SafeTransaction:
    def __init__(self, tx, middleware: CypherASTMiddleware):
        self.tx = tx
        self.middleware = middleware

    def run(self, query: str, **params):
        tenant_id = params.pop("tenant_id", self.middleware.tenant_id)
        safe_query = self.middleware.rewrite_query(query, tenant_id)
        return self.tx.run(safe_query, **params)

    def __getattr__(self, name):
        return getattr(self.tx, name)


def get_safe_neo4j_session(tenant_id: str):
    from app.core.database import neo4j_manager
    
    async def _get_session():
        middleware = CypherASTMiddleware(tenant_id)
        session = await neo4j_manager.get_session()
        return SafeNeo4jSession(session, middleware)
    
    return _get_session()


def create_tenant_aware_driver(tenant_id: str):
    from app.core.database import neo4j_driver
    middleware = CypherASTMiddleware(tenant_id)
    
    class TenantAwareDriver:
        def session(self):
            session = neo4j_driver.session()
            return SafeNeo4jSession(session, middleware)
        
        def close(self):
            return neo4j_driver.close()
    
    return TenantAwareDriver()