from duckduckgo_search import DDGS

PLUGIN_METADATA = {
    "name": "web_search",
    "description": "Searches the live internet (DuckDuckGo) for information and returns a summary of the top results.",
    "keywords": ["search", "web", "internet", "google", "duckduckgo", "find out", "news"]
}

def execute(args: dict = None) -> str:
    if not args or "query" not in args:
        return "Error: No search query provided. Please provide a 'query' argument."
    
    query = args["query"]
    max_results = args.get("max_results", 3)
    
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"Title: {r['title']}\nSnippet: {r['body']}\nLink: {r['href']}")
                
        if not results:
            return f"No results found for query: '{query}'"
            
        return "Top Search Results:\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"Error performing web search: {e}"
