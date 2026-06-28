import asyncio
import logging
import os
from typing import List

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

logger = logging.getLogger("OptimusMemory")

class RAGPipeline:
    def __init__(self, persist_dir: str = "./chroma_db"):
        self.available = CHROMA_AVAILABLE
        if not self.available:
            logger.warning("ChromaDB not installed. RAG memory disabled.")
            return

        try:
            # Ensure the directory exists
            os.makedirs(persist_dir, exist_ok=True)
            self.client = chromadb.PersistentClient(path=persist_dir)
            self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
            self.collection = self.client.get_or_create_collection(
                name="optimus_long_term",
                embedding_function=self.emb_fn
            )
            logger.info("RAG Pipeline initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.available = False

    async def inject_memory(self, user_query: str) -> str:
        """Fetch relevant past context asynchronously to avoid blocking."""
        if not self.available:
            return ""

        try:
            results = await asyncio.to_thread(
                self.collection.query,
                query_texts=[user_query],
                n_results=3
            )
            documents = results.get("documents", [[]])[0]
            if not documents:
                return ""
            
            context = "\n[RECALLED SYSTEM MEMORY]:\n" + "\n".join(documents) + "\n"
            return context
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return "" # Graceful fallback to zero memory

    def background_index(self, session_id: str, text: str):
        """Fire-and-forget indexing. Designed to be called safely."""
        if not self.available or not text.strip(): 
            return
            
        try:
            doc_id = f"{session_id}_{hash(text)}"
            self.collection.add(
                documents=[text],
                metadatas=[{"session": session_id}],
                ids=[doc_id]
            )
            logger.debug(f"Indexed memory: {doc_id}")
        except Exception as e:
            logger.error(f"Memory indexing failed: {e}")

rag_pipeline = RAGPipeline()
