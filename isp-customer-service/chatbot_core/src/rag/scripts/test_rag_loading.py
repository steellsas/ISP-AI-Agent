"""
Test RAG Document Loading
Tests loading documents from knowledge_base directories

Usage:
    cd chatbot_core
    uv run src/rag/test_rag_loading.py
"""

import sys
from pathlib import Path

# Add src to path for local imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from rag import get_retriever
from utils import get_logger

logger = get_logger(__name__)


def test_load_documents():
    """Test loading documents from knowledge base."""
    
    print("=" * 80)
    print("RAG DOCUMENT LOADING TEST")
    print("=" * 80)
    
    # Get retriever
    print("\n1. Initializing retriever...")
    retriever = get_retriever(
        top_k=3,
        similarity_threshold=0.5
    )
    print("✅ Retriever initialized")
    
    # Knowledge base path
    kb_path = Path(__file__).parent / "knowledge_base"
    print(f"\n2. Knowledge base path: {kb_path}")
    
    if not kb_path.exists():
        print(f"❌ Knowledge base not found at: {kb_path}")
        return
    
    # Load documents from each directory
    directories = [
        "troubleshooting",
        "procedures",
        "faq"
    ]
    
    total_docs = 0
    
    for directory in directories:
        dir_path = kb_path / directory
        
        if not dir_path.exists():
            print(f"\n⚠️  Directory not found: {dir_path}")
            continue
        
        print(f"\n3. Loading documents from: {directory}/")
        print("-" * 60)
        
        # Count files
        md_files = list(dir_path.glob("*.md"))
        print(f"   Found {len(md_files)} markdown files")
        
        if not md_files:
            print("   No files to load")
            continue
        
        # Load documents
        try:
            retriever.load_documents_from_directory(
                directory=dir_path,
                file_extension=".md",
                recursive=False
            )
            total_docs += len(md_files)
            print(f"✅ Loaded {len(md_files)} documents from {directory}/")
            
            # Show loaded files
            for file in md_files:
                print(f"   📄 {file.name}")
                
        except Exception as e:
            print(f"❌ Error loading from {directory}/: {e}")
    
    print("\n" + "=" * 80)
    print(f"TOTAL DOCUMENTS LOADED: {total_docs}")
    print("=" * 80)
    
    # Get statistics
    print("\n4. Retriever Statistics:")
    print("-" * 60)
    stats = retriever.get_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    return retriever


def test_retrieval(retriever):
    """Test document retrieval with queries."""
    
    print("\n" + "=" * 80)
    print("TESTING DOCUMENT RETRIEVAL")
    print("=" * 80)
    
    # Test queries in Lithuanian and English
    test_queries = [
        "Internetas neveikia",
        "Kaip perkrauti maršrutizatorių?",
        "Lėtas internetas",
        "WiFi slaptažodis",
        "Gedimo pranešimas",
        "Internet not working",
        "Slow speed"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. Query: '{query}'")
        print("-" * 60)
        
        try:
            results = retriever.retrieve(query, top_k=3)
            
            if not results:
                print("   No results found")
                continue
            
            for j, result in enumerate(results, 1):
                doc = result['document']
                score = result['score']
                metadata = result['metadata']
                
                # Get first line as title
                title = doc.split('\n')[0].replace('#', '').strip()
                
                print(f"\n   Result {j} (Score: {score:.3f})")
                print(f"   Title: {title}")
                print(f"   Category: {metadata.get('category', 'unknown')}")
                print(f"   File: {metadata.get('filename', 'unknown')}")
                
                # Show snippet (first 200 chars)
                snippet = doc[:200].replace('\n', ' ')
                print(f"   Snippet: {snippet}...")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 80)


def test_context_retrieval(retriever):
    """Test formatted context retrieval."""
    
    print("\n" + "=" * 80)
    print("TESTING CONTEXT FORMATTING")
    print("=" * 80)
    
    query = "Kaip perkrauti maršrutizatorių jei internetas neveikia?"
    
    print(f"\nQuery: '{query}'")
    print("-" * 60)
    
    try:
        context = retriever.retrieve_with_context(
            query,
            top_k=2,
            include_scores=True
        )
        
        print("\nFormatted Context:")
        print("=" * 60)
        print(context)
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")


def test_save_load(retriever):
    """Test saving and loading retriever state."""
    
    print("\n" + "=" * 80)
    print("TESTING SAVE/LOAD")
    print("=" * 80)
    
    # Save
    print("\n1. Saving retriever state...")
    try:
        retriever.save("test_kb")
        print("✅ Saved successfully")
    except Exception as e:
        print(f"❌ Save error: {e}")
        return
    
    # Create new retriever
    print("\n2. Creating new retriever...")
    new_retriever = get_retriever()
    
    # Clear to simulate fresh start
    new_retriever.vector_store.clear()
    print("✅ New retriever created (empty)")
    
    # Load
    print("\n3. Loading saved state...")
    try:
        success = new_retriever.load("test_kb")
        if success:
            print("✅ Loaded successfully")
            
            # Verify
            stats = new_retriever.get_statistics()
            print(f"\n4. Verification:")
            print(f"   Documents loaded: {stats['total_documents']}")
            
            # Test query
            print(f"\n5. Testing query on loaded retriever...")
            results = new_retriever.retrieve("Internetas neveikia", top_k=1)
            if results:
                print(f"✅ Query works! Found: {results[0]['metadata']['filename']}")
            else:
                print("⚠️  Query returned no results")
        else:
            print("❌ Load failed")
    except Exception as e:
        print(f"❌ Load error: {e}")


def main():
    """Run all tests."""
    
    try:
        # Test 1: Load documents
        retriever = test_load_documents()
        
        if retriever is None:
            print("\n❌ Failed to load documents. Stopping tests.")
            return
        
        # Test 2: Retrieval
        test_retrieval(retriever)
        
        # Test 3: Context formatting
        test_context_retrieval(retriever)
        
        # Test 4: Save/Load
        test_save_load(retriever)
        
        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
