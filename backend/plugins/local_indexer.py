import os
import logging
import hashlib
import asyncio

PLUGIN_METADATA = {
    "name": "local_indexer",
    "description": "Indexes local directories (PDFs, DOCX, TXT) into the local_docs ChromaDB semantic search collection, or searches it. Use action='index' with 'path' to index, and action='search' with 'query' to search.",
    "keywords": ["index", "search", "local", "pdf", "docx", "documents", "files", "rag"]
}

logger = logging.getLogger("LocalIndexer")

# Get or create the local docs collection
def _get_local_docs_col():
    try:
        from backend.core.agent import _GLOBAL_CHROMA_CLIENT
        if _GLOBAL_CHROMA_CLIENT:
            return _GLOBAL_CHROMA_CLIENT.get_or_create_collection(name="optimus_local_docs")
    except Exception as e:
        logger.error(f"Failed to get local_docs collection: {e}")
    return None

async def execute(args: dict = None) -> str:
    action = args.get("action", "search")
    
    if action == "search":
        query = args.get("query")
        if not query:
            return "Error: Please provide a 'query' to search."
            
        col = _get_local_docs_col()
        if not col:
            return "Error: ChromaDB local_docs collection unavailable."
            
        try:
            results = await asyncio.to_thread(
                col.query,
                query_texts=[query],
                n_results=int(args.get("n_results", 5))
            )
            docs = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            if not docs:
                return f"No local documents found matching query: '{query}'"
                
            out = []
            for doc, meta in zip(docs, metadatas):
                source = meta.get("source", "Unknown file")
                out.append(f"--- From {source} ---\n{doc}")
            return "\n\n".join(out)
        except Exception as e:
            return f"Search failed: {e}"
            
    elif action == "index":
        path = args.get("path")
        if not path or not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."
            
        col = _get_local_docs_col()
        if not col:
            return "Error: ChromaDB local_docs collection unavailable."
            
        indexed_count = 0
        errors = []
        
        def _index_file(filepath):
            text = ""
            ext = filepath.lower().split('.')[-1]
            try:
                if ext == "pdf":
                    import fitz # PyMuPDF
                    with fitz.open(filepath) as doc:
                        text = chr(10).join([page.get_text() for page in doc])
                elif ext == "docx":
                    import docx2txt
                    text = docx2txt.process(filepath)
                elif ext in ["txt", "md", "py", "js", "html", "css", "json"]:
                    with open(filepath, "r", encoding="utf-8") as f:
                        text = f.read()
                else:
                    return 0 # Unsupported
                    
                if not text.strip():
                    return 0
                    
                # Chunking logic (simple 1000 char chunks)
                chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
                docs = []
                metas = []
                ids = []
                for i, chunk in enumerate(chunks):
                    docs.append(chunk)
                    metas.append({"source": filepath, "chunk": i})
                    ids.append(hashlib.sha256(f"{filepath}_{i}".encode()).hexdigest())
                    
                col.upsert(documents=docs, metadatas=metas, ids=ids)
                return len(chunks)
            except Exception as e:
                errors.append(f"Failed {filepath}: {e}")
                return 0
                
        # Run indexing in thread
        def _run_indexer():
            nonlocal indexed_count
            if os.path.isfile(path):
                indexed_count += _index_file(path)
            else:
                for root, _, files in os.walk(path):
                    for f in files:
                        indexed_count += _index_file(os.path.join(root, f))
                        
        await asyncio.to_thread(_run_indexer)
        
        res = f"Indexed {indexed_count} chunks from {path}."
        if errors:
            res += f"\nErrors occurred on some files: {', '.join(errors[:5])}" + ("..." if len(errors)>5 else "")
        return res
        
    else:
        return f"Error: Unknown action '{action}'."
