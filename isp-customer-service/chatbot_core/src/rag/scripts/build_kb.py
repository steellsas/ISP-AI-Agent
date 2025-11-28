# #!/usr/bin/env python3
# """
# Knowledge Base Builder
# Builds FAISS vector store from markdown documents

# Usage:
#     cd chatbot_core
#     uv run python src/rag/scripts/build_kb.py
    
# This should be run:
# - After adding new documents
# - After updating existing documents
# - Before deploying to production
# """

# import sys
# from pathlib import Path
# from datetime import datetime

# # Setup paths for imports
# current_dir = Path(__file__).parent
# src_dir = current_dir.parent.parent
# if str(src_dir) not in sys.path:
#     sys.path.insert(0, str(src_dir))

# from rag import get_retriever

# # Import utilities from shared package
# try:
#     from isp_shared.utils import get_logger
# except ImportError:
#     # Fallback if shared package not available
#     import logging
#     logging.basicConfig(level=logging.INFO)
#     def get_logger(name):
#         return logging.getLogger(name)

# logger = get_logger(__name__)


# def build_knowledge_base(kb_name: str = "production"):
#     """
#     Build knowledge base from markdown files.
    
#     Args:
#         kb_name: Name for saved knowledge base
#     """
#     print("=" * 80)
#     print("KNOWLEDGE BASE BUILDER")
#     print("=" * 80)
    
#     # Initialize retriever
#     print("\n1. Initializing retriever...")
#     retriever = get_retriever(
#         top_k=5,
#         similarity_threshold=0.6
#     )
#     print("✅ Retriever ready")
    
#     # Knowledge base path
#     kb_path = current_dir.parent / "knowledge_base"
#     print(f"\n2. Knowledge base path: {kb_path}")
    
#     if not kb_path.exists():
#         print(f"❌ Knowledge base not found: {kb_path}")
#         return False
    
#     # Load documents from all directories
#     print("\n3. Loading documents...")
#     print("-" * 80)
    
#     directories = ["troubleshooting", "procedures", "faq"]
#     total_docs = 0
    
#     for directory in directories:
#         dir_path = kb_path / directory
        
#         if not dir_path.exists():
#             print(f"⚠️  Skipping missing directory: {directory}/")
#             continue
        
#         md_files = list(dir_path.glob("*.md"))
        
#         if not md_files:
#             print(f"⚠️  No files in: {directory}/")
#             continue
        
#         print(f"\n📁 {directory}/")
        
#         try:
#             retriever.load_documents_from_directory(
#                 directory=dir_path,
#                 file_extension=".md",
#                 recursive=False
#             )
            
#             total_docs += len(md_files)
            
#             for file in md_files:
#                 print(f"   ✅ {file.name}")
                
#         except Exception as e:
#             print(f"   ❌ Error: {e}")
#             return False
    
#     print("\n" + "-" * 80)
#     print(f"📊 Total documents loaded: {total_docs}")
    
#     if total_docs == 0:
#         print("❌ No documents loaded. Aborting.")
#         return False
    
#     # Save knowledge base
#     print(f"\n4. Saving knowledge base as '{kb_name}'...")
#     try:
#         retriever.save(kb_name)
#         print(f"✅ Saved successfully")
#     except Exception as e:
#         print(f"❌ Save failed: {e}")
#         return False
    
#     # Verify save
#     print("\n5. Verifying...")
#     stats = retriever.get_statistics()
    
#     save_path = Path(__file__).parent.parent / "vector_store_data"
#     index_file = save_path / f"{kb_name}_index.faiss"
#     meta_file = save_path / f"{kb_name}_metadata.pkl"
    
#     print(f"   Index file: {index_file.name} ({index_file.stat().st_size / 1024:.1f} KB)")
#     print(f"   Metadata file: {meta_file.name} ({meta_file.stat().st_size / 1024:.1f} KB)")
#     print(f"   Embedding model: {stats['embedding_model']}")
#     print(f"   Embedding dim: {stats['embedding_dim']}")
#     print(f"   Total docs: {stats['total_documents']}")
    
#     # Test query
#     print("\n6. Testing retrieval...")
#     test_queries = [
#         "Internetas neveikia",
#         "Kaip perkrauti maršrutizatorių",
#         "WiFi slaptažodis"
#     ]
    
