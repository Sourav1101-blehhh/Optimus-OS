import asyncio
from duckduckgo_search import DDGS
import httpx

PLUGIN_METADATA = {
    "name": "web_search",
    "description": "Searches the live internet (DuckDuckGo + Wikipedia) for information.",
    "keywords": ["search", "web", "internet", "google", "duckduckgo", "find out", "news", "wikipedia"]
}

_http_client: httpx.AsyncClient | None = None

def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            timeout=8.0,
            headers={"User-Agent": "OptimusBot/5.1 (optimus@example.com)"}
        )
    return _http_client

async def execute(args: dict = None) -> str:
    if not args or "query" not in args:
        return "Error: No search query provided."
    
    query = args["query"]
    max_results = args.get("max_results", 3)
    
    results = []
    
    try:
        def fetch_ddg():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        
        ddg_res = await asyncio.to_thread(fetch_ddg)
        for r in ddg_res:
            results.append(f"[DDG] Title: {r.get('title')}\nSnippet: {r.get('body')}\nLink: {r.get('href')}")
    except Exception as e:
        results.append(f"[DDG Error] {e}")
        
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        client = _get_http_client()
        wiki_res = await client.get(
            f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&utf8=&format=json",
            timeout=5.0,
            headers={"User-Agent": "OptimusBot/1.0 (optimus@example.com)"}
        )
        if wiki_res.status_code == 200:
            wiki_data = wiki_res.json()
            search_items = wiki_data.get("query", {}).get("search", [])[:max_results]
            for r in search_items:
                import re
                snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))
                results.append(f"[Wikipedia] Title: {r.get('title')}\nSnippet: {snippet}")
    except Exception as e:
        results.append(f"[Wikipedia Error] {e}")
        
    if not results:
        return f"No results found for query: '{query}'"
        
    return "Top Search Results:\n\n" + "\n\n".join(results)
