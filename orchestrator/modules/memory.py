# modules/memory.py

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import time
import uuid


@dataclass
class MemoryItem:
    """
    Represents a memory item that can be stored and retrieved
    """
    text: str
    type: str
    tool_name: Optional[str] = None
    user_query: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class MemoryManager:
    """
    Manages storage and retrieval of memory items
    """
    def __init__(self, embedding_model_url: str = None, model_name: str = None):
        # We're not using embeddings, but keeping the parameters for compatibility
        self.memories: List[MemoryItem] = []
    
    def add(self, item: MemoryItem):
        """
        Add a memory item to storage
        """
        self.memories.append(item)
    
    def retrieve(
        self, 
        query: str, 
        top_k: int = 5, 
        type_filter: Optional[str] = None,
        session_filter: Optional[str] = None
    ) -> List[MemoryItem]:
        """
        Retrieve the most recent relevant memories based on filters
        """
        if not self.memories:
            return []
        
        # Apply filters
        filtered_memories = self.memories.copy()
        
        # Apply type filter if specified
        if type_filter:
            filtered_memories = [m for m in filtered_memories if m.type == type_filter]
        
        # Apply session filter if specified
        if session_filter:
            filtered_memories = [m for m in filtered_memories if m.session_id == session_filter]
        
        # Sort by timestamp (most recent first)
        filtered_memories.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Return top k memories
        return filtered_memories[:top_k]
    
    def save_to_file(self, filename: str):
        """
        Save memories to a file
        """
        with open(filename, "w") as f:
            memories_dict = [
                {
                    "id": memory.id,
                    "text": memory.text,
                    "type": memory.type,
                    "tool_name": memory.tool_name,
                    "user_query": memory.user_query,
                    "tags": memory.tags,
                    "session_id": memory.session_id,
                    "timestamp": memory.timestamp,
                    "embedding": memory.embedding
                }
                for memory in self.memories
            ]
            json.dump(memories_dict, f, indent=2)
    
    def load_from_file(self, filename: str):
        """
        Load memories from a file
        """
        try:
            with open(filename, "r") as f:
                memories_dict = json.load(f)
                self.memories = [
                    MemoryItem(
                        id=memory["id"],
                        text=memory["text"],
                        type=memory["type"],
                        tool_name=memory.get("tool_name"),
                        user_query=memory.get("user_query"),
                        tags=memory.get("tags", []),
                        session_id=memory.get("session_id"),
                        timestamp=memory.get("timestamp", time.time()),
                        embedding=memory.get("embedding")
                    )
                    for memory in memories_dict
                ]
        except Exception as e:
            print(f"[memory] ⚠️ Error loading memories from file: {e}")
            self.memories = []