#     for query in test_queries:
#         results = retriever.retrieve(query, top_k=1)
#         if results:
#             print(f"   ✅ '{query}' → {results[0]['metadata']['filename']}")
#         else:
#             print(f"   ⚠️  '{query}' → No results")
    
#     # Summary
#     print("\n" + "=" * 80)
#     print("✅ KNOWLEDGE BASE BUILD COMPLETE")
#     print("=" * 80)
#     print(f"\nBuild time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
#     print(f"KB name: {kb_name}")
#     print(f"Documents: {total_docs}")
#     print(f"Size: ~{(index_file.stat().st_size + meta_file.stat().st_size) / 1024:.1f} KB")
#     print("\nTo use in production:")
#     print(f"  retriever = get_retriever()")
#     print(f"  retriever.load('{kb_name}')")
#     print()
    
#     return True


# def rebuild_all():
#     """Rebuild all knowledge bases."""
#     print("🔄 Rebuilding all knowledge bases...\n")
    
#     # Build main production KB
#     success = build_knowledge_base("production")
    
#     if success:
#         print("\n✅ All knowledge bases rebuilt successfully!")
#     else:
#         print("\n❌ Build failed")
#         sys.exit(1)


# if __name__ == "__main__":
#     import argparse
    
#     parser = argparse.ArgumentParser(description="Build knowledge base")
#     parser.add_argument(
#         "--name",
#         default="production",
#         help="Knowledge base name (default: production)"
#     )
#     parser.add_argument(
#         "--rebuild-all",
#         action="store_true",
#         help="Rebuild all knowledge bases"
#     )
    
#     args = parser.parse_args()
    
#     try:
#         if args.rebuild_all:
#             rebuild_all()
#         else:
#             success = build_knowledge_base(args.name)
#             sys.exit(0 if success else 1)
            
#     except KeyboardInterrupt:
#         print("\n\n⚠️  Build interrupted by user")
#         sys.exit(1)
#     except Exception as e:
#         print(f"\n❌ Unexpected error: {e}")
#         import traceback
#         traceback.print_exc()
#         sys.exit(1)


