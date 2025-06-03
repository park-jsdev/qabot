import re
from langchain.vectorstores import FAISS
from langchain.embeddings import OllamaEmbeddings
from langchain.llms import Ollama
from langchain.chains import RetrievalQAWithSourcesChain

# 1. Load embeddings and vector store
embeddings = OllamaEmbeddings(model="mistral")
vectorstore = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)

# 2. Set up the LLM and RetrievalQA chain
llm = Ollama(model="mistral")
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})  # Retrieve top 5 chunks

qa_chain = RetrievalQAWithSourcesChain.from_chain_type(
    llm=llm,
    retriever=retriever,
    return_source_documents=True,
    chain_type="stuff"
)

print("Type your questions. Type 'exit' or 'quit' to stop.\n")

def extract_possible_entities(query):
    # Adjust regexes as needed for your data
    date_pattern = r"\b(?:\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})\b"
    name_pattern = r"[A-Z][a-z]+ [A-Z][a-z]+"
    serial_pattern = r"[A-Z0-9#-]{6,}"   # Example: Serial/Record IDs with 6+ chars/digits
    dates = re.findall(date_pattern, query)
    names = re.findall(name_pattern, query)
    records = re.findall(serial_pattern, query)
    # You can add more patterns for underlined, etc.
    return set(dates + names + records)

def metadata_search(entity_values, vectorstore):
    # Retrieve all documents in the index (small sets only!)
    all_docs = vectorstore.docstore._dict.values()
    hits = []
    for doc in all_docs:
        found = False
        for field in ["dates", "names", "underlined"]:
            # metadata may have these fields as list or string
            meta_values = doc.metadata.get(field, [])
            if isinstance(meta_values, str):
                meta_values = [meta_values]
            for entity in entity_values:
                if entity in meta_values:
                    found = True
        # Also: search in header fields (e.g., version, heading)
        for field in ["heading", "version", "revision", "source"]:
            meta_value = doc.metadata.get(field)
            if meta_value and any(entity in str(meta_value) for entity in entity_values):
                found = True
        if found:
            hits.append(doc)
    return hits

while True:
    try:
        query = input("Ask a question about your SOPs: ")
        if query.strip().lower() in ["exit", "quit"]:
            print("Exiting.")
            break

        # --- Hybrid: Search metadata entities first
        entity_values = extract_possible_entities(query)
        entity_hits = metadata_search(entity_values, vectorstore) if entity_values else []
        docs = []

        if entity_hits:
            print(f"\n[Hybrid Retrieval] Found {len(entity_hits)} direct metadata matches for: {entity_values}")
            docs = entity_hits[:5]  # limit to top 5 for display/QA
            answer_context = " ".join([doc.page_content for doc in docs])
            # Use the LLM directly if you want, or use QA chain with provided docs
            answer = llm(answer_context + "\n\n" + query)
            sources = "; ".join(set([doc.metadata.get("source", "N/A") for doc in docs]))
        else:
            # Fallback: semantic search
            result = qa_chain(query)
            answer = result['answer']
            sources = result['sources']
            docs = retriever.get_relevant_documents(query)

        print("\nAnswer:\n", answer)
        print("\nSources:\n", sources)

        # ---- Print audit trail (actual text and metadata) ----
        print("\n--- Retrieved Sections for Audit ---")
        for i, doc in enumerate(docs, 1):
            print(f"\nSection {i}:")
            print("File:", doc.metadata.get("source"))
            print("Section/Heading:", doc.metadata.get("heading"))
            print("Excerpt:\n", doc.page_content.strip()[:1000])
            print("Metadata:", doc.metadata)
            print("-" * 40)
        print()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected. Exiting.")
        break
    except Exception as e:
        print(f"Error: {e}")
        print("Try again or type 'exit' to quit.")