#!/usr/bin/env python3
"""
Knowledge Base Builder
Builds FAISS vector store from markdown documents AND YAML scenarios

Usage:
    cd chatbot_core
    uv run python src/rag/scripts/build_kb.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Setup paths for imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from rag import get_retriever
from rag.scenario_loader import get_scenario_loader  # ← PRIDĖTI

# Import utilities from shared package
try:
    from isp_shared.utils import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)


def build_knowledge_base(kb_name: str = "production"):
    """
    Build knowledge base from markdown files AND YAML scenarios.
    
    Args:
        kb_name: Name for saved knowledge base
    """
    print("=" * 80)
    print("KNOWLEDGE BASE BUILDER (with Scenarios)")  # ← PAKEISTA
    print("=" * 80)
    
    # Initialize retriever
    print("\n1. Initializing retriever...")
    retriever = get_retriever(
        top_k=5,
        similarity_threshold=0.6
    )
    print("✅ Retriever ready")
    
    # Knowledge base path
    kb_path = current_dir.parent / "knowledge_base"
    print(f"\n2. Knowledge base path: {kb_path}")
    
    if not kb_path.exists():
        print(f"❌ Knowledge base not found: {kb_path}")
        return False
    
    # === PART 1: Load Markdown Documents ===
    print("\n3. Loading markdown documents...")
    print("-" * 80)
    
    directories = ["troubleshooting", "procedures", "faq"]
    total_docs = 0
    
    for directory in directories:
        dir_path = kb_path / directory
        
        if not dir_path.exists():
            print(f"⚠️  Skipping missing directory: {directory}/")
            continue
        
        md_files = list(dir_path.glob("*.md"))
        
        if not md_files:
            print(f"⚠️  No files in: {directory}/")
            continue
        
        print(f"\n📁 {directory}/")
        
        try:
            retriever.load_documents_from_directory(
                directory=dir_path,
                file_extension=".md",
                recursive=False
            )
            
            total_docs += len(md_files)
            
            for file in md_files:
                print(f"   ✅ {file.name}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    print("\n" + "-" * 80)
    print(f"📊 Markdown documents loaded: {total_docs}")
    
    # === PART 2: Load YAML Scenarios ===  # ← NAUJAS BLOKAS
    print("\n4. Loading YAML scenarios...")
    print("-" * 80)
    
    scenarios_loaded = 0
    try:
        # Initialize scenario loader
        scenario_loader = get_scenario_loader()
        
        # Get scenarios for embedding
        scenarios_data = scenario_loader.get_scenarios_for_embedding()
        
        if not scenarios_data:
            print("⚠️  No scenarios found")
        else:
            print(f"\n📋 Scenarios:")
            
            # Prepare data
            documents = [s["text"] for s in scenarios_data]
            metadata_list = [s["metadata"] for s in scenarios_data]
            ids = [s["id"] for s in scenarios_data]
            
            # Add to retriever
            retriever.add_documents(
                documents=documents,
                metadata=metadata_list,
                ids=ids
            )
            
            for scenario in scenarios_data:
                print(f"   ✅ {scenario['metadata']['title']} ({scenario['metadata']['scenario_id']})")
            
            scenarios_loaded = len(scenarios_data)
            print("\n" + "-" * 80)
            print(f"📊 Scenarios loaded: {scenarios_loaded}")
            total_docs += scenarios_loaded
            
    except Exception as e:
        print(f"❌ Error loading scenarios: {e}")
        import traceback
        traceback.print_exc()
        # Continue even if scenarios fail
    
    # Total
    print("\n" + "-" * 80)
    print(f"📊 TOTAL items loaded: {total_docs} ({total_docs - scenarios_loaded} docs + {scenarios_loaded} scenarios)")
    
    if total_docs == 0:
        print("❌ No documents loaded. Aborting.")
        return False
    
    # Save knowledge base
    print(f"\n5. Saving knowledge base as '{kb_name}'...")
    try:
        retriever.save(kb_name)
        print(f"✅ Saved successfully")
    except Exception as e:
        print(f"❌ Save failed: {e}")
        return False
    
    # Verify save
    print("\n6. Verifying...")
    stats = retriever.get_statistics()
    
    save_path = Path(__file__).parent.parent / "vector_store_data"
    index_file = save_path / f"{kb_name}_index.faiss"
    meta_file = save_path / f"{kb_name}_metadata.pkl"
    
    print(f"   Index file: {index_file.name} ({index_file.stat().st_size / 1024:.1f} KB)")
    print(f"   Metadata file: {meta_file.name} ({meta_file.stat().st_size / 1024:.1f} KB)")
    print(f"   Embedding model: {stats['embedding_model']}")
    print(f"   Embedding dim: {stats['embedding_dim']}")
    print(f"   Total items: {stats['total_documents']}")
    
    # Test query
    print("\n7. Testing retrieval...")
    test_queries = [
        ("neveikia internetas", "scenario"),
        ("lėtas internetas", "scenario"),
        ("TV neveikia", "scenario"),
        ("Kaip perkrauti maršrutizatorių", "document"),
    ]
    
    for query, expected_type in test_queries:
        results = retriever.retrieve(query, top_k=2)
        if results:
            result_type = results[0]['metadata'].get('type', 'unknown')
            title = results[0]['metadata'].get('title') or results[0]['metadata'].get('filename', 'Unknown')
            score = results[0]['score']
            print(f"   ✅ '{query}' → {result_type}: {title} ({score:.2f})")
        else:
            print(f"   ⚠️  '{query}' → No results")
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ KNOWLEDGE BASE BUILD COMPLETE")
    print("=" * 80)
    print(f"\nBuild time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"KB name: {kb_name}")
    print(f"Documents: {total_docs - scenarios_loaded}")
    print(f"Scenarios: {scenarios_loaded}")
    print(f"Total: {total_docs}")
    print(f"Size: ~{(index_file.stat().st_size + meta_file.stat().st_size) / 1024:.1f} KB")
    print("\nTo use in production:")
    print(f"  retriever = get_retriever()")
    print(f"  retriever.load('{kb_name}')")
    print()
    
    return True


def rebuild_all():
    """Rebuild all knowledge bases."""
    print("🔄 Rebuilding all knowledge bases...\n")
    
    # Build main production KB
    success = build_knowledge_base("production")
    
    if success:
        print("\n✅ All knowledge bases rebuilt successfully!")
    else:
        print("\n❌ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build knowledge base")
    parser.add_argument(
        "--name",
        default="production",
        help="Knowledge base name (default: production)"
    )
    parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Rebuild all knowledge bases"
    )
    
    args = parser.parse_args()
    
    try:
        if args.rebuild_all:
            rebuild_all()
        else:
            success = build_knowledge_base(args.name)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)